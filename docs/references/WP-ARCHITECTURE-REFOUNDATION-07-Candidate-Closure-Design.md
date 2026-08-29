# WP-ARCHITECTURE-REFOUNDATION-07 Candidate Closure Design

> **Status:** CANONICAL_TARGET_ARCHITECTURE
> **Design State:** `APPROVED_DESIGN / IMPLEMENTATION_NOT_STARTED`
> **Schema Epoch:** `MRA_REFOUNDATION_1`
> **Release State:** `DRAFT`
> **Cutover State:** `NOT_CUT_OVER`
> **Authority:** Approved Candidate Closure design checkpoint; not implementation, verification, Research Evaluation, Decision/Outcome, trading, Runtime Cutover, or Production Authority
> **Owner:** Market Regime Alpha maintainers
> **Approved At:** 2026-08-30
> **Starting Main:** `origin/main@d45fe83730a75dfa6083db9b6c929b37838fdd50`
> **Design Checkpoint:** assigned by the independent pure-document checkpoint commit
> **Implementation Evidence:** none at this checkpoint

This document freezes the approved WP-07 design before any Candidate code, DDL,
seed, test, or Runtime implementation is added. Candidate remains permanently
owned by `market_regime_alpha.selection`. This work package closes Candidate
Authority only. It does not create or authorize Model, ModelVersion, Target,
Evaluation, Evidence, Qualification, Decision, Outcome, Execution, or Runtime
Cutover behavior.

## 1. Scope and non-scope

WP-07 introduces exactly these five Candidate Authority relations:

```text
candidate_policy
candidate_policy_component
candidate_set
candidate
candidate_score_component
```

The only commands introduced by this closure are the Candidate-specific
registration/build behaviors required to own those relations, principally
`RegisterCandidatePolicy` and `BuildCandidateSet`. The test-only target
vertical slice uses the exact Step kind `BUILD_CANDIDATE_SET`.
`BUILD_CANDIDATES` is not a target name and receives no compatibility alias,
dual-write path, dispatcher fallback, or second handler.

The following are expressly outside WP-07:

- Model or ModelVersion definitions, fitted parameters, predictions, or
  qualification;
- TargetDefinition, TargetCheckpoint, ResearchPartition, Experiment,
  Evaluation, Evidence, Assessment, or Qualification owners;
- DecisionRun, Context, Signal, Forecast, Opportunity, Thesis, Strategy,
  Portfolio, Outcome, Execution, Account, Fill, Position, or broker behavior;
- placeholders, nullable future foreign keys, generic owner registries,
  CommandBus/Mediator/service-location infrastructure, compatibility writers,
  fallback reads, or dual writes;
- Production Runtime/CLI cutover or any promotion beyond
  `MRA_REFOUNDATION_1 / DRAFT / NOT_CUT_OVER`.

Candidate V1 is a transparent deterministic cross-sectional ranking. It is not
a predictive model. A Candidate score is descriptive ranking evidence and
must never be named or interpreted as a probability, expected return, MFE,
MAE, Target value, Entry instruction, or trading authorization.

## 2. Permanent bounded-context and dependency seam

### 2.1 Ownership

Candidate Domain, Application, ports, repositories, and PostgreSQL UoW live
under the permanent Selection bounded context. The intended module boundary is:

```text
market_regime_alpha.selection
  domain/candidate_*.py
  application/candidate_*.py
  ports/candidate_repository.py
  ports/candidate_uow.py
  ports/research_inputs.py

market_regime_alpha.infrastructure.postgres
  candidate_uow.py
  repositories/candidate.py
  queries/candidate_research_inputs.py

market_regime_alpha.queries
  candidate.py
```

Physical filenames may be made cohesive during implementation, but ownership
and import direction are fixed. Selection Domain/Application imports neither
`market_regime_alpha.research_qualification` nor PostgreSQL infrastructure.
Research Qualification imports no Selection Candidate module. The composition
root alone wires concrete adapters.

### 2.2 Selection-owned Research-input port

