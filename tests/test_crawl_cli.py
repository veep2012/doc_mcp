import asyncio
import sqlite3
import sys
import types
from collections import deque

import pytest

import docmcp.crawl_cli as crawl_cli
from docmcp import __version__
from docmcp.config.playwright import BrowserUnavailableError
from docmcp.crawl_cli import (
    _disallowed_reason,
    _extract_links,
    _format_queue_preview,
    _load_selected_pages,
    _html_to_markdown,
    _is_allowed,
    _is_page_url,
    _link_discovery_decision,
    _normalize_url,
    _validate_selected_page_url,
    _get_redirect_policy,
)
from docmcp.index_store import get_page, init_db, upsert_page


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
    assert _is_page_url("https://example.test/docs/reference.pdf")
    assert not _is_page_url("https://example.test/static/logo.png")
    assert not _is_page_url("https://example.test/assets/site.css")


def test_pdf_detection_recognizes_url_and_content_type():
    assert crawl_cli._is_pdf_url("https://example.test/docs/reference.PDF?download=1")
    assert not crawl_cli._is_pdf_url("https://example.test/docs/guide")
    assert crawl_cli._is_pdf_content_type("application/pdf; charset=binary")
    assert not crawl_cli._is_pdf_content_type("text/html")


@pytest.mark.parametrize(
    ("ok", "status", "response_url", "content_type", "expected_message"),
    [
        (False, 503, "https://example.test/docs/reference.pdf", "application/pdf", "HTTP 503"),
        (True, 200, "https://example.test/docs/reference", "text/html", "not a PDF"),
    ],
)
def test_fetch_pdf_document_rejects_failed_or_non_pdf_responses(
    monkeypatch,
    ok,
    status,
    response_url,
    content_type,
    expected_message,
):
    class FakeResponse:
        url = response_url
        headers = {"content-type": content_type}

        async def body(self):
            return b"not used"

    FakeResponse.ok = ok
    FakeResponse.status = status

    class FakeRequest:
        async def get(self, url, timeout, **kwargs):
            assert url == "https://example.test/docs/reference.pdf"
            assert timeout == 60000
            assert kwargs == {"headers": {"Accept": "application/pdf"}}
            return FakeResponse()

    context = types.SimpleNamespace(request=FakeRequest())

    with pytest.raises(crawl_cli.PdfExtractionError, match=expected_message):
        asyncio.run(
            crawl_cli._fetch_pdf_document(context, "https://example.test/docs/reference.pdf")
        )


def test_fetch_pdf_document_accepts_content_type_only_and_preserves_query(monkeypatch):
    class FakeResponse:
        ok = True
        status = 200
        url = "https://example.test/docs/download?file=reference"
        headers = {"content-type": "application/pdf; charset=binary"}

        async def body(self):
            return b"%PDF"

    class FakeRequest:
        async def get(self, url, timeout, **kwargs):
            return FakeResponse()

    monkeypatch.setattr(
        crawl_cli,
        "_extract_pdf_document",
        lambda data: ("Reference PDF", "PDF-only content"),
    )
    context = types.SimpleNamespace(request=FakeRequest())

    assert asyncio.run(
        crawl_cli._fetch_pdf_document(context, "https://example.test/docs/download?file=reference")
    ) == (
        "https://example.test/docs/download?file=reference",
        "Reference PDF",
        "PDF-only content",
    )


def test_fetch_pdf_document_uses_proxy_and_authenticated_storage_state(monkeypatch):
    class FakeResponse:
        ok = True
        status = 200
        url = "https://private.example.test/reference.pdf"
        headers = {"content-type": "application/pdf"}

        async def body(self):
            return b"%PDF"

    class FakeRequestContext:
        disposed = False

        async def get(self, url, timeout, **kwargs):
            assert url == "https://private.example.test/reference.pdf"
            assert timeout == 60000
            assert kwargs == {"headers": {"Accept": "application/pdf"}}
            return FakeResponse()

        async def dispose(self):
            self.disposed = True

    class FakeRequestFactory:
        def __init__(self):
            self.context = FakeRequestContext()
            self.options = None

        async def new_context(self, **kwargs):
            self.options = kwargs
            return self.context

    request_factory = FakeRequestFactory()
    context = types.SimpleNamespace(
        request=None,
        storage_state=lambda: _storage_state(),
    )

    async def _storage_state():
        return {"cookies": [{"name": "session", "value": "redacted"}], "origins": []}

    monkeypatch.setattr(
        crawl_cli,
        "_extract_pdf_document",
        lambda data: ("Reference PDF", "PDF-only content"),
    )

    assert asyncio.run(
        crawl_cli._fetch_pdf_document(
            context,
            "https://private.example.test/reference.pdf",
            playwright=types.SimpleNamespace(request=request_factory),
            proxy={"server": "http://proxy.example.test:8080"},
        )
    ) == (
        "https://private.example.test/reference.pdf",
        "Reference PDF",
        "PDF-only content",
    )
    assert request_factory.options == {
        "storage_state": {"cookies": [{"name": "session", "value": "redacted"}], "origins": []},
        "proxy": {"server": "http://proxy.example.test:8080"},
    }
    assert request_factory.context.disposed


def test_fetch_pdf_document_wraps_request_errors_and_disposes_request_context():
    class FakeRequestContext:
        disposed = False

        async def get(self, *args, **kwargs):
            raise OSError("getaddrinfo ENOTFOUND private.example.test")

        async def dispose(self):
            self.disposed = True

    class FakeRequestFactory:
        def __init__(self):
            self.context = FakeRequestContext()

        async def new_context(self, **kwargs):
            return self.context

    request_factory = FakeRequestFactory()

    async def _storage_state():
        return {"cookies": [], "origins": []}

    context = types.SimpleNamespace(request=None, storage_state=_storage_state)
    with pytest.raises(crawl_cli.PdfExtractionError, match="PDF download failed: .*ENOTFOUND"):
        asyncio.run(
            crawl_cli._fetch_pdf_document(
                context,
                "https://private.example.test/reference.pdf",
                playwright=types.SimpleNamespace(request=request_factory),
            )
        )
    assert request_factory.context.disposed


