# Documentation MCP Server

`doc-mcp` is a local MCP server for documentation sites. It authenticates with Playwright, crawls pages into SQLite, and exposes the indexed content to AI clients over stdio.

## Quick Start

1. Create and activate the development environment.

If `make` is available:

```bash
make local-venv
source .venv/bin/activate
```

On Windows PowerShell:

```powershell
make local-venv
.venv\Scripts\Activate.ps1
```

`make local-venv` creates and populates `.venv`, but activation still has to be run in your current shell.

If you want a different virtual environment directory, set `DOC_MCP_VENV` before following the setup commands and substitute that path consistently in your shell.

If `make` is not available, create the environment directly:

```bash
VENV_DIR="${DOC_MCP_VENV:-.venv}"
python3 -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
python -m playwright install chromium
```

On Windows PowerShell without `make`:

```powershell
$VenvDir = $env:DOC_MCP_VENV
if (-not $VenvDir) { $VenvDir = ".venv" }
python -m venv $VenvDir
& "$VenvDir\Scripts\Activate.ps1"
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
python -m playwright install chromium
```

The development checkout can run through source-tree wrappers, so editable
install is not required. If you want the `docmcp-auth`, `docmcp-crawl`, and
`docmcp-server` console commands in this environment, run this after activating
`.venv`:

```bash
python -m pip install -e .
```

2. Create local configuration files:

```bash
cp .env.example .env
cp config/sites.yaml.example config/sites.yaml
```

On Windows PowerShell:

```powershell
Copy-Item .env.example .env
Copy-Item config\sites.yaml.example config\sites.yaml
```

3. Edit `config/sites.yaml` and `.env` for your site, credentials, and paths.

   The current authentication flow is validated for `headful` login only. The `email_code` and `password_only` auth types are not tested thoroughly and are not recommended for production use.

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

## Smoke Tests

The repository includes smoke tests that exercise crawl and MCP behavior end to end. They have a few explicit prerequisites:

- Podman or Docker must be installed and reachable as a container runtime.
- Playwright Chromium must be installed in the active Python environment.
- The environment must allow container networking and bind/mapped ports.

Common limitations:

- Rootless Podman can fail in CI or locked-down environments if user namespaces or port forwarding are restricted.
- Docker may work where Podman does not, and vice versa.
- If no container runtime is available, smoke tests should be skipped rather than expected to pass.
- If Chromium is missing, Playwright-based auth, crawl, and smoke paths will fail before the first site run.

When a container runtime is available, smoke failures should include a helpful message that points to `CONTAINER_BIN=docker` as an alternative when Podman is the default and rootless networking is the problem.

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

## License

`doc-mcp` is open-source software released under the MIT License. You may use,
copy, modify, distribute, sublicense, and sell copies of the software without
restriction, subject to the license notice terms in [LICENSE](LICENSE).
