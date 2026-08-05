# PostgreSQL Authority Migration Evidence

> **Status:** CURRENT_STATUS
> **Authority:** Commit-bound local bootstrap, migration and cutover observations
> **Owner:** Market Regime Alpha maintainers
> **Observed:** 2026-08-05
> **Related Documents:** ../operations/PostgreSQL-Authority-Runbook.md, ../status/Current-State.md, ../superpowers/specs/2026-08-05-postgresql-authority-migration-design.md, ../superpowers/plans/2026-08-05-postgresql-authority-migration.md

## Evidence boundary

This record proves local PostgreSQL persistence engineering only. It does not prove production deployment, sustained Shadow operation, formal PIT/OOS data, model validity, operator authentication, Broker integration or trading authority.

The migration report is bound to code commit `7366ab326c2333d4f6eaefbe0a443b588d0e15b1`. Documentation and final-gate commits after that checkpoint must be validated separately at their exact HEAD.

## Bootstrap and catalog observation

Observed against the approved local authority without printing a DSN or credential:

```text
PostgreSQL server = 16.14 (Debian 16.14-1.pgdg12+1)
role = market_regime_alpha
role attributes = LOGIN, NOSUPERUSER, NOCREATEDB, NOCREATEROLE, NOREPLICATION
database owner = market_regime_alpha
schema owner = market_regime_alpha
search_path = market_regime_alpha, pg_catalog
applied migrations = 17 of 17
catalog tables = 58
non-empty business/runtime tables before import = 0
```

The administrator account was used only during bootstrap. The generated application credential exists only in the Git-ignored mode-`0600` `.env` and is absent from this evidence.

## Source discovery and import

Repository discovery found no SQLite `.sqlite`, `.sqlite3` or `.db` business authority under the repository, `artifacts/` or `data/` scope. The approved manifest is `config/postgres/initial-sqlite-migration-manifest.json`, with zero sources.

The schema-only import produced:

```text
result = PASS
source_count = 0
source_row_count = 0
target_row_count = 0
table_count = 0
manifest_hash = sha256:934f17ca757e1fcad20ceac56257e5fa584dc708efeef55f5599161287fe11c0
report_id = postgres-migration-0a6091e24ab31b2014697157
report_hash = sha256:0a6091e24ab31b20146971576a3636b5734f08b1eb9b44aaa014814c3f1fc59b
report_file_sha256 = d24ea6aef8ed9181658436a1b2299b2ca2b50cae8195fb2ee32b6368bc57f469
```

This is explicitly `0 -> 0` evidence. It does not claim that undiscovered, external, DuckDB, Parquet, CSV or immutable Artifact data was migrated.

## Pre-write backup

A PostgreSQL 16 custom-format dump was captured outside tracked paths and its archive list was verified:

```text
backup_format = pg_dump custom
pg_restore_list = PASS
backup_sha256 = 12c80e9de18bdfcd53ed8a1937216e7363ac68a3efe603766ab3726244ec5f14
tracked_in_git = false
```

The transient local path is intentionally omitted from authority evidence. Operators must store retained backups in an approved external location.

## Focused verification at the migration checkpoint

```text
PostgreSQL migration/catalog tests = PASS
PostgreSQL Repository parity suites = PASS
Canonical/Feature/Daily lifecycle parity = PASS
Controlled Operation/Longitudinal parity = PASS
CLI PostgreSQL-default and explicit SQLite compatibility = PASS
SQLite manifest/import/report tests = 10 passed
Ruff focused scope = PASS
mypy persistence/import scope = PASS
```

The pre-final cutover worktree based on `7366ab326c2333d4f6eaefbe0a443b588d0e15b1` then observed:

```text
FROZEN_UV_SYNC_DEFAULT_DEV_POSTGRES = PASS
DOCUMENT_AUTHORITY_AND_LINKS = PASS
DOCS_TESTS = 8 passed
PLATFORM_TESTS = 23 passed
FULL_PYTEST = PASS, 2234 tests collected, 6 existing pandas PerformanceWarnings
RUFF = PASS
MYPY = PASS, 338 source files
PACKAGE_BUILD = PASS, sdist and wheel
GIT_DIFF_CHECK = PASS
```

An exact-commit rerun is required after the checkpoint containing this evidence. Remote CI is separate and is not claimed here.

## Authority ceiling

```text
POSTGRESQL_DEFAULT_RUNTIME = true
SQLITE_EXPLICIT_COMPATIBILITY_ONLY = true
DUAL_WRITE = false
AUTOMATIC_FALLBACK = false
FORMAL_PIT_ESTABLISHED = false
FORMAL_OOS_ALPHA_ESTABLISHED = false
SHADOW_READY = false
OPERATOR_AUTHENTICATION_ESTABLISHED = false
BROKER_INTEGRATION_PROVEN = false
AUTOMATIC_ORDER_EXECUTION = false
PRODUCTION_READY = false
```
