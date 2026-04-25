"""
Headful Crawl CLI — authenticates (if needed) and crawls a documentation site
using a real Playwright browser, saving pages as Markdown to the SQLite index.

This bypasses crawl4ai entirely, avoiding anti-bot detection issues on SPAs.
Markdown conversion is done via markdownify on the inner page HTML.

Usage:
    docmcp-crawl --site "LD documentation"
    docmcp-crawl --site "LD documentation" --force-auth
    docmcp-crawl --site "LD documentation" --headless
    docmcp-crawl --list
"""

import argparse
import asyncio
import re
import sys
from collections import deque
from fnmatch import fnmatch
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlunparse

from dotenv import load_dotenv

from .auth.session import authenticate
from .config.loader import get_sites
from .index_store import init_db, upsert_page

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


def _normalize_url(url: str) -> str:
    """Strip fragments and query strings; normalize scheme/host to lowercase."""
    p = urlparse(url)
    path = p.path
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    return urlunparse((p.scheme.lower(), p.netloc.lower(), path, "", "", ""))


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


def _is_page_url(url: str) -> bool:
    """Return False if the URL points to a static asset (image, font, archive, etc.)."""
    path = urlparse(url).path.lower()
    ext = Path(path).suffix
    return ext not in _STATIC_EXTENSIONS


def _is_allowed(
    url: str, start_url: str, allow_patterns: list[str], deny_patterns: list[str]
) -> bool:
    """Return True if url should be crawled."""
    ps = urlparse(start_url)
    pu = urlparse(url)
    if pu.netloc != ps.netloc:
        return False
    start_path = ps.path.rstrip("/") or "/"
    if not pu.path.startswith(start_path):
        return False
    for pat in deny_patterns:
        if fnmatch(url, pat):
            return False
    if allow_patterns:
        return any(fnmatch(url, pat) for pat in allow_patterns)
    return True


