# WP-3 Provider Routing and Candidate Runs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an authority-aware WP-3 runner that prefers a valid Xuntou normalized export, temporarily uses the existing Tencent composite path for `EXPLORATORY` training data when Xuntou is unavailable, runs fixed B0/B1 baselines, and writes immutable evidence artifacts.

**Architecture:** A pure routing module selects one complete provider backend from immutable capability reports. Xuntou artifacts flow through existing Calendar, Universe, Eligibility, Feature, Target and Candidate contracts; Tencent retains its existing exploratory materialization. Both backends share one extracted fixed B0/B1 evaluation seam and one atomic run-artifact writer.

**Tech Stack:** Python 3.12, frozen slotted dataclasses, enums, pathlib, JSON/SHA-256, existing R5 contracts, pytest, Ruff and mypy.

## Global Constraints

- Xuntou remains the canonical primary provider.
- Tencent is temporary `EXPLORATORY` training data and later an explicit auxiliary.
- No source route may emit `FORMAL_RESEARCH`.
- Xuntou `INVALID` is fail-closed; only `UNAVAILABLE` may route to Tencent in `AUTO` mode.
- A valid empty Candidate Population must remain empty and must not trigger fallback.
- Provider selection is Data/Research composition, not Candidate scoring or trading strategy logic.
- Do not implement B2, Entry, Exit, Portfolio, live trading, field-level source mixing or XtQuant runtime extraction.
- Keep import-time XtQuant optional; no new `requirements.txt` dependency.
- Preserve unknown PIT, availability, finality, adjustment and buyability semantics.
- Do not modify B0/B1 scoring arithmetic.

---

## File Structure

Create or modify these bounded units:

```text
docs/references/providers/xuntou/README.md
    Local provider-document index, evidence tiers, API summary and limitations.

docs/references/providers/xuntou/source-manifest.json
    URL, title, retrieval date, evidence tier and retrieved-byte SHA-256.

src/market_regime_alpha/research/provider_routing.py
    Pure provider capability and source-selection policy.

src/market_regime_alpha/research/r5_baseline_runner.py
    Shared fixed B0/B1 Target-panel evaluation seam.

src/market_regime_alpha/research/provider_candidate_runner.py
    ProviderRehearsalMarketArtifact to Candidate panels and evaluation.

src/market_regime_alpha/research/wp3_run_artifacts.py
    Atomic, hashed, non-overwriting success/failure artifacts.

src/market_regime_alpha/research/wp3_orchestrator.py
    Backend composition without CLI parsing or public snapshot side effects.

scripts/run_wp3_candidate_research.py
    CLI arguments, current revision/config identity and dependency composition.

tests/research/test_provider_routing.py
tests/research/test_r5_baseline_runner.py
tests/research/test_provider_candidate_runner.py
tests/research/test_wp3_run_artifacts.py
tests/research/test_wp3_orchestrator.py
tests/research/test_wp3_candidate_cli.py
tests/research/test_wp3_public_api.py
    Focused contract, pipeline, artifact and CLI coverage.
```

---

### Task 1: Preserve the Supplied Provider Documentation as a Local Evidence Index

**Files:**
- Create: `docs/references/providers/xuntou/README.md`
- Create: `docs/references/providers/xuntou/source-manifest.json`
- Modify: `docs/research/R5-Xuntou-P0-Official-Documentation-Evidence.md`

**Interfaces:**
- Consumes: the seven supplied MiniQMT/Xuntou URLs and exact retrieved page bytes.
- Produces: a stable human-readable reference and a machine-readable source manifest; no mirrored HTML.

- [ ] **Step 1: Retrieve each page and calculate exact SHA-256 values**

Run one `curl -fsSL` request per URL, retain the response only in a temporary directory, and compute
the digest with `shasum -a 256`. Record retrieval failures explicitly instead of inventing hashes.

- [ ] **Step 2: Write the source manifest**

Use this exact shape for every source:

```json
{
  "schema_version": "xuntou-provider-document-source-manifest-v1",
  "retrieved_on": "2026-07-16",
  "sources": [
    {
      "url": "https://www.miniqmt.com/pages/docs/xtdata.html",
      "title": "xtdata行情模块",
      "evidence_tier": "SUPPLEMENTARY_MINIQMT",
      "content_sha256": null,
      "retrieval_status": "RETRIEVAL_FAILED"
    }
  ]
}
```

