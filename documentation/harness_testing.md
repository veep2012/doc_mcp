# Harness Testing Guide

## Document Control
- Status: Review
- Owner: Documentation Maintainers
- Reviewers: Repository maintainers
- Created: 2026-08-15
- Last Updated: 2026-08-15
- Version: v1.2
- Related Tickets: veep2012/doc_mcp#2

## Change Log
- 2026-08-15 | v1.2 | Added the minimum supported baseline requirement: `doc-mcp 1.1.1` or newer.

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
- **Minimum baseline**: `doc-mcp 1.1.1`; earlier wheels are unsupported because they do not pin the runtime dependency versions required for reproducible startup.

## Background / Context
The harness validates installed wheels rather than importing the working tree. It starts one isolated container for each wheel, installs the wheel into that container, sends the same newline-delimited MCP JSON-RPC requests to both servers, and compares the parsed responses in request order. The fixture is mounted read-only, and no production configuration or credentials are needed.

## Requirements
### Functional Requirements
- FR-1: The baseline and current wheel paths must point to existing `.whl` files.
- FR-1a: The baseline wheel must be `doc-mcp 1.1.1` or newer. Earlier baseline wheels are unsupported.
- FR-2: The fixture must contain valid `config/sites.yaml`, every configured index file, and a local `mcp_requests.json` copied from the tracked example.
- FR-3: The request corpus must include `initialize`, `get_version`, and at least three `search_docs` calls.
- FR-4: The harness must fail on malformed responses, startup failures, timeouts, unavailable runtimes, and non-allowlisted response differences.
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
  -> container run --rm -i ...
  -> pip install wheel && exec docmcp-server
```

The runner mounts the fixture at `/fixture` read-only and the wheel directory at `/wheels` read-only. It passes `DOC_MCP_HOME=/fixture` and `CONFIG_FILE=config/sites.yaml` to each container. The container is removed automatically after the comparison because the command uses `--rm`.

### Repository files involved

- `.env-harness` - local harness settings and wheel paths.
- `tests/fixtures/harness/config/sites.yaml` - sanitized site configuration.
- `tests/fixtures/harness/mcp_requests.json.example` - tracked example MCP request corpus.
- `tests/fixtures/harness/mcp_requests.json` - local request corpus copied from the example; ignored by Git.
- `tests/fixtures/harness/index/ld_docs.db` - local SQLite index required by the fixture; the `index/` path is ignored by Git and must be created locally.
- `src/docmcp/harness/config.py` - settings and fixture validation.
- `src/docmcp/harness/runner.py` - container execution and artifact creation.
- `tests/test_harness.py` - unit coverage for validation, comparison, and command quoting.

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

Obtain the baseline wheel from a release artifact, previous build, or another checked-out revision. Keep both wheels in a directory accessible to the harness. For example:

```bash
mkdir -p /tmp/docmcp-harness-wheels
cp dist/doc_mcp-*.whl /tmp/docmcp-harness-wheels/current.whl
cp /path/to/baseline/doc_mcp-*.whl /tmp/docmcp-harness-wheels/baseline.whl
```

The minimum supported baseline is `doc-mcp 1.1.1`. Use `1.1.1` or a newer
wheel for `HARNESS_BASELINE_WHEEL`; earlier releases declare broad dependency
ranges and can resolve incompatible MCP runtime versions during the isolated
container install. The current wheel may be the same version or newer.

The filenames do not need to be named `baseline.whl` and `current.whl`; the environment file may point directly to the generated names.

### 3. Create the local fixture index

The repository stores the fixture configuration and corpus, but not the SQLite database. Create it once after checkout, or recreate it whenever the fixture content changes:

```bash
mkdir -p tests/fixtures/harness/index
.venv/bin/python - <<'PY'
from docmcp.index_store import init_db, upsert_page

index = "tests/fixtures/harness/index/ld_docs.db"
init_db(index)
upsert_page(index, "https://example.test/alpha", "Alpha", "Alpha documentation content.")
upsert_page(index, "https://example.test/beta", "Beta", "Beta documentation content.")
PY
```

The checked-in corpus queries `Harness Docs`, searches for `alpha`, exercises a missing phrase, and requests a missing site. Keep the configured site name and index path aligned with `tests/fixtures/harness/config/sites.yaml`.

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
HARNESS_IMAGE=python:3.11-slim
HARNESS_TIMEOUT_SECONDS=30
HARNESS_ALLOWLIST=result.serverInfo.version,result.content.0.text.version,result.structuredContent.result.version
```

Run the harness with the local file when possible:

```bash
cp .env-harness.local .env-harness
```

The required settings are:

| Setting | Meaning |
| --- | --- |
| `HARNESS_BASELINE_WHEEL` | Existing baseline `.whl` path; the baseline must be `doc-mcp 1.1.1` or newer. |
| `HARNESS_CURRENT_WHEEL` | Existing current `.whl` path. |
| `HARNESS_FIXTURE_DIR` | Fixture root containing `config/sites.yaml`, indexes, and the corpus. |
| `HARNESS_ARTIFACT_DIR` | Root directory for timestamped run diagnostics. |

