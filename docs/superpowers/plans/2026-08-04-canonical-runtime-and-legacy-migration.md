# Canonical Runtime and Legacy Model Migration Implementation Plan

> **Status:** CURRENT_SPECIFICATION
> **Authority:** Task-level execution plan for the approved canonical runtime and Legacy migration infrastructure
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-04
> **Supersedes:** None
> **Superseded By:** None
> **Related Documents:** ../specs/2026-08-04-canonical-runtime-and-legacy-migration-design.md, ../../architecture/06-Legacy-Migration.md, ../../architecture/10-Production-Decision-Lifecycle.md, ../../architecture/11-Production-Lifecycle-Hardening-and-Shadow-Operations.md
> **Code Evidence:** Plan starts from `feat/canonical-runtime-and-legacy-migration@e7e0bdf` based on `origin/main@734c8b6f677f458e5048846fa28377b681b1fb65`.

> **For agentic workers:** REQUIRED SUB-SKILL: Use `executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a durable, recoverable canonical decision lifecycle over the existing domain services, strengthen H4.5 manual-intent safety, and establish an isolated, content-addressed Legacy model migration and differential-verification foundation.

**Architecture:** Add a lifecycle-specific SQLite Runtime Journal that references existing immutable Artifacts and domain objects without replacing the Daily Runtime Journal. Drive it through typed stage handlers and a canonical runner, retain H4.5 as the only reducing ManualTrade authority, and isolate all `dividend_t` calls beneath migration adapters. Domain-local model Protocols, a Decimal moving-average Feature Artifact and a policy-driven differential harness provide the first complete migration/replay slice.

**Tech Stack:** Python 3.12, frozen dataclasses, Enum and Protocol, `Decimal`, canonical JSON/SHA-256, SQLite migration 011, argparse module CLIs, pandas only inside the Legacy adapter, pytest, Ruff, mypy, setuptools build.

## Global Constraints

- Work only on `feat/canonical-runtime-and-legacy-migration`; preserve and never stage `.idea/modules.xml`.
- Preserve migrations 002–010 and all V1/V2/V3 Artifact, Reader, Repository and domain compatibility.
- The Daily Runtime Journal remains the only authority for Daily acquisition; the lifecycle journal only references verified inputs.
- `automatic_order_execution = false`.
- `broker_integration_proven = false`.
- `entry_model_empirically_validated = false`.
- `production_ready = false`.
- Never create a BrokerOrder, call QMT/PTrade/Broker code, synthesize a Fill or infer an observed Fill from ManualTrade.
- Do not change existing model parameters, score thresholds or evidence ceilings.
- Candidate, Signal, Forecast, Opportunity, Thesis, Portfolio, Risk, ManualTrade, Fill, Position, Holding and Exit remain distinct.
- New price, money and quantity fields use `Decimal` or integer shares; adapter-only compatibility with existing float contracts must be explicit.
- Canonical modules cannot import `market_regime_alpha.dividend_t`; only `migration.legacy` and narrowly tested compatibility facades may do so.
- Every mutation is idempotent or recoverable by deterministic object reload; completed stages and immutable receipts are never overwritten.
- Use red → complete green → focused regression for each behavior slice and make dependency-coherent commits.
- Report `WAIT`, `DATA_INSUFFICIENT`, blockers and failures honestly; never replace unavailable data with static success data.

## File and responsibility map

### Canonical lifecycle

- `src/market_regime_alpha/application/canonical_lifecycle/states.py`: run/stage enums and transition validation.
- `src/market_regime_alpha/application/canonical_lifecycle/contracts.py`: lifecycle IDs, references, records, attempts, receipts and events.
- `src/market_regime_alpha/application/canonical_lifecycle/commands.py`: content-addressed create/resume commands.
- `src/market_regime_alpha/application/canonical_lifecycle/input_manifest.py`: immutable lifecycle input manifest and Reader.
- `src/market_regime_alpha/application/canonical_lifecycle/repositories.py`: Runtime Journal Protocol and typed conflicts.
- `src/market_regime_alpha/application/canonical_lifecycle/sqlite_repository.py`: migration-011 adapter, transactions, history and recovery claims.
- `src/market_regime_alpha/application/canonical_lifecycle/runner.py`: stage orchestration only.
- `src/market_regime_alpha/application/canonical_lifecycle/replay.py`: pure-stage receipt replay and mutating-stage verification.
- `src/market_regime_alpha/application/canonical_lifecycle/stages/*.py`: adapters over existing Readers/services.
- `src/market_regime_alpha/application/canonical_lifecycle/migrations/*.sql`: additive journal schema.

### Model migration

- `src/market_regime_alpha/features/model_contracts.py`: FeatureComputer and FeatureArtifact.
- `src/market_regime_alpha/research/model_contracts.py`: ResearchModel result contract.
- `src/market_regime_alpha/signals/model_contracts.py`: SignalModel result contract.
- `src/market_regime_alpha/decision/model_contracts.py`: DecisionModel result contract.
- `src/market_regime_alpha/features/technical/moving_average.py`: Decimal simple-moving-average implementation.
- `src/market_regime_alpha/features/artifact.py`: Feature Artifact publisher, Reader and replay.
- `src/market_regime_alpha/migration/legacy/adapters/moving_average.py`: exact Legacy pandas call and normalization.
- `src/market_regime_alpha/migration/comparison/contracts.py`: comparison policy/report/domain classification.
- `src/market_regime_alpha/migration/comparison/harness.py`: deterministic dual execution and classification.
- `src/market_regime_alpha/migration/comparison/artifact.py`: immutable report publisher/Reader/replay.

### CLIs and compatibility

- `src/market_regime_alpha/cli/run_canonical_lifecycle.py`: structured lifecycle command/resume/replay CLI.
- `src/market_regime_alpha/cli/create_manual_trade_from_risk_decision.py`: stable H4.5 manual-only CLI.
- `scripts/confirm_risk_reduction.py`: compatibility delegation with unchanged accepted inputs.
- `src/market_regime_alpha/data_sources/storage_paths.py`: neutral storage default used by canonical data sources.
- `src/market_regime_alpha/research/tencent_composite_dividend_t.py`: compatibility facade only.

---

### Task 1: Repair the verified baseline and enforce the Legacy import boundary

**Files:**
- Modify: `tests/application/operational_research/test_sqlite_composite_repository.py`
- Create: `src/market_regime_alpha/data_sources/storage_paths.py`
- Modify: `src/market_regime_alpha/data_sources/tencent_minute_cache.py`
- Create: `src/market_regime_alpha/migration/__init__.py`
- Create: `src/market_regime_alpha/migration/legacy/__init__.py`
- Create: `src/market_regime_alpha/migration/legacy/adapters/__init__.py`
- Create: `src/market_regime_alpha/migration/legacy/adapters/tencent_dividend_t.py`
- Modify: `src/market_regime_alpha/research/tencent_composite_dividend_t.py`
- Create: `tests/architecture/test_legacy_import_boundary.py`
- Modify: `tests/research/test_tencent_composite_dividend_t.py`
- Modify: `tests/test_tencent_minute_cache.py`

**Interfaces:**
- Produces `DEFAULT_RESEARCH_DIR` from a neutral canonical module.
- Produces a compatibility facade whose implementation dependency points from `migration.legacy` to `dividend_t`.
- Produces an AST rule that rejects direct canonical imports of `market_regime_alpha.dividend_t`.

- [ ] **Step 1: Replace the non-portable tamper statement and prove the original assertion remains active.**

Use a deterministic scalar subquery instead of SQLite's optional `UPDATE ... LIMIT` extension:

```python
connection.execute(
    """
    UPDATE composite_operational_components
    SET content_hash = ?
    WHERE rowid = (
        SELECT rowid
        FROM composite_operational_components
        ORDER BY manifest_id, component_role, scope_key
        LIMIT 1
    )
    """,
    ("sha256:" + "0" * 64,),
)
```

- [ ] **Step 2: Run the focused baseline test.**

Run:

```bash
python -m pytest -q tests/application/operational_research/test_sqlite_composite_repository.py::test_repository_rejects_idempotency_conflict_and_projection_tamper
```

Expected: PASS, including the projection-tamper rejection.

- [ ] **Step 3: Write failing architecture and storage-boundary tests.**

The architecture test parses imports and treats only these roots as Legacy-compatible:

```python
ALLOWED_DIRECT_IMPORT_PREFIXES = (
    "market_regime_alpha.migration.legacy",
    "market_regime_alpha.legacy",
    "market_regime_alpha.dividend_t",
    "market_regime_alpha.web.dividend_t_app",
)
```

It must fail on `data_sources/tencent_minute_cache.py` and the existing Tencent bridge before the move.

- [ ] **Step 4: Move shared storage configuration and Legacy implementation.**

Define the neutral default without importing Legacy:

```python
DEFAULT_RESEARCH_DIR = Path("artifacts") / "research"
```

Move the existing Tencent/Dividend-T implementation unchanged under
`migration.legacy.adapters.tencent_dividend_t`; keep the historical research
module as explicit re-exports so existing callers and tests retain their API.

- [ ] **Step 5: Run boundary and compatibility tests.**

Run:

```bash
python -m pytest -q tests/architecture/test_legacy_import_boundary.py tests/research/test_tencent_composite_dividend_t.py tests/test_tencent_minute_cache.py
python -m ruff check src/market_regime_alpha/data_sources src/market_regime_alpha/migration src/market_regime_alpha/research/tencent_composite_dividend_t.py tests/architecture
```

Expected: all tests PASS; AST scan reports no unauthorized canonical import.

- [ ] **Step 6: Commit the boundary checkpoint.**

```bash
git add src/market_regime_alpha/data_sources src/market_regime_alpha/migration src/market_regime_alpha/research/tencent_composite_dividend_t.py tests/architecture tests/research/test_tencent_composite_dividend_t.py tests/test_tencent_minute_cache.py tests/application/operational_research/test_sqlite_composite_repository.py
git diff --cached --check
git commit -m "refactor: isolate legacy runtime dependencies"
```

### Task 2: Add role-specific model contracts

**Files:**
- Create: `src/market_regime_alpha/features/model_contracts.py`
- Create: `src/market_regime_alpha/research/model_contracts.py`
- Create: `src/market_regime_alpha/signals/model_contracts.py`
- Create: `src/market_regime_alpha/decision/model_contracts.py`
- Modify: `src/market_regime_alpha/features/__init__.py`
- Modify: `src/market_regime_alpha/signals/__init__.py`
- Create: `tests/features/test_model_contracts.py`
- Create: `tests/research/test_model_contracts.py`
- Create: `tests/signals/test_model_contracts.py`
- Create: `tests/decision/test_model_contracts.py`

**Interfaces:**

```python
class FeatureComputer(Protocol):
    feature_id: FeatureDefinitionId
    model_version: str
    def compute(self, request: FeatureComputationRequest) -> FeatureArtifact: ...

class ResearchModel(Protocol):
    model_id: ModelId
    model_version: str
    def run(self, request: ResearchModelRequest) -> ResearchModelResult: ...

class SignalModel(Protocol):
    model_id: ModelId
    model_version: str
    def run(self, request: SignalModelRequest) -> SignalModelResult: ...

class DecisionModel(Protocol):
    model_id: ModelId
    model_version: str
    def decide(self, request: DecisionModelRequest) -> DecisionModelResult: ...
```

- [ ] **Step 1: Write failing tests for independent structural Protocols.**

Use one stub per role and assert `isinstance(stub, FeatureComputer)` only for
the matching runtime-checkable Protocol. Assert there is no shared `Model`
base symbol.

- [ ] **Step 2: Add immutable request/result metadata and exact validation.**

Every role result includes:

```python
model_id: ModelId
model_version: str
configuration_id: ArtifactId
configuration_hash: str
input_artifact_ids: tuple[ArtifactId, ...]
input_hashes: tuple[str, ...]
state: str
score: Decimal | None
reason_codes: tuple[str, ...]
limitations: tuple[str, ...]
validation_status: str
```

Validate aligned/sorted/unique input references, SHA-256 values, explicit
timezone-aware as-of values, sorted unique reason codes and limitations, and
finite Decimal scores.

- [ ] **Step 3: Constrain Signal and Decision semantics.**

Define exact enums:

```python
class SignalMeaning(str, Enum):
    ENTRY_CONFIRMATION = "ENTRY_CONFIRMATION"
    TREND_CONTINUATION = "TREND_CONTINUATION"
    REVERSAL_WARNING = "REVERSAL_WARNING"
    SELL_PRESSURE = "SELL_PRESSURE"
    OVERHEAT = "OVERHEAT"
    VOLUME_CONFIRMATION = "VOLUME_CONFIRMATION"

class DecisionOutcome(str, Enum):
    REJECT = "REJECT"
    WAIT = "WAIT"
    READY_FOR_MANUAL_CONFIRMATION = "READY_FOR_MANUAL_CONFIRMATION"
    REDUCE = "REDUCE"
    EXIT = "EXIT"
```

Tests reject order, broker, fill and automatic-execution strings.

- [ ] **Step 4: Run contract tests and static checks.**

```bash
python -m pytest -q tests/features/test_model_contracts.py tests/research/test_model_contracts.py tests/signals/test_model_contracts.py tests/decision/test_model_contracts.py
python -m ruff check src/market_regime_alpha/features/model_contracts.py src/market_regime_alpha/research/model_contracts.py src/market_regime_alpha/signals/model_contracts.py src/market_regime_alpha/decision/model_contracts.py
```

- [ ] **Step 5: Commit.**

```bash
git add src/market_regime_alpha/features src/market_regime_alpha/research/model_contracts.py src/market_regime_alpha/signals src/market_regime_alpha/decision/model_contracts.py tests/features/test_model_contracts.py tests/research/test_model_contracts.py tests/signals/test_model_contracts.py tests/decision/test_model_contracts.py
git diff --cached --check
git commit -m "feat: add role-specific model migration contracts"
```

### Task 3: Implement the Decimal moving-average Feature Artifact

**Files:**
- Create: `src/market_regime_alpha/features/technical/__init__.py`
- Create: `src/market_regime_alpha/features/technical/moving_average.py`
- Create: `src/market_regime_alpha/features/artifact.py`
- Create: `tests/features/test_moving_average.py`
- Create: `tests/features/test_feature_artifact.py`
- Create: `tests/features/test_feature_replay.py`
- Modify: `pyproject.toml`

**Interfaces:**

```python
@dataclass(frozen=True, slots=True)
class NormalizedCloseBar:
    symbol: str
    market_date: date
    close: Decimal
    available_at: datetime

@dataclass(frozen=True, slots=True)
class MovingAverageConfiguration:
    configuration_id: ArtifactId
    configuration_version: str
    window: int
    content_hash: str

class SimpleMovingAverageComputer:
    feature_id = FeatureDefinitionId("technical.simple-moving-average")
    model_version = "1.0.0"
    def compute(self, request: FeatureComputationRequest) -> FeatureArtifact: ...
```

- [ ] **Step 1: Write failing pure-computation tests.**

Use `Decimal("10.00")`, `Decimal("11.00")`, `Decimal("12.00")` with window 3
and expect `Decimal("11.00")`. Assert the first two rows contain no value and
reason `WINDOW_NOT_READY`. Add unsorted bars, duplicate dates, post-as-of
availability, mixed symbols, invalid window and non-finite Decimal rejection.

- [ ] **Step 2: Implement deterministic Decimal computation.**

Use only explicit inputs:

```python
window_sum = sum((bar.close for bar in window_bars), start=Decimal("0"))
value = window_sum / Decimal(configuration.window)
```

Do not quantize or read current time. Preserve the exact Decimal string in
canonical JSON.

- [ ] **Step 3: Write failing publisher/Reader/replay tests.**

Require exactly:

```text
artifact.json
manifest.json
SHA256SUMS.json
```

Test idempotent republish, conflicting directory content, checksum tamper,
unexpected file, canonical hash tamper and replay mismatch.

- [ ] **Step 4: Implement atomic artifact publication.**

Follow the existing Signal publisher pattern: sibling staging directory,
canonical sorted JSON, checksum coverage, exact-file Reader and rename into a
content-derived artifact directory. Add package-data only if SQL/resource
packaging requires it; Python modules need no package-data entry.

- [ ] **Step 5: Prove purity and deterministic replay.**

Monkeypatch repository and Broker-related module imports to raise if reached;
run compute twice with the same explicit `created_at`/as-of and compare full
artifacts and semantic hashes.

- [ ] **Step 6: Run focused suites and commit.**

```bash
python -m pytest -q tests/features/test_moving_average.py tests/features/test_feature_artifact.py tests/features/test_feature_replay.py
python -m ruff check src/market_regime_alpha/features tests/features
git add src/market_regime_alpha/features tests/features pyproject.toml
git diff --cached --check
git commit -m "feat: add replayable decimal moving-average feature"
```

### Task 4: Implement the Legacy adapter and differential harness

**Files:**
- Create: `src/market_regime_alpha/migration/legacy/normalization/__init__.py`
- Create: `src/market_regime_alpha/migration/legacy/normalization/market_data.py`
- Create: `src/market_regime_alpha/migration/legacy/adapters/moving_average.py`
- Create: `src/market_regime_alpha/migration/comparison/__init__.py`
- Create: `src/market_regime_alpha/migration/comparison/contracts.py`
- Create: `src/market_regime_alpha/migration/comparison/harness.py`
- Create: `src/market_regime_alpha/migration/comparison/artifact.py`
- Create: `tests/migration/test_legacy_moving_average_adapter.py`
- Create: `tests/migration/test_differential_harness.py`
- Create: `tests/migration/test_comparison_artifact.py`

**Interfaces:**

```python
class DifferenceClassification(str, Enum):
    EXACT_MATCH = "EXACT_MATCH"
    NUMERIC_TOLERANCE = "NUMERIC_TOLERANCE"
    EXPECTED_SEMANTIC_CHANGE = "EXPECTED_SEMANTIC_CHANGE"
    LEGACY_DEFECT_FIXED = "LEGACY_DEFECT_FIXED"
    CANONICAL_REGRESSION = "CANONICAL_REGRESSION"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    NOT_COMPARABLE = "NOT_COMPARABLE"

class DifferentialTestHarness:
    def compare(
        self,
        *,
        dataset: NormalizedFeatureDataset,
        legacy_adapter: LegacyFeatureAdapter,
        canonical_model: FeatureComputer,
        policy: ComparisonPolicy,
        created_at: datetime,
    ) -> ModelComparisonReport: ...
```

- [ ] **Step 1: Write failing Legacy adapter tests.**

Patch and assert the adapter calls
`market_regime_alpha.dividend_t.indicators.add_daily_indicators`. Prove standard
bars become the expected pandas columns and output `ma_5`; normalize `NaN` to
an explicit missing result and convert numeric values with
`Decimal(str(value))`. An exception becomes a typed adapter result containing
the exception class/message and `LEGACY_COMPUTATION_FAILED`.

- [ ] **Step 2: Implement input normalization and the isolated adapter.**

The adapter returns a normalized result only. It has no Repository reference
and no method that can create Signal, Trade, Fill or Position.

- [ ] **Step 3: Write failing comparison-policy and classification tests.**

Cover every classification. In particular:

```python
assert classify(disagreement_without_oracle) is DifferenceClassification.NOT_COMPARABLE
assert classify(legacy_exception) is DifferenceClassification.INSUFFICIENT_DATA
assert classify(canonical_invariant_violation) is DifferenceClassification.CANONICAL_REGRESSION
```

Require a defect ID plus independently expected value for
`LEGACY_DEFECT_FIXED`; a Legacy mismatch alone is insufficient.

- [ ] **Step 4: Implement deterministic comparison.**

Compare exact structural fields first, then Decimal numeric tolerances, then
policy-bound semantic differences. Record field/numeric/semantic differences
separately, and set `expected_difference` and `unexpected_difference` from the
policy result rather than from test expectations.

- [ ] **Step 5: Add immutable report publication and replay.**

Use the same three-file package and exact Reader semantics as FeatureArtifact.
The semantic report hash excludes only explicit observation metadata
`created_at`; it includes dataset, model versions, policy hash and normalized
outputs.

- [ ] **Step 6: Run focused suites and commit.**

```bash
python -m pytest -q tests/migration
python -m ruff check src/market_regime_alpha/migration tests/migration
git add src/market_regime_alpha/migration tests/migration
git diff --cached --check
git commit -m "feat: add legacy differential verification harness"
```

### Task 5: Define lifecycle commands, input manifest and state machines

**Files:**
- Create: `src/market_regime_alpha/application/canonical_lifecycle/__init__.py`
- Create: `src/market_regime_alpha/application/canonical_lifecycle/states.py`
- Create: `src/market_regime_alpha/application/canonical_lifecycle/contracts.py`
- Create: `src/market_regime_alpha/application/canonical_lifecycle/commands.py`
- Create: `src/market_regime_alpha/application/canonical_lifecycle/input_manifest.py`
- Create: `tests/application/canonical_lifecycle/test_states.py`
- Create: `tests/application/canonical_lifecycle/test_contracts.py`
- Create: `tests/application/canonical_lifecycle/test_commands.py`
- Create: `tests/application/canonical_lifecycle/test_input_manifest.py`

**Interfaces:**

```python
class LifecycleRunType(str, Enum):
    CANONICAL_DECISION_LIFECYCLE = "CANONICAL_DECISION_LIFECYCLE"
    RISK_REDUCTION_CONTINUATION = "RISK_REDUCTION_CONTINUATION"
    REPLAY = "REPLAY"

class LifecycleRunStatus(str, Enum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    RETRYING = "RETRYING"
    WAITING_FOR_ENTRY_CONFIRMATION = "WAITING_FOR_ENTRY_CONFIRMATION"
    BLOCKED_BY_MODEL_VALIDATION = "BLOCKED_BY_MODEL_VALIDATION"
    WAITING_FOR_MANUAL_CONFIRMATION = "WAITING_FOR_MANUAL_CONFIRMATION"
    WAITING_FOR_FILL = "WAITING_FOR_FILL"
    POSITION_OPEN = "POSITION_OPEN"
    WAITING_FOR_T1 = "WAITING_FOR_T1"
    READY_FOR_HOLDING_ASSESSMENT = "READY_FOR_HOLDING_ASSESSMENT"
    READY_FOR_EXIT_REVIEW = "READY_FOR_EXIT_REVIEW"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

class LifecycleStageName(str, Enum):
    VERIFY_COMPOSITE_EVIDENCE = "VERIFY_COMPOSITE_EVIDENCE"
    PLATFORM_RESEARCH = "PLATFORM_RESEARCH"
    SIGNAL = "SIGNAL"
    PATH_FORECAST = "PATH_FORECAST"
    ENTRY_ASSESSMENT = "ENTRY_ASSESSMENT"
    OPPORTUNITY = "OPPORTUNITY"
    THESIS = "THESIS"
    PORTFOLIO_RISK = "PORTFOLIO_RISK"
    RISK_REDUCTION = "RISK_REDUCTION"
    MANUAL_CONFIRMATION = "MANUAL_CONFIRMATION"
    MANUAL_TRADE = "MANUAL_TRADE"
    FILL_POSITION = "FILL_POSITION"
    THESIS_HEALTH = "THESIS_HEALTH"
    HOLDING_ASSESSMENT = "HOLDING_ASSESSMENT"
    EXIT_ASSESSMENT = "EXIT_ASSESSMENT"
    OUTCOME_REVIEW = "OUTCOME_REVIEW"
```

- [ ] **Step 1: Write exhaustive transition-table tests.**

Parameterize every legal pair from design section 8 and assert all other pairs
raise `InvalidLifecycleTransition`. Do the same for `PENDING`, `RUNNING`,
`COMPLETED`, `WAITING`, `BLOCKED`, `FAILED` and
`SKIPPED_NOT_APPLICABLE` stage states.

- [ ] **Step 2: Implement exact enums, order and transition validators.**

Expose `LIFECYCLE_STAGE_ORDER` and reject stage skipping. Completed, blocked
and not-applicable stages are immutable.

- [ ] **Step 3: Write failing immutable-record tests.**

Cover `LifecycleRun`, `LifecycleStage`, `LifecycleAttempt`, `StageReceipt`,
`LifecycleEvent` and `LifecycleObjectReference`; require canonical round trip,
aware whole-second UTC times, sorted references, aligned hashes, positive
versions/tokens and semantic receipt hash verification.

- [ ] **Step 4: Implement records using canonical helpers.**

Receipt identity is:

```python
receipt_hash = canonical_hash(receipt.semantic_payload())
receipt_id = ArtifactId(f"lifecycle-receipt-{receipt_hash.split(':', 1)[1][:24]}")
```

Exclude attempt wall-clock timestamps from `semantic_payload`; retain them in
attempt/event audit records.

- [ ] **Step 5: Add command and manifest identity tests.**

Prove output directory and resume control do not change semantic command hash,
while run type, decision/as-of time, input hash and config/model manifests do.
Reject naive time, hash mismatch, different ID/same hash ambiguity and locator
without an expected hash.

- [ ] **Step 6: Implement strict canonical Readers and run tests.**

```bash
python -m pytest -q tests/application/canonical_lifecycle/test_states.py tests/application/canonical_lifecycle/test_contracts.py tests/application/canonical_lifecycle/test_commands.py tests/application/canonical_lifecycle/test_input_manifest.py
python -m ruff check src/market_regime_alpha/application/canonical_lifecycle tests/application/canonical_lifecycle
```

- [ ] **Step 7: Commit.**

```bash
git add src/market_regime_alpha/application/canonical_lifecycle tests/application/canonical_lifecycle
git diff --cached --check
git commit -m "feat: define canonical lifecycle contracts"
```

### Task 6: Add migration 011 and the transactional Runtime Journal

**Files:**
- Create: `src/market_regime_alpha/application/canonical_lifecycle/migrations/011_canonical_lifecycle_runtime_up.sql`
- Create: `src/market_regime_alpha/application/canonical_lifecycle/migrations/011_canonical_lifecycle_runtime_down.sql`
- Create: `src/market_regime_alpha/application/canonical_lifecycle/repositories.py`
- Create: `src/market_regime_alpha/application/canonical_lifecycle/sqlite_repository.py`
- Modify: `pyproject.toml`
- Create: `tests/application/canonical_lifecycle/test_migration_011.py`
- Create: `tests/application/canonical_lifecycle/test_sqlite_repository.py`
- Create: `tests/application/canonical_lifecycle/test_history.py`

**Interfaces:**

```python
class LifecycleRunRepository(Protocol):
    def create_or_get(self, command: CanonicalLifecycleCommand, *, created_at: datetime) -> LifecycleRun: ...
    def get_run(self, run_id: LifecycleRunId) -> LifecycleRun: ...
    def claim(self, run_id: LifecycleRunId, *, expected_version: int, claimed_at: datetime) -> LifecycleRun: ...
    def start_stage(self, run_id: LifecycleRunId, stage: LifecycleStageName, *, started_at: datetime, claim_token: int) -> LifecycleAttempt: ...
    def finish_stage(self, transition: StageTransition) -> LifecycleRun: ...
    def mark_stage_failed(self, failure: StageFailure) -> LifecycleRun: ...
    def resume(self, run_id: LifecycleRunId, *, resumed_at: datetime) -> LifecycleRun: ...
    def history(self, run_id: LifecycleRunId) -> LifecycleHistory: ...
```

- [ ] **Step 1: Write migration tests from a database at migration 010.**

Assert all five tables, foreign keys, checks, indexes, triggers and package
resource paths. Repeat up application without data loss. Test down on an
isolated database and prove migrations 002–010 remain untouched.

- [ ] **Step 2: Implement SQL constraints and append-only triggers.**

Required unique keys are:

```text
lifecycle_runs(idempotency_key)
lifecycle_stages(run_id, stage_name)
lifecycle_attempts(run_id, stage_name, attempt_number)
lifecycle_stage_receipts(receipt_id)
lifecycle_stage_receipts(run_id, stage_name, receipt_hash)
lifecycle_events(run_id, sequence_number)
```

Add triggers rejecting update/delete on attempts, receipts and events and
rejecting mutation of a completed stage.

- [ ] **Step 3: Write failing idempotency and command-conflict tests.**

The same idempotency key/hash returns the same `run_id`; the same key with a
different command hash raises `LifecycleIdempotencyConflict`. Concurrent
connections must not create two rows.

- [ ] **Step 4: Implement `create_or_get` with `BEGIN IMMEDIATE`.**

After `INSERT OR IGNORE`, reload and compare the stored canonical command and
hash. Never treat an `IntegrityError` as successful without semantic reload.

- [ ] **Step 5: Write failing stage/attempt/receipt transaction tests.**

Inject failure between every insert/update in `finish_stage`; assert the whole
transition rolls back. Prove attempt numbering increments, completed receipt
cannot change and stage/run versions use compare-and-set.

- [ ] **Step 6: Implement transactional transition methods.**

Use one explicit transaction to validate claim/version, update attempt, insert
receipt, transition stage/run and append the next event. Verify `rowcount == 1`
for every projection compare-and-set.

- [ ] **Step 7: Implement failure, resume and history.**

Failure records exception type/message and the last safe stage. Resume moves
`FAILED → RETRYING → RUNNING`, increments claim token and never changes a
completed stage. History orders events by sequence, attempts by stage/number
and receipts by creation/ID.

- [ ] **Step 8: Run repository suites and commit.**

```bash
python -m pytest -q tests/application/canonical_lifecycle/test_migration_011.py tests/application/canonical_lifecycle/test_sqlite_repository.py tests/application/canonical_lifecycle/test_history.py
python -m ruff check src/market_regime_alpha/application/canonical_lifecycle tests/application/canonical_lifecycle
git add src/market_regime_alpha/application/canonical_lifecycle pyproject.toml tests/application/canonical_lifecycle
git diff --cached --check
git commit -m "feat: persist canonical lifecycle runtime journal"
```

### Task 7: Implement the runner kernel and recoverable stage adapter contract

**Files:**
- Create: `src/market_regime_alpha/application/canonical_lifecycle/runner.py`
- Create: `src/market_regime_alpha/application/canonical_lifecycle/stages/__init__.py`
- Create: `src/market_regime_alpha/application/canonical_lifecycle/stages/contracts.py`
- Create: `tests/application/canonical_lifecycle/test_runner.py`
- Create: `tests/application/canonical_lifecycle/test_runner_recovery.py`

**Interfaces:**

```python
@dataclass(frozen=True, slots=True)
class StageExecutionResult:
    stage_status: LifecycleStageStatus
    run_status: LifecycleRunStatus
    input_references: tuple[LifecycleObjectReference, ...]
    output_references: tuple[LifecycleObjectReference, ...]
    model_versions: tuple[tuple[str, str], ...]
    configuration_hashes: tuple[str, ...]
    reason_codes: tuple[str, ...]
    blocker_reason: str | None

class LifecycleStageHandler(Protocol):
    stage_name: LifecycleStageName
    mutation_kind: StageMutationKind
    def recover(self, context: LifecycleStageContext) -> StageExecutionResult | None: ...
    def execute(self, context: LifecycleStageContext) -> StageExecutionResult: ...

class CanonicalDecisionLifecycleRunner:
    def run(self, command: CanonicalLifecycleCommand) -> LifecycleRunResult: ...
    def resume(self, run_id: LifecycleRunId, *, stop_after_stage: LifecycleStageName | None = None) -> LifecycleRunResult: ...
```

- [ ] **Step 1: Write failing handler-order and stop tests.**

Use recording fake handlers to prove exact enum order, one active stage at a
time, `--stop-after-stage` completion, explicit not-applicable receipts and no
execution after waiting/blocked/failed results.

- [ ] **Step 2: Implement the runner without domain logic.**

The runner only claims, locates the first safe stage, calls `recover()` before
`execute()`, verifies references and delegates atomic journal transitions.
Reject missing, duplicate and wrong-name handler registrations.

- [ ] **Step 3: Write fault-injection recovery tests.**

Simulate:

```text
before domain call
during domain call
after domain commit before receipt
after receipt before CLI return
```

The recoverable fake exposes a deterministic output ID/hash after domain
commit. Resume must reload it, create one receipt, increment attempt count and
never invoke `execute()` again for that stage.

- [ ] **Step 4: Implement typed failure handling.**

Expected waiting/blocking results are receipts, not exceptions. Unexpected
exceptions are recorded with exact class/message and re-raised as
`LifecycleStageExecutionError` after the journal failure transaction.

- [ ] **Step 5: Run focused suites and commit.**

```bash
python -m pytest -q tests/application/canonical_lifecycle/test_runner.py tests/application/canonical_lifecycle/test_runner_recovery.py
python -m ruff check src/market_regime_alpha/application/canonical_lifecycle tests/application/canonical_lifecycle
git add src/market_regime_alpha/application/canonical_lifecycle tests/application/canonical_lifecycle
git diff --cached --check
git commit -m "feat: add recoverable canonical lifecycle runner"
```

### Task 8: Add evidence, research, Signal, forecast and Entry stage adapters

**Files:**
- Create: `src/market_regime_alpha/application/canonical_lifecycle/stages/evidence.py`
- Create: `src/market_regime_alpha/application/canonical_lifecycle/stages/research.py`
- Create: `src/market_regime_alpha/application/canonical_lifecycle/stages/signal_forecast.py`
- Create: `tests/application/canonical_lifecycle/test_research_stages.py`
- Create: `tests/application/canonical_lifecycle/test_entry_blocker.py`
- Modify: `src/market_regime_alpha/application/operational_research/bridge.py` only if a public verified-output lookup is missing.

**Interfaces:**
- `VerifyCompositeEvidenceStage` loads only through the H6 Reader.
- `PlatformResearchStage` composes `OperationalResearchRunner` and `PlatformResearchRunner`.
- `SignalStage` calls `run_signal_model` and the existing Signal publisher/Reader.
- `PathForecastStage` calls `build_path_forecast` and its existing publisher/Reader.
- `EntryAssessmentStage` maps existing validation/evidence state to ready, wait or blocked without changing thresholds.

- [ ] **Step 1: Write a verified-H6 evidence stage test.**

Seed the existing exact H6 package fixture and assert receipt inputs contain
manifest ID/hash and both package references. Tamper and non-VERIFIED inputs
must fail before research is called.

- [ ] **Step 2: Implement controlled Readers and output recovery.**

Each stage's `recover()` loads the deterministic published path/Repository
object and compares ID/hash. It cannot accept unverified raw JSON.

- [ ] **Step 3: Write an H6 → Platform V2 stage integration test.**

Assert the actual call chain is:

```text
load_verified_composite_operational_manifest
→ OperationalResearchRunner.run
→ PlatformResearchRunner.run
→ verified Research Layer Artifact
```

Receipt output must reference the verified research artifact, not the input
bundle object alone.

- [ ] **Step 4: Add Signal and forecast sufficiency tests.**

When all required observations/samples exist, compare stage output to direct
existing function output. When current H6 lacks required factors/samples,
return explicit `DATA_INSUFFICIENT` with the existing reason codes; do not use
Legacy or static values.

- [ ] **Step 5: Add the unvalidated Entry stop test.**

Use the actual Entry validation status and assert the run stops at
`BLOCKED_BY_MODEL_VALIDATION` or `WAITING_FOR_ENTRY_CONFIRMATION`, with a stage
receipt and no Opportunity call. The assertion must follow current domain
semantics rather than force a preferred status.

- [ ] **Step 6: Run focused stage suites and commit.**

```bash
python -m pytest -q tests/application/canonical_lifecycle/test_research_stages.py tests/application/canonical_lifecycle/test_entry_blocker.py tests/application/operational_research tests/research/platform_v2 tests/signals tests/forecasting
python -m ruff check src/market_regime_alpha/application/canonical_lifecycle tests/application/canonical_lifecycle
git add src/market_regime_alpha/application/canonical_lifecycle src/market_regime_alpha/application/operational_research/bridge.py tests/application/canonical_lifecycle
git diff --cached --check
git commit -m "feat: orchestrate canonical research and entry stages"
```

### Task 9: Add decision, portfolio/risk and existing-position continuation stages

**Files:**
- Create: `src/market_regime_alpha/application/canonical_lifecycle/stages/decision_risk.py`
- Create: `tests/application/canonical_lifecycle/test_decision_risk_stages.py`
- Create: `tests/application/canonical_lifecycle/test_risk_reduction_continuation.py`

**Interfaces:**
- Opportunity/Thesis calls use `DecisionLifecycleService`.
- Portfolio/Risk calls use existing application services and durable repositories.
- H4 reducing route calls `RiskRouteApplicationService.assess_reducing()`.
- `RISK_REDUCTION_CONTINUATION` starts from existing traceable authorities and marks entry-only stages `SKIPPED_NOT_APPLICABLE` with receipts.

- [ ] **Step 1: Write decision-service delegation tests.**

Use spies around the real Repository to prove Opportunity and Thesis are
created once, stage receipts bind exact aggregate ID/version/hash and resume
reloads them rather than recreating them.

- [ ] **Step 2: Implement decision stages as thin adapters.**

Map only existing service return types. A rejected/WAIT portfolio or risk
decision stops with its exact reasons; no runner-side score interpretation is
allowed.

- [ ] **Step 3: Write portfolio/risk and H4 delegation tests.**

Seed the current account/position fixtures. Compare returned decisions against
direct existing application-service calls and verify exact Repository reload.

- [ ] **Step 4: Write an existing-position continuation test.**

Provide traceable PositionBook/PositionSnapshot, Thesis, H5, H6 and H4
references. Assert evidence-through-entry stages are not-applicable, the H4
decision is loaded, and the run reaches `WAITING_FOR_MANUAL_CONFIRMATION`.

- [ ] **Step 5: Implement continuation routing and run tests.**

```bash
python -m pytest -q tests/application/canonical_lifecycle/test_decision_risk_stages.py tests/application/canonical_lifecycle/test_risk_reduction_continuation.py tests/decision tests/portfolio
python -m ruff check src/market_regime_alpha/application/canonical_lifecycle tests/application/canonical_lifecycle
```

- [ ] **Step 6: Commit.**

```bash
git add src/market_regime_alpha/application/canonical_lifecycle tests/application/canonical_lifecycle
git diff --cached --check
git commit -m "feat: orchestrate canonical decision and risk stages"
```

### Task 10: Harden H4.5 supersession and add the stable manual-only CLI

**Files:**
- Modify: `src/market_regime_alpha/application/trading_lifecycle/sqlite_risk_reduction.py`
- Modify: `src/market_regime_alpha/application/trading_lifecycle/risk_reduction_confirmation.py`
- Create: `src/market_regime_alpha/cli/__init__.py`
- Create: `src/market_regime_alpha/cli/create_manual_trade_from_risk_decision.py`
- Modify: `scripts/confirm_risk_reduction.py`
- Modify: `tests/execution/test_risk_reduction_confirmation_repository.py`
- Create: `tests/execution/test_create_manual_trade_from_risk_decision_cli.py`

**Interfaces:**
- H4.5 continues to produce only `RiskReductionConfirmationAttempt` and `ManualTradeRecord V3 REDUCING`.
- Latest same-scope decision check is performed inside the existing `BEGIN IMMEDIATE` authority transaction.
- CLI success/wait/failure JSON always contains `MANUAL_CONFIRMATION_REQUIRED`, `NO_ORDER_CREATED`, `BROKER_NOT_INVOKED` and `NO_FILL_CREATED`.

- [ ] **Step 1: Write a failing superseded-decision test.**

Seed two durable reducing decisions for the same PositionBook, Thesis and
symbol with the second decision created later. Confirming the first must create
an immutable rejected attempt with reason `RISK_REDUCING_DECISION_SUPERSEDED`
and no ManualTrade; confirming the latest may succeed if every existing gate
passes.

- [ ] **Step 2: Implement same-scope latest-decision verification.**

Query durable H4 decisions in deterministic `(created_at, decision_id)` order
inside the transaction. Compare full scope and do not mutate the old decision.
Add an index only through migration 011 if the query needs one; do not rewrite
migration 007 or 010.

- [ ] **Step 3: Add full H4.5 safety regression tests.**

Run/extend legal creation, same-command replay, conflicting idempotency key,
expired decision, changed Position, quantity over sellable shares, T+1,
symbol/Thesis/hash mismatch and rollback tests. Assert counts for BrokerOrder,
Fill and Broker call fakes remain zero.

- [ ] **Step 4: Write the new module CLI tests.**

The success payload includes:

```python
{
    "MANUAL_CONFIRMATION_REQUIRED": True,
    "NO_ORDER_CREATED": True,
    "BROKER_NOT_INVOKED": True,
    "NO_FILL_CREATED": True,
}
```

The parser accepts no Broker endpoint, account login, QMT or PTrade argument.
Test deterministic exit codes for validation, idempotency conflict and domain
rejection.

- [ ] **Step 5: Implement CLI delegation and compatibility wrapper.**

Move reusable parsing/JSON rendering into the module CLI and let the script
call its `main()`. Preserve all existing script arguments and add the required
stable declarations without removing historical safety declarations.

- [ ] **Step 6: Run focused suites and commit.**

```bash
python -m pytest -q tests/execution/test_risk_reduction_confirmation_repository.py tests/execution/test_create_manual_trade_from_risk_decision_cli.py tests/execution/test_confirm_risk_reduction_cli.py tests/execution/test_migration_010_risk_reduction.py
python -m ruff check src/market_regime_alpha/application/trading_lifecycle/sqlite_risk_reduction.py src/market_regime_alpha/cli scripts/confirm_risk_reduction.py tests/execution
git add src/market_regime_alpha/application/trading_lifecycle src/market_regime_alpha/cli scripts/confirm_risk_reduction.py tests/execution
git diff --cached --check
git commit -m "feat: harden reducing decisions to manual trade"
```

### Task 11: Add ManualTrade, Fill/Position, health, assessment and review stage adapters

**Files:**
- Create: `src/market_regime_alpha/application/canonical_lifecycle/stages/execution_position.py`
- Create: `src/market_regime_alpha/application/canonical_lifecycle/stages/assessment_review.py`
- Create: `tests/application/canonical_lifecycle/test_execution_position_stages.py`
- Create: `tests/application/canonical_lifecycle/test_assessment_review_stages.py`

**Interfaces:**
- Manual confirmation validates explicit confirmation evidence but does not itself create a trade.
- ManualTrade stage calls the H4.5 service once and returns `WAITING_FOR_FILL`.
- Fill/Position stage only observes existing manual Fill records and rebuilds Position.
- Health/holding/exit/review stages call existing services and store references; absent durable H7 authority yields readiness/wait state rather than an invented record.

- [ ] **Step 1: Write ManualTrade stage and recovery tests.**

Assert no confirmation yields `WAITING_FOR_MANUAL_CONFIRMATION`. With valid
confirmation, assert H4.5 produces exactly one trade and the run becomes
`WAITING_FOR_FILL`. Crash after H4.5 commit must recover by idempotency key and
record the missing lifecycle receipt without a second trade.

- [ ] **Step 2: Implement ManualTrade adapter.**

Use a stage idempotency key derived from `run_id`, stage name and immutable H4
decision hash. Verify the reloaded trade's reducing authority route and source
hashes before recording the receipt.

- [ ] **Step 3: Write external Fill/Position observation tests.**

With no Fill, remain `WAITING_FOR_FILL`. After a separately recorded observed
Fill, call the existing Fill-derived projector and move to `POSITION_OPEN` or
`WAITING_FOR_T1`. Assert the runner never calls Fill append.

- [ ] **Step 4: Implement Fill/Position stage as read-only orchestration.**

The handler receives only repository/projector read capability. Its constructor
must not accept a Fill command service.

- [ ] **Step 5: Write health, holding, exit and review delegation tests.**

Compare each output to direct existing service execution. When the current
repository lacks durable H7 assessment storage, journal the existing assessment
Artifact/result reference and stop at `READY_FOR_HOLDING_ASSESSMENT` or
`READY_FOR_EXIT_REVIEW` according to actual available authority.

- [ ] **Step 6: Implement adapters and run focused suites.**

```bash
python -m pytest -q tests/application/canonical_lifecycle/test_execution_position_stages.py tests/application/canonical_lifecycle/test_assessment_review_stages.py tests/execution tests/position tests/evaluation
python -m ruff check src/market_regime_alpha/application/canonical_lifecycle tests/application/canonical_lifecycle
```

- [ ] **Step 7: Commit.**

```bash
git add src/market_regime_alpha/application/canonical_lifecycle tests/application/canonical_lifecycle
git diff --cached --check
git commit -m "feat: orchestrate manual execution and position lifecycle"
```

### Task 12: Add canonical lifecycle CLI and replay verifier

**Files:**
- Create: `src/market_regime_alpha/application/canonical_lifecycle/replay.py`
- Create: `src/market_regime_alpha/cli/run_canonical_lifecycle.py`
- Create: `tests/application/canonical_lifecycle/test_replay.py`
- Create: `tests/application/canonical_lifecycle/test_cli.py`

**Interfaces:**

```python
class LifecycleReplayVerifier:
    def replay(self, run_id: LifecycleRunId) -> LifecycleReplayReport: ...

def main(argv: Sequence[str] | None = None) -> int: ...
```

- [ ] **Step 1: Write semantic replay tests.**

For pure stages, rerun recorded model/config/input/as-of and compare semantic
receipt hashes. For ManualTrade and other mutating stages, reload and verify
the original durable object instead of invoking the mutation. Tampered input,
output or receipt must fail closed.

- [ ] **Step 2: Implement replay routing by stage mutation kind.**

Return a content-addressed replay report listing matched/mismatched/not-
replayable stages and exact reasons. A replay run has `run_type=REPLAY` and
references the source run without changing it.

- [ ] **Step 3: Write CLI create/resume/stop/replay tests.**

Cover all required options:

```text
--input-manifest
--decision-date
--as-of
--idempotency-key
--resume-run-id
--stop-after-stage
--output-dir
```

Assert one sorted JSON object, current status/stage, completed stages, blocker,
retry state, ManualTrade reference, and fixed Broker safety declarations.

- [ ] **Step 4: Implement stable exit codes and dependency composition.**

Use exact codes:

```text
0 valid completed/waiting/blocked result
2 command/input validation
3 idempotency conflict
4 unknown/unsafe resume
5 recoverable stage failure
6 repository/migration/integrity failure
```

The CLI creates Readers/Repositories/services from explicit paths only; it
does not import web or Broker modules.

- [ ] **Step 5: Run CLI/replay tests and commit.**

```bash
python -m pytest -q tests/application/canonical_lifecycle/test_replay.py tests/application/canonical_lifecycle/test_cli.py
python -m ruff check src/market_regime_alpha/application/canonical_lifecycle src/market_regime_alpha/cli tests/application/canonical_lifecycle
git add src/market_regime_alpha/application/canonical_lifecycle src/market_regime_alpha/cli tests/application/canonical_lifecycle
git diff --cached --check
git commit -m "feat: add canonical lifecycle cli and replay"
```

### Task 13: Close integration, recovery, documentation and quality evidence

**Files:**
- Create: `tests/application/canonical_lifecycle/test_end_to_end.py`
- Create: `tests/application/canonical_lifecycle/test_recovery_integration.py`
- Create: `docs/audit/Canonical-Runtime-and-Legacy-Migration-Delivery.md`
- Modify: `docs/README.md`
- Modify: `docs/architecture/01-Domain-Boundaries.md`
- Modify: `docs/architecture/06-Legacy-Migration.md`
- Modify: `docs/architecture/10-Production-Decision-Lifecycle.md`
- Modify: `docs/operations/Production-Decision-Lifecycle-Runbook.md`
- Modify: `docs/status/Current-State.md`
- Modify: `docs/status/Capability-Matrix.md`
- Modify: `docs/status/Gap-Register.md`

**Interfaces:**
- Produces commit-bound delivery evidence and truthful current-state documentation.
- Proves both honest lifecycle paths without bypassing Entry validation.

- [ ] **Step 1: Add the research-to-entry-blocker integration test.**

Exercise actual verified H6 package → Operational Research → Platform Research
→ Signal/data sufficiency → PathForecast → Entry blocker. Assert journal run,
stages, attempts, receipts and events, and assert Opportunity/ManualTrade/Fill
counts stay zero after the blocker.

- [ ] **Step 2: Add risk-reduction-to-ManualTrade integration test.**

Seed traceable existing Position/Thesis/H5/H6/H4 authorities, run
`RISK_REDUCTION_CONTINUATION`, supply confirmation and assert exactly one H4.5
ManualTrade, `WAITING_FOR_FILL`, no Fill, no Broker object and no Broker call.

- [ ] **Step 3: Add cross-repository crash recovery integration.**

Inject a crash after ManualTrade commit/before lifecycle receipt. Resume and
assert:

```text
same run_id
same manual_trade_id
attempt_count increased
one semantic receipt
completed stages not invoked again
no Fill and no Broker calls
```

- [ ] **Step 4: Add full replay/idempotency integration.**

Run the same explicit input twice with one idempotency key, then replay. Compare
run IDs, domain object IDs, semantic hashes and receipts. Freeze/patch current
time to raise if accessed outside injected clock values.

- [ ] **Step 5: Run the complete canonical/Legacy focused gate.**

```bash
python -m pytest -q tests/architecture tests/features tests/migration tests/application/canonical_lifecycle tests/execution/test_risk_reduction_confirmation_repository.py tests/execution/test_create_manual_trade_from_risk_decision_cli.py
```

Expected: PASS with no skip added.

- [ ] **Step 6: Update architecture, status, runbook and delivery evidence.**

Document the actual code call chain, migration 011 tables/indexes/constraints,
full transition matrix, transaction/Saga boundary, H4.5 safety proof, Legacy
dependency rule, model contracts, differential classifications and MA replay.
Retain the four fixed false capability declarations and list:

```text
WP-MIG-01 Technical Observable Migration
MACD
Moving Average expansion
Volume Structure
Force Ratio
Chan Features
Tuishen Volume-Price Features
```

- [ ] **Step 7: Run documentation and packaging checks.**

```bash
python scripts/check_docs_links.py
python -m pytest -q tests/scripts/test_check_docs_links.py
python -m build
git diff --check
```

- [ ] **Step 8: Run the complete repository quality gate.**

```bash
python -m pytest -q tests/platform
python -m pytest -q
python -m ruff check .
python -m mypy
python -m build
```

Record actual counts and every command as `PASS`, `FAIL`, `NOT_RUN` or
`BLOCKED`; fix in-scope failures without deleting, weakening or skipping tests.

- [ ] **Step 9: Perform final scope and safety review.**

Inspect:

```bash
git status --short
git diff --check
git diff --stat origin/main...HEAD
git diff origin/main...HEAD -- src tests docs pyproject.toml scripts
rg -n "BrokerOrder|QMT|PTrade|append_fill" src/market_regime_alpha/application/canonical_lifecycle src/market_regime_alpha/cli
```

Confirm `.idea/modules.xml`, credentials, personal paths and generated build
artifacts are not staged. Confirm any `append_fill` occurrence is absent from
runner/CLI production code or is a test assertion proving it was not called.

- [ ] **Step 10: Commit delivery evidence.**

```bash
git add docs tests/application/canonical_lifecycle
git diff --cached --check
git commit -m "docs: record canonical runtime migration delivery"
```

Do not push, merge or open a PR unless the user separately requests it.
