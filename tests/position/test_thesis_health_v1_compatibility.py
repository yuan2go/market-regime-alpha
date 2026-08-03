from __future__ import annotations

import pytest

import market_regime_alpha.execution  # noqa: F401  # existing package initialization order
from market_regime_alpha.application.trading_lifecycle import (
    OperationalPositionAssessmentServiceV2,
)
from market_regime_alpha.position import ThesisHealthObservation

from tests.position.test_assessments import _config, _observation, _position, _thesis, NOW


def test_v1_reader_still_restores_historical_health_fixture() -> None:
    historical = _observation()

    restored = ThesisHealthObservation.from_canonical_dict(
        historical.to_canonical_dict()
    )
    assert restored == historical
    assert restored.signal_support is True


def test_v1_observation_cannot_enter_new_v2_operational_path() -> None:
    with pytest.raises(TypeError, match="ThesisHealthObservationV2"):
        OperationalPositionAssessmentServiceV2().assess(
            thesis=_thesis(),
            position=_position(),
            health_observation=_observation(),  # type: ignore[arg-type]
            configuration=_config(),
            assessed_at=NOW,
            actor="reviewer-a",
            reason="V1 must remain legacy-only",
        )
