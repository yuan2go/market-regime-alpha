# Authority Map

> **Status:** CANONICAL_TARGET_ARCHITECTURE
> **Authority:** Target business-fact ownership and canonical-write specification
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-09-05
> **Code Evidence:** target `src/market_regime_alpha/shared`, `src/market_regime_alpha/runtime`, `src/market_regime_alpha/market`, `src/market_regime_alpha/selection`, `src/market_regime_alpha/research_qualification`, `src/market_regime_alpha/decision_support`, `src/market_regime_alpha/infrastructure`, `src/market_regime_alpha/interfaces`, `src/market_regime_alpha/infrastructure/postgres/migrations/001_baseline.sql`, `tests/refoundation`; legacy source/migrations remain current business implementation

This document answers one question for every retained fact: who may create or
change it? A table, DTO, policy, artifact, snapshot, report, receipt, or query is
not an Authority merely because it exists.

## 1. Authority rules

1. Each fact has one bounded-context owner and one Application command path.
2. PostgreSQL constraints and the owning repository protect identity and
   lifecycle in the command transaction.
3. A projection can be rebuilt from owner facts and cannot write upstream.
4. A policy constrains an owner; it never grants itself authority.
5. Corrections append a revision/supersession fact. Historical identity is not
   overwritten.
6. Cross-context callers supply stable IDs, not caller-constructed “current”
   DTOs.
7. Read models, Current State, Capability Matrix, Evidence Ledger, reports, and
   artifacts cannot promote qualification or business state.
8. Runtime controls when a command runs, not what the business result means.

## 2. Canonical write path

```text
authenticated Command
→ when Runtime-owned: lock current Run/Step/Attempt and validate lease/fence
→ idempotency/request-hash check or exact terminal replay
→ load exact immutable dependencies
→ lock every participating root in the explicit global order
→ enforce Domain invariants and expected version
→ write canonical fact/revision
→ write dependency links + command receipt + audit event
→ finalize the same live Attempt with the matching receipt/fence when applicable
→ one PostgreSQL commit
```

Remote I/O and artifact byte publication happen outside the transaction under
the protocols in the supporting architecture documents. When a Runtime claim
participates, its lock/fence is the first relational lock in the short business
transaction; the owner never writes first and validates the fence later. No
caller may write owner tables through a generic repository or raw SQL.

If a deterministic rejection aborts the business transaction, that transaction
is rolled back before the owning Application opens a new short instance of the
same bounded-context UoW. That failure transaction locks the live fence first,
then atomically records the failed receipt, audit, and Attempt/Step failure.
Stale fences write none of those facts. The shared contract interprets neither
Domain errors nor commands and is not a command bus or workflow owner.

## 3. Authority matrix