@pytest.mark.parametrize(
    ("redirect_policy", "expected_url", "expected_debug"),
    [
        ("final", "https://example.test/docs/reference.pdf", "final"),
        ("requested", "https://example.test/docs/download", "requested"),
        ("skip", None, "skip"),
    ],
)
def test_index_pdf_document_applies_redirect_policy(
    monkeypatch, tmp_path, redirect_policy, expected_url, expected_debug
):
    indexed = []
    debug_lines = []

    async def fake_fetch(context, requested_url):
        assert requested_url == "https://example.test/docs/download"
        return "https://example.test/docs/reference.pdf", "Reference PDF", "PDF-only content"

    monkeypatch.setattr(crawl_cli, "_fetch_pdf_document", fake_fetch)
    monkeypatch.setattr(
        crawl_cli,
        "upsert_page",
        lambda index_file, url, title, content: indexed.append((index_file, url, title, content)),
    )

    result = asyncio.run(
        crawl_cli._index_pdf_document(
            types.SimpleNamespace(),
            requested_url="https://example.test/docs/download",
            index_file=str(tmp_path / "docs.db"),
            redirect_policy=redirect_policy,
            debug=debug_lines.append,
        )
    )

    assert result == (expected_url, "Reference PDF")
    if expected_url is None:
        assert indexed == []
        assert "skipping redirected PDF" in " ".join(debug_lines)
    else:
        assert indexed == [
            (str(tmp_path / "docs.db"), expected_url, "Reference PDF", "PDF-only content")
        ]
        assert any(f"indexing {expected_debug} URL {expected_url}" in line for line in debug_lines)


def test_extract_pdf_document_normalizes_text_and_uses_metadata_title(monkeypatch):
    class FakePage:
        def extract_text(self):
            return "  First page  "

    class FakeReader:
        metadata = types.SimpleNamespace(title=" Reference Guide ")
        pages = [FakePage()]
        is_encrypted = False

        def __init__(self, stream):
            assert stream.read() == b"%PDF"

    monkeypatch.setattr(crawl_cli, "HAS_PYPDF", True)
    monkeypatch.setattr(crawl_cli, "PdfReader", FakeReader)

    assert crawl_cli._extract_pdf_document(b"%PDF") == ("Reference Guide", "First page")


def test_extract_pdf_document_uses_no_title_for_whitespace_metadata(monkeypatch):
    class FakePage:
        def extract_text(self):
            return "Text"

    class FakeReader:
        metadata = types.SimpleNamespace(title="   ")
        pages = [FakePage()]
        is_encrypted = False

        def __init__(self, stream):
            pass

    monkeypatch.setattr(crawl_cli, "HAS_PYPDF", True)
    monkeypatch.setattr(crawl_cli, "PdfReader", FakeReader)

    assert crawl_cli._extract_pdf_document(b"%PDF") == (None, "Text")


def test_extract_pdf_document_uses_no_title_without_metadata(monkeypatch):
    class FakePage:
        def extract_text(self):
            return "Text"

    class FakeReader:
        metadata = None
        pages = [FakePage()]
        is_encrypted = False

        def __init__(self, stream):
            pass

    monkeypatch.setattr(crawl_cli, "HAS_PYPDF", True)
    monkeypatch.setattr(crawl_cli, "PdfReader", FakeReader)

    assert crawl_cli._extract_pdf_document(b"%PDF") == (None, "Text")


def test_extract_pdf_document_reports_encrypted_pdf(monkeypatch):
    class FakeReader:
        is_encrypted = True

        def __init__(self, stream):
            pass

    monkeypatch.setattr(crawl_cli, "HAS_PYPDF", True)
    monkeypatch.setattr(crawl_cli, "PdfReader", FakeReader)

    with pytest.raises(crawl_cli.PdfExtractionError, match="requires a password"):
        crawl_cli._extract_pdf_document(b"%PDF")


@pytest.mark.parametrize(
    "parser_state, expected_message",
    [
        (None, "PDF support requires pypdf. Install it with: pip install pypdf"),
        (RuntimeError("broken PDF"), "unable to read PDF: broken PDF"),
    ],
)
def test_extract_pdf_document_reports_missing_or_unreadable_parser(
    monkeypatch, parser_state, expected_message
):
    monkeypatch.setattr(crawl_cli, "HAS_PYPDF", parser_state is not None)
    if parser_state is not None:

        def fail_to_read(stream):
            raise parser_state

        monkeypatch.setattr(crawl_cli, "PdfReader", fail_to_read)

    with pytest.raises(crawl_cli.PdfExtractionError, match=expected_message):
        crawl_cli._extract_pdf_document(b"not a PDF")


def test_extract_pdf_document_rejects_empty_text(monkeypatch):
    class FakePage:
        def extract_text(self):
            return ""

    class FakeReader:
        metadata = None
        pages = [FakePage()]
        is_encrypted = False

        def __init__(self, stream):
            pass

    monkeypatch.setattr(crawl_cli, "HAS_PYPDF", True)
    monkeypatch.setattr(crawl_cli, "PdfReader", FakeReader)

    with pytest.raises(crawl_cli.PdfExtractionError, match="PDF contains no extractable text"):
        crawl_cli._extract_pdf_document(b"%PDF")


def test_get_redirect_policy_normalizes_case_and_whitespace():
    assert _get_redirect_policy({"redirect_policy": "  FINAL  "}) == "final"
    assert _get_redirect_policy({"redirect_policy": "Requested"}) == "requested"


def test_get_redirect_policy_rejects_non_string_values_with_site_context():
    with pytest.raises(
        crawl_cli.ConfigError,
        match=r"Invalid crawl\.redirect_policy for site 'Example Docs': received 123; expected one of final, requested, skip",
    ):
        _get_redirect_policy({"redirect_policy": 123}, "Example Docs")


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


def test_validate_selected_page_url_rejects_external_and_static_assets():
    start_url = "https://example.test/docs"
    allow_patterns = ["https://example.test/docs/*"]
    deny_patterns = ["https://example.test/docs/private/*"]

    assert _validate_selected_page_url(
        "https://example.test/docs/guide#intro",
        start_url,
        allow_patterns,
        deny_patterns,
    ) == ("https://example.test/docs/guide", None, None)
    assert _validate_selected_page_url(
        "https://example.test/docs/reference.pdf",
        start_url,
        allow_patterns,
        deny_patterns,
    ) == ("https://example.test/docs/reference.pdf", None, None)
    assert _validate_selected_page_url(
        "https://other.test/docs/guide",
        start_url,
        allow_patterns,
        deny_patterns,
    ) == (None, "out_of_scope", "host 'other.test' is outside start host 'example.test'")
    assert _validate_selected_page_url(
        "https://example.test/docs/static/logo.png",
        start_url,
        allow_patterns,
        deny_patterns,
    ) == (None, "asset_url", "URL points to a non-page asset")


def test_load_selected_pages_normalizes_and_merges_cli_and_file_entries(tmp_path):
    pages_file = tmp_path / "pages.txt"
    pages_file.write_text(
        "# ignore comments\n https://example.test/docs/api/#intro \n\nhttps://example.test/docs/install/\n",
        encoding="utf-8",
    )

    assert _load_selected_pages(
        [" https://example.test/docs/guide/#details "],
        str(pages_file),
    ) == [
        "https://example.test/docs/guide",
        "https://example.test/docs/api",
        "https://example.test/docs/install",
    ]


