# WP-D4 — Multi-model Candidate Prediction Ledger

> **Status:** ROADMAP  
> **Authority:** Executable implementation work package WP-D4  
> **Owner:** Market Regime Alpha maintainers  
> **Last Updated:** 2026-07-26  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** README.md, ../Phase-D-Work-Packages.md, ../../status/Gap-Register.md  
> **Code Evidence:** Acceptance evidence must be added when implemented

## Objective

Run comparable Candidate models on the same PIT dataset and freeze complete rankings, rejections and recommendation projections.

## Bounded contexts

- Candidate Discovery
- Research Artifact

## Dependencies

- WP-D0
- WP-D2
- WP-D3 or explicit no-context lane
- B0/B1

## Inputs

- CandidateResearchDataset
- FeatureMatrix
- ModelDefinitions
- TargetDefinition
- EvaluationProtocol

## Outputs

- PredictionRun
- complete rank/rejection ledger
- CandidateRecommendation
- model comparison artifact

## Expected files/modules

- src/market_regime_alpha/candidates/**
- src/market_regime_alpha/platform/**
- src/market_regime_alpha/review/**
- tests/candidates/**

Exact files may change after code inspection, but ownership may not move outside the declared bounded contexts without an architecture decision.

## New or changed contracts

- PredictionRun
- CandidatePrediction
- CandidateRecommendation
- ComparableLane

## Code work

- adapt B0/B1
- register challenger only under budget
- persist full ranking
- recommendation projection
- matched-K comparison

## Tests

- same dataset/model deterministic
- rank/rejection totals reconcile
- score/probability guard
- comparable-lane incompatibility rejected
- empty output valid

## Acceptance conditions

- full population ledger frozen
- B0/B1 outputs preserved
- recommendation never contains Entry action
- pairwise overlap and primary metrics available

## Evidence required

- prediction artifacts
- comparison report
- hash-equivalence tests
- coverage report

## Risks

- leaderboard overfitting
- top-K-only storage
- model identity collision

## Stop conditions

- population or target differs across direct comparison
- validation budget exceeded
- challenger changes multiple primary variables

When a stop condition occurs, publish a blocked/negative result. Do not expand scope or tune unrelated variables to manufacture success.

## Migration effect

Moves Candidate runtime from task-specific WP3 runners to a canonical daily ledger while retaining adapters.

## Documentation updates

- docs/research/Candidate-Research.md
- docs/specs/CandidateRecommendation.md
- docs/status/Capability-Matrix.md

## Explicit non-goals

- Entry timing
- position sizing
- automatic model selection