Selection defines a narrow read-only `CandidateResearchInputs` port and
Selection-owned immutable DTOs. The contract supplies only facts that
`BuildCandidateSet` is allowed to consume:

- the exact `DECISION_INPUT` Dataset identity and content hash;
- the Dataset's DecisionTime, Universe revision, Eligibility policy, ordered
  FeatureDefinition identities, and immutable manifest/code/config Artifact
  triples;
- every Dataset population row, preserving manifest order only as input
  identity and never as a ranking tie-break;
- for every population row and required Feature, its typed raw value or exact
  `MISSING / UNKNOWN / STALE / CONFLICT` status, reason, Feature identity, and
  deterministic cell/source-lineage hash;
- exact Dataset and FeatureDefinition dependency identities required for final
  revalidation.

The PostgreSQL infrastructure adapter may depend on both contexts to translate
Research-owned Dataset/FeatureDefinition facts into those Selection-owned
DTOs. That adapter is the only cross-context seam. It does not expose a
Research repository, Research aggregate, generic DTO registry, or Research
UoW to Selection. This yields the one-way dependency:

```text
Selection Candidate Application
  -> Selection-owned CandidateResearchInputs port/DTO
  <- PostgreSQL cross-context adapter
     -> Research Definition tables and immutable Dataset Artifact
```

There is no `selection -> research_qualification` package edge and therefore
no Selection/Research package cycle.

### 2.3 Separate Candidate UoW

Candidate uses a narrow `CandidateUnitOfWork`; Selection Core and Research
UoWs are not expanded into a mega-UoW. The Candidate UoW owns only Candidate
repositories plus the already-established shared receipt, audit, Artifact
verification linkage, Runtime fence, Attempt, and Step finalization operations
needed for the final atomic write. Repositories never commit.

## 3. Candidate V1 authority model

### 3.1 `candidate_policy`

`candidate_policy` is immutable Selection policy Authority. It records:

- stable policy identity, semantic code and version, and canonical content
  hash;
- `ARITHMETIC_MIDRANK` normalization;
- `COMPETITION` composite rank method;
- `STRICT_COMPLETE_CASE` missing policy;
- explicit `TOP_K` selection policy and positive `requested_top_k`;
- `INCLUDE_ALL_BOUNDARY_TIES` tie policy;
- descriptive score semantics and the Decimal projection algorithm/version;
- exact policy code/config Artifact identity, hash, and size triples;
- declared component count and immutable lifecycle metadata.

Policy does not bind a Dataset, DecisionTime, DecisionRun, ModelVersion,
Target, Evaluation, Evidence, or Qualification. One policy can be applied to
multiple immutable Decision-input Datasets.

### 3.2 `candidate_policy_component`

Each component binds exactly one real Research-owned FeatureDefinition and
records:

- immutable component identity, code, and ordinal;
- parent CandidatePolicy identity;
- exact FeatureDefinition identity and content hash;
- the supported numeric Feature value type;
- explicit desirability direction (`HIGHER_IS_BETTER` or
  `LOWER_IS_BETTER`);
- one positive canonical `declared_weight` stored as PostgreSQL `numeric`.

The component does not bind Dataset, DatasetSource, ModelVersion, Target,
Evidence, or any future owner. `declared_weight` is the only weight Authority
on the policy component. A finite Decimal `normalized_weight` is not stored on
the policy and cannot become a second policy truth.

Policy/component constraints require unique `(candidate_policy_id, ordinal)`,
unique `(candidate_policy_id, component_code)`, and unique
`(candidate_policy_id, feature_definition_id)`. The component count must match
the immutable policy declaration. Only numeric FeatureDefinitions admitted by
the closed Candidate V1 value-type contract may be bound.

### 3.3 `candidate_set`

`candidate_set` is the frozen result and reconciliation root for exactly one
CandidatePolicy applied to exactly one immutable `DECISION_INPUT` Dataset. It
records at least:

- immutable CandidateSet identity and canonical result hash;
- exact CandidatePolicy and Dataset identities and content hashes;
- copied, FK-checkable Dataset scope: DecisionTime, Universe revision, and
  Eligibility policy;
- requested Top-K, component count, and
  `decimal_projection_precision`;
- `population_count`, `rankable_count`, `unrankable_count`,
  `selected_count`, and `ranked_not_selected_count`;
- complete score-matrix row count;
- component `AVAILABLE / CONSTANT / NOT_ESTIMABLE` counts;
- CandidateSet ranking status `AVAILABLE / CONSTANT / NOT_ESTIMABLE`;
- `composite_distinct_count`;
- boundary score/rank, strictly-above-boundary count, boundary group count,
  selected overflow count, whether the boundary contains a tie, and whether
  `INCLUDE_ALL_BOUNDARY_TIES` expanded the requested selection;
- exact dependency fingerprint and result fingerprint required for idempotent
  replay and revalidation.

`(candidate_policy_id, dataset_id)` is unique. CandidateSet has no DecisionRun,
ModelVersion, Target, Evaluation, Evidence, Qualification, or Context foreign
key. Empty Dataset is a valid CandidateSet with all funnel counts zero,
`NOT_ESTIMABLE` ranking status, no boundary, and no score rows.

### 3.4 `candidate`

Every Dataset population row produces exactly one Candidate record. Candidate
records the parent set/policy/Dataset scope, the real instrument identity, its
exact population `dataset_source` identity, a closed terminal disposition,
and its rank/score or unrankable reason:

```text
SELECTED
RANKED_NOT_SELECTED
UNRANKABLE
```

`SELECTED` and `RANKED_NOT_SELECTED` require a composite score and competition
rank. `UNRANKABLE` requires both to be null and requires an explicit reason
derived from the incomplete required Feature statuses. Unique
`(candidate_set_id, instrument_id)` and exact same-Dataset population-source
foreign keys prevent duplication or cross-Dataset drift.

There is deliberately no unique `(candidate_set_id, rank)` constraint. Equal
scores must have equal rank. A non-unique set/rank access index supports reads
without turning rank into unique identity.

### 3.5 `candidate_score_component`

The relation is a complete immutable matrix: one typed score row exists for
every `Candidate x CandidatePolicyComponent`, including every UNRANKABLE
Candidate. Each row records only Candidate calculation facts needed to
reconstruct and explain the build:

- exact Candidate, CandidateSet, CandidatePolicy, PolicyComponent,
  FeatureDefinition, Dataset, and instrument identities needed for same-scope
  composite foreign keys;
- typed raw numeric value when the Dataset cell is `AVAILABLE`;
- exact raw cell status and reason;
- deterministic `cell_source_lineage_hash` for validation of the immutable
  Dataset cell/source lineage;
- CandidateSet-projected `normalized_weight` on every row, plus percentile and
  contribution when the Candidate is rankable;
- the Candidate disposition required for local reconciliation.

The table must not contain `DatasetSource UUID[]`, any source identity array,
or a GIN index over a source array. It creates no new lineage Authority.
Canonical Dataset lineage remains owned by the immutable Dataset manifest and
relational `dataset_source`. The Candidate dossier follows
`CandidateSet.dataset_id -> Dataset manifest/dataset_source` to explain original
sources. A direct CandidateComponent-to-DatasetSource many-to-many link may be
considered only in a later separately reviewed work package if a measured real
query profile requires it; WP-07 adds no sixth Candidate Authority table.

A UNIQUE constraint on `(candidate_id, candidate_policy_component_id)` closes
the matrix identity. Same-set/policy/Dataset/Feature composite foreign keys and
closed status/value checks reject cross-owner or mistyped rows.

For a rankable Candidate every required raw status is `AVAILABLE`, and every
score row has percentile, projected normalized weight, and contribution. For
an UNRANKABLE Candidate the available raw cells remain recorded, but all
component rows still retain the same projected normalized weight while every
percentile and contribution is null. Partial scoring of an incomplete row is
forbidden and the fixed denominator remains reconstructible.

