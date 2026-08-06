# PostgreSQL-Only Decision Closure Implementation Plan

> **Status:** ROADMAP

> **For agentic workers:** REQUIRED SUB-SKILL: Use executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove every runnable SQLite persistence/replay path, make all repositories native PostgreSQL 16 implementations, and add the research/manual decision-support closure to the existing Continuous Runtime.

**Architecture:** Bounded Repository Protocols compose directly to psycopg-backed native repositories through one PostgreSQL-only factory. One `DECISION_SYSTEM` child composes append-only account observation, reconciliation, Daily Summary, research portfolio and independently reloaded risk services under the existing tick Lease/fence.

**Tech Stack:** Python 3.12, psycopg 3/pool, PostgreSQL 16, SQL forward migrations, Decimal, pytest, Ruff, mypy, uv.

## Global Constraints

- Baseline is `feat/continuous-research-runtime@547ddfba39df155a8b53611e1ce9200bf789de60`.
- Preserve the primary checkout's unrelated `.idea/modules.xml` change exactly; do not touch it from this worktree.
- PostgreSQL is the only durable Runtime, Repository, Journal, Replay and integration-test database.
- Never retain a SQLite backend, bridge, feature flag, path, DSN, fallback, replay mode or test substitute.
- Preserve historical fixed-14:55 Target/TargetId/Artifact/Reader semantics.
- Preserve all Fill-derived Position authority and A-share T+1 rules.
- Manual Account is observation only; Proposal and Risk are research decisions only.
- No Opportunity, Order, BrokerOrder, automatic/manual fake Fill, Position mutation or Broker call.
- Entry remains blocked. Model parameters and registry status remain unchanged.
- All database tests use an isolated UTF-8 PostgreSQL 16 cluster/schema and must not skip.
- Every checkpoint runs focused tests and `git diff --check` before commit.

---

### Task 1: Freeze baseline and removal inventory

**Files:**
- Create: `docs/audit/WP-PGSQL-01-SQLite-Inventory.md`
- Create: `docs/superpowers/specs/2026-08-06-postgresql-only-decision-closure-design.md`
- Create: `docs/superpowers/plans/2026-08-06-wp-pgsql-decision-closure.md`

**Interfaces:**
- Produces: audited removal matrix and authority boundaries used by every later task.

- [ ] Record branch/SHA/tool/migration/test baselines and exact database isolation.
- [ ] Classify Repository, Adapter, Schema, Test, Replay, CLI, Environment, Documentation and Dependency occurrences.
- [ ] Prove no Market Regime Alpha SQLite business data requires a retained importer.
- [ ] Run `git diff --check` and commit `audit(pgsql): inventory sqlite and compatibility paths`.

### Task 2: Make settings and composition PostgreSQL-only

**Files:**
- Modify: `src/market_regime_alpha/persistence/settings.py`
- Modify: `src/market_regime_alpha/persistence/repository_factory.py`
- Modify: `src/market_regime_alpha/persistence/__init__.py`
- Modify: affected CLI/script composition roots
- Modify: `tests/persistence/test_settings.py`
- Modify: `tests/persistence/test_repository_factory.py`
- Modify: `tests/persistence/test_cli_backend_selection.py`

**Interfaces:**
- Produces: `DatabaseSettings.from_sources(database_url, environ)`, PostgreSQL-only `RepositoryFactory`, typed `DATABASE_UNAVAILABLE` behavior.

- [ ] Add failing tests rejecting `sqlite:`, file paths, legacy flags, missing PostgreSQL and unavailable PostgreSQL.
- [ ] Remove `DatabaseBackend`, `sqlite_path`, backend selection and automatic/explicit fallback.
- [ ] Remove all CLI SQLite flags and require explicit URL/environment.
- [ ] Run focused settings/factory/CLI tests against PostgreSQL.
- [ ] Run `git diff --check` and commit `refactor(pgsql): remove sqlite repositories and factory branches`.

### Task 3: Replace bridge-backed repositories with native psycopg

**Files:**
- Delete: `src/market_regime_alpha/persistence/postgres/dbapi.py`
- Delete: `src/market_regime_alpha/persistence/postgres/adapter.py`
- Rewrite: bounded `postgres*.py` repositories under `platform`, `decision`, `portfolio`, `execution`, `position`, `features`, and `application/**`
- Delete: every `sqlite*.py` runtime/repository module
- Modify: package `__init__.py` exports and `pyproject.toml`

