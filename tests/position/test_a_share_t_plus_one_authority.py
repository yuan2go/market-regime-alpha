from __future__ import annotations

from datetime import date, datetime, timedelta
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
from market_regime_alpha.data import (
    TradingSession,
    build_trading_calendar_artifact,
)
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
from market_regime_alpha.position import (
    LotSettlementState,
    PositionProjector,
    PositionSellabilityState,
    PositionState,
    SymbolTradingSessionStatus,
    SymbolTradingState,
)
from market_regime_alpha.portfolio import (
    AccountReconciliationState,
    PositionAuthorityAccountSnapshotBuilder,
    PositionRiskValuationInput,
)
from market_regime_alpha.position import PositionSnapshot


TZ = ZoneInfo("Asia/Shanghai")
FRIDAY = date(2026, 7, 17)
MONDAY = date(2026, 7, 20)
TUESDAY = date(2026, 7, 21)


def _at(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=TZ)


def _calendar(*days: date):
    return build_trading_calendar_artifact(
        source_dataset_id=DatasetId("synthetic-calendar-dataset-v1"),
        market="CN_A_SHARE",
        calendar_version="synthetic-explicit-sessions-v1",
        timezone_name="Asia/Shanghai",
        sessions=tuple(
            TradingSession(trade_date=day, session_close=_at(day, 15))
            for day in days
        ),
    )


def _status(day: date, state: SymbolTradingState = SymbolTradingState.TRADABLE):
    return SymbolTradingSessionStatus.create(
        symbol="000001.SZ",
        session_date=day,
        state=state,
        source_artifact_id=ArtifactId(f"symbol-status-{day.isoformat()}"),
        source_artifact_hash="sha256:" + day.strftime("%d")[-1] * 64,
        availability_time=_at(day, 9),
        reason_code=f"SYNTHETIC_{state.value}",
    )


def _book() -> PositionBook:
    return PositionBook.open(
        account_id="account-a",
        symbol="000001.SZ",
        opportunity_id=OpportunityId("opportunity-t-plus-one"),
        thesis_id=ThesisId("thesis-t-plus-one"),
        thesis_version=0,
        opened_at=_at(FRIDAY, 9, 30),
        actor="test-operator",
        reason="synthetic T+1 fixture",
    )


def _trade(book: PositionBook, side: TradeSide, quantity: int, index: int):
    return ManualTradeRecord(
        schema_version=TRACEABLE_MANUAL_TRADE_SCHEMA,
        manual_trade_id=ManualTradeId(f"manual-trade-t-plus-one-{index}"),
        risk_decision_id=RiskDecisionId(f"risk-t-plus-one-{index}"),
        risk_decision_hash="sha256:" + format(index, "x") * 64,
        portfolio_decision_id=PortfolioDecisionId(f"portfolio-t-plus-one-{index}"),
        target_position_hash="sha256:" + format(index + 8, "x") * 64,
        account_id=book.account_id,
        symbol=book.symbol,
        side=side,
        intended_quantity=quantity,
        expected_price_lower=9.0,
        expected_price_upper=12.0,
        state=ManualOrderState.FILLED,
        filled_quantity=quantity,
        version=1,
        actor="test-operator",
        reason="synthetic filled trade",
        created_at=_at(FRIDAY, 9, 31) + timedelta(seconds=index),
        updated_at=_at(FRIDAY, 9, 32) + timedelta(seconds=index),
        last_actor="test-operator",
        last_reason="synthetic filled trade",
        position_book_id=book.position_book_id,
        thesis_id=book.thesis_id,
        opportunity_id=book.opportunity_id,
        post_trade_snapshot_id=ArtifactId(f"post-trade-t-plus-one-{index}"),
        post_trade_snapshot_hash="sha256:" + format(index + 1, "x") * 64,
    )


def _fill(
    trade: ManualTradeRecord,
    *,
    index: int,
    day: date,
    quantity: int,
    price: float,
    kind: FillKind = FillKind.EXECUTION,
    correction_of_fill_id: FillId | None = None,
) -> Fill:
    return Fill(
        schema_version=FILL_SCHEMA,
        fill_id=FillId(f"fill-t-plus-one-{index}"),
        manual_trade_id=trade.manual_trade_id,
        account_id=trade.account_id,
        symbol=trade.symbol,
        side=trade.side,
        quantity=quantity,
        price=price,
        fees=0.0,
        occurred_at=_at(day, 10, index),
        recorded_at=_at(day, 10, index) + timedelta(seconds=1),
        actor="test-operator",
        reason="synthetic fill",
        external_fill_id=f"external-t-plus-one-{index}",
        fill_kind=kind,
        correction_of_fill_id=correction_of_fill_id,
    )


