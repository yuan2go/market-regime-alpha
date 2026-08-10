# Runtime Runbook

> **Status:** CURRENT_STATUS
> **Authority:** Current executable operator procedures
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-10
> **Code Evidence:** `pyproject.toml`, `scripts/*.py`, `src/market_regime_alpha/cli`

## Install and verify environment

```bash
uv sync --frozen --extra dev --extra postgres
uv run continuous-research --help
uv run continuous-research run-day --help
uv run continuous-research settle-day --help
uv run continuous-research strategy-day --help
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

Expected head: migration 047, `free_historical_evidence_registry`. Expected schema catalog: 148 tables. Migration 047 adds retrospective free Decision/Outcome artifact kinds and an immutable Strategy Shadow liquidity-observation owner kind; migration 046's qualification and Production constraints remain unchanged and fail-closed. Missing/unreachable PostgreSQL is a blocked operation; there is no alternate persistent backend.

Migration 046 intentionally stops if an existing database contains reference-only qualified Validation or Historical Sample rows. Do not update or delete those append-only rows in place. Preserve/export the database, audit the owning evidence, and use a separately reviewed forward-repair migration before retrying 046.

## Canonical Runtime

Inspect required arguments before scheduling:

```bash
uv run continuous-research run-due --help
uv run continuous-research run-day --help
uv run continuous-research settle-day --help
uv run continuous-research strategy-day --help
uv run continuous-research report-day --help
uv run continuous-research replay-day --help
uv run continuous-research inspect-run --help
uv run continuous-research replay --help
```

Every command requires an explicit database URL/schema. `run-due` remains the
canonical tick operation. `run-day` invokes that same operation and, for a
completed `SHADOW` run, resolves its PostgreSQL Summary and freezes Research
Shadow. Before a due Research/Shadow decision it also attempts the bounded
BaoStock Historical Sample build. No samples remains a valid fail-closed
Forecast result. An already-available `UNQUALIFIED` Registry Dataset permits an
exploratory, uncalibrated Forecast. Production never receives that provider.

The free-data operational sequence is:

```text
continuous-research run-day ...
continuous-research settle-day \
  --trading-date YYYY-MM-DD --next-session-date YYYY-MM-DD \
  --artifact-root ARTIFACT_ROOT --at RFC3339
continuous-research strategy-day --observations OBSERVATION_JSON
continuous-research report-day --trading-date YYYY-MM-DD --at RFC3339
continuous-research replay-day --trading-date YYYY-MM-DD
```

`settle-day` resolves the frozen Controlled package, Candidate, Dynamic Pool and
Research Shadow IDs from PostgreSQL and acquires BaoStock five-minute OHLC after
close for both current and missed sessions. It writes Outcome, Targeted Outcome,
Panel V2 and Factor Enrichment artifacts. Tencent last-price snapshots remain
runtime context and are never promoted to factual OHLC/barrier evidence. Once
factual settlement exists, retries reload its PostgreSQL-owned identities and
immutable packages without calling the Provider again.

`strategy-day` resolves the settled Research Shadow, Panel and Candidate from
PostgreSQL. Its observation file contains only operator facts: trading date,
optional selected symbol, intended quantity/reference price, fillability,
optional observed shadow fill, holding/exit observations and an observed-at
timestamp. It advances only the isolated Strategy Shadow ledger.

All four day commands are duplicate-safe and resume partial owner journals on
reinvocation. Strategy Shadow reloads immutable Entry/Fill/Position owner rows
and can advance later Holding/Exit observations until Outcome settlement.
`resume --run-id` releases recoverable Continuous Runtime state;
`replay`, `strategy-replay` and `replay-day` verify owner histories without
creating real trading state. Provider failures leave earlier immutable
PostgreSQL evidence intact. Lease/fence or CAS conflicts fail closed and must be
retried through the same command and identifiers.

Free data may run only in `RESEARCH` or `SHADOW`. A Production request must fail with `FREE_DATA_PRODUCTION_AUTHORITY_DENIED`. Do not edit status rows, receipts or hashes to recover a run; resume through the owning journal.

## Authority administration

```bash
uv run state-system --help
uv run decision-system --help
uv run model-governance --help
uv run pit-authority --help
uv run research-shadow --help
```

`decision-system` is manual-account decision support. It requires current PostgreSQL model selection; Production qualification is currently forced closed. `research-shadow` freezes research decisions and outcomes, not simulated fills. Strategy Shadow is exposed only as subcommands of `continuous-research`; there is no duplicate installed CLI.

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
