# WP-13 Remaining Decision Support Closure Implementation Plan

> **Status:** CURRENT_STATUS
> **Design Authority:**
> `WP-ARCHITECTURE-REFOUNDATION-13-Remaining-Decision-Support-Design.md`
> **Execution-Time Baseline:**
> `origin/main@6e0ad150057e43a89843eb4fb307e0373d5572ac`
> **Design Checkpoint:** `2aac234`
> **Branch:** `agent/wp-13-remaining-decision-support-closure`
> **Method:** public-seam TDD, narrow UoWs, exact-SHA qualification

## 1. Execution invariants

Each implementation slice starts with a public Domain/Application or PostgreSQL
specification test that fails for the missing behavior. The smallest complete
implementation makes that test pass; refactoring follows only while the same
tests remain green. Tests never obtain authority by inserting incomplete root
rows that the public command could not create.

All persistent changes extend only
`src/market_regime_alpha/infrastructure/postgres/migrations/001_baseline.sql`
and its catalog identity. No `002+`, Model/Calibration, Account/Execution,
Runtime dispatcher, CLI command, Legacy dependency, compatibility writer, or
placeholder is permitted.

Every checkpoint uses:

```text
git diff --check
focused tests for the slice
architecture/import tests when a module boundary changes
```

## 2. Slice 1 — next-generation Qualification roster

### Red tests

Extend:

- `tests/refoundation/decision_support/test_decision_domain.py` for typed
  purpose/role, intentional empty roster, duplicate identity/role rejection,
  deterministic ordered hash, and semantic request-hash sensitivity;
- `tests/refoundation/decision_support/test_decision_application.py` for
  exact-ID preparation, changed roster rejection, no current/latest path, and
  exact replay without re-reading Qualification;
- `tests/refoundation/decision_support/test_decision_postgres.py` for admitted,
  matching-purpose, cutoff, non-superseded and strictly earlier-generation
  validation plus root-last roster closure;
- `tests/refoundation/decision_support/test_decision_schema_specification.py`
  for both concrete roster/member tables, composite FKs, checks and leading
  indexes.

Run the new tests and preserve the expected failure before implementation.

### Implementation

Modify:

- `decision_support/domain/vocabulary.py`: add typed Research purpose and
  Qualification input role;
- `decision_support/domain/model.py`: add
  `RequestedResearchQualification`, immutable snapshots and the roster in
  `OpenDecisionRunRequest`/`DecisionRunAuthority` hashes;
- `decision_support/ports/preparation.py` and `ports/repository.py`: declare the
  Decision-owned exact-ID Qualification preparation and persistence seams;
- `decision_support/application/service.py`: prepare exact decisions before the
  transaction, revalidate them under the existing Decision UoW lock order,
  include them in idempotency and write the roster atomically;
- `infrastructure/postgres/queries/decision_inputs.py`: load only requested
  exact decisions with the declared DecisionTime cutoff; never current/latest;
- `infrastructure/postgres/repositories/decision_runs.py` and
  `decision_uow.py`: lock/revalidate supersession, generation and purpose;
- `001_baseline.sql`: add roster/member tables and deferred complete-root
  guards, and require exactly one reconciled roster per successful DecisionRun.

### Green/refactor checkpoint

Run all Decision Support refoundation tests and the WP-12 qualification tests
that own the parent read semantics. Commit one dependency-coherent checkpoint.

## 3. Slice 2 — Context definitions and PIT assessments

### Red tests

Create:

- `tests/refoundation/decision_support/test_wp13_context_domain.py` for closed
  vocabulary, relational rule shape, Decimal thresholds, status/state
  compatibility, complete ordered metric/source rosters and deterministic
  hashes;
- `tests/refoundation/decision_support/test_wp13_context_application.py` for
  immutable policy registration, exact replay/changed request, complete policy
  kind derivation, explicit unavailable/not-estimable/failed outputs, and a
  proof that no Outcome port is accepted or called;
