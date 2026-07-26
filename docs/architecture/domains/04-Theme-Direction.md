# Theme Direction Domain

> **Status:** CURRENT_ARCHITECTURE  
> **Authority:** Canonical bounded-context design for Theme Direction  
> **Owner:** Theme Direction domain  
> **Last Updated:** 2026-07-26  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** ../01-Domain-Boundaries.md, ../../specs/README.md, ../../roadmap/work-packages/README.md  
> **Code Evidence:** path:no canonical Phase D implementation; path:Legacy concept/theme observations

## Responsibility

Own PIT theme membership, breadth, leaders, relative strength and quantified lifecycle state.

## Owned entities

- `ThemeDirectionSnapshot`
- `ThemeDirectionRow`
- `ThemeMembershipSnapshot`

Only this domain may create or supersede these authoritative entities.

## Commands

- `BuildThemeMembership`
- `AssessThemeBreadth`
- `ClassifyThemePhase`
- `FreezeThemeDirectionSnapshot`

Commands are idempotent by an explicit request key and either produce immutable artifacts/events or a structured failure.

## Queries

- `GetThemeDirection`
- `ListThemeMembers`
- `ExplainThemePhase`
- `ListThemeLeaders`

Queries are read-only projections and return canonical source IDs.

## Events

- `ThemeMembershipFrozen`
- `ThemeDirectionSnapshotFrozen`
- `ThemeDirectionBlocked`

Events carry aggregate identity, schema version, occurred time, correlation ID and causation ID.

## Input contracts

- PIT theme mapping
- eligible stock population
- member features
- registered lifecycle rules

## Output contracts

- ThemeDirectionSnapshot
- theme-member evidence

## Upstream domains

- Data Source and PIT
- Calendar and Universe
- Feature and Factor
- ETF Direction

## Downstream domains

- Candidate Discovery
- Entry
- Portfolio
- Review and Attribution

## Invariants

- Theme membership is versioned and PIT.
- Lifecycle labels use quantitative evidence.
- Leader selection uses declared rules and complete membership.

## Failure modes

| # | Failure | Required behavior |
|---|---|---|
| `1` | historical membership unavailable | Fail closed; emit domain error/event and preserve input evidence. |
| `2` | member coverage insufficient | Fail closed; emit domain error/event and preserve input evidence. |
| `3` | phase without evidence | Fail closed; emit domain error/event and preserve input evidence. |
| `4` | theme definition drift | Fail closed; emit domain error/event and preserve input evidence. |

## Current code mapping

- `no canonical Phase D implementation`
- `Legacy concept/theme observations`

## Missing implementation

- PIT mapping store
- theme breadth/leader materializer
- theme lifecycle validation lane

## Transaction and persistence boundary

One command commits one owning-domain aggregate and its outbox event atomically. Cross-domain orchestration uses identities/events; no command mutates another domain's aggregate.

## Compatibility rule

Legacy adapters may translate input/output shapes but cannot become the authority owner or increase evidence level.
