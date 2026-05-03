---
name: docs-guardian
description: Standardize and review repository documentation against documentation/_documentation_template.md and documentation/_documentation_standards.md. Use when creating, updating, or reviewing files in documentation/.
---

# Docs Guardian

## Overview

Use this skill to keep project documentation consistent, complete, and aligned with:
- `documentation/_documentation_template.md`
- `documentation/_documentation_standards.md`
- `documentation/_naming_convention.md`
- `documentation/_documentation-index.md`

## Workflow (Required)

### Step 1: Classify the doc task
Choose one:
- **New document**
- **Update existing document**
- **Review existing document**

### Step 2: Load standards and template
- Read `documentation/_documentation_standards.md`.
- Read `documentation/_documentation_template.md`.
- Read `documentation/_naming_convention.md`.
- Read `documentation/_documentation-index.md`.

### Step 2b: Reference existing docs before drafting new story content
- When creating or updating a story, issue, or implementation brief, identify only the repository docs that describe the area being developed.
- Read the relevant existing docs first and cite them in the story text instead of restating requirements from memory.
- Prefer an explicit "Pre-Development Reading" or equivalent section that lists only the docs needed for that scope before implementation begins.
- Do not require unrelated documentation links; keep the reference list scoped to the feature, workflow, or subsystem under development.
- If the story touches setup, runtime behavior, troubleshooting, or test flow, include the current canonical docs for those areas in the reference list.

### Step 3: Validate required structure
For each target file in `documentation/`:
- Confirm required sections from standards exist.
- Confirm one H1 heading only.
- Confirm `Document Control` is present with status, owner, and dates.
- Confirm `References` section exists.
- Confirm filename follows lowercase underscore convention.
- Confirm no uppercase characters exist in any `documentation/*.md` filename.
- Confirm helper/control files use `_` prefix.
- Confirm any new/renamed documentation files are added to `documentation/_documentation-index.md`.
 - Run `find documentation -type f -name '*.md' | rg '[A-Z]'` and require empty output.

### Step 4: Normalize and tighten content
- Keep wording implementation-focused and concise.
- Use explicit requirement language (`must`, `should`, `may`) where applicable.
- Remove sections that are not applicable; do not leave placeholder text in final docs.
- Keep Mermaid diagrams only when they add clarity.
- Change Log update policy:
  - If the latest entry date matches today, update that latest entry description instead of adding a new entry.
  - Add a new Change Log entry only when the calendar date changes.

### Step 5: Report result
State one outcome:
- **Compliant**
- **Updated to compliant**
- **Partially compliant** (list exact gaps)

## Response Requirements

- When editing docs, mention which sections were added or normalized.
- When reviewing only, provide a checklist of pass/fail items from the standards.
- Do not invent requirements that conflict with repository standards.
