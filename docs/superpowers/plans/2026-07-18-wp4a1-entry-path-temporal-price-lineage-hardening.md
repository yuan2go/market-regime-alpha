# WP-4A.1 Entry Path Temporal and Price-Lineage Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make WP-4A Entry Path Target materialization fail closed on untraceable reference prices and distinguish not-yet-available evidence from confirmed missing future evidence.

**Architecture:** The Data domain gains complete, self-identifying reference and future-path evidence. Entry receives only those evidence contracts, validates their exact scope and lineage, then derives a status according to exchange close, readiness, completeness availability, coverage watermark, and finally missing evidence. Readiness changes materialization evidence identity but not the target-label definition.

**Tech Stack:** Python 3.12, frozen dataclasses, Enum, pytest, Ruff, mypy, GitHub Actions.

## Global Constraints

- Base all work on remote `cf5d29b1eb13991ff4b82e5c19e251491d7c828c`; preserve the user-owned `.idea/misc.xml`.
- Do not add an Entry Gate, Entry Proposal, Entry model, Candidate B0/B1 change, WP-3 runner/artifact change, Portfolio, or Execution work.
- Do not accept `RehearsalDecisionSnapshot` in `materialize_entry_path_target()` and do not create an implicit snapshot adapter.
- Evidence is REHEARSAL compatibility authority only; do not assert Entry accuracy, Alpha, or Xuntou execution.
- `EntryBarrierSpec` requires `upper_return > 0`, `-1.0 < lower_return < 0`, and positive integer `horizon_sessions`.
- Future bars, suspensions, completeness and references must carry explicit Dataset lineage and deterministic evidence identities.
- Completeness scope must exactly equal `CandidatePopulation.symbols`; no date-only or partial-symbol coverage is valid.
- Commit domain code/tests/normative status updates separately from `.github/workflows/ci.yml`.

---

## File Structure

- Modify `src/market_regime_alpha/data/path_evidence.py`: Data-owned reference, lineage, readiness, and completeness contracts plus deterministic evidence-ID builder.
- Modify `src/market_regime_alpha/data/__init__.py`: export the new Data contracts.
- Modify `src/market_regime_alpha/strategies/entry/contracts.py`: reason-code enum, lower-barrier validation, observation matrix, and materialization audit IDs.
- Modify `src/market_regime_alpha/strategies/entry/materialization.py`: replace snapshot input with complete reference evidence; validate evidence lineage/scope; evaluate temporal completeness; hash and retain evidence IDs.
- Modify `src/market_regime_alpha/strategies/entry/__init__.py`: export `EntryPathReasonCode`.
- Modify `tests/data/test_path_evidence.py`, `tests/strategies/entry/test_contracts.py`, and `tests/strategies/entry/test_materialization.py`: use explicit lineage fixtures and prove the contract matrix.
- Modify `docs/specs/Entry-Path-Target-V1.md` and `docs/research/R5-Current-Status.md`: record the WP-4A.1 contract and remaining provider-backed blocker.
- Create `.github/workflows/ci.yml`: run the required Python 3.12 quality suite in a separate commit.

### Task 1: Add Data Evidence Identity and Completeness Contracts

**Files:**
- Modify: `src/market_regime_alpha/data/path_evidence.py`
- Modify: `src/market_regime_alpha/data/__init__.py`
- Test: `tests/data/test_path_evidence.py`

**Interfaces:**
- Produces `RehearsalEntryReferenceEvidence`, `RehearsalFuturePathSessionReadiness`, and `RehearsalFuturePathEvidenceCompleteness`.
- Extends `RehearsalFutureDailyBar` and `RehearsalFutureSuspensionEvidence` with `source_dataset_id: DatasetId` and `evidence_id: ArtifactId`.
- Each evidence ID is deterministically built from the complete canonical evidence payload.

- [ ] **Step 1: Write failing Data-domain tests**

```python
def test_reference_evidence_is_identified_and_requires_decision_availability() -> None:
    evidence = RehearsalEntryReferenceEvidence(
        symbol="000001.SZ",
        decision_time=DecisionTime(_at(14, 55)),
        reference_price=10.0,
        price_adjustment_basis="RAW_UNADJUSTED_TRADABLE_PRICE_V1",
        available_at=AvailabilityTime(_at(14, 55)),
        source_dataset_id=DatasetId("dataset-reference-v1"),
        evidence_convention="DECISION_REFERENCE_ASSERTION_V1",
    )
    assert str(evidence.evidence_id).startswith("entry-reference-evidence-")

    with pytest.raises(ValueError, match="available by decision_time"):
        replace(evidence, available_at=AvailabilityTime(_at(14, 56)))


def test_completeness_rejects_duplicate_or_unordered_symbol_and_readiness_scope() -> None:
    with pytest.raises(ValueError, match="covered_symbols must be sorted"):
        _completeness(covered_symbols=("000002.SZ", "000001.SZ"))
    with pytest.raises(ValueError, match="readiness session dates must be unique"):
        _completeness(readiness=(_readiness(HORIZON_DATES[0]), _readiness(HORIZON_DATES[0])))
```

