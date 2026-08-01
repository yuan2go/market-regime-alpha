# Production Decision Lifecycle Gap Analysis

> **Status:** CURRENT_STATUS  
> **Authority:** Code-level architecture gap analysis for the production decision lifecycle  
> **Owner:** Market Regime Alpha maintainers  
> **Last Updated:** 2026-08-01  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** ../architecture/10-Production-Decision-Lifecycle.md, ../architecture/decisions/ADR-004-Production-Decision-Lifecycle-Organization.md, ../status/Gap-Register.md  
> **Code Evidence:** `main` as reviewed on 2026-08-01. This document distinguishes implemented code from proposed design.

## 1. Executive conclusion

The proposed production decision lifecycle belongs inside the existing repository. It is not a separate product domain and should not create a second project, data authority, model registry, state machine or artifact family for concepts already owned by `market-regime-alpha`.

The correct organization is a modular monolith that completes existing Platform V2 layers while preserving current DailyLoop and artifact compatibility. A future broker adapter may be independently deployed only when the external execution environment requires it.

The current repository is strong in immutable evidence, time semantics, replay, runtime recovery and research contracts. It is incomplete in operational integration, durable governance, signal execution, portfolio risk, manual execution records, position authority, holding/exit and complete attribution.

## 2. Confirmed current capabilities

| Capability | Current implementation evidence | Assessment |
|---|---|---|
| Stable identities | `core/identity.py` | Reusable |
| Semantic time | `core/time.py` | Reusable and mandatory |
| Provider and dataset contracts | `data/contracts.py` | Reusable |
| Field-level source authority | `data/source_manifest.py` | Reusable; formal providers still missing |
| PIT universe and eligibility | `universe/contracts.py` | Contracts ready; operational population incomplete |
| Feature contracts | `features/contracts.py` | Contracts ready; durable registry incomplete |
| Immutable artifact envelope | `evidence/envelope.py` | Reusable; current public Platform V2 ceiling remains EXPLORATORY |
| Runtime journal | `application/daily_loop/state.py`, repositories and SQLite adapter | Mature local recovery pattern |
| Daily source-to-decision flow | `application/daily_loop/runner.py` | Executable exploratory vertical slice |
| Platform V2 research flow | `research/platform_v2/pipeline.py` | Executable offline research slice |
| Market Regime | `research/market_regime/**` | V0 implemented; thresholds unvalidated |
| Theme Rotation | `research/theme_rotation/**` | V0 implemented; one-snapshot classifier, not historical state machine |
| Capital Evolution | `research/capital_evolution/**` | V0 implemented; proxy inference only |
| Candidate Discovery | `research/candidate_discovery/**` | V2 implemented with complete-population reconciliation |
| Signal boundary | `signals/contracts.py` | Contract only |
| Forecast boundary | `forecasting/contracts.py` | Strict next-session contract only |
| Entry path targets | `strategies/entry/**` | Valuable reusable path-target foundation |
| Trade decision boundary | `decision/contracts.py` | Thin simulation-only contract |
| Portfolio boundary | `portfolio/contracts.py` | Thin research-only contract |
| Execution boundary | `execution/contracts.py` | Simulation only; no manual ledger |
| Position/Exit boundary | `position/contracts.py` | Thin contract; no authoritative position |
| Evaluation boundary | `evaluation/contracts.py` | Generic report contract only |
| Model lifecycle | `platform/model_registry.py` | Strong rules, in-memory authority |
| Experiment governance | `platform/experiment_governance.py` | Strong rules, in-memory authority |
| CI and quality | `.github/workflows/ci.yml` | pytest, Ruff, mypy and doc validation |

## 3. Business-fit assessment

### Same domain

The proposed lifecycle uses the same:

- A-share market and data scope;
- Provider and SourceManifest identities;
- Universe and eligibility semantics;
- feature definitions and materializations;
- Market, Theme, Capital and Candidate research;
- model and experiment governance;
- immutable artifacts and replay;
- daily outcome and review evidence.

It therefore belongs to the same bounded system and lifecycle.

### Same data lifecycle

The desired flow begins with the current Source Freeze and ends with model evaluation. A separate project would need to import or duplicate every authority in between.

### Same deployment boundary for the current phase

