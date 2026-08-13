"""Owner-resolved exploratory challenger over Historical Research Panels.

The challenger deliberately reuses the canonical deterministic regularized-linear
kernel.  It never accepts a caller-supplied matrix: feature and target values are
reloaded from immutable PostgreSQL panel owners for one Historical run.
"""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Iterator
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
    RobustPreprocessingState,
    fit_regularized_continuous_statistics,
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
MAXIMUM_CHALLENGER_SAMPLES = 250_000
CHALLENGER_COMPONENT_BATCH_SIZE = 4


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
    component_batch_size: int
    maximum_feature_buffer_rows: int
    whole_run_sample_graph_materialized: bool = False

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "reason_codes": list(self.reason_codes),
            "source_references": [item.to_canonical_dict() for item in self.source_references],
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
            "missing_feature_contract": ("CANONICAL_ROBUST_PREPROCESSOR_MEDIAN_PLUS_EXPLICIT_MISSING_INDICATOR"),
            "formal_model_qualified": False,
            "formal_oos": False,
            "calibrated": False,
            "aggregation_runtime": {
                "mode": "KEYSET_MULTI_PASS_SUFFICIENT_STATISTICS_V1",
                "component_batch_size": self.component_batch_size,
                "maximum_feature_buffer_rows": self.maximum_feature_buffer_rows,
                "maximum_sample_ceiling": MAXIMUM_CHALLENGER_SAMPLES,
                "whole_run_sample_graph_materialized": self.whole_run_sample_graph_materialized,
            },
        }


class HistoricalExploratoryChallenger:
    """Reload panel owners and fit one fixed, non-promotable challenger."""

    def __init__(self, component_repository: PostgresHistoricalMaterializationRepository) -> None:
        self._components = component_repository

    def train(self, *, run_id: ArtifactId) -> ExploratoryChallengerResult:
        sources = self._components.list_references_for_run(
            run_id=run_id,
            component_kind=HistoricalComponentKind.RESEARCH_PANEL,
        )
        session_bindings: list[dict[str, Any]] = []
        sample_counts: list[int] = []
        excluded = 0
        for _index, panel, samples, panel_excluded in _iter_session_samples(
            self._components,
            run_id=run_id,
        ):
            sample_counts.append(len(samples))
            excluded += panel_excluded
            session_bindings.append(
                {
                    "panel_reference": panel.reference.to_canonical_dict(),
                    "session_key": panel.trading_date.isoformat(),
                    "sample_count": len(samples),
                    "excluded_missing_target_count": panel_excluded,
                    "session_sample_hash": canonical_hash({"samples": list(samples)}),
                }
            )
        total_samples = sum(sample_counts)
        matrix_hash = canonical_hash(
            {
                "schema_version": "historical-challenger-streaming-matrix/v2",
                "feature_names": list(CHALLENGER_FEATURES),
                "target_name": CHALLENGER_TARGET,
                "session_bindings": session_bindings,
                "source_references": [item.to_canonical_dict() for item in sources],
            }
        )
        session_count = len(sample_counts)
        validation_count = max(MIN_VALIDATION_SESSIONS, (session_count + 4) // 5)
        training_count = session_count - validation_count
        training_sample_count = sum(sample_counts[: max(0, training_count)])
        validation_sample_count = sum(sample_counts[max(0, training_count) :])
        if total_samples > MAXIMUM_CHALLENGER_SAMPLES:
            return _not_estimable(
                sources=sources,
                matrix_hash=matrix_hash,
                training_sessions=max(0, training_count),
                validation_sessions=min(session_count, validation_count),
                training_samples=training_sample_count,
                validation_samples=validation_sample_count,
                excluded=excluded,
                reason="DECLARED_CHALLENGER_SAMPLE_CEILING_EXCEEDED",
                maximum_feature_buffer_rows=0,
            )
        if training_count < MIN_TRAINING_SESSIONS or validation_count < MIN_VALIDATION_SESSIONS:
            return _not_estimable(
                sources=sources,
                matrix_hash=matrix_hash,
                training_sessions=max(0, training_count),
                validation_sessions=min(session_count, validation_count),
                training_samples=0,
                validation_samples=0,
                excluded=excluded,
                reason="INSUFFICIENT_TEMPORAL_SESSIONS",
                maximum_feature_buffer_rows=0,
            )
        if training_sample_count < len(CHALLENGER_FEATURES) + 2 or validation_sample_count < 2:
            return _not_estimable(
                sources=sources,
                matrix_hash=matrix_hash,
                training_sessions=training_count,
                validation_sessions=validation_count,
                training_samples=training_sample_count,
                validation_samples=validation_sample_count,
                excluded=excluded,
                reason="INSUFFICIENT_TRAINING_OR_VALIDATION_SAMPLES",
                maximum_feature_buffer_rows=0,
            )
        preprocessing, maximum_feature_buffer_rows = _fit_streaming_preprocessing(
            self._components,
            run_id=run_id,
            training_session_count=training_count,
        )
        normal, rhs, distinct_targets, target_sum = _stream_training_statistics(
            self._components,
            run_id=run_id,
            training_session_count=training_count,
            preprocessing=preprocessing,
        )
        try:
            model = fit_regularized_continuous_statistics(
                preprocessing=preprocessing,
                target_name=CHALLENGER_TARGET,
                normal_matrix=normal,
                rhs=rhs,
                distinct_target_count=distinct_targets,
                penalty=CHALLENGER_PENALTY,
            )
        except ValueError as error:
            return _not_estimable(
                sources=sources,
                matrix_hash=matrix_hash,
                training_sessions=training_count,
                validation_sessions=validation_count,
                training_samples=training_sample_count,
                validation_samples=validation_sample_count,
                excluded=excluded,
                reason=f"CANONICAL_MODEL_NOT_ESTIMABLE:{error}",
                maximum_feature_buffer_rows=maximum_feature_buffer_rows,
            )
        training_mean = target_sum / Decimal(training_sample_count)
        mse, baseline, rank_ic, hit_rate = _stream_validation_metrics(
            self._components,
            run_id=run_id,
            training_session_count=training_count,
            model=model,
            training_mean=training_mean,
        )
        return ExploratoryChallengerResult(
            status="AVAILABLE",
            reason_codes=(
                "EXPLORATORY_TEMPORAL_VALIDATION_ONLY",
                "FIXED_PENALTY_NO_HYPERPARAMETER_SEARCH",
                "OWNER_RESOLVED_TRAINING_MATRIX",
            ),
            source_references=sources,
            matrix_hash=matrix_hash,
            training_session_count=training_count,
            validation_session_count=validation_count,
            training_sample_count=training_sample_count,
            validation_sample_count=validation_sample_count,
            excluded_missing_target_count=excluded,
            validation_mse=mse,
            baseline_mse=baseline,
            validation_rank_ic=rank_ic,
            validation_hit_rate=hit_rate,
            model=model,
            component_batch_size=CHALLENGER_COMPONENT_BATCH_SIZE,
            maximum_feature_buffer_rows=maximum_feature_buffer_rows,
        )


def _panel_samples(
    panel: HistoricalSessionComponent,
) -> tuple[tuple[Mapping[str, Any], ...], int]:
    samples: list[Mapping[str, Any]] = []
    excluded = 0
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
                "features": {name: _text(_optional_decimal(factors[name])) for name in CHALLENGER_FEATURES},
                "target": str(target),
            }
        )
    return tuple(samples), excluded


