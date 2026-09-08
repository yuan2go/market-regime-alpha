# WP-ARCHITECTURE-REFOUNDATION-10 Market Target Outcome Design

> **Status:** CANONICAL_TARGET_ARCHITECTURE
> **Design State:** `APPROVED`
> **Implementation State:** `IMPLEMENTED / EXIT_GATE_PASS`
> **Runtime/CLI Cutover:** `NO_GO`
> **Schema Epoch:** `MRA_REFOUNDATION_1`
> **Release State:** `DRAFT / NOT_CUT_OVER`
> **Owner:** Market Regime Alpha maintainers
> **Frozen At:** 2026-08-31
> **Execution Baseline:** `origin/main@a5e1c1b1cac9563582ad71abfbad7ecbe53075c2`
> **Execution Branch:** `agent/wp-10-market-target-outcome-authority`
> **Execution Worktree:** `/Users/yuan/projects/market-regime-alpha-worktrees/wp-10-market-target-outcome-authority`
> **Implementation Checkpoint:** `56812c58ce7b6e601366ffd0a5cfb52fec573227`
> **Implementation Evidence:** [WP-10 Market Target Outcome Verification](WP-ARCHITECTURE-REFOUNDATION-10-Market-Target-Outcome-Verification.md)
> **Authority:** Approved implementation contract for WP-10 only; not
> Partition, Experiment, Evaluation, Evidence, Qualification, Model, Context,
> Decision Support expansion, Execution, Prospective, Production, Legacy
> deletion, or Runtime/CLI Cutover authority

This record freezes WP-10 before business code and DDL. It implements, without
reversing, the WP-08 Outcome lifecycle and consumes the exact WP-09 commitment,
Target version, and Decision reference. Code, PostgreSQL, tests, and the future
immutable WP-10 Verification remain the only implementation evidence.

## 1. Execution-time audit and cleanup basis

The required fetch resolved execution-time `origin/main` to
`a5e1c1b1cac9563582ad71abfbad7ecbe53075c2`, the merge of WP-09. The original
checkout was on `agent/wp-portfolio-execution-authority-01` with an unrelated
`.idea/modules.xml` modification, so it remains untouched. WP-10 uses the clean
branch and worktree recorded above.

The audit established these executable facts:

- the unreleased target baseline has 48 tables and four views, including the
  complete WP-09 Target and Decision authorities and no Outcome table;
- the clean disposable PostgreSQL 16.14 bootstrap/verify reports 328 indexes,
  609 constraints, 39 functions, and 100 non-internal triggers;
- one `decision_target_commitment` has one immutable
  `decision_reference_observation`, whose source is exactly a
  `market_bar_revision` or `source_gap` and whose `known_at` is bounded by
  DecisionTime;
- Target Definition is provider-neutral. `decision_run_target` freezes the
  Product used for the committed reference; WP-10 reuses that Product for the
  same committed Target's Outcome observations and never binds a Provider to
  the Target Definition itself;
- Target checkpoints declare exact session offset, local bar end, timeframe,
  price basis, value field, availability rule, and finality rule. Target metrics
  declare kind, required/optional completion, algorithm/code/config identities,
  and ordered `REFERENCE`, `OBSERVATION`, or `PATH_MEMBER` dependencies;
- Market/PIT owns append-only Product, Capture, Session, bar revision,
  corporate-action revision, and SourceGap facts. Exact bounded as-of queries
  exist; unrestricted current/latest lookup is not permitted;
- Runtime already has a `SETTLE_OUTCOME` vocabulary value and a real
  Run/Step/Attempt fence. There is no target Outcome application, repository,
  UoW, read port, replay verifier, or production dispatch;
- Legacy contains several return/MFE/MAE/barrier writers. Their common factual
  semantics are Decimal checkpoint return, path extrema, first passage, and
  same-bar barrier-order ambiguity. They remain characterization oracles only
  and are not imported by the new package.

The pre-design cleanup is commit `3056313`: it marks the WP-08 exit block as a
historical handoff now completed by immutable WP-09 evidence. It does not alter
WP-08 design facts or any Verification.

