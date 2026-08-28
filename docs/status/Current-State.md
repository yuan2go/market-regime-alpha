# Current State

> **Status:** CURRENT_STATUS
> **Authority:** Non-authoritative exact-SHA implementation read model
> **Owner:** Market Regime Alpha maintainers
> **Generated At:** 2026-08-28T23:17:40Z
> **Repository SHA:** `db206933b9c243bb65d2f85748d0e968b42497b0`
> **Implementation Line Start:** `c3ac21ef1e13f2e8408d30b0481fa9b74c4f9539`
> **Foundation Source Checkpoint:** `eeff49c7a3995ba6d65045be88d4244617301234`
> **Legacy Business Implementation Parent:** `0382dad416d6d50d1eea0bda1603d7c359d65274`
> **Schema Epochs:** canonical business `LEGACY_MIGRATIONS_001_106`; target draft `MRA_REFOUNDATION_1 / DRAFT / NOT_CUT_OVER`
> **Generator:** `WP-04 Market/PIT audit with CLAUDE governance follow-up`
> **Source Tree IDs:** source `3a8e9f062861f90d26a21c85835021386b662c8e`; legacy migrations `6d3730548780ad6244d2cfecb4fb3559064b6f06`; target baseline `b1d64d2525ee9be7aa1f32861796f148c62095a9`; tests `dc13df166600eae6be1f97d1c90ac35f2ce97308`
> **Code Evidence:** target and legacy source/migration packages plus `tests`

This snapshot is invalid after any source, migration, test, or composition
change until regenerated. It reports implementation and local engineering
verification only; it cannot write business state or promote Provider,
research, qualification, trading, or Production claims.

## Current implementation truth

| Area | Exact current fact at the snapshot SHA |
|---|---|
| Package shape | The legacy Python 3.12 modular monolith remains intact. Target `shared`, `runtime`, `market`, `infrastructure`, `interfaces`, and sole target `bootstrap.py` are isolated by dependency tests |
| PostgreSQL | The canonical business implementation remains legacy 001–106 with 283 tables. The target draft has 25 relations and two read-only views under schema `mra` |
| Runtime | Continuous Research remains the current all-day business control plane. Target Run/Step/Attempt can execute a test-only `CAPTURE -> NORMALIZE_PIT` slice; it is not a canonical entry point |
| CLI | Six legacy scripts remain. `mra` exposes target DB bootstrap/verify/recreate and Runtime inspection/recovery, but no Market business cutover command |
| Market/PIT | A target owner now exists with Domain/Application/Ports, narrow Market UoW, PostgreSQL writer/query adapters, Tencent and BaoStock exploratory adapters, exact/as-of queries, and Artifact lineage |
| Universe/Candidate | Current legacy capabilities remain; target convergence has not started |
| Research/Qualification | Current legacy capabilities remain. No target Research owner or Provider/PIT qualification/admission framework exists |
| Decision/Outcome | Current legacy capabilities remain; target single write paths have not started |
| Execution/Account | Human/manual execution only; observed effective Fill remains the source of trade-caused Position. No target implementation was added |
| Target epoch | Foundation plus Market/PIT are implemented in the mutable `MRA_REFOUNDATION_1` draft; every later target context and Runtime/CLI Cutover remain absent |
| Legacy | Old source, 001–106 migrations, CLIs, compatibility paths, and tests remain physically present as the current implementation and regression oracle |

The convergence state is therefore
`FOUNDATION_MERGED_AND_MARKET_IMPLEMENTED_DRAFT / NOT_CUT_OVER`. Similar legacy
vocabulary does not make an old owner part of the target, and target test writes
do not become canonical business writes.

## Target draft catalog

Foundation retains its 13 relations:
`schema_epoch`, `schema_migrations`, `command_receipt`, `runtime_schedule`,
`runtime_run`, `runtime_step`, `runtime_step_dependency`, `runtime_attempt`,
`audit_event`, `artifact`, `artifact_dependency`, `artifact_verification`, and
`artifact_gc_candidate`.

Market/PIT adds exactly the approved 12 relations:
`provider`, `provider_product`, `data_capture`, `instrument`,
`instrument_identifier`, `trading_session`, `classification`,
`classification_membership_revision`, `market_bar_revision`,
`instrument_fact_revision`, `corporate_action_revision`, and `source_gap`.

The two views remain `run_trace` and `artifact_integrity_status`. The verified
draft catalog contains 126 indexes, 322 constraints, 22 functions, and 67
non-internal triggers. Table count is descriptive, not an optimization target.

## Market/PIT implementation truth

- Provider network I/O and content-addressed byte publication/verification run
  outside PostgreSQL transactions.
- One short Market UoW first locks and validates a participating Runtime claim,
  then atomically owns the business facts, command receipt, audit event, and
  matching Runtime Step finalization.
  A stale fence rolls all relational writes back; published bytes remain a
  discoverable, two-pass-GC orphan.
- `data_capture` keeps provider, source-availability, capture, PostgreSQL
  recording, knowledge, and Decision-visible time distinct. PostgreSQL enforces
  `known_at = greatest(capture_completed_at, recorded_at)` and, for the current
  unqualified products, `decision_visible_at = known_at`.
- Tencent preserves exact GB18030 response bytes. BaoStock preserves a
  deterministic captured representation and
  `HISTORICAL_AVAILABLE_TIME_NOT_PROVIDED`. Neither adapter can exceed
  `EXPLORATORY_UNQUALIFIED`.
