# WP-11 Research Validity and Evaluation Closure Design

> **Status:** CANONICAL_TARGET_ARCHITECTURE
> **Authority:** Approved implementation design for the integrated WP-11 draft;
> implementation and validation claims remain owned by executable evidence
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-31
> **Schema Epoch:** `MRA_REFOUNDATION_1`
> **Release/Cutover State:** `DRAFT / NOT_CUT_OVER`
> **Execution-Time Main:** `4aaf4eb1c13f42c01dbc0057078f916fd50cf022`
> **Code Evidence:** `src/market_regime_alpha`,
> `src/market_regime_alpha/infrastructure/postgres/migrations/001_baseline.sql`,
> `tests`, and the immutable WP-09/WP-10 Verification records

## 1. Decision and evidence ceiling

WP-11 is one integrated implementation package inside the existing canonical
Research & Qualification Authority. It does not create a Research Validity
bounded context. The permanent package remains
`market_regime_alpha.research_qualification`, cohesively modularized by Target,
Partition, Experiment, and Evaluation.

The implementation order is mandatory:

```text
Gate A: Target Domain = Target PostgreSQL = Outcome contract
→ Gate B: Partition + Experiment + Protocol + OPEN EvaluationRun, zero access
→ Gate C: exact Outcome access + observations + complete metric rosters
```

WP-11 may reach only:

```text
WP11_IMPLEMENTED_DRAFT
FOCUSED_VALIDATION_PASS
ENGINEERING_QUALIFICATION_PENDING
```

Focused validation is not `WP-11_EXIT_GATE = PASS`. Full PostgreSQL,
concurrency, recovery, replay, full regression, Runtime/CLI cutover, Formal OOS,
Prospective promotion, Provider qualification, Alpha, trading, and Production
proof remain absent.

EvidenceItem, EvidenceDependency, ResearchAssessment, ResearchQualification,
Model, ModelVersion, Calibration, Context, Signal, Forecast, Opportunity,
Portfolio, Risk, Execution, Fill, Position, TradeOutcome, Attribution, Runtime
dispatch, CLI cutover, Legacy deletion, and placeholders for those branches are
outside this package.

## 2. Gate A — Target and Outcome parity

Every successfully registered Target Definition must be consumable by the
canonical Outcome Domain without a later contract-shape rejection. Target
Domain and the root-last PostgreSQL closure function both enforce:

| Metric kind | Exact dependency shape |
|---|---|
| `SIMPLE_RETURN` | exactly one `REFERENCE` and exactly one `OBSERVATION` |
| `OBSERVATION_VALUE` | exactly one `OBSERVATION` |
| `MAX_FAVORABLE_EXCURSION` | exactly one `REFERENCE` and at least one `PATH_MEMBER` |
| `MAX_ADVERSE_EXCURSION` | exactly one `REFERENCE` and at least one `PATH_MEMBER` |
| `BARRIER_HIT` | exactly one `REFERENCE` and at least one `PATH_MEMBER` |

No other dependency role is allowed for a metric. Existing role-to-checkpoint
validation remains mandatory. A Target Definition additionally requires at
least one metric whose completion rule is `REQUIRED`.

This correction does not change Target hashes, Outcome arithmetic, Outcome
revision identity, supersession, status, availability, finality, or numerical
semantics. It closes registration eligibility only.

## 3. Authority ownership and narrow units of work

The Research & Qualification context owns three independent, non-reusable,
non-nestable short transaction boundaries:

| UoW | Owned writers |
|---|---|
| Partition UoW | `ResearchPartition`, `ResearchPartitionMember` |
| Experiment UoW | `Experiment`, `ExperimentPartition`, `ExperimentRun` |
| Evaluation UoW | `EvaluationProtocol`, `EvaluationProtocolMetric`, `EvaluationRun`, `research_partition_outcome_access`, `EvaluationObservation`, `EvaluationMetric`, `EvaluationMetricObservation` |

`EvaluationRun` is created, locked, transitioned, failed, replayed, and queried
only through the Evaluation UoW. The Experiment UoW never creates a Run for a
different owner and never updates an Evaluation Run.

Each owning application module declares its narrow typed ports. PostgreSQL
adapters implement those ports. Domain/Application code does not import a
PostgreSQL repository, Market repository, Outcome repository, Provider, Legacy
package, service locator, or generic repository/UoW.