No audited fact changes the WP-08 bounded-context ownership, dependency
direction, Outcome lifecycle, or WP-10 scope.

## 2. Bounded context and dependency direction

WP-10 creates the permanent `market_regime_alpha.outcome` bounded context with
`domain`, `application`, and `ports`. Infrastructure adapters remain under the
existing PostgreSQL infrastructure package.

```text
Decision Support read port ─┐
Research Target read port ──┼→ Outcome application → Outcome-owned ports
Market/PIT exact read port ─┘                         ↑
Runtime claim/fence contract ─────────────────────────┘

PostgreSQL adapters implement those ports; no owner package imports an adapter.
```

- Domain imports only shared value/hash/time primitives.
- Application imports Outcome domain/ports and the Runtime command contract.
- Infrastructure may read exact relational parents through Outcome-owned typed
  adapters but does not import another owner's repository implementation.
- Runtime orchestrates and fences; it does not own Outcome facts.
- Research/Evaluation will later consume only the Outcome read port. WP-10 adds
  no consumer, Partition, Experiment, or Evaluation object.
- Legacy, `daily_decision`, current research label writers, Provider clients,
  filesystem artifacts, and generic repositories are forbidden imports.

## 3. Relational normalization correction

The WP-08 semantic catalog contains 117 relations and seven Outcome relations.
Its single `market_target_outcome_metric_observation` relation correctly binds
same-revision Outcome observations but cannot also bind `REFERENCE` to the
WP-09 `decision_reference_observation` without a polymorphic/XOR dependency.

WP-10 therefore makes the approved normalization explicit:

| Before | WP-10 concrete form |
|---|---|
| `REFERENCE`, `OBSERVATION`, and `PATH_MEMBER` described through one metric-observation concept | `market_target_outcome_metric_reference` accepts only `REFERENCE` and concrete-FKs the frozen WP-09 Decision reference |
| same concept | `market_target_outcome_metric_observation` accepts only `OBSERVATION`/`PATH_MEMBER` and concrete-FKs a same-revision Outcome observation |

The logical catalog becomes 118 relations. This is one real normalization
relation, not a table-count target or future placeholder. The eight WP-10
relations are:

1. `market_target_outcome`;
2. `market_target_outcome_revision`;
3. `market_target_outcome_source`;
4. `market_target_outcome_observation`;
5. `market_target_outcome_metric`;
6. `market_target_outcome_metric_reference`;
7. `market_target_outcome_metric_observation`;
8. `market_target_outcome_reason`.

## 4. Aggregate and revision lifecycle

`MarketTargetOutcome` is a stable root for exactly one
`DecisionTargetCommitment`. The root also composite-FKs that commitment's exact
Target, instrument, DecisionRun, and `DecisionReferenceObservation`. A unique
commitment key enforces one root; there is no generic subject or nullable future
binding.

The root is created only with revision one. Every settlement is a full immutable
`MarketTargetOutcomeRevision` snapshot. Revision identity includes:

- stable root and positive contiguous ordinal;
- optional immediate predecessor from the same root;
- `observation_cutoff` and `knowledge_cutoff`;
- independent aggregate value/completeness, availability, and finality states;
- exact source, observation, metric, reference-dependency,
  observation-dependency, and reason counts/hashes;
- Target/version/hash and frozen Decision-reference identity/hash;
- Target-level and per-metric algorithm/code/config identities;
- request identity/hash, PostgreSQL authoritative `settled_at`, request time,
  actor provenance, and exact Runtime Run/Step/Attempt/fence;
- canonical definition/result summary hashes and successful receipt.

The database locks the stable root before appending. Revision one has no
predecessor. Revision `n > 1` must name the current leaf at ordinal `n - 1`.
Unique `(outcome_id, ordinal)`, unique `(outcome_id, request_hash)`, and unique
non-null predecessor plus a root-locked predecessor trigger prevent forks and
guarantee at most one direct successor and one leaf. No mutable `current_id`
pointer is needed. Root, revisions, and every child reject UPDATE/DELETE.

## 5. Due assessment and zero-write boundary

