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
import logging
import os
import re
import sqlite3
from pathlib import Path

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
from .config.loader import get_sites as _get_sites, _normalize_search_engine
from .index_store import (
    _normalize_search_limit,
    count_pages,
    get_page,
    list_pages as _list_pages,
    search_pages,
)
from .vector_index import (
    VectorBackendUnavailableError,
    VectorIndexError,
    VectorSidecarIncompatibleError,
    VectorSidecarStaleError,
    VectorSidecarSchemaMismatchError,
    _age_seconds_from_timestamp,
    _source_index_fingerprint,
    resolve_vector_index_file,
    search_vector_chunks,
)

mcp = FastMCP(os.getenv("MCP_SERVER_NAME", "docs-mcp"))
logger = logging.getLogger("docmcp.tools")
obs_logger = logging.getLogger("docmcp.observability")


def _find_site(name: str) -> dict | None:
    for site in _get_sites():
        if site["name"].lower() == name.lower():
            return site
    return None


def _site_search_engine(site: dict) -> str:
    return _normalize_search_engine(site.get("search_engine"), site.get("name"))


def _emit_observation(event: str, **fields) -> None:
    payload = {"event": event, **fields}
    obs_logger.info(json.dumps(payload, sort_keys=True, default=str))


CONTRACT_VERSION = "1.0"


def _tool_success(**fields) -> dict:
    """Return the shared public MCP success envelope."""
    return {"ok": True, "contract_version": CONTRACT_VERSION, **fields}


def _tool_error(code: str, message: str, **fields) -> dict:
    """Return a safe, actionable error without implementation details."""
    error = {"code": code, "message": message}
    return {"ok": False, "contract_version": CONTRACT_VERSION, **fields, "error": error}


def _serialize(payload: dict) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)


def _valid_nonempty_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _empty_search_response(mode: str = "keyword") -> dict:
    return {
        "ok": True,
        "contract_version": CONTRACT_VERSION,
        "mode": mode,
        "vector_hits": 0,
        "keyword_hits": 0,
        "results": [],
    }


def _search_error_response(mode: str, error_type: str, message: str) -> dict:
    response = _empty_search_response(mode)
    response["ok"] = False
    response["contract_version"] = CONTRACT_VERSION
    # ``type`` is retained for the pre-contract search clients.
    response["error"] = {"code": error_type, "type": error_type, "message": message}
    return response


def _site_not_found_search_response(site_name: str) -> dict:
    return _search_error_response("keyword", "site_not_found", f"Site '{site_name}' not found.")


def _keyword_score(rank: float | None, position: int) -> float:
    # FTS5 bm25() ranks are ordered best-to-worst by ascending value, and can be negative.
    # Use the returned position so the score stays monotonic with the result ordering.
    return round(1.0 / (position + 1), 6)


def _vector_score(distance: float | None) -> float:
    distance = max(distance or 0.0, 0.0)
    return round(1.0 / (1.0 + distance), 6)


def _normalize_result_text(text: str | None) -> str:
    """Collapse result text to a stable single-space form for deduplication."""
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


def _vector_index_observation(site: dict) -> dict[str, int | float | None]:
    index_file = site.get("index_file")
    if not index_file:
        return {"index_doc_count": None, "index_age": None}

    snapshot = _source_index_fingerprint(index_file)
    if snapshot is None:
        return {"index_doc_count": None, "index_age": None}

    index_doc_count, source_max_last_crawled, _ = snapshot
    return {
        "index_doc_count": index_doc_count,
        "index_age": _age_seconds_from_timestamp(source_max_last_crawled),
    }


def _log_vector_path_decision(
    *,
    site: dict | None,
    search_engine: str,
    vector_search_used: bool,
    fallback_reason: str | None,
    mode: str,
    vector_hits: int,
    keyword_hits: int,
) -> None:
    payload = {
        "site_name": site["name"] if site else None,
        "search_engine": search_engine,
        "vector_search_used": vector_search_used,
        "fallback_reason": fallback_reason,
        "mode": mode,
        "vector_hits": vector_hits,
        "keyword_hits": keyword_hits,
    }
    payload.update(
        _vector_index_observation(site) if site else {"index_doc_count": None, "index_age": None}
    )
    _emit_observation("vector_path_decision", **payload)


