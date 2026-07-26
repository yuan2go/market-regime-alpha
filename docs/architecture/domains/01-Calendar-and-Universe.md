# Calendar and Universe Domain

> **Status:** CURRENT_ARCHITECTURE  
> **Authority:** Canonical bounded-context design for Calendar and Universe  
> **Owner:** Calendar and Universe domain  
> **Last Updated:** 2026-07-26  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** ../01-Domain-Boundaries.md, ../../specs/README.md, ../../roadmap/work-packages/README.md  
> **Code Evidence:** path:src/market_regime_alpha/data/trading_calendar.py; path:src/market_regime_alpha/universe/**

## Responsibility

Own sessions, PIT stock/ETF membership, eligibility and complete population accounting.

## Owned entities

- `TradingCalendar`
- `MarketSession`
- `UniverseSnapshot`
- `EligibilitySnapshot`
- `ExclusionRecord`

Only this domain may create or supersede these authoritative entities.

## Commands

- `BuildTradingCalendar`
- `BuildUniverseSnapshot`
- `EvaluateEligibility`
- `FreezePopulation`

Commands are idempotent by an explicit request key and either produce immutable artifacts/events or a structured failure.

## Queries

- `GetSession`
- `ListUniverseMembers`
- `ExplainExclusion`
- `GetEligiblePopulation`

Queries are read-only projections and return canonical source IDs.

## Events

- `UniverseSnapshotFrozen`
- `EligibilityEvaluated`
- `PopulationBlocked`

Events carry aggregate identity, schema version, occurred time, correlation ID and causation ID.

## Input contracts

- calendar artifacts
- listing/ST/suspension/membership facts
- liquidity observations
- universe policy

## Output contracts

- UniverseSnapshot
- EligibilitySnapshot
- complete Candidate population and explicit exclusions

## Upstream domains

- Data Source and PIT

## Downstream domains

- Feature and Factor
- Candidate Discovery
- ETF Direction
- Theme Direction

## Invariants

- Membership is as-of decision time.
- Unknown eligibility fails closed.
- Every excluded instrument has a reason code.
- Population totals reconcile exactly.

## Failure modes

| # | Failure | Required behavior |
|---|---|---|
| `1` | missing historical membership | Fail closed; emit domain error/event and preserve input evidence. |
| `2` | calendar mismatch | Fail closed; emit domain error/event and preserve input evidence. |
| `3` | ambiguous ST/suspension effective time | Fail closed; emit domain error/event and preserve input evidence. |
| `4` | coverage below protocol | Fail closed; emit domain error/event and preserve input evidence. |

## Current code mapping

- `src/market_regime_alpha/data/trading_calendar.py`
- `src/market_regime_alpha/universe/**`

## Missing implementation

- canonical daily stock/ETF universe service
- PIT theme/industry/ETF mappings
- production liquidity policy registry

## Transaction and persistence boundary

One command commits one owning-domain aggregate and its outbox event atomically. Cross-domain orchestration uses identities/events; no command mutates another domain's aggregate.

## Compatibility rule

Legacy adapters may translate input/output shapes but cannot become the authority owner or increase evidence level.
