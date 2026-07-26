# Capital Context Domain

> **Status:** CURRENT_ARCHITECTURE  
> **Authority:** Canonical bounded-context design for Capital Context  
> **Owner:** Capital Context domain  
> **Last Updated:** 2026-07-26  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** ../01-Domain-Boundaries.md, ../../specs/README.md, ../../roadmap/work-packages/README.md  
> **Code Evidence:** path:partial Legacy features; path:no canonical Phase D implementation

## Responsibility

Own market liquidity and capital-flow observations with per-field availability and authority.

## Owned entities

- `CapitalContextSnapshot`
- `CapitalFieldAvailability`

Only this domain may create or supersede these authoritative entities.

## Commands

- `MaterializeCapitalContext`
- `AssessLiquidityState`
- `FreezeCapitalContext`

Commands are idempotent by an explicit request key and either produce immutable artifacts/events or a structured failure.

## Queries

- `GetCapitalContext`
- `GetCapitalFieldAvailability`
- `ExplainLiquidityState`

Queries are read-only projections and return canonical source IDs.

## Events

- `CapitalContextFrozen`
- `CapitalFieldUnavailable`
- `CapitalContextBlocked`

Events carry aggregate identity, schema version, occurred time, correlation ID and causation ID.

## Input contracts

- turnover/breadth observations
- qualified financing/flow fields when available
- source manifest

## Output contracts

- CapitalContextSnapshot

## Upstream domains

- Data Source and PIT
- Calendar and Universe

## Downstream domains

- Market Context
- Candidate Discovery
- Entry
- Portfolio
- Review and Attribution

## Invariants

- Unavailable fields remain null with explicit status.
- No unqualified flow field enters formal evidence.
- Liquidity state is descriptive unless validated.

## Failure modes

| # | Failure | Required behavior |
|---|---|---|
| `1` | field semantics unknown | Fail closed; emit domain error/event and preserve input evidence. |
| `2` | capital field stale | Fail closed; emit domain error/event and preserve input evidence. |
| `3` | optional field used as mandatory | Fail closed; emit domain error/event and preserve input evidence. |
| `4` | authority inflation | Fail closed; emit domain error/event and preserve input evidence. |

## Current code mapping

- `partial Legacy features`
- `no canonical Phase D implementation`

## Missing implementation

- CapitalContextSnapshot service
- availability registry
- incremental validation

## Transaction and persistence boundary

One command commits one owning-domain aggregate and its outbox event atomically. Cross-domain orchestration uses identities/events; no command mutates another domain's aggregate.

## Compatibility rule

Legacy adapters may translate input/output shapes but cannot become the authority owner or increase evidence level.