**Interfaces:**
- Produces: direct psycopg repositories using `%s`, `ON CONFLICT`, `RETURNING`, native types, row locks, scoped advisory locks, CAS and fences.

- [ ] Port contract tests to PostgreSQL and make bridge/SQLite import guards fail.
- [ ] Move aggregate restoration into native bounded repositories without SQL translation.
- [ ] Replace global emulation lock with aggregate/operation/account/date lock scopes.
- [ ] Delete SQLite modules and verify no source import can re-enable them.
- [ ] Run all repository, constraint and concurrency tests.
- [ ] Run `git diff --check` and commit `refactor(pgsql): replace compatibility bridge with native repositories`.

### Task 4: PostgreSQL-only Replay and test infrastructure

**Files:**
- Modify: canonical/controlled/runtime replay application modules and CLIs
- Delete: importer/manifest files listed in the audit
- Modify: `tests/persistence/postgres/conftest.py`
- Delete or port: SQLite-only repository/integration test modules
- Add: PostgreSQL replay, migration-upgrade, worker-schema and package-content guards

**Interfaces:**
- Produces: session/worker-isolated migrated PostgreSQL schemas and deterministic replay from immutable evidence.

- [ ] Make missing test DSN an error rather than a skip.
- [ ] Test empty 001-latest migration and a schema stopped at 023 upgraded forward.
- [ ] Replay historical 14:55, Canonical, Controlled, State and Decision evidence in PostgreSQL.
- [ ] Assert the built wheel contains no runnable SQLite modules or bridge.
- [ ] Run focused replay/migration tests and commit `test(pgsql): migrate replay and integration tests to postgres`.

### Task 5: Declare PostgreSQL Authority Only

**Files:**
- Modify: `AGENTS.md`, `CLAUDE.md`, current status/capability/gap documents
- Modify: PostgreSQL runbook, architecture and documentation index
- Add: PostgreSQL-only delivery evidence

**Interfaces:**
- Produces: one current persistence authority statement with explicit non-claims.

- [ ] Supersede current SQLite compatibility/import instructions.
- [ ] Document failure, backup/restore, migration and isolated replay without a fallback database.
- [ ] Run documentation authority/link tests and commit `docs(pgsql): declare postgres-only authority`.

### Task 6: Add Daily Decision and Manual Account domain contracts

**Files:**
- Create: `src/market_regime_alpha/application/decision_system/contracts.py`
- Create: `src/market_regime_alpha/application/decision_system/window.py`
- Create: `src/market_regime_alpha/application/decision_system/account.py`
- Create: focused pure-domain tests

**Interfaces:**
- Produces: typed IDs, lifecycle/status enums, immutable Summary/Candidate and Account/Position observation contracts with Decimal validation.

- [ ] Write failing tests for window boundaries, immutable Final/Correction semantics, late evidence and prohibited outcome vocabulary.
- [ ] Write failing tests for Decimal precision, quantity partitions, duplicate symbols, revisions and no-Fill boundary.
- [ ] Implement deterministic content identities and explicit lineage validation.
- [ ] Run focused tests and commit `feat(decision): add decision window summary and manual account contracts`.

### Task 7: Add migration 024 and native decision repository

**Files:**
- Create: `src/market_regime_alpha/persistence/postgres/migrations/024_decision_system.sql`
- Create: `src/market_regime_alpha/application/decision_system/postgres_repository.py`
- Create: repository and migration tests

**Interfaces:**
- Produces: append-only Summary, Account, Reconciliation, Proposal, Risk and Runtime receipt persistence with idempotency, revision, CAS and fencing.

- [ ] Test fresh migration, 023 upgrade, checks, unique Final, append-only triggers and exact numeric round-trip.
- [ ] Implement direct psycopg reads/writes with explicit identities only.
- [ ] Test concurrent account revisions/finalization and stale-fence rejection.
- [ ] Run focused tests and commit `feat(decision): add postgres decision authority`.

### Task 8: Implement reconciliation

**Files:**
- Create: `src/market_regime_alpha/application/decision_system/reconciliation.py`
- Create: reconciliation unit and PostgreSQL integration tests

**Interfaces:**
- Consumes: explicit Account Observation, Fill-derived Position snapshot/head and tolerance configuration.
- Produces: immutable `AccountReconciliationReport` plus typed difference lines.

- [ ] Test exact match, cash/equity/quantity/availability/cost/missing/T+1/corporate-action/insufficient cases.
- [ ] Implement deterministic comparison without Fill or Position writes.
- [ ] Test unresolved differences block OPEN/ADD and concurrent revision CAS.
- [ ] Run focused tests and commit `feat(account): add fill-derived reconciliation`.

