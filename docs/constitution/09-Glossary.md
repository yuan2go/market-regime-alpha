# The Constitution of Market Regime Alpha

# Volume X — Glossary

> **Document:** `docs/constitution/09-Glossary.md`  
> **Status:** Foundational / Normative  
> **Authority:** Project-wide canonical vocabulary, semantic disambiguation, Legacy-to-V2 terminology mapping, naming discipline, and interpretation rules  
> **Applies to:** Constitution documents, architecture, data contracts, research artifacts, feature and factor registries, Candidate Discovery, strategies, portfolio and execution interfaces, validation, reports, dashboards, APIs, agents, migration plans, source code and future specifications  
> **Project:** `market-regime-alpha`  
> **Precedence:** This Glossary interprets and normalizes terminology established by `00-Project-Vision.md` through `08-Roadmap.md`. It does not override the substantive authority of those volumes and must not create a new architectural direction.

---

## 0. Purpose

`market-regime-alpha` has completed the constitutional definition of:

```text
Vision
    ↓
Principles
    ↓
Architecture
    ↓
Research
    ↓
Data
    ↓
Factors
    ↓
Strategies
    ↓
Validation
    ↓
Migration Roadmap
```

The remaining constitutional problem is semantic stability.

The current repository contains valuable Legacy terminology from earlier stages, including:

- `Signal`;
- `CandidateSignal`;
- `StrategyDecision`;
- `OrderIntent`;
- `PositionState`;
- `timing_action`;
- probability-like scores;
- local OOS classifications;
- Dividend-T-specific actions;
- multiple uses of words such as `state`, `score`, `signal`, `candidate`, `rehearsal`, `formal`, `position` and `strategy`.

The target Alpha Research Operating System also introduces more precise concepts such as:

- Candidate Prediction;
- Strategy Proposal;
- Portfolio Decision;
- Execution Request;
- Data Eligibility;
- Sample Role;
- Evidence Level;
- Authority State;
- Feature Definition;
- Feature Materialization;
- Semantic Family;
- Source-Information Family;
- Strategy Sleeve;
- Physical Position;
- Point-in-Time correctness.

Without a canonical vocabulary, a technically correct refactor can still create semantic corruption.

For example:

```text
Candidate
```

may incorrectly mean:

```text
A stock worth ranking
A setup
A proposed action
A final buy decision
```

Likewise:

```text
HOLD
```

may incorrectly mean:

```text
No model output
No candidate
No position
No action
Continue an evaluated position
```

These meanings are not interchangeable.

The purpose of this Glossary is therefore to answer:

> **What does each core term mean in this project, what does it not mean, and which term must be used when several Legacy meanings previously shared one name?**

The central rule is:

> **A term must identify one semantic role within one authority boundary. When a word is overloaded, qualify it or replace it rather than relying on context to guess the meaning.**

---

# 1. Authority of the Glossary

## 1.1 The Glossary normalizes; it does not redesign

This document must not introduce a new project mission, architecture, research process, data model, factor doctrine, strategy doctrine, validation doctrine or migration sequence.

It exists to make the already-established Constitution implementable without semantic drift.

When a term appears to conflict with a substantive rule in another Constitution volume:

```text
Substantive Constitution Rule
        >
Glossary Interpretation
```

The Glossary must then be corrected.

---

## 1.2 Canonical vocabulary applies across interfaces

Canonical terms should be used consistently in:

- Python types;
- JSON and API contracts;
- manifests;
- registries;
- experiment artifacts;
- reports;
- dashboards;
- logs;
- agent prompts;
- architecture documents;
- migration plans.

A UI label may be more readable than an internal type name.

It must not change the underlying semantics.

---

## 1.3 Legacy terms may remain for compatibility

A Legacy term may remain when:

- existing imports depend on it;
- historical artifacts require it;
- behavior reproduction requires it;
- a compatibility adapter exposes it explicitly.

Legacy compatibility does not grant platform-level semantic authority.

The preferred pattern is:

```text
Legacy Term
    ↓
Explicit Compatibility Mapping
    ↓
Canonical V2 Term
```

not:

```text
Legacy Term
    ↓
Silently Becomes Platform Truth
```

---

# 2. Vocabulary Status Labels

This Glossary uses the following semantic status labels.

## 2.1 `CANONICAL`

The preferred project-wide term for new platform contracts.

---

## 2.2 `QUALIFIED`

The term is valid only with an explicit qualifier.

Example:

```text
State
```

is too ambiguous by itself.

Valid qualified forms include:

```text
Market Regime State
Strategy Lifecycle State
Risk State
Portfolio State
Execution State
```

---

## 2.3 `LEGACY-ONLY`

The term may remain in historical code or compatibility interfaces but must not become a new platform-wide contract without explicit mapping.

---

## 2.4 `DISCOURAGED UNQUALIFIED`

The word may be useful in prose, but new formal contracts should not use it without a more precise semantic label.

Examples include:

```text
signal
score
state
confidence
position
action
model works
formal data
```

---

## 2.5 `PROHIBITED SEMANTIC CLAIM`

A term is prohibited when its use would make a stronger claim than the evidence supports.

Examples:

```text
OHLCV proxy called real capital flow
0–100 score called probability without calibration
current universe called historical PIT universe
rehearsal result called formal Alpha evidence
```

---

# 3. Core Semantic Rules

## 3.1 Owner-qualify ambiguous state

Do not create a universal object named only:

```text
State
```

Use the owner and meaning:

```text
MarketRegimeState
ThemeState
CandidateState, only when precisely defined
StrategyLifecycleState
RiskState
PortfolioState
ExecutionState
DataQualityState
```

State ownership is part of semantics.

---

## 3.2 A score is not a probability

```text
Composite Score
Model Score
Rank Score
Utility Score
```

must remain scores unless a defined event, horizon, population and calibration process justify:

```text
Calibrated Probability
```

Numeric range does not determine semantic type.

```text
82 / 100
```

is not:

```text
82% probability
```

unless probability authority exists.

---

## 3.3 A prediction is not an action

```text
Candidate Prediction
Expected Return
Expected MFE
Rank
Probability
```

must not be silently interpreted as:

```text
ENTER
ADD
HOLD
REDUCE
ROTATE
EXIT
```

Strategy policy owns actions.

---

## 3.4 A proposal is not an allocation

```text
Strategy Proposal
```

is not:

```text
Portfolio Decision
```

A strategy may propose exposure.

The Portfolio System owns final account-level allocation.

---

## 3.5 An allocation is not execution

```text
Portfolio Decision
```

is not:

```text
Execution Result
```

Execution must preserve whether an action was:

- requested;
- executable;
- blocked;
- delayed;
- modified;
- filled;
- partially filled;
- rejected.

---

## 3.6 Data quality, sample role, evidence and authority are different dimensions

The following must never be collapsed:

```text
Data Eligibility
Sample Role
Evidence Level
Authority State
```

For example:

```text
Data Eligibility = FORMAL_RESEARCH
Sample Role = SEALED_TEST
Evidence Level = E5 — SEALED_TESTED
Authority State = SHADOW or PROMOTED_FOR_SCOPE
```

Each answers a different question.

---

## 3.7 Theory name does not create information independence

```text
MACD
Moving Average
Chan
Tuishen-inspired construct
Breakout
Attention Proxy
```

may have different semantic interpretations while sharing the same underlying:

```text
PRICE_ONLY
or
OHLCV
```

source-information lineage.

Terminology must not imply independent evidence merely because representations have different names.

---

# 4. Project and Architecture Terms

## 4.1 Alpha Research Operating System — `CANONICAL`

**Definition**

The project-wide environment for repeatedly discovering, defining, testing, validating, combining, monitoring, degrading and retiring Alpha-related research objects for the China A-share market.

It is not one model, one strategy or one execution engine.

Canonical project definition:

> **Market Regime Alpha is an Alpha Research Operating System for the China A-share market.**

---

## 4.2 Alpha — `CANONICAL, CLAIM-RELATIVE`

**Definition**

A scoped research claim that information or a decision process provides measurable incremental value relative to an appropriate baseline under a defined target, population, decision-time convention and validation protocol.

**Not equivalent to**

- a plausible narrative;
- a positive backtest;
- a technical indicator;
- a high score;
- a single profitable trade;
- a universally permanent edge.

---

## 4.3 Current Implementation State — `CANONICAL`

**Definition**

What the repository can do now, including Legacy naming, current modules, current interfaces and current limitations.

It does not redefine the constitutional destination.

---

## 4.4 Constitutional Target State — `CANONICAL`

**Definition**

The system ownership, semantics and governance toward which future implementation must migrate.

---

## 4.5 Legacy Research Asset — `CANONICAL`

**Definition**

Existing code, rules, models, experiments, reports, data adapters, state machines or interfaces that contain useful research or operational knowledge from earlier project stages.

**Important**

Legacy does not mean worthless or immediately deprecated.

A Legacy Research Asset may be:

```text
PRESERVE
ADAPT
EXTRACT
FREEZE
RECLASSIFY
REPLACE
RETIRE_LATER
```

---

## 4.6 Legacy Path — `CANONICAL`

**Definition**

An existing execution, research, import or application path that remains supported during migration.

A Legacy Path may remain authoritative for its historical scope until replacement authority is explicitly established.

---

## 4.7 Legacy Freeze — `CANONICAL`

**Definition**

A restriction against adding new platform-wide ownership, universal semantics or uncontrolled rule accumulation to Legacy God Objects.

**Does not prohibit**

- bug fixes;
- tests;
- characterization;
- trace improvements;
- security fixes;
- compatibility work;
- correctness fixes.

---

## 4.8 V2 — `QUALIFIED`

**Definition**

The target architectural generation governed by the Constitution.

`V2` does not mean that every model, dataset or strategy must receive version number `2`.

Use qualified forms such as:

```text
V2 Kernel
V2 Candidate System
V2 Strategy Contract
```

---

## 4.9 V2 Kernel — `CANONICAL`

**Definition**

The minimal shared contract and identity layer required for new bounded-context work.

It may include:

- identity primitives;
- canonical time semantics;
- experiment identity;
- status and error semantics;
- cross-context interfaces.

It is not the complete future platform.

---

## 4.10 Bounded Context — `CANONICAL`

