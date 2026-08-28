# WP-ARCHITECTURE-REFOUNDATION-04 Market/PIT Verification

> **Status:** CURRENT_STATUS
> **Authority:** Exact-SHA local engineering verification record; not business, evidence, Provider qualification, Runtime, or Production Authority
> **Owner:** Market Regime Alpha maintainers
> **Executed At:** 2026-08-29
> **Source Checkpoint:** `e7a276a30f71a98b6b32580fa0a4840c2e269b9f`
> **Implementation Line Start:** `c3ac21ef1e13f2e8408d30b0481fa9b74c4f9539`
> **Foundation Source Checkpoint:** `eeff49c7a3995ba6d65045be88d4244617301234`
> **Code Evidence:** isolated target Market/Foundation source and tests; unchanged legacy source and 001–106 migrations

This record proves only the target Market/PIT draft slice. It does not release
the mutable baseline, cut over the canonical Runtime, establish formal PIT or
Provider qualification, or implement Universe, Research, Decision, Execution,
broker, Prospective, or Production capability.

## Verified draft catalog

```text
schema               mra
epoch                MRA_REFOUNDATION_1
release_state        DRAFT
baseline_version     1
baseline_checksum    30b3371c5db2bd9682d7c519fb3ceb9c9d85c6c106fb927e1b4d077f846f09bd
seed_checksum        9c41cd715e35e1a7bed3a58c52a29f01cc1e9bf950b77344bb56eac6dfa2df11
vocabulary_checksum  f16d4629a62afcb559f9e9dac77634fe91e43b21f3c2cd14eaa9c2a41311c132
catalog_checksum     88cbcb014e7fc498d3b25e5cc45c36e7ccac7e7c331be95265ea11dbe0a4cbb8
tables               25
views                2
indexes              126
constraints          322
functions            22
triggers              67
```

The 13 Foundation relations remain unchanged in responsibility. Market/PIT
adds `provider`, `provider_product`, `data_capture`, `instrument`,
`instrument_identifier`, `trading_session`, `classification`,
`classification_membership_revision`, `market_bar_revision`,
`instrument_fact_revision`, `corporate_action_revision`, and `source_gap`.

Any previous target test database carries the old checksum and must be
explicitly recreated. Normal startup is verify-only and rejects missing schema,
legacy/wrong epoch, checksum drift, and unexpected objects. The release state
remains `DRAFT`; there is no temporary upgrade migration.

## Authority and transaction seam

`market/domain` owns typed values and invariants. `market/application` owns
commands. `market/ports` exposes the Market owner plus only Artifact metadata,
command receipt, audit, and live Runtime finalization. PostgreSQL and Provider
implementations live under `infrastructure`; `bootstrap.py` is the only target
composition root.

```text
Provider network call
-> exact byte publish and hash/size verification
-> short PostgresMarketUnitOfWork
   -> lock current Run/Step/Attempt; validate live lease/fence when present
   -> idempotency receipt check or exact replay
   -> immutable dependency verification
   -> Market aggregate locks in global order
   -> Market write
   -> command receipt
   -> audit event
   -> matching Runtime Step/Attempt finalization
-> commit
```

Provider and Artifact byte I/O never run inside the relational transaction.
Repositories never commit, a Market UoW cannot be nested or reused, and no
RepositoryFactory, service locator, generic command bus, workflow framework,
registry framework, legacy adapter, dual write, or fallback was added.

## Temporal, revision, gap, and Provider proof

- `event`, `provider`, `source_available`, `capture_started`,
  `capture_completed`, PostgreSQL `recorded`, `known`, and `decision_visible`
  times are separate columns/values.
- The DB clock freezes
  `known_at = greatest(capture_completed_at, recorded_at)`. Current unqualified
  products enforce `decision_visible_at = known_at`.
- Provider-reported availability cannot follow `known_at`; Capture keys are a
  closed Domain/DDL value and reject invalid correlation identity before remote
  or Artifact I/O.
- `source_available_at` remains null with typed `UNKNOWN` when a Provider does
  not supply trustworthy historical availability. Retrieval time is never
  relabelled as source availability and no historical visibility backfill is
  available.
- Tencent stores exact non-empty GB18030 response bytes. BaoStock stores a
  deterministic JSON representation of the exact library result and retains
  `HISTORICAL_AVAILABLE_TIME_NOT_PROVIDED`.
- Both adapters are structurally capped at `EXPLORATORY_UNQUALIFIED`; there is
  no qualification, registry, or admission state in Market.
- Raw/unadjusted, forward-adjusted, and backward-adjusted are distinct logical
  series. Financial values cross the canonical boundary as bounded `Money` or
  `Quantity` values and are stored without rounding as PostgreSQL `numeric`.
- Revisions are append-only and predecessor-validated. Point/session identities
  retain exact event intervals; effective-state roots keep `effective_from` and
  the current revision may close `effective_to`. Exact/as-of owner queries first
  choose the current visible root and callers cannot request “latest.” A later
  visible same-lineage gap hides an older fact, while a later valid correction
  hides the older gap. A Product-local gap cannot poison another Product's
  selected global Session/Classification Authority.
- Missing, placeholder, Provider failure, conflict, and invalid OHLC are typed.
  Placeholder/null OHLC creates a gap, not a bar. Missing bars, zero volume, and
  flat price do not infer suspension.
- Security status binds either `DECISION_SESSION` or `PRIOR_SESSION`. Only a
  current-session typed suspension affects the Decision reference.
