# Manual Test Scenarios

## Document Control
- Status: Review
- Owner: Documentation Maintainers
- Reviewers: Repository maintainers
- Created: 2026-04-26
- Last Updated: 2026-05-03
- Version: v0.8

## Change Log
- 2026-05-03 | v0.8 | Linked the automated pytest scenario document and clarified that this manual checklist remains the source coverage baseline.
- 2026-04-26 | v0.3 | Added manual verification scenarios with separate development and installed-wheel runtime flows.

## Purpose
Provide a repeatable manual test checklist for validating that `doc-mcp` can be installed, configured, authenticated, crawled, queried, and connected to an MCP client.

## Scope
- In scope:
  - Local environment setup.
  - Site configuration discovery.
  - Manual authentication.
  - Crawl and SQLite index creation.
  - MCP server startup and client configuration smoke checks.
  - Basic failure-mode verification.
- Out of scope:
  - Automated unit or integration tests.
  - Site-specific login troubleshooting beyond observable pass/fail signals.
  - Semantic vector search verification.

## Design / Behavior
The checklist separates source-tree development checks from installed-wheel runtime checks, then validates shared authentication, crawling, server startup, MCP client configuration, search, fetch, and failure-mode behavior.

The manual scenarios remain the source coverage checklist for the repository. Automated coverage derived from this checklist is tracked separately in [documentation/test_scenarios/testing_framework_test_scenarios.md](test_scenarios/testing_framework_test_scenarios.md).

## Audience
- Repository maintainers
- QA reviewers
- Developers validating a local or packaged installation

## Preconditions
- Python 3.11 or newer is installed.
- The repository is checked out locally.
- A test documentation site is available.
- The tester can log in to the test site manually if authentication is required.
- The tester can edit local files under `.env`, `config/`, `storage/`, and `index/`.
- If you want a virtual environment directory other than `.venv`, set `DOC_MCP_VENV` and use that directory consistently when creating and activating the environment.

## Test Data
- Site name: `My Docs`
- Development runtime workspace: repository root
- Installed-wheel runtime workspace: separate runtime directory outside the repository
- Config file: `config/sites.yaml`
- Session file: `storage/my-docs.json`
- Index file: `index/my-docs.db`
- Search term: choose a term that appears on a known crawled page

Replace these values with the actual site name and paths used in `config/sites.yaml`.

## Development Environment Tests
Run this block first when validating the repository checkout directly.

### Development Command Set
- Auth command: `python auth_cli.py`
- Crawl command: `python crawl_cli.py`
- Server command: `python -m src.main`; stop it with `Ctrl+C` after startup is verified.

### MT-001A: Create Development Source-Tree Environment
- Steps:
  1. If `make` is available, run `make local-venv`.
  2. If `make` is not available, create the environment directly:
     - macOS/Linux:
       - `python3 -m venv .venv`
       - `source .venv/bin/activate`
       - `python -m pip install --upgrade pip`
       - `python -m pip install -r requirements-dev.txt`
       - `python -m playwright install chromium`
     - Windows PowerShell:
       - `python -m venv .venv`
       - `.venv\Scripts\Activate.ps1`
       - `python -m pip install --upgrade pip`
       - `python -m pip install -r requirements-dev.txt`
       - `python -m playwright install chromium`
  3. If `make local-venv` was used, activate the virtual environment:
     - macOS/Linux: `source .venv/bin/activate`
     - Windows PowerShell: `.venv\Scripts\Activate.ps1`
  4. Run `python auth_cli.py --help`.
  5. Run `python crawl_cli.py --help`.
  6. Run `python -c "import src.docmcp.main"` to verify the server module imports.
- Expected result:
  - The virtual environment is created.
  - Chromium is installed by Playwright.
  - Source-tree wrapper commands run without installing the package itself.
  - `docmcp-auth`, `docmcp-crawl`, and `docmcp-server` are not required for this test block.
- Pass/Fail:
  - Pass if setup succeeds and the wrapper commands print help or start correctly.
  - Fail if dependency installation, Playwright installation, or source-tree imports fail.

