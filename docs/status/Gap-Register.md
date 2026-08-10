# Gap Register

> **Status:** CURRENT_STATUS  
> **Authority:** Ordered gap and dependency register  
> **Owner:** Market Regime Alpha maintainers  
> **Last Updated:** 2026-08-10
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** Current-State.md, Capability-Matrix.md, ../architecture/13-Canonical-Market-Data-and-Feature-Spine.md, ../architecture/14-Canonical-Signal-Authority-and-Operational-Feature-Handoff.md, ../architecture/16-Phase-A-Correctness-and-Research-Shadow-Operations.md, ../audit/Phase-A-Correctness-Shadow-Operations-Delivery.md, ../audit/WP-SIG-01A-Delivery.md, ../audit/H4-5-Risk-Reduction-Manual-Intent-Delivery.md, ../audit/H6-Composite-Operational-Evidence-Delivery.md, ../audit/H5-Thesis-Health-Delivery.md, ../audit/H4-Risk-Route-Delivery.md, ../audit/Current-Main-Code-Audit-2026-08-01.md, ../roadmap/work-packages/WP-PDL-Hardening-and-Shadow-Readiness.md, ../architecture/11-Production-Lifecycle-Hardening-and-Shadow-Operations.md, ../architecture/12-Canonical-Runtime-and-Legacy-Migration.md
> **Code Evidence:** Canonical Feature Spine checkpoint `4f099069cde5191e46d3c242dd46788947997f9c`; canonical runtime merge baseline `9ccc751`; H4.5 checkpoint `b1d6533a0b3b1bbd9e180c7f6864b3be8dbd2254`; H6 checkpoint `654e025b97c5d9553d7614b4b5be0898272aacbc`
> **Ordering Rule:** Fix current-baseline correctness before adding capabilities. Engineering mechanics, operating evidence, model validation and production admission are separate exit conditions.

## 1. Immediate P0 gaps

| Gap | Priority | Current state | Dependency | Exit condition |
|---|---|---|---|---|
| Reproducible dependency set | DELIVERED_FEATURE_BRANCH | `uv.lock` covers default, dev and postgres dependency groups; setuptools remains the build backend | Final frozen-sync gate and remote CI | `uv sync --frozen --extra dev --extra postgres` and all frozen-environment gates remain green |
| CI enforcement | P1 | Workflow covers Python 3.12 install, docs, pytest, Ruff, configured mypy and package build on push/PR; both remote branch and Draft PR jobs passed at `dfd7a0b`, while required-check policy was not inspected | Repository settings authority | Protected branches require the complete workflow and preserve passing push/PR checks |

## 2. Pre-Shadow hardening gaps