## 4. Dataset is the sole Candidate population

The Dataset population is already authoritatively proven as:

```text
UniverseMember = INCLUDED
INTERSECT
EligibilityAssessment = ELIGIBLE
```

`BuildCandidateSet` consumes that exact immutable population. It must not
re-run Universe membership, Eligibility, Market hard gates, liquidity gates,
or other screening. It cannot read a broader instrument catalog, silently
discard a row, or add an instrument absent from the Dataset.

Consequently:

```text
population_count = rankable_count + unrankable_count
rankable_count = selected_count + ranked_not_selected_count
candidate_count = population_count
score_component_count = population_count * component_count
```

For an empty Dataset all four equalities remain valid. Any write-plan or
post-write reload that violates them fails atomically.

## 5. Exact ranking and projection semantics

### 5.1 Strict complete case

Let `R` be the rankable cross-section. A Dataset row belongs to `R` if and only
if every required policy component cell is `AVAILABLE` with a valid typed
numeric value. If any required component is `MISSING`, `UNKNOWN`, `STALE`, or
`CONFLICT`, that row is `UNRANKABLE`; score and rank are null and no imputation
occurs.

The value `0.5` is never a missing-value fill. Assigning `0.5` without applying
the ordinary `n > 1` formula is permitted only for an `AVAILABLE` Feature with
one distinct value in the complete rankable cross-section. In a nonconstant
cross-section the ordinary arithmetic-midrank formula may naturally evaluate to
`0.5` for a middle value or tie group; that component remains `AVAILABLE`, not
`CONSTANT`, and no imputation has occurred.

### 5.2 Arithmetic midrank percentile

All calculations are performed with exact rational arithmetic. For a required
Feature in a rankable cross-section of size `n > 1`, orient values so a larger
oriented value is always better. For a Candidate with:

- `w`: number of rankable values strictly worse than its value; and
- `t`: number of rankable values equal to its value,

the tie-aware percentile is:

```text
percentile = (w + (t - 1) / 2) / (n - 1)
```

This is the arithmetic midrank mapped exactly to `[0, 1]`. Equal Feature
values receive equal percentiles. Instrument code, UUID, row position, source
identity, and insertion order are never inputs to percentile, composite score,
rank, boundary, or selection.

The approved constant cases are normative:

1. Only an `AVAILABLE` Feature whose `distinct_count = 1` in the complete
   rankable cross-section receives the special constant assignment `0.5`; its
   component ranking status is `CONSTANT`. An ordinary nonconstant arithmetic
   midrank may also be numerically `0.5`, without changing its `AVAILABLE`
   status.
2. `MISSING / UNKNOWN / STALE / CONFLICT` never receive `0.5` and make the row
   `UNRANKABLE` under `STRICT_COMPLETE_CASE`.
3. If `rankable_count = 1`, every required Feature percentile is `0.5`, the
   composite score is `0.5`, competition rank is `1`, and the Candidate is
   selected because `requested_top_k > 0`. CandidateSet status is `CONSTANT`,
   explicitly indicating that no cross-sectional discrimination exists.
4. If some components are constant and others discriminate, each constant
   component contributes its fixed normalized weight times `0.5`; weights are
   not dynamically redistributed. CandidateSet status is `AVAILABLE`.
5. If every required component is constant, every rankable Candidate has
   composite score `0.5` and rank `1`. Boundary ties are included completely;
   selected count may exceed requested Top-K and the CandidateSet records both
   `CONSTANT` and boundary-tie diagnostics.
6. If `rankable_count = 0`, no percentile, contribution, score, rank, or
   boundary is computed; CandidateSet status is `NOT_ESTIMABLE` and
   `selected_count = 0`.

### 5.3 Declared weights and exact rational normalization

A canonical Decimal declared weight represents an exact rational number. At
build time the application converts every declared weight to that exact
rational and normalizes with:

```text
exact_normalized_weight_i
  = exact_declared_weight_i / sum(exact_declared_weights)
```

