# WP-4A Entry Path Target Contracts and Materialization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build deterministic `UP_FIRST / DOWN_FIRST / TIMEOUT` Entry research Targets from explicit 14:55 reference prices, exchange-session calendars, and rehearsal future daily evidence while preserving ambiguity and missingness.

**Architecture:** Data owns future OHLC/suspension evidence, Trading Calendar owns multi-session resolution, and `strategies.entry` owns categorical Target semantics and pure materialization. Repository quality baseline repairs are committed before WP-4A feature changes and remain independent of Entry behavior.

**Tech Stack:** Python 3.12+, frozen slotted dataclasses, enums, SHA-256 canonical JSON identities, semantic time wrappers, pytest, Ruff, mypy.

## Global Constraints

- Target start is exactly `NEXT_TRADING_SESSION_OPEN_AFTER_DECISION_V1`.
- Reference price is the 14:55 Asia/Shanghai Decision Snapshot; V1 excludes the final five minutes of the Decision Date.
- Daily ordering is exactly `DAILY_OHLC_OPEN_THEN_UNORDERED_EXTREMES_V1`.
- `available_at >= finalized_at >= TradingSession.session_close`; Target `observed_at` uses evidence `available_at`.
- Exchange trading sessions come only from `TradingCalendarArtifact`; no weekday or natural-day inference.
- Same-bar high/low dual touch is terminal `AMBIGUOUS`, never resolved by later sessions.
- A missing future bar without explicit confirmed suspension evidence is `MISSING`, never inferred suspension.
- Target ID includes all Target semantics; artifact ID includes all source, Calendar, Population, code/config, and observation evidence.
- Do not modify Candidate contracts, B0/B1, WP-3 runner, Provider Artifact schema, or provider authority.
- Do not add Entry Gate, Entry Proposal, model, Portfolio, Execution, or buy-point accuracy claims.
- WP-3 remains pending real Xuntou input.

---

## File Structure

- Create `tests/data/__init__.py`, `tests/features/__init__.py`, `tests/universe/__init__.py`: unique pytest package identities.
- Modify `tests/research/test_provider_rehearsal_market_artifact.py`: remove existing unused import.
- Modify four existing source modules with typing-only variable-name/annotation repairs.
- Modify `src/market_regime_alpha/data/trading_calendar.py`: multi-session resolver.
- Create `src/market_regime_alpha/data/path_evidence.py`: future OHLC and suspension evidence.
- Modify `src/market_regime_alpha/data/__init__.py`: intended Data exports.
- Create `src/market_regime_alpha/strategies/entry/contracts.py`: Entry categorical Target contracts.
- Create `src/market_regime_alpha/strategies/entry/materialization.py`: pure path evaluator and artifact identity.
- Create `src/market_regime_alpha/strategies/entry/__init__.py` and `src/market_regime_alpha/strategies/__init__.py`: intended public boundary.
- Create `tests/strategies/entry/test_contracts.py` and `tests/strategies/entry/test_materialization.py`.
- Create `docs/specs/Entry-Path-Target-V1.md`; update current research status.

---

### Task 1: Restore Full Pytest Collection and Ruff Baseline

**Files:**
- Create: `tests/data/__init__.py`
- Create: `tests/features/__init__.py`
- Create: `tests/universe/__init__.py`
- Modify: `tests/research/test_provider_rehearsal_market_artifact.py:3`

**Interfaces:**
- Consumes: current pytest default import mode and Ruff configuration.
- Produces: unique module names `data.test_contracts`, `features.test_contracts`, and `universe.test_contracts`; no runtime application change.

- [ ] **Step 1: Reproduce the two existing quality failures**

Run:

```bash
python3 -m pytest -q
python3 -m ruff check .
```

Expected before repair: pytest reports two import-file-mismatch collection errors and Ruff reports the unused `timedelta` import.

- [ ] **Step 2: Add explicit test package markers and remove the unused import**

Each package marker contains only:

```python
"""Tests for the owning bounded context."""
```

Change the existing import to:

```python
from datetime import date, datetime
```

- [ ] **Step 3: Verify the repaired pytest and Ruff baselines**

```bash
python3 -m pytest -q
python3 -m ruff check .
```

Expected: full pytest and full Ruff pass.

- [ ] **Step 4: Commit quality repair separately**

