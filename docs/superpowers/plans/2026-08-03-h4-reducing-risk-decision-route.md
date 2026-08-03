# H4 Reducing-Risk Decision Route Implementation Plan

> **Status:** CURRENT_SPECIFICATION
> **Authority:** Task-level execution plan for the approved H4 repair
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-03
> **Supersedes:** None
> **Superseded By:** None
> **Related Documents:** ../specs/2026-08-03-h4-reducing-risk-decision-route-design.md, ../../roadmap/work-packages/WP-PDL-Hardening-and-Shadow-Readiness.md, ../../architecture/11-Production-Lifecycle-Hardening-and-Shadow-Operations.md
> **Code Evidence:** Plan starts from `fix/h4-risk-route-baseline@f16a61e`; implementation evidence requires later tests and commits.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete H4 as a durable, replayable, human-confirmation-only reducing-risk decision route and restore the exact-commit engineering baseline.

**Architecture:** Keep decision rules in `portfolio/risk_routes.py`, place persistence behind a storage-neutral Repository Protocol and SQLite adapter, and expose one application command that hashes all inputs before invoking the Gate. The CLI reads canonical evidence, persists only `RiskReducingDecision`, and prints an explicit no-order/no-authority envelope.

**Tech Stack:** Python 3.12, frozen dataclasses, Enum, Protocol, canonical JSON/SHA-256, SQLite `BEGIN IMMEDIATE`, argparse, pytest, Ruff, mypy and Python build.

## Global Constraints

- `OPEN` and `ADD` remain dependent on complete-account Portfolio/Risk and cannot use the reducing Gate.
- `REDUCE` and `EXIT` output only `PERMITTED_FOR_MANUAL_CONFIRMATION`, `BLOCKED` or `DATA_INSUFFICIENT`.
- All Position and Observation freshness thresholds are explicit configuration and all decision times are timezone-aware inputs.
- Do not modify ManualTradeRecord, ManualTrade schema, Fill schema, Fill ledger, Position projection or broker adapters.
- Do not create orders, fills or trading authority.
- Preserve `.idea/modules.xml` and exclude it and generated `dist/` files from every commit.
- Preserve formal PIT/OOS, Shadow, production and broker non-claims.

---

### Task 1: Public API progression and domain freshness

**Files:**
- Modify: `src/market_regime_alpha/portfolio/risk_routes.py`
- Modify: `src/market_regime_alpha/portfolio/__init__.py`
- Modify: `tests/portfolio/test_risk_route_separation.py`

**Interfaces:**
- Consumes: `PositionSnapshot`, `ReducingExecutionObservation`, explicit `assessed_at`.
- Produces: v2 `RiskReducingGateConfiguration`, stronger `RiskReducingExecutionGate`, stable H4 public imports.

- [ ] **Step 1: Export the existing public domain types and run the original red test**

Add imports and `__all__` entries for:

```python
from market_regime_alpha.portfolio.risk_routes import (
    ExecutionConstraintState,
    ReducingExecutionObservation,
    RiskChangeKind,
    RiskReducingDecision,
    RiskReducingDecisionState,
    RiskReducingExecutionGate,
    RiskReducingGateConfiguration,
)
```

Run: `python -m pytest -q tests/portfolio/test_risk_route_separation.py`

Expected: collection advances to the missing `RiskRouteApplicationService` or `sqlite_risk_routes` import.

- [ ] **Step 2: Add failing fixed-time tests for explicit Observation freshness**

Add tests that construct configurations with both thresholds:

```python
configuration = RiskReducingGateConfiguration.create(
    profile_id="test_risk_reducing_gate_v2",
    maximum_position_age_seconds=60.0,
    maximum_observation_age_seconds=30.0,
    maximum_liquidity_participation=0.1,
)
```

Assert future observations produce `EXECUTION_OBSERVATION_UNAVAILABLE`, stale
observations produce `EXECUTION_OBSERVATION_STALE`, and neither is permitted.

Run: `python -m pytest -q tests/portfolio/test_risk_route_separation.py -k 'fresh or stale or future'`

Expected: FAIL because the new configuration field and stale reason do not exist.

- [ ] **Step 3: Upgrade the configuration and Gate semantics**

Implement the explicit schema and checks:

```python
RISK_REDUCING_GATE_CONFIG_SCHEMA = "risk-reducing-gate-configuration-v2"

@dataclass(frozen=True, slots=True)
class RiskReducingGateConfiguration:
    schema_version: str
    configuration_id: ArtifactId
    configuration_hash: str
    profile_id: str
    maximum_position_age_seconds: float
    maximum_observation_age_seconds: float
    maximum_liquidity_participation: float
```