def _vector_lookup_error(site: dict, vector_index_file: str, exc: Exception | None = None) -> dict:
    def safe_detail(default: str) -> str:
        detail = str(exc).rstrip(".") if exc else ""
        if not detail:
            return default
        return re.sub(r"(?<![A-Za-z0-9])(?:/|[A-Za-z]:[\\/])[^\s)]+", "<path>", detail)

    if exc is None:
        return {
            "type": "vector_index_missing",
            "message": f"Vector search is enabled for '{site['name']}' but the sidecar is missing.",
        }
    if isinstance(exc, VectorBackendUnavailableError):
        return {
            "type": "vector_backend_unavailable",
            "message": safe_detail("Vector search backend is unavailable."),
        }
    if isinstance(exc, VectorSidecarStaleError):
        return {"type": "vector_index_stale", "message": safe_detail("Vector sidecar is stale.")}
    if isinstance(exc, VectorSidecarSchemaMismatchError):
        return {
            "type": "vector_index_schema_mismatch",
            "message": safe_detail("Vector sidecar schema is incompatible."),
        }
    if isinstance(exc, VectorSidecarIncompatibleError):
        return {
            "type": "vector_index_incompatible",
            "message": safe_detail("Vector sidecar is incompatible."),
        }
    # Preserve useful diagnostic wording while removing filesystem paths and other
    # implementation details from the client-facing contract.
    exc_text = safe_detail("")
    exc_detail = f" ({exc_text})" if exc_text else ""
    return {
        "type": "vector_index_unreadable",
        "message": f"Vector sidecar for '{site['name']}' is unreadable{exc_detail}.",
    }


def _vector_lookup(site: dict, query: str, limit: int) -> tuple[list[dict], dict | None]:
    vector_index_file = resolve_vector_index_file(site)
    if not Path(vector_index_file).exists():
        error = _vector_lookup_error(site, vector_index_file)
        logger.warning(
            "Hybrid search degraded to keyword for site %r because %s: %s",
            site["name"],
            error["type"],
            error["message"],
        )
        return [], error
    try:
        return search_vector_chunks(site, query, limit), None
    except (sqlite3.Error, OSError, VectorIndexError) as exc:
        error = _vector_lookup_error(site, vector_index_file, exc)
        logger.warning(
            "Hybrid search degraded to keyword for site %r because %s: %s",
            site["name"],
            error["type"],
            error["message"],
        )
        return [], error


def _vector_lookup_strict(site: dict, query: str, limit: int) -> tuple[list[dict], dict | None]:
    vector_index_file = resolve_vector_index_file(site)
    if not Path(vector_index_file).exists():
        return [], _vector_lookup_error(site, vector_index_file)

    try:
        return search_vector_chunks(site, query, limit), None
    except VectorBackendUnavailableError as exc:
        return [], _vector_lookup_error(site, vector_index_file, exc)
    # VectorSidecarStaleError and VectorSidecarIncompatibleError inherit from VectorIndexError,
    # so they intentionally flow through this shared fallback branch for consistent classification.
    except (sqlite3.Error, OSError, VectorIndexError) as exc:
        return [], _vector_lookup_error(site, vector_index_file, exc)


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


def _public_search_results(results: list[dict]) -> list[dict]:
    return [
        {key: value for key, value in result.items() if key != "_dedupe_keys"} for result in results
    ]


def _search_result_sort_key(result: dict) -> tuple[float, int, str, str, str]:
    source_priority = 0 if result.get("source") == "vector" else 1
    return (
        -float(result.get("score") or 0.0),
        source_priority,
        result.get("page_url") or "",
        result.get("title") or "",
        result.get("text") or "",
    )


def _merge_search_results(
    vector_results: list[dict], keyword_results: list[dict], limit: int
) -> tuple[list[dict], set[str]]:
    merged: list[dict] = []
    seen_keys: set[str] = set()
    contributors: set[str] = set()

    for result in [*vector_results, *keyword_results]:
        dedupe_keys = result.get("_dedupe_keys", ())
        if any(key in seen_keys for key in dedupe_keys):
            continue
        seen_keys.update(dedupe_keys)
        contributors.add(result["source"])
        merged.append(
            {
                "text": result["text"],
                "page_url": result["page_url"],
                "title": result["title"],
                "score": result["score"],
                "source": result["source"],
            }
        )

    merged.sort(key=_search_result_sort_key)
    return merged[:limit], contributors


