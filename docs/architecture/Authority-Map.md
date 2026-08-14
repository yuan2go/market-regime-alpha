# Authority Map

> **Status:** CURRENT_ARCHITECTURE
> **Authority:** Canonical ownership and write map
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-14
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
| Strategy Shadow | Owns the isolated simulated lifecycle plus Strategy sleeve projection and fill-derived realized Strategy Outcomes. Simulated artifacts never write actual fills or physical positions; sleeve quantity is derived from manual Fill allocations. |
| Multi-Strategy business facts | One `PostgresMultiStrategyRepository` owns stable Strategy registration, cycles/runs/gates/proposals, cross-strategy Portfolio decisions, observed-Fill allocations, Path Outcomes and version-scoped feedback. The existing Strategy Shadow owner resolves state/outcomes from those facts. It is a bounded child of the existing runtimes. |
| Production Admission | A blocked projection only. No final Production Admission Authority exists. |
| PostgreSQL Authority-schema tables | 270 in `EXPECTED_AUTHORITY_TABLES`; this catalog includes owner state, journals and projections and is not a count of independent business Authorities. |

## Complete capability ledger

Every entry separates ownership from storage and consumption. A missing writer or replay path is recorded as missing; it is not inferred from a DTO or table name.

### Continuous schedule and tick

- **Domain / Capability:** Runtime / all-day scheduling, tick lease and child order.
- **Classification:** Runtime Authority.
- **Owner:** Continuous Research.
- **Canonical Writer:** `PostgresContinuousResearchJournal` through `ContinuousResearchScheduleRunner` and `ContinuousResearchTickRunner`.
- **Reader:** Journal `get`/inspection methods and `continuous-research inspect-run`.
- **Repository:** `PostgresContinuousResearchJournal`.
- **PostgreSQL tables:** `continuous_research_run`, `continuous_runtime_schedule`, `continuous_runtime_tick`, `continuous_runtime_event`, `continuous_child_run`.
- **Artifact / Receipt:** run, tick, event and child-run records.
- **Runtime caller:** `continuous-research run-due`.
- **Downstream consumer:** every ordered Continuous child and runtime report.
- **Replay mechanism:** journal resume plus Continuous replay/report Readers.
- **Evidence ceiling:** Research/Shadow; never Order, Fill or Position mutation.
- **Legacy replacement:** replaces ad-hoc DailyLoop scheduling; bounded free-data commands are not replacements for this owner.

### Provider attempt and current evidence

- **Domain / Capability:** Runtime evidence / provider acquisition attempt, immutable evidence commit and current pointer.
- **Classification:** Runtime and Evidence Authority.
- **Owner:** Continuous Research evidence boundary.
- **Canonical Writer:** `PostgresContinuousResearchJournal` and `PostgresRuntimeAuthorityEvidenceRepository`.
- **Reader:** current-evidence, attempt, commit and runtime-authority evidence repository methods.
- **Repository:** Continuous journal plus runtime Authority evidence repository.
- **PostgreSQL tables:** `continuous_provider_attempt`, `continuous_evidence_commit`, `continuous_current_evidence`, `continuous_change_decision`, `continuous_runtime_authority_evidence`.
- **Artifact / Receipt:** provider attempt, evidence commit/current reference, change decision and runtime Authority evidence.
- **Runtime caller:** Continuous Tick Runner.
- **Downstream consumer:** Dataset freeze, State System, Controlled Operation and Research Summary.
- **Replay mechanism:** immutable commit reload and current-pointer lineage replay.
- **Evidence ceiling:** public free data remains exploratory and PIT-incomplete;
  multiple free Providers may contribute or cross-check one Fact Kind, but
  agreement cannot manufacture archive/finality/availability qualification.
- **Legacy replacement:** replaces mutable/local provider result handoff in the Canonical composition.

### Runtime Scope

- **Domain / Capability:** Universe / immutable per-session runnable symbol scope.
- **Classification:** Research Evidence Authority; Policy constrains but does not write.
- **Owner:** Runtime Scope bounded context.
- **Canonical Writer:** `PostgresRuntimeScopeRepository` through `PostgresRuntimeScopeOperator`.
- **Reader:** scope/policy/operational-input reload and as-of resolution.
- **PostgreSQL tables:** `research_universe_policy`, `runtime_scope_receipt`,
  `runtime_scope_input_reference`, `runtime_scope_member`,
  `runtime_scope_operational_input`.
- **Artifact / Receipt:** content-addressed `RuntimeScopeReceipt` with
  `INCLUDED`, `EXCLUDED` and `UNKNOWN` members and exact source references.
- **Runtime caller:** bounded `continuous-research runtime-scope-*` commands and
  the shared Decision Session Kernel.
- **Downstream consumer:** Historical/Research/Shadow owner stages; consumers do
  not select a Provider.
- **Replay mechanism:** reload Policy, free Security Master and captured
  Operational Universe payloads, rebuild, compare exact receipt hash.
- **Evidence ceiling:** `EXPLORATORY`, `PIT_INCOMPLETE`, `formal_pit=false`.
  Overlapping free Provider facts are combined conservatively with all provenance.
- **Legacy replacement:** replaces operator-maintained daily symbol lists; it is
  not a second Security Master or membership Authority.

### Historical Research Journal

- **Domain / Capability:** Research / chronological multi-session execution,
  recovery and replay.
