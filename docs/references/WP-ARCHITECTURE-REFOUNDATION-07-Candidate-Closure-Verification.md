# WP-ARCHITECTURE-REFOUNDATION-07 Candidate Closure Verification

> **Status:** CURRENT_STATUS
> **Verification State:** `CANDIDATE_CLOSURE_ENGINEERING_GO`
> **Authority:** Exact-SHA local engineering verification record; not Research Evaluation, Target, Model, Evidence, Qualification, Decision/Outcome, Execution, Runtime Cutover, trading, or Production Authority
> **Owner:** Market Regime Alpha maintainers
> **Executed At:** `2026-08-30 (Asia/Shanghai)`
> **Starting Main:** `origin/main@d45fe83730a75dfa6083db9b6c929b37838fdd50`
> **Initial Design Checkpoint:** `50d0ee7`
> **Approved Corrected Design Checkpoint:** `0a6560ccb27b0f8f058e647ecc19063815da5002`
> **Implementation Checkpoint:** `029c26928af436d7788da1cce3a53c94b96377bf`
> **Containing Documentation Commit:** reported by the final handoff; this file does not claim a self-referential Git SHA
> **Schema Epoch:** `MRA_REFOUNDATION_1`
> **Release State:** `DRAFT`
> **Cutover State:** `NOT_CUT_OVER`

This record verifies only WP-07 Candidate Authority. Candidate remains
permanently owned by `market_regime_alpha.selection`; current legacy paths
remain canonical until a separately authorized cutover. WP-07 creates no
Model/ModelVersion, Target, Research Evaluation, Evidence, Qualification,
Decision/Outcome, Execution, or future placeholder Authority, and grants no
authority to implement any of them.

The engineering decision at this ledger is:

```text
WP-07 CANDIDATE CLOSURE ENGINEERING GO
MRA_REFOUNDATION_1 / DRAFT / NOT_CUT_OVER
```

Regardless of that local engineering decision, Runtime/CLI cutover, formal
Provider/PIT evidence, Alpha/OOS evidence, broker authority, trading authority,
and Production admission remain **NO-GO**.

## 1. Exact checkpoint chain and scope

The implementation used the execution-time latest `origin/main` as its sole
baseline and preserved the approved checkpoint separation:

```text
d45fe83730a75dfa6083db9b6c929b37838fdd50  starting origin/main
50d0ee7                                      initial design checkpoint
0a6560ccb27b0f8f058e647ecc19063815da5002  approved corrected design checkpoint
3d869e1                                      implementation plan checkpoint
9a7f3ac                                      Candidate schema checkpoint
c2b162b88823a98df477e565487f7f1d9a9a106a  Candidate Domain/port checkpoint
df5cce1545a11f6b712a3af767a7c28b857aa43d  first complete implementation checkpoint
cdeca1eb9580f8aec70ad6b6237cf87117b6dca4  first review correction checkpoint
02e945624833c52606d60097033c9dc5c704e238  replay/projection correction checkpoint
8209131520d4c741914b8a8c0e050554471e343b  Decimal-context/numeric correction checkpoint
e82eac1f9ed72d9a0e844c424e8e619c62dbc1e2  empty-CandidateSet correction checkpoint
246e58218f7e7ed57e1d45429e4105ba8df6922f  mandatory-fence implementation checkpoint
029c26928af436d7788da1cce3a53c94b96377bf  final transaction-invariant correction checkpoint
```

The final implementation checkpoint binds these Git objects:

```text
root tree                 d77c8540eaae24e5acdc7e85e1c0ef983614d1ed
source tree               314b9df317e056196b6ab7962fe6cf36ec308b99
legacy migrations tree    6d3730548780ad6244d2cfecb4fb3559064b6f06
target baseline blob      f86f5f8623aad758ed6df533fd3b706c09a69b96
tests tree                715b9bccb0618926842ec859fffd9b5e695ab55a
```

WP-07 changes the mutable target draft only. The legacy Python packages and
001--106 legacy PostgreSQL migrations remain in place and retain their current
authority. No compatibility write, dual write, fallback reader, CommandBus,
Registry, service locator, or production dispatcher path was added.

## 2. Candidate design debt closed

The independent design checkpoint removed or corrected the following stale or
conflicting Candidate design before implementation began:

- Candidate is permanently in Selection, not a future Research-owned package;
- the staged Selection Core -> Research Definition -> Candidate dependency is
  closed with a Selection-owned read port and Infrastructure adapter, without a
  `selection <-> research_qualification` package cycle;
- the Candidate authority is exactly five tables, rather than a design that
  pre-created Model, Target, Evidence, Qualification, or future placeholders;
- CandidatePolicyComponent binds a real FeatureDefinition and owns only the
  canonical declared Decimal weight; it does not bind a Dataset or
  ModelVersion, and no finite projected normalized weight becomes a second
  policy truth;
- CandidateSet binds the immutable Decision-input Dataset; CandidatePolicy does
  not bind a DecisionTime-specific Dataset;
- Dataset is the only Candidate population, replacing any Candidate-layer
  repetition of Universe, Eligibility, liquidity, or Market hard gates;
- every Dataset row has an explicit terminal Candidate disposition and every
  Candidate has a complete component matrix, closing the partial funnel and
  silent row-deletion ambiguity;
- the invalid unique `(candidate_set_id, rank)` design was removed so exact
  ties can share competition rank;
