# WP-11 Research Validity and Evaluation Closure Implementation Plan

> **Status:** CURRENT_STATUS
> **Execution base:** `4aaf4eb1c13f42c01dbc0057078f916fd50cf022`
> **Branch:** `agent/wp-11-research-validity-evaluation-closure`
> **Design:** `docs/references/WP-ARCHITECTURE-REFOUNDATION-11-Research-Validity-Evaluation-Design.md`

**Goal:** Implement the integrated Research & Qualification chain from an
Outcome-compatible registered Target through frozen Partition/Experiment/
Protocol, controlled exact Outcome access, and complete Evaluation metrics.

**Architecture:** Keep all ownership in
`market_regime_alpha.research_qualification`. Add cohesive Partition,
Experiment, and Evaluation Domain/Application/Port modules plus three narrow
PostgreSQL UoWs. Extend the unreleased `001_baseline.sql` with twelve concrete
relations, composite FKs, closure functions, lifecycle guards, and append-only
triggers. Evaluation's exact-as-of Outcome resolver remains private to its
transaction and cannot release values before access/observation commit.

**Technology:** Python 3.12, frozen dataclasses/StrEnum/Protocol, psycopg 3,
PostgreSQL 16, pytest, Ruff, mypy, canonical SHA-256 identities.

## Task 1 — Gate A Target/Outcome parity

**Files:**

- Modify `src/market_regime_alpha/research_qualification/domain/targets.py`
- Modify `src/market_regime_alpha/infrastructure/postgres/migrations/001_baseline.sql`
- Modify `tests/refoundation/research_qualification/test_target_domain.py`
- Modify `tests/refoundation/research_qualification/test_target_postgres.py`
- Modify `tests/refoundation/outcome/test_outcome_kernel.py` if parity needs a
  public reconstruction fixture

**Steps:**

1. Add failing parameterized Domain tests for every legal and illegal metric
   dependency shape and for zero `REQUIRED` metrics.
2. Add a failing parity test that constructs each valid Target and reconstructs
   the Outcome Target contract without a later shape rejection.
3. Replace the SIMPLE_RETURN-only Target check with exact per-kind cardinality
   validation and require at least one `REQUIRED` metric.
4. Add failing PostgreSQL tests that attempt root-last closure with invalid
   shapes and no required metric.
5. Extend `validate_target_definition_closure()` with the same per-kind shape
   and required-metric predicates.
6. Run the focused Target Domain/PostgreSQL tests and `git diff --check`.
7. Commit one Gate A checkpoint.

## Task 2 — Research validity vocabulary and immutable Domain models

**Files:**

- Create `src/market_regime_alpha/research_qualification/domain/partition.py`
- Create `src/market_regime_alpha/research_qualification/domain/experiment.py`
- Create `src/market_regime_alpha/research_qualification/domain/evaluation.py`
- Create `src/market_regime_alpha/research_qualification/domain/research_vocabulary.py`
- Modify `src/market_regime_alpha/research_qualification/domain/__init__.py`
- Create `tests/refoundation/research_qualification/test_partition_domain.py`
- Create `tests/refoundation/research_qualification/test_experiment_domain.py`
- Create `tests/refoundation/research_qualification/test_evaluation_domain.py`

**Steps:**

1. Write failing closed-vocabulary and immutable-hash tests.
2. Implement Partition plans/snapshots with positive contiguous rosters,
   Target/scope/session checks, purpose-policy compatibility, and no Outcome
   fields.
3. Implement Experiment/partition/run identities with exact Target binding and
   one primary change.
4. Implement Protocol metric reducer/value-type and slice/disposition
   compatibility plus Evaluation lifecycle transition functions.
5. Implement pure reducers and full metric-member classification, preserving
   EXCLUDED and NOT_ESTIMABLE inputs.
6. Run the three new Domain test modules.

## Task 3 — Typed ports and command contracts

**Files:**

