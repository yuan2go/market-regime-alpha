# WP-ARCHITECTURE-REFOUNDATION-10 Market Target Outcome Verification

> **Status:** CURRENT_STATUS
> **Verification State:** `WP10_MARKET_TARGET_OUTCOME_ENGINEERING_GO`
> **Authority:** Exact-SHA local engineering verification record; not Research Partition, Experiment, Evaluation, Evidence, Qualification, Model, Context, Execution, Prospective, Runtime/CLI Cutover, trading, or Production Authority
> **Owner:** Market Regime Alpha maintainers
> **Executed At:** `2026-08-31 (Asia/Shanghai)`
> **Execution-Time Origin Main:** `origin/main@a5e1c1b1cac9563582ad71abfbad7ecbe53075c2`
> **Documentation Cleanup Checkpoint:** `3056313c61876514e6a08b349e5d8dd8622388df`
> **Approved Design Checkpoint:** `a1dd9912563d50c5501b483ca86abfb5c0e70e27`
> **Implementation Checkpoint:** `56812c58ce7b6e601366ffd0a5cfb52fec573227`
> **Containing Documentation Commit:** reported by the final handoff; this file does not claim a self-referential Git SHA
> **Schema Epoch:** `MRA_REFOUNDATION_1`
> **Release State:** `DRAFT`
> **Cutover State:** `NOT_CUT_OVER`
> **Code Evidence:** `src/market_regime_alpha/outcome`, `src/market_regime_alpha/infrastructure/postgres`, `src/market_regime_alpha/bootstrap.py`, `tests/refoundation/outcome`

This record verifies only the WP-10 Market Target Outcome realized-fact
Authority. The engineering decision is:

```text
WP-10 MARKET TARGET OUTCOME EXIT GATE = PASS
MRA_REFOUNDATION_1 / DRAFT / NOT_CUT_OVER
```

WP-11 Research Partition + Experiment is only the next independent work
package and has not started. Evaluation, Evidence, Qualification, Model,
Context, Runtime/CLI Cutover, Formal PIT, Formal OOS, Prospective, Production,
broker authority, automatic trading, and Legacy deletion remain **NO-GO**.

## 1. Baseline, branch, worktree, and checkpoint chain

Execution first fetched the remote and created an isolated branch/worktree from
the then-current exact `origin/main`:

```text
remote                 git@github.com:yuan2go/market-regime-alpha.git
origin/main             a5e1c1b1cac9563582ad71abfbad7ecbe53075c2
branch                  agent/wp-10-market-target-outcome-authority
worktree                /Users/yuan/projects/market-regime-alpha-worktrees/wp-10-market-target-outcome-authority
original checkout       agent/wp-portfolio-execution-authority-01
original dirty path     .idea/modules.xml (pre-existing; not touched)
```

The dependency-coherent checkpoint chain is:

```text
a5e1c1b1cac9563582ad71abfbad7ecbe53075c2  execution-time origin/main
3056313c61876514e6a08b349e5d8dd8622388df  independent docs cleanup
a1dd9912563d50c5501b483ca86abfb5c0e70e27  approved canonical WP-10 design
fd32f80b3c6d0990983727af787ea97f79f5cc64  Market Target Outcome Authority
56812c58ce7b6e601366ffd0a5cfb52fec573227  closed typed source-role vocabulary
```

The implementation checkpoint binds:

```text
root tree                 15f3adc2b5a424a81cfa1224dfee4b04b6b422fa
source tree               1ad379e67be0960a45d7c1d8f11fb953fd11480e
tests tree                b03577799a3b76585b1ec3fe023c2adb3a8ceff3
Outcome tree              d984bcc66246be0f68d530c46fe3a1c85294a16a
target baseline blob      37522c256e5bfe0c28d43a48256dfd5aac7f2068
legacy migrations tree    6d3730548780ad6244d2cfecb4fb3559064b6f06
```

## 2. Pre-code audit and documentation cleanup

The audit read and cross-checked `AGENTS.md`, `CONTEXT-MAP.md`, docs navigation,
the four canonical architecture documents, Authority Map, Current State,
Roadmap, WP-08 design, immutable WP-09 Verification, Target/checkpoint/metric/
dependency Domain and DDL, Decision Run/commitment/reference Domain and DDL,
Market/PIT Capture/Product/Session/revision/SourceGap/corporate-action models,
Runtime claim/fence/failure code, target bootstrap/composition, expected catalog
and checksum verification, disposable database tests, architecture/import
guards, all refoundation tests, and relevant Legacy return/MFE/MAE/barrier/
settlement/label writers and readers.

