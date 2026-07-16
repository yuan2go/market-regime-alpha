# WP-3 Candidate Directional Accuracy Diagnostics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add versioned, target-aware positive-return diagnostics to fixed WP-3 B0/B1 Candidate evaluations without creating Entry, Exit or execution semantics.

**Architecture:** A new Candidate-owned module evaluates an already-built ranking against an explicit Next-Session Close Return sign rule. The fixed R5 runner attaches either an applicable panel diagnostic or an explicit non-applicability record, and the existing WP-3 evaluation artifact and manifest serialize the additive evidence.

**Tech Stack:** Python 3.11+, frozen slotted dataclasses, enums, existing Candidate dataset/ranking contracts, pytest, Ruff, mypy, canonical JSON WP-3 artifacts.

## Global Constraints

- Preserve B0/B1 features, weights, missing policy, scores and ordering exactly.
- Apply `R5_NEXT_SESSION_POSITIVE_RETURN_TOP5_V1` only to `R5_NEXT_SESSION_RETURN_TARGET_ID`.
- Classify `value > 0` as positive, `value < 0` as negative and `value == 0` as neutral.
- Keep Top K fixed at `5`; do not backfill unavailable Top-5 Targets from later ranks.
- Preserve unavailable Targets and zero denominators explicitly; never convert them to zero outcomes.
- Tencent remains `EXPLORATORY`; Xuntou remains bounded by actual `REHEARSAL` evidence.
- Add no Entry Proposal, Exit Proposal, Portfolio Decision or trading execution.
- Do not implement WP-4 Entry targets or later Position/Exit contracts in this plan.

---

## File Structure

- Create `src/market_regime_alpha/candidates/directional_accuracy.py`: diagnostic spec, counts, slice/panel results and evaluators.
- Create `tests/candidates/test_directional_accuracy.py`: exact classification, missingness, aggregation and alignment contracts.
- Modify `src/market_regime_alpha/candidates/__init__.py`: export intended Candidate diagnostic APIs.
- Modify `src/market_regime_alpha/research/r5_baseline_runner.py`: attach applicable/non-applicable diagnostics and serialize them.
- Modify `tests/research/test_r5_baseline_runner.py`: runner applicability and JSON contract tests.
- Modify `src/market_regime_alpha/research/wp3_orchestrator.py`: record the metric protocol identity in all successful WP-3 manifests.
- Modify `tests/research/test_wp3_orchestrator.py`: assert manifest identity and additive evaluation evidence.
- Modify `tests/research/test_wp3_public_api.py`: assert intended public APIs only.
- Modify `docs/research/R5-Current-Status.md`: record implemented scope, verification and explicit Entry/Exit limitations.
- Modify `docs/research/R5-WP3-Provider-Routing-Status.md`: record the new additive diagnostic protocol.

---

### Task 1: Candidate Directional Diagnostic Core

**Files:**
- Create: `tests/candidates/test_directional_accuracy.py`
- Create: `src/market_regime_alpha/candidates/directional_accuracy.py`
- Modify: `src/market_regime_alpha/candidates/__init__.py`

**Interfaces:**
- Consumes: `CandidateResearchDataset`, `CandidateResearchPanel`, `CandidateRankingLike`, `evaluate_candidate_ranking_slice`, `R5_NEXT_SESSION_RETURN_TARGET_ID`.
- Produces: `R5_NEXT_SESSION_POSITIVE_RETURN_TOP5_SPEC`, `CandidateDirectionalAccuracySpec`, `DirectionalOutcomeCounts`, `CandidateDirectionalSliceEvaluation`, `CandidateDirectionalPanelEvaluation`, `evaluate_candidate_directional_accuracy_slice(...)`, `evaluate_candidate_directional_accuracy_panel(...)`.

- [ ] **Step 1: Write failing classification and no-backfill tests**

