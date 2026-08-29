# System and Runtime Architecture

> **Status:** CANONICAL_TARGET_ARCHITECTURE
> **Authority:** Target Application, Runtime, concurrency, recovery, and interface specification
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-29
> **Implementation State:** `FOUNDATION_AND_MARKET_IMPLEMENTED_DRAFT / REMAINDER_DESIGN_ONLY / NOT_CUT_OVER`
> **Code Evidence:** target `src/market_regime_alpha/runtime`, `src/market_regime_alpha/market`, `src/market_regime_alpha/infrastructure`, `src/market_regime_alpha/interfaces`, `tests/refoundation`; legacy Runtime remains current business implementation

This is the target specification. Its Foundation Runtime and test-only
Market/PIT vertical slice are implemented in the mutable target draft, but have
not cut over the current business entry points. The current nested
Continuous/Controlled/Lifecycle/State/Historical journals are still to be
replaced by one Runtime journal. Business owners remain in their bounded
contexts.

## 1. Application versus Runtime

Application services perform one business use case. Runtime schedules and
coordinates those services; it does not reimplement their rules.

| Layer | Owns | Does not own |
|---|---|---|
| Domain | aggregates, value objects, state transitions, invariant failures | SQL, retries, clocks, providers, artifacts, logging |
| Application | command/query orchestration, transaction boundary, port calls, authorization, result DTO | scheduling loops, adapter selection, table-level CRUD |
| Runtime | schedule, DAG, claim, lease, fence, retry, resume, recovery, trace | Candidate logic, PIT rules, Risk rules, Position math, qualification |
| Infrastructure | PostgreSQL transaction/repository/query adapters, providers, artifact store, telemetry | business choices or fallback policy |
| Interface | CLI parsing and read-only inspection presentation | direct SQL writes or composition |

Historical, replay, shadow, and prospective execution select different port
implementations at the composition root. They call the same commands and do not
fork Domain logic.

## 2. Composition root

`bootstrap.py` performs exactly these actions:

1. load and validate environment configuration;
2. connect and verify the exact schema epoch before resolving any writer;
3. construct PostgreSQL unit-of-work and query adapters;
4. construct artifact, Provider, clock, telemetry, and authorization adapters;
5. construct Application command/query handlers;
6. register the finite Runtime step catalog;
7. expose the small CLI command tree.

No import-time singleton opens a connection or chooses a Provider. No
Repository Factory exposes every repository to every caller. A handler receives
only the ports it needs.

## 3. Canonical Runtime aggregates

### Run

A Run freezes:

- `run_id`, `schedule_id`/revision, mode, requested time and Decision time;
- code SHA, resolved config artifact/hash, schema epoch;
- parent/original Run for replay where applicable;
- state, created/started/finished timestamps and terminal reason.

Closed Run states:

```text
QUEUED
  └─> RUNNING
        ├─> WAITING ─> RUNNING
        ├─> SUCCEEDED
        ├─> BLOCKED
        ├─> FAILED
        └─> CANCELLED
QUEUED ───────────────> CANCELLED
WAITING ──────────────> BLOCKED | FAILED | CANCELLED
```

`SUCCEEDED` means every required Step is `SUCCEEDED` or explicitly
`SKIPPED`. `BLOCKED` means a declared external/business prerequisite is absent
or denied. `FAILED` means an integrity defect, invariant breach, terminal
adapter failure, or exhausted safe retries. Cancellation is an explicit
operator command; it is not inferred from process death.

### Step

A Step is one logical DAG node within a Run. It freezes `step_key`,
implementation/version, required/optional status, ordinal, request hash, input
evidence hash, retry policy, and current fence.

Closed Step states:

```text
PENDING --dependencies satisfied--> READY
READY -----------------------------> CLAIMED
CLAIMED ----------------------------> RUNNING
CLAIMED/RUNNING --------------------> READY       (safe retry via terminal old Attempt)
RUNNING ----------------------------> WAITING     (external reconciliation or scheduled prerequisite)
RUNNING ----------------------------> SUCCEEDED
RUNNING ----------------------------> BLOCKED
RUNNING ----------------------------> FAILED
PENDING/READY/CLAIMED/RUNNING/WAITING -> CANCELLED
PENDING ----------------------------> SKIPPED     (declared optional branch only)
```

