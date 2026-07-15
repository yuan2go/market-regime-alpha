# R5 Xuntou Provider Decision and Strategy-Research Priority

> **Stage:** R5 — Candidate Discovery Rehearsal MVP
> **Status:** CURRENT PROVIDER DECISION
> **Purpose:** Fix Xuntou/ThinkTrader as the current concrete data provider while preventing provider integration from displacing quantitative-strategy research
> **Authority:** Implementation sequencing and provider-role decision. This document does not override the Constitution.

---

## 1. Decision

The current R5 concrete provider is:

```text
Xuntou / ThinkTrader / XtQuant data services
```

The active implementation sequence is no longer a provider-selection exercise.

For the current project:

```text
Current Concrete Provider = Xuntou
```

Other provider-neutral contracts remain useful as architecture boundaries, but QMT/broker/other-provider adapters are not active R5 priorities unless the provider decision changes.

---

## 2. Provider Is Infrastructure, Not the Research Objective

The project objective remains:

```text
Market / ETF / Theme / Capital Context
        ↓
Candidate Discovery
        ↓
Entry
        ↓
Position Lifecycle
HOLD / ADD / REDUCE / ROTATE / EXIT
```

Xuntou is the evidence/data substrate for this research system.

It is not the system identity.

Therefore:

```text
More API Coverage
≠
Better Alpha Model
```

and:

```text
Provider Integration Completeness
≠
Research Progress
```

The active engineering rule is:

> **Implement only the Xuntou data path required by the next identified research experiment.**

---

## 3. Xuntou Capabilities Relevant to the Current Research Program

The Xuntou knowledge base currently documents capabilities that can support the R5/R6 research spine, including:

### Core market structure and eligibility

```text
Trading dates
A-share sector/universe lists
Instrument details
Listing date
Current suspension/trading status
Historical ST intervals
Historical price-limit levels
```

### Price / volume market data

```text
1d bars
1m bars
tick data
OHLC
volume
amount
pre-close
suspension flag
multi-level bid / ask fields in tick data
```

### Research expansion data

```text
transaction-count / money-flow style statistics
1m and daily transaction-count aggregates
order-flow data
industry / concept data
exchange announcements
financial data
northbound / southbound-related data
Xuntou factor products where licensed
```

These capabilities are research inputs, not automatically promoted Factors.

---

## 4. Important PIT and Authority Caveat

A provider function returning a field does not automatically prove historical PIT correctness for every research use.

Examples:

```text
Current instrument detail
≠
Historical PIT security master

Current sector constituent list
≠
Historical PIT constituent history

Downloaded historical bars
≠
Proven Decision-Time availability semantics
```

The project must continue to record:

```text
source identity
retrieval time
availability convention
finality convention
adjustment basis
historical-effective-time convention
```

Provider-backed R5 evidence remains:

```text
REHEARSAL
```

until the required PIT semantics are verified for the research claim.

---

## 5. Minimal Xuntou Adapter Scope

### P0 — Required for the first provider-backed Candidate experiment

Implement only the Xuntou mappings required for:

```text
Trading Calendar
Historical A-share research universe evidence
Listing-date evidence
Historical ST evidence
Suspension evidence
Historical price-limit evidence
Daily OHLCV / amount
14:55 Decision-Time price snapshot
Next-session OHLC
```

This is sufficient to produce:

```text
Candidate Population
Baseline Features
Close Return / MFE / MAE
B0 / B1 ranking experiments
```

### P1 — Add only when the corresponding experiment is approved

```text
Industry / concept context
ETF / index context
transaction-count / capital-flow aggregates
auction / limit-state statistics
```

### P2 — Add only after lower-frequency evidence is exhausted

```text
1m order flow
Level-2 / multi-level order-book features
queue / microstructure features
```

P2 data is not a prerequisite for the first credible Candidate model.

---

## 6. Data-to-Research Ownership

The active direction is:

```text
Xuntou Native Data
        ↓
Xuntou Adapter
        ↓
Canonical / Rehearsal Research Artifacts
        ↓
Feature Materialization
        ↓
Candidate Model Experiments
```

The adapter must not contain:

```text
alpha weights
model thresholds
feature selection
ranking policy
Entry rules
Exit rules
```

Those belong to research/model/strategy owners.

---

## 7. Strategy-Research Time Allocation Principle

For the current stage, development effort should be biased toward:

```text
Strategy / Model Research       HIGH PRIORITY
Validation / Ablation           HIGH PRIORITY
Xuntou Minimum Adapter          REQUIRED ENABLER
Broad Xuntou API Coverage       LOW PRIORITY
UI / Automation                 LOW PRIORITY
Broker Execution                NOT CURRENT PRIORITY
```

A useful decision rule is:

> **Do not add a Xuntou endpoint unless an identified experiment, data-quality requirement, or PIT requirement needs it.**

---

## 8. Immediate Research Use of Xuntou Data

The first provider-backed research loop should use:

```text
Daily OHLCV / amount
        +
14:55 Decision Snapshot
        +
Historical ST / Suspension / Listing Age / Price Limits
        ↓
Provider-backed Candidate Population
        ↓
Transparent Feature Set
        ↓
B0 / B1 Cross-Sectional Ranking
        ↓
Close Return / MFE / MAE Evaluation
```

Only after this loop produces reproducible evidence should the project add:

```text
Market Context
ETF / Theme Context
Transaction Flow
Order Flow
Level 2
```

through controlled incremental experiments.

---

## 9. Non-Goals

This provider decision does not mean:

```text
Xuntou is formally PIT-authoritative for every field
Xuntou factors are automatically trusted Alpha factors
all Xuntou APIs must be integrated now
Level 2 is required before Candidate research can continue
current instrument metadata may be backfilled into history
provider scores may bypass Feature / Factor governance
```

---

## 10. Current Commitment

> **Xuntou is now the concrete data provider for the active A-share research program. The project will implement the smallest Xuntou data path needed to run identified experiments, while the primary development effort shifts to Candidate-model research, factor/family attribution, cross-sectional ranking, validation, and later Market/ETF/Theme conditioning.**
