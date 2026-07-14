# The Constitution of Market Regime Alpha

# Volume IX — Roadmap

> **Document:** `docs/constitution/08-Roadmap.md`  
> **Status:** Foundational / Normative  
> **Authority:** Project-wide migration sequence, implementation priorities, stage dependencies, phase gates, Legacy preservation, V2 construction order, and refoundation completion criteria  
> **Applies to:** Repository refoundation, architecture migration, data-platform work, feature/factor infrastructure, Candidate Discovery, validation infrastructure, strategy decomposition, ETF/Theme/Market Regime integration, portfolio and execution simulation, shadow observation, Legacy retirement, agents and future implementation plans  
> **Project:** `market-regime-alpha`  
> **Precedence:** Must remain consistent with `00-Project-Vision.md`, `01-Core-Principles.md`, `02-Architecture-Blueprint.md`, `03-Research-Framework.md`, `04-Data-Constitution.md`, `05-Factor-Constitution.md`, `06-Strategy-Constitution.md`, and `07-Validation-Constitution.md`

---

## 0. Purpose

The project has now defined:

```text
Vision
    ↓
Principles
    ↓
Architecture
    ↓
Research Lifecycle
    ↓
Data Governance
    ↓
Factor Governance
    ↓
Strategy Governance
    ↓
Validation Governance
```

The remaining problem is implementation order.

A good architecture can still fail if migrated in the wrong sequence.

The current repository is not an empty greenfield project. It already contains:

- working data adapters;
- a large `dividend_t` research domain;
- a `CoscoTimingEngine` integrating many hypotheses;
- a deterministic `DividendTStrategy`;
- explicit signal-intent and trace contracts;
- MACD experiment identity and controlled ablation;
- OOS and sealed-test governance assets;
- a fail-closed formal rehearsal dataset builder;
- a large integrated backtest with multiple lifecycle state machines;
- market-environment and broader-universe research code;
- web applications, dashboards, schedulers and notifications;
- ETF backtest prototypes;
- existing users and scripts that depend on Legacy import paths.

The repository also has structural constraints:

- most mature reusable logic still lives under `market_regime_alpha.dividend_t`;
- several classes own multiple future bounded-context responsibilities;
- current public project metadata still describes a buy/sell-point research tool rather than the target Alpha Research Operating System;
- the broader-universe builder explicitly warns that it is current-snapshot, not historical PIT;
- formal data and OOS mechanisms exist, but several are MACD-specific;
- Candidate Discovery does not yet exist as an independent cross-sectional research system;
- the current backtest contains substantial research knowledge but also a very large rule, state and parameter surface;
- the application layer can expose more than one decision semantic for the same instrument and time;
- current research interfaces and operational scripts are useful and must not be broken casually.

The project therefore requires a migration roadmap that does two things at once:

```text
Preserve accumulated knowledge
        +
Create a cleaner authority model
```

The governing question of this Roadmap is:

> **In what order should the current repository be migrated so that Candidate Discovery becomes useful early, formal research quality increases continuously, Legacy knowledge is preserved, and no new God Object is created during the transition?**

The central roadmap principle is:

> **Do not wait for a perfect future platform before producing new research value, and do not obtain speed by expanding the structures that the refoundation is intended to replace.**

---

# 1. Roadmap Authority and Boundaries

This Roadmap defines:

- migration order;
- stage dependencies;
- parallel workstreams;
- phase entry and exit gates;
- what must be frozen;
- what may be adapted;
- what should be built new;
- what must not block the current first strategic priority;
- when Legacy assets may be retired.

This Roadmap does **not** define:

- permanent calendar deadlines;
- guaranteed implementation duration;
- one vendor procurement decision;
- permanent model thresholds;
- final module-level API schemas;
- final portfolio optimization mathematics;
- broker-specific production deployment.

Those belong to implementation plans, specifications and future operational decisions.

---

# 2. Current Repository Migration Audit

The roadmap is grounded in the current repository rather than an idealized greenfield architecture.

---

## 2.1 Repository identity is still Legacy-facing

Current project metadata and entry documentation still primarily describe:

```text
A-share buy/sell point identification
signal validation
backtesting
Dividend-T research
```

The Python package itself is named correctly:

```text
market_regime_alpha
```

but much of the mature domain logic remains under:

```text
market_regime_alpha.dividend_t
```

This is expected during migration.

The Roadmap does **not** require a big-bang package rename.

The correct sequence is:

```text
Freeze target terminology
    ↓
Create V2 bounded-context modules
    ↓
Introduce compatibility boundaries
    ↓
Move authority gradually
    ↓
Retire Legacy paths only after replacement evidence exists
```

---

## 2.2 Existing directory organization is useful but not yet the target domain architecture

The repository already distinguishes:

```text
src/
tests/
scripts/
backtesting/
docs/
strategies/
data/
reports/
```

This is a useful repository-level boundary.

The refoundation does not require abandoning it.

The primary architectural migration occurs inside reusable code and research contracts, where the target bounded contexts are:

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

Repository-level folders and domain bounded contexts solve different problems.

---

## 2.3 `dividend_t` is both an asset and a coupling hotspot

The current `dividend_t` package contains valuable implementations across:

- factors and indicators;
- market environment;
- universe building;
- signal semantics;
- strategy logic;
- position sizing;
- timing;
- backtesting;
- OOS validation;
- formal dataset rehearsal;
- reporting.

It therefore behaves partly as:

```text
Legacy Strategy Domain
```

and partly as:

```text
De Facto Research Platform Namespace
```

The second role must end gradually.

The first role should remain supported as long as it provides research value.

---

## 2.4 Data access exists; formal PIT authority does not yet exist broadly

Current adapters can provide or normalize accessible market data.

This is useful for:

- exploration;
- application interfaces;
- local research;
- compatibility;
- prototyping.

However, the current repository itself already recognizes important formal-data gaps.

The broader-universe builder explicitly marks its output as:

```text
current-snapshot universe;
not point-in-time historical constituents
```

The formal rehearsal builder requires stronger evidence such as:

- finalized bars;
- PIT adjustment;
- trading calendar;
- PIT universe;
- eligibility sidecar;
- suspension sidecar;
- corporate actions;
- market context.

Therefore the Data Platform is not a blank slate, but formal PIT capability is still a critical dependency for high-authority Candidate Discovery.

---

## 2.5 Candidate Discovery is architecturally defined but not yet implemented as an independent system

The target Candidate system is:

```text
PIT Universe
    ↓
Comparable Cross-Sectional Features
    ↓
Target-Specific Prediction / Ranking
    ↓
CandidatePrediction
```

The repository currently has:

