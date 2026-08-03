# Current State

> **Status:** CURRENT_STATUS  
> **Authority:** Single authoritative current implementation-state document  
> **Owner:** Market Regime Alpha maintainers  
> **Last Updated:** 2026-08-04
> **Supersedes:** ../constitution/implementation-status.md; ../research/R5-Current-Status.md; R5 task status documents as current authorities  
> **Superseded By:** None  
> **Related Documents:** Capability-Matrix.md, Gap-Register.md, External-Blockers.md, ../architecture/09-Platform-Architecture-V2.md, ../architecture/10-Production-Decision-Lifecycle.md, ../architecture/11-Production-Lifecycle-Hardening-and-Shadow-Operations.md, ../audit/H6-Composite-Operational-Evidence-Delivery.md, ../audit/H5-Thesis-Health-Delivery.md, ../audit/H4-Risk-Route-Delivery.md, ../audit/Production-Decision-Lifecycle-Delivery.md, ../audit/Production-Lifecycle-Hardening-Delivery.md, ../audit/Current-Main-Code-Audit-2026-08-01.md
> **Code Evidence:** H6 hardened implementation checkpoint `654e02556080d1476b399ee5145989be743f47a0`; H5 checkpoint `831edd6b2ae044d3bd1f3abcec97a30e47082071`; H4 checkpoint `3672067549e1b72a8bfd390f8320e2a7c55c599e`
> **Verification Boundary:** This status distinguishes current-code inspection, historical checkpoint test records and independently observed runtime evidence. Historical PASS records do not establish that the current HEAD passes.

## 1. Executive status

The repository is a research-first A-share Alpha Research Operating System and manual decision-support platform. It is not a production broker execution system and it has not established formal out-of-sample Alpha.

The implemented architecture separates:

```text
Data and Evidence
→ Research Opportunity Discovery
→ Signal and Path Forecast
→ Opportunity and Thesis
→ Portfolio and Independent Risk
→ Manual Execution and Fill
→ Position, Holding and Exit
→ Outcome, Attribution and Review
```

The current engineering baseline contains substantial implementations across this chain, including immutable content-addressed artifacts, semantic Readers, recoverable SQLite journals, append-only Fill evidence, complete-account Portfolio/Risk, Thesis-scoped Position books and Fill/calendar-derived A-share T+1 sellability.

The H6 implementation checkpoint extends the green H4/H5 baseline with an
explicit Composite Operational Evidence authority. It binds verified Daily and
Supplemental packages through a content-addressed policy, immutable terminal
manifest, append-only SQLite replay index and `ResearchInputBundleV2` labelled
`OPERATIONAL_EXPLORATORY_ARCHIVE`. It does not promote exploratory evidence,
run a new model, transition a Thesis, call H4, create a ManualTrade/Fill/Broker
Order or grant trading authority.

## 2. Current stage

```text
RESEARCH_PLATFORM_KERNEL_IMPLEMENTED
IMMUTABLE_RESEARCH_EVIDENCE_IMPLEMENTED
EXPLORATORY_DAILY_LOOP_IMPLEMENTED
PLATFORM_V2_RESEARCH_LAYER_IMPLEMENTED_EXPLORATORY
PRODUCTION_DECISION_LIFECYCLE_PHASES_0_TO_7_ENGINEERING_COMPLETE_ON_PRIOR_CHECKPOINT
H1_COMPLETE_ACCOUNT_PORTFOLIO_RISK_IMPLEMENTED_SQLITE
H2_THESIS_TO_OUTCOME_TRACE_IMPLEMENTED_SQLITE
H3_FILL_CALENDAR_DERIVED_T_PLUS_ONE_IMPLEMENTED
H4_REDUCING_RISK_ROUTE_IMPLEMENTED_AND_VERIFIED
H4_IMPLEMENTATION_CHECKPOINT_ENGINEERING_GATE_VERIFIED
H5_ARTIFACT_DERIVED_THESIS_HEALTH_IMPLEMENTED_AND_VERIFIED
H5_V2_OPERATIONAL_ASSESSMENT_ADAPTER_IMPLEMENTED
H5_IMPLEMENTATION_CHECKPOINT_ENGINEERING_GATE_VERIFIED
H6_COMPOSITE_OPERATIONAL_EVIDENCE_IMPLEMENTED_AND_VERIFIED
H6_RESEARCH_INPUT_BUNDLE_V2_IMPLEMENTED
H6_IMPLEMENTATION_CHECKPOINT_ENGINEERING_GATE_VERIFIED
SHADOW_READY_NOT_ESTABLISHED
FORMAL_PIT_NOT_ESTABLISHED
FORMAL_OOS_ALPHA_NOT_ESTABLISHED
TRADING_AUTHORITY_NOT_GRANTED
REAL_BROKER_AUTHORITY_NOT_IMPLEMENTED
PRODUCTION_READINESS_NOT_ESTABLISHED
```

