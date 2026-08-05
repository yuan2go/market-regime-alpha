# PostgreSQL Authority Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the dedicated local PostgreSQL 16 database the default persistence authority for every current SQLite-backed runtime and domain repository, with verified SQLite import and explicit SQLite compatibility.

**Architecture:** Existing Repository Protocols remain the domain boundary. A central PostgreSQL package owns settings, connections, migrations, redaction, and import infrastructure; bounded contexts expose PostgreSQL adapters while SQLite implementations remain explicit compatibility adapters. Cutover is single-authority and fail-closed: no dual write and no silent SQLite fallback.

**Tech Stack:** Python 3.12, psycopg 3 with `psycopg_pool`, PostgreSQL 16, SQLite compatibility fixtures, SQL migrations, pytest, Ruff, mypy, uv, GitHub Actions PostgreSQL service.

## Global Constraints

- Planning baseline is commit `bceeaf7`.
- Preserve `.idea/modules.xml` and every unrelated user change exactly.
- Use role, database, and schema name `market_regime_alpha`.
- Never commit or log the administrator password, generated application password, or an unredacted DSN.
- Administrator `novel_forge` is bootstrap-only and never an application fallback.
- PostgreSQL is the runtime default; SQLite requires explicit compatibility selection.
- Never dual-write or silently fall back between database authorities.
- Canonical JSON authority bytes remain text; PostgreSQL must not normalize them through `jsonb`.
- Preserve idempotency, command hashes, CAS, fencing, append-only history, immutable identities, restore validation, and replay semantics.
- DuckDB, Parquet, CSV, immutable Artifacts, and source archives stay outside this migration.
- No broker, Fill invention, automatic execution, formal-data qualification, Shadow readiness, production qualification, or trading-authority claim.
- All evidence and documentation claims bind to the exact tested HEAD.

---

### Task 1: PostgreSQL Settings, Redaction, and Secure Bootstrap

**Files:**
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Create: `src/market_regime_alpha/persistence/__init__.py`
- Create: `src/market_regime_alpha/persistence/settings.py`
- Create: `src/market_regime_alpha/persistence/postgres/__init__.py`
- Create: `src/market_regime_alpha/persistence/postgres/connection.py`
- Create: `scripts/bootstrap_postgres.py`
- Create: `tests/persistence/test_settings.py`
- Create: `tests/persistence/test_postgres_bootstrap.py`

**Interfaces:**
- Produces: `DatabaseBackend(str, Enum)` with `POSTGRES` and `SQLITE`.
- Produces: `DatabaseSettings.from_sources(database_url, sqlite_path, environ) -> DatabaseSettings`.
- Produces: `redact_database_url(value: str) -> str`.
- Produces: `PostgresConnectionFactory(settings)` backed by a bounded `psycopg_pool.ConnectionPool` and `.connection(read_only=False)`.
- Produces: bootstrap CLI accepting administrator coordinates through arguments/environment while reading passwords only from environment or secure prompt.

- [ ] **Step 1: Add failing configuration and redaction tests.**

  Cover PostgreSQL default selection, `MARKET_REGIME_ALPHA_DATABASE_URL`, explicit SQLite selection, incompatible arguments, missing configuration, and percent-encoded password redaction.

  ```python
  def test_default_backend_requires_postgres_url() -> None:
      with pytest.raises(DatabaseConfigurationError, match="PostgreSQL configuration"):
          DatabaseSettings.from_sources(database_url=None, sqlite_path=None, environ={})

  def test_redaction_never_exposes_password() -> None:
      value = "postgresql://market_regime_alpha:s%40cret@127.0.0.1:5432/market_regime_alpha"
      assert "s%40cret" not in redact_database_url(value)
  ```

- [ ] **Step 2: Run the tests and observe the expected missing-module failures.**

  Run: `uv run pytest -q tests/persistence/test_settings.py tests/persistence/test_postgres_bootstrap.py`

- [ ] **Step 3: Make psycopg a core runtime dependency and implement immutable settings.**

  ```python
  @dataclass(frozen=True)
  class DatabaseSettings:
      backend: DatabaseBackend
      database_url: str | None = None
      sqlite_path: Path | None = None

      def __post_init__(self) -> None:
          if (self.database_url is None) == (self.sqlite_path is None):
              raise DatabaseConfigurationError("select exactly one database authority")
  ```

  Move `psycopg[binary,pool]>=3.2` from the optional-only path into project runtime dependencies, regenerate `uv.lock`, and retain the `postgres` extra only if compatibility with existing install commands requires an empty marker.