- Create `src/market_regime_alpha/research_qualification/ports/partition_uow.py`
- Create `src/market_regime_alpha/research_qualification/ports/experiment_uow.py`
- Create `src/market_regime_alpha/research_qualification/ports/evaluation_uow.py`
- Create `src/market_regime_alpha/research_qualification/ports/partition_inputs.py`
- Create `src/market_regime_alpha/research_qualification/ports/evaluation_inputs.py`
- Modify `src/market_regime_alpha/research_qualification/ports/__init__.py`
- Create `src/market_regime_alpha/research_qualification/application/partitions.py`
- Create `src/market_regime_alpha/research_qualification/application/experiments.py`
- Create `src/market_regime_alpha/research_qualification/application/evaluations.py`
- Modify `src/market_regime_alpha/research_qualification/application/__init__.py`
- Modify `src/market_regime_alpha/research_qualification/__init__.py`
- Create `src/market_regime_alpha/research_qualification/errors.py`
- Create `tests/refoundation/research_qualification/test_partition_application.py`
- Create `tests/refoundation/research_qualification/test_experiment_application.py`
- Create `tests/refoundation/research_qualification/test_evaluation_application.py`

**Steps:**

1. Define request/result types and narrow repository/UoW protocols. Do not add
   a generic repository or expand the existing Dataset/Target UoWs.
2. Write fake-UoW tests proving Partition freeze never asks for Outcome data and
   accepts no member roster.
3. Implement `FreezeResearchPartition` with semantic request hashing, optional
   Runtime fence, exact replay, failure recording, and bounded retry seam.
4. Implement `RegisterExperiment` and `OpenExperimentRun` in the Experiment UoW.
5. Implement `RegisterEvaluationProtocol` and `OpenEvaluationRun` only in the
   Evaluation UoW; test that Experiment interfaces cannot create/update it.
6. Implement Gate B query/guard types and protected-purpose zero-access checks.
7. Define a private transactional `OutcomeAcquisitionPort`; it returns only an
   acquisition result after UoW commit, never an Outcome DTO or iterable.
8. Implement `AcquireOutcomeInputs`, `CompleteEvaluationRun`, and fail
   transitions with lifecycle/idempotency tests.
9. Run the three new application test modules and architecture import tests.

## Task 4 — Extend the unreleased PostgreSQL baseline and catalog

**Files:**

- Modify `src/market_regime_alpha/infrastructure/postgres/migrations/001_baseline.sql`
- Modify `src/market_regime_alpha/infrastructure/postgres/schema.py`
- Modify `tests/refoundation/test_schema_specification.py`
- Create `tests/refoundation/research_qualification/test_wp11_schema_specification.py`

**Steps:**

1. Add `EXPECTED_RESEARCH_VALIDITY_TABLES` containing exactly the twelve WP-11
   relations and include it in `EXPECTED_TARGET_TABLES`.
2. Add reference-vocabulary checksums for Partition, Experiment, and Evaluation
   closed values.
3. Add root/child tables in dependency order with no JSONB, generic subject,
   future nullable FK, Model/Forecast/Evidence placeholder, or physical table
   partitioning.
4. Add composite unique keys/FKs for Target, commitment, Partition,
   ExperimentPartition/Run, Protocol, Outcome revision, access, observation,
   and metric chains.
5. Add closure functions for Partition roster, Experiment binding, Protocol
   metric roster, access ordinal/order, observation completeness, metric input
   Cartesian completeness, and EvaluationRun transitions.
6. Add append-only triggers to immutable roots/children and a guarded update
   trigger only for EvaluationRun lifecycle fields.
7. Add indexes for Target/window/purpose, member commitment, protected overlap,
   Experiment/Partition, protocol/purpose, Evaluation lifecycle, member access
   ordinal, exact revision, and metric reconciliation.
8. Add schema specification tests for exact relation set, FK delete restrict,
   no JSONB/partitioning, trigger coverage, lifecycle checks, and no 002+ file.
9. Bootstrap a disposable PostgreSQL database through the focused fixtures and
   run schema tests.

## Task 5 — PostgreSQL Partition adapter and UoW

**Files:**

- Create `src/market_regime_alpha/infrastructure/postgres/queries/research_partition_inputs.py`
- Create `src/market_regime_alpha/infrastructure/postgres/repositories/research_partitions.py`
- Create `src/market_regime_alpha/infrastructure/postgres/partition_uow.py`
- Modify PostgreSQL package exports only where a stable public adapter is needed
- Create `tests/refoundation/research_qualification/test_partition_postgres.py`

**Steps:**

1. Add failing tests for database-derived roster completeness, wrong Target,
   empty scope, and caller inability to pass member IDs.
