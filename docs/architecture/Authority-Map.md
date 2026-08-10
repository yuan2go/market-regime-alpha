# Authority Map

> **Status:** CURRENT_ARCHITECTURE
> **Authority:** Canonical ownership and write map
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-10
> **Code Evidence:** `src/market_regime_alpha/application/authority_boundary.py`, `src/market_regime_alpha/persistence/repository_factory.py`, `src/market_regime_alpha/persistence/postgres/schema.py`, `src/market_regime_alpha/persistence/postgres/migrations/*.sql`

## Terms

- **Runtime Authority** decides whether and when work may run, resume or replay.
- **Business Authority** is the unique writer of a domain state transition.
- **Evidence Authority** is immutable owner-resolved evidence with identity, content, time, status and lineage verified.
- **Projection** is a derived read model. It cannot promote its inputs.
- **Protocol/Policy** constrains a writer. It is not a writer.
- **Qualification** is a governed transition recorded by its owner, not a boolean in a DTO.
- Model Governance `QUALIFIED` is purpose-scoped model-runtime eligibility. For `RESEARCH`/`BACKTEST`/`SHADOW` it does not qualify the referenced Dataset, OOS result, Calibration, Entry, Holding/Exit or Strategy Shadow artifact; only that artifact's owner can do so.

## Canonical counts

| Question | Current answer |
|---|---|
| Canonical all-day Runtime | One: `CONTINUOUS_RESEARCH`. |
| Canonical Decision writer | One PostgreSQL bounded owner, `PostgresDecisionSystemRepository`; Research Summary and manual-account Decision System are distinct documents, not competing writers. |
| State Authority | One: `PostgresStateSystemRepository`, with typed State tables and one StateSeries head/CAS authority. |
| Outcome Authority | One factual Shadow outcome family: target protocol plus targeted/prospective settlements in PostgreSQL. Diagnostic trade outcomes remain strategy/evaluation artifacts, not actual Position truth. |
| Model Governance | One: `PostgresModelGovernanceRepository`; Model Registry lifecycle remains a subordinate registry history in the same governance schema. |
| Research Shadow | Freezes research decisions and factual outcome lineage; it never simulates account execution. |
| Strategy Shadow | Simulates Entry/Fill/Position/Holding/Exit in an isolated ledger; it never writes actual fills or positions. |
| Production Admission | A blocked projection only. No final Production Admission Authority exists. |
| PostgreSQL Authority-schema tables | 148 in `EXPECTED_AUTHORITY_TABLES`; this catalog includes owner state, journals and projections and is not a count of independent business Authorities. |

## Owner map