**Definition**

A domain boundary with explicit semantic ownership.

Target bounded contexts include:

```text
core
data
universe
features
market
candidates
strategies
portfolio
execution
research
application
interfaces
legacy
```

---

## 4.11 Owner — `CANONICAL`

**Definition**

The bounded context or subsystem with final semantic authority for a concept within its declared scope.

Examples:

```text
Features owns feature definitions.
Strategies owns strategy actions.
Portfolio owns final account allocation.
Execution owns executable orders and fills.
Validation owns sample-role and evidence-governance semantics.
```

Owner does not necessarily mean one source file or one class.

---

## 4.12 Authority — `CANONICAL`

**Definition**

The recognized right of a system or research object to determine a canonical output or influence a decision within a defined scope.

Authority must be explicit and scope-specific.

---

## 4.13 Authoritative Path — `CANONICAL`

**Definition**

The single designated path whose output is treated as canonical for a given decision scope.

Alternative paths may be:

- shadow;
- diagnostic;
- baseline;
- counterfactual;
- experimental.

They must not silently become co-equal final authorities.

---

## 4.14 Decision Scope — `CANONICAL`

**Definition**

The boundary within which one decision authority is being evaluated or exercised.

A scope may include:

- strategy;
- instrument;
- decision time;
- portfolio sleeve;
- position state;
- action family;
- target or horizon.

---

## 4.15 Compatibility Adapter — `CANONICAL`

**Definition**

A temporary or durable boundary that maps Legacy interfaces into canonical contracts without declaring Legacy internals to be target architecture.

Examples may include:

```text
LegacyDataAdapter
LegacyFactorAdapter
LegacyStrategyAdapter
LegacyExperimentAdapter
```

Exact implementation names belong to lower-level design.

---

## 4.16 Modular Monolith — `CANONICAL ARCHITECTURAL DIRECTION`

**Definition**

One deployable or repository-integrated application with explicit internal module boundaries and ownership.

It is the default target architecture before any demonstrated need for microservices.

---

# 5. Research Terms

## 5.1 Observation / Idea — `CANONICAL RESEARCH STARTING POINT`

**Definition**

A noticed market behavior, recurring pattern, anomaly, practical question or theory-derived possibility that may motivate research.

It is not yet a validated claim.

---

## 5.2 Research Question — `CANONICAL`

**Definition**

A precise question that identifies the object, scope and decision problem to be investigated.

Example:

```text
Does cross-sectional 20-day relative strength add incremental ranking value
for a defined liquid A-share universe at a defined decision time
for a defined next-session target?
```

---

## 5.3 Hypothesis — `CANONICAL`

**Definition**

A falsifiable statement about an expected relationship or decision effect.

A theory narrative becomes research only after it can be expressed as a testable hypothesis.

---

## 5.4 Research Charter — `CANONICAL`

**Definition**

The pre-research contract that defines, as applicable:

- question;
- hypothesis;
- object;
- target;
- population;
- decision time;
- data requirements;
- baseline;
- validation approach;
- risks;
- invalidation conditions.

---

## 5.5 Research Object — `CANONICAL`

**Definition**

The exact entity being studied.

Examples:

- feature;
- factor;
- Candidate model;
- calibration model;
- Entry policy;
- HOLD policy;
- ADD policy;
- REDUCE policy;
- ROTATE policy;
- Exit policy;
- Market Regime model;
- ETF Rotation model;
- complete strategy;
- execution assumption set.

---

## 5.6 Research Claim — `CANONICAL`

**Definition**

The scoped assertion that a Research Object has a defined relationship or value under specified conditions.

Authority attaches to the claim and scope, not merely to the object name.

---

## 5.7 Target — `CANONICAL`

**Definition**

The measurable future outcome a predictive or evaluative object is designed to estimate or relate to.

Examples:

- next-session return;
- future MFE threshold event;
- future MAE;
- relative return;
- remaining return from a lifecycle state;
- thesis invalidation event.

A target is not a strategy action.

---

## 5.8 Target Contract — `CANONICAL`

**Definition**

The versioned definition of a target, including as applicable:

- event or quantity;
- horizon;
- start and end timing;
- price convention;
- censoring;
- missingness;
- population;
- decision-time relationship.

---

## 5.9 Horizon — `CANONICAL`

**Definition**

The future interval over which a Target or evaluation is defined.

A horizon must not be inferred from a metric name alone.

---

## 5.10 Decision Time — `CANONICAL`

**Definition**

The historical or live time at which the system is assumed to make a prediction or decision using only information available by that time.

Decision Time is central to PIT correctness.

---

## 5.11 Experiment — `CANONICAL`

**Definition**

A controlled research run that evaluates a defined object or hypothesis under identified data, configuration, split, baseline and metric semantics.

---

## 5.12 Experiment Identity — `CANONICAL`

**Definition**

The stable identity of all result-affecting experiment semantics required to reproduce and interpret a result.

It may include:

- code revision;
- dataset identity;
- split identity;
- target identity;
- feature set;
- model or policy identity;
- algorithm version;
- execution assumptions;
- random seed;
- environment identity.

A profile label is not sufficient Experiment Identity.

---

## 5.13 Evidence Artifact — `CANONICAL`

**Definition**

An immutable or identifiable package that preserves the evidence supporting a research claim.

It may include:

- run manifest;
- experiment identity;
- dataset and split references;
- metrics;
- predictions;
- traces;
- counterfactuals;
- diagnostics;
- checksums;
- logs;
- review decision.

---

## 5.14 Baseline — `CANONICAL`

**Definition**

The relevant comparison against which incremental value is measured.

Possible baselines include:

- no signal;
- no action;
- hold existing position;
- simple deterministic rule;
- market benchmark;
- current Legacy model;
- current promoted model;
- ablated parent model.

The baseline must match the claim.

---

## 5.15 Counterfactual — `CANONICAL`

**Definition**

A modeled outcome under an alternative feasible decision path.

A valid counterfactual must respect:

- information availability;
- decision time;
- next eligible execution;
- tradability;
- costs;
- path assumptions.

A future high or low that was not executable is not a valid primary counterfactual fill.

---

## 5.16 Ablation — `CANONICAL`

**Definition**

A controlled comparison that measures what changes when a component, role or interaction is present versus absent while other relevant conditions are held constant.

Ablation is broader than feature removal.

---

## 5.17 Attribution — `CANONICAL`

**Definition**

The process of assigning observed changes in prediction, decision or economic outcome to identifiable components and interactions.

---

## 5.18 Incremental Value — `CANONICAL`

**Definition**

Value added relative to an appropriate existing baseline or information set.

The project distinguishes:

```text
Standalone Value
Incremental Predictive Value
Incremental Economic Value
```

---

## 5.19 Robustness — `CANONICAL`

**Definition**

The degree to which a result survives reasonable variation in time, population, parameters, costs, data assumptions or related conditions within the intended claim scope.

Robustness does not require universal invariance.

---

## 5.20 Research Result — `CANONICAL`

**Definition**

An empirical output produced under an identified experiment and evidence process.

A Research Result is not automatically a Fact about future market behavior.

---

# 6. Data Terms

## 6.1 Provider — `CANONICAL`

**Definition**

The external or internal origin from which information is obtained.

A Provider is not a Dataset.

Provider reputation does not automatically determine dataset eligibility.

---

## 6.2 Source Artifact — `CANONICAL`

**Definition**

The identifiable unit actually retrieved or preserved from a Provider.

Examples:

- API response;
- downloaded file;
- provider snapshot;
- broker archive;
- vendor export.

---

## 6.3 Adapter / Ingestion Adapter — `CANONICAL`

**Definition**

A component that translates provider-specific representations into project-understood semantics.

An Adapter performs translation, not epistemic promotion.

---

## 6.4 Normalized Observation — `CANONICAL`

**Definition**

A value represented using stable internal field names, units and types after ingestion normalization.

Normalization does not prove PIT correctness or formal research eligibility.

---

## 6.5 Observation — `CANONICAL, CONTEXT-DEPENDENT`

**Definition**

A measured or recorded information value used by the Data or Feature System.

When precision is required, prefer:

```text
Source Observation
Normalized Observation
Canonical PIT Observation
Raw Observation
```

rather than bare `Observation`.

---

## 6.6 Raw Observation — `CANONICAL FEATURE-LAYER TERM`

**Definition**

A canonical data value consumed by the Feature System before feature transformation.

`Raw` here means raw relative to feature construction.

It does not necessarily mean untouched provider bytes.

---

## 6.7 Canonical Point-in-Time Data — `CANONICAL`

**Definition**

The project-approved representation of an information domain for a declared research use, with explicit identity, time, availability, provenance, version, missingness, corrections and eligibility semantics.

---

## 6.8 Dataset — `CANONICAL`

**Definition**

A controlled and identifiable collection of data artifacts prepared for a defined research scope.

A directory name such as:

```text
data/final
```

is not Dataset Identity.

---

## 6.9 Dataset Identity — `CANONICAL`

**Definition**

The stable identity of the exact data content and result-affecting data semantics used for research.

It should be derived from manifests, content references, versions or hashes rather than mutable path names alone.

---

## 6.10 Dataset Manifest — `CANONICAL`

**Definition**

The structured record describing dataset identity, source references, coverage, semantics, quality and dependencies.

---

## 6.11 Data Eligibility — `CANONICAL`

**Definition**

The qualification of whether data may support a class of research claim.

Canonical Data Eligibility classes are:

```text
UNQUALIFIED
EXPLORATORY
REHEARSAL
FORMAL_RESEARCH
```

Data Eligibility is not a Sample Role, Evidence Level or live-capital authority.

---

## 6.12 `UNQUALIFIED` — `CANONICAL DATA ELIGIBILITY`

Critical semantics or provenance are unknown or insufficiently reviewed.

It must not support formal performance claims.

---

## 6.13 `EXPLORATORY` — `CANONICAL DATA ELIGIBILITY`

Data is sufficient for bounded exploration, prototyping or hypothesis work but not for formal promotion claims that require stronger evidence.

---

## 6.14 `REHEARSAL` — `CANONICAL DATA ELIGIBILITY`

Data and artifacts are sufficient to rehearse stricter research or pipeline contracts under declared limitations.