- Raw, forward-adjusted, and backward-adjusted bars are separate series using
  `numeric`/`Decimal`. Revisions are append-only; owner queries select exact
  as-of facts without caller-controlled “latest.”
- Missing, placeholder, provider failure, conflict, and invalid OHLC are typed
  gaps. A placeholder creates no valid bar. Missing/zero-volume/flat-price do
  not infer suspension.
- The Decision reference is only the exact same-session Raw five-minute bar
  ending 14:55. Daily or previous-session prices cannot substitute; current-
  session typed suspension is distinct from prior-session status.
- `data_capture` is a canonical Artifact reference and therefore protects its
  bytes from orphan classification and garbage collection. Authoritative reads
  require an AVAILABLE physical hash/size verification no older than 24 hours;
  stale evidence blocks until an explicit outside-transaction verification is
  committed.

## Exact-SHA verification

The immutable pre-refoundation ledger is
[WP-02](../references/WP-ARCHITECTURE-REFOUNDATION-02-Pre-Refoundation-Verification-Baseline.md),
the Foundation ledger is [WP-03](../references/WP-ARCHITECTURE-REFOUNDATION-03-Foundation-Verification.md),
and the current results, including every failed attempt, are recorded in
[WP-04](../references/WP-ARCHITECTURE-REFOUNDATION-04-Market-PIT-Verification.md).

At Market/PIT source checkpoint
`e7a276a30f71a98b6b32580fa0a4840c2e269b9f`, all 3,175 collected tests pass
through exhaustive resource-bounded batches on a repeatedly recreated isolated
PostgreSQL 16 database. All 136 target tests, including 69 Market tests and
focused Foundation/PostgreSQL/runtime/artifact/architecture tests,
documentation checks, Ruff, mypy, build, and diff checks pass. The unchanged
legacy 001–106 bootstrap and schema tests pass. Remote CI was not executed and
is `NOT_RUN`.

The monolithic local `pytest -q` attempt is not reported as PASS: it exhausted
the host filesystem after repeated 283-table test-schema churn and caused a
PostgreSQL recovery cycle. The complete 3,175-node collection subsequently
passed in five disjoint batches with an explicit database recreate between
batches; no assertion, skip, or xfail changed.

The earlier governance-fix checkpoint separately established that:

- the complete repository gate catalogs in `AGENTS.md` and `README.md` execute
  every Python command through `uv run`;
- `CLAUDE.md` delegates to that authoritative gate without copying the command
  list, states the non-activation boundary, and joins both catalogs in the
  regression test that rejects bare `python` across all three entry points;
- the clean, non-activated shell resolves bare `python` to pyenv 3.12.13 while
  `uv run python` resolves to the worktree `.venv` on Python 3.12.2 with the
  frozen lock's Ruff 0.16.1, mypy 2.3.0, and pytest 9.1.1;
- the fresh-PostgreSQL full regression passes with 3,101 tests collected on
  PostgreSQL 16.14 in a disposable loopback-only cluster and new database OID
  `515555`;
- all 61 target Foundation tests, documentation checks, 33 platform tests,
  focused legacy replay/recovery/concurrency tests, Ruff, mypy over 451 source
  files, build, and diff checks pass;
- the legacy 001→106 bootstrap/schema checks still pass without modification;
- a clean database proves missing-schema fail-closed, explicit bootstrap,
  idempotent retry, exact checksum/catalog verification, and guarded recreate.

One non-final host-database run was stopped at 58% after catalog autovacuum and
schema teardown exhausted the host lock table while only 637 MiB of disk
remained. Its exact disposable database was removed. The unchanged command then
passed at 100% in the isolated cluster with `max_locks_per_transaction=256`, one
autovacuum worker, and a 4 GiB RAM volume; no assertion, skip, migration, source,
or test order was changed. GitHub Actions remain disabled, so remote CI is
`BLOCKED_BY_REPOSITORY_CONFIGURATION / NOT_RUN`, not PASS.

At the current governance checkpoint, the documentation inventory/link checker,
seven link-checker tests, three reproducible-environment tests, focused Ruff,
and diff check pass. The full 3,175-test engineering suite, PostgreSQL tests,
mypy, build, and every Market/research backtest are `NOT_RUN` at this follow-up.

The current follow-up leaves the WP-04 source, legacy-migration, and target-
baseline tree IDs unchanged. Foundation and Market/PIT therefore retain their
recorded exit states without rollback or capability promotion. This follow-up
does not prove Provider, Alpha/OOS, broker, trading, Prospective, Production, or
Runtime/CLI Cutover evidence, and none of those evidence classes were rerun.

## Research and production ceiling

```text
target_release_state = DRAFT
runtime_cli_cut_over = false
provider_qualification_established = false
formal_pit_established = false
formal_oos_alpha_supported = false
entry_model_empirically_validated = false
broker_integration_proven = false
automatic_order_execution = false
sustained_prospective_value_proven = false
production_ready = false
```

## Refresh contract

A future Current State must obtain facts read-only from Git identity, the
configured schema epoch/migration registry, code-owned inventories, executed
test receipts, and canonical Evidence IDs/hashes. It receives no database write
credentials and cannot infer “current” from filenames, latest rows, documents,
or Artifact directories.
