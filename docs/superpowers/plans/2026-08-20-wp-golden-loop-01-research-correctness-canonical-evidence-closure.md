# WP-GOLDEN-LOOP-01 Research Correctness and Canonical Evidence Closure Implementation Plan

> **Status:** HISTORICAL
>
> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a tie-correct V2 Alpha campaign whose Historical Evidence is aggregated from canonical session evaluation, Strategy, Portfolio, Outcome, cost, and attribution owners.

**Architecture:** A shared pure ranking module owns midrank and boundary-weight semantics. The existing Historical bounded runner adds one `RESEARCH_EVALUATION` session component after its canonical Multi-Strategy Cycle, Cross-Strategy Portfolio, Historical Outcome, and Research Panel exist; the Evidence Producer only aggregates those persisted owners. Migration 089 admits the new component and methodology-assessment evidence kinds without mutating V1 evidence.

**Tech Stack:** Python 3.12, frozen dataclasses, `Decimal`, PostgreSQL 16/psycopg 3, SQL forward migrations, pytest, Ruff, mypy, existing content-addressed Authority owners.

## Global Constraints

- Keep `CONTINUOUS_RESEARCH` as the sole all-day Runtime and Historical Research as one bounded runner.
- Keep PostgreSQL as the only Runtime and Evidence Authority; Artifact Root stores immutable bytes only.
- Keep Target, Decision Time, Horizon, Factors, Candidate/Signal thresholds, Forecast floors, cost assumptions, capacity assumptions, Strategy contracts, and Cross-Strategy Portfolio policy unchanged.
- Historical execution remains Shadow/Simulation with `NOT_REAL_FILL`; never create physical Position Authority.
- Preserve all V1 owners; methodology correction is append-only.
- Retain `EXPLORATORY`, `PIT_INCOMPLETE`, `FORMAL_OOS_FALSE`, `CALIBRATED_FALSE`, and `PRODUCTION_AUTHORIZED_FALSE`.
- Do not modify or stage `.idea/modules.xml`.

## File map

- Create `src/market_regime_alpha/research/cross_sectional_ranking.py`: shared pure midrank, diagnostics, composite, and fractional boundary APIs.
- Modify `src/market_regime_alpha/candidates/composite_baseline.py`: consume shared directional percentiles and remove its private rank implementation.
- Modify `src/market_regime_alpha/candidates/baselines.py`: consume shared percentiles and make score ties explicit in semantic identity.
- Modify `src/market_regime_alpha/research/pit_replication_success_v2_features.py`: import only the public shared kernel.
- Modify `src/market_regime_alpha/application/research_validation/ablation.py`: V2 scoring consumes the shared kernel and persisted boundary weights; delete private tie splitting.
- Create `src/market_regime_alpha/application/historical_corpus/golden_loop.py`: frozen V2 contract, session evaluation payload, canonical-source verification, and sufficient-statistic aggregation types.
- Modify `src/market_regime_alpha/application/historical_corpus/frozen_experiment.py`: exact Golden Loop V2 Experiment creator/verifier while preserving the V1 verifier for stored replay.
- Modify `src/market_regime_alpha/application/historical_corpus/materialization_contracts.py`: admit `RESEARCH_EVALUATION`.
- Modify `src/market_regime_alpha/application/historical_research/multi_strategy.py`: extend PERFORMANCE after the delegate and persist canonical evaluation/feedback owners.
- Modify `src/market_regime_alpha/application/historical_corpus/evidence.py`: admit `METHODOLOGY_ASSESSMENT`.
- Modify `src/market_regime_alpha/application/historical_corpus/evidence_producer.py`: aggregate `RESEARCH_EVALUATION`; do not rank or build a portfolio.
- Create `src/market_regime_alpha/persistence/postgres/migrations/089_golden_loop_v2_evidence.sql`: forward-only enum constraints and comments.
- Modify CLI composition only where needed to inject the existing Strategy repository and frozen V2 contract into the adapter.
- Update canonical status/research documents after runtime proof; delete `docs/superpowers/specs` and `docs/superpowers/plans` from final tree after their checkpoint commits.

---

### Task 1: Shared tie-aware ranking and boundary policy

