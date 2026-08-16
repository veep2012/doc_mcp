---
name: check-documentation-gaps
description: Compare repository documentation with the current implementation and identify stale, missing, contradictory, or untraceable documentation. Use for documentation audits; an explicit `fix` argument authorizes updating documentation to close confirmed gaps.
---

# Check Documentation Gaps

Review documentation from the implementation outward. Default mode is audit-only. Only modify documentation when the user explicitly invokes the skill with `fix`, for example `$check-documentation-gaps fix`.

## Inputs and modes

- Scope may be a feature, module, story, recent change, or the whole repository.
- `audit` (default): report gaps and recommendations; make no writes.
- `fix`: update documentation for confirmed gaps, then validate the result. Do not change production code or tests unless separately requested.

## Workflow

1. Establish the documentation scope.
   - Inspect the working tree and recent relevant diffs without reverting user changes.
   - Locate canonical product, configuration, operations, architecture, story, and test-scenario documents.
   - Read repository documentation rules, templates, and standards before judging format or required sections.
   - If a story is supplied, distinguish acceptance criteria from suggested tests and narrative context.

2. Derive the source of truth from implementation.
   - Inspect relevant `src/`, configuration, scripts, packaging files, and `tests/`.
   - Check command-line behavior, MCP tools, configuration, authentication, crawling, indexing, storage, external services, retries, cleanup, and operational prerequisites as applicable.

3. Compare documentation to behavior.
   Look for:
   - missing capabilities or contracts;
   - stale names, paths, parameters, examples, defaults, or configuration;
   - contradictions between canonical documents;
   - undocumented security, failure, empty-state, or compatibility behavior;
   - documentation that describes intended behavior but is not implemented;
   - broken links, wrong file references, missing required template sections, and untraceable scenarios.

4. Validate claims.
   - Use targeted tests, static searches, packaging checks, and runtime inspection as appropriate.
   - Treat tests as evidence of behavior, not automatically as documentation requirements.
   - Clearly label claims that are inferred rather than directly verified.
   - Do not report style preferences as gaps unless repository standards require them.

5. In `fix` mode only, close confirmed gaps.
   - Make the smallest documentation-only edits that accurately describe current behavior.
   - Prefer the canonical document and avoid duplicating a contract in several places.
   - Preserve user changes and avoid broad rewrites or speculative requirements.
   - If implementation and documentation disagree, report the conflict and fix documentation only when current implementation is clearly authoritative.
   - Update scenario mappings and changelogs only when required by repository standards; do not fabricate dates, versions, or completed validation.

6. Re-check after edits.
   - Run repository documentation validators, link checks, scenario traceability checks, and relevant tests when available.
   - Inspect the final diff for accidental code/test changes, formatting errors, stale references, and contradictory duplicate contracts.

## Gap classification

Rank confirmed gaps:

- `P0`: documented behavior could cause unsafe operation, security misunderstanding, data loss, or a broken release procedure;
- `P1`: core user-facing, configuration, authentication, or operational contract is missing or materially wrong;
- `P2`: important edge case, error behavior, compatibility detail, or traceability is stale or absent;
- `P3`: minor example, wording, link, or maintainability issue.

Each finding must include:

- the inaccurate or missing claim;
- implementation evidence with an absolute file path and line when practical;
- affected documentation file(s);
- whether it is story-required, implementation-inferred, or optional hardening;
- the smallest correction, and whether it was applied (`fix` mode) or only recommended (`audit` mode).

## Output

Lead with `documentation aligned`, `partially aligned`, or `documentation gaps found`.

Then provide:

1. Findings ordered by priority with file evidence.
2. A compact coverage map: implementation area → canonical documentation → status.
3. Validation performed and exact results.
4. For `fix`, a concise list of changed files and any unresolved conflicts.
5. Recommended follow-up, separating required corrections from optional hardening.

If no gaps are found, state the inspected scope and residual uncertainty. Never claim documentation is current based solely on a story checklist.
