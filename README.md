# Documentation MCP Server

An MCP (Model Context Protocol) server that gives AI assistants (GitHub Copilot, Claude, etc.)
full-text search access to documentation sites — including authenticated ones.

Uses **Playwright** for semi-manual authentication and **direct headful browser crawling**
to bypass anti-bot protection on SPAs.

---

## How It Works

```
auth_cli.py  (Playwright headful auth → saves session/cookies to storage/)
        ↓
crawl_cli.py (Playwright headful crawler → indexes pages as Markdown to SQLite)
        ↓
MCP Server   (exposes tools: search_docs, fetch_page, list_pages, get_sites)
        ↓
AI Client    (GitHub Copilot, Claude Desktop, etc.)
```

---

## Quick Start

### Prerequisites

- Python 3.11
- Make / GNU Make, optional but strongly recommended
  - Linux and macOS: install through your package manager if it is not already available
  - Windows: install a GNU Make distribution such as Chocolatey, winget, or MSYS2
- Optional developer tooling:
  - `pip-audit` for `make audit`

### 1. Install dependencies

#### With Make

```bash
make local-venv
```

The target creates the venv, installs project and dev dependencies, and installs the Chromium browser used by Playwright.
Activate the environment in your own terminal before running the CLI:

- Windows PowerShell: `.venv\Scripts\Activate.ps1`
- Linux / macOS: `source .venv/bin/activate`

#### Manual setup

#### Windows

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
playwright install chromium
```

#### Linux / macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

### 2. Configure environment

#### Windows

```powershell
cp .env.example .env
# Edit .env — set proxy, MCP_SERVER_NAME, and per-site credentials
```

#### Linux / macOS

```bash
cp .env.example .env
# Edit .env - set proxy, MCP_SERVER_NAME, and per-site credentials
```

### 3. Configure sites

Edit `config/sites.yaml` to add your documentation sites:

```yaml
sites:
  - name: "My Docs"
    url: "https://docs.example.com"
    auth_required: true
    auth_mode: "headful"
    session_file: "storage/my_docs.json"
    crawl:
      start_url: "https://docs.example.com/docs"
      max_depth: 5
      delay_seconds: 1.0
      block_images: true
      allow_patterns: []
      deny_patterns: []
    index_file: "index/my_docs.db"
```

### 4. Authenticate (one-time per site)

#### Windows

```powershell
# List configured sites
.venv\Scripts\python auth_cli.py --list

# Authenticate — opens a browser window, log in manually, press Enter
.venv\Scripts\python auth_cli.py --site "My Docs"

# Force re-authentication (if session expired)
.venv\Scripts\python auth_cli.py --site "My Docs" --force
```

#### Linux / macOS

```bash
# List configured sites
.venv/bin/python auth_cli.py --list

# Authenticate - opens a browser window, log in manually, press Enter
.venv/bin/python auth_cli.py --site "My Docs"

# Force re-authentication (if session expired)
.venv/bin/python auth_cli.py --site "My Docs" --force
```

Session is saved to `storage/<site>.json` and reused until it expires.

### 4. Audit dependencies

If you installed the dev dependencies with `make local-venv`, run:

```bash
make audit
```

If you set up the environment manually, install the dev dependency first:

```bash
pip install -r requirements-dev.txt
```

Manual fallback:

```bash
# Linux / macOS
.venv/bin/python -m pip_audit -r requirements.txt

# Windows
.venv\Scripts\python.exe -m pip_audit -r requirements.txt
```

### 5. Crawl and index

#### Windows

```powershell
# Crawl a site (headful browser by default)
.venv\Scripts\python crawl_cli.py --site "My Docs"

# Force re-auth before crawling
.venv\Scripts\python crawl_cli.py --site "My Docs" --force-auth

# List all configured sites
.venv\Scripts\python crawl_cli.py --list
```

#### Linux / macOS

```bash
# Crawl a site (headful browser by default)
.venv/bin/python crawl_cli.py --site "My Docs"

# Force re-auth before crawling
.venv/bin/python crawl_cli.py --site "My Docs" --force-auth

