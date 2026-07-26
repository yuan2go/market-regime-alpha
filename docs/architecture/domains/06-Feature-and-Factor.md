# Feature and Factor Domain

> **Status:** CURRENT_ARCHITECTURE  
> **Authority:** Canonical bounded-context design for Feature and Factor  
> **Owner:** Feature and Factor domain  
> **Last Updated:** 2026-07-26  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** ../01-Domain-Boundaries.md, ../../specs/README.md, ../../roadmap/work-packages/README.md  
> **Code Evidence:** path:src/market_regime_alpha/features/**

## Responsibility

Own versioned feature definitions, materialization, lineage, availability and approval state.

## Owned entities

- `FeatureDefinition`
- `FeatureMaterialization`
- `FeatureSetDefinition`
- `ObservableDefinition`

Only this domain may create or supersede these authoritative entities.

## Commands

- `RegisterFeature`
- `MaterializeFeatureSet`
- `ValidateFeatureLineage`
- `ApproveFeature`

Commands are idempotent by an explicit request key and either produce immutable artifacts/events or a structured failure.

## Queries

- `GetFeatureDefinition`
- `GetFeatureValues`
- `TraceFeatureLineage`
- `ListApprovedFeatures`

Queries are read-only projections and return canonical source IDs.

## Events

- `FeatureRegistered`
- `FeatureSetMaterialized`
- `FeatureValidationFailed`
- `FeatureApproved`

Events carry aggregate identity, schema version, occurred time, correlation ID and causation ID.

## Input contracts

- normalized PIT artifacts
- observable definitions
- feature parameters
- availability policy

## Output contracts

- FeatureMaterialization
- FeatureMatrix
- lineage manifest

## Upstream domains

- Data Source and PIT
- Calendar and Universe
- Knowledge/Theory formalization

## Downstream domains

- Market/ETF/Theme/Capital Context
- Candidate Discovery
- Entry
- Holding
- Exit

## Invariants

- Every feature has identity and lineage.
- No future data enters decision-time values.
- Correlated transforms are not independent evidence by default.
- Feature state distinguishes implemented from empirically approved.

## Failure modes

| # | Failure | Required behavior |
|---|---|---|
| `1` | lineage missing | Fail closed; emit domain error/event and preserve input evidence. |
| `2` | availability violation | Fail closed; emit domain error/event and preserve input evidence. |
| `3` | duplicate information family | Fail closed; emit domain error/event and preserve input evidence. |
| `4` | parameter/version mismatch | Fail closed; emit domain error/event and preserve input evidence. |

## Current code mapping

- `src/market_regime_alpha/features/**`

## Missing implementation

- persistent Feature registry
- theory/observable approval workflow
- broader approved feature catalog

## Transaction and persistence boundary

One command commits one owning-domain aggregate and its outbox event atomically. Cross-domain orchestration uses identities/events; no command mutates another domain's aggregate.

## Compatibility rule

Legacy adapters may translate input/output shapes but cannot become the authority owner or increase evidence level.
