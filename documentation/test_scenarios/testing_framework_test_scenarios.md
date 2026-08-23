# Testing Framework Test Scenarios

## Document Control
- Status: Review
- Owner: Documentation Maintainers
- Reviewers: Repository maintainers
- Created: 2026-05-03
- Last Updated: 2026-08-23
- Version: v2.5
- Related Tickets: veep2012/doc_mcp#2

## Change Log
- 2026-08-23 | v2.5 | Expanded MCP tool and stdio scenarios for the JSON contract, structured errors, empty states, preserved search semantics, fixed safe vector error messages with server-side raw exception logging, complete missing-page response assertions, and safe configuration-failure coverage.
- 2026-08-16 | v2.4 | Extended TS-TF-022 with a real repository-built wheel rewrite and installation check, extended TS-TF-023 with concurrent-process artifact creation coverage so parallel harness runs receive distinct directories, and added diagnostics for vector sidecars built with a different embedding model than configured in sites.yaml.
- 2026-08-15 | v1.3 | Added failure-boundary coverage for invalid harness options, malformed or mismatched MCP responses, early server exit, and preserved comparison-failure artifacts.
- 2026-08-14 | v1.0 | Added the lightweight MCP dependency profile and dual full/MCP-only wheel output, including cached baseline/current harness images, live image-build progress, vector-search runtime coverage, shell timeout overrides, concurrent stderr artifact streaming for verbose runs, and fixed internal safety limits after removing the configurable harness timeout.
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
- FR-8: Expected vector failures must return fixed safe messages for their public error codes, while raw exception details are retained only in server-side logs.

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
- `TS-TF-006` - MCP tools return standardized JSON contracts for configured sites, pages, search results, fetched page content, empty states, invalid arguments, unavailable indexes, and unknown sites; vector error messages are fixed per public error code and raw exception details are server-side only.
- `TS-TF-007` - Crawl smoke indexes a temporary static site through Podman or Docker.
- `TS-TF-008` - MCP smoke starts an isolated stdio server and verifies all five tool contracts, including representative success and failure calls.
- `TS-TF-009` - Missing smoke prerequisites fail with actionable messages.
- `TS-TF-010` - Default collection remains usable and reports actionable skips for unavailable optional runtime dependencies.
- `TS-TF-011` - Test files do not import shared helpers through the `tests.*` package path.
- `TS-TF-012` - Shared helpers import successfully through the supported pytest and direct Python invocation modes.
- `TS-TF-013` - The MCP version-comparison harness validates its fixture and safe configuration, runs the checked-in initialization, `get_version`, `alpha`, missing-phrase, and missing-site corpus, normalizes only allowlisted fields (including JSON-encoded `get_version` payload versions), and reports unexpected differences.
- `TS-TF-014` - Harness JSON artifacts recursively redact credential-like values, including nested objects and JSON-encoded tool text.
- `TS-TF-015` - Invalid harness option values fail validation with actionable errors before a comparison starts.
- `TS-TF-016` - Malformed, mismatched, or prematurely closed MCP responses fail the run and preserve comparison diagnostics.
- `TS-TF-017` - The packaged-version harness sends `notifications/initialized` after `initialize`, validates notification messages without request IDs, and does not wait for notification responses.
- `TS-TF-018` - Harness stderr is drained without blocking MCP stdout and credential-like values are redacted before stderr artifacts are retained on success or failure.
- `TS-TF-019` - The harness buffers partial newline-delimited MCP responses and enforces one response deadline through completion, including when the server stalls after writing a fragment.
- `TS-TF-020` - Harness preflight rejects empty or corrupt source indexes and hybrid/vector fixtures with missing, stale, incompatible, or empty vector sidecars.
- `TS-TF-021` - Harness runtime selection gives explicit process/Make overrides precedence over repository `.env`, then uses `.env-harness` and Podman as fallbacks.
- `TS-TF-022` - MCP-only wheel rewriting renames distribution metadata, replaces dependencies and entry points, regenerates valid RECORD hashes, uses the expected output filename, and produces an installable wheel.
- `TS-TF-023` - Harness artifact run directories retain a UTC timestamp and add a collision-resistant UUID suffix so repeated or parallel runs receive distinct diagnostic directories.

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
- Preconditions: A configured temporary index contains pages and can be replaced with an empty or unavailable index.
- Action: Call all five MCP tools with successful, empty, unknown-site, missing-page, invalid-argument, and recoverable index-failure inputs.
- Expected Result: Every tool returns its documented JSON contract. Configuration failures return `configuration_unavailable` with a fixed safe message; missing or corrupt source indexes are reported as `index_unavailable`, missing pages retain `site_name`, the requested `url`, and `page: null`, site listings mark unavailable indexes without raising, and vector failures return a fixed safe message for each stable public error code. Raw exception text, credentials, URLs, SQL details, and absolute, relative, spaced, or UNC paths are available only in server-side logs. Non-search successes include `ok: true` and `contract_version`; expected failures include stable `error.code` values and no internal diagnostics. `search_docs` preserves its `mode`, hit counters, ordering, source labels, fallback error details, and default limit of 10.

