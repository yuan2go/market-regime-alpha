# WP-11Q Research Validity and Evaluation Qualification Design

> **Status:** CANONICAL_TARGET_ARCHITECTURE
> **Design State:** `APPROVED_FOR_IMPLEMENTATION`
> **Authority:** Correctness and exact-SHA engineering-qualification contract
> for WP-11 only
> **Owner:** Market Regime Alpha maintainers
> **Frozen At:** 2026-09-01
> **Execution-Time Main:** `d7f41a30f1917fc3b266bdeebbc157021c3cc352`
> **Execution Branch:** `agent/wp-11q-research-validity-evaluation-qualification`
> **Schema Epoch:** `MRA_REFOUNDATION_1 / DRAFT / NOT_CUT_OVER`
> **Supersedes:** WP-11 implementation-detail claims where this execution-time
> audit found composition, exchange-calendar, Experiment-roster, or
> qualification gaps

This record freezes the WP-11Q correction before business source or DDL is
changed. It preserves the approved integrated WP-11 Authority and closes the
gaps that prevent an engineering exit gate. It creates no WP-12 relation,
package, placeholder, Evidence, Assessment, Qualification, Model, Runtime
dispatch, or CLI path.

## 1. Execution-time audit result

The fetched baseline contains the focused-validated WP-11 implementation and
no immutable WP-11 Verification. Executable evidence identifies four required
closures:

1. `bootstrap.py` does not construct the existing Partition, Experiment, or
   Evaluation commands. Only tests can currently assemble their PostgreSQL
   adapters.
2. Partition boundaries are checked as one exchange, but the root does not
   freeze that exchange/calendar identity and roster derivation/closure selects
   commitments by `session_date` without requiring the same exchange. Same-date
   SSE and SZSE commitments can therefore enter one Partition.
3. Experiment Domain, command, repository, record, and replay accept one
   `ExperimentPartitionBinding`. The database root freezes no binding count or
   roster hash and has no complete-root closure.
4. Local reconciliation exists inside individual commands, but no formal
   read-only verifier reconstructs the complete Target → Partition → Experiment
   → Evaluation chain, access ordinals, receipts, audit, and optional Runtime
   provenance.

The audit additionally found that PostgreSQL connection failure during
`commit()` is currently classified as an automatically retryable transaction.
WP-11Q must distinguish unknown commit outcome from a known pre-commit
transient failure so an ambiguous business mutation is never blindly repeated.

## 2. Preserved Authority and dependency direction

All objects remain cohesive modules of the existing
`market_regime_alpha.research_qualification` bounded context:

```text
Partition UoW  → ResearchPartition / ResearchPartitionMember
Experiment UoW → Experiment / ExperimentPartition / ExperimentRun
Evaluation UoW → EvaluationProtocol / EvaluationProtocolMetric /
                 EvaluationRun / OutcomeAccess / EvaluationObservation /
                 EvaluationMetric / EvaluationMetricObservation
```

No UoW imports or delegates to another UoW. EvaluationRun remains exclusively
owned by the Evaluation UoW. Owning Application code imports only its Domain
and typed ports; PostgreSQL adapters stay in Infrastructure. The correction
introduces no generic repository, service locator, command bus, shared mutable
aggregate, compatibility facade, or dual write.

Gate order remains:

```text
Gate A — Target Domain = Target PostgreSQL = Outcome contract
Gate B — complete pre-access freeze + OPEN EvaluationRun + zero access
Gate C — complete access/observation/metric Cartesian closure
```

Existing Target/Outcome parity, numerical semantics, correction lifecycle,
database-derived member selection, live-clock Prospective rule, PIT-safe exact
revision resolution, transaction-bound value visibility, global access
ordinals, and failed/unavailable/not-estimable preservation are invariants of
this correction.

## 3. Sole target composition

The sole target `bootstrap.py` constructs the three existing command modules
from their three PostgreSQL UoW providers and exposes them explicitly:

```text
TargetApplication.research_partitions
TargetApplication.research_experiments
TargetApplication.research_evaluations
TargetApplication.research_evaluation_verifier
```

The resulting public command paths are:

```text
research_partitions.freeze
research_experiments.register
research_experiments.open_run
research_evaluations.register_protocol
research_evaluations.open_run
research_evaluations.acquire_outcome_inputs
research_evaluations.complete
```

`research_definitions` remains the existing Dataset/Feature/Target facade; it
is not widened into a God UoW. The new fields are normal in-process
composition, not Runtime dispatch. CLI, schedules, Step vocabulary, and the
legacy composition remain unchanged.

Architecture tests instantiate the real `TargetApplication`, prove the command
objects use the correct concrete UoW providers, and reject direct
Domain/Application-to-PostgreSQL imports.

## 4. One Partition, one explicit exchange calendar

### 4.1 Declaration and derived identity

`ResearchPartitionPlan` adds one required, closed-format `exchange_code`.
The caller still cannot submit members, dates, calendar rows, roster hashes,
Outcome IDs, or labels.

PostgreSQL derives and the root freezes:

- exact `exchange_code` and `timezone_name`;
- Decision start/end Session identities and dates;
- protected start/end Session identities and dates;
- maximum Target Outcome session horizon;
- purge-before, purge-after, and embargo session counts;
- the complete exchange Session roster spanning protected start through
  protected end, with positive `calendar_session_count` and canonical
  `calendar_roster_sha256`;
- member count/hash and all existing code/config/provenance facts.

The calendar roster hash covers, in session order, the exact Session ID,
exchange, date, timezone, open/close/reference times, Capture identity,
recorded time, and known time. It verifies relational rows and never replaces
them.

### 4.2 Relational proof

Trading Session exposes a Partition-specific composite unique identity. Root
boundary FKs carry Session ID + exchange + date + timezone. Each member freezes
its Decision Session date/exchange/timezone and concrete-FKs the same identity,
as well as the existing exact Decision reference chain.

Roster derivation and the deferred bidirectional set closure both require:

```text
commitment Target = Partition Target
AND Decision reference Session exchange = Partition exchange
AND Session date is inside the declared Decision window
AND Candidate disposition is inside the declared population scope
```

Target checkpoint shifts, earliest Outcome event, due event, protected range,
purge, and embargo traverse only ordered Session rows for the explicit
exchange. Missing, duplicated, cross-exchange, or incomplete Session facts fail
closed. An SSE Partition cannot acquire an SZSE commitment merely because the
two exchanges share a `session_date`.

Overlap compatibility is evaluated only where populations can intersect: same
Target and exchange, compatible population scopes, protected ranges, purposes,
series, and folds. Diagnostic reuse and different rolling folds remain legal;
LOCKED_OOS/PROSPECTIVE isolation and same-fold purged walk-forward separation
remain enforced symmetrically under the existing Target-scoped serialization.

## 5. Complete immutable Experiment Partition roster

### 5.1 Domain and command

`ExperimentPartitionBinding` adds a positive `binding_ordinal`.
Registration accepts an immutable tuple:

```text
register(
    definition: ExperimentDefinition,
    bindings: tuple[ExperimentPartitionBinding, ...],
    context: CommandContext,
)
```

The tuple must be non-empty and must have contiguous ordinals `1..N`. Every
binding must name the Experiment, exact Target ID/version/hash, one typed
Partition purpose, and exact Partition content hash. Binding IDs and Partition
IDs are unique. Multiple partitions with the same purpose remain legal for
declared rolling/fold designs; duplicate bindings do not.

The owner computes:

- definition hash from the immutable question/primary change/hypothesis and
  protocol/code/config/provenance facts;
- ordered `partition_count` and `partition_roster_sha256`;
- aggregate Experiment `content_sha256` over definition plus roster summary;
- semantic request hash over the exact definition and complete tuple.

### 5.2 Atomic PostgreSQL closure

The Experiment root stores definition hash, positive partition count, ordered
roster hash, and aggregate content hash. Child rows store their exact ordinal.
The registration transaction inserts the root and all children under one
PostgreSQL-authoritative registration time. A child insert guard permits rows
only while that root was created by the current transaction. A deferred root
closure recomputes:

- non-empty count;
- contiguous ordinals;
- no duplicate Partition or binding;
- exact Target/purpose/content binding to every frozen Partition;
- ordered roster hash and aggregate Experiment hash;
- protected-purpose zero-access and Partition-before-Experiment ordering.

A raw SQL root without all children, a partial mid-command failure, a missing
ordinal, a substituted Partition, or a late child cannot commit. Experiment
Run continues to bind one exact ExperimentPartition child and must open strictly
after the complete Experiment registration.

Exact command retry reloads the entire root/child roster and compares its
result hash. Reusing an idempotency identity with any changed order or binding
fails closed.

## 6. Evaluation and first-access preservation

Evaluation behavior is not redesigned. WP-11Q adds regression and race proof
that:

- protected Gate B locks and proves the complete Experiment roster exists,
  the selected ExperimentPartition belongs to it, EvaluationRun is `OPEN`, and
  its access count is zero;
- Outcome correction and acquisition serialize on exact Outcome roots before
  Partition/Evaluation locks;
- member-scoped advisory locks assign globally contiguous access ordinals;
  exactly one row can be ordinal one;
- each acquisition atomically writes the complete access and observation
  rosters and transitions to `INPUTS_ACQUIRED` before returning identities;
- each completion atomically writes every protocol-metric × member input and
  transitions to `COMPLETED`;
- `UNAVAILABLE`, `FAILED`, and `NOT_ESTIMABLE` remain relational states, never
  omitted members.

Acquire/Fail and Complete/Fail races may have one terminal winner only. The
loser observes and reports the canonical state; it cannot fork inputs, reopen a
Run, or create a second terminal truth.

## 7. Formal read-only verifier

Research & Qualification declares a read-only verification port implemented by
PostgreSQL Infrastructure. `ResearchEvaluationVerifier` exposes:

```text
verify_partition(partition_id)
verify_experiment(experiment_id)
verify_evaluation_run(evaluation_run_id)
```

