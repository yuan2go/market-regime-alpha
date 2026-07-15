# Entry, Position Lifecycle and Exit Research Program

> **Status:** CURRENT RESEARCH PROGRAM
> **Authority:** Lower-level research sequencing under the Constitution and Strategy Constitution
> **Scope:** A-share Entry timing, Position Lifecycle, and Exit research after Candidate Discovery
> **Primary data provider:** Xuntou / ThinkTrader / XtQuant
> **Auxiliary sources:** Eastmoney, Tencent and other explicitly identified public sources under the Data Source Role Matrix

---

## 1. Purpose

The project must reduce two distinct practical failure modes:

```text
Failure A: ENTER -> immediate adverse move
           "buy, then fall"

Failure B: EXIT -> strong continuation
           "sell, then rally"
```

These failures are not solved by one symmetric buy/sell score.

The canonical research decomposition is:

```text
Market / ETF / Theme / Capital Context
        ↓
Candidate Discovery
        ↓
Entry Timing Model
        ↓
Position Lifecycle
HOLD / ADD / REDUCE / ROTATE / EXIT
        ↓
Exit Continuation / Stopping Model
        ↓
Portfolio Decision
        ↓
Execution
```

The governing rule is:

> **Candidate ranking, Entry timing, Position Lifecycle and Exit timing are separate research problems with separate targets, evidence and evaluation.**

---

## 2. Problem Decomposition

### 2.1 Candidate Discovery asks `WHO?`

Candidate Discovery ranks the eligible cross-section.

It answers:

```text
Which securities have the strongest relative forward opportunity profile?
```

It does not answer:

```text
Should a position be entered now?
```

A high Candidate rank may legitimately lead to `NO_ACTION`.

### 2.2 Entry asks `WHY NOW?`

Entry evaluates whether a high-ranked opportunity should be initiated at the current Decision Time.

It must distinguish:

```text
Good security
≠
Good entry timing
```

The primary practical objective is to reduce adverse path behavior immediately after entry without filtering away most valid upside opportunities.

### 2.3 Position Lifecycle asks `WHAT SHOULD AN EXISTING POSITION DO NOW?`

The lifecycle model consumes:

```text
current position state
original entry thesis
new Candidate / context evidence
path since entry
risk
opportunity cost
```

and supports:

```text
HOLD
ADD
REDUCE
ROTATE
EXIT
```

### 2.4 Exit asks `IS CONTINUED HOLDING STILL WORTH IT?`

Exit is not the inverse of Entry.

The Exit model evaluates the marginal value and risk of continued holding from the current state.

```text
Not attractive for a new entry
≠
Existing position should be exited
```

---

## 3. Entry Path-Dependent Target Family

### 3.1 Why point-return labels are insufficient

A simple forward-return label can mark this path as successful:

```text
Decision Price
        ↓
-4% adverse excursion
        ↓
+7% final return
```

but the practical experience is still:

```text
buy -> immediate drawdown
```

Therefore Entry research must include path-dependent targets.

### 3.2 Canonical Entry competing-event labels

For a declared Decision Time, an explicit upper barrier, lower barrier and maximum horizon define three mutually exclusive outcomes:

```text
UP_FIRST
DOWN_FIRST
TIMEOUT
```

Definitions:

```text
UP_FIRST:
    the favorable barrier is reached before the adverse barrier

DOWN_FIRST:
    the adverse barrier is reached before the favorable barrier

TIMEOUT:
    neither barrier is reached before the declared horizon expires
```

The barrier specification must be versioned and identified.

Allowed research forms include:

```text
fixed percentage barriers
volatility-scaled barriers
ATR-like scaled barriers
strategy-family-specific barriers
```

A barrier configuration is a research definition, not a universal market truth.

### 3.3 Entry outputs

An Entry model may estimate, when supported:

```text
P(UP_FIRST)
P(DOWN_FIRST)
P(TIMEOUT)
Expected MFE
Expected MAE
Expected time to favorable event
Expected time to adverse event
uncertainty
```

These are predictions.

They do not directly equal `ENTER`.

### 3.4 Entry policy boundary

A later Entry policy may consume:

```text
Candidate rank
+
Entry path prediction
+
risk
+
context
+
cost
```