- The 14:55 reference accepts only the exact same-session
  `RAW_UNADJUSTED / MINUTE_5 / 14:50-14:55` valid bar. Daily and previous-session
  prices are prohibited as substitutes.

## Artifact and Runtime proof

`data_capture.artifact_id` is a canonical FK. Orphan scanning checks it along
with Foundation references before first observation, second-pass quarantine,
or delete. Hash/size/existence verification is required before capture binding
and before normalization reads. Authoritative reads require an AVAILABLE
verification within the frozen 24-hour cadence; stale evidence blocks until
`VerifyArtifact` performs byte I/O outside SQL and commits a new observation.
Exact verify retries use the caller key and replay the committed observation.

The test-only Runtime vertical slice completes `CAPTURE -> NORMALIZE_PIT` with
the same receipt/audit fence token as the successful Attempt. A worker whose
lease expired can finish Provider and CAS I/O but cannot commit a Capture,
Artifact row, receipt, audit, Market fact, or Step success. Its published bytes
remain an unbound, discoverable orphan eligible only for the existing grace and
two-pass GC protocol. Barrier tests also prove post-preflight races: an exact
winner is replayed and finalizes the slow Attempt; a changed request or
normalizer contract receives a separate fenced rejection without replacing the
winner; integrity observations remain durable even without a Runtime claim.

## Query-plan and index proof

Representative `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` calls execute the
exact/as-of bar, exchange/session-date, and classification-membership paths.
Tests verify the plans traverse the intended owner relations and finish, while
catalog inspection verifies the exact/as-of indexes for bar, session,
classification, membership, and identifier queries. Tiny fixtures may
legitimately choose sequential scans, so no node type, cost, timing, or planner
output is hard-coded as an invariant.

## Final validation ledger

| Check | Result | Evidence |
|---|---|---|
| frozen dependency/install sync | **PASS** | project, dev, and PostgreSQL extras resolve from `uv.lock` |
| documentation inventory/link checker | **PASS** | canonical inventory, metadata, links, and checker tests pass |
| Market/PIT focused tests | **PASS** | 69 tests |
| all target refoundation tests | **PASS** | 136 tests |
| legacy PostgreSQL 001→106 migrator/schema tests | **PASS** | unchanged bootstrap, verify, checksum, idempotency, and concurrency behavior |
| complete repository test collection | **PASS** | all 3,175 collected nodes pass in five disjoint resource-bounded batches on an explicitly recreated isolated PostgreSQL database |
| stale-fence/runtime/concurrency/idempotency/artifact selection | **PASS** | capture/finalization rollback, lease expiry, retry, idempotency conflict, corruption, canonical-reference protection, and orphan GC pass |
| target empty DB bootstrap/retry/verify | **PASS** | missing schema fails closed; bootstrap creates 25 tables; retry is idempotent; epoch, seed, baseline, vocabulary, and catalog checksums verify |
| target destructive recreate plan/apply | **PASS** | plan binds the exact database name/OID, owner, epoch, catalog, operator, and zero-other-connection state; injected catalog drift rejects the old plan with `RECREATE_PLAN_STALE`; an explicit replan/apply rebuilds and verifies the draft schema |
| representative query plans and index catalog | **PASS** | exact bar, session, classification/membership, and identifier access paths execute and required indexes exist |
| target architecture dependencies | **PASS** | target Market imports no old data/market_data/PIT/legacy/RepositoryFactory path; Domain remains infrastructure-free |
| Ruff | **PASS** | all checks passed |
| mypy | **PASS** | no issues in 463 source files |
| package build | **PASS** | sdist and wheel include target source, SQL/seed resources, providers, and `mra` entry point |
| final diff/worktree check | **PASS** | no whitespace errors; implementation worktree is clean after the checkpoint commit; the original worktree's pre-existing `.idea/modules.xml` modification remains untouched |
| Remote CI | **NOT_RUN** | no remote workflow was dispatched or observed for this local checkpoint |

## Investigated non-final attempts

Every failed command is retained rather than hidden:

| Attempt | Result | Root cause and disposition |
|---|---|---|
| first full suite with `postgresql:///mra_wp04_test` | **FAIL** | legacy settings require an explicit host; rerun used `postgresql://localhost/mra_wp04_test` |
| monolithic full suite with the corrected host URL | **FAIL** | repeated creation/deletion of the 283-table legacy schema exhausted the host filesystem at about 68%, causing PostgreSQL recovery and cascading temp failures; the exact disposable DB and this run's temp directory were removed |
| first resource-bounded application batch | **FAIL** | the invocation omitted `MARKET_REGIME_ALPHA_TEST_DATABASE_URL` and tests correctly failed closed; it was interrupted and rerun with the explicit URL |
| first final scripts/signals/strategies/universe batch | **FAIL** | documentation convergence had omitted the existing `entry_model_empirically_validated = false` proof ceiling; the invariant test caught it, the declaration was restored, and the complete batch passed on rerun |

The complete 3,175-node collection was then partitioned without overlap as
974 + 307 + 468 + 237 + 1,189. The exact database was recreated between batches
to reclaim PostgreSQL catalog space. No test, assertion, fixture meaning,
skip/xfail marker, or application behavior was relaxed.

## Exit boundary

Market/PIT is `GO` for its engineering exit gate and
`NO-GO` for canonical Runtime/CLI cutover, formal PIT, qualified Provider use,
or Production. Universe/Eligibility/Candidate is dependency-ready only if a
separate work package authorizes it; WP-04 stops here.