def _html_to_markdown(html: str) -> str:
    """Convert HTML to Markdown, or fall back to stripping tags."""
    # Remove non-content blocks first so markdownify does not turn their inner text
    # into visible garbage in the indexed document.
    html = re.sub(r"<!--.*?-->", " ", html, flags=re.S)
    html = re.sub(
        r"<(script|style|noscript|template|head)\b.*?>.*?</\1>", " ", html, flags=re.S | re.I
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


def _extract_links(page_url: str, link_elements: list[dict]) -> list[tuple[str, bool]]:
    """Extract and normalize hrefs from Playwright link objects.

    Returns pairs of (normalized_url, is_anchor_link).
    """
    links = []
    for el in link_elements:
        href = el.get("href", "") or ""
        href = href.strip()
        if not href or href.startswith(("#", "mailto:", "javascript:")):
            continue
        absolute_url = urljoin(page_url, href)
        normalized_url = _normalize_url(absolute_url)
        is_anchor_link = "#" in absolute_url and normalized_url == _normalize_url(page_url)
        links.append((normalized_url, is_anchor_link))
    return links


# ---------------------------------------------------------------------------
# Core headful crawler
# ---------------------------------------------------------------------------


async def crawl_site_headful(site: dict, headless: bool = False) -> None:
    """
    Crawl a site using a real Playwright browser (headful by default).
    Uses the saved session from auth_cli.py, or prompts auth if missing.
    """
    from playwright.async_api import async_playwright

    name = site["name"]
    crawl_cfg = site.get("crawl", {})
    start_url = crawl_cfg.get("start_url", site["url"])
    max_depth = crawl_cfg.get("max_depth", 3)
    delay_seconds = crawl_cfg.get("delay_seconds", 1.0)
    allow_patterns = crawl_cfg.get("allow_patterns", [])
    deny_patterns = crawl_cfg.get("deny_patterns", [])
    block_images = crawl_cfg.get("block_images", False)
    ignore_anchor_links = crawl_cfg.get("ignore_anchor_links", True)
    ignore_https_errors = crawl_cfg.get("ignore_https_errors", False)
    index_file = site["index_file"]
    session_file = site.get("session_file")

    print(f"\n[crawl] Site     : {name}")
    print(f"[crawl] Start URL: {start_url}")
    print(f"[crawl] Max depth: {max_depth}")
    print(f"[crawl] Index    : {index_file}")

    init_db(index_file)

    # Login indicators used to detect redirect to auth page
    login_indicators = ["login", "signin", "sign-in", "/auth", "/sso"]

    visited: set[str] = set()
    queued: set[str] = {_normalize_url(start_url)}
    queue: deque[tuple[str, int]] = deque([(_normalize_url(start_url), 0)])
    page_count = 0

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
            while queue:
                depth = queue[0][1]
                level_total = sum(1 for _, item_depth in queue if item_depth == depth)
                level_number = depth + 1
                total_levels = max_depth + 1

                for index_in_level in range(1, level_total + 1):
                    url, item_depth = queue.popleft()
                    if item_depth != depth:
                        queue.appendleft((url, item_depth))
                        break
                    queued.discard(url)
                    if url in visited:
                        continue
                    visited.add(url)

                    print(
                        f"[crawl] [{index_in_level} of {level_total} level {level_number}/{total_levels}] {url}"
                    )

                    try:
                        await page.goto(url, wait_until="networkidle", timeout=60000)
                    except Exception as e:
                        print(f"[crawl]   ✗ Navigation error: {e}")
                        continue

                    current_url = _normalize_url(page.url)

                    # Detect redirect to login page
                    if any(ind in current_url for ind in login_indicators):
                        print("[crawl]   ✗ Redirected to login — session may be expired. Stopping.")
                        print(f'[crawl]   Run: docmcp-auth --site "{name}" --force')
                        stop_crawl = True
                        break

                    # Extract title
                    title = await page.title() or url

                    # Extract the most complete rendered HTML we can find.
                    html = await _extract_page_html(page)

                    content_md = _html_to_markdown(html) if html else ""

                    # Save to index
                    upsert_page(index_file, current_url, title, content_md)
                    page_count += 1
                    print(f"[crawl]   ✓ Indexed: {title[:70]}")

                    # Discover links for next depth
                    if depth < max_depth:
                        try:
                            anchors = await page.eval_on_selector_all(
                                "a[href]", "els => els.map(e => ({ href: e.href }))"
                            )
                            for href, is_anchor_link in _extract_links(current_url, anchors):
                                if ignore_anchor_links and is_anchor_link:
                                    continue
                                if (
                                    href not in visited
                                    and href not in queued
                                    and _is_page_url(href)
                                    and _is_allowed(href, start_url, allow_patterns, deny_patterns)
                                ):
                                    queue.append((href, depth + 1))
                                    queued.add(href)
                        except Exception as e:
                            print(f"[crawl]   ✗ Link extraction error: {e}")

                    await asyncio.sleep(delay_seconds)

                if stop_crawl:
                    break

        finally:
            await browser.close()

    print(f"\n[crawl] Done. {page_count} pages indexed → {index_file}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Headful browser crawler — authenticates and indexes a documentation site."
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
    parser.add_argument("--list", action="store_true", help="List all configured sites")
    args = parser.parse_args()

    if args.list:
        sites = get_sites()
        print("\nConfigured sites:")
        for s in sites:
            auth = "auth required" if s.get("auth_required") else "public"
            print(f"  - {s['name']} ({auth}) — {s['url']}")
        return

    if not args.site:
        parser.print_help()
        return

    sites = get_sites()
    site = next((s for s in sites if s["name"].lower() == args.site.lower()), None)
    if not site:
        print(f"[crawl] Site '{args.site}' not found. Use --list to see available sites.")
        sys.exit(1)

    # Authenticate first if required
    if site.get("auth_required"):
        asyncio.run(authenticate(site, force=args.force_auth))

    # Then crawl
    asyncio.run(crawl_site_headful(site, headless=args.headless))


if __name__ == "__main__":
    main()