and produce an Entry Proposal.

Conceptually:

```text
Entry Utility
=
P(UP_FIRST) * Expected Upside
-
P(DOWN_FIRST) * Expected Downside
-
Transaction Cost
-
Uncertainty Penalty
```

This equation is a research-policy template. Permanent coefficients or thresholds must be established through lower-level specifications and validation.

---

## 4. Exit and Continuation Target Family

### 4.1 Exit is a continuation problem

For an existing position, the model asks:

```text
From the current position state,
will additional favorable continuation occur
before a material adverse drawdown?
```

### 4.2 Canonical Exit competing-event labels

A first research family is:

```text
CONTINUE_UP_FIRST
DRAWDOWN_FIRST
TIMEOUT
```

Definitions:

```text
CONTINUE_UP_FIRST:
    an explicitly defined further-upside barrier is reached first

DRAWDOWN_FIRST:
    an explicitly defined adverse-drawdown barrier is reached first

TIMEOUT:
    neither event occurs within the declared evaluation horizon
```

This target is evaluated from each eligible lifecycle Decision Time, not only from original entry.

### 4.3 Exit outputs

An Exit continuation model may estimate:

```text
P(CONTINUE_UP_FIRST)
P(DRAWDOWN_FIRST)
P(TIMEOUT)
Expected Further MFE
Expected Future Drawdown
Expected Time to Continuation
Expected Time to Drawdown
uncertainty
```

### 4.4 Post-Exit Regret diagnostic

The project adds a dedicated diagnostic for premature exit:

```text
PostExitRegret(H)
=
future maximum favorable price within H
/
actual or simulated exit reference price
- 1
```

This is a diagnostic, not an optimization instruction to sell at the future maximum.

### 4.5 Late-exit diagnostics

The system must not reduce premature exits by simply never exiting.

Therefore Exit evaluation must also report:

```text
future adverse excursion after hold decision
profit giveback
avoided drawdown from exit
late-exit rate
```

The research objective is to balance:

```text
Premature Exit
vs
Late Exit
```

---

## 5. Position State as First-Class Research Input

Exit and lifecycle decisions must know the state of the existing position.

Minimum future Position State research fields include:

```text
entry reference price
entry time
current price
highest price since entry
lowest price since entry
current unrealized PnL
MFE since entry
MAE since entry
drawdown from post-entry high
holding time
add count
reduce count
original thesis / Candidate reference
current thesis validity
```

The same market bar may justify different actions for:

```text
a new position
an early losing position
a mature profitable position
a partially reduced position
```

Position State therefore belongs to lifecycle research and must not be reconstructed from ambiguous action strings.

---

## 6. Feature and Evidence Layers

### Layer A — Candidate / Opportunity Evidence

Examples:

```text
Candidate rank
1 / 3 / 5 / 10-session relative strength
short-horizon reversal
market-adjusted return
industry / ETF / theme relative strength
```

### Layer B — Entry Timing Structure

High-priority 14:55 research candidates:

```text
decision price vs intraday VWAP
return from open to Decision Time
morning vs afternoon return split
last 30m / 60m return
late-session acceleration
late-session volume share
closing-range position
distance from intraday high
pullback depth
breakout distance
```

### Layer C — Risk State

Examples:

```text
realized volatility
downside volatility
ATR-like normalized range
recent drawdown
intraday maximum adverse excursion
gap-risk descriptors
liquidity / capacity
price-limit distance
```

Risk descriptors must not automatically be interpreted as Alpha predictors.

### Layer D — Context

Examples:

```text
Market Regime
market breadth
market volatility state
market liquidity state
ETF relative strength
Theme breadth
Leader resonance
capital concentration / exhaustion
```

Context should first be tested through subgroup analysis and incremental comparison before becoming a hard gate.

### Layer E — Position Lifecycle State

Examples:

```text
MFE since entry
MAE since entry
drawdown from high
holding duration
original thesis strength
current thesis strength
opportunity-cost rank
```

### Layer F — Flow / Microstructure

Later Xuntou-supported experiments may include:

```text
transaction-flow imbalance
large-order net flow
order-flow imbalance
multi-level depth imbalance
cancel intensity
queue pressure
```