- [ ] **Step 4: Implement bounded connection pooling, initialization, and typed exception redaction.**

  Use a small local pool with explicit minimum/maximum size, acquisition timeout, max idle, and max lifetime. Every checked-out connection sets `search_path = market_regime_alpha, pg_catalog`, `timezone = UTC`, `application_name = market-regime-alpha`, `statement_timeout`, `lock_timeout`, and `idle_in_transaction_session_timeout`. Error messages expose host, port, and database but never credentials.

- [ ] **Step 5: Implement idempotent, conflict-safe bootstrap.**

  Resolve existing role/database attributes before mutation. Create a generated application password, non-superuser login role, owned database, application schema, search path, and least required privileges. Refuse conflicting ownership or privileged role attributes. Append only `MARKET_REGIME_ALPHA_DATABASE_URL` to a new or existing Git-ignored `.env` without overwriting unrelated keys.

- [ ] **Step 6: Run focused tests and bootstrap dry-run.**

  Run: `uv run pytest -q tests/persistence/test_settings.py tests/persistence/test_postgres_bootstrap.py`

- [ ] **Step 7: Commit the foundation checkpoint.**

  ```bash
  git add pyproject.toml uv.lock src/market_regime_alpha/persistence scripts/bootstrap_postgres.py tests/persistence
  git diff --cached --check
  git commit -m "feat(db): add secure PostgreSQL foundation"
  ```

### Task 2: Transactional PostgreSQL Migration Registry and Authority Schema

**Files:**
- Create: `src/market_regime_alpha/persistence/postgres/migrator.py`
- Create: `src/market_regime_alpha/persistence/postgres/schema.py`
- Create: `src/market_regime_alpha/persistence/postgres/migrations/001_governance.sql`
- Create: `src/market_regime_alpha/persistence/postgres/migrations/002_decision_lifecycle.sql`
- Create: `src/market_regime_alpha/persistence/postgres/migrations/003_portfolio_risk.sql`
- Create: `src/market_regime_alpha/persistence/postgres/migrations/004_manual_execution.sql`
- Create: `src/market_regime_alpha/persistence/postgres/migrations/005_complete_account_portfolio_risk.sql`
- Create: `src/market_regime_alpha/persistence/postgres/migrations/006_execution_traceability.sql`
- Create: `src/market_regime_alpha/persistence/postgres/migrations/007_risk_routes.sql`
- Create: `src/market_regime_alpha/persistence/postgres/migrations/008_thesis_health.sql`
- Create: `src/market_regime_alpha/persistence/postgres/migrations/009_composite_operational_evidence.sql`
- Create: `src/market_regime_alpha/persistence/postgres/migrations/010_risk_reduction_manual_intent.sql`
- Create: `src/market_regime_alpha/persistence/postgres/migrations/011_canonical_lifecycle_runtime.sql`
- Create: `src/market_regime_alpha/persistence/postgres/migrations/012_feature_materialization_run.sql`
- Create: `src/market_regime_alpha/persistence/postgres/migrations/013_feature_materialization_hardening.sql`
- Create: `src/market_regime_alpha/persistence/postgres/migrations/014_controlled_operation.sql`
- Create: `src/market_regime_alpha/persistence/postgres/migrations/015_longitudinal_operational_index.sql`
- Create: `src/market_regime_alpha/persistence/postgres/migrations/016_daily_runtime_journal.sql`
- Modify: `pyproject.toml`
- Create: `tests/persistence/postgres/conftest.py`
- Create: `tests/persistence/postgres/test_migrator.py`
- Create: `tests/persistence/postgres/test_schema.py`

**Interfaces:**
- Produces: `PostgresMigration(version: int, name: str, checksum: str, sql: str)`.
- Produces: `PostgresMigrator.apply_all(connection_factory) -> tuple[AppliedMigration, ...]`.
- Produces: `verify_postgres_authority_schema(connection) -> None`.
- Test fixture consumes `MARKET_REGIME_ALPHA_TEST_DATABASE_URL` and creates one isolated schema per test worker.

