---
name: story-guardian
description: Standardize story creation, refinement, and review against `documentation/_story_template.md`. Use when creating or updating parent stories, numbered sub-stories, acceptance criteria, or definitions of done.
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

## When To Use

Use for any of the following:
- Creating a new parent story.
- Creating a new numbered sub-story.
- Creating a new stage-based technical implementation story.
- Refining story title or description.
- Writing or tightening acceptance criteria.
- Writing or tightening Definition of Done.
- Reviewing existing story text for consistency.

## Workflow (Required)

### Step 1: Classify the story work
Choose one:
- **Parent story**
- **Sub-story**
- **Technical implementation story**
- **Story review**

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
