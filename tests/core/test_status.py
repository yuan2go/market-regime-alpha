from __future__ import annotations

from market_regime_alpha.core.status import InputAvailabilityStatus


def test_only_available_input_status_is_usable() -> None:
    assert InputAvailabilityStatus.AVAILABLE.is_usable
    assert all(
        not status.is_usable
        for status in InputAvailabilityStatus
        if status is not InputAvailabilityStatus.AVAILABLE
    )


def test_strategy_no_action_is_not_an_input_status() -> None:
    assert "NO_ACTION" not in {status.value for status in InputAvailabilityStatus}
