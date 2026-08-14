# System Architecture

> **Status:** CURRENT_ARCHITECTURE
> **Authority:** Canonical implementation architecture
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-14
> **Code Evidence:** `src/market_regime_alpha/cli/continuous_research.py`, `src/market_regime_alpha/application/continuous_research`, `src/market_regime_alpha/persistence/repository_factory.py`, `src/market_regime_alpha/persistence/postgres/migrations/*.sql`

## Shape

Market Regime Alpha is one Python modular monolith with one PostgreSQL 16 authority. It is a human-in-the-loop research and decision-support system. It has no broker writer and no automatic Order, Fill or Position authority.

There is one canonical all-day runtime owner:

```text
continuous-research run-due
  -> ContinuousResearchScheduleRunner
  -> ContinuousResearchTickRunner
  -> PostgresContinuousResearchJournal
  -> Provider attempt / immutable evidence commit / change decision
  -> ordered bounded-context children
```

`canonical_lifecycle`, `controlled_operation`, `state_system` and `decision_system` are bounded children or operator tools. They are not parallel daily schedulers.

## Actual runtime chain

The current free-data Research/Shadow composition is:

```text
BaoStock/Tencent recorded provider evidence
-> SourceFreezeService
   -> retained DailyLoop identity adapter
-> Canonical market-data Dataset
-> Feature materialization
-> PostgreSQL Model Governance selection
-> State System
   -> Market Regime
   -> ETF Rotation
   -> Theme Rotation
   -> Capital State
   -> StateSeries
   -> Dynamic Stock Pool
   -> Candidate
-> Controlled Operation
   -> pre-decision minute evidence
   -> Signal
   -> PostgreSQL Historical Sample Registry Reader
   -> uncalibrated exploratory PathForecast
   -> optional Canonical Lifecycle child
-> ResearchDailySummary
-> MultiStrategyRuntime child
   -> Overnight Strategy Run
   -> Swing State Strategy Run
   -> Cross-strategy Portfolio Decision
-> Continuous child receipts and terminal tick
```

The Strategy child is part of the existing tick fence. It reloads the exact
Candidate fact and stable Strategy Versions, records the complete gate/action
funnel, and persists one Portfolio decision. It creates no Order, Fill, or
physical Position. A model-blocked empty CandidateSet is itself a durable State
owner fact, so both strategies record `DATA_INSUFFICIENT` instead of silently
disappearing from the research sample.

Before the decision child, the Research/Shadow composition may retrospectively
build exact-14:55 BaoStock decisions, T+1 multi-horizon outcomes and PathForecast
samples. The resulting Historical Sample Dataset is immutable, PostgreSQL-owned,
`UNQUALIFIED` and `FREE_DATA_EXPLORATORY`. Its retrieval time is its earliest
availability time, so the current run cannot consume a dataset retrieved at or
after its own decision time. A first run therefore remains fail-closed; a later
decision may consume already-registered samples. Production composition never
receives this Reader. BaoStock `adjustflag=3` is accepted only when the frozen
Target declares `RAW_UNADJUSTED_TRADABLE_PRICE_V1`; adjustment semantics are
never substituted or promoted.

The runtime denies `PRODUCTION` when the input is free public evidence. A missing or invalid stage is represented by typed blocked evidence; the runtime does not synthesize a missing Canonical Lifecycle receipt.

Multi-year research runs are bounded operator jobs, not a second all-day
Runtime. `HistoricalResearchRunner` advances a shared Decision Session Kernel
through a PostgreSQL lease/fence/stage journal and can resume or replay the same
Runtime Scope, Experiment and Target identities. Research-model and performance
operators use the same database and remain exploratory.

The Historical `STRATEGY` and `PORTFOLIO` stages call the same
`MultiStrategyRuntime` and PostgreSQL repository as the Continuous child.
`HISTORICAL`, `REPLAY`, and `SHADOW` remain explicit origins in lineage, while
the strategy-policy/action semantics are shared.

The post-runtime chain is orchestrated by thin commands on the same runtime and
the existing PostgreSQL owners; it is not a second scheduler or daily writer:

```text
ResearchDailySummary
-> Research Shadow frozen decision
-> factual Outcome / Target settlement
-> prospective attestation (currently prospective_proven=false)
-> Evaluation Dataset / Research Panel V2
-> canonical Factor Extraction
-> engineering Ablation / Calibration / Formal Evaluation
-> Entry research
-> isolated Strategy Shadow Entry/Fill/Position
-> CAS-linked Portfolio Shadow day state
-> Holding / Exit engineering validation
-> engineering RBAC Approval/Audit (separate operator boundary)
-> blocked Production Admission projection
```

Historical Research is a bounded batch child, not another all-day Runtime or a
separate Backtest authority:

```text
Free Research Universe + captured Operational Universe facts
-> immutable Runtime Scope receipt
-> PostgreSQL Historical Research Journal
-> shared Decision Session Kernel
-> existing Continuous/Shadow/Strategy/Portfolio/Outcome owners
-> immutable Performance/Attribution report
-> deterministic replay against the same owner hashes
```

The journal applies sessions and stateful portfolio transitions serially in
trading-calendar order. Each stage uses a lease, fencing token, expected
predecessor and immutable receipt. Resume advances the same run; replay reloads
captured facts and never calls a replacement Provider. Free Provider overlap is
resolved below Canonical facts with complete provenance and conservative
eligibility aggregation.

