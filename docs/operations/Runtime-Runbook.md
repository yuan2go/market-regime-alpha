# Runtime Runbook

> **Status:** CURRENT_STATUS
> **Authority:** Current executable operator procedures
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-10
> **Code Evidence:** `pyproject.toml`, `scripts/*.py`, installed CLI modules

## Install and verify environment

```bash
uv sync --frozen --extra dev --extra postgres
uv run continuous-research --help
uv run model-governance --help
uv run pit-authority --help
```

## PostgreSQL Authority Only

Bootstrap a dedicated local authority only with an administrator URL:

```bash
uv run python scripts/bootstrap_postgres.py \
  --admin-database-url "$MARKET_REGIME_ALPHA_ADMIN_DATABASE_URL" \
  --dry-run
uv run python scripts/bootstrap_postgres.py \
  --admin-database-url "$MARKET_REGIME_ALPHA_ADMIN_DATABASE_URL"
```

Apply or verify the packaged schema:

```bash
uv run python scripts/apply_postgres_migrations.py
uv run python scripts/apply_postgres_migrations.py --verify-only
```

Expected head: migration 046, `close_reference_only_qualification`. Expected schema catalog: 148 tables. Missing/unreachable PostgreSQL is a blocked operation; there is no alternate persistent backend.

## Canonical Runtime

Inspect required arguments before scheduling:

```bash
uv run continuous-research run-due --help
uv run continuous-research inspect-run --help
uv run continuous-research replay --help
```

The command must use an explicit database URL/schema or the ignored `.env` authority. `run-due` is the canonical all-day entry. The six `*-free-data-operation` commands operate one bounded Controlled Operation and do not replace the scheduler.

Free data may run only in `RESEARCH` or `SHADOW`. A Production request must fail with `FREE_DATA_PRODUCTION_AUTHORITY_DENIED`. Do not edit status rows, receipts or hashes to recover a run; resume through the owning journal.

## Authority administration

```bash
uv run state-system --help
uv run decision-system --help
uv run model-governance --help
uv run pit-authority --help
uv run research-shadow --help
```

`decision-system` is manual-account decision support. It requires current PostgreSQL model selection; Production qualification is currently forced closed. `research-shadow` freezes research decisions and outcomes, not simulated fills. Strategy Shadow currently has no installed CLI.

## Validation

```bash
uv run python scripts/check_docs_links.py
MARKET_REGIME_ALPHA_TEST_DATABASE_URL="$TEST_DATABASE_URL" uv run pytest -q
uv run ruff check .
uv run mypy
uv run python -m build
git diff --check
```

PostgreSQL tests never skip. Use a disposable database and the isolated schemas created by test fixtures. Never point tests at a production database.
