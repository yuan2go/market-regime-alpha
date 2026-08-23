# Alpha Daily Architecture Convergence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **Status:** CURRENT_RESEARCH_PROGRAM

**Goal:** Close the frozen intraday Alpha correctness risk, execute only evidence-admissible campaigns, wire conditional prediction through PostgreSQL owners, start immutable FreeData daily research, and retire proven duplicate architecture.

**Architecture:** Extend the existing PostgreSQL-centered modular monolith. Raw correctness is a pure independent kernel feeding the existing Historical Phase II evidence service; calendar/session freeze extends the existing `ResearchExperimentDefinition`; Strategy Opportunity and pre-Strategy Risk are new business facts inside the existing Strategy authority; daily prediction/settlement remains a child of `CONTINUOUS_RESEARCH`.

**Tech Stack:** Python 3.12, immutable dataclasses, psycopg/PostgreSQL 16, content-addressed canonical JSON, pytest, Ruff, mypy, `uv build`.

## Global Constraints

- Never rewrite migrations 001–092 or historical Evidence.
- Never call production normalization from the independent Raw correctness kernel.
- Never read External outcomes unless owner-resolved Correctness is `CORRECTNESS_SUPPORTED`.
- Preserve incumbent Overnight/Swing V1 identities and one Strategy Runtime.
- Keep Conditional Strategy and validated challenger inactive when evidence dependencies fail.
- Never touch `.idea/modules.xml`.

---

### Task 1: Independent Raw Normalization Correctness

**Files:**
- Create: `src/market_regime_alpha/application/historical_corpus/raw_normalization_correctness.py`
- Modify: `src/market_regime_alpha/application/historical_corpus/alpha_correctness.py`
- Modify: `src/market_regime_alpha/application/historical_corpus/phase_ii_service.py`
- Test: `tests/application/historical_corpus/test_raw_normalization_correctness.py`
- Test: `tests/application/historical_corpus/test_alpha_correctness.py`

**Interfaces:**
- Consumes: `HistoricalDataOwner` Raw and Normalized owners plus immutable physical package verification.
- Produces: `IndependentNormalizationVerification` with provenance, canonical comparisons and deterministic discrepancy classes; `AlphaCorrectnessConclusion` maps internal states to supported/failed/inconclusive.

- [ ] **Step 1: Write failing comparison tests**

```python
verification = verify_independent_baostock_normalization(
    raw_owner=raw_owner,
    canonical_normalized_owner=normalized_owner,
    provenance=PhysicalAcquisitionProvenance.REACQUIRED_EQUIVALENT_SOURCE,
)
assert verification.status is IndependentNormalizationStatus.MATCHED
assert verification.discrepancies == ()
```

Add mismatch cases for event interval, OHLC, volume, amount, adjustment basis,
source request identity and canonical bar hash. Assert sorted stable reason codes.

- [ ] **Step 2: Verify tests fail before implementation**

Run: `python -m pytest -q tests/application/historical_corpus/test_raw_normalization_correctness.py`

Expected: import failure for the new module.

- [ ] **Step 3: Implement the independent pure kernel**

Implement a self-contained parser for BaoStock Daily/5-minute fields. It may use
`HistoricalRawRequest`/`HistoricalNormalizedBar` types but must not import
`historical_corpus.normalization` or its private functions. Compare observations
by `(session, symbol, timeframe, event_start)` and compare every required field.

- [ ] **Step 4: Bind both correctness layers into the aggregate proof**

Require Raw physical verification and independent normalization verification
before a proof can map to `CORRECTNESS_SUPPORTED`. Map absent physical bytes,
unavailable provider data or insufficient population to `INCONCLUSIVE`; map
deterministic value/temporal/lineage disagreement to `CORRECTNESS_FAILED`.

- [ ] **Step 5: Run focused tests and commit**

Run: `python -m pytest -q tests/application/historical_corpus/test_raw_normalization_correctness.py tests/application/historical_corpus/test_alpha_correctness.py tests/persistence/postgres/test_phase_ii_evidence_service.py`

Commit explicit Task 1 files with message `feat: close raw normalization correctness`.

### Task 2: Calendar-Owned TEMPORAL_VALIDATION_V1 Identity

