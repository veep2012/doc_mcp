# AGENTS

## Default Skill

For any development task where non-blocking issues are found but intentionally deferred, always apply the **tech-debt** skill to record debt in `tech-debt/<YYYY-MM-DD>.md`.
For any explicit user request to create a commit, always apply the **commiter** skill.

## Skills

- backend-doc-sync: Enforce documentation synchronization for backend Python changes. Invoke as `$backend-doc-sync`. (file: `.agents/skills/backend-doc-sync/SKILL.md`)
- docs-guardian: Standardize and review repository documentation. Invoke as `$docs-guardian`. (file: `.agents/skills/docs-guardian/SKILL.md`)
- monthly-doc-actualizer: Run documentation freshness checks and actualization. Invoke as `$monthly-doc-actualizer`. (file: `.agents/skills/monthly-doc-actualizer/SKILL.md`)
- release-note-writer: Draft user-facing release notes. Invoke as `$release-note-writer`. (file: `.agents/skills/release-note-writer/SKILL.md`)
- story-guardian: Standardize and review stories. Invoke as `$story-guardian`. (file: `.agents/skills/story-guardian/SKILL.md`)
- tech-debt: Capture deferred technical debt items into dated markdown files under `tech-debt/`. (file: `.agents/skills/tech-debt/SKILL.md`)
- commiter: Create commit/push flow with standardized commit message format on explicit commit requests. (file: `.agents/skills/commiter/SKILL.md`)