- Dataset lineage stays with the immutable Dataset manifest and relational
  `dataset_source`; Candidate score rows contain a deterministic cell/source
  lineage hash, not a new UUID-array/GIN lineage Authority or a sixth Candidate
  table;
- `BUILD_CANDIDATES` was removed as a target name; the only target Step name is
  `BUILD_CANDIDATE_SET`, with no alias or compatibility route;
- Candidate no longer depends on future Evidence/Qualification or a fitted
  Model, and its score semantics are explicitly descriptive rather than a
  probability, expected return, MFE/MAE, Target, or Entry instruction;
- WP-07 stops at Candidate Closure; after its exit gate, the only next activity
  is a separate dependency review that neither freezes Research Evaluation
  before Decision/Outcome nor authorizes either stage.

## 3. Permanent package boundary and acyclic Research-input seam

Candidate Domain, Application, ports, repositories, and UoW are Selection
owned:

```text
market_regime_alpha.selection.domain.candidate_*
market_regime_alpha.selection.application.candidates
market_regime_alpha.selection.ports.candidate_*
market_regime_alpha.selection.ports.research_inputs
market_regime_alpha.infrastructure.postgres.candidate_uow
market_regime_alpha.infrastructure.postgres.repositories.candidate
market_regime_alpha.infrastructure.postgres.queries.candidate_research_inputs
market_regime_alpha.infrastructure.postgres.queries.candidate
```

Selection defines the narrow `CandidateResearchInputs` port and immutable
Selection-owned DTOs. The PostgreSQL Infrastructure adapter reads only the
Research Definition facts Candidate needs: the immutable DECISION_INPUT
Dataset identity and hashes, DecisionTime/scope, ordered real
FeatureDefinitions, every population row and required typed cell, exact raw
status/reason, cell/source-lineage hash, and final revalidation identities.

```text
Selection Candidate Application
  -> Selection-owned CandidateResearchInputs port/DTO
  <- PostgreSQL cross-context adapter
     -> immutable Research Definition tables and Dataset Artifact
```

Selection Domain/Application imports neither
`market_regime_alpha.research_qualification` nor PostgreSQL Infrastructure.
Research Qualification imports no Candidate package. The adapter does not hand
a Research repository or Research UoW to Selection. `CandidateUnitOfWork` is
independent; Runtime, Selection Core, and Research UoWs were not expanded into
a mega-UoW.

## 4. Five-table Candidate Authority

The target draft adds exactly these Candidate Authority relations:

```text
candidate_policy
candidate_policy_component
candidate_set
candidate
candidate_score_component
```

Their closed responsibilities are:

- `candidate_policy` owns immutable deterministic-ranking semantics, requested
  Top-K/tie/missing/rank policies, projection algorithm identity, and exact
  code/config Artifact triples; it owns no Dataset or later-context identity;
- `candidate_policy_component` binds one real numeric FeatureDefinition,
  ordinal, direction, and positive canonical declared Decimal weight;
- `candidate_set` binds exactly one Policy and immutable Decision-input Dataset
  and owns result/dependency fingerprints, projection precision, funnel,
  ranking, component, and boundary diagnostics;
- `candidate` records exactly one Dataset population instrument with
  `SELECTED`, `RANKED_NOT_SELECTED`, or `UNRANKABLE`, plus score/rank only when
  rankable and the real POPULATION `dataset_source` identity;
- `candidate_score_component` is the complete typed Candidate x
  PolicyComponent matrix and stores the raw value/status/reason,
  FeatureDefinition identity, cell/source-lineage hash, projected normalized
  weight, percentile, contribution, and disposition facts needed to reproduce
  and explain the result.

The schema deliberately has no unique set/rank constraint. It uses real and
composite FKs to reject cross-Policy, cross-Dataset, cross-instrument, and
cross-Feature drift. Candidate score rows have no DatasetSource UUID array and
no GIN lineage index. Dossier lineage follows
`CandidateSet.dataset_id -> Dataset manifest/dataset_source`.

The two Candidate projections are `candidate_component_diagnostic` and
`candidate_funnel`; they are replaceable views, not additional Authority.
WP-07 added no Candidate-specific trigger function: all five append-only tables
reuse the Foundation mutation guard because row-local, identity, closed-status,
and referential invariants are declarative.

## 5. Policy, ranking, missingness, projection, and tie semantics

Candidate V1 is a transparent deterministic cross-sectional ranker, not a
prediction model.

The ranker consumes only the Dataset's typed required Feature cells. It does
not read Target, Outcome, market Context, Model, Qualification, probability,
expected-return, MFE/MAE, or Entry facts. Operational `CommandContext` is used
only for receipt/audit metadata and never enters a percentile, contribution,
composite, rank, boundary, or result hash.

### 5.1 Strict complete case and population preservation

The immutable Dataset population is already proven by Research Definition as:

```text
UniverseMember = INCLUDED
INTERSECT
EligibilityAssessment = ELIGIBLE
```

Candidate consumes that population unchanged. Any required component with raw
status `MISSING`, `UNKNOWN`, `STALE`, or `CONFLICT` makes the Candidate
`UNRANKABLE`; composite score and rank are null. No imputation occurs, `0.5`
is never a missing-value fill, and available cells on an otherwise unrankable
Candidate remain in the immutable complete score matrix.

### 5.2 Exact arithmetic midrank

All semantic normalization, component contribution, composite, rank, and
boundary decisions use exact rational arithmetic. For rankable cross-section
size `n > 1`, after orienting the value so larger is better:

```text
percentile = (strictly_worse + (equal_count - 1) / 2) / (n - 1)
```

