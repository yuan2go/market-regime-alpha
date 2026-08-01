from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from market_regime_alpha.core.identity import (
    ArtifactId,
    FillId,
    ManualTradeId,
    OpportunityId,
    ThesisId,
)
from market_regime_alpha.decision import (
    DecisionEvidenceReference,
    InvalidationCondition,
    InvalidationKind,
    ThesisState,
    TradingThesis,
)
from market_regime_alpha.decision.thesis import TRADING_THESIS_SCHEMA
from market_regime_alpha.evaluation import (
    TRADE_EVALUATION_CONFIG_SCHEMA,
    AttributionComponent,
    RollingScorecardBuilder,
    ScorecardStatus,
    TradeEvaluationConfig,
    TradeOutcomeEvaluator,
    TradePathObservation,
)
from market_regime_alpha.execution import ExecutionDeviation, Fill, FillKind, TradeSide
from market_regime_alpha.execution.manual import FILL_SCHEMA
from market_regime_alpha.position import PositionProjector


TZ = ZoneInfo("Asia/Shanghai")
ENTRY_AT = datetime(2026, 7, 20, 14, 55, tzinfo=TZ)
EXIT_AT = datetime(2026, 7, 23, 14, 55, tzinfo=TZ)
EVALUATED_AT = EXIT_AT + timedelta(minutes=10)
SYMBOL = "000001.SZ"


def _evidence(name: str) -> DecisionEvidenceReference:
    return DecisionEvidenceReference(
        artifact_type="TRADE_PATH_OBSERVATION",
        artifact_id=ArtifactId(name),
        content_hash="sha256:" + "8" * 64,
        status="VERIFIED_EXPLORATORY",
    )


def _thesis() -> TradingThesis:
    return TradingThesis(
        schema_version=TRADING_THESIS_SCHEMA,
        thesis_id=ThesisId("thesis-outcome-test"),
        opportunity_id=OpportunityId("opportunity-outcome-test"),
        source_opportunity_version=0,
        symbol=SYMBOL,
        supporting_evidence=(_evidence("supporting-outcome-evidence"),),
        invalidation_conditions=(
            InvalidationCondition(
                condition_id="time-or-price",
                kind=InvalidationKind.PRICE,
                description="synthetic outcome fixture",
                reason_code="SYNTHETIC_INVALIDATION",
            ),
        ),
        time_invalidation=EXIT_AT + timedelta(days=1),
        state=ThesisState.APPROVED,
        version=0,
        approved_by="approver-a",
        approval_reason="synthetic fixture",
        created_at=ENTRY_AT - timedelta(minutes=5),
        updated_at=ENTRY_AT - timedelta(minutes=5),
        last_actor="approver-a",
        last_reason="synthetic fixture",
    )


def _fill(
    *,
    fill_id: str,
    trade_id: str,
    side: TradeSide,
    quantity: int,
    price: float,
    fees: float,
    occurred_at: datetime,
) -> Fill:
    return Fill(
        schema_version=FILL_SCHEMA,
        fill_id=FillId(fill_id),
        manual_trade_id=ManualTradeId(trade_id),
        account_id="account-a",
        symbol=SYMBOL,
        side=side,
        quantity=quantity,
        price=price,
        fees=fees,
        occurred_at=occurred_at,
        recorded_at=occurred_at + timedelta(seconds=1),
        actor="human-a",
        reason="synthetic lifecycle Fill",
        external_fill_id=f"external-{fill_id}",
        fill_kind=FillKind.EXECUTION,
        correction_of_fill_id=None,
    )


def _fills() -> tuple[Fill, ...]:
    return (
        _fill(
            fill_id="fill-entry-1",
            trade_id="trade-entry",
            side=TradeSide.BUY,
            quantity=40,
            price=10.0,
            fees=0.4,
            occurred_at=ENTRY_AT,
        ),
        _fill(
            fill_id="fill-entry-2",
            trade_id="trade-entry",
            side=TradeSide.BUY,
            quantity=60,
            price=10.1,
            fees=0.6,
            occurred_at=ENTRY_AT + timedelta(minutes=1),
        ),
        _fill(
            fill_id="fill-exit",
            trade_id="trade-exit",
            side=TradeSide.SELL,
            quantity=100,
            price=10.8,
            fees=1.0,
            occurred_at=EXIT_AT,
        ),
    )


def _config(*, minimum: int = 1) -> TradeEvaluationConfig:
    return TradeEvaluationConfig.create(
        profile_id="synthetic_trade_evaluation_v1",
        rolling_window_size=20,
        minimum_sample_count=minimum,
        capture_denominator_floor=0.001,
        schema_version=TRADE_EVALUATION_CONFIG_SCHEMA,
    )


