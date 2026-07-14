# The Constitution of Market Regime Alpha

# Volume IV — Research Framework

> **Document:** `docs/constitution/03-Research-Framework.md`  
> **Status:** Foundational / Normative  
> **Authority:** Project-wide research lifecycle, research-object model, experiment discipline and evidence-flow framework  
> **Applies to:** Research programs, hypotheses, targets, experiments, baselines, model development, strategy research, ablation, attribution, research artifacts, promotion decisions, monitoring, agents, and legacy research migration  
> **Project:** `market-regime-alpha`  
> **Precedence:** Must remain consistent with `00-Project-Vision.md`, `01-Core-Principles.md`, and `02-Architecture-Blueprint.md`

---

## 0. Purpose

`00-Project-Vision.md` defines what `market-regime-alpha` is becoming.

`01-Core-Principles.md` defines the principles the project must not silently violate.

`02-Architecture-Blueprint.md` defines the target system boundaries and ownership model.

This document defines **how the project conducts research**.

Its purpose is to transform the project from a collection of plausible trading ideas and integrated rule engines into a disciplined research operating system in which an idea can move through a traceable lifecycle:

```text
Observation
    ↓
Research Question
    ↓
Falsifiable Hypothesis
    ↓
Explicit Target
    ↓
Eligible Information Set
    ↓
Baseline
    ↓
Experiment
    ↓
Evidence
    ↓
Attribution
    ↓
Research Decision
    ↓
Promotion / Revision / Rejection / Quarantine / Retirement
    ↓
Monitoring and Feedback
```

The central rule of this Research Framework is:

> **The project does not promote ideas. It promotes evidence-backed, reproducible research objects with explicit targets, valid information sets, known failure conditions and traceable identities.**

This document is intentionally not:

- the detailed point-in-time data specification;
- the detailed feature registry specification;
- the detailed strategy contract;
- the numeric validation threshold catalog;
- the implementation plan for refactoring the repository.

Those responsibilities belong respectively to:

```text
04-Data-Constitution.md
05-Factor-Constitution.md
06-Strategy-Constitution.md
07-Validation-Constitution.md
08-Roadmap.md
```

This volume defines the lifecycle that connects them.

---

# 1. Alignment With the Project Vision

## 1.1 The research framework serves the Alpha Research Operating System

The project is not being refounded to build one larger strategy.

It is being refounded to support repeated research across multiple opportunity classes, including:

- Candidate Discovery;
- market-regime research;
- ETF and theme rotation;
- next-session or overnight opportunities;
- multi-session trend continuation;
- independent entry timing;
- position lifecycle management;
- independent exit research;
- long-term and dividend strategies;
- capital-flow research;
- price-volume research;
- Chan-derived structural features;
- Tuishen-inspired quantitative features;
- MACD and moving-average research;
- event and policy research;
- portfolio and execution research.

The Research Framework must therefore remain strategy-neutral at the platform level.

A specific research program may study:

```text
T-day late-session entry
        ↓
T+1 early-session upward excursion
```

but that does not redefine the entire project as a fixed next-morning exit system.

A specific ETF model may later trade ETFs directly, but the current constitutional role of ETF and theme research also includes:

```text
Market Context
    ↓
Rotation Detection
    ↓
Candidate Universe Narrowing
    ↓
Individual Security Discovery
```

The framework must support both without collapsing them into one model.

---

## 1.2 The current first research priority remains Candidate Discovery

The current project priority established by the Project Vision is Candidate Discovery.

The Research Framework therefore gives special attention to the research problem:

> **At a defined decision time, among securities that were actually eligible and tradable, which securities have the most attractive forward opportunity profile for a precisely defined target?**

This is a cross-sectional research problem.

It is not equivalent to running a single-stock timing engine repeatedly across thousands of securities.

It requires explicit research treatment of:

- point-in-time universe construction;
- comparable features across securities;
- cross-sectional normalization;
- ranking targets;
- top-K selection behavior;
- sector and theme concentration;
- liquidity and execution feasibility;
- target-specific forward labels;
- ranking stability;
- rejection reasons;
- incremental context from Market Regime, ETF Rotation and Theme Rotation.

Candidate Discovery produces research predictions and rankings.

It does not directly own capital allocation or execution.

---

## 1.3 Position management is a continuing research problem

The project explicitly rejects the idea that every position must be exited at a fixed time merely because the initial candidate model was designed around an overnight opportunity.

The canonical lifecycle remains:

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

Not every position passes through every state, and the diagram is not a mandatory linear sequence.

The research implication is that the project must study separate questions:

- Should a new position be entered?
- Is the original thesis still valid?
- Has expected remaining return increased or decreased?
- Is additional capital justified?
- Has risk increased enough to reduce exposure?
- Has a superior opportunity created a rotation case?
- Has an exit condition or invalidation condition occurred?

The research framework must not evaluate all of these questions with one overloaded target or one universal hit-rate metric.

---

# 2. Research Worldview

## 2.1 Alpha is a conditional claim

Within `market-regime-alpha`, Alpha is not a descriptive label attached to an indicator.

Alpha is a research claim of the form:

```text
Under information set I,
for population U,
at decision time T,
under market condition or regime R,
observable construct X
contains incremental information
about target Y
over horizon H,
after realistic implementation assumptions C.
```

A strong research object should make each element inspectable.

For example:

```text
Claim:
Among point-in-time tradable A-shares at 14:45,
late-session relative strength combined with industry strength
contains incremental information about
next-session maximum favorable excursion before 10:30,
after liquidity filters and realistic next-eligible execution assumptions.
```

This is a researchable claim.

The weaker statement:

```text
“Strong stocks usually continue rising.”
```

is a source of intuition, not a completed research object.

---

## 2.2 Markets are non-stationary and regime-dependent

The project does not assume a single stationary data-generating process.

A feature or strategy may behave differently across:

- trend regimes;
- volatility regimes;
- liquidity regimes;
- risk-on and risk-off conditions;
- policy cycles;
- broad versus concentrated markets;
- early versus late theme stages;
- leader-driven versus breadth-driven markets;
- high-crowding versus low-crowding environments.

Therefore, research must distinguish between:

```text
Unconditional effectiveness
```

and:

```text
Conditional effectiveness by regime or context
```

However, regime analysis must not become a post-hoc excuse for weak results.

A regime split introduced only after observing failures is a new hypothesis and must be evaluated as such.

---

## 2.3 Research claims must be falsifiable

A hypothesis must define what evidence would weaken or reject it.

Examples:

### Non-falsifiable

```text
The feature works when the market recognizes it.
```

### Falsifiable

```text
After controlling for baseline momentum and liquidity,
feature X should improve out-of-sample RankIC
and top-decile economic outcomes
without materially worsening turnover-adjusted drawdown.
```

The exact metric depends on the target and belongs to the experiment design.

The principle is universal:

> **A research claim that cannot lose cannot be validated.**

---

## 2.4 Research separates fact, inference, assumption and action

Every serious research report should distinguish, where relevant:

```text
Fact
Inference
Model assumption
Trading or strategy plan
Risk
Invalidation condition
Observation metric
```

Examples:

### Fact

```text
The ETF's turnover increased by X% relative to its trailing window.
```

