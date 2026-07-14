# The Constitution of Market Regime Alpha

# Volume VI — Factor Constitution

> **Document:** `docs/constitution/05-Factor-Constitution.md`  
> **Status:** Foundational / Normative  
> **Authority:** Project-wide feature and factor identity, lineage, information-family, transformation, normalization, redundancy, composition, research-use and promotion rules  
> **Applies to:** Raw and derived features, factors, descriptors, context variables, scores, technical indicators, fundamental variables, market/ETF/theme features, capital-flow features, microstructure features, Chan-derived structures, Tuishen-inspired constructs, event/policy features, machine-learning inputs, feature registries, feature materialization, factor research, agents, legacy migration, and future production feature systems  
> **Project:** `market-regime-alpha`  
> **Precedence:** Must remain consistent with `00-Project-Vision.md`, `01-Core-Principles.md`, `02-Architecture-Blueprint.md`, `03-Research-Framework.md`, and `04-Data-Constitution.md`

---

## 0. Purpose

`market-regime-alpha` does not become a stronger Alpha Research Operating System by accumulating more indicators.

It becomes stronger when it can answer, for every piece of information used by a model or decision:

```text
What is this object?
Where did its information come from?
When was that information available?
What transformation produced it?
What does it claim to represent?
What target is it expected to help predict?
What other features contain substantially the same information?
What incremental value does it add?
In which regimes does it work or fail?
What happens if it is removed?
```

The current repository contains many useful research ideas, including:

- moving averages;
- MACD;
- price and return features;
- volume and turnover features;
- VWAP relationships;
- breakout and pullback structures;
- attention proxies;
- certainty-like composite scores;
- memory-like setup scores;
- sell-pressure proxies;
- capital-flow observations and OHLCV-derived flow proxies;
- Chan-derived structural states;
- Tuishen-inspired volume-price constructs;
- market-regime concepts;
- ETF and theme context;
- fundamental and valuation inputs.

The risk is not that these ideas are individually useless.

The risk is that several differently named objects may be transformations of the same underlying information and then be counted repeatedly as if they were independent confirmation.

For example:

```text
Price and Volume
    ↓
Trend
MACD
Moving-Average Position
Breakout Score
Attention Proxy
Certainty Component
Sell-Pressure Proxy
Capital-Flow Proxy
Chan Structure
Tuishen Volume-Price Score
    ↓
Composite Scores
    ↓
Dynamic Weights
    ↓
Final Decision
```

Without lineage and controlled attribution, complexity can create an illusion of evidence.

The purpose of this Factor Constitution is therefore to answer one governing question:

> **How must information be defined, traced, transformed, compared, combined and validated before it is allowed to influence Alpha research or strategy decisions?**

The central rule is:

> **A factor earns authority from explicit information lineage and incremental evidence, not from a persuasive name, intuitive narrative, indicator popularity, or repeated agreement with correlated transformations.**

This document defines:

- the distinction between observations, features, factors, states, scores, probabilities and decisions;
- canonical feature and factor identity;
- feature registry requirements;
- source-field and transformation lineage;
- the distinction between semantic families and source-information families;
- point-in-time feature materialization;
- normalization and cross-sectional processing;
- missingness and default-value governance;
- redundancy and double-counting controls;
- composite-score governance;
- role-specific use of the same information;
- quantification rules for MACD, moving averages, volume-price, Chan and Tuishen-inspired research;
- factor research and promotion requirements;
- legacy-factor migration;
- agent governance for feature creation.

This document intentionally does **not** define:

- detailed provider qualification or dataset eligibility;
- every mathematical formula for every future factor;
- strategy entry, hold, add, reduce, rotate or exit thresholds;
- portfolio weights;
- execution fill rules;
- numeric statistical acceptance thresholds for promotion.

Those responsibilities belong to the Data, Strategy and Validation Constitutions and lower-level specifications.

---

# 1. Constitutional Position of Features and Factors

## 1.1 A named indicator is not automatically a factor

The project distinguishes the following concepts:

```text
Observation
    ↓
Primitive Feature
    ↓
Derived Feature
    ↓
Descriptor / State / Factor Candidate
    ↓
Predictive Factor or Model Input
    ↓
Composite Score / Model Output
    ↓
Strategy Use
    ↓
Portfolio Decision
```

These concepts must not be collapsed.

A moving average is a transformation.

A MACD histogram is a derived feature.

A Chan structure classification is a derived structural descriptor.

A Tuishen-inspired force ratio is a composite research construct.

An attention score built from amount and return is an OHLCV-derived proxy.

A calibrated probability is a model output with a defined event and calibration evidence.

A final trade action belongs to the Strategy System.

The word **factor** must not become a universal synonym for every numeric field.

---

## 1.2 A factor is a research claim about information

Within this project, a factor is best understood as:

> **A defined, versioned and traceable information construct whose relationship to one or more explicit research targets is evaluated under a specified population, decision-time convention and validation protocol.**

A factor may ultimately prove useful as:

- a predictor;
- a ranking input;
- a market-context variable;
- a risk input;
- a regime interaction term;
- a strategy gate input;
- an explanatory diagnostic.

Its role must be explicit.

A factor does not become predictive Alpha merely because it is computable.

---

## 1.3 Feature usefulness and factor authority are different

A feature may be useful for:

- charting;
- diagnostics;
- explaining a state;
- debugging;
- visualization;
- a deterministic risk rule;

without showing independent predictive Alpha.

The project therefore distinguishes:

```text
Useful Feature
        ≠
Predictive Factor
        ≠
Validated Alpha Component
        ≠
Strategy Decision
```

This distinction protects useful engineering or explanatory features from being forced into false predictive claims.

---

# 2. Canonical Information Object Model

The Factor System uses explicit object categories.

## 2.1 Raw Observation

A **Raw Observation** is a canonical data value obtained under the Data Constitution.

Examples:

- close price;
- traded amount;
- ETF shares outstanding;
- observed net inflow field;
- order-book imbalance input;
- published ROE;
- policy publication timestamp;
- industry membership as of a date.

A raw observation is not a factor.

---

## 2.2 Primitive Feature

A **Primitive Feature** is a direct, limited transformation of observations.

Examples:

```text
1-bar return
20-day return
rolling volatility
amount / rolling median amount
price / VWAP - 1
ETF share change
book imbalance
valuation ratio
```

Primitive does not mean unimportant.

It means the transformation has relatively low semantic depth and clear lineage.

---

## 2.3 Derived Feature

A **Derived Feature** combines one or more primitive features or applies a more complex transformation.

Examples:

- MACD DIF / DEA / histogram;
- moving-average slope;
- breakout distance;
- low-volume pullback score;
- Chan pivot state;
- volume-price persistence;
- theme breadth;
- leader resonance;
- market breadth composite.

Derived features must retain lineage to all contributing inputs.

---

## 2.4 Descriptor

A **Descriptor** summarizes an observable condition without necessarily claiming predictive power.

Examples:

```text
TREND_UP
LOW_VOLUME_PULLBACK
CHAN_BUY2
THEME_IGNITION
ETF_STRENGTHENING
HIGH_VOLUME_STALL
```

