from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from market_regime_alpha.candidates.dataset import (
    CandidateTargetValue,
    TargetObservation,
    TargetObservationStatus,
)
from market_regime_alpha.core.identity import TargetId
from market_regime_alpha.core.time import AvailabilityTime


DECISION_AT = datetime(2026, 7, 15, 6, 55, tzinfo=timezone.utc)
OBSERVED_AT = AvailabilityTime(DECISION_AT + timedelta(days=1))


def test_missing_target_requires_observation_time() -> None:
    with pytest.raises(ValueError, match="MISSING or INVALID target requires observed_at"):
        TargetObservation(
            symbol="000001.SZ",
            status=TargetObservationStatus.MISSING,
            value=None,
            observed_at=None,
        )


def test_not_yet_observed_target_cannot_claim_observation_time() -> None:
    with pytest.raises(ValueError, match="NOT_YET_OBSERVED target must not carry observed_at"):
        CandidateTargetValue(
            target_id=TargetId("target-v1"),
            status=TargetObservationStatus.NOT_YET_OBSERVED,
            value=None,
            observed_at=OBSERVED_AT,
        )


def test_available_candidate_target_requires_value_and_observation_time() -> None:
    with pytest.raises(ValueError, match="AVAILABLE target requires value and observed_at"):
        CandidateTargetValue(
            target_id=TargetId("target-v1"),
            status=TargetObservationStatus.AVAILABLE,
            value=None,
            observed_at=OBSERVED_AT,
        )