**Files:**
- Create: `src/market_regime_alpha/research/cross_sectional_ranking.py`
- Create: `tests/research/test_cross_sectional_ranking.py`

**Interfaces:**
- Produces: `rank_percentiles(values: Mapping[K, Decimal], *, higher_is_better: bool) -> CrossSectionalRankResult[K]`
- Produces: `composite_percentile_scores(...) -> CompositeRankResult[K]`
- Produces: `fractional_boundary_weights(scores: Mapping[K, Decimal], *, slots: int, higher_is_better: bool) -> BoundarySelection[K]`

- [ ] **Step 1: Write failing unit and metamorphic tests**

```python
def test_equal_values_share_midrank_and_constant_is_neutral() -> None:
    tied = rank_percentiles({"a": Decimal("2"), "b": Decimal("2"), "c": Decimal("1")}, higher_is_better=True)
    assert tied.percentiles["a"] == tied.percentiles["b"] == Decimal("0.75")
    constant = rank_percentiles({"a": Decimal("7"), "b": Decimal("7")}, higher_is_better=True)
    assert set(constant.percentiles.values()) == {Decimal("0.5")}
    assert constant.status is RankInformationStatus.CONSTANT

def test_permutation_and_symbol_renaming_are_equivariant() -> None:
    original = rank_percentiles({"000001.SZ": Decimal("3"), "600000.SH": Decimal("1")}, higher_is_better=True)
    renamed = rank_percentiles({"x": Decimal("3"), "y": Decimal("1")}, higher_is_better=True)
    assert original.percentiles["000001.SZ"] == renamed.percentiles["x"]
    assert original.percentiles["600000.SH"] == renamed.percentiles["y"]

def test_fractional_boundary_never_uses_entity_identity() -> None:
    selected = fractional_boundary_weights({"a": Decimal("1"), "b": Decimal("0"), "c": Decimal("0")}, slots=2, higher_is_better=True)
    assert selected.weights == {"a": Decimal("1"), "b": Decimal("0.5"), "c": Decimal("0.5")}
    assert selected.boundary_group_size == 2
```

- [ ] **Step 2: Run the focused test and confirm RED**

Run: `python -m pytest -q tests/research/test_cross_sectional_ranking.py`
Expected: FAIL because `cross_sectional_ranking` does not exist.

- [ ] **Step 3: Implement immutable result types and pure kernels**

```python
class RankInformationStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    CONSTANT = "CONSTANT"
    NOT_ESTIMABLE = "NOT_ESTIMABLE"

@dataclass(frozen=True, slots=True)
class CrossSectionalRankResult(Generic[K]):
    percentiles: Mapping[K, Decimal]
    status: RankInformationStatus
    observed_count: int

def rank_percentiles(values: Mapping[K, Decimal], *, higher_is_better: bool) -> CrossSectionalRankResult[K]:
    if any(isinstance(value, bool) or not value.is_finite() for value in values.values()):
        raise ValueError("cross-sectional values must be finite Decimals")
    ordered = sorted(values.items(), key=lambda item: item[1])
    if not ordered:
        return CrossSectionalRankResult({}, RankInformationStatus.NOT_ESTIMABLE, 0)
    if len(ordered) == 1 or ordered[0][1] == ordered[-1][1]:
        return CrossSectionalRankResult({key: Decimal("0.5") for key, _ in ordered}, RankInformationStatus.CONSTANT, len(ordered))
    denominator = Decimal(len(ordered) - 1)
    percentiles: dict[K, Decimal] = {}
    position = 0
    while position < len(ordered):
        end = position + 1
        while end < len(ordered) and ordered[end][1] == ordered[position][1]:
            end += 1
        midrank = (Decimal(position) + Decimal(end - 1)) / Decimal(2)
        ascending = midrank / denominator
        percentile = ascending if higher_is_better else Decimal(1) - ascending
        for index in range(position, end):
            percentiles[ordered[index][0]] = percentile
        position = end
    return CrossSectionalRankResult(percentiles, RankInformationStatus.AVAILABLE, len(ordered))

def fractional_boundary_weights(scores: Mapping[K, Decimal], *, slots: int, higher_is_better: bool) -> BoundarySelection[K]:
    if slots <= 0:
        raise ValueError("boundary slots must be positive")
    ordered_scores = sorted(scores.values(), reverse=higher_is_better)
    boundary_score = ordered_scores[min(slots, len(scores)) - 1]
    strict = {key for key, value in scores.items() if (value > boundary_score if higher_is_better else value < boundary_score)}
    boundary = {key for key, value in scores.items() if value == boundary_score}
    remaining = Decimal(min(slots, len(scores)) - len(strict))
    boundary_weight = remaining / Decimal(len(boundary))
    weights = {key: (Decimal(1) if key in strict else boundary_weight if key in boundary else Decimal(0)) for key in scores}
    return BoundarySelection(weights, boundary_score, len(strict), len(boundary), boundary_weight)
```

