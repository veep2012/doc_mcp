# Story Template

## Document Control
- Status: Draft
- Owner: Documentation Maintainers
- Reviewers: Repository maintainers
- Created: 2026-05-09
- Last Updated: 2026-05-09
- Version: v0.2

## Change Log
- 2026-05-09 | v0.2 | Added the Pre-Development Reading section and the canonical story structure for parent stories, sub-stories, and technical implementation stories.

## Purpose
Define the standard structure for story documents used to describe outcomes, scope, acceptance criteria, and delivery gates.

## Scope
- In scope:
  - Parent stories.
  - Numbered sub-stories.
  - Technical implementation stories.
- Out of scope:
  - Detailed implementation notes.
  - Reusable product documentation.

## Design / Behavior
### Story Types
- Parent story: broad outcome statement with minimal delivery detail.
- Sub-story: numbered slice of work with a specific outcome.
- Technical implementation story: stage-oriented delivery plan with context, problem, desired outcome, scope, proposed fix, acceptance criteria, test plan, documentation sync, and definition of done.

### Required Sections
- Title.
- Story type.
- Description.
- Pre-Development Reading.
- Context.
- Problem.
- Desired outcome.
- Scope.
- Proposed fix.
- Acceptance Criteria.
- Test plan.
- Documentation sync.
- Definition of Done.
- References.

### Formatting Rules
- Keep story text concise and outcome-focused.
- Use numbered sub-story titles when splitting work.
- Keep acceptance criteria specific and testable.
- Keep definition of done short and reusable.
- Keep technical implementation stories stage-oriented and explicit about the planned fix.
- Record only the minimum relevant repository docs in Pre-Development Reading.
- Use technical details only when they are necessary to explain the outcome.

## Edge Cases
- If a story combines unrelated outcomes, split it into separate stories.
- If a technical story becomes too large, break it into numbered stages.
- If a story is stored in documentation, also apply the repository documentation standards.
- If the relevant docs are unclear, note the ambiguity before drafting the story.

## References
- [documentation/_documentation_template.md](./_documentation_template.md)
- [documentation/_documentation_standards.md](./_documentation_standards.md)
- [documentation/_documentation-index.md](./_documentation-index.md)
