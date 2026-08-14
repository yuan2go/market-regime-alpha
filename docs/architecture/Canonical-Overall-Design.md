# Market Regime Alpha — Canonical Overall Design

> **Status:** CANONICAL_TARGET_ARCHITECTURE  
> **Authority:** Consolidated overall design and implementation baseline  
> **Owner:** Market Regime Alpha maintainers  
> **Last Updated:** 2026-08-14  
> **Applies To:** Architecture, research, strategy, portfolio, runtime, evidence, qualification, operations, and future execution  
> **Normative Boundary:** This document consolidates the current target design. It does not override `docs/constitution/00` through `09`; where a conflict exists, the repository documentation authority order applies. Current implementation facts remain authoritative only when proven by code, PostgreSQL schema, tests, and reproducible runtime evidence.

---

## 1. Executive Summary

Market Regime Alpha is a **Multi-Strategy Alpha Research, Decision & Portfolio Operating System for the China A-share market**.

The platform is not one T+1 model, one buy/sell-point model, one factor library, or one automated trading bot. It provides shared market evidence, PIT-safe data, features, state intelligence, research infrastructure, strategy runtime, portfolio/risk, execution boundaries, outcome attribution, and qualification so that multiple strategy families can be researched, compared, shadowed, admitted, degraded, and retired under common contracts.

The canonical end-to-end business loop is:

```text
Market / Reference Evidence
        ↓
Canonical PIT Data
        ↓
Features & Shared Market Intelligence
        ↓
Strategy-specific Opportunity Discovery
        ↓
Forecast / Decision Policy
        ↓
Strategy Proposal
        ↓
Portfolio & Risk
        ↓
Shadow / Manual / Future Broker Execution
        ↓
Fill-derived Position
        ↓
Outcome & Attribution
        ↓
Evidence & Qualification
        ↓
Research Feedback / Challenger
```

The platform must support materially different strategy families without duplicating the platform itself. The initial reference families are:

1. **Overnight / T+1** — late-session entry and next-session realization at explicit execution checkpoints.
2. **Swing State** — Entry / Hold / Add / Reduce / Exit decisions evaluated against future path quality, not a single next-day return.

Future families may include ETF rotation, theme rotation, trend following, mean reversion, dividend/long-term allocation, policy/event strategies, and intraday overlays. They must reuse the same platform contracts rather than create parallel control planes.

The principal architectural constraint for the next phase is **business and research convergence, not further governance expansion**. PostgreSQL Authority, PIT, replay, evidence identity, recovery, and qualification remain core. New authorities, receipts, protocol wrappers, orchestrators, or runtime planes require a concrete correctness or operational failure mode before they are added.

---

## 2. Goals and Non-Goals

### 2.1 Goals

The system shall:

- support multiple independently versioned strategy families;
- separate facts, inferred state, prediction, signal, decision, strategy, portfolio, execution, and outcome;
- make historical and prospective decisions reproducible at the exact decision-time information boundary;
- measure factor/model value only relative to an explicit target, horizon, universe, regime, and strategy context;
- support buy-point, holding, reduction, and exit research as well as short-horizon strategies;
- preserve real negative and inconclusive evidence instead of promoting unsupported Alpha claims;
- provide deterministic recovery/replay for critical runtime state;
- support Shadow and human-in-the-loop production before automatic broker execution;
- attribute realized results to strategy, model, entry/exit policy, portfolio, cost, and execution where evidence permits;
- allow Champion/Challenger evolution only through explicit re-evaluation and qualification.

### 2.2 Non-Goals

The system shall not:

- promise deterministic returns or a fixed win rate;
- treat one strategy as the identity of the platform;
- treat a factor as globally useful or useless outside a target/context;
- equate model score with a trade action;
- infer a real position from a decision or order intent instead of fills;
- allow online self-modification to bypass qualification;
- require microservices, Kafka, Kubernetes, graph databases, autonomous multi-agent trading, reinforcement-learning execution, or other infrastructure without demonstrated need;
- treat automatic broker execution as a prerequisite for a production-grade manual decision-support system.

