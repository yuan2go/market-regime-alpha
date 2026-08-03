from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
import sqlite3
from zoneinfo import ZoneInfo

import pytest

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
from market_regime_alpha.portfolio import (
    ExecutionConstraintState,
    ReducingExecutionObservation,
    RiskChangeKind,
    RiskReducingGateConfiguration,
    RiskReducingExecutionGate,
    RiskReducingDecisionState,
    RiskRouteApplicationService,
    SQLiteCompleteAccountPortfolioRiskRepository,
    SQLiteRiskRouteRepository,
)
from market_regime_alpha.portfolio.sqlite_risk_routes import (
    RISK_ROUTE_DOWN_MIGRATION,
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


def _sha(character: str) -> str:
    return "sha256:" + character * 64


def _at(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=TZ)


def _calendar():
    return build_trading_calendar_artifact(
        source_dataset_id=DatasetId("risk-route-calendar"),
        market="CN_A_SHARE",
        calendar_version="synthetic-risk-route-v1",
        timezone_name="Asia/Shanghai",
        sessions=tuple(
            TradingSession(day, _at(day, 15))
            for day in (FRIDAY, MONDAY, TUESDAY)
        ),
    )


def _status(state: SymbolTradingState = SymbolTradingState.TRADABLE):
    return SymbolTradingSessionStatus.create(
        symbol="000001.SZ",
        session_date=MONDAY,
        state=state,
        source_artifact_id=ArtifactId("risk-route-symbol-status"),
        source_artifact_hash=_sha("a"),
        availability_time=NOW - timedelta(hours=1),
        reason_code=f"SYNTHETIC_{state.value}",
    )


def _book() -> PositionBook:
    return PositionBook.open(
        account_id="account-a",
        symbol="000001.SZ",
        opportunity_id=OpportunityId("opportunity-risk-route"),
        thesis_id=ThesisId("thesis-risk-route"),
        thesis_version=0,
        opened_at=_at(FRIDAY, 9, 30),
        actor="operator-a",
        reason="synthetic route fixture",
    )


def _trade(book: PositionBook, side: TradeSide, quantity: int, index: int):
    return ManualTradeRecord(
        schema_version=TRACEABLE_MANUAL_TRADE_SCHEMA,
        manual_trade_id=ManualTradeId(f"manual-trade-risk-route-{index}"),
        risk_decision_id=RiskDecisionId(f"risk-route-{index}"),
        risk_decision_hash=_sha(format(index, "x")),
        portfolio_decision_id=PortfolioDecisionId(f"portfolio-risk-route-{index}"),
        target_position_hash=_sha(format(index + 8, "x")),
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
        reason="synthetic route fixture",
        created_at=_at(FRIDAY, 9, 31) + timedelta(seconds=index),
        updated_at=_at(FRIDAY, 9, 32) + timedelta(seconds=index),
        last_actor="operator-a",
        last_reason="synthetic route fixture",
        position_book_id=book.position_book_id,
        thesis_id=book.thesis_id,
        opportunity_id=book.opportunity_id,
        post_trade_snapshot_id=ArtifactId(f"post-trade-risk-route-{index}"),
        post_trade_snapshot_hash=_sha(format(index + 1, "x")),
    )


def _fill(trade: ManualTradeRecord, *, day: date, index: int, quantity: int):
    return Fill(
        schema_version=FILL_SCHEMA,
        fill_id=FillId(f"fill-risk-route-{index}"),
        manual_trade_id=trade.manual_trade_id,
        account_id=trade.account_id,
        symbol=trade.symbol,
        side=trade.side,
        quantity=quantity,
        price=10.0,
        fees=0.0,
        occurred_at=_at(day, 10, index),
        recorded_at=_at(day, 10, index) + timedelta(seconds=1),
        actor="operator-a",
        reason="synthetic route fixture",
        external_fill_id=f"external-risk-route-{index}",
        fill_kind=FillKind.EXECUTION,
        correction_of_fill_id=None,
    )


def _position(
    *,
    status: SymbolTradingState = SymbolTradingState.TRADABLE,
    same_session: bool = False,
    reconciliation: bool = False,
    as_of: datetime = NOW,
) -> PositionSnapshot:
    book = _book()
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
    return PositionProjector().project_book_t_plus_one(
        book=book,
        trades=trades,
        fills=fills,
        calendar=_calendar(),
        symbol_session_statuses=(_status(status),),
        as_of=as_of,
    )


def _configuration() -> RiskReducingGateConfiguration:
    return RiskReducingGateConfiguration.create(
        profile_id="test_risk_reducing_gate_v2",
        maximum_position_age_seconds=60.0,
        maximum_observation_age_seconds=120.0,
        maximum_liquidity_participation=0.1,
    )


def _observation(
    state: ExecutionConstraintState = ExecutionConstraintState.EXECUTABLE,
    *,
    average_daily_volume: int = 10_000,
    symbol: str = "000001.SZ",
    session_date: date = MONDAY,
    availability_time: datetime | None = None,
) -> ReducingExecutionObservation:
    return ReducingExecutionObservation.create(
        symbol=symbol,
        session_date=session_date,
        state=state,
        reference_price=10.0,
        average_daily_volume=average_daily_volume,
        source_artifact_id=ArtifactId("execution-constraint-source"),
        source_artifact_hash=_sha("b"),
        availability_time=(
            availability_time
            if availability_time is not None
            else NOW - timedelta(minutes=1)
        ),
        reason_code=f"SYNTHETIC_{state.value}",
    )


def _service(tmp_path: Path):
    repository = SQLiteRiskRouteRepository(tmp_path / "risk-routes.sqlite3")
    return RiskRouteApplicationService(repository), repository


def test_valid_exit_does_not_depend_on_increasing_risk_service(tmp_path) -> None:
    service, _ = _service(tmp_path)
    position = _position()

    decision = service.assess_reducing(
        action=RiskChangeKind.EXIT,
        position=position,
        target_quantity=0,
        order_quantity=100,
        execution_observation=_observation(),
        configuration=_configuration(),
        actor="risk-reduction-operator",
        reason="full manual exit after unrelated opening-risk timeout",
        assessed_at=NOW + timedelta(seconds=1),
        idempotency_key="valid-exit",
    )

    assert decision.state is RiskReducingDecisionState.PERMITTED_FOR_MANUAL_CONFIRMATION
    assert decision.reason_codes == ("STRICT_RISK_REDUCTION_PERMITTED",)


def test_valid_reduce_is_permitted_for_manual_confirmation(tmp_path) -> None:
    service, _ = _service(tmp_path)

    decision = service.assess_reducing(
        action=RiskChangeKind.REDUCE,
        position=_position(),
        target_quantity=80,
        order_quantity=20,
        execution_observation=_observation(),
        configuration=_configuration(),
        actor="risk-reduction-operator",
        reason="strict manual reduction",
        assessed_at=NOW + timedelta(seconds=1),
        idempotency_key="valid-reduce",
    )

    assert decision.state is RiskReducingDecisionState.PERMITTED_FOR_MANUAL_CONFIRMATION
    assert decision.target_quantity == 80
    assert decision.order_quantity == 20


@pytest.mark.parametrize("action", (RiskChangeKind.OPEN, RiskChangeKind.ADD))
def test_increasing_actions_are_rejected_before_the_reducing_gate(
    tmp_path, action: RiskChangeKind
) -> None:
    service, _ = _service(tmp_path)

    with pytest.raises(ValueError, match="increasing Risk"):
        service.assess_reducing(
            action=action,
            position=_position(),
            target_quantity=120,
            order_quantity=20,
            execution_observation=_observation(),
            configuration=_configuration(),
            actor="risk-reduction-operator",
            reason="bypass attempt",
            assessed_at=NOW + timedelta(seconds=1),
            idempotency_key=f"reject-{action.value.lower()}",
        )


@pytest.mark.parametrize("action", (RiskChangeKind.OPEN, RiskChangeKind.ADD))
def test_increasing_actions_are_rejected_by_the_reducing_gate(
    action: RiskChangeKind,
) -> None:
    with pytest.raises(ValueError, match="increasing Risk"):
        RiskReducingExecutionGate().assess(
            action=action,
            position=_position(),
            target_quantity=120,
            order_quantity=20,
            execution_observation=_observation(),
            configuration=_configuration(),
            actor="risk-reduction-operator",
            reason="direct gate bypass attempt",
            assessed_at=NOW + timedelta(seconds=1),
        )


def test_application_service_rejects_idempotency_key_semantic_conflict(
    tmp_path,
) -> None:
    service, _ = _service(tmp_path)
    arguments = {
        "action": RiskChangeKind.REDUCE,
        "position": _position(),
        "target_quantity": 80,
        "order_quantity": 20,
        "execution_observation": _observation(),
        "configuration": _configuration(),
        "actor": "risk-reduction-operator",
        "reason": "original reducing command",
        "assessed_at": NOW + timedelta(seconds=1),
        "idempotency_key": "application-conflict",
    }
    service.assess_reducing(**arguments)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="idempotency key reused"):
        service.assess_reducing(
            **{**arguments, "reason": "different command semantics"}  # type: ignore[arg-type]
        )


