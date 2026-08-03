from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from market_regime_alpha.core.identity import (
    ArtifactId,
    DatasetId,
    FillId,
    ManualTradeId,
    OpportunityId,
    PortfolioDecisionId,
    RiskDecisionId,
    ThesisId,
)
from market_regime_alpha.data import TradingSession, build_trading_calendar_artifact
from market_regime_alpha.execution import (
    Fill,
    FillKind,
    ManualOrderState,
    ManualTradeRecord,
    PositionBook,
    TradeSide,
)
from market_regime_alpha.execution.manual import (
    FILL_SCHEMA,
    TRACEABLE_MANUAL_TRADE_SCHEMA,
)
from market_regime_alpha.portfolio.risk_routes import (
    ExecutionConstraintState,
    ReducingExecutionObservation,
    RiskChangeKind,
    RiskReducingDecision,
    RiskReducingExecutionGate,
    RiskReducingGateConfiguration,
)
from market_regime_alpha.position import (
    PositionProjector,
    PositionSnapshot,
    SymbolTradingSessionStatus,
    SymbolTradingState,
)


TZ = ZoneInfo("Asia/Shanghai")
FRIDAY = date(2026, 7, 17)
MONDAY = date(2026, 7, 20)
TUESDAY = date(2026, 7, 21)
NOW = datetime(2026, 7, 20, 14, 55, tzinfo=TZ)


def sha(character: str) -> str:
    return "sha256:" + character * 64


def at(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=TZ)


def make_position(
    *,
    status: SymbolTradingState = SymbolTradingState.TRADABLE,
    same_session: bool = False,
    reconciliation: bool = False,
    as_of: datetime = NOW,
) -> PositionSnapshot:
    book = PositionBook.open(
        account_id="account-a",
        symbol="000001.SZ",
        opportunity_id=OpportunityId("opportunity-risk-route-support"),
        thesis_id=ThesisId("thesis-risk-route-support"),
        thesis_version=0,
        opened_at=at(FRIDAY, 9, 30),
        actor="operator-a",
        reason="synthetic route support",
    )
    buy = _trade(book, TradeSide.BUY, 100, 1)
    fill = _fill(
        buy,
        day=MONDAY if same_session else FRIDAY,
        index=1,
        quantity=100,
    )
    trades = (buy,)
    fills = (fill,)
    if reconciliation:
        sell = _trade(book, TradeSide.SELL, 10, 2)
        trades = (buy, sell)
        fills = (fill, _fill(sell, day=MONDAY, index=2, quantity=10))
    calendar = build_trading_calendar_artifact(
        source_dataset_id=DatasetId("risk-route-support-calendar"),
        market="CN_A_SHARE",
        calendar_version="synthetic-risk-route-support-v1",
        timezone_name="Asia/Shanghai",
        sessions=tuple(
            TradingSession(day, at(day, 15))
            for day in (FRIDAY, MONDAY, TUESDAY)
        ),
    )
    session_status = SymbolTradingSessionStatus.create(
        symbol=book.symbol,
        session_date=MONDAY,
        state=status,
        source_artifact_id=ArtifactId("risk-route-support-symbol-status"),
        source_artifact_hash=sha("a"),
        availability_time=NOW - timedelta(hours=1),
        reason_code=f"SYNTHETIC_{status.value}",
    )
    return PositionProjector().project_book_t_plus_one(
        book=book,
        trades=trades,
        fills=fills,
        calendar=calendar,
        symbol_session_statuses=(session_status,),
        as_of=as_of,
    )


def make_observation(
    state: ExecutionConstraintState = ExecutionConstraintState.EXECUTABLE,
    *,
    symbol: str = "000001.SZ",
    session_date: date = MONDAY,
    average_daily_volume: int = 10_000,
    availability_time: datetime | None = None,
) -> ReducingExecutionObservation:
    return ReducingExecutionObservation.create(
        symbol=symbol,
        session_date=session_date,
        state=state,
        reference_price=10.0,
        average_daily_volume=average_daily_volume,
        source_artifact_id=ArtifactId("risk-route-support-execution-source"),
        source_artifact_hash=sha("b"),
        availability_time=(
            availability_time
            if availability_time is not None
            else NOW - timedelta(seconds=10)
        ),
        reason_code=f"SYNTHETIC_{state.value}",
    )