- **Classification:** bounded Runtime Journal, not the all-day Runtime or a
  business fact owner.
- **Owner:** Historical Research application context.
- **Canonical Writer:** `PostgresHistoricalResearchJournal`; business stages use
  their existing owners through `ResearchDecisionSessionKernel` and
  `PostgresHistoricalSessionOwner`.
- **Reader:** run/session/receipt/event report and deterministic replay.
- **PostgreSQL tables:** `historical_research_run`,
  `historical_research_session`, `historical_research_stage_receipt`,
  `historical_research_attempt`, `historical_research_event`.
- **Artifact / Receipt:** frozen command, session request and stage receipts for
  Scope, Decision, Strategy, Portfolio, Outcome and Performance.
- **Runtime caller:** `continuous-research historical-run`, `historical-resume`,
  `historical-report` and `historical-replay`.
- **Downstream consumer:** exploratory model research and human research review.
- **Replay mechanism:** lease/fence/CAS journal plus exact owner/hash reload;
  Decision reuse also matches calendar, scope, policy and code revision.
- **Evidence ceiling:** Historical/Shadow engineering only; blocked stages are
  valid terminal evidence and never become Formal OOS.
- **Legacy replacement:** no legacy backtest or `daily_research` writer may
  become a parallel journal or Authority.

### Multi-Strategy Runtime and business facts

- **Domain / Capability:** Strategy / stable registration, execution, Portfolio,
  Fill attribution, Path Outcome and feedback.
- **Classification:** bounded Business and Research Evidence Authority; not a
  top-level Runtime Authority and not a Production Admission owner.
- **Owner:** Multi-Strategy bounded context.
- **Canonical Writer:** `PostgresMultiStrategyRepository` through the shared
  `MultiStrategyRuntime`, cross-strategy Portfolio kernel, Fill allocation
  service, path measurement kernel and feedback service.
- **Reader:** repository exact reload/replay plus `continuous-research
  inspect-strategy`, canonical DAG, trace and metrics.
- **PostgreSQL tables:** `strategy_contract`, `strategy_version`,
  `multi_strategy_cycle`, `strategy_run`, `strategy_gate_attribution`,
  `strategy_proposal`, `cross_strategy_portfolio_decision`,
  `cross_strategy_portfolio_line`, `strategy_fill_allocation_batch`,
  `strategy_fill_allocation`, `strategy_path_outcome` and
  `strategy_feedback_artifact`.
- **Runtime caller:** one `STRATEGY_RUNTIME` child in Continuous Research and the
  `STRATEGY`/`PORTFOLIO` stages of the existing Historical Session Kernel.
- **Downstream consumer:** read-only Portfolio/Risk, Path Outcome, attribution,
  challenger and qualification projections; no broker writer.
- **Replay mechanism:** reload exact cycle payload and Strategy Version
  ID/hash set, rerun pure strategy/Portfolio kernels, and compare exact hashes.
- **Lineage enforcement:** composite PostgreSQL constraints plus transactional
  owner reload bind Proposal→Version, Fill Allocation→Proposal/Version,
  Path Outcome→Run/Version/Dataset/Decision Time/Target/Horizon, and every
  feedback source by exact ID/hash/version and non-decreasing evidence time.
- **Evidence ceiling:** deterministic engineering evidence. Free input remains
  `EXPLORATORY`/`PIT_INCOMPLETE`; qualification cannot become positive without
  Formal PIT/OOS/calibration/economics/prospective owner evidence. Caller
  booleans cannot assert those positive facts.
- **Legacy replacement:** it is the canonical multi-family Strategy seam. Older
  Strategy Shadow/Portfolio Shadow ledgers remain active compatibility and
  specialized simulation consumers until their consumer inventory permits
  deletion; they are not a second all-day runtime.

### Source freeze and Dataset

- **Domain / Capability:** Data / one bounded source-freeze and Dataset run.
- **Classification:** Business and Evidence Authority.
- **Owner:** Source Freeze data boundary inside the free-data operation.
- **Application seam:** `SourceFreezeService`; the retained `DailyLoopRunner` is an identity-compatible adapter, not Canonical research ownership.
- **Canonical Writer:** `PostgresDailyRunRepository`.
- **Reader:** Daily-run and stage-receipt repository methods.
- **Repository:** `PostgresDailyRunRepository`.
- **PostgreSQL tables:** `daily_runs`, `acquisition_stage_receipts`, `stage_receipts`.
- **Artifact / Receipt:** Daily Run, acquisition-stage receipt and Dataset-stage receipt.
- **Runtime caller:** free-data service invoked by the Continuous Dataset child.
- **Downstream consumer:** Feature materialization and State System.
- **Replay mechanism:** exact run/stage receipt reload.
- **Evidence ceiling:** source eligibility and availability carried from recorded provider evidence; no silent provider promotion.
- **Legacy replacement:** file artifacts may be compatibility Readers only and cannot write Canonical Dataset state.

### Feature materialization