Descriptors may later become factor inputs.

A descriptive label must not be treated as validated Alpha merely because it sounds economically meaningful.

---

## 2.5 State

A **State** is a persistent or categorical interpretation that may evolve over time.

Examples:

- market regime;
- theme stage;
- trend state;
- lifecycle state;
- setup state.

State ownership must remain explicit.

A state may consume factors.

It must not silently rewrite factor definitions.

---

## 2.6 Factor Candidate

A **Factor Candidate** is a registered feature or construct for which the project has an explicit predictive or explanatory hypothesis.

It requires at least:

```text
Factor Identity
Hypothesis
Target Scope
Expected Direction or Relationship
Population
Decision-Time Convention
Lineage
Research Status
```

---

## 2.7 Predictive Factor

A **Predictive Factor** is a factor candidate that has obtained evidence of a stable relationship with a defined target under the relevant validation design.

Predictive authority is always scoped.

For example:

```text
Factor X may be useful
for liquid A-shares
at 14:55
for next-session MFE
in risk-on regimes
```

This does not imply:

```text
Factor X works for all A-shares,
all decision times,
all targets,
and all regimes.
```

---

## 2.8 Composite Score

A **Composite Score** combines several features, factors or model outputs.

Examples include:

- technical score;
- opportunity score;
- risk score;
- attention proxy score;
- force ratio;
- candidate utility score.

A composite score is itself a versioned research object.

It must declare:

- its components;
- component identities;
- weights or combination rule;
- missingness policy;
- intended semantic meaning;
- target or decision role;
- overlap risks.

A composite score bounded to `[0, 100]` is not automatically a probability.

---

## 2.9 Gate

A **Gate** is a decision rule that permits, blocks or downgrades downstream behavior.

Examples:

```text
Data Quality Gate
Liquidity Gate
Trend Confirmation Gate
Risk Gate
Entry Eligibility Gate
```

A factor may be an input to a gate.

The gate itself belongs to the system that owns the decision being gated.

For example:

```text
MACD feature
    ↓
Entry Policy Gate
```

The MACD feature does not become the owner of Entry.

---

## 2.10 Model Output

A **Model Output** may include:

- raw model score;
- expected return;
- rank score;
- calibrated probability;
- expected MFE;
- expected MAE.

A model output must not be registered as a primitive factor merely to hide model complexity.

Its identity includes the model artifact and training context.

---

# 3. Two Independent Family Systems

A major constitutional requirement is the separation of:

```text
Semantic Family
```

from:

```text
Source-Information Family
```

These are not the same thing.

---

## 3.1 Semantic Family

The **Semantic Family** describes what a feature is intended to represent.

Examples may include:

```text
Market Regime
ETF / Industry / Theme Rotation
Trend
Momentum
Volatility
Liquidity
Price-Volume Structure
Capital Flow
Microstructure
Structure / Pattern
Fundamental Quality
Valuation
Event / Policy
Risk
Relative Strength
Breadth
Crowding / Exhaustion
```

Semantic families are useful for research interpretation and system organization.

They do **not** prove information independence.

---

## 3.2 Source-Information Family

The **Source-Information Family** describes the underlying information actually used to construct the feature.

Examples may include:

```text
PRICE_ONLY
OHLCV
TRADE_AMOUNT
OBSERVED_FUND_FLOW
TRADE_PRINTS
ORDER_BOOK_L1
ORDER_BOOK_L2
ETF_SHARES
SECURITY_MASTER
FUNDAMENTAL_REPORTED
VALUATION_MARKET_DATA
EVENT_DOCUMENT
POLICY_DOCUMENT
INDUSTRY_MEMBERSHIP
THEME_MEMBERSHIP
INDEX_CONSTITUENTS
POSITION_STATE
PORTFOLIO_STATE
```

A feature may depend on multiple source-information families.

This dimension is essential for double-counting control.

---

## 3.3 Why both are required

Consider the following:

### MACD

```text
Semantic Family: Trend / Momentum
Source-Information Family: PRICE_ONLY
```

### Moving-average slope

```text
Semantic Family: Trend
Source-Information Family: PRICE_ONLY
```

### Chan structure

```text
Semantic Family: Structure / Pattern
Source-Information Family: PRICE_ONLY or OHLCV
```

### Tuishen-inspired volume-price structure

```text
Semantic Family: Price-Volume Structure
Source-Information Family: OHLCV
```

### Attention proxy built from return and amount

```text
Semantic Family: Attention Proxy
Source-Information Family: OHLCV / TRADE_AMOUNT
```

### Observed ETF share change

```text
Semantic Family: Capital Flow / Participation
Source-Information Family: ETF_SHARES
```

These features may have different semantic interpretations while sharing substantial source information.

Therefore:

> **Semantic diversity must never be mistaken for information independence.**

---

# 4. Feature and Factor Identity

Every formal feature or factor must have stable identity.

A recommended logical identity includes, as applicable:

```text
feature_id
feature_name
feature_version
object_type
semantic_family
source_information_families
entity_scope
frequency
lookback
input_dependencies
source_fields
availability_rule
finalization_requirement
transformation
parameters
normalization
cross_sectional_scope
missingness_policy
expected_direction
supported_targets
allowed_roles
owner
status
```

The exact schema belongs to `docs/specs/Feature-Registry.md` or equivalent future specifications.

The constitutional rule is that result-affecting semantic changes require a new identity or version.

---

## 4.1 Definition Identity and Materialization Identity are different

The project distinguishes:

```text
Feature Definition
```

from:

```text
Feature Materialization
```

A definition may be:

```text
20-day return = close_t / close_t-20 - 1
```

A materialization additionally depends on:

```text
Dataset Identity
Universe Identity
As-Of Time
Adjustment View
Calendar
Feature Version
Parameters
Code Revision
```

Therefore the same feature definition can produce different materializations on different datasets.

The materialization identity must be traceable for formal research.

---

## 4.2 Parameter changes may change feature identity

The following are not necessarily the same factor:

```text
5-day momentum
20-day momentum
60-day momentum
```

Likewise:

```text
MACD(12,26,9)
```

and:

```text
MACD(8,17,6)
```

may require distinct parameterized identities.

The project must not silently tune a parameter while preserving the appearance of one unchanged factor.

---

## 4.3 Horizon-specific meaning must remain explicit

A feature may have different predictive relationships across targets and horizons.

The feature definition may remain the same.

The **factor claim** changes.

For example:

```text
Volume expansion
```

may be positively related to:

```text
next-bar continuation
```

and negatively related to:

```text
5-session forward return
```

under certain conditions.

Therefore the project distinguishes:

```text
Feature Identity
```

from:

```text
Factor Claim Identity
```

---

# 5. Feature Registry

The project shall establish a canonical Feature Registry.

The registry is the authoritative catalog of formal feature definitions and factor candidates.

It should make it possible to answer:

```text
Does this feature already exist?
What does it mean?
Which inputs does it use?
Which source-information families does it depend on?
Which version is active?
Which targets has it been tested against?
What is its current research status?
Which features substantially overlap with it?
Which experiments used it?
```

