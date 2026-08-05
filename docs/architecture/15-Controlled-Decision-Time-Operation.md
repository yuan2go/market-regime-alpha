# Controlled 14:55 Decision-Time Operation

> **Status:** CURRENT_ARCHITECTURE
> **Authority:** WP-DATA-OPS-01 application and evidence architecture
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-05
> **Related Documents:** 13-Canonical-Market-Data-and-Feature-Spine.md, 14-Canonical-Signal-Authority-and-Operational-Feature-Handoff.md, decisions/ADR-007-Controlled-Decision-Time-Operation.md
> **Code Evidence:** `application/controlled_operation/**`, `features/materialization_run.py`, `market_data/minute_batch.py`

## 1. Authority boundary

`ControlledDecisionTimeOperationRunner` is an application-layer orchestrator.
It composes existing Readers, repositories and domain handlers and does not
become a second data, Feature, Signal, Forecast, Entry or execution authority.
It is a controlled single-day research operation, not H8 recurring scheduling,
H9 validation, Shadow qualification, production or trading authority.

The executable call chain is:

```text
runner.prepare
  -> load_controlled_trading_calendar
  -> load_operational_universe
  -> load_verified_public_source_stage_artifact
  -> normalize_public_history_stage
  -> FeatureMaterializationRunner.run
  -> StaticUniverseFeatureBundle.create

runner.run_decision_window
  -> PlatformResearchRunner.run_controlled
  -> discover_controlled_candidates
  -> CandidateMinuteBatchAcquirer.run
  -> RawMinuteSourceReader.read
  -> normalize_tencent_minute_source
  -> minute_normalizations_to_dataset
  -> FeatureMaterializationRunner.run
  -> CandidateIntradayFeatureOverlay.create
  -> SignalStageHandler.run_controlled_v2
  -> PathForecastStageHandler.run_controlled
  -> EntryAssessmentStageHandler.run_controlled
  -> ControlledCanonicalLifecycleRunReceipt.create/publish
  -> ControlledOperationalEvidencePackage.create

runner.settle
  -> load_outcome_settlement_source_archive
  -> load_verified_market_data_dataset
  -> build_trade_horizon_outcome_evidence
  -> ControlledOperationalEvidencePackage.create(SETTLED)
  -> SQLiteLongitudinalOperationalIndex.append
```

The runner never invokes `DailyLoopRunner`, the Legacy daily Feature path,
Signal V1/V2, in-memory `ModelRegistry`, Opportunity creation, ManualTrade,
Fill, order or Broker code.

## 2. Trading Calendar, Operational Universe and policy

`OperationalUniverseArtifact` accounts for every included and excluded symbol,
including listing, ST, suspension, liquidity, history, source and eligibility
evidence. The supported controlled scope is 100–300 A-share symbols. The old
20-symbol pool remains historical Smoke input and is not the controlled default.
Increasing cardinality does not create PIT authority; the initial ceiling is
`CONTROLLED_EXPLORATORY_UNIVERSE` plus `FORMAL_PIT_NOT_ESTABLISHED`.

`DecisionTimeOperationPolicy` is content-addressed and defaults to
Asia/Shanghai 14:55, static-ready 14:50, minute-fetch 14:54 and hard cutoff
14:56. UTC instants are derived from the policy. An injectable Clock and an
explicit `TradingCalendarArtifact` govern live execution. Non-trading days,
missing or conflicting calendars, early/late runs, sources received after the
DecisionTime and retry after cutoff fail closed. Replay uses recorded semantic
times and never the current wall clock.

Window admission uses the immutable `STATIC_FEATURES` stage Receipt time, not
the presence of a bundle alone. A Receipt after 14:50, after the observation
time, or outside the declared decision date is `DATA_BLOCKED`; a run beginning
after 14:55:00 is `DEADLINE_MISSED`. The 14:56 cutoff remains the cancellation
boundary for work that was admitted before DecisionTime.

## 3. Static Feature and Intraday Overlay architecture

`PRE_DECISION_STATIC_FEATURES` materializes completed daily history before the
decision window. `StaticUniverseFeatureBundle` binds the Operational Universe,
daily Dataset, SourceManifest, Feature Set, code revision and Run Receipt. It is
immutable after publication.

Only selected Candidates enter minute acquisition. The resulting
`CandidateIntradayFeatureOverlay` binds CandidateSet, minute Dataset, Trading
Calendar and intraday Feature Bundle. It contains Candidate-only references and
does not copy or replace static Features. `CandidateFeatureViewV2` composes
static and intraday references. Signal V3 obtains all five factors from this V2
View. A missing Candidate minute source leaves VWAP/intraday inputs missing and
produces `DATA_INSUFFICIENT`; there is no daily VWAP fallback, cross-symbol
substitution or zero fill.

## 4. Candidate minute batch acquisition

`CandidateMinuteAcquisitionCommand` freezes CandidateSet, DecisionTime,
Provider profile, concurrency, timeout, retry and cutoff. The batch acquirer
uses bounded concurrency, one immutable attempt history per symbol, finite
pre-cutoff retries and cancellation at the global deadline. HTTP 429/5xx,
timeouts, DNS failures, malformed payloads and validation failures remain
symbol-specific. `MinuteAcquisitionCoverageArtifact` preserves succeeded,
failed and late scope; failed Candidates are never silently removed. All-source
failure publishes a `DATA_BLOCKED` or `DEADLINE_MISSED` operation package.

## 5. Journals, migrations and crash recovery

