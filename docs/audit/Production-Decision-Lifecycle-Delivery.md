# Production Decision Lifecycle Delivery

> **Status:** CURRENT_STATUS
> **Authority:** Commit-bound implementation delivery record for WP-PDL
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-01
> **Supersedes:** None
> **Superseded By:** None
> **Related Documents:** Production-Decision-Lifecycle-Gap-Analysis.md, ../architecture/10-Production-Decision-Lifecycle.md, ../roadmap/work-packages/WP-PDL-Production-Decision-Lifecycle.md, ../operations/Production-Decision-Lifecycle-Runbook.md
> **Code Evidence:** `feat/production-decision-lifecycle`; semantic phase checkpoint commits and recorded tests below

## Phase 0 — baseline reconciliation

Checkpoint: `f7b57a3` (`docs: reconcile production lifecycle baseline`).

Delivered:

- corrected repository-supported prompt status and AGENTS authority heading;
- recorded actual bridge, governance, boundary, Position and execution facts;
- approved explicit-config, fail-closed design and implementation plan;
- preserved the user-owned `.idea/modules.xml` change outside the commit.

Observed quality gate:

| Command | Result |
|---|---|
| `git diff --check` | PASS |
| `python scripts/check_docs_links.py` | PASS |
| `python -m pytest -q tests/scripts/test_check_docs_links.py` | PASS — 8 |
| `python -m pytest -q tests/platform` | PASS — 15 |
| `python -m pytest -q` | PASS — 1170 |
| `python -m ruff check .` | PASS |
| `python -m mypy` | PASS — 224 source files |

## Phase 1 — Operational Research Bridge

Delivered on the Phase 1 checkpoint:

- immutable content-addressed supplemental evidence package and semantic
  Reader;
- exact Source Artifact IDs/hashes, SourceManifest, DecisionTime,
  AvailabilityTime, PIT membership, ETF mapping, Theme, Capital, Symbol,
  DataEligibility, missingness and reason-code contracts;
- application adapter that reuses verified Daily Universe, Eligibility,
  Decision Price and PredictionRuns;
- explicit-config run and replay CLI;
- deterministic duplicate-run reuse and semantic replay.

The adapter remains orchestration, not data authority. Missing or late
supplemental evidence fails closed. Fixture evidence is synthetic and
EXPLORATORY. No LIVE, formal PIT, formal OOS, calibrated probability or trading
authority is established.

Focused evidence before the phase quality gate:

| Command | Result |
|---|---|
| `python -m pytest -q tests/application/operational_research` | PASS — 6 |
| focused Ruff | PASS |
| `python -m mypy` | PASS — 229 source files |

Phase quality gate:

| Command | Result |
|---|---|
| `git diff --check` | PASS |
| `python scripts/check_docs_links.py` | PASS |
| `python -m pytest -q tests/scripts/test_check_docs_links.py` | PASS — 8 |
| `python -m pytest -q tests/platform` | PASS — 15 |
| `python -m pytest -q` | PASS — 1176 |
| `python -m ruff check .` | PASS |
| `python -m mypy` | PASS — 229 source files |

## Phase 2 — durable governance repositories

Delivered on the Phase 2 checkpoint:

- `ModelRegistryRepository` and `ExperimentGovernanceRepository` Protocols;
- persistent services that validate with the existing in-memory domain rules;
- isolated SQLite up/down migration and packaged SQL resources;
- `version` compare-and-swap and globally unique idempotency commands;
- append-only model lifecycle transitions and experiment access events;
- restore, duplicate, conflicting key, stale writer, forged state, transaction
  rollback and migration isolation tests.

Database changes:

| Table | Authority and constraint |
|---|---|
| `pdl_schema_migrations` | applied governance schema versions only |
| `governance_commands` | unique idempotency key, command hash and result version |
| `model_registrations` | current validated projection with CAS version |
| `model_lifecycle_transitions` | append-only sequence per ModelId |
| `governed_experiments` | frozen protocol and current access projection |
| `experiment_access_events` | append-only validation/sealed access sequence |

