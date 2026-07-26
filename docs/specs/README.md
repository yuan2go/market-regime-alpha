# Phase D Specifications

> **Status:** CURRENT_SPECIFICATION  
> **Authority:** Index of current Phase D contracts and shared conventions  
> **Owner:** Market Regime Alpha maintainers  
> **Last Updated:** 2026-07-26  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** ../architecture/05-Phase-D-Daily-Decision-Engine-V1.md, ../status/Gap-Register.md  
> **Code Evidence:** Most contracts are DESIGNED_ONLY; see Capability-Matrix

## Shared conventions

- [Contract Conventions](Contract-Conventions.md)
- [Error Catalog](Error-Catalog.md)

## Aggregate contracts

| Specification | Purpose | Main state |
|---|---|---|
| [DailyResearchSnapshot](DailyResearchSnapshot.md) | Freeze the complete, point-in-time evidence root for one decision instant. | DESIGNED_ONLY |
| [ETFDirectionSnapshot](ETFDirectionSnapshot.md) | Freeze ranked ETF direction evidence at one decision time without granting trade authority. | DESIGNED_ONLY |
| [ThemeDirectionSnapshot](ThemeDirectionSnapshot.md) | Freeze theme breadth, leadership and lifecycle evidence under an identified PIT mapping. | DESIGNED_ONLY |
| [CapitalContextSnapshot](CapitalContextSnapshot.md) | Freeze market-wide liquidity and capital-context observations with explicit field availability. | DESIGNED_ONLY |
| [CandidateRecommendation](CandidateRecommendation.md) | Project one immutable CandidatePrediction into an explainable decision-support record without creating Entry or trade authority. | DESIGNED_ONLY |
| [EntryAssessment](EntryAssessment.md) | Assess whether opening now, waiting, or rejecting adds value relative to the frozen Candidate baseline. | DESIGNED_ONLY |
| [ManualTradeRecord](ManualTradeRecord.md) | Record the human decision, order intent, actual fills and deviation from the system proposal without inferring missing trades. | DESIGNED_ONLY |
| [PositionSnapshot](PositionSnapshot.md) | Freeze actual account position state from manual-ledger or broker-reconciled evidence; never derive it from recommendations. | DESIGNED_ONLY |
| [HoldingAssessment](HoldingAssessment.md) | Evaluate whether an actual position should be held, added, reduced, rotated or receive no model action. | DESIGNED_ONLY |
| [ExitAssessment](ExitAssessment.md) | Evaluate independent exit, reduction and monitoring reasons for an actual position. | DESIGNED_ONLY |
| [RecommendationOutcome](RecommendationOutcome.md) | Attach an observed target/path result to a frozen recommendation without mutating the original prediction. | DESIGNED_ONLY |
| [DailyReviewReport](DailyReviewReport.md) | Aggregate immutable daily facts, layer-specific metrics, failures and controlled research proposals. | DESIGNED_ONLY |
| [FailureReasonTaxonomy](FailureReasonTaxonomy.md) | Version hierarchical, evidence-bound failure codes used by daily review and research governance. | DESIGNED_ONLY |

## Existing implemented research contracts

- [Experiment/Artifact Identity](../research/Research-Artifact-Identity-V3.md)
- [Entry Path Target V1](Entry-Path-Target-V1.md)
- Xuntou/provider specifications already present in this directory retain their individual code evidence.

A specification defines target semantics. Implementation status is owned by `docs/status/Current-State.md` and `Capability-Matrix.md`.
