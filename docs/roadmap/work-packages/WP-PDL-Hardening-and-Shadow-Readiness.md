# WP-PDL-HARDENING — Production Lifecycle Hardening and Shadow Readiness

> **Status:** ROADMAP
> **Authority:** Dependency-ordered implementation work package for hardening the delivered Phase 0–7 lifecycle
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-01
> **Supersedes:** None
> **Superseded By:** None
> **Related Documents:** WP-PDL-Production-Decision-Lifecycle.md, ../../architecture/11-Production-Lifecycle-Hardening-and-Shadow-Operations.md, ../../audit/Production-Lifecycle-Hardening-Baseline.md, ../../operations/Production-Decision-Lifecycle-Runbook.md
> **Code Evidence:** Baseline `a7ce0b444e77506a85e1c1c7b240c22c8421580d`; each phase requires its own commit-bound delivery evidence

## 1. Objective

Harden the existing modular-monolith lifecycle from complete operational
evidence through manual/synthetic Shadow outcome, then establish engineering
Shadow readiness without adding LIVE broker mutation or claiming production
data, parameters, calibration or Alpha.

This work extends, rather than replaces, WP-PDL. It preserves existing V1
schemas and readers and introduces new schema identities for stronger
semantics.

## 2. Current code facts

The baseline already provides durable Opportunity/Thesis, Portfolio/Risk and
Manual Execution SQLite repositories; Fill-derived Position projection;
Holding/Exit models; an immutable LifecycleReview package; Signal/Path
Artifacts; and an Operational Research Bridge.

The baseline gaps are:

- allocation-local rather than account-complete Portfolio/Risk;
- incomplete Thesis-to-Outcome authority binding;
- no Fill-derived A-share sellable-quantity authority;
- no dedicated reducing-risk gate;
- caller-authored Thesis support booleans;
- no composite operational manifest or operational evidence kind;
- no durable assessment state;
- no recoverable Shadow operation;
- no complete Signal incremental-value and Path calibration infrastructure.

The exact baseline evidence is recorded in
`docs/audit/Production-Lifecycle-Hardening-Baseline.md`.

## 3. Non-goals

- LIVE_ORDER, QMT, PTrade or any broker write;
- automatic trade execution;
- automatic model promotion or risk-limit mutation;
- production risk, position-size, horizon, barrier, stop or concentration
  defaults;
- formal PIT, OOS, calibration, Alpha or return claims;
- a QuantDesk UI or microservice split;
- expanding Legacy or `daily_research` behavior;
- changing MR1 next-session 10:30 semantics;
- replacing DailyRun, SourceManifest, immutable Artifact or Fill authority.

## 4. Domain invariants

1. Candidate, Signal, Forecast, Opportunity, Thesis, Portfolio, Risk,
   Execution, Position, Assessment and Evaluation remain separate authorities.
2. All increasing-risk decisions use a complete reconciled account snapshot.
3. All actual Position state derives from effective Fill only.
4. A reducing-risk gate can never authorize an increasing delta.
5. T+1 uses the explicit trading-calendar authority, never weekday inference.
6. One account/symbol has at most one open Thesis book in the first version.
7. Every Fill and TradeOutcome has a complete upstream authority trace.
8. External callers submit evidence references, not final Thesis-health
   conclusions.
9. Composite manifests index original authorities and do not replace them.
10. Mutable aggregates use optimistic versioning and command idempotency.
11. Manual actions record actor, reason and time; histories are append-only or
    exactly reconstructible.
12. Missing, stale, late, conflicting, incomplete or unreconciled facts fail
    closed, except that unavailable increasing-risk service alone does not
    block an otherwise valid strictly reducing execution gate.
13. `FORMAL_OOS_ALPHA_NOT_ESTABLISHED` and
    `TRADING_AUTHORITY_NOT_GRANTED` remain visible.

## 5. Phase dependency graph

```text
H0 Baseline
 ├─ H1 Complete-account Portfolio/Risk
 │   ├─ H2 Traceability
 │   │   └─ H3 T+1 Position authority
 │   │       └─ H4 Increasing/reducing split
 │   │           └─ H7 Durable assessment state
 │   │               └─ H8 Shadow operations
 │   └─ H5 Thesis-health builder
 └─ H6 Composite operational evidence
H1–H8 ──> H9 validation infrastructure where external data is not required
```

The implementation proceeds in H0–H9 order to keep migrations and application
composition reviewable.

## 6. H0 — Baseline and gap review

### Scope

- read the required documentation and actual code paths;
- verify the twelve specified weaknesses against classes, repositories, SQL,
  CLIs and tests;
