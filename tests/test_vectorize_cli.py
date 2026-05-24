import sys
import textwrap

import pytest

from docmcp.index_store import init_db, upsert_page
from docmcp.vector_index import vector_backend_status
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
                  embedding_dimensions: 8
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
                  embedding_dimensions: 8
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
