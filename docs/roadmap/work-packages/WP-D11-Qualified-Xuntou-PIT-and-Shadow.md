# WP-D11 — Qualified Xuntou PIT Replication and Shadow

> **Status:** ROADMAP  
> **Authority:** Executable implementation work package WP-D11  
> **Owner:** Market Regime Alpha maintainers  
> **Last Updated:** 2026-07-26  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** README.md, ../Phase-D-Work-Packages.md, ../../status/Gap-Register.md  
> **Code Evidence:** Acceptance evidence must be added when implemented

## Objective

Run the predeclared formal PIT replication and daily shadow protocol on real qualified XtQuant/Xuntou input.

## Bounded contexts

- Data Source and PIT
- Research Artifact
- Review and Attribution

## Dependencies

- external XtQuant runtime and qualified v4 bundle
- WP-D4
- WP-D8

## Inputs

- real qualified Xuntou export
- sealed protocol
- registered models/targets/costs

## Outputs

- formal replication artifacts
- shadow ledger
- authority assessment

## Expected files/modules

- tools/xuntou/**
- src/market_regime_alpha/research/xuntou_*
- scripts/**
- tests/research/**

Exact files may change after code inspection, but ownership may not move outside the declared bounded contexts without an architecture decision.

## New or changed contracts

- QualifiedSourceManifest
- PITReplicationRun
- ShadowObservationLedger

## Code work

- external export validation
- sealed run
- daily shadow scheduler
- authority report

## Tests

- tamper/reader semantics
- protocol hash
- no fallback
- shadow prediction freeze
- outcome reconciliation

## Acceptance conditions

- real input verified
- minimum dates/coverage satisfied
- sealed protocol unchanged
- formal authority granted only by gates

## Evidence required

- qualified bundle hash
- formal run artifact
- shadow scorecards
- human governance decision

## Risks

- external runtime unavailable
- vendor semantic drift
- overinterpreting short shadow window

## Stop conditions

- qualified input unavailable
- protocol mismatch
- coverage/decision-date minimum fails
- sealed evidence previously contaminated

When a stop condition occurs, publish a blocked/negative result. Do not expand scope or tune unrelated variables to manufacture success.

## Migration effect

Replaces public-source evidence for formal lanes while preserving exploratory artifacts as separate evidence.

## Documentation updates

- docs/status/External-Blockers.md
- docs/status/Current-State.md
- docs/research/PIT-Candidate-Replication-Charter.md

## Explicit non-goals

- profitability promise
- automatic capital scale-up
- fallback to Tencent in formal run
