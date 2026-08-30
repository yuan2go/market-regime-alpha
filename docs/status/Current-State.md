# Current State

> **Status:** CURRENT_STATUS
> **Authority:** Non-authoritative implementation status read model; exact-SHA engineering proof remains in Verification
> **Owner:** Market Regime Alpha maintainers
> **Generated At:** 2026-08-30 WP-07 Candidate Closure exit reconciliation
> **Repository Implementation Checkpoint:** `029c26928af436d7788da1cce3a53c94b96377bf`
> **Containing Documentation Commit:** reported by the final handoff; this read model does not claim a self-referential Git SHA
> **Previous Verified Snapshot:** WP-06 at `22a5ec692fcc261182197c2953a0a860d7cd6f94`
> **Implementation Line Start:** `c3ac21ef1e13f2e8408d30b0481fa9b74c4f9539`
> **Foundation Source Checkpoint:** `eeff49c7a3995ba6d65045be88d4244617301234`
> **Legacy Business Implementation Parent:** `0382dad416d6d50d1eea0bda1603d7c359d65274`
> **Schema Epochs:** canonical business `LEGACY_MIGRATIONS_001_106`; target draft `MRA_REFOUNDATION_1 / DRAFT / NOT_CUT_OVER`
> **Generator:** `WP-ARCHITECTURE-REFOUNDATION-07 Candidate Closure exit reconciliation; non-authoritative read model`
> **Source Tree IDs:** root `d77c8540eaae24e5acdc7e85e1c0ef983614d1ed`; source `314b9df317e056196b6ab7962fe6cf36ec308b99`; tests `715b9bccb0618926842ec859fffd9b5e695ab55a`; target baseline blob `f86f5f8623aad758ed6df533fd3b706c09a69b96`; legacy migrations tree `6d3730548780ad6244d2cfecb4fb3559064b6f06`
> **Code Evidence:** target and legacy source/migration packages, `tests`, and [WP-07 Candidate Closure Verification](../references/WP-ARCHITECTURE-REFOUNDATION-07-Candidate-Closure-Verification.md)

This read model records implemented Candidate scope and the local WP-07
engineering exit result bound to the exact implementation checkpoint above. It
is invalid after any source, migration, test, or composition change until
regenerated. It cannot write business state or promote Provider, research,
qualification, trading, or Production claims.

## Current implementation truth

| Area | Current implementation fact at the WP-07 implementation checkpoint |
|---|---|
| Package shape | The legacy Python 3.12 modular monolith remains intact. Target `shared`, `runtime`, `market`, permanent `selection`, permanent `research_qualification`, `infrastructure`, `interfaces`, and sole target `bootstrap.py` are isolated by dependency tests; importing target Selection/Research does not execute legacy Universe/Research/Features/Candidates packages |
| PostgreSQL | The canonical business implementation remains legacy 001–106 with 283 tables. The target draft defines 40 tables and four read-only views under schema `mra` |
| Runtime | Continuous Research remains the current all-day business control plane. Target Run/Step/Attempt composes a test-only `CAPTURE -> NORMALIZE_PIT -> FREEZE_UNIVERSE -> ASSESS_ELIGIBILITY -> REGISTER_DATASET -> BUILD_CANDIDATE_SET` slice; it is not a canonical entry point |
| CLI | Six legacy scripts remain. `mra` exposes target DB bootstrap/verify/recreate and Runtime inspection/recovery, but no Market business cutover command |
| Market/PIT | Within the isolated target draft, the target owner is the sole writer of its draft facts; legacy remains canonical business implementation. Its large files are physically split by cohesive Domain/Application/Ports/query/repository responsibilities with stable exports and unchanged WP-04 schema/PIT/Provider semantics; only generic exact/as-of facts remain public |
| Universe/Eligibility | Permanent target `market_regime_alpha.selection` owns explicit immutable scope, frozen membership, typed policy/rules, complete three-state assessment/reasons, exact Market lineage, and an independent narrow Selection UoW, all test-only |
| Candidate | Current legacy capabilities remain canonical. The target draft implements the five Selection-owned Candidate relations, deterministic Policy/Set writer, complete score matrix, independent Candidate UoW, Selection-owned Research-input port with Infrastructure adapter, and funnel/dossier queries; its local WP-07 engineering exit gate passes at `029c269` |
| Research/Qualification | Current legacy capabilities remain canonical. Permanent target `market_regime_alpha.research_qualification` implements only immutable Decision-input `dataset`, closed-FK `dataset_source`, and calculation-only `feature_definition` through an independent narrow UoW; Model/Evaluation/Evidence/Qualification remain absent and their implementation order is not authorized |
| Decision/Outcome | Current legacy capabilities remain; target single write paths have not started |
| Execution/Account | Human/manual execution only; observed effective Fill remains the source of trade-caused Position. No target implementation was added |
| Target epoch | Foundation, Market/PIT, Selection Core, Research Definition Core, and Candidate are implemented in the mutable `MRA_REFOUNDATION_1` draft; every later target context and Runtime/CLI Cutover remain absent |
| Legacy | Old source, 001–106 migrations, CLIs, compatibility paths, and tests remain physically present as the current implementation and regression oracle |

