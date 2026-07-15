# R5 Candidate Model Research Program

> **Stage:** R5 — Candidate Discovery Rehearsal MVP
> **Status:** ACTIVE RESEARCH PROGRAM
> **Purpose:** Convert external quantitative-finance research and the current Candidate vertical slice into an ordered, falsifiable, A-share-specific model-improvement program
> **Provider:** Xuntou / ThinkTrader
> **Authority:** Research sequencing. External papers are hypothesis sources, not project authority until reproduced under project data, targets and validation rules.

---

## 1. Research Objective

The current model should answer:

> **At a declared A-share Decision Time, which eligible securities have the strongest relative forward opportunity profile, under an explicit target and market context?**

The current first target family remains:

```text
Next-Session Close Return
Next-Session MFE
Next-Session MAE
```

The ranking problem is cross-sectional.

Therefore the project should optimize and evaluate:

```text
relative ordering
coverage
risk / opportunity separation
stability across dates and regimes
incremental value
turnover / execution realism
```

rather than relying only on point-return prediction error.

---

## 2. Research Interpretation of the Literature

### 2.1 Cross-sectional prediction is naturally a ranking problem

Relevant research:

- Daniel Poh, Bryan Lim, Stefan Zohren, Stephen Roberts — *Building Cross-Sectional Systematic Strategies By Learning to Rank*.
- Xin Zhang, Lan Wu, Zhixue Chen — *Constructing long-short stock portfolio with a new listwise learn-to-rank algorithm*; empirical application includes China A-share factors.
- Masaya Abe, Kei Nakagawa — *Cross-sectional Stock Price Prediction using Deep Learning for Actual Investment Management*.

Project implication:

```text
Candidate Discovery
should not be permanently defined as
"predict exact next return and sort"
```

The project should compare:

```text
pointwise regression
vs
classification where target semantics justify it
vs
pairwise / listwise ranking
```

under the same Candidate Population and evaluation protocol.

---

### 2.2 Short-horizon momentum and contrarian effects are state-dependent

Relevant China-market research:

- Huai-Long Shi, Wei-Xing Zhou — *Time series momentum and contrarian effects in the Chinese stock market*.
- Huai-Long Shi, Wei-Xing Zhou — *Wax and wane of the cross-sectional momentum and contrarian effects: Evidence from the Chinese stock markets*.
- Huai-Long Shi, Wei-Xing Zhou — *Horse race of weekly idiosyncratic momentum strategies with respect to various risk metrics: Evidence from the Chinese stock market*.

Project implication:

```text
Momentum
≠
always-on universal Alpha
```

and:

```text
Contrarian / reversal
≠
always-on universal Alpha
```

The research question should become:

```text
Which short-horizon effect works
under which market / liquidity / volatility / sentiment context?
```

This supports the existing architecture:

```text
Market Context
        ↓
Candidate Model conditioning / comparison
```

rather than a permanent fixed-weight score.

---

### 2.3 Intraday and time-of-day structure may contain incremental information

Relevant research:

- Steven L. Heston, Robert A. Korajczyk, Ronnie Sadka — *Intraday Patterns in the Cross-section of Stock Returns*.

Project implication:

Intraday features may later test:

```text
same-time-of-day continuation
short-lived liquidity reversal
volume / imbalance timing
```

but this evidence should not be transplanted directly into A-shares without local reproduction.

The correct sequence is:

```text
Daily / 14:55 baseline
        ↓
A-share intraday reproduction
        ↓
Incremental feature test
```

not:

```text
foreign-market paper
        ↓
production rule
```

---

### 2.4 More factors create a multiple-testing problem

Relevant research:

- Campbell R. Harvey, Yan Liu — *False (and Missed) Discoveries in Financial Economics*.

Project implication:

The project must not improve the model by repeatedly trying:

```text
hundreds of indicators
hundreds of thresholds
hundreds of feature combinations
```

and selecting the best historical result.

Every new feature family requires:

```text
pre-declared hypothesis
identified Feature Definition
fixed Target
fixed Sample Role
baseline comparison
ablation
OOS / walk-forward evidence
negative-result retention
```

---

## 3. Model Ladder

