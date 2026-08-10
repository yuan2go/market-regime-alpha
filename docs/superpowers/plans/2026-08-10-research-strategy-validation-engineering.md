# Research and Strategy Validation Engineering Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **Status:** ROADMAP
> **Authority:** Execution plan for the approved 2026-08-10 engineering completion scope
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-10
> **Baseline:** `origin/main@66d9e8cac5015684a179de18c854ab4991423e87`

**Goal:** Complete the reusable Research/OOS/Entry/Holding-Exit/Strategy-Shadow/Admission engineering machines while all unavailable real-evidence gates remain fail-closed.

**Architecture:** Extend Research Panel V2 with an immutable enrichment, add one validation bounded context over existing PIT/Target/Governance authorities, and add a Strategy Shadow workflow attached to the existing Continuous Runtime. Preserve real trading authorities and historical Readers.

**Tech Stack:** Python 3.12 dataclasses and deterministic Decimal/statistical routines, PostgreSQL 16/psycopg, immutable JSON artifacts, pytest, Ruff, mypy, uv/build.

## Global Constraints

- `ENGINEERING_COMPLETE != VALIDATED != QUALIFIED != PRODUCTION_AUTHORIZED`.
- No second Runtime, State, Outcome, Governance, Order, Fill, Broker or real Position authority.
- Formal OOS requires real Formal PIT; fixture and exploratory runs remain engineering-only.
- Canonical Entry remains blocked and `entry_qualified=false`.
- Full repository validation runs after production implementation and focused smoke checks.

---

### Task 1: Canonical factor extraction and Panel enrichment

**Files:**
- Create: `src/market_regime_alpha/application/research_validation/factor_extraction.py`
- Create: `src/market_regime_alpha/application/research_validation/postgres_repository.py`
- Modify: `src/market_regime_alpha/application/research_evaluation/panel_v2.py`
- Modify: `src/market_regime_alpha/application/shadow_research/operations.py`
- Test: `tests/application/research_validation/test_factor_extraction.py`

**Interfaces:**
- Consumes: `VerifiedMarketDataDataset`, `VerifiedFeatureBundleV2`, canonical State/Pool/Candidate/Signal/Forecast artifacts, `FrozenResearchPanelV2`.
- Produces: `FactorExposure`, `ResearchPanelEnrichment`, `extract_panel_enrichment(...)`, append-only repository registration.

- [ ] Copy all scalar source values, explicit missingness, gates and ID/hash/config/model lineage without recomputation.
- [ ] Enforce complete factor-family coverage declarations and an exploratory authority ceiling.
- [ ] Integrate optional verified enrichment inputs into `ResearchShadowOperations.build_evaluation`.
- [ ] Run `uv run pytest -q tests/application/research_validation/test_factor_extraction.py` and `git diff --check`.

### Task 2: Ablation and liquidity/capacity engines

**Files:**
- Create: `src/market_regime_alpha/application/research_validation/ablation.py`
- Create: `src/market_regime_alpha/application/research_validation/liquidity_capacity.py`
- Test: `tests/application/research_validation/test_ablation.py`
- Test: `tests/application/research_validation/test_liquidity_capacity.py`

**Interfaces:**
- Consumes: frozen enriched row observations and targeted outcomes.
- Produces: versioned `AblationProtocol/Run/Metric`, `LiquidityCapacityProtocol/Assessment`.

- [ ] Implement standard and arbitrary deletion variants with deterministic IC/Rank IC/Top-K/Spread/Hit/Return/MFE/MAE/Turnover/Drawdown/Overlap/Lift metrics.
- [ ] Implement observed ADV/amount/turnover/status facts and identified participation/slippage/impact/fillability/capacity assumptions.
- [ ] Reject Formal OOS/qualification claims and calibrated parameter labels without bound evidence.
- [ ] Run the two focused test files and `git diff --check`.

### Task 3: Historical Path Sample Authority and calibration

**Files:**
- Create: `src/market_regime_alpha/application/research_validation/samples.py`
- Create: `src/market_regime_alpha/application/research_validation/calibration.py`
- Modify: `src/market_regime_alpha/forecasting/sample_provider.py`
- Test: `tests/application/research_validation/test_samples.py`
- Test: `tests/application/research_validation/test_calibration.py`

**Interfaces:**
- Produces: `HistoricalSampleDataset`, registry transition/Reader/replay, `RegisteredPathForecastSampleProvider`, and Calibration Protocol/Fit/Artifact/Evaluation.

- [ ] Bind every sample to source outcome, Target, PIT lineage, DecisionTime and AvailabilityTime; never derive samples from the current Signal.
- [ ] Load only historical samples available at forecast DecisionTime and preserve qualification ceiling in batch reasons/limitations.
- [ ] Implement Platt/logistic, isotonic and binning fits with disjoint fit/validation/OOS sample IDs and Brier/LogLoss/reliability/ECE/coverage.
- [ ] Keep `calibrated=false` absent qualified calibration evidence.
- [ ] Run focused sample/forecast/calibration tests.

### Task 4: Formal evaluation/OOS and Entry qualification

**Files:**
- Create: `src/market_regime_alpha/application/research_validation/formal_evaluation.py`
- Create: `src/market_regime_alpha/application/research_validation/entry_qualification.py`
- Test: `tests/application/research_validation/test_formal_evaluation.py`
- Test: `tests/application/research_validation/test_entry_qualification.py`