| Gap | Priority | Current state | Dependency | Exit condition |
|---|---|---|---|---|
| Qualified H6 operational packages | P1-EVIDENCE | H6 mechanics now preserve both manifests, per-field authority and DecisionTime without eligibility inflation, but current tests use synthetic/exploratory fixtures | Controlled Daily/Supplemental producers and authenticated runtime | Consecutive real packages pass H6 verification with qualified availability, lineage and producer evidence; no formal-PIT inflation |
| H7 durable Holding/Exit operations | P1 | The H5 V2 adapter can compute one-shot Holding/Exit assessments, but there is no append-only schedule, blocked state, acknowledgement or durable projection | Delivered H5 health plus H6 evidence and H4.5 bridge | Repository supports CAS, idempotency, restart, rebuild, due/blocked/acknowledged state and migration isolation |
| H5 canonical Decision input authority | P1 | `build_thesis_health.py` loads canonical Thesis/Opportunity JSON supplied by the caller rather than the current aggregate version from `DecisionLifecycleRepository` | H7 operational command authority | H7 loads current Thesis/Opportunity by ID/version from Decision authority and rejects stale or caller-substituted aggregate files |
| H5 assessment freshness/scheduling | P1 | The V2 adapter requires Health `assessed_at` to equal assessment time and has no durable schedule, Position maximum age or retry semantics | H7 durable lifecycle | Versioned freshness policy, due time, retry/reassessment and Position age are persisted and replayable |
| H5 module decomposition | P2 | `position/thesis_health.py` is a large aggregate module; behavior is tested but navigation and change isolation are weak | Separate behavior-preserving refactor package | Rules, bundle/observation and Builder seams are split without schema/hash/public-API drift and all H5/H6 regressions pass |
| H6 Builder module decomposition | P2 | `composite_manifest.py` deliberately centralizes H6 domain validation for the first delivery and is now large | Separate behavior-preserving refactor package after H6 evidence stabilizes | Policy/manifest/value objects and Builder relationship validators are split without schema/hash/status/public-API drift |
| H7 reducing-risk assessment lifecycle | P1 | H4.5 adds `OperationalExitDirectiveV2` with explicit reducing authority, but Legacy `ExitAssessment` keeps its historical Portfolio/Risk wording and there is no durable H7 producer/acknowledgement flow | H7 durable lifecycle | Durable REDUCE/EXIT assessments produce and track H4/H4.5 references while OPEN/ADD retain complete-account Risk authority, without creating Broker authority |
| H7 T+1 projection integration | P1 | Historical `LifecycleReviewApplicationService` uses base `PositionProjector.project()` instead of the H3 `project_book_t_plus_one()` authority path | H7 durable review redesign | V2 durable review consumes an H3 PositionSnapshot with calendar/session evidence and never reconstructs weaker sellability |
| H4_V2_REDUCE_REQUIRES_POSITIVE_REMAINDER | P2 | H4 V1 still permits `REDUCE target_quantity=0`; H4.5 preserves replay but rejects confirmation with `ACTION_SEMANTICS_CONFLICT` and `REQUIRES_NEW_EXIT_DECISION` | Explicit H4 V2 schema/semantic migration | H4 V2 enforces `0 < target_quantity < current_quantity` for REDUCE and `target_quantity=0` for EXIT while V1 replay remains immutable |
| H4.5 operator authentication | P1 | Confirmation policy and attempts explicitly emit `OPERATOR_AUTHENTICATION_NOT_ESTABLISHED`; actor is audit text only | Authentication/RBAC design | Confirmation binds an authenticated principal/role and verifiable audit identity without rewriting historical attempts |
| Manual invalidation authentication | P1 | H5 ManualInvalidationEvidence binds actor/reason/time and content identity but actor authentication is not established | Authentication/RBAC design | Evidence carries authenticated principal/role and verifiable audit identity without changing historical V1/V2 content |
| H8 sustained Shadow operations | P1-EXTERNAL | the Research Shadow operating loop now provides CLI/Application schedule, Runtime attach, policy-bound freeze, pending, multi-target settlement, attestation, complete Panel V2, report/replay/resume/invalidate and no-trade mutation guards. Recorded data proves only engineering mechanics; no decision/outcome pair is prospective | exact-window live operation, authenticated scheduler/operator acknowledgement, incidents/alerts and consecutive sessions | scheduled real Shadow operation proves consecutive frozen T decisions, later real T+1 outcomes, recovery drills and replay without changing authority ceilings |
| Continuous Runtime production operation | P1-EVIDENCE | The single Continuous owner now executes staged BaoStock/Tencent `run-due`, the real State chain, pre-Decision minute acquisition, mode-specific selection, typed Summary, material reuse and recovery on PostgreSQL with recorded providers | exact-window live rehearsal, operational supplemental producer, authenticated scheduler and operating environment | consecutive bounded real-data runs recover from drills, preserve last-valid Evidence and never raise Entry/Broker authority |
| Daily Decision operating evidence | P1-EVIDENCE | Strict Production account decisions remain separate; Summary V3 binds real State Receipt/CandidateSet, actual consumed Provider sources/attempts, typed outcomes/timestamps, verified model receipts, fencing and replay | exact-window Provider evidence and sustained scheduler | consecutive prospective summaries and T+1 outcomes replay without Position mutation, authority inflation or stale-fence writes |
| H9 Signal/Path validation infrastructure | P1 | Signal and PathForecast mechanics exist with explicit assumptions, but no formal incremental-value, calibration or locked OOS infrastructure | Qualified historical data and H8 artifact production | Purged walk-forward, embargo, controls, calibration, sensitivity and frozen OOS protocols pass leakage checks |
| Runtime governance integration | DELIVERED_WP_GOV_01_LOCAL_ENGINEERING_GATE | PostgreSQL Registry owns version lineage, evidence, policy, assignments and immutable receipts; the free-data path selects Market Regime, Theme, Capital, Candidate, Signal and Forecast by `RESEARCH`/`SHADOW`/`PRODUCTION_DECISION`; caller qualification is ignored | formal Production qualification evidence is intentionally external | seed explicit Research/Shadow assignments for rehearsal and add PIT/OOS/economic/cost/Shadow evidence only through qualification actions |
| Formal PIT Data Authority | DELIVERED_WP_PIT_01_ENGINEERING_AUTHORITY | Migration 028 owns strict Reader/persisted-receipt resolution, contextual kind/dependency checks, Provider/contract/use/fact-kind policy, PostgreSQL-clock prospective and typed historical modes, repeatable-read validation, role-bound explicit Fact-set projection replay and the guarded existing-governance bridge; no global PIT revision write lock remains | Real qualified Provider evidence/archive, canonical Eligibility and Validation Protocol Readers, complete ETF/Theme/ST/suspension/listing/corporate-action history and independent validation remain external | A real Provider archive is policy-qualified, all required canonical Artifacts and facts resolve without leakage, and explicit-set replay enters Model Governance without automatic qualification |
| Feature package storage efficiency | DELIVERED_WP_SIG_01A_LOCAL_BENCHMARK_PASS | Encoding V2 separates logical hashes from compressed/columnar physical files, shares definition/configuration data and supports selective read; the required 100-symbol fixture reduced bytes by 85.8937% and selective read time by 99.7085% with stable Bundle/Signal hashes | Sustained operational profiling | Observe real Shadow-scale packages without changing logical identities or V1 compatibility |
| PostgreSQL Authority Only | DELIVERED_LOCAL_ENGINEERING_EVIDENCE | Native bounded PostgreSQL repositories, migrations 001–042, isolated-schema integration/re-execution replay and fail-closed settings are implemented; the executable file-database backend and bridge are removed | exact-SHA CI PostgreSQL service and production operations qualification | Preserve native PostgreSQL gates in CI; production admission remains separate |

