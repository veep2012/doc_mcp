import sys
import textwrap

import pytest

from docmcp.config.loader import ConfigError
from docmcp.index_store import init_db, upsert_page
from docmcp.vector_index import (
    VectorBackendUnavailableError,
    VectorIndexError,
    vector_backend_status,
)
from docmcp.vectorize_cli import main


def _require_vector_backend():
    available, message = vector_backend_status()
    if not available:
        pytest.skip(message or "sqlite-vec backend unavailable")


def test_vectorize_cli_builds_local_vector_index(monkeypatch, tmp_path, capsys):
    _require_vector_backend()
    runtime_root = tmp_path / "runtime"
    (runtime_root / "config").mkdir(parents=True)
    (runtime_root / "index").mkdir(parents=True)

    keyword_index = runtime_root / "index" / "docs.db"
    vector_index = runtime_root / "index" / "docs.vec.db"
    init_db(str(keyword_index))
    upsert_page(str(keyword_index), "https://example.test/guide", "Guide", "Alpha beta gamma")

    assert not vector_index.exists()

    (runtime_root / "config" / "sites.yaml").write_text(
        textwrap.dedent(
            """
            sites:
              - name: "Example Docs"
                url: "https://example.test"
                auth_required: false
                index_file: "index/docs.db"
                vector_index_file: "index/docs.vec.db"
                vectorizer:
                  chunk_size: 24
                  chunk_overlap: 6
                  embedding_model: "fake-fastembed-model"
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("DOC_MCP_HOME", str(runtime_root))
    monkeypatch.delenv("CONFIG_FILE", raising=False)
    monkeypatch.setattr(sys, "argv", ["docmcp-vectorize", "--site", "Example Docs"])

    main()

    captured = capsys.readouterr()
    assert vector_index.exists()
    assert "[vectorize] Loaded 1 pages from source index" in captured.out
    assert "[vectorize] Initializing vector index" in captured.out
    assert "[vectorize] Page 1/1 start:" in captured.out
    assert "[vectorize] Page 1/1 done: 1 chunks" in captured.out
    assert "[vectorize] Page 1/1 chunk 1" not in captured.out
    assert "[vectorize] Wrote temporary index" in captured.out
    assert "[vectorize] Replaced vector index" in captured.out
    assert "[vectorize] Done." in captured.out
    assert captured.err == ""


def test_vectorize_cli_debug_emits_chunk_progress(monkeypatch, tmp_path, capsys):
    _require_vector_backend()
    runtime_root = tmp_path / "runtime"
    (runtime_root / "config").mkdir(parents=True)
    (runtime_root / "index").mkdir(parents=True)

    keyword_index = runtime_root / "index" / "docs.db"
    vector_index = runtime_root / "index" / "docs.vec.db"
    init_db(str(keyword_index))
    upsert_page(str(keyword_index), "https://example.test/guide", "Guide", "Alpha beta gamma")

    (runtime_root / "config" / "sites.yaml").write_text(
        textwrap.dedent(
            """
            sites:
              - name: "Example Docs"
                url: "https://example.test"
                auth_required: false
                index_file: "index/docs.db"
                vector_index_file: "index/docs.vec.db"
                vectorizer:
                  chunk_size: 24
                  chunk_overlap: 6
                  embedding_model: "fake-fastembed-model"
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("DOC_MCP_HOME", str(runtime_root))
    monkeypatch.delenv("CONFIG_FILE", raising=False)
    monkeypatch.setattr(sys, "argv", ["docmcp-vectorize", "--site", "Example Docs", "--debug"])

    main()

    captured = capsys.readouterr()
    assert vector_index.exists()
    assert "[vectorize] Page 1/1 chunk 1" in captured.out
    assert "[vectorize] Page 1/1 chunking complete:" in captured.out
    assert "[vectorize] Page 1/1 embeddings written:" in captured.out
    assert "[vectorize] Page 1/1 metadata written:" in captured.out


def test_vectorize_cli_lists_configured_targets(monkeypatch, tmp_path, capsys):
    runtime_root = tmp_path / "runtime"
    (runtime_root / "config").mkdir(parents=True)
    (runtime_root / "config" / "sites.yaml").write_text(
        textwrap.dedent(
            """
            sites:
              - name: "Example Docs"
                url: "https://example.test"
                auth_required: false
                index_file: "index/docs.db"
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("DOC_MCP_HOME", str(runtime_root))
    monkeypatch.delenv("CONFIG_FILE", raising=False)
    monkeypatch.setattr(sys, "argv", ["docmcp-vectorize", "--list"])

    main()

    assert "Example Docs" in capsys.readouterr().out


def test_vectorize_cli_version_and_invalid_combo(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["docmcp-vectorize", "--version"])

    with pytest.raises(SystemExit) as excinfo:
        main()
    assert excinfo.value.code == 0
    assert capsys.readouterr().out.strip().startswith("docmcp-vectorize ")

    monkeypatch.setattr(sys, "argv", ["docmcp-vectorize", "--version", "--site", "Example Docs"])

    with pytest.raises(SystemExit) as excinfo:
        main()
    assert excinfo.value.code == 2
    assert "--version cannot be combined with other arguments" in capsys.readouterr().err


def test_vectorize_cli_reports_config_errors(monkeypatch, capsys):
    def fake_get_sites():
        raise ConfigError("broken configuration")

    monkeypatch.setattr("docmcp.vectorize_cli.get_sites", fake_get_sites)
    monkeypatch.setattr(sys, "argv", ["docmcp-vectorize", "--site", "Example Docs"])

    with pytest.raises(SystemExit) as excinfo:
        main()
    assert excinfo.value.code == 1
    assert "[docmcp-vectorize] Configuration error:" in capsys.readouterr().err


@pytest.mark.parametrize(
    "error",
    [VectorBackendUnavailableError("backend missing"), VectorIndexError("boom")],
)
def test_vectorize_cli_reports_vectorization_failures(monkeypatch, tmp_path, capsys, error):
    runtime_root = tmp_path / "runtime"
    (runtime_root / "config").mkdir(parents=True)
    (runtime_root / "index").mkdir(parents=True)

    (runtime_root / "config" / "sites.yaml").write_text(
        textwrap.dedent(
            """
            sites:
              - name: "Example Docs"
                url: "https://example.test"
                auth_required: false
                index_file: "index/docs.db"
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("DOC_MCP_HOME", str(runtime_root))
    monkeypatch.delenv("CONFIG_FILE", raising=False)
    monkeypatch.setattr(sys, "argv", ["docmcp-vectorize", "--site", "Example Docs"])
    monkeypatch.setattr(
        "docmcp.vectorize_cli.rebuild_vector_index",
        lambda site, debug=False: (_ for _ in ()).throw(error),
    )

    with pytest.raises(SystemExit) as excinfo:
        main()
    assert excinfo.value.code == 1
    stderr = capsys.readouterr().err
    if isinstance(error, VectorBackendUnavailableError):
        assert "[vectorize] Vector backend unavailable:" in stderr
    else:
        assert "[vectorize] Vectorization failed:" in stderr


def test_vectorize_cli_rejects_unknown_site(monkeypatch, tmp_path, capsys):
    runtime_root = tmp_path / "runtime"
    (runtime_root / "config").mkdir(parents=True)
    (runtime_root / "config" / "sites.yaml").write_text("sites: []\n", encoding="utf-8")

    monkeypatch.setenv("DOC_MCP_HOME", str(runtime_root))
    monkeypatch.delenv("CONFIG_FILE", raising=False)
    monkeypatch.setattr(sys, "argv", ["docmcp-vectorize", "--site", "Missing Docs"])

    with pytest.raises(SystemExit, match="1"):
        main()

    assert "Configuration has no sites" in capsys.readouterr().err