- watchlist scanning;
- symbol-specific timing;
- broader-universe construction;
- trend snapshots;
- strategy Candidate objects;
- historical buy-point classifications.

These are useful inputs and baselines.

They are not yet the target Candidate Discovery system.

In particular, Candidate Discovery must not be created by:

```text
Run CoscoTimingEngine across every stock
    ↓
Sort one symbol-specific score
```

unless cross-sectional comparability is independently demonstrated.

---

## 2.6 Current Market Environment code contains multiple future ownership layers

The current market-environment implementation contains useful constructs such as:

- trend;
- breadth;
- amount;
- limit-up/down structure;
- industry diffusion;
- market state.

It also contains outputs or inputs associated with:

- maximum total position;
- whether new buys are allowed;
- model holding win rate;
- model new-buy success rate.

This means the current module contains a mixture of:

```text
Market Description
+
Model Self-State
+
Strategy Gate
+
Portfolio Exposure Guidance
```

The module is therefore a valuable Legacy research asset, but it should not be copied wholesale into the V2 Market Context System.

Migration must separate:

```text
Observed Market Context
Model Performance State
Strategy Policy
Portfolio Risk Allocation
```

---

## 2.7 Existing strategy contracts contain strong migration seeds

`signal_intent.py` already provides:

- explicit intent;
- setup identity;
- entry confirmations;
- exit confirmations;
- risk severity;
- Candidate validation;
- DecisionTrace.

These are valuable semantic assets.

However, the current Candidate contract still carries action-oriented Legacy signals.

Therefore the migration direction is:

```text
Preserve:
    Intent
    Setup Identity
    Confirmation Identity
    Trace
    Risk Severity

Separate:
    Candidate Prediction
    Strategy Action
    Portfolio Decision
    Execution Result
```

---

## 2.8 Existing strategy implementation is a baseline, not the target architecture

`DividendTStrategy` currently performs several responsibilities:

```text
Score Construction
    ↓
Candidate Selection
    ↓
Policy Gate
    ↓
Sizing
    ↓
Final Signal
    ↓
Order Intent
```

This is useful as a deterministic integrated baseline.

It must not become the platform strategy abstraction.

The Roadmap therefore freezes new platform-level responsibility in this class.

---

## 2.9 `CoscoTimingEngine` is a research knowledge repository, not a V2 kernel

The engine currently integrates:

- multiple timeframes;
- trend;
- capital-flow logic;
- volume-price logic;
- Chan-derived structures;
- attention;
- memory;
- sell pressure;
- certainty;
- dynamic weighting;
- breakout;
- market regime;
- timing policy.

This makes it valuable for:

- Legacy replay;
- hypothesis mining;
- baseline comparison;
- extraction of specific validated components.

It is not suitable as:

- the V2 Feature System;
- the Candidate Discovery engine;
- the universal Strategy System.

Migration is selective, not mechanical.

---

## 2.10 The current backtest is a behavior-preservation laboratory

The large integrated backtest contains real research knowledge, including:

- attack states;
- beta-hold states;
- risk-on adds;
- position targets;
- follow-through logic;
- trailing-profit logic;
- distribution logic;
- market filters;
- execution assumptions;
- multiple strategy modes.

Its size and parameter surface also create:

- rule-accumulation risk;
- hidden state ownership;
- multiple-testing risk;
- attribution difficulty;
- migration difficulty.

The correct action is:

```text
Characterize
    ↓
Preserve behavior
    ↓
Extract by owner
    ↓
Validate extracted components
```

not:

```text
Delete and rewrite everything
```

and not:

```text
Continue adding all new platform logic into backtest.py
```

---

## 2.11 Current validation infrastructure is stronger than the current architecture around it

The repository already contains valuable patterns for:

- Experiment Identity;
- canonical config hashing;
- controlled four-arm ablation;
- counterfactual event traces;
- immutable run artifacts;
- checksums;
- split manifests;
- final-test readiness;
- sealed-test access control;
- fail-closed data rehearsal.

These mechanisms should be generalized early.

They are not optional late-stage polish.

A new Candidate Discovery system should not reproduce the old pattern of building model logic first and adding research identity much later.

---

## 2.12 Application surfaces already exist and should not drive domain authority

The repository already contains:

- web applications;
- dashboards;
- GitHub Pages snapshots;
- schedulers;
- notifications;
- local data collection paths.

These are useful operational interfaces.

They should be preserved where practical.

However:

```text
UI Field
≠
Domain Authority
```

Application interfaces must eventually consume canonical V2 outputs rather than defining semantics through existing JSON fields.

---

# 3. Migration Doctrine

The authoritative migration doctrine is:

```text
Legacy Freeze
    ↓
Characterize Existing Behavior
    ↓
Create Compatibility Boundaries
    ↓
Build Minimal V2 Kernel
    ↓
Run New Research Through V2 Contracts
    ↓
Extract Evidence-Backed Legacy Components
    ↓
Move Authority Gradually
    ↓
Retire Redundant Legacy Paths
```

This is a Strangler-style migration.

---

## 3.1 Legacy Freeze does not mean no bug fixes

Legacy Freeze means:

- no new platform-wide ownership;
- no new universal semantics;
- no uncontrolled rule accumulation;
- no new Candidate architecture inside a Legacy timing engine;
- no new lifecycle platform inside the Legacy backtest.

Allowed work includes:

- correctness fixes;
- reproducibility fixes;
- trace improvements;
- tests;
- security fixes;
- data-contract fixes;
- compatibility fixes;
- characterization.

---

## 3.2 Extraction must follow ownership, not file boundaries

A large Legacy file may contain several future modules.

The Roadmap does not require:

```text
one old file
    ↓
one new file
```

Instead:

```text
one old file
    ↓
several explicitly owned V2 capabilities
```

may be correct.

---

## 3.3 New V2 modules must not import Legacy policy by default

Compatibility adapters may call Legacy code.

The target dependency direction should not become:

```text
V2 Core
    ↓
Legacy Dividend-T Internals
```

as a permanent architecture.

New bounded contexts should depend on explicit contracts.

Legacy adapters may implement those contracts temporarily.

---

## 3.4 Research value must arrive before migration completion

The project must not spend months creating abstractions without producing research capability.

The first major new research deliverable remains:

```text
Candidate Discovery MVP
```

The Roadmap therefore uses staged authority:

```text
Exploratory Candidate Research
    ↓
Reproducible Candidate Research
    ↓
PIT-Correct Formal Candidate Validation
    ↓
Entry / Lifecycle Integration
```

Candidate research may begin before every future data source and feature family is complete.

Its evidence authority must remain honest.

---

# 4. The Two-Track Migration Model

The refoundation proceeds through two coordinated tracks.

---