Canonicalize result mappings only for serialization; never use keys in arithmetic. `BoundarySelection` validates that all weights are in `[0, 1]` and sum to `min(slots, len(scores))`.

- [ ] **Step 4: Run focused tests and property loops**

Run: `python -m pytest -q tests/research/test_cross_sectional_ranking.py`
Expected: PASS, including 100 deterministic permutations and renamings generated by the test.

- [ ] **Step 5: Commit the pure correctness kernel**

```bash
git add src/market_regime_alpha/research/cross_sectional_ranking.py tests/research/test_cross_sectional_ranking.py
git commit -m "feat(research): add tie-aware ranking contract"
```

### Task 2: Converge Candidate, Baseline, PIT, and Ablation consumers

**Files:**
- Modify: `src/market_regime_alpha/candidates/composite_baseline.py`
- Modify: `src/market_regime_alpha/candidates/baselines.py`
- Modify: `src/market_regime_alpha/research/pit_replication_success_v2_features.py`
- Modify: `src/market_regime_alpha/application/research_validation/ablation.py`
- Modify: `tests/candidates/test_composite_baseline.py`
- Modify: `tests/application/research_validation/test_alpha_ablation.py`
- Create: `tests/architecture/test_shared_cross_sectional_ranking.py`

**Interfaces:**
- Consumes: Task 1 public ranking APIs.
- Produces: `WITHIN_SESSION_TIE_AWARE_FACTOR_PERCENTILE_MEAN_V2` ablation scoring with `FRACTIONAL_BOUNDARY_WEIGHT_V1`.

- [ ] **Step 1: Add failing consumer and architecture tests**

```python
def test_constant_factor_cannot_change_ablation_selection_or_economics() -> None:
    base = evaluate_session(factors={"price": varying_values})
    augmented = evaluate_session(factors={"price": varying_values, "theme": constant_values})
    assert augmented.boundary_weights == base.boundary_weights
    assert augmented.gross_return == base.gross_return
    assert augmented.incremental_status == "NO_RANKING_INFORMATION"
```

The architecture test reads the four active modules and asserts they import `market_regime_alpha.research.cross_sectional_ranking`; it rejects definitions named `_directional_rank_percentiles` or `_within_session_percentile_scores` in those modules.

- [ ] **Step 2: Run focused tests and confirm RED**

Run: `python -m pytest -q tests/candidates/test_composite_baseline.py tests/application/research_validation/test_alpha_ablation.py tests/architecture/test_shared_cross_sectional_ranking.py`
Expected: FAIL on V1 constant-factor behavior and duplicate helpers.

- [ ] **Step 3: Replace private ranking implementations**

Use shared percentiles for Candidate and PIT. Preserve Candidate `STRICT_COMPLETE_CASE_REJECT`. In Ablation, build one factor result per session, use neutral `0.5` for missing/constant/unobserved factors under a fixed declared denominator, and persist factor coverage/status diagnostics. Replace lexical Top-K slicing with `fractional_boundary_weights` and compute weighted gross, cost, net, MFE, MAE, hit rate, turnover, and drawdown.

- [ ] **Step 4: Run all affected non-PostgreSQL tests**

Run: `python -m pytest -q tests/research/test_cross_sectional_ranking.py tests/candidates tests/application/research_validation/test_alpha_ablation.py tests/architecture/test_shared_cross_sectional_ranking.py`
Expected: PASS.

- [ ] **Step 5: Commit consumer convergence**

