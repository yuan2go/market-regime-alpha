# Phase A Correctness Convergence and Research Shadow Operations Implementation Plan

> **Status:** CURRENT_SPECIFICATION
> **Authority:** Executable Phase A implementation plan
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-08-10
> **Supersedes:** None
> **Superseded By:** None
> **Related Documents:** ../specs/2026-08-10-phase-a-correctness-shadow-operations-design.md, ../../architecture/16-Phase-A-Correctness-and-Research-Shadow-Operations.md
> **Code Evidence:** Baseline `4ab425d956f76c1e06d410592ff4c7842f2cc574`; implementation evidence is recorded in ../../audit/Phase-A-Correctness-Shadow-Operations-Delivery.md

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve future Research Shadow sample semantics through one canonical execution boundary, cross-session State, explicit policy/target lineage, an operational Shadow loop, a frozen full-population panel and truthful read models.

**Architecture:** Extend the existing Continuous Runtime and bounded PostgreSQL authorities with append-only V2 overlays. Keep all V1 payloads/readers immutable, use stable content-addressed series/policy/target identities, and orchestrate existing Shadow/Outcome/Evaluation owners through one application service.

**Tech Stack:** Python 3.12 dataclasses/enums, PostgreSQL 16/psycopg 3, immutable canonical JSON/SHA-256 Artifacts, argparse CLI, pytest, Ruff, mypy, setuptools/uv.

## Global Constraints

- Baseline is `origin/main` at `4ab425d956f76c1e06d410592ff4c7842f2cc574` after an explicit fetch on 2026-08-10.
- PostgreSQL 16 is the only persistent Runtime/Authority database and must fail closed.
- Do not edit migrations 001–037 or rewrite historical V1 Artifacts.
- Do not create Order, Fill, Broker or Position mutation.
- Do not optimize factors, State parameters or target horizons.
- Fixture and simulated-clock evidence must remain `NOT_PROSPECTIVE_EVIDENCE`.
- Preserve existing MR1 next-session 10:30 and `daily_research` historical identities.
- Implement production code continuously; run focused smoke checks during implementation and the complete gate once at the end.

---

### Task 1: Canonical/Legacy authority catalog and guard

**Files:**
- Create: `src/market_regime_alpha/application/authority_boundary.py`
- Modify: `src/market_regime_alpha/daily_research/__init__.py`
- Modify: `tests/architecture/test_legacy_import_boundary.py`
- Create: `tests/architecture/test_canonical_execution_boundary.py`
- Modify: `docs/architecture/12-Canonical-Runtime-and-Legacy-Migration.md`

**Interfaces:**
- Produces: `canonical_authority_catalog() -> CanonicalAuthorityCatalog`
- Produces: `LegacyCapability.READ`, `REPLAY`, `MIGRATION`, `CHARACTERIZATION`
- Invariant: canonical compositions cannot import `daily_research` or `dividend_t`; canonical Entry cannot enumerate `ENTER`.

- [ ] **Step 1: Add characterization guards**

```python
def test_canonical_entry_can_never_enter() -> None:
    assert {item.value for item in EntryAssessmentState} == {
        "REJECT", "WAIT_CONFIRMATION"
    }

def test_canonical_compositions_do_not_import_legacy_daily_research() -> None:
    assert scan_canonical_imports("market_regime_alpha.daily_research") == ()
```

- [ ] **Step 2: Add the typed catalog**

```python
@dataclass(frozen=True, slots=True)
class CanonicalAuthorityCatalog:
    daily_runtime: str
    lifecycle_runtime: str
    decision_owner: str
    entry_owner: str
    legacy_namespaces: tuple[LegacyNamespace, ...]
```

- [ ] **Step 3: Run the architecture smoke tests**

Run: `python -m pytest -q tests/architecture/test_legacy_import_boundary.py tests/architecture/test_canonical_execution_boundary.py`

Expected: PASS with no canonical-to-Legacy executable dependency.

- [ ] **Step 4: Checkpoint commit**

```bash
git add src/market_regime_alpha/application/authority_boundary.py src/market_regime_alpha/daily_research/__init__.py tests/architecture docs/architecture/12-Canonical-Runtime-and-Legacy-Migration.md
git commit -m "feat: enforce canonical execution boundary"
```

### Task 2: State Policy and stable State Series contracts

