import json
import logging
import sqlite3

import pytest

import docmcp.tools as tools
import docmcp.vector_index as vector_index
from docmcp.index_store import init_db, upsert_page
from docmcp.vector_index import rebuild_vector_index, vector_backend_status


def _require_vector_backend():
    available, message = vector_backend_status()
    if not available:
        pytest.skip(message or "sqlite-vec backend unavailable")


def test_mcp_tools_return_site_pages_search_and_fetch(monkeypatch, tmp_path):
    index_file = tmp_path / "docs.db"
    init_db(str(index_file))
    upsert_page(str(index_file), "https://example.test/guide", "Guide", "Alpha beta")
    upsert_page(str(index_file), "https://example.test/install", "Install", "Gamma delta")

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

    sites_output = tools.get_sites()
    assert "Example Docs" in sites_output
    assert "2 pages indexed" in sites_output
    assert "Index:" not in sites_output
    assert "Session:" not in sites_output

    list_output = tools.list_pages("Example Docs")
    assert "Guide" in list_output
    assert "Install" in list_output

    search_output = json.loads(tools.search_docs("Example Docs", "Alpha"))
    assert search_output["mode"] == "keyword"
    assert search_output["vector_hits"] == 0
    assert search_output["keyword_hits"] == 1
    assert search_output["results"] == [
        {
            "text": "[Alpha] beta",
            "page_url": "https://example.test/guide",
            "title": "Guide",
            "score": search_output["results"][0]["score"],
            "source": "keyword",
        }
    ]
    assert isinstance(search_output["results"][0]["score"], float)

    fetch_output = tools.fetch_page("Example Docs", "https://example.test/guide")
    assert fetch_output.startswith("# Guide")
    assert "Alpha beta" in fetch_output


def test_keyword_score_is_monotonic_with_result_order():
    assert tools._keyword_score(-0.001, 0) > tools._keyword_score(-10.0, 1)
    assert tools._keyword_score(-10.0, 1) > tools._keyword_score(-20.0, 2)


def test_mcp_tools_report_unknown_site(monkeypatch):
    monkeypatch.setattr(tools, "_get_sites", lambda: [])

    assert tools.list_pages("Missing Docs") == "Site 'Missing Docs' not found."
    assert json.loads(tools.search_docs("Missing Docs", "query")) == {
        "mode": "keyword",
        "vector_hits": 0,
        "keyword_hits": 0,
        "results": [],
        "error": {
            "type": "site_not_found",
            "message": "Site 'Missing Docs' not found.",
        },
    }
    assert (
        tools.fetch_page("Missing Docs", "https://example.test") == "Site 'Missing Docs' not found."
    )


def test_search_docs_returns_empty_json_for_empty_or_missing_indexes(monkeypatch, tmp_path):
    empty_index_file = tmp_path / "empty.db"
    init_db(str(empty_index_file))

    missing_index_file = tmp_path / "missing" / "docs.db"

    monkeypatch.setattr(
        tools,
        "_get_sites",
        lambda: [
            {
                "name": "Empty Docs",
                "url": "https://empty.example.test",
                "auth_required": False,
                "index_file": str(empty_index_file),
            },
            {
                "name": "Missing Docs",
                "url": "https://missing.example.test",
                "auth_required": False,
                "index_file": str(missing_index_file),
            },
        ],
    )

    expected = {"mode": "keyword", "vector_hits": 0, "keyword_hits": 0, "results": []}

    assert json.loads(tools.search_docs("Empty Docs", "Alpha")) == expected
    assert json.loads(tools.search_docs("Missing Docs", "Alpha")) == expected


def test_search_docs_returns_empty_json_for_zero_match_query(monkeypatch, tmp_path):
    index_file = tmp_path / "docs.db"
    init_db(str(index_file))
    upsert_page(str(index_file), "https://example.test/guide", "Guide", "Alpha beta")

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

    assert json.loads(tools.search_docs("Example Docs", "Omega")) == {
        "mode": "keyword",
        "vector_hits": 0,
        "keyword_hits": 0,
        "results": [],
    }


