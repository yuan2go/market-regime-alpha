# PostgreSQL Free-Data Canonical Runtime V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a PostgreSQL-backed, Tencent-centered free-data composition that prepares and runs the existing Controlled parent and Canonical child to the honest Entry blocker.

**Architecture:** Reuse the PostgreSQL DailyLoop source-freeze journal, immutable Artifact Store, Controlled Operation, Feature V2, and Canonical Lifecycle. Add no new runtime state machine. Tighten PostgreSQL transaction semantics and require explicit production repository injection before adding the free-data facade.

**Tech Stack:** Python 3.12, uv, psycopg 3, PostgreSQL 16, pytest, Ruff, mypy, BaoStock, Tencent public HTTP, immutable JSON/Parquet artifacts.

## Global Constraints

- `PostgreSQL = state and transaction authority`.
- `Immutable Artifact Store = immutable evidence content authority`.
- Provider fallback is forbidden unless a new explicit profile identity is created.
- All free public data remains `EXPLORATORY` and `FORMAL_PIT_NOT_ESTABLISHED`.
- PathForecast uses `UnavailablePathForecastSampleProvider` unless qualified non-fixture samples exist.
- No Opportunity, Portfolio Decision, ManualTrade, Fill, Position mutation, Order, or Broker call may be created.
- `.idea/modules.xml` must remain unmodified by this work package and must never be staged.

---

### Task 1: PostgreSQL concurrency and composition guardrails

**Files:**
- Create: `src/market_regime_alpha/application/canonical_lifecycle/composition.py`
- Modify: `src/market_regime_alpha/application/canonical_lifecycle/sqlite_composition.py`
- Modify: `src/market_regime_alpha/application/canonical_lifecycle/postgres_composition.py`
- Modify: `src/market_regime_alpha/persistence/postgres/connection.py`
- Modify: `src/market_regime_alpha/persistence/postgres/dbapi.py`
- Modify: `src/market_regime_alpha/features/postgres_materialization_run.py`
- Test: `tests/architecture/test_postgres_runtime_boundaries.py`
- Test: `tests/persistence/postgres/test_runtime_concurrency.py`

**Interfaces:**
- Produces: `base_lifecycle_stage_handlers(...) -> tuple[LifecycleStageHandler, ...]`.
- Produces: retry metrics from `PostgresConnectionFactory.transaction(...)`.
- Produces: PostgreSQL feature claims selected with row locking and fencing.

- [ ] Extract backend-neutral stage construction from `sqlite_composition.py`; both PostgreSQL and explicit compatibility roots import the neutral module.
- [ ] Add a failing architecture test that rejects SQLite imports or constructors in PostgreSQL/production composition modules.
- [ ] Add deterministic PostgreSQL retry classification for SQLSTATE `40001` and `40P01`; reject retries for integrity, validation, and application errors.
- [ ] Replace silent `BEGIN IMMEDIATE -> BEGIN` weakening with a stable transaction-scoped advisory lock and expose lock/retry counters.
- [ ] Select Feature tasks with `FOR UPDATE SKIP LOCKED`, retain version/claim-token/epoch CAS, and test two concurrent workers receive disjoint tasks.
- [ ] Run `uv run pytest -q tests/persistence/postgres/test_runtime_concurrency.py tests/architecture/test_postgres_runtime_boundaries.py` and require PASS.
- [ ] Commit with `fix(db): enforce postgres runtime concurrency semantics`.

### Task 2: Metadata-complete free-data source archive

**Files:**
- Modify: `src/market_regime_alpha/data/providers/public_composite/contracts.py`
- Modify: `src/market_regime_alpha/data/providers/public_composite/live_clients.py`
- Modify: `src/market_regime_alpha/data/providers/public_composite/profiles.py`
- Modify: `src/market_regime_alpha/data/providers/public_composite/stage_artifact.py`
- Test: `tests/data/test_free_data_source_metadata.py`