- **Domain / Capability:** Feature / definition-bound materialization run and task.
- **Classification:** Business and Evidence Authority.
- **Owner:** Feature materialization bounded context.
- **Canonical Writer:** `PostgresFeatureMaterializationRunRepository`.
- **Reader:** materialization run/task/receipt repository methods.
- **Repository:** `PostgresFeatureMaterializationRunRepository`.
- **PostgreSQL tables:** `feature_materialization_run`, `feature_materialization_task`, `feature_materialization_attempt`, `feature_materialization_receipt`, `feature_materialization_event`.
- **Artifact / Receipt:** Feature Materialization Receipt with Dataset/config/code lineage.
- **Runtime caller:** Continuous Feature Materialization child.
- **Downstream consumer:** Model Governance runtime lineage, State, Candidate, Signal, Forecast and canonical Factor Extraction.
- **Replay mechanism:** run/task receipt and immutable materialization Reader.
- **Evidence ceiling:** inherits Dataset authority; computation does not improve PIT or Provider status.
- **Legacy replacement:** replaces recomputation from legacy feature files in current execution.

### Free-data Security Master and Research Universe

- **Domain / Capability:** Data / append-only BaoStock Security Master snapshot and full A-share historical research population.
- **Classification:** exploratory Evidence Authority; distinct from Daily Eligibility, bounded Operational Universe, Dynamic Pool and Candidate.
- **Owner:** Free Research Universe.
- **Canonical Writer:** `FreeResearchUniverseOperator` through `PostgresFreeResearchUniverseRepository`.
- **Reader:** snapshot/member reload, latest-as-of and replay Readers.
- **Repository:** `PostgresFreeResearchUniverseRepository`.
- **PostgreSQL tables:** `free_data_research_universe_snapshot`, `free_data_research_universe_member`.
- **Artifact / Receipt:** content-addressed Security Master raw archive/SourceManifest and `FreeResearchUniverseSnapshot`.
- **Runtime caller:** `continuous-research research-universe-sync`; archived replay uses `research-universe-replay`.
- **Downstream consumer:** research population/audit Readers; the bounded Operational Universe remains a separate capacity control.
- **Replay mechanism:** exact owner-row ID/hash reconstruction, member-projection comparison and checksum/identity verification of the immutable raw archive supplied to `research-universe-replay`.
- **Evidence ceiling:** `EXPLORATORY`, `PIT_INCOMPLETE`, `FORMAL_PIT_NOT_ESTABLISHED`; unknown listing facts remain `UNKNOWN` and are never silently included or discarded.
- **Legacy replacement:** no listing-date or current-status heuristic may write Daily Eligibility or Formal PIT facts.

### Longitudinal Historical data and materialization

- **Domain / Capability:** Historical Data / effective-dated constituent
  timeline, business facts, partitioned corpus and Decision/Outcome
  projections.
- **Classification:** exploratory Evidence Authority plus derived immutable
  projections; none establishes Formal PIT.
- **Owner:** Free Research Universe owns constituent cohorts and the exact
  session timeline; Historical Security Facts owns Industry, published shares,
  corporate actions, unresolved gaps and the exact acquisition symbol/date/
  Universe scope; Historical Corpus owns raw/normalized packages and partition
  locators; the Historical Context Instrument Set owns the frozen
  `000300.SH` market-index and `510300.SH` theme-ETF roles; Historical
  Experiment Definition freezes the unchanged methodology before Scope;
  Historical Materialization owns session components and projected Outcome
  labels.
- **Canonical Writer:** `FreeResearchUniverseOperator`,
  `HistoricalSecurityFactsOperator`, the longitudinal corpus CLI through
  `PostgresResearchValidationRepository`,
  `PostgresHistoricalCorpusRepository` and
  `PostgresHistoricalMaterializationRepository` through the single Historical
  Decision materializer. Context changes require a new frozen Experiment.
- **PostgreSQL tables:** `free_data_historical_constituent_timeline`,
  `free_data_historical_constituent_timeline_cohort`,
  `free_data_historical_security_fact_set`,
  `free_data_historical_security_fact`,
  `free_data_historical_security_fact_coverage_gap`,
  `research_validation_artifact` (`HISTORICAL_CONTEXT_INSTRUMENT_SET` and
  `RESEARCH_EXPERIMENT_DEFINITION`),
  `historical_corpus_owner`, `historical_corpus_partition`,
  `historical_corpus_session_component`,
  `historical_corpus_component_source_binding` and
  `historical_corpus_outcome_label`.
- **Replay mechanism:** exact owner ID/hash and immutable Artifact Root checksum
  reload, exact session-to-cohort mapping, keyset component iteration and
  deterministic projected-label reconstruction.
- **Evidence ceiling:** `EXPLORATORY`, `PIT_INCOMPLETE`,
  `FORMAL_OOS=false`, `CALIBRATED=false`; corporate-action absence is usable
  only inside the persisted v4 acquisition scope and all gaps fail raw returns
  closed.

### Formal PIT

- **Domain / Capability:** Data governance / source qualification, bitemporal facts and as-of validation.
- **Classification:** Evidence Authority.
- **Owner:** PIT Authority.
- **Canonical Writer:** `PostgresPITAuthority` for source/fact/PIT evidence and `PostgresProviderFactQualificationAuthority` for Provider×Contract×Fact decisions.
- **Reader:** PIT source/fact/snapshot/evidence reload and replay methods.
- **Repository:** `PostgresPITAuthority`.
- **PostgreSQL tables:** existing PIT tables plus `provider_fact_qualification_policy`, `provider_fact_qualification_decision` and its idempotency command owner.
- **Artifact / Receipt:** Source Qualification, PIT Fact Revision, as-of Snapshot and Formal PIT Validation Evidence.
- **Runtime caller:** `pit-authority` and the Model Governance PIT bridge.
- **Downstream consumer:** formal research preparation and Model Governance `FORMAL_PIT` evidence.
- **Replay mechanism:** exact Provider decision, typed source evidence, bitemporal snapshot and validation-evidence reload.
- **Evidence ceiling:** mechanics exist; current free Provider scopes are explicitly `REJECTED`, and no qualified real archive is established.
- **Legacy replacement:** replaces reference-kind-only PIT claims; exploratory provider adapters remain non-formal.

