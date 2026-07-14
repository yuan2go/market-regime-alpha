# The Constitution of Market Regime Alpha

# Volume I — Project Vision

> **Document:** `docs/constitution/00-Project-Vision.md`  
> **Status:** Foundational / Normative  
> **Authority:** Highest-level project vision  
> **Applies to:** Research, architecture, data, factors, strategies, validation, engineering, agents, and future production systems  
> **Project:** `market-regime-alpha`  

---

## 0. Preamble

`market-regime-alpha` began as an A-share buy/sell point research project. Its early implementation accumulated practical assets around dividend-stock observation, intraday timing, MACD, moving averages, Chan Theory, Tuishen-inspired volume-price interpretation, backtesting, data adapters, signal validation, dashboards, notification scripts, and A-share execution constraints.

Those assets remain valuable, but they no longer fully describe the project's destination.

The project is now being refounded around a broader and stricter objective:

> **Market Regime Alpha is an Alpha Research Operating System for the China A-share market.**

Its purpose is not to discover one permanent trading rule, not to predict every price movement, and not to automate capital deployment as quickly as possible.

Its purpose is to build a system that can repeatedly:

```text
Observe the market
        ↓
Form hypotheses
        ↓
Construct measurable features
        ↓
Discover candidate opportunities
        ↓
Test entry, holding, reduction, rotation and exit decisions
        ↓
Validate results under point-in-time constraints
        ↓
Measure whether Alpha is real, incremental and durable
        ↓
Promote, monitor, degrade or retire research components
        ↓
Feed evidence back into the next research cycle
```

This document establishes the project's mission, identity, long-term direction, system boundaries and canonical Alpha pipeline.

All lower-level documents, architecture decisions and implementation work must remain consistent with this vision.

---

# 1. Project Mission

## 1.1 Why this project exists

The central problem this project intends to solve is not simply:

> “Which stock will rise tomorrow?”

Nor is it:

> “Which technical indicator has the highest win rate?”

The deeper problem is that market opportunities are conditional, temporary and regime-dependent.

A rule can appear effective in one environment and fail in another. A factor can work before it becomes crowded and decay afterward. A theme can move from ignition to diffusion, acceleration, climax, divergence and retreat. A stock can remain technically strong while its sector loses capital support. A model can produce an attractive backtest because it has unknowingly counted the same price-volume information multiple times or used information that was not available at the historical decision point.

Therefore, the project must not be organized around the assumption that there is one final strategy waiting to be found.

It must be organized around the ability to answer, continuously and with evidence:

1. **What is the current market rewarding?**
2. **Which sources of Alpha are active in the current regime?**
3. **Which candidate securities express those Alpha sources most clearly?**
4. **When should a position be entered, held, added to, reduced, rotated or exited?**
5. **What evidence supports each decision?**
6. **Under what conditions should the conclusion be considered invalid?**
7. **Has the Alpha survived realistic out-of-sample validation?**
8. **Is the Alpha still working, or has it degraded?**

The project mission is therefore:

> **To create a verifiable, reviewable and continuously evolving research operating system that discovers, validates, combines and monitors Alpha for the China A-share market.**

---

## 1.2 The project is research-first

The project places research before strategy deployment and strategy deployment before execution automation.

The intended order is:

```text
Research
    ↓
Validated Strategy Components
    ↓
Portfolio Decisions
    ↓
Execution
```

Not:

```text
Execution
    ↓
Rules added after losses
    ↓
More rules added after new losses
    ↓
An increasingly opaque strategy
```

A system that can place orders but cannot explain the source of its expected return is not the target architecture.

A system that generates many indicators but cannot measure their incremental contribution is not the target research process.

A model that reports a probability without calibration is not treated as a probability model merely because its score lies between 0 and 100.

A strategy that appears profitable only on the same data used to design it is not considered validated.

Research quality is the foundation on which later trading capability may be built.

---

# 2. Project Positioning

## 2.1 Canonical definition

The canonical project definition is:

> **Market Regime Alpha is an Alpha Research Operating System for the China A-share market.**

Chinese interpretation:

> **Market Regime Alpha 是一个面向 A 股市场、用于持续发现、验证、组合、监控和演化 Alpha 的研究操作系统。**

The phrase **Research Operating System** is intentional.