## Track A — Platform and Evidence Spine

Builds:

- V2 contracts;
- identity;
- PIT data spine;
- universe contracts;
- feature registry;
- experiment artifacts;
- validation protocols;
- strategy proposal boundaries;
- portfolio and execution interfaces.

---

## Track B — Research Value Delivery

Builds and evaluates:

- Candidate Discovery baselines;
- factor baselines;
- Candidate targets;
- Entry policies;
- lifecycle policies;
- Exit models;
- ETF and Theme context;
- Market Regime research.

The tracks interact through explicit contracts.

Neither track is allowed to redefine the other silently.

---

## 4.1 Why the project must not use a pure waterfall

The following sequence is rejected:

```text
Build complete Data Platform
    ↓
Build complete Feature Store
    ↓
Build complete Research Platform
    ↓
Build complete Strategy Platform
    ↓
Only then test Candidate Discovery
```

This creates a high risk of over-engineering before the research problem is understood.

---

## 4.2 Why the project must not use pure Legacy extension

The following sequence is also rejected:

```text
Need Candidate Discovery
    ↓
Add market-wide loop around CoscoTimingEngine
    ↓
Add more scores to backtest.py
    ↓
Add more actions to Legacy Signal
```

This would deepen the exact coupling the refoundation is intended to remove.

---

# 5. Critical Path

The minimum dependency path to the first credible Candidate Discovery system is:

```text
Constitution Complete
    ↓
Minimal V2 Identity and Contract Kernel
    ↓
Reproducible Universe + Dataset Slice
    ↓
Minimal Feature Registry
    ↓
Candidate Target Contract
    ↓
Candidate Dataset Builder
    ↓
Simple Candidate Baselines
    ↓
Cross-Sectional Evaluation
    ↓
Generalized Validation Artifacts
    ↓
PIT-Correct Formal Rebuild
    ↓
OOS Candidate Validation
```

The following are **not** prerequisites for the first Candidate Discovery MVP:

- full Legacy factor migration;
- complete ETF rotation strategy;
- complete Theme rotation strategy;
- complete Market Regime model;
- production broker integration;
- full Position Lifecycle system;
- microservices;
- a universal feature store;
- Level 2 data;
- every possible A-share instrument.

---

# 6. Roadmap Stages

The roadmap is stage-gated.

Stages represent dependency and authority progression, not fixed calendar duration.

Several stages may overlap where their contracts are stable.

---

# R0 — Constitution and Refoundation Freeze

## Objective

Freeze the target direction before significant V2 implementation.

## Current status

Substantially complete after:

```text
00 Project Vision
01 Core Principles
02 Architecture Blueprint
03 Research Framework
04 Data Constitution
05 Factor Constitution
06 Strategy Constitution
07 Validation Constitution
08 Roadmap
```

`09-Glossary.md` remains required before large-scale semantic API migration.

## Required outputs

- Constitution volumes `00–09`;
- explicit precedence rules;
- canonical terminology;
- current refoundation constraints.

## Gate to exit R0

```text
No unresolved direction-level contradiction across Constitution volumes.
Canonical terminology is frozen in 09-Glossary.
Legacy freeze rules are explicit.
```

## Important rule

Characterization and non-semantic preparatory work may continue before `09` is complete.

New platform-wide semantic contracts should wait for Glossary alignment.

---

# R1 — Repository Truth and Legacy Characterization

## Objective

Create an evidence-backed map of what the repository currently does before extracting behavior.

## Why this stage exists

The current Legacy system contains useful knowledge embedded in:

- classes;
- enums;
- thresholds;
- state variables;
- report fields;
- application flows;
- backtest branches.

Extraction without characterization risks silent behavior loss.

## Work

### 1. Build a Legacy Asset Inventory

Classify major assets as:

```text
PRESERVE
ADAPT
EXTRACT
FREEZE
RECLASSIFY
REPLACE
RETIRE_LATER
```

### 2. Build a Responsibility Inventory

For major files and modules, identify ownership currently embedded for:

```text
Data
Universe
Feature
Context
Candidate
Entry
Lifecycle
Exit
Portfolio
Execution
Research
Application
```

### 3. Characterization Tests

Before extraction, preserve important existing behavior for:

- signal-intent validation;
- Candidate setup mapping;
- MACD experiment identity;
- counterfactual execution chronology;
- dataset manifests;
- sealed-test access control;
- key Legacy strategy paths;
- critical state transitions in the integrated backtest.

### 4. Freeze New Platform Expansion

Add clear code/document ownership notes where practical.

## Exit criteria

```text
Major Legacy assets classified.
Critical high-risk behavior has characterization coverage.
Future extraction targets are named by owner.
No new platform-wide feature is being added to CoscoTimingEngine or backtest.py.
```

---

# R2 — Minimal V2 Kernel and Compatibility Boundary

## Objective

Create the smallest stable platform contracts required for new work.

This stage must remain minimal.

It is not a rewrite of the whole project.

## Initial V2 kernel should include

### Core identity primitives

As applicable:

```text
ArtifactId
DatasetId
UniverseId
FeatureDefinitionId
FeatureMaterializationId
TargetId
ModelId
StrategyId
ExperimentId
```

Exact schemas belong to specifications.

### Canonical time semantics

Shared types or contracts for:

```text
Decision Time
Availability Time
Finalization
Next Eligible Execution
As-Of
```

### Research identity kernel

Generalize the strongest ideas from `MACDExperimentIdentity` into a project-wide contract.

Do not delete the MACD implementation immediately.

Use compatibility adapters.

### Canonical error / status semantics

Distinguish:

```text
MISSING
UNAVAILABLE
STALE
INVALID
UNSUPPORTED
BLOCKED
NO_ACTION
```

from neutral numeric values.

## Compatibility principle

Legacy code may be exposed through adapters such as:

```text
LegacyDataAdapter
LegacyFactorAdapter
LegacyStrategyAdapter
LegacyExperimentAdapter
```

The exact names are implementation choices.

## Exit criteria

```text
New V2 modules can identify data, features, targets, experiments and decisions without importing Legacy action semantics as platform truth.
Legacy paths still run through compatibility boundaries.
```

---

# R3 — Data Spine and PIT Universe

## Objective

Create the minimum trustworthy data substrate required for cross-sectional Candidate research.

## Priority order

### R3.1 Generalize provider and dataset contracts

Preserve current data adapters.

Add explicit distinction between:

```text
Provider Access
Normalized Observation
PIT-Curated Dataset
Research Role
```

### R3.2 Generalize dataset manifest identity

Build from current MACD OOS and formal rehearsal assets.

The generalized manifest should support more than one MACD-specific 5-minute dataset.

### R3.3 Create PIT Universe Contract