### Model Registry and Governance

- **Domain / Capability:** Platform / model lifecycle, purpose-scoped qualification, assignment and selection.
- **Classification:** Business Authority and Policy owner.
- **Owner:** Model Governance; Registry history is subordinate in the same PostgreSQL boundary.
- **Canonical Writer:** `PostgresModelGovernanceRepository`.
- **Reader:** model inspection, qualification, assignment and selection-receipt replay/export methods, plus the typed Formal Research lineage resolver that freezes lifecycle, Registry version and Registry/Lineage governance actions.
- **Repository:** `PostgresModelGovernanceRepository`.
- **PostgreSQL tables:** `governance_commands`, `model_registrations`, `model_lifecycle_transitions`, `model_governance_action`, `model_version_lineage`, `model_qualification_evidence`, `model_governance_policy`, `model_qualification_decision`, `model_runtime_lineage`, `model_runtime_assignment`, `model_selection_receipt`.
- **Artifact / Receipt:** Model Version Lineage, Formal Research Model Lineage Resolution, Qualification Decision, Runtime Assignment and Model Selection Receipt.
- **Runtime caller:** State/Signal/Forecast selectors and Decision System.
- **Downstream consumer:** State, Candidate, Signal, Forecast, Decision stages and audit/replay Readers.
- **Replay mechanism:** governance-revision-bound receipt replay/export; terminal lifecycle state fails Formal Protocol freeze and later owner replay.
- **Evidence ceiling:** Research/Backtest/Shadow qualification is runtime eligibility only; Production qualification is forced closed.
- **Legacy replacement:** one PostgreSQL owner replaces registry/selector decisions assembled from caller DTOs.

### State and StateSeries

- **Domain / Capability:** Research State / Market, ETF, Theme, Capital states and cross-session series.
- **Classification:** Business Authority.
- **Owner:** State System.
- **Canonical Writer:** `PostgresStateSystemRepository`.
- **Reader:** typed State, current pointer, StateSeries head and stage-authority Readers.
- **Repository:** `PostgresStateSystemRepository`.
- **PostgreSQL tables:** typed observation/state/transition tables, `state_current_pointer`, `state_policy_authority`, `state_series`, `state_series_link`, `state_series_head`, `state_runtime_receipt`, `state_research_stage_authority`.
- **Artifact / Receipt:** typed State artifacts, StateSeries head and State Runtime Receipt.
- **Runtime caller:** Continuous State System child.
- **Downstream consumer:** Pool, Candidate, Research Summary, Controlled Operation and Decision System.
- **Replay mechanism:** typed State/stage receipt reload and CAS-protected series traversal.
- **Evidence ceiling:** research state only; it grants neither Entry nor Position authority.
- **Legacy replacement:** Canonical PostgreSQL stages replace legacy state recomputation in current execution.

### Dynamic Pool and Candidate

- **Domain / Capability:** Research selection / tradable research pool and candidate discovery.
- **Classification:** Business Authority inside State System.
- **Owner:** State System Pool/Candidate stages.
- **Canonical Writer:** `PostgresStateSystemRepository`.
- **Reader:** dynamic-pool, member/change, candidate-artifact and stage-authority Readers.
- **Repository:** `PostgresStateSystemRepository`.
- **PostgreSQL tables:** `dynamic_stock_pool`, `dynamic_stock_pool_member`, `dynamic_stock_pool_change`, `state_runtime_candidate_artifact`, `state_research_stage_authority`.
- **Artifact / Receipt:** Pool artifact, Candidate artifact and exact scoped stage bundle.
- **Runtime caller:** ordered State System pipeline.
- **Downstream consumer:** Signal, Forecast, Research Summary and research evaluation.
- **Replay mechanism:** pool/change and candidate stage receipt reload.
- **Evidence ceiling:** Candidate is research output, not Signal, recommendation, Entry or Position.
- **Legacy replacement:** legacy candidate adapters are explicit migration/research boundaries only.

### Controlled decision-time operation, Signal and Forecast

- **Domain / Capability:** Application / bounded decision-window acquisition and calculation.
- **Classification:** Runtime Authority for one window; Signal/Forecast are research artifacts.
- **Owner:** Controlled Operation.
- **Canonical Writer:** `PostgresDecisionTimeOperationJournal`; Signal and Forecast are written through its governed stage composition.
- **Reader:** operation run/stage/attempt/receipt/event Readers and evidence-package replay.
- **Repository:** `PostgresDecisionTimeOperationJournal` plus bounded artifact repositories.
- **PostgreSQL tables:** `controlled_operation_run`, `controlled_operation_stage`, `controlled_operation_attempt`, `controlled_operation_receipt`, `controlled_operation_child_run`, `controlled_operation_event`.
- **Artifact / Receipt:** Controlled Operation Receipt, minute evidence, Signal Artifact and uncalibrated PathForecast.
- **Runtime caller:** Continuous Controlled Operation child.
- **Downstream consumer:** optional Canonical Lifecycle and Research Summary.
- **Replay mechanism:** operation/package/stage receipt replay.
- **Evidence ceiling:** Research/Shadow; PathForecast is explicitly uncalibrated and no Entry authority follows.
- **Legacy replacement:** old Signal/Entry producers cannot enter Canonical composition.