Each returns immutable typed mismatches plus:

```text
matched: bool
mismatch_count: int
```

The verifier reconstructs, as applicable:

- Target/Outcome metric dependency compatibility;
- Partition Target, exchange calendar roster/hash, boundary/protected range,
  trading-session shifts, declared population set, member count/order/hash;
- Experiment definition, complete ordered binding roster/count/hash, Target
  agreement, and immutable Run binding;
- EvaluationProtocol metric count/order/hash and reducer/source/slice shape;
- EvaluationRun lifecycle/version/times and frozen parents;
- global access ordinal chain and unique ordinal one;
- cutoff-visible exact Outcome revision identity;
- complete EvaluationObservation roster;
- EvaluationMetric roster and full MetricObservation Cartesian roster;
- successful receipt, audit, and optional Runtime claim/fence provenance.

It reads only frozen owner rows and exact FKs. Provider calls, Market
reconstruction, bars-to-label calculation, unrestricted current/latest
queries, and mutation are absent from the port and implementation. Passing is
only `matched = true` with `mismatch_count = 0`.

## 8. Transactions, unknown commit, failure, and recovery

Global lock order remains:

```text
optional live Runtime fence
→ immutable Artifact/Target/Runtime/Outcome identities
→ Decision commitment where required
→ ResearchPartition and ordered members
→ ExperimentRun/EvaluationRun
```

All commands remain short PostgreSQL transactions with no Provider, network,
filesystem, broker, or Artifact-byte I/O and no nested transaction.
Serialization/deadlock/known pre-commit connection failures receive a bounded
whole-transaction retry over identical prepared inputs and identities.

A connection/transport error raised by `commit()` is instead
`ResearchUnknownCommitOutcomeError`. It is not consumed by the automatic
transient retry loop. Recovery performs an exact receipt/root probe using the
same command kind, scope, idempotency key, and semantic request hash:

- committed success reloads and reconciles the exact aggregate;
- committed failure reloads the exact failure;
- unresolved absence remains explicitly unknown for that invocation and does
  not trigger a blind business mutation.

A later explicitly initiated exact recovery command again probes first and may
execute only when Authority proves the prior transaction did not commit.
Stale Runtime fences write no business, receipt, failure, audit, or Runtime
finality. Failure-recorder failure rolls back its own short transaction and is
reported without fabricating a durable failure fact.

## 9. TDD and qualification contract

Implementation begins with failing tests at the public seams above. Required
correctness slices are:

1. real bootstrap construction and callable command surfaces;
2. Domain exchange identity and multi-binding roster validation/hash;
3. SSE/SZSE deliberately divergent Session rosters proving strict exchange
   isolation and no same-date contamination;
4. Experiment non-empty/ordered/multi-purpose root/child closure, exact replay,
   changed roster, incomplete raw SQL, and late binding rejection;
5. verifier zero-mismatch and deliberately corrupted/missing/extra/order/hash/
   lifecycle/provenance mismatch classification;
6. preserved Gate A/B/C, access, observation, metric and missingness behavior.

After focused regression, correctness is frozen at one implementation SHA.
Qualification uses a new disposable PostgreSQL 16 database and reruns any
affected gate whenever source, tests, or DDL changes. It includes:

- clean bootstrap/verify/guarded exact-name-and-OID recreate/verify;
- real concurrent identical/conflicting Partition, protected overlap,
  Experiment roster, EvaluationRun, first access, correction/acquire,
  acquire/fail and complete/fail races;
- serialization, deadlock, connection, unknown-commit, stale-fence, mid-roster,
  mid-access/observation/metric, failure-recorder and exact recovery campaigns;
- formal verifier/reconciliation qualification;
- representative `EXPLAIN (ANALYZE, BUFFERS)` for the six required paths;
- focused, refoundation, platform, PostgreSQL persistence and full repository
  pytest; full Ruff, mypy, build, docs/navigation, architecture/import,
  schema/catalog/checksum and diff gates.

Remote CI is `BLOCKED_BY_REPOSITORY_CONFIGURATION / NOT_RUN` when repository
Actions remain disabled; it is never promoted to PASS.

## 10. Exit and sequential stop boundary

Only evidence bound to the final exact implementation SHA may create the
immutable WP-11 Verification. `WP11_EXIT_GATE = PASS` requires every P0/P1
correctness and local engineering gate above to pass. Otherwise the gate is
`NO-GO` and execution stops before WP-12.

After PASS, the branch must be clean, reconciled with newly fetched main,
pushed, reviewed and merged. Only a newly fetched remote main containing both
the exact verified implementation and immutable PASS Verification can unblock
a fresh WP-12 branch/worktree.

The following remain NO-GO throughout WP-11Q:

```text
Evidence / Assessment / Research Qualification
Model / Calibration / Context / Signal / Forecast
Portfolio / Risk / Execution / TradeOutcome / Attribution
Runtime dispatch / CLI cutover / Legacy deletion
Formal PIT / OOS / Prospective promotion
Provider / Alpha / broker / Production qualification
```