def test_load_selected_pages_deduplicates_equivalent_cli_and_file_entries(tmp_path):
    pages_file = tmp_path / "pages.txt"
    pages_file.write_text(
        "https://example.test/docs/api/\nhttps://example.test/docs/api#fragment\n",
        encoding="utf-8",
    )

    assert _load_selected_pages(
        ["https://example.test/docs/api#top", "https://example.test/docs/api/"],
        str(pages_file),
    ) == [
        "https://example.test/docs/api",
    ]


def test_load_selected_pages_returns_empty_list_for_empty_or_comment_only_file(tmp_path):
    pages_file = tmp_path / "pages.txt"
    pages_file.write_text("# ignore comments\n\n   \n", encoding="utf-8")

    assert _load_selected_pages([], str(pages_file)) == []


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


@pytest.mark.parametrize(
    ("argv", "expected_pages"),
    [
        (
            [
                "docmcp-crawl",
                "--site",
                "Example Docs",
                "--pages",
                "https://example.test/docs/guide",
                "https://example.test/docs/api",
            ],
            [
                "https://example.test/docs/guide",
                "https://example.test/docs/api",
            ],
        ),
        (
            None,
            [
                "https://example.test/docs/guide",
                "https://example.test/docs/api",
            ],
        ),
    ],
)
def test_main_routes_targeted_reindex_inputs_to_selected_pages(
    monkeypatch, tmp_path, argv, expected_pages
):
    site = {"name": "Example Docs", "url": "https://example.test", "auth_required": False}
    captured = {}
    pages_file = tmp_path / "pages.txt"
    pages_file.write_text(
        "https://example.test/docs/guide\nhttps://example.test/docs/api\n",
        encoding="utf-8",
    )
    if argv is None:
        argv = [
            "docmcp-crawl",
            "--site",
            "Example Docs",
            "--pages-file",
            str(pages_file),
        ]

    async def fake_reindex(arg_site, page_urls, headless=False, debug=False):
        captured["site"] = arg_site
        captured["page_urls"] = page_urls
        captured["headless"] = headless
        captured["debug"] = debug
        return [{"url": page_urls[0], "outcome": "indexed"}]

    async def fail_crawl(*args, **kwargs):
        raise AssertionError("full crawl should not run for targeted reindex inputs")

    monkeypatch.setattr(crawl_cli, "get_sites", lambda: [site])
    monkeypatch.setattr(crawl_cli, "reindex_selected_pages", fake_reindex)
    monkeypatch.setattr(crawl_cli, "crawl_site_headful", fail_crawl)
    monkeypatch.setattr(sys, "argv", argv)

    crawl_cli.main()

    assert captured == {
        "site": site,
        "page_urls": expected_pages,
        "headless": False,
        "debug": False,
    }


def test_main_normalizes_and_deduplicates_targeted_reindex_inputs(monkeypatch, tmp_path):
    site = {"name": "Example Docs", "url": "https://example.test", "auth_required": False}
    captured = {}
    pages_file = tmp_path / "pages.txt"
    pages_file.write_text(
        "https://example.test/docs/api/#fragment\nhttps://example.test/docs/guide/\n",
        encoding="utf-8",
    )

    async def fake_reindex(arg_site, page_urls, headless=False, debug=False):
        captured["site"] = arg_site
        captured["page_urls"] = page_urls
        captured["headless"] = headless
        captured["debug"] = debug
        return [{"url": page_urls[0], "outcome": "indexed"}]

    async def fail_crawl(*args, **kwargs):
        raise AssertionError("full crawl should not run for targeted reindex inputs")

    monkeypatch.setattr(crawl_cli, "get_sites", lambda: [site])
    monkeypatch.setattr(crawl_cli, "reindex_selected_pages", fake_reindex)
    monkeypatch.setattr(crawl_cli, "crawl_site_headful", fail_crawl)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "docmcp-crawl",
            "--site",
            "Example Docs",
            "--pages",
            " https://example.test/docs/guide#top ",
            "https://example.test/docs/api",
            "https://example.test/docs/api/",
            "--pages-file",
            str(pages_file),
        ],
    )

    crawl_cli.main()

    assert captured == {
        "site": site,
        "page_urls": [
            "https://example.test/docs/guide",
            "https://example.test/docs/api",
        ],
        "headless": False,
        "debug": False,
    }


def test_main_warns_when_targeted_batch_is_large(monkeypatch, tmp_path, capsys):
    site = {"name": "Example Docs", "url": "https://example.test", "auth_required": False}
    captured = {}
    pages_file = tmp_path / "pages.txt"
    pages_file.write_text(
        "\n".join(f"https://example.test/docs/page-{index}" for index in range(1, 4)) + "\n",
        encoding="utf-8",
    )

    async def fake_reindex(arg_site, page_urls, headless=False, debug=False):
        captured["site"] = arg_site
        captured["page_urls"] = page_urls
        captured["headless"] = headless
        captured["debug"] = debug
        return [{"url": page_urls[0], "outcome": "indexed"}]

    async def fail_crawl(*args, **kwargs):
        raise AssertionError("full crawl should not run for targeted reindex inputs")

    monkeypatch.setattr(crawl_cli, "_TARGETED_REINDEX_WARN_THRESHOLD", 3)
    monkeypatch.setattr(crawl_cli, "_TARGETED_REINDEX_HARD_CAP", 10)
    monkeypatch.setattr(crawl_cli, "get_sites", lambda: [site])
    monkeypatch.setattr(crawl_cli, "reindex_selected_pages", fake_reindex)
    monkeypatch.setattr(crawl_cli, "crawl_site_headful", fail_crawl)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "docmcp-crawl",
            "--site",
            "Example Docs",
            "--pages-file",
            str(pages_file),
        ],
    )

    crawl_cli.main()

    assert captured["page_urls"] == [
        "https://example.test/docs/page-1",
        "https://example.test/docs/page-2",
        "https://example.test/docs/page-3",
    ]
    assert "[docmcp-crawl] Warning: targeted reindex contains 3 pages." in capsys.readouterr().err


def test_main_refuses_targeted_batches_over_hard_cap(monkeypatch, tmp_path, capsys):
    site = {"name": "Example Docs", "url": "https://example.test", "auth_required": False}
    pages_file = tmp_path / "pages.txt"
    pages_file.write_text(
        "\n".join(f"https://example.test/docs/page-{index}" for index in range(1, 5)) + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(crawl_cli, "_TARGETED_REINDEX_WARN_THRESHOLD", 3)
    monkeypatch.setattr(crawl_cli, "_TARGETED_REINDEX_HARD_CAP", 3)
    monkeypatch.setattr(crawl_cli, "get_sites", lambda: [site])
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "docmcp-crawl",
            "--site",
            "Example Docs",
            "--pages-file",
            str(pages_file),
        ],
    )

    with pytest.raises(SystemExit) as excinfo:
        crawl_cli.main()

    assert excinfo.value.code == 1
    assert "Refusing targeted reindex with 4 pages" in capsys.readouterr().err