**Files:**
- Create: `src/market_regime_alpha/research/state_system/authority.py`
- Modify: `src/market_regime_alpha/research/state_system/common.py`
- Modify: `src/market_regime_alpha/research/state_system/configuration.py`
- Modify: `src/market_regime_alpha/research/state_system/__init__.py`
- Create: `tests/research/state_system/test_state_authority_v2.py`
- Create: `tests/research/state_system/test_state_policy_authority.py`

**Interfaces:**
- Produces: `StateTransitionPolicy.create(domain, policy_version, thresholds) -> StateTransitionPolicy`
- Produces: `DynamicPoolPolicy.create(policy_version, allowed states, dwell, coverage, material threshold) -> DynamicPoolPolicy`
- Produces: `StateSeries.create(domain, logical scope, family, mode, universe/model/policy references) -> StateSeries`
- Extends: `StateLineage` with optional V2 `state_series_*` and `state_policy_*` fields while restoring V1 exactly.

- [ ] **Step 1: Define immutable policy contracts**

```python
policy = StateTransitionPolicy.create(
    domain="MARKET_REGIME",
    policy_version="free-data-v1",
    thresholds=TransitionThresholds(
        enter_threshold=Decimal("0.60"),
        exit_threshold=Decimal("0.40"),
        hysteresis=Decimal("0.20"),
        confirmation_count=1,
        minimum_dwell_seconds=0,
        minimum_coverage=Decimal("0.50"),
        missing_data_policy=MissingDataPolicy.FAIL_CLOSED,
    ),
)
assert policy.policy_hash == canonical_hash(policy.identity_payload())
```

- [ ] **Step 2: Define stable series identity**

```python
series = StateSeries.create(
    domain="MARKET_REGIME",
    logical_scope="A_SHARE_MARKET",
    research_family="FREE_DATA_STATEFUL_RESEARCH",
    authority_mode="SHADOW",
    universe_policy=universe_policy,
    model=model_reference,
    state_policy=policy.reference,
)
```

- [ ] **Step 3: Add V1/V2 lineage restoration**

V1 payloads omit all V2 keys and preserve their historical hash. V2 payloads
require a complete Series/Policy reference set; partial references fail closed.

- [ ] **Step 4: Run contract smoke tests**

Run: `python -m pytest -q tests/research/state_system/test_state_authority_v2.py tests/research/state_system/test_state_policy_authority.py`

Expected: PASS for policy hash/version, stable series and V1 compatibility.

### Task 3: PostgreSQL cross-session State V2 and Dynamic Pool series

**Files:**
- Create: `src/market_regime_alpha/persistence/postgres/migrations/038_state_series_policy_authority.sql`
- Modify: `src/market_regime_alpha/application/state_system/repository.py`
- Modify: `src/market_regime_alpha/application/state_system/postgres_repository.py`
- Modify: `src/market_regime_alpha/application/state_system/free_data_composition.py`
- Modify: `src/market_regime_alpha/research/state_system/market.py`
- Modify: `src/market_regime_alpha/research/state_system/etf_rotation.py`
- Modify: `src/market_regime_alpha/research/state_system/theme_rotation.py`
- Modify: `src/market_regime_alpha/research/state_system/capital.py`
- Modify: `src/market_regime_alpha/research/state_system/pool.py`
- Create: `tests/persistence/postgres/test_cross_session_state_v2.py`
- Modify: `tests/persistence/postgres/test_migrator.py`

**Interfaces:**
- Produces: `read_current_series_state(series) -> StoredSeriesState | None`
- Produces: `read_current_series_pool(series) -> DynamicStockPoolVersion | None`
- Produces: `verify_series_chain(series_id) -> StateSeriesChainVerification`
- Consumes: `StateArtifactWrite.series` and `StateArtifactWrite.policy`.

- [ ] **Step 1: Append migration 038**

Create immutable Policy/Series tables, per-domain series links and a
CAS/fenced series head. Bind links to `continuous_runtime_tick` and domain
Artifact tables with explicit foreign keys. Install append-only triggers.

- [ ] **Step 2: Implement run-scoped fencing and cross-run temporal CAS**

```text
same run     → fence token cannot regress
different run → as_of_time must advance; token restarts are valid
all writes   → expected predecessor must equal locked series head
```

- [ ] **Step 3: Replace run-scoped composition lookup**

Remove `f"{run_id}:{logical_scope}"` from new writes. Build the series from
stable Universe policy, model configuration and State policy references.

- [ ] **Step 4: Bind policy/series into V2 State and Pool payloads**