Equal values receive equal percentiles. Instrument code, UUID, insertion order,
manifest order, row position, and source identity never break a tie.

Only an `AVAILABLE` Feature with `distinct_count = 1` in the complete rankable
cross-section receives the special arithmetic-midrank value `0.5` and
component status `CONSTANT`. A nonconstant component's ordinary formula may
naturally produce `0.5` for a middle observation without becoming constant.

The closed edge cases are:

- `rankable_count = 1`: every required component percentile is `0.5`, the
  exact composite is `0.5`, competition rank is 1, and the Candidate is
  selected for positive Top-K; CandidateSet status is `CONSTANT`;
- mixed constant/discriminating components: constant components retain their
  fixed weight times `0.5`, weights are not dynamically redistributed, and
  CandidateSet status is `AVAILABLE`;
- every component constant: every rankable Candidate has composite `0.5` and
  rank 1; the complete boundary group is selected, with `CONSTANT` and tie/
  overflow diagnostics;
- `rankable_count = 0`: no percentile, contribution, score, rank, or boundary
  is calculated; status is `NOT_ESTIMABLE` and selected count is zero;
- an empty Dataset is a legal empty `NOT_ESTIMABLE` CandidateSet with zero
  Candidates and score rows.

### 5.3 Exact weights and finite Decimal projection

Each canonical declared Decimal weight is converted to an exact rational and
normalized by the exact sum. That rational computation is semantic Authority.
`candidate_policy_component` stores no projected normalized-weight copy.

The build chooses one `candidate_set.decimal_projection_precision` and applies
one isolated `ROUND_HALF_EVEN` Decimal context to projected normalized weights,
percentiles, contributions, composites, and boundary values stored as
PostgreSQL `numeric`. The isolated context fixes precision, exponent bounds,
clamp/capitals, flags, and traps rather than inheriting ambient process state.
Precision begins at 64 and deterministically doubles through the closed maximum
4096 if necessary to preserve exact unequal composite ordering and the boundary
class. Projected component values need not sum to exactly one or reconstruct a
projected composite by finite Decimal addition; exact rational inputs and the
algorithm remain the semantic source.

The application rejects projection outside PostgreSQL unconstrained `numeric`
physical bounds (131072 integer digits and 16383 fractional digits) before the
final business UoW. Every non-empty Dataset projects component weights even if
all rows are unrankable. An empty Dataset has no score rows and therefore does
not manufacture an otherwise-unused normalized-weight projection.

### 5.4 Composite, competition rank, and boundary

Before projection:

```text
exact_contribution_i = exact_normalized_weight_i * exact_percentile_i
exact_composite       = sum(exact_contribution_i)
competition_rank      = 1 + count(exact composites strictly greater)
```

Top-K uses the exact score at ordinal
`min(requested_top_k, rankable_count)` as its boundary. Every exact score at or
above the boundary is selected. `INCLUDE_ALL_BOUNDARY_TIES` is unconditional;
selected count may exceed requested Top-K, and the CandidateSet records
boundary score/rank, strictly-above count, boundary-group count, overflow,
whether the boundary is tied, and whether ties expanded selection.

## 6. Funnel, matrix, and diagnostic reconciliation

The CandidateSet is accepted only when all of these identities hold both in the
prepared immutable plan and after PostgreSQL reload:

```text
population_count = rankable_count + unrankable_count
rankable_count = selected_count + ranked_not_selected_count
candidate_count = population_count
score_component_count = population_count * component_count
```

Every Dataset row therefore produces a terminal Candidate record, including an
explicit unrankable reason, and every Candidate/component pair produces one
typed score row. Empty populations satisfy the same equations with zeros.

The component diagnostic derives, without a sixth table, `observed_count`,
`distinct_count`, `raw_available_count`, literal `missing_count`, and separate
`unknown_count`, `stale_count`, and `conflict_count`. Component status is
`NOT_ESTIMABLE`, `CONSTANT`, or `AVAILABLE`. CandidateSet status is
`NOT_ESTIMABLE` with no rankable rows, `CONSTANT` when all estimable components
are constant, and `AVAILABLE` when any component discriminates.
`composite_distinct_count` separately states whether the final composite
actually separates rows.

The funnel query returns Dataset population, all reconciled counts,
disposition/unrankable-reason counts, ranking and boundary diagnostics, and
component diagnostics. The dossier returns Policy/Dataset/Candidate identity,
disposition/score/rank/reason, every typed component fact, and relational
Dataset manifest/source lineage reached through the CandidateSet's Dataset.

Representative immutable plans prove the full numeric funnel rather than only
the equations:

```text
strict complete case, two components:
  population=3 rankable=2 unrankable=1 selected=1
  ranked_not_selected=1 score_rows=6

fresh target vertical, one component:
  dataset_population=1 population=1 rankable=1 selected=1
  ranked_not_selected=0 unrankable=0 score_rows=1
  ranking_status=CONSTANT composite_distinct=1
  population/rankable/component-matrix reconciliation=true

all four unavailable statuses, one component:
  population=4 rankable=0 unrankable=4 selected=0
  ranked_not_selected=0 score_rows=4 ranking_status=NOT_ESTIMABLE

empty Dataset, one component:
  population=0 rankable=0 unrankable=0 selected=0
  ranked_not_selected=0 score_rows=0 ranking_status=NOT_ESTIMABLE

all-constant Top-1 boundary:
  population=3 rankable=3 selected=3 requested_top_k=1
  selected_overflow=2 boundary_group=3 all ranks=1 all scores=0.5
  boundary_has_tie=true boundary_tie_expanded=true
```