---

## 3. Core Principles

### P1. Strategy is not Model

Canonical responsibility chain:

```text
Feature / Factor
    ↓
Model / Forecast
    ↓
Signal / Assessment
    ↓
Decision Policy
    ↓
Strategy Proposal
    ↓
Portfolio
    ↓
Execution
```

A model estimates. A strategy owns a bounded decision policy. Portfolio owns cross-position/cross-strategy allocation. Execution owns side effects.

### P2. Candidate is not Entry

Canonical opportunity funnel:

```text
Base Tradable Universe
        ↓
Shared Eligibility
        ↓
Strategy-specific Ranking
        ↓
Candidate
        ↓
Entry / Action Decision
```

Candidate Discovery answers **what deserves attention**. Entry answers **whether action is justified now**. Candidate hard gates must not silently consume the role of the downstream decision model.

### P3. Shared Intelligence is not a Shared Trade Decision

Market Regime, Theme State, ETF State, Capital State, Trend State, Liquidity State, and related context may be shared. They are contextual evidence, not universal BUY/SELL authorities.

### P4. Evidence is Scoped

A factor/model/strategy conclusion is scoped by at least:

```text
Data / PIT Status × Universe × Decision Time × Target × Horizon
× Strategy Version × Cost Assumption × Evaluation Protocol
```

Evidence for an Overnight strategy does not qualify a Swing strategy, and vice versa.

### P5. Position is Fill-derived

```text
Decision ≠ Order ≠ Fill ≠ Position
```

Authoritative account position is derived from fills and reconciled execution facts. Strategy-level logical sleeves may allocate those fills for attribution, but they do not replace physical account truth.

### P6. Historical and Prospective Semantics Converge

Historical research, replay, Shadow, and production should share the same strategy/domain semantics. Replace clock, data source, and execution adapters rather than copy the business logic.

### P7. One Business Fact, One Authority

A business fact may have projections/read models, but only one canonical writer/authority. Storage duplication must not create authority duplication.

### P8. Fail Closed for Correctness, Not for Research Starvation

Fail closed for future leakage, unresolved PIT facts, corrupted data, unsafe corporate-action labels, unqualified production admission, and invalid execution semantics. Research selectivity itself must remain measurable: every material rejection requires explicit attribution.

### P9. Governance Must Pay for Itself

Every new Authority, Receipt, Protocol, Admission status, repository abstraction, or orchestration layer must identify the concrete failure mode it prevents and its real consumers.

### P10. Prefer a Modular Monolith

The target deployment remains a PostgreSQL-centered modular monolith until independent scaling, isolation, ownership, or availability requirements justify a split.

---

## 4. Business Architecture

### 4.1 Primary Roles

- **Quant Researcher:** hypothesis, factors, targets, models, experiments, evaluation.
- **Strategy Developer:** Strategy Contract, policies, strategy runtime behavior.
- **Trader / Decision User:** review opportunities, execute or decline manual actions, record fills.
- **Reviewer:** evidence, qualification, promotion/degradation decisions.
- **Operator:** data readiness, runtime health, recovery, replay, inspection.
- **System:** acquisition, materialization, inference, evaluation, decision lineage, outcome and attribution.

### 4.2 Core Business Loop

```text
Observe
  → Understand Market Context
  → Discover Opportunities
  → Estimate Future Path / Utility
  → Decide
  → Allocate Capital
  → Apply Risk
  → Execute / Record
  → Observe Outcome
  → Attribute
  → Evaluate
  → Qualify Challenger
  → Promote / Degrade / Retire
```

The feedback loop produces research evidence and challengers. It never silently mutates the active Champion.

---

## 5. Capability Architecture

The platform is organized into nine capability domains:

1. **Market & Reference Data** — market observations, security lifecycle, calendar, corporate actions, indices, ETF/theme/industry reference, trading rules.
2. **Feature & State Intelligence** — observable features and versioned inferred market/theme/capital/trend/liquidity states.
3. **Research & Evaluation** — dataset manifests, target labels, factor analysis, ablation, cross-sectional evaluation, walk-forward/OOS, calibration, cost sensitivity.
4. **Strategy** — candidate policy, forecast/model consumption, Entry/Hold/Add/Reduce/Exit and strategy-specific state.
5. **Portfolio & Risk** — strategy sleeves, capital allocation, exposure, concentration, liquidity, correlation, turnover and drawdown controls.
6. **Decision & Execution** — authoritative decisions, execution mode, order intent, human/broker boundaries, fills and reconciliation.
7. **Outcome & Attribution** — market outcomes, strategy outcomes, layered attribution and error taxonomy.
8. **Evidence & Qualification** — immutable evidence lineage, Champion/Challenger, admission/degradation policy.
9. **Runtime & Operations** — scheduling, retries, leases/fences, checkpoints, recovery, replay, trace, metrics and inspection.

These are capability boundaries, not a requirement for nine services.

---

## 6. System Architecture

```text
┌──────────────────── External Systems ────────────────────┐
│ Market Data │ Reference Data │ Events │ Broker / Manual │
└──────────────────────────┬───────────────────────────────┘
                           ▼
                  Market Evidence Layer
                           ▼
                  Canonical PIT Data
                           ▼
                 Feature Infrastructure
                           ▼
              Shared Market Intelligence
         ┌─────────────┬─────────────┬─────────────┐
         │ Regime      │ Theme / ETF │ Capital/etc │
         └─────────────┴──────┬──────┴─────────────┘
                              ▼
                    Strategy Runtime Kernel
          ┌───────────────────┼───────────────────┐
          ▼                   ▼                   ▼
     Overnight/T+1       Swing State        ETF Rotation ...
          │                   │                   │
          └───────────────────┼───────────────────┘
                              ▼
                    Strategy Proposals
                              ▼
                       Portfolio Engine
                              ▼
                          Risk Engine
                              ▼
                      Decision Authority
                              ▼
               Shadow / Manual / Future Broker
                              ▼
                             Fill
                              ▼
              Physical Position + Strategy Sleeves
                              ▼
                         Outcome
                              ▼
                       Attribution
                              ▼
                Evidence & Qualification
```

Cross-cutting concerns are PostgreSQL Authority, identity/versioning, PIT, audit, trace, recovery, replay, security, and observability.

---

## 7. Canonical Runtime

### 7.1 One Production Control Plane

The platform has one canonical all-day production control plane. Strategy families are bounded children of that runtime; a new strategy must not introduce another top-level scheduler or authority plane.

Canonical logical flow:

```text
Scheduler / Session Owner
        ↓
Acquire / Refresh Evidence
        ↓
Normalize / Validate / PIT
        ↓
Materialize Features
        ↓
Infer Shared State
        ↓
For each eligible Strategy Version:
    Resolve Universe & Eligibility
    Rank / Discover Candidates
    Run Models / Path Forecast
    Apply Strategy Policy
    Emit Strategy Proposal
        ↓
Cross-strategy Portfolio
        ↓
Risk Overlay
        ↓
Authoritative Decision
        ↓
Execution Mode Adapter
        ↓
Fill / Position / Outcome
        ↓
Attribution / Evidence
```

### 7.2 Historical Runtime

Historical research uses historical clock + frozen PIT evidence + frozen Strategy Version and reuses the same domain/strategy semantics. Historical materialization may be operationally separate but must not become a second implementation of strategy rules.

### 7.3 Execution Modes

Execution mode is independent of research qualification:

- `BACKTEST`
- `SHADOW`
- `MANUAL`
- `BROKER_AUTO` (future)

A statistically/economically qualified strategy may remain in Shadow or Manual mode. Automatic broker side effects require a separate operational admission boundary.

---

## 8. Domain and Authority Model

Canonical identities include:

