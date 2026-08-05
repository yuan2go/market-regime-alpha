# WP-DATA-OPS-01 Delivery Evidence

> **Status:** CURRENT_STATUS
> **Authority:** Branch-local WP-DATA-OPS-01 delivery evidence; not Operational Proof
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-05
> **Supersedes:** None
> **Superseded By:** None
> **Evidence Date:** 2026-08-05
> **Base:** `68f91295a888e54b83334c7d7afcaab580961244` (PR #36 merge)
> **Branch:** `feat/controlled-1455-operational-evidence`
> **Related:** ../architecture/15-Controlled-Decision-Time-Operation.md, WP-DATA-OPS-01-Profile-Before.json, WP-DATA-OPS-01-Benchmark.json

## Delivered call chain

The integration test calls the production application code, not hand-built
Candidate/Signal objects:

```text
ControlledDecisionTimeOperationRunner.prepare
-> verified daily Source Archive and SourceManifest
-> Canonical MarketDataDataset
-> FeatureMaterializationRunner
-> StaticUniverseFeatureBundle

ControlledDecisionTimeOperationRunner.run_decision_window
-> PlatformResearchRunner.run_controlled
-> CandidateSet (5 selected from 100-symbol Operational Universe)
-> CandidateMinuteBatchAcquirer (5 recorded Tencent responses)
-> canonical minute Dataset
-> CandidateIntradayFeatureOverlay
-> CandidateFeatureViewV2
-> injected-Clock wait from 14:54:30 to 14:55:00
-> CanonicalDecisionLifecycleRunner with migration-011 journal
   -> SignalRunArtifactV3
   -> PathForecast DATA_INSUFFICIENT
   -> EntryAssessment BLOCKED_BY_MODEL_VALIDATION
-> immutable binding to actual canonical Run/history/Stage Receipts
-> ControlledOperationalEvidencePackage OUTCOME_PENDING

ControlledDecisionTimeOperationRunner.settle
-> verified raw T+1 Outcome Source Archive
-> T+1 verified canonical Dataset
-> 5 factual TradeHorizonOutcomeObservation records
-> superseding SETTLED package
-> LongitudinalOperationalIndex
-> full offline replay STABLE
```

The test also asserts that the output tree contains no Opportunity,
ManualTrade, Fill, order or Broker path. All Signals remain
`DATA_INSUFFICIENT` because Path sample authority is unavailable; this is the
required fail-closed outcome, not a failure disguised as a Recommendation.

## Feature performance root cause and correction

The exact pre-fix profile executed 1,041,670,303 calls in 233.840 profile
seconds. `_compute_artifacts` was entered 175 times and accumulated 177.021143
seconds. Each small batch constructed `_verified_dataset_membership`, which
reverified the Dataset 175 times and verified 35,400 partitions, accumulating
166.816023 seconds.

`PreparedFeatureExecutionContext` now verifies Dataset identity, immutable Bar
membership, scope indexes, definitions/configurations and lineage once.
Planning, batch compute, publication and Task settlement are independent. The
after profile entered `_compute_artifacts` three times, built membership once
and reduced profile time to 25.819 seconds. Final standard wall-time measurement
was 57.986357 seconds with tracemalloc enabled, satisfying the ≤60-second
target. The earlier 584.626303-second result remains historical comparison,
not a fabricated rerun.

## Performance evidence

| Metric | Before | Final |
|---|---:|---:|
| 100-symbol cold V2 | 584.626303 s historical / 234.789293 s exact profile | 57.986357 s |
| 100-symbol peak memory | 179,542,034 B earlier trace | 46,604,431 B |
| 100-symbol output | 18,704,356 B earlier trace | 16,121,164 B |
| 100-symbol files | 2,326 | 2,326 |
| 300-static/10-Candidate cold V2 | not applicable | 161.981241 s |
| 300-static/10-Candidate peak/output/files | not applicable | 125,667,134 B / 40,019,491 B / 4,908 |
| Candidate minute acquisition | not applicable | 7 ms |
| Candidate minute normalization + Dataset | not applicable | 57 ms |
| Candidate intraday overlay | not applicable | 51 ms |
| Signal V3 | not applicable | 32 ms |
| Required decision increment | not applicable | 147 ms ≤ 30,000 ms |

The 300-symbol value is a real two-stage research measurement: five static
families cover all 300 Symbols while two intraday families and 480 five-minute
Bars cover exactly 10 Candidates. It has no absolute CI Gate. The 100-symbol
and decision-increment targets passed on deterministic, offline,
synthetic/recorded Fixtures. The 147 ms increment is the no-crash performance
Fixture; recovery measurements are reported separately because completed work
is content-addressedly reused after restart and must not be presented as cold
compute latency.

## Database authority

Migration 013 rebuilds the Feature Run, Task, Attempt, Receipt and Event tables
with status/JSON/SHA checks, foreign keys, uniqueness and claimable/lease/history
indexes. Triggers prevent Event/Receipt update/delete, settled Attempt mutation,
completed Task regression/deletion, Run command mutation/deletion and
unconditional active-claim replacement. Task settlement matches claim token,
monotonic `claim_epoch` and Task version. Expired leases settle the old Attempt
as `LEASE_EXPIRED`, append an explanatory Event and reclaim only at the next
epoch.

Migration 014 adds parent operation Run, Stage, Attempt, Receipt, Event,
artifact-reference and child-run-reference tables with the same CHECK,
append-only, lease, fencing, CAS and transaction discipline. It references
Daily acquisition, static/intraday Feature, minute batch, canonical lifecycle
and Outcome runs without copying their state. The Canonical child reference is
backed by a real `CanonicalDecisionLifecycleRunner` Run. The published wrapper
binds its command hash, one-snapshot history hash, ordered Stage Receipt hashes
and fail-closed terminal status; the parent binds the wrapper content hash and
Replay verifies it against migration 011 in SQLite read-only mode.
Migration 014 also rejects any `OUTCOME_PENDING -> DEADLINE_MISSED/DATA_BLOCKED`
regression in both the adapter and a database Trigger; only the Outcome stage
may advance it to `SETTLED`.

Migration 015 adds an append-only longitudinal package index with date/model/
configuration/outcome indexes and database triggers rejecting update/delete.

## Recovery evidence

Feature crash tests cover:

- claimed Task before artifact publication;
- artifact published before repository completion;
- Task complete before Bundle publication;
- Bundle published before Receipt completion;
- lease expiry, stale claim token, stale epoch and stale Task version;
- event-history rebuild and serial/parallel Hash equality.

Parent journal tests cover start/resume/idempotency/conflict, child references,
completed Stage immutability, append-only Event/Receipt, leases/fencing, crash
injection, package publication, settlement and index rebuild. Resume also
compares frozen input bytes and all completed-stage Receipt references before
reuse. The full 100-symbol integration injects a failure after the canonical
Signal Stage Receipt is durable, then resumes the same migration-011 Run without
repeating Provider acquisition and proceeds to the Entry blocker. Content-addressed
publication makes a published-but-unsettled artifact reusable without creating
a conflicting second artifact or Receipt.

Resume after DecisionTime is admitted only for a canonical child whose exact
run and command were already persisted no later than DecisionTime. A read-only
migration-011 check verifies its idempotency identity, command time/type/output
root and the Calendar, Universe, SourceManifest, daily/minute Dataset, static
wrapper and overlay hashes frozen in completed parent Receipts. A schema-valid
empty database is not admission evidence. The integration resumes at 14:55:10,
before the 14:56 hard cutoff; a 14:56:01 call against its already-complete
`OUTCOME_PENDING` package is an immutable read, not a new window admission.

## Operational evidence classification

The observed integration Package had:

```text
Universe: 100
Candidates: 5
Recorded Tencent responses: 5 / 5
Canonical child persisted: 14:55:00 under injected Fixture Clock
Injected crash: after durable canonical Signal Stage Receipt
Resume: 14:55:10, without repeating Provider acquisition
Deadline status: RECOVERED_BEFORE_HARD_CUTOFF
Post-cutoff idempotent read: 14:56:01, same pending Package
Canonical child run: lifecycle-run-97e2b7752283e3b220b0d2d2
Canonical wrapper hash: sha256:0790091bbb39fa89f3ef0ed6971b725b007e5b9a1b88e45cb9647bcf7d869dec
Canonical history: sha256:77daf5ad3d26a6dc6e3a3830211087ba47226186eb7eaae6d237e81639ecdcba
Pending package: controlled-package-50e9cfba242e974f37d980ca
Settled package: controlled-package-e938d44b9002f1cf537b2013
Replay: STABLE
Outcome observations: 5 factual records
T+1 raw source archive: exact-file/hash verified and Dataset replayed from source
Recovery Fixture operation output: 11,063,466 bytes / 1,815 files
```

This was not a real 14:55 execution. It is `ENGINEERING_FIXTURE` evidence.
Provider success rate, deadline and Package identifiers above must not be cited
as Operational Proof or Provider qualification.

## Safety and remaining work

```text
NO_ORDER_CREATED = true
BROKER_NOT_INVOKED = true
NO_FILL_CREATED = true
ENTRY_MODEL_EMPIRICALLY_VALIDATED_FALSE = true
FORMAL_OOS_ALPHA_NOT_ESTABLISHED = true
PathForecast Sample Authority = unavailable
Entry = blocked
Shadow Ready = NO
Trading Authority = NO
```

The next authorized work remains limited to:

- `WP-MIG-01B`: Force Ratio / Chan / Tuishen;
- `WP-SIG-01B`: Buy Point Quality / Sell Pressure / Certainty / Attention;
- `WP-H9A`: Formal Validation Infrastructure;
- `WP-ENTRY-01`: Entry Model V1.

Real controlled 14:55 operation, repeated trading-day coverage, Provider
qualification, formal PIT/OOS, H7/H8/H9, PostgreSQL, RBAC, frontend and Broker
authority remain outside this delivery.
