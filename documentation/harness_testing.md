# Harness Testing Guide

## Document Control
- Status: Review
- Owner: Documentation Maintainers
- Reviewers: Repository maintainers
- Created: 2026-08-15
- Last Updated: 2026-08-29
- Version: v3.2
- Related Tickets: veep2012/doc_mcp#14, veep2012/doc_mcp#2

## Change Log
- 2026-08-29 | v3.2 | Confirmed that contract version 1.1 is part of the MCP comparison surface and any baseline/current contract mismatch must fail the harness comparison.
- 2026-08-23 | v3.1 | Clarified that `contract_version` differences are semantic incompatibilities that must fail comparison, and documented the exact package-version paths that may be allowlisted while retaining all other response fields.
- 2026-08-16 | v3.0 | Documented the required `notifications/initialized` handshake, notification no-response behavior, redacted nonblocking stderr artifact handling, deadline-bound partial-response handling, source/vector fixture integrity preflight, container-runtime precedence, deterministic fixture index/sidecar regeneration, actual checked-in corpus coverage, end-to-end MCP-only wheel rewrite verification, collision-resistant artifact directories, explicit vector embedding-model mismatch diagnostics, and CI validation of the real MCP-only wheel metadata.
- 2026-08-15 | v1.9 | Documented recursive credential redaction, corrected direct source-tree invocation and optional requirements configuration, and synchronized harness scenario coverage.

## Purpose
Explain how to run the packaged-version harness that sends one stable MCP request corpus to a baseline wheel and a current wheel, then fails on any response difference that is not explicitly allowlisted.

## Scope
- In scope:
  - Local harness setup and execution.
  - Wheel selection, fixture preparation, and safe configuration.
  - Container-runtime selection and CI usage.
  - Harness artifacts, expected results, and failure diagnosis.
- Out of scope:
  - Building a production documentation index.
  - End-to-end browser authentication or live-site crawling.
  - Replacing the unit tests in `tests/test_harness.py`.

## Audience
- Contributors comparing a release wheel with a new build.
- Maintainers validating packaged MCP behavior before release.
- CI maintainers troubleshooting a harness failure.

## Definitions
- **Baseline wheel**: The packaged `doc-mcp` version whose responses are the comparison reference.
- **Current wheel**: The packaged `doc-mcp` version being validated.
- **Fixture**: Sanitized configuration, request corpus, and local SQLite index mounted into both containers.
- **Allowlist**: Dot-separated response paths removed before comparison because their differences are expected. Paths may traverse object keys, list indexes, and JSON-encoded tool text.

## Background / Context
The harness validates installed wheels rather than importing the working tree. It starts one isolated container for each wheel, installs the wheel into that container, sends the same newline-delimited MCP JSON-RPC requests to both servers, and compares the parsed responses in request order. The corpus sends `initialize`, then the MCP-required `notifications/initialized` notification without an `id`; the runner does not wait for or compare a response for that notification. The fixture is mounted read-only, and no production configuration or credentials are needed.

## Requirements
### Functional Requirements
- FR-1: The baseline and current wheel paths must point to existing `.whl` files.
- FR-2: The fixture must contain valid `config/sites.yaml`, non-empty readable SQLite indexes containing pages, valid vector sidecars for hybrid/vector sites, and a local `mcp_requests.json` copied from the tracked example.
- FR-3: The request corpus must include `initialize`, a response-free `notifications/initialized` notification immediately afterward, `get_version`, and at least three `search_docs` calls; the fixture's hybrid/vector configuration must exercise the vector backend.
- FR-4: The harness must fail on malformed responses, startup failures, timeouts, unavailable runtimes, non-allowlisted response differences, and any `contract_version` mismatch.
- FR-4a: Each run must remove containers labeled `docmcp.harness=true` before starting new comparison containers.
- FR-5: Only explicitly configured response paths may be ignored during comparison.

### Non-Functional Requirements
- NFR-1: Fixture data must be sanitized and must not contain credentials or production data.
- NFR-2: Both wheels must receive the identical request corpus and fixture.
- NFR-3: Failed runs must retain enough redacted diagnostics to reproduce the investigation.

## Design / Behavior

### What the harness runs

The Make target is a thin launcher:

```text
make harness
  -> .venv/bin/python -m docmcp.harness
  -> remove stale containers labeled docmcp.harness=true
  -> container build --tag docmcp-harness:baseline ...
  -> container build --tag docmcp-harness:current ...
  -> container run --rm -i --label docmcp.harness=true docmcp-harness:baseline ...
  -> container run --rm -i --label docmcp.harness=true docmcp-harness:current ...
  -> exec docmcp-server
```

The runner mounts the fixture at `/fixture` read-only and the wheel directory at `/wheels` read-only. It passes `DOC_MCP_HOME=/fixture` and `CONFIG_FILE=config/sites.yaml` to each container. The container is removed automatically after the comparison because the command uses `--rm`.

### Repository files involved

- `.env-harness` - local harness settings, generated image repository name, and wheel paths.
- `requirements.txt` - single-source, pinned full runtime dependency profile used by the full wheel and development installation.
- `requirements-mcp.txt` - pinned MCP/vector dependency profile used by the harness and MCP-only wheel builder.
- `scripts/build_mcp_wheel.py` - derives the MCP-only wheel metadata from the full wheel and reads dependencies from `requirements-mcp.txt`.
- `tests/fixtures/harness/config/sites.yaml` - sanitized site configuration.
- `tests/fixtures/harness/mcp_requests.json.example` - tracked example MCP request corpus.
- `tests/fixtures/harness/mcp_requests.json` - local request corpus copied from the example; ignored by Git.
  - `tests/fixtures/harness/index/example.db` - local SQLite index required by the fixture; the `index/` path is ignored by Git and must be created locally.
- `src/docmcp/harness/config.py` - settings and fixture validation.
- `src/docmcp/harness/runner.py` - container execution and artifact creation.
- `tests/test_harness.py` - unit coverage for validation, comparison, command quoting, failure boundaries, artifact redaction, and preserved failure diagnostics.

## Setup

### 1. Create the project environment

From the repository root:

```bash
make local-venv
```

This creates `.venv` and installs the development requirements. The harness itself needs the project dependencies, the Python build tooling, and a working Podman or Docker installation.

### 2. Prepare the two wheels

Build the current wheel from the checkout:

```bash
make wheel
ls -1 dist/*.whl
```

`make wheel` produces two current-version artifacts: the normal full wheel
(`doc_mcp-<version>-py3-none-any.whl`) with crawler and vector dependencies,
and an MCP-only wheel (`doc_mcp_no_crawler-<version>-py3-none-any.whl`) with only the
MCP-serving dependency profile and only the `docmcp-server` console executable.
The harness uses `requirements-mcp.txt` and installs either target wheel with
`--no-deps`. The profile includes FastEmbed and sqlite-vec because the harness
fixture uses hybrid search and must exercise vector lookup, but it excludes
crawler-only packages such as Playwright, markdownify, and pypdf.

Obtain the baseline wheel from a release artifact, previous build, or another checked-out revision. Keep both wheels in a directory accessible to the harness. For example:

```bash
mkdir -p /tmp/docmcp-harness-wheels
cp dist/doc_mcp-*.whl /tmp/docmcp-harness-wheels/current.whl
cp /path/to/baseline/doc_mcp-*.whl /tmp/docmcp-harness-wheels/baseline.whl
```

The filenames do not need to be named `baseline.whl` and `current.whl`; the environment file may point directly to the generated names.

### 3. Create the local fixture index

The repository stores the fixture configuration and corpus, but not the SQLite database. Create it once after checkout, or recreate it whenever the fixture content changes:

```bash
mkdir -p tests/fixtures/harness/index
rm -f tests/fixtures/harness/index/example.db tests/fixtures/harness/index/example.vec.db
.venv/bin/python - <<'PY'
from docmcp.index_store import init_db, upsert_page

index = "tests/fixtures/harness/index/example.db"
init_db(index)
upsert_page(index, "https://example.test/alpha", "Alpha", "Alpha documentation content.")
upsert_page(index, "https://example.test/beta", "Beta", "Beta documentation content.")
PY

PYTHONPATH=src .venv/bin/python -m docmcp.vectorize_cli --site "Harness Docs"
test -s tests/fixtures/harness/index/example.db
test -s tests/fixtures/harness/index/example.vec.db
```

The reset makes regeneration deterministic from the two fixture pages. The vectorizer reads the configured `index/example.db` and replaces the derived `index/example.vec.db` sidecar using the checked-in embedding model and vectorizer settings.