```bash
git add src/market_regime_alpha/candidates src/market_regime_alpha/research/pit_replication_success_v2_features.py src/market_regime_alpha/application/research_validation/ablation.py tests/candidates tests/application/research_validation/test_alpha_ablation.py tests/architecture/test_shared_cross_sectional_ranking.py
git commit -m "fix(research): remove identity-based factor ranking"
```

### Task 3: Freeze the Golden Loop V2 Experiment and session evaluation contract

**Files:**
- Create: `src/market_regime_alpha/application/historical_corpus/golden_loop.py`
- Modify: `src/market_regime_alpha/application/historical_corpus/frozen_experiment.py`
- Create: `tests/application/historical_corpus/test_golden_loop.py`
- Modify: `tests/application/historical_corpus/test_frozen_experiment.py`

**Interfaces:**
- Produces: `GoldenLoopScoringContract.create_v2() -> GoldenLoopScoringContract`
- Produces: `create_golden_loop_v2_historical_experiment(target_protocol, *, locked_at) -> ResearchExperimentDefinition`
- Produces: `evaluate_golden_loop_session(...) -> GoldenLoopSessionEvaluation`
- Produces: `GoldenLoopSessionEvaluation.to_component_payload() -> Mapping[str, Any]`

- [ ] **Step 1: Write failing identity and source-lineage tests**

```python
def test_v2_experiment_changes_only_correctness_identities(phase_e3_owners) -> None:
    v1 = create_phase_e3_historical_experiment(phase_e3_owners.target, locked_at=LOCKED)
    v2 = create_golden_loop_v2_historical_experiment(phase_e3_owners.target, locked_at=LOCKED)
    assert v2.target_references == v1.target_references
    assert v2.feature_reference == v1.feature_reference
    assert v2.cost_policy_reference == v1.cost_policy_reference
    assert v2.definition_hash != v1.definition_hash

def test_session_evaluation_requires_exact_canonical_sources() -> None:
    with pytest.raises(ValueError, match="CROSS_STRATEGY_PORTFOLIO"):
        evaluate_golden_loop_session(panel=panel, cycle=cycle, portfolio=None, outcome=outcome, contract=contract)
```

- [ ] **Step 2: Run and confirm RED**

Run: `python -m pytest -q tests/application/historical_corpus/test_golden_loop.py tests/application/historical_corpus/test_frozen_experiment.py`
Expected: FAIL because the V2 contract and experiment do not exist.

- [ ] **Step 3: Implement the frozen contract and evaluation payload**

The contract payload includes exact strings:

```python
scoring_contract = "WITHIN_SESSION_TIE_AWARE_FACTOR_PERCENTILE_MEAN_V2"
selection_policy = "FRACTIONAL_BOUNDARY_WEIGHT_V1"
missing_policy = "FIXED_DENOMINATOR_NEUTRAL_0_5_V1"
tie_policy = "ARITHMETIC_MIDRANK_V1"
constant_policy = "NEUTRAL_0_5_NO_RANKING_INFORMATION_V1"
```

Bind the contract hash into the V2 Experiment hyperparameter domain and V2 hypothesis-family IDs. Session evaluation stores per-variant scores, top/bottom fractional weights, returns/costs, factor coverage/status, boundary diagnostics, and exact canonical sources. It stores canonical Portfolio lines and gate coverage but does not create proposals or allocation.

- [ ] **Step 4: Run focused tests**

Run: `python -m pytest -q tests/application/historical_corpus/test_golden_loop.py tests/application/historical_corpus/test_frozen_experiment.py`
Expected: PASS.

- [ ] **Step 5: Commit the V2 contract**

```bash
git add src/market_regime_alpha/application/historical_corpus/golden_loop.py src/market_regime_alpha/application/historical_corpus/frozen_experiment.py tests/application/historical_corpus/test_golden_loop.py tests/application/historical_corpus/test_frozen_experiment.py
git commit -m "feat(research): freeze golden loop v2 experiment"
```

### Task 4: Admit immutable evaluation and methodology-assessment owners

