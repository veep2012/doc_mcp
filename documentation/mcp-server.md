# MCP Server

## Document Control
- Status: Approved
- Owner: Documentation Maintainers
- Reviewers: Repository maintainers
- Created: 2026-04-24
- Last Updated: 2026-04-24
- Version: v1.0

## Change Log
- 2026-04-24 | v1.0 | Reformatted the MCP server reference and clarified stdio startup, tools, and client wiring.

## Purpose
Describe the stdio MCP server entry point, the tools it exposes, and the client setup required to launch it.

## Scope
- In scope:
  - The server entry point and script command.
  - The tools exposed to MCP clients.
- Out of scope:
  - Internal storage implementation details.
  - Site-specific crawling or authentication workflows.

## Design / Behavior
### Start The Server
```bash
python -m src.main
```

Or:

```bash
docmcp-server
```

### Available Tools
- `get_sites`
- `list_pages(site_name)`
- `search_docs(site_name, query, limit=10)`
- `fetch_page(site_name, url)`

### Tool Behavior
- `get_sites` lists each configured site and counts pages in its SQLite index.
- `list_pages` returns indexed page titles, URLs, and last crawled timestamps.
- `search_docs` runs SQLite FTS5 keyword search and returns snippets.
- `fetch_page` returns the full Markdown content for a single indexed page.

### Client Setup
- The server is designed for MCP clients that connect over stdio, such as VS Code / Copilot or Claude Desktop.
- The client command should point to the Python interpreter inside `.venv`.
- `PYTHONPATH` should include the repository root.

Example values:
- Command: `.venv/bin/python`
- Args: `-m src.main`
- Env: `PYTHONPATH=/path/to/doc_mcp`

### Server Name
- The server name defaults to `docs-mcp`.
- It can be overridden with `MCP_SERVER_NAME`.

## Edge Cases
- If the client does not launch the repository interpreter, the server may not find local package imports.
- If `MCP_SERVER_NAME` changes between crawl and query workflows, the client-visible name also changes.

## References
- [src/main.py](../src/main.py)
- [src/docmcp/tools.py](../src/docmcp/tools.py)
- [pyproject.toml](../pyproject.toml)
