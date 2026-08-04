from dataclasses import FrozenInstanceError, replace
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from market_regime_alpha.core.identity import ArtifactId, DatasetId
from market_regime_alpha.core.status import InputAvailabilityStatus
from market_regime_alpha.features.model_contracts import FeatureComputationRequest
from market_regime_alpha.features.technical.moving_average import (
    MovingAverageConfiguration,
    MovingAverageObservation,
    NormalizedCloseBar,
    SimpleMovingAverageComputer,
)


HASH_A = "sha256:" + "a" * 64
AS_OF = datetime(2026, 8, 4, 7, 0, tzinfo=timezone.utc)
CREATED_AT = datetime(2026, 8, 4, 7, 1, tzinfo=timezone.utc)


def _bars() -> tuple[NormalizedCloseBar, ...]:
    return tuple(
        NormalizedCloseBar(
            symbol="600000.SH",
            market_date=date(2026, 8, day),
            close=close,
            available_at=datetime(2026, 8, day, 7, 0, tzinfo=timezone.utc),
        )
        for day, close in (
            (1, Decimal("10.00")),
            (2, Decimal("11.00")),
            (3, Decimal("12.00")),
        )
    )


def _configuration(window: int = 3) -> MovingAverageConfiguration:
    return MovingAverageConfiguration.create(
        configuration_version="1.0.0",
        window=window,
    )


def _request(
    *,
    bars: tuple[object, ...] | None = None,
    configuration: MovingAverageConfiguration | None = None,
    availability: InputAvailabilityStatus = InputAvailabilityStatus.AVAILABLE,
) -> FeatureComputationRequest:
    selected_configuration = configuration or _configuration()
    return FeatureComputationRequest(
        dataset_id=DatasetId("moving-average-dataset-1"),
        as_of_time=AS_OF,
        created_at=CREATED_AT,
        data_availability=availability,
        configuration_id=selected_configuration.configuration_id,
        configuration_version=selected_configuration.configuration_version,
        configuration_hash=selected_configuration.content_hash,
        input_artifact_ids=(ArtifactId("source-bars-1"),),
        input_hashes=(HASH_A,),
        normalized_data=_bars() if bars is None else bars,
        configuration=selected_configuration,
    )


def test_simple_moving_average_is_decimal_and_marks_warm_up_explicitly() -> None:
    artifact = SimpleMovingAverageComputer().compute(_request())

    assert artifact.score == Decimal("11.00")
    assert artifact.state == "AVAILABLE"
    assert artifact.reason_codes == ("FEATURE_COMPUTED", "WINDOW_NOT_READY")
    assert artifact.configuration_parameters == (("window", "3"),)
    observations = artifact.observations
    assert all(isinstance(item, MovingAverageObservation) for item in observations)
    assert [item.value for item in observations] == [None, None, Decimal("11.00")]
    assert [item.missing_reason for item in observations] == [
        "WINDOW_NOT_READY",
        "WINDOW_NOT_READY",
        None,
    ]
    assert [item.observations_seen for item in observations] == [1, 2, 3]
    assert artifact.artifact_id.value.startswith("feature-artifact-")
    artifact.verify_content_identity()


