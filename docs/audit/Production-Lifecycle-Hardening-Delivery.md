# Production Lifecycle Hardening Delivery

> **Status:** CURRENT_STATUS
> **Authority:** Commit-bound delivery record for WP-PDL-HARDENING
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-01
> **Supersedes:** None
> **Superseded By:** None
> **Related Documents:** Production-Lifecycle-Hardening-Baseline.md, ../architecture/11-Production-Lifecycle-Hardening-and-Shadow-Operations.md, ../roadmap/work-packages/WP-PDL-Hardening-and-Shadow-Readiness.md, ../operations/Production-Decision-Lifecycle-Runbook.md
> **Code Evidence:** Feature branch semantic phase checkpoints and the observed commands below

## H0 — Baseline and gap review

Checkpoint: `d98691a` (`docs: audit production lifecycle hardening baseline`).

Delivered:

- exact branch/HEAD/workspace baseline and user-file preservation;
- code/SQL/CLI/test verification of all twelve hardening questions;
- Architecture 11, WP-PDL-HARDENING and task-level plan;
- implementation-state corrections without runtime changes.

Quality gate: PASS for diff check, documentation checker, 8 documentation
tests, 23 Platform tests, full pytest, Ruff and mypy over 248 source files.

## H1 — Complete-account Portfolio and Risk Authority

Delivered in the H1 semantic checkpoint containing this record:

- content-identified `AuthoritativeAccountPortfolioSnapshot` with explicit
  account scope, source reference, NAV/cash, all positions, completeness,
  reconciliation state and source Position references/hashes;
- explicit versioned `CompleteAccountRiskConfiguration`; no age or risk limit
  default;
- Thesis-bound `ProposedTradeDelta` and content-identified
  `PostTradePortfolioSnapshot` retaining unallocated existing positions;
- independent complete-account Risk recomputation over resulting full-account
  gross, symbol, theme and maximum-loss exposure and delta-level cash,
  liquidity and sellable-quantity checks;
- structured DATA_INSUFFICIENT decisions for partial, stale, future or
  unreconciled account snapshots;
- storage-neutral `CompleteAccountPortfolioRiskRepository`;
- atomic SQLite assessment persistence, strict reconstructible restore and
  command idempotency;
- CLI `run-full-account` and `show-full-account-risk` operations;
- isolated migration 005 with a disposable/test-only down migration.

Focused evidence:

| Command | Result |
|---|---|
| `python -m pytest -q tests/portfolio/test_complete_account_risk.py` | PASS — 8 tests |
| `python -m pytest -q tests/portfolio` | PASS — 21 tests |
| focused Ruff | PASS |
| `python -m mypy` | PASS — 250 source files |

Full phase gate:

| Command | Result |
|---|---|
| `git diff --check` | PASS |
| `python scripts/check_docs_links.py` | PASS |
| `python -m pytest -q tests/scripts/test_check_docs_links.py` | PASS — 8 tests |
| `python -m pytest -q tests/platform` | PASS — 23 tests |
| `python -m pytest -q` | PASS — 1,243 tests; six pre-existing pandas fragmentation warnings |
| `python -m ruff check .` | PASS |
| `python -m mypy` | PASS — 250 source files |

### Migration 005

| Table | Purpose and constraint |
|---|---|
| `complete_account_risk_commands` | globally unique idempotency key, exact command/result identities |
| `authoritative_account_portfolio_snapshots` | immutable content-identified complete/partial account observation with source version |
| `complete_account_portfolio_decisions` | immutable version-0 full post-trade proposal and exact configuration |
| `complete_account_risk_decisions` | one independently recomputable version-0 Risk result per proposal |

The migration neither modifies migration 003 nor creates/changes `daily_runs`.
The down migration removes only H1 tables and receipt 005. For any non-disposable
database, stop writes and export the decisions before rollback; immutable
decisions should normally be retained read-only and superseded by a forward
repair.

### Evidence ceiling after H1

H1 closes allocation-local gross/theme/loss risk in the new V2 path. It does
not yet prove that a source Position reference is the unique Thesis book or
derive A-share sellability from Fill/calendar. H2 and H3 own those gaps. The
V1 Portfolio/Risk reader and CLI remain compatible but are not used as
complete-account authority.

No production RiskBudget, Position authority promotion, LIVE execution,
formal PIT/OOS or Alpha claim is established.

## H2 — Thesis-to-Outcome authority trace

Delivered in the H2 semantic checkpoint containing this record:

- deterministic `PositionBook` identity scoped to account, symbol and Thesis;
- a database-enforced single OPEN Thesis per account/symbol, with explicit
  close transition and later-Thesis reopening;