- `tests/refoundation/decision_support/test_wp13_context_postgres.py` for
  DecisionTime `known_at` cutoffs, exact concrete Market revision/SourceGap
  lineage, cross-Run/cross-policy rejection, closure and rollback;
- schema assertions for policy/metric/assessment/metric-source relations,
  concrete FKs and leading indexes.

### Implementation

Add cohesive files inside the existing bounded context:

- `decision_support/domain/context.py`;
- `decision_support/application/context.py`;
- `decision_support/ports/context.py`;
- `infrastructure/postgres/context_uow.py`;
- `infrastructure/postgres/repositories/decision_context.py`;
- `infrastructure/postgres/queries/decision_context_inputs.py`.

The typed preparation query derives the exact Market/PIT source roster and
values outside the short write transaction. The final Context transaction
locks the DecisionRun, Policy and exact source revisions, revalidates Known
Time, writes all sources/metrics, closes each assessment and then commits.

Extend `001_baseline.sql` with the five Context tables, immutability triggers,
source-shape checks and deferred reconciliation. Export the public commands and
types without importing PostgreSQL from Domain/Application.

### Green/refactor checkpoint

Run Context tests, Market/PIT owner regressions, architecture/import tests and
Decision Support tests. Commit the vertical slice.

## 4. Slice 3 — immutable Strategy Version

### Red tests

Create `test_wp13_strategy_domain.py`, `test_wp13_strategy_application.py` and
PostgreSQL/schema tests proving:

- one stable Strategy family and immutable version;
- exactly one primary change/action mapping;
- complete contiguous non-duplicate Context requirements;
- exactly one typed Signal rule;
- complete Target checkpoint/metric Forecast-rule roster;
- Decimal coefficients/bounds and deterministic child/root hashes;
- direct append-only supersession only;
- exact replay and changed-definition failure;
- root-last closure rejects partial child rosters.

### Implementation

Add:

- `decision_support/domain/strategy.py`;
- `decision_support/application/strategy.py`;
- `decision_support/ports/strategy.py`;
- `infrastructure/postgres/strategy_uow.py`;
- `infrastructure/postgres/repositories/decision_strategies.py`.

Extend `001_baseline.sql` with Strategy, Version, Context requirement, Signal
rule and Forecast rule tables, content-addressed code/config/provenance FKs,
direct-supersession guards, counts/hashes and deferred closure.

### Green/refactor checkpoint

Run Strategy, Target, Artifact, architecture/import and schema tests. Commit.

## 5. Slice 4 — complete Signal and rule-based Forecast

### Red tests

Create Domain/Application/PostgreSQL tests proving:

- Signal is derived for every Candidate, never from a caller roster;
- every required Context kind binds one exact same-Run assessment;
- `PRESENT`, `NO_SIGNAL`, `WAIT`, `UNKNOWN`, `NOT_ESTIMABLE` remain explicit;
- no score is exposed as a probability;
- Forecast is derived for every required Signal × matching commitment;
- every estimate concrete-FKs an exact Target checkpoint/metric;
- V1 calibration is only `UNCALIBRATED` or `NOT_APPLICABLE`;
- no Model table/binding/provider is required;
- missing/mismatched Context, Target, checkpoint or metric fails closed;
- mid-roster failure rolls back all Signal/Forecast rows;
- exact replay and changed request are deterministic.

### Implementation

Add:

- `decision_support/domain/inference.py`;
- `decision_support/application/inference.py`;
- `decision_support/ports/inference.py`;
- `infrastructure/postgres/inference_uow.py`;
- `infrastructure/postgres/repositories/decision_inferences.py`;
- `infrastructure/postgres/queries/decision_inference_inputs.py`.

Pure calculation happens outside the transaction from exact prepared
snapshots. The final transaction re-locks Strategy/Decision/Context and writes
complete roots/children before reconciliation. Extend `001_baseline.sql` with
Signal, Context binding, Forecast and Estimate tables and deferred completeness
guards.

