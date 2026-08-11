# Phase D Research Execution Implementation Plan

> **Status:** ROADMAP
> **Authority:** Temporary execution checklist for ADR-008; not implementation or evidence authority
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-11
> **Code Evidence:** `src/market_regime_alpha`, `src/market_regime_alpha/persistence/postgres/migrations/*.sql`, `tests`

> **For implementers:** Execute this plan continuously in dependency order. Use
> tests first for each behavior, preserve one PostgreSQL fact owner, and make a
> dependency-coherent checkpoint commit after each task. Do not claim Formal PIT,
> Formal OOS, calibration or Production authority from local evidence.

**Goal:** Deliver one durable, resumable historical research loop that shares
runtime scope, decision logic, observations, portfolio facts, performance facts
and a real exploratory forecast model with the existing Continuous Research
system.

**Architecture:** ADR-008 selects a Shared Decision Session Kernel plus a
PostgreSQL Historical Journal. Historical execution is a batch child of the one
Continuous Runtime architecture, not a second Backtest engine. Every artifact
is immutable/content-addressed and every resumable transition is protected by
expected predecessor, lease and fencing checks.

**Technology:** Python 3.12, frozen `uv` environment, dataclasses/enums/Decimal,
psycopg/PostgreSQL 16, NumPy for deterministic linear algebra, pytest, Ruff,
Mypy and the existing CLI/RepositoryFactory boundaries.

## Task 1: Freeze the shared session and Runtime Scope contracts

**Files:**

- Create: `src/market_regime_alpha/application/research_session/__init__.py`
- Create: `src/market_regime_alpha/application/research_session/contracts.py`
- Create: `src/market_regime_alpha/universe/runtime_scope.py`
- Create: `src/market_regime_alpha/universe/postgres_runtime_scope.py`
- Create: `src/market_regime_alpha/persistence/postgres/migrations/058_runtime_scope_authority.sql`
- Modify: `src/market_regime_alpha/persistence/repository_factory.py`
- Modify: `src/market_regime_alpha/persistence/postgres/schema.py`
- Test: `tests/application/research_session/test_contracts.py`
- Test: `tests/universe/test_runtime_scope.py`
- Test: `tests/universe/test_postgres_runtime_scope.py`
- Test: `tests/persistence/postgres/test_migrations.py`

**Step 1: Write failing contract tests.**

Cover canonical identity for `ResearchDecisionSessionRequest`, explicit
`SessionClock`, `DataAuthorityMode`, `ExecutionMode` and qualification; reject
naive timestamps, unsorted/duplicate symbols, free-data Formal mode and hidden
defaults. Cover `ResearchUniversePolicy` source selectors and versioned
eligibility/liquidity/minimum-history policy references.

**Step 2: Run the focused tests and verify RED.**

Run:

```bash
python -m pytest -q tests/application/research_session/test_contracts.py tests/universe/test_runtime_scope.py
```

Expected: import/contract failures because the contracts do not exist.

**Step 3: Implement pure contracts and scope evaluation.**

Use typed status and reason values:

```python
class RuntimeScopeDecision(str, Enum):
    INCLUDED = "INCLUDED"
    EXCLUDED = "EXCLUDED"
    UNKNOWN = "UNKNOWN"

@dataclass(frozen=True, slots=True)
class RuntimeScopeReceipt:
    policy_id: ArtifactId
    as_of: datetime
    members: tuple[RuntimeScopeMember, ...]
    input_references: tuple[ArtifactReference, ...]
    evidence_authority: str
    content_hash: str
```

Resolve the existing free full-A security master and eligibility owner at the
exact as-of time. Never substitute the latest snapshot for a missing historical
snapshot. Preserve every excluded/unknown member and make runnable symbols only
the ordered `INCLUDED` subset.

**Step 4: Add the append-only PostgreSQL owner.**

Migration 058 creates immutable policy, scope receipt, input reference and
member tables, no-update/delete triggers, unique content-hash/idempotency
constraints and indexes on `(policy_id, as_of)` and member symbol. Repository
methods register/resolve/replay and verify hashes after reload.

