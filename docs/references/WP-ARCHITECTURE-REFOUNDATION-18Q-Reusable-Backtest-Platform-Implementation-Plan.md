# WP-18Q Reusable Backtest Platform Implementation Plan

> **Status:** ROADMAP
> **Authority:** Dependency-ordered implementation plan only; never business or evidence Authority
> **Baseline:** `origin/main@e45d232cb0c4891a75d55a65ed83398640160893`
> **Design:** [WP-18Q Design](WP-ARCHITECTURE-REFOUNDATION-18Q-Reusable-Backtest-Platform-Design.md)
> **Owner:** Market Regime Alpha maintainers
> **Frozen:** 2026-09-04
> **Decision:** APPROVED / IMPLEMENTATION_ACTIVE

## Working rules

- Use test-driven development: add one failing behavioral/constraint test,
  prove the intended failure, implement the smallest closure, then refactor.
- Keep Track A and Track C P0. Check the PostgreSQL clock and pending
  prospective windows before starting any repeatable long backtest operation.
- Use only permanent bounded-context Applications and UoWs for writes.
- Preserve every historical row/hash/Artifact and the old executor until the
  hard-cut gate passes.
- Make one dependency-coherent checkpoint commit at a time.
- Never touch `.idea/modules.xml`.

## Checkpoint 0 — Baseline and design freeze

- [x] Fetch and record latest `origin/main`.
- [x] Create an isolated worktree/branch from exact merged main.
- [x] Freeze the approved WP-18Q design.
- [x] Freeze this dependency-ordered plan.
- [ ] Run documentation links and diff checks.
- [ ] Commit the design/plan checkpoint without implementation changes.

## Checkpoint 1 — Generic specification domain

Expected files:

- `src/market_regime_alpha/research_qualification/domain/backtest.py`
- `src/market_regime_alpha/research_qualification/domain/backtest_compatibility.py`
- `src/market_regime_alpha/research_qualification/domain/exploratory_backtest.py`
- `tests/refoundation/research_qualification/test_backtest_specification_domain.py`
- `tests/refoundation/research_qualification/test_backtest_historical_decoder.py`

Tasks:

- [ ] Add red tests for ordered arbitrary arm rosters and orthogonal arm fields.
- [ ] Add red tests for rolling/expanding overlapping FIT membership.
- [ ] Add red tests for distinct-session versus binding counts.
- [ ] Add red tests for explicit acyclic FoldDependency and Model requirements.
- [ ] Add red tests proving a missing current manifest is not legacy.
- [ ] Implement `BacktestSpecification`, arm/fold/dependency/cost/evaluation
  contracts, and `FrozenBacktestRun` projection.
- [ ] Implement a private exact historical compatibility manifest/decoder.
- [ ] Preserve the historical hash implementation only inside that decoder.
- [ ] Remove generation/WP dispatch from the permanent domain surface.

Focused gate:

```bash
uv run python -m pytest -q \
  tests/refoundation/research_qualification/test_backtest_specification_domain.py \
  tests/refoundation/research_qualification/test_backtest_historical_decoder.py \
  tests/refoundation/research_qualification/test_exploratory_backtest_domain.py \
  tests/refoundation/research_qualification/test_wp18_walk_forward_domain.py
uv run python -m ruff check src/market_regime_alpha/research_qualification tests/refoundation/research_qualification
uv run python -m mypy
git diff --check
```

## Checkpoint 2 — Relational specification Authority

Expected files:

- `src/market_regime_alpha/infrastructure/postgres/migrations/001_baseline.sql`
- `src/market_regime_alpha/research_qualification/ports/backtest_uow.py`
- `src/market_regime_alpha/research_qualification/application/backtests.py`
- `src/market_regime_alpha/infrastructure/postgres/repositories/backtests.py`
- `src/market_regime_alpha/infrastructure/postgres/backtest_uow.py`
- `tests/refoundation/research_qualification/test_backtest_schema_specification.py`
- `tests/refoundation/research_qualification/test_backtest_postgres.py`

Tasks:

- [ ] Add schema specification tests for the one-to-one current companion and
  concrete child FKs.
- [ ] Add PostgreSQL red tests for root-last closure, arbitrary arms, overlap,
  FoldDependency cycles, and exact parent hashes.
- [ ] Add current specification, sample, arm, dependency, arm-fold, model
  requirement, effective cost, and evaluation requirement relations.
- [ ] Evolve old arm/fold constraints without updating historical rows.
- [ ] Implement typed predeclaration UoW and reload/reconciliation.
- [ ] Implement read-only validate/plan and mutating predeclare Applications.
- [ ] Prove idempotency, changed-request rejection, concurrency, failure
  atomicity, stale fence, and unknown-commit replay.

Focused gate:

```bash
uv run python -m pytest -q \
  tests/refoundation/research_qualification/test_backtest_schema_specification.py \
  tests/refoundation/research_qualification/test_backtest_postgres.py
uv run python -m pytest -q tests/refoundation/test_schema_epoch.py
uv run python -m ruff check .
uv run python -m mypy
git diff --check
```