@pytest.mark.parametrize(
    ("target_quantity", "order_quantity"),
    ((80.5, 19.5), (True, 99)),
)
def test_application_service_rejects_non_integer_order_quantities(
    tmp_path,
    target_quantity: object,
    order_quantity: object,
) -> None:
    service, _ = _service(tmp_path)

    with pytest.raises(ValueError, match="must be an integer"):
        service.assess_reducing(
            action=RiskChangeKind.REDUCE,
            position=_position(),
            target_quantity=target_quantity,  # type: ignore[arg-type]
            order_quantity=order_quantity,  # type: ignore[arg-type]
            execution_observation=_observation(),
            configuration=_configuration(),
            actor="risk-reduction-operator",
            reason="illegal quantity type",
            assessed_at=NOW + timedelta(seconds=1),
            idempotency_key="illegal-quantity-type",
        )


@pytest.mark.parametrize(
    ("position", "observation", "reason_code"),
    (
        (
            _position(as_of=NOW - timedelta(minutes=2)),
            _observation(),
            "POSITION_SNAPSHOT_STALE",
        ),
        (
            _position(),
            _observation(availability_time=NOW - timedelta(minutes=3)),
            "EXECUTION_OBSERVATION_STALE",
        ),
        (
            _position(),
            _observation(availability_time=NOW + timedelta(seconds=2)),
            "EXECUTION_OBSERVATION_UNAVAILABLE",
        ),
        (
            _position(),
            _observation(symbol="000002.SZ"),
            "EXECUTION_OBSERVATION_SCOPE_MISMATCH",
        ),
        (
            _position(),
            _observation(session_date=FRIDAY),
            "EXECUTION_OBSERVATION_SCOPE_MISMATCH",
        ),
    ),
)
def test_stale_future_or_scope_mismatched_evidence_is_never_permitted(
    tmp_path,
    position: PositionSnapshot,
    observation: ReducingExecutionObservation,
    reason_code: str,
) -> None:
    service, _ = _service(tmp_path)

    decision = service.assess_reducing(
        action=RiskChangeKind.EXIT,
        position=position,
        target_quantity=0,
        order_quantity=100,
        execution_observation=observation,
        configuration=_configuration(),
        actor="risk-reduction-operator",
        reason="freshness and scope fixture",
        assessed_at=NOW + timedelta(seconds=1),
        idempotency_key=f"insufficient-{reason_code}",
    )

    assert decision.state is RiskReducingDecisionState.DATA_INSUFFICIENT
    assert reason_code in decision.reason_codes


