# Testing

## Document Control
- Status: Approved
- Owner: Documentation Maintainers
- Reviewers: Repository maintainers
- Created: 2026-04-25
- Last Updated: 2026-04-25
- Version: v1.0

## Change Log
- 2026-04-25 | v1.0 | Added pytest, unit test, and smoke test workflow documentation.

## Purpose
Describe the canonical commands for local verification and the runtime prerequisites needed by the smoke tests.

## Scope
- In scope:
  - Unit and smoke test commands.
  - Local prerequisites for containerized crawl smoke tests and MCP smoke tests.
- Out of scope:
  - Detailed crawler implementation behavior.
  - CI workflow configuration.

## Design / Behavior
### Canonical Commands
- `make test`
- `make test-unit`
- `make test-smoke`
- `make test CONTAINER_BIN=docker`
- `.venv/bin/python crawl_cli.py --site newsvl.ru --headless`

### Expected Test Flow
- `make test` runs unit tests first.
- Smoke tests run only after unit tests pass.
- Direct `pytest` excludes smoke tests by default for fast local iteration.

### Prerequisites
- Use Podman by default, or run `make test CONTAINER_BIN=docker` to use Docker instead.
- Install Playwright Chromium with `make local-venv`.
- Configure a local `newsvl.ru` site entry when you need to regenerate `index/newsvl.ru.db`.
- Keep `index/newsvl.ru.db` available locally for the MCP smoke test, or regenerate it with `.venv/bin/python crawl_cli.py --site newsvl.ru --headless`.

## Edge Cases
- If `index/newsvl.ru.db` is missing, the MCP smoke test fails with a regeneration command.
- If the selected container runtime is not installed or cannot start `nginx:alpine`, the crawl smoke test cannot run successfully.

## References
- [documentation/installation.md](./installation.md)
- [documentation/crawling.md](./crawling.md)
- [documentation/mcp-server.md](./mcp-server.md)