| Fact / lifecycle | Canonical owner | Canonical command | Relational owner | Authoritative mutation rule | Primary downstream consumers |
|---|---|---|---|---|---|
| Schema epoch | Runtime & Provenance | `BootstrapSchema` | `schema_epoch` | create once in empty schema; exact checksum thereafter | every process preflight |
| Migration history | Runtime & Provenance | release migrator | `schema_migrations` | forward-only checksum registry within one epoch | bootstrap/verify |
| Runtime schedule | Runtime & Provenance | `Create/ReviseSchedule` | `runtime_schedule` | immutable revision; one enabled revision per schedule | scheduler |
| Run | Runtime & Provenance | `ScheduleRun` | `runtime_run` | transition by Run state machine | operators, Steps |
| Step DAG/state | Runtime & Provenance | Run planner/finalizer | `runtime_step`, `runtime_step_dependency` | frozen DAG; state through guarded transitions only | workers, trace |
| Formal proof Runtime profiles | Runtime & Provenance, composed by Research | existing `ScheduleRun` plus canonical Application commands | existing Runtime DAG rows plus `formal_research_campaign_runtime_run` binding | exact mandatory Decision Proof and Due Proof step/edge rosters; no second Runtime, business dispatcher, or CLI cutover | controlled campaign execution/inspection |
| Attempt/lease/fence | Runtime & Provenance | `ClaimStep`, `HeartbeatAttempt`, `FinalizeAttempt` | `runtime_attempt` | DB-clock lease and monotonic fence | business writers, recovery |
| Command idempotency | Runtime & Provenance | every mutating handler | `command_receipt` | unique scope/key; immutable request hash/result | callers, replay |
| Audit event | Runtime & Provenance | same business transaction | `audit_event` | append-only typed actor/action/reason/version | inspection, compliance |
| Artifact identity/binding | Runtime & Provenance | `RegisterArtifact` | `artifact`, `artifact_dependency` | SHA-256 identity; verified bytes before reference | every artifact consumer |
| Artifact verification/GC eligibility | Runtime & Provenance | `VerifyArtifact`, `MarkGcCandidate` | `artifact_verification`, `artifact_gc_candidate` | append verification; two-pass quarantine | operators |
| Provider identity/product contract | Market & PIT | `RegisterProviderProduct` | `provider`, `provider_product` | explicit source/fact/time/price-basis capability revision | Capture, qualification |
| Raw capture | Market & PIT | `RegisterCapture` | `data_capture` + `artifact` | immutable bytes, request identity, provider/capture times | normalizer, replay |
| Instrument and identifier | Market & PIT | `RegisterInstrument/Identifier` | `instrument`, `instrument_identifier` | stable instrument; effective-dated identifiers never reused ambiguously | all contexts |
| Trading session | Market & PIT | `RegisterTradingSession` | `trading_session` | exchange-calendar evidence; no weekday inference | Universe, Decision, Outcome |
| Classification and membership | Market & PIT | `RegisterClassification/ReviseMembership` | `classification`, `classification_membership_revision` | append-only PIT revision for index/industry/theme | Context, Universe |
| Market bar revision | Market & PIT | `NormalizeMarketBar` | `market_bar_revision` | append-only logical-key revision with raw/adjusted basis and Known Time | Context, Signal, Outcome |
| Instrument fact revision | Market & PIT | `NormalizeInstrumentFact` | `instrument_fact_revision` | append-only typed status/shares/limit/reference fact | Eligibility, Risk |
| Corporate action revision | Market & PIT | `NormalizeCorporateAction` | `corporate_action_revision` | append-only source revision; no silent adjustment | Outcome, Position basis |
| Expected-source gap | Market & PIT | `RecordSourceGap` | `source_gap` | explicit missing/placeholder/conflict interval and reason | PIT query, operators |
| Market archive | Market & PIT, Archive UoW | `StartMarketArchive`, `ExecuteArchiveSlice`, `RecordArchiveCaptureObservation`, `SealRetrospectiveArchive` | `market_archive`, `market_archive_slice`, `market_archive_capture_observation`, `market_archive_slice_gap`, `market_archive_resource_stop`, `market_archive_seal` | immutable complete slice roster over exactly one retrospective or prospective lane; Capture/Artifact/normalization and typed gap lineage are concrete; PostgreSQL owns archive/seal time; pre-window prospective access fails and retrospective seal fixes `EXPLORATORY_RETROSPECTIVE` | dual-clock Dataset/backtest, archive inspection, future evidence accumulation |
| Provider qualification protocol/decision | Market & PIT, Provider Qualification UoW | `RegisterProviderQualificationProtocol`, `CompleteProviderQualification` | `provider_qualification_protocol`, `provider_qualification_requirement`, `provider_finality_observation`, `provider_qualification_decision`, `provider_qualification_capture_member`, `provider_qualification_requirement_result` | immutable purpose-specific scope and complete ten-requirement recorded-fact rosters; finality chain and result count/hash reconciled; `ENGINEERING_REHEARSAL` cannot be admitted; no caller assertion | qualified historical visibility, Formal Campaign |
| Qualified historical source visibility | Market & PIT | source-specific admission commands after exact Provider Decision | `qualified_market_bar_visibility`, `qualified_instrument_fact_visibility`, `qualified_classification_membership_visibility`, `qualified_trading_session_visibility`, `qualified_source_gap_visibility` | only exact `RECORDED_PROVIDER + ADMITTED + HISTORICAL_PIT` decision may append; concrete source/capture FK, source availability, Decision-visible cutoff, and content hash; no current/latest or reconstruction | Formal PIT resolver/Dataset |
| Universe definition/revision | Selection | `FreezeUniverse` | `universe`, `universe_revision` | immutable explicit scope-spec/config identity; no implicit all-current-instrument scope | membership |
| Universe membership | Selection | same `FreezeUniverse` command | `universe_member` | every explicitly scoped instrument classified included/excluded/unknown with exact Market lineage | Eligibility, research |
| Eligibility policy/rules | Selection | `RegisterEligibilityPolicy` | `eligibility_policy`, `eligibility_rule` | immutable typed policy and complete ordered criteria; units/window/operator/threshold explicit | assessment |
| Eligibility assessment | Selection | `AssessEligibility` | `eligibility_assessment`, `eligibility_reason` | every rule evaluated for every scoped instrument; one three-state aggregate with exact Market lineage | Candidate, funnel |
| Candidate policy | Selection | `RegisterCandidatePolicy` | `candidate_policy`, `candidate_policy_component` | immutable arithmetic-midrank/competition-rank/strict-complete-case/Top-K/tie/projection contract; components bind only real numeric Feature Definitions and canonical declared weights | Candidate command |
| Candidate Set/Candidate | Selection | `BuildCandidateSet` | `candidate_set`, `candidate`, `candidate_score_component` | immutable Policy × Decision-input Dataset result; Dataset is sole population; every row terminal; complete typed component matrix and funnel; non-unique equal rank; independent of all later authorities | dependency-authorized downstream consumers |
| Decision-input Dataset | Research & Qualification | `RegisterDataset` | `dataset`, `dataset_source` | immutable content plus exact DecisionTime, `INCLUDED` + `ELIGIBLE` population, Feature status/value Artifact, and concrete Market/Selection lineage; Target/Outcome/realized labels prohibited | Candidate |
| Formal Dataset admission | Research & Qualification | `RegisterFormalDataset` | `formal_research_dataset` plus ordinary `dataset`, `dataset_source` | exact Formal Campaign and bound admitted Provider Decision; complete typed qualified-source roster must match the ordinary Dataset lineage; engineering rehearsal fails closed | formal Candidate/Decision proof |
| Feature definition | Research & Qualification | `RegisterFeatureDefinition` | `feature_definition` | immutable semantic/value/unit/frequency/window/lookback/source/availability/missingness/algorithm/code/config identity; no research conclusion | Candidate |
| Retrospective simulation bindings | Selection, Research & Qualification, and Decision Support for their own roots | typed `FreezeExploratoryRetrospectiveUniverse`, `AssessExploratoryRetrospectiveEligibility`, `RegisterExploratoryRetrospectiveDataset`, `OpenExploratoryRetrospectiveDecisionRun` seams | `exploratory_retrospective_universe_revision`, `exploratory_retrospective_eligibility_batch`, `exploratory_retrospective_dataset`, `exploratory_retrospective_decision_run` | bind ordinary immutable owners to one exact archive seal, real knowledge cutoff and earlier simulated event/session cutoff; evidence class is database-fixed; ordinary PIT remains unchanged and Formal/LOCKED_OOS/PROSPECTIVE admission rejects these bindings | exploratory Candidate/Decision chain only |
| Target Definition/checkpoints/metrics | Research & Qualification | `RegisterTargetDefinition` | `target_definition`, `target_checkpoint`, `target_metric_definition`, `target_metric_dependency` | immutable provider-neutral Decision-reference rule, horizon, observation grid, metric/barrier/dependency, price-basis, availability/finality, algorithm/code/config contract; Target-owned root-last closure requires at least one required metric and exactly the Outcome-consumable dependency shape for every metric kind; append-only supersession; all business semantics relational | requested Target roster, Forecast, Outcome |
| Research Partition roster | Research & Qualification | `FreezeResearchPartition` | `research_partition`, `research_partition_member` | PostgreSQL derives the complete non-empty commitment roster from exact Target, Decision window and declared population scope; each member binds its exact DecisionReference session and deferred bidirectional set closure rejects omission/substitution; freezes purpose, session-expanded Outcome/purge/embargo protected range, purpose-specific overlap compatibility, calendar, code/config, provenance, count and hash before any Outcome read | Experiment/Evaluation/OOS proof |
| Research Partition Outcome access | Research & Qualification, Evaluation UoW | `AcquireOutcomeInputs` | `research_partition_outcome_access` | append-only exact Evaluation Run/member/Outcome revision fact; per-member ordinal is globally monotonic and ordinal one is first-access Authority; exact Outcome-root locking serializes cutoff-visible leaf validation with correction; non-protected reuse is ordinal 2+, while protected reuse is rejected; values cannot leave the acquiring transaction before the access, observation, reconciliation and lifecycle transition commit | Evaluation/OOS diagnostics |
| Experiment and partition binding | Research & Qualification | `RegisterExperiment` | `experiment`, `experiment_partition` | one primary change, one Target, frozen protocol/input identities and purpose-specific partitions | Experiment Run |
| Experiment Run | Research & Qualification | `OpenExperimentRun` | `experiment_run` | immutable execution identity opened after Experiment registration; no positive-result or qualification implication | Evaluation Run |
| Evaluation protocol | Research & Qualification | `RegisterEvaluationProtocol` | `evaluation_protocol`, `evaluation_protocol_metric` | exact Target/purpose, reducer/source-value compatibility, concrete Candidate-disposition slice, direction, missingness, inclusion/exclusion and acceptance semantics freeze before any Outcome access | Evaluation Run |
| Evaluation observation/metric | Research & Qualification | `OpenEvaluationRun`, `AcquireOutcomeInputs`, `CompleteEvaluationRun` | `evaluation_run`, `evaluation_observation`, `evaluation_metric`, `evaluation_metric_observation` | Run freezes Experiment Run, same-Target bound Partition/protocol, exact cutoff, code/config and provenance, never Model; protected purposes require zero prior Partition access; every member gets one exact cutoff-visible Outcome revision observation including unavailable/failed; not-due/missing/ambiguous blocks; full metric/slice × observation roster records included/excluded/not-estimable before completion | Evidence/Assessment |
| Exploratory backtest predeclaration | Research & Qualification, Exploratory Backtest UoW | `RegisterExploratoryBacktestRun` | `exploratory_backtest_run`, `exploratory_backtest_feature`, `exploratory_backtest_arm`, `exploratory_backtest_fold`, `exploratory_backtest_fold_session`, `exploratory_backtest_cost_assumption`, `exploratory_backtest_dataset` | atomically freezes one archive seal, Target/policies, ordered rule/Model arms, chronological FIT/VALIDATION session folds, purge/embargo, costs, metrics, seed and complete hashes; owns lineage only and cannot store labels, portfolios, Risk or metrics | canonical Dataset/Decision/Outcome/Evaluation owners |
| Model/Training/Version | Research & Qualification, Research Model UoW | `RegisterResearchModel`, `OpenModelTrainingRun`, `FitAndRegisterModelVersion` | `model`, `model_feature_definition`, `model_training_run`, `model_training_sample`, `model_version` | stable family and immutable feature roster; TrainingRun derives every sample from a completed FIT Evaluation; deterministic fit publishes a verified immutable Artifact outside the transaction; Version reloads the exact sample/Artifact/algorithm/hyperparameter/seed/cutoff lineage; no caller-selected performance and no qualification implication | strictly later-fold Model Forecast |
| Exploratory Evaluation sources | Research & Qualification, Evaluation UoW | backtest-aware `AcquireOutcomeInputs` / `CompleteEvaluationRun` | `evaluation_backtest_arm_source`, `evaluation_candidate_source`, `evaluation_signal_source`, `evaluation_forecast_source`, `evaluation_portfolio_source`, `evaluation_portfolio_cost_source`, `evaluation_risk_source` | every metric-member input concrete-FKs the exact canonical source owner; complete Cartesian reconciliation preserves unavailable, failed, excluded and not-estimable members; Evaluation owns values and state, not a DataFrame or report | Evidence/inspection |
| Evidence Item/graph | Research & Qualification, Evidence UoW | `RecordEvidence` | `evidence_item`, `evidence_dependency` | every item requires a concrete terminal Evaluation Run and immutable Artifact FKs; metric scope binds an exact same-Run Evaluation Metric; ordered dependency count/hash and recursive guards prove an immutable typed support/counter-evidence DAG | Research Assessment |
| Research Assessment/evidence | Research & Qualification, Assessment UoW | `AssessResearch` | `research_assessment`, `research_assessment_evaluation`, `research_assessment_evidence` | one Experiment-bound append-only revision derives complete non-empty terminal Evaluation and concrete Evidence rosters at a PostgreSQL cutoff; every item belongs to a rostered Run; failed/negative/inconclusive/not-estimable preserved; direct supersession only | Research Qualification |
| Research Qualification policy/floors | Research & Qualification, Qualification UoW | `RegisterResearchQualificationPolicy` | `research_qualification_policy`, `research_qualification_policy_floor` | immutable purpose and complete relational floor/decision-rule revision with exact Protocol metric/slice, state, threshold, count, missingness and Evidence requirements; direct supersession only | qualification command |
| Research Qualification decision | Research & Qualification, Qualification UoW | `DecideResearchQualification` | `research_qualification_decision`, `research_qualification_floor_result`, `research_qualification_floor_evidence` | concrete Assessment + Policy; every floor and exact links to that Assessment's Evidence set complete; generation-safe effective/known time, typed append-only supersession, no generic subject | exact-ID later-generation admission read |
| Formal Research Campaign | Research & Qualification, Formal Campaign UoW | `PredeclareFormalResearchCampaign`, `BindProviderDecision`, `BindPartitionRoster`, `BindExperiment`, `OpenProtected` | `formal_research_campaign`, `formal_research_campaign_partition_plan`, `formal_research_campaign_evaluation_protocol`, `formal_research_campaign_cost_assumption`, `formal_research_campaign_provider_decision`, `formal_research_campaign_partition_binding`, `formal_research_campaign_experiment`, `formal_research_campaign_protected_open`, `formal_research_campaign_runtime_run` | root/child-closed immutable Target/hypothesis/baseline/FIT/VALIDATION/LOCKED_OOS/Evaluation/Qualification/cost freeze; binds complete database-derived Partition and Experiment rosters; PostgreSQL-time protected opening concrete-FKs Run/Evaluation and proves zero Outcome access; any change requires new revision/generation | controlled proof Runtime and read-only inspection |
| Decision Run/requested Target/commitment/reference | Decision Support (`market_regime_alpha.decision_support`) | `OpenDecisionRun` | `decision_run`, `decision_run_target`, `decision_target_commitment`, `decision_reference_observation` | mandatory after Candidate and before Context; exactly one canonical Run per Candidate Set; atomically freezes an ordered Target/version and Decision-time Provider Product roster that survives empty population, every Candidate × requested Target, and exact Decision-visible Market revision or Source Gap with separate value/availability/finality states; no Outcome placeholder | all decision facts, Market Target Outcome |
| Later-generation Research Qualification input | Decision Support | qualified form of `OpenDecisionRun` | `decision_run_research_qualification_roster`, `decision_run_research_qualification_member` | every Run atomically freezes an intentional zero-or-more ordered count/hash roster; each member has a matching-purpose exact `ADMITTED` decision FK effective/known and non-superseded at DecisionTime with strictly earlier source Outcome generations; no current/latest or caller assertion | later-generation Context/Forecast/Decision policy only |
| Context assessment | Decision Support | `RegisterContextPolicy`, `AssessContext` | `context_policy`, `context_policy_metric`, `context_assessment`, `context_metric`, `context_metric_source` | immutable typed Regime/ETF/Theme/Capital/Breadth rules; complete Market/PIT source lineage, Known Time, availability and missingness; never Outcome | Signal/Strategy |
| Signal | Decision Support | `ProduceSignal` | `signal`, `signal_context_binding` | one immutable typed assertion for every Candidate under exact Context/Strategy inputs; explicit no-signal/wait/unknown/not-estimable; no probability claim | Forecast/Opportunity |
| Forecast | Decision Support | `ProduceForecast` | `forecast`, `forecast_estimate` | complete rule-based Target/commitment/checkpoint estimates; uncalibrated semantics explicit; no Model prerequisite or placeholder | Opportunity/Evaluation |
| Forecast Model binding | Decision Support | `ProduceModelForecast` | `forecast_model_binding` | concrete exact ModelVersion and Forecast/Estimate lineage; binding is permitted only for a strictly later backtest fold/generation than every training sample and remains uncalibrated; rule Forecast needs no Model | Opportunity/Evaluation |
| Opportunity | Decision Support | `CreateOpportunities` | `opportunity_set`, `opportunity`, `opportunity_context` | complete Forecast roster with exact Candidate/Signal/Forecast/Context/Strategy input bindings; no Risk authorization | Thesis/Portfolio |
| Thesis/condition | Decision Support | `CreateThesis` | `thesis`, `thesis_condition` | immutable append-only revision; conditions typed and independently observed | Portfolio, monitoring |
| Strategy/version | Decision Support | `RegisterStrategyVersion` | `strategy`, `strategy_version` | stable semantics; qualification purpose-scoped | Opportunity/Portfolio |
| Portfolio policy | Decision Support | `RegisterPortfolioPolicy` | `portfolio_policy` | immutable allocation constraints | proposal |
| Portfolio proposal/line | Decision Support | `ProposePortfolio` | `portfolio_proposal`, `portfolio_line` | complete allocation result; no account/Fill mutation | Risk/Execution |
| Risk policy/rules | Decision Support | `RegisterRiskPolicy` | `risk_policy`, `risk_rule` | immutable typed limits, units and missing behavior | risk assessment |
| Risk decision/reason | Decision Support | `AssessRisk` | `risk_decision`, `risk_reason` | `DECISION_SUPPORT_ONLY` authorization over one complete Proposal using frozen proposal/upstream Market facts and every typed rule; authorized/rejected/unknown/no-action are explicit and rejection is final for this scope; never Account, Intent, broker or trading authority | later Execution may only narrow an accepted scope |
| Market Target Outcome root/revision | Outcome & Attribution | `SettleMarketTargetOutcome` | `market_target_outcome`, `market_target_outcome_revision` | one root per Decision Target Commitment; exact request retry reuses revision; partial/completion/correction/finality change appends a full snapshot with direct supersession | Outcome read port |
| Market Target Outcome facts | Outcome & Attribution | same settlement command | `market_target_outcome_source`, `market_target_outcome_observation`, `market_target_outcome_metric`, `market_target_outcome_metric_reference`, `market_target_outcome_metric_observation`, `market_target_outcome_reason` | exact relational source roster; `REFERENCE` concrete-FKs the frozen WP-09 Decision reference while `OBSERVATION`/`PATH_MEMBER` concrete-FK same-revision Outcome observations; revision children keep path/checkpoint/return/MFE/MAE/barrier value, availability, finality and failure independent; two cutoffs; never rewrites Decision | Evaluation/Market Attribution |
| Market Attribution | Outcome & Attribution | `RunMarketAttribution` | `market_attribution_run`, `market_attribution_line` | diagnostic, reconciled to declared Market Outcome total or `NOT_ESTIMABLE` | Research |
| TradeOutcome | Outcome & Attribution | `SettleTradeOutcome` | `trade_outcome`, `trade_outcome_fill_binding`, `trade_outcome_metric` | immutable account/instrument episode revision with concrete opening/closing effective Fill roots and complete Fill roster; replay proves zero-to-zero Position; Fill correction supersedes; never uses a Decision Target Commitment | Trade Attribution/Evaluation |
| Trade Attribution | Outcome & Attribution | `RunTradeAttribution` | `trade_attribution_run`, `trade_attribution_line` | diagnostic over TradeOutcome only; no Market/Trade polymorphic subject | Research |
| Account | Execution & Account | `RegisterAccount` | `account` | stable external account identity; no secret storage | execution |
| Account Authority Epoch | Execution & Account | `OpenAccountAuthorityEpoch` | `account_authority_epoch` | explicit cut-in time/opening evidence; one active epoch | Position/Reconciliation |
| Opening/non-trade basis | Execution & Account | `RecordPositionBasisEvent` | `position_basis_event` | typed opening/corporate-action/reconciliation event under special rules | Position projection |
| Execution Intent | Execution & Account | `ApproveExecutionIntent` | `execution_intent` | accepted Portfolio/Risk scope, reservation and lifecycle; not Fill | human/broker workflow |
| Fill/correction | Execution & Account | `RecordObservedFill/CorrectFill` | `fill` | append-only observed fact/correction, external execution identity unique | Position/Outcome |
| Strategy Fill allocation | Execution & Account | `AllocateFill` | `fill_allocation` | total allocations cannot exceed effective Fill; no negative sleeve | sleeve/Attribution |
| Broker observation | Execution & Account | `RecordBrokerObservation` | `broker_observation`, `broker_observation_line` | append-only comparison evidence; no Position mutation | reconciliation |
| Reconciliation | Execution & Account | `ReconcileAccount` | `reconciliation`, `reconciliation_difference` | deterministic comparison; difference alone cannot mutate | operator/action |
| Physical Position | Execution & Account query owner | no direct write | `current_position` view over `fill` + `position_basis_event` | always derived as-of; no independent Position table | Risk, inspection |
| Strategy sleeve | Execution & Account query owner | no direct write | query/view over effective `fill_allocation` and qualified corporate actions | derived; opening/reconciliation quantities stay unallocated | Outcome/Attribution |

