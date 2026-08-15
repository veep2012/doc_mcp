"""Container-backed MCP version comparison execution."""

from __future__ import annotations

import json
import selectors
import shlex
import subprocess
import sys
from pathlib import Path

from .artifacts import create_run_dir, write_json, write_text
from .comparison import compare_responses, normalize_response
from .config import HarnessConfig, HarnessError, load_config

_HARNESS_LABEL = "docmcp.harness=true"


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


def _server_command(config: HarnessConfig, wheel: Path) -> list[str]:
    log_level = "DEBUG" if config.verbose else "INFO"
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
    mounts = [
        "-v",
        f"{config.fixture_dir}:/fixture:ro",
        "-v",
        f"{wheel.parent}:/wheels:ro",
    ]
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
        config.image,
        "sh",
        "-c",
        f"{pip_command} && exec docmcp-server",
    ]


def _run_version(
    config: HarnessConfig, wheel: Path, requests: list[dict], output: Path
) -> list[dict]:
    command = _server_command(config, wheel)
    write_text(output / "command.log", "$ " + " ".join(command) + "\n")
    process: subprocess.Popen[str] | None = None
    try:
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        assert process.stdin and process.stdout
        responses = []
        for request in requests:
            process.stdin.write(json.dumps(request, separators=(",", ":")) + "\n")
            process.stdin.flush()
            selector = selectors.DefaultSelector()
            selector.register(process.stdout, selectors.EVENT_READ)
            if not selector.select(config.timeout_seconds):
                raise HarnessError(
                    f"{wheel.name} timed out after {config.timeout_seconds} seconds waiting for {request['method']}."
                )
            line = process.stdout.readline()
            selector.close()
            if not line:
                raise HarnessError(
                    f"{wheel.name} closed MCP stdout before responding to {request['method']}."
                )
            try:
                response = json.loads(line)
            except json.JSONDecodeError as exc:
                raise HarnessError(f"{wheel.name} returned malformed MCP JSON: {line!r}") from exc
            if not isinstance(response, dict) or response.get("id") != request["id"]:
                raise HarnessError(
                    f"{wheel.name} returned an invalid response for request id {request['id']!r}."
                )
            responses.append(response)
        process.stdin.close()
        process.stdin = None
        _, stderr = process.communicate(timeout=config.timeout_seconds)
        write_text(output / "stderr.log", stderr)
        write_json(output / "responses.json", responses)
        return responses
    except subprocess.TimeoutExpired as exc:
        assert process is not None
        process.kill()
        _, stderr = process.communicate()
        write_text(output / "stderr.log", stderr)
        raise HarnessError(
            f"{wheel.name} timed out after {config.timeout_seconds} seconds."
        ) from exc
    except HarnessError:
        assert process is not None
        if process.poll() is None:
            process.kill()
        _, stderr = process.communicate()
        write_text(output / "stderr.log", stderr)
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
        baseline = _run_version(config, config.baseline_wheel, requests, run_dir / "baseline")
        current = _run_version(config, config.current_wheel, requests, run_dir / "current")
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