## 3. Implemented capabilities

### 3.1 Evidence and research foundation

Implemented:

- stable content identities and semantic time contracts;
- `SourceManifest`, source-field lineage and fail-closed data quality;
- immutable exact-file artifacts with checksums and semantic Readers;
- historical trading calendar, PIT Universe and Eligibility contracts;
- Feature definitions and materialization;
- B0/B1 Candidate datasets, ranks and immutable PredictionRuns;
- replay and tamper verification for major research artifacts;
- explicit `AvailabilityTime` and DecisionTime leakage checks.

These mechanics establish research reproducibility and lineage. They do not establish provider truth, formal PIT completeness or economic validity.

### 3.2 Exploratory daily loop

`application/daily_loop/runner.py` implements the principal daily research chain:

```text
BaoStock History
→ BaoStock Security Status
→ Tencent Decision Quote
→ Source Archive and SourceManifest
→ DataQuality
→ Universe and Eligibility
→ Features
→ B0/B1 PredictionRuns
→ CandidateRecommendation
→ EntryAssessment
→ Daily Decision Artifact
→ next-session 10:30 Outcome and DailyReview
```

The loop is recoverable through a SQLite Runtime Journal and can publish a verified `DATA_BLOCKED` artifact rather than silently continue with invalid inputs.

The operational runtime remains restricted to a small smoke Universe and exploratory data authority. A real controlled 14:55 run reaching `OUTCOME_PENDING` has not been established as current formal evidence.

### 3.3 Platform V2 research layer

Implemented exploratory models:

- Market Regime;
- Theme Rotation;
- inferred Capital Evolution;
- Candidate Discovery;
- five-factor Signal;
- multi-horizon PathForecast.

The Research Layer is deterministic and content-addressed. Thresholds and weights are explicit configuration assumptions. They are not validated operating parameters.

Capital Evolution is an inference from observable proxies, not evidence of hidden institutional intent. CandidateSet is opportunity-discovery evidence, not a recommendation or buy list.

### 3.4 Entry boundary

The current canonical daily Entry component is plumbing only:

```text
REJECT
or
WAIT_CONFIRMATION
never ENTER
```

When data and eligibility pass, the fixed blocker remains `ENTRY_MODEL_NOT_YET_VALIDATED`. A production-qualified Entry Model is not implemented.

### 3.5 Opportunity and Thesis

Implemented:

- immutable evidence binding from CandidateSet, Signal and PathForecast;
- versioned `TradingOpportunity` and `TradingThesis` aggregates;
- explicit expiry, approval and invalidation transitions;
- actor, reason and timestamps;
- SQLite compare-and-swap, global command idempotency and append-only history;
- atomic Opportunity confirmation and initial Thesis creation.

The implementation supports research-backed human decisions. It does not grant automated order authority.

### 3.6 H1 complete-account Portfolio and Risk

Implemented:

- content-identified complete/partial account snapshots;
- explicit completeness, reconciliation state and source Position references;
- proposed deltas applied to every account position;
- post-trade gross, symbol, theme, cash, liquidity and maximum-loss evaluation;
- structured `DATA_INSUFFICIENT` for partial, stale, future or unreconciled inputs;
- independent Risk recomputation before persistence;
- atomic SQLite persistence and command idempotency.

The hardened H3 application path should be used for new work because the older H1 compatibility entry can accept caller-declared Position quantities.

### 3.7 H2 authority trace

Implemented:

- deterministic `PositionBook` scoped to account, symbol and Thesis;
- one OPEN Thesis book per account/symbol as the first-version restriction;
- traceable ManualTrade bindings to Opportunity, Thesis, Portfolio, Risk and post-trade snapshot;
- Fill retained as the only position-changing fact;
- Thesis-scoped Position projection;
- traceable closed-trade outcome validation across the full authority chain;
- restart/replay reconstruction through SQLite indexes and histories.

