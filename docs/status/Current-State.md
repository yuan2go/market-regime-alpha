# Current State

> **Status:** CURRENT_STATUS  
> **Authority:** Single authoritative current implementation-state document  
> **Owner:** Market Regime Alpha maintainers  
> **Last Updated:** 2026-08-05
> **Supersedes:** ../constitution/implementation-status.md; ../research/R5-Current-Status.md; R5 task status documents as current authorities  
> **Superseded By:** None  
> **Related Documents:** Capability-Matrix.md, Gap-Register.md, External-Blockers.md, ../architecture/09-Platform-Architecture-V2.md, ../architecture/10-Production-Decision-Lifecycle.md, ../architecture/11-Production-Lifecycle-Hardening-and-Shadow-Operations.md, ../architecture/12-Canonical-Runtime-and-Legacy-Migration.md, ../architecture/13-Canonical-Market-Data-and-Feature-Spine.md, ../architecture/14-Canonical-Signal-Authority-and-Operational-Feature-Handoff.md, ../audit/WP-SIG-01A-Delivery.md, ../audit/H4-5-Risk-Reduction-Manual-Intent-Delivery.md, ../audit/H6-Composite-Operational-Evidence-Delivery.md, ../audit/H5-Thesis-Health-Delivery.md, ../audit/H4-Risk-Route-Delivery.md, ../audit/Production-Decision-Lifecycle-Delivery.md, ../audit/Production-Lifecycle-Hardening-Delivery.md, ../audit/Current-Main-Code-Audit-2026-08-01.md
> **Code Evidence:** Canonical Feature Spine implementation/gate checkpoint `4f099069cde5191e46d3c242dd46788947997f9c`; canonical runtime merge baseline `9ccc751`; H4.5 hardened implementation checkpoint `b1d6533a0b3b1bbd9e180c7f6864b3be8dbd2254`; H6 hardened implementation checkpoint `654e025b97c5d9553d7614b4b5be0898272aacbc`; H5 checkpoint `831edd6b2ae044d3bd1f3abcec97a30e47082071`; H4 checkpoint `3672067549e1b72a8bfd390f8320e2a7c55c599e`
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

The current engineering baseline contains substantial implementations across this chain, including immutable content-addressed artifacts, semantic Readers, recoverable PostgreSQL-default journals, append-only Fill evidence, complete-account Portfolio/Risk, Thesis-scoped Position books and Fill/calendar-derived A-share T+1 sellability. SQLite adapters remain available only through explicit compatibility/import selection.

The H6 implementation checkpoint extends the green H4/H5 baseline with an
explicit Composite Operational Evidence authority. It binds verified Daily and
Supplemental packages through a content-addressed policy, immutable terminal
manifest, append-only SQLite replay index and `ResearchInputBundleV2` labelled
`OPERATIONAL_EXPLORATORY_ARCHIVE`. It does not promote exploratory evidence,
run a new model, transition a Thesis, call H4, create a ManualTrade/Fill/Broker
Order or grant trading authority.

The H4.5 implementation checkpoint adds the reducing-risk-only bridge from a
current permitted H4 decision to a ManualTrade V3 SELL intent. One SQLite
`BEGIN IMMEDIATE` transaction reloads and replays Decision, H4, H5, H6 and
Execution authorities, rebuilds the latest H3 T+1 Position, reruns the H4 Gate
from fresh execution evidence and atomically records the immutable confirmation
attempt, route binding, intent and command. It creates no Fill, Broker Order,
Position mutation or trading authority.

The canonical-runtime development branch adds a 16-stage
`CanonicalDecisionLifecycleRunner` and a distinct migration-011 Lifecycle
Runtime Journal. The Runner stores typed references to existing domain
authorities and calls their Readers, Repositories and Application Services; it
does not copy their rules. A normal research run currently reaches verified
Research, Signal and PathForecast mechanics and then honestly stops at
`BLOCKED_BY_MODEL_VALIDATION` because Entry validation is absent. A separately
scoped H4 continuation verifies existing risk authorities and then waits for
external H4.5 human confirmation, an existing ManualTrade and a separately
human-recorded Fill.

