# H4.5 Risk-Reduction Manual Intent Implementation Plan

> **Status:** CURRENT_SPECIFICATION
> **Authority:** Task-level execution plan for approved H4.5 implementation
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-04
> **Supersedes:** None
> **Superseded By:** None
> **Related Documents:** ../specs/2026-08-04-h4-5-risk-reduction-manual-intent-design.md, ../../roadmap/work-packages/WP-PDL-Hardening-and-Shadow-Readiness.md, ../../architecture/11-Production-Lifecycle-Hardening-and-Shadow-Operations.md
> **Code Evidence:** Plan starts from `feat/h4-5-risk-reduction-manual-intent@6c2d9fa` based on `origin/main@190fede53ab01487e7f339c38cf223b944ac861e`.

> **For agentic workers:** REQUIRED SUB-SKILL: Use `executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert one current, permitted H4 reducing-risk decision into one route-authorized ManualTrade V3 SELL intent after atomic repository reload, T+1 Position rebuild, H5/H6 lineage verification and fresh execution recheck.

**Architecture:** Add immutable H4.5 domain contracts and a route-aware ManualTrade V3, then use one SQLite lifecycle composition repository to reload and replay Decision/H4/H5/H6/Execution authorities inside `BEGIN IMMEDIATE`. Persist each immutable attempt and, only on success, the V3 intent, reducing binding and command atomically; keep later manual Fill handling on the existing ledger.

**Tech Stack:** Python 3.12, frozen dataclasses, Enum/Protocol, canonical JSON/SHA-256, SQLite migrations and partial indexes, argparse, pytest, Ruff, mypy, `python -m build` and GitHub Actions.

## Global Constraints

- Start from `origin/main@190fede53ab01487e7f339c38cf223b944ac861e` on `feat/h4-5-risk-reduction-manual-intent`.
- Preserve and never stage `.idea/modules.xml`.
- Add migration 010; do not rewrite migrations 004, 006, 007, 008 or 009.
- Preserve V1/V2 ManualTrade canonical JSON and Reader semantics.
- Do not put a RiskReducingDecision ID in `risk_decision_id` or create fake Portfolio, Risk, TargetPosition or post-trade authority.
- Confirmation and ManualTrade creation use one SQLite file and one `BEGIN IMMEDIATE`; mismatched repository paths fail closed.
- Only current H6 operational H5 lineage is accepted; V1/synthetic/historical chains fail closed.
- No Fill, Broker Order, automatic Position update, automatic Thesis/Book transition, H7, H8 or H9 behavior.
- Every behavior slice follows red → minimal green → focused regression.
- Every threshold is explicit; operator identity remains unauthenticated and labelled accordingly.

---

### Task 1: ManualTrade V3 route authority

**Files:**
- Modify: `src/market_regime_alpha/execution/manual.py`
- Modify: `src/market_regime_alpha/execution/__init__.py`
- Create: `tests/execution/test_manual_trade_v3_routes.py`

**Interfaces:**
- Produces `ROUTE_AUTHORIZED_MANUAL_TRADE_SCHEMA` and `ManualTradeAuthorityRoute`.
- Extends `ManualTradeRecord` with nullable increasing authority and explicit V3 reducing authority while preserving V1/V2 field dispatch.

- [ ] Add a failing V3 INCREASING canonical round-trip test using this public shape:

```python
record = ManualTradeRecord(
    schema_version=ROUTE_AUTHORIZED_MANUAL_TRADE_SCHEMA,
    authority_route=ManualTradeAuthorityRoute.INCREASING,
    risk_decision_id=risk_id,
    risk_decision_hash=risk_hash,
    portfolio_decision_id=portfolio_id,
    target_position_hash=delta_hash,
    post_trade_snapshot_id=snapshot_id,
    post_trade_snapshot_hash=snapshot_hash,
    risk_reducing_decision_id=None,
    risk_reducing_decision_hash=None,
    risk_reduction_confirmation_id=None,
    risk_reduction_confirmation_hash=None,
    source_position_snapshot_id=None,
    source_position_snapshot_hash=None,
    source_position_snapshot_version=None,
    target_quantity=None,
    order_quantity=None,
    manual_trade_id=ManualTradeId("manual-trade-v3-increasing-test"),
    account_id="account-a",
    symbol="600000.SH",
    side=TradeSide.BUY,
    intended_quantity=100,
    expected_price_lower=9.9,
    expected_price_upper=10.1,
    state=ManualOrderState.RECORDED,
    filled_quantity=0,
    version=0,
    actor="operator-a",
    reason="approved increasing intent",
    created_at=NOW,
    updated_at=NOW,
    last_actor="operator-a",
    last_reason="approved increasing intent",
    position_book_id=book_id,
    thesis_id=thesis_id,
    opportunity_id=opportunity_id,
)
```

- [ ] Run `python -m pytest -q tests/execution/test_manual_trade_v3_routes.py`; expect missing symbols.
- [ ] Implement V3 INCREASING validation and exact canonical field dispatch; rerun to PASS.
- [ ] Add a failing V3 REDUCING round trip and parameterized mutual-exclusivity, SELL, quantity and hash-tamper tests.
- [ ] Implement the REDUCING family and prove V1/V2 fixture JSON still round-trips unchanged.
- [ ] Run `python -m ruff check src/market_regime_alpha/execution/manual.py tests/execution/test_manual_trade_v3_routes.py`.

### Task 2: Directive, Policy and Attempt domain

**Files:**
- Create: `src/market_regime_alpha/execution/risk_reduction.py`
- Modify: `src/market_regime_alpha/execution/__init__.py`
- Create: `tests/execution/test_risk_reduction_confirmation_domain.py`

**Interfaces:**
- Produces `OperationalExitDirectiveV2.create(...)`, `RiskReductionConfirmationPolicy.create(...)`, `RiskReductionConfirmationAttempt.create(...)` and strict Readers.
- Produces enums `RequiredAuthorityRoute`, `OperatorAuthenticationRequirement` and `RiskReductionConfirmationState`.

- [ ] Write failing Directive tests for REDUCE/EXIT, exact ExitAssessment/H5/H6/Position scope, fixed authority ceiling and rejected WAIT/DATA_INSUFFICIENT.
- [ ] Implement content-derived Directive ID/hash and canonical Reader; rerun to PASS.
- [ ] Write failing Policy tests proving every threshold is required, positive/finite and identity-affecting.
- [ ] Implement Policy with `RECORDED_ACTOR_ONLY` and fixed `OPERATOR_AUTHENTICATION_NOT_ESTABLISHED` limitation.
- [ ] Write failing Attempt tests for all six states, optional ManualTrade only on CONFIRMED_INTENT, sorted reasons, canonical round trip and tamper.
- [ ] Implement Attempt and run the complete domain file plus Ruff.

### Task 3: Public verified authority bundle reads

**Files:**
- Modify: `src/market_regime_alpha/portfolio/repositories.py`
- Modify: `src/market_regime_alpha/portfolio/sqlite_risk_routes.py`
- Modify: `src/market_regime_alpha/position/thesis_health.py`
- Modify: `src/market_regime_alpha/position/sqlite_thesis_health.py`
- Modify: `src/market_regime_alpha/application/operational_research/composite_repository.py`
- Modify: `tests/portfolio/test_sqlite_risk_routes.py`
- Modify: `tests/position/test_sqlite_thesis_health.py`
- Modify: `tests/application/operational_research/test_sqlite_composite_repository.py`

**Interfaces:**

```python
def get_verified_reducing_decision_bundle(
    decision_id: ArtifactId,
) -> VerifiedRiskReducingDecisionBundle: ...

