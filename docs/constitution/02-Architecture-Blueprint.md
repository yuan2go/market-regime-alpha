# The Constitution of Market Regime Alpha

# Volume III — Architecture Blueprint

> **Document:** `docs/constitution/02-Architecture-Blueprint.md`  
> **Status:** Foundational / Normative  
> **Authority:** Project-wide target architecture and responsibility boundaries  
> **Applies to:** Source layout, module ownership, runtime orchestration, research infrastructure, data flow, decision flow, migration, agents, and future production systems  
> **Project:** `market-regime-alpha`  
> **Audit baseline:** Repository state after `00-Project-Vision.md` and `01-Core-Principles.md` were introduced  

---

## 0. Purpose

`00-Project-Vision.md` defines what `market-regime-alpha` is becoming.

`01-Core-Principles.md` defines the rules the project must not silently violate.

This document defines the architecture required to make that vision and those principles operational.

The architecture exists to answer five questions unambiguously:

1. **Which subsystem owns each business responsibility?**
2. **How does information move from raw market data to a research conclusion or trading action?**
3. **Which contracts separate data, features, predictions, position decisions, portfolio decisions and execution?**
4. **How can the current legacy system be preserved while the new architecture is introduced incrementally?**
5. **How can future strategies, factors, data vendors and agents be added without recreating another monolithic rule engine?**

This blueprint does not prescribe the detailed schema of every field, the mathematical definition of every factor, or the validation threshold of every model. Those belong to later Constitution volumes and lower-level specifications.

It does prescribe the following:

- the canonical architectural layers;
- the allowed direction of dependencies;
- the single owner of major domain concepts;
- the canonical end-to-end runtime flows;
- the separation between observation, prediction, decision and execution;
- the role of research infrastructure;
- the role of legacy code;
- the migration model from the current repository to the target platform.

The central architectural rule is:

> **No module may become a universal owner merely because it was the first place where a useful idea was implemented.**

The current repository contains valuable research assets. The target architecture must preserve that knowledge without preserving accidental coupling.

---

# 1. Architectural Context

## 1.1 The current repository and the target platform are not the same thing

The current repository began as an A-share buy/sell-point and dividend-T research system. Its current implementation reflects that history.

Examples include:

- the package namespace `market_regime_alpha.dividend_t` containing a large share of the project's domain logic;
- `DividendTStrategy` producing a simplified F/R/T-driven decision path;
- `CoscoTimingEngine` producing a second, substantially more complex timing path;
- `trend_snapshot.py` running both paths and exposing both `signal` and `timing_action` in the same public row;
- `backtest.py` combining configuration, signal generation, position state, execution constraints, state machines, event accounting and reporting;
- data adapters focused on obtaining normalized OHLCV bars from multiple accessible sources;
- research diagnostics and empirical priors embedded near live model logic.

This implementation is not treated as a mistake. It is treated as the accumulated output of the project's first research phase.

However, the target platform is broader:

> **Market Regime Alpha is an Alpha Research Operating System for the China A-share market.**

Therefore, the target architecture must be organized around stable research and decision responsibilities rather than around one historical strategy package.

---

## 1.2 Current-state audit summary

The architecture audit identifies the following structural conditions.

### 1.2.1 A strategy namespace has become a de facto platform namespace

`src/market_regime_alpha/dividend_t/` currently owns or hosts concepts spanning:

- data interpretation;
- fundamentals;
- technical indicators;
- Chan structure;
- Tuishen-inspired volume-price logic;
- attention;
- certainty;
- memory;
- sell pressure;
- capital-flow proxies;
- market environment;
- signal intent;
- candidate setup codes;
- MACD policy;
- position sizing;
- backtesting;
- hit-rate diagnostics;
- public trend snapshots.

These are not all dividend-T-specific responsibilities.

The package therefore contains reusable research assets but cannot remain the long-term architectural root of the platform.

### 1.2.2 `CoscoTimingEngine` is an integration engine, not an atomic model

The current `CoscoTimingEngine.evaluate()` pipeline performs, in one call, a sequence resembling:

```text
Prepare Bars
    ↓
Reference Levels
    ↓
Daily Context
    ↓
Intraday Context
    ↓
Multi-period Trend
    ↓
Capital-flow Estimate
    ↓
Volume-price Structure
    ↓
Chan Structure
    ↓
Setup Classification
    ↓
Attention
    ↓
Memory
    ↓
Sell Pressure
    ↓
Certainty
    ↓
Dynamic Weights
    ↓
Force Ratio
    ↓
Trend Probability-like Score
    ↓
Breakout Setup
    ↓
Market Regime
    ↓
Manual Candidate Action
    ↓
Additional Buy/Sell Quality Gates
    ↓
Final Timing Snapshot
```

This is useful as a historical integrated research engine.

It is not an appropriate future owner for all of the following at once:

- feature computation;
- feature aggregation;
- market-regime inference;
- candidate generation;
- entry policy;
- exit policy;
- calibration;
- portfolio state;
- execution policy.

The target architecture must separate these concerns while preserving the ability to replay the legacy engine unchanged during migration.

### 1.2.3 The public snapshot path contains two decision authorities

`trend_snapshot.py` currently:

1. computes technical inputs and retreat inputs;
2. runs `DividendTStrategy.evaluate()`;
3. separately runs `CoscoTimingEngine.evaluate()`;
4. exposes the simplified strategy result as `signal`;
5. exposes the complex timing result as `timing_action`.

This means a single public row can contain two independently generated action semantics.

The target architecture must not solve this by hiding one field in the UI.

It must solve it architecturally:

> **There must be exactly one authoritative decision path for a given decision scope.**

Alternative models may coexist as research models, shadow models, diagnostics or ensemble inputs, but only one component may own the final decision contract for that scope.

### 1.2.4 `backtest.py` contains multiple independent domains

The current backtest module includes, directly or indirectly:

- a very large configuration surface;
- signal evaluation;
- market-regime and stock-regime state;
- attack state;
- beta-hold state;
- base and T-position state;
- candidate-entry state;
- follow-through state;
- buyback state;
- execution costs;
- A-share T+1 constraints;
- limit-price constraints;
- suspension constraints;
- corporate actions;
- event accounting;
- performance metrics;
- signal and equity-curve snapshots;
- cache identity and research experiment concerns.

This is a classic responsibility accumulation pattern.

The target architecture does not require an immediate rewrite. It requires extraction by explicit owner.

### 1.2.5 Useful contracts already exist, but they are scoped to the legacy domain

The repository already contains valuable contract-oriented work, including:

- `SignalIntent`;
- `PrimarySetupCode`;
- `CandidateSignal`;
- `DecisionTrace`;
- `RiskEnforcement`;
- candidate validation;
- explicit decision and confirmation bar times;
- MACD policy identity;
- experiment identity concepts;
- data-source attempt metadata.

These are architectural assets.

The target system should preserve the design intent while preventing legacy enum values such as `BUY_T` or `SELL_T` from becoming universal platform semantics.

### 1.2.6 Current data adapters solve access, not formal research truth