**Step 5: Run unit and PostgreSQL tests and verify GREEN.**

Run:

```bash
python -m pytest -q tests/application/research_session/test_contracts.py tests/universe/test_runtime_scope.py
python -m pytest -q tests/universe/test_postgres_runtime_scope.py tests/persistence/postgres/test_migrations.py
```

Expected: all pass; duplicate identical receipts are idempotent and conflicting
content is rejected.

**Step 6: Commit.**

```bash
git add src/market_regime_alpha/application/research_session src/market_regime_alpha/universe/runtime_scope.py src/market_regime_alpha/universe/postgres_runtime_scope.py src/market_regime_alpha/persistence/postgres/migrations/058_runtime_scope_authority.sql src/market_regime_alpha/persistence/repository_factory.py src/market_regime_alpha/persistence/postgres/schema.py tests/application/research_session tests/universe/test_runtime_scope.py tests/universe/test_postgres_runtime_scope.py tests/persistence/postgres/test_migrations.py
git diff --cached --check
git commit -m "feat: own immutable research runtime scopes"
```

## Task 2: Add the Shared Decision Session Kernel and Historical Journal

**Files:**

- Create: `src/market_regime_alpha/application/research_session/kernel.py`
- Create: `src/market_regime_alpha/application/historical_research/__init__.py`
- Create: `src/market_regime_alpha/application/historical_research/contracts.py`
- Create: `src/market_regime_alpha/application/historical_research/postgres_journal.py`
- Create: `src/market_regime_alpha/application/historical_research/runner.py`
- Create: `src/market_regime_alpha/application/historical_research/replay.py`
- Create: `src/market_regime_alpha/persistence/postgres/migrations/059_historical_research_journal.sql`
- Modify: `src/market_regime_alpha/application/continuous_research/free_data_runtime.py`
- Modify: `src/market_regime_alpha/persistence/repository_factory.py`
- Modify: `src/market_regime_alpha/persistence/postgres/schema.py`
- Modify: `src/market_regime_alpha/cli/continuous_research.py`
- Test: `tests/application/research_session/test_kernel.py`
- Test: `tests/application/historical_research/test_runner.py`
- Test: `tests/application/historical_research/test_postgres_journal.py`
- Test: `tests/application/historical_research/test_replay.py`
- Test: `tests/cli/test_continuous_research_cli.py`

**Step 1: Write failing kernel and journal tests.**

Use a deterministic fake owner port to prove that Live Research and Historical
Research produce the same canonical decision-stage outputs for the same scope,
clock and owner facts. Cover calendar gaps, single day, ranges, ordered stage
advancement, interruption after every stage, expired leases, stale fencing,
same-command idempotency, hash conflicts and replay corruption.

**Step 2: Run focused tests and verify RED.**

```bash
python -m pytest -q tests/application/research_session/test_kernel.py tests/application/historical_research/test_runner.py tests/application/historical_research/test_postgres_journal.py tests/application/historical_research/test_replay.py
```

**Step 3: Extract the kernel seam.**

Define a narrow owner-backed port instead of copying runtime logic:

```python
class ResearchDecisionSessionOwner(Protocol):
    def resolve_scope(self, request: ResearchDecisionSessionRequest) -> RuntimeScopeReceipt: ...
    def compute_decision(self, request: ResearchDecisionSessionRequest, scope: RuntimeScopeReceipt) -> DecisionSessionReceipt: ...
```

Move only deterministic session composition behind this seam. The current
`CanonicalFreeDataResearchComposition` remains the concrete Live owner adapter;
Historical uses an archive/PIT adapter but calls the same kernel.

**Step 4: Add the durable run/stage/attempt/event schema.**

Migration 059 creates one immutable run definition plus session, stage,
attempt, receipt and event tables. Store request hash, frozen calendar/scope/
policy/code identities, expected predecessor, attempt number, lease expiry,
fencing token, terminal status and result reference. Add CAS updates only for
lease/state columns; business receipts remain append-only.

