# Current State

> **Status:** CURRENT_STATUS  
> **Authority:** Single authoritative current implementation-state document  
> **Owner:** Market Regime Alpha maintainers  
> **Last Updated:** 2026-07-26  
> **Supersedes:** ../constitution/implementation-status.md; ../research/R5-Current-Status.md; R5 task status documents as current authorities  
> **Superseded By:** None  
> **Related Documents:** Capability-Matrix.md, Gap-Register.md, External-Blockers.md, ../audit/Post-Consolidation-Code-Audit-2026-07-26.md
> **Code Evidence:** main@772ecfb09410588b5a406ad900d793a5850e60d5 for the audited implementation baseline; path:tests/daily_research/test_v1_characterization.py for convergence evidence

## Overall stage

```text
RESEARCH_PLATFORM_KERNEL_AND_CANDIDATE_EVIDENCE_STAGE
PLATFORM_KERNEL_CONTRACT_IMPLEMENTED
PLATFORM_KERNEL_GOVERNANCE_NOT_HARDENED
DAILY_ARTIFACT_V1_IMPLEMENTED_NON_CANONICAL
DAILY_RESEARCH_CONTRACT_CONVERGENCE_DESIGNED
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
- PIT replication success and blocker semantics;
- Theory/Observable/Model platform contracts;
- content-addressed Target and Evaluation Protocol contracts;
- frozen Experiment Protocol and access-budget mechanics;
- in-memory Model Registry with lifecycle transition gates;
- first comparable Multi-model Candidate Slice and contract tests.

## Implemented non-canonical compatibility layer

`src/market_regime_alpha/daily_research/**` implements immutable historical V1
contracts for DailyResearchSnapshot, CandidateRecommendation and EntryAssessment,
plus aggregate policy, Artifact publication and a semantic Reader. The focused
test suite verifies construction, identity, tamper rejection and round-trip
semantics.

This V1 is `IMPLEMENTED_NON_CANONICAL`. Its names overlap current Phase D
specifications, but its fields and meanings do not implement those specifications.
It does not establish a canonical daily runtime, Prediction Ledger, formal data
authority, Position authority, Alpha evidence or trading authority.

The convergence ADR and field-level migration matrix freeze V1 as a
compatibility layer and keep the current Phase D specifications as the sole
canonical target. Characterization tests pin the V1 module bytes, schema
versions, enums and canonical JSON field sets. A production Adapter and
Canonical Daily runtime remain deferred until WP-D0 stabilizes EvidenceLevel,
governance and PredictionRun identities.

## Implemented but not yet hardened as operational authority

The Platform Kernel is merged and test-backed, but its Registry and Experiment Governance are process-local in-memory implementations. The current Multi-model Slice proves comparable orchestration mechanics; it is not yet an immutable daily Prediction Ledger, persistent governance service, model winner or production runtime.

Required WP-D0 hardening includes persistence/recovery boundaries, registration-bypass closure, DataEligibility/EvidenceLevel separation, platform mypy coverage, B0/B1 equivalence evidence and protocol-bound PredictionRun artifacts.

## Implemented mechanics but externally blocked

The qualified Xuntou v4 path requires an actual XtQuant runtime and a real qualified bundle. Current main can publish a verified blocker but has not produced formal Candidate replication metrics from real provider input.

## Not implemented as canonical Phase D authority

Daily Source Manifest service, canonical Phase D DailyResearchSnapshot runtime,
production stock/ETF universe snapshots, ETF/Theme/Capital context snapshots,
daily multi-model Prediction Ledger, canonical CandidateRecommendation service,
canonical EntryAssessment service, ManualTradeRecord, PositionSnapshot,
HoldingAssessment, ExitAssessment, RecommendationOutcome ledger,
DailyReviewReport, PortfolioDecision, Codex Evidence Pack and QuantDesk
integration.

## Negative result preserved

The frozen MR-2B primary context-conditioned hypothesis was not supported. No secondary established formal authority. This does not invalidate all Candidate research; it rejects the tested conditionality claim.

## Current operating boundary

Research outputs may support manual decisions. No current component may send real orders, mutate broker positions or promote itself based on a daily result.
