# Current State

> **Status:** CURRENT_STATUS
> **Authority:** Non-authoritative implementation status read model; exact-SHA engineering proof remains in Verification
> **Owner:** Market Regime Alpha maintainers
> **Generated At:** 2026-08-31 WP-10 Market Target Outcome exit reconciliation
> **Repository Implementation Checkpoint:** `56812c58ce7b6e601366ffd0a5cfb52fec573227`
> **Containing Documentation Commit:** reported by the final handoff; this read model does not claim a self-referential Git SHA
> **Previous Verified Snapshot:** WP-09 at `9a21d5d5384ace9ace987055a131d010e54daf0f`
> **Implementation Line Start:** `c3ac21ef1e13f2e8408d30b0481fa9b74c4f9539`
> **Foundation Source Checkpoint:** `eeff49c7a3995ba6d65045be88d4244617301234`
> **Legacy Business Implementation Parent:** `0382dad416d6d50d1eea0bda1603d7c359d65274`
> **Schema Epochs:** canonical business `LEGACY_MIGRATIONS_001_106`; target draft `MRA_REFOUNDATION_1 / DRAFT / NOT_CUT_OVER`
> **Generator:** `WP-ARCHITECTURE-REFOUNDATION-10 exit reconciliation; non-authoritative read model`
> **Source Tree IDs:** root `15f3adc2b5a424a81cfa1224dfee4b04b6b422fa`; source `1ad379e67be0960a45d7c1d8f11fb953fd11480e`; tests `b03577799a3b76585b1ec3fe023c2adb3a8ceff3`; Outcome tree `d984bcc66246be0f68d530c46fe3a1c85294a16a`; target baseline blob `37522c256e5bfe0c28d43a48256dfd5aac7f2068`; legacy migrations tree `6d3730548780ad6244d2cfecb4fb3559064b6f06`
> **Code Evidence:** target and legacy source/migration packages, `tests`, and [WP-10 Market Target Outcome Verification](../references/WP-ARCHITECTURE-REFOUNDATION-10-Market-Target-Outcome-Verification.md)

This read model records the implemented Target Definition, Decision Run, and
Market Target Outcome scope plus the local WP-10 engineering exit result bound
to the exact implementation checkpoint above. It
is invalid after any source, migration, test, or composition change until
regenerated. It cannot write business state or promote Provider, research,
qualification, trading, or Production claims.

## Current implementation truth

| Area | Current implementation fact at the WP-10 implementation checkpoint |
|---|---|
| Package shape | The legacy Python 3.12 modular monolith remains intact. Target `shared`, `runtime`, `market`, permanent `selection`, permanent `research_qualification`, permanent `decision_support`, permanent `outcome`, `infrastructure`, `interfaces`, and sole target `bootstrap.py` are isolated by dependency tests; each owner keeps Domain/Application/ports while PostgreSQL adapters remain in Infrastructure |
| PostgreSQL | The canonical business implementation remains legacy 001–106 with 283 tables. The target draft defines 56 tables and four read-only views under schema `mra` |
| Runtime | Continuous Research remains the current all-day business control plane. The target test-only DAG requires `CAPTURE -> NORMALIZE_PIT -> FREEZE_UNIVERSE -> ASSESS_ELIGIBILITY -> REGISTER_DATASET -> BUILD_CANDIDATE_SET -> OPEN_DECISION_RUN`; its next logical Step is `ASSESS_CONTEXT`, which is vocabulary only and has no Context implementation |
| CLI | Six legacy scripts remain. `mra` exposes target DB bootstrap/verify/recreate and Runtime inspection/recovery, but no Market business cutover command |
| Market/PIT | Within the isolated target draft, the target owner is the sole writer of its draft facts; legacy remains canonical business implementation. Its large files are physically split by cohesive Domain/Application/Ports/query/repository responsibilities with stable exports and unchanged WP-04 schema/PIT/Provider semantics; only generic exact/as-of facts remain public |
| Universe/Eligibility | Permanent target `market_regime_alpha.selection` owns explicit immutable scope, frozen membership, typed policy/rules, complete three-state assessment/reasons, exact Market lineage, and an independent narrow Selection UoW, all test-only |
| Candidate | Current legacy capabilities remain canonical. The target draft implements the five Selection-owned Candidate relations, deterministic Policy/Set writer, complete score matrix, independent Candidate UoW, Selection-owned Research-input port with Infrastructure adapter, and funnel/dossier queries; its local WP-07 engineering exit gate passes at `029c269` |
| Research/Qualification | Current legacy capabilities remain canonical. Permanent target `market_regime_alpha.research_qualification` implements immutable Decision-input Dataset/Source/Feature plus provider-neutral Target Definition/Checkpoint/Metric/Dependency Authority; Target registration has an independent narrow UoW and append-only supersession. Partition/Experiment/Evaluation/Model/Evidence/Qualification remain absent |
| Decision/Outcome | Current legacy capabilities remain canonical. Permanent target `market_regime_alpha.decision_support` implements the sole immutable Decision Run per Candidate Set and frozen reference. Permanent `market_regime_alpha.outcome` implements one commitment-bound Market Target Outcome root, append-only full revisions, exact source/observation/metric/dependency/reason rosters, dual cutoffs, pure Decimal settlement, typed replay/reconciliation, and a narrow read-only port; all remain test-only before cutover |
| Execution/Account | Human/manual execution only; observed effective Fill remains the source of trade-caused Position. No target implementation was added |
| Target epoch | Foundation, Market/PIT, Selection Core, Research Definition Core, Candidate, Target Definition, Decision Run commitment, and Market Target Outcome are implemented in the mutable `MRA_REFOUNDATION_1` draft; Partition/Experiment and every later target context plus Runtime/CLI Cutover remain absent |
| Legacy | Old source, 001–106 migrations, CLIs, compatibility paths, and tests remain physically present as the current implementation and regression oracle |

