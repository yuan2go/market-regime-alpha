# Market Context Domain

> **Status:** CURRENT_ARCHITECTURE  
> **Authority:** Canonical bounded-context design for Market Context  
> **Owner:** Market Context domain  
> **Last Updated:** 2026-07-26  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** ../01-Domain-Boundaries.md, ../../specs/README.md, ../../roadmap/work-packages/README.md  
> **Code Evidence:** path:MR2 research paths; path:Legacy market environment components

## Responsibility

Own descriptive market breadth, regime and risk-state snapshots; no default hard-gate authority.

## Owned entities

- `MarketContextSnapshot`
- `MarketBreadthRow`
- `RegimeAssessment`

Only this domain may create or supersede these authoritative entities.

## Commands

- `MaterializeMarketContext`
- `AssessRegime`
- `FreezeMarketContext`

Commands are idempotent by an explicit request key and either produce immutable artifacts/events or a structured failure.

## Queries

- `GetMarketContext`
- `GetRegimeEvidence`
- `CompareContextWindows`

Queries are read-only projections and return canonical source IDs.

## Events

- `MarketContextFrozen`
- `MarketContextBlocked`

Events carry aggregate identity, schema version, occurred time, correlation ID and causation ID.

## Input contracts

- eligible market population
- index/market bars
- breadth and turnover features
- registered methodology

## Output contracts

- MarketContextSnapshot
- descriptive regime evidence

## Upstream domains

- Data Source and PIT
- Calendar and Universe
- Feature and Factor

## Downstream domains

- Candidate Discovery
- Entry
- Portfolio
- Review and Attribution

## Invariants

- Context is descriptive until incremental value is proven.
- No regime label without evidence codes.
- Context timing cannot exceed decision time.

## Failure modes

| # | Failure | Required behavior |
|---|---|---|
| `1` | breadth coverage too low | Fail closed; emit domain error/event and preserve input evidence. |
| `2` | index population mismatch | Fail closed; emit domain error/event and preserve input evidence. |
| `3` | regime method unavailable | Fail closed; emit domain error/event and preserve input evidence. |
| `4` | context hard-gate used without approval | Fail closed; emit domain error/event and preserve input evidence. |

## Current code mapping

- `MR2 research paths`
- `Legacy market environment components`

## Missing implementation

- Phase D MarketContextSnapshot implementation
- ablation-ready context registry
- role-specific approval for feature/gate/budget use

## Transaction and persistence boundary

One command commits one owning-domain aggregate and its outbox event atomically. Cross-domain orchestration uses identities/events; no command mutates another domain's aggregate.

## Compatibility rule

Legacy adapters may translate input/output shapes but cannot become the authority owner or increase evidence level.