WP-18Q adds no owner and no second Backtest, Runtime or Outcome/Evaluation
truth. Its implemented target-draft refinements are:

| Fact / operation | Sole owner | Concrete bindings and authority limit |
|---|---|---|
| Generic frozen Backtest specification | Research & Qualification, Backtest UoW | `BacktestApplication.predeclare` binds the existing `exploratory_backtest_run` to `backtest_specification` and complete sample/arm/fold/dependency/evaluation requirements; specification is not execution evidence |
| Generic execution / inspect / resume / replay | Existing Runtime plus each canonical Application owner | `backtest_runtime_binding`, `backtest_evaluation_execution`, `backtest_model_lineage` reconcile exact owner facts; they cannot create a second workflow or metric truth |
| Model reproducibility | Research & Qualification, Research Model UoW | `model_training_reproducibility`, `model_training_dependency`, `model_training_hyperparameter`; completed FIT → TrainingRun → ModelVersion → strictly later VALIDATION remains mandatory |
| Standard formulas and report | Evaluation owns metrics; Report owns projection only | `evaluation_metric_formula`, `evaluation_formula_parameter`, `evaluation_candidate_outcome_source` and existing typed sources feed reconciled JSON/Markdown `backtest_report_artifact`; no raw-bar recomputation |
| Prospective generations / due / terminals / revisions | Market Application using existing Runtime | `prospective_archive_generation`, `prospective_archive_generation_member`, `prospective_archive_slice_schedule`, `prospective_archive_slice_terminal`, `prospective_archive_revision_observation`, `prospective_archive_planning_gap`; PostgreSQL clock and real Runtime fences, never a second scheduler |