def make_configuration() -> RiskReducingGateConfiguration:
    return RiskReducingGateConfiguration.create(
        profile_id="test_risk_reducing_gate_v2",
        maximum_position_age_seconds=60.0,
        maximum_observation_age_seconds=30.0,
        maximum_liquidity_participation=0.1,
    )


def make_decision(
    *,
    action: RiskChangeKind = RiskChangeKind.EXIT,
    position: PositionSnapshot | None = None,
    target_quantity: int = 0,
    order_quantity: int = 100,
    observation: ReducingExecutionObservation | None = None,
    configuration: RiskReducingGateConfiguration | None = None,
    actor: str = "risk-reduction-operator",
    reason: str = "manual audited reduction",
    assessed_at: datetime | None = None,
) -> tuple[
    PositionSnapshot,
    ReducingExecutionObservation,
    RiskReducingGateConfiguration,
    RiskReducingDecision,
]:
    resolved_position = position if position is not None else make_position()
    resolved_observation = observation if observation is not None else make_observation()
    resolved_configuration = (
        configuration if configuration is not None else make_configuration()
    )
    resolved_assessed_at = (
        assessed_at if assessed_at is not None else NOW + timedelta(seconds=1)
    )
    decision = RiskReducingExecutionGate().assess(
        action=action,
        position=resolved_position,
        target_quantity=target_quantity,
        order_quantity=order_quantity,
        execution_observation=resolved_observation,
        configuration=resolved_configuration,
        actor=actor,
        reason=reason,
        assessed_at=resolved_assessed_at,
    )
    return (
        resolved_position,
        resolved_observation,
        resolved_configuration,
        decision,
    )


def _trade(
    book: PositionBook, side: TradeSide, quantity: int, index: int
) -> ManualTradeRecord:
    return ManualTradeRecord(
        schema_version=TRACEABLE_MANUAL_TRADE_SCHEMA,
        manual_trade_id=ManualTradeId(f"manual-trade-risk-route-support-{index}"),
        risk_decision_id=RiskDecisionId(f"risk-route-support-{index}"),
        risk_decision_hash=sha(format(index, "x")),
        portfolio_decision_id=PortfolioDecisionId(
            f"portfolio-risk-route-support-{index}"
        ),
        target_position_hash=sha(format(index + 8, "x")),
        account_id=book.account_id,
        symbol=book.symbol,
        side=side,
        intended_quantity=quantity,
        expected_price_lower=9.0,
        expected_price_upper=12.0,
        state=ManualOrderState.FILLED,
        filled_quantity=quantity,
        version=1,
        actor="operator-a",
        reason="synthetic route support",
        created_at=at(FRIDAY, 9, 31) + timedelta(seconds=index),
        updated_at=at(FRIDAY, 9, 32) + timedelta(seconds=index),
        last_actor="operator-a",
        last_reason="synthetic route support",
        position_book_id=book.position_book_id,
        thesis_id=book.thesis_id,
        opportunity_id=book.opportunity_id,
        post_trade_snapshot_id=ArtifactId(
            f"post-trade-risk-route-support-{index}"
        ),
        post_trade_snapshot_hash=sha(format(index + 1, "x")),
    )


def _fill(
    trade: ManualTradeRecord, *, day: date, index: int, quantity: int
) -> Fill:
    return Fill(
        schema_version=FILL_SCHEMA,
        fill_id=FillId(f"fill-risk-route-support-{index}"),
        manual_trade_id=trade.manual_trade_id,
        account_id=trade.account_id,
        symbol=trade.symbol,
        side=trade.side,
        quantity=quantity,
        price=10.0,
        fees=0.0,
        occurred_at=at(day, 10, index),
        recorded_at=at(day, 10, index) + timedelta(seconds=1),
        actor="operator-a",
        reason="synthetic route support",
        external_fill_id=f"external-risk-route-support-{index}",
        fill_kind=FillKind.EXECUTION,
        correction_of_fill_id=None,
    )
