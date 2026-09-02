# Current State

> **Status:** CURRENT_STATUS
> **Authority:** Non-authoritative implementation status read model; exact-SHA engineering proof remains in Verification
> **Owner:** Market Regime Alpha maintainers
> **Generated At:** 2026-09-02 WP-16 external Provider-evidence Gate A reconciliation
> **Repository Implementation Checkpoint:** `ca6f66b50ec2c55250cd82d2fa1ed6c5f35c29b8`
> **Execution-Time Main Baseline:** `16a4ab1d0d42a4144ef1bd1dcd15ac4ba5ab1087`
> **Containing Documentation Commit:** reported by the final handoff; this read model does not claim a self-referential Git SHA
> **Previous Verified Snapshot:** merged WP-13 implementation `fc5993e5d9e05dbe2845659140108e1051cf3704` on `origin/main@eb7970b4833228a2faba6715c65c26dae88f6ee5`
> **Implementation Line Start:** `c3ac21ef1e13f2e8408d30b0481fa9b74c4f9539`
> **Foundation Source Checkpoint:** `eeff49c7a3995ba6d65045be88d4244617301234`
> **Legacy Business Implementation Parent:** `0382dad416d6d50d1eea0bda1603d7c359d65274`
> **Schema Epochs:** canonical business `LEGACY_MIGRATIONS_001_106`; target draft `MRA_REFOUNDATION_1 / DRAFT / NOT_CUT_OVER`
> **Generator:** `WP-ARCHITECTURE-REFOUNDATION-16 external Provider-evidence Gate A reconciliation; non-authoritative read model`
> **Source Tree IDs:** execution-baseline root `6f12a62c63b869000c08b0bf2673e9a3721187f6`; source `ccc42e2a732f0738c560d762ce3c61a1418c475e`; tests `4a2148ff361c057db68d4ee3e758266246b010dd`; Research Qualification tree `453e0f4f81d62a27ebd1e8237fae1627901c95b8`; Market tree `d0efafaa99e7cc575b619f1a3791112e432bb5f0`; Runtime tree `b01c45b9ca7009fe8ddc9cba227f2f656473c6c1`; target baseline blob `2b4f587da1f616ef6b0eeaf15621cbe1c116be50`; legacy migrations tree `6d3730548780ad6244d2cfecb4fb3559064b6f06`
> **Code Evidence:** target and legacy source/migration packages, `tests`, [WP-14 canonical design](../references/WP-ARCHITECTURE-REFOUNDATION-14-Formal-Research-Engineering-Readiness-Design.md), [WP-14 immutable Verification](../references/WP-ARCHITECTURE-REFOUNDATION-14-Formal-Research-Engineering-Readiness-Verification.md), [WP-15 real campaign Verification](../references/WP-ARCHITECTURE-REFOUNDATION-15-Formal-Research-Proof-Campaign-Verification.md), [WP-16 blocker design](../references/WP-ARCHITECTURE-REFOUNDATION-16-Real-Provider-Evidence-Blocker-Design.md), and [WP-16 immutable Gate A Verification](../references/WP-ARCHITECTURE-REFOUNDATION-16-Real-Provider-Evidence-Gate-A-Verification.md)

This read model records the WP-14 controlled proof Runtime profiles, Formal
Campaign freeze, protected OOS/prospective mechanics, Market-owned Provider
qualification mechanics, qualified Formal PIT/Dataset seams, inspection, and
exact-SHA engineering qualification. It also records the first WP-15 real
recorded-Provider gate: BaoStock transport and capture succeeded, but the
complete purpose-specific Provider Decision is `REJECTED`, so no formal
hypothesis or downstream campaign started. WP-16 then audited the exact latest
main, environment, and accessible Provider/Product evidence and stopped at Gate
A because no accessible Product has direct recorded evidence for both P0
availability and finality floors. This is an external-evidence blocker, not a
vendor-wide incapability finding and not a new Provider Decision. The linked
immutable Verifications establish those separate results;
the containing documentation/merge SHA is reported by the final handoff rather
than self-referenced here.
This read model is invalid after any source, migration, test, or composition change until
regenerated. It cannot write business state or promote Provider, research,
qualification, trading, or Production claims.

## Current implementation truth

| Area | Current implementation fact at the WP-14 implementation checkpoint |
|---|---|
| Package shape | The legacy Python 3.12 modular monolith remains intact. Target `shared`, `runtime`, `market`, permanent `selection`, permanent `research_qualification`, permanent `decision_support`, permanent `outcome`, `infrastructure`, `interfaces`, and sole target `bootstrap.py` are isolated by dependency tests; each owner keeps Domain/Application/ports while PostgreSQL adapters remain in Infrastructure |
| PostgreSQL | The canonical business implementation remains legacy 001–106 with 283 tables. The target draft defines 129 tables and four read-only views under schema `mra` |
| Runtime | Continuous Research remains the current all-day business control plane. WP-14 composes exact Decision Proof and Due Proof profiles from existing Runtime/Application commands, but target Runtime business dispatch and CLI cutover remain absent |
| CLI | Six legacy scripts remain. `mra` exposes target DB bootstrap/verify/recreate and Runtime inspection/recovery, but no Market business cutover command |
| Market/PIT | Within the isolated target draft, Market is the sole writer of its draft facts and purpose-specific Provider Qualification Protocol/requirements/finality/decision/visibility. Engineering rehearsals cannot admit a Provider. Formal PIT requires an exact admitted recorded-provider decision and typed source identity; legacy remains canonical business implementation |
| Universe/Eligibility | Permanent target `market_regime_alpha.selection` owns explicit immutable scope, frozen membership, typed policy/rules, complete three-state assessment/reasons, exact Market lineage, and an independent narrow Selection UoW, all test-only |
| Candidate | Current legacy capabilities remain canonical. The target draft implements the five Selection-owned Candidate relations, deterministic Policy/Set writer, complete score matrix, independent Candidate UoW, Selection-owned Research-input port with Infrastructure adapter, and funnel/dossier queries; its local WP-07 engineering exit gate passes at `029c269` |
| Research/Qualification | Current legacy capabilities remain canonical. Permanent target `market_regime_alpha.research_qualification` retains WP-11/WP-12 Authority and adds immutable Formal Campaign predeclaration, complete FIT/VALIDATION/LOCKED_OOS plans, actual Partition/Experiment binding, protected zero-access opening, database-clock due inspection, and read-only reconciliation. Model/Calibration remain absent |
| Decision/Outcome | Current legacy capabilities remain canonical. Permanent target `market_regime_alpha.decision_support` implements the sole immutable Decision Run per Candidate Set, explicit later-generation Qualification roster, PIT Context, Strategy, Signal, uncalibrated rule Forecast, Opportunity, Thesis, complete Portfolio and Decision-Support-only Risk. Permanent `market_regime_alpha.outcome` retains one commitment-bound Market Target Outcome root, append-only full revisions, exact rosters, dual cutoffs, pure Decimal settlement, typed replay/reconciliation, and a narrow read-only port; all remain test-only before cutover |
| Execution/Account | Human/manual execution only; observed effective Fill remains the source of trade-caused Position. No target implementation was added |
| Target epoch | Foundation through WP-14 Formal Research Engineering Readiness are implemented in mutable `MRA_REFOUNDATION_1`; the first WP-15 recorded BaoStock Provider scope is rejected; WP-16 stops before implementation because no accessible inspected Product has P0 `F/F` evidence; Formal PIT/OOS/Prospective/Alpha remain unproven, and Model/Calibration, Execution, and Runtime/CLI Cutover remain absent |
| Legacy | Old source, 001–106 migrations, CLIs, compatibility paths, and tests remain physically present as the current implementation and regression oracle |

