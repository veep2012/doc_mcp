# MCP Server

## Document Control
- Status: Approved
- Owner: Documentation Maintainers
- Reviewers: Repository maintainers
- Created: 2026-04-24
- Last Updated: 2026-06-06
- Version: v1.7

## Change Log
- 2026-06-06 | v1.7 | Documented the experimental `0.99.3` hybrid `search_docs` behavior, including mode selection, source labels, and keyword fallback when the vector sidecar is missing or unreadable.
- 2026-05-24 | v1.6 | Corrected the historical search_docs contract entry, kept the current `0.99.2` response contract documentation, and bumped the document control record.
- 2026-05-21 | v1.5 | Documented the server log-level environment variable, added current server version/help guidance, and clarified startup diagnostics.
- 2026-05-17 | v1.4 | Clarified that `search_docs` is keyword-only today, that the vector search counters remain zero until a vector backend is added, that `score` is an ordinal value derived from result order rather than a semantic relevance score, and that lookup failures return structured JSON.
- 2026-05-09 | v1.3 | Documented the experimental `0.99.1` JSON response contract for `search_docs`.
- 2026-04-25 | v1.2 | Added VS Code GitHub Copilot MCP setup instructions with the stable wheel-installed docmcp-server entry point and workspace runtime env values.
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
docmcp-server
```

Show the current server version:

```bash
docmcp-server --version
```

Source-tree compatibility wrapper:

```bash
python -m src.main
```

### Available Tools
- `get_sites`
- `get_version`
- `list_pages(site_name)`
- `search_docs(site_name, query, limit=10)`
- `fetch_page(site_name, url)`

### Tool Behavior
- `get_sites` lists each configured site and counts pages in its SQLite index.
- `get_version` returns the MCP server name and code-embedded package version for runtime checks.
- `list_pages` returns indexed page titles, URLs, and last crawled timestamps.
- `search_docs` runs hybrid search across SQLite FTS5 keyword results and the local sqlite-vec sidecar, while preserving the current JSON response contract.
- `fetch_page` returns the full Markdown content for a single indexed page.

### Experimental Search Contract (`0.99.3`)
`search_docs(site_name, query, limit=10)` currently returns a JSON string with this
shape:

```json
{
  "mode": "keyword",
  "vector_hits": 0,
  "keyword_hits": 2,
  "results": [
    {
      "text": "Result snippet or chunk text",
      "page_url": "https://docs.example.com/page",
      "title": "Page title",
      "score": 0.87,
      "source": "keyword"
    }
  ]
}
```

Implementation notes:
- `mode` is `"hybrid"` only when both vector and keyword search contribute at least one unique merged result.
- `mode` is `"vector"` when vector search returns the only usable results for the response.
- `mode` falls back to `"keyword"` when the vector sidecar is missing, unreadable, empty, or fully deduplicated away.
- `vector_hits` reflects the number of vector rows read before merge-time deduplication.
- `keyword_hits` reflects the number of SQLite FTS5 matches returned for the query before merge-time deduplication.
- `results` are merged deterministically with vector rows first (ordered by nearest-neighbor distance) and keyword rows second (ordered by existing FTS rank).
- Cross-source duplicates are removed deterministically using stable chunk/page-text identity, and the retained row keeps its original `source` label.
- `limit` defaults to `10` and bounds the merged response.
- `score` remains experimental and should be treated as an ordering hint, not as an absolute relevance measure.

If no keyword results are available, the tool still returns valid JSON:

```json
{
  "mode": "keyword",
  "vector_hits": 0,
  "keyword_hits": 0,
  "results": []
}
```

If the site name is unknown, the tool returns structured JSON with an `error` object instead of plain text:

```json
{
  "mode": "keyword",
  "vector_hits": 0,
  "keyword_hits": 0,
  "results": [],
  "error": {
    "type": "site_not_found",
    "message": "Site 'Missing Docs' not found."
  }
}
```

Successful search calls and empty-index search calls still return the base JSON search contract.

### Client Setup
- The server is designed for MCP clients that connect over stdio, such as VS Code / Copilot or Claude Desktop.
- The client command should point to the installed `docmcp-server` console script inside the active environment.
- `CONFIG_FILE` should point to the workspace `config/sites.yaml`.
- `DOC_MCP_HOME` should point to the workspace root used for runtime files.
- `MCP_LOG_LEVEL` controls startup logging. Default: `INFO`
- The server reconfigures stdout and stderr to UTF-8 at startup and emits startup diagnostics to `stderr`.

Example values:
- Command: `docmcp-server`
- Env: `CONFIG_FILE=/path/to/doc_mcp/config/sites.yaml`
- Env: `DOC_MCP_HOME=/path/to/doc_mcp`
- Env: `MCP_LOG_LEVEL=INFO`

### VS Code With GitHub Copilot
Use this setup when GitHub Copilot Chat runs in Agent mode and should call the local documentation MCP tools.

1. Install and sign in to the GitHub Copilot extension in VS Code.
2. Copy the built wheel into the VS Code destination directory, create a local virtual environment, and install the wheel:

```bash
mkdir -p dist
cp /path/to/doc_mcp-*.whl dist/
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install dist/doc_mcp-*.whl
```

On Windows PowerShell, create and activate the environment with `python -m venv .venv` and `.venv\Scripts\Activate.ps1`.

3. Create the runtime directories and put the site configuration in the destination workspace:

```bash
mkdir -p config storage index
cp /path/to/sites.yaml config/sites.yaml
```

Use relative runtime paths in `config/sites.yaml`; they resolve from `DOC_MCP_HOME` when the MCP client starts the server. For example:

```yaml
sites:
  - name: "My Docs"
    url: "https://docs.example.com"
    auth_required: true
    session_file: "storage/my_docs.json"
    crawl:
      start_url: "https://docs.example.com/docs"
      max_depth: 5
      delay_seconds: 1.0
      start_delay_seconds: 10.0
      block_images: true
      ignore_anchor_links: true
      ignore_https_errors: false
      allow_patterns: []
      deny_patterns: []
    index_file: "index/my_docs.db"
