# The Constitution of Market Regime Alpha

# Volume II — Core Principles

> **Document:** `docs/constitution/01-Core-Principles.md`  
> **Status:** Foundational / Normative  
> **Authority:** Project-wide governing principles  
> **Applies to:** Research, data, factors, strategies, validation, architecture, implementation, agents, reviews, migration, and future production systems  
> **Project:** `market-regime-alpha`  

---

## 0. Purpose

`00-Project-Vision.md` defines what `market-regime-alpha` is trying to become.

This document defines the rules the project must not silently violate while moving toward that vision.

These principles exist because the largest risk in an evolving quantitative research system is not a single bad indicator or a single bad trade. The larger risk is loss of epistemic control: duplicated information being mistaken for independent evidence, sample leakage being mistaken for predictive power, conflicting signal semantics being mistaken for flexibility, and implementation complexity being mistaken for research sophistication.

The purpose of this Constitution volume is therefore to establish a common standard for answering questions such as:

- Can this result be trusted?
- Can this decision be reproduced?
- Can this feature be traced to its source information?
- Is this signal meaning stable across the system?
- Is this model truly adding information?
- Was this experiment evaluated on data that was available at the decision time?
- Can this component be safely promoted?
- Can this architecture evolve without accumulating another God Object?

The project adopts the following position:

> **A quantitative research system becomes stronger only when increased sophistication is accompanied by increased traceability, evidence quality and semantic discipline.**

---

# 1. Constitutional Precedence

The documentation authority hierarchy is:

```text
00-Project-Vision.md
        ↓
01-Core-Principles.md
        ↓
Remaining Constitution volumes
        ↓
Architecture documents
        ↓
Research / design documents
        ↓
Specifications
        ↓
Implementation
        ↓
Experimental evidence and reports
```

No lower-level artifact may silently redefine a higher-level principle.

If implementation conflicts with this Constitution, the conflict must be made explicit and resolved. Existing legacy behavior is not automatically authoritative merely because it already exists.

---

# 2. Principle 1 — Research Before Production

No component becomes production-authoritative merely because it is implemented, tested for syntax, or appears profitable in one backtest.

The project distinguishes at least the following states:

```text
Idea
Hypothesis
Prototype
Research Candidate
Validated Research Component
Paper / Shadow Candidate
Production Eligible
Production Active
Degraded
Quarantined
Retired
```

These states must not be collapsed into a single boolean such as `enabled=true`.

A component may be technically complete while still being scientifically unvalidated.

A component may be statistically promising while still being operationally unsuitable.

A component may have passed historical validation while later becoming degraded.

Therefore:

> **Implementation readiness, research validity and production eligibility are separate dimensions.**

### Required implication

Every strategy, feature family, model or decision policy intended for formal use must have a defined research status and promotion path.

### Forbidden pattern

```text
Implement rule
    ↓
Backtest once
    ↓
Call it production
```

---

# 3. Principle 2 — Evidence Before Opinion

Market narratives, expert experience, technical theories and intuitive reasoning are permitted as sources of hypotheses.

They are not substitutes for evidence.

The project may begin with claims such as:

- a theme is entering an ignition stage;
- a leader is attracting capital;
- a Chan structure indicates a second-buy opportunity;
- a Tuishen-inspired force ratio indicates strengthening participation;
- an ETF is receiving persistent inflow;
- a breakout has higher continuation probability.

But the project must convert each claim into a testable research object.

At minimum, a serious research claim must eventually define:

```text
Target
Data
Population
Decision time
Feature or rule definition
Expected direction
Evaluation metric
Risk assumptions
Failure conditions
Validation protocol
```

### Required implication

The stronger the claim, the stronger the evidence required.

### Forbidden pattern

```text
“This looks right on the chart”
        ↓
Treat as verified Alpha
```

---

# 4. Principle 3 — Single Source of Truth

Each important business concept must have one authoritative semantic definition.

Examples include:

- market regime;
- candidate score;
- entry intent;
- position action;
- exit intent;
- portfolio decision;
- calibrated probability;
- expected return;
- tradable universe;
- feature identity;
- experiment identity.

The project must not allow multiple fields or engines to represent the same concept with incompatible meanings.

A historical example of semantic drift is the coexistence of concepts such as:

```text
signal = HOLD

timing_action = BUY_T_TIMING
```

Such a combination may be explainable if the fields intentionally represent different layers, but it is unacceptable if both are presented as the final action.