The convergence state is therefore
`FOUNDATION_MARKET_SELECTION_RESEARCH_DEFINITION_CANDIDATE_TARGET_DECISION_RUN_OUTCOME_IMPLEMENTED_DRAFT /
WP10_EXIT_GATE_PASS / NOT_CUT_OVER`.
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

The four replaceable views are `candidate_component_diagnostic`,
`candidate_funnel`, `run_trace`, and `artifact_integrity_status`. The
implementation-defined draft shape is 56 tables, four views, 421 indexes, 699
constraints, 42 functions, 116 non-internal triggers, and 1,339 catalog
objects.
Its baseline checksum is
`7a8d641140f855a4e6dd15e0bcad6430dbb715e224a00603d437d058d6a63baf`, its
seed checksum is
`9c41cd715e35e1a7bed3a58c52a29f01cc1e9bf950b77344bb56eac6dfa2df11`, and its
reference-vocabulary checksum is
`37dae1c30c2c37a30b810af2f7a70d9198f6ec0f4245981211618144eb9bebe6`.
Clean PostgreSQL 16.14 bootstrap/verify/recreate produced catalog checksum
`6c3e2732024ae28875df111ad3ef97cd8c8520f40adc168b0ac8951048335888`.
The guarded recreate's disposable database identity is recorded only in the
linked WP-10 Verification. Table count is descriptive, not an optimization
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
  Model, ModelVersion, Partition, Experiment, Evaluation, Evidence,
  Qualification, and later Research contexts remain absent; Candidate remains
  a separately implemented Selection owner.
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

## Historical exact-SHA verification through WP-09

The following evidence is historical through WP-09 and does not prove WP-10.
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

At implementation checkpoint
`22a5ec692fcc261182197c2953a0a860d7cd6f94`, all 3,245 collected repository
tests pass in five non-overlapping fresh-database batches of 1,298 + 291 + 29 +
684 + 943. All 205 target refoundation tests pass, including 46 Research, 21
Selection, and 69 Market tests. The unchanged legacy 001–106 migration/schema
and business suites, 33 platform tests, documentation inventory/link checks,
Ruff, mypy over 500 source files, package build, clean bootstrap/verify/
exact-OID recreate, representative query plans, architecture dependency rules,
and diff checks pass. No test or assertion was skipped, xfailed, deleted, or
weakened.

At that WP-06 snapshot, the verified PostgreSQL 16.14 target catalog contained
35 tables and kept `MRA_REFOUNDATION_1 / DRAFT / NOT_CUT_OVER`. Its baseline,
seed, vocabulary,
and catalog checksums are recorded in WP-06. Candidate V1's real Selection and
Research definition prerequisites now exist in an acyclic Authority order;
Candidate capability was still absent at that historical checkpoint.

At WP-06, GitHub Actions remained disabled, so remote CI was
`BLOCKED_BY_REPOSITORY_CONFIGURATION / NOT_RUN`, not PASS. No current or
historical local gate proves Provider, Alpha/OOS, broker, trading, Prospective,
Production, or Runtime/CLI Cutover evidence.

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