Use `/v2` schema tags for new payloads; Reader helpers accept `/v1` and `/v2`
and reconstruct exact lineage.

- [ ] **Step 5: Run PostgreSQL State smoke tests**

Run: `python -m pytest -q tests/persistence/postgres/test_cross_session_state_v2.py tests/persistence/postgres/test_state_system_schema.py`

Expected: PASS for D1→D2→D3, Friday→Monday, same-day ticks, reset, stale CAS,
run-scoped fencing, restart and replay.

- [ ] **Step 6: Checkpoint commit**

```bash
git add src/market_regime_alpha/research/state_system src/market_regime_alpha/application/state_system src/market_regime_alpha/persistence/postgres/migrations/038_state_series_policy_authority.sql tests/research/state_system tests/persistence/postgres
git commit -m "feat: add cross-session state authority"
```

### Task 4: Outcome Target Protocol and targeted factual labels

**Files:**
- Create: `src/market_regime_alpha/application/research_evaluation/targets.py`
- Create: `src/market_regime_alpha/application/research_evaluation/target_outcome.py`
- Create: `src/market_regime_alpha/application/research_evaluation/postgres_target_outcome.py`
- Modify: `src/market_regime_alpha/application/research_evaluation/__init__.py`
- Create: `src/market_regime_alpha/persistence/postgres/migrations/039_outcome_target_protocol.sql`
- Create: `tests/research_evaluation/test_target_protocol.py`
- Create: `tests/persistence/postgres/test_target_outcome_authority.py`

**Interfaces:**
- Produces: `OutcomeTargetProtocol`, `TargetDefinition`, `LabelInterval`, `BarrierDefinition`
- Produces: `build_targeted_shadow_outcome(decision, protocol, source archive, verified dataset, created_at) -> TargetedShadowOutcome`
- Produces: `PostgresTargetOutcomeRepository.register_protocol/settle/replay`

- [ ] **Step 1: Add content-addressed target contracts**

```python
TargetDefinition(
    target_version="v1",
    label_start="T+1 09:30 Asia/Shanghai",
    label_end="T+1 10:30 Asia/Shanghai",
    return_reference=ReturnReference.DECISION_REFERENCE_PRICE,
    checkpoint=Checkpoint.CLOSE_1030,
    barriers=(Decimal("-0.01"), Decimal("0.01"), Decimal("0.02")),
    required_timeframes=(Timeframe.MINUTE_1,),
    tradability_policy=TradabilityPolicy.OBSERVE_WITH_CONDITION,
    corporate_action_policy=CorporateActionPolicy.MARK_UNAVAILABLE,
    missing_quote_policy=MissingQuotePolicy.PARTIAL,
)
```

- [ ] **Step 2: Build labels without leakage**

Require every consumed bar's market date, event interval and `available_at` to
fit the target. Missing checkpoint, suspension, corporate action and missing
quotes follow the protocol's explicit fail-closed policies.

- [ ] **Step 3: Persist multiple protocols per frozen Decision**

The unique semantic scope is `(shadow_decision_id, target_protocol_id)`.
Identical settlement is idempotent; conflicting content is rejected.

- [ ] **Step 4: Run target smoke tests**

Run: `python -m pytest -q tests/research_evaluation/test_target_protocol.py tests/persistence/postgres/test_target_outcome_authority.py`

Expected: PASS for multiple horizons, interval boundaries, barriers,
corporate actions, missing checkpoints and no future leakage.

### Task 5: Research Shadow operating loop and Prospective Attestation

**Files:**
- Create: `src/market_regime_alpha/application/shadow_research/operations.py`
- Create: `src/market_regime_alpha/application/shadow_research/attestation.py`
- Create: `src/market_regime_alpha/application/shadow_research/postgres_attestation.py`
- Modify: `src/market_regime_alpha/application/shadow_research/__init__.py`
- Modify: `src/market_regime_alpha/application/shadow_research/postgres_repository.py`
- Create: `src/market_regime_alpha/cli/research_shadow.py`
- Modify: `pyproject.toml`
- Create: `src/market_regime_alpha/persistence/postgres/migrations/040_research_shadow_operations.sql`
- Create: `tests/cli/test_research_shadow_cli.py`
- Create: `tests/persistence/postgres/test_research_shadow_operations.py`

