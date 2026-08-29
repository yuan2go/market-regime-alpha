# WP-ARCHITECTURE-REFOUNDATION-07 Candidate Closure Implementation Plan

> **Status:** CURRENT_STATUS
> **Plan State:** EXECUTION_PLAN
> **Schema Epoch:** `MRA_REFOUNDATION_1`
> **Release State:** `DRAFT`
> **Cutover State:** `NOT_CUT_OVER`
> **Starting Main:** `origin/main@d45fe83730a75dfa6083db9b6c929b37838fdd50`
> **Approved Design Checkpoint:** `0a6560ccb27b0f8f058e647ecc19063815da5002`
> **Authority:** Execution sequence for the approved Candidate Closure design;
> not Model, Target/Evaluation/Evidence/Qualification, Decision/Outcome,
> Execution, Runtime Cutover, or Production Authority

This plan implements the approved Candidate Closure design test-first. Each
behavioral task starts with a focused failing test, records the expected
failure, implements only enough production behavior to make that test pass,
then runs the adjacent regression gates. Historical WP-02 through WP-06
Verification documents remain byte-unchanged.

## Fixed implementation boundaries

- Candidate remains in `market_regime_alpha.selection`.
- `CandidateApplication` and `CandidateUnitOfWork` are independent from the
  Selection Core and Research Definition UoWs.
- Selection owns the narrow Research-input DTO/port. Only PostgreSQL
  Infrastructure may translate Research Dataset/FeatureDefinition objects.
- There are exactly five Candidate Authority tables and no future owner
  placeholders.
- Policy registration writes only policy/component rows. CandidateSet build
  writes only set/candidate/score-component rows.
- Dataset Artifact verification/read/parse and all ranking computation happen
  outside the final PostgreSQL write transaction.
- The semantic request fingerprint excludes Runtime Attempt/Step/fence
  identities. Those are receipt/finalization metadata.
- Exact `Fraction` arithmetic is semantic Authority. Decimal values are a
  versioned, injective PostgreSQL `numeric` projection.
- No DatasetSource UUID array, GIN lineage index, direct source-link table, or
  sixth Candidate Authority table is introduced.
- No Candidate business trigger/function is added. The existing generic
  append-only mutation guard is reused; cross-row completeness is checked by
  final-transaction reconciliation.

## Task 1: Freeze architecture and public seams with RED tests

**Tests first**

- Modify `tests/refoundation/selection/test_architecture.py` to require:
  - Candidate modules are owned by Selection;
  - Selection source does not import `research_qualification`;
  - Research source still does not import Selection;
  - Candidate has a separate UoW/application and does not widen Selection Core
    or Research UoW;
  - only the five approved Candidate tables are permitted;
  - no Model, Target, Evaluation, Evidence, Qualification, Decision, Outcome,
    Execution, compatibility, registry, or CommandBus names appear in the new
    Candidate surface.
- Add/modify `tests/refoundation/selection/test_candidate_api.py` to import the
  intended Selection-owned domain, application, UoW, Research-input, artifact,
  and query contracts.
- Modify `tests/refoundation/test_schema_specification.py` and
  `tests/refoundation/selection/test_schema_specification.py` to expect exactly
  the five new Candidate tables in the target inventory.
- Modify the Research schema/architecture specifications only enough to permit
  those exact Selection-owned tables while preserving exactly three Research
  owner tables.

**RED command**

```bash
uv run pytest -q \
  tests/refoundation/selection/test_architecture.py \
  tests/refoundation/selection/test_candidate_api.py \
  tests/refoundation/selection/test_schema_specification.py \
  tests/refoundation/research_qualification/test_architecture.py \
  tests/refoundation/research_qualification/test_schema_specification.py \
  tests/refoundation/test_schema_specification.py
```

Expected RED: missing Candidate modules/contracts and missing five-table target
inventory, not weakened architecture assertions.

**Implementation**

- Add narrow modules under:
  - `src/market_regime_alpha/selection/domain/candidate.py`
  - `src/market_regime_alpha/selection/domain/candidate_ranking.py`
  - `src/market_regime_alpha/selection/application/candidates.py`
  - `src/market_regime_alpha/selection/ports/candidate_repository.py`
  - `src/market_regime_alpha/selection/ports/candidate_uow.py`
  - `src/market_regime_alpha/selection/ports/research_inputs.py`
  - `src/market_regime_alpha/selection/ports/candidate_artifacts.py`
  - `src/market_regime_alpha/selection/ports/candidate_queries.py`
