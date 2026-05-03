from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from pathlib import Path

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
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            args,
            cwd=cwd,
            env=env,
            timeout=timeout,
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.TimeoutExpired as exc:
        pytest.fail(
            f"{description} timed out after {timeout} seconds.\n"
            f"Command: {' '.join(args)}\n"
            "If you are using Podman, verify rootless networking works or retry with CONTAINER_BIN=docker."
        )
    except subprocess.CalledProcessError as exc:
        pytest.fail(
            f"{description} failed with exit code {exc.returncode}.\n"
            f"STDOUT:\n{exc.stdout}\nSTDERR:\n{exc.stderr}"
        )


def smoke_env(runtime_root: Path) -> dict[str, str]:
    return {
        **os.environ,
        "DOC_MCP_HOME": str(runtime_root),
        "CONFIG_FILE": "config/sites.yaml",
        "PYTHONPATH": str(REPO_ROOT / "src"),
        "MCP_LOG_LEVEL": "ERROR",
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


async def call_search_docs(runtime_root: Path, site_name: str, query: str) -> str:
    server = StdioServerParameters(
        command=sys.executable,
        args=["-m", "src.main"],
        cwd=REPO_ROOT,
        env=smoke_env(runtime_root),
    )

    async with stdio_client(server) as streams:
        async with ClientSession(*streams) as session:
            await session.initialize()
            result = await session.call_tool("search_docs", {"site_name": site_name, "query": query})
            return result.content[0].text
