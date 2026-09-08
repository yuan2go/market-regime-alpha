# WP-11Q Research Validity and Evaluation Qualification Implementation Plan

> **Status:** CURRENT_STATUS
> **Execution base:** `d7f41a30f1917fc3b266bdeebbc157021c3cc352`
> **Branch:** `agent/wp-11q-research-validity-evaluation-qualification`
> **Design:** [WP-11Q Qualification Design](WP-ARCHITECTURE-REFOUNDATION-11Q-Research-Validity-Evaluation-Qualification-Design.md)
> **Dependency stop:** no WP-12 source, DDL, package, placeholder, or design
> implementation before merged-main WP-11 PASS preflight

**Goal:** Correct canonical composition, make each ResearchPartition a complete
single-exchange-calendar Authority, make each Experiment atomically close a
complete ordered Partition roster, add formal read-only verification, and
qualify the resulting exact SHA through the complete local engineering gate.

**Architecture:** Preserve the existing Research & Qualification bounded
context and its Partition, Experiment, and Evaluation UoWs. The sole target
composition root constructs those modules. PostgreSQL derives and closes
calendar/member/binding rosters. Evaluation retains its private transaction-
bound Outcome resolver. Verification is read-only and owner-typed.

**Technology:** Python 3.12, immutable dataclasses/`StrEnum`/`Protocol`,
psycopg 3, PostgreSQL 16, exact Decimal/SHA-256 semantics, pytest, Ruff, mypy,
`build`, and the unreleased `MRA_REFOUNDATION_1/001_baseline.sql`.

## Public seams frozen for TDD

```text
bootstrap_application(settings) -> TargetApplication
TargetApplication.research_partitions.freeze(...)
TargetApplication.research_experiments.register(definition, bindings, ...)
TargetApplication.research_experiments.open_run(...)
TargetApplication.research_evaluations.register_protocol(...)
TargetApplication.research_evaluations.open_run(...)
TargetApplication.research_evaluations.acquire_outcome_inputs(...)
TargetApplication.research_evaluations.complete(...)
TargetApplication.research_evaluation_verifier.verify_partition(...)
TargetApplication.research_evaluation_verifier.verify_experiment(...)
TargetApplication.research_evaluation_verifier.verify_evaluation_run(...)
```

Tests may use owner test fixtures to create prerequisite Target/Decision/
Outcome rows, but success may not depend on manually assembling WP-11
Infrastructure adapters except in adapter-specific unit tests.

## Task 1 — Canonical composition RED/GREEN

**Files:**

- Modify `tests/refoundation/test_bootstrap_cli.py`
- Modify `tests/refoundation/research_qualification/test_wp11_architecture.py`
- Modify `src/market_regime_alpha/bootstrap.py`
- Modify PostgreSQL package exports only if needed for stable composition

**Steps:**

1. Add a failing bootstrap test asserting the four public fields above and the
   concrete command/verifier types.
2. Add a failing architecture test proving the sole root, not a test helper,
   imports the three UoW providers and read-only verification provider.
3. Construct `PostgresPartitionUnitOfWorkProvider`,
   `PostgresExperimentUnitOfWorkProvider`, and
   `PostgresEvaluationUnitOfWorkProvider` once from the target pool.
4. Construct the three existing command modules with the root ID factory and
   expose them on `TargetApplication`.
5. Leave Runtime dispatch, target Step vocabulary, and CLI untouched.
6. Run the two focused tests, Ruff for `bootstrap.py`, mypy for the target root,
   and `git diff --check`.

## Task 2 — Single-exchange Partition Domain and query RED/GREEN

**Files:**

- Modify `src/market_regime_alpha/research_qualification/domain/partition.py`
- Modify `src/market_regime_alpha/research_qualification/ports/partition_inputs.py`
- Modify `src/market_regime_alpha/infrastructure/postgres/queries/research_partition_inputs.py`
- Modify `src/market_regime_alpha/infrastructure/postgres/repositories/research_partitions.py`
- Modify `tests/refoundation/research_qualification/test_partition_domain.py`
- Modify `tests/refoundation/research_qualification/test_evaluation_closure_postgres.py`
- Add `tests/refoundation/research_qualification/test_partition_calendar_postgres.py`

**Steps:**

1. Add failing Domain tests for required closed-format `exchange_code`, stable
   semantic hash inclusion, and continued absence of a caller roster/hash.
2. Extend `PartitionCalendarBounds` with exact exchange/timezone, protected
   Session roster count/hash, and boundary facts.
