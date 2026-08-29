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

import base64
import binascii
import json
import logging
import os
import sqlite3
from pathlib import Path
from urllib.parse import quote, unquote
from unicodedata import normalize

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

        def resource(self, uri: str, **kwargs):
            def decorator(func):
                return func

            return decorator

        def run(self, transport: str = "stdio"):
            raise ModuleNotFoundError("mcp is required to run the MCP server")


from . import __version__
from .config.loader import (
    ConfigError,
    find_site,
    get_sites as _get_sites,
    _normalize_search_engine,
)
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


class _ConfigurationUnavailableError(RuntimeError):
    """Internal marker for configuration failures crossing the MCP tool boundary."""


def _load_sites() -> list[dict]:
    try:
        return _get_sites()
    except ConfigError as exc:
        logger.warning("Could not load site configuration: %s", exc, exc_info=True)
        raise _ConfigurationUnavailableError from exc


def _find_site(name: str) -> dict | None:
    return find_site(_load_sites(), name)


def _page_key_from_url(url: str) -> str:
    """Encode a canonical page URL as one URI-safe resource path segment."""
    return quote(normalize("NFC", url), safe="")


def _page_resource_uri(site: dict, url: str) -> str:
    return f"docmcp://site/{site['site_id']}/page/{_page_key_from_url(url)}"


_LIST_PAGES_LIMIT_MAX = 100