The example shows the exact failure representation. A retrieved source must instead contain the
actual 64-character lowercase SHA-256 digest and `retrieval_status: RETRIEVED` before commit.

- [ ] **Step 3: Write the summarized reference**

Cover:

```text
provider/product/runtime relationships
API inventory relevant to P0/WP-3
period and adjustment enums
K-line and tick fields
calendar and sector interfaces
ST, suspension and limit-price interfaces
what each source confirms
what each source does not establish
normative mapping-spec link
```

Paraphrase source content. Do not copy complete pages.

- [ ] **Step 4: Link the local index from the existing evidence note**

Add one authority note explaining that ThinkTrader pages are first-party evidence and MiniQMT is a
supplementary cross-check.

- [ ] **Step 5: Validate the manifest and documentation diff**

Run:

```bash
python3 -m json.tool docs/references/providers/xuntou/source-manifest.json
git diff --check
```

Expected: JSON prints successfully and `git diff --check` has no output.

- [ ] **Step 6: Commit**

```bash
git add docs/references/providers/xuntou docs/research/R5-Xuntou-P0-Official-Documentation-Evidence.md
git commit -m "docs: preserve Xuntou provider references"
```

---

### Task 2: Add Pure Authority-Aware Provider Routing

**Files:**
- Create: `src/market_regime_alpha/research/provider_routing.py`
- Create: `tests/research/test_provider_routing.py`

**Interfaces:**
- Consumes: `DataEligibility` and immutable provider preflight facts.
- Produces: `select_candidate_data_source(...) -> ProviderSelectionDecision`.

- [ ] **Step 1: Write failing routing tests**

Cover the exact policy:

```python
def test_auto_prefers_available_xuntou() -> None:
    decision = select_candidate_data_source(
        mode=CandidateRunSourceMode.AUTO,
        minimum_eligibility=DataEligibility.EXPLORATORY,
        xuntou=_report(CandidateDataSource.XUNTOU, ProviderAvailabilityStatus.AVAILABLE, DataEligibility.REHEARSAL),
        tencent=_report(CandidateDataSource.TENCENT_COMPOSITE, ProviderAvailabilityStatus.AVAILABLE, DataEligibility.EXPLORATORY),
    )
    assert decision.selected_source is CandidateDataSource.XUNTOU


def test_auto_uses_tencent_only_when_xuntou_is_unavailable() -> None:
    decision = select_candidate_data_source(
        mode=CandidateRunSourceMode.AUTO,
        minimum_eligibility=DataEligibility.EXPLORATORY,
        xuntou=_report(CandidateDataSource.XUNTOU, ProviderAvailabilityStatus.UNAVAILABLE, DataEligibility.REHEARSAL),
        tencent=_report(CandidateDataSource.TENCENT_COMPOSITE, ProviderAvailabilityStatus.AVAILABLE, DataEligibility.EXPLORATORY),
    )
    assert decision.selected_source is CandidateDataSource.TENCENT_COMPOSITE
    assert decision.selected_data_eligibility is DataEligibility.EXPLORATORY


def test_invalid_xuntou_fails_closed_without_tencent_fallback() -> None:
    with pytest.raises(ProviderRoutingError) as exc_info:
        select_candidate_data_source(
            mode=CandidateRunSourceMode.AUTO,
            minimum_eligibility=DataEligibility.EXPLORATORY,
            xuntou=_report(CandidateDataSource.XUNTOU, ProviderAvailabilityStatus.INVALID, DataEligibility.REHEARSAL),
            tencent=_report(CandidateDataSource.TENCENT_COMPOSITE, ProviderAvailabilityStatus.AVAILABLE, DataEligibility.EXPLORATORY),
        )
    assert exc_info.value.code is ProviderRoutingErrorCode.SOURCE_INVALID


def test_rehearsal_requirement_rejects_tencent() -> None:
    with pytest.raises(ProviderRoutingError) as exc_info:
        select_candidate_data_source(
            mode=CandidateRunSourceMode.AUTO,
            minimum_eligibility=DataEligibility.REHEARSAL,
            xuntou=_report(CandidateDataSource.XUNTOU, ProviderAvailabilityStatus.UNAVAILABLE, DataEligibility.REHEARSAL),
            tencent=_report(CandidateDataSource.TENCENT_COMPOSITE, ProviderAvailabilityStatus.AVAILABLE, DataEligibility.EXPLORATORY),
        )
    assert exc_info.value.code is ProviderRoutingErrorCode.AUTHORITY_UNSUPPORTED
```

