"""Canonical Candidate Discovery contracts.

Candidate Discovery produces predictions or rankings, not trade actions. Candidate
Population construction requires explicit PIT universe membership and trading eligibility.
"""

from __future__ import annotations

from dataclasses import dataclass
import math

from market_regime_alpha.core.identity import DatasetId, ExperimentId, ModelId, TargetId, UniverseId
from market_regime_alpha.core.time import DecisionTime, SemanticTime
from market_regime_alpha.universe.contracts import (
    PITUniverseSnapshot,
    TradingEligibilitySnapshot,
    TradingEligibilityStatus,
)


def _require_non_empty(label: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f"{label} must be a non-empty trimmed string")


def _require_finite(label: str, value: float | None) -> None:
    if value is not None and not math.isfinite(float(value)):
        raise ValueError(f"{label} must be finite when present")


@dataclass(frozen=True, slots=True)
class CandidateExpiryTime(SemanticTime):
    """Time after which a Candidate Prediction must not be treated as current."""


@dataclass(frozen=True, slots=True)
class TargetContract:
    """Versioned definition of the future outcome studied by Candidate Discovery."""

    target_id: TargetId
    name: str
    horizon: str
    outcome: str
    price_convention: str
    decision_time_convention: str
    population_scope: str
    version: str

    def __post_init__(self) -> None:
        for label in (
            "name",
            "horizon",
            "outcome",
            "price_convention",
            "decision_time_convention",
            "population_scope",
            "version",
        ):
            _require_non_empty(label, getattr(self, label))


@dataclass(frozen=True, slots=True)
class CandidatePopulation:
    """Complete eligible opportunity set for one Candidate decision time.

    An empty population is valid and means the declared membership/eligibility process
    produced no eligible instruments. It must not be converted into a system error or a
    fabricated fallback population.
    """

    universe_id: UniverseId
    decision_time: DecisionTime
    symbols: tuple[str, ...]
    source_dataset_ids: tuple[DatasetId, ...]

    def __post_init__(self) -> None:
        if len(self.symbols) != len(set(self.symbols)):
            raise ValueError("candidate population symbols must be unique")
        if tuple(sorted(self.symbols)) != self.symbols:
            raise ValueError("candidate population symbols must be sorted")
        if not self.source_dataset_ids:
            raise ValueError("candidate population requires source dataset ids")
        if len(self.source_dataset_ids) != len(set(self.source_dataset_ids)):
            raise ValueError("source_dataset_ids must be unique")


def build_candidate_population(
    universe: PITUniverseSnapshot,
    eligibility: TradingEligibilitySnapshot,
    *,
    decision_time: DecisionTime,
) -> CandidatePopulation:
    """Intersect PIT universe membership with explicit trading eligibility."""

    if universe.as_of.value > decision_time.value:
        raise ValueError("universe snapshot must not be from the future")
    if eligibility.as_of.value > decision_time.value:
        raise ValueError("trading eligibility snapshot must not be from the future")
    symbols = tuple(
        sorted(
            symbol
            for symbol in universe.member_symbols
            if eligibility.status_for(symbol) is TradingEligibilityStatus.ELIGIBLE
        )
    )
    source_dataset_ids = tuple(
        dict.fromkeys((universe.source_dataset_id, eligibility.source_dataset_id))
    )
    return CandidatePopulation(
        universe_id=universe.universe_id,
        decision_time=decision_time,
        symbols=symbols,
        source_dataset_ids=source_dataset_ids,
    )


@dataclass(frozen=True, slots=True)
class CandidatePrediction:
    """Prediction/ranking evidence for one Candidate Instrument.

    The contract intentionally contains no ENTER/ADD/HOLD/REDUCE/ROTATE/EXIT action.
    ``model_score`` remains a score. ``calibrated_probability`` is optional and may be
    populated only by a model with probability semantics and calibration evidence.
    """

    symbol: str
    universe_id: UniverseId
    model_id: ModelId
    target_id: TargetId
    decision_time: DecisionTime
    experiment_id: ExperimentId
    population_size: int | None = None
    model_score: float | None = None
    rank: int | None = None
    percentile: float | None = None
    calibrated_probability: float | None = None
    expected_return: float | None = None
    expected_mfe: float | None = None
    expected_mae: float | None = None
    uncertainty: float | None = None
    expires_at: CandidateExpiryTime | None = None

    def __post_init__(self) -> None:
        _require_non_empty("symbol", self.symbol)
        if all(
            value is None
            for value in (
                self.model_score,
                self.calibrated_probability,
                self.expected_return,
                self.expected_mfe,
                self.expected_mae,
            )
        ):
            raise ValueError("candidate prediction requires at least one prediction output")
        for label, value in (
            ("model_score", self.model_score),
            ("percentile", self.percentile),
            ("calibrated_probability", self.calibrated_probability),
            ("expected_return", self.expected_return),
            ("expected_mfe", self.expected_mfe),
            ("expected_mae", self.expected_mae),
            ("uncertainty", self.uncertainty),
        ):
            _require_finite(label, value)
        if self.population_size is not None and self.population_size <= 0:
            raise ValueError("population_size must be positive")
        if self.rank is not None and self.rank <= 0:
            raise ValueError("rank must be positive")
        if self.population_size is not None and self.rank is not None and self.rank > self.population_size:
            raise ValueError("rank must not exceed population_size")
        if self.percentile is not None and not 0.0 <= self.percentile <= 1.0:
            raise ValueError("percentile must be in [0, 1]")
        if self.calibrated_probability is not None and not 0.0 <= self.calibrated_probability <= 1.0:
            raise ValueError("calibrated_probability must be in [0, 1]")
        if self.uncertainty is not None and self.uncertainty < 0.0:
            raise ValueError("uncertainty must be non-negative")
        if self.expires_at is not None and self.expires_at.value <= self.decision_time.value:
            raise ValueError("expires_at must be after decision_time")