### Inference

```text
This may indicate increasing participation.
```

### Model assumption

```text
The model assumes this participation measure is available at the decision time and has comparable semantics across the sample.
```

### Strategy plan

```text
Candidates in the highest eligible rank bucket may be considered by the Entry policy.
```

### Risk

```text
The turnover increase may reflect late-stage crowding rather than early inflow.
```

### Invalidation

```text
If the feature does not add incremental out-of-sample value beyond the baseline, it is not promoted.
```

### Observation metric

```text
Incremental RankIC, top-K spread, calibration, turnover and regime stability.
```

This separation is mandatory for decision quality and post-mortem analysis.

---

# 3. The Canonical Research Lifecycle

The canonical lifecycle is:

```text
1. Observation or Idea
        ↓
2. Research Question
        ↓
3. Falsifiable Hypothesis
        ↓
4. Research Charter
        ↓
5. Target Contract
        ↓
6. Data and Universe Eligibility
        ↓
7. Baseline Definition
        ↓
8. Feature / Signal / Model Prototype
        ↓
9. Experiment Design
        ↓
10. Development / Training
        ↓
11. Controlled Evaluation
        ↓
12. Walk-Forward / Out-of-Sample Evaluation
        ↓
13. Calibration Where Applicable
        ↓
14. Ablation and Attribution
        ↓
15. Economic, Risk and Execution Review
        ↓
16. Reproducibility Review
        ↓
17. Research Decision
        ↓
18. Promotion / Revision / Rejection / Quarantine
        ↓
19. Paper / Shadow Observation Where Required
        ↓
20. Ongoing Monitoring
        ↓
21. Degradation Detection
        ↓
22. Retraining / Redesign / Retirement
        ↓
23. Knowledge Feedback
```

This lifecycle is directional but iterative.

A research object may return to an earlier stage.

For example:

```text
Evaluation fails
    ↓
Hypothesis revised
    ↓
Target preserved or explicitly versioned
    ↓
New experiment identity
```

What is prohibited is silently modifying the hypothesis, target, feature definition or sample until the result becomes attractive while continuing to present the process as one unchanged experiment.

---

# 4. Research Object Model

The project treats research as a system of explicit objects rather than a sequence of undocumented notebook decisions.

## 4.1 Research Program

A Research Program is a durable problem area.

Examples:

```text
Candidate Discovery
Market Regime
ETF Rotation
Theme Rotation
Next-Session Opportunity
Position Continuation
Exit Quality
Capital Flow
Chan Structure
Tuishen-Inspired Price-Volume Research
```

A Research Program may contain many hypotheses and experiments.

It is not itself a strategy or model.

---

## 4.2 Research Question

A Research Question defines what the project is trying to learn.

Examples:

```text
Does late-session relative strength help rank next-session upward-excursion opportunities?
```

```text
Does real capital-flow data add incremental information beyond OHLCV-derived flow proxies?
```

```text
Does a quantified Chan structure improve entry quality after controlling for trend and price location?
```

A question should be narrow enough to answer with evidence.

---

## 4.3 Hypothesis

A Hypothesis is a falsifiable expected relationship.

It must identify at least:

- the information or intervention being studied;
- the expected direction of effect;
- the target or decision being affected;
- the relevant population;
- the expected context or regime dependence;
- the primary failure condition.

Hypotheses must be versioned when their meaning changes materially.

---

## 4.4 Research Charter

The Research Charter is the pre-experiment contract.

It defines the problem before results are known.

A formal Research Charter should include, directly or by reference:

```text
Research Program
Research Question
Hypothesis ID and version
Decision being supported
Target definition
Decision time
Prediction horizon
Population / universe
Required information set
Required data eligibility
Baseline
Primary evaluation dimensions
Secondary evaluation dimensions
Expected direction
Known confounders
Execution assumptions
Primary risks
Invalidation conditions
Planned ablations
Planned regime analysis
Sample-role plan
Promotion intent
Current authority level
```

A Research Charter is not required for every five-minute exploratory calculation.

It is required before a research result can become formal evidence for promotion.

---

## 4.5 Target Contract

A Target Contract defines what is being predicted or optimized.

It must make success measurable.

A Target Contract may describe:

- a continuous forward return;
- a rank target;
- an event probability;
- a maximum favorable excursion;
- a maximum adverse excursion;
- a barrier-hit event;
- a continuation event;
- an invalidation event;
- a state transition;
- an economic utility target.

The Target Contract must specify enough semantics to prevent target drift.

At minimum, where applicable:

```text
Target ID
Target version
Population
Decision time
Reference price semantics
Label start time
Label end time
Horizon
Event definition
Barrier definition
Cost treatment
Missing-label policy
Suspension / limit-state policy
Corporate-action treatment
```

The exact schema belongs to lower-level specifications.

---

## 4.6 Dataset and Universe Identity

A result must identify the data and population on which it was produced.

The Research Framework therefore requires explicit identities for:

```text
Dataset
Universe
Time range
Sample role
Decision-time convention
```

The Data Constitution will define the detailed data eligibility and manifest rules.

The research-level rule is:

> **A result without identifiable data and universe context is not a formal research result.**

---

## 4.7 Feature Set

A Feature Set is a versioned set of formal inputs.

It must be distinguishable from:

- a single feature;
- a strategy rule;
- a model artifact;
- a target;
- a runtime decision.

The Factor Constitution will define feature identity, lineage and redundancy rules.

The Research Framework requires that experiments identify which Feature Set was used.

---

## 4.8 Baseline

A Baseline is the minimum comparison required to justify complexity.

A baseline may be:

- a naive predictor;
- an equal-weight score;
- a simple momentum rule;
- a simple cross-sectional rank;
- logistic regression;
- a linear model;
- a fixed-time exit;
- buy-and-hold;
- the current Legacy strategy;
- the previous promoted version.

A baseline is chosen according to the research question.

There is no universal baseline for every problem.

---

## 4.9 Experiment

An Experiment is an identified execution of a research design.

It connects:

```text
Hypothesis
Target
Data
Universe
Feature Set
Model / Rule
Configuration
Execution assumptions
Sample roles
Code identity
```

and produces identified results.

Changing any result-affecting element may require a new Experiment Identity.

---

## 4.10 Research Result

A Research Result is more than a performance number.

It should contain or reference:

```text
Experiment Identity
Primary results
Secondary results
Uncertainty
Failure cases
Regime breakdown
Ablation / attribution
Execution sensitivity
Data quality status
Known limitations
Reproducibility status
Research decision
```

A favorable metric without limitations or failure cases is an incomplete result.

---

## 4.11 Research Decision Record

A Research Decision Record captures what the project decided because of the evidence.

Valid outcomes include:

```text
REJECT
REVISE
CONTINUE_RESEARCH
PROMOTE_RESEARCH_STATUS
PROMOTE_TO_SHADOW
PROMOTE_TO_PRODUCTION_ELIGIBLE
QUARANTINE
RETRAIN
RETIRE
```

The exact status vocabulary may be implemented in a registry, but the semantic distinction is constitutional.

A result does not promote itself.

Promotion is an explicit decision with evidence and authority.

---

