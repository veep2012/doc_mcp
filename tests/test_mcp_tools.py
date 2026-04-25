from pathlib import Path

from src.docmcp import tools
from src.index.store import upsert_page


def test_mcp_tools_use_monkeypatched_sites(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "docs.db"
    upsert_page(
        db_path,
        "https://example.com/getting-started",
        "Getting Started",
        "Install the package and run the smoke checks.",
    )
    monkeypatch.setattr(
        tools,
        "_get_sites",
        lambda: [
            {
                "name": "Example Docs",
                "url": "https://example.com",
                "auth_required": False,
                "index_file": str(db_path),
            }
        ],
    )

    sites_text = tools.get_sites()
    pages_text = tools.list_pages("Example Docs")
    search_text = tools.search_docs("Example Docs", "Install package")
    page_text = tools.fetch_page("Example Docs", "https://example.com/getting-started")

    assert "Example Docs" in sites_text
    assert "1 pages indexed" in sites_text
    assert "Getting Started" in pages_text
    assert "Getting Started" in search_text
    assert "smoke checks" in search_text
    assert page_text.startswith("# Getting Started")
    assert "smoke checks" in page_text


def test_mcp_tools_report_unknown_site(monkeypatch) -> None:
    monkeypatch.setattr(tools, "_get_sites", lambda: [])
    assert tools.list_pages("Missing") == "Site 'Missing' not found."
    assert tools.search_docs("Missing", "query") == "Site 'Missing' not found."
    assert tools.fetch_page("Missing", "https://example.com") == "Site 'Missing' not found."
