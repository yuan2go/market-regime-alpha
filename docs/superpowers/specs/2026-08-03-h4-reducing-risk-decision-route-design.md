# H4 Reducing-Risk Decision Route Design

> **Status:** CURRENT_SPECIFICATION
> **Authority:** Approved bounded design for repairing the H4 reducing-risk route
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-03
> **Supersedes:** None
> **Superseded By:** None
> **Related Documents:** ../../architecture/11-Production-Lifecycle-Hardening-and-Shadow-Operations.md, ../../roadmap/work-packages/WP-PDL-Hardening-and-Shadow-Readiness.md, ../../status/Current-State.md, ../../audit/Current-Main-Code-Audit-2026-08-01.md
> **Code Evidence:** Repair branch starts from `origin/main@c018a6a2cfa6c5a5edc7d2083750d336c6860acb`; the underlying H4 code baseline is `e183fdac285786ed448c835e65c99dc67189c2b9`.

## 1. Goal and bounded context

Complete the H4 reducing-risk decision route as a durable, replayable and
human-confirmation-only vertical slice:

```text
Authoritative PositionSnapshot
+ ReducingExecutionObservation
+ explicit RiskReducingGateConfiguration
+ REDUCE or EXIT command
→ RiskReducingExecutionGate
→ immutable RiskReducingDecision
→ atomic SQLite persistence
→ DECISION_ONLY CLI output
```

The result may be `PERMITTED_FOR_MANUAL_CONFIRMATION`, `BLOCKED` or
`DATA_INSUFFICIENT`. It never creates an order, ManualTradeRecord, Fill or
Position mutation and never grants broker authority.

## 2. Baseline facts

At the branch baseline:

- `portfolio/risk_routes.py` contains the H4 value objects and Gate;
- migration 007 contains reducing-decision and command tables;
- `tests/portfolio/test_risk_route_separation.py` imports missing public API;
- `portfolio/sqlite_risk_routes.py`, `SQLiteRiskRouteRepository` and
  `RiskRouteApplicationService` do not exist;
- the first reproducible failure is a package-export collection error;
- the formal CI mypy target passes, while H4 leaves Ruff and pytest red;
- CI does not run `python -m build`.

## 3. Considered approaches

### Import-only repair

Rejected. Exporting domain objects would only reveal the next missing module
and would provide no persistence, idempotency, recovery or operator entry.

### Bounded H4 vertical slice

Accepted. Complete the Gate semantics, Repository, Application Service,
stable exports, decision-only CLI, focused tests, CI build gate and
commit-bound documentation while leaving execution schemas unchanged.

### Direct ManualTrade/Fill integration

Deferred to H4.5. It would require new execution schema identities,
migrations, stale-decision checks and partial-fill state transitions that are
not necessary to restore H4 or the current engineering baseline.

## 4. Domain model

### 4.1 Route separation

`OPEN` and `ADD` are increasing-risk actions. They cannot enter either
`RiskRouteApplicationService.assess_reducing` or
`RiskReducingExecutionGate.assess`; callers must use the existing
complete-account Portfolio/Risk authority.

`REDUCE` and `EXIT` do not call Entry or the increasing-risk service. They are
assessed solely for strict risk reduction and current execution constraints.

### 4.2 Explicit freshness configuration

The current configuration schema cannot represent execution-observation
freshness. H4 therefore introduces an explicit v2 configuration schema with:

```text
maximum_position_age_seconds
maximum_observation_age_seconds
maximum_liquidity_participation
```

All values are finite, positive and content-identified. The v2 schema updates
creation, canonical serialization, reconstruction, content hash and
configuration identity together. H4 has no functioning durable v1 repository
or qualified production artifacts, so the incomplete v1 configuration is not
silently accepted with invented defaults.

For explicit timezone-aware `assessed_at`:

```text
position.as_of > assessed_at
  → DATA_INSUFFICIENT / POSITION_NOT_AVAILABLE_AT_ASSESSMENT_TIME

assessed_at - position.as_of > maximum_position_age_seconds
  → DATA_INSUFFICIENT / POSITION_SNAPSHOT_STALE

observation.availability_time > assessed_at
  → DATA_INSUFFICIENT / EXECUTION_OBSERVATION_UNAVAILABLE

assessed_at - observation.availability_time
  > maximum_observation_age_seconds
  → DATA_INSUFFICIENT / EXECUTION_OBSERVATION_STALE
```

Symbol or session mismatch also produces `DATA_INSUFFICIENT`; no stale,
future or cross-scope observation may produce permission.

### 4.3 Quantity semantics

For `REDUCE`:

```text
0 <= target_quantity < current_quantity
order_quantity = current_quantity - target_quantity
order_quantity > 0
order_quantity <= available_quantity
```

For `EXIT`:

```text
target_quantity = 0
order_quantity = current_quantity
order_quantity <= available_quantity
```

Invalid non-negative command quantities produce an immutable `BLOCKED`
decision with explicit reason codes. Negative quantities remain invalid domain
input and are rejected. An EXIT with only part of the current position
sellable is blocked; a future best-effort action must be a separate REDUCE
command.

## 5. Application Service