In `assess`, reject naive `assessed_at`; classify future/stale Position and
Observation evidence as data insufficient; allow REDUCE only when
`0 <= target_quantity < current_quantity`; retain EXIT zero-target semantics.

Run: `python -m pytest -q tests/portfolio/test_risk_route_separation.py -k 'fresh or stale or future or reducing_gate'`

Expected: freshness and quantity tests pass; collection may still fail on missing persistence imports until Task 2 scaffolding is present.

### Task 2: Repository Protocol and SQLite schema contract

**Files:**
- Modify: `src/market_regime_alpha/portfolio/repositories.py`
- Create: `src/market_regime_alpha/portfolio/sqlite_risk_routes.py`
- Modify: `src/market_regime_alpha/portfolio/migrations/007_risk_routes_up.sql`
- Modify: `src/market_regime_alpha/portfolio/migrations/007_risk_routes_down.sql` only if trigger ownership changes
- Create: `tests/portfolio/test_sqlite_risk_routes.py`

**Interfaces:**
- Consumes: the four-object Position/Observation/Configuration/Decision bundle plus idempotency key and command hash.
- Produces: atomic save, command resolution and canonical/recomputed reads.

- [ ] **Step 1: Write failing repository interface tests**

Tests call these exact protocol operations:

```python
class RiskRouteRepository(Protocol):
    def save_reducing_decision(
        self,
        decision: RiskReducingDecision,
        *,
        position: PositionSnapshot,
        execution_observation: ReducingExecutionObservation,
        configuration: RiskReducingGateConfiguration,
        idempotency_key: str,
        command_hash: str,
    ) -> RiskReducingDecision: ...

    def resolve_reducing_command(
        self, *, idempotency_key: str, command_hash: str
    ) -> RiskReducingDecision | None: ...

    def get_reducing_decision(
        self, decision_id: ArtifactId
    ) -> RiskReducingDecision: ...
```

Cover first save/get, same command replay, restart and repeated constructor migration.

Run: `python -m pytest -q tests/portfolio/test_sqlite_risk_routes.py`

Expected: FAIL because the adapter and protocol are missing.

- [ ] **Step 2: Implement initialization and schema verification**

Create constants and the connection boundary:

```python
_MIGRATION_ROOT = Path(__file__).resolve().parent / "migrations"
RISK_ROUTE_UP_MIGRATION = _MIGRATION_ROOT / "007_risk_routes_up.sql"
RISK_ROUTE_DOWN_MIGRATION = _MIGRATION_ROOT / "007_risk_routes_down.sql"

class SQLiteRiskRouteRepository:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(RISK_ROUTE_UP_MIGRATION.read_text(encoding="utf-8"))
            _validate_schema(connection)
```

`_validate_schema` must require migration version 7, both H4 tables, every
declared column and both decision append-only triggers.

Run: `python -m pytest -q tests/portfolio/test_sqlite_risk_routes.py -k 'migration or first_save or restart'`

Expected: migration tests and basic save/read tests advance to unimplemented persistence behavior.

- [ ] **Step 3: Implement atomic insert and idempotency resolution**

Use one explicit transaction:

```python
with self._connect() as connection:
    connection.execute("BEGIN IMMEDIATE")
    try:
        replay = _resolve_command(
            connection,
            idempotency_key=idempotency_key,
            command_hash=command_hash,
        )
        if replay is not None:
            connection.commit()
            return replay
        _insert_or_validate_decision_bundle(
            connection,
            decision=decision,
            position=position,
            observation=execution_observation,
            configuration=configuration,
        )
        connection.execute(
            "INSERT INTO risk_reducing_commands(idempotency_key, command_hash, decision_id, created_at) VALUES (?, ?, ?, ?)",
            (idempotency_key, command_hash, str(decision.decision_id), decision.assessed_at.isoformat()),
        )
        restored = _load_reducing_decision(connection, decision.decision_id)
        connection.commit()
        return restored
    except Exception:
        connection.rollback()
        raise
```

Run: `python -m pytest -q tests/portfolio/test_sqlite_risk_routes.py -k 'save or replay or conflict or restart'`

Expected: save/replay pass; tamper tests remain red until reconstruction is implemented.

### Task 3: Canonical reconstruction, recomputation and atomic rollback