**Interfaces:**
- Produces: `ResearchShadowOperationsService.schedule/run/attach_summary/outcome_pending/settle/build_evaluation/report/replay/resume/invalidate`
- Produces: `ProspectiveEvidenceAttestation` with `prospective_proven is False`.

- [ ] **Step 1: Compose existing owners**

The service accepts the existing Continuous, Shadow, V1 Outcome, Target
Outcome and Evaluation repositories. It contains no acquisition/model/trading
implementation.

- [ ] **Step 2: Add crash-safe status transitions**

Duplicate commands reload matching owner Artifacts. Failed sessions may resume;
invalidated/settled terminal states cannot be mutated. No-candidate and
non-action Summary outcomes remain valid.

- [ ] **Step 3: Add attestation mechanics**

Bind Runtime clock mode, run/tick, source acquisition receipts, frozen Summary,
Decision freeze, Outcome availability and code revision. Replay/Fixture/
Simulated modes cannot impersonate prospective evidence.

- [ ] **Step 4: Add `research-shadow` subcommands**

```text
schedule, run, attach-summary, freeze, outcome-pending, settle,
build-evaluation, report, replay, resume, invalidate
```

- [ ] **Step 5: Run operating-loop smoke tests**

Run: `python -m pytest -q tests/cli/test_research_shadow_cli.py tests/persistence/postgres/test_research_shadow_operations.py`

Expected: PASS for schedule→settle, duplicate invocation, CAS, crash/resume,
invalidate, unavailable Outcome and deterministic replay.

### Task 6: Research Evaluation Dataset V2 full panel

**Files:**
- Create: `src/market_regime_alpha/application/research_evaluation/panel_v2.py`
- Create: `src/market_regime_alpha/application/research_evaluation/postgres_panel_v2.py`
- Modify: `src/market_regime_alpha/application/research_evaluation/__init__.py`
- Create: `src/market_regime_alpha/persistence/postgres/migrations/041_research_evaluation_panel_v2.sql`
- Create: `tests/research_evaluation/test_panel_v2.py`
- Create: `tests/persistence/postgres/test_research_evaluation_panel_v2.py`

**Interfaces:**
- Produces: `FactorExposureRecord`, `ResearchPanelRow`, `EvaluationDecisionSliceV2`, `FrozenResearchEvaluationDatasetV2`
- Produces: `build_evaluation_panel_v2(decision, pool, candidates, targeted outcome, factor evidence)` and append-only PostgreSQL register/replay.

- [ ] **Step 1: Define full-row identity**

Rows include explicit `NOT_OBSERVED` factor values, all eligibility/pool/
candidate dispositions, ranks/scores, State/Signal/Forecast owners, model,
configuration, policy, target and Outcome labels.

- [ ] **Step 2: Join exact frozen owner Artifacts**

Union Dynamic Pool members and CandidateSet records. Reject symbol, hash,
Decision, Policy or Target mismatches. Do not query mutable production tables
for missing research values.

- [ ] **Step 3: Persist and replay V2**

Register immutable artifact path plus normalized row identities and exact
Decision/Target/Outcome foreign keys. Reader reload and recompute identity.

- [ ] **Step 4: Run panel smoke tests**

Run: `python -m pytest -q tests/research_evaluation/test_panel_v2.py tests/persistence/postgres/test_research_evaluation_panel_v2.py`

Expected: PASS for full population, inclusion/exclusion, factor exposure,
target binding and replay.

- [ ] **Step 5: Checkpoint commit**

```bash
git add src/market_regime_alpha/application/research_evaluation src/market_regime_alpha/application/shadow_research src/market_regime_alpha/cli/research_shadow.py src/market_regime_alpha/persistence/postgres/migrations/039_outcome_target_protocol.sql src/market_regime_alpha/persistence/postgres/migrations/040_research_shadow_operations.sql src/market_regime_alpha/persistence/postgres/migrations/041_research_evaluation_panel_v2.sql pyproject.toml tests
git commit -m "feat: operationalize targeted research shadow evaluation"
```

### Task 7: Runtime Query and Observability hardening

**Files:**
- Modify: `src/market_regime_alpha/application/runtime_operations/query.py`
- Modify: `src/market_regime_alpha/application/runtime_operations/observability.py`
- Modify: `src/market_regime_alpha/cli/continuous_research.py`
- Create: `tests/persistence/postgres/test_runtime_readmodel_v2.py`
- Modify: `tests/cli/test_continuous_research_cli.py`

