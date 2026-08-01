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
