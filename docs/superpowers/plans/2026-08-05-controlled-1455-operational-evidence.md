# Controlled 14:55 Operational Evidence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver WP-DATA-OPS-01 as one controlled, recoverable 14:55 canonical operation with longitudinal evidence and offline replay while Entry and trading authority remain blocked.

**Architecture:** A new `application/controlled_operation` parent journal orchestrates existing immutable child authorities. Feature execution is hardened first because static preparation and the decision-window SLA depend on its performance and crash recovery. Static daily authority and Candidate-only intraday authority remain separate and compose through CandidateFeatureView V2.

**Tech Stack:** Python 3.12, frozen dataclasses, Decimal, SQLite WAL, immutable JSON/Parquet packages, urllib single-Symbol Tencent adapter, bounded `ThreadPoolExecutor`, pytest, ruff, mypy, uv.

## Global Constraints

- Base must contain `68f91295a888e54b83334c7d7afcaab580961244`.
- Preserve `.idea/modules.xml` and all unrelated changes exactly.
- Use injected aware clocks and the exact TradingCalendar; no hidden wall-clock authority.
- Never use data received after DecisionTime or retry after hard cutoff.
- Never substitute daily VWAP, another Symbol, zero, or a different Provider for missing minute evidence.
- New production path emits Signal V3 only and retains V1/V2 Readers for compatibility.
- PathForecast sample authority remains unavailable and Entry remains blocked.
- No Opportunity, Thesis approval, ManualTrade, Fill, order or Broker call.
- All artifacts are content-addressed, atomically published, exact-file-set verified and replayable.
- Operational authority remains exploratory; formal PIT, formal OOS Alpha, Shadow, Production and Trading Authority remain false.

---

### Task 1: Baseline, call-chain Gap Map and profile evidence

**Files:**
- Create: `docs/audit/WP-DATA-OPS-01-Profile-Before.json`
- Modify: `docs/superpowers/specs/2026-08-05-controlled-1455-operational-evidence-design.md`

**Interfaces:**
- Consumes: PR #36 merge commit and frozen benchmark fixture.
- Produces: cProfile rows `{function, calls, total_seconds, cumulative_seconds, percentage}` plus observed elapsed, memory, bytes and file count.

- [ ] Run the exact baseline commands and record PASS/FAIL without changing source.
- [ ] Profile only Feature Encoding V2 for 100 Symbols, 250 daily sessions, 48 five-minute Bars and seven definitions.
- [ ] Export the top cumulative functions and the required named operations to the audit JSON.
- [ ] Confirm the profile, not inference, determines optimization scope.

### Task 2: Prepared Feature execution and batch settlement

**Files:**
- Modify: `src/market_regime_alpha/features/materialization_v2.py`
- Modify: `src/market_regime_alpha/features/materialization_run.py`
- Test: `tests/features/test_materialization_runner_v2.py`
- Test: `tests/features/test_feature_benchmark.py`
- Modify: `scripts/benchmark_feature_materialization.py`

**Interfaces:**
- Produces: `PreparedFeatureExecutionContext.build(verified_dataset, feature_set, selected_symbols)`.
- Produces: `SQLiteFeatureMaterializationRunRepository.claim_batch(run_id, limit, lease_duration)`.
- Consumes: each settlement token as `(claim_token, claim_epoch, task_version)`.

- [ ] Add a failing test that patches `PreparedFeatureExecutionContext.build` and asserts one call for a multi-batch run.
- [ ] Add failing serial/parallel and per-task failure tests over a batch larger than worker count.
- [ ] Implement the frozen context with verified membership, bars index, definitions, configurations, task plan, input scopes and lineage.
- [ ] Refactor computation to consume the prepared context and claimed task scope without Dataset traversal.
- [ ] Claim tasks in bounded batches, publish independent artifacts, and settle every task independently.
- [ ] Verify existing logical hashes and V1/V2 compatibility are unchanged.
- [ ] Run `uv run pytest -q tests/features/test_materialization_runner_v2.py tests/features/test_feature_benchmark.py`.

### Task 3: migration 013, leases and fencing epoch