# 5. Research Status Lifecycle

The project distinguishes research maturity from implementation completeness.

The canonical status family is:

```text
IDEA
    ↓
HYPOTHESIS
    ↓
PROTOTYPE
    ↓
RESEARCH_CANDIDATE
    ↓
VALIDATED_RESEARCH_COMPONENT
    ↓
PAPER_OR_SHADOW_CANDIDATE
    ↓
PRODUCTION_ELIGIBLE
    ↓
PRODUCTION_ACTIVE
    ↓
DEGRADED / QUARANTINED
    ↓
RETRAINED / REDESIGNED / RETIRED
```

These states are not a mandatory straight line.

A component may:

- remain a useful research diagnostic indefinitely;
- be rejected before validation;
- be promoted to a shadow role but never become production eligible;
- become degraded and return to research;
- be retired while its historical evidence remains preserved.

The exact promotion thresholds belong to `07-Validation-Constitution.md`.

This document defines the lifecycle and evidence responsibilities.

---

# 6. Research Charter Discipline

## 6.1 Define the decision before the model

Every formal research program must identify the decision it is intended to improve.

Examples:

```text
Rank new candidates
```

```text
Decide whether to enter a ranked candidate
```

```text
Estimate whether an existing position should remain held
```

```text
Detect structural invalidation
```

```text
Rank ETFs as upstream market context
```

A model without a decision context may still be academically interesting, but it must not silently become a trading component.

---

## 6.2 Define failure before seeing the final result

A Research Charter should state what would cause the hypothesis to be:

- rejected;
- revised;
- restricted to a narrower context;
- considered economically irrelevant;
- considered operationally unusable.

Examples:

```text
The feature has predictive correlation but adds no incremental value beyond existing OHLCV features.
```

```text
The model improves gross return but only through unrealistic turnover.
```

```text
The signal works only in a post-hoc regime slice with insufficient support elsewhere.
```

```text
The probability ranking is strong but calibration is unusable for the intended decision.
```

Failure conditions protect the research process from goalpost movement.

---

## 6.3 Separate primary and secondary questions

A formal experiment should identify:

```text
Primary question
Secondary questions
Exploratory diagnostics
```

This prevents a failed primary hypothesis from being silently replaced with whichever secondary metric appears strongest.

Exploratory findings are valuable.

They become new hypotheses, not retroactive proof of the old one.

---

# 7. Target-First Research

## 7.1 The project does not use one universal “up” label

Different decisions require different targets.

For Candidate Discovery, useful target families may include:

```text
next_open_return
next_session_close_return
next_30m_max_return
next_60m_max_return
next_60m_close_return
multi_session_return
maximum_favorable_excursion
maximum_adverse_excursion
hit_return_threshold_before_stop
breakout_continuation
```

These names are examples of target families, not a final schema.

The Research Framework explicitly rejects the vague target:

```text
“Will the stock go up?”
```

without:

- a decision time;
- a reference price;
- a horizon;
- an event definition;
- execution semantics.

---

## 7.2 Candidate targets and exit targets are different

A candidate model may predict:

```text
P(hit +1% within next session)
```

An exit model may predict:

```text
Expected remaining return conditional on current position state
```

or:

```text
P(structural invalidation within next N bars)
```

These are not inverse labels.

The project must not define Exit simply by negating the Candidate or Entry target.

---

## 7.3 Multi-target research is allowed but must remain explicit

A model may estimate several outputs:

```text
Expected Return
Expected MFE
Expected MAE
Probability of Threshold Hit
Expected Holding Horizon
```

But multiple outputs must not be collapsed into one undocumented composite score.

If a utility function combines them, the utility definition becomes a research object and must be versioned.

---

## 7.4 Target changes create new research meaning

Changing:

```text
next-session close return
```

to:

```text
maximum return before 10:30
```

is not a minor implementation change.

It changes the research question.

The target must be versioned accordingly.

---

# 8. Decision-Time and Label-Time Discipline

The research framework distinguishes:

```text
Information available at decision time
```

from:

```text
Future information used only to construct the label
```

The canonical temporal relationship is:

```text
Source Events
    ↓
Availability / Finalization
    ↓
Feature Materialization
    ↓
Decision Time
    ↓
Next Eligible Execution Time
    ↓
Future Label Window
```

A label may use future information.

A feature may not.

The project must explicitly define, where relevant:

- whether a bar is complete;
- when the feature becomes available;
- whether the decision is made at bar close, after bar close, or before finalization;
- the next executable price convention;
- the beginning and end of the label window.

The detailed temporal and point-in-time rules belong to `04-Data-Constitution.md`.

This Research Framework makes compliance with them mandatory.

---

# 9. Data Eligibility in Research

## 9.1 Data access is not evidence eligibility

The project distinguishes:

```text
Can fetch data
        ≠
Can normalize data
        ≠
Can reproduce data
        ≠
Can prove point-in-time semantics
        ≠
Can use data for formal promotion
```

Exploratory data may be sufficient for:

- prototyping;
- interface development;
- rough hypothesis screening;
- pipeline smoke testing.

It may be insufficient for:

- formal out-of-sample claims;
- calibrated probability claims;
- promotion decisions;
- sealed evaluation.

The exact data eligibility classes are defined by `04-Data-Constitution.md`.

---

## 9.2 Current project data limitations remain binding

The existing formal data-source audit has already established that currently available free or cached sources do not, by themselves, prove all formal research requirements such as:

- explicit bar-finalization provenance;
- point-in-time minute adjustment;
- point-in-time tradable universe;
- historical ST and suspension state;
- historical price-limit state;
- historical industry and theme mappings;
- complete market sidecars;
- formal licensing and reproducibility requirements.

Therefore:

> **The Research Framework must not treat data-source convenience as formal evidence eligibility.**

Until a data source or dataset passes the required future Data Constitution gates, related results must remain honestly classified according to their actual evidence level.

---

## 9.3 Fail closed for critical eligibility gaps

If a hypothesis requires information that cannot be reconstructed correctly, the project has three valid options:

```text
1. Narrow the claim
2. Acquire or build the required data
3. Keep the result exploratory
```

The invalid option is:

```text
Fill missing historical truth with today's value
and continue as if the experiment were PIT-correct
```

---

# 10. Universe and Population Discipline

## 10.1 The population is part of the claim

A model evaluated on:

```text
20 hand-selected dividend stocks
```

is not automatically evidence for:

```text
all A-shares
```

A model evaluated on:

```text
large-cap liquid stocks
```

is not automatically evidence for:

```text
small-cap thematic leaders
```

Every formal result must identify its population.

---

## 10.2 Cross-sectional research requires point-in-time universe semantics

For Candidate Discovery, the universe must reflect what was eligible at each historical decision time.

Relevant conditions may include:

- listing status;
- listing age;
- ST status;
- suspension;
- liquidity;
- price-limit state;
- data completeness;
- strategy-specific exclusions.

The exact rules belong to the Data and Strategy Constitutions.

The research requirement is that the universe be identifiable and reproducible.

---

## 10.3 Convenience samples must be labeled honestly

A small sample may be useful for:

- debugging;
- prototype iteration;
- initial hypothesis screening;
- adapter verification.

