"""Owner-resolved exploratory challenger over Historical Research Panels.

The challenger deliberately reuses the canonical deterministic regularized-linear
kernel.  It never accepts a caller-supplied matrix: feature and target values are
reloaded from immutable PostgreSQL panel owners for one Historical run.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from math import sqrt
from statistics import fmean
from typing import Any, Mapping

from market_regime_alpha.application.historical_corpus.materialization_contracts import (
    HistoricalComponentKind,
    HistoricalSessionComponent,
)
from market_regime_alpha.application.historical_corpus.postgres_materialization import (
    PostgresHistoricalMaterializationRepository,
)
from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.forecasting.regularized_linear import (
    RegularizedMultiTargetModel,
    TrainingMatrix,
    fit_regularized_multi_target,
)


CHALLENGER_FEATURES = (
    "candidate",
    "capital",
    "dynamic_pool",
    "etf",
    "forecast",
    "market_regime",
    "price",
    "signal",
    "theme",
    "volume",
)
CHALLENGER_TARGET = "t_plus_one_1030_return"
CHALLENGER_PENALTY = Decimal("1")
MIN_TRAINING_SESSIONS = 20
MIN_VALIDATION_SESSIONS = 5


@dataclass(frozen=True, slots=True)
class ExploratoryChallengerResult:
    status: str
    reason_codes: tuple[str, ...]
    source_references: tuple[ValidationArtifactReference, ...]
    matrix_hash: str
    training_session_count: int
    validation_session_count: int
    training_sample_count: int
    validation_sample_count: int
    excluded_missing_target_count: int
    validation_mse: Decimal | None
    baseline_mse: Decimal | None
    validation_rank_ic: Decimal | None
    validation_hit_rate: Decimal | None
    model: RegularizedMultiTargetModel | None

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "reason_codes": list(self.reason_codes),
            "source_references": [
                item.to_canonical_dict() for item in self.source_references
            ],
            "matrix_hash": self.matrix_hash,
            "feature_names": list(CHALLENGER_FEATURES),
            "target_name": CHALLENGER_TARGET,
            "penalty": str(CHALLENGER_PENALTY),
            "training_session_count": self.training_session_count,
            "validation_session_count": self.validation_session_count,
            "training_sample_count": self.training_sample_count,
            "validation_sample_count": self.validation_sample_count,
            "excluded_missing_target_count": self.excluded_missing_target_count,
            "validation_mse": _text(self.validation_mse),
            "baseline_mse": _text(self.baseline_mse),
            "validation_rank_ic": _text(self.validation_rank_ic),
            "validation_hit_rate": _text(self.validation_hit_rate),
            "model": None if self.model is None else self.model.to_canonical_dict(),
            "owner_resolved_training_matrix": True,
            "missing_feature_contract": (
                "CANONICAL_ROBUST_PREPROCESSOR_MEDIAN_PLUS_EXPLICIT_MISSING_INDICATOR"
            ),
            "formal_model_qualified": False,
            "formal_oos": False,
            "calibrated": False,
        }


class HistoricalExploratoryChallenger:
    """Reload panel owners and fit one fixed, non-promotable challenger."""

    def __init__(
        self, component_repository: PostgresHistoricalMaterializationRepository
    ) -> None:
        self._components = component_repository

    def train(self, *, run_id: ArtifactId) -> ExploratoryChallengerResult:
        panels = self._components.list_for_run(
            run_id=run_id,
            component_kind=HistoricalComponentKind.RESEARCH_PANEL,
        )
        sources = tuple(item.reference for item in panels)
        samples, excluded = _samples(panels)
        matrix_hash = canonical_hash(
            {
                "feature_names": list(CHALLENGER_FEATURES),
                "target_name": CHALLENGER_TARGET,
                "samples": samples,
                "source_references": [item.to_canonical_dict() for item in sources],
            }
        )
        sessions = tuple(sorted({str(item["session_key"]) for item in samples}))
        validation_count = max(MIN_VALIDATION_SESSIONS, (len(sessions) + 4) // 5)
        training_count = len(sessions) - validation_count
        if training_count < MIN_TRAINING_SESSIONS or validation_count < MIN_VALIDATION_SESSIONS:
            return _not_estimable(
                sources=sources,
                matrix_hash=matrix_hash,
                training_sessions=max(0, training_count),
                validation_sessions=min(len(sessions), validation_count),
                training_samples=0,
                validation_samples=0,
                excluded=excluded,
                reason="INSUFFICIENT_TEMPORAL_SESSIONS",
            )
        training_sessions = set(sessions[:training_count])
        validation_sessions = set(sessions[training_count:])
        training = tuple(
            item for item in samples if str(item["session_key"]) in training_sessions
        )
        validation = tuple(
            item for item in samples if str(item["session_key"]) in validation_sessions
        )
        if len(training) < len(CHALLENGER_FEATURES) + 2 or len(validation) < 2:
            return _not_estimable(
                sources=sources,
                matrix_hash=matrix_hash,
                training_sessions=len(training_sessions),
                validation_sessions=len(validation_sessions),
                training_samples=len(training),
                validation_samples=len(validation),
                excluded=excluded,
                reason="INSUFFICIENT_TRAINING_OR_VALIDATION_SAMPLES",
            )
        try:
            model = fit_regularized_multi_target(
                _matrix(training), penalty=CHALLENGER_PENALTY
            )
        except ValueError as error:
            return _not_estimable(
                sources=sources,
                matrix_hash=matrix_hash,
                training_sessions=len(training_sessions),
                validation_sessions=len(validation_sessions),
                training_samples=len(training),
                validation_samples=len(validation),
                excluded=excluded,
                reason=f"CANONICAL_MODEL_NOT_ESTIMABLE:{error}",
            )
        predictions = tuple(
            model.predict(_feature_row(item)).continuous[CHALLENGER_TARGET]
            for item in validation
        )
        targets = tuple(Decimal(str(item["target"])) for item in validation)
        training_mean = sum(
            (Decimal(str(item["target"])) for item in training), Decimal("0")
        ) / Decimal(len(training))
        mse = _mean((left - right) ** 2 for left, right in zip(predictions, targets, strict=True))
        baseline = _mean((training_mean - item) ** 2 for item in targets)
        rank_ic = _session_rank_ic(validation, predictions, targets)
        hit_rate = Decimal(
            sum((left >= 0) == (right >= 0) for left, right in zip(predictions, targets, strict=True))
        ) / Decimal(len(targets))
        return ExploratoryChallengerResult(
            status="AVAILABLE",
            reason_codes=(
                "EXPLORATORY_TEMPORAL_VALIDATION_ONLY",
                "FIXED_PENALTY_NO_HYPERPARAMETER_SEARCH",
                "OWNER_RESOLVED_TRAINING_MATRIX",
            ),
            source_references=sources,
            matrix_hash=matrix_hash,
            training_session_count=len(training_sessions),
            validation_session_count=len(validation_sessions),
            training_sample_count=len(training),
            validation_sample_count=len(validation),
            excluded_missing_target_count=excluded,
            validation_mse=mse,
            baseline_mse=baseline,
            validation_rank_ic=rank_ic,
            validation_hit_rate=hit_rate,
            model=model,
        )


def _samples(
    panels: tuple[HistoricalSessionComponent, ...],
) -> tuple[tuple[Mapping[str, Any], ...], int]:
    samples: list[Mapping[str, Any]] = []
    excluded = 0
    for panel in sorted(panels, key=lambda item: (item.trading_date, str(item.component_id))):
        raw_rows = panel.payload.get("rows")
        if not isinstance(raw_rows, list):
            raise ValueError("Historical Research Panel rows must be an array")
        for raw in raw_rows:
            if not isinstance(raw, Mapping):
                raise ValueError("Historical Research Panel row must be an object")
            target = _optional_decimal(raw.get("target_return"))
            if target is None:
                excluded += 1
                continue
            factors = raw.get("factor_values")
            if not isinstance(factors, Mapping):
                raise ValueError("Historical Research Panel factors must be an object")
            if set(factors) != set(CHALLENGER_FEATURES):
                raise ValueError("Historical Research Panel feature projection drifted")
            samples.append(
                {
                    "sample_key": f"{panel.component_id}:{raw.get('symbol')}",
                    "session_key": panel.trading_date.isoformat(),
                    "symbol": str(raw.get("symbol")),
                    "features": {
                        name: _text(_optional_decimal(factors[name]))
                        for name in CHALLENGER_FEATURES
                    },
                    "target": str(target),
                }
            )
    return tuple(samples), excluded


def _matrix(samples: tuple[Mapping[str, Any], ...]) -> TrainingMatrix:
    return TrainingMatrix.create(
        feature_names=CHALLENGER_FEATURES,
        rows=tuple(_feature_row(item) for item in samples),
        continuous_targets={
            CHALLENGER_TARGET: tuple(Decimal(str(item["target"])) for item in samples)
        },
        barrier_targets={},
    )


def _feature_row(sample: Mapping[str, Any]) -> Mapping[str, Decimal | None]:
    raw = sample["features"]
    if not isinstance(raw, Mapping):
        raise ValueError("Challenger sample features must be an object")
    return {name: _optional_decimal(raw[name]) for name in CHALLENGER_FEATURES}


def _session_rank_ic(
    samples: tuple[Mapping[str, Any], ...],
    predictions: tuple[Decimal, ...],
    targets: tuple[Decimal, ...],
) -> Decimal | None:
    grouped: dict[str, tuple[list[Decimal], list[Decimal]]] = {}
    for sample, prediction, target in zip(samples, predictions, targets, strict=True):
        left, right = grouped.setdefault(str(sample["session_key"]), ([], []))
        left.append(prediction)
        right.append(target)
    values = tuple(
        value
        for left, right in grouped.values()
        if (value := _rank_correlation(left, right)) is not None
    )
    return None if not values else _mean(values)


def _rank_correlation(left: list[Decimal], right: list[Decimal]) -> Decimal | None:
    if len(left) < 2 or len(left) != len(right):
        return None
    left_rank = _ranks(left)
    right_rank = _ranks(right)
    left_mean = fmean(left_rank)
    right_mean = fmean(right_rank)
    numerator = sum(
        (a - left_mean) * (b - right_mean)
        for a, b in zip(left_rank, right_rank, strict=True)
    )
    denominator = sqrt(
        sum((item - left_mean) ** 2 for item in left_rank)
        * sum((item - right_mean) ** 2 for item in right_rank)
    )
    return None if denominator == 0 else Decimal(str(numerator / denominator))


def _ranks(values: list[Decimal]) -> list[float]:
    ordered = sorted(enumerate(values), key=lambda item: (item[1], item[0]))
    result = [0.0] * len(values)
    index = 0
    while index < len(ordered):
        end = index + 1
        while end < len(ordered) and ordered[end][1] == ordered[index][1]:
            end += 1
        rank = (index + 1 + end) / 2
        for original, _value in ordered[index:end]:
            result[original] = rank
        index = end
    return result


def _not_estimable(
    *,
    sources: tuple[ValidationArtifactReference, ...],
    matrix_hash: str,
    training_sessions: int,
    validation_sessions: int,
    training_samples: int,
    validation_samples: int,
    excluded: int,
    reason: str,
) -> ExploratoryChallengerResult:
    return ExploratoryChallengerResult(
        status="NOT_ESTIMABLE",
        reason_codes=(reason,),
        source_references=sources,
        matrix_hash=matrix_hash,
        training_session_count=training_sessions,
        validation_session_count=validation_sessions,
        training_sample_count=training_samples,
        validation_sample_count=validation_samples,
        excluded_missing_target_count=excluded,
        validation_mse=None,
        baseline_mse=None,
        validation_rank_ic=None,
        validation_hit_rate=None,
        model=None,
    )


def _mean(values: Any) -> Decimal:
    result = tuple(values)
    return sum(result, Decimal("0")) / Decimal(len(result))


def _optional_decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    result = Decimal(str(value))
    if not result.is_finite():
        raise ValueError("Challenger values must be finite")
    return result


def _text(value: Decimal | None) -> str | None:
    return None if value is None else str(value)


__all__ = [
    "CHALLENGER_FEATURES",
    "CHALLENGER_PENALTY",
    "CHALLENGER_TARGET",
    "ExploratoryChallengerResult",
    "HistoricalExploratoryChallenger",
]
