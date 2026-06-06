"""
MCP tool definitions — exposes documentation tools to AI clients via stdio MCP server.
Uses FastMCP (high-level API).

Tools:
  - search_docs   : full-text search across indexed pages
  - fetch_page    : retrieve a page by URL
  - list_pages    : list all indexed pages for a site
  - get_sites     : list all configured sites
  - get_version   : report the MCP server version
"""

import json
import os
import sqlite3

try:
    from mcp.server.fastmcp import FastMCP
except ModuleNotFoundError:  # pragma: no cover - only used in minimal test environments

    class FastMCP:  # type: ignore[too-many-ancestors]
        def __init__(self, name: str):
            self.name = name

        def tool(self):
            def decorator(func):
                return func

            return decorator

        def run(self, transport: str = "stdio"):
            raise ModuleNotFoundError("mcp is required to run the MCP server")


from . import __version__
from .config.loader import get_sites as _get_sites
from .index_store import count_pages, get_page, list_pages as _list_pages, search_pages
from .vector_index import VectorIndexError, search_vector_chunks

mcp = FastMCP(os.getenv("MCP_SERVER_NAME", "docs-mcp"))
_SEARCH_LIMIT_MAX = 100


def _find_site(name: str) -> dict | None:
    for site in _get_sites():
        if site["name"].lower() == name.lower():
            return site
    return None


def _empty_search_response() -> dict:
    return {"mode": "keyword", "vector_hits": 0, "keyword_hits": 0, "results": []}


def _site_not_found_search_response(site_name: str) -> dict:
    response = _empty_search_response()
    response["error"] = {
        "type": "site_not_found",
        "message": f"Site '{site_name}' not found.",
    }
    return response


def _keyword_score(rank: float | None, position: int) -> float:
    # FTS5 bm25() ranks are ordered best-to-worst by ascending value, and can be negative.
    # Use the returned position so the score stays monotonic with the result ordering.
    return round(1.0 / (position + 1), 6)


def _vector_score(distance: float | None) -> float:
    distance = max(distance or 0.0, 0.0)
    return round(1.0 / (1.0 + distance), 6)


def _normalize_search_limit(limit: int) -> int | None:
    if limit <= 0:
        return None
    return min(limit, _SEARCH_LIMIT_MAX)


def _normalize_result_text(text: str | None) -> str:
    return " ".join((text or "").split())


def _dedupe_keys(result: dict) -> tuple[str, ...]:
    page_url = result.get("page_url") or result.get("url") or ""
    text = _normalize_result_text(result.get("text") or result.get("excerpt"))
    keys = []
    if result.get("chunk_id"):
        keys.append(f"chunk:{result['chunk_id']}")
    keys.append(f"text:{page_url}\n{text}")
    return tuple(keys)


def _keyword_lookup(site: dict, query: str, limit: int) -> list[dict]:
    try:
        return search_pages(site["index_file"], query, limit)
    except sqlite3.Error:
        return []


def _vector_lookup(site: dict, query: str, limit: int) -> list[dict]:
    try:
        return search_vector_chunks(site, query, limit)
    except (sqlite3.Error, OSError, VectorIndexError):
        return []


def _normalize_keyword_results(results: list[dict]) -> list[dict]:
    return [
        {
            "text": result.get("excerpt") or "",
            "page_url": result["url"],
            "title": result.get("title") or "",
            "score": _keyword_score(result.get("rank"), index),
            "source": "keyword",
            "_dedupe_keys": _dedupe_keys(result),
        }
        for index, result in enumerate(results)
    ]


def _normalize_vector_results(results: list[dict]) -> list[dict]:
    return [
        {
            "text": result.get("text") or "",
            "page_url": result["page_url"],
            "title": result.get("title") or "",
            "score": _vector_score(result.get("distance")),
            "source": "vector",
            "_dedupe_keys": _dedupe_keys(result),
        }
        for result in results
    ]