**Files:**
- Create: `src/market_regime_alpha/application/historical_corpus/temporal_validation_window.py`
- Modify: `src/market_regime_alpha/application/historical_corpus/external_validation.py`
- Modify: `src/market_regime_alpha/application/historical_corpus/phase_ii_service.py`
- Test: `tests/application/historical_corpus/test_temporal_validation_window.py`
- Test: `tests/application/historical_corpus/test_external_validation.py`

**Interfaces:**
- Consumes: owner-reloaded `TradingCalendarArtifact`, start `date(2025, 7, 15)`, count 126.
- Produces: `FrozenTemporalValidationWindow` containing all Decision sessions, final Target session and calendar reference/hash; this object is embedded in `FrozenExternalValidationExperiment` identity.

- [ ] **Step 1: Write failing calendar identity tests**

```python
window = freeze_temporal_validation_window(
    calendar=calendar,
    start_decision_session=date(2025, 7, 15),
    session_count=126,
)
assert window.decision_sessions[0] == date(2025, 7, 15)
assert len(window.decision_sessions) == 126
assert window.final_target_session == calendar.resolve_next_session_date(
    DecisionTime(datetime.combine(window.decision_sessions[-1], time(14, 55), SHANGHAI))
)
```

Reject missing start, fewer than 127 available sessions, altered session list,
calendar hash drift, and a second external validation dimension.

- [ ] **Step 2: Verify the new tests fail**

Run: `python -m pytest -q tests/application/historical_corpus/test_temporal_validation_window.py`

- [ ] **Step 3: Implement and bind the frozen window**

The function must slice explicit `TradingCalendarArtifact.sessions`; it must not
infer weekdays or accept a caller-supplied end date. Persist the full date list,
final target date, calendar reference and hash in canonical payloads.

- [ ] **Step 4: Add `INCONCLUSIVE` external result semantics**

Return `INCONCLUSIVE` for insufficient admissible coverage or inference rather
than collapsing missing evidence into `NOT_SUPPORTED`. Keep measured threshold
failure as `NOT_SUPPORTED` and supported thresholds as `SUPPORTED`.

- [ ] **Step 5: Run focused tests and commit**

Run: `python -m pytest -q tests/application/historical_corpus/test_temporal_validation_window.py tests/application/historical_corpus/test_external_validation.py tests/persistence/postgres/test_phase_ii_evidence_service.py`

Commit with message `feat: freeze owner-derived temporal validation window`.

### Task 3: Reacquisition and Gated Research Campaign

**Files:**
- Modify: `src/market_regime_alpha/cli/continuous_research.py`
- Modify: `src/market_regime_alpha/application/historical_corpus/baostock_archive.py`
- Modify: `src/market_regime_alpha/application/historical_corpus/phase_ii_service.py`
- Create/update: owner-generated campaign report under `docs/references/`
- Test: focused Historical/PostgreSQL campaign tests.

**Interfaces:**
- Consumes: original request parameters/symbol scope from PostgreSQL owners, BaoStock provider, frozen discovery Experiment and new temporal protocol.
- Produces: immutable `REACQUIRED_EQUIVALENT_SOURCE` Raw/Normalized packages, correctness Evidence, and—only if supported—External/Context/Candidate Evidence.

- [ ] **Step 1: Add an explicit reacquisition command contract**

Require the original provider, symbols, Daily `2024-06-01..2025-07-14`, minute
`2025-01-01..2025-07-14`, adjustflag 3, bucket count 128 and an acquisition ID.
The command output must state `ORIGINAL_PHYSICAL_REOPENED=false` and
`REACQUIRED_EQUIVALENT_SOURCE=true`.

- [ ] **Step 2: Reacquire and publish exact packages**

Use checkpointed requests and existing `PostgresHistoricalCorpusRepository`.
Never overwrite or reuse old owner IDs unless content hashing independently
produces equality and the provenance still remains reacquired.

- [ ] **Step 3: Execute the complete 126-session correctness suite**

Run the frozen Factor/target/placebo/timing/redundancy/block-inference protocol
and persist a typed result. Preserve mismatches and negative/inconclusive output.

- [ ] **Step 4: Enforce the outcome access gate**

