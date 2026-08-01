# Claude Code Prompt — Production Decision Lifecycle

> **Status:** CURRENT_SPECIFICATION  
> **Authority:** Implementation prompt for Claude Code  
> **Owner:** Market Regime Alpha maintainers  
> **Last Updated:** 2026-08-01  
> **Related Documents:** ../architecture/10-Production-Decision-Lifecycle.md, ../architecture/decisions/ADR-004-Production-Decision-Lifecycle-Organization.md, ../roadmap/work-packages/WP-PDL-Production-Decision-Lifecycle.md, ../specs/Production-Decision-Lifecycle-Requirements.md

Use the following prompt as the implementation instruction for Claude Code.

---

You are a senior Python software architect, domain-modeling specialist, quantitative trading systems engineer and codebase implementation lead.

Repository:

- `https://github.com/yuan2go/market-regime-alpha`
- target branch: `main`
- create development branch: `feat/production-decision-lifecycle`

## Project background

The repository already implements an A-share quantitative research foundation including SourceManifest, point-in-time Universe, Feature contracts, immutable artifacts, a recoverable Daily Runtime Journal, Platform V2 research contracts, Market Regime, Theme Rotation, Capital Evolution, Candidate Discovery, deterministic replay and basic model/experiment governance.

The goal is not to create a second project and not to implement unattended live trading. The goal is to incrementally complete the existing architecture into a human-in-the-loop decision-support lifecycle:

```text
Daily Evidence
→ Research Layer
→ Signal
→ Multi-Horizon Path Forecast
→ Trading Opportunity
→ Trading Thesis
→ Portfolio and Risk
→ Manual Trade Record
→ Position Snapshot
→ Holding and Exit
→ Attribution and Governance
```

## Mandatory engineering organization

1. Continue inside the existing repository and Python package.
2. Use a modular monolith with explicit bounded contexts.
3. Do not place the new lifecycle inside `DailyLoopRunner`, `CapitalEvolution`, `CandidateDiscovery` or a new God Object.
4. Follow the existing Platform V2 layer model.
5. Implement `signals`, `forecasting`, `decision`, `portfolio`, `execution`, `position` and `evaluation` as separate ownership boundaries.
6. Keep cross-domain orchestration under `application`.
7. The first execution authority is manual recording and simulation only.
8. Do not implement LIVE_ORDER, QMT, PTrade or unattended broker mutation.
9. A future broker adapter may be separately deployed, but it is not part of this work.

## Required code scan

Read actual code and call chains before planning changes. Do not rely on README alone.

Read at minimum:

### Architecture and status

- `README.md`
- `docs/README.md`
- `docs/status/Current-State.md`
- `docs/status/Capability-Matrix.md`
- `docs/status/Gap-Register.md`
- `docs/architecture/01-Domain-Boundaries.md`
- `docs/architecture/09-Platform-Architecture-V2.md`
- `docs/architecture/10-Production-Decision-Lifecycle.md`
- `docs/architecture/decisions/`
- `docs/specs/Production-Decision-Lifecycle-Requirements.md`
- `docs/roadmap/work-packages/WP-PDL-Production-Decision-Lifecycle.md`
- `docs/audit/Production-Decision-Lifecycle-Gap-Analysis.md`

### Core contracts

- `pyproject.toml`
- `src/market_regime_alpha/core/`
- `src/market_regime_alpha/data/contracts.py`
- `src/market_regime_alpha/data/source_manifest.py`
- `src/market_regime_alpha/evidence/`
- `src/market_regime_alpha/universe/`
- `src/market_regime_alpha/features/`

### Platform and governance

- `src/market_regime_alpha/platform/architecture_v2.py`
- `src/market_regime_alpha/platform/contracts.py`
- `src/market_regime_alpha/platform/model_registry.py`
- `src/market_regime_alpha/platform/experiment_governance.py`

### Current runtime

- `src/market_regime_alpha/application/daily_loop/`
- `src/market_regime_alpha/application/research_layer/`
- `src/market_regime_alpha/daily_decision/`
- `scripts/run_exploratory_daily_loop.py`
- `scripts/run_research_layer.py`

