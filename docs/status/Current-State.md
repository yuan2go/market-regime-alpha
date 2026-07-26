# Current State

> **Status:** CURRENT_STATUS  
> **Authority:** Single authoritative current implementation-state document  
> **Owner:** Market Regime Alpha maintainers  
> **Last Updated:** 2026-07-26  
> **Supersedes:** ../constitution/implementation-status.md; ../research/R5-Current-Status.md; R5 task status documents as current authorities  
> **Superseded By:** None  
> **Related Documents:** Capability-Matrix.md, Gap-Register.md, External-Blockers.md  
> **Code Evidence:** main@96e41a12d86b3b5f7472c2d4e44011736b087b6b

## Overall stage

```text
RESEARCH_INFRASTRUCTURE_AND_CANDIDATE_EVIDENCE_STAGE
PHASE_D_DESIGNED_NOT_IMPLEMENTED
FORMAL_OOS_ALPHA_NOT_ESTABLISHED
TRADING_AUTHORITY_NOT_GRANTED
```

## Implemented and verified on main

- stable identities and semantic times;
- Dataset eligibility and source contracts;
- historical trading-calendar and PIT universe/eligibility contracts/artifacts;
- Feature definitions/materialization;
- complete Candidate datasets and B0/B1 ranks;
- Candidate diagnostics and immutable research artifacts/readers;
- Provider routing, Tencent exploratory path and Xuntou native/v4 semantic adapters;
- Entry Path Target infrastructure;
- PIT replication success and blocker semantics.

## Implemented mechanics but externally blocked

The qualified Xuntou v4 path requires an actual XtQuant runtime and a real qualified bundle. Current main can publish a verified blocker but has not produced formal Candidate replication metrics from real provider input.

## Not implemented as canonical Phase D authority

DailyResearchSnapshot, ETF/Theme/Capital snapshots, CandidateRecommendation, EntryAssessment, ManualTradeRecord, PositionSnapshot, HoldingAssessment, ExitAssessment, RecommendationOutcome, DailyReviewReport, PortfolioDecision, Codex Evidence Pack and QuantDesk integration.

## Pending PR

Draft PR #12 supplies platform domain/Target/Evaluation/Experiment/Model Registry and a first multi-model slice. CI passed, but main does not gain these capabilities until merge/rebase and post-merge verification.

## Negative result preserved

The frozen MR-2B primary context-conditioned hypothesis was not supported. No secondary established formal authority. This does not invalidate all Candidate research; it rejects the tested conditionality claim.

## Current operating boundary

Research outputs may support manual decisions. No current component may send real orders, mutate broker positions or promote itself based on a daily result.
