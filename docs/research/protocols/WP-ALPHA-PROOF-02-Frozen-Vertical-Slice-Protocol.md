# WP-ALPHA-PROOF-02 Frozen Vertical Slice Protocol

> **Status:** HISTORICAL
> **Authority:** Pre-result execution protocol subordinate to the Canonical Overall Design and existing persisted Experiment owners
> **Decision Date:** 2026-08-25
> **Repository Baseline:** `main@adbc7857e261835eccbe2acf4902910363dae724`
> **Data Cutoff:** `2026-08-25T08:59:24+08:00`; latest completed market session must be resolved by the canonical Trading Calendar
> **Evidence Ceiling:** `FREE_DATA / PIT_INCOMPLETE` unless exact qualified owner evidence proves otherwise; `LOCKED_OOS_CONSUMED=false`; `FORMAL_OOS=false`; `PROSPECTIVE_PROVEN=false`; `PRODUCTION_QUALIFIED=false`

This protocol freezes the WP-ALPHA-PROOF-02 research question before any
Locked OOS Outcome is read. Executable truth remains the content-addressed
`ResearchExperimentDefinition`, Calendar/roster owners, Historical Corpus
owners and append-only Research Evidence in PostgreSQL. This document neither
creates an owner nor upgrades a research result.

## 1. Primary research question

Does the already-discovered, higher-is-better, equal-weight rank-percentile
combination of:

- `intraday_return_to_decision_time`;
- `price_vs_vwap_return`;
- `vwap_slope`;

reproduce from newly acquired physical Raw data and retain stable T+1 10:30
cross-sectional information and non-negative Top-5 net research economics in the
already-frozen Temporal External Validation window?

The valid terminal answers are `SUPPORTED`, `REJECTED`, `NOT_ESTIMABLE` or
`DATA_BLOCKED`. A positive Discovery reproduction is not new discovery and
cannot change Factor direction, composition, weight, Target, Top-K, cost or
qualification floors.

Secondary questions are admitted only after the primary dependency permits
them:

1. Does the canonical Candidate Challenger preserve the supported Factor
   contribution without an unvalidated Context hard gate?
2. Does Conditional Forecast improve on the owner-resolved empirical
   PathForecast and naive baseline under frozen walk-forward rules?
3. Does any existing Strategy family retain positive net economics under the
   frozen conservative A-share execution assumptions?

These questions may return negative or not-estimable results. They cannot
change the primary hypothesis.

## 2. Parent protocols and immutable partitions

WP-ALPHA-PROOF-02 reuses, and does not replace, these frozen parents:

| Item | Immutable value |
|---|---|
| Discovery protocol | `WP-ALPHA-RESEARCH-01` |
| Discovery Experiment | `research-experiment-definition:ab6820cb12247973feab2103684b47b9785d8969b5d4362a595888752f99c02e` |
| Discovery sessions | 126 Decision Sessions, `2025-01-02` through `2025-07-11` |
| Discovery final Target session | `2025-07-14` |
| Discovery Evidence | `historical-evidence-f9326f869186419a89e450b9@sha256:f9326f869186419a89e450b9b64923046a30677d4c3c0003f1f12060388c1fe6` |
| External protocol | `TEMPORAL_VALIDATION_V1` |
| External window | 126 Decision Sessions, `2025-07-15` through `2026-01-16` |
| External final Target session | `2026-01-19` |
| External window owner | `frozen-temporal-validation-window:b9e0dfaf85e5ed006f217b1e4b309347a6e5d296d2a8c09beba4296c0800278e` |
| External window hash | `sha256:b9e0dfaf85e5ed006f217b1e4b309347a6e5d296d2a8c09beba4296c0800278e` |
| External Calendar owner | `trading-calendar-9fc7d108a062caf59596580f@sha256:9fc7d108a062caf59596580fcb47313e1d0e20dbdbd41e81a677d986191f7927` |
| Universe | effective-dated CSI 300, 300 active members per Decision Session |
| DecisionTime | `14:55:00 Asia/Shanghai` |
| Primary Target | next valid trading session `10:30 Asia/Shanghai` return |

The new physical Dataset is a `REACQUIRED_EQUIVALENT_SOURCE`; it must never
impersonate or overwrite the unavailable original physical package. A
reproduction definition binds both the immutable parent protocol and the new
Raw/Normalized owner references and hashes.

