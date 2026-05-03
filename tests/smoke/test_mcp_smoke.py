import textwrap

import pytest

from docmcp.index_store import init_db, upsert_page
from tests.smoke.support import call_search_docs


@pytest.mark.smoke
@pytest.mark.mcp_smoke
async def test_mcp_stdio_search_docs_uses_prepared_index(tmp_path):
    runtime_root = tmp_path / "runtime"
    (runtime_root / "config").mkdir(parents=True)
    (runtime_root / "storage").mkdir()
    (runtime_root / "index").mkdir()

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
                index_file: "index/prepared.db"
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )

    response = await call_search_docs(runtime_root, "Prepared Docs", "Alpha")

    assert "Search results for 'Alpha' in 'Prepared Docs'" in response
    assert "Guide" in response
