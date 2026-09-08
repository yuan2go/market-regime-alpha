# WP-DAILY-RESEARCH-OPERATIONAL-CLOSURE-02 — Implementation Plan

> **Status:** CURRENT_STATUS
> **Outcome:** IMPLEMENTED_WITH_BOUNDED_VERIFICATION
> **Authority:** Ordered implementation and validation plan only
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-09-08
> **Baseline:** `origin/main@1562855928b2b7e839883838f367876cc49d7391`

## Delivery order

1. Correct current documentation and freeze this design, scope and proof ceiling.
2. Replace negative prospective-series inference with an exact transient manifest/
   Runtime capability; test first declaration, ordinary capture, maintenance,
   concurrent claim, lock loss, crash before/after commit and recovery.
3. Separate current-use prediction admission from all-use frozen Outcome work
   discovery; make scanning bounded, visible and non-starving; correct the
   outstanding-session bound and downtime reason contract.
4. Make daily prediction, collection and settlement Attempts terminalize ordinary
   failures while preserving lease recovery and unknown-effect reconciliation.
5. Add bounded daily health plus separate report/delivery Runtime identity,
   explicit `NOT_CONFIGURED`, fake-channel dedup/retry/receipt/expiry and a stable
   manual research follow-up link.
6. Exercise the focused pure/unit and PostgreSQL gates, then affected Runtime,
   Prospective, Backtest and Daily regressions. Expand only for observed cross-domain
   risk or a mandatory repository gate.
7. Run docs links, Ruff, mypy, build and an installed-wheel smoke. Record every
   command as PASS, FAIL, BLOCKED or NOT_RUN in a new Verification; do not edit the
   prior immutable daily Verification or any registered migration bytes.

## Execution outcome

Steps 1 through 5 were implemented at source/tests commit `c9f7cd14`. Focused
Daily, Prospective, Runtime, Evaluation, schema and compatibility gates passed;
Ruff, mypy, build and installed-wheel resource/import smoke also passed. The
repository-wide pytest command was explicitly stopped by the user at 47%, so it
is `INTERRUPTED / NOT_RUN_TO_COMPLETION`, not PASS. Exact commands, environment
failures and proof ceilings are frozen in the package Verification.

## Checkpoint discipline

- checkpoint 1: design and stale/conflicting current documentation;
- checkpoint 2: prospective positive-admission correction and focused evidence;
- checkpoint 3: daily recovery/history/time/health implementation and tests;
- checkpoint 4: report delivery/follow-up implementation and tests;
- checkpoint 5: final verification/status documentation.

Each checkpoint is dependency-coherent. Before committing: inspect staged and
unstaged scope, preserve `.idea/modules.xml` and private configuration, run
`git diff --check`, and stage only this work package. No push, PR, merge, database
upgrade, service restart, paid Provider call, real notification or trading action
is authorized.