Also test explicit modes, no source, deterministic identity and identity change when a report or
policy version changes.

- [ ] **Step 2: Run the focused tests and confirm import failure**

Run:

```bash
python3 -m pytest tests/research/test_provider_routing.py -q
```

Expected: collection fails because `provider_routing` does not exist.

- [ ] **Step 3: Implement the contracts and policy**

Implement:

```python
PROVIDER_SELECTION_POLICY_VERSION = "R5_CANDIDATE_DATA_SOURCE_SELECTION_V1"


class CandidateDataSource(str, Enum):
    XUNTOU = "XUNTOU"
    TENCENT_COMPOSITE = "TENCENT_COMPOSITE"


class CandidateRunSourceMode(str, Enum):
    AUTO = "AUTO"
    XUNTOU = "XUNTOU"
    TENCENT = "TENCENT"


class ProviderAvailabilityStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    INVALID = "INVALID"


class ProviderRoutingErrorCode(str, Enum):
    REQUIRED_SOURCE_UNAVAILABLE = "PROVIDER_ROUTE_REQUIRED_SOURCE_UNAVAILABLE"
    SOURCE_INVALID = "PROVIDER_ROUTE_SOURCE_INVALID"
    AUTHORITY_UNSUPPORTED = "PROVIDER_ROUTE_AUTHORITY_UNSUPPORTED"
    NO_ELIGIBLE_SOURCE = "PROVIDER_ROUTE_NO_ELIGIBLE_SOURCE"
```

Use frozen slotted dataclasses for reports, attempts and decisions. Compute the decision ID from
canonical JSON containing the policy version, mode, minimum eligibility, both reports and attempts.

- [ ] **Step 4: Run focused tests**

Run:

```bash
python3 -m pytest tests/research/test_provider_routing.py -q
```

Expected: all routing tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/market_regime_alpha/research/provider_routing.py tests/research/test_provider_routing.py
git commit -m "feat: add authority-aware provider routing"
```

---

### Task 3: Extract the Fixed B0/B1 Evaluation Seam

**Files:**
- Create: `src/market_regime_alpha/research/r5_baseline_runner.py`
- Create: `tests/research/test_r5_baseline_runner.py`
- Modify: `src/market_regime_alpha/research/tencent_composite_runner.py`
- Modify: `tests/research/test_tencent_composite_runner.py`

**Interfaces:**
- Consumes: same-target `CandidateResearchDataset` slices.
- Produces: `run_r5_target_baselines(...) -> R5TargetBaselineRun` and frozen B1 specs.

- [ ] **Step 1: Add characterization tests around the existing Tencent output**

Capture the existing names, feature IDs, model IDs and evaluation summaries for four B0 controls and
B1-A through B1-E before extraction. Assert no target values affect ranking scores.

- [ ] **Step 2: Run characterization tests**

Run:

```bash
python3 -m pytest tests/research/test_tencent_composite_runner.py -q
```

Expected: pass before refactoring.

- [ ] **Step 3: Write the shared-runner tests**

Use two small Candidate slices and assert:

```python
result = run_r5_target_baselines(
    datasets=(first, second),
    code_revision="abc123",
    config_hash="sha256:config",
)
assert len(result.b0_evaluations) == 4
assert tuple(item.name for item in result.b1_evaluations) == (
    "B1-A", "B1-B", "B1-C", "B1-D", "B1-E"
)
assert result.panel.slice_count == 2
```

- [ ] **Step 4: Implement the shared seam**

Move only provider-neutral logic into `r5_baseline_runner.py`:

```python
@dataclass(frozen=True, slots=True)
class NamedCandidatePanelEvaluation:
    name: str
    feature_ids: tuple[FeatureDefinitionId, ...]
    evaluation: CandidatePanelEvaluation


