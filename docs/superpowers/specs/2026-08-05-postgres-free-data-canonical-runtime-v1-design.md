# PostgreSQL Free-Data Canonical Runtime V1 Design

> **Status:** CURRENT_SPECIFICATION
> **Authority:** Approved implementation design for the free-data canonical runtime work package
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-05
> **Related Documents:** ../../plans/2026-08-05-postgres-free-data-canonical-runtime-v1.md, ../../../delivery/PostgreSQL-Free-Data-Canonical-Runtime-V1.md
> **Code Evidence:** Design baseline `dbdd72cc55a5e13fecf0113e3fad3ac694917ff2`; implementation evidence is listed in the delivery record.

## Status and authority

This design implements the approved `PostgreSQL-backed, Tencent-centered,
Free-data Canonical Research Runtime` work package on branch
`feat/controlled-1455-operational-evidence`. The implementation baseline is
`dbdd72cc55a5e13fecf0113e3fad3ac694917ff2`; the only pre-existing working-tree
change is `.idea/modules.xml`, which is outside this work package.

The work package proves engineering behavior only. Every result remains
`EXPLORATORY`, `FORMAL_PIT_NOT_ESTABLISHED`,
`FORMAL_OOS_ALPHA_NOT_ESTABLISHED`, `ENTRY_MODEL_NOT_VALIDATED`,
`TRADING_AUTHORITY_NOT_GRANTED`, `BROKER_NOT_INVOKED`, `NO_ORDER_CREATED`, and
`NO_FILL_CREATED`.

## Current executable facts

- PostgreSQL 16.14 is reachable through the ignored `.env`; packaged migration
  017 is applied.
- Active CLIs default to `RepositoryFactory`, which fails closed without a
  PostgreSQL URL. SQLite is selected only by an explicit compatibility flag.
- Canonical, Controlled, Feature, Daily, governance, decision, portfolio,
  execution, position, thesis-health, and operational-evidence PostgreSQL
  adapters exist.
- PostgreSQL adapters currently reuse SQLite-oriented repository algorithms
  through a DB-API bridge. `BEGIN IMMEDIATE` is translated to plain `BEGIN`;
  this does not preserve the original serialization guarantee.
- Controlled operation CLI composition injects PostgreSQL repositories, but
  reusable application constructors still contain implicit SQLite defaults.
- Public BaoStock/Tencent acquisition, immutable raw bytes, SourceManifest,
  canonical daily data, Tencent minute archive, Feature V2, Candidate overlay,
  Signal V3, PathForecast fail-closed behavior, and Controlled/Canonical
  orchestration already exist as separate capabilities.
- No production composition currently turns a free-data request into the full
  set of Controlled input artifacts. Supplemental theme/capital evidence in
  full-chain tests is fixture-built.

## Considered approaches

### A. Add a new free-data runtime and journal

This would give the new CLI a purpose-built state machine, but it would create
a third active runtime beside DailyLoop and Controlled Operation. It would also
duplicate lease, recovery, replay, and reporting behavior. Rejected.

### B. Compose existing acquisition and runtime authorities

Use the PostgreSQL DailyLoop journal for idempotent BaoStock/Tencent source
freeze, materialize the missing Controlled input artifacts, then execute the
existing Controlled parent and Canonical child. The free-data application is a
composition service and CLI facade, not a new lifecycle authority. Selected.

### C. Expand Controlled Operation stages to own all acquisition

This would make one state machine visually complete, but it changes the
already-delivered 14:55 protocol, migration 014, replay packages, and evidence
contracts. The risk is disproportionate when DailyLoop already provides the
required acquisition recovery. Deferred unless operational evidence proves
the composition boundary inadequate.

## Target architecture

```text
FreeDataOperationRequest
  -> PostgreSQL DailyRun source-freeze child
  -> immutable raw BaoStock/Tencent Archive + SourceManifest
  -> explicit TradingCalendar Artifact
  -> complete OperationalUniverse Artifact
  -> canonical daily MarketData Dataset
  -> supplemental observable-proxy evidence or explicit missing evidence
  -> ControlledOperationCommand
  -> PostgreSQL Controlled parent journal
  -> PostgreSQL Feature run/task authority
  -> Tencent candidate-minute archive
  -> PostgreSQL Canonical child journal
  -> Signal V3
  -> PathForecast DATA_INSUFFICIENT
  -> Entry BLOCKED_BY_MODEL_VALIDATION
  -> immutable evidence package and offline replay
```

PostgreSQL is the mutable state and transaction authority. The Artifact Store
owns immutable evidence bytes. PostgreSQL stores identities, hashes, locators,
versions, leases, fencing epochs, attempts, events, and parent/child references;
it does not become a second mutable copy of artifact content.