---

## 5.1 Registry before formal authority

Exploratory code may create temporary features.

Before a feature influences formal research authority, it must obtain a registered identity.

The project rejects:

```text
Anonymous column added in notebook
    ↓
Used in model
    ↓
Model promoted
```

without a recoverable feature definition.

---

## 5.2 One canonical definition per feature identity

A feature ID must not map to multiple formulas in different modules.

If implementation variants are intentionally supported, they require:

- separate versions;
- separate identities; or
- an explicitly parameterized contract.

---

## 5.3 Registry status is not performance authority

Registration means:

```text
The feature is known and defined.
```

It does not mean:

```text
The feature is validated Alpha.
```

Research status must remain separate.

---

# 6. Lineage Is Part of Factor Identity

Every formal factor must preserve a lineage graph.

The conceptual lineage is:

```text
Source Artifact
    ↓
Canonical Data Field
    ↓
Primitive Feature
    ↓
Derived Feature
    ↓
Composite / Factor
    ↓
Model / Strategy Use
```

A factor must not exist only as a final number.

---

## 6.1 Minimum lineage

At minimum, a formal feature should identify:

```text
Source Dataset(s)
Source Field(s)
Input Feature Dependencies
Lookback Window
Frequency
Availability Rule
Transformation
Normalization
Version
```

---

## 6.2 Dependency graphs must be acyclic

Formal feature dependencies should form a directed acyclic graph for a given materialization.

A feature must not indirectly depend on itself through hidden composite scores.

Circular dependency can create unstable semantics and non-reproducible state.

---

## 6.3 Hidden lineage is prohibited

Examples of hidden lineage include:

- a `fundamental_score` that secretly contains moving-average information;
- a `capital_flow_score` that silently falls back from observed flow to OHLCV without changing identity;
- an `attention_score` that appears independent but is built from the same return and amount already used elsewhere;
- a probability-like output that embeds a historical prior without recording the prior artifact.

---

# 7. Point-in-Time Feature Materialization

The Data Constitution governs whether information is historically available.

The Factor Constitution governs how that information is transformed without creating new leakage.

The canonical rule is:

> **A feature value at decision time T may depend only on inputs that were eligible and available under the feature contract at T.**

---

## 7.1 Window closure is explicit

A rolling feature must define:

- window length;
- interval semantics;
- whether the current bar is included;
- whether the current bar is finalized;
- calendar behavior;
- missing-bar behavior.

For example:

```text
20-bar moving average
```

is incomplete as a formal definition unless the project also knows whether the current decision bar is included and final.

---

## 7.2 Cross-sectional normalization must be PIT-correct

A cross-sectional z-score, rank or percentile at time T must use the eligible cross-section at T.

The project must not use:

- today's surviving universe;
- future eligibility information;
- full-sample mean and variance;
- future winsorization thresholds;

unless the research design explicitly permits an in-sample exploratory calculation and labels it honestly.

---

## 7.3 Learned transformations are model artifacts

The following may be learned from data:

- normalization parameters;
- bin boundaries;
- winsorization thresholds;
- monotonic transforms;
- target encoding;
- PCA components;
- clustering assignments;
- calibration maps;
- empirical priors.

If learned from outcomes or a sample distribution, they become versioned research artifacts and must obey sample isolation.

---

# 8. Normalization Constitution

Normalization changes feature meaning and must be explicit.

Possible methods include:

```text
Raw Value
Ratio
Log Transform
Z-Score
Robust Z-Score
Percentile Rank
Cross-Sectional Rank
Time-Series Rank
Winsorized Value
Industry-Neutralized Value
Market-Neutralized Value
```

No method is universally correct.

---

## 8.1 Raw and normalized forms are distinct objects

For example:

```text
20-day return
```

and:

```text
cross-sectional percentile of 20-day return
```

are different feature definitions.

They may share a parent lineage.

They must not share an ambiguous field name.

---

## 8.2 Cross-sectional and time-series normalization are different

A stock may rank highly relative to other stocks while remaining weak relative to its own history.

Therefore:

```text
Cross-Sectional Rank
        ≠
Time-Series Z-Score
```

Their intended role must be explicit.

---

## 8.3 Neutralization must have a hypothesis

Industry, size, beta or market neutralization must not be applied automatically.

Neutralization changes the information claim.

The project must ask:

```text
Are we trying to remove an unwanted exposure?
Or are we accidentally removing the Alpha itself?
```

A neutralized factor is a distinct research object from its raw parent.

---

## 8.4 Full-sample normalization leakage is prohibited

A historical experiment must not compute normalization parameters using future observations unless the method is explicitly designed as a non-causal diagnostic.

Formal predictive research requires causal or train-fitted transformations.

---

# 9. Missingness and Default Values

Missingness is part of factor semantics.

The project must distinguish:

```text
Observed Neutral Value
Missing Value
Unavailable Value
Not Applicable
Stale Value
Insufficient History
Provider Failure
```

These states are not interchangeable.

---

## 9.1 Missing does not automatically mean neutral

The following pattern is prohibited for formal research unless explicitly justified:

```text
Missing feature
    ↓
Set to 50
    ↓
Continue with unchanged confidence
```

A neutral default can create false certainty.

---

## 9.2 Missingness may itself contain information

A missingness indicator may be researched as a separate feature when economically or operationally meaningful.

But it must not be introduced accidentally through data defects.

---

## 9.3 Insufficient history must be explicit

A factor requiring 60 sessions of history must not silently compute on 8 sessions and preserve the same identity.

Valid responses include:

- unavailable;
- reduced-scope alternate feature with a different identity;
- explicit minimum-history branch;
- exclusion from the eligible universe.

---

# 10. Information Redundancy and Double Counting

The project adopts a strict position:

> **Multiple transformations of the same information may all be useful, but they are not independent evidence merely because they have different names.**

Redundancy review operates at multiple levels.

---

## 10.1 Level 1 — Lineage redundancy

Before statistical analysis, inspect whether features share:

- source fields;
- lookback windows;
- transformations;
- intermediate dependencies;
- semantic parents.

Examples:

```text
MACD
MA slope
price above MA20
20-day momentum
```

all draw heavily from price history.

---

## 10.2 Level 2 — Statistical redundancy

Where appropriate, the project may evaluate:

- Pearson correlation;
- Spearman correlation;
- rank correlation stability;
- mutual information or nonlinear dependence;
- VIF or equivalent collinearity diagnostics;
- feature clustering;
- conditional dependence;
- similarity of prediction errors.

No single statistic is the universal redundancy test.

---

## 10.3 Level 3 — Incremental predictive value

A feature can be correlated with another feature and still add value.

The decisive question is:

```text
What changes when this feature is added or removed?
```

Relevant methods may include:

- incremental IC;
- incremental RankIC;
- controlled ablation;
- nested-model comparison;
- permutation or grouped importance;
- out-of-sample contribution analysis;
- counterfactual decision-path analysis.

---

## 10.4 Level 4 — Incremental economic value

Even predictive improvement may fail to improve trading outcomes after:

- turnover;
- slippage;
- capacity;
- concentration;
- delayed execution;
- false positives;
- tail risk.

Factor authority therefore requires more than a favorable standalone correlation.

---

## 10.5 Agreement is not multiplication of confidence

The project rejects:

```text
MACD bullish
+ MA bullish
+ breakout bullish
+ Chan bullish
+ attention high
= five independent confirmations
```

when these objects largely derive from the same recent price-volume path.

Agreement may still be useful.

It must be interpreted as:

```text
Multiple views of partially shared information
```

unless independence or incremental contribution has been demonstrated.

---

# 11. Information Family Budgets

The project may use multiple factors from one source-information family.

However, model and composite design must make family concentration visible.

A future specification may represent, for each model or score:

```text
Contribution by Feature
Contribution by Semantic Family
Contribution by Source-Information Family
```

The constitutional purpose is to detect situations such as:

```text
80% of apparent evidence
comes from transformed OHLCV
but is presented as
trend + attention + flow + structure + certainty
```

The Constitution does not impose a universal numeric family cap.

It requires visibility, attribution and evidence for concentrated reuse.

---

# 12. Composite Score Constitution

Composite scores are allowed.

Untraceable composites are not.

---

## 12.1 Every component has identity

A composite must not combine anonymous values.

Each component should reference a registered feature, factor, model output or explicitly versioned constant.

---

## 12.2 Weights are part of the model

Weights may be:

- fixed by hypothesis;
- estimated from data;
- regime-dependent;
- dynamically generated.

In every case, the weight rule is result-affecting model logic.

It must be versioned and researchable.

---

## 12.3 Dynamic weighting does not remove the need for attribution

A dynamic-weight engine can amplify hidden double counting.

Therefore the project must be able to reconstruct:

```text
Which components were active?
What were their weights?
Why did weights change?
Which source-information families gained authority?
What changed in the output because of the dynamic weighting?
```

---

## 12.4 Composite labels must match semantics

A score named:

```text
fundamental_score
```

must not contain hidden price-trend adjustments.

A score named:

```text
capital_flow_score
```

must not silently alternate between observed flow and OHLCV proxy under one unchanged identity.

A score named:

```text
certainty
```

must not be treated as a probability unless it meets the Probability Constitution requirements from higher-level documents.

---

# 13. Feature Role Constitution

The same feature may be tested in different decision roles.

The role is part of the research claim.

Canonical roles may include:

```text
DESCRIPTOR
PREDICTOR
RANKING_INPUT
CONTEXT
INTERACTION_TERM
GATE_INPUT
RISK_INPUT
SIZING_INPUT
EXIT_EVIDENCE
DIAGNOSTIC
```

A feature's success in one role does not authorize every other role.

---

## 13.1 Dual use must be explicit

The current MACD research already demonstrates an important pattern:

```text
MACD as Technical Score Input
```

and:

```text
MACD as Policy Gate
```

are separate behavioral interventions.

If both are used, the project should preserve the ability to compare:

```text
Baseline
Score Only
Policy Only
Full
```

and estimate interaction effects.

This is a preferred pattern for any factor used in multiple roles.

---

## 13.2 A feature must not silently become a decision owner

For example:

```text
Chan sell point
```

may be:

- a structural descriptor;
- an exit-risk input;
- a hard strategy gate;

but these are different layers.

The feature does not own the final exit decision unless the Strategy Constitution explicitly defines a strategy whose policy delegates that authority.

---

# 14. Factor Research Lifecycle

A factor follows the Research Framework.

A typical lifecycle is:

```text
Concept
    ↓
Registered Hypothesis
    ↓
Feature Definition
    ↓
Exploratory Materialization
    ↓
Factor Candidate
    ↓
Baseline Comparison
    ↓
Standalone Analysis
    ↓
Incremental Analysis
    ↓
Regime / Population Analysis
    ↓
Economic and Operational Review
    ↓
Promotion / Revision / Rejection
    ↓
Monitoring / Degradation / Retirement
```

The exact proof thresholds belong to `07-Validation-Constitution.md`.

---

## 14.1 Standalone strength is not sufficient

A feature may show strong standalone IC and add no value to the existing model.

A weak standalone feature may add value through interaction.

Therefore both standalone and conditional contribution matter.

---

## 14.2 Research status is explicit

A factor may have states such as:

```text
IDEA
REGISTERED
EXPLORATORY
RESEARCH_CANDIDATE
VALIDATED_FOR_SCOPE
SHADOW
ACTIVE_FOR_SCOPE
DEGRADED
QUARANTINED
RETIRED
```

A factor may be active for one target and exploratory for another.

---

# 15. Factor Evaluation Dimensions

The project evaluates factor quality across multiple dimensions.

No single metric is sufficient.

Possible dimensions include:

```text
Predictive Direction
IC / RankIC
Top-K Separation
Monotonicity
Calibration Contribution
Incremental Value
Regime Stability
Population Stability
Turnover Impact
Capacity
Tail Risk
Missingness Sensitivity
Data Dependency
Operational Cost
Interpretability
```

The exact required metrics depend on the research object and belong to future research designs and the Validation Constitution.

---

## 15.1 IC and RankIC are tools, not universal proof

IC and RankIC are especially useful for cross-sectional factor research.

They do not automatically answer:

- whether a factor survives transaction costs;
- whether top-K selection is stable;
- whether the effect is concentrated in one regime;
- whether the factor is redundant with an existing feature;
- whether the signal can be executed.

---

## 15.2 Direction must be stable or explicitly conditional

A factor whose sign flips across regimes may still be useful.

But the relationship must be modeled honestly.

The project distinguishes:

```text
Unstable Noise
```

from:

```text
Conditional Relationship
```

A post-hoc regime split is not automatically evidence of a conditional factor.

---

# 16. Cross-Sectional Factor Constitution

Candidate Discovery is the current first strategic priority.

Therefore cross-sectional factor research is a first-class capability.

A cross-sectional feature or factor must define:

```text
Decision Time
PIT Universe
Eligibility Rules
Cross-Sectional Population
Normalization Scope
Grouping / Neutralization
Ranking Direction
Missingness Treatment
Tie Handling
Top-K or Quantile Evaluation Scope
```

---

## 16.1 Comparable values are required

A factor used to rank thousands of securities must have comparable semantics across the population.

A stock-specific heuristic calibrated only to one symbol is not automatically cross-sectionally comparable.

---

## 16.2 Symbol-specific thresholds require justification

Per-symbol normalization or thresholds may be appropriate.

But the project must distinguish:

```text
Cross-Sectional Opportunity Ranking
```

from:

```text
Within-Symbol Timing State
```

Running a within-symbol score across all stocks does not automatically create a valid market-wide ranking factor.

---

## 16.3 Universe filters are not automatically Alpha factors

Liquidity, listing age, ST status or data completeness may determine eligibility.

They may also be researched as predictive variables.

The two roles must remain separate.

---

# 17. Time-Series Feature Constitution

Time-series features describe a security or market relative to its own history.

Examples:

- moving-average slope;
- drawdown;
- volatility regime;
- MACD state;
- breakout persistence;
- rolling volume expansion.

A time-series feature must define:

- lookback;
- frequency;
- warm-up;
- calendar behavior;
- current-bar inclusion;
- adjustment view;
- missing-bar behavior.

Time-series predictive evidence does not automatically imply cross-sectional ranking value.

---

# 18. Market Regime, ETF and Theme Features

Market Regime, ETF Rotation and Theme Rotation may produce:

- descriptors;
- context states;
- factor inputs;
- interaction terms;
- universe filters;
- direct strategy signals.

Each role must be explicit.

---

## 18.1 Context factors are not universal gates by default

For example:

```text
ETF relative strength
```

may improve Candidate Discovery as a contextual feature.

That does not automatically justify:

```text
Reject all candidates when ETF score < X
```

A hard gate is a separate strategy hypothesis.

---

## 18.2 Theme-stage labels require measurable definitions

Terms such as:

```text
Ignition
Diffusion
Acceleration
Climax
Divergence
Retreat
```

must eventually map to explicit inputs, state-transition rules or models.

A narrative label is not a factor until its construction and target relationship are testable.

---

## 18.3 ETF price strength is not ETF flow

The project must distinguish:

```text
ETF Price Momentum
ETF Relative Strength
ETF Turnover
ETF Share Change
ETF AUM Change
Creation / Redemption
Observed Flow
```

These may interact.

They are not interchangeable.

---

# 19. Capital-Flow Factor Constitution

Capital-flow semantics require strict classification.

The project distinguishes at least:

```text
OBSERVED_VENDOR_FLOW
TRADE_DERIVED_FLOW
ORDER_BOOK_DERIVED_FLOW
ETF_SHARE_DERIVED_FLOW
OHLCV_FLOW_PROXY
HEURISTIC_FLOW_SCORE
```

---

## 19.1 Source class is part of factor identity

The current legacy capital-flow implementation contains a useful idea: it records whether the source is real money-flow data or an OHLCV proxy.

The future Factor System strengthens this rule:

> **A factor must not silently switch source-information class while preserving one unchanged identity.**

For example:

```text
capital_flow_real_v1
```

and:

```text
capital_flow_ohlcv_proxy_v1
```

may share a higher-level semantic family.

They are not the same factor materialization.

---

## 19.2 Proxy quality must remain visible

A proxy may be useful.

The project should preserve:

- source type;
- proxy definition;
- confidence or eligibility state where appropriate;
- comparison against observed flow when available.

The correct research question is often:

```text
Does observed flow add incremental value beyond the OHLCV proxy?
```

---

# 20. Technical Indicator Constitution

Technical indicators are permitted as research objects.

They receive no exemption from lineage, redundancy or validation requirements.

---

## 20.1 Moving Averages

A moving-average feature must define:

```text
Price Field
Window
Frequency
Adjustment View
Current-Bar Inclusion
Slope Definition
Normalization
Decision Role
```

Possible distinct features include:

- price / MA20;
- MA5 / MA20;
- MA20 slope;
- distance from MA20 in volatility units.

They must not share one ambiguous `ma_score` identity.

---

## 20.2 MACD

MACD must be decomposable into explicit objects such as:

```text
DIF
DEA
Histogram
Histogram Delta
Cross Type
Cross Age
Zero-Axis State
Histogram Trend
```

A later composite MACD score is a separate research object.

MACD may be studied as:

- descriptor;
- predictor;
- confirmation input;
- gate input;
- sizing input;
- exit evidence.

Each behavioral use must be attributable.

The current project infrastructure for comparing score-only, policy-only and full use is a valuable research pattern to preserve and generalize.

---

## 20.3 Trend and momentum overlap with MACD

MACD, moving averages, returns and trend states frequently share the same price path.

The project must therefore evaluate:

- lineage overlap;
- statistical dependence;
- incremental contribution;
- role interaction.

It must not treat agreement among them as automatic independent confirmation.

---

# 21. Volume and Price-Volume Constitution

Volume-price research is a major project capability.

It must remain explicit about what it observes.

Possible primitive inputs include:

- volume;
- amount;
- return;
- range;
- close location;
- VWAP;
- volume ratio;
- amount ratio.

Possible derived structures include:

- volume breakout;
- low-volume pullback;
- high-volume stall;
- price-up-volume-down;
- VWAP support;
- persistence.

These are allowed as separate research objects.

Their shared OHLCV lineage must remain visible.

---

## 21.1 Subscores are not independent votes by default

The current Tuishen-inspired volume-price implementation computes several subscores from overlapping recent bars.

That is useful for interpretable decomposition.

It does not imply that:

```text
Volume Breakout
+ VWAP Support
+ Persistence
```

are three independent sources of evidence.

The composite must be evaluated as a model and through ablation where useful.

---

## 21.2 VWAP semantics must be explicit

A VWAP feature must define:

- source amount and volume fields;
- time window;
- session reset behavior;
- cumulative or rolling method;
- data eligibility;
- whether the value is provider-observed or reconstructed.

---

# 22. Chan-Derived Feature Constitution

Chan Theory may inspire structural features.

The project does not treat the theory as self-validating.

Possible quantifiable objects include:

```text
Pivot / Zhongshu State
Trend Direction
Buy Point Type
Sell Point Type
Divergence Type
Structure Break
Invalidation Level
Distance to Pivot
Structure Age
```

Each object must define:

- deterministic or model-based construction;
- data frequency;
- lookback or segmentation rules;
- confirmation timing;
- repainting or revision behavior;
- source-information family;
- expected research role.

---

## 22.1 Structural semantics do not imply independent information

A Chan feature may belong to the semantic family:

```text
STRUCTURE
```

while its source-information family remains:

```text
PRICE_ONLY
```

or:

```text
OHLCV
```

Therefore it may overlap materially with trend, momentum and breakout features.

---

## 22.2 Confirmation timing is mandatory

A structure that is only identifiable after future bars confirm it must expose the confirmation time.

The system must not label the structure at an earlier timestamp as if it had been known then.

---

# 23. Tuishen-Inspired Feature Constitution

Tuishen-inspired concepts are treated as hypothesis generators and quantifiable constructs.

Possible objects include:

```text
Attention Proxy
Force Ratio
Memory / Setup Similarity
Sell-Pressure Proxy
Volume Persistence
Leader Ignition
Exhaustion
Feedback State
```

Each construct must be decomposed into measurable inputs and explicit semantics.

---

## 23.1 “Attention” must declare what is observed

The current legacy `attention.py` estimates attention from:

- return;
- amount;
- volume;
- benchmark strength where available.

This is appropriately interpreted as:

```text
OHLCV-derived Attention Proxy
```

not direct observation of investor attention or intention.

Future data such as search trends, news attention, social activity or order flow would create different source-information families.

---

## 23.2 “Certainty” must not masquerade as probability

The current legacy certainty construct combines:

- fundamental input;
- valuation input;
- price shape;
- attention proxy;
- inverse sell-pressure proxy;
- memory score.

This is a mixed-family composite score.

It may remain useful as a Legacy research construct.

