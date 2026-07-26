# Portfolio Domain

> **Status:** CURRENT_ARCHITECTURE  
> **Authority:** Canonical bounded-context design for Portfolio  
> **Owner:** Portfolio domain  
> **Last Updated:** 2026-07-26  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** ../01-Domain-Boundaries.md, ../../specs/README.md, ../../roadmap/work-packages/README.md  
> **Code Evidence:** path:Legacy position sizing/backtests

## Responsibility

Own capital/risk allocation across validated proposals and simulation under A-share constraints.

## Owned entities

- `PortfolioDecision`
- `RiskBudget`
- `SimulationResult`

Only this domain may create or supersede these authoritative entities.

## Commands

- `ConstructPortfolio`
- `ApplyRiskPolicy`
- `SimulateExecution`
- `FreezePortfolioDecision`

Commands are idempotent by an explicit request key and either produce immutable artifacts/events or a structured failure.

## Queries

- `GetPortfolioDecision`
- `ExplainAllocation`
- `GetSimulationResult`
- `GetRiskExposure`

Queries are read-only projections and return canonical source IDs.

## Events

- `PortfolioDecisionFrozen`
- `PortfolioBlocked`
- `SimulationCompleted`

Events carry aggregate identity, schema version, occurred time, correlation ID and causation ID.

## Input contracts

- Candidate/Entry/Holding/Exit proposals
- PositionSnapshot
- risk/portfolio policy
- cost/capacity model

## Output contracts

- PortfolioDecision
- SimulationResult
- exposure report

## Upstream domains

- Candidate Discovery
- Entry
- Position Lifecycle
- Exit
- Data Source and PIT

## Downstream domains

- Manual Execution Record
- Review and Attribution
- Application/QuantDesk

## Invariants

- Only validated compatible components compose.
- Concentration/capacity/cost/T+1 are explicit.
- No real order authority.
- Risk budgets are versioned.

## Failure modes

| # | Failure | Required behavior |
|---|---|---|
| `1` | incompatible strategy components | Fail closed; emit domain error/event and preserve input evidence. |
| `2` | concentration breach | Fail closed; emit domain error/event and preserve input evidence. |
| `3` | capacity unavailable | Fail closed; emit domain error/event and preserve input evidence. |
| `4` | cost model missing | Fail closed; emit domain error/event and preserve input evidence. |

## Current code mapping

- `Legacy position sizing/backtests`

## Missing implementation

- canonical PortfolioDecision
- strategy composition validator
- execution simulator

## Transaction and persistence boundary

One command commits one owning-domain aggregate and its outbox event atomically. Cross-domain orchestration uses identities/events; no command mutates another domain's aggregate.

## Compatibility rule

Legacy adapters may translate input/output shapes but cannot become the authority owner or increase evidence level.
