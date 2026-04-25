# Troubleshooting

## Document Control
- Status: Approved
- Owner: Documentation Maintainers
- Reviewers: Repository maintainers
- Created: 2026-04-24
- Last Updated: 2026-04-25
- Version: v1.1

## Change Log
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

### Crawl Stops At Login
- The crawler treats redirects to login-like URLs as a sign that the session expired.
- Re-authenticate, then run the crawl again.

### Search Returns No Results
- Confirm the crawler indexed pages into the correct `index_file`.
- Check whether the site was crawled from the right `start_url`.
- Make sure the query terms actually exist in the indexed Markdown.

### Pages Look Truncated
- The crawler tries several page containers, but some sites still expose incomplete content to automation.
- Re-run in normal mode and inspect the site structure if needed.

### Missing Markdown Conversion
- If `markdownify` is not installed, the crawler falls back to plain text extraction.
- Install dependencies through `make local-venv` or `pip install -r requirements.txt`.

### Windows Console Output Looks Broken
- `src/docmcp/main.py` reconfigures stdout and stderr to UTF-8.
- If a terminal still renders poorly, use a modern terminal emulator and ensure the virtual environment is active.

### VS Code MCP Looks In `site-packages/config/sites.yaml`
- The VS Code MCP process did not receive `CONFIG_FILE`.
- Set `CONFIG_FILE` and `DOC_MCP_HOME` in `.vscode/mcp.json`.
- Restart the `docs-mcp` server from `MCP: List Servers` after saving `.vscode/mcp.json`.

### Server Fails During Startup Configuration
- Missing `config/sites.yaml`, an empty `sites:` list, or missing `storage/` and `index/` directories now stop `docmcp-server` before it accepts MCP traffic.
- Create the runtime workspace with `mkdir -p config storage index`, put `sites.yaml` under `config/`, and pass `DOC_MCP_HOME` plus `CONFIG_FILE` through the MCP client environment.
- For VS Code, check the `docs-mcp` output from `MCP: List Servers` to see the exact startup configuration error.

## Edge Cases
- If a site uses a non-standard login redirect, the session validity check may classify it as expired.
- If the crawler returns partial pages, the site may require a different content container or a manual browser review.
- If search is empty after a crawl, check both the index path and the crawl start URL before re-running the job.

## References
- [authentication.md](authentication.md)
- [crawling.md](crawling.md)
- [mcp-server.md](mcp-server.md)
- [src/docmcp/main.py](../src/docmcp/main.py)
