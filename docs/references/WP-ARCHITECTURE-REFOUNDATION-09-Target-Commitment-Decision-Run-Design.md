# WP-ARCHITECTURE-REFOUNDATION-09 Target Commitment and Decision Run Design

> **Status:** CANONICAL_TARGET_ARCHITECTURE
> **Design State:** `APPROVED_WITH_CONDITIONS`
> **Implementation State:** `AUTHORIZED / NOT_YET_VERIFIED`
> **Runtime/CLI Cutover:** `NO_GO`
> **Schema Epoch:** `MRA_REFOUNDATION_1`
> **Release State:** `DRAFT / NOT_CUT_OVER`
> **Owner:** Market Regime Alpha maintainers
> **Approved At:** 2026-08-30
> **Execution Baseline:** `origin/main@03eeb8cdba2f412fc6536a38c4234b12c8552efe`
> **Execution Branch:** `agent/wp-09-target-commitment-decision-run-authority`
> **Authority:** Approved implementation contract for WP-09 only; not Outcome,
> Context, Evaluation, Qualification, Prospective, Production, Legacy deletion,
> or Runtime/CLI Cutover authority

This record freezes the final WP-09 architecture before business code and DDL.
It refines, but does not reverse, the approved WP-08 post-Candidate dependency
direction. Code, PostgreSQL, tests, and the future immutable WP-09 Verification
remain the only implementation evidence.

## 1. Execution-time audit and cleanup basis

The execution-time fetch resolved `origin/main` to
`03eeb8cdba2f412fc6536a38c4234b12c8552efe`. The original checkout was on
`agent/wp-portfolio-execution-authority-01@10689a4` and had the unrelated local
change `.idea/modules.xml`; WP-09 therefore uses the isolated worktree
`/Users/yuan/projects/market-regime-alpha-worktrees/wp-09-target-commitment-decision-run-authority`.
The original checkout is not modified.

The code/schema audit established these implementation facts:

- the target draft has 40 tables and stops at the five-table Candidate
  Authority; no WP-09 or later target table/package exists;
- Candidate Set is immutable, content-addressed, complete over its Dataset, and
  stores `SELECTED`, `RANKED_NOT_SELECTED`, and `UNRANKABLE`; its
  `content_sha256` is its current immutable version fact;
- the Runtime has real Run/Step/Attempt leases and a row-locked fence, but its
  vocabulary currently jumps from `BUILD_CANDIDATE_SET` to `ASSESS_CONTEXT`
  and its generic DAG validator does not prevent that bypass;
- Market/PIT owns exact `market_bar_revision` and typed `source_gap` facts with
  capture, Provider Product, instrument, session, event, revision,
  `recorded_at`, `known_at`, and Decision visibility;
- no formal Market reference finality owner exists, so WP-09 can truthfully
  freeze only `UNKNOWN` finality;
- the existing `market_regime_alpha.decision` package is a Legacy/current Trade
  Decision implementation with old persistence dependencies. WP-09 neither
  imports, edits, renames, nor reuses it;
- the unreleased baseline policy requires extending `001_baseline.sql`; it does
  not permit a compatibility schema, dual write, or a new migration epoch;
- the current local databases are not an acceptable target proof database.
  WP-09 verification must provision a new disposable PostgreSQL 16 database.

The independent cleanup checkpoint removes only stale active-looking WP-07
handoff language. Immutable WP-03 through WP-07 Verification records remain
unchanged.

## 2. WP-08 116-relation reconciliation

The WP-08 catalog contains `target_definition`, `target_checkpoint`, and
`target_metric_definition`, and states that metric dependencies are
relational. Its detailed table list and concrete FK map do not contain a
`target_metric_dependency` relation. Encoding an ordered many-to-many metric
observation dependency in JSON or repeating checkpoint columns on the metric
would contradict the frozen relational rule.

WP-09 therefore makes an explicit **relational normalization correction**:

```text
WP-08 frozen destination relations        116
+ target_metric_dependency                  1
WP-09 corrected destination relations     117
```

The Remaining Research & Qualification area changes from 28 to 29 relations.
The other catalog areas do not change. WP-09 physically implements eight
relations, taking the mutable target draft from 40 to 48 tables. The corrected
117-relation destination is semantic inventory, not a quota; the remaining 69
design-only relations are not created as placeholders.

## 3. Bounded contexts and dependency direction

Target Definition is permanently owned by Research & Qualification.
Decision Run is permanently owned by Decision Support in a new package:

```text
market_regime_alpha.research_qualification
  domain/target_*.py
  application/target_definitions.py
  ports/target_*.py

market_regime_alpha.decision_support
  domain/
  application/
  ports/

market_regime_alpha.infrastructure.postgres
  target_uow.py
  decision_support_uow.py
  repositories/target_definitions.py
  repositories/decision_runs.py
  queries/decision_inputs.py
```

The owning context declares every port. Infrastructure implements adapters.
Decision Support consumes immutable Candidate, Target, Market reference, and
Runtime facts through narrow typed ports. It never imports Selection, Research,
Market, or Runtime PostgreSQL repositories. Domain imports no Infrastructure.
The existing `decision` and all `legacy` packages are prohibited dependencies.
`bootstrap.py` is the sole multi-context composition root.

`ResearchQualificationApplication.register_target_definition(...)` is a stable
facade only. Target registration has its own `TargetDefinitionCommands`,
`TargetDefinitionRepository`, and `TargetUnitOfWorkProvider`; the existing
Research Definition UoW is not expanded into a Research-lifecycle God UoW.

## 4. Target Definition Authority

### 4.1 Relational model

WP-09 adds four Research-owned relations:

| Relation | Immutable authority |
|---|---|
| `target_definition` | stable code/version, immutable registration status, provider-neutral observation semantics, exact algorithm/code/config identity, counts/hashes, append-only supersession and registration provenance |
| `target_checkpoint` | stable checkpoint identity and contiguous ordinal; reference/outcome role, session horizon, local timing, timeframe, price basis, value field, availability/finality rule and checkpoint hash |
| `target_metric_definition` | stable metric identity/ordinal/kind/value/unit/completion/barrier semantics plus exact algorithm/code/config identity and metric hash |
| `target_metric_dependency` | ordered typed edge from one metric to one checkpoint in the same Target Definition, with role and dependency hash |

All four are append-only. Ordinary `UPDATE` and `DELETE` fail. A semantic
change creates a new Target Definition version. `supersedes_target_definition_id`
must bind the immediately preceding version of the same `target_code`, and a
partial unique index permits only one direct successor. The old root and every
old child remain unchanged. Immutable `registration_status = 'REGISTERED'`
records lifecycle state; it is not an active/current flag.

A valid definition has:

- a non-empty provider-neutral Target code and positive version;
- one `DECISION_REFERENCE` checkpoint and at least one
  `OUTCOME_OBSERVATION` checkpoint;
- unique contiguous checkpoint, metric, and dependency ordinals;
- one or more metrics and one or more dependencies;
- every metric dependency pointing to a checkpoint in the same Target;
- typed horizon/timing, reference rule, price basis, instrument/market scope,
  availability, finality, value, completion, algorithm, code, and config
  semantics;
- canonical checkpoint, metric, dependency, and definition SHA-256 values;
- exact immutable code/config Artifact identity, hash, and size;
- immutable actor/source/request/creation provenance.

No Target business field is JSON, free text, an unvalidated string reference,
or a caller-supplied authoritative hash.

### 4.2 Provider neutrality

Target Definition specifies what must be observed: instrument/market scope,
session offset, local checkpoint time, timeframe, price basis, value field,
availability rule, finality rule, and metric dependency. It does not bind a
Provider or Provider Product. Provider selection is a Decision-time input and
the exact `market_bar_revision` or `source_gap` freezes the actual Provider
Product and Capture provenance.

`OpenDecisionRunRequest` contains an ordered tuple of
`RequestedDecisionTarget(target_definition_id, reference_provider_product_id)`.
The Provider Product is therefore explicit, hashed, and auditable for that Run
without becoming permanent Target semantics. A caller cannot provide a bar ID,
gap ID, price, status, revision, or fallback. The Decision-owned Market input
adapter validates the selected Product and resolves the exact as-of fact.

### 4.3 Target-owned closure

Command receipt status is not Target closure authority. Target children have
deferred FKs to `target_definition`. Registration inserts checkpoints, metrics,
and dependencies first, then inserts the root last. Child `BEFORE INSERT`
guards reject additions once the root exists. The root closure trigger locks
and validates the complete relational child graph, contiguous order, exact
counts, same-Target composite keys, roster hashes, and canonical definition
hash before accepting the root. Deferred FKs prevent committed orphans. A
rollback leaves no child, root, or receipt.

The receipt supplies only exact idempotency, audit, optional Runtime evidence,
and result lookup. This closure remains valid if receipts are projected or
archived independently.

### 4.4 Registration command

`RegisterTargetDefinition` computes its request and definition hashes from the
typed request. It ignores any caller hash. In one short transaction it:

1. locks a participating live Runtime fence first;
2. takes a transaction advisory lock for Target code/version;
3. locks the optional superseded Target and distinct Artifacts in stable UUID
   order;
4. validates Artifact hashes and complete semantics;
5. inserts children, the closing root, receipt, audit, and optional Runtime
   finalization;
6. commits once.

An exact request retry returns the original Target and receipt without new
business rows, verification rows, or audit. Reusing the idempotency identity
with another request hash fails closed. Concurrent identical registration has
one writer; a conflicting code/version, content hash, or supersession loses
deterministically. A deterministic failure rolls back and uses a fresh narrow
Target UoW to record failure only while the Runtime fence is still live. A
stale fence writes nothing.

## 5. Decision Run Authority

WP-09 adds four Decision Support relations:

| Relation | Immutable authority |
|---|---|
| `decision_run` | one closed Decision-time envelope for one Candidate Set, with request/Runtime/time/provenance and roster/count/hash summary |
| `decision_run_target` | non-empty ordered Target version roster plus explicit Decision-time reference Provider Product selection |
| `decision_target_commitment` | complete Candidate × Target binding, including every Candidate disposition and exact Decision/runtime/recorded facts |
| `decision_reference_observation` | mandatory 1:1 exact bar revision or Source Gap with independent value/availability/finality state |

`decision_run(candidate_set_id)` is unique. One Candidate Set can create only
one canonical Decision Run. The exact logical retry returns that Run. A new
idempotency identity, changed Target order/version/source Product, changed code
or config identity, or any other changed request for the Candidate Set fails
closed. Later Target/Protocol comparison belongs to Experiment/Evaluation and
cannot create a second canonical Decision Run.

The `decision_run` root freezes:

- Decision Run ID and immutable `OPENED` status;
- Candidate Set ID and `content_sha256` version fact;
- Dataset, Candidate Policy, Candidate count/disposition counts and canonical
  Candidate roster hash;
- positive Target count and ordered Target roster hash;
- commitment/reference counts and commitment roster hash;
- Runtime mode and DecisionTime loaded from the exact Runtime Run;
- PostgreSQL `clock_timestamp()` commitment time shared by root, commitments,
  and references;
- request-received time, request identity/hash, code/config and actor
  provenance;
- exact Runtime Run, Step, Attempt, and fence identity;
- canonical result/definition summary hash.

The Candidate roster is loaded from the closed Candidate Set without reranking,
filtering, sorting by a new criterion, or deriving a new disposition. Canonical
serialization orders Candidate rows by persisted identity solely for hashing.
All three dispositions are included.

An empty Candidate Set creates the immutable Run and non-empty Target roster,
with zero commitments and zero references. An empty Target roster always fails
before business writes.

### 5.1 Relational closure and composite keys

Decision children are inserted before the root through deferred FKs; the root
is inserted last and closes the aggregate. Child guards prohibit additions once
the root exists. The root closure trigger verifies:

- one ordered Target row per requested Target, with no duplicate Target or
  position;
- every Candidate in the Candidate Set appears once for every Target;
- no extra Candidate, Target, commitment, or reference row;
- one reference per commitment and one commitment per reference;
- exact counts and SQL-recomputed canonical roster hashes;
- Candidate disposition, instrument, Candidate Set, Target version, Provider
  Product, DecisionTime, Runtime mode, and recorded time agreement;
- exact Runtime Run/Step/Attempt/fence ownership.

Composite FKs close these paths:

```text
commitment
  → (candidate, candidate_set, instrument, disposition)
  → (decision_run_target, decision_run, target_definition, provider_product)
  → (decision_run, candidate_set, decision_time, runtime_mode, recorded_at)

reference
  → (commitment, decision_run, candidate_set, candidate, target, instrument)
  → exact Target DECISION_REFERENCE checkpoint
  → exactly one market_bar_revision or source_gap
  → matching Provider Product/Capture/Instrument/Session/timeframe/price basis
```

Every WP-09 relation has FK-supporting indexes, replay/reconciliation indexes,
unique business keys, closed-vocabulary checks, temporal checks, and append-only
guards. PostgreSQL core `sha256(bytea)` is used for relational closure hashes;
no extension or JSON owner is introduced.

## 6. Decision reference semantics

The Decision input adapter resolves the requested Target reference checkpoint
for each Candidate instrument and explicitly selected Provider Product. It may
return only:

1. the unique latest revision of the exact bar identity visible at
   DecisionTime; or
2. the exact typed Source Gap for the same Provider Product, instrument,
   session, timeframe, price basis, and event window that is visible at
   DecisionTime.