### Canonical Lifecycle

- **Domain / Capability:** Application / recoverable research-to-manual lifecycle orchestration.
- **Classification:** Bounded Runtime, not the all-day Runtime or a business owner.
- **Owner:** Canonical Lifecycle application context.
- **Canonical Writer:** `PostgresLifecycleRunRepository` for lifecycle state; domain stages call their own owners.
- **Reader:** lifecycle run/stage/attempt/receipt/event Readers.
- **Repository:** `PostgresLifecycleRunRepository`.
- **PostgreSQL tables:** `lifecycle_runs`, `lifecycle_stages`, `lifecycle_attempts`, `lifecycle_stage_receipts`, `lifecycle_events`.
- **Artifact / Receipt:** Lifecycle Run and Stage Receipt.
- **Runtime caller:** optional child of Controlled Operation or explicit operator invocation.
- **Downstream consumer:** Opportunity/Thesis, Portfolio/Risk and manual workflow projections.
- **Replay mechanism:** durable lifecycle stage replay.
- **Evidence ceiling:** human-in-the-loop decision support; no automatic execution.
- **Executable boundary:** Research Decision Support and Manual Account Observation are PostgreSQL-composed. Holding/Exit/Outcome Position Review identities are contract-only and fail closed.
- **Legacy replacement:** Legacy lifecycle producers are excluded from the current composition.

### Research Summary

- **Domain / Capability:** Decision support / daily research summary projection.
- **Classification:** Read Model / Projection.
- **Owner:** Decision System research-summary sub-boundary.
- **Canonical Writer:** `PostgresDecisionSystemRepository` research-summary methods.
- **Reader:** research-summary and stage Readers.
- **Repository:** `PostgresDecisionSystemRepository`.
- **PostgreSQL tables:** `research_daily_summary`, `research_summary_stage`.
- **Artifact / Receipt:** `ResearchDailySummary` and stage rows.
- **Runtime caller:** final Continuous Research Summary child.
- **Downstream consumer:** Research Shadow and human research review.
- **Replay mechanism:** immutable summary/stage reload.
- **Evidence ceiling:** Research/Shadow; receipt IDs do not authorize Production.
- **Legacy replacement:** `daily_research` V1 remains compatibility Reader/identity only.

### Manual-account Decision System

- **Domain / Capability:** Decision support / account observation, reconciliation, proposal and independent Risk.
- **Classification:** Business Authority for decision-support records; proposal remains non-executing.
- **Owner:** Decision System.
- **Canonical Writer:** `PostgresDecisionSystemRepository`.
- **Reader:** observation, reconciliation, summary, proposal, Risk and runtime-receipt Readers.
- **Repository:** `PostgresDecisionSystemRepository`.
- **PostgreSQL tables:** `manual_account_observation`, `manual_position_observation`, `account_reconciliation`, `reconciliation_difference`, `daily_decision_summary`, `daily_summary_candidate`, `research_portfolio_proposal`, `research_portfolio_line`, `independent_risk_decision`, `decision_runtime_receipt`, configuration/evidence tables.
- **Artifact / Receipt:** Manual Account Observation, Reconciliation, Daily Decision Summary, Portfolio Proposal, Independent Risk Decision and Decision Runtime Receipt.
- **Runtime caller:** `decision-system` CLI and optional Continuous Decision child.
- **Downstream consumer:** human decision review and audit Readers.
- **Replay mechanism:** individual repository Readers; no composed full Decision replay remains.
- **Evidence ceiling:** Production Decision is blocked by Model Governance; no Order/Fill mutation.
- **Legacy replacement:** uncomposed pseudo-Production replay and its fixture seeder were removed.

### Opportunity and Thesis

- **Domain / Capability:** Decision / opportunity and thesis lifecycle.
- **Classification:** Business Authority.
- **Owner:** Decision Lifecycle.
- **Canonical Writer:** `PostgresDecisionLifecycleRepository`.
- **Reader:** opportunity/thesis aggregate and event Readers.
- **Repository:** `PostgresDecisionLifecycleRepository`.
- **PostgreSQL tables:** `decision_commands`, `trading_opportunities`, `opportunity_events`, `trading_theses`, `thesis_events`.
- **Artifact / Receipt:** Trading Opportunity and Trading Thesis aggregates/events.
- **Runtime caller:** Canonical Lifecycle decision stages.
- **Downstream consumer:** Portfolio/Risk and human review.
- **Replay mechanism:** append-only event restoration.
- **Evidence ceiling:** proposal/thesis only; neither creates actual Position.
- **Legacy replacement:** old recommendation objects do not write these aggregates.

### Portfolio and Risk

