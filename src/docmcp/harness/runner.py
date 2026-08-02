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


def _server_command(config: HarnessConfig, wheel: Path) -> list[str]:
    return [
        config.container_bin, "run", "--rm", "-i",
        "-v", f"{config.fixture_dir}:/fixture:ro",
        "-v", f"{wheel.parent}:/wheels:ro",
        "-e", "DOC_MCP_HOME=/fixture", "-e", "CONFIG_FILE=config/sites.yaml",
        config.image, "sh", "-c",
        f"pip install --no-cache-dir {shlex.quote(f'/wheels/{wheel.name}')} >/dev/null && exec docmcp-server",
    ]


def _run_version(config: HarnessConfig, wheel: Path, requests: list[dict], output: Path) -> list[dict]:
    command = _server_command(config, wheel)
    write_text(output / "command.log", "$ " + " ".join(command) + "\n")
    process: subprocess.Popen[str] | None = None
    try:
        process = subprocess.Popen(
            command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
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
                raise HarnessError(f"{wheel.name} closed MCP stdout before responding to {request['method']}.")
            try:
                response = json.loads(line)
            except json.JSONDecodeError as exc:
                raise HarnessError(f"{wheel.name} returned malformed MCP JSON: {line!r}") from exc
            if not isinstance(response, dict) or response.get("id") != request["id"]:
                raise HarnessError(f"{wheel.name} returned an invalid response for request id {request['id']!r}.")
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
        raise HarnessError(f"{wheel.name} timed out after {config.timeout_seconds} seconds.") from exc
    except OSError as exc:
        raise HarnessError(f"Could not start {wheel.name} with {config.container_bin}: {exc}") from exc
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
    run_dir = create_run_dir(config.artifact_dir)
    try:
        baseline = _run_version(config, config.baseline_wheel, requests, run_dir / "baseline")
        current = _run_version(config, config.current_wheel, requests, run_dir / "current")
        differences = compare_responses(baseline, current, config.allowlist)
        write_json(run_dir / "normalized" / "baseline.json", [normalize_response(item, config.allowlist) for item in baseline])
        write_json(run_dir / "normalized" / "current.json", [normalize_response(item, config.allowlist) for item in current])
        write_json(run_dir / "diff.json", differences)
        write_text(run_dir / "summary.md", f"# MCP comparison\n\nDifferences: {len(differences)}\n")
        if differences:
            raise HarnessError(f"MCP comparison found {len(differences)} unexpected difference(s). Artifacts: {run_dir}")
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