It must not be interpreted as a calibrated probability unless separately trained and validated as one.

Future migration should make its component lineage and semantic role explicit.

---

## 23.3 “Sell pressure” must declare proxy status

The current legacy sell-pressure estimator uses recent price and amount structure to estimate:

- resistance pressure;
- profit-taking proxy;
- trapped-position proxy;
- volume-stalling pressure.

These are OHLCV-derived structural proxies.

They are not direct observation of all holders' cost bases or actual future sell orders.

The naming and research reports must preserve that distinction.

---

## 23.4 Memory-like features require sample isolation

A memory or similarity construct may use:

- deterministic current setup classification;
- nearest historical states;
- empirical historical outcomes;
- learned embeddings.

If historical outcomes influence the current score, the learned memory artifact becomes part of the model and must obey sample isolation.

---

# 24. Fundamental and Valuation Feature Constitution

Fundamental and valuation information must remain semantically clean.

Examples of fundamental families include:

- profitability;
- balance-sheet quality;
- cash-flow quality;
- growth;
- dividend sustainability;
- cyclicality;
- revisions.

Valuation families may include:

- PE;
- PB;
- EV-related ratios;
- dividend yield;
- relative valuation.

---

## 24.1 Technical information must not be hidden inside fundamental identity

The current legacy `_dynamic_fundamental_score()` modifies a fundamental-named score using:

- moving averages;
- recent return;
- drawdown;
- recovery.

This is a known semantic contamination.

The future system must separate:

```text
Fundamental Feature
```

from:

```text
Technical / Trend Context
```

A strategy may combine them later through an explicit composite or model.

---

## 24.2 Publication time matters

Fundamental features must use values available under the Data Constitution at the historical decision time.

A restated or later-published value must not be treated as originally known.

---

# 25. Event and Policy Feature Constitution

Policy and event research is a first-class project objective.

Possible objects include:

- event type;
- policy category;
- affected industry;
- affected theme;
- affected security set;
- sentiment or direction classification;
- novelty;
- policy intensity;
- expected time horizon.

These may be manually defined, rule-derived, vendor-provided or model/LLM-derived.

---

## 25.1 Derived event labels are model outputs

An LLM-generated label is not original source truth.

Its identity must include, where relevant:

- source document identity;
- model identity;
- prompt or extraction contract version;
- classification schema;
- processing time;
- review status.

---

## 25.2 Event mapping must be time-aware

A policy feature must distinguish:

```text
Published At
Available At
Effective At
Decision Time
```

A later retrospective interpretation must not be backfilled into the original decision time without explicit versioning.

---

# 26. Market, Position and Portfolio Context

Not every contextual variable is an Alpha factor.

The project distinguishes:

```text
Market Feature
Security Feature
Position State
Portfolio State
Execution State
```

For example:

- current holding cost;
- sellable shares;
- portfolio concentration;
- available cash;

may affect a decision.

They are not automatically market Alpha factors.

They belong to strategy, portfolio or execution context and must not be mixed into factor research without explicit purpose.

---

# 27. Feature Interaction Constitution

Interactions are allowed.

An interaction can represent genuine conditional Alpha.

Examples:

```text
Momentum × Market Regime
ETF Strength × Stock Relative Strength
Volume Expansion × Breakout State
Observed Flow × Theme Breadth
```

An interaction is a new research object.

It must not be created merely to rescue weak standalone features after inspecting outcomes.

---

## 27.1 Interaction terms require parent identities

The lineage of an interaction includes all parent factors.

Its source-information concentration must remain visible.

---

## 27.2 Regime conditioning is not free complexity

A factor may work only in certain regimes.

The project must distinguish:

```text
Predefined Conditional Hypothesis
```

from:

```text
Post-Hoc Partition Search
```

The latter requires a new research hypothesis and independent evaluation.

---

# 28. Feature Selection Constitution

Feature selection is part of the model-development process.

Methods may include:

- domain-driven inclusion;
- univariate screening;
- correlation filtering;
- grouped redundancy control;
- regularization;
- tree-based selection;
- stability selection;
- model-specific importance.

No method receives automatic authority.

---

## 28.1 Selection must obey sample isolation

A feature selected using test or sealed-test outcomes has contaminated those samples.

---

## 28.2 Selection must preserve feature groups where needed

Feature-level selection can hide family-level concentration.

The project should be able to evaluate selection at:

- individual feature level;
- semantic family level;
- source-information family level.

---

# 29. Feature Materialization and Reproducibility

Formal feature computation must be reproducible.

A materialized feature set should be traceable to:

```text
Feature Definition Versions
Dataset Identity
Universe Identity
Decision-Time Convention
Materialization Time
Code Revision
Configuration
Dependency Versions
```

---

## 29.1 Cached features require identity

A cache filename is not sufficient identity.

Changing input data, feature version or materialization policy must not silently reuse stale cached values.

---

## 29.2 Offline and online semantics must converge

Historical research and future live inference may use different implementations for performance reasons.

They must preserve the same feature contract.

Where practical, conformance tests should compare:

```text
Historical Materialization
vs
Incremental / Online Materialization
```

for equivalent inputs.

---

# 30. Feature Quality Gates

A feature can fail before predictive evaluation.

Potential quality failures include:

- unavailable required input;
- stale input;
- insufficient lookback;
- invalid timestamp alignment;
- non-finite values;
- impossible range;
- inconsistent units;
- excessive missingness;
- dependency-version mismatch;
- use of ineligible data;
- feature-definition drift.

Critical failures should fail closed or downgrade research eligibility according to the relevant contract.

---

# 31. Factor Promotion Requirements

A factor is not promoted because it has an attractive chart.

Before a factor gains formal authority for a scope, it should have evidence addressing, as applicable:

```text
Definition Correctness
Data Eligibility
Point-in-Time Correctness
Lineage Completeness
Standalone Relationship
Incremental Relationship
Redundancy
Regime / Population Stability
Economic Relevance
Operational Feasibility
Reproducibility
Risk and Failure Modes
```

Numeric thresholds and exact proof standards belong to `07-Validation-Constitution.md`.

---

## 31.1 Promotion is scope-specific

A factor can be:

```text
VALIDATED_FOR_SCOPE
```

where scope includes:

- target;
- horizon;
- population;
- decision time;
- role;
- data class.

It must not silently generalize beyond that scope.

---

## 31.2 Factor retirement preserves knowledge

A retired factor should retain:

- definition;
- prior evidence;
- reason for retirement;
- affected models;
- replacement where applicable.

Negative evidence remains part of the research memory.

---

# 32. Current Legacy Factor Audit

This Constitution is informed by the current repository.

The following interpretations are binding until superseded by more specific design or specification documents.

---

## 32.1 `scoring.py`

**Current value:** explicit weighted scoring and technical-score diagnostics.  
**Risk:** F/R/T and total score can hide heterogeneous feature families and shared information.  
**Constitutional interpretation:** Legacy composite-score baseline, not the universal Factor System.  
**Required evolution:** register components, expose lineage, separate semantic families, preserve weight identity and evaluate incremental value.  
**Action:** **Preserve as Legacy baseline + Decompose for V2 research.**