**Step 5: Implement runner, resume and replay.**

The runner enumerates only frozen calendar sessions, always applies business
stages chronologically, checkpoints committed owner receipts and returns typed
`COMPLETE`, `BLOCKED` or `FAILED` results. Resume re-enters the first incomplete
stage. Replay reads original references and compares recomputed canonical hash
without mutation.

**Step 6: Extend the existing CLI.**

Add subcommands `historical-run`, `historical-resume`, `historical-report` and
`historical-replay` below `continuous-research`. Inputs are explicit run policy
or run id; commands never accept a second database backend or provider bypass.

**Step 7: Run focused and compatibility tests, then commit.**

```bash
python -m pytest -q tests/application/research_session tests/application/historical_research tests/application/continuous_research tests/cli/test_continuous_research_cli.py
git diff --check
git add src/market_regime_alpha/application/research_session src/market_regime_alpha/application/historical_research src/market_regime_alpha/application/continuous_research/free_data_runtime.py src/market_regime_alpha/persistence/postgres/migrations/059_historical_research_journal.sql src/market_regime_alpha/persistence/repository_factory.py src/market_regime_alpha/persistence/postgres/schema.py src/market_regime_alpha/cli/continuous_research.py tests/application/research_session tests/application/historical_research tests/application/continuous_research tests/cli/test_continuous_research_cli.py
git diff --cached --check
git commit -m "feat: run replayable historical research sessions"
```

## Task 3: Build Strategy and Portfolio observations from owners

**Files:**

- Create: `src/market_regime_alpha/application/strategy_shadow/observation_builder.py`
- Create: `src/market_regime_alpha/application/strategy_shadow/postgres_observations.py`
- Create: `src/market_regime_alpha/persistence/postgres/migrations/060_shadow_observation_authority.sql`
- Modify: `src/market_regime_alpha/application/strategy_shadow/operator.py`
- Modify: `src/market_regime_alpha/application/strategy_shadow/portfolio_operator.py`
- Modify: `src/market_regime_alpha/persistence/repository_factory.py`
- Modify: `src/market_regime_alpha/persistence/postgres/schema.py`
- Modify: `src/market_regime_alpha/cli/continuous_research.py`
- Test: `tests/application/strategy_shadow/test_observation_builder.py`
- Test: `tests/application/strategy_shadow/test_postgres_observations.py`
- Test: `tests/application/strategy_shadow/test_strategy_shadow_runtime.py`
- Test: `tests/application/strategy_shadow/test_portfolio_operator.py`
- Test: `tests/cli/test_continuous_research_cli.py`

**Step 1: Write failing builder tests.**

Test Candidate/Signal/Forecast/State/market/cost/position resolution, exact
effective-time joins, sorted results, prior portfolio linkage and all four
provenance categories. Test missing price, ADV, status, limit, session, cost,
liquidity and prior-state references individually; each must fail closed with a
stable reason. Test explicit immutable overrides and reject silent override of
an observed fact.

**Step 2: Implement owner ports and immutable receipts.**

Builders return either a complete typed observation plus all source references
or a blocked receipt. They never call Provider clients. Migration 060 persists
request, source bindings, value provenance, override receipt and canonical
observation hash; content substitution raises an integrity error.

**Step 3: Integrate automatic operator modes.**

Add `run_auto(...)` to the existing operators and `--auto` to `strategy-day`
and `portfolio-shadow-day`. Keep explicit JSON backward-compatible and label all
such values `OPERATOR_INPUT`. Approval remains a separate command/owner.

**Step 4: Verify and commit.**

```bash
python -m pytest -q tests/application/strategy_shadow tests/cli/test_continuous_research_cli.py
git diff --check
git add src/market_regime_alpha/application/strategy_shadow src/market_regime_alpha/persistence/postgres/migrations/060_shadow_observation_authority.sql src/market_regime_alpha/persistence/repository_factory.py src/market_regime_alpha/persistence/postgres/schema.py src/market_regime_alpha/cli/continuous_research.py tests/application/strategy_shadow tests/cli/test_continuous_research_cli.py
git diff --cached --check
git commit -m "feat: build shadow observations from fact owners"
```