The project should progress through the following model ladder.

### B0 — Single-Feature Deterministic Rank

Current status:

```text
IMPLEMENTED
```

Purpose:

```text
pipeline verification
single-feature attribution
minimum comparator
```

Current representative example:

```text
5-session momentum descending rank
```

B0 must remain permanently available as a comparator.

---

### B1 — Transparent Cross-Sectional Composite Rank

Current priority:

```text
NEXT MODEL IMPLEMENTATION
```

Method:

1. select a small number of pre-declared Features;
2. normalize each Feature within the Decision-Time cross-section by rank / percentile;
3. apply explicit direction:
   - higher-is-better;
   - lower-is-better;
4. combine with explicit fixed weights;
5. preserve complete Candidate Population accounting;
6. reject incomplete rows explicitly under the first strict baseline;
7. evaluate each feature and combination through ablation.

Why rank normalization:

```text
feature scale differences
should not determine composite weight accidentally
```

Why B1 before machine learning:

```text
interpretable
reproducible
low parameter count
strong attribution baseline
```

### Initial B1 experiment family

Do not declare one final weight set immediately.

Run a controlled ladder:

```text
B1-A: Momentum only              control
B1-B: Momentum + Liquidity
B1-C: Momentum + Volatility penalty
B1-D: Momentum + Liquidity + Volatility penalty
B1-E: add Price-vs-MA20 only as a redundancy test
```

Important:

```text
Momentum
Volatility
Price-vs-MA20
```

all depend substantially on `PRICE_ONLY` information.

Agreement among them must not be interpreted as three independent confirmations.

`Price-vs-MA20` is therefore an ablation candidate, not an automatic core feature.

---

### B2 — Regularized Statistical Baselines

Candidate models:

```text
Ridge
Elastic Net
simple ordinal / pairwise logistic model
```

Purpose:

```text
learn modest interactions / coefficients
while retaining strong regularization and interpretability
```

Required controls:

```text
chronological split
cross-sectional normalization fit without future leakage
coefficient stability
feature-family ablation
turnover comparison against B1
```

B2 should not use a large factor zoo.

---

### B3 — Tree-Based Nonlinear Models

Candidate models:

```text
LightGBM / XGBoost style regression
or
ranking objective such as LambdaMART-style learning-to-rank
```

Entry requirement:

```text
B2 cannot explain the observed nonlinear incremental value
and
B3 improves OOS ranking evidence after costs / turnover controls
```

Primary evaluation remains ranking-oriented:

```text
RankIC
Top-K target spread
quantile monotonicity
coverage
turnover
regime stability
```

Pointwise RMSE alone is insufficient.

---

### B4 — Target-Specific or Multi-Task Opportunity Models

Only after separate single-target baselines are stable.

Possible outputs:

```text
Expected Close Return
Expected MFE
Expected MAE
```

Potential model structure:

```text
shared representation
+
separate target heads
```

but the project must preserve:

```text
Target Identity separation
```

A multi-task model must not collapse the three outcomes into one unlabeled score.

---

### B5 — Context-Conditioned Candidate Model

Add only through controlled incremental comparison:

```text
Market Regime
ETF Context
Theme Context
Leader Resonance
```

Comparison sequence:

```text
Base Candidate Model
        ↓
+ Market Context
        ↓
+ ETF Context
        ↓
+ Theme Context
        ↓
+ Leader Resonance
```

Context may enter as:

```text
feature
interaction
conditional model
mixture / gate
```

but must earn authority through incremental evidence.

---

### B6 — Transaction Flow / Order Flow Increment

Xuntou provides research inputs that can support later experiments such as:

```text
transaction-count / capital-flow aggregates
DDX / DDY / DDZ style fields
net order / withdrawal statistics
large-order / small-order active-flow fields
1m order-flow data
```

These are not immediate baseline requirements.

Research sequence:

```text
Daily price / volume baseline
        ↓
Transaction-flow increment
        ↓
Order-flow increment
        ↓
Level-2 / microstructure increment
```

Each layer must show incremental value over the lower-cost data layer.

---

## 4. Feature-Family Research Map

### Family A — Short-Horizon Return State

