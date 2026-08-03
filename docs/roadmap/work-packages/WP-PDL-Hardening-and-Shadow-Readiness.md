# WP-PDL-HARDENING — Production Lifecycle Hardening and Shadow Readiness

> **Status:** ROADMAP
> **Authority:** Dependency-ordered implementation work package for hardening the delivered Phase 0–7 lifecycle
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-04
> **Supersedes:** None
> **Superseded By:** None
> **Related Documents:** WP-PDL-Production-Decision-Lifecycle.md, ../../architecture/11-Production-Lifecycle-Hardening-and-Shadow-Operations.md, ../../audit/H6-Composite-Operational-Evidence-Delivery.md, ../../audit/H5-Thesis-Health-Delivery.md, ../../audit/H4-Risk-Route-Delivery.md, ../../audit/Production-Lifecycle-Hardening-Baseline.md, ../../operations/Production-Decision-Lifecycle-Runbook.md
> **Code Evidence:** H6 hardened checkpoint `654e02556080d1476b399ee5145989be743f47a0`; H5 checkpoint `831edd6b2ae044d3bd1f3abcec97a30e47082071`; H4 checkpoint `3672067549e1b72a8bfd390f8320e2a7c55c599e`; each later phase requires its own commit-bound delivery evidence

## 1. Objective

Harden the existing modular-monolith lifecycle from complete operational
evidence through manual/synthetic Shadow outcome, then establish engineering
Shadow readiness without adding LIVE broker mutation or claiming production
data, parameters, calibration or Alpha.

This work extends, rather than replaces, WP-PDL. It preserves existing V1
schemas and readers and introduces new schema identities for stronger
semantics.

## 2. Current code facts

The current checkpoint provides durable Opportunity/Thesis, complete-account
Portfolio/Risk, H4 reducing-risk and Manual Execution SQLite repositories;
Fill-derived Position projection; Holding/Exit models; an immutable
LifecycleReview package; Signal/Path Artifacts; and an Operational Research
Bridge.

The remaining gaps after H5/H6 delivery are:

- H5 Decision aggregate input is not yet loaded from repository authority;
- no qualified real Composite Operational Evidence producer/run sample;
- no reducing-decision-to-ManualTrade execution bridge;
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

### Implementation evidence

Delivered on the H2 checkpoint with `PositionBook`, exact V2
`ManualTradeRecord`/`PositionSnapshot` schemas, an immutable SQLite trace
index and `TraceableTradeOutcome`. Migration 006 creates no Fill table and
does not change migration 004. Tests cover active-Thesis uniqueness,
Opportunity/Thesis expiry, upstream mismatch, cross-book Fill, correction,
close/reopen, restart/replay and isolated down migration. H3 still owns all
sellable-quantity and trading-calendar semantics.

## 9. H3 — Fill-derived A-share T+1

### Deliverables

- PositionLot V3 availability, frozen quantity, trade date, sellable session
  and settlement fields;
- PositionSnapshot V3 total/available/frozen/today-acquired authority;
- projector input includes identified TradingCalendarArtifact and explicit
  market-executability evidence;
- Risk derives sellable quantity only from Position Authority.

### Acceptance tests

- same-day sell rejected; Friday/Monday and holiday calendars resolve from
  explicit sessions; suspension and missing calendar fail closed;
- partial sells, multiple lots, correction, cross-day replay and restart are
  deterministic.

### Rollback

Retain Fill history, stop V3 projections and rebuild from the previous verified
code only for read-only comparison. Never synthesize sellability.

### Implementation evidence

Delivered on the H3 checkpoint with an exact V3 Position schema, settled lot
fields, typed symbol-session status evidence and the existing explicit
TradingCalendarArtifact. The hardened Risk application enumerates all OPEN
books and builds account positions from those V3 projections; arbitrary
available quantity is not an input. Tests cover same-session restriction,
Friday/Monday, a holiday gap, suspension, partial/multi-lot sells, correction,
missing/late evidence, canonical Reader and SQLite restart. H3 adds no table or
migration. All evidence remains synthetic/manual.

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

### Implementation evidence

Delivered and review-hardened at `3672067549e1b72a8bfd390f8320e2a7c55c599e` with SQLite persistence,
canonical restoration, command/decision append-only triggers, semantic
idempotency, explicit Position/Observation freshness, public exports and a
decision-only CLI. H4 does not create ManualTrade, Fill or Broker Order.

## 11. H5 — ThesisHealthObservationBuilder