The convergence state is therefore
`WP14_EXIT_GATE_PASS / FORMAL_RESEARCH_ENGINEERING_READY / WP15_PROVIDER_GATE_REJECTED / WP16_GATE_A_BLOCKED / FORMAL_CAMPAIGN_STOPPED / NOT_CUT_OVER`.
Similar legacy vocabulary does not make an old owner part of the target, and
target test writes do not become canonical business writes.

## Target draft catalog

Foundation retains its 13 relations:
`schema_epoch`, `schema_migrations`, `command_receipt`, `runtime_schedule`,
`runtime_run`, `runtime_step`, `runtime_step_dependency`, `runtime_attempt`,
`audit_event`, `artifact`, `artifact_dependency`, `artifact_verification`, and
`artifact_gc_candidate`.

Market/PIT adds exactly the approved 12 relations:
`provider`, `provider_product`, `data_capture`, `instrument`,
`instrument_identifier`, `trading_session`, `classification`,
`classification_membership_revision`, `market_bar_revision`,
`instrument_fact_revision`, `corporate_action_revision`, and `source_gap`.

Selection Core adds exactly seven tables:
`universe`, `universe_revision`, `universe_member`, `eligibility_policy`,
`eligibility_rule`, `eligibility_assessment`, and `eligibility_reason`.

Research Definition Core adds exactly three tables: `feature_definition`,
`dataset`, and `dataset_source`.

Candidate Closure adds exactly five Selection-owned tables: `candidate_policy`,
`candidate_policy_component`, `candidate_set`, `candidate`, and
`candidate_score_component`.

Target Definition adds exactly four Research-owned tables:
`target_definition`, `target_checkpoint`, `target_metric_definition`, and the
explicit normalization correction `target_metric_dependency`. Decision Support
adds exactly four tables: `decision_run`, `decision_run_target`,
`decision_target_commitment`, and `decision_reference_observation`.

Market Target Outcome adds exactly eight Outcome-owned tables:
`market_target_outcome`, `market_target_outcome_revision`,
`market_target_outcome_source`, `market_target_outcome_observation`,
`market_target_outcome_metric`, `market_target_outcome_metric_reference`,
`market_target_outcome_metric_observation`, and
`market_target_outcome_reason`. The split between reference and observation
dependencies is the explicit WP-10 relational normalization correction; it
raises the WP-08 logical destination catalog from 117 to 118 relations without
moving dependency semantics into JSON.

WP-11 adds exactly twelve Research-owned tables:
`research_partition`, `research_partition_member`, `experiment`,
`experiment_partition`, `experiment_run`, `evaluation_protocol`,
`evaluation_protocol_metric`, `evaluation_run`,
`research_partition_outcome_access`, `evaluation_observation`,
`evaluation_metric`, and `evaluation_metric_observation`.

WP-12 adds exactly ten Research-owned tables: `evidence_item`,
`evidence_dependency`, `research_assessment`,
`research_assessment_evaluation`, `research_assessment_evidence`,
`research_qualification_policy`, `research_qualification_policy_floor`,
`research_qualification_decision`, `research_qualification_floor_result`, and
`research_qualification_floor_evidence`. No Model, Calibration, Forecast
binding, generic subject, compatibility, JSON business owner, or placeholder
relation is added.

WP-13 adds exactly 30 Decision-Support-owned tables. Qualification input adds
`decision_run_research_qualification_roster` and
`decision_run_research_qualification_member`. Context adds `context_policy`,
`context_policy_metric`, `context_assessment`, `context_metric`, and
`context_metric_source`. Strategy adds `strategy`, `strategy_version`,
`strategy_context_requirement`, `strategy_signal_rule`, and
`strategy_forecast_rule`. Inference adds `signal_run`, `signal`,
`signal_context_binding`, `forecast_run`, `forecast`, and `forecast_estimate`.
Opportunity/Thesis adds `opportunity_set`, `opportunity`,
`opportunity_context`, `thesis`, and `thesis_condition`. Portfolio adds
`portfolio_policy`, `portfolio_proposal`, and `portfolio_line`. Risk adds
`risk_policy`, `risk_rule`, `risk_decision`, and `risk_reason`. No Model,
Calibration, Account, Execution, broker, Order, Fill, Position mutation, or
future placeholder relation is added.

WP-14 adds exactly 21 tables. Market adds
`provider_qualification_protocol`, `provider_qualification_requirement`,
`provider_finality_observation`, `provider_qualification_decision`,
`provider_qualification_capture_member`, and
`provider_qualification_requirement_result`; five source-specific
`qualified_*_visibility` tables freeze admitted historical visibility.
Research & Qualification adds `formal_research_campaign` plus its partition
plan, Evaluation Protocol, cost assumption, Provider Decision, actual
Partition, Experiment, protected-open, and Runtime Run bindings. Formal
Dataset adds `formal_research_dataset`. No generic Campaign framework, Model,
Calibration, Execution, future nullable FK, or compatibility table is added.

