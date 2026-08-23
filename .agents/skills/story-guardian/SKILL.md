---
name: story-guardian
description: Standardize stories against `documentation/_story_template.md`, including converting GitHub tickets—especially technical-debt tickets—into executable parent or technical implementation stories.
---

# Story Guardian

## Overview

Use this skill whenever work involves creating, refining, or reviewing stories for initiatives, parent stories, or numbered sub-stories.

Core rule:
1. Story content must follow `documentation/_story_template.md`.
2. Story wording must stay concise and outcome-focused.
3. Parent stories must remain broad; detailed delivery belongs in numbered sub-stories.
4. Stage-based technical stories should use the technical implementation-story template.
5. Acceptance criteria must stay story-specific.
6. Definition of Done must stay short and reusable.
7. When a GitHub ticket link is supplied, treat it as a conversion request: read the ticket and rewrite it into the applicable Story Guardian format.

## When To Use

Use for any of the following:
- Creating a new parent story.
- Creating a new numbered sub-story.
- Creating a stage-based technical implementation story.
- Refining story title or description.
- Writing or tightening acceptance criteria.
- Writing or tightening Definition of Done.
- Reviewing existing story text for consistency.
- Converting a GitHub issue or ticket into the repository story format.
- Converting a technical-debt ticket into an executable technical implementation story.

## GitHub Ticket Conversion

When the input includes a GitHub issue or ticket URL, the URL is a conversion signal, not
merely a request to compare implementation with the ticket.

- Read the issue through the available GitHub MCP or connector tools first. Use a read-only
  CLI/API fallback only when those tools are unavailable.
- Treat the issue title, body, and explicitly stated acceptance criteria as the source intent.
  Use comments only as supporting context unless the user explicitly asks to include them.
- Preserve the original outcome and story number when present, but rewrite the content to
  match `documentation/_story_template.md`.
- Classify the source as a parent story, numbered sub-story, or technical implementation
  story before selecting the output structure. Keep parent stories broad.
- If the ticket represents technical debt, convert the debt context and risk into a concrete
  implementation problem, desired outcome, scope, proposed fix, acceptance criteria, test
  plan, documentation sync, and short Definition of Done. The result must be executable by
  an engineering team, not just a restatement of the debt register.
- Do not claim that deferred work is already implemented. Preserve unresolved constraints as
  requirements, scope boundaries, or open questions.
- Do not modify the GitHub issue, add comments, change labels, or change issue state.

For a converted ticket, return one complete, copyable Markdown `md` block containing the
rewritten story and a concise Story Guardian Report. Do not create or update a repository
story file unless the user separately requests that write.

## Workflow (Required)

### Step 1: Classify the story work
Choose one:
- **Parent story**
- **Sub-story**
- **Technical implementation story**
- **Story review**
- **GitHub ticket conversion** — use this when a GitHub ticket link is supplied and the
  requested outcome is to rewrite the ticket into the repository story format.

### Step 2: Load the template and standards
- Read `documentation/_story_template.md`.
- If the story content is stored in `documentation/`, also apply:
  - `documentation/_documentation_template.md`
  - `documentation/_documentation_standards.md`
  - `documentation/_documentation-index.md`

### Step 3: Pre-Development Reading
- Before drafting or updating a story, read the minimal set of repository docs that describe the feature, workflow, or subsystem in scope.
- Use only the docs that materially affect the story; do not load unrelated material.
- If the story covers setup, runtime behavior, troubleshooting, or test flow, include the canonical docs for those areas in the reading list.
- Record the selected docs in the story itself under `Pre-Development Reading`.

### Step 4: Apply structure rules
- Parent stories must contain a concise title and broad description.
- Sub-stories should use numbered titles such as `0. Define Requirements`.
- Technical implementation stories should use the stage-style template with description, context, problem, desired outcome, scope, proposed fix, acceptance criteria, test plan, documentation sync, and definition of done.
- Keep descriptions focused on outcome and scope, not implementation tasks.
- Use `Acceptance Criteria` for story-specific validation.
- Use `Definition of Done` for short reusable completion gates.

For technical-debt conversions specifically:

- Translate the debt item's `Context`, `Impact/Risk`, and `Proposed Fix` into the story's
  `Context`, `Problem`, `Desired Outcome`, `Scope`, and `Proposed Fix` sections.
- Turn the debt item's `Acceptance Signal` into story-specific acceptance criteria and
  verification evidence.
- Add concrete repository paths to `Pre-Development Reading`, `Test Plan`, and
  `Documentation Sync` when the ticket identifies them or repository inspection supports
  them.
- Keep the debt record as a reference to the deferred discovery; do not use the story to
  silently broaden unrelated product scope.

### Step 5: Tighten content
- Prefer simple business language over technical detail unless the user asks for more detail.
- Avoid embedding long task lists into the description.
- Keep requirements or architecture detail in linked documents when the story becomes too dense.
- Split stories when one story covers multiple independently deliverable outcomes.
- For technical implementation stories, keep the template general-purpose and stage-oriented rather than scheduler-specific.

### Step 6: Report result
State one outcome:
- **Compliant**
- **Updated to compliant**
- **Partially compliant** (list exact gaps)

## Output Requirements

Always report:
- Story type handled
- Template sections created or normalized
- Whether the story remains broad enough or should be split
- For GitHub ticket conversion, state that the ticket was converted, identify whether it
  became a parent, sub-story, or technical implementation story, and confirm that no
  GitHub resource was modified.