## 3. Data and operational evidence gaps

| Gap | Priority | Current state | Dependency | Exit condition |
|---|---|---|---|---|
| Controlled 14:55 public runtime | P0-EXTERNAL | Complete controlled runner/package/outcome/index/replay mechanics pass a 100-Universe/5-Candidate offline Fixture; no real 14:55 operation was observed | Controlled scheduling and Provider availability | Sustained real exact-window archives reach `OUTCOME_PENDING`, settle and replay with stable hashes |
| Free-data on-window operation | P0-EXTERNAL | recorded-provider PostgreSQL E2E reaches non-empty Stateful `RESEARCH_CANDIDATE` in RESEARCH/SHADOW through the operational free producer; the latest real BaoStock/Tencent attempt was after-window and correctly blocked | trading-day scheduling and Provider availability | Exact-SHA 14:30/14:54/14:55 staged operation publishes and replays a non-empty Summary without late data or fallback |
| Free-data staged acquisition | DELIVERED_ENGINEERING_LIVE_UNOBSERVED | one `run-due` entry freezes BaoStock history/status, admits the semantic 14:55 Tick at or after 14:54, freezes the Tencent quote, runs bounded Candidate minute acquisition and does not finalize Summary before DecisionTime; recorded tests prove crash/restart reuse without duplicate Provider calls | exact-window Provider rehearsal | real staged run preserves request/response/deadline and stage completion times and reaches Summary idempotently |
| Free-data query facade | DELIVERED_ENGINEERING | `inspect-run/tick/provider/evidence/state/pool/candidate/minute/model-selection/summary`, trace and metrics reconstruct the Canonical DAG from existing Authority owners without recomputation | live operator rehearsal and long-running retention | every blocked/partial/recovered live Tick remains explainable from the same read-only projections |
| Qualified minute-source authority | P0-EXTERNAL | Tencent exact-byte archive/normalizer/resampler is implemented but explicitly `EXPLORATORY`; recorded fixtures prove engineering replay only | Controlled DecisionTime acquisition and qualified formal Provider | Repeated real archives establish availability, units, coverage and PIT limits without promoting Tencent cache rows |
| Qualified Xuntou V4 input | P0-EXTERNAL | Adapter/preflight/evidence contracts exist; no qualified real XtQuant bundle has passed | Windows XtQuant exporter and source inventory | Real bundle passes qualification and same-pipeline comparison without authority promotion |
| Qualified PIT Operational stock Universe | P1-EXTERNAL | Versioned 100–300-symbol exploratory artifact is implemented; the fixed 20-symbol pool is isolated to Smoke compatibility | Approved effective-dated PIT membership/liquidity/status source | Repeated qualified Universes account for every inclusion/exclusion with availability evidence and `PIT_CORRECT_FOR_DECLARED_SCOPE` |
| Canonical ETF Universe | P1-EXTERNAL | an append-only exploratory Reference authority now identifies `510300.SH`, `000300.SH`, effective/availability time, liquidity policy seam and the bounded proxy mapping. It deliberately contains no invented stock membership and is not comprehensive or Formal PIT | qualified ETF identity/listing/liquidity data and effective-dated Theme membership source | expanded immutable ETF Universe and membership records replay with authoritative source lineage and delisting/duplication rules |
| PIT theme membership | P1 | Bridge requires full membership coverage, but no qualified daily producer exists | Theme taxonomy and effective-dated source | Every symbol’s primary/supporting membership is available by DecisionTime and versioned |
| Theme/ETF mapping | P1 | the V1 current-operational-Universe proxy mapping is effective-dated, content-addressed and bound to actual source lineage; it explicitly is not qualified PIT taxonomy or index membership | qualified Theme taxonomy and historical membership source | Every proxy mapping has qualified effective time, source lineage and deterministic Reader |
| Theme and Capital observations | P1-VALIDATION | the free operational producer materializes observable breadth/participation, amount/persistence, concentration and diffusion proxies with coverage/missingness into the real lifecycle State mechanics; it is recorded-source engineering evidence only | repeated live operation and later qualified historical inputs | Daily live materialization remains stable and later ablation establishes incremental value without hidden-intent or causal claims |
| Free-data supplemental producer | DELIVERED_ENGINEERING_LIVE_UNOBSERVED | the same Daily journal freezes exact BaoStock ETF bytes and current-only policy bytes, then the bounded producer drives real ETF/Theme/Capital State and non-empty Pool/Candidate in PostgreSQL; outage/partial/late evidence never falls back | exact-window trading-day Provider access | repeated live immutable supplemental evidence passes availability/lineage/recovery checks without claiming Formal PIT or institutional intent |
| External account authority | P1 | H1 snapshots and H3 positions are based on explicit/manual evidence | Broker statement/import boundary | Complete cash/position statement is authenticated, versioned and reconciled before Risk |
| Fill reconciliation | P1 | Fill is append-only human-recorded evidence, not broker truth | External execution statement and operator roles | Every manual Fill is matched, disputed or corrected through an append-only reconciliation workflow |