**Files:**
- Create: `src/market_regime_alpha/features/migrations/013_feature_materialization_run_hardening_up.sql`
- Create: `src/market_regime_alpha/features/migrations/013_feature_materialization_run_hardening_down.sql`
- Modify: `src/market_regime_alpha/features/materialization_run.py`
- Create: `tests/features/test_migration_013.py`
- Modify: `tests/features/test_materialization_runner_v2.py`

**Interfaces:**
- `ClaimedFeatureMaterializationTask` carries `claim_token: str`, `claim_epoch: int`, `task_version: int`, `attempt_number: int`.
- `heartbeat(claim, lease_duration) -> ClaimedFeatureMaterializationTask` uses CAS.
- `recover_expired(run_id, observed_at) -> tuple[str, ...]` settles attempts as `LEASE_EXPIRED` and makes tasks retryable.

- [ ] Add migration tests for CHECK, JSON validity, SHA256, FKs, unique indexes and query indexes.
- [ ] Add trigger tests proving event/receipt append-only, settled-attempt immutability, completed-task immutability, run command immutability and no run/task deletion.
- [ ] Rebuild migration-012 tables without rewriting migration 012 and preserve valid legacy rows.
- [ ] Inject the repository Clock and remove direct `datetime.now()` from repository transitions.
- [ ] Increment `claim_epoch` monotonically and fence settlement by token, epoch and task version.
- [ ] Recover expired leases automatically on resume, emit `LEASE_EXPIRED`, and reject takeover of active leases.
- [ ] Add crash tests at claimed, artifact-published, task-settled, bundle-published and pre-receipt seams.
- [ ] Run `uv run pytest -q tests/features` and `uv run mypy`.

### Task 4: Operational Universe and decision-window policy

**Files:**
- Create: `src/market_regime_alpha/universe/operational.py`
- Modify: `src/market_regime_alpha/universe/__init__.py`
- Create: `src/market_regime_alpha/application/controlled_operation/policy.py`
- Create: `tests/universe/test_operational_universe.py`
- Create: `tests/application/controlled_operation/test_policy.py`

**Interfaces:**
- `OperationalUniverseArtifact.create(decision_date, effective_at, available_at, records, source_references, limitations)`.
- `DecisionTimeOperationPolicy.assess(clock_time, calendar, decision_date) -> DecisionWindowAssessment`.

- [ ] Test 100 and 300 Symbol controlled universes, per-Symbol reasons, exclusions, source references and explicit formal-PIT ceiling.
- [ ] Test that the Smoke pool is neither imported nor defaulted by the controlled builder.
- [ ] Implement exact-file-set atomic publisher and Reader for the Universe artifact.
- [ ] Test trading day, weekend, holiday, temporary closure, early invocation, window, late data, cutoff and Calendar hash conflict.
- [ ] Implement content-addressed default Asia/Shanghai policy with configurable times and injected Clock.

### Task 5: Static bundle, Candidate overlay and CandidateFeatureView V2

**Files:**
- Create: `src/market_regime_alpha/features/operational_overlay.py`
- Modify: `src/market_regime_alpha/features/technical/catalog.py`
- Modify: `src/market_regime_alpha/features/__init__.py`
- Create: `src/market_regime_alpha/signals/candidate_view_v2.py`
- Modify: `src/market_regime_alpha/signals/input_v3.py`
- Modify: `src/market_regime_alpha/signals/__init__.py`
- Create: `tests/features/test_operational_overlay.py`
- Create: `tests/signals/test_candidate_feature_view_v2.py`

**Interfaces:**
- `static_technical_feature_set(effective_from) -> FeatureSetConfiguration` contains daily-only families.
- `intraday_overlay_feature_set(effective_from) -> FeatureSetConfiguration` contains intraday price action and session VWAP.
- `StaticUniverseFeatureBundle.create(universe, daily_dataset, feature_bundle, receipt)`.
- `CandidateIntradayFeatureOverlay.create(candidate_set, static_bundle, minute_dataset, feature_bundle, calendar)`.
- `CandidateFeatureViewV2.create(candidate_set, static_bundle, overlay)`.

