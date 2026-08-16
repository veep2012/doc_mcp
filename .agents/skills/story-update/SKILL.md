---
name: story-update
description: Refresh a GitHub implementation story from the current repository solution. Use when a user provides a GitHub issue URL and asks to update the story with features already implemented, manually added behavior, or requirements missing from the original story, while preserving the repository story-guardian format and returning one copyable Markdown block.
---

# Story Update

Update an existing GitHub story so it describes the current repository solution as if
the implementation had not yet started. Treat the current code, database, tests, and
documentation as the source of truth for the updated story, while treating the original
GitHub issue as the source of the declared intent.

## Required workflow

### 1. Resolve the story URL

- Extract the GitHub owner, repository, and issue number from the user-provided URL.
- Accept a full issue URL as the primary input, for example:
  `https://github.com/owner/repository/issues/123`.
- Do not guess a repository or issue number when the URL is missing or malformed.
- Read the issue with the GitHub MCP issue-read tool first.
- Read the issue body and use comments only as supporting context; do not promote
  comments into requirements unless the user explicitly asks for that.
- Do not modify the GitHub issue, add comments, change labels, or change issue state.

### 2. Load story standards

- Read `documentation/story_template.md`.
- Read `.agents/skills/story-guardian/SKILL.md`.
- Apply the technical implementation-story structure when the issue describes a
  deliverable requiring implementation context and verification.
- Preserve the original story number and intent unless the repository evidence requires
  a clearer title.

### 3. Inspect the current solution

- Check `git status --short` and inspect relevant working-tree diffs. Include uncommitted
  implementation and documentation changes in the comparison.
- Inspect the implementation files, API schemas, database migrations/functions/views,
  tests, test scenarios, and related documentation relevant to the issue.
- Follow the actual code path far enough to verify behavior, not just symbol existence.
- Search for related routes, workflow functions, database tables, configuration values,
  feature flags, tests, and documentation references.
- Record repository-relative evidence internally while drafting the story.

### 4. Reconstruct the story as pre-implementation work

- Pretend the current solution has not yet been implemented.
- Convert every confirmed implemented behavior into story requirements, proposed changes,
  acceptance criteria, tests, and documentation synchronization items.
- Include behavior that was added manually or exists in the repository but is absent from
  the original story.
- Include required compatibility changes, such as removing an obsolete API route,
  adding a replacement route, preserving a compatibility field, or updating public
  response contracts.
- Do not describe the result as already implemented inside the replacement story.
- Do not invent behavior that cannot be supported by repository evidence.
- Explicitly record important behavior that is *not* implemented when it could otherwise
  be mistaken for part of the story.
- Keep the story outcome-focused; move detailed evidence into concise references and
  implementation bullets.

### 5. Apply story-guardian structure

Follow the applicable structure and section order defined in
`documentation/story_template.md`, using `.agents/skills/story-guardian/SKILL.md` as
the governing refinement guidance.

Use concise, story-specific acceptance criteria and keep `Definition of Done` short and
reusable. Split the story only when the current scope contains independently deliverable
outcomes that cannot reasonably be reviewed together.

### 6. Produce copyable output

- Print the complete replacement story in exactly one Markdown fenced code block using
  the `md` language marker.
- Do not place explanatory text before or after that code block when delivering the
  final story; the block must have one-click copy behavior in the client.
- Do not use nested triple-backtick fences inside the story. Use indented examples or
  four-tilde fences inside the outer block if examples are required.
- Include the Story Guardian Report inside the same Markdown block.
- Do not create or modify repository files unless the user separately requests that.
- Do not write the updated story back to GitHub.

## Current-solution comparison rules

Classify findings internally as:

- **Implemented behavior to add** — confirmed in current code but absent from the issue.
- **Story requirement preserved** — stated in the issue and supported by current code.
- **Story requirement corrected** — stated differently from current behavior; rewrite it
  to match the current solution.
- **Current behavior explicitly out of scope** — present in the repository but not part
  of the story's user-visible outcome; mention only when necessary to prevent ambiguity.
- **Unsupported requirement** — present in the issue but not supported by current code;
  retain it only if it is clearly part of the intended story, and identify it as pending
  rather than claiming implementation evidence.

The final story should describe the complete intended change, not a review table. Use
repository paths in `References` and in pre-reading lists to make the story actionable.

## Failure handling

- If GitHub issue retrieval fails, report the exact retrieval error and do not fabricate
  the issue's title or body.
- If the repository implementation cannot be inspected, report the exact limitation and
  do not claim that the story is synchronized with current behavior.
- If the issue is a parent story, keep the result broad and do not force it into a
  technical implementation story. If it is a numbered technical story, use the full
  technical template.

## Output requirements

The final response must contain:

- one complete, copyable `md` code block;
- a story title aligned with the original issue;
- all applicable story-guardian sections;
- acceptance criteria covering both original requirements and confirmed additional
  implementation behavior;
- a `Story Guardian Report` stating the story type, normalized sections, scope-splitting
  assessment, and one result: `Compliant`, `Updated to compliant`, or
  `Partially compliant`.