The checked-in corpus initializes the MCP session, sends `notifications/initialized`, requests `get_version`, searches `Harness Docs` for `alpha`, exercises a missing phrase, and requests a missing site. The guide does not promise domain-specific semantic queries or a particular `mode` in this corpus; those behaviors require separate fixture data and assertions. Keep the configured site name and index path aligned with `tests/fixtures/harness/config/sites.yaml`.

Create the local request corpus from the visible example:

```bash
cp tests/fixtures/harness/mcp_requests.json.example tests/fixtures/harness/mcp_requests.json
```

### 4. Configure `.env-harness`

Use a local copy while editing paths:

```bash
cp .env-harness .env-harness.local
```

Example configuration:

```dotenv
HARNESS_BASELINE_WHEEL=/tmp/docmcp-harness-wheels/baseline.whl
HARNESS_CURRENT_WHEEL=/tmp/docmcp-harness-wheels/current.whl
HARNESS_FIXTURE_DIR=tests/fixtures/harness
HARNESS_ARTIFACT_DIR=artifacts/harness
HARNESS_IMAGE=docmcp-harness
HARNESS_ALLOWLIST=result.serverInfo.version,result.content.0.text.version,result.structuredContent.result.version
HARNESS_VERBOSE=false
HARNESS_REQUIREMENTS_FILE=requirements-mcp.txt
```

Run the harness with the local file when possible:

```bash
cp .env-harness.local .env-harness
```

The required settings are:

| Setting | Meaning |
| --- | --- |
| `HARNESS_BASELINE_WHEEL` | Existing baseline `.whl` path. |
| `HARNESS_CURRENT_WHEEL` | Existing current `.whl` path. |
| `HARNESS_FIXTURE_DIR` | Fixture root containing `config/sites.yaml`, indexes, and the corpus. |
| `HARNESS_ARTIFACT_DIR` | Root directory for timestamped run diagnostics. |

Optional settings are `HARNESS_IMAGE`, `HARNESS_ALLOWLIST`, `HARNESS_VERBOSE`, and `HARNESS_REQUIREMENTS_FILE`. `HARNESS_IMAGE` is the generated image repository prefix; the harness builds `<prefix>:baseline` and `<prefix>:current` from `python:3.11-slim`. Image-build stdout and stderr are shown live in the terminal, while only server stderr is written to the per-version artifacts. `HARNESS_REQUIREMENTS_FILE` defaults to `requirements-mcp.txt` when that file exists. Set `HARNESS_VERBOSE=true` to retain pip dependency-resolution output and enable `MCP_LOG_LEVEL=DEBUG` in the container. The harness uses fixed internal safety limits: 15 minutes per image build and 180 seconds per MCP request/process shutdown. Container stderr is drained on a dedicated path while MCP stdout is processed, preventing verbose diagnostics from filling a subprocess pipe and blocking JSON-RPC responses; chunks are redacted before writing and the completed `stderr.log` is sanitized again on success and failure cleanup. MCP stdout is buffered until a complete newline-delimited response arrives, and the same request deadline covers partial fragments and the wait for that newline. Pip diagnostics never share stdout with the MCP JSON-RPC stream. Relative paths resolve from the repository root passed to the harness.

Do not put secrets, tokens, passwords, certificates, private keys, connection strings, or production data in `.env-harness`. The loader rejects settings whose names look secret-bearing.

### 5. Select Podman or Docker

The runtime precedence is explicit process/Make override, then `CONTAINER_BIN` in the repository `.env`, then `.env-harness`, and finally Podman:

```bash
make harness
```

Use Docker when it is the available runtime or Podman networking is unavailable:

```bash
make CONTAINER_BIN=docker harness
```

For a direct Python invocation, the process environment overrides the repository `.env`:

```bash
CONTAINER_BIN=docker PYTHONPATH=src .venv/bin/python -m docmcp.harness
```

The selected executable must be discoverable on `PATH` and able to run Linux containers.

## Running the harness

### Standard run

After setup, run:

```bash
make harness
```

Or invoke the module directly:

```bash
PYTHONPATH=src .venv/bin/python -m docmcp.harness
```

A successful run prints the UTC-timestamped, collision-resistant artifact directory:

```text
MCP comparison passed. Artifacts: artifacts/harness/20260815T120000Z-5e2f4a9c3d1b4f7a8c6d2e1f9a0b3c4d
```

The command exits with status `0` only when all normalized responses match.

### Comparing a deliberate behavior change

The current public MCP contract version is `1.1`.

If a response difference is intentional, first decide whether it is a semantic contract change or nondeterministic metadata. A `contract_version` difference is a semantic incompatibility and must fail comparison; it must never be added to `HARNESS_ALLOWLIST`. Only nondeterministic, non-semantic fields belong in the allowlist. `initialize` exposes the package version at `result.serverInfo.version`; `get_version` returns a JSON-encoded payload in both `result.content.0.text` and `result.structuredContent.result`. To ignore only the package version key in all three locations while retaining every other tool field:

```dotenv
HARNESS_ALLOWLIST=result.serverInfo.version,result.content.0.text.version,result.structuredContent.result.version
```

Do not allowlist an entire response, tool result, or error object to make a failing comparison pass. Update the request corpus or the expected product behavior separately when the contract intentionally changes.

## Request corpus and fixture rules

Each request in the local `mcp_requests.json` must be a JSON object containing `jsonrpc: "2.0"` and a `method`; normal requests contain an `id`, while notifications do not. Start from the tracked `mcp_requests.json.example` when creating or updating the local corpus. The validator requires:

- one `initialize` request;
- one `notifications/initialized` notification immediately after `initialize`, without an ID;
- one `tools/call` request for `get_version`;
- at least three `tools/call` requests for `search_docs`;
- valid request IDs on every non-notification entry and valid methods on every entry.

The fixture configuration must resolve successfully. Every configured `index_file` must be a non-empty readable SQLite database containing pages. Each hybrid/vector site must also have its resolved `.vec.db` sidecar with matching source metadata, the supported sidecar schema, the configured embedding model, and non-empty vector records; otherwise preflight fails instead of allowing an always-fallback comparison. If the sidecar was built with a different embedding model, the preflight error identifies both the sidecar and configured models and instructs the operator to rebuild it. The fixture should include success, empty-result, and error behavior so a version change cannot silently break only one response class.

When extending the corpus:

1. Add the request to `tests/fixtures/harness/mcp_requests.json.example`.
2. Copy the example to `tests/fixtures/harness/mcp_requests.json` locally.
3. Keep IDs unique and stable on request entries.
4. Use the same fixture data for both wheel runs.
5. Update TS-TF-013 in [the test scenario catalog](test_scenarios/testing_framework_test_scenarios.md) if the acceptance behavior or coverage changes.
6. Run `tests/test_harness.py` and a real harness comparison.

## Artifacts and expected results

Each successful run creates a unique UTC-timestamped directory with a UUID suffix under `HARNESS_ARTIFACT_DIR`:

```text
artifacts/harness/<timestamp>-<uuid>/
├── baseline/
│   ├── command.log
│   ├── responses.json
│   └── stderr.log
├── current/
│   ├── command.log
│   ├── responses.json
│   └── stderr.log
├── normalized/
│   ├── baseline.json
│   └── current.json
├── diff.json
└── summary.md
```

`normalized/` contains responses after allowlisted paths are removed. `diff.json` contains the request index and both values for every unexpected difference. When a run fails after artifact creation, `failure.log` records the error. Text and JSON diagnostics recursively redact credential-like values, including nested objects and JSON-encoded tool text.

To investigate a failure:

```bash
find artifacts/harness -maxdepth 2 -type f -print
sed -n '1,160p' artifacts/harness/<timestamp>/failure.log
sed -n '1,240p' artifacts/harness/<timestamp>/baseline/stderr.log
sed -n '1,240p' artifacts/harness/<timestamp>/diff.json
```

Common failure categories are:

- **Wheel validation**: a path is missing, not a file, or does not end in `.whl`.
- **Fixture validation**: `sites.yaml`, an index, or the request corpus is missing or invalid.
- **Runtime unavailable**: the selected Podman/Docker executable is not on `PATH`.
- **Stale harness containers**: interrupted runs are cleaned automatically on the next run using the dedicated `docmcp.harness=true` label; unrelated containers are not removed.
- **Startup failure**: the wheel cannot install or `docmcp-server` exits before responding.
- **Malformed or mismatched response**: stdout is not one valid JSON response per request or the response ID differs from the request ID.
- **Timeout**: an image build exceeds 15 minutes or an MCP request exceeds 180 seconds.
- **Unexpected difference**: normalized baseline and current responses differ.