- `DataSourceVersion`
- `FeatureDefinitionVersion`
- `StateModelVersion`
- `DatasetManifest`
- `TargetDefinitionVersion`
- `ModelVersion`
- `StrategyVersion`
- `StrategyRun`
- `PortfolioPolicyVersion`
- `Decision`
- `OrderIntent`
- `Fill`
- `PhysicalPosition`
- `StrategySleevePosition`
- `Outcome`
- `Attribution`
- `EvidenceArtifact`
- `QualificationAssessment`
- `RuntimeAttempt`

Logical authority map:

| Fact / Object | Canonical Authority |
|---|---|
| Market observation | Market Evidence Authority |
| Reference/effective-dated fact | PIT Reference Authority |
| Materialized feature | Feature Materialization Authority |
| Inferred shared state | State Authority |
| Frozen dataset | Dataset Manifest Authority |
| Model identity/status | Model Registry |
| Strategy identity/status | Strategy Registry |
| Portfolio decision | Portfolio/Decision Authority |
| Order intent / execution request | Execution Authority |
| Fill | Fill Authority |
| Physical position | Fill-derived Position Authority |
| Outcome | Outcome Authority |
| Attribution | Attribution Authority |
| Evidence artifact | Evidence Authority |
| Qualification assessment | Qualification Authority |
| Runtime attempt / recovery state | Runtime Authority |

A logical authority does not require a separate database/service/table family when one cohesive aggregate is sufficient.

---

## 9. Data Architecture

### 9.1 Data Layers

```text
L0 Source Evidence
L1 Canonical Market / Reference Data
L2 Features & Inferred State
L3 Research Dataset / Target Views
L4 Outcome / Evaluation / Attribution
```

### 9.2 Temporal Semantics

Data that can cause lookahead bias must preserve the necessary time semantics, commonly including:

- event/effective time;
- publication/knowledge time where applicable;
- ingestion time;
- decision time;
- valid-from/valid-to for effective-dated reference facts.

The research question is not merely whether a value existed historically, but whether it was knowable and usable at the declared decision time.

### 9.3 Formal PIT Boundary

Formal PIT engineering mechanisms and Formal PIT historical evidence are separate claims. Formal historical evidence requires qualified point-in-time treatment of the relevant universe, constituents, security lifecycle, suspensions, corporate actions, reference mappings, and decision-time availability for the strategy under test.

### 9.4 Dataset Manifest

Every formal evaluation dataset must freeze at least:

```text
dataset_id
universe_definition
date_range
decision_clock
source_versions
feature_versions
target_version
PIT_status
exclusion_rules
content_hash
code_sha / implementation identity
```

Formal evaluation must not depend on an unversioned ad-hoc query.

---

## 10. Research, Target and Forecast Architecture

### 10.1 Factor Research

A Factor definition must declare formula, required data, availability boundary, lookback, normalization, missing-value policy, and version. Its value is evaluated against explicit targets using suitable diagnostics such as RankIC, IC decay, quantile spread, monotonicity, bootstrap uncertainty, regime stability, turnover, and cost sensitivity.

A factor is never globally promoted because it worked on one horizon.

### 10.2 Target / Label Authority

The platform uses reusable market outcomes and strategy-specific target views.

**Overnight examples:**

- returns at explicit T+1 checkpoints;
- morning MFE / MAE;
- target-before-stop;
- executable net return.

**Swing examples:**

- MFE/MAE at 3/5/10/20 sessions;
- target-before-stop;
- time-to-MFE;
- trend continuation/failure;
- post-exit MFE/MAE;
- opportunity loss and avoided drawdown.

The same raw future path may support several target definitions, but target identity/version must be explicit.

### 10.3 Path Forecast

Path Forecast is a reusable predictive capability, not a synonym for T+1 return. Depending on the Strategy Contract it may estimate:

```text
Expected Return
MFE / MAE Distribution
P(Target Hit)
P(Stop Hit)
P(Target Before Stop)
Time-to-MFE
Trend Continuation / Failure
```

Forecast output is not itself a trade action.

### 10.4 Decision Error Taxonomy