It must not be silently presented as market-wide evidence.

---

## 10.4 Population drift must be monitored

If the effective population changes materially over time, research should consider:

- coverage changes;
- missing-data changes;
- liquidity changes;
- listing composition changes;
- provider changes;
- regime-dependent eligibility.

A stable metric on a changing population may not represent stable Alpha.

---

# 11. Baseline-First Research

## 11.1 Complexity must earn its place

The project requires a relevant baseline before a complex model can justify itself.

A typical complexity ladder may be:

```text
Naive benchmark
    ↓
Simple rule
    ↓
Simple linear / logistic model
    ↓
Simple ranking model
    ↓
Tree-based model
    ↓
More complex ensemble
    ↓
Specialized deep or agentic model
```

The ladder is illustrative, not mandatory.

The principle is:

> **A more complex model must show incremental value relative to a simpler relevant alternative.**

---

## 11.2 Rule systems are valid baselines

The project does not reject rules.

Rule models can be strong research tools because they are:

- interpretable;
- deterministic;
- easy to ablate;
- easy to replay;
- useful for expressing theory.

But rules remain subject to the same evidence requirements as machine-learning models.

---

## 11.3 Legacy systems may serve as baselines

The existing `DividendTStrategy` and `CoscoTimingEngine` may be valuable as:

- Legacy baselines;
- shadow comparators;
- sources of reusable feature hypotheses;
- behavior-preservation references during migration.

They are not automatically the target architecture.

A V2 model that cannot outperform or improve upon a relevant Legacy baseline must explain why its architectural or operational benefits justify promotion.

---

# 12. Experiment Design

## 12.1 One experiment should answer a defined question

An experiment may contain multiple metrics and ablation arms.

But it should have a primary research question.

The project rejects experiments of the form:

```text
Change ten rules
Change three factors
Change the universe
Change the execution model
Change the target
Then compare final return
```

Such a result cannot support reliable attribution.

---

## 12.2 Treatment and control must be explicit

Where applicable, experiments should identify:

```text
Control / Baseline
Treatment
Difference being tested
```

Examples:

```text
Baseline
vs
Baseline + ETF context
```

```text
OHLCV flow proxy
vs
Real capital-flow data
```

```text
Entry baseline
vs
Entry baseline + quantified Chan structure
```

---

## 12.3 Factorial and ablation designs are preferred for interacting components

If components may interact, the project should consider designs such as:

```text
Baseline
A only
B only
A + B
```

This allows decomposition into:

- A effect;
- B effect;
- interaction effect.

The current MACD research infrastructure already contains useful factorial-attribution concepts.

These concepts should be generalized where appropriate rather than discarded.

---

## 12.4 Primary metrics should be declared before final evaluation

The project may inspect many diagnostics.

However, the experiment should identify which metrics answer the primary question.

Otherwise metric shopping can replace target shopping.

---

## 12.5 Negative results are valid research outputs

A failed hypothesis may teach the project that:

- a feature is redundant;
- a theory is regime-limited;
- an execution assumption destroys apparent Alpha;
- a professional data source does not add enough value;
- a complex model adds no incremental benefit;
- a target is too noisy;
- a sample is insufficient.

These are useful findings.

The research system should preserve them to prevent repeated unproductive work.

---

# 13. Experiment Identity and Reproducibility

## 13.1 Every formal experiment requires identity

The project already contains a valuable precedent in `MACDExperimentIdentity`.

The long-term platform must generalize this idea into a platform-level `ExperimentIdentity`.

A formal experiment should be able to identify, where applicable:

```text
Experiment ID
Research Program ID
Hypothesis ID and version
Target ID and version
Dataset Manifest ID
Universe ID
Sample Split ID
Decision-time convention
Feature Set ID and version
Model / Rule ID and version
Calibration artifact ID
Strategy component versions
Portfolio policy version
Execution configuration identity
Code revision / Git commit
Configuration hashes
Random seed
Environment / dependency identity
Run timestamp
Parent experiment IDs
Sealed-test access state
Research status
```

Not every experiment requires every field.

Every result-affecting element does require identity.

---

## 13.2 Result identity must be content-aware

A filename is not sufficient experiment identity.

The project should prefer deterministic identities or hashes derived from canonicalized result-affecting configuration.

The existing MACD experiment code already demonstrates useful patterns such as:

- canonical configuration serialization;
- config hashing;
- explicit algorithm and contract versions;
- execution configuration identity;
- data split identity;
- Git commit identity.

These should be preserved as research assets and generalized into V2.

---

## 13.3 Changing a result-affecting input creates a new experiment meaning

Examples include changing:

- target definition;
- data version;
- feature definition;
- model hyperparameters;
- execution assumptions;
- universe filters;
- calibration method;
- sample split;
- risk policy.

The project must not overwrite previous results as if nothing changed.

---

## 13.4 Reproduction must be distinguishable from rerun

A rerun means the code executed again.

A reproduction means the project can reconstruct the same research conditions and obtain materially consistent results within the expected determinism envelope.

The latter is required for formal authority.

---

# 14. Sample Roles and Isolation

## 14.1 Historical data can have different roles

A formal research design may distinguish:

```text
Development / Train
Validation
Calibration
Test
Sealed Test
Shadow / Forward Observation
```

The exact split depends on the research problem.

The semantic separation does not.

---

## 14.2 Sample-derived knowledge becomes part of the model

If the project calculates from historical outcomes:

- a prior;
- a threshold;
- a weight;
- a calibration curve;
- a regime rule;
- a feature-selection decision;
- a model hyperparameter;

and then uses it in future inference, that knowledge is part of the model.

It must obey sample isolation.

---

## 14.3 Current hard-coded buy-point priors are a migration example

The current `buy_point_quality.py` contains empirical priors derived from a local 20-symbol, one-year sample.

The taxonomy of buy-point subtypes may remain useful.

The learned outcome statistics must not remain permanently hard-coded as if they were timeless constants.

The target research pattern is:

```text
Training / Estimation Sample
        ↓
Versioned Prior or Calibration Artifact
        ↓
Frozen Artifact Identity
        ↓
Independent Evaluation
        ↓
Promotion Decision
```

This is a concrete example of the broader rule:

> **Research evidence may become a runtime artifact only through explicit, versioned promotion.**

---

## 14.4 Sealed evaluation must remain sealed

A sealed test exists to provide evidence not repeatedly optimized against.

The project must not:

- inspect sealed results during ordinary tuning;
- use sealed outcomes to revise the same model and still call the result sealed;
- allow an agent to access sealed results merely because automation makes access convenient;
- repeatedly query the sealed set until a desired result appears.

The exact sealed-test governance belongs to `07-Validation-Constitution.md`.

Until formally authorized otherwise, current refoundation constraints that protect existing research state remain in force, including the principle that sealed-test access must not be silently activated.

---

# 15. Evaluation Is Multi-Dimensional

No single metric proves Alpha.

The relevant evaluation dimensions depend on the research object.

## 15.1 Predictive quality

Examples include:

- IC;
- RankIC;
- AUC;
- precision / recall;
- top-K hit behavior;
- ranking spread;
- event likelihood discrimination;
- forecast error.

The metric must match the target.

