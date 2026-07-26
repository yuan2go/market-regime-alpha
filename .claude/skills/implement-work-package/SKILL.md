---
name: implement-work-package
description: Execute one declared Market Regime Alpha Work Package from audit through Draft PR. Use when the user asks to implement WP-D0 through WP-D12 or provides a work-package path.
disable-model-invocation: true
---

Implement exactly one Work Package. The argument is the path or identifier, for example:

```text
/implement-work-package docs/roadmap/work-packages/WP-D0-Platform-Governance-Kernel.md
```

## Required procedure

1. Read `CLAUDE.md`, `AGENTS.md`, `docs/README.md`, Current State, Capability Matrix and Gap Register.
2. Resolve the requested Work Package and read every related architecture, research and specification document.
3. Fetch/prune Git refs, verify the actual `main` HEAD and create a dedicated branch. Never work directly on `main`.
4. Inspect current code and tests line by line in the affected bounded contexts.
5. Produce a concise baseline report:
   - facts;
   - scope and non-goals;
   - invariants;
   - existing implementation;
   - missing implementation;
   - blockers and stop conditions.
6. Freeze one primary change. Do not combine unrelated cleanup, factor changes or research hypotheses.
7. Add characterization/regression tests before changing behavior when migration or Legacy compatibility is involved.
8. Implement the smallest coherent change using existing canonical contracts.
9. Run focused tests after each coherent increment.
10. Ask the relevant project subagents to review architecture, evidence and verification when useful.
11. Run the full validation suite from `CLAUDE.md`.
12. Update Current State, Capability Matrix, Gap Register, Work Package evidence and migration/audit documents.
13. Review `git diff --check`, the complete diff and any generated/untracked files.
14. Commit semantically and open a Draft PR. Do not merge automatically unless the user explicitly requested merge and all required checks succeeded.

## Stop conditions

Stop and publish a blocked report when:

- Constitution or authority documents conflict;
- Point-in-Time or provider semantics would need to be guessed;
- historical Artifact identity cannot be preserved or explicitly migrated;
- a required equivalence/regression test fails;
- success would require changing factors, weights, Target, Universe or research conclusion outside scope;
- external Xuntou/XtQuant input is required but unavailable;
- scope expands into a later Work Package.

## Final report

Return:

```text
BASELINE
BRANCH AND COMMITS
FACTS FOUND
IMPLEMENTATION
TESTS AND RESULTS
DOCUMENTATION UPDATES
CAPABILITY BEFORE/AFTER
MIGRATION EFFECT
EVIDENCE CEILING
REMAINING GAPS
BLOCKERS
NEXT WORK PACKAGE
DRAFT PR URL
```

Never claim Alpha, a model winner, live readiness or trading authority without corresponding formal evidence and approval.