## 4. Research and model gaps

| Gap | Priority | Current state | Dependency | Exit condition |
|---|---|---|---|---|
| Real Entry Model | P1 | Canonical Entry emits only `REJECT` or `WAIT_CONFIRMATION`; `ENTER` is intentionally absent | Qualified Candidate/Signal/path evidence and validation protocol | Independent Entry model has frozen inputs, thresholds, target, cost assumptions, calibration and OOS result |
| Entry authority namespace convergence | DELIVERED_ENGINEERING_BOUNDARY | Canonical `daily_decision` Entry cannot emit `ENTER`; `daily_research.EntryState` is explicitly historical compatibility, and machine-readable plus AST guards prevent Legacy executable imports in Canonical composition | preserve compatibility tests while Legacy Readers remain | no current Runtime/Decision/Shadow writer imports or accepts the Legacy ENTER authority |
| Market Regime validation | P1 | Deterministic weighted gate with explicit thresholds | Qualified historical observations | Walk-forward comparison proves usefulness for exposure/gating versus simpler controls |
| Theme lifecycle validation | P1-VALIDATION | WP-STATE-01 implements an independent versioned state machine with persistence, duration, confirmation, hysteresis, missing mapping and conflict evidence | PIT mapping/history and locked transition protocol | Walk-forward evidence validates decay behavior and incremental value without current-membership backfill |
| Dynamic Stock Pool validation | P1-VALIDATION | Immutable versioned Pool, full cross section, material reuse, CAS/fencing and Candidate binding are implemented with engineering fixtures | qualified State, Eligibility and PIT Theme/ETF evidence | frozen comparison establishes stability, turnover and incremental value without opening Entry authority |
| Capital Evolution validation | P1 | Observable-proxy inference exists | Theme/ETF/symbol historical observations | Ablation and incremental-value tests show what the inferred score contributes beyond price/volume baselines |
| Candidate incremental value | P1 | Market/Theme/Capital gates feed Candidate Discovery over B0/B1 factors | Qualified historical archive | Frozen comparison reports hit rate, return, drawdown, turnover and overlap versus B0/B1 controls |
| PathForecast calibration | P1 | MFE/MAE, barriers and quantiles exist without validated profile or event probability | H9 and qualified samples | Horizon/barrier profile is selected only from training data and evaluated on locked OOS |
| Risk parameter validation | P1 | Risk constraints are explicit engineering fixtures | Shadow account/position/outcome sample | Limits are approved through a versioned protocol with sensitivity and incident review |
| Holding/Exit parameter validation | P1 | Actions and contracts exist with synthetic profiles | H5/H7/H8 and closed shadow trades | Frozen configurations are evaluated by regime/theme/liquidity slices without causal overclaim |
| WP-MIG-01B Remaining Technical Observable Migration | P1 | MA/EMA, MACD and comparable Volume structure are now canonical observables with isolated Legacy differential evidence | Qualified normalized datasets and model-specific policies | Force Ratio, Chan Features and Tuishen Volume-Price Features each have pure canonical Features, isolated adapters, explicit differences, verified Readers and replay evidence |
| Formal PIT/OOS Alpha | P0-RESEARCH | No model has current formal winning evidence | Qualified data, H9 and locked protocol | Formal study publishes immutable protocol, access history, results and negative outcomes; no data reuse violation |