@dataclass(frozen=True, slots=True)
class R5TargetBaselineRun:
    target_id: TargetId
    panel: CandidateResearchPanel
    b0_evaluations: tuple[NamedCandidatePanelEvaluation, ...]
    b1_evaluations: tuple[NamedCandidatePanelEvaluation, ...]
```

Expose `r5_b1_fixed_specs()`, `run_r5_target_baselines(...)` and
`candidate_evaluation_record(...)`. Keep existing Tencent public functions and serialized output
stable by delegating to the new seam.

- [ ] **Step 5: Run shared and Tencent tests**

Run:

```bash
python3 -m pytest tests/research/test_r5_baseline_runner.py tests/research/test_tencent_composite_runner.py -q
```

Expected: pass with unchanged Tencent semantics.

- [ ] **Step 6: Commit**

```bash
git add src/market_regime_alpha/research/r5_baseline_runner.py src/market_regime_alpha/research/tencent_composite_runner.py tests/research/test_r5_baseline_runner.py tests/research/test_tencent_composite_runner.py
git commit -m "refactor: share fixed R5 baseline evaluation"
```

---

### Task 4: Build Provider Artifact Candidate Panels

**Files:**
- Create: `src/market_regime_alpha/research/provider_candidate_runner.py`
- Create: `tests/research/test_provider_candidate_runner.py`

**Interfaces:**
- Consumes: `ProviderRehearsalMarketArtifact`, `TradingEligibilityPolicy`, materialization identity and `decision_count`.
- Produces: `run_provider_candidate_experiment(...) -> ProviderCandidateRun`.

- [ ] **Step 1: Write a complete-v2 fixture test**

Build a small `ProviderRehearsalMarketArtifact` directly with two Decision Times, sufficient prior
bars, `BUYABLE` observations, a calendar-resolved next session and two symbols. Assert three Target
runs, B0/B1 evaluation and `REHEARSAL` eligibility.

```python
run = run_provider_candidate_experiment(
    market_artifact=artifact,
    eligibility_policy=r5_provider_rehearsal_trading_eligibility_policy_v2(
        minimum_liquidity_value=1.0,
        liquidity_measure_id="TEST_MEDIAN_AMOUNT_20D",
    ),
    materialized_at=AsOfTime(datetime(2026, 7, 20, tzinfo=TZ)),
    code_revision="abc123",
    config_hash="sha256:config",
    decision_count=2,
)
assert run.outcome is ProviderCandidateRunOutcome.EVALUATED
assert run.data_eligibility is DataEligibility.REHEARSAL
assert len(run.target_runs) == 3
```

- [ ] **Step 2: Write the truthful empty-population test**

Use `DecisionBuyabilityStatus.UNKNOWN` and assert:

```python
assert run.outcome is ProviderCandidateRunOutcome.NO_CANDIDATES_AFTER_ELIGIBILITY
assert run.target_runs == ()
assert all(item.eligible_count == 0 for item in run.decision_diagnostics)
```

Also assert that the runner never changes the source and never weakens the supplied policy.

- [ ] **Step 3: Run tests and confirm import failure**

Run:

```bash
python3 -m pytest tests/research/test_provider_candidate_runner.py -q
```

Expected: import failure because the runner is absent.

- [ ] **Step 4: Implement the provider pipeline**

Implement:

```python
class ProviderCandidateRunOutcome(str, Enum):
    EVALUATED = "EVALUATED"
    NO_CANDIDATES_AFTER_ELIGIBILITY = "NO_CANDIDATES_AFTER_ELIGIBILITY"


@dataclass(frozen=True, slots=True)
class CandidateDecisionDiagnostic:
    decision_time: DecisionTime
    universe_member_count: int
    eligible_count: int
    ineligible_count: int
    unknown_count: int


@dataclass(frozen=True, slots=True)
class ProviderCandidateRun:
    outcome: ProviderCandidateRunOutcome
    data_eligibility: DataEligibility
    decision_times: tuple[DecisionTime, ...]
    decision_diagnostics: tuple[CandidateDecisionDiagnostic, ...]
    target_runs: tuple[R5TargetBaselineRun, ...]
    limitations: tuple[str, ...]