### MT-002A: Create Development Runtime Configuration
- Steps:
  1. Copy `.env.example` to `.env` if `.env` does not exist.
  2. Copy `config/sites.yaml.example` to `config/sites.yaml` if `config/sites.yaml` does not exist.
  3. Edit `config/sites.yaml` for the test site.
  4. Confirm `session_file` points under `storage/`.
  5. Confirm `index_file` points under `index/`.
  6. Leave `DOC_MCP_HOME` unset when running from the repository root; the loader uses the current directory by default.
  7. Leave `CONFIG_FILE` unset to use the default `config/sites.yaml`.
- Expected result:
  - The site entry has a stable `name`, `url`, `crawl.start_url`, `session_file`, and `index_file`.
  - Relative runtime paths resolve from the repository root.
- Pass/Fail:
  - Pass if the config can be read by the development CLI in the next scenario.
  - Fail if paths point outside the intended runtime workspace or required fields are missing.

### MT-003A: List Configured Sites In Development
- Steps:
  1. Run `python auth_cli.py --list`.
  2. Run `python crawl_cli.py --list`.
- Expected result:
  - Both commands print the configured site name.
  - The site name exactly matches the value that will be passed to `--site`.
- Pass/Fail:
  - Pass if both commands list `My Docs`.
  - Fail if either command cannot find `config/sites.yaml` or prints no configured sites.

## Runtime Environment Tests
Run this block after the development environment passes, using a separate runtime directory and installed wheel.

### Runtime Command Set
- Auth command: `docmcp-auth`
- Crawl command: `docmcp-crawl`
- Server command: `docmcp-server`; stop it with `Ctrl+C` after startup is verified.

### MT-001B: Create Separate Installed-Wheel Environment
- Steps:
  1. From the repository environment, build the wheel with `make wheel`.
  2. Create a separate runtime directory outside the repository.
  3. Create and activate a new virtual environment in that runtime directory:
     - macOS/Linux:
       - `python3 -m venv .venv`
       - `source .venv/bin/activate`
     - Windows PowerShell:
       - `python -m venv .venv`
       - `.venv\Scripts\Activate.ps1`
  4. Install the built wheel:
     - macOS/Linux: `python -m pip install /path/to/doc_mcp-*.whl`
     - Windows PowerShell: `python -m pip install /path/to/doc_mcp-*.whl`
  5. Install Chromium:
     - macOS/Linux: `python -m playwright install chromium`
     - Windows PowerShell: `python -m playwright install chromium`
  6. Run `docmcp-auth --help`.
  7. Run `docmcp-crawl --help`.
  8. Run `command -v docmcp-server` to verify the server console script is installed.
- Expected result:
  - The wheel installs into an environment that does not depend on the repository source tree.
  - The `docmcp-auth`, `docmcp-crawl`, and `docmcp-server` console commands are available.
  - Help output prints without import errors.
- Pass/Fail:
  - Pass if the wheel installs and all console commands are available.
  - Fail if the wheel build, wheel install, Playwright install, or console script import fails.

### MT-002B: Create Runtime Configuration
- Steps:
  1. In the separate runtime directory, create `config/`, `storage/`, and `index/`.
  2. Copy or create `config/sites.yaml` in that runtime directory.
  3. Copy or create `.env` in that runtime directory if the site config needs environment variables.
  4. Edit `config/sites.yaml` for the test site.
  5. Confirm `session_file` points under `storage/`.
  6. Confirm `index_file` points under `index/`.
  7. If running commands from the runtime directory, leave `DOC_MCP_HOME` unset; the loader uses the current directory by default.
  8. Leave `CONFIG_FILE` unset to use the default `config/sites.yaml`.
  9. If running commands from another directory, set both explicitly:
     - `export DOC_MCP_HOME="/path/to/runtime-workspace"`
     - `export CONFIG_FILE="config/sites.yaml"`
- Expected result:
  - The runtime directory contains only the files needed to run the installed wheel.
  - Relative config, session, and index paths resolve from `DOC_MCP_HOME`.