### Research Layer

- `src/market_regime_alpha/research/platform_v2/`
- `src/market_regime_alpha/research/market_regime/`
- `src/market_regime_alpha/research/theme_rotation/`
- `src/market_regime_alpha/research/capital_evolution/`
- `src/market_regime_alpha/research/candidate_discovery/`
- `src/market_regime_alpha/strategies/entry/`

### Target ownership seams

- `src/market_regime_alpha/signals/`
- `src/market_regime_alpha/forecasting/`
- `src/market_regime_alpha/decision/`
- `src/market_regime_alpha/portfolio/`
- `src/market_regime_alpha/execution/`
- `src/market_regime_alpha/position/`
- `src/market_regime_alpha/evaluation/`

### Compatibility and tests

- `src/market_regime_alpha/daily_research/`
- `src/market_regime_alpha/legacy/`
- `src/market_regime_alpha/dividend_t/`
- `tests/application/daily_loop/`
- `tests/research/platform_v2/`
- `tests/platform/`
- `tests/evidence/`
- `.github/workflows/ci.yml`

## Mandatory work cycle

Follow this loop without skipping stages:

```text
scan code
→ build current-state model
→ test design assumptions
→ create implementation plan
→ make incremental changes
→ run tests
→ fix failures
→ run regression
→ update documentation
→ report results
```

## Prohibited actions

- Do not develop after reading only README or architecture prose.
- Do not create duplicate StableId, SemanticTime, SourceManifest, Feature, Candidate, Model Registry, Experiment Governance or DailyRun systems.
- Do not create a second data or position authority.
- Do not weaken `ArtifactEnvelope` authority ceilings.
- Do not label model scores as probabilities without calibration.
- Do not describe Capital Evolution as hidden institutional intent.
- Do not convert CandidateSet into an order list.
- Do not change the fixed MR1 next-session 10:30 semantics in place.
- Do not create temporary compatibility layers that conceal domain conflicts.
- Do not bypass SourceManifest, PIT Universe, Eligibility or Risk Authority.
- Do not modify unrelated modules.
- Do not delete existing functionality to simplify the implementation.
- Do not add LIVE_ORDER or automated broker calls.
- Do not promote models automatically.
- Do not skip or weaken tests to make changes pass.

## Phase 0 — Code facts and design reconciliation

1. Inspect all required code and actual imports/call chains.
2. Create a current-state map of modules, identities, artifacts, repositories, authorities and state machines.
3. Compare code facts with the target architecture.
4. Classify each target capability as implemented, partial, missing or conflicting.
5. If documentation conflicts with code, use code as truth and record the difference.
6. Update `docs/audit/Production-Decision-Lifecycle-Gap-Analysis.md` only when new code evidence changes its conclusions.
7. Produce a phase plan before editing runtime code.

Do not re-create architecture documents that already exist.

## Phase 1 — Operational Research Bridge

Goal: safely transform verified DailyLoop evidence into Platform V2 ResearchInputBundle without copying authority.

Suggested paths:

```text
src/market_regime_alpha/application/operational_research/
scripts/run_operational_research.py
tests/application/operational_research/
```

Requirements:

- verify SourceManifest and artifact checksums;
- verify DecisionTime and AvailabilityTime;
- reuse existing Universe and Eligibility;
- preserve source Artifact IDs and hashes;
- create typed market, theme, ETF and symbol observations;
- fail closed on missing mapping or required observation;
- never create a LIVE fixture alias;
- never raise DataEligibility;
- run and replay deterministically;
- do not add the new pipeline directly to `DailyLoopRunner`.

Required tests:

- Daily artifact to ResearchInputBundle;
- complete lineage preservation;
- late evidence rejection;
- missing theme/capital evidence blocks;
- duplicate run returns the same artifact;
- replay performs no network access.

## Phase 2 — Durable Model Registry and Experiment Governance

Goal: make current governance rules recoverable and concurrency safe.