## 7. Artifact boundary, final transaction, and exact replay

Dataset Artifact verification, byte read, hash/size verification, closed-schema
parse, DTO construction, exact-rational ranking, Decimal projection, and
immutable write-plan construction occur outside the final PostgreSQL write
transaction.

`build_candidate_set` requires a keyword-only real Runtime `AttemptClaim`.
Omitting it, passing `None`, presenting a stale claim, or presenting a live
claim whose `step_key` does not match the persisted Step or whose persisted
Step kind is not exactly `BUILD_CANDIDATE_SET` fails before Artifact I/O or
Candidate writes. The exact Step key and persisted Step kind are checked at
preflight, successful replay finalization, and fresh binding rather than being
trusted from the caller.

The final short Candidate transaction is ordered:

```text
live monotonic Runtime fence + exact persisted Step-key/Step-kind check
-> CandidateSet identity advisory lock
-> exact Policy/Component/Dataset/Feature/population snapshot revalidation
-> deduplicated Artifact exact revalidation and locks in global UUID order
-> CandidateSet, Candidate, and complete score-matrix writes
-> exact reload and reconciliation
-> receipt start
-> linked Dataset-manifest ArtifactVerification
-> receipt success
-> audit event
-> Attempt/Step finalization
-> one commit
```

The identity advisory lock is acquired immediately after the fence and before
dependency locks; the repository repeats the re-entrant lock as a standalone
defense against speculative-insert deadlocks. The five Policy/Dataset Artifact
roles are deduplicated by Artifact UUID. Conflicting immutable bindings for one
UUID fail closed, and all locks are then acquired in ascending UUID order. The
Dataset manifest receives the strongest required mode (`FOR UPDATE`) because a
verification row will be linked to it; every other Artifact receives
`FOR SHARE`. This closes both ordinary same-identity races and the observed
cross-role `FOR SHARE` -> `FOR UPDATE` upgrade deadlock without translating
PostgreSQL `40P01` into a deterministic business failure. Repositories do not
commit.

An exact successful replay does not read Dataset Artifact bytes, parse the
manifest, rerank, or rewrite Candidate Authority. Its initial probe reads only
the receipt, Policy, immutable snapshot, and narrow CandidateSet binding. A
separate read-only Candidate UoW loads the persisted immutable result plan and
closes; pure validation of content hash, summaries, matrix, ranks, and
fingerprints occurs outside a UoW. The final replay transaction performs the
live fence, exact Policy/Artifact/Dataset-snapshot revalidation, exact receipt
reload, locked CandidateSet binding/full Authority reload, reconciliation,
Runtime finalization, and commit. Replay appends no audit event and rewrites no
Candidate Authority.

Same request identity plus changed semantics fails closed. Recovery may execute
the same semantic request under a later valid Attempt because business request
fingerprints exclude Attempt/Step/lease/fence metadata; execution metadata is
recorded separately. A successful durable result converges to one unique
`(candidate_policy_id, dataset_id)` CandidateSet.

After loading the Candidate Policy and Research dependency snapshot needed to
derive the exact semantic request hash, preflight checks terminal receipt status
before any CandidateSet/result Authority lookup, Artifact byte I/O, parse, or
ranking. Therefore an exact retry of a durable deterministic failure raises the
original `CommandPreviouslyFailedError`; it reuses the original FAILED receipt
and error identity, writes no Candidate Authority or rejection receipt, appends
no duplicate audit event, and terminally finalizes the new valid Runtime
Attempt/Step/Run.

## 8. Deterministic failure, stale fence, and concurrency proof

Candidate uses the established shared deterministic failure contract:

```text
Candidate business UoW rolls back completely
-> fresh Candidate UoW
-> revalidate the live Runtime fence
-> failed receipt
-> audit event
-> Attempt/Step terminal failure
-> one commit
```

A stale fence produces no Candidate fact, receipt, audit, or Runtime
finalization. A wrong-kind live claim likewise fails before Artifact I/O and
leaves the unrelated Runtime Attempt running. Injected failure at each of these
five points is covered:

1. Candidate row write;
2. score-component row write;
3. successful receipt write;
4. audit write;
5. Runtime Attempt/Step finalization.

Each injection rolls back the entire business transaction before the shared
fresh-UoW failure record. Tests also cover late stale-fence rejection,
idempotency conflict, exact concurrent builders, replay, recovery, illegal
contribution/boundary drift, and failure-record atomicity. No skip, xfail,
deleted test, compatibility fallback, or weakened invariant is used.

The final cross-role concurrency tracer deliberately makes one Dataset
manifest Artifact also serve as the config Artifact of two distinct Candidate
Policies, pauses both builders before the manifest-exclusive lock, and releases
them together. Both builds complete without deadlock and persist exactly two
CandidateSets, two Candidates, two score rows, two success receipts, and two
manifest verifications. A separate exact-identity double barrier proves two
builders converge to one CandidateSet and one Authority graph. PostgreSQL
deadlock/serialization defects remain operational errors to diagnose; they are
not relabeled as deterministic Candidate rejections.

## 9. Test-only target Runtime vertical slice

The executable target-only proof is:

```text
CAPTURE
-> NORMALIZE_PIT
-> FREEZE_UNIVERSE
-> ASSESS_ELIGIBILITY
-> REGISTER_DATASET
-> BUILD_CANDIDATE_SET
```