The adapter never performs an unbounded latest/current lookup, substitutes a
Provider, uses a prior-session/daily/last-available bar, invents a gap, or
accepts a caller value. If neither an exact bar nor an exact persisted gap
exists, opening fails deterministically so Market can first record the missing
fact. If an exact gap is the later Decision-visible fact, it remains the
reference even if a Provider repair is recorded later.

Every observation freezes source and Capture identity, instrument/session,
event start/end, observation time, `known_at`, revision identity, selected value
field/value, reason, and immutable creation provenance. PostgreSQL enforces
`known_at <= decision_time`.

The state axes are independent:

| Source | Value status | Availability status | Finality status |
|---|---|---|---|
| exact valid bar revision | `PRESENT` | `AVAILABLE` | `UNKNOWN` |
| missing/placeholder gap | `UNAVAILABLE` | `UNAVAILABLE` | `UNKNOWN` |
| Provider failure/conflict/invalid gap | `FAILED` | `FAILED` | `UNKNOWN` |

WP-09 does not admit `PROVISIONAL` or `FINAL` Decision references because no
implemented Market owner can prove those states. A future qualified finality
owner may add new semantics forward; it cannot mutate a historical WP-09
reference.

## 7. Time and Prospective ceiling

DecisionTime and Runtime mode come from the locked Runtime Run. The Candidate
Set/Dataset DecisionTime must match. `request_received_at` records command-entry
provenance. PostgreSQL supplies the one authoritative
`commitment_recorded_at` after all final locks and revalidation.

Commitment-before-Outcome is a relational fact, not a Prospective conclusion.
`HISTORICAL`, `REPLAY`, `SHADOW`, `OPERATIONAL`, and even a named
`PROSPECTIVE` Runtime mode are stored without promotion. WP-09 implements no
campaign, OOS, Qualification, Production eligibility, or Alpha proof.

## 8. Preparation, transaction, lock, retry, and recovery

Artifact byte reads and deterministic reference preparation occur before the
write transaction. Prepared inputs carry exact IDs, versions, hashes, event
windows, `known_at`, and source state. The final short transaction revalidates
every prepared identity and snapshot; any drift fails closed.

The final lock order is:

```text
live Runtime Run/Step/Attempt fence
→ Decision command/CandidateSet identity advisory lock
→ immutable Artifact, Target, Provider Product, session, bar/gap rows in
  (kind, UUID) order
→ CandidateSet and Candidates in UUID order
→ Decision children and closing root
→ receipt, audit, Attempt/Step finalization
→ commit
```

There is no Provider, network, filesystem, broker, or Artifact-byte I/O inside
the transaction; no nested transaction; and no reverse acquisition of Runtime
locks.

Only PostgreSQL `40001` serialization failures and `40P01` deadlocks receive a
fixed bounded maximum of three whole-transaction attempts over the same frozen
prepared input and deterministic identities. Other errors are not silently
retried. A lost connection with unknown commit outcome raises an explicit
unknown-outcome error; repeating the exact command/request identity first probes
the canonical receipt/root and returns the committed Run if present.

For a deterministic failure:

1. the business transaction rolls back;
2. a fresh Decision UoW locks and revalidates the live fence;
3. it atomically writes one failed receipt/audit and finalizes Attempt/Step;
4. no Decision business row exists.

If fence ownership is stale at either phase, there are zero business writes and
zero failure writes. If failure recording itself fails, the error propagates;
the system never reports a durable failure receipt that was not committed.

## 9. Idempotency and concurrency

The semantic OpenDecisionRun request hash includes Candidate Set identity/hash,
the ordered Target Definition/version/hash and Decision-time Provider Product
roster, Runtime Run DecisionTime/mode, code/config identity, and command
provenance. Attempt/fence identity is execution provenance, not a way to change
the logical request.

Exact replay returns the same Run, Target rows, commitments, references,
counts/hashes, receipt, audit, and original Runtime execution identity. It does
not resolve Market again. A reused idempotency identity with a different hash
fails `IDEMPOTENCY_KEY_REUSED`. A different request for an already committed
Candidate Set fails `CANDIDATE_SET_ALREADY_COMMITTED`.

The Candidate Set advisory lock plus unique `decision_run(candidate_set_id)`
provides one canonical writer. Concurrent identical commands either observe
the original receipt/result or lose a uniqueness race and exact-reload it.
Concurrent conflicts cannot create a partial or second roster.

## 10. Replay and reconciliation

