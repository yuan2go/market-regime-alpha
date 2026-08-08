# WP-PGSQL-01 SQLite and Compatibility Inventory

> **Status:** CURRENT_STATUS
> **Authority:** Pre-change executable inventory for PostgreSQL-only convergence
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-06
> **Baseline:** `feat/continuous-research-runtime@547ddfba39df155a8b53611e1ce9200bf789de60`
> **Related Documents:** ../superpowers/specs/2026-08-06-postgresql-only-decision-closure-design.md, ../superpowers/plans/2026-08-06-wp-pgsql-decision-closure.md

## Baseline

| Item | Observed value |
| --- | --- |
| Branch | `feat/continuous-research-runtime` |
| Start commit | `547ddfba39df155a8b53611e1ce9200bf789de60` |
| Local `origin/main` | `8de820cd149278bfebbaf18f150a90f36380176d` |
| Workspace | clean; branch 17 commits ahead of local `origin/main` |
| Python | 3.12.2 |
| uv | 0.11.7 |
| PostgreSQL | 16.14, temporary UTF-8 cluster on loopback only |
| Packaged migrations | 001-023 |
| Test functions by static scan | 1,627 across 327 test modules |
| Full configured baseline | 2,430 passed, 8 subtests passed, 0 skipped, 6 warnings, 241.18 seconds |
| PostgreSQL test modules/functions | 19 / 59 |
| Migration-related test functions | 82 |
| Replay-related test functions | 72 |
| SQLite-related test functions | 65 |
| SQLite/bridge matching tracked files | 252 before classification |

The first full run used a passwordless trust DSN and produced two locator-
redaction assertion failures. A second run used a placeholder password in the
same temporary trust-authenticated cluster and passed completely. No business
database or credential was contacted.

## Physical data discovery

No `.sqlite`, `.sqlite3`, or `.db` business file was found in this worktree,
the primary Market Regime Alpha checkout, Market Regime Alpha worktrees, or the
reviewed user project/document paths. SQLite files belonging to unrelated
projects were not opened or changed. Therefore no legacy data importer is
required. The existing hypothetical importer and empty migration manifest are
removal targets, not retained Runtime assets.

## Runtime dependency graph before change

```text
Application / Domain
  -> Repository Protocol
  -> Postgres*Repository thin subclass
  -> PostgresRepositoryAdapter
  -> PostgresDBAPIConnection
  -> SQLite*Repository algorithm and qmark SQL
  -> psycopg connection
  -> PostgreSQL 16

Explicit compatibility selection
  -> DatabaseSettings(backend=SQLITE, sqlite_path=...)
  -> RepositoryFactory SQLite branch
  -> SQLite*Repository
  -> sqlite3 file database
```

This structure means PostgreSQL is the physical database on its active path,
but the repository implementation is not PostgreSQL-native. The bridge
rewrites qmark placeholders and `INSERT OR IGNORE`, synthesizes SQLite-shaped
rows/timestamps/`lastrowid`, and emulates `BEGIN IMMEDIATE` with a shared
advisory lock.

## Classified removal matrix

