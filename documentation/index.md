# Documentation

## Document Control
- Status: Approved
- Owner: Documentation Maintainers
- Reviewers: Repository maintainers
- Created: 2026-04-24
- Last Updated: 2026-04-24
- Version: v1.0

## Change Log
- 2026-04-24 | v1.0 | Reformatted the landing page to the repository documentation standard and refreshed navigation links.

## Purpose
Provide the entry point for the repository documentation set and link to the operational docs that describe setup, runtime behavior, and troubleshooting.

## Scope
- In scope:
  - Navigation to the main documentation pages.
  - High-level summary of the runtime directories and configuration files.
- Out of scope:
  - Implementation details for authentication, crawling, or the MCP server.
  - Exhaustive API and database references.

## Design / Behavior
### Start Here
- [Overview](overview.md)
- [Quick Start](installation.md)
- [Configuration](configuration.md)
- [Authentication](authentication.md)
- [Testing](testing.md)
- [Crawling and Indexing](crawling.md)
- [MCP Server](mcp-server.md)
- [Operations](operations.md)
- [Troubleshooting](troubleshooting.md)

### What This Project Does
- `doc-mcp` is a Model Context Protocol server for documentation sites.
- It uses Playwright to capture authenticated browser sessions.
- It crawls pages into SQLite and exposes the indexed content through MCP tools such as search, page fetch, and site listing.

### Documentation System
- [Documentation template](./_documentation_template.md)
- [Documentation standards](./_documentation_standards.md)
- [Naming convention](./_naming_convention.md)
- [Documentation index](./_documentation-index.md)

### Current Runtime Data
- `storage/` stores Playwright session state as JSON.
- `index/` stores SQLite indexes for crawled sites.
- `config/sites.yaml` stores site definitions.
- `.env` stores local environment values and credentials.

## Edge Cases
- If a documentation page is missing from this index, add it in the same change that creates or renames the file.
- If a runtime directory is deleted, regenerate it through the normal auth or crawl flow rather than editing files by hand.

## References
- [documentation/_documentation_standards.md](./_documentation_standards.md)
- [documentation/_documentation_template.md](./_documentation_template.md)
- [documentation/_documentation-index.md](./_documentation-index.md)
- [README.md](../README.md)
