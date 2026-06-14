# Troubleshooting

## Document Control
- Status: Approved
- Owner: Documentation Maintainers
- Reviewers: Repository maintainers
- Created: 2026-04-24
- Last Updated: 2026-06-14
- Version: v1.8

## Change Log
- 2026-06-14 | v1.8 | Added vector-sidecar fallback and rebuild guidance for degraded search results.
- 2026-05-26 | v1.7 | Added guidance for `crawl.delay_seconds` and `crawl.start_delay_seconds`, and clarified redirect skip semantics.
- 2026-05-24 | v1.6 | Added Podman machine recovery guidance for smoke-test environments and documented the rootful connection option.
- 2026-05-22 | v1.5 | Added redirect-policy troubleshooting guidance and aligned crawl diagnostics notes with the v0.1.4 release behavior.
- 2026-05-21 | v1.4 | Consolidated same-day crawl diagnostics updates and kept the startup and recovery guidance aligned with the current code.
- 2026-05-20 | v1.3 | Clarified debug stderr routing, redirected-navigation diagnostics, and crawl debug guidance for queue, link, and page-level behavior.
- 2026-04-27 | v1.2 | Added Windows Playwright module verification and recovery steps.
- 2026-04-25 | v1.1 | Updated troubleshooting notes for the package entry point and VS Code MCP configuration.
- 2026-04-24 | v1.0 | Reformatted the troubleshooting guide and grouped the common failures into standard sections.

## Purpose
List the most common failure modes for `doc-mcp` and the first corrective step for each one.

## Scope
- In scope:
  - Site lookup and crawl failures.
  - Session refresh and search issues.
- Out of scope:
  - Deep browser debugging.
  - Non-reproducible site-specific behavior.

## Design / Behavior
### The Server Cannot Find My Site
- Confirm the site name matches exactly what is in `config/sites.yaml`.
- Use `docmcp-auth --list` or `docmcp-crawl --list` to verify the configured sites.

### Authentication Keeps Repeating
- The saved session may have expired.
- Re-run `docmcp-auth --site "My Docs" --force`.
- Check whether the site redirects unauthenticated users to a login page.

### I Need Time To Set Up The Page
- Set `crawl.start_delay_seconds` for a headful crawl when you want the browser to load the start page, pause, and then let you change the page before crawling begins.
- Use that window to click buttons, switch filters, or navigate to the exact page you want to scan.
- `crawl.start_delay_seconds` is ignored when the crawl runs headless.

### Crawl Stops At Login
- The crawler treats redirects to login-like URLs as a sign that the session expired.
- Re-authenticate, then run the crawl again.

### Search Returns No Results
- Confirm the crawler indexed pages into the correct `index_file`.
- Check whether the site was crawled from the right `start_url`.
- Make sure the query terms actually exist in the indexed Markdown.

### Search Falls Back From Vector To Keyword
- `search_docs` now treats vector lookup as best-effort and keeps returning valid JSON when the vector sidecar is missing, unreadable, stale, incompatible, or empty.
- If the response includes an `error` object such as `vector_index_missing`, `vector_index_stale`, or `vector_index_incompatible`, rebuild the sidecar with `docmcp-vectorize --site "My Docs"` after confirming the crawl index is current.
- Rebuild the sidecar after changing `vectorizer.embedding_model` or replacing the site's `index_file`.
- In hybrid mode, the same fallback reason is logged and keyword results remain available when the SQLite index can answer.

### Pages Look Truncated
- The crawler tries several page containers, but some sites still expose incomplete content to automation.
- Re-run with `docmcp-crawl --site "My Docs" --debug` to inspect navigation, extraction, and discovered-link diagnostics before inspecting the site structure manually.
- Debug traces are written to `stderr`, so redirect that stream if you want to keep the main crawl progress output clean.

