# Current State

> **Status:** CURRENT_STATUS  
> **Authority:** Single authoritative current implementation-state document  
> **Owner:** Market Regime Alpha maintainers  
> **Last Updated:** 2026-07-30
> **Supersedes:** ../constitution/implementation-status.md; ../research/R5-Current-Status.md; R5 task status documents as current authorities  
> **Superseded By:** None  
> **Related Documents:** Capability-Matrix.md, Gap-Register.md, External-Blockers.md, ../architecture/09-Platform-Architecture-V2.md, ../audit/Run-First-Daily-Platform-Delivery.md, ../audit/WP-D3-Public-Live-Semantic-Closure.md, ../audit/WP-D3-1-Real-Decision-Evidence-Delivery.md, ../audit/WP-PAV2-Platform-Architecture-V2-Delivery.md
> **Code Evidence:** feat/platform-architecture-v2-research-layer@45fdaa9

## Overall stage

```text
RESEARCH_PLATFORM_KERNEL_AND_CANDIDATE_EVIDENCE_STAGE
PLATFORM_MINIMUM_GOVERNANCE_BOUNDARY_HARDENED
PHASE_D_EXPLORATORY_DAILY_LOOP_IMPLEMENTED
EXPLORATORY_DAILY_LOOP_OPERATIONAL
PLATFORM_ARCHITECTURE_V2_COMPLETE
RESEARCH_LAYER_MVP_COMPLETE
PUBLIC_LIVE_STILL_DATA_BLOCKED
REAL_1455_RUNTIME_VALIDATION_PENDING
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
- v2 protocol/Provider/Universe Policy/Eligibility Policy Source authority separation;
- recoverable BaoStock history and Tencent Decision Quote acquisition stages whose immutable
  Artifacts are reused across Quote failure and pre-Receipt process failure;
- independent exact-date BaoStock Security Status acquisition with typed Trading/ST/Listing
  observations, prior-session scoping and immutable scope-bound V3 Stage Artifacts;
- independently schedulable History, Security Status, Decision Quote and network-free Finalize
  commands with exact-scope orphan recovery;
- two-level public quality handling: global Source/Policy integrity gate plus per-symbol
  fail-closed eligibility;
- versioned exploratory BaoStock prior-session daily history semantics without invented
  historical Available Time or finality;
- content-addressed A-share smoke Universe policy and daily Feature/Candidate materialization;
- per-model CandidateRecommendation and non-ENTER Entry plumbing;
- exact-file-set Phase D Daily Decision Artifact, semantic Reader and Versioned Reader Registry;
- append-only MR1 next-session 10:30 Outcome Settlement and DailyReview Artifact;
- single-session and ten-session Replay with stable hashes;
- real public-source LIVE dry run that published a verified `DATA_BLOCKED` Artifact.
- strict Platform V2 Artifact Envelope and six-layer ownership catalog;
- executable offline Research Layer V0 for Market Regime, Theme Rotation,
  inferred Capital Evolution and Candidate Discovery;
- content-addressed, versioned model configurations whose thresholds and
  weights are explicitly unvalidated assumptions;
- exact-file-set ResearchLayerArtifact, semantic Reader, versioned Reader
  Registry and deterministic recomputation;
- independent PlatformResearchRunner and fixture/archive-only run, replay and
  report CLI;
- compatibility-preserving MR2A and B0/B1 adapters without changes to legacy
  scores, ranks, PredictionRuns or Readers.

## Deliberately limited operational authority

The daily Runtime Journal is persistent and recoverable, but Model Registry and Experiment
Governance remain process-local in-memory implementations. The delivery closes only the minimum
registration, lifecycle, data/evidence-separation and PredictionRun boundaries required by this
loop; it does not claim complete WP-D0 governance persistence.

The smoke loop is limited to 20 A-share stocks. The policy contract is configurable, but an
approved 100–300-symbol membership source and formal PIT eligibility evidence are not delivered.
Operational-pool expansion is additionally blocked until a real public Archive reaches
`OUTCOME_PENDING`.
Parquet/DuckDB query projections are deferred and remain rebuildable, non-authoritative views.

Platform V2 is an offline Research Layer engineering MVP. Its current inputs
are explicitly labelled synthetic fixtures or historical immutable archives.
No public LIVE Adapter creates a ResearchInputBundle, and the initial Market,
Theme, Capital and Candidate thresholds have not established predictive
validity. CandidateSet is opportunity-discovery evidence, not a Recommendation
or buy list.

## Implemented mechanics but externally blocked

The qualified Xuntou v4 path requires an actual XtQuant runtime and a real qualified bundle. The
existing path can publish a verified blocker but has not produced formal Candidate replication
metrics from real provider input.

The latest observed public LIVE run archived 1,200 BaoStock prior daily bars, 20 exact-date
BaoStock Status Payloads and 20 Tencent Quotes. BaoStock returned explicit Trading, non-ST and
listed values, but the run occurred at 00:47 on the following day. The status values and Quotes
were therefore unavailable at the historical 14:55 Decision Time. The verified Artifact is
`DATA_BLOCKED` with no Prediction, Recommendation or Entry output. Its real Source Archive
replays offline with a stable repeated Replay Hash, but remains blocked.

The same three-stage path reaches `OUTCOME_PENDING` in qualified fixtures and isolates five
different per-symbol failures while retaining a 15-symbol Candidate Population. This is
engineering evidence, not real public 14:55 runtime evidence.

## Not implemented as canonical Phase D authority

Production stock/ETF Universe snapshots, operational PIT theme mappings, a
validated Signal or Forecast model, a validated Entry model, ManualTradeRecord,
PositionSnapshot authority, HoldingAssessment, ExitAssessment, rolling
review/attribution, PortfolioDecision, Codex Evidence Pack and QuantDesk
integration. Platform V2 Theme and Capital snapshots are executable
exploratory research contracts, not validated operational authority.

The historical `daily_research` V1 six-file Artifact, Schema, IDs, Reader and `ENTER` semantics
remain a frozen compatibility layer. The new Phase D schema and Reader do not rename or mutate it.

## Negative result preserved

The frozen MR-2B primary context-conditioned hypothesis was not supported. No secondary established formal authority. This does not invalidate all Candidate research; it rejects the tested conditionality claim.

## Current operating boundary

Research outputs may support manual decisions. No current component may send real orders, mutate
broker positions or promote itself based on a daily result. Entry plumbing emits
`WAIT_CONFIRMATION` or `REJECT`, never `ENTER`.