- Export only the intended stable names from the local `__init__.py` files.
- Extend `EXPECTED_SELECTION_TABLES` by exactly the approved relations and
  retain exact total target inventory checks.

**GREEN command:** repeat the RED command.

## Task 2: Implement Candidate domain math with exact TDD

**Tests first**

Add `tests/refoundation/selection/test_candidate_domain.py` with independent
examples and property-style permutations proving:

- positive declared Decimal weights normalize as exact rational values;
- ambient Decimal context cannot change results;
- arithmetic midrank supports higher/lower directions and raw ties;
- a nonconstant median may naturally equal `.5` while its component status is
  `AVAILABLE`;
- singleton and constant components receive the special `.5` assignment and
  status `CONSTANT`;
- `MISSING / UNKNOWN / STALE / CONFLICT` never receive `.5` and make the whole
  row `UNRANKABLE` under `STRICT_COMPLETE_CASE`;
- one unavailable required component removes the row from every component's
  rankable denominator; no partial percentile is emitted;
- non-required Dataset features do not affect rankability;
- empty population and zero-rankable population are `NOT_ESTIMABLE`;
- mixed constant/variable components retain fixed exact normalized weights and
  produce Set status `AVAILABLE`;
- all components constant produce score `.5`, competition rank `1`, and all
  boundary ties selected;
- variable component contributions may cancel to an all-composite tie without
  changing the Set status from `AVAILABLE`;
- competition rank is `1,1,3`, never identity-broken;
- the K-th observation defines the boundary and
  `INCLUDE_ALL_BOUNDARY_TIES` may select more than K;
- identity renaming, row permutation, and component declaration iteration order
  do not change percentile/score/rank/disposition;
- Decimal projection preserves exact equality and strict ordering, increases
  precision when required, and fails deterministically at the configured cap;
- the complete Candidate x Component result matrix and all funnel counts
  reconcile.

**RED command**

```bash
uv run pytest -q tests/refoundation/selection/test_candidate_domain.py
```

Expected RED: missing Candidate ranking kernel/domain results.

**Implementation**

- Define the closed vocabularies and immutable dataclasses for policy,
  components, Research-input rows/cells, CandidateSet, Candidate, score rows,
  component diagnostics, and build result.
- Accept only `DECIMAL` and `INTEGER` FeatureDefinitions in V1.
- Convert declared `Decimal` weights and raw numerics to `Fraction` before any
  normalization/ranking work.
- Compute the common complete-case cross-section, direction-aware arithmetic
  midranks, fixed-weight contributions, exact composite scores, competition
  ranks, and inclusive boundary using exact rational arithmetic.
- Project exact normalized weights, percentiles, contributions, scores, and
  boundary score with the frozen `ROUND_HALF_EVEN` projection contract. Store
  the chosen precision on CandidateSet. Never derive stored score by summing
  already-rounded stored contributions.
- Derive stable IDs/fingerprints using canonical semantic content. Identity may
  order serialized output only after all semantic calculations are complete.
- Hash each cell/source lineage canonically; do not retain source ID arrays as
  Candidate lineage Authority.

**GREEN command:** repeat the RED command, then run the existing Selection
domain suite.

## Task 3: Add the five-table PostgreSQL schema with declarative constraints

**Tests first**

Extend `tests/refoundation/selection/test_schema_specification.py` and add
Candidate schema cases in
`tests/refoundation/selection/test_candidate_postgres.py` to prove:

- clean bootstrap owns exactly the five new tables;
- all numeric score/weight columns are PostgreSQL `numeric`, without float
  types or lossy fixed scale;
- policy components bind only exact real FeatureDefinition identity/hash/type
  and contain `declared_weight`, not `normalized_weight` or Dataset/Model keys;
- CandidateSet binds the real Dataset and Policy exact identities;
- Candidate binds its Dataset population source;
- score rows enforce typed raw-value shape, closed status values, projected
  normalized weight, percentile/contribution nullability, Feature identity,
  and lineage hash;
- `UNIQUE(candidate_set_id, instrument_id)` and
  `UNIQUE(candidate_id, candidate_policy_component_id)` exist;
