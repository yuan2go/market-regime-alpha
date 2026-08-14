# Multi-Strategy Platform Convergence Implementation Plan

> **Status:** CURRENT_STATUS
> **Authority:** Dependency-ordered execution plan for ADR-013
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-14
> **Code Evidence:** `docs/architecture/decisions/ADR-013-Multi-Strategy-Platform-Convergence.md`, `src/market_regime_alpha`, `tests`

> **For agentic workers:** Execute inline in dependency order. Each task ends in an independently reviewable checkpoint; critical invariants use red-green TDD through the public Strategy, Portfolio, PostgreSQL, and runtime inspection interfaces.

**Goal:** Deliver two materially different Strategy Families through one PostgreSQL-centered runtime, Portfolio, Position-allocation, outcome, attribution, evidence, replay, and inspection path.

**Architecture:** Add one deep Strategy module behind the existing Continuous and Research Session seams. Reuse Candidate, Target, runtime journal, observed Fill/physical Position, and PostgreSQL composition; do not introduce a scheduler, database, broker writer, or generic governance framework.

**Tech Stack:** Python 3.12, immutable dataclasses, psycopg/PostgreSQL 16, forward SQL migration 085, pytest, Ruff, mypy, setuptools build.

## Global Constraints

- PostgreSQL 16 remains the only persistent runtime and business database.
- `CONTINUOUS_RESEARCH` remains the sole all-day control plane.
- Candidate, Prediction, Signal, Decision, Order, Fill, Position, Market Outcome, and Strategy Outcome remain distinct.
- Physical Position comes only from observed Fill.
- Free/public data remains `EXPLORATORY` and `PIT_INCOMPLETE`; Formal OOS, calibration, economic support, prospective proof, Production Admission, and broker authority remain false.
- Migration is forward-only and must pass fresh, upgrade, idempotency, concurrency, and replay checks.
- `.idea/modules.xml` is never modified, staged, overwritten, stashed, or committed.

---

### Task 1: Baseline documentation and immutable Strategy contracts

**Files:**
- Modify: `scripts/check_docs_links.py`
- Modify: `tests/scripts/test_check_docs_links.py`
- Create: `src/market_regime_alpha/strategies/contracts.py`
- Create: `src/market_regime_alpha/strategies/path_outcomes.py`
- Modify: `src/market_regime_alpha/strategies/__init__.py`
- Test: `tests/strategies/test_multi_strategy_contracts.py`
- Test: `tests/strategies/test_path_outcomes.py`

**Interfaces:**
- Produces: `StrategyContract`, `StrategyVersion`, `StrategyRuntimeInput`, `StrategyRun`, `StrategyProposal`, `GateAttribution`, `StrategyPathOutcome`, `measure_path_outcome`.

- [ ] Write failing tests proving content identity changes for every result-affecting contract field, `NO_ACTION != HOLD`, physical Position is absent from Strategy Proposal, and Strategy evidence identity includes exact Target/Dataset/PIT/Universe/Decision Time/cost/evaluation/code/config references.
- [ ] Run the focused tests and confirm failure because the public Strategy interfaces do not exist.
- [ ] Implement the immutable contracts with canonical hashes and strict restoration; reuse `ArtifactId`, `RuntimeAuthorityMode`, `RuntimeArtifactReference`, and existing Target references.
- [ ] Add a deterministic path kernel that independently computes MFE/MAE, first-passage ordering, time-to-MFE, continuation/failure, post-exit opportunity loss, and avoided drawdown.
- [ ] Add `Canonical-Overall-Design.md` and `CANONICAL_TARGET_ARCHITECTURE` to the documentation validator, then prove the latest-main baseline regression is closed.
- [ ] Run focused tests, Ruff, mypy for the new files, and `git diff --check`; commit the contract/path slice.

### Task 2: Overnight and Swing policies behind one Strategy Runtime seam

**Files:**
- Create: `src/market_regime_alpha/strategies/policies.py`
- Create: `src/market_regime_alpha/strategies/runtime.py`
- Test: `tests/strategies/test_multi_strategy_runtime.py`

**Interfaces:**
- Consumes: `StrategyRuntimeInput`, `StrategyContract`, existing `CandidateSet`.
- Produces: `MultiStrategyRuntime.execute(input) -> MultiStrategyCycle` and frozen canonical Overnight/Swing Strategy Versions.

