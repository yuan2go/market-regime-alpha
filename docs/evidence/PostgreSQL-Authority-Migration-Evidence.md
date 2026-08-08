# PostgreSQL Authority Only and Decision Closure Evidence

> **Status:** CURRENT_STATUS
> **Authority:** Exact-worktree local engineering observations
> **Owner:** Market Regime Alpha maintainers
> **Observed:** 2026-08-06
> **Start Commit:** `547ddfba39df155a8b53611e1ce9200bf789de60`
> **Related Documents:** ../operations/PostgreSQL-Authority-Runbook.md, ../operations/Daily-Decision-System-Runbook.md, ../status/Current-State.md

## Evidence boundary

This record proves local code, fixture, PostgreSQL integration, concurrency and
PostgreSQL replay mechanics only. It does not prove Formal PIT, Formal OOS
Alpha, model profitability, sustained Free Live or Shadow operation,
production-qualified PostgreSQL, authenticated operators, Broker integration
or trading authority.

## Baseline

The requested start commit was observed on `feat/continuous-research-runtime`.
An isolated loopback-only PostgreSQL 16.14 cluster was initialized with UTF-8
encoding; tests did not connect to or modify an unknown local business database.

```text
Python = 3.12.2
uv = 0.11.7
PostgreSQL = 16.14
start migrations = 001-023
start full pytest = 2430 passed, 0 failed, 0 skipped, 6 warnings, 8 subtests, 241.18s
start docs/Ruff/mypy/build/diff = PASS
```

Repository and bounded user-directory discovery found no real file-database
business authority requiring retention. The former schema-only import inventory
was `0 -> 0`; it did not prove migration of external or undiscovered data and
did not justify retaining a runtime importer.

## PostgreSQL-only implementation

The current executable call chain is:

```text
Application / Domain
→ bounded Repository Protocol
→ native psycopg PostgreSQL Repository
→ PostgreSQL 16
```

The file-database repositories, local schemas/migrations, backend factory
branches, connection adapter, DB-API/SQL translation bridge, replay path,
integration tests, CLI/environment switches and long-lived importer were
removed. `DatabaseSettings` and `RepositoryFactory` admit PostgreSQL only and
fail closed when it is unavailable.

Central migrations are now 001–025. Migration 024 constrains current runtime
bindings to PostgreSQL while preserving the published migration-017 checksum.
Migration 025 adds Manual Account, Reconciliation, Daily Summary/Candidates,
Research Portfolio/lines, Independent Risk and Decision Runtime receipts.

Native repositories use psycopg binding, PostgreSQL transactions, `ON
CONFLICT`, `RETURNING`, `TIMESTAMPTZ`, `BOOLEAN`, `NUMERIC`, `JSONB`, row or
aggregate-scoped locks, CAS, fencing and partial terminal uniqueness. Tests and
replay use randomly isolated PostgreSQL schemas.

## Decision closure

```text
Continuous Runtime STATE_SYSTEM
→ Daily Summary Preview
→ Manual Account Observation
→ Fill-derived Reconciliation
→ Research Portfolio Proposal
→ independently reloaded Risk Decision
→ immutable Daily Summary Final/Correction
```

The window is 14:30–14:55 Asia/Shanghai, not an exact-point task. The original
Final is unique and immutable; a Correction appends another revision.
Observation, Reconciliation, Portfolio and Risk do not create or mutate an
Opportunity, ManualTrade, Order, Fill or Position. Unresolved account lineage
or differences block OPEN/ADD. Independent Risk reloads PostgreSQL authority by
identity and does not trust caller-supplied proposal derivations.

## Local worktree gate before checkpoint commit

The complete local worktree was verified against the isolated PostgreSQL 16.14
authority before the checkpoint commit:

```text
FROZEN_UV_SYNC_DEFAULT_DEV_POSTGRES = PASS, 78 packages checked
DOCUMENT_AUTHORITY_AND_LINKS = PASS
DOCS_TESTS = PASS, 8 passed
FULL_PYTEST_WITH_POSTGRES = PASS, 2426 passed, 0 failed, 0 skipped
PYTEST_WARNINGS = 6 existing pandas PerformanceWarnings
PYTEST_SUBTESTS = 8 passed
PYTEST_DURATION = 406.68 seconds
POSTGRESQL_MIGRATIONS = PASS, 001-025 fresh and 023-025 upgrade
POSTGRESQL_REPOSITORY_REPLAY_CONCURRENCY = PASS
RUFF = PASS
MYPY = PASS, 364 source files
PACKAGE_BUILD = PASS, sdist and wheel
PACKAGE_FILE_DATABASE_BACKEND_SCAN = PASS, no executable match
GIT_DIFF_CHECK = PASS
REMOTE_CI = NOT_RUN
```

The checkpoint commit and final clean-worktree verification are recorded in the
delivery report. Remote CI is not claimed because this work was not pushed.

## Authority ceiling

```text
POSTGRESQL_ONLY_RUNTIME = true
AUTOMATIC_DATABASE_FALLBACK = false
FORMAL_PIT_ESTABLISHED = false
FORMAL_OOS_ALPHA_ESTABLISHED = false
SHADOW_READY = false
BROKER_INTEGRATION_PROVEN = false
AUTOMATIC_ORDER_EXECUTION = false
PRODUCTION_READY = false
```