3. Add a fixture with intentionally divergent SSE/SZSE calendars and same-date
   commitments for the same Target.
4. Add failing PostgreSQL tests proving an SSE declaration includes every and
   only matching SSE commitment, excludes SZSE, and fails when either Decision
   boundary belongs to another exchange.
5. Make boundary, horizon, earliest/due event, purge and embargo queries filter
   the declared exchange explicitly.
6. Canonically hash every exact Session from protected start through protected
   end, including Session/Capture/temporal identity.
7. Persist the derived exchange/calendar identity and member Session identity;
   do not accept them from callers.
8. Re-run all Partition Domain and PostgreSQL focused tests.

## Task 3 — Partition PostgreSQL Authority closure

**Files:**

- Modify `src/market_regime_alpha/infrastructure/postgres/migrations/001_baseline.sql`
- Modify `src/market_regime_alpha/infrastructure/postgres/schema.py`
- Modify `tests/refoundation/research_qualification/test_wp11_schema_specification.py`
- Modify `tests/refoundation/test_schema_specification.py`
- Continue `test_partition_calendar_postgres.py`

**Steps:**

1. Add failing schema tests for root/member exchange/timezone/date columns,
   positive calendar count/hash, composite Session FKs, and required indexes.
2. Add the Partition-specific TradingSession composite unique identity.
3. Extend `research_partition` with explicit exchange/timezone and calendar
   roster summary; strengthen all four boundary FKs.
4. Extend members with exchange/timezone/date and strengthen their Session FK
   plus Partition composite FK.
5. Update `validate_research_partition_member()` and deferred closure so both
   declared-population set differences include the exact exchange.
6. Recompute Session count/hash and protected/horizon bounds in the closure
   trigger; reject wrong calendar or incomplete roster.
7. Scope protected-overlap checks to the same Target and exchange while
   retaining population/purpose/fold compatibility.
8. Update expected baseline/reference/catalog checksums through existing schema
   helpers; create no `002+` migration.
9. Bootstrap a fresh disposable test database and run the Partition/schema
   focused set.

**Checkpoint:** commit canonical composition plus complete Partition calendar
Authority after RED/GREEN is stable.

## Task 4 — Complete Experiment roster Domain/Application RED/GREEN

**Files:**

- Modify `src/market_regime_alpha/research_qualification/domain/experiment.py`
- Modify `src/market_regime_alpha/research_qualification/application/experiments.py`
- Modify `src/market_regime_alpha/research_qualification/ports/experiment_uow.py`
- Modify `tests/refoundation/research_qualification/test_experiment_domain.py`
- Add `tests/refoundation/research_qualification/test_experiment_application.py`

**Steps:**

1. Add failing tests for an empty tuple, non-contiguous ordinals, duplicate
   binding ID, duplicate Partition, wrong Experiment/Target, and stable ordered
   roster/hash semantics.
2. Add `binding_ordinal` to `ExperimentPartitionBinding`.
3. Add a pure Domain closure function that validates all bindings and computes
   partition count/hash plus aggregate Experiment content hash.
4. Change `ExperimentCommands.register` to accept only the immutable tuple and
   hash the full ordered request.
5. Change typed records/repository ports so Experiment replay returns the root
   and complete ordered child tuple.
6. Add fake-UoW tests proving one repository call receives the whole roster,
   changed order changes the request, and Experiment UoW still exposes no
   EvaluationRun writer.
7. Run Domain/Application tests before changing PostgreSQL.

## Task 5 — Complete Experiment roster PostgreSQL RED/GREEN

**Files:**

- Modify `src/market_regime_alpha/infrastructure/postgres/repositories/research_experiments.py`
- Modify `src/market_regime_alpha/infrastructure/postgres/migrations/001_baseline.sql`
- Modify `src/market_regime_alpha/infrastructure/postgres/schema.py`
- Modify `tests/refoundation/research_qualification/test_evaluation_closure_postgres.py`
- Add `tests/refoundation/research_qualification/test_experiment_roster_postgres.py`
- Modify `tests/refoundation/research_qualification/test_wp11_schema_specification.py`

**Steps:**

1. Add failing success tests for FIT + VALIDATION + LOCKED_OOS in one ordered
   Experiment and a Run bound to one exact child.
2. Add failing direct-SQL cases for zero/partial children, missing ordinal,
   duplicate Partition, wrong Target/purpose/hash, and late child insertion.
3. Add root definition hash, positive partition count, roster hash, aggregate
   content hash, and child ordinal columns/constraints/indexes.