---

## 15.2 Economic quality

Examples include:

- expected return;
- threshold-hit rate;
- maximum favorable excursion;
- maximum adverse excursion;
- payoff asymmetry;
- turnover-adjusted return;
- transaction-cost sensitivity;
- capacity or liquidity constraints.

Predictive quality without economic usefulness may not justify a strategy component.

---

## 15.3 Calibration quality

If the output is called a probability, the project must evaluate calibration.

Relevant concepts may include:

- reliability by probability bucket;
- Brier score;
- calibration error;
- calibration drift;
- calibration stability across regimes.

A good ranking model is not automatically a calibrated probability model.

---

## 15.4 Stability

Research should examine where appropriate:

- time stability;
- regime stability;
- universe stability;
- provider stability;
- parameter sensitivity;
- feature drift;
- population drift.

A result that depends on one narrow historical window requires explicit limitation.

---

## 15.5 Risk quality

Relevant dimensions may include:

- drawdown;
- tail loss;
- adverse excursion;
- loss clustering;
- concentration;
- gap risk;
- execution-block risk;
- regime failure.

Risk is not an afterthought appended after return optimization.

---

## 15.6 Operational quality

A model may be statistically attractive but operationally unsuitable because of:

- unavailable data;
- unstable providers;
- excessive latency;
- excessive turnover;
- unrealistic fill assumptions;
- non-reproducible state;
- excessive maintenance complexity.

Operational feasibility is part of research quality.

---

## 15.7 Explainability and trace quality

The project should be able to explain:

- what changed;
- which evidence drove the prediction;
- which gate changed the action;
- which portfolio constraint changed the size;
- which execution rule changed the fill;
- which data and model versions were involved.

A more powerful model requires stronger traceability, not weaker traceability.

---

# 16. Candidate Discovery Research Track

Candidate Discovery is the current first strategic research priority.

Its canonical research structure is:

```text
Point-in-Time Tradable Universe
        ↓
Market / ETF / Theme Context
        ↓
Registered Feature Set
        ↓
Target-Specific Candidate Model
        ↓
Cross-Sectional Normalization / Ranking
        ↓
Eligibility and Quality Gates
        ↓
CandidatePrediction Set
        ↓
Ranking and Economic Evaluation
```

## 16.1 Candidate Discovery is not Entry

The candidate model answers:

> **Which opportunities rank highest for the target?**

The Entry model answers:

> **Should and when should this candidate become actionable?**

A top-ranked candidate may be rejected because of:

- poor execution feasibility;
- excessive gap risk;
- invalid setup location;
- stale data;
- portfolio concentration;
- insufficient reward-to-risk;
- failed strategy-specific confirmation.

Candidate quality and entry quality must be separately measurable.

---

## 16.2 Candidate research must be cross-sectional

Formal Candidate Discovery research should consider where relevant:

- daily or intraday cross-sectional ranking;
- rank stability;
- top-K versus universe outcomes;
- decile or quantile spreads;
- sector-neutral or sector-aware analysis;
- theme concentration;
- liquidity buckets;
- regime conditioning;
- candidate overlap across models;
- turnover of the candidate set.

A model that looks strong on one symbol may fail as a market-wide ranker.

---

## 16.3 Candidate targets must reflect the actual opportunity being studied

For the project's near-term next-session opportunity research, possible labels may include:

```text
next_open_return
next_30m_max_return
next_60m_max_return
next_60m_close_return
next_session_mfe
next_session_mae
hit_0_5pct
hit_1_0pct
cost_adjusted_return
```

These remain target candidates, not automatically the final production target set.

The purpose of listing them is to prevent the project from collapsing a multi-dimensional opportunity into one vague “up probability.”

---

# 17. Entry Research Track

Entry research begins after a candidate opportunity exists.

Its purpose is to determine whether timing or confirmation improves realizable outcomes.

Potential research questions include:

- Does waiting for a pullback improve reward-to-risk?
- Does VWAP reclaim add incremental value?
- Does a Chan buy structure improve entry timing after controlling for trend and location?
- Does a Tuishen-inspired ignition measure improve early participation detection?
- Does a late-session entry outperform next-session open entry for the same candidate target?
- Does confirmation improve quality enough to justify missed opportunities?

Entry research must compare:

```text
Candidate quality before entry policy
```

with:

```text
Realized outcome after entry policy
```

This is necessary to determine whether the Entry model adds value or merely filters away opportunities.

---

# 18. Position Lifecycle Research Track

Position Lifecycle research is stateful.

The canonical review inputs may include:

```text
Current Position State
        +
Original Entry Thesis
        +
Latest Candidate / Continuation Assessment
        +
Market / ETF / Theme Context
        +
Risk Evidence
        +
Exit Evidence
        +
Opportunity Cost
```

and produce a proposal such as:

```text
HOLD
ADD
REDUCE
ROTATE
EXIT
```

## 18.1 Lifecycle actions are separate research objects

The project must not assume:

```text
If BUY was correct,
then HOLD is automatically correct.
```

or:

```text
If HOLD becomes weaker,
then EXIT is automatically optimal.
```

Different actions may require different thresholds, targets and cost assumptions.

---

## 18.2 State transitions must be attributable

A lifecycle experiment should be able to reconstruct:

- previous state;
- new evidence;
- transition rule or model output;
- proposed action;
- portfolio modification;
- realized consequence.

Hidden state transitions cannot become authoritative research evidence.

---

## 18.3 Opportunity cost is a first-class research dimension

A position may remain positive in absolute expectation but still be a weak portfolio choice if a materially better opportunity exists.

Therefore Rotation research may compare:

```text
Expected remaining value of current position
```

against:

```text
Expected value of alternative eligible opportunities
```

subject to costs, risk and concentration.

This does not mean every higher-ranked candidate forces rotation.

It means opportunity cost is explicitly researchable.

---

# 19. Exit Research Track

Exit is independent from Entry.

The project distinguishes at least several exit intents:

```text
Profit-taking
Risk stop
Trend invalidation
Structure break
Distribution / exhaustion
Reduce exposure
Full liquidation
Rotation
Time-based expiry
```

These intents require different evaluation logic.

## 19.1 Fixed time exit is a valid baseline, not a universal rule

For an overnight strategy, the project may test:

```text
Exit at 09:35
Exit at 10:00
Exit at 10:30
```

as deterministic baselines.

But the constitutional target is to determine whether an independent Exit model can improve lifecycle outcomes for the relevant strategy.

---

## 19.2 Exit evaluation must match intent

Examples:

### Profit-taking

May evaluate retained upside versus protected profit.

### Risk stop

May evaluate avoided tail loss, false-stop cost and adverse excursion.

### Trend invalidation

May evaluate future continuation after the invalidation event.

### Rotation

May evaluate net opportunity improvement after switching costs.

The current legacy point-hit-rate diagnostic, which groups different sell-like actions under one forward-close rule, must remain a historical diagnostic rather than a universal Exit promotion contract.

---

# 20. Market Regime, ETF Rotation and Theme Research

## 20.1 Context variables and direct strategies are different roles

Market Regime, ETF Rotation and Theme Rotation may be used as:

- upstream context;
- feature families;
- universe filters;
- strategy gates;
- portfolio risk inputs;
- direct trading strategies.

Each role must be explicit.

A context model should not silently become a direct order engine.

---

## 20.2 Context research asks about conditional Alpha

Examples:

```text
Does feature X work better in broad risk-on regimes?
```

```text
Does candidate quality improve when the mapped ETF shows breadth and leader resonance?
```

```text
Does real ETF share growth add incremental value beyond price momentum?
```

```text
Does theme-stage classification improve holding and exit decisions?
```

These questions treat regime and rotation as explanatory or moderating research objects.

---

## 20.3 Post-hoc regime storytelling is prohibited

The project must not repeatedly split the sample until a favorable regime appears and then present the regime as pre-existing theory.

A new regime definition is a new research object.

It requires:

- explicit construction;
- versioning;
- point-in-time semantics;
- independent evaluation.

---

# 21. Researching MACD, Chan, Tuishen and Other Trading Theories

The project supports qualitative and technical theories as sources of hypotheses.

They must be converted into quantifiable objects.

For each theory-derived construct, research should eventually identify:

```text
Concept definition
Data source
Feature or state definition
Threshold or model
Expected direction
Target
Decision role
Information family
Lineage
Overlap with existing features
Ablation plan
Risk
Invalidation condition
```

Examples include:

### MACD

Possible roles:

- feature;
- trend-state descriptor;
- confirmation gate;
- sizing modifier;
- exit evidence.

Each role must be evaluated separately where it changes behavior.

### Chan Theory

Possible quantifiable objects:

- structure type;
- pivot position;
- buy-point type;
- sell-point type;
- divergence;
- invalidation level.

### Tuishen-inspired research

Possible quantifiable objects:

- force ratio;
- attention feedback;
- sell pressure;
- volume persistence;
- leader ignition;
- exhaustion.

The project must not assume that different names imply independent information.

The Factor Constitution will define the formal lineage and redundancy rules.

---

# 22. Ablation, Attribution and Counterfactual Research

## 22.1 Full-model performance is not enough

The project must be able to ask:

```text
What changed because component X was added?
```

Ablation may examine:

- predictive quality;
- economic outcome;
- drawdown;
- turnover;
- calibration;
- coverage;
- regime stability;
- tail risk.

---

## 22.2 Counterfactual research should compare actual decision paths

Where practical, the project may preserve paired paths such as:

```text
Original decision
vs
Decision without component X
```

or:

```text
Candidate before policy
vs
Candidate after policy
```

The current MACD research infrastructure already contains valuable concepts such as:

- candidate-before-policy;
- candidate-after-policy;
- score effect;
- policy effect;
- interaction effect;
- avoided loss;
- missed profit;
- execution feasibility;
- path-specific holding outcomes.

These are strong research patterns and should be generalized into the future Research System where appropriate.

---

## 22.3 Attribution must include negative side effects

A component may improve one metric while worsening:

- coverage;
- turnover;
- missed opportunity;
- tail risk;
- calibration;
- complexity;
- data dependency.

Attribution must report the trade-off, not only the preferred side.

---

# 23. Research Artifacts

A mature experiment should produce a coherent artifact set.

The exact storage format may vary, but the logical artifacts include:

```text
Research Charter
Target Contract Reference
Experiment Identity / Manifest
Data and Universe References
Configuration Identity
Result Summary
Detailed Metrics
Ablation / Attribution
Failure Cases
Risk and Limitation Review
Reproduction Status
Research Decision Record
```

## 23.1 Human-readable and machine-readable artifacts serve different purposes

Human-readable documents explain:

- why the experiment exists;
- what was learned;
- what failed;
- what decision was made.

Machine-readable artifacts preserve:

- identities;
- configurations;
- metrics;
- hashes;
- status;
- traceable references.

The project should support both.

---

## 23.2 Reports are not runtime configuration

A generated research report may describe an empirical prior.

The runtime model must not read that report opportunistically and treat the latest number as authoritative.

The correct flow is:

```text
Research Result
        ↓
Promotion Decision
        ↓
Versioned Model / Calibration / Prior Artifact
        ↓
Controlled Runtime Loading
```

This rule directly addresses the current risk of hard-coded sample-derived priors and report-driven model behavior.

---

## 23.3 Negative evidence should be searchable

The project should preserve enough information to answer:

```text
Have we already tested this idea?
```

```text
Why was it rejected?
```

```text
Under which data and target definition did it fail?
```

This prevents research memory from depending only on chat history or individual recollection.

---

# 24. Research Decision Rules

At the end of a meaningful research cycle, the project should make an explicit decision.

## 24.1 Reject

Use when the evidence does not support the hypothesis or the economic value is insufficient.

Rejecting a hypothesis does not delete the evidence.

---

## 24.2 Revise

Use when the research question remains valuable but the hypothesis, target, data or implementation requires material correction.

A material revision creates a new hypothesis or version.

---

## 24.3 Continue Research

Use when evidence is insufficient rather than negative.

Examples:

- sample too small;
- required professional data unavailable;
- calibration not yet possible;
- execution assumptions not yet validated.

“Inconclusive” is different from “validated.”

---

## 24.4 Promote Research Status

Use when the component satisfies the evidence required for the next research state.

Promotion must identify:

- source state;
- destination state;
- supporting experiments;
- limitations;
- authority scope;
- monitoring requirements.

---

## 24.5 Quarantine

Use when a previously trusted component becomes suspect because of:

- data integrity issues;
- drift;
- reproducibility failure;
- unexpected behavior;
- provider change;
- regime breakdown;
- implementation regression.

Quarantine reduces authority while investigation proceeds.

---

## 24.6 Retire

Use when a component should no longer influence current decisions.

Retirement preserves:

- history;
- evidence;
- identity;
- reason for retirement.

The research system should be able to learn from retired components.

---

# 25. Research Feedback and Knowledge Accumulation

The Research Operating System must close the loop.

The canonical feedback loop is:

```text
Experiment
    ↓
Evidence
    ↓
Decision
    ↓
Observed consequences
    ↓
Drift / failure / success analysis
    ↓
New question
    ↓
New hypothesis
```

## 25.1 Feedback must not become automatic self-tuning without governance

The system may automate:

- experiment scheduling;
- metric collection;
- drift detection;
- candidate hypothesis suggestions;
- report generation.

It must not automatically rewrite production rules based solely on recent outcomes unless a governed adaptive mechanism has itself been researched and promoted.

---

## 25.2 Research memory must be durable

Important decisions should not exist only in:

- chat history;
- temporary notebooks;
- local terminal output;
- an agent's transient context.

The project should maintain durable research records in the appropriate documentation and artifact layers.

---

# 26. Monitoring, Degradation and Retirement

Research does not end at promotion.

A promoted component may degrade because of:

- market structure changes;
- crowding;
- policy changes;
- provider changes;
- feature drift;
- population drift;
- execution-cost changes;
- regime changes;
- implementation regression.

The monitoring loop is:

```text
Expected behavior
        ↓
Observed behavior
        ↓
Difference / Drift
        ↓
Investigation
        ↓
Continue / Reduce authority / Quarantine / Retrain / Retire
```