The four replaceable views are `candidate_component_diagnostic`,
`candidate_funnel`, `run_trace`, and `artifact_integrity_status`. The
implementation-defined draft shape is 129 tables, four views, 963 indexes,
1,349 constraints, 105 functions, 268 non-internal triggers, and 2,819 catalog
objects.
Its baseline checksum is
`df75c594bba25ab293723af615fcdad8f5b64781fddaf716f6fe586fffc8bc85`, its
seed checksum is
`9c41cd715e35e1a7bed3a58c52a29f01cc1e9bf950b77344bb56eac6dfa2df11`, and its
reference-vocabulary checksum is
`52fd044a72334fe7334bacd7f5ef96cff72244f3f89fab1c48bcfa4ee095d0a6`.
A clean PostgreSQL 16 bootstrap/verify used by exact-SHA WP-14 qualification produced
catalog checksum
`1d58cbace3120fb0c7048900bb5e162df8dfc40c2b4a26337b2e562093f03714`.
Clean bootstrap, exact-OID recreate, concurrency, failure/recovery, replay,
representative plans, full regression, static and build gates pass at the
linked WP-14 Verification. Table count is descriptive, not an optimization
target.

## Market/PIT implementation truth

- Provider network I/O and content-addressed byte publication/verification run
  outside PostgreSQL transactions.
- One short Market UoW first locks and validates a participating Runtime claim,
  then atomically owns the business facts, command receipt, audit event, and
  matching Runtime Step finalization.
  A stale fence rolls all relational writes back; published bytes remain a
  discoverable, two-pass-GC orphan.
- `data_capture` keeps provider, source-availability, capture, PostgreSQL
  recording, knowledge, and Decision-visible time distinct. PostgreSQL enforces
  `known_at = greatest(capture_completed_at, recorded_at)` and, for the current
  unqualified products, `decision_visible_at = known_at`.
- Tencent preserves exact GB18030 response bytes. BaoStock preserves a
  deterministic captured representation and
  `HISTORICAL_AVAILABLE_TIME_NOT_PROVIDED`. Neither adapter can exceed
  `EXPLORATORY_UNQUALIFIED`.
- Raw, forward-adjusted, and backward-adjusted bars are separate series using
  `numeric`/`Decimal`. Revisions are append-only; owner queries select exact
  as-of facts without caller-controlled “latest.”
- Missing, placeholder, provider failure, conflict, and invalid OHLC are typed
  gaps. A placeholder creates no valid bar. Missing/zero-volume/flat-price do
  not infer suspension.
- Market exposes only generic exact/as-of bar, fact, classification, lifecycle,
  gap, and session queries. Decision Support declares its narrow read-only
  Decision-reference port; an Infrastructure adapter resolves only the exact
  requested Target checkpoint and Provider Product to a concrete bar revision
  or Source Gap. Market owns neither Target business semantics nor Decision
  writes, and current reference finality is frozen honestly as `UNKNOWN`.
- `data_capture` is a canonical Artifact reference and therefore protects its
  bytes from orphan classification and garbage collection. Foundation retains
  exact identity plus hash/size/existence/integrity verification. The 24-hour
  cadence is now explicitly a Market consumer read policy; a Selection scope
  configuration needs Foundation integrity but does not inherit that Market
  engineering cadence. Market stale evidence remains unavailable to a Market
  consumer until an outside-transaction verification is committed.

## Selection Core implementation truth

- `FreezeUniverse` accepts only an explicit immutable scope specification bound
  by exact Artifact id/hash/size plus Market Product and Classification
  identity. It never discovers “all current instruments.” Every scoped
  instrument produces `INCLUDED`, `EXCLUDED`, or `UNKNOWN`; missing, stale,
  gap, or conflicting PIT membership is persisted rather than dropped.
- Universe owns research range only. Suspension, special-treatment status,
  listing age, liquidity, and limit metadata are Eligibility criteria and never
  Universe exclusions.
- An immutable Eligibility policy explicitly records each rule's measure,
  aggregation, window value/unit, typed threshold, operator, value unit, and
  missing-result behavior. Financial values use PostgreSQL `numeric` and
  Python `Decimal`; no float/materializer/artifact architecture was copied.
- Every member executes every rule without short circuit. Every rule produces a
  typed `PASS`/`FAIL`/`UNKNOWN` reason with the observed typed value, copied
  criterion semantics, reason code, exact Market revision/bar/gap/session/
  Capture lineage, and lineage hash. Aggregation is fixed: any FAIL is
  `INELIGIBLE`; otherwise any UNKNOWN is `UNKNOWN`; otherwise `ELIGIBLE`.
- A Selection UoW owns only Selection repositories plus a narrow Market query
  port and minimal receipt/audit/live-fence/finalization ports. A successful
  business write, receipt, audit, matching fence, and Runtime Step finalization
  share one short transaction. Runtime and Market UoWs were not expanded.
- Representative plans execute through the classification membership,
  instrument fact, Market bar, Universe member status, and Eligibility result
  indexes. Tests assert executed owner relations/index availability, not fixed
  optimizer costs or node shapes.

## Research Definition Core implementation truth

- The permanent target namespace is
  `market_regime_alpha.research_qualification`; legacy `research`, `features`,
  and Candidate persistence remain invariant sources only and cannot be target
  dependencies or compatibility paths.
- Research Definition Core retains exactly `dataset`, `dataset_source`, and
  `feature_definition`. WP-09 additionally adds the four Target Definition
  relations through a separate Target registration command/repository/UoW seam.
  Partition, Experiment, Evaluation, Evidence, Assessment, and Qualification
  now belong to the same bounded context through cohesive modules and separate
  narrow UoWs. Model, ModelVersion, Calibration, and later Research contexts
  remain absent; Candidate remains a separately implemented Selection owner.
- A target Dataset is a Decision-input Dataset. At one DecisionTime its
  instrument rows must equal, without omission or addition, the intersection
  of `UniverseMember = INCLUDED` and
  `EligibilityAssessment = ELIGIBLE`. Missing Feature observations remain
  explicit typed cells and never remove an instrument.
