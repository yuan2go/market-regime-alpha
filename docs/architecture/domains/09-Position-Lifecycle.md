# Position Lifecycle Domain

> **Status:** CURRENT_ARCHITECTURE  
> **Authority:** Canonical bounded-context design for Position Lifecycle  
> **Owner:** Position Lifecycle domain  
> **Last Updated:** 2026-07-26  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** ../01-Domain-Boundaries.md, ../../specs/README.md, ../../roadmap/work-packages/README.md  
> **Code Evidence:** path:Legacy PositionState only

## Responsibility

Own actual position state, thesis continuity and HOLD/ADD/REDUCE/ROTATE assessments.

## Owned entities

- `PositionSnapshot`
- `HoldingAssessment`
- `PositionThesis`

Only this domain may create or supersede these authoritative entities.

## Commands

- `RecordPositionSnapshot`
- `ReconcilePosition`
- `AssessHolding`
- `FreezeHoldingAssessments`

Commands are idempotent by an explicit request key and either produce immutable artifacts/events or a structured failure.

## Queries

- `GetPositionSnapshot`
- `ListOpenPositions`
- `GetHoldingAssessment`
- `ExplainThesisStatus`

Queries are read-only projections and return canonical source IDs.

## Events

- `PositionSnapshotFrozen`
- `PositionReconciliationMismatch`
- `HoldingAssessmentsPublished`

Events carry aggregate identity, schema version, occurred time, correlation ID and causation ID.

## Input contracts

- ManualTradeRecord or broker-reconciled fills
- marks
- position/thesis policy
- holding features/model

## Output contracts

- PositionSnapshot
- HoldingAssessment

## Upstream domains

- Manual Execution Record
- Data Source and PIT
- Feature and Factor

## Downstream domains

- Exit
- Portfolio
- Review and Attribution
- Application/QuantDesk

## Invariants

- Position derives only from actual records.
- T+1 available quantity is explicit.
- NO_ACTION is not HOLD.
- Corrections supersede; they do not overwrite.

## Failure modes

| # | Failure | Required behavior |
|---|---|---|
| `1` | trade ledger mismatch | Fail closed; emit domain error/event and preserve input evidence. |
| `2` | position inferred from recommendation | Fail closed; emit domain error/event and preserve input evidence. |
| `3` | available quantity invalid | Fail closed; emit domain error/event and preserve input evidence. |
| `4` | thesis evidence missing | Fail closed; emit domain error/event and preserve input evidence. |

## Current code mapping

- `Legacy PositionState only`

## Missing implementation

- canonical position ledger
- reconciliation service
- Holding model/assessment

## Transaction and persistence boundary

One command commits one owning-domain aggregate and its outbox event atomically. Cross-domain orchestration uses identities/events; no command mutates another domain's aggregate.

## Compatibility rule

Legacy adapters may translate input/output shapes but cannot become the authority owner or increase evidence level.
