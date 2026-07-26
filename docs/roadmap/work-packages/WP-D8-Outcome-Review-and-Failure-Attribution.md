# WP-D8 — Outcome Matching, Daily Review and Failure Attribution

> **Status:** ROADMAP  
> **Authority:** Executable implementation work package WP-D8  
> **Owner:** Market Regime Alpha maintainers  
> **Last Updated:** 2026-07-26  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** README.md, ../Phase-D-Work-Packages.md, ../../status/Gap-Register.md  
> **Code Evidence:** Acceptance evidence must be added when implemented

## Objective

Match future outcomes without mutating predictions and produce reproducible daily/rolling layer-specific reviews.

## Bounded contexts

- Review and Attribution

## Dependencies

- WP-D4
- WP-D5
- WP-D6
- WP-D7 as applicable

## Inputs

- frozen recommendations/assessments
- future market data
- manual trades/positions
- Target/Evaluation protocols
- failure taxonomy

## Outputs

- RecommendationOutcome
- DailyReviewReport
- FailureAttribution
- 5/20/60/120-day scorecards

## Expected files/modules

- src/market_regime_alpha/review/**
- src/market_regime_alpha/evaluation/**
- tests/review/**

Exact files may change after code inspection, but ownership may not move outside the declared bounded contexts without an architecture decision.

## New or changed contracts

- RecommendationOutcome
- DailyReviewReport
- FailureReasonTaxonomy

## Code work

- target scheduler/matcher
- layer metrics
- failure classifier
- rolling scorecards
- replay

## Tests

- NOT_YET_OBSERVED null rules
- prediction immutability
- target identity
- facts/inferences/hypotheses separation
- scorecard reproducibility

## Acceptance conditions

- outcomes attach by immutable refs
- Candidate/Entry/Exit/Execution effects separated
- UNCLASSIFIED allowed
- daily and rolling reports replay exactly

## Evidence required

- replay report
- failure examples
- scorecard hashes
- late/unavailable outcome tests

## Risks

- post-hoc storytelling
- metric conflation
- silent missing outcomes

## Stop conditions

- target cannot be reproduced
- source outcome semantics unknown
- attribution lacks required evidence

When a stop condition occurs, publish a blocked/negative result. Do not expand scope or tune unrelated variables to manufacture success.

## Migration effect

Consolidates scattered diagnostics into canonical outcome/review artifacts; historical reports remain evidence.

## Documentation updates

- docs/research/Failure-Attribution.md
- docs/research/Negative-and-Inconclusive-Results.md
- docs/specs/RecommendationOutcome.md
- docs/specs/DailyReviewReport.md

## Explicit non-goals

- automatic model mutation
- causal certainty
- promotion from one day