def test_search_docs_keyword_mode_skips_vector_lookup(monkeypatch, tmp_path):
    index_file = tmp_path / "docs.db"
    init_db(str(index_file))
    upsert_page(str(index_file), "https://example.test/guide", "Guide", "Alpha beta")

    monkeypatch.setattr(
        tools,
        "_get_sites",
        lambda: [
            {
                "name": "Keyword Docs",
                "url": "https://example.test",
                "auth_required": False,
                "search_engine": "keyword",
                "index_file": str(index_file),
                "vector_index_file": str(tmp_path / "docs.vec.db"),
            }
        ],
    )

    monkeypatch.setattr(
        tools,
        "search_vector_chunks",
        lambda *args, **kwargs: pytest.fail("vector search should not be called"),
    )

    response = json.loads(tools.search_docs("Keyword Docs", "Alpha"))

    assert response["mode"] == "keyword"
    assert response["vector_hits"] == 0
    assert response["keyword_hits"] == 1
    assert response["results"] == [
        {
            "text": "[Alpha] beta",
            "page_url": "https://example.test/guide",
            "title": "Guide",
            "score": response["results"][0]["score"],
            "source": "keyword",
        }
    ]
    assert isinstance(response["results"][0]["score"], float)


def test_search_docs_vector_mode_returns_vector_results_and_skips_keyword(monkeypatch, tmp_path):
    index_file = tmp_path / "docs.db"
    vector_index_file = tmp_path / "docs.vec.db"
    init_db(str(index_file))
    vector_index_file.write_bytes(b"placeholder")

    monkeypatch.setattr(
        tools,
        "_get_sites",
        lambda: [
            {
                "name": "Vector Docs",
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
        "search_pages",
        lambda *args, **kwargs: pytest.fail("keyword search should not be called"),
    )
    monkeypatch.setattr(
        tools,
        "search_vector_chunks",
        lambda site, query, limit: [
            {
                "chunk_id": "chunk-1",
                "page_url": "https://example.test/vector",
                "title": "Vector Guide",
                "text": "Alpha beta",
                "distance": 0.25,
            }
        ],
    )

    response = json.loads(tools.search_docs("Vector Docs", "Alpha"))

    assert response["mode"] == "vector"
    assert response["vector_hits"] == 1
    assert response["keyword_hits"] == 0
    assert response["results"] == [
        {
            "text": "Alpha beta",
            "page_url": "https://example.test/vector",
            "title": "Vector Guide",
            "score": 0.8,
            "source": "vector",
        }
    ]


def test_search_docs_vector_mode_reports_missing_sidecar(monkeypatch, tmp_path):
    index_file = tmp_path / "docs.db"
    vector_index_file = tmp_path / "docs.vec.db"
    init_db(str(index_file))

    monkeypatch.setattr(
        tools,
        "_get_sites",
        lambda: [
            {
                "name": "Vector Docs",
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
        lambda *args, **kwargs: pytest.fail("vector search should not be called"),
    )

    response = json.loads(tools.search_docs("Vector Docs", "Alpha"))

    assert response["mode"] == "vector"
    assert response["vector_hits"] == 0
    assert response["keyword_hits"] == 0
    assert response["results"] == []
    assert response["error"]["type"] == "vector_index_missing"
    assert "sidecar is missing" in response["error"]["message"]


def test_search_docs_vector_mode_reports_unreadable_sidecar(monkeypatch, tmp_path):
    index_file = tmp_path / "docs.db"
    vector_index_file = tmp_path / "docs.vec.db"
    init_db(str(index_file))
    vector_index_file.write_bytes(b"not a sqlite database")

    monkeypatch.setattr(
        tools,
        "_get_sites",
        lambda: [
            {
                "name": "Vector Docs",
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
        lambda *args, **kwargs: (_ for _ in ()).throw(sqlite3.DatabaseError("broken")),
    )

    response = json.loads(tools.search_docs("Vector Docs", "Alpha"))

    assert response["mode"] == "vector"
    assert response["vector_hits"] == 0
    assert response["keyword_hits"] == 0
    assert response["results"] == []
    assert response["error"]["type"] == "vector_index_unreadable"
    assert "unreadable" in response["error"]["message"]


def test_search_docs_vector_mode_reports_missing_fastembed_backend(monkeypatch, tmp_path):
    _require_vector_backend()
    index_file = tmp_path / "docs.db"
    vector_index_file = tmp_path / "docs.vec.db"
    init_db(str(index_file))
    upsert_page(str(index_file), "https://example.test/vector", "Vector", "Alpha beta")

    site = {
        "name": "Vector Docs",
        "url": "https://example.test",
        "auth_required": False,
        "search_engine": "vector",
        "index_file": str(index_file),
        "vector_index_file": str(vector_index_file),
        "vectorizer": {"embedding_model": "fake-fastembed-model"},
    }
    rebuild_vector_index(site)

    monkeypatch.setattr(
        tools,
        "_get_sites",
        lambda: [site],
    )
    monkeypatch.setattr(
        vector_index,
        "_load_text_embedding_backend",
        lambda model_name: (_ for _ in ()).throw(
            tools.VectorBackendUnavailableError("fastembed is not installed")
        ),
    )

    response = json.loads(tools.search_docs("Vector Docs", "Alpha"))

    assert response["mode"] == "vector"
    assert response["vector_hits"] == 0
    assert response["keyword_hits"] == 0
    assert response["results"] == []
    assert response["error"]["type"] == "vector_backend_unavailable"
    assert "fastembed is not installed" in response["error"]["message"]


def test_search_docs_returns_empty_json_on_sqlite_query_error(monkeypatch, tmp_path):
    index_file = tmp_path / "docs.db"

    def raise_sqlite_error(index_file: str, query: str, limit: int) -> list[dict]:
        raise sqlite3.OperationalError("broken")

    monkeypatch.setattr(
        tools,
        "_get_sites",
        lambda: [
            {
                "name": "Broken Docs",
                "url": "https://example.test",
                "auth_required": False,
                "index_file": str(index_file),
            }
        ],
    )
    monkeypatch.setattr(
        tools,
        "search_pages",
        raise_sqlite_error,
    )

    assert json.loads(tools.search_docs("Broken Docs", "Alpha")) == {
        "mode": "keyword",
        "vector_hits": 0,
        "keyword_hits": 0,
        "results": [],
    }


def test_search_docs_logs_hybrid_vector_degradation(monkeypatch, tmp_path, caplog):
    index_file = tmp_path / "docs.db"
    init_db(str(index_file))
    upsert_page(str(index_file), "https://example.test/guide", "Guide", "Alpha beta")

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

    def raise_sqlite_error(index_file: str, query: str, limit: int) -> list[dict]:
        raise sqlite3.OperationalError("broken vector index")

    monkeypatch.setattr(tools, "search_vector_chunks", raise_sqlite_error)

    caplog.set_level(logging.WARNING, logger="docmcp.tools")
    response = json.loads(tools.search_docs("Example Docs", "Alpha"))

    assert response["mode"] == "keyword"
    assert response["vector_hits"] == 0
    assert response["keyword_hits"] == 1
    assert any(
        record.name == "docmcp.tools"
        and "Hybrid search degraded to keyword" in record.message
        and "OperationalError" in record.message
        for record in caplog.records
    )


def test_search_docs_rejects_non_positive_limit(monkeypatch, tmp_path):
    index_file = tmp_path / "docs.db"
    init_db(str(index_file))
    upsert_page(str(index_file), "https://example.test/guide", "Guide", "Alpha beta")

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

    expected = {"mode": "keyword", "vector_hits": 0, "keyword_hits": 0, "results": []}

    assert json.loads(tools.search_docs("Example Docs", "Alpha", limit=0)) == expected


def test_normalize_search_results_use_shared_schema():
    keyword_results = tools._normalize_keyword_results(
        [
            {
                "url": "https://example.test/guide",
                "title": "Guide",
                "excerpt": "Alpha beta",
                "rank": -1.0,
            }
        ]
    )
    vector_results = tools._normalize_vector_results(
        [
            {
                "chunk_id": "chunk-1",
                "page_url": "https://example.test/guide",
                "title": "Guide",
                "text": "Alpha beta",
                "distance": 0.25,
            }
        ]
    )

    assert keyword_results == [
        {
            "text": "Alpha beta",
            "page_url": "https://example.test/guide",
            "title": "Guide",
            "score": 1.0,
            "source": "keyword",
            "_dedupe_keys": ("text:https://example.test/guide\nAlpha beta",),
        }
    ]
    assert vector_results == [
        {
            "text": "Alpha beta",
            "page_url": "https://example.test/guide",
            "title": "Guide",
            "score": 0.8,
            "source": "vector",
            "_dedupe_keys": (
                "chunk:chunk-1",
                "text:https://example.test/guide\nAlpha beta",
            ),
        }
    ]


def test_merge_search_results_prefers_vector_order_and_deduplicates():
    vector_results = [
        {
            "text": "Alpha beta",
            "page_url": "https://example.test/guide",
            "title": "Guide",
            "score": 0.9,
            "source": "vector",
            "_dedupe_keys": (
                "chunk:chunk-1",
                "text:https://example.test/guide\nAlpha beta",
            ),
        },
        {
            "text": "Gamma delta",
            "page_url": "https://example.test/reference",
            "title": "Reference",
            "score": 0.7,
            "source": "vector",
            "_dedupe_keys": (
                "chunk:chunk-2",
                "text:https://example.test/reference\nGamma delta",
            ),
        },
    ]
    keyword_results = [
        {
            "text": "Alpha beta",
            "page_url": "https://example.test/guide",
            "title": "Guide",
            "score": 1.0,
            "source": "keyword",
            "_dedupe_keys": ("text:https://example.test/guide\nAlpha beta",),
        },
        {
            "text": "Install alpha",
            "page_url": "https://example.test/install",
            "title": "Install",
            "score": 0.5,
            "source": "keyword",
            "_dedupe_keys": ("text:https://example.test/install\nInstall alpha",),
        },
    ]

    merged_results, contributors = tools._merge_search_results(vector_results, keyword_results, 10)

    assert contributors == {"keyword", "vector"}
    assert merged_results == [
        {
            "text": "Alpha beta",
            "page_url": "https://example.test/guide",
            "title": "Guide",
            "score": 0.9,
            "source": "vector",
        },
        {
            "text": "Gamma delta",
            "page_url": "https://example.test/reference",
            "title": "Reference",
            "score": 0.7,
            "source": "vector",
        },
        {
            "text": "Install alpha",
            "page_url": "https://example.test/install",
            "title": "Install",
            "score": 0.5,
            "source": "keyword",
        },
    ]


def test_merge_search_results_keeps_distinct_keyword_snippets_from_same_page():
    vector_results = [
        {
            "text": "Alpha beta",
            "page_url": "https://example.test/guide",
            "title": "Guide",
            "score": 0.9,
            "source": "vector",
            "_dedupe_keys": (
                "chunk:chunk-1",
                "text:https://example.test/guide\nAlpha beta",
            ),
        }
    ]
    keyword_results = [
        {
            "text": "Alpha beta gamma",
            "page_url": "https://example.test/guide",
            "title": "Guide",
            "score": 1.0,
            "source": "keyword",
            "_dedupe_keys": ("text:https://example.test/guide\nAlpha beta gamma",),
        }
    ]

    merged_results, contributors = tools._merge_search_results(vector_results, keyword_results, 10)

    assert contributors == {"keyword", "vector"}
    assert merged_results == [
        {
            "text": "Alpha beta",
            "page_url": "https://example.test/guide",
            "title": "Guide",
            "score": 0.9,
            "source": "vector",
        },
        {
            "text": "Alpha beta gamma",
            "page_url": "https://example.test/guide",
            "title": "Guide",
            "score": 1.0,
            "source": "keyword",
        },
    ]


def test_merge_search_results_preserves_same_page_keyword_hits_in_hybrid_mode():
    vector_results = [
        {
            "text": "Alpha beta",
            "page_url": "https://example.test/guide",
            "title": "Guide",
            "score": 0.92,
            "source": "vector",
            "_dedupe_keys": (
                "chunk:chunk-1",
                "text:https://example.test/guide\nAlpha beta",
            ),
        }
    ]
    keyword_results = [
        {
            "text": "Alpha beta gamma",
            "page_url": "https://example.test/guide",
            "title": "Guide",
            "score": 1.0,
            "source": "keyword",
            "_dedupe_keys": ("text:https://example.test/guide\nAlpha beta gamma",),
        }
    ]

    merged_results, contributors = tools._merge_search_results(vector_results, keyword_results, 10)

    assert contributors == {"keyword", "vector"}
    assert [result["source"] for result in merged_results] == ["vector", "keyword"]
    assert merged_results[0]["page_url"] == "https://example.test/guide"
    assert merged_results[1]["page_url"] == "https://example.test/guide"
    assert merged_results[1]["text"] == "Alpha beta gamma"


@pytest.mark.parametrize(
    ("vector_results", "keyword_results", "expected_mode"),
    [
        (
            [
                {
                    "chunk_id": "chunk-1",
                    "page_url": "https://example.test/vector",
                    "title": "Vector",
                    "text": "Alpha beta",
                    "distance": 0.1,
                }
            ],
            [],
            "vector",
        ),
        (
            [
                {
                    "chunk_id": "chunk-1",
                    "page_url": "https://example.test/shared",
                    "title": "Shared",
                    "text": "Alpha beta",
                    "distance": 0.1,
                }
            ],
            [
                {
                    "url": "https://example.test/shared",
                    "title": "Shared",
                    "excerpt": "Alpha beta",
                    "rank": -1.0,
                }
            ],
            "vector",
        ),
        (
            [
                {
                    "chunk_id": "chunk-1",
                    "page_url": "https://example.test/vector",
                    "title": "Vector",
                    "text": "Alpha beta",
                    "distance": 0.1,
                }
            ],
            [
                {
                    "url": "https://example.test/keyword",
                    "title": "Keyword",
                    "excerpt": "Alpha beta keyword",
                    "rank": -1.0,
                }
            ],
            "hybrid",
        ),
    ],
)
def test_search_response_selects_mode_from_unique_source_contributors(
    vector_results, keyword_results, expected_mode
):
    response = tools._search_response(keyword_results, vector_results, limit=10)

    assert response["mode"] == expected_mode
    assert response["vector_hits"] == len(vector_results)
    assert response["keyword_hits"] == len(keyword_results)


def test_search_docs_falls_back_to_keyword_when_vector_lookup_fails(monkeypatch, tmp_path):
    index_file = tmp_path / "docs.db"
    init_db(str(index_file))
    upsert_page(str(index_file), "https://example.test/guide", "Guide", "Alpha beta")

    monkeypatch.setattr(
        tools,
        "_get_sites",
        lambda: [
            {
                "name": "Example Docs",
                "url": "https://example.test",
                "auth_required": False,
                "index_file": str(index_file),
                "vector_index_file": str(tmp_path / "docs.vec.db"),
            }
        ],
    )

    def _mock_vector_search_error(site: dict, query: str, limit: int) -> list[dict]:
        raise sqlite3.OperationalError("broken vector index")

    monkeypatch.setattr(tools, "search_vector_chunks", _mock_vector_search_error)

    response = json.loads(tools.search_docs("Example Docs", "Alpha"))

    assert response == {
        "mode": "keyword",
        "vector_hits": 0,
        "keyword_hits": 1,
        "results": [
            {
                "text": "[Alpha] beta",
                "page_url": "https://example.test/guide",
                "title": "Guide",
                "score": response["results"][0]["score"],
                "source": "keyword",
            }
        ],
    }
    assert isinstance(response["results"][0]["score"], float)


def test_search_docs_returns_vector_only_results_when_keyword_has_no_hits(monkeypatch, tmp_path):
    index_file = tmp_path / "docs.db"
    init_db(str(index_file))

    monkeypatch.setattr(
        tools,
        "_get_sites",
        lambda: [
            {
                "name": "Example Docs",
                "url": "https://example.test",
                "auth_required": False,
                "index_file": str(index_file),
                "vector_index_file": str(tmp_path / "docs.vec.db"),
            }
        ],
    )
    monkeypatch.setattr(
        tools,
        "search_vector_chunks",
        lambda site, query, limit: [
            {
                "chunk_id": "chunk-1",
                "page_url": "https://example.test/vector",
                "title": "Vector Guide",
                "text": "Alpha beta",
                "distance": 0.25,
            }
        ],
    )

    response = json.loads(tools.search_docs("Example Docs", "Alpha"))

    assert response == {
        "mode": "vector",
        "vector_hits": 1,
        "keyword_hits": 0,
        "results": [
            {
                "text": "Alpha beta",
                "page_url": "https://example.test/vector",
                "title": "Vector Guide",
                "score": 0.8,
                "source": "vector",
            }
        ],
    }


def test_search_docs_returns_keyword_results_when_vector_lookup_returns_no_hits(
    monkeypatch, tmp_path, caplog
):
    index_file = tmp_path / "docs.db"
    init_db(str(index_file))
    upsert_page(str(index_file), "https://example.test/guide", "Guide", "Alpha beta")

    monkeypatch.setattr(
        tools,
        "_get_sites",
        lambda: [
            {
                "name": "Example Docs",
                "url": "https://example.test",
                "auth_required": False,
                "index_file": str(index_file),
                "vector_index_file": str(tmp_path / "docs.vec.db"),
            }
        ],
    )
    monkeypatch.setattr(tools, "search_vector_chunks", lambda site, query, limit: [])

    caplog.set_level(logging.WARNING, logger="docmcp.tools")
    response = json.loads(tools.search_docs("Example Docs", "Alpha"))

    assert response == {
        "mode": "keyword",
        "vector_hits": 0,
        "keyword_hits": 1,
        "results": [
            {
                "text": "[Alpha] beta",
                "page_url": "https://example.test/guide",
                "title": "Guide",
                "score": response["results"][0]["score"],
                "source": "keyword",
            }
        ],
    }
    assert isinstance(response["results"][0]["score"], float)
    assert not any(
        "Hybrid search degraded to keyword" in record.message for record in caplog.records
    )


def test_search_docs_returns_hybrid_results_with_partial_vector_sidecar(monkeypatch, tmp_path):
    _require_vector_backend()

    index_file = tmp_path / "docs.db"
    vector_index_file = tmp_path / "docs.vec.db"
    init_db(str(index_file))
    upsert_page(
        str(index_file),
        "https://example.test/vector-best",
        "Vector Best",
        "Alpha alpha alpha beta",
    )
    upsert_page(
        str(index_file),
        "https://example.test/vector-only",
        "Vector Only",
        "Gamma delta epsilon zeta",
    )

    site = {
        "name": "Example Docs",
        "url": "https://example.test",
        "auth_required": False,
        "index_file": str(index_file),
        "vector_index_file": str(vector_index_file),
        "vectorizer": {
            "chunk_size": 100,
            "chunk_overlap": 20,
            "embedding_model": "fake-fastembed-model",
        },
    }
    rebuild_vector_index(site)

    upsert_page(
        str(index_file),
        "https://example.test/keyword-only",
        "Keyword Only",
        "Alpha beta gamma delta",
    )

    monkeypatch.setattr(tools, "_get_sites", lambda: [site])

    response = json.loads(tools.search_docs("Example Docs", "Alpha", limit=3))

    assert response["mode"] == "hybrid"
    assert response["vector_hits"] == 2
    assert response["keyword_hits"] == 2
    assert [result["source"] for result in response["results"]] == [
        "vector",
        "vector",
        "keyword",
    ]
    assert response["results"][0]["page_url"] == "https://example.test/vector-best"
    assert response["results"][1]["page_url"] == "https://example.test/vector-only"
    assert response["results"][2]["page_url"] == "https://example.test/vector-best"
    assert response["results"][2]["title"] == "Vector Best"
    assert response["results"][2]["text"].startswith("[Alpha]")
    assert all(isinstance(result["score"], float) for result in response["results"])


def test_search_docs_falls_back_when_vector_sidecar_is_unreadable(monkeypatch, tmp_path):
    index_file = tmp_path / "docs.db"
    vector_index_file = tmp_path / "docs.vec.db"
    init_db(str(index_file))
    upsert_page(str(index_file), "https://example.test/guide", "Guide", "Alpha beta")
    vector_index_file.write_bytes(b"not a sqlite database")

    monkeypatch.setattr(
        tools,
        "_get_sites",
        lambda: [
            {
                "name": "Example Docs",
                "url": "https://example.test",
                "auth_required": False,
                "index_file": str(index_file),
                "vector_index_file": str(vector_index_file),
            }
        ],
    )

    response = json.loads(tools.search_docs("Example Docs", "Alpha"))

    assert response == {
        "mode": "keyword",
        "vector_hits": 0,
        "keyword_hits": 1,
        "results": [
            {
                "text": "[Alpha] beta",
                "page_url": "https://example.test/guide",
                "title": "Guide",
                "score": response["results"][0]["score"],
                "source": "keyword",
            }
        ],
    }
    assert isinstance(response["results"][0]["score"], float)


def test_get_version_returns_server_metadata(monkeypatch):
    monkeypatch.setenv("MCP_SERVER_NAME", "docs-mcp")

    payload = json.loads(tools.get_version())

    assert payload == {
        "package_name": "doc-mcp",
        "server_name": "docs-mcp",
        "version": "0.99.3",
    }
