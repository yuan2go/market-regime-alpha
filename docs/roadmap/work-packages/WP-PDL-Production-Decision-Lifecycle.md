# WP-PDL — Production Decision Lifecycle

> **Status:** ROADMAP  
> **Authority:** Executable implementation work package  
> **Owner:** Market Regime Alpha maintainers  
> **Last Updated:** 2026-08-01  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** ../../architecture/10-Production-Decision-Lifecycle.md, ../../architecture/decisions/ADR-004-Production-Decision-Lifecycle-Organization.md, ../../specs/Production-Decision-Lifecycle-Requirements.md, ../../audit/Production-Decision-Lifecycle-Gap-Analysis.md  
> **Code Evidence:** Planned against current `main`; delivery claims must be recorded separately after implementation and verification.

## 1. Work-package objective

Deliver an incremental, testable and recoverable production decision-support lifecycle on top of the current DailyLoop and Platform V2 foundation.

The target vertical slice is:

```text
Verified Daily Evidence
→ Operational Research Adapter
→ ResearchLayerArtifact
→ SignalSnapshot
→ PathForecast
→ TradingOpportunity
→ TradingThesis
→ PortfolioDecision
→ RiskDecision
→ ManualTradeRecord and Fill
→ PositionSnapshot
→ Holding/Exit Assessment
→ AttributionReport
```

The work package does not authorize unattended live broker operation.

## 2. Delivery principles

1. Preserve existing immutable artifacts and readers.
2. Reuse existing identities, semantic time, SourceManifest, Universe, Feature and governance rules.
3. Do not create a second daily acquisition state machine.
4. Keep domain behavior out of application orchestration.
5. Keep Candidate, Signal, Decision, Execution and Position responsibilities separate.
6. Add new schema identities for new semantics.
7. Use fail-closed data and risk gates.
8. Make every phase independently testable and reversible.
9. Keep first execution authority human-recorded and append-only.
10. Do not claim formal PIT, OOS Alpha or trading authority without separate evidence and promotion.

## 3. Scope

### In scope

- code-first architecture reconciliation;
- operational DailyLoop-to-Research adapter;
- durable Model Registry and Experiment Governance repositories;
- executable Signal Engine;
- multi-horizon PathForecast;
- TradingOpportunity and TradingThesis;
- PortfolioDecision and RiskDecision;
- ManualTradeRecord and Fill ledger;
- PositionSnapshot projection;
- HoldingAssessment and ExitAssessment;
- outcome and layer attribution;
- CLI-first application surface;
- tests, documentation, runbook and shadow-operation preparation.

### Out of scope

- unattended live order placement;
- broker client mutation;
- Level-2 order-book models;
- automatic model mutation or promotion;
- multi-account or multi-broker portfolio management;
- high-frequency execution;
- formal performance claims before validation.

## 4. Phase plan

## Phase 0 — Architecture and contract freeze

### Goal

Confirm code facts, record design conflicts and freeze ownership before implementation.

### Changes

- add ADR-004;
- add target architecture and requirements;
- add gap analysis;
- update domain, status and roadmap indexes;
- define initial authority matrix and compatibility constraints.

### Deliverables

- accepted architecture documentation;
- unresolved decision register;
- phase-specific implementation plan.

### Verification

- documentation links pass;
- no code behavior changes;
- maintainers approve open product decisions required for later phases.

### Rollback

Revert documentation commits; no runtime or data migration exists.

## Phase 1 — Operational Research Bridge

### Goal

Run Platform V2 research from verified operational evidence without changing DailyLoop ownership.

### Target paths

```text
src/market_regime_alpha/application/operational_research/
src/market_regime_alpha/application/research_layer/
scripts/run_operational_research.py
tests/application/operational_research/
```

### Requirements

- load verified Daily Decision or Source Archive;
- verify SourceManifest, DecisionTime, AvailabilityTime and input hashes;
- reuse current Universe and Eligibility;
- build typed ResearchInputBundle observations;
- fail closed on missing theme/capital/mapping evidence;
- preserve EXPLORATORY authority;
- support deterministic run and replay;
- do not modify DailyLoopRunner core responsibilities.

### Completion criteria

- fixture and historical archive can produce a verified ResearchLayerArtifact;
- repeated execution produces no duplicate artifact;
- late evidence is rejected;
- current DailyLoop and Platform V2 tests remain unchanged and green.

### Implementation evidence

Implemented on `feat/production-decision-lifecycle` as an exploratory
engineering slice:

- typed, content-addressed `SupplementalResearchEvidenceBundle` Artifact;
- exact supplemental SourceManifest and source-hash coverage;
- DecisionTime and per-item AvailabilityTime validation;
- complete PIT Theme Membership and ETF/Theme mapping reconciliation;
- fail-closed missingness and DataEligibility enforcement;
- verified Daily Artifact → ResearchInputBundle → ResearchLayerArtifact run;
- content-idempotent repeated execution, semantic replay and explicit-config
  CLI tests.

