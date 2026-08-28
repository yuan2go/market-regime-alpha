# Authority Map

> **Status:** CANONICAL_TARGET_ARCHITECTURE
> **Authority:** Target business-fact ownership and canonical-write specification
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-29
> **Implementation State:** `FOUNDATION_AND_MARKET_IMPLEMENTED_DRAFT / REMAINDER_DESIGN_ONLY / NOT_CUT_OVER`
> **Code Evidence:** target `src/market_regime_alpha/shared`, `src/market_regime_alpha/runtime`, `src/market_regime_alpha/market`, `src/market_regime_alpha/infrastructure`, `src/market_regime_alpha/interfaces`, `src/market_regime_alpha/infrastructure/postgres/migrations/001_baseline.sql`, `tests/refoundation`; legacy source/migrations remain current business implementation

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
→ lock every non-Runtime aggregate in global `(aggregate_kind, aggregate_id)` order
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

## 3. Authority matrix

| Fact / lifecycle | Canonical owner | Canonical command | Relational owner | Authoritative mutation rule | Primary downstream consumers |
|---|---|---|---|---|---|
| Schema epoch | Runtime & Provenance | `BootstrapSchema` | `schema_epoch` | create once in empty schema; exact checksum thereafter | every process preflight |
| Migration history | Runtime & Provenance | release migrator | `schema_migrations` | forward-only checksum registry within one epoch | bootstrap/verify |
| Runtime schedule | Runtime & Provenance | `Create/ReviseSchedule` | `runtime_schedule` | immutable revision; one enabled revision per schedule | scheduler |
| Run | Runtime & Provenance | `ScheduleRun` | `runtime_run` | transition by Run state machine | operators, Steps |
| Step DAG/state | Runtime & Provenance | Run planner/finalizer | `runtime_step`, `runtime_step_dependency` | frozen DAG; state through guarded transitions only | workers, trace |
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
| Universe definition/revision | Universe & Eligibility | `FreezeUniverse` | `universe`, `universe_revision` | immutable policy/config/source binding per revision | membership |
| Universe membership | Universe & Eligibility | same `FreezeUniverse` command | `universe_member` | every scoped instrument classified included/excluded/unknown with evidence | Eligibility, research |
| Eligibility policy/rules | Universe & Eligibility | `RegisterEligibilityPolicy` | `eligibility_policy`, `eligibility_rule` | immutable typed policy and complete ordered criteria | assessment |
| Eligibility assessment | Universe & Eligibility | `AssessEligibility` | `eligibility_assessment`, `eligibility_reason` | one instrument/policy/universe/Decision-time result; exact evidence | Candidate, funnel |
| Candidate policy | Universe & Eligibility | `RegisterCandidatePolicy` | `candidate_policy`, `candidate_policy_component` | immutable ranking, components and tie/selection rules | Candidate command |
| Candidate Set/Candidate | Universe & Eligibility | `BuildCandidateSet` | `candidate_set`, `candidate`, `candidate_score_component` | immutable complete funnel; Candidate requires eligible assessment | Decision, research |
| Dataset | Research & Qualification | `RegisterDataset` | `dataset`, `dataset_source` | content hash plus exact temporal/universe/source lineage | experiments/models |
| Feature definition | Research & Qualification | `RegisterFeatureDefinition` | `feature_definition` | immutable semantics/code/config identity | Candidate/model |
| Target/checkpoints | Research & Qualification | `RegisterTargetDefinition` | `target_definition`, `target_checkpoint` | immutable Decision reference, horizon and metric requirements | Forecast/Outcome |
| Research partition | Research & Qualification | `FreezeResearchPartition` | `research_partition` | immutable time/member boundary and purpose | experiment/evaluation |
| Experiment and partition binding | Research & Qualification | `RegisterExperiment` | `experiment`, `experiment_partition` | one primary change and frozen protocol/input identities | experiment runs |
| Experiment Run | Research & Qualification | `RunExperiment` | `experiment_run` | immutable execution identity/status; no claim promotion | evaluation |
| Model/Model Version | Research & Qualification | `RegisterModelVersion` | `model`, `model_version` | immutable fitted artifact/definition lineage; lifecycle through qualification only | Forecast |
| Evaluation | Research & Qualification | `EvaluateExperiment/Model` | `evaluation_run`, `evaluation_metric` | predeclared metrics and typed estimability | Assessment |
| Evidence Item/graph | Research & Qualification | `RecordEvidence` | `evidence_item`, `evidence_dependency` | immutable typed evidence; dependency time/hash verified | Assessment/Qualification |
| Assessment | Research & Qualification | `AssessResearchClaim` | `assessment` | status in closed vocabulary; negative/inconclusive preserved | Qualification, reports |
| Qualification policy/floors | Research & Qualification | `RegisterQualificationPolicy` | `qualification_policy`, `qualification_policy_floor` | immutable purpose and complete floor/decision-rule revision | qualification command |
| Qualification | Research & Qualification | `DecideQualification` | `qualification_decision`, `qualification_floor_result` | one purpose/subject/revision; every required floor explicit | runtime admission |
| Decision Run | Decision Support | `RunDecision` | `decision_run` | freezes Candidate Set, Decision time, policies, code/config | all decision facts |
| Context assessment | Decision Support | `AssessContext` | `context_assessment`, `context_metric` | typed Regime/ETF/Theme/Capital kind with evidence and Known Time | Signal/Strategy |
| Signal | Decision Support | `ProduceSignal` | `signal` | immutable setup assertion; no probability claim | Forecast/Opportunity |
| Forecast | Decision Support | `ProduceForecast` | `forecast`, `forecast_estimate` | bound to Target/checkpoint/model; calibration state explicit | Opportunity/Outcome |
| Opportunity | Decision Support | `CreateOpportunity` | `opportunity` | exact Candidate/Signal/Forecast/Context/Strategy input binding; no Risk authorization | Thesis/Portfolio |
| Thesis/condition | Decision Support | `Create/ReviseThesis` | `thesis`, `thesis_condition` | immutable revision; conditions typed and independently observed | Portfolio, monitoring |
| Strategy/version | Decision Support | `RegisterStrategyVersion` | `strategy`, `strategy_version` | stable semantics; qualification purpose-scoped | Opportunity/Portfolio |
| Portfolio policy | Decision Support | `RegisterPortfolioPolicy` | `portfolio_policy` | immutable allocation constraints | proposal |
| Portfolio proposal/line | Decision Support | `ProposePortfolio` | `portfolio_proposal`, `portfolio_line` | complete allocation result; no account/Fill mutation | Risk/Execution |
| Risk policy/rules | Decision Support | `RegisterRiskPolicy` | `risk_policy`, `risk_rule` | immutable typed limits, units and missing behavior | risk assessment |
| Risk decision/reason | Decision Support | `AssessRisk` | `risk_decision`, `risk_reason` | accept/reject/unknown from exact account/market state; rejection final for scope | Execution |
| Outcome observations | Outcome & Attribution | `SettleOutcome` | `outcome`, `outcome_observation`, `outcome_reason` | append factual observation/status after availability; never rewrites Decision | metrics/research |
| Outcome metric | Outcome & Attribution | same settlement command | `outcome_metric` | typed metric/status; MFE/MAE require declared reference/path states | Evaluation/Attribution |
| Attribution | Outcome & Attribution | `RunAttribution` | `attribution_run`, `attribution_line` | diagnostic, reconciled to declared total or `NOT_ESTIMABLE` | Research |
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

Risk evaluates the exact account/Position query, active Intent reservations,
Market/PIT evidence, liquidity/trading restrictions, Portfolio Proposal, and
every ordered `risk_rule` in the exact Risk Policy at Decision time. Each
`risk_reason` FK-binds the evaluated rule. Its accepted quantity is an upper
bound, not a Fill. A rejection cannot be overridden by Strategy code or an
ordinary retry.

Execution Intent creation re-loads the accepted Proposal and Risk Decision under
lock and computes remaining authorization:

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

Qualification is owned only by `qualification_decision` plus the complete set of
`qualification_floor_result` rows. Evidence Items, Assessments, models,
prospective runs, passing tests, runtime receipts, and reports are inputs—not
qualification writers.

A new decision supersedes an earlier decision for the same subject and purpose
without editing it. Missing floors remain explicit. Production admission is a
qualification purpose, not a separate boolean or table.

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