## 3. Locked OOS derivation and access gate

The Locked OOS partition changes no Discovery or External boundary. Its roster
is derived once from an exact, hash-verified canonical A-share Trading Calendar:

1. require `2026-01-19` to be the already-frozen External final Target session;
2. take the first explicit Decision Session strictly after `2026-01-19` as the
   Locked OOS start;
3. take Decision Sessions whose adjacent T+1 10:30 Target session was complete
   before the Data Cutoff above;
4. persist the complete ordered Decision-session array, every Target-session
   binding, Calendar reference/hash, roster hash and derivation policy before
   any Locked OOS Outcome read;
5. reject overlap with Discovery or External and reject a Calendar gap,
   inferred weekday, changed cutoff or ambiguous Target session.

Formal PIT is a hard Outcome-access gate:

```text
FORMAL_PIT_SUPPORTED + PHYSICAL_CORRECTNESS_SUPPORTED
→ one owner-controlled Locked OOS unlock may be considered

PIT_INCOMPLETE or PHYSICAL_CORRECTNESS != SUPPORTED
→ LOCKED_OOS_CONSUMED=false
→ do not read, project, evaluate or report Locked OOS Outcomes
→ LOCKED_OOS_SUPPORTED=NOT_ESTIMABLE
```

Raw acquisition may store bytes covering Locked OOS dates, but research query,
Panel, Target, Forecast, Strategy, Evaluation and report surfaces must not read
or aggregate their Outcome values while the gate is closed. Locked observations
cannot be exposed as a retrospective diagnostic.

## 4. Physical acquisition and PIT contract

The acquisition scope is `2025-01-01` through the latest completed market
session at the frozen Data Cutoff. Calendar authority, not weekday inference,
resolves the final date. The scope contains:

- Daily OHLCV and amount;
- 5-minute OHLCV and amount;
- effective-dated CSI 300 membership;
- listing, ST, suspension/trading status and eligibility where the provider
  actually supplies them;
- adjustment and corporate-action facts with exact source lineage;
- exact Context instruments only when a real owner exists.

The union of symbols may exceed 300. Each Decision Session uses only its
effective membership. Current membership cannot be projected backwards.

Acquisition extends the existing Historical Corpus authority with staged,
checkpointed partition publication. It must bound decoded records and open
transactions, use finite retry/rate-limit policies, and atomically finalize one
immutable owner manifest only after every expected partition is verified.
Filesystem paths are physical locators only; PostgreSQL owner ID/hash is the
lookup authority. Resume reuses exact request checkpoints. Replay performs no
network I/O and verifies the same semantic and physical hashes.

BaoStock currently supplies retrospective event-time data but not supportable
historical provider availability. Its owner must retain:

```text
RETROSPECTIVE_EVENT_TIME
HISTORICAL_AVAILABLE_TIME_NOT_PROVIDED
PIT_INCOMPLETE
FORMAL_PIT_NOT_ESTABLISHED
```

No task-time timestamp, inferred publication time or copied availability value
may replace the missing fact. Other existing providers may contribute only
through their current canonical PIT/source owners and only when credentials,
source contract and historical evidence actually prove the required Fact Kind.
There is no silent provider substitution.

## 5. Frozen correctness campaign

Correctness reopens the new physical Raw and Normalized packages and uses the
existing independent Phase-II kernels. It does not trust persisted Feature or
Target values as expected output.

Required comparisons cover:

- Raw row parsing and normalized bar identity;
- checksums, exact file set and physical package hash;
- OHLCV/amount integrity, duplicates, missing intervals and trading status;
- effective Universe membership and security facts;
- DecisionTime cutoff and absence of future bars/facts/revisions;
- independent reproduction of the three primary Factors;
- independent Decision reference, T+1 10:30 return, MFE and MAE;
- adjustment/corporate-action exclusion semantics;
- cross-run isolation and deterministic resume/replay.

The frozen negative controls are symbol permutation, target permutation,
target time shift, factor lag and deterministic random ranking. Redundancy uses
pairwise value/rank correlation, leave-one-out, incremental and residual
diagnostics. Inference uses 2,000 moving-block draws, block lengths `(1, 5,
10)`, confidence `0.95`, and seed `20260813`.

