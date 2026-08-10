# Research and Strategy Validation Engineering Completion

> **Status:** CURRENT_SPECIFICATION
> **Authority:** Current user request, Constitution 00-09, Architecture 09-16, and current executable authorities
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-10
> **Baseline:** `origin/main@66d9e8cac5015684a179de18c854ab4991423e87`
> **Supersedes:** None
> **Superseded By:** None
> **Related Documents:** ../plans/2026-08-10-research-strategy-validation-engineering.md, ../../architecture/16-Phase-A-Correctness-and-Research-Shadow-Operations.md
> **Code Evidence:** `src/market_regime_alpha`; `tests`; PostgreSQL migrations 001-042
> **Authority Ceiling:** Engineering completion only. No real Formal PIT, Formal OOS, Alpha validation, Entry qualification, Holding/Exit validation, sustained Strategy Shadow proof, or Production authorization.

## 1. Objective and starting facts

Build every machine required to validate Research and Strategy without inventing
the evidence that those machines must later consume. Current code already owns
Canonical Runtime, PostgreSQL Authority, StateSeries/State Policy, PIT
Authority, Model Governance, Research Shadow, Research Panel V2, Target
Protocols, factual Outcomes, real Fill-derived Position Authority and
Holding/Exit production-decision mechanics. This work extends those owners; it
does not create replacements.

Verified gaps at the baseline are:

- Research Panel V2 defaults to four Candidate scores and accepts externally
  assembled factor mappings; it does not copy all canonical variables itself.
- no general versioned factor-ablation or liquidity/capacity assessment exists;
- Canonical PathForecast defaults to an unavailable sample provider;
- no independent calibration or locked formal evaluation runtime exists;
- Entry has no research-to-qualification evidence chain;
- Research Shadow stops at Candidate/Signal/Forecast outcomes and has no
  separate Entry-to-strategy lifecycle;
- Production Governance has no unified admission projection;
- Prospective Attestation trusts settlement caller clock/origin values;
- Canonical free-data StateSeries derives a Universe identity from metadata
  instead of binding the actual Daily Operational Universe Policy.

## 2. Chosen architecture

### 2.1 Panel enrichment, not a parallel feature authority

`ResearchPanelEnrichment` references one immutable Panel V2 and copies values
from verified Canonical Dataset, Feature Bundle V2, State, Dynamic Pool,
Candidate, Signal V3 and PathForecast artifacts. It never computes a competing
factor. Each exposure records family, source kind, raw numeric/text value,
optional normalized value and contribution only when the source owns them,
gate result, missingness, availability and exact source ID/hash/config/model
lineage. The enrichment and per-row exposures are content-addressed and
append-only in PostgreSQL.

### 2.2 One validation bounded context over existing evidence owners

The new `application/research_validation` package owns protocols, immutable run
results and admission projections. Large or complete populations remain
immutable artifacts; PostgreSQL stores their canonical payloads and indexes.
Its components are:

```text
Panel Enrichment
  -> Ablation Protocol/Run
  -> Liquidity/Capacity Assessment
  -> Historical Sample Registry/Reader/Provider
  -> Calibration Protocol/Fit/Evaluation
  -> Formal Evaluation Protocol/Run
  -> Entry Research/Evaluation/Qualification Evidence
  -> Holding/Exit Validation Evidence
  -> Production Admission Decision
```

PIT source qualification is consumed from the existing PIT Authority. Formal
Evaluation may execute on fixture/exploratory data, but only a dataset carrying
`REAL_FORMAL_PIT` and eligible locked partitions can emit Formal OOS evidence.
Otherwise the run is `ENGINEERING_ONLY` or `BLOCKED`.

### 2.3 Strategy Shadow is a downstream workflow, not a Runtime or Position owner

`application/strategy_shadow` attaches a session to an existing Continuous
Runtime Run/Tick and frozen Research Shadow Decision. Its objects are named and
typed `ShadowEntry`, `ShadowFill`, `ShadowPosition`, `ShadowHoldingAssessment`,
`ShadowExitAssessment` and `StrategyOutcome`. They never import or mutate the
real Order, Fill, Broker or Position repositories.

The workflow supports schedule, optimistic-CAS resume/recovery, immutable
events, replay, settlement, incident/drift records and daily reports. Exit
policies cover fixed time, signal reversal, Market/Theme/Capital deterioration,
trailing/protection rules and multiple horizons. A completed engineering
session is never sustained prospective proof.

## 3. Component contracts

### Full Factor Extraction and Panel Enrichment

Families cover Price, Price Action, Volume, Amount, MA/EMA, MACD, VWAP,
Volatility, Momentum/Trend, Liquidity, Market Regime, ETF, Theme, Capital,
Dynamic Pool, Candidate, Intraday, Signal and Forecast. Dataset values are
copied from the latest available canonical bar at the decision boundary;
Feature values are copied from `TechnicalFeatureValue`; State, Pool, Candidate,
Signal and Forecast values are copied from their canonical artifacts. Text
states and missing values are preserved, not numerically fabricated.

