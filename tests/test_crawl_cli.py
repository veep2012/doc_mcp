import sys
import types
from collections import deque

import pytest

import docmcp.crawl_cli as crawl_cli
from docmcp import __version__
from docmcp.crawl_cli import (
    _disallowed_reason,
    _extract_links,
    _format_queue_preview,
    _html_to_markdown,
    _is_allowed,
    _is_page_url,
    _link_discovery_decision,
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
    assert not _is_allowed(
        "https://other.test/docs/guide", start_url, allow_patterns, deny_patterns
    )
    assert not _is_allowed(
        "https://example.test/blog/post", start_url, allow_patterns, deny_patterns
    )


def test_disallowed_reason_explains_why_url_is_filtered():
    start_url = "https://example.test/docs"
    allow_patterns = ["https://example.test/docs/*.html"]
    deny_patterns = ["https://example.test/docs/private/*"]

    assert (
        _disallowed_reason(
            "https://other.test/docs/guide", start_url, allow_patterns, deny_patterns
        )
        == "host 'other.test' is outside start host 'example.test'"
    )
    assert (
        _disallowed_reason(
            "https://example.test/docs/private/secret.html",
            start_url,
            allow_patterns,
            deny_patterns,
        )
        == "matches deny pattern 'https://example.test/docs/private/*'"
    )
    assert (
        _disallowed_reason(
            "https://example.test/docs/guide", start_url, allow_patterns, deny_patterns
        )
        == "does not match allow patterns"
    )


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


def test_format_queue_preview_summarizes_next_depth():
    queue = deque(
        [
            ("https://example.test/docs", 0),
            ("https://example.test/docs/install", 1),
            ("https://example.test/docs/api", 1),
        ]
    )

    assert _format_queue_preview(queue, depth=1, total_levels=3) == (
        "Next queue for level 2/3: 2 queued URLs -> "
        "https://example.test/docs/install, https://example.test/docs/api"
    )


def test_format_queue_preview_handles_empty_and_truncates_long_queues():
    empty_queue = deque([("https://example.test/docs", 0)])
    long_queue = deque(
        [
            ("https://example.test/docs", 0),
            ("https://example.test/docs/a", 1),
            ("https://example.test/docs/b", 1),
            ("https://example.test/docs/c", 1),
            ("https://example.test/docs/d", 1),
            ("https://example.test/docs/e", 1),
            ("https://example.test/docs/f", 1),
            ("https://example.test/docs/g", 1),
        ]
    )

    assert _format_queue_preview(empty_queue, depth=1, total_levels=3) == (
        "Next queue for level 2/3: 0 queued URLs -> (empty)"
    )
    assert _format_queue_preview(long_queue, depth=1, total_levels=3) == (
        "Next queue for level 2/3: 7 queued URLs -> "
        "https://example.test/docs/a, https://example.test/docs/b, "
        "https://example.test/docs/c, https://example.test/docs/d, "
        "https://example.test/docs/e, ... (+2 more)"
    )


def test_link_discovery_decision_reports_queue_and_skip_reasons():
    start_url = "https://example.test/docs"
    allow_patterns = ["https://example.test/docs/*"]
    deny_patterns = ["https://example.test/docs/private/*"]
    visited = {"https://example.test/docs/guide"}
    queued = {"https://example.test/docs/install"}

    assert _link_discovery_decision(
        "https://example.test/docs/guide",
        is_anchor_link=False,
        visited=visited,
        queued=queued,
        start_url=start_url,
        allow_patterns=allow_patterns,
        deny_patterns=deny_patterns,
        ignore_anchor_links=True,
    ) == (False, "already visited")
    assert _link_discovery_decision(
        "https://example.test/docs/install",
        is_anchor_link=False,
        visited=visited,
        queued=queued,
        start_url=start_url,
        allow_patterns=allow_patterns,
        deny_patterns=deny_patterns,
        ignore_anchor_links=True,
    ) == (False, "already queued")
    assert _link_discovery_decision(
        "https://example.test/docs/guide",
        is_anchor_link=True,
        visited=set(),
        queued=set(),
        start_url=start_url,
        allow_patterns=allow_patterns,
        deny_patterns=deny_patterns,
        ignore_anchor_links=True,
    ) == (False, "anchor link points to the current page")
    assert _link_discovery_decision(
        "https://example.test/docs/private/secret",
        is_anchor_link=False,
        visited=set(),
        queued=set(),
        start_url=start_url,
        allow_patterns=allow_patterns,
        deny_patterns=deny_patterns,
        ignore_anchor_links=True,
    ) == (False, "matches deny pattern 'https://example.test/docs/private/*'")
    assert _link_discovery_decision(
        "https://example.test/docs/static/logo.png",
        is_anchor_link=False,
        visited=set(),
        queued=set(),
        start_url=start_url,
        allow_patterns=allow_patterns,
        deny_patterns=deny_patterns,
        ignore_anchor_links=True,
    ) == (False, "URL points to a non-page asset")
    assert _link_discovery_decision(
        "https://example.test/docs/api",
        is_anchor_link=False,
        visited=set(),
        queued=set(),
        start_url=start_url,
        allow_patterns=allow_patterns,
        deny_patterns=deny_patterns,
        ignore_anchor_links=True,
    ) == (True, "eligible for crawl")


def test_main_accepts_debug_and_threads_it_to_crawler(monkeypatch):
    site = {"name": "Example Docs", "url": "https://example.test", "auth_required": False}
    captured = {}

    async def fake_crawl(arg_site, headless=False, debug=False):
        captured["site"] = arg_site
        captured["headless"] = headless
        captured["debug"] = debug

    monkeypatch.setattr(crawl_cli, "get_sites", lambda: [site])
    monkeypatch.setattr(crawl_cli, "crawl_site_headful", fake_crawl)
    monkeypatch.setattr(
        sys, "argv", ["docmcp-crawl", "--site", "Example Docs", "--headless", "--debug"]
    )

    crawl_cli.main()

    assert captured == {"site": site, "headless": True, "debug": True}


def test_crawl_cli_version_and_help_include_current_version(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["docmcp-crawl", "--version"])
    with pytest.raises(SystemExit) as excinfo:
        crawl_cli.main()
    assert excinfo.value.code == 0
    assert capsys.readouterr().out.strip() == f"docmcp-crawl {__version__}"

    monkeypatch.setattr(sys, "argv", ["docmcp-crawl", "--help"])
    with pytest.raises(SystemExit) as excinfo:
        crawl_cli.main()
    assert excinfo.value.code == 0
    help_text = capsys.readouterr().out
    assert f"Version: {__version__}" in help_text


def test_crawl_cli_version_rejects_other_arguments(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["docmcp-crawl", "--version", "--debug"])
    with pytest.raises(SystemExit) as excinfo:
        crawl_cli.main()
    assert excinfo.value.code == 2
    assert "--version cannot be combined with other arguments" in capsys.readouterr().err


def test_crawl_site_headful_debug_outputs_queue_and_link_reasons(monkeypatch, tmp_path, capsys):
    class FakeElement:
        def __init__(self, html):
            self.html = html

        async def inner_html(self):
            return self.html

    class FakePage:
        def __init__(self):
            self.url = ""

        async def goto(self, url, wait_until, timeout):
            self.url = url

        async def title(self):
            return "Guide"

        async def content(self):
            return "<html><body><main><h1>Guide</h1><p>Hello docs.</p></main></body></html>"

        async def query_selector(self, selector):
            if selector == "main":
                return FakeElement("<h1>Guide</h1><p>Hello docs.</p>")
            return None

        async def eval_on_selector_all(self, selector, script):
            return [
                {"href": "/docs#intro"},
                {"href": "/docs/install"},
                {"href": "/docs/install"},
                {"href": "/docs"},
                {"href": "https://other.test/docs/offsite"},
                {"href": "/docs/static/logo.png"},
            ]

    class FakeContext:
        async def new_page(self):
            return FakePage()

    class FakeBrowser:
        async def new_context(self, **kwargs):
            return FakeContext()

        async def close(self):
            return None

    class FakeChromium:
        async def launch(self, headless):
            return FakeBrowser()

    class FakePlaywrightManager:
        async def __aenter__(self):
            return types.SimpleNamespace(chromium=FakeChromium())

        async def __aexit__(self, exc_type, exc, tb):
            return False

    async def fake_sleep(delay):
        return None

    monkeypatch.setitem(
        sys.modules,
        "playwright.async_api",
        types.SimpleNamespace(async_playwright=lambda: FakePlaywrightManager()),
    )
    monkeypatch.setattr(crawl_cli.asyncio, "sleep", fake_sleep)

    site = {
        "name": "Example Docs",
        "url": "https://example.test/docs",
        "index_file": str(tmp_path / "docs.db"),
        "crawl": {
            "start_url": "https://example.test/docs",
            "max_depth": 1,
            "delay_seconds": 0,
            "ignore_anchor_links": True,
        },
    }

    import asyncio

    asyncio.run(crawl_cli.crawl_site_headful(site, headless=True, debug=True))

    captured = capsys.readouterr()
    output = captured.err
    assert "[crawl][debug] Starting level 1/2 with 1 queued URL(s)" in output
    assert "[crawl][debug] Navigating to https://example.test/docs" in output
    assert "[crawl][debug] Discovered 6 raw anchors, 6 normalized link target(s)" in output
    assert (
        "[crawl][debug] Discovered https://example.test/docs/install -> queued for level 2/2"
        in output
    )
    assert (
        "[crawl][debug] Discovered https://example.test/docs/install -> skipped (already queued)"
        in output
    )
    assert (
        "[crawl][debug] Discovered https://example.test/docs -> skipped (anchor link points to the current page)"
        in output
    )
    assert (
        "[crawl][debug] Discovered https://other.test/docs/offsite -> skipped "
        "(host 'other.test' is outside start host 'example.test')" in output
    )
    assert (
        "[crawl][debug] Discovered https://example.test/docs/static/logo.png -> skipped "
        "(URL points to a non-page asset)" in output
    )
    assert (
        "[crawl][debug] Next queue for level 2/2: 1 queued URL -> "
        "https://example.test/docs/install" in output
    )


def test_crawl_site_headful_redirects_to_final_url_and_indexes_that_url(
    monkeypatch, tmp_path, capsys
):
    indexed = []

    class FakePage:
        def __init__(self):
            self.url = ""

        async def goto(self, url, wait_until, timeout):
            self.url = "https://example.test/docs/guide?from=nav#intro"

        async def title(self):
            return "Guide"

        async def content(self):
            return "<html><body><main><h1>Guide</h1></main></body></html>"

        async def query_selector(self, selector):
            return None

        async def eval_on_selector_all(self, selector, script):
            return []

    class FakeContext:
        async def new_page(self):
            return FakePage()

    class FakeBrowser:
        async def new_context(self, **kwargs):
            return FakeContext()

        async def close(self):
            return None

    class FakeChromium:
        async def launch(self, headless):
            return FakeBrowser()

    class FakePlaywrightManager:
        async def __aenter__(self):
            return types.SimpleNamespace(chromium=FakeChromium())

        async def __aexit__(self, exc_type, exc, tb):
            return False

    async def fake_sleep(delay):
        return None

    def fake_upsert_page(index_file, url, title, content_md):
        indexed.append((index_file, url, title, content_md))

    monkeypatch.setitem(
        sys.modules,
        "playwright.async_api",
        types.SimpleNamespace(async_playwright=lambda: FakePlaywrightManager()),
    )
    monkeypatch.setattr(crawl_cli.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(crawl_cli, "upsert_page", fake_upsert_page)

    site = {
        "name": "Example Docs",
        "url": "https://example.test/docs",
        "index_file": str(tmp_path / "docs.db"),
        "crawl": {
            "start_url": "https://example.test/docs",
            "max_depth": 0,
            "delay_seconds": 0,
        },
    }

    import asyncio

    asyncio.run(crawl_cli.crawl_site_headful(site, headless=True, debug=True))

    output = capsys.readouterr()
    assert "[crawl][debug] Navigating to https://example.test/docs" in output.err
    assert "[crawl][debug] Navigation redirected to https://example.test/docs/guide" in output.err
    assert indexed[0][:3] == (
        str(tmp_path / "docs.db"),
        "https://example.test/docs/guide",
        "Guide",
    )
    assert "Guide" in indexed[0][3]
