from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
import tempfile
import urllib.error
import urllib.request
from contextlib import contextmanager
from pathlib import Path
from typing import TextIO

import pytest
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from tests.conftest import REPO_ROOT


def require_executable(command: str, guidance: str) -> str:
    executable = shutil.which(command)
    if executable is None:
        pytest.fail(f"Smoke prerequisite missing: '{command}' is not installed. {guidance}")
    return executable


def require_existing_path(path: Path, guidance: str) -> Path:
    if not path.exists():
        pytest.fail(f"Smoke prerequisite missing: expected {path}. {guidance}")
    return path


def run_checked(
    args: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    timeout: int = 120,
    description: str,
    log_path: Path | None = None,
    echo_output: bool = False,
) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            args,
            cwd=cwd,
            env=env,
            timeout=timeout,
            check=True,
            capture_output=True,
            text=True,
        )
        _write_smoke_log(log_path, args, result.stdout, result.stderr)
        if echo_output:
            _echo_process_output(result.stdout, result.stderr)
        return result
    except subprocess.TimeoutExpired:
        pytest.fail(
            f"{description} timed out after {timeout} seconds.\n"
            f"Command: {' '.join(args)}\n"
            "If you are using Podman, verify rootless networking works or retry with CONTAINER_BIN=docker."
        )
    except subprocess.CalledProcessError as exc:
        _write_smoke_log(log_path, args, exc.stdout, exc.stderr)
        if echo_output:
            _echo_process_output(exc.stdout, exc.stderr)
        pytest.fail(
            f"{description} failed with exit code {exc.returncode}.\n"
            f"STDOUT:\n{exc.stdout}\nSTDERR:\n{exc.stderr}"
        )


def _write_smoke_log(
    log_path: Path | None, args: list[str], stdout: str | None, stderr: str | None
) -> None:
    if log_path is None:
        return

    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        "\n".join(
            [
                f"$ {' '.join(args)}",
                "",
                "STDOUT:",
                stdout or "",
                "",
                "STDERR:",
                stderr or "",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _echo_process_output(stdout: str | None, stderr: str | None) -> None:
    if stdout:
        print(stdout, end="" if stdout.endswith("\n") else "\n")
    if stderr:
        print(stderr, end="" if stderr.endswith("\n") else "\n", file=sys.stderr)


def smoke_artifact_root(test_name: str) -> Path:
    root = REPO_ROOT / ".local" / "smoke"
    root.mkdir(parents=True, exist_ok=True)
    artifact_root = Path(tempfile.mkdtemp(prefix=f"{test_name}-", dir=root))
    for child in ("config", "storage", "index", "logs"):
        (artifact_root / child).mkdir(parents=True, exist_ok=True)
    return artifact_root


def smoke_log_file(runtime_root: Path, filename: str) -> Path:
    return runtime_root / "logs" / filename


def print_smoke_context(title: str, lines: list[tuple[str, str]]) -> None:
    print(f"[smoke] {title}")
    for label, value in lines:
        print(f"[smoke]   {label:<12} {value}")


def smoke_env(runtime_root: Path) -> dict[str, str]:
    return {
        **os.environ,
        "DOC_MCP_HOME": str(runtime_root),
        "CONFIG_FILE": "config/sites.yaml",
        "PYTHONPATH": str(REPO_ROOT / "src"),
        "MCP_LOG_LEVEL": "INFO",
    }


@contextmanager
def running_static_site(site_root: Path):
    container_bin = os.environ.get("CONTAINER_BIN", "podman")
    require_executable(container_bin, "Install Podman or Docker, or set CONTAINER_BIN=docker.")
    image = os.environ.get("DOCMCP_SMOKE_IMAGE", "docker.io/library/nginx:alpine")

    run_result = run_checked(
        [
            container_bin,
            "run",
            "-d",
            "--rm",
            "-p",
            "127.0.0.1::80",
            "-v",
            f"{site_root}:/usr/share/nginx/html:ro",
            image,
        ],
        timeout=90,
        description=f"Starting the smoke site container with {container_bin}",
    )
    container_id = run_result.stdout.strip()

    try:
        port_result = run_checked(
            [container_bin, "port", container_id, "80/tcp"],
            timeout=30,
            description=f"Resolving the smoke site port from {container_bin}",
        )
        port = port_result.stdout.strip().rsplit(":", 1)[-1]
        base_url = f"http://127.0.0.1:{port}/"

        deadline = time.time() + 30
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(base_url) as response:
                    if response.status == 200:
                        break
            except (urllib.error.URLError, ConnectionError):
                time.sleep(1)
        else:
            pytest.fail(
                f"Smoke site container started but {base_url} never became reachable.\n"
                f"Container runtime: {container_bin}"
            )

        yield base_url
    finally:
        subprocess.run(
            [container_bin, "stop", container_id],
            check=False,
            capture_output=True,
            text=True,
        )


async def call_search_docs(
    runtime_root: Path,
    site_name: str,
    query: str,
    *,
    errlog: TextIO | None = None,
) -> str:
    server = StdioServerParameters(
        command=sys.executable,
        args=["-m", "src.main"],
        cwd=REPO_ROOT,
        env=smoke_env(runtime_root),
    )

    async with stdio_client(server, errlog=errlog or sys.stderr) as streams:
        async with ClientSession(*streams) as session:
            await session.initialize()
            result = await session.call_tool(
                "search_docs", {"site_name": site_name, "query": query}
            )
            return result.content[0].text
