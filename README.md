# Market Regime Alpha

> **Status:** CURRENT_STATUS
> **Authority:** Repository entry point
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-10
> **Related Documents:** `docs/README.md`, `docs/status/Current-State.md`, `docs/architecture/System-Architecture.md`

Market Regime Alpha is an A-share Alpha Research Operating System and human-in-the-loop trading decision-support platform. It is not an unattended live-trading system.

```text
Data / Evidence
-> Dataset / Feature
-> Market / ETF / Theme / Capital State
-> Dynamic Pool / Candidate
-> Signal / PathForecast
-> Research Summary / Shadow / Outcome
-> Research and Strategy Validation
-> human decision support
```

The implementation is a PostgreSQL-only modular monolith. `continuous-research run-due` is the single canonical all-day Runtime. Actual positions derive only from observed manual fills. Free public data remains exploratory, Production qualification is closed, and no broker writer exists.

Start with [Documentation Authority](docs/README.md), then read [System Architecture](docs/architecture/System-Architecture.md), [Authority Map](docs/architecture/Authority-Map.md), [Current State](docs/status/Current-State.md) and the [Runtime Runbook](docs/operations/Runtime-Runbook.md).

## Development

```bash
uv sync --frozen --extra dev --extra postgres
uv run python scripts/check_docs_links.py
MARKET_REGIME_ALPHA_TEST_DATABASE_URL="$TEST_DATABASE_URL" uv run pytest -q
uv run ruff check .
uv run mypy
uv run python -m build
git diff --check
```

PostgreSQL 16 is the only persistent authority. Missing or unreachable PostgreSQL fails closed; tests use isolated schemas and never skip core Authority integration.