These refinements are implemented, not automatically engineering-qualified.
WP-specific executable surfaces remain until the prescribed real-campaign,
report, replay, historical-equivalence and regression hard-cut gates pass.
Their presence is a qualification blocker, not a permanent compatibility policy.

Rows through WP-14 Formal Research readiness, WP-13 Decision Support, and
WP-17P archive/Model/backtest describe implemented, engineering-qualified
target-draft ownership without Runtime/CLI cutover or empirical promotion.
Rows for Execution, TradeOutcome, and Attribution remain logical Target design
only. Model exists only for exploratory research and is neither qualified nor
calibrated. Their sequence is owned only by the Roadmap. Realized
market labels stay under the Market Target Outcome Authority and realized trade
economics under TradeOutcome; Research cannot construct a parallel truth source.

The aggregate edge is acyclic:

```text
MarketArchive → MarketArchiveSeal → dual-clock Dataset binding
                                      │
Dataset → CandidateSet → DecisionRun → DecisionRunTarget ← TargetDefinition
             │                            │
             └────────────────────────────v
                              DecisionTargetCommitment
                    ├→ Context/Signal/Forecast/Decision
                    ├→ MarketTargetOutcome ← Market/PIT
                    └→ ResearchPartitionMember
Experiment → ExperimentPartition ← ResearchPartition
ExperimentPartition → ExperimentRun → EvaluationRun
MarketTargetOutcome ─ read-only port → OutcomeAccess/EvaluationObservation
EvaluationRun/Observation → EvaluationMetric → EvidenceItem
→ ResearchAssessment → ResearchQualification
FIT Evaluation → ModelTrainingRun → ModelVersion
                                    └→ later-fold ForecastModelBinding
ProviderQualificationDecision → qualified source visibility → FormalDataset
FormalResearchCampaign → exact Runtime/Partition/Experiment/Evaluation bindings
```