- The Dataset manifest parser rejects Target, Outcome, return, MFE, MAE,
  barrier, future-observation, realized-label, and other posterior fields.
  Dataset source roles are closed, use concrete owner foreign keys, and must
  reconcile exactly with manifest lineage; no polymorphic string identity,
  generic business-lineage JSON, future nullable identity, or Registry
  exists.
- Runtime command failure uses one narrow cross-context contract: the failed
  business transaction rolls back, then a fresh short owner UoW validates the
  live fence before atomically writing the failed receipt, audit, and matching
  Attempt/Step failure. The contract owns no command dispatch or Domain-error
  interpretation.

## Target Definition implementation truth

- `TargetDefinition` is a provider-neutral immutable version. It freezes exact
  instrument/market scope, ordered checkpoints, timing/horizon/reference rules,
  price/value basis, availability/finality rules, ordered typed metrics and
  normalized dependencies, algorithm identity, and exact code/config Artifact
  bindings. Canonical hashes are computed from typed facts, not caller input.
- Target closure is relational and Target-owned. Child rows are inserted first
  only inside the registration transaction; inserting the root invokes a
  closure guard that checks positive counts, contiguous ordinals, complete
  roster hashes, exact dependency roles, and required reference/observation
  checkpoints. A receipt is idempotency/audit evidence, never closure Authority.
- Versions are append-only. Version one has no predecessor; every later version
  binds one unique immediately preceding Target through
  `supersedes_target_definition_id`. Update/delete triggers protect roots and
  children, and no provider/product identity is stored on the Target.
- `ResearchQualificationApplication.register_target_definition(...)` is only a
  facade over `TargetDefinitionCommands`. Target has its own repository,
  Artifact port, reconciliation port, and `TargetUnitOfWorkProvider`; the
  Dataset/Feature UoW was not expanded into a Research lifecycle God UoW.
- Exact retry returns the original Target/receipt/result. Reusing the same
  request identity with changed typed content fails closed; concurrent
  registration has one canonical writer, and rollback leaves no orphan child,
  root, receipt, or audit.

## Candidate Closure implementation truth

- Permanent `market_regime_alpha.selection` owns exactly Candidate Policy,
  Policy Component, Candidate Set, Candidate, and Candidate Score Component.
  Candidate uses an independent narrow UoW; Runtime, Selection Core, and Research
  UoWs were not widened.
- Policy components bind real numeric Feature Definitions. Candidate Set binds
  one immutable Decision-input Dataset, which remains the sole population and
  already proves same-DecisionTime `INCLUDED` plus `ELIGIBLE` membership.
- Every Dataset row receives `SELECTED`, `RANKED_NOT_SELECTED`, or `UNRANKABLE`
  and one typed score row per Policy Component. Required unavailable cells remain
  `UNRANKABLE` without imputation or silent row deletion.
- V1 converts canonical declared Decimal weights to exact rational normalized
  weights. Only the projected normalized weight is stored on score rows, with
  no dynamic redistribution. Arithmetic-midrank normalization, competition
  rank, explicit Top-K, and `INCLUDE_ALL_BOUNDARY_TIES` never use identity to
  break a score tie.
- Selection declares the immutable Research-input DTO/port. Infrastructure maps
  Dataset/Feature definitions and verifies/reads/parses Dataset Artifact bytes;
  byte I/O and ranking occur outside the final PostgreSQL write transaction.
- Public `BuildCandidateSet` requires a real keyword-only Runtime claim.
  Preflight, fresh binding, and successful replay validate the exact claimed Step
  key and persisted `BUILD_CANDIDATE_SET` Step kind before any Candidate effect.
- The final short Candidate transaction owns the live fence, CandidateSet
  identity advisory lock, exact dependency revalidation, and one globally
  UUID-ordered acquisition of each distinct Artifact using the strongest
  required mode. A fresh Dataset manifest is locked for verification; other
  distinct Artifact dependencies are shared-locked. Candidate writes and
  reconciliation, receipt, verification binding, audit, matching Attempt/Step
  finalization, and commit follow in the same transaction.
- Exact successful replay does not reread Artifact bytes, rerank, append audit,
  or rewrite Candidate Authority. An existing failed receipt preserves its
  original error and receipt while terminalizing the new live Attempt; it creates
  no Candidate result, rejection receipt, or duplicate audit.
- `candidate_funnel` and Candidate dossier queries expose complete population,
  rankability, disposition, component, boundary, and Dataset-source lineage
  facts without becoming Authority.
- This is an engineering implementation statement only. At `029c269`, all 82
  Candidate-focused tests and the complete 3,330-node legacy-plus-target
  collection pass, together with clean PostgreSQL bootstrap/verify/recreate,
  concurrency/recovery/replay, representative query plans, architecture, docs,
  Ruff, mypy, build, checksum, and diff gates. The linked WP-07 Verification
  owns the exact commands and proof ceiling; Remote CI remains
  `BLOCKED_BY_REPOSITORY_CONFIGURATION / NOT_RUN`.

## Decision Run commitment implementation truth

- Permanent `market_regime_alpha.decision_support` owns the only
  `OpenDecisionRun` command. Decision Domain/Application depend only on their
  typed Candidate, Target, Market-reference, Runtime-fence, repository, and UoW
  ports; PostgreSQL adapters implement those ports. No Legacy module is a target
  runtime dependency.
- One immutable Candidate Set can produce exactly one canonical Decision Run.
  The request carries a non-empty ordered Target/version plus reference Product
  roster. Exact retry returns the original Run; the same idempotency identity
  with changed content and any second request for that Candidate Set fail
  closed.
- The short write transaction locks the live Runtime Run/Step/Attempt fence
  first, then serializes the Candidate Set identity, locks/revalidates all
  prepared immutable dependencies, and writes the complete root-last closure.
  Provider, network, filesystem, and Artifact-byte I/O do not occur inside it.
- Every Candidate disposition participates in the exact Candidate × Target
  cross-product. An empty Candidate Set is valid and yields zero commitments;
  an empty Target roster is rejected. Each commitment has exactly one reference
  observation through reciprocal composite FKs.
