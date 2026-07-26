# Research Artifact Domain

> **Status:** CURRENT_ARCHITECTURE  
> **Authority:** Canonical bounded-context design for Research Artifact  
> **Owner:** Research Artifact domain  
> **Last Updated:** 2026-07-26  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** ../01-Domain-Boundaries.md, ../../specs/README.md, ../../roadmap/work-packages/README.md  
> **Code Evidence:** path:src/market_regime_alpha/research/**; path:Draft PR #12 platform kernel

## Responsibility

Own immutable experiment, model, target, run, outcome, evaluation and promotion identities.

## Owned entities

- `ExperimentIdentity`
- `ModelDefinition`
- `TargetDefinition`
- `EvaluationProtocol`
- `ResearchArtifact`
- `PromotionDecision`

Only this domain may create or supersede these authoritative entities.

## Commands

- `RegisterModel`
- `FreezeExperimentProtocol`
- `StoreArtifact`
- `VerifyArtifact`
- `RecordPromotionDecision`

Commands are idempotent by an explicit request key and either produce immutable artifacts/events or a structured failure.

## Queries

- `GetArtifact`
- `VerifyArtifact`
- `TraceExperiment`
- `GetModelLifecycle`

Queries are read-only projections and return canonical source IDs.

## Events

- `ExperimentProtocolFrozen`
- `ArtifactStored`
- `ArtifactVerificationFailed`
- `ModelLifecycleChanged`

Events carry aggregate identity, schema version, occurred time, correlation ID and causation ID.

## Input contracts

- definitions/config/code/data identities
- run outputs
- human governance decisions

## Output contracts

- content-addressed artifacts
- verification results
- model lifecycle records

## Upstream domains

- all research/decision domains

## Downstream domains

- all model-running domains
- Review and Attribution
- Codex feedback

## Invariants

- Result-affecting inputs are identified.
- Artifacts are immutable and verifiable.
- Model lifecycle and evidence level are separate.
- Promotion requires declared evidence and human approval.

## Failure modes

| # | Failure | Required behavior |
|---|---|---|
| `1` | hash mismatch | Fail closed; emit domain error/event and preserve input evidence. |
| `2` | identity collision | Fail closed; emit domain error/event and preserve input evidence. |
| `3` | validation budget exceeded | Fail closed; emit domain error/event and preserve input evidence. |
| `4` | promotion without evidence | Fail closed; emit domain error/event and preserve input evidence. |

## Current code mapping

- `src/market_regime_alpha/research/**`
- `Draft PR #12 platform kernel`

## Missing implementation

- unified platform registry on main
- daily decision artifact profiles
- promotion workflow integration

## Transaction and persistence boundary

One command commits one owning-domain aggregate and its outbox event atomically. Cross-domain orchestration uses identities/events; no command mutates another domain's aggregate.

## Compatibility rule

Legacy adapters may translate input/output shapes but cannot become the authority owner or increase evidence level.