#### TS-TF-007
- Purpose: Verify the end-to-end crawl smoke path.
- Preconditions: `CONTAINER_BIN` points to a working Podman or Docker binary, and Playwright Chromium is installed through the active interpreter.
- Expected Result: A temporary static site served from a container is crawled headlessly and indexed into a temporary SQLite file.

#### TS-TF-008
- Purpose: Verify the end-to-end MCP stdio path.
- Preconditions: A prepared local SQLite index exists for the temporary runtime workspace.
- Action: Start the isolated stdio server and call `get_sites`, `get_version`, `list_pages`, `search_docs`, and `fetch_page`, including an unknown-site and invalid-argument call.
- Expected Result: Every response is valid JSON with the documented contract metadata and result/error fields; search content and page content are preserved, expected failures are structured, and MCP stdout contains no diagnostic output.

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
- Preconditions: Both wheel paths exist; the fixture contains valid `config/sites.yaml`, non-empty readable SQLite indexes with pages, a valid vector sidecar for each hybrid/vector site, and the stable request corpus; Podman or Docker is available through `CONTAINER_BIN`.
- Action: Run `python -m docmcp.harness` or `make harness`.
- Expected Result: The harness validates each source index as a non-empty readable SQLite database containing pages, and validates each hybrid/vector sidecar as a readable schema-versioned SQLite-vec database with matching source metadata and non-empty vector records before building two tagged images, `<HARNESS_IMAGE>:baseline` and `<HARNESS_IMAGE>:current`, with shared dependency/model layers and one target wheel in the final layer. Both isolated containers receive identical requests; runtime startup does not reinstall dependencies or download the model. The MCP-only wheel derives its dependency metadata from the same pinned `requirements-mcp.txt` profile used by the image builder. The corpus starts with `initialize`, sends `notifications/initialized` without an ID, then requests `get_version`, searches `Harness Docs` for `alpha`, searches for `missing phrase`, and searches the missing `Missing Docs` site. The harness compares those responses and ignores only documented allowlisted fields; it does not claim domain-specific semantic queries or assert a particular vector/hybrid response mode in this scenario. Stale containers labeled `docmcp.harness=true` are removed before startup. Unexpected differences or startup, timeout, malformed-response, and runtime failures fail while retaining redacted artifacts. Container stderr must stream directly into the version artifact while MCP stdout is processed, so verbose pip, HTTP, model-download, and server diagnostics cannot fill a pipe and block JSON-RPC responses. MCP stdout remains JSON-RPC only.
- Unit coverage of the default Podman setting must clear any process-level `CONTAINER_BIN` override so CI runtime selection does not affect the assertion.
- Cleanup: The container command uses `--rm`; inspect the timestamped artifact directory if the comparison fails.

#### TS-TF-014
- Purpose: Prevent credential-like values from being preserved in structured harness diagnostics.
- Preconditions: A temporary artifact path is writable.
- Action: Write nested dictionaries, lists, and JSON-encoded text containing credential-like keys through the harness artifact writer.
- Expected Result: The resulting JSON remains valid and contains `[REDACTED]` in place of credential values at every nested level.

#### TS-TF-015
- Purpose: Reject unsafe or ambiguous optional harness settings before container execution.
- Preconditions: Baseline and current wheel paths and a valid fixture exist.
- Action: Load configurations with invalid `HARNESS_VERBOSE` or `HARNESS_IMAGE` values.
- Expected Result: Configuration loading raises `HarnessError` identifying the invalid setting.

#### TS-TF-016
- Purpose: Fail safely when an MCP server violates the request/response protocol or exits before responding.
- Preconditions: A temporary harness output directory is writable.
- Action: Run a test server that emits malformed JSON, a response with the wrong request ID, or no response.
- Expected Result: The harness raises `HarnessError`, terminates the child process, and retains the per-version diagnostic output. A comparison difference also creates `failure.log` in the run artifact directory.

#### TS-TF-017
- Purpose: Preserve the MCP initialization handshake when the harness drives the server with raw JSON-RPC.
- Preconditions: The fixture corpus contains an `initialize` request followed by a `notifications/initialized` notification without an ID.
- Action: Run the version harness against a test server that emits responses only for requests with IDs.
- Expected Result: Corpus validation accepts the notification, the runner sends it after initialization, does not wait for or append a response for it, and continues with `get_version` and `search_docs` requests.

