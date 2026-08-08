# WP-GOV-01 Model Governance and Runtime Selector Implementation Plan

> **Status:** CURRENT_SPECIFICATION
> **Authority:** Executable implementation plan for WP-GOV-01
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-08
> **Supersedes:** None
> **Superseded By:** None
> **Related Documents:** ../specs/2026-08-08-wp-gov-01-model-governance-runtime-selector-design.md, ../../status/Current-State.md, ../../status/Capability-Matrix.md
> **Code Evidence:** Baseline `feat/continuous-research-runtime@bd868b06df13c4a657a169e5039c91c1d69a5ef9`; completion is established only by exact-HEAD PostgreSQL, replay, regression and static-check evidence

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the existing PostgreSQL Model Registry with auditable qualification and model selection, and make DailyLoop and Decision Runtime fail closed through that authority.

**Architecture:** Keep `ModelRegistry` as lifecycle truth, add immutable version/runtime lineage, evidence, policy, qualification, assignment and selection contracts in the same `platform` bounded context, and implement them through one PostgreSQL governance repository exposed by the existing factory. DailyLoop selects B0/B1 before execution; Decision Runtime derives model eligibility from persisted selection rather than caller input.

**Tech Stack:** Python 3.12, frozen dataclasses/enums, psycopg 3, PostgreSQL 16, pytest, Ruff, mypy, uv/build.

## Global Constraints

- Branch is `feat/continuous-research-runtime`; never merge `main`.
- PostgreSQL 16 is the only database authority; no mock database or fallback.
- Preserve historical Artifact and PredictionRun readers and immutable identities.
- No automatic promotion, Production Champion, Entry, Order, Broker, Fill or automatic execution.
- Qualification mechanics do not establish PIT, OOS, economic validity, Shadow evidence or profitability.
- Every write uses explicit idempotency, actor/reason audit and deterministic content identity.
- Historical selection replay uses the original governance revision, never current mutable projections.

---

## File Structure

- Create `src/market_regime_alpha/platform/runtime_governance.py`: immutable lineage, policy, evidence, qualification, assignment and selection contracts.
- Create `src/market_regime_alpha/platform/postgres_runtime_governance.py`: unified PostgreSQL qualification, assignment, fail-closed selection and historical replay service, extending the existing Registry repository.
- Extend `src/market_regime_alpha/platform/postgres_governance.py`: bind Registry registration and lifecycle transition to the shared governance revision ledger.
- Create `src/market_regime_alpha/persistence/postgres/migrations/027_model_runtime_governance.sql`: governance revision, evidence, assignment and receipt tables/constraints/triggers.
- Extend `src/market_regime_alpha/persistence/postgres/schema.py`: catalog expectations.
- Extend `src/market_regime_alpha/persistence/repository_factory.py`: expose the unified governance repository/selector composition.
- Create `src/market_regime_alpha/cli/model_governance.py`: governed write/query/replay CLI.
- Modify `src/market_regime_alpha/application/daily_loop/runner.py`: remove in-memory Registry and require selection before B0/B1 execution.
- Modify `src/market_regime_alpha/application/decision_system/runtime.py`: derive candidate eligibility and bind selection receipt.
- Modify `src/market_regime_alpha/application/decision_system/runtime.py`: accept exact runtime lineages, persist selection bindings through the existing receipt, and replay those immutable receipt references.
- Modify `src/market_regime_alpha/platform/candidate_prediction_adapter.py`: stable B0/B1 version definition plus per-run lineage validation.
- Add focused platform, Decision, DailyLoop, migration, concurrency, replay and CLI tests.
- Update current architecture/status/gap/runbook/work-package/delivery evidence documents.

---

### Task 1: Domain contracts and deterministic qualification

**Files:**
- Create: `src/market_regime_alpha/platform/runtime_governance.py`
- Test: `tests/platform/test_runtime_governance.py`

**Interfaces:**
- Produces: `ModelVersionLineage`, `ModelQualificationEvidence`, `ModelGovernancePolicy`, `ModelQualificationDecision`, `ModelRuntimeAssignment`, `RuntimeModelLineage`, `ModelSelectionRequest`, `ModelSelectionReceipt`.
- Produces enums: `RuntimePurpose`, `AssignmentLane`, `QualificationEvidenceKind`, `QualificationEvidenceOutcome`, `QualificationStatus`, `SelectionStatus`.

- [ ] **Step 1: Write failing public-contract tests**

