# PostgreSQL Free-Data Canonical Runtime V1 Delivery

> **Status:** CURRENT_STATUS
> **Authority:** Delivery record for the PostgreSQL-backed Tencent-centered free-data composition
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-05
> **Implementation Baseline:** `dbdd72cc55a5e13fecf0113e3fad3ac694917ff2`
> **Related Documents:** ../architecture/audits/PostgreSQL-Free-Data-Migration-Matrix.md, ../operations/PostgreSQL-Authority-Runbook.md, ../status/Current-State.md, ../superpowers/specs/2026-08-05-postgres-free-data-canonical-runtime-v1-design.md
> **Code Evidence:** `src/market_regime_alpha/application/free_data_operation/**`, `src/market_regime_alpha/data/providers/public_composite/**`, `tests/application/free_data_operation/**`, `tests/persistence/postgres/test_free_data_operation.py`

## 1. Implementation summary

The delivery composes existing authorities rather than creating a parallel
runtime:

```text
PostgreSQL Daily source freeze
-> immutable BaoStock/Tencent raw archive and SourceManifest
-> explicit calendar, complete Operational Universe and canonical daily data
-> static Feature materialization
-> typed missing supplemental evidence
-> PostgreSQL Controlled parent
-> PostgreSQL Feature tasks
-> PostgreSQL Canonical child when Candidates exist
-> Signal V3
-> PathForecast DATA_INSUFFICIENT
-> Entry BLOCKED_BY_MODEL_VALIDATION
```

The built-in free profile intentionally has no invented theme membership, ETF
mapping or capital-intent evidence. If those inputs are absent, Candidate
Discovery ends in an immutable `DATA_BLOCKED` package. If source normalization
fails after raw bytes were frozen, the service publishes an immutable
`FreeDataBlockedArtifact` bound to the raw archive, SourceManifest, command,
provider-result hash and code revision.

## 2. Before and after

| Concern | Before | After |
|---|---|---|
| Runtime composition | BaoStock/Tencent, Daily, Controlled and Canonical pieces existed separately | One PostgreSQL-only application facade composes the existing Daily parent and Controlled/Canonical authorities |
| PostgreSQL serialization | inherited `BEGIN IMMEDIATE` weakened to plain `BEGIN` | stable transaction advisory lock; retries limited to serialization/deadlock SQLSTATEs |
| Feature workers | CAS/fencing without PostgreSQL row-locked selection | `FOR UPDATE SKIP LOCKED` plus existing CAS/fencing |
| Provider identity | public composite profile did not fully bind raw request metadata | `TENCENT_FREE_OPERATIONAL_V1`, no fallback, raw metadata/hash/size/time/encoding/limitations |
| Universe | final pool could hide excluded requests | exact 20/100/300 records with inclusion and exclusion reasons |
| Failure after source freeze | exception could leave only source stage evidence | content-addressed, tamper-evident blocked artifact |
| CLI | separate low-level runtime commands | six explicit free-data operation entries; prepare is allowed before 14:55, run is gated |
| Legacy boundary | PostgreSQL adapters reused old algorithms ambiguously | migration matrix distinguishes code reuse from physical SQLite authority; architecture guard blocks active imports |

## 3. File inventory

### Added

- free-data contracts, builders, service and blocked-evidence package;
- six-command CLI facade and explicit live-smoke wrapper;
- backend-neutral Canonical composition;
- PostgreSQL migration 018;
- source metadata, recorded 20/100/300, PostgreSQL integration, concurrency,
  architecture and CLI tests;
- design, implementation plan, migration audit and this delivery record.

### Modified

- PostgreSQL connection/DB-API behavior and Feature task claims;
- Daily source-freeze public application seam;
- Controlled research missing-evidence behavior;
- public composite provider/profile contracts;
- Operational Universe availability handling;
- RepositoryFactory coverage for all active bounded adapters;
- `pyproject.toml`, CI coverage, `.gitignore` and current status documents.

### Migrated

- migration 018 extends credential-free runtime authority bindings to
  `DAILY_LOOP` and `FREE_DATA_OPERATION`.

### Frozen