All business commands use exact command receipts, request hashes, audit facts,
bounded PostgreSQL transient retry, deterministic rollback, unknown-commit
exact replay, and an optional Runtime fence. When a Runtime claim participates,
the live fence is locked first. WP-11 adds no Runtime step, dispatcher, or CLI.

## 4. Closed vocabulary

Partition vocabulary:

```text
PartitionPurpose = DISCOVERY | FIT | VALIDATION | LOCKED_OOS | PROSPECTIVE
PartitionPopulationScope =
  ALL_COMMITMENTS | SELECTED | RANKED_NOT_SELECTED | UNRANKABLE
PartitionOverlapPolicy =
  DIAGNOSTIC_REUSE | PURGED_WALK_FORWARD | ISOLATED_PROTECTED
PartitionStatus = FROZEN
```

Experiment vocabulary:

```text
ExperimentStatus = REGISTERED
ExperimentRunStatus = OPENED
```

Evaluation vocabulary:

```text
EvaluationProtocolStatus = FROZEN
EvaluationRunStatus = OPEN | INPUTS_ACQUIRED | COMPLETED | FAILED
EvaluationReducer =
  MEAN_DECIMAL | MEDIAN_DECIMAL | TRUE_RATE | ESTIMABLE_RATE
EvaluationSliceKind = ALL_MEMBERS | CANDIDATE_DISPOSITION
EvaluationDirection = HIGHER_IS_BETTER | LOWER_IS_BETTER | DESCRIPTIVE
EvaluationValueInclusion = COMPLETE_ONLY | AVAILABLE_VALUE
EvaluationMissingnessPolicy =
  RETAIN_AND_ESTIMATE | REQUIRE_COMPLETE_ROSTER
EvaluationMetricState = ESTIMATED | NOT_ESTIMABLE
EvaluationMetricInputState = INCLUDED | EXCLUDED | NOT_ESTIMABLE
EvaluationAcceptanceOperator = NONE | AT_LEAST | AT_MOST
EvaluationAcceptanceState = ACCEPTED | REJECTED | NOT_APPLICABLE | NOT_ESTIMABLE
```

For `CANDIDATE_DISPOSITION`, the protocol metric must freeze exactly one of
`SELECTED`, `RANKED_NOT_SELECTED`, or `UNRANKABLE`; `ALL_MEMBERS` requires no
disposition. Reducer/source compatibility is frozen and validated by Domain and
PostgreSQL:

| Reducer | Required source Target metric value type |
|---|---|
| `MEAN_DECIMAL` | `DECIMAL` |
| `MEDIAN_DECIMAL` | `DECIMAL` |
| `TRUE_RATE` | `BOOLEAN` |
| `ESTIMABLE_RATE` | `DECIMAL` or `BOOLEAN` |

`NONE` acceptance requires `DESCRIPTIVE` direction and no threshold.
`AT_LEAST`/`AT_MOST` require a finite Decimal threshold. Acceptance is an
Evaluation result only; it is not a Research Assessment or Qualification.

## 5. Research Partition Authority

### 5.1 Root and member contract

`research_partition` freezes:

- stable identity, partition code, purpose, status, and content hash;
- exact Target Definition ID/version/hash;
- declared population scope and its semantic hash;
- decision start/end trading-session FKs;
- maximum Target Outcome session offset and resolved Outcome end session;
- purge-before, purge-after, and embargo session counts;
- resolved protected start/end and embargo-end trading-session FKs;
- exchange, timezone, exact calendar boundary and calendar roster hash;
- overlap policy, series identity, and positive fold ordinal where applicable;
- complete positive member count/hash;
- exact code/config Artifact IDs, hashes, and sizes;
- request identity/hash, actor/reason, and PostgreSQL `frozen_at`.

`research_partition_member` freezes one member ordinal and one exact
`DecisionTargetCommitment` chain: commitment, Decision Run/Target, Candidate
Set/Candidate, instrument, disposition, Target, DecisionTime, Runtime mode,
commitment-recorded time, and commitment hash. The member carries no Outcome
ID, revision, value, status, label, or future Market fact.

The root and complete non-empty member roster are inserted and reconciled in
one Partition UoW transaction. Both are append-only.

### 5.2 Database-derived complete roster

The caller declares Target, Decision window, and one population scope; it does
not submit member IDs. PostgreSQL locks and derives every matching
`decision_target_commitment`:

```text
exact Target Definition
AND DecisionTime maps to a frozen trading session inside the Decision window
AND disposition satisfies the declared population scope
```

The application independently reconstructs the ordered typed roster and hash;
the database closure function recomputes count, contiguous ordinals, Target
match, scope match, session membership, and roster hash. Zero members or any
caller/database reconciliation mismatch fails closed. No Outcome table or
Outcome port is read while freezing a Partition.

### 5.3 Trading-session horizon, purge, and embargo

All offsets traverse exact `trading_session` rows ordered by exchange and
session date. Calendar-day arithmetic is forbidden.

For each member, the Outcome interval starts at its Decision session and ends
at the session obtained by shifting through the Target's maximum Outcome
checkpoint offset. The root Outcome end uses the last member/Decision session.
Purge-before shifts the root Decision start backward; purge-after shifts the
Outcome end forward; embargo then shifts the purge-adjusted end forward. Every
resolved session must exist in the exact calendar roster and match exchange and
timezone. Missing or ambiguous session resolution fails closed.

### 5.4 Purpose-specific overlap policy

WP-11 does not globally reject every same-scope overlap. It freezes the policy
that determines where overlap is prohibited:

| Purpose | Allowed policy | Enforcement |
|---|---|---|
| `DISCOVERY` | `DIAGNOSTIC_REUSE` | overlap is recorded and allowed; it carries no independent-evaluation claim |
| `FIT` | `DIAGNOSTIC_REUSE` or `PURGED_WALK_FORWARD` | formal fold use requires the latter |
| `VALIDATION` | `DIAGNOSTIC_REUSE` or `PURGED_WALK_FORWARD` | formal fold use requires the latter |
| `LOCKED_OOS` | `ISOLATED_PROTECTED` only | its protected range cannot intersect a development/evaluation range with intersecting population for the same Target before first access |
| `PROSPECTIVE` | `ISOLATED_PROTECTED` only | the same isolation rule plus live-clock eligibility applies |

`PURGED_WALK_FORWARD` requires a shared series identity and positive fold
ordinal. Within one fold, matching `FIT` and `VALIDATION` partitions with
intersecting populations must have disjoint protected ranges after Target
horizon, purge, and embargo expansion. Different folds may overlap to support
rolling/walk-forward research; fold order and Decision windows must move
forward. A later fold may reuse an earlier period as fit data without rewriting
the earlier access ledger.

`ISOLATED_PROTECTED` checks all existing non-diagnostic partitions for the same
Target whose population scopes can intersect. It is not bypassed by changing a
series code. Reusing the same frozen Partition through another Evaluation Run
does not create another Partition; access ordinal 2+ makes that use diagnostic.

The PostgreSQL insertion guard serializes the relevant Target/range policy,
recomputes session-derived boundaries, and rejects prohibited overlap. The
application performs the same compatibility check for a typed error, but the
database remains authoritative.

### 5.5 PROSPECTIVE eligibility

Research does not hard-code an allowed Runtime-mode list. A narrow
Research-owned clock-eligibility port asks the Infrastructure adapter to load
the exact Runtime Run and apply the canonical Runtime clock contract, including
mode, requested/created/Decision times, and replay lineage. `HISTORICAL` and
`REPLAY` are always retrospective. `SHADOW` is accepted only when its exact Run
facts satisfy the same live-clock contract; its name alone neither admits nor
rejects it.

For every member, PostgreSQL additionally resolves the earliest Outcome event
from the minimum Outcome checkpoint session offset, checkpoint local time,
timezone, and exact trading calendar, then enforces:

```text
commitment_recorded_at < earliest_outcome_event
```

Mode text, caller time, or an Artifact attestation cannot upgrade historical or
replay facts to Prospective.

## 6. Experiment Authority

`experiment` freezes one research question, one primary change/hypothesis,
exact Target ID/version/hash, protocol identity, acceptance semantics,
code/config Artifacts, provenance, status, content hash, and PostgreSQL
`registered_at`.

`experiment_partition` binds an Experiment to one frozen Partition and purpose.
Composite FKs carry exact Target ID/version/hash and make Target mismatch
unrepresentable. One Experiment may bind multiple purpose-specific partitions;
each binding is immutable and unique.

