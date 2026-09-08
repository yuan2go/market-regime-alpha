# WP-ARCHITECTURE-REFOUNDATION-02 Pre-Refoundation Verification Baseline

> **Status:** HISTORICAL
> **Authority:** Immutable exact-SHA engineering verification record; not business or qualification Authority
> **Owner:** Market Regime Alpha maintainers
> **Executed At:** 2026-08-27
> **Verified SHA:** `d0d1f3152a20f1a3f4f9b8a1d9c4383a49162fb7`
> **Business Implementation Parent:** `0382dad416d6d50d1eea0bda1603d7c359d65274`
> **Code Evidence:** `pyproject.toml`, `uv.lock`, `scripts`, `src/market_regime_alpha`, `tests`

This baseline was executed in a clean isolated worktree before Repository
Governance edits. It freezes the behavior that must remain explainable while the
target replaces current owners. It does not require the target to preserve old
module/table identity.

## Environment

| Component | Observed value |
|---|---|
| macOS Python | 3.12.2 |
| uv | 0.11.7 |
| PostgreSQL | 16.14 Homebrew |
| Test database | dedicated empty local database; no business database used |
| Source tree | `13e8922bb42a0054a2f168eac5ce3ab61f5694ed` |
| Migration tree | `6d3730548780ad6244d2cfecb4fb3559064b6f06` |
| Test tree | `7c525ee274be34d9cae7dbe1d76c700d9f21a54c` |

## Validation ledger

| Check | Result | Evidence |
|---|---|---|
| `uv sync --frozen --extra dev --extra postgres` | **PASS** | clean `.venv`; 61 packages installed from frozen lock/project metadata |
| `python scripts/check_docs_links.py` | **PASS** | canonical documentation inventory, metadata and links OK |
| `python -m pytest -q tests/scripts/test_check_docs_links.py` | **PASS** | 7 tests |
| `python -m pytest -q tests/platform` | **PASS** | 33 tests |
| `python -m pytest -q` | **PASS** | exit 0 and 100% progress; separate collection counted 3,034 tests; no failure/error/skip marker |
| first `apply_postgres_migrations.py` against a nonexistent application schema | **FAIL** | `InsufficientPrivilege: permission denied to create pg_catalog.schema_migrations`; `search_path` silently fell through because the schema was absent |
| explicit empty schema → apply packaged migrations | **PASS** | newly applied versions 001–106, migration count/head 106, expected table count 283 |
| `apply_postgres_migrations.py --verify-only` | **PASS** | zero newly applied versions; checksums/head/schema verified |
| direct catalog query | **PASS** | `schema_migrations max/count = 106/106`; base tables = 283 |
| `tests/persistence/postgres/test_schema.py tests/persistence/postgres/test_migrator.py` | **PASS** | 40 tests, including clean schema, forward upgrades, checksums, idempotency and concurrent migrators |
| focused Runtime/replay/recovery/idempotency command | **PASS** | 90 tests across Canonical Lifecycle, Continuous Research, Daily journal, Feature materialization and PostgreSQL Runtime owners |
| `python -m ruff check .` | **PASS** | all checks passed |
| `python -m mypy` | **PASS** | no issues in 423 source files |
| `python -m build` | **PASS** | sdist and wheel built; generated `dist/` was removed from repository scope |
| `git diff --check` | **PASS** | exact-SHA worktree remained free of tracked changes before governance edits |

No assertion was weakened, no test was skipped/xfail-added, and no compatibility
code was introduced. The initial bootstrap failure is retained because it is a
real existing contract gap, not a transient test failure.

## Focused Runtime test scope

The exact 90-test selection was:

```bash
python -m pytest -q \
  tests/application/canonical_lifecycle/test_commands.py \
  tests/application/canonical_lifecycle/test_postgres_repository.py \
  tests/application/canonical_lifecycle/test_replay.py \
  tests/application/canonical_lifecycle/test_runner_recovery.py \
  tests/application/continuous_research/test_journal_contract.py \
  tests/application/continuous_research/test_replay.py \
  tests/application/continuous_research/test_runner_recovery.py \
  tests/application/continuous_research/test_scheduler.py \
  tests/application/daily_loop/test_runtime_journal.py \
  tests/features/test_feature_replay.py \
  tests/features/test_materialization_crash_recovery.py \
  tests/features/test_materialization_run_hardening.py \
  tests/persistence/postgres/test_continuous_research_journal.py \
  tests/persistence/postgres/test_historical_research_runner.py \
  tests/persistence/postgres/test_runtime_concurrency.py
```

It covered:

- semantic command hashes and idempotency-key conflicts;
- canonical durable replay and source tamper detection;
- resume after failed/interrupted stages;
- PostgreSQL create-or-get concurrency and stale writer fencing;
- Continuous Research journal claim/lease/retry/replay/recovery;
- scheduler restart and concurrent reservation;
- Daily Runtime journal idempotency and restart;
- Feature replay, crash atomicity, lease heartbeat and monotonic fence;
- PostgreSQL Runtime concurrency and Historical runner resume/replay.

## Interpretation and ceiling

The verified pre-refoundation implementation is locally reproducible on a clean
PostgreSQL 16 database. This is the deletion baseline for behavior and invariant
comparison. It is not evidence that:

- `MRA_REFOUNDATION_1` or the target 91-table baseline exists;
- any target bounded context is implemented or canonically wired;
- the existing schema bootstrap is safe for a missing/legacy/mismatched schema;
- a Provider is PIT/finality qualified;
- Alpha, Formal OOS, sustained Prospective value, broker integration, trading,
  or Production is established.

The missing-schema failure is an accepted Foundation implementation obligation.
It does not block starting Foundation because the approved target already
requires an explicit epoch/catalog preflight and clean schema bootstrap.