This is engineering traceability for manual evidence, not broker truth.

### 3.8 H3 Fill-derived A-share T+1 Position Authority

Implemented:

- Position lots with trade date, next explicit sellable session and settlement state;
- total, available, frozen and today-acquired quantities;
- explicit `TradingCalendarArtifact` identity and hash;
- typed symbol-session trading status evidence;
- same-session buy freezing;
- holiday and Friday/weekend handling through explicit sessions;
- suspension and missing/late status fail-closed behavior;
- reconciliation-required states for invalid sells or inconsistent Fill history;
- complete-account Risk input constructed from OPEN Position books and V3 Position snapshots.

The source remains human-recorded Fill evidence and synthetic/test calendar/status evidence. External statement reconciliation is not implemented.

### 3.9 H4 increasing versus reducing risk

H4 is **IMPLEMENTED_AND_VERIFIED** at `3672067549e1b72a8bfd390f8320e2a7c55c599e`:

- `RiskChangeKind` separates OPEN/ADD from REDUCE/EXIT;
- increasing-risk references require an approved complete-account RiskDecision;
- reducing-risk decisions require a Thesis-scoped H3 Position;
- target/order quantities cannot increase or overstate the position;
- A-share sellable quantity, suspension, price-limit state, position/observation freshness and liquidity participation are checked;
- output is `PERMITTED_FOR_MANUAL_CONFIRMATION`, `BLOCKED` or `DATA_INSUFFICIENT`;
- migration 007 defines append-only reducing decisions and idempotency commands, with repeat-safe initialization and validation of columns, constraints, foreign keys and trigger semantics;
- `SQLiteRiskRouteRepository` restores all canonical evidence and reruns the Gate before returning a decision;
- `RiskRouteApplicationService` validates the command, performs semantic replay and atomically persists the immutable evidence bundle;
- public package exports and `application/trading_lifecycle` expose the stable H4 route;
- `scripts/assess_risk_reduction.py` emits `DECISION_ONLY`, `NO_ORDER_CREATED` and `TRADING_AUTHORITY_NOT_GRANTED`.

The CLI is an assessment/persistence entry point only. Connecting a permitted decision to ManualTrade/Fill is the separate H4.5 work package and is not part of H4.

### 3.10 H5 artifact-derived Thesis Health

H5 is **IMPLEMENTED_AND_VERIFIED** at `831edd6b2ae044d3bd1f3abcec97a30e47082071`:

- `ThesisInvalidationRuleSet` binds every existing Thesis invalidation condition exactly once to a typed, versioned rule; descriptions and condition names are never parsed;
- `ThesisHealthRuleConfiguration` content-identifies every freshness threshold, component-state mapping and exploratory Path rule;
- `ThesisHealthInputBundle` stores the exact current Market/Theme/Capital/Candidate/Signal/Path/price evidence, configuration, rule set, optional Manual evidence and explicit prior V2 Observation for private replay;
- the Builder verifies canonical identities, SourceManifest lineage, Candidate→research, Signal→Candidate, Path→Signal, symbol/theme scope, creation-versus-current evidence and explicit price/research skew;
- `ThesisHealthObservationV2` records observed, prior-effective and effective state. `INVALIDATED` is terminal; `DATA_INSUFFICIENT` does not advance effective state; `WEAKENING` cannot recover automatically;
- migration 008 and `SQLiteThesisHealthRepository` use `BEGIN IMMEDIATE`, command hash/idempotency, append-only triggers, canonical restoration, prior-chain validation and Builder recomputation;
- `ThesisHealthApplicationService` accepts actual typed domain inputs, loads the explicitly bound prior Observation, constructs the private bundle internally and persists the derived Observation atomically;
- `scripts/build_thesis_health.py` reads verified Research/Signal/Path packages, rejects V1 support booleans and emits `OBSERVATION_ONLY`, `NO_TRADE_ACTION_CREATED` and `TRADING_AUTHORITY_NOT_GRANTED`;
- `OperationalPositionAssessmentServiceV2` consumes the derived effective health and a Thesis-scoped H3 T+1 PositionSnapshot directly, reusing the existing Holding/Exit decision core without constructing a fake V1 Observation.

