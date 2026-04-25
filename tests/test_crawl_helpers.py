from crawl_cli import _extract_links, _html_to_markdown, _is_allowed, _is_page_url, _normalize_url


def test_normalize_url_strips_query_fragment_and_trailing_slash() -> None:
    assert (
        _normalize_url("HTTPS://Example.COM/docs/guide/?page=2#intro")
        == "https://example.com/docs/guide"
    )


def test_is_page_url_filters_common_static_assets() -> None:
    assert _is_page_url("https://example.com/docs/guide") is True
    assert _is_page_url("https://example.com/assets/logo.svg") is False
    assert _is_page_url("https://example.com/app.js") is False


def test_is_allowed_enforces_scope_allow_and_deny_patterns() -> None:
    start_url = "https://example.com/docs/"

    assert _is_allowed(
        "https://example.com/docs/guide",
        start_url,
        ["https://example.com/docs/*"],
        ["https://example.com/docs/private/*"],
    )
    assert not _is_allowed(
        "https://example.com/docs/private/secret",
        start_url,
        ["https://example.com/docs/*"],
        ["https://example.com/docs/private/*"],
    )
    assert not _is_allowed(
        "https://other.example.com/docs/guide",
        start_url,
        ["https://example.com/docs/*"],
        [],
    )


def test_extract_links_normalizes_and_marks_anchor_links() -> None:
    links = _extract_links(
        "https://example.com/docs/page",
        [
            {"href": "/docs/page#section"},
            {"href": "/docs/guide/?utm=1"},
            {"href": "mailto:test@example.com"},
            {"href": "#local"},
        ],
    )

    assert links == [
        ("https://example.com/docs/page", True),
        ("https://example.com/docs/guide", False),
    ]


def test_html_to_markdown_ignores_non_content_blocks() -> None:
    html = """
    <html>
      <head><title>ignored</title></head>
      <body>
        <nav>Navigation</nav>
        <main><h1>Guide</h1><p>Hello <strong>world</strong>.</p></main>
        <script>window.bad = true;</script>
      </body>
    </html>
    """

    markdown = _html_to_markdown(html)

    assert "# Guide" in markdown
    assert "Hello **world**." in markdown
    assert "Navigation" not in markdown
    assert "window.bad" not in markdown
