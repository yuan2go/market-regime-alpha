# Current State

> **Status:** CURRENT_STATUS  
> **Authority:** Single authoritative current implementation-state document  
> **Owner:** Market Regime Alpha maintainers  
> **Last Updated:** 2026-07-28
> **Supersedes:** ../constitution/implementation-status.md; ../research/R5-Current-Status.md; R5 task status documents as current authorities  
> **Superseded By:** None  
> **Related Documents:** Capability-Matrix.md, Gap-Register.md, External-Blockers.md, ../audit/Run-First-Daily-Platform-Delivery.md
> **Code Evidence:** feat/run-first-exploratory-daily-platform@dc9f27a68d3febd4a461e3e299af6ccbba3e70d0

## Overall stage

```text
RESEARCH_PLATFORM_KERNEL_AND_CANDIDATE_EVIDENCE_STAGE
PLATFORM_MINIMUM_GOVERNANCE_BOUNDARY_HARDENED
PHASE_D_EXPLORATORY_DAILY_LOOP_IMPLEMENTED
EXPLORATORY_DAILY_LOOP_OPERATIONAL
FORMAL_OOS_ALPHA_NOT_ESTABLISHED
TRADING_AUTHORITY_NOT_GRANTED
```

## Implemented and verified on the delivery branch

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
- in-memory Model Registry with closed registration and validated transition/restore boundaries;
- immutable protocol-bound Candidate PredictionRuns with full B0/B1 equivalence evidence;
- recoverable SQLite Runtime Journal with separate RunRequestId and source-bound DailyRunId;
- distinct LIVE and REPLAY public Provider profiles, immutable raw archives, field-level
  SourceManifest and fail-closed DataQualityReport;
- content-addressed A-share smoke Universe policy and daily Feature/Candidate materialization;
- per-model CandidateRecommendation and non-ENTER Entry plumbing;
- exact-file-set Phase D Daily Decision Artifact, semantic Reader and Versioned Reader Registry;
- append-only MR1 next-session 10:30 Outcome Settlement and DailyReview Artifact;
- single-session and ten-session Replay with stable hashes;
- real public-source LIVE dry run that published a verified `DATA_BLOCKED` Artifact.

## Deliberately limited operational authority

The daily Runtime Journal is persistent and recoverable, but Model Registry and Experiment
Governance remain process-local in-memory implementations. The delivery closes only the minimum
registration, lifecycle, data/evidence-separation and PredictionRun boundaries required by this
loop; it does not claim complete WP-D0 governance persistence.

The smoke loop is limited to 20 A-share stocks. The policy contract is configurable, but an
approved 100–300-symbol membership source and formal PIT eligibility evidence are not delivered.
Parquet/DuckDB query projections are deferred and remain rebuildable, non-authoritative views.

## Implemented mechanics but externally blocked

The qualified Xuntou v4 path requires an actual XtQuant runtime and a real qualified bundle. The
existing path can publish a verified blocker but has not produced formal Candidate replication
metrics from real provider input. Public LIVE data likewise cannot establish formal PIT:
the observed dry run correctly blocked on availability, trading-status and PIT
membership/eligibility evidence.

## Not implemented as canonical Phase D authority

Production stock/ETF Universe snapshots, ETF/Theme/Capital context snapshots, a validated Entry
model, ManualTradeRecord, PositionSnapshot authority, HoldingAssessment, ExitAssessment, rolling
review/attribution, PortfolioDecision, Codex Evidence Pack and QuantDesk integration.

The historical `daily_research` V1 six-file Artifact, Schema, IDs, Reader and `ENTER` semantics
remain a frozen compatibility layer. The new Phase D schema and Reader do not rename or mutate it.

## Negative result preserved

The frozen MR-2B primary context-conditioned hypothesis was not supported. No secondary established formal authority. This does not invalidate all Candidate research; it rejects the tested conditionality claim.

## Current operating boundary

Research outputs may support manual decisions. No current component may send real orders, mutate
broker positions or promote itself based on a daily result. Entry plumbing emits
`WAIT_CONFIRMATION` or `REJECT`, never `ENTER`.
