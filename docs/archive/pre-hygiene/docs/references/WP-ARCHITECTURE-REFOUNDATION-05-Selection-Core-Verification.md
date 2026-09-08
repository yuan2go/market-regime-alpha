# WP-ARCHITECTURE-REFOUNDATION-05 Selection Core Verification

> **Status:** CURRENT_STATUS
> **Authority:** Exact-SHA local engineering verification record; not business, evidence, qualification, Runtime, trading, or Production Authority
> **Owner:** Market Regime Alpha maintainers
> **Executed At:** 2026-08-29
> **Source Checkpoint:** `44caf94aac86c51bb0e69968aadc4dc47ff84907`
> **Baseline:** `origin/main@b18a29b14fe654cfc83d47016e5b70ab59156e15`
> **Design Checkpoint:** `ef55f5fa08236c675953976f52c7178212a1fcda`
> **Market/PIT Source Checkpoint:** `e7a276a30f71a98b6b32580fa0a4840c2e269b9f`
> **Code Evidence:** isolated target Market/Selection/Foundation source and tests; unchanged legacy source and 001–106 migrations

This record proves only the target Selection Core draft slice. It does not
release the mutable baseline, cut over the canonical Runtime, implement
Candidate or a Research Definition owner, establish formal PIT or Provider
qualification, or prove Alpha, broker, trading, Prospective, or Production
capability.

## Dependency correction and namespace

The frozen physical order is:

```text
Market/PIT
-> Selection Core: Universe/Eligibility
-> minimal Research Definition substrate required by Candidate
-> Candidate closure
-> Research Evaluation/Evidence/Qualification
-> Decision/Outcome
```

The permanent package is `market_regime_alpha.selection`. It neither reuses nor
executes the legacy `market_regime_alpha.universe` package, and no `v2`, `next`,
`new_*`, compatibility, Registry, or future-stub namespace exists.

Candidate is `DEFERRED / NO-GO`. A future Candidate Set must exist independently
of Decision Run; a future Decision Run must carry a required FK to an already
existing Candidate Set. Candidate may depend only on the real immutable
Research-owned Dataset, Feature Definition, and Model/Model Version identities
an approved Candidate policy actually needs. Full Evidence, Assessment, and
Qualification are not required merely for Candidate existence; Qualification
will own purpose-scoped admission. None of those future identities or tables is
faked in this checkpoint.

## Verified draft catalog

```text
schema               mra
epoch                MRA_REFOUNDATION_1
release_state        DRAFT
baseline_version     1
baseline_checksum    3c8deeda6d7a90aef3a45b5de0c3a3fa44a952d74abec1a533402608806bac43
seed_checksum        9c41cd715e35e1a7bed3a58c52a29f01cc1e9bf950b77344bb56eac6dfa2df11
vocabulary_checksum  1e6bb4185c53930ea3981972b2f2d00a6b027bc193f03f210a7a63f060404392
catalog_checksum     2127574a622caaeac16b5bd905196d3542a0e90a5184ad40f047c1d34a677c05
tables               32
views                2
indexes              166
constraints          402
functions            23
triggers              74
```

Selection adds exactly these seven tables:

```text
universe
universe_revision
universe_member
eligibility_policy
eligibility_rule
eligibility_assessment
eligibility_reason
```

No Candidate, Research, Decision, future owner, or placeholder table was added.
Relative to WP-04, Selection contributes 7 tables, 40 indexes, 80 constraints,
and 7 append-only triggers. The triggers reuse the Foundation append-only
function; no Selection-specific function or trigger function was introduced.
The one catalog function increase splits Foundation Artifact integrity from the
Market consumer freshness predicate.

## Market physical modularization and Artifact seam

The large WP-04 files were physically split by cohesive responsibility while
keeping their stable exports:

- Market Domain: vocabulary, temporal values, reference identities, facts, and
  normalization;
- Market Application: registration, capture, normalization, results, and local
  support;
- Market Ports: provider, repository, query, and UoW contracts;
- PostgreSQL: public Market query/repository facades plus focused bar, fact,
  gap, mapping, reference, capture, normalization, SQL, and support modules.

