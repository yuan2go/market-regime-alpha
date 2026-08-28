# WP-ARCHITECTURE-REFOUNDATION-03 Foundation Verification

> **Status:** CURRENT_STATUS
> **Authority:** Exact-SHA engineering verification record; not business, evidence, qualification, or Runtime Authority
> **Owner:** Market Regime Alpha maintainers
> **Executed At:** 2026-08-28
> **Source Checkpoint:** `eeff49c7a3995ba6d65045be88d4244617301234`
> **Implementation Line Start:** `6711331a781ccd483e9bbf9924cf6c0f697b0881`
> **Code Evidence:** target Foundation source and tests; unchanged legacy source, migrations, and regression tests

This record proves only the unpublished Foundation slice. It does not release
the mutable target baseline, cut over the canonical Runtime, implement a
business bounded context, or establish Provider, Alpha, broker, Prospective, or
Production evidence.

## Verified draft catalog

```text
schema               mra
epoch                MRA_REFOUNDATION_1
release_state        DRAFT
baseline_version     1
baseline_checksum    e6da8c68b6692923e7e402664765d1ad63e9d0622228586ce03bcb3d823fdc0c
seed_checksum        9c41cd715e35e1a7bed3a58c52a29f01cc1e9bf950b77344bb56eac6dfa2df11
vocabulary_checksum  8119668fa09a0b785b0e9d8ce9ac4400730538d1a8176af4a681c5f4ffa03f7f
catalog_checksum     0df972924a2cf0c106b2d6bb162cd18b912e7d244b6711b4fdd3f526f0ab97bf
tables               13
views                2
indexes              56
constraints          145
functions            9
triggers              21
```

The tables are `schema_epoch`, `schema_migrations`, `command_receipt`,
`runtime_schedule`, `runtime_run`, `runtime_step`,
`runtime_step_dependency`, `runtime_attempt`, `audit_event`, `artifact`,
`artifact_dependency`, `artifact_verification`, and
`artifact_gc_candidate`. The views are `run_trace` and
`artifact_integrity_status`.

## Final validation ledger

| Check | Result | Evidence |
|---|---|---|
| frozen dependency/install sync | **PASS** | project, dev, and PostgreSQL extras resolve from the frozen lock |
| documentation inventory/link checker | **PASS** | canonical inventory, metadata, and links OK; 7 checker tests pass |
| `tests/refoundation` | **PASS** | 61 tests |
| legacy PostgreSQL migrator/schema tests with host DSN | **PASS** | 40 tests; unchanged 001→106 bootstrap, verify, checksum, idempotency, and concurrency behavior |
| full `pytest -q` on a newly recreated PostgreSQL database | **PASS** | exit 0 at 100%; 3,100 tests collected independently |
| `tests/platform` with the required isolated database URL | **PASS** | 33 tests |
| focused legacy replay/recovery/concurrency selection | **PASS** | 31 tests across nine files; no old assertion changed |
| empty target database verify before bootstrap | **PASS** | typed `SchemaMissingError`; normal startup performs no DDL |
| target bootstrap, retry, and verify | **PASS** | first call `created=true`; retry `created=false`; all four checksums and catalog match |
| target destructive recreate CLI smoke | **PASS** | exact database name/OID/owners, empty connection set, object manifest, plan hash, operator, TTL, and challenge validated; post-recreate checksum unchanged |
| target Runtime CLI smoke | **PASS** | verify-only composition; empty recovery returns no claimed Attempts |
| Ruff | **PASS** | all checks passed |
| mypy | **PASS** | no issues in 451 source files |
| package build | **PASS** | sdist and wheel include the target SQL/seed resources and `mra` entry point |
| staged/final diff check | **PASS** | no whitespace errors or unrelated original-worktree changes |

## Investigated non-final attempts

Every failed command is retained here rather than hidden:

| Attempt | Result | Root cause and disposition |
|---|---|---|
| legacy PostgreSQL migrator/schema selection with a Unix-socket DSN | **FAIL** | legacy `DatabaseSettings` requires a host DSN; 38 setup errors. Rerun with the repository-required host URL passed |
| first full suite after those setup errors | **FAIL** | one legacy migration hit `LockNotAvailable` while catalog autovacuum processed leaked empty test schemas. The failing file passed after exact isolated-schema cleanup; a newly recreated database then passed the complete suite |
| explicit `tests/platform` without `MARKET_REGIME_ALPHA_TEST_DATABASE_URL` | **FAIL** | seven tests correctly failed closed on missing PostgreSQL configuration. Rerun with the isolated host URL passed |

No assertion was weakened, no skip/xfail was added, and no compatibility path
was introduced to make a failure disappear.

## Foundation proof boundaries

The target tests cover schema absence, bootstrap retry, legacy/wrong epoch,
checksum and unexpected-object rejection, recreate drift/connection/owner
protection, concurrent claims, lease expiry, heartbeat, stale fence, retry,
resume, deadline and unknown-external-effect recovery, command idempotency
conflicts, transactional rollback, Artifact publish/DB-failure orphaning,
corruption, canonical locator checks, quarantine races, and two-stage garbage
collection.

Architecture tests reject target imports of old Continuous/Controlled/State,
legacy persistence, migration compatibility, or `RepositoryFactory`; Domain
cannot import infrastructure, repositories cannot commit, SQL is confined to
the target PostgreSQL adapter, and `bootstrap.py` is the sole target
composition root.