- [ ] **Step 1: Write migration registry tests.**

  Prove empty application, unchanged re-run, checksum drift rejection, missing version rejection, transactional failure, advisory-lock serialization, and exact registry contents.

- [ ] **Step 2: Write schema invariant tests before adding SQL.**

  Parameterize all authority tables and expected primary keys, unique indexes, foreign keys, foreign-key supporting indexes, query indexes, check constraints, and triggers. Test representative UPDATE/DELETE rejection for every append-only family.

- [ ] **Step 3: Implement the migrator.**

  ```python
  with connection.transaction():
      connection.execute("SELECT pg_advisory_xact_lock(%s)", (MIGRATION_LOCK_KEY,))
      applied = load_registry(connection)
      verify_applied_checksums(applied, migrations)
      connection.execute(migration.sql)
      connection.execute(
          "INSERT INTO schema_migrations(version, name, checksum, applied_at) VALUES (%s, %s, %s, now())",
          (migration.version, migration.name, migration.checksum),
      )
  ```

- [ ] **Step 4: Port versions 001–010 exactly.**

  Preserve canonical text columns and domain constraints. Replace SQLite trigger `RAISE` with named PL/pgSQL functions raising integrity exceptions. Use explicit conflict targets and partial/covering indexes only when they match observed repository reads.

- [ ] **Step 5: Port versions 011–015 and add version 016.**

  Map autoincrement identifiers to identity bigint, SHA checks to PostgreSQL-compatible expressions, and lifecycle/controlled-operation fencing constraints without relaxing them. Move the Daily Runtime Journal's inline schema into version 016.

- [ ] **Step 6: Implement catalog-based schema verification.**

  Query `pg_catalog.pg_class`, `pg_attribute`, `pg_constraint`, `pg_index`, and `pg_trigger`; do not compare normalized `CREATE TABLE` strings.

- [ ] **Step 7: Run PostgreSQL schema tests.**

  Run: `uv run pytest -q tests/persistence/postgres/test_migrator.py tests/persistence/postgres/test_schema.py`

- [ ] **Step 8: Commit the schema checkpoint.**

  ```bash
  git add pyproject.toml src/market_regime_alpha/persistence/postgres tests/persistence/postgres
  git diff --cached --check
  git commit -m "feat(db): port authority schema to PostgreSQL"
  ```

### Task 3: PostgreSQL DB-API Bridge and Domain Authority Adapters

**Files:**
- Create: `src/market_regime_alpha/persistence/postgres/dbapi.py`
- Create: `src/market_regime_alpha/platform/postgres_governance.py`
- Create: `src/market_regime_alpha/decision/postgres_repository.py`
- Create: `src/market_regime_alpha/portfolio/postgres_repository.py`
- Create: `src/market_regime_alpha/execution/postgres_repository.py`
- Create: `src/market_regime_alpha/position/postgres_thesis_health.py`
- Create: `src/market_regime_alpha/application/operational_research/postgres_composite_repository.py`
- Create: `src/market_regime_alpha/application/trading_lifecycle/postgres_risk_reduction.py`
- Modify: `src/market_regime_alpha/platform/__init__.py`
- Modify: `src/market_regime_alpha/decision/__init__.py`
- Modify: `src/market_regime_alpha/portfolio/__init__.py`
- Modify: `src/market_regime_alpha/execution/__init__.py`
- Modify: `src/market_regime_alpha/position/__init__.py`
- Modify: `src/market_regime_alpha/application/operational_research/__init__.py`
- Modify: `src/market_regime_alpha/application/trading_lifecycle/__init__.py`
- Create: `tests/persistence/postgres/test_dbapi.py`
- Create: `tests/persistence/postgres/test_domain_repository_parity.py`

**Interfaces:**
- Produces: `PostgresRow(Mapping[str, object])` with stable name and positional access used by existing codecs.
- Produces: `PostgresCursor.execute`, `executemany`, `fetchone`, `fetchall`, `rowcount`, and explicit generated-ID access.
- Produces bounded-context classes prefixed `Postgres` implementing the same Protocols as current SQLite adapters.

- [ ] **Step 1: Add DB-API behavior tests.**

  Verify qmark-to-psycopg placeholder compilation ignores quoted question marks, `BEGIN IMMEDIATE` maps to a PostgreSQL transaction, explicit `INSERT OR IGNORE` maps only to declared conflict targets, rows support existing codec access, and PostgreSQL integrity errors become typed persistence conflicts without leaking DSNs.

