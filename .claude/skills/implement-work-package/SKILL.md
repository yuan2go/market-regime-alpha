---
name: implement-work-package
description: Execute one declared Market Regime Alpha Work Package or one bounded WP-PDL phase from code audit through a validated checkpoint commit. Use when the user supplies a work-package path or requests exactly one bounded phase.
disable-model-invocation: true
---

Implement exactly one Work Package or one explicitly bounded phase. Examples:

```text
/implement-work-package docs/roadmap/work-packages/WP-D0-Platform-Governance-Kernel.md
/implement-work-package docs/roadmap/work-packages/WP-PDL-Production-Decision-Lifecycle.md phase-2
```

For continuous execution of the complete WP-PDL program, use `/advance-production-lifecycle` instead.

## Required procedure

1. Read `CLAUDE.md`, `AGENTS.md`, `docs/README.md`, Current State, Capability Matrix and Gap Register.
2. Resolve the requested Work Package or phase and read every related architecture, domain, research, specification, audit and runbook document.
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
14. Update Current State, Capability Matrix, Gap Register, Work Package evidence, architecture/runbook and delivery audit documents when implementation facts change.
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
