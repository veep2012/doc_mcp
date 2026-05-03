from docmcp.crawl_cli import (
    _extract_links,
    _html_to_markdown,
    _is_allowed,
    _is_page_url,
    _normalize_url,
)


def test_normalize_url_strips_fragments_queries_and_trailing_slashes():
    assert (
        _normalize_url("HTTPS://Example.TEST/docs/guide/?q=1#intro")
        == "https://example.test/docs/guide"
    )


def test_is_page_url_filters_static_assets():
    assert _is_page_url("https://example.test/docs/guide.html")
    assert not _is_page_url("https://example.test/static/logo.png")
    assert not _is_page_url("https://example.test/assets/site.css")


def test_is_allowed_enforces_host_path_allow_and_deny_rules():
    start_url = "https://example.test/docs"
    allow_patterns = ["https://example.test/docs/*"]
    deny_patterns = ["https://example.test/docs/private/*"]

    assert _is_allowed("https://example.test/docs/guide", start_url, allow_patterns, deny_patterns)
    assert not _is_allowed(
        "https://example.test/docs/private/secret", start_url, allow_patterns, deny_patterns
    )
    assert not _is_allowed("https://other.test/docs/guide", start_url, allow_patterns, deny_patterns)
    assert not _is_allowed("https://example.test/blog/post", start_url, allow_patterns, deny_patterns)


def test_extract_links_marks_anchors_and_skips_non_http_targets():
    links = _extract_links(
        "https://example.test/docs/guide",
        [
            {"href": "#summary"},
            {"href": "mailto:test@example.test"},
            {"href": "javascript:void(0)"},
            {"href": "/docs/guide#details"},
            {"href": "/docs/install?source=nav"},
        ],
    )

    assert links == [
        ("https://example.test/docs/guide", True),
        ("https://example.test/docs/install", False),
    ]


def test_html_to_markdown_removes_non_content_blocks():
    markdown = _html_to_markdown(
        """
        <html>
          <head><title>Ignored</title><script>window.bad = true;</script></head>
          <body>
            <main>
              <h1>Guide</h1>
              <p>Hello <strong>docs</strong>.</p>
            </main>
            <footer>Footer text</footer>
          </body>
        </html>
        """
    )

    assert "Guide" in markdown
    assert "Hello" in markdown
    assert "window.bad" not in markdown
    assert "Footer text" not in markdown
