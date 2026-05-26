import asyncio
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


def test_normalize_url_strips_fragments_queries_and_trailing_slashes_by_default():
    assert (
        _normalize_url("HTTPS://Example.TEST/docs/guide/?q=1#intro")
        == "https://example.test/docs/guide"
    )


def test_normalize_url_can_preserve_query_strings():
    assert (
        _normalize_url(
            "HTTPS://Example.TEST/docs/guide/?q=1#intro",
            strip_query=False,
        )
        == "https://example.test/docs/guide?q=1"
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
    ]


def test_extract_links_skips_or_preserves_query_links_based_on_setting():
    link_elements = [
        {"href": "/docs/guide?tab=api#details"},
        {"href": "/docs/install?source=nav"},
        {"href": "/docs/install"},
    ]

    assert _extract_links("https://example.test/docs/guide?tab=api", link_elements) == [
        ("https://example.test/docs/guide?tab=api", True),
        ("https://example.test/docs/install", False),
    ]
    assert _extract_links(
        "https://example.test/docs/guide?tab=api",
        link_elements,
        ignore_query_links=False,
    ) == [
        ("https://example.test/docs/guide?tab=api", True),
        ("https://example.test/docs/install?source=nav", False),
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


def test_main_authenticates_before_crawling_when_required(monkeypatch):
    site = {"name": "Example Docs", "url": "https://example.test", "auth_required": True}
    calls = []

    def fake_authenticate(arg_site, force=False):
        calls.append(("auth", arg_site, force))

    async def fake_crawl(arg_site, headless=False, debug=False):
        calls.append(("crawl", arg_site, headless, debug))

    monkeypatch.setattr(crawl_cli, "get_sites", lambda: [site])
    monkeypatch.setattr(crawl_cli, "crawl_site_headful", fake_crawl)
    monkeypatch.setattr(crawl_cli, "_authenticate_site", fake_authenticate)
    monkeypatch.setattr(sys, "argv", ["docmcp-crawl", "--site", "Example Docs"])

    crawl_cli.main()

    assert calls == [
        ("auth", site, False),
        ("crawl", site, False, False),
    ]


def test_authenticate_site_awaits_async_authenticate(monkeypatch):
    site = {"name": "Example Docs", "url": "https://example.test", "auth_required": True}
    calls = []

    async def fake_authenticate(arg_site, force=False):
        calls.append(("auth", arg_site, force))

    monkeypatch.setitem(
        sys.modules,
        "docmcp.auth.session",
        types.SimpleNamespace(authenticate=fake_authenticate),
    )

    crawl_cli._authenticate_site(site, force=True)

    assert calls == [("auth", site, True)]


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


def test_main_reports_invalid_redirect_policy_as_configuration_error(monkeypatch, tmp_path, capsys):
    site = {
        "name": "Example Docs",
        "url": "https://example.test/docs",
        "index_file": str(tmp_path / "docs.db"),
        "crawl": {
            "start_url": "https://example.test/docs",
            "redirect_policy": "unexpected",
        },
    }

    monkeypatch.setattr(crawl_cli, "get_sites", lambda: [site])
    monkeypatch.setattr(sys, "argv", ["docmcp-crawl", "--site", "Example Docs"])
    monkeypatch.setitem(
        sys.modules,
        "playwright.async_api",
        types.SimpleNamespace(async_playwright=lambda: None),
    )

    with pytest.raises(SystemExit) as excinfo:
        crawl_cli.main()

    assert excinfo.value.code == 1
    err = capsys.readouterr().err
    assert "[docmcp-crawl] Configuration error:" in err
    assert "Invalid crawl.redirect_policy" in err


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


@pytest.mark.parametrize(
    ("redirect_policy", "expected_indexed_url", "expected_debug_line", "expect_skip"),
    [
        (
            None,
            "https://example.test/docs/guide",
            "Redirect policy=final -> indexing final URL https://example.test/docs/guide",
            False,
        ),
        (
            "final",
            "https://example.test/docs/guide",
            "Redirect policy=final -> indexing final URL https://example.test/docs/guide",
            False,
        ),
        (
            "requested",
            "https://example.test/docs",
            "Redirect policy=requested -> indexing requested URL https://example.test/docs",
            False,
        ),
        ("skip", None, "Redirect policy=skip -> skipping redirected page", True),
    ],
)
def test_crawl_site_headful_applies_redirect_policy_to_redirected_pages(
    monkeypatch,
    tmp_path,
    capsys,
    redirect_policy,
    expected_indexed_url,
    expected_debug_line,
    expect_skip,
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

    crawl_cfg = {
        "start_url": "https://example.test/docs",
        "max_depth": 0,
        "delay_seconds": 0,
    }
    if redirect_policy is not None:
        crawl_cfg["redirect_policy"] = redirect_policy

    site = {
        "name": "Example Docs",
        "url": "https://example.test/docs",
        "index_file": str(tmp_path / "docs.db"),
        "crawl": crawl_cfg,
    }

    asyncio.run(crawl_cli.crawl_site_headful(site, headless=True, debug=True))

    output = capsys.readouterr()
    assert "[crawl][debug] Navigating to https://example.test/docs" in output.err
    assert "[crawl][debug] Navigation redirected to https://example.test/docs/guide" in output.err
    assert f"[crawl][debug] {expected_debug_line}" in output.err
    if expect_skip:
        assert indexed == []
        assert "[crawl]   ↷ Skipped: redirect_policy=skip" in output.out
    else:
        assert indexed[0][:3] == (
            str(tmp_path / "docs.db"),
            expected_indexed_url,
            "Guide",
        )
        assert "Guide" in indexed[0][3]


@pytest.mark.parametrize("redirect_policy", ["final", "requested", "skip"])
def test_crawl_site_headful_non_redirected_pages_ignore_redirect_policy(
    monkeypatch, tmp_path, capsys, redirect_policy
):
    indexed = []

    class FakePage:
        def __init__(self):
            self.url = ""

        async def goto(self, url, wait_until, timeout):
            self.url = url

        async def title(self):
            return "Docs"

        async def content(self):
            return "<html><body><main><h1>Docs</h1></main></body></html>"

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
            "redirect_policy": redirect_policy,
        },
    }

    asyncio.run(crawl_cli.crawl_site_headful(site, headless=True, debug=True))

    output = capsys.readouterr()
    assert "[crawl][debug] Navigation stayed on https://example.test/docs" in output.err
    assert "Redirect policy=" not in output.err
    assert indexed[0][:3] == (
        str(tmp_path / "docs.db"),
        "https://example.test/docs",
        "Docs",
    )


