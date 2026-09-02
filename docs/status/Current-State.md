# Current State

> **Status:** CURRENT_STATUS
> **Authority:** Non-authoritative implementation status read model; exact-SHA engineering proof remains in Verification
> **Owner:** Market Regime Alpha maintainers
> **Generated At:** 2026-09-02 WP-12 exact-SHA engineering qualification reconciliation
> **Repository Implementation Checkpoint:** `48949c87ad0241a8d60031137bc3aa8eb9887525`
> **Merged Main Checkpoint:** `6e0ad150057e43a89843eb4fb307e0373d5572ac`
> **Containing Documentation Commit:** reported by the final handoff; this read model does not claim a self-referential Git SHA
> **Previous Verified Snapshot:** merged WP-11 at `07151542f12a66d6e7da3e228e2dbf1d7d7771bb`
> **Implementation Line Start:** `c3ac21ef1e13f2e8408d30b0481fa9b74c4f9539`
> **Foundation Source Checkpoint:** `eeff49c7a3995ba6d65045be88d4244617301234`
> **Legacy Business Implementation Parent:** `0382dad416d6d50d1eea0bda1603d7c359d65274`
> **Schema Epochs:** canonical business `LEGACY_MIGRATIONS_001_106`; target draft `MRA_REFOUNDATION_1 / DRAFT / NOT_CUT_OVER`
> **Generator:** `WP-ARCHITECTURE-REFOUNDATION-12 engineering qualification reconciliation; non-authoritative read model`
> **Source Tree IDs:** root `b81e4c2ae29ff0f6b26c15333004b849ebc56431`; source `baa201bfdd4540ad0a63dc4f0f3274eed2199db1`; tests `906f0e59aea13218bfb461ffb967685fe57bb64e`; Research & Qualification tree `94b0c082a8db37ba3e1734834aa4154e3df3fff0`; target baseline blob `b7fe5192a1df0c5733842c632a70e2d88db80d91`; legacy migrations tree `6d3730548780ad6244d2cfecb4fb3559064b6f06`
> **Code Evidence:** target and legacy source/migration packages, `tests`, [WP-12 canonical design](../references/WP-ARCHITECTURE-REFOUNDATION-12-Research-Evidence-Assessment-Qualification-Design.md), and [WP-12 immutable Verification](../references/WP-ARCHITECTURE-REFOUNDATION-12-Research-Evidence-Assessment-Qualification-Verification.md)

This read model records the WP-12 Evaluation-bound Evidence, complete
Experiment Assessment, purpose-specific Research Qualification, and
generation-safe admission-read implementation and exact-SHA engineering
qualification. The linked immutable Verification establishes the exit gate and
the merged main SHA above contains that exact WP-12 checkpoint. WP-13 Remaining
Decision Support is authorized but not yet implemented in this snapshot.
This read model is invalid after any source, migration, test, or composition change until
regenerated. It cannot write business state or promote Provider, research,
qualification, trading, or Production claims.

## Current implementation truth

