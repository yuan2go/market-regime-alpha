# PostgreSQL Authority Runbook

> **Status:** CURRENT_STATUS
> **Authority:** Local PostgreSQL bootstrap, migration, cutover and recovery procedure
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-05
> **Related Documents:** ../status/Current-State.md, ../status/Capability-Matrix.md, ../evidence/PostgreSQL-Authority-Migration-Evidence.md, ../superpowers/specs/2026-08-05-postgresql-authority-migration-design.md

## Scope and safety boundary

PostgreSQL is the default database authority for runtime journals and domain repositories. SQLite is an explicit compatibility/import source only; there is no dual write and no automatic fallback. DuckDB, Parquet, CSV and immutable file Artifacts remain outside database authority.

This runbook proves local persistence mechanics. It does not establish formal PIT data, OOS Alpha, sustained Shadow operation, authenticated operators, production readiness, Broker authority or automatic execution.

Approved local resources:

```text
role=market_regime_alpha
database=market_regime_alpha
schema=market_regime_alpha
host=127.0.0.1
port=5432
```

Never place administrator or application passwords in a command argument, committed file, report, terminal transcript or issue. `.env` must remain Git-ignored and mode `0600`.

## 1. Bootstrap

Read the complete administrator DSN without terminal echo, then bootstrap the least-privileged application role. The administrator is bootstrap-only.

```bash
read -r -s MARKET_REGIME_ALPHA_ADMIN_DATABASE_URL
export MARKET_REGIME_ALPHA_ADMIN_DATABASE_URL
uv run python scripts/bootstrap_postgres.py --env-file .env
unset MARKET_REGIME_ALPHA_ADMIN_DATABASE_URL
```

The command creates or verifies the role/database/schema, generates a fresh application password and stores only `MARKET_REGIME_ALPHA_DATABASE_URL` in `.env`. Existing resources with foreign ownership or unsafe role attributes fail closed.

## 2. Apply and verify migrations

```bash
set -a
source .env
set +a
uv run python scripts/apply_postgres_migrations.py
uv run python scripts/apply_postgres_migrations.py --verify-only
```

Both commands must report the packaged migration count, latest version, server version, schema and catalog table count without rendering the DSN.

## 3. Stop SQLite writers and inventory sources

Before a non-empty import:

1. stop every process that can write the declared SQLite files;
2. require absolute source paths and no active `-wal` or `-journal` sidecar;
3. enumerate only SQLite authority tables—never DuckDB/Parquet/CSV/Artifact files;
4. calculate each source file and selected-schema hash;
5. create a manifest matching `sqlite-to-postgres-migration-manifest-v1`;
6. independently confirm that the PostgreSQL business tables are empty.

The repository's approved initial manifest is `config/postgres/initial-sqlite-migration-manifest.json`. It has no sources because repository discovery found no SQLite business database. Its successful report is therefore schema-only `0 -> 0` evidence, not proof that external or undiscovered data was migrated.

## 4. Capture the pre-write backup

Set an explicit absolute path outside the repository. Do not use a broad directory or overwrite an unresolved target.

```bash
export MRA_POSTGRES_BACKUP_PATH=/absolute/operator-controlled/market-regime-alpha-prewrite.dump
test ! -e "$MRA_POSTGRES_BACKUP_PATH"
pg_dump --dbname="$MARKET_REGIME_ALPHA_DATABASE_URL" --format=custom --file="$MRA_POSTGRES_BACKUP_PATH"
pg_restore --list "$MRA_POSTGRES_BACKUP_PATH" >/dev/null
shasum -a 256 "$MRA_POSTGRES_BACKUP_PATH"
```

Keep the dump and its digest outside tracked paths with operator-controlled permissions.

## 5. Execute the one-time import

```bash
uv run python scripts/migrate_sqlite_to_postgres.py --manifest config/postgres/initial-sqlite-migration-manifest.json --output-root artifacts/postgres-migration
```

The importer holds SQLite read snapshots, rechecks source hashes, requires every PostgreSQL business table to be empty, uses one PostgreSQL transaction, copies tables in foreign-key order, repairs identity sequences, compares counts/primary-key ranges/canonical row digests, verifies canonical JSON and publishes a content-addressed report only after success.

Any source change, schema mismatch, unsupported table, non-empty target, constraint failure, digest mismatch or injected pre-commit fault rolls back the import and publishes no PASS report.

## 6. PostgreSQL integration smoke

Use isolated schemas in the dedicated local database; never point tests at another environment.

```bash
export MARKET_REGIME_ALPHA_TEST_DATABASE_URL="$MARKET_REGIME_ALPHA_DATABASE_URL"
uv run pytest -q tests/persistence/postgres
uv run pytest -q tests/platform tests/decision tests/portfolio tests/execution tests/position
uv run pytest -q tests/application/daily_loop tests/features tests/application/canonical_lifecycle tests/application/controlled_operation
```

These tests cover migrations, Governance, Decision, Portfolio/Risk, manual execution without an invented Fill, Daily/Feature/Canonical/Controlled journals, restart/replay, fencing and longitudinal reads. They are isolated local engineering evidence, not sustained operational evidence.

## 7. Runtime selection

Ordinary CLIs load PostgreSQL from `.env` or `MARKET_REGIME_ALPHA_DATABASE_URL`. `--database-url` is an explicit PostgreSQL override. SQLite requires `--sqlite-database /absolute/path.sqlite3`; old `--database`/`--journal` flags remain hidden compatibility aliases and never identify PostgreSQL.

Missing or conflicting configuration fails closed. A stored PostgreSQL run binding records backend plus a credential-free database/schema locator. Resume and replay reject missing or mismatched bindings.

## 8. Rollback and forward repair

Before the first PostgreSQL authority write, rollback may explicitly select the unchanged SQLite source only when the migration report still proves source/target equality:

```bash
uv run python -m market_regime_alpha.cli.run_canonical_lifecycle --sqlite-database /absolute/verified-source.sqlite3 --help
```

After any new PostgreSQL authority write, do not return to a stale SQLite database. Recovery is PostgreSQL restore or a reviewed forward migration:

```bash
export MRA_POSTGRES_RESTORE_PATH=/absolute/operator-controlled/verified.dump
pg_restore --list "$MRA_POSTGRES_RESTORE_PATH" >/dev/null
createdb market_regime_alpha_restore_verification
pg_restore --exit-on-error --clean --if-exists --dbname=market_regime_alpha_restore_verification "$MRA_POSTGRES_RESTORE_PATH"
```

Restore verification uses a separate explicitly named database. Replacing the authority database, deleting data or dropping resources requires a separate approved recovery action. Migration checksum drift is repaired only by a new forward migration; never edit an applied migration.

## 9. Final gate

```bash
git diff --check
uv run python scripts/check_docs_links.py
uv run pytest -q tests/scripts/test_check_docs_links.py
uv run pytest -q tests/platform
uv run pytest -q
uv run ruff check .
uv run mypy
uv run python -m build
```

Record every command as `PASS`, `FAIL`, `NOT_RUN` or `BLOCKED` and bind the result to the exact tested Git SHA. Remote CI is separate evidence and must not be claimed before the exact-SHA run is green.
