# WP-ARCHITECTURE-REFOUNDATION-06 Research Definition Core Verification

> **Status:** CURRENT_STATUS
> **Authority:** Exact-SHA local engineering verification record; not business, research evaluation, qualification, Candidate, Runtime cutover, trading, or Production Authority
> **Owner:** Market Regime Alpha maintainers
> **Executed At:** 2026-08-29
> **Source Checkpoint:** `22a5ec692fcc261182197c2953a0a860d7cd6f94`
> **Baseline:** `origin/main@7932fda7f41c44bc29f04672caaef75d6b9b2c69`
> **Design Checkpoint:** `355f628241c33949ac3da85c17066a2067d6c0bd`
> **Selection Core Merged Baseline:** `7932fda7f41c44bc29f04672caaef75d6b9b2c69`
> **Code Evidence:** isolated target Foundation/Market/Selection/Research source, target draft DDL, and `tests/refoundation`; unchanged legacy source and 001–106 migrations

This record proves only the target Research Definition Core draft and the
cross-context Runtime command-failure contract. It does not implement
Candidate, Model/ModelVersion, Target, Evaluation, Evidence, Assessment,
Qualification, Decision/Outcome, Execution/Account, or Runtime/CLI Cutover. It
does not release the mutable baseline or establish formal PIT, Provider,
Alpha/OOS, broker, trading, Prospective, or Production evidence.

## Documentation and dependency closure

The design checkpoint removed current-state claims that still described
Selection as unmerged, corrected the merged starting SHA and 32-table catalog,
removed duplicate or conflicting current Research/Candidate instructions, and
froze this acyclic order:

```text
Market/PIT
-> Selection Core: Universe/Eligibility
-> Research Definition Core: Dataset/DatasetSource/FeatureDefinition
-> Candidate closure
-> Research Evaluation/Evidence/Qualification
-> Decision/Outcome
```

WP-01 through WP-05 verification/evidence reports were retained unchanged as
historical exact-SHA records. Candidate Set remains independent of Decision
Run and Qualification; a future Decision Run must reference an already-existing
Candidate Set. No nullable future FK, string placeholder, future stub table,
generic Registry, or compatibility adapter was introduced.

## Shared deterministic command-failure contract

`RuntimeCommandFailureRecorder` is the one narrow cross-context Application
contract used by Market, Selection, and Research. Each bounded context still
classifies its own Domain errors and owns its own UoW. On deterministic failure:

```text
business UoW rolls back completely
-> fresh owner UoW
-> lock and validate live Runtime fence
-> failed command receipt
-> audit event
-> terminal Attempt/Step/Run failure
-> one commit
```

Stale fence rejection occurs before receipt or audit writes. An injected audit
failure rolls the failed receipt and Runtime failure back together, leaving the
Attempt live rather than waiting only for lease expiry. Exact successful
concurrency is replayed; idempotency conflict uses a separate attempt-scoped
rejection receipt and never takes over the original command identity. The
shared layer has no command dispatcher, Domain error registry, handler lookup,
CommandBus, Mediator, Workflow engine, Service Locator, or cross-context mega-
UoW.

## Permanent Research namespace and physical shape

The permanent bounded-context package is
`market_regime_alpha.research_qualification`, with explicit `domain`,
`application`, and `ports` boundaries. Its stable export facade delegates to
cohesive FeatureDefinition and Dataset command modules; Dataset validation and
cross-cutting command mechanics are physically separate. Importing the package
does not execute legacy `market_regime_alpha.research`, `features`, or
`candidates`, and the target package imports none of their persistence or
compatibility paths.

`PostgresResearchUnitOfWork` is independent and narrow: Research definitions,
Research Artifact metadata, exact Selection/Market source queries, receipt,
audit, and Runtime finalization only. Runtime, Market, and Selection UoWs were
not expanded. Repositories never commit. Dataset Artifact byte verify/read and
closed-schema parsing occur outside PostgreSQL; final identity/source binding,
Artifact verification record, Research writes, receipt, audit, live fence, and
success finalization use one short Research transaction.

## Research Definition Authority

`feature_definition` owns only immutable calculation semantics:

- semantic code/version/content identity;
- value type and unit;
- frequency, window, and lookback value/unit;
- closed source requirements;
- `DECISION_VISIBLE_AT_OR_BEFORE` availability;
- `EXPLICIT_STATUS` missingness;
- deterministic algorithm code/version/hash and exact code/config Artifact
  identities.

It contains no Alpha support, maturity, validation, Assessment, Qualification,
Model, or Feature-to-Feature dependency field.

`dataset` is permanently typed `DECISION_INPUT`. It binds one DecisionTime,
exact Universe revision, Eligibility policy, ordered Feature definitions,
manifest/code/config Artifact triples, immutable content identity, and
reconciled row/source/cell/status counts.

`dataset_source` has this closed role vocabulary:

```text
POPULATION
FEATURE_DEFINITION
MARKET_BAR_REVISION
MARKET_INSTRUMENT_FACT_REVISION
MARKET_TRADING_SESSION
MARKET_SOURCE_GAP
MARKET_CAPTURE
```