Material executable findings were:

- execution-time main was the merged WP-09 checkpoint and the target draft had
  48 tables/four views with no Outcome relation or package;
- one immutable `decision_target_commitment` already had exactly one frozen
  `decision_reference_observation`; its concrete source was one bar revision or
  SourceGap and its `known_at` was bounded by DecisionTime;
- provider-neutral Target versions already held ordered checkpoints, metrics,
  required/optional completion, algorithm/code/config identity, and typed
  `REFERENCE`/`OBSERVATION`/`PATH_MEMBER` dependencies;
- `decision_run_target` and exact Market revisions/gaps supplied Product and
  Capture provenance, so Target Definition did not need a Provider binding;
- Market/PIT already exposed exact bounded facts, revisions, gaps, Sessions and
  known-at semantics. It had no formal Provider finality Authority, requiring
  Outcome finality to remain `UNKNOWN`;
- Runtime supplied a real `SETTLE_OUTCOME` Step vocabulary plus live
  Run/Step/Attempt fencing, receipt/audit/finalization and failure patterns, but
  no Outcome dispatch or production CLI;
- Legacy had multiple realized-return/path/label writers. Only Decimal
  checkpoint return, clamped excursion, first passage, and explicit same-bar
  ambiguity were intentionally retained as numerical characterization; no
  Legacy module could become a target runtime dependency;
- the WP-08 historical handoff still described WP-09 as pending even though
  immutable WP-09 evidence had closed it.

The independent cleanup commit changed only the WP-08 handoff status. It did
not rewrite WP-08's frozen design facts or any immutable Verification. The
canonical design commit then recorded the concrete dependency split, aggregate
lifecycle, cutoffs, kernel, transaction, retry, replay, schema, TDD and NO-GO
contract before business code or DDL entered the branch.

No audited fact changed WP-08 bounded-context ownership, dependency direction,
Outcome lifecycle, or WP-10 scope.

## 3. Bounded contexts and dependency direction

Permanent ownership is:

```text
Decision Support
  owns DecisionTargetCommitment and frozen DecisionReferenceObservation

Research & Qualification
  owns exact TargetDefinition/Checkpoint/Metric/Dependency versions

Market & PIT
  owns Product/Capture/Session/bar/corporate-action/SourceGap facts

Outcome & Attribution
  owns MarketTargetOutcome root/revisions and SettleMarketTargetOutcome

Runtime
  owns orchestration, live claim/fence, receipt/audit support and Step finality
```

Permanent `market_regime_alpha.outcome` contains Domain, Application and
Outcome-owned ports. Domain has no Infrastructure, Runtime implementation,
Market implementation, Decision implementation, Research implementation, I/O,
Provider, or Legacy import. Application consumes only immutable typed facts
through its own preparation/repository/UoW/query/verification ports and the
narrow existing Runtime command contracts. Infrastructure implements those
ports and owns PostgreSQL mapping without exposing a session or another
bounded-context repository.

No generic repository/registry, polymorphic subject, JSON Authority, shared
mutable aggregate, hidden global session, service locator, God UoW,
compatibility facade, dual write, or cross-context mutation seam was added.
Production Runtime/CLI dispatch was not changed.

## 4. Commitment root and immutable Decision reference

One `market_target_outcome` root binds exactly one
`decision_target_commitment`; the one-to-one unique key prevents a second root.
Composite FKs retain the same Decision Run, Candidate Set, Candidate, Target,
instrument, exact Target version/hash, and exact
`decision_reference_observation` scope.

The Decision reference is reused directly. It is never queried from Market,
copied into a replacement truth, recomputed at settlement, changed to a newer
revision, repaired after Provider correction, or filled from zero/prior
session/latest data. Its content hash and concrete identity are frozen on the
root and included in every revision's definition summary.

Target metric dependencies are concrete and non-polymorphic:

- `market_target_outcome_metric_reference` accepts only `REFERENCE`; it
  composite-FKs the exact Target dependency, same-revision Outcome metric,
  Outcome root, and frozen WP-09 Decision reference;
- `market_target_outcome_metric_observation` accepts only `OBSERVATION` or
  `PATH_MEMBER`; it composite-FKs the exact Target dependency, same-revision
  Outcome metric, and one Outcome observation from that same revision.