def _project(
    *,
    calendar,
    trades,
    fills,
    as_of: datetime,
    statuses,
):
    return PositionProjector().project_book_t_plus_one(
        book=_book(),
        trades=trades,
        fills=fills,
        calendar=calendar,
        symbol_session_statuses=statuses,
        as_of=as_of,
    )


def test_same_session_buy_is_frozen_and_same_session_sell_reconciles() -> None:
    calendar = _calendar(FRIDAY, MONDAY)
    book = _book()
    buy = _trade(book, TradeSide.BUY, 100, 1)
    buy_fill = _fill(buy, index=1, day=FRIDAY, quantity=100, price=10.0)
    snapshot = _project(
        calendar=calendar,
        trades=(buy,),
        fills=(buy_fill,),
        as_of=_at(FRIDAY, 14, 55),
        statuses=(_status(FRIDAY),),
    )

    assert snapshot.total_quantity == 100
    assert snapshot.available_quantity == 0
    assert snapshot.frozen_quantity == 100
    assert snapshot.today_acquired_quantity == 100
    assert snapshot.sellability_state is PositionSellabilityState.T_PLUS_ONE_FROZEN
    assert snapshot.lots[0].sellable_from_session == MONDAY
    assert snapshot.lots[0].settlement_state is LotSettlementState.FROZEN_T_PLUS_ONE

    sell = _trade(book, TradeSide.SELL, 100, 2)
    sell_fill = _fill(sell, index=2, day=FRIDAY, quantity=100, price=10.1)
    invalid = _project(
        calendar=calendar,
        trades=(buy, sell),
        fills=(buy_fill, sell_fill),
        as_of=_at(FRIDAY, 14, 55),
        statuses=(_status(FRIDAY),),
    )
    assert invalid.state is PositionState.RECONCILIATION_REQUIRED
    assert "T_PLUS_ONE_SELL_EXCEEDS_AVAILABLE" in invalid.reason_codes


@pytest.mark.parametrize("next_session_date", (MONDAY, TUESDAY))
def test_friday_and_pre_holiday_buys_use_next_explicit_session(
    next_session_date: date,
) -> None:
    calendar = _calendar(FRIDAY, next_session_date)
    book = _book()
    buy = _trade(book, TradeSide.BUY, 100, 1)
    fill = _fill(buy, index=1, day=FRIDAY, quantity=100, price=10.0)

    friday = _project(
        calendar=calendar,
        trades=(buy,),
        fills=(fill,),
        as_of=_at(FRIDAY, 14, 55),
        statuses=(_status(FRIDAY),),
    )
    next_session = _project(
        calendar=calendar,
        trades=(buy,),
        fills=(fill,),
        as_of=_at(next_session_date, 14, 55),
        statuses=(_status(next_session_date),),
    )

    assert friday.lots[0].sellable_from_session == next_session_date
    assert next_session.available_quantity == 100
    assert next_session.frozen_quantity == 0
    assert next_session.today_acquired_quantity == 0
    assert next_session.sellability_state is PositionSellabilityState.AVAILABLE
    assert PositionSnapshot.from_canonical_dict(
        next_session.to_canonical_dict()
    ) == next_session


def test_complete_account_input_derives_available_quantity_from_position_authority() -> None:
    calendar = _calendar(FRIDAY, MONDAY)
    book = _book()
    buy = _trade(book, TradeSide.BUY, 100, 1)
    fill = _fill(buy, index=1, day=FRIDAY, quantity=100, price=10.0)
    as_of = _at(MONDAY, 14, 55)
    snapshot = _project(
        calendar=calendar,
        trades=(buy,),
        fills=(fill,),
        as_of=as_of,
        statuses=(_status(MONDAY),),
    )
    valuation = PositionRiskValuationInput(
        symbol=book.symbol,
        theme_id="theme-bank",
        market_price=10.0,
        loss_per_share=1.0,
        source_artifact_id=ArtifactId("risk-valuation-source"),
        source_artifact_hash="sha256:" + "a" * 64,
    )
    builder = PositionAuthorityAccountSnapshotBuilder()
    account = builder.build(
        account_id=book.account_id,
        as_of=as_of,
        source_reference="synthetic-reconciled-account-statement",
        net_asset_value=100_000.0,
        available_cash=99_000.0,
        open_books=(book,),
        position_snapshots=(snapshot,),
        valuations=(valuation,),
        reconciliation_state=AccountReconciliationState.RECONCILED,
        version=1,
    )

    assert account.all_positions[0].available_quantity == snapshot.available_quantity
    assert str(account.all_positions[0].source_position_snapshot_id) == str(
        snapshot.snapshot_id
    )

    legacy = PositionProjector().project_book(
        book=book,
        trades=(buy,),
        fills=(fill,),
        as_of=as_of,
    )
    with pytest.raises(ValueError, match="invalid for account Risk"):
        builder.build(
            account_id=book.account_id,
            as_of=as_of,
            source_reference="legacy-position-is-not-sellability-authority",
            net_asset_value=100_000.0,
            available_cash=99_000.0,
            open_books=(book,),
            position_snapshots=(legacy,),
            valuations=(valuation,),
            reconciliation_state=AccountReconciliationState.RECONCILED,
            version=1,
        )