- exact V2 ManualTrade schema binding Opportunity, Thesis, complete-account
  Portfolio/Risk, post-trade snapshot and target-delta hashes;
- V2 Position projection that admits only ManualTrade/Fill events belonging
  to the book while retaining Fill as the only position-changing evidence;
- immutable SQLite authority-chain bindings, reconstruction checks,
  idempotent commands and CAS close;
- `TraceableTradeOutcome` and evaluator that recompute Risk and validate all
  upstream identities before calculating existing outcome metrics;
- exact compatibility for V1 ManualTrade, PositionSnapshot and TradeOutcome
  schemas/readers.

Focused evidence before the full phase gate:

| Command | Result |
|---|---|
| `python -m pytest -q tests/execution/test_traceable_execution_chain.py tests/execution/test_manual_position_authority.py tests/evaluation` | PASS — 20 tests |
| focused Ruff | PASS |
| `python -m mypy` | PASS — 253 source files |

Full phase gate:

| Command | Result |
|---|---|
| `git diff --check` | PASS |
| `python scripts/check_docs_links.py` | PASS |
| `python -m pytest -q tests/scripts/test_check_docs_links.py` | PASS — 8 tests |
| `python -m pytest -q tests/platform` | PASS — 23 tests |
| `python -m pytest -q` | PASS — 1,248 tests; six pre-existing pandas fragmentation warnings |
| `python -m ruff check .` | PASS |
| `python -m mypy` | PASS — 253 source files |

### Migration 006

| Table or index | Purpose and constraint |
|---|---|
| `position_books` | reconstructible OPEN/CLOSED account-symbol-Thesis projection |
| `one_open_position_book_per_account_symbol` | SQLite partial unique concurrency backstop |
| `position_book_events` | append-only open/close history with idempotency keys |
| `traceable_manual_trade_bindings` | immutable upstream identity/hash index referencing the existing manual-trade ledger |

The down migration removes only H2 tables/index/triggers and receipt 006. It
does not remove or rewrite `manual_trade_records`, `manual_trade_events`,
`manual_fills`, Position snapshots or immutable outcome artifacts. For a
non-disposable database, stop traceable commands and export/read-retain the
index before any rollback.

### Evidence ceiling after H2

H2 proves deterministic engineering traceability for synthetic/manual records.
It does not prove broker Fill truth, A-share T+1 sellability, multi-strategy
sleeves, qualified operational reconciliation, LIVE execution, formal PIT/OOS,
calibration or Alpha.

## H3 — Fill-derived A-share T+1 and sellability

Delivered in the H3 semantic checkpoint containing this record:

- V3 PositionSnapshot with total, available, frozen and today-acquired
  quantities and structured sellability state;
- settled PositionLot trade date, next explicit sellable session,
  available/frozen quantities and settlement state;
- typed content-identified symbol-session status evidence with availability
  time and original artifact hash;
- exact TradingCalendarArtifact content hash carried by every V3 snapshot;
- same-session sell reconciliation, explicit-session Friday/holiday handling,
  suspension and missing/late evidence fail-closed behavior;
- deterministic correction/replay and V3 canonical Reader;
- repository enumeration of all OPEN PositionBooks and a hardened
  Position-authoritative complete-account Risk application path.

No database migration is required. Position remains a deterministic projection
of the migration-004 Fill ledger and migration-006 book index. Rollback disables
the V3 application path while retaining exact V1/V2 readers and all Fill/book
history.

Focused evidence before the full phase gate:

| Command | Result |
|---|---|
| `python -m pytest -q tests/position/test_a_share_t_plus_one_authority.py tests/execution/test_traceable_execution_chain.py tests/position tests/data/test_trading_calendar.py` | PASS — 29 tests |
| focused Ruff | PASS |
| `python -m mypy` | PASS — 254 source files |

Full phase gate:

| Command | Result |
|---|---|
| `git diff --check` | PASS |
| `python scripts/check_docs_links.py` | PASS |
| `python -m pytest -q tests/scripts/test_check_docs_links.py` | PASS — 8 tests |
| `python -m pytest -q tests/platform` | PASS — 23 tests |
| `python -m pytest -q` | PASS — 1,255 tests; six pre-existing pandas fragmentation warnings |
| `python -m ruff check .` | PASS |
| `python -m mypy` | PASS — 254 source files |

### Evidence ceiling after H3

Calendar, symbol status, account and Fill fixtures are synthetic/manual. H3
does not establish broker truth, qualified operational reconciliation,
production risk limits, LIVE execution, formal PIT/OOS, calibration or Alpha.
H4 still owns the risk-reducing execution gate.