def test_main_exits_when_pages_file_cannot_be_read(monkeypatch, capsys):
    site = {"name": "Example Docs", "url": "https://example.test", "auth_required": False}

    monkeypatch.setattr(crawl_cli, "get_sites", lambda: [site])
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "docmcp-crawl",
            "--site",
            "Example Docs",
            "--pages-file",
            "/tmp/does-not-exist-pages.txt",
        ],
    )

    with pytest.raises(SystemExit) as excinfo:
        crawl_cli.main()

    assert excinfo.value.code == 1
    assert "[docmcp-crawl] Failed to read --pages-file:" in capsys.readouterr().err


def test_main_exits_when_pages_file_is_not_utf8(monkeypatch, tmp_path, capsys):
    site = {"name": "Example Docs", "url": "https://example.test", "auth_required": False}
    pages_file = tmp_path / "pages.txt"
    pages_file.write_bytes(b"\xff\xfe\xfa")

    monkeypatch.setattr(crawl_cli, "get_sites", lambda: [site])
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "docmcp-crawl",
            "--site",
            "Example Docs",
            "--pages-file",
            str(pages_file),
        ],
    )

    with pytest.raises(SystemExit) as excinfo:
        crawl_cli.main()

    assert excinfo.value.code == 1
    assert "[docmcp-crawl] Failed to read --pages-file:" in capsys.readouterr().err


def test_main_vectorizes_after_successful_crawl_when_requested(monkeypatch, capsys):
    site = {
        "name": "Example Docs",
        "url": "https://example.test",
        "auth_required": False,
        "index_file": "index/docs.db",
    }
    calls = []

    async def fake_crawl(arg_site, headless=False, debug=False):
        calls.append(("crawl", arg_site, headless, debug))
        return True

    def fake_vectorize(arg_site, debug=False):
        calls.append(("vectorize", arg_site, debug))

    monkeypatch.setattr(crawl_cli, "get_sites", lambda: [site])
    monkeypatch.setattr(crawl_cli, "crawl_site_headful", fake_crawl)
    monkeypatch.setattr(crawl_cli, "rebuild_vector_index", fake_vectorize)
    monkeypatch.setattr(
        sys,
        "argv",
        ["docmcp-crawl", "--site", "Example Docs", "--vectorize"],
    )

    crawl_cli.main()

    output = capsys.readouterr()
    assert calls == [
        ("crawl", site, False, False),
        ("vectorize", site, False),
    ]
    assert "[crawl] Vectorize : enabled" in output.out


def test_main_skips_vectorize_when_crawl_does_not_complete(monkeypatch, capsys):
    site = {
        "name": "Example Docs",
        "url": "https://example.test",
        "auth_required": False,
        "index_file": "index/docs.db",
    }
    calls = []

    async def fake_crawl(arg_site, headless=False, debug=False):
        calls.append(("crawl", arg_site, headless, debug))
        return False

    def fake_vectorize(arg_site, debug=False):
        calls.append(("vectorize", arg_site, debug))
        raise AssertionError("vectorize should not run when the crawl does not complete")

    monkeypatch.setattr(crawl_cli, "get_sites", lambda: [site])
    monkeypatch.setattr(crawl_cli, "crawl_site_headful", fake_crawl)
    monkeypatch.setattr(crawl_cli, "rebuild_vector_index", fake_vectorize)
    monkeypatch.setattr(
        sys,
        "argv",
        ["docmcp-crawl", "--site", "Example Docs", "--vectorize"],
    )

    crawl_cli.main()

    output = capsys.readouterr()
    assert calls == [
        ("crawl", site, False, False),
    ]
    assert "[crawl] Skipping vectorize: crawl did not complete successfully" in output.out


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


def test_main_authenticates_and_vectorizes_after_successful_crawl(monkeypatch, capsys):
    site = {
        "name": "Example Docs",
        "url": "https://example.test",
        "auth_required": True,
        "index_file": "index/docs.db",
    }
    calls = []

    def fake_authenticate(arg_site, force=False):
        calls.append(("auth", arg_site, force))

    async def fake_crawl(arg_site, headless=False, debug=False):
        calls.append(("crawl", arg_site, headless, debug))
        return True

    def fake_vectorize(arg_site, debug=False):
        calls.append(("vectorize", arg_site, debug))

    monkeypatch.setattr(crawl_cli, "get_sites", lambda: [site])
    monkeypatch.setattr(crawl_cli, "_authenticate_site", fake_authenticate)
    monkeypatch.setattr(crawl_cli, "crawl_site_headful", fake_crawl)
    monkeypatch.setattr(crawl_cli, "rebuild_vector_index", fake_vectorize)
    monkeypatch.setattr(
        sys,
        "argv",
        ["docmcp-crawl", "--site", "Example Docs", "--vectorize"],
    )

    crawl_cli.main()

    output = capsys.readouterr()
    assert calls == [
        ("auth", site, False),
        ("crawl", site, False, False),
        ("vectorize", site, False),
    ]
    assert "[crawl] Vectorize : enabled" in output.out


