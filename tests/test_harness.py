"""TS-TF-013 harness configuration and comparison verification.

Scenario document: documentation/test_scenarios/testing_framework_test_scenarios.md
"""

import json
import sys
from pathlib import Path

import pytest

from docmcp.harness.artifacts import write_json
from docmcp.harness.comparison import compare_responses
from docmcp.harness.config import HarnessConfig, HarnessError, load_config
from docmcp.harness.runner import _run_version, _server_command
from docmcp.harness import runner
from scripts.build_mcp_wheel import _read_mcp_requirements

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
    path.write_text(
        "\n".join(f"{key}={value}" for key, value in defaults.items()), encoding="utf-8"
    )
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
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {"name": "get_version"},
                },
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {"name": "search_docs"},
                },
                {
                    "jsonrpc": "2.0",
                    "id": 4,
                    "method": "tools/call",
                    "params": {"name": "search_docs"},
                },
                {
                    "jsonrpc": "2.0",
                    "id": 5,
                    "method": "tools/call",
                    "params": {"name": "search_docs"},
                },
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
    monkeypatch.delenv("CONTAINER_BIN", raising=False)
    monkeypatch.setattr("docmcp.harness.config.shutil.which", lambda _: "/usr/bin/docker")

    config, corpus = load_config(_write_env(tmp_path), root=tmp_path)

    assert config.container_bin == "podman"
    assert len(corpus) == 5


