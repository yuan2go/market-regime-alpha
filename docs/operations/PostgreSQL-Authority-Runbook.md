# PostgreSQL Authority Only Runbook

> **Status:** CURRENT_SPECIFICATION
> **Scope:** Runtime, Journal, Replay, repositories, CLI integration, account, position and risk authority
> **Authority ceiling:** RESEARCH / MANUAL_DECISION_SUPPORT
> **Database:** PostgreSQL 16 only

## 1. Invariant

The executable database chain is:

```text
Application / Domain
→ bounded Repository Protocol
→ native psycopg PostgreSQL Repository
→ PostgreSQL 16
```

There is no database backend selector, file-database path, compatibility bridge,
SQL translation layer, automatic fallback or persistent test substitute. An
unavailable PostgreSQL authority fails closed as `DATABASE_UNAVAILABLE` or
`PostgresConnectionUnavailable`.

Immutable file Artifacts, Parquet and CSV interchange files are evidence or
transport formats. They are not Runtime, Journal, account, position or risk
databases. Research caches cannot claim operational authority.

## 2. Bootstrap an explicit database

Use a dedicated PostgreSQL 16 database. Never point tests or replay at an
unknown business database.

```bash
export MARKET_REGIME_ALPHA_DATABASE_URL='postgresql://USER:PASSWORD@127.0.0.1:5432/market_regime_alpha'
export MARKET_REGIME_ALPHA_DATABASE_SCHEMA='market_regime_alpha'
uv run python scripts/bootstrap_postgres.py
uv run python scripts/apply_postgres_migrations.py
```

The URL must include a host and database. CLI arguments can override both
values explicitly:

```bash
uv run continuous-research \
  --database-url "$MARKET_REGIME_ALPHA_DATABASE_URL" \
  --application-schema "$MARKET_REGIME_ALPHA_DATABASE_SCHEMA" \
  report --run-id RUN_ID
```

Decision System commands deliberately require an explicit URL:

```bash
uv run decision-system \
  --database-url "$MARKET_REGIME_ALPHA_DATABASE_URL" \
  --database-schema "$MARKET_REGIME_ALPHA_DATABASE_SCHEMA" \
  inspect-manual-account --observation-id OBSERVATION_ID
```

## 3. Migration

Migrations are contiguous PostgreSQL SQL under
`src/market_regime_alpha/persistence/postgres/migrations`.

```bash
uv run python scripts/apply_postgres_migrations.py
```

The current sequence is 001–042:

- 001–023: historical PostgreSQL authorities through Stateful Research;
- 024: current runtime binding is constrained to `backend = 'postgres'`;
- 025: Daily Decision, Manual Account, Reconciliation, Research Portfolio,
  Independent Risk and Decision Runtime receipt authorities.
- 026: lease-bound Decision receipts, immutable State-stage and frozen
  Fill-account references, versioned Risk/Tolerance configurations and isolated
  replay imports.
- 027–033: Model Governance, PIT, Summary V3, State ownership and recoverable
  Candidate authority.
- 034–037: Pre-live Shadow Session, factual Outcome, Evaluation V1 and
  ETF/Theme reference authority.
- 038–042: cross-session State Policy/Series, multi-horizon Target Protocol,
  Prospective Evidence Attestation, Evaluation Panel V2 and frozen Decision
  State Policy lineage.

Published migrations are immutable. Migration 024 supersedes the historical
binding vocabulary in 017 without editing its checksum. Both an empty-database
001→042 apply and incremental upgrade from the actual prior head must pass.

Migration 026 preserves rows written by the prerelease v1 Decision payloads
without rewriting their immutable identities. Legacy v1 Runtime receipts remain
archival with a null Lease field; all new receipts require the v2 schema and an
active Lease window. New configuration foreign keys are `NOT VALID`, preserving
historical rows while enforcing references for new writes. Both 023→026 and an
empty 001→026 apply are supported.

## 4. Transaction and concurrency rules

- bind every value with psycopg parameters;
- use `ON CONFLICT`, `RETURNING`, native `BOOLEAN`, `TIMESTAMPTZ`, `NUMERIC`
  and `JSONB` where the contract calls for them;
- acquire transaction advisory locks only for the aggregate scope whose next
  revision is being assigned;
- claim queued work with row locking and `SKIP LOCKED` only where the Journal
  contract includes recovery;
- validate Claim ID, fencing token, tick version and lease expiration in the
  same transaction as each Decision write;
- use unique/partial indexes for terminal identity and compare-and-set for
  revision chains;
- never serialize the entire schema for an ordinary account, tick or trading
  date operation.

## 5. Backup, recovery and replay

Backup and restore use normal PostgreSQL 16 tooling. A restore target must be a
new validated database or an explicitly selected recovery database.

```bash
pg_dump --format=custom --file=market-regime-alpha.dump "$MARKET_REGIME_ALPHA_DATABASE_URL"
createdb market_regime_alpha_restore
pg_restore --clean --if-exists --dbname=market_regime_alpha_restore market-regime-alpha.dump
```

Replay uses an isolated PostgreSQL database or schema:

```text
Immutable Artifact / authority identities
→ frozen Fill-derived account view at the original as-of
→ optional content-addressed T+1 calendar/session settlement evidence
→ isolated PostgreSQL schema
→ apply 001–042
→ restore/import explicitly bound identities
→ re-execute Reconciliation, Portfolio and independent Risk
→ reload every Risk authority input from the isolated PostgreSQL import
→ verify terminal identity, hashes and lineage
→ drop isolated schema
```

Repository, migration, runtime, concurrency, CLI and replay tests require
`MARKET_REGIME_ALPHA_TEST_DATABASE_URL`. Absence is an error, not a skip.
Each test uses a randomly named schema. Path-shaped legacy test inputs are
opaque scope keys mapped to bounded PostgreSQL schemas; no file database is
created.

## 6. Local qualification gate

```bash
uv sync --frozen --extra dev --extra postgres
uv run python scripts/check_docs_links.py
MARKET_REGIME_ALPHA_TEST_DATABASE_URL="$TEST_DATABASE_URL" uv run pytest
uv run ruff check .
uv run mypy
uv run python -m build
git diff --check
```

Record collected, passed, failed, skipped, warnings, duration, PostgreSQL
integration, migration, replay and concurrency counts. A green local gate is
engineering evidence only; it is not Formal PIT, OOS, Shadow, production or
trading authorization evidence.

## 7. Failure handling

When PostgreSQL is unavailable:

1. stop the operation;
2. emit a credential-safe database-unavailable error;
3. do not create a local persistence substitute;
4. restore service or select an explicitly provisioned PostgreSQL recovery
   database;
5. resume only through the Journal/Claim/fencing protocol.

Forward repair must be a new reviewed migration. Do not edit an applied
migration, rewrite authority history, fabricate a Fill, or directly modify a
Position.

## 8. Non-claims

PostgreSQL Authority Only does not prove model profitability, Formal PIT,
Formal OOS Alpha, sustained Shadow operation, broker truth or production
readiness. Entry remains blocked and this runbook grants no QMT, PTrade,
XtQuant, Broker, Order, cancellation or automatic execution authority.