No table stores a second Artifact authority, and the existing DailyRun tables
are untouched. SQLite is local/test authority only; PostgreSQL is not
implemented.

Phase quality gate:

| Command | Result |
|---|---|
| `python -m pytest -q tests/platform/test_governance_persistence.py` | PASS — 7 |
| `git diff --check` | PASS |
| `python scripts/check_docs_links.py` | PASS |
| `python -m pytest -q tests/scripts/test_check_docs_links.py` | PASS — 8 |
| `python -m pytest -q tests/platform` | PASS — 22 |
| `python -m pytest -q` | PASS — 1183 |
| `python -m ruff check .` | PASS |
| `python -m mypy` | PASS — 229 source files |

## Phase 3 — Signal Engine and PathForecast

Delivered on the Phase 3 checkpoint:

- explicit content-identified Signal and Path configuration contracts with no
  implicit parameter defaults;
- A-share, long-only, versioned decision-time profile validation;
- five-factor Signal confirmation over selected CandidateSet members with exact
  source Artifact lineage and fail-closed missingness/time checks;
- PathForecast over the existing identified EntryPathTarget contract, with
  horizon, upper/lower barriers, MFE, MAE, empirical return quantiles and
  explicit calibration status;
- preservation of dual-touch ambiguity and missing-future-bar exclusions;
- exact-file immutable packages, semantic Readers, content-idempotent publish,
  deterministic replay and CLI operations.

The named profiles in tests are fixture configuration only. No configuration
is a production default, no forecast probability is emitted, and Signal does
not create an Entry, Opportunity, Thesis, order or Position.

Focused evidence before the phase quality gate:

| Command | Result |
|---|---|
| `python -m pytest -q tests/signals tests/forecasting` | PASS — 8 |
| focused Ruff | PASS |
| `python -m mypy` | PASS — 233 source files |

Phase quality gate:

| Command | Result |
|---|---|
| `git diff --check` | PASS |
| `python scripts/check_docs_links.py` | PASS |
| `python -m pytest -q tests/scripts/test_check_docs_links.py` | PASS — 8 |
| `python -m pytest -q tests/platform` | PASS — 22 |
| `python -m pytest -q` | PASS — 1191 |
| `python -m ruff check .` | PASS |
| `python -m mypy` | PASS — 233 source files |

## Phase 4 — TradingOpportunity and TradingThesis

Delivered on the Phase 4 checkpoint:

- exact verified CandidateSet, SignalSnapshot and PathForecast evidence binding;
- versioned Opportunity/Thesis aggregates with expiry, approval, time and typed
  invalidation semantics;
- actor, reason and timestamps on creation and every mutable transition;
- storage-neutral Repository Protocol and isolated SQLite migration;
- CAS conflicts, globally idempotent commands, append-only event histories and
  complete restore validation;
- atomic Opportunity confirmation plus initial approved Thesis;
- application service and CLI without a Candidate-to-Thesis path.

Database changes:

| Table | Authority and constraint |
|---|---|
| `decision_commands` | unique idempotency key and exact command hash |
| `trading_opportunities` | current versioned projection; not evidence authority |
| `opportunity_events` | append-only state snapshots and human audit fields |
| `trading_theses` | one versioned Thesis projection per Opportunity |
| `thesis_events` | append-only approval/invalidation history |

The isolated `002_decision_lifecycle_down.sql` removes only Phase 4 tables and
its migration receipt. Back up histories before destructive rollback. The
existing `daily_runs` semantics and immutable Artifact authority are untouched.

Focused evidence before the phase quality gate:

| Command | Result |
|---|---|
| `python -m pytest -q tests/decision` | PASS — 8 |
| focused Ruff | PASS |
| `python -m mypy` | PASS — 237 source files |

Phase quality gate:

| Command | Result |
|---|---|
| `git diff --check` | PASS |
| `python scripts/check_docs_links.py` | PASS |
| `python -m pytest -q tests/scripts/test_check_docs_links.py` | PASS — 8 |
| `python -m pytest -q tests/platform` | PASS — 22 |
| `python -m pytest -q` | PASS — 1199 |
| `python -m ruff check .` | PASS |
| `python -m mypy` | PASS — 237 source files |