A Step never moves from a terminal state. A retry creates a new Attempt and
moves only a non-terminal Step back to `READY`. `SKIPPED` requires a frozen
branch rule and reason; an exception cannot be converted to `SKIPPED`.

### Attempt

An Attempt is one exclusive execution claim. It owns:

- `attempt_id`, `step_id`, monotonically increasing `attempt_no`;
- monotonically increasing `fence_token`;
- `lease_owner`, `lease_acquired_at`, `lease_until`, last heartbeat;
- state, error class/code, external-effect classification;
- started/finished times and result/receipt IDs.

Closed Attempt states:

```text
CLAIMED -> RUNNING
CLAIMED -> ABANDONED
RUNNING -> SUCCEEDED
RUNNING -> FAILED_RETRYABLE
RUNNING -> FAILED_TERMINAL
RUNNING -> ABANDONED
RUNNING -> RECONCILIATION_REQUIRED
```

All terminal Attempt states are immutable. `RECONCILIATION_REQUIRED` means an
external effect may have occurred but cannot be proven; it is never an automatic
retry signal.

## 4. Claim, lease, fence, and heartbeat

Claim is one short PostgreSQL transaction:

1. select one `READY` Step whose Run is runnable and dependencies are satisfied,
   using `FOR UPDATE SKIP LOCKED`;
2. lock its Run and Step;
3. reject a non-expired current claim;
4. increment the Step's fence token;
5. create an Attempt with `attempt_no = prior + 1` and database-clock lease;
6. set Step to `CLAIMED` and commit.

Only PostgreSQL `clock_timestamp()` determines lease expiry. Worker clocks are
diagnostic. A heartbeat updates the lease only when all of these match:

- Attempt is current and non-terminal;
- Step's current Attempt and fence match;
- lease owner matches;
- prior lease has not expired;
- Run is `RUNNING`.

Finalization repeats those predicates under lock. Every business write performed
on behalf of a Step carries `step_id` and `fence_token`; its repository validates
the live fence in the same transaction. A stale worker may finish computation or
upload bytes, but cannot commit a business fact, receipt, or Step state.

Lease duration exceeds the expected local transaction duration, not the total
remote job duration. Long computation heartbeats between bounded operations.
External I/O never occurs while database locks are held.

## 5. Retry and error classification

Retry policy is frozen into the Run config artifact and copied to the Step:
maximum attempts, backoff sequence, retryable codes, and deadline. Code cannot
invent a new retry class at runtime.

| Failure | Attempt terminal state | Step result | Automatic action |
|---|---|---|---|
| deterministic Domain rejection | `FAILED_TERMINAL` | `BLOCKED` or `FAILED` by declared code | none |
| integrity/hash/schema/fence conflict | `FAILED_TERMINAL` | `FAILED` | none |
| known no-effect transient adapter error | `FAILED_RETRYABLE` | `READY` if budget remains | new Attempt after backoff |
| lease expiry before any external effect | `ABANDONED` | `READY` if budget remains | new Attempt |
| external effect known committed with receipt | `SUCCEEDED` | `SUCCEEDED` | reuse receipt |
| external effect outcome unknown | `RECONCILIATION_REQUIRED` | `WAITING` | explicit reconciliation |
| retry budget/deadline exhausted | final retry state retained | `FAILED` | none |

Retry never edits or reopens an old Attempt. Backoff is scheduling metadata; no
database transaction sleeps.

## 6. Idempotency

Every mutating Application command has:

- caller-supplied or deterministically derived `idempotency_key`;
- canonical request hash after validation and secret removal;
- command kind and aggregate scope;
- terminal status, result aggregate/version, result hash, timestamps.

`command_receipt` enforces uniqueness on
`(command_kind, scope_id, idempotency_key)`.

