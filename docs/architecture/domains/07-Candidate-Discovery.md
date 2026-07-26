# Candidate Discovery Domain

> **Status:** CURRENT_ARCHITECTURE  
> **Authority:** Canonical bounded-context design for Candidate Discovery  
> **Owner:** Candidate Discovery domain  
> **Last Updated:** 2026-07-26  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** ../01-Domain-Boundaries.md, ../../specs/README.md, ../../roadmap/work-packages/README.md  
> **Code Evidence:** path:src/market_regime_alpha/candidates/**; path:WP3 provider-backed Candidate research

## Responsibility

Own complete eligible cross-section predictions, rankings and explainable recommendation projections.

## Owned entities

- `CandidatePopulation`
- `CandidatePrediction`
- `PredictionRun`
- `CandidateRecommendation`

Only this domain may create or supersede these authoritative entities.

## Commands

- `BuildCandidatePopulation`
- `RunCandidateModel`
- `FreezePredictionRun`
- `ProjectRecommendations`

Commands are idempotent by an explicit request key and either produce immutable artifacts/events or a structured failure.

## Queries

- `GetPredictionRun`
- `ListFullRanking`
- `GetRecommendation`
- `ExplainCandidate`

Queries are read-only projections and return canonical source IDs.

## Events

- `CandidatePopulationFrozen`
- `PredictionRunFrozen`
- `CandidateRecommendationsPublished`
- `CandidateRunBlocked`

Events carry aggregate identity, schema version, occurred time, correlation ID and causation ID.

## Input contracts

- UniverseSnapshot
- EligibilitySnapshot
- FeatureMatrix
- TargetDefinition
- ModelDefinition
- frozen experiment protocol

## Output contracts

- complete PredictionRun
- CandidateRecommendation records
- explicit rejection ledger

## Upstream domains

- Calendar and Universe
- Feature and Factor
- Context domains
- Research Artifact

## Downstream domains

- Entry
- Portfolio
- Review and Attribution
- Application/QuantDesk

## Invariants

- Full ranking/rejection ledger is authoritative.
- Candidate never emits trade action.
- Score is not probability without calibration.
- Empty Candidate output is valid.

## Failure modes

| # | Failure | Required behavior |
|---|---|---|
| `1` | population mismatch | Fail closed; emit domain error/event and preserve input evidence. |
| `2` | model/feature incompatibility | Fail closed; emit domain error/event and preserve input evidence. |
| `3` | coverage below protocol | Fail closed; emit domain error/event and preserve input evidence. |
| `4` | probability without calibration | Fail closed; emit domain error/event and preserve input evidence. |

## Current code mapping

- `src/market_regime_alpha/candidates/**`
- `WP3 provider-backed Candidate research`

## Missing implementation

- daily multi-model Prediction Ledger
- structured CandidateRecommendation persistence/API
- B2+ challengers

## Transaction and persistence boundary

One command commits one owning-domain aggregate and its outbox event atomically. Cross-domain orchestration uses identities/events; no command mutates another domain's aggregate.

## Compatibility rule

Legacy adapters may translate input/output shapes but cannot become the authority owner or increase evidence level.
