# Exit Domain

> **Status:** CURRENT_ARCHITECTURE  
> **Authority:** Canonical bounded-context design for Exit  
> **Owner:** Exit domain  
> **Last Updated:** 2026-07-26  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** ../01-Domain-Boundaries.md, ../../specs/README.md, ../../roadmap/work-packages/README.md  
> **Code Evidence:** path:Legacy sell-side rules only

## Responsibility

Own independent exit/reduction reasons, continuation targets and exit-quality evaluation.

## Owned entities

- `ExitAssessment`
- `ExitModelDefinition`
- `ExitContinuationTarget`

Only this domain may create or supersede these authoritative entities.

## Commands

- `AssessPositionExit`
- `FreezeExitAssessments`
- `EvaluateExitIncrement`

Commands are idempotent by an explicit request key and either produce immutable artifacts/events or a structured failure.

## Queries

- `GetExitAssessment`
- `ListExitAssessments`
- `ExplainExitReason`

Queries are read-only projections and return canonical source IDs.

## Events

- `ExitAssessmentsPublished`
- `ExitAssessmentBlocked`

Events carry aggregate identity, schema version, occurred time, correlation ID and causation ID.

## Input contracts

- PositionSnapshot
- holding/thesis state
- exit features/context
- Exit model/target

## Output contracts

- ExitAssessment
- profit-giveback/avoided-drawdown/post-exit-regret metrics

## Upstream domains

- Position Lifecycle
- Feature and Factor
- Context domains
- Research Artifact

## Downstream domains

- Manual Execution Record
- Portfolio
- Review and Attribution

## Invariants

- Exit is not inverse Entry.
- Action respects available quantity/T+1.
- Primary reason is explicit.
- No exit without actual position.

## Failure modes

| # | Failure | Required behavior |
|---|---|---|
| `1` | inverse-entry implementation | Fail closed; emit domain error/event and preserve input evidence. |
| `2` | position unavailable | Fail closed; emit domain error/event and preserve input evidence. |
| `3` | quantity unsellable | Fail closed; emit domain error/event and preserve input evidence. |
| `4` | reason/action mismatch | Fail closed; emit domain error/event and preserve input evidence. |

## Current code mapping

- `Legacy sell-side rules only`

## Missing implementation

- canonical Exit targets/models/assessments
- control arms
- exit scorecards

## Transaction and persistence boundary

One command commits one owning-domain aggregate and its outbox event atomically. Cross-domain orchestration uses identities/events; no command mutates another domain's aggregate.

## Compatibility rule

Legacy adapters may translate input/output shapes but cannot become the authority owner or increase evidence level.