Only exact full-population reproduction with every fail-closed temporal and
lineage check satisfied can emit `CORRECTNESS_SUPPORTED`. Correctness does not
mean Alpha support.

## 6. Frozen Factor, Candidate and evaluation semantics

The physical Discovery reproduction reruns the complete pre-registered
WP-ALPHA-RESEARCH-01 registry and retains every positive, negative,
inconclusive and not-estimable result. It may diagnose drift against the old
Evidence but may not select a new Factor.

External Validation consumes only:

| Dimension | Frozen value |
|---|---|
| Factors | the three Factors in the Primary Research Question |
| Directions | `HIGHER_IS_BETTER` for all three |
| Composite | `EQUAL_WEIGHT_RANK_PERCENTILE` |
| Ranking | Golden Loop V2 exact-rational arithmetic midrank |
| Boundary | `FRACTIONAL_BOUNDARY_WEIGHT_V1` |
| Primary Top-K | `5` |
| Research round-trip cost | `0.002100` |
| Minimum observation coverage | `0.80` |
| Minimum Discovery RankIC retention | `0.50` |
| Minimum Top-5 net return | `0` |
| Multiple testing | existing `BENJAMINI_HOCHBERG_FDR` family |
| Bootstrap | 2,000 draws; blocks `(1, 5, 10)`; seed `20260813` |
| Stopping rule | exhaust exactly the frozen External roster once; no result-dependent change |

External is `SUPPORTED` only when the existing evaluator finds the frozen
population estimable, coverage meets its floor, RankIC retention is at least
0.50, and Top-5 net is non-negative. Otherwise it is `REJECTED` or
`NOT_ESTIMABLE`. Under free-data `PIT_INCOMPLETE`, even `SUPPORTED` remains
Temporal External research evidence and never becomes Formal OOS.

Candidate layers are fixed as:

```text
Universal Integrity / PIT legality / effective eligibility
→ externally supported Alpha Factors only
→ independently supported Context only
```

The Incumbent is immutable. The Challenger is
`HARD_INTEGRITY_PRICE_RETURN`, Top-5 with fractional boundary ties. Market,
ETF, Theme and Capital cannot be hard predictive gates without same-Experiment
support. Missing Context remains explicit; it cannot reject the whole Alpha
population. Per-symbol validated contributions bind exposure, percentile,
direction, equal weight, contribution, Context adjustment, final score and the
exact External/Candidate Evidence references. Exploratory Features remain
diagnostics.

Signal reuses Signal V3. No new heuristic or threshold is admitted.

## 7. Forecast, Strategy and Portfolio scope

Forecast comparison is downstream of a supported External Candidate and uses
only owner-resolved, DecisionTime-admissible samples outside Locked OOS:

1. unconditional/naive mean baseline;
2. empirical PathForecast median and path distribution;
3. deterministic regularized-linear Conditional Forecast.

The Conditional model uses only the three frozen Alpha inputs, targets T+1
return/MFE/MAE plus raw upper/lower barrier heads, expanding owner-controlled
walk-forward folds, a one-target-session purge/embargo, penalties `(0.1, 1)`,
no more than two candidate fits per fold, seed `20260813`, and no stochastic
optimization. The exact fold/session owner fixes sample floors before fitting.
If owner-resolved samples cannot meet existing floors, the result is
`NOT_ESTIMABLE`; floors are not lowered. Raw barrier scores are not
probabilities. Calibration runs only after real predictive lift and through the
existing Calibration Authority.

Strategy evaluation reuses Overnight, Swing and Conditional Prediction. A
Forecast-required Strategy consumes exact Candidate, Signal, Forecast,
Context, pre-Strategy Risk and Opportunity owners. No Candidate-score Forecast
substitute exists.

The conservative bar-based economics policy preserves A-share T+1 and 100-share
lot semantics and records commission, stamp duty, spread/slippage, impact,
participation, liquidity, suspension/ST, price-limit, partial-fill and capacity
facts or assumptions separately. It never claims Level-2 queue precision.
Gross, explicit cost, impact/slippage, fillability loss and net are reported
separately. Current uncalibrated cost values remain
`ENGINEERING_ASSUMPTION`. Portfolio remains the existing deterministic simple
cross-strategy policy and creates no Order or physical Position.

