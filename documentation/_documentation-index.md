# Documentation Index

## Document Control
- Status: Approved
- Owner: Documentation Maintainers
- Reviewers: Repository maintainers
- Created: 2026-04-24
- Last Updated: 2026-04-24
- Version: v1.0

## Change Log
- 2026-04-24 | v1.0 | Reformatted the documentation index to the standard control/log layout and kept the navigation list current.

## Purpose
Provide a single entry point for all files in `documentation/` and make it easy to find the right page by topic.

## Scope
- In scope:
  - Navigation and file grouping for the documentation folder.
  - The maintenance rules that keep the index current.
- Out of scope:
  - The detailed content of each individual document.

## Design / Behavior
### Core Architecture
- `index.md` - Documentation landing page and quick links.
- `overview.md` - High-level architecture and data flow for the documentation MCP server.
- `installation.md` - Setup and first-run instructions.
- `configuration.md` - Environment, site, and runtime configuration reference.
- `authentication.md` - Authentication session flow and Playwright login process.
- `crawling.md` - Crawler behavior, indexing flow, and crawl tuning.
- `mcp-server.md` - MCP server entry points and client connection details.
- `operations.md` - Operational workflow, maintenance, and runtime notes.
- `troubleshooting.md` - Common failure modes and recovery steps.

### Standards And Templates
- `_documentation_standards.md` - Required structure and writing rules.
- `_documentation_template.md` - Base template for new documents.
- `_naming_convention.md` - Filename rules.
- `_documentation-index.md` - This index file.

### Maintenance Rules
- Add every new `documentation/*.md` file to this index in the same change.
- Keep entries lowercase to match naming convention.
- Keep helper/control files prefixed with `_`.
- Use `-` bullets for all index entries.

## Edge Cases
- If a new file is created without an index entry, the documentation set becomes inconsistent.
- If a file is renamed, update the index link in the same change.

## References
- [documentation/_documentation_standards.md](./_documentation_standards.md)
- [documentation/_documentation_template.md](./_documentation_template.md)
- [documentation/_naming_convention.md](./_naming_convention.md)
- [documentation/index.md](./index.md)
