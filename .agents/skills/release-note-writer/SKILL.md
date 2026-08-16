---
name: release-note-writer
description: Draft user-friendly release notes and PR release summaries in a consistent versioned format. Use when the user asks for a release note, changelog entry, release announcement, or PR-based version summary.
---

# Release Note Writer

## Overview

Use this skill to turn a PR, version bump, or merged change set into a short release note that is easy for users to read.

Core rules:
1. Match the repository’s release-note template and keep the tone user-friendly.
2. Lead with what changed and why it matters.
3. Prefer plain language over implementation detail.
4. Keep the note concise unless the user asks for a longer announcement.
5. State whether there are breaking changes.

## When To Use

Use for any of the following:
- Writing a release note for a versioned release.
- Summarizing one PR as a user-facing release note.
- Drafting a changelog entry from a merged diff.
- Turning a technical change list into a readable announcement.

## Workflow (Required)

### Step 1: Identify the release scope
Capture:
- version number, if provided
- PR number or commit range, if provided
- user-visible changes
- tests or validation worth mentioning
- whether the release is breaking or non-breaking

### Step 2: Use the release-note template
Write in this structure:

```markdown
Release Note: vX.Y.Z

Based on PR #NN.

One short paragraph that explains the release in user-friendly terms.

Highlights

- Bullet 1
- Bullet 2
- Bullet 3

Notes

- Optional short notes section for compatibility, defaults, or limits.
```

### Step 3: Tighten the wording
- Lead with the user impact.
- Group related changes into a few bullets.
- Avoid internal code names unless they help comprehension.
- Mention defaults that stayed the same when that reduces ambiguity.
- If there are no breaking changes, say so plainly.
- If the user asks for a shorter note, collapse the body into fewer bullets.

### Step 4: Validate the final note
- Version and PR reference are correct.
- The note is readable by a non-technical user.
- Bullets describe outcomes, not implementation steps.
- The note does not overclaim unsupported behavior.

## Output Requirements

Always report:
- the version or PR reference used
- whether the release is breaking or non-breaking
- the final user-facing release note