def test_load_config_rejects_invalid_verbose_value(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """TS-TF-015: Invalid verbosity settings fail before container execution."""
    _fixture(tmp_path)
    (tmp_path / "baseline.whl").touch()
    (tmp_path / "current.whl").touch()
    monkeypatch.setattr("docmcp.harness.config.shutil.which", lambda _: "/usr/bin/podman")

    with pytest.raises(HarnessError, match="HARNESS_VERBOSE must be true or false"):
        load_config(_write_env(tmp_path, HARNESS_VERBOSE="sometimes"), root=tmp_path)


def test_load_config_rejects_invalid_image_value(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """TS-TF-015: Invalid image names fail before container execution."""
    _fixture(tmp_path)
    (tmp_path / "baseline.whl").touch()
    (tmp_path / "current.whl").touch()
    monkeypatch.setattr("docmcp.harness.config.shutil.which", lambda _: "/usr/bin/podman")

    with pytest.raises(HarnessError, match="HARNESS_IMAGE must contain only image-repository"):
        load_config(_write_env(tmp_path, HARNESS_IMAGE="docmcp harness"), root=tmp_path)


def test_comparison_allows_only_explicit_version_difference():
    baseline = [{"result": {"serverInfo": {"name": "doc-mcp", "version": "1.0"}}}]
    current = [{"result": {"serverInfo": {"name": "doc-mcp", "version": "2.0"}}}]

    assert compare_responses(baseline, current, ("result.serverInfo.version",)) == []
    assert compare_responses(baseline, current, ()) != []


def test_comparison_allowlists_version_in_get_version_tool_payload():
    """TS-TF-013: Allowlist the version without hiding another tool-result change."""
    baseline_payload = json.dumps(
        {"package_name": "doc-mcp", "server_name": "docs-mcp", "version": "1.1.1"}, indent=2
    )
    current_payload = json.dumps(
        {"package_name": "doc-mcp", "server_name": "docs-mcp", "version": "1.1.2"}, indent=2
    )
    baseline = [
        {
            "result": {
                "content": [{"type": "text", "text": baseline_payload}],
                "structuredContent": {"result": baseline_payload},
            }
        }
    ]
    current = [
        {
            "result": {
                "content": [{"type": "text", "text": current_payload}],
                "structuredContent": {"result": current_payload},
            }
        }
    ]
    allowlist = ("result.content.0.text.version", "result.structuredContent.result.version")

    assert compare_responses(baseline, current, allowlist) == []

    current[0]["result"]["content"][0]["text"] = json.dumps(
        {"package_name": "doc-mcp", "server_name": "other-server", "version": "1.1.2"},
        indent=2,
    )
    assert compare_responses(baseline, current, allowlist) != []


def test_server_command_quotes_wheel_filename(tmp_path: Path):
    """TS-TF-013: configured wheel names cannot alter the container shell command."""
    config = HarnessConfig(
        tmp_path / "baseline.whl",
        tmp_path / "current;echo unexpected.whl",
        tmp_path / "fixture",
        tmp_path / "artifacts",
        "podman",
        "python:3.11-slim",
        (),
    )

    assert (
        "'/wheels/current;echo unexpected.whl'" in _server_command(config, config.current_wheel)[-1]
    )

    assert "--label" in _server_command(config, config.current_wheel)
    assert "docmcp.harness=true" in _server_command(config, config.current_wheel)


def test_server_command_verbose_mode_exposes_install_and_server_logs(tmp_path: Path):
    """TS-TF-013: Verbose harness runs expose pip and server diagnostics."""
    config = HarnessConfig(
        tmp_path / "baseline.whl",
        tmp_path / "current.whl",
        tmp_path / "fixture",
        tmp_path / "artifacts",
        "podman",
        "python:3.11-slim",
        (),
        None,
        True,
    )

    command = _server_command(config, config.current_wheel)

    assert "MCP_LOG_LEVEL=DEBUG" in command
    assert "pip install -v --no-cache-dir" in command[-1]
    assert "1>&2" in command[-1]


def test_server_command_uses_prebuilt_harness_image(tmp_path: Path):
    """TS-TF-013: Tagged harness images start without reinstalling dependencies."""
    config = HarnessConfig(
        tmp_path / "baseline.whl",
        tmp_path / "current.whl",
        tmp_path / "fixture",
        tmp_path / "artifacts",
        "podman",
        "python:3.11-slim",
        (),
    )

    command = _server_command(config, config.current_wheel, "docmcp-harness:current")

    assert "docmcp-harness:current" in command
    assert "exec docmcp-server" == command[-1]
    assert "pip install" not in " ".join(command)
    assert "/wheels" not in " ".join(command)


def test_run_version_streams_large_stderr_without_blocking_stdout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """TS-TF-013: Verbose stderr cannot deadlock MCP response processing."""
    child = (
        "import json,sys\n"
        "for line in sys.stdin:\n"
        " request=json.loads(line)\n"
        " sys.stderr.write('x' * 262144)\n"
        " sys.stderr.flush()\n"
        " print(json.dumps({'jsonrpc':'2.0','id':request['id'],'result':{}}), flush=True)\n"
    )
    monkeypatch.setattr(
        "docmcp.harness.runner._server_command",
        lambda _config, _wheel, _image=None: [sys.executable, "-c", child],
    )
    config = HarnessConfig(
        tmp_path / "baseline.whl",
        tmp_path / "current.whl",
        tmp_path / "fixture",
        tmp_path / "artifacts",
        "podman",
        "python:3.11-slim",
        (),
    )
    output = tmp_path / "run"
    requests = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call"},
    ]

    responses = _run_version(config, config.current_wheel, requests, output)

    assert [response["id"] for response in responses] == [1, 2]
    assert (output / "stderr.log").stat().st_size == 524288


def _run_version_with_child(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, child: str) -> None:
    monkeypatch.setattr(
        "docmcp.harness.runner._server_command",
        lambda _config, _wheel, _image=None: [sys.executable, "-c", child],
    )
    config = HarnessConfig(
        tmp_path / "baseline.whl",
        tmp_path / "current.whl",
        tmp_path / "fixture",
        tmp_path / "artifacts",
        "podman",
        "python:3.11-slim",
        (),
    )
    with pytest.raises(HarnessError):
        _run_version(
            config,
            config.current_wheel,
            [{"jsonrpc": "2.0", "id": 1, "method": "initialize"}],
            tmp_path / "run",
        )
    assert (tmp_path / "run" / "stderr.log").is_file()


def test_run_version_rejects_malformed_response(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """TS-TF-016: Malformed MCP output fails the version run."""
    _run_version_with_child(
        tmp_path,
        monkeypatch,
        "import sys; next(sys.stdin); print('not-json', flush=True)",
    )


def test_run_version_rejects_mismatched_response_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """TS-TF-016: A response for the wrong request ID fails the version run."""
    _run_version_with_child(
        tmp_path,
        monkeypatch,
        "import json,sys; request=json.loads(next(sys.stdin)); print(json.dumps({'id': 99}), flush=True)",
    )


def test_run_version_rejects_early_server_exit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """TS-TF-016: A server that closes stdout before responding fails the version run."""
    _run_version_with_child(tmp_path, monkeypatch, "import sys; next(sys.stdin)")


def test_run_harness_preserves_comparison_failure_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """TS-TF-016: Unexpected differences retain a failure log and diff artifact."""
    config = HarnessConfig(
        tmp_path / "baseline.whl",
        tmp_path / "current.whl",
        tmp_path / "fixture",
        tmp_path / "artifacts",
        "podman",
        "python:3.11-slim",
        (),
    )
    monkeypatch.setattr(runner, "load_config", lambda _env: (config, [{"id": 1}]))
    monkeypatch.setattr(runner, "_cleanup_stale_containers", lambda _config: None)
    monkeypatch.setattr(
        runner, "_build_harness_image", lambda _config, _wheel, role: f"image:{role}"
    )

    def fake_run_version(_config, _wheel, _requests, output, _image):
        value = "baseline" if output.name == "baseline" else "current"
        return [{"id": 1, "result": value}]

    monkeypatch.setattr(runner, "_run_version", fake_run_version)

    with pytest.raises(HarnessError, match="unexpected difference"):
        runner.run_harness(tmp_path / ".env-harness")

    run_dirs = list((tmp_path / "artifacts").iterdir())
    assert len(run_dirs) == 1
    assert (run_dirs[0] / "diff.json").is_file()
    assert (run_dirs[0] / "failure.log").is_file()


def test_server_command_uses_minimal_requirements_profile(tmp_path: Path):
    """TS-TF-013: Harness installs MCP dependencies without crawler extras."""
    requirements = tmp_path / "requirements-mcp.txt"
    requirements.write_text("mcp==1.28.1\n", encoding="utf-8")
    config = HarnessConfig(
        tmp_path / "baseline.whl",
        tmp_path / "current.whl",
        tmp_path / "fixture",
        tmp_path / "artifacts",
        "podman",
        "python:3.11-slim",
        (),
        requirements,
    )

    command = _server_command(config, config.current_wheel)

    assert "/requirements/requirements-mcp.txt" in command[-1]
    assert "pip install --no-cache-dir --no-deps /wheels/current.whl" in command[-1]


def test_mcp_profile_includes_vector_runtime_without_crawler_extras():
    """TS-TF-013: MCP-only harness installs vector lookup dependencies."""
    requirements = (REPO_ROOT / "requirements-mcp.txt").read_text(encoding="utf-8")

    assert "fastembed==0.8.0" in requirements
    assert "sqlite-vec==0.1.9" in requirements
    assert "playwright" not in requirements
    assert "markdownify" not in requirements
    assert "pypdf" not in requirements


def test_mcp_wheel_metadata_reads_the_shared_requirements_profile(tmp_path: Path):
    """TS-TF-013: MCP wheel metadata has no independently duplicated versions."""
    requirements_file = tmp_path / "requirements-mcp.txt"
    requirements_file.write_text(
        "# comment\nmcp==9.9.9\nfastembed==8.8.8  # pinned vector runtime\n", encoding="utf-8"
    )

    assert _read_mcp_requirements(requirements_file) == (
        "Requires-Dist: mcp==9.9.9",
        "Requires-Dist: fastembed==8.8.8",
    )


def test_project_metadata_reads_full_runtime_requirements_file():
    """TS-TF-013: Full wheel dependencies are not duplicated in pyproject.toml."""
    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert 'dynamic = ["dependencies"]' in pyproject
    assert 'dependencies = {file = ["requirements.txt"]}' in pyproject
    assert "playwright==" not in pyproject
    assert "fastembed==" not in pyproject


def test_json_artifacts_redact_nested_credentials(tmp_path: Path):
    """TS-TF-014: Structured diagnostics redact nested and JSON-encoded credentials."""
    artifact = tmp_path / "artifact.json"
    write_json(
        artifact,
        {
            "token": "top-secret",
            "nested": [{"api_key": "nested-secret"}],
            "tool_text": json.dumps({"password": "encoded-secret", "ok": True}),
        },
    )

    content = artifact.read_text(encoding="utf-8")
    payload = json.loads(content)
    assert payload["token"] == "[REDACTED]"
    assert payload["nested"][0]["api_key"] == "[REDACTED]"
    assert json.loads(payload["tool_text"])["password"] == "[REDACTED]"
    assert "top-secret" not in content
    assert "nested-secret" not in content
    assert "encoded-secret" not in content
