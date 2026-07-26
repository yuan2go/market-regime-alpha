# WP-D2 — Daily Stock/ETF Universe and Eligibility

> **Status:** ROADMAP  
> **Authority:** Executable implementation work package WP-D2  
> **Owner:** Market Regime Alpha maintainers  
> **Last Updated:** 2026-07-26  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** README.md, ../Phase-D-Work-Packages.md, ../../status/Gap-Register.md  
> **Code Evidence:** Acceptance evidence must be added when implemented

## Objective

Build content-addressed PIT stock and ETF populations with explicit eligibility and exclusion reasons.

## Bounded contexts

- Calendar and Universe

## Dependencies

- WP-D1
- existing trading calendar/PIT universe/eligibility contracts

## Inputs

- TradingCalendar
- listing/delisting/ST/suspension facts
- ETF metadata
- liquidity observations
- universe policy

## Outputs

- UniverseSnapshot
- EligibilitySnapshot
- ExclusionLedger

## Expected files/modules

- src/market_regime_alpha/universe/**
- src/market_regime_alpha/data/trading_calendar.py
- tests/universe/**

Exact files may change after code inspection, but ownership may not move outside the declared bounded contexts without an architecture decision.

## New or changed contracts

- UniverseSnapshot
- EligibilitySnapshot
- ExclusionRecord

## Code work

- daily stock/ETF builders
- mapping version capture
- eligibility policy registry
- population reconciliation

## Tests

- historical membership as-of correctness
- unknown status blocks
- population totals reconcile
- ETF/stock semantics separated

## Acceptance conditions

- complete population accounting
- PIT membership evidence
- every exclusion coded
- content-addressed snapshots

## Evidence required

- fixture/replay snapshots
- coverage report
- PIT leakage tests

## Risks

- current-snapshot leakage
- missing ETF history
- liquidity look-ahead

## Stop conditions

- historical membership cannot be qualified for requested lane
- population coverage below protocol
- eligibility semantics ambiguous

When a stop condition occurs, publish a blocked/negative result. Do not expand scope or tune unrelated variables to manufacture success.

## Migration effect

Makes daily universe snapshots the canonical input; Legacy current-snapshot builders become exploratory adapters.

## Documentation updates

- docs/status/Capability-Matrix.md
- docs/status/Gap-Register.md
- docs/architecture/domains/01-Calendar-and-Universe.md

## Explicit non-goals

- context scoring
- Candidate ranking
- portfolio allocation