**Interfaces:**
- Produces: `TENCENT_FREE_OPERATIONAL_V1`.
- Produces: `RawSourceRequestMetadata` embedded in new live `AcquiredSourcePayload` writes.
- Preserves: V1 payload/archive readers for historical replay.

- [ ] Write fixture tests for exact request metadata, raw byte hash, response size, encoding, Content-Type mismatch, timeout, empty body, malformed encoding, and provider-profile identity.
- [ ] Implement the optional metadata schema with canonical serialization and backward-compatible V1 reads.
- [ ] Capture Tencent HTTP status/headers/timing before parsing and validate the response envelope without trusting Content-Type alone.
- [ ] Capture BaoStock product parameters and explicit unavailable HTTP/provider-time fields; never invent them.
- [ ] Assert a Tencent failure raises a blocked acquisition result and never returns static or alternate-provider values.
- [ ] Run `uv run pytest -q tests/data/test_free_data_source_metadata.py tests/data/test_public_composite_provider.py tests/data/test_public_source_stage_artifact.py` and require PASS.
- [ ] Commit with `feat(data): define tencent free operational source evidence`.

### Task 3: Free-data input materialization

**Files:**
- Create: `src/market_regime_alpha/application/free_data_operation/__init__.py`
- Create: `src/market_regime_alpha/application/free_data_operation/contracts.py`
- Create: `src/market_regime_alpha/application/free_data_operation/builders.py`
- Modify: `src/market_regime_alpha/application/daily_loop/runner.py`
- Test: `tests/application/free_data_operation/test_builders.py`

**Interfaces:**
- Produces: `FreeDataOperationScale` with exact `SMOKE=20`, `STANDARD=100`, `STRESS=300` scopes.
- Produces: `FreeDataPreparedInputs` containing verified paths for calendar, universe, source stage/manifest, supplemental evidence, and runtime configuration.
- Consumes: `AcquiredReplaySource`, verified source-stage artifacts, and PostgreSQL repository factories.

- [ ] Expose a public DailyLoop source-freeze result so free-data preparation reuses journal recovery without running B0/B1 decisions.
- [ ] Build an explicit calendar only from archived provider session evidence; reject inferred weekdays.
- [ ] Materialize all requested Universe records with listing/ST/suspension/history/liquidity evidence and exclusion reasons.
- [ ] Normalize included assets through Canonical Market Data and use Decimal/SHARES/CNY contracts.
- [ ] Derive market and symbol observable proxies only from verified canonical bars.
- [ ] Emit typed `MissingEvidence` for absent theme membership, ETF mapping, or capital inputs and allow Controlled research to return `DATA_INSUFFICIENT` instead of raising during input construction.
- [ ] Publish an idempotent prepared-input manifest whose identities and hashes bind every child artifact.
- [ ] Run `uv run pytest -q tests/application/free_data_operation/test_builders.py tests/universe/test_operational_universe.py tests/market_data` and require PASS.
- [ ] Commit with `feat(data): materialize free operational inputs`.

### Task 4: Existing Runtime composition and CLI facade

**Files:**
- Create: `src/market_regime_alpha/application/free_data_operation/service.py`
- Create: `src/market_regime_alpha/cli/free_data_operation.py`
- Modify: `src/market_regime_alpha/cli/_controlled_operation.py`
- Modify: `pyproject.toml`
- Test: `tests/application/free_data_operation/test_service.py`
- Test: `tests/cli/test_free_data_operation_cli.py`

**Interfaces:**
- Produces: `prepare`, `run`, `resume`, `replay`, `report`, and `inspect` subcommands plus the six requested console-script names.
- Consumes: `RepositoryFactory`, `ControlledDecisionTimeOperationRunner`, and existing replay/report readers.