def _select_search_mode(contributors: set[str]) -> str:
    if contributors == {"keyword", "vector"}:
        return "hybrid"
    if contributors == {"vector"}:
        return "vector"
    return "keyword"


def _search_response(
    keyword_results: list[dict], vector_results: list[dict], limit: int, error: dict | None = None
) -> dict:
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
    if error:
        response["ok"] = False
        response["contract_version"] = CONTRACT_VERSION
        response["error"] = {"code": error["type"], **error}
    return response


def _keyword_search_response(site: dict, query: str, limit: int) -> dict:
    keyword_results = _keyword_lookup(site, query, limit)
    response = _empty_search_response("keyword")
    response["keyword_hits"] = len(keyword_results)
    response["results"] = _public_search_results(_normalize_keyword_results(keyword_results))
    _log_vector_path_decision(
        site=site,
        search_engine=_site_search_engine(site),
        vector_search_used=False,
        fallback_reason="search_engine_keyword",
        mode=response["mode"],
        vector_hits=response["vector_hits"],
        keyword_hits=response["keyword_hits"],
    )
    return response


def _vector_search_response(site: dict, query: str, limit: int) -> dict:
    vector_results, error = _vector_lookup_strict(site, query, limit)
    if vector_results:
        response = _empty_search_response("vector")
        response["vector_hits"] = len(vector_results)
        response["results"] = _public_search_results(_normalize_vector_results(vector_results))
        _log_vector_path_decision(
            site=site,
            search_engine=_site_search_engine(site),
            vector_search_used=True,
            fallback_reason=None,
            mode=response["mode"],
            vector_hits=response["vector_hits"],
            keyword_hits=response["keyword_hits"],
        )
        return response

    keyword_results = _keyword_lookup(site, query, limit)
    response = _empty_search_response("keyword")
    response["keyword_hits"] = len(keyword_results)
    response["results"] = _public_search_results(_normalize_keyword_results(keyword_results))
    if error:
        response["ok"] = False
        response["contract_version"] = CONTRACT_VERSION
        response["error"] = {"code": error["type"], **error}
    _log_vector_path_decision(
        site=site,
        search_engine=_site_search_engine(site),
        vector_search_used=False,
        fallback_reason=error["type"] if error else "vector_empty",
        mode=response["mode"],
        vector_hits=response["vector_hits"],
        keyword_hits=response["keyword_hits"],
    )
    return response


def _limit_error_mode(search_engine: str) -> str:
    return "vector" if search_engine == "vector" else "keyword"


@mcp.tool()
def get_sites() -> str:
    """List configured sites as a JSON contract with their index status."""
    sites = _get_sites()
    result = []
    for site in sites:
        if not Path(site["index_file"]).is_file():
            result.append(
                {
                    "name": site["name"],
                    "url": site["url"],
                    "auth_required": bool(site.get("auth_required")),
                    "index": {"status": "unavailable", "page_count": None},
                }
            )
            continue
        try:
            n = count_pages(site["index_file"])
            index = {"status": "ready", "page_count": n}
        except (OSError, sqlite3.Error):
            logger.warning("Could not read index status for site %r", site["name"], exc_info=True)
            index = {"status": "unavailable", "page_count": None}
        result.append(
            {
                "name": site["name"],
                "url": site["url"],
                "auth_required": bool(site.get("auth_required")),
                "index": index,
            }
        )
    return _serialize(_tool_success(sites=result))


@mcp.tool()
def get_version() -> str:
    """Return the MCP server name and version."""
    payload = _tool_success(
        server_name=os.getenv("MCP_SERVER_NAME", "docs-mcp"),
        package_name="doc-mcp",
        version=__version__,
    )
    return _serialize(payload)