- **Domain / Capability:** Portfolio / portfolio decision, complete-account risk and risk-reduction route.
- **Classification:** Business Authority and independent safety gate.
- **Owner:** Portfolio/Risk bounded contexts.
- **Canonical Writer:** PostgreSQL portfolio, complete-account and risk-route repositories.
- **Reader:** decision/snapshot/Risk and route Readers with independent Risk reload.
- **Repository:** `PostgresPortfolioDecisionRepository`, `PostgresCompleteAccountPortfolioRiskRepository`, `PostgresRiskRouteRepository`.
- **PostgreSQL tables:** `portfolio_risk_commands`, `portfolio_decisions`, `risk_decisions`, `complete_account_risk_commands`, `authoritative_account_portfolio_snapshots`, `complete_account_portfolio_decisions`, `complete_account_risk_decisions`, risk-route tables.
- **Artifact / Receipt:** Portfolio Decision, complete-account Snapshot/Decision and Risk Decision.
- **Runtime caller:** Canonical Lifecycle and Decision System.
- **Downstream consumer:** human manual-intent workflow; Risk rejection terminates the route.
- **Replay mechanism:** immutable decision/snapshot Readers and event history.
- **Evidence ceiling:** decision support; strategy code cannot bypass Risk rejection.
- **Legacy replacement:** legacy target positions never become actual holdings.

### Manual execution and actual Position

- **Domain / Capability:** Execution and Position / observed manual records and fill-derived books.
- **Classification:** Business Authority for actual execution facts and Position state.
- **Owner:** Manual Execution and Position Book bounded contexts.
- **Canonical Writer:** PostgreSQL manual execution, traceability and Position Book repositories.
- **Reader:** manual record/fill, traceability and Position Book Readers.
- **Repository:** `PostgresManualExecutionRepository`, `PostgresTraceableManualExecutionRepository` and Position Book repository.
- **PostgreSQL tables:** `execution_commands`, `manual_trade_records`, `manual_trade_events`, `manual_fills`, `position_books`, `position_book_events`, `traceable_manual_trade_bindings`.
- **Artifact / Receipt:** Manual Trade Record, observed Fill and fill-derived Position Book event/snapshot.
- **Runtime caller:** explicit human record/import only.
- **Downstream consumer:** reconciliation, complete-account Portfolio/Risk, Holding and Exit assessment.
- **Replay mechanism:** append-only manual ledger and Position Book event replay.
- **Evidence ceiling:** actual Position comes only from observed Fill; no broker writer exists.
- **Legacy replacement:** legacy recommendation/Entry state cannot create a Position.

### Research Shadow

- **Domain / Capability:** Shadow Research / frozen daily research decision.
- **Classification:** Research Evidence Authority.
- **Owner:** Shadow Research.
- **Canonical Writer:** `PostgresShadowResearchRepository`.
- **Reader:** session, decision, state-policy and event Readers.
- **Repository:** `PostgresShadowResearchRepository`.
- **PostgreSQL tables:** `shadow_research_session`, `shadow_research_decision`, `shadow_research_decision_state_policy`, `shadow_research_event`.
- **Artifact / Receipt:** Shadow Research Session and frozen Shadow Decision.
- **Runtime caller:** `research-shadow` CLI.
- **Downstream consumer:** Outcome/Target settlement, Panel and research validation.
- **Replay mechanism:** session/decision/event replay.
- **Evidence ceiling:** frozen research decision only; it does not simulate or mutate an account.
- **Legacy replacement:** replaces ad-hoc prospective observation records in current research flow.

### Outcome, Target and prospective attestation

- **Domain / Capability:** Research Evaluation / target protocol and factual outcome settlement.
- **Classification:** Evidence Authority.
- **Owner:** Outcome Target and prospective settlement bounded contexts.
- **Canonical Writer:** PostgreSQL target/outcome/attestation repositories.
- **Reader:** target, targeted outcome, settlement and attestation Readers.
- **Repository:** target/outcome repositories used by `application/research_evaluation` and Shadow Research.
- **PostgreSQL tables:** `outcome_target_protocol`, `outcome_target_definition`, `targeted_shadow_outcome`, `targeted_shadow_outcome_label`, `prospective_outcome_settlement`, `prospective_evidence_attestation`.
- **Artifact / Receipt:** Target Protocol/Definition, Targeted Shadow Outcome, Prospective Settlement and Attestation.
- **Runtime caller:** later checkpoint acquisition and settlement workflows.
- **Downstream consumer:** Evaluation Dataset, Panel, calibration/evaluation harnesses and Strategy Shadow qualification assessment.
- **Replay mechanism:** immutable target/outcome/settlement/attestation reload.
- **Evidence ceiling:** factual outcome mechanics exist; current attestation remains `prospective_proven=false`.
- **Legacy replacement:** legacy diagnostic outcome files are research inputs only, not this factual owner.

### Evaluation Dataset, Panel and Factor Extraction