This layer enters only after lower-cost daily and minute-level evidence has established a reproducible baseline.

---

## 7. Model Ladder

### E0 — Candidate-Only Entry Baseline

Use Candidate rank without an Entry timing model.

Purpose:

```text
control group
measure the raw buy-then-fall failure rate
```

### E1 — Transparent / Regularized Entry Baseline

Candidate models:

```text
multinomial logistic regression
regularized logistic models
simple competing-event score
```

Outputs target:

```text
UP_FIRST / DOWN_FIRST / TIMEOUT
```

### E2 — Nonlinear Entry Model

Candidate models:

```text
LightGBM / XGBoost style classification
```

Entry requirement:

```text
E2 must improve OOS path metrics over E1
without unacceptable coverage loss or turnover increase
```

### E3 — Time-to-Event / Competing-Risk Entry Model

Potential methods:

```text
survival analysis
competing-risk models
hazard-based time-to-event models
```

Only after path labels and simpler baselines are stable.

### X0 — Fixed / Simple Exit Baselines

Permanent control arms may include:

```text
fixed-time exit
simple trailing stop
simple time stop
simple risk stop
```

These are baselines, not constitutional exit rules.

### X1 — Transparent Continuation Baseline

Estimate:

```text
CONTINUE_UP_FIRST
vs
DRAWDOWN_FIRST
vs
TIMEOUT
```

using a small, explicit feature set.

### X2 — Nonlinear Continuation Model

Candidate models:

```text
LightGBM / XGBoost style classification
```

### X3 — Survival / Competing-Risk Exit Model

Estimate time-varying continuation and drawdown hazards.

### X4 — Optimal-Stopping Policy Research

Only after predictive continuation evidence is stable.

The project may compare:

```text
continue holding value
vs
immediate liquidation value
```

but must not collapse prediction and final portfolio/execution authority.

---

## 8. Experiment Queue

### EXP-ENTRY-001 — Candidate vs Candidate + Entry Gate

Compare:

```text
B0 / B1 Candidate ranking only
vs
B0 / B1 + Entry competing-event baseline
```

Primary question:

```text
Does DOWN_FIRST Rate fall materially
without rejecting most valid UP_FIRST opportunities?
```

### EXP-ENTRY-002 — 14:55 Intraday Structure Increment

Add one family at a time:

```text
VWAP distance
late-session return
late-session acceleration
closing-range position
late-session volume share
```

### EXP-ENTRY-003 — Market Regime Conditioning

Compare:

```text
base Entry model
vs
Market Regime interaction / conditional performance
```

### EXP-ENTRY-004 — ETF / Theme / Leader Context Increment

Test incremental value only.

### EXP-ENTRY-005 — Transaction Flow Increment

Add Xuntou transaction-flow evidence only after daily/minute baselines are stable.

### EXP-EXIT-001 — Fixed-Time / Simple Exit Controls

Maintain simple control arms.

### EXP-EXIT-002 — Continuation Competing-Event Baseline

Compare continuation prediction against fixed exits.

### EXP-EXIT-003 — Position-State Increment

Add:

```text
MFE since entry
MAE since entry
drawdown from high
holding duration
```

### EXP-EXIT-004 — Market / ETF / Theme / Leader Exhaustion Increment

Test whether context reduces premature exits or late exits.

### EXP-EXIT-005 — Minute / Flow Increment

Only after lower-cost evidence is stable.

---

## 9. Evaluation Metrics

### 9.1 Entry metrics

Minimum metrics:

```text
UP_FIRST Rate
DOWN_FIRST Rate
TIMEOUT Rate
Entry MAE distribution
Entry MFE distribution
Opportunity Recall
Entry coverage
Expected / realized transaction cost
```

`DOWN_FIRST Rate` is the primary direct diagnostic for:

```text
buy, then fall
```

It must never be optimized alone.

The paired metric is opportunity recall / missed valid upside.

### 9.2 Exit metrics

Minimum metrics:

```text
Premature Exit Rate
Post-Exit Regret distribution
Avoided Drawdown
Late Exit Rate
Profit Giveback
Continuation-event accuracy / ranking
holding-period distribution
turnover
```

### 9.3 Lifecycle metrics