def get_verified_observation_bundle(
    observation_id: ArtifactId,
) -> VerifiedThesisHealthBundle: ...

def get_source_package_paths(
    manifest_id: ArtifactId,
) -> tuple[Path, Path]: ...
```

- [ ] Add failing public-read tests that save, restart, read the full H4/H5 bundle and observe Gate/Builder replay.
- [ ] Add frozen bundle result types and public Protocol methods without exposing SQLite rows or private helpers.
- [ ] Add H4/H5 projection and canonical tamper tests through the new methods.
- [ ] Add the existing H6 source-locator method to its Protocol and prove unknown/mismatched manifest reads fail.
- [ ] Run the three focused repository files.

### Task 4: Migration 010 and schema validation

**Files:**
- Create: `src/market_regime_alpha/execution/migrations/010_risk_reduction_manual_intent_up.sql`
- Create: `src/market_regime_alpha/execution/migrations/010_risk_reduction_manual_intent_down.sql`
- Create: `src/market_regime_alpha/application/trading_lifecycle/sqlite_risk_reduction.py`
- Modify: `src/market_regime_alpha/execution/sqlite_repository.py`
- Modify: `pyproject.toml` only if package-data discovery requires an explicit addition
- Create: `tests/execution/test_migration_010_risk_reduction.py`

**Interfaces:**
- Adds route columns to `manual_trade_records` and append-only Directive/Attempt/Command/reducing-binding tables.
- Exposes `RISK_REDUCTION_CONFIRMATION_UP_MIGRATION`, `RISK_REDUCTION_CONFIRMATION_DOWN_MIGRATION` and schema validation on repository initialization.

- [ ] Build a failing migration test from a migration-004/006 database containing V1 and V2 trades, events and fills.
- [ ] Implement safe table rebuild/copy so historical aggregate/event JSON remains byte-identical and projected route becomes INCREASING.
- [ ] Add database CHECK, FK, partial-unique-index and append-only-trigger assertions.
- [ ] Add repeat migration, weak schema, spoofed trigger and isolated down tests; down with REDUCING rows must fail instead of losing authority.
- [ ] Run `python -m pytest -q tests/execution/test_risk_reduction_migration.py` and migration-related V1/V2 execution tests.

### Task 5: Increasing and reducing trace bindings

**Files:**
- Modify: `src/market_regime_alpha/execution/repositories.py`
- Modify: `src/market_regime_alpha/execution/sqlite_repository.py`
- Modify: `src/market_regime_alpha/execution/sqlite_traceability.py`
- Modify: `src/market_regime_alpha/application/trading_lifecycle/traceable_execution.py`
- Modify: `tests/execution/test_traceable_execution_chain.py`
- Create: `tests/execution/test_reducing_trace_binding.py`

**Interfaces:**

```python
def create_risk_reducing_trade(
    record: ManualTradeRecord,
    *,
    book: PositionBook,
    decision: RiskReducingDecision,
    attempt: RiskReductionConfirmationAttempt,
    idempotency_key: str,
    command_hash: str,
) -> tuple[PositionBook, ManualTradeRecord]: ...
```

- [ ] Change new increasing application creation to V3/INCREASING and keep repository acceptance of historical V2 fixtures.
- [ ] Add failing reducing binding create/read/restart tests proving the existing OPEN book is reused and no book event is appended.
- [ ] Implement separate reducing validation and binding insertion without calling `create_traceable_trade()`.
- [ ] Add binding/projection tamper tests and a stored-route hook used by `get_trade`, transition and base `append_fill`.
- [ ] Update book trade/fill queries to cover both binding tables and reject a missing, duplicated or route-wrong binding.
- [ ] Run all execution trace tests.

### Task 6: Position projector compatibility

**Files:**
- Modify: `src/market_regime_alpha/position/authority.py`
- Modify: `tests/position/test_a_share_t_plus_one_authority.py`
- Modify: `tests/execution/test_reducing_trace_binding.py`

**Interfaces:**
- `PositionProjector.project_book()` and `project_book_t_plus_one()` accept traceable V2 and route-authorized V3 records after exact book scope validation.

- [ ] Add a failing V3 SELL Fill projection test from one V3 BUY and one V3 REDUCING trade.
- [ ] Implement schema-set validation without weakening book/Thesis/Opportunity/account/symbol checks.
- [ ] Prove partial SELL reduces quantity, full EXIT reaches CLOSED Position state and no H4.5 service creates the Fill.
- [ ] Run A-share T+1 and projector suites.

### Task 7: H5/H6 operational lineage validator

**Files:**
- Modify: `src/market_regime_alpha/execution/risk_reduction.py`
- Create: `tests/execution/test_risk_reduction_operational_lineage.py`

**Interfaces:**

```python
def verify_h5_h6_operational_lineage(
    *,
    observation: ThesisHealthObservationV2,
    bundle: ThesisHealthInputBundle,
    composite: VerifiedCompositeOperationalManifest,
) -> None: ...
```

- [ ] Add one failing success test using the existing H6→Research→Signal→Path→H5 fixture chain.
- [ ] Require exact manifest ID/hash in Market/Theme/Capital/Candidate/Signal/Path Envelopes and exact direct component lineage.
- [ ] Add rejected latest-H5, V1 H5, historical/synthetic lineage, non-VERIFIED H6, manifest ID/hash mismatch and unbound-component tests.
- [ ] Run the H6/H5 integration and new lineage file.

### Task 8: Atomic confirmation repository and Application Service

**Files:**
- Modify: `src/market_regime_alpha/application/trading_lifecycle/sqlite_risk_reduction.py`
- Create: `src/market_regime_alpha/application/trading_lifecycle/risk_reduction_lineage.py`
- Create: `src/market_regime_alpha/application/trading_lifecycle/risk_reduction_confirmation.py`
- Modify: `src/market_regime_alpha/application/trading_lifecycle/__init__.py`
- Create: `tests/application/test_risk_reduction_confirmation.py`

**Interfaces:**

```python
@dataclass(frozen=True, slots=True)
class ConfirmRiskReductionCommand:
    risk_reducing_decision_id: ArtifactId
    risk_reducing_decision_hash: str
    exit_directive_id: ArtifactId
    exit_directive_hash: str
    thesis_health_observation_id: ArtifactId
    thesis_health_observation_hash: str
    composite_manifest_id: ArtifactId
    composite_manifest_hash: str
    calendar: TradingCalendarArtifact
    symbol_session_statuses: tuple[SymbolTradingSessionStatus, ...]
    execution_observation: ReducingExecutionObservation
    policy: RiskReductionConfirmationPolicy
    expected_price_lower: float
    expected_price_upper: float
    confirmed_at: datetime
    actor: str
    reason: str
    idempotency_key: str
