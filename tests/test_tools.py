import json
import sqlite3

import docmcp.tools as tools
from docmcp.index_store import init_db, upsert_page


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


def test_get_version_returns_server_metadata(monkeypatch):
    monkeypatch.setenv("MCP_SERVER_NAME", "docs-mcp")

    payload = json.loads(tools.get_version())

    assert payload == {
        "package_name": "doc-mcp",
        "server_name": "docs-mcp",
        "version": "0.99.0",
    }