def _encode_pages_cursor(site: dict, page: dict) -> str:
    payload = json.dumps(
        {"site_id": site["site_id"], "title": page["title"], "url": page["url"]},
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def _decode_pages_cursor(site: dict, cursor: str) -> tuple[str, str] | None:
    allowed_chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
    if not _valid_nonempty_text(cursor) or any(char not in allowed_chars for char in cursor):
        return None
    try:
        padding = "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(cursor + padding).decode("utf-8"))
    except (ValueError, UnicodeDecodeError, binascii.Error):
        return None
    if not isinstance(payload, dict) or payload.get("site_id") != site.get("site_id"):
        return None
    title, url = payload.get("title"), payload.get("url")
    if not isinstance(title, str) or not isinstance(url, str) or not title or not url:
        return None
    return title, url


def _decode_page_key(page_key: str) -> str | None:
    if not _valid_nonempty_text(page_key):
        return None
    decoded = unquote(page_key)
    if quote(decoded, safe="") != page_key:
        return None
    return decoded


def _find_site_by_id(site_id: str) -> dict | None:
    return next((site for site in _load_sites() if site["site_id"] == site_id), None)


def _resource_site_or_error(site_id: str) -> dict:
    try:
        site = _find_site_by_id(site_id)
    except _ConfigurationUnavailableError as exc:
        raise ValueError("Server configuration is unavailable.") from exc
    if not site:
        raise ValueError("Documentation site resource was not found.")
    return site


def _site_index_metadata(site: dict) -> dict[str, int | str | None]:
    """Return the compact public index metadata shared by site disclosures."""
    if not Path(site["index_file"]).is_file():
        return {"status": "unavailable", "page_count": None}
    try:
        return {"status": "ready", "page_count": count_pages(site["index_file"])}
    except (OSError, sqlite3.Error):
        logger.warning("Could not read index status for site %r", site["name"], exc_info=True)
        return {"status": "unavailable", "page_count": None}


@mcp.resource(
    "docmcp://sites",
    name="Documentation sites",
    description="Configured documentation sites.",
    mime_type="text/markdown",
)
def documentation_sites_resource() -> str:
    """Return the configured documentation catalog without private settings."""
    try:
        sites = _load_sites()
    except _ConfigurationUnavailableError as exc:
        raise ValueError("Server configuration is unavailable.") from exc
    lines = ["# Documentation sites", ""]
    lines.extend(
        f"- {json.dumps(site['name'], ensure_ascii=False)}: " f"<docmcp://site/{site['site_id']}>"
        for site in sites
    )
    return "\n".join(lines)


@mcp.resource(
    "docmcp://site/{site_id}",
    name="Documentation site",
    description="A configured documentation site.",
    mime_type="text/markdown",
)
def documentation_site_resource(site_id: str) -> str:
    """Return compact public metadata for one configured documentation site."""
    site = _resource_site_or_error(site_id)
    index = _site_index_metadata(site)
    page_count = index["page_count"] if index["page_count"] is not None else "unknown"
    return "\n".join(
        [
            "# Documentation site",
            "",
            f"Site name: {json.dumps(site['name'], ensure_ascii=False)}",
            f"Page count: {page_count}",
            f"Crawl/index status: {index['status']}",
            "",
            f"Page URI template: `docmcp://site/{site['site_id']}/page/{{page_key}}`",
            "",
            f"Page catalog: call `list_pages` with site_name={json.dumps(site['name'], ensure_ascii=False)}.",
        ]
    )


@mcp.resource(
    "docmcp://site/{site_id}/page/{page_key}",
    name="Documentation page",
    description="An indexed documentation page in Markdown.",
    mime_type="text/markdown",
)
def documentation_page_resource(site_id: str, page_key: str) -> str:
    """Return one indexed page after strict resource-URI validation."""
    site = _resource_site_or_error(site_id)
    page_url = _decode_page_key(page_key)
    if page_url is None:
        raise ValueError("Documentation page resource URI is malformed.")
    if not Path(site["index_file"]).is_file():
        raise ValueError("Documentation page resource is unavailable.")
    try:
        page = get_page(site["index_file"], page_url)
    except (OSError, sqlite3.Error) as exc:
        logger.warning("Could not read page resource for site %r", site["name"], exc_info=True)
        raise ValueError("Documentation page resource is unavailable.") from exc
    if not page:
        raise ValueError("Documentation page resource was not found.")
    return page["content_md"]


def _configuration_error_response() -> dict:
    return _tool_error("configuration_unavailable", "Server configuration is unavailable.")


def _configuration_search_error_response() -> dict:
    return _search_error_response(
        "keyword", "configuration_unavailable", "Server configuration is unavailable."
    )


def _site_search_engine(site: dict) -> str:
    return _normalize_search_engine(site.get("search_engine"), site.get("name"))


def _emit_observation(event: str, **fields) -> None:
    payload = {"event": event, **fields}
    obs_logger.info(json.dumps(payload, sort_keys=True, default=str))


CONTRACT_VERSION = "1.1"

_VECTOR_ERROR_MESSAGES = {
    "vector_index_missing": "Vector search index is missing.",
    "vector_index_unreadable": "Vector search index could not be read.",
    "vector_index_stale": "Vector search index is stale.",
    "vector_index_schema_mismatch": "Vector search index schema is incompatible.",
    "vector_index_incompatible": "Vector search index is incompatible.",
    "vector_backend_unavailable": "Vector search backend is unavailable.",
}


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
    return search_pages(site["index_file"], query, limit)


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
    if exc is None:
        return {
            "type": "vector_index_missing",
            "message": _VECTOR_ERROR_MESSAGES["vector_index_missing"],
        }
    if isinstance(exc, VectorBackendUnavailableError):
        error_type = "vector_backend_unavailable"
    elif isinstance(exc, VectorSidecarStaleError):
        error_type = "vector_index_stale"
    elif isinstance(exc, VectorSidecarSchemaMismatchError):
        error_type = "vector_index_schema_mismatch"
    elif isinstance(exc, VectorSidecarIncompatibleError):
        error_type = "vector_index_incompatible"
    else:
        error_type = "vector_index_unreadable"

    # Keep the complete exception, including sensitive diagnostics, in server logs only.
    logger.warning(
        "Vector lookup failed for site %r at %r: %s",
        site.get("name"),
        vector_index_file,
        exc,
        exc_info=(type(exc), exc, exc.__traceback__),
    )
    return {"type": error_type, "message": _VECTOR_ERROR_MESSAGES[error_type]}


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


def _normalize_keyword_results(results: list[dict], site: dict | None = None) -> list[dict]:
    normalized_results = [
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
    if site and site.get("site_id"):
        for result in normalized_results:
            result["resource_uri"] = _page_resource_uri(site, result["page_url"])
    return normalized_results


def _normalize_vector_results(results: list[dict], site: dict | None = None) -> list[dict]:
    normalized_results = [
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
    if site and site.get("site_id"):
        for result in normalized_results:
            result["resource_uri"] = _page_resource_uri(site, result["page_url"])
    return normalized_results


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
                **({"resource_uri": result["resource_uri"]} if "resource_uri" in result else {}),
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
    keyword_results: list[dict],
    vector_results: list[dict],
    limit: int,
    error: dict | None = None,
    *,
    site: dict | None = None,
) -> dict:
    response = _empty_search_response()
    normalized_keyword_results = _normalize_keyword_results(keyword_results, site)
    normalized_vector_results = _normalize_vector_results(vector_results, site)
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
    try:
        keyword_results = _keyword_lookup(site, query, limit)
    except sqlite3.Error:
        return _search_error_response(
            "keyword",
            "index_unavailable",
            f"The index for '{site['name']}' is unavailable.",
        )
    response = _empty_search_response("keyword")
    response["keyword_hits"] = len(keyword_results)
    response["results"] = _public_search_results(_normalize_keyword_results(keyword_results, site))
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
        response["results"] = _public_search_results(
            _normalize_vector_results(vector_results, site)
        )
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
    response["results"] = _public_search_results(_normalize_keyword_results(keyword_results, site))
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


def _degraded_search_response(site: dict) -> dict:
    """Preserve search semantics when a site's source index cannot be read."""
    logger.warning("Could not search unavailable index for site %r", site["name"])
    return _empty_search_response()


@mcp.tool()
def get_sites() -> str:
    """List configured sites as a JSON contract with their index status."""
    try:
        sites = _load_sites()
    except _ConfigurationUnavailableError:
        return _serialize(_configuration_error_response())
    result = []
    for site in sites:
        index = _site_index_metadata(site)
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
def list_pages(site_name: str, limit: int = 100, cursor: str | None = None) -> str:
    """List all indexed pages for a documentation site.

    Args:
        site_name: Name of the site as configured in sites.yaml
        limit: Maximum number of pages to return (default: 100, maximum: 100)
        cursor: Opaque cursor returned by a previous call
    """
    if not _valid_nonempty_text(site_name):
        return _serialize(_tool_error("invalid_argument", "site_name must be a non-empty string."))
    if (
        isinstance(limit, bool)
        or not isinstance(limit, int)
        or not 0 < limit <= _LIST_PAGES_LIMIT_MAX
    ):
        return _serialize(
            _tool_error("invalid_argument", "limit must be an integer from 1 to 100.")
        )
    try:
        site = _find_site(site_name)
    except _ConfigurationUnavailableError:
        return _serialize(_configuration_error_response())
    if not site:
        return _serialize(_tool_error("site_not_found", f"Site '{site_name}' not found."))
    if not Path(site["index_file"]).is_file():
        return _serialize(
            _tool_error("index_unavailable", f"The index for '{site['name']}' is unavailable.")
        )
    after = None if cursor is None else _decode_pages_cursor(site, cursor)
    if cursor is not None and after is None:
        return _serialize(_tool_error("invalid_argument", "cursor is invalid for this site."))
    try:
        pages = _list_pages(site["index_file"], limit=limit + 1, after=after)
    except (OSError, sqlite3.Error):
        logger.warning("Could not list pages for site %r", site["name"], exc_info=True)
        return _serialize(
            _tool_error("index_unavailable", f"The index for '{site['name']}' is unavailable.")
        )
    has_more = len(pages) > limit
    pages = pages[:limit]
    if not pages:
        return _serialize(_tool_success(site_name=site["name"], pages=[]))
    response = _tool_success(
        site_name=site["name"],
        pages=[
            {
                "title": page["title"],
                "url": page["url"],
                "resource_uri": _page_resource_uri(site, page["url"]),
                "last_crawled": page["last_crawled"],
            }
            for page in pages
        ],
    )
    if has_more:
        response["nextCursor"] = _encode_pages_cursor(site, pages[-1])
    return _serialize(response)


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
    try:
        site = _find_site(site_name)
    except _ConfigurationUnavailableError:
        return _serialize(_configuration_search_error_response())
    if not site:
        return _serialize(_site_not_found_search_response(site_name))
    if not Path(site["index_file"]).is_file():
        return _serialize(_degraded_search_response(site))
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
        try:
            return _serialize(_vector_search_response(site, query, normalized_limit))
        except sqlite3.Error:
            return _serialize(_degraded_search_response(site))

    try:
        keyword_results = _keyword_lookup(site, query, normalized_limit)
    except sqlite3.Error:
        return _serialize(_degraded_search_response(site))
    vector_results, error = _vector_lookup(site, query, normalized_limit)
    response = _search_response(keyword_results, vector_results, normalized_limit, error, site=site)
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
    try:
        site = _find_site(site_name)
    except _ConfigurationUnavailableError:
        return _serialize(_configuration_error_response())
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
        response = _tool_error(
            "page_not_found",
            f"Page not found in index: {url}",
            site_name=site["name"],
            url=url,
            page=None,
        )
        response["error"]["type"] = "page_not_found"
        return _serialize(response)
    return _serialize(
        _tool_success(
            site_name=site["name"],
            page={"title": page["title"], "url": url, "content_md": page["content_md"]},
        )
    )