WP-MIG-01 must remain observable-first. Its explicit backlog is:

- Force Ratio;
- Chan Features;
- Tuishen Volume-Price Features.

It does not authorize migration of complete buy/sell points, risk, position
sizing, COSCO strategy behavior or any Legacy Broker path.

## 5. Product, security and operations gaps

| Gap | Priority | Current state | Dependency | Exit condition |
|---|---|---|---|---|
| Authentication and RBAC | P1 | Domain `actor` is a string, not an authenticated principal | Operator/API architecture | Roles govern approval, risk, Fill, reconciliation, model transition and incident actions |
| Artifact signatures | P2 | SHA-256 proves content consistency but not trusted producer identity | Key management and authenticated runtime | Artifacts carry verifiable producer/operator signatures and rotation/revocation rules |
| Metrics, tracing and alerts | P1-OPERATIONS | read-only Runtime/Shadow DAG and metrics derive owner-backed Candidate counts and available coverage; unavailable replay/fence/coverage measurements are `NOT_OBSERVED`, not zero. No external exporter, threshold history or alert routing exists | exact-window and sustained Shadow operation | observed operating distributions define versioned thresholds and actionable alerts without entering decisions |
| Backup and recovery | P1-OPERATIONS | local real PostgreSQL custom-format backup, isolated database restore, schema/Table fingerprint verification, Continuous replay and immutable Artifact hash comparison pass; this is not production PITR/SLA evidence | Production PostgreSQL/filesystem deployment, retention and encryption policy | repeated environment restore/PITR drills meet documented RPO/RTO and reconcile all configured Artifact locators |
| Prospective Outcome sample | P0-EXTERNAL | Summary-scoped T+1/multi-target Outcome, complete Evaluation Panel V2 and Prospective Evidence Attestation are implemented and replayable with recorded data; the database-enforced current attestation schema always has `prospective_proven=false` and sample size remains zero | exact-window frozen Shadow Decisions followed by later real checkpoint acquisition and separately approved trusted-runtime attestation policy | nonzero consecutive samples bind trusted clock/source receipts and satisfy `decision_frozen_at < outcome_available_at` without fixture/replay substitution |
| QuantDesk read model | P2 | Canonical lifecycle is CLI-driven; Legacy FastAPI is not Reader-backed | Stable H8 commands/queries | UI reads verified artifacts and durable projections without recomputing decisions |
| Legacy Dashboard isolation | P1 | `web/dividend_t_app.py` can use static fallback and Legacy strategy/risk paths | QuantDesk replacement or explicit isolation | Legacy endpoint is local-only/clearly labelled and cannot be confused with canonical authority |
| Broker adapter architecture | DEFERRED | QMT/PTrade adapters safely reject live operations | Sustained shadow evidence, security review and separate approval | Versioned intent port, external receipts, reconciliation, permissions and kill switch pass dedicated admission |