- [ ] **Step 2: Run the focused Data test to verify red**

Run: `.venv/bin/python -m pytest -q tests/data/test_path_evidence.py`

Expected: FAIL because the new contracts and evidence identities do not exist.

- [ ] **Step 3: Implement the Data contracts and IDs**

```python
@dataclass(frozen=True, slots=True)
class RehearsalEntryReferenceEvidence:
    symbol: str
    decision_time: DecisionTime
    reference_price: float
    price_adjustment_basis: str
    available_at: AvailabilityTime
    source_dataset_id: DatasetId
    evidence_convention: str

    @property
    def evidence_id(self) -> ArtifactId:
        return _evidence_id("entry-reference-evidence", _payload(self))


@dataclass(frozen=True, slots=True)
class RehearsalFuturePathSessionReadiness:
    session_date: date
    evidence_ready_at: AvailabilityTime


@dataclass(frozen=True, slots=True)
class RehearsalFuturePathEvidenceCompleteness:
    source_dataset_id: DatasetId
    available_at: AvailabilityTime
    completeness_convention: str
    covered_symbols: tuple[str, ...]
    coverage_through_session_date: date
    session_readiness: tuple[RehearsalFuturePathSessionReadiness, ...]

    @property
    def evidence_id(self) -> ArtifactId:
        return _evidence_id("future-path-completeness", _payload(self))
```

Validate semantic wrapper types, Dataset IDs, non-empty trimmed conventions, positive prices,
reference `available_at <= decision_time`, exact sorted/unique `covered_symbols`, non-empty
readiness, and chronological/unique readiness dates. Add `source_dataset_id` and deterministic
`evidence_id` to existing daily-bar and suspension payloads; do not change their OHLC/finality
semantics. Export all three new types from `market_regime_alpha.data`.

- [ ] **Step 4: Run Data tests and formatter checks**

Run: `.venv/bin/python -m pytest -q tests/data/test_path_evidence.py && .venv/bin/python -m ruff check src/market_regime_alpha/data/path_evidence.py tests/data/test_path_evidence.py`

Expected: PASS.

### Task 2: Tighten Entry Contracts and Audit Identity

**Files:**
- Modify: `src/market_regime_alpha/strategies/entry/contracts.py`
- Modify: `src/market_regime_alpha/strategies/entry/__init__.py`
- Test: `tests/strategies/entry/test_contracts.py`

**Interfaces:**
- Produces `EntryPathReasonCode(str, Enum)` with the eight approved V1 values.
- `EntryPathObservation.reason_code` consumes that enum.
- `EntryPathTargetMaterialization` retains ordered reference, consumed bar, consumed suspension, and completeness evidence IDs.

- [ ] **Step 1: Write failing contract tests**

```python
@pytest.mark.parametrize("lower_return", (-1.0, -1.01))
def test_barrier_rejects_total_loss_or_lower(lower_return: float) -> None:
    with pytest.raises(ValueError, match="greater than -1.0"):
        EntryBarrierSpec(0.02, lower_return, 3, PRICE_BASIS)


def test_observation_rejects_reason_not_permitted_by_status_and_trigger() -> None:
    with pytest.raises(ValueError, match="reason_code"):
        _observation(
            status=EntryPathObservationStatus.MISSING,
            outcome=None,
            trigger_type=None,
            reason_code=EntryPathReasonCode.OUTCOME_RESOLVED,
        )
```

- [ ] **Step 2: Run focused Entry contract test to verify red**

Run: `.venv/bin/python -m pytest -q tests/strategies/entry/test_contracts.py`

Expected: FAIL because the lower bound and typed reason matrix are absent.

- [ ] **Step 3: Implement barrier, reason, and audit-ID validation**

```python
class EntryPathReasonCode(str, Enum):
    OUTCOME_RESOLVED = "OUTCOME_RESOLVED"
    DAILY_BAR_DUAL_TOUCH_ORDER_UNRESOLVED = "DAILY_BAR_DUAL_TOUCH_ORDER_UNRESOLVED"
    HORIZON_EXHAUSTED_WITHOUT_BARRIER_TOUCH = "HORIZON_EXHAUSTED_WITHOUT_BARRIER_TOUCH"
    FUTURE_DAILY_BAR_MISSING = "FUTURE_DAILY_BAR_MISSING"
    ENTRY_REFERENCE_MISSING = "ENTRY_REFERENCE_MISSING"
    HORIZON_NOT_COMPLETE = "HORIZON_NOT_COMPLETE"
    EVIDENCE_NOT_YET_AVAILABLE = "EVIDENCE_NOT_YET_AVAILABLE"
    EVIDENCE_COVERAGE_NOT_COMPLETE = "EVIDENCE_COVERAGE_NOT_COMPLETE"
```