def test_moving_average_has_no_hidden_wall_clock_or_side_effect_imports(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import builtins

    original_import = builtins.__import__

    def guarded_import(name: str, *args: object, **kwargs: object) -> object:
        lowered = name.lower()
        if "broker" in lowered or "repository" in lowered:
            raise AssertionError(f"feature calculation imported forbidden module: {name}")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    first = SimpleMovingAverageComputer().compute(_request())
    second = SimpleMovingAverageComputer().compute(_request())

    assert first == second
    assert first.to_canonical_dict() == second.to_canonical_dict()


@pytest.mark.parametrize(
    ("bars", "message"),
    [
        (
            tuple(reversed(_bars())),
            "strictly sorted",
        ),
        (
            (_bars()[0], replace(_bars()[1], market_date=_bars()[0].market_date)),
            "duplicate market dates",
        ),
        (
            (_bars()[0], replace(_bars()[1], symbol="600001.SH")),
            "one symbol",
        ),
        (
            (
                _bars()[0],
                replace(
                    _bars()[1],
                    available_at=datetime(2026, 8, 4, 7, 0, 1, tzinfo=timezone.utc),
                ),
            ),
            "after as_of_time",
        ),
        (
            (
                _bars()[0],
                replace(_bars()[1], market_date=date(2026, 8, 5)),
            ),
            "market_date is after as_of_time",
        ),
    ],
)
def test_moving_average_rejects_ambiguous_or_unavailable_bars(
    bars: tuple[NormalizedCloseBar, ...], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        SimpleMovingAverageComputer().compute(_request(bars=bars))


def test_moving_average_rejects_non_bar_input_and_configuration_mismatch() -> None:
    with pytest.raises(TypeError, match="NormalizedCloseBar"):
        SimpleMovingAverageComputer().compute(_request(bars=(object(),)))

    request = _request()
    with pytest.raises(ValueError, match="configuration identity"):
        SimpleMovingAverageComputer().compute(
            replace(request, configuration_id=ArtifactId("wrong-config"))
        )


def test_bar_and_configuration_reject_invalid_decimal_time_and_window() -> None:
    with pytest.raises(ValueError, match="positive"):
        _configuration(window=0)
    with pytest.raises(TypeError, match="integer"):
        MovingAverageConfiguration.create(
            configuration_version="1.0.0",
            window=True,
        )
    with pytest.raises(ValueError, match="finite"):
        replace(_bars()[0], close=Decimal("NaN"))
    with pytest.raises(TypeError, match="Decimal"):
        replace(_bars()[0], close=10.0)
    with pytest.raises(ValueError, match="positive"):
        replace(_bars()[0], close=Decimal("0"))
    with pytest.raises(ValueError, match="timezone-aware"):
        replace(_bars()[0], available_at=datetime(2026, 8, 1, 7, 0))
    with pytest.raises(ValueError, match="whole-second"):
        replace(
            _bars()[0],
            available_at=datetime(2026, 8, 1, 7, 0, 0, 1, tzinfo=timezone.utc),
        )


def test_unavailable_input_is_an_explicit_non_computed_artifact() -> None:
    artifact = SimpleMovingAverageComputer().compute(
        _request(availability=InputAvailabilityStatus.MISSING)
    )

    assert artifact.state == "DATA_UNAVAILABLE"
    assert artifact.score is None
    assert artifact.reason_codes == ("INPUT_DATA_MISSING",)
    assert all(
        item.missing_reason == "INPUT_DATA_MISSING"
        for item in artifact.observations
        if isinstance(item, MovingAverageObservation)
    )


def test_decimal_result_does_not_depend_on_the_process_decimal_context() -> None:
    from decimal import localcontext

    bars = tuple(
        replace(bar, close=close)
        for bar, close in zip(
            _bars(),
            (
                Decimal("1.23456"),
                Decimal("2.34567"),
                Decimal("3.45678"),
            ),
            strict=True,
        )
    )
    with localcontext() as context:
        context.prec = 3
        low_process_precision = SimpleMovingAverageComputer().compute(
            _request(bars=bars)
        )
    with localcontext() as context:
        context.prec = 50
        high_process_precision = SimpleMovingAverageComputer().compute(
            _request(bars=bars)
        )

    assert low_process_precision == high_process_precision
    assert low_process_precision.score == Decimal("2.34567")

def test_moving_average_contracts_are_immutable() -> None:
    with pytest.raises(FrozenInstanceError):
        setattr(_bars()[0], "close", Decimal("99"))
    with pytest.raises(FrozenInstanceError):
        setattr(_configuration(), "window", 99)