If correctness is failed/inconclusive, persist the blocked reason without an
External Evaluation artifact and do not fetch/read external outcome bars. If
supported, acquire the calendar-frozen temporal corpus and execute the frozen
External evaluator.

- [ ] **Step 5: Gate Context and Candidate**

Run both only for `SUPPORTED` External evidence. Compare Incumbent and
Challenger on the identical frozen panel/economics protocol. Leave the
Challenger dormant unless stable supported improvement is recorded.

- [ ] **Step 6: Verify replay and commit campaign records**

Replay every persisted owner and run targeted PostgreSQL tests. Commit code and
truthful report separately from provider-generated artifact roots.

### Task 4: PostgreSQL Pre-Strategy Risk and Opportunity Owners

**Files:**
- Create: `src/market_regime_alpha/strategies/opportunity_authority.py`
- Modify: `src/market_regime_alpha/strategies/contracts.py`
- Modify: `src/market_regime_alpha/strategies/multi_strategy.py`
- Modify: `src/market_regime_alpha/strategies/postgres_repository.py`
- Create: `src/market_regime_alpha/persistence/postgres/migrations/093_strategy_opportunity_authority.sql`
- Modify: `src/market_regime_alpha/persistence/postgres/schema.py`
- Test: `tests/strategies/test_opportunity_authority.py`
- Test: `tests/persistence/postgres/test_strategy_opportunity_authority.py`

**Interfaces:**
- Produces: immutable `PreStrategyRiskState`, `StrategyOpportunity`, concrete `StrategyOpportunityAuthority`, `ContinuousStrategyOpportunityResolver`, and `HistoricalStrategyOpportunityResolver`.

- [ ] **Step 1: Write contract rejection tests**

```python
with pytest.raises(ValueError, match="pre-Strategy Risk"):
    StrategyOpportunityInput.create(
        risk_state_reference=RuntimeArtifactReference(
            "COMPLETE_ACCOUNT_RISK_DECISION", risk_id, risk_hash
        ),
        **valid_values,
    )
```

Accept only `PRE_STRATEGY_RISK_STATE` and explicitly compatible historical
projection kinds. Require Candidate, Signal, Forecast, Context, Risk, model,
Strategy Version, symbol and DecisionTime coherence.

- [ ] **Step 2: Implement immutable domain owners**

Compose account/position/restriction/liquidity/risk-limit references without
copying their business facts. Include `risk_allows_action`, sorted reason codes,
availability and exact source hashes.

- [ ] **Step 3: Add forward-only migration 093 and repository**

Create two append-only content-addressed tables with no-update/no-delete
triggers and natural uniqueness. Repository reload must reconstruct and verify
canonical hashes.

- [ ] **Step 4: Wire concrete resolvers into both adapters**

Continuous and Historical resolvers reload the exact PostgreSQL Candidate,
Signal/Forecast locator receipts, Context, pre-risk, model and Strategy owners.
Drift, symbol mismatch, candidate-set mismatch, future availability or stale
Strategy version fails closed.

- [ ] **Step 5: Run parity/PostgreSQL tests and commit**

Run focused Strategy runtime, migration, repository and Continuous/Historical
parity tests. Commit with message `feat: wire postgres strategy opportunities`.

### Task 5: FreeData Daily Alpha Freeze and Automatic Settlement

**Files:**
- Modify: `src/market_regime_alpha/application/continuous_research/free_data_runtime.py`
- Modify: `src/market_regime_alpha/application/continuous_research/scheduler.py`
- Modify: `src/market_regime_alpha/application/shadow_research/free_data_settlement.py`
- Modify: `src/market_regime_alpha/cli/continuous_research.py`
- Test: `tests/persistence/postgres/test_free_data_stateful_runtime.py`
- Test: `tests/cli/test_continuous_research_cli.py`

**Interfaces:**
- Consumes: evidence-gated Alpha/Candidate policy, canonical stage owners and the existing settlement operator.
- Produces: immutable daily prediction snapshot and a due-settlement child operation inside the existing Continuous control plane.

- [ ] **Step 1: Write inactive-dependency tests**

