from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from market_regime_alpha.application.continuous_research.journal import (
    RuntimeArtifactReference,
)
from market_regime_alpha.application.controlled_operation.prospective_outcome import (
    OutcomeAvailabilityStatus,
    OutcomeMarketCondition,
)
from market_regime_alpha.application.research_evaluation.targeted_outcome import (
    BarrierOrderingOutcome,
    TargetOutcomeLabel,
)
from market_regime_alpha.application.research_evaluation.targets import (
    BarrierDefinition,
    OutcomeCheckpoint,
    TargetDefinition,
    canonical_target_horizon,
)
from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.application.research_validation.liquidity_capacity import (
    CapacityParameter,
    CapacityValueProvenance,
    LiquidityCapacityAssessment,
    LiquidityCapacityProtocol,
)
from market_regime_alpha.application.strategy_shadow.economics import (
    StrategyEconomicsPolicy,
    StrategyEconomicsStatus,
    StrategyEntryKind,
    StrategyExecutionObservation,
    StrategyExecutionPhase,
    StrategyExitKind,
    evaluate_strategy_economics,
)
from market_regime_alpha.application.strategy_shadow.portfolio import (
    ShadowParameterProvenance,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.market_data import Exchange, PriceLimitState, TradingStatus
from tests.market_data.test_contracts import _raw_bar


NOW = datetime(2026, 8, 12, 8, tzinfo=UTC)


def _target() -> TargetDefinition:
    return TargetDefinition.create(
        target_version="strategy-economics-target-v2",
        canonical_horizon=canonical_target_horizon(
            checkpoint=OutcomeCheckpoint.TIME_1030,
            barriers=(
                BarrierDefinition("down-2", Decimal("0.02"), "DOWN"),
                BarrierDefinition("up-2", Decimal("0.02"), "UP"),
            ),
            compute_mfe_mae=True,
        ),
        required_market_data=("5m_ohlc",),
    )


def _label(
    target: TargetDefinition,
    *,
    conditions: tuple[OutcomeMarketCondition, ...] = (
        OutcomeMarketCondition.TRADING,
    ),
    barrier_ordering: BarrierOrderingOutcome = BarrierOrderingOutcome.UP_FIRST,
) -> TargetOutcomeLabel:
    target_ref = RuntimeArtifactReference(
        "OUTCOME_TARGET_DEFINITION", target.target_id, target.target_hash
    )
    return TargetOutcomeLabel.create(
        symbol="000001.SZ",
        target=target_ref,
        label_interval_start=NOW,
        label_interval_end=NOW + timedelta(days=1),
        decision_reference_price=Decimal("10"),
        checkpoint_price=Decimal("10.5"),
        mfe=Decimal("0.07"),
        mae=Decimal("-0.01"),
        barrier_passages=(
            ("down-2", None),
            ("up-2", NOW + timedelta(days=1, hours=-1)),
        ),
        barrier_ordering=barrier_ordering,
        market_conditions=conditions,
        availability_status=(
            OutcomeAvailabilityStatus.PARTIAL
            if barrier_ordering
            is BarrierOrderingOutcome.AMBIGUOUS_NOT_OBSERVABLE
            else OutcomeAvailabilityStatus.COMPLETE
        ),
        outcome_available_at=NOW + timedelta(days=1, seconds=1),
        reason_codes=(
            ("BARRIER_ORDERING_NOT_OBSERVABLE",)
            if barrier_ordering
            is BarrierOrderingOutcome.AMBIGUOUS_NOT_OBSERVABLE
            else ()
        ),
    )


def _capacity() -> LiquidityCapacityAssessment:
    parameters = (
        CapacityParameter(
            "impact_coefficient_bps",
            Decimal("8"),
            CapacityValueProvenance.ENGINEERING_ASSUMPTION,
        ),
        CapacityParameter(
            "participation_rate",
            Decimal("0.1"),
            CapacityValueProvenance.ENGINEERING_ASSUMPTION,
        ),
        CapacityParameter(
            "slippage_bps",
            Decimal("5"),
            CapacityValueProvenance.ENGINEERING_ASSUMPTION,
        ),
    )
    protocol = LiquidityCapacityProtocol.create(
        protocol_version="economics-capacity-v1",
        parameters=parameters,
        created_at=NOW,
    )
    bars = tuple(
        _raw_bar(
            symbol="000001.SZ",
            exchange=Exchange.SZ,
            market_date=(NOW - timedelta(days=20 - index)).date(),
            event_start=NOW - timedelta(days=20 - index, hours=6),
            event_end=NOW - timedelta(days=20 - index, hours=1),
            available_at=NOW - timedelta(days=20 - index, minutes=59),
            amount=Decimal("10000000"),
            trading_status=TradingStatus.TRADING,
            price_limit_state=PriceLimitState.NORMAL,
            source_artifact_id=ArtifactId(f"economics-source-{index}"),
        )
        for index in range(20)
    )
    return LiquidityCapacityAssessment.create(
        symbol="000001.SZ",
        as_of_date=bars[-1].market_date,
        market_data_reference=ValidationArtifactReference(
            "MARKET_DATA_DATASET",
            ArtifactId("economics-market-data"),
            canonical_hash({"market": 1}),
        ),
        bars=bars,
        requested_position=Decimal("100000"),
        requested_order=Decimal("100000"),
        protocol=protocol,
        created_at=NOW,
    )


def _policy(target: TargetDefinition, exit_kind: StrategyExitKind) -> StrategyEconomicsPolicy:
    return StrategyEconomicsPolicy.create(
        policy_version=f"economics-{exit_kind.value.lower()}-v1",
        prediction_target=target,
        entry_kind=StrategyEntryKind.FROZEN_DECISION_REFERENCE,
        exit_kind=exit_kind,
        fixed_exit_checkpoint=OutcomeCheckpoint.TIME_1030,
        barrier_id="up-2" if exit_kind is StrategyExitKind.BARRIER else None,
        forecast_raw_score_threshold=(
            Decimal("0")
            if exit_kind is StrategyExitKind.FORECAST_AWARE
            else None
        ),
        lot_size=100,
        t_plus_one=True,
        parameters={
            "commission_bps": (
                Decimal("3"),
                ShadowParameterProvenance.ENGINEERING_ASSUMPTION,
            ),
            "stamp_duty_bps": (
                Decimal("5"),
                ShadowParameterProvenance.ENGINEERING_ASSUMPTION,
            ),
            "spread_slippage_bps": (
                Decimal("5"),
                ShadowParameterProvenance.ENGINEERING_ASSUMPTION,
            ),
        },
        created_at=NOW,
    )


def _execution(
    phase: StrategyExecutionPhase,
    *,
    conditions: tuple[OutcomeMarketCondition, ...] = (
        OutcomeMarketCondition.TRADING,
    ),
    price: Decimal | None = None,
) -> StrategyExecutionObservation:
    is_entry = phase is StrategyExecutionPhase.ENTRY
    effective_at = NOW if is_entry else NOW + timedelta(days=1)
    available_at = effective_at if is_entry else effective_at + timedelta(seconds=1)
    resolved_price = Decimal("10") if is_entry else Decimal("10.5")
    reference_payload = {
        "phase": phase.value,
        "conditions": [item.value for item in conditions],
        "price": str(resolved_price if price is None else price),
    }
    return StrategyExecutionObservation(
        phase=phase,
        symbol="000001.SZ",
        price=resolved_price if price is None else price,
        market_conditions=tuple(sorted(conditions, key=lambda item: item.value)),
        effective_at=effective_at,
        available_at=available_at,
        source_reference=ValidationArtifactReference(
            f"{phase.value}_EXECUTION_OBSERVATION",
            ArtifactId(f"{phase.value.lower()}-execution-observation"),
            canonical_hash(reference_payload),
        ),
    )


def test_fixed_time_strategy_economics_reports_gross_cost_net_and_capacity() -> None:
    target = _target()
    result = evaluate_strategy_economics(
        policy=_policy(target, StrategyExitKind.FIXED_TIME),
        label=_label(target),
        liquidity=_capacity(),
        entry_execution=_execution(StrategyExecutionPhase.ENTRY),
        exit_execution=_execution(StrategyExecutionPhase.EXIT),
        requested_notional=Decimal("100000"),
        evaluated_at=NOW + timedelta(days=1, seconds=2),
    )

    assert result.status is StrategyEconomicsStatus.AVAILABLE
    assert result.gross_return == Decimal("0.05")
    assert result.cost_return is not None and result.cost_return > 0
    assert result.net_return == result.gross_return - result.cost_return
    assert result.capacity_ceiling == Decimal("1000000.0")
    assert result.filled_quantity % Decimal("100") == 0
    assert result.turnover == Decimal("2")
    assert "EXPLORATORY_NOT_FORMAL_ALPHA_EVIDENCE" in result.limitations


@pytest.mark.parametrize(
    ("conditions", "expected_status"),
    [
        ((OutcomeMarketCondition.SUSPENDED,), StrategyEconomicsStatus.NOT_ESTIMABLE),
        ((OutcomeMarketCondition.LIMIT_UP,), StrategyEconomicsStatus.AVAILABLE),
        ((OutcomeMarketCondition.LIMIT_DOWN,), StrategyEconomicsStatus.NOT_ESTIMABLE),
        ((OutcomeMarketCondition.MISSING_QUOTE,), StrategyEconomicsStatus.NOT_ESTIMABLE),
    ],
)
def test_t_plus_one_exit_conditions_do_not_retroactively_deny_entry(
    conditions: tuple[OutcomeMarketCondition, ...],
    expected_status: StrategyEconomicsStatus,
) -> None:
    target = _target()
    result = evaluate_strategy_economics(
        policy=_policy(target, StrategyExitKind.FIXED_TIME),
        label=_label(target, conditions=conditions),
        liquidity=_capacity(),
        entry_execution=_execution(StrategyExecutionPhase.ENTRY),
        exit_execution=_execution(
            StrategyExecutionPhase.EXIT,
            conditions=conditions,
        ),
        requested_notional=Decimal("100000"),
        evaluated_at=NOW + timedelta(days=1, seconds=2),
    )

    assert result.status is expected_status
    assert result.filled_quantity > 0
    assert result.entry_price == Decimal("10")
    if expected_status is StrategyEconomicsStatus.NOT_ESTIMABLE:
        assert result.net_return is None
        assert "EXIT_MARKET_CONDITION_NOT_FILLABLE" in result.reason_codes


@pytest.mark.parametrize(
    ("conditions", "expected_status"),
    [
        ((OutcomeMarketCondition.LIMIT_UP,), StrategyEconomicsStatus.NO_ENTRY),
        ((OutcomeMarketCondition.SUSPENDED,), StrategyEconomicsStatus.NO_ENTRY),
        ((OutcomeMarketCondition.LIMIT_DOWN,), StrategyEconomicsStatus.AVAILABLE),
    ],
)
def test_entry_execution_is_side_aware_and_independent_of_exit(
    conditions: tuple[OutcomeMarketCondition, ...],
    expected_status: StrategyEconomicsStatus,
) -> None:
    target = _target()
    result = evaluate_strategy_economics(
        policy=_policy(target, StrategyExitKind.FIXED_TIME),
        label=_label(target),
        liquidity=_capacity(),
        entry_execution=_execution(
            StrategyExecutionPhase.ENTRY,
            conditions=conditions,
        ),
        exit_execution=_execution(StrategyExecutionPhase.EXIT),
        requested_notional=Decimal("100000"),
        evaluated_at=NOW + timedelta(days=1, seconds=2),
    )

    assert result.status is expected_status


def test_barrier_strategy_does_not_assume_intrabar_ordering() -> None:
    target = _target()
    result = evaluate_strategy_economics(
        policy=_policy(target, StrategyExitKind.BARRIER),
        label=_label(
            target,
            barrier_ordering=BarrierOrderingOutcome.AMBIGUOUS_NOT_OBSERVABLE,
        ),
        liquidity=_capacity(),
        entry_execution=_execution(StrategyExecutionPhase.ENTRY),
        exit_execution=_execution(StrategyExecutionPhase.EXIT),
        requested_notional=Decimal("100000"),
        evaluated_at=NOW + timedelta(days=1, seconds=2),
    )

    assert result.status is StrategyEconomicsStatus.NOT_ESTIMABLE
    assert "BARRIER_ORDERING_NOT_OBSERVABLE" in result.reason_codes
    assert result.filled_quantity > 0
    assert result.entry_price == Decimal("10")


def test_strategy_policy_rejects_target_horizon_drift() -> None:
    target = _target()
    policy = _policy(target, StrategyExitKind.FIXED_TIME)
    other_target = TargetDefinition.create(
        target_version="other-target-v2",
        canonical_horizon=target.canonical_horizon,
        required_market_data=target.required_market_data,
    )
    other = _label(other_target)

    with pytest.raises(ValueError, match="TargetDefinition identity"):
        evaluate_strategy_economics(
            policy=policy,
            label=other,
            liquidity=_capacity(),
            entry_execution=_execution(StrategyExecutionPhase.ENTRY),
            exit_execution=_execution(StrategyExecutionPhase.EXIT),
            requested_notional=Decimal("100000"),
            evaluated_at=NOW + timedelta(days=1, seconds=2),
        )