### Green/refactor checkpoint

Run inference plus Candidate/Target/Decision/Context owner regressions. Commit.

## 6. Slice 5 — Opportunity and falsifiable Thesis

### Red tests

Create Domain/Application/PostgreSQL tests proving:

- Opportunity derives the full DecisionRun × Strategy Signal/Forecast roster;
- exact Candidate, Target, Commitment, Signal, Forecast, Strategy and complete
  Context bindings agree;
- unavailable inputs remain typed no-action/wait/not-estimable facts;
- no Risk, quantity or account field exists;
- Thesis has a complete non-empty ordered typed condition roster;
- condition source/operator/unit/missing/invalidation semantics are relational;
- revision is append-only direct supersession and old content is unchanged;
- exact replay/changed request and injected child failure are atomic.

### Implementation

Add:

- `decision_support/domain/opportunity.py`;
- `decision_support/application/opportunity.py`;
- `decision_support/ports/opportunity.py`;
- `infrastructure/postgres/opportunity_uow.py`;
- `infrastructure/postgres/repositories/decision_opportunities.py`;
- `infrastructure/postgres/queries/decision_opportunity_inputs.py`.

Add Opportunity/Context/Thesis/Condition tables, concrete composite FKs,
append-only supersession and closure triggers to `001_baseline.sql`.

### Green/refactor checkpoint

Run Opportunity plus all upstream WP-13 tests. Commit.

## 7. Slice 6 — complete Portfolio Proposal

### Red tests

Create Domain/Application/PostgreSQL tests proving:

- immutable content-addressed `EQUAL_WEIGHT_ACTIONABLE` policy;
- Decimal-only constraints and deterministic rounding/remainder allocation;
- proposal derives every exact Opportunity and writes one line per member;
- included/excluded/not-estimable rosters and totals reconcile;
- empty/no-actionable roster produces explicit `NO_ACTION`;
- caller cannot select lines or weights;
- exact replay, changed request, concurrent identical requests and injected
  mid-Cartesian failure leave one complete truth.

### Implementation

Add Portfolio Domain/Application/ports, `portfolio_uow.py`, repository and
typed input query. Extend `001_baseline.sql` with Policy/Proposal/Line,
immutable definition guards, complete roster/totals checks, concrete FKs and
leading indexes.

### Green/refactor checkpoint

Run Portfolio plus all upstream WP-13 tests. Commit.

## 8. Slice 7 — Decision-Support-only Risk

### Red tests

Create Domain/Application/PostgreSQL tests proving:

- immutable non-empty complete typed Risk rule roster;
- every global or line-scoped rule input gets one reason;
- PASS/FAIL/UNKNOWN/NOT_APPLICABLE are preserved;
- only complete reasons permit terminal AUTHORIZED/REJECTED/UNKNOWN/NO_ACTION;
- `authority_scope` is always `DECISION_SUPPORT_ONLY`;
- rejection cannot be bypassed by a different idempotency key;
- no Account/Intent/Broker/Order/Fill/Position relation or application import;
- Complete-vs-fail/concurrent identical/changed request behavior produces one
  terminal truth with no partial reason roster.

### Implementation

Add Risk Domain/Application/ports, `risk_uow.py`, repository and input query.
Extend `001_baseline.sql` with Policy/Rule/Decision/Reason, constant-scope
checks, complete rule × applicable-line closure, append-only guards, concrete
FKs and indexes.

### Green/refactor checkpoint

Run all WP-13 focused tests and architecture/import checks. Commit.

## 9. Slice 8 — sole composition and read-only verifier

### Red tests

Extend `tests/refoundation/test_bootstrap_cli.py` to prove the sole
`bootstrap_application` constructs and exposes every WP-13 command without a
Runtime dispatcher or CLI route. Add architecture tests rejecting PostgreSQL,
Legacy, Outcome and Execution imports across prohibited seams.