The exact statistical and operational thresholds belong to `07-Validation-Constitution.md` and lower-level monitoring specifications.

---

# 27. Agent-Assisted Research

AI agents may assist the Research Framework.

Permitted roles include:

- repository inspection;
- hypothesis drafting;
- literature review;
- feature implementation;
- experiment orchestration;
- test generation;
- result summarization;
- ablation planning;
- anomaly detection;
- documentation;
- code review.

Agents do not receive implicit authority to:

- redefine the Project Vision;
- change a target after seeing results without versioning;
- access sealed data without authorization;
- promote a component because results look attractive;
- bypass data eligibility gates;
- hide failed experiments;
- change production capital authority;
- treat generated explanations as evidence.

If an agent configuration, prompt, model version or generated transformation materially affects a formal research result, that dependency should be identifiable in the experiment context where practical.

---

# 28. Current Legacy Research Assets and Their Research Role

The current repository contains several valuable research assets.

This framework classifies their role without allowing them to define the future platform by inertia.

## 28.1 `MACDExperimentIdentity`

**Value:** explicit result-affecting identity, config hashing, version capture and data-split identity.

**Future role:** preserve the pattern and generalize toward platform-level experiment identity.

**Research action:** **Preserve + Generalize.**

---

## 28.2 MACD factorial and counterfactual research

**Value:** separates score effect, policy effect, interaction effect and decision-path consequences.

**Future role:** model for broader component attribution.

**Research action:** **Preserve + Generalize selectively.**

---

## 28.3 Formal data-source capability audit

**Value:** distinguishes data accessibility from formal PIT eligibility.

**Future role:** precursor to the Data Constitution and dataset promotion gates.

**Research action:** **Preserve as evidence; formalize in `04-Data-Constitution.md`.**

---

## 28.4 `buy_point_quality.py` empirical priors

**Value:** useful subtype taxonomy and evidence that historical outcome statistics can influence model behavior.

**Risk:** current empirical priors are hard-coded from a specific local sample.

**Future role:** taxonomy may remain code; learned priors must become versioned research artifacts estimated on controlled samples.

**Research action:** **Split Taxonomy from Learned Artifact.**

---

## 28.5 `point_hit_rate.py`

**Value:** historical diagnostic for buy/sell-like timing points.

**Current limitation:** one forward-close rule does not represent the objectives of all exit intents.

**Future role:** preserve as a legacy diagnostic, not a universal strategy-promotion metric.

**Research action:** **Preserve + Reclassify.**

---

## 28.6 `DividendTStrategy`

**Value:** interpretable legacy baseline with explicit strategy semantics.

**Future role:** named Legacy strategy baseline and compatibility asset.

**Research action:** **Freeze platform-level expansion; preserve for comparison.**

---

## 28.7 `CoscoTimingEngine`

**Value:** integrated repository of many practical research ideas.

**Risk:** tightly combines multiple feature, scoring, regime, candidate and timing responsibilities.

**Future role:** replayable Legacy research engine and source of extractable hypotheses.

**Research action:** **Freeze expansion + Extract by evidence and ownership.**

---

## 28.8 `backtest.py`

**Value:** extensive encoded A-share execution and state-management knowledge.

**Risk:** research, strategy, portfolio, execution and reporting responsibilities are highly coupled.

**Future role:** behavior-preservation baseline while responsibilities migrate to the V2 Research, Portfolio and Execution systems.

**Research action:** **Characterize + Extract incrementally.**

---

# 29. Current Refoundation Research Constraints

The project is currently in a refoundation stage.

Until explicitly superseded by a new evidence-backed decision, the following research posture remains binding:

```text
Do not treat current free/cached data as formally qualified by default.
Do not access sealed evaluation merely to accelerate iteration.
Do not promote heuristic probabilities as calibrated probabilities.
Do not let current local empirical priors become universal constants.
Do not expand the legacy backtest God Object with new platform responsibilities.
Do not expand CoscoTimingEngine into the V2 Candidate Discovery platform.
Do not interpret implementation completion as production authorization.
Do not claim stable profitability or deterministic returns.
```

Existing temporary experimental constraints such as disabled promotion paths, disabled conflict gates or zero-weight research components remain experiment-specific state and must be changed only through an identified research decision.

The Constitution does not freeze one temporary numeric value forever.

It freezes the requirement that changing such values be explicit, traceable and evidence-backed.

---

# 30. Research Stage Gates

This framework defines lifecycle gates conceptually.

The numeric acceptance criteria belong to `07-Validation-Constitution.md`.

## Gate 0 — Question Gate

Before formal work:

- Is the question clear?
- Does it support a real decision?
- Is it materially different from an existing question?

---

## Gate 1 — Hypothesis Gate

Before formal implementation:

- Is the hypothesis falsifiable?
- Is the expected direction explicit?
- Are failure conditions identified?

---

## Gate 2 — Target Gate

Before model evaluation:

- Is the target explicit?
- Is the horizon explicit?
- Are decision and label times defined?
- Is the metric aligned with the target?

---

## Gate 3 — Data and Universe Gate

Before formal evidence:

- Is the data eligible for the intended claim?
- Is the population identifiable?
- Are PIT requirements understood?
- Are critical gaps visible?

---

## Gate 4 — Baseline Gate

Before complexity is justified:

- Is there a relevant baseline?
- Is the comparison fair?

---

## Gate 5 — Experiment Identity Gate

Before a result becomes authoritative:

- Can the experiment be identified?
- Can result-affecting configuration be reconstructed?

---

## Gate 6 — Evidence Gate

Before promotion consideration:

- Does the result answer the primary question?
- Are sample roles respected?
- Are limitations and failure cases reported?

---

## Gate 7 — Attribution Gate

Before adding complexity to a promoted system:

- Is incremental value measured?
- Are interactions understood sufficiently for the intended use?

---

## Gate 8 — Economic and Execution Gate

Before strategy authority:

- Is the effect economically meaningful?
- Can it survive realistic execution assumptions?
- Are risk and operational costs acceptable for the intended scope?

---

## Gate 9 — Promotion Decision Gate

Before authority changes:

- Is there an explicit Research Decision Record?
- Is the destination state defined?
- Are monitoring requirements defined?

---

## Gate 10 — Monitoring Gate

After promotion:

- Is expected behavior monitored?
- Can degradation reduce authority?
- Can the component be quarantined or retired?

---

# 31. Research Anti-Patterns

The following patterns are prohibited or must be explicitly labeled exploratory.

## 31.1 Target shopping

```text
Try many targets
        ↓
Keep the one with the best result
        ↓
Present it as the original hypothesis
```

---

## 31.2 Metric shopping

```text
Primary metric fails
        ↓
Search secondary metrics
        ↓
Declare success without a new hypothesis
```

---

## 31.3 Split leakage

Using validation, calibration or test outcomes to tune the same model while continuing to claim independence.

---

## 31.4 Sample-derived constants without artifact identity

Embedding empirical priors, thresholds or weights in source code without recording the sample, estimation process and version.

---

## 31.5 Post-hoc regime rescue

Defining a favorable regime only after seeing where the model worked and presenting it as prior theory.

---

## 31.6 Complexity without baseline

