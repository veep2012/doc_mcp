from pathlib import Path

import pytest

from src.index.store import count_pages, get_page, init_db, list_pages, search_pages, upsert_page


def test_upsert_page_updates_existing_row(tmp_path: Path) -> None:
    db_path = tmp_path / "pages.db"

    init_db(db_path)
    upsert_page(db_path, "https://example.com/docs", "First title", "Alpha content")
    upsert_page(db_path, "https://example.com/docs", "Updated title", "Updated content")

    assert count_pages(db_path) == 1
    page = get_page(db_path, "https://example.com/docs")
    assert page is not None
    assert page["title"] == "Updated title"
    assert page["content_md"] == "Updated content"
    assert page["last_crawled"].endswith("Z")


def test_search_pages_returns_matches_and_excerpt(tmp_path: Path) -> None:
    db_path = tmp_path / "pages.db"

    upsert_page(db_path, "https://example.com/guide", "Guide", "Python smoke testing guidance")
    upsert_page(db_path, "https://example.com/other", "Other", "Completely unrelated content")

    results = search_pages(db_path, "Python guidance")

    assert len(results) == 1
    assert results[0]["title"] == "Guide"
    assert "Python" in results[0]["excerpt"]


def test_read_helpers_raise_for_missing_db(tmp_path: Path) -> None:
    missing = tmp_path / "missing.db"

    with pytest.raises(FileNotFoundError):
        count_pages(missing)
    with pytest.raises(FileNotFoundError):
        list_pages(missing)
    with pytest.raises(FileNotFoundError):
        get_page(missing, "https://example.com")