---

## 32.2 `attention.py`

**Current value:** interpretable decomposition of return, amount and volume behavior.  
**Risk:** the name may sound like direct investor-attention measurement while the implementation is largely OHLCV-derived.  
**Constitutional interpretation:** `OHLCV-derived attention proxy`.  
**Required evolution:** register primitive inputs and proxy identity; compare against genuinely independent attention data if later acquired.  
**Action:** **Preserve + Rename semantically in V2 lineage.**

---

## 32.3 `certainty.py`

**Current value:** integrates several research ideas into one interpretable composite.  
**Risk:** mixes fundamental, valuation, shape, attention, sell-pressure and memory inputs; may be mistaken for calibrated probability.  
**Constitutional interpretation:** mixed-family Legacy composite score, not a probability contract.  
**Required evolution:** expose component identities and evaluate whether the composite adds value beyond its parents.  
**Action:** **Preserve for Legacy replay + Decompose and re-evaluate.**

---

## 32.4 `sell_pressure.py`

**Current value:** quantifies resistance, turnover-position proxies and volume-stalling structure.  
**Risk:** may be interpreted as direct observation of future sell supply.  
**Constitutional interpretation:** OHLCV-derived sell-pressure proxy.  
**Required evolution:** preserve subfeature lineage; compare with observed order-flow or holder-cost data when available.  
**Action:** **Preserve + Classify as proxy.**

---

## 32.5 `cosco_timing_capital_flow.py`

**Current value:** explicitly distinguishes observed flow-like fields from OHLCV fallback and records `source_type`.  
**Risk:** one high-level score can still hide materially different source-information classes.  
**Constitutional interpretation:** strong migration pattern, but V2 factor identity should separate observed-flow and OHLCV-proxy materializations.  
**Required evolution:** preserve source classification, prohibit silent source-class substitution, test real flow versus proxy incrementally.  
**Action:** **Preserve design principle + Split formal identities.**

---

## 32.6 `tuishen_volume_price.py`

**Current value:** decomposes volume-price structure into interpretable subcomponents and explicitly states that it is not real order-flow evidence.  
**Risk:** subcomponents share substantial OHLCV lineage and may be repeatedly counted elsewhere.  
**Constitutional interpretation:** structured OHLCV feature family and Legacy composite.  
**Required evolution:** register subfeatures, measure redundancy, compare component and composite contributions.  
**Action:** **Preserve + Register + Ablate.**

---

## 32.7 MACD integration

**Current value:** explicit algorithm versioning, data-readiness semantics, score-use diagnostics and policy-use counterfactuals.  
**Risk:** MACD may affect both technical score and strategy policy, creating dual use.  
**Constitutional interpretation:** valuable example of role-specific factor attribution.  
**Required evolution:** generalize factorial attribution patterns to other multi-role features.  
**Action:** **Preserve and generalize research pattern.**

---

## 32.8 `cosco_timing_daily.py::_dynamic_fundamental_score`

**Current value:** attempts to adapt position posture to market evidence while formal fundamentals are incomplete.  
**Risk:** price, moving averages, drawdown and recovery modify a field named `fundamental_score`.  
**Constitutional interpretation:** semantic contamination and duplicate-information risk.  
**Required evolution:** separate fundamental data from technical/trend context; combine only through an explicitly named composite or strategy policy.  
**Action:** **Correct semantic ownership during extraction.**

---

## 32.9 `CoscoTimingEngine`

**Current value:** integrated repository of many useful research constructs.  
**Risk:** feature extraction, composite scoring, regime inference, candidate logic and timing policy are tightly coupled, making attribution difficult.  
**Constitutional interpretation:** Legacy integrated research engine, not the V2 Feature System.  
**Required evolution:** extract reusable factors by lineage and evidence, not by mechanically copying every score into the new registry.  
**Action:** **Freeze expansion + Extract selectively.**

---

# 33. V2 Factor-System Direction

The future V2 Factor System should support the logical flow:

```text
Qualified Canonical Data
        ↓
Feature Definitions
        ↓
PIT Materialization
        ↓
Feature Quality Gates
        ↓
Feature Registry / Lineage
        ↓
Factor Research
        ↓
Redundancy and Incremental Analysis
        ↓
Approved Feature Set
        ↓
Candidate / Context / Strategy Models
```

The Feature System does not own:

- final candidate ranking;
- entry decisions;
- position lifecycle transitions;
- portfolio allocation;
- execution.

It provides trustworthy, versioned information objects to those systems.

---

# 34. Minimum Formal Factor Package

Before a feature can be treated as a formal factor candidate rather than an informal column, it should have, at minimum, as applicable:

```text
1. Feature / Factor Identity
2. Object Type
3. Semantic Family
4. Source-Information Family
5. Source Field and Dependency Lineage
6. Data Eligibility Requirements
7. Decision-Time and Availability Semantics
8. Frequency and Lookback
9. Transformation Definition
10. Normalization Definition
11. Missingness Policy
12. Population / Universe Scope
13. Target and Horizon Scope
14. Expected Relationship
15. Allowed Decision Roles
16. Research Status
17. Known Redundancy Risks
18. Risk and Failure Conditions
19. Materialization Identity Requirements
20. Owner and Version
```

A factor seeking greater authority requires additional evidence under the Research and Validation Constitutions.

---

# 35. Factor Anti-Patterns

The following patterns are constitutionally prohibited or must remain explicitly exploratory.

---

## 35.1 Indicator accumulation

```text
Model weakens
    ↓
Add another indicator
    ↓
Composite score grows
```

without attribution.

---

## 35.2 Semantic diversity theater

```text
Trend
Attention
Flow
Structure
Certainty
```

all derived mostly from the same OHLCV path but presented as independent information families.

---

## 35.3 Proxy laundering

Renaming an OHLCV-derived estimate as observed capital flow, investor intention or actual sell supply.

---

## 35.4 Probability laundering

Renaming a weighted factor score as probability without an explicit event and calibration evidence.

---

## 35.5 Hidden source substitution

Using real flow when available and OHLCV proxy otherwise under one unchanged factor identity without exposing the change.

---

## 35.6 Semantic contamination

Putting technical price behavior into a fundamental-named feature or mixing unrelated families under misleading labels.

---

## 35.7 Full-sample normalization

Using future observations to normalize historical predictive features.

---

## 35.8 Reusing sample-derived constants as timeless rules

Embedding learned thresholds, priors or weights in source code without artifact identity and sample isolation.

---

## 35.9 Feature name as documentation

A descriptive column name is not sufficient lineage.

---

## 35.10 Anonymous notebook features in formal models

A formal model must be reconstructable from registered feature definitions.

---

## 35.11 Same factor name, changing horizon

A factor claim for next-session return must not silently become a 5-session target while preserving one unchanged research identity.

---

## 35.12 Multi-role use without attribution

A feature used in score, gate and sizing must not be treated as one isolated intervention.

---

## 35.13 Family concentration hidden by feature count

Fifty OHLCV transformations are not automatically a diversified fifty-factor model.

