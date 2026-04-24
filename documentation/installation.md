# Quick Start And Installation

## Document Control
- Status: Approved
- Owner: Documentation Maintainers
- Reviewers: Repository maintainers
- Created: 2026-04-24
- Last Updated: 2026-04-24
- Version: v1.0

## Change Log
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
- GNU Make, recommended
- A Chromium browser installation through Playwright

### Fastest Setup
```bash
make local-venv
```

This creates `.venv`, installs project dependencies, installs dev dependencies, and downloads Chromium for Playwright.

Activate the virtual environment before running commands:

```bash
source .venv/bin/activate
```

On Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

If you want the `docmcp-auth`, `docmcp-crawl`, and `docmcp-server` console commands, install the project itself in editable mode:

```bash
pip install -e .
```

### Manual Setup
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt
playwright install chromium
pip install -e .
```

On Windows:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -r requirements-dev.txt
playwright install chromium
pip install -e .
```

### Verify The Environment
Without editable install:

```bash
python auth_cli.py --help
python crawl_cli.py --help
python -m src.main
```

With editable install:

```bash
docmcp-auth --help
docmcp-crawl --help
docmcp-server
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

## References
- [README.md](../README.md)
- [pyproject.toml](../pyproject.toml)
- [requirements.txt](../requirements.txt)
- [requirements-dev.txt](../requirements-dev.txt)
- [auth_cli.py](../auth_cli.py)
- [crawl_cli.py](../crawl_cli.py)