- The reference is either one exact `market_bar_revision` or one exact
  `source_gap`. It binds instrument, Target decision checkpoint, requested
  Provider Product, event/observation/source-recorded/known-at times and
  independent value/availability/finality states. `known_at <= DecisionTime` is
  enforced; current finality is honestly `UNKNOWN`; no latest, zero,
  previous-day, repair, or later replacement path exists.
- Decision Run freezes Candidate/Target/commitment/reference counts and canonical
  hashes, Runtime mode, DecisionTime, PostgreSQL authoritative
  `commitment_recorded_at`, exact Run/Step/Attempt/fence identity, request
  identity/hash, receipt, audit, and definition summary. Append-only guards and
  composite FKs prevent cross-Run, cross-CandidateSet, cross-Target, or
  cross-instrument rebinding.
- Retry is bounded to three whole transactions for SQLSTATE `40001`/`40P01`.
  Unknown commit outcome resolves only through exact command replay.
  Deterministic failure rolls back business facts, then a fresh short UoW
  revalidates the live fence and records failure atomically; stale fence means
  zero business and zero failure writes.
- The typed verifier is read-only, uses only frozen rows and exact FKs, and
  distinguishes missing/extra/order/count/hash/identity/reference/Runtime and
  immutable-fact mismatches. Successful replay/reconciliation is
  `matched=true`, `mismatch_count=0`; it performs no Provider/latest lookup and
  mutates no Authority.
- At `9a21d5d`, all 85 WP-09 focused nodes, 668 PostgreSQL owner nodes, all 33
  platform nodes, and the complete 3,389-node repository collection pass with
  clean bootstrap/verify/recreate, concurrency/failure/recovery/replay,
  representative plans, architecture/import, docs, Ruff, mypy, build, checksum,
  and diff gates. The linked WP-09 Verification owns exact commands and proof
  ceilings; Remote CI is
  `BLOCKED_BY_REPOSITORY_CONFIGURATION / NOT_RUN`.

## Market Target Outcome implementation truth

- Permanent `market_regime_alpha.outcome` owns the only
  `SettleMarketTargetOutcome` writer. Its Application depends on immutable
  Decision/Target/Market/Runtime facts only through Outcome-owned typed ports;
  PostgreSQL adapters live in Infrastructure. The package's public consumer
  surface exports only `OutcomeReadPort` and `OutcomeSnapshot`.
- One Decision Target Commitment has at most one stable Outcome root. A due
  settlement appends one complete revision snapshot; correction, source
  improvement, coverage change, or finality change names the current leaf and
  appends the next contiguous ordinal. Unique direct supersession, root/head
  locking, predecessor validation, and append-only guards prevent a fork or
  historical mutation.
- `NOT_DUE` is a query result with `database_writes=0`; it is not persisted as
  an unavailable placeholder. Due revisions keep aggregate status
  `PARTIAL`/`COMPLETE`/`UNAVAILABLE`/`FAILED`, availability, and finality as
  independent axes. Current source finality is honestly `UNKNOWN`.
- Every revision freezes separate `observation_cutoff` and `knowledge_cutoff`.
  Exact Session/bar/SourceGap rows must satisfy
  `event_end <= observation_cutoff` and `known_at <= knowledge_cutoff`.
  Target checkpoint order and scope, exact Product/Capture provenance, source
  roster, and every count/hash are revalidated before relational closure.
- `REFERENCE` dependencies concrete-FK the immutable WP-09
  `decision_reference_observation`; `OBSERVATION` and `PATH_MEMBER`
  dependencies concrete-FK an observation in the same Outcome revision. No
  generic dependency table, polymorphic subject, JSON roster, reference
  recomputation, latest lookup, Provider repair, or previous-session fallback
  exists.
- One pure I/O-free Decimal kernel is the only target bars-to-realized-fact
  calculator. It produces checkpoint observations, simple return, MFE, MAE,
  barrier/first-passage state, explicit same-bar ambiguity, source/metric
  reasons, and required/optional roll-up. Legacy algorithms are imported only
  by a characterization test and never by target runtime code.
- Provider/network/filesystem work is absent from settlement. Preparation is
  outside the short transaction; the transaction locks the live Runtime fence
  first, revalidates immutable Target/Market/Candidate/Decision dependencies,
  serializes the Outcome root/head, writes one full root-last closure plus
  receipt/audit/Runtime finalization, reconciles it, and commits.
- Exact retry returns the original revision and appends no facts or audit.
  Changed reuse of an idempotency identity fails closed. Corrections require
  the exact current leaf. Concurrent same requests have one writer and replay;
  concurrent corrections cannot fork. SQLSTATE `40001`/`40P01` retries the
  whole transaction at most three times; unknown commit state is resolved only
  by exact replay; stale fence causes zero business and zero failure writes.
- The verifier is read-only and reconstructs the root, full revision chain,
  cutoffs, exact commitment/reference/Target, all rosters/dependencies,
  counts/hashes, Runtime identity, receipt, and kernel result only from frozen
  rows. Success is `matched=true`, `mismatch_count=0`; no Provider/latest read
  or Authority mutation occurs.
- At `56812c58`, all 43 WP-10 focused nodes, 392 refoundation nodes, 33 platform
  nodes, 286 PostgreSQL persistence nodes, and the complete 3,432-node
  repository collection pass. Clean PostgreSQL bootstrap/verify/guarded
  recreate, representative `EXPLAIN (ANALYZE)`, concurrency, failure/recovery,
  replay/reconciliation, architecture/import, docs, Ruff, mypy, build, and diff
  gates pass. The linked WP-10 Verification owns exact commands and proof
  ceilings; Remote CI remains
  `BLOCKED_BY_REPOSITORY_CONFIGURATION / NOT_RUN`.

## WP-11 Research Validity and Evaluation implementation truth

WP-11 is engineering-qualified at
`07151542f12a66d6e7da3e228e2dbf1d7d7771bb`. The sole target composition root
constructs the Partition, Experiment, Evaluation, and read-only verification
Application modules. Runtime dispatch and CLI cutover remain absent.

