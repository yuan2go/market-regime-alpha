from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.application.research_validation.path_calibration import (
    CalibrationPartitionPolicy,
    _ResolvedCalibrationObservation,
    _partition_observations,
)
from market_regime_alpha.application.research_validation.calibration import (
    CalibrationPartition,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash


def _reference(kind: str, name: str) -> ValidationArtifactReference:
    return ValidationArtifactReference(
        kind,
        ArtifactId(name),
        canonical_hash({"name": name}),
    )


def _observation(trading_date: date, index: int) -> _ResolvedCalibrationObservation:
    return _ResolvedCalibrationObservation(
        trading_date=trading_date,
        label_end_date=trading_date + timedelta(days=1),
        label_reference=_reference("TARGET_OUTCOME_LABEL", f"label-{index}"),
        target_reference=_reference("OUTCOME_TARGET", "target"),
        barrier_id="UP_1_PERCENT",
        observation_id=f"{trading_date.isoformat()}-{index}",
        score=Decimal(index) / Decimal("10"),
        outcome=index % 2,
        panel_reference=_reference("RESEARCH_PANEL_V2", f"panel-{trading_date}"),
        forecast_reference=_reference("PATH_FORECAST", f"forecast-{index}"),
    )


def test_path_calibration_partitions_by_date_and_purges_overlapping_labels() -> None:
    start = date(2026, 8, 3)
    values = tuple(
        _observation(start + timedelta(days=day), index)
        for day in range(4)
        for index in range(day * 2, day * 2 + 2)
    )

    observations, reasons = _partition_observations(
        values,
        policy=CalibrationPartitionPolicy.create(
            minimum_fit_samples=2,
            minimum_validation_samples=2,
        ),
    )

    assert observations is not None
    assert sum(
        item.partition is CalibrationPartition.FIT for item in observations
    ) == 4
    assert sum(
        item.partition is CalibrationPartition.VALIDATION for item in observations
    ) == 2
    assert all(
        not item.observation_id.startswith("2026-08-05")
        for item in observations
    )
    assert reasons == (
        "LABEL_AWARE_PURGE_APPLIED",
        "TRADING_DATE_PARTITION_APPLIED",
    )


def test_path_calibration_returns_not_estimable_without_date_partition() -> None:
    observations, reasons = _partition_observations(
        (_observation(date(2026, 8, 3), 1),),
        policy=CalibrationPartitionPolicy.create(
            minimum_fit_samples=1,
            minimum_validation_samples=1,
        ),
    )

    assert observations is None
    assert reasons == ("NOT_ESTIMABLE_TRADING_DATE_PARTITION",)


def test_path_calibration_partition_policy_identity_freezes_validation_floor() -> None:
    first = CalibrationPartitionPolicy.create(
        minimum_fit_samples=10,
        minimum_validation_samples=2,
    )
    second = CalibrationPartitionPolicy.create(
        minimum_fit_samples=10,
        minimum_validation_samples=3,
    )

    assert first.policy_id != second.policy_id
    assert first.policy_hash != second.policy_hash
    assert first.identity_payload()["minimum_validation_samples"] == 2
    assert first.identity_payload()["fit_rule"].startswith("TRADING_DATE_LT")
