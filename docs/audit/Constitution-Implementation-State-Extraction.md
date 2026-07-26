# Constitution Implementation-State Extraction

> **Status:** HISTORICAL  
> **Authority:** Historical implementation-state text extracted from Constitution  
> **Owner:** Market Regime Alpha maintainers  
> **Last Updated:** 2026-07-26  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** ../constitution/08-Roadmap.md, ../status/Current-State.md  
> **Code Evidence:** Historical prose; verify implementation against current code/tests/artifacts

## Reason for extraction

The Constitution is normative. Repository implementation facts are time-sensitive and belong in `docs/status`, `docs/audit` and executable work packages. The following section was removed from the constitutional roadmap on 2026-07-26 to eliminate status drift.

## Extracted historical text

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