Candidate Features:

```text
1-session return
3-session return
5-session momentum
short-term reversal
residual / market-adjusted return
```

Research question:

```text
momentum or reversal?
under which regime?
```

---

### Family B — Trend / Price Location

Candidate Features:

```text
price vs MA
breakout distance
rolling high distance
trend slope
```

Risk:

High redundancy with momentum.

Rule:

```text
one representative first
siblings only through ablation
```

---

### Family C — Volatility / Adverse-Risk State

Candidate Features:

```text
realized volatility
downside volatility
recent drawdown
intraday range
ATR-like range normalization
```

Possible role:

```text
risk descriptor
ranking penalty
context interaction
```

Do not assume low volatility is always a positive Alpha signal for a short-horizon Candidate target.

---

### Family D — Liquidity / Capacity

Candidate Features:

```text
median amount
average amount
turnover
amihud-style price impact proxy
spread / depth when available
```

Possible roles must be separated:

```text
Eligibility Gate
vs
Candidate Predictor
vs
Portfolio Capacity Control
```

Using one liquidity measure in several owners must be explicit.

---

### Family E — Intraday Price / Volume Structure

Candidate Features:

```text
14:55 return from open
morning vs afternoon return split
intraday VWAP distance
late-session acceleration
late-session volume share
closing-range position
```

These are high-priority after the first provider-backed daily baseline because they directly match the 14:55 Decision Time.

---

### Family F — Transaction Flow

Candidate Features from identified Xuntou transaction-count data may include:

```text
active buy / sell imbalance
large-order net inflow
net order change
withdrawal imbalance
DDX / DDY / DDZ research fields
```

These fields must be treated as provider-defined observations.

The project must not assume:

```text
provider field name
=
independent economic information
```

Lineage and correlation analysis remain required.

---

### Family G — Order Flow / Microstructure

Later features may include:

```text
price-level order concentration
order-flow imbalance
bid / ask depth imbalance
queue shape
cancel intensity
```

This family has higher data cost and higher overfitting risk.

It enters only after daily / minute / transaction-flow baselines are established.

---

### Family H — Market / ETF / Theme Context

Candidate context objects:

```text
broad-market breadth
market volatility
index relative strength
ETF relative strength
ETF turnover / flow where valid
industry / theme breadth
leader resonance
```

These should initially be tested as context interactions, not permanent hard gates.

---

## 5. First Concrete Experiment Queue

### EXP-CAND-001 — B0 Momentum Reproduction

Goal:

```text
reproduce the current one-feature rank on provider-backed Xuntou rehearsal data
```

Target:

```text
Close Return
MFE
MAE reported separately
```

---

### EXP-CAND-002 — Momentum Horizon Scan

Pre-declared horizons:

```text
1 session
3 sessions
5 sessions
10 sessions
```

Purpose:

```text
identify whether the current 5-session choice is supported
without unrestricted parameter search
```

Use the same split and evaluation protocol for all horizons.

---

### EXP-CAND-003 — Momentum vs Short-Term Reversal

Compare:

```text
positive momentum ranking
vs
contrarian / reversal ranking
```

Evaluate by:

```text
Market Regime
market volatility bucket
liquidity bucket
```

This directly tests the China-market literature's state-dependence hypothesis.

---

### EXP-CAND-004 — B1 Transparent Composite

Compare:

```text
Momentum
Momentum + Liquidity
Momentum + Volatility penalty
Momentum + Liquidity + Volatility penalty
```

Then add:

```text
Price-vs-MA20
```

only as an explicit redundancy / incremental-value test.

---

### EXP-CAND-005 — 14:55 Intraday Structure Increment

Candidate additions:

```text
intraday return to 14:55
late-session return acceleration
late-session volume share
decision price vs intraday VWAP
closing-range position
```

Purpose:

Match the model to the actual Decision Time instead of relying only on daily-history descriptors.

---

### EXP-CAND-006 — Market Context Increment

Add:

```text
market breadth
index trend
market volatility state
```

Test:

```text
feature interaction
vs
conditional subgroup performance
vs
hard gate
```

A hard gate is the last option, not the first.

---