- run the unchanged baseline quality gate;
- create this Work Package, Architecture 11, a baseline audit and an execution
  plan;
- correct current-state prose that still describes Phase 0–7 as target-only.

### Acceptance

- each issue is confirmed, denied or redefined with code evidence;
- branch, HEAD and dirty workspace are recorded;
- no runtime or migration change exists;
- all baseline gates pass;
- one documentation-only semantic checkpoint is created.

### Rollback

Revert the H0 documentation commit. No runtime or database state changes.

## 7. H1 — Complete-account Portfolio and Risk Authority

### Deliverables

- `AuthoritativeAccountPortfolioSnapshot` with account, as-of, source,
  NAV/cash, all positions, reconciliation, version and content hash;
- `ProposedTradeDelta` and content-identified `PostTradePortfolioSnapshot`;
- Portfolio construction and independent Risk over the resulting full account;
- explicit completeness, freshness and reconciliation gates;
- repository Protocol and SQLite migration/recovery support.

### Acceptance tests

- existing unrelated holdings can breach gross, theme and loss limits;
- omitted existing holdings, stale snapshots and reconciliation fail closed;
- empty accounts, pure reduction and full closure are deterministic;
- idempotency, restart and repository contract tests pass.

### Rollback

Stop H1 commands and retain previous decisions read-only. The isolated down
migration is permitted only for disposable local/test databases after export.

### Implementation evidence

Delivered on the H1 checkpoint with V2 content-addressed account/configuration/
post-trade contracts, complete-account constraint evaluation, storage-neutral
repository, atomic SQLite migration 005, CLI, idempotency and restart restore.
Focused tests cover unrelated-holding gross/theme/loss, partial/stale/
unreconciled input, empty account, pure reduction, closure and rollback.

The source Position ID/hash is retained, but H3 still owns Fill/calendar-derived
sellability. All named limits are synthetic explicit fixture configuration.

## 8. H2 — Complete authority trace

### Deliverables

- one open `account_id + symbol` Thesis/position book constraint;
- ManualTradeRecord binds Thesis, Opportunity, Portfolio, Risk and exact target;
- Fill and Position retain book, manual-trade and Fill provenance;
- TradeOutcome verifies the complete chain;
- historical books remain separable after close and replay.

### Acceptance tests

- duplicate open Thesis, mismatched trade/Thesis, cross-book Fill and mixed
  Outcome fail;
- close then new Thesis succeeds without merging history;
- Fill correction, restart and replay retain the trace.

### Rollback

Disable new commands; preserve V1 readers and append-only ledger. Do not
rewrite historical Fill identities.

## 9. H3 — Fill-derived A-share T+1

### Deliverables

- PositionLot V2 availability, frozen quantity, trade date, sellable session
  and settlement fields;
- PositionSnapshot V2 total/available/frozen/today-acquired authority;
- projector input includes identified TradingCalendarArtifact and explicit
  market-executability evidence;
- Risk derives sellable quantity only from Position Authority.

### Acceptance tests

- same-day sell rejected; Friday/Monday and holiday calendars resolve from
  explicit sessions; suspension and missing calendar fail closed;
- partial sells, multiple lots, correction, cross-day replay and restart are
  deterministic.

### Rollback

Retain Fill history, stop V2 projections and rebuild from the previous verified
code only for read-only comparison. Never synthesize sellability.

## 10. H4 — Increasing-risk and reducing-risk separation

### Deliverables

- typed increasing-risk classification and unchanged full Risk approval;
- independent `RiskReducingExecutionGate` with structured states;
- manual actor/reason audit and no route from increasing delta to reducing gate.

### Acceptance tests

- normal Risk timeout does not block a valid full exit;
- reduction cannot increase exposure or exceed sellable quantity;
- reconciliation, suspension, missing execution state and T+1 produce the
  specified blocked states;
- audit and bypass tests pass.

### Rollback

Stop reducing-gate commands. Existing EXIT/REDUCE assessments remain evidence,
not orders.

## 11. H5 — ThesisHealthObservationBuilder

### Deliverables

- versioned builder configuration;
- verified Market/Theme/Capital/Signal/price Artifact inputs;
- deterministic support, invalidation and missingness derivation;
- CLI/API input contains references and config only.

### Acceptance tests

- hash/time/symbol/theme mismatch and missing Capital fail closed;
- expired Signal, risk-off regime and invalidation conditions are derived;
- replay is deterministic and no support-boolean command path remains.

### Rollback

Disable assessment commands that require V2 observations. Keep old V1 package
readers for compatibility; do not accept old caller booleans in the new path.

## 12. H6 — Composite operational evidence manifest