## CI usage

CI must make both wheel artifacts available before invoking the harness. A typical sequence is:

```bash
make local-venv
make wheel
# Place the baseline wheel and current wheel at the paths in .env-harness.
CONTAINER_BIN=docker make harness
```

The repository’s general CI test command uses Docker for smoke tests. The harness should use the same runtime unless the CI job explicitly provisions another supported runtime. Do not upload `.env-harness` when it contains machine-specific paths; upload only the redacted artifact directory when diagnostics are needed.

CI also runs `make wheel` and inspects the generated `doc_mcp_no_crawler-*.whl` before tests. The check requires the MCP distribution name and pinned MCP dependency, and rejects Playwright or crawler dependencies. This complements the pytest-level synthetic and repository-built wheel installation tests.

## Security / Permissions

- Use only sanitized fixture data.
- Do not mount a production configuration or credential directory into the harness.
- Keep wheel and fixture mounts read-only; the runner enforces read-only mounts for both.
- Review `command.log`, `stderr.log`, and `failure.log` before sharing them outside the repository.
- Store generated artifacts under a local or CI artifact directory, not in the committed source tree.

## Edge Cases
- A fresh checkout has no `tests/fixtures/harness/index/example.db` or its vector sidecar because `index/` is ignored; create both before running.
- A process-level or Make `CONTAINER_BIN` overrides the repository `.env`, `.env-harness`, and the Podman default.
- A missing index is not created by read-only search operations; fixture validation fails first.
- A configuration error occurs before the unique run directory is created, so there may be no `failure.log` for configuration-only failures.
- Run directories use a UTC timestamp plus UUID suffix; parallel and same-second runs therefore retain separate diagnostics.
- Version strings and other nondeterministic fields must be allowlisted by their exact response path, not by broad structural paths.
- A changed response caused by a real product behavior change should be reviewed as a compatibility decision, not hidden with an allowlist entry.

## Testing Strategy
- Unit tests: `tests/test_harness.py` validates safe settings, fixture and corpus rules, response comparison, and shell-command quoting.
- Scenario coverage: TS-TF-013 through TS-TF-023 in `documentation/test_scenarios/testing_framework_test_scenarios.md` define packaged comparison, artifact-redaction, invalid-option, failure-boundary, protocol-notification, stderr-redaction, partial-response timeout, fixture-integrity, runtime-precedence, wheel-rewrite, and unique-artifact-directory acceptance criteria.
- Manual verification: run a real comparison with two available wheels and inspect `summary.md`, `diff.json`, and the baseline/current responses.

## Rollout / Migration
- No migration is required.
- Contributors should create the ignored fixture index locally after checkout.
- Existing `.env-harness` users should add explicit absolute wheel paths and use `result.serverInfo.version` when version-only differences are expected.

## Risks and Mitigations
- Risk: A broad allowlist hides a real regression.
  - Mitigation: Allowlist only exact known nondeterministic response paths and review `diff.json`.
- Risk: Local fixture data differs between baseline and current runs.
  - Mitigation: Mount one sanitized fixture read-only into both containers.
- Risk: A wheel works from the source tree but fails when installed.
  - Mitigation: The harness installs and executes each wheel inside a clean container.

## Open Questions
- Should CI publish a dedicated baseline wheel artifact for the harness instead of requiring a caller-provided path?

## References
- [README.md](../README.md)
- [documentation/mcp-server.md](mcp-server.md)
- [documentation/test_scenarios/testing_framework_test_scenarios.md](test_scenarios/testing_framework_test_scenarios.md)
- [Makefile](../Makefile)
- [src/docmcp/harness/config.py](../src/docmcp/harness/config.py)
- [src/docmcp/harness/runner.py](../src/docmcp/harness/runner.py)
- [tests/fixtures/harness/config/sites.yaml](../tests/fixtures/harness/config/sites.yaml)
- [tests/fixtures/harness/mcp_requests.json.example](../tests/fixtures/harness/mcp_requests.json.example)
- [tests/test_harness.py](../tests/test_harness.py)
