# Documentation Naming Convention

## Document Control
- Status: Approved
- Owner: Documentation Maintainers
- Reviewers: Repository maintainers
- Created: 2026-04-24
- Last Updated: 2026-04-24
- Version: v1.0

## Change Log
- 2026-04-24 | v1.0 | Reformatted the naming guide into the standard control/log layout and preserved the filename rules.

## Purpose
Define filename rules for all Markdown files in `documentation/`.

## Scope
- In scope:
  - Markdown filenames under `documentation/` and subfolders.
  - Helper/control file naming.
- Out of scope:
  - Content structure inside each document.

## Design / Behavior
### Rules
- Use lowercase only for every Markdown filename under `documentation/` (including subfolders).
- Use underscores as word separators.
- Use `.md` extension for Markdown files.
- Use a leading underscore for helper/control files that are not product or feature documentation.
- Reserve helper/control files for standards, templates, conventions, and indexes.

### Examples
- Documentation files:
  - `api_interfaces.md`
  - `distribution_list_feature.md`
  - `notifications_and_dls.md`
- Helper/control files:
  - `_documentation_template.md`
  - `_documentation_standards.md`
  - `_naming_convention.md`
  - `_documentation-index.md`

### Migration Guidance
- When touching an existing file, rename it to this convention if safe.
- Update all references in docs, skills, and `AGENTS.md` in the same change.
- Verify compliance with `find documentation -type f -name '*.md' | rg '[A-Z]'`.

## Edge Cases
- Filenames with uppercase characters are not allowed anywhere under `documentation/`.
- Helper/control files should keep the leading underscore even when their content changes.

## References
- [documentation/_documentation_standards.md](./_documentation_standards.md)
- [documentation/_documentation_template.md](./_documentation_template.md)
- [documentation/_documentation-index.md](./_documentation-index.md)