| Area | Current implementation fact at the WP-12 implementation checkpoint |
|---|---|
| Package shape | The legacy Python 3.12 modular monolith remains intact. Target `shared`, `runtime`, `market`, permanent `selection`, permanent `research_qualification`, permanent `decision_support`, permanent `outcome`, `infrastructure`, `interfaces`, and sole target `bootstrap.py` are isolated by dependency tests; each owner keeps Domain/Application/ports while PostgreSQL adapters remain in Infrastructure |
| PostgreSQL | The canonical business implementation remains legacy 001–106 with 283 tables. The target draft defines 78 tables and four read-only views under schema `mra` |
| Runtime | Continuous Research remains the current all-day business control plane. The target test-only DAG requires `CAPTURE -> NORMALIZE_PIT -> FREEZE_UNIVERSE -> ASSESS_ELIGIBILITY -> REGISTER_DATASET -> BUILD_CANDIDATE_SET -> OPEN_DECISION_RUN`; its next logical Step is `ASSESS_CONTEXT`, which is vocabulary only and has no Context implementation |
| CLI | Six legacy scripts remain. `mra` exposes target DB bootstrap/verify/recreate and Runtime inspection/recovery, but no Market business cutover command |
| Market/PIT | Within the isolated target draft, the target owner is the sole writer of its draft facts; legacy remains canonical business implementation. Its large files are physically split by cohesive Domain/Application/Ports/query/repository responsibilities with stable exports and unchanged WP-04 schema/PIT/Provider semantics; only generic exact/as-of facts remain public |
| Universe/Eligibility | Permanent target `market_regime_alpha.selection` owns explicit immutable scope, frozen membership, typed policy/rules, complete three-state assessment/reasons, exact Market lineage, and an independent narrow Selection UoW, all test-only |
| Candidate | Current legacy capabilities remain canonical. The target draft implements the five Selection-owned Candidate relations, deterministic Policy/Set writer, complete score matrix, independent Candidate UoW, Selection-owned Research-input port with Infrastructure adapter, and funnel/dossier queries; its local WP-07 engineering exit gate passes at `029c269` |
| Research/Qualification | Current legacy capabilities remain canonical. Permanent target `market_regime_alpha.research_qualification` implements immutable Decision-input Dataset/Source/Feature, Outcome-compatible Target Definition, database-derived Research Partition, predeclared Experiment and Evaluation Protocol/Run, transactional exact Outcome access, complete observations/metric inputs, Evaluation-bound immutable Evidence DAGs, complete Experiment Assessments, and purpose-specific Research Qualification. Evidence, Assessment, and Qualification retain three additional narrow UoWs; Model/Calibration remain absent |
| Decision/Outcome | Current legacy capabilities remain canonical. Permanent target `market_regime_alpha.decision_support` implements the sole immutable Decision Run per Candidate Set and frozen reference. Permanent `market_regime_alpha.outcome` implements one commitment-bound Market Target Outcome root, append-only full revisions, exact source/observation/metric/dependency/reason rosters, dual cutoffs, pure Decimal settlement, typed replay/reconciliation, and a narrow read-only port; all remain test-only before cutover |
| Execution/Account | Human/manual execution only; observed effective Fill remains the source of trade-caused Position. No target implementation was added |
| Target epoch | Foundation through WP-11 plus WP-12 Evidence/Assessment/Research Qualification are implemented in the mutable `MRA_REFOUNDATION_1` draft; optional Model/Calibration, every later target context, and Runtime/CLI Cutover remain absent |
| Legacy | Old source, 001–106 migrations, CLIs, compatibility paths, and tests remain physically present as the current implementation and regression oracle |

The convergence state is therefore
`WP12_EXIT_GATE_PASS / NOT_CUT_OVER`.
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

The four replaceable views are `candidate_component_diagnostic`,
`candidate_funnel`, `run_trace`, and `artifact_integrity_status`. The
implementation-defined draft shape is 78 tables, four views, 611 indexes, 913
constraints, 65 functions, 163 non-internal triggers, and 1,835 catalog
objects.
Its baseline checksum is
`a7ef01de52dcb0dae900cc4bba6e7861e70dff0deb438e2fab2e4cbbcfa8986c`, its
seed checksum is
`9c41cd715e35e1a7bed3a58c52a29f01cc1e9bf950b77344bb56eac6dfa2df11`, and its
reference-vocabulary checksum is
`f5ab9cc4fe7617dd0bc5de171365e877eddadc9f6158f3fa0eb83f634c03e701`.
A clean PostgreSQL 16 bootstrap/verify used by exact-SHA WP-12 qualification produced
catalog checksum
`5fa66be6a0b6019032217e201ed547cfd9217fa109ef3b9122d3f0d6dc48ee72`.
Clean bootstrap, exact-OID recreate, concurrency, failure/recovery, replay,
representative plans, full regression, static and build gates pass at the
linked WP-12 Verification. Table count is descriptive, not an optimization
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

## Historical exact-SHA verification through WP-12

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

Each immutable ledger owns only its recorded exact-SHA evidence. Earlier
checkpoint counts and checksums remain historical facts inside those ledgers;
they are not current catalog or regression claims. At WP-12, GitHub Actions
remains disabled, so remote CI is
`BLOCKED_BY_REPOSITORY_CONFIGURATION / NOT_RUN`, not PASS. No current or
historical local gate proves Provider, Alpha/OOS, broker, trading, sustained
Prospective value, Production, or Runtime/CLI Cutover evidence.

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