def test_crawl_site_headful_preserves_query_start_url_and_indexes_query_links(
    monkeypatch, tmp_path, capsys
):
    indexed = []
    visited_urls = []

    class FakePage:
        def __init__(self):
            self.url = ""

        async def goto(self, url, wait_until, timeout):
            visited_urls.append(url)
            self.url = url

        async def title(self):
            return "Guide" if "tab=api" in self.url else "Docs"

        async def content(self):
            return "<html><body><main><h1>Guide</h1></main></body></html>"

        async def query_selector(self, selector):
            return None

        async def eval_on_selector_all(self, selector, script):
            if self.url.endswith("/docs?page=1"):
                return [{"href": "/docs/guide?tab=api"}]
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
            "start_url": "https://example.test/docs?page=1",
            "max_depth": 1,
            "delay_seconds": 0,
            "ignore_query_links": False,
        },
    }

    asyncio.run(crawl_cli.crawl_site_headful(site, headless=True, debug=True))

    output = capsys.readouterr()
    assert visited_urls == [
        "https://example.test/docs?page=1",
        "https://example.test/docs/guide?tab=api",
    ]
    assert "[crawl][debug] Navigating to https://example.test/docs?page=1" in output.err
    assert indexed[0][:3] == (
        str(tmp_path / "docs.db"),
        "https://example.test/docs?page=1",
        "Docs",
    )
    assert indexed[1][:3] == (
        str(tmp_path / "docs.db"),
        "https://example.test/docs/guide?tab=api",
        "Guide",
    )


def test_crawl_site_headful_keeps_query_anchor_links_as_current_page_targets(
    monkeypatch, tmp_path, capsys
):
    indexed = []
    visited_urls = []

    class FakePage:
        def __init__(self):
            self.url = ""

        async def goto(self, url, wait_until, timeout):
            visited_urls.append(url)
            self.url = url

        async def title(self):
            return "Docs"

        async def content(self):
            return "<html><body><main><h1>Docs</h1></main></body></html>"

        async def query_selector(self, selector):
            return None

        async def eval_on_selector_all(self, selector, script):
            return [
                {"href": "/docs?page=1#intro"},
                {"href": "/docs/other?tab=api"},
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
            "start_url": "https://example.test/docs?page=1",
            "max_depth": 1,
            "delay_seconds": 0,
            "ignore_query_links": True,
            "ignore_anchor_links": True,
        },
    }

    asyncio.run(crawl_cli.crawl_site_headful(site, headless=True, debug=True))

    output = capsys.readouterr()
    assert visited_urls == ["https://example.test/docs?page=1"]
    assert "[crawl][debug] Discovered 2 raw anchors, 1 normalized link target(s)" in output.err
    assert (
        "[crawl][debug] Discovered https://example.test/docs?page=1 -> skipped "
        "(anchor link points to the current page)" in output.err
    )
    assert indexed[0][:3] == (
        str(tmp_path / "docs.db"),
        "https://example.test/docs?page=1",
        "Docs",
    )