Feedback may cross generations only:
`Outcome(n) → Evaluation(n) → Qualification(n) → DecisionRun(n+1)`.
A Research Qualification crosses the last edge only through the concrete Run
roster/member pair; a selected Model Version follows the same temporal rule
through its concrete owning binding. No same-generation FK or command
returns to Candidate, commitment, Context, Signal, Forecast, or Decision.

## 4. Position Authority

“Fill-derived Position” means **all trade-caused quantity and cost changes come
only from observed effective Fills**. It does not require inventing Fills for
opening balances or non-trade corporate actions.

For account `a`, instrument `i`, and as-of time `t`:

```text
PhysicalQuantity(a,i,t)
  = Σ EffectiveFillSignedQuantity(a,i,≤t)
  + Σ AuthorizedNonTradeBasisQuantity(a,i,≤t)
```

`current_position` is this deterministic query. It is not stored as mutable
Authority.

### Effective Fill

- An original Fill records the externally observed execution identity, side,
  quantity, price, fees, execution time, capture time, and Intent.
- Corrections append a Fill event linked to the original chain. They express a
  typed reversal or delta; they never update/delete the original.
- Duplicate external execution identity with conflicting content fails closed.
- A Proposal, Risk Decision, Execution Intent, target position, broker
  observation, reconciliation difference, or operator note cannot create a Fill.
