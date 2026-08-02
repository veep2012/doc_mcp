"""TS-TF-013 harness configuration and comparison verification.

Scenario document: documentation/test_scenarios/testing_framework_test_scenarios.md
"""

import json
from pathlib import Path

import pytest

from docmcp.harness.comparison import compare_responses
from docmcp.harness.config import HarnessConfig, HarnessError, load_config
from docmcp.harness.runner import _server_command

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_make_harness_is_thin_python_launcher():
    """TS-TF-013: Make delegates comparison work to the Python module."""
    makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
    harness_target = makefile.split(".PHONY: harness", maxsplit=1)[1]

    assert "harness: ## Compare baseline and current MCP wheels" in makefile
    assert "-m docmcp.harness" in harness_target
    assert "container run" not in harness_target


def _write_env(tmp_path: Path, **values: str) -> Path:
    defaults = {
        "HARNESS_BASELINE_WHEEL": "baseline.whl",
        "HARNESS_CURRENT_WHEEL": "current.whl",
        "HARNESS_FIXTURE_DIR": "fixture",
        "HARNESS_ARTIFACT_DIR": "artifacts",
    }
    defaults.update(values)
    path = tmp_path / ".env-harness"
    path.write_text("\n".join(f"{key}={value}" for key, value in defaults.items()), encoding="utf-8")
    return path


def _fixture(tmp_path: Path) -> None:
    fixture = tmp_path / "fixture"
    (fixture / "config").mkdir(parents=True)
    (fixture / "index").mkdir()
    (fixture / "index" / "harness.db").touch()
    (fixture / "config" / "sites.yaml").write_text(
        "sites:\n- name: Harness\n  url: https://example.test\n  auth_required: false\n"
        "  session_file: null\n  index_file: index/harness.db\n",
        encoding="utf-8",
    )
    (fixture / "mcp_requests.json").write_text(
        json.dumps(
            [
                {"jsonrpc": "2.0", "id": 1, "method": "initialize"},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "get_version"}},
                {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "search_docs"}},
                {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "search_docs"}},
                {"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "search_docs"}},
            ]
        ),
        encoding="utf-8",
    )


def test_load_config_rejects_secret_setting(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _fixture(tmp_path)
    (tmp_path / "baseline.whl").touch()
    (tmp_path / "current.whl").touch()
    monkeypatch.setattr("docmcp.harness.config.shutil.which", lambda _: "/usr/bin/podman")

    with pytest.raises(HarnessError, match="secret settings"):
        load_config(_write_env(tmp_path, API_TOKEN="not-allowed"), root=tmp_path)


def test_load_config_validates_fixture_and_corpus(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _fixture(tmp_path)
    (tmp_path / "baseline.whl").touch()
    (tmp_path / "current.whl").touch()
    monkeypatch.setattr("docmcp.harness.config.shutil.which", lambda _: "/usr/bin/docker")

    config, corpus = load_config(_write_env(tmp_path), root=tmp_path)

    assert config.container_bin == "podman"
    assert len(corpus) == 5


def test_comparison_allows_only_explicit_version_difference():
    baseline = [{"result": {"serverInfo": {"name": "doc-mcp", "version": "1.0"}}}]
    current = [{"result": {"serverInfo": {"name": "doc-mcp", "version": "2.0"}}}]

    assert compare_responses(baseline, current, ("result.serverInfo.version",)) == []
    assert compare_responses(baseline, current, ()) != []


def test_server_command_quotes_wheel_filename(tmp_path: Path):
    """TS-TF-013: configured wheel names cannot alter the container shell command."""
    config = HarnessConfig(
        tmp_path / "baseline.whl",
        tmp_path / "current;echo unexpected.whl",
        tmp_path / "fixture",
        tmp_path / "artifacts",
        "podman",
        "python:3.11-slim",
        30,
        (),
    )

    assert "'/wheels/current;echo unexpected.whl'" in _server_command(config, config.current_wheel)[-1]
