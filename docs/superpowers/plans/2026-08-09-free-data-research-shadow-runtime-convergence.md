# Free-Data Research and Shadow Runtime Convergence Implementation Plan

> **Status:** ROADMAP
> **Authority:** Execution plan for the free-data Runtime convergence
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-09
> **Supersedes:** None
> **Superseded By:** None
> **Related Documents:** ../specs/2026-08-09-free-data-research-shadow-runtime-convergence-design.md, ../../status/Current-State.md
> **Code Evidence:** Baseline `fee02f68d3d3e4745ec25920f022a2436e4ae08a`; `src/market_regime_alpha`; `tests`

> **For agentic workers:** Execute inline in dependency order with focused tests and reviewable checkpoint commits.

**Goal:** Deliver one PostgreSQL-only executable Continuous Runtime that uses the explicit BaoStock/Tencent free-data profile, distinguishes Research/Shadow/Production authority, and reaches an immutable Daily Summary despite stage-level missing research evidence.

**Architecture:** Continuous remains the sole all-day owner. Existing FreeData and Controlled services remain bounded execution owners; new code adds authority-mode propagation, Registry admission, stage-result projection, and an account-neutral Summary inside DecisionSystem. Production retains the existing strict Decision path.

**Tech Stack:** Python 3.12, dataclasses, PostgreSQL 16, psycopg, pytest, Ruff, mypy, uv.

## Global Constraints

- Default free-data profile is BaoStock history/status plus Tencent quote/minute.
- No automatic Provider fallback or silent source substitution.
- Free data remains `FREE_DATA_EXPLORATORY` / `PIT_INCOMPLETE` or weaker.
- PostgreSQL is the only Runtime and Journal writer.
- Research and Shadow cannot create Order, Fill, Broker, or Position mutation.
- Production qualification and Entry remain fail-closed.
- Historical commands, receipts, and Artifacts remain readable and immutable.

---

### Task 1: Runtime authority contract and persisted propagation

**Files:**
- Modify: `src/market_regime_alpha/platform/runtime_governance.py`
- Modify: `src/market_regime_alpha/application/continuous_research/contracts.py`
- Modify: `src/market_regime_alpha/application/continuous_research/ports.py`
- Modify: `src/market_regime_alpha/application/continuous_research/scheduler.py`
- Test: `tests/platform/test_runtime_governance.py`
- Test: `tests/application/continuous_research/test_contracts.py`
- Test: `tests/application/continuous_research/test_scheduler.py`

**Produces:** `RuntimeAuthorityMode`, exact `RuntimePurpose` mapping, and mode-bound run/Tick/child identities.

- [ ] Add failing tests for the three exact mappings and V1 Continuous command compatibility as Research.
- [ ] Add mode to V2 command/Tick serialization and deterministic identities.
- [ ] Propagate mode into `ChildExecutionRequest` and scheduled Tick creation.
- [ ] Verify focused tests and commit the bounded contract change.

### Task 2: Account-neutral immutable Research/Shadow Summary

**Files:**
- Create: `src/market_regime_alpha/application/decision_system/research_summary.py`
- Modify: `src/market_regime_alpha/application/decision_system/postgres_repository.py`
- Modify: `src/market_regime_alpha/application/decision_system/replay.py`
- Create: `src/market_regime_alpha/persistence/postgres/migrations/029_research_runtime_summary.sql`
- Create: `tests/application/decision_system/test_research_summary.py`
- Create: `tests/application/decision_system/test_research_summary_postgres.py`

**Produces:** `ResearchStageEvidence`, `ResearchDailySummary`, immutable revision rules, PostgreSQL Reader/writer, and deterministic replay.

- [ ] Write contract tests for complete and `DATA_INSUFFICIENT` stage prefixes, ceiling monotonicity, original immutability, and correction lineage.
- [ ] Implement canonical contracts and outcome derivation without account or execution dependencies.
- [ ] Add append-only PostgreSQL tables, fencing-aware inserts, exact indexes/constraints/triggers, and repository schema checks.
- [ ] Add replay tests proving identical stage/Summary identities and no network or trading ports.
- [ ] Verify focused tests and commit.

### Task 3: Mode-aware Decision Model Governance

**Files:**
- Modify: `src/market_regime_alpha/application/decision_system/runtime.py`
- Modify: `src/market_regime_alpha/application/decision_system/replay.py`
- Test: `tests/application/decision_system/test_runtime.py`
- Test: `tests/application/decision_system/test_runtime_governance.py`

**Produces:** exact Research/Shadow/Production selection requests and separation of Research Summary from the existing Production account closure.