Migration 013 hardens Feature Runs without rewriting migration 012. It adds
status/JSON/hash checks, foreign keys, uniqueness and query indexes; append-only
Event/Receipt triggers; immutable completed Task/settled Attempt/Run command
rules; and lease columns. A UUID claim remains diagnostic identity while the
monotonic `claim_epoch`, `task_version` and claim ID jointly fence settlement.
Expired work records `LEASE_EXPIRED`, settles the old Attempt explicitly and is
reclaimed at the next epoch. A prepared execution context verifies and indexes
the Dataset once per Run; planning, batch computation, artifact publication and
Task settlement remain separate.

Migration 014 adds the parent `DecisionTimeOperationRun`, Stage, Attempt,
Receipt, Event, artifact-reference and child-run-reference tables. Completed
Stages and Events/Receipts are immutable. Stage claims use leases, monotonic
epochs and CAS. The parent records child Receipt hashes and never copies child
domain state. Signal, Path and Entry publish a separately readable
`ControlledCanonicalLifecycleRunReceipt`; the parent references its actual Run
ID and Receipt hash, never a locally composed placeholder. Migration 015 adds a
rebuildable append-only longitudinal index.

Crash tests cover failure before Feature publication, after publication before
repository settlement, after Task completion before Bundle, and after Bundle
before Receipt. Resume reuses matching content-addressed output, rejects stale
workers and never creates two conflicting Receipts. A completed parent Stage is
accepted only when recomputed input, output, child-run and reason references
exactly equal its immutable Receipt. Frozen input directories are compared by
exact relative file set and SHA-256 before reuse.

## 6. Operational Evidence Package and longitudinal archive

`ControlledOperationalEvidencePackage` has an exact file set, SHA-256 index,
atomic publication and strict Reader. It binds command, policy, Calendar,
Universe, daily source archive/manifest/Dataset, static Features, controlled
research, CandidateSet, minute coverage/Dataset, overlay, Candidate View V2,
Signal V3, PathForecast, Entry blocker, stage Receipts, code/config/model
manifests, the real Canonical child-run Receipt, coverage, latency, deadline and
authority ceiling.

Allowed states are `OPERATIONAL_EXPLORATORY_ARCHIVE`, `DATA_BLOCKED`,
`DEADLINE_MISSED`, `OUTCOME_PENDING` and `SETTLED`. A settled package is a new
immutable package that explicitly supersedes the pending package; it never
modifies history.

`SQLiteLongitudinalOperationalIndex` stores package references and discovery
fields only. It is append-only, range/model queryable, detects configuration
switches and missing trading dates, and can rebuild from packages. It stores no
unverified profitability conclusion.

## 7. T+1 Outcome Evidence

Settlement accepts an exact-file, SHA-verified raw Outcome Source Archive, its
subsequent SourceManifest and the canonical Dataset covering Candidate
09:30–10:30 minute Bars plus daily close evidence. The archive requires every
SourceManifest raw hash to equal the archived bytes. Offline replay reconstructs
the canonical Outcome Dataset from the recorded bar-source payload before
recomputing factual observations.
`TradeHorizonOutcomeObservation` records reference price, next open, 10:30,
morning high/low, close, gross return, MFE, MAE, suspension, limits,
completeness, feasibility observations, availability and source lineage.
These are factual observations for future H9 work, not a Label, Alpha result,
win-rate claim, model approval or Entry authorization.

## 8. Full offline replay and CLI

`replay_controlled_operation` reads only immutable local packages. It rebuilds
daily Dataset semantics from the daily source archive, recomputes both Feature
Bundles, controlled research/CandidateSet, minute normalization/Dataset,
Overlay, Candidate View V2, Signal V3, PathForecast, Entry blocker, Canonical
child-run Receipt and optional raw-source-derived Outcome, then compares package
and Receipt fingerprints. It performs no
network, current-time, Broker, ManualTrade, Fill, approval or model-promotion
action.

The operational modules are:

```text
python -m market_regime_alpha.cli.prepare_controlled_operation
python -m market_regime_alpha.cli.run_decision_window
python -m market_regime_alpha.cli.resume_controlled_operation
python -m market_regime_alpha.cli.settle_controlled_operation
python -m market_regime_alpha.cli.replay_controlled_operation
python -m market_regime_alpha.cli.report_controlled_operation
```

Every command emits JSON with explicit no-order/no-Broker/no-Fill and
validation ceilings. Stable exits distinguish arguments, non-trading day,
too-early, deadline, data block, partial Provider failure, conflict, rejected
resume, replay divergence and repository failure.

## 9. Observed engineering performance

The frozen offline synthetic benchmark on 2026-08-05 produced:

| Measurement | Result |
|---|---:|
| Historical V2 cold baseline | 584.626303 s |
| Exact pre-fix profiled run | 234.789293 s |
| Final 100-symbol V2 cold run | 57.986357 s |
| Final 100-symbol tracemalloc peak | 46,604,431 B |
| Final 100-symbol output / files | 16,121,164 B / 2,326 |
| 300-static/10-Candidate two-stage V2 research run | 161.981241 s |
| 300-static/10-Candidate tracemalloc peak | 125,667,134 B |
| 300-static/10-Candidate output / files | 40,019,491 B / 4,908 |
| 100-Universe/5-Candidate decision increment | 0.139 s |

The 100-symbol target passed and the Candidate increment passed. The 300-symbol
number is measurement only, not an absolute CI gate. All values are engineering
Fixtures; no run in this work package was observed at real wall-clock 14:55 and
no Provider was qualified.

## 10. Authority statement

```text
Engineering verified: YES, subject to the cited local gates
Operationally observed at real 14:55: NO
Provider qualified: NO
Formal PIT: NO
Formal OOS Alpha: NO
Shadow Ready: NO
Production: NO
Trading Authority: NO
Entry: BLOCKED
PathForecast Sample Authority: UNAVAILABLE
```