```

For each selected Decision Time:

1. materialize v2 eligibility;
2. build the exact Population intersection;
3. retain status counts even when empty;
4. materialize baseline Features only for non-empty populations;
5. materialize calendar-resolved Close Return/MFE/MAE targets;
6. build one dataset per Target;
7. run the shared fixed baseline seam by Target.

- [ ] **Step 5: Run focused and affected Candidate tests**

Run:

```bash
python3 -m pytest tests/research/test_provider_candidate_runner.py tests/candidates -q
```

Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add src/market_regime_alpha/research/provider_candidate_runner.py tests/research/test_provider_candidate_runner.py
git commit -m "feat: run provider-backed R5 candidate panels"
```

---

### Task 5: Add Atomic WP-3 Run Artifacts

**Files:**
- Create: `src/market_regime_alpha/research/wp3_run_artifacts.py`
- Create: `tests/research/test_wp3_run_artifacts.py`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: JSON-ready manifest, selection decision, source references, quality, Candidate summaries and limitations.
- Produces: one complete run directory or one explicit failure directory.

- [ ] **Step 1: Write failing success-artifact tests**

Assert the exact nine filenames, no overwrite, canonical JSON, per-file SHA-256 and staging cleanup.

```python
output = write_wp3_candidate_run(root=tmp_path, run_id="run-001", payload=payload)
assert {path.name for path in output.iterdir()} == {
    "manifest.json", "provider_selection.json", "source_artifacts.json",
    "quality.json", "candidate_panel_summary.json", "b0_b1_evaluation.json",
    "limitations.json", "report.md", "SHA256SUMS.json",
}
with pytest.raises(FileExistsError):
    write_wp3_candidate_run(root=tmp_path, run_id="run-001", payload=payload)
```

- [ ] **Step 2: Write failure and empty-population tests**

Failure artifacts contain `manifest.json`, `failure.json` and `SHA256SUMS.json`, with no evaluation.
Empty-population success writes `b0_b1_evaluation.json` as:

```json
{"status":"NOT_PRODUCED","reason":"NO_CANDIDATES_AFTER_ELIGIBILITY","targets":[]}
```

- [ ] **Step 3: Run tests and verify import failure**

Run:

```bash
python3 -m pytest tests/research/test_wp3_run_artifacts.py -q
```

- [ ] **Step 4: Implement staged atomic writes**

Use canonical UTF-8 JSON with sorted keys and a trailing newline. Hash all files except
`SHA256SUMS.json`, write the checksum map last, validate the staged filename set, then rename.
Remove only the owned staging directory on failure.

- [ ] **Step 5: Ignore run data, not specifications**

Add:

```gitignore
data/processed/r5_candidate_runs/
```

- [ ] **Step 6: Run focused tests and commit**

```bash
python3 -m pytest tests/research/test_wp3_run_artifacts.py -q
git add .gitignore src/market_regime_alpha/research/wp3_run_artifacts.py tests/research/test_wp3_run_artifacts.py
git commit -m "feat: write immutable WP-3 run artifacts"
```

---

### Task 6: Compose Xuntou and Tencent Backends Without Side Effects

**Files:**
- Create: `src/market_regime_alpha/research/wp3_orchestrator.py`
- Create: `tests/research/test_wp3_orchestrator.py`
- Create: `scripts/run_wp3_candidate_research.py`
- Create: `tests/research/test_wp3_candidate_cli.py`

**Interfaces:**
- Consumes: `WP3RunRequest`, optional Xuntou bundle, injected Tencent backend and output root.
- Produces: `execute_wp3_candidate_run(...) -> Path`.

- [ ] **Step 1: Write orchestrator routing tests with injected backends**

Test:

- valid Xuntou is selected and Tencent is not called;
- absent Xuntou selects Tencent for exploratory requests;
- corrupt Xuntou fails without calling Tencent;
- rehearsal requests reject Tencent;
- Xuntou empty Population writes a successful diagnostic artifact;
- Tencent output remains `EXPLORATORY` and preserves composite limitations.

- [ ] **Step 2: Write CLI parsing tests**

Assert:

```python
args = build_parser().parse_args(["--source", "auto"])
assert args.minimum_eligibility == "exploratory"

with pytest.raises(SystemExit):
    build_parser().parse_args(["--source", "xuntou"])
```