The current `a_share_bars.py` adapter layer normalizes accessible providers into a shared OHLCV-like schema.

That is useful for exploratory research and operational convenience.

The formal data audit, however, establishes that the project currently lacks complete proof for:

- `bar_final` provenance;
- point-in-time adjustment;
- point-in-time universe membership;
- historical ST and suspension state;
- historical limit-price regime and limit prices;
- historical industry/theme mappings;
- complete market sidecars;
- data licensing and provenance needed for formal research promotion.

Therefore the target architecture must distinguish:

```text
Can Fetch Data
        ≠
Can Reproduce Data
        ≠
Can Prove Point-in-Time Availability
        ≠
Can Use Data for Formal Promotion
```

### 1.2.7 Research evidence has leaked into model implementation

Examples include:

- buy-point empirical priors hard-coded from a current local sample;
- heuristic probability-like fields exposed as probabilities;
- legacy hit-rate diagnostics used near model-quality decisions;
- fixed fallback fundamental inputs in public snapshot generation.

The architecture must separate:

```text
Research Result
    ↓ optional promotion
Versioned Model Artifact
    ↓ controlled loading
Runtime Inference
```

A research report is not a runtime configuration source unless explicitly promoted and versioned.

---

# 2. Architectural Objective

The target system must allow the project to evolve from:

```text
Strategy-specific integrated engines
```

into:

```text
A shared research and decision platform
containing multiple independently testable strategies
```

The architecture must support the following without structural rewrites:

- candidate discovery across the A-share market;
- market-regime models;
- ETF and theme rotation models;
- overnight or next-session opportunity models;
- multi-day trend continuation models;
- independent entry models;
- independent position-lifecycle policies;
- independent exit models;
- dividend/long-term strategies;
- manual research workflows;
- future broker-connected execution;
- multiple data providers;
- multiple model families;
- rule baselines and statistical models;
- shadow evaluation of competing models;
- walk-forward and out-of-sample validation;
- model degradation and retirement.

The architecture must not assume that one strategy, one factor family, one data provider or one model type will remain dominant.

---

# 3. Canonical Architecture

The canonical platform architecture is:

```text
┌──────────────────────────────────────────────────────────────────────┐
│                        Interfaces / Applications                     │
│   CLI · Jobs · API · Dashboard · Reports · Agent Use Cases          │
└──────────────────────────────────────┬───────────────────────────────┘
                                       │
                                       ▼
┌──────────────────────────────────────────────────────────────────────┐
│                         Application Orchestration                    │
│  Research Runs · Daily Scans · Position Review · Portfolio Review   │
└──────────────┬───────────────────┬───────────────────┬───────────────┘
               │                   │                   │
               ▼                   ▼                   ▼
┌──────────────────────┐  ┌──────────────────────┐  ┌──────────────────┐
│ Candidate & Strategy │  │ Portfolio & Risk     │  │ Research System  │
│ Candidate Discovery  │  │ Portfolio Decision   │  │ Backtest/Replay  │
│ Entry                 │  │ Exposure             │  │ Walk Forward     │
│ Position Lifecycle    │  │ Capital Allocation   │  │ Ablation         │
│ Exit                  │  │ Concentration        │  │ Calibration      │
└──────────┬───────────┘  └──────────┬───────────┘  └─────────┬────────┘
           │                         │                        │
           └──────────────┬──────────┴──────────────┬─────────┘
                          │                         │
                          ▼                         ▼
              ┌────────────────────┐     ┌────────────────────┐
              │ Market Context     │     │ Execution          │
              │ Market Regime      │     │ A-share Rules      │
              │ ETF Rotation       │     │ Fill Simulation    │
              │ Theme Rotation     │     │ Broker Adapters     │
              └──────────┬─────────┘     └──────────┬─────────┘
                         │                          │
                         ▼                          │
              ┌────────────────────┐                │
              │ Feature System     │                │
              │ Registry           │                │
              │ Lineage            │                │
              │ Feature Frames     │                │
              └──────────┬─────────┘                │
                         │                          │
                         ▼                          │
              ┌────────────────────┐                │
              │ Universe System    │                │
              │ Tradability        │                │
              │ Security Master    │                │
              │ Industry/Theme Map │                │
              └──────────┬─────────┘                │
                         │                          │
                         ▼                          ▼
┌──────────────────────────────────────────────────────────────────────┐
│                           Data Platform                              │
│ Providers · Adapters · PIT · Quality · Dataset Builder · Manifests  │
└──────────────────────────────────────┬───────────────────────────────┘
                                       │
                                       ▼
┌──────────────────────────────────────────────────────────────────────┐
│                         Core / Control Plane                         │
│ Identity · Time Semantics · Contracts · Registry IDs · Trace IDs    │
└──────────────────────────────────────────────────────────────────────┘
```

This diagram expresses responsibility, not necessarily process deployment.

The project may continue to run as a local Python application for a long period. Architectural separation does not require microservices.

> **The default deployment model is a modular monolith with strict internal boundaries.**

Microservices are not an architectural goal.

---

# 4. The Core / Control Plane

## 4.1 Purpose

The Core / Control Plane contains the smallest set of concepts that every major subsystem needs to agree on.

It must remain strategy-neutral and vendor-neutral.

It owns concepts such as:

- research run identity;
- decision time;
- as-of time;
- availability time;
- dataset identity;
- feature-set identity;
- model identity;
- strategy identity;
- execution-model identity;
- trace identity;
- contract versions;
- common validation errors.

It must not own:

- MACD rules;
- Chan rules;
- Tuishen rules;
- ETF ranking formulas;
- dividend strategy thresholds;
- broker-specific APIs;
- data-vendor-specific field names.

## 4.2 Core invariants

The Core / Control Plane must enforce several distinctions.

### Event time is not availability time

```text
Event Time
    = when the market event occurred

Availability Time
    = when the information became legally and technically available to the model

Decision Time
    = when the system is allowed to form a decision

Execution Time
    = when the market could execute the resulting request
```

These timestamps may differ.

### A model version is not a code commit

A model identity may include:

- implementation version;
- parameters;
- feature-set version;
- training dataset identity;
- calibration artifact;
- code commit.

Git commit identity is necessary for reproducibility but is not sufficient as the entire model identity.

### A trace ID is not a report row number

Every significant research or decision flow must be traceable independently of its final presentation surface.

---

# 5. Data Platform

## 5.1 Architectural responsibility

The Data Platform owns the transformation from external information sources into versioned, auditable, queryable research data.

Its responsibilities are:

```text
External Provider
        ↓
Provider Adapter
        ↓
Raw Ingestion Artifact
        ↓
Normalization
        ↓
Point-in-Time Semantics
        ↓
Quality Validation
        ↓
Dataset Build
        ↓
Dataset Manifest
        ↓
Approved Research Dataset
```

The Data Platform owns whether data is eligible for a given research class.

No strategy may silently upgrade exploratory data into formal research data.

## 5.2 Data access and data truth are separate layers

The current provider layer is valuable and should be preserved.

However, future architecture must separate:

### Provider Access

Examples:

- Tencent;
- EastMoney;
- BaoStock;
- Tushare;
- QMT/XtQuant;
- future Xuntou or commercial data vendor;
- local files.

### Canonical Data Contract

Examples:

- normalized security identifiers;
- interval semantics;
- timestamp semantics;
- finalization state;
- adjustment state;
- source provenance;
- retrieval time;
- revision policy.

### Research Eligibility

Examples:

- exploratory;
- rehearsal;
- formal candidate;
- sealed-test eligible;
- production eligible.

The existence of a DataFrame is not evidence of research eligibility.

## 5.3 Data Platform output

The Data Platform must produce immutable or content-addressable dataset identities.

A downstream module consumes:

```text
Dataset ID
+ As-of Rules
+ Canonical Data Contract
```

not merely:

```text
some local CSV path
```

Detailed data rules belong to `04-Data-Constitution.md`.

---

# 6. Universe System

## 6.1 Purpose

The Universe System owns the answer to:

> **Which securities were eligible to be considered at a specific decision time?**

This is different from candidate selection.

The Universe System owns:

- security master identity;
- exchange membership;
- listing and delisting status;
- ST status;
- suspension state;
- tradability;
- liquidity eligibility;
- IPO-age filters;
- point-in-time index membership;
- point-in-time ETF constituents when available;
- point-in-time industry/theme mappings;
- strategy-specific eligibility views built from canonical rules.

It does not own:

- which security is attractive;
- which security should be bought;
- market-regime inference;
- portfolio weights.

## 6.2 Canonical output

The primary output is a versioned `TradableUniverseSnapshot`-like contract containing, conceptually:

```text
universe_id
as_of_time
symbol
eligibility
tradability_flags
classification_refs
rejection_reasons
source_identity
```

The exact schema will be specified later.

## 6.3 Why the Universe System is separate

Candidate Discovery is a ranking problem.

Universe construction is an eligibility problem.

Combining them creates survivorship bias, hidden filtering and irreproducible candidate pools.

---

# 7. Feature System

## 7.1 Purpose

The Feature System converts approved source information into versioned measurable representations.

It owns:

- feature definitions;
- feature implementation registration;
- source-column lineage;
- lookback requirements;
- frequency;
- availability rules;
- missingness policy;
- raw versus transformed feature identity;
- normalization identity;
- feature-set assembly;
- feature materialization.

It does not own:

- whether a stock should be bought;
- portfolio weights;
- final probability calibration;
- execution.

## 7.2 Feature families are first-class

Feature families may include:

- price momentum;
- trend;
- volatility;
- liquidity;
- volume-price structure;
- capital flow;
- microstructure;
- fundamental;
- valuation;
- event;
- market breadth;
- ETF strength;
- theme strength;
- Chan structure;
- Tuishen-inspired structure;
- MACD;
- relative strength.

A feature name does not prove informational independence.

Therefore the Feature System must expose lineage sufficient for the Research System to test:

- correlation;
- factor clusters;
- duplicate information paths;
- incremental contribution;
- ablation impact.

Detailed factor governance belongs to `05-Factor-Constitution.md`.

## 7.3 Atomic features before composite decisions

The target architecture prefers:

```text
Atomic / explainable feature outputs
        ↓
Explicit model or rule composition
```

instead of:

```text
A large helper function returning a final score
whose internal sources cannot be independently tested
```

Composite features are allowed, but their dependencies must remain explicit.

---

# 8. Market Context System

## 8.1 Purpose

The Market Context System describes the environment in which opportunities are evaluated.

It owns contextual models such as:

- broad market regime;
- risk-on / neutral / risk-off state;
- market breadth;
- liquidity regime;
- volatility regime;
- style regime;
- ETF strength and rotation state;
- industry strength;
- theme strength;
- hotspot lifecycle;
- leader resonance;
- crowding or exhaustion indicators.

## 8.2 Market context is not a direct order generator

A market-regime model may:

- change candidate priors;
- filter a universe;
- alter risk budget;
- change model selection;
- change portfolio concentration limits.

It must not directly place an order.

## 8.3 ETF Rotation in the architecture

ETF Rotation initially belongs here as an upstream market-context capability.

Its first responsibility is:

```text
Rank ETF / Industry / Theme Strength
        ↓
Identify Active Directions
        ↓
Provide Context and Candidate-Universe Constraints
```

A future ETF trading strategy may also exist under the Strategy System.

These are different responsibilities:

```text
ETF Rotation as Context
        ≠
ETF Rotation as Tradable Strategy
```

---

# 9. Candidate Discovery System

## 9.1 Purpose

Candidate Discovery is the first strategic priority of the refounded project.

It answers:

> **Given the point-in-time tradable universe and current market context, which securities deserve further decision attention?**

Candidate Discovery owns:

- cross-sectional scoring;
- cross-sectional ranking;
- candidate eligibility after feature availability;
- model inference for opportunity targets;
- candidate confidence;
- expected return estimates when supported;
- expected favorable excursion estimates when supported;
- expected adverse excursion estimates when supported;
- candidate setup classification;
- candidate-level invalidation signals;
- ranking explanations;
- top-N candidate selection before portfolio constraints.

It does not own:

- actual position size;
- whether an existing position should be reduced;
- final portfolio composition;
- order execution.

## 9.2 Candidate prediction is not a trade decision

The canonical distinction is:

```text
CandidatePrediction
        ↓
Entry / Position Lifecycle Evaluation
        ↓
Portfolio Decision
        ↓
Execution Request
```

A high candidate score may still result in no trade because of:

- entry quality;
- market risk;
- portfolio concentration;
- current position state;
- T+1 constraints;
- insufficient liquidity;
- better competing opportunities;
- stale data;
- invalidation conditions.

## 9.3 Cross-sectional architecture

The Candidate Discovery System must be capable of processing:

```text
One decision time
×
Many symbols
```

This is fundamentally different from repeatedly invoking a single-symbol timing engine without cross-sectional normalization.

It must support:

- rank normalization;
- sector or theme concentration analysis;
- comparable feature scaling;
- missingness awareness;
- duplicate-candidate suppression;
- candidate diversity;
- model score calibration.

---

# 10. Strategy System

## 10.1 Purpose

The Strategy System owns decision policies applied after candidate information and context are available.

The canonical strategic responsibilities are separated into:

```text
Entry
Position Lifecycle
Exit
```

A strategy may implement one, two or all three, but the contracts remain separate.

## 10.2 Entry System

The Entry System answers:

> **Should the portfolio initiate or increase exposure to this opportunity now?**

It may consider:

- candidate rank;
- setup quality;
- entry location;
- liquidity;
- invalidation distance;
- expected reward/risk;
- market context;
- portfolio state.

It outputs an entry proposal, not a broker order.

## 10.3 Position Lifecycle System

The Position Lifecycle System owns the state transition of an existing position.

Canonical actions include:

```text
HOLD
ADD
REDUCE
ROTATE
EXIT
```

A strategy-specific vocabulary may contain more detailed subtypes, but the platform-level lifecycle must remain stable.

The Position Lifecycle System owns:

