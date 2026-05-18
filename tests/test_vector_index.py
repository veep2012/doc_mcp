import sqlite3

import pytest

from docmcp.index_store import init_db, upsert_page
from docmcp.vector_index import (
    VectorIndexError,
    chunk_markdown,
    inspect_vector_index,
    read_vector_records,
    rebuild_vector_index,
    shape_vector_records,
    site_partition_key,
    site_vector_index_file,
)


def test_shape_vector_records_uses_stable_site_partition_and_chunk_ids():
    site = {
        "name": "Example Docs",
        "index_file": "/tmp/example.db",
        "vectorizer": {"chunk_size": 3, "chunk_overlap": 1, "embedding_dimensions": 8},
    }
    pages = [
        {
            "url": "https://example.test/guide",
            "title": "Guide",
            "content_md": "alpha beta gamma delta epsilon",
            "last_crawled": "2026-05-17T00:00:00+00:00",
        }
    ]

    records = shape_vector_records(site, pages)
    rebuilt_records = shape_vector_records(site, pages)

    assert [record.site_key for record in records] == ["example docs", "example docs"]
    assert [record.chunk_index for record in records] == [0, 1]
    assert records[0].chunk_text == "alpha beta gamma"
    assert records[1].chunk_text == "gamma delta epsilon"
    assert records[0].chunk_id == rebuilt_records[0].chunk_id
    assert records[0].chunk_id != records[1].chunk_id
    assert len(records[0].embedding) == 8


def test_rebuild_vector_index_creates_and_refreshes_sidecar(tmp_path):
    keyword_index_file = tmp_path / "keyword.db"
    site = {
        "name": "Example Docs",
        "index_file": str(keyword_index_file),
        "vectorizer": {"chunk_size": 3, "chunk_overlap": 1, "embedding_dimensions": 8},
    }

    init_db(str(keyword_index_file))
    upsert_page(str(keyword_index_file), "https://example.test/guide", "Guide", "alpha beta gamma")
    upsert_page(
        str(keyword_index_file),
        "https://example.test/install",
        "Install",
        "delta epsilon zeta eta",
    )

    first = rebuild_vector_index(site)
    vector_index_file = site_vector_index_file(site)
    site_key = site_partition_key(site["name"])
    first_records = read_vector_records(vector_index_file, site_key)

    assert first.page_count == 2
    assert first.chunk_count == 3
    assert len(first_records) == 3
    assert inspect_vector_index(site)["available"] is True

    with sqlite3.connect(str(keyword_index_file)) as conn:
        conn.execute("DELETE FROM pages WHERE url = ?", ("https://example.test/install",))
    upsert_page(
        str(keyword_index_file),
        "https://example.test/guide",
        "Guide",
        "omega sigma tau upsilon",
    )

    second = rebuild_vector_index(site)
    second_records = read_vector_records(vector_index_file, site_key)

    assert second.page_count == 1
    assert second.chunk_count == 2
    assert len(second_records) == 2
    assert all(record["page_url"] == "https://example.test/guide" for record in second_records)
    assert {record["chunk_text"] for record in second_records} == {
        "omega sigma tau",
        "tau upsilon",
    }
    assert all(record["page_url"] != "https://example.test/install" for record in second_records)


def test_rebuild_vector_index_fails_cleanly_without_sqlite_vec(monkeypatch, tmp_path):
    keyword_index_file = tmp_path / "keyword.db"
    site = {"name": "Example Docs", "index_file": str(keyword_index_file)}

    init_db(str(keyword_index_file))
    upsert_page(str(keyword_index_file), "https://example.test/guide", "Guide", "alpha beta gamma")

    monkeypatch.setattr("docmcp.vector_index.sqlite_vec", None)

    with pytest.raises(VectorIndexError, match="sqlite-vec is not installed"):
        rebuild_vector_index(site)


def test_rebuild_vector_index_requires_keyword_index_file(tmp_path):
    site = {"name": "Example Docs", "index_file": str(tmp_path / "missing.db")}

    with pytest.raises(VectorIndexError, match="Run docmcp-crawl first"):
        rebuild_vector_index(site)


def test_inspect_vector_index_reports_missing_sidecar(tmp_path):
    site = {"name": "Example Docs", "index_file": str(tmp_path / "keyword.db")}

    assert inspect_vector_index(site) == {
        "available": False,
        "reason": "missing",
        "vector_index_file": str(tmp_path / "keyword.vec.db"),
    }


def test_chunk_markdown_returns_empty_list_for_blank_input():
    assert chunk_markdown("", chunk_size=10, chunk_overlap=2) == []