### Implementation contract

| Concern | Contract |
|---|---|
| Business goal | Replace operator-authored health booleans with deterministic health derived from verified lifecycle evidence. |
| Input Artifacts | Active TradingThesis, Signal, PathForecast, Market/Theme/Capital observations, price/invalidation evidence and versioned health configuration. |
| Output Artifact | Content-addressed `ThesisHealthObservationV2` with support, invalidation, missingness and evidence references. |
| State machine | Observed priority is `INVALIDATED > DATA_INSUFFICIENT > WEAKENING > HEALTHY`; effective state is monotonic `HEALTHY → WEAKENING → INVALIDATED`, while observed `DATA_INSUFFICIENT` preserves prior effective state and a first insufficient observation establishes no effective state. |
| Idempotency key | Thesis ID/version + decision time + exact input/config hashes. |
| Persistence tables | `thesis_health_observations` and `thesis_health_commands`, both append-only; latest state is a rebuildable projection. |
| Transaction boundary | Resolve command, validate all Readers/times/scope, insert observation and command atomically. |
| Failure recovery | Replay from immutable inputs; conflicting key/hash fails; partial write rolls back; corrupt projection rebuilds from events. |
| Audit evidence | Source IDs/hashes, configuration ID, decision time, derived reason codes and builder revision. |
| Tests | Hash/time/symbol/theme mismatch, stale Signal, missing Capital, invalidation derivation, replay/restart, tamper and rollback. |
| Completion condition | No new H5 caller can submit free-form health state; focused/full gates and commit-bound delivery pass. |
| Dependencies | H4 green baseline; feeds H6/H7 and never bypasses Risk. |

### Implementation evidence

Delivered and hardened at `831edd6b2ae044d3bd1f3abcec97a30e47082071` with typed rules, explicit configuration, strict canonical/current-evidence validation, content-addressed V2 Observation, migration 008, append-only SQLite command/observation persistence, recursive Builder replay, command-row tamper validation, semantic idempotency, verified package-path CLI and a thin Holding/Exit adapter. The Application Service constructs the replay bundle from actual domain inputs; the adapter consumes derived effective health directly, requires a Thesis-scoped T+1 PositionSnapshot and does not construct a V1 support-boolean Observation.

The H5 private replay bundle is not H6 authority. H5 does not transition a Thesis, call H4, create ManualTrade/Fill/order, or change the historical LifecycleReview package schema.

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

Disable assessment commands that require V2 observations and stop new migration
008 writes. Existing append-only observations remain readable. Keep old V1
package readers for compatibility; do not accept old caller booleans in the new
path.

## 12. H6 — Composite operational evidence manifest

### Implementation contract

| Concern | Contract |
|---|---|
| Business goal | Represent runtime-composed evidence honestly without labelling it `HISTORICAL_IMMUTABLE_ARCHIVE`. |
| Input Artifacts | Verified Phase D Daily Decision package, verified Supplemental Research Evidence package and explicit composition policy. |
| Output Artifact | `CompositeOperationalInputManifest` plus exact Reader/index and `OPERATIONAL_EXPLORATORY_ARCHIVE` evidence kind. |
| State machine | `ASSEMBLING → VERIFIED | DATA_INSUFFICIENT | CONFLICTED`; verified does not promote authority. |
| Idempotency key | Decision time + ordered component manifest IDs/hashes + composition policy ID. |
| Persistence tables | `composite_operational_manifests`, `composite_operational_components`, `composite_operational_field_authorities`, `composite_operational_commands`; immutable artifact files remain primary evidence. |
| Transaction boundary | Validate and atomically publish the file package first, then use `BEGIN IMMEDIATE` for manifest/component/field/command indexes; no cross-storage atomicity claim. |
| Failure recovery | Original component Artifacts remain independent; retry composition by key; orphan staging is verified or discarded without mutating sources. |
| Audit evidence | Both original manifests, per-field source/availability/finality, policy identity, ceiling and complete missingness report. |
| Tests | Source/time/hash conflict, missing coverage, eligibility inflation, replay, exact file set, tamper, crash before/after publish. |
| Completion condition | Operational bridge consumes the composite type and never misclassifies runtime composition as historical/formal PIT. |
| Dependencies | H5 input needs and current bridge contracts; feeds H4.5/H7/H8. |

### Implementation evidence