- Gate A makes successful Target registration sufficient for Outcome contract
  reconstruction: all five metric kinds have the exact dependency shape and
  every Target has at least one `REQUIRED` metric in both Domain and PostgreSQL
  closure. WP-10 numerical and revision semantics are unchanged.
- The Partition UoW derives a commitment roster in PostgreSQL from exact
  Target, Decision window, and declared population scope without an Outcome
  read or caller-selected member list. One Partition freezes one explicit
  exchange calendar, exact boundary/protected Sessions, complete calendar
  count/hash, session-based horizon/purge/embargo, purpose-compatible overlap,
  code/config, provenance, and complete member count/hash. Divergent XSHG/XSHE
  same-date rosters cannot mix.
- `PROSPECTIVE` validates the canonical Runtime live-clock lineage instead of a
  hard-coded allow-list, explicitly rejects Historical/Replay lineage, and
  requires PostgreSQL-recorded commitment time before the earliest Outcome
  event. Purpose alone is not prospective proof.
- The Experiment UoW atomically freezes a complete ordered non-empty Partition
  binding roster with exact Target/version/hash, typed purpose, contiguous
  order, count/hash, root/child reconciliation, exact replay, no duplicates,
  and no late binding. An Experiment Run binds one concrete roster child.
- The Evaluation UoW alone owns Protocol/metrics, Evaluation Run, Outcome
  access, observations, and metrics. Exact Target and protected-purpose
  ordering are guarded by concrete FKs, lifecycle checks, zero-access guards,
  PostgreSQL authoritative time, and transaction locks.
- `AcquireOutcomeInputs` privately resolves one exact revision visible at the
  requested knowledge cutoff. It locks the complete roster, appends globally
  monotonic member access ordinals, writes one observation per member,
  reconciles, and transitions to `INPUTS_ACQUIRED` in one short transaction.
  No Outcome value escapes first; there is no current/latest, Provider, Market
  repository, bar, or label-builder path. `UNAVAILABLE`/`FAILED` remain samples;
  `NOT_DUE`, missing due revisions, ambiguity, or incomplete roster fail closed.
- Pure post-acquisition Evaluation implements `MEAN_DECIMAL`,
  `MEDIAN_DECIMAL`, `TRUE_RATE`, and `ESTIMABLE_RATE` with frozen source-type
  compatibility and exact Candidate disposition slices. Completion requires
  the full protocol-metric × observation roster with explicit `INCLUDED`,
  `EXCLUDED`, or `NOT_ESTIMABLE` state and reason.
- The permanent read-only verifier recomputes Target parity, Partition
  roster/calendar/bounds, complete Experiment bindings, Protocol metrics,
  Evaluation lifecycle, global access ordinal chain, exact revisions,
  observation and metric rosters, Cartesian inputs, receipt/audit/fence, and
  provenance. Passing is `matched=true`, `mismatch_count=0`; it uses no
  Provider, current/latest, Market reconstruction, or mutation.
- Exact-SHA qualification passes 163 focused, 492 refoundation, 33 platform,
  286 PostgreSQL persistence, and all 3,532 repository tests, plus clean
  bootstrap/recreate, real concurrency/failure/recovery/unknown-commit replay,
  representative plans, Ruff, mypy, build, docs, architecture/import, and diff
  gates. Remote CI is `BLOCKED_BY_REPOSITORY_CONFIGURATION / NOT_RUN`.

## WP-12 Evidence, Assessment and Qualification implementation truth

WP-12 is engineering-qualified at
`48949c87ad0241a8d60031137bc3aa8eb9887525`. All ownership remains inside
permanent `market_regime_alpha.research_qualification`, with separate narrow
Evidence, Assessment, and Qualification UoWs and PostgreSQL Infrastructure
adapters. The sole target composition root exposes the command and read-only
verification seams; Runtime dispatch and CLI cutover remain absent.

- Evidence items concrete-FK exact terminal Evaluation Runs, immutable
  Artifacts, and exact same-Run Evaluation Metrics when metric-scoped.
  Dependency edges form an immutable ordered Evidence-only DAG with complete
  count/hash closure and typed support, counter-evidence, and neutral facts.
- Assessment accepts one exact Experiment, derives every terminal Evaluation
  and all corresponding Evidence by a PostgreSQL-authoritative cutoff, freezes
  complete ordered child rosters, and preserves failed, negative,
  inconclusive, and not-estimable conclusions. Supersession appends a new
  revision and cannot rewrite or fork history.
- Purpose-specific Policy floors relationally freeze exact Evaluation
  purpose/state, Protocol metric/slice, operator/threshold, minimum sample and
  estimable counts, missing/not-estimable policy, and Evidence requirements.
  No business threshold or owner is hidden in JSON.
- Every Qualification Decision binds one exact Assessment and Policy, writes
  one explicit result for every floor and the exact Assessment Evidence used
  by each floor, and reconciles all child/root hashes before a closed
  `ADMITTED`, `REJECTED`, or `INCONCLUSIVE` status. Admission grants only the
  declared Research purpose.
- Generation guards require source Outcome generation before effective time,
  which is no later than known and PostgreSQL-recorded time. The narrow read
  port requires an exact admitted Decision ID, cutoff, purpose, and later
  DecisionTime; no current/latest lookup or same-generation DecisionRun edge
  exists.
- The verifier recomputes Evidence identities/DAG, complete Assessment rosters,
  Policy floors, Decision results/exact Evidence bindings, supersession,
  generation, Artifact/receipt/audit/fence/provenance, and hashes without
  Provider, Market reconstruction, current/latest, or mutation.
- Exact-SHA qualification passes 216 focused, 545 refoundation, 33 platform,
  286 PostgreSQL persistence, and all 3,585 repository tests, plus clean
  bootstrap/recreate, concurrency/failure/recovery/unknown-commit replay,
  representative plans, Ruff, mypy, build, docs, architecture/import, and diff
  gates. Remote CI is `BLOCKED_BY_REPOSITORY_CONFIGURATION / NOT_RUN`.

## WP-13 Remaining Decision Support implementation truth

WP-13 is engineering-qualified at
`fc5993e5d9e05dbe2845659140108e1051cf3704`. All new owners remain cohesive
modules inside permanent `market_regime_alpha.decision_support`, with their
typed ports implemented by PostgreSQL Infrastructure adapters. The sole target
composition root constructs the commands and read-only verifier, but Runtime
dispatch and business CLI cutover remain absent.