Strategy economics and attribution may consume Discovery/External Outcomes
only when their upstream gates permit. They cannot consume Locked OOS while
Formal PIT is incomplete.

## 8. Outcome, attribution and prospective boundary

Every admitted row binds exact Prediction, Candidate, Signal, Forecast,
Strategy diagnostic, Portfolio, Target Session, Market Outcome and Strategy
Outcome references/hashes. Market path return is not Strategy PnL.
Attribution separates Factor, Context, Candidate gate, Signal gate, Forecast
error, Strategy decision, Portfolio constraint, timing, execution and cost.

Research Feedback records support, rejection, not-estimable or blocked states
without automatic promotion. If External is supported, the exact Experiment,
Feature/Factor, Candidate, Signal, Forecast, Strategy, economics and Portfolio
identities may be bound into the existing Continuous/Shadow path for the next
real session without code changes. Historical predictions are never
backfilled. Until real future sessions settle, status is at most
`PROSPECTIVE_READY / ACCUMULATING`; `PROSPECTIVE_PROVEN=false`.

## 9. Architecture and operator design

Selected approach: extend the existing Historical Corpus/Historical Research
operators vertically. Acquisition staging, Corpus finalization, Phase-II
correctness/external execution, Historical run/replay and Evidence reporting
remain bounded operations of the installed `continuous-research` CLI. The CLI
parses input and delegates; it does not become a research state machine.

Rejected alternatives:

- extending the current whole-owner in-memory acquisition/publisher, because
  the real 300-stock Daily+5m scope is not memory-bounded;
- building a standalone backtest/data runner, because that would create a
  second Historical Runtime and Evidence path;
- creating a new generic Evidence/Qualification owner, because existing owners
  already encode the required facts and gates.

`application/daily_loop` remains compatibility-only. The source acquisition
primitive still consumed by Continuous FreeData is extracted behind the
existing `application/source_freeze` boundary; legacy B0/B1/finalization
orchestration is not reactivated. Deletion occurs only after consumer and
differential replay proof.

## 10. TDD seams and acceptance

Tests exercise public seams only:

1. `historical-corpus-acquire` acquire/resume/replay and immutable owner reload;
2. Historical Corpus staged publish/open-index/selective-read corruption checks;
3. `historical-phase-ii` correctness and External operations;
4. canonical Historical run/resume/report/replay;
5. PIT qualification and Locked OOS roster/unlock boundary;
6. Candidate Policy V2 explanation and Daily Alpha contribution projection;
7. Forecast baseline comparison/replay;
8. Strategy/Portfolio economics and attribution report/replay;
9. Continuous source freeze after DailyLoop compatibility extraction.

Regression never skips, xfails, deletes or weakens an existing test or frozen
research floor. PostgreSQL validation discovers schema/table/column identities
from packaged migrations and `pg_catalog`; campaign tooling must not guess a
schema name from a database name.

Final validation includes frozen dependency sync, docs validation, platform and
full pytest, ruff, mypy, build, diff checking, fresh migrations, previous-main
upgrade, migration idempotency/concurrency, append-only constraints, exact
owner reload, acquisition interruption/resume/provider failure, historical and
Forecast replay, settlement idempotency, Strategy/Portfolio replay and physical
corruption detection.

## 11. Result matrix

The final report must populate these fields from owners and commands actually
executed:

```text
FORMAL_PIT
PHYSICAL_CORRECTNESS
DISCOVERY_REPRODUCED
EXTERNAL_VALIDATED
ALPHA_SUPPORTED
LOCKED_OOS_CONSUMED
LOCKED_OOS_SUPPORTED
FORECAST_BASELINE_BEATEN
CALIBRATED
NET_ECONOMICS_SUPPORTED
STRATEGY_QUALIFIED
PROSPECTIVE_READY
PROSPECTIVE_PROVEN
PRODUCTION_QUALIFIED=false
```

If BaoStock remains the strongest available source and its historical
availability is unprovable, `FORMAL_PIT=PIT_INCOMPLETE`,
`LOCKED_OOS_CONSUMED=false`, and `LOCKED_OOS_SUPPORTED=NOT_ESTIMABLE` regardless
of any favorable Discovery or External metric.