---

## 35.14 Treating descriptor accuracy as trading profitability

Correctly identifying a trend state does not automatically prove profitable entry or exit timing.

---

## 35.15 Post-hoc interaction mining

Repeatedly searching interactions until one works and presenting it as an original conditional hypothesis.

---

# 36. Factor Review Questions

Every serious factor addition should be reviewable through the following questions.

## Identity

- What exactly is the feature or factor?
- Is the version stable?
- Is this a primitive, derived feature, descriptor, factor, composite or model output?

## Semantics

- What does it claim to represent?
- Is the name honest about whether it is observed or proxied?

## Lineage

- Which source fields and upstream features does it use?
- Which source-information families does it depend on?
- Does it share substantial lineage with existing features?

## Time

- When is the feature available?
- Is the current bar final?
- Does the window include only information available at decision time?

## Population

- Is the feature comparable across the intended universe?
- Is it time-series, cross-sectional or both?

## Transformation

- What normalization is applied?
- Were parameters learned from data?
- Were they fitted only on permitted samples?

## Missingness

- What happens when data is missing, stale or insufficient?
- Does the model distinguish missing from neutral?

## Research

- What target and horizon is the factor expected to help?
- What is the expected direction or conditional relationship?
- What is the baseline?

## Redundancy

- Which existing factors contain similar information?
- Does the factor add incremental predictive or economic value?

## Role

- Is the feature used as predictor, context, gate, sizing input, risk input or diagnostic?
- Is multi-role use separately attributable?

## Risk

- In which regimes or populations may the factor fail?
- What data dependency or semantic assumption could invalidate it?

---

# 37. Current Refoundation Factor Constraints

Until explicitly changed by new evidence and a traceable decision, the following posture remains binding:

```text
Do not expand CoscoTimingEngine with new platform-wide factors.
Do not add new factor responsibilities to the legacy backtest God Object.
Do not treat F/R/T or total score as the V2 Factor System.
Do not call a weighted score a calibrated probability.
Do not call OHLCV-derived flow real capital flow.
Do not treat attention proxy as direct investor-intention observation.
Do not treat sell-pressure proxy as observed future sell supply.
Do not hide technical information inside fundamental identity.
Do not interpret multiple OHLCV transformations as independent confirmation by default.
Do not embed new sample-derived priors or thresholds as timeless source constants.
Do not promote a feature without explicit target, lineage and incremental evidence.
Do not use sealed-test outcomes for feature selection or factor tuning.
```

Exploratory research may continue.

The authority of the claim must remain bounded by actual evidence.

---

# 38. Relationship to the Remaining Constitution

## `06-Strategy-Constitution.md`

Will define:

- Candidate versus Strategy boundaries;
- strategy objectives;
- applicable market and universe;
- signal sources;
- Entry;
- Position Lifecycle;
- Exit;
- strategy composition;
- position sizing;
- risk rules;
- invalidation;
- strategy state and versioning.

The Factor Constitution defines trustworthy information objects.

The Strategy Constitution defines how approved information is converted into decision policies.

---

## `07-Validation-Constitution.md`

Will define the proof standard for:

- train / validation / calibration / test roles;
- walk-forward;
- OOS;
- sealed test;
- IC / RankIC acceptance where applicable;
- robustness;
- calibration;
- economic significance;
- promotion gates;
- degradation criteria.

The Factor Constitution defines what must be tested.

The Validation Constitution defines how much evidence is sufficient.

---

## `08-Roadmap.md`

Will sequence:

- Feature Registry implementation;
- lineage and materialization contracts;
- Legacy factor inventory;
- duplicate-information audit;
- Candidate Discovery baseline factors;
- observed-flow integration;
- ETF/theme context factors;
- Chan and Tuishen-inspired factor research;
- Factor System migration.

The Roadmap may prioritize.

It may not weaken factor identity or lineage discipline for speed.

---

## `09-Glossary.md`

Will freeze terms such as:

- Observation;
- Feature;
- Factor;
- Descriptor;
- State;
- Composite Score;
- Semantic Family;
- Source-Information Family;
- Feature Definition;
- Feature Materialization;
- Lineage;
- Proxy;
- Incremental Value;
- IC;
- RankIC;
- Ablation.

---

# 39. Constitutional Factor Commitments

The project commits to the following factor model.

1. **A named indicator is not automatically a factor, and a factor is not automatically Alpha.**
2. **Every formal factor must have stable identity, explicit semantics and traceable lineage.**
3. **Semantic family and source-information family are separate dimensions.**
4. **Semantic diversity does not prove information independence.**
5. **Multiple OHLCV transformations may coexist, but repeated use requires visible lineage and incremental evidence.**
6. **Feature Definition Identity and Feature Materialization Identity are distinct.**
7. **A factor claim is scoped by target, horizon, population, decision time and role.**
8. **Cross-sectional and time-series semantics must not be conflated.**
9. **Normalization is a result-affecting transformation and must be point-in-time correct.**
10. **Learned normalization parameters, priors, thresholds and transforms are model artifacts and obey sample isolation.**
11. **Missing, unavailable, stale and neutral values are different states.**
12. **Composite scores are versioned models and are not probabilities by default.**
13. **A feature used in multiple decision roles requires role-specific attribution.**
14. **Observed capital flow and OHLCV-derived flow proxies must remain separate information classes.**
15. **MACD, moving averages, trend and momentum require explicit overlap analysis.**
16. **Chan-derived structures may have distinct semantics while still sharing price-based source information.**
17. **Tuishen-inspired concepts must be converted into measurable proxies or models and labeled honestly.**
18. **Fundamental, valuation, technical, flow and event families must not be silently contaminated.**
19. **Factor promotion requires both definition correctness and evidence of useful contribution for a defined scope.**
20. **Standalone strength does not replace incremental analysis.**
21. **A large number of correlated features is not equivalent to a diversified information set.**
22. **Negative factor evidence, degradation and retirement remain part of project knowledge.**
23. **Legacy factor ideas are preserved selectively through lineage and evidence, not copied wholesale into V2.**
24. **The Feature System provides information; it does not own Candidate, Entry, Position Lifecycle, Portfolio or Execution decisions.**
25. **Agents may propose or implement features but may not silently alter definitions, lineage, source class, target scope, sample isolation or promotion status.**

---

# 40. Closing Declaration

The first phase of `market-regime-alpha` learned how to encode many market ideas.

The next phase must learn how to distinguish:

```text
Different names
from
Different information
```

and:

```text
More signals
from
More Alpha
```

The target Factor System is one in which:

```text
Every feature has identity.
Every factor has a hypothesis.
Every value has lineage.
Every transformation has time semantics.
Every proxy is labeled honestly.
Every composite exposes its components.
Every family concentration is visible.
Every new factor must earn incremental authority.
Every retired factor leaves behind evidence.
```

The project will not measure sophistication by the number of indicators it can compute.

It will measure sophistication by whether it can determine what information each indicator actually adds.

The constitutional factor principle is therefore:

> **Do not count names. Count independent information, traceable contribution and validated incremental value.**
