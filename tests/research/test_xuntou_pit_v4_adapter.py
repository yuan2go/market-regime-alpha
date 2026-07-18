from datetime import datetime

from market_regime_alpha.research.xuntou_pit_v4_adapter import (
    derive_research_orderability,
    qualify_evaluation_evidence,
)
from market_regime_alpha.research.xuntou_pit_v4_contract import ResearchOrderabilityStatus


DECISION = datetime.fromisoformat("2026-07-18T14:55:00+08:00")


def test_no_historical_quote_remains_unknown() -> None:
    result = derive_research_orderability(
        decision_time=DECISION,
        quote_observed_at=None,
        available_at=DECISION,
        snapshot_finalized=False,
        trading_status="TRADING",
        suspension_status="NOT_SUSPENDED",
        reference_price=10.0,
        best_ask_price=None,
        best_ask_volume=None,
        best_bid_price=None,
        best_bid_volume=None,
        limit_up_price=None,
        limit_down_price=None,
    )
    assert result.status is ResearchOrderabilityStatus.UNKNOWN


def test_unsuspended_alone_does_not_prove_orderability() -> None:
    result = derive_research_orderability(
        decision_time=DECISION,
        quote_observed_at=DECISION,
        available_at=DECISION,
        snapshot_finalized=True,
        trading_status="TRADING",
        suspension_status="NOT_SUSPENDED",
        reference_price=10.0,
        best_ask_price=None,
        best_ask_volume=None,
        best_bid_price=None,
        best_bid_volume=None,
        limit_up_price=11.0,
        limit_down_price=9.0,
    )
    assert result.status is ResearchOrderabilityStatus.UNKNOWN


def test_late_quote_is_not_decision_time_evidence() -> None:
    result = derive_research_orderability(
        decision_time=DECISION,
        quote_observed_at=datetime.fromisoformat("2026-07-18T15:00:00+08:00"),
        available_at=datetime.fromisoformat("2026-07-18T15:00:01+08:00"),
        snapshot_finalized=True,
        trading_status="TRADING",
        suspension_status="NOT_SUSPENDED",
        reference_price=10.0,
        best_ask_price=10.01,
        best_ask_volume=1000.0,
        best_bid_price=10.0,
        best_bid_volume=1000.0,
        limit_up_price=11.0,
        limit_down_price=9.0,
    )
    assert result.status is ResearchOrderabilityStatus.UNKNOWN


def test_daily_close_cannot_replace_next_session_1030_minute_evidence() -> None:
    result = qualify_evaluation_evidence(
        has_exact_1030_minute=False,
        minute_path_0930_1030_complete=False,
        full_diagnostic_path_complete=False,
        daily_close_available=True,
    )
    assert result.primary_1030_available is False
    assert "DAILY_CLOSE_CANNOT_SUBSTITUTE_FOR_1030" in result.reasons


def test_daily_high_low_cannot_establish_event_order() -> None:
    result = qualify_evaluation_evidence(
        has_exact_1030_minute=True,
        minute_path_0930_1030_complete=True,
        full_diagnostic_path_complete=False,
        daily_close_available=True,
    )
    assert result.primary_1030_available is True
    assert result.path_diagnostics_available is False
    assert "PATH_DIAGNOSTICS_UNAVAILABLE" in result.reasons
