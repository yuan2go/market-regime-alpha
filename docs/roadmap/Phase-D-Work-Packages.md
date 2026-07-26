# Phase D Work Packages

> **Status:** ROADMAP  
> **Authority:** Ordered index for the A-share daily research and manual-decision engine  
> **Owner:** Market Regime Alpha maintainers  
> **Last Updated:** 2026-07-26  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** ../architecture/05-Phase-D-Daily-Decision-Engine-V1.md, ../status/Gap-Register.md, work-packages/README.md  
> **Code Evidence:** Acceptance evidence is package-specific

| Package | Objective | Dependencies | Primary outputs |
|---|---|---|---|
| [WP-D0](work-packages/WP-D0-Platform-Governance-Kernel.md) | Platform Governance Kernel | Draft PR #12 or equivalent reviewed implementation, current main research artifact contracts | one canonical registry namespace, model lifecycle and evidence-level gates, migration decision for PR #12, compatibility tests |
| [WP-D1](work-packages/WP-D1-Source-Manifest-and-Quality-Gates.md) | Daily Source Manifest and Data Quality Gates | WP-D0 for artifact identity, existing provider/data/time contracts | SourceManifest, DataQualityReport, raw immutable archive, freshness and authority gates |
| [WP-D2](work-packages/WP-D2-Daily-Universe-and-Eligibility.md) | Daily Stock/ETF Universe and Eligibility | WP-D1, existing trading calendar/PIT universe/eligibility contracts | UniverseSnapshot, EligibilitySnapshot, ExclusionLedger |
| [WP-D2E](work-packages/WP-D2E-Tencent-Exploratory-Daily-Loop.md) | Tencent Exploratory Daily Vertical Slice | WP-D0, WP-D1, WP-D2, existing B0/B1 and target materializers | DailyResearchSnapshot profile, B0/B1 PredictionRuns, CandidateRecommendations, next-session RecommendationOutcomes, minimal DailyReviewReport, raw/source archive |
| [WP-D3](work-packages/WP-D3-Market-ETF-Theme-Capital-Context.md) | Market, ETF, Theme and Capital Context | WP-D1, WP-D2, WP-D2E operational feedback | MarketContextSnapshot, ETFDirectionSnapshot, ThemeDirectionSnapshot, CapitalContextSnapshot |
| [WP-D4](work-packages/WP-D4-Multi-Model-Candidate-Prediction-Ledger.md) | Multi-model Candidate Prediction Ledger | WP-D0, WP-D2, WP-D3 or explicit no-context lane, B0/B1 | PredictionRun, complete rank/rejection ledger, CandidateRecommendation, model comparison artifact |
| [WP-D5](work-packages/WP-D5-Entry-Assessment-V1.md) | Entry Assessment V1 | WP-D4, existing Entry Path Target infrastructure | EntryAssessment, Entry evaluation report |
| [WP-D6](work-packages/WP-D6-Manual-Trade-and-Position-Authority.md) | Manual Trade Record and Canonical Position Authority | WP-D4, WP-D5 optional for linked proposals | ManualTradeRecord, PositionSnapshot, reconciliation report |
| [WP-D7](work-packages/WP-D7-Holding-and-Exit-V1.md) | Independent Holding and Exit V1 | WP-D6, Feature/Context inputs | HoldingAssessment, ExitAssessment, holding/exit evaluation |
| [WP-D8](work-packages/WP-D8-Outcome-Review-and-Failure-Attribution.md) | Outcome Matching, Daily Review and Failure Attribution | WP-D4, WP-D5, WP-D6, WP-D7 as applicable | RecommendationOutcome, DailyReviewReport, FailureAttribution, 5/20/60/120-day scorecards |
| [WP-D9](work-packages/WP-D9-Portfolio-and-Execution-Simulation.md) | Portfolio and Execution Simulation | validated outputs from WP-D4–D8 | PortfolioDecision, SimulationResult, risk exposure report |
| [WP-D10](work-packages/WP-D10-Codex-Research-Feedback.md) | Codex Research Feedback | WP-D8, WP-D0 governance | CodexDiagnosis, ImprovementProposal, ExperimentProposal, ProposalReview |
| [WP-D11](work-packages/WP-D11-Qualified-Xuntou-PIT-and-Shadow.md) | Qualified Xuntou PIT Replication and Shadow | external XtQuant runtime and qualified v4 bundle, WP-D4, WP-D8 | formal replication artifacts, shadow ledger, authority assessment |
| [WP-D12](work-packages/WP-D12-QuantDesk-Workbench-Integration.md) | QuantDesk Workbench Integration | stable Phase D APIs from D4–D10 | Research Workbench, Daily Decision Workbench, Review Workbench, typed API client |

Detailed scope, files, contracts, tests, evidence, risks, stop conditions, migration effects and documentation updates are defined in [the work-package index](work-packages/README.md).

## Global completion rule

A work package cannot be marked complete when required PIT evidence is unavailable, a parent model fails its gate, population coverage is below protocol, the primary change cannot be isolated, or declared acceptance evidence is missing.