The current `build_largecap_universe()` is useful as an exploratory universe builder but explicitly not historical PIT authority.

The V2 Universe System must support effective historical membership and eligibility.

### R3.4 Separate tradability sidecars

At minimum, where required by the research claim:

- listing state;
- ST state;
- suspension;
- previous close;
- limit regime;
- limit-up/down prices;
- listing age;
- board eligibility.

### R3.5 Preserve rehearsal capability

The current fail-closed rehearsal builder should remain available while the formal system is generalized.

Rehearsal success proves pipeline readiness, not Alpha.

## Parallel data procurement track

Professional or broker/commercial data capability assessment may proceed in parallel.

No vendor is automatically trusted.

Acceptance is scoped by:

```text
Dataset
Field Set
Frequency
Date Range
PIT Guarantees
Research Use
License
```

## Exit criteria for exploratory Candidate work

```text
A reproducible cross-sectional development dataset exists.
Universe construction is explicit.
Known PIT limitations are declared.
Dataset identity is stable.
```

## Exit criteria for formal Candidate validation

```text
Required data is FORMAL_RESEARCH eligible.
PIT Universe and required sidecars are verified.
Decision-time semantics are verified.
Dataset manifests are immutable and reproducible.
```

---

# R4 — Feature Registry MVP and Legacy Factor Inventory

## Objective

Build only enough Feature System to support Candidate Discovery and controlled Legacy factor extraction.

## R4.1 Feature Registry MVP

The first registry must support, at minimum:

- definition identity;
- materialization identity;
- semantic family;
- source-information family;
- source lineage;
- decision-time availability;
- frequency;
- lookback;
- missingness policy;
- research status.

## R4.2 Legacy Factor Inventory

Inventory current constructs including:

- moving averages;
- momentum;
- MACD;
- trend;
- volume-price;
- attention proxy;
- sell-pressure proxy;
- capital-flow real/proxy variants;
- Chan-derived structures;
- Tuishen-inspired constructs;
- market context;
- fundamental and valuation fields.

## R4.3 Do not migrate every Legacy score

The first migration should prioritize:

```text
Simple
Interpretable
PIT-Correct
Cross-Sectionally Comparable
Baseline-Capable
```

features.

The goal is not to maximize feature count.

## Candidate baseline feature families may initially include

As permitted by available data:

- short/medium momentum;
- relative strength;
- volatility;
- liquidity;
- volume/amount change;
- price location;
- simple trend descriptors;
- market-relative behavior;
- industry-relative behavior where PIT mappings are available.

This is a baseline set, not a permanent model.

## Exit criteria

```text
Candidate MVP can materialize a versioned feature matrix from registered definitions.
Legacy factors are classified by lineage and migration status.
No anonymous formal feature columns are required for the baseline experiment.
```

---

# R5 — Candidate Discovery Rehearsal MVP

## Objective

Deliver the first independent cross-sectional Candidate Discovery system as early as possible.

This is the first major new research-value milestone of the refoundation.

## Scope

The MVP should be deliberately narrow.

Example scope may be:

```text
Liquid A-share subset
Defined decision time
Defined next-session or multi-session target
Simple PIT-compatible feature set
Top-K ranking
```

The exact scope belongs to a Candidate design document and Target Contract.

## Required components

```text
Universe Snapshot
    ↓
Candidate Dataset Builder
    ↓
Registered Feature Matrix
    ↓
Target Builder
    ↓
Baseline Models
    ↓
CandidatePrediction
    ↓
Cross-Sectional Evaluation
```

## Baseline ladder

Begin with simple models such as:

```text
Naive ranking
Simple momentum / relative-strength rule
Linear or logistic model where appropriate
Simple tree-based model
```

Complex models do not enter first by default.

## Important constraint

R5 may use:

```text
EXPLORATORY
or
REHEARSAL
```

eligible data for pipeline and research rehearsal.

The evidence status must remain bounded accordingly.

The project must not delay all Candidate work until perfect data procurement is complete.

It also must not promote rehearsal results as formal Alpha evidence.

## Exit criteria

```text
Candidate Discovery is an independent subsystem.
It produces explicit CandidatePrediction objects.
It does not emit orders.
It does not depend on running CoscoTimingEngine as the universal cross-sectional scorer.
The full candidate population and predictions can be preserved for evaluation.
The experiment is reproducible.
```

---

# R6 — Generalized Validation System and Formal Candidate Validation

## Objective

Generalize existing strong validation mechanisms and use them to validate Candidate Discovery formally.

## R6.1 Generalize Experiment Identity

Extract the project-wide pattern from MACD-specific implementation.

## R6.2 Generalize immutable run artifacts

Preserve:

- manifest;
- checksums;
- non-overwrite semantics;
- environment identity;
- config identity;
- dataset and split identity.

## R6.3 Generalize sample roles and split manifests

Normalize terminology according to the Data and Validation Constitutions.

Avoid parallel global ontologies.

## R6.4 Candidate validation protocol

Support:

- chronological OOS;
- date-aware panel splits;
- symbol holdout where useful;
- walk-forward;
- overlap-aware purging/embargo where required;
- ranking metrics;
- top-K metrics;
- calibration where probabilities exist;
- robustness;
- baseline comparisons.

## R6.5 Sealed test remains scarce

Do not open a sealed test merely because the Candidate MVP runs.

The promotion candidate must first satisfy the required readiness protocol.

## Exit criteria

```text
Candidate experiments can progress through explicit evidence levels.
Formal OOS evidence is reproducible.
Baseline and model comparisons are immutable.
Candidate promotion decisions can be made without relying only on strategy P&L.
```

---

# R7 — Entry Policy and Strategy Proposal Boundary

## Objective

Convert Candidate opportunity estimates into independently testable Entry decisions.

## Required work

### Candidate-to-Entry contract

Separate:

```text
Opportunity attractiveness
```

from:

```text
Establish exposure now
```

### Entry policy baselines

Possible baselines may include:

- immediate next-eligible entry;
- no-confirmation entry;
- simple price-location filter;
- simple liquidity/execution filter.

### Controlled confirmation research

Research the incremental value of:

- MACD confirmation;
- market context;
- ETF/theme context;
- flow confirmation;
- Chan structure;
- Tuishen-inspired proxies.

No confirmation is privileged by theory alone.

### Canonical StrategyProposal

Introduce one authoritative strategy proposal per decision scope.

## Application migration

`trend_snapshot.py` and similar interfaces should begin consuming:

```text
One Authoritative Strategy Proposal
```

while alternative engines remain:

- shadow;
- diagnostic;
- baseline.

## Exit criteria