**Interfaces:**
- Produces: frozen split/walk-forward protocols, target-derived purge/embargo folds, engineering/formal run results, Entry Research assessments/evaluations/protocol/evidence.

- [ ] Implement Train/Validation/Locked OOS, walk-forward, purging, target-label-derived embargo, deterministic bootstrap CI, multiple-testing adjustment, sensitivity and requested slices.
- [ ] Block `FORMAL_OOS` without existing PIT Authority evidence at `REAL_FORMAL_PIT`.
- [ ] Compare Candidate-only, Candidate+Signal, Candidate+Forecast and Candidate+Intraday without changing Canonical Entry.
- [ ] Keep Entry qualification false until all formal protocol requirements are bound.
- [ ] Run focused evaluation and Entry tests.

### Task 5: Holding/Exit validation and Strategy Shadow workflow

**Files:**
- Create: `src/market_regime_alpha/application/strategy_shadow/contracts.py`
- Create: `src/market_regime_alpha/application/strategy_shadow/engine.py`
- Create: `src/market_regime_alpha/application/strategy_shadow/postgres_repository.py`
- Create: `src/market_regime_alpha/application/strategy_shadow/operations.py`
- Test: `tests/application/strategy_shadow/test_engine.py`
- Test: `tests/persistence/postgres/test_strategy_shadow.py`

**Interfaces:**
- Consumes: existing Runtime/Research Shadow references and immutable market observations.
- Produces: separate Shadow Entry/Fill/Position/Holding/Exit/Outcome objects, CAS sessions, events, incidents, drift and daily reports.

- [ ] Implement fixed-time, reversal, Market/Theme/Capital deterioration, trailing/protection and multi-horizon rules.
- [ ] Implement schedule/run/resume/recovery/replay/settlement/report with no real execution repository imports or mutations.
- [ ] Persist append-only objects/events and versioned session projection in PostgreSQL.
- [ ] Emit Holding/Exit validation evidence that remains unvalidated for fixtures.
- [ ] Run focused domain and real PostgreSQL recovery/replay tests.

### Task 6: Production Admission and authority-boundary fixes

**Files:**
- Create: `src/market_regime_alpha/application/research_validation/admission.py`
- Create: `src/market_regime_alpha/application/continuous_research/runtime_evidence.py`
- Create: `src/market_regime_alpha/application/continuous_research/postgres_runtime_evidence.py`
- Modify: `src/market_regime_alpha/application/shadow_research/operations.py`
- Modify: `src/market_regime_alpha/cli/continuous_research.py`
- Modify: `src/market_regime_alpha/universe/operational.py`
- Modify: `src/market_regime_alpha/application/free_data_operation/builders.py`
- Modify: `src/market_regime_alpha/application/state_system/free_data_composition.py`
- Test: `tests/application/research_validation/test_admission.py`
- Test: `tests/application/shadow_research/test_attestation_authority.py`
- Test: `tests/universe/test_operational_universe.py`

**Interfaces:**
- Produces: unified admission decision, durable Run/Tick clock/origin evidence, Operational Universe V2 policy binding.

- [ ] Evaluate all eleven Governance floors with only blocked/review/authorized states and no automatic promotion.
- [ ] Persist runtime clock/origin from the executable run-due path and make Attestation load it instead of trusting settlement caller fields.
- [ ] Bind free-data Operational Universe V2 and StateSeries to the exact DailyUniversePolicy ID/hash/version while retaining V1 Readers.
- [ ] Run focused authority-boundary tests.

### Task 7: PostgreSQL migrations, composition and documentation

**Files:**
- Create: `src/market_regime_alpha/persistence/postgres/migrations/043_research_validation_authority.sql`
- Create: `src/market_regime_alpha/persistence/postgres/migrations/044_strategy_shadow_validation.sql`
- Create: `src/market_regime_alpha/persistence/postgres/migrations/045_runtime_authority_evidence.sql`
- Modify: `src/market_regime_alpha/persistence/postgres/schema.py`
- Modify: status, capability, gap, architecture, runbook and delivery records.

**Interfaces:**
- Produces: fresh/incremental migration head 45, expected-table verification and current-state documentation.

- [ ] Add indexes, foreign keys, canonical payload checks, append-only triggers and CAS guards.
- [ ] Verify fresh/incremental migration, replay, idempotency, tamper rejection and no authority inflation on PostgreSQL 16.
- [ ] Update `docs/README.md`, Current State, Capability Matrix, Gap Register, architecture/runbook/delivery evidence.
- [ ] Run focused PostgreSQL and docs-link tests.

### Task 8: Consolidated validation, review and publication

**Files:**
- Modify: `scripts/run_engineering_verification.py` only if the new head/claims require it.
- Create/update: SHA-bound Engineering Verification Record after the clean commit.

**Interfaces:**
- Produces: exact command results, semantic commits, pushed branch and Draft PR.

- [ ] Run `uv sync --frozen --extra dev --extra postgres`.
- [ ] Run full PostgreSQL-backed `uv run pytest`, `uv run ruff check .`, `uv run mypy`, `uv run python -m build`, docs checks and `git diff --check`.
- [ ] Review the complete diff against this specification and authority ceilings; fix all actionable findings.
- [ ] Commit, run clean-SHA verification, push, create Draft PR, and report CI as `CI_NOT_RUN` unless actually observed.