PostgreSQL therefore rejects a wrong Decision reference, Target dependency,
metric, checkpoint, revision, root, instrument, Product, or commitment without
relying on caller discipline.

## 5. Append-only revision lifecycle

The stable root has a linear chain of full snapshots:

```text
revision 1 → revision 2 → revision 3 → ...
```

Each revision freezes its positive contiguous ordinal, direct predecessor,
request identity/hash, dual cutoffs, settled/request times, exact Runtime
identity, algorithm/code/config/Target/reference summary, full child counts and
roster hashes, aggregate status, availability, finality, receipt and audit.

Version one has no predecessor. Every correction must use a new request
identity and name the exact current leaf. A root/head lock plus unique ordinal,
unique predecessor, immediate-predecessor validation and one direct successor
permit one leaf only. A concurrent loser sees a stale predecessor conflict;
there is no revision fork or best-effort merge.

Every root, revision and child is append-only. Child inserts are allowed only
while the revision root is absent in the same transaction. The revision is
inserted last; its closure trigger verifies source/observation/metric/
dependency/reason counts, contiguous ordinals, canonical hashes, required
Target dependency coverage, exact state roll-up, predecessor and Runtime/
receipt closure. Historical rows cannot be updated, deleted, rebound, reordered
or replaced.

## 6. Due, dual-cutoff, source and state semantics

Due assessment happens before opening the Outcome write UoW. If the final
required Target window is not due, the command returns typed `NOT_DUE` with
`database_writes=0`. It creates no root, revision, placeholder, receipt, audit,
failure fact or Runtime finalization.

Every due revision stores two independent boundaries:

```text
event_end <= observation_cutoff
known_at  <= knowledge_cutoff
```

The exact Session roster resolves Target offsets. The exact observation roster
resolves every checkpoint in Target order to one `market_bar_revision` or one
`source_gap`. Every source records a closed source kind and role, checkpoint,
instrument, Product, Capture, Session, event range, known-at, revision/gap
identity and provenance. Later-known facts and after-window observations are
rejected before calculation and revalidated under lock in the transaction.

`OutcomeStatus` is closed to `PARTIAL`, `COMPLETE`, `UNAVAILABLE`, and
`FAILED`; `NOT_DUE` is deliberately not a stored fact. Availability is closed
independently to `AVAILABLE`, `UNAVAILABLE`, or `FAILED`. Current finality is
the separate honest value `UNKNOWN`. A present bar does not fabricate `FINAL`;
an intrabar ambiguity can be `PARTIAL + AVAILABLE + UNKNOWN`; an explicit gap
can be unavailable or failed without a zero value. Required metrics control
aggregate completeness; optional failures remain visible but do not falsely
block a complete required roster.

## 7. Single pure numerical kernel

`calculate_market_target_outcome(...)` is the only target numerical writer. It
accepts only frozen Commitment/reference, exact Target, Session/source rosters,
and the two cutoffs, and returns an immutable `OutcomeRevisionDraft`.

The kernel uses a fixed precision-38 `Decimal` context with half-even rounding.
It calculates:

- checkpoint selected value plus exact OHLC/path state;
- simple return from the frozen Decision reference;
- clamped maximum favorable and adverse excursion;
- up/down barrier hit and first-passage time;
- explicit same-bar opposing-barrier ambiguity;
- observation/metric/source reasons and required/optional roll-up;
- concrete reference and observation/path dependency drafts.

The kernel has no PostgreSQL, Provider, network, filesystem, clock, Runtime,
latest/current query, mutable global state, float financial arithmetic, or
side effect. A single characterization test compares only the intentionally
preserved Legacy Decimal path numerics; target runtime imports no Legacy label
writer and retains no second canonical bars-to-label authority.

## 8. Relational catalog and PostgreSQL enforcement

WP-10 extends only unreleased `MRA_REFOUNDATION_1/001_baseline.sql`; it creates
no `002+`, compatibility schema, dual-write table or future placeholder.

WP-08's semantic catalog contained 117 relations and represented all metric
dependencies through one observation concept. That could not concrete-FK
`REFERENCE` to WP-09 while also concrete-FKing same-revision
`OBSERVATION`/`PATH_MEMBER`. WP-10 records the normalization correction by
splitting the two shapes. The logical destination catalog becomes 118, and the
physical target draft adds exactly these eight real Authority tables:

```text
market_target_outcome
market_target_outcome_revision
market_target_outcome_source
market_target_outcome_observation
market_target_outcome_metric
market_target_outcome_metric_reference
market_target_outcome_metric_observation
market_target_outcome_reason
```

The PostgreSQL 16.14 target catalog is:

```text
tables                           56
views                             4
indexes                         421
constraints                     699
functions                        42
non-internal triggers           116
catalog objects               1,339

baseline              7a8d641140f855a4e6dd15e0bcad6430dbb715e224a00603d437d058d6a63baf
seed                  9c41cd715e35e1a7bed3a58c52a29f01cc1e9bf950b77344bb56eac6dfa2df11
reference vocabulary 37dae1c30c2c37a30b810af2f7a70d9198f6ec0f4245981211618144eb9bebe6
catalog               6c3e2732024ae28875df111ad3ef97cd8c8520f40adc168b0ac8951048335888
```

Key root/revision constraints include one commitment/root, exact commitment/
reference/Target composite FKs, unique request identity/hash, unique ordinal,
unique predecessor, receipt and Runtime claim FKs, chain/count/hash/cutoff/
state/time/request/runtime CHECKs, and root/reference/revision scope uniques.

Source constraints include exact bar/gap/session/checkpoint FKs, observation and
Session Product/Capture provenance composite FKs, source XOR/shape, typed role,
two-cutoff CHECKs and unique ordered scope. Observation/metric constraints bind
the exact Target checkpoint/metric plus same-revision source and enforce typed
value/status shape. Dependency constraints bind the exact Target dependency and
same-revision metric/fact with closed roles. Reason constraints enforce one
typed source/observation/metric/revision dimension and stable order/identity.

Every Outcome table has an append-only trigger. Every child also has an
open-revision guard; revision has predecessor and root-last closure guards.
All concrete/composite FK paths have leading indexes. Dedicated indexes cover
commitment/root lookup, current leaf, request replay, predecessor, Runtime,
source bar/gap/Session/Capture/Product, checkpoint, metric, dependency, reason
and read-only replay. Representative executed plans use declared owner indexes;
tests do not freeze optimizer costs or an exact node shape.

## 9. Settlement transaction, lock order, failure and recovery

Provider acquisition, normalization, network/file/Artifact byte I/O are absent
from settlement. Exact preparation is read-only and occurs before the write
transaction. The short SERIALIZABLE write transaction is:

```text
live Runtime Run/Step/Attempt fence
→ immutable Artifact / Target / Market revisions and Sessions
→ Candidate Set / Candidate
→ Decision Run / Commitment / frozen Decision reference
→ MarketTargetOutcome root/current leaf
→ revision children
→ revision root-last closure and reconciliation
→ receipt + audit + matching Attempt/Step success
→ commit once
```

The Runtime fence is always locked first and never reacquired in reverse. The
transaction revalidates the prepared exact identities, hashes, known-at/event
boundaries and source roster under lock. There is no nested transaction,
external wait, Provider call, filesystem read, partial commit or cleanup pass.

Only SQLSTATE `40001` and `40P01` retry the whole transaction, with the same
frozen draft and preallocated identities, at most three attempts. A transport
failure after commit is an unknown outcome and is resolved only by exact
read-only request replay; absence remains an explicit unknown result, never a
blind second write.

Deterministic failure rolls back every Outcome fact, then opens a fresh narrow
Outcome UoW, re-locks the still-live fence first, and atomically records one
failed receipt, audit and Attempt/Step failure. If failure recording fails, its
incident transaction also rolls back and the claim remains recoverable. A stale
or lost fence creates zero business writes and zero failure writes. Recovery
uses a fresh Runtime attempt and exact command replay; a tested mid-write crash
left no partial root/child and subsequently settled successfully.

## 10. Idempotency and concurrency

The owner-computed semantic request hash covers exact commitment/Target/
reference identities and hashes, both cutoffs, exact Session/source roster,
algorithm/code/config identity, actor/reason, Runtime Run and expected current
leaf. The caller cannot submit or override it.

- Exact retry returns the original root, revision, rosters, reference, counts,
  hashes, receipt and Runtime finalization and does not rerun preparation.
- Reusing an idempotency identity with a changed cutoff or other semantic fact
  fails closed and cannot reuse or overwrite the original result.
- A changed cutoff/source/algorithm is a correction only with a new request
  identity and the exact current leaf as predecessor.