```text
Candidate and Entry are independently measurable.
Accepted and rejected Candidate opportunities are preserved.
The application layer no longer requires humans to reconcile two final action authorities for the migrated scope.
```

---

# R8 — Position Lifecycle and Exit Decomposition

## Objective

Extract existing lifecycle knowledge from the integrated Legacy backtest and rebuild it as explicit policies.

## Sequence

Do not migrate all state machines simultaneously.

Prioritize a minimal lifecycle:

```text
HOLD
ADD
REDUCE
EXIT
```

Then add:

```text
ROTATE
```

when comparative opportunity infrastructure is mature.

## R8.1 Position State Contract

Explicitly model, as applicable:

- entry thesis;
- entry time;
- reference price;
- holding age;
- current virtual strategy exposure;
- MFE / MAE;
- prior adds and reductions;
- risk state;
- lifecycle mode.

## R8.2 HOLD policy

Move from:

```text
No exit signal = HOLD
```

to explicit continued-exposure evaluation.

## R8.3 ADD policy

Treat ADD as marginal exposure research, not repeated Entry.

## R8.4 REDUCE policy

Separate risk reduction, profit protection and capital reallocation intents.

## R8.5 Exit policy families

Separate:

- profit taking;
- risk stop;
- thesis invalidation;
- trend invalidation;
- structure break;
- exhaustion/distribution;
- time expiry;
- forced exit.

## Migration source

Extract hypotheses from:

- attack states;
- beta-hold states;
- risk-on add logic;
- trailing-profit logic;
- distribution logic;
- existing stop behavior.

Extraction does not imply automatic promotion.

## Exit criteria

```text
Lifecycle state is explicitly owned.
At least one complete Entry → Hold/Add/Reduce/Exit path is testable outside the Legacy backtest God Object.
Exit is not the inverse of Entry.
Fixed next-morning exit remains a strategy-specific baseline, not project law.
```

---

# R9 — Market Regime, ETF and Theme Integration

## Objective

Integrate context systems after the Candidate and strategy contracts are stable enough to measure their incremental role.

## Why this stage is not earlier on the critical path

Market Regime and ETF/Theme context are strategically important.

However, making them hard prerequisites before a Candidate baseline would:

- delay Candidate research;
- make attribution harder;
- encourage early coupling.

Therefore the project first establishes an unconditional or minimally conditioned Candidate baseline.

Then context must earn incremental authority.

## R9.1 Market Context extraction

Separate from current Market Environment code:

```text
Observed Market Context
```

from:

```text
Model Self-State
Strategy Gate
Portfolio Exposure Cap
```

## R9.2 Market Regime model

Research as a separate object.

Possible roles:

- context;
- interaction term;
- Candidate conditioning;
- strategy gate;
- portfolio risk input.

Each role requires separate attribution.

## R9.3 ETF Rotation

Support two distinct roles:

```text
ETF Context for Stock Candidate Discovery
```

and:

```text
Direct ETF Trading Strategy
```

Do not collapse them.

## R9.4 Theme Rotation

Require PIT-valid membership before formal historical claims.

## Exit criteria

```text
Market, ETF and Theme outputs have explicit roles.
Context-only effects can be distinguished from hard-gate effects.
Candidate performance with and without context is attributable.
Direct ETF strategy research remains independently versioned.
```

---

# R10 — Portfolio and Execution Simulation

## Objective

Move from isolated Strategy Proposals to realistic multi-opportunity capital decisions.

## R10.1 Portfolio System MVP

Own:

- final target exposure;
- aggregate capital allocation;
- concentration;
- sector/theme constraints;
- cross-strategy conflict resolution;
- cash and risk budgets.

## R10.2 Multi-sleeve reconciliation

Support strategy-local virtual exposures such as:

- long-term dividend sleeve;
- active/T overlay;
- cross-sectional trend sleeve.

Reconcile them to physical account exposure.

## R10.3 Execution Simulation

Extract execution semantics from integrated backtests into an explicit owner.

Where relevant:

- next eligible execution;
- T+1 sellability;
- lot size;
- suspension;
- price limits;
- transaction costs;
- slippage;
- fill assumptions.

## R10.4 Shared contracts for simulated and future live execution

Simulation and future broker adapters may share:

- request semantics;
- result semantics;
- rejection reasons.

They should not share the same implementation by necessity.

## Exit criteria

```text
Strategy does not own final account allocation.
Execution constraints are no longer hidden inside strategy logic.
Multiple strategies can propose conflicting actions without last-writer-wins behavior.
```

---

# R11 — Shadow Observation and Application Migration

## Objective

Observe V2 behavior under live-like data without automatic capital authority.

## Work

### Shadow Candidate outputs

Monitor:

- coverage;
- rank distribution;
- top-K stability;
- missing data;
- data latency;
- prediction drift.

### Shadow Strategy outputs

Monitor:

- Entry proposals;
- HOLD / ADD / REDUCE / ROTATE / EXIT distribution;
- rejected proposals;
- risk blocks;
- state transitions.

### Execution feasibility observation

Track:

- blocked actions;
- delayed actions;
- tradability;
- cost assumptions;
- live-like latency.

### Application migration

Move dashboards, snapshots and notifications toward canonical V2 contracts.

Do not redesign all UI before domain semantics stabilize.

## Exit criteria

```text
V2 outputs can be observed without ambiguity.
Shadow models cannot silently affect authoritative Legacy decisions unless promoted.
Operational failures and data drift are measurable.
```

---

# R12 — Selective Legacy Migration, Degradation and Retirement

## Objective

Reduce duplicated authority only after replacement capability exists.

## Retirement rule

A Legacy path may be retired only when:

```text
Replacement Exists
AND
Replacement Behavior Is Characterized
AND
Required Research Evidence Exists
AND
Operational Consumers Have Migrated
AND
Rollback or Historical Reproduction Is Addressed
```

## Possible retirement order

Likely lower-risk retirement targets include:

1. duplicated application-level decision fields;
2. obsolete compatibility wrappers;
3. duplicated feature calculations after registry migration;
4. hard-coded empirical artifacts after externalization;
5. superseded isolated Legacy policy branches.

High-risk core Legacy systems such as the integrated backtest or `CoscoTimingEngine` may remain longer as:

- replay baselines;
- historical research references;
- behavior laboratories.

Retirement is not a measure of architectural success by itself.

Removing useful knowledge too early is failure.

---

# 7. Workstream Dependency Map

The roadmap should be understood as a dependency graph.