**Interfaces:**
- Extends: `CanonicalDagNodeType` with Shadow/Outcome/Target/Evaluation/Attestation.
- Produces: `inspect_trading_date(trading_date) -> CanonicalRuntimeInspection`.
- Emits: metric observations with `status = OBSERVED | UNKNOWN | NOT_OBSERVED`.

- [ ] **Step 1: Correct all owner mappings**

Use the owner table in the design. Signal and Forecast must never project as
`STATE_SYSTEM`.

- [ ] **Step 2: Add Shadow DAG projection**

Join session→decision→outcome→target→evaluation→attestation by immutable IDs
and expose partial/blocked/recovered paths without recomputation.

- [ ] **Step 3: Replace fake metrics**

Count Candidate records and Pool members from owner rows; count fence and replay
failures only from recorded events. Emit unknown observations when an owner has
no evidence.

- [ ] **Step 4: Run read-model smoke tests**

Run: `python -m pytest -q tests/persistence/postgres/test_runtime_readmodel_v2.py tests/cli/test_continuous_research_cli.py`

Expected: PASS for owners, partial/recovered path, Shadow DAG and no fake zero.

### Task 8: Documentation, runbook and concentrated integration tests

**Files:**
- Modify: `docs/status/Current-State.md`
- Modify: `docs/status/Capability-Matrix.md`
- Modify: `docs/status/Gap-Register.md`
- Modify: `docs/architecture/11-Production-Lifecycle-Hardening-and-Shadow-Operations.md`
- Modify: `docs/runbooks/Stateful-Research-Runtime.md`
- Create: `docs/runbooks/Research-Shadow-Operations.md`
- Create: `docs/audit/Phase-A-Correctness-Convergence-Delivery.md`
- Modify: `docs/README.md`
- Modify: `tests/persistence/postgres/test_free_data_stateful_runtime.py`
- Modify: `tests/persistence/postgres/test_migrator.py`

**Interfaces:**
- Documents: exact Authority boundaries, commands, migrations 038–041,
  rollback/forward repair and evidence non-claims.
- Tests: end-to-end T Shadow Decision → T+1 target settlement → V2 panel → replay.

- [ ] **Step 1: Add the end-to-end PostgreSQL test**

Use recorded Provider data and real PostgreSQL; assert engineering readiness
only and preserve `prospective_proven is False`.

- [ ] **Step 2: Update current-state authorities**

Record implemented mechanics separately from external evidence blockers. Remove
the closed namespace/state-policy/target/ops/read-model gaps and retain formal
PIT/OOS/Alpha/Entry/Production blockers.

- [ ] **Step 3: Add operator runbook and repair procedures**

Document idempotent daily commands, missed T+1, duplicate settlement,
invalidation, replay, stale CAS and PostgreSQL unavailability.

### Task 9: Final gate, review, verification and publication

**Files:**
- Create: `docs/evidence/Phase-A-Engineering-Verification.md`
- Modify: any implementation/test/docs files required by gate fixes.

**Interfaces:**
- Produces: exact-SHA local verification record with per-command status.
- Produces: checkpoint commits, pushed branch and Draft PR.

- [ ] **Step 1: Sync the frozen environment**

Run: `uv sync --frozen --extra dev --extra postgres`

Expected: PASS.

- [ ] **Step 2: Run the complete local quality gate**

```bash
uv run python scripts/check_docs_links.py
uv run python -m pytest -q tests/scripts/test_check_docs_links.py
uv run python -m pytest -q tests/platform
uv run python -m pytest -q
uv run python -m ruff check .
uv run python -m mypy
uv run python -m build
git diff --check
```

Expected: every command PASS; PostgreSQL authority tests use the real fixture.

- [ ] **Step 3: Review standards and specification coverage**

Inspect the full `origin/main...HEAD` diff, migrations, backward Readers,
authority ceilings, secrets and unrelated files. Fix all actionable findings.

- [ ] **Step 4: Generate and bind verification evidence**

Record the tested commit SHA and every command as `PASS`, `FAIL`, `NOT_RUN` or
`BLOCKED`. Record GitHub Actions as `CI_NOT_RUN` until actually observed.

- [ ] **Step 5: Commit, push and open Draft PR**

```bash
git push -u origin agent/phase-a-correctness-shadow-ops
gh pr create --draft --base main --head agent/phase-a-correctness-shadow-ops
```

Expected: Draft PR targets latest `main`; no merge is performed.