- Exact request hash retry returns the original committed result.
- Same key with a different hash fails `IDEMPOTENCY_KEY_REUSED`.
- A pending receipt owned by another live fence cannot be taken over.
- A failed command is retryable only through its declared policy; changing input
  requires a new key.
- Provider captures and artifact uploads deduplicate by content hash but still
  receive distinct capture/command identities when business events differ.
- A future broker request additionally uses the broker's idempotency identifier;
  absence of deterministic outcome routes to reconciliation.

Business fact, exact input/dependency links, terminal command receipt, audit
event, and Runtime Step finalization commit in one transaction whenever the
business effect is relational. There is no “write fact then best-effort mark
done” path.

Each business context owns a narrow unit of work. Selection receives only its
aggregate repository, a read-only Market/PIT query port, and the minimal
cross-cutting fence/receipt/audit/finalization ports. It does not extend or
import the Runtime UoW, Market UoW, a Market PostgreSQL repository, Legacy
Universe, State System, Candidate, or compatibility persistence. When Runtime
participates, live-fence validation, Selection writes, receipt, audit, and Step
finalization share that one short Selection transaction.

## 7. Transaction and lock invariants

The global lock order is:

1. current Runtime Run/Step/Attempt when a Runtime fence participates;
2. Account and Account Authority Epoch;
3. Portfolio Proposal / Risk Decision;
4. Execution Intent;
5. Fill / Fill Allocation;
6. any other aggregate roots ordered by `(aggregate_kind, aggregate_id)`.

Immutable definitions and evidence are verified but not locked for mutation.
Every multi-root command follows this order. Repository methods do not start or
commit nested transactions.

Isolation defaults to `READ COMMITTED` with explicit row locks and uniqueness/
version predicates. Use `SERIALIZABLE` only for a measured invariant that cannot
be protected by scoped locks/constraints. Expected uniqueness races are handled
by insert-on-conflict plus exact re-read; unexpected constraint violations fail
closed.

Database-enforced examples:

- one live Attempt per Step;
- monotonic Attempt number and fence;
- one command receipt per idempotency scope;
- immutable business identity and revision uniqueness;
- non-negative quantities and legal OHLC;
- exactly one qualification subject/purpose;
- Fill correction links and allocation totals;
- allowed lifecycle transitions through guarded repository statements.

## 8. Crash recovery invariants

| Crash point | Durable state | Recovery |
|---|---|---|
| before claim commit | no Attempt/effect | another worker claims |
| after claim, before work | live/expired lease only | heartbeat or expiry → old Attempt `ABANDONED` → new Attempt |
| during pure computation | no business effect | same as above |
| after artifact publish, before PostgreSQL commit | content-addressed orphan bytes | retry may reuse exact hash; GC later quarantines if unreferenced |
| after remote side effect, before its receipt is proven | Attempt cannot prove outcome | `RECONCILIATION_REQUIRED`; never blind retry |
| after relational business commit | command receipt and Step terminal in same commit | retry reads original receipt; no redispatch |
| after response serialization | committed result exists | caller retries same key and receives original result |
| during heartbeat/finalization race | fence/version predicate selects one winner | stale worker rejected; no partial fact |

Recovery scans expired non-terminal Attempts. It never changes completed
business facts, advances Decision-time visibility, substitutes a Provider,
rebuilds an immutable input with “latest,” or opens terminal blocked work without
a new explicit command/evidence condition.

## 9. Resume, replay, and deterministic comparison

`resume` operates on the same Run:

- retains code/config/input identities;
- leaves successful/skipped Steps untouched;
- claims only `READY` work or work made ready by a resolved prerequisite;
- creates new Attempts with higher fences;
- never converts `BLOCKED`/`FAILED` to success without an explicit resolution
  command recorded in audit.

`replay` creates a new Run that references the original. It reloads exact
captures, facts, Universe revision, policies, definitions, artifacts, and
Decision times. It cannot call a replacement Provider or rewrite original rows.
Pure outputs are recomputed and compared by canonical status, value, identity,
hash, and lineage. Replay succeeds only with a terminal report containing
`matched=true` and zero mismatches; process completion or row counts are not
proof.