The convergence state is therefore
`FOUNDATION_MARKET_SELECTION_RESEARCH_DEFINITION_CANDIDATE_IMPLEMENTED_DRAFT /
CANDIDATE_EXIT_GATE_PASS / NOT_CUT_OVER`.
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

The four replaceable views are `candidate_component_diagnostic`,
`candidate_funnel`, `run_trace`, and `artifact_integrity_status`. The
implementation-defined draft shape is 40 tables, four views, 245 indexes, 497
constraints, 23 functions, 82 non-internal triggers, and 892 catalog objects.
Its baseline checksum is
`afeb68cb418ceffb4158a4d8d79a75087a30d07777972148e713266951ccaa7b`, its
seed checksum is
`9c41cd715e35e1a7bed3a58c52a29f01cc1e9bf950b77344bb56eac6dfa2df11`, and its
reference-vocabulary checksum is
`60cbea58a647865fa533845ca8e3b6bd35158deedf0373b2132c94cc27abff76`.
Clean PostgreSQL 16.14 bootstrap/verify/recreate produced catalog checksum
`527570a3d0d1e00ec242e57060baa1eb47998a493aa2dd94a2d60841841da6ca`.
The guarded recreate's disposable database identity is recorded only in the
linked WP-07 Verification. Table count is descriptive, not an optimization
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
  gap, and session queries. The named `decision_reference_1455` Target business
  interface and classifier are absent. The underlying exact same-session Raw
  five-minute correctness invariant remains tested; a formal Target resolver
  belongs to a later Research Target/Outcome owner.
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
- Research Definition Core adds exactly `dataset`, `dataset_source`, and
  `feature_definition`. Model, ModelVersion, Target, Evaluation, Evidence,
  Qualification, and later Research contexts remain absent; Candidate is a
  separately implemented Selection owner, not part of this Research UoW.
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

## Historical exact-SHA verification through WP-06

The following evidence is historical through WP-06 and does not prove WP-07
Candidate Closure. The immutable pre-refoundation ledger is
[WP-02](../references/WP-ARCHITECTURE-REFOUNDATION-02-Pre-Refoundation-Verification-Baseline.md),
the Foundation ledger is [WP-03](../references/WP-ARCHITECTURE-REFOUNDATION-03-Foundation-Verification.md),
the Market/PIT ledger is
[WP-04](../references/WP-ARCHITECTURE-REFOUNDATION-04-Market-PIT-Verification.md),
the Selection checkpoint is recorded in
[WP-05](../references/WP-ARCHITECTURE-REFOUNDATION-05-Selection-Core-Verification.md).
The Research Definition commands, failure contract, catalog, full validation,
non-final attempts, and proof ceilings are recorded in
[WP-06](../references/WP-ARCHITECTURE-REFOUNDATION-06-Research-Definition-Core-Verification.md).

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