**Files:**
- Modify: `src/market_regime_alpha/portfolio/sqlite_risk_routes.py`
- Modify: `tests/portfolio/test_sqlite_risk_routes.py`

**Interfaces:**
- Consumes: persisted canonical payloads and projection columns.
- Produces: a decision only when its entire evidence bundle reconstructs and recomputes exactly.

- [ ] **Step 1: Add failing tamper and transaction tests**

Drop the no-update trigger only inside disposable test databases, then alter
each of `decision_json`, row `content_hash` and `configuration_json` and assert
`get_reducing_decision` raises `ValueError`. Install a temporary trigger that
rejects command insertion and assert both H4 tables remain without the attempted
decision/command after rollback.

Run: `python -m pytest -q tests/portfolio/test_sqlite_risk_routes.py -k 'tamper or rollback or append_only or identity_conflict'`

Expected: FAIL until strict restoration and transaction rollback are complete.

- [ ] **Step 2: Implement strict JSON reconstruction and row checks**

Restore with canonical readers:

```python
position = PositionSnapshot.from_canonical_dict(_object_json(row["position_json"]))
observation = ReducingExecutionObservation.from_canonical_dict(
    _object_json(row["observation_json"])
)
configuration = RiskReducingGateConfiguration.from_canonical_dict(
    _object_json(row["configuration_json"])
)
decision = RiskReducingDecision.from_canonical_dict(
    _object_json(row["decision_json"])
)
```

Compare row ID/action/state/content hash/assessed time, then require the
Decision's Position, Observation and Configuration references/hashes to match
the three restored inputs.

- [ ] **Step 3: Recompute the Gate result on every read**

```python
expected = RiskReducingExecutionGate().assess(
    action=decision.action,
    position=position,
    target_quantity=decision.target_quantity,
    order_quantity=decision.order_quantity,
    execution_observation=observation,
    configuration=configuration,
    actor=decision.actor,
    reason=decision.reason,
    assessed_at=decision.assessed_at,
)
if expected != decision:
    raise ValueError("risk-reducing decision is not reconstructible")
```

Run: `python -m pytest -q tests/portfolio/test_sqlite_risk_routes.py`

Expected: all Repository, tamper, rollback, migration and trigger tests pass.

### Task 4: RiskRouteApplicationService

**Files:**
- Modify: `src/market_regime_alpha/portfolio/risk_routes.py`
- Modify: `src/market_regime_alpha/portfolio/__init__.py`
- Modify: `src/market_regime_alpha/application/trading_lifecycle/__init__.py`
- Modify: `tests/portfolio/test_risk_route_separation.py`

**Interfaces:**
- Consumes: one explicit reducing command.
- Produces: the repository-restored immutable `RiskReducingDecision`.

- [ ] **Step 1: Add failing Application Service tests**

Cover legal REDUCE/EXIT, OPEN/ADD rejection, freshness, symbol/session mismatch,
quantity rules, T+1, suspension, price limit, unknown execution state and
idempotency conflict through real SQLite.

Run: `python -m pytest -q tests/portfolio/test_risk_route_separation.py`

Expected: FAIL because `RiskRouteApplicationService` is missing.

- [ ] **Step 2: Implement deterministic command orchestration**

```python
class RiskRouteApplicationService:
    def __init__(self, repository: RiskRouteRepository) -> None:
        self._repository = repository
        self._gate = RiskReducingExecutionGate()

    def assess_reducing(
        self,
        *,
        action: RiskChangeKind,
        position: PositionSnapshot,
        target_quantity: int,
        order_quantity: int,
        execution_observation: ReducingExecutionObservation,
        configuration: RiskReducingGateConfiguration,
        actor: str,
        reason: str,
        assessed_at: datetime,
        idempotency_key: str,
    ) -> RiskReducingDecision:
        if action not in {RiskChangeKind.REDUCE, RiskChangeKind.EXIT}:
            raise ValueError("increasing Risk cannot use the reducing service")
        if assessed_at.tzinfo is None:
            raise ValueError("risk-reducing assessed_at must be timezone-aware")
        if not idempotency_key or idempotency_key != idempotency_key.strip():
            raise ValueError("idempotency key must be a non-empty trimmed string")
        restored_position = PositionSnapshot.from_canonical_dict(
            position.to_canonical_dict()
        )
        restored_observation = ReducingExecutionObservation.from_canonical_dict(
            execution_observation.to_canonical_dict()
        )
        restored_configuration = RiskReducingGateConfiguration.from_canonical_dict(
            configuration.to_canonical_dict()
        )
        command_hash = canonical_hash(
            {
                "command": "ASSESS_RISK_REDUCTION",
                "action": action.value,
                "position": restored_position.to_canonical_dict(),
                "target_quantity": target_quantity,
                "order_quantity": order_quantity,
                "execution_observation": restored_observation.to_canonical_dict(),
                "configuration": restored_configuration.to_canonical_dict(),
                "actor": actor,
                "reason": reason,
                "assessed_at": assessed_at.isoformat(),
            }
        )
        replay = self._repository.resolve_reducing_command(
            idempotency_key=idempotency_key,
            command_hash=command_hash,
        )
        if replay is not None:
            return replay
        decision = self._gate.assess(
            action=action,
            position=restored_position,
            target_quantity=target_quantity,
            order_quantity=order_quantity,
            execution_observation=restored_observation,
            configuration=restored_configuration,
            actor=actor,
            reason=reason,
            assessed_at=assessed_at,
        )
        return self._repository.save_reducing_decision(
            decision,
            position=restored_position,
            execution_observation=restored_observation,
            configuration=restored_configuration,
            idempotency_key=idempotency_key,
            command_hash=command_hash,
        )
```