### Crawl Behavior Is Hard To Explain
- Run `docmcp-crawl --site "My Docs" --debug` to print crawler-only queue previews, per-page navigation details, discovered links, and skip reasons.
- Compare the debug trace with your `allow_patterns`, `deny_patterns`, and `start_url` configuration when pages are unexpectedly skipped or queued.
- If a page redirects before indexing, compare the requested URL and the final normalized URL in the debug trace.
- If a page redirects before indexing, compare the requested URL, the final normalized URL, and the `crawl.redirect_policy` decision in the debug trace.
- The crawler compares hosts exactly when it decides whether a discovered URL stays inside the site scope. If the site uses `www.example.com`, but `start_url` or `url` is set to `example.com`, links on the canonical host can be skipped as "outside start host". Use the canonical hostname consistently in the site config.
- If you need to set up the browser manually before crawling starts, use `crawl.start_delay_seconds` instead of stretching `delay_seconds`.
- If `docmcp-crawl` reports an invalid `crawl.delay_seconds` or `crawl.start_delay_seconds` value, make sure the configured value is numeric, finite, and greater than or equal to 0.

### Redirected Pages End Up Under The Wrong URL
- `crawl.redirect_policy` defaults to `final`, which stores the landing URL after a redirect.
- Set `crawl.redirect_policy: requested` if search results should keep the original requested URL.
- Set `crawl.redirect_policy: skip` if redirected pages should be crawled without being added to the index; the crawler still loads the page, extracts content, and discovers links from it.
- Re-run with `--debug` to confirm whether the crawler reported `final`, `requested`, or `skip` for that redirect.

### Missing Markdown Conversion
- If `markdownify` is not installed, the crawler falls back to plain text extraction.
- Install development dependencies through `make local-venv` or `python -m pip install -r requirements-dev.txt`.

### Windows Playwright Module Is Missing
- A standalone `playwright` script may not be visible in the active environment; use `python -m ...` instead.
- Verify the package with `python -m pip show playwright`.
- Verify the CLI module with `python -m playwright --version`.
- If verification fails with `No module named playwright`, reinstall dependencies with `python -m pip install -r requirements-dev.txt`.
- Install Chromium with `python -m playwright install chromium`.

### Windows Console Output Looks Broken
- `src/docmcp/main.py` reconfigures stdout and stderr to UTF-8.
- If a terminal still renders poorly, use a modern terminal emulator and ensure the virtual environment is active.

### VS Code MCP Looks In `site-packages/config/sites.yaml`
- The VS Code MCP process did not receive `CONFIG_FILE`.
- Set `CONFIG_FILE` and `DOC_MCP_HOME` in `.vscode/mcp.json`.
- Restart the `docs-mcp` server from `MCP: List Servers` after saving `.vscode/mcp.json`.

### Server Fails During Startup Configuration
- Missing `config/sites.yaml` or an empty `sites:` list stops `docmcp-server` before it accepts MCP traffic.
- Create the runtime workspace with `mkdir -p config storage index`, put `sites.yaml` under `config/`, and pass `DOC_MCP_HOME` plus `CONFIG_FILE` through the MCP client environment.
- Site-specific output directories are created when that site is authenticated, crawled, or queried, so one unused site's paths do not block server startup.
- For VS Code, check the `docs-mcp` output from `MCP: List Servers` to see the exact startup configuration error.

### Podman Smoke Runtime Is Stale Or Unreachable
- If `make test` reaches the smoke phase and Podman reports that the machine is already running but the socket refuses connections, treat the local Podman machine state as stale.
- Reinitialize the default machine with:
```bash
podman machine stop
podman machine rm -f podman-machine-default
podman machine init
podman machine start
```
- If you need the default connection to point at the rootful socket, run:
```bash
podman machine set --rootful
podman system connection default podman-machine-default-root
```
- If you want to set the default Podman service connection explicitly after reinitialization, the rootful connection is typically named `podman-machine-default-root`.
- If Podman is installed but unusable in the current environment, rerun the smoke target with `CONTAINER_BIN=docker`.

## Edge Cases
- If a site uses a non-standard login redirect, the session validity check may classify it as expired.
- If redirected pages still appear unexpectedly, confirm the active site config is the one being loaded and that `crawl.redirect_policy` is spelled exactly as documented.
- If the crawler returns partial pages, the site may require a different content container or a manual browser review.
- If search is empty after a crawl, check both the index path and the crawl start URL before re-running the job.
- If Podman is reachable but the smoke container still fails to start, confirm the current remote connection with `podman system connection list` before retrying.

## References
- [authentication.md](authentication.md)
- [crawling.md](crawling.md)
- [mcp-server.md](mcp-server.md)
- [src/docmcp/main.py](../src/docmcp/main.py)