- [ ] **Step 2: Implement the smallest shared bridge.**

  The bridge may share row/cursor and placeholder mechanics, but it must not dynamically translate schema SQL, infer conflict targets, or hide arbitrary PostgreSQL errors. Generated identifiers use explicit `RETURNING`.

- [ ] **Step 3: Add parameterized SQLite/PostgreSQL contract cases.**

  Reuse existing domain fixtures for Governance, Decision, Portfolio/Risk, Manual Execution, Position books, Risk Routes, Thesis Health, Composite Evidence, and Risk-Reduction Manual Intent. Compare reconstructed canonical dictionaries and exact exception categories.

- [ ] **Step 4: Implement versions 001–006 adapters.**

  Extract backend-neutral state restoration only where needed. Keep transaction ownership in the adapter and use `ON CONFLICT`, conditional `UPDATE ... WHERE version = %s`, `FOR UPDATE`, and `RETURNING` explicitly. Acquire multiple row locks in stable primary-key order and keep external Artifact/network operations outside database transactions.

- [ ] **Step 5: Implement versions 007–010 adapters.**

  Preserve risk recomputation, complete evidence restoration, authority-route conflicts, append-only command attempts, and manual-only H4.5 semantics. No adapter may create a Fill or broker call.

- [ ] **Step 6: Run contract parity and existing domain suites.**

  Run: `uv run pytest -q tests/persistence/postgres/test_dbapi.py tests/persistence/postgres/test_domain_repository_parity.py tests/platform tests/decision tests/portfolio tests/execution tests/position tests/application/operational_research`

- [ ] **Step 7: Commit the domain adapter checkpoint.**

  ```bash
  git add src/market_regime_alpha tests/persistence/postgres
  git diff --cached --check
  git commit -m "feat(db): add PostgreSQL domain repositories"
  ```

### Task 4: Daily, Feature, and Canonical Runtime Adapters

**Files:**
- Create: `src/market_regime_alpha/application/daily_loop/postgres_repository.py`
- Create: `src/market_regime_alpha/features/postgres_materialization_run.py`
- Create: `src/market_regime_alpha/application/canonical_lifecycle/postgres_repository.py`
- Create: `src/market_regime_alpha/application/canonical_lifecycle/postgres_schema.py`
- Create: `src/market_regime_alpha/application/canonical_lifecycle/postgres_composition.py`
- Modify: `src/market_regime_alpha/application/daily_loop/__init__.py`
- Modify: `src/market_regime_alpha/features/__init__.py`
- Modify: `src/market_regime_alpha/application/canonical_lifecycle/__init__.py`
- Create: `tests/persistence/postgres/test_daily_repository_parity.py`
- Create: `tests/persistence/postgres/test_feature_repository_parity.py`
- Create: `tests/persistence/postgres/test_canonical_repository_parity.py`

**Interfaces:**
- `PostgresDailyRunRepository` implements `DailyRunRepository`.
- `PostgresFeatureMaterializationRunRepository` matches the materialization runner's current repository surface including fencing and recovery.
- `PostgresLifecycleRunRepository` implements `LifecycleRunRepository` with `read_only` transaction support.
- `postgres_lifecycle_stage_handlers(...)` binds PostgreSQL domain authority adapters.

- [ ] **Step 1: Add Daily journal parity tests.**

  Cover create/get, identity binding, stage receipts, acquisition receipts, CAS transition, idempotent read, crash retry, restart, and terminal status behavior.

- [ ] **Step 2: Add Feature journal parity tests.**

  Cover generated IDs, batch claims, lease heartbeat/expiry, epoch fencing, attempt and receipt append-only behavior, crash seams, bundle settlement, and one-snapshot reads.

- [ ] **Step 3: Add Canonical lifecycle parity tests.**

  Cover 16-stage creation, command conflict, claim fencing, stage settlement, receipt/event history, recovery/resume, source snapshot, replay tamper rejection, and read-only mode.

- [ ] **Step 4: Implement all three adapters.**

  Use transactionally consistent PostgreSQL reads. Replace SQLite schema text introspection with the catalog verifier. Preserve source history capture before replay mutation and immutable file publication behavior.