- `OpenDecisionRun` freezes an explicit zero-or-more later-generation Research
  Qualification roster. Each member is an exact matching-purpose `ADMITTED`
  decision, known/effective by DecisionTime, not then superseded, and sourced
  from a strictly earlier Outcome generation. There is no current/latest read.
- Context policies and assessments freeze complete typed Market Regime, ETF,
  Theme, and Capital/Breadth metric/source rosters with exact PIT Market
  lineage, known time, availability, and missingness. Context never reads
  Outcome.
- immutable Strategy Versions freeze the primary change, Context requirements,
  Signal rule, complete Target/checkpoint/metric Forecast rules, code/config,
  and provenance. Signal and Forecast roots remain explicit for empty
  Candidate populations; Forecast is rule-based and uncalibrated without a
  Model placeholder.
- Opportunity binds the complete Forecast roster and exact Candidate, Signal,
  Context, Strategy, Target, and commitment facts. Thesis revisions contain
  typed independently falsifiable conditions.
- Portfolio Proposal retains one explicit line for every Opportunity and uses
  Decimal weights. Risk evaluates only that complete Proposal under every
  global or rule × line input, preserves rejection/unknown/no-action, and has
  constant `DECISION_SUPPORT_ONLY` scope.
- the read-only verifier recomputes all upstream and WP-13 rosters, ordinals,
  Cartesian inputs, hashes, exact FK identities, receipts, audits, fences, and
  provenance without Provider, current/latest, Outcome access, Market
  reconstruction, or mutation.
- exact-SHA qualification passes 51 focused, 585 refoundation, 33 platform,
  286 PostgreSQL persistence, and all 3,625 repository tests, plus clean
  bootstrap/recreate, real concurrency, injected failure rollback,
  unknown-commit exact probe/replay, representative plans, Ruff, mypy, build,
  docs, architecture/import, and diff gates. Remote CI is
  `BLOCKED_BY_REPOSITORY_CONFIGURATION / NOT_RUN`.

## WP-14 Formal Research engineering readiness truth

WP-14 is engineering-qualified at
`ca6f66b50ec2c55250cd82d2fa1ed6c5f35c29b8`. It reuses the existing Runtime,
Market, Research & Qualification, Outcome, and Decision Support owners.

- exact Decision Proof and Due Proof Runtime DAGs are immutable and database-
  checked; the sole composition root exposes the required commands and read
  seams without adding Runtime business dispatch or CLI cutover;
- Formal Campaign predeclaration freezes exact Target, hypothesis, Provider,
  Decision Support baseline, FIT/VALIDATION/LOCKED_OOS plans, Evaluation
  Protocols, Qualification Policy, Decimal cost assumptions, code/config, and
  provenance in complete relational rosters;
- actual database-derived Partitions and the complete Experiment roster are
  bound before protected opening; one exact Experiment Run/Evaluation Run pair
  opens with PostgreSQL time and zero Outcome access;
- Market-owned Provider qualification derives every decision from a complete
  ten-requirement recorded-fact roster. `ENGINEERING_REHEARSAL` cannot admit a
  Provider or write qualified visibility;
- Formal PIT and Formal Dataset require an exact bound `RECORDED_PROVIDER +
  ADMITTED + HISTORICAL_PIT` decision and source-specific cutoff visibility;
  there is no current/latest or caller assertion path;
- database-clock due inspection preserves `NOT_DUE`, `DUE`, `MISSING`, and
  `SETTLED`; historical/replay facts cannot masquerade as Prospective;
- the read-only verifier recomputes campaign/provider rosters, Runtime DAGs,
  protected first-access ordering, downstream WP-11/WP-12 closure, receipts,
  audit, fences, and hashes without Provider I/O, mutation, or reconstruction;
- exact-SHA qualification passes 19 focused, 604 refoundation, 33 platform,
  286 PostgreSQL persistence, and all 3,644 repository tests, plus clean
  bootstrap/recreate, concurrency/failure/recovery/replay, six representative
  plans, Ruff, mypy, build, docs, architecture/import, and diff gates. Remote
  CI is `BLOCKED_BY_REPOSITORY_CONFIGURATION / NOT_RUN`.

This proves `FORMAL_RESEARCH_ENGINEERING_READY = true` only. Formal PIT, Formal
OOS, Prospective value, Provider qualification, Alpha, and Production remain
unproven.

## WP-15 real Provider gate truth

WP-14 was merged through PR #97 as
`origin/main@8067a4be74f697a01aaa996465c10ed5b45b5a7f`. WP-15 fetched that exact
main in an independent worktree and executed one real BaoStock
`RECORDED_PROVIDER / HISTORICAL_PIT` gate for `sh.600519` raw five-minute bars.

The sole composition root ran a fenced `SHADOW` CAPTURE and committed one
verified 17,894-byte Artifact containing 144 real rows. PostgreSQL recorded
`known_at` from the acquisition clock while correctly retaining
`source_availability_status=UNKNOWN`, `source_available_at=NULL`, and
`provider_time=NULL`.

The immutable ten-floor Provider Decision is `REJECTED`. Coverage, exact
Runtime/raw lineage, acquisition known-time, and raw price basis passed.
Historical availability, revision finality, and the five-session Outcome path
failed. Trading calendar, membership status, and Decision-reference evidence
were insufficient. Protocol and Decision reconciliation both return
`matched=true, mismatch_count=0`.

```text
WP15_CAMPAIGN_EXECUTION = STOPPED_AT_PROVIDER_GATE
PROVIDER_QUALIFICATION = REJECTED
FORMAL_PIT / LOCKED_OOS = BLOCKED_BY_PROVIDER_GATE / NOT_RUN
RESEARCH_QUALIFICATION = BLOCKED_BY_PROVIDER_GATE / NOT_RUN
PROSPECTIVE_CAMPAIGN = NOT_STARTED
PROSPECTIVE_PROVEN / ALPHA_PROVEN = NO
```

