"""
Headful Crawl CLI — authenticates (if needed) and crawls a documentation site
using a real Playwright browser, saving pages as Markdown to the SQLite index.

This bypasses crawl4ai entirely, avoiding anti-bot detection issues on SPAs.
Markdown conversion is done via markdownify on the inner page HTML.

Usage:
    docmcp-crawl --site "LD documentation"
    docmcp-crawl --site "LD documentation" --force-auth
    docmcp-crawl --site "LD documentation" --headless
    docmcp-crawl --site "LD documentation" --debug
    docmcp-crawl --site "LD documentation" --vectorize
    docmcp-crawl --list
"""

import argparse
import asyncio
import base64
import contextlib
from io import BytesIO
import math
import re
import sqlite3
import sys
from collections import deque
from fnmatch import fnmatch
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlunparse

from dotenv import load_dotenv

from . import __version__
from .config.loader import ConfigError, get_sites
from .config.playwright import BrowserUnavailableError, launch_browser, resolve_playwright_settings
from .index_store import init_db, upsert_page
from .vector_index import (
    VectorBackendUnavailableError,
    VectorIndexError,
    rebuild_vector_index,
)

load_dotenv()

_DEFAULT_VIEWPORT = {"width": 1280, "height": 900}


# ---------------------------------------------------------------------------
# Optional: markdownify for HTML → Markdown conversion
# ---------------------------------------------------------------------------
try:
    from markdownify import markdownify as md_convert

    HAS_MARKDOWNIFY = True
except ImportError:
    HAS_MARKDOWNIFY = False
    print(
        "[crawl] Warning: markdownify not installed. Falling back to plain text extraction.",
        file=sys.stderr,
    )
    print("[crawl] Install with: pip install markdownify", file=sys.stderr)


try:
    from pypdf import PdfReader

    HAS_PYPDF = True
except ImportError:
    PdfReader = None
    HAS_PYPDF = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _normalize_url(url: str, *, strip_query: bool = True) -> str:
    """Strip fragments and optionally the query string; normalize scheme/host to lowercase."""
    p = urlparse(url)
    path = p.path
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    query = "" if strip_query else p.query
    return urlunparse((p.scheme.lower(), p.netloc.lower(), path, "", query, ""))


_STATIC_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".svg",
    ".ico",
    ".bmp",
    ".zip",
    ".tar",
    ".gz",
    ".mp4",
    ".mp3",
    ".avi",
    ".mov",
    ".woff",
    ".woff2",
    ".ttf",
    ".eot",
    ".otf",
    ".css",
    ".js",
    ".map",
}


class PdfExtractionError(RuntimeError):
    """Raised when a PDF cannot be extracted into searchable text."""


class PdfParserUnavailableError(PdfExtractionError):
    """Raised when PDF support is requested without its optional parser."""


def _is_pdf_url(url: str) -> bool:
    """Return True when a URL path identifies a PDF document."""
    return Path(urlparse(url).path).suffix.lower() == ".pdf"


def _is_pdf_content_type(content_type: str | None) -> bool:
    """Return True when a response content type identifies a PDF document."""
    return bool(content_type and content_type.split(";", 1)[0].strip().lower() == "application/pdf")


def _response_is_pdf(response) -> bool:
    """Return True when a Playwright response is a PDF."""
    return response is not None and _is_pdf_content_type(response.headers.get("content-type"))


def _extract_pdf_document(pdf_bytes: bytes) -> tuple[str | None, str]:
    """Extract a PDF's metadata title and searchable text."""
    if not HAS_PYPDF:
        raise PdfParserUnavailableError(
            "PDF support requires pypdf. Install it with: pip install pypdf"
        )
    try:
        reader = PdfReader(BytesIO(pdf_bytes))
        if reader.is_encrypted:
            raise PdfExtractionError("PDF is encrypted and requires a password")
        text_parts = []
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text and (page_text := page_text.strip()):
                text_parts.append(page_text)
        text = "\n\n".join(text_parts)
    except PdfExtractionError:
        raise
    except Exception as exc:
        # Convert all parser failures into the crawler's stable PDF error contract.
        raise PdfExtractionError(f"unable to read PDF: {exc}") from exc
    if not text:
        raise PdfExtractionError("PDF contains no extractable text")
    metadata = reader.metadata
    title = None
    if metadata and metadata.title:
        title = metadata.title.strip() or None
    return title, text