- current lifecycle state;
- state transition rules;
- position-level invalidation;
- holding thesis state;
- opportunity-cost review;
- add/reduce eligibility;
- rotation proposal.

It does not own portfolio-wide capital allocation.

## 10.4 Exit System

The Exit System is not defined as the inverse of Entry.

It answers:

> **Given an existing position, what evidence indicates that the remaining expected value no longer justifies the risk or opportunity cost?**

It may evaluate:

- trend continuation probability;
- exhaustion;
- distribution;
- structure break;
- theme retreat;
- fund outflow;
- invalidation;
- trailing risk;
- alternative opportunity quality.

A fixed time exit may exist as a strategy rule, but it is one exit policy among many.

## 10.5 Strategy registry

Every strategy must have a stable identity and declare:

- strategy purpose;
- supported asset universe;
- required inputs;
- decision frequency;
- target horizon;
- entry responsibility;
- lifecycle responsibility;
- exit responsibility;
- portfolio assumptions;
- execution assumptions;
- validation state;
- version.

Detailed strategy governance belongs to `06-Strategy-Constitution.md`.

---

# 11. Portfolio System

## 11.1 Purpose

The Portfolio System is the only owner of portfolio-level capital allocation.

It receives candidate and lifecycle proposals and decides what the portfolio may actually hold.

It owns:

- portfolio risk budget;
- symbol concentration;
- industry concentration;
- theme concentration;
- ETF exposure;
- gross and net exposure where relevant;
- cash reserve;
- turnover budget;
- position sizing;
- competing opportunity allocation;
- rebalance decisions.

It does not own:

- raw feature computation;
- candidate model inference;
- broker fills.

## 11.2 Position-level proposals do not own capital

A strategy may propose:

```text
ADD 20%
```

but only the Portfolio System can interpret that within total capital constraints.

This prevents the historical pattern where multiple state machines each independently behave as partial position-size owners.

## 11.3 One portfolio authority

There must be one authoritative `PortfolioDecision` for a given portfolio and decision cycle.

Multiple strategies may contribute proposals.

They may not independently mutate shared portfolio capital.

---

# 12. Execution System

## 12.1 Purpose

The Execution System owns the difference between a desired portfolio change and what the A-share market can actually execute.

It owns:

- A-share lot size;
- T+1 sellability;
- suspension;
- limit-up and limit-down constraints;
- commissions;
- stamp duty;
- slippage models;
- fill models;
- next-bar execution semantics;
- partial fills when modeled;
- corporate-action execution effects;
- broker adapters in future production.

## 12.2 Execution is downstream of portfolio decisions

The allowed direction is:

```text
PortfolioDecision
        ↓
ExecutionRequest
        ↓
ExecutionPolicy / Market Constraints
        ↓
ExecutionResult
        ↓
Portfolio State Update
```

A signal engine must not bypass the Portfolio System and create broker orders directly.

## 12.3 Simulation and live execution share contracts, not implementations

Backtesting and future broker connectivity should share:

- request semantics;
- constraint semantics;
- result semantics.

They should not share hidden state or assume identical fill mechanics.

The Execution System may therefore contain:

```text
Execution Contracts
    ├── Historical Simulator
    ├── Paper Adapter
    ├── Manual Export Adapter
    └── Future Broker Adapter
```

---

# 13. Research System

## 13.1 Purpose

The Research System owns the evidence lifecycle.

It is not merely a `backtest()` function.

It owns:

- experiment identity;
- baseline comparison;
- historical replay;
- backtesting;
- walk-forward analysis;
- out-of-sample analysis;
- sealed-test access control;
- ablation;
- feature analysis;
- calibration;
- counterfactual analysis;
- robustness analysis;
- result manifests;
- promotion evidence;
- degradation monitoring;
- retirement evidence.

## 13.2 Production/domain modules must not import research code

The dependency rule is:

```text
Research may orchestrate domain components.
Domain components may not depend on Research.
```

This prevents runtime logic from depending on test reports, local research files or experiment-only state.

## 13.3 Backtest decomposition

The current backtest God Object must be decomposed toward explicit owners.

The target responsibilities are:

```text
research/
    replay_orchestrator
    experiment_runner
    metrics
    reporting
    counterfactual

portfolio/
    portfolio_state
    allocation
    concentration

strategies/
    position_lifecycle
    entry_policy
    exit_policy

execution/
    simulator
    a_share_constraints
    transaction_costs
    corporate_actions

core/
    event_ledger_contracts
    identity
    trace
```

The exact file names may vary.

The architectural rule does not:

> “Split one 8,000-line file into many files.”

The rule is:

> **Move each state transition and decision responsibility to its single authoritative owner.**

## 13.4 The future backtest orchestrator

The final orchestration flow should resemble:

```text
Load Experiment Identity
        ↓
Resolve Approved Dataset
        ↓
Build Point-in-Time Universe
        ↓
Materialize Features
        ↓
Evaluate Market Context
        ↓
Generate Candidates
        ↓
Evaluate Strategy Proposals
        ↓
Construct Portfolio Decision
        ↓
Simulate Execution
        ↓
Update State
        ↓
Record Events and Traces
        ↓
Compute Metrics
        ↓
Write Immutable Result Manifest
```

The orchestrator coordinates.

It does not contain strategy thresholds.

---

# 14. Application Orchestration

## 14.1 Why an application layer is required

The current repository often allows presentation or scheduling code to instantiate deep domain engines directly.

For example, a snapshot builder can create strategy and timing engines itself.

This makes the presentation layer an accidental composition root.

The target architecture introduces explicit application use cases.

Examples:

```text
RunDailyCandidateScan
EvaluateHeldPositions
RunPortfolioReview
RunHistoricalExperiment
BuildResearchReport
PublishDashboardSnapshot
```

The Application layer owns orchestration of a use case.

It does not own domain rules.

## 14.2 Composition root

Provider implementations, model versions and strategy versions are selected at an application composition boundary.

Deep domain modules should not discover global providers, local paths or current model versions on their own.

This allows:

- controlled experiments;
- dependency injection;
- deterministic replay;
- shadow-model evaluation;
- easier migration.

---

# 15. Interfaces

Interfaces include:

- CLI;
- scheduled jobs;
- APIs;
- dashboards;
- GitHub Pages snapshots;
- report generation;
- manual trading exports;
- agent workflows.

Interfaces are consumers of application use cases.

They must not become alternative decision engines.

The target rule is:

```text
Interface
    ↓
Application Use Case
    ↓
Authoritative Domain Flow
```

not:

```text
Dashboard
    ├── Simplified Strategy
    ├── Timing Engine
    ├── Extra Local Rules
    └── Final Display Logic That Implicitly Chooses a Winner
```

---

# 16. Canonical Contracts

This section defines architectural contracts at a conceptual level. Detailed schemas belong in `docs/specs/` and later Constitution volumes.

## 16.1 `ResearchContext`

Identifies the context in which a research or decision run occurred.

Conceptually contains:

```text
run_id
as_of_time
dataset_id
universe_id
feature_set_id
market_context_model_id
candidate_model_id
strategy_id
portfolio_policy_id
execution_model_id
code_revision
```

