# Testing Framework Test Scenarios

## Document Control
- Status: Review
- Owner: Documentation Maintainers
- Reviewers: Repository maintainers
- Created: 2026-05-03
- Last Updated: 2026-08-15
- Version: v1.2
- Related Tickets: veep2012/doc_mcp#2

## Change Log
- 2026-08-14 | v1.0 | Added the lightweight MCP dependency profile and dual full/MCP-only wheel output, including cached baseline/current harness images, live image-build progress, vector-search runtime coverage, shell timeout overrides, concurrent stderr artifact streaming for verbose runs, and fixed internal safety limits after removing the configurable harness timeout.
- 2026-08-15 | v1.2 | Added recursive credential redaction coverage for JSON harness artifacts and aligned the harness contract with the supported wheel-path validation.
- 2026-08-02 | v0.3 | Added packaged MCP version-comparison harness scenarios and automated mapping.
- 2026-07-26 | v0.2 | Documented MCP smoke prerequisites, added optional-dependency collection-gate regression coverage, and mapped the package-independent test support helpers.
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
- FR-6: Default test collection must remain usable when Playwright or MCP is unavailable, and affected tests must report installation guidance.
- FR-7: The packaged-version harness must validate safe settings, exercise vector search through the MCP-only dependency profile, and fail on response differences other than explicitly allowlisted fields.

### Non-Functional Requirements
- NFR-1: Test commands should use the active virtual-environment Python.
- NFR-2: Smoke tests should remain isolated from checked-in runtime data.
- NFR-3: Scenario documentation should stay aligned with `documentation/test_scenarios/manual-test-scenarios.md`.

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
- `TS-TF-010` - Default collection remains usable and reports actionable skips for unavailable optional runtime dependencies.
- `TS-TF-011` - Test files do not import shared helpers through the `tests.*` package path.
- `TS-TF-012` - Shared helpers import successfully through the supported pytest and direct Python invocation modes.
- `TS-TF-013` - The MCP version-comparison harness validates its fixture and safe configuration, exercises vector search with the MCP-only dependency profile, normalizes only allowlisted fields (including JSON-encoded `get_version` payload versions), and reports unexpected differences.
- `TS-TF-014` - Harness JSON artifacts recursively redact credential-like values, including nested objects and JSON-encoded tool text.

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

#### TS-TF-010
- Purpose: Keep collection usable in dependency-light environments.
- Expected Result: Collection succeeds without Playwright or MCP; affected tests skip and print an installation command.

#### TS-TF-011
- Purpose: Prevent accidental reintroduction of package-dependent `tests.*` imports in test and smoke files.
- Expected Result: The static AST guard fails with the source path, line number, and forbidden module when a `tests` or `tests.*` import is added.

#### TS-TF-012
- Purpose: Detect import-path regressions that appear only under a specific test entry point.
- Expected Result: The helper modules import successfully through the `pytest` executable, `python -m pytest`, and direct Python import execution.

#### TS-TF-013
- Purpose: Compare two packaged MCP server versions reproducibly without production data.
- Preconditions: Both wheel paths exist; the fixture contains valid `config/sites.yaml`, referenced indexes, and the stable request corpus; Podman or Docker is available through `CONTAINER_BIN`.
- Action: Run `python -m docmcp.harness` or `make harness`.
- Expected Result: The harness builds two tagged images, `<HARNESS_IMAGE>:baseline` and `<HARNESS_IMAGE>:current`, with shared dependency/model layers and one target wheel in the final layer. Both isolated containers receive identical requests; runtime startup does not reinstall dependencies or download the model. The MCP-only wheel derives its dependency metadata from the same pinned `requirements-mcp.txt` profile used by the image builder. The corpus includes topic-specific Harness Docs searches: semantic queries such as training machine-learning models on biologics, configuring project permissions, analyzing assay plots, and working with molecular structures in three dimensions must produce `mode=vector` with vector hits and no keyword hits; related queries with overlapping terms must exercise `mode=hybrid`. The fixture's hybrid/vector search produces vector-backed results instead of `vector_backend_unavailable` fallback. Stale containers labeled `docmcp.harness=true` are removed before startup. Only documented allowlisted fields are ignored; an allowlist path may traverse response objects, list indexes, and JSON-encoded tool text. Unexpected differences or startup, timeout, malformed-response, and runtime failures fail while retaining redacted artifacts. Container stderr must stream directly into the version artifact while MCP stdout is processed, so verbose pip, HTTP, model-download, and server diagnostics cannot fill a pipe and block JSON-RPC responses. MCP stdout remains JSON-RPC only.
- Unit coverage of the default Podman setting must clear any process-level `CONTAINER_BIN` override so CI runtime selection does not affect the assertion.
- Cleanup: The container command uses `--rm`; inspect the timestamped artifact directory if the comparison fails.

#### TS-TF-014
- Purpose: Prevent credential-like values from being preserved in structured harness diagnostics.
- Preconditions: A temporary artifact path is writable.
- Action: Write nested dictionaries, lists, and JSON-encoded text containing credential-like keys through the harness artifact writer.
- Expected Result: The resulting JSON remains valid and contains `[REDACTED]` in place of credential values at every nested level.

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
- `TS-TF-010` -> `tests/test_playwright_settings.py::test_authentication_and_session_validation_use_site_playwright_settings`, `tests/support/smoke_support.py`, `tests/test_smoke_support.py::{test_optional_dependency_gates_allow_collection_in_minimal_environment,test_optional_dependency_gate_uses_repository_install_command,test_shared_helpers_import_without_tests_package}`
- `TS-TF-011` -> `tests/test_smoke_support.py::test_test_files_do_not_use_forbidden_tests_package_imports`
- `TS-TF-012` -> `tests/test_smoke_support.py::{test_shared_helpers_import_under_supported_invocation_modes,test_support_modules_import_as_top_level_modules}`
- `TS-TF-013` -> `tests/test_harness.py`
- `TS-TF-014` -> `tests/test_harness.py::test_json_artifacts_redact_nested_credentials`

## Edge Cases
- If Podman is installed but not usable in the current environment, rerun smoke tests with `CONTAINER_BIN=docker`.
- If the prepared MCP smoke index is missing, generate it locally or point the smoke test at another prepared SQLite file before retrying.
- If `pytest` is invoked with explicit marker overrides, those overrides take precedence over the default exclusion in `pytest.ini`.
- If a comparison timeout occurs, the failed run's baseline/current logs and `failure.log` remain under `artifacts/harness/`.

## References
- [README.md](../../README.md)
- [Makefile](../../Makefile)
- [pytest.ini](../../pytest.ini)
- [documentation/test_scenarios/manual-test-scenarios.md](manual-test-scenarios.md)
- [src/docmcp/config/loader.py](../../src/docmcp/config/loader.py)
- [src/docmcp/crawl_cli.py](../../src/docmcp/crawl_cli.py)
- [src/docmcp/tools.py](../../src/docmcp/tools.py)
- [src/docmcp/harness/runner.py](../../src/docmcp/harness/runner.py)