Minimum metrics:

```text
action coverage
HOLD / ADD / REDUCE / ROTATE / EXIT frequency
action transition matrix
position-duration distribution
MFE captured
MAE experienced
opportunity-cost improvement from rotation
```

---

## 10. Validation Rules

Every Entry / Exit experiment must preserve:

```text
Point-in-Time correctness
explicit Decision Time
explicit Target Identity
explicit barrier / horizon identity
chronological train / validation / OOS split
no final-test retuning
negative-result retention
feature-family ablation
transaction-cost and execution diagnostics
complete Candidate / position population accounting
```

Additional rules:

1. Barrier values must be pre-declared in a small hypothesis set.
2. Do not search a large grid and report only the best barrier combination.
3. Future highs/lows used to construct labels may not enter features.
4. Exit labels must be created from lifecycle Decision Times, not reconstructed only from completed winning trades.
5. Positions that would not exist under the evaluated Entry policy require explicit counterfactual handling.
6. Time-based baselines must remain available permanently for comparison.
7. L2 and deep-learning complexity requires incremental OOS evidence over simpler models.

---

## 11. Relationship to MACD, Moving Averages, Chan and Tuishen

These frameworks may contribute measurable Features or Context.

They do not receive automatic action authority.

### MACD / Moving Averages

Translate into identified descriptors such as:

```text
DIF / DEA / Histogram
histogram slope / acceleration
time since cross
price vs MA
MA slope
MA spread
```

### Chan Theory

Research implementation must identify:

```text
confirmed structure
confirmation time
repaint / future-confirmation risk
pivot / center state
divergence state
invalidation level
```

### Tuishen-inspired research

Translate into measurable hypotheses such as:

```text
leader ignition
breadth expansion
volume acceleration
leader divergence
sell-pressure / exhaustion
```

Required comparison:

```text
Base model
vs
Base + framework-derived Feature family
```

---

## 12. Data Sequence

The provider sequence is experiment-driven.

### P0 — First Entry / Exit baselines

```text
Xuntou trading calendar
PIT / explicitly qualified Candidate universe evidence
listing / ST / suspension / price-limit evidence
daily OHLCV / amount
14:55 Decision-Time observations
next-session and multi-session OHLC needed by declared targets
```

### P1 — Intraday Entry / Lifecycle experiments

```text
1m bars
intraday VWAP evidence
finalized minute observations
```

### P2 — Context

```text
market index state
ETF / industry / theme context
market breadth
leader context
```

### P3 — Flow / Microstructure

```text
transaction flow
order flow
Level 2 / depth / queue evidence
```

Eastmoney, Tencent and other public sources remain auxiliary under the Data Source Role Matrix.

---

## 13. Implementation Order

The current ordered implementation program is:

```text
1. Finish B1 verification and common ranking interface
2. Implement minimum Xuntou P0 adapter required for provider-backed Candidate experiments
3. Reproduce B0 / B1 on Xuntou REHEARSAL data
4. Implement identified Entry Path Target contracts and materializers
5. Run EXP-ENTRY-001
6. Add 14:55 intraday Entry features incrementally
7. Define canonical Position State contract
8. Implement Exit continuation Target contracts and simple control arms
9. Run EXP-EXIT-001 / EXP-EXIT-002
10. Add Market / ETF / Theme context incrementally
11. Add flow / L2 only when lower-cost evidence justifies it
```

This order is deliberately research-first.

It does not require the entire Xuntou API surface before strategy experiments begin.

---

## 14. Current Non-Claims

The project does not currently claim:

```text
Entry model validated
Exit model validated
buy/sell point accuracy improved
positive Alpha proven
optimal barrier values known
optimal stopping policy proven
Xuntou formal PIT authority for every field
production trading authority
```

---

## 15. Research Commitment

> **The project's practical buy/sell-point objective is now expressed as two falsifiable path-dependent problems: reduce adverse events that occur before favorable movement after Entry, and reduce favorable continuation that occurs after premature Exit without creating excessive late exits. Candidate Discovery remains cross-sectional; Entry and Exit remain independent; Position Lifecycle repeatedly reevaluates existing exposure; all model complexity must earn authority through PIT-correct, chronological, incremental evidence.**
