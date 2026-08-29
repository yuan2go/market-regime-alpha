# Current State

> **Status:** CURRENT_STATUS
> **Authority:** Non-authoritative exact-SHA implementation read model
> **Owner:** Market Regime Alpha maintainers
> **Generated At:** 2026-08-29T08:02:16Z
> **Repository SHA:** `7932fda7f41c44bc29f04672caaef75d6b9b2c69`
> **Implementation Line Start:** `c3ac21ef1e13f2e8408d30b0481fa9b74c4f9539`
> **Foundation Source Checkpoint:** `eeff49c7a3995ba6d65045be88d4244617301234`
> **Legacy Business Implementation Parent:** `0382dad416d6d50d1eea0bda1603d7c359d65274`
> **Schema Epochs:** canonical business `LEGACY_MIGRATIONS_001_106`; target draft `MRA_REFOUNDATION_1 / DRAFT / NOT_CUT_OVER`
> **Generator:** `WP-ARCHITECTURE-REFOUNDATION-06 design audit before business-code changes`
> **Source Tree IDs:** source `d9f5ff8ac1b6eb736cc0f14f8dc2b8ed1d6d577c`; legacy migrations `6d3730548780ad6244d2cfecb4fb3559064b6f06`; target baseline `f514b18d29f48e730d0bce6c243df774bd2fceeb`; tests `be2f694e967acc09bb49b8d11c61c8663df30ab4`
> **Code Evidence:** target and legacy source/migration packages plus `tests`

This snapshot is invalid after any source, migration, test, or composition
change until regenerated. It reports implementation and local engineering
verification only; it cannot write business state or promote Provider,
research, qualification, trading, or Production claims.

## Current implementation truth

| Area | Exact current fact at the snapshot SHA |
|---|---|
| Package shape | The legacy Python 3.12 modular monolith remains intact. Target `shared`, `runtime`, `market`, permanent `selection`, `infrastructure`, `interfaces`, and sole target `bootstrap.py` are isolated by dependency tests; importing Selection does not execute legacy `universe/__init__.py` |
| PostgreSQL | The canonical business implementation remains legacy 001–106 with 283 tables. The target draft has 32 tables and two read-only views under schema `mra` |
| Runtime | Continuous Research remains the current all-day business control plane. Target Run/Step/Attempt can execute a test-only `CAPTURE -> NORMALIZE_PIT -> FREEZE_UNIVERSE -> ASSESS_ELIGIBILITY` slice; it is not a canonical entry point |
| CLI | Six legacy scripts remain. `mra` exposes target DB bootstrap/verify/recreate and Runtime inspection/recovery, but no Market business cutover command |
| Market/PIT | The target owner remains authoritative for its draft facts. Its large files are physically split by cohesive Domain/Application/Ports/query/repository responsibilities with stable exports and unchanged WP-04 schema/PIT/Provider semantics; only generic exact/as-of facts remain public |
| Universe/Eligibility | Permanent target `market_regime_alpha.selection` owns explicit immutable scope, frozen membership, typed policy/rules, complete three-state assessment/reasons, exact Market lineage, and an independent narrow Selection UoW, all test-only |
| Candidate | Current legacy capabilities remain canonical. Target Candidate is `DEFERRED / NO-GO`; Candidate Set still has no target table or writer and remains independent of future Decision/Qualification |
| Research/Qualification | Current legacy capabilities remain. The permanent target namespace is frozen as `market_regime_alpha.research_qualification`, but at this design snapshot it has no package or table yet; only `dataset`, `dataset_source`, and `feature_definition` are approved for implementation, while Model/Evaluation/Evidence/Qualification remain deferred |
| Decision/Outcome | Current legacy capabilities remain; target single write paths have not started |
| Execution/Account | Human/manual execution only; observed effective Fill remains the source of trade-caused Position. No target implementation was added |
| Target epoch | Foundation, Market/PIT, and Selection Core are implemented in the mutable `MRA_REFOUNDATION_1` draft; Research Definition Core is design-approved but not implemented; Candidate and every later target context plus Runtime/CLI Cutover remain absent |
| Legacy | Old source, 001–106 migrations, CLIs, compatibility paths, and tests remain physically present as the current implementation and regression oracle |

The convergence state is therefore
`FOUNDATION_MARKET_SELECTION_IMPLEMENTED_DRAFT / RESEARCH_DEFINITION_DESIGN_FROZEN / NOT_CUT_OVER`.
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

