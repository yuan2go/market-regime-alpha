from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from market_regime_alpha.application.research_evaluation.targets import (
    engineering_multi_horizon_protocol,
)
from market_regime_alpha.application.research_validation.calibration import (
    CalibrationMethod,
    CalibrationProtocol,
)
from market_regime_alpha.application.research_validation.calibration_qualification import (
    CalibrationQualificationPolicy,
)
from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)


NOW = datetime(2026, 8, 11, 8, tzinfo=UTC)


def test_calibration_policy_identity_freezes_target_method_and_oos_floors() -> None:
    target = engineering_multi_horizon_protocol().targets[0]
    calibration = CalibrationProtocol.create(
        protocol_version="formal-calibration-v1",
        method=CalibrationMethod.PLATT_LOGISTIC,
    )
    values = dict(
        policy_version="phase-c5-v1",
        target_protocol_reference=ValidationArtifactReference(
            "OUTCOME_TARGET_PROTOCOL",
            engineering_multi_horizon_protocol().protocol_id,
            engineering_multi_horizon_protocol().protocol_hash,
        ),
        target_reference=ValidationArtifactReference(
            "OUTCOME_TARGET", target.target_id, target.target_hash
        ),
        barrier_id=target.barriers[0].barrier_id,
        calibration_protocol_reference=ValidationArtifactReference(
            "CALIBRATION_PROTOCOL",
            calibration.protocol_id,
            calibration.protocol_hash,
        ),
        minimum_oos_samples=30,
        maximum_brier=Decimal("0.20"),
        maximum_log_loss=Decimal("0.60"),
        maximum_ece=Decimal("0.05"),
        minimum_coverage=Decimal("0.95"),
        locked_at=NOW,
    )
    first = CalibrationQualificationPolicy.create(**values)
    changed = CalibrationQualificationPolicy.create(
        **{**values, "maximum_ece": Decimal("0.04")}
    )

    assert first.policy_hash != changed.policy_hash
    assert first.identity_payload()["method_selection_uses_locked_oos"] is False
    assert first.identity_payload()["engineering_default"] is False