```

- [ ] Add a failing legal REDUCE test that seeds one same-file Decision/H4/H5/H6/Execution lifecycle and expects attempt + V3 SELL intent with no Fill.
- [ ] Implement path-consistency checks and preflight public repository reads.
- [ ] Implement one `BEGIN IMMEDIATE` in-transaction reload/replay, current Position projection, Directive/current Decision/H5/H6 validation, fresh Gate replay and price range validation.
- [ ] Add legal EXIT, existing-book reuse, no-new-book/no-Fill/no-Broker assertions.
- [ ] Add non-permitted/expired/hash/scope/REDUCE-zero states and every Position/market recheck failure.
- [ ] Add current Thesis APPROVED, INVALIDATED EXIT and CLOSED rejection; Opportunity/thesis version mismatch tests.
- [ ] Add multiple failed attempts, same-command replay, conflicting key, one-confirmed-only and injected rollback tests.
- [ ] Reread attempt/trade/binding projections before commit and run the complete application file.

### Task 9: Later manual Fill compatibility

**Files:**
- Modify: `tests/application/test_risk_reduction_confirmation.py`
- Modify: `tests/execution/test_reducing_trace_binding.py`

**Interfaces:**
- Reuses `TraceableManualExecutionApplicationService.record_fill()`, `trades_for_book()`, `fills_for_book()` and `rebuild_a_share_position()`.

- [ ] Record a later partial SELL Fill against the confirmed V3 trade and prove it appears in trade/fill book queries and reduces the projected Position.
- [ ] Prove the same H4 decision cannot create another intent after partial Fill.
- [ ] Record the full remaining EXIT Fill, rebuild CLOSED Position and prove explicit later `close_position_book()` can consume it while H4.5 itself never closes the book.
- [ ] Run execution, position and application focused files.

### Task 10: Confirmation CLI

**Files:**
- Modify: `src/market_regime_alpha/data/trading_calendar.py`
- Create: `scripts/confirm_risk_reduction.py`
- Create: `tests/scripts/test_confirm_risk_reduction.py`

**Interfaces:**
- Adds strict canonical `TradingCalendarArtifact.from_canonical_dict()` for a verified calendar JSON path.
- CLI accepts IDs/hashes and canonical calendar/status/recheck/policy files, never aggregate Decision/Thesis/Position/Trade JSON.

- [ ] Add failing calendar canonical round-trip/tamper tests and implement the Reader.
- [ ] Add a failing CLI success test against a seeded lifecycle DB and implement argument parsing plus service composition.
- [ ] Assert the fixed success strings and `manual_trade_id`, with `fill_id`/broker output absent.
- [ ] Add expired/position-changed/blocked failure output tests with null `manual_trade_id` and full evidence IDs/hashes.
- [ ] Prove forbidden aggregate arguments are unknown and run CLI tests plus Ruff.

### Task 11: Compatibility and regression closure

**Files:**
- Modify only affected existing tests where new creation correctly emits V3.
- Test: `tests/execution/`, `tests/portfolio/`, `tests/position/`, `tests/application/`, H4/H5/H6 focused files.

- [ ] Run V1 manual execution tests and historical V1 canonical fixtures.
- [ ] Run V2 traceable execution and migration 006 compatibility tests.
- [ ] Run H4 focused: `tests/portfolio/test_risk_route_domain.py tests/portfolio/test_risk_route_separation.py tests/portfolio/test_sqlite_risk_routes.py tests/scripts/test_assess_risk_reduction.py`.
- [ ] Run H5 focused: Thesis-health domain, repository, service, CLI and V2 assessment tests.
- [ ] Run H6 focused: operational research, V2 input and operational CLI tests.
- [ ] Run `python -m pytest -q tests/execution tests/portfolio tests/position tests/application` and fix only H4.5-caused failures.

### Task 12: Status, audit and delivery evidence

**Files:**
- Create: `docs/audit/H4-5-Risk-Reduction-Manual-Intent-Delivery.md`
- Modify: `docs/README.md`
- Modify: `docs/status/Current-State.md`
- Modify: `docs/status/Capability-Matrix.md`
- Modify: `docs/status/Gap-Register.md`
- Modify: `docs/roadmap/work-packages/WP-PDL-Hardening-and-Shadow-Readiness.md`

- [ ] Update implementation facts only after focused tests pass; retain every evidence ceiling and add `H4_V2_REDUCE_REQUIRES_POSITIVE_REMAINDER`.
- [ ] Record migration, atomicity, Fill compatibility, rollback and exact non-goals in the audit.
- [ ] Run `python scripts/check_docs_links.py` and `git diff --check`.

### Task 13: Final gate, review, commits and Draft PR

**Files:**
- Review every changed file and staged path; `.idea/modules.xml` remains unstaged.

- [ ] Run final focused suites for H4.5, execution context and H4/H5/H6 regression.
- [ ] Run:

```bash
python -m pytest -q
python -m ruff check .
python -m mypy
python -m build
python scripts/check_docs_links.py
git diff --check
```

- [ ] Remove only locally generated untracked build artifacts after recording PASS.
- [ ] Inspect `git diff`, `git diff --cached --check`, staged paths and credentials/personal paths.
- [ ] Create dependency-coherent semantic commits, push `feat/h4-5-risk-reduction-manual-intent`, and open Draft PR `feat: bridge reducing-risk decisions to manual intent`.
- [ ] Inspect both push and PR GitHub Actions jobs; fix only failures introduced by this branch and rerun until green.
- [ ] Bind the delivery audit and final report to the final commit SHA and exact observed counts.
