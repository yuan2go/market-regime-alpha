# Current State

> **Status:** CURRENT_STATUS  
> **Authority:** Single authoritative current implementation-state document  
> **Owner:** Market Regime Alpha maintainers  
> **Last Updated:** 2026-08-01  
> **Supersedes:** ../constitution/implementation-status.md; ../research/R5-Current-Status.md; R5 task status documents as current authorities  
> **Superseded By:** None  
> **Related Documents:** Capability-Matrix.md, Gap-Register.md, External-Blockers.md, ../architecture/09-Platform-Architecture-V2.md, ../architecture/10-Production-Decision-Lifecycle.md, ../architecture/11-Production-Lifecycle-Hardening-and-Shadow-Operations.md, ../audit/Production-Lifecycle-Hardening-Baseline.md
> **Code Evidence:** `main@a7ce0b4`; Phase 0–7 checkpoint evidence is recorded in the production-lifecycle delivery audit and H0 hardening facts in the new baseline audit.

## Overall stage

```text
RESEARCH_PLATFORM_KERNEL_AND_CANDIDATE_EVIDENCE_STAGE
PLATFORM_MINIMUM_GOVERNANCE_BOUNDARY_HARDENED
PHASE_D_EXPLORATORY_DAILY_LOOP_IMPLEMENTED
EXPLORATORY_DAILY_LOOP_OPERATIONAL
PLATFORM_ARCHITECTURE_V2_COMPLETE
RESEARCH_LAYER_MVP_COMPLETE
PRODUCTION_DECISION_LIFECYCLE_DOCUMENTATION_BASELINE_CREATED
OPERATIONAL_RESEARCH_BRIDGE_IMPLEMENTED_EXPLORATORY
SQLITE_MODEL_AND_EXPERIMENT_GOVERNANCE_IMPLEMENTED
SIGNAL_AND_UNCALIBRATED_PATH_FORECAST_IMPLEMENTED_EXPLORATORY
DURABLE_OPPORTUNITY_AND_THESIS_LIFECYCLE_IMPLEMENTED
INDEPENDENT_PORTFOLIO_RISK_AUTHORITY_IMPLEMENTED_SQLITE
MANUAL_FILL_LEDGER_AND_POSITION_AUTHORITY_IMPLEMENTED_SQLITE
HOLDING_EXIT_AND_TRADE_ATTRIBUTION_IMPLEMENTED_EXPLORATORY
PRODUCTION_DECISION_LIFECYCLE_PHASES_0_TO_7_ENGINEERING_COMPLETE
PRODUCTION_LIFECYCLE_HARDENING_H0_BASELINE_CONFIRMED
SHADOW_READY_NOT_ESTABLISHED
PUBLIC_LIVE_STILL_DATA_BLOCKED
REAL_1455_RUNTIME_VALIDATION_PENDING
FORMAL_OOS_ALPHA_NOT_ESTABLISHED
TRADING_AUTHORITY_NOT_GRANTED
```

## Implemented and verified on the implementation baseline

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
- Model Registry domain validation with closed registration and validated
  transition/restore boundaries, plus a SQLite Repository adapter with
  optimistic versioning, command idempotency and append-only transitions;
- Experiment Governance access-budget validation plus a SQLite Repository
  adapter with optimistic versioning, command idempotency and append-only
  access events;
- immutable protocol-bound Candidate PredictionRuns with full B0/B1 equivalence evidence;
- recoverable SQLite Runtime Journal with separate RunRequestId and source-bound DailyRunId;
- distinct LIVE and REPLAY public Provider profiles, immutable raw archives, field-level SourceManifest and fail-closed DataQualityReport;
- v2 protocol/Provider/Universe Policy/Eligibility Policy Source authority separation;
- recoverable BaoStock history and Tencent Decision Quote acquisition stages whose immutable Artifacts are reused across Quote failure and pre-Receipt process failure;
- independent exact-date BaoStock Security Status acquisition with typed Trading/ST/Listing observations, prior-session scoping and immutable scope-bound V3 Stage Artifacts;
- independently schedulable History, Security Status, Decision Quote and network-free Finalize commands with exact-scope orphan recovery;
- two-level public quality handling: global Source/Policy integrity gate plus per-symbol fail-closed eligibility;
- versioned exploratory BaoStock prior-session daily history semantics without invented historical Available Time or finality;
- content-addressed A-share smoke Universe policy and daily Feature/Candidate materialization;
- per-model CandidateRecommendation and non-ENTER Entry plumbing;
- exact-file-set Phase D Daily Decision Artifact, semantic Reader and Versioned Reader Registry;
- append-only MR1 next-session 10:30 Outcome Settlement and DailyReview Artifact;
- single-session and ten-session Replay with stable hashes;
- real public-source LIVE dry run that published a verified `DATA_BLOCKED` Artifact;
- strict Platform V2 Artifact Envelope and six-layer ownership catalog;
- executable offline Research Layer V0 for Market Regime, Theme Rotation, inferred Capital Evolution and Candidate Discovery;
- content-addressed, versioned model configurations whose thresholds and weights are explicitly unvalidated assumptions;
- exact-file-set ResearchLayerArtifact, semantic Reader, versioned Reader Registry and deterministic recomputation;
- independent PlatformResearchRunner and fixture/archive-only run, replay and report CLI;
- content-addressed SupplementalResearchEvidenceBundle with exact SourceManifest,
  DecisionTime, AvailabilityTime, PIT Theme Membership, ETF/Theme mapping,
  Theme/Capital/Symbol observations, missingness and reason-code validation;