## Checkpoint 3 — Historical equivalence

Expected files:

- `src/market_regime_alpha/research_qualification/application/backtest_replay.py`
- `src/market_regime_alpha/research_qualification/ports/backtest_queries.py`
- `src/market_regime_alpha/infrastructure/postgres/queries/backtest_replay.py`
- `tests/refoundation/research_qualification/test_backtest_wp17p_equivalence_postgres.py`
- `tests/refoundation/research_qualification/test_backtest_wp18_definition_equivalence.py`

Tasks:

- [ ] Freeze exact approved historical run/definition tuples.
- [ ] Prove WP-17P root/child/downstream/Artifact equivalence through the
  generic decoder and verifier.
- [ ] Prove the historical verification is a zero-write no-op with pre/post
  database and Artifact checksums.
- [ ] Prove WP-18 four-arm multi-fold definition/specification equivalence.
- [ ] Label WP-18 accurately as definition-only equivalence.
- [ ] Reject unknown legacy-shaped and incomplete current rows.

## Checkpoint 4 — Runtime-backed multi-fold executor

Expected files:

- `src/market_regime_alpha/research_qualification/application/backtest_execution.py`
- `src/market_regime_alpha/research_qualification/ports/backtest_execution.py`
- `src/market_regime_alpha/infrastructure/postgres/queries/backtest_execution.py`
- `tests/refoundation/research_qualification/test_backtest_execution_planner.py`
- `tests/refoundation/research_qualification/test_backtest_execution_postgres.py`

Tasks:

- [ ] Add red tests for expected-action reconciliation states.
- [ ] Add red tests for orthogonal ExecutionState/ResearchState projections.
- [ ] Add red tests for completed identity reuse and no mutable cursor.
- [ ] Compile exact arm/fold/session work into existing Runtime Runs/Steps.
- [ ] Bind actual Runtime Runs to exact Backtest execution cells.
- [ ] Delegate Dataset/Candidate/Decision/Outcome calls to canonical owners.
- [ ] Implement retryable recovery and integrity-error fail-closed behavior.
- [ ] Prove two workers cannot execute the same fenced cell.

## Checkpoint 5 — Model extension and leakage closure

Expected files:

- `src/market_regime_alpha/research_qualification/ports/model_execution.py`
- `src/market_regime_alpha/research_qualification/infrastructure/` or the
  existing deterministic model implementation package
- `src/market_regime_alpha/research_qualification/application/research_models.py`
- `src/market_regime_alpha/research_qualification/domain/research_models.py`
- `tests/refoundation/research_qualification/test_model_execution_contracts.py`
- `tests/refoundation/research_qualification/test_model_training_leakage_postgres.py`

Tasks:

- [ ] Add `ModelTrainer` and `ModelPredictor` ports.
- [ ] Move deterministic ridge behind a concrete adapter.
- [ ] Freeze typed hyperparameter, runtime, lockfile, dependency, implementation,
  cutoff, sample, and fitted Artifact rosters.
- [ ] Obtain training cutoff only from PostgreSQL.
- [ ] Enforce Outcome known-time, generation, purge, embargo, Feature, Target,
  and Model lineage.
- [ ] Bind actual TrainingRun/ModelVersion only after successful FIT.
- [ ] Prove rule paths never require ModelVersion.

## Checkpoint 6 — Standard Evaluation and diagnosis

Expected files:

- `src/market_regime_alpha/research_qualification/domain/evaluation.py`
- `src/market_regime_alpha/research_qualification/application/evaluations.py`
- `src/market_regime_alpha/infrastructure/postgres/repositories/research_evaluations.py`
- `src/market_regime_alpha/research_qualification/domain/alpha_diagnosis.py`
- `tests/refoundation/research_qualification/test_backtest_formulae.py`
- `tests/refoundation/research_qualification/test_backtest_evaluation_postgres.py`

Tasks:

- [ ] Freeze formula code/version and typed parameter relations.
- [ ] Add Decimal golden tests for every standard metric and boundary.
- [ ] Prove Top/Bottom membership comes from DecisionTime ranking.
- [ ] Add complete Data/Candidate/Context/Signal/Forecast/Portfolio/Risk/
  Economics/Stability source closures.
- [ ] Persist null plus typed reason for every not-estimable result.
- [ ] Create fold, aggregate, time, and Context-slice Evaluation runs.
- [ ] Complete deterministic AlphaFunnelDiagnosis over Evaluation only.

## Checkpoint 7 — Report, comparison, and operator surface

Expected files:

- `src/market_regime_alpha/research_qualification/application/backtest_reports.py`
- `src/market_regime_alpha/research_qualification/ports/backtest_reports.py`
- `src/market_regime_alpha/infrastructure/postgres/queries/backtest_reports.py`
- `src/market_regime_alpha/interfaces/cli/backtest.py`
- `src/market_regime_alpha/interfaces/cli/main.py`
- `tests/refoundation/interfaces/test_backtest_cli.py`
- `tests/refoundation/research_qualification/test_backtest_reports.py`
- `tests/refoundation/research_qualification/test_backtest_comparison.py`

Tasks:

- [ ] Build the required report structure from canonical reconciled owners only.
- [ ] Produce byte-stable canonical JSON and Markdown from one projection.
- [ ] Exclude wall-clock report generation time from content.
- [ ] Publish content-addressed derived Artifacts with exact bindings.
- [ ] Implement exact compatibility fingerprint and fail-closed comparison.
- [ ] Implement visibly non-like-for-like descriptive comparison.
- [ ] Add all eight Application-backed `mra backtest` operations.
- [ ] Prove report/compare never read raw bars or write metric truth.

## Checkpoint 8 — Track A continuous prospective closure

Expected files:

- `src/market_regime_alpha/market/domain/prospective_archive.py`
- `src/market_regime_alpha/market/application/prospective_archive.py`
- `src/market_regime_alpha/market/ports/target_archive_schedule.py`
- `src/market_regime_alpha/runtime/application/` integration
- `src/market_regime_alpha/interfaces/cli/archive.py` or current generic archive CLI
- `tests/refoundation/market/test_prospective_runtime_schedule_postgres.py`
- `tests/refoundation/market/test_prospective_runtime_recovery_postgres.py`

Tasks:

- [ ] Correct Outcome-path versus point-window semantics.
- [ ] Replace the WP-specific archive execution interface with permanent names.
- [ ] Add immutable planning-gap Authority for missed generation planning.
- [ ] Bind roll-forward, due execution, overdue finalization, and recovery to
  existing Runtime schedule/run/attempt/fence.
- [ ] Prove no backdating, weekday arithmetic, blind retry, or second scheduler.
- [ ] Add generic prospective CLI commands and daily health projection.
- [ ] Inspect due windows before every long retrospective run.

## Checkpoint 9 — Safe operational upgrade

Expected files:

- `src/market_regime_alpha/infrastructure/postgres/schema.py`
- a packaged, content-hashed additive operational upgrade resource
- `src/market_regime_alpha/interfaces/cli/main.py`
- `tests/refoundation/test_operational_schema_upgrade.py`

Tasks:

- [ ] Implement read-only upgrade planning bound to exact database OID/catalog.
- [ ] Require a verified-readable `pg_dump` hash/size and disk preflight.
- [ ] Implement one locked additive transaction and append-only receipt.
- [ ] Prove stale plan, wrong OID/checksum, active Runtime, corrupt backup, and
  low disk fail before DDL.
- [ ] Prove historical rows and Artifact bytes remain unchanged.
- [ ] Reconcile schema, archive, and historical Backtest after upgrade.

## Checkpoint 10 — Real prospective and generic campaign proof

- [ ] Inspect PostgreSQL time and execute any due prospective work first.
- [ ] Safely upgrade the exact authorized operational database after backup.
- [ ] Run at least one real due prospective Runtime Attempt; retain its honest
  terminal state and evidence ceiling.
- [ ] Freeze one at-least-40-session, exact 32-symbol, four-arm, multi-fold,
  rule/ridge generic Backtest before validation Outcome access.
- [ ] Execute through the generic Runtime-backed platform.
- [ ] Publish and preserve deterministic JSON/Markdown report Artifacts.
- [ ] Resume/replay the exact same run and record
  `matched=true, mismatch_count=0`.

## Checkpoint 11 — Hard cut

- [ ] Re-run every historical/current/generic proof gate.
- [ ] Inventory all executable WP-specific callers and exports.
- [ ] Delete `Wp17pCampaignOperations` and other WP-specific Backtest execution
  or orchestration entry points.
- [ ] Remove the WP-specific prospective execution interface after generic
  Runtime replacement is proven.
- [ ] Retain only private exact decoder semantics and immutable evidence/docs.
- [ ] Prove no facade, dual execution, generation dispatch, or fallback remains.

Deletion is forbidden if any preceding checkbox is not proven.

## Checkpoint 12 — Full exact-SHA qualification

Run and classify every command:

```bash
uv sync --frozen --extra dev --extra postgres
uv run python scripts/check_docs_links.py
uv run python -m pytest -q tests/scripts/test_check_docs_links.py
uv run python -m pytest -q tests/platform
uv run python -m pytest -q tests/refoundation
uv run python -m pytest -q
uv run python -m ruff check .
uv run python -m mypy
uv run python -m build
git diff --check
```

Also run focused PostgreSQL bootstrap/recreate, migration, idempotency,
concurrency, failure/recovery, unknown-commit, replay, query-plan, compatibility,
report determinism, and operational-upgrade tests.

- [ ] Commit a clean implementation checkpoint.
- [ ] Qualify that exact SHA in a clean worktree and disposable PostgreSQL 16.
- [ ] Record every result as PASS, FAIL, NOT_RUN, or BLOCKED.
- [ ] Create immutable WP-18Q Verification bound to the implementation SHA.
- [ ] Reconcile Current State, Roadmap, Capability Matrix, docs index, tree IDs,
  database/catalog checksums, real Artifact identities, and evidence ceiling.
- [ ] Claim `WP18Q_EXIT_GATE = PASS` only after the immutable Verification and
  status documents agree.