- [ ] Write a failing tracer test where one Candidate artifact drives both family runs while each emits a different action under its own state/Target contract.
- [ ] Write failing tests for explicit Eligibility/Ranking/Candidate/Entry attribution, empty/data-insufficient funnels, Swing `ENTER/HOLD/ADD/REDUCE/EXIT`, Overnight next-session `EXIT`, and no implicit HOLD.
- [ ] Implement `OvernightPolicy` and `SwingStatePolicy` behind one small policy interface; version every threshold that changes behavior.
- [ ] Implement `MultiStrategyRuntime.execute` as the only strategy orchestration interface and ensure all Candidate records receive a terminal action/rejection attribution.
- [ ] Execute the same frozen input as `HISTORICAL`, `REPLAY`, and `SHADOW`; assert policy/proposal semantic hashes match while origin lineage remains explicit.
- [ ] Run focused tests and quality checks; commit the shared-runtime slice.

### Task 3: Simple Strategy and cross-strategy Portfolio baseline

**Files:**
- Create: `src/market_regime_alpha/strategies/portfolio.py`
- Test: `tests/strategies/test_cross_strategy_portfolio.py`

**Interfaces:**
- Consumes: multiple `StrategyProposal` objects plus one versioned Portfolio policy.
- Produces: `CrossStrategyPortfolioDecision` and exact per-strategy sleeve lines.

- [ ] Write failing tests for Top-K Equal and Score weighting, per-strategy budgets, single-name/gross caps, opposing proposals on the same symbol, and deterministic conflict reasons.
- [ ] Implement a pure Portfolio kernel that accepts Strategy Proposals, nets cross-strategy conflicts, preserves every accepted/rejected sleeve line, and emits no Order or Fill.
- [ ] Prove strategy order does not change the decision hash and a Risk rejection cannot be bypassed by a Strategy proposal.
- [ ] Run focused tests and quality checks; commit the Portfolio slice.

### Task 4: PostgreSQL Strategy business facts and Fill allocation

**Files:**
- Create: `src/market_regime_alpha/persistence/postgres/migrations/085_multi_strategy_platform.sql`
- Create: `src/market_regime_alpha/strategies/postgres_repository.py`
- Modify: `src/market_regime_alpha/persistence/postgres/schema.py`
- Modify: `src/market_regime_alpha/persistence/repository_factory.py`
- Test: `tests/persistence/postgres/test_multi_strategy_platform.py`
- Test: `tests/persistence/postgres/test_multi_strategy_migrations.py`

**Interfaces:**
- Produces: `PostgresStrategyPlatformRepository.register_version`, `record_cycle`, `get_cycle`, `replay_cycle`, `allocate_fill`, `read_sleeve`, `record_path_outcome`, `record_feedback`, and version-scoped query methods.

- [ ] Write failing PostgreSQL tests for fresh migration catalog, Strategy Version idempotency/conflict, cycle/run/proposal/gate restoration, and exact replay.
- [ ] Add migration 085 tables and supporting indexes/triggers for Strategy Version, cycle/run/gate/proposal, cross-strategy Portfolio, Fill Allocation, Path Outcome, and typed feedback.
- [ ] Implement one PostgreSQL repository at the real seam; avoid one-interface-per-table wrappers.
- [ ] Write failing concurrency tests where two allocations race for one observed physical Fill; prove total allocation never exceeds the immutable Fill quantity and a sleeve cannot sell below zero.
- [ ] Implement serialized Fill allocation and derive sleeve positions only from observed Fill allocations; never create a second physical Position writer.
- [ ] Prove migration 001→085 fresh, 084→085 upgrade, repeated apply, and concurrent apply; run focused tests and commit.

### Task 5: Canonical Continuous composition and deterministic replay

**Files:**
- Create: `src/market_regime_alpha/application/continuous_research/strategy_runtime.py`
- Modify: `src/market_regime_alpha/application/continuous_research/journal.py`
- Modify: `src/market_regime_alpha/application/continuous_research/composition.py`
- Modify: `src/market_regime_alpha/application/continuous_research/free_data_runtime.py`
- Modify: `src/market_regime_alpha/application/continuous_research/runner.py`
- Modify: `src/market_regime_alpha/cli/continuous_research.py`
- Test: `tests/application/continuous_research/test_strategy_runtime_child.py`
- Modify: `tests/persistence/postgres/test_free_data_continuous_runtime.py`
- Modify: `tests/persistence/postgres/test_free_data_stateful_runtime.py`

**Interfaces:**
- Produces: one `STRATEGY_RUNTIME` Continuous child receipt that references both Strategy Runs and the cross-strategy Portfolio decision.