2. Resolve Decision sessions and Target horizon only through exact
   `trading_session` rows; test weekends/holidays prove no calendar arithmetic.
3. Implement purge-before/purge-after/embargo session shifting and hashes.
4. Implement `DIAGNOSTIC_REUSE`, `PURGED_WALK_FORWARD`, and
   `ISOLATED_PROTECTED` compatibility, including rolling-fold allowance and
   protected Locked-OOS/Prospective rejection.
5. Implement Runtime-clock eligibility through a typed seam. HISTORICAL/REPLAY
   fail; SHADOW follows exact Runtime clock facts; every member must precede its
   earliest Outcome event.
6. Insert root then complete members with deferred closure, receipt, audit, and
   optional fence in one short transaction.
7. Test exact replay, changed request, rollback, and no Outcome table access.

## Task 6 — PostgreSQL Experiment adapter and UoW

**Files:**

- Create `src/market_regime_alpha/infrastructure/postgres/repositories/research_experiments.py`
- Create `src/market_regime_alpha/infrastructure/postgres/experiment_uow.py`
- Create `tests/refoundation/research_qualification/test_experiment_postgres.py`

**Steps:**

1. Add failing exact Target/Partition mismatch and immutable predeclaration
   tests.
2. Implement Experiment and ExperimentPartition insertion with frozen
   Partition and purpose checks.
3. Implement immutable ExperimentRun opening.
4. Enforce PostgreSQL authoritative `frozen_at < registered_at < opened_at` and
   zero access for protected purposes under locks.
5. Test exact replay, changed request, prohibited late binding, and no positive
   result semantics.

## Task 7 — PostgreSQL Evaluation adapter, UoW, and Gate B

**Files:**

- Create `src/market_regime_alpha/infrastructure/postgres/repositories/research_evaluations.py`
- Create `src/market_regime_alpha/infrastructure/postgres/queries/research_evaluation_inputs.py`
- Create `src/market_regime_alpha/infrastructure/postgres/evaluation_uow.py`
- Create `tests/refoundation/research_qualification/test_evaluation_protocol_postgres.py`
- Create `tests/refoundation/research_qualification/test_evaluation_lifecycle_postgres.py`

**Steps:**

1. Implement Protocol root-last closure and reducer/value-type,
   slice/disposition, acceptance, Target, purpose, code/config checks.
2. Implement EvaluationRun opening only through Evaluation UoW with exact
   ExperimentRun/Partition/Protocol bindings and expected counts.
3. Add Gate B tests proving OPEN state and zero access are both required before
   acquisition.
4. Add lifecycle transition tests, terminal FAILED tests, immutable binding
   tests, and reopen/input-replacement rejection.

## Task 8 — Transaction-bound exact Outcome acquisition and first access

**Files:**

- Continue `src/market_regime_alpha/infrastructure/postgres/queries/research_evaluation_inputs.py`
- Continue `src/market_regime_alpha/infrastructure/postgres/repositories/research_evaluations.py`
- Continue `src/market_regime_alpha/research_qualification/application/evaluations.py`
- Create `tests/refoundation/research_qualification/test_outcome_acquisition_postgres.py`

**Steps:**

1. Add tests with multiple Outcome corrections showing the resolver chooses the
   unique leaf visible at the requested cutoff, never the unrestricted current
   leaf.
2. Add missing, NOT_DUE, due-but-missing, and ambiguous-visible-leaf fail-closed
   tests.
3. Instrument a test port to prove Outcome values cannot escape before commit
   and no access/observation survives rollback.
4. Lock/revalidate exact Outcome roots/revisions, Partition/members, then
   EvaluationRun in global order.
5. Under each member lock, assign global `max(access_ordinal)+1`; append one
   access and one EvaluationObservation per member.
6. Reconcile exact complete rosters, transition to INPUTS_ACQUIRED with
   PostgreSQL time, and return only committed identities/count/hash.
7. Test ordinal one Authority, later EvaluationRun ordinal 2+ reuse, strict
   PostgreSQL ordering, retained UNAVAILABLE/FAILED, concurrent exact request,
   changed request, rollback, and unknown-commit replay seams.

## Task 9 — Pure Evaluation completion and Gate C

**Files:**

- Continue Evaluation Domain/Application/PostgreSQL files from Tasks 2, 3, 7
- Create `tests/refoundation/research_qualification/test_evaluation_completion_postgres.py`

