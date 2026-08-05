# Controlled 14:55 Operational Evidence Design

> **Status:** CURRENT_SPECIFICATION
> **Authority:** Approved WP-DATA-OPS-01 design derived from the 2026-08-05 user directive
> **Owner:** Market Regime Alpha maintainers
> **Base:** `68f91295a888e54b83334c7d7afcaab580961244`
> **Branch:** `feat/controlled-1455-operational-evidence`

## Objective and evidence ceiling

Build one recoverable, content-addressed, A-share trading-session-aware operation that prepares static daily evidence before the decision window, acquires only Candidate minute evidence inside the window, produces Signal V3, preserves PathForecast `DATA_INSUFFICIENT`, blocks Entry, archives T+1 observations, and supports exact offline replay.

The operation remains `OPERATIONAL_EXPLORATORY_ARCHIVE`. It does not establish formal PIT, formal OOS Alpha, Shadow readiness, production readiness, trading authority, Opportunity, ManualTrade, Fill, order, or Broker behavior.

## Explored approaches

### Chosen: parent operation journal over existing child authorities

Add `application/controlled_operation` as an Application-layer orchestrator. It owns only window policy, stage progression, child references, evidence-package publication, settlement, and replay. Market source archives, canonical datasets, Feature Runs, Platform Research, Signal V3, PathForecast, and Entry assessment remain authoritative in their current bounded contexts.

This approach preserves the repository's authority hierarchy, gives each child run one durable identity, and allows crashes between child publication and parent settlement to recover by Reader verification.

### Rejected: expand `DailyLoopRunner`

The old runner has historical Phase-D semantics: a fixed Smoke policy, legacy daily Feature materialization, B0/B1 publication through an in-memory `ModelRegistry`, recommendation projection, and Phase-D outcome review. Extending it would blur Smoke compatibility with controlled canonical operation and would retain the exact coupling this work removes.

### Rejected: make Canonical Lifecycle the parent scheduler

The Canonical Lifecycle is an H4-H6 decision/position lifecycle with a fixed ordered stage graph. Adding source acquisition, pre-window preparation, deadline cancellation, and T+1 archive settlement would change its historical semantics and mix operational scheduling with decision authority.

## Code-level Gap Map

| Area | Current executable fact | Required change |
|---|---|---|
| Daily operation | `DailyLoopRunner` defaults to `smoke_pool_policy_v1`, old daily Features, B0/B1 and in-memory `ModelRegistry` | retain as historical/exploratory compatibility; new runner never calls it |
| Feature performance | `FeatureMaterializationRunner` claims 1-8 tasks, then `_compute_artifacts` rebuilds verified Dataset membership and `bars_by_scope` for every batch | build one immutable `PreparedFeatureExecutionContext`; batch claims/computation/publication/settlement |
| Feature crash recovery | migration 012 has unconstrained status text, random token only, `claimed_at`, and optional stale recovery driven by wall clock | migration 013, injected Clock, lease/heartbeat, monotonic `claim_epoch`, task version fencing, automatic expired-lease recovery |
| Minute source | `TencentMinuteSourceClient` is correct single-Symbol raw-first authority | add bounded batch planner around it; do not weaken the single-Symbol client |
| Universe | Smoke and historical PIT contracts exist; no controlled 100-300 Symbol artifact | add immutable `OperationalUniverseArtifact` with per-Symbol inclusion/exclusion evidence and explicit PIT ceiling |
| Features at 14:55 | one combined bundle computes daily and minute families across the whole universe | publish immutable static daily bundle before the window; publish Candidate-only intraday overlay later |
| Signal input | `CandidateFeatureView` V1 references one combined Feature Bundle | retain V1; add V2 composing static references and overlay references without copying values |
| Research | H6/Platform V2 already creates `CandidateSet`; current H6 input is tied to Phase-D packages | controlled operation invokes the existing Platform runner from exact recorded operational inputs and binds the static bundle as an operation prerequisite; it does not create CandidateSet by hand |
| Path/Entry | V3 Signal and unavailable sample provider already fail closed; Entry handler blocks | reuse unchanged authority and record their artifacts/reason codes |
| Parent recovery | no decision-window parent journal | migration 014 with run/stage/attempt/receipt/event tables, CAS, lease and fencing |
| Evidence/archive | no unified package or longitudinal index | exact-file-set package plus append-only SQLite index and rebuild |
| Outcome | Phase-D MR1 10:30 review and Fill-derived outcome exist, but no raw controlled horizon observation | add fact-only `TradeHorizonOutcomeObservation`; do not emit H9 labels |

## Component design

### Feature execution and migration 013

`PreparedFeatureExecutionContext` verifies Dataset and Feature Set identity once and stores immutable membership, definitions/configurations, task plans, task-to-input scopes, bars indexed by `(symbol, timeframe)`, source lineage, and the verified physical Reader root. The runner claims a configurable batch, computes only claimed tasks, publishes each content-addressed artifact, and settles each task with `(claim_token, claim_epoch, task_version)`.

Migration 013 rebuilds migration-012 tables with CHECK, JSON, hash, unique, foreign-key and lease-shape constraints. Events and receipts are append-only; completed tasks, settled attempts, run command identity, and runs are immutable. Resume atomically expires overdue attempts, emits `LEASE_EXPIRED`, makes the task retryable, and increments the next claim epoch.