- **Domain / Capability:** Research Evaluation / immutable sample assembly and canonical feature extraction.
- **Classification:** Evidence assembly and Read Model.
- **Owner:** Research Evaluation.
- **Canonical Writer:** PostgreSQL evaluation-dataset and Panel repositories; Factor Extraction emits enrichment through Research Validation repository.
- **Reader:** Dataset, settlement, Panel row/slice and canonical feature Readers.
- **Repository:** Research Evaluation repositories plus `PostgresResearchValidationRepository` for enrichment.
- **PostgreSQL tables:** `research_evaluation_dataset`, `research_evaluation_dataset_settlement`, `research_evaluation_panel_v2`, `research_evaluation_panel_slice_v2`, `research_evaluation_panel_row_v2`, `research_panel_factor_exposure`.
- **Artifact / Receipt:** Evaluation Dataset, Research Panel V2 and Panel Enrichment.
- **Runtime caller:** separately invoked research evaluation workflow.
- **Downstream consumer:** ablation, calibration, formal-evaluation harness, Entry research and Holding/Exit evaluation.
- **Replay mechanism:** immutable Dataset/Panel/enrichment Readers.
- **Evidence ceiling:** assembly does not itself establish Alpha, Formal OOS or qualification.
- **Legacy replacement:** Panel V2 is current; duplicate enrichment/recalculation paths are not Canonical.

### Research Validation

- **Domain / Capability:** Research Validation / ablation, liquidity/capacity, historical sample, calibration, formal evaluation, Entry and Holding/Exit evidence.
- **Classification:** Research Harness plus narrow owner-resolved qualification Authorities.
- **Owner:** Research Validation.
- **Canonical Writer:** `PostgresResearchValidationRepository` for engineering artifacts; Formal Protocol/Forecast, Historical/family-OOS, Calibration and Phase C gate repositories own only their respective facts and decisions.
- **Reader:** payload, factor exposure and historical-sample Readers.
- **Repository:** `PostgresResearchValidationRepository`.
- **PostgreSQL tables:** the engineering tables plus `formal_research_protocol*`, `formal_forecast_computation_*`, `formal_locked_oos_roster*`, PIT Universe projections/bindings, `research_model_*`, `research_runtime_scope*`, `historical_research_*`, `frozen_hypothesis_family*`, Locked-OOS consumption, observation/performance, Historical/OOS decision, Calibration qualification/binding and `phase_c_stage_decision` tables.
- **Artifact / Receipt:** engineering Validation artifacts, owner-computed Forecast receipt, Frozen Hypothesis Family, Historical Sample Dataset, family Evaluation result, Calibration artifact and Entry/Holding evidence.
- **Runtime caller:** `continuous-research settle-day` automatically invokes the PostgreSQL PathForecast calibration bridge after Panel enrichment; offline harnesses remain available for method-level research.
- **Downstream consumer:** human research review, C6/C7 gates and persisted Production Admission floor resolution.
- **Replay mechanism:** immutable typed Target/Evaluation/component reload, metadata-only C3 pre-OOS resolution, full Frozen Calendar payload/date replay, deterministic measure Forecast recomputation, label-value-blind complete Locked roster freeze with exact PIT Universe membership and Dataset lineage, restartable Historical Session replay, durable pre-read raw/Target consumption, Target-observation and family-multiplicity replay, mandatory Train/Validation readiness before Locked OOS, exact Calibration partitions and Entry→Outcome replay. Pre-057 Protocols and migration-027 Registry action envelopes remain replay-only. Bare caller references or submitted Forecast values cannot establish a positive decision.
- **Evidence ceiling:** migration 046 remains unchanged; later owner writers can only satisfy a gate from exact upstream owner evidence. Current upstream evidence is absent.
- **Legacy replacement:** five reference-only promotion helpers and their generic Governance binding DTO were deleted.

### Exploratory Model Research and Formal assessment

- **Domain / Capability:** Research Validation / deterministic exploratory
  training, inference and ordered Formal predecessor assessment.
- **Classification:** Research artifact owner plus fail-closed qualification
  orchestration; neither grants Production Authority.
- **Owner:** Research Validation.
- **Canonical Writer:** `PostgresResearchModelRepository` for exploratory
  artifacts/receipts and `PostgresFormalExecutionRepository` for assessments.
- **Reader:** model/assessment report and exact deterministic replay.
- **PostgreSQL tables:** `research_model_training_*`,
  `research_model_walk_forward_fold`, `research_model_artifact`,
  `research_model_candidate_diagnostic`, `research_model_coefficient_head`,
  `research_model_inference_*`, `formal_execution_request`,
  `formal_execution_provider_requirement`, `formal_execution_assessment`,
  `formal_execution_stage_assessment`, `formal_execution_source_binding`.
- **Artifact / Receipt:** immutable research challenger, walk-forward diagnostics,
  inference receipt and ordered Formal Execution assessment.
- **Runtime caller:** bounded `continuous-research model-*` and
  `formal-execution-*` commands.
- **Downstream consumer:** Historical/Daily Shadow research and Formal gap
  reporting; the Formal Forecast owner remains separately governed.
- **Replay mechanism:** restore exact samples/features/targets/folds/coefficients
  or exact qualification predecessors and compare canonical identities.
- **Evidence ceiling:** `RESEARCH_MODEL_AVAILABLE=true` only for a stored valid
  artifact; `FORMAL_MODEL_QUALIFIED=false`, `FORMAL_OOS=false`,
  `CALIBRATED=false`. The assessment stops before OOS/calibration when Provider
  Fact or PIT qualification is missing.
- **Legacy replacement:** no caller-submitted score or generic evidence DTO can
  qualify a model or unlock OOS.

### Strategy Shadow

- **Domain / Capability:** Strategy Shadow / simulated Entry, Fill, Position, Portfolio, Holding and Exit.
- **Classification:** isolated Research Harness and simulated ledger.
- **Owner:** Strategy Shadow.
- **Canonical Writer:** `PostgresStrategyShadowRepository` for single-trade
  sessions, `PostgresShadowPortfolioRepository` for Portfolio Shadow,
  `PostgresShadowObservationRepository` for owner-resolved inputs and
  `PostgresPortfolioPerformanceRepository` for Performance/Attribution.