Optional settings are `HARNESS_IMAGE`, `HARNESS_TIMEOUT_SECONDS`, and `HARNESS_ALLOWLIST`. Relative paths resolve from the repository root passed to the harness.

Do not put secrets, tokens, passwords, certificates, private keys, connection strings, or production data in `.env-harness`. The loader rejects settings whose names look secret-bearing.

### 5. Select Podman or Docker

The default runtime is Podman:

```bash
make harness
```

Use Docker when it is the available runtime or Podman networking is unavailable:

```bash
make CONTAINER_BIN=docker harness
```

The process environment takes precedence over `CONTAINER_BIN` in `.env-harness`. For a direct Python invocation:

```bash
CONTAINER_BIN=docker .venv/bin/python -m docmcp.harness
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

A successful run prints the timestamped artifact directory:

```text
MCP comparison passed. Artifacts: artifacts/harness/20260815T120000Z
```

The command exits with status `0` only when all normalized responses match.

### Comparing a deliberate behavior change

If a response difference is intentional, first decide whether it is a semantic contract change or nondeterministic metadata. Only nondeterministic, non-semantic fields belong in `HARNESS_ALLOWLIST`. `initialize` exposes the version at `result.serverInfo.version`; `get_version` returns a JSON-encoded payload in both `result.content.0.text` and `result.structuredContent.result`. To ignore only the version key in all three locations while retaining every other tool field:

```dotenv
HARNESS_ALLOWLIST=result.serverInfo.version,result.content.0.text.version,result.structuredContent.result.version
```

Do not allowlist an entire response, tool result, or error object to make a failing comparison pass. Update the request corpus or the expected product behavior separately when the contract intentionally changes.

## Request corpus and fixture rules

Each request in the local `mcp_requests.json` must be a JSON object containing `jsonrpc: "2.0"`, an `id`, and a `method`. Start from the tracked `mcp_requests.json.example` when creating or updating the local corpus. The validator requires:

- one `initialize` request;
- one `tools/call` request for `get_version`;
- at least three `tools/call` requests for `search_docs`;
- valid request IDs and methods on every entry.

The fixture configuration must resolve successfully, and every configured `index_file` must already exist. The fixture should include success, empty-result, and error behavior so a version change cannot silently break only one response class.

When extending the corpus:

1. Add the request to `tests/fixtures/harness/mcp_requests.json.example`.
2. Copy the example to `tests/fixtures/harness/mcp_requests.json` locally.
2. Keep IDs unique and stable.
3. Use the same fixture data for both wheel runs.
4. Update TS-TF-013 in [the test scenario catalog](test_scenarios/testing_framework_test_scenarios.md) if the acceptance behavior or coverage changes.
5. Run `tests/test_harness.py` and a real harness comparison.

## Artifacts and expected results

Each successful run creates a timestamped directory under `HARNESS_ARTIFACT_DIR`:

```text
artifacts/harness/<timestamp>/
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

`normalized/` contains responses after allowlisted paths are removed. `diff.json` contains the request index and both values for every unexpected difference. When a run fails after artifact creation, `failure.log` records the error. Captured text diagnostics are passed through credential-like value redaction.

To investigate a failure:

```bash
find artifacts/harness -maxdepth 2 -type f -print
sed -n '1,160p' artifacts/harness/<timestamp>/failure.log
sed -n '1,240p' artifacts/harness/<timestamp>/diff.json
```

Common failure categories are:

- **Wheel validation**: a path is missing, not a file, or does not end in `.whl`.
- **Fixture validation**: `sites.yaml`, an index, or the request corpus is missing or invalid.
- **Runtime unavailable**: the selected Podman/Docker executable is not on `PATH`.
- **Startup failure**: the wheel cannot install or `docmcp-server` exits before responding.
- **Malformed or mismatched response**: stdout is not one valid JSON response per request or the response ID differs from the request ID.
- **Timeout**: a response is not produced within `HARNESS_TIMEOUT_SECONDS`.
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

## Security / Permissions

- Use only sanitized fixture data.
- Do not mount a production configuration or credential directory into the harness.
- Keep wheel and fixture mounts read-only; the runner enforces read-only mounts for both.
- Review `command.log`, `stderr.log`, and `failure.log` before sharing them outside the repository.
- Store generated artifacts under a local or CI artifact directory, not in the committed source tree.

## Edge Cases
- A fresh checkout has no `tests/fixtures/harness/index/ld_docs.db` because `index/` is ignored; create the index before running.
- A process-level `CONTAINER_BIN` can override the runtime named in `.env-harness`.
- A missing index is not created by read-only search operations; fixture validation fails first.
- A configuration error occurs before the timestamped run directory is created, so there may be no `failure.log` for configuration-only failures.
- Version strings and other nondeterministic fields must be allowlisted by their exact response path, not by broad structural paths.
- A changed response caused by a real product behavior change should be reviewed as a compatibility decision, not hidden with an allowlist entry.

## Testing Strategy
- Unit tests: `tests/test_harness.py` validates safe settings, fixture and corpus rules, response comparison, and shell-command quoting.
- Scenario coverage: TS-TF-013 in `documentation/test_scenarios/testing_framework_test_scenarios.md` defines the packaged comparison acceptance criteria.
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
