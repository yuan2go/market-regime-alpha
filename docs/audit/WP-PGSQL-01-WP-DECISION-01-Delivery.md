# WP-PGSQL-01 / WP-DECISION-01 Delivery Evidence

> **Status:** CURRENT_STATUS
> **Authority:** Local implementation and test evidence
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-06
> **Evidence Commit:** `8b5007b79e83b0988466621cabe4b5557c7b4f1a`
> **Related Documents:** WP-PGSQL-01-SQLite-Inventory.md, ../operations/PostgreSQL-Authority-Runbook.md, ../operations/Daily-Decision-System-Runbook.md

## 1. Baseline and final checkpoint

| Item | Start | Final implementation checkpoint |
| --- | --- | --- |
| Branch | `feat/continuous-research-runtime` | `feat/continuous-research-runtime` |
| Commit | `547ddfba39df155a8b53611e1ce9200bf789de60` | `8b5007b79e83b0988466621cabe4b5557c7b4f1a` |
| Local `origin/main` | `8de820cd149278bfebbaf18f150a90f36380176d` | unchanged |
| Python under uv | 3.12.2 | 3.12.2 |
| uv | 0.11.7 | 0.11.7 |
| PostgreSQL | 16.14 | 16.14 |
| Packaged migrations | 001–023 | 001–026 |
| Full pytest | 2,430 passed; 0 skipped; 6 warnings; 8 subtests; 241.18 s | 2,439 passed; 0 failed; 0 skipped; 6 warnings; 8 subtests; 406.61 s |

The database evidence used a dedicated loopback-only PostgreSQL 16 instance
with UTF-8 encoding and per-test isolated schemas. No unknown local business
database was contacted or modified. No remote push or pull request was made.

Local checkpoint commits, in order:

1. `e376446` — inventory SQLite and compatibility paths;
2. `09d6dcf` — normalize the audit document;
3. `b6adb20` — remove backend/factory branches;
4. `af79ad3` — replace inherited algorithms with native repositories;
5. `ac26318` — add the PostgreSQL-only Decision closure;
6. `8b5007b` — harden lineage, frozen authority, T+1, replay and migration behavior.

## 2. SQLite removal disposition

No business `.sqlite`, `.sqlite3` or `.db` source requiring preservation was
found, so no one-time importer was retained.

| Class | Removed or replaced |
| --- | --- |
| Repository | Governance, Decision, Portfolio/Risk, Execution/Fill, Thesis Health, Daily, Canonical Lifecycle, Controlled Operation, Composite Evidence and State SQLite repositories were deleted or renamed into native PostgreSQL implementations. |
| Adapter/bridge | `persistence/postgres/adapter.py`, `persistence/postgres/dbapi.py` and the PostgreSQL-to-SQLite DB-API/SQL translation path were deleted. |
| Factory/settings | Backend enum, SQLite path/DSN, fallback and all SQLite factory branches were removed. PostgreSQL absence raises `DATABASE_UNAVAILABLE`. |
| Schema/migration | Per-domain SQLite up/down migrations and inline SQLite schema modules were deleted. Packaged forward migrations 001–026 are the only migration authority. |
| Replay | File-database replay paths were removed. Decision replay imports immutable authority into an independently migrated PostgreSQL schema. |
| Import tool | The hypothetical manifest, report, importer, script and initial empty manifest were deleted because discovery found no real source data. |
| Tests | SQLite repository, bridge, importer and migration suites were deleted or ported to PostgreSQL. Remaining SQLite strings are negative rejection/architecture assertions or historical documents. |
| CLI/environment | SQLite CLI flags, database paths and environment selection were removed. PostgreSQL URL/schema are explicit. |
| Package | The final wheel (539 members) and sdist (639 members) contain no SQLite or compatibility-bridge module. |