The project is not intended to be a single model. It is the environment in which multiple research ideas, data sources, feature families, candidate models, entry models, position-management rules, exit models, portfolio policies and validation methods can coexist under common contracts and governance.

---

## 2.2 What the project is not

`market-regime-alpha` is not defined as any one of the following:

- a dividend-stock trading system;
- a COSCO Shipping single-stock timing tool;
- a MACD strategy;
- a Chan Theory implementation;
- a Tuishen Theory implementation;
- an ETF moving-average strategy;
- an overnight gap strategy;
- a next-morning exit strategy;
- a multi-factor stock screener;
- a market dashboard;
- a QMT/PTrade automation script;
- a large language model that directly decides buy and sell orders;
- a collection of unrelated trading rules.

These may exist as strategies, research assets, adapters, experiments or user interfaces inside the larger system.

None of them defines the whole project.

---

## 2.3 Current implementation versus constitutional direction

The repository's current implementation still contains historical naming and architecture from earlier stages, including `dividend_t`, single-symbol timing logic, buy/sell point models, large backtesting modules, dashboards and legacy research paths.

This is expected during refoundation.

The Constitution distinguishes two concepts:

### Current implementation state

What the repository can do today.

### Constitutional target state

What the project is becoming and what future work must align toward.

The existence of legacy code does not redefine the project vision.

The Constitution is the authoritative destination. Legacy systems are research assets to be preserved, adapted, migrated, validated or retired according to evidence.

The project therefore adopts the following transition posture:

```text
Preserve useful research assets
        ↓
Freeze uncontrolled expansion of legacy God Objects
        ↓
Define new contracts and system boundaries
        ↓
Adapt legacy capabilities into the new architecture
        ↓
Build new strategies only on the new research foundation
        ↓
Retire duplicate or invalid paths when evidence allows
```

This is an evolutionary refoundation, not a blind rewrite.

---

# 3. The Core Research Problem

## 3.1 The project does not assume stationary markets

The system assumes that Alpha is conditional.

The effectiveness of a signal may depend on:

- market trend and breadth;
- volatility regime;
- liquidity conditions;
- risk appetite;
- policy and event context;
- sector and theme leadership;
- ETF and index relative strength;
- capital concentration;
- crowding and exhaustion;
- the stage of a market narrative;
- the security's own price-volume and structural state.

Therefore, the project name **Market Regime Alpha** reflects a fundamental design belief:

> **Alpha should be evaluated in the context of the market regime in which it is expected to work.**

The system should not ask only:

> “Does factor X work?”

It should also ask:

> “In which regimes does factor X work, how much independent information does it add, when does it fail, and how quickly does its effectiveness decay?”

---

## 3.2 Alpha is a research claim, not a label

Within this project, an idea is not Alpha merely because it has a plausible narrative.

Examples of plausible narratives include:

- volume expansion indicates capital participation;
- a Chan second-buy structure indicates favorable structure;
- a Tuishen-inspired force ratio indicates ignition;
- an ETF with rising turnover indicates sector strength;
- a leader with strong relative strength may continue to attract capital;
- a stock closing near the intraday high may have next-day continuation potential.

These are hypotheses.

They become usable Alpha only after the project can establish, under a defined target, dataset, market universe and validation protocol, that the information provides measurable and sufficiently robust incremental value.

The project therefore separates:

```text
Theory
    ↓
Hypothesis
    ↓
Feature
    ↓
Signal
    ↓
Model contribution
    ↓
Validated Alpha
```

No conceptual framework receives automatic authority because of reputation, popularity or intuitive appeal.

MACD, moving averages, Chan Theory, Tuishen-inspired constructs, capital-flow features, theme heat, ETF rotation, fundamentals and machine-learning features must all pass through the same evidence framework.

---

# 4. Strategic Goals

The project has three canonical strategic goals.

They are related but must not be collapsed into one monolithic model.

---

## 4.1 Goal A — Candidate Discovery

### Definition

Candidate Discovery is the project's first current priority.

Its purpose is:

> **At a defined decision time, rank the tradable A-share universe and identify securities with the most attractive forward opportunity profiles under the current market regime.**

Candidate Discovery is not identical to “predict tomorrow's close.”

The system may care about multiple forward outcomes, including:

- probability of positive return;
- probability of a meaningful upward excursion;
- expected maximum favorable excursion;
- expected maximum adverse excursion;
- probability of breakout continuation;
- probability that a setup remains valid over several sessions;
- expected holding horizon;
- downside asymmetry;
- execution feasibility;
- opportunity quality relative to other candidates.

The target horizon may differ by strategy family.

The key constitutional requirement is that the prediction target must be explicit and measurable.

---

### Candidate Discovery is cross-sectional

The legacy system often evaluates one symbol through a time-series decision engine.

Candidate Discovery asks a different question:

```text
Given all securities that were actually tradable at time T,
which securities ranked highest for the defined opportunity at time T?
```

This requires the system to reason across the market, not only within one stock.

Candidate Discovery therefore depends on capabilities such as:

- point-in-time tradable universe construction;
- liquidity and eligibility filters;
- cross-sectional normalization;
- sector and theme context;
- relative strength;
- candidate ranking;
- concentration control;
- explicit rejection reasons;
- comparable scoring across securities.

The output is a candidate set, not an automatic order list.

---

### Candidate Discovery output philosophy

A candidate should not be represented only as:

```text
BUY
```

The intended output is richer:

```text
Candidate
├── what opportunity is being predicted
├── expected upside
├── expected downside
├── expected holding horizon
├── confidence or calibrated probability
├── supporting feature families
├── market / ETF / theme context
├── setup classification
├── invalidation conditions
├── data quality status
└── traceable rejection or promotion reasons
```

The system should prefer a smaller number of well-defined predictions over a large number of ambiguous signals.

---

## 4.2 Goal B — Position Lifecycle Management

### The project rejects fixed exit assumptions

An earlier formulation focused on:

```text
Buy near the close of day T
        ↓
Sell during the morning of T+1
```

That formulation may remain a valid strategy hypothesis for a specific overnight model, but it is not the constitutional definition of position management.

The project adopts the broader principle:

> **A position exits when its exit logic, risk logic, opportunity-cost logic or invalidation logic requires exit—not merely because a fixed clock time has arrived.**

Time-based exits may exist, but they are one exit mechanism among several.

---

### Canonical position lifecycle

The canonical position lifecycle is:

```text
ENTRY
  ↓
HOLD
  ↓
ADD
  ↓
REDUCE
  ↓
ROTATE
  ↓
EXIT
```

Not every position must pass through every state.

The purpose of the lifecycle model is to separate distinct decisions that were previously at risk of being mixed together.

For example:

- an entry model evaluates whether a new position should be initiated;
- a hold model evaluates whether the original thesis still has sufficient expected value;
- an add decision requires stronger evidence than merely remaining in the position;
- a reduce decision may respond to risk concentration or weakening continuation probability;
- a rotate decision compares the existing opportunity with superior alternatives;
- an exit decision terminates the position because the opportunity, structure or risk budget has changed.

These decisions must not be represented by one overloaded `signal` field.

---

### Position management is a repeated re-evaluation problem

The project does not assume that the best forecast is made once and then left unchanged.

A position should be re-evaluated as new information becomes available.

Depending on the strategy and data frequency, this may include changes in:

- market regime;
- ETF and sector leadership;
- theme stage;
- relative strength;
- breadth and leader resonance;
- capital-flow evidence;
- volatility;
- price-volume behavior;
- structure and invalidation levels;
- expected remaining return;
- expected downside;
- opportunity cost;
- portfolio concentration.

This means the project treats position management as a stateful but traceable decision process.

State must not become hidden logic.

Each state transition must have an explicit reason, input context and decision trace.

---

## 4.3 Goal C — ETF and Theme Rotation

ETF Rotation is important, but its initial constitutional role is broader than simply trading ETFs.

Its first role is to help answer:

> **Where is the market's relative strength and capital attention currently concentrating?**

The intended upstream flow is:

```text
Market Regime
        ↓
ETF Strength / Weakness
        ↓
Theme and Industry Rotation
        ↓
Breadth and Leader Resonance
        ↓
Candidate Universe Narrowing
        ↓
Individual Stock Candidate Discovery
```

ETF and theme models may later support direct ETF trading strategies.

However, the architecture must not force ETF Rotation to be only a trading endpoint.

It is also a market-context and universe-selection capability.

---

# 5. The Canonical Alpha Pipeline

The project is organized around one canonical high-level pipeline:

```text
Market Regime
        ↓
ETF Rotation
        ↓
Theme Rotation
        ↓
Tradable Universe
        ↓
Feature Pipeline
        ↓
Candidate Discovery
        ↓
Entry Model
        ↓
Position Lifecycle
        ↓
Exit Model
        ↓
Portfolio Construction
        ↓
Execution Simulation
        ↓
Research Feedback
```

This pipeline is the conceptual backbone of the project.

A concrete strategy may bypass some optional branches, but any exception must be explicit.

---

## 5.1 Market Regime

The Market Regime layer describes the environment in which strategy evidence should be interpreted.

It may eventually represent dimensions such as:

- trend;
- breadth;
- liquidity;
- volatility;
- risk appetite;
- market concentration;
- style leadership;
- event and policy context.

The constitutional role of this layer is not to produce an omniscient “bull” or “bear” label.

Its role is to provide context for conditional Alpha evaluation.

---

## 5.2 ETF Rotation

The ETF Rotation layer measures relative strength, participation, flow, persistence and possible rotation among broad-market, industry, sector and thematic exposures.

Its output may influence:

- which areas receive research attention;
- which candidate universes are expanded or contracted;
- how theme persistence is interpreted;
- portfolio concentration limits;
- direct ETF strategies in later stages.

---

## 5.3 Theme Rotation

The Theme Rotation layer represents narrative and participation dynamics that may not map cleanly to a single industry classification.

A theme may pass through stages such as:

```text
Ignition
    ↓
Diffusion
    ↓
Acceleration
    ↓
Climax
    ↓
Divergence
    ↓
Retreat
```

These are research states, not immutable truths.

Their definitions must later be formalized and validated.

---

## 5.4 Tradable Universe

The project must reason about the set of securities that were actually eligible and tradable at the historical decision time.

A research system that selects from today's surviving stock list while testing the past is not acceptable.

The Tradable Universe layer is therefore foundational to credible cross-sectional research.

It provides the eligible search space before candidate ranking begins.

---

## 5.5 Feature Pipeline

The Feature Pipeline transforms point-in-time data into registered research features.

Its constitutional role is to make information explicit and traceable.

A feature should eventually be able to answer:

- what information family it belongs to;
- what source fields it uses;
- what lookback it requires;
- when the information became available;
- how it is normalized;
- how it is versioned;
- whether it overlaps strongly with other features.

Detailed requirements belong to the Factor and Data Constitutions.

---

## 5.6 Candidate Discovery

The Candidate Discovery layer ranks opportunities for a defined target and horizon.

It does not own portfolio weights and does not directly simulate execution.

Its job is to answer:

> “Which eligible securities best express the target opportunity under the current information set?”

---

## 5.7 Entry Model

The Entry Model decides whether and when a candidate becomes actionable.

A high-ranked candidate is not automatically a valid entry.

Entry may depend on:

- setup quality;
- execution feasibility;
- timing;
- invalidation distance;
- reward-to-risk;
- current portfolio exposure;
- data freshness;
- strategy-specific gates.

The Entry Model must not own the entire future position lifecycle.

---

## 5.8 Position Lifecycle

The Position Lifecycle layer manages state transitions after entry.

It is responsible for the distinction between:

```text
Hold
Add
Reduce
Rotate
Exit
```

Its decisions must be traceable and should be driven by updated evidence, risk and opportunity cost.

---

## 5.9 Exit Model

The Exit Model is an independent research object.

It is not defined as “entry logic reversed.”

It may study different objectives, including:

- trend continuation failure;
- structural invalidation;
- exhaustion;
- distribution;
- adverse risk expansion;
- loss of theme or ETF support;
- better alternative opportunities;
- stop loss;
- take profit;
- time decay of a specific setup.

Different exit intents require different evaluation metrics.

A profit-taking exit and a risk-stop exit are not the same research problem.

---

## 5.10 Portfolio Construction

The Portfolio Construction layer converts candidate and position-level decisions into a coherent portfolio.

Its role includes resolving conflicts that cannot be solved by single-stock models, such as:

- capital limits;
- sector concentration;
- theme concentration;
- correlation exposure;
- turnover;
- liquidity;
- risk budget;
- competing opportunities.

No single strategy component should directly bypass portfolio constraints to create an order.