- **Reader:** session, event, artifact and Portfolio day-state Readers plus deterministic replay.
- **Repository:** `PostgresStrategyShadowRepository`, `PostgresShadowPortfolioRepository`.
- **PostgreSQL tables:** `strategy_shadow_policy_authority`,
  `strategy_shadow_session`, `strategy_shadow_session_lineage_binding`,
  `strategy_shadow_event`, `strategy_shadow_artifact`,
  `strategy_shadow_portfolio`, `strategy_shadow_portfolio_day`,
  `strategy_shadow_portfolio_state_source_binding`, `shadow_observation_*`,
  `shadow_performance_*`, prospective qualification policy and stage decision.
- **Artifact / Receipt:** Strategy Shadow Session/Event, provenance-complete
  Observation, simulated Entry/Fill/Position/Holding/Exit artifacts, Portfolio
  Policy/CAS-linked day states and immutable Performance report.
- **Runtime caller:** thin subcommands of the installed `continuous-research` CLI; no second Runtime.
- **Downstream consumer:** Holding/Exit engineering evaluation and Production Admission gap projection.
- **Replay mechanism:** reusable Policy owner plus exact artifact ID/hash source
  binding, durable Observation Receipt lineage, CAS session/event/artifact,
  typed Strategy/Portfolio/Outcome chain and exact Performance state-set replay;
  prospective proof counts only post-policy-lock live sessions.
- **Evidence ceiling:** simulated only; no actual Fill, Position or broker mutation.
- **Legacy replacement:** no legacy trading simulator may write actual Position Authority.

### Engineering Access Governance

- **Domain / Capability:** Principal, Role, Permission, engineering Approval and Audit.
- **Classification:** PostgreSQL Authority for engineering access facts; external authentication remains unbound.
- **Owner:** Access Governance.
- **Canonical Writer:** `PostgresAccessGovernance`.
- **Reader:** current Principal status/Role authorization and append-only Audit readers.
- **Repository:** `PostgresAccessGovernance`.
- **PostgreSQL tables:** `security_principal`, `security_principal_status_event`, `security_role_event`, `security_approval`, `security_approval_decision`, `security_audit_event`, `security_governance_command`.
- **Artifact / Receipt:** content-addressed Principal, Role event, Approval and Approval Decision.
- **Runtime caller:** `model-governance access-*` manages facts; every `continuous-research` command requires an active `--principal-id`, binds an exact operation resource and writes an allowed/denied audit event. Formal command `actor` must equal that principal. Non-Admin Shadow/recovery mutation also consumes an exact approved `--approval-decision-id`.
- **Replay mechanism:** append-only status/role chains and idempotent command receipts.
- **Evidence ceiling:** the caller-supplied Principal ID is role-authorized but not externally authenticated; there is no Production Admission permission, Broker permission or trading authority.

### Production Admission

- **Domain / Capability:** Production governance / admission-floor visibility.
- **Classification:** persisted fail-closed Admission decision Authority; it is not Broker authority.
- **Owner:** Phase C Production Admission floor resolver.
- **Canonical Writer:** `PostgresPhaseCGateAuthority`, which re-reads every owner and can currently persist only `BLOCKED`.
- **Reader:** immutable PostgreSQL decision replay.
- **Repository:** `PostgresPhaseCGateAuthority`.
- **PostgreSQL tables:** `production_admission_decision_authority`, `phase_c_gate_command`.
- **Artifact / Receipt:** `ProductionAdmissionDecision` with status `BLOCKED`; no authorization receipt.
- **Runtime caller:** `continuous-research qualification-status`; not part of a trading tick.
- **Downstream consumer:** engineering gap/status reporting only.
- **Replay mechanism:** immutable exact-floor payload restoration and revision/supersession chain.
- **Evidence ceiling:** always blocked; engineering RBAC exists, but authenticated operator, Formal evidence and broker readiness owners do not. Caller-supplied approval references cannot promote a floor.
- **Legacy replacement:** removes reference-only `ELIGIBLE_FOR_OPERATOR_REVIEW` and `AUTHORIZED` projections.

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
| `PIT_ELIGIBLE` historical sample | Owner writer exists; it reloads Protocol/PIT/Target/Provider evidence. Current evidence is missing, so no transition exists. |
| `OOS_ELIGIBLE` / Formal OOS | Owner writer replays frozen observations/calendar/metrics. Current qualified sample/PIT evidence is missing. |
| `CALIBRATED` | Owner writer replays exact partitions and metrics. Current Formal OOS evidence is missing, so `calibrated=false`. |
| `ENTRY_QUALIFIED` | C6 owner replays formal Entry/Strategy Outcome/economic/provenance/approval evidence. Current upstream evidence is missing. |
| `HOLDING_EXIT_VALIDATED` | Same C6 owner evaluates independent rule coverage and outcome floors; current state is false. |
| `STRATEGY_SHADOW_PROVEN` | C7 owner requires live Runtime Authority, acquisition receipt, attestation, complete T+1 factual Outcome, Strategy Outcome and Portfolio day; no qualifying post-lock window has accumulated. |
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