The second validation may occur in `main()` if argparse cannot express the conditional requirement.
Tests inject orchestration and perform no network calls.

- [ ] **Step 3: Run tests and verify missing-module failures**

Run:

```bash
python3 -m pytest tests/research/test_wp3_orchestrator.py tests/research/test_wp3_candidate_cli.py -q
```

- [ ] **Step 4: Implement request and orchestration contracts**

```python
@dataclass(frozen=True, slots=True)
class WP3RunRequest:
    source_mode: CandidateRunSourceMode
    minimum_eligibility: DataEligibility
    output_root: Path
    xuntou_bundle: Path | None
    decision_count: int
    code_revision: str
    config_hash: str


def execute_wp3_candidate_run(
    request: WP3RunRequest,
    *,
    tencent_backend: TencentWP3Backend,
) -> Path:
    xuntou_report = preflight_xuntou_bundle(request.xuntou_bundle)
    tencent_report = tencent_backend.capability_report()
    selection = select_candidate_data_source(
        mode=request.source_mode,
        minimum_eligibility=request.minimum_eligibility,
        xuntou=xuntou_report,
        tencent=tencent_report,
    )
    if selection.selected_source is CandidateDataSource.XUNTOU:
        return _execute_xuntou_run(request, selection)
    return _execute_tencent_run(request, selection, tencent_backend)
```

`TencentWP3Backend` is a protocol. The production implementation reuses existing composite
acquisition, quality and Candidate-run functions but does not call
`write_dividend_trend_snapshot()`.

- [ ] **Step 5: Implement the CLI**

Supported arguments:

```text
--source auto|xuntou|tencent
--minimum-eligibility exploratory|rehearsal
--xuntou-bundle PATH
--output-root PATH
--watchlist PATH
--decision-count INTEGER
--history-calendar-days INTEGER
--timeout-seconds FLOAT
--retry-count INTEGER
```

The CLI captures Git revision, computes a canonical config hash and calls the orchestrator. It does
not contain provider arithmetic or write the Legacy Pages snapshot.

- [ ] **Step 6: Run focused tests**

```bash
python3 -m pytest tests/research/test_wp3_orchestrator.py tests/research/test_wp3_candidate_cli.py tests/research/test_tencent_composite_runner.py -q
```

Expected: pass.

- [ ] **Step 7: Commit**

```bash
git add src/market_regime_alpha/research/wp3_orchestrator.py scripts/run_wp3_candidate_research.py tests/research/test_wp3_orchestrator.py tests/research/test_wp3_candidate_cli.py
git commit -m "feat: orchestrate source-aware WP-3 runs"
```

---

### Task 7: Integrate Public APIs and Current Status

**Files:**
- Modify: `src/market_regime_alpha/research/__init__.py`
- Create: `docs/research/R5-WP3-Provider-Routing-Status.md`
- Modify: `docs/research/R5-Current-Status.md`
- Modify: `README.md`
- Create: `tests/research/test_wp3_public_api.py`

**Interfaces:**
- Consumes: completed intended routing/runner/artifact APIs.
- Produces: stable public imports and accurate current authority documentation.

- [ ] **Step 1: Add a public-import test**

Assert only intended contracts and entry functions are importable from
`market_regime_alpha.research`; keep CLI helpers and private serializers internal.

- [ ] **Step 2: Add public exports with lazy loading where Candidate imports would cycle**

Public APIs include:

```text
CandidateDataSource
CandidateRunSourceMode
ProviderAvailabilityStatus
ProviderCapabilityReport
ProviderSelectionDecision
ProviderRoutingError
select_candidate_data_source
ProviderCandidateRun
ProviderCandidateRunOutcome
run_provider_candidate_experiment
WP3RunRequest
execute_wp3_candidate_run
```

- [ ] **Step 3: Write the implementation-status document**

Record:

```text
provider-document local index                         IMPLEMENTED
authority-aware router                               IMPLEMENTED
Tencent temporary training route                     EXPLORATORY
Xuntou normalized-export execution infrastructure     IMPLEMENTED
real Xuntou bundle run                                NOT AVAILABLE unless actually executed
WP-3 overall                                          PENDING until real non-empty Xuntou B0/B1 run
B2                                                    NOT IMPLEMENTED
```

