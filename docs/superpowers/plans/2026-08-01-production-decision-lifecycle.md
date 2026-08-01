# Production Decision Lifecycle Implementation Plan

> **Status:** ROADMAP
> **Authority:** Approved execution plan for WP-PDL Phases 0–7
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-01
> **Supersedes:** None
> **Superseded By:** None
> **Related Documents:** ../specs/2026-08-01-production-decision-lifecycle-design.md, ../../roadmap/work-packages/WP-PDL-Production-Decision-Lifecycle.md
> **Code Evidence:** `origin/main@83a3168bc8550d862bd8b675277dd587ea71182c`; phase commits provide implementation evidence

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the research-to-manual-position decision-support lifecycle through Phase 7 without creating live execution or inflating evidence authority.

**Architecture:** Extend the existing modular monolith through bounded contracts, storage-neutral Repository Protocols, SQLite adapters and application services. Immutable Artifacts remain research evidence; mutable versioned aggregates use optimistic concurrency and append-only histories; actual positions are deterministic projections of accepted manual fills.

**Tech Stack:** Python 3.12, frozen dataclasses, Enum, Protocol, SQLite, canonical JSON/SHA-256 Artifacts, argparse CLI, pytest, Ruff and mypy.

## Global Constraints

- A-share, long-only and `exploratory_a_share_1455_v1` are explicit versioned profile semantics.
- All Path, Portfolio and Risk values are explicit versioned configuration; absence fails closed.
- Keep `EXPLORATORY`, `FORMAL_PIT_NOT_ESTABLISHED`, `FORMAL_OOS_ALPHA_NOT_ESTABLISHED` and `TRADING_AUTHORITY_NOT_GRANTED` ceilings.
- Do not change MR1 next-session 10:30, `daily_research` V1, DailyRun SQLite semantics or existing Artifact Readers.
- No LIVE_ORDER, QMT, PTrade, broker fills, unattended execution or automatic model promotion.
- Exclude `.idea/modules.xml` and every unrelated user change from commits.

---

### Task 1: Phase 0 baseline and architecture reconciliation

**Files:** Modify `AGENTS.md`, the master prompt and Gap Analysis; create this approved design and plan.

**Interfaces:** Consumes the existing documentation validator. Produces a clean documentation baseline and code-fact record.

- [ ] Correct the two validator-incompatible metadata values without changing tests or validator policy.
- [ ] Record the bridge, governance, placeholder-boundary, position and execution code facts.
- [ ] Run the complete quality gate and fix ordinary failures.
- [ ] Commit only Phase 0 documentation as `docs: reconcile production lifecycle baseline`.

### Task 2: Phase 1 Operational Research Bridge

**Files:** Create focused contracts and adapters under `application/operational_research/`, a run/replay CLI, and tests under `tests/application/operational_research/`.

**Interfaces:** Consumes `VerifiedPhaseDDailyDecisionArtifact` and `SupplementalResearchEvidenceBundle`. Produces `ResearchInputBundle` and `VerifiedResearchLayerArtifact` through the existing `PlatformResearchRunner`.

- [ ] Write failing tests for source/hash verification, DecisionTime and AvailabilityTime, PIT mapping completeness, missingness, eligibility ceiling, replay and duplicate publication.
- [ ] Implement an immutable supplemental bundle with exact Source Artifact references and typed Theme, Capital, Symbol, Membership and ETF mapping evidence.
- [ ] Implement a fail-closed adapter that reuses DailyLoop Universe, Eligibility, prices and predictions without inference.
- [ ] Add idempotent run/replay CLI commands, focused tests, documentation and the complete quality gate.
- [ ] Commit as `feat: add operational research evidence bridge`.

### Task 3: Phase 2 durable governance repositories

**Files:** Add repository protocols and SQLite adapters beside `platform/model_registry.py` and `platform/experiment_governance.py`; add isolated migrations and repository tests.

**Interfaces:** Consumes existing `ModelRegistration`, transitions and frozen experiment protocols. Produces recoverable versioned registrations, append-only transitions/access records and CAS conflicts.

- [ ] Write failing contract tests for restore, duplicate commands, stale version conflict, crash recovery and lifecycle bypass attempts.
- [ ] Refactor domain operations to persist only through protocols while preserving existing in-memory APIs.
- [ ] Implement SQLite schema versioning, transactions, optimistic compare-and-swap and append-only histories.
- [ ] Add rollback instructions, focused tests, documentation and the complete quality gate.
- [ ] Commit as `feat: persist model and experiment governance`.

### Task 4: Phase 3 Signal and PathForecast

**Files:** Extend `signals/` and `forecasting/` with configs, models, Artifact publishers/readers/replay; add owning tests.

