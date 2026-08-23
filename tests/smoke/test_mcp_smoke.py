import json
import textwrap

import pytest

from docmcp.index_store import init_db, upsert_page
from smoke_support import (
    call_mcp_tool,
    call_search_docs,
    print_smoke_context,
    smoke_artifact_root,
    smoke_log_file,
)


@pytest.mark.smoke
@pytest.mark.mcp_smoke
async def test_mcp_stdio_search_docs_uses_prepared_index():
    runtime_root = smoke_artifact_root("mcp")

    index_file = runtime_root / "index" / "prepared.db"
    init_db(str(index_file))
    upsert_page(str(index_file), "https://example.test/guide", "Guide", "Alpha beta gamma")

    (runtime_root / "config" / "sites.yaml").write_text(
        textwrap.dedent(
            """
            sites:
              - name: "Prepared Docs"
                url: "https://example.test"
                auth_required: false
                session_file: null
                search_engine: keyword
                index_file: "index/prepared.db"
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )

    print_smoke_context(
        "mcp smoke",
        [
            ("site", "Prepared Docs"),
            ("runtime_root", str(runtime_root)),
            ("index_file", str(index_file)),
            ("log_file", str(smoke_log_file(runtime_root, "mcp.log"))),
        ],
    )

    with smoke_log_file(runtime_root, "mcp.log").open("w", encoding="utf-8") as mcp_log:
        response = await call_search_docs(
            runtime_root,
            "Prepared Docs",
            "Alpha",
            errlog=mcp_log,
        )

    payload = json.loads(response)
    assert payload["ok"] is True
    assert payload["contract_version"] == "1.0"
    assert payload["mode"] == "keyword"
    assert payload["vector_hits"] == 0
    assert payload["keyword_hits"] == 1
    assert payload["results"][0]["title"] == "Guide"
    assert payload["results"][0]["page_url"] == "https://example.test/guide"
    assert payload["results"][0]["source"] == "keyword"

    sites_payload = json.loads(await call_mcp_tool(runtime_root, "get_sites", {}))
    assert sites_payload["ok"] is True
    assert sites_payload["sites"][0]["name"] == "Prepared Docs"

    version_payload = json.loads(await call_mcp_tool(runtime_root, "get_version", {}))
    assert version_payload["ok"] is True
    assert version_payload["contract_version"] == "1.0"

    pages_payload = json.loads(
        await call_mcp_tool(
            runtime_root,
            "list_pages",
            {"site_name": "Prepared Docs"},
        )
    )
    assert pages_payload["ok"] is True
    assert pages_payload["pages"][0]["title"] == "Guide"

    page_payload = json.loads(
        await call_mcp_tool(
            runtime_root,
            "fetch_page",
            {"site_name": "Prepared Docs", "url": "https://example.test/guide"},
        )
    )
    assert page_payload["ok"] is True
    assert page_payload["page"]["content_md"] == "Alpha beta gamma"

    invalid_payload = json.loads(
        await call_mcp_tool(
            runtime_root,
            "search_docs",
            {"site_name": "Prepared Docs", "query": ""},
        )
    )
    assert invalid_payload["ok"] is False
    assert invalid_payload["error"]["code"] == "invalid_argument"

    missing_site_payload = json.loads(
        await call_mcp_tool(
            runtime_root,
            "search_docs",
            {"site_name": "Missing Docs", "query": "Alpha"},
        )
    )
    assert missing_site_payload["ok"] is False
    assert missing_site_payload["error"]["code"] == "site_not_found"