The exact rational computation is semantic Authority. It is deterministically
reconstructible from the immutable declared weights and the policy's ranking
algorithm/version. There is no second normalized-weight Authority on
`candidate_policy_component`.

The application then applies the CandidateSet's canonical
`decimal_projection_precision` and projection contract to produce PostgreSQL
`numeric` values. The projected normalized weight is stored only on each
`candidate_score_component`, beside the percentile and contribution produced
under the same projection contract. Repeating decimals are not required to
sum to exactly `1` after finite Decimal projection; such a database CHECK would
incorrectly replace the exact rational semantics.

### 5.4 Composite, projection, and rank

For each rankable Candidate, before Decimal projection:

```text
exact_contribution_i
  = exact_normalized_weight_i * exact_percentile_i

exact_composite_score
  = sum(exact_contribution_i for every required component i)
```

The rank/tie/boundary decisions use the exact rational composite values, not
float and not prematurely rounded Decimals. Public and persisted values use
Python `Decimal` and PostgreSQL `numeric`; binary float is prohibited.

The canonical projection uses `ROUND_HALF_EVEN` at the CandidateSet precision.
Implementation starts with precision 64 and increases deterministically, by
doubling up to the closed maximum 4096, whenever projection would collapse or
reverse two unequal exact values needed to reconstruct the score order. If the
closed maximum cannot preserve the exact equality/order classes, the command
fails deterministically without Candidate Authority writes.

Projected contribution rows are explanatory finite projections. The projected
Candidate score is independently projected from the exact composite; it is not
required to equal a database sum of already-projected contributions. The
result/dependency fingerprints, declared weights, raw values, projection
precision, and algorithm identity make the exact result reproducible.

Competition rank is:

```text
rank(candidate) = 1 + count(rankable composite scores strictly greater)
```

Equal exact composite scores therefore receive equal rank and rank gaps are
valid. Identity-based tie-breaks are forbidden.

### 5.5 Top-K and boundary ties

For a non-empty rankable cross-section, the boundary score is the exact score
at ordinal `min(requested_top_k, rankable_count)` in descending score order.
Every Candidate with exact score greater than or equal to that boundary is
`SELECTED`; all other rankable Candidates are `RANKED_NOT_SELECTED`.

`INCLUDE_ALL_BOUNDARY_TIES` is unconditional. If a tie group crosses requested
Top-K, the entire group is selected. CandidateSet records the boundary score
and rank, strictly-above count, boundary group size, selected overflow, tie
presence, and whether boundary expansion occurred. `selected_count` may exceed
`requested_top_k`. No instrument identity can select one member of an equal-
score group over another.

## 6. Component and CandidateSet diagnostics

Component diagnostics may be a replaceable query/view derived from immutable
Candidate, score-component, and policy-component rows; they are not a sixth
Authority table. For every CandidateSet component the dossier exposes:

- `observed_count`: rankable rows whose raw status is `AVAILABLE` and for which
  a percentile was computed;
- `distinct_count`: distinct typed raw values among those observed rankable
  rows;
- literal `missing_count`, plus separate `unknown_count`, `stale_count`, and
  `conflict_count` across the complete Dataset population;
- `raw_available_count` across the complete population, including available
  cells belonging to an otherwise incomplete Candidate;
- component status:
  - `NOT_ESTIMABLE` when `rankable_count = 0`;
  - `CONSTANT` when `rankable_count > 0` and `distinct_count = 1`;
  - `AVAILABLE` when `rankable_count > 0` and `distinct_count > 1`.

The derivation starts from CandidateSet x PolicyComponent and left joins score
rows, so an empty Dataset still yields one diagnostic row per required
component with zero counts and `NOT_ESTIMABLE`.

CandidateSet status is component-based:

- `NOT_ESTIMABLE` when no Candidate is rankable;
- `CONSTANT` when one or more Candidates are rankable and every required
  component is `CONSTANT`;
- `AVAILABLE` when any required component is `AVAILABLE`, including the case
  where different component contributions happen to cancel into one composite
  value.