## Phase 5 — Portfolio and independent Risk Authority

Delivered on the Phase 5 checkpoint:

- explicit content-identified RiskBudget and exact limit snapshot binding;
- PortfolioDecision/TargetPosition proposal separated from independent
  RiskDecision approval;
- gross, symbol, theme, liquidity, cash, long-only current-position, T+1 and
  maximum-loss constraints with structured fail-closed reason codes;
- timeout, missing configuration and late input failure paths;
- SQLite repository that recomputes RiskDecision before accepting a write,
  preventing caller-forged approval;
- idempotent immutable decisions and CLI restricted to simulation/manual modes.

Database changes:

| Table | Authority and constraint |
|---|---|
| `portfolio_risk_commands` | unique idempotency key and command hash |
| `portfolio_decisions` | immutable version-0 proposal and full RiskBudget snapshot |
| `risk_decisions` | one independently validated version-0 result per PortfolioDecision |

`003_portfolio_risk_down.sql` removes only these Phase 5 tables and its
migration receipt. The account/position inputs remain explicit snapshots; they
are not yet Phase 6 actual-position authority.

Focused evidence before the phase quality gate:

| Command | Result |
|---|---|
| `python -m pytest -q tests/portfolio` | PASS — 13 |
| focused Ruff | PASS |
| `python -m mypy` | PASS — 242 source files |

Phase quality gate:

| Command | Result |
|---|---|
| `git diff --check` | PASS |
| `python scripts/check_docs_links.py` | PASS |
| `python -m pytest -q tests/scripts/test_check_docs_links.py` | PASS — 8 |
| `python -m pytest -q tests/platform` | PASS — 22 |
| `python -m pytest -q` | PASS — 1212 |
| `python -m ruff check .` | PASS |
| `python -m mypy` | PASS — 242 source files |

## Phase 6 — Manual Execution and Position Authority

Delivered on the Phase 6 checkpoint:

- approved RiskDecision/PortfolioDecision/TargetPosition binding for manual
  intent creation;
- versioned manual order lifecycle with partial, filled, cancelled, rejected,
  unknown and reconciliation-required states;
- append-only Fill/correction ledger with internal/external identity and command
  idempotency;
- SQLite triggers preventing Fill UPDATE and DELETE;
- PositionSnapshot rebuilt only from Fill, including FIFO lot cost, realized
  PnL, correction replacement and reconciliation anomalies;
- separate record-trade, record-fill and Position rebuild CLI paths.

Database changes:

| Table | Authority and constraint |
|---|---|
| `execution_commands` | unique command key/hash and historical result version |
| `manual_trade_records` | current versioned human-intent projection |
| `manual_trade_events` | append-only state snapshots |
| `manual_fills` | append-only Fill/correction authority with unique IDs |

`004_manual_execution_down.sql` removes only Phase 6 ledger tables, triggers
and its migration receipt. Back up Fill history before rollback; Position can
always be rebuilt from the retained ledger. No DailyRun table is changed.

Focused evidence before the phase quality gate:

| Command | Result |
|---|---|
| `python -m pytest -q tests/execution tests/position` | PASS — 13 |
| focused Ruff | PASS |
| `python -m mypy` | PASS — 246 source files |

Phase quality gate:

| Command | Result |
|---|---|
| `git diff --check` | PASS |
| `python scripts/check_docs_links.py` | PASS |
| `python -m pytest -q tests/scripts/test_check_docs_links.py` | PASS — 8 |
| `python -m pytest -q tests/platform` | PASS — 22 |
| `python -m pytest -q` | PASS — 1225 |
| `python -m ruff check .` | PASS |
| `python -m mypy` | PASS — 246 source files |

## Pending phases

Phase 7 remains pending until its executable behavior, tests, documentation
and semantic checkpoint commit are present. Qualified operational supplemental
data remains an external evidence blocker, not a blocker to the fail-closed
engineering mechanics.
