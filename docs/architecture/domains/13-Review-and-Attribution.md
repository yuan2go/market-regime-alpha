# Review and Attribution Domain

> **Status:** CURRENT_ARCHITECTURE  
> **Authority:** Canonical bounded-context design for Review and Attribution  
> **Owner:** Review and Attribution domain  
> **Last Updated:** 2026-07-26  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** ../01-Domain-Boundaries.md, ../../specs/README.md, ../../roadmap/work-packages/README.md  
> **Code Evidence:** path:Candidate diagnostics and research artifacts

## Responsibility

Own observed outcomes, layer-specific metrics, failure attribution, rolling scorecards and controlled research proposals.

## Owned entities

- `RecommendationOutcome`
- `DailyReviewReport`
- `FailureAttribution`
- `RollingScorecard`

Only this domain may create or supersede these authoritative entities.

## Commands

- `MatchOutcomes`
- `AttributeFailure`
- `PublishDailyReview`
- `BuildRollingScorecard`

Commands are idempotent by an explicit request key and either produce immutable artifacts/events or a structured failure.

## Queries

- `GetOutcome`
- `GetDailyReview`
- `GetFailureAttribution`
- `CompareModels`

Queries are read-only projections and return canonical source IDs.

## Events

- `RecommendationOutcomeMatched`
- `DailyReviewPublished`
- `FailureAttributed`
- `ScorecardPublished`

Events carry aggregate identity, schema version, occurred time, correlation ID and causation ID.

## Input contracts

- frozen predictions/assessments
- future observed data
- manual trades/positions
- evaluation protocol
- failure taxonomy

## Output contracts

- RecommendationOutcome
- DailyReviewReport
- 5/20/60/120-day scorecards
- FailureAttribution

## Upstream domains

- all decision domains
- Research Artifact

## Downstream domains

- Research Artifact/Governance
- Application/QuantDesk
- Codex feedback

## Invariants

- Facts, inferences and hypotheses remain separate.
- Candidate/Entry/Exit/Execution effects are attributed separately.
- Original predictions are immutable.
- Daily reports cannot promote models.

## Failure modes

| # | Failure | Required behavior |
|---|---|---|
| `1` | target mismatch | Fail closed; emit domain error/event and preserve input evidence. |
| `2` | outcome unavailable | Fail closed; emit domain error/event and preserve input evidence. |
| `3` | attribution without evidence | Fail closed; emit domain error/event and preserve input evidence. |
| `4` | layer metric conflation | Fail closed; emit domain error/event and preserve input evidence. |

## Current code mapping

- `Candidate diagnostics and research artifacts`

## Missing implementation

- automatic outcome matcher
- daily review pipeline
- failure taxonomy runtime
- rolling scorecards

## Transaction and persistence boundary

One command commits one owning-domain aggregate and its outbox event atomically. Cross-domain orchestration uses identities/events; no command mutates another domain's aggregate.

## Compatibility rule

Legacy adapters may translate input/output shapes but cannot become the authority owner or increase evidence level.