Adding models, factors or rules without showing improvement over a relevant simpler comparator.

---

## 31.7 Multi-change experiments without attribution

Changing multiple independent domains and attributing the final outcome to one preferred component.

---

## 31.8 Report-driven runtime behavior

Reading the latest research report or local CSV as an implicit production model artifact.

---

## 31.9 Data downgrade by convenience

Using weaker data than the research claim requires because it is easier to access.

---

## 31.10 Universalizing a convenience sample

Treating results from a small hand-selected universe as evidence for the entire A-share market.

---

## 31.11 Hiding negative experiments

Discarding failed experiments so that the surviving research history appears stronger than the actual process.

---

## 31.12 Agent-induced research drift

Allowing an agent to silently change:

- target;
- sample;
- metric;
- data source;
- gate;
- production authority;

because a different choice is easier to implement.

---

# 32. Research Review Questions

Every major research effort should be reviewable through the following questions.

## Question

- What decision are we trying to improve?
- What exact question are we asking?

## Hypothesis

- What relationship do we expect?
- What evidence would falsify it?

## Target

- What is the event or outcome?
- What is the horizon?
- What is the decision time?
- What is the reference price?

## Data

- Was the information available at the decision time?
- Is the data eligible for the strength of the claim?
- Is provenance known?

## Population

- Which securities or positions does the claim cover?
- Is the universe point-in-time correct?

## Baseline

- What is the simplest relevant comparator?
- Does added complexity outperform it meaningfully?

## Experiment

- What changed?
- What remained fixed?
- Can the result be reproduced?

## Attribution

- What incremental value did the component add?
- What negative side effects appeared?

## Risk

- What are the failure modes?
- What invalidates the conclusion?

## Promotion

- What research state is justified?
- What is not yet justified?

## Monitoring

- What should be observed after promotion?
- What would trigger degradation or quarantine?

---

# 33. Minimum Formal Research Package

Before a component can be treated as a formal research candidate rather than an informal idea, it should have, at minimum:

```text
1. Research Question
2. Falsifiable Hypothesis
3. Target Contract or explicit target reference
4. Population / Universe definition
5. Decision-time convention
6. Data eligibility statement
7. Baseline
8. Experiment Identity
9. Primary evaluation dimensions
10. Risk and invalidation conditions
11. Result summary
12. Research Decision Record
```

More complex or higher-authority components require stronger evidence.

The exact validation requirements are defined in `07-Validation-Constitution.md`.

---

# 34. Relationship to the Remaining Constitution

## `04-Data-Constitution.md`

Will define the exact rules for:

- source provenance;
- PIT correctness;
- bar finalization;
- availability time;
- adjustment;
- universe history;
- data manifests;
- quality gates;
- provider eligibility;
- formal versus exploratory data classes.

The Research Framework consumes those rules.

It does not redefine them.

---

## `05-Factor-Constitution.md`

Will define:

- Feature Registry;
- feature identity;
- lineage;
- source fields;
- factor families;
- normalization;
- redundancy;
- IC / RankIC research;
- incremental value;
- factor promotion.

The Research Framework defines where factor research fits in the lifecycle.

---

## `06-Strategy-Constitution.md`

Will define:

- Candidate versus Strategy boundaries;
- Entry;
- Position Lifecycle;
- Exit;
- strategy registry;
- strategy objectives;
- applicable market and universe;
- signals;
- position management;
- risk rules;
- invalidation;
- strategy state and versioning.

The Research Framework requires those strategy objects to pass through the evidence lifecycle.

---

## `07-Validation-Constitution.md`

Will define the exact validation governance for:

- train / validation / calibration / test roles;
- walk-forward;
- OOS;
- sealed test;
- robustness;
- calibration;
- statistical and economic thresholds;
- promotion gates;
- degradation criteria.

This Research Framework defines the lifecycle.

The Validation Constitution defines the proof standard.

---

## `08-Roadmap.md`

Will sequence implementation and migration priorities.

It must not change the Research Framework merely because one implementation order is convenient.

---

## `09-Glossary.md`

Will freeze canonical terminology such as:

- Alpha;
- Research Program;
- Hypothesis;
- Target;
- Candidate;
- Entry;
- Position Lifecycle;
- Exit;
- Experiment Identity;
- Promotion;
- Degradation;
- Sealed Test.

---

# 35. Constitutional Research Commitments

The project commits to the following research model.

1. **Every serious Alpha claim must be explicit, falsifiable and target-specific.**
2. **Candidate Discovery remains the current first strategic research priority, but the Research Framework remains platform-wide and strategy-neutral.**
3. **An overnight or next-session model is a research program, not the definition of the entire project.**
4. **Position management is a repeated lifecycle decision problem, not a fixed next-morning exit assumption.**
5. **Entry, Hold/Add/Reduce/Rotate, and Exit may require different targets and different evidence.**
6. **ETF and Theme Rotation may act as context, universe support, portfolio input or direct strategy research, but each role must be explicit.**
7. **The target must be defined before the model is judged.**
8. **The population and universe are part of the research claim.**
9. **Data accessibility does not imply formal evidence eligibility.**
10. **Every formal experiment must have reproducible identity.**
11. **Sample-derived priors, thresholds, calibration curves and weights are model artifacts and must obey sample isolation.**
12. **Complexity must be compared with a relevant baseline.**
13. **Incremental value must be measured through ablation, attribution or an equivalent controlled design.**
14. **A favorable full-model result does not prove that every included component adds value.**
15. **Predictive, economic, calibration, risk, stability, execution and operational quality are distinct evaluation dimensions.**
16. **A probability claim requires an explicit event and calibration evidence.**
17. **Research evidence may enter runtime behavior only through explicit, versioned promotion.**
18. **Negative results and retired models remain part of project knowledge.**
19. **Promotion, degradation, quarantine and retirement are explicit research decisions.**
20. **Agents may accelerate research but may not bypass the Constitution, data eligibility, sample isolation, sealed-test governance or promotion authority.**
21. **Legacy research assets are preserved when useful, but Legacy architecture does not define future research semantics.**
22. **The project must become more reproducible, attributable and traceable as research sophistication increases.**

---

# 36. Closing Declaration

The first phase of `market-regime-alpha` accumulated many ideas:

- MACD;
- moving averages;
- Chan structures;
- Tuishen-inspired measures;
- price-volume logic;
- capital-flow proxies;
- buy and sell points;
- state machines;
- backtests;
- dashboards;
- market filters;
- execution constraints.

The next phase must determine which of those ideas contain real, independent and durable information—and under what conditions.

The project therefore moves from:

```text
More rules
```

toward:

```text
Better questions
    ↓
Explicit targets
    ↓
Qualified data
    ↓
Controlled experiments
    ↓
Reproducible evidence
    ↓
Incremental attribution
    ↓
Governed promotion
    ↓
Continuous monitoring
```

The purpose of the Research Framework is not to make every idea succeed.

It is to make it difficult for weak evidence to masquerade as strong Alpha.

The research rule of Market Regime Alpha is therefore:

> **Ask a precise question. Define what would prove or falsify it. Use only information that was actually available. Compare against a baseline. Measure incremental value. Preserve the evidence. Promote only what survives.**