The two views remain `run_trace` and `artifact_integrity_status`. The verified
draft catalog contains 166 indexes, 402 constraints, 23 functions, and 74
non-internal triggers. Selection adds no owner-specific trigger function: its
seven append-only triggers reuse the Foundation mutation guard. Table count is
descriptive, not an optimization target. These counts describe the merged
starting baseline; the approved Research Definition tables do not exist at this
design snapshot.

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

## Research Definition design freeze

- The permanent target namespace is
  `market_regime_alpha.research_qualification`; legacy `research`, `features`,
  and Candidate persistence remain invariant sources only and cannot be target
  dependencies or compatibility paths.
- This work package may add exactly `dataset`, `dataset_source`, and
  `feature_definition`. Model, ModelVersion, Evaluation, Evidence,
  Qualification, Candidate, and later contexts remain deferred.
- A target Dataset is a Decision-input Dataset. At one DecisionTime its
  instrument rows must equal, without omission or addition, the intersection
  of `UniverseMember = INCLUDED` and
  `EligibilityAssessment = ELIGIBLE`. Missing Feature observations remain
  explicit typed cells and never remove an instrument.
- The Dataset manifest parser rejects Target, Outcome, return, MFE, MAE,
  barrier, future-observation, realized-label, and other posterior fields.
  Dataset source roles are closed, use concrete owner foreign keys, and must
  reconcile exactly with manifest lineage; no polymorphic string identity,
  generic business-lineage JSON, future nullable identity, or Registry is
  permitted.
- Runtime command failure uses one narrow cross-context contract: the failed
  business transaction rolls back, then a fresh short owner UoW validates the
  live fence before atomically writing the failed receipt, audit, and matching
  Attempt/Step failure. The contract owns no command dispatch or Domain-error
  interpretation.

## Exact-SHA verification

The immutable pre-refoundation ledger is
[WP-02](../references/WP-ARCHITECTURE-REFOUNDATION-02-Pre-Refoundation-Verification-Baseline.md),
the Foundation ledger is [WP-03](../references/WP-ARCHITECTURE-REFOUNDATION-03-Foundation-Verification.md),
the Market/PIT ledger is
[WP-04](../references/WP-ARCHITECTURE-REFOUNDATION-04-Market-PIT-Verification.md),
and the Selection checkpoint's commands, catalog, non-final attempts, and proof
ceilings are recorded in
[WP-05](../references/WP-ARCHITECTURE-REFOUNDATION-05-Selection-Core-Verification.md).

At implementation checkpoint `44caf94`, all 3,195 collected repository tests
pass in five non-overlapping resource-bounded batches of 974 + 324 + 954 + 705
+ 238 against a repeatedly recreated dedicated PostgreSQL 16.14 database. All
155 target refoundation tests pass, including 19 Selection tests and the
behavior-preserved 69 Market tests. The unchanged legacy 001–106 bootstrap,
schema, compatibility, and regression suites pass. The 33 platform tests,
documentation inventory/link checks, Ruff, mypy over 494 source files, package
build, PostgreSQL clean bootstrap/verify/exact-OID recreate, representative
query plans, architecture dependency checks, and diff checks pass.

The full 3,195-node run preceded removal of pure formatter-only churn in the
affected files; all affected Market and complete refoundation suites then passed
again on the exact checkpoint content. No assertion, fixture meaning,
skip/xfail marker, schema invariant, or application behavior was relaxed.

Two non-final invocations are not counted as PASS. A Unix-socket test URL was
rejected because legacy settings require an explicit host; the database was
rebuilt and the run used `postgresql://localhost/...`. A parallel target/legacy
attempt against one database was rejected because target bootstrap correctly
found live legacy temporary schemas; serial, isolated, explicitly recreated
runs then passed.

GitHub's repository Actions permission endpoint reports `enabled=false`.
Remote CI is therefore `BLOCKED_BY_REPOSITORY_CONFIGURATION / NOT_RUN`, not
PASS. Local engineering proof does not establish Provider qualification,
Formal PIT, Alpha/OOS, broker, trading, Production, or Runtime/CLI Cutover.

Between the WP-05 implementation checkpoint and merged starting SHA
`7932fda7f41c44bc29f04672caaef75d6b9b2c69`, governance-only changes updated
`CLAUDE.md`, documentation, and reproducible-environment tests. They did not
change the target source, legacy migrations, or target baseline tree. Their
focused documentation, reproducibility, Ruff, and diff checks passed; a full
repository suite was not rerun at that merged SHA. The 3,195-test result above
therefore remains historical exact-SHA WP-05 evidence, not a claim about the
current design snapshot. The WP-06 full gate is `NOT_RUN` until implementation
and verification complete.

GitHub Actions remain disabled, so remote CI is
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