def _iter_session_samples(
    repository: PostgresHistoricalMaterializationRepository,
    *,
    run_id: ArtifactId,
) -> Iterator[
    tuple[
        int,
        HistoricalSessionComponent,
        tuple[Mapping[str, Any], ...],
        int,
    ]
]:
    index = 0
    for batch in repository.iter_for_run(
        run_id=run_id,
        component_kind=HistoricalComponentKind.RESEARCH_PANEL,
        batch_size=CHALLENGER_COMPONENT_BATCH_SIZE,
    ):
        for panel in batch:
            samples, excluded = _panel_samples(panel)
            yield index, panel, samples, excluded
            index += 1


def _fit_streaming_preprocessing(
    repository: PostgresHistoricalMaterializationRepository,
    *,
    run_id: ArtifactId,
    training_session_count: int,
) -> tuple[RobustPreprocessingState, int]:
    medians: list[Decimal] = []
    scales: list[Decimal] = []
    maximum_buffer = 0
    for feature in CHALLENGER_FEATURES:
        values: list[Decimal] = []
        for index, _panel, samples, _excluded in _iter_session_samples(repository, run_id=run_id):
            if index >= training_session_count:
                break
            for sample in samples:
                value = _feature_row(sample)[feature]
                if value is not None:
                    values.append(value)
        if len(values) > MAXIMUM_CHALLENGER_SAMPLES:
            raise ValueError("Challenger feature buffer exceeds declared ceiling")
        maximum_buffer = max(maximum_buffer, len(values))
        values.sort()
        if not values:
            medians.append(Decimal("0"))
            scales.append(Decimal("1"))
            continue
        median = _quantile(values, Decimal("0.5"))
        scale = _quantile(values, Decimal("0.75")) - _quantile(values, Decimal("0.25"))
        medians.append(median)
        scales.append(Decimal("1") if scale == 0 else scale)
    return (
        RobustPreprocessingState(
            feature_names=CHALLENGER_FEATURES,
            medians=tuple(medians),
            scales=tuple(scales),
        ),
        maximum_buffer,
    )