Create fixtures with six ranked symbols and Target states `AVAILABLE(+0.1)`, `AVAILABLE(-0.1)`, `AVAILABLE(0.0)`, `MISSING`, `AVAILABLE(+0.2)`, `AVAILABLE(-0.2)`. Assert:

```python
result = evaluate_candidate_directional_accuracy_slice(
    dataset,
    ranking,
    spec=R5_NEXT_SESSION_POSITIVE_RETURN_TOP5_SPEC,
)

assert result.candidate_population.observed_count == 5
assert result.candidate_population.positive_count == 2
assert result.candidate_population.negative_count == 2
assert result.candidate_population.neutral_count == 1
assert result.top_k.observed_count == 4
assert result.top_k.positive_count == 2
assert result.top_k.negative_count == 1
assert result.top_k.neutral_count == 1
assert result.top_k_observed_coverage == 0.8
```

The sixth symbol must not replace the unavailable fourth-ranked Target.

- [ ] **Step 2: Run the new test and confirm it fails at import**

Run:

```bash
python3 -m pytest -o addopts='' tests/candidates/test_directional_accuracy.py -q
```

Expected: collection fails because `market_regime_alpha.candidates.directional_accuracy` does not exist.

- [ ] **Step 3: Implement the fixed spec and count contract**

Add these public shapes:

```python
R5_NEXT_SESSION_POSITIVE_RETURN_TOP5_SPEC_ID = (
    "R5_NEXT_SESSION_POSITIVE_RETURN_TOP5_V1"
)

@dataclass(frozen=True, slots=True)
class CandidateDirectionalAccuracySpec:
    spec_id: str
    target_id: TargetId
    top_k: int

@dataclass(frozen=True, slots=True)
class DirectionalOutcomeCounts:
    observed_count: int
    positive_count: int
    negative_count: int
    neutral_count: int

    @property
    def positive_rate(self) -> float | None:
        return (
            self.positive_count / self.observed_count
            if self.observed_count
            else None
        )

    @property
    def negative_rate(self) -> float | None:
        return (
            self.negative_count / self.observed_count
            if self.observed_count
            else None
        )

    @property
    def neutral_rate(self) -> float | None:
        return (
            self.neutral_count / self.observed_count
            if self.observed_count
            else None
        )
```

Validate trimmed non-empty `spec_id`, exact `TargetId`, positive integer `top_k`, non-negative counts and `positive + negative + neutral == observed`. Define the fixed spec with `R5_NEXT_SESSION_RETURN_TARGET_ID` and `top_k=5`.

- [ ] **Step 4: Implement slice evaluation using the existing ranking guard**

Define:

```python
def evaluate_candidate_directional_accuracy_slice(
    dataset: CandidateResearchDataset,
    ranking: CandidateRankingLike,
    *,
    spec: CandidateDirectionalAccuracySpec,
) -> CandidateDirectionalSliceEvaluation:
```

First require `dataset.target_id == spec.target_id`, then call `evaluate_candidate_ranking_slice(dataset, ranking, top_k=spec.top_k)` to reuse exact population/identity validation. Count all `AVAILABLE` Candidate Targets, all `AVAILABLE` ranked Targets, and only `AVAILABLE` Targets among `ranking.predictions[:spec.top_k]`. Expose `None` for all rates or differences whose denominator is zero.

- [ ] **Step 5: Add panel aggregation tests**

Build two chronologically ordered slices with different population sizes. Assert:

```python
assert result.slice_evaluations[0].decision_time < result.slice_evaluations[1].decision_time
assert result.micro_top_k.positive_rate == 3 / 6
assert result.macro_top_k_positive_rate == (
    first.top_k.positive_rate + second.top_k.positive_rate
) / 2
assert result.comparable_slice_count == 2
assert result.improved_slice_count == 1
assert result.improved_slice_fraction == 0.5
```

Also assert an all-unavailable slice contributes counts but no defined macro rate.

- [ ] **Step 6: Implement panel aggregation and strict alignment**

Define:

```python
def evaluate_candidate_directional_accuracy_panel(
    panel: CandidateResearchPanel,
    rankings: tuple[CandidateRankingLike, ...],
    *,
    spec: CandidateDirectionalAccuracySpec,
) -> CandidateDirectionalPanelEvaluation:
```

Require unique ranking dataset IDs, exact coverage of `panel.slice_dataset_ids`, one model identity and `panel.target_id == spec.target_id`. Order rankings by `panel.slices`, evaluate each slice, sum count groups for micro metrics, average only defined slice rates for macro metrics, and count strict positive-rate improvements.

- [ ] **Step 7: Add mismatch and zero-denominator tests**

Assert `ValueError` for a mismatched Target spec, missing panel ranking, duplicate dataset ranking and mixed model identities. Assert zero-observation group rates and lift values are `None`, never `0.0`.

- [ ] **Step 8: Export intended Candidate APIs and run focused verification**

Add the public names to `candidates/__init__.py`, then run:

```bash
python3 -m pytest -o addopts='' tests/candidates/test_directional_accuracy.py tests/candidates/test_baseline_ranking_evaluation_guards.py -q
python3 -m ruff check src/market_regime_alpha/candidates/directional_accuracy.py tests/candidates/test_directional_accuracy.py src/market_regime_alpha/candidates/__init__.py
python3 -m mypy src/market_regime_alpha/candidates/directional_accuracy.py
```

Expected: all focused tests and scoped checks pass.

- [ ] **Step 9: Commit the core**

```bash
git add src/market_regime_alpha/candidates/directional_accuracy.py src/market_regime_alpha/candidates/__init__.py tests/candidates/test_directional_accuracy.py
git commit -m "feat: add Candidate directional diagnostics"
```

---

### Task 2: Fixed B0/B1 Runner Integration

**Files:**
- Modify: `src/market_regime_alpha/research/r5_baseline_runner.py`
- Modify: `tests/research/test_r5_baseline_runner.py`

**Interfaces:**
- Consumes: `R5_NEXT_SESSION_POSITIVE_RETURN_TOP5_SPEC`, `CandidateDirectionalPanelEvaluation`, `evaluate_candidate_directional_accuracy_panel(...)` from Task 1.
- Produces: `DirectionalAccuracyApplicability`, `NamedDirectionalAccuracy`, additive `NamedCandidatePanelEvaluation.directional_accuracy`, and explicit JSON records.

- [ ] **Step 1: Write failing runner applicability tests**

Change the applicable fixture to use `R5_NEXT_SESSION_RETURN_TARGET_ID`. Run the fixed runner and assert every B0/B1 item has:

```python
assert item.directional_accuracy.status is DirectionalAccuracyApplicability.APPLICABLE
assert item.directional_accuracy.spec_id == R5_NEXT_SESSION_POSITIVE_RETURN_TOP5_SPEC.spec_id
assert item.directional_accuracy.evaluation is not None
assert item.directional_accuracy.reason is None
```

Run the same fixture with `R5_NEXT_SESSION_MFE_TARGET_ID` and assert `NOT_APPLICABLE`, no spec/evaluation, and reason `TARGET_SEMANTICS_NOT_POSITIVE_CLOSE_RETURN`.

- [ ] **Step 2: Run the runner tests and confirm the new assertions fail**

Run:

```bash
python3 -m pytest -o addopts='' tests/research/test_r5_baseline_runner.py -q
```

Expected: failures because the applicability fields do not exist.

- [ ] **Step 3: Add explicit applicability contracts**

Implement:

```python
class DirectionalAccuracyApplicability(str, Enum):
    APPLICABLE = "APPLICABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"

@dataclass(frozen=True, slots=True)
class NamedDirectionalAccuracy:
    status: DirectionalAccuracyApplicability
    spec_id: str | None
    evaluation: CandidateDirectionalPanelEvaluation | None
    reason: str | None
```

Validate the two allowed state shapes: applicable requires spec/evaluation and forbids reason; not-applicable forbids spec/evaluation and requires a trimmed reason.

