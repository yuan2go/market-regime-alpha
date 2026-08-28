# Current State

> **Status:** CURRENT_STATUS
> **Authority:** Non-authoritative exact-SHA implementation read model
> **Owner:** Market Regime Alpha maintainers
> **Generated At:** 2026-08-28T15:24:02Z
> **Repository SHA:** `aeeabe684d5a775e195ecc593cbd37846bc67497`
> **Re-foundation Parent:** `6711331a781ccd483e9bbf9924cf6c0f697b0881`
> **Legacy Business Implementation Parent:** `0382dad416d6d50d1eea0bda1603d7c359d65274`
> **Schema Epochs:** canonical business `LEGACY_MIGRATIONS_001_106`; unpublished target draft `MRA_REFOUNDATION_1`
> **Generator:** `governance-fix WP-03-equivalent environment audit`
> **Source Tree IDs:** source `416b609041d3da6098d29245378a2c0100eed853`; legacy migrations `6d3730548780ad6244d2cfecb4fb3559064b6f06`; target baseline `6b9c746300457281ddcf9b6a6b4b474c6c55d892`; tests `c88d128b5483071d5d7e38ca2c5bc9263a6df59e`
> **Code Evidence:** unchanged target and legacy source/migration packages, repository gate entry points, and `tests`

This snapshot is invalid after any source, migration, test, or composition change
until regenerated. It can report implementation and validation facts; it cannot
write business state or promote research/Production qualification.

## Current implementation truth

| Area | Exact current fact at the snapshot SHA |
|---|---|
| Package shape | Existing Python 3.12 modular monolith remains intact. Isolated target `shared`, `runtime`, `infrastructure`, `interfaces`, and sole target `bootstrap.py` now exist and have architecture dependency tests |
| PostgreSQL | Canonical business implementation remains legacy 001–106 with 283 tables. The unpublished target package also has a draft 13-table Foundation baseline and two read-only views under schema `mra` |
| Runtime | Continuous Research remains the current all-day business control plane. A target Run/Step/Attempt kernel now exists on the unpublished line but has no Market or later business workflow and is not a canonical entry point |
| CLI | The six legacy scripts remain. Installed `mra` adds explicit target DB bootstrap/verify/recreate and Runtime inspect/recover operations, but is not cut over to business execution |
| Market/PIT | Public-provider capture, PIT/calendar, historical corpus, revisions, and gaps exist across several packages/tables; no target Market/PIT owner exists |
| Universe/Candidate | Current Universe, Eligibility, State/Candidate, daily and historical paths are implemented but not converged on the target aggregates |
| Research | Dataset/experiment/evaluation/evidence/qualification capability exists across campaign- and phase-specific owners; no target unified evidence model exists |
| Decision/Outcome | Signal, Forecast, Opportunity, Strategy, Portfolio, Risk, Outcome, and Attribution capabilities exist through multiple current paths; target single write paths do not exist |
| Execution/Account | Human/manual execution only; observed effective Fill drives trade-caused Position. No broker writer or unattended execution authority exists |
| Target epoch | Foundation slice implemented: `MRA_REFOUNDATION_1`, draft `001_baseline.sql`, checksum seed, catalog verification, `bootstrap.py`, and `mra`. The complete target baseline and all business contexts remain absent |
| Legacy | `daily_research`, `daily_decision`, `dividend_t`, `legacy/**`, `migration/legacy/**`, old migrations, and compatibility tests remain physically present |

The approved Target Architecture is therefore
`FOUNDATION_IMPLEMENTED_ON_UNPUBLISHED_LINE / NOT_CUT_OVER`. Foundation is
infrastructure and orchestration substrate, not a business bounded context.
Market/PIT and every later target capability remain `NOT_STARTED`; no current
class/table with similar vocabulary counts as convergence.

## Foundation implementation truth

The target Foundation owns only:

- epoch, packaged baseline/seed checksums, exact catalog fingerprinting, safe
  destructive-recreate authorization, and explicit operator DDL;
- command receipts and audit events;
- Runtime Schedule/Run/Step/Dependency/Attempt state, database-clock leases,
  fences, retries, resume/recovery, and application-owned unit-of-work scope;
- content-addressed local bytes plus relational Artifact metadata,
  verification, dependency, and two-phase garbage-collection state.

Its 13 relations are `schema_epoch`, `schema_migrations`, `command_receipt`,
`runtime_schedule`, `runtime_run`, `runtime_step`,
`runtime_step_dependency`, `runtime_attempt`, `audit_event`, `artifact`,
`artifact_dependency`, `artifact_verification`, and
`artifact_gc_candidate`. The two views are `run_trace` and
`artifact_integrity_status`. The verified draft catalog contains 56 indexes,
145 constraints, nine functions, and 21 non-internal triggers.

Normal target startup is verify-only and performs no DDL. Draft checksum drift,
a missing/wrong/legacy epoch, unexpected objects, owner drift, catalog drift,
or Artifact corruption fails closed. Draft databases are recreated explicitly;
there is no temporary upgrade migration.

## Exact-SHA verification

The immutable pre-change command ledger is
[WP-02 Pre-Refoundation Verification Baseline](../references/WP-ARCHITECTURE-REFOUNDATION-02-Pre-Refoundation-Verification-Baseline.md).
Foundation results and investigated failed attempts are recorded in
[WP-03 Foundation Verification](../references/WP-ARCHITECTURE-REFOUNDATION-03-Foundation-Verification.md).
At this refreshed snapshot:

- every Python-based repository gate in `AGENTS.md` and `README.md` executes
  through `uv run`; a regression test rejects a return to bare `python` in
  either entry point;
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

The source, legacy-migration, and target-baseline tree IDs remain identical to
the Foundation checkpoint. The WP-03-equivalent rerun therefore keeps the
Foundation exit gate at `GO`; it does not require reverting the mainline merge.
It does not prove Market/PIT, any later target context, Provider, Alpha, broker,
Production, or Runtime/CLI Cutover, and none of those evidence classes were
rerun.

## Research and production ceiling

Existing immutable reports retain negative, inconclusive, and not-estimable
results. They are historical evidence, not an active Roadmap and not a reason to
preserve old persistence identities.

```text
automatic_order_execution = false
broker_integration_proven = false
entry_model_empirically_validated = false
production_ready = false
formal_pit_established = false
formal_oos_alpha_supported = false
sustained_prospective_value_proven = false
```

The current engineering implementation may be tested and replayable while every
stronger empirical or operational claim remains false.

## Refresh contract

A future generated Current State must obtain facts read-only from Git identity,
the configured schema epoch/migration registry, code-owned inventories, executed
test receipts, and canonical Evidence IDs/hashes. It must display missing or
unavailable sources explicitly. It receives no database write credentials and
cannot infer “current” from filenames, latest rows, documents, or artifact
directories.