Due assessment is a typed read over the exact commitment, Target version, and
calendar sessions visible by `knowledge_cutoff`. It resolves every declared
Outcome checkpoint; no checkpoint or optional metric is materialized before its
window exists.

If any declared Outcome checkpoint ends after `observation_cutoff`, the command
returns `NOT_DUE`. The command performs zero writes: no Outcome/root/revision,
receipt, audit, failure receipt, or Runtime finalization. A Runtime claim created
by an external caller is not mutated by this result. A missing calendar fact
that prevents a due decision is a typed preparation failure, not a fabricated
NOT_DUE or unavailable Outcome.

Once all declared checkpoints are due, each must resolve to one exact Market bar
revision or one exact pre-existing SourceGap. The Outcome command never creates
a SourceGap. Neither fact available means `OUTCOME_SOURCE_NOT_MATERIALIZED` and
business rollback; an exact SourceGap permits an auditable UNAVAILABLE/FAILED
settlement.

## 6. Two cutoffs and exact source roster

The request freezes two distinct UTC instants:

```text
source event_end <= observation_cutoff
source known_at  <= knowledge_cutoff
```

DecisionTime applies only to the already-frozen WP-09 reference. Settlement
time is neither cutoff and is never substituted for DecisionTime.

The preparation adapter performs only bounded exact-as-of reads:

1. load the commitment, exact Decision reference, and exact Target version;
2. use the Product frozen by its `decision_run_target`;
3. resolve each session offset through exact `trading_session` facts visible at
   the knowledge cutoff;
4. resolve the exact checkpoint interval/timeframe/price basis/instrument to one
   visible bar revision or exact SourceGap;
5. return an immutable typed roster for pure calculation.

`market_target_outcome_source` freezes the complete kernel input roster. Its
closed concrete shapes are `TRADING_SESSION`, `BAR_REVISION`, and `SOURCE_GAP`.
Each row copies and composite-FKs the exact Product, Capture, instrument,
session, event interval, revision/gap state, recorded time, and known time
required by that shape. Session rows similarly bind their source Capture and
Product. CHECKs enforce one shape only; there is no `(kind,id)`, JSON array, or
Artifact manifest lineage.

Current Target semantics select an already-declared `price_basis`; the kernel
does not silently adjust prices. No current Target dependency kind consumes a
corporate-action revision, so WP-10 does not create an unused corporate-action
source shape. A future Target semantic that truly consumes such facts must add
that concrete behavior in its own authorized Target/Outcome revision, not via a
nullable placeholder now.

Preparation occurs outside the write transaction and performs no Provider,
network, filesystem, broker, or Artifact-byte I/O. Inside the transaction the
adapter locks and revalidates every exact identity/hash/time boundary before any
Outcome write.

## 7. Observation, metric, dependency, and reason closure

One `market_target_outcome_observation` exists for every declared
`OUTCOME_OBSERVATION` checkpoint in a due revision. It binds the exact Target
checkpoint and exactly one same-revision BAR_REVISION or SOURCE_GAP source.
Bar observations retain open/high/low/close plus the checkpoint-selected value,
event interval, observation time, known time, value/completeness,
availability, and finality. Gap observations retain null values and the exact
typed gap state. Missing is never zero.

One `market_target_outcome_metric` exists for every exact
`TargetMetricDefinition`. It retains kind, value type, unit, completion rule,
algorithm binding, Decimal or boolean value, optional first-passage time, and
independent value/completeness, availability, and finality states.

Every Target dependency is represented exactly once:

- `market_target_outcome_metric_reference` composite-FKs the Outcome metric,
  exact Target `REFERENCE` dependency, and the root's frozen
  `decision_reference_observation`;
- `market_target_outcome_metric_observation` composite-FKs the Outcome metric,
  exact Target `OBSERVATION` or `PATH_MEMBER` dependency, and the matching
  same-revision Outcome observation/checkpoint.

Closure triggers compare those concrete rows to the Target dependency roster;
missing, extra, wrong-role, wrong-checkpoint, cross-revision, or recomputed
reference bindings fail the transaction.

