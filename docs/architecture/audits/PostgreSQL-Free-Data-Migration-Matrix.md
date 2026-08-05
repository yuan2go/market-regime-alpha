# PostgreSQL Free-Data Migration Matrix

> **Status:** CURRENT_STATUS
> **Authority:** Executable call-chain audit for PostgreSQL and retained SQLite boundaries
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-05
> **Baseline:** `dbdd72cc55a5e13fecf0113e3fad3ac694917ff2` on `feat/controlled-1455-operational-evidence`
> **Related Documents:** ../../status/Current-State.md, ../../operations/PostgreSQL-Authority-Runbook.md, ../../delivery/PostgreSQL-Free-Data-Canonical-Runtime-V1.md
> **Code Evidence:** `src/market_regime_alpha/persistence/repository_factory.py`, `src/market_regime_alpha/persistence/postgres/**`, `tests/persistence/postgres/**`, `tests/architecture/test_postgres_runtime_boundaries.py`

## Audit conclusion

The active free-data, Daily, Controlled, Feature and Canonical composition is
PostgreSQL-only and rejects explicit SQLite settings. There is no
PostgreSQL/SQLite dual write. PostgreSQL owns mutable run state, idempotency,
versions, claims, leases, fencing, attempts and parent/child bindings. The
Artifact Store owns immutable evidence bytes; database rows retain only the
identities, hashes and locators required to govern them.

Most bounded PostgreSQL adapters intentionally reuse the previously verified
repository algorithms through `PostgresDBAPIConnection`. Consequently, a
PostgreSQL adapter can inherit a class named `SQLite...` without opening a
SQLite file. This is a compatibility implementation technique, not a second
authority. `PostgresConnectionFactory` supplies the only physical connection
on the active path. Compatibility critical sections now take a PostgreSQL
transaction-scoped advisory lock; Feature task claims additionally use
`FOR UPDATE SKIP LOCKED` and fencing CAS.

## Executable migration matrix

| Module | CLI / composition call chain | Current Repository | PostgreSQL state | SQLite reachable on active path | Current fact authority | Recommendation |
|---|---|---|---|---|---|---|
| Free-data composition | prepare/run facade -> `FreeDataOperationService` -> `RepositoryFactory` | Daily + Controlled + Feature + Canonical PostgreSQL repositories | migration 018 binds `FREE_DATA_OPERATION` and `DAILY_LOOP`; migration 019 records immutable blocked references | No; constructor rejects SQLite | PostgreSQL state/projection plus immutable source/prepared/blocked packages | Split decision quote from static prepare; complete free-data resume/replay/report/inspect projection |
| Daily source freeze | free-data service -> `DailyLoopRunner.freeze_sources` -> `daily()` | `PostgresDailyRunRepository` | migration 016 | No physical SQLite connection | PostgreSQL journal; raw archive is immutable evidence | Retain explicit compatibility adapter for old replay/tests |
| Controlled operation | free-data service -> Controlled runner -> `controlled_operation()` | `PostgresDecisionTimeOperationJournal` | migrations 014, 017, 018 | No physical SQLite connection | PostgreSQL parent state | Preserve typed blocked terminals and exact parent bindings |
| Canonical lifecycle | Controlled bridge -> `controlled_canonical_repository()` | `PostgresLifecycleRunRepository` | migrations 011, 017 | No physical SQLite connection | PostgreSQL child state | Continue pure/replay Reader expansion without execution authority |
| Feature materialization | Controlled runner -> `feature_materialization_for_path()` | `PostgresFeatureMaterializationRunRepository` | migrations 012, 013 | No physical SQLite connection | PostgreSQL run/task/lease/fencing state; immutable Bundle bytes | Keep row-lock selection and stale-writer fencing tests |
| Operational evidence | Controlled runner -> `longitudinal()` and package publisher | `PostgresLongitudinalOperationalIndex` | migration 015 | No physical SQLite connection | PostgreSQL index; immutable package content | Add sustained operating evidence before H8 claims |
| Composite research evidence | lifecycle service -> `composite()` | `PostgresCompositeOperationalRepository` | migration 009 | No physical SQLite connection | PostgreSQL reference/index state; immutable H6 package | Qualified producers remain external blocker |
| Model Registry | `RepositoryFactory.model_registry()` | `PostgresModelRegistryRepository` | migration 001 | Only when caller explicitly selects SQLite | PostgreSQL governance state | Integrate approved model selection in a later bounded package |
| Experiment Governance | `RepositoryFactory.experiment_governance()` | `PostgresExperimentGovernanceRepository` | migration 001 | Only explicit compatibility | PostgreSQL governance state | Keep access budgets/transitions out of free-data model tuning |
| Opportunity / Thesis | `RepositoryFactory.decision()` | `PostgresDecisionLifecycleRepository` | migration 002 | Only explicit compatibility | PostgreSQL aggregate state | Not invoked by this work package |
| Portfolio / complete-account Risk | `portfolio()`, `complete_account_portfolio()`, `risk_route()` | three PostgreSQL Portfolio/Risk adapters | migrations 003, 005, 007 | Only explicit compatibility | PostgreSQL decisions | Not invoked by free-data operation |
| ManualTrade / Fill | `manual_execution()`, `traceable_execution()` | PostgreSQL manual/traceable repositories | migrations 004, 006 | Only explicit compatibility | PostgreSQL human-recorded intent/Fill ledger | No automatic creation; broker truth still absent |
| Risk-reduction intent | `risk_reduction_manual_intent()` | `PostgresRiskReductionManualIntentRepository` | migration 010 | Only explicit compatibility | PostgreSQL manual confirmation transaction | Preserve manual-only boundary |
| Position | execution trace and H3 projection Readers | Fill-derived PostgreSQL execution/trace tables | migrations 004, 006, 010 | Only explicit compatibility | Recorded Fill evidence and deterministic projection | No free-data position mutation |
| Thesis Health | `thesis_health()` | `PostgresThesisHealthRepository` | migration 008 | Only explicit compatibility | PostgreSQL assessment state | Durable H7 scheduling remains unimplemented |
| Outcome / review | `longitudinal()` plus Daily review repository | PostgreSQL longitudinal and Daily repositories | migrations 015, 016 | Only explicit compatibility | PostgreSQL index/journal and immutable outcomes | H9 may consume; no causal claim |