**Files:**
- Create: `src/market_regime_alpha/persistence/postgres/migrations/089_golden_loop_v2_evidence.sql`
- Modify: `src/market_regime_alpha/application/historical_corpus/materialization_contracts.py`
- Modify: `src/market_regime_alpha/application/historical_corpus/evidence.py`
- Modify: `tests/persistence/postgres/test_migrator.py`
- Modify: `tests/persistence/postgres/test_historical_materialization_repository.py`
- Modify: `tests/persistence/postgres/test_historical_corpus_repository.py`

**Interfaces:**
- Produces: `HistoricalComponentKind.RESEARCH_EVALUATION` at ordinal 14.
- Produces: `HistoricalEvidenceKind.METHODOLOGY_ASSESSMENT`.

- [ ] **Step 1: Add failing migration and immutability tests**

Verify 084 database state migrates through 089; V1 rows remain byte-identical; new component/evidence kinds insert; update/delete triggers still reject mutation; conflicting same-ID payloads fail.

- [ ] **Step 2: Run PostgreSQL migration tests and confirm RED**

Run: `MARKET_REGIME_ALPHA_TEST_DATABASE_URL="$MARKET_REGIME_ALPHA_TEST_DATABASE_URL" python -m pytest -q tests/persistence/postgres/test_migrator.py tests/persistence/postgres/test_historical_materialization_repository.py`
Expected: FAIL because migration 089 and enums are absent.

- [ ] **Step 3: Implement the forward migration**

Drop and recreate only the two CHECK constraints so they additionally admit `RESEARCH_EVALUATION` and `METHODOLOGY_ASSESSMENT`. Add comments that V1 owners are immutable and the assessment is append-only lineage. Do not rewrite table data.

- [ ] **Step 4: Run migration and repository tests**

Run the command from Step 2 plus `python -m pytest -q tests/persistence/postgres/test_historical_corpus_repository.py` with the test database URL.
Expected: PASS.

- [ ] **Step 5: Commit migration 089**

```bash
git add src/market_regime_alpha/persistence/postgres/migrations/089_golden_loop_v2_evidence.sql src/market_regime_alpha/application/historical_corpus/materialization_contracts.py src/market_regime_alpha/application/historical_corpus/evidence.py tests/persistence/postgres
git commit -m "feat(postgres): admit golden loop v2 evidence owners"
```

### Task 5: Wire session evaluation into the existing Historical bounded runner

**Files:**
- Modify: `src/market_regime_alpha/application/historical_research/multi_strategy.py`
- Modify: `src/market_regime_alpha/cli/continuous_research.py`
- Modify: `tests/persistence/postgres/test_historical_decision_materializer.py`
- Modify: `tests/cli/test_continuous_research_cli.py`

**Interfaces:**
- Consumes: Task 3 evaluator and Task 4 component kind.
- Produces: PERFORMANCE outputs containing both `HISTORICAL_RESEARCH_PANEL` and `HISTORICAL_RESEARCH_EVALUATION`.

- [ ] **Step 1: Write failing canonical-wiring tests**

Assert one completed session persists exact `MULTI_STRATEGY_CYCLE`, `CROSS_STRATEGY_PORTFOLIO`, `HISTORICAL_OUTCOME`, `HISTORICAL_RESEARCH_PANEL`, and `HISTORICAL_RESEARCH_EVALUATION` references. Assert evaluation source bindings contain all four owner hashes and the V2 Experiment. Assert zero proposals produces Portfolio `NO_ACTION`, attribution `NOT_ESTIMABLE`, and no path/physical Fill/Position owner.

- [ ] **Step 2: Run focused PostgreSQL tests and confirm RED**

Run: `MARKET_REGIME_ALPHA_TEST_DATABASE_URL="$MARKET_REGIME_ALPHA_TEST_DATABASE_URL" python -m pytest -q tests/persistence/postgres/test_historical_decision_materializer.py tests/cli/test_continuous_research_cli.py`
Expected: FAIL because PERFORMANCE is not decorated.

- [ ] **Step 3: Extend only the adapter PERFORMANCE branch**

```python
if stage is ResearchSessionStage.PERFORMANCE:
    return self._performance_stage(request, delegated)
```