- Cash/cost and quantity projections use the same effective chain and canonical
  decimal arithmetic.

### Opening position

An account enters Authority through exactly one `account_authority_epoch`.
Opening holdings require `position_basis_event.kind = OPENING_BALANCE`:

- effective at the epoch boundary;
- one row per account/instrument/epoch;
- backed by a verified broker observation and operator attestation;
- immutable quantity/cost basis with explicit `UNKNOWN` where cost cannot be
  established;
- cannot reference a Strategy Version or masquerade as a Fill.

Opening holdings are physical account truth but not strategy performance
history. They remain in an unallocated opening sleeve unless later reduced by
observed Fills.

### Corporate action

A split, bonus issue, conversion, merger, or other non-trade quantity change
requires `position_basis_event.kind = CORPORATE_ACTION` and:

- an exact qualified `corporate_action_revision`;
- owner-resolved entitlement holdings immediately before the effective event;
- effective session/time and deterministic quantity/cost transformation;
- raw/adjusted policy consistency;
- idempotent uniqueness for account/action/instrument.

Cash dividend alone changes cash evidence, not share quantity. Missing or
conflicting action evidence blocks reconciliation; it is never inferred from an
adjusted price series. Strategy sleeve quantity transformations may be derived
proportionally only from allocations that existed at entitlement time and the
same qualified action; no new strategy ownership is created.

