# WP-D6 — Manual Trade Record and Canonical Position Authority

> **Status:** ROADMAP  
> **Authority:** Executable implementation work package WP-D6  
> **Owner:** Market Regime Alpha maintainers  
> **Last Updated:** 2026-07-26  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** README.md, ../Phase-D-Work-Packages.md, ../../status/Gap-Register.md  
> **Code Evidence:** Acceptance evidence must be added when implemented

## Objective

Create append-only human decision/fill records and derive canonical actual position snapshots with reconciliation.

## Bounded contexts

- Manual Execution Record
- Position Lifecycle

## Dependencies

- WP-D4
- WP-D5 optional for linked proposals

## Inputs

- human decisions
- order intents
- actual fills
- Candidate/Entry references
- marks

## Outputs

- ManualTradeRecord
- PositionSnapshot
- reconciliation report

## Expected files/modules

- src/market_regime_alpha/execution/manual/**
- src/market_regime_alpha/positions/**
- src/market_regime_alpha/application/api/**
- tests/execution/**
- tests/positions/**

Exact files may change after code inspection, but ownership may not move outside the declared bounded contexts without an architecture decision.

## New or changed contracts

- ManualTradeRecord
- PositionSnapshot

## Code work

- write API
- fill aggregation
- T+1 available quantity
- position ledger
- correction/supersedes workflow

## Tests

- recommendation cannot create position
- fill aggregates reconcile
- T+1 quantity
- idempotent external fill
- correction preserves original

## Acceptance conditions

- all positions trace to actual records
- manual deviations captured
- reconciliation status explicit
- no credentials persisted

## Evidence required

- ledger replay
- position reconciliation fixture
- API contract tests

## Risks

- manual entry errors
- duplicate fills
- privacy/account data leakage

## Stop conditions

- position cannot be reconstructed
- external fill identity ambiguous
- secrets would need persistence

When a stop condition occurs, publish a blocked/negative result. Do not expand scope or tune unrelated variables to manufacture success.

## Migration effect

Replaces Legacy inferred PositionState as authority; Legacy state becomes a view/control comparator.

## Documentation updates

- docs/specs/ManualTradeRecord.md
- docs/specs/PositionSnapshot.md
- docs/research/Position-Lifecycle-Research.md

## Explicit non-goals

- broker sync
- automatic orders
- portfolio optimization
