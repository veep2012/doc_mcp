# Operations

## Document Control
- Status: Approved
- Owner: Documentation Maintainers
- Reviewers: Repository maintainers
- Created: 2026-04-24
- Last Updated: 2026-04-25
- Version: v1.1

## Change Log
- 2026-04-25 | v1.1 | Updated implementation references for package entry points.
- 2026-04-24 | v1.0 | Reformatted the operations guide and kept the normal workflow, recovery, and logging steps.

## Purpose
Describe the day-to-day operational workflow for refreshing a site, rebuilding indexes, and preserving runtime artifacts.

## Scope
- In scope:
  - The normal auth, crawl, and server startup sequence.
  - Recovery steps when a site or index needs a refresh.
- Out of scope:
  - Internal implementation details for crawling or indexing.
  - Per-site configuration values.

## Design / Behavior
### Normal Workflow
1. Configure a site in `config/sites.yaml`.
2. Authenticate the site with `docmcp-auth`.
3. Crawl the site with `docmcp-crawl`.
4. Start `docmcp-server`.
5. Connect an MCP client and use `search_docs`, `list_pages`, or `fetch_page`.

### File Layout
- `storage/` holds session state and can be deleted if you want to re-authenticate.
- `index/` holds SQLite indexes and can be deleted if you want a full re-crawl.
- `config/sites.yaml` is the live site configuration file.
- `.env` holds local overrides and secrets.

### Rebuilding An Index
- Remove the site's SQLite database from `index/`.
- Re-authenticate if the session expired.
- Re-run the crawler.

### Backups
- The two important runtime artifacts are the session JSON under `storage/` and the SQLite index under `index/`.
- Back up both if you need to preserve access and search state.

### Logging
- The server and CLIs use standard Python logging and print statements.
- Increase the server log level with:
```bash
MCP_LOG_LEVEL=DEBUG docmcp-server
```

## Edge Cases
- If a session file is missing, the next crawl run may need a fresh authentication step.
- If an index is deleted, search results disappear until the crawler repopulates it.
- If logging output is hard to read on Windows, use a UTF-8 capable terminal.

## References
- [config/sites.yaml](../config/sites.yaml)
- [auth_cli.py](../auth_cli.py)
- [crawl_cli.py](../crawl_cli.py)
- [src/docmcp/main.py](../src/docmcp/main.py)