```text
                         ┌──────────────────────┐
                         │ R1 Legacy Character. │
                         └──────────┬───────────┘
                                    │
                                    ▼
┌─────────────┐          ┌──────────────────────┐
│ R0 Const.   │─────────▶│ R2 Minimal V2 Kernel │
└─────────────┘          └──────────┬───────────┘
                                    │
                   ┌────────────────┴────────────────┐
                   ▼                                 ▼
          ┌─────────────────┐               ┌─────────────────┐
          │ R3 Data / PIT   │               │ R4 Feature MVP  │
          └────────┬────────┘               └────────┬────────┘
                   └────────────────┬────────────────┘
                                    ▼
                          ┌─────────────────────┐
                          │ R5 Candidate MVP    │
                          └──────────┬──────────┘
                                     ▼
                          ┌─────────────────────┐
                          │ R6 Formal Validation│
                          └──────────┬──────────┘
                                     ▼
                          ┌─────────────────────┐
                          │ R7 Entry Policy     │
                          └──────────┬──────────┘
                                     ▼
                          ┌─────────────────────┐
                          │ R8 Lifecycle / Exit │
                          └──────────┬──────────┘
                                     │
                         ┌───────────┴───────────┐
                         ▼                       ▼
              ┌──────────────────┐    ┌────────────────────┐
              │ R9 Context/ETF   │    │ R10 Portfolio/Exec │
              └─────────┬────────┘    └──────────┬─────────┘
                        └──────────────┬──────────┘
                                       ▼
                            ┌────────────────────┐
                            │ R11 Shadow / Apps  │
                            └──────────┬─────────┘
                                       ▼
                            ┌────────────────────┐
                            │ R12 Legacy Retire  │
                            └────────────────────┘
```

This diagram is directional, not a prohibition against controlled overlap.

---

# 8. What Can Run in Parallel

The project should use parallelism where semantics are stable.

---

## 8.1 Data procurement can begin immediately

Professional data capability research can proceed while:

- the Glossary is completed;
- Legacy characterization is performed;
- V2 contracts are designed.

No formal provider integration should bypass Data Constitution acceptance.

---

## 8.2 Legacy characterization can run throughout early stages

Characterization should continue as migration targets are discovered.

It does not need to finish for the entire repository before any V2 code exists.

---

## 8.3 Candidate rehearsal can begin before full formal data

A clearly classified development or rehearsal dataset can support:

- pipeline construction;
- target design;
- baseline comparison;
- metric design;
- API design.

It cannot support final promotion claims.

---

## 8.4 Market and ETF research can begin as independent research programs

Early exploratory Market Regime and ETF research may proceed.

They should not block the Candidate baseline and should not silently become hard gates.

---

## 8.5 Application maintenance can continue

Existing dashboards and schedulers may continue receiving correctness and maintenance work.

New platform authority should not be added through UI-specific fields.

---

# 9. What Must Not Run in Parallel Without a Contract

Some work creates dangerous semantic races.

---

## 9.1 Two competing platform action vocabularies

Do not independently create multiple V2 action enums.

`09-Glossary.md` and lower-level specifications should establish one canonical vocabulary.

---

## 9.2 Two competing Experiment Identity systems

The MACD-specific implementation should be generalized through one project direction.

Do not build another unrelated Candidate experiment manifest system in parallel.

---

## 9.3 Two competing PIT universe authorities

Exploratory universe builders may coexist.

Formal historical eligibility must have one canonical authority per dataset scope.

---

## 9.4 Strategy and Portfolio both owning final exposure

Exposure proposal and final allocation may be developed in parallel only if their contract boundary is explicit.

---

# 10. Immediate Implementation Sequence After the Constitution

The following is the recommended first implementation sequence after `09-Glossary.md` freezes terminology.

It is intentionally incremental.

---

## Change Set 1 — Repository Authority Alignment

Update high-level project metadata and documentation to acknowledge:

```text
Alpha Research Operating System
```

while clearly preserving Legacy compatibility.

Likely targets include:

- `README.md`;
- `pyproject.toml` description;
- `docs/Project-Structure.md`;
- package-level documentation.

Do not rename Legacy packages in this change set.

---

## Change Set 2 — Legacy Asset and Responsibility Inventory

Create a machine-readable or structured migration inventory.

Record:

- path;
- current responsibility;
- target owner;
- migration action;
- risk;
- tests/characterization status.

---

## Change Set 3 — V2 Core Identity Contracts

Introduce minimal shared identity and time contracts.

No strategy logic.

No feature expansion.

---

## Change Set 4 — Generalized Experiment Identity Adapter

Build a project-wide experiment identity contract using the MACD implementation as the reference pattern.

Keep Legacy MACD APIs working.

---

## Change Set 5 — Data Provider and Dataset Contracts

Define provider/dataset boundaries without rewriting all adapters.

Wrap current adapters where useful.

---

## Change Set 6 — PIT Universe Contract

Create the canonical interface and manifest identity for historical universe membership and eligibility.

Keep the current large-cap snapshot builder explicitly exploratory.

---

## Change Set 7 — Generalized Dataset Manifest and Research Snapshot

Generalize manifest identity from current MACD OOS and formal rehearsal patterns.

Do not open sealed data.

---

## Change Set 8 — Feature Registry MVP

Implement only the fields required by the Factor Constitution and Candidate baseline.

---

## Change Set 9 — Legacy Factor Inventory Tooling

Register or inventory existing factors without automatically promoting them.

---

## Change Set 10 — Candidate Target Contract and Prediction Schema

Define:

- target;
- horizon;
- decision time;
- universe scope;
- CandidatePrediction output.

---

## Change Set 11 — Candidate Dataset Builder

Build a reproducible panel dataset from:

```text
PIT / declared Universe
+
Registered Features
+
Target Contract
```

---

## Change Set 12 — Candidate Baseline Models

Implement simple baselines first.

Preserve full candidate population outputs.

---

## Change Set 13 — Candidate Evaluation and Immutable Run Artifact

Generalize existing validation patterns for cross-sectional Candidate experiments.

---

## Change Set 14 — Candidate Rehearsal Report

Produce a report that explicitly distinguishes:

```text
Fact
Inference
Model Assumption
Research Result
Risk
Invalidation
Next Observation
```

and declares evidence level.

---

## Change Set 15 — Formal Data Upgrade Path

Rebuild the same Candidate experiment on FORMAL_RESEARCH eligible data without changing the research claim silently.

This allows comparison between:

```text
Research Rehearsal
```

and:

```text
Formal Evidence
```

---

# 11. Current Asset Migration Matrix

The following is the current default migration posture.