- [ ] **Step 4: Evaluate only the approved return Target**

After constructing each tuple of B0 or B1 rankings, call the directional panel evaluator only when `panel.target_id == R5_NEXT_SESSION_RETURN_TARGET_ID`. For MFE and MAE attach the explicit non-applicable record. Add the wrapper to `NamedCandidatePanelEvaluation`.

- [ ] **Step 5: Serialize exact applicability evidence**

Extend `candidate_evaluation_record()` to return:

```python
"directional_accuracy": {
    "status": item.directional_accuracy.status.value,
    "spec_id": item.directional_accuracy.spec_id,
    "reason": item.directional_accuracy.reason,
    "metrics": (
        _directional_evaluation_record(item.directional_accuracy.evaluation)
        if item.directional_accuracy.evaluation is not None
        else None
    ),
}
```

Serialize count groups, micro/macro rates, comparable/improved slice counts and chronological slice details. Keep existing continuous fields unchanged and do not add winner/probability fields.

- [ ] **Step 6: Run runner and regression verification**

```bash
python3 -m pytest -o addopts='' tests/research/test_r5_baseline_runner.py tests/research/test_provider_candidate_runner.py -q
python3 -m ruff check src/market_regime_alpha/research/r5_baseline_runner.py tests/research/test_r5_baseline_runner.py
python3 -m mypy src/market_regime_alpha/research/r5_baseline_runner.py
```

Expected: all tests and scoped checks pass; the existing four B0 and five B1 names and continuous metrics remain unchanged.

- [ ] **Step 7: Commit runner integration**

```bash
git add src/market_regime_alpha/research/r5_baseline_runner.py tests/research/test_r5_baseline_runner.py
git commit -m "feat: attach directional evidence to R5 baselines"
```

---

### Task 3: WP-3 Artifact Identity and Public Integration

**Files:**
- Modify: `src/market_regime_alpha/research/wp3_orchestrator.py`
- Modify: `tests/research/test_wp3_orchestrator.py`
- Modify: `tests/research/test_wp3_public_api.py`

**Interfaces:**
- Consumes: `R5_NEXT_SESSION_POSITIVE_RETURN_TOP5_SPEC_ID` and additive evaluation records.
- Produces: successful manifest field `evaluation_protocol_ids` and stable public Candidate imports.

- [ ] **Step 1: Write failing manifest identity and public API assertions**

For a successful fake backend run, assert:

```python
assert manifest["evaluation_protocol_ids"] == [
    "R5_NEXT_SESSION_POSITIVE_RETURN_TOP5_V1"
]
```

Assert intended names import from `market_regime_alpha.candidates`, while private count helpers remain absent from `__all__`.

- [ ] **Step 2: Run integration tests and confirm failure**

```bash
python3 -m pytest -o addopts='' tests/research/test_wp3_orchestrator.py tests/research/test_wp3_public_api.py -q
```

Expected: manifest assertion fails before the protocol identity is added.

- [ ] **Step 3: Add the manifest protocol identity**

Import the constant from the Candidate module and add this common successful-run manifest field:

```python
"evaluation_protocol_ids": [R5_NEXT_SESSION_POSITIVE_RETURN_TOP5_SPEC_ID],
```

Record it for every successful WP-3 run even when eligibility yields no Candidate metrics: it identifies the declared protocol, not a fabricated result. Failure artifacts remain unchanged.

- [ ] **Step 4: Verify artifact determinism and orchestration**

```bash
python3 -m pytest -o addopts='' tests/research/test_wp3_orchestrator.py tests/research/test_wp3_run_artifacts.py tests/research/test_wp3_public_api.py -q
python3 -m ruff check src/market_regime_alpha/research/wp3_orchestrator.py tests/research/test_wp3_orchestrator.py tests/research/test_wp3_public_api.py
python3 -m mypy src/market_regime_alpha/research/wp3_orchestrator.py
```

