# WP-D9 — Portfolio and Execution Simulation

> **Status:** ROADMAP  
> **Authority:** Executable implementation work package WP-D9  
> **Owner:** Market Regime Alpha maintainers  
> **Last Updated:** 2026-07-26  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** README.md, ../Phase-D-Work-Packages.md, ../../status/Gap-Register.md  
> **Code Evidence:** Acceptance evidence must be added when implemented

## Objective

Evaluate allocation, concentration, cost, capacity and A-share execution constraints across validated components.

## Bounded contexts

- Portfolio

## Dependencies

- validated outputs from WP-D4–D8

## Inputs

- Candidate/Entry/Holding/Exit artifacts
- PositionSnapshot
- risk policy
- cost/slippage/capacity models

## Outputs

- PortfolioDecision
- SimulationResult
- risk exposure report

## Expected files/modules

- src/market_regime_alpha/portfolio/**
- src/market_regime_alpha/execution/simulation/**
- tests/portfolio/**

Exact files may change after code inspection, but ownership may not move outside the declared bounded contexts without an architecture decision.

## New or changed contracts

- PortfolioDecision
- RiskPolicy
- ExecutionPolicy
- SimulationResult

## Code work

- component compatibility validator
- risk budgets
- T+1/limit/lot/cost simulation
- portfolio comparison

## Tests

- concentration limits
- incompatible components rejected
- cost scenarios
- unfillable limit-up
- deterministic simulation

## Acceptance conditions

- risk-adjusted portfolio metrics
- cost/capacity explicit
- no real order path
- allocation traceable to proposals

## Evidence required

- simulation artifact
- stress scenarios
- compatibility matrix

## Risks

- optimistic fills
- hidden leverage/concentration
- strategy correlation

## Stop conditions

- component Alpha not validated
- cost/capacity model unavailable
- portfolio result depends on impossible fills

When a stop condition occurs, publish a blocked/negative result. Do not expand scope or tune unrelated variables to manufacture success.

## Migration effect

Reuses validated model outputs; Legacy backtests remain benchmark/control implementations.

## Documentation updates

- docs/constitution/06-Strategy-Constitution.md
- docs/status/Capability-Matrix.md
- docs/architecture/domains/11-Portfolio.md

## Explicit non-goals

- broker integration
- live rebalance
- guaranteed return