`REHEARSAL` does not mean the dataset is a sample partition named rehearsal.

---

## 6.15 `FORMAL_RESEARCH` — `CANONICAL DATA ELIGIBILITY`

Data is eligible, for a declared scope, to support formal research claims under the Data Constitution.

It does not imply:

- OOS validation;
- sealed testing;
- promotion;
- production readiness;
- live capital authority.

---

## 6.16 Sample Role — `CANONICAL`

**Definition**

The role a dataset or partition plays inside a validation protocol.

Canonical Sample Roles are:

```text
DEVELOPMENT
TRAIN
VALIDATION
CALIBRATION
OOS_TEST
SEALED_TEST
SHADOW_OBSERVATION
```

---

## 6.17 Point-in-Time / PIT — `CANONICAL`

**Definition**

The requirement that a historical decision at time `T` use only information that the system could actually have possessed by `T`, in the state and version available at that time.

Canonical PIT test:

> **At historical decision time T, could the system actually have possessed the exact information used, in the form and state in which it was used?**

---

## 6.18 As-Of Time — `CANONICAL, QUALIFIED`

**Definition**

A reference time indicating the information state represented by an artifact or record.

`as_of` is not automatically the same as publication time, retrieval time or availability time.

Use specific time fields where semantics matter.

---

## 6.19 Source Event Time — `CANONICAL`

The time at which the underlying market or business event occurred.

---

## 6.20 Source Publish Time — `CANONICAL`

The time at which the source published information.

---

## 6.21 Retrieved At — `CANONICAL`

The time at which the project retrieved or recorded the source artifact.

---

## 6.22 Available At — `CANONICAL`

The earliest time at which the information is treated as available to the decision system under the declared data contract.

---

## 6.23 Finalized At / Bar Final — `CANONICAL`

**Definition**

The time or status indicating that an observation, such as a market bar, is complete under the source and bar contract.

Historical age alone does not prove finalization.

---

## 6.24 Effective At — `CANONICAL`

The time at which a rule, constituent membership, corporate action, classification or other state becomes effective.

---

## 6.25 Decision Time — `CANONICAL CROSS-DOMAIN TERM`

The time at which a prediction or decision is assumed to be made.

Data availability must be evaluated relative to Decision Time.

---

## 6.26 Execution-Eligible Time — `CANONICAL`

The earliest time at which an approved action may be executable under the applicable market and execution contract.

Decision Time and Execution-Eligible Time are not necessarily equal.

---

## 6.27 Sidecar — `CANONICAL`

**Definition**

A separately maintained but identity-relevant data artifact required to interpret, qualify or reproduce a dataset.

Examples:

- trading calendar;
- PIT universe;
- corporate actions;
- suspension state;
- trading eligibility;
- industry mapping;
- theme mapping;
- market context.

A result-affecting Sidecar is part of Dataset Identity.

---

## 6.28 Universe — `CANONICAL`

**Definition**

The population of instruments considered for a defined research or decision scope.

A Universe must be reproducible and time-aware when used for historical formal claims.

---

## 6.29 Universe Membership — `CANONICAL`

Whether an instrument belongs to a defined population at a given historical point in time.

---

## 6.30 Eligibility — `CANONICAL, OWNER-QUALIFIED WHEN NEEDED`

Whether an instrument or observation satisfies rules for inclusion in a research or decision process.

Examples:

```text
Universe Eligibility
Trading Eligibility
Entry Eligibility
Data Eligibility
```

Bare `eligible` should be qualified when multiple authorities are possible.

---

## 6.31 Tradability — `CANONICAL`

Whether an instrument can legally and operationally be traded at the relevant historical or current time under known market-state facts.

Tradability is not the same as Universe Membership.

---

## 6.32 Execution Feasibility — `CANONICAL`

Whether a specific approved action can be executed under the applicable execution assumptions and constraints.

An instrument may be tradable in general while a specific action is not executable at a specific time or price.

---

## 6.33 Adjustment View — `CANONICAL`

A defined representation of prices relative to corporate actions.

Canonical distinctions include:

```text
Raw / Unadjusted Price View
Current Back-Adjusted Display View
Point-in-Time Adjusted Research View
Execution Price View
```

Different views must not be mixed silently.

---

## 6.34 Data Incident — `CANONICAL`

A material defect, semantic change, provider correction, missingness event, revision or integrity issue that may affect downstream datasets, experiments, models or claims.

---

# 7. Feature and Factor Terms

## 7.1 Feature — `CANONICAL`

**Definition**

A defined transformation or representation of observations used for analysis, description, prediction or decision support.

A Feature is not automatically a predictive Factor.

---

## 7.2 Primitive Feature — `CANONICAL`

A relatively direct transformation with clear lineage and limited semantic depth.

Examples:

- one-bar return;
- 20-day return;
- rolling volatility;
- amount relative to rolling median;
- price relative to VWAP.

---

## 7.3 Derived Feature — `CANONICAL`

A more complex transformation that combines one or more observations or primitive features.

Examples:

- MACD histogram;
- moving-average slope;
- Chan pivot state;
- volume-price persistence;
- theme breadth.

---

## 7.4 Indicator — `CANONICAL, NON-AUTHORITY TERM`

**Definition**

A named mathematical or structural transformation commonly used to summarize market information.

Examples:

- MACD;
- moving average;
- RSI, if introduced later;
- volatility measure.

An Indicator is not automatically:

- a Factor;
- a Signal;
- a Gate;
- a Strategy.

---

## 7.5 Descriptor — `CANONICAL`

**Definition**

A label or structured description of an observable condition without necessarily claiming predictive power.

Examples:

```text
TREND_UP
LOW_VOLUME_PULLBACK
CHAN_BUY2
THEME_IGNITION
HIGH_VOLUME_STALL
```

---

## 7.6 State — `DISCOURAGED UNQUALIFIED`

**Definition**

A persistent or categorical interpretation that evolves over time.

Always qualify by owner or domain when used in formal contracts.

Examples:

```text
Market Regime State
Theme State
Trend State
Strategy Lifecycle State
Risk State
Portfolio State
Execution State
```

---

## 7.7 Factor Candidate — `CANONICAL`

**Definition**

A registered feature or construct for which the project has an explicit predictive or explanatory hypothesis.

A Factor Candidate has not yet earned predictive authority merely by registration.

---

## 7.8 Predictive Factor — `CANONICAL`

**Definition**

A Factor Candidate that has obtained scoped evidence of a stable relationship with a defined target under the relevant validation design.

Predictive authority remains conditional on scope.

---

## 7.9 Factor — `QUALIFIED CANONICAL TERM`

**Definition**

A defined, versioned and traceable information construct whose relationship to one or more explicit research targets is evaluated under a specified population, decision-time convention and validation protocol.

Do not use `factor` as a universal synonym for every numeric field.

---

## 7.10 Feature Definition — `CANONICAL`

**Definition**

The versioned semantic and computational definition of a feature independent of one specific materialized dataset run.

---

## 7.11 Feature Materialization — `CANONICAL`

**Definition**

The concrete computed values produced from a Feature Definition under identified:

- dataset;
- universe;
- as-of scope;
- parameters;
- adjustment view;
- code revision;
- dependencies.

Feature Definition and Feature Materialization are different identities.

---

## 7.12 Feature Registry — `CANONICAL`

**Definition**

The project authority for registered Feature Definitions, identity, lineage, availability, parameters and research status.

A registry may be implemented as code, files, database records or another controlled mechanism.

The Constitution defines semantics, not one storage technology.

---

## 7.13 Factor Registry — `CANONICAL LOGICAL ROLE`

**Definition**

The logical authority that records Factor Candidates, hypotheses, target scopes, evidence and status.

Feature Registry and Factor Registry may share one implementation.

Their semantic roles remain distinguishable.

---

## 7.14 Lineage — `CANONICAL`

**Definition**

The traceable dependency path from source information through transformations to downstream research and decisions.

Canonical conceptual path:

```text
Source Artifact
    ↓
Canonical Field
    ↓
Feature
    ↓
Factor / Model Input
    ↓
Composite / Model Output
    ↓
Strategy Use
    ↓
Decision
```

---

## 7.15 Semantic Family — `CANONICAL`

**Definition**

The family describing what a Feature or Factor is intended to represent.

Examples:

- Trend;
- Momentum;
- Volatility;
- Liquidity;
- Capital Flow;
- Structure;
- Fundamental Quality;
- Valuation;
- Event / Policy;
- Relative Strength;
- Breadth.

Semantic Family does not prove information independence.

---

## 7.16 Source-Information Family — `CANONICAL`

**Definition**

The family describing the underlying information actually used to construct a Feature or Factor.

Examples:

```text
PRICE_ONLY
OHLCV
TRADE_AMOUNT
OBSERVED_FUND_FLOW
TRADE_PRINTS
ORDER_BOOK_L1
ORDER_BOOK_L2
ETF_SHARES
FUNDAMENTAL_REPORTED
EVENT_DOCUMENT
POLICY_DOCUMENT
INDUSTRY_MEMBERSHIP
THEME_MEMBERSHIP
POSITION_STATE
PORTFOLIO_STATE
```

---

## 7.17 Representation Method — `CANONICAL`

**Definition**

The algorithmic, theoretical or structural method used to represent underlying information.

Examples:

- MACD;
- moving averages;
- Chan-derived structure;
- Tuishen-inspired decomposition.

Representation Method must not be confused with Source-Information Family.

---

## 7.18 Proxy — `CANONICAL, MUST BE QUALIFIED`

**Definition**

A derived approximation used to represent a concept that is not directly observed from the same evidence source.

Examples:

```text
OHLCV-derived Attention Proxy
OHLCV-derived Sell-Pressure Proxy
Bar-Derived Flow Proxy
```

A Proxy must not be renamed as direct observation.

---

## 7.19 Observed Real Flow — `CANONICAL`

**Definition**

A flow field directly supplied under an identified data contract as observed or vendor-defined capital-flow information.

Its exact semantics still require provider qualification.

---

## 7.20 Order-Flow-Derived Measure — `CANONICAL`

A measure derived from trade prints, order book or other microstructure data under an explicit algorithm.

It is not automatically equivalent to a provider's observed real-flow field.

---