# List all configured sites
.venv/bin/python crawl_cli.py --list
```

### 6. Connect to your AI client

#### GitHub Copilot / VS Code (`.vscode/mcp.json`)
##### Windows
```json
{
  "servers": {
    "docs-mcp": {
      "type": "stdio",
      "command": "${workspaceFolder}/.venv/Scripts/python.exe",
      "args": ["-m", "src.main"],
      "env": {
        "PYTHONPATH": "${workspaceFolder}"
      }
    }
  }
}
```

##### Linux / macOS
```json
{
  "servers": {
    "docs-mcp": {
      "type": "stdio",
      "command": "${workspaceFolder}/.venv/bin/python",
      "args": ["-m", "src.main"],
      "env": {
        "PYTHONPATH": "${workspaceFolder}"
      }
    }
  }
}
```

#### Claude Desktop (`claude_desktop_config.json`)
##### Windows
```json
{
  "mcpServers": {
    "docs-mcp": {
      "command": "C:/path/to/your/project/.venv/Scripts/python.exe",
      "args": ["-m", "src.main"],
      "env": {
        "PYTHONPATH": "C:/path/to/your/project"
      }
    }
  }
}
```

##### Linux / macOS
```json
{
  "mcpServers": {
    "docs-mcp": {
      "command": "/path/to/your/project/.venv/bin/python",
      "args": ["-m", "src.main"],
      "env": {
        "PYTHONPATH": "/path/to/your/project"
      }
    }
  }
}
```

---

## Available MCP Tools

| Tool | Description | Parameters |
|------|-------------|------------|
| `get_sites` | List all configured sites and index status | — |
| `list_pages` | List all indexed pages for a site | `site_name` |
| `search_docs` | Full-text keyword search | `site_name`, `query`, `limit` |
| `fetch_page` | Get full Markdown content of a page | `site_name`, `url` |

---

## Project Structure

```
docs-mcp/
├── auth_cli.py              # Authenticate to a site, save session
├── crawl_cli.py             # Crawl a site and index pages to SQLite
├── config/
│   └── sites.yaml           # Site configuration
├── src/
│   ├── main.py              # MCP server entry point (stdio)
│   ├── auth/
│   │   └── session.py       # Playwright headful auth + session validation
│   ├── config/
│   │   └── loader.py        # YAML config loader with ${ENV_VAR} resolution
│   ├── crawler/
│   │   └── (unused)         # Legacy crawl4ai crawler — removed
│   ├── index/
│   │   └── store.py         # SQLite + FTS5 index storage
│   └── docmcp/
│       └── tools.py         # MCP tool definitions (FastMCP)
├── storage/                 # Session files (gitignored)
├── index/                   # SQLite index files (gitignored)
├── .env                     # Local environment variables (gitignored)
├── .env.example             # Environment variables template
├── requirements.txt
└── README.md
```

---

## Tech Stack

| Component | Technology |
|-----------|------------|
| Language | Python 3.11+ |
| Browser Automation | Playwright (async) |
| HTML → Markdown | markdownify |
| MCP Server | `mcp` Python SDK + FastMCP |
| Storage | SQLite FTS5 (pages) + JSON (sessions) |
| Config | YAML (`PyYAML`) + `.env` (`python-dotenv`) |

---

## Configuration Reference

### `config/sites.yaml` fields

| Field | Description |
|-------|-------------|
| `name` | Display name (used in CLI and MCP tools) |
| `url` | Site root URL |
| `auth_required` | `true` / `false` |
| `auth_mode` | `headful` — visible browser, user logs in manually |
| `session_file` | Path to save Playwright session state |
| `crawl.start_url` | URL to begin crawling from |
| `crawl.max_depth` | BFS depth limit |
| `crawl.delay_seconds` | Delay between page requests |
| `crawl.block_images` | Skip image/font/media requests (faster crawl) |
| `crawl.allow_patterns` | Glob patterns — only crawl matching URLs |
| `crawl.deny_patterns` | Glob patterns — skip matching URLs |
| `index_file` | SQLite DB path for this site's index |

### `.env` variables

| Variable | Description |
|----------|-------------|
| `MCP_SERVER_NAME` | Name of the MCP server (default: `docs-mcp`) |
| `HTTPS_PROXY` / `HTTP_PROXY` | Corporate proxy settings |
| `SITE1_USERNAME` | Username/email for site 1 auth |
| `SITE1_PASSWORD` | Password for site 1 auth (if needed) |
