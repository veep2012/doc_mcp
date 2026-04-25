# MCP Server

## Document Control
- Status: Approved
- Owner: Documentation Maintainers
- Reviewers: Repository maintainers
- Created: 2026-04-24
- Last Updated: 2026-04-25
- Version: v1.2

## Change Log
- 2026-04-25 | v1.2 | Updated VS Code setup to use the stable wheel-installed docmcp-server entry point and workspace runtime env values.
- 2026-04-25 | v1.1 | Added VS Code GitHub Copilot MCP setup instructions.
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

Source-tree compatibility wrapper:

```bash
python -m src.main
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
- The client command should point to the installed `docmcp-server` console script inside `.venv`.
- `CONFIG_FILE` should point to the workspace `config/sites.yaml`.
- `DOC_MCP_HOME` should point to the workspace root used for runtime files.

Example values:
- Command: `.venv/bin/docmcp-server`
- Env: `CONFIG_FILE=/path/to/doc_mcp/config/sites.yaml`
- Env: `DOC_MCP_HOME=/path/to/doc_mcp`

### VS Code With GitHub Copilot
Use this setup when GitHub Copilot Chat runs in Agent mode and should call the local documentation MCP tools.

1. Install and sign in to the GitHub Copilot extension in VS Code.
2. Copy the built wheel into the VS Code destination directory, create a local virtual environment, and install the wheel:

```bash
mkdir -p dist
cp /path/to/doc_mcp-*.whl dist/
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install dist/doc_mcp-*.whl
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
      block_images: true
      ignore_anchor_links: true
      ignore_https_errors: false
      allow_patterns: []
      deny_patterns: []
    index_file: "index/my_docs.db"
```

The VS Code MCP server receives `CONFIG_FILE` and `DOC_MCP_HOME` from `.vscode/mcp.json` in step 5.

4. Run fast local checks:

```bash
docmcp-auth --help
docmcp-crawl --help
docmcp-server
```

When `docmcp-server` starts successfully, stop it with `Ctrl+C` in the same terminal.

5. Create `.vscode/mcp.json` in the destination workspace root:

```json
{
  "servers": {
    "docs-mcp": {
      "type": "stdio",
      "command": "${workspaceFolder}/.venv/bin/docmcp-server",
      "env": {
        "CONFIG_FILE": "${workspaceFolder}/config/sites.yaml",
        "DOC_MCP_HOME": "${workspaceFolder}",
        "MCP_SERVER_NAME": "docs-mcp"
      }
    }
  }
}
```

On Windows, use `${workspaceFolder}\\.venv\\Scripts\\docmcp-server.exe` as the command.

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