Historical execution is a Run over ordered owner-resolved trading sessions.
Session order comes only from `trading_session`, never weekday arithmetic.
Prospective execution cannot read evidence captured after its Decision time.

## 10. External effects

Adapters classify operations before dispatch:

- `PURE_READ`: safe to repeat, but every returned capture has a new observed
  capture time unless exact bytes are reused as a replay input;
- `CONTENT_PUT`: idempotent by hash and verified after write;
- `IDEMPOTENT_REMOTE_COMMAND`: requires remote idempotency and status query;
- `NON_IDEMPOTENT_REMOTE_COMMAND`: forbidden from unattended Runtime;
- `OBSERVATION_ONLY`: broker/provider observation cannot mutate Position.

No broker writer is part of this target checkpoint. If introduced later, it
must implement remote receipt lookup and reconciliation before Production
admission.

## 11. Commands and queries

Representative commands:

- `CaptureMarketData`, `NormalizeMarketFacts`, `FreezeUniverse`,
  `AssessEligibility`; later, after Research definitions, `BuildCandidateSet`;
- `AssessContext`, `ProduceSignal`, `ProduceForecast`,
  `CreateOpportunity`, `ProposePortfolio`, `AssessRisk`;
- `ApproveExecutionIntent`, `RecordObservedFill`, `CorrectFill`,
  `RecordBrokerObservation`, `ReconcileAccount`;
- `SettleOutcome`, `RunAttribution`, `AssessResearchClaim`,
  `DecideQualification`;
- `ScheduleRun`, `ClaimStep`, `HeartbeatAttempt`, `ResumeRun`,
  `ResolveExternalEffect`, `VerifyArtifact`.

The command dependency is one-way:
`FreezeUniverse → AssessEligibility → BuildCandidateSet → AssessContext`.
Same-run Context cannot mutate or filter the already frozen Universe,
Eligibility, or Candidate Set. `CreateOpportunity` carries no Risk
authorization; only `AssessRisk` after `ProposePortfolio` creates a Risk
Decision. The current Selection Core Runtime slice stops after
`ASSESS_ELIGIBILITY`; it does not create a Candidate or Decision fact.

Representative queries:

- exact/as-of Market facts and source lineage;
- Selection Universe/Eligibility dossier at Decision time; later Candidate
  dossier after Candidate closure;
- Decision dossier from Candidate through Risk;
- current Position and Strategy sleeve projection;
- Outcome/metric availability;
- evidence graph and qualification-floor matrix;
- Run trace, stuck leases, artifact integrity, and reconciliation differences.

Query handlers use dedicated SQL/read DTOs. They do not hydrate large write
aggregates or acquire write locks.

## 12. Interface behavior

CLI commands:

- validate schema epoch before handler construction;
- print stable IDs and machine-readable terminal status;
- return non-zero for `FAILED`, schema/integrity mismatch, or unsafe command;
- distinguish valid `BLOCKED`/`NOT_ESTIMABLE`/`NO_ACTION` outcomes from
  process failure;
- never display secrets or infer proof from a successful exit;
- require an explicit operator identity and reason for destructive recreate,
  reconciliation adjustment, cancellation, and qualification decisions.

Inspection commands are read-only and safe against a mismatched schema: they
report the mismatch without attempting migration.

## 13. Architecture verification

Required target tests include:

- import/dependency graph and sole composition-root checks;
- Run/Step/Attempt transition tables and property tests;
- concurrent claim proves one live fence;
- expired lease rejects stale finalization;
- exact command retry returns one fact/receipt;
- reused key with altered request fails;
- crash-point recovery matrix;
- unknown external effect cannot auto-retry;
- resume preserves successful identity;
- replay requires exact zero-mismatch terminal evidence;
- lock-order contention completes without deadlock;
- empty PostgreSQL bootstrap and mismatched epoch fail-fast;
- CLI smoke from capture through outcome/evidence.

The current tests are not classified for deletion until their Domain invariants
are mapped in the checkpoint catalog.