```bash
git add tests/data/__init__.py tests/features/__init__.py tests/universe/__init__.py tests/research/test_provider_rehearsal_market_artifact.py
git commit -m "chore: fix repository test collection and Ruff baseline"
```

---

### Task 2: Close the Current Six Mypy Errors

**Files:**
- Modify: `src/market_regime_alpha/universe/eligibility_policy.py`
- Modify: `src/market_regime_alpha/candidates/rehearsal_targets.py`
- Modify: `src/market_regime_alpha/candidates/rehearsal_opportunity_targets.py`
- Modify: `src/market_regime_alpha/research/provider_rehearsal_market_artifact.py`

**Interfaces:**
- Consumes: existing runtime contracts unchanged.
- Produces: identical runtime behavior with unambiguous local variable types.

- [ ] **Step 1: Reproduce the six errors**

```bash
python3 -m mypy
```

Expected before repair: six errors in the four files above.

- [ ] **Step 2: Separate heterogeneous loop variable names**

In `eligibility_policy.py`, replace reused `value` locals with typed names:

```python
for label, boolean_value in (
    ("is_suspended", self.is_suspended),
    ("is_st", self.is_st),
):
    if boolean_value is not None and not isinstance(boolean_value, bool):
        raise TypeError(f"{label} must be boolean or None")

for label, numeric_value in (
    ("prev_close", self.prev_close),
    ("limit_up_price", self.limit_up_price),
    ("limit_down_price", self.limit_down_price),
    ("liquidity_value", self.liquidity_value),
):
    if isinstance(numeric_value, bool):
        raise TypeError(f"{label} must not be boolean")
```

Use `text_value` for policy strings and `boolean_value` for policy booleans. Before the eligibility branch, declare:

```python
status: TradingEligibilityStatus
reasons: tuple[str, ...]
```

- [ ] **Step 3: Rename optional lookup and heterogeneous bar locals**

Use `resolved_snapshot` for `.get(...)` results in both Candidate Target materializers. In the provider artifact validation loops, use `daily_bar` and `next_session_bar` rather than reusing `bar` for different dataclass types.

- [ ] **Step 4: Verify full mypy and affected tests**

```bash
python3 -m mypy
python3 -m pytest -q tests/universe tests/candidates tests/research/test_provider_rehearsal_market_artifact.py
```

Expected: full mypy passes and affected tests pass.

- [ ] **Step 5: Commit typing repairs separately**

```bash
git add src/market_regime_alpha/universe/eligibility_policy.py src/market_regime_alpha/candidates/rehearsal_targets.py src/market_regime_alpha/candidates/rehearsal_opportunity_targets.py src/market_regime_alpha/research/provider_rehearsal_market_artifact.py
git commit -m "fix: close current mypy errors"
```

---

### Task 3: Calendar Horizon Resolver and Future Path Evidence

**Files:**
- Modify: `tests/data/test_trading_calendar.py`
- Create: `tests/data/test_path_evidence.py`
- Modify: `src/market_regime_alpha/data/trading_calendar.py`
- Create: `src/market_regime_alpha/data/path_evidence.py`
- Modify: `src/market_regime_alpha/data/__init__.py`
- Modify: `pyproject.toml`

**Interfaces:**
- Produces: `TradingCalendarArtifact.resolve_following_session_dates(decision_time, count)`, `RehearsalFutureDailyBar`, and `RehearsalFutureSuspensionEvidence`.
- Consumed by: Tasks 4 and 5.

- [ ] **Step 1: Write failing Calendar resolver tests**

Assert explicit-session behavior:

```python
assert calendar.resolve_following_session_dates(decision_time, 2) == (
    date(2026, 7, 20),
    date(2026, 7, 21),
)
assert calendar.resolve_next_session_date(decision_time) == date(2026, 7, 20)
```

Assert `TypeError` for `True` and non-integer counts, `ValueError` for zero/negative counts, and `LookupError` when fewer than `count` later sessions exist.

- [ ] **Step 2: Run Calendar tests and confirm red**

```bash
python3 -m pytest -q tests/data/test_trading_calendar.py
```

Expected: failure because the multi-session resolver does not exist.

- [ ] **Step 3: Implement one-owner Calendar resolution**

Add:

```python
def resolve_following_session_dates(
    self,
    decision_time: DecisionTime,
    count: int,
) -> tuple[date, ...]:
    if isinstance(count, bool) or not isinstance(count, int):
        raise TypeError("count must be an integer")
    if count <= 0:
        raise ValueError("count must be positive")
    local_date = decision_time.value.astimezone(ZoneInfo(self.timezone_name)).date()
    following = tuple(
        session.trade_date for session in self.sessions if session.trade_date > local_date
    )
    if len(following) < count:
        raise LookupError("insufficient later trading sessions in identified calendar artifact")
    return following[:count]
```

Make `resolve_next_session_date()` return `self.resolve_following_session_dates(decision_time, 1)[0]`.

- [ ] **Step 4: Write failing future evidence contract tests**

Cover valid evidence plus rejection of non-positive/non-finite OHLC, invalid OHLC ordering, non-string/empty basis, and `available_at < finalized_at`:

```python
bar = RehearsalFutureDailyBar(
    symbol="000001.SZ",
    session_date=date(2026, 7, 20),
    open=10.0,
    high=10.4,
    low=9.8,
    close=10.2,
    price_adjustment_basis="RAW_UNADJUSTED_TRADABLE_PRICE_V1",
    available_at=AvailabilityTime(datetime(2026, 7, 20, 15, 5, tzinfo=TZ)),
    finalized_at=FinalizationTime(datetime(2026, 7, 20, 15, 1, tzinfo=TZ)),
)
assert bar.available_at.value >= bar.finalized_at.value
```

- [ ] **Step 5: Implement Data evidence and public exports**

Create frozen slotted dataclasses with exact fields from the design. Reuse local symbol, finite-price, and non-empty-text validators. Suspension evidence requires a real boolean `is_suspended` and the same availability/finality ordering.

Add `src/market_regime_alpha/data/path_evidence.py` to mypy files and export both contracts from `data/__init__.py`.

- [ ] **Step 6: Verify and commit Data/Calendar increment**

```bash
python3 -m pytest -q tests/data/test_trading_calendar.py tests/data/test_path_evidence.py
python3 -m ruff check src/market_regime_alpha/data tests/data
python3 -m mypy
git add src/market_regime_alpha/data/trading_calendar.py src/market_regime_alpha/data/path_evidence.py src/market_regime_alpha/data/__init__.py tests/data/test_trading_calendar.py tests/data/test_path_evidence.py pyproject.toml
git commit -m "feat: add future path evidence and calendar horizon resolver"
```

Expected: focused tests, full mypy, and scoped Ruff pass before commit.

---

### Task 4: Entry Path Target Contracts and Identity

**Files:**
- Create: `src/market_regime_alpha/strategies/__init__.py`
- Create: `src/market_regime_alpha/strategies/entry/__init__.py`
- Create: `src/market_regime_alpha/strategies/entry/contracts.py`
- Create: `tests/strategies/__init__.py`
- Create: `tests/strategies/entry/__init__.py`
- Create: `tests/strategies/entry/test_contracts.py`
- Modify: `pyproject.toml`

**Interfaces:**
- Produces: `EntryPathOutcome`, `EntryPathObservationStatus`, `EntryPathTriggerType`, `EntryBarrierSpec`, `EntryPathTargetContract`, `EntryPathObservation`, `EntryPathTargetMaterialization`, `build_entry_path_target_contract(...)`.
- Consumed by: Task 5 pure materializer.

- [ ] **Step 1: Write failing Target identity and state-matrix tests**

Build two identical specs in different calls and assert equal Target IDs. Change each semantic field independently and assert a different Target ID. Assert exact outcomes/statuses and fixed conventions.

For observations, assert these valid shapes and reject every cross-state mismatch:

```text
AVAILABLE        -> outcome present, observed_at present
AMBIGUOUS        -> outcome None, dual-touch trigger, observed_at present
MISSING          -> outcome None, first_missing_session_date present, observed_at present
INVALID          -> outcome None, reference/upper/lower may be None, observed_at present
NOT_YET_OBSERVED -> outcome None, observed_at None
```

- [ ] **Step 2: Run contract tests and confirm red**

```bash
python3 -m pytest -q tests/strategies/entry/test_contracts.py
```

Expected: collection failure because the Entry package does not exist.

- [ ] **Step 3: Implement fixed enums and barrier specification**

Use exact enum values:

```python
class EntryPathOutcome(str, Enum):
    UP_FIRST = "UP_FIRST"
    DOWN_FIRST = "DOWN_FIRST"
    TIMEOUT = "TIMEOUT"

class EntryPathObservationStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    AMBIGUOUS = "AMBIGUOUS"
    MISSING = "MISSING"
    INVALID = "INVALID"
    NOT_YET_OBSERVED = "NOT_YET_OBSERVED"
```

