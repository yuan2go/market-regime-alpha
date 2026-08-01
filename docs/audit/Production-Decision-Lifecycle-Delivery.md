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

## Pending phases

Phases 5–7 remain pending until their separate executable behavior, tests,
documentation and semantic checkpoint commits are present. Qualified
operational supplemental data remains an external evidence blocker, not a
blocker to the fail-closed engineering mechanics.

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
