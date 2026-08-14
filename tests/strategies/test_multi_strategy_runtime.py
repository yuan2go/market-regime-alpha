from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from market_regime_alpha.application.continuous_research.journal import (
    RuntimeArtifactReference,
)
from market_regime_alpha.core.identity import ArtifactId, ModelId, StrategyId
from market_regime_alpha.core.time import DecisionTime
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.evidence.envelope import ArtifactEnvelope, EvidenceAuthority
from market_regime_alpha.platform.runtime_governance import RuntimeAuthorityMode
from market_regime_alpha.research.candidate_discovery.contracts import (
    CandidateRecord,
    CandidateSelectionStatus,
    CandidateSet,
)
from market_regime_alpha.research.capital_evolution.contracts import (
    CapitalEvolutionState,
)
from market_regime_alpha.research.market_regime.contracts import MarketState
from market_regime_alpha.research.theme_rotation.contracts import RotationState
from market_regime_alpha.strategies.contracts import (
    CanonicalStrategyAction,
    PortfolioWeightingMethod,
    StrategyContract,
    StrategyEligibilityStatus,
    StrategyFamily,
    StrategyPositionState,
    StrategyRegistry,
    StrategyRunOrigin,
    StrategyRuntimeInput,
    StrategyVersion,
)
from market_regime_alpha.strategies.runtime import MultiStrategyRuntime


TZ = ZoneInfo("Asia/Shanghai")
NOW = datetime(2026, 8, 14, 14, 55, tzinfo=TZ)


def _reference(kind: str, name: str) -> RuntimeArtifactReference:
    digest = canonical_hash({"kind": kind, "name": name})
    return RuntimeArtifactReference(kind, ArtifactId(f"{name}:{digest[7:]}"), digest)


def _contract(family: StrategyFamily) -> StrategyContract:
    parameters = {
        StrategyFamily.OVERNIGHT: (("minimum_entry_score", "0.50"),),
        StrategyFamily.SWING_STATE: (
            ("add_return", "0.03"),
            ("max_add_count", "1"),
            ("minimum_entry_score", "0.50"),
            ("reduce_drawdown", "0.04"),
            ("stop_loss", "0.08"),
        ),
    }[family]
    return StrategyContract.create(
        strategy_id=StrategyId(family.value.lower()),
        family=family,
        semantic_version="1.0.0",
        objective=f"{family.value} exploratory policy",
        universe_reference=_reference("UNIVERSE_POLICY", "full-a-research"),
        target_references=(_reference("OUTCOME_TARGET_PROTOCOL", family.value),),
        decision_times=("14:55:00+08:00",),
        horizon_sessions=(1,) if family is StrategyFamily.OVERNIGHT else (3, 5, 10),
        candidate_policy_version="candidate-explicit-gates-v1",
        action_policy_version=f"{family.value.lower()}-state-v1",
        portfolio_weighting=PortfolioWeightingMethod.SCORE,
        top_k=2,
        strategy_budget=Decimal("0.30"),
        cost_model_reference=_reference("COST_MODEL", "engineering-cost"),
        evaluation_protocol_reference=_reference("EVALUATION_PROTOCOL", family.value),
        code_reference=_reference("CODE_IDENTITY", "test-code"),
        configuration_reference=_reference("CONFIGURATION", family.value),
        parameters=parameters,
        limitations=(
            "CALIBRATED_FALSE",
            "FORMAL_OOS_FALSE",
            "PIT_INCOMPLETE",
            "PRODUCTION_AUTHORIZED_FALSE",
        ),
    )


def _candidate(
    symbol: str,
    status: CandidateSelectionStatus,
    *,
    score: float | None,
    rank: int | None,
) -> CandidateRecord:
    return CandidateRecord(
        symbol=symbol,
        primary_theme_id="theme-test",
        supporting_theme_ids=(),
        market_regime_status=MarketState.RISK_ON,
        theme_rotation_state=RotationState.STRENGTHENING,
        capital_evolution_state=CapitalEvolutionState.IGNITION,
        market_regime_score=score,
        theme_score=score,
        capital_evolution_score=score,
        candidate_discovery_score=score,
        rank=rank,
        selection_status=status,
        reason_codes=(f"CANDIDATE_{status.value}",),
        source_feature_ids=(),
        input_artifact_ids=(),
    )


def _candidate_set() -> CandidateSet:
    records = (
        _candidate("000001.SZ", CandidateSelectionStatus.SELECTED, score=0.80, rank=1),
        _candidate("000002.SZ", CandidateSelectionStatus.SELECTED, score=0.70, rank=2),
        _candidate("000003.SZ", CandidateSelectionStatus.REJECTED, score=0.60, rank=None),
        _candidate(
            "000004.SZ",
            CandidateSelectionStatus.DATA_INSUFFICIENT,
            score=None,
            rank=None,
        ),
    )
    payload = {
        "records": [item.to_canonical_dict() for item in records],
        "minimum_candidate_population": 2,
        "reason_codes": ["COMPLETE_RECONCILIATION"],
    }
    envelope = ArtifactEnvelope.create(
        artifact_type="CANDIDATE_SET",
        artifact_payload=payload,
        decision_date=NOW.date(),
        decision_time=DecisionTime(NOW),
        created_at=NOW,
        code_revision="test-code",
        configuration_id=ArtifactId("candidate-config-test"),
        configuration_hash=canonical_hash({"candidate": "config"}),
        source_manifest_id=ArtifactId("candidate-source-test"),
        source_manifest_hash=canonical_hash({"candidate": "source"}),
        input_artifact_ids=(),
        input_content_hashes=(),
        model_id=ModelId("candidate-model-test"),
        model_version="1.0.0",
        data_eligibility=DataEligibility.EXPLORATORY,
        evidence_authority=EvidenceAuthority.IMMUTABLE_CONTENT_ADDRESSED_ARTIFACT,
        status="RESEARCH_READY",
        reason_codes=("COMPLETE_RECONCILIATION",),
        limitations=("PIT_INCOMPLETE",),
    )
    return CandidateSet(
        envelope=envelope,
        records=records,
        minimum_candidate_population=2,
        reason_codes=("COMPLETE_RECONCILIATION",),
    )