| Type | Current files or locations | Current use | PostgreSQL replacement | Planned result |
| --- | --- | --- | --- | --- |
| Settings | `persistence/settings.py` | `DatabaseBackend.SQLITE`, path selection | one PostgreSQL URL setting | remove backend enum/path branch |
| Factory | `persistence/repository_factory.py` | selects PostgreSQL or SQLite repositories and accepts legacy flags | direct native PostgreSQL composition | remove every SQLite branch and flag |
| Bridge | `persistence/postgres/adapter.py`, `persistence/postgres/dbapi.py` | masks psycopg as `sqlite3.Connection`, translates SQL and rows | direct psycopg repositories | delete compatibility bridge |
| Import | `persistence/sqlite_to_postgres.py`, `persistence/migration_manifest.py`, `scripts/migrate_sqlite_to_postgres.py`, `config/postgres/initial-sqlite-migration-manifest.json` | hypothetical one-time import | none because no source data exists | delete importer and manifest |
| Governance | `platform/sqlite_governance.py` | model/experiment persistence and PostgreSQL algorithm base | native `platform/postgres_governance.py` | delete SQLite implementation |
| Decision | `decision/sqlite_repository.py` | opportunity/thesis aggregate persistence | native `decision/postgres_repository.py` | delete SQLite implementation |
| Portfolio | `portfolio/sqlite_repository.py`, `sqlite_account_authority.py`, `sqlite_risk_routes.py` | portfolio/risk authorities | native PostgreSQL repositories | delete SQLite implementations |
| Execution | `execution/sqlite_repository.py`, `sqlite_traceability.py` | manual intent/Fill ledger/Position book persistence | native PostgreSQL repositories | delete SQLite implementations |
| Position | `position/sqlite_thesis_health.py` | H5 state | native PostgreSQL repository | delete SQLite implementation |
| H4.5 | `application/trading_lifecycle/sqlite_risk_reduction.py` | reducing-risk manual-intent transaction | native PostgreSQL scoped transaction | delete SQLite implementation |
| Daily | `application/daily_loop/sqlite_repository.py` | Daily Runtime journal and PostgreSQL algorithm base | native PostgreSQL journal | delete SQLite implementation |
| Canonical | `application/canonical_lifecycle/sqlite_repository.py`, `sqlite_composition.py`, `_sqlite_schema.py`, `_sqlite_codec.py` | lifecycle journal, composition and replay | native PostgreSQL journal/composition/Reader | delete SQLite implementation |
| Controlled | `application/controlled_operation/sqlite_journal.py` and SQLite index in `longitudinal_index.py` | controlled journal/index and PostgreSQL algorithm base | native PostgreSQL journal/index | delete SQLite implementation |
| Composite | `application/operational_research/sqlite_composite_repository.py` | H6 persistence and PostgreSQL algorithm base | native PostgreSQL repository | delete SQLite implementation |
| State | `application/state_system/sqlite_repository.py` | compatibility state/pool persistence | existing native PostgreSQL repository | delete SQLite implementation |
| Feature | `features/materialization_run.py` SQLite class | Feature Runtime compatibility implementation and PostgreSQL base | complete native PostgreSQL class | retain domain contracts, delete SQLite repository |
| Replay | canonical/controlled replay and CLI modules | open SQLite journals by path | isolated migrated PostgreSQL schemas | remove path replay and bind PostgreSQL snapshot |
| CLI | account/lifecycle/controlled scripts and CLI modules | hidden `--database`/`--journal` aliases and `--sqlite-database` | explicit `--database-url`/environment | remove SQLite arguments and path routing |
| Tests | 57 Python test modules reference SQLite names/behavior | unit, integration, parity and replay | pure in-memory doubles or isolated PostgreSQL schemas | delete SQLite-only suites; port authoritative cases |
| Docs | current status, runbooks, architecture, prior migration design/evidence | describe explicit SQLite compatibility/import | PostgreSQL Authority Only | supersede current claims; retain historical facts only in audit/archive context |
| Package | `pyproject.toml` mypy/package references plus built wheel contents | includes runnable SQLite modules | native PostgreSQL modules only | remove references and verify wheel contents |

## SQL and transaction constructs requiring native replacement

The inventory found all required classes of SQLite behavior:

- qmark parameters throughout legacy repository algorithms;
- `INSERT OR IGNORE` in Daily, Canonical and State journals;
- `BEGIN IMMEDIATE` in aggregate, journal, feature and reconciliation-like
  critical sections;
- `PRAGMA` and `sqlite_master` schema inspection;
- SQLite row, Boolean and datetime compatibility conversion;
- synthesized generated identity/`lastrowid` handling;
- file paths, `:memory:` fixtures and temporary `.sqlite3` files;
- one bridge-wide advisory lock that serializes unrelated scopes;
- SQLite-specific triggers and migration tests;
- CLI flags and environment selection that can re-enable SQLite.

Native replacements are `%s` psycopg binding, explicit `ON CONFLICT` targets,
`RETURNING`, native `TIMESTAMPTZ`/`BOOLEAN`/`NUMERIC`, aggregate or operation
row locks, scope advisory locks only where no row exists, conditional CAS,
lease/fencing checks and central forward migrations.

## Authority and compatibility constraints

- Historical fixed-14:55 Target, TargetId, Artifact and Reader semantics stay
  unchanged. Only their database replay transport moves to PostgreSQL.
- DuckDB, Parquet, immutable Artifacts and source archives are not SQLite
  Runtime backends and remain outside this removal.
- Manual Account observations never create Fill or Position state.
- Research Portfolio and Independent Risk decisions never create Order,
  ManualTrade, Fill or Broker calls.
- Entry remains blocked and model parameters remain frozen.

## Delivered disposition

Every `Planned result` in the matrix was executed. The executable repositories,
factory branches, bridge, importer, local schemas/migrations, replay path,
CLI/environment switches and database integration tests were removed or ported
to native PostgreSQL. No one-time importer was retained because discovery found
no business source data. Immutable file Artifact Readers and historical 14:55
identities remain; they are not database backends.

Migration 024 supersedes the historical migration-017 backend vocabulary
without changing that published migration's checksum. Migration 025 adds the
Decision System authorities; migration 026 hardens lease/configuration/stage
lineage, freezes Decision-time Fill account authority and provides isolated
PostgreSQL replay import. Current runtime code, integration tests and built
packages contain no executable file-database repository or compatibility
bridge.