### Broker observation

A broker snapshot is `broker_observation` evidence. It may reveal a difference,
but it never writes Physical Position, Fill, or sleeve state. The comparison is
stored in `reconciliation`/`reconciliation_difference` with both sides,
tolerance policy, and status.

### Reconciliation adjustment

A difference does not authorize mutation. If an observed Fill or qualified
corporate action can explain it, that canonical fact is recorded and
reconciliation is rerun. Only when the difference cannot be represented by an
available source fact may an operator issue
`position_basis_event.kind = RECONCILIATION_ADJUSTMENT`:

- explicit operator identity, reason code, approval/audit event;
- exact reconciliation and difference;
- quantity/cost delta, effective time, and evidence artifact;
- no Strategy Version or Fill identity;
- append-only correction/supersession if later resolved.

The adjustment is visible as lower-quality non-trade basis evidence and blocks
Production qualification until resolved under policy. It cannot be silently
netted into a Fill.

## 5. Risk and execution boundary

WP-13 Risk evaluates the complete Portfolio Proposal, its lines, frozen
Decision-visible Market/PIT lineage and every ordered `risk_rule` in the exact
Risk Policy. Each `risk_reason` FK-binds the evaluated rule. Its constant
`DECISION_SUPPORT_ONLY` scope authorizes no Account, Intent, broker request,
Order, Fill, Position mutation or trading. A rejection cannot be overridden by
Strategy code or an ordinary retry.

