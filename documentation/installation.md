# Quick Start And Installation

## Document Control
- Status: Approved
- Owner: Documentation Maintainers
- Reviewers: Repository maintainers
- Created: 2026-04-24
- Last Updated: 2026-04-27
- Version: v1.6

## Change Log
- 2026-04-27 | v1.6 | Clarified optional Make setup, Playwright installation, and optional editable install for source-tree development.
- 2026-04-25 | v1.1 | Updated setup and verification commands for the package entry points and explicit virtual environment activation.
- 2026-04-24 | v1.0 | Reformatted the setup guide to the documentation standard and kept the install paths and verification commands.

## Purpose
Provide the shortest path to a working local environment for `doc-mcp`, including Python setup, Playwright dependencies, and the available console commands.

## Scope
- In scope:
  - Local environment prerequisites.
  - Virtual environment setup and dependency installation.
  - Basic verification commands.
- Out of scope:
  - Site-specific authentication and crawl settings.
  - MCP tool behavior after the environment is ready.

## Design / Behavior
### Prerequisites
- Python 3.11 or newer
- GNU Make, optional but recommended for the fastest setup path
- A Chromium browser installation through Playwright

### Fastest Setup With Make
```bash
make local-venv
```

This creates `.venv`, installs project dependencies, installs dev dependencies, and downloads Chromium for Playwright. The `make` target does not activate the virtual environment in your current shell.

If you prefer a different virtual environment directory, set `DOC_MCP_VENV` before running the setup commands and substitute that directory consistently in the activation step.

Activate the virtual environment before running project commands:

```bash
source .venv/bin/activate
```

On Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

The source-tree wrappers work without installing the package itself. If you want the `docmcp-auth`, `docmcp-crawl`, and `docmcp-server` console commands, install the project in editable mode:

```bash
pip install -e .
```

### Manual Setup Without Make
```bash
VENV_DIR="${DOC_MCP_VENV:-.venv}"
python3 -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
python -m playwright install chromium
```

On Windows:

```powershell
$VenvDir = $env:DOC_MCP_VENV
if (-not $VenvDir) { $VenvDir = ".venv" }
python -m venv $VenvDir
& "$VenvDir\Scripts\Activate.ps1"
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
python -m playwright install chromium
```

Editable install remains optional for source-tree development. Use it only when you need the package console commands:

```bash
python -m pip install -e .
```

### Verify The Environment
Source-tree compatibility wrappers:

```bash
python auth_cli.py --help
python crawl_cli.py --help
python -m src.main
```

Installed package commands:

```bash
docmcp-auth --help
docmcp-crawl --help
docmcp-server
```

On Windows, do not rely on a standalone `playwright` file being visible in
the activated environment. Verify Playwright through Python:

```powershell
python -m pip show playwright
python -m playwright --version
```

### Build And Install A Wheel On Another Environment
If you want to package `doc-mcp` in one environment and install it in another, build a wheel and copy it across:

1. Build the wheel from the repository root:

```bash
python -m pip install build
python -m build --wheel
```

2. Copy the generated `.whl` file from `dist/` to the target environment.

3. Install the wheel on the target machine:

```bash
python -m pip install /path/to/doc_mcp-*.whl
```

4. Run the installed console commands:

```bash
docmcp-auth --help
docmcp-crawl --help
docmcp-server
```

## Edge Cases
- If `make` is not available, use the manual setup commands.
- If the virtual environment is not active, the CLI commands will use whatever Python is on `PATH`.
- If Chromium is missing, Playwright-based auth and crawl commands will fail before the first site run.
- If `python -m playwright --version` fails with `No module named playwright`, reinstall dependencies with `python -m pip install -r requirements-dev.txt`.

## References
- [README.md](../README.md)
- [pyproject.toml](../pyproject.toml)
- [requirements.txt](../requirements.txt)
- [requirements-dev.txt](../requirements-dev.txt)
- [auth_cli.py](../auth_cli.py)
- [crawl_cli.py](../crawl_cli.py)
- [src/docmcp/main.py](../src/docmcp/main.py)
- [src/docmcp/auth_cli.py](../src/docmcp/auth_cli.py)
- [src/docmcp/crawl_cli.py](../src/docmcp/crawl_cli.py)