## 7.21 Bar-Derived Flow Proxy — `CANONICAL`

A flow-like measure derived from bars such as OHLCV or amount.

It must not be labeled as observed real capital flow.

---

## 7.22 Heuristic Flow Score — `CANONICAL`

A rule-based or composite score intended to summarize flow-like evidence.

It must preserve its heuristic status.

---

## 7.23 Composite Score — `CANONICAL`

**Definition**

A versioned research object that combines multiple features, factors or model outputs according to an explicit rule.

A Composite Score must declare:

- components;
- component identities;
- combination rule or weights;
- missingness policy;
- intended meaning;
- role;
- overlap risks.

---

## 7.24 Model Score — `CANONICAL`

A numeric output from a model that is not, by itself, a calibrated probability.

---

## 7.25 Rank Score — `CANONICAL`

A numeric output used to order a cross-section or opportunity set.

A Rank Score may preserve only ordering semantics and need not have cardinal probability meaning.

---

## 7.26 Calibrated Probability — `CANONICAL`

**Definition**

A probability output associated with an explicit:

- event;
- horizon;
- population;
- decision time;
- calibration method;
- calibration sample;
- validation evidence.

---

## 7.27 Expected Return — `CANONICAL`

A model estimate of future return under a defined target and horizon.

Expected Return is not guaranteed return.

---

## 7.28 Expected MFE — `CANONICAL`

A model estimate of future Maximum Favorable Excursion under a defined path and horizon contract.

---

## 7.29 Expected MAE — `CANONICAL`

A model estimate of future Maximum Adverse Excursion under a defined path and horizon contract.

---

## 7.30 Decision Utility — `CANONICAL, MODEL-DEPENDENT`

A value that combines predicted outcomes, risk, costs or opportunity considerations for a declared decision problem.

Decision Utility is not a probability.

---

## 7.31 Gate — `CANONICAL`

**Definition**

A decision rule that permits, blocks or downgrades downstream behavior.

A Gate belongs to the system that owns the gated decision.

A feature used by an Entry Gate does not become the owner of Entry.

---

# 8. Candidate and Opportunity Terms

## 8.1 Candidate Discovery — `CANONICAL`

**Definition**

The cross-sectional or opportunity-set research process that identifies and ranks instruments with potentially attractive future outcomes for a defined target and decision time.

Candidate Discovery is currently the first strategic new research priority.

It is not a market-wide loop around a symbol-specific Legacy timing engine.

---

## 8.2 Candidate — `DISCOURAGED UNQUALIFIED IN FORMAL CONTRACTS`

**Definition**

A general-language term for an instrument or opportunity under consideration.

Because the word is historically overloaded, formal contracts should prefer one of:

```text
Candidate Instrument
Candidate Population
Candidate Prediction
Entry Candidate, only when explicitly strategy-level
Promotion Candidate, only when explicitly validation-level
```

Bare `Candidate` must never imply automatic buy authority.

---

## 8.3 Candidate Instrument — `CANONICAL`

An eligible instrument being considered by Candidate Discovery for a defined decision-time cross-section.

---

## 8.4 Candidate Population — `CANONICAL`

The complete eligible set against which Candidate predictions or rankings are evaluated for a decision time.

Preserving only selected winners is not equivalent to preserving the Candidate Population.

---

## 8.5 Candidate Prediction — `CANONICAL`

**Definition**

An opportunity estimate for an eligible instrument at a defined decision time.

It may include:

- raw prediction;
- rank;
- percentile;
- calibrated probability, if valid;
- expected return;
- expected MFE;
- expected MAE;
- uncertainty;
- expiry;
- trace and artifact references.

A Candidate Prediction does not own capital allocation or execution.

---

## 8.6 Opportunity Assessment — `CANONICAL ALTERNATIVE WHEN RANKING IS NOT REQUIRED`

A structured estimate of an opportunity that may be time-series or context-specific rather than cross-sectional.

It remains a prediction or assessment, not an action.

---

## 8.7 Setup — `CANONICAL, STRATEGY-CONTEXT TERM`

**Definition**

A defined market, technical, structural or contextual configuration that may support a strategy decision.

Examples:

- pullback low-buy setup;
- breakout-confirmed setup;
- Chan second-buy setup;
- risk-reduction setup.

A Setup is not automatically:

- a Candidate Prediction;
- a Strategy Action;
- a fill.

---

## 8.8 Trigger — `CANONICAL`

A discrete condition or event that activates evaluation of a policy, setup or state transition.

A Trigger may be necessary but not sufficient for an action.

---

## 8.9 Confirmation — `CANONICAL`

Additional evidence required by a policy before a proposal remains eligible or is upgraded.

Multiple confirmations derived from the same source-information family do not automatically constitute independent evidence.

---

## 8.10 Intent — `CANONICAL, MUST BE QUALIFIED`

**Definition**

The purpose or reason category behind a proposal or decision.

Examples:

```text
Strategy Intent
Entry Intent
Exit Intent
Risk-Reduction Intent
```

Intent is not the same as Action.

---

## 8.11 Signal — `DISCOURAGED UNQUALIFIED`

**Definition**

A historically overloaded term that may refer to an indicator event, setup, prediction, action recommendation or final decision.

New platform contracts should avoid bare `Signal` and use the precise object:

```text
Feature
Descriptor
Trigger
Confirmation
Candidate Prediction
Strategy Proposal
Strategy Action
Risk Event
Execution Result
```

---

## 8.12 `Signal` Enum in `dividend_t.models` — `LEGACY-ONLY`

Current Legacy values include:

```text
BUILD_BASE
HOLD
BUY_T
SELL_T
SELL_REVERSE_T
BUY_BACK_REVERSE_T
STOP_T
REDUCE
CLEAR
```

These remain valid for the Dividend-T Legacy domain.

They are not the platform-wide action vocabulary.

---

# 9. Strategy Terms

## 9.1 Strategy — `CANONICAL`

**Definition**

A versioned decision policy that consumes explicit information and state, operates within a defined scope, and produces traceable proposals subject to Portfolio and Execution authority.

A Strategy is not the whole system.

---

## 9.2 Strategy Policy — `CANONICAL`

The decision logic that maps explicit information and owned strategy state into a Strategy Proposal.

---

## 9.3 Strategy Family — `CANONICAL`

A category of strategies sharing a broad mandate or decision structure.

Examples:

- overnight opportunity;
- trend continuation;
- ETF rotation;
- long-term dividend;
- mean reversion;
- active overlay.

A Strategy Family is not a stable Strategy Identity by itself.

---

## 9.4 Strategy Identity — `CANONICAL`

The stable identity of a formal strategy, including result-affecting policy semantics, scope and dependencies.

A name such as:

```text
ETF Rotation Strategy
```

is not sufficient identity.

---

## 9.5 Entry — `CANONICAL DECISION ROLE`

The strategy decision problem of whether a new exposure should be established now for an eligible opportunity.

Entry is not a synonym for Candidate ranking.

---

## 9.6 Entry Proposal — `CANONICAL`

A strategy-level recommendation to establish new exposure.

It should identify:

- opportunity eligibility;
- why entry should occur now;
- supporting evidence;
- timing and price convention;
- invalidation;
- accepted risk;
- expiry.

---

## 9.7 Position Lifecycle — `CANONICAL`

The ongoing strategy decision process for an existing exposure.

Canonical lifecycle actions are:

```text
HOLD
ADD
REDUCE
ROTATE
EXIT
```

These actions are not a mandatory linear sequence.

---

## 9.8 Position Lifecycle Proposal — `CANONICAL`

A recommendation about an existing strategy exposure.

---

## 9.9 Strategy Proposal — `CANONICAL`

**Definition**

The canonical output of an authoritative Strategy Policy for a Decision Scope.

A Strategy Proposal may include:

- strategy identity;
- decision scope;
- instrument;
- decision time;
- current strategy-position-state reference;
- canonical action;
- intent;
- setup or trigger reference;
- Candidate Prediction reference;
- context references;
- reason codes;
- risk and invalidation state;
- expiry;
- proposed exposure range or delta;
- trace and artifact references.

A Strategy Proposal is not a Portfolio Decision and does not imply execution.

---

## 9.10 Canonical Strategy Action — `CANONICAL`

The platform-level action vocabulary is:

```text
NO_ACTION
ENTER
HOLD
ADD
REDUCE
ROTATE
EXIT
```

Strategy-specific actions may exist below this level only with explicit mapping.

---

## 9.11 `NO_ACTION` — `CANONICAL ACTION`

No authoritative position action is proposed.

It does not imply:

- data is valid;
- a position was evaluated;
- execution was attempted;
- an existing position should continue.

Supporting reason or status should distinguish why no action exists.

---

## 9.12 `ENTER` — `CANONICAL ACTION`

Establish a new strategy exposure.

`ENTER` is distinct from `ADD`.

---

## 9.13 `HOLD` — `CANONICAL ACTION`

An existing strategy exposure has been evaluated and continued exposure is the current Strategy Proposal.

`HOLD` must not be used as a universal null value.

---

## 9.14 `ADD` — `CANONICAL ACTION`

Increase an existing strategy exposure based on marginal evidence and current position context.

`ADD` is not repeated Entry.

---

## 9.15 `REDUCE` — `CANONICAL ACTION`

Decrease an existing strategy exposure while retaining some exposure for the relevant strategy scope.

---

## 9.16 `ROTATE` — `CANONICAL ACTION`

A comparative strategy decision to replace or reallocate exposure from a current opportunity toward an eligible alternative after considering expected remaining value, switching cost, risk and concentration.

`ROTATE` is not merely syntactic `EXIT + ENTER`.

---

## 9.17 `EXIT` — `CANONICAL ACTION`

Terminate the relevant strategy exposure.

`EXIT` intent must be explicit where it affects validation.

---

## 9.18 Exit Intent — `CANONICAL`

The purpose behind an Exit or exit-like decision.

Canonical families may include:

```text
PROFIT_TAKING
RISK_STOP
THESIS_INVALIDATION
TREND_INVALIDATION
STRUCTURE_BREAK
DISTRIBUTION_EXHAUSTION
TIME_EXPIRY
ROTATION
FORCED_EXIT
```

Different Exit Intents require different validation semantics.

---

