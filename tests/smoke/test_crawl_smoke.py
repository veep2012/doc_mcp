import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
import uuid
from pathlib import Path

import pytest
import yaml

from src.index.store import count_pages, list_pages, search_pages

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "crawl_smoke_site"


def _pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_site(url: str, timeout_seconds: int = 30) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2):
                return
        except Exception:
            time.sleep(1)
    raise RuntimeError(f"Timed out waiting for smoke site at {url}")


def _run(command: list[str], **kwargs) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, text=True, capture_output=True, check=True, **kwargs)


@pytest.mark.smoke
@pytest.mark.crawl_smoke
def test_crawl_smoke_indexes_fixture_site(tmp_path: Path) -> None:
    container_bin = os.environ.get("CONTAINER_BIN", "podman")
    if shutil.which(container_bin) is None:
        pytest.skip(f"{container_bin} is not installed")

    port = _pick_free_port()
    container_name = f"doc-mcp-crawl-smoke-{uuid.uuid4().hex[:8]}"
    base_url = f"http://127.0.0.1:{port}"
    index_file = tmp_path / "crawl-smoke.db"
    config_path = tmp_path / "sites.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "sites": [
                    {
                        "name": "crawl-smoke",
                        "url": f"{base_url}/",
                        "auth_required": False,
                        "session_file": None,
                        "index_file": str(index_file),
                        "crawl": {
                            "start_url": f"{base_url}/",
                            "max_depth": 2,
                            "delay_seconds": 0,
                            "block_images": True,
                            "ignore_anchor_links": True,
                            "ignore_https_errors": False,
                            "allow_patterns": [],
                            "deny_patterns": [f"{base_url}/private/*"],
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    try:
        _run(
            [
                container_bin,
                "run",
                "--detach",
                "--rm",
                "--name",
                container_name,
                "--publish",
                f"{port}:80",
                "--mount",
                f"type=bind,src={FIXTURE_ROOT},dst=/usr/share/nginx/html,ro",
                "nginx:alpine",
            ]
        )
        try:
            _wait_for_site(f"{base_url}/")
        except RuntimeError as exc:
            pytest.skip(f"{container_bin} did not expose a reachable smoke site: {exc}")

        result = subprocess.run(
            [sys.executable, "crawl_cli.py", "--site", "crawl-smoke", "--headless"],
            cwd=REPO_ROOT,
            env={**os.environ, "CONFIG_FILE": str(config_path), "PYTHONPATH": str(REPO_ROOT)},
            text=True,
            capture_output=True,
            check=False,
        )
        assert result.returncode == 0, result.stdout + "\n" + result.stderr

        assert count_pages(index_file) == 3
        urls = {page["url"] for page in list_pages(index_file)}
        assert f"{base_url}/" in urls
        assert f"{base_url}/guide.html" in urls
        assert f"{base_url}/guide/deeper.html" in urls
        assert f"{base_url}/private/secret.html" not in urls
        search_results = search_pages(index_file, "guide")
        assert search_results
    finally:
        subprocess.run(
            [container_bin, "rm", "--force", container_name],
            text=True,
            capture_output=True,
            check=False,
        )