| Current asset | Current value | Primary risk | Roadmap action | Earliest target stage |
|---|---|---|---|---|
| `data_sources/a_share_bars.py` | broad accessible bar adapters and normalization | access mistaken for PIT authority | Preserve adapters, wrap with Data contracts | R3 |
| `dividend_t/universe.py` | broader large-cap universe construction | explicitly current-snapshot, not historical PIT | Preserve exploratory use, replace formal authority with PIT Universe | R3 |
| `formal_dataset_builder.py` | fail-closed PIT/finalization/sidecar rehearsal | MACD/5-minute/MVP scope can be mistaken for universal scope | Preserve mechanics, generalize | R3/R6 |
| `macd_oos.py` | manifests, split governance, sealed-test gate, immutable artifacts | local ontology and MACD-specific scope | Preserve governance, normalize vocabulary, generalize | R2/R6 |
| `macd_experiments.py` | strong experiment identity and controlled attribution | MACD-specific | Preserve and generalize pattern | R2/R6 |
| `signal_intent.py` | intent, setup, confirmation, risk and trace semantics | Candidate mixed with action-oriented Legacy signals | Preserve principles, adapt contracts | R2/R7 |
| `models.py::Signal` | useful Dividend-T action vocabulary | may become false platform ontology | Preserve Legacy only, map to canonical actions | R7 |
| `DividendTStrategy` | deterministic integrated baseline | Candidate, policy, sizing and order coupling | Freeze expansion, characterize, extract | R1/R7/R8 |
| `CoscoTimingEngine` | dense repository of research hypotheses | integrated responsibilities and non-comparable symbol timing | Freeze platform expansion, selective extraction | R1/R4/R8 |
| `market_environment.py` | useful market breadth/trend/context research | mixes context, model state, strategy gate and position cap | Decompose by owner | R9 |
| `attention.py` | interpretable OHLCV attention proxy | semantic overclaim and overlap | Register as proxy, ablate | R4 |
| `sell_pressure.py` | structured OHLCV sell-pressure proxy | may be mistaken for observed supply | Register as proxy, ablate | R4/R8 |
| `cosco_timing_capital_flow.py` | real/proxy source distinction | one high-level score hides source class | Split formal identities | R4/R9 |
| `tuishen_volume_price.py` | structured volume-price decomposition | shared OHLCV lineage and repeated counting | Register, measure redundancy, ablate | R4/R9 |
| `buy_point_quality.py` | subtype taxonomy and empirical priors | sample-derived priors hard-coded in source | Preserve taxonomy, externalize learned artifacts | R4/R6 |
| `point_hit_rate.py` | useful historical timing diagnostic | heterogeneous intent collapse | Keep Legacy diagnostic only | R6/R8 |
| `backtest.py` | large behavior laboratory and execution knowledge | God Object, hidden state, rule accumulation | Characterize and extract by owner | R1/R8/R10 |
| `trend_snapshot.py` | useful operational research interface | dual action authorities and probability semantics | Preserve UI utility, migrate to one authoritative path | R7/R11 |
| ETF MA crossover prototype | simple end-to-end ETF baseline | synthetic/minimal and not target ETF Rotation system | Preserve as simple baseline, do not overinterpret | R9 |
| web apps / schedulers / notifications | working operational interfaces | application fields may become domain truth | Maintain, migrate after canonical outputs stabilize | R11 |

This matrix is a default roadmap decision.

A specific asset may change status only through explicit architecture or research evidence.

---

# 12. Priority Rules

When two roadmap items compete, use the following priority order.

---

## Priority 1 — Prevent invalid evidence

Fix first when an issue can cause:

- look-ahead;
- PIT failure;
- test leakage;
- identity mismatch;
- semantic corruption;
- silent source substitution.

---

## Priority 2 — Protect accumulated knowledge

Before deleting or rewriting:

- characterize behavior;
- preserve traces;
- preserve reproducibility where possible.

---

## Priority 3 — Unblock Candidate Discovery

Prefer infrastructure that directly enables:

- PIT universe;
- reproducible features;
- target construction;
- cross-sectional evaluation.

---

## Priority 4 — Reduce duplicated authority

Examples:

- two final action fields;
- multiple position owners;
- duplicated experiment identity systems.

---

## Priority 5 — Improve convenience and presentation

UI redesign, cosmetic package movement and large naming cleanups come after semantic and evidence boundaries.

---

# 13. Roadmap Non-Goals

The refoundation does not require:

- rewriting the repository in another language;
- replacing Python;
- microservices;
- a distributed feature store before Candidate research;
- automatic broker trading;
- a single universal machine-learning model;
- eliminating all heuristic research;
- eliminating all Legacy code immediately;
- buying every available data product;
- using Level 2 for every strategy;
- implementing every Constitution concept before any research runs.

---

# 14. Roadmap Anti-Patterns

The following migration patterns are prohibited or must remain explicitly temporary.

---

## 14.1 Big-bang rewrite

```text
Delete Legacy
    ↓
Rebuild everything
```

without behavior preservation.

---

## 14.2 Architecture astronautics

Building broad generic infrastructure without a near-term research consumer.

---

## 14.3 Candidate inside Legacy timing engine

Turning a symbol-specific integrated timing engine into the market-wide Candidate platform by looping it across symbols.

---

## 14.4 Perfect-data paralysis

Refusing to build any research pipeline until every future formal data field is available.

---

## 14.5 Rehearsal evidence inflation

Treating an exploratory or rehearsal pipeline result as formal OOS Alpha evidence.

---

## 14.6 Feature migration by copy

Copying every Legacy score into a new Feature Registry without lineage, redundancy or evidence review.

---

## 14.7 God Object relocation

Moving `backtest.py` logic into one new file and calling it V2 architecture.

---

## 14.8 Package rename as architecture

Renaming `dividend_t` directories without changing ownership or authority boundaries.

---

## 14.9 Dual authority during migration without explicit shadow status

Running old and new models together is allowed.

Presenting both as equally authoritative final actions is not.

---

## 14.10 UI-first semantics

Designing the canonical domain model around existing dashboard fields.

---

## 14.11 Data-vendor-driven architecture

Allowing one provider SDK or product taxonomy to define the platform domain model.

---

## 14.12 Sealed-test pressure

Opening final holdout data merely to demonstrate roadmap progress.

---

## 14.13 Full Legacy migration before first new research value

The project must not require complete refactoring of every historical strategy before Candidate Discovery can run.

---

# 15. Stage Review Questions

Before moving significant authority to the next stage, ask:

## Direction

- Does this work move the project toward an Alpha Research Operating System?
- Is Candidate Discovery still the first strategic research priority?

## Ownership

- Which bounded context owns the new capability?
- Is authority duplicated elsewhere?

## Legacy

- What existing behavior or knowledge is being preserved?
- Is characterization sufficient before extraction?

## Data

- What Data Eligibility class supports the current claim?
- Is PIT authority required now or only before promotion?

## Features

- Are new inputs registered and traceable?
- Are Legacy proxies labeled honestly?