---

## 5.11 Execution Simulation

Execution Simulation models the realities that separate theoretical signals from tradable results.

For A-shares, the system must ultimately respect constraints such as:

- T+1;
- trading sessions;
- suspension;
- price limits;
- unavailable fills;
- fees and taxes;
- slippage;
- liquidity;
- timestamp and data finalization.

A strategy is not validated if its return depends on fills that could not have occurred.

---

## 5.12 Research Feedback

Research Feedback closes the loop.

The system should not end with a backtest report.

It should feed evidence back into the research process:

```text
What worked?
What failed?
Which regime mattered?
Which feature added independent value?
Which feature was redundant?
Which decision caused drawdown?
Which assumption was invalid?
Has the Alpha degraded?
Should the component be promoted, modified, quarantined or retired?
```

This feedback loop is what turns a collection of strategies into a research operating system.

---

# 6. Research Before Production

## 6.1 Canonical research lifecycle

The project adopts the following high-level lifecycle:

```text
Idea
  ↓
Hypothesis
  ↓
Data Qualification
  ↓
Feature / Signal Definition
  ↓
Baseline
  ↓
Backtest
  ↓
Walk Forward
  ↓
Out-of-Sample Validation
  ↓
Calibration and Risk Review
  ↓
Promotion Decision
  ↓
Paper / Shadow Observation
  ↓
Production Eligibility
  ↓
Monitoring
  ↓
Degradation / Retirement
```

The detailed gates are defined in later Constitution volumes.

The vision-level rule is simple:

> **Nothing becomes production-authoritative merely because it is implemented.**

Implementation status and research validity are different concepts.

---

## 6.2 Rules are baselines, not exemptions from evidence

Rule-based systems remain valuable.

They are useful for:

- expressing hypotheses clearly;
- creating interpretable baselines;
- establishing deterministic controls;
- encoding execution constraints;
- providing risk gates.

However, a rule does not avoid validation because it is interpretable.

A complex machine-learning model and a handcrafted score must both be tested against explicit targets and realistic data.

---

## 6.3 Machine learning is a tool, not the project identity

The project may use:

- linear models;
- logistic regression;
- tree models;
- ranking models;
- probability calibration;
- time-series models;
- deep learning;
- agent-assisted research.

But the project is not defined by any model family.

The preferred model is the one that provides the best evidence-adjusted value under the target problem, data quality, interpretability needs, computational cost and robustness requirements.

The project explicitly rejects premature complexity.

A stronger baseline is more valuable than a sophisticated model that cannot be trusted.

---

# 7. The Role of Existing Trading Theories and Factor Families

The project intentionally supports multiple schools of market analysis.

These include, among others:

- momentum;
- trend;
- moving averages;
- MACD;
- volatility;
- liquidity;
- price-volume structure;
- capital flow;
- market breadth;
- ETF strength;
- theme heat;
- fundamentals;
- valuation;
- events;
- Chan Theory;
- Tuishen-inspired constructs.

Their constitutional role is not to compete for ideological dominance.

They are research hypotheses and feature families.

Each must be translated into measurable definitions and tested for:

- data availability;
- point-in-time correctness;
- stability;
- correlation with other features;
- incremental contribution;
- regime dependence;
- failure modes;
- practical tradability.

The project therefore converts qualitative theories into quantitative research objects.

For example, concepts such as “leader ignition,” “exhaustion,” “divergence,” “second buy,” “capital entering,” or “theme retreat” must eventually be represented by explicit definitions, data sources, thresholds or models, evaluation targets, and invalidation conditions.

The theory may inspire the hypothesis.

Evidence determines whether the hypothesis survives.

---

# 8. The Role of Data

## 8.1 Data is part of the model

The project treats data quality as part of strategy validity.

A model is not separable from:

- its source data;
- availability timestamps;
- adjustment methodology;
- universe history;
- field semantics;
- data revisions;
- missing-data policy;
- provider licensing and provenance.

A profitable backtest built on invalid historical availability assumptions is not a valid Alpha result.

---

## 8.2 Professional data is a research foundation, not a cosmetic upgrade

The project currently uses or has explored several free and semi-formal market data sources for development and research convenience.

These sources can remain useful for:

- prototyping;
- interface development;
- smoke testing;
- exploratory research;
- non-authoritative dashboards.