### Deliverables

- `CompositeOperationalInputManifest` with Daily and supplemental identities,
  hashes and per-field authority references;
- `OPERATIONAL_EXPLORATORY_ARCHIVE` evidence kind;
- exact reader/replay and eligibility ceiling checks.

### Acceptance tests

- time/hash/source conflicts, missing per-field authority and eligibility
  inflation fail;
- replay retains both original SourceManifests;
- operational evidence cannot become LIVE or formal PIT.

### Rollback

Stop V2 bridge publication. Original Daily and supplemental Artifacts remain
independently readable and unchanged.

## 13. H7 — Durable Holding, Exit and exception state

### Deliverables

- storage-neutral assessment repository and SQLite adapter;
- append-only assessment/schedule/action/exception/acknowledgement events;
- CAS latest-state projection and corruption detection;
- pending reduction, blocked execution, stale evidence and reconciliation
  states.

### Acceptance tests

- duplicate, stale position/Thesis, concurrent assessment, restart, blocked
  exit, acknowledgement and append-only checks;
- migration up/down and projection rebuild tests.

### Rollback

Stop writes, retain event history read-only and rebuild projections. Down
migration is disposable/test-only after export.

## 14. H8 — Shadow Operations

### Deliverables

- CLI-first recoverable ShadowRun and stage receipts;
- idempotent schedule, restart recovery and correlation IDs;
- active Thesis/Position, assessment, exception and reconciliation queues;
- manual-recorded and explicitly synthetic Shadow Fill sources;
- structured logs, metrics, alerts, acknowledgement and daily report;
- synthetic end-to-end and updated runbook.

### Acceptance tests

- duplicate schedule produces no duplicate effect;
- interruption at each durable stage resumes exactly;
- queues and metrics reflect structured failures;
- every Fill traces and every Position rebuilds;
- no broker mutation path exists;
- complete synthetic E2E and full quality gate pass.

### Shadow readiness admission

The status may become `SHADOW_READY_ENGINEERING` only when Architecture 11
criteria pass. The repository must still state that no real sustained Shadow
period has been observed.

### Rollback

Pause scheduling, retain receipts/events/reports, rebuild projections and run
manual reconciliation. No DailyRun or Artifact deletion is allowed.

## 15. H9 — Model-validation infrastructure

### Deliverables

- PIT-preserving validation datasets and complete comparison groups;
- cost, purge, embargo, walk-forward, regime/theme segmentation, ablation,
  calibration and selection-bias diagnostics;
- `EmpiricalPathBaselineV1` classification and a bounded PathForecastV2
  contract for conditional buckets/pooling/sample gates/uncertainty;
- versioned metrics including incremental value versus baseline.

### Acceptance

Synthetic/fixture protocols and leakage tests pass. No result is represented as
formal OOS, calibrated or production-effective without external qualified data.

### Rollback

Stop validation publication; immutable inputs and prior research outputs remain
unchanged. Evaluation never mutates Model Registry or weights.

## 16. Database and migration requirements

- migrations continue after 004 and are isolated by bounded context;
- no change to `daily_runs`, stage receipts or Artifact semantics;
- all mutable aggregates have `version` and all command paths have unique
  idempotency protection;
- event and Fill histories are append-only or database-protected;
- every migration has an up/down test and an operational safe-rollback note;
- repository contracts make no SQLite-specific promise and allow PostgreSQL;
- operational tables store references/hashes, never a duplicate Artifact body.

## 17. Per-phase validation and evidence

Every phase runs focused unit, integration, repository, migration,
concurrency/CAS, idempotency, recovery, replay, leakage and compatibility tests
as applicable, followed by:

```bash
git diff --check
python scripts/check_docs_links.py
python -m pytest -q tests/scripts/test_check_docs_links.py
python -m pytest -q tests/platform
python -m pytest -q
python -m ruff check .
python -m mypy
```

Each command is recorded as PASS, FAIL, NOT_RUN or BLOCKED. Each phase updates
Current State, Capability Matrix, Gap Register, this Work Package,
Architecture 11, the runbook and its commit-bound delivery audit before its
semantic checkpoint commit.

## 18. Genuine external blockers

- qualified formal Provider and PIT Theme mapping data;
- real current operational supplemental evidence;
- formal Signal incremental-value, Path calibration and OOS evidence;
- approved production risk and portfolio parameters;
- production authentication/authorization and database operations;
- real consecutive 20–60 trading-day Shadow evidence;
- any request that would require LIVE_ORDER or broker mutation.

These blockers limit evidence claims. They do not block synthetic engineering
work through H8 or validation infrastructure that fails closed without them.
