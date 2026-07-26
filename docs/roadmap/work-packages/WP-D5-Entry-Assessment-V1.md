# WP-D5 — Entry Assessment V1

> **Status:** ROADMAP  
> **Authority:** Executable implementation work package WP-D5  
> **Owner:** Market Regime Alpha maintainers  
> **Last Updated:** 2026-07-26  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** README.md, ../Phase-D-Work-Packages.md, ../../status/Gap-Register.md  
> **Code Evidence:** Acceptance evidence must be added when implemented

## Objective

Implement fixed baselines and the first path-aware Entry model, measuring incremental value separately from Candidate quality.

## Bounded contexts

- Entry

## Dependencies

- WP-D4
- existing Entry Path Target infrastructure

## Inputs

- CandidateRecommendation
- decision-time price/location/volume/context
- Entry ModelDefinition
- Entry Path Targets

## Outputs

- EntryAssessment
- Entry evaluation report

## Expected files/modules

- src/market_regime_alpha/strategies/entry/**
- src/market_regime_alpha/application/**
- tests/strategies/entry/**

Exact files may change after code inspection, but ownership may not move outside the declared bounded contexts without an architecture decision.

## New or changed contracts

- EntryAssessment
- EntryModelDefinition

## Code work

- fixed immediate-entry baseline
- WAIT/REJECT rules
- first transparent Entry model
- assessment persistence/API

## Tests

- no target leakage
- action-field validation
- ENTER vs WAIT vs REJECT strata
- MAE/MFE/cost metrics

## Acceptance conditions

- Entry lowers adverse metrics or improves cost-adjusted return while retaining opportunity
- reduced count alone not success
- assessments expire and fail closed

## Evidence required

- incremental evaluation
- missed-opportunity report
- assessment fixtures

## Risks

- hiding poor Candidate quality
- future path leakage
- overly restrictive gate

## Stop conditions

- Entry cannot beat fixed baseline under declared metric
- path evidence unavailable
- Candidate lane unstable

When a stop condition occurs, publish a blocked/negative result. Do not expand scope or tune unrelated variables to manufacture success.

## Migration effect

Adds an independent Entry layer; Legacy buy-point signals remain challengers/control arms only.

## Documentation updates

- docs/research/Entry-Research.md
- docs/specs/EntryAssessment.md
- docs/status/Gap-Register.md

## Explicit non-goals

- orders
- position state
- Exit logic