## 16.2 `TradableUniverseSnapshot`

Represents point-in-time eligibility.

It answers:

```text
Which securities could legally and operationally be considered?
```

## 16.3 `FeatureDefinition`

Defines one feature's identity and lineage.

## 16.4 `FeatureFrame`

Represents materialized feature values at explicit decision times.

## 16.5 `MarketContextSnapshot`

Represents market, ETF, industry and theme context used by downstream models.

## 16.6 `CandidatePrediction`

Represents a model's opportunity assessment.

Conceptually includes:

```text
symbol
decision_time
target_horizon
raw_score
calibrated_probability, when valid
expected_return, when valid
expected_mfe, when valid
expected_mae, when valid
setup_codes
risk_flags
invalidation_conditions
feature_contributions
model_identity
trace_id
```

A `CandidatePrediction` is not an order.

## 16.7 `PositionLifecycleState`

Represents the current state and thesis of an existing position.

## 16.8 `PositionActionProposal`

Represents a strategy proposal such as:

```text
HOLD
ADD
REDUCE
ROTATE
EXIT
```

It is not a portfolio mutation.

## 16.9 `PortfolioDecision`

Represents the single authoritative portfolio-level allocation decision for a decision cycle.

## 16.10 `ExecutionRequest`

Represents an executable desired change after portfolio policy.

## 16.11 `ExecutionResult`

Represents simulated or real execution outcome.

## 16.12 `DecisionTrace`

Links:

```text
Data Identity
    ↓
Universe Eligibility
    ↓
Features
    ↓
Market Context
    ↓
Candidate Prediction
    ↓
Strategy Proposal
    ↓
Portfolio Decision
    ↓
Execution Result
```

The existing legacy `DecisionTrace` is a valuable precursor but is not automatically the final platform-wide schema.

## 16.13 `ExperimentIdentity`

Provides immutable identity for research results.

It must prevent a result from being interpreted without knowing:

- data;
- features;
- model;
- strategy;
- portfolio policy;
- execution assumptions;
- code version.

---

# 17. Decision Authority Model

The architecture defines a strict authority ladder.

```text
Raw Observation
        │
        │ cannot decide
        ▼
Feature
        │
        │ cannot decide
        ▼
Market Context / Candidate Prediction
        │
        │ can rank and assess, cannot allocate capital
        ▼
Strategy Proposal
        │
        │ can propose lifecycle action, cannot mutate shared portfolio
        ▼
Portfolio Decision
        │
        │ can allocate capital, cannot assume execution success
        ▼
Execution Request
        │
        ▼
Execution Result
        │
        ▼
Authoritative State Update
```

This ladder eliminates several classes of ambiguity.

A feature named `sell_pressure` is not a sell order.

A `BUY_T_TIMING`-like legacy setup is not automatically a portfolio buy.

A high predicted probability is not automatically an entry.

A position-level add proposal is not automatically a portfolio allocation.

An execution request is not automatically a fill.

---

# 18. Single Ownership Matrix

| Concept | Authoritative owner | Allowed consumers | Must not own |
| --- | --- | --- | --- |
| External data access | Data Platform adapters | Data ingestion | Strategy decisions |
| Dataset eligibility | Data Platform | All research modules | Candidate ranking |
| Tradable universe | Universe System | Market, candidate, strategy, portfolio | Alpha ranking |
| Feature definition | Feature System | Research and models | Orders |
| Feature lineage | Feature System | Research, validation | Portfolio sizing |
| Market regime | Market Context System | Candidate, strategy, portfolio | Broker execution |
| ETF/theme context | Market Context System | Candidate, strategy | Final portfolio authority |
| Candidate ranking | Candidate Discovery | Entry, portfolio, research | Position mutation |
| Entry proposal | Entry System | Portfolio | Broker fills |
| Position lifecycle state | Position Lifecycle System | Portfolio, research | Portfolio-wide capital |
| Exit proposal | Exit System | Portfolio | Data quality decisions |
| Portfolio allocation | Portfolio System | Execution, reporting | Data ingestion |
| A-share execution constraints | Execution System | Research, future production | Alpha discovery |
| Execution result | Execution System | Portfolio state, research | Model training |
| Experiment identity | Research/Core | Research, reports | Strategy rules |
| Promotion evidence | Research/Validation | Governance | Runtime signal generation |
| Presentation | Interfaces | Users | Independent final decision rules |

If two modules appear to own the same row in this table, the architecture is drifting.

---

# 19. Dependency Rules

The target codebase is a modular monolith with enforced dependency direction.

## 19.1 Base dependency direction

Conceptually:

```text
core
  ↑
data
  ↑
universe
  ↑
features
  ↑
market context
  ↑
candidates
  ↑
strategies
  ↑
portfolio
  ↑
execution contracts
```

Research and Application orchestration may depend across these modules to compose use cases.

Interfaces depend on Application.

Legacy adapters may depend on legacy code and translate into new contracts.

## 19.2 Explicit prohibitions

### Core must not import strategy packages

Core contracts cannot depend on `dividend_t`, overnight models, ETF rotation or future strategies.

### Data adapters must not import strategy logic

Provider code cannot know what constitutes a buy point.

### Feature modules must not import portfolio state

A feature is a measurement, not a capital decision.

### Strategies must not read research reports as hidden runtime inputs

Promoted artifacts must be versioned and loaded through explicit model/configuration mechanisms.

### Interfaces must not choose between competing final signals

Signal arbitration belongs in an authoritative domain/application flow.

### Production modules must not import research-only diagnostics

Research can inspect production components. Production cannot depend on ad hoc research output.

---

# 20. Target Package Structure

The target package structure is:

```text
src/market_regime_alpha/
│
├── core/
│   ├── identity/
│   ├── time/
│   ├── contracts/
│   ├── tracing/
│   └── errors/
│
├── data/
│   ├── contracts/
│   ├── adapters/
│   ├── ingestion/
│   ├── point_in_time/
│   ├── quality/
│   ├── datasets/
│   └── manifests/
│
├── universe/
│   ├── security_master/
│   ├── tradability/
│   ├── classifications/
│   └── builders/
│
├── features/
│   ├── registry/
│   ├── price_volume/
│   ├── capital_flow/
│   ├── microstructure/
│   ├── fundamentals/
│   ├── valuation/
│   ├── chan/
│   ├── tuishen/
│   ├── macd/
│   └── materialization/
│
├── market/
│   ├── regime/
│   ├── breadth/
│   ├── etf_rotation/
│   ├── theme_rotation/
│   └── hotspot_lifecycle/
│
├── candidates/
│   ├── contracts/
│   ├── ranking/
│   ├── calibration/
│   ├── selection/
│   └── models/
│
├── strategies/
│   ├── contracts/
│   ├── entry/
│   ├── position_lifecycle/
│   ├── exit/
│   ├── overnight/
│   ├── etf_rotation/
│   └── dividend_t/
│
├── portfolio/
│   ├── state/
│   ├── allocation/
│   ├── sizing/
│   ├── concentration/
│   └── risk/
│
├── execution/
│   ├── contracts/
│   ├── a_share_rules/
│   ├── simulation/
│   ├── costs/
│   └── adapters/
│
├── research/
│   ├── experiments/
│   ├── replay/
│   ├── backtest/
│   ├── walk_forward/
│   ├── ablation/
│   ├── calibration/
│   ├── factor_analysis/
│   ├── counterfactual/
│   └── reporting/
│
├── application/
│   ├── candidate_scan/
│   ├── position_review/
│   ├── portfolio_review/
│   ├── research_run/
│   └── publishing/
│
├── interfaces/
│   ├── cli/
│   ├── web/
│   ├── jobs/
│   └── reports/
│
└── legacy/
    └── adapters/
```

