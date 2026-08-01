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


class PathForecastStatus(str, Enum):
    AVAILABLE_FOR_RESEARCH = "AVAILABLE_FOR_RESEARCH"
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


@dataclass(frozen=True, slots=True)
class PathForecast:
    """Multi-session path statistics; never an Entry action or probability."""

    envelope: ArtifactEnvelope
    symbol: str
    target_id: TargetId
    forecast_horizon: str
    upper_barrier_return: float
    lower_barrier_return: float
    expected_mfe: float | None
    expected_mae: float | None
    return_quantiles: tuple[ReturnQuantile, ...]
    calibration_status: CalibrationStatus
    forecast_status: PathForecastStatus
    usable_sample_count: int
    excluded_sample_count: int
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.symbol or self.symbol != self.symbol.strip():
            raise ValueError("PathForecast symbol must be non-empty and trimmed")
        if not self.forecast_horizon or self.forecast_horizon != self.forecast_horizon.strip():
            raise ValueError("PathForecast horizon must be non-empty and trimmed")
        if not isfinite(self.upper_barrier_return) or self.upper_barrier_return <= 0.0:
            raise ValueError("upper path barrier must be positive and finite")
        if (
            not isfinite(self.lower_barrier_return)
            or not -1.0 < self.lower_barrier_return < 0.0
        ):
            raise ValueError("lower path barrier must be finite, negative and above -1")
        if self.expected_mfe is not None and (
            not isfinite(self.expected_mfe) or self.expected_mfe < 0.0
        ):
            raise ValueError("MFE must be finite and non-negative")
        if self.expected_mae is not None and (
            not isfinite(self.expected_mae) or self.expected_mae > 0.0
        ):
            raise ValueError("MAE must be finite and non-positive")
        quantile_levels = tuple(item.probability for item in self.return_quantiles)
        if quantile_levels != tuple(sorted(set(quantile_levels))):
            raise ValueError("PathForecast return quantiles must be sorted and unique")
        if self.usable_sample_count < 0 or self.excluded_sample_count < 0:
            raise ValueError("PathForecast sample counts cannot be negative")
        if self.calibration_status is CalibrationStatus.CALIBRATED_EXPLORATORY:
            raise ValueError("PathForecast V1 has no calibration implementation")
        if self.forecast_status is PathForecastStatus.DATA_INSUFFICIENT:
            if (
                self.expected_mfe is not None
                or self.expected_mae is not None
                or self.return_quantiles
            ):
                raise ValueError("insufficient PathForecast cannot carry estimates")
            if self.calibration_status is not CalibrationStatus.DATA_INSUFFICIENT:
                raise ValueError("insufficient PathForecast requires insufficient calibration")
        elif self.calibration_status is not CalibrationStatus.NOT_CALIBRATED:
            raise ValueError("research PathForecast must remain explicitly uncalibrated")
        self.envelope.verify_payload(self.artifact_payload())

    def artifact_payload(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "target_id": str(self.target_id),
            "forecast_horizon": self.forecast_horizon,
            "upper_barrier_return": self.upper_barrier_return,
            "lower_barrier_return": self.lower_barrier_return,
            "expected_mfe": self.expected_mfe,
            "expected_mae": self.expected_mae,
            "return_quantiles": [
                {
                    "probability": item.probability,
                    "return_value": item.return_value,
                }
                for item in self.return_quantiles
            ],
            "calibration_status": self.calibration_status.value,
            "forecast_status": self.forecast_status.value,
            "usable_sample_count": self.usable_sample_count,
            "excluded_sample_count": self.excluded_sample_count,
            "reason_codes": list(self.reason_codes),
        }

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "envelope": self.envelope.to_canonical_dict(),
            **self.artifact_payload(),
        }

    @classmethod
    def from_canonical_dict(cls, payload: dict[str, Any]) -> PathForecast:
        expected = {
            "envelope",
            "symbol",
            "target_id",
            "forecast_horizon",
            "upper_barrier_return",
            "lower_barrier_return",
            "expected_mfe",
            "expected_mae",
            "return_quantiles",
            "calibration_status",
            "forecast_status",
            "usable_sample_count",
            "excluded_sample_count",
            "reason_codes",
        }
        envelope = payload.get("envelope")
        quantiles = payload.get("return_quantiles")
        reasons = payload.get("reason_codes")
        if (
            set(payload) != expected
            or not isinstance(envelope, dict)
            or not isinstance(quantiles, list)
            or not isinstance(reasons, list)
        ):
            raise ValueError("PathForecast fields mismatch")
        return cls(
            envelope=ArtifactEnvelope.from_canonical_dict(envelope),
            symbol=str(payload["symbol"]),
            target_id=TargetId(str(payload["target_id"])),
            forecast_horizon=str(payload["forecast_horizon"]),
            upper_barrier_return=float(payload["upper_barrier_return"]),
            lower_barrier_return=float(payload["lower_barrier_return"]),
            expected_mfe=_optional_float(payload["expected_mfe"]),
            expected_mae=_optional_float(payload["expected_mae"]),
            return_quantiles=tuple(
                ReturnQuantile(
                    probability=float(_object(item)["probability"]),
                    return_value=float(_object(item)["return_value"]),
                )
                for item in quantiles
            ),
            calibration_status=CalibrationStatus(str(payload["calibration_status"])),
            forecast_status=PathForecastStatus(str(payload["forecast_status"])),
            usable_sample_count=int(payload["usable_sample_count"]),
            excluded_sample_count=int(payload["excluded_sample_count"]),
            reason_codes=tuple(str(item) for item in reasons),
        )


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("forecast numeric value is invalid")
    return float(value)


def _object(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("forecast value must be an object")
    return value