`market_target_outcome_reason` is a typed, ordered child. Its dimension is
`REVISION`, `OBSERVATION`, `METRIC`, or `SOURCE`; shape constraints bind the
specific same-revision child where applicable. Reason codes explain every
PARTIAL, UNAVAILABLE, or FAILED dimension and may record barrier ambiguity.

## 8. Independent state semantics

Persisted aggregate outcome status is exactly `PARTIAL`, `COMPLETE`,
`UNAVAILABLE`, or `FAILED`; `NOT_DUE` is not persisted. Observation/metric value
status uses the same four factual states. Availability is independently
`AVAILABLE`, `UNAVAILABLE`, or `FAILED`. Until a formal Market finality owner
exists, every new Outcome finality is honestly `UNKNOWN`; data presence never
means FINAL.

- exact missing/placeholder SourceGap produces UNAVAILABLE observation state;
- Provider failure, conflict, or invalid OHLC SourceGap produces FAILED;
- a required failed metric makes the aggregate FAILED;
- all required metrics COMPLETE makes the aggregate COMPLETE even if an
  optional metric is unavailable;
- otherwise a mixture of usable and unavailable facts is PARTIAL;
- all required metrics unavailable with none complete/failed is UNAVAILABLE;
- a value is null for UNAVAILABLE/FAILED and never receives a zero fallback.

Database CHECKs enforce state/value shapes. The root-last revision closure
recomputes actual child counts/hashes and state roll-up before accepting the
revision row.

## 9. Single pure numerical kernel

`calculate_market_target_outcome(...) -> OutcomeRevisionDraft` is the only new
bars-to-realized-fact writer. It accepts frozen typed commitment/reference,
Target, exact source/session rosters, and the two cutoffs. It has no database,
Provider, filesystem, clock, environment, mutable global, or current/latest
access.

Financial arithmetic uses `Decimal`, precision 38, round-half-even, and a
canonical scale of 18 for ratios. The closed algorithms are selected by
`TargetMetricKind` while the exact registered algorithm/code/config identities
remain part of the result:

- `OBSERVATION_VALUE`: the Target checkpoint's selected OHLC field;
- `SIMPLE_RETURN`: `observation / frozen_reference - 1`;
- `MAX_FAVORABLE_EXCURSION`: `max(0, max(path.high/reference - 1))`;
- `MAX_ADVERSE_EXCURSION`: `min(0, min(path.low/reference - 1))`;
- `BARRIER_HIT`: exact first passage using high for UP and low for DOWN.

MFE/MAE deliberately include the zero excursion at Decision reference. This is
the standard semantics already present in the strategy path oracle; older
Legacy writers that allowed all-negative MFE or all-positive MAE are recorded
as non-canonical divergences, not retained as a second writer. Return and first
passage receive exact characterization parity tests.

If opposite barriers first pass in the same source bar, both hit values and the
shared first-passage time remain factual, while affected barrier metric state
is PARTIAL and `INTRABAR_ORDERING_NOT_OBSERVABLE` is recorded. MFE/MAE may still
be COMPLETE. An unavailable/failed frozen Decision reference propagates to
every `REFERENCE`-dependent metric without querying another price.

## 10. Settlement command and transaction

The public command is:

```text
OutcomeApplication.settle_market_target_outcome(
    SettleMarketTargetOutcomeRequest,
    CommandContext,
    runtime_claim=AttemptClaim,
) -> SettleMarketTargetOutcomeResult | OutcomeNotDue
```

The request names one commitment, the two cutoffs, and an optional exact
expected predecessor for correction. It never accepts a reference value, Market
revision identity, calculated metric, caller hash, Provider fallback, or
unrestricted source query.

Lock order is fixed:

```text
live Runtime Run/Step/Attempt fence
→ exact immutable Artifact/Target/Market revisions and Sessions
→ CandidateSet/Candidate
→ DecisionRun/Commitment/DecisionReference
→ stable MarketTargetOutcome root
```

No Runtime lock is acquired after another owner lock. The short transaction:

1. locks the live `SETTLE_OUTCOME` claim;
2. revalidates and locks the prepared immutable dependencies in global order;
3. locks or creates the one commitment root and verifies expected leaf;
4. starts the exact receipt;
5. obtains PostgreSQL authoritative `settled_at`;
6. inserts full source/observation/metric/dependency/reason children;
7. inserts the revision root last so deferred closure validates all rosters;
8. reconciles counts/hashes/chain/state;
9. succeeds one receipt, one audit, and the matching Runtime Attempt/Step;
10. commits once.

There is no Provider, network, filesystem, Artifact-byte I/O, nested
transaction, or sleep inside it.

## 11. Idempotency, correction, concurrency, and recovery

The canonical request hash covers commitment/Target/reference identities and
hashes, both cutoffs, exact source/session roster, algorithm/code/config
identities, actor/reason, Runtime Run identity, and expected predecessor. It is
computed from owner-loaded facts; callers cannot submit it.

- Same commitment, idempotency identity, semantic request, and Runtime Run is
  exact replay of the original revision, receipt, roster, and reference.
- Same idempotency identity with any changed semantic field fails closed.
- A changed cutoff/source roster/algorithm is a correction only when it uses a
  new idempotency identity and names the exact current leaf as predecessor.
- A changed request without that contract is a deterministic conflict.
- The stable root row serializes concurrent appenders. Identical writers yield
  one writer plus exact replay. Competing corrections from the same leaf yield
  one successor; the loser observes a stale predecessor conflict. No fork is
  possible.

Only SQLSTATE `40001` and `40P01` receive at most three bounded
whole-transaction attempts with the same prepared facts and identities. An
unknown commit result is resolved by exact receipt/revision replay; there is no
blind second write.

Deterministic failure rolls back the business transaction, opens a fresh narrow
Outcome UoW, locks the still-live fence first, and atomically records failed
receipt, audit, and Attempt/Step failure. It contains no uncommitted Outcome
facts. If the fence is stale, both business and failure writes are zero. If
failure recording itself fails, that exception is exposed and no success is
claimed. Recovery reissues the exact command and uses receipt/revision replay.

## 12. Replay, reconciliation, and read-only port

`OutcomeVerifier` and its PostgreSQL provider are read-only. They reconstruct:

- root/commitment/reference/Target identities and hashes;
- linear revision ordinal/predecessor/unique leaf;
- both cutoffs and exact source/session roster;
- observation, metric, concrete reference and observation dependencies;
- reasons, counts, hashes, state roll-up, algorithm/code/config identities;
- request/receipt/audit and exact Runtime identity/times.

Typed mismatches distinguish missing row, extra row, identity, order, count,
hash, predecessor/leaf, cutoff, reference, source state, metric value,
dependency, reason, Runtime, receipt, and immutable-fact mutation. Passing is
only `matched=true` and `mismatch_count=0`. Replay performs no Provider call,
latest lookup, source replacement, Decision-reference recomputation, or write.

The permanent narrow `OutcomeReadPort` returns immutable `OutcomeSnapshot`,
`OutcomeRevisionSnapshot`, `OutcomeObservationSnapshot`,
`OutcomeMetricSnapshot`, and `OutcomeReasonSnapshot`. Reads are by exact root or
revision identity; a current-leaf convenience read is explicitly Outcome-owned
and never an as-of Market query. The port exposes no session, repository,
Provider, Market reader, calculator, or mutation method.

## 13. PostgreSQL enforcement and query plans

The unreleased `001_baseline.sql` is extended in place. No `002+`, compatibility
schema, dual write, or placeholder table is created. PostgreSQL owns every
reliably expressible invariant through:

- primary, natural unique, concrete and composite foreign keys;
- one-root-per-commitment and exact root/reference closure;
- revision ordinal/predecessor/no-self/one-successor/one-leaf guards;
- child same-root/same-revision/same-Target/checkpoint/dependency FKs;
- concrete source shape and two-cutoff CHECKs;
- value/availability/finality/value-column shape CHECKs;
- request identity/hash and receipt/Runtime claim FKs;
- root-last counts/hash/dependency/state reconciliation;
- append-only and open-child/revision-closure triggers;
- leading indexes for every FK plus root leaf, idempotency, source replay,
  checkpoint, metric, dependency, reason, and read-port plans.