This is a target responsibility map, not an instruction to immediately move every file.

The project must not perform a mass rename solely to make the tree look correct.

A module moves only when:

1. its target owner is clear;
2. its behavior is protected by tests or characterization evidence;
3. its public compatibility path is understood;
4. the move reduces ambiguity rather than merely changing paths.

---

# 21. Legacy Compatibility Architecture

## 21.1 Legacy is a supported migration state

The project will not rewrite all existing research logic before new work can continue.

The migration model is:

```text
Legacy Engine
      │
      ▼
Compatibility Adapter
      │
      ▼
Canonical V2 Contract
      │
      ▼
New Application / Research Flow
```

This allows legacy behavior to be:

- replayed;
- compared;
- shadow-run;
- ablated;
- gradually replaced.

## 21.2 Legacy modules are not automatically deprecated

A module can be:

- **Preserve** — valuable and already well-bounded;
- **Adapt** — valuable but uses legacy contracts;
- **Extract** — contains reusable capability mixed with unrelated responsibility;
- **Freeze** — maintain for reproducibility but do not extend;
- **Retire** — remove only after replacement and evidence.

## 21.3 Current migration map

### `data_sources/a_share_bars.py`

**Current value:** multi-source access and normalization.  
**Target:** extract provider adapters into the Data Platform; preserve a compatibility facade temporarily.  
**Action:** **Adapt + Extract.**

### `dividend_t/models.py`

**Current value:** stable legacy contracts for the dividend-T strategy.  
**Target:** keep as strategy-local contracts while platform-neutral contracts move to `core`, `candidates`, `portfolio` and `execution`.  
**Action:** **Preserve + Scope.**

The platform must not redefine the global action model around `BUY_T`, `SELL_T` and `BUILD_BASE`.

### `dividend_t/signal_intent.py`

**Current value:** explicit intent mapping, setup ownership, candidate validation and trace discipline.  
**Target:** preserve the design principles; map legacy setup semantics into platform-level candidate and lifecycle contracts.  
**Action:** **Preserve + Adapt.**

### `dividend_t/strategy.py`

**Current value:** simplified dividend-T strategy baseline.  
**Target:** a named legacy strategy implementation under the Strategy System.  
**Action:** **Freeze new platform expansion; preserve as baseline.**

### `dividend_t/cosco_timing.py`

**Current value:** rich integrated research engine containing many useful signal ideas.  
**Target:** remain replayable while reusable feature calculations and strategy policies are extracted incrementally.  
**Action:** **Freeze expansion + Extract by responsibility.**

It must not become the V2 Candidate Discovery engine.

### `dividend_t/cosco_timing_daily.py`

**Current value:** daily context and multi-period trend logic.  
**Known issue:** `_dynamic_fundamental_score()` blends price/MA/drawdown information into a field named fundamental score.  
**Target:** separate fundamental information from technical/trend context.  
**Action:** **Extract + Correct semantic ownership.**

### `dividend_t/trend_snapshot.py`

**Current value:** public aggregation and publishing path.  
**Known issue:** invokes both simplified and complex decision paths.  
**Target:** become an interface/publishing consumer of one authoritative application use case.  
**Action:** **Refactor composition boundary.**

### `dividend_t/backtest.py`

**Current value:** extensive A-share simulation knowledge and strategy state behavior.  
**Target:** decompose into explicit research, strategy, portfolio and execution owners.  
**Action:** **Characterize + Extract incrementally.**

No big-bang rewrite.

### `dividend_t/buy_point_quality.py`

**Current value:** subtype classification and historical empirical observations.  
**Known issue:** empirical priors are hard-coded from a current local sample.  
**Target:** subtype classification may remain code; learned priors must become versioned research/model artifacts with train/validation isolation.  
**Action:** **Split taxonomy from empirical artifact.**

### `dividend_t/point_hit_rate.py`

**Current value:** historical timing diagnostic.  
**Current code already marks it as legacy diagnostic only.  
**Target:** preserve under Research diagnostics; never treat as the universal sell-side evaluation contract.  
**Action:** **Preserve + Reclassify.**

---

# 22. Canonical Runtime Flows

## 22.1 Daily Candidate Discovery Flow

```text
Resolve Research / Decision Context
        ↓
Resolve Approved Data as of Decision Time
        ↓
Build Tradable Universe Snapshot
        ↓
Materialize Feature Set
        ↓
Evaluate Market / ETF / Theme Context
        ↓
Run Candidate Model(s)
        ↓
Calibrate Where Valid
        ↓
Apply Candidate Eligibility Rules
        ↓
Cross-sectional Rank
        ↓
Produce CandidatePrediction Set
        ↓
Persist Decision Trace
```

This flow may end without any trade action.

## 22.2 New Position Entry Flow

```text
CandidatePrediction
        ↓
Entry Policy
        ↓
PositionActionProposal(ADD/ENTER-like intent)
        ↓
Portfolio Constraints
        ↓
PortfolioDecision
        ↓
ExecutionRequest
        ↓
ExecutionResult
        ↓
Position State Update
```

## 22.3 Existing Position Review Flow

```text
Current Position State
        +
Latest Candidate / Continuation Assessment
        +
Market Context
        +
Exit Evidence
        +
Opportunity Cost
        ↓
Position Lifecycle Evaluation
        ↓
HOLD / ADD / REDUCE / ROTATE / EXIT Proposal
        ↓
Portfolio Decision
        ↓
Execution
```

This is the canonical replacement for a fixed “sell next morning” assumption.

## 22.4 Historical Research Flow

```text
Experiment Identity
        ↓
Dataset Manifest
        ↓
Point-in-Time Replay
        ↓
Universe Snapshot per Decision Time
        ↓
Feature Materialization
        ↓
Model / Strategy Evaluation
        ↓
Portfolio Construction
        ↓
Execution Simulation
        ↓
Event Ledger
        ↓
Metrics
        ↓
Validation / Ablation / Attribution
        ↓
Immutable Research Result
```

## 22.5 Future Production Flow

The future production flow must reuse the same decision contracts while changing data freshness and execution adapters.

```text
Live/Finalized Data
        ↓
Canonical Data Contract
        ↓
Same Feature / Model / Strategy Contracts
        ↓
Portfolio Decision
        ↓
Production Execution Adapter
```

The project does not currently authorize automatic production execution.

---

# 23. State Ownership

State must have one owner.

## 23.1 Data state