`DecisionRunQueryProvider.load(decision_run_id)` returns an immutable typed
snapshot. `DecisionRunVerifier.replay(decision_run_id)` reconstructs the
canonical summary only from exact WP-09 rows and their concrete immutable FKs.
`DecisionRunVerifier.reconcile(decision_run_id)` additionally runs relational
missing/extra/cross-product/count checks. Neither interface receives or calls a
Provider/Market resolver, performs a current/latest lookup, or writes Authority.

Mismatch kinds are closed and typed:

```text
IDENTITY_MISMATCH
MISSING_ROW
EXTRA_ROW
ORDER_MISMATCH
COUNT_MISMATCH
HASH_MISMATCH
REFERENCE_STATE_MISMATCH
RUNTIME_IDENTITY_MISMATCH
IMMUTABLE_FACT_MUTATION
```

A valid Run returns `matched = true` and `mismatch_count = 0` for both replay
and reconciliation. Historical Target versions and the original exact
bar/gap reference remain independently reconstructible after supersession or
Provider repair.

## 11. Mandatory Runtime DAG

The target vocabulary adds `OPEN_DECISION_RUN`. The target DAG must contain
direct required-success edges and increasing ordinals:

```text
BUILD_CANDIDATE_SET
  → OPEN_DECISION_RUN
  → ASSESS_CONTEXT
```

If any of these stage kinds appears, all three must appear exactly once in the
canonical target plan. No direct or transitive Build-to-Context bypass is
valid, and no Legacy/old-test exception exists. The test-only vertical slice
uses real claims, Candidate/Target/Decision Authorities, PostgreSQL writes,
receipt/audit/failure behavior, and leaves `ASSESS_CONTEXT` as the next READY
logical Step. It does not implement Context or alter the production Runtime or
CLI composition.

## 12. Test-first implementation plan

The approved public seams under test are:

- `ResearchQualificationApplication.register_target_definition(...)` backed by
  the independent Target command/repository/UoW seam;
- `DecisionSupportApplication.open_decision_run(...)`;
- `DecisionRunQueryProvider.load(...)`;
- `DecisionRunVerifier.replay(...)` and `.reconcile(...)`;
- `RuntimeApplication.schedule_run(...)` and real claim/finalization behavior;
- clean PostgreSQL bootstrap/verify/recreate/catalog interfaces.

Implementation proceeds in vertical red/green slices:

1. add architecture/schema/API tests that fail on the absent packages,
   eight-table inventory, corrected 117-relation catalog, and missing mandatory
   DAG edge;
2. add Target typed domain validation/hash tests, then the four relations,
   independent ports/UoW, registration command, exact replay, rollback,
   concurrency, supersession, and root-owned closure tests;
3. add Decision typed request/reference/canonical-hash tests, then the four
   relations and composite FK/closure/immutability tests;
4. add exact bar/gap resolution and OpenDecisionRun application slices,
   including empty Candidate Set, all dispositions, one-Run-per-Set,
   idempotency, conflict, stale fence, failure, retry, unknown-outcome replay,
   and concurrency;
5. add typed load/replay/reconciliation slices and deliberate missing, extra,
   order, count, hash, reference, Runtime, and mutation mismatch tests;
6. add the real test-only Candidate → OpenDecisionRun vertical slice and prove
   `ASSESS_CONTEXT` is next;
7. update baseline checksum/catalog/bootstrap/verify/recreate and validate
   representative indexed plans;
8. run the exact-SHA disposable-PostgreSQL and repository Exit Gate, then write
   the immutable WP-09 Verification and current status only from executed
   evidence.

Every production behavior begins with a failing public-seam test. PostgreSQL
integration tests use a real disposable database; mocks are limited to genuine
external byte/Provider boundaries and never replace Authority tests.

## 13. Explicit non-scope and stop boundary

WP-09 creates no Outcome, Context, Partition, Experiment, Evaluation, Evidence,
Assessment, Qualification, Model, Calibration, Signal, Forecast, Opportunity,
Thesis, Portfolio, Risk, Execution, Fill, Position, TradeOutcome, Attribution,
future FK, generic registry, compatibility facade, Legacy dependency, dual
write, future-stage package/table, or campaign.

Until the complete WP-09 Exit Gate passes:

```text
WP-10 Market Target Outcome   BLOCKED
Runtime/CLI Cutover           NO_GO
Prospective                   NO_GO
Formal OOS                    NO_GO
Production Qualification     NO_GO
Legacy deletion              NO_GO
```

After the gate passes, Market Target Outcome is only the next independently
authorized work package. WP-09 stops and does not start it.
