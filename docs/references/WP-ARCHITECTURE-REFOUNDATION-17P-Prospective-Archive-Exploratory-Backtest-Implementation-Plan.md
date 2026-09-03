# WP-17P Archive and Exploratory Backtest Implementation Plan

> **Status:** CURRENT_STATUS
> **Authority:** Execution order for the approved WP-17P canonical design; never business or empirical evidence Authority
> **Baseline:** `origin/main@f67a4f34761516dab65825c38c4e81019f8c2dd1`
> **Owner:** Market Regime Alpha maintainers
> **Frozen:** 2026-09-03

> **For agentic workers:** REQUIRED SUB-SKILL: Use `executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build two permanently separate real-data archive lanes, an explicit dual-clock retrospective simulation seam, a minimal immutable Model path, and reproducible canonical baseline/challenger backtests without raising the Formal evidence ceiling.

**Architecture:** Market owns archive roots, slices, Capture observations and seals while the existing Runtime owns leases/fences. Research & Qualification owns only retrospective simulation lineage, exploratory backtest predeclaration, Model training/version and Evaluation extensions; existing Dataset, Candidate, Decision Support, Outcome, Portfolio/Risk and Evaluation rows remain the business truth. Ordinary PIT continues to validate `known_at <= DecisionTime`; retrospective event selection is carried by concrete bindings with a real archive-seal knowledge cutoff.

**Tech Stack:** Python 3.12, PostgreSQL 16, psycopg 3, immutable content-addressed local Artifacts, BaoStock, NumPy/pandas where appropriate outside transactions, pytest, Ruff, mypy, setuptools build.

## Global Constraints

- Baseline is `origin/main@f67a4f34761516dab65825c38c4e81019f8c2dd1` in branch `agent/wp-17p-prospective-archive` and its isolated worktree.
- Keep `RETROSPECTIVE_BACKFILL` and `PROSPECTIVE_CONTEMPORANEOUS` relationally distinct forever.
- Retrospective `knowledge_cutoff` is PostgreSQL archive-seal time; `simulated_event_cutoff` is historical event time; evidence class is always `EXPLORATORY_RETROSPECTIVE`.
- Ordinary PIT, Formal PIT/Dataset, LOCKED_OOS and PROSPECTIVE admission reject retrospective bindings.
- Preserve the WP-15 BaoStock rejection and WP-16 external-evidence blocker unchanged.
- Reuse the canonical Dataset → Candidate → Decision Support → Outcome → Experiment/Evaluation chain; no DataFrame/report business truth.
- Real operational PostgreSQL/Artifact storage is isolated from disposable qualification storage and is never recreated or test-torn down.
- Provider/network/filesystem byte I/O occurs outside short PostgreSQL business transactions.
- Use concrete relational FKs, PostgreSQL authoritative time, Decimal boundaries, deterministic hashes, exact idempotency, bounded retry, exact unknown-commit recovery and fence-first writes.
- No Formal Provider/PIT/OOS/Prospective/Alpha/Model qualification or Production claim may be emitted by WP-17P.

---

### Task 1: Market archive domain

**Files:**
- Create: `src/market_regime_alpha/market/domain/archive.py`
- Modify: `src/market_regime_alpha/market/domain/__init__.py`
- Test: `tests/refoundation/market/test_archive_domain.py`

**Interfaces:**
- Produces: `ArchiveLane`, `ArchiveStatus`, `SliceStatus`, `ObservationRelation`, `ObservationTimeliness`, `SealDisposition`, `MarketArchive`, `MarketArchiveSlice`, `ArchiveCaptureObservation`, `MarketArchiveSeal`, and `RetrospectiveSimulationClock`.
- Consumes: existing shared UUID/hash/time validation conventions.

- [ ] Write public-domain tests proving the two-lane vocabulary, prospective start guard, contiguous slice roster/hash, terminal-only seal, immutable evidence ceiling, dual-clock ordering, and explicit partial dispositions.
- [ ] Run `python -m pytest -q tests/refoundation/market/test_archive_domain.py`; expect import/behavior failures.
- [ ] Implement frozen dataclasses and pure validators. `RetrospectiveSimulationClock` must enforce:

```python
if evidence_class is not ArchiveEvidenceClass.EXPLORATORY_RETROSPECTIVE:
    raise MarketInvariantError("retrospective evidence class is fixed")