- [ ] **Step 5: Bind PostgreSQL domain handlers.**

  The PostgreSQL composition root binds Decision, Portfolio/Risk, Risk Route, Manual Intent, Thesis Health, and Composite Evidence adapters to the same database settings and schema.

- [ ] **Step 6: Run focused and regression suites.**

  Run: `uv run pytest -q tests/persistence/postgres/test_daily_repository_parity.py tests/persistence/postgres/test_feature_repository_parity.py tests/persistence/postgres/test_canonical_repository_parity.py tests/application/daily_loop tests/features tests/application/canonical_lifecycle`

- [ ] **Step 7: Commit the lifecycle adapter checkpoint.**

  ```bash
  git add src/market_regime_alpha tests/persistence/postgres
  git diff --cached --check
  git commit -m "feat(db): run lifecycle journals on PostgreSQL"
  ```

### Task 5: Controlled Operation and Longitudinal PostgreSQL Adapters

**Files:**
- Create: `src/market_regime_alpha/application/controlled_operation/postgres_journal.py`
- Create: `src/market_regime_alpha/application/controlled_operation/postgres_longitudinal_index.py`
- Modify: `src/market_regime_alpha/application/controlled_operation/runner.py`
- Modify: `src/market_regime_alpha/application/controlled_operation/replay.py`
- Modify: `src/market_regime_alpha/application/controlled_operation/__init__.py`
- Create: `tests/persistence/postgres/test_controlled_operation_parity.py`
- Create: `tests/persistence/postgres/test_longitudinal_index_parity.py`

**Interfaces:**
- `PostgresDecisionTimeOperationJournal` implements the current journal surface.
- `PostgresLongitudinalOperationalIndex` implements append/query/rebuild behavior.
- Runner receives repository Protocols or factories; it does not construct SQLite adapters internally.

- [ ] **Step 1: Add Controlled Operation parity and concurrency tests.**

  Prove parent run/stage/attempt/receipt/event behavior, child bindings, deadlines, claim/heartbeat/expiry, stale-writer rejection, restart repair, and one-snapshot history.

- [ ] **Step 2: Add Longitudinal Index parity tests.**

  Prove immutable append, exact duplicate idempotency, conflicting duplicate rejection, date/model/config queries, missing-day detection, and deterministic rebuild.

- [ ] **Step 3: Implement adapters and remove internal SQLite construction.**

  Inject canonical journal and longitudinal-index factories. Replay opens PostgreSQL consistent snapshots and continues to reject domain-authority mutation.

- [ ] **Step 4: Run controlled-operation regression.**

  Run: `uv run pytest -q tests/persistence/postgres/test_controlled_operation_parity.py tests/persistence/postgres/test_longitudinal_index_parity.py tests/application/controlled_operation`

- [ ] **Step 5: Commit the controlled-operation checkpoint.**

  ```bash
  git add src/market_regime_alpha/application/controlled_operation tests/persistence/postgres
  git diff --cached --check
  git commit -m "feat(db): persist controlled operations in PostgreSQL"
  ```

### Task 6: PostgreSQL-Default Composition and CLI Cutover

**Files:**
- Create: `src/market_regime_alpha/persistence/repository_factory.py`
- Modify: `src/market_regime_alpha/cli/_canonical_lifecycle_output.py`
- Modify: `src/market_regime_alpha/cli/_controlled_operation.py`
- Modify: `src/market_regime_alpha/cli/run_canonical_lifecycle.py`
- Modify: `src/market_regime_alpha/cli/replay_canonical_lifecycle.py`
- Modify: `src/market_regime_alpha/cli/create_manual_trade_from_risk_decision.py`
- Modify: `scripts/run_exploratory_daily_loop.py`
- Modify: `scripts/run_decision_lifecycle.py`
- Modify: `scripts/run_portfolio_risk.py`
- Modify: `scripts/assess_risk_reduction.py`
- Modify: `scripts/build_thesis_health.py`
- Modify: `scripts/build_composite_operational_manifest.py`
- Modify: `scripts/record_manual_trade.py`
- Modify: `scripts/record_manual_fill.py`
- Create: `tests/persistence/test_repository_factory.py`
- Create: `tests/persistence/test_cli_backend_selection.py`