The current runtime is a Python application with local/durable artifacts and SQLite journaling. Signal, thesis, manual records and position projection do not currently require independent scaling or deployment.

## 4. Direct conflicts between target behavior and current implementation

### 4.0 Phase 0 code-fact reconciliation

The current operational `DailyLoopRunner` publishes a verified Phase D daily
decision Artifact, but that Artifact does not own the complete Theme
Observation, Capital Observation, PIT Theme Membership or ETF-to-Theme mapping
evidence required by `ResearchInputBundle`. The Operational Research Bridge
therefore cannot derive or infer those facts from Candidate, Feature,
PredictionRun or Daily Decision payloads.

The bridge must instead consume a separate, immutable and content-addressed
supplemental research evidence bundle. That bundle must preserve exact source
Artifact references and hashes, its own SourceManifest, DecisionTime,
per-observation AvailabilityTime, PIT mappings, DataEligibility, missingness
and reason codes. The application adapter may validate and combine this bundle
with verified DailyLoop evidence, but it does not become a second data
authority. Missing, late, unverifiable or authority-incompatible supplemental
evidence fails closed.

`ModelRegistry` and `ExperimentGovernance` remain in-memory authorities. Their
domain transition and access-budget validation is implemented, while durable
Repository Protocols, optimistic concurrency and restart recovery are absent.

The `signals`, `forecasting`, `decision`, `portfolio`, `execution`, `position`
and `evaluation` packages currently provide mainly versioned contract
boundaries or placeholders. They do not yet provide the complete application
services, repositories, replay paths or lifecycle state machines described by
the target architecture. In particular, no actual Position Authority exists,
and there is no LIVE execution authority. Existing simulated execution records
do not establish fills or actual positions.

### 4.1 Fixed MR1 horizon

`daily_decision/recommendation.py` binds recommendations to the frozen next-session 10:30 target. The target production lifecycle needs configurable multi-horizon path semantics and cannot silently change the existing schema.

**Required action:** preserve MR1; add new PathForecast, TradingOpportunity and TradingThesis contracts.

### 4.2 Entry plumbing cannot enter

`daily_decision/entry.py` intentionally emits only `REJECT` or `WAIT_CONFIRMATION` and uses `ENTRY_MODEL_NOT_YET_VALIDATED` as the fixed non-data blocker.

**Required action:** keep plumbing behavior; implement a separate Platform V2 Signal/Decision path.

### 4.3 State labels are not historical state machines

Theme Rotation and Capital Evolution map current scores directly to labels. They do not consume previous state, state duration or hysteresis.

**Required action:** preserve V0 compatibility; introduce separate lifecycle snapshots when historical evidence is available.

### 4.4 Overlapping Theme and Capital factors

Relative strength, amount, breadth, leader and participation variables appear in both models and then enter Candidate Discovery together.

**Risk:** repeated counting and unstable interpretation.

**Required action:** run ablation and conditional evaluation before changing Candidate Discovery weights or gates.

### 4.5 Missing actual execution authority

Current execution contracts are simulation-only. No canonical manual order/fill ledger exists.

**Required action:** add append-only ManualTradeRecord and Fill contracts before creating authoritative PositionSnapshot.

### 4.6 Governance is not durable

Model Registry and Experiment Governance are process-memory dictionaries.

**Required action:** define repository protocols and durable SQLite/PostgreSQL adapters while preserving existing transition validation.

## 5. Capability matching

| Target capability | Existing base | Required change |
|---|---|---|
| Operational research input | DailyLoop artifacts + ResearchInputBundle | Add verified adapter |
| Market risk gate | MarketRegimeSnapshot | Validate and add historical evaluation |
| Theme priority | ThemeRotationSnapshot | Keep V0; add historical lifecycle later |
| Capital context | CapitalEvolutionSnapshot | Split observables and lifecycle in V1 |
| Candidate population | CandidateSet V2 | Preserve; add ablation-backed V3 only later |
| Signal | SignalSnapshot contract | Implement model, config, artifact, reader and replay |
| Multi-horizon forecast | EntryPath targets + forecast contract patterns | Add PathForecast |
| Trading opportunity | None | Add new aggregate |
| Trading thesis | None | Add new aggregate and state model |
| Portfolio construction | Thin PositionPlan | Implement target positions and constraints |
| Risk approval | Market exposure hint only | Add independent RiskDecision |
| Manual execution | None | Add ledger, idempotency and corrections |
| Position authority | None | Project from fills |
| Holding and Exit | Legacy/design only | Add independent assessments |
| Attribution | MR1 review + generic evaluation | Add complete trade and layer attribution |
| Operator surface | Legacy/uncertain | Add CLI first, API/UI later |