Delivered and review-hardened at `654e02556080d1476b399ee5145989be743f47a0` with
content-addressed policy and terminal manifest, typed component/field authority,
exact three-file package, file-first crash recovery, migration 009,
append-only SQLite idempotency/replay, independent `ResearchInputBundleV2`,
`OPERATIONAL_EXPLORATORY_ARCHIVE`, strict V2 operational CLI/Runner, V1 Reader
compatibility and H6→Platform V2→H5 integration. The V2 route reloads original
packages and replays the Builder before research. It preserves Daily as the
primary SourceManifest and never promotes PIT/OOS/trading authority.

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

## 12A. H4.5 — Risk-Reducing Decision to Manual Execution Bridge

H4.5 is design-only here and is not required for H4 completion. It must be
completed before or as the first dependency-coherent slice of H7.

### Implementation contract

| Concern | Contract |
|---|---|
| Business goal | Allow an authenticated operator to turn a still-valid permitted reducing decision into a manual trade intent without creating broker authority. |
| Input Artifacts | `PERMITTED_FOR_MANUAL_CONFIRMATION` RiskReducingDecision, its original evidence, latest PositionSnapshot, fresh execution observation and authenticated confirmer. |
| Output Artifact | ManualTrade V2 intent plus append-only `RiskReductionConfirmation` linking `risk_reducing_decision_id`; no Fill is created. |
| State machine | `AWAITING_CONFIRMATION → CONFIRMED_INTENT | EXPIRED | POSITION_CHANGED | BLOCKED_ON_RECHECK | CANCELLED`; execution/Fills remain separate. |
| Idempotency key | Risk-reducing decision ID + latest Position version/hash + operator intent nonce. |
| Persistence tables | Migration introduces route-separated ManualTrade V2 references and confirmation events/commands; existing OPEN/ADD rows migrate as `INCREASING` and keep complete-account Risk references. |
| Transaction boundary | Lock command, reload decision, verify permission/expiry, rebuild latest sellability, require exact Position version, then atomically write confirmation and ManualTrade intent. |
| Failure recovery | Any Position/available-quantity change invalidates reuse and requires a new H4 decision; transaction rolls back on either write; restart resolves the command ledger. |
| Audit evidence | `risk_reducing_decision_id`, confirmed by/at/reason, prior/latest Position IDs/hashes, recheck observation/config and resulting ManualTrade ID. |
| Tests | Expired decision, non-permitted state, stale/current Position mismatch, T+1 change, duplicate/conflict, rollback, restart, OPEN/ADD route separation and authentication. |
| Completion condition | A permitted decision can create one traceable manual intent only after recheck; it cannot create Fill/order; all schema compatibility and migration tests pass. |
| Dependencies | H4 complete; H6 evidence available. Must precede or be part of H7. |

### Fill and partial-execution policy

ManualTrade proceeds to the existing append-only Fill ledger only through a
separate human recording step. Fill then rebuilds PositionSnapshot. A partial
fill, cancellation or changed Position closes the old confirmation scope; any
residual REDUCE/EXIT requires a new H4 decision. An EXIT may never be treated
as complete until effective Fill reduces the actual Position to zero.

### Authority separation

The migration must enforce exactly one route authority: OPEN/ADD references an
approved complete-account Risk decision; REDUCE/EXIT references a permitted
risk-reducing decision and its recheck. Neither route calls a Broker adapter.

## 13. H7 — Durable Holding, Exit and exception state

### Implementation contract

| Concern | Contract |
|---|---|
| Business goal | Give Holding/Reduce/Exit assessments a durable, restart-safe lifecycle instead of one-shot review output. |
| Input Artifacts | Active Thesis/Position, H5 health, H6 composite evidence, H4/H4.5 decision/manual-intent references and Holding/Exit configuration. |
| Output Artifact | Immutable Holding/Reduce/Exit assessment, schedule, exception/acknowledgement events and latest projection. |
| State machine | `SCHEDULED → DUE → ASSESSED → NO_ACTION | REDUCE_PENDING | EXIT_PENDING | BLOCKED | DATA_INSUFFICIENT → ACKNOWLEDGED/SUPERSEDED`; `NO_ACTION ≠ HOLD`. |
| Idempotency key | Position book/version + assessment due time + evidence/config hashes. |
| Persistence tables | Assessment events, schedules, action intents, exceptions, acknowledgements, command ledger and rebuildable latest-state projection. |
| Transaction boundary | CAS current projection and atomically append assessment/event/command; H4.5 manual intent remains its own transaction boundary. |
| Failure recovery | Resume due work from receipts; rebuild projection from events; stale CAS retries with fresh Position; preserve blocked/exception history. |
| Audit evidence | Every transition's actor/time/reason, Position/Thesis/evidence/config hashes, linked H4/H4.5 IDs and acknowledgement. |
| Tests | Duplicate/concurrent commands, restart/rebuild, stale Position/Thesis, T+1/suspension/limits, blocked exit, ack, tamper, migration up/down. |
| Completion condition | Durable lifecycle survives restart and every reduce/exit transition has traceable evidence without broker mutation. |
| Dependencies | H5, H6 and completed H4.5 bridge; feeds H8. |

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