4. Insert root and every child in one UoW using one PostgreSQL-authoritative
   registration instant.
5. Permit child insertion only for a root created by the current transaction;
   add a deferred root closure that recomputes every count/order/hash/binding
   and protected zero-access condition.
6. Make `record()` load exactly the complete ordered roster. Exact replay must
   compare that record; a changed roster under the same idempotency identity
   must fail closed.
7. Add concurrent identical and changed-roster registration tests using real
   PostgreSQL sessions.
8. Run Experiment, Evaluation dependency, and schema focused tests.

**Checkpoint:** commit atomic Experiment roster closure.

## Task 6 — Unknown commit and recovery semantics

**Files:**

- Modify `src/market_regime_alpha/research_qualification/errors.py`
- Modify `src/market_regime_alpha/infrastructure/postgres/research_transaction.py`
- Modify `src/market_regime_alpha/research_qualification/application/_command_support.py`
- Modify Partition/Experiment/Evaluation commands only as required for exact
  outcome probing and typed recovery
- Add `tests/refoundation/research_qualification/test_wp11_recovery.py`

**Steps:**

1. Add failing tests distinguishing known serialization/deadlock/pre-commit
   failures from connection loss raised by `commit()`.
2. Introduce `ResearchUnknownCommitOutcomeError`; automatic transaction retry
   must not catch it.
3. Add exact receipt/result probe behavior keyed by command kind, scope,
   idempotency key, and request hash.
4. With a real PostgreSQL transaction and a faulting connection wrapper, commit
   the transaction then raise a transport error. Prove the command does not
   execute a second mutation and exact recovery reloads the committed result.
5. Exercise the no-commit variant and prove the invocation remains explicit
   unknown without a partial aggregate; an explicitly initiated exact recovery
   may subsequently write once.
6. Preserve bounded three-attempt retry only for known transient whole-
   transaction failures.
7. Run all Research command/failure/Runtime fence regressions.

## Task 7 — Formal read-only verifier RED/GREEN

**Files:**

- Add `src/market_regime_alpha/research_qualification/domain/verification.py`
- Add `src/market_regime_alpha/research_qualification/application/verification.py`
- Add `src/market_regime_alpha/research_qualification/ports/verification.py`
- Modify relevant package exports
- Add `src/market_regime_alpha/infrastructure/postgres/queries/research_evaluation_verification.py`
- Modify `src/market_regime_alpha/bootstrap.py`
- Add `tests/refoundation/research_qualification/test_wp11_verifier.py`
- Modify `tests/refoundation/research_qualification/test_wp11_architecture.py`

**Steps:**

1. Add failing typed result/mismatch tests and public bootstrap seam tests.
2. Implement closed mismatch kinds for identity, missing/extra row, order,
   count/hash, calendar/bounds, Target/Outcome compatibility, lifecycle,
   revision visibility, access ordinal, Cartesian roster, receipt/audit/Runtime
   provenance and immutable-fact mutation.
3. Implement `verify_partition` from exact Target/Session/commitment/member
   rows, independently recomputing calendar and population closure.
4. Implement `verify_experiment` from the complete root/child tuple and
   Partition facts.
5. Implement `verify_evaluation_run` through Protocol, ExperimentRun,
   Partition, access/revision, observations, metrics and metric inputs.
6. Add zero-mismatch tests and deliberate owner-table corruption cases under
   the test maintenance seam; every mismatch remains read-only and typed.
7. Add source inspection assertions banning Provider, Market repository,
   bars-to-label, current/latest Outcome, SQL mutation, and Infrastructure
   imports from Domain/Application.

**Checkpoint:** commit formal replay/reconciliation and unknown-commit recovery.

## Task 8 — Focused correctness regression and implementation SHA

**Files:** all directly changed source/tests/DDL; no status promotion yet.

**Steps:**

1. Run the original WP-11 111-node focused set.
2. Run all new composition/calendar/Experiment/recovery/verifier tests.
3. Run focused Ruff/mypy, schema specification, docs links/navigation and
   architecture/import tests.
4. Run `git diff --check`, inspect staged/unstaged scope and confirm
   `.idea/modules.xml` is absent.
5. Commit the final correctness source/test/DDL checkpoint.
6. Record its exact SHA and source/test/baseline tree identities. All later
   qualification evidence binds this SHA.

## Task 9 — Real PostgreSQL concurrency and failure campaigns

**Files:**

- Add or extend focused campaign tests under
  `tests/refoundation/research_qualification/`
