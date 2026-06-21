import os
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
                search_engine: "vector"
                session_file: "storage/example.json"
                crawl:
                  redirect_policy: "requested"
                index_file: "index/example.db"
                vector_index_file: "index/example.vec.db"
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
    assert site["search_engine"] == "vector"
    assert site["session_file"] == str(runtime_root / "storage" / "example.json")
    assert site["crawl"]["redirect_policy"] == "requested"
    assert site["index_file"] == str(runtime_root / "index" / "example.db")
    assert site["vector_index_file"] == str(runtime_root / "index" / "example.vec.db")
    assert get_site_by_name("Example Docs") == site
    assert "DOCS_URL" not in os.environ


def test_load_config_resolves_config_file_relative_to_runtime_root(monkeypatch, tmp_path):
    runtime_root = tmp_path / "runtime"
    (runtime_root / "custom").mkdir(parents=True)
    (runtime_root / ".env").write_text("DOCS_URL=https://example.test/docs\n", encoding="utf-8")
    (runtime_root / "custom" / "sites.yaml").write_text(
        textwrap.dedent(
            """
            sites:
              - name: "Relative Config"
                url: "${DOCS_URL}"
                auth_required: false
                session_file: "storage/relative.json"
                index_file: "index/relative.db"
                vector_index_file: "index/relative.vec.db"
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("DOC_MCP_HOME", str(runtime_root))
    monkeypatch.setenv("CONFIG_FILE", "custom/sites.yaml")
    monkeypatch.delenv("DOCS_URL", raising=False)

    config = load_config()

    assert config["sites"][0]["url"] == "https://example.test/docs"
    assert config["sites"][0]["search_engine"] == "hybrid"
    assert config["sites"][0]["session_file"] == str(runtime_root / "storage" / "relative.json")
    assert config["sites"][0]["index_file"] == str(runtime_root / "index" / "relative.db")
    assert config["sites"][0]["vector_index_file"] == str(
        runtime_root / "index" / "relative.vec.db"
    )


def test_load_config_does_not_mutate_process_env_between_workspace_loads(monkeypatch, tmp_path):
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
    (runtime_b / ".env").write_text("DOCS_URL=https://workspace-b.test/docs\n", encoding="utf-8")

    monkeypatch.delenv("DOCS_URL", raising=False)
    monkeypatch.setenv("DOC_MCP_HOME", str(runtime_a))
    monkeypatch.delenv("CONFIG_FILE", raising=False)

    first = load_config()
    assert first["sites"][0]["url"] == "https://workspace-a.test/docs"
    assert "DOCS_URL" not in os.environ

    monkeypatch.setenv("DOC_MCP_HOME", str(runtime_b))
    second = load_config()
    assert second["sites"][0]["url"] == "https://workspace-b.test/docs"
    assert "DOCS_URL" not in os.environ


def test_load_config_prefers_workspace_dotenv_over_process_env(monkeypatch, tmp_path):
    runtime_root = tmp_path / "runtime"
    (runtime_root / "config").mkdir(parents=True)
    (runtime_root / ".env").write_text(
        "DOCS_URL=https://workspace-dotenv.test/docs\n", encoding="utf-8"
    )
    (runtime_root / "config" / "sites.yaml").write_text(
        textwrap.dedent(
            """
            sites:
              - name: "Workspace Dotenv"
                url: "${DOCS_URL}"
                auth_required: false
                session_file: "storage/dotenv.json"
                index_file: "index/dotenv.db"
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("DOC_MCP_HOME", str(runtime_root))
    monkeypatch.setenv("DOCS_URL", "https://process-env.test/docs")
    monkeypatch.delenv("CONFIG_FILE", raising=False)

    config = load_config()

    assert config["sites"][0]["url"] == "https://workspace-dotenv.test/docs"


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


def test_load_config_rejects_invalid_search_engine(monkeypatch, tmp_path):
    runtime_root = tmp_path / "runtime"
    (runtime_root / "config").mkdir(parents=True)
    (runtime_root / "config" / "sites.yaml").write_text(
        textwrap.dedent(
            """
            sites:
              - name: "Broken Docs"
                url: "https://example.test/docs"
                auth_required: false
                search_engine: "fuzzy"
                session_file: "storage/broken.json"
                index_file: "index/broken.db"
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("DOC_MCP_HOME", str(runtime_root))

    with pytest.raises(ConfigError, match="Invalid search_engine"):
        load_config()


@pytest.mark.parametrize(
    "config_text, expected",
    [
        (
            """
            sites:
              - name: "Bad Redirect"
                url: "https://example.test/docs"
                auth_required: false
                crawl:
                  redirect_policy: "unexpected"
                index_file: "index/bad.db"
            """,
            r"Invalid crawl\.redirect_policy for site 'Bad Redirect'",
        ),
        (
            """
            sites:
              - name: "Bad Delay"
                url: "https://example.test/docs"
                auth_required: false
                crawl:
                  delay_seconds: "fast"
                index_file: "index/bad.db"
            """,
            r"Invalid crawl\.delay_seconds for site 'Bad Delay'",
        ),
        (
            """
            sites:
              - name: "Bad Start Delay"
                url: "https://example.test/docs"
                auth_required: false
                crawl:
                  start_delay_seconds: -1
                index_file: "index/bad.db"
            """,
            r"Invalid crawl\.start_delay_seconds for site 'Bad Start Delay'",
        ),
        (
            """
                sites:
                  - name: "Bad Vectorizer"
                    url: "https://example.test/docs"
                    auth_required: false
                    index_file: "index/bad.db"
                    vectorizer:
                      chunk_size: 0
                      chunk_overlap: 0
                """,
            r"Invalid vectorizer settings for site 'Bad Vectorizer': chunk_size must be positive",
        ),
    ],
)
def test_load_config_rejects_invalid_new_config_values(
    monkeypatch, tmp_path, config_text, expected
):
    runtime_root = tmp_path / "runtime"
    (runtime_root / "config").mkdir(parents=True)
    (runtime_root / "config" / "sites.yaml").write_text(
        textwrap.dedent(config_text).strip() + "\n", encoding="utf-8"
    )

    monkeypatch.setenv("DOC_MCP_HOME", str(runtime_root))
    monkeypatch.delenv("CONFIG_FILE", raising=False)

    with pytest.raises(ConfigError, match=expected):
        load_config()
