"""Container-backed MCP version comparison execution."""

from __future__ import annotations

import json
import selectors
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from .artifacts import create_run_dir, write_json, write_text
from .comparison import compare_responses, normalize_response
from .config import HarnessConfig, HarnessError, load_config

_HARNESS_LABEL = "docmcp.harness=true"
_BUILD_TIMEOUT_SECONDS = 900
_REQUEST_TIMEOUT_SECONDS = 180


def _cleanup_stale_containers(config: HarnessConfig) -> None:
    """Remove containers left by interrupted runs, limited to the harness label."""
    try:
        listed = subprocess.run(
            [
                config.container_bin,
                "ps",
                "-aq",
                "--filter",
                f"label={_HARNESS_LABEL}",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise HarnessError(f"Could not inspect stale harness containers: {exc}") from exc
    if listed.returncode != 0:
        detail = (listed.stderr or listed.stdout).strip()
        raise HarnessError(f"Could not inspect stale harness containers: {detail}")

    container_ids = [line.strip() for line in listed.stdout.splitlines() if line.strip()]
    if not container_ids:
        return
    try:
        removed = subprocess.run(
            [config.container_bin, "rm", "-f", *container_ids],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise HarnessError(f"Could not remove stale harness containers: {exc}") from exc
    if removed.returncode != 0:
        detail = (removed.stderr or removed.stdout).strip()
        raise HarnessError(f"Could not remove stale harness containers: {detail}")


def _server_command(config: HarnessConfig, wheel: Path, image: str | None = None) -> list[str]:
    log_level = "DEBUG" if config.verbose else "INFO"
    runtime_image = image or config.image
    pip_output = " 1>&2" if config.verbose else " >/dev/null"
    install_commands = []
    if config.requirements_file is not None:
        install_commands.append(
            "pip install "
            + ("-v " if config.verbose else "")
            + f"--no-cache-dir -r /requirements/{shlex.quote(config.requirements_file.name)}"
            + pip_output
        )
        install_commands.append(
            "pip install "
            + ("-v " if config.verbose else "")
            + f"--no-cache-dir --no-deps {shlex.quote(f'/wheels/{wheel.name}')}"
            + pip_output
        )
    else:
        install_commands.append(
            "pip install "
            + ("-v " if config.verbose else "")
            + f"--no-cache-dir {shlex.quote(f'/wheels/{wheel.name}')}"
            + pip_output
        )
    pip_command = " && ".join(install_commands)
    mounts = ["-v", f"{config.fixture_dir}:/fixture:ro"]
    if image is None:
        mounts.extend(["-v", f"{wheel.parent}:/wheels:ro"])
        if config.requirements_file is not None:
            mounts.extend(["-v", f"{config.requirements_file.parent}:/requirements:ro"])
    return [
        config.container_bin,
        "run",
        "--rm",
        "-i",
        "--label",
        _HARNESS_LABEL,
        *mounts,
        "-e",
        "DOC_MCP_HOME=/fixture",
        "-e",
        "CONFIG_FILE=config/sites.yaml",
        "-e",
        f"MCP_LOG_LEVEL={log_level}",
        runtime_image,
        "sh",
        "-c",
        f"{pip_command} && exec docmcp-server" if image is None else "exec docmcp-server",
    ]


def _build_harness_image(config: HarnessConfig, wheel: Path, role: str) -> str:
    """Build a wheel-specific image with shared MCP/vector layers cached."""
    if config.requirements_file is None:
        raise HarnessError("Harness image builds require HARNESS_REQUIREMENTS_FILE.")
    tag = f"{config.image_prefix}:{role}"
    with tempfile.TemporaryDirectory(prefix="docmcp-harness-image-") as temp_dir:
        context = Path(temp_dir)
        shutil.copy2(config.requirements_file, context / "requirements-mcp.txt")
        shutil.copy2(wheel, context / wheel.name)
        dockerfile = (
            f"FROM {config.image}\n"
            "COPY requirements-mcp.txt /tmp/requirements-mcp.txt\n"
            "RUN pip install --no-cache-dir -r /tmp/requirements-mcp.txt\n"
            'RUN python -c "from fastembed import TextEmbedding; '
            "TextEmbedding(model_name='BAAI/bge-small-en-v1.5')\"\n"
            f"COPY {wheel.name} /tmp/{wheel.name}\n"
            f"RUN pip install --no-cache-dir --no-deps /tmp/{wheel.name}\n"
        )
        (context / "Dockerfile").write_text(dockerfile, encoding="utf-8")
        command = [
            config.container_bin,
            "build",
            "--tag",
            tag,
            "--file",
            "Dockerfile",
            ".",
        ]
        try:
            result = subprocess.run(
                command,
                cwd=context,
                text=True,
                check=False,
                timeout=_BUILD_TIMEOUT_SECONDS,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise HarnessError(f"Could not build harness image {tag}: {exc}") from exc
        if result.returncode != 0:
            raise HarnessError(f"Could not build harness image {tag}.")
    return tag


def _run_version(
    config: HarnessConfig,
    wheel: Path,
    requests: list[dict],
    output: Path,
    image: str | None = None,
) -> list[dict]:
    command = _server_command(config, wheel, image)
    write_text(output / "command.log", "$ " + " ".join(command) + "\n")
    process: subprocess.Popen[str] | None = None
    stderr_path = output / "stderr.log"
    try:
        with stderr_path.open("w", encoding="utf-8") as stderr_stream:
            process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=stderr_stream,
                text=True,
            )
            assert process.stdin and process.stdout
            responses = []
            for request in requests:
                process.stdin.write(json.dumps(request, separators=(",", ":")) + "\n")
                process.stdin.flush()
                with selectors.DefaultSelector() as selector:
                    selector.register(process.stdout, selectors.EVENT_READ)
                    if not selector.select(_REQUEST_TIMEOUT_SECONDS):
                        raise HarnessError(
                            f"{wheel.name} timed out after {_REQUEST_TIMEOUT_SECONDS} seconds "
                            f"waiting for {request['method']}."
                        )
                line = process.stdout.readline()
                if not line:
                    raise HarnessError(
                        f"{wheel.name} closed MCP stdout before responding to {request['method']}."
                    )
                try:
                    response = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise HarnessError(
                        f"{wheel.name} returned malformed MCP JSON: {line!r}"
                    ) from exc
if (
    not isinstance(response, dict)
    or response.get("jsonrpc") != "2.0"
    or response.get("id") != request["id"]
    or (("result" in response) == ("error" in response))
):
    raise HarnessError(
        f"{wheel.name} returned an invalid response for request id {request['id']!r}."
    )
                responses.append(response)
            process.stdin.close()
            process.stdin = None
return_code = process.wait(timeout=_REQUEST_TIMEOUT_SECONDS)
if return_code != 0:
    raise HarnessError(f"{wheel.name} exited with status {return_code}.")
            write_json(output / "responses.json", responses)
            return responses
    except subprocess.TimeoutExpired as exc:
        assert process is not None
        process.kill()
        process.wait()
        raise HarnessError(
            f"{wheel.name} timed out after {_REQUEST_TIMEOUT_SECONDS} seconds."
        ) from exc
    except HarnessError:
        assert process is not None
        if process.poll() is None:
            process.kill()
        process.wait()
        raise
    except OSError as exc:
        raise HarnessError(
            f"Could not start {wheel.name} with {config.container_bin}: {exc}"
        ) from exc
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


def run_harness(env_file: Path | str = ".env-harness") -> Path:
    """Compare two packaged servers and return the diagnostic artifact directory."""
    config, requests = load_config(env_file)
    _cleanup_stale_containers(config)
    run_dir = create_run_dir(config.artifact_dir)
    try:
        baseline_image = _build_harness_image(config, config.baseline_wheel, "baseline")
        current_image = _build_harness_image(config, config.current_wheel, "current")
        baseline = _run_version(
            config, config.baseline_wheel, requests, run_dir / "baseline", baseline_image
        )
        current = _run_version(
            config, config.current_wheel, requests, run_dir / "current", current_image
        )
        differences = compare_responses(baseline, current, config.allowlist)
        write_json(
            run_dir / "normalized" / "baseline.json",
            [normalize_response(item, config.allowlist) for item in baseline],
        )
        write_json(
            run_dir / "normalized" / "current.json",
            [normalize_response(item, config.allowlist) for item in current],
        )
        write_json(run_dir / "diff.json", differences)
        write_text(run_dir / "summary.md", f"# MCP comparison\n\nDifferences: {len(differences)}\n")
        if differences:
            raise HarnessError(
                f"MCP comparison found {len(differences)} unexpected difference(s). Artifacts: {run_dir}"
            )
        return run_dir
    except Exception as exc:
        write_text(run_dir / "failure.log", f"{type(exc).__name__}: {exc}\n")
        raise


def main() -> None:
    try:
        print(f"MCP comparison passed. Artifacts: {run_harness()}")
    except HarnessError as exc:
        print(f"Harness failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