It uses fresh real target owners at every stage, an exact shared DecisionTime,
an immutable DECISION_INPUT Dataset, the real CandidateApplication and
CandidateUoW, and the exact `BUILD_CANDIDATE_SET` Step vocabulary. It does not
wire Candidate into the production dispatcher/CLI or create a compatibility
Runtime. The proof covers success, empty/all-unrankable and normal funnels,
stale fence, atomic failure, double-barrier concurrency, exact idempotency,
replay, and recovery.

## 10. Funnel, dossier, and representative query plans

The test fixture has three explanatory Candidate rows and then appends 512
representative Candidate rows, for 515 total. It exercises six bounded query
profiles:

1. exact CandidateSet reload;
2. Candidate rank/disposition lookup;
3. Candidate funnel;
4. Candidate dossier header;
5. dossier-component lookup by exact Candidate/CandidateSet identity;
6. Dataset manifest/relational `dataset_source` lineage traversal.

The proof uses `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)`. Exact set reload,
rank/disposition, Dataset-source lineage, and score-component paths require the
relevant owner indexes. The richer funnel/dossier may validly use a sequential
scan at this representative cardinality, but their owner relations and bounded
predicates must be present. Assertions do not freeze planner cost, elapsed
time, row timing, one node type, or one exact index when PostgreSQL may choose
an equivalent owner index.

## 11. Verified draft schema and checksums

The final exact-SHA clean bootstrap, verify-only retry, guarded recreate, and
post-recreate verification gate passed on one isolated disposable database:

```text
PostgreSQL              16.14
database                mra_wp07_final_schema_029c2692
database OID            383646667
proof workspace         /tmp/mra-wp07-schema-proof.sfbfI8MK (retained, mode 0700)
database owner/schema owner/current user
                        yuan / yuan / yuan
initial empty verify    EXPECTED SCHEMA_MISSING (no mutation)
bootstrap               created=true
first verify             created=false
retry bootstrap         created=false (verify-only; stable identity/checksums)
recreate plan hash      f570fceffc2a1f3cb3317641c784caaf517cc62d056a951eb82c0b6c9623a026
recreate object count   892
active connections      []
unexpected objects      []
challenge/apply         exact issued 24-character challenge matched; apply admitted
recreate verification   created=true
post-recreate verify    created=false
schema                  mra
schema epoch            MRA_REFOUNDATION_1
release state           DRAFT
architecture cutover state (not a schema metadata field)
                        NOT_CUT_OVER
baseline checksum       afeb68cb418ceffb4158a4d8d79a75087a30d07777972148e713266951ccaa7b
seed checksum           9c41cd715e35e1a7bed3a58c52a29f01cc1e9bf950b77344bb56eac6dfa2df11
vocabulary checksum     60cbea58a647865fa533845ca8e3b6bd35158deedf0373b2132c94cc27abff76
catalog checksum        527570a3d0d1e00ec242e57060baa1eb47998a493aa2dd94a2d60841841da6ca
tables/views            40 / 4
indexes/constraints     245 / 497
functions/triggers      23 / 82 non-internal
Candidate tables        5 exactly
metrics evidence sha256 1c41d74145d12991f52a85aaf10049cd5224c7a6ea897babd53214017f95229c
manifest evidence sha256
                        bd9360c771b775a13c9381684a5a1be8e850f6f13d00c0f87d82acc71f6f9bd6
cleanup                 database dropped; empty Artifact root and short-lived
                        full recreate plan removed; proof workspace retained
```

The guarded recreate proof binds the exact disposable database name and OID,
database/schema owner, zero other connections, plan hash/challenge, and
post-recreate checksum. Retry is verify-only. Regardless of the passing local
gate, this target draft does not replace the legacy 001--106 business schema
and remains `NOT_CUT_OVER`.

## 12. Validation ledger

Every Python gate uses `uv run`. Focused groups below overlap and are not added
to the complete-collection count. The full collection was frozen as an exact
set of node IDs, proven equal to the disjoint shard union before any shard was
executed.