The method immediately rejects OPEN/ADD, canonical-round-trips every evidence
object, computes `canonical_hash` over the full command, resolves replay,
invokes the Gate, saves the full bundle and returns the restored result.

- [ ] **Step 3: Export only the stable public surface**

Export the nine requested H4 symbols from `portfolio.__init__` and export
`RiskRouteApplicationService` from `application.trading_lifecycle.__init__`.
Do not export SQL helpers, JSON helpers or migration internals from package
roots.

Run: `python -m pytest -q tests/portfolio/test_risk_route_separation.py tests/portfolio/test_sqlite_risk_routes.py`

Expected: all H4 domain, service and repository tests pass.

### Task 5: Decision-only human confirmation CLI

**Files:**
- Create: `scripts/assess_risk_reduction.py`
- Create: `tests/scripts/test_assess_risk_reduction.py`

**Interfaces:**
- Consumes: `--database PATH` and `--input PATH` containing a canonical command object.
- Produces: one JSON decision-only response on stdout and one durable H4 decision in SQLite.

- [ ] **Step 1: Add failing CLI tests**

Use a command document with exact fields:

```json
{
  "action": "EXIT",
  "position": {},
  "target_quantity": 0,
  "order_quantity": 100,
  "execution_observation": {},
  "configuration": {},
  "actor": "risk-reduction-operator",
  "reason": "manual exit assessment",
  "assessed_at": "2026-07-20T14:55:01+08:00",
  "idempotency_key": "exit-command-1"
}
```

Fixtures replace the three empty objects with real canonical payloads. Assert
permitted replay, blocked reasons, insufficient reasons, identical decision ID,
no ManualTrade/Fill tables and explicit no-authority output.

Run: `python -m pytest -q tests/scripts/test_assess_risk_reduction.py`

Expected: FAIL because the CLI does not exist.

- [ ] **Step 2: Implement strict parsing and output**

The script reconstructs all inputs through domain readers, calls the service,
and prints sorted JSON containing:

```python
{
    "mode": "DECISION_ONLY",
    "decision_id": str(decision.decision_id),
    "state": decision.state.value,
    "reason_codes": list(decision.reason_codes),
    "position_snapshot_id": str(decision.position_snapshot_id),
    "observation_id": str(decision.observation_id),
    "configuration_id": str(decision.configuration_id),
    "manual_confirmation_required": decision.state is RiskReducingDecisionState.PERMITTED_FOR_MANUAL_CONFIRMATION,
    "order_created": False,
    "execution_boundary": "NO_ORDER_CREATED",
    "trading_authority": "TRADING_AUTHORITY_NOT_GRANTED",
}
```

Unknown/missing input fields fail rather than defaulting. The module imports no
ManualTrade, Fill or broker adapter.

Run: `python -m pytest -q tests/scripts/test_assess_risk_reduction.py`

Expected: all CLI tests pass.

### Task 6: CI build gate and focused regression

**Files:**
- Modify: `pyproject.toml`
- Modify: `.github/workflows/ci.yml`
- Modify: H4 tests only for Ruff/type correctness

**Interfaces:**
- Consumes: editable `.[dev]` install on Python 3.12.
- Produces: package sdist/wheel validation in every push and pull request.

