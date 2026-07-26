# Phase D Specifications

> **Status:** CURRENT_SPECIFICATION  
> **Authority:** Index of current Phase D data and decision contracts  
> **Owner:** Market Regime Alpha maintainers  
> **Last Updated:** 2026-07-26  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** ../architecture/05-Phase-D-Daily-Decision-Engine-V1.md, ../status/Gap-Register.md  
> **Code Evidence:** Most Phase D contracts are DESIGNED_ONLY; existing Entry/Xuntou specs retain their code references

| Specification | Purpose | Main state |
|---|---|---|
| [DailyResearchSnapshot](DailyResearchSnapshot.md) | immutable daily evidence root | DESIGNED_ONLY |
| [ETFDirectionSnapshot](ETFDirectionSnapshot.md) | ETF context | DESIGNED_ONLY |
| [ThemeDirectionSnapshot](ThemeDirectionSnapshot.md) | theme context | DESIGNED_ONLY |
| [CapitalContextSnapshot](CapitalContextSnapshot.md) | capital/liquidity context | DESIGNED_ONLY |
| [CandidateRecommendation](CandidateRecommendation.md) | present structured Candidate evidence | DESIGNED_ONLY |
| [EntryAssessment](EntryAssessment.md) | opening suitability | DESIGNED_ONLY; Entry Path targets exist |
| [ManualTradeRecord](ManualTradeRecord.md) | user decision/order/fill/deviation | DESIGNED_ONLY |
| [PositionSnapshot](PositionSnapshot.md) | canonical actual position state | DESIGNED_ONLY |
| [HoldingAssessment](HoldingAssessment.md) | continuation/add/reduce/rotate | DESIGNED_ONLY |
| [ExitAssessment](ExitAssessment.md) | independent exit reasons | DESIGNED_ONLY |
| [RecommendationOutcome](RecommendationOutcome.md) | realized target/path result | DESIGNED_ONLY |
| [DailyReviewReport](DailyReviewReport.md) | daily/rolling review | DESIGNED_ONLY |
| [FailureReasonTaxonomy](FailureReasonTaxonomy.md) | hierarchical attribution | DESIGNED_ONLY |
| [Experiment Identity](../research/Research-Artifact-Identity-V3.md) | experiment/artifact identity | IMPLEMENTED_AND_VERIFIED in existing research paths |
