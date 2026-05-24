import sqlite3

import pytest
import sqlite_vec

from docmcp.index_store import init_db, upsert_page
from docmcp.vector_index import (
    VectorSourceError,
    build_vector_records,
    chunk_markdown,
    rebuild_vector_index,
    resolve_vector_index_file,
    _normalize_chunk_settings,
    vector_backend_status,
)


def _require_vector_backend():
    available, message = vector_backend_status()
    if not available:
        pytest.skip(message or "sqlite-vec backend unavailable")


def _read_vector_db(index_file):
    _require_vector_backend()
    conn = sqlite3.connect(str(index_file))
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    return conn


def test_build_vector_records_shapes_stable_chunk_records():
    records = build_vector_records(
        "Example Docs",
        [
            {
                "url": "https://example.test/guide",
                "title": "Guide",
                "content_md": "Alpha beta gamma delta epsilon zeta eta theta",
                "last_crawled": "2026-05-23T00:00:00+00:00",
            }
        ],
        chunk_size=20,
        chunk_overlap=5,
        embedding_dimensions=8,
    )

    assert len(records) >= 2
    assert records[0].site_name == "Example Docs"
    assert records[0].page_url == "https://example.test/guide"
    assert records[0].title == "Guide"
    assert records[0].chunk_index == 0
    assert len(records[0].embedding) == 8
    assert records[0].chunk_id
    assert records[0].chunk_text
    assert (
        build_vector_records(
            "Example Docs",
            [
                {
                    "url": "https://example.test/guide",
                    "title": "Guide",
                    "content_md": "Alpha beta gamma delta epsilon zeta eta theta",
                    "last_crawled": "2026-05-23T00:00:00+00:00",
                }
            ],
            chunk_size=20,
            chunk_overlap=5,
            embedding_dimensions=8,
        )
        == records
    )


def test_chunk_markdown_handles_oversized_tokens():
    text = "alpha " + ("x" * 1200) + " beta gamma"

    chunks = chunk_markdown(text, chunk_size=800, chunk_overlap=120)

    assert chunks
    assert chunks[0].startswith("alpha")
    assert any("x" * 1200 in chunk for chunk in chunks)
    assert chunks[-1].endswith("gamma")


def test_vector_backend_status_reports_missing_dependency(monkeypatch):
    monkeypatch.setattr("docmcp.vector_index.sqlite_vec", None)

    available, message = vector_backend_status()

    assert not available
    assert "pip install sqlite-vec" in message


def test_resolve_vector_index_file_defaults_to_sidecar_name(tmp_path):
    site = {"index_file": str(tmp_path / "index" / "docs.db")}

    assert resolve_vector_index_file(site) == str(tmp_path / "index" / "docs.vec.db")


@pytest.mark.parametrize(
    "chunk_size, chunk_overlap, embedding_dimensions, expected",
    [
        (0, 5, 8, "chunk_size must be positive"),
        (18, 5, 0, "embedding_dimensions must be positive"),
    ],
)
def test_normalize_chunk_settings_rejects_explicit_zero_values(
    chunk_size, chunk_overlap, embedding_dimensions, expected
):
    with pytest.raises(ValueError, match=expected):
        _normalize_chunk_settings(chunk_size, chunk_overlap, embedding_dimensions)


def test_rebuild_vector_index_creates_and_refreshes_sidecar(tmp_path):
    _require_vector_backend()
    source_index = tmp_path / "index" / "docs.db"
    vector_index = tmp_path / "index" / "docs.vec.db"
    init_db(str(source_index))
    upsert_page(
        str(source_index),
        "https://example.test/guide",
        "Guide",
        "Alpha beta gamma delta epsilon",
    )

    site = {
        "name": "Example Docs",
        "index_file": str(source_index),
        "vector_index_file": str(vector_index),
        "vectorizer": {"chunk_size": 18, "chunk_overlap": 5, "embedding_dimensions": 8},
    }

    summary = rebuild_vector_index(site)

    assert summary.page_count == 1
    assert summary.chunk_count >= 2
    assert vector_index.exists()

    with _read_vector_db(vector_index) as conn:
        first_rows = conn.execute(
            "SELECT chunk_id, page_url, title, chunk_text FROM vector_chunks ORDER BY chunk_index"
        ).fetchall()
        meta = conn.execute(
            "SELECT site_name, page_count, chunk_count, embedding_dimensions FROM vector_meta"
        ).fetchone()

    assert meta == ("Example Docs", 1, len(first_rows), 8)
    assert all(row[1] == "https://example.test/guide" for row in first_rows)

    upsert_page(
        str(source_index),
        "https://example.test/guide",
        "Guide Updated",
        "Alpha beta gamma delta epsilon zeta eta theta iota",
    )

    rebuild_vector_index(site)

    with _read_vector_db(vector_index) as conn:
        second_rows = conn.execute(
            "SELECT chunk_id, title, chunk_text FROM vector_chunks ORDER BY chunk_index"
        ).fetchall()

    assert second_rows != first_rows
    assert all(row[1] == "Guide Updated" for row in second_rows)
    assert len({row[0] for row in second_rows}) == len(second_rows)
    assert len(second_rows) >= len(first_rows)
    assert any("theta" in row[2] for row in second_rows)


def test_rebuild_vector_index_requires_existing_keyword_index(tmp_path):
    site = {
        "name": "Example Docs",
        "index_file": str(tmp_path / "missing" / "docs.db"),
        "vector_index_file": str(tmp_path / "index" / "docs.vec.db"),
    }

    with pytest.raises(VectorSourceError, match="Run docmcp-crawl before docmcp-vectorize"):
        rebuild_vector_index(site)