## 6. Delivered engineering mechanics retained

The following are not open implementation gaps, although their operating/model evidence remains limited:

- immutable content-addressed artifacts and semantic Readers;
- SourceManifest and fail-closed DataQuality;
- B0/B1 PredictionRuns and candidate baselines;
- PostgreSQL Model Registry, explicit qualification, Runtime Selector,
  Champion/Challenger assignment and immutable selection replay;
- recoverable exploratory DailyLoop;
- Market/Theme/Capital/Candidate research mechanics;
- Signal and uncalibrated PathForecast mechanics;
- PostgreSQL-only Opportunity/Thesis lifecycle;
- H1 complete-account Portfolio/Risk;
- H2 Thesis-scoped authority trace;
- H3 Fill/calendar-derived T+1 Position;
- H4 reducing-risk domain, PostgreSQL-only persistence, idempotency, strict restoration and decision-only CLI;
- H4.5 ManualTrade V3 route authority, immutable Directive/Policy/Attempt,
  migration 010, unified atomic confirmation, H5/H6 lineage validation,
  T+1/Gate recheck, reducing Fill compatibility and reference-only CLI;
- H5 typed invalidation rules, verified current-evidence Builder, V2 Observation, migration 008, PostgreSQL replay, V2-only CLI and thin operational assessment adapter;
- H6 typed composition policy/manifest, exact immutable package, migration 009, append-only PostgreSQL replay index, V2-only operational research route and H5 integration;
- canonical 16-stage Runner, migration-011 Lifecycle Runtime Journal,
  idempotent/recoverable stage receipts, single-snapshot history reads and
  captured-source durable replay with pure model recomputation and read-only
  ManualTrade verification on the development branch, with the local
  repository-wide engineering gate passed;
- canonical-to-Legacy import enforcement, role-specific migration Protocols,
  seven technical-observable definitions, per-family differential evidence,
  FeatureBundle/Signal recomputation replay and architecture guards on the
  Feature Spine branch;
- append-only manual Fill ledger;
- exploratory Holding/Exit, TradeOutcome and rolling diagnostics;
- PostgreSQL-only settings/composition, native bounded repositories, migrations
  001–042, credential-free runtime bindings, isolated-schema replay and
  fail-closed database unavailability;
- mode-separated Research/Shadow Summary plus strict Production Decision,
  append-only Manual Account, Fill-derived Reconciliation, research-only
  Portfolio and independently reloaded Risk;
- stable cross-session State Series and immutable State/Pool Policy authority;
- versioned multi-horizon Outcome Targets, Research Shadow orchestration,
  prospective attestation mechanism and complete Evaluation Panel V2;
- owner-correct Runtime/Shadow read model with explicit unobserved metrics.

Delivered mechanics must not be upgraded to production, Alpha or trading-authority claims without the separate exit conditions above.

## 7. Required implementation order

```text
Frozen dependency/CI mechanics delivered; enforce required remote checks
→ H7 durable Holding/Exit
→ qualified H6 operational package production
→ Research Shadow operating mechanics delivered
→ H8 sustained real Shadow operations and authenticated control plane
→ qualified 14:55/Universe/Theme/Capital/account evidence
→ H9 formal validation infrastructure
→ sustained shadow evidence
→ production restore/security/observability/QuantDesk
→ separately approved broker architecture
```

Do not start production UI or live broker integration while the ShadowRun/evidence/validation layers remain incomplete. H4.5 completion creates only a manual intent and does not authorize an order, Fill or broker action.

The gap register retains these admission facts:

```text
automatic_order_execution = false
broker_integration_proven = false
entry_model_empirically_validated = false
production_ready = false
```