def _stream_training_statistics(
    repository: PostgresHistoricalMaterializationRepository,
    *,
    run_id: ArtifactId,
    training_session_count: int,
    preprocessing: RobustPreprocessingState,
) -> tuple[
    tuple[tuple[Decimal, ...], ...],
    tuple[Decimal, ...],
    int,
    Decimal,
]:
    width = len(preprocessing.transformed_feature_names) + 1
    normal = [[Decimal("0") for _ in range(width)] for _ in range(width)]
    rhs = [Decimal("0") for _ in range(width)]
    first_target: Decimal | None = None
    target_varies = False
    target_sum = Decimal("0")
    for index, _panel, samples, _excluded in _iter_session_samples(repository, run_id=run_id):
        if index >= training_session_count:
            break
        for sample in samples:
            target = Decimal(str(sample["target"]))
            target_sum += target
            if first_target is None:
                first_target = target
            elif target != first_target:
                target_varies = True
            design = (
                Decimal("1"),
                *preprocessing.transform(_feature_row(sample)),
            )
            for left in range(width):
                rhs[left] += design[left] * target
                for right in range(left, width):
                    normal[left][right] += design[left] * design[right]
    for left in range(width):
        for right in range(left):
            normal[left][right] = normal[right][left]
    return (
        tuple(tuple(row) for row in normal),
        tuple(rhs),
        2 if target_varies else (1 if first_target is not None else 0),
        target_sum,
    )


def _stream_validation_metrics(
    repository: PostgresHistoricalMaterializationRepository,
    *,
    run_id: ArtifactId,
    training_session_count: int,
    model: RegularizedMultiTargetModel,
    training_mean: Decimal,
) -> tuple[Decimal, Decimal, Decimal | None, Decimal]:
    squared_error = Decimal("0")
    baseline_error = Decimal("0")
    hit_count = 0
    sample_count = 0
    session_rank_ics: list[Decimal] = []
    for index, _panel, samples, _excluded in _iter_session_samples(repository, run_id=run_id):
        if index < training_session_count:
            continue
        predictions: list[Decimal] = []
        targets: list[Decimal] = []
        for sample in samples:
            prediction = model.predict(_feature_row(sample)).continuous[CHALLENGER_TARGET]
            target = Decimal(str(sample["target"]))
            predictions.append(prediction)
            targets.append(target)
            squared_error += (prediction - target) ** 2
            baseline_error += (training_mean - target) ** 2
            hit_count += (prediction >= 0) == (target >= 0)
            sample_count += 1
        rank_ic = _rank_correlation(predictions, targets)
        if rank_ic is not None:
            session_rank_ics.append(rank_ic)
    if sample_count == 0:
        raise ValueError("Challenger validation stream is empty")
    return (
        squared_error / Decimal(sample_count),
        baseline_error / Decimal(sample_count),
        None if not session_rank_ics else _mean(session_rank_ics),
        Decimal(hit_count) / Decimal(sample_count),
    )


def _feature_row(sample: Mapping[str, Any]) -> Mapping[str, Decimal | None]:
    raw = sample["features"]
    if not isinstance(raw, Mapping):
        raise ValueError("Challenger sample features must be an object")
    return {name: _optional_decimal(raw[name]) for name in CHALLENGER_FEATURES}


def _rank_correlation(left: list[Decimal], right: list[Decimal]) -> Decimal | None:
    if len(left) < 2 or len(left) != len(right):
        return None
    left_rank = _ranks(left)
    right_rank = _ranks(right)
    left_mean = fmean(left_rank)
    right_mean = fmean(right_rank)
    numerator = sum((a - left_mean) * (b - right_mean) for a, b in zip(left_rank, right_rank, strict=True))
    denominator = sqrt(sum((item - left_mean) ** 2 for item in left_rank) * sum((item - right_mean) ** 2 for item in right_rank))
    return None if denominator == 0 else Decimal(str(numerator / denominator))


def _quantile(values: list[Decimal], probability: Decimal) -> Decimal:
    if len(values) == 1:
        return values[0]
    position = probability * Decimal(len(values) - 1)
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    fraction = position - Decimal(lower)
    return values[lower] * (Decimal("1") - fraction) + values[upper] * fraction


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
    maximum_feature_buffer_rows: int,
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
        component_batch_size=CHALLENGER_COMPONENT_BATCH_SIZE,
        maximum_feature_buffer_rows=maximum_feature_buffer_rows,
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
