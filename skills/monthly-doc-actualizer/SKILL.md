---
name: monthly-doc-actualizer
description: Run daily documentation freshness checks and trigger full code-first documentation actualization when due. Use when repository docs must be revalidated against the current implementation in `api/`, `ci/init/`, `tests/`, and related source files.
---

# Monthly Doc Actualizer

## Overview

Use this skill to enforce periodic documentation refresh with a lightweight daily check and a full monthly actualization when due.

Core principle:
- Actualization is not a wording pass.
- Actualization means reading the current implementation first, identifying canonical docs from `documentation/_documentation-index.md`, and updating those docs so they describe the code that exists now.
- If code and docs disagree, update docs to match the implemented behavior unless the user explicitly asks for a code change instead.

State is tracked in:
- `documentation/_documentation_actualization_state.md`

Helper script:
- `skills/monthly-doc-actualizer/scripts/check_due.py`

## Workflow (Required)

### Step 1: Run daily due check
- Run:
  - `python3 skills/monthly-doc-actualizer/scripts/check_due.py --state-file documentation/_documentation_actualization_state.md --mark-check`
- Read output fields:
  - `DUE=true|false`
  - `LAST_FULL_ACTUALIZATION`
  - `NEXT_DUE_DATE`
  - `DAYS_SINCE_FULL`

### Step 2: If not due
- Stop after the check.
- Report that monthly actualization is not required yet.

### Step 3: If due
- Run full documentation actualization for `documentation/*.md` as a code-first review:
  - read `documentation/_documentation-index.md` to identify canonical docs by domain
  - inspect current implementation before editing docs:
    - `api/routers`
    - `api/schemas`
    - `api/db`
    - `ci/init/*.sql`
    - `tests/api`
    - any feature-specific source files touched by recent work
  - compare implementation to documentation and classify each mismatch:
    - stale doc text
    - stale examples
    - stale schema, table, or field descriptions
    - stale endpoint, request, response, or validation contract
    - stale test-scenario mapping
  - update the canonical docs to match current code behavior
  - remove obsolete claims instead of leaving “future”, “planned”, or stale historical wording in current-state docs
  - normalize `Document Control` metadata (`Last Updated`, `Version`) in modified docs
  - keep `documentation/_documentation-index.md` aligned for any added or renamed docs
  - preserve repository doc standards, including one `Change Log` entry per calendar date

### Step 4: Required coverage during a full actualization
- Review at least these categories when they exist in the repo:
  - API contract docs
  - workflow and DB rule docs
  - ER and data-model docs
  - auth and permission docs
  - test scenario docs
- Do not assume unchanged docs are accurate because they were recently touched; confirm against current code.
- If a document is still accurate after review, leave it unchanged and mention that it was checked.

### Step 5: Validate
- Invariant: documentation markdown filenames must be lowercase (no uppercase letters).
- Run:
  - `find documentation -type f -name '*[A-Z]*.md'`
- Expected: no output.
- Confirm no document has more than one `Change Log` entry for the same calendar date.
- Confirm modified docs still satisfy `documentation/_documentation_standards.md`.

### Step 6: Mark completion
- After successful actualization and validation, mark completion:
  - `python3 skills/monthly-doc-actualizer/scripts/check_due.py --state-file documentation/_documentation_actualization_state.md --mark-full`

## Output Requirements

Always report:
- Whether monthly run was due
- Which implementation areas were reviewed
- Which documentation files were checked
- Which files were updated
- New next due date
- Any unresolved ambiguity or manual follow-up