Cover stable hashes, strict unknown-field rejection, future-time rejection,
evidence/definition mismatch, policy requirement evaluation, Challenger isolation
and separate Production authorization.

- [ ] **Step 2: Run the focused test and verify RED**

Run: `uv run pytest -q tests/platform/test_runtime_governance.py`

- [ ] **Step 3: Implement the smallest immutable contracts**

Use canonical JSON/hash helpers and exact UTC-second semantics. A policy decision
must bind the complete evidence ID/hash set and cannot infer a lifecycle
transition or assignment.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run: `uv run pytest -q tests/platform/test_runtime_governance.py`

### Task 2: PostgreSQL migration and unified repository

**Files:**
- Create: `src/market_regime_alpha/persistence/postgres/migrations/027_model_runtime_governance.sql`
- Create: `src/market_regime_alpha/platform/postgres_runtime_governance.py`
- Modify: `src/market_regime_alpha/platform/postgres_governance.py`
- Modify: `src/market_regime_alpha/persistence/postgres/schema.py`
- Modify: `src/market_regime_alpha/persistence/repository_factory.py`
- Test: `tests/persistence/postgres/test_model_runtime_governance.py`
- Test: `tests/persistence/postgres/test_migrator.py`

**Interfaces:**
- Produces: `PostgresModelGovernanceRepository` and native PostgreSQL adapter methods for lineage/evidence/policy/qualification/assignment/selection/as-of snapshot.
- Reuses: `governance_commands`, Registry CAS and `acquire_scope_lock()`.

- [ ] **Step 1: Write migration and repository RED tests**

Assert 001→027 and 026→027 migration, re-execution, FKs/indexes/triggers,
append-only protection, global revisions, restart restore, idempotent writes and
conflicting key rejection.

- [ ] **Step 2: Run real PostgreSQL focused tests and verify RED**

Run with `MARKET_REGIME_ALPHA_TEST_DATABASE_URL` against PostgreSQL 16.

- [ ] **Step 3: Implement migration and native repository**

Use `timestamptz`, `bigint`, `boolean`, JSON text for canonical bytes, indexed
FKs, append-only supersession events, transaction advisory locks in stable
scope order and short transactions.

- [ ] **Step 4: Add CAS/concurrency/idempotency tests**

Two writers replacing the same Champion must yield one winner; duplicate
commands must return the same result; conflicting reuse must fail.

- [ ] **Step 5: Run focused PostgreSQL tests and verify GREEN**

### Task 3: Runtime Selector and historical replay

**Files:**
- Create: `src/market_regime_alpha/platform/postgres_runtime_governance.py`
- Test: `tests/platform/test_runtime_governance.py`
- Test: `tests/persistence/postgres/test_model_runtime_governance.py`

**Interfaces:**
- Produces: `PostgresModelGovernanceRepository.select_model(request) -> ModelSelectionReceipt`.
- Produces: `PostgresModelGovernanceRepository.replay_selection(receipt_id) -> ModelSelectionReceipt`.
- Consumes: exact Registry, policy, qualification, assignment, evidence and runtime lineage at one governance revision.

- [ ] **Step 1: Write accepted/rejected selection RED tests**

Cover missing Champion, duplicate/corrupt authority, suspended/retired model,
stale qualification, missing evidence, every lineage mismatch, unavailable
Production authorization and Challenger non-selection.

- [ ] **Step 2: Implement selection with persisted rejection receipts**

Always record the considered Champion/Challengers, exact revision and reason
codes when PostgreSQL is available. Never fall back to a Challenger.

- [ ] **Step 3: Write and implement historical replay tests**

Select Champion A, replace it with B, replay A at its original revision, and
prove new selection chooses B while historical identity remains unchanged.

- [ ] **Step 4: Run focused selector/replay tests and verify GREEN**

### Task 4: Remove DailyLoop Registry bypass

**Files:**
- Modify: `src/market_regime_alpha/platform/candidate_prediction_adapter.py`
- Modify: `src/market_regime_alpha/application/daily_loop/runner.py`
- Modify: `scripts/run_exploratory_daily_loop.py`
- Test: `tests/persistence/postgres/test_daily_loop_model_governance.py`
- Modify: existing DailyLoop fixtures only where they reach model execution.

**Interfaces:**
- DailyLoop receives a PostgreSQL-backed `ModelRuntimeSelector`.
- `freeze_sources()` remains model-independent.
- B0/B1 PredictionRuns consume selected stable definitions plus exact per-run lineage.