#### TS-TF-018
- Purpose: Prevent pip and server diagnostics from persisting credential-like values while preserving nonblocking stderr draining.
- Preconditions: A temporary harness output directory is writable and a test server emits large stderr content containing credential-like values.
- Action: Run the version harness once to successful completion and once with a response failure.
- Expected Result: MCP stdout processing continues while stderr is drained, and each retained `stderr.log` contains `[REDACTED]` instead of the credential values.

#### TS-TF-019
- Purpose: Prevent a partial MCP response from bypassing the per-request timeout through a blocking `readline()` call.
- Preconditions: A temporary harness output directory is writable and a test server writes an incomplete JSON fragment without a newline, then stalls.
- Action: Run the version harness with the standard response timeout.
- Expected Result: The runner buffers available stdout bytes, waits only until the single request deadline for a newline, and raises `HarnessError` when the response remains incomplete.

#### TS-TF-020
- Purpose: Prevent invalid fixtures from passing preflight and silently forcing hybrid/vector searches onto fallback paths.
- Preconditions: A fixture contains configured source indexes and a hybrid/vector site.
- Action: Run harness configuration validation with an empty/corrupt source index, a missing sidecar, stale sidecar metadata, or an empty sidecar.
- Expected Result: Validation raises an actionable `HarnessError` before container startup; a valid source index and matching non-empty vector sidecar pass preflight. If the sidecar embedding model differs from the model configured in `sites.yaml`, the error identifies both model values and tells the operator to rebuild the sidecar with the configured model.

#### TS-TF-021
- Purpose: Keep direct and Make-based harness invocation aligned on container-runtime selection.
- Preconditions: The repository `.env` may define `CONTAINER_BIN`, and the process may provide an explicit override.
- Action: Load harness configuration with no process override, then with a process/Make override.
- Expected Result: The process/Make value wins; otherwise the repository `.env` value wins; `.env-harness` and finally Podman provide fallback values.

#### TS-TF-022
- Purpose: Protect the packaged MCP-only wheel transformation from metadata, archive-integrity, naming, and installation regressions.
- Preconditions: A minimal valid source wheel and pinned MCP requirements file are available in temporary paths.
- Action: Run `build_mcp_wheel` on the source wheel, inspect the generated archive and RECORD entries, then install it with pip without dependencies and import the packaged module.
- Expected Result: The output uses the `doc_mcp_no_crawler` filename and dist-info directory, metadata contains only the pinned MCP requirements, entry points expose only `docmcp-server`, every non-RECORD archive member has a matching hash/size, and pip installs/imports the resulting wheel successfully. Coverage must include both a deterministic synthetic source wheel for focused rewrite assertions and a wheel produced from the repository by its configured build backend, so build-generated metadata and package layout are exercised in CI.

#### TS-TF-023
- Purpose: Prevent parallel or same-second harness runs from colliding before diagnostics are created.
- Preconditions: A writable artifact root is available.
- Action: Create multiple run directories concurrently from separate processes under the same writable artifact root.
- Expected Result: Every directory exists, uses the UTC timestamp plus UUID format, and has a distinct name; no process fails because another process created a run directory at the same time.

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
- `TS-TF-015` -> `tests/test_harness.py::{test_load_config_rejects_invalid_verbose_value,test_load_config_rejects_invalid_image_value}`
- `TS-TF-016` -> `tests/test_harness.py::{test_run_version_rejects_malformed_response,test_run_version_rejects_mismatched_response_id,test_run_version_rejects_early_server_exit,test_run_harness_preserves_comparison_failure_artifact}`
- `TS-TF-017` -> `tests/test_harness.py::{test_load_config_validates_initialized_notification,test_run_version_skips_notification_responses}`
- `TS-TF-018` -> `tests/test_harness.py::{test_run_version_redacts_stderr_artifact,test_run_version_redacts_stderr_on_failure}`
- `TS-TF-019` -> `tests/test_harness.py::test_run_version_times_out_on_partial_response`
- `TS-TF-020` -> `tests/test_harness.py::{test_load_config_rejects_empty_index,test_load_config_rejects_missing_hybrid_vector_sidecar,test_load_config_rejects_empty_hybrid_vector_sidecar,test_validate_vector_sidecar_reports_embedding_model_mismatch}`
- `TS-TF-021` -> `tests/test_harness.py::{test_load_config_uses_project_env_container_runtime,test_load_config_process_runtime_overrides_project_env}`
- `TS-TF-022` -> `tests/test_packaging.py::{test_build_mcp_wheel_rewrites_and_installs_minimal_wheel,test_build_mcp_wheel_rewrites_real_repository_wheel}`
- `TS-TF-023` -> `tests/test_harness.py::{test_create_run_dir_uses_unique_timestamped_names,test_create_run_dir_is_safe_for_parallel_processes}`

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
