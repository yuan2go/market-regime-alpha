from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.application.research_validation.qualification import (
    FormalEvaluationObservationBinding,
    FormalOOSMetricFloor,
    FormalOOSQualificationPolicy,
    QualificationOutcome,
    evaluate_metric_floor_payloads,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash


NOW = datetime(2026, 8, 11, tzinfo=UTC)


def _reference(kind: str, name: str) -> ValidationArtifactReference:
    return ValidationArtifactReference(
        kind,
        ArtifactId(name),
        canonical_hash({"kind": kind, "name": name}),
    )


def test_formal_evaluation_observation_binding_accepts_only_owner_references() -> None:
    binding = FormalEvaluationObservationBinding.create(
        forecast_reference=_reference(
            "OUTCOME_TARGET_BOUND_FORECAST", "forecast-v1"
        ),
        label_reference=_reference("TARGET_OUTCOME_LABEL", "label-v1"),
        panel_slice_reference=_reference(
            "RESEARCH_PANEL_SLICE_V2", "panel-slice-v1"
        ),
        panel_row_reference=_reference("RESEARCH_PANEL_ROW_V2", "panel-row-v1"),
    )

    assert FormalEvaluationObservationBinding.from_canonical_dict(
        binding.to_canonical_dict()
    ) == binding
    with pytest.raises(ValueError, match="identity mismatch"):
        FormalEvaluationObservationBinding(
            observation_id="caller-selected-observation",
            forecast_reference=binding.forecast_reference,
            label_reference=binding.label_reference,
            panel_slice_reference=binding.panel_slice_reference,
            panel_row_reference=binding.panel_row_reference,
        )


def _policy() -> FormalOOSQualificationPolicy:
    return FormalOOSQualificationPolicy.create(
        policy_version="phase-c4-test-v1",
        metric_floors=(
            FormalOOSMetricFloor("SPREAD", Decimal("0.001"), None),
        ),
        minimum_sample_count=20,
        maximum_adjusted_p_value=Decimal("0.05"),
        require_confidence_interval_excludes_zero=True,
        required_sensitivity_multipliers=(Decimal("0.9"), Decimal("1")),
        locked_at=NOW,
    )


def _metric(multiplier: str, **overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "partition": "LOCKED_OOS",
        "slice_kind": "ALL",
        "slice_value": "ALL",
        "metric_name": "SPREAD",
        "fold": 1,
        "sensitivity_return_multiplier": multiplier,
        "status": "ESTIMATED",
        "sample_count": 30,
        "estimate": "0.01",
        "adjusted_p_value": "0.01",
        "confidence_low": "0.002",
        "confidence_high": "0.02",
    }
    values.update(overrides)
    return values


def test_formal_oos_metric_policy_preserves_pass_reject_and_not_estimable() -> None:
    policy = _policy()
    passed = evaluate_metric_floor_payloads(
        policy=policy,
        metrics=(_metric("0.9"), _metric("1")),
    )
    rejected = evaluate_metric_floor_payloads(
        policy=policy,
        metrics=(
            _metric("0.9"),
            _metric("1", estimate="-0.01", confidence_low="-0.02"),
        ),
    )
    not_estimable = evaluate_metric_floor_payloads(
        policy=policy,
        metrics=(_metric("1"),),
    )

    assert passed == (QualificationOutcome.SATISFIED, ())
    assert rejected[0] is QualificationOutcome.REJECTED
    assert "LOCKED_OOS_MINIMUM_NOT_MET_SPREAD_1_FOLD_1" in rejected[1]
    assert not_estimable[0] is QualificationOutcome.NOT_ESTIMABLE


def test_formal_oos_metric_policy_rejects_any_failing_fold() -> None:
    outcome, reasons = evaluate_metric_floor_payloads(
        policy=_policy(),
        metrics=(
            _metric("0.9", fold=1),
            _metric("0.9", fold=2, estimate="-0.01", confidence_low="-0.02"),
            _metric("1", fold=1),
            _metric("1", fold=2),
        ),
    )

    assert outcome is QualificationOutcome.REJECTED
    assert "LOCKED_OOS_MINIMUM_NOT_MET_SPREAD_0.9_FOLD_2" in reasons


def test_formal_oos_policy_identity_freezes_metric_floor() -> None:
    changed = FormalOOSQualificationPolicy.create(
        policy_version="phase-c4-test-v1",
        metric_floors=(
            FormalOOSMetricFloor("SPREAD", Decimal("0.002"), None),
        ),
        minimum_sample_count=20,
        maximum_adjusted_p_value=Decimal("0.05"),
        require_confidence_interval_excludes_zero=True,
        required_sensitivity_multipliers=(Decimal("0.9"), Decimal("1")),
        locked_at=NOW,
    )

    assert changed.policy_hash != _policy().policy_hash