- [ ] Write CLI contract tests for all required identifiers, redacted database authority, code revision, configuration hash, runtime status, blocker, Artifact root, and safety declarations.
- [ ] Compose DailyLoop source freeze, prepared inputs, Controlled parent, Feature runs, and Canonical child without creating another journal.
- [ ] Treat empty CandidateSet, provider failure, missing theme evidence, missed window, Path `DATA_INSUFFICIENT`, and Entry blocker as distinct auditable statuses.
- [ ] Ensure `ENGINEERING_RUN_COMPLETED` and `ENTRY_AUTHORITY_BLOCKED` cannot render as a successful trade decision.
- [ ] Add structured provider/stage/feature/candidate/signal/recovery/retry/lock/deadline metrics without secrets.
- [ ] Run `uv run pytest -q tests/application/free_data_operation tests/cli/test_free_data_operation_cli.py` and require PASS.
- [ ] Commit with `feat(runtime): compose free data canonical operation`.

### Task 5: PostgreSQL and 20/100/300 end-to-end proof

**Files:**
- Create: `tests/persistence/postgres/test_free_data_operation.py`
- Create: `tests/application/free_data_operation/test_recorded_e2e.py`
- Create: `scripts/run_free_data_live_smoke.py`
- Modify: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: real PostgreSQL fixture and recorded raw archives.
- Produces: deterministic replay equality and explicit live-smoke evidence classification.

- [ ] Test idempotency conflict, CAS, concurrent claim, lease expiration, fencing, retry, restart, append-only events, and parent/child references on real PostgreSQL.
- [ ] Parameterize recorded end-to-end tests for 20, 100, and 300 symbols; require stable hashes and no repeated acquisition or Feature publication.
- [ ] Assert provider failure cannot enter a static example; missing evidence fails closed.
- [ ] Assert zero Opportunity, Portfolio, ManualTrade, Fill, Position mutation, Order, and Broker calls.
- [ ] Keep live network smoke outside ordinary CI and label fixture, recorded replay, and live evidence separately.
- [ ] Run the PostgreSQL and recorded commands with `MARKET_REGIME_ALPHA_TEST_DATABASE_URL` and require PASS.
- [ ] Commit with `test(runtime): prove free data postgres replay boundaries`.

### Task 6: Documentation, qualification, and publication

**Files:**
- Create: `docs/architecture/audits/PostgreSQL-Free-Data-Migration-Matrix.md`
- Create: `docs/delivery/PostgreSQL-Free-Data-Canonical-Runtime-V1.md`
- Modify: `README.md`
- Modify: `docs/status/Current-State.md`
- Modify: `docs/status/Capability-Matrix.md`
- Modify: `docs/status/Gap-Register.md`
- Modify: `docs/operations/PostgreSQL-Authority-Runbook.md`

**Interfaces:**
- Produces: SHA-bound migration matrix, live/replay evidence table, command ledger, unresolved P0/P1/P2 list, and capability booleans.

- [ ] Document `ACTIVE_PROHIBITED`, `READ_ONLY_COMPATIBILITY`, `TEST_ONLY`, `LEGACY_ARCHIVE`, and `REMOVABLE` SQLite classifications from actual call chains.
- [ ] Run an explicit live 20-symbol smoke if the decision window and providers permit; otherwise preserve the real blocked evidence and external limitation.
- [ ] Run `uv sync --frozen --extra dev --extra postgres`, docs links, full pytest, Ruff, mypy, build, PostgreSQL integration tests, and `git diff --check`.
- [ ] Record every command as PASS, FAIL, NOT_RUN, or BLOCKED with Python/PostgreSQL versions, exact tested SHA, counts, warnings, duration, and live-evidence class.
- [ ] Review the complete diff, exclude `.idea/modules.xml`, secrets, and generated local artifacts, then commit and push normally without force.
- [ ] Publish the final report with `formal_pit=false`, `formal_oos_alpha=false`, `entry_model_validated=false`, `shadow_ready=false`, `broker_integration_proven=false`, `trading_authority=false`, and `production_ready=false`.