def _path(fills: tuple[Fill, ...]) -> TradePathObservation:
    entries = tuple(item for item in fills if item.side is TradeSide.BUY)
    entry_vwap = sum(item.price * item.quantity for item in entries) / sum(
        item.quantity for item in entries
    )
    return TradePathObservation(
        symbol=SYMBOL,
        path_started_at=ENTRY_AT,
        path_ended_at=EXIT_AT,
        availability_time=EXIT_AT + timedelta(minutes=5),
        maximum_price=11.2,
        minimum_price=9.7,
        entry_reference_price=entry_vwap,
        entry_fill_ids=tuple(sorted((item.fill_id for item in entries), key=str)),
        evidence=_evidence("trade-path-outcome-test"),
    )


def _deviations() -> tuple[ExecutionDeviation, ...]:
    return (
        ExecutionDeviation(
            manual_trade_id=ManualTradeId("trade-entry"),
            intended_quantity=100,
            effective_filled_quantity=100,
            quantity_deviation=0,
            volume_weighted_price=10.06,
            expected_mid_price=10.0,
            price_deviation=10.06 - 10.0,
        ),
        ExecutionDeviation(
            manual_trade_id=ManualTradeId("trade-exit"),
            intended_quantity=100,
            effective_filled_quantity=100,
            quantity_deviation=0,
            volume_weighted_price=10.8,
            expected_mid_price=10.75,
            price_deviation=10.8 - 10.75,
        ),
    )


def _outcome(*, configuration: TradeEvaluationConfig | None = None):
    fills = _fills()
    final = PositionProjector().project(
        account_id="account-a",
        symbol=SYMBOL,
        fills=fills,
        as_of=EVALUATED_AT,
    )
    return TradeOutcomeEvaluator().evaluate(
        thesis=_thesis(),
        final_position=final,
        fills=fills,
        path=_path(fills),
        execution_deviations=_deviations(),
        configuration=configuration or _config(),
        evaluated_at=EVALUATED_AT,
    )


def test_trade_outcome_has_mfe_mae_capture_execution_and_four_part_attribution() -> None:
    outcome = _outcome()
    assert outcome.realized_pnl > 0.0
    assert outcome.mfe > 0.0
    assert outcome.mae < 0.0
    assert outcome.capture_ratio is not None
    assert tuple(item.component for item in outcome.attributions) == tuple(
        AttributionComponent
    )
    assert len(outcome.execution_deviations) == 2


def test_outcome_fails_closed_for_open_position_or_unavailable_path() -> None:
    fills = _fills()
    open_position = PositionProjector().project(
        account_id="account-a",
        symbol=SYMBOL,
        fills=fills[:2],
        as_of=ENTRY_AT + timedelta(minutes=2),
    )
    with pytest.raises(ValueError, match="closed authoritative Position"):
        TradeOutcomeEvaluator().evaluate(
            thesis=_thesis(),
            final_position=open_position,
            fills=fills[:2],
            path=_path(fills),
            execution_deviations=_deviations(),
            configuration=_config(),
            evaluated_at=EVALUATED_AT,
        )

    final = PositionProjector().project(
        account_id="account-a",
        symbol=SYMBOL,
        fills=fills,
        as_of=EVALUATED_AT,
    )
    late_path = replace(_path(fills), availability_time=EVALUATED_AT + timedelta(seconds=1))
    with pytest.raises(ValueError, match="unavailable path evidence"):
        TradeOutcomeEvaluator().evaluate(
            thesis=_thesis(),
            final_position=final,
            fills=fills,
            path=late_path,
            execution_deviations=_deviations(),
            configuration=_config(),
            evaluated_at=EVALUATED_AT,
        )

    incomplete_path = replace(
        _path(fills),
        path_ended_at=EXIT_AT - timedelta(seconds=1),
        availability_time=EXIT_AT + timedelta(minutes=5),
    )
    with pytest.raises(ValueError, match="does not cover authoritative"):
        TradeOutcomeEvaluator().evaluate(
            thesis=_thesis(),
            final_position=final,
            fills=fills,
            path=incomplete_path,
            execution_deviations=_deviations(),
            configuration=_config(),
            evaluated_at=EVALUATED_AT,
        )


def test_rolling_scorecard_is_diagnostic_and_minimum_sample_fail_closed() -> None:
    insufficient_config = _config(minimum=2)
    outcome = _outcome(configuration=insufficient_config)
    insufficient = RollingScorecardBuilder().build(
        (outcome,), insufficient_config, evaluated_at=EVALUATED_AT
    )
    available_config = _config(minimum=1)
    available_outcome = _outcome(configuration=available_config)
    available = RollingScorecardBuilder().build(
        (available_outcome,), available_config, evaluated_at=EVALUATED_AT
    )
    assert insufficient.status is ScorecardStatus.DATA_INSUFFICIENT
    assert insufficient.mean_realized_return is None
    assert available.status is ScorecardStatus.AVAILABLE_FOR_REVIEW
    assert available.mean_realized_return == available_outcome.realized_return