## Task 4: Own multi-period performance and attribution

**Files:**

- Create: `src/market_regime_alpha/application/strategy_shadow/performance.py`
- Create: `src/market_regime_alpha/application/strategy_shadow/postgres_performance.py`
- Create: `src/market_regime_alpha/persistence/postgres/migrations/061_shadow_performance_authority.sql`
- Modify: `src/market_regime_alpha/persistence/repository_factory.py`
- Modify: `src/market_regime_alpha/persistence/postgres/schema.py`
- Modify: `src/market_regime_alpha/cli/continuous_research.py`
- Test: `tests/application/strategy_shadow/test_performance.py`
- Test: `tests/application/strategy_shadow/test_postgres_performance.py`
- Test: `tests/application/strategy_shadow/test_performance_reconciliation.py`
- Test: `tests/cli/test_continuous_research_cli.py`

**Step 1: Write metric edge-case tests.**

Use exact Decimal fixtures for equity curve, returns, costs, exposures and
trades. Cover all requested metrics, zero/one sample, zero downside, zero
drawdown, missing benchmark, sparse months/years and insufficient MFE/MAE.
Every undefined value must be `NOT_ESTIMABLE`, not `NaN`, infinity or zero.

**Step 2: Write attribution reconciliation tests.**

Prove symbol + cash + cost contributions reconcile to NAV change at every
session and across the period. Cover regime/theme/factor/signal/entry/exit/rank
dimensions with exact owner references and verify missing dimensions remain
typed `NOT_ESTIMABLE`.

**Step 3: Implement pure aggregation and PostgreSQL report owner.**

Freeze metric definition version, sessions-per-year, benchmark/risk-free
policy, comparison selectors and reconciliation tolerance. Migration 061 stores
report, input states, metrics, return periods, attribution rows and comparison
references with immutable triggers.

**Step 4: Add `historical-report`/`performance-report` output and commit.**

```bash
python -m pytest -q tests/application/strategy_shadow/test_performance.py tests/application/strategy_shadow/test_postgres_performance.py tests/application/strategy_shadow/test_performance_reconciliation.py tests/cli/test_continuous_research_cli.py
git diff --check
git add src/market_regime_alpha/application/strategy_shadow src/market_regime_alpha/persistence/postgres/migrations/061_shadow_performance_authority.sql src/market_regime_alpha/persistence/repository_factory.py src/market_regime_alpha/persistence/postgres/schema.py src/market_regime_alpha/cli/continuous_research.py tests/application/strategy_shadow tests/cli/test_continuous_research_cli.py
git diff --cached --check
git commit -m "feat: own shadow performance and attribution"
```

## Task 5: Train and execute the exploratory multi-target model

**Files:**

- Create: `src/market_regime_alpha/application/research_validation/research_model.py`
- Create: `src/market_regime_alpha/application/research_validation/postgres_research_model.py`
- Create: `src/market_regime_alpha/forecasting/regularized_linear.py`
- Create: `src/market_regime_alpha/persistence/postgres/migrations/062_research_model_artifact.sql`
- Modify: `src/market_regime_alpha/application/research_validation/formal_forecast_computation.py`
- Modify: `src/market_regime_alpha/application/continuous_research/free_data_runtime.py`
- Modify: `src/market_regime_alpha/persistence/repository_factory.py`
- Modify: `src/market_regime_alpha/persistence/postgres/schema.py`
- Modify: `src/market_regime_alpha/cli/continuous_research.py`
- Test: `tests/forecasting/test_regularized_linear.py`
- Test: `tests/application/research_validation/test_research_model.py`
- Test: `tests/application/research_validation/test_postgres_research_model.py`
- Test: `tests/application/research_validation/test_formal_forecast_computation.py`
- Test: `tests/application/research_validation/test_model_partition_isolation.py`
- Test: `tests/cli/test_continuous_research_cli.py`