Owned by the Data Platform.

Examples:

- ingestion status;
- raw artifact hashes;
- dataset build status;
- quality gates.

## 23.2 Candidate model state

Owned by the Candidate model or model registry.

Examples:

- model version;
- calibration artifact;
- training identity.

## 23.3 Position lifecycle state

Owned by the Position Lifecycle System.

Examples:

- current lifecycle stage;
- entry thesis;
- invalidation status;
- add/reduce history;
- trailing state.

## 23.4 Portfolio state

Owned by the Portfolio System.

Examples:

- cash;
- target weights;
- current weights;
- concentration;
- exposure budgets.

## 23.5 Execution state

Owned by the Execution System.

Examples:

- pending requests;
- fills;
- rejected orders;
- sellable shares;
- transaction costs.

## 23.6 Research experiment state

Owned by the Research System.

Examples:

- run status;
- artifact identity;
- sealed-test access state;
- promotion state.

A single boolean or counter must not be independently maintained by multiple layers.

---

# 24. Time Semantics Architecture

A market research system can be architecturally clean and still be invalid because of time leakage.

Therefore time semantics are cross-cutting architecture.

Every relevant contract must distinguish as needed:

```text
source_event_time
source_publish_time
retrieved_at
available_at
decision_time
confirmation_time
execution_eligible_time
execution_time
```

Not every data type needs every timestamp.

But no subsystem may collapse distinct time semantics merely for convenience.

For bar data in particular, the architecture must be able to represent:

- interval start or end semantics;
- whether the bar is final;
- when the final value became available;
- whether later revisions occurred.

The exact policy belongs to `04-Data-Constitution.md`.

---

# 25. Probability and Score Architecture

The architecture must distinguish:

```text
Raw Feature
Composite Score
Model Score
Rank Score
Calibrated Probability
Expected Return
Decision Utility
```

These are not interchangeable.

A rule-weighted value bounded to `[0, 1]` is not automatically a probability.

A calibrated probability must have:

- a defined event;
- a defined horizon;
- a defined population;
- an out-of-sample calibration method;
- a model identity;
- validation evidence.

The current heuristic probability-like fields may remain legacy diagnostics during migration.

They must not define the platform's future probability contract.

---

# 26. Configuration Architecture

Configuration is a first-class architectural concern because uncontrolled configuration can become hidden code.

Configuration must be separated by owner:

```text
Data Config
Universe Config
Feature Config
Market Model Config
Candidate Model Config
Strategy Config
Portfolio Config
Execution Config
Research Config
```

A single strategy backtest configuration object must not remain the permanent container for all platform behavior.

Rules for configuration:

1. every field has one owner;
2. fields have stable semantics;
3. experiment-relevant fields are included in experiment identity;
4. deprecated fields are explicit;
5. configuration translation from Legacy to V2 is versioned;
6. unrelated modules do not inspect each other's private configuration.

---

# 27. Event and Trace Architecture

Every meaningful system transition should be observable as an event or traceable state change.

The project should be able to reconstruct:

```text
Why was symbol X in the universe?
Why was symbol Y rejected?
Which feature values were available?
Which market regime was active?
Why was candidate Z ranked third?
Why did Entry reject the top-ranked candidate?
Why did Position Lifecycle propose REDUCE?
Why did Portfolio reject that reduction or change its size?
Why did Execution fail or fill at a different price?
Which model, data and code versions were involved?
```

The target event flow conceptually includes:

```text
DataQualityEvent
UniverseEligibilityEvent
FeatureMaterializationEvent
MarketContextEvent
CandidatePredictionEvent
StrategyProposalEvent
PortfolioDecisionEvent
ExecutionEvent
PositionStateTransitionEvent
ResearchEvaluationEvent
```

The exact event schema is a lower-level specification.

---

# 28. Failure Boundaries

## 28.1 Fail closed on missing required data

If a required feature cannot be computed from valid point-in-time data, the system must not silently substitute a plausible value unless the feature definition explicitly declares and versions that imputation rule.

## 28.2 Partial failure is allowed at the correct boundary

A failure for one symbol should not necessarily abort an entire market scan.

A failure in the dataset identity or time semantics may invalidate the entire experiment.

The failure boundary must match the responsibility boundary.

Examples:

```text
One symbol has insufficient history
    → reject symbol with reason

Dataset has unknown finalization semantics
    → reject formal experiment

One optional shadow model fails
    → continue authoritative model, record shadow failure

Authoritative portfolio state is inconsistent
    → stop decision cycle
```

## 28.3 Error conversion is explicit

Vendor exceptions should be translated at the adapter boundary.

Strategy code should not need to understand a Tencent HTTP exception or an XtQuant import exception.

---

# 29. Research and Production Separation

The architecture defines four broad operating classes:

```text
Exploratory
Rehearsal
Formal Research
Production
```

A component may exist in one class without being authorized for the next.

Examples:

- Tencent data may support exploratory analysis without formal PIT approval;
- a candidate model may be implemented without promotion;
- a backtest may run without access to the sealed test;
- a portfolio decision engine may be simulated without broker connectivity.

Promotion is an evidence transition, not a code-location transition.

Detailed validation gates belong to `07-Validation-Constitution.md`.

---

# 30. Migration Strategy

The architecture will be introduced through a strangler migration, not a big-bang rewrite.

## Stage A — Freeze architectural expansion of Legacy

Rules:

- do not add new platform-wide responsibilities to `dividend_t`;
- do not add new unrelated state machines to `backtest.py`;
- do not make `CoscoTimingEngine` the integration point for new strategies;
- preserve bug fixes and reproducibility work.

## Stage B — Establish V2 core contracts

Create the minimum stable contracts for:

- research context;
- experiment identity;
- universe snapshot;
- feature identity;
- candidate prediction;
- position action proposal;
- portfolio decision;
- execution request/result;
- trace identity.

Do not migrate all legacy logic at once.

## Stage C — Introduce compatibility adapters

Map legacy outputs into V2-compatible research contracts.

Examples:

```text
DividendTStrategy result
    → LegacyStrategyAdapter
    → PositionActionProposal / diagnostic record

CoscoTimingSnapshot
    → LegacyTimingAdapter
    → Candidate or setup diagnostic record
```

The adapter must preserve legacy semantics rather than pretending the legacy model already obeys all V2 concepts.

## Stage D — Extract Backtest responsibilities

Each extraction requires characterization tests.

Recommended order:

1. execution constraints and costs;
2. event ledger;
3. portfolio state;
4. position lifecycle state;
5. metrics;
6. reporting;
7. orchestration.

Behavioral changes and structural extraction should not be mixed unless separately justified.

## Stage E — Build native Candidate Discovery MVP

The first V2-native strategic capability should be cross-sectional Candidate Discovery.

It must not be implemented inside `CoscoTimingEngine`.

## Stage F — Build native Position Lifecycle

Existing positions become first-class stateful research subjects.

Entry and Exit remain separate.

## Stage G — Unify application decision paths

Public snapshots and dashboards consume one authoritative application flow.

Legacy models may continue as shadow diagnostics.