| Check | Result | Evidence |
|---|---|---|
| exact starting baseline | **PASS** | implementation started from `origin/main@d45fe83730a75dfa6083db9b6c929b37838fdd50` in the isolated WP-07 worktree |
| independent design checkpoint | **PASS** | initial `50d0ee7`; user-approved corrections frozen at `0a6560ccb27b0f8f058e647ecc19063815da5002` before schema/code |
| Candidate focused tests | **PASS** | 82/82 across 9 Candidate files at `029c26928af436d7788da1cce3a53c94b96377bf` on a fresh PostgreSQL database |
| Candidate Application plus target vertical | **PASS** | 30/30, including mandatory/wrong-kind claim, fresh/replay/failure/recovery, exact concurrency, and cross-role Artifact-lock tracers |
| ranking and Policy semantics | **PASS** | 26/26, covering arithmetic midrank, singleton/all-constant/mixed-constant, strict missingness, exact weights, projection, competition rank, and boundary ties |
| Candidate schema specification | **PASS** | 9/9, including five-table authority, closed precision/code vocabularies, complete FKs/checks, non-unique rank, views, and indexes |
| funnel/dossier query plans | **PASS** | six representative 515-row `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` profiles proved bounded predicates and required owner-index coverage without hard-coded cost, timing, or plan-node choices |
| final Standards review | **PASS** | `029c269...`: P0=0, P1=0, P2=0; engineering GO |
| final specification review | **PASS** | `029c269...`: P0=0, P1=0, P2=0; Candidate scope and user-approved semantics fully matched |
| architecture dependency gate | **PASS** | 26/26 Candidate-focused architecture checks at the implementation checkpoint; final documentation-tree combination 44/44; Selection -> Research imports=0, Research -> Selection imports=0, only the approved Infrastructure adapter/schema cross-context files, future-Authority offenders=0 |
| complete collection | **PASS** | 3,330 nodes in 484 test files; `SUM=UNION=FULL=3330`, unique=3,330, duplicate occurrences=0, missing=0, extra=0 |
| full legacy plus target execution | **PASS** | all 3,330 exact nodes passed across the 20 non-overlapping serialized shards below; every shard exit=0 |
| refoundation plus Market/Selection/Research regressions | **PASS** | the exact full union includes every legacy and target refoundation, Market/PIT, Selection, Research Definition, Runtime, replay/recovery, concurrency, and compatibility node; none was excluded or xfailed |
| clean bootstrap/verify/recreate | **PASS** | PostgreSQL 16.14 isolated bootstrap, verify-only retry, exact guarded recreate, post-recreate checksum/catalog verification, and exact cleanup; see Section 11 |
| historical WP-02--WP-06 Verification bytes | **PASS** | all five SHA-256 values remain byte-identical to the starting-main blobs; see Section 14 |
| locked environment sync | **PASS** | `uv sync --frozen --extra dev --extra postgres`; the isolated `.venv` was rebuilt from the lock after resource remediation |
| final docs links/docs tests | **PASS** | `scripts/check_docs_links.py`; 7/7 docs-link tests; 1/1 status/runbook authority-ceiling test |
| final `tests/platform` isolated PostgreSQL gate | **PASS** | 33/33 on fresh `mra_wp07_final_platform_029c2692`; database was 25 MB and was dropped only after client count reached zero; exact Artifact/basetemp roots removed |
| Ruff | **PASS** | `uv run python -m ruff check .` at implementation checkpoint `029c269...` |
| mypy | **PASS** | `uv run python -m mypy`; 505 source files checked at `029c269...` |
| build | **PASS** | `uv run python -m build` produced `market_regime_alpha-0.1.0` wheel and sdist; SHA-256 `89c55cd3effb4192a538e09cb121bfee2e1323e11905084cfe092fdb2bb6fa05` and `473a51f5d63e41c7c628642a44aef5e3630aac7fcd327fba4899b5d3897a9428`; the two newly generated `dist` files were removed after audit |
| implementation/documentation diff | **PASS** | `git diff --check` before implementation commit `029c269...` and on the final documentation working tree; staged scope and historical Verification bytes are checked again before the containing documentation commit |
| Remote CI | **BLOCKED_BY_REPOSITORY_CONFIGURATION / NOT_RUN** | repository Actions permission returned `enabled=false`; no workflow was dispatched or observed |

Final non-overlapping full-collection shard evidence:

| Shard | Tests | Exit | Wall time | DB before cleanup | pytest temp before cleanup |
|---|---:|---:|---:|---:|---:|
| S01 | 129 | 0 | 164.85 s | 350 MB | 42 MB |
| S02 | 169 | 0 | 1.08 s | 7,537 kB | absent |
| S03 | 185 | 0 | 158.02 s | 114 MB | 91 MB |
| S04 | 177 | 0 | 18.77 s | 113 MB | 15 MB |
| S05 | 187 | 0 | 143.55 s | 371 MB | 31 MB |
| S06 | 127 | 0 | 35.75 s | 253 MB | 18 MB |
| S07 | 195 | 0 | 32.58 s | 105 MB | 1.6 MB |
| S08 | 196 | 0 | 12.50 s | 49 MB | 868 kB |
| S09 | 197 | 0 | 164.29 s | 715 MB | 41 MB |
| S10 | 200 | 0 | 102.03 s | 583 MB | 4.4 MB |
| S11 | 184 | 0 | 13.21 s | 96 MB | 0 B |
| S12 | 186 | 0 | 324.25 s | 649 MB | 67 MB |
| S13 | 121 | 0 | 109.97 s | 541 MB | 76 kB |
| S14 | 184 | 0 | 39.33 s | 193 MB | 992 kB |
| S15 | 187 | 0 | 43.41 s | 83 MB | 5.5 MB |
| S16 | 153 | 0 | 3.70 s | 7,537 kB | 7.1 MB |
| S17 | 198 | 0 | 6.50 s | 7,537 kB | 7.6 MB |
| S18 | 117 | 0 | 1.84 s | 7,537 kB | 3.8 MB |
| S19 | 191 | 0 | 3.06 s | 7,537 kB | 15 MB |
| S20 | 47 | 0 | 2.77 s | 7,537 kB | absent |
| **Total** | **3,330** | **all 0** | **1,381.46 s** | serialized, not additive | serialized, not additive |

Each shard used one exact disposable PostgreSQL database and a disjoint node-ID
list, ran only after the previous shard's zero-client teardown, and dropped only
its own database and pytest temporary tree. Final shard cleanup found zero
remaining shard databases, zero remaining clients, zero shard temp roots, and
about 1.5 GiB free space.

## 13. Investigated non-final attempts and root causes

The following failures were retained as engineering evidence and corrected at
the cause. None was converted to skip/xfail and no invariant was relaxed.

