# Commiter (Repo Local Skill)

Use this skill only when the user explicitly asks to create a commit.

## Goal
Create a git commit with a single-line message in this exact format:
`username: date: Short description in one line`

## Trigger Rules
- Run only on direct user request to commit (examples: "commit", "create commit", "$commiter").
- Do not run automatically after code changes.
- On explicit commit request, do not ask file-selection questions; commit all current working tree changes.

## Commit Message Rules
- `username`:
  - First choice: `git config user.name`
  - Fallback: `whoami`
- `date`: use `YYYY-MM-DD` format.
- `Short description in one line`:
  - Imperative, concise, no trailing period.
  - Must fit one line.

## Workflow
1) Confirm there are staged or unstaged changes:
```bash
git status --short
```

2) Stage all current changes (tracked + untracked) without asking follow-up questions:
```bash
git add -A
```

3) Build commit message using required format.

4) Pre-commit checks (required when configured):
- Detect whether pre-commit is configured:
  - `.pre-commit-config.yaml` exists, or
  - `.git/hooks/pre-commit` exists.
- If configured, run:
```bash
pre-commit run --all-files
```
- If checks fail:
  - inspect errors and apply fixes in code/config (lint, formatting, imports, typing, etc.)
  - re-run `pre-commit run --all-files`
  - repeat until it passes or a real blocker is reached
- Re-stage any files changed by auto-fixes:
```bash
git add <files>
```

5) Commit:
```bash
git commit -m "<username>: <YYYY-MM-DD>: <short one-line description>"
```

6) Push current branch to default remote:
```bash
git push
```

7) Report:
- committed files
- final commit hash
- final commit message
- push result

## Notes
- Never amend existing commits unless the user explicitly asks.
- Never use destructive git commands.
- If `pre-commit` is configured, do not skip it.
