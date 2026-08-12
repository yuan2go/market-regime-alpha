from __future__ import annotations

from decimal import Decimal

import pytest

from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.application.research_validation.formal_protocol import (
    ForecastMeasureEstimate,
    ForecastMeasureKind,
    ForecastMeasureStatus,
    OutcomeTargetForecastEstimate,
    OutcomeTargetForecastStatus,
)
from market_regime_alpha.core.identity import ArtifactId


HASH = "sha256:" + "a" * 64


def test_measures_are_independently_available_and_replayable() -> None:
    estimate = OutcomeTargetForecastEstimate(
        target_id=ArtifactId("target:test"),
        target_hash=HASH,
        measures=tuple(
            sorted(
                (
                    ForecastMeasureEstimate(
                        ForecastMeasureKind.EXPECTED_RETURN,
                        ForecastMeasureStatus.AVAILABLE,
                        Decimal("0.012"),
                    ),
                    ForecastMeasureEstimate(
                        ForecastMeasureKind.EXPECTED_MFE,
                        ForecastMeasureStatus.NOT_ESTIMABLE,
                        None,
                        ("TARGET_NOT_IN_TRAINING_PLAN",),
                    ),
                    ForecastMeasureEstimate(
                        ForecastMeasureKind.RETURN_POSITIVE_RAW_LOGIT,
                        ForecastMeasureStatus.AVAILABLE,
                        Decimal("0.7"),
                    ),
                ),
                key=lambda item: item.key,
            )
        ),
        reason_codes=(),
    )

    assert estimate.status is OutcomeTargetForecastStatus.AVAILABLE_FOR_RESEARCH
    assert estimate.expected_return == Decimal("0.012")
    assert estimate.expected_mfe is None
    assert estimate.measure(ForecastMeasureKind.RETURN_POSITIVE_RAW_LOGIT).is_raw_score
    assert estimate == OutcomeTargetForecastEstimate.from_canonical_dict(
        estimate.to_canonical_dict()
    )


def test_probability_requires_real_calibration_evidence_but_raw_logit_does_not() -> None:
    ForecastMeasureEstimate(
        ForecastMeasureKind.UPPER_BEFORE_LOWER_RAW_LOGIT,
        ForecastMeasureStatus.AVAILABLE,
        Decimal("-0.25"),
    )
    with pytest.raises(ValueError, match="Calibration Artifact evidence"):
        ForecastMeasureEstimate(
            ForecastMeasureKind.UPPER_BEFORE_LOWER_PROBABILITY,
            ForecastMeasureStatus.AVAILABLE,
            Decimal("0.45"),
        )

    calibrated = ForecastMeasureEstimate(
        ForecastMeasureKind.UPPER_BEFORE_LOWER_PROBABILITY,
        ForecastMeasureStatus.AVAILABLE,
        Decimal("0.45"),
        calibration_reference=ValidationArtifactReference(
            "CALIBRATION_ARTIFACT",
            ArtifactId("calibration:test"),
            HASH,
        ),
    )
    assert calibrated.is_raw_score is False


def test_non_probability_measure_cannot_smuggle_calibration_evidence() -> None:
    with pytest.raises(ValueError, match="Only calibrated probability"):
        ForecastMeasureEstimate(
            ForecastMeasureKind.RETURN_POSITIVE_RAW_LOGIT,
            ForecastMeasureStatus.AVAILABLE,
            Decimal("0.1"),
            calibration_reference=ValidationArtifactReference(
                "CALIBRATION_ARTIFACT",
                ArtifactId("calibration:test"),
                HASH,
            ),
        )
