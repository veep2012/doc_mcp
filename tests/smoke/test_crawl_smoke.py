import textwrap
import sys
from pathlib import Path

import pytest

from docmcp.index_store import count_pages, list_pages
from tests.smoke.support import running_static_site, run_checked, smoke_env

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.smoke
@pytest.mark.crawl_smoke
def test_crawl_cli_indexes_containerized_static_site(tmp_path):
    site_root = tmp_path / "site"
    (site_root / "docs").mkdir(parents=True)
    (site_root / "index.html").write_text(
        "<!doctype html><html><head><title>Home</title></head><body><main><h1>Home</h1><p>Welcome.</p>"
        '<a href="/docs/guide.html">Guide</a></main></body></html>',
        encoding="utf-8",
    )
    (site_root / "docs" / "guide.html").write_text(
        "<!doctype html><html><head><title>Guide</title></head><body><main><h1>Guide</h1><p>Alpha beta smoke content.</p>"
        '<a href="/index.html">Home</a></main></body></html>',
        encoding="utf-8",
    )

    runtime_root = tmp_path / "runtime"
    (runtime_root / "config").mkdir(parents=True)
    (runtime_root / "storage").mkdir()
    (runtime_root / "index").mkdir()

    with running_static_site(site_root) as base_url:
        (runtime_root / "config" / "sites.yaml").write_text(
            textwrap.dedent(
                f"""
                sites:
                  - name: "Smoke Docs"
                    url: "{base_url}"
                    auth_required: false
                    session_file: null
                    crawl:
                      start_url: "{base_url}"
                      max_depth: 2
                      delay_seconds: 0
                      allow_patterns:
                        - "{base_url}*"
                      deny_patterns: []
                      block_images: true
                      ignore_anchor_links: true
                      ignore_https_errors: false
                    index_file: "index/smoke.db"
                """
            ).strip()
            + "\n",
            encoding="utf-8",
        )

        run_checked(
            [sys.executable, "crawl_cli.py", "--site", "Smoke Docs", "--headless"],
            cwd=REPO_ROOT,
            env=smoke_env(runtime_root),
            timeout=180,
            description="Running crawl smoke test",
        )

    index_file = runtime_root / "index" / "smoke.db"
    assert count_pages(str(index_file)) >= 2
    titles = {page["title"] for page in list_pages(str(index_file))}
    assert {"Home", "Guide"} <= titles