**Interfaces:**
- Produces repository constructors keyed by Protocol and `DatabaseSettings`.
- CLI arguments: `--database-url` for explicit PostgreSQL override; `--sqlite-database` for explicit compatibility; both together are invalid.
- Default source is `.env`/`MARKET_REGIME_ALPHA_DATABASE_URL` and backend is PostgreSQL.

- [ ] **Step 1: Add factory and CLI selection tests.**

  Assert PostgreSQL default, explicit URL precedence, explicit SQLite compatibility, missing configuration failure, conflicting argument failure, redacted errors, and replay binding stability.

- [ ] **Step 2: Implement protocol-oriented repository factories.**

  ```python
  def lifecycle_repository(settings: DatabaseSettings, *, read_only: bool = False) -> LifecycleRunRepository:
      if settings.backend is DatabaseBackend.POSTGRES:
          return PostgresLifecycleRunRepository(settings, read_only=read_only)
      return SQLiteLifecycleRunRepository(settings.require_sqlite_path(), read_only=read_only)
  ```

- [ ] **Step 3: Migrate canonical and controlled CLI composition.**

  Stored command bindings must identify the backend and stable database locator without persisting credentials. Resume rejects a backend or locator mismatch.

- [ ] **Step 4: Migrate domain scripts.**

  Keep existing JSON request/response contracts and exit-code taxonomy. Rename SQLite-only flags without accepting an ambiguous path as a PostgreSQL locator.

- [ ] **Step 5: Run CLI and integration tests.**

  Run: `uv run pytest -q tests/persistence/test_repository_factory.py tests/persistence/test_cli_backend_selection.py tests/application/canonical_lifecycle/test_cli.py tests/application/controlled_operation/test_cli.py tests/execution/test_create_manual_trade_from_risk_decision_cli.py`

- [ ] **Step 6: Commit the runtime cutover checkpoint.**

  ```bash
  git add src/market_regime_alpha scripts tests/persistence
  git diff --cached --check
  git commit -m "feat(db): default runtime composition to PostgreSQL"
  ```

### Task 7: SQLite Importer and Immutable Migration Evidence

**Files:**
- Create: `src/market_regime_alpha/persistence/migration_manifest.py`
- Create: `src/market_regime_alpha/persistence/sqlite_to_postgres.py`
- Create: `src/market_regime_alpha/persistence/migration_report.py`
- Create: `scripts/migrate_sqlite_to_postgres.py`
- Create: `tests/persistence/test_migration_manifest.py`
- Create: `tests/persistence/postgres/test_sqlite_import.py`
- Create: `tests/persistence/postgres/test_migration_report.py`

**Interfaces:**
- `SQLiteMigrationManifest.from_json(path) -> SQLiteMigrationManifest`.
- `SQLiteToPostgresMigrator.plan(manifest, settings) -> MigrationPlan`.
- `SQLiteToPostgresMigrator.execute(plan, output_root) -> MigrationReport`.
- Report publisher creates content-addressed JSON plus SHA-256 manifest and exact-file-set Reader verification.

- [ ] **Step 1: Add manifest validation tests.**

  Reject relative paths, duplicate source names, unknown table ownership, schema mismatch, missing files, unsupported tables, changed source hashes, and non-quiescent source files.

- [ ] **Step 2: Add fixture import tests.**

  Build representative SQLite databases through the authoritative SQLite repositories, import into an empty isolated PostgreSQL schema, and compare rows, primary-key ranges, canonical table digests, sequences, foreign keys, and reconstructed domain objects.

- [ ] **Step 3: Implement canonical row/table digests.**

  Digest stable primary-key-ordered rows with explicit type tags and canonical UTF-8 encoding. Do not depend on SQLite or PostgreSQL display formatting.

- [ ] **Step 4: Implement all-or-nothing import.**

  Hold SQLite read transactions, require quiescent source hashes, require empty PostgreSQL business tables, copy in dependency order with psycopg `COPY FROM STDIN` and explicit column lists, reset identity sequences, validate constraints, and commit one PostgreSQL transaction only after every Reader/digest check passes.

- [ ] **Step 5: Implement schema-only evidence.**

  An empty manifest produces a valid `0 -> 0` report only after every PostgreSQL migration and table inventory check succeeds. It must not claim that undiscovered SQLite data was migrated.

- [ ] **Step 6: Add rollback and tamper tests.**

  Prove non-empty target, duplicate key, digest mismatch, source mutation, invalid canonical JSON, foreign-key violation, sequence mismatch, and injected fault all leave PostgreSQL business tables unchanged and publish no success report.