`RiskRouteApplicationService` is the command boundary exposed from the
Portfolio package and the trading-lifecycle application package. It:

1. rejects `OPEN` and `ADD` before persistence;
2. requires timezone-aware explicit `assessed_at` and a trimmed idempotency key;
3. round-trips Position, Observation and Configuration through canonical
   reconstruction to reject malformed command inputs;
4. builds a deterministic command payload and SHA-256 command hash;
5. resolves an existing command by idempotency key and command hash;
6. calls `RiskReducingExecutionGate` for a new command;
7. atomically persists the complete verified decision bundle;
8. returns the stored and restored decision.

The command hash covers action, full canonical Position, target/order
quantities, full canonical Observation and Configuration, actor, reason and
assessed time. The idempotency key itself is an addressing key and is not part
of the semantic hash.

## 6. SQLite Repository

`SQLiteRiskRouteRepository` owns migration 007 and implements the
storage-neutral H4 repository protocol.

### 6.1 Initialization

Construction applies the idempotent up migration and then verifies migration
version 7, required tables, required columns and append-only triggers. A
pre-existing incompatible table is rejected rather than trusted because
`CREATE TABLE IF NOT EXISTS` cannot repair it.

### 6.2 Atomic save

One `BEGIN IMMEDIATE` transaction performs:

```text
resolve existing command
→ validate command hash and decision reference
→ restore existing decision bundle when replaying
or
validate any existing decision identity
→ insert immutable decision bundle if absent
→ insert idempotency command
→ reload and revalidate the stored bundle
→ COMMIT
```

Any error rolls back both the decision and command insert. Reusing an
idempotency key with a different command hash is an error. Reusing a
decision ID with different content or inputs is an error. A new idempotency
key may reference an already-identical content-addressed decision.

### 6.3 Restore and tamper detection

Reads do not return deserialized JSON directly. They:

1. parse every JSON column as an object;
2. reconstruct `PositionSnapshot`, `ReducingExecutionObservation`,
   `RiskReducingGateConfiguration` and `RiskReducingDecision` through their
   canonical readers;
3. compare row IDs, action, state, hashes and timestamps with reconstructed
   values;
4. verify every Decision reference and hash against the three restored inputs;
5. rerun `RiskReducingExecutionGate` with the persisted command values;
6. require the recomputed decision to equal the stored decision.

This detects malformed schemas, unknown fields, identity drift, JSON tampering,
projection-column tampering, foreign-reference mismatches and decisions that
cannot be reproduced from their evidence.

## 7. Human-confirmation CLI

The CLI follows the repository's existing script-based command style. It
accepts a SQLite path and one JSON command document containing canonical
Position, Observation and Configuration payloads plus the explicit action,
quantities, actor, reason, assessed time and idempotency key.

Its JSON output contains:

```text
mode = DECISION_ONLY
decision_id
state
reason_codes
Position / Observation / Configuration evidence references
manual_confirmation_required
order_created = false
execution_boundary = NO_ORDER_CREATED
trading_authority = TRADING_AUTHORITY_NOT_GRANTED
```

The CLI has no execution repository or broker dependency. Replaying the same
command returns the same decision ID.

## 8. Tests

Focused tests are split by responsibility:

- Gate/Application tests: valid REDUCE/EXIT, route separation, T+1,
  quantities, market constraints, scope mismatch and freshness;
- Repository tests: save/get, restart, idempotency, identity conflict,
  canonical tamper detection, atomic rollback, migration idempotence and
  append-only triggers;
- CLI tests: permitted, blocked, insufficient and replay output plus absence
  of ManualTrade/Fill/Broker effects;
- regression tests: complete Portfolio, Position and Execution suites remain
  green.

Every test uses fixed timezone-aware times and real SQLite files. No in-memory
repository substitutes for persistence behavior.

## 9. CI and dependency boundary

The formal gate remains Python 3.12 with editable dev installation,
documentation validation, `python -m pytest -q`, Ruff and the configured
`python -m mypy` file set. The dev extra adds the build frontend and CI adds
`python -m build`. No publishing, deployment, OS matrix or broker test is
introduced.

The absence of a committed dependency lock and the wider `mypy src` Legacy
errors are recorded as separate baseline gaps unless H4 changes introduce a
new failure there.

## 10. H4.5 forward design boundary

H4.5 will design the Risk-Reducing Decision to Manual Execution Bridge. It
must define a new ManualTrade schema that references an unexpired permitted
decision, rechecks the latest Position and sellability at confirmation time,
records confirmer/time/reason, preserves REDUCE/EXIT permissions, and handles
partial fill, cancellation and mandatory re-decision after position change.

H4 does not depend on H4.5. H4.5 must be completed before, or as an explicit
dependency within, H7 durable Holding/Exit operations. No H4.5 execution code
is included in this repair.

## 11. Completion and non-claims

H4 is complete only when focused and full tests, Ruff, configured mypy,
documentation validation, migration checks and package build pass on the
same commit-bound tree.

Completion does not establish formal PIT/OOS Alpha, calibrated probability,
Shadow operations, production readiness, Entry authority, Manual execution
integration, broker authority or trading authority.