Buy/hold/exit quality must not be reduced to direction accuracy. Evaluation should distinguish, where applicable:

- Entry false positive — action followed by poor path/risk outcome;
- Entry false negative — skipped opportunity that subsequently met the strategy target;
- Exit false positive — premature exit with material opportunity loss;
- Exit false negative — failure to exit before material avoidable downside.

Strategy optimization should target expected trading utility/economic value, not raw classification accuracy alone.

---

## 11. Strategy Architecture

### 11.1 Strategy Contract

Every Strategy Version must freeze the minimum contract required to reproduce and evaluate it:

```text
strategy_id / family / version
universe & eligibility contract
decision clock / holding horizon
target contract
feature/model dependencies
candidate policy
entry / holding / add / reduce / exit policies
portfolio proposal policy
risk assumptions
cost model
execution constraints
evaluation protocol
qualification policy
code/config identity
```

### 11.2 Reference Strategy A — Overnight / T+1

Owns a short-horizon policy such as late-session entry and explicit next-session realization checkpoints. Its existing negative/inconclusive results remain valid evidence for the tested Strategy Version and must not be generalized to the entire platform.

### 11.3 Reference Strategy B — Swing State

Owns stateful Entry / Hold / Add / Reduce / Exit decisions over multi-session horizons. Its research emphasizes path quality, trend persistence/failure, MFE/MAE, target-before-stop, opportunity loss, and avoided drawdown rather than a single T+1 direction label.

### 11.4 Candidate Boundary

Shared Eligibility should represent objective tradability/data eligibility. Strategy-specific Candidate Discovery should rank or select opportunities for that strategy. Rejection counts/reasons must be observable so that selectivity, coverage, and model starvation are distinguishable.

### 11.5 Strategy Registry

The platform needs a canonical Strategy identity/lifecycle alongside Model identity. This may reuse existing registry infrastructure rather than require a new service. Strategy qualification and promotion are strategy-version scoped.

---

## 12. Portfolio, Position and Risk

### 12.1 Two Position Views

A multi-strategy account requires both:

1. **Physical Account Position** — authoritative quantity/cost derived from actual fills.
2. **Strategy Sleeve Position** — logical attribution of capital and fills to a Strategy Version.

A documented Fill Allocation Policy must reconcile multiple strategy intents on the same security and support strategy-level PnL/exposure attribution without inventing physical holdings.

### 12.2 Portfolio Layers

- **Strategy Portfolio:** candidate selection, Top-K, score/equal weighting, strategy budget, rebalance semantics.
- **Master Portfolio:** cross-strategy allocation, single-name/industry/theme exposure, correlation, liquidity, turnover, drawdown and aggregate risk.

Complex optimization is not a prerequisite. Baselines such as Top-1/3/5/10 and equal/score weighting are preferred until Alpha and cost economics justify a more complex optimizer.

### 12.3 A-share Risk/Execution Constraints

Relevant rules must be effective-dated and strategy-aware, including T+1 restrictions, suspension, price limits, trading calendar, minimum order units, security lifecycle, corporate actions, and instrument-specific rules.

---

## 13. Outcome, Attribution and Feedback

### 13.1 Outcome Types

**Market Outcome** records what objectively happened after a decision point: return, high/low, MFE/MAE, gap, target/stop timing, and related path facts.

**Strategy Outcome** records what the strategy/account experienced: actual or simulated entry/exit, holding time, gross/net PnL, cost, slippage, drawdown and turnover.

They must not be conflated.

### 13.2 Attribution

Where statistically meaningful, the system should distinguish contributions/failures from:

- market regime/context;
- theme/ETF/capital context;
- candidate/eligibility gates;
- factors/models/forecast;
- entry/holding/exit policy;
- portfolio/risk;
- transaction cost/slippage;
- execution/fill behavior.

Gate attribution is mandatory for material candidate funnels: counts and explicit reject reasons must explain how the universe becomes the selected set.

### 13.3 Research Feedback

```text
Outcome
  → Attribution
  → Research Finding
  → Challenger
  → Formal Evaluation
  → Qualification
  → Promotion / Rejection
```

