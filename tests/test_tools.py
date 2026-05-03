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

    list_output = tools.list_pages("Example Docs")
    assert "Guide" in list_output
    assert "Install" in list_output

    search_output = tools.search_docs("Example Docs", "Alpha")
    assert "Search results for 'Alpha'" in search_output
    assert "Guide" in search_output

    fetch_output = tools.fetch_page("Example Docs", "https://example.test/guide")
    assert fetch_output.startswith("# Guide")
    assert "Alpha beta" in fetch_output


def test_mcp_tools_report_unknown_site(monkeypatch):
    monkeypatch.setattr(tools, "_get_sites", lambda: [])

    assert tools.list_pages("Missing Docs") == "Site 'Missing Docs' not found."
    assert tools.search_docs("Missing Docs", "query") == "Site 'Missing Docs' not found."
    assert tools.fetch_page("Missing Docs", "https://example.test") == "Site 'Missing Docs' not found."