- Pass/Fail:
  - Pass if the config can be read by the installed wheel CLI in the next scenario.
  - Fail if paths still depend on the repository checkout or required files are missing.

### MT-003B: List Configured Sites In Runtime
- Steps:
  1. Run `docmcp-auth --list`.
  2. Run `docmcp-crawl --list`.
- Expected result:
  - Both commands print the configured site name.
  - The site name exactly matches the value that will be passed to `--site`.
- Pass/Fail:
  - Pass if both commands list `My Docs`.
  - Fail if either command cannot find `config/sites.yaml` or prints no configured sites.

## Shared Functional Tests
Run these scenarios after either `MT-003A` or `MT-003B`, using the command set for the environment under test.

### MT-004: Missing Config Fails Clearly
- Steps:
  1. Temporarily set `CONFIG_FILE` to a non-existent path.
  2. Run the selected auth command with `--list`.
  3. Restore the valid `CONFIG_FILE` value.
- Expected result:
  - The command fails with a clear configuration error.
  - The error identifies that the config file is missing or cannot be loaded.
- Pass/Fail:
  - Pass if the failure is readable and actionable.
  - Fail if the command crashes with an unrelated traceback or silently uses the wrong config.

## Authentication
### MT-005: Authenticate Site Manually
- Steps:
  1. Run the selected auth command with `--site "My Docs" --force`.
  2. Complete login in the Playwright browser window.
  3. Wait for the command to finish.
  4. Confirm `storage/my-docs.json` exists.
- Expected result:
  - A visible browser opens.
  - The tester can complete the site login flow.
  - The session file is written under `storage/`.
- Pass/Fail:
  - Pass if the session file exists and no authentication error remains.
  - Fail if the browser cannot open, login cannot complete, or the session file is not saved.

### MT-006: Reuse Existing Session
- Steps:
  1. Run the selected auth command with `--site "My Docs"` without `--force`.
  2. Observe whether the command reuses the saved session.
- Expected result:
  - The command validates the existing session when it is still valid.
  - A new browser login is not required for a valid session.
- Pass/Fail:
  - Pass if the existing session is accepted.
  - Fail if a valid session repeatedly forces login.

## Crawling And Indexing
### MT-007: Crawl Site
- Steps:
  1. Run the selected crawl command with `--site "My Docs"`.
  2. Watch the page-level crawl output.
  3. Confirm the command reaches the done message.
  4. Confirm `index/my-docs.db` exists.
- Expected result:
  - The crawler loads the saved session.
  - Pages are visited breadth-first from `crawl.start_url`.
  - HTML content is converted to Markdown and indexed.
  - The SQLite index file is created or updated.
- Pass/Fail:
  - Pass if at least one expected documentation page is indexed.
  - Fail if the crawl stops at login, produces no pages, or writes to the wrong index file.

### MT-008: Crawl With Headless Browser
- Steps:
  1. Run the selected crawl command with `--site "My Docs" --headless`.
  2. Confirm the run completes without opening a visible browser.
- Expected result:
  - The crawler runs with Chromium in headless mode.
  - Existing crawl and indexing behavior remains the same.
- Pass/Fail:
  - Pass if the run completes and updates existing indexed rows.
  - Fail if headless mode changes authentication state or prevents page extraction unexpectedly.

### MT-009: Expired Session Stops Crawl
- Steps:
  1. Move the session file to a temporary backup path or use an expired session.
  2. Run the selected crawl command with `--site "My Docs"`.
  3. Restore the original session file after the test.
- Expected result:
  - The crawler detects login-like redirects.
  - The crawl stops instead of indexing login pages as documentation content.
  - The output tells the tester to re-authenticate.
- Pass/Fail:
  - Pass if login content is not indexed and the recovery instruction is clear.
  - Fail if the crawler stores login pages or continues with unauthenticated content.

## MCP Server
### MT-010: Start MCP Server From Shell
- Steps:
  1. From the repository root, leave `DOC_MCP_HOME` and `CONFIG_FILE` unset unless you need to override the defaults.
  2. If running from another directory or a wheel runtime directory, run `export DOC_MCP_HOME="/path/to/runtime-workspace"` and `export CONFIG_FILE="config/sites.yaml"`.
  3. Development source tree: run `python -m src.main`.
  4. Installed wheel: run `docmcp-server`.
  5. Stop the server with `Ctrl+C` after startup completes or after confirming it is waiting on stdio.