No qualified operational supplemental evidence, formal PIT or trading
authority is claimed.

### Rollback

Disable or remove the adapter and CLI; existing DailyLoop and offline research remain unaffected.

## Phase 2 — Durable governance repositories

### Goal

Persist Model Registry and Experiment Governance without weakening existing rules.

### Target paths

```text
src/market_regime_alpha/platform/repositories.py
src/market_regime_alpha/infrastructure/sqlite/
src/market_regime_alpha/infrastructure/postgres/  # contract-ready, implementation may be deferred
tests/platform/repositories/
```

### Requirements

- define repository protocols;
- preserve current transition validation;
- add SQLite adapters first;
- restore exact lifecycle and access histories after restart;
- use optimistic concurrency;
- reject duplicate identity with different semantics;
- prevent direct persistence writes from bypassing domain validation.

### Completion criteria

- lifecycle and experiment-access state survive process restart;
- concurrent transition/access tests pass;
- restore rejects non-contiguous history;
- existing in-memory behavior remains available for unit tests.

### Implementation evidence

Implemented on `feat/production-decision-lifecycle`:

- storage-neutral Model Registry and Experiment Governance Repository
  Protocols;
- domain-validating persistent application services that replay the existing
  lifecycle and access-budget rules;
- isolated SQLite migration `001_governance` with no change to `daily_runs`;
- optimistic compare-and-swap versions and global command idempotency keys;
- append-only model transition and experiment access tables;
- restart restore, duplicate, conflicting-key, stale-writer, forged-state,
  transaction rollback and up/down migration tests.

SQLite is the local/test durable adapter. PostgreSQL implementation and
operational database promotion are not claimed.

### Rollback

Switch application composition to the in-memory adapters and retain the SQLite
file read-only for audit. For an unused local/test database, the isolated
`001_governance_down.sql` migration removes only governance tables. Back up or
export append-only histories before any destructive schema rollback.

## Phase 3 — Signal Engine and PathForecast

### Goal

Add replayable entry-structure and multi-horizon path research.

### Target paths

```text
src/market_regime_alpha/signals/
src/market_regime_alpha/forecasting/
src/market_regime_alpha/strategies/entry/
tests/signals/
tests/forecasting/
```

### Signal V1 scope

- price action;
- volume confirmation;
- trend confirmation;
- VWAP context;
- overheat state.

### Forecast V1 scope

- target ID and horizon;
- upper and lower barrier;
- expected return;
- MFE and MAE;
- return quantiles;
- calibration status;
- explicit missing and ambiguous outcomes.

### Completion criteria

- no post-DecisionTime evidence is consumed;
- dual-touch ambiguity is preserved;
- uncalibrated output cannot expose probability;
- artifact publication, reader and replay are deterministic;
- Signal output has no order or position authority.

### Rollback

Disable model registrations and stop publishing V1 Signal/PathForecast artifacts; Candidate research remains operational.

## Phase 4 — TradingOpportunity and TradingThesis

### Goal

Create the explicit boundary between research evidence and human trade consideration.

### Target paths

```text
src/market_regime_alpha/decision/opportunity.py
src/market_regime_alpha/decision/thesis.py
src/market_regime_alpha/decision/repositories.py
src/market_regime_alpha/application/trading_lifecycle/
tests/decision/
```

### Requirements

- opportunity binds exact Candidate, Signal, Forecast, model/config and DecisionTime;
- opportunity has expiry and idempotent identity;
- thesis records rationale, evidence and invalidation conditions;
- every mutable transition uses version checking and audit event;
- expired opportunity cannot become thesis;
- invalidated thesis cannot add exposure.

### Completion criteria

- complete state-transition suite passes;
- duplicate commands are idempotent;
- concurrent confirmation has one winner;
- evidence mismatch is rejected.

### Rollback

Disable opportunity/thesis commands and keep persisted records read-only.

## Phase 5 — Portfolio and Risk Authority

### Goal

Convert active theses into risk-constrained target positions.

### Target paths

```text
src/market_regime_alpha/portfolio/
src/market_regime_alpha/decision/risk.py
src/market_regime_alpha/application/trading_lifecycle/
tests/portfolio/
tests/decision/test_risk.py
```

### Requirements

- current positions and cash;
- maximum gross exposure;
- per-symbol and per-theme limits;
- liquidity and capacity checks;
- T+1 and available quantity;
- portfolio loss budget;
- independent RiskDecision;
- fail closed on risk failure or timeout;
- output simulation/manual-confirmation only.

### Completion criteria

- hard-risk rejection cannot create an approved manual intent;
- concentration and cash constraints are deterministic;
- all decisions carry exact limit snapshots and reasons;
- portfolio tests include conflicting theses and partial capacity.