### Required implication

Every decision layer must have a clearly defined owner.

A lower layer may contribute evidence. It must not silently compete with the authoritative decision layer.

### Forbidden pattern

```text
Several engines each emit a “final” action
        ↓
UI chooses whichever is convenient
```

---

# 5. Principle 4 — Semantic Stability

A field, signal, action or metric must keep the same meaning across research, backtest, API, dashboard and production contexts.

The same name must not represent different targets in different modules.

For example:

- `probability` must not mean a heuristic score in one module and a calibrated probability in another;
- `sell` must not simultaneously mean profit-taking, stop-loss, stop doing T, full liquidation and rotation without explicit intent;
- `fundamental_score` must not contain price trend information unless its name and definition explicitly say so;
- `candidate_score` must not silently change target horizon between experiments.

### Required implication

Semantic changes require versioning or explicit migration.

### Forbidden pattern

```text
Same field name
+ different definition
+ no version change
```

---

# 6. Principle 5 — Point-in-Time Discipline

All historical research must respect what was actually knowable at the historical decision time.

This applies not only to price bars, but also to:

- adjustment factors;
- index membership;
- tradable universe;
- ST status;
- suspension status;
- listing age;
- industry membership;
- theme mapping;
- ETF shares;
- financial statements;
- announcements;
- analyst or event data;
- data revisions;
- bar finalization.

The constitutional test is:

> **Could the system, at historical time T, have possessed this exact information in the form used by the model?**

If the answer is unknown, the experiment cannot be treated as formally point-in-time correct.

### Required implication

Availability time is part of data semantics.

### Forbidden patterns

```text
Use today's constituent list to test the past
Use revised data as if it were known earlier
Use an unfinished bar as a finalized bar
Use future-adjusted information without PIT controls
```

---

# 7. Principle 6 — Feature Lineage Is Mandatory

Every formal feature must be traceable to its source information.

At minimum, the project must eventually be able to identify:

```text
Feature name
Feature family
Source fields
Source dataset
Lookback
Frequency
Availability time
Transformation
Normalization
Version
Expected direction
```

Feature lineage exists to answer a critical question:

> **What information is this feature actually adding?**

Without lineage, several differently named features can repeatedly encode the same OHLCV behavior and create the illusion of confirmation.

### Required implication

Lineage is not optional documentation added after research. It is part of feature identity.

### Forbidden pattern

```text
Feature has a descriptive name
but no one can identify its source information
```

---

# 8. Principle 7 — No Double Counting Without Evidence

The project must not repeatedly weight multiple transformations of the same underlying information and call the result a diversified multi-factor model.

Examples of potentially overlapping OHLCV-derived information include:

- trend;
- momentum;
- moving-average position;
- MACD;
- breakout status;
- attention proxies;
- certainty scores;
- price-volume structure;
- sell-pressure proxies;
- capital-flow proxies derived only from bars;
- Chan structures derived from price;
- Tuishen-inspired measures derived from price and volume.

These may all be useful.

But usefulness does not imply independence.

### Required implication

The project must measure redundancy and incremental value through methods appropriate to the research problem, including where relevant:

- Pearson correlation;
- Spearman correlation;
- feature clustering;
- VIF or equivalent collinearity diagnostics;
- IC / RankIC;
- incremental IC;
- ablation;
- permutation importance;
- model contribution analysis;
- stability across regimes.

### Forbidden pattern

```text
Five indicators agree
therefore confidence is five times stronger
```

---

# 9. Principle 8 — Information Families Must Remain Conceptually Clean

The project distinguishes different information families because their economic meaning matters.

Examples include:

```text
Market
ETF / Theme
Price / Momentum
Volume / Liquidity
Capital Flow
Microstructure
Fundamental
Valuation
Event / Policy
Structure
Risk
```

A feature may combine several families if explicitly designed to do so, but hidden contamination is prohibited.

A historical anti-pattern is using price-versus-moving-average behavior to dynamically alter a field named `fundamental_score`.

That creates both semantic pollution and duplicate weighting.

### Required implication

A model may combine families.

A feature definition must not mislabel one family as another.

---

# 10. Principle 9 — Probability Must Mean Probability

A score between 0 and 100 is not automatically a probability.

The project distinguishes:

```text
Raw score
Normalized score
Rank score
Model output
Estimated probability
Calibrated probability
```