No outcome directly mutates the active Champion.

---

## 14. Reliability, Recovery and Replay

Retain the reliability mechanisms that protect real failure modes:

- idempotency keys;
- explicit attempts;
- bounded retry for transient failures;
- leases/fences where concurrent ownership exists;
- checkpoints/resume;
- deterministic replay;
- immutable evidence/artifact identity.

Do not retry deterministic invalid-data, PIT-violation, schema-incompatibility, or qualification failures as if they were transient infrastructure failures.

Replay proof requires frozen input/evidence identity, frozen code/config/strategy identity, and deterministic comparison of the authoritative outputs relevant to the replay scope. A replay proof for one research campaign does not automatically prove all production workflows.

---

## 15. Governance, Qualification and Production Admission

Qualification should be modeled as separable evidence dimensions rather than an ever-growing single state machine:

| Axis | Core Question |
|---|---|
| Engineering | Can the software/runtime operate correctly and recoverably? |
| Data / PIT | Is the required data fit for this formal claim at decision time? |
| Statistical | Has the hypothesis survived a predeclared formal/OOS protocol? |
| Economic | Does the result survive costs, liquidity/capacity and relevant constraints? |
| Prospective | Does the behavior survive future real-time Shadow observation? |
| Operational | Is the strategy admitted for Research, Shadow, Manual, or Auto execution? |

Production Admission is policy over evidence dimensions, not a magic boolean. Admission criteria may differ by strategy family and execution mode, but cannot silently downgrade required evidence.

Evidence labels such as `EXPLORATORY`, `PIT_INCOMPLETE`, `FORMAL_OOS=false`, or `CALIBRATED=false` must never be upgraded by documentation wording or engineering test success.

---

## 16. Observability and Operations

Operational inspection must answer business questions, not only infrastructure health.

Canonical correlation identities should allow navigation among runtime/session, strategy run, dataset, model, strategy version, decision, position, attempt and trace.

Minimum business observability includes:

- source freshness and coverage;
- PIT/data eligibility failures;
- eligible/candidate/selected counts and rejection distributions;
- forecast estimability/calibration status;
- factor/model/strategy drift where defined;
- portfolio exposure, turnover and capacity;
- gross/net strategy outcomes;
- provider/runtime failures, retry/recovery counts and latency;
- current qualification/admission status.

An operator must be able to inspect why a strategy did not run, why no candidate was selected, why a forecast is not estimable, and which upstream evidence is missing.

---

## 17. Testing and Qualification Ladder

Separate software correctness from research validity:

1. **Unit** — local algorithms and invariants.
2. **Contract** — providers, repositories, strategy/model contracts.
3. **Integration** — PostgreSQL, migrations and composed modules.
4. **E2E Runtime** — canonical business flow with real composition.
5. **Recovery / Replay** — deterministic failure/resume/replay semantics.
6. **Research Qualification** — PIT, leakage controls, frozen datasets, statistical/OOS and economic evidence.
7. **Prospective Proof** — future real-time Shadow behavior and data availability.
8. **Production Admission** — explicit operational policy for Manual or future Broker Auto execution.

Formal research protocols should use train/validation/OOS and walk-forward/purging/embargo when required by label overlap and horizon. Statistical significance alone is insufficient; stability, economic magnitude, cost, capacity and failure conditions matter.

---

## 18. Security and External Boundaries

Keep provider and broker details behind adapters. Credentials and permissions should be separated by capability, especially broker read versus broker trade authority.

Shadow execution must never create broker side effects. Manual execution remains a valid production mode when fills are captured and reconciled.

LLMs/Agents may support policy/event interpretation, research summarization, hypothesis generation and anomaly analysis, but an unversioned LLM response is not Market Fact or Trading Authority. If used as derived evidence, model/prompt/input provenance must be retained.

---

## 19. Architecture Conflict Resolution

The following decisions supersede incompatible lower-level interpretations while remaining subject to the Constitution:

| Historical ambiguity | Canonical decision |
|---|---|
| T+1 versus buy/hold/exit focus | They are independent Strategy Families on one platform |
| One platform-wide candidate gate | Shared objective Eligibility + strategy-specific Candidate Discovery |
| Candidate equals buy decision | Candidate and Entry/Action are separate responsibilities |
| Capital/Theme/Regime directly decide trades | They are shared/contextual intelligence consumed by strategies |
| Forecast means next-day return | Path Forecast is target/horizon-specific and reusable |
| Factor is globally valid/invalid | Evidence is scoped to target/horizon/universe/regime/strategy |
| Model Registry represents full strategy lifecycle | Model and Strategy identities/lifecycles are distinct |
| Multiple daily orchestration surfaces are acceptable | One canonical production control plane; other surfaces are bounded tools/children or retired |
| Qualification is one giant enum | Qualification is multi-dimensional evidence plus admission policy |
| Backtest and live own separate business logic | Reuse domain/strategy semantics; swap clock/data/execution adapters |
| Decision creates Position | Fill-derived physical Position is authoritative |
| Multi-strategy only needs account position | Physical position + strategy sleeves + fill allocation are required |
| Outcome directly tunes production | Outcome creates evidence/challengers; promotion requires requalification |
| Auto execution defines production readiness | Manual production and Auto execution are separate operational modes |

---

## 20. Gap Analysis

### Must Complete

- Multi-Strategy Contract and canonical Strategy Version/Run identity where current code does not yet provide it.
- Strategy-scoped Evidence and Qualification.
- Unified Target/Path Label Authority supporting both Overnight and Swing research.
- Candidate/Entry responsibility convergence and gate-attribution observability.
- Strategy Sleeve + Fill Allocation semantics for real multi-strategy attribution.
- Multi-horizon path dataset/evaluation support for Entry/Hold/Exit research.
- Strategy-level economic evaluation rather than factor/model-only evidence.
- Sufficient PIT/reference coverage for each strategy before Formal PIT claims.
- Simple cross-strategy portfolio/risk baseline.

### Should Complete

- unified factor catalog/evaluation report;
- calibration diagnostics where probabilistic forecasts are claimed;
- regime-conditioned analysis and ablation;
- cost/capacity sensitivity;
- runtime inspection/query/reporting;
- outcome/attribution and strategy comparison reporting;
- prospective Shadow automation and longitudinal stability reports.

### Future Enhancements

- policy/event NLP and alternative data;
- Level-2 microstructure where justified;
- advanced ensembles/meta-models;
- dynamic strategy capital allocation;
- automated broker execution after operational admission.

### Not Needed Now

- microservice decomposition;
- Kafka/event-bus redesign;
- Kubernetes-first deployment;
- graph database;
- generic autonomous-agent trading plane;
- online self-learning Champion mutation;
- reinforcement-learning execution without prior evidence.

---

## 21. Target Architecture Completion Criteria

The target platform is materially achieved when:

1. at least two materially different Strategy Families run through the same canonical platform contracts;
2. each Strategy Version owns explicit target, candidate/decision policy, cost model, evidence and qualification lineage;
3. shared PIT data/features/state are reusable without creating shared trade authority;
4. historical research, replay, Shadow and production use convergent strategy semantics;
5. portfolio/risk can combine simultaneous strategy proposals and reconcile them to fill-derived positions;
6. outcomes and attribution support strategy-level learning without evidence contamination;
7. Formal PIT, Formal OOS, economic support, Prospective Proof and Production Admission remain separately auditable claims;
8. runtime failures are recoverable/replayable within clearly stated proof scope;
9. operators can inspect the current runtime and explain missing or rejected decisions;
10. adding a new strategy requires a Strategy implementation and evidence program, not a new platform or control plane.

---

## 22. Dependency-Ordered Roadmap

### Phase 0 — Architecture Convergence

