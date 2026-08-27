# WP-ARCHITECTURE-REFOUNDATION-01 Capability Preservation Matrix

> **Status:** CANONICAL_TARGET_ARCHITECTURE
> **Authority:** Design-checkpoint capability-to-target traceability; not implementation or proof status
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-27
> **Starting Main:** `0382dad416d6d50d1eea0bda1603d7c359d65274`
> **Code Evidence:** `src/market_regime_alpha`, `src/market_regime_alpha/persistence/postgres/migrations/*.sql`, `tests`

This matrix was recovered from executable call chains, repositories, SQL, and
tests. It prevents structural deletion from silently deleting a business
capability. It does not claim the target exists or that any research capability
is qualified.

Disposition vocabulary:

- **PRESERVE/REDESIGN** — capability remains, Authority and model change.
- **PRESERVE/DERIVE** — capability remains as a query/read model, not a writer.
- **PRESERVE/CONSOLIDATE** — several current paths converge on one target owner.
- **DELETE ABSTRACTION** — named current wrapper/table is removed while the
  mapped capability/invariant remains.

| Capability | Current executable evidence / persistence | Target Domain and owner | Target command/query and Runtime placement | Target persistence | Disposition | Preservation invariant / implementation acceptance |
|---|---|---|---|---|---|---|
| **Market** | `data/*`, `market_data/*`, PIT and historical-corpus repositories; captures/facts/calendar/reference spread across `pit_*`, `free_data_historical_*`, `historical_corpus_*` | Market & PIT: Capture, Instrument, Session, Fact Revision, Source Gap | `CaptureMarketData` → `NormalizeMarketFacts`; CAPTURE/NORMALIZE_PIT Steps; exact/as-of queries | `provider` through `source_gap` Market catalog | **PRESERVE/CONSOLIDATE** | Raw bytes, provider/request, event/session/provider/capture/known/visible times, basis, revision, gaps and hashes remain exact; no provider substitution |
| **Regime** | State System market state calculator/repository; `market_regime_state_observation/state/transition` plus generic state series | Decision Support Context Assessment kind `MARKET_REGIME` | `AssessContext` after Candidate inputs are frozen; current/transition are queries | `context_assessment`, `context_metric` | **PRESERVE/REDESIGN** | Inferred state is distinct from Market fact; exact input/model evidence; unknown remains explicit; no state/current/transition triple writers |
| **ETF** | ETF rotation state code/tables and `etf_theme_reference_snapshot` | Market classification/instruments + Context kind `ETF_ROTATION` | Market membership as-of query; `AssessContext` | `instrument`, `classification*`, `context_assessment/metric` | **PRESERVE/CONSOLIDATE** | ETF identity/membership is PIT; rotation is inference; current constituent list cannot reconstruct history |
| **Theme** | Theme rotation state code/tables and reference snapshot | Market classification membership + Context kind `THEME_ROTATION` | same Context command with theme-specific policy/version | `classification*`, `context_assessment/metric` | **PRESERVE/CONSOLIDATE** | Theme taxonomy revision and membership visibility are retained separately from inferred state |
| **Capital** | Capital evolution/state code; `capital_state_observation/state/transition` | Context kind `CAPITAL_PROXY` | `AssessContext` with explicit proxy definition | `context_assessment`, `context_metric`, source Evidence | **PRESERVE/REDESIGN** | Public proxies stay labelled proxies; never claim hidden institutional intent/raw capital fact; missing source → unknown |
| **Universe** | `universe/*`, Runtime Scope, free-data universe and historical membership/timeline projections | Universe & Eligibility: Universe, Revision, Member | `FreezeUniverse` in FREEZE_UNIVERSE Step; exact/as-of scope query | `universe`, `universe_revision`, `universe_member` | **PRESERVE/CONSOLIDATE** | All included/excluded/unknown members accounted; exact classification/lifecycle/source visibility; no current membership backfill |
| **Eligibility** | Candidate eligibility/funnel logic in State/Strategy/Historical paths; reasons spread through payloads/gates | Universe & Eligibility: Eligibility Policy/Rule/Assessment/Reason | `RegisterEligibilityPolicy`; `AssessEligibility` for every scoped instrument | `eligibility_policy`, `eligibility_rule`, `eligibility_assessment`, `eligibility_reason` | **PRESERVE/REDESIGN** | Per-instrument Decision-time evidence and criterion reasons are typed and FK-bound to rules; `UNKNOWN` differs from `INELIGIBLE`; no silent filtering/JSON |
| **Candidate** | `candidates/*`, candidate discovery, state candidate artifact, daily summary candidate, Strategy proposals | Universe & Eligibility: Candidate Policy/Component/Set/Candidate/Score Component | `RegisterCandidatePolicy`; `BuildCandidateSet` after Eligibility; Candidate dossier query | `candidate_policy`, `candidate_policy_component`, `candidate_set`, `candidate`, `candidate_score_component` | **PRESERVE/CONSOLIDATE** | Candidate requires matching eligible assessment; full funnel/counts/ties/components/evidence; empty set valid; Candidate ≠ Signal/Entry |
| **Signal** | `signals/*`, state/research summaries and Strategy inputs | Decision Support: Signal | `ProduceSignal` in SIGNAL_AND_FORECAST Step | `signal` | **PRESERVE/REDESIGN** | Exact Candidate/Decision/input/version/status lineage; missing is explicit; score is not probability |
| **Forecast** | `forecasting/*`, outcome-target-bound forecast/estimate, research-model inference receipts | Decision Support: Forecast/Estimate; Research owns Model/Target | `ProduceForecast` with exact Target/Model; query by Decision/Target | `forecast`, `forecast_estimate` with `target_*`/`model_version` FKs | **PRESERVE/CONSOLIDATE** | Target/checkpoint binding, uncertainty, calibration status and availability explicit; no generic forecast payload or target-free probability |
| **Opportunity** | `trading_opportunities/opportunity_events` and Strategy opportunity/source-binding tables | Decision Support: Opportunity | `CreateOpportunity` reloads Candidate/Signal/Forecast/Context/Strategy and exact input Evidence; no Risk authorization | `opportunity` | **PRESERVE/CONSOLIDATE** | One exact Decision-time bundle; Forecast-required contract fails closed; Opportunity cannot authorize Risk or create Fill/Position |
| **Thesis** | `trading_theses/thesis_events` and thesis-health command/observation tables | Decision Support: Thesis/Condition | `Create/ReviseThesis`; condition observation query feeds new Strategy action | `thesis`, `thesis_condition` | **PRESERVE/REDESIGN** | Immutable falsifiable revisions; entry/hold/invalidation/reduce/exit are distinct; notes are not mutable Authority |
| **Strategy** *(additional protected capability)* | `strategies/*`, strategy contract/version/run/gate/proposal and Strategy Shadow paths | Decision Support: Strategy/Version | `RegisterStrategyVersion`; Strategy action inside Decision Run | `strategy`, `strategy_version`; actions bind Opportunity/Proposal | **PRESERVE/CONSOLIDATE** | Stable version identity, explicit Forecast contract and terminal action for every input; no parallel Strategy Shadow Authority |
| **Portfolio** | portfolio decisions, complete-account portfolio, research portfolio, cross-strategy and Strategy Shadow portfolio tables | Decision Support: Portfolio Policy/Proposal/Line | `ProposePortfolio`; account/Position stays a downstream Risk query | `portfolio_policy`, `portfolio_proposal`, `portfolio_line` | **PRESERVE/CONSOLIDATE** | Complete allocation/count/weight/cash constraints; Proposal never mutates account/Position; simulation is an evaluation artifact |
| **Risk** | risk decisions/commands, complete-account and independent/pre-strategy/risk-reduction paths | Decision Support: Risk Policy/Rule/Decision/Reason | `RegisterRiskPolicy`; `AssessRisk` after Portfolio; exact account/market query and locks | `risk_policy`, `risk_rule`, `risk_decision`, `risk_reason` | **PRESERVE/CONSOLIDATE** | One pre-execution risk owner; results FK to exact typed limits/evidence; rejection cannot be bypassed; unknown fails closed |
| **Execution** | `execution/*`, manual trade/fill, risk-reduction/manual-binding tables | Execution & Account: Intent, Fill, Fill Allocation | human `ApproveExecutionIntent`; `RecordObservedFill/CorrectFill/AllocateFill` | `execution_intent`, `fill`, `fill_allocation` | **PRESERVE/REDESIGN** | Intent ≠ Fill; command capacity/idempotency and account locks; partial/late/corrected fills append and reconcile |
| **Position** *(additional protected capability)* | `position/authority.py`, position book/event, manual account/position observation | Execution & Account query owner | `current_position`/sleeve query; typed `RecordPositionBasisEvent` only for non-trade exceptions | `account_authority_epoch`, `position_basis_event`; view over `fill` | **PRESERVE/DERIVE** | Trade delta only observed effective Fill; opening/corporate action/reconciliation rules explicit; broker observation cannot mutate |
| **Outcome** | targeted/prospective/strategy/path/realized/historical labels and settlements | Outcome & Attribution: Outcome, Observation, Metric, Reason | `SettleOutcome` after source availability; OUTCOME Step/query | `outcome`, `outcome_observation`, `outcome_metric`, `outcome_reason` | **PRESERVE/CONSOLIDATE** | Decision reference, path and each metric status independent; exact Target/checkpoint/source lineage; MFE/MAE unavailable rules; no zero-fill |
| **Attribution** | shadow performance attribution/metrics/returns, strategy gate attribution, evaluation factor exposure | Outcome & Attribution: Attribution Run/Line | `RunAttribution` on exact Outcome/Fill allocation; query-only reports | `attribution_run`, `attribution_line` | **PRESERVE/CONSOLIDATE** | Declared dimensions and total reconciliation; missing denominator → `NOT_ESTIMABLE`; no residual balancing/causal overclaim |
| **Research** | historical corpus/research, panels, datasets, experiments, model training/inference, evaluation and validation paths | Research & Qualification: Dataset/Feature/Target/Partition/Experiment/Model/Evaluation/Evidence | bounded Research commands scheduled by shared Runtime or operator; no second journal | `dataset` through `assessment` plus artifact metadata | **PRESERVE/CONSOLIDATE** | Immutable definitions/partitions/one-primary-change, evidence ceiling, negative results, exact lineage and deterministic replay |
| **Qualification** | model/PIT/provider/OOS/calibration/Phase C/production tables and commands | Research & Qualification: Qualification Policy/Floor/Decision/Result | `RegisterQualificationPolicy`; `DecideQualification` under one purpose-scoped policy | `qualification_policy`, `qualification_policy_floor`, `qualification_decision`, `qualification_floor_result` | **PRESERVE/CONSOLIDATE** | Evidence Class, Assessment Status and non-scalar proof class remain distinct; every required floor FK-bound and explicit; caller booleans cannot promote |
| **Prospective** | prospective attestation/outcome, Daily Alpha prediction target session and Continuous evidence paths | ordinary Runtime + Decision/Evidence/Outcome identities; no separate attestation owner | Decision commits before deadline; later `SettleOutcome`; prospective query/report | `runtime_*`, `decision_run`, `evidence_item`, `outcome*` | **PRESERVE/DERIVE** | Database times/dependencies prove pre-outcome commitment; missed/no-action days retained; prospective does not repair PIT/OOS; reports non-authoritative |

## Cross-capability deletion rules

The following abstractions may be deleted without capability loss only after the
mapped target path passes its acceptance tests:

- table-per-observation/state/transition and generic State Series/current head;
- command/receipt/event table families per runtime or capability;
- per-campaign, per-phase, per-proof, per-panel, and per-outcome registries;
- Strategy/Portfolio Shadow persistence that duplicates Decision/Execution/
  Outcome semantics;
- “current evidence,” snapshot, authority resolution, and admission projection
  tables that duplicate an immutable fact plus as-of query;
- Legacy, migration compatibility, `daily_research`, `daily_decision`, and
  Dividend-T execution paths after their correctness invariants are re-homed;
- document-only capability/evidence assertions.

## Capability acceptance gate

A target capability is preserved only when all relevant conditions hold:

1. Domain types and transition/invariant tests exist;
2. one command writer and one transactional repository path exist;
3. target DDL constraints and concurrency/idempotency tests pass;
4. one read/query path exposes the required audit lineage;
5. clean-database Runtime smoke reaches the capability;
6. architecture tests show old writers/readers are absent;
7. empirical evidence stays at its actual proof class.

The table-count reduction itself satisfies none of these conditions.