## 9.19 Thesis — `CANONICAL`

The explicit reason an exposure is expected to remain valid.

A Thesis may reference:

- target;
- setup;
- factors;
- context;
- expected path;
- expected horizon.

---

## 9.20 Invalidation — `CANONICAL`

A condition under which a research claim, strategy thesis, model assumption or decision premise should no longer be treated as valid for the relevant scope.

Invalidation must be distinguished from ordinary adverse noise where possible.

---

## 9.21 Risk State — `CANONICAL QUALIFIED STATE`

The current strategy- or system-owned assessment of risk relevant to a decision.

Risk State is not the same as Strategy Action.

---

## 9.22 Forced Exit — `CANONICAL EXIT INTENT`

An exit required by rules, eligibility, market structure, risk policy or operational constraints rather than an ordinary Alpha thesis decision.

---

# 10. Position and Portfolio Terms

## 10.1 Position — `DISCOURAGED UNQUALIFIED`

The word is overloaded.

Formal contracts should distinguish:

```text
Strategy Exposure
Virtual Strategy Exposure
Strategy Position State
Portfolio Position
Physical Position
Base Position
T Position
```

---

## 10.2 Strategy Exposure — `CANONICAL`

The exposure logically owned by one Strategy within its own decision scope.

It may be virtual relative to the physical brokerage account.

---

## 10.3 Virtual Strategy Exposure — `CANONICAL`

A strategy-local accounting representation used when multiple strategies or sleeves contribute to one physical account position.

---

## 10.4 Strategy Position State — `CANONICAL`

The state required by a Strategy to evaluate an existing exposure.

It may include:

- entry thesis;
- entry time;
- reference price;
- holding age;
- virtual exposure;
- MFE / MAE;
- previous adds or reductions;
- lifecycle mode;
- risk state.

---

## 10.5 Strategy Sleeve — `CANONICAL`

A logically separated strategy allocation or mandate inside a broader portfolio.

Examples:

- long-term dividend sleeve;
- active/T overlay sleeve;
- cross-sectional trend sleeve.

A Sleeve is not necessarily a separate brokerage account.

---

## 10.6 Base Position — `STRATEGY-SPECIFIC`

A persistent core exposure used by strategies such as long-term dividend plus active-overlay designs.

It is not a universal platform position type.

---

## 10.7 T Position / Active Overlay — `STRATEGY-SPECIFIC`

A strategy-local active exposure managed around a Base Position.

It is not a universal lifecycle model for all strategies.

---

## 10.8 Portfolio Decision — `CANONICAL`

**Definition**

The account-level resolution of one or more Strategy Proposals into final capital-allocation decisions.

The Portfolio System owns:

- final target exposure;
- capital allocation;
- concentration;
- sector/theme constraints;
- cash allocation;
- risk budgets;
- cross-strategy conflict resolution.

---

## 10.9 Portfolio Position — `CANONICAL`

The account-level position representation owned by the Portfolio System before or after execution reconciliation, depending on the explicit contract.

Use a more specific term when distinguishing desired from actually held exposure.

---

## 10.10 Physical Position — `CANONICAL`

The actual account-level held position after execution results and account reconciliation.

Multiple Strategy Exposures may map into one Physical Position.

---

## 10.11 Position State — `DISCOURAGED UNQUALIFIED`

Always identify the owner:

```text
Strategy Position State
Portfolio Position State
Physical Position State
```

The Legacy `dividend_t.models.PositionState` is strategy-specific and must not become the universal platform position contract.

---

# 11. Execution Terms

## 11.1 Execution Request — `CANONICAL`

An executable instruction derived from an approved Portfolio Decision under an execution contract.

It may specify:

- instrument;
- side;
- quantity or target delta;
- timing;
- order semantics;
- constraints;
- reference decision and portfolio identities.

---

## 11.2 Execution Result — `CANONICAL`

The record of what actually happened when an Execution Request was processed.

It must distinguish intended from realized execution.

---

## 11.3 Order Intent — `LEGACY-ONLY / DISCOURAGED FOR NEW PLATFORM CONTRACTS`

The current Legacy `OrderIntent` mixes strategy decision and pre-execution semantics.

New platform flow should prefer:

```text
Strategy Proposal
    ↓
Portfolio Decision
    ↓
Execution Request
    ↓
Execution Result
```

---

## 11.4 Fill — `CANONICAL`

An executed transaction result under the Execution System.

A Strategy Proposal, Portfolio Decision or Execution Request must never be described as a Fill.

---

## 11.5 Execution Constraint — `CANONICAL`

A rule or state affecting whether and how an approved action can be executed.

Examples:

- T+1 sellability;
- lot size;
- suspension;
- price limits;
- liquidity;
- broker restrictions.

---

## 11.6 Slippage — `CANONICAL`

The difference between an assumed reference price and modeled or realized execution price under a defined execution model.

---

## 11.7 Transaction Cost — `CANONICAL`

Explicit fees, taxes and modeled trading costs associated with execution.

Cost assumptions are part of Experiment Identity when result-affecting.

---

# 12. Market, ETF and Theme Terms

## 12.1 Market Context — `CANONICAL`

Observed or derived information describing the broader market environment.

Examples:

- breadth;
- trend;
- amount;
- volatility;
- limit-up/down structure;
- liquidity conditions.

Market Context is not automatically a Market Regime, Strategy Gate or Portfolio Exposure Cap.

---

## 12.2 Market Regime — `CANONICAL`

A versioned state or model describing a market environment under an explicit algorithm and research scope.

Possible downstream roles include:

- context;
- interaction term;
- Candidate conditioning;
- strategy gate;
- portfolio risk input.

Each role requires separate attribution.

---

## 12.3 Model Self-State — `CANONICAL QUALIFIED TERM`

A summary of recent model or strategy behavior, such as holding success or proposal outcomes.

Model Self-State is not the same as observed Market Context.

---

## 12.4 ETF Context — `CANONICAL`

ETF-derived information used as context for another research or decision process, such as stock Candidate Discovery.

ETF Context is not automatically a direct ETF trading strategy.

---

## 12.5 ETF Rotation — `CANONICAL STRATEGY / RESEARCH FAMILY`

The comparative process of ranking, selecting or reallocating among ETFs under an explicit target and strategy policy.

---

## 12.6 Direct ETF Trading Strategy — `CANONICAL QUALIFIED TERM`

A Strategy whose traded instruments are ETFs.

It must be distinguished from using ETFs only as context for stock selection.

---

## 12.7 Theme Context — `CANONICAL`

PIT-valid theme-related information used as context or features for another research object.

---

## 12.8 Theme Rotation — `CANONICAL RESEARCH / STRATEGY FAMILY`

The process of estimating relative opportunity across themes under explicit PIT-valid membership and research semantics.

---

## 12.9 Leader Resonance — `QUALIFIED RESEARCH CONSTRUCT`

A measurable construct representing whether leading instruments within an industry or theme are strengthening together.

It must have explicit algorithm, PIT membership, source lineage and target relationship.

The phrase alone is not a validated factor.

---

# 13. Validation Terms

## 13.1 Validation — `CANONICAL PROCESS TERM`

The evidence process used to evaluate whether a Research Object supports a scoped claim under a defined protocol.

When referring to the Sample Role, use uppercase:

```text
VALIDATION
```

---

## 13.2 Validation Protocol — `CANONICAL`

The defined rules governing:

- sample roles;
- split policy;
- leakage controls;
- baselines;
- metrics;
- statistical treatment;
- economic assumptions;
- robustness;
- promotion conditions;
- sealed-test rules where applicable.

---

## 13.3 Evidence Level — `CANONICAL`

The level of empirical authority earned by a Research Object under the Validation Constitution.

Canonical ladder:

```text
E0 — IDEA
E1 — EXPLORATORY
E2 — REPRODUCIBLE
E3 — CONTROLLED_VALIDATION
E4 — OOS_VALIDATED
E5 — SEALED_TESTED
E6 — PROMOTION_CANDIDATE
```

Evidence Level is not Data Eligibility or Authority State.

---

## 13.4 Authority State — `CANONICAL`

The current governance or operational status of a Research Object after evidence and review are considered.

Examples include:

```text
SHADOW
PROMOTED_FOR_SCOPE
DEGRADED
QUARANTINED
RETIRED
```

---

## 13.5 `E0 — IDEA` — `CANONICAL EVIDENCE LEVEL`

Concept or hypothesis exists without meaningful empirical evidence.

---

## 13.6 `E1 — EXPLORATORY` — `CANONICAL EVIDENCE LEVEL`

The object has been examined under flexible exploratory conditions.

It must not be presented as final OOS evidence.

---

## 13.7 `E2 — REPRODUCIBLE` — `CANONICAL EVIDENCE LEVEL`

The object can be rerun from identified inputs with stable semantic results.

Reproducibility is necessary but does not prove Alpha.

---

## 13.8 `E3 — CONTROLLED_VALIDATION` — `CANONICAL EVIDENCE LEVEL`

The object has been evaluated under controlled sample roles, baselines and protocols without consuming final untouched evidence as a routine tuning loop.

---

## 13.9 `E4 — OOS_VALIDATED` — `CANONICAL EVIDENCE LEVEL`

The frozen or selected object has evidence on data outside the fitting and routine selection process under the declared protocol.

OOS authority remains scope-specific.

---

## 13.10 `E5 — SEALED_TESTED` — `CANONICAL EVIDENCE LEVEL`

The object has been evaluated on a restricted previously uninspected final holdout under a readiness gate.

A Sealed Test is a scarce evidence event.

---

## 13.11 `E6 — PROMOTION_CANDIDATE` — `CANONICAL EVIDENCE LEVEL`

The object has enough evidence to enter formal promotion review.

It is not automatic promotion.

**Naming rule**

When ambiguity is possible, include the `E6` prefix.

Do not use bare `PROMOTION_CANDIDATE` in a new API if it could be confused with a workflow or authority state.

---

## 13.12 Promotion — `CANONICAL`

A scope-specific governance decision granting higher authority to a Research Object after evidence review.

Promotion is not the automatic consequence of one passing metric.

---

## 13.13 `PROMOTED_FOR_SCOPE` — `CANONICAL AUTHORITY STATE`

The object has approved authority for an explicit scope.

