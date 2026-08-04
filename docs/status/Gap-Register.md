# Gap Register

> **Status:** CURRENT_STATUS  
> **Authority:** Ordered gap and dependency register  
> **Owner:** Market Regime Alpha maintainers  
> **Last Updated:** 2026-08-04
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** Current-State.md, Capability-Matrix.md, ../architecture/13-Canonical-Market-Data-and-Feature-Spine.md, ../audit/H4-5-Risk-Reduction-Manual-Intent-Delivery.md, ../audit/H6-Composite-Operational-Evidence-Delivery.md, ../audit/H5-Thesis-Health-Delivery.md, ../audit/H4-Risk-Route-Delivery.md, ../audit/Current-Main-Code-Audit-2026-08-01.md, ../roadmap/work-packages/WP-PDL-Hardening-and-Shadow-Readiness.md, ../architecture/11-Production-Lifecycle-Hardening-and-Shadow-Operations.md, ../architecture/12-Canonical-Runtime-and-Legacy-Migration.md
> **Code Evidence:** Canonical Feature Spine checkpoint `14058a5`; canonical runtime merge baseline `9ccc751`; H4.5 checkpoint `b1d6533a0b3b1bbd9e180c7f6864b3be8dbd2254`; H6 checkpoint `654e025b97c5d9553d7614b4b5be0898272aacbc`
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
| H8 sustained Shadow operations | P1 | The development branch has a single-run Lifecycle owner, migration-011 stage receipts, one-snapshot history reads, retry/resume and captured-source durable replay; it has no scheduler/control plane, lease owner, deadlines, operator acknowledgement, metrics, alerts or sustained run evidence | Canonical runtime plus H7 | A scheduled Shadow operation proves consecutive runs, operator deadlines/acknowledgements, metrics/alerts, recovery drills and replay without changing authority ceilings |
| H9 Signal/Path validation infrastructure | P1 | Signal and PathForecast mechanics exist with explicit assumptions, but no formal incremental-value, calibration or locked OOS infrastructure | Qualified historical data and H8 artifact production | Purged walk-forward, embargo, controls, calibration, sensitivity and frozen OOS protocols pass leakage checks |
| Runtime governance integration | P1 | Persistent Model/Experiment repositories exist, but DailyLoop creates a local in-memory `ModelRegistry` for B0/B1 | Green baseline and repository ownership decision | Runtime loads approved immutable model/config references from governance authority and cannot bypass transitions/access budgets |
| Feature package storage efficiency | P2 | 100-symbol offline benchmark produced 127,261,684 bytes; deterministic JSON packages duplicate source references for audit clarity | Stable schema plus format migration design | Versioned selective/columnar encoding materially reduces storage and read latency without Decimal/time/hash/Reader drift |
| PostgreSQL repository parity | P1 | Lifecycle persistence is SQLite local/test authority | Stable Repository protocols and contract suite | PostgreSQL adapters pass the same concurrency, idempotency, reconstruction and migration contract tests |

## 3. Data and operational evidence gaps

| Gap | Priority | Current state | Dependency | Exit condition |
|---|---|---|---|---|
| Controlled 14:55 public runtime | P0-EXTERNAL | Public acquisition stages exist; latest real run was outside the historical DecisionTime and correctly became `DATA_BLOCKED` | Controlled scheduling and provider availability | Sustained exact-window archives reach `OUTCOME_PENDING` and replay with stable hashes |
| Qualified Xuntou V4 input | P0-EXTERNAL | Adapter/preflight/evidence contracts exist; no qualified real XtQuant bundle has passed | Windows XtQuant exporter and source inventory | Real bundle passes qualification and same-pipeline comparison without authority promotion |
| Operational stock Universe | P1 | Runtime uses a fixed 20-symbol smoke pool | Successful provider archive and approved PIT membership/liquidity source | Versioned 100–300 symbol Universe accounts for every inclusion/exclusion and replays identically |
| Canonical ETF Universe | P1 | ETF observations/mappings are supplemental only; no ETF Universe, tracking-index identity or primary/alternative policy | ETF reference data and PIT mapping | Separate immutable ETF Universe and eligibility artifact supports replay and delisting/duplication rules |
| PIT theme membership | P1 | Bridge requires full membership coverage, but no qualified daily producer exists | Theme taxonomy and effective-dated source | Every symbol’s primary/supporting membership is available by DecisionTime and versioned |
| Theme/ETF mapping | P1 | Supplemental contract requires exact mapping coverage; no operational producer exists | ETF Universe and theme taxonomy | Every proxy mapping has effective time, source lineage and deterministic Reader |
| Theme and Capital observations | P1 | V0 models run from typed fixtures/supplemental artifacts | Qualified market/ETF/symbol history | Daily materializer produces complete decision-time observations with missingness and coverage reports |
| External account authority | P1 | H1 snapshots and H3 positions are based on explicit/manual evidence | Broker statement/import boundary | Complete cash/position statement is authenticated, versioned and reconciled before Risk |
| Fill reconciliation | P1 | Fill is append-only human-recorded evidence, not broker truth | External execution statement and operator roles | Every manual Fill is matched, disputed or corrected through an append-only reconciliation workflow |

