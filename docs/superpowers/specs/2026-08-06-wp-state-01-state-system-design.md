# WP-STATE-01 Stateful Research System Design

> **Status:** CURRENT_SPECIFICATION
> **Authority:** Additive design for stateful research under the Continuous Research Runtime
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-06

## Outcome and boundary

WP-STATE-01 adds deterministic, recoverable Market, ETF Rotation, Theme
Rotation and Capital states plus an immutable Dynamic Stock Pool. It consumes
only Evidence available by the Runtime Tick As-of Time and runs only as a child
of the existing Continuous Research parent. It reuses V0 snapshots, canonical
Feature/Candidate/Signal/PathForecast services and their Readers. It creates no
second Provider, Dataset, Feature, Candidate, Signal, Forecast, Canonical
Lifecycle, scheduler or research runtime.

It does not implement DailyDecisionWindowSummary, account observation,
reconciliation, Portfolio/Risk, model-registry selection, economic validation,
Shadow operation, pages, Broker, QMT, PTrade, XtQuant, Order, real Fill or
Position mutation. Entry remains fail closed.

## State flow

```text
Evidence
-> domain Observation
-> Proposed State
-> domain Transition Policy
-> Effective State
-> Transition Event
-> Dynamic Stock Pool evaluation
-> existing Candidate Discovery
-> Signal V4 research projection
-> empirical PathForecast projection
```

Observation and Effective State are separate immutable Artifacts. A proposed
state never overwrites an Effective State. Each domain owns its vocabulary and
transition evaluator; shared code is limited to lineage, content identity and
time validation.

## Determinism and time

Every Observation, State, Transition, Pool and research binding is content
addressed. Identity binds the prior State, Observation, explicit Model ID and
Version, Configuration ID and hash, As-of Time, AvailableAt, source Artifact
IDs, Continuous Operation, Runtime Tick and Provider/Evidence lineage. CreatedAt
is audit metadata and is not part of the transition decision. `AvailableAt <=
AsOfTime` is mandatory. A later correction produces a new Observation and State
version; it never mutates a past Artifact.

## Versioned configuration

Four domain-specific configuration contracts contain enter/exit thresholds,
confirmation count, minimum dwell, hysteresis, minimum coverage and missing-data
policy. Dynamic Pool configuration contains the allowed rotation states,
minimum state dwell, minimum evidence coverage and material-change threshold.
The Runtime command explicitly selects all Model/Configuration identities. No
service contains an unversioned default threshold.

## Market Regime

The existing V0 `MarketRegimeSnapshot` and Reader remain unchanged. The new
state vocabulary is `DATA_INSUFFICIENT`, `RISK_OFF`, `DEFENSIVE`, `NEUTRAL`,
`RISK_ON`, `OVERHEATED`. The evaluator uses the persisted V0 observable scores,
coverage and counter evidence. Enter and exit thresholds differ; a single pulse
cannot cross multiple states. Research Permission and Exposure Ceiling are
separate projections, and Trading Authority is always false.

## ETF and Theme Rotation

ETF Rotation observations carry 1/3/5/10-day relative strength, benchmark
excess, amount/volume change and persistence, drawdown, volatility, diffusion,
liquidity and coverage. Lifecycle states are `DATA_INSUFFICIENT`, `DORMANT`,
`STARTING`, `STRENGTHENING`, `LEADING`, `DIVERGING`, `WEAKENING`, `FAILED`.
`LEADING` requires persisted multi-observation confirmation and cannot result
from one ETF pulse.

Theme Rotation is a separate model and transition policy. Its Observation binds
versioned many-to-many ETF-to-Theme mapping, verified ETF states, stock breadth,
participation, leader resonance, concentration, amount persistence and evidence
coverage. Missing mapping emits `THEME_MAPPING_INCOMPLETE`; no current mapping
is projected backward and membership is never guessed.

## Capital State

Capital State describes only observable proxy behavior. States are
`DATA_INSUFFICIENT`, `CONTRACTION_BIAS`, `ACCUMULATION_BIAS`, `EXPANSION_BIAS`,
`DISTRIBUTION_BIAS`. Output language and reason codes cannot assert investor
identity, institutional ownership, accumulation by a real actor or state-fund
activity.

## Dynamic Stock Pool

`DynamicStockPoolVersion` is the only dynamic stock-pool fact consumed by new
Candidate Discovery. `RequestScopedUniverse` remains an upstream acquisition
scope. A Pool version binds all effective State IDs, Eligibility, liquidity,
board, ST, suspension, listing-age and Theme-overlap facts. It records the full
included and excluded cross section plus added/removed members. The evaluator
requires qualified Rotation State, minimum dwell, minimum evidence coverage,
Eligibility and a material member-change threshold. Identical or immaterial
input returns `NO_MATERIAL_POOL_CHANGE` and reuses the prior Pool identity.

## Research integration

Candidate V3 is an additive binding around the existing complete CandidateSet.
It verifies that every Candidate record belongs to the Dynamic Pool cross
section and binds Pool, Market, ETF, Theme, Capital, Feature Bundle and Runtime
Tick identities. The full included/excluded/gate/score/rank/reason cross section
is retained. A lineage audit reports repeated Momentum, Price Action, Volume,
Amount, ETF, Theme, Capital and Signal exposures without changing weights.

Signal V4 writes `factor_coverage`; it never calls that value predictive
confidence. Its states remain `DATA_INSUFFICIENT`, `INACTIVE`, `WATCH`,
`CONFIRMED_FOR_RESEARCH`. The V1-V3 Readers continue to read historical
`confidence` unchanged; a compatibility projection may expose it as legacy
factor coverage but may not promote it to probability.

Forecast V2 remains `EMPIRICAL_PATH_DISTRIBUTION` and `NOT_CALIBRATED`. It may
label `UP_BIAS`, `DOWN_BIAS`, `NEUTRAL`, or `DATA_INSUFFICIENT`, stores sample
count/coverage/distribution and all source State/Pool IDs, and never emits an
uncalibrated positive-return probability. The unavailable sample provider keeps
the result fail closed.

## Persistence

Migration 022 adds explicit Observation/State/Transition tables for all four
domains, Dynamic Pool/version/member/change tables and State Runtime receipts.
PostgreSQL is the default writer. SQLite implements the same public repository
contract only when explicitly selected for compatibility/replay. History tables
are append-only; current pointers use CAS and active Continuous Tick fencing.
Business transitions are computed in Python and persisted explicitly—SQL
triggers enforce immutability only and do not invent state.

## Acceptance

Acceptance requires deterministic replay, restart recovery, PostgreSQL CAS and
concurrency, SQLite parity, future-data rejection, unchanged historical 14:55
Target/Reader/Replay, no duplicate no-change computation, and static authority
tests proving no Opportunity, Order, Fill, Position or Broker path was added.