if simulated_event_cutoff >= knowledge_cutoff:
    raise MarketInvariantError("simulated event cutoff must precede knowledge cutoff")
```

- [ ] Re-run the test file and expect PASS.
- [ ] Commit `feat(market): define archive evidence lanes`.

### Task 2: Archive PostgreSQL Authority and command seam

**Files:**
- Create: `src/market_regime_alpha/market/application/archive.py`
- Create: `src/market_regime_alpha/market/ports/archive.py`
- Create: `src/market_regime_alpha/infrastructure/postgres/repositories/market_archive.py`
- Create: `src/market_regime_alpha/infrastructure/postgres/archive_uow.py`
- Modify: `src/market_regime_alpha/infrastructure/postgres/migrations/001_baseline.sql`
- Modify: `src/market_regime_alpha/infrastructure/postgres/schema.py`
- Modify: package `__init__.py` exports
- Test: `tests/refoundation/market/test_archive_postgres.py`
- Test: `tests/refoundation/market/test_archive_schema_specification.py`

**Interfaces:**
- Produces: `StartMarketArchive`, `RecordArchiveCaptureObservation`, `RecordArchiveSliceGap`, `SealRetrospectiveArchive`, `ArchiveUnitOfWorkProvider`, `ArchiveReadPort`.
- Consumes: existing Runtime claim/finalization, `data_capture`, `source_gap`, `artifact`, Provider/Product identities.

- [ ] Write PostgreSQL tests for PostgreSQL-time start/seal, complete contiguous slices, concrete Capture/Gap FKs, global observation ordinal, no backfill in prospective lane, prospective request start guard, terminal reconciliation, idempotent replay, changed request rejection, stale-fence zero-write and immutable rows.
- [ ] Run the two focused files against the disposable PostgreSQL fixture; expect missing-table/import failures.
- [ ] Extend `001_baseline.sql` with archive root/slice/observation/gap/seal tables, FK-leading indexes and deferred reconciliation triggers. Root success must be impossible while `slice_count/hash` differs from the full child roster.
- [ ] Implement the narrow repository/UoW and command handlers using the existing receipt/audit/fence support. The start API is:

```python
class StartMarketArchive:
    def execute(self, request: StartMarketArchiveRequest) -> MarketArchiveResult: ...