## PostgreSQL transaction findings

| Requirement | Executable status | Evidence / limitation |
|---|---|---|
| Unique idempotency plus command-hash conflict | Implemented | Repository unique keys and conflict tests reject key reuse with changed commands |
| Code revision binding | Implemented | Free-data command hash changes with code revision; PostgreSQL projections cannot collide across revisions |
| Optimistic version / CAS | Implemented | Daily, Controlled, Canonical and Feature repository contract tests |
| Row locking | Implemented where queue selection needs it | Feature claims select with `FOR UPDATE SKIP LOCKED` |
| Worker lease and fencing | Implemented locally | Feature and Controlled claim/expiry/stale-writer tests |
| Retryable transaction errors | Implemented | Only SQLSTATE `40001` and `40P01` are retried; other errors fail closed |
| Compatibility serialization | Implemented | Former `BEGIN IMMEDIATE` sections acquire a stable transaction advisory lock |
| Append-only events | Implemented | migrations and mutation/tamper tests across bounded repositories |
| Parent/child binding | Implemented | migrations 014, 017, 018 and PostgreSQL free-data integration test |
| Blocked Artifact reference authority | Implemented | migration 019 stores command, Artifact ID/hash/locator, source hashes, reason and code revision; UPDATE/DELETE are rejected |
| Artifact published before database receipt | Recoverable in bounded publishers | Content-addressed identity is verified before a missing receipt is repaired |
| Database receipt with missing artifact | Fail closed | Readers/replay require the bound locator and hash |
| Cross-file/database atomic transaction | Not implemented | PostgreSQL and files cannot form one ACID transaction; recovery protocol is the authority |
| Multi-instance sustained operation | Not proven | Local concurrent-worker tests do not establish H8 |
| Migration down | Not supported by PostgreSQL migrator | Applied migrations are immutable; rollback uses restore or reviewed forward repair |

## SQLite classification

| Classification | Scope | Rule |
|---|---|---|
| `ACTIVE_PROHIBITED` | Free-data, current Controlled, current Canonical and Feature production composition | Architecture tests forbid SQLite imports/default constructors; free-data service rejects SQLite settings |
| `READ_ONLY_COMPATIBILITY` | Historical Signal V1/V2, legacy lifecycle replay/import Readers | May reconstruct old evidence; cannot create a current V3/free-data write |
| `TEST_ONLY` | Deterministic repository parity and unit fixtures | Must be selected explicitly and cannot be reported as PostgreSQL evidence |
| `LEGACY_ARCHIVE` | Dividend-T, dashboard, historical daily research and archived strategies | Isolated from canonical authority and may contain static fallbacks |
| `REMOVABLE` | None proven safe in this package | Deletion requires separate reachability and historical-reader evidence |

## Non-claims

This audit does not establish production PostgreSQL admission, restore/PITR,
formal PIT, formal OOS Alpha, Entry validity, Shadow readiness, broker
integration or trading authority.
