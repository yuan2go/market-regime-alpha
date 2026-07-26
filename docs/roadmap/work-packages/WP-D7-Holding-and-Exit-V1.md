# WP-D7 — Independent Holding and Exit V1

> **Status:** ROADMAP  
> **Authority:** Executable implementation work package WP-D7  
> **Owner:** Market Regime Alpha maintainers  
> **Last Updated:** 2026-07-26  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** README.md, ../Phase-D-Work-Packages.md, ../../status/Gap-Register.md  
> **Code Evidence:** Acceptance evidence must be added when implemented

## Objective

Implement separate Holding and Exit assessments on actual positions with simple control arms before complex models.

## Bounded contexts

- Position Lifecycle
- Exit

## Dependencies

- WP-D6
- Feature/Context inputs

## Inputs

- PositionSnapshot
- thesis references
- holding/exit features
- simple control policies

## Outputs

- HoldingAssessment
- ExitAssessment
- holding/exit evaluation

## Expected files/modules

- src/market_regime_alpha/positions/**
- src/market_regime_alpha/strategies/exit/**
- tests/positions/**
- tests/strategies/exit/**

Exact files may change after code inspection, but ownership may not move outside the declared bounded contexts without an architecture decision.

## New or changed contracts

- HoldingAssessment
- ExitAssessment
- ExitContinuationTarget

## Code work

- HOLD/ADD/REDUCE/ROTATE baseline
- profit/risk/thesis/time exit reasons
- continuation target materialization
- assessment persistence

## Tests

- NO_ACTION != HOLD
- Exit not inverse Entry
- T+1 sellability
- reason/action validation
- post-exit regret/avoided drawdown

## Acceptance conditions

- independent assessment artifacts
- simple controls available
- giveback/tail-loss improvement measured with regret
- actual position required

## Evidence required

- control-arm report
- exit attribution examples
- T+1 tests

## Risks

- selling winners too early
- holding via absence of exit
- reason proliferation

## Stop conditions

- no actual position authority
- control arms not defined
- Exit gain only appears through changed Candidate set

When a stop condition occurs, publish a blocked/negative result. Do not expand scope or tune unrelated variables to manufacture success.

## Migration effect

Extracts sell/holding hypotheses from Legacy into independent models; Legacy remains comparison evidence.

## Documentation updates

- docs/research/Position-Lifecycle-Research.md
- docs/research/Exit-Research.md
- docs/specs/HoldingAssessment.md
- docs/specs/ExitAssessment.md

## Explicit non-goals

- portfolio allocation
- real sell orders
- nonlinear optimal stopping