@pytest.mark.parametrize(
    ("action", "position", "target", "order", "reason_code"),
    (
        (
            RiskChangeKind.REDUCE,
            _position(same_session=True),
            80,
            20,
            "T_PLUS_ONE_NOT_SELLABLE",
        ),
        (
            RiskChangeKind.REDUCE,
            _position(),
            100,
            0,
            "REDUCE_REQUIRES_STRICTLY_LOWER_TARGET",
        ),
        (
            RiskChangeKind.EXIT,
            _position(),
            80,
            20,
            "EXIT_REQUIRES_ZERO_TARGET",
        ),
    ),
)
def test_reducing_quantity_boundaries_are_blocked(
    tmp_path,
    action: RiskChangeKind,
    position: PositionSnapshot,
    target: int,
    order: int,
    reason_code: str,
) -> None:
    service, _ = _service(tmp_path)

    decision = service.assess_reducing(
        action=action,
        position=position,
        target_quantity=target,
        order_quantity=order,
        execution_observation=_observation(),
        configuration=_configuration(),
        actor="risk-reduction-operator",
        reason="quantity boundary fixture",
        assessed_at=NOW + timedelta(seconds=1),
        idempotency_key=f"quantity-{reason_code}",
    )

    assert decision.state is RiskReducingDecisionState.BLOCKED
    assert reason_code in decision.reason_codes


