---
name: backend-doc-sync
description: Enforce documentation synchronization for every backend Python change. Use when creating, updating, or reviewing backend `*.py` code so repository docs stay aligned with implementation.
---

# Backend Doc Sync

## Overview

Use this skill whenever backend Python code changes to ensure the corresponding documentation is updated in the same change.

Core rule:
1. Backend code change and documentation update must ship together.
2. If behavior, contracts, or architecture changed, documentation must explicitly reflect the new behavior.
3. If no documentation update is made, provide a written impact analysis proving no user-visible or system-level behavior changed.

## When To Use

Use for any of the following:
- New backend Python modules, endpoints, services, or handlers.
- Updates to existing backend Python logic.
- Refactors that can affect behavior, permissions, validation, status transitions, or integrations.
- Backend code reviews where documentation drift is possible.

## Workflow (Required)

### Step 1: Classify backend change impact
Choose all that apply:
- **API contract impact** (request/response/status codes/validation)
- **Workflow or business-rule impact**
- **Auth or permission impact**
- **Data-model or persistence impact**
- **Internal-only refactor** (no externally observable behavior)

### Step 2: Map impact to documentation targets
- Read `documentation/_documentation-index.md` to find canonical target docs.
- Update the relevant existing docs (for example: `documentation/api_interfaces.md`, `documentation/api_db_rules.md`, feature docs).
- If no suitable doc exists, create one from `documentation/_documentation_template.md` and add it to `documentation/_documentation-index.md`.

### Step 3: Update docs in the same change
- Keep changes in backend code and docs in one atomic update.
- Update `Document Control` metadata for modified documentation files.
- Ensure filenames and structure follow `documentation/_documentation_standards.md`.
- Avoid vague notes; document exact behavior that changed.

### Step 4: Enforce no-drift checks
- Reject completion if backend code changed but docs were not reviewed.
- If claiming no doc update is required, include a short impact statement covering:
  - affected modules
  - why behavior is unchanged
  - why existing docs remain accurate
- Confirm any new documentation file is added to `documentation/_documentation-index.md`.

## Output Requirements

Always report:
- Backend Python files changed
- Documentation files changed (or explicit no-impact justification)
- What behavior/contract/architecture detail was synchronized