**Step 1: Write failing math and determinism tests.**

Test deterministic ridge/logistic-score fitting, stable feature ordering,
constant/degenerate target rejection, missingness indicators, robust scaling,
identical inference bytes and no probability label on uncalibrated barrier
scores. Avoid a global RNG; any fold seed is frozen in the request identity.

**Step 2: Write training-isolation tests.**

Build owner-referenced rows with decision/effective/availability times. Reject
future features, target-bearing inputs, overlapping train/validation/OOS,
purge/embargo violations and OOS access during selection. Verify walk-forward
folds only select hyperparameters from train/validation diagnostics.

**Step 3: Implement the artifact and training owner.**

Migration 062 stores training request, exact dataset/feature/factor/target/code/
config lineage, partitions/folds, candidate diagnostics, selected artifact,
coefficient heads and terminal negative result. The artifact schema is
content-addressed and contains all preprocessing state required for inference.

**Step 4: Implement research inference and the installed executor.**

`RegularizedLinearForecastExecutor` accepts only the exact implementation,
artifact schema, model-definition hash, config hash and code identity. It
returns continuous estimates and raw barrier logits. Unsupported model,
substitution, incomplete features or insufficient data returns
`NOT_ESTIMABLE`. The free-data runtime may use a governed research/challenger
artifact for Shadow, while the Formal computation resolver remains blocked
before inference without qualified PIT and Formal Model Governance.

**Step 5: Add `model-train`, `model-report` and deterministic replay under the
existing CLI and commit.**

```bash
python -m pytest -q tests/forecasting/test_regularized_linear.py tests/application/research_validation/test_research_model.py tests/application/research_validation/test_postgres_research_model.py tests/application/research_validation/test_formal_forecast_computation.py tests/application/research_validation/test_model_partition_isolation.py tests/cli/test_continuous_research_cli.py
git diff --check
git add src/market_regime_alpha/application/research_validation src/market_regime_alpha/forecasting/regularized_linear.py src/market_regime_alpha/application/continuous_research/free_data_runtime.py src/market_regime_alpha/persistence/postgres/migrations/062_research_model_artifact.sql src/market_regime_alpha/persistence/repository_factory.py src/market_regime_alpha/persistence/postgres/schema.py src/market_regime_alpha/cli/continuous_research.py tests/forecasting/test_regularized_linear.py tests/application/research_validation tests/cli/test_continuous_research_cli.py
git diff --cached --check
git commit -m "feat: train deterministic exploratory forecast models"
```

## Task 6: Add fail-closed Formal OOS/calibration execution orchestration

**Files:**

- Create: `src/market_regime_alpha/application/research_validation/formal_execution.py`
- Create: `src/market_regime_alpha/application/research_validation/postgres_formal_execution.py`
- Create: `src/market_regime_alpha/persistence/postgres/migrations/063_formal_execution_assessment.sql`
- Modify: `src/market_regime_alpha/persistence/repository_factory.py`
- Modify: `src/market_regime_alpha/persistence/postgres/schema.py`
- Modify: `src/market_regime_alpha/cli/continuous_research.py`
- Test: `tests/application/research_validation/test_formal_execution.py`
- Test: `tests/application/research_validation/test_postgres_formal_execution.py`
- Test: `tests/application/research_validation/test_family_level_oos.py`
- Test: `tests/application/research_validation/test_calibration_leakage.py`

**Step 1: Write predecessor and one-time-unlock tests.**

Cover every missing/rejected Provider Fact Kind, incomplete Formal PIT,
unqualified historical dataset/model, mismatched family, purge/embargo error,
raw OOS reuse and calibration access before OOS consumption. Current free-data
facts must persist `BLOCKED` with `formal_oos_alpha_established=false` and
`calibrated=false`.

**Step 2: Implement one ordered orchestration facade.**