`experiment_run` is an immutable execution identity for one exact
ExperimentPartition, code/config identity, request, actor, and PostgreSQL
`opened_at`. Status is only `OPENED`. It does not claim success, support,
promotion, or a positive result.

For `LOCKED_OOS` and `PROSPECTIVE`, registration and run opening use
transactional guards that require the Partition to be `FROZEN` and every member
access count to be zero. PostgreSQL authoritative times and concrete FKs prove:

```text
partition.frozen_at < experiment.registered_at < experiment_run.opened_at
```

## 7. Evaluation Protocol and Run Authority

### 7.1 Protocol

`evaluation_protocol` freezes a stable code/version/hash, exact Target
ID/version/hash, applicable Partition purpose, inclusion/exclusion semantics,
decision rule summary, code/config Artifacts, positive metric count/hash,
provenance, status, and PostgreSQL `frozen_at`.

Each `evaluation_protocol_metric` freezes:

- ordinal/code and exact source `target_metric_definition`;
- reducer and source value type;
- slice kind and exact optional Candidate disposition;
- direction, value-inclusion policy, missingness policy;
- positive minimum estimable count;
- acceptance operator and optional Decimal threshold;
- algorithm/code/config identity and content hash.

Protocol root-last closure verifies a complete contiguous metric roster and all
Target/reducer/slice compatibility. Protocol and children are append-only and
cannot be changed after any Outcome access.

### 7.2 Evaluation Run

`evaluation_run` belongs only to the Evaluation UoW. Opening it binds one exact
ExperimentRun, its ExperimentPartition and frozen Partition, one applicable
EvaluationProtocol with the same Target/purpose, one requested knowledge
cutoff, expected member/metric counts, code/config identity, request/provenance,
and PostgreSQL `opened_at`.

The only transitions are:

```text
OPEN → INPUTS_ACQUIRED → COMPLETED
OPEN → FAILED
INPUTS_ACQUIRED → FAILED
```

Status-dependent check constraints and a guarded-update trigger forbid reopen,
input replacement, protocol/partition/experiment changes, backward transition,
or any non-lifecycle mutation. A failed Run is terminal.

For `LOCKED_OOS` and `PROSPECTIVE`, opening requires all prior Authority rows to
be frozen/opened and every PartitionMember access count to be zero. Gate B is a
database-backed query/guard proving:

```text
Partition FROZEN
+ Experiment REGISTERED
+ ExperimentRun OPENED
+ EvaluationProtocol FROZEN
+ EvaluationRun OPEN
+ complete member roster
+ Outcome access count = 0
```

Only after Gate B may `AcquireOutcomeInputs` begin.

## 8. Transaction-bound PIT-safe Outcome access

### 8.1 Resolver contract

The Evaluation UoW exposes no ordinary resolver that can return an Outcome DTO.
Its private transactional acquisition port accepts:

```text
commitment_id + requested_knowledge_cutoff
```

and may expose the resolved Outcome only to the still-active acquisition
transaction. An eligible revision must satisfy all of:

```text
revision.commitment_id = requested commitment
revision.observation_cutoff <= requested_knowledge_cutoff
revision.knowledge_cutoff <= requested_knowledge_cutoff
revision.settled_at <= requested_knowledge_cutoff
```

The selected row is the unique eligible revision with no eligible successor at
that cutoff. The query never uses unrestricted current/latest state. Zero or
multiple visible leaves fail closed. If the Target's canonical maximum due time
is after the requested cutoff, the member is `NOT_DUE` and acquisition fails.
If due but no visible revision exists, acquisition also fails. Resolution uses
only exact immutable Decision/Target/trading-session/Outcome rows: no Provider,
Market repository, bars, label builder, Legacy path, or network call.

Outcome correction/debug may keep `current_for_commitment()` inside the Outcome
owner. No Research/Experiment/Evaluation module imports or invokes it.

### 8.2 AcquireOutcomeInputs

One short PostgreSQL transaction performs all acquisition effects. To preserve
the repository's global lock order, it reads identities first without exposing
values, then locks/revalidates in this order:

```text
optional live Runtime fence
→ exact immutable Target/Runtime/Outcome roots and visible revisions
→ ResearchPartition and complete ResearchPartitionMember roster
→ EvaluationRun
→ command receipt identity
→ access/observation inserts and reconciliation
```

The transaction then:

1. re-proves Gate B and `EvaluationRun = OPEN`;
2. resolves one exact visible revision for every member;
3. appends one `research_partition_outcome_access` per member;
4. creates exactly one `evaluation_observation` per member;
5. reconciles access and observation counts/hashes to the frozen roster;
6. transitions the Run to `INPUTS_ACQUIRED` using PostgreSQL authoritative time;
7. commits the receipt/audit/finalization atomically.

No Outcome state, metric value, DTO, generator item, cursor row, or partial
roster leaves the transaction boundary before the access ledger, complete
EvaluationObservation roster, reconciliation, and status transition commit.
Rollback releases no values to the caller.

`UNAVAILABLE` and `FAILED` revisions are valid acquired observations and remain
in the complete roster. `PARTIAL` remains explicit and is interpreted only by
the frozen metric inclusion policy. `NOT_DUE`, due-but-missing, ambiguity,
incomplete Partition membership, or any reconciliation mismatch rolls back the
whole acquisition; no smaller sample is attempted.

## 9. First Outcome Access Authority

`research_partition_outcome_access` has concrete composite FKs to the exact
EvaluationRun, ResearchPartitionMember, MarketTargetOutcome root, and
MarketTargetOutcomeRevision. It freezes requested cutoff, revision cutoffs,
revision ordinal/status/hash, global per-member `access_ordinal`, and PostgreSQL
`accessed_at`.

Constraints enforce:

- unique `(research_partition_member_id, access_ordinal)`;
- unique `(evaluation_run_id, research_partition_member_id)`;
- `access_ordinal = previous maximum + 1` under a member lock;
- ordinal one has no predecessor and is the sole first-access Authority;
- later EvaluationRuns receive ordinal 2+ and are diagnostic/reuse accesses;
- exact Target/commitment/Partition/Evaluation binding;
- no nullable EvaluationRun FK, polymorphic owner, JSON subject, placeholder,
  registry, replacement, update, or delete.

For protected purposes, an insert guard validates PostgreSQL times, FKs, and
states together:

```text
partition.frozen_at
< experiment.registered_at
< experiment_run.opened_at
< evaluation_run.opened_at
< access.accessed_at
```

The guard does not trust caller timestamps. The participating rows are created
by separate successful transactions, and strict order is revalidated while
locked.

## 10. Evaluation observations and metrics

`evaluation_observation` concrete-FKs one EvaluationRun and one matching
PartitionMember to its exact OutcomeAccess and exact OutcomeRevision. It stores
the immutable revision identity/status/cutoff/hash required to verify the input
roster, not a recalculated label. Unique `(evaluation_run_id,
research_partition_member_id)` and a closure hash make one complete observation
roster mandatory.

After `INPUTS_ACQUIRED` commits, a pure calculation query loads only exact
Outcome revisions and exact `market_target_outcome_metric` rows already named by
EvaluationObservations. It never resolves a different revision and never reads
Market bars or Providers.

For every EvaluationProtocolMetric × EvaluationObservation, completion creates
one `evaluation_metric_observation` with an exact Outcome metric FK and one
state:

- `EXCLUDED`: member is outside the frozen slice, with `OUTSIDE_SLICE`;
- `NOT_ESTIMABLE`: member is in-slice but its exact Outcome metric state/value
  does not satisfy the frozen inclusion rule, preserving `PARTIAL`,
  `UNAVAILABLE`, or `FAILED` reason;
- `INCLUDED`: source value is type-compatible and admitted by the frozen rule.

`COMPLETE_ONLY` admits only `COMPLETE` values. `AVAILABLE_VALUE` may also admit
an exact `PARTIAL` value; it never converts unavailable/failed to zero.
`RETAIN_AND_ESTIMATE` estimates when included count reaches the declared floor.
`REQUIRE_COMPLETE_ROSTER` yields a `NOT_ESTIMABLE` aggregate if any in-slice
member is not estimable. Both policies retain the full metric-member roster.

`evaluation_metric` binds one protocol metric and records expected/included/
excluded/not-estimable counts, roster hash, reducer, state, optional Decimal
estimate, and acceptance state. A metric is `NOT_ESTIMABLE`, not absent, when
its rule cannot estimate.

The completion transaction locks the Partition then EvaluationRun, revalidates
the committed input roster, inserts every declared metric and the complete
Cartesian metric-observation roster, reconciles counts/hashes and acceptance,
then moves the Run to `COMPLETED`. No caller-supplied member list is accepted.