## Research

- What exact hypothesis is being tested?
- What baseline exists?

## Validation

- What evidence level is being claimed?
- Is any test or sealed sample being consumed?

## Strategy

- Is prediction being confused with action?
- Is Strategy taking Portfolio or Execution authority?

## Operations

- Are current working applications being broken unnecessarily?
- Can the migration be rolled back or compared?

---

# 16. Refoundation Milestones

The following milestones define meaningful progress.

---

## M1 — Constitutional Closure

```text
00–09 complete
```

The project has stable governing terminology and direction.

---

## M2 — Legacy Is Characterized

The project can identify major Legacy assets, responsibilities and migration actions.

---

## M3 — V2 Research Kernel Exists

New experiments have stable identity and do not depend on Legacy platform semantics.

---

## M4 — PIT-Capable Data Spine Exists

Formal historical universe and required sidecars can be reproduced for the target research scope.

---

## M5 — Feature Registry Supports Candidate Research

The project can explain where each Candidate input came from and how it was materialized.

---

## M6 — Candidate Discovery MVP Exists

The project can rank a reproducible cross-section for a defined target without using an integrated Legacy timing engine as the universal scorer.

---

## M7 — Candidate Discovery Has Formal OOS Evidence

The project can separate rehearsal success from formal validation authority.

---

## M8 — Strategy Decision Chain Is Explicit

```text
Candidate
→ Entry
→ Lifecycle
→ Exit
→ Portfolio
→ Execution
```

is represented through explicit owners.

---

## M9 — Context Systems Have Attributable Roles

Market Regime, ETF and Theme information can be measured as context, feature, gate or direct strategy without semantic drift.

---

## M10 — Shadow Research Loop Exists

The project can observe live-like behavior and feed evidence back into research without automatic capital deployment.

---

## M11 — Legacy Authority Is Reduced Selectively

Legacy systems remain only where they retain research or compatibility value.

---

# 17. Success Criteria for the Roadmap

The Roadmap is successful when the repository can support the following loop:

```text
Research Question
    ↓
Target Contract
    ↓
PIT-Correct Dataset and Universe
    ↓
Registered Features
    ↓
Candidate / Strategy Research Object
    ↓
Experiment Identity
    ↓
Controlled Validation
    ↓
Immutable Evidence
    ↓
Promotion Decision
    ↓
Shadow Monitoring
    ↓
Degradation / Revision / Retirement
```

without requiring:

- a single God Object;
- one universal strategy;
- one universal score;
- one universal data vendor;
- one universal metric;
- one universal exit rule.

---

# 18. Relationship to `09-Glossary.md`

The final Constitution volume must freeze canonical vocabulary for terms repeatedly used in the roadmap, including:

- Alpha Research Operating System;
- Legacy Research Asset;
- V2 Kernel;
- Observation;
- Feature;
- Factor;
- Candidate Prediction;
- Entry Proposal;
- Strategy Proposal;
- Portfolio Decision;
- Execution Request;
- Execution Result;
- Position Lifecycle;
- Strategy Sleeve;
- Physical Position;
- Data Eligibility;
- Sample Role;
- Evidence Level;
- Authority State;
- PIT;
- Experiment Identity;
- Promotion;
- Degradation;
- Quarantine;
- Retirement.

The Glossary must not invent a new direction.

It must normalize the terminology already established by Volumes `00–08`.

---

# 19. Constitutional Roadmap Commitments

The project commits to the following migration model.

1. **The project will use incremental migration, not a big-bang rewrite.**
2. **Legacy knowledge will be characterized before destructive replacement.**
3. **No new platform-wide responsibility will be added to `CoscoTimingEngine` or the Legacy backtest God Object.**
4. **Candidate Discovery remains the first strategic new research priority.**
5. **Candidate Discovery will be built as an independent cross-sectional prediction system, not as mass repetition of a symbol-specific timing engine.**
6. **The project will not wait for perfect future infrastructure before producing new research value.**
7. **Exploratory and rehearsal research may proceed before formal data readiness, but its authority will remain bounded.**
8. **Formal promotion claims require PIT-correct and eligible data for the declared scope.**
9. **The first V2 platform layer will be a minimal modular monolith and contract kernel, not microservices.**
10. **Existing data adapters will be preserved where useful and separated from formal dataset authority.**
11. **The current snapshot-based large-cap universe will not be treated as historical PIT truth.**
12. **The existing formal rehearsal and MACD OOS governance mechanisms will be generalized rather than discarded.**
13. **The Feature Registry will start small and support Candidate baselines before attempting complete Legacy factor migration.**
14. **Legacy feature ideas will migrate by lineage and evidence, not by score copying.**
15. **A simple Candidate baseline will precede complex Candidate ensembles.**
16. **Candidate, Entry, Lifecycle, Exit, Portfolio and Execution will remain separate decision authorities.**
17. **One authoritative Strategy Proposal path will exist per decision scope; alternatives may remain shadow or diagnostic.**
18. **Market Regime, ETF and Theme systems will not become hard prerequisites for the first Candidate baseline.**
19. **Context systems must earn incremental authority through controlled comparison.**
20. **Lifecycle knowledge inside Legacy backtests will be extracted incrementally and validated by action intent and path-level counterfactuals.**
21. **Portfolio and Execution ownership will be introduced before multiple strategies are allowed to claim the same physical position independently.**
22. **Application interfaces will migrate after domain contracts stabilize; existing dashboards will not define canonical semantics.**
23. **Sealed-test evidence will not be consumed merely to demonstrate implementation progress.**
24. **Negative experiments and failed migrations will remain part of project knowledge.**
25. **Legacy retirement will occur only after replacement capability, evidence and consumer migration exist.**

---

# 20. Closing Declaration

The repository has already accumulated substantial market ideas, implementation effort and research infrastructure.

The refoundation must not confuse maturity with the number of files rewritten.

The correct migration is not:

```text
Old Code
    ↓
New Code
```

It is:

```text
Implicit Responsibility
    ↓
Explicit Ownership

Mutable Result
    ↓
Identified Evidence

Integrated Timing Score
    ↓
Traceable Information and Policy Components

Single-Stock Research Platform
    ↓
Alpha Research Operating System
```

The roadmap must therefore preserve two forms of momentum at the same time:

```text
Engineering Momentum
        +
Research Momentum
```

Engineering without research value becomes architecture theater.

Research without architecture and evidence discipline becomes rule accumulation.

The constitutional roadmap principle is therefore:

> **Build the smallest trustworthy spine that enables the next falsifiable research question, move new authority onto that spine, and retire Legacy responsibility only after its knowledge has been preserved and its replacement has earned evidence.**