The facade calls existing Protocol, PIT, qualification, raw unlock, family
evaluation and calibration owners only after reloading and verifying every
predecessor. It records an immutable assessment for success, negative,
inconclusive or blocked outcomes. It must not create a shortcut writer for any
existing Formal owner.

**Step 3: Add operator command and commit.**

```bash
python -m pytest -q tests/application/research_validation/test_formal_execution.py tests/application/research_validation/test_postgres_formal_execution.py tests/application/research_validation/test_family_level_oos.py tests/application/research_validation/test_calibration_leakage.py
git diff --check
git add src/market_regime_alpha/application/research_validation/formal_execution.py src/market_regime_alpha/application/research_validation/postgres_formal_execution.py src/market_regime_alpha/persistence/postgres/migrations/063_formal_execution_assessment.sql src/market_regime_alpha/persistence/repository_factory.py src/market_regime_alpha/persistence/postgres/schema.py src/market_regime_alpha/cli/continuous_research.py tests/application/research_validation
git diff --cached --check
git commit -m "feat: orchestrate formal research gates fail closed"
```

## Task 7: Representative run, documentation convergence and exact-SHA verification

**Files:**

- Modify: `docs/architecture/System-Architecture.md`
- Modify: `docs/architecture/Authority-Map.md`
- Modify: `docs/architecture/Data-and-Evidence-Architecture.md`
- Modify: `docs/architecture/Research-Strategy-Lifecycle.md`
- Modify: `docs/status/Current-State.md`
- Modify: `docs/status/Capability-Matrix.md`
- Modify: `docs/status/Gap-Register.md`
- Modify: `docs/status/Roadmap.md`
- Modify: `docs/operations/Runtime-Runbook.md`
- Modify: `docs/research/Negative-and-Inconclusive-Results.md`
- Remove after convergence: `docs/architecture/decisions/Phase-D-Implementation-Plan.md`
- Test: all affected and full test suites

**Step 1: Start an isolated PostgreSQL 16 database and apply all migrations.**

Use an explicit disposable container name, port and test schema. Verify migration
head/checksum, expected tables, triggers and clean upgrade from migration 057.

**Step 2: Execute a representative historical run.**

Use an immutable local free-data archive and a bounded but multi-session policy
that exercises normal, ST/suspended/unknown, T+1, price-limit, lot-size, costs
and capacity paths. Record period, universe, sessions, candidates, signals,
forecasts, shadow trades, NAV, return, drawdown, costs and all rejected/
`NOT_ESTIMABLE` findings. This is engineering evidence only.

**Step 3: Exercise interruption/resume and deterministic replay.**

Interrupt after a committed stage, resume from PostgreSQL, replay the completed
run and compare canonical receipt/report hashes. Run a corruption test and
verify fail-closed behavior.

**Step 4: Converge current documentation.**

Document only code/schema/test/runtime facts. Preserve Formal PIT/OOS/
calibration false states and the free Provider qualification gaps. Remove this
temporary plan after the canonical documents contain the current truth.

**Step 5: Run the required validation matrix.**

```bash
uv sync --frozen --extra dev --extra postgres
python scripts/check_docs_links.py
python -m pytest -q tests/scripts/test_check_docs_links.py
python -m pytest -q tests/platform
python -m pytest -q
python -m ruff check .
python -m mypy
python -m build
git diff --check
```

Also run the focused PostgreSQL migration, idempotency, concurrency, replay,
recovery and compatibility tests introduced above. Every command is reported
as `PASS`, `FAIL`, `NOT_RUN` or `BLOCKED`.

**Step 6: Commit documentation and verification evidence.**

```bash
git add docs
git diff --cached --check
git commit -m "docs: qualify phase d research execution"
```

**Step 7: Verify the exact final commit without changing it.**

Record branch, baseline SHA, final SHA, commits, migration head/checksum, clean
tree status and rerun all non-mutating verification against `HEAD`. If GitHub
Actions have not run, report exactly `CI_NOT_RUN`. Do not claim a PR unless one
was requested and actually created.
