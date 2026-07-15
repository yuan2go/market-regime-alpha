# R5 Data Source Role Matrix

> **Stage:** R5 — Candidate Discovery Rehearsal MVP
> **Status:** CURRENT DATA-SOURCE ROLE POLICY
> **Purpose:** Keep data integration subordinate to strategy research while fixing Xuntou as the current primary provider and preserving public sources as explicit auxiliaries

---

## 1. Current Provider Decision

The current project decision is:

```text
Primary Provider
=
Xuntou / ThinkTrader / XtQuant
```

Public sources such as:

```text
Eastmoney
Tencent public market interfaces
other explicitly identified public sources
```

may be used as auxiliary evidence where useful.

This decision does not change the project's primary objective:

```text
Strategy / Model Research
>
Provider Integration Breadth
```

Data integration exists to enable identified experiments.

---

## 2. Xuntou — Primary Role

Xuntou is the current primary source for the canonical R5 provider-backed rehearsal path.

Priority research inputs include, subject to the actual purchased/account permission and a verified adapter contract:

```text
trading calendar
A-share security universe / instrument master
listing date
historical ST evidence
suspension / trading-status evidence
price-limit metadata
historical daily OHLCV / amount
intraday / minute observations required by approved experiments
14:55 Decision-Time observations
next-session OHLC for Target materialization
industry / concept / ETF / index context when approved
transaction-flow or deeper quote data only when approved by an experiment charter
```

The project must not implement the entire Xuntou API surface before running Candidate research.

The rule is:

```text
Research Question
        ↓
Required Evidence
        ↓
Minimum Xuntou Adapter Increment
```

not:

```text
Complete Provider Integration
        ↓
Eventually Start Research
```

---

## 3. Eastmoney / Tencent / Other Public Sources — Auxiliary Role

Public/free sources may be used for:

```text
exploratory research
cross-source diagnostics
data-gap investigation
public market-context enrichment
theme / news / public classification exploration
reproducibility checks where their semantics are explicit
```

They are not automatically authoritative replacements for Xuntou in the current canonical R5 provider path.

---

## 4. No Silent Source Substitution

For one semantic field:

```text
Xuntou value
≠
Eastmoney value
≠
Tencent value
```

must not be resolved by silently selecting whichever value is convenient.

A conflict must preserve:

```text
source identity
retrieval / availability evidence where known
field definition
adjustment basis where relevant
observed conflict
reconciliation rule or unresolved status
```

The default current provider priority for the canonical R5 rehearsal path is Xuntou.

An auxiliary source may replace a primary field only under a new identified Dataset / Adapter / Research Charter whose semantics make that substitution explicit.

---

## 5. Data Eligibility Does Not Inflate Through Auxiliary Completion

Example:

```text
Xuntou REHEARSAL dataset
+
public-source exploratory missing-field patch
```

must not automatically become:

```text
FORMAL_RESEARCH
```

The resulting Dataset authority is bounded by the weakest required input and the actual PIT / availability evidence of the combined artifact.

---

## 6. Strategy Research Priority

The current implementation priority is:

```text
B0 single-feature Candidate ranking
        ↓
B1 transparent cross-sectional composite ranking
        ↓
B2 regularized statistical ranking / prediction baseline
        ↓
B3 nonlinear / Learning-to-Rank candidate models
        ↓
Market / ETF / Theme conditional increments
        ↓
Flow / order-flow increments only when lower-cost evidence is exhausted
```

Provider work should be pulled by this sequence.

---

## 7. Current Research Data Tiers

### Tier A — Required for B0/B1

```text
PIT Candidate Population
listing age
ST / suspension / buyability evidence
PIT liquidity measure
daily OHLCV / amount
14:55 Decision-Time reference observation
next-session OHLC
```

### Tier B — Required for Context Experiments

```text
market index state
industry / concept membership
ETF / index relative strength
market breadth
leader / theme context
```

### Tier C — Required for Flow / Microstructure Experiments

```text
minute bars
transaction flow
order-flow proxies
Level-2 / multi-level quote data
auction / queue / depth evidence
```

Tier C must not become a prerequisite for B0/B1/B2 research unless an experiment demonstrates that it is necessary.

---

## 8. Binding Principle

> **Xuntou is the current primary provider; Eastmoney, Tencent and other public channels are auxiliary sources. Data engineering is experiment-driven. The project must spend research complexity on falsifiable Candidate models and validation before spending it on broad provider coverage or expensive microstructure data whose incremental value has not yet been demonstrated.**