| Non-final attempt | Result | Root cause and correction |
|---|---|---|
| Candidate Domain/Application RED tests | **FAIL (TDD RED)** | required modules and APIs did not yet exist; implementation followed the approved RED/GREEN sequence |
| first complete implementation review | **FAIL** | review found replay, projection, reconciliation, and concurrency gaps; corrected in `cdeca1e` and `02e9456` without broadening scope |
| Decimal projection review | **FAIL** | Decimal calculation inherited ambient exponent/trap state; replaced by a fully isolated canonical context |
| extreme Decimal integration | **FAIL** | individually valid Decimal weights could exceed PostgreSQL unconstrained `numeric` physical limits only at final insert; added deterministic pre-UoW physical-bound validation |
| empty Dataset projection review | **FAIL** | a legal empty CandidateSet was incorrectly forced to project unused normalized weights; empty sets now write no score rows, while every non-empty set still projects weights |
| legal contribution drift test | **FAIL** | contribution/reconciliation validation was incomplete; exact plan and reload validation now reject drift |
| concurrent exact receipt build | **FAIL** | PostgreSQL reported real `40P01` from inconsistent receipt/dependency lock order; CandidateSet identity serialization first established consistent same-identity ordering |
| mandatory build-fence review | **FAIL** | the public build API still accepted a missing Runtime claim and could proceed unfenced; `246e582...` made the keyword-only claim mandatory and rejects `None` before opening a UoW or loading an Artifact |
| exact Runtime Step-kind review | **FAIL** | a live claim could identify a Step other than `BUILD_CANDIDATE_SET`; `029c269...` now validates the persisted exact Step kind at preflight and both final paths |
| cross-role Artifact concurrency tracer | **FAIL** | two distinct policies could acquire the same Artifact as `FOR SHARE` in one role and later both upgrade it to `FOR UPDATE` as the Dataset manifest; all Artifact roles are now deduplicated, conflict-checked, promoted to the strongest mode, and locked once in global UUID order |
| prior FAILED-receipt exact replay | **FAIL** | replay attempted Candidate Authority reconciliation before rejecting a durable FAILED receipt; receipt status is now checked first, the original deterministic error/receipt/audit remain unique, and the new Runtime Attempt is terminally finalized without Candidate writes |
| projection-precision schema/domain parity | **FAIL** | Domain admitted arbitrary values such as 10/100 while SQL defined a closed projection contract; both layers now admit only 64, 128, 256, 512, 1024, 2048, or 4096 |
| Candidate code-vocabulary parity | **FAIL** | Candidate Policy/component SQL admitted hyphens while the Domain accepted only canonical lower-case alphanumeric/underscore codes; SQL was narrowed so both now enforce `[a-z][a-z0-9_]{0,99}` without altering the distinct Eligibility vocabulary |
| Selection package ownership review | **FAIL** | the package description omitted Candidate Authority even though the implementation was Selection-owned; the package authority statement now names Candidate explicitly |
| early query proof | **FAIL** | missing query module/database/seed setup and an over-specific planner assertion; completed representative data and asserted bounded owner/index structure without freezing planner choices |
| early Ruff/single-file mypy | **FAIL** | fixture imports and isolated type-check invocation exposed local issues/import context; corrected source types/imports and retained the repository-wide gate |
| shared test database runs | **FAIL** | overlapping schema teardown caused concurrent `DROP SCHEMA` interference; final database-backed executions use fresh isolated databases and non-overlapping shards |
| current-session Market fixture | **FAIL** | fixture emitted a post-capture DAILY bar after Shanghai close, making PIT behavior depend on wall-clock time; fixture now emits only bars whose close is at or before capture completion |
| stale-worker setup | **FAIL** | direct lease mutation was correctly rejected by the Runtime heartbeat trigger before the intended assertion; test now reaches staleness through the real Runtime contract |
| first Runtime vocabulary attempt | **FAIL** | it invented `REGISTER_CANDIDATE_POLICY`, which is not a real Step kind; removed it and used only the approved six-step target slice |
| focused command typo | **FAIL** | an invocation named a nonexistent test file; corrected the command without changing the collection |
| read-only wrapper | **FAIL** | a wrapper omitted the required `read_only` argument; corrected the real UoW call contract |
| historical-hash command | **FAIL** | a glob named a nonexistent historical verification path; replaced with the five explicit WP-02--WP-06 paths |
| first schema report | **FAIL** | reporting referenced a nonexistent result attribute after database work had succeeded; reran on a disposable database and reported only actual verification fields |
| first full-suite attempt after `02e9456` | **INTERRUPTED / NOT FINAL** | intentionally stopped with exit 130 when code review found the Decimal-context defect; no test failure was promoted from that run |
| single-command full suite at `8209131` | **FAIL (RESOURCE)** | PostgreSQL raised `DiskFull` after 37 tests; this was storage exhaustion, not a test assertion; the corrected final implementation moved to isolated non-overlapping shards |
| simultaneous refoundation run during storage exhaustion | **FAIL (RESOURCE)** | cascaded PostgreSQL recovery/DiskFull errors from the same exhausted volume; results were discarded and not counted as regression evidence |
| first large application shard at `e82eac1` | **INTERRUPTED / NOT FINAL** | stopped proactively around 44% when free space approached the same failure boundary; it was repartitioned into smaller non-overlapping fresh-DB shards |
| implementation-`246e582` shard attempts | **INTERRUPTED / NOT FINAL** | stopped when the final review exposed Step-kind, cross-role Artifact-lock, FAILED-receipt, schema/domain-parity, and ownership-description defects; those executions were invalidated rather than promoted to final proof |
| first final-collection parser | **FAIL (HARNESS; ZERO TESTS RUN)** | the parser assumed an older pytest collection-output format and produced an empty shard set; it was replaced with an in-process pytest collection hook, then proved the exact 3,330-node union before execution |
| final concurrency-tracer bring-up | **FAIL (TEST HARNESS)** | tracer construction exposed an accidental Eligibility-regex replacement, an invalid hexadecimal test character, an unescaped psycopg percent literal, and the wrong Artifact-binding test type; the Eligibility vocabulary was restored and the harness defects corrected before the fresh-database tracer passed |
| first final-schema shell probe | **FAIL (HARNESS; NO MUTATION)** | a `psql -c` variable-substitution form was syntactically invalid before any database mutation; corrected parameter handling then completed the isolated bootstrap/verify/recreate proof |

