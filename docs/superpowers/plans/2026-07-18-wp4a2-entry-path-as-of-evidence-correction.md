# WP-4A.2 Entry Path As-Of Evidence Correction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Correct Entry Path as-of evidence semantics by separating readiness policy from coverage assertion and recording only evidence actually consumed by a materialization.

**Architecture:** Data owns a stable readiness policy and optional observed coverage assertion. Entry validates both at the boundary, consumes direct finalized evidence before absence semantics, and records explicit observation/materialization schema versions plus consumed identities. Target truth semantics stay at v1.

**Tech Stack:** Python 3.12, frozen dataclasses, Enum, pytest, Ruff, mypy, GitHub Actions.

## Global Constraints

- Do not implement WP-5, an Entry Gate/Proposal/model, Candidate changes, WP-3 runner changes, ProviderRehearsalMarketArtifact expansion, Portfolio, or Execution.
- `ENTRY_PATH_TARGET_SCHEMA_VERSION` remains `entry-path-target-v1`.
- Remove `INVALID` and `ENTRY_REFERENCE_MISSING`; V1 states are AVAILABLE, AMBIGUOUS, MISSING, NOT_YET_OBSERVED only.
- Use `entry-path-observation-v2` and `entry-path-materialization-v2` in explicit payload fields.
- All future bar, suspension, coverage, and readiness-effective inputs fail closed; only `coverage_assertion=None` represents unavailable coverage.
- Readiness policy, present coverage assertion, bars, and suspensions use one Dataset ID; reference may be a separately declared Dataset.
- Keep semantic changes, pure formatting, and CI-only workflow updates in separate commits.

---

### Task 1: Replace mixed completeness with Data contracts

**Files:**
- Modify: `src/market_regime_alpha/data/path_evidence.py`
- Modify: `src/market_regime_alpha/data/__init__.py`
- Test: `tests/data/test_path_evidence.py`

**Interfaces:**

```python
class RehearsalFuturePathReadinessPolicy:
    source_dataset_id: DatasetId
    policy_convention: str
    effective_at: AvailabilityTime
    session_readiness: tuple[RehearsalFuturePathSessionReadiness, ...]
    policy_id: ArtifactId

class RehearsalFuturePathCoverageAssertion:
    source_dataset_id: DatasetId
    available_at: AvailabilityTime
    coverage_convention: str
    covered_symbols: tuple[str, ...]
    coverage_through_session_date: date
    evidence_id: ArtifactId
```

- [ ] **Step 1: Write red Data tests**

```python
def test_readiness_policy_and_coverage_assertion_have_distinct_ids() -> None:
    assert readiness.policy_id != replace(readiness, policy_convention="POLICY_V2").policy_id
    assert coverage.evidence_id != replace(coverage, coverage_convention="COVERAGE_V2").evidence_id
```

- [ ] **Step 2: Run red test**

Run: `.venv/bin/python -m pytest -q tests/data/test_path_evidence.py`

Expected: FAIL because policy/assertion classes do not exist.

- [ ] **Step 3: Implement contracts**

Delete `RehearsalFuturePathEvidenceCompleteness`. Make policy contain only stable readiness information and assertion contain only observed coverage. Contract-local validation enforces non-empty conventions, Dataset IDs, sorted unique symbols, and deterministic canonical IDs; Calendar-dependent checks remain in materialization.

- [ ] **Step 4: Verify Data slice**

Run: `.venv/bin/python -m pytest -q tests/data/test_path_evidence.py && .venv/bin/python -m ruff check src/market_regime_alpha/data tests/data/test_path_evidence.py`

Expected: PASS.

### Task 2: Version Observation and remove unreachable invalid state

**Files:**
- Modify: `src/market_regime_alpha/strategies/entry/contracts.py`
- Modify: `src/market_regime_alpha/strategies/entry/__init__.py`
- Test: `tests/strategies/entry/test_contracts.py`

**Interfaces:**

```python
ENTRY_PATH_OBSERVATION_SCHEMA_VERSION = "entry-path-observation-v2"

class EntryPathObservationStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    AMBIGUOUS = "AMBIGUOUS"
    MISSING = "MISSING"
    NOT_YET_OBSERVED = "NOT_YET_OBSERVED"
```

`EntryPathObservation` gains `schema_version`; `EntryPathTargetMaterialization` gains
`readiness_policy_id` and `consumed_coverage_assertion_id: ArtifactId | None`.

- [ ] **Step 1: Write red schema tests**

```python
def test_observation_requires_explicit_v2_schema() -> None:
    assert _observation().schema_version == ENTRY_PATH_OBSERVATION_SCHEMA_VERSION
    with pytest.raises(ValueError, match="schema_version"):
        _observation(schema_version="entry-path-observation-v1")
```

- [ ] **Step 2: Run red test**