A quantity may be called a probability only when its interpretation is supported by an explicit target and calibration evidence.

For example, a claim such as:

```text
P(hit +1% before stop within next 3 sessions) = 0.68
```

has a defined event.

A claim such as:

```text
上涨概率 = 68%
```

without target horizon, event definition and calibration does not.

### Required implication

Probability outputs must specify the event being predicted.

### Forbidden pattern

```text
Weighted heuristic score
        ↓
Rename to probability
```

---

# 11. Principle 10 — Target Before Model

The target must be defined before evaluating the model.

The project must not use vague objectives such as:

```text
“predict whether the stock is good”
```

A research target must specify what success means.

Examples include:

- next-session open return;
- maximum favorable excursion over N sessions;
- maximum adverse excursion over N sessions;
- probability of hitting a return threshold before a stop;
- continuation probability conditional on current position state;
- expected remaining return;
- probability of exit-trigger invalidation.

### Required implication

Different targets require different labels, metrics and validation protocols.

### Forbidden pattern

```text
Change the definition of success after seeing the results
```

---

# 12. Principle 11 — Metric Must Match Decision Intent

The project rejects universal metrics for semantically different decisions.

For example, the following exits have different objectives:

```text
Profit-taking
Risk stop
Trend invalidation
Reduce exposure
Stop doing T
Full liquidation
Rotation to a superior opportunity
Time-based expiry
```

They must not all be judged by a single rule such as:

```text
“Was the future close below the execution price?”
```

### Required implication

Every decision intent must have an evaluation metric aligned with its purpose.

### Forbidden pattern

```text
One hit-rate metric
used to promote every sell action
```

---

# 13. Principle 12 — Sample Isolation

Training, parameter selection, prior estimation, model selection, calibration and final evaluation must be separated according to the research design.

The project must not estimate a historical prior on a dataset and then present performance on the same dataset as independent evidence unless the result is explicitly labeled in-sample.

At minimum, formal research should distinguish roles such as:

```text
Train
Validation
Calibration
Test / Sealed Test
```

The exact structure may vary by strategy and data availability.

The principle does not.

### Required implication

Any statistic derived from historical outcomes becomes part of the model if it influences future predictions.

It must therefore obey sample isolation.

### Forbidden pattern

```text
Use sample outcomes to tune a prior
        ↓
Evaluate on the same outcomes
        ↓
Call the result out-of-sample
```

---

# 14. Principle 13 — Reproducibility Is a First-Class Requirement

A research result that cannot be reproduced cannot become authoritative.

A formal experiment must eventually identify enough context to reconstruct its result, including where applicable:

```text
Dataset identity
Data version or manifest
Universe identity
Decision-time convention
Feature-set version
Model version
Configuration
Random seed
Execution assumptions
Code revision / Git commit
Environment or dependency identity
```

The project will define an explicit `ExperimentIdentity` contract in later architecture and research specifications.

### Required implication

A result should be tied to an identifiable experiment, not only to a report filename.

### Forbidden pattern

```text
“Last week's backtest was better”
but no one can reconstruct what changed
```

---

# 15. Principle 14 — Trace Everything That Affects a Decision

Every important decision should be explainable after the fact.

The intended decision trace spans the full lifecycle:

```text
Market Context
        ↓
Universe Eligibility
        ↓
Feature Evidence
        ↓
Candidate Ranking
        ↓
Entry Decision
        ↓
Position State
        ↓
Add / Hold / Reduce / Rotate / Exit
        ↓
Portfolio Constraint
        ↓
Execution Result
```

A trace is not merely a human-readable sentence.

It should preserve enough structured information to support:

- debugging;
- attribution;
- counterfactual analysis;
- audit;
- model comparison;
- post-trade review.

### Required implication

The more autonomous the system becomes, the stronger its trace requirements become.

### Forbidden pattern

```text
Action exists
but the system cannot reconstruct why it happened
```

---

# 16. Principle 15 — Fail Closed on Critical Data Uncertainty

When critical data required for a decision is missing, stale, inconsistent or semantically uncertain, the system should prefer refusing the decision over inventing confidence.

This principle applies especially to:

- stale market data;
- incomplete bars;
- unresolved symbol mapping;
- unknown trading eligibility;
- missing PIT state;
- provider conflicts;
- unavailable required features;
- broken model artifacts.

### Required implication

Data quality status must be capable of gating research or decisions.

