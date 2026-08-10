---
name: implement-work-package
description: Execute one user-supplied bounded specification or one current Roadmap item from code audit through a validated checkpoint commit.
disable-model-invocation: true
---

Implement exactly one user-supplied specification or one bounded item from `docs/status/Roadmap.md`. Example:

```text
/implement-work-package docs/status/Roadmap.md P1-exact-window-operation
```

There is no standing WP-PDL program. Do not restore deleted plans from Git history.

## Required procedure

1. Read `CLAUDE.md`, `AGENTS.md`, `docs/README.md`, Current State, Capability Matrix and Gap Register.
2. Resolve the bounded request against the current architecture, Current State, Gap Register and Roadmap.
3. Inspect the current workspace with `git status --short --branch`, `git rev-parse HEAD`, `git diff --stat` and untracked-file review.
4. Preserve all user changes. Do not fetch, pull, switch, reset, clean, stash or rewrite history unless explicitly authorized.
5. Never implement directly on `main`; use the current valid isolated branch or create a dedicated branch from the verified local HEAD without discarding changes.
6. Inspect actual code, imports, call chains, migrations and tests in every affected bounded context.
7. Produce a concise baseline:
   - implementation facts;
   - scope and non-goals;
   - invariants and authorities;
   - existing and missing behavior;
   - assumptions requiring verification;
   - blockers and stop conditions.
8. Freeze one dependency-coherent vertical slice. Do not combine unrelated cleanup, factor changes or research hypotheses.
9. Add characterization or regression tests before changing established behavior or compatibility contracts.
10. Implement the smallest complete behavior through domain, persistence, application, adapter and test layers as required.
11. Run focused tests after each coherent increment and fix ordinary failures.
12. Use relevant project subagents for bounded read-only architecture, evidence and verification reviews.
13. Run the full validation suite from `CLAUDE.md`.
14. Update only the current canonical architecture, status and runbook documents when implementation facts change.
15. Review `git diff --check`, the complete diff, migrations, generated files and untracked files.
16. Create one or more semantic checkpoint commits for the completed phase.
17. Do not merge automatically. Open or update a Draft PR only when requested or required by repository workflow.

## Stop conditions

Stop and publish a blocked report only when:

- Constitution or accepted authority documents genuinely conflict;
- PIT, Provider, calibration, risk or business semantics would have to be guessed and no fail-closed behavior is valid;
- historical Artifact identity, model identity or actual-position authority cannot be preserved or explicitly migrated;
- a required external Xuntou/XtQuant or other qualified input is unavailable;
- success requires live broker mutation or another prohibited capability;
- the requested bounded phase depends on an unfinished earlier phase.

Ordinary test failures, refactoring needs, documentation drift and local code defects are not stop conditions. Fix them within scope.

## Final report

Return:

```text
BASELINE AND WORKSPACE STATE
WORK PACKAGE OR PHASE
CODE FACTS AND ASSUMPTIONS
IMPLEMENTATION
CHECKPOINT COMMITS
TESTS AND RESULTS
DOCUMENTATION UPDATES
CAPABILITY BEFORE AND AFTER
MIGRATION AND ROLLBACK EFFECT
AUTHORITIES AND INVARIANTS PRESERVED
EVIDENCE CEILING
REMAINING GAPS
GENUINE BLOCKERS
NEXT DEPENDENCY-READY PHASE
PR URL AND MERGE STATE
```

Never claim Alpha, a model winner, production readiness, live readiness or trading authority without corresponding formal evidence and approval.
