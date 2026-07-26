# ETF Direction Domain

> **Status:** CURRENT_ARCHITECTURE  
> **Authority:** Canonical bounded-context design for ETF Direction  
> **Owner:** ETF Direction domain  
> **Last Updated:** 2026-07-26  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** ../01-Domain-Boundaries.md, ../../specs/README.md, ../../roadmap/work-packages/README.md  
> **Code Evidence:** path:no canonical Phase D implementation; path:Legacy/prototype ETF backtests

## Responsibility

Own PIT ETF universe, relative-strength/flow context and ETF-specific ranking evidence.

## Owned entities

- `ETFDirectionSnapshot`
- `ETFDirectionRow`
- `ETFMapping`

Only this domain may create or supersede these authoritative entities.

## Commands

- `BuildETFUniverse`
- `RankETFDirections`
- `FreezeETFDirectionSnapshot`

Commands are idempotent by an explicit request key and either produce immutable artifacts/events or a structured failure.

## Queries

- `GetETFDirection`
- `ListRankedETFs`
- `ExplainETFScore`

Queries are read-only projections and return canonical source IDs.

## Events

- `ETFDirectionSnapshotFrozen`
- `ETFDirectionBlocked`

Events carry aggregate identity, schema version, occurred time, correlation ID and causation ID.

## Input contracts

- ETF universe
- ETF bars/turnover
- theme mappings
- registered ETF methodology

## Output contracts

- ETFDirectionSnapshot
- ETF context references

## Upstream domains

- Data Source and PIT
- Calendar and Universe
- Feature and Factor

## Downstream domains

- Theme Direction
- Candidate Discovery
- Portfolio
- Review and Attribution

## Invariants

- ETF and stock semantics remain distinct.
- Flow proxies declare provider authority.
- Rank does not imply trade action.

## Failure modes

| # | Failure | Required behavior |
|---|---|---|
| `1` | ETF universe incomplete | Fail closed; emit domain error/event and preserve input evidence. |
| `2` | fund metadata stale | Fail closed; emit domain error/event and preserve input evidence. |
| `3` | flow proxy unqualified | Fail closed; emit domain error/event and preserve input evidence. |
| `4` | liquidity threshold unavailable | Fail closed; emit domain error/event and preserve input evidence. |

## Current code mapping

- `no canonical Phase D implementation`
- `Legacy/prototype ETF backtests`

## Missing implementation

- PIT ETF universe and mappings
- ETFDirectionSnapshot service
- ETF outcome and scorecard lane

## Transaction and persistence boundary

One command commits one owning-domain aggregate and its outbox event atomically. Cross-domain orchestration uses identities/events; no command mutates another domain's aggregate.

## Compatibility rule

Legacy adapters may translate input/output shapes but cannot become the authority owner or increase evidence level.