Assert a completed tick records
`EVIDENCE_DEPENDENCY_NOT_SATISFIED`, validated challenger inactive and
conditional Strategy inactive while still preserving incumbent research output.

- [ ] **Step 2: Freeze prediction lineage**

Bind run/tick/code/config/provider/dataset/universe/features/context/Candidate/
Signal/Forecast/Strategy diagnostics into a content-addressed PostgreSQL-backed
snapshot. Replaying the same tick must return the same identity.

- [ ] **Step 3: Schedule settlement through the existing control plane**

At the first due tick after the canonical next session has sufficient data,
invoke the existing `FreeDataSettlementOperator` idempotently. Do not add a
scheduler or Daily Runtime. Record OPEN, 09:45, 10:00, 10:30, 11:30, CLOSE,
MFE/MAE, barriers, suspension/limit/tradability and execution proxy outcomes.

- [ ] **Step 4: Verify immutability/recovery/idempotency**

Test same-tick replay, crash before/after owner commit, duplicate settlement,
future-data rejection, one Evidence identity and prediction-before-outcome.

- [ ] **Step 5: Run focused tests and commit**

Commit with message `feat: run immutable daily alpha research`.

### Task 6: Architecture Convergence and Legacy Retirement

**Files:**
- Create: `docs/references/Architecture-Convergence-Inventory.md`
- Create: `tests/architecture/test_canonical_boundaries.py`
- Modify/delete only modules proven unused by import/runtime/persistence inventory.

**Interfaces:**
- Produces: consumer/authority/disposition inventory and lightweight import boundary tests.

- [ ] **Step 1: Generate the consumer/authority inventory**

Classify `dividend_t`, `daily_research`, `daily_decision`, old backtesting,
`legacy`, `migration/legacy`, MR1/MR2, Tencent compatibility and large owner
modules as KEEP/SIMPLIFY/MERGE/REFACTOR/MIGRATE/RETIRE/DELETE/
COMPATIBILITY_ONLY using actual imports and entrypoints.

- [ ] **Step 2: Add dependency boundary tests**

Reject Continuous→legacy runtime, Feature→Strategy, research helper→Position
mutation, migration legacy→canonical execute, Strategy→post-Portfolio Risk and
legacy Candidate/backtest→canonical write imports.

- [ ] **Step 3: Retire only zero-consumer runtime paths**

Delete duplicate execute/write entrypoints only after tests and `rg` prove no
canonical consumer. Migrate valuable pure quant kernels before deleting their
legacy host. Preserve replay/migration facades as `COMPATIBILITY_ONLY`.

- [ ] **Step 4: Decompose directly affected God modules**

Extract cohesive pure kernels/owner resolvers from files modified by Tasks 1–5
without changing Runtime, Authority, schema or identity semantics. Avoid empty
Service/Repository wrappers.

- [ ] **Step 5: Run architecture tests and commit**

Commit inventory/boundaries separately from proven retirements and refactors.

### Task 7: Final Evidence, Validation and Draft PR

**Files:**
- Modify: `docs/status/Current-State.md`
- Modify: `docs/status/Capability-Matrix.md`
- Modify: `docs/status/Gap-Register.md`
- Modify: `docs/status/Roadmap.md`
- Modify: `docs/research/Negative-and-Inconclusive-Results.md` when campaigns are negative/inconclusive.

- [ ] **Step 1: Update every status from executable evidence**

Record commands as `PASS`, `FAIL`, `NOT_RUN` or `BLOCKED`; never infer proof
from implementation. Record all gates and the final evidence ceiling.

- [ ] **Step 2: Run required focused and static validation**

Run docs validation, targeted unit/PostgreSQL/replay tests, Ruff, mypy, build and
`git diff --check`. Run full pytest only when cost/risk warrants it and report
`NOT_RUN` otherwise.

- [ ] **Step 3: Review commits and protected scope**

Inspect staged/unstaged files before each commit; verify `.idea/modules.xml`,
credentials, artifact roots and unrelated files are absent.

- [ ] **Step 4: Push and open Draft PR**

Push `agent/alpha-daily-arch-convergence-01` and create a Draft PR containing
baseline/final SHA, migration head, tests, campaign results, architecture
dispositions, CI state, remaining gaps and evidence ceiling.
