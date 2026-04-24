# Documentation MCP Server

`doc-mcp` is a local MCP server for documentation sites. It authenticates with Playwright, crawls pages into SQLite, and exposes the indexed content to AI clients over stdio.

## Quick Start

1. Create the environment:

```bash
make local-venv
source .venv/bin/activate
```

On Windows PowerShell:

```powershell
make local-venv
.venv\Scripts\Activate.ps1
```

2. Create local configuration files:

```bash
cp .env.example .env
cp config/sites.yaml.example config/sites.yaml
```

3. Edit `config/sites.yaml` and `.env` for your site, credentials, and paths.

4. Authenticate the site:

```bash
python auth_cli.py --list
python auth_cli.py --site "My Docs"
```

5. Crawl and index the site:

```bash
python crawl_cli.py --site "My Docs"
```

6. Start the MCP server:

```bash
python -m src.main
```

If you want the `docmcp-auth`, `docmcp-crawl`, and `docmcp-server` console commands, install the project in editable mode:

```bash
pip install -e .
```

## What To Edit

- `config/sites.yaml` defines each documentation site.
- `.env` stores local secrets and overrides.
- `storage/` receives Playwright session files.
- `index/` receives SQLite search indexes.

## Detailed Docs

The full documentation lives in [`documentation/`](documentation/index.md).