- Add reusable test-only PostgreSQL fault helpers under `tests/refoundation/`
  only when existing helpers cannot express the failure

**Concurrency steps:**

1. identical and changed Partition freeze;
2. symmetric protected-overlap inserts;
3. identical and changed complete Experiment roster registration;
4. EvaluationRun open races;
5. two first accesses to one member and global ordinal monotonicity;
6. Outcome correction versus acquisition;
7. identical acquisition replay and changed acquisition identity;
8. Acquire versus Fail and Complete versus Fail;
9. receipt/idempotency races and stale Runtime fence.

**Failure/recovery steps:**

1. serialization failure and deadlock with real PostgreSQL sessions;
2. known transient connection failure and unknown commit result;
3. stale fence and failure-recorder failure;
4. fault after a subset of Partition members, Experiment bindings, access rows,
   observations, Evaluation metrics, and MetricObservation Cartesian rows;
5. exact recovery/replay after every rollback or ambiguous result;
6. verifier proof that no partial root/roster/ledger/terminal state remains.

If any campaign reveals a source/DDL defect, fix it, commit a new
implementation checkpoint, and rerun every affected focused and qualification
gate. Old evidence is discarded.

## Task 10 — Disposable PostgreSQL and representative plan gate

**Steps:**

1. Provision a new explicitly named disposable PostgreSQL 16 database; record
   version, database name/OID/owner and Artifact root.
2. Run empty bootstrap and verify.
3. Create a guarded recreate plan with exact name/OID/owner, backup
   attestation, zero clients and no unexpected objects; record plan hash and
   challenge.
4. Apply guarded recreate and verify identical epoch/baseline/seed/vocabulary/
   catalog checksums.
5. Populate representative WP-11 fixtures and execute
   `EXPLAIN (ANALYZE, BUFFERS)` for commitment→Partition roster, protected
   overlap, cutoff-visible Outcome revision, member ordinal,
   EvaluationObservation→OutcomeMetric and metric-member Cartesian
   reconciliation.
6. Inspect FK-leading indexes, row estimates, loops, buffer usage, sequential
   scans on representative volumes and lock amplification. Do not assert a
   fixed optimizer node shape.

## Task 11 — Full exact-SHA engineering gate

Run, without filtering failures:

```bash
uv sync --frozen --extra dev --extra postgres
uv run python -m pytest -q <frozen WP-11 focused files>
uv run python -m pytest -q tests/refoundation
uv run python -m pytest -q tests/platform
uv run python -m pytest -q tests/persistence/postgres
uv run python -m pytest -q
uv run ruff check .
uv run mypy
uv run python -m build --outdir <disposable build directory>
uv run python scripts/check_docs_links.py
uv run python -m pytest -q tests/scripts/test_check_docs_links.py
uv run python -m pytest -q <architecture/import suites>
git diff --check
```

Run schema/catalog verification and representative plans against the same
fresh qualification database. Inspect wheel/sdist contents and hashes, then
remove only disposable build output. Query repository Actions permissions;
when disabled record exactly
`BLOCKED_BY_REPOSITORY_CONFIGURATION / NOT_RUN`.

## Task 12 — Immutable Verification, status, and merge gate

**Files after all gates pass:**

- Add `docs/references/WP-ARCHITECTURE-REFOUNDATION-11-Research-Validity-Evaluation-Verification.md`
- Update `docs/status/Current-State.md`
- Update `docs/status/Capability-Matrix.md`
- Update `docs/status/Roadmap.md`
- Update relevant current architecture/catalog summaries
- Update `docs/README.md`

**Steps:**

1. Record execution baseline, final implementation SHA/tree identities,
   schema/checksums, closures, every exact command/result, investigated
   failures, concurrency/recovery/replay/plans/static/build evidence, remote-CI
   block, evidence ceiling and NO-GO.
2. Set `WP11_EXIT_GATE = PASS` only if every required local gate passed on the
   exact final SHA. Otherwise record `NO-GO` and stop before WP-12.
3. Validate docs, commit immutable Verification/status, and confirm the branch
   is clean.
4. Fetch `origin/main`; if it changed, reconcile and rerun all affected gates
   before using the Verification.
5. Push the branch, create/update the PR with exact metadata, observe required
   PR validation, and merge only a matching PASS branch.
6. Fetch merged main and prove it contains the exact verified implementation
   and immutable Verification.
7. Only then create a new WP-12 branch/worktree and perform its independent
   preflight/audit/design/TDD/qualification sequence.