Every role uses a real owner FK. One role-shape CHECK permits exactly its legal
FK tuple and requires every unrelated identity to be null. Population rows use
composite FKs proving same Dataset scope/DecisionTime,
`UniverseMember = INCLUDED`, and `EligibilityAssessment = ELIGIBLE`. Partial
UNIQUE indexes prohibit duplicate per-Dataset role identities. No
`source_type + source_id`, generic JSON lineage, or nullable future identity
exists. After insertion, the repository reloads all source rows and compares
them exactly to the parsed manifest, so PostgreSQL and the Artifact cannot
diverge into two lineage truths.

## Exact population, PIT lineage, and leakage barrier

Within the final Research transaction, the source query locks and derives the
complete population as the same-DecisionTime intersection:

```text
UniverseMember = INCLUDED
AND EligibilityAssessment = ELIGIBLE
```

The manifest's population source tuples and ordered instrument rows must both
equal that set exactly. Empty intersections remain valid empty Datasets. Every
row contains every bound Feature exactly once. Feature absence is represented
by `MISSING`, `UNKNOWN`, `STALE`, or `CONFLICT` with null value, reason, and
source lineage; it cannot remove an instrument. `AVAILABLE` cells require a
typed value and exact Market fact lineage. Decimal values are canonical strings
parsed into bounded `Decimal`, while JSON floats and non-finite values are
rejected.

All Market source identities are resolved through real canonical FKs and must
have `decision_visible_at <= Dataset DecisionTime`, Foundation Artifact
integrity, and matching instrument ownership where applicable. Code/config/
manifest Artifacts bind exact id/hash/size, and bound Research Artifacts are
protected from Foundation orphan GC.

The Domain parser has a closed JSON schema and recursively rejects field names
containing `target`, `outcome`, `return`, `returns`, `mfe`, `mae`, `barrier`,
`future`, `realized`, `label`, or `posterior`. Negative tests cover nested
`target`, `outcome`, `forward_return`, MFE/MAE, barrier result, future
observation, realized label, and posterior value before any Dataset Authority
write. Decision-input and future Evaluation/Target data therefore cannot share
this parser or manifest schema.

## Verified draft catalog

```text
schema               mra
epoch                MRA_REFOUNDATION_1
release_state        DRAFT
cutover               NOT_CUT_OVER
baseline_version     1
baseline_checksum    103e0867dd767ef0ceb8ffb1c6b3a641f15cbf0d484b24b9a072d1e516be822e
seed_checksum        9c41cd715e35e1a7bed3a58c52a29f01cc1e9bf950b77344bb56eac6dfa2df11
vocabulary_checksum  2026845c5efc6aa17b181210b3629fda5851b4f84f857a81058d97aa0aed1058
catalog_checksum     a66324041156083caa2c04786712a43b6e886893bb6d1d2cb97d97815048c07a
tables               35
views                2
indexes              203
constraints          453
functions            23
triggers              77
```

Research Definition Core adds exactly:

```text
feature_definition
dataset
dataset_source
```

No Candidate, Model/ModelVersion, Target, Evaluation, Evidence, Assessment,
Qualification, Decision, or future placeholder table exists. The three new
append-only triggers reuse the Foundation mutation guard; no new function or
owner-specific trigger function was needed. Clean bootstrap creates the 35
tables; retry is verify-only. Guarded recreate bound exact database name/OID,
database/schema owner, zero other connections, plan hash/challenge, and
recreated the same catalog checksum.

Representative `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` paths execute:

```text
universe_member_status_idx
eligibility_assessment_result_idx
dataset_source_dataset_role_idx
one bounded dataset decision/scope index
```

DDL tests independently reject invalid counts, Artifact triples, immutable
identity conflicts, role/FK shapes, duplicate source identities, non-INCLUDED/
non-ELIGIBLE population, and append-only mutation.

## Validation ledger

Every Python command ran through `uv run`.

| Check | Result | Evidence |
|---|---|---|
| frozen dependency sync | **PASS** | `uv sync --frozen --extra dev --extra postgres` |
| Research focused tests | **PASS** | 46 collected tests; Domain, architecture, DDL, PostgreSQL, Artifact, PIT, concurrency, Runtime success/failure |
| Market focused regression | **PASS** | 69/69 |
| Selection focused regression | **PASS** | 21/21 |
| all target refoundation tests | **PASS** | 205/205 |
| complete repository collection | **PASS** | 3,245 nodes collected |
| complete repository regression | **PASS** | five disjoint fresh-DB batches: 1,298 + 291 + 29 + 684 + 943 = 3,245/3,245 |
| legacy PostgreSQL/business regression | **PASS** | unchanged 001–106 migration/schema plus all legacy application/business suites |
| target clean bootstrap/verify/recreate | **PASS** | PostgreSQL 16.14; 35 tables; exact checksums; name/OID/owner/zero-connection guarded plan/apply |
| failure/fence/idempotency/recovery | **PASS** | Market/Selection/Research success and deterministic failure; stale no-write; atomic rollback; replay/concurrency |
| Dataset population/PIT/leakage | **PASS** | exact and empty populations, explicit missing cells, exact visibility/lineage, parser negative cases |
| constraints/query plans/import boundaries | **PASS** | declarative rejection, required indexes, namespace isolation, no forbidden dependency |
| documentation checker/tests | **PASS** | canonical inventory, metadata, links, and 7 checker tests |
| platform tests | **PASS** | 33/33 within the complete regression |
| Ruff | **PASS** | all checks passed |
| mypy | **PASS** | no issues in 500 source files |
| package build | **PASS** | sdist and wheel contain Research package, DDL/seeds, and stable entry point |
| diff/worktree gate | **PASS** | no whitespace error; generated build outputs removed; original worktree `.idea/modules.xml` untouched |
| Remote CI | **BLOCKED / NOT_RUN** | GitHub Actions permission reports `enabled=false`; no workflow dispatched or observed |