async def _fetch_pdf_document(
    context, url: str, *, page=None, playwright=None, proxy: dict | None = None
) -> tuple[str, str | None, str]:
    """Fetch a PDF using the CDP Fetch domain to capture raw bytes before Chrome's PDF viewer.

    The CDP ``Fetch.enable`` with ``requestStage: "Response"`` pauses every
    response at the network layer before Chrome hands the bytes to any plugin or
    renderer.  This lets us read the raw response body (via
    ``Fetch.getResponseBody``) and then release the request.  Because it is a
    real browser navigation the request carries the correct session cookies,
    ``Sec-Fetch-Mode: navigate``, and goes through the same proxy/DNS/TLS as
    any other page.
    """
    page_context = getattr(page, "context", None) if page is not None else None
    if callable(page_context):
        page_context = page_context()
    if page_context is not None and hasattr(page_context, "new_cdp_session"):
        # Open a short-lived page so the main crawl page is not disturbed.
        pdf_page = await context.new_page()
        cdp = await page_context.new_cdp_session(pdf_page)
        loop = asyncio.get_event_loop()
        captured: asyncio.Future = loop.create_future()

        async def _on_paused(event):
            request_id = event.get("requestId")
            stage = event.get("responseStatusCode")  # present only in response stage
            if stage is None:
                # Request stage — just continue, we only want the response.
                with contextlib.suppress(Exception):
                    await cdp.send("Fetch.continueRequest", {"requestId": request_id})
                return
            # Response stage — grab the body before releasing.
            try:
                result = await cdp.send("Fetch.getResponseBody", {"requestId": request_id})
                raw = result.get("body", "")
                is_b64 = result.get("base64Encoded", False)
                body = base64.b64decode(raw) if is_b64 else raw.encode()
                status = event.get("responseStatusCode", 0)
                final_url = event.get("request", {}).get("url", url)
                if not captured.done():
                    captured.set_result((status, final_url, body))
            except Exception as exc:
                if not captured.done():
                    captured.set_exception(exc)
            finally:
                with contextlib.suppress(Exception):
                    await cdp.send("Fetch.continueRequest", {"requestId": request_id})

        cdp.on("Fetch.requestPaused", _on_paused)
        try:
            # Enable CDP Fetch interception for this page only, response stage.
            await cdp.send(
                "Fetch.enable",
                {
                    "patterns": [{"urlPattern": url, "requestStage": "Response"}],
                },
            )
            with contextlib.suppress(Exception):
                await pdf_page.goto(url, wait_until="commit", timeout=60000)
            try:
                status, final_url, pdf_bytes = await asyncio.wait_for(
                    asyncio.shield(captured), timeout=30.0
                )
            except asyncio.TimeoutError as exc:
                raise PdfExtractionError("Timed out waiting for PDF response") from exc
            if status != 200:
                raise PdfExtractionError(f"PDF request failed with HTTP {status}")
            if not pdf_bytes:
                raise PdfExtractionError("PDF response body is empty")
            preserve_query = "?" in url
            final_url = _normalize_url(final_url, strip_query=not preserve_query)
            title, content = _extract_pdf_document(pdf_bytes)
            return final_url, title, content
        except PdfExtractionError:
            raise
        except Exception as exc:
            raise PdfExtractionError(f"PDF download failed: {exc}") from exc
        finally:
            with contextlib.suppress(Exception):
                await cdp.send("Fetch.disable")
            await pdf_page.close()

    # Fallback: use the existing browser context request client when available.
    request_context = None
    try:
        request_factory = getattr(playwright, "request", None) if playwright is not None else None
        if request_factory is not None:
            request_context = await request_factory.new_context(
                storage_state=await context.storage_state(),
                proxy=proxy,
            )
            request_client = request_context
        else:
            request_client = getattr(context, "request", None)
            if request_client is None:
                raise PdfExtractionError("PDF request client is unavailable")
        response = await request_client.get(
            url,
            timeout=60000,
            headers={"Accept": "application/pdf"},
        )
        if not response.ok:
            raise PdfExtractionError(f"PDF request failed with HTTP {response.status}")
        if not (_is_pdf_url(response.url) or _response_is_pdf(response)):
            raise PdfExtractionError("response is not a PDF document")
        title, content = _extract_pdf_document(await response.body())
        preserve_query = "?" in url
        return _normalize_url(response.url, strip_query=not preserve_query), title, content
    except PdfExtractionError:
        raise
    except Exception as exc:
        raise PdfExtractionError(f"PDF download failed: {exc}") from exc
    finally:
        if request_context is not None:
            await request_context.dispose()


_REDIRECT_POLICIES = frozenset({"final", "requested", "skip"})
_TARGETED_REINDEX_WARN_THRESHOLD = 100
_TARGETED_REINDEX_HARD_CAP = 500


def _invalid_redirect_policy_message(received_value: str, site_name: str | None = None) -> str:
    allowed_values = ", ".join(sorted(_REDIRECT_POLICIES))
    site_context = f" for site {site_name!r}" if site_name is not None else ""
    return (
        f"Invalid crawl.redirect_policy{site_context}: received "
        f"{received_value!r}; expected one of {allowed_values}"
    )


def _invalid_start_delay_message(received_value: object, site_name: str | None = None) -> str:
    site_context = f" for site {site_name!r}" if site_name is not None else ""
    return (
        f"Invalid crawl.start_delay_seconds{site_context}: received "
        f"{received_value!r}; expected a finite number >= 0"
    )