- Freeze `StrategyContract`, `StrategyVersion`, `StrategyRun`, `ExecutionMode`, and Strategy Registry semantics.
- Classify current runtime/application surfaces as Canonical Runtime, bounded child, research/operator tool, compatibility path, or retired path.
- Freeze further governance/authority proliferation unless justified by a concrete failure mode.

### Phase 1 — Research Foundation

- Build/finish unified Outcome/Target/Path Label Authority.
- Close material PIT/reference gaps needed by the first strategy families.
- Freeze formal dataset identities and decision-time semantics.

### Phase 2 — Alpha and Candidate Diagnostics

- Empirically evaluate existing factor families across explicit targets/horizons.
- Separate objective Eligibility from strategy-specific Ranking/Candidate.
- Add rejection/gate attribution, Recall@K/Top-K and downstream sample diagnostics.

### Phase 3 — Two Reference Strategy Closures

- Preserve and continue the Overnight/T+1 family with its real negative/inconclusive evidence.
- Add the Swing State family with Entry/Hold/Add/Reduce/Exit path targets.
- Prove both can share the same data/state/runtime/evidence infrastructure without new control planes.

### Phase 4 — Portfolio and Position Closure

- Implement/validate Strategy Sleeves, fill allocation, strategy PnL/exposure and physical-position reconciliation.
- Establish simple portfolio baselines before sophisticated optimization.

### Phase 5 — Reliability Convergence

- Remove duplicate orchestration/compatibility paths where safe.
- Re-prove migrations, PostgreSQL integration, retry/recovery/replay and canonical operator inspection.

### Phase 6 — Formal Evaluation

For each Strategy Version independently:

```text
Frozen Dataset
  → Predeclared Evaluation Protocol
  → Walk-forward / Locked OOS
  → Cost / Capacity
  → Economic Evidence
```

### Phase 7 — Prospective Shadow

Run real decision-time data through the canonical strategy runtime without broker side effects; accumulate outcomes, calibration/stability, availability and operational evidence.

### Phase 8 — Manual Production Admission

Admit qualified strategies to human-in-the-loop production. Capture actual decisions/fills/positions/outcomes and continue prospective attribution.

### Phase 9 — Strategy Expansion

Only after the first two families prove the platform contract, add ETF rotation, theme rotation, trend, dividend/long-term, mean-reversion or event strategy families.

### Phase 10 — Future Broker Automation

Only after separate operational qualification, add broker order state, reconciliation, duplicate-order prevention, partial fill/cancel handling, limits and kill switches.

---

## 23. Immediate Highest-Value Work

If only five workstreams are funded next, prioritize:

1. **Multi-Strategy Contract / Strategy Registry convergence.**
2. **Target / Path Label Authority and multi-horizon outcome datasets.**
3. **Candidate / Entry decoupling with explicit gate attribution.**
4. **Overnight + Swing reference strategy closures on the same runtime.**
5. **Strategy Sleeve + simple cross-strategy Portfolio/Risk baseline.**

These maximize information gain and business closure. They are higher priority than another layer of Authority, Receipt, Protocol, or orchestration abstraction.

---

## 24. Canonical Architecture Baseline

The project baseline is:

```text
Market Regime Alpha
=
Multi-Strategy Alpha Research
+ Decision
+ Portfolio
+ Evidence Operating System
```

The platform shares:

```text
Market / Reference Data
PIT Semantics
Feature Infrastructure
Shared Market Intelligence
Research Infrastructure
Portfolio / Risk Infrastructure
Runtime / Reliability Infrastructure
```

Each Strategy Version independently owns or freezes:

```text
Target / Horizon
Strategy-specific Candidate policy
Model / Forecast dependencies
Entry / Holding / Exit policy
Cost / execution assumptions
Evidence lineage
Qualification status
```

All admitted strategy decisions converge through:

```text
Portfolio
→ Risk
→ Decision
→ Execution
→ Fill
→ Position
→ Outcome
→ Attribution
→ Evidence / Qualification
```

Future architecture and implementation work must preserve these boundaries unless a new explicit decision supersedes this design and is reflected through the repository's documentation authority process.