### Forbidden pattern

```text
Missing critical data
        ↓
Substitute arbitrary default
        ↓
Continue as if confidence were unchanged
```

Defaults may exist for explicitly non-critical fields, but their use must be visible and justified.

---

# 17. Principle 16 — Baseline Before Complexity

Every sophisticated model should be compared with a simpler baseline.

Examples of valid baselines include:

- equal-weight rules;
- linear scoring;
- logistic regression;
- simple cross-sectional ranking;
- buy-and-hold or market benchmarks;
- naive timing rules.

The purpose is not to prefer simple models in all cases.

It is to determine whether added complexity produces measurable incremental value.

### Required implication

A model that cannot beat a relevant simple baseline has not justified its complexity.

### Forbidden pattern

```text
Complex model performs well in isolation
therefore complexity is justified
```

---

# 18. Principle 17 — Incremental Value Must Be Measured

A new feature, theory or model component is not promoted merely because the full model performs well after it is added.

The project must ask:

```text
What changed because of this component?
```

Relevant methods may include:

- ablation;
- incremental IC;
- incremental return;
- change in drawdown;
- change in calibration;
- change in regime robustness;
- change in turnover;
- change in tail risk;
- change in interpretability or operational resilience.

### Required implication

Chan, Tuishen-inspired features, MACD, real capital flow, ETF context and theme features must each earn their place through incremental evidence.

### Forbidden pattern

```text
Add ten components simultaneously
        ↓
Observe improvement
        ↓
Assume every component helped
```

---

# 19. Principle 18 — State Must Be Explicit

Position and strategy state is necessary, but hidden state is dangerous.

The project may maintain state such as:

- position lifecycle state;
- cooldown;
- active setup;
- prior entry thesis;
- risk budget;
- portfolio exposure;
- model regime state.

But state must have:

```text
Owner
Schema
Transition rules
Persistence rules
Reset rules
Trace
Version
```

### Required implication

State transitions are domain events, not incidental side effects scattered across modules.

### Forbidden pattern

```text
Multiple modules mutate position state
without a clear owner
```

---

# 20. Principle 19 — One Owner Per Responsibility

Each major responsibility should have one authoritative owner.

Examples:

```text
Universe eligibility → Universe layer
Feature computation → Feature layer
Candidate ranking → Candidate Discovery
Entry action → Entry policy
Position transitions → Position Lifecycle
Exit intent → Exit model / policy
Portfolio exposure → Portfolio layer
Order simulation → Execution layer
```

A component may consume another component's output.

It should not silently reimplement the same responsibility.

### Required implication

God Objects are architectural warnings because they accumulate multiple owners into one file or class.

### Forbidden pattern

```text
Backtest engine
also owns feature definitions
also owns portfolio state
also owns execution
also owns reporting
also owns strategy semantics
```

---

# 21. Principle 20 — Modular and Composable Architecture

The project must support independent evolution of:

- data providers;
- feature families;
- candidate models;
- entry models;
- exit models;
- portfolio policies;
- execution models;
- validation workflows.

Composition should happen through explicit contracts rather than shared hidden assumptions.

### Required implication

The project should be able to run controlled experiments such as:

```text
Baseline
Baseline + ETF context
Baseline + real flow
Baseline + Chan
Baseline + Tuishen-inspired features
Baseline + Chan + Tuishen-inspired features
```

without rewriting the whole pipeline.

### Forbidden pattern

```text
To test one feature family,
modify a monolithic strategy engine in ten places
```

---

# 22. Principle 21 — Configuration Is Part of the Model

Configuration affects model behavior and must therefore be governed.

A large configuration surface can create hidden overfitting even if every individual parameter appears reasonable.

The project must distinguish:

- research parameters;
- execution parameters;
- risk limits;
- environment configuration;
- provider configuration;
- feature configuration;
- model hyperparameters.

### Required implication

Configuration must have ownership, versioning and a known scope.

Large flat configuration objects should be decomposed by domain.

### Forbidden pattern

```text
Hundreds of unrelated fields
inside one global backtest config
```

---

# 23. Principle 22 — Realistic Execution Is Part of Validation

A signal that cannot be executed under realistic market constraints is not validated Alpha.

Formal evaluation must account for applicable realities such as:

- T+1;
- suspension;
- price limits;
- unavailable entry or exit;
- transaction costs;
- taxes;
- slippage;
- liquidity;
- market sessions;
- data timestamp alignment.