However, the project recognizes that formal validation of advanced strategies requires stronger guarantees around capabilities such as:

- historical minute bars;
- finalized-bar semantics;
- point-in-time adjustment;
- historical tradable universe;
- historical ST and suspension status;
- price-limit eligibility;
- historical industry and theme mappings;
- ETF shares and fund-flow-related fields;
- Level 2 and microstructure data where required;
- data provenance and reproducibility.

Professional data therefore supports research credibility, not merely signal precision.

The project will evaluate providers such as Xuntou and other qualified sources according to capability, correctness, cost, authorization and reproducibility.

QMT/PTrade execution integration is not required before the research platform becomes valid.

---

# 9. Legacy Assets and Refoundation

## 9.1 Legacy does not mean worthless

The existing project contains substantial research assets.

Examples include:

- A-share trading constraints;
- T+1 handling;
- price-limit logic;
- suspension handling;
- transaction cost assumptions;
- backtesting experience;
- MACD and trend logic;
- Chan-related structure research;
- Tuishen-inspired volume-price research;
- signal intent concepts;
- candidate and timing traces;
- data adapters;
- dataset-building work;
- out-of-sample and sealed-test discipline;
- counterfactual research;
- sell-point lifecycle experiments;
- dashboards and observation workflows.

These should be classified, tested and migrated where useful.

---

## 9.2 What must not continue

Refoundation exists because several patterns are no longer sustainable.

The project must stop treating the following as acceptable long-term architecture:

- continuously adding configuration fields to a single backtest God Object;
- continuously adding indicators to one monolithic timing engine;
- placing unrelated future strategies under `dividend_t` because the package already exists;
- allowing multiple signal fields to compete as if each were the final decision;
- mixing technical price behavior into a “fundamental” score;
- calling a handcrafted normalized score a calibrated probability;
- calculating priors on a sample and then presenting evaluation on the same sample as independent evidence;
- evaluating different exit intents with one universal hit-rate definition;
- repeatedly weighting multiple transformations of the same OHLCV information without lineage or redundancy analysis.

These are not merely code-style concerns.

They directly affect research validity.

---

## 9.3 Refoundation strategy

The project will use gradual migration rather than a destructive rewrite.

The intended pattern is:

```text
Legacy system remains observable and testable
        ↓
New constitutional contracts are introduced
        ↓
Legacy capabilities are wrapped or adapted
        ↓
New research is built on the new architecture
        ↓
Behavior is compared and validated
        ↓
Duplicate paths are retired intentionally
```

The project values continuity, characterization tests and reversible migration.

Large-scale file movement without clarified ownership is not considered architectural progress.

---

# 10. System Boundaries

## 10.1 Current priority scope

The current priority scope is:

1. establish the Project Constitution;
2. define a coherent architecture for the Alpha Research Operating System;
3. establish trustworthy data and point-in-time research foundations;
4. build Candidate Discovery as the first major V2 research capability;
5. establish Position Lifecycle and independent Exit research;
6. use ETF and theme rotation as upstream context and candidate-universe support;
7. validate Chan, Tuishen-inspired, volume-price, MACD, flow and other feature families through incremental evidence;
8. build portfolio and execution capabilities after the research contracts are sufficiently stable.

---

## 10.2 Explicit non-goals for the current stage

The current stage does not prioritize:

- high-frequency trading;
- ultra-low-latency execution;
- automatic live capital deployment;
- reinforcement learning as the default solution;
- large language models directly issuing authoritative trade orders;
- strategy complexity for its own sake;
- maximizing the number of indicators;
- claiming stable profitability before formal validation;
- promising deterministic returns;
- replacing missing data with untraceable assumptions.

These may be reconsidered in future stages, but they must not distract from the current research foundation.

---

## 10.3 Human authority and automation

The project may increasingly automate:

- data ingestion;
- feature generation;
- experiment execution;
- reporting;
- monitoring;
- regression detection;
- research suggestion;
- documentation;
- paper or shadow observation.

Automation does not remove governance.

Before production trading is explicitly authorized, the system remains a research and decision-support platform.

AI agents may assist with research, coding, review and experiment orchestration, but they do not obtain implicit authority to override research gates or capital controls.

---

# 11. Success Criteria

The project is successful not when it has the most rules, but when it can answer difficult questions reliably.

