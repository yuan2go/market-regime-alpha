# End-to-End Research and Decision Flow

> **Status:** CURRENT_ARCHITECTURE  
> **Authority:** Canonical research and daily decision flow  
> **Owner:** Market Regime Alpha maintainers  
> **Last Updated:** 2026-07-26  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** 01-Domain-Boundaries.md, 03-Research-Artifact-Architecture.md, 05-Phase-D-Daily-Decision-Engine-V1.md  
> **Code Evidence:** Current main implements the early research spine; Phase D objects remain planned

## Research flow

```text
Theory / market observation
→ formal Observable and Feature definition
→ falsifiable hypothesis
→ frozen experiment protocol
→ identified PIT dataset
→ backtest / walk-forward / validation
→ immutable evaluation artifact
→ model lifecycle decision
```

## Daily decision flow

```text
Provider / Raw Data
→ PIT Normalization and Source Manifest
→ Trading Calendar
→ Stock / ETF Universe
→ Eligibility
→ Market / ETF / Theme / Capital Context
→ Candidate Population
→ Feature Materialization
→ Candidate Prediction and Recommendation
→ Entry Assessment
→ Human Decision / Manual Trade Record
→ Position Snapshot
→ Holding / Exit Assessment
→ Outcome Matching
→ Daily Review / Failure Attribution
→ Rolling Validation / Research Feedback
```

## Commands

- `AcquireDailySources`
- `BuildDailyUniverse`
- `MaterializeDailyContext`
- `RunCandidateModels`
- `AssessCandidateEntry`
- `RecordManualDecision`
- `BuildPositionSnapshot`
- `AssessHoldingAndExit`
- `MatchRecommendationOutcomes`
- `PublishDailyReview`
- `ProposeResearchExperiment`

## Events

- `DailyResearchSnapshotFrozen`
- `CandidatePredictionsPublished`
- `EntryAssessmentsPublished`
- `ManualTradeRecorded`
- `PositionSnapshotFrozen`
- `HoldingExitAssessmentsPublished`
- `RecommendationOutcomesMatched`
- `DailyReviewPublished`
- `ResearchProposalCreated`

## Failure behavior

Every stage is fail-closed. Missing/late data, unknown membership, unresolved eligibility or incompatible model/data evidence yields an explicit blocked or unresolved state; it must not trigger provider fallback or fabricated candidates unless the fallback is predeclared by the source policy.
