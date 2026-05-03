from docmcp.index_store import count_pages, get_page, init_db, list_pages, search_pages, upsert_page


def test_index_store_round_trip_and_upsert(tmp_path):
    index_file = tmp_path / "docs.db"

    init_db(str(index_file))
    assert count_pages(str(index_file)) == 0

    upsert_page(str(index_file), "https://example.test/guide", "Guide", "Alpha beta content")
    upsert_page(str(index_file), "https://example.test/install", "Install", "Gamma delta content")
    upsert_page(
        str(index_file),
        "https://example.test/guide",
        "Guide Updated",
        "Alpha beta updated content",
    )

    assert count_pages(str(index_file)) == 2
    assert get_page(str(index_file), "https://example.test/missing") is None

    page = get_page(str(index_file), "https://example.test/guide")
    assert page is not None
    assert page["title"] == "Guide Updated"
    assert "updated" in page["content_md"]

    titles = [page["title"] for page in list_pages(str(index_file))]
    assert titles == ["Guide Updated", "Install"]

    results = search_pages(str(index_file), "Alpha")
    assert len(results) == 1
    assert results[0]["url"] == "https://example.test/guide"
    assert "[Alpha]" in results[0]["excerpt"]