```

- [ ] Implement exact receipt probe/replay and bounded PostgreSQL transient retry without retrying changed business payloads.
- [ ] Re-run focused domain/PostgreSQL/schema tests and expect PASS.
- [ ] Commit `feat(market): persist immutable archive operations`.

### Task 3: Real BaoStock capture products and exact normalization

**Files:**
- Modify: `src/market_regime_alpha/infrastructure/providers/baostock.py`
- Create: `src/market_regime_alpha/infrastructure/providers/baostock_archive.py`
- Create: `src/market_regime_alpha/market/application/archive_execution.py`
- Create: `src/market_regime_alpha/market/ports/archive_provider.py`
- Test: `tests/refoundation/market/test_baostock_archive_provider.py`
- Test: `tests/refoundation/market/test_archive_execution.py`

**Interfaces:**
- Produces: typed BaoStock security-master, calendar/membership, daily-bar and five-minute-bar requests returning exact raw bytes plus parsed metadata; `ExecuteArchiveSlice` orchestrates I/O outside transactions.
- Consumes: `LocalArtifactStore`, existing `RecordCapture`/normalization commands and Task 2 archive commands.

- [ ] Write boundary tests for exact raw-byte hashing, provider rejection, malformed rows, timeout/retry classification, missing fields, `adjustflag=3`, timezone/session parsing, UNKNOWN historical availability/finality and secret-free errors.
- [ ] Run focused tests and expect failures at the new interfaces.
- [ ] Implement deterministic request serialization and preserve the exact UTF-8 JSON byte envelope returned by the adapter; the envelope includes Product method, Provider field order, raw string values, provider error code/message and no invented timestamps.
- [ ] Implement security-master/calendar/index-membership/daily/5m adapters only for actual BaoStock methods; unsupported 1m and unavailable historical semantics become typed gaps.
- [ ] Implement `ExecuteArchiveSlice` in this order: Provider request, Artifact publication/verification, Capture command, normalization command, archive observation command. No transaction spans Provider or Artifact byte I/O.
- [ ] Re-run focused tests and expect PASS.
- [ ] Commit `feat(market): execute real BaoStock archive slices`.

### Task 4: Resource-safe operations and inspection

**Files:**
- Create: `src/market_regime_alpha/market/application/archive_operations.py`
- Create: `src/market_regime_alpha/infrastructure/postgres/queries/market_archive.py`
- Create: `src/market_regime_alpha/interfaces/archive.py`
- Modify: `src/market_regime_alpha/interfaces/cli.py`
- Test: `tests/refoundation/market/test_archive_operations.py`
- Test: `tests/refoundation/test_archive_cli.py`

**Interfaces:**
- Produces: `ArchiveResourcePreflight`, `ArchiveOperations`, `ArchiveInspection`, and `mra archive start|resume|inspect|retry|gap-report|revision-report|daily-health`.
- Consumes: Tasks 2–3 applications and existing target composition.

- [ ] Write tests that reject operational commands against known disposable/test DB names, prevent destructive recreate, clean-stop below reserved disk, retain raw Artifacts, resume exact pending slices, and render expected/actual/gaps/revisions without mutation.
- [ ] Run focused tests and expect interface failures.
- [ ] Implement a resource preflight returning immutable measured free bytes, reserved bytes, maximum archive bytes and `PROCEED`/`PARTIAL_WITH_RESOURCE_LIMIT`; never delete evidence.
- [ ] Implement operator commands as composition-root calls only; parsing code must not import PostgreSQL repositories.
- [ ] Re-run tests and expect PASS.
- [ ] Commit `feat(market): add resource-safe archive operations`.

### Task 5: Dual-clock archive-seal read port and retrospective Dataset

**Files:**
- Create: `src/market_regime_alpha/market/ports/archive_queries.py`
- Create: `src/market_regime_alpha/infrastructure/postgres/queries/retrospective_archive.py`
- Create: `src/market_regime_alpha/research_qualification/application/retrospective_datasets.py`
- Create: `src/market_regime_alpha/research_qualification/ports/retrospective.py`
- Modify: `src/market_regime_alpha/infrastructure/postgres/research_uow.py`
- Modify: `src/market_regime_alpha/infrastructure/postgres/repositories/research_definitions.py`
- Modify: `src/market_regime_alpha/infrastructure/postgres/migrations/001_baseline.sql`
- Test: `tests/refoundation/research_qualification/test_retrospective_dataset.py`

**Interfaces:**
- Produces: `ArchiveSealSourceReadPort`, `RegisterRetrospectiveDataset`, and concrete `retrospective_dataset_binding`.
- Consumes: existing `RegisterDataset`, exact Dataset sources, `MarketArchiveSeal`, `RetrospectiveSimulationClock`.

- [ ] Write tests proving source event time ≤ simulated cutoff, actual source known time ≤ seal cutoff, source Capture belongs to seal, wrong/prospective lane rejection, ordinary Dataset PIT invariants unchanged, and Formal Dataset rejection.
- [ ] Run focused test; expect failures.
- [ ] Add the concrete binding table and indexes, then implement the typed read port without current/latest queries.
- [ ] Implement `RegisterRetrospectiveDataset` to validate exact sources and atomically create the ordinary Dataset plus binding in the Research UoW.
- [ ] Re-run focused plus existing Dataset/Formal PIT tests and expect PASS.
- [ ] Commit `feat(research): bind dual-clock retrospective datasets`.

### Task 6: Exploratory backtest predeclaration

**Files:**
- Create: `src/market_regime_alpha/research_qualification/domain/exploratory_backtest.py`
- Create: `src/market_regime_alpha/research_qualification/application/exploratory_backtest.py`
- Create: `src/market_regime_alpha/research_qualification/ports/exploratory_backtest_uow.py`
- Create: `src/market_regime_alpha/infrastructure/postgres/exploratory_backtest_uow.py`
- Create: `src/market_regime_alpha/infrastructure/postgres/repositories/exploratory_backtests.py`
- Modify: `src/market_regime_alpha/infrastructure/postgres/migrations/001_baseline.sql`
- Test: `tests/refoundation/research_qualification/test_exploratory_backtest_domain.py`
- Test: `tests/refoundation/research_qualification/test_exploratory_backtest_postgres.py`

**Interfaces:**
- Produces: `RegisterExploratoryBacktestRun`, ordered `RULE_BASELINE`/`MODEL_CHALLENGER` arms, chronological fold/session roster, and exact root/child verifier.
- Consumes: archive seal, Target, policy roots, EvaluationProtocol and code/config Artifacts.

- [ ] Write tests for fixed evidence ceiling, exact Target, two-arm shared-protocol rule, chronological non-overlap, trading-session purge/embargo, contiguous order, complete hashes, no late binding, concurrency/replay and changed-roster rejection.
- [ ] Run focused tests and expect failures.
- [ ] Implement domain/root/child value objects and the atomic PostgreSQL registration UoW with deferred count/hash closure.
- [ ] Implement a read-only verifier returning `matched` and typed mismatches.
- [ ] Re-run tests and expect PASS.
- [ ] Commit `feat(research): freeze exploratory backtest protocol`.

### Task 7: Retrospective DecisionRun and arm/fold propagation

**Files:**
- Create: `src/market_regime_alpha/decision_support/application/retrospective.py`
- Create: `src/market_regime_alpha/decision_support/ports/retrospective.py`
- Create: `src/market_regime_alpha/infrastructure/postgres/queries/retrospective_decision_inputs.py`
- Modify: `src/market_regime_alpha/infrastructure/postgres/decision_uow.py`
- Modify: `src/market_regime_alpha/infrastructure/postgres/repositories/decision_runs.py`
- Modify: `src/market_regime_alpha/infrastructure/postgres/migrations/001_baseline.sql`
- Modify: Partition population-scope query/repository files
- Test: `tests/refoundation/decision_support/test_retrospective_decision_run.py`
- Test: `tests/refoundation/research_qualification/test_retrospective_partition_postgres.py`

**Interfaces:**
- Produces: `OpenRetrospectiveDecisionRun`, `retrospective_decision_run_binding`, and arm/fold-aware database-derived Partition roster.
- Consumes: ordinary CandidateSet/DecisionRun commands, historical simulation session, archive seal and exploratory backtest member.

- [ ] Write tests proving ordinary `OpenDecisionRun` is unchanged, retrospective run decision time equals real knowledge cutoff, exact historical reference resolution, actual source known time retained, no Formal/LOCKED_OOS/PROSPECTIVE use, and baseline/challenger Partition rosters cannot mix.
- [ ] Run focused tests and expect failures.
- [ ] Add concrete binding schema and a narrow retrospective reference resolver requiring exact archive/backtest/session identity.
- [ ] Implement the command and Partition population-scope extension without accepting caller member IDs.
- [ ] Re-run focused plus existing DecisionRun/Partition tests and expect PASS.
- [ ] Commit `feat(decision): open typed retrospective decision runs`.

### Task 8: Minimal Model training and immutable version

**Files:**
- Create: `src/market_regime_alpha/research_qualification/domain/research_model.py`
- Create: `src/market_regime_alpha/research_qualification/application/research_models.py`
- Create: `src/market_regime_alpha/research_qualification/ports/model_uow.py`
- Create: `src/market_regime_alpha/research_qualification/ports/model_inputs.py`
- Create: `src/market_regime_alpha/infrastructure/postgres/model_uow.py`
- Create: `src/market_regime_alpha/infrastructure/postgres/repositories/research_models.py`
- Create: `src/market_regime_alpha/infrastructure/postgres/queries/model_training_inputs.py`
- Create: `src/market_regime_alpha/research_qualification/application/deterministic_linear.py`
- Modify: `src/market_regime_alpha/infrastructure/postgres/migrations/001_baseline.sql`
- Test: `tests/refoundation/research_qualification/test_model_domain.py`
- Test: `tests/refoundation/research_qualification/test_model_postgres.py`
- Test: `tests/refoundation/research_qualification/test_deterministic_linear.py`

**Interfaces:**
- Produces: `RegisterModel`, `OpenModelTrainingRun`, `FitDeterministicLinearModel`, `RegisterModelVersion`; full database-derived sample roster.
- Consumes: completed FIT Evaluation, exact Evaluation observations/metric observations, Dataset cells and Artifact store.

- [ ] Write tests for terminal FIT-only inputs, complete sample roster including not-estimable members, no caller performance, deterministic seed/coefficient bytes, immutable Artifact, same-request replay and changed Artifact/request rejection.
- [ ] Run focused tests and expect failures.
- [ ] Add Model/root/training/sample/version DDL with concrete Evaluation/Dataset/Outcome/Artifact FKs and deferred roster reconciliation.
- [ ] Implement training-input query and command handlers. Fit occurs outside the business transaction and serializes sorted-key canonical JSON coefficients/preprocessing metadata.
- [ ] Implement a deterministic regularized linear estimator using NumPy with explicit float-to-Decimal serialization and fixed BLAS-independent solve tolerances recorded in config.
- [ ] Re-run focused tests and expect PASS.
- [ ] Commit `feat(research): register immutable exploratory model versions`.

### Task 9: Model-backed Forecast binding with generation safety

**Files:**
- Create: `src/market_regime_alpha/decision_support/domain/model_forecast.py`
- Create: `src/market_regime_alpha/decision_support/application/model_forecast.py`
- Create: `src/market_regime_alpha/decision_support/ports/model_forecast.py`
- Modify: `src/market_regime_alpha/infrastructure/postgres/inference_uow.py`
- Modify: `src/market_regime_alpha/infrastructure/postgres/repositories/decision_inference.py`
- Modify: `src/market_regime_alpha/infrastructure/postgres/migrations/001_baseline.sql`
- Test: `tests/refoundation/decision_support/test_model_forecast.py`

**Interfaces:**
- Produces: `ProduceModelForecast`, concrete `forecast_model_binding`.
- Consumes: exact ModelVersion read port, ordinary Forecast/Estimate Authority and later backtest arm/fold binding.

- [ ] Write tests for exact model Artifact verification, feature vector lineage, uncalibrated output, later-fold/generation requirement, same-fold/same-generation rejection and rule Forecast independence.
- [ ] Run focused test and expect failures.
- [ ] Add the concrete FK table and implement inference outside the transaction followed by one short Forecast/binding transaction.
- [ ] Re-run focused plus existing inference tests and expect PASS.
- [ ] Commit `feat(decision): bind model versions to later forecasts`.

### Task 10: Canonical backtest Evaluation metrics

**Files:**
- Modify: `src/market_regime_alpha/research_qualification/domain/evaluation.py`
- Modify: `src/market_regime_alpha/research_qualification/application/evaluations.py`
- Modify: `src/market_regime_alpha/research_qualification/ports/evaluation_inputs.py`
- Modify: `src/market_regime_alpha/infrastructure/postgres/queries/research_partition_inputs.py`
- Modify: `src/market_regime_alpha/infrastructure/postgres/repositories/research_evaluation_inputs.py`
- Modify: `src/market_regime_alpha/infrastructure/postgres/repositories/research_evaluations.py`
- Modify: `src/market_regime_alpha/infrastructure/postgres/migrations/001_baseline.sql`
- Test: `tests/refoundation/research_qualification/test_backtest_evaluation_domain.py`
- Test: `tests/refoundation/research_qualification/test_backtest_evaluation_postgres.py`

**Interfaces:**
- Produces: typed Decision-source observation bindings and reducers for coverage, RankIC, gross/net, MFE/MAE/hit, turnover/drawdown/exposure and Portfolio/Risk rejection.
- Consumes: exact OutcomeMetric, ForecastEstimate, Candidate, Signal, PortfolioLine and RiskDecision rows.

- [ ] Write independent worked-example reducer tests including ties, missing/not-estimable members, assumed costs, zero denominator and complete metric×member rosters.
- [ ] Run focused tests and expect failures.
- [ ] Extend metric source/reducer vocabulary with frozen compatibility checks and concrete source-binding child tables; no polymorphic `(kind,id)` or JSON owner.
- [ ] Extend acquisition/reconciliation so every Partition member has an explicit state for every declared source, and completion requires the full Cartesian roster.
- [ ] Re-run focused plus WP-11 Evaluation tests and expect PASS.
- [ ] Commit `feat(research): evaluate canonical exploratory backtests`.

### Task 11: Composition, verifier and operator orchestration

**Files:**
- Modify: `src/market_regime_alpha/bootstrap.py`
- Modify: `src/market_regime_alpha/interfaces/cli.py`
- Create: `src/market_regime_alpha/research_qualification/application/exploratory_runner.py`
- Create: `src/market_regime_alpha/infrastructure/postgres/queries/wp17p_verification.py`
- Test: `tests/refoundation/test_wp17p_bootstrap.py`
- Test: `tests/refoundation/test_wp17p_reconciliation_postgres.py`

**Interfaces:**
- Produces: fully composed archive/retrospective/backtest/model/evaluation services, `mra exploratory-backtest run|inspect`, and read-only `WP17PVerifier`.
- Consumes: Tasks 1–10 public commands.

- [ ] Write tests that bootstrap the sole target composition and invoke every new command without hand-assembled Infrastructure.
- [ ] Write reconciliation tests that detect altered roster/hash/clock/source/Model/Forecast/metric lineage and return zero mismatch for canonical state without mutation/Provider/latest/label reconstruction.
- [ ] Implement composition and the bounded orchestration service; it calls owner commands and records their identities but does not write their tables directly.
- [ ] Re-run focused tests and expect PASS.
- [ ] Commit `feat: compose WP-17P archive and backtest operations`.

### Task 12: Failure, concurrency, schema and plan qualification tests

**Files:**
- Create: `tests/refoundation/wp17p/test_concurrency_postgres.py`
- Create: `tests/refoundation/wp17p/test_failure_recovery_postgres.py`
- Create: `tests/refoundation/wp17p/test_query_plans_postgres.py`
- Modify: `tests/refoundation/research_qualification/test_architecture.py`
- Modify: `tests/refoundation/market/test_schema_specification.py`

**Interfaces:**
- Produces: executable engineering proof for races, rollback/recovery, import boundaries and representative plans.

- [ ] Add real PostgreSQL races for identical/changed archive starts, slice observations, seals, backtest registrations, Model runs/versions and model Forecast bindings.
- [ ] Add serialization/deadlock/transient/unknown-commit/stale-fence/mid-roster/Artifact-failure campaigns and assert no partial archive, Model or metric roster.
- [ ] Add `EXPLAIN (ANALYZE, BUFFERS)` coverage for pending slice acquisition, observation ordinal, seal reconciliation, archive-source resolution, training roster and metric Cartesian roster.
- [ ] Run the three focused files and architecture/schema tests; expect PASS with no asserted optimizer node shape.
- [ ] Commit `test: qualify WP-17P concurrency and recovery`.

### Task 13: Freeze exact implementation and run engineering gates

**Files:**
- No source change after the implementation checkpoint unless all affected gates are rerun.

- [ ] Run `uv sync --frozen --extra dev --extra postgres`.
- [ ] Run all WP-17P focused tests, `tests/refoundation`, `tests/platform`, `tests/persistence/postgres`, and full `python -m pytest -q`.
- [ ] Run `python -m ruff check .`, `python -m mypy`, `python -m build`, docs/navigation, architecture/import and `git diff --check`.
- [ ] Create a fresh disposable PostgreSQL 16 database; run clean bootstrap/verify, guarded exact-OID recreate/verify, concurrency/failure/recovery/replay and representative plans.
- [ ] Commit any correction, record the new exact SHA and rerun every affected gate; freeze only a SHA with all required PASS results.

### Task 14: Execute the real isolated pilot

**Files:**
- Operational PostgreSQL and Artifact root are external to the repository; no secrets or local absolute paths are committed.

- [ ] Create a new non-test operational database and external Artifact root named from the frozen implementation SHA; bootstrap once and verify without recreate.
- [ ] Record resource preflight, start the retrospective archive for `2026-01-01` through the execution trading date, execute bounded BaoStock slices, retain all gaps, and seal COMPLETE or explicit partial disposition.
- [ ] Start the prospective archive using PostgreSQL time and execute the currently available real scheduled slot/post-close smoke; record future Decision-critical schedule without inventing future captures.
- [ ] Register the exact exploratory protocol; materialize chronological sessions through canonical owners; run the rule baseline and complete its Evaluation.
- [ ] Open FIT ModelTrainingRun, train/register the deterministic ModelVersion, run it only on later folds, and complete challenger Evaluation.
- [ ] Run Artifact, archive, dual-clock, Model and Evaluation reconciliation; expect `matched=true`, `mismatch_count=0` or stop with a typed exact blocker.

### Task 15: Immutable verification, status truth, PR and merge

**Files:**
- Create: `docs/references/WP-ARCHITECTURE-REFOUNDATION-17P-Prospective-Archive-Exploratory-Backtest-Verification.md`
- Modify: `docs/status/Current-State.md`
- Modify: `docs/status/Roadmap.md`
- Modify: `docs/status/Capability-Matrix.md`
- Modify: `docs/architecture/Authority-Map.md`
- Modify: `docs/README.md`

- [ ] Record baseline/final SHA, source/schema/test identities, operational isolation, archive start, Product, Artifact counts/hashes, retrospective coverage/gaps, prospective observations, Dataset/ModelVersion/backtest/Evaluation identities, exact metrics, reconciliation and every validation command as PASS/FAIL/NOT_RUN/BLOCKED.
- [ ] Report engineering, retrospective, prospective accumulation, model/backtest and Formal evidence ceilings separately; Remote CI disabled is `BLOCKED_BY_REPOSITORY_CONFIGURATION / NOT_RUN`.
- [ ] Run docs links/tests, full static/build checks affected by final docs, and `git diff --check`.
- [ ] Commit immutable Verification and status/navigation truth; confirm clean worktree.
- [ ] Fetch `origin/main`, compare its new commits with the baseline and rebase/requalify if the verified tree changes.
- [ ] Push the branch, create/update the PR with exact validation metadata, merge only if all required local gates and repository policy permit, fetch merged main and record the exact merged SHA.