## 4. Research and model gaps

| Gap | Priority | Current state | Dependency | Exit condition |
|---|---|---|---|---|
| Real Entry Model | P1 | Canonical Entry emits only `REJECT` or `WAIT_CONFIRMATION`; `ENTER` is intentionally absent | Qualified Candidate/Signal/path evidence and validation protocol | Independent Entry model has frozen inputs, thresholds, target, cost assumptions, calibration and OOS result |
| Entry authority namespace convergence | P1 | Canonical `daily_decision` Entry cannot emit `ENTER`, while older `daily_research.EntryState` still defines an ENTER-capable contract | Reader/producer inventory and compatibility decision | Legacy ENTER-capable artifacts are explicitly historical/isolated or migrated; no runtime can confuse them with canonical Entry authority |
| Market Regime validation | P1 | Deterministic weighted gate with explicit thresholds | Qualified historical observations | Walk-forward comparison proves usefulness for exposure/gating versus simpler controls |
| Theme lifecycle semantics | P1 | Theme Rotation V0 is direct per-day classification | PIT history and transition protocol | Versioned state machine includes persistence, duration, hysteresis and validated decay behavior |
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
| Metrics, tracing and alerts | P1 | Reason codes and artifacts exist; no production telemetry stack | H8 | Stage latency/failure/data-quality/risk/reconciliation metrics, trace IDs and actionable alerts are operational |
| Backup and recovery | P1 | Append-only histories and artifacts are reconstructible, but no production recovery evidence exists | PostgreSQL/filesystem deployment | Point-in-time restore, artifact restore and reconciliation drills are documented and tested |
| QuantDesk read model | P2 | Canonical lifecycle is CLI-driven; Legacy FastAPI is not Reader-backed | Stable H8 commands/queries | UI reads verified artifacts and durable projections without recomputing decisions |
| Legacy Dashboard isolation | P1 | `web/dividend_t_app.py` can use static fallback and Legacy strategy/risk paths | QuantDesk replacement or explicit isolation | Legacy endpoint is local-only/clearly labelled and cannot be confused with canonical authority |
| Broker adapter architecture | DEFERRED | QMT/PTrade adapters safely reject live operations | Sustained shadow evidence, security review and separate approval | Versioned intent port, external receipts, reconciliation, permissions and kill switch pass dedicated admission |

## 6. Delivered engineering mechanics retained

The following are not open implementation gaps, although their operating/model evidence remains limited:

- immutable content-addressed artifacts and semantic Readers;
- SourceManifest and fail-closed DataQuality;
- B0/B1 PredictionRuns and candidate baselines;
- recoverable exploratory DailyLoop;
- Market/Theme/Capital/Candidate research mechanics;
- Signal and uncalibrated PathForecast mechanics;
- SQLite Opportunity/Thesis lifecycle;
- H1 complete-account Portfolio/Risk;
- H2 Thesis-scoped authority trace;
- H3 Fill/calendar-derived T+1 Position;
- H4 reducing-risk domain, SQLite persistence, idempotency, strict restoration and decision-only CLI;
- H4.5 ManualTrade V3 route authority, immutable Directive/Policy/Attempt,
  migration 010, unified atomic confirmation, H5/H6 lineage validation,
  T+1/Gate recheck, reducing Fill compatibility and reference-only CLI;
- H5 typed invalidation rules, verified current-evidence Builder, V2 Observation, migration 008, SQLite replay, V2-only CLI and thin operational assessment adapter;
- H6 typed composition policy/manifest, exact immutable package, migration 009, append-only SQLite replay index, V2-only operational research route and H5 integration;
- canonical 16-stage Runner, migration-011 Lifecycle Runtime Journal,
  idempotent/recoverable stage receipts, single-snapshot history reads and
  captured-source durable replay with pure model recomputation and read-only
  ManualTrade verification on the development branch, with the local
  repository-wide engineering gate passed;
- canonical-to-Legacy import enforcement, role-specific migration Protocols,
  six technical-observable families, per-family differential evidence,
  FeatureBundle/Signal recomputation replay and architecture guards on the
  Feature Spine branch;
- append-only manual Fill ledger;
- exploratory Holding/Exit, TradeOutcome and rolling diagnostics.

Delivered mechanics must not be upgraded to production, Alpha or trading-authority claims without the separate exit conditions above.

## 7. Required implementation order

```text
Frozen dependency/CI mechanics delivered; enforce required remote checks
→ H7 durable Holding/Exit
→ qualified H6 operational package production
→ H8 sustained Shadow operations and control plane
→ qualified 14:55/Universe/Theme/Capital/account evidence
→ H9 formal validation infrastructure
→ sustained shadow evidence
→ security/PostgreSQL/observability/QuantDesk
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