Promotion outside that scope requires additional evidence.

---

## 13.14 `SHADOW` — `CANONICAL AUTHORITY STATE`

The object may run and produce observable outputs without being the authoritative capital or decision path.

`SHADOW` must be distinguished from the Sample Role:

```text
SHADOW_OBSERVATION
```

---

## 13.15 `SHADOW_OBSERVATION` — `CANONICAL SAMPLE ROLE`

Forward observation data or period used to monitor live-like behavior without automatic capital authority.

---

## 13.16 Degradation / `DEGRADED` — `CANONICAL`

A reduction in evidence-supported effectiveness, reliability, calibration, data quality or operational validity that may require reduced authority or remediation.

---

## 13.17 Quarantine / `QUARANTINED` — `CANONICAL`

Temporary suspension of authority because evidence integrity, data, implementation or operational safety is uncertain.

Quarantine is not the same as permanent retirement.

---

## 13.18 Retirement / `RETIRED` — `CANONICAL`

The lifecycle state in which an object is no longer granted active authority or expected to receive ordinary maintenance as a current solution.

Historical identity, evidence and failure reason should remain preserved.

---

## 13.19 Out-of-Sample / OOS — `CANONICAL, MUST BE QUALIFIED WHEN FORMAL`

Evaluation outside the sample used for fitting or routine selection under a declared protocol.

Use:

```text
OOS_TEST
```

for the Sample Role and:

```text
E4 — OOS_VALIDATED
```

for the Evidence Level.

Bare `OOS` does not describe how often the sample was inspected or whether it remained independent.

---

## 13.20 Sealed Test — `CANONICAL`

A restricted final holdout used under explicit readiness and access governance.

It is not another tuning set.

---

## 13.21 Walk-Forward Validation — `CANONICAL`

A chronological validation protocol that repeatedly fits, selects or calibrates on past windows and evaluates on later windows under a reproducible schedule.

---

## 13.22 Purging — `CANONICAL`

Removal of observations whose label-information windows overlap across a training/evaluation boundary when such overlap would compromise the validation design.

---

## 13.23 Embargo — `CANONICAL`

A gap between sample periods introduced when dependence or information carryover requires it.

Purging and Embargo are tools, not mandatory rituals for every experiment.

---

## 13.24 Calibration — `CANONICAL`

The process of mapping model output to probability semantics or another declared calibrated quantity.

Calibration fitting and calibration evaluation must respect sample isolation.

---

## 13.25 Metric Contract — `CANONICAL`

The versioned definition of what a metric measures, how it is calculated, for which object and decision problem, and under what population or aggregation semantics.

---

## 13.26 Hit Rate — `CANONICAL DIAGNOSTIC METRIC, NOT UNIVERSAL PROOF`

The proportion of events meeting a defined hit condition.

Hit Rate must identify:

- event definition;
- horizon;
- population;
- payoff context;
- decision intent where relevant.

It is not a universal strategy-quality metric.

---

## 13.27 Multiple Testing — `CANONICAL`

The research-selection problem created when many features, thresholds, targets, universes, horizons or model variants are tried and only favorable results are emphasized.

Experiment history is part of evidence context.

---

## 13.28 Effective Sample Size — `CANONICAL CONCEPT`

The amount of genuinely independent information in a sample after considering dependence such as:

- same-date cross-sectional correlation;
- overlapping horizons;
- repeated symbols;
- common sector shocks;
- common market shocks.

Raw row count is not automatically Effective Sample Size.

---

# 14. Sample Role Terms

## 14.1 `DEVELOPMENT` — `CANONICAL SAMPLE ROLE`

Used for repeated exploration, debugging, feature design and early hypothesis iteration.

Repeatedly inspected Development data is not untouched evidence.

---

## 14.2 `TRAIN` — `CANONICAL SAMPLE ROLE`

Used to fit learned parameters, weights, thresholds, priors or transformations.

Anything learned from TRAIN becomes part of artifact identity.

---

## 14.3 `VALIDATION` — `CANONICAL SAMPLE ROLE`

Used for controlled model, feature, threshold or policy selection.

Repeated optimization against VALIDATION consumes its independence.

---

## 14.4 `CALIBRATION` — `CANONICAL SAMPLE ROLE`

Used to fit calibration artifacts.

It is not the final untouched test by default.

---

## 14.5 `OOS_TEST` — `CANONICAL SAMPLE ROLE`

Used to evaluate a frozen or selected object outside fitting and routine selection data.

Repeated design changes based on its results reduce its future independence.

---

## 14.6 `SEALED_TEST` — `CANONICAL SAMPLE ROLE`

A restricted final holdout for high-authority evaluation.

---

## 14.7 `SHADOW_OBSERVATION` — `CANONICAL SAMPLE ROLE`

Forward observation used to assess live-like behavior and operational characteristics without automatic capital authority.

---

# 15. Reporting Epistemology Terms

The project requires research and trading discussions to distinguish different kinds of statements.

## 15.1 Fact — `CANONICAL`

A statement directly supported by identified data, source, code behavior or documented event.

A Fact should be traceable where practical.

---

## 15.2 Inference — `CANONICAL`

A reasoned interpretation derived from facts or model outputs.

An Inference is not a directly observed Fact.

---

## 15.3 Model Assumption — `CANONICAL`

A simplifying premise or convention required by a model, simulation or analysis.

Examples:

- execution at next eligible bar under a specified fill rule;
- constant slippage assumption;
- a chosen target horizon;
- a defined universe filter.

Assumptions must remain explicit when result-affecting.

---

## 15.4 Research Result — `CANONICAL`

An output from an identified experiment under a defined evidence level.

A Research Result must not be promoted to universal fact beyond its validated scope.

---

## 15.5 Trading Plan — `CANONICAL USER-FACING TERM`

A conditional action plan based on current evidence, risk limits, triggers and invalidation conditions.

A Trading Plan is not a guaranteed forecast or return promise.

---

## 15.6 Risk Point — `CANONICAL USER-FACING TERM`

A condition, exposure or uncertainty that could make an expected outcome worse, invalidate assumptions or increase loss severity.

---

## 15.7 Invalidation Condition — `CANONICAL USER-FACING TERM`

An observable condition under which the current inference, model premise or Trading Plan should be reconsidered or rejected.

---

## 15.8 Follow-Up Observation Indicator — `CANONICAL USER-FACING TERM`

A measurable item that should be monitored after the current analysis because it may confirm, weaken or invalidate the working thesis.

---

# 16. Quantitative Evaluation Terms

## 16.1 IC — `CANONICAL ABBREVIATION`

Information Coefficient: a defined association measure between factor or model output and a future target.

The exact correlation method and aggregation semantics must be stated.

---

## 16.2 RankIC — `CANONICAL ABBREVIATION`

Rank-based Information Coefficient, commonly using rank correlation between factor or prediction ranking and future target ranking.

RankIC is not a universal promotion metric.

---

## 16.3 MFE — `CANONICAL ABBREVIATION`

Maximum Favorable Excursion under a defined path and horizon convention.

The exact reference price and path window must be explicit.

---

## 16.4 MAE — `CANONICAL ABBREVIATION`

Maximum Adverse Excursion under a defined path and horizon convention.

---

## 16.5 Coverage — `CANONICAL`

The proportion of the eligible population or required observations for which a research object produces valid output.

Coverage changes can materially affect interpretation.

---

## 16.6 Top-K — `CANONICAL, MUST DEFINE K AND POPULATION`

The highest-ranked `K` opportunities within a declared Candidate Population and Decision Time.

---

## 16.7 Quantile Spread — `CANONICAL`

The difference in target outcomes between defined prediction or factor quantiles.

Quantile construction and population must be explicit.

---

## 16.8 Monotonicity — `CANONICAL`

The degree to which target outcomes change consistently across ordered factor, score or prediction groups.

---

## 16.9 Turnover — `CANONICAL, MUST BE OWNER-QUALIFIED WHEN NEEDED`

The amount of change in rankings, portfolio holdings or traded exposure over time.

Use qualifiers such as:

```text
Ranking Turnover
Portfolio Turnover
Trading Turnover
```

---

## 16.10 Capacity — `CANONICAL`

The amount of capital a strategy or execution process may plausibly deploy before liquidity, market impact or concentration materially changes expected outcomes.

---

# 17. Market Data and Microstructure Abbreviations

## 17.1 OHLCV — `CANONICAL ABBREVIATION`

Open, High, Low, Close and Volume bar data.

Amount may be available separately.

OHLCV-derived constructs do not become independent information merely because they use different transformations.

---

## 17.2 VWAP — `CANONICAL ABBREVIATION`

Volume-Weighted Average Price under an explicit data and formula contract.

VWAP provenance and units must be known when used formally.

---

## 17.3 Level 1 / L1 — `CANONICAL`

Market data generally representing first-level quote or best-bid/offer information under a provider-specific contract.

Exact field semantics depend on the provider.

---

## 17.4 Level 2 / L2 — `CANONICAL`

More granular order-book, quote or trade data under an exchange, broker or vendor contract.

Level 2 is strategy-specific research input, not a universal requirement for all Alpha research.

---

## 17.5 T+1 — `CANONICAL A-SHARE EXECUTION TERM`

The A-share sellability constraint under which newly purchased shares are generally not sellable until the next eligible trading day, subject to applicable instrument and rule specifics.

Execution logic must use the versioned applicable rule rather than relying on a slogan alone.

---

## 17.6 ST — `CANONICAL A-SHARE REFERENCE TERM`

A special-treatment classification affecting eligibility, risk and price-limit rules under applicable historical exchange and regulatory semantics.

Current ST state must not substitute for historical PIT ST state.

---

# 18. Legacy-to-V2 Terminology Mapping

This section is normative for migration interpretation.

## 18.1 `dividend_t` namespace — `LEGACY DOMAIN NAMESPACE`

**Current meaning**

Contains both Dividend-T strategy logic and de facto platform infrastructure accumulated historically.

**Canonical interpretation**

```text
dividend_t
=
Legacy Strategy Domain + Legacy Research Assets
```

It is not the project identity.

New platform-wide capabilities should migrate to bounded-context ownership rather than extending `dividend_t` as the default platform namespace.

---