- no unique CandidateSet/rank constraint exists and equal ranks can be inserted;
- declarative funnel, state, boundary, and count checks reject malformed rows;
- all five relations are append-only using the established generic guard;
- no Candidate-specific trigger function, source array, GIN index, sixth table,
  or prohibited future FK exists;
- Runtime step vocabulary contains `REGISTER_DATASET` and
  `BUILD_CANDIDATE_SET` and no longer contains `BUILD_CANDIDATES`.

**RED command**

```bash
uv run pytest -q \
  tests/refoundation/selection/test_schema_specification.py \
  tests/refoundation/selection/test_candidate_postgres.py -k schema
```

Expected RED: absent relations/constraints and stale Runtime step vocabulary.

**Implementation**

- Edit `src/market_regime_alpha/infrastructure/postgres/migrations/001_baseline.sql`.
- Add only supporting composite unique constraints needed as FK targets on:
  - exact FeatureDefinition identity/hash/type;
  - exact Dataset identity/hash/scope/row count;
  - DatasetSource identity/Dataset/instrument;
  - the existing Dataset Feature-source business key where required.
- Create the five Candidate relations, composite foreign keys, closed checks,
  non-unique rank/funnel indexes, dossier/component lookup indexes, and generic
  append-only triggers.
- Replace `BUILD_CANDIDATES` with the exact target step kinds required by the
  vertical slice. Do not create an alias or fallback.
- Update `schema.py` inventories and exported constants.

**GREEN command:** repeat the RED command and run the complete schema
specification collection.

## Task 4: Implement policy registration and its independent final transaction

**Tests first**

Add unit/fake-UoW and PostgreSQL cases for `RegisterCandidatePolicy` proving:

- semantic validation rejects empty components, nonpositive weights, duplicate
  ordinals/codes/features, unsupported Feature types, and noncanonical content;
- code/config Artifact binding and every real FeatureDefinition are checked;
- Policy has no Dataset binding;
- Artifact verification can occur before the final write transaction;
- final transaction order is live fence, receipt/replay, exact artifact and
  Feature dependency locks/revalidation, policy/component writes,
  reconciliation, verification receipt, audit, Attempt/Step finalization,
  commit;
- semantic replay uses the same result and does not duplicate rows;
- same idempotency key with changed semantic input conflicts;
- concurrent identical registration converges to one Policy;
- stale fence writes no success/failure receipt or Candidate row;
- deterministic failures use the shared failure contract and remain atomic.

**RED command**

```bash
uv run pytest -q \
  tests/refoundation/selection/test_candidate_application.py -k policy \
  tests/refoundation/selection/test_candidate_postgres.py -k policy
```

**Implementation**

- Implement Selection-owned command/result types and semantic request hash.
- Add `CandidateArtifactRepository` contract and PostgreSQL adapter reusing the
  generic Artifact repository without importing Research bindings into
  Selection.
- Implement `CandidateRepository` policy methods and exact reconciliation.
- Implement independent `PostgresCandidateUnitOfWork`; never add Candidate
  repositories to Selection Core or Research UoWs.
- Wire `RuntimeCommandFailureRecorder` with Candidate's narrow UoW provider.

**GREEN command:** repeat the RED command.

## Task 5: Implement the Research-input adapter and CandidateSet build flow

**Tests first**

Add adapter/application/PostgreSQL tests proving:

- Selection source imports no Research package; Infrastructure performs the
  only Research Dataset/FeatureDefinition translation;
- loader verifies/reads/parses the immutable Dataset manifest outside any
  PostgreSQL write transaction;
- loader preserves every Dataset row and every required typed cell while
  exposing only a deterministic lineage hash;
- label/future-field leakage and malformed manifests fail deterministically;
- build never calls Universe, Eligibility, Market hard-gate, Context, Target,
  Outcome, Model, Evidence, Qualification, or Entry services;
- final build transaction order is live fence, receipt/replay, exact Policy,
  Dataset, FeatureDefinition, Artifact, DatasetSource dependency
  revalidation, three owner writes, exact reconciliation, verification
  receipt, audit, Attempt/Step finalization, commit;
- a dependency changed after external computation causes a stale dependency
  failure and no Candidate writes;
- every Dataset row produces one Candidate and every Candidate x Component
  produces one immutable score row;
- empty Dataset commits a valid empty `NOT_ESTIMABLE` CandidateSet;
- all four non-available statuses produce `UNRANKABLE` records with null
  score/rank and no percentile/contribution imputation;