### Rollback

Pause new portfolio decisions; existing theses remain observable but cannot create new intents.

## Phase 6 — Manual Execution and Position Authority

### Goal

Establish actual human-recorded execution and authoritative position projection.

### Target paths

```text
src/market_regime_alpha/execution/
src/market_regime_alpha/position/
src/market_regime_alpha/application/trading_lifecycle/
scripts/record_manual_trade.py
scripts/record_manual_fill.py
tests/execution/
tests/position/
```

### Requirements

- append-only ManualTradeRecord and Fill;
- idempotent command and fill identities;
- partial fill, cancellation, rejection and correction;
- PositionSnapshot derived only from fills;
- full rebuild and reconciliation;
- no model or plan creates actual position directly.

### Completion criteria

- replaying all fills rebuilds the same quantity, cost and realized PnL;
- duplicate fill does not change position twice;
- correction records preserve history;
- mismatch moves the account/symbol into reconciliation-required state.

### Rollback

Stop new writes and rebuild read-only positions from the retained fill ledger.

## Phase 7 — Holding, Exit and Attribution

### Goal

Complete the open-position and closed-trade feedback loop.

### Target paths

```text
src/market_regime_alpha/position/holding.py
src/market_regime_alpha/position/exit.py
src/market_regime_alpha/evaluation/attribution.py
src/market_regime_alpha/application/review_loop/
tests/position/
tests/evaluation/
```

### Requirements

- independent Holding and Exit assessments;
- current thesis, position, market, theme, capital and signal context;
- ADD requires a fresh portfolio/risk decision;
- closed positions produce MFE, MAE, capture and layer attribution;
- evaluation cannot modify models automatically;
- rolling scorecards use frozen protocols.

### Completion criteria

- complete trade lifecycle can be replayed;
- all actions and outcomes trace to immutable evidence;
- attribution differentiates selection, entry, holding, exit, sizing and execution;
- current model lifecycle rules consume evidence references without automatic promotion.

### Rollback

Disable automated assessments and continue manual position closure; preserve outcome evidence.

## Phase 8 — Shadow operations

### Goal

Run the full lifecycle with real-time evidence and no unattended execution.

### Requirements

- controlled schedule;
- operator confirmation;
- daily source, artifact and position reconciliation;
- metrics and alerts;
- no result-affecting manual database edits;
- documented incident and rollback procedures.

### Completion criteria

The shadow period and minimum sample count must be approved before the repository makes any stronger production claim. The exact duration is an open governance decision and must not be invented by implementation code.

## Phase 9 — Operator surface

### Goal

Provide read and write surfaces over application services.

### Initial views

- daily research and opportunity plan;
- evidence and reason-code detail;
- thesis confirmation;
- portfolio/risk decision;
- manual trade and fill capture;
- position health and reconciliation;
- review and scorecards;
- audit trace.

CLI remains a supported recovery surface even after an HTTP/UI adapter exists.

## Phase 10 — Optional external execution adapter

This phase requires a separate architecture and security approval. It is not authorized by WP-PDL.

Any future adapter must preserve approved-intent versioning, append-only execution events, reconciliation, kill switches and independent credential boundaries.

## 5. Cross-phase test gate

Every phase must run:

```bash
python scripts/check_docs_links.py
python -m pytest -q
python -m ruff check .
python -m mypy
```

A phase is incomplete while any required command fails.

Tests must not be weakened to preserve a new implementation. Existing schema and behavior changes require an explicit new version and compatibility test.

## 6. Database and migration rules

- do not alter current `daily_runs`, `stage_receipts` or `acquisition_stage_receipts` semantics;
- every mutable aggregate table has `version`;
- command-facing tables have idempotency protection;
- fill and transition histories are append-only;
- immutable artifact content remains outside the operational database authority;
- each migration has a rollback or a documented irreversible safety procedure;
- production PostgreSQL is introduced only after repository contract parity with SQLite.

## 7. Documentation deliverables

Each implemented phase updates:

- `docs/status/Current-State.md`;
- `docs/status/Capability-Matrix.md`;
- `docs/status/Gap-Register.md`;
- this work package;
- the architecture document if boundaries change;
- a delivery audit with exact commit and test evidence;
- the operations runbook when runtime behavior changes.

## 8. Completion definition

WP-PDL is complete only when:

1. the entire lifecycle runs and replays through closed-position attribution;
2. actual position state is reconstructed from the manual fill ledger;
3. all hard-risk paths fail closed;
4. existing artifact compatibility remains green;
5. durable governance recovers exactly;
6. a sustained shadow period is recorded;
7. no unattended live execution path exists;
8. remaining formal PIT, OOS Alpha and broker-authority gaps are still declared honestly.