Trigger values are `OPEN_GAP_UP`, `OPEN_GAP_DOWN`, `INTRADAY_HIGH_ONLY`, `INTRADAY_LOW_ONLY`, `INTRADAY_DUAL_TOUCH_UNORDERED`, and `HORIZON_EXHAUSTED`.

`EntryBarrierSpec` contains upper/lower return, horizon, three fixed convention strings, explicit price adjustment basis, and schema version. Validate finite non-boolean returns with `lower < 0 < upper`, a positive non-boolean integer horizon, and non-empty strings.

- [ ] **Step 4: Implement deterministic Target contract**

Canonicalize all spec fields with sorted-key compact JSON, hash with SHA-256, and produce:

```python
TargetId(f"target-entry-path-{digest[:24]}")
```

The returned contract retains the complete exact spec and a descriptive name; no default barrier builder is added.

- [ ] **Step 5: Implement observation/materialization validation**

Validate the exact state matrix, one-based event index, unique/chronological evaluated dates, event date/index pairing, missing-date rules, reason code, and optional reference/barrier prices. Materialization validates unique source IDs, Target ID, unique/sorted observation symbols, non-empty code/config, and semantic times.

- [ ] **Step 6: Export APIs, add mypy scope, verify, and commit**

```bash
python3 -m pytest -q tests/strategies/entry/test_contracts.py
python3 -m ruff check src/market_regime_alpha/strategies tests/strategies/entry/test_contracts.py
python3 -m mypy
git add src/market_regime_alpha/strategies tests/strategies pyproject.toml
git commit -m "feat: add Entry path Target contracts"
```

Expected: focused tests, scoped Ruff, and full mypy pass.

---

### Task 5: Pure Entry Path Materializer

**Files:**
- Create: `src/market_regime_alpha/strategies/entry/materialization.py`
- Create: `tests/strategies/entry/test_materialization.py`
- Modify: `src/market_regime_alpha/strategies/entry/__init__.py`
- Modify: `pyproject.toml`

**Interfaces:**
- Consumes: Task 3 Data/Calendar contracts, Task 4 Entry contracts, existing `CandidatePopulation` and `RehearsalDecisionSnapshot`.
- Produces: `materialize_entry_path_target(...) -> EntryPathTargetMaterialization`.

- [ ] **Step 1: Write failing outcome-path tests**

Use a three-session Calendar, 14:55 reference price `10.0`, upper return `0.02`, lower return `-0.02`, and raw adjustment basis. Assert:

- open `10.3` -> `UP_FIRST / OPEN_GAP_UP`;
- open `9.7` -> `DOWN_FIRST / OPEN_GAP_DOWN`;
- open inside, high `10.2`, low above `9.8` -> `UP_FIRST / INTRADAY_HIGH_ONLY`;
- open inside, low `9.8`, high below `10.2` -> `DOWN_FIRST / INTRADAY_LOW_ONLY`;
- high `10.2` and low `9.8` -> terminal `AMBIGUOUS` even if a later bar is one-sided;
- three complete untouched sessions -> `TIMEOUT / HORIZON_EXHAUSTED`.

- [ ] **Step 2: Write failing missing/pending tests**

Assert missing first session prevents using a later event, missing after an earlier event is irrelevant, a future unresolved session before close is `NOT_YET_OBSERVED`, missing Snapshot is `INVALID`, confirmed suspension counts as evaluated/no-touch, and missing bar without suspension is `MISSING`.

- [ ] **Step 3: Write failing structural-error and identity tests**

Assert whole-call failure for duplicate Snapshot/bar/suspension, wrong Decision Time, off-Calendar and outside-horizon evidence, future-available input, finalization before session close, bar plus confirmed suspension on one key, adjustment mismatch, duplicate source IDs, and insufficient Calendar coverage.

Assert empty Population returns zero observations. Assert input-order normalization yields the same artifact ID, while changed Target/source/Calendar/Population/code/config/observation changes it.

- [ ] **Step 4: Implement structural preflight**

Use this exact public signature:

```python
def materialize_entry_path_target(
    *,
    contract: EntryPathTargetContract,
    population: CandidatePopulation,
    source_dataset_ids: tuple[DatasetId, ...],
    trading_calendar: TradingCalendarArtifact,
    decision_snapshots: tuple[RehearsalDecisionSnapshot, ...],
    future_daily_bars: tuple[RehearsalFutureDailyBar, ...],
    future_suspensions: tuple[RehearsalFutureSuspensionEvidence, ...],
    materialized_at: AsOfTime,
    code_revision: str,
    config_hash: str,
) -> EntryPathTargetMaterialization:
```

Resolve the exact horizon before per-symbol evaluation. Normalize and validate evidence keys, Calendar membership, horizon scope, finalization/availability, source IDs, Decision Time, and adjustment basis before producing any observation.

- [ ] **Step 5: Implement per-symbol terminal evaluation**

For each sorted Population symbol, calculate reference and barriers, then process exact horizon dates. Return immediately on open gap, one-sided touch, dual-touch ambiguity, missing completed evidence, or pending session. Confirmed suspension appends the date to evaluated dates and continues. Timeout uses the final required evidence availability.

Use stable reason codes:

```text
OUTCOME_RESOLVED
DAILY_BAR_DUAL_TOUCH_ORDER_UNRESOLVED
FUTURE_DAILY_BAR_MISSING
DECISION_SNAPSHOT_MISSING
HORIZON_NOT_COMPLETE
HORIZON_EXHAUSTED_WITHOUT_BARRIER_TOUCH
```

- [ ] **Step 6: Implement deterministic artifact identity**

Canonical JSON includes Target ID, sorted source IDs, Calendar artifact, Universe, Decision Time, sorted Population, materialized time, code/config, and every serialized observation/audit field. Hash to:

```python
ArtifactId(f"entry-path-materialization-{digest[:24]}")
```

- [ ] **Step 7: Export, verify, and commit materializer**

```bash
python3 -m pytest -q tests/strategies/entry
python3 -m ruff check src/market_regime_alpha/strategies tests/strategies
python3 -m mypy
git add src/market_regime_alpha/strategies/entry/materialization.py src/market_regime_alpha/strategies/entry/__init__.py tests/strategies/entry/test_materialization.py pyproject.toml
git commit -m "feat: materialize Entry competing-event targets"
```

Expected: all Entry tests, scoped Ruff, and full mypy pass.

---

### Task 6: Normative Specification, Status, and Full Verification

**Files:**
- Create: `docs/specs/Entry-Path-Target-V1.md`
- Modify: `docs/research/R5-Current-Status.md`

**Interfaces:**
- Consumes: verified WP-4A behavior and exact command results.
- Produces: normative semantics and accurate current authority.

- [ ] **Step 1: Write the normative specification**

Record exact conventions, Data/Entry ownership, state matrix, daily ordering, suspension/missing rules, audit fields, availability/finality, Target/artifact identities, structural errors, and explicit non-claims from the approved design.

- [ ] **Step 2: Run focused and full verification**

```bash
python3 -m pytest -q tests/data/test_trading_calendar.py tests/data/test_path_evidence.py tests/strategies/entry
python3 -m pytest -q
python3 -m ruff check .
python3 -m mypy
```

Expected: focused tests and all three full repository quality commands pass.

- [ ] **Step 3: Update current status with exact results**

Record:

```text
WP-4A Entry Path contracts/materializer       IMPLEMENTED / VERIFIED
Target start                                  NEXT_TRADING_SESSION_OPEN_AFTER_DECISION_V1
Entry model                                   NOT IMPLEMENTED
Entry timing accuracy                         NOT VALIDATED
WP-3 real Xuntou run                          STILL PENDING INPUT
Trading execution                             OUT OF SCOPE
```

Do not mark WP-3 complete and do not claim buy-point accuracy.

- [ ] **Step 4: Review architecture and leakage manually**

Confirm Target values never enter Candidate scoring, the final Decision-Date five minutes are excluded, future evidence availability is enforced, dual-touch ambiguity is terminal, missing bars are not inferred suspension, retrieval time is unused, and no Provider/Portfolio/Execution schema changed.

- [ ] **Step 5: Commit docs and final status**

```bash
git add docs/specs/Entry-Path-Target-V1.md docs/research/R5-Current-Status.md
git commit -m "docs: record WP-4A Entry path target status"
```

- [ ] **Step 6: Confirm repository state**

```bash
git status --short
git log -10 --oneline
```

Expected: clean working tree, independent quality commits before WP-4A feature commits, and no push.
