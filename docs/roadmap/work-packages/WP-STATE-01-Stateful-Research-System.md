# WP-STATE-01 — Stateful Research System and Dynamic Stock Pool

> **Status:** CURRENT_STATUS
> **Authority:** Delivered local-engineering work package for stateful research
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-06
> **Related Documents:** ../../superpowers/specs/2026-08-06-wp-state-01-state-system-design.md, ../../superpowers/plans/2026-08-06-wp-state-01-state-system.md, ../../runbooks/Stateful-Research-Runtime.md, ../../evidence/WP-STATE-01-Acceptance.md
> **Code Evidence:** `src/market_regime_alpha/research/state_system`, `src/market_regime_alpha/application/state_system`, migrations 022 and 023, `tests/research/state_system`, `tests/application/state_system`

## 1. Delivered outcome

WP-STATE-01 adds four deterministic state domains and one immutable Dynamic
Stock Pool authority beneath the sole Continuous Research Runtime:

```text
validated Evidence
→ Observable Snapshot
→ Proposed State
→ domain Transition Evaluation
→ Effective State
→ Transition Event
→ Dynamic Stock Pool
→ existing Candidate Discovery
→ Signal V4 research projection
→ empirical PathForecast V2 projection
```

It does not add a Provider, Dataset/Feature materializer, Scheduler, Canonical
Lifecycle or parallel research runtime. The existing V0 Market/Theme/Capital
artifacts and historical Readers remain unchanged.

## 2. Domain state machines

Each domain owns a separate Observation, State, Transition and versioned policy.
Shared code is limited to content identity, lineage, time guards and common
threshold value objects.

```text
Market: DATA_INSUFFICIENT ↔ RISK_OFF ↔ DEFENSIVE ↔ NEUTRAL ↔ RISK_ON ↔ OVERHEATED

ETF:    DATA_INSUFFICIENT ↔ DORMANT ↔ STARTING ↔ STRENGTHENING ↔ LEADING
                                      ↘ DIVERGING ↔ WEAKENING ↔ FAILED

Theme:  DATA_INSUFFICIENT ↔ DORMANT ↔ STARTING ↔ STRENGTHENING ↔ LEADING
                                      ↘ DIVERGING ↔ WEAKENING ↔ FAILED

Capital: DATA_INSUFFICIENT ↔ CONTRACTION_BIAS ↔ ACCUMULATION_BIAS
                           ↔ EXPANSION_BIAS ↔ DISTRIBUTION_BIAS
```

Transitions use distinct enter/exit thresholds, hysteresis, confirmation count,
minimum dwell, counter evidence and a fail-closed missing-data policy. One
observation cannot jump across multiple lifecycle positions. Insufficient
coverage enters `DATA_INSUFFICIENT` without retaining a stale permission state.

ETF and Theme share compatible lifecycle vocabulary but not one generic state
machine. Theme evaluation binds explicit effective-dated many-to-many mapping,
ETF states, breadth, participation, leader resonance, concentration and amount
persistence. Missing mapping records `THEME_MAPPING_INCOMPLETE`; membership is
never guessed or projected backward.

Capital outputs observable-proxy inference only. It cannot assert investor
identity, institutional ownership, state-fund activity or actual accumulation
by a named actor.

## 3. State Artifact invariant

Every persisted state binds:

- State, previous State and proposed/effective values;
- State entered time, duration, observations and confirmations;
- enter/exit thresholds, minimum dwell and hysteresis;
- coverage, missing and counter evidence, and reason codes;
- Model ID/version and Configuration ID/hash;
- Provider Attempts, Evidence, Dataset, Feature and source Artifact IDs;
- parent Continuous Operation, Runtime Tick, As-of Time and AvailableAt.

Identity excludes wall-clock execution time. The same Observation, previous
State, model/configuration and As-of Time reproduce the same State and
Transition identity. `AvailableAt > AsOfTime` is rejected. A late correction
creates a new version and never rewrites an intraday Artifact.

## 4. Dynamic Stock Pool authority

`DynamicStockPoolVersion` is the only dynamic-pool fact accepted by the new
Candidate binding. `RequestScopedUniverse` remains only an upstream acquisition
scope. Pool evaluation requires an allowed Rotation state, minimum dwell,
minimum evidence coverage, Eligibility and a material-change threshold.

Each version retains the complete included/excluded cross section, member gate,
score, rank, exclusion reasons, data coverage, Eligibility, liquidity, board,
ST/suspension/listing-age, Theme overlap, added/removed symbols and all source
State IDs. An immaterial change returns `NO_MATERIAL_POOL_CHANGE` and reuses the
previous Pool ID. History is append-only.

## 5. Candidate, Signal and Forecast bindings

`StateBoundCandidateSet` requires exact State/Pool/Tick lineage and the complete
Pool cross section; Top-K-only input is rejected. A repeated-exposure audit
reports Momentum, Price Action, Volume, Amount, ETF, Theme, Capital and Signal
lineage without changing weights or claiming economic improvement.

New Signal writes use `factor_coverage` and only
`DATA_INSUFFICIENT`, `INACTIVE`, `WATCH`, or `CONFIRMED_FOR_RESEARCH`. Historical
Readers continue to decode `confidence` for old Artifacts, but the new writer
does not call it predictive confidence.

Forecast remains `EMPIRICAL_PATH_DISTRIBUTION` and `NOT_CALIBRATED`; it emits no
positive-return probability. Missing sample authority returns
`DATA_INSUFFICIENT`.

## 6. Persistence and recovery

Migration 022 adds 17 explicit tables: Observation/State/Transition for four
domains, one current-pointer table, Pool/version/member/change tables and a
State Runtime receipt. Migration 023 registers `STATE_SYSTEM` as the fifth
ordered Continuous child. PostgreSQL is the only database writer and replay
authority.

PostgreSQL writes validate the active Tick Claim, Lease, fencing token and Tick
version before final commit. History is append-only; current pointers use CAS.
Concurrent identical writes converge on one Artifact. A stale worker cannot
publish State, Pool or the final State Runtime receipt. SQL triggers enforce
immutability and pointer monotonicity only; business transitions are visible in
Python.

## 7. Authority ceiling

Market State, Rotation, Capital inference, Dynamic Pool, Candidate, Signal and
Forecast are research Artifacts. They grant neither Research permission as a
trading right nor Entry, Opportunity, Order, Fill, Position or Broker authority.
WP-STATE-01 does not deliver Daily Decision Summary, account observation,
reconciliation, Portfolio/Risk wiring, complete Model Registry selection,
economic validation, Shadow Runtime, pages, QMT, PTrade, XtQuant or automatic
model promotion.