The H5 private replay bundle is not an H6 CompositeOperationalInputManifest and does not promote DataEligibility, PIT status or source authority. Manual invalidation actor strings are not authenticated production identities. V1 Readers and historical LifecycleReview inputs remain readable, but no new V2 operational path accepts V1 support booleans.

### 3.11 H6 composite operational evidence

H6 is **IMPLEMENTED_AND_VERIFIED** at
`654e02556080d1476b399ee5145989be743f47a0`:

- `CompositeOperationalCompositionPolicy` content-identifies explicit required
  component roles, field authorities, DecisionTime/coverage/conflict policy and
  the builder revision;
- `CompositeOperationalInputManifest` binds both verified packages, both
  SourceManifests, typed component/field authority references, missingness,
  conflicts and a fixed exploratory/non-PIT/non-OOS/non-trading ceiling;
- canonical H6 timestamps normalize to whole-second UTC `Z`; container
  availability is derived from explicit underlying retrieval/availability
  evidence rather than invented from DecisionTime;
- only immutable terminal `VERIFIED`, `DATA_INSUFFICIENT` and `CONFLICTED`
  manifests are publishable; only `VERIFIED` can enter Platform V2;
- exact three-file package publication detects checksum, semantic, policy and
  identity tamper and uses verified staging plus atomic rename;
- migration 009 and `SQLiteCompositeOperationalRepository` add append-only
  manifest/component/field/command indexes, semantic idempotency, full
  projection validation, original-package loading and Builder replay;
- `CompositeOperationalEvidenceApplicationService` implements the explicit
  file-first/SQLite-second transaction boundary and restart repair without
  claiming cross-storage atomicity;
- `ResearchInputBundleV2` uses
  `OPERATIONAL_EXPLORATORY_ARCHIVE`, preserves Daily as primary
  `source_manifest`, binds the Composite Manifest directly in all Platform V2
  component lineage and preserves V1 Reader/hash semantics;
- `scripts/build_composite_operational_manifest.py` builds/indexes terminal
  evidence only; the operational research CLI requires the H6 package and
  replays the Builder against the original Daily/Supplemental packages before
  running existing research models;
- cross-stage testing proves H6 Research output can feed Signal, PathForecast
  and H5 V2 health without turning the H5 private replay bundle into H6
  authority.

H6 is an authority-composition and lineage capability. It does not establish a
qualified Supplemental producer, formal PIT/OOS evidence, a sustained
operational run or any execution authority.

### 3.12 Manual execution, Position and review

Implemented on prior verified checkpoints:

- approved-Risk-bound manual intent;
- partial, filled, cancelled, rejected, unknown and reconciliation-required states;
- append-only Fill and correction records;
- SQLite triggers prohibiting Fill UPDATE/DELETE;
- FIFO Position reconstruction and realized PnL;
- separate Holding and Exit assessment roles;
- ADD requiring a fresh independent RiskDecision;
- closed TradeOutcome with return, MFE, MAE, capture ratio and execution deviation;
- immutable LifecycleReview and rolling diagnostic scorecard.

No component contacts a broker or treats recorded Fill as broker authority.

## 4. Persistence, transactions and consistency

Implemented SQLite repositories generally use:

- `BEGIN IMMEDIATE` transactions;
- `busy_timeout`;
- command idempotency key plus command hash;
- optimistic version compare-and-swap;
- append-only event tables;
- rollback on failure;
- restore by replaying and validating history;
- recomputation of Risk before accepting caller-supplied decisions.

This is a strong single-machine engineering boundary. It is not multi-process or distributed production authority.

Not implemented:

- PostgreSQL parity for the full lifecycle;
- distributed lease/fencing semantics;
- cross-database or file/database transactions;
- outbox/message delivery guarantees;
- durable whole-lifecycle Saga;
- multi-instance Shadow operations.

## 5. Frontend, scheduler and broker boundary

The current canonical lifecycle is CLI/Application-Service driven. There is no production UI consuming verified Artifacts and ledgers.

The FastAPI application under `web/dividend_t_app.py` remains Legacy. It directly invokes `DividendTStrategy` and the Legacy risk engine, can fall back to static sample inputs and is not backed by the current Daily/Research/Decision/Risk/Position Readers.