@mcp.tool()
def list_pages(site_name: str) -> str:
    """List all indexed pages for a documentation site.

    Args:
        site_name: Name of the site as configured in sites.yaml
    """
    if not _valid_nonempty_text(site_name):
        return _serialize(_tool_error("invalid_argument", "site_name must be a non-empty string."))
    site = _find_site(site_name)
    if not site:
        return _serialize(_tool_error("site_not_found", f"Site '{site_name}' not found."))
    if not Path(site["index_file"]).is_file():
        return _serialize(
            _tool_error("index_unavailable", f"The index for '{site['name']}' is unavailable.")
        )
    try:
        pages = _list_pages(site["index_file"])
    except (OSError, sqlite3.Error):
        logger.warning("Could not list pages for site %r", site["name"], exc_info=True)
        return _serialize(
            _tool_error("index_unavailable", f"The index for '{site['name']}' is unavailable.")
        )
    if not pages:
        return _serialize(_tool_success(site_name=site["name"], pages=[]))
    return _serialize(
        _tool_success(
            site_name=site["name"],
            pages=[
                {"title": page["title"], "url": page["url"], "last_crawled": page["last_crawled"]}
                for page in pages
            ],
        )
    )


@mcp.tool()
def search_docs(site_name: str, query: str, limit: int = 10) -> str:
    """Full-text search across indexed documentation pages.

    Args:
        site_name: Name of the site to search
        query: Search query string
        limit: Maximum number of results (default: 10)
    """
    if not _valid_nonempty_text(site_name):
        return _serialize(
            _search_error_response(
                "keyword", "invalid_argument", "site_name must be a non-empty string."
            )
        )
    if not _valid_nonempty_text(query):
        return _serialize(
            _search_error_response(
                "keyword", "invalid_argument", "query must be a non-empty string."
            )
        )
    site = _find_site(site_name)
    if not site:
        return _serialize(_site_not_found_search_response(site_name))
    if not Path(site["index_file"]).is_file():
        return _serialize(
            _search_error_response(
                _limit_error_mode(_site_search_engine(site)),
                "index_unavailable",
                f"The index for '{site['name']}' is unavailable.",
            )
        )
    search_engine = _site_search_engine(site)
    normalized_limit = _normalize_search_limit(limit)
    if normalized_limit is None:
        return _serialize(
            _search_error_response(
                _limit_error_mode(search_engine),
                "invalid_argument",
                "limit must be a positive integer.",
            )
        )
    if search_engine == "keyword":
        return _serialize(_keyword_search_response(site, query, normalized_limit))
    if search_engine == "vector":
        return _serialize(_vector_search_response(site, query, normalized_limit))

    keyword_results = _keyword_lookup(site, query, normalized_limit)
    vector_results, error = _vector_lookup(site, query, normalized_limit)
    response = _search_response(keyword_results, vector_results, normalized_limit, error)
    _log_vector_path_decision(
        site=site,
        search_engine=search_engine,
        vector_search_used=bool(vector_results),
        fallback_reason=error["type"] if error and not vector_results else None,
        mode=response["mode"],
        vector_hits=response["vector_hits"],
        keyword_hits=response["keyword_hits"],
    )
    return _serialize(response)


@mcp.tool()
def fetch_page(site_name: str, url: str) -> str:
    """Fetch the full Markdown content of a documentation page by URL.

    Args:
        site_name: Name of the site
        url: Full URL of the page to fetch
    """
    if not _valid_nonempty_text(site_name):
        return _serialize(_tool_error("invalid_argument", "site_name must be a non-empty string."))
    if not _valid_nonempty_text(url):
        return _serialize(_tool_error("invalid_argument", "url must be a non-empty string."))
    site = _find_site(site_name)
    if not site:
        return _serialize(_tool_error("site_not_found", f"Site '{site_name}' not found."))
    if not Path(site["index_file"]).is_file():
        return _serialize(
            _tool_error("index_unavailable", f"The index for '{site['name']}' is unavailable.")
        )
    try:
        page = get_page(site["index_file"], url)
    except (OSError, sqlite3.Error):
        logger.warning("Could not fetch page for site %r", site["name"], exc_info=True)
        return _serialize(
            _tool_error("index_unavailable", f"The index for '{site['name']}' is unavailable.")
        )
    if not page:
        return _serialize(
            _tool_error("page_not_found", f"Page '{url}' was not found for '{site['name']}'.")
        )
    return _serialize(
        _tool_success(
            site_name=site["name"],
            page={"title": page["title"], "url": url, "content_md": page["content_md"]},
        )
    )