def test_suspension_and_missing_status_fail_closed() -> None:
    calendar = _calendar(FRIDAY, MONDAY)
    book = _book()
    buy = _trade(book, TradeSide.BUY, 100, 1)
    fill = _fill(buy, index=1, day=FRIDAY, quantity=100, price=10.0)

    suspended = _project(
        calendar=calendar,
        trades=(buy,),
        fills=(fill,),
        as_of=_at(MONDAY, 14, 55),
        statuses=(_status(MONDAY, SymbolTradingState.SUSPENDED),),
    )
    assert suspended.available_quantity == 0
    assert suspended.frozen_quantity == 100
    assert suspended.sellability_state is PositionSellabilityState.SUSPENDED
    assert "SYMBOL_SUSPENDED" in suspended.reason_codes

    with pytest.raises(ValueError, match="session status evidence is required"):
        _project(
            calendar=calendar,
            trades=(buy,),
            fills=(fill,),
            as_of=_at(MONDAY, 14, 55),
            statuses=(),
        )


def test_multiple_lots_partial_sell_and_correction_replay_deterministically() -> None:
    calendar = _calendar(FRIDAY, MONDAY, TUESDAY)
    book = _book()
    friday_buy = _trade(book, TradeSide.BUY, 100, 1)
    monday_buy = _trade(book, TradeSide.BUY, 50, 2)
    monday_sell = _trade(book, TradeSide.SELL, 60, 3)
    first = _fill(friday_buy, index=1, day=FRIDAY, quantity=100, price=10.0)
    correction = _fill(
        friday_buy,
        index=4,
        day=FRIDAY,
        quantity=80,
        price=10.0,
        kind=FillKind.CORRECTION,
        correction_of_fill_id=first.fill_id,
    )
    second = _fill(monday_buy, index=2, day=MONDAY, quantity=50, price=11.0)
    sold = _fill(monday_sell, index=3, day=MONDAY, quantity=60, price=12.0)
    inputs = {
        "calendar": calendar,
        "trades": (friday_buy, monday_buy, monday_sell),
        "fills": (first, correction, second, sold),
        "as_of": _at(MONDAY, 14, 55),
        "statuses": (_status(MONDAY),),
    }

    snapshot = _project(**inputs)
    replay = _project(**inputs)

    assert replay == snapshot
    assert snapshot.state is PositionState.OPEN
    assert snapshot.total_quantity == 70
    assert snapshot.available_quantity == 20
    assert snapshot.frozen_quantity == 50
    assert snapshot.today_acquired_quantity == 50
    assert [lot.quantity_remaining for lot in snapshot.lots] == [20, 50]
    assert snapshot.effective_fill_ids == (
        correction.fill_id,
        second.fill_id,
        sold.fill_id,
    )


def test_missing_calendar_session_or_future_status_fails_closed() -> None:
    book = _book()
    buy = _trade(book, TradeSide.BUY, 100, 1)
    fill = _fill(buy, index=1, day=FRIDAY, quantity=100, price=10.0)
    with pytest.raises(LookupError, match="no later trading session"):
        _project(
            calendar=_calendar(FRIDAY),
            trades=(buy,),
            fills=(fill,),
            as_of=_at(FRIDAY, 14, 55),
            statuses=(_status(FRIDAY),),
        )

    future_status = SymbolTradingSessionStatus.create(
        symbol="000001.SZ",
        session_date=MONDAY,
        state=SymbolTradingState.TRADABLE,
        source_artifact_id=ArtifactId("future-status"),
        source_artifact_hash="sha256:" + "f" * 64,
        availability_time=_at(MONDAY, 15),
        reason_code="FUTURE_STATUS",
    )
    with pytest.raises(ValueError, match="unavailable symbol session status"):
        _project(
            calendar=_calendar(FRIDAY, MONDAY),
            trades=(buy,),
            fills=(fill,),
            as_of=_at(MONDAY, 14, 55),
            statuses=(future_status,),
        )