`PaperBrokerAdapter` is a local placeholder. QMT and PTrade adapters explicitly reject live operations until vendor runtimes are integrated. No broker adapter is authorized.

The existing APScheduler factory belongs to the Legacy Dividend-T context and does not implement a recoverable ShadowRun.

## 6. Verification evidence

### 6.1 Historical checkpoint evidence

Repository delivery records report passing focused and full gates for earlier semantic checkpoints, including Phase 0–7 and H1–H3. Those records are useful commit-bound evidence.

### 6.2 Current checkpoint evidence

The local Python 3.12 verification on H6 hardened implementation checkpoint
`654e02556080d1476b399ee5145989be743f47a0` observed:

```text
FOCUSED_H6 = 67 passed, 0 skipped, 0 failed
H4_FOCUSED_REGRESSION = 42 passed, 0 skipped, 0 failed
H5_FOCUSED_REGRESSION = 101 passed, 0 skipped, 0 failed
RESEARCH_CONTEXT = 396 passed, 0 skipped, 0 failed
PLATFORM_CONTEXT = 23 passed, 0 skipped, 0 failed
POSITION_CONTEXT = 91 passed, 0 skipped, 0 failed
APPLICATION_CONTEXT = 114 passed, 0 skipped, 0 failed
FULL_PYTEST = 1459 passed, 0 skipped, 0 failed, 8 subtests passed
RUFF = PASS
MYPY_FORMAL_SCOPE = PASS, 263 source files
PACKAGE_BUILD = PASS, sdist and wheel
DOCUMENT_AUTHORITY_AND_LINKS = PASS
GIT_DIFF_CHECK = PASS
```

The full run emitted six existing pandas fragmentation warnings and no failures.
The CI workflow runs docs validation, pytest, Ruff, configured mypy and
`python -m build` on Python 3.12 for push and pull requests. Remote H6 CI is not
claimed until the Draft PR jobs complete; required-check branch protection was
not inspected.

## 7. Not implemented as production authority

- qualified operational Theme/Capital/PIT mapping evidence;
- production stock and ETF Universe snapshots;
- a validated Entry Model;
- validated Signal, PathForecast, Portfolio, Risk, Holding or Exit parameters;
- formal PIT and formal OOS Alpha evidence;
- sustained real 14:55 Shadow runs;
- H4.5 reducing-decision-to-manual-execution bridge;
- qualified real Composite Operational Evidence packages and producer identity;
- durable Holding/Exit schedules and acknowledgement state;
- recoverable ShadowRun queues, receipts, metrics, tracing and alerts;
- production authentication, authorization and operator signatures;
- external account/statement/Fill reconciliation;
- PostgreSQL operational deployment;
- QuantDesk production integration;
- broker execution and kill-switch architecture.

## 8. Operating boundary

Research outputs may support manual decisions. No current component may:

- send a live order;
- mutate a broker position;
- represent a manual Fill as broker truth;
- automatically promote a model;
- describe exploratory thresholds as validated parameters;
- describe CandidateSet or Signal as an Entry;
- treat a permitted H4 decision as an order, Fill or execution confirmation.

## 9. Immediate required sequence

```text
P0 engineering baseline restored
  H4 Repository/Application/exports/CLI integration complete
  → exact-commit pytest, Ruff, mypy, docs and package-build gates complete

P1 complete pre-Shadow mechanics
  H5 Artifact-derived Thesis Health complete
  → H6 Composite Evidence Manifest complete
  → H4.5 Risk-Reducing Decision to Manual Execution Bridge
  → H7 Durable Holding/Exit Operations
  → H8 Recoverable ShadowRun
  → H9 Validation Infrastructure

P1 establish qualified evidence
  controlled 14:55 runtime
  → operational Universe
  → PIT Theme/ETF mappings
  → Theme/Capital materialization
  → formal validation protocols

P2 production hardening
  PostgreSQL
  → authentication/RBAC
  → metrics/tracing/alerts
  → external reconciliation
  → operator workbench
  → separately approved broker architecture
```

## 10. Maturity statement

The repository is best classified as:

> **A pre-Shadow research decision platform with verified H4, H5 and H6 engineering checkpoints and strong evidence/manual-lifecycle mechanics, but without formal Alpha, sustained Shadow operations, production readiness or trading authority.**