Requirements:

- define repository protocols;
- retain existing domain validation and in-memory adapters;
- add SQLite adapters first;
- design PostgreSQL-compatible contracts without forcing premature production migration;
- persist lifecycle transitions and evidence references;
- persist experiment protocols and access budgets;
- use optimistic concurrency or equivalent compare-and-set;
- reject identity conflicts and non-contiguous restore history;
- do not allow persistence code to bypass domain rules.

Required tests:

- restart recovery;
- duplicate registration;
- concurrent transition;
- concurrent validation/sealed access;
- corrupt/non-contiguous history rejection;
- in-memory and SQLite contract parity.

## Phase 3 — Signal Engine and PathForecast

Goal: add replayable timing and path-risk research without creating a trade.

Signal V1 scope:

- price action;
- volume confirmation;
- trend confirmation;
- VWAP context;
- overheat state.

Requirements:

- add versioned signal model/config/artifact/reader/replay;
- consume only evidence available by DecisionTime;
- use MACD, moving averages and other indicators only as features, not separate authority layers;
- preserve current SignalSnapshot boundary where compatible;
- add a separate PathForecast instead of changing NextSessionForecast semantics;
- reuse EntryPathTarget contracts;
- include horizon, barriers, MFE, MAE, quantiles and calibration status;
- do not emit probability when uncalibrated;
- preserve daily-bar dual-touch ambiguity.

Required tests:

- time leakage rejection;
- missing feature behavior;
- signal reason codes;
- dual-touch ambiguity;
- missing future bar;
- deterministic publication and replay;
- no decision/order authority in output.

## Phase 4 — TradingOpportunity and TradingThesis

Goal: create the explicit boundary between research and human trade consideration.

Add under `decision/`:

- `TradingOpportunity`;
- `OpportunityState`;
- `TradingThesis`;
- `ThesisState`;
- `InvalidationCondition`;
- repository protocols;
- application services.

Requirements:

- opportunity binds exact CandidateSet, SignalSnapshot, PathForecast, DecisionTime, model and configuration;
- opportunity has deterministic/idempotent identity and expiry;
- expired or evidence-mismatched opportunity cannot become a thesis;
- thesis records rationale, evidence, invalidation, actor and version;
- invalidated thesis cannot authorize ADD;
- every transition appends an audit event;
- use optimistic concurrency.

Required tests:

- state transition table;
- expiry;
- duplicate command;
- concurrent confirmation;
- evidence mismatch;
- invalidation and close.

## Phase 5 — Portfolio and Risk Authority

Goal: construct target positions and apply independent hard-risk rules.

Requirements:

- add `RiskBudget`, `PortfolioConstraint`, `TargetPosition`, `PortfolioDecision` and `RiskDecision`;
- consume active theses, current positions and available cash;
- enforce gross exposure, symbol limit, theme limit, liquidity/capacity, T+1 and loss budget;
- persist exact limit snapshot and reason codes;
- fail closed on risk failure or timeout;
- output only simulation/manual-confirmation semantics;
- prevent strategy code from overriding rejection.

Required tests:

- insufficient cash;
- symbol/theme concentration;
- market exposure ceiling;
- T+1 and available quantity;
- conflicting theses;
- risk timeout;
- rejection cannot create approved intent.

## Phase 6 — Manual Execution and Position Authority

Goal: create append-only manual execution records and positions derived from fills.

Add under `execution/`:

- `ManualTradeRecord`;
- manual order state;
- `Fill`;
- correction/deviation contracts;
- repository protocols.

Add under `position/`:

- `PositionSnapshot`;
- position lot/state;
- `PositionProjector`;
- reconciliation contracts.

Requirements:

- fills are append-only;
- correction creates a new record;
- duplicate fill/idempotency key has no second effect;
- partial fill, cancellation and rejection remain explicit;
- position quantity, cost and PnL rebuild from fills;
- no plan or recommendation creates actual position;
- mismatch enters reconciliation-required state and blocks new exposure.

Required tests:

- full and partial fill;
- duplicate fill;
- cancellation;
- correction;
- long position open/reduce/close;
- restart and full projection rebuild;
- reconciliation mismatch.

## Phase 7 — Holding, Exit and Attribution

Goal: complete open-position management and controlled feedback.

Requirements:

- add independent HoldingAssessment and ExitAssessment;
- use current thesis, authoritative position and new market/theme/capital/signal evidence;
- support HOLD, ADD, REDUCE, WAIT and DATA_INSUFFICIENT;
- support NO_ACTION, WAIT, EXIT and DATA_INSUFFICIENT;
- require fresh portfolio/risk approval for ADD;
- prohibit ADD after thesis invalidation;
- add TradeOutcome, MFE, MAE, capture ratio and layer attribution;
- distinguish selection, entry, holding, exit, sizing and execution effects;
- publish immutable evaluation evidence;
- never mutate model configuration automatically.

Required tests:

- holding/exit independence;
- invalidated thesis;
- T+1 unavailable exit;
- closed-position lifecycle;
- attribution identities and hashes;
- rolling scorecard protocol;
- no automatic lifecycle promotion.

## Database and persistence rules

1. Immutable artifacts remain the evidence authority.
2. SQLite is the first durable operational adapter for local and test use.
3. Repository contracts must permit later PostgreSQL adapters.
4. Do not duplicate full artifact semantics into mutable tables.
5. Every mutable aggregate has a version.
6. Every command supports an idempotency key or deterministic identity.
7. Every manual action records actor, reason and time.
8. Every migration has tests and a rollback procedure.
9. Do not alter current `daily_runs`, `stage_receipts` or `acquisition_stage_receipts` semantics.
10. Fill, audit and lifecycle transition records are append-only.

## Dependency constraints

1. `core`, `data` and `evidence` do not depend on upper layers.
2. `research` does not depend on decision, portfolio, execution or position.
3. `signals` consumes verified candidate and evidence contracts only.
4. `decision` does not write actual position state.
5. `execution` does not recompute research.
6. `position` does not fetch provider data directly.
7. `evaluation` consumes versioned evidence and authoritative positions.
8. `application` performs cross-domain orchestration.
9. CLI/API/UI adapters call application services and do not recompute canonical scores.
10. `daily_research` and Legacy code are compatibility sources only.

## Required quality gate after every phase

Run all commands:

```bash
python scripts/check_docs_links.py
python -m pytest -q
python -m ruff check .
python -m mypy
```

Also run the phase-specific test suite.

Do not proceed while any command fails.

## Commit and rollback discipline

- one independently reviewable commit or small commit series per phase;
- do not combine unrelated refactors;
- keep changes reversible;
- database changes include rollback or safe forward-repair instructions;
- preserve new evidence and ledgers during code rollback;
- if design conflicts with code, stop the affected implementation, record the conflict and update the plan;
- do not hide architecture conflicts behind monkey patches, global switches or duplicate objects.

## Documentation requirements

Update when code facts change:

- `docs/status/Current-State.md`;
- `docs/status/Capability-Matrix.md`;
- `docs/status/Gap-Register.md`;
- `docs/architecture/01-Domain-Boundaries.md`;
- `docs/architecture/10-Production-Decision-Lifecycle.md`;
- `docs/roadmap/work-packages/WP-PDL-Production-Decision-Lifecycle.md`;
- `docs/operations/Production-Decision-Lifecycle-Runbook.md`.

For each completed phase, add or update a delivery audit containing exact commit IDs, changed paths, test commands and remaining authority limitations.

## Final response format

```text
# 1. Code scan and current-state model
# 2. Design assumptions confirmed or rejected
# 3. Implementation plan and phase boundaries
# 4. Completed changes by phase
# 5. File-by-file change table
# 6. Database and migration changes
# 7. Tests actually executed and results
# 8. Compatibility and authority verification
# 9. Unfinished or blocked items
# 10. Risks and next recommended phase
```

Do not claim completion for behavior that is only contracted, documented or tested with synthetic fixtures.

---
