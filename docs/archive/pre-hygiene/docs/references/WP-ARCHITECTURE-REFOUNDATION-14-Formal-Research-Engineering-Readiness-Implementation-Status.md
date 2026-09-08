# WP-14 Formal Research Engineering Readiness Implementation Status

> **Status:** CURRENT_STATUS
> **Authority:** Mutable status read model; exact-SHA proof remains in the immutable WP-14 Verification
> **Owner:** Market Regime Alpha maintainers
> **Recorded At:** 2026-09-02 (Asia/Shanghai)
> **Execution-Time Origin Main:** `origin/main@eb7970b4833228a2faba6715c65c26dae88f6ee5`
> **Implementation Checkpoint:** `ca6f66b50ec2c55250cd82d2fa1ed6c5f35c29b8`
> **Branch:** `agent/wp-14-formal-research-readiness`
> **Worktree:** isolated linked worktree `wp-14-formal-research-readiness`; primary checkout untouched
> **Schema Epoch:** `MRA_REFOUNDATION_1 / DRAFT / NOT_CUT_OVER`

```text
WP13 = MERGED / EXIT_GATE_PASS
WP14 = IMPLEMENTED_AND_QUALIFIED
WP14_EXIT_GATE = PASS
FORMAL_RESEARCH_ENGINEERING_READY = true
FORMAL_PIT / FORMAL_OOS = NOT_PROVEN
PROSPECTIVE_PROVEN / PROVIDER_QUALIFIED / ALPHA_PROVEN = NO
Runtime dispatch / CLI Cutover = NO-GO
```

The immutable
[WP-14 Verification](WP-ARCHITECTURE-REFOUNDATION-14-Formal-Research-Engineering-Readiness-Verification.md)
owns the exact proof. This page grants no empirical research or Provider claim.

## Implemented mechanics

The existing Runtime owns exact Decision Proof and Due Proof DAGs. The existing
Research & Qualification Authority owns immutable Formal Campaign
predeclaration, complete FIT/VALIDATION/LOCKED_OOS plans, actual Partition and
Experiment binding, protected zero-access opening, database-clock due
inspection, and read-only reconciliation. Market owns purpose-specific
Provider Qualification Protocol/requirements/finality/decision rosters and
qualified source visibility. Formal PIT and Formal Dataset seams require exact
admitted recorded-provider facts and fail closed for engineering rehearsals.

The sole target composition root constructs all new commands and read ports,
without Runtime business dispatch or CLI cutover. Existing Outcome,
Evaluation, Evidence, Assessment, Qualification, and WP-13 Decision Support
commands remain the only business owners used by proof profiles.

## Persistence and qualification

WP-14 extends unreleased `001_baseline.sql` to 129 tables and four views; it
adds no `002+`, second Runtime, generic registry/UoW, JSON business Authority,
nullable future FK, compatibility writer, dual write, Model, Calibration, or
Execution placeholder.

At implementation `ca6f66b50ec2c55250cd82d2fa1ed6c5f35c29b8`, clean
PostgreSQL 16 bootstrap/verify/exact-OID recreate, real concurrency/failure/
recovery/replay, six representative plans, 19 focused, 604 refoundation, 33
platform, 286 PostgreSQL persistence, and all 3,644 repository tests pass.
Ruff, mypy, build, docs/navigation, architecture/import, schema/catalog, and
diff gates pass. GitHub Actions remains disabled, so remote CI is
`BLOCKED_BY_REPOSITORY_CONFIGURATION / NOT_RUN`.

## Handoff boundary

WP-15 is dependency-ready only after this branch is pushed, reviewed, merged,
latest `origin/main` is fetched again, and merged main is proved to contain the
WP-14 Verification and exact implementation checkpoint. It must use a new
Campaign branch/worktree and real recorded Provider data/timestamps.

The following remain expressly unsupported:

```text
Formal Provider qualification or Formal PIT
completed Locked OOS or sustained Prospective proof
Alpha value or cost evidence
Model / ModelVersion / Calibration
Runtime dispatch / CLI Cutover / Legacy deletion
Execution / broker / automatic trading / Production readiness
```