`composite_distinct_count` separately reports whether the composite actually
distinguishes Candidates, preventing component availability from being
misreported as realized composite separation.

## 7. PostgreSQL enforcement

Declarative PostgreSQL constraints are preferred for all row-local,
referential, role-shape, uniqueness, and status/value invariants. The five new
tables reuse the established append-only mutation-rejection function/trigger;
WP-07 introduces no Candidate-specific trigger/function unless implementation
proves a named invariant cannot be expressed declaratively and records why.

Required enforcement includes:

- real FKs to CandidatePolicy, PolicyComponent, Dataset, FeatureDefinition,
  DecisionTime/scope owners, instrument, and the Dataset's POPULATION
  `dataset_source` as appropriate;
- composite FKs that prove repeated set/policy/Dataset/instrument/Feature
  identities agree rather than merely existing independently;
- closed enum/status checks and typed raw-value/value-status checks;
- Candidate disposition versus score/rank nullability checks;
- score-component percentile/contribution nullability consistent with the
  Candidate's rankability;
- positive declared weights, positive requested Top-K, valid projection
  precision, non-negative counts, and row-local boundary diagnostics;
- unique policy semantic identity, component natural identities,
  `(policy, Dataset)` CandidateSet, `(set, instrument)` Candidate, and
  `(Candidate, component)` score row;
- no unique Candidate rank constraint;
- application pre-write and post-reload reconciliation for the cross-row
  funnel, complete score matrix, exact tie/rank, diagnostics, and result hash.

Leading-FK and query indexes support exact reload and dossiers. At minimum the
physical design covers CandidateSet Dataset/policy lookup, Candidate by
set/disposition, non-unique set/rank lookup, score rows by Candidate and by
set/component, and existing Dataset-source lineage lookup. No UUID-array/GIN
lineage index is permitted.

## 8. Command and transaction boundaries

### 8.1 RegisterCandidatePolicy

Policy registration does not load or rank a Dataset. Its one short Candidate
transaction is:

1. validate the live Runtime fence when present;
2. start/replay the exact command receipt;
3. lock and exactly validate the policy code/config Artifacts and every real
   FeatureDefinition binding through Candidate-owned ports;
4. insert `candidate_policy` and its complete ordered
   `candidate_policy_component` rows;
5. reload and reconcile identity, component count, declared weights, and
   content hash;
6. persist the successful receipt and audit;
7. finalize Attempt/Step success under the same live fence;
8. commit once.

It writes only Policy and PolicyComponent Candidate authorities. An exact
successful replay returns the existing Policy without rewriting it.

### 8.2 BuildCandidateSet

Dataset Artifact verification/read/parse and ranking computation must not hold
the final PostgreSQL CandidateSet write transaction open. The build sequence is:

1. in a short read/probe scope, resolve immutable Dataset, policy, components,
   FeatureDefinitions, Artifact metadata, receipt identity, and current Runtime
   fence, then close the scope;
2. outside a PostgreSQL write transaction, verify Dataset manifest bytes/hash/
   size/schema, read and parse the complete Dataset, translate through the
   Selection-owned input DTO, calculate exact rational normalization,
   percentiles, components, composites, ranks, dispositions, diagnostics, and
   the complete immutable write plan;
3. open a fresh, short Candidate transaction;
4. validate the live monotonic Runtime fence before any business write;
5. reload and exactly revalidate all policy, component, Dataset,
   FeatureDefinition, scope, Artifact, population, and dependency identities
   against the prepared plan;
6. write CandidateSet, every Candidate, and the complete score-component
   matrix; Policy and PolicyComponent are pre-existing locked dependencies, not
   writes of this command;
7. reload/reconcile all counts, statuses, ranks, boundary diagnostics,
   fingerprints, and matrix identities;
8. persist the successful command receipt and linked Artifact verification;
9. append the audit event;
10. finalize Attempt and Step success under the same live fence;
11. commit once.

