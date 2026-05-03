# Testing Framework Test Scenarios

## Document Control
- Status: Review
- Owner: Documentation Maintainers
- Reviewers: Repository maintainers
- Created: 2026-05-03
- Last Updated: 2026-05-03
- Version: v0.1
- Related Tickets: veep2012/doc_mcp#2

## Change Log
- 2026-05-03 | v0.1 | Added pytest framework scenario coverage, smoke prerequisites, and automated test mapping.

## Purpose
Document the automated test framework scenarios for `doc-mcp`, including the expected `make test` workflow, default pytest behavior, smoke-test prerequisites, and the coverage mapping back to the repository runtime and manual checklist.

## Scope
- In scope:
  - The pytest and Make-based test entry points.
  - Unit and smoke scenarios for index, config, crawler, and MCP behavior.
  - Mapping automated scenarios back to the manual test checklist.
- Out of scope:
  - Site-specific authentication walkthroughs.
  - Manual browser-login validation steps.

## Audience
- Repository maintainers
- Contributors extending automated coverage
- QA reviewers comparing manual and automated validation

## Requirements
### Functional Requirements
- FR-1: `make test` must run unit coverage before smoke coverage.
- FR-2: Direct `pytest` invocation must stay fast by excluding smoke tests by default.
- FR-3: Automated tests must cover index store, config loader, crawler helpers, and MCP tool behavior.
- FR-4: Smoke tests must cover a crawl against a temporary static site and MCP stdio search against a prepared index.
- FR-5: Missing smoke prerequisites must fail with actionable messages instead of tracebacks.

### Non-Functional Requirements
- NFR-1: Test commands should use the active virtual-environment Python.
- NFR-2: Smoke tests should remain isolated from checked-in runtime data.
- NFR-3: Scenario documentation should stay aligned with `documentation/manual-test-scenarios.md`.

## Design / Behavior
### Scenario Catalog
- `TS-TF-001` - `make test` runs unit tests first, then smoke tests only after unit success.
- `TS-TF-002` - Direct `pytest` remains fast and excludes smoke tests by default.
- `TS-TF-003` - Index store persists, updates, searches, fetches, lists, and counts pages correctly.
- `TS-TF-004` - Config loader resolves runtime-relative files and fails clearly for missing or invalid config.
- `TS-TF-005` - Crawler helpers normalize URLs, reject static assets, enforce allow/deny rules, handle anchors, and convert HTML to Markdown.
- `TS-TF-006` - MCP tools return configured sites, pages, search results, fetched page content, and clear unknown-site messages.
- `TS-TF-007` - Crawl smoke indexes a temporary static site through Podman or Docker.
- `TS-TF-008` - MCP smoke starts an isolated stdio server and verifies `search_docs` against a prepared index.
- `TS-TF-009` - Missing smoke prerequisites fail with actionable messages.

### Scenario Details
#### TS-TF-001
- Purpose: Confirm the canonical Make entry point preserves a safe validation order.
- Preconditions: `.venv` exists and contains development dependencies.
- Expected Result: `test-unit` runs before `test-smoke`, and `make` stops before smoke if unit tests fail.

#### TS-TF-002
- Purpose: Keep the default contributor feedback loop fast.
- Preconditions: `pytest.ini` is present.
- Expected Result: Plain `pytest` runs the non-smoke suite and deselects smoke-marked tests.

#### TS-TF-003
- Purpose: Validate SQLite index creation and CRUD/search behavior.
- Expected Result: Temporary indexes support init, upsert, count, fetch, list, and FTS search.

#### TS-TF-004
- Purpose: Validate runtime-root config loading.
- Expected Result: Relative session and index paths resolve from `DOC_MCP_HOME`, `${ENV_VAR}` placeholders resolve from the runtime `.env`, and missing or invalid config raises readable `ConfigError` output.

#### TS-TF-005
- Purpose: Validate crawler helper decisions without requiring a live browser session.
- Expected Result: URL normalization, asset filtering, allow/deny checks, anchor handling, and HTML-to-Markdown conversion behave predictably.

#### TS-TF-006
- Purpose: Validate the MCP tool layer on top of configured site indexes.
- Expected Result: Site listing, page listing, search, fetch, and unknown-site responses are stable and readable.

#### TS-TF-007
- Purpose: Verify the end-to-end crawl smoke path.
- Preconditions: `CONTAINER_BIN` points to a working Podman or Docker binary, and Playwright Chromium is installed through the active interpreter.
- Expected Result: A temporary static site served from a container is crawled headlessly and indexed into a temporary SQLite file.

#### TS-TF-008
- Purpose: Verify the end-to-end MCP stdio path.
- Preconditions: A prepared local SQLite index exists for the temporary runtime workspace.
- Expected Result: An isolated stdio server responds to `search_docs` with content from the prepared index.

#### TS-TF-009
- Purpose: Make missing smoke prerequisites actionable.
- Expected Result: Missing container runtimes or missing prepared indexes fail with direct remediation guidance instead of Python tracebacks.

### Automated Test Mapping
- `TS-TF-001` -> `tests/test_smoke_support.py::test_make_test_dry_run_lists_unit_before_smoke`
- `TS-TF-002` -> `tests/test_smoke_support.py::test_direct_pytest_excludes_smoke_by_default`
- `TS-TF-003` -> `tests/test_index_store.py`
- `TS-TF-004` -> `tests/test_config_loader.py`
- `TS-TF-005` -> `tests/test_crawl_cli.py`
- `TS-TF-006` -> `tests/test_tools.py`
- `TS-TF-007` -> `tests/smoke/test_crawl_smoke.py`
- `TS-TF-008` -> `tests/smoke/test_mcp_smoke.py`
- `TS-TF-009` -> `tests/test_smoke_support.py::{test_missing_container_runtime_fails_with_actionable_message,test_missing_prepared_index_fails_with_actionable_message}`

## Edge Cases
- If Podman is installed but not usable in the current environment, rerun smoke tests with `CONTAINER_BIN=docker`.
- If the prepared MCP smoke index is missing, generate it locally or point the smoke test at another prepared SQLite file before retrying.
- If `pytest` is invoked with explicit marker overrides, those overrides take precedence over the default exclusion in `pytest.ini`.

## References
- [README.md](../../README.md)
- [Makefile](../../Makefile)
- [pytest.ini](../../pytest.ini)
- [documentation/manual-test-scenarios.md](../manual-test-scenarios.md)
- [src/docmcp/config/loader.py](../../src/docmcp/config/loader.py)
- [src/docmcp/crawl_cli.py](../../src/docmcp/crawl_cli.py)
- [src/docmcp/tools.py](../../src/docmcp/tools.py)