### 13.1 Resource remediation

The resource incident was audited before cleanup. Thirty-one exact
zero-connection `mra_wp07_*` disposable test databases, totaling about 1.2 GB,
were removed after PostgreSQL recovered. The exact pytest temporary directory
and worktree pytest cache were removed; the uv cache was cleaned (about
870.1 MiB); the worktree `.venv` was removed and rebuilt with
`uv sync --frozen --extra dev --extra postgres`. Free space recovered to about
1.6 GiB before serialized shards resumed.

No historical/business database, especially the approximately 18 GB
historical research-evidence database, was dropped or modified. No source,
Git history, user data, or unspecified workspace was removed. All deleted
items were rebuildable test/environment artifacts; the virtual environment was
recreated immediately.

## 14. Historical WP-02--WP-06 evidence immutability

WP-07 did not rewrite historical Verification records. Their byte hashes are:

```text
WP-02  4daf0f3a3a402f8284cfe1a4ba87b37a8ca3ea0f83bbacb347a7d9debe7d1a2d
WP-03  3b5be2afa013f2639b618cb36fc3c8896d3ad1b67c47a57242c40d8724986e59
WP-04  6a8aedda78a6246a64b26335a6506315f30322c948e181b90760d73b473103a4
WP-05  990dd4f9dfbed7d1bd941301290f6ee7eb8a0b9c737efc653fa55821aa719caf
WP-06  59d7bd856eb874dc9e7a1c1f696e86f446facf3a8bd845b09e7b1cfe2bc4746c
```

Those reports remain exact-SHA historical evidence for their own work
packages; WP-07 neither retroactively expands their scope nor treats them as
Candidate proof.

## 15. Post-Candidate real dependency audit facts

The target draft currently has Foundation, Market/PIT, Selection Core,
Research Definition Core, and the five Candidate relations. It has no target
business Authority for:

```text
TargetDefinition
TargetCheckpoint
ResearchPartition
Experiment
Model
DecisionRun
Outcome
Evaluation
Evidence
Qualification
```

The existing target package name `research_qualification` currently contains
only FeatureDefinition and Dataset/DatasetSource Authority; its name is not
Qualification Authority.

The required next dependency review is code-first because legacy code contains
multiple independent realized-label computations from Market bars:

- `controlled_operation/outcome_evidence.py` computes returns and MFE/MAE;
- `research_evaluation/targeted_outcome.py` re-reads bars and computes a label
  despite a prospective outcome input;
- `historical_corpus/historical_target_semantics.py` and
  `historical_corpus/decision_materializer.py` independently derive outcomes
  from normalized bars;
- `research_validation/free_historical_samples.py`,
  `research/tencent_composite_materialization.py`,
  `research/mr1_morning_pop.py`, and `strategies/path_outcomes.py` contain
  additional label/outcome calculations.

Those values flow into current qualification/model/calibration/forecasting/
shadow/evaluation paths, including `postgres_qualification.py`,
`postgres_research_model.py`, `path_calibration.py`,
`postgres_calibration_qualification.py`, `forecasting/path.py`,
`strategy_shadow/economics.py`, and `research_evaluation/dataset.py`.

The dependency review must therefore decide an acyclic ownership model before
any next implementation. The leading constraint is that TargetDefinition and
TargetCheckpoint may define what is observed, while one future Outcome
Authority must own realized observation, status, finality, availability, and
lineage. Research should consume that owner through a narrow read-only
OutcomeObservation port rather than reconstructing realized labels from bars.
Downstream numeric copies, if any, must remain non-authoritative and reconcile
by owner identity/hash. Historical, prospective, and replay provenance modes
must not become parallel truths, and market Target Outcome must remain distinct
from Fill/Position-derived TradeOutcome.

These are dependency-audit facts and constraints only. WP-07 does not decide
whether Research Evaluation or Decision/Outcome comes first, does not approve
an implementation order, and does not authorize Target, Model, Evaluation,
Evidence, Qualification, Decision, or Outcome implementation.

## 16. Candidate Closure exit ceiling

The local Candidate engineering exit decision binds implementation checkpoint
`029c26928af436d7788da1cce3a53c94b96377bf` and its containing documentation
commit reported by the final handoff. All local gates required by this ledger
are terminally recorded above. Candidate Closure engineering GO means only:

- the five-table Selection-owned Candidate draft is internally coherent;
- the approved deterministic ranking and complete Dataset funnel are executable;
- its transactions, replay, stale fence, failure, concurrency, recovery,
  queries, indexes, and package seam have local engineering proof; and
- the repository's full legacy plus target behavior remains green at that SHA.

It does not make Candidate canonical, cut over Runtime, qualify any Provider or
model, prove Alpha, create a Decision/Outcome truth, place an order, or admit
Production. The sole next authorized activity is the real dependency review
described above.
