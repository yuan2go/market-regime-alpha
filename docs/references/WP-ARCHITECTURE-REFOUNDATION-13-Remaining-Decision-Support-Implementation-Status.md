# WP-13 Remaining Decision Support Closure Implementation Status

> **Status:** CURRENT_STATUS
> **Authority:** Mutable implementation/status record; exact-SHA engineering proof remains in the immutable WP-13 Verification
> **Owner:** Market Regime Alpha maintainers
> **Recorded At:** 2026-09-02 (Asia/Shanghai)
> **Execution-Time Origin Main:** `origin/main@6e0ad150057e43a89843eb4fb307e0373d5572ac`
> **Implementation Checkpoint:** `fc5993e5d9e05dbe2845659140108e1051cf3704`
> **Branch:** `agent/wp-13-remaining-decision-support-closure`
> **Worktree:** isolated linked worktree `wp-13-remaining-decision-support-closure`; primary checkout untouched
> **Schema Epoch:** `MRA_REFOUNDATION_1 / DRAFT / NOT_CUT_OVER`

```text
WP12 = MERGED / EXIT_GATE_PASS
WP13 = IMPLEMENTED_AND_QUALIFIED
WP13_EXIT_GATE = PASS
Runtime dispatch / CLI Cutover = NO-GO
Formal PIT / Locked OOS / Prospective = NOT_PROVEN
Provider qualification / Alpha / Production = NOT_PROVEN
```

WP-13 is implemented in the existing Decision Support Authority. The exact
proof is the immutable
[WP-13 Verification](WP-ARCHITECTURE-REFOUNDATION-13-Remaining-Decision-Support-Verification.md).
This status page grants neither target business cutover nor empirical research,
Provider, trading, or Production authority.

## Implemented closure

```text
ResearchQualification(n)
→ exact zero-or-more DecisionRun qualification roster(n+1)
→ PIT Context
→ immutable Strategy Version
→ complete Signal + rule-based uncalibrated Forecast
→ complete Opportunity + typed Thesis conditions
→ complete Portfolio Proposal
→ Decision-Support-only Risk Decision
```

The sole target composition root constructs every WP-13 command and read-only
DecisionRun verifier. Runtime dispatch and business CLI commands still do not
call them. Model, ModelVersion, Calibration, Account, Intent, Order, Fill,
Position mutation, broker integration, and Execution remain absent.

Every aggregate freezes complete ordered relational rosters with concrete FKs,
PostgreSQL-authoritative time, deterministic hashes, exact receipts, audit, and
optional live fences. Rule-based Forecast explicitly remains uncalibrated and
has no Model placeholder. Risk has constant scope `DECISION_SUPPORT_ONLY`; an
`AUTHORIZED` result cannot create an execution fact.

## Persistence and proof state

The unreleased `001_baseline.sql` adds 30 WP-13 tables and no `002+` migration,
generic registry, JSON business Authority, nullable future FK, compatibility
writer, or dual write. The qualified PostgreSQL 16 catalog has 108 tables,
four views, 845 indexes, 1,196 constraints, 89 functions, 224 non-internal
triggers, and 2,467 catalog objects.

At implementation `fc5993e5d9e05dbe2845659140108e1051cf3704`, clean
bootstrap/verify/recreate, real identical and changed-request concurrency,
stale-fence zero-write, injected mid-roster rollback, unknown-commit exact
probe/replay, read-only reconciliation, representative `EXPLAIN (ANALYZE,
BUFFERS)` plans, all 3,625 repository tests, Ruff, mypy, build, documentation,
architecture/import, and diff gates pass. GitHub Actions is disabled, so remote
CI is `BLOCKED_BY_REPOSITORY_CONFIGURATION / NOT_RUN`, not PASS.

## Handoff boundary

WP-14 Formal Research / OOS / Prospective Engineering Readiness is dependency-
ready only after this branch is pushed, reviewed, merged, latest `origin/main`
is fetched again, and that merged main is proved to contain this Verification
and exact implementation checkpoint. WP-14 must use a new branch and worktree.

The following remain expressly unsupported:

```text
Model / ModelVersion / Calibration
Runtime dispatch / CLI Cutover / Legacy deletion
Execution / Account / broker / Order / Fill / Position mutation
Formal Provider qualification or Formal PIT
Locked OOS or sustained Prospective proof
Alpha value, automatic trading, or Production readiness
```