Qualified visibility, Formal Campaign, Dataset, Research Partition,
Experiment, and Evaluation Run counts remain zero. The rejected capture and
Decision are preserved as negative evidence; another attempt requires adequate
external evidence and a new immutable Protocol/revision. Exact identities,
timestamps, floor results, command evidence, and the stop proof are recorded in
[WP-15](../references/WP-ARCHITECTURE-REFOUNDATION-15-Formal-Research-Proof-Campaign-Verification.md).

## WP-16 external Provider-evidence Gate A truth

WP-16 fetched merged `origin/main@16a4ab1d0d42a4144ef1bd1dcd15ac4ba5ab1087`
and audited actual credential/runtime/access availability plus the inspected
BaoStock, Tencent, Tushare, XtQuant, iFinD, Wind, JQData, RQData, and
AKShare/EastMoney Product surfaces. Its four-state matrix preserves direct
facts as `F`, exact-Product contract failures as `X`, unestablished capability
as `?`, and access-blocked capability as `B`.

No actually accessible Product has direct recorded evidence for both:

```text
HISTORICAL_AVAILABILITY = F
REVISION_FINALITY = F
```

The bounded result is therefore:

```text
WP16_GATE_A = BLOCKED
WP16 = BLOCKED_BY_EXTERNAL_PROVIDER_EVIDENCE
WP16_ENGINEERING_IMPLEMENTATION = NOT_STARTED_BY_GATE
NEW_PROVIDER_PROTOCOL = NOT_REGISTERED
NEW_PROVIDER_QUALIFICATION = NOT_RUN
FORMAL_PIT = BLOCKED
WP17 = NO-GO
```

iFinD's public QuantAPI documentation establishes historical/high-frequency
and some point-in-time interface feasibility, but this environment has no
usable SDK/client/license and the inspected public contract does not prove
exact historical-minute publication or revision/finality/version semantics.
XtQuant, Tushare, Wind, JQData, and RQData are likewise access-blocked here;
their `B/?` state is not a finding that the vendor is incapable.

No adapter, schema, Product, Protocol, Capture, Decision, or Formal PIT state
was added. Gate A may reopen only with a new secure credential/runtime/license,
a versioned vendor publication/finality contract, a new actual Product, or new
direct evidence that changes a `B/?` cell. The exact stop proof and re-entry
contract are recorded in the immutable
[WP-16 Gate A Verification](../references/WP-ARCHITECTURE-REFOUNDATION-16-Real-Provider-Evidence-Gate-A-Verification.md).

## Historical exact-SHA verification through WP-16

The immutable pre-refoundation ledger is
[WP-02](../references/WP-ARCHITECTURE-REFOUNDATION-02-Pre-Refoundation-Verification-Baseline.md),
the Foundation ledger is [WP-03](../references/WP-ARCHITECTURE-REFOUNDATION-03-Foundation-Verification.md),
the Market/PIT ledger is
[WP-04](../references/WP-ARCHITECTURE-REFOUNDATION-04-Market-PIT-Verification.md),
the Selection checkpoint is recorded in
[WP-05](../references/WP-ARCHITECTURE-REFOUNDATION-05-Selection-Core-Verification.md).
The Research Definition commands, failure contract, catalog, full validation,
non-final attempts, and proof ceilings are recorded in
[WP-06](../references/WP-ARCHITECTURE-REFOUNDATION-06-Research-Definition-Core-Verification.md).
Candidate closure and its own exact ceiling are recorded in
[WP-07](../references/WP-ARCHITECTURE-REFOUNDATION-07-Candidate-Closure-Verification.md).
Target commitment and Decision Run closure are recorded in
[WP-09](../references/WP-ARCHITECTURE-REFOUNDATION-09-Target-Commitment-Decision-Run-Verification.md).
Market Target Outcome closure and its proof ceiling are recorded in
[WP-10](../references/WP-ARCHITECTURE-REFOUNDATION-10-Market-Target-Outcome-Verification.md).
Research Validity and Evaluation closure and its proof ceiling are recorded in
[WP-11](../references/WP-ARCHITECTURE-REFOUNDATION-11-Research-Validity-Evaluation-Verification.md).
Research Evidence, Assessment and Qualification closure and its proof ceiling
are recorded in
[WP-12](../references/WP-ARCHITECTURE-REFOUNDATION-12-Research-Evidence-Assessment-Qualification-Verification.md).
Remaining Decision Support closure and its proof ceiling are recorded in
[WP-13](../references/WP-ARCHITECTURE-REFOUNDATION-13-Remaining-Decision-Support-Verification.md).
Formal Research/OOS/Prospective engineering readiness and its empirical ceiling
are recorded in
[WP-14](../references/WP-ARCHITECTURE-REFOUNDATION-14-Formal-Research-Engineering-Readiness-Verification.md).
The first real Provider gate and its negative empirical ceiling are recorded in
[WP-15](../references/WP-ARCHITECTURE-REFOUNDATION-15-Formal-Research-Proof-Campaign-Verification.md).
The bounded external Provider-evidence feasibility stop and re-entry contract
are recorded in
[WP-16](../references/WP-ARCHITECTURE-REFOUNDATION-16-Real-Provider-Evidence-Gate-A-Verification.md).

Each immutable ledger owns only its recorded exact-SHA evidence. Earlier
checkpoint counts and checksums remain historical facts inside those ledgers;
they are not current catalog or regression claims. At WP-16, GitHub Actions
remains disabled, so remote CI is
`BLOCKED_BY_REPOSITORY_CONFIGURATION / NOT_RUN`, not PASS. No current or
historical gate admits a Provider or proves Alpha/OOS, broker, trading,
sustained Prospective value, Production, or Runtime/CLI Cutover evidence.

## Research and production ceiling

```text
target_release_state = DRAFT
runtime_cli_cut_over = false
provider_qualification_established = false
formal_pit_established = false
formal_oos_alpha_supported = false
entry_model_empirically_validated = false
broker_integration_proven = false
automatic_order_execution = false
sustained_prospective_value_proven = false
production_ready = false
```

## Refresh contract

A future Current State must obtain facts read-only from Git identity, the
configured schema epoch/migration registry, code-owned inventories, executed
test receipts, and canonical Evidence IDs/hashes. It receives no database write
credentials and cannot infer “current” from filenames, latest rows, documents,
or Artifact directories.