The Canonical Feature Spine branch adds a content-addressed Market Data
authority, versioned Feature Set, seven Decimal technical-observable definitions,
deterministic materialization/Bundle/replay, per-family Legacy differential
evidence and five-factor Signal assembly. Canonical Signal now consumes actual
non-empty Feature values when evidence exists. PathForecast still has no
qualified sample provider and Entry remains safely blocked. These are research
mechanics, not validated predictive ability.

WP-SIG-01A converges new Signal production on a Decimal-only V3 authority. It
materializes the full controlled Universe before Candidate selection, projects a
reference-only Candidate Feature View, evaluates daily freshness by trading
session and intraday freshness by session plus elapsed time, and binds all
policies/calendar/configuration in Signal lineage. It also adds an immutable
Tencent raw-minute archive, explicit LOTS-to-SHARES conversion, recoverable
Feature runs and V2 selective physical encodings without changing logical
Artifact hashes. Signal V1/V2 remain historical compatibility authorities only.

## 2. Current stage

```text
RESEARCH_PLATFORM_KERNEL_IMPLEMENTED
IMMUTABLE_RESEARCH_EVIDENCE_IMPLEMENTED
EXPLORATORY_DAILY_LOOP_IMPLEMENTED
PLATFORM_V2_RESEARCH_LAYER_IMPLEMENTED_EXPLORATORY
PRODUCTION_DECISION_LIFECYCLE_PHASES_0_TO_7_ENGINEERING_COMPLETE_ON_PRIOR_CHECKPOINT
H1_COMPLETE_ACCOUNT_PORTFOLIO_RISK_POSTGRES_DEFAULT_SQLITE_COMPAT
H2_THESIS_TO_OUTCOME_TRACE_POSTGRES_DEFAULT_SQLITE_COMPAT
H3_FILL_CALENDAR_DERIVED_T_PLUS_ONE_IMPLEMENTED
H4_REDUCING_RISK_ROUTE_IMPLEMENTED_AND_VERIFIED
H4_IMPLEMENTATION_CHECKPOINT_ENGINEERING_GATE_VERIFIED
H4_5_RISK_REDUCTION_MANUAL_INTENT_IMPLEMENTED_AND_VERIFIED
H4_5_MANUAL_TRADE_V3_ROUTE_AUTHORITY_IMPLEMENTED
H4_5_IMPLEMENTATION_CHECKPOINT_ENGINEERING_GATE_VERIFIED
H5_ARTIFACT_DERIVED_THESIS_HEALTH_IMPLEMENTED_AND_VERIFIED
H5_V2_OPERATIONAL_ASSESSMENT_ADAPTER_IMPLEMENTED
H5_IMPLEMENTATION_CHECKPOINT_ENGINEERING_GATE_VERIFIED
H6_COMPOSITE_OPERATIONAL_EVIDENCE_IMPLEMENTED_AND_VERIFIED
H6_RESEARCH_INPUT_BUNDLE_V2_IMPLEMENTED
H6_IMPLEMENTATION_CHECKPOINT_ENGINEERING_GATE_VERIFIED
CANONICAL_LIFECYCLE_RUNTIME_IMPLEMENTED_ON_DEVELOPMENT_BRANCH
LIFECYCLE_RUNTIME_JOURNAL_MIGRATION_011_IMPLEMENTED_ON_DEVELOPMENT_BRANCH
CANONICAL_LEGACY_IMPORT_BOUNDARY_IMPLEMENTED_ON_DEVELOPMENT_BRANCH
ROLE_SPECIFIC_MODEL_MIGRATION_CONTRACTS_IMPLEMENTED_ON_DEVELOPMENT_BRANCH
SIMPLE_MOVING_AVERAGE_MIGRATION_EXAMPLE_IMPLEMENTED_ON_DEVELOPMENT_BRANCH
CANONICAL_RUNTIME_BRANCH_LOCAL_ENGINEERING_GATE_VERIFIED
UV_FROZEN_DEPENDENCY_LOCK_IMPLEMENTED_ON_FEATURE_BRANCH
CANONICAL_MARKET_DATA_AUTHORITY_IMPLEMENTED_ON_FEATURE_BRANCH
TECHNICAL_FEATURE_SPINE_IMPLEMENTED_ON_FEATURE_BRANCH
FEATURE_BUNDLE_AND_REPLAY_IMPLEMENTED_ON_FEATURE_BRANCH
CANONICAL_SIGNAL_FEATURE_INPUTS_IMPLEMENTED_ON_FEATURE_BRANCH
UNIVERSE_FEATURE_HANDOFF_AND_CANDIDATE_VIEW_IMPLEMENTED_ON_FEATURE_BRANCH
CANONICAL_DECIMAL_SIGNAL_V3_IMPLEMENTED_ON_FEATURE_BRANCH
TRADING_SESSION_SIGNAL_FRESHNESS_IMPLEMENTED_ON_FEATURE_BRANCH
IMMUTABLE_TENCENT_MINUTE_ARCHIVE_IMPLEMENTED_EXPLORATORY
FEATURE_MATERIALIZATION_RUN_AUTHORITY_POSTGRES_DEFAULT_SQLITE_COMPAT
FEATURE_AND_MARKET_DATA_ENCODING_V2_IMPLEMENTED_ON_FEATURE_BRANCH
ENTRY_REMAINS_BLOCKED_BY_MODEL_VALIDATION
SHADOW_READY_NOT_ESTABLISHED
FORMAL_PIT_NOT_ESTABLISHED
FORMAL_OOS_ALPHA_NOT_ESTABLISHED
TRADING_AUTHORITY_NOT_GRANTED
REAL_BROKER_AUTHORITY_NOT_IMPLEMENTED
PRODUCTION_READINESS_NOT_ESTABLISHED
OPERATOR_AUTHENTICATION_NOT_ESTABLISHED
POSTGRESQL_DEFAULT_RUNTIME_IMPLEMENTED_LOCAL_ENGINEERING_EVIDENCE
SQLITE_EXPLICIT_COMPATIBILITY_AND_IMPORT_ONLY
POSTGRESQL_SCHEMA_MIGRATIONS_001_TO_019_APPLIED_LOCAL
SQLITE_TO_POSTGRES_SCHEMA_ONLY_IMPORT_0_TO_0_VERIFIED
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

The loop is recoverable through a PostgreSQL-default Runtime Journal and can publish a verified `DATA_BLOCKED` artifact rather than silently continue with invalid inputs. The SQLite journal remains an explicit compatibility adapter.

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

The H4 CLI remains an assessment/persistence entry point only. H4.5 consumes a
separately reloaded and replayed permitted decision; H4 itself still creates no
ManualTrade, Fill or Broker Order.

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
`654e025b97c5d9553d7614b4b5be0898272aacbc`:

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

### 3.12 H4.5 reducing-risk manual intent bridge

H4.5 is **IMPLEMENTED_AND_VERIFIED** at
`b1d6533a0b3b1bbd9e180c7f6864b3be8dbd2254`:

- `ManualTradeRecord` V3 has mutually exclusive `INCREASING` and `REDUCING`
  authority routes while preserving V1/V2 Reader and hash semantics;
- increasing intent retains approved complete-account Portfolio/Risk,
  ProposedTradeDelta and post-trade snapshot requirements;
- reducing intent requires SELL plus exact H4 decision, immutable confirmation,
  source Position, book, Thesis, Opportunity, target and order quantity binding;
- `OperationalExitDirectiveV2`, `RiskReductionConfirmationPolicy` and
  `RiskReductionConfirmationAttempt` are content-addressed and fail closed;
- only the latest operational H5 V2 replay chain bound to an exact VERIFIED H6
  Composite manifest is accepted; synthetic, historical V1 and mismatched
  lineage are rejected;
- the unified SQLite repository owns migration 010 composition and uses one
  `BEGIN IMMEDIATE` transaction for authority reload, T+1 Position recheck,
  fresh Gate replay, attempt, ManualTrade, reducing binding and command;
- each H4 decision can create at most one confirmed intent; failures remain
  append-only attempts and do not create a trade;
- later manual partial/full SELL Fills flow through the existing append-only
  ledger and T+1 projector; a full EXIT Fill can support an explicit later book
  close, but H4.5 never records a Fill or closes a book itself;
- `scripts/confirm_risk_reduction.py` accepts IDs/hashes and explicit current
  evidence/configuration, not caller-supplied aggregate objects.

The actor remains an audit string, not an authenticated production identity.
Every successful result therefore retains `OPERATOR_AUTHENTICATION_NOT_ESTABLISHED`,
`TRADING_AUTHORITY_NOT_GRANTED`, `NO_FILL_CREATED` and
`NO_BROKER_ORDER_CREATED`.

### 3.13 Manual execution, Position and review

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

### 3.14 Canonical Lifecycle Runtime Journal

Implemented on the canonical-runtime development branch:

- one Runner with the exact ordered stages Evidence, Research, Signal,
  Forecast, Entry, Opportunity, Thesis, Portfolio/Risk, Risk Reduction, Manual
  Confirmation, ManualTrade, Fill/Position, Thesis Health, Holding, Exit and
  Outcome/Review;
- explicit `CANONICAL_DECISION_LIFECYCLE`,
  `RISK_REDUCTION_CONTINUATION` and source-bound durable `REPLAY` run types;
- immutable commands with deterministic run identity, typed object/config/model
  references and command-hash conflict rejection;
- migration 011 tables for run and stage projections, append-only attempts,
  immutable receipts and gap-free event history;
- `BEGIN IMMEDIATE` transactions, version compare-and-set and monotonic claim
  tokens for stale-writer rejection, plus one-snapshot read transactions for
  multi-query journal history;
- recover-before-execute behavior, explicit failure/resume, no overwrite of
  completed stages and no implicit retry on duplicate invocation;
- durable replay that creates an independent journal run, recomputes registered
  pure/model Artifacts, compares cross-run Receipt fingerprints and reloads
  ManualTrade read-only without invoking business handlers, H4.5 confirmation,
  Fill creation or a Broker; the exact source view is captured before journal
  mutation through a crash-atomic immutable publish, so interrupted replay
  remains recoverable after the source advances; Command V2 and LifecycleRun V1
  journal JSON remain readable after the replay linkage schema increment;
- structured module CLIs for start/resume/durable replay with stable exit
  codes and explicit `NO_ORDER_CREATED`, `BROKER_NOT_INVOKED`,
  `NO_FILL_CREATED` and admission-ceiling fields.

The Runner does not remove every operator boundary. H4.5 confirmation and Fill
recording remain external manual actions. Opportunity approval inputs,
complete-account Portfolio/Risk inputs and durable H7 assessment authorities
must be explicitly persisted; they are never synthesized to advance a run.

### 3.15 Canonical market data, Feature and Signal spine

Implemented on the Canonical Feature Spine branch:

- immutable Decimal OHLCV/amount Bars, explicit timeframes, PIT-safe adjustment
  policies and partitioned Market Data Dataset packages;
- versioned Feature definitions/configurations/Feature Set and explicit
  required/optional missingness;
- Price Action, SMA/EMA, MACD, Volume/Amount, real-minute VWAP and
  Overheat/Extension observable families;
- deterministic bounded-parallel Feature materialization, immutable Bundle,
  crash-safe receipt/report publication and true Dataset-to-Bundle replay;
- real Legacy MA/EMA/MACD/volume adapters isolated under `migration.legacy`,
  per-family comparison policy and fail-on-canonical-regression evidence;
- content-addressed five-factor mapping, per-factor value/source/freshness/
  missingness and Signal V2 replay through Feature reassembly;
- unchanged 16-stage graph, Signal receipt binding to FeatureBundle, durable
  Journal replay and explicit H9 Path sample-provider boundary.

All configurations remain `MODEL_ASSUMPTION`, `NOT_EMPIRICALLY_VALIDATED` and
`RESEARCH_ONLY`. VWAP requires real minute amount/volume and has no daily
fallback. Signal non-emptiness does not calibrate PathForecast or open Entry.

### 3.16 WP-SIG-01A authority convergence

Implemented on the WP-SIG-01A branch:

- full-Universe Feature materialization followed by Candidate subset projection;
- `CandidateFeatureView` binding Bundle, CandidateSet, Dataset, SourceManifest,
  DecisionTime and selected Feature references without copying Feature payloads;
- explicit all/declared/minimum factor policies, with the canonical five-factor
  model requiring all Factors and preserving precise missingness;
- Trading-Calendar-bound daily session lag and intraday same-session/elapsed
  freshness lineage;
- Decimal-only `CanonicalSignalModelV2` and `SignalRunArtifactV3`, while V1/V2
  Readers and replay remain immutable historical compatibility paths;
- V3-only canonical Signal stage and runtime configuration Readers; absent
  authority blocks instead of producing an empty-factor V1 artifact;
- exact-byte Tencent source/attempt archives, strict cumulative-counter
  handling, explicit volume conversion and versioned 1m→5m resampling;
- SQLite Run/Task/Attempt/Receipt/Event recovery for Feature materialization;
- V2 Market Data/Feature physical encoding and selective Readers with logical
  hash equality across V1/V2;
- durable replay that recomputes Dataset-derived Features, Candidate View,
  freshness and Decimal Signal before comparing receipts.

These mechanics remain exploratory. Path samples are unavailable, Entry is
blocked, and no Opportunity, ManualTrade, Fill, order or Broker action is added.

### 3.17 WP-DATA-OPS-01 controlled operation and archive

Implemented on the Controlled 14:55 operation branch:

- a versioned Calendar-bound DecisionTime policy and 100–300-symbol
  `OperationalUniverseArtifact`; admission binds the actual static-stage
  Receipt to the 14:50 deadline, and the 20-symbol DailyLoop pool remains Smoke;
- pre-decision static daily Feature materialization plus Candidate-only minute
  acquisition, intraday Feature overlay and `CandidateFeatureViewV2`;
- controlled Platform research without B0/B1, Signal V3, unavailable-sample
  PathForecast and an immutable Entry blocker;
- bounded Tencent per-symbol acquisition with deadline, finite retry, partial
  failure and complete coverage evidence;
- migrations 013/014/015 for Feature Run hardening, the parent operation
  journal and an append-only longitudinal index, including leases, monotonic
  fencing epochs, CAS and database triggers;
- immutable pending/settled operational packages, factual T+1 Outcome evidence,
  a raw Outcome Source Archive, a real migration-011 Canonical Lifecycle child
  run with exact history/Stage Receipt binding, full offline semantic replay and
  six JSON CLIs;
- read-only pre-cutoff crash admission bound to an already-persisted canonical
  command and frozen parent evidence, plus database-enforced prevention of
  `OUTCOME_PENDING` status regression on later idempotent reads;
- a 100-symbol cold Feature result of 57.986357 seconds against the 60-second
  engineering target, a 300-static/10-Candidate two-stage research measurement
  of 161.981241 seconds, and a 100-Universe/5-Candidate decision increment of
  0.147 seconds.

These are local engineering Fixtures. No operation in WP-DATA-OPS-01 was
observed at real wall-clock 14:55. Tencent remains exploratory, formal PIT and
OOS Alpha are not established, PathForecast has no Sample Authority, Entry is
blocked, and Shadow/Production/Trading Authority remain `NO`.

### 3.9 PostgreSQL free-data canonical composition

The current development branch adds `TENCENT_FREE_OPERATIONAL_V1` as an
explicit no-fallback profile and composes existing authorities rather than
creating another runtime. Both prepare/run CLIs currently fail closed before
14:55, while the composed Daily source freeze groups History, Status and quote
and the Controlled static deadline remains 14:50. A safe two-phase operating
schedule therefore remains incomplete. When invoked with admissible recorded
timing, the same request owns a PostgreSQL Controlled parent, Feature run and,
when Candidate inputs are complete, a PostgreSQL Canonical child.

New source writes retain raw BaoStock/Tencent bytes with request, timing,
content, scope, encoding, byte-count and hash metadata. The preparation layer
materializes exact 20/100/300 Operational Universes including excluded symbols,
explicit provider-derived sessions, canonical daily bars and static Features.
Missing theme membership, ETF mapping or capital observations are typed missing
evidence; they are never replaced by neutral constants. A post-freeze
normalization error publishes a content-addressed `FreeDataBlockedArtifact`.

Recorded 20/100/300 replay and real PostgreSQL integration prove deterministic
identities, single acquisition/materialization and no SQLite file write. A real
20-symbol network attempt after the 2026-08-05 decision window froze BaoStock
history/status, Tencent quote and the SourceManifest, then correctly blocked
with `DATA_AVAILABLE_AFTER_DECISION_TIME`. This is live source evidence, not a
successful controlled 14:55 run.

## 4. Persistence, transactions and consistency

PostgreSQL is now the default authority selected through
`MARKET_REGIME_ALPHA_DATABASE_URL`; SQLite requires an explicit compatibility
path. All current SQLite-backed bounded contexts have PostgreSQL adapters behind
the same Repository protocols, including Governance, Decision, Portfolio/Risk,
Manual Execution, Daily, Feature, Canonical Lifecycle, Controlled Operation and
Longitudinal state. Runtime composition neither dual-writes nor falls back.

PostgreSQL migration versions 001–019 are checksummed, contiguous and serialized
with an advisory lock. The approved local PostgreSQL 16.14 schema contains 59
catalog tables. The initial import manifest discovered no SQLite business source
and produced a verified schema-only `0 -> 0` report at code checkpoint
`7366ab326c2333d4f6eaefbe0a443b588d0e15b1`. This does not claim migration of
DuckDB, Parquet, CSV, external files or undiscovered SQLite data.

The retained explicit SQLite repositories generally use:

- `BEGIN IMMEDIATE` transactions;
- `busy_timeout`;
- command idempotency key plus command hash;
- optimistic version compare-and-swap;
- append-only event tables;
- rollback on failure;
- restore by replaying and validating history;
- recomputation of Risk before accepting caller-supplied decisions.

PostgreSQL adapters preserve idempotency, command hashes, compare-and-swap,
fencing, append-only events, immutable identities, reconstruction and replay.
Migration 017 records credential-free runtime backend/database/schema bindings;
Migration 018 admits `DAILY_LOOP` and `FREE_DATA_OPERATION` binding scopes;
Migration 019 records append-only free-data Blocked Artifact references;
resume/replay rejects a missing or mismatched PostgreSQL binding.

This is local PostgreSQL engineering evidence. It is not multi-instance or
distributed production authority.

Not implemented:

- distributed leases and multi-instance ownership;
- cross-database or file/database transactions;
- outbox/message delivery guarantees;
- multi-instance or sustained scheduled Shadow operations.

## 5. Frontend, scheduler and broker boundary

The current canonical lifecycle is CLI/Application-Service driven. There is no production UI consuming verified Artifacts and ledgers.

The FastAPI application under `web/dividend_t_app.py` remains Legacy. It directly invokes `DividendTStrategy` and the Legacy risk engine, can fall back to static sample inputs and is not backed by the current Daily/Research/Decision/Risk/Position Readers.

`PaperBrokerAdapter` is a local placeholder. QMT and PTrade adapters explicitly reject live operations until vendor runtimes are integrated. No broker adapter is authorized.

The existing APScheduler factory belongs to the Legacy Dividend-T context and does not implement a recoverable ShadowRun.

## 6. Verification evidence

### 6.1 Historical checkpoint evidence

Repository delivery records report passing focused and full gates for earlier semantic checkpoints, including Phase 0–7 and H1–H3. Those records are useful commit-bound evidence.

### 6.2 Current checkpoint evidence

The local Python 3.12 verification on H4.5 hardened implementation checkpoint
`b1d6533a0b3b1bbd9e180c7f6864b3be8dbd2254` observed:

```text
FOCUSED_H4_5 = 81 passed, 0 skipped, 0 failed
EXECUTION_CONTEXT = 97 passed, 0 skipped, 0 failed
PORTFOLIO_CONTEXT = 55 passed, 0 skipped, 0 failed
POSITION_CONTEXT = 91 passed, 0 skipped, 0 failed
APPLICATION_CONTEXT = 114 passed, 0 skipped, 0 failed
H4_FOCUSED_REGRESSION = 42 passed, 0 skipped, 0 failed
H5_FOCUSED_REGRESSION = 101 passed, 0 skipped, 0 failed
H6_FOCUSED_REGRESSION = 67 passed, 0 skipped, 0 failed
FULL_PYTEST = 1541 passed, 0 skipped, 0 failed, 8 subtests passed
RUFF = PASS
MYPY_FORMAL_SCOPE = PASS, 266 source files
PACKAGE_BUILD = PASS, sdist and wheel
DOCUMENT_AUTHORITY_AND_LINKS = PASS
GIT_DIFF_CHECK = PASS
```

The full run emitted six existing pandas fragmentation warnings and no failures.
The CI workflow runs docs validation, pytest, Ruff, configured mypy and
`python -m build` on Python 3.12 for push and pull requests. Remote H4.5 CI is
not claimed until the Draft PR jobs complete; required-check branch protection
was not inspected.

### 6.3 Canonical-runtime development branch verification

Focused tests exist for state transitions, command idempotency/hash conflict,
migration-011 schema integrity, attempts/receipts/history, failure recovery,
research/Entry blocking, H4 continuation observation, manual confirmation,
ManualTrade/Fill boundaries, Legacy imports, role-specific contracts,
differential classification and Feature replay.

The final branch-wide commands were observed locally on the canonical-runtime
development branch:

```text
python scripts/check_docs_links.py = PASS
python -m pytest -q tests/scripts/test_check_docs_links.py = 8 passed
python -m pytest -q tests/platform = 23 passed
python -m pytest -q = PASS, 1967 tests collected, 6 existing pandas PerformanceWarnings
python -m ruff check . = PASS
python -m mypy = PASS, 298 source files
python -m build = PASS, sdist and wheel built
```

These are local engineering checks, not remote CI, sustained Shadow evidence,
formal model validation, Broker authority or production admission.

### 6.4 Canonical Feature Spine verification

At implementation/gate checkpoint `4f099069cde5191e46d3c242dd46788947997f9c`, the
frozen Python 3.12 environment observed:

```text
FROZEN_UV_SYNC_DEFAULT_DEV_POSTGRES = PASS
FEATURE_FOCUSED = 490 passed, 0 skipped, 0 failed
H4_H5_REGRESSION = 143 passed, 0 skipped, 0 failed
FULL_PYTEST = 2059 passed, 0 skipped, 0 failed
RUFF = PASS
MYPY_FORMAL_SCOPE = PASS, 319 source files
PACKAGE_BUILD = PASS, sdist and wheel
DOCUMENT_AUTHORITY_AND_LINKS = PASS
DOCS_TESTS = 8 passed, 0 skipped, 0 failed
GIT_DIFF_CHECK = PASS
```

The full run retained six existing pandas fragmentation warnings. The 100-symbol
offline performance fixture measured a 29.502912-second cold Feature run and an
8.359181-second cached verification; this is engineering performance evidence,
not Alpha or production admission. Remote CI is not claimed until pushed checks
complete.

### 6.5 WP-SIG-01A branch verification

The pre-commit branch passed the 44 Market Data, 78 Feature, 21 Signal, 353
Canonical Lifecycle and five Architecture focused collections plus all 2082
tests. Ruff, mypy over 328 source files, package build, frozen dependency sync,
documentation authority/links and diff hygiene passed. The same-fixture
100-symbol benchmark reduced package bytes by 85.8937% and selective-read time
by 99.7085%, with identical Feature Bundle and Signal Artifact hashes. Exact
measurements and the retained evidence ceiling are recorded in
`../audit/WP-SIG-01A-Delivery.md`. Remote CI is reported externally after push;
this status does not pre-claim it.

### 6.6 PostgreSQL authority cutover verification

The pre-final cutover worktree based on migration checkpoint
`7366ab326c2333d4f6eaefbe0a443b588d0e15b1` observed PostgreSQL 16.14 with
17/17 migrations, 58 catalog tables, no non-empty business/runtime table, a
verified external custom-format backup and immutable schema-only import report
`sha256:0a6091e24ab31b20146971576a3636b5734f08b1eb9b44aaa014814c3f1fc59b`.
PostgreSQL isolated-schema smoke suites and the full 2234-test collection passed;
frozen sync, documentation checks, Ruff, mypy over 338 source files and sdist/
wheel build also passed. The checkpoint commit requires its own exact-HEAD
rerun. Remote CI and production admission are not claimed.

## 7. Not implemented as production authority

- qualified operational Theme/Capital/PIT mapping evidence;
- production stock and ETF Universe snapshots;
- a validated Entry Model;
- validated Signal, PathForecast, Portfolio, Risk, Holding or Exit parameters;
- formal PIT and formal OOS Alpha evidence;
- sustained real 14:55 Shadow runs;
- qualified real Composite Operational Evidence packages and producer identity;
- durable Holding/Exit schedules and acknowledgement state;
- sustained scheduled Shadow operations, operator deadlines/acknowledgements,
  metrics, tracing and alerts;
- production authentication, authorization and operator signatures;
- external account/statement/Fill reconciliation;
- production-qualified PostgreSQL deployment and restore drill;
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
- treat a permitted H4 decision by itself as an order, Fill or execution
  confirmation;
- treat an H4.5 ManualTrade intent as a Fill, Broker Order or trading authority.

## 9. Immediate required sequence

```text
P0 engineering baseline restored
  H4 Repository/Application/exports/CLI integration complete
  → exact-commit pytest, Ruff, mypy, docs and package-build gates complete