### EXP-CAND-007 — ETF / Theme Context Increment

Test whether:

```text
stock Candidate score
+
related ETF / theme relative strength
+
leader resonance
```

improves the Candidate ranking OOS.

Do not assume ETF strength is always useful.

---

### EXP-CAND-008 — Xuntou Transaction-Flow Increment

Only after the previous baselines are stable.

Candidate inputs:

```text
large-order net inflow
active buy / sell imbalance
net order / withdrawal measures
```

Required comparison:

```text
Base Model
vs
Base + Transaction Flow
```

---

### EXP-CAND-009 — Learning-to-Rank Baseline

Compare:

```text
pointwise regression score sorting
vs
pairwise ranking
vs
listwise ranking
```

under identical:

```text
Candidate Population
Feature Set
Target
Train / Validation / OOS windows
Portfolio / Top-K evaluation
```

No LTR claim is accepted from in-sample ranking improvement alone.

---

## 6. Evaluation Protocol

Every experiment should report at least:

### Candidate quality

```text
RankIC distribution by date
mean / median RankIC
RankIC hit rate
Top-K target mean
Top-K minus population mean
quantile monotonicity
MFE distribution
MAE distribution
```

### Stability

```text
rolling performance
market-regime slices
liquidity slices
market-cap slices where PIT data permits
year / quarter slices
```

### Practicality

```text
ranking coverage
turnover
concentration
limit-state exclusions
next-session tradability diagnostics
execution-sensitive stress cases
```

### Incremental evidence

```text
baseline
+
new component
-
component ablation
```

---

## 7. Promotion Gate for a New Feature or Model

A feature/model is not promoted because it has:

```text
one high IC
one high annual return
one attractive backtest period
```

Minimum promotion evidence should include:

```text
PIT-correct input for the tested claim
reproducible identity
chronological OOS evidence
incremental value over a simpler baseline
ablation support
reasonable turnover / capacity behavior
stability analysis
failure-condition definition
```

---

## 8. Current Model Improvement Decision

The current implementation sequence is:

```text
Xuntou minimum P0 adapter
        ∥
B1 Transparent Composite Rank
        ↓
Provider-backed B0 / B1 reproduction
        ↓
Momentum-horizon and reversal experiments
        ↓
14:55 intraday feature increment
        ↓
Market / ETF / Theme context increment
        ↓
Transaction flow
        ↓
Learning-to-Rank
        ↓
Order flow / Level 2 only if incremental evidence justifies it
```

The project should not jump directly from B0 to a deep model.

---

## 9. Reference Set

Primary research references used as hypothesis sources:

1. Poh, Lim, Zohren, Roberts — *Building Cross-Sectional Systematic Strategies By Learning to Rank* — arXiv:2012.07149.
2. Zhang, Wu, Chen — *Constructing long-short stock portfolio with a new listwise learn-to-rank algorithm* — arXiv:2104.12484.
3. Abe, Nakagawa — *Cross-sectional Stock Price Prediction using Deep Learning for Actual Investment Management* — arXiv:2002.06975.
4. Shi, Zhou — *Time series momentum and contrarian effects in the Chinese stock market* — arXiv:1702.07374.
5. Shi, Zhou — *Wax and wane of the cross-sectional momentum and contrarian effects: Evidence from the Chinese stock markets* — arXiv:1707.05552.
6. Shi, Zhou — *Horse race of weekly idiosyncratic momentum strategies with respect to various risk metrics: Evidence from the Chinese stock market* — arXiv:1910.13115.
7. Heston, Korajczyk, Sadka — *Intraday Patterns in the Cross-section of Stock Returns* — arXiv:1005.3535.
8. Harvey, Liu — *False (and Missed) Discoveries in Financial Economics* — arXiv:2006.04269.

These references do not constitute direct evidence that the same effects survive in the project's A-share universe, Decision Time, target definition, costs, or period.

---

## 10. Research Commitment

> **The next phase of Market Regime Alpha is strategy/model research supported by Xuntou data, not a broad data-integration project. The project will build a strong transparent ranking baseline first, then test statistical, nonlinear, context-conditioned and Learning-to-Rank models only through controlled incremental evidence.**