**Steps:**

1. Load only exact Outcome revision/metric rows named by committed
   EvaluationObservations; add an architecture test rejecting Market/Provider/
   bars/current-latest imports.
2. Generate every protocol-metric × EvaluationObservation input classification
   with exact source metric FK and reason.
3. Compute the four V1 reducers with Decimal semantics and explicit aggregate
   NOT_ESTIMABLE behavior.
4. Insert all EvaluationMetric/MetricObservation rows and reconcile the full
   Cartesian roster before COMPLETED.
5. Add tests for slices, failed/unavailable/partial values, both missingness
   policies, minimum count, acceptance, hidden omission attempts, incomplete
   metric roster, exact replay, and terminal lifecycle.
6. Prove Gate C: complete access + observation + metric-input rosters and no
   posterior member omission.

## Task 10 — Current documentation and focused implementation status

**Files:**

- Modify `docs/status/Current-State.md`
- Modify `docs/status/Capability-Matrix.md`
- Modify `docs/status/Roadmap.md`
- Modify `docs/architecture/Authority-Map.md`
- Modify `docs/architecture/Data-and-Evidence-Architecture.md`
- Modify `docs/architecture/Research-Strategy-Lifecycle.md`
- Modify `docs/architecture/System-Architecture.md` only for implemented facts
- Create `docs/references/WP-ARCHITECTURE-REFOUNDATION-11-Research-Validity-Evaluation-Implementation-Status.md`
- Modify `docs/README.md`

**Steps:**

1. Update implementation facts, schema/catalog counts, commands, ports, and
   remaining NO-GO without changing immutable WP-09/WP-10 Verifications.
2. Record exactly:

   ```text
   WP11_IMPLEMENTED_DRAFT
   FOCUSED_VALIDATION_PASS
   ENGINEERING_QUALIFICATION_PENDING
   ```

3. List every executed command with PASS/FAIL and every omitted qualification
   item as `NOT_RUN_BY_SCOPE`.
4. Run documentation link validation and focused documentation tests.

## Task 11 — Scoped validation, review, and handoff

**Commands:**

```bash
python scripts/check_docs_links.py
python -m pytest -q tests/scripts/test_check_docs_links.py
python -m pytest -q tests/refoundation/research_qualification/test_target_domain.py
python -m pytest -q tests/refoundation/research_qualification/test_target_postgres.py
python -m pytest -q tests/refoundation/research_qualification/test_partition_domain.py tests/refoundation/research_qualification/test_experiment_domain.py tests/refoundation/research_qualification/test_evaluation_domain.py
python -m pytest -q tests/refoundation/research_qualification/test_partition_application.py tests/refoundation/research_qualification/test_experiment_application.py tests/refoundation/research_qualification/test_evaluation_application.py
python -m pytest -q tests/refoundation/research_qualification/test_wp11_schema_specification.py
python -m pytest -q tests/refoundation/research_qualification/test_partition_postgres.py tests/refoundation/research_qualification/test_experiment_postgres.py
python -m pytest -q tests/refoundation/research_qualification/test_evaluation_protocol_postgres.py tests/refoundation/research_qualification/test_evaluation_lifecycle_postgres.py
python -m pytest -q tests/refoundation/research_qualification/test_outcome_acquisition_postgres.py tests/refoundation/research_qualification/test_evaluation_completion_postgres.py
python -m pytest -q tests/refoundation/research_qualification/test_architecture.py
python -m ruff check <changed Python and test files>
python -m mypy <changed source modules>
git diff --check
```

Run only the listed focused and dependency-required nodes. Do not run or claim:

```text
full repository pytest
full Legacy regression
large PostgreSQL concurrency/integration matrix
production/recovery campaign
formal replay qualification campaign
remote CI
Runtime/CLI cutover
Formal PIT/OOS/Prospective campaign
Provider/Alpha/trading/Production qualification
```

Inspect staged and unstaged scope before every checkpoint. Never touch
`.idea/modules.xml`. Finish with a read-only code review against this plan and
the canonical WP-11 design, correct any findings, and report execution-time
main SHA, branch/worktree, commits, schema/catalog changes, focused evidence,
all `NOT_RUN_BY_SCOPE` items, remaining NO-GO, and the next qualification step.