### Task 9: Implement research portfolio proposal

**Files:**
- Create: `src/market_regime_alpha/application/decision_system/portfolio.py`
- Create: proposal unit and PostgreSQL integration tests

**Interfaces:**
- Consumes: explicit Summary/State/Pool/Candidate/Signal/Forecast/Account/Reconciliation/Position/Risk configuration identities.
- Produces: immutable research-only proposal and line items.

- [ ] Test existing positions, symbol/theme/ cash/liquidity constraints, model qualification and unknown orderability.
- [ ] Implement deterministic Decimal weights/amounts and invalidation reasons.
- [ ] Assert no execution, Fill, Position or Broker dependency/call.
- [ ] Run focused tests and commit `feat(portfolio): add research portfolio proposal`.

### Task 10: Implement independently reloaded risk

**Files:**
- Create: `src/market_regime_alpha/application/decision_system/risk.py`
- Create: independent risk tests

**Interfaces:**
- Consumes: Proposal ID plus PostgreSQL authority Reader.
- Produces: immutable `IndependentRiskDecision`.

- [ ] Test fresh reload rather than trusting proposal-derived values.
- [ ] Test stale account/data, unreconciled/position mismatch, unknown orderability, lineage mismatch, unqualified model and invalid config.
- [ ] Implement fail-closed OPEN/ADD and research-only approval/reduction results.
- [ ] Run focused tests and commit `feat(risk): add independent risk decision`.

### Task 11: Wire the sole Continuous Runtime decision child

**Files:**
- Modify: Continuous Runtime child, runner, journal/replay/report contracts
- Create: `src/market_regime_alpha/application/decision_system/service.py`
- Add: runtime integration/concurrency/recovery tests

**Interfaces:**
- Produces: one ordered `DECISION_SYSTEM` child and six durable stage receipts.

- [ ] Test one child only, ordered stages, same-tick reuse and Preview/Final behavior.
- [ ] Test multi-worker claim, Lease expiry, stale fence, rollback, resume and concurrent finalize.
- [ ] Bind every write to Operation/Tick/Claim/Lease/Fence/Tick version/State receipt/configuration.
- [ ] Run focused tests and commit `feat(runtime): add decision system child`.

### Task 12: Add PostgreSQL-only account and decision CLI

**Files:**
- Create: `src/market_regime_alpha/cli/decision_system.py`
- Modify: `pyproject.toml` entry points
- Add: CLI JSON/CSV integration tests

**Interfaces:**
- Produces: record/import/inspect account, reconcile, preview/finalize/inspect Summary, inspect Proposal and inspect Risk commands with deterministic JSON.

- [ ] Test JSON and CSV ingestion, Decimal fidelity, revisions and idempotency.
- [ ] Test unavailable PostgreSQL fail-closed and reject SQLite DSNs/paths.
- [ ] Assert commands do not schedule, call Broker, create Fill or modify Position.
- [ ] Run focused tests and commit `feat(cli): add postgres-only account and decision commands`.

### Task 13: Authority, replay and concurrency closure

**Files:**
- Add: decision authority AST/import guards
- Add: PostgreSQL decision replay and concurrency suites
- Modify: migration/schema manifests and exact table expectations

**Interfaces:**
- Produces: executable proof of PostgreSQL-only authority and unchanged trading boundary.

- [ ] Prove only valid Fill changes Position.
- [ ] Prove Summary/Account/Reconciliation/Proposal/Risk create no trade authority.
- [ ] Prove no QMT/PTrade/XtQuant/Broker call and Entry blocker remains.
- [ ] Run all PostgreSQL/migration/replay/concurrency/decision tests and commit `test(decision): add concurrency replay and authority coverage`.

### Task 14: Documentation, full validation and self-review

**Files:**
- Modify: docs index, architecture, status, capability, gap and runbooks
- Create: WP-DECISION-01 work package, runbook, audit and acceptance evidence

**Interfaces:**
- Produces: exact-HEAD evidence and next-phase assessment for WP-GOV-01.

- [ ] Run docs links, full pytest, Ruff, mypy, build and `git diff --check` on the exact final code.
- [ ] Inspect package contents and repository search results for forbidden SQLite runtime paths.
- [ ] Review standards and correctness; fix all High/Medium findings and rerun affected gates.
- [ ] Record evidence levels and explicit remaining gaps.
- [ ] Commit `docs(decision): add decision closure runbook and evidence` without push or PR.