@pytest.mark.parametrize(
    ("action", "target", "order", "reason_code"),
    (
        (RiskChangeKind.REDUCE, 120, 20, "RISK_REDUCTION_WOULD_INCREASE_POSITION"),
        (RiskChangeKind.REDUCE, 80, 30, "REDUCING_ORDER_QUANTITY_MISMATCH"),
        (RiskChangeKind.EXIT, 0, 101, "ORDER_QUANTITY_EXCEEDS_POSITION"),
    ),
)
def test_reducing_gate_cannot_be_used_to_increase_or_overstate_quantity(
    tmp_path, action, target, order, reason_code
) -> None:
    service, _ = _service(tmp_path)
    decision = service.assess_reducing(
        action=action,
        position=_position(),
        target_quantity=target,
        order_quantity=order,
        execution_observation=_observation(),
        configuration=_configuration(),
        actor="risk-reduction-operator",
        reason="negative route fixture",
        assessed_at=NOW + timedelta(seconds=1),
        idempotency_key=f"invalid-{reason_code}",
    )
    assert decision.state is RiskReducingDecisionState.BLOCKED
    assert reason_code in decision.reason_codes


def test_t_plus_one_reconciliation_and_market_constraints_are_distinct(tmp_path) -> None:
    service, _ = _service(tmp_path)
    cases = (
        (
            _position(same_session=True),
            _observation(),
            "T_PLUS_ONE_NOT_SELLABLE",
        ),
        (
            _position(same_session=True, reconciliation=True),
            _observation(),
            "POSITION_RECONCILIATION_REQUIRED",
        ),
        (
            _position(status=SymbolTradingState.SUSPENDED),
            _observation(ExecutionConstraintState.SUSPENDED),
            "EXIT_BLOCKED_BY_MARKET_CONSTRAINT",
        ),
        (
            _position(),
            _observation(ExecutionConstraintState.PRICE_LIMIT_BLOCKED),
            "EXIT_BLOCKED_BY_MARKET_CONSTRAINT",
        ),
        (
            _position(),
            _observation(ExecutionConstraintState.UNKNOWN),
            "EXECUTION_STATE_UNKNOWN",
        ),
    )
    for index, (position, observation, reason_code) in enumerate(cases):
        decision = service.assess_reducing(
            action=RiskChangeKind.EXIT,
            position=position,
            target_quantity=0,
            order_quantity=100,
            execution_observation=observation,
            configuration=_configuration(),
            actor="risk-reduction-operator",
            reason="structured blocked exit fixture",
            assessed_at=NOW + timedelta(seconds=1),
            idempotency_key=f"blocked-exit-{index}",
        )
        assert decision.state is not RiskReducingDecisionState.PERMITTED_FOR_MANUAL_CONFIRMATION
        assert reason_code in decision.reason_codes


def test_liquidity_idempotency_restart_audit_and_migration(tmp_path) -> None:
    service, repository = _service(tmp_path)
    arguments = {
        "action": RiskChangeKind.REDUCE,
        "position": _position(),
        "target_quantity": 80,
        "order_quantity": 20,
        "execution_observation": _observation(average_daily_volume=100),
        "configuration": _configuration(),
        "actor": "risk-reduction-operator",
        "reason": "manual audited reduction",
        "assessed_at": NOW + timedelta(seconds=1),
        "idempotency_key": "liquidity-reduction",
    }
    first = service.assess_reducing(**arguments)  # type: ignore[arg-type]
    duplicate = service.assess_reducing(**arguments)  # type: ignore[arg-type]
    restarted = SQLiteRiskRouteRepository(repository.path)

    assert duplicate == first
    assert first.state is RiskReducingDecisionState.BLOCKED
    assert "LIQUIDITY_PARTICIPATION_EXCEEDED" in first.reason_codes
    assert first.actor == "risk-reduction-operator"
    assert first.reason == "manual audited reduction"
    assert restarted.get_reducing_decision(first.decision_id) == first

    SQLiteCompleteAccountPortfolioRiskRepository(repository.path)
    with sqlite3.connect(repository.path) as connection:
        connection.executescript(
            RISK_ROUTE_DOWN_MIGRATION.read_text(encoding="utf-8")
        )
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    assert "risk_reducing_decisions" not in tables
    assert "complete_account_risk_decisions" in tables
