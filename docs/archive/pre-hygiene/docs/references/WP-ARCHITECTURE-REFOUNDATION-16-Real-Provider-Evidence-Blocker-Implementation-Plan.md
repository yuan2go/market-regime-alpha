# WP-16 Real Provider Evidence Gate A Blocker Implementation Plan

> **Status:** CURRENT_STATUS
> **Design:** [WP-16 Gate A blocker design](WP-ARCHITECTURE-REFOUNDATION-16-Real-Provider-Evidence-Blocker-Design.md)
> **Baseline:** `origin/main@16a4ab1d0d42a4144ef1bd1dcd15ac4ba5ab1087`
> **Frozen:** 2026-09-02

## Checkpoint discipline

This is a docs-only external-evidence stop. It does not implement or test a
Provider adapter, schema, multi-Product Authority, Qualification Protocol, or
Formal PIT path. Historical immutable Verification files remain read-only.

## Checkpoint 1 — active documentation cleanup

1. Remove the superseded WP-11 pre-composition blockers from the active
   Repository Convergence Inventory.
2. Reconcile the logical catalog with implemented WP-12 Evidence/Assessment/
   Qualification and WP-14 Provider/Formal Campaign relations.
3. Keep implementation status and proof ceilings in Current State and immutable
   Verification rather than promoting canonical architecture prose.
4. Commit the cleanup independently.

Result: completed by commit `032d538`.

## Checkpoint 2 — freeze Gate A decision and re-entry contract

1. Record the exact four-state feasibility vocabulary.
2. Include BaoStock, Tencent, Tushare, XtQuant, iFinD, Wind, JQData, RQData,
   and AKShare/EastMoney without inflating `B/?` into incapability.
3. Freeze the P0 conjunction and the no-implementation stop.
4. Freeze the external evidence checklist and re-entry contract.
5. Add navigation from the canonical documentation index.

## Checkpoint 3 — immutable blocker Verification

1. Record execution-time main, branch/worktree, final documentation SHA and
   relevant tree/blob identities.
2. Record secret-safe credential/runtime/module availability only; never values.
3. Record official capability references and real probe results with their
   evidence ceiling.
4. Prove the old WP-15 BaoStock identities are unchanged in Git.
5. Record the corrected feasibility matrix and the absence of a P0 `F/F` row.
6. State every unexecuted implementation/qualification gate as `NOT_RUN`, not
   PASS.

## Checkpoint 4 — status reconciliation and applicable validation

1. Update Current State, Roadmap, and Capability Matrix with the exact Gate A
   blocker semantics.
2. Link the design, checklist, plan, and immutable Verification from
   `docs/README.md`.
3. Run documentation metadata/navigation/link tests, applicable architecture
   checks, and `git diff --check`.
4. Inspect staged scope before each commit and keep application, schema, tests,
   credentials, local configuration, and `.idea/modules.xml` untouched.

The following remain `NOT_RUN_BY_GATE_A_STOP` unless a later re-entry produces
an actual implementation:

```text
Provider adapter TDD
Provider Capture campaign
new Provider Qualification Protocol/Decision
PostgreSQL bootstrap/recreate/plans for WP-16 changes
WP-16 concurrency/failure/recovery campaign
full repository pytest/Ruff/mypy/build qualification
remote CI
```