### Required implication

The project distinguishes signal quality from realizable trading outcome.

Both matter.

### Forbidden pattern

```text
Use theoretical close price
for an order that could not have been filled
```

---

# 24. Principle 23 — Risk and Invalidation Are Mandatory

Every strategy or candidate hypothesis must specify not only why it may work, but also how it can fail.

At minimum, serious strategy research must eventually identify:

```text
Primary risks
Expected failure modes
Invalidation conditions
Exposure limits
Stop or risk response
Regime sensitivity
Data dependency
```

The project rejects one-sided research that models upside while leaving downside undefined.

### Required implication

A candidate with high expected return but undefined downside is not a complete decision object.

---

# 25. Principle 24 — Promotion Requires Explicit Gates

Research promotion must be governed by explicit criteria.

A component should not enter a more authoritative stage because of enthusiasm, recent performance or implementation convenience.

Promotion gates may eventually include:

- data qualification;
- unit and integration correctness;
- point-in-time review;
- baseline comparison;
- out-of-sample evidence;
- walk-forward stability;
- calibration;
- ablation;
- risk review;
- execution realism;
- reproducibility;
- shadow observation.

The exact gate set is defined in `07-Validation-Constitution.md`.

### Required implication

Promotion is a decision event with evidence.

### Forbidden pattern

```text
Recent backtest looks strong
        ↓
Enable in production
```

---

# 26. Principle 25 — Degradation and Retirement Are Normal

The project assumes that Alpha can decay.

A strategy component may become:

- weaker;
- crowded;
- regime-incompatible;
- data-dependent;
- operationally too expensive;
- redundant after another component is introduced.

Therefore, the project must support:

```text
Monitor
Detect degradation
Investigate
Reduce authority
Quarantine
Retrain / redesign
Retire
```

### Required implication

Retirement is not failure of the research system.

Failing to detect decay is.

---

# 27. Principle 26 — Migration Must Preserve Knowledge

Architecture refactoring must not destroy useful research history.

The project adopts gradual migration:

```text
Characterize current behavior
        ↓
Introduce explicit contract
        ↓
Adapt legacy implementation
        ↓
Compare behavior
        ↓
Migrate responsibility
        ↓
Retire duplicate path
```

### Required implication

Before extracting complex legacy logic, preserve behavior with characterization tests where practical.

### Forbidden pattern

```text
Move many files
rename many concepts
change behavior
change configuration
all in one step
```

---

# 28. Principle 27 — Documentation Is Part of the System Contract

For this project, documentation is not an afterthought.

The Constitution, architecture documents, research designs and specifications define system contracts that agents and developers are expected to follow.

The documentation hierarchy is:

```text
docs/
├── constitution/   # Normative project rules
├── architecture/   # Concrete architecture and migration
├── research/       # Research methods and evidence
├── designs/        # Subsystem designs
└── specs/          # Implementable contracts
```

### Required implication

Major semantic changes require documentation updates.

### Forbidden pattern

```text
Code changes system meaning
but documentation continues describing the old meaning
```

---

# 29. Principle 28 — Agents Are Assistants, Not Constitutional Authorities

AI agents may assist with:

- research;
- code generation;
- refactoring;
- test creation;
- experiment orchestration;
- documentation;
- review;
- anomaly detection.

Agents must not silently redefine project goals, validation standards or production authority.

The Constitution has higher authority than agent convenience.

### Required implication

Claude Code, Codex, ChatGPT and future agents should treat Constitution documents as governing context.

### Forbidden pattern

```text
Agent finds implementation easier another way
        ↓
Silently violates project contracts
```

---

# 30. Principle 29 — No Deterministic Return Claims

The project operates in an uncertain market environment.

It does not promise guaranteed profits, stable deterministic returns or certainty of future price direction.

All strategy outputs are conditional estimates under assumptions.

### Required implication

Research reports must distinguish:

```text
Fact
Inference
Model assumption
Trading plan
Risk
Invalidation condition
Observation metric
```

This distinction is especially important when communicating model outputs to humans.

---

# 31. Principle 30 — The System Must Become More Explainable as It Becomes More Powerful

Sophistication must not reduce accountability.

As the project adds:

- more data sources;
- more features;
- more models;
- more automation;
- more agents;
- more portfolio logic;

the system must also strengthen:

- lineage;
- versioning;
- trace;
- reproducibility;
- governance;
- monitoring;
- failure isolation.