- [ ] **Step 7: Run importer tests.**

  Run: `uv run pytest -q tests/persistence/test_migration_manifest.py tests/persistence/postgres/test_sqlite_import.py tests/persistence/postgres/test_migration_report.py`

- [ ] **Step 8: Commit the import checkpoint.**

  ```bash
  git add src/market_regime_alpha/persistence scripts/migrate_sqlite_to_postgres.py tests/persistence
  git diff --cached --check
  git commit -m "feat(db): migrate SQLite authority into PostgreSQL"
  ```

### Task 8: CI, Operator Workflow, Local Cutover, and Final Evidence

**Files:**
- Modify: `.github/workflows/ci.yml`
- Modify: `README.md`
- Modify: `docs/status/Current-State.md`
- Modify: `docs/status/Capability-Matrix.md`
- Modify: `docs/status/Gap-Register.md`
- Modify: `docs/architecture/10-Production-Decision-Lifecycle.md`
- Create: `docs/operations/PostgreSQL-Authority-Runbook.md`
- Create: `docs/evidence/PostgreSQL-Authority-Migration-Evidence.md`
- Create: `tests/scripts/test_postgres_commands.py`

**Interfaces:**
- CI exposes `MARKET_REGIME_ALPHA_TEST_DATABASE_URL` only to PostgreSQL integration tests.
- Runbook specifies bootstrap, migrate, backup, smoke, explicit pre-write rollback, and post-write forward-repair commands.
- Evidence binds database server version, migration checksums, report digest, validation commands, and exact Git SHA without credentials.

- [ ] **Step 1: Add a pinned PostgreSQL service to CI.**

  ```yaml
  services:
    postgres:
      image: postgres:16
      env:
        POSTGRES_USER: market_regime_alpha_test
        POSTGRES_PASSWORD: market_regime_alpha_test
        POSTGRES_DB: market_regime_alpha_test
      ports:
        - 5432:5432
      options: >-
        --health-cmd "pg_isready -U market_regime_alpha_test"
        --health-interval 5s --health-timeout 5s --health-retries 10
  ```

- [ ] **Step 2: Test documented commands and secret exclusion.**

  Parse every runbook command, assert scripts exist, verify `git grep` cannot find supplied/generated passwords, and ensure status docs retain all authority non-claims.

- [ ] **Step 3: Bootstrap the approved local resources.**

  Use the supplied administrator connection through environment-only secrets. Verify role attributes, database owner, schema owner, search path, PostgreSQL version, and absence of target business data. Never echo DSNs.

- [ ] **Step 4: Apply migrations, capture backup, and run schema-only import.**

  Store the backup outside tracked paths. Publish the immutable `0 -> 0` migration report and explicitly state that no business SQLite source was discoverable.

- [ ] **Step 5: Run PostgreSQL smoke scenarios.**

  Exercise Governance, Decision, Portfolio/Risk, Manual Execution without invented Fill, Canonical Lifecycle, Feature Materialization, Controlled Operation, restart/replay, and longitudinal reads against the dedicated local database.

- [ ] **Step 6: Run the complete validation matrix.**

  ```text
  git diff --check
  uv run python scripts/check_docs_links.py
  uv run pytest -q tests/scripts/test_check_docs_links.py
  uv run pytest -q tests/platform
  uv run pytest -q
  uv run ruff check .
  uv run mypy
  uv run python -m build
  ```

- [ ] **Step 7: Reconcile documentation and exact-HEAD evidence.**

  State PostgreSQL persistence scope, local validation, CI status, discovered source-data scope, and every remaining authority ceiling. Do not call local PG setup production-qualified.

- [ ] **Step 8: Commit the final cutover checkpoint.**

  ```bash
  git add .github/workflows/ci.yml README.md docs src tests scripts pyproject.toml uv.lock
  git diff --cached --check
  git commit -m "docs(db): qualify local PostgreSQL authority cutover"
  ```

- [ ] **Step 9: Verify final repository and database state.**

  Confirm `.idea/modules.xml` remains unstaged and untouched by this work, no credentials are tracked, PostgreSQL is selected by `.env`, schema migration checksums match, the migration report verifies, and every reported validation result binds the final HEAD.