- singleton/mixed/all-constant/cancelled-composite/boundary-tie scenarios match
  the exact domain semantics;
- concurrent identical builds, idempotent replay, recovery after interrupted
  attempts, deterministic failure atomicity, and stale fences obey the shared
  contracts.

**RED command**

```bash
uv run pytest -q \
  tests/refoundation/selection/test_candidate_application.py -k build \
  tests/refoundation/selection/test_candidate_research_input.py \
  tests/refoundation/selection/test_candidate_postgres.py -k build
```

**Implementation**

- Implement the Selection-owned `CandidateResearchInputLoader` and
  final-transaction `CandidateResearchDependencyQueries` contracts.
- Add PostgreSQL Infrastructure adapters that may import both Selection DTOs
  and Research manifest/parser/domain code.
- Perform preflight replay/fence, then Artifact I/O/parse/ranking outside the
  write transaction.
- In the final short Candidate transaction, lock/revalidate the exact prepared
  dependency fingerprint before writing `candidate_set`, `candidate`, and
  `candidate_score_component` rows in bulk.
- Reconcile actual population, disposition, rankability, complete score matrix,
  component statuses, boundary diagnostics, and content hash before success.
- Record deterministic failures through the established shared contract;
  propagate stale fences without writing a failure receipt.

**GREEN command:** repeat the RED command and the full Candidate focused suite.

## Task 6: Add Candidate funnel, dossier, and representative plans

**Tests first**

Add query cases proving:

- funnel returns Dataset/Policy/Set identities, requested K, declared and actual
  population/rankable/unrankable/selected/ranked-not-selected/component-matrix
  counts, component status counts, boundary diagnostics, and explicit
  reconciliation booleans;
- component diagnostics derive `observed_count`, `distinct_count`, literal
  missing/unknown/stale/conflict counts, available-but-not-observed count, and
  `AVAILABLE / CONSTANT / NOT_ESTIMABLE` from immutable score rows, including
  empty Sets;
- dossier traces through `CandidateSet.dataset_id` to Dataset manifest and
  relational DatasetSource lineage and explains raw typed value/status,
  Feature identity, percentile, projected normalized weight, contribution,
  component diagnostics, score/rank/disposition, and boundary reason;
- no query treats Candidate score as probability, return, MFE/MAE, or Entry;
- representative `EXPLAIN (FORMAT JSON)` cases use an acceptable owner index
  with sequential scans disabled, without asserting planner cost, timing, row
  estimates, or a fixed node shape.

**RED command**

```bash
uv run pytest -q \
  tests/refoundation/selection/test_candidate_queries.py \
  tests/refoundation/selection/test_candidate_postgres.py -k 'funnel or dossier or plan'
```

**Implementation**

- Add replaceable `candidate_funnel` and component-diagnostic views to the
  baseline schema; views are not Authority tables.
- Implement the read-only Candidate query port and PostgreSQL query provider in
  `src/market_regime_alpha/infrastructure/postgres/queries/candidate.py`.
- Expose the provider at the composition root without adding a generic registry.

**GREEN command:** repeat the RED command.

## Task 7: Prove the test-only Target vertical slice

**Tests first**

Add an integration fixture and test-only driver that executes exactly:

```text
CAPTURE
-> NORMALIZE_PIT
-> FREEZE_UNIVERSE
-> ASSESS_ELIGIBILITY
-> REGISTER_DATASET
-> BUILD_CANDIDATE_SET
```

The tests must prove:

- each step consumes the preceding frozen Authority rather than reconstructing
  it or using a compatibility path;
- Runtime Attempt/Step/fence metadata is not part of the semantic Candidate
  request hash;
- success finalizes receipt/audit/Attempt/Step atomically;
- stale fence, concurrent identical commands, replay after a new attempt,
  deterministic failure, and injected pre-commit failure leave no partial
  Candidate Authority;
- exact replay reports the same CandidateSet identity/fingerprint and zero
  Candidate/score mismatches.

**RED command**

```bash
uv run pytest -q tests/refoundation/test_candidate_vertical_slice.py
```

**Implementation**

- Add only test-support composition needed to invoke existing Target
  applications plus the new Candidate application.
- Extend `bootstrap.py` with an independent `candidates` application and
  Candidate query provider. Do not create a production Runtime dispatcher or
  cut over any legacy flow.