## 11. PostgreSQL enforcement

WP-11 extends only the unreleased
`MRA_REFOUNDATION_1 / 001_baseline.sql`. It adds the twelve real relations:

```text
research_partition
research_partition_member
experiment
experiment_partition
experiment_run
evaluation_protocol
evaluation_protocol_metric
evaluation_run
research_partition_outcome_access
evaluation_observation
evaluation_metric
evaluation_metric_observation
```

There is no `002+`, physical PostgreSQL table partitioning, JSON/JSONB business
fact, generic subject, weak reference, nullable future branch, Model/Forecast/
Evidence placeholder, Legacy facade, or dual write.

Database constraints/functions/triggers own composite Target/commitment/FK
closure, immutable roots/rosters, purpose-policy compatibility,
trading-session-derived ranges, protected overlap, Prospective eligibility,
Experiment binding/order, protocol reducer compatibility, lifecycle guards,
global member access ordinals, exact Outcome revision binding, observation and
metric Cartesian completeness, roster hashes, idempotency, and append-only
history. Python duplicates critical validation for typed errors but cannot
weaken PostgreSQL Authority.

## 12. Concurrency, failure, and recovery

All commands preserve the global order:

```text
Runtime fence when present
→ immutable Artifact/Target/Runtime/Outcome rows
→ Decision commitment where required
→ ResearchPartition
→ ExperimentRun/EvaluationRun
```

No transaction performs Provider, network, broker, filesystem, or Artifact-byte
I/O. Repository methods do not begin nested transactions. Stable advisory/row
locks serialize Partition identity/overlap, Experiment identity, EvaluationRun,
and member access ordinals. Whole-transaction retries are bounded to PostgreSQL
serialization/deadlock/transient connection failures. Exact concurrent requests
produce one writer and one replay; changed request reuse fails closed. An
unknown commit result probes the exact receipt/aggregate identities without
re-executing acquisition or calculation. A stale Runtime fence produces zero
business, failure, audit, or Runtime-finalization writes.

WP-11 implements replay/reconciliation seams needed for exact recovery, but the
full concurrent/recovery/replay qualification campaign belongs to the next
independent work package.

## 13. Focused validation contract

Required focused tests cover:

- all valid/invalid Target metric dependency shapes, zero REQUIRED metric, and
  Target-to-Outcome reconstruction parity;
- database-derived Partition roster completeness, wrong Target/scope rejection,
  trading-session horizon/purge/embargo, purpose-policy overlap, no Outcome read
  during freeze, and Prospective live-clock/event ordering;
- immutable Experiment predeclaration, exact Target/Partition binding, protected
  ordering, and access-zero guards;
- Protocol reducer/source and slice/disposition compatibility;
- Evaluation lifecycle and ownership, Gate B, PIT cutoff resolution, rejection
  of current/latest paths, transaction-bound value visibility, global access
  ordinals, retained unavailable/failed observations, complete observation
  roster, explicit `NOT_ESTIMABLE`, and complete metric Cartesian roster;
- focused PostgreSQL schema/FK/trigger/idempotency correctness needed by those
  invariants.

The following remain `NOT_RUN_BY_SCOPE` even when focused tests pass:

```text
full repository pytest
full Legacy regression
large PostgreSQL integration/concurrency matrix
production/recovery campaign
formal replay qualification campaign
remote CI
Runtime/CLI cutover
Formal PIT/OOS or Prospective campaign
Provider, Alpha, trading, or Production qualification
```

## 14. Completion boundary

WP-11 implementation is complete only when executable code and focused evidence
provide this chain:

```text
REGISTERED Target
→ Outcome-compatible contract
→ database-derived frozen ResearchPartition roster
→ predeclared Experiment and ExperimentRun
→ predeclared EvaluationProtocol
→ OPEN EvaluationRun with zero access
→ transaction-bound exact as-of Outcome access
→ complete EvaluationObservation roster
→ complete EvaluationMetric and metric-member rosters
```

The package must make posterior member selection, posterior experiment/protocol
mutation, unrestricted latest/current Outcome lookup, failed-sample omission,
and bars-to-label reconstruction unavailable through the canonical interfaces.
It still grants no Research Assessment, Qualification, Prospective promotion,
Production admission, or trading authority.
