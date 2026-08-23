from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from decimal import Decimal, localcontext
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
    PriceFreshnessStatus,
    StrategyContract,
    StrategyEligibilityStatus,
    StrategyFamily,
    StrategyForecastRequirement,
    StrategyOpportunityInput,
    StrategyPositionState,
    StrategyRegistry,
    StrategyRunStatus,
    StrategyRunOrigin,
    StrategyRuntimeInput,
    StrategyVersion,
    strategy_reference,
)
from market_regime_alpha.strategies.defaults import (
    canonical_exploratory_strategy_registry,
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


def _candidate_set(
    records: tuple[CandidateRecord, ...] | None = None,
) -> CandidateSet:
    if records is None:
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


def _conditional_contract() -> StrategyContract:
    base = _contract(StrategyFamily.OVERNIGHT)
    return StrategyContract.create(
        strategy_id=StrategyId("conditional-alpha"),
        family=StrategyFamily.CONDITIONAL_PREDICTION,
        semantic_version="1.0.0-research",
        objective="Consume explicit Signal and conditional Forecast lineage.",
        universe_reference=base.universe_reference,
        target_references=base.target_references,
        decision_times=base.decision_times,
        horizon_sessions=base.horizon_sessions,
        candidate_policy_version="challenger-v1",
        action_policy_version="conditional-prediction-v1",
        portfolio_weighting=base.portfolio_weighting,
        top_k=2,
        strategy_budget=base.strategy_budget,
        cost_model_reference=base.cost_model_reference,
        evaluation_protocol_reference=base.evaluation_protocol_reference,
        code_reference=base.code_reference,
        configuration_reference=base.configuration_reference,
        parameters=(
            ("maximum_uncertainty", "0.02"),
            ("minimum_entry_score", "0.50"),
            ("minimum_expected_return", "0.01"),
        ),
        limitations=base.limitations,
        forecast_requirement=StrategyForecastRequirement.FORECAST_REQUIRED,
    )


def _opportunity(
    symbol: str,
    *,
    version: StrategyVersion,
    candidate_set: CandidateSet,
    signal_active: bool = True,
    risk_allows_action: bool = True,
) -> StrategyOpportunityInput:
    return StrategyOpportunityInput.create(
        symbol=symbol,
        strategy_version_reference=strategy_reference(version),
        candidate_reference=RuntimeArtifactReference(
            "CANDIDATE_SET",
            candidate_set.envelope.artifact_id,
            candidate_set.envelope.content_hash,
        ),
        decision_time=NOW,
        signal_reference=_reference("SIGNAL_SNAPSHOT", f"signal-{symbol}"),
        forecast_reference=_reference("CONDITIONAL_FORECAST_RESULT", f"forecast-{symbol}"),
        context_reference=_reference("CONTEXT_CONDITIONAL_EVALUATION", f"context-{symbol}"),
        risk_state_reference=_reference(
            "PRE_STRATEGY_RISK_STATE", f"risk-{symbol}"
        ),
        model_reference=_reference("MODEL_VERSION", "conditional-model-v1"),
        signal_active=signal_active,
        risk_allows_action=risk_allows_action,
        risk_reason_codes=() if risk_allows_action else ("ACCOUNT_RISK_LIMIT",),
        expected_return=Decimal("0.02"),
        prediction_uncertainty=Decimal("0.01"),
        calibration_status="NOT_CALIBRATED",
        available_at=NOW,
    )


class _ExactOpportunityAuthority:
    def reload(
        self, opportunity: StrategyOpportunityInput
    ) -> StrategyOpportunityInput:
        return opportunity


def _conditional_runtime(registry: StrategyRegistry) -> MultiStrategyRuntime:
    return MultiStrategyRuntime(
        registry,
        opportunity_authority=_ExactOpportunityAuthority(),
    )


def test_strategy_opportunity_is_content_addressed_and_available_by_decision_time() -> None:
    version = StrategyVersion.activate(_conditional_contract())
    candidate_set = _candidate_set()
    opportunity = _opportunity(
        "000001.SZ", version=version, candidate_set=candidate_set
    )
    payload = opportunity.to_canonical_dict()

    assert StrategyOpportunityInput.from_canonical_dict(payload) == opportunity
    assert opportunity.reference.reference_kind == "STRATEGY_OPPORTUNITY"
    payload["expected_return"] = "0.99"
    with pytest.raises(ValueError, match="binding hash mismatch"):
        StrategyOpportunityInput.from_canonical_dict(payload)

    with pytest.raises(ValueError, match="unavailable at DecisionTime"):
        StrategyOpportunityInput.create(
            **{
                field_name: getattr(opportunity, field_name)
                for field_name in (
                    "symbol",
                    "strategy_version_reference",
                    "candidate_reference",
                    "decision_time",
                    "signal_reference",
                    "forecast_reference",
                    "context_reference",
                    "risk_state_reference",
                    "model_reference",
                    "signal_active",
                    "risk_allows_action",
                    "risk_reason_codes",
                    "expected_return",
                    "prediction_uncertainty",
                    "calibration_status",
                )
            },
            available_at=NOW + timedelta(seconds=1),
        )


def test_complete_account_risk_cannot_be_used_before_strategy() -> None:
    version = StrategyVersion.activate(_conditional_contract())
    candidate_set = _candidate_set()
    opportunity = _opportunity(
        "000001.SZ", version=version, candidate_set=candidate_set
    )

    with pytest.raises(ValueError, match="risk_state_reference kind is invalid"):
        StrategyOpportunityInput.create(
            **{
                field_name: getattr(opportunity, field_name)
                for field_name in (
                    "symbol",
                    "strategy_version_reference",
                    "candidate_reference",
                    "decision_time",
                    "signal_reference",
                    "forecast_reference",
                    "context_reference",
                    "model_reference",
                    "signal_active",
                    "risk_allows_action",
                    "risk_reason_codes",
                    "expected_return",
                    "prediction_uncertainty",
                    "calibration_status",
                    "available_at",
                )
            },
            risk_state_reference=_reference(
                "COMPLETE_ACCOUNT_RISK_DECISION", "post-portfolio-risk"
            ),
        )


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


def test_forecast_required_strategy_fails_closed_without_opportunity_lineage() -> None:
    contracts = (*_registry().contracts, _conditional_contract())
    registry = StrategyRegistry.create(
        contracts=contracts,
        versions=tuple(StrategyVersion.activate(item) for item in contracts),
    )

    with pytest.raises(ValueError, match="FORECAST_REQUIRED"):
        MultiStrategyRuntime(registry).execute(_runtime_input(registry.active_versions))


def test_conditional_strategy_consumes_signal_forecast_context_risk_and_model() -> None:
    contracts = (*_registry().contracts, _conditional_contract())
    registry = StrategyRegistry.create(
        contracts=contracts,
        versions=tuple(StrategyVersion.activate(item) for item in contracts),
    )
    base_input = _runtime_input(registry.active_versions)
    conditional_version = next(
        item
        for item in registry.active_versions
        if item.family is StrategyFamily.CONDITIONAL_PREDICTION
    )
    runtime_input = replace(
        base_input,
        opportunities=(
            _opportunity(
                "000001.SZ",
                version=conditional_version,
                candidate_set=base_input.candidate_set,
            ),
            _opportunity(
                "000002.SZ",
                version=conditional_version,
                candidate_set=base_input.candidate_set,
                signal_active=False,
            ),
        ),
    )

    with pytest.raises(ValueError, match="PostgreSQL owner reload"):
        MultiStrategyRuntime(registry).execute(runtime_input)
    cycle = _conditional_runtime(registry).execute(runtime_input)
    conditional = next(
        run
        for run in cycle.runs
        if registry.family_for(run) is StrategyFamily.CONDITIONAL_PREDICTION
    )

    assert len(conditional.proposals) == 1
    assert conditional.proposals[0].symbol == "000001.SZ"
    assert conditional.proposals[0].utility_score == Decimal("0.02")
    assert next(
        item for item in conditional.gate_attributions if item.symbol == "000002.SZ"
    ).eligibility_status is StrategyEligibilityStatus.INELIGIBLE


def test_conditional_strategy_cannot_bypass_rejected_risk_state() -> None:
    contracts = (*_registry().contracts, _conditional_contract())
    registry = StrategyRegistry.create(
        contracts=contracts,
        versions=tuple(StrategyVersion.activate(item) for item in contracts),
    )
    base_input = _runtime_input(registry.active_versions)
    conditional_version = next(
        item
        for item in registry.active_versions
        if item.family is StrategyFamily.CONDITIONAL_PREDICTION
    )
    opportunities = (
        _opportunity(
            "000001.SZ",
            version=conditional_version,
            candidate_set=base_input.candidate_set,
            risk_allows_action=False,
        ),
        _opportunity(
            "000002.SZ",
            version=conditional_version,
            candidate_set=base_input.candidate_set,
        ),
    )
    cycle = _conditional_runtime(registry).execute(
        replace(base_input, opportunities=opportunities)
    )
    conditional = next(
        run
        for run in cycle.runs
        if registry.family_for(run) is StrategyFamily.CONDITIONAL_PREDICTION
    )
    attribution = next(
        item for item in conditional.gate_attributions if item.symbol == "000001.SZ"
    )
    assert attribution.action is CanonicalStrategyAction.NO_ACTION
    assert "RISK_STATE_REJECTED" in attribution.reason_codes


def test_forecast_lineage_is_bound_to_exact_strategy_version() -> None:
    contracts = (*_registry().contracts, _conditional_contract())
    registry = StrategyRegistry.create(
        contracts=contracts,
        versions=tuple(StrategyVersion.activate(item) for item in contracts),
    )
    base_input = _runtime_input(registry.active_versions)
    wrong_version = next(
        item
        for item in registry.active_versions
        if item.family is StrategyFamily.OVERNIGHT
    )
    runtime_input = replace(
        base_input,
        opportunities=tuple(
            sorted(
                (
                    _opportunity(
                        symbol,
                        version=wrong_version,
                        candidate_set=base_input.candidate_set,
                    )
                    for symbol in ("000001.SZ", "000002.SZ")
                ),
                key=lambda item: (
                    str(item.strategy_version_reference.artifact_id), item.symbol
                ),
            )
        ),
    )

    with pytest.raises(ValueError, match="FORECAST_NOT_REQUIRED"):
        _conditional_runtime(registry).execute(runtime_input)


def test_forecast_required_position_only_symbol_cannot_bypass_contract() -> None:
    contracts = (*_registry().contracts, _conditional_contract())
    registry = StrategyRegistry.create(
        contracts=contracts,
        versions=tuple(StrategyVersion.activate(item) for item in contracts),
    )
    base_input = _runtime_input(registry.active_versions)
    conditional_version = next(
        item
        for item in registry.active_versions
        if item.family is StrategyFamily.CONDITIONAL_PREDICTION
    )
    position = StrategyPositionState(
        strategy_version_id=conditional_version.version_id,
        symbol="000003.SZ",
        quantity=Decimal("100"),
        average_cost=Decimal("10"),
        current_price=Decimal("10"),
        peak_price=Decimal("10"),
        sessions_held=1,
    )
    opportunities = tuple(
        _opportunity(
            symbol,
            version=conditional_version,
            candidate_set=base_input.candidate_set,
        )
        for symbol in ("000001.SZ", "000002.SZ")
    )
    runtime_input = replace(
        base_input,
        positions=tuple(
            sorted(
                (*base_input.positions, position),
                key=lambda item: (str(item.strategy_version_id), item.symbol),
            )
        ),
        opportunities=opportunities,
    )

    with pytest.raises(ValueError, match="000003.SZ"):
        _conditional_runtime(registry).execute(runtime_input)


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


def test_empty_candidate_population_is_explicitly_data_insufficient() -> None:
    registry = _registry()
    runtime_input = replace(
        _runtime_input(registry.active_versions),
        candidate_set=_candidate_set(()),
        positions=(),
    )

    cycle = MultiStrategyRuntime(registry).execute(runtime_input)

    assert all(
        run.status is StrategyRunStatus.DATA_INSUFFICIENT
        for run in cycle.runs
    )
    assert all(run.gate_attributions == () for run in cycle.runs)
    assert all(
        "STRATEGY_CANDIDATE_POPULATION_EMPTY" in run.reason_codes
        for run in cycle.runs
    )


def test_swing_price_sensitive_actions_fail_closed_for_stale_owner_mark() -> None:
    registry = _registry()
    runtime_input = _runtime_input(registry.active_versions)
    swing_version = next(
        item
        for item in registry.active_versions
        if item.family is StrategyFamily.SWING_STATE
    )
    positions = tuple(
        replace(
            item,
            available_quantity=item.quantity,
            entry_time=NOW,
            price_observed_at=NOW.replace(day=13),
            price_freshness=PriceFreshnessStatus.STALE,
            trading_calendar_reference=_reference("PIT_TRADING_CALENDAR", "calendar"),
        )
        if item.strategy_version_id == swing_version.version_id
        else item
        for item in runtime_input.positions
    )

    cycle = MultiStrategyRuntime(registry).execute(
        replace(runtime_input, positions=positions)
    )

    swing_run = next(
        item
        for item in cycle.runs
        if registry.family_for(item) is StrategyFamily.SWING_STATE
    )
    attribution = next(
        item for item in swing_run.gate_attributions if item.symbol == "000002.SZ"
    )
    assert attribution.action is CanonicalStrategyAction.NO_ACTION
    assert "SWING_CURRENT_PRICE_STALE" in attribution.reason_codes


def test_strategy_policy_identity_does_not_depend_on_process_decimal_context() -> None:
    registry = canonical_exploratory_strategy_registry()
    runtime_input = replace(
        _runtime_input(registry.active_versions),
        positions=(),
    )

    with localcontext() as context:
        context.prec = 8
        low_precision = MultiStrategyRuntime(registry).execute(runtime_input)
    with localcontext() as context:
        context.prec = 50
        high_precision = MultiStrategyRuntime(registry).execute(runtime_input)

    assert low_precision == high_precision


def test_production_mode_fails_closed_without_strategy_qualification() -> None:
    registry = _registry()

    with pytest.raises(RuntimeError, match="PRODUCTION_AUTHORIZED_FALSE"):
        MultiStrategyRuntime(registry).execute(
            _runtime_input(
                registry.active_versions,
                authority_mode=RuntimeAuthorityMode.PRODUCTION,
            )
        )