- Expected result:
  - The server starts without configuration errors.
  - Startup output identifies the configured server name or runtime configuration.
  - The process waits for MCP stdio traffic.
- Pass/Fail:
  - Pass if startup succeeds and no missing-config error appears.
  - Fail if startup cannot find `config/sites.yaml`, fails to load sites, or exits unexpectedly.

### MT-011: Verify VS Code MCP Configuration
- Steps:
  1. Create or update `.vscode/mcp.json` with the documented `docs-mcp` server config.
  2. Development source tree: ensure `command` points to the active environment's `python` executable and `args` includes `-m` and `src.main`.
  3. Installed wheel: ensure `command` points to the installed `docmcp-server` executable.
  4. Ensure `.vscode/mcp.json` sets `CONFIG_FILE`, `DOC_MCP_HOME`, and `MCP_SERVER_NAME` in `servers.docs-mcp.env`.
  5. In VS Code, run `MCP: List Servers`.
  6. Start or restart `docs-mcp`.
- Expected result:
  - VS Code starts the MCP server from the local virtual environment.
  - The MCP process reads the workspace config rather than a `site-packages` path.
  - The server appears available in VS Code.
- Pass/Fail:
  - Pass if `docs-mcp` starts and stays running.
  - Fail if VS Code reports missing `config/sites.yaml` or uses the wrong working directory.

## Search And Fetch Smoke Test
### MT-012: Search Indexed Content Through MCP Client
- Steps:
  1. Start the MCP server in the client.
  2. Use the MCP search tool for `My Docs`.
  3. Query for the selected search term.
  4. Open one returned page through the MCP page-fetch tool.
- Expected result:
  - Search returns one or more relevant indexed pages.
  - The page-fetch tool returns Markdown content for a selected URL.
  - The returned URL matches a page visited during crawling.
- Pass/Fail:
  - Pass if search and fetch both return expected documentation content.
  - Fail if the site is missing, search is empty for known content, or fetch cannot find a returned URL.

### MT-013: Unknown Site Fails Clearly
- Steps:
  1. Use the MCP client to search a site name that is not in `config/sites.yaml`.
- Expected result:
  - The tool reports that the site is unknown or not configured.
  - No unrelated site data is returned.
- Pass/Fail:
  - Pass if the error is clear and scoped to the missing site.
  - Fail if the server crashes or returns results from a different site.

## Cleanup
- Remove test-only files if they were created outside normal runtime paths.
- Keep valid `storage/` and `index/` artifacts if they are useful for future local verification.
- Restore any temporary environment variable changes.
- Restore any moved session files.

## Edge Cases
- If the selected site requires MFA, pause the manual run until login completes and record the login path used.
- If a crawl starts from a redirected URL, verify indexed URLs still belong to the configured site and path scope.
- If a command is run outside the repository or runtime workspace, set `DOC_MCP_HOME` and `CONFIG_FILE` explicitly before treating failures as product defects.

## Risks and Mitigations
- Risk: Site-specific authentication behavior may make tests inconsistent.
  - Mitigation: Record the exact test site, account type, and login path in the test notes.
- Risk: Search terms may disappear after site content changes.
  - Mitigation: Choose a stable term from a durable documentation page.
- Risk: A stale session can make authentication reuse appear broken.
  - Mitigation: Run the forced-auth scenario before testing session reuse.

## References
- [installation.md](installation.md)
- [configuration.md](configuration.md)
- [authentication.md](authentication.md)
- [crawling.md](crawling.md)
- [mcp-server.md](mcp-server.md)
- [troubleshooting.md](troubleshooting.md)
- [src/docmcp/auth_cli.py](../src/docmcp/auth_cli.py)
- [src/docmcp/crawl_cli.py](../src/docmcp/crawl_cli.py)
- [src/docmcp/main.py](../src/docmcp/main.py)