- fail-closed Operational Research Bridge and explicit-config CLI from a
  verified Phase D Daily Artifact plus verified supplemental evidence into the
  existing ResearchInputBundle, PlatformResearchRunner and deterministic
  ResearchLayerArtifact replay;
- versioned, explicit-config A-share long-only Signal model for Price Action,
  Volume Confirmation, Trend Confirmation, VWAP and Overheat, with exact
  CandidateSet/source lineage and no Entry or order action;
- multi-horizon PathForecast that reuses identified EntryPathTarget semantics,
  admits only historical samples available by DecisionTime, preserves
  dual-touch and missing-bar exclusions, and emits MFE/MAE and return quantiles
  without an uncalibrated event probability;
- exact-file-set Signal and PathForecast Artifact readers, deterministic replay
  and CLI run/replay operations;
- versioned TradingOpportunity and TradingThesis aggregates with exact
  Candidate/Signal/Path evidence binding, human actor/reason, expiry,
  invalidation conditions, optimistic concurrency and append-only SQLite
  histories;
- atomic Opportunity confirmation and Thesis creation through a
  storage-neutral Repository Protocol and CLI-first application service;
- explicit-config Portfolio proposals from approved Thesis plus independently
  recomputed RiskDecision for gross, symbol, theme, liquidity, cash, current
  position, T+1 and loss-budget constraints;
- fail-closed risk timeout/data insufficiency, structured rejection codes,
  exact RiskBudget snapshots and durable SQLite/CLI operation restricted to
  `SIMULATION` or `MANUAL_CONFIRMATION`;
- approved-Risk-bound ManualTradeRecord lifecycle and append-only SQLite Fill
  ledger supporting partial fill, cancellation, rejection, unknown state and
  correction records without any broker adapter;
- deterministic PositionProjector whose only position-changing inputs are
  effective Fill events, with FIFO lots, quantity/cost/realized-PnL replay and
  reconciliation-required anomalies;
- versioned A-share long-only PositionLifecycleConfig with independent Holding
  and Exit model roles, explicit thesis-health missingness and actions covering
  HOLD, ADD, REDUCE, EXIT, WAIT and DATA_INSUFFICIENT;
- ADD validation that recomputes and binds a fresh independent RiskDecision;
  invalidated Thesis and missing risk authority fail closed without ADD;
- closed-trade TradeOutcome with Fill-bound realized return, MFE, MAE, capture
  ratio, execution deviation and non-causal selection/entry/holding/exit
  diagnostics;
- protocol-bound RollingScorecard and exact-file LifecycleReview Artifact with
  checksum verification, content-idempotent publish, Reader, CLI and full
  Fill-to-Position-to-assessment-to-outcome deterministic replay;
- compatibility-preserving MR2A and B0/B1 adapters without changes to legacy scores, ranks, PredictionRuns or Readers.

## H0 hardening baseline

The current Phase 0–7 chain is mechanically executable but not yet
account-complete or Shadow-ready. Direct code inspection at `a7ce0b4`
confirmed that Portfolio/Risk sees allocation-local positions only, Position
does not own A-share available/frozen/sellable quantities, ManualTrade/Fill and
TradeOutcome do not preserve a complete Thesis authority chain, REDUCE/EXIT
uses the normal Risk path, Thesis-health support booleans are caller inputs,
the operational bridge has no composite manifest/evidence kind, assessments
are not durable, and continuous Shadow operations do not exist.

The complete evidence and refinements are in
[Production Lifecycle Hardening Baseline](../audit/Production-Lifecycle-Hardening-Baseline.md).
H0 changes documentation only and makes no runtime capability claim.

## Documentation baseline added on 2026-08-01

The repository now contains an agreed target documentation set for the production decision-support lifecycle:

- requirements;
- target architecture;
- ADR-004 modular-monolith organization decision;
- code-level gap analysis;
- implementation work package;
- operations runbook;
- Claude Code implementation prompt;
- documentation-delivery audit.

This documentation establishes the intended sequence from verified evidence through Signal, PathForecast, TradingOpportunity, TradingThesis, Portfolio/Risk, manual records, Position, Holding/Exit and Attribution.

The documentation alone is not runtime implementation evidence. Phases 0–7
now have separate code, test, full-gate and semantic-checkpoint evidence on the
delivery branch. Shadow operations, qualified inputs, validated parameters and
production admission remain separate future evidence.

## Deliberately limited operational authority