def _merge_search_results(
    vector_results: list[dict], keyword_results: list[dict], limit: int
) -> tuple[list[dict], set[str]]:
    merged: list[dict] = []
    seen_keys: set[str] = set()
    contributors: set[str] = set()
    vector_pages: set[str] = set()

    for result in [*vector_results, *keyword_results]:
        dedupe_keys = result.get("_dedupe_keys", ())
        if result["source"] == "keyword" and result["page_url"] in vector_pages:
            continue
        if any(key in seen_keys for key in dedupe_keys):
            continue
        seen_keys.update(dedupe_keys)
        contributors.add(result["source"])
        if result["source"] == "vector":
            vector_pages.add(result["page_url"])
        merged.append(
            {
                "text": result["text"],
                "page_url": result["page_url"],
                "title": result["title"],
                "score": result["score"],
                "source": result["source"],
            }
        )
        if len(merged) >= limit:
            break

    return merged, contributors


def _select_search_mode(contributors: set[str]) -> str:
    if contributors == {"keyword", "vector"}:
        return "hybrid"
    if contributors == {"vector"}:
        return "vector"
    return "keyword"


def _search_response(keyword_results: list[dict], vector_results: list[dict], limit: int) -> dict:
    response = _empty_search_response()
    normalized_keyword_results = _normalize_keyword_results(keyword_results)
    normalized_vector_results = _normalize_vector_results(vector_results)
    merged_results, contributors = _merge_search_results(
        normalized_vector_results, normalized_keyword_results, limit
    )
    response["mode"] = _select_search_mode(contributors)
    response["vector_hits"] = len(vector_results)
    response["keyword_hits"] = len(keyword_results)
    response["results"] = merged_results
    return response


@mcp.tool()
def get_sites() -> str:
    """List all configured documentation sites and their index status."""
    sites = _get_sites()
    lines = ["## Configured Documentation Sites\n"]
    for site in sites:
        try:
            n = count_pages(site["index_file"])
            status = f"{n} pages indexed"
        except Exception as exc:
            status = f"ERROR: {type(exc).__name__}: {exc}"
        auth = "🔒 Auth required" if site.get("auth_required") else "🌐 Public"
        lines.append(f"- **{site['name']}** ({auth}) — {status}")
        lines.append(f"  URL: {site['url']}")
    return "\n".join(lines)


@mcp.tool()
def get_version() -> str:
    """Return the MCP server name and version."""
    payload = {
        "server_name": os.getenv("MCP_SERVER_NAME", "docs-mcp"),
        "package_name": "doc-mcp",
        "version": __version__,
    }
    return json.dumps(payload, indent=2, sort_keys=True)


@mcp.tool()
def list_pages(site_name: str) -> str:
    """List all indexed pages for a documentation site.

    Args:
        site_name: Name of the site as configured in sites.yaml
    """
    site = _find_site(site_name)
    if not site:
        return f"Site '{site_name}' not found."
    pages = _list_pages(site["index_file"])
    if not pages:
        return f"No pages indexed for '{site_name}'. Run docmcp-crawl first."
    lines = [f"## Pages in '{site_name}' ({len(pages)} total)"]
    lines.append(f"Index: {site['index_file']}\n")
    for p in pages:
        lines.append(f"- [{p['title']}]({p['url']})  _(last crawled: {p['last_crawled']})_")
    return "\n".join(lines)


@mcp.tool()
def search_docs(site_name: str, query: str, limit: int = 10) -> str:
    """Full-text search across indexed documentation pages.

    Args:
        site_name: Name of the site to search
        query: Search query string
        limit: Maximum number of results (default: 10)
    """
    site = _find_site(site_name)
    if not site:
        return json.dumps(_site_not_found_search_response(site_name), indent=2)
    normalized_limit = _normalize_search_limit(limit)
    if normalized_limit is None:
        return json.dumps(_empty_search_response(), indent=2)
    keyword_results = _keyword_lookup(site, query, normalized_limit)
    vector_results = _vector_lookup(site, query, normalized_limit)
    return json.dumps(_search_response(keyword_results, vector_results, normalized_limit), indent=2)


@mcp.tool()
def fetch_page(site_name: str, url: str) -> str:
    """Fetch the full Markdown content of a documentation page by URL.

    Args:
        site_name: Name of the site
        url: Full URL of the page to fetch
    """
    site = _find_site(site_name)
    if not site:
        return f"Site '{site_name}' not found."
    page = get_page(site["index_file"], url)
    if not page:
        return f"Page not found in index: {url}"
    return f"# {page['title']}\n\n{page['content_md']}"