Nothing in steps 6-10 is committed if any later step fails. The final
transaction does not verify/read Artifact bytes, parse the Dataset, compute
ranking, re-run Universe/Eligibility/Market gates, or invoke a Research UoW.

## 9. Idempotency, concurrency, failure, and recovery

Command identity and deterministic semantic request fingerprints bind the exact
policy, Dataset, algorithm/projection contract, and dependencies. They exclude
Runtime Attempt, Step, lease, and fence identities so exact recovery can replay
the same business request under a later valid Attempt. Receipt and Runtime
finalization metadata separately bind the executing Step/Attempt/fence.
An exact successful retry returns the original CandidateSet and does not read
Artifact bytes, rerank, or rewrite Authority. The initial replay probe is short;
if it tentatively creates a pending receipt for new work, that probe is rolled
back before the outside-transaction Artifact/math phase.

Concurrent exact commands converge on one `(CandidatePolicy, Dataset)` set and
one successful receipt/result. A same idempotency key with different semantics
fails closed. A stale worker cannot write a Candidate fact, receipt, audit, or
Runtime finalization.

Deterministic command failure uses the established shared failure contract:

```text
Candidate business UoW rolls back completely
-> fresh Candidate UoW
-> validate the live Runtime fence
-> persist failed receipt
-> append audit event
-> finalize Attempt and Step failure
-> commit once
```

If the fence is stale, even the failure record is rejected and no stale write
occurs. Injected failure at Candidate rows, score rows, receipt, audit, or
Runtime finalization must prove full atomic rollback. Recovery reuses a durable
successful receipt and creates only genuinely missing work; replay compares
exact owner identities, statuses, values, ranks, counts, and result hashes.

## 10. Test-only target vertical slice

WP-07 adds a target-only executable proof slice:

```text
CAPTURE
-> NORMALIZE_PIT
-> FREEZE_UNIVERSE
-> ASSESS_ELIGIBILITY
-> REGISTER_DATASET
-> BUILD_CANDIDATE_SET
```

The slice uses real target owners at every step and an immutable Decision-input
Dataset. It proves the Candidate path without changing the production Runtime
dispatcher/CLI or cutting over from legacy. It introduces no command registry,
compatibility path, alias for `BUILD_CANDIDATES`, or cross-context mega-UoW.

## 11. Funnel, dossier, and query-plan contract

The Candidate funnel query returns, for an exact CandidateSet:

- Dataset population and all five reconciled counts;
- ranking status and composite distinct count;
- requested Top-K and all boundary-tie diagnostics;
- per-disposition and per-unrankable-reason counts;
- component observed/distinct/raw-status counts and component status.

The Candidate dossier returns CandidateSet/policy/Dataset identities, each
Candidate's terminal disposition/score/rank/reason, every typed score component
and its Feature identity/raw status/value/percentile/projected weight/
contribution/cell-lineage hash, and the Dataset manifest/source lineage reached
through `CandidateSet.dataset_id`. It does not duplicate DatasetSource lineage
onto Candidate score rows.

Representative PostgreSQL plan proof uses real predicates and representative
data for funnel, dossier, set reload, rank/disposition, and component lookup.
Tests inspect `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` structurally: the owner
relations, bounded predicates, and an accepted owner-index family must be
present where applicable. They must not hard-code planner cost, elapsed time,
row timing, one exact node type, or one exact valid index when PostgreSQL may
legitimately choose among equivalent bounded indexes.

## 12. TDD and engineering proof plan

Implementation proceeds test-first at the approved seams. No test may be
skipped, xfailed, deleted, weakened, or made less strict to obtain a pass.

The Candidate-focused RED/GREEN sequence covers:

1. policy/component immutable identity, only declared-weight Authority, and
   forbidden Dataset/ModelVersion/future dependencies;
2. strict Dataset population and complete Candidate/score matrix;
3. exact rational weight normalization and Decimal projection;
4. arithmetic midrank for distinct values, ties, constant components,
   singleton rankable sets, mixed constant/discriminating components, all-
   constant sets, no-rankable sets, and empty Datasets;