## Stage H — Retire duplicate authority

Only after V2 behavior is validated may duplicate legacy decision authority be removed.

---

# 31. What Must Not Be Done

The following are explicitly prohibited migration patterns.

## 31.1 Big-bang package relocation

Do not move every `dividend_t` file into new directories in one change.

A new path does not create a new architecture.

## 31.2 Wrapper-only architecture

Do not create empty V2 classes that simply call the entire legacy God Object forever.

Adapters are transitional boundaries, not permanent architecture theater.

## 31.3 Rewrite plus strategy change in one step

Do not simultaneously:

- extract execution;
- change execution semantics;
- change signal thresholds;
- change data;
- report improved performance.

The result would be impossible to attribute.

## 31.4 UI-level signal arbitration

Do not resolve `signal` versus `timing_action` by choosing whichever looks stronger in presentation code.

## 31.5 Generic `utils` as a new dumping ground

Shared behavior must have a domain owner.

## 31.6 `core` as a new God package

Only strategy-neutral, vendor-neutral concepts belong in Core.

## 31.7 Configuration compatibility by silent defaulting

Legacy configuration translation must be explicit and versioned.

---

# 32. Architectural Acceptance Criteria

The target architecture is considered materially established when the project can satisfy all of the following.

## 32.1 Responsibility clarity

For every major decision and state transition, the project can name one authoritative owner.

## 32.2 One decision authority per scope

A public or production-facing decision scope does not expose two competing final actions without an explicit ensemble/arbitration owner.

## 32.3 Reproducible research identity

A research result can identify:

- dataset;
- universe;
- features;
- model;
- strategy;
- portfolio policy;
- execution assumptions;
- code revision.

## 32.4 Point-in-time eligibility is explicit

A formal experiment cannot run merely because bars are present.

## 32.5 Cross-sectional candidate capability exists natively

The project can rank a point-in-time multi-symbol universe without treating each symbol as an isolated standalone strategy invocation.

## 32.6 Position lifecycle is first-class

Existing positions can be evaluated through explicit HOLD / ADD / REDUCE / ROTATE / EXIT semantics.

## 32.7 Portfolio authority is centralized

Strategies propose. The Portfolio System allocates.

## 32.8 Execution is reusable

The same execution contracts support historical simulation and future execution adapters.

## 32.9 Legacy remains reproducible during migration

Existing research can be rerun or compared until its replacement is validated.

## 32.10 Presentation is downstream

Dashboards and snapshots do not implement hidden decision logic.

---

# 33. Architecture Decision Rules for Agents

AI agents working on this repository must follow these rules.

Before adding a new module, an agent must identify:

1. the owning subsystem;
2. the input contract;
3. the output contract;
4. the state owner, if any;
5. the time semantics;
6. whether the module is exploratory, rehearsal, formal or production;
7. whether a legacy owner already exists;
8. the migration or compatibility impact.

An agent must reject or escalate a design when:

- two modules would own the same business state;
- a strategy module directly accesses ungoverned external data;
- a feature directly creates an order;
- presentation code becomes a signal arbiter;
- research output becomes a hidden runtime dependency;
- a new rule is proposed as another branch inside a God Object without an explicit owner;
- a new probability field lacks a defined event and calibration contract;
- a structural refactor silently changes model behavior.

The correct agent question is not:

> “Where can I put this code fastest?”

It is:

> **“Which subsystem is constitutionally responsible for this behavior, and what contract should cross the boundary?”**

---

# 34. Relationship to the Remaining Constitution

This Architecture Blueprint intentionally leaves several topics to later volumes.

## `03-Research-Framework.md`

Will define the end-to-end research lifecycle:

```text
Idea
→ Hypothesis
→ Data
→ Feature
→ Baseline
→ Experiment
→ Walk Forward
→ OOS
→ Calibration
→ Promotion
→ Monitoring
→ Retirement
```

## `04-Data-Constitution.md`

Will define:

- PIT requirements;
- provider evidence;
- finalization;
- corporate actions;
- dataset manifests;
- provenance;
- quality gates;
- data eligibility classes.

## `05-Factor-Constitution.md`

Will define:

- feature registry;
- lineage;
- factor families;
- duplicate-information control;
- normalization;
- IC/RankIC;
- incremental value;
- factor promotion.

## `06-Strategy-Constitution.md`

Will define:

- Candidate versus Strategy boundaries;
- Entry;
- Position Lifecycle;
- Exit;
- strategy registry;
- strategy versioning;
- strategy state.

## `07-Validation-Constitution.md`

Will define:

- sample isolation;
- walk-forward;
- OOS;
- sealed test;
- promotion gates;
- statistical and economic validation;
- degradation monitoring.

## `08-Roadmap.md`

Will sequence implementation priorities without redefining architecture.

## `09-Glossary.md`

Will freeze project-wide terminology.

---

# 35. Constitutional Architectural Commitments

The project therefore commits to the following architecture.

1. **The project will remain a modular monolith unless evidence requires another deployment model.**
2. **The `dividend_t` package will be preserved as a legacy strategy/research asset, not expanded as the universal platform kernel.**
3. **The new platform will separate Data, Universe, Features, Market Context, Candidate Discovery, Strategy, Portfolio, Execution and Research.**
4. **Candidate prediction will not be treated as a trade order.**
5. **Entry, Position Lifecycle and Exit will be independently owned and independently testable.**
6. **The Portfolio System will be the sole owner of portfolio-wide capital allocation.**
7. **The Execution System will be the sole owner of market-execution constraints and fill semantics.**
8. **The Research System will orchestrate evidence but will not become a runtime dependency of strategy logic.**
9. **Interfaces will consume one authoritative application flow rather than compose competing decision engines.**
10. **Legacy migration will preserve research knowledge through adapters and characterization, not through permanent accidental coupling.**
11. **Point-in-time correctness and data eligibility will be architectural gates, not optional backtest flags.**
12. **Every important decision must be traceable from data identity to execution outcome.**
13. **No future God Object is acceptable, regardless of whether it is named `backtest`, `engine`, `manager`, `core`, `agent` or `orchestrator`.**
14. **A module is accepted into the target architecture only when its responsibility, owner, inputs, outputs, state and validation class are explicit.**

---

# 36. Final Architectural Statement

The first phase of `market-regime-alpha` proved that the project can encode complex A-share trading ideas.

The next phase must prove that the project can organize those ideas without losing epistemic control.

The target is not a larger timing engine.

The target is not a larger backtest file.

The target is not a larger collection of indicators.

The target architecture is a system in which:

```text
Data has provenance.
Universe has point-in-time meaning.
Features have lineage.
Market context has explicit scope.
Candidates are ranked cross-sectionally.
Entry is distinct from prediction.
Positions have a lifecycle.
Exit is distinct from entry.
Portfolio allocation has one owner.
Execution has realistic constraints.
Research has reproducible identity.
Every decision can be traced.
Legacy knowledge can migrate without controlling the future.
```

That architecture is the foundation required for Market Regime Alpha to become what the Project Vision defines:

> **An Alpha Research Operating System for the China A-share market.**