Canonical Feature input preparation
  frozen uv environment
  → Canonical Market Data Dataset
  → Universe Feature materialization and Bundle
  → Candidate Feature View
  → Decimal Signal V3 with policy/calendar lineage
  → Path remains uncalibrated and Entry remains blocked

P1 complete pre-Shadow mechanics
  H5 Artifact-derived Thesis Health complete
  → H6 Composite Evidence Manifest complete
  → H4.5 Risk-Reducing Decision to Manual Execution Bridge complete
  → H7 Durable Holding/Exit Operations
  → H8 sustained Shadow operations and control plane
  → H9 Validation Infrastructure

P1 establish qualified evidence
  controlled 14:55 runtime
  → operational Universe
  → PIT Theme/ETF mappings
  → Theme/Capital materialization
  → formal validation protocols

P2 production hardening
  local PostgreSQL parity/cutover delivered
  → production restore/operations qualification
  → authentication/RBAC
  → metrics/tracing/alerts
  → external reconciliation
  → operator workbench
  → separately approved broker architecture
```

## 10. Maturity statement

The repository is best classified as:

> **A pre-Shadow research decision platform with PostgreSQL-default local persistence and verified H4, H4.5, H5 and H6 engineering checkpoints plus a canonical lifecycle/migration foundation, but without formal Alpha, sustained Shadow operations, production readiness or trading authority.**

The canonical-runtime branch does not change these admission facts:

```text
automatic_order_execution = false
broker_integration_proven = false
entry_model_empirically_validated = false
production_ready = false
```