def test_main_threads_debug_to_vectorize_when_requested(monkeypatch):
    site = {
        "name": "Example Docs",
        "url": "https://example.test",
        "auth_required": False,
        "index_file": "index/docs.db",
    }
    calls = []

    async def fake_crawl(arg_site, headless=False, debug=False):
        calls.append(("crawl", arg_site, headless, debug))
        return True

    def fake_vectorize(arg_site, debug=False):
        calls.append(("vectorize", arg_site, debug))

    monkeypatch.setattr(crawl_cli, "get_sites", lambda: [site])
    monkeypatch.setattr(crawl_cli, "crawl_site_headful", fake_crawl)
    monkeypatch.setattr(crawl_cli, "rebuild_vector_index", fake_vectorize)
    monkeypatch.setattr(
        sys,
        "argv",
        ["docmcp-crawl", "--site", "Example Docs", "--debug", "--vectorize"],
    )

    crawl_cli.main()

    assert calls == [
        ("crawl", site, False, True),
        ("vectorize", site, True),
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
    assert "Invalid crawl.redirect_policy for site 'Example Docs'" in err


def test_main_reports_missing_browser_during_crawl(monkeypatch, tmp_path, capsys):
    site = {
        "name": "Example Docs",
        "url": "https://example.test/docs",
        "auth_required": False,
        "index_file": str(tmp_path / "docs.db"),
    }

    monkeypatch.setattr(crawl_cli, "get_sites", lambda: [site])
    monkeypatch.setattr(sys, "argv", ["docmcp-crawl", "--site", "Example Docs"])

    async def fail_crawl(*args, **kwargs):
        raise BrowserUnavailableError(
            "Playwright browser 'webkit' is not installed.\n"
            "Install it with:\n"
            "  python -m playwright install webkit"
        )

    monkeypatch.setattr(crawl_cli, "crawl_site_headful", fail_crawl)

    with pytest.raises(SystemExit) as excinfo:
        crawl_cli.main()

    assert excinfo.value.code == 1
    assert capsys.readouterr().err == (
        "[docmcp-crawl] Browser error:\n"
        "Playwright browser 'webkit' is not installed.\n"
        "Install it with:\n"
        "  python -m playwright install webkit\n"
    )


@pytest.mark.parametrize("start_delay_seconds", ["1", -0.1, float("inf"), float("nan"), True])
def test_crawl_site_headful_rejects_invalid_start_delay_seconds(tmp_path, start_delay_seconds):
    site = {
        "name": "Example Docs",
        "url": "https://example.test/docs",
        "index_file": str(tmp_path / "docs.db"),
        "crawl": {
            "start_url": "https://example.test/docs",
            "start_delay_seconds": start_delay_seconds,
        },
    }

    with pytest.raises(
        crawl_cli.ConfigError,
        match=r"Invalid crawl\.start_delay_seconds.*expected a finite number >= 0",
    ):
        asyncio.run(crawl_cli.crawl_site_headful(site, headless=True))


@pytest.mark.parametrize("delay_seconds", ["1", -0.1, float("inf"), float("nan"), True])
def test_crawl_site_headful_rejects_invalid_delay_seconds(tmp_path, delay_seconds):
    site = {
        "name": "Example Docs",
        "url": "https://example.test/docs",
        "index_file": str(tmp_path / "docs.db"),
        "crawl": {
            "start_url": "https://example.test/docs",
            "delay_seconds": delay_seconds,
        },
    }

    with pytest.raises(
        crawl_cli.ConfigError,
        match=r"Invalid crawl\.delay_seconds.*expected a finite number >= 0",
    ):
        asyncio.run(crawl_cli.crawl_site_headful(site, headless=True))


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


def test_crawl_site_headful_indexes_linked_pdf(monkeypatch, tmp_path):
    class FakeResponse:
        url = "https://example.test/docs/reference.pdf"
        ok = True
        status = 200
        headers = {"content-type": "application/pdf"}

        async def body(self):
            return b"%PDF"

    class FakeRequest:
        async def get(self, url, timeout, **kwargs):
            assert url == "https://example.test/docs/reference.pdf"
            assert timeout == 60000
            return FakeResponse()

    class FakePage:
        url = ""

        async def goto(self, url, wait_until, timeout):
            self.url = url

        async def title(self):
            return "Docs"

        async def content(self):
            return "<main><a href='/docs/reference.pdf'>Reference</a></main>"

        async def query_selector(self, selector):
            return None

        async def eval_on_selector_all(self, selector, script):
            return [{"href": "/docs/reference.pdf"}]

    class FakeContext:
        request = FakeRequest()

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
    monkeypatch.setattr(
        crawl_cli, "_extract_pdf_document", lambda data: ("Reference PDF", "PDF-only content")
    )
    index_file = tmp_path / "docs.db"
    site = {
        "name": "Example Docs",
        "url": "https://example.test/docs",
        "index_file": str(index_file),
        "crawl": {"start_url": "https://example.test/docs", "max_depth": 1, "delay_seconds": 0},
    }

    assert asyncio.run(crawl_cli.crawl_site_headful(site, headless=True))
    indexed_pdf = get_page(str(index_file), "https://example.test/docs/reference.pdf")
    assert indexed_pdf["title"] == "Reference PDF"
    assert indexed_pdf["content_md"] == "PDF-only content"


def test_crawl_site_headful_indexes_pdf_detected_by_content_type(monkeypatch, tmp_path):
    class FakeResponse:
        url = "https://example.test/docs/download"
        ok = True
        status = 200
        headers = {"content-type": "application/pdf"}

        async def body(self):
            return b"%PDF"

    class FakeRequest:
        async def get(self, url, timeout, **kwargs):
            assert url == "https://example.test/docs/download"
            return FakeResponse()

    class FakePage:
        url = ""

        async def goto(self, url, wait_until, timeout):
            self.url = url
            if url.endswith("/download"):
                return FakeResponse()
            return types.SimpleNamespace(
                url=url,
                headers={"content-type": "text/html"},
            )

        async def title(self):
            return "Docs"

        async def content(self):
            return "<main>PDF download</main>"

        async def query_selector(self, selector):
            return None

        async def eval_on_selector_all(self, selector, script):
            return [{"href": "/docs/download"}]

    class FakeContext:
        request = FakeRequest()

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
    monkeypatch.setattr(
        crawl_cli, "_extract_pdf_document", lambda data: ("Download PDF", "PDF-only content")
    )
    index_file = tmp_path / "docs.db"
    site = {
        "name": "Example Docs",
        "url": "https://example.test/docs",
        "index_file": str(index_file),
        "crawl": {"start_url": "https://example.test/docs", "max_depth": 1, "delay_seconds": 0},
    }

    assert asyncio.run(crawl_cli.crawl_site_headful(site, headless=True))
    indexed_pdf = get_page(str(index_file), "https://example.test/docs/download")
    assert indexed_pdf["title"] == "Download PDF"
    assert indexed_pdf["content_md"] == "PDF-only content"


def test_crawl_site_headful_continues_after_pdf_extraction_failure(monkeypatch, tmp_path):
    class FakePage:
        url = ""

        async def goto(self, url, wait_until, timeout):
            self.url = url
            return types.SimpleNamespace(
                url=url,
                headers={"content-type": "text/html"},
            )

        async def title(self):
            return "Guide"

        async def content(self):
            if self.url.endswith("/docs"):
                return "<main>Start</main>"
            return "<main>Guide content</main>"

        async def query_selector(self, selector):
            return None

        async def eval_on_selector_all(self, selector, script):
            if self.url.endswith("/docs"):
                return [
                    {"href": "/docs/reference.pdf"},
                    {"href": "/docs/guide"},
                ]
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

    async def fail_index(*args, **kwargs):
        raise crawl_cli.PdfExtractionError("PDF contains no extractable text")

    indexed = []
    monkeypatch.setitem(
        sys.modules,
        "playwright.async_api",
        types.SimpleNamespace(async_playwright=lambda: FakePlaywrightManager()),
    )
    monkeypatch.setattr(crawl_cli.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(crawl_cli, "_index_pdf_document", fail_index)
    monkeypatch.setattr(
        crawl_cli,
        "upsert_page",
        lambda index_file, url, title, content: indexed.append((url, title, content)),
    )
    site = {
        "name": "Example Docs",
        "url": "https://example.test/docs",
        "index_file": str(tmp_path / "docs.db"),
        "crawl": {"start_url": "https://example.test/docs", "max_depth": 1, "delay_seconds": 0},
    }

    assert asyncio.run(crawl_cli.crawl_site_headful(site, headless=True))
    assert indexed == [
        ("https://example.test/docs", "Guide", "Start"),
        ("https://example.test/docs/guide", "Guide", "Guide content"),
    ]


def test_reindex_selected_pages_indexes_targeted_pdf(monkeypatch, tmp_path):
    class FakeResponse:
        url = "https://example.test/docs/reference.pdf"
        ok = True
        status = 200
        headers = {"content-type": "application/pdf"}

        async def body(self):
            return b"%PDF"

    class FakeRequest:
        async def get(self, url, timeout, **kwargs):
            return FakeResponse()

    class FakeContext:
        request = FakeRequest()

        async def new_page(self):
            return types.SimpleNamespace()

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
    monkeypatch.setattr(
        crawl_cli, "_extract_pdf_document", lambda data: ("Reference PDF", "PDF-only content")
    )
    index_file = tmp_path / "docs.db"
    site = {
        "name": "Example Docs",
        "url": "https://example.test/docs",
        "index_file": str(index_file),
        "crawl": {"start_url": "https://example.test/docs", "delay_seconds": 0},
    }

    results = asyncio.run(
        crawl_cli.reindex_selected_pages(
            site, ["https://example.test/docs/reference.pdf"], headless=True
        )
    )

    assert results == [
        {
            "url": "https://example.test/docs/reference.pdf",
            "requested_url": "https://example.test/docs/reference.pdf",
            "outcome": "indexed",
            "title": "Reference PDF",
        }
    ]
    assert get_page(str(index_file), "https://example.test/docs/reference.pdf")["content_md"] == (
        "PDF-only content"
    )


def test_reindex_selected_pages_reports_pdf_extraction_failure_and_continues(
    monkeypatch, tmp_path, capsys
):
    class FakeResponse:
        url = "https://example.test/docs/broken.pdf"
        ok = True
        status = 200
        headers = {"content-type": "application/pdf"}

        async def body(self):
            return b"%PDF"

    class FakeRequest:
        async def get(self, url, timeout, **kwargs):
            return FakeResponse()

    class FakeContext:
        request = FakeRequest()

        async def new_page(self):
            return types.SimpleNamespace()

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

    async def fail_index(*args, **kwargs):
        raise crawl_cli.PdfExtractionError("PDF contains no extractable text")

    monkeypatch.setattr(crawl_cli, "_index_pdf_document", fail_index)
    index_file = tmp_path / "docs.db"
    site = {
        "name": "Example Docs",
        "url": "https://example.test/docs",
        "index_file": str(index_file),
        "crawl": {"start_url": "https://example.test/docs", "delay_seconds": 0},
    }

    results = asyncio.run(
        crawl_cli.reindex_selected_pages(
            site, ["https://example.test/docs/broken.pdf"], headless=True
        )
    )

    assert results == [
        {
            "url": "https://example.test/docs/broken.pdf",
            "outcome": "failed",
            "reason_code": "pdf_error",
            "reason": "PDF extraction error: PDF contains no extractable text",
        }
    ]
    assert "Targeted reindex summary: indexed=0 skipped=0 failed=1" in capsys.readouterr().out


def test_reindex_selected_pages_indexes_pdf_detected_by_content_type(monkeypatch, tmp_path):
    class FakeResponse:
        url = "https://example.test/docs/download"
        ok = True
        status = 200
        headers = {"content-type": "application/pdf"}

        async def body(self):
            return b"%PDF"

    class FakeRequest:
        async def get(self, url, timeout, **kwargs):
            assert url == "https://example.test/docs/download"
            return FakeResponse()

    class FakePage:
        url = ""

        async def goto(self, url, wait_until, timeout):
            self.url = url
            return FakeResponse()

    class FakeContext:
        request = FakeRequest()

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
    monkeypatch.setattr(
        crawl_cli, "_extract_pdf_document", lambda data: ("Download PDF", "PDF-only content")
    )
    index_file = tmp_path / "docs.db"
    site = {
        "name": "Example Docs",
        "url": "https://example.test/docs",
        "index_file": str(index_file),
        "crawl": {"start_url": "https://example.test/docs", "delay_seconds": 0},
    }

    results = asyncio.run(
        crawl_cli.reindex_selected_pages(
            site, ["https://example.test/docs/download"], headless=True
        )
    )

    assert results == [
        {
            "url": "https://example.test/docs/download",
            "requested_url": "https://example.test/docs/download",
            "outcome": "indexed",
            "title": "Download PDF",
        }
    ]
    assert get_page(str(index_file), "https://example.test/docs/download")["content_md"] == (
        "PDF-only content"
    )


def test_reindex_selected_pages_updates_only_selected_rows(monkeypatch, tmp_path, capsys):
    class FakePage:
        def __init__(self):
            self.current = {}
            self.url = ""

        async def goto(self, url, wait_until, timeout):
            self.current = {
                "title": "Guide Updated",
                "html": "<html><body><main><h1>Guide Updated</h1><p>Fresh content.</p></main></body></html>",
                "url": url,
            }
            self.url = url

        async def title(self):
            return self.current["title"]

        async def content(self):
            return self.current["html"]

        async def query_selector(self, selector):
            return None

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

    index_file = tmp_path / "docs.db"
    init_db(str(index_file))
    upsert_page(str(index_file), "https://example.test/docs/guide", "Guide", "Old guide content")
    upsert_page(
        str(index_file),
        "https://example.test/docs/unchanged",
        "Unchanged",
        "Leave me alone",
    )
    original_other_page = get_page(str(index_file), "https://example.test/docs/unchanged")

    site = {
        "name": "Example Docs",
        "url": "https://example.test/docs",
        "index_file": str(index_file),
        "crawl": {
            "start_url": "https://example.test/docs",
            "delay_seconds": 0,
        },
    }

    results = asyncio.run(
        crawl_cli.reindex_selected_pages(
            site,
            ["https://example.test/docs/guide"],
            headless=True,
        )
    )

    output = capsys.readouterr().out
    updated_page = get_page(str(index_file), "https://example.test/docs/guide")
    other_page = get_page(str(index_file), "https://example.test/docs/unchanged")

    assert results == [
        {
            "url": "https://example.test/docs/guide",
            "requested_url": "https://example.test/docs/guide",
            "outcome": "indexed",
            "title": "Guide Updated",
        }
    ]
    assert updated_page is not None
    assert updated_page["title"] == "Guide Updated"
    assert "Fresh content" in updated_page["content_md"]
    assert other_page == original_other_page
    assert "[crawl] Targeted reindex summary: indexed=1 skipped=0 failed=0" in output


def test_reindex_selected_pages_reports_mixed_indexed_skipped_and_failed_results(
    monkeypatch, tmp_path, capsys
):
    page_payloads = {
        "https://example.test/docs/guide": {
            "title": "Guide Updated",
            "html": "<html><body><main><h1>Guide Updated</h1></main></body></html>",
            "url": "https://example.test/docs/guide",
        },
        "https://example.test/docs/api": {
            "title": "API Updated",
            "html": "<html><body><main><h1>API Updated</h1></main></body></html>",
            "url": "https://example.test/docs/api",
        },
    }

    class FakePage:
        def __init__(self):
            self.current = {}
            self.url = ""

        async def goto(self, url, wait_until, timeout):
            if url == "https://example.test/docs/failing":
                raise RuntimeError("boom")
            self.current = page_payloads[url]
            self.url = self.current["url"]

        async def title(self):
            return self.current["title"]

        async def content(self):
            return self.current["html"]

        async def query_selector(self, selector):
            return None

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

    index_file = tmp_path / "docs.db"
    init_db(str(index_file))
    upsert_page(str(index_file), "https://example.test/docs/guide", "Guide", "Old guide content")
    upsert_page(str(index_file), "https://example.test/docs/api", "API", "Old api content")

    site = {
        "name": "Example Docs",
        "url": "https://example.test/docs",
        "index_file": str(index_file),
        "crawl": {
            "start_url": "https://example.test/docs",
            "delay_seconds": 0,
            "allow_patterns": ["https://example.test/docs/*"],
        },
    }

    results = asyncio.run(
        crawl_cli.reindex_selected_pages(
            site,
            [
                "https://example.test/docs/guide",
                "https://other.test/docs/offsite",
                "https://example.test/docs/static/logo.png",
                "https://example.test/docs/api",
                "https://example.test/docs/failing",
            ],
            headless=True,
        )
    )

    output = capsys.readouterr().out

    assert [item["outcome"] for item in results] == [
        "indexed",
        "skipped",
        "skipped",
        "indexed",
        "failed",
    ]
    assert results[1]["reason_code"] == "out_of_scope"
    assert results[1]["reason"] == "host 'other.test' is outside start host 'example.test'"
    assert results[2]["reason_code"] == "asset_url"
    assert results[2]["reason"] == "URL points to a non-page asset"
    assert results[4]["reason_code"] == "navigation_error"
    assert results[4]["reason"] == "navigation error: boom"
    assert get_page(str(index_file), "https://example.test/docs/guide")["title"] == "Guide Updated"
    assert get_page(str(index_file), "https://example.test/docs/api")["title"] == "API Updated"
    assert "[crawl] Targeted reindex summary: indexed=2 skipped=2 failed=1" in output
    assert (
        "[crawl] Targeted reindex reasons: asset_url=1 navigation_error=1 out_of_scope=1" in output
    )


def test_reindex_selected_pages_classifies_parse_and_db_failures(monkeypatch, tmp_path, capsys):
    class FakePage:
        def __init__(self):
            self.current = {}
            self.url = ""

        async def goto(self, url, wait_until, timeout):
            self.current = {
                "title": f"Page for {url}",
                "html": "<html><body><main><h1>Loaded</h1></main></body></html>",
                "url": url,
            }
            self.url = url

        async def title(self):
            if self.url.endswith("/parse-failure"):
                raise RuntimeError("bad title")
            return self.current["title"]

        async def content(self):
            return self.current["html"]

        async def query_selector(self, selector):
            return None

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
        if url.endswith("/db-failure"):
            raise sqlite3.OperationalError("disk I/O error")

    monkeypatch.setitem(
        sys.modules,
        "playwright.async_api",
        types.SimpleNamespace(async_playwright=lambda: FakePlaywrightManager()),
    )
    monkeypatch.setattr(crawl_cli.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(crawl_cli, "upsert_page", fake_upsert_page)

    index_file = tmp_path / "docs.db"
    init_db(str(index_file))

    site = {
        "name": "Example Docs",
        "url": "https://example.test/docs",
        "index_file": str(index_file),
        "crawl": {
            "start_url": "https://example.test/docs",
            "delay_seconds": 0,
        },
    }

    results = asyncio.run(
        crawl_cli.reindex_selected_pages(
            site,
            [
                "https://example.test/docs/parse-failure",
                "https://example.test/docs/db-failure",
            ],
            headless=True,
        )
    )

    output = capsys.readouterr().out

    assert [item["outcome"] for item in results] == ["failed", "failed"]
    assert [item["reason_code"] for item in results if item["outcome"] == "failed"] == [
        "parse_error",
        "db_error",
    ]
    assert results[0]["reason"].startswith("page processing error:")
    assert results[1]["reason"].startswith("database error:")
    assert "[crawl] Targeted reindex summary: indexed=0 skipped=0 failed=2" in output
    assert "[crawl] Targeted reindex reasons: db_error=1 parse_error=1" in output


def test_reindex_selected_pages_keeps_prior_successes_when_a_later_write_fails(
    monkeypatch, tmp_path, capsys
):
    class FakePage:
        def __init__(self):
            self.current = {}
            self.url = ""

        async def goto(self, url, wait_until, timeout):
            self.current = {
                "title": f"Page for {url}",
                "html": "<html><body><main><h1>Loaded</h1></main></body></html>",
                "url": url,
            }
            self.url = url

        async def title(self):
            return self.current["title"]

        async def content(self):
            return self.current["html"]

        async def query_selector(self, selector):
            return None

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

    original_upsert_page = crawl_cli.upsert_page
    write_calls = []

    def flaky_upsert_page(index_file, url, title, content_md):
        write_calls.append(url)
        if url.endswith("/broken"):
            raise sqlite3.OperationalError("disk I/O error")
        return original_upsert_page(index_file, url, title, content_md)

    monkeypatch.setitem(
        sys.modules,
        "playwright.async_api",
        types.SimpleNamespace(async_playwright=lambda: FakePlaywrightManager()),
    )
    monkeypatch.setattr(crawl_cli.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(crawl_cli, "upsert_page", flaky_upsert_page)

    index_file = tmp_path / "docs.db"
    init_db(str(index_file))

    site = {
        "name": "Example Docs",
        "url": "https://example.test/docs",
        "index_file": str(index_file),
        "crawl": {
            "start_url": "https://example.test/docs",
            "delay_seconds": 0,
        },
    }

    results = asyncio.run(
        crawl_cli.reindex_selected_pages(
            site,
            [
                "https://example.test/docs/good",
                "https://example.test/docs/broken",
            ],
            headless=True,
        )
    )

    output = capsys.readouterr().out

    assert [item["outcome"] for item in results] == ["indexed", "failed"]
    assert results[1]["reason_code"] == "db_error"
    assert write_calls == [
        "https://example.test/docs/good",
        "https://example.test/docs/broken",
    ]
    assert get_page(str(index_file), "https://example.test/docs/good") is not None
    assert get_page(str(index_file), "https://example.test/docs/broken") is None
    assert "[crawl] Targeted reindex summary: indexed=1 skipped=0 failed=1" in output
    assert "[crawl] Targeted reindex reasons: db_error=1" in output


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


@pytest.mark.parametrize("redirect_policy", ["final", "requested", "skip"])
def test_reindex_selected_pages_skips_redirected_out_of_scope_pages(
    monkeypatch, tmp_path, capsys, redirect_policy
):
    class FakePage:
        def __init__(self):
            self.url = ""

        async def goto(self, url, wait_until, timeout):
            self.url = "https://other.test/outside/landing"

        async def title(self):
            return "Redirected landing"

        async def content(self):
            return "<html><body><main><h1>Redirected landing</h1></main></body></html>"

        async def query_selector(self, selector):
            return None

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
            "max_depth": 0,
            "delay_seconds": 0,
            "redirect_policy": redirect_policy,
            "allow_patterns": ["https://example.test/docs/*"],
        },
    }

    results = asyncio.run(
        crawl_cli.reindex_selected_pages(
            site,
            ["https://example.test/docs/guide"],
            headless=True,
        )
    )

    output = capsys.readouterr().out

    assert results == [
        {
            "url": "https://example.test/docs/guide",
            "requested_url": "https://example.test/docs/guide",
            "outcome": "skipped",
            "reason_code": "out_of_scope",
            "reason": "redirected to out-of-scope URL: host 'other.test' is outside start host 'example.test'",
        }
    ]
    assert "[crawl]   ↷ Skipped: host 'other.test' is outside start host 'example.test'" in output
    assert "[crawl] Targeted reindex summary: indexed=0 skipped=1 failed=0" in output
    assert "[crawl] Targeted reindex reasons: out_of_scope=1" in output


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

    import asyncio

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

    import asyncio

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

    import asyncio

    asyncio.run(crawl_cli.crawl_site_headful(site, headless=True, debug=False))

    assert context_kwargs["ignore_https_errors"] is expected["ignore_https_errors"]
    assert route_calls == expected["route_calls"]
    assert sleep_calls == expected["sleep_calls"]
    assert visited_urls == expected["visited_urls"]
    assert [row[1] for row in indexed] == expected["indexed_urls"]


def test_crawl_uses_site_playwright_engine_and_options(monkeypatch, tmp_path):
    calls = {}

    class FakePage:
        url = "https://example.test/docs"

        async def goto(self, *args, **kwargs):
            return None

        async def title(self):
            return "Docs"

        async def content(self):
            return "<main><h1>Docs</h1></main>"

        async def query_selector(self, selector):
            return None

        async def eval_on_selector_all(self, selector, script):
            return []

    class FakeContext:
        async def new_page(self):
            return FakePage()

    class FakeBrowser:
        async def new_context(self, **kwargs):
            calls["context"] = kwargs
            return FakeContext()

        async def close(self):
            return None

    class FakeEngine:
        def __init__(self, name):
            self.name = name

        async def launch(self, **kwargs):
            calls["engine"] = self.name
            calls["launch"] = kwargs
            return FakeBrowser()

    class FakePlaywrightManager:
        async def __aenter__(self):
            return types.SimpleNamespace(
                chromium=FakeEngine("chromium"),
                firefox=FakeEngine("firefox"),
                webkit=FakeEngine("webkit"),
            )

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setitem(
        sys.modules,
        "playwright.async_api",
        types.SimpleNamespace(async_playwright=lambda: FakePlaywrightManager()),
    )
    monkeypatch.setattr(crawl_cli, "upsert_page", lambda *args: None)
    site = {
        "name": "Example Docs",
        "url": "https://example.test/docs",
        "index_file": str(tmp_path / "docs.db"),
        "crawl": {"max_depth": 0, "delay_seconds": 0},
        "playwright": {
            "browser": "webkit",
            "launch": {"slow_mo": 25},
            "context": {"user_agent": "doc-mcp-test", "viewport": {"width": 800, "height": 600}},
        },
    }

    assert asyncio.run(crawl_cli.crawl_site_headful(site, headless=True))
    assert calls["engine"] == "webkit"
    assert calls["launch"] == {"headless": True, "slow_mo": 25}
    assert calls["context"] == {
        "viewport": {"width": 800, "height": 600},
        "user_agent": "doc-mcp-test",
        "ignore_https_errors": False,
    }

    calls.clear()
    results = asyncio.run(
        crawl_cli.reindex_selected_pages(
            site, ["https://example.test/docs/selected"], headless=True
        )
    )
    assert results[0]["outcome"] == "indexed"
    assert calls["engine"] == "webkit"
    assert calls["launch"] == {"headless": True, "slow_mo": 25}
    assert calls["context"]["viewport"] == {"width": 800, "height": 600}


def test_crawl_site_headful_start_delay_pauses_after_start_page_loads(
    monkeypatch, tmp_path, capsys
):
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

    asyncio.run(crawl_cli.crawl_site_headful(site, headless=False, debug=True))

    output = capsys.readouterr()

    assert headless_flags == [False]
    assert events[:2] == [
        ("goto", "https://example.test/docs"),
        ("sleep", 0.5),
    ]
    assert events[2] == ("index", "https://example.test/docs")
    assert "[crawl][debug] Using already loaded start page: https://example.test/docs" in output.err
    assert "[crawl][debug] Loaded page stayed on https://example.test/docs" in output.err


def test_crawl_site_headless_ignores_start_delay(monkeypatch, tmp_path):
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

    asyncio.run(crawl_cli.crawl_site_headful(site, headless=True, debug=False))

    assert headless_flags == [True]
    assert events[:2] == [
        ("goto", "https://example.test/docs"),
        ("index", "https://example.test/docs"),
    ]
    assert events[-1] == ("sleep", 0)


def test_crawl_site_headful_start_delay_load_error_stops_crawl(monkeypatch, tmp_path, capsys):
    closed = []
    events = []

    class FakePage:
        def __init__(self):
            self.url = ""

        async def goto(self, url, wait_until, timeout):
            events.append(("goto", url))
            raise RuntimeError("page load failed")

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
            closed.append(True)
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

    asyncio.run(crawl_cli.crawl_site_headful(site, headless=False, debug=True))

    output = capsys.readouterr()
    assert events == [("goto", "https://example.test/docs")]
    assert "[crawl][debug] Loading start page before crawl: https://example.test/docs" in output.err
    assert "[crawl]   ✗ Start page load error: page load failed" in output.out
    assert closed == [True]