- [ ] Write a failing composition test proving a Continuous tick cannot complete without a durable Strategy child and that Production/free-data still fails before mutation.
- [ ] Implement a thin child adapter that reloads the exact Candidate owner and Target protocols, registers/reloads both Strategy Versions, executes one cycle, and persists under the active tick fence.
- [ ] Add the Strategy child after Decision Summary without changing the scheduler, provider, state, or decision owners.
- [ ] Prove crash/retry idempotency, no-material-change reuse, complete Continuous replay, and two-family output in one tick.
- [ ] Add a bounded historical adapter that invokes the same Strategy Runtime interface and prove Historical/Replay/Shadow policy hashes converge.
- [ ] Run focused E2E/PostgreSQL tests and commit the composition slice.

### Task 6: Strategy outcome, attribution, challenger, and qualification loop

**Files:**
- Create: `src/market_regime_alpha/strategies/feedback.py`
- Modify: `src/market_regime_alpha/strategies/postgres_repository.py`
- Test: `tests/strategies/test_strategy_feedback.py`
- Test: `tests/persistence/postgres/test_strategy_feedback.py`

**Interfaces:**
- Produces: `StrategyAttribution`, `StrategyChallenger`, `StrategyEvidence`, and `StrategyQualificationAssessment` stored as typed feedback artifacts.

- [ ] Write failing tests that bind one path/strategy outcome to explicit regime/context, candidate gate, forecast, action policy, Portfolio/Risk, cost, and execution attribution layers.
- [ ] Implement attribution and Challenger creation without mutating the active Strategy Version.
- [ ] Implement Strategy Evidence with exact Dataset/PIT/Universe/Decision Time/Target/Horizon/Strategy Version/cost/evaluation/code/config identity.
- [ ] Implement dimensional qualification that remains blocked unless every required owner-resolved dimension is true; default free-data assessments preserve all current false claims.
- [ ] Prove querying Overnight evidence cannot return Swing evidence and vice versa.
- [ ] Run focused tests and commit the feedback slice.

### Task 7: Runtime inspection, metrics, and operator proof

**Files:**
- Modify: `src/market_regime_alpha/application/runtime_operations/query.py`
- Modify: `src/market_regime_alpha/application/runtime_operations/observability.py`
- Modify: `src/market_regime_alpha/cli/continuous_research.py`
- Test: `tests/application/runtime_operations/test_strategy_query.py`
- Test: `tests/cli/test_continuous_research_cli.py`

**Interfaces:**
- Produces: `inspect-strategy`, `inspect-portfolio`, and Strategy fields in canonical trace/metrics.

- [ ] Write failing query tests for two Strategy Versions, gate/rejection distributions, proposal/Portfolio lineage, sleeve reconciliation, and missing qualification dimensions.
- [ ] Extend the read-only DAG and metrics projections from existing PostgreSQL owner rows; do not create an observability fact store.
- [ ] Add CLI read operations and RBAC resource coverage.
- [ ] Run an exact PostgreSQL operator proof: register both families, execute one composed cycle, replay it, inspect it, and capture hashes/counts/ceilings.
- [ ] Run focused tests and commit the operator slice.

### Task 8: Canonical documentation, debt convergence, and final gates

**Files:**
- Modify: `docs/README.md`
- Modify: `docs/architecture/Canonical-Overall-Design.md`
- Modify: `docs/architecture/System-Architecture.md`
- Modify: `docs/architecture/Authority-Map.md`
- Modify: `docs/architecture/Data-and-Evidence-Architecture.md`
- Modify: `docs/architecture/Research-Strategy-Lifecycle.md`
- Modify: `docs/status/Current-State.md`
- Modify: `docs/status/Capability-Matrix.md`
- Modify: `docs/status/Gap-Register.md`
- Modify: `docs/status/Roadmap.md`
- Modify: `docs/operations/Runtime-Runbook.md`
- Modify: `docs/research/Negative-and-Inconclusive-Results.md` only if new empirical evidence exists.

**Interfaces:**
- Produces: documentation that distinguishes implemented engineering proof from unestablished research/Production claims.

- [ ] Remove or reclassify only compatibility/runtime paths proven superseded by current call-chain and import evidence; retain historical readers and immutable migrations.
- [ ] Update canonical/status/gap/roadmap/runbook documents to exact code, migration, runtime, test, and evidence facts.
- [ ] Run documentation links, focused tests, all PostgreSQL integration tests, full pytest, Ruff, mypy, build, and `git diff --check`; classify every command PASS/FAIL/NOT_RUN/BLOCKED.
- [ ] Perform architecture, code, migration, recovery/replay, and research-validity self-review; fix findings and rerun affected gates.
- [ ] Inspect final diff/staged scope, exclude `.idea/modules.xml` and local artifacts, make logical final commits, push the feature branch, and create a Draft PR to `main`.
