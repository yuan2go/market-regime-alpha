"""Versioned Next Session Forecast boundary with calibration protection."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite
from typing import Any

from market_regime_alpha.core.identity import TargetId
from market_regime_alpha.evidence.envelope import ArtifactEnvelope


class CalibrationStatus(str, Enum):
    NOT_CALIBRATED = "NOT_CALIBRATED"
    CALIBRATED_EXPLORATORY = "CALIBRATED_EXPLORATORY"
    DATA_INSUFFICIENT = "DATA_INSUFFICIENT"


@dataclass(frozen=True, slots=True)
class ReturnQuantile:
    probability: float
    return_value: float

    def __post_init__(self) -> None:
        if not 0.0 < self.probability < 1.0:
            raise ValueError("return quantile probability must be within (0, 1)")
        if not isfinite(self.return_value):
            raise ValueError("return quantile must be finite")


@dataclass(frozen=True, slots=True)
class NextSessionForecast:
    envelope: ArtifactEnvelope
    symbol: str
    forecast_horizon: str
    target_id: TargetId
    probability_positive_return: float | None
    expected_return: float | None
    return_quantiles: tuple[ReturnQuantile, ...]
    expected_adverse_excursion: float | None
    expected_favorable_excursion: float | None
    confidence: float
    calibration_status: CalibrationStatus
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.probability_positive_return is not None and (
            not 0.0 <= self.probability_positive_return <= 1.0
            or self.calibration_status
            is not CalibrationStatus.CALIBRATED_EXPLORATORY
        ):
            raise ValueError("probability requires explicit calibration evidence")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("forecast confidence must be within [0, 1]")
        for value in (
            self.expected_return,
            self.expected_adverse_excursion,
            self.expected_favorable_excursion,
        ):
            if value is not None and not isfinite(value):
                raise ValueError("Forecast returns must be finite")
        self.envelope.verify_payload(self.artifact_payload())

    def artifact_payload(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "forecast_horizon": self.forecast_horizon,
            "target_id": str(self.target_id),
            "probability_positive_return": self.probability_positive_return,
            "expected_return": self.expected_return,
            "return_quantiles": [
                {
                    "probability": item.probability,
                    "return_value": item.return_value,
                }
                for item in self.return_quantiles
            ],
            "expected_adverse_excursion": self.expected_adverse_excursion,
            "expected_favorable_excursion": self.expected_favorable_excursion,
            "confidence": self.confidence,
            "calibration_status": self.calibration_status.value,
            "reason_codes": list(self.reason_codes),
        }