@pytest.mark.parametrize(
    "crawl_cfg, expected",
    [
        (
            {
                "start_url": "https://example.test/docs?page=1",
                "max_depth": 1,
                "delay_seconds": 0.25,
                "block_images": False,
                "ignore_query_links": False,
                "ignore_anchor_links": True,
                "ignore_https_errors": False,
            },
            {
                "visited_urls": [
                    "https://example.test/docs?page=1",
                    "https://example.test/docs/guide?tab=api",
                ],
                "indexed_urls": [
                    "https://example.test/docs?page=1",
                    "https://example.test/docs/guide?tab=api",
                ],
                "sleep_calls": [0.25, 0.25],
                "route_calls": [],
                "ignore_https_errors": False,
            },
        ),
        (
            {
                "start_url": "https://example.test/docs?page=1",
                "max_depth": 1,
                "delay_seconds": 0.25,
                "block_images": True,
                "ignore_query_links": False,
                "ignore_anchor_links": True,
                "ignore_https_errors": True,
            },
            {
                "visited_urls": [
                    "https://example.test/docs?page=1",
                    "https://example.test/docs/guide?tab=api",
                ],
                "indexed_urls": [
                    "https://example.test/docs?page=1",
                    "https://example.test/docs/guide?tab=api",
                ],
                "sleep_calls": [0.25, 0.25],
                "route_calls": ["**/*"],
                "ignore_https_errors": True,
            },
        ),
    ],
)
def test_crawl_site_headful_runtime_config_matrix(monkeypatch, tmp_path, crawl_cfg, expected):
    indexed = []
    visited_urls = []
    sleep_calls = []
    route_calls = []
    context_kwargs = {}

    class FakePage:
        def __init__(self):
            self.url = ""

        async def goto(self, url, wait_until, timeout):
            visited_urls.append(url)
            self.url = url

        async def title(self):
            return "Docs" if self.url.endswith("?page=1") else "Guide"

        async def content(self):
            return "<html><body><main><h1>Docs</h1></main></body></html>"

        async def query_selector(self, selector):
            return None

        async def eval_on_selector_all(self, selector, script):
            if self.url.endswith("?page=1"):
                return [
                    {"href": "/docs?page=1#intro"},
                    {"href": "/docs/guide?tab=api"},
                ]
            return []

    class FakeContext:
        async def route(self, pattern, handler):
            route_calls.append(pattern)

        async def new_page(self):
            return FakePage()

    class FakeBrowser:
        async def new_context(self, **kwargs):
            context_kwargs.update(kwargs)
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
        sleep_calls.append(delay)

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
        "crawl": crawl_cfg,
    }

    asyncio.run(crawl_cli.crawl_site_headful(site, headless=True, debug=False))

    assert context_kwargs["ignore_https_errors"] is expected["ignore_https_errors"]
    assert route_calls == expected["route_calls"]
    assert sleep_calls == expected["sleep_calls"]
    assert visited_urls == expected["visited_urls"]
    assert [row[1] for row in indexed] == expected["indexed_urls"]


def test_crawl_site_headful_start_delay_pauses_before_first_navigation(monkeypatch, tmp_path):
    events = []

    class FakePage:
        def __init__(self):
            self.url = ""

        async def goto(self, url, wait_until, timeout):
            events.append(("goto", url))
            self.url = url

        async def title(self):
            return "Docs"

        async def content(self):
            return "<html><body><main><h1>Docs</h1></main></body></html>"

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

    headless_flags = []

    class FakeChromium:
        async def launch(self, headless):
            headless_flags.append(headless)
            return FakeBrowser()

    class FakePlaywrightManager:
        async def __aenter__(self):
            return types.SimpleNamespace(chromium=FakeChromium())

        async def __aexit__(self, exc_type, exc, tb):
            return False

    async def fake_sleep(delay):
        events.append(("sleep", delay))

    def fake_upsert_page(index_file, url, title, content_md):
        events.append(("index", url))

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
            "start_delay_seconds": 0.5,
        },
    }

    asyncio.run(crawl_cli.crawl_site_headful(site, headless=False, debug=False))

    assert headless_flags == [False]
    assert events[:2] == [
        ("goto", "https://example.test/docs"),
        ("sleep", 0.5),
    ]
    assert events[2] == ("index", "https://example.test/docs")
