---
name: test-scenario-guardian
description: Enforce scenario-first verification development with strict bidirectional traceability between documentation/test_scenarios/*.md and automated verification artifacts in tests/ or scripts/. Use for test creation, updates, and reviews.
---

# Test Scenario Guardian

## Overview

Use this skill to keep test scenarios and automated verification tightly synchronized.

Core rule:
1. Define or update scenarios first in `documentation/test_scenarios/`.
2. Implement or update automated verification in the appropriate executable artifact.
3. Ensure bidirectional links so changing one requires updating the other.
4. Treat scenario documentation as the single source of truth for expected behavior.

## When To Use

Use for new or updated tests, smoke checks, scenario documents, and reviews where behavior or coverage changes.

## Workflow (Required)

### Step 1: Create or update the scenario document first

- Ensure a scenario file exists in `documentation/test_scenarios/`.
- Scenario filenames must be lowercase only.
- Update `Document Control` metadata.
- Define stable scenario IDs, for example `TS-DL-001`.
- For each scenario include intent, setup/preconditions, request or action, expected response/assertions, and cleanup when required.

### Step 2: Implement automated verification from scenario IDs

- Add or update the executable verification artifact in `tests/` or `scripts/`.
- Each artifact must reference scenario IDs in code, comments, docstrings, or adjacent metadata.
- Keep assertions aligned to scenario acceptance criteria.
- When behavior differs between docs and verification artifacts, update verification to match docs unless the user explicitly asks to revise docs first.

### Step 3: Enforce bidirectional traceability

- In scenario docs, add an **Automated Test Mapping** section with concrete artifact names and entrypoints.
- In automated verification artifacts, map back to scenario IDs and the scenario document path where practical.
- Add or maintain a lightweight traceability check when feasible so missing scenario IDs or mapping entries fail validation.

### Step 4: Validate and tighten

- If automated verification changed, update scenario docs in the same change.
- If scenario docs changed, update automated verification in the same change.
- Reject partial updates that only modify one side when linkage is affected.
- Resolve ambiguity by tightening the scenario doc first, then update tests in the same change.
- Verify documentation markdown filenames contain no uppercase letters:
  - `find documentation -type f -name '*.md' | rg '[A-Z]'`

## Output Requirements

Always report scenario files updated, verification artifacts updated, traceability checks added or updated, and any intentional gaps such as manual-only scenarios.