### Ablation

`AblationProtocol` freezes Full/No Market/No Theme/No Capital/No Dynamic Pool,
Price-only, Volume-only, Price+Volume, Static/Dynamic and arbitrary single/group
deletions. `AblationEngine` deterministically evaluates IC, Rank IC, Top-K,
Spread, Hit Rate, Return, MFE/MAE, Turnover, Drawdown, Overlap and Incremental
Lift from frozen row/outcome observations. Every result is `EXPLORATORY` and is
rejected if asked to claim Formal OOS or qualification.

### Liquidity and Capacity

The engine separates `OBSERVED_FACT`, `ENGINEERING_ASSUMPTION` and
`CALIBRATED_PARAMETER`. It records ADV5/20, median amount, turnover,
participation, position/order-to-ADV, suspension/limit status, estimated
slippage, impact, fillability and capacity ceiling. Impact/slippage can be
computed under an identified assumption but remain uncalibrated until a
separate Calibration Artifact is bound.

### Historical samples and calibration

`HistoricalSampleDataset` binds target, outcome, PIT lineage and availability.
Registry statuses are `UNQUALIFIED`, `PIT_ELIGIBLE`, `OOS_ELIGIBLE`, and
`QUALIFIED`; status changes are append-only evidence transitions, never inferred
from the current Signal. The PathForecast provider reads only samples available
strictly before DecisionTime and reports their qualification ceiling.

Calibration implements versioned Logistic/Platt, Isotonic and Binning fits.
Fit, validation and OOS roles are disjoint by sample identity. Evaluation emits
Brier, Log Loss, reliability bins, ECE and coverage. Current artifacts always
declare `calibrated=false` until qualified OOS calibration evidence exists.

### Formal evaluation and Entry qualification

The evaluation protocol owns Train, Validation and Locked OOS partitions,
walk-forward folds, purging and embargo. Embargo is derived from the maximum
Target label interval end; there is no hard-coded day count. Metric bundles may
include bootstrap confidence intervals, multiple-testing adjustments,
sensitivity and regime/liquidity/market-cap/theme slices.

Entry research compares Candidate-only, Candidate+Signal,
Candidate+Forecast and Candidate+Intraday assessments. Qualification evidence
requires a qualified Formal Evaluation, Calibration where probabilities are
used, and protocol thresholds. No code path changes Canonical Entry or unlocks
`ENTER`; the current projection remains `entry_qualified=false`.

### Admission

One content-addressed `ProductionAdmissionDecision` evaluates Formal PIT,
Formal OOS, economic validation, Calibration, cost/capacity, Entry,
Holding/Exit, sustained Strategy Shadow, operator approval, Auth/RBAC and Broker
readiness. Results are `BLOCKED`, `ELIGIBLE_FOR_OPERATOR_REVIEW`, or
`AUTHORIZED`. Authorization requires every Governance floor and a separately
recorded operator authority; no automatic promotion or Champion mutation is
performed.

## 4. Authority hardening

Continuous `run-due` persists a `DurableRuntimeEvidence` row after enforcing
the PostgreSQL/host clock constraint and deriving origin from the executable
Runtime path. Prospective settlement loads this row by Run/Tick; settlement
callers cannot assert the final clock/origin.

Operational Universe Artifact V2 binds the exact `DailyUniversePolicy`
ID/hash/version supplied by free-data preparation. Canonical StateSeries uses
that binding. V1 Readers remain valid; V1 artifacts are not rewritten.

## 5. Persistence, recovery and repair

Migrations are additive and use append-only triggers for immutable protocols,
artifacts, results and evidence. Strategy session projections use versioned CAS;
their event stream and strategy objects are append-only. Recovery replays
canonical JSON and exact IDs/hashes, resumes unfinished folds/sessions, and
preserves failed, negative and inconclusive results.

Rollback means stop new writers and keep existing Readers. Forward repair uses
new protocol/artifact identities or explicit invalidation; no immutable row is
updated or deleted.

## 6. Acceptance and evidence ceiling

Focused tests cover deterministic extraction, missingness/lineage, ablation
metrics, capacity assumptions, sample availability/qualification, split
isolation, target-derived embargo, Formal PIT gating, Entry fail-closure,
Shadow replay/recovery/no-trade-authority and Admission floors. PostgreSQL tests
cover fresh/incremental migration, idempotency, append-only protection and CAS.

The maximum claims are the engineering-ready declarations requested by the
user. The following remain false until later real evidence is recorded:

```text
REAL_FORMAL_PIT
FORMAL_OOS
ALPHA_VALIDATED
ENTRY_QUALIFIED
HOLDING_EXIT_VALIDATED
STRATEGY_SHADOW_PROVEN
PRODUCTION_AUTHORIZED
```