- Signal V1/V2 new writes, model weights, thresholds, PathForecast sample
  authority and all Entry/Opportunity/Portfolio/Execution authorities.

### Legacy

- explicit SQLite compatibility/readers/tests and Dividend-T/dashboard/archive
  code remain isolated. No broad deletion was attempted.

### Deleted

- none.

## 4. Data and replay evidence

| Evidence class | Scope | Result | Authority ceiling |
|---|---|---|---|
| deterministic fixture | parser/error/unit contracts | Provider failures, envelope validation, encoding, units and cutoff fail closed | Test only |
| recorded replay | 20/100/300 symbols | stable prepared identities/hashes; complete Universe records; no execution-domain mutation | Exploratory engineering evidence |
| real PostgreSQL integration | 20 symbols | one source acquisition, one Feature run, idempotent prepare/run and terminal `DATA_BLOCKED`; no SQLite files | Local persistence evidence |
| real network attempt | 20 liquid symbols, 2026-08-05 after the decision window | BaoStock history/status and Tencent quote raw stages plus SourceManifest were frozen; normalization rejected availability after DecisionTime | Exploratory live source evidence, not a 14:55 run |

The real network attempt did not use a fixture fallback. It ended with
`DATA_AVAILABLE_AFTER_DECISION_TIME`, which is the correct authority-preserving
result after the window.

## 5. PostgreSQL scope

PostgreSQL is the active mutable authority for Daily, Controlled, Canonical,
Feature, longitudinal evidence, governance, decision, Portfolio/Risk, manual
execution, thesis health and review/index repositories. The complete call-chain
and retained compatibility classifications are in the migration matrix.

PostgreSQL migration count is 18. The local approved server is PostgreSQL 16.14.
Migration 018 is forward-only; applied migration checksum changes are forbidden.

## 6. Verification protocol

The final release gate must run without further tracked changes against the
commit containing this report:

```text
uv sync --frozen --extra dev --extra postgres
uv run python scripts/check_docs_links.py
uv run pytest -q
uv run ruff check .
uv run mypy
uv run python -m build
git diff --check
```

PostgreSQL integration is additionally run with the ignored test DSN. Local
results are reported with the final handoff because a document cannot embed its
own future Git object ID. Remote CI is separate evidence and is not pre-claimed.

## 7. Unresolved issues

### P0

- No successful real on-window 14:55 package exists; the observed live attempt
  was after the cutoff and correctly blocked.

### P1

- Built-in free data does not provide qualified theme membership, ETF mapping or
  capital evidence; a full Candidate/Signal path requires an explicit immutable
  supplemental producer.
- H7 durable Holding/Exit and H8 scheduling/control-plane state remain absent.
- PostgreSQL restore/PITR and sustained multi-instance operation are unproven.
- Persistent governance repositories are available through RepositoryFactory,
  but Daily B0/B1 runtime model selection is not yet governance-driven.

### P2

- PostgreSQL adapters still reuse compatibility algorithms through a DB-API
  bridge. Future native SQL refactors must be bounded and evidence-driven.
- Artifact producer signatures and authenticated actor identity are absent.

## 8. Capability boundary

```text
free_data_operational_chain = RECORDED_AND_POSTGRES_PROVEN_LIVE_AFTER_WINDOW_BLOCKED
postgres_authority_converged = ACTIVE_RUNTIME_PATHS_TRUE
canonical_runtime_proven = FIXTURE_AND_RECORDED_TRUE_REAL_1455_FALSE
real_tencent_run_proven = RAW_ARCHIVE_TRUE_DECISION_CHAIN_FALSE
formal_pit = false
formal_oos_alpha = false
entry_model_validated = false
shadow_ready = false
broker_integration_proven = false
trading_authority = false
production_ready = false
```

Safety state remains `BROKER_NOT_INVOKED`, `NO_ORDER_CREATED`,
`NO_FILL_CREATED` and `NO_POSITION_MUTATION`.

## 9. Next stage

The dependency-ready next package is **Qualified Historical Data Preparation**:
produce effective-dated theme/ETF/capital inputs and qualified historical
samples without changing model weights or claiming formal PIT. H9, H7 and the
Shadow control plane remain separate later packages.
