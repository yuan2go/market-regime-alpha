from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pytest

from market_regime_alpha.application.continuous_research.policy import (
    ContinuousDecisionWindowPolicy,
    ContinuousRunState,
    ContinuousSessionPhase,
    default_continuous_decision_window_policy,
)


SHANGHAI = ZoneInfo("Asia/Shanghai")
TRADING_DATE = date(2026, 8, 6)


def _at(hour: int, minute: int, second: int = 0) -> datetime:
    return datetime(2026, 8, 6, hour, minute, second, tzinfo=SHANGHAI)


@pytest.mark.parametrize(
    ("observed_at", "phase", "state", "window_open"),
    (
        (_at(9, 29, 59), ContinuousSessionPhase.PRE_MARKET, ContinuousRunState.PREPARING, False),
        (_at(9, 30), ContinuousSessionPhase.MORNING_SESSION, ContinuousRunState.MONITORING, False),
        (_at(11, 30), ContinuousSessionPhase.MIDDAY_RECESS, ContinuousRunState.WAITING_FOR_NEW_DATA, False),
        (_at(13, 0), ContinuousSessionPhase.AFTERNOON_SESSION, ContinuousRunState.MONITORING, False),
        (_at(14, 29, 59), ContinuousSessionPhase.AFTERNOON_SESSION, ContinuousRunState.MONITORING, False),
        (_at(14, 30), ContinuousSessionPhase.DECISION_WINDOW, ContinuousRunState.DECISION_WINDOW_OPEN, True),
        (_at(14, 55), ContinuousSessionPhase.DECISION_WINDOW, ContinuousRunState.DECISION_WINDOW_OPEN, True),
        (_at(14, 55, 1), ContinuousSessionPhase.AFTERNOON_SESSION, ContinuousRunState.MONITORING, False),
        (_at(15, 0), ContinuousSessionPhase.MARKET_CLOSED, ContinuousRunState.MARKET_CLOSED, False),
    ),
)
def test_policy_projects_session_and_additive_decision_window(
    observed_at: datetime,
    phase: ContinuousSessionPhase,
    state: ContinuousRunState,
    window_open: bool,
) -> None:
    result = default_continuous_decision_window_policy().assess(
        trading_date=TRADING_DATE,
        observed_at=observed_at,
    )

    assert result.session_phase is phase
    assert result.run_state is state
    assert result.decision_window_open is window_open


def test_policy_does_not_require_an_exact_1455_tick() -> None:
    policy = default_continuous_decision_window_policy()

    within_window = policy.assess(
        trading_date=TRADING_DATE,
        observed_at=_at(14, 44, 17),
    )
    after_window = policy.assess(
        trading_date=TRADING_DATE,
        observed_at=_at(14, 56, 23),
    )

    assert within_window.run_state is ContinuousRunState.DECISION_WINDOW_OPEN
    assert after_window.run_state is ContinuousRunState.MONITORING
    assert "EXACT_1455_TICK_NOT_REQUIRED" in within_window.reason_codes


def test_policy_identity_round_trip_is_stable_and_tamper_is_rejected() -> None:
    policy = default_continuous_decision_window_policy()

    restored = ContinuousDecisionWindowPolicy.from_canonical_dict(
        policy.to_canonical_dict()
    )
    changed = ContinuousDecisionWindowPolicy.create(
        policy_version="continuous-research-a-share-v2",
        timezone_name="Asia/Shanghai",
        market_open=time(9, 30),
        midday_start=time(11, 30),
        midday_end=time(13, 0),
        decision_window_open=time(14, 30),
        decision_window_close=time(14, 55),
        market_close=time(15, 0),
        polling_interval_seconds=45,
        provider_timeout_seconds=3,
        provider_max_attempts=2,
        retry_backoff_seconds=1,
        limitations=policy.limitations,
    )

    assert restored == policy
    assert changed.content_hash != policy.content_hash
    with pytest.raises(ValueError, match="hash mismatch"):
        replace(policy, content_hash="sha256:" + "0" * 64)


def test_policy_rejects_naive_or_wrong_date_observation() -> None:
    policy = default_continuous_decision_window_policy()

    with pytest.raises(ValueError, match="timezone-aware"):
        policy.assess(
            trading_date=TRADING_DATE,
            observed_at=datetime(2026, 8, 6, 14, 30),
        )
    with pytest.raises(ValueError, match="trading_date"):
        policy.assess(
            trading_date=TRADING_DATE,
            observed_at=datetime(2026, 8, 7, 14, 30, tzinfo=SHANGHAI),
        )