- [ ] **Step 1: Add the build frontend to the dev extra**

```toml
dev = [
    "build>=1.2",
    "pytest>=8.2",
    "ruff>=0.6",
    "mypy>=1.10",
]
```

- [ ] **Step 2: Add the minimal CI build step**

```yaml
      - name: Build package
        run: python -m build
```

No publishing, cache, matrix, deployment or broker job is added.

- [ ] **Step 3: Run focused bounded-context regression**

Run:

```bash
python -m pytest -q tests/portfolio/test_risk_route_separation.py tests/portfolio/test_sqlite_risk_routes.py tests/scripts/test_assess_risk_reduction.py
python -m pytest -q tests/portfolio tests/position tests/execution
python -m ruff check src/market_regime_alpha/portfolio src/market_regime_alpha/application/trading_lifecycle scripts/assess_risk_reduction.py tests/portfolio tests/scripts/test_assess_risk_reduction.py
python -m mypy
```

Expected: every command passes.

### Task 7: Read-only adjacent architecture audit and delivery documents

**Files:**
- Modify: `docs/status/Current-State.md`
- Modify: `docs/status/Capability-Matrix.md`
- Modify: `docs/status/Gap-Register.md`
- Modify: `docs/audit/Current-Main-Code-Audit-2026-08-01.md`
- Create: `docs/audit/H4-Risk-Route-Delivery.md`
- Modify: `docs/roadmap/work-packages/WP-PDL-Hardening-and-Shadow-Readiness.md`
- Modify: `docs/README.md`

**Interfaces:**
- Consumes: exact code/test evidence and read-only adjacent-module findings.
- Produces: current H4 status, H4.5 work package and dependency-ordered H5–H9 plan.

- [ ] **Step 1: Verify adjacent facts without changing those modules**

Use `rg` and direct reads to record whether DailyLoop constructs in-memory
`ModelRegistry`, Entry remains REJECT/WAIT_CONFIRMATION-only, Legacy Web bypasses
canonical Readers, Paper Broker only accepts locally, and QMT/PTrade reject.

- [ ] **Step 2: Record H4.5 as design-only**

Document the new ManualTrade schema/reference, permitted/unexpired validation,
latest Position recheck, confirmer audit, ManualTrade→Fill→Position trace,
partial/cancel/re-decision behavior, migration needs and route permissions.
State that H4 does not depend on H4.5 and H4.5 precedes or belongs within H7.

- [ ] **Step 3: Update H4 and H5–H9 status without inflating authority**

Mark H4 implemented and locally verified only after the full gate passes.
Retain formal PIT/OOS, Entry, Shadow, production and broker non-claims. Describe
H5→H9 business goal, artifacts, states, idempotency, tables, transaction,
recovery, audit, tests, completion and dependencies.

- [ ] **Step 4: Validate documentation**

Run:

```bash
python scripts/check_docs_links.py
python -m pytest -q tests/scripts/test_check_docs_links.py
git diff --check
```

Expected: all pass.

### Task 8: Full gate, review, checkpoint and Draft PR

**Files:** All intended H4, test, CI and documentation files; explicitly exclude `.idea/modules.xml` and generated build products.

**Interfaces:**
- Consumes: completed working tree.
- Produces: one reviewable H4 implementation commit and Draft PR.

- [ ] **Step 1: Run the formal full gate**

```bash
python scripts/check_docs_links.py
python -m pytest -q tests/scripts/test_check_docs_links.py
python -m pytest -q tests/platform
python -m pytest -q
python -m ruff check .
python -m mypy
python -m build
```

Record passed/skipped/failed counts, mypy checked-file count and build artifacts.

- [ ] **Step 2: Run diagnostic out-of-scope commands**

Run `pytest -q` and `mypy src`. Record exact pre-existing path/Legacy failures
separately and fix only H4-introduced diagnostics.

- [ ] **Step 3: Review the complete diff**

Run `git diff --check`, inspect staged and unstaged changes, verify no debug
markers/secrets/personal paths, and perform Standards/Spec review against the
approved design and repository contract.

- [ ] **Step 4: Commit and publish**

Commit the bounded implementation as:

```bash
git commit -m "fix: complete H4 reducing-risk decision route"
```

Push `fix/h4-risk-route-baseline` and open a Draft PR targeting `main` titled
`fix: complete H4 reducing-risk decision route`. The PR must state that it
does not alter ManualTrade/Fill schemas, create orders or grant trading
authority, and that execution integration is deferred to H4.5.