- Concurrent identical requests have one canonical writer and one exact
  replaying result; no duplicate audit, receipt, root or child appears.
- Concurrent corrections from one leaf have one successor. The loser receives
  a deterministic stale-predecessor conflict and cannot fork the chain.

The PostgreSQL tests exercise these behaviors with real concurrent
transactions; mocks do not substitute for database authority.

## 11. Replay, reconciliation, and permanent read-only port

`OutcomeVerifier` and its PostgreSQL verification provider are read-only. They
reconstruct the root, complete revision chain, predecessor/current leaf, both
cutoffs, exact commitment/reference/Target version, source/observation/metric/
dependency/reason rosters, counts/hashes, state roll-up, algorithm/code/config,
request/receipt and Runtime identity. The pure kernel is rerun only against the
frozen relational rows; no source is re-resolved.

Typed mismatch kinds distinguish identity, missing row, extra row, order,
count, hash, revision chain, cutoff, reference, source state, metric value,
dependency, reason, Runtime identity, receipt and immutable-fact mutation.
Passing evidence is only:

```text
matched = true
mismatch_count = 0
```

Replay performs no Provider call, Market latest/current query, source
replacement, Decision-reference recomputation, repair or Authority mutation.
Corrupt persisted shapes are translated into typed integrity mismatches rather
than escaping as an unclassified reconstruction exception.

The permanent public package exports only `OutcomeReadPort` and immutable
`OutcomeSnapshot`. Exact revision, request and current-leaf reads return the
complete nested immutable root/revision/observation/metric/reason authority.
No PostgreSQL session, Market repository, Provider client, calculator, writer or
mutation method is exposed. WP-10 wires no downstream consumer.

## 12. Disposable PostgreSQL proof

Every target database command and PostgreSQL test used the newly created
disposable database only:

```text
host/runtime             local Homebrew PostgreSQL 16.14
database                 mra_wp10_gate_20260831_b
database OID             418574993
database/schema owner    yuan
schema                   mra
Artifact root            /tmp/mra-wp10-gate-artifacts-20260831-b
initial recreate plan    /tmp/mra-wp10-recreate-plan-20260831-b.json
initial plan hash        c6248162275163a6332437e072189dcdbc67bfadd338043c19c7259ef5912a9d
initial challenge        7d18c2a04cf0984cf1ce3133
final recreate plan      /tmp/mra-wp10-recreate-plan-20260831-b-final.json
final plan hash          fb21e9f6f7517f8a31043a04dbedca8286a31a1b64a9159e200c9e9d1420b71f
final challenge          4f338822fd61c1ee17096e2e
operator                 codex-wp10-gate
reason                   WP10_FINAL_DISPOSABLE_SCHEMA_RECREATE_VERIFICATION
backup attestation       DISPOSABLE_TEST_DATABASE_NO_BACKUP_REQUIRED
active client PIDs       [] at both plan times
unexpected objects       [] at both plan times
```

Clean bootstrap, verify-only retry, exact name/OID/owner/zero-client guarded
recreate and post-recreate verification passed before the test gate. The full
repository fixture teardown intentionally left `mra` absent; the final
post-suite bootstrap returned `created=true`, then a second guarded recreate
and verify rebuilt the identical 56-table catalog and all four checksums. No
Legacy, business, proof, historical, unknown or default database was treated as
target Authority or modified.

## 13. Validation ledger

Execution environment:

```text
OS          Darwin 25.5.0 arm64 / macOS 26.5.2
uv          0.11.7
Python      3.12.2
PostgreSQL  16.14 Homebrew arm64
timezone    Asia/Shanghai
ledger time UTC
```

All Python commands used the frozen `uv run` environment. Database tests used
`MARKET_REGIME_ALPHA_TEST_DATABASE_URL=postgresql://localhost/mra_wp10_gate_20260831_b`;
schema commands used the same database through `MRA_DATABASE_URL` and the
Artifact root above.