```

If a site needs a manual setup window in the browser before crawling starts, add `crawl.start_delay_seconds` to that site and run the crawl headful.

The VS Code MCP server receives `CONFIG_FILE` and `DOC_MCP_HOME` from `.vscode/mcp.json` in step 5.

4. Run fast local checks:

```bash
docmcp-auth --help
docmcp-crawl --help
docmcp-server
```

When `docmcp-server` starts successfully, stop it with `Ctrl+C` in the same terminal.

5. Create `.vscode/mcp.json` in the destination workspace root. If you use a
different virtual environment directory, update the `command` path to match:

```json
{
  "servers": {
    "docs-mcp": {
      "type": "stdio",
      "command": "${workspaceFolder}/${env:DOC_MCP_VENV}/bin/docmcp-server",
      "env": {
        "CONFIG_FILE": "${workspaceFolder}/config/sites.yaml",
        "DOC_MCP_HOME": "${workspaceFolder}",
        "MCP_SERVER_NAME": "docs-mcp"
      }
    }
  }
}
```

On Windows, use `${workspaceFolder}\\${env:DOC_MCP_VENV}\\Scripts\\docmcp-server.exe` as the command.

6. In VS Code, open the Command Palette with `Cmd+Shift+P` on macOS or `Ctrl+Shift+P` on Windows/Linux, then run `MCP: List Servers`.
7. Select `docs-mcp`, restart it after every `.vscode/mcp.json` change, and trust the server when prompted.
8. Open GitHub Copilot Chat with `Ctrl+Cmd+I` on macOS or `Ctrl+Alt+I` on Windows/Linux, switch to Agent mode, and ask it to list available MCP tools or call `get_sites`. If the shortcut is not mapped, open Copilot Chat from the VS Code activity bar or Command Palette.

After the MCP connection works, authenticate and crawl the target site:

```bash
export CONFIG_FILE="$PWD/config/sites.yaml"
export DOC_MCP_HOME="$PWD"
docmcp-auth --site "My Docs"
docmcp-crawl --site "My Docs"
```

Run these commands from the destination workspace root.

On Windows PowerShell, use `$env:CONFIG_FILE="$PWD\config\sites.yaml"` and `$env:DOC_MCP_HOME="$PWD"`.

Then ask Copilot Agent mode a documentation query that can use `search_docs` or `fetch_page`.

If the server does not appear, run `MCP: Open Workspace Folder MCP Configuration` and confirm that `.vscode/mcp.json` is valid JSON.

If `get_sites` fails with a path under `.venv/lib/.../site-packages/config/sites.yaml`, the MCP server did not receive `CONFIG_FILE`. Reopen `MCP: List Servers`, stop and restart `docs-mcp`, then run `MCP: Show Installed Servers` or `MCP: List Servers` -> `docs-mcp` -> `Show Output` to confirm VS Code is using the workspace `.vscode/mcp.json` shown above.

### Server Name
- The server name defaults to `docs-mcp`.
- It can be overridden with `MCP_SERVER_NAME`.

## Edge Cases
- If the client launches an old wheel, `docmcp-server` may still reference `src.main`; rebuild and reinstall the wheel.
- If `CONFIG_FILE` is not passed to the VS Code MCP process, the server may look for `config/sites.yaml` relative to the process working directory.
- If `MCP_SERVER_NAME` changes between crawl and query workflows, the client-visible name also changes.

## References
- [src/docmcp/main.py](../src/docmcp/main.py)
- [src/docmcp/tools.py](../src/docmcp/tools.py)
- [src/docmcp/config/loader.py](../src/docmcp/config/loader.py)
- [pyproject.toml](../pyproject.toml)
