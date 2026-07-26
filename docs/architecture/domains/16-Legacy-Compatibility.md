# Legacy Compatibility Domain

> **Status:** CURRENT_ARCHITECTURE  
> **Authority:** Canonical bounded-context design for Legacy Compatibility  
> **Owner:** Legacy Compatibility domain  
> **Last Updated:** 2026-07-26  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** ../01-Domain-Boundaries.md, ../../specs/README.md, ../../roadmap/work-packages/README.md  
> **Code Evidence:** path:src/market_regime_alpha/dividend_t/**; path:src/market_regime_alpha/legacy/**

## Responsibility

Characterize, adapt and retire Legacy behavior without expanding Legacy God Objects.

## Owned entities

- `LegacyAdapter`
- `CharacterizationEvidence`
- `MigrationDecision`

Only this domain may create or supersede these authoritative entities.

## Commands

- `CharacterizeLegacyBehavior`
- `AdaptLegacyOutput`
- `ApproveLegacyRetirement`

Commands are idempotent by an explicit request key and either produce immutable artifacts/events or a structured failure.

## Queries

- `GetLegacyMapping`
- `CompareLegacyAndCanonical`
- `GetRetirementReadiness`

Queries are read-only projections and return canonical source IDs.

## Events

- `LegacyBehaviorCharacterized`
- `LegacyAdapterVerified`
- `LegacyComponentRetired`

Events carry aggregate identity, schema version, occurred time, correlation ID and causation ID.

## Input contracts

- Legacy code/results
- canonical contracts
- characterization fixtures

## Output contracts

- compatibility adapters
- behavior-diff evidence
- retirement decisions

## Upstream domains

- dividend_t
- Legacy web/backtests

## Downstream domains

- canonical domains during migration

## Invariants

- No big-bang rewrite.
- New platform responsibility does not enter Legacy.
- Retirement follows replacement evidence and caller migration.
- Behavior changes are explicit.

## Failure modes

| # | Failure | Required behavior |
|---|---|---|
| `1` | uncharacterized behavior | Fail closed; emit domain error/event and preserve input evidence. |
| `2` | semantic mismatch | Fail closed; emit domain error/event and preserve input evidence. |
| `3` | hidden caller dependency | Fail closed; emit domain error/event and preserve input evidence. |
| `4` | premature retirement | Fail closed; emit domain error/event and preserve input evidence. |

## Current code mapping

- `src/market_regime_alpha/dividend_t/**`
- `src/market_regime_alpha/legacy/**`

## Missing implementation

- component extraction inventory
- caller migration ledger
- retirement gates

## Transaction and persistence boundary

One command commits one owning-domain aggregate and its outbox event atomically. Cross-domain orchestration uses identities/events; no command mutates another domain's aggregate.

## Compatibility rule

Legacy adapters may translate input/output shapes but cannot become the authority owner or increase evidence level.