The published PostgreSQL migration 017 still contains its historical backend
vocabulary because migration checksums are immutable. Migration 024 constrains
all current bindings to PostgreSQL. This is not a runnable SQLite backend.

## 3. Native PostgreSQL architecture

```text
Application / Domain Service
→ bounded Repository protocol or native repository API
→ NativePostgresRepository / bounded Postgres*Repository
→ psycopg parameter binding and PostgreSQL transaction
→ PostgreSQL 16 authority tables
```

- Transactions use psycopg parameters, native `ON CONFLICT`, `RETURNING`,
  `BOOLEAN`, `TIMESTAMPTZ`, `NUMERIC` and `JSONB` where required.
- Aggregate-scoped advisory locks protect identity creation; row locks and
  conditional checks protect existing aggregates. There is no bridge-wide
  global mutex.
- Revision chains use CAS; terminal Daily Summary uniqueness uses a partial
  unique index.
- Every Decision writer revalidates Claim, Lease, fencing token and Tick version
  inside its transaction. A stale worker cannot publish reconciliation,
  settlement evidence, Summary, Proposal, Risk or Runtime receipt.
- Idempotency keys are bound to canonical command hashes; a reused key with
  different content fails closed.
- Configuration rows are immutable and content-addressed. New Reconciliation,
  Proposal and Risk rows have PostgreSQL-enforced configuration references.
- Migration 026 preserves populated prerelease v1 rows without rewriting their
  identities; all new Runtime receipts use lease-bound v2 payloads.
- Tests use session infrastructure plus a random PostgreSQL schema per test;
  no SQLite transaction or constraint behavior is used as a substitute.

## 4. Decision System architecture and authority boundary

Actual Runtime chain:

```text
State System receipt and exact State-stage bundle
→ Manual Account Observation lookup
→ optional explicit T+1 settlement evidence
→ frozen Fill-derived account authority
→ Account Reconciliation
→ Daily Summary Preview
→ Research Portfolio Proposal
→ independent PostgreSQL Risk reload and recomputation
→ blocked/final/correction Daily Summary
→ Decision Runtime receipt
```

The Continuous composition now passes the State receipt as
`STATE_SYSTEM_OUTPUT` and preserves the pipeline aggregate under a distinct
reference. Multi-scope ETF/Theme stages bind the exact ordered State ID/hash/scope
set through one canonical bundle identity; a subset or superset has a different
identity.

`PositionSettlementEvidence` binds the account/AsOf scope, CN A-share trading
calendar and per-symbol session statuses. The existing Fill projector then
derives T+1 available/frozen quantities. Missing settlement evidence leaves a
non-empty basic projection incomplete. It never creates or changes a Fill or
Position.

Independent Risk accepts only the Proposal ID, then reloads and validates the
Summary, Manual Observation, Reconciliation, Risk configuration, frozen Fill
view, optional settlement evidence, live as-of Fill projection and scoped State
authority from PostgreSQL. It recomputes the Proposal before deciding.

Replay uses a separately migrated PostgreSQL schema. It imports the immutable
bundle, strictly restores every versioned payload, and the replay Risk Reader
reloads each authority from PostgreSQL before recomputation. Replay proves
deterministic identity and local PostgreSQL integration; it is not production
recovery qualification.

All outputs remain `RESEARCH / MANUAL_DECISION_SUPPORT`. Summary, Manual Account,
Reconciliation, Portfolio and Risk do not create ManualTrade, Order, Fill,
Position change or Broker call. The Entry blocker remains in place.

## 5. Primary implementation scope