Expected: all tests and scoped checks pass; existing artifact file sets and non-overwrite behavior remain unchanged.

- [ ] **Step 5: Commit artifact integration**

```bash
git add src/market_regime_alpha/research/wp3_orchestrator.py tests/research/test_wp3_orchestrator.py tests/research/test_wp3_public_api.py
git commit -m "feat: identify WP-3 directional evaluation protocol"
```

---

### Task 4: Documentation, Verification and Architecture Review

**Files:**
- Modify: `docs/research/R5-Current-Status.md`
- Modify: `docs/research/R5-WP3-Provider-Routing-Status.md`

**Interfaces:**
- Consumes: final code behavior and exact command results from Tasks 1-3.
- Produces: current implementation status, verification record and explicit next-package boundary.

- [ ] **Step 1: Run the complete affected test set**

```bash
python3 -m pytest -o addopts='' tests/candidates/test_directional_accuracy.py tests/candidates/test_baseline_ranking_evaluation_guards.py tests/research/test_r5_baseline_runner.py tests/research/test_provider_candidate_runner.py tests/research/test_wp3_orchestrator.py tests/research/test_wp3_run_artifacts.py tests/research/test_wp3_public_api.py tests/research/test_wp3_candidate_cli.py -q
```

Expected: all affected tests pass.

- [ ] **Step 2: Run scoped static verification**

```bash
python3 -m ruff check src/market_regime_alpha/candidates/directional_accuracy.py src/market_regime_alpha/candidates/__init__.py src/market_regime_alpha/research/r5_baseline_runner.py src/market_regime_alpha/research/wp3_orchestrator.py tests/candidates/test_directional_accuracy.py tests/research/test_r5_baseline_runner.py tests/research/test_wp3_orchestrator.py tests/research/test_wp3_public_api.py
python3 -m mypy src/market_regime_alpha/candidates/directional_accuracy.py src/market_regime_alpha/research/r5_baseline_runner.py src/market_regime_alpha/research/wp3_orchestrator.py
```

Expected: scoped Ruff and mypy pass.

- [ ] **Step 3: Run full repository checks and preserve unrelated failures**

```bash
python3 -m pytest -o addopts='' -q
python3 -m ruff check .
python3 -m mypy
```

Expected: accurately record pass/fail output. Do not repair unrelated known import-file mismatch, existing F401 or existing full-mypy debt unless this increment caused the failure.

- [ ] **Step 4: Update current-status documentation**

Record:

```text
WP-3 Candidate directional diagnostic       IMPLEMENTED / VERIFIED
Metric identity                              R5_NEXT_SESSION_POSITIVE_RETURN_TOP5_V1
Applicable Target                            Next-Session Close Return only
Tencent authority                            EXPLORATORY
Real Xuntou run                              STILL NOT AVAILABLE unless supplied now
Entry timing accuracy                        NOT YET AVAILABLE
Exit timing accuracy                         NOT YET AVAILABLE
Trading execution                            OUT OF SCOPE
```

Include exact verification commands and results. Keep WP-4 as the next recommended implementation package.

- [ ] **Step 5: Manually review architecture and leakage**

Inspect `git diff` and confirm:

- no Target value reaches B0/B1 ranking construction;
- unavailable Top-5 Targets are not backfilled;
- no current/retrieval time becomes historical availability evidence;
- no metric is named probability, Entry, Exit or execution authority;
- data eligibility is unchanged;
- manifest identity includes result-affecting metric semantics;
- no Candidate score or model identity changes.

- [ ] **Step 6: Commit documentation and verification evidence**

```bash
git add docs/research/R5-Current-Status.md docs/research/R5-WP3-Provider-Routing-Status.md
git commit -m "docs: record WP-3 directional diagnostic status"
```

- [ ] **Step 7: Confirm final repository state**

```bash
git status --short
git log -5 --oneline
```

Expected: clean working tree and four intentional commits after the approved design commit.
