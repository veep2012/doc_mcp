import os
import re
import sys
from pathlib import Path

import pytest
import yaml
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from src.index.store import get_page, list_pages

REPO_ROOT = Path(__file__).resolve().parents[2]
NEWSVL_INDEX = REPO_ROOT / "index" / "newsvl.ru.db"
MISSING_INDEX_MESSAGE = (
    f"Missing {NEWSVL_INDEX}. Regenerate it with "
    f"{REPO_ROOT / '.venv' / 'bin' / 'python'} crawl_cli.py --site newsvl.ru --headless"
)


def _pick_search_term() -> str:
    pages = list_pages(NEWSVL_INDEX)
    if not pages:
        pytest.fail(f"{MISSING_INDEX_MESSAGE}. The database exists but contains no indexed pages.")
    page = get_page(NEWSVL_INDEX, pages[0]["url"])
    assert page is not None
    for token in re.findall(r"\w{4,}", f"{page['title']} {page['content_md']}", flags=re.UNICODE):
        return token
    pytest.fail(f"{MISSING_INDEX_MESSAGE}. Could not derive a searchable term from the index.")


@pytest.mark.asyncio
@pytest.mark.smoke
@pytest.mark.mcp_smoke
async def test_mcp_smoke_search_docs_against_newsvl_index(tmp_path: Path) -> None:
    if not NEWSVL_INDEX.exists():
        pytest.fail(MISSING_INDEX_MESSAGE)

    search_term = _pick_search_term()
    config_path = tmp_path / "sites.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "sites": [
                    {
                        "name": "newsvl.ru",
                        "url": "https://newsvl.ru",
                        "auth_required": False,
                        "session_file": None,
                        "index_file": str(NEWSVL_INDEX),
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    server = StdioServerParameters(
        command=sys.executable,
        args=["-m", "src.main"],
        cwd=str(REPO_ROOT),
        env={**os.environ, "CONFIG_FILE": str(config_path), "PYTHONPATH": str(REPO_ROOT)},
    )

    async with stdio_client(server) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.call_tool(
                "search_docs",
                {"site_name": "newsvl.ru", "query": search_term, "limit": 3},
            )

    text = "\n".join(item.text for item in result.content if hasattr(item, "text"))
    assert search_term.lower() in text.lower()
