---
name: check-test-gaps
description: Review current functionality and available tests to identify behavior, integration, regression, and traceability gaps. Use for audit-only analysis by default, or with an explicit `fix` argument to close confirmed gaps.
---

# Check Test Gaps

Assess what the code currently does, what the tests actually prove, and what remains unverified. Default mode is audit-only. An explicit `fix` argument, for example `$check-test-gaps fix`, authorizes closing confirmed gaps.

## Inputs

- Repository or workspace in scope.
- Optional GitHub issue/story URL. If provided, read it through GitHub tools first, then use the story as an additional requirement source.
- Optional feature, module, command, MCP tool, or commit scope. If omitted, infer the smallest relevant scope from the request and recent implementation changes.
- Optional mode: `fix`. Without it, make no repository changes.

## Workflow

1. Establish scope.
   - Inspect the working tree and recent relevant diffs without reverting user changes.
   - Locate implementation entry points under `src/`, CLI wrappers, configuration, documentation, and `tests/`.
   - If a GitHub story is supplied, separate explicit acceptance criteria from examples, test suggestions, and incidental narrative. Do not merely replay the story's test list.

2. Build a behavior inventory from the implementation.
   Cover, when applicable:
   - happy paths and empty states;
   - malformed input, validation, and boundary values;
   - authentication, authorization, and hidden-resource behavior;
   - command output, MCP tool responses, errors, filtering, sorting, pagination, and idempotency;
   - local storage, indexing, vectorization, external services, retries, and cleanup;
   - backward compatibility, packaging, configuration, and documentation contracts.

3. Map tests to behavior.
   - Search unit, smoke, integration, contract, scenario, and end-to-end tests.
   - Distinguish mocked tests from tests that exercise real external or runtime boundaries.
   - Treat assertions that only inspect registration, strings, or mock calls as contract evidence, not proof of runtime behavior.
   - Check whether scenario documentation and tests are bidirectionally traceable when the repository uses scenario catalogs.

4. Exercise the smallest useful verification set.
   - Run targeted existing tests first.
   - Follow repository-required validation skills and commands for the affected area.
   - If a test cannot run, report the exact blocker and do not convert an unexecuted check into a pass.

5. Identify and rank gaps.
   Report only evidence-backed gaps. Classify each as:
   - `P0`: likely production failure, security issue, data loss, or broken core contract;
   - `P1`: important behavior or integration path is unverified or likely regressed;
   - `P2`: meaningful edge case, compatibility, or contract gap;
   - `P3`: low-risk completeness or maintainability gap.

   A gap should include the behavior at risk, implementation and test evidence, why existing coverage is insufficient, the smallest closing change, and whether it is required or optional hardening.

6. If `fix` was explicitly requested, close confirmed gaps.
   - Add or strengthen the smallest high-value tests first, preferring real runtime coverage where risk crosses a boundary.
   - Update scenario documentation and traceability mappings when the repository requires them.
   - If analysis proves the implementation defective, make the smallest production fix and apply all applicable documentation and testing skills.
   - Run targeted tests after each logical fix, then repository-required validation.
   - Preserve unrelated user changes and report any gap that remains blocked.

## Fresh-opinion rules

- Do not assume the story's proposed tests are complete or correct.
- Do not call a feature covered merely because a test has the right name.
- Prefer a small number of high-value runtime scenarios over broad shallow assertions.
- Verify allowed and denied behavior separately where access control exists.
- Verify empty, missing, and invalid cases separately.
- Separate implementation defects from test gaps. If behavior is wrong, say so even when a test exists.
- Do not invent requirements from style preferences. Mark recommendations beyond the supplied story as hardening.

## Output

Lead with `covered`, `partially covered`, or `not covered`.

Then provide findings ordered by priority, a behavior-to-test coverage map, exact validation results, and recommended next actions separated into required closure and optional hardening. In `fix` mode, also provide changed files and final validation results. In audit mode, explicitly state that no files were changed.