## Investigated non-final attempts

| Attempt | Result | Root cause and disposition |
|---|---|---|
| first design docs check | **FAIL** | abbreviated Code Evidence paths violated the canonical inventory; replaced with resolvable repository paths |
| first fresh-worktree pytest command | **FAIL** | development dependencies were not installed in that worktree; frozen `uv sync` restored the exact environment |
| first Selection PostgreSQL integration command | **FAIL** | required explicit target DB URL was absent; created the dedicated PostgreSQL 16 database and used the explicit host URL thereafter |
| early Selection helper run | **FAIL** | test helper passed `ContentHash` where a serialized string was required; corrected without changing fixture meaning |
| intended command-failure RED test | **FAIL (TDD RED)** | deterministic failure left the Attempt `RUNNING`; implementation of the shared fresh-UoW failure contract made it terminal atomically |
| early Ruff/mypy focused gates | **FAIL** | unused test imports and three local inference ambiguities; removed imports and made local types explicit |
| early BOOLEAN parser test | **FAIL** | fixture lacked required Market lineage and failed earlier than the intended typed-value assertion; completed the valid lineage fixture, leaving the assertion strict |
| first DDL bootstrap verification | **FAIL** | seven leading FK indexes were absent; added the required indexes and reran clean bootstrap |
| intended Dataset registration RED test | **FAIL (TDD RED)** | `register_dataset` did not exist; implemented only after the failing semantic tests |
| first combined Research/Selection collection | **FAIL** | duplicate `test_architecture.py` basenames were imported as non-packages; added the Research test package marker |
| first Runtime success-path fixture | **FAIL** | it invented an unsupported future Step kind; used the existing `ASSESS_RESEARCH` vocabulary without changing Runtime |
| first query-plan assertion | **FAIL** | PostgreSQL validly chose another bounded Dataset FK/scope index; assertion now requires the owner relation and accepted bounded index set, not one planner shape |
| first complete refoundation run after implementation | **FAIL** | existing Selection fixture omitted the current-session liquidity bar, becoming time-of-day dependent after Shanghai close; completed the same canonical evidence fixture, preserving production PIT logic and strict expected counts |
| first schema evidence report | **FAIL** | reporting code requested nonexistent `SchemaVerification.cutover_state` after recreate had succeeded; rebuilt the disposable DB and reported only real fields plus the unchanged `NOT_CUT_OVER` boundary |
| first post-documentation script-test rerun | **FAIL** | invocation omitted the mandatory explicit PostgreSQL test URL; no test body ran, and all 12 affected script/documentation tests passed on a fresh DB with `postgresql://localhost/...` |
| generated build cleanup with `rm -rf` | **BLOCKED** | tool safety rejected the command; removed the two exact generated files with `unlink` and the empty directory with `rmdir` |

No test was skipped, xfailed, deleted, weakened, or made less strict. No fixture
business meaning was changed; the Selection fix completed evidence that the
fixture already claimed to provide across pre/post-close wall-clock execution.

## Candidate V1 dependency closure and exit gate

Candidate V1 may now bind only these already-real immutable owners:

1. `universe_member` with `membership_status = INCLUDED`;
2. same-DecisionTime `eligibility_assessment` with `result = ELIGIBLE`;
3. one immutable `dataset` whose rows exactly reconcile that intersection;
4. the Dataset's real `feature_definition` identities and source lineage;
5. Candidate-owned policy/config/code Artifact identities to be introduced by
   the Candidate work package itself.

Candidate Set existence remains independent of Decision Run, Evaluation,
Evidence, Assessment, and Qualification. Model/ModelVersion is not in the V1
closure because no approved Candidate policy requires a fitted model. A future
Decision Run must require an already-existing Candidate Set. The physical
Authority direction above is acyclic.

Research Definition Core is **GO** for its local engineering exit gate and
**NO-GO** for canonical Runtime/CLI cutover or any evidence ceiling listed
above. Candidate capability remains unimplemented, but **Candidate Closure is
formally GO to begin as the next separately bounded work package**. WP-06 stops
before Candidate code.