Create `test_wp13_verification_postgres.py` proving the verifier recomputes:

- Decision Target/commitment/reference and Qualification roster closure;
- Context definition/source/result closure and PIT cutoffs;
- Strategy definitions and Candidate Signal completeness;
- Commitment Forecast/Estimate completeness and calibration ceiling;
- Opportunity/Context and Thesis/Condition closure;
- Opportunity/Portfolio Cartesian closure and Decimal totals;
- Risk Rule/Reason closure and constant authority scope;
- receipt/audit/Runtime fence and Artifact provenance.

Fault injection must yield `matched = false` and a positive mismatch count;
normal replay yields exactly `matched = true, mismatch_count = 0`. The verifier
must be read-only and must expose no Provider, Outcome or current/latest port.

### Implementation

Add `decision_support/application/verification.py` orchestration over narrow
typed verification ports and PostgreSQL query providers. Update exports and
`bootstrap.py` to compose all WP-13 services/UoWs/providers once. Add no CLI or
Runtime dispatch entry.

### Green/refactor checkpoint

Run bootstrap, verifier, architecture/import and all WP-13 focused tests.
Commit the final implementation checkpoint.

## 10. Exact-SHA engineering qualification

Freeze the implementation SHA only after all focused regressions pass. If any
qualification command requires a code/schema/test change, create a new
checkpoint SHA and rerun every affected gate; no old evidence backs new code.

Use a fresh disposable PostgreSQL 16 instance and record exact database name,
OID, server version, schema epoch, baseline SHA-256 and catalog SHA-256. Run:

```text
uv sync --frozen --extra dev --extra postgres
clean bootstrap
verify
guarded exact-OID recreate
verify
```

Run real PostgreSQL concurrency races for each owner: identical and changed
requests, Qualification supersession vs Decision open, Context source revision
vs assess, Signal/Forecast roster races, Opportunity/Thesis supersession,
Portfolio proposal races and Risk terminal races. Prove one canonical root, no
fork, no partial child roster and no bypass.

Run injected failure/recovery for serialization, deadlock, transient
connection, unknown commit, stale fence, receipt/failure-recorder failure and
every root/child boundary. Unknown commit must use exact probe/replay rather
than blind mutation.

Run representative `EXPLAIN (ANALYZE, BUFFERS)` for:

- exact Qualification roster resolution at DecisionTime;
- Context Market-source roster and cutoff;
- Candidate → Signal and Commitment → Forecast roster derivation;
- Opportunity → Portfolio Cartesian reconciliation;
- Risk rule × applicable line reconciliation;
- full read-only verifier joins.

Then run the repository gates exactly:

```bash
python -m pytest -q tests/refoundation/decision_support
python -m pytest -q tests/refoundation
python -m pytest -q tests/platform
python -m pytest -q tests/persistence/postgres
python -m pytest -q
python -m ruff check .
python -m mypy
python -m build
python scripts/check_docs_links.py
python -m pytest -q tests/scripts/test_check_docs_links.py
git diff --check
```

Record every gate as PASS/FAIL/NOT_RUN/BLOCKED. Remote CI may be PASS only from
real enabled remote evidence; repository-disabled CI is
`BLOCKED_BY_REPOSITORY_CONFIGURATION / NOT_RUN`.

## 11. Verification, merge and stop boundary

Only after the exact implementation SHA passes all P0/P1 gates, add a new
immutable WP-13 Verification containing source/test/schema tree identities,
database/checksum evidence, exact commands/results, concurrency,
failure/recovery, replay, plans, full regression/static/build, evidence ceiling
and NO-GO boundaries. Update Current State, Roadmap, Capability Matrix and docs
navigation without changing WP-08 through WP-12 Verification records.

Push, create/update the WP-13 PR, re-fetch latest main, rebase/requalify if main
changed, merge, re-fetch and prove remote main contains the exact Verification
and `WP13_EXIT_GATE = PASS`. Only then create a fresh WP-14 branch/worktree.
