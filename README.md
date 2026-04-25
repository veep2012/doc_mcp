# Documentation MCP Server

`doc-mcp` is a local MCP server for documentation sites. It authenticates with Playwright, crawls pages into SQLite, and exposes the indexed content to AI clients over stdio.

## Quick Start

1. Create and activate the environment, then install the project commands:

```bash
make local-venv
source .venv/bin/activate
pip install -e .
```

On Windows PowerShell:

```powershell
make local-venv
.venv\Scripts\Activate.ps1
pip install -e .
```

`make local-venv` creates and populates `.venv`, but activation still has to be run in your current shell.

2. Create local configuration files:

```bash
cp .env.example .env
cp config/sites.yaml.example config/sites.yaml
```

3. Edit `config/sites.yaml` and `.env` for your site, credentials, and paths.

   The current authentication flow is validated for `headful` login only. The `email_code` and `password_only` auth types are not tested thoroughly and are not recommended for production use.

4. Authenticate the site:

```bash
docmcp-auth --list
docmcp-auth --site "My Docs"
```

5. Crawl and index the site:

```bash
docmcp-crawl --site "My Docs"
```

6. Start the MCP server:

```bash
docmcp-server
```

## Install On Another Environment

If you want to build a distributable wheel in one environment and install it in another:

1. Build the wheel from the project root:

```bash
python -m pip install build
python -m build --wheel
```

2. Copy the generated file from `dist/` to the target environment.

3. Install the wheel on the target machine:

```bash
python -m pip install /path/to/doc_mcp-*.whl
```

4. Create or copy runtime files in a workspace directory:

```bash
mkdir -p config storage index
cp /path/to/sites.yaml config/sites.yaml
cp /path/to/.env .env
```

Relative `CONFIG_FILE`, `session_file`, and `index_file` values are resolved from `DOC_MCP_HOME`, or from the current working directory when `DOC_MCP_HOME` is not set.

5. Use the installed console commands:

```bash
export DOC_MCP_HOME="$PWD"
export CONFIG_FILE="config/sites.yaml"
docmcp-auth --help
docmcp-crawl --help
docmcp-server
```

## What To Edit

- `config/sites.yaml` defines each documentation site.
- `.env` stores local secrets and overrides.
- `storage/` receives Playwright session files.
- `index/` receives SQLite search indexes.

## Detailed Docs

The full documentation lives in [`documentation/`](documentation/index.md).
