from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from market_regime_alpha.core.identity import FillId, ManualTradeId
from market_regime_alpha.execution.manual import FILL_SCHEMA, Fill, FillKind, TradeSide
from market_regime_alpha.position import PositionProjector, PositionState


TZ = ZoneInfo("Asia/Shanghai")
NOW = datetime(2026, 7, 20, 15, 0, tzinfo=TZ)


def _fill(
    index: int,
    *,
    side: TradeSide,
    quantity: int,
    price: float,
    fees: float,
    correction_of: FillId | None = None,
    recorded_offset: int | None = None,
) -> Fill:
    occurred = NOW + timedelta(minutes=index)
    return Fill(
        schema_version=FILL_SCHEMA,
        fill_id=FillId(f"position-fill-{index}"),
        manual_trade_id=ManualTradeId(f"position-trade-{side.value.lower()}"),
        account_id="account-a",
        symbol="000001.SZ",
        side=side,
        quantity=quantity,
        price=price,
        fees=fees,
        occurred_at=occurred,
        recorded_at=NOW + timedelta(
            minutes=recorded_offset if recorded_offset is not None else index,
            seconds=1,
        ),
        actor="human-trader-a",
        reason="position projector fixture",
        external_fill_id=f"external-position-{index}",
        fill_kind=(
            FillKind.CORRECTION if correction_of is not None else FillKind.EXECUTION
        ),
        correction_of_fill_id=correction_of,
    )


def test_full_fill_replay_rebuilds_fifo_cost_quantity_and_realized_pnl() -> None:
    buy = _fill(1, side=TradeSide.BUY, quantity=100, price=10.0, fees=10.0)
    sell = _fill(2, side=TradeSide.SELL, quantity=40, price=12.0, fees=4.0)

    first = PositionProjector().project(
        account_id="account-a",
        symbol="000001.SZ",
        fills=(sell, buy),
        as_of=NOW + timedelta(minutes=3),
    )
    replay = PositionProjector().project(
        account_id="account-a",
        symbol="000001.SZ",
        fills=(buy, sell),
        as_of=NOW + timedelta(minutes=3),
    )

    assert first == replay
    assert first.state is PositionState.OPEN
    assert first.total_quantity == 60
    assert first.average_cost == 10.1
    assert first.realized_pnl == pytest.approx(72.0)


def test_position_projector_rejects_future_and_duplicate_fill_evidence() -> None:
    buy = _fill(1, side=TradeSide.BUY, quantity=100, price=10.0, fees=0.0)

    with pytest.raises(ValueError, match="future recorded Fill"):
        PositionProjector().project(
            account_id="account-a",
            symbol="000001.SZ",
            fills=(buy,),
            as_of=NOW,
        )
    with pytest.raises(ValueError, match="duplicate FillId"):
        PositionProjector().project(
            account_id="account-a",
            symbol="000001.SZ",
            fills=(buy, buy),
            as_of=NOW + timedelta(minutes=2),
        )


def test_correction_replaces_original_fill_without_erasing_history() -> None:
    original = _fill(1, side=TradeSide.BUY, quantity=100, price=10.0, fees=0.0)
    correction = _fill(
        3,
        side=TradeSide.BUY,
        quantity=80,
        price=11.0,
        fees=0.0,
        correction_of=original.fill_id,
    )

    snapshot = PositionProjector().project(
        account_id="account-a",
        symbol="000001.SZ",
        fills=(original, correction),
        as_of=NOW + timedelta(minutes=4),
    )

    assert snapshot.total_quantity == 80
    assert snapshot.source_fill_ids == (original.fill_id, correction.fill_id)
    assert snapshot.effective_fill_ids == (correction.fill_id,)