| Command / check | UTC interval | Result | Evidence |
|---|---|---|---|
| `uv sync --frozen --extra dev --extra postgres` | 01:41:10Z | **PASS** | exit 0; 61 locked packages checked |
| empty `mra db bootstrap` + `mra db verify` | 01:41:18Z–01:41:19Z | **PASS** | `created=true`; exact 56-table draft/checksums |
| `mra db recreate-plan` | 01:41:29Z–01:41:30Z | **PASS** | exact name/OID/owner, zero clients, no unexpected objects |
| `mra db recreate-apply` + verify | 01:41:41Z–01:41:42Z | **PASS** | only disposable `mra` removed/rebuilt; checksums stable |
| WP-10 focused six-file set | 01:41:50Z–01:42:07Z | **PASS** | 43/43: Application 7, architecture 5, kernel 9, Legacy characterization 1, PostgreSQL 17, schema 4 |
| `pytest -q tests/refoundation` | 01:42:38Z–01:44:59Z | **PASS** | 392/392 |
| `ruff check .` | 01:43:18Z–01:43:19Z | **PASS** | all checks passed |
| `mypy` | 01:43:18Z–01:43:19Z | **PASS** | no issues in 518 source files |
| `git diff --check` | 01:43:18Z–01:43:19Z | **PASS** | no whitespace error |
| `python -m build --outdir /tmp/mra-wp10-build-20260831-b` | 01:43:27Z–01:43:38Z | **PASS** | wheel and sdist built |
| `pytest -q tests/platform` | 01:45:08Z–01:45:17Z | **PASS** | 33/33 |
| `pytest -q tests/persistence/postgres` | 01:45:23Z–01:53:18Z | **PASS** | 286/286 |
| `pytest -q` with explicit disposable DB URL | 01:53:25Z–02:20:45Z | **PASS** | complete 3,432/3,432 repository nodes |
| architecture/import suite | 02:21:00Z–02:21:09Z | **PASS** | 60/60 across application, architecture, platform and all target owners |
| representative Outcome `EXPLAIN (ANALYZE)` | 02:21:16Z–02:21:18Z | **PASS** | declared owner indexes execute for root/replay/source plans |
| `scripts/check_docs_links.py` | 02:21:26Z–02:21:32Z | **PASS** | canonical inventory, metadata and links OK |
| docs navigation tests | 02:21:26Z–02:21:32Z | **PASS** | 7/7 |
| post-suite empty bootstrap + verify | 02:22:10Z–02:22:11Z | **PASS** | `created=true`; identical catalog/checksums |
| final `mra db recreate-plan` | 02:22:18Z–02:22:19Z | **PASS** | exact OID, zero clients, no unexpected objects |
| final `mra db recreate-apply` + verify | 02:22:28Z–02:22:29Z | **PASS** | identical 56-table catalog/checksums |
| `gh api repos/yuan2go/market-regime-alpha/actions/permissions` | 02:28:55Z–02:28:56Z | **BLOCKED_BY_REPOSITORY_CONFIGURATION / NOT_RUN** | read-only query exit 0 returned `enabled=false`; no workflow could run or was reported PASS |
| final docs inventory/static/diff gate | after containing documentation checkpoint | **PASS only if reported by final handoff** | this immutable record does not pre-claim its own containing commit |

Collection-only checks independently confirmed 43 focused, 392 refoundation,
33 platform, 286 PostgreSQL persistence and 3,432 complete repository nodes. No
test was filtered, skipped, xfailed, deleted or weakened to obtain the full
gate.

Build outputs were:

```text
wheel  e2dd35d1a82b1cad9eb8a54a3d7a432c6504b8e63ebd605798f44a9ffd3b1203
sdist  d86815a6b10bd4e0e1e1c8efdf0198bc2149690fd30f61a6e34a5a069a78ea50
```

The outputs are under `/tmp`, are reproducible, and were not committed.

## 14. Investigated non-final failures and superseded attempts

No failure, interruption or unavailable remote gate was hidden or promoted to
PASS:

| Attempt | Classification | Root cause and correction/disposition |
|---|---|---|
| first Domain/Application/PostgreSQL cases | **FAIL (TDD RED)** | Outcome API, kernel and eight relations did not yet exist; implementation followed the committed RED contracts |
| intrabar ambiguity roll-up | **FAIL (TDD SEMANTIC)** | partial-but-observed ambiguity incorrectly rolled availability to unavailable; Domain and DDL now preserve `PARTIAL + AVAILABLE + UNKNOWN` |
| calculated-fact construction | **FAIL (TDD INVARIANT)** | typed fact DTOs initially accepted impossible status/value/finality shapes; constructors now reject them before persistence |
| corrupted-row replay | **FAIL (VERIFIER CLASSIFICATION)** | stronger Domain validation surfaced a raw `ValueError`; PostgreSQL reconstruction now wraps corruption as `OutcomeAuthorityIntegrityError` and verifier emits typed mismatches |
| first complete refoundation run | **FAIL (ARCHITECTURE GUARD)** | an Outcome provenance FK reused a Market-specific `*_capture_product_fk` naming pattern; renamed to Outcome-owned observation/Session provenance FKs and full 392-node rerun passed |
| source role closure review | **FAIL (FINAL REVIEW)** | source roles were string-derived rather than a closed Domain vocabulary; `OutcomeSourceRole` now owns `CALENDAR_SESSION`/`OUTCOME_OBSERVATION`, repository mapping and schema vocabulary; exact implementation gate reran after the correction |
| `mra db identity` probe | **FAIL (READ-ONLY HARNESS)** | the CLI intentionally has no identity subcommand; exact identity was read through PostgreSQL/SchemaManager and guarded recreate instead; no mutation occurred |
| first final database and persistence attempt | **CANCELLED_SUPERSEDED** | it was bound to implementation `fd32f80`; source-role review advanced the checkpoint, so the old disposable DB evidence and an in-progress persistence run were discarded, not reported PASS; all gates reran at `56812c58` |
| repository fixture teardown | **EXPECTED FAIL-CLOSED STATE** | full pytest removed target `mra`; final clean bootstrap returned `created=true`, then verify/recreate proved the identical catalog |

## 15. Historical Verification immutability

WP-10 did not rewrite historical Verification bytes:

```text
WP-02  4daf0f3a3a402f8284cfe1a4ba87b37a8ca3ea0f83bbacb347a7d9debe7d1a2d
WP-03  3b5be2afa013f2639b618cb36fc3c8896d3ad1b67c47a57242c40d8724986e59
WP-04  6a8aedda78a6246a64b26335a6506315f30322c948e181b90760d73b473103a4
WP-05  990dd4f9dfbed7d1bd941301290f6ee7eb8a0b9c737efc653fa55821aa719caf
WP-06  59d7bd856eb874dc9e7a1c1f696e86f446facf3a8bd845b09e7b1cfe2bc4746c
WP-07  84dba3b18079ad54bfec0ff0a1be78b03cad136e921c08fd2d56f48d52f37d95
WP-09  2ad5eae3f6e9161c4b031ecb026b79451cd0720b4feaf0bfac90387003af5dad
```

## 16. Exit Gate, absent capabilities, and evidence ceiling

The WP-10 Exit Gate passes because the exact implementation proves one
Commitment/one stable Outcome root, append-only full revisions, exact
supersession/one leaf, direct reuse of the frozen WP-09 Decision reference,
relational exact source/observation/metric/reason rosters, concrete
`REFERENCE`/`OBSERVATION`/`PATH_MEMBER` dependencies, two independent cutoffs,
`NOT_DUE` zero-write semantics, correct partial/complete/unavailable/failed
states, independent availability/finality/value state, one pure Decimal kernel,
exact idempotency, non-forking concurrency, failure atomicity, recovery,
read-only exact replay/reconciliation with zero mismatches, a narrow permanent
read-only port, and absence of a second target bars-to-label writer.

The implementation and target catalog explicitly contain none of:

```text
ResearchPartition / Experiment / Evaluation / Evidence / ResearchAssessment
ResearchQualification / Model / ModelVersion / Calibration
Context / Signal / Forecast / Opportunity / Thesis / Strategy
Portfolio / Risk / Execution / Fill / Position / TradeOutcome / Attribution
Forecast binding / Qualification binding / generic outcome registry
nullable future FK / compatibility facade / future-stage placeholder
Legacy runtime dependency / dual write / Runtime or CLI cutover
```

Legacy Outcome consumers remain unchanged and canonical only until their own
future cut; none consumes the new port yet. The target epoch remains mutable,
unreleased and test-only. Current local fixture facts and SourceGaps do not
prove real Provider coverage, finality, Formal PIT or historical availability.
No Partition/access ledger exists, so no Formal OOS or Prospective eligibility
can be inferred. No empirical Alpha value, qualification, broker correctness,
trading performance, operational cutover or Production readiness is proved.

The next independent work package is **WP-11 Research Partition + Experiment**.
This record stops before it and grants no authority to start Evaluation,
Qualification, Context, Prospective campaign, Runtime/CLI Cutover, Legacy
deletion, or any other later capability.