| Capability | Canonical writer / repository | Principal PostgreSQL tables | Runtime caller / consumer | Replay | Evidence ceiling / Legacy |
|---|---|---|---|---|---|
| Runtime schedule and tick | `PostgresContinuousResearchJournal` | `continuous_research_run`, `continuous_runtime_schedule`, `continuous_runtime_tick`, `continuous_runtime_event`, `continuous_child_run` | `continuous-research run-due`; all children | journal resume/replay | Research/Shadow; no broker or Position mutation |
| Provider attempt and current evidence | same journal plus runtime evidence repository | `continuous_provider_attempt`, `continuous_evidence_commit`, `continuous_current_evidence`, `continuous_change_decision`, `continuous_runtime_authority_evidence` | Tick Runner; State/Controlled/Summary | immutable commit and current-pointer replay | free data is exploratory/PIT-incomplete |
| Source freeze, Dataset, Feature | `PostgresDailyRunRepository`, `PostgresFeatureMaterializationRunRepository` | `daily_runs`, `acquisition_stage_receipts`, `stage_receipts`, `feature_materialization_*` | Free-data service, then State System | run/task receipts and materialization readers | canonical writer; old file artifacts are readers only |
| Formal PIT | `PostgresPITAuthority` | `pit_authority_action`, `pit_artifact_authority_resolution`, `pit_source_qualification*`, `pit_fact_revision`, `pit_fact_temporal_authority_resolution`, `pit_as_of_snapshot`, `formal_pit_validation_evidence` | `pit-authority`, Governance bridge, formal research | exact snapshot/evidence replay | mechanics implemented; qualified real Provider evidence absent |
| Model Registry/Governance | `PostgresModelGovernanceRepository` | `governance_commands`, `model_registrations`, `model_lifecycle_transitions`, `model_governance_*`, `model_version_lineage`, `model_qualification_*`, `model_runtime_*`, `model_selection_receipt` | State/Signal/Forecast selectors, Decision System | revision-bound receipt replay/export | Research/Shadow runtime eligibility only; it cannot promote referenced artifacts. Production qualification is forced closed until all floor owners resolve. |
| State, StateSeries, Pool, Candidate | `PostgresStateSystemRepository` | typed Market/ETF/Theme/Capital observation/state/transition tables, `state_current_pointer`, `state_series*`, `dynamic_stock_pool*`, `state_policy_authority`, `state_runtime_*`, `state_research_stage_authority` | Continuous free-data composition | receipt, series and stage replay | research state; no Entry authority |
| Controlled decision-time operation | `PostgresDecisionTimeOperationJournal` | `controlled_operation_run`, `controlled_operation_stage`, `controlled_operation_attempt`, `controlled_operation_receipt`, `controlled_operation_child_run`, `controlled_operation_event` | Continuous child | package/receipt replay | bounded Research/Shadow operation |
| Canonical lifecycle | `PostgresLifecycleRunRepository` | `lifecycle_runs`, `lifecycle_stages`, `lifecycle_attempts`, `lifecycle_stage_receipts`, `lifecycle_events` | optional Controlled child | stage receipt replay | downstream human-in-loop continuation, not a scheduler |
| Research Summary and Decision System | `PostgresDecisionSystemRepository` | `research_daily_summary`, `research_summary_stage`, `manual_account_observation`, `manual_position_observation`, `account_reconciliation`, `daily_decision_summary`, `daily_summary_candidate`, `research_portfolio_*`, `independent_risk_decision`, `decision_runtime_receipt`, configuration/evidence tables | Continuous Summary child; separate `decision-system` CLI | current repository Readers; no composed full Decision replay | Summary is Research/Shadow; Production Decision remains blocked by Governance |
| Opportunity and Thesis | `PostgresDecisionLifecycleRepository` | `decision_commands`, `trading_opportunities`, `opportunity_events`, `trading_theses`, `thesis_events` | Canonical lifecycle | append-only event restoration | proposal/thesis only, no actual Position |
| Portfolio and Risk | portfolio repositories | `portfolio_risk_commands`, `portfolio_decisions`, `risk_decisions`, complete-account snapshot/decision tables, risk route tables | lifecycle and Decision System | event/decision Readers | decision support only; Risk rejection cannot be bypassed |
| Manual execution and actual Position | manual execution and traceability repositories | `execution_commands`, `manual_trade_records`, `manual_trade_events`, `manual_fills`, `position_books`, `position_book_events`, `traceable_manual_trade_bindings` | explicit human record/import | append-only ledger replay | actual Position derives only from observed Fill |
| Research Shadow | `PostgresShadowResearchRepository` | `shadow_research_session`, `shadow_research_decision`, `shadow_research_decision_state_policy`, `shadow_research_event` | `research-shadow` | session/decision/event replay | frozen research decision only |
| Outcome and Target | target/outcome repositories | `outcome_target_protocol`, `outcome_target_definition`, `targeted_shadow_outcome`, `targeted_shadow_outcome_label`, `prospective_outcome_settlement`, `prospective_evidence_attestation` | later checkpoint acquisition and evaluation | immutable target/outcome/attestation Readers | attestation is owner-checked but `prospective_proven=false` |
| Evaluation Dataset and Panel | evaluation/panel repositories | `research_evaluation_dataset`, settlement table, `research_evaluation_panel_v2`, row/slice tables | Factor Extraction and validation harness | immutable dataset/panel Readers | evidence assembly, not Alpha or qualification |
| Research Validation | `PostgresResearchValidationRepository` | `research_validation_artifact`, factor exposure, historical sample and calibration binding tables | offline research harness | payload/sample Readers | migration 046 enforces engineering/unqualified only |
| Strategy Shadow | `PostgresStrategyShadowRepository` | `strategy_shadow_session`, `strategy_shadow_event`, `strategy_shadow_artifact` | separately invoked research workflow | CAS session and artifact replay | simulated only; real-trading mutation is false |
| Production Admission | no Authority writer | no final owner table | none | none | always `BLOCKED`; operator/RBAC/broker floors do not exist |

## Qualification closure

The canonical rule is:

```text
Reference
-> owner Repository reload
-> ID/hash verification
-> semantic status verification
-> availability/system-time verification
-> lineage/protocol verification
-> governed qualification decision
```

Current promotion matrix:

| Claimed transition | Current writer behavior |
|---|---|
| `PIT_ELIGIBLE` historical sample | No writer. Migration 046 permits `UNQUALIFIED` only. |
| `OOS_ELIGIBLE` / Formal OOS | The harness computes metrics but cannot emit durable Formal OOS Authority. |
| `CALIBRATED` | Fit/evaluation artifacts remain `calibrated=false`. |
| `ENTRY_QUALIFIED` | Entry research can emit Shadow decisions; no qualification writer exists. |
| `HOLDING_EXIT_VALIDATED` | Engineering floor assessment only; no qualification writer exists. |
| `STRATEGY_SHADOW_PROVEN` | Engineering floor assessment only; prospective attestations remain unproven. |
| `ELIGIBLE_FOR_OPERATOR_REVIEW` | Not emitted; Production Admission remains blocked. |
| `PRODUCTION_AUTHORIZED` | PostgreSQL Model Governance adds `PRODUCTION_EVIDENCE_OWNER_RESOLUTION_NOT_IMPLEMENTED`; no assignment can pass. |

This is closed by denial, not by claiming the missing evidence exists.

## Legacy boundary

| Namespace | Classification | Retained capability | Prohibited capability |
|---|---|---|---|
| `daily_research` | `COMPATIBILITY_REQUIRED` / historical Reader | immutable V1 identity, Reader and replay compatibility | execute or write from Canonical composition |
| `dividend_t` | `HISTORICAL_READER` / characterization | legacy research reproduction and isolated legacy web view | canonical Runtime, Repository, Signal, Entry, Position or broker authority |
| `legacy/**` | `COMPATIBILITY_REQUIRED` | explicit adapters | direct canonical import |
| `migration/legacy/**` | `MIGRATION_ONLY` / `REPLAY_ONLY` | differential comparison and conversion | current business writes |
| `decision_replay_import` table | `HISTORICAL_SCHEMA` | preserve already-recorded append-only rows and forward-only migration history | application writes, Reads, composition or Authority claims |

Architecture tests enforce that installed CLI and Canonical compositions do not import Legacy producers.
