"""Pure deterministic forecast computation below every qualification gate."""

from __future__ import annotations

from market_regime_alpha.application.research_evaluation.targets import (
    OutcomeTargetProtocol,
)
from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.application.research_validation.formal_protocol import (
    ForecastMeasureEstimate,
    ForecastMeasureKind,
    ForecastMeasureStatus,
    OutcomeTargetForecastEstimate,
    not_estimable_target_forecast,
)
from market_regime_alpha.application.research_validation.research_model import (
    ResearchMeasureBinding,
    ResearchModelHeadKind,
)
from market_regime_alpha.forecasting.regularized_linear import (
    FeatureRow,
    RegularizedMultiTargetModel,
)


def compute_regularized_measure_forecast(
    *,
    model: RegularizedMultiTargetModel,
    bindings: tuple[ResearchMeasureBinding, ...],
    target_protocol: OutcomeTargetProtocol,
    feature_values: FeatureRow,
) -> tuple[OutcomeTargetForecastEstimate, ...]:
    """Execute the model without making PIT, Formal, OOS or Calibration claims."""

    if bindings != tuple(sorted(bindings, key=lambda item: item.key)):
        raise ValueError("Forecast measure bindings must be sorted")
    prediction = model.predict(feature_values)
    targets = {
        ValidationArtifactReference("OUTCOME_TARGET", item.target_id, item.target_hash): item
        for item in target_protocol.targets
    }
    if any(item.target_reference not in targets for item in bindings):
        raise ValueError("Forecast binding is outside the frozen Target Protocol")
    continuous_heads = {item.target_name for item in model.continuous_heads}
    logistic_heads = {item.target_name for item in model.barrier_heads}
    if {
        item.training_target_name
        for item in bindings
        if item.head_kind is ResearchModelHeadKind.CONTINUOUS_EXPECTATION
    } != continuous_heads:
        raise ValueError("Continuous model heads diverged from frozen measure bindings")
    if {
        item.training_target_name
        for item in bindings
        if item.head_kind is ResearchModelHeadKind.LOGISTIC_RAW_LOGIT
    } != logistic_heads:
        raise ValueError("Logistic model heads diverged from frozen measure bindings")

    bindings_by_target: dict[ValidationArtifactReference, list[ResearchMeasureBinding]] = {}
    for binding in bindings:
        bindings_by_target.setdefault(binding.target_reference, []).append(binding)

    estimates = []
    for reference, target in sorted(targets.items(), key=lambda item: str(item[0].artifact_id)):
        base = not_estimable_target_forecast(
            target_id=target.target_id,
            target_hash=target.target_hash,
            barrier_ids=tuple(item.barrier_id for item in target.barriers),
            reason_codes=("MEASURE_NOT_IN_FROZEN_MODEL_PLAN",),
        )
        measures = {item.key: item for item in base.measures}
        for binding in bindings_by_target.get(reference, []):
            value = (
                prediction.continuous[binding.training_target_name]
                if binding.head_kind is ResearchModelHeadKind.CONTINUOUS_EXPECTATION
                else prediction.raw_barrier_logits[binding.training_target_name]
            )
            try:
                measure = ForecastMeasureEstimate(
                    binding.measure_kind,
                    ForecastMeasureStatus.AVAILABLE,
                    value,
                    barrier_id=binding.barrier_id,
                )
            except ValueError:
                measure = ForecastMeasureEstimate(
                    binding.measure_kind,
                    ForecastMeasureStatus.NOT_ESTIMABLE,
                    None,
                    ("MODEL_OUTPUT_OUTSIDE_MEASURE_DOMAIN",),
                    barrier_id=binding.barrier_id,
                )
            measures[measure.key] = measure

        for probability_kind in (
            ForecastMeasureKind.RETURN_POSITIVE_PROBABILITY,
            ForecastMeasureKind.UPPER_BEFORE_LOWER_PROBABILITY,
        ):
            key = (probability_kind.value, "")
            measures[key] = ForecastMeasureEstimate(
                probability_kind,
                ForecastMeasureStatus.NOT_ESTIMABLE,
                None,
                ("CALIBRATION_ARTIFACT_MISSING",),
            )
        ordered = tuple(sorted(measures.values(), key=lambda item: item.key))
        target_reasons = (
            ()
            if any(item.status is ForecastMeasureStatus.AVAILABLE for item in ordered)
            else tuple(
                sorted(
                    {
                        reason
                        for item in ordered
                        for reason in item.reason_codes
                    }
                )
            )
        )
        estimates.append(
            OutcomeTargetForecastEstimate(
                target_id=target.target_id,
                target_hash=target.target_hash,
                measures=ordered,
                reason_codes=target_reasons,
            )
        )
    return tuple(estimates)


__all__ = ["compute_regularized_measure_forecast"]