5. `MISSING / UNKNOWN / STALE / CONFLICT` complete-case rejection with no
   imputation or silent row deletion;
6. exact composite, competition rank, permutation/identity invariance,
   `INCLUDE_ALL_BOUNDARY_TIES`, and selection overflow;
7. PostgreSQL constraints, append-only behavior, FK/scope consistency,
   idempotency, and declarative rejection;
8. Artifact I/O and math outside the final write transaction;
9. fence, exact dependency revalidation, success atomicity, deterministic
   failure atomicity, concurrency, replay, and recovery;
10. the complete test-only target vertical slice;
11. funnel/dossier explanation including Dataset-source traversal and component
    diagnostics;
12. representative query-plan/index behavior and import-graph acyclicity.

The final engineering ledger must run every Python gate with `uv run` and
include Candidate-focused tests, all refoundation tests, Market/Selection/
Research regressions, the complete legacy plus target collection, PostgreSQL
clean bootstrap/verify/guarded recreate, Runtime/concurrency/replay/recovery,
architecture dependencies, documentation checks/tests, Ruff, mypy, build, and
`git diff --check`. Resource contention may be addressed only with a fresh
isolated database and non-overlapping shards whose totals prove the complete
collection. Every non-final failure is retained with root cause and correction.
Remote CI remains `BLOCKED / NOT_RUN` if repository Actions are still disabled.

## 13. Historical evidence immutability

WP-02 through WP-06 Verification records are historical exact-SHA evidence and
must remain byte-for-byte unchanged. The design and implementation checkpoints
must verify their pre-existing file hashes before claiming closure. WP-07 adds
its own later exact-SHA verification record; it does not rewrite earlier
reports, retroactively change their scope, or promote their engineering proof.

This design checkpoint itself changes current architecture/Roadmap/invariant
prose only. It provides no implementation or passing-test claim.

## 14. Post-Candidate dependency review, not a frozen next stage

Candidate Closure does not freeze or authorize a rule that complete Research
Evaluation/Evidence/Qualification must necessarily precede Decision/Outcome.
After WP-07 engineering closure, the next work is a fresh code-first dependency
audit across:

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

The audit must inspect actual code, PostgreSQL ownership, current call chains,
and legacy semantics before choosing the next checkpoint order. In particular,
Research must not independently construct realized labels that compete with a
future Outcome Authority and create two truths for the same observed result.

The WP-07 Roadmap statement is therefore only: **perform the next-stage real
dependency review after Candidate Closure**. It grants no implementation
authority for Research Evaluation, Decision/Outcome, Target, Model, Evidence,
or Qualification, and it makes no advance decision about their order.

## 15. Candidate Closure implementation exit

WP-07 may report engineering GO only when all of the following are true at one
final exact SHA:

- the five and only five Candidate Authority tables exist in the verified
  `MRA_REFOUNDATION_1 / DRAFT / NOT_CUT_OVER` catalog;
- the package seam is acyclic and Candidate remains permanently in Selection;
- real Dataset/FeatureDefinition inputs, exact rational ranking, Decimal
  projection, strict missingness, constant diagnostics, competition rank, and
  inclusive boundary ties pass executable tests;
- every Dataset row and every Candidate-component pair is reconciled, including
  empty and all-unrankable sets;
- no Target/Outcome/Context/Model/Evidence/Qualification input or Candidate
  score meaning has leaked into V1;
- final Candidate writes are short, fenced, exactly revalidated, atomic, and
  covered by success/failure/concurrency/replay/recovery proof;
- funnel/dossier and representative plan/index verification pass;
- all focused, refoundation, full legacy/target, PostgreSQL, architecture,
  documentation, lint, type, build, and diff gates pass without weakened tests;
- WP-02 through WP-06 Verification files remain byte-identical;
- Remote CI is honestly reported as PASS or, if still disabled,
  `BLOCKED / NOT_RUN`.

Until that ledger exists, this record remains approved design only and
Candidate engineering status is not GO.
