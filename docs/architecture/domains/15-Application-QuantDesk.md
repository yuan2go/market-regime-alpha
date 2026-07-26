# Application and QuantDesk Domain

> **Status:** CURRENT_ARCHITECTURE  
> **Authority:** Canonical bounded-context design for Application and QuantDesk  
> **Owner:** Application and QuantDesk domain  
> **Last Updated:** 2026-07-26  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** ../01-Domain-Boundaries.md, ../../specs/README.md, ../../roadmap/work-packages/README.md  
> **Code Evidence:** path:Legacy FastAPI dashboards

## Responsibility

Own read models, workflow initiation and human capture surfaces without owning model/data/account truth.

## Owned entities

- `WorkbenchView`
- `TaskRequest`
- `ApprovalRequest`

Only this domain may create or supersede these authoritative entities.

## Commands

- `RequestResearchRun`
- `RecordManualDecision`
- `ApproveProposal`
- `RequestReplay`

Commands are idempotent by an explicit request key and either produce immutable artifacts/events or a structured failure.

## Queries

- `GetDailyWorkbench`
- `GetResearchWorkbench`
- `GetReviewWorkbench`
- `GetArtifactDetails`

Queries are read-only projections and return canonical source IDs.

## Events

- `TaskRequested`
- `ApprovalRecorded`

Events carry aggregate identity, schema version, occurred time, correlation ID and causation ID.

## Input contracts

- read APIs from authoritative domains
- human commands

## Output contracts

- projections
- command requests
- approval records

## Upstream domains

- all authoritative domains

## Downstream domains

- human operator
- Ops

## Invariants

- UI never recomputes canonical signals.
- No secrets/model logic in frontend.
- Write commands validate domain authority.
- Displayed values retain source IDs.

## Failure modes

| # | Failure | Required behavior |
|---|---|---|
| `1` | stale projection | Fail closed; emit domain error/event and preserve input evidence. |
| `2` | duplicate command | Fail closed; emit domain error/event and preserve input evidence. |
| `3` | unauthorized mutation | Fail closed; emit domain error/event and preserve input evidence. |
| `4` | logic duplicated in UI | Fail closed; emit domain error/event and preserve input evidence. |

## Current code mapping

- `Legacy FastAPI dashboards`

## Missing implementation

- Phase D API gateway/read models
- three workbenches
- manual capture/approval flows

## Transaction and persistence boundary

One command commits one owning-domain aggregate and its outbox event atomically. Cross-domain orchestration uses identities/events; no command mutates another domain's aggregate.

## Compatibility rule

Legacy adapters may translate input/output shapes but cannot become the authority owner or increase evidence level.