def _runtime_input(
    versions: tuple[StrategyVersion, ...],
    *,
    origin: StrategyRunOrigin = StrategyRunOrigin.CONTINUOUS,
    authority_mode: RuntimeAuthorityMode = RuntimeAuthorityMode.RESEARCH,
) -> StrategyRuntimeInput:
    by_family = {item.family: item for item in versions}
    return StrategyRuntimeInput(
        origin=origin,
        authority_mode=authority_mode,
        parent_run_reference=_reference("CONTINUOUS_RUN", "run-1"),
        parent_tick_reference=_reference("CONTINUOUS_TICK", "tick-1"),
        candidate_set=_candidate_set(),
        dataset_reference=_reference("DATASET", "dataset-1"),
        decision_time=NOW,
        positions=tuple(
            sorted(
                (
                    StrategyPositionState(
                        strategy_version_id=by_family[StrategyFamily.OVERNIGHT].version_id,
                        symbol="000002.SZ",
                        quantity=Decimal("100"),
                        average_cost=Decimal("10"),
                        current_price=Decimal("10.50"),
                        peak_price=Decimal("10.50"),
                        sessions_held=1,
                    ),
                    StrategyPositionState(
                        strategy_version_id=by_family[StrategyFamily.SWING_STATE].version_id,
                        symbol="000002.SZ",
                        quantity=Decimal("100"),
                        average_cost=Decimal("10"),
                        current_price=Decimal("10.40"),
                        peak_price=Decimal("10.40"),
                        sessions_held=2,
                    ),
                ),
                key=lambda item: (str(item.strategy_version_id), item.symbol),
            )
        ),
        code_reference=_reference("CODE_IDENTITY", "test-code"),
        configuration_reference=_reference("CONFIGURATION", "multi-strategy"),
    )


def _registry() -> StrategyRegistry:
    contracts = (
        _contract(StrategyFamily.OVERNIGHT),
        _contract(StrategyFamily.SWING_STATE),
    )
    versions = tuple(StrategyVersion.activate(item) for item in contracts)
    return StrategyRegistry.create(contracts=contracts, versions=versions)


def test_one_runtime_executes_overnight_and_swing_with_complete_gate_attribution() -> None:
    registry = _registry()
    cycle = MultiStrategyRuntime(registry).execute(_runtime_input(registry.active_versions))

    assert tuple(run.strategy_version_reference.artifact_id for run in cycle.runs) == tuple(sorted(registry.active_version_ids, key=str))
    assert {run.origin for run in cycle.runs} == {StrategyRunOrigin.CONTINUOUS}
    assert all(len(run.gate_attributions) == 4 for run in cycle.runs)

    by_family = {registry.family_for(run): run for run in cycle.runs}
    overnight_actions = {item.symbol: item.action for item in by_family[StrategyFamily.OVERNIGHT].gate_attributions}
    swing_actions = {item.symbol: item.action for item in by_family[StrategyFamily.SWING_STATE].gate_attributions}
    assert overnight_actions == {
        "000001.SZ": CanonicalStrategyAction.ENTER,
        "000002.SZ": CanonicalStrategyAction.EXIT,
        "000003.SZ": CanonicalStrategyAction.NO_ACTION,
        "000004.SZ": CanonicalStrategyAction.NO_ACTION,
    }
    assert swing_actions == {
        "000001.SZ": CanonicalStrategyAction.ENTER,
        "000002.SZ": CanonicalStrategyAction.ADD,
        "000003.SZ": CanonicalStrategyAction.NO_ACTION,
        "000004.SZ": CanonicalStrategyAction.NO_ACTION,
    }
    insufficient = next(item for item in by_family[StrategyFamily.SWING_STATE].gate_attributions if item.symbol == "000004.SZ")
    assert insufficient.eligibility_status is StrategyEligibilityStatus.NOT_ESTIMABLE
    assert "CANDIDATE_DATA_INSUFFICIENT" in insufficient.reason_codes


def test_historical_replay_uses_identical_strategy_semantics() -> None:
    registry = _registry()
    runtime = MultiStrategyRuntime(registry)
    historical = runtime.execute(_runtime_input(registry.active_versions, origin=StrategyRunOrigin.HISTORICAL))
    replay = runtime.execute(_runtime_input(registry.active_versions, origin=StrategyRunOrigin.REPLAY))

    historical_actions = tuple(tuple(item.action for item in run.gate_attributions) for run in historical.runs)
    replay_actions = tuple(tuple(item.action for item in run.gate_attributions) for run in replay.runs)
    assert historical_actions == replay_actions
    assert historical.runtime_input.origin is StrategyRunOrigin.HISTORICAL
    assert replay.runtime_input.origin is StrategyRunOrigin.REPLAY


def test_production_mode_fails_closed_without_strategy_qualification() -> None:
    registry = _registry()

    with pytest.raises(RuntimeError, match="PRODUCTION_AUTHORIZED_FALSE"):
        MultiStrategyRuntime(registry).execute(
            _runtime_input(
                registry.active_versions,
                authority_mode=RuntimeAuthorityMode.PRODUCTION,
            )
        )