After the concrete Account and Execution parents exist, Execution Intent
creation must re-load an accepted Proposal and Risk Decision plus the exact
Account Authority Epoch, Fill-derived Position and live reservations under
lock. It may only narrow capacity or reject; it cannot overwrite or reinterpret
the Decision Support result. Remaining authorization is then computed as:

```text
remaining
  = authorized quantity
  - effective observed Fill quantity
  - quantity reserved by live Intents
```

A different idempotency key cannot reuse capacity. Terminal cancellation releases
only unused reservation. A late Fill remains factual and triggers
reconciliation; it is not discarded because its Intent is terminal.

## 6. Qualification Authority

Research Qualification is owned only by a concrete
`research_qualification_decision` plus its complete
`research_qualification_floor_result` and
`research_qualification_floor_evidence` rows. Its required subject is one
`research_assessment`; its policy is one `research_qualification_policy`.
Evidence Items, models, prospective runs, passing tests, runtime receipts, and
reports are inputs—not qualification writers.

A new Research decision supersedes an earlier Research decision without editing
it. Missing floors remain explicit. Future Provider, Model, Strategy, Execution,
and Production qualification must introduce subject-specific binding/decision
relations in their owning work packages. They cannot widen Research
Qualification into `(subject_kind, subject_id)` or add nullable placeholder FKs.

## 7. Read models and documents

Permitted replaceable views include:

- `current_market_fact` and `current_classification_membership`;
- `current_universe` and the Candidate funnel;
- `current_position`, `current_strategy_sleeve`, cash/exposure;
- Decision dossier and outcome/attribution summaries;
- Run trace and artifact integrity;
- qualification-floor matrix and Capability status.

Evidence Ledger, Current State, Capability Matrix, Roadmap progress, dashboards,
and reports may be generated from these queries with `generated_at`, code SHA,
schema epoch, and source query/artifact hash. They are explicitly
non-authoritative. Manual edits to those documents cannot change a row, unlock a
floor, or establish a capability.

## 8. Deleted authority patterns

The target forbids:

- table-per-state and separately mutable “current” pointer tables;
- registry + snapshot + artifact rows that each claim the same identity;
- command tables per capability;
- separate Runtime journals per child workflow;
- simulated Position tables sharing names/semantics with physical Position;
- caller-supplied qualification booleans;
- compatibility readers that can write a new semantic version;
- generic payload repositories as business state;
- documents or filesystem paths used as latest-state pointers.
