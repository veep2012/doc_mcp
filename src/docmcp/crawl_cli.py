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
import math
import re
import sys
from collections import deque
from fnmatch import fnmatch
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlunparse

from dotenv import load_dotenv

from . import __version__
from .config.loader import ConfigError, get_sites
from .index_store import init_db, upsert_page
from .vector_index import (
    VectorBackendUnavailableError,
    VectorIndexError,
    rebuild_vector_index,
)

load_dotenv()


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
    ".pdf",
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


_REDIRECT_POLICIES = frozenset({"final", "requested", "skip"})


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
        browser = await p.chromium.launch(headless=headless)

        # Load saved session if available
        context_kwargs = {}
        if session_file and Path(session_file).exists():
            context_kwargs["storage_state"] = session_file
            print(f"[crawl] Loaded session: {session_file}")

        context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            ignore_https_errors=ignore_https_errors,
            **context_kwargs,
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

                    print(
                        f"[crawl] [{index_in_level} of {level_total} level {level_number}/{total_levels}] {url}"
                    )
                    if used_preloaded_page:
                        _debug(f"Using already loaded start page: {url}")
                        use_loaded_start_page = False
                    else:
                        _debug(f"Navigating to {url}")
                        try:
                            await page.goto(url, wait_until="networkidle", timeout=60000)
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

                    # Detect redirect to login page
                    if any(ind in current_url for ind in login_indicators):
                        print("[crawl]   ✗ Redirected to login — session may be expired. Stopping.")
                        print(f'[crawl]   Run: docmcp-auth --site "{name}" --force')
                        stop_crawl = True
                        break

                    if redirected:
                        if redirect_policy == "requested":
                            index_url = url
                            _debug(
                                f"Redirect policy=requested -> indexing requested URL {index_url}"
                            )
                        elif redirect_policy == "skip":
                            index_url = None
                            _debug("Redirect policy=skip -> skipping redirected page")
                        else:
                            index_url = current_url
                            _debug(f"Redirect policy=final -> indexing final URL {index_url}")
                    else:
                        index_url = current_url

                    # Extract title
                    title = await page.title() or url

                    # Extract the most complete rendered HTML we can find.
                    html = await _extract_page_html(page)

                    content_md = _html_to_markdown(html) if html else ""
                    _debug(
                        f"Page title={title!r}; extracted {len(html)} HTML chars -> {len(content_md)} Markdown chars"
                    )

                    # Save to index
                    if index_url is None:
                        print("[crawl]   ↷ Skipped: redirect_policy=skip")
                    else:
                        upsert_page(index_file, index_url, title, content_md)
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
    if site.get("auth_required"):
        _authenticate_site(site, force=args.force_auth)

    # Then crawl
    try:
        crawl_completed = asyncio.run(
            crawl_site_headful(site, headless=args.headless, debug=args.debug)
        )
    except ConfigError as exc:
        print(f"[docmcp-crawl] Configuration error:\n{exc}", file=sys.stderr)
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