def _validate_start_delay_seconds(value: object, site_name: str | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(_invalid_start_delay_message(value, site_name))

    delay_seconds = float(value)
    if not math.isfinite(delay_seconds) or delay_seconds < 0:
        raise ConfigError(_invalid_start_delay_message(value, site_name))
    return delay_seconds


def _invalid_delay_message(received_value: object, site_name: str | None = None) -> str:
    site_context = f" for site {site_name!r}" if site_name is not None else ""
    return (
        f"Invalid crawl.delay_seconds{site_context}: received "
        f"{received_value!r}; expected a finite number >= 0"
    )


def _validate_delay_seconds(value: object, site_name: str | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(_invalid_delay_message(value, site_name))

    delay_seconds = float(value)
    if not math.isfinite(delay_seconds) or delay_seconds < 0:
        raise ConfigError(_invalid_delay_message(value, site_name))
    return delay_seconds


def _is_page_url(url: str) -> bool:
    """Return False if the URL points to a static asset (image, font, archive, etc.)."""
    path = urlparse(url).path.lower()
    ext = Path(path).suffix
    return ext not in _STATIC_EXTENSIONS


def _is_allowed(
    url: str, start_url: str, allow_patterns: list[str], deny_patterns: list[str]
) -> bool:
    """Return True if url should be crawled."""
    return _disallowed_reason(url, start_url, allow_patterns, deny_patterns) is None


def _disallowed_reason(
    url: str, start_url: str, allow_patterns: list[str], deny_patterns: list[str]
) -> str | None:
    """Return the first reason a URL should not be crawled, or None if it is allowed."""
    ps = urlparse(start_url)
    pu = urlparse(url)
    if pu.netloc != ps.netloc:
        return f"host '{pu.netloc}' is outside start host '{ps.netloc}'"
    start_path = ps.path.rstrip("/") or "/"
    if not pu.path.startswith(start_path):
        return f"path '{pu.path or '/'}' is outside start path '{start_path}'"
    for pat in deny_patterns:
        if fnmatch(url, pat):
            return f"matches deny pattern '{pat}'"
    if allow_patterns:
        if not any(fnmatch(url, pat) for pat in allow_patterns):
            return "does not match allow patterns"
    return None


def _html_to_markdown(html: str) -> str:
    """Convert HTML to Markdown, or fall back to stripping tags."""
    # Remove non-content blocks first so markdownify does not turn their inner text
    # into visible garbage in the indexed document.
    html = re.sub(r"<!--.*?-->", " ", html, flags=re.S)
    html = re.sub(
        r"<(script|style|noscript|template|head|nav|footer)\b.*?>.*?</\1>",
        " ",
        html,
        flags=re.S | re.I,
    )
    if HAS_MARKDOWNIFY:
        return md_convert(html, heading_style="ATX", strip=["script", "style", "nav", "footer"])
    # Fallback: strip all HTML tags
    text = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s{2,}", " ", text).strip()


def _validate_selected_page_url(
    url: str, start_url: str, allow_patterns: list[str], deny_patterns: list[str]
) -> tuple[str | None, str | None, str | None]:
    """Normalize and validate a targeted reindex URL."""
    normalized_url = _normalize_url(url, strip_query=False)
    if not _is_page_url(normalized_url):
        return None, "asset_url", "URL points to a non-page asset"
    reason = _disallowed_reason(normalized_url, start_url, allow_patterns, deny_patterns)
    if reason:
        return None, "out_of_scope", reason
    return normalized_url, None, None


def _selected_page_scope_reason(
    url: str, start_url: str, allow_patterns: list[str], deny_patterns: list[str]
) -> str | None:
    """Return a selected-page scope violation reason using the targeted reindex policy."""
    return _disallowed_reason(url, start_url, allow_patterns, deny_patterns)


def _selected_page_result(
    *,
    url: str,
    outcome: str,
    reason_code: str | None = None,
    reason: str | None = None,
    requested_url: str | None = None,
    title: str | None = None,
) -> dict:
    result = {"url": url, "outcome": outcome}
    if requested_url is not None:
        result["requested_url"] = requested_url
    if reason_code is not None:
        result["reason_code"] = reason_code
    if reason is not None:
        result["reason"] = reason
    if title is not None:
        result["title"] = title
    return result


def _load_selected_pages(page_urls: list[str] | None, pages_file: str | None) -> list[str]:
    """Load targeted reindex URLs from CLI arguments and an optional file."""
    selected_pages = list(page_urls or [])
    raw_pages = selected_pages
    if pages_file:
        with Path(pages_file).open(encoding="utf-8") as handle:
            for line in handle:
                candidate = line.strip()
                if candidate and not candidate.startswith("#"):
                    raw_pages.append(candidate)

    normalized_pages: list[str] = []
    seen_pages: set[str] = set()
    for raw_page in raw_pages:
        candidate = raw_page.strip()
        if not candidate:
            continue
        normalized_page = _normalize_url(candidate, strip_query=False)
        if normalized_page in seen_pages:
            continue
        seen_pages.add(normalized_page)
        normalized_pages.append(normalized_page)
    return normalized_pages


async def _extract_page_html(page) -> str:
    """Extract the most complete rendered HTML we can get from the page."""
    candidates: list[str] = []
    try:
        full_html = await page.content()
        if full_html:
            candidates.append(full_html)
    except Exception:
        pass

    for selector in [
        "main",
        "article",
        '[role="main"]',
        "#content",
        ".content",
        "body",
    ]:
        try:
            el = await page.query_selector(selector)
            if el:
                html = await el.inner_html()
                if html:
                    candidates.append(html)
        except Exception:
            continue

    if not candidates:
        return ""
    return max(candidates, key=len)


def _extract_links(
    page_url: str, link_elements: list[dict], *, ignore_query_links: bool = True
) -> list[tuple[str, bool]]:
    """Extract and normalize hrefs from Playwright link objects.

    Returns pairs of (normalized_url, is_anchor_link).
    """
    links = []
    normalized_page_url = _normalize_url(page_url, strip_query=False)
    for el in link_elements:
        href = el.get("href", "") or ""
        href = href.strip()
        if not href or href.startswith(("#", "mailto:", "javascript:")):
            continue
        absolute_url = urljoin(page_url, href)
        parsed_url = urlparse(absolute_url)
        normalized_absolute_url = _normalize_url(absolute_url, strip_query=False)
        is_anchor_link = (
            bool(parsed_url.fragment) and normalized_absolute_url == normalized_page_url
        )
        if ignore_query_links and parsed_url.query and not is_anchor_link:
            continue
        normalized_url = (
            normalized_page_url
            if is_anchor_link
            else _normalize_url(absolute_url, strip_query=ignore_query_links)
        )
        links.append((normalized_url, is_anchor_link))
    return links


def _format_queue_preview(
    queue: deque[tuple[str, int]], depth: int, total_levels: int, limit: int = 5
) -> str:
    """Summarize the queued URLs for a crawl depth."""
    queued_urls = [url for url, item_depth in queue if item_depth == depth]
    if not queued_urls:
        return f"Next queue for level {depth + 1}/{total_levels}: 0 queued URLs -> (empty)"
    preview = ", ".join(queued_urls[:limit])
    remaining = len(queued_urls) - limit
    if remaining > 0:
        preview = f"{preview}, ... (+{remaining} more)"
    count = len(queued_urls)
    label = "URL" if count == 1 else "URLs"
    return f"Next queue for level {depth + 1}/{total_levels}: {count} queued {label} -> {preview}"


def _link_discovery_decision(
    href: str,
    *,
    is_anchor_link: bool,
    visited: set[str],
    queued: set[str],
    start_url: str,
    allow_patterns: list[str],
    deny_patterns: list[str],
    ignore_anchor_links: bool,
) -> tuple[bool, str]:
    """Explain whether a discovered link should be enqueued."""
    if ignore_anchor_links and is_anchor_link:
        return False, "anchor link points to the current page"
    if href in visited:
        return False, "already visited"
    if href in queued:
        return False, "already queued"
    if not _is_page_url(href):
        return False, "URL points to a non-page asset"
    reason = _disallowed_reason(href, start_url, allow_patterns, deny_patterns)
    if reason:
        return False, reason
    return True, "eligible for crawl"


def _get_redirect_policy(crawl_cfg: dict, site_name: str | None = None) -> str:
    """Return the normalized redirect policy for a site crawl config."""
    policy = crawl_cfg.get("redirect_policy", "final")
    if not isinstance(policy, str):
        raise ConfigError(_invalid_redirect_policy_message(policy, site_name))
    normalized_policy = policy.strip().lower()
    if normalized_policy not in _REDIRECT_POLICIES:
        raise ConfigError(_invalid_redirect_policy_message(policy, site_name))
    return normalized_policy


def _authenticate_site(site: dict, force: bool = False) -> None:
    """Authenticate a site using the lazy-loaded auth session helper."""
    from .auth.session import authenticate

    result = authenticate(site, force=force)
    if asyncio.iscoroutine(result):
        asyncio.run(result)


async def _index_loaded_page(
    page,
    *,
    requested_url: str,
    current_url: str,
    index_file: str,
    redirect_policy: str,
    debug,
) -> tuple[str | None, str]:
    """Capture, convert, and upsert the current page into the SQLite index."""
    if current_url != requested_url:
        if redirect_policy == "requested":
            index_url = requested_url
            debug(f"Redirect policy=requested -> indexing requested URL {index_url}")
        elif redirect_policy == "skip":
            index_url = None
            debug("Redirect policy=skip -> skipping redirected page")
        else:
            index_url = current_url
            debug(f"Redirect policy=final -> indexing final URL {index_url}")
    else:
        index_url = current_url

    title = await page.title() or requested_url
    html = await _extract_page_html(page)
    content_md = _html_to_markdown(html) if html else ""
    debug(
        f"Page title={title!r}; extracted {len(html)} HTML chars -> {len(content_md)} Markdown chars"
    )

    if index_url is not None:
        upsert_page(index_file, index_url, title, content_md)
    return index_url, title


async def _index_pdf_document(
    context,
    *,
    requested_url: str,
    index_file: str,
    redirect_policy: str,
    debug,
    page=None,
    playwright=None,
    proxy: dict | None = None,
) -> tuple[str | None, str]:
    """Fetch, extract, and upsert a PDF into the SQLite page index."""
    fetch_options = {"playwright": playwright, "proxy": proxy}
    if page is not None:
        fetch_options["page"] = page
    current_url, pdf_title, content_md = await _fetch_pdf_document(
        context, requested_url, **fetch_options
    )
    if current_url != requested_url:
        if redirect_policy == "requested":
            index_url = requested_url
            debug(f"Redirect policy=requested -> indexing requested URL {index_url}")
        elif redirect_policy == "skip":
            index_url = None
            debug("Redirect policy=skip -> skipping redirected PDF")
        else:
            index_url = current_url
            debug(f"Redirect policy=final -> indexing final URL {index_url}")
    else:
        index_url = current_url
    title_fallback_url = index_url or current_url
    title = pdf_title or title_fallback_url
    debug(f"PDF title={title!r}; extracted {len(content_md)} text chars")
    if index_url is not None:
        upsert_page(index_file, index_url, title, content_md)
    return index_url, title


# ---------------------------------------------------------------------------
# Core headful crawler
# ---------------------------------------------------------------------------


async def crawl_site_headful(site: dict, headless: bool = False, debug: bool = False) -> bool:
    """
    Crawl a site using a real Playwright browser (headful by default).
    Uses the saved session from auth_cli.py, or prompts auth if missing.
    Returns True when the crawl reaches normal completion.
    """
    name = site["name"]
    stop_crawl = True
    crawl_cfg = site.get("crawl", {})
    start_url = crawl_cfg.get("start_url", site["url"])
    max_depth = crawl_cfg.get("max_depth", 3)
    delay_seconds = _validate_delay_seconds(crawl_cfg.get("delay_seconds", 1.0), name)
    start_delay_seconds = _validate_start_delay_seconds(
        crawl_cfg.get("start_delay_seconds", 0.0), name
    )
    from playwright.async_api import async_playwright

    allow_patterns = crawl_cfg.get("allow_patterns", [])
    deny_patterns = crawl_cfg.get("deny_patterns", [])
    block_images = crawl_cfg.get("block_images", False)
    ignore_query_links = crawl_cfg.get("ignore_query_links", True)
    ignore_anchor_links = crawl_cfg.get("ignore_anchor_links", True)
    ignore_https_errors = crawl_cfg.get("ignore_https_errors", False)
    redirect_policy = _get_redirect_policy(crawl_cfg, name)
    index_file = site["index_file"]
    session_file = site.get("session_file")

    print(f"\n[crawl] Site     : {name}")
    print(f"[crawl] Start URL: {start_url}")
    print(f"[crawl] Max depth: {max_depth}")
    print(f"[crawl] Index    : {index_file}")

    init_db(index_file)

    # Login indicators used to detect redirect to auth page
    login_indicators = ["login", "signin", "sign-in", "/auth", "/sso"]
    page_count = 0

    def _debug(message: str) -> None:
        """Print a debug-only crawl trace line."""
        if debug:
            print(f"[crawl][debug] {message}", file=sys.stderr)

    async with async_playwright() as p:
        # Launch browser — headful by default to avoid anti-bot detection
        settings = resolve_playwright_settings(site)
        browser = await launch_browser(p, settings, headless=headless)

        # Load saved session if available
        context_kwargs = {
            "viewport": _DEFAULT_VIEWPORT,
            **settings.context_options,
        }
        if session_file and Path(session_file).exists():
            context_kwargs["storage_state"] = session_file
            print(f"[crawl] Loaded session: {session_file}")

        context = await browser.new_context(
            **context_kwargs, ignore_https_errors=ignore_https_errors
        )

        # Block images, fonts, and media to speed up crawling
        if block_images:
            blocked = {"image", "media", "font"}

            async def _block_resources(route, request):
                if request.resource_type in blocked:
                    await route.abort()
                else:
                    await route.continue_()

            await context.route("**/*", _block_resources)
            print("[crawl] Resource blocking: images/fonts/media disabled")

        page = await context.new_page()

        try:
            stop_crawl = False
            seed_url = _normalize_url(start_url, strip_query=False)
            seed_preserves_query = "?" in seed_url
            use_loaded_start_page = False

            if start_delay_seconds and not headless:
                use_loaded_start_page = True
                _debug(f"Loading start page before crawl: {seed_url}")
                try:
                    await page.goto(seed_url, wait_until="networkidle", timeout=60000)
                except Exception as e:
                    print(f"[crawl]   ✗ Start page load error: {e}")
                    stop_crawl = True
                else:
                    loaded_start_url = _normalize_url(page.url, strip_query=False)
                    _debug(f"Start page loaded at {loaded_start_url}")
                    print(f"[crawl] Start delay: {start_delay_seconds:g}s after start page loads")
                    _debug(f"Pausing {start_delay_seconds:g}s before the first crawl request")
                    await asyncio.sleep(start_delay_seconds)
                    seed_url = _normalize_url(page.url, strip_query=False)
                    seed_preserves_query = "?" in seed_url
                    _debug(f"Start page selected for crawl: {seed_url}")

            visited: set[str] = set()
            queued: set[str] = {seed_url}
            queue: deque[tuple[str, int]] = deque([(seed_url, 0)])

            while queue and not stop_crawl:
                loaded_page_active = use_loaded_start_page
                depth = queue[0][1]
                level_total = sum(1 for _, item_depth in queue if item_depth == depth)
                level_number = depth + 1
                total_levels = max_depth + 1
                _debug(
                    f"Starting level {level_number}/{total_levels} with {level_total} queued URL(s)"
                )

                for index_in_level in range(1, level_total + 1):
                    url, item_depth = queue.popleft()
                    if item_depth != depth:
                        queue.appendleft((url, item_depth))
                        break
                    queued.discard(url)
                    if url in visited:
                        continue
                    visited.add(url)
                    used_preloaded_page = loaded_page_active and url == seed_url
                    response = None

                    print(
                        f"[crawl] [{index_in_level} of {level_total} level {level_number}/{total_levels}] {url}"
                    )
                    if _is_pdf_url(url):
                        try:
                            index_url, title = await _index_pdf_document(
                                context,
                                requested_url=url,
                                index_file=index_file,
                                redirect_policy=redirect_policy,
                                debug=_debug,
                                page=page,
                                playwright=p,
                                proxy=settings.launch_options.get("proxy"),
                            )
                        except PdfExtractionError as exc:
                            print(f"[crawl]   ✗ PDF extraction error: {exc}")
                            continue
                        if index_url is None:
                            print("[crawl]   ↷ Skipped: redirect_policy=skip")
                        else:
                            page_count += 1
                            print(f"[crawl]   ✓ Indexed: {title[:70]}")
                        await asyncio.sleep(delay_seconds)
                        continue
                    if used_preloaded_page:
                        _debug(f"Using already loaded start page: {url}")
                        use_loaded_start_page = False
                    else:
                        _debug(f"Navigating to {url}")
                        try:
                            response = await page.goto(url, wait_until="networkidle", timeout=60000)
                        except Exception as e:
                            print(f"[crawl]   ✗ Navigation error: {e}")
                            continue
                    strip_query = ignore_query_links and not (
                        url == seed_url and seed_preserves_query
                    )
                    current_url = _normalize_url(
                        page.url,
                        strip_query=strip_query,
                    )
                    redirected = current_url != url
                    if used_preloaded_page:
                        if redirected:
                            _debug(f"Loaded page redirected to {current_url}")
                        else:
                            _debug(f"Loaded page stayed on {current_url}")
                    elif redirected:
                        _debug(f"Navigation redirected to {current_url}")
                    else:
                        _debug(f"Navigation stayed on {current_url}")

                    if _response_is_pdf(response):
                        try:
                            index_url, title = await _index_pdf_document(
                                context,
                                requested_url=url,
                                index_file=index_file,
                                redirect_policy=redirect_policy,
                                debug=_debug,
                                page=page,
                            )
                        except PdfExtractionError as exc:
                            print(f"[crawl]   ✗ PDF extraction error: {exc}")
                            continue
                        if index_url is None:
                            print("[crawl]   ↷ Skipped: redirect_policy=skip")
                        else:
                            page_count += 1
                            print(f"[crawl]   ✓ Indexed: {title[:70]}")
                        await asyncio.sleep(delay_seconds)
                        continue

                    # Detect redirect to login page
                    if any(ind in current_url for ind in login_indicators):
                        print("[crawl]   ✗ Redirected to login — session may be expired. Stopping.")
                        print(f'[crawl]   Run: docmcp-auth --site "{name}" --force')
                        stop_crawl = True
                        break

                    index_url, title = await _index_loaded_page(
                        page,
                        requested_url=url,
                        current_url=current_url,
                        index_file=index_file,
                        redirect_policy=redirect_policy,
                        debug=_debug,
                    )
                    if index_url is None:
                        print("[crawl]   ↷ Skipped: redirect_policy=skip")
                    else:
                        page_count += 1
                        print(f"[crawl]   ✓ Indexed: {title[:70]}")

                    # Discover links for next depth
                    if depth < max_depth:
                        try:
                            anchors = await page.eval_on_selector_all(
                                "a[href]", "els => els.map(e => ({ href: e.href }))"
                            )
                            discovered_links = _extract_links(
                                current_url,
                                anchors,
                                ignore_query_links=ignore_query_links,
                            )
                            _debug(
                                f"Discovered {len(anchors)} raw anchors, {len(discovered_links)} normalized link target(s)"
                            )
                            for href, is_anchor_link in discovered_links:
                                should_enqueue, reason = _link_discovery_decision(
                                    href,
                                    is_anchor_link=is_anchor_link,
                                    visited=visited,
                                    queued=queued,
                                    start_url=start_url,
                                    allow_patterns=allow_patterns,
                                    deny_patterns=deny_patterns,
                                    ignore_anchor_links=ignore_anchor_links,
                                )
                                if should_enqueue:
                                    queue.append((href, depth + 1))
                                    queued.add(href)
                                    _debug(
                                        f"Discovered {href} -> queued for level {depth + 2}/{total_levels}"
                                    )
                                else:
                                    _debug(f"Discovered {href} -> skipped ({reason})")
                        except Exception as e:
                            print(f"[crawl]   ✗ Link extraction error: {e}")

                    await asyncio.sleep(delay_seconds)

                if stop_crawl:
                    break
                if debug and queue:
                    next_depth = queue[0][1]
                    if next_depth > depth:
                        _debug(_format_queue_preview(queue, next_depth, total_levels))

        finally:
            await browser.close()

    print(f"\n[crawl] Done. {page_count} pages indexed → {index_file}")
    return not stop_crawl


async def reindex_selected_pages(
    site: dict, page_urls: list[str], headless: bool = False, debug: bool = False
) -> list[dict]:
    """Reindex only the explicitly selected page URLs for a configured site."""
    name = site["name"]
    crawl_cfg = site.get("crawl", {})
    start_url = crawl_cfg.get("start_url", site["url"])
    delay_seconds = _validate_delay_seconds(crawl_cfg.get("delay_seconds", 1.0), name)
    redirect_policy = _get_redirect_policy(crawl_cfg, name)
    allow_patterns = crawl_cfg.get("allow_patterns", [])
    deny_patterns = crawl_cfg.get("deny_patterns", [])
    block_images = crawl_cfg.get("block_images", False)
    ignore_https_errors = crawl_cfg.get("ignore_https_errors", False)
    index_file = site["index_file"]
    session_file = site.get("session_file")
    login_indicators = ["login", "signin", "sign-in", "/auth", "/sso"]
    results: list[dict] = []

    def _debug(message: str) -> None:
        if debug:
            print(f"[crawl][debug] {message}", file=sys.stderr)

    print(f"\n[crawl] Site     : {name}")
    print("[crawl] Mode     : targeted reindex")
    print(f"[crawl] Start URL: {start_url}")
    print(f"[crawl] Index    : {index_file}")
    print(f"[crawl] Pages    : {len(page_urls)}")

    init_db(index_file)

    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        settings = resolve_playwright_settings(site)
        browser = await launch_browser(p, settings, headless=headless)

        context_kwargs = {
            "viewport": _DEFAULT_VIEWPORT,
            **settings.context_options,
        }
        if session_file and Path(session_file).exists():
            context_kwargs["storage_state"] = session_file
            print(f"[crawl] Loaded session: {session_file}")

        context = await browser.new_context(
            **context_kwargs, ignore_https_errors=ignore_https_errors
        )

        if block_images:
            blocked = {"image", "media", "font"}

            async def _block_resources(route, request):
                if request.resource_type in blocked:
                    await route.abort()
                else:
                    await route.continue_()

            await context.route("**/*", _block_resources)
            print("[crawl] Resource blocking: images/fonts/media disabled")

        page = await context.new_page()

        try:
            for index, raw_url in enumerate(page_urls, start=1):
                normalized_url, reason_code, reason = _validate_selected_page_url(
                    raw_url,
                    start_url,
                    allow_patterns,
                    deny_patterns,
                )
                if reason is not None:
                    print(f"[crawl] [{index} of {len(page_urls)}] {raw_url}")
                    print(f"[crawl]   ↷ Skipped: {reason}")
                    results.append(
                        _selected_page_result(
                            url=raw_url,
                            outcome="skipped",
                            reason_code=reason_code,
                            reason=reason,
                        )
                    )
                    continue

                print(f"[crawl] [{index} of {len(page_urls)}] {normalized_url}")
                if _is_pdf_url(normalized_url):
                    try:
                        index_url, title = await _index_pdf_document(
                            context,
                            requested_url=normalized_url,
                            index_file=index_file,
                            redirect_policy=redirect_policy,
                            debug=_debug,
                            page=page,
                            playwright=p,
                            proxy=settings.launch_options.get("proxy"),
                        )
                    except PdfExtractionError as exc:
                        message = f"PDF extraction error: {exc}"
                        print(f"[crawl]   ✗ {message}")
                        results.append(
                            _selected_page_result(
                                url=normalized_url,
                                outcome="failed",
                                reason_code="pdf_error",
                                reason=message,
                            )
                        )
                    else:
                        if index_url is None:
                            print("[crawl]   ↷ Skipped: redirect_policy=skip")
                            results.append(
                                _selected_page_result(
                                    url=normalized_url,
                                    outcome="skipped",
                                    reason_code="redirect_policy_skip",
                                    reason="redirect_policy=skip",
                                )
                            )
                        else:
                            print(f"[crawl]   ✓ Indexed: {title[:70]}")
                            results.append(
                                _selected_page_result(
                                    url=index_url,
                                    requested_url=normalized_url,
                                    outcome="indexed",
                                    title=title,
                                )
                            )
                    await asyncio.sleep(delay_seconds)
                    continue
                _debug(f"Navigating to {normalized_url}")
                try:
                    response = await page.goto(
                        normalized_url, wait_until="networkidle", timeout=60000
                    )
                except Exception as exc:
                    print(f"[crawl]   ✗ Navigation error: {exc}")
                    results.append(
                        _selected_page_result(
                            url=normalized_url,
                            outcome="failed",
                            reason_code="navigation_error",
                            reason=f"navigation error: {exc}",
                        )
                    )
                    continue

                current_url = _normalize_url(page.url, strip_query=False)
                if current_url != normalized_url:
                    _debug(f"Navigation redirected to {current_url}")
                else:
                    _debug(f"Navigation stayed on {current_url}")

                if any(ind in current_url for ind in login_indicators):
                    message = "redirected to login — session may be expired"
                    print(f"[crawl]   ✗ {message}. Stopping.")
                    print(f'[crawl]   Run: docmcp-auth --site "{name}" --force')
                    results.append(
                        _selected_page_result(
                            url=normalized_url,
                            outcome="failed",
                            reason_code="login_redirect",
                            reason=message,
                        )
                    )
                    break

                post_redirect_reason = _selected_page_scope_reason(
                    current_url,
                    start_url,
                    allow_patterns,
                    deny_patterns,
                )
                if post_redirect_reason is not None:
                    print(f"[crawl]   ↷ Skipped: {post_redirect_reason}")
                    results.append(
                        _selected_page_result(
                            url=normalized_url,
                            requested_url=normalized_url,
                            outcome="skipped",
                            reason_code="out_of_scope",
                            reason=f"redirected to out-of-scope URL: {post_redirect_reason}",
                        )
                    )
                    continue

                try:
                    if _response_is_pdf(response):
                        index_url, title = await _index_pdf_document(
                            context,
                            requested_url=normalized_url,
                            index_file=index_file,
                            redirect_policy=redirect_policy,
                            debug=_debug,
                            page=page,
                            playwright=p,
                            proxy=settings.launch_options.get("proxy"),
                        )
                    else:
                        index_url, title = await _index_loaded_page(
                            page,
                            requested_url=normalized_url,
                            current_url=current_url,
                            index_file=index_file,
                            redirect_policy=redirect_policy,
                            debug=_debug,
                        )
                except sqlite3.Error as exc:
                    print(f"[crawl]   ✗ Database error: {exc}")
                    results.append(
                        _selected_page_result(
                            url=normalized_url,
                            outcome="failed",
                            reason_code="db_error",
                            reason=f"database error: {exc}",
                        )
                    )
                    continue
                except Exception as exc:
                    print(f"[crawl]   ✗ Page processing error: {exc}")
                    results.append(
                        _selected_page_result(
                            url=normalized_url,
                            outcome="failed",
                            reason_code="parse_error",
                            reason=f"page processing error: {exc}",
                        )
                    )
                    continue
                if index_url is None:
                    print("[crawl]   ↷ Skipped: redirect_policy=skip")
                    results.append(
                        _selected_page_result(
                            url=normalized_url,
                            outcome="skipped",
                            reason_code="redirect_policy_skip",
                            reason="redirect_policy=skip",
                        )
                    )
                else:
                    print(f"[crawl]   ✓ Indexed: {title[:70]}")
                    results.append(
                        _selected_page_result(
                            url=index_url,
                            requested_url=normalized_url,
                            outcome="indexed",
                            title=title,
                        )
                    )

                await asyncio.sleep(delay_seconds)

        finally:
            await browser.close()

    counts = {
        "indexed": sum(1 for item in results if item["outcome"] == "indexed"),
        "skipped": sum(1 for item in results if item["outcome"] == "skipped"),
        "failed": sum(1 for item in results if item["outcome"] == "failed"),
    }
    reason_counts: dict[str, int] = {}
    for item in results:
        reason_code = item.get("reason_code")
        if reason_code:
            reason_counts[reason_code] = reason_counts.get(reason_code, 0) + 1
    print(
        "\n[crawl] Targeted reindex summary: "
        f"indexed={counts['indexed']} skipped={counts['skipped']} failed={counts['failed']}"
    )
    if reason_counts:
        breakdown = " ".join(f"{code}={reason_counts[code]}" for code in sorted(reason_counts))
        print(f"[crawl] Targeted reindex reasons: {breakdown}")
    return results


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        prog="docmcp-crawl",
        description=(
            "Headful browser crawler — authenticates and indexes a documentation site.\n"
            f"Version: {__version__}"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--site", type=str, help="Name of the site to crawl (as in sites.yaml)")
    parser.add_argument(
        "--force-auth", action="store_true", help="Force re-authentication before crawling"
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run browser in headless mode (may trigger anti-bot)",
    )
    parser.add_argument("--debug", action="store_true", help="Print detailed crawler diagnostics")
    parser.add_argument(
        "--vectorize",
        action="store_true",
        help="Build or refresh the local vector index after a successful crawl",
    )
    parser.add_argument(
        "--pages",
        nargs="+",
        metavar="URL",
        help="Reindex only the selected page URL(s)",
    )
    parser.add_argument(
        "--pages-file",
        type=str,
        help="Read page URLs to reindex from a file (one URL per line)",
    )
    parser.add_argument("--list", action="store_true", help="List all configured sites")
    parser.add_argument("--version", action="store_true", help="Show the current version and exit")
    args = parser.parse_args()

    if args.version:
        if (
            args.site
            or args.force_auth
            or args.headless
            or args.debug
            or args.vectorize
            or args.pages
            or args.pages_file
            or args.list
        ):
            parser.error("--version cannot be combined with other arguments")
        print(f"{parser.prog} {__version__}")
        sys.exit(0)

    if not args.list and not args.site:
        parser.print_help()
        return

    try:
        sites = get_sites()
    except ConfigError as exc:
        print(f"[docmcp-crawl] Configuration error:\n{exc}", file=sys.stderr)
        sys.exit(1)

    if args.list:
        print("\nConfigured sites:")
        for s in sites:
            auth = "auth required" if s.get("auth_required") else "public"
            print(f"  - {s['name']} ({auth}) — {s['url']}")
        return

    site = next((s for s in sites if s["name"].lower() == args.site.lower()), None)
    if not site:
        print(f"[crawl] Site '{args.site}' not found. Use --list to see available sites.")
        sys.exit(1)

    # Authenticate first if required
    try:
        if site.get("auth_required"):
            _authenticate_site(site, force=args.force_auth)
    except BrowserUnavailableError as exc:
        print(f"[docmcp-crawl] Browser error:\n{exc}", file=sys.stderr)
        sys.exit(1)

    try:
        selected_pages = _load_selected_pages(args.pages, args.pages_file)
    except (OSError, UnicodeError) as exc:
        print(f"[docmcp-crawl] Failed to read --pages-file:\n{exc}", file=sys.stderr)
        sys.exit(1)

    try:
        if selected_pages:
            selected_page_count = len(selected_pages)
            if selected_page_count > _TARGETED_REINDEX_HARD_CAP:
                print(
                    "[docmcp-crawl] Refusing targeted reindex with "
                    f"{selected_page_count} pages; the maximum supported batch size is "
                    f"{_TARGETED_REINDEX_HARD_CAP}. Split the file or use the normal crawl path.",
                    file=sys.stderr,
                )
                sys.exit(1)
            if selected_page_count >= _TARGETED_REINDEX_WARN_THRESHOLD:
                print(
                    "[docmcp-crawl] Warning: targeted reindex contains "
                    f"{selected_page_count} pages. Large batches can behave like a near-full crawl "
                    "and are more expensive for SQLite-backed runs.",
                    file=sys.stderr,
                )
            results = asyncio.run(
                reindex_selected_pages(
                    site,
                    selected_pages,
                    headless=args.headless,
                    debug=args.debug,
                )
            )
            crawl_completed = not any(item["outcome"] == "failed" for item in results)
        else:
            crawl_completed = asyncio.run(
                crawl_site_headful(site, headless=args.headless, debug=args.debug)
            )
    except ConfigError as exc:
        print(f"[docmcp-crawl] Configuration error:\n{exc}", file=sys.stderr)
        sys.exit(1)
    except BrowserUnavailableError as exc:
        print(f"[docmcp-crawl] Browser error:\n{exc}", file=sys.stderr)
        sys.exit(1)

    if args.vectorize and crawl_completed:
        print("[crawl] Vectorize : enabled")
        try:
            rebuild_vector_index(site, debug=args.debug)
        except VectorBackendUnavailableError as exc:
            print(f"[vectorize] sqlite-vec backend unavailable:\n{exc}", file=sys.stderr)
            sys.exit(1)
        except VectorIndexError as exc:
            print(f"[vectorize] Vectorization failed:\n{exc}", file=sys.stderr)
            sys.exit(1)
    elif args.vectorize:
        print("[crawl] Skipping vectorize: crawl did not complete successfully")


if __name__ == "__main__":
    main()