Run: `.venv/bin/python -m pytest -q tests/strategies/entry/test_contracts.py`

Expected: FAIL because Observation has no schema version and invalid state remains public.

- [ ] **Step 3: Implement schema cleanup**

Remove invalid enum/reason/validation paths and their tests. Require only four status matrices. Include observation schema version and new materialization IDs in validation and public exports.

- [ ] **Step 4: Verify contract slice**

Run: `.venv/bin/python -m pytest -q tests/strategies/entry/test_contracts.py`

Expected: PASS.

### Task 3: Rebuild materializer as-of order and consumed identity

**Files:**
- Modify: `src/market_regime_alpha/strategies/entry/materialization.py`
- Test: `tests/strategies/entry/test_materialization.py`

**Interfaces:**

```python
def materialize_entry_path_target(
    *,
    future_path_readiness_policy: RehearsalFuturePathReadinessPolicy,
    future_path_coverage_assertion: RehearsalFuturePathCoverageAssertion | None,
    ...,
) -> EntryPathTargetMaterialization: ...
```

- [ ] **Step 1: Write red behavioral tests**

```python
def test_bar_precedes_readiness_and_coverage() -> None:
    observation = _materialize(
        bars=(_bar(HORIZON_DATES[0], high=10.3),),
        materialized_at=AsOfTime(_at(HORIZON_DATES[0], 15, 10)),
        readiness_policy=_policy(deadline_minute=30),
        coverage_assertion=None,
    ).observations[0]
    assert observation.outcome is EntryPathOutcome.UP_FIRST

def test_none_coverage_after_readiness_is_coverage_pending() -> None:
    assert _materialize(coverage_assertion=None).observations[0].reason_code is EntryPathReasonCode.EVIDENCE_COVERAGE_NOT_COMPLETE
```

Add red tests for future input errors, coverage watermark off-Calendar/early availability, coverage consumed only by absence, policy identity changes, canonical ID ordering, exact reference cardinality, and old barrier classification.

- [ ] **Step 2: Run red materializer tests**

Run: `.venv/bin/python -m pytest -q tests/strategies/entry/test_materialization.py`

Expected: FAIL because the V1 mixed completeness signature and ordering remain.

- [ ] **Step 3: Implement minimal materializer**

Index and validate all direct evidence first; reject future values. Validate policy against the exact horizon and coverage assertion against full Calendar before evaluation. For each session, perform close, bar, suspension, readiness, coverage-none/watermark, then missing branches. Only mark coverage consumed on the coverage branch with an assertion. Hash policy always, optional consumed coverage only, explicit observation schema and `entry-path-materialization-v2`.

- [ ] **Step 4: Verify focused suites**

Run: `.venv/bin/python -m pytest -q tests/strategies/entry tests/data/test_path_evidence.py tests/data/test_trading_calendar.py && .venv/bin/python -m mypy src/market_regime_alpha/data src/market_regime_alpha/strategies/entry`

Expected: PASS.

### Task 4: Document and commit semantic correction

**Files:**
- Modify: `docs/specs/Entry-Path-Target-V1.md`
- Modify: `docs/research/R5-Current-Status.md`
- Modify: files from Tasks 1–3

- [ ] **Step 1: Record contracts and limits**

Document policy/assertion separation, optional unavailable coverage, direct-evidence precedence, four-state schema, observation/materialization v2, consumed coverage identity, and no CI VERIFIED claim.

- [ ] **Step 2: Commit semantics only**

```bash
git add src/market_regime_alpha/data src/market_regime_alpha/strategies/entry tests/data/test_path_evidence.py tests/strategies/entry docs/specs/Entry-Path-Target-V1.md docs/research/R5-Current-Status.md
git commit -m "fix: correct Entry path as-of evidence"
```

### Task 5: Pure formatting and CI-only changes

**Files:**
- Modify: `src/market_regime_alpha/strategies/entry/materialization.py`
- Modify: `.github/workflows/ci.yml`

- [ ] **Step 1: Format only materialization**

Reflow function signatures, calls, returns, and payload literals without changing behavior. Verify with focused tests, then commit `style: reformat Entry path materialization`.

- [ ] **Step 2: Add CI manual trigger**

```yaml
on:
  push:
  pull_request:
  workflow_dispatch:
```

Verify YAML text and commit only the workflow as `ci: enable manual workflow dispatch`.

### Task 6: Full verification and remote CI audit

- [ ] **Step 1: Run quality suite**

Run: `.venv/bin/python -m pytest -q && .venv/bin/python -m ruff check . && .venv/bin/python -m mypy`

- [ ] **Step 2: Query remote CI**

Run: `gh workflow list`, `gh run list --workflow CI --limit 10`, and `gh run view --log-failed` for a run when available. If CLI authentication remains unavailable, report only `CI workflow implemented; remote CI result not verified`.