## Installed CLI boundary

There are six installed scripts and exactly the same six CLI modules have
`__main__` guards: `continuous-research`, `state-system`, `decision-system`,
`model-governance`, `pit-authority` and `research-shadow`.

The prior 18 guarded modules are classified as follows. Removing a guard does
not remove an importable compatibility function or its tests.

| Module | Classification | Executable treatment |
|---|---|---|
| `continuous_research` | `PUBLIC_OPERATOR` | installed; owns the daily commands plus Runtime Scope, Historical Research, Performance, exploratory Model and fail-closed Formal assessment build/report/replay operations |
| `state_system` | `PUBLIC_OPERATOR` | installed bounded owner/admin command |
| `decision_system` | `PUBLIC_OPERATOR` | installed bounded decision-support command |
| `model_governance` | `PUBLIC_OPERATOR` | installed Model and engineering Access Governance administration command |
| `pit_authority` | `PUBLIC_OPERATOR` | installed Authority administration command; Formal qualification remains closed |
| `research_shadow` | `PUBLIC_OPERATOR` | installed bounded research command |
| `compare_legacy_features` | `RESEARCH_TOOL` | importable harness; main guard removed |
| `materialize_features` | `RESEARCH_TOOL` | importable harness; main guard removed |
| `replay_feature_bundle` | `RESEARCH_TOOL` | importable harness; main guard removed |
| `prepare_controlled_operation` | `INTERNAL_ONLY` | called through the canonical composition; main guard removed |
| `report_controlled_operation` | `INTERNAL_ONLY` | compatibility function; main guard removed |
| `resume_controlled_operation` | `INTERNAL_ONLY` | compatibility function; main guard removed |
| `replay_controlled_operation` | `INTERNAL_ONLY` | compatibility function; main guard removed |
| `settle_controlled_operation` | `INTERNAL_ONLY` | reused by settlement owner; main guard removed |
| `run_canonical_lifecycle` | `INTERNAL_ONLY` | bounded child implementation; main guard removed |
| `replay_canonical_lifecycle` | `INTERNAL_ONLY` | bounded child replay; main guard removed |
| `create_manual_trade_from_risk_decision` | `INTERNAL_ONLY` | manual-account application helper; main guard removed |
| `run_decision_window` | `LEGACY` | compatibility composition only; main guard removed |

No reviewed guarded module was `DEAD`; deletion would remove still-tested
compatibility behavior. The six former `*-free-data-operation` installed aliases
were duplicate entry points and were removed from packaging.

## Package responsibilities

| Package | One responsibility |
|---|---|
| `application/continuous_research` | Own the all-day schedule, tick lease/fence, provider attempt and child composition. |
| `application/source_freeze` | Expose the canonical source-only freeze seam over retained Daily identities. |
| `application/free_data_operation` | Run one bounded public-data decision-window operation. |
| `application/state_system` | Persist ordered State, StateSeries, Pool and Candidate owner receipts. |
| `application/controlled_operation` | Coordinate one decision-time acquisition/calculation package. |
| `application/canonical_lifecycle` | Recover one downstream research-to-manual lifecycle run; never schedule the day. |
| `application/decision_system` | Own Research Summary and the separate manual-account decision-support projection. |
| `application/shadow_research` | Freeze research decisions and settle factual prospective outcomes. |
| `application/research_evaluation` | Build immutable outcome datasets, target protocols and complete Research Panel V2. |
| `application/research_validation` | Compute engineering-only factor, ablation, calibration, evaluation and Entry evidence. |
| `application/research_session` | Apply one ordered live/Shadow/Historical decision session through typed owner stages. |
| `application/historical_research` | Own the bounded multi-session command, PostgreSQL journal, recovery and deterministic replay. |
| `application/strategy_shadow` | Simulate Entry/Fill/Position/Holding/Exit without real execution mutation. |
| `application/governance` | Own append-only engineering Principal/Role/Approval/Audit facts; never Production Admission. |
| `research/**` | Hold pure research models and observable State algorithms. |
| `market_data`, `data`, `universe`, `features` | Own source semantics, datasets, eligibility, materialization and feature lineage. |
| `signals`, `forecasting`, `candidates` | Compute distinct Candidate, Signal and Forecast artifacts. |
| `platform` | Own Model Registry, Model Governance, experiment governance and selection receipts. |
| `decision`, `portfolio`, `execution`, `position` | Own Opportunity/Thesis, Portfolio/Risk, manual Fill and fill-derived Position lifecycles. |
| `persistence` | Compose PostgreSQL-only repositories and validate the full schema. |

## Dependency rules

- Domain objects do not schedule runtimes or select repositories.
- Application compositions call bounded owners; they do not recreate their persistence.
- Projection, DTO, protocol, policy and reference objects never grant Authority.
- New writers use `RepositoryFactory` and PostgreSQL. No file or SQLite persistence fallback exists.
- Legacy may be read or characterized only through explicit compatibility/migration boundaries.
- Artifact recovery resolves PostgreSQL `artifact-root-v1` locators and receipt
  locators with hash verification; directory discovery is not an Authority.