No WP-04 schema, temporal Authority, PIT visibility, transaction, or Provider
semantics was redesigned. Market exports generic exact/as-of facts only. The
named `decision_reference_1455` Target interface/classifier is absent; the exact
same-session Raw five-minute correctness invariant remains covered, while a
formal resolver waits for its Research Target/Outcome owner.

`mra.artifact_has_verified_integrity` retains the Foundation integrity seam:
exact Artifact identity and verified physical hash/size/existence/integrity
remain mandatory. `mra.market_artifact_is_readable` composes that invariant with
the WP-04 24-hour Market consumer read cadence. A Selection scope configuration
requires Foundation integrity but does not inherit a single Market engineering
cadence. No general Policy Framework was added and Artifact integrity was not
weakened.

## Selection Authority and transaction seam

Universe freezes research scope from an explicit immutable specification bound
to exact scope Artifact id/hash/size, provider Product, Classification scheme/
code, and ordered instrument identities. It never defaults to all current
instruments. For one Decision Time, every scoped instrument receives
`INCLUDED`, `EXCLUDED`, or `UNKNOWN`; missing, stale, gap, or conflicting
Market/classification/lifecycle evidence is retained with a reason and exact
lineage. Current membership cannot backfill historical knowledge.

Eligibility owns current Candidate-population legality, not Universe scope and
not Candidate existence. Suspension, special-treatment status, listing age,
liquidity, and limit metadata are Eligibility rules. The immutable policy
declares each rule's measure, aggregation, window value/unit, value kind,
operator, threshold, and value unit. Listing age is `CALENDAR_DAYS`; liquidity
uses an explicit session window, currency unit, mean aggregation, operator, and
Decimal threshold supplied by policy. No hidden business default is supplied by
the application.

Every scoped member executes every policy rule without short circuit. Each
`eligibility_reason` stores the typed criterion result, typed observed value,
measure/aggregation/window, operator/threshold/unit, reason code, and exact
Market fact/bar/gap/session/Capture lineage arrays plus a lineage hash.
Aggregation is fixed:

```text
any FAIL                 -> INELIGIBLE
else any UNKNOWN         -> UNKNOWN
all PASS                 -> ELIGIBLE
```

Only explicit criterion failure is `FAIL`. Missing, stale, conflicting,
gapped, invisible, or unknown-status evidence is `UNKNOWN`. Universe membership
is not Eligibility; Eligibility is not Candidate; limit metadata is not
execution fillability.

The independent `PostgresSelectionUnitOfWork` exposes only Selection writes, a
narrow caller-transaction Market query port, command receipt, audit, and live
Runtime fence/finalization ports. It does not embed or expand the Runtime or
Market UoW. Business write, receipt, audit, matching live fence, and Step/
Attempt finalization commit in one short transaction. Repositories never
commit, and the UoW cannot be nested or reused.

## Runtime, PIT, concurrency, and query proof

The test-only Target Runtime completes:

```text
CAPTURE
-> NORMALIZE_PIT
-> FREEZE_UNIVERSE
-> ASSESS_ELIGIBILITY
```

All four Steps and Attempts finish `SUCCEEDED`. Each Selection business result,
receipt, audit event, live fence token, and matching Step finalization is atomic.
A stale fence rolls back the entire Selection command and creates no partial
Selection, receipt, or audit write.

Focused PostgreSQL tests prove:

- one three-instrument scope reconciles to one included, one excluded, and one
  unknown member; Eligibility reconciles to one eligible, one ineligible, and
  one unknown assessment;
- all five rules run for all three members, producing 15 queryable reason rows
  with exact lineage;
- an explicit empty scope produces complete zero counts rather than implicit
  market-wide discovery;
- identical concurrent idempotency keys produce one original commit and one
  exact replay;
- Decision-time mismatch and stale Runtime fence leave no business writes;
- historical membership selects the then-visible revision, not a later current
  correction;
- a 25-hour-old Market Artifact remains Foundation-integrity `AVAILABLE` but is
  stale for Market consumption, yielding typed Selection `UNKNOWN` results;
- unique/FK/check constraints independently reject count, aggregate, identity,
  rule-shape, typed-value, and lineage inconsistencies.

Representative `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` calls execute the
Selection paths and traverse these intended indexes:

```text
classification_membership_classification_idx
instrument_fact_current_asof_idx
market_bar_exact_asof_idx
universe_member_status_idx
eligibility_assessment_result_idx
```

Tests require the owner relations and indexes to execute, but do not freeze
planner costs, timings, or node shapes for tiny fixtures.

## Final validation ledger

Every Python gate ran through `uv run`.

| Check | Result | Evidence |
|---|---|---|
| frozen dependency/install sync | **PASS** | `uv sync --frozen --extra dev --extra postgres` |
| Selection focused tests | **PASS** | 19 tests covering Domain, architecture, DDL, PostgreSQL semantics, lineage, concurrency, idempotency, and plans |
| Market focused regression | **PASS** | all 69 behavior-preserved WP-04 tests |
| all target refoundation tests | **PASS** | 155 tests on the exact checkpoint content |
| complete repository test collection | **PASS** | all 3,195 nodes pass in five non-overlapping batches: 974 + 324 + 954 + 705 + 238 |
| legacy PostgreSQL and business regression | **PASS** | unchanged 001→106 bootstrap/schema plus application, compatibility, replay, and business suites |
| target clean DB bootstrap/verify | **PASS** | missing target schema fails closed; bootstrap creates 32 tables; exact epoch/checksums/catalog verify |
| target guarded recreate | **PASS** | exact database name/OID, owner, zero-other-connection plan/apply rebuilds and verifies the draft schema |
| Runtime/fence/concurrency/idempotency | **PASS** | four-Step slice, complete atomic finalization, replay, Decision-time, and stale-fence rollback pass |
| three-state/count/lineage/empty scope | **PASS** | all members and rules accounted; exact PIT lineage persists; zero scope reconciles |
| representative query plans and constraints | **PASS** | Market/PIT and Selection paths execute intended indexes; declarative invariants reject invalid state |
| architecture dependencies | **PASS** | Selection imports no legacy Universe, Market PostgreSQL Repository/UoW, State System, Candidate, legacy persistence, or compatibility path |
| documentation checks | **PASS** | inventory/link checker and its tests pass |
| platform tests | **PASS** | 33 tests |
| Ruff | **PASS** | all checks passed |
| mypy | **PASS** | no issues in 494 source files |
| package build | **PASS** | sdist and wheel include target Selection/Market code, SQL/seed resources, and `mra` entry point |
| diff/worktree checks | **PASS** | no whitespace errors; generated build output excluded; original worktree's pre-existing `.idea/modules.xml` change untouched |
| Remote CI | **BLOCKED / NOT_RUN** | GitHub Actions repository permission is `enabled=false`; no workflow was dispatched or observed |

The full repository batches ran on a repeatedly recreated dedicated PostgreSQL
16.14 database. The full 3,195-node pass preceded removal of pure formatter-only
churn; all affected Market tests and the complete 155-test refoundation suite
then passed again on exact checkpoint content. No assertion, fixture semantics,
skip/xfail marker, application behavior, or database invariant was relaxed.

## Investigated non-final attempts

| Attempt | Result | Root cause and disposition |
|---|---|---|
| first full-batch URL used `postgresql:///...` | **FAIL** | legacy `DatabaseSettings` correctly requires an explicit host; the dedicated database was rebuilt and all batches used `postgresql://localhost/...` |
| parallel platform/refoundation attempt shared one database | **FAIL** | target bootstrap correctly rejected live legacy temporary schemas; the database was rebuilt and the disjoint suites passed serially |
| first final catalog report selected nonexistent `epoch` column | **FAIL** | reporting query only; corrected registry query returned the exact epoch/checksums/catalog above, with no schema or test change |

## Exit boundary

Selection Core is `GO` for its local engineering exit gate and `NO-GO` for
canonical Runtime/CLI cutover, Candidate, formal PIT, qualified Provider use,
Alpha/OOS, broker, trading, or Production.

Candidate is not ready for formal implementation. Its real remaining
precondition is a minimal Research Definition substrate containing only the
immutable Dataset, Feature Definition, and Model/Model Version identities an
approved Candidate policy proves it needs, followed by an acyclic schema review.
No full Evidence/Assessment/Qualification implementation is required for
Candidate existence. WP-05 stops here.
