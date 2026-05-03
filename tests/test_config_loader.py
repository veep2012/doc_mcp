import textwrap

import pytest

from docmcp.config.loader import ConfigError, get_site_by_name, get_sites, load_config


def test_load_config_resolves_runtime_paths_and_env(monkeypatch, tmp_path):
    runtime_root = tmp_path / "runtime"
    (runtime_root / "config").mkdir(parents=True)
    (runtime_root / ".env").write_text("DOCS_URL=https://example.test/docs\n", encoding="utf-8")
    (runtime_root / "config" / "sites.yaml").write_text(
        textwrap.dedent(
            """
            sites:
              - name: "Example Docs"
                url: "${DOCS_URL}"
                auth_required: false
                session_file: "storage/example.json"
                index_file: "index/example.db"
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("DOC_MCP_HOME", str(runtime_root))
    monkeypatch.delenv("CONFIG_FILE", raising=False)
    monkeypatch.delenv("DOCS_URL", raising=False)

    config = load_config()
    site = config["sites"][0]

    assert site["url"] == "https://example.test/docs"
    assert site["session_file"] == str(runtime_root / "storage" / "example.json")
    assert site["index_file"] == str(runtime_root / "index" / "example.db")
    assert get_site_by_name("Example Docs") == site


def test_load_config_clears_previous_runtime_env_when_workspace_changes(monkeypatch, tmp_path):
    runtime_a = tmp_path / "runtime-a"
    runtime_b = tmp_path / "runtime-b"

    (runtime_a / "config").mkdir(parents=True)
    (runtime_b / "config").mkdir(parents=True)

    (runtime_a / ".env").write_text("DOCS_URL=https://workspace-a.test/docs\n", encoding="utf-8")
    (runtime_a / "config" / "sites.yaml").write_text(
        textwrap.dedent(
            """
            sites:
              - name: "Workspace A"
                url: "${DOCS_URL}"
                auth_required: false
                session_file: "storage/a.json"
                index_file: "index/a.db"
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )

    (runtime_b / "config" / "sites.yaml").write_text(
        textwrap.dedent(
            """
            sites:
              - name: "Workspace B"
                url: "${DOCS_URL}"
                auth_required: false
                session_file: "storage/b.json"
                index_file: "index/b.db"
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.delenv("DOCS_URL", raising=False)
    monkeypatch.setenv("DOC_MCP_HOME", str(runtime_a))
    monkeypatch.delenv("CONFIG_FILE", raising=False)

    first = load_config()
    assert first["sites"][0]["url"] == "https://workspace-a.test/docs"

    monkeypatch.setenv("DOC_MCP_HOME", str(runtime_b))
    second = load_config()
    assert second["sites"][0]["url"] == ""


def test_load_config_missing_file_raises_friendly_error(monkeypatch, tmp_path):
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()
    monkeypatch.setenv("DOC_MCP_HOME", str(runtime_root))

    with pytest.raises(ConfigError, match="Configuration file not found"):
        load_config()


def test_load_config_invalid_yaml_raises_config_error(monkeypatch, tmp_path):
    runtime_root = tmp_path / "runtime"
    (runtime_root / "config").mkdir(parents=True)
    (runtime_root / "config" / "sites.yaml").write_text("sites: [oops\n", encoding="utf-8")
    monkeypatch.setenv("DOC_MCP_HOME", str(runtime_root))

    with pytest.raises(ConfigError, match="not valid YAML"):
        load_config()


def test_get_sites_requires_non_empty_sites_list(monkeypatch, tmp_path):
    runtime_root = tmp_path / "runtime"
    (runtime_root / "config").mkdir(parents=True)
    (runtime_root / "config" / "sites.yaml").write_text("sites: []\n", encoding="utf-8")
    monkeypatch.setenv("DOC_MCP_HOME", str(runtime_root))

    with pytest.raises(ConfigError, match="Configuration has no sites"):
        get_sites()
