# Market Regime Alpha

> **Status:** CURRENT_STATUS
> **Authority:** Repository entry point only
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-28
> **Related Documents:** `docs/README.md`, `docs/architecture/Canonical-Overall-Design.md`, `docs/status/Current-State.md`, `docs/status/Roadmap.md`

Market Regime Alpha is an A-share research operating system and
human-in-the-loop decision-support platform. It is not unattended live trading.

The repository is in an approved Hard Cutover Architecture Re-foundation:

- **Target:** context-first modular monolith, one PostgreSQL Authority, one
  composition root, one Runtime, and a new `MRA_REFOUNDATION_1` schema epoch.
- **Current implementation:** the pre-refoundation Python packages, 001–106
  migrations, 283-table PostgreSQL schema, and existing Continuous Research
  Runtime.

The Target is approved but not implemented. Current code/schema/tests decide
current behavior until an explicit Runtime/CLI cutover.

Start with [Documentation Authority](docs/README.md), then read the
[Canonical Target Architecture](docs/architecture/Canonical-Overall-Design.md),
[Current State](docs/status/Current-State.md), and
[Implementation Roadmap](docs/status/Roadmap.md).

## Development gate

```bash
uv sync --frozen --extra dev --extra postgres
uv run python scripts/check_docs_links.py
uv run python -m pytest -q tests/scripts/test_check_docs_links.py
uv run python -m pytest -q tests/platform
MARKET_REGIME_ALPHA_TEST_DATABASE_URL="postgresql://HOST/TEST_DATABASE" uv run python -m pytest -q
uv run python -m ruff check .
uv run python -m mypy
uv run python -m build
git diff --check
```

Use a dedicated PostgreSQL 16 test database. Missing PostgreSQL fails closed;
tests use isolated schemas. Local/fixture success does not establish Provider,
Alpha, broker, trading, or Production qualification.