Include the buyability/empty-Population limitation.

- [ ] **Step 4: Update current status and README**

Add the new CLI and explain that `AUTO` does not silently downgrade a rehearsal request. Do not
claim a real provider run or Alpha.

- [ ] **Step 5: Run focused import and documentation checks**

```bash
python3 -m pytest tests/research/test_provider_routing.py tests/research/test_provider_candidate_runner.py tests/research/test_wp3_orchestrator.py tests/research/test_wp3_candidate_cli.py -q
git diff --check
```

- [ ] **Step 6: Commit**

```bash
git add src/market_regime_alpha/research/__init__.py docs/research/R5-WP3-Provider-Routing-Status.md docs/research/R5-Current-Status.md README.md tests/research/test_wp3_public_api.py
git commit -m "docs: record WP-3 routing infrastructure"
```

---

### Task 8: Final Verification and Architecture Review

**Files:**
- Modify only files required to fix defects introduced by Tasks 1–7.

**Interfaces:**
- Consumes: the complete bounded change set.
- Produces: evidence-backed verification report and a clean worktree.

- [ ] **Step 1: Run all focused WP-3 tests**

```bash
python3 -m pytest \
  tests/research/test_provider_routing.py \
  tests/research/test_r5_baseline_runner.py \
  tests/research/test_provider_candidate_runner.py \
  tests/research/test_wp3_run_artifacts.py \
  tests/research/test_wp3_orchestrator.py \
  tests/research/test_wp3_candidate_cli.py -q
```

- [ ] **Step 2: Run affected-area tests**

```bash
python3 -m pytest tests/research tests/candidates tests/universe tests/data tests/features -q
```

- [ ] **Step 3: Run scoped Ruff and mypy**

```bash
python3 -m ruff check \
  src/market_regime_alpha/research/provider_routing.py \
  src/market_regime_alpha/research/r5_baseline_runner.py \
  src/market_regime_alpha/research/provider_candidate_runner.py \
  src/market_regime_alpha/research/wp3_run_artifacts.py \
  src/market_regime_alpha/research/wp3_orchestrator.py \
  scripts/run_wp3_candidate_research.py \
  tests/research/test_provider_routing.py \
  tests/research/test_r5_baseline_runner.py \
  tests/research/test_provider_candidate_runner.py \
  tests/research/test_wp3_run_artifacts.py \
  tests/research/test_wp3_orchestrator.py \
  tests/research/test_wp3_candidate_cli.py

python3 -m mypy \
  src/market_regime_alpha/research/provider_routing.py \
  src/market_regime_alpha/research/r5_baseline_runner.py \
  src/market_regime_alpha/research/provider_candidate_runner.py \
  src/market_regime_alpha/research/wp3_run_artifacts.py \
  src/market_regime_alpha/research/wp3_orchestrator.py \
  scripts/run_wp3_candidate_research.py
```

- [ ] **Step 4: Attempt full quality commands**

```bash
python3 -m pytest
python3 -m ruff check .
python3 -m mypy
```

Report focused, affected and full results separately. Do not hide known pre-existing failures.

- [ ] **Step 5: Manually review authority and leakage invariants**

Confirm:

```text
Tencent never exceeds EXPLORATORY
invalid Xuntou never falls back
empty Xuntou Population never switches source
UNKNOWN never becomes ELIGIBLE
retrieval time never becomes availability time
no future Target enters Feature computation
next session always comes from TradingCalendarArtifact
no public snapshot or live order side effect exists
no import-time xtquant dependency exists
no B0/B1 arithmetic changed
no FORMAL_RESEARCH or Alpha claim exists
```

- [ ] **Step 6: Commit any bounded verification fixes**

If verification required changes, create one final focused commit such as:

```bash
git add src/market_regime_alpha/research/wp3_orchestrator.py tests/research/test_wp3_orchestrator.py
git commit -m "fix: close WP-3 verification gaps"
```

Stage only the files actually repaired; the two paths above illustrate a bounded orchestrator fix.

- [ ] **Step 7: Confirm repository state**

```bash
git status --short --branch
git log --oneline --reverse 28982b1..HEAD
```

Expected: clean worktree, intentional local commits, no push.
