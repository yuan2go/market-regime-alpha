"""Read-only B0/B1 factor adapter that preserves existing PredictionRun semantics."""

from __future__ import annotations

from dataclasses import dataclass

from market_regime_alpha.core.identity import (
    ArtifactId,
    FeatureDefinitionId,
)
from market_regime_alpha.platform.candidate_prediction_adapter import (
    B0_MOMENTUM_MODEL_ID,
    B1_BALANCED_MODEL_ID,
)
from market_regime_alpha.platform.prediction_run import PredictionRun


@dataclass(frozen=True, slots=True)
class LegacyCandidateFactors:
    symbol: str
    b0_momentum_percentile: float | None
    b1_balanced_percentile: float | None
    source_feature_ids: tuple[FeatureDefinitionId, ...]
    prediction_run_ids: tuple[ArtifactId, ArtifactId]
    reason_codes: tuple[str, ...]


def adapt_b0_b1_candidate_factors(
    runs: tuple[PredictionRun, ...],
) -> dict[str, LegacyCandidateFactors]:
    by_model = {run.model_id: run for run in runs}
    if set(by_model) != {B0_MOMENTUM_MODEL_ID, B1_BALANCED_MODEL_ID}:
        raise ValueError("Candidate Discovery V2 requires exact frozen B0/B1 PredictionRuns")
    b0 = by_model[B0_MOMENTUM_MODEL_ID]
    b1 = by_model[B1_BALANCED_MODEL_ID]
    if (
        b0.decision_time != b1.decision_time
        or b0.dataset_id != b1.dataset_id
        or b0.universe_id != b1.universe_id
        or b0.target_id != b1.target_id
        or b0.population_size != b1.population_size
    ):
        raise ValueError("B0/B1 PredictionRun scope mismatch")
    b0_predictions = {item.symbol: item for item in b0.predictions}
    b1_predictions = {item.symbol: item for item in b1.predictions}
    b0_rejections = {item.symbol: item.reason_code for item in b0.rejections}
    b1_rejections = {item.symbol: item.reason_code for item in b1.rejections}
    symbols = tuple(
        sorted(
            {
                *b0_predictions,
                *b1_predictions,
                *b0_rejections,
                *b1_rejections,
            }
        )
    )
    if len(symbols) != b0.population_size:
        raise ValueError("B0/B1 population reconciliation mismatch")
    result: dict[str, LegacyCandidateFactors] = {}
    for symbol in symbols:
        b0_prediction = b0_predictions.get(symbol)
        b1_prediction = b1_predictions.get(symbol)
        reasons = tuple(
            value
            for value in (
                (
                    f"B0_REJECTED:{b0_rejections[symbol]}"
                    if symbol in b0_rejections
                    else None
                ),
                (
                    f"B1_REJECTED:{b1_rejections[symbol]}"
                    if symbol in b1_rejections
                    else None
                ),
            )
            if value is not None
        )
        result[symbol] = LegacyCandidateFactors(
            symbol=symbol,
            b0_momentum_percentile=(
                b0_prediction.percentile
                if b0_prediction is not None
                else None
            ),
            b1_balanced_percentile=(
                b1_prediction.percentile
                if b1_prediction is not None
                else None
            ),
            source_feature_ids=tuple(
                dict.fromkeys(
                    (*b0.feature_definition_ids, *b1.feature_definition_ids)
                )
            ),
            prediction_run_ids=(
                b0.prediction_run_id,
                b1.prediction_run_id,
            ),
            reason_codes=reasons,
        )
    return result