### Implementation contract

| Concern | Contract |
|---|---|
| Business goal | Run the complete research/decision/position lifecycle on schedule with reproducible receipts, simulated/manual outcomes and operator-visible failures. |
| Input Artifacts | Frozen daily/provider data, governed model definitions, H5/H6 evidence, H7 queues, manual/synthetic Fill sources and Shadow configuration. |
| Output Artifact | ShadowRun journal, stage receipts, frozen decisions, next-day outcomes, position/exit simulation, daily report, metrics and alerts. |
| State machine | `SCHEDULED → ACQUIRING → EVIDENCE_FROZEN → DECIDED → OUTCOME_PENDING → REVIEWED`; each stage can be `RETRYABLE`, `DATA_BLOCKED`, `FAILED` or `ACK_REQUIRED`. |
| Idempotency key | Trading session + run profile + code/config revision; each stage also binds input receipt hashes. |
| Persistence tables | `shadow_runs`, stage receipts, retry/deadline records, acknowledgements, alerts, report index and correlation IDs. |
| Transaction boundary | One journal transaction per stage/receipt; immutable file publication uses staging plus verified receipt, never a cross-store fiction. |
| Failure recovery | Lease/fencing or single-owner discipline, bounded retry, orphan receipt recovery, resume from last verified stage and manual reconciliation queue. |
| Audit evidence | Scheduler trigger, stage inputs/outputs/hashes, attempts, latency, structured failure, operator acknowledgement, outcome and report. |
| Tests | Duplicate scheduling, crash at each stage, retry/deadline, data freeze, deterministic replay, next-day outcome, position/exit simulation, alerts and no Broker mutation. |
| Completion condition | Engineering admission criteria pass and a separate sustained-run evidence period is collected; code completion alone is not Shadow operations evidence. |
| Dependencies | H4–H7, runtime governance integration and controlled provider windows; produces samples for H9. |

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

### Implementation contract

| Concern | Contract |
|---|---|
| Business goal | Establish formal, leakage-controlled evidence for incremental value, calibration, costs, capacity, risk and failure conditions. |
| Input Artifacts | Qualified PIT Universe/theme mapping, adjusted/delisting-aware prices, frozen model/config definitions, H8 run/outcome sample, benchmarks and cost policy. |
| Output Artifact | Frozen validation protocol, dataset partitions, walk-forward runs, trade/path metrics, stability/failure report and immutable negative results. |
| State machine | `DRAFT → FROZEN → TRAINING → VALIDATING → OOS_LOCKED → EVALUATED → ACCEPTED | REJECTED | INCONCLUSIVE`; access is budgeted and append-only. |
| Idempotency key | Protocol ID/version + dataset manifest hash + split/walk-forward identity + code revision. |
| Persistence tables | Validation protocols, dataset manifests, access ledger, run receipts, metric bundles, comparison/decision records; large data remains immutable artifacts. |
| Transaction boundary | Freeze protocol before data access; atomically record each access/run receipt and result identity; promotion is a separate governed transaction. |
| Failure recovery | Resume deterministic folds, preserve all partial/negative results, reject post-freeze mutation and require new protocol identity for semantic change. |
| Audit evidence | PIT lineage, adjustment/delisting rules, train/validation/OOS dates, access history, costs/slippage/T+1/limits/capacity, benchmark and all metrics. |
| Tests | Synthetic leakage traps, delisting/adjustment, purge/embargo, walk-forward, costs/slippage, limit non-fill, T+1, capacity/risk, MFE/MAE, hit/return/drawdown and stability. |
| Completion condition | Qualified locked OOS runs meet a predeclared protocol or are honestly rejected/inconclusive; infrastructure completion alone does not establish Alpha. |
| Dependencies | Qualified data and H8 artifacts; follows H5–H8 and cannot grant trading authority. |

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
