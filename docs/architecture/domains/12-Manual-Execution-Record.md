# Manual Execution Record Domain

> **Status:** CURRENT_ARCHITECTURE  
> **Authority:** Canonical bounded-context design for Manual Execution Record  
> **Owner:** Manual Execution Record domain  
> **Last Updated:** 2026-07-26  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** ../01-Domain-Boundaries.md, ../../specs/README.md, ../../roadmap/work-packages/README.md  
> **Code Evidence:** path:no canonical implementation

## Responsibility

Own human decisions, order intent, actual fills, cancellations and deviations from proposals.

## Owned entities

- `ManualTradeRecord`
- `Fill`
- `ManualDecision`

Only this domain may create or supersede these authoritative entities.

## Commands

- `RecordManualDecision`
- `RecordOrderIntent`
- `RecordFill`
- `CorrectManualTradeRecord`

Commands are idempotent by an explicit request key and either produce immutable artifacts/events or a structured failure.

## Queries

- `GetManualTradeRecord`
- `ListTradeRecords`
- `GetExecutionDeviation`

Queries are read-only projections and return canonical source IDs.

## Events

- `ManualDecisionRecorded`
- `ManualFillRecorded`
- `ManualTradeCorrected`

Events carry aggregate identity, schema version, occurred time, correlation ID and causation ID.

## Input contracts

- Candidate/Entry/Exit/Portfolio proposal references
- user-entered decision/order/fill evidence

## Output contracts

- ManualTradeRecord
- execution deviation facts

## Upstream domains

- Candidate Discovery
- Entry
- Exit
- Portfolio
- human operator

## Downstream domains

- Position Lifecycle
- Review and Attribution

## Invariants

- No record is inferred.
- Actual fills are append-only evidence.
- Corrections use supersedes.
- Credentials and secrets are never persisted.

## Failure modes

| # | Failure | Required behavior |
|---|---|---|
| `1` | missing fill evidence | Fail closed; emit domain error/event and preserve input evidence. |
| `2` | aggregate mismatch | Fail closed; emit domain error/event and preserve input evidence. |
| `3` | deviation reason missing | Fail closed; emit domain error/event and preserve input evidence. |
| `4` | duplicate external fill | Fail closed; emit domain error/event and preserve input evidence. |

## Current code mapping

- `no canonical implementation`

## Missing implementation

- write API/UI
- fill reconciliation
- manual deviation analytics

## Transaction and persistence boundary

One command commits one owning-domain aggregate and its outbox event atomically. Cross-domain orchestration uses identities/events; no command mutates another domain's aggregate.

## Compatibility rule

Legacy adapters may translate input/output shapes but cannot become the authority owner or increase evidence level.