### Two-stage Feature authority

`StaticUniverseFeatureBundle` binds the controlled Universe, daily Dataset, decision date, daily-only Feature Set, SourceManifest, code revision, configuration and Feature Run receipt. It is immutable after publication.

`CandidateIntradayFeatureOverlay` binds the selected CandidateSet, Static bundle, Candidate-only minute Dataset, TradingCalendar, intraday Feature Set and artifact references. It contains no static values and cannot expand Candidate scope.

`CandidateFeatureViewV2` is a reference-only composition of the static bundle and overlay. The V3 assembler resolves daily factors from the static bundle and VWAP from the overlay. Missing overlay data remains missing and makes the corresponding Signal `DATA_INSUFFICIENT`.

### Operational Universe and policy

`OperationalUniverseArtifact` contains one record for every considered Symbol, including membership source, listing/ST/suspension status, liquidity, history coverage, inclusion/exclusion reasons, availability, source references and eligibility. The default controlled profile requires 100-300 Symbols and is `CONTROLLED_EXPLORATORY_UNIVERSE` / `FORMAL_PIT_NOT_ESTABLISHED`. It never imports the Smoke policy as a default.

`DecisionTimeOperationPolicy` is content-addressed and uses `Asia/Shanghai`, default decision time 14:55, static deadline 14:50, minute start 14:54, and hard cutoff 14:56. An injected Clock and explicit TradingCalendar decide every transition. Provider responses received after DecisionTime cannot enter Signal; work and retries stop at hard cutoff. Replay uses recorded timestamps only.

### Minute batch

`CandidateMinuteAcquisitionRunner` schedules one `MinuteSourceRequest` per Candidate with bounded concurrency, per-request timeout, finite retry policy and a common hard deadline. Each network attempt is archived independently. A coverage artifact records attempted/succeeded/failed/late Symbols, latency distribution, reasons, attempts and raw source references. Cancellation and late responses are evidence, never inputs.

### Parent journal and operation runner

Migration 014 adds `controlled_operation_run`, `controlled_operation_stage`, `controlled_operation_attempt`, `controlled_operation_receipt`, `controlled_operation_event`, and `longitudinal_operational_index`. The parent references child IDs and receipt hashes; it does not copy child state. Completed stages and events are immutable. Claim epoch, lease and task version reject stale workers.

`ControlledDecisionTimeOperationRunner.prepare` executes Calendar/Universe/Daily Source/Daily Dataset/Static Feature stages. `run_decision_window` executes Research/Candidate/minute acquisition/intraday Dataset/overlay/Signal/Path/Entry/package stages. `settle` archives T+1 sources and fact-only outcomes, publishes a settled package, and appends the index. `resume` uses Readers to recover an already-published child before re-executing it.

### Package, settlement and replay

`ControlledOperationalEvidencePackage` stores canonical references, exact SHA256 file inventory, latency and coverage, deadline status and the fixed authority ceiling. Publication is staging plus Reader validation plus atomic rename.

`TradeHorizonOutcomeObservation` binds Symbol, CandidateSet, Signal snapshot, PathForecast, operation package, decision reference, T+1 minute source, 10:30 price, morning high/low, close, gross return, MFE, MAE, data completeness and execution-feasibility observations. It makes no model-quality conclusion.

Offline replay reads the package, reconstructs every semantic artifact from archived inputs, invokes no network/current clock/Broker/execution repository, and compares ordered receipt fingerprints. V1 Readers remain unchanged.

## Failure semantics

- Non-trading day, missing or conflicting Calendar, early run, deadline miss, and data block have distinct statuses and CLI exit codes.
- Partial minute failure does not erase failed Candidates. Successful Candidates may proceed; failed Candidates receive missing intraday factors and `DATA_INSUFFICIENT` Signals.
- No daily VWAP substitution, zero imputation, other-Symbol substitution, post-DecisionTime response, or post-cutoff retry is allowed.
- A crash after an immutable child publication is recovered by recomputing its identity and loading it. Conflicting bytes or hashes fail closed.
- Package status is limited to `OPERATIONAL_EXPLORATORY_ARCHIVE`, `DATA_BLOCKED`, `DEADLINE_MISSED`, `OUTCOME_PENDING`, or `SETTLED`.

## Verification strategy

Focused tests cover migration triggers and schema authority, prepared-context cardinality, serial/parallel hashes, all five Feature crash seams, decision-window states, Provider response failures, static/overlay mismatch, Signal missingness, journal CAS/lease/fencing, package atomicity, outcome settlement, index rebuild and full no-network replay.

Performance evidence uses the frozen 100-Symbol/250-session/48-five-minute/7-definition fixture and a 300-Symbol research benchmark. Absolute timing is recorded from the actual environment, not used as a fragile universal CI gate. The 100-Symbol cold run target is at most 60 seconds; Candidate normalization + overlay + Signal target is at most 30 seconds.

## Scope exclusions

No Force Ratio, Chan, Tuishen, Buy Point Quality, Sell Pressure, Certainty, Attention, H7, H8 scheduler/control plane, H9 validation, Path calibration, Entry opening, Opportunity automation, Thesis approval, PostgreSQL, RBAC, frontend, Broker, order, ManualTrade or Fill is implemented.