Catalog/checksum verification, bootstrap, verify, guarded exact-OID recreate,
and representative `EXPLAIN (ANALYZE, BUFFERS)` evidence change with the DDL.

## 14. Test-first implementation plan

Every public seam begins with a failing test. Test doubles are limited to typed
owner ports for domain/application behavior; PostgreSQL Authority, constraints,
transactions, concurrency, recovery, and replay use a fresh real database.

1. Add `tests/refoundation/outcome/test_outcome_domain.py` and
   `test_outcome_kernel.py` for immutable identities, all state dimensions,
   exact frozen-reference reuse, return/MFE/MAE/barrier/path dependencies,
   required/optional roll-up, gaps, and intrabar ambiguity. Implement
   `outcome/domain/{vocabulary,model,kernel,verification}.py`.
2. Add `test_outcome_api.py` and `test_architecture.py` for the permanent
   package, public command/read/verifier seams, narrow ports, dependency
   direction, and Legacy/Provider/latest/mutation absence. Implement
   `outcome/application`, `outcome/ports`, and exports.
3. Add `test_outcome_schema_specification.py` before extending
   `infrastructure/postgres/migrations/001_baseline.sql`, `schema.py`, expected
   catalog/vocabulary/checksums, append-only/closure triggers, and indexes.
4. Add `test_outcome_postgres.py` for exact source preparation, two cutoffs,
   NOT_DUE zero writes, due states, FK/CHECK/UNIQUE/immutability enforcement,
   exact retry, changed request, corrections, concurrent same/correction,
   rollback, stale fence, failure recording, unknown commit, recovery, and
   representative plans. Implement the narrow Outcome UoW, repositories, and
   query adapters.
5. Add `test_outcome_replay.py` for zero-mismatch replay and every typed
   mismatch without Provider/latest/write access. Implement query/read and
   verification adapters.
6. Add `test_outcome_runtime.py` for a real `SETTLE_OUTCOME` claim, exact
   Run/Step/Attempt identity, success/failure finalization, stale fence zero
   writes, and test-only composition wiring. Update `bootstrap.py`; do not add a
   production dispatcher or CLI cutover.
7. Add Legacy characterization tests for the intentionally preserved return,
   extrema, first-passage, and same-bar ambiguity semantics. Existing Legacy
   modules remain unchanged and unimported by Outcome.
8. Run focused red/green checks continuously, then the clean disposable
   PostgreSQL and full repository exact-SHA gate. Only executed results update
   Current State/Roadmap and the immutable WP-10 Verification.

## 15. Exit boundary

WP-10 is complete only after the exact-SHA gate proves one commitment root,
linear immutable full revisions, direct frozen reference binding, exact source
and dependency rosters, two cutoffs, zero-write NOT_DUE, independent states,
the single pure kernel, transaction/fence/failure/recovery semantics, exact
idempotency/concurrency, zero-mismatch replay, and the narrow read-only port.

Before the gate, WP-11 was blocked. At the implementation checkpoint recorded
above, the WP-10 gate passes, so only its planning handoff changes:

```text
WP-11 Research Partition + Experiment = NEXT_INDEPENDENT_WORK_PACKAGE / NOT_STARTED
Runtime/CLI Cutover                   = NO_GO
Formal PIT / Formal OOS               = NO_GO
Prospective                           = NO_GO
Production Qualification              = NO_GO
Legacy deletion                       = NO_GO
```

WP-10 creates no Partition, Experiment, Evaluation, Evidence, Assessment,
Qualification, Model, Calibration, Context, Signal, Forecast, Opportunity,
Thesis, Strategy, Portfolio, Risk, Execution, Fill, Position, TradeOutcome,
Attribution, generic registry, compatibility facade, dual write, future FK,
future table/package, or campaign. Passing WP-10 may only mark WP-11 as the next
independent work package; implementation stops at the WP-10 gate.
