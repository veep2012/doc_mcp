---
name: story-check
description: Compare a GitHub issue or story with the current repository implementation and report scope discrepancies. Use when a GitHub issue link is provided and the user wants to verify that implementation matches the declared story.
---

# Story Check

## Purpose

Verify that the current repository implementation matches the scope declared in a GitHub issue or story. This is a read-only review: do not modify GitHub resources or implementation files unless the user separately requests a fix.

## When To Use

Use this skill when:
- The user provides a GitHub issue URL or asks to check implementation against an issue.
- The user asks whether delivered work matches a story, acceptance criteria, or declared scope.
- The user asks for out-of-scope or missing implementation findings.

## Required Workflow

### 1. Resolve the declared scope

- Extract the GitHub owner, repository, and issue number from the link.
- Read the issue through the GitHub MCP tools first, as required by repository instructions.
- Use the issue title, body, acceptance criteria, and explicitly linked requirements as the declared scope.
- Treat comments, labels, and linked pull requests as supporting context only; do not silently promote them to requirements.
- If the issue cannot be read, report the exact access or retrieval error and stop before making scope claims.

### 2. Inspect the current implementation

- Check the working-tree status and relevant diff so uncommitted work is included in the review.
- Inspect the implementation files, tests, migrations, configuration, and documentation relevant to each requirement.
- Follow code paths far enough to verify behavior, not just the presence of a filename or symbol.
- Use tests and test scenarios as evidence, but do not treat a passing test alone as proof that the full story is implemented.
- Record precise evidence using repository-relative file paths and line numbers where available.

### 3. Compare scope to implementation

Classify every meaningful requirement as one of:
- **Implemented** — current behavior and supporting evidence satisfy the requirement.
- **Partially implemented** — some required behavior exists, but a stated condition, edge case, or acceptance criterion is missing.
- **Missing** — no sufficient implementation evidence was found.
- **Out of scope** — implementation adds behavior or files not supported by the declared issue scope.
- **Ambiguous** — the story is not specific enough to determine compliance; state the exact ambiguity.

Distinguish functional scope from incidental implementation details. Do not report normal refactoring, required tests, or documentation synchronization as out of scope unless they introduce user-visible behavior not justified by the story.

### 4. Report discrepancies

Always print a concise comparison summary. If discrepancies exist, list each one with:
- Classification
- Requirement or story excerpt paraphrase
- Implementation evidence or missing evidence
- Impact or risk
- A focused follow-up recommendation

If no discrepancies are found, state that the implementation is scope-aligned and identify the evidence reviewed. Do not claim certainty when the issue or implementation could not be fully inspected.

## Output Format

Use this structure:

```text
Scope: <issue URL and title>
Implementation examined: <branch/working-tree context and key areas>
Overall status: Scope-aligned | Discrepancies found | Blocked | Ambiguous

Requirement comparison:
- <requirement>: Implemented | Partially implemented | Missing | Out of scope | Ambiguous

Discrepancies:
1. [<classification>] <short finding>
   Evidence: <issue requirement and repository evidence, or missing evidence>
   Impact: <why it matters>
   Follow-up: <focused recommendation>

Verification limits:
- <only material limitations; write “None” when applicable>
```

Do not create commits, alter files, post GitHub comments, or change issue state as part of this skill.
