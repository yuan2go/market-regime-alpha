# Entry Domain

> **Status:** CURRENT_ARCHITECTURE  
> **Authority:** Canonical bounded-context design for Entry  
> **Owner:** Entry domain  
> **Last Updated:** 2026-07-26  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** ../01-Domain-Boundaries.md, ../../specs/README.md, ../../roadmap/work-packages/README.md  
> **Code Evidence:** path:src/market_regime_alpha/strategies/entry/**

## Responsibility

Own path-aware opening suitability and the incremental comparison against Candidate-only baselines.

## Owned entities

- `EntryAssessment`
- `EntryModelDefinition`
- `EntryPathTarget`

Only this domain may create or supersede these authoritative entities.

## Commands

- `AssessCandidateEntry`
- `FreezeEntryAssessments`
- `EvaluateEntryIncrement`

Commands are idempotent by an explicit request key and either produce immutable artifacts/events or a structured failure.

## Queries

- `GetEntryAssessment`
- `ListEntryAssessments`
- `ExplainEntryAction`

Queries are read-only projections and return canonical source IDs.

## Events

- `EntryAssessmentsPublished`
- `EntryAssessmentBlocked`

Events carry aggregate identity, schema version, occurred time, correlation ID and causation ID.

## Input contracts

- CandidateRecommendation
- decision-time price/location/volume/context
- Entry model
- Entry Path Target definitions

## Output contracts

- EntryAssessment
- Entry evaluation strata

## Upstream domains

- Candidate Discovery
- Feature and Factor
- Context domains
- Research Artifact

## Downstream domains

- Manual Execution Record
- Portfolio
- Review and Attribution

## Invariants

- Entry cannot rewrite Candidate quality.
- Future path targets are unavailable at decision time.
- ENTER has explicit invalidation and price assumptions.
- NO_ACTION is not HOLD.

## Failure modes

| # | Failure | Required behavior |
|---|---|---|
| `1` | path target leakage | Fail closed; emit domain error/event and preserve input evidence. |
| `2` | action-specific fields missing | Fail closed; emit domain error/event and preserve input evidence. |
| `3` | price zone invalid | Fail closed; emit domain error/event and preserve input evidence. |
| `4` | Entry reduces trades without economic increment | Fail closed; emit domain error/event and preserve input evidence. |

## Current code mapping

- `src/market_regime_alpha/strategies/entry/**`

## Missing implementation

- Entry model/gate
- EntryAssessment service
- incremental Entry scorecards

## Transaction and persistence boundary

One command commits one owning-domain aggregate and its outbox event atomically. Cross-domain orchestration uses identities/events; no command mutates another domain's aggregate.

## Compatibility rule

Legacy adapters may translate input/output shapes but cannot become the authority owner or increase evidence level.