- [ ] Write failing tests showing Research and Shadow use their own purposes and preserve rejected receipts in Summary.
- [ ] Replace the hard-coded purpose with the mode mapping and require `production_authorized` only for Production.
- [ ] Route Research/Shadow to the account-neutral Summary service; retain the current account/reconciliation/portfolio/risk path for Production.
- [ ] Test that caller qualification remains ignored and Production rejection still blocks.
- [ ] Verify focused tests and commit.

### Task 4: Free-data staged execution and no-fallback provider boundary

**Files:**
- Modify: `src/market_regime_alpha/application/free_data_operation/contracts.py`
- Modify: `src/market_regime_alpha/application/free_data_operation/service.py`
- Modify: `src/market_regime_alpha/application/continuous_research/composition.py`
- Test: `tests/application/free_data_operation/test_service.py`
- Test: `tests/application/continuous_research/test_composition.py`

**Produces:** pre-Decision history preparation, DecisionTime status/quote freeze, exact profile lineage, and failed Attempt translation without fallback.

- [ ] Add failing tests that history can freeze before DecisionTime while quote cannot, and that the semantic command stays stable.
- [ ] Split FreeData preparation around the existing DailyLoop staged methods without introducing another acquisition client.
- [ ] Bind BaoStock/Tencent product contracts and provider profile to the validated Evidence payload.
- [ ] Test BaoStock failure, Tencent failure, late quote, future data, and absence of any alternate-provider call.
- [ ] Verify focused tests and commit.

### Task 5: Governed research-stage projection over the existing Controlled execution

**Files:**
- Create: `src/market_regime_alpha/application/continuous_research/research_stages.py`
- Modify: `src/market_regime_alpha/application/controlled_operation/runtime_configuration.py`
- Modify: `src/market_regime_alpha/application/continuous_research/composition.py`
- Modify: `src/market_regime_alpha/application/state_system/runtime.py`
- Test: `tests/application/continuous_research/test_research_stages.py`
- Test: `tests/application/state_system/test_runtime.py`

**Produces:** one ordered set of actual/missing State evidence and Registry admission receipts for every model that executes.

- [ ] Add tests for Market/Theme/Capital/Candidate/Signal/Forecast slot selection using the mode purpose.
- [ ] Verify selected model/version/configuration against the existing Controlled executable catalog before invoking Controlled.
- [ ] Project ETF absence and missing Theme/Capital evidence as immutable `DATA_INSUFFICIENT` stages.
- [ ] Treat Dynamic Pool/evidence-ceiling joins as deterministic configured policies, not Registry models.
- [ ] Propagate missing stages to Candidate/Signal/Forecast without fabricating data.
- [ ] Verify focused tests and commit.

### Task 6: Executable Continuous composition root and CLI

**Files:**
- Create: `src/market_regime_alpha/application/continuous_research/canonical_runtime.py`
- Modify: `src/market_regime_alpha/cli/continuous_research.py`
- Modify: `pyproject.toml`
- Create: `tests/application/continuous_research/test_canonical_runtime.py`
- Modify: `tests/cli/test_continuous_research_cli.py`

**Produces:** `continuous-research run-due` that constructs RepositoryFactory, schedule runner, provider, bounded child composition, Summary service, and replayable result.

- [ ] Add a PostgreSQL end-to-end failing test for one due Research Tick reaching Summary.
- [ ] Implement one composition root that calls FreeData/Controlled once and records exact existing Artifact/receipt references.
- [ ] Add Shadow and unqualified Production end-to-end cases with explicit safety declarations.
- [ ] Add `NO_MATERIAL_CHANGE` identity reuse, restart/resume, crash-after-child, and stale-fence tests.
- [ ] Verify focused tests and commit.

### Task 7: Replay, reports, documentation, and complete gates

**Files:**
- Modify: `src/market_regime_alpha/application/continuous_research/replay.py`
- Modify: `src/market_regime_alpha/application/continuous_research/report.py`
- Modify: `docs/status/Current-State.md`
- Modify: `docs/status/Capability-Matrix.md`
- Modify: `docs/status/Gap-Register.md`
- Create or modify: delivery evidence under `docs/delivery/`
- Test: `tests/application/continuous_research/test_replay.py`
- Test: `tests/application/continuous_research/test_report.py`

**Produces:** deterministic mode/Summary replay, accurate operator report, and code-evidence-aligned status documents.

- [ ] Add replay/report tests for mode, stage results, selection receipt IDs, Summary identity, ceiling, and safety fields.
- [ ] Update factual documents without claiming live Provider or production qualification evidence.
- [ ] Run `uv sync --frozen --extra dev --extra postgres`.
- [ ] Run docs link check, full real-PostgreSQL pytest, Ruff, mypy, package build, and `git diff --check`.
- [ ] Review all staged/unstaged changes, exclude generated or unrelated files, and commit the final checkpoint.