## PostgreSQL convergence

The shared PostgreSQL connection layer will expose bounded retries only for
PostgreSQL serialization failures and deadlocks. Compatibility execution of a
SQLite `BEGIN IMMEDIATE` section will take a transaction-scoped PostgreSQL
advisory lock with a stable application/schema key, making the inherited
critical section explicit instead of silently weakening it to plain `BEGIN`.
Feature worker selection will use `FOR UPDATE SKIP LOCKED` before CAS/fencing
updates. Retry, advisory-lock wait, and transaction-attempt metrics will be
observable without logging credentials.

Canonical composition will no longer import the SQLite composition root for
backend-neutral stage construction. Controlled production construction will
require explicit journal, longitudinal-index, canonical-repository, and
feature-repository dependencies. SQLite implementations remain available only
through explicit compatibility composition and tests.

## Provider profile and raw evidence

`TENCENT_FREE_OPERATIONAL_V1` declares:

- BaoStock: prior-session raw daily history and exact-session security status;
- Tencent: decision-time quote and candidate one-minute data;
- no local/static/AKShare/Tushare/EastMoney fallback;
- `EXPLORATORY` and `FORMAL_PIT_NOT_ESTABLISHED` authority.

Each live raw payload records provider/profile, endpoint, canonical request
parameters, requested/retrieved times, provider/event/availability/decision
times when known, status/content type, byte length, encoding, symbol/field
scope, limitations, and raw SHA-256. Historical artifact readers continue to
accept the older payload schema; new live writes use the metadata-bearing
schema.

Provider failure publishes or returns a blocked result under the same request.
It never substitutes a fixture or keeps the Tencent profile identity after a
different provider is used.

## Universe, calendar, and supplemental evidence

The free-data preparation service supports exact 20/100/300 request scopes.
Every requested symbol receives an OperationalUniverse record. Inclusion is
derived from archived history coverage, explicit listing/ST/suspension facts,
liquidity evidence, and decision-time availability. Unknown critical status is
an exclusion reason, not a neutral default.

The trading calendar contains only sessions explicitly present in archived
provider evidence. Weekdays are never invented.

Market and per-symbol observable inputs are derived from verified canonical
daily bars and SourceManifest facts. Theme membership, ETF mapping, or capital
inputs not present in free data are represented by `MissingEvidence` and cause
Theme Rotation, Capital Evolution, Candidate, and the operation to fail closed.
The application never creates a broad-market pseudo-theme or copies a market
amount metric into an ETF field. A full Signal V3 path therefore requires an
explicit immutable supplemental artifact whose source lineage is independently
verified; absence is an honest engineering terminal state.

## CLI and status semantics

The facade exposes:

- `prepare-free-data-operation`
- `run-free-data-decision-window`
- `resume-free-data-operation`
- `replay-free-data-operation`
- `report-free-data-operation`
- `inspect-free-data-operation`

The commands delegate to existing application services. Outputs include the
requested IDs/hashes/locators, PostgreSQL authority locator with credentials
redacted, code revision, configuration hash, runtime and blocker status, and
all safety declarations. `ENTRY BLOCKED` is rendered as
`ENGINEERING_RUN_COMPLETED` plus `ENTRY_AUTHORITY_BLOCKED`, never as a trade
decision.

## Recovery and artifact/database failure order

- Acquisition recovery first searches for the unique immutable stage artifact
  bound to the DailyRun request, then repairs a missing journal receipt.
- Artifact publication is content-addressed and idempotent.
- A committed PostgreSQL receipt with a missing artifact fails replay and
  inspect with a precise blocked reason.
- An artifact published before a PostgreSQL receipt is recovered by verified
  identity and hash; it is never overwritten.
- Reusing an idempotency key with another command hash is rejected.
- Lease expiry increments the fencing epoch; stale writers cannot complete.

## Test and evidence strategy

- Deterministic provider fixtures test parsing and failure semantics only.
- Recorded raw archives test replay, tamper detection, normalization, time and
  unit rules without network access.
- PostgreSQL integration tests run against a real PostgreSQL schema and cover
  concurrent claims, lease expiry, fencing, idempotency conflicts, retryable
  transaction errors, restart, parent/child references, and append-only state.
- 20/100/300 tests use recorded archives and assert stable artifact hashes,
  no repeated acquisition/computation, and no execution-domain mutations.
- An explicit live smoke is run when the provider and decision window allow it.
  A late clock or inaccessible provider yields a real blocked artifact and is
  not replaced by a fixture.

## Non-goals

No formal PIT/OOS qualification, parameter search, model calibration, Entry
opening, Opportunity/Portfolio/ManualTrade/Fill creation, broker integration,
position mutation, XtQuant work, or automated trading is included.