**Interfaces:** Consumes verified Candidate/data evidence and EntryPathTarget contracts. Produces versioned `SignalSnapshot` and new `PathForecast` Artifacts; leaves `NextSessionForecast` unchanged.

- [ ] Write failing tests for five approved confirmations, uncalibrated probability rejection, temporal leakage, dual touch, missing future bars and semantic replay.
- [ ] Implement explicit content-addressed exploratory configs and deterministic signal evaluation.
- [ ] Implement multi-horizon PathForecast values for TargetId, barriers, horizon, MFE, MAE, quantiles and calibration status without probability when uncalibrated.
- [ ] Add readers, replay, focused tests, documentation and the complete quality gate.
- [ ] Commit as `feat: add replayable signals and path forecasts`.

### Task 5: Phase 4 Opportunity and Thesis

**Files:** Add decision aggregates, repository protocols, SQLite adapter and application service under `decision/` and `application/trading_lifecycle/`.

**Interfaces:** Consumes verified CandidateSet, SignalSnapshot and PathForecast references. Produces versioned TradingOpportunity and approved/rejected/expired TradingThesis histories.

- [ ] Write failing tests for verified lineage, expiry, forbidden Candidate-to-Thesis shortcut, idempotency, transition rules and CAS conflicts.
- [ ] Implement the two aggregate state machines with actor, approval, invalidation, version and command key.
- [ ] Implement SQLite persistence and application orchestration without writing positions.
- [ ] Run focused tests, documentation updates and the complete quality gate.
- [ ] Commit as `feat: add opportunity and thesis lifecycle`.

### Task 6: Phase 5 Portfolio and Risk Authority

**Files:** Extend `portfolio/`, add independent risk contracts/service under `decision/`, SQLite repositories and application orchestration.

**Interfaces:** Consumes approved active theses, current fill-derived positions, cash and explicit versioned policies. Produces TargetPosition, PortfolioDecision and append-only RiskDecision for SIMULATION or MANUAL_CONFIRMATION only.

- [ ] Write failing tests for missing config, gross/symbol/theme/liquidity/cash/T+1/loss constraints, timeout, structured rejection and concurrent decisions.
- [ ] Implement explicit versioned RiskBudget and PortfolioConstraint configs with no operational defaults.
- [ ] Implement portfolio proposal and independent fail-closed risk approval; strategy code cannot override rejection.
- [ ] Run focused tests, documentation updates and the complete quality gate.
- [ ] Commit as `feat: add portfolio and independent risk authority`.

### Task 7: Phase 6 Manual Execution and Position Authority

**Files:** Extend `execution/` and `position/` with aggregates, SQLite ledgers, correction records, projector and CLI application commands.

**Interfaces:** Consumes risk-approved manual intent and explicit operator commands. Produces append-only Fill evidence and deterministic PositionSnapshot projections only from accepted fills.

- [ ] Write failing tests for partial/cancel/reject/unknown states, duplicate fill/idempotency keys, correction records, reconciliation mismatch, restart and full rebuild.
- [ ] Implement manual records and append-only fills with actor, reason and created time.
- [ ] Implement the long-only A-share lot projector and T+1 facts without Provider reads or plan-to-position shortcuts.
- [ ] Run migration, focused, replay, documentation and complete quality gates.
- [ ] Commit as `feat: add manual fills and position authority`.

### Task 8: Phase 7 Holding, Exit and Attribution

**Files:** Add holding/exit assessment models and application services under `position/`; add outcome, attribution and rolling scorecard code under `evaluation/`.

**Interfaces:** Consumes active thesis, verified context, explicit configs and authoritative PositionSnapshot. Produces HOLD/ADD/REDUCE/EXIT/WAIT/DATA_INSUFFICIENT assessments and versioned attribution reports without mutating models.

- [ ] Write failing tests for independent Holding/Exit roles, invalid-thesis ADD rejection, fresh risk requirement, MFE/MAE/capture/execution deviation attribution and full lifecycle replay.
- [ ] Implement versioned assessments and fail-closed application orchestration.
- [ ] Implement immutable TradeOutcome, layer attribution and rolling scorecard calculation.
- [ ] Run focused lifecycle replay, documentation and complete quality gates.
- [ ] Commit as `feat: complete holding exit and attribution loop`.

### Task 9: Consolidated review and handoff

**Files:** Update delivery audit, status, capability, gap, architecture and runbook evidence.

**Interfaces:** Consumes all phase commits and observed test output. Produces the final evidence-bound delivery record.

- [ ] Verify dependency directions and search for forbidden LIVE or duplicate authority paths.
- [ ] Run the complete quality gate once more and record exact results.
- [ ] Inspect all branch changes and checkpoint commits; exclude user files.
- [ ] Report remaining data, validation and production-admission blockers without claiming live or formal authority.
