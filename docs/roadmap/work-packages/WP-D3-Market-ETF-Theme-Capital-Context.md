# WP-D3 — Market, ETF, Theme and Capital Context

> **Status:** ROADMAP  
> **Authority:** Executable implementation work package WP-D3  
> **Owner:** Market Regime Alpha maintainers  
> **Last Updated:** 2026-07-26  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** README.md, ../Phase-D-Work-Packages.md, ../../status/Gap-Register.md  
> **Code Evidence:** Acceptance evidence must be added when implemented

## Objective

Materialize transparent, versioned context snapshots that can be evaluated as features, interactions or risk-budget inputs without default hard-gate authority.

## Bounded contexts

- Market Context
- ETF Direction
- Theme Direction
- Capital Context

## Dependencies

- WP-D1
- WP-D2
- WP-D2E operational feedback

## Inputs

- UniverseSnapshot
- FeatureMatrix
- ETF/theme mappings
- turnover/breadth observations
- registered methodologies

## Outputs

- MarketContextSnapshot
- ETFDirectionSnapshot
- ThemeDirectionSnapshot
- CapitalContextSnapshot

## Expected files/modules

- src/market_regime_alpha/context/**
- src/market_regime_alpha/etf/**
- src/market_regime_alpha/themes/**
- tests/context/**

Exact files may change after code inspection, but ownership may not move outside the declared bounded contexts without an architecture decision.

## New or changed contracts

- four context snapshots
- context role declaration

## Code work

- baseline breadth/relative-strength/phase materializers
- field availability
- context artifact persistence
- ablation hooks

## Tests

- PIT mapping tests
- coverage gates
- context role isolation
- no hard gate without approval

## Acceptance conditions

- all snapshots reproducible
- context roles explicit
- missing optional capital fields stay null
- ablation-ready identities

## Evidence required

- snapshot examples
- coverage/quality report
- context-only vs baseline ablation plan

## Risks

- explanatory variables mistaken for predictors
- theme history gaps
- correlated feature double counting

## Stop conditions

- PIT mappings unavailable
- context coverage below protocol
- implementation requires unqualified flow inference

When a stop condition occurs, publish a blocked/negative result. Do not expand scope or tune unrelated variables to manufacture success.

## Migration effect

Extracts reusable context from Legacy/MR research into canonical snapshots; Legacy context remains comparison evidence.

## Documentation updates

- docs/research/ETF-Theme-Capital-Context-Research.md
- docs/status/Capability-Matrix.md
- docs/architecture/domains/02-Market-Context.md

## Explicit non-goals

- automatic context gate
- portfolio allocation
- model winner
