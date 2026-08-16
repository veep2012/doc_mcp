---
name: tech-debt
description: Capture deferred technical debt discovered during development in dated markdown files under tech-debt/. Use when an issue is real, relevant, and intentionally not fixed in the current task.
---

# Tech Debt

## Overview

Use this skill when implementation/review uncovers technical debt that should be documented now and fixed later.

Core rule:
1. If debt is actionable but out of current scope, record it immediately.
2. Keep debt entries concrete and traceable to code/files.
3. Store entries only in `tech-debt/<YYYY-MM-DD>.md`.

## When To Use

Use for any of the following:
- Known limitation deferred to keep scope controlled
- Risky workaround intentionally accepted for now
- Missing test/guard/documentation that cannot be completed in the current change
- Design compromise that should be revisited

Do not use for:
- Already fixed issues
- Vague ideas with no concrete code impact
- Product feature requests unrelated to technical quality

## Workflow (Required)

### Step 1: Confirm it is real debt
- Identify exact impacted files/components.
- State why it cannot be fixed now.
- State risk if it remains unresolved.

### Step 2: Ensure dated file exists
- Target file: `tech-debt/<YYYY-MM-DD>.md` (for today).
- If the file exists, append a new debt item.
- If it does not exist, create it with one H1 and a short purpose line.

### Step 3: Add debt item with required fields
Each item must include:
- `ID`: `TD-YYYYMMDD-XX`
- `Title`
- `Context` (what was being changed when found)
- `Location` (repo file paths)
- `Impact/Risk`
- `Why Deferred Now`
- `Proposed Fix`
- `Acceptance Signal` (what proves debt is resolved)
- `Status` (`open` by default)

### Step 4: Keep entries implementation-ready
- Use precise language and concrete paths.
- Avoid secrets, credentials, or personal data.
- Keep each item independently actionable.

## Output Requirements

Always report:
- Dated debt file path updated/created
- Debt item IDs added
- Short statement of why each item was deferred