| Area | Delivered scope |
| --- | --- |
| Contracts/Readers | Strict versioned Decimal, UTC-second, NFC, identity/hash and lineage Readers for Summary, account, reconciliation, proposal, Risk, Fill authority and settlement evidence. |
| Migration 025 | Daily Summary/candidates, Manual Account/positions, Reconciliation/differences, Proposal/lines, Risk and Runtime receipt. Its published checksum was not changed. |
| Migration 026 | Lease-bound receipts, State-stage authority, immutable configuration, T+1 settlement evidence, frozen Fill authority, replay import and forward-only v1 preservation. |
| Repository | Native PostgreSQL CRUD, CAS, scope locking, claim/fence validation, strict reconstruction and configuration authority checks. |
| Runtime child | Single `DECISION_SYSTEM` child; no second scheduler or Runtime. |
| CLI | Record/import/inspect Manual Account; reconcile; preview/finalize/inspect Summary; inspect Proposal and Risk; JSON plus CSV account input. |
| Replay | Isolated PostgreSQL import, strict Reader restoration, deterministic Reconciliation/Portfolio/Risk re-execution and terminal verification. |
| Tests | Window, append-only observation, reconciliation, portfolio, independent Risk, runtime, stale fence, migration, concurrency, CLI, replay, authority and T+1 PostgreSQL integration. |

## 6. Validation record

| Command | Result |
| --- | --- |
| `uv sync --frozen --extra dev --extra postgres` | PASS |
| `uv run python scripts/check_docs_links.py` | PASS — documentation authority, links, evidence, supersession and inventory OK |
| `uv run pytest -q tests/scripts/test_check_docs_links.py` | PASS — 8 passed |
| PostgreSQL Decision/State/Composition/CLI/Migration/Schema/architecture focused matrix | PASS — 89 passed |
| `MARKET_REGIME_ALPHA_TEST_DATABASE_URL=… uv run pytest` | PASS — 2,439 passed, 0 failed, 0 skipped, 6 warnings, 8 subtests, 406.61 s |
| `uv run ruff check .` | PASS |
| `uv run mypy` | PASS — 365 source files |
| `uv run python -m build --outdir <isolated-temp-dir>` | PASS — sdist and wheel |
| wheel/sdist forbidden-member scan | PASS — no SQLite/DB-API compatibility bridge modules |
| `git diff --check` / `git diff --cached --check` | PASS |

One focused invocation initially named a nonexistent architecture-test path and
exited before collection. It was corrected to
`tests/architecture/test_postgres_runtime_boundaries.py`; the resulting 89-test
matrix passed. This was an invocation error, not a skipped or failed test.

The six full-suite warnings are existing pandas DataFrame fragmentation
performance warnings in Top1000 attribution tests. PostgreSQL integration,
migration and replay tests were not skipped.

## 7. Evidence levels and non-claims

| Evidence level | Result |
| --- | --- |
| Code | Implemented and locally committed |
| Fixture/domain tests | Passed |
| PostgreSQL integration | Passed on PostgreSQL 16.14 |
| PostgreSQL replay | Passed in isolated migrated schemas with PostgreSQL-backed Risk reload |
| Free Live | Not run in this work package |
| PIT-aware | Contracts preserve explicit AsOf/AvailableAt lineage; no new Provider qualification |
| Formal PIT | Not established |
| Formal OOS | Not run |
| Shadow | Not run |
| Production | Not established |

This evidence does not show profitability, validated Alpha, formal model
qualification, production readiness, Entry admission or Broker readiness.

## 8. Remaining work and next-stage judgment

Still absent or intentionally deferred:

- Model Registry Runtime Selector;
- economic validation, Formal PIT and Formal OOS;
- sustained Shadow Runtime and long-duration Free Live evidence;
- qualified/authenticated independent cash/equity and calendar/status sources;
- QMT, MiniQMT, PTrade, XtQuant and every Broker connection;
- Web/dashboard pages and authenticated operator workbench;
- automatic order, cancellation, Fill, model promotion or Entry unblock.

The repository is engineering-dependency-ready to enter `WP-GOV-01` only as a
governance and selection-control work package. `WP-GOV-01` must not promote a
model, grant Entry/Broker authority or claim economic validation until Formal
PIT/OOS, Shadow and qualified operating evidence exist.
