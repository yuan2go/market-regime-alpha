from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from market_regime_alpha.application.decision_system.contracts import (
    ManualPositionObservation,
)
from market_regime_alpha.application.decision_system.window import (
    DailyDecisionWindowPolicy,
    DecisionWindowBlocked,
)
from tests.application.decision_system.support import TRADING_DATE, observation


UTC = timezone.utc


@pytest.mark.parametrize(
    ("hour", "minute", "allowed"),
    ((6, 29, False), (6, 30, True), (6, 45, True), (6, 55, True), (6, 56, False)),
)
def test_daily_decision_is_a_window_not_a_single_point(hour: int, minute: int, allowed: bool) -> None:
    policy = DailyDecisionWindowPolicy()
    as_of = datetime(2026, 8, 6, hour, minute, tzinfo=UTC)

    if allowed:
        policy.require_preview(trading_date=TRADING_DATE, as_of_time=as_of)
        policy.require_finalize(
            trading_date=TRADING_DATE,
            as_of_time=as_of,
            latest_available_at=as_of,
        )
    else:
        with pytest.raises(DecisionWindowBlocked):
            policy.require_preview(trading_date=TRADING_DATE, as_of_time=as_of)
        with pytest.raises(DecisionWindowBlocked):
            policy.require_finalize(
                trading_date=TRADING_DATE,
                as_of_time=as_of,
                latest_available_at=as_of,
            )


def test_finalize_rejects_late_evidence_and_complete_close_bar() -> None:
    policy = DailyDecisionWindowPolicy()
    as_of = datetime(2026, 8, 6, 6, 45, tzinfo=UTC)

    with pytest.raises(DecisionWindowBlocked, match="AVAILABLE_AT_EXCEEDS_AS_OF"):
        policy.require_finalize(
            trading_date=TRADING_DATE,
            as_of_time=as_of,
            latest_available_at=datetime(2026, 8, 6, 6, 46, tzinfo=UTC),
        )
    with pytest.raises(DecisionWindowBlocked, match="COMPLETE_CLOSE_BAR_PROHIBITED"):
        policy.require_finalize(
            trading_date=TRADING_DATE,
            as_of_time=as_of,
            latest_available_at=as_of,
            uses_complete_close_bar=True,
        )


def test_manual_account_is_decimal_append_only_observation_contract() -> None:
    account = observation()

    assert account.total_equity == Decimal("100000.120000")
    assert account.positions[0].average_cost == Decimal("10.123456")
    assert not hasattr(account, "fills")
    assert not hasattr(account, "position_mutations")
    with pytest.raises(TypeError, match="finite Decimal"):
        observation(total_equity=100000.12)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("total", "available", "frozen"),
    ((-1, 0, -1), (100, 101, -1), (100, 80, 10)),
)
def test_manual_position_rejects_invalid_quantity_partition(total: int, available: int, frozen: int) -> None:
    with pytest.raises(ValueError):
        ManualPositionObservation(
            symbol="600000.SH",
            total_quantity=total,
            available_quantity=available,
            frozen_quantity=frozen,
            average_cost=Decimal("10") if total else None,
            observed_market_value=Decimal("100"),
        )
