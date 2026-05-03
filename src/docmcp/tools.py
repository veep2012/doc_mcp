"""
MCP tool definitions — exposes documentation tools to AI clients via stdio MCP server.
Uses FastMCP (high-level API).

Tools:
  - search_docs   : full-text search across indexed pages
  - fetch_page    : retrieve a page by URL
  - list_pages    : list all indexed pages for a site
  - get_sites     : list all configured sites
"""

from mcp.server.fastmcp import FastMCP

import os

from .config.loader import get_sites as _get_sites
from .index_store import count_pages, get_page, list_pages as _list_pages, search_pages

mcp = FastMCP(os.getenv("MCP_SERVER_NAME", "docs-mcp"))


def _find_site(name: str) -> dict | None:
    for site in _get_sites():
        if site["name"].lower() == name.lower():
            return site
    return None


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
        return f"Site '{site_name}' not found."
    results = search_pages(site["index_file"], query, limit)
    if not results:
        return f"No results found for '{query}' in '{site_name}'."
    lines = [f"## Search results for '{query}' in '{site_name}'\n"]
    for r in results:
        lines.append(f"### [{r['title']}]({r['url']})")
        lines.append(f"{r['excerpt']}\n")
    return "\n".join(lines)


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