Load exact sources through existing repositories, evaluate once, persist a `RESEARCH_EVALUATION` component at ordinal 14, and extend the stage receipt. Create existing `StrategyFeedbackArtifact` with `NOT_ESTIMABLE` when no canonical proposal/outcome path exists. Keep accepted simulated economics bound to Historical Outcome/cost references and retain `NOT_REAL_FILL`.

- [ ] **Step 4: Run Historical integration and CLI tests**

Run the Step 2 command and `python -m pytest -q tests/application/historical_research tests/application/historical_corpus`.
Expected: PASS.

- [ ] **Step 5: Commit canonical session wiring**

```bash
git add src/market_regime_alpha/application/historical_research/multi_strategy.py src/market_regime_alpha/cli/continuous_research.py tests/persistence/postgres/test_historical_decision_materializer.py tests/cli/test_continuous_research_cli.py
git commit -m "feat(research): wire canonical golden loop evaluation"
```

### Task 6: Make Historical Evidence an owner aggregator and append invalidation lineage

**Files:**
- Modify: `src/market_regime_alpha/application/historical_corpus/evidence_producer.py`
- Modify: `src/market_regime_alpha/application/historical_corpus/postgres_evidence.py`
- Modify: `tests/application/historical_corpus/test_evidence_producer.py`
- Modify: `tests/persistence/postgres/test_historical_corpus_repository.py`

**Interfaces:**
- Consumes: ordered `RESEARCH_EVALUATION` components.
- Produces: V2 corpus, ablation, strategy economics, portfolio performance, exploratory model, and methodology assessment owners.

- [ ] **Step 1: Add failing anti-reimplementation and lineage tests**

Assert V2 production fails if any evaluation, cycle, portfolio, outcome, feedback, contract, or Experiment source is absent. Monkeypatch the shared ranking kernel to raise and prove Evidence aggregation never calls it. Assert the methodology assessment preserves exact Phase E2/Phase E3 V1 evidence references and statuses.

- [ ] **Step 2: Run focused tests and confirm RED**

Run: `python -m pytest -q tests/application/historical_corpus/test_evidence_producer.py`
Expected: FAIL because the producer still reads panel rows and ranks them.

- [ ] **Step 3: Replace scoring with sufficient-statistic aggregation**

Delete `_panel_observations`, `_stream_observation_sessions`, and producer-local scoring. Aggregate stored scores, fractional weights, coverage, returns, costs, and canonical Portfolio weights in session order. Emit `NO_ACTION`/`NOT_ESTIMABLE` when the canonical Portfolio has no accepted exposure. Persist methodology assessments in each isolated Authority database with old evidence sources and the V2 correction identity; do not update old rows.

- [ ] **Step 4: Run Evidence and replay-focused tests**

Run: `python -m pytest -q tests/application/historical_corpus/test_evidence_producer.py tests/application/historical_corpus/test_historical_window.py` and the affected PostgreSQL repository test with the test database URL.
Expected: PASS.

- [ ] **Step 5: Commit canonical Evidence aggregation**

```bash
git add src/market_regime_alpha/application/historical_corpus/evidence_producer.py src/market_regime_alpha/application/historical_corpus/postgres_evidence.py tests/application/historical_corpus/test_evidence_producer.py tests/persistence/postgres/test_historical_corpus_repository.py
git commit -m "fix(research): aggregate evidence from canonical owners"
```

### Task 7: Prove migration, V2 campaign, resume, replay, and empirical conclusions

**Files:**
- Runtime artifacts only under `.local/golden-loop-v2/` and never staged.
- Modify after proof: `docs/references/Phase-E2-Historical-Evidence-Expansion-Report.md`
- Modify after proof: `docs/references/Phase-E3-Longitudinal-Historical-Evidence-Report.md`
- Modify after proof: `docs/research/Negative-and-Inconclusive-Results.md`
- Modify after proof: `docs/status/Current-State.md`
- Modify after proof: `docs/status/Capability-Matrix.md`
- Modify after proof: `docs/status/Gap-Register.md`
- Modify after proof: `docs/status/Roadmap.md`

**Interfaces:**
- Consumes: Phase E3 Authority dump and Artifact Root.
- Produces: exact run/evidence/replay IDs and hashes; no tracked runtime bytes.

- [ ] **Step 1: Clone and upgrade the restored Authority database**