**GREEN command:** repeat the RED command, then run Market/Selection/Research
focused PostgreSQL regressions.

## Task 8: PostgreSQL lifecycle and recovery verification

Run against fresh isolated PostgreSQL databases and preserve exact outputs:

```bash
uv run pytest -q tests/refoundation/selection
uv run pytest -q tests/refoundation/test_candidate_vertical_slice.py
uv run pytest -q tests/refoundation/market
uv run pytest -q tests/refoundation/research_qualification
uv run pytest -q tests/refoundation -n auto
uv run python scripts/refoundation_postgres.py clean-bootstrap
uv run python scripts/refoundation_postgres.py verify
uv run python scripts/refoundation_postgres.py recreate
```

If repository scripts use different established subcommands, record the actual
commands rather than inventing aliases. Validate migration idempotency,
clean-bootstrap checksums, concurrent/recovery cases, append-only behavior,
and representative plans. Resource contention may be handled with separate
databases and non-overlapping shards, but the complete collection must run.

## Task 9: Reconcile current docs and create WP-07 verification

**Tests first**

- Update docs-contract tests to require Candidate implementation status,
  five-table inventory/checksum, dependency seam, ranking/missing/tie semantics,
  funnel counts, Runtime vertical-slice scope, validation evidence, and the
  bounded next-stage dependency review.
- Recompute WP-02 through WP-06 hashes and assert byte identity with the
  pre-implementation values.

**Implementation**

- Update only current architecture, Current State, Capability Matrix, Gap
  Register, Roadmap, Authority Map, and the approved WP-07 design status needed
  to describe implemented Candidate Closure.
- Add
  `docs/references/WP-ARCHITECTURE-REFOUNDATION-07-Candidate-Closure-Verification.md`
  with exact SHA/command/database/schema/checksum/plan/failure evidence.
- Roadmap stops at “post-Candidate dependency review.” It does not choose or
  authorize Research Evaluation, Decision/Outcome, or any later implementation.
- Record real code facts needed to review the dependency graph across
  TargetDefinition, TargetCheckpoint, ResearchPartition, Experiment, Model,
  DecisionRun, Outcome, Evaluation, Evidence, and Qualification, especially any
  competing realized-label construction.

**Docs command**

```bash
uv run python scripts/check_docs_links.py
uv run pytest -q tests/scripts/test_check_docs_links.py
uv run pytest -q tests/architecture
```

## Task 10: Complete regression, static, build, diff, and independent review

Run every Python gate through `uv run`:

```bash
uv sync --frozen --extra dev --extra postgres
uv run pytest -q tests/refoundation/selection
uv run pytest -q tests/refoundation/market
uv run pytest -q tests/refoundation/research_qualification
uv run pytest -q tests/refoundation
uv run pytest -q
uv run python scripts/check_docs_links.py
uv run pytest -q tests/scripts/test_check_docs_links.py
uv run pytest -q tests/platform
uv run python -m ruff check .
uv run python -m mypy
uv run python -m build
git diff --check
```

- Run the repository's architecture dependency and PostgreSQL
  bootstrap/verify/recreate gates discovered from current scripts/tests.
- Never skip/xfail/delete tests or weaken invariants. Root-cause every
  non-final failure and record it in WP-07 Verification.
- Keep remote CI as `BLOCKED_BY_REPOSITORY_CONFIGURATION / NOT_RUN` if Actions
  remain disabled; do not claim CI evidence.
- Run an independent Standards and Spec review against the approved design SHA;
  fix findings test-first and rerun affected/full gates.
- Before each checkpoint commit, inspect staged/unstaged scope, run
  `git diff --check`, verify `.idea/modules.xml` is untouched, and record the
  exact commit SHA. Do not push, merge, or cut over Runtime.

## Checkpoint sequence

1. Design checkpoint: `0a6560ccb27b0f8f058e647ecc19063815da5002`.
2. Implementation-plan checkpoint: this file only.
3. Candidate domain/API checkpoint after Tasks 1-2 pass.
4. Candidate schema/persistence checkpoint after Tasks 3-4 pass.
5. Candidate build/query/vertical-slice checkpoint after Tasks 5-7 pass.
6. Verification/docs checkpoint after Tasks 8-10 pass.
7. Final reviewed SHA after any review corrections and the full regression rerun.

Each checkpoint is dependency-coherent and does not rewrite the historical
WP-02 through WP-06 Verification record.