- [ ] **Step 1: Write a RED test proving no selection blocks B0/B1**

- [ ] **Step 2: Write a RED test proving explicit Research Champions execute**

Assert both selection receipts predate PredictionRun publication and their
model/definition/config/Dataset/Universe/Feature lineage matches the runs.

- [ ] **Step 3: Remove `ModelRegistry()` and implement governed selection**

- [ ] **Step 4: Add static architecture assertion against the bypass**

Assert `application/daily_loop/runner.py` neither imports nor constructs the
in-memory Registry.

- [ ] **Step 5: Run DailyLoop focused tests and verify GREEN**

### Task 5: Bind Decision Runtime and Independent Risk

**Files:**
- Modify: `src/market_regime_alpha/application/decision_system/runtime.py`
- Modify: `src/market_regime_alpha/cli/decision_system.py`
- Modify: `tests/application/decision_system/test_runtime.py`

**Interfaces:**
- Decision Runtime receives selector requests/receipt references, not caller authorization.
- Candidate compatibility field is derived from the receipt before Summary creation.
- Decision Runtime receipt binds selection ID/hash/governance revision.

- [ ] **Step 1: Write forged-qualification RED test**

An input candidate marked `QUALIFIED` with no accepted Signal/Forecast
selection must persist a blocked selection/Decision receipt and create no
approved Portfolio/Risk result.

- [ ] **Step 2: Implement selector admission and derived qualification**

- [ ] **Step 3: Prove Research success and Production fail-closed**

Research-qualified Champions may reach research-only Proposal/Risk; the same
models under `PRODUCTION_DECISION` remain blocked without the full policy.

- [ ] **Step 4: Extend Decision replay**

Replay imports and verifies selection evidence in its isolated migrated
PostgreSQL schema and fails atomically on identity/revision conflict.

- [ ] **Step 5: Run Decision/Independent Risk focused tests and verify GREEN**

### Task 6: Governance CLI and inspection

**Files:**
- Create: `src/market_regime_alpha/cli/model_governance.py`
- Modify: `pyproject.toml`
- Test: `tests/cli/test_model_governance_cli.py`

**Interfaces:**
- Produces structured JSON register-lineage/evidence/policy/qualify/assign/suspend/replace/list/show/inspect/replay operations.

- [ ] **Step 1: Write CLI RED tests for read and write operations**

- [ ] **Step 2: Implement strict JSON input and credential-redacted output**

- [ ] **Step 3: Run CLI tests and verify GREEN**

### Task 7: Documentation, full validation, review and publication

**Files:**
- Create: `docs/roadmap/work-packages/WP-GOV-01-Model-Governance-Runtime-Selector.md`
- Create: `docs/audit/WP-GOV-01-Delivery.md`
- Modify: `docs/README.md`
- Modify: `docs/status/Current-State.md`
- Modify: `docs/status/Capability-Matrix.md`
- Modify: `docs/status/Gap-Register.md`
- Modify: `docs/operations/Daily-Decision-System-Runbook.md`
- Modify: `docs/operations/PostgreSQL-Authority-Runbook.md`

- [ ] **Step 1: Run the focused PostgreSQL matrix**

Include migration, Registry, selector, assignment concurrency, DailyLoop,
Decision Runtime, Risk and replay.

- [ ] **Step 2: Run the complete repository gate**

```bash
uv run python scripts/check_docs_links.py
uv run pytest -q tests/scripts/test_check_docs_links.py
MARKET_REGIME_ALPHA_TEST_DATABASE_URL=... uv run pytest -q
uv run ruff check .
uv run mypy
uv run python -m build --outdir <isolated-temp-dir>
git diff --check
```

- [ ] **Step 3: Inspect package contents and migration checksums**

Verify migration 027 and governance CLI/modules exist in wheel/sdist and no
SQLite/compatibility bridge is reintroduced.

- [ ] **Step 4: Update evidence documents with exact results and non-claims**

- [ ] **Step 5: Run two-axis code review against `bd868b0` and fix findings**

- [ ] **Step 6: Inspect/stage the bounded diff and commit**

Run `git diff --cached --check` before the semantic checkpoint commit.

- [ ] **Step 7: Push without force**

Push `feat/continuous-research-runtime` to `origin`, then verify local/remote SHA equality. Do not merge `main` and do not create a PR unless separately requested.