## 6. Technical-debt risks

### P0

- no formal PIT data authority;
- no operational 100–300 symbol universe;
- no authoritative theme mapping;
- no canonical actual-position state;
- no risk approval boundary;
- no manual fill ledger;
- no production authentication or permission model.

### P1

- Research Layer and DailyLoop are not operationally connected;
- Model Registry and Experiment Governance are not durable;
- Signal and Path Forecast are not executable;
- lifecycle labels can oscillate because they lack history and hysteresis;
- Theme and Capital factors may be repeatedly counted;
- production database and migration discipline are not established;
- no application-level outbox and audit-event store.

### P2

- no operator workbench;
- no production metrics, trace and alert implementation;
- no rolling multi-horizon scorecard;
- no controlled failure-attribution workflow;
- no formal provider comparison for future Xuntou/QMT data.

## 7. Recommended code placement

```text
application/operational_research/   # verified DailyLoop → Platform V2 adapter
application/trading_lifecycle/      # opportunity, thesis, portfolio, risk and manual orchestration
application/review_loop/            # holding, exit, settlement and attribution
signals/                            # executable signal research
forecasting/                        # PathForecast
 decision/                          # TradingOpportunity, TradingThesis, RiskDecision
portfolio/                          # target positions and portfolio constraints
execution/                          # manual intent and fill ledger
position/                           # position projection, holding and exit
evaluation/                         # complete-trade outcome and attribution
platform/                           # durable governance repositories
```

No new code should be added to `daily_research/**` except compatibility documentation or adapters. The fixed MR1 behavior under `daily_decision/**` should remain unchanged.

## 8. Persistence assessment

### Keep as immutable artifacts

- source archives;
- SourceManifest;
- feature and research artifacts;
- Signal and Forecast artifacts;
- evaluation and attribution artifacts.

### Store as operational mutable state

- opportunity and thesis state;
- portfolio and risk decisions;
- manual trade intents;
- fill ledger;
- position projection;
- durable model and experiment governance;
- audit and outbox events.

SQLite is sufficient for local implementation and deterministic tests. PostgreSQL should become the production operational authority only after repository compatibility and migration tests exist.

## 9. Test gaps

The current suite is strong for artifact integrity and DailyLoop recovery. New work must add:

- opportunity/thesis state tests;
- risk-rule and risk-timeout tests;
- partial-fill and correction tests;
- position rebuild tests;
- T+1 and suspension tests;
- optimistic concurrency tests;
- durable governance restart tests;
- SQLite/PostgreSQL repository contract tests;
- complete lifecycle replay;
- operator permission tests;
- performance and sustained shadow-run checks.

## 10. Organization decision matrix

| Option | Benefit | Main cost | Decision |
|---|---|---|---|
| Extend current modules directly | Fast initial edits | mixed authority and God Objects | Reject |
| Add bounded modules in current application | Maximum reuse and clear ownership | requires discipline | Accept |
| Split into services now | physical isolation | premature distributed complexity | Reject |
| Create new project | independent repository | duplicate truth and lifecycle | Reject |
| Modular monolith with future broker adapter | current simplicity and future deployment seam | requires stable ports | Recommended |

## 11. Unique recommendation

Continue in the existing repository as a modular monolith. Complete Platform V2 layers with new bounded modules, preserve immutable evidence and current schema compatibility, establish manual fills as the first execution authority, derive positions only from fills, and postpone any separately deployed broker adapter until after a verified shadow and manual-operation phase.

## 12. Unconfirmed items

The following remain unconfirmed by the reviewed canonical code paths:

- whether any legacy FastAPI endpoint is still operationally used;
- current production server and scheduler topology;
- credential and secret-management implementation;
- commercial data licences and formal availability guarantees;
- external databases maintained outside the repository;
- an existing QMT/PTrade adapter that satisfies the proposed authority model;
- a production authentication and authorization provider.
