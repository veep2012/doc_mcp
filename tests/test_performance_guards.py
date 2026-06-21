import json
import time

import pytest

import docmcp.tools as tools
from docmcp.index_store import init_db, upsert_page
from docmcp.vector_index import rebuild_vector_index, vector_backend_status


def _require_vector_backend():
    available, message = vector_backend_status()
    if not available:
        pytest.skip(message or "sqlite-vec backend unavailable")


@pytest.mark.performance
def test_cold_start_keyword_search_is_fast(monkeypatch, tmp_path):
    index_file = tmp_path / "docs.db"
    init_db(str(index_file))
    upsert_page(str(index_file), "https://example.test/guide", "Guide", "Alpha beta gamma")

    monkeypatch.setattr(
        tools,
        "_get_sites",
        lambda: [
            {
                "name": "Example Docs",
                "url": "https://example.test",
                "auth_required": False,
                "index_file": str(index_file),
            }
        ],
    )

    started_at = time.perf_counter()
    response = json.loads(tools.search_docs("Example Docs", "Alpha"))
    elapsed = time.perf_counter() - started_at

    assert response["mode"] == "keyword"
    assert response["keyword_hits"] == 1
    assert elapsed < 1.0


@pytest.mark.performance
def test_post_crawl_vectorization_completes_promptly(tmp_path):
    _require_vector_backend()
    source_index = tmp_path / "index" / "docs.db"
    vector_index_file = tmp_path / "index" / "docs.vec.db"
    init_db(str(source_index))
    upsert_page(
        str(source_index),
        "https://example.test/guide",
        "Guide",
        "Alpha beta gamma delta epsilon zeta eta theta",
    )
    upsert_page(
        str(source_index),
        "https://example.test/install",
        "Install",
        "Iota kappa lambda mu nu xi omicron pi",
    )

    site = {
        "name": "Example Docs",
        "index_file": str(source_index),
        "vector_index_file": str(vector_index_file),
        "vectorizer": {
            "chunk_size": 32,
            "chunk_overlap": 8,
            "embedding_model": "fake-fastembed-model",
        },
    }

    started_at = time.perf_counter()
    summary = rebuild_vector_index(site)
    elapsed = time.perf_counter() - started_at

    assert summary.page_count == 2
    assert summary.chunk_count >= 2
    assert elapsed < 5.0


@pytest.mark.performance
def test_vector_fallback_search_returns_promptly(monkeypatch, tmp_path):
    _require_vector_backend()
    index_file = tmp_path / "docs.db"
    vector_index_file = tmp_path / "docs.vec.db"
    init_db(str(index_file))
    upsert_page(str(index_file), "https://example.test/guide", "Guide", "Alpha beta gamma")
    vector_index_file.write_bytes(b"placeholder")

    monkeypatch.setattr(
        tools,
        "_get_sites",
        lambda: [
            {
                "name": "Example Docs",
                "url": "https://example.test",
                "auth_required": False,
                "search_engine": "vector",
                "index_file": str(index_file),
                "vector_index_file": str(vector_index_file),
            }
        ],
    )
    monkeypatch.setattr(
        tools,
        "search_vector_chunks",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("broken sidecar")),
    )

    started_at = time.perf_counter()
    response = json.loads(tools.search_docs("Example Docs", "Alpha"))
    elapsed = time.perf_counter() - started_at

    assert response["mode"] == "keyword"
    assert response["error"]["type"] == "vector_index_unreadable"
    assert response["keyword_hits"] == 1
    assert elapsed < 1.0
