from __future__ import annotations

from decimal import Decimal

from market_regime_alpha.application.research_evaluation.targets import (
    engineering_multi_horizon_protocol,
)
from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.application.research_validation.forecast_measure_kernel import (
    compute_regularized_measure_forecast,
)
from market_regime_alpha.application.research_validation.formal_protocol import (
    ForecastMeasureKind,
    ForecastMeasureStatus,
)
from market_regime_alpha.application.research_validation.research_model import (
    ResearchMeasureBinding,
    ResearchModelHeadKind,
)
from market_regime_alpha.forecasting.regularized_linear import (
    TrainingMatrix,
    fit_regularized_multi_target,
)


def test_kernel_is_deterministic_measure_oriented_and_has_no_pit_gate() -> None:
    target_protocol = engineering_multi_horizon_protocol()
    target = target_protocol.targets[0]
    target_reference = ValidationArtifactReference(
        "OUTCOME_TARGET", target.target_id, target.target_hash
    )
    matrix = TrainingMatrix.create(
        feature_names=("price_momentum", "volume_expansion"),
        rows=tuple(
            {
                "price_momentum": Decimal(index),
                "volume_expansion": Decimal(index % 3),
            }
            for index in range(1, 9)
        ),
        continuous_targets={
            "return": tuple(Decimal(index) / Decimal("100") for index in range(1, 9))
        },
        barrier_targets={
            "direction": tuple(index > 4 for index in range(1, 9))
        },
    )
    model = fit_regularized_multi_target(matrix, penalty=Decimal("1"))
    bindings = tuple(
        sorted(
            (
                ResearchMeasureBinding(
                    "return",
                    target_reference,
                    ForecastMeasureKind.EXPECTED_RETURN,
                    ResearchModelHeadKind.CONTINUOUS_EXPECTATION,
                ),
                ResearchMeasureBinding(
                    "direction",
                    target_reference,
                    ForecastMeasureKind.RETURN_POSITIVE_RAW_LOGIT,
                    ResearchModelHeadKind.LOGISTIC_RAW_LOGIT,
                ),
            ),
            key=lambda item: item.key,
        )
    )
    inputs = {
        "price_momentum": Decimal("5"),
        "volume_expansion": Decimal("2"),
    }

    first = compute_regularized_measure_forecast(
        model=model,
        bindings=bindings,
        target_protocol=target_protocol,
        feature_values=inputs,
    )
    second = compute_regularized_measure_forecast(
        model=model,
        bindings=bindings,
        target_protocol=target_protocol,
        feature_values=inputs,
    )

    assert first == second
    predicted = first[0]
    assert predicted.measure(ForecastMeasureKind.EXPECTED_RETURN).status is ForecastMeasureStatus.AVAILABLE
    assert predicted.measure(ForecastMeasureKind.RETURN_POSITIVE_RAW_LOGIT).status is ForecastMeasureStatus.AVAILABLE
    assert predicted.measure(ForecastMeasureKind.RETURN_POSITIVE_PROBABILITY).status is ForecastMeasureStatus.NOT_ESTIMABLE
    assert predicted.measure(ForecastMeasureKind.RETURN_POSITIVE_PROBABILITY).reason_codes == (
        "CALIBRATION_ARTIFACT_MISSING",
    )
    assert all(
        item.status is ForecastMeasureStatus.NOT_ESTIMABLE
        for estimate in first[1:]
        for item in estimate.measures
    )