- [ ] Test immutable separation, exact Candidate scope, dataset/source/calendar/DecisionTime mismatch and no copied static values.
- [ ] Implement atomic publishers/Readers and semantic replay for all three artifacts.
- [ ] Extend `SignalInputAssemblerV3` through an explicit V1/V2 view dispatch; daily factors resolve from static references and VWAP from overlay references.
- [ ] Test five-factor completion and missing VWAP producing `DATA_INSUFFICIENT` without imputation.

### Task 6: Candidate minute batch acquisition

**Files:**
- Create: `src/market_regime_alpha/market_data/minute_batch.py`
- Modify: `src/market_regime_alpha/market_data/__init__.py`
- Create: `tests/market_data/test_minute_batch.py`

**Interfaces:**
- `CandidateMinuteAcquisitionCommand` binds CandidateSet, DecisionTime, Provider profile, concurrency, timeout, retry policy, cutoff and output root.
- `CandidateMinuteAcquisitionRunner.run(command, client_factory, clock) -> MinuteAcquisitionCoverageArtifact`.

- [ ] Test 1/5/10 Symbols, partial/all failure, timeout, 429, 5xx, malformed JSON, HTML, content-type mismatch valid JSON, wrong Symbol, cumulative decrease, duplicate/missing minute, cancellation and retry cutoff.
- [ ] Implement bounded concurrency and finite deadline-aware retry with one immutable attempt per request.
- [ ] Reject late responses as inputs while retaining late attempt evidence.
- [ ] Publish the content-addressed coverage artifact with latency distribution, reason codes and raw-source references.

### Task 7: migration 014 and parent operation journal

**Files:**
- Create: `src/market_regime_alpha/application/controlled_operation/__init__.py`
- Create: `src/market_regime_alpha/application/controlled_operation/contracts.py`
- Create: `src/market_regime_alpha/application/controlled_operation/repository.py`
- Create: `src/market_regime_alpha/application/controlled_operation/sqlite_repository.py`
- Create: `src/market_regime_alpha/application/controlled_operation/migrations/014_controlled_decision_time_operation_up.sql`
- Create: `src/market_regime_alpha/application/controlled_operation/migrations/014_controlled_decision_time_operation_down.sql`
- Create: `tests/application/controlled_operation/test_migration_014.py`
- Create: `tests/application/controlled_operation/test_journal.py`

**Interfaces:**
- Run/stage/attempt/receipt/event contracts use immutable command hashes, ordered stage enum, CAS version, lease and monotonic claim epoch.
- Child references are `(child_kind, child_run_id, receipt_hash, locator)` and remain references only.

- [ ] Test schema checks, indexes, FKs, triggers and safe isolated down migration.
- [ ] Test create/get, command conflict, claim, heartbeat, expiry, stale-writer rejection, stage completion immutability, append-only events and one-snapshot history.
- [ ] Implement repository transactions with `BEGIN IMMEDIATE` and injected Clock.

### Task 8: Controlled runner and operation package

**Files:**
- Create: `src/market_regime_alpha/application/controlled_operation/runner.py`
- Create: `src/market_regime_alpha/application/controlled_operation/package.py`
- Create: `src/market_regime_alpha/application/controlled_operation/composition.py`
- Create: `tests/application/controlled_operation/test_runner.py`
- Create: `tests/application/controlled_operation/test_package.py`

**Interfaces:**
- `prepare(command)`, `run_decision_window(run_id)`, and `resume(run_id)` return a journal-bound snapshot.
- `ControlledOperationalEvidencePackage` binds every required artifact/reference and fixed safety booleans.

- [ ] Implement stage handlers that load verified child inputs, call domain services, publish child artifacts, then settle only references.
- [ ] Ensure Platform Research creates CandidateSet and no test helper injects it into the runner.
- [ ] Ensure new runner imports neither `application.daily_loop` nor legacy daily Feature/Signal modules.
- [ ] Publish package through staging, exact file set, SHA256 index, Reader verification and atomic rename.
- [ ] Add crash/recovery tests at every child publication boundary and prove no Order/ManualTrade/Fill/Broker call.

### Task 9: T+1 outcome and longitudinal index

**Files:**
- Create: `src/market_regime_alpha/application/controlled_operation/outcome.py`
- Create: `src/market_regime_alpha/application/controlled_operation/longitudinal.py`
- Create: `tests/application/controlled_operation/test_outcome.py`
- Create: `tests/application/controlled_operation/test_longitudinal.py`