The project rejects the idea that a mature quantitative system is necessarily opaque.

Complexity may increase.

Untraceability must not.

---

# 32. Constitutional Anti-Patterns

The following patterns are explicitly recognized as threats to the project:

## 32.1 Rule accumulation without attribution

```text
Performance weakens
        ↓
Add rule
        ↓
Performance weakens again
        ↓
Add another rule
```

without systematic ablation or attribution.

---

## 32.2 Indicator democracy

```text
Many related indicators agree
        ↓
Treat agreement as independent evidence
```

---

## 32.3 Probability theater

```text
Heuristic score = 72
        ↓
Display “72% probability”
```

---

## 32.4 Semantic overloading

One `signal` or `sell` field representing several incompatible intents.

---

## 32.5 Sample reuse

Using the same sample for hypothesis formation, prior estimation, tuning and final proof without honest labeling.

---

## 32.6 Data convenience over correctness

Choosing a dataset because it is easy to obtain while ignoring PIT, eligibility or finalization requirements needed by the research claim.

---

## 32.7 God Object expansion

Continuing to add responsibilities to a file or class because it is already central.

---

## 32.8 Hidden defaults

Replacing missing critical information with fixed values while preserving the appearance of full model confidence.

---

## 32.9 Architecture by inheritance from legacy

Allowing historical package names and earlier project goals to define future boundaries by inertia.

---

## 32.10 Promotion by enthusiasm

Treating an attractive recent result as sufficient evidence for formal authority.

---

# 33. Constitutional Review Questions

Every major change should be reviewable through the following questions.

## Research

- What hypothesis is being tested?
- What is the target?
- What evidence would falsify the hypothesis?
- Is there a baseline?
- Is incremental value measured?

## Data

- Was the information available at decision time?
- Is the universe point-in-time correct?
- Is data provenance known?
- What happens when required data is missing?

## Feature

- What is the lineage?
- Which information family does it belong to?
- Does it overlap with existing features?

## Semantics

- Does this change introduce another meaning for an existing field?
- Is there one authoritative owner?
- Does the same term mean the same thing across layers?

## Validation

- Is the sample independent?
- Is execution realistic?
- Is the result reproducible?
- Is the metric aligned with the decision intent?

## Architecture

- Is responsibility becoming clearer or more centralized?
- Can the component be tested and replaced independently?
- Is hidden state being introduced?

## Risk

- What can make the model fail?
- What are the invalidation conditions?
- What happens when confidence is unsupported by data?

---

# 34. Exception Policy

The Constitution is designed to govern the project, not to prevent all experimentation.

A research experiment may temporarily violate a normal production constraint when the purpose of the experiment requires it.

However, the exception must be explicit.

An exception should identify:

```text
Principle being relaxed
Reason
Scope
Duration
Research-only or production impact
Risk
Exit condition
```

An undocumented exception is not an exception.

It is drift.

---

# 35. Relationship to Remaining Constitution Volumes

This document defines the principles.

The following documents operationalize them:

```text
02-Architecture-Blueprint.md
    Defines system boundaries, ownership and contracts.

03-Research-Framework.md
    Defines the formal lifecycle from hypothesis to research result.

04-Data-Constitution.md
    Defines data correctness, PIT, provenance and provider requirements.

05-Factor-Constitution.md
    Defines feature identity, lineage, families, redundancy and factor research.

06-Strategy-Constitution.md
    Defines Candidate, Entry, Position Lifecycle, Exit and strategy composition.

07-Validation-Constitution.md
    Defines backtest, walk-forward, OOS, calibration, promotion and degradation gates.

08-Roadmap.md
    Defines phased implementation and migration priorities.

09-Glossary.md
    Freezes project terminology and canonical definitions.
```

---

# 36. Closing Rule

Whenever the project faces a choice between:

```text
More rules
or
More evidence
```

choose more evidence.

Whenever it faces a choice between:

```text
Faster implementation
or
Stable semantics
```

preserve semantics.

Whenever it faces a choice between:

```text
A stronger-looking backtest
or
A more honest validation
```

choose the more honest validation.

Whenever it faces a choice between:

```text
Hidden convenience
or
Traceable complexity
```

choose traceability.

The core constitutional principle of `market-regime-alpha` is therefore:

> **Every increase in model power must be matched by an increase in evidence quality, traceability and governance.**