Replace `reason_code: str` with `EntryPathReasonCode`; reject all values not in the exact
state/outcome/trigger matrix. `ENTRY_REFERENCE_MISSING` is permitted only by `INVALID`, but the
WP-4A.1 materializer never emits it because reference tuple omissions are structural errors.
Remove the now-unreachable per-symbol `INVALID` snapshot construction from the materializer.
Require
`lower_return > -1.0`. Add these materialization audit fields and validate deterministic ordering:

```python
entry_reference_evidence_ids: tuple[ArtifactId, ...]
consumed_future_bar_evidence_ids: tuple[ArtifactId, ...]
consumed_future_suspension_evidence_ids: tuple[ArtifactId, ...]
completeness_evidence_id: ArtifactId
```

Export `EntryPathReasonCode` publicly.

- [ ] **Step 4: Run Entry contract tests**

Run: `.venv/bin/python -m pytest -q tests/strategies/entry/test_contracts.py`

Expected: PASS.

### Task 3: Replace the Materializer Input and Implement Temporal Completeness

**Files:**
- Modify: `src/market_regime_alpha/strategies/entry/materialization.py`
- Test: `tests/strategies/entry/test_materialization.py`

**Interfaces:**
- Consumes `entry_reference_evidence: tuple[RehearsalEntryReferenceEvidence, ...]` and exactly one `future_path_evidence_completeness: RehearsalFuturePathEvidenceCompleteness`.
- Produces an `EntryPathTargetMaterialization` with only consumed evidence IDs and the completeness evidence ID.

- [ ] **Step 1: Replace test fixtures and add red behavioral tests**

```python
def test_closed_session_before_readiness_is_not_yet_observed() -> None:
    result = _materialize(
        materialized_at=AsOfTime(_at_on(HORIZON_DATES[0], 15, 10)),
        completeness=_completeness(readiness_minutes=(30, 30, 30)),
    )
    assert result.observations[0].status is EntryPathObservationStatus.NOT_YET_OBSERVED
    assert result.observations[0].reason_code is EntryPathReasonCode.EVIDENCE_NOT_YET_AVAILABLE


def test_covered_missing_bar_is_known_at_completeness_availability() -> None:
    completeness = _completeness(available_at=AvailabilityTime(_at_on(HORIZON_DATES[0], 15, 31)))
    observation = _materialize(completeness=completeness).observations[0]
    assert observation.status is EntryPathObservationStatus.MISSING
    assert observation.observed_at == completeness.available_at
```

Add tests for: reference basis mismatch; all bases equal; duplicate/missing/outside/wrong-time
reference; future source mismatch; completeness availability after as-of; watermark shortfall;
exact Population coverage mismatch; every readiness validation rule; all prescribed identity
changes; and old barrier/open/dual-touch/suspension/timeout outcomes using the new fixtures.

- [ ] **Step 2: Run materializer tests to verify red**

Run: `.venv/bin/python -m pytest -q tests/strategies/entry/test_materialization.py`

Expected: FAIL because the old public signature accepts snapshots and classifies a post-close gap
as missing.

- [ ] **Step 3: Implement explicit evidence indexing and decision order**

```python
def materialize_entry_path_target(
    *,
    contract: EntryPathTargetContract,
    population: CandidatePopulation,
    source_dataset_ids: tuple[DatasetId, ...],
    trading_calendar: TradingCalendarArtifact,
    entry_reference_evidence: tuple[RehearsalEntryReferenceEvidence, ...],
    future_daily_bars: tuple[RehearsalFutureDailyBar, ...],
    future_suspensions: tuple[RehearsalFutureSuspensionEvidence, ...],
    future_path_evidence_completeness: RehearsalFuturePathEvidenceCompleteness,
    materialized_at: AsOfTime,
    code_revision: str,
    config_hash: str,
) -> EntryPathTargetMaterialization:
```

Resolve exact horizon first. Validate and index the full reference tuple before per-symbol work:
its symbols must exactly equal the Population, every Decision Time must match, every reference
must be decision-available, its source must be in `source_dataset_ids`, and its basis must equal
the Target basis. Validate completeness source and availability; require its sorted covered symbols
to equal Population, exact one readiness per horizon date, each deadline at/after Calendar close,
and no outer dates. Require every future bar/suspension source Dataset to equal completeness source
and be declared. Reject a bar basis different from Target or its same-symbol reference.

For an unresolved session, evaluate this exact branch order:

```python
if materialized_at.value < session_close:
    return _not_yet(..., EntryPathReasonCode.HORIZON_NOT_COMPLETE)
if materialized_at.value < readiness.evidence_ready_at.value:
    return _not_yet(..., EntryPathReasonCode.EVIDENCE_NOT_YET_AVAILABLE)
if completeness.available_at.value > materialized_at.value or coverage_before_session:
    return _not_yet(..., EntryPathReasonCode.EVIDENCE_COVERAGE_NOT_COMPLETE)
if bar is None and not (suspension and suspension.is_suspended):
    return _missing(..., observed_at=completeness.available_at)
```

Only append actually consumed bar/suspension IDs. Keep current `_classify_bar()` ordering and the
terminal ambiguity behavior unchanged. Canonicalize inputs by symbol/session, add evidence IDs and
complete result audit values to `_artifact_id()`, and return the same IDs in the materialization
contract.

- [ ] **Step 4: Run focused Entry and Data suites**

Run: `.venv/bin/python -m pytest -q tests/strategies/entry tests/data/test_path_evidence.py tests/data/test_trading_calendar.py`

Expected: PASS with all legacy WP-4A barrier-classification cases preserved and WP-4A.1 cases added.

### Task 4: Record the Normative WP-4A.1 Status and Commit Domain Logic

**Files:**
- Modify: `docs/specs/Entry-Path-Target-V1.md`
- Modify: `docs/research/R5-Current-Status.md`
- Modify: files from Tasks 1–3

**Interfaces:**
- Documents that path completeness is identified evidence, not session-close inference.
- Records that no Entry Gate, model, accuracy, Alpha, or real Xuntou run exists.

- [ ] **Step 1: Update the normative specification and current status**

Add the new reference-evidence schema, exact Population coverage, per-session readiness order,
completeness availability time used by `MISSING`, source-lineage/evidence-ID fields, reason enum,
lower barrier bound, Target-versus-Artifact identity decision, and the remaining provider-backed
WP-3 blocker. Remove the legacy claim that a missing snapshot creates an `INVALID` target row.

- [ ] **Step 2: Run domain checks before commit**

Run: `.venv/bin/python -m pytest -q tests/strategies/entry tests/data/test_path_evidence.py tests/data/test_trading_calendar.py && .venv/bin/python -m ruff check src/market_regime_alpha/data/path_evidence.py src/market_regime_alpha/data/__init__.py src/market_regime_alpha/strategies/entry tests/data/test_path_evidence.py tests/strategies/entry && .venv/bin/python -m mypy src/market_regime_alpha/data src/market_regime_alpha/strategies/entry`

Expected: PASS.

- [ ] **Step 3: Commit only WP-4A.1 domain work**

```bash
git add src/market_regime_alpha/data/path_evidence.py src/market_regime_alpha/data/__init__.py src/market_regime_alpha/strategies/entry tests/data/test_path_evidence.py tests/strategies/entry docs/specs/Entry-Path-Target-V1.md docs/research/R5-Current-Status.md
git commit -m "feat: harden Entry path evidence contracts"
```

### Task 5: Add Independent GitHub Actions CI

**Files:**
- Create: `.github/workflows/ci.yml`

**Interfaces:**
- Runs repository quality commands under Python 3.12 on pushes and pull requests.

- [ ] **Step 1: Add the workflow**

```yaml
name: CI

on:
  push:
  pull_request:

jobs:
  quality:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: python -m pip install --upgrade pip
      - run: python -m pip install -e ".[dev]"
      - run: python -m pytest -q
      - run: python -m ruff check .
      - run: python -m mypy
```

- [ ] **Step 2: Validate syntax and commit CI separately**

Run: `.venv/bin/python -c "from pathlib import Path; assert 'python-version: \"3.12\"' in Path('.github/workflows/ci.yml').read_text()" && git diff --check`

Expected: PASS.

```bash
git add .github/workflows/ci.yml
git commit -m "ci: validate Python quality checks"
```

### Task 6: Full Verification and Drift Review

**Files:**
- Inspect: all modified files and GitHub Actions workflow

**Interfaces:**
- Reports exactly executed local checks and any unexecuted remote workflow result.

- [ ] **Step 1: Run repository quality suite**

Run: `.venv/bin/python -m pytest -q && .venv/bin/python -m ruff check . && .venv/bin/python -m mypy`

Expected: PASS; report actual counts and warnings rather than a blanket claim.

- [ ] **Step 2: Perform Constitution and scope review**

Verify the diff introduces no Candidate, Provider Artifact, B0/B1, Entry policy, Position,
Portfolio, or Execution ownership; does not infer source/basis/coverage; preserves fixed horizon and
daily-bar ambiguity; and does not call REHEARSAL evidence Alpha.

- [ ] **Step 3: Inspect CI workflow status**

If the commits are not pushed, report workflow status as not triggered rather than claiming it
passed. Do not push without explicit authorization.