**Interfaces:**
- `TradeHorizonOutcomeObservation.create(...)` produces fact-only return/MFE/MAE and completeness fields.
- `LongitudinalOperationalIndex.append(package, outcomes)` and `.rebuild(package_roots)` are append-only and idempotent.

- [ ] Test next open, 10:30, morning high/low, close, suspension, limit state, missing data and AvailabilityTime.
- [ ] Test package settlement cannot mutate the pending package and creates one new settled package.
- [ ] Test date/model/configuration queries, missing trading-day detection, duplicate rejection and deterministic rebuild.

### Task 10: Full offline replay and CLI

**Files:**
- Create: `src/market_regime_alpha/application/controlled_operation/replay.py`
- Create: `src/market_regime_alpha/cli/_controlled_operation.py`
- Create: `src/market_regime_alpha/cli/prepare_controlled_operation.py`
- Create: `src/market_regime_alpha/cli/run_decision_window.py`
- Create: `src/market_regime_alpha/cli/resume_controlled_operation.py`
- Create: `src/market_regime_alpha/cli/settle_controlled_operation.py`
- Create: `src/market_regime_alpha/cli/replay_controlled_operation.py`
- Create: `src/market_regime_alpha/cli/report_controlled_operation.py`
- Create: `tests/application/controlled_operation/test_replay.py`
- Create: `tests/application/controlled_operation/test_cli.py`

**Interfaces:**
- `replay_controlled_operation(package_path) -> ControlledReplayReport` compares ordered semantic and receipt fingerprints.
- CLI JSON always includes safety ceiling fields and stable `ControlledOperationExitCode`.

- [ ] Recompute the full chain offline with recorded timestamps and no network/current Clock/Broker/execution repositories.
- [ ] Test replay divergence and V1/V2 Reader compatibility.
- [ ] Implement six module CLIs with stable JSON and exit-code mapping for every specified state.

### Task 11: Integration fixture and performance evidence

**Files:**
- Create: `tests/application/controlled_operation/fixtures/README.md`
- Create: `tests/application/controlled_operation/test_full_integration.py`
- Modify: `scripts/benchmark_feature_materialization.py`
- Create: `scripts/benchmark_controlled_operation.py`
- Create: `docs/audit/WP-DATA-OPS-01-Benchmark.json`

**Interfaces:**
- Frozen fixture covers 100-Symbol Universe, five selected Candidates, five Tencent responses and T+1 settlement sources.

- [ ] Run full fixture from verified sources through `SETTLED` and stable replay.
- [ ] Assert Signal V3 only, Path `DATA_INSUFFICIENT`, Entry blocked, and absence of Opportunity/ManualTrade/Fill/Broker effects.
- [ ] Measure 100-Symbol cold Feature run, 300-Symbol research run and Candidate normalization/overlay/Signal components.
- [ ] Record actual elapsed, peak memory, output bytes and file counts; mark unmet thresholds accurately.

### Task 12: Documentation, gates, review and delivery

**Files:**
- Create: `docs/architecture/15-Controlled-1455-Decision-Time-Operation.md`
- Create: `docs/architecture/decisions/ADR-0015-Controlled-Operation-Authority.md`
- Modify: `docs/status/Current-State.md`
- Modify: `docs/status/Capability-Matrix.md`
- Modify: `docs/status/Gap-Register.md`
- Create: `docs/audit/WP-DATA-OPS-01-Delivery.md`
- Modify: `docs/README.md`

**Interfaces:**
- Delivery evidence binds the exact tested HEAD and distinguishes engineering fixture from operational observation.

- [ ] Update architecture, migration, authority ceiling, legacy compatibility and remaining-gap documentation.
- [ ] Run every focused and full quality command from the user directive and record PASS/FAIL/NOT_RUN/BLOCKED.
- [ ] Run code review, fix findings, inspect staged scope, and run `git diff --cached --check`.
- [ ] Commit dependency-coherent checkpoints, push the branch, open/update a Draft PR, and wait for remote CI.
- [ ] Report base, branch, final HEAD, commits, PR, CI, working tree, actual call chain, performance, package/replay/outcome evidence, migration details and only the four allowed next work packages.