The daily Runtime Journal remains an independent persistent and recoverable
authority. Model Registry and Experiment Governance now have storage-neutral
Repository Protocols and isolated SQLite durable adapters; the original
in-memory classes remain the domain validators and unit-test implementation.
The DailyLoop does not silently adopt or mutate shared governance state, and
the existing `daily_runs` schema is unchanged. PostgreSQL parity and
multi-process operational deployment remain future work.

The smoke loop is limited to 20 A-share stocks. The policy contract is configurable, but an approved 100–300-symbol membership source and formal PIT eligibility evidence are not delivered. Operational-pool expansion is additionally blocked until a real public Archive reaches `OUTCOME_PENDING`.

Parquet/DuckDB query projections are deferred and remain rebuildable, non-authoritative views.

Platform V2 is an exploratory Research Layer engineering MVP. Its inputs remain
synthetic fixtures or verified immutable artifacts. The Operational Research
Bridge can combine a verified Daily Artifact with a separately verified
supplemental evidence Artifact, but no qualified operational supplemental
Theme/Capital/PIT mapping bundle currently exists. The initial Market, Theme,
Capital and Candidate thresholds have not established predictive validity.
CandidateSet is opportunity-discovery evidence, not a Recommendation or buy
list. The fixture profiles `exploratory_a_share_1455_v1` and
`synthetic_path_profile_v1` are explicit exploratory/test configurations, not
validated operating parameters. No Path barrier, horizon, Signal threshold or
empirical path statistic has production validity or calibration evidence.

The production-decision architecture explicitly preserves the same authority
ceiling. It authorizes no unattended broker operation; the implemented
Position authority is limited to append-only human-recorded Fill evidence and
does not establish broker truth.

## Implemented mechanics but externally blocked

The qualified Xuntou v4 path requires an actual XtQuant runtime and a real qualified bundle. The existing path can publish a verified blocker but has not produced formal Candidate replication metrics from real provider input.

The latest observed public LIVE run archived 1,200 BaoStock prior daily bars, 20 exact-date BaoStock Status Payloads and 20 Tencent Quotes. BaoStock returned explicit Trading, non-ST and listed values, but the run occurred at 00:47 on the following day. The status values and Quotes were therefore unavailable at the historical 14:55 Decision Time. The verified Artifact is `DATA_BLOCKED` with no Prediction, Recommendation or Entry output. Its real Source Archive replays offline with a stable repeated Replay Hash, but remains blocked.

The same three-stage path reaches `OUTCOME_PENDING` in qualified fixtures and isolates five different per-symbol failures while retaining a 15-symbol Candidate Population. This is engineering evidence, not real public 14:55 runtime evidence.

## Not implemented as canonical authority

The following are not implemented as canonical production-decision authority:

- qualified operational supplemental Theme/Capital/PIT mapping evidence;
- production stock/ETF Universe snapshots;
- operational PIT theme mappings;
- PostgreSQL Model Registry and Experiment Governance adapters and an approved
  multi-process operational deployment;
- validated Signal configuration or operating model;
- calibrated or production-qualified multi-horizon PathForecast;
- production-qualified TradingOpportunity operating policy;
- production-qualified TradingThesis approval/invalidation policy;
- production-qualified RiskBudget and independent RiskDecision policy;
- production-qualified PortfolioDecision allocation policy;
- production authentication/reconciliation operation for ManualTradeRecord and Fill;
- external statement reconciliation around the implemented Fill-derived PositionSnapshot;
- production-qualified Holding/Exit configurations and operating evidence;
- production-qualified complete-trade attribution protocol and rolling sample;
- complete-account Portfolio/Risk snapshots and post-trade exposure;
- strict Opportunity/Thesis/Portfolio/Risk/ManualTrade/Fill/Position/Outcome trace;
- Fill-derived A-share T+1 available/frozen/sellable quantity;
- a separate reducing-risk execution gate;
- Artifact-derived Thesis-health observation building;
- a composite operational evidence manifest and explicit operational evidence kind;
- durable Holding/Exit schedules, histories, exceptions and acknowledgements;
- recoverable ShadowRun, queues, metrics, tracing and alerts;
- production authentication and permissions;
- QuantDesk production integration;
- automated broker adapter.

Platform V2 Theme and Capital snapshots are executable exploratory research contracts, not validated operational authority. Their current labels are direct score classifications rather than proven historical lifecycle state machines.

The historical `daily_research` V1 six-file Artifact, Schema, IDs, Reader and `ENTER` semantics remain a frozen compatibility layer. The current Phase D and target production-decision schemas do not rename or mutate it.

## Negative result preserved

The frozen MR-2B primary context-conditioned hypothesis was not supported. No secondary established formal authority. This does not invalidate all Candidate research; it rejects the tested conditionality claim.

## Current operating boundary

Research outputs may support manual decisions. No current component may send real orders, mutate broker positions or promote itself based on a daily result. Entry plumbing emits `WAIT_CONFIRMATION` or `REJECT`, never `ENTER`.

The hardening documentation does not alter this boundary. Runtime work follows
WP-PDL-HARDENING H1–H9 and retains fail-closed evidence, full-account risk and
manual-only execution semantics.