## 18.2 `CandidateSignal` — `LEGACY-ONLY BUNDLED CONTRACT`

**Current Legacy behavior**

Combines:

- Legacy action-oriented `Signal`;
- setup code;
- intent;
- confirmations;
- reasons;
- risk enforcement;
- decision-bar timing.

**Canonical migration interpretation**

Preserve valuable concepts:

```text
Setup
Intent
Confirmation
Risk Enforcement
Decision Trace
```

but separate them from:

```text
Candidate Prediction
Strategy Proposal
```

A Legacy `CandidateSignal` must not become the canonical Candidate Discovery output.

---

## 18.3 `SignalIntent` — `LEGACY DOMAIN TERM WITH REUSABLE PRINCIPLE`

**Current Legacy meaning**

Classifies broad strategy intent such as:

```text
MEAN_REVERSION_T
TREND_FOLLOWING
RISK_REDUCTION
BASE_ACCUMULATION
```

**Canonical interpretation**

The principle of explicit Intent is reusable.

The exact enum remains strategy-domain-specific unless generalized through a new canonical Strategy Intent contract.

---

## 18.4 `PrimarySetupCode` — `LEGACY STRATEGY SETUP TAXONOMY`

Useful for historical behavior, research strata and strategy-specific setup identification.

It is not a universal Candidate taxonomy.

---

## 18.5 `Signal` in `models.py` — `LEGACY-ONLY ACTION ENUM`

Map to canonical actions only through explicit strategy-specific semantics.

Example mappings may require context:

```text
BUILD_BASE → ENTER or ADD, depending on existing strategy exposure
BUY_T → ENTER or ADD, depending on strategy state
SELL_T → REDUCE or EXIT, depending on remaining exposure
CLEAR → EXIT
```

The mapping must not be guessed from the enum name alone.

---

## 18.6 Legacy `HOLD` — `MUST BE DISAMBIGUATED`

Current Legacy code may use `HOLD` as a null or fallback action.

Canonical V2 `HOLD` requires:

```text
Existing exposure
+
Explicit evaluation
+
Continued exposure proposal
```

Otherwise use a more accurate status such as:

```text
NO_ACTION
MISSING
UNAVAILABLE
BLOCKED
```

under the appropriate owner.

---

## 18.7 `StrategyDecision` — `LEGACY-ONLY INTEGRATED OUTPUT`

**Current Legacy behavior**

Combines:

- strategy signal;
- score breakdown;
- position limits;
- suggested trade percentage;
- reasons;
- warnings;
- `OrderIntent`;
- decision trace.

**Canonical migration interpretation**

Future ownership must separate:

```text
Strategy Proposal
Portfolio Decision
Execution Request
```

The Legacy type may remain for compatibility and characterization.

---

## 18.8 `OrderIntent` — `LEGACY-ONLY`

Current Legacy pre-execution object.

Future canonical chain:

```text
Strategy Proposal
    ↓
Portfolio Decision
    ↓
Execution Request
    ↓
Execution Result
```

---

## 18.9 `PositionState` in `dividend_t.models` — `LEGACY STRATEGY-SPECIFIC STATE`

Current fields include:

- symbol position percentage;
- base position percentage;
- T position percentage;
- cash;
- sellable percentage;
- cycle-stock flag;
- T-failure count.

This is useful for Dividend-T behavior.

It is not the canonical portfolio or physical-position model.

---

## 18.10 `timing_action` — `LEGACY APPLICATION / MODEL FIELD`

A timing engine output used by current research interfaces.

It must not coexist as a second final action authority beside a migrated canonical Strategy Proposal for the same Decision Scope unless explicitly labeled:

- shadow;
- diagnostic;
- baseline.

---

## 18.11 `signal` — `LEGACY APPLICATION FIELD`

A Legacy strategy output.

Do not expose both `signal` and `timing_action` as co-equal final authorities in migrated scopes.

---

## 18.12 `up_probability_*` or Probability-Like Output — `LEGACY SEMANTIC RISK`

A field named probability must have:

- target event;
- horizon;
- population;
- calibration method;
- calibration evidence;
- model identity.

Otherwise migrate the field to an honestly named:

```text
score
heuristic estimate
model score
```

or attach explicit `uncalibrated` status.

---

## 18.13 `certainty` — `LEGACY MIXED COMPOSITE`

Current Legacy certainty-like logic combines heterogeneous inputs.

Canonical interpretation:

```text
Mixed-Family Composite Score
```

unless a future model earns a more specific calibrated semantic claim.

`certainty` must not imply probability merely by name.

---

## 18.14 `attention` — `LEGACY OHLCV-DERIVED PROXY`

Canonical interpretation:

```text
OHLCV-Derived Attention Proxy
```

unless direct attention data is introduced under a separate identity.

---

## 18.15 `sell_pressure` — `LEGACY OHLCV-DERIVED PROXY`

Canonical interpretation:

```text
OHLCV-Derived Sell-Pressure Proxy
```

It is not direct observation of future sell orders or total holder intent.

---

## 18.16 `capital_flow_score` — `MUST SPLIT SOURCE CLASS`

Future identities must distinguish, as applicable:

```text
Observed Real Flow
Order-Flow-Derived Measure
Bar-Derived Flow Proxy
Heuristic Flow Score
```

One score identity must not silently change information class depending on data availability.

---

## 18.17 `rehearsal_range` in Legacy MACD OOS — `LEGACY SAMPLE-PARTITION TERM`

It is not the canonical Data Eligibility class:

```text
REHEARSAL
```

Future migration must map the Legacy partition to an explicit Sample Role or workflow stage.

Historical manifests may preserve the old field name.

---

## 18.18 `FORMAL_FINAL_CANDIDATE` — `LEGACY LOCAL DATASET CLASSIFICATION`

It is not a canonical project-wide Data Eligibility class.

Future platform semantics must separate:

```text
Data Eligibility
Sample Role
Evidence Level
Promotion / Authority State
```

---

## 18.19 `point_hit_rate` — `LEGACY DIAGNOSTIC`

Useful for historical timing-point diagnostics.

It is not the universal validation contract for:

- Entry;
- profit taking;
- risk stops;
- thesis invalidation;
- rotation;
- forced exits.

---

## 18.20 `BUY_POINT_5D_PRIORS` — `LEGACY LEARNED ARTIFACT EMBEDDED IN SOURCE`

Canonical migration representation:

```text
Versioned Learned Artifact
+
Estimation Sample Identity
+
Target Definition
+
Validity Scope
```

Historical values are not timeless market constants.

---

## 18.21 `CoscoTimingEngine` — `LEGACY INTEGRATION ENGINE`

Canonical interpretation:

A dense integration engine containing many useful research hypotheses and responsibilities.

It is not:

- the universal Candidate model;
- the Feature Registry;
- the Strategy Platform;
- the Portfolio System.

New platform-wide responsibility must not be added to it.

---

## 18.22 `backtest.py` — `LEGACY BEHAVIOR LABORATORY / GOD OBJECT`

Canonical interpretation:

A valuable integrated research and behavior-preservation asset containing strategy, lifecycle, execution, state and reporting knowledge.

Migration must extract by ownership, not copy the file into a new God Object.

---

## 18.23 `market_environment.py` — `LEGACY MIXED-CONTEXT ASSET`

Current implementation may mix:

```text
Observed Market Context
Model Self-State
Strategy Gate
Portfolio Exposure Cap
```

Future migration must separate these owners.

The current object must not be renamed wholesale as the canonical Market Regime model.

---

# 19. Discouraged Ambiguous Phrases

## 19.1 “The signal says buy” — `DISCOURAGED`

Replace with the precise chain, for example:

```text
Candidate Model ranks the instrument in Top-K.
Entry Policy proposes ENTER.
Portfolio Decision authorizes exposure.
Execution Result records the fill.
```

---

## 19.2 “The model works” — `DISCOURAGED`

Replace with a scoped claim:

```text
Model X has E4 OOS evidence for Target Y,
Population P,
Decision Time T,
and Evaluation Period D,
relative to Baseline B.
```

---

## 19.3 “Formal data” — `DISCOURAGED UNQUALIFIED`

Use:

```text
FORMAL_RESEARCH-eligible dataset for Scope S
```

or state the actual eligibility and claim.

---

## 19.4 “The test set” — `DISCOURAGED UNQUALIFIED`

Use the canonical Sample Role:

```text
OOS_TEST
SEALED_TEST
VALIDATION
```

because their access and authority differ.

---

## 19.5 “Confidence” — `DISCOURAGED UNQUALIFIED`

Possible meanings include:

- model score;
- probability;
- uncertainty estimate;
- subjective analyst confidence;
- evidence strength.

Use the precise term.

---

## 19.6 “Probability” — `PROHIBITED WITHOUT PROBABILITY SEMANTICS`

Do not use without an event, horizon, population and calibration status.

---

## 19.7 “Flow” — `DISCOURAGED UNQUALIFIED`

Use:

```text
Observed Real Flow
Order-Flow-Derived Measure
Bar-Derived Flow Proxy
Heuristic Flow Score
ETF Share Change
```

as applicable.

---

## 19.8 “Position” — `DISCOURAGED UNQUALIFIED`

Use:

```text
Strategy Exposure
Strategy Position State
Portfolio Position
Physical Position
Base Position
T Position
```

---

## 19.9 “State” — `DISCOURAGED UNQUALIFIED`

Always identify the owner and semantic domain.

---

## 19.10 “Score” — `DISCOURAGED WITHOUT TYPE`

Use:

```text
Feature Value
Composite Score
Model Score
Rank Score
Utility Score
Risk Score
```

and preserve its identity.

---

# 20. Canonical Naming Discipline for New Contracts

This section defines semantic naming discipline, not a complete schema specification.

## 20.1 Identity fields

Prefer explicit identity suffixes such as:

```text
*_id
*_version
*_ref
*_hash
```

when they represent distinct semantics.

Do not use a human-readable name as the only formal identity.

---

## 20.2 Time fields

Prefer semantic time names such as:

```text
source_event_time
source_publish_time
retrieved_at
available_at
finalized_at
effective_at
decision_time
execution_eligible_time
```

Avoid bare:

```text
time
date
timestamp
```

when several time semantics coexist.

---

## 20.3 Status fields

Qualify the owner:

```text
data_quality_status
research_status
authority_state
risk_state
execution_state
```

Avoid one universal `status` field when meanings differ.

---

## 20.4 Score fields

Name the semantic type:

```text
model_score
rank_score
risk_score
composite_score
calibrated_probability
expected_return
```

Do not call every numeric output `score`.

---

## 20.5 Action fields

Use canonical platform action values only at platform boundaries:

```text
NO_ACTION
ENTER
HOLD
ADD
REDUCE
ROTATE
EXIT
```

Strategy-specific action values must be mapped explicitly.

---

## 20.6 Missing and unavailable values

Do not encode semantically distinct states as a neutral number.

Distinguish, where applicable:

```text
MISSING
UNAVAILABLE
STALE
INVALID
UNSUPPORTED
BLOCKED
NO_ACTION
```

A neutral score such as `50` must not silently mean missing data unless the contract explicitly defines and validates that behavior.

---

# 21. Canonical End-to-End Vocabulary

The canonical platform chain is:

```text
Provider
    ↓
Source Artifact
    ↓
Adapter / Ingestion
    ↓
Normalized Observation
    ↓
Canonical PIT Data
    ↓
Dataset + Dataset Manifest
    ↓
Data Eligibility + Sample Role
    ↓
Raw Observation
    ↓
Primitive / Derived Feature
    ↓
Factor Candidate / Predictive Factor / Model Input
    ↓
Model Output / Candidate Prediction
    ↓
Strategy Policy
    ↓
Strategy Proposal
    ↓
Portfolio Decision
    ↓
Execution Request
    ↓
Execution Result
    ↓
Physical Position / Portfolio State Update
    ↓
Evidence Artifact
    ↓
Evidence Level
    ↓
Authority State
    ↓
Monitoring / Degradation / Quarantine / Retirement
```

This chain is conceptual.

Not every research experiment requires every stage.

The semantic boundaries remain authoritative.

---

# 22. Canonical Candidate-to-Execution Vocabulary

For the current first strategic priority:

```text
PIT Universe
    ↓
Candidate Population
    ↓
Registered Feature Materialization
    ↓
Candidate Model
    ↓
Candidate Prediction
    ↓
Entry Policy
    ↓
Entry Proposal / Strategy Proposal
    ↓
Portfolio Decision
    ↓
Execution Request
    ↓
Execution Result
```

For an existing exposure:

```text
Strategy Position State
    +
New Evidence
    +
Opportunity Cost
    ↓
Position Lifecycle Policy
    ↓
HOLD / ADD / REDUCE / ROTATE / EXIT Proposal
    ↓
Portfolio Decision
    ↓
Execution Request
    ↓
Execution Result
```

---

# 23. Canonical Evidence Vocabulary

The canonical evidence dimensions are:

```text
Data Eligibility
        ↓
Can this data support this class of claim?

Sample Role
        ↓
How may this dataset partition be used?

Evidence Level
        ↓
How strong is the empirical evidence earned by this object?

Authority State
        ↓
What authority does the object currently have?
```

Example:

```text
Dataset Eligibility:
FORMAL_RESEARCH

Sample Role:
OOS_TEST

Evidence Level after successful protocol:
E4 — OOS_VALIDATED

Authority State after review:
SHADOW
```

This is coherent.

The following is not:

```text
formal test candidate model
```

without distinguishing the dimensions.

---

# 24. Canonical Distinctions That Must Survive Implementation

The following distinctions are constitutional and must not be erased by convenience APIs.

## 24.1 Project identity

```text
Alpha Research Operating System
≠
One Strategy
```

## 24.2 Data

```text
Provider
≠
Dataset
```

```text
Normalized Observation
≠
PIT-Correct Formal Data
```

```text
Universe Membership
≠
Trading Eligibility
≠
Execution Feasibility
```

## 24.3 Features

```text
Indicator
≠
Feature
≠
Predictive Factor
```

```text
Semantic Family
≠
Source-Information Family
```

```text
Proxy
≠
Direct Observation
```

## 24.4 Prediction and decision

```text
Candidate Prediction
≠
Entry Proposal
```

```text
Strategy Proposal
≠
Portfolio Decision
```

```text
Portfolio Decision
≠
Execution Result
```

## 24.5 Actions

```text
NO_ACTION
≠
HOLD
```

```text
ENTER
≠
ADD
```

```text
REDUCE
≠
EXIT
```

```text
ROTATE
≠
Syntactic EXIT + ENTER
```

## 24.6 Positions

```text
Strategy Exposure
≠
Physical Position
```

```text
Base Position / T Position
≠
Universal Platform Position Model
```

## 24.7 Validation

```text
Data Eligibility
≠
Sample Role
≠
Evidence Level
≠
Authority State
```

```text
OOS_TEST
≠
E4 — OOS_VALIDATED
```

```text
SEALED_TEST
≠
E5 — SEALED_TESTED
```

```text
SHADOW_OBSERVATION
≠
SHADOW Authority State
```

## 24.8 Scores

```text
Score
≠
Probability
≠
Expected Return
≠
Decision Utility
```

---

# 25. Glossary Review Rules for Agents and Developers

Before introducing a new project-wide term, an agent or developer must check:

1. Does an existing canonical term already describe the concept?
2. Is the proposed term actually a new concept or merely a synonym?
3. Does the term imply stronger evidence than exists?
4. Does the term hide ownership?
5. Does the term collapse prediction, policy, portfolio or execution?
6. Does it conflict with Data Eligibility, Sample Role, Evidence Level or Authority State?
7. Does it reuse a Legacy name with a different meaning?
8. Does it turn a Proxy into a direct-observation claim?
9. Does it turn a Score into a Probability?
10. Does it create a second platform vocabulary for an existing concept?

If a new term is genuinely required:

```text
Define
    ↓
Assign Owner
    ↓
Define Boundary
    ↓
Map Related Terms
    ↓
Version Contract
    ↓
Update Glossary if Project-Wide
```

Agents must not invent project-wide terminology merely to make generated code locally convenient.

---

# 26. Minimum Semantic Contract for New Project-Wide Objects

A new project-wide object should be able to answer, as applicable:

```text
1. What is it called?
2. What exact concept does it represent?
3. Which bounded context owns it?
4. What is its scope?
5. What does it consume?
6. What does it produce?
7. What is it explicitly not?
8. What time semantics apply?
9. What identity/version semantics apply?
10. What evidence or authority semantics apply?
11. Which Legacy terms map to it, if any?
12. Which nearby canonical terms must remain distinct?
```

An object that cannot answer these questions should not become a new platform-wide abstraction by default.

---

# 27. Constitutional Glossary Commitments

The project commits to the following vocabulary rules.

1. **The project identity is Alpha Research Operating System, not any one Legacy strategy or model.**
2. **Legacy terminology may remain for compatibility but does not automatically become platform vocabulary.**
3. **Bare `Signal` is not the preferred canonical object for new V2 contracts.**
4. **Candidate Discovery produces predictions or rankings, not automatic trade actions.**
5. **Candidate Prediction, Strategy Proposal, Portfolio Decision and Execution Result remain distinct.**
6. **The canonical platform actions are `NO_ACTION`, `ENTER`, `HOLD`, `ADD`, `REDUCE`, `ROTATE` and `EXIT`.**
7. **`NO_ACTION` and `HOLD` remain semantically different.**
8. **State, Position, Score, Flow, Confidence and Signal must be qualified when ambiguity exists.**
9. **A Score is not a Probability without target and calibration authority.**
10. **A Proxy is not a direct observation.**
11. **Semantic Family and Source-Information Family remain distinct.**
12. **Representation methods such as MACD, Chan and Tuishen-inspired constructs do not create information independence by name.**
13. **Provider, Dataset and Data Eligibility remain distinct.**
14. **Data Eligibility, Sample Role, Evidence Level and Authority State remain independent dimensions.**
15. **`REHEARSAL` is the canonical data-eligibility class; Legacy `rehearsal_range` is not a platform Sample Role.**
16. **`FORMAL_FINAL_CANDIDATE` remains a Legacy local classification, not a global Data Eligibility class.**
17. **`OOS_TEST` is a Sample Role; `E4 — OOS_VALIDATED` is an Evidence Level.**
18. **`SEALED_TEST` is a Sample Role; `E5 — SEALED_TESTED` is an Evidence Level.**
19. **`SHADOW_OBSERVATION` is a Sample Role; `SHADOW` is an Authority State.**
20. **Strategy Exposure and Physical Position remain distinct.**
21. **Base Position and T Position remain strategy-specific concepts.**
22. **Strategy does not own final account allocation.**
23. **Portfolio does not imply execution.**
24. **Execution Request does not imply Fill.**
25. **Market Context, Market Regime, Model Self-State, Strategy Gate and Portfolio Exposure Cap remain distinct.**
26. **ETF Context and Direct ETF Trading Strategy remain distinct.**
27. **Research reports distinguish Fact, Inference, Model Assumption, Research Result, Risk, Invalidation and Follow-Up Observation.**
28. **New project-wide terminology must not create a second ontology for an existing canonical concept.**
29. **The Glossary must evolve only by preserving consistency with the substantive Constitution.**
30. **Semantic precision is treated as part of correctness, not as documentation polish.**

---

# 28. Constitutional Closure

Volumes `00–09` now define the complete foundational Constitution:

```text
00 — Project Vision
01 — Core Principles
02 — Architecture Blueprint
03 — Research Framework
04 — Data Constitution
05 — Factor Constitution
06 — Strategy Constitution
07 — Validation Constitution
08 — Roadmap
09 — Glossary
```

The Constitution now answers:

```text
Why does the project exist?
What principles are non-negotiable?
Who owns what?
How does research work?
What data is trustworthy for what claim?
What is a valid feature or factor?
How does information become a strategy proposal?
What evidence is required for authority?
In what order should the repository migrate?
What do the core terms mean?
```

The next phase is no longer constitutional invention.

It is implementation under constitutional control.

The first implementation work must follow the Roadmap rather than reopening foundational semantics without evidence.

The constitutional closure principle is:

> **Use one precise vocabulary for one authority model, preserve Legacy meaning where history requires it, and never allow ambiguous words to reconnect boundaries that the architecture deliberately separated.**