Create a uniquely named database from the preserved dump, set an isolated schema/database URL, run `PostgresMigrator`, and record before/after migration rows. Expected proof: source head 084; target head 089; all V1 row counts and ordered hashes unchanged.

- [ ] **Step 2: Bootstrap the exact V2 Experiment without changing frozen inputs**

Reuse the Phase E3 normalized owner, timeline, security facts, Target, feature, economics, calendar, Universe, and portfolio inputs. Generate a new Experiment, command, run, and idempotency identity using current code SHA and the V2 scoring/selection hashes.

- [ ] **Step 3: Execute interruption/resume and uninterrupted controls**

Run a bounded partial campaign, resume it to terminal completion, then restore a second isolated clone and run uninterrupted. Record terminal statuses, session/component counts, peak memory, elapsed time, and failure diagnostics.

- [ ] **Step 4: Produce Evidence and replay**

Run Evidence production only after terminal completion. Run the repository replay command and compare ordered Run, Session, stage receipt, component, source binding, Strategy Cycle, Portfolio, feedback, Evidence, and metric ID/hash sets between resumed and uninterrupted runs.

- [ ] **Step 5: Query research answers without promotion**

Record constant-factor incremental status, boundary diagnostics, symbol/exchange-prefix concentration, RankIC, gross/cost/net, turnover, drawdown, Candidate/Signal/Forecast coverage, Portfolio status, and exact canonical owner equality. Mark unavailable metrics `NOT_ESTIMABLE`; retain `EXPLORATORY/PIT_INCOMPLETE`.

- [ ] **Step 6: Update current documentation with exact evidence IDs**

Invalidate the old Phase E2/Phase E3 ranking-dependent interpretation, link the append-only methodology assessment owners, report V2 negative/positive values exactly, and select the next Work Package solely from the V2 result.

- [ ] **Step 7: Commit runtime-backed documentation**

```bash
git add docs/references docs/research/Negative-and-Inconclusive-Results.md docs/status
git commit -m "docs(research): record golden loop v2 evidence"
```

### Task 8: Full quality gates, architecture review, cleanup, and publication

**Files:**
- Delete from current tree after checkpoint history exists: `docs/superpowers/specs/2026-08-20-wp-golden-loop-01-research-correctness-canonical-evidence-closure-design.md`
- Delete from current tree after execution: `docs/superpowers/plans/2026-08-20-wp-golden-loop-01-research-correctness-canonical-evidence-closure.md`
- Modify only findings required by review.

**Interfaces:**
- Produces: clean branch, exact final SHA, pushed remote branch, Draft PR, and evidence-bounded delivery report.

- [ ] **Step 1: Run repository quality gates**

Run exactly:

```bash
uv sync --frozen --extra dev --extra postgres
python scripts/check_docs_links.py
python -m pytest -q tests/scripts/test_check_docs_links.py
python -m pytest -q tests/platform
MARKET_REGIME_ALPHA_TEST_DATABASE_URL="$MARKET_REGIME_ALPHA_TEST_DATABASE_URL" python -m pytest -q
python -m ruff check .
python -m mypy
python -m build
git diff --check
```

Record every command as `PASS`, `FAIL`, `NOT_RUN`, or `BLOCKED` with the exact exit result.

- [ ] **Step 2: Review Standards and Spec compliance**

Check the complete branch diff against AGENTS.md, the approved design, Authority reload, canonical runtime call chain, V1 immutability, simulation/physical Fill separation, and the explicit no-tuning list. Fix only evidenced defects and rerun affected tests.

- [ ] **Step 3: Remove temporary superpowers documents from the active tree**

Use `apply_patch` deletions so the repository's canonical docs inventory passes. Their exact contents remain in checkpoint commits `cfcbb52` and the plan commit.

- [ ] **Step 4: Commit final cleanup**

```bash
git add -u docs/superpowers
git commit -m "chore(docs): archive implementation checkpoints in history"
```

- [ ] **Step 5: Verify scope and publish**

Inspect `git status --short --branch`, `git diff origin/main...HEAD --check`, and the commit list. Push `agent/alpha-proof-campaign-01`, verify remote SHA equality, and create a Draft PR containing exact validation and Evidence ceilings. Do not merge.