A mature version of `market-regime-alpha` should be able to answer:

### Market

- What regime is the market currently in?
- Which dimensions support that classification?
- How uncertain is the classification?

### Rotation

- Which ETFs, sectors and themes are strengthening?
- Is the strength broad, concentrated, early, mature or exhausted?

### Candidates

- Which securities are the strongest candidates for a defined forward target?
- Why were they selected?
- Why were similar securities rejected?

### Position lifecycle

- Why is an existing position held, added, reduced, rotated or exited?
- Which conditions would invalidate the current decision?

### Alpha quality

- Which feature families contribute independent value?
- Which are redundant transformations of the same information?
- In which regimes does the Alpha work or fail?

### Validation

- Was the result point-in-time correct?
- Was the test out of sample?
- Was the probability calibrated?
- Were realistic execution constraints applied?

### Evolution

- Is the Alpha degrading?
- What changed?
- Should it be retrained, reweighted, quarantined or retired?

The system's quality is measured by the reliability of these answers.

---

# 12. Long-Term Vision

The long-term destination is a self-improving research environment, not an ungoverned self-trading machine.

A mature system should be able to operate a loop such as:

```text
Ingest qualified market data
        ↓
Detect changes in market regime and rotation
        ↓
Evaluate known Alpha components
        ↓
Generate candidate rankings
        ↓
Manage active position hypotheses
        ↓
Run continuous research and monitoring
        ↓
Detect degradation and anomalies
        ↓
Propose new hypotheses or feature revisions
        ↓
Run reproducible experiments
        ↓
Produce evidence for human or governed promotion decisions
```

The ultimate objective is not to freeze one final strategy.

It is to create an institutional-quality process for continually improving how A-share opportunities are researched.

---

# 13. Constitutional Commitments

This Vision commits the project to the following direction:

1. **The project is an Alpha Research Operating System, not a single strategy.**
2. **Candidate Discovery is the current first strategic priority.**
3. **Position management is a lifecycle, not a fixed next-morning exit rule.**
4. **Entry and Exit are independent research problems.**
5. **ETF and Theme Rotation are both context and potential strategy capabilities.**
6. **Market Regime provides conditional context for Alpha evaluation.**
7. **Qualitative trading theories must be converted into measurable research objects.**
8. **Data validity is part of model validity.**
9. **Research evidence precedes production authority.**
10. **Legacy assets are preserved and migrated intentionally, not allowed to define future architecture by inertia.**
11. **The system must become more traceable as it becomes more sophisticated.**
12. **The project does not promise deterministic returns.**

---

# 14. Authority of This Document

This document is the highest-level vision document in the `market-regime-alpha` documentation hierarchy.

The hierarchy is:

```text
Constitution
      ↓
Architecture
      ↓
Research / Design
      ↓
Specification
      ↓
Implementation
      ↓
Experimental Evidence
```

Lower-level documents may refine this vision.

They may not silently contradict it.

The remaining Constitution volumes define the rules required to make this vision operational:

```text
docs/constitution/
├── 00-Project-Vision.md
├── 01-Core-Principles.md
├── 02-Architecture-Blueprint.md
├── 03-Research-Framework.md
├── 04-Data-Constitution.md
├── 05-Factor-Constitution.md
├── 06-Strategy-Constitution.md
├── 07-Validation-Constitution.md
├── 08-Roadmap.md
└── 09-Glossary.md
```

The supporting documentation hierarchy is:

```text
docs/
├── constitution/   # Highest-level normative rules
├── architecture/   # Concrete architecture and migration documents
├── research/       # Research methods, experiments and evidence
├── designs/        # Subsystem and feature designs
└── specs/          # Implementable contracts and specifications
```

---

# 15. Closing Declaration

`market-regime-alpha` will not be judged by how many indicators it contains.

It will be judged by whether it can distinguish evidence from intuition, independent Alpha from duplicated information, research results from production claims, and valid opportunity from historical overfitting.

The project will not search for certainty where markets do not provide it.

It will instead build a disciplined process for managing uncertainty.

Its long-term purpose is therefore summarized as follows:

> **Observe the regime. Discover the opportunity. Validate the Alpha. Manage the lifecycle. Learn from the evidence. Repeat.**

That is the constitutional vision of Market Regime Alpha.
