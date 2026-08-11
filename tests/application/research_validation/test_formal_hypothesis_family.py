from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from market_regime_alpha.application.research_evaluation.targets import (
    engineering_multi_horizon_protocol,
)
from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.application.research_validation.formal_evaluation import (
    EvaluationMetricStatus,
    EvaluationObservation,
    EvaluationPartition,
    EvaluationWindow,
    FormalEvaluationProtocol,
    MultipleTestingMethod,
)
from market_regime_alpha.application.research_validation.formal_hypothesis_family import (
    FamilyEvaluationInput,
    FrozenHypothesisFamily,
    run_formal_hypothesis_family_evaluation,
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


def _evaluation() -> FormalEvaluationProtocol:
    targets = engineering_multi_horizon_protocol()
    return FormalEvaluationProtocol.create(
        protocol_version="family-test-v1",
        target_protocol=targets,
        windows=(
            EvaluationWindow(
                "train", EvaluationPartition.TRAIN,
                date(2026, 1, 2), date(2026, 1, 9), 1,
            ),
            EvaluationWindow(
                "validation", EvaluationPartition.VALIDATION,
                date(2026, 1, 12), date(2026, 1, 19), 1,
            ),
            EvaluationWindow(
                "locked-oos", EvaluationPartition.LOCKED_OOS,
                date(2026, 1, 22), date(2026, 1, 30), 1,
            ),
        ),
        bootstrap_iterations=20,
        confidence_level=Decimal("0.90"),
        multiple_testing_method=MultipleTestingMethod.BONFERRONI,
        hypothesis_family_id="FROZEN-MULTI-TARGET-V1",
        top_k=1,
        locked_at=NOW,
    )


def _family() -> FrozenHypothesisFamily:
    targets = engineering_multi_horizon_protocol()
    return FrozenHypothesisFamily.create(
        formal_protocol_reference=_reference(
            "FORMAL_RESEARCH_PROTOCOL", "formal-protocol-family-test"
        ),
        evaluation_protocol=_evaluation(),
        target_references=tuple(
            ValidationArtifactReference(
                "OUTCOME_TARGET", item.target_id, item.target_hash
            )
            for item in targets.targets[:2]
        ),
        frozen_at=NOW,
    )


def _observations(prefix: str) -> tuple[EvaluationObservation, ...]:
    return tuple(
        EvaluationObservation(
            observation_id=f"{prefix}-{day}-{symbol}",
            session_date=date(2026, 1, day),
            label_end_date=date(2026, 1, day),
            symbol=symbol,
            score=Decimal(score),
            realized_return=Decimal(realized),
            mfe=Decimal("0.03"),
            mae=Decimal("-0.01"),
            regime="RISK_ON",
            liquidity_slice="HIGH",
            market_cap_slice="LARGE",
            theme_slice="T1",
        )
        for day, symbol, score, realized in (
            (22, "000001.SZ", "1", "0.01"),
            (22, "000002.SZ", "2", "0.03"),
            (23, "000001.SZ", "1", "0.02"),
            (23, "000002.SZ", "2", "0.04"),
        )
    )


def test_frozen_family_identity_rejects_post_hoc_target_mutation() -> None:
    family = _family()
    targets = engineering_multi_horizon_protocol()
    added = ValidationArtifactReference(
        "OUTCOME_TARGET", targets.targets[2].target_id, targets.targets[2].target_hash
    )

    assert FrozenHypothesisFamily.from_canonical_dict(
        family.to_canonical_dict()
    ) == family
    with pytest.raises(ValueError, match="identity"):
        replace(
            family,
            target_references=(*family.target_references, added),
        )


def test_family_evaluation_corrects_across_every_frozen_target() -> None:
    family = _family()
    inputs = tuple(
        FamilyEvaluationInput(
            target_reference=target,
            panel_reference=_reference("RESEARCH_PANEL_V2", f"panel-{index}"),
            observations=_observations(f"target-{index}"),
        )
        for index, target in enumerate(family.target_references, start=1)
    )

    result = run_formal_hypothesis_family_evaluation(
        family=family,
        protocol=_evaluation(),
        inputs=inputs,
        formal_pit_evidence=None,
        created_at=NOW,
    )
    assert type(result).from_canonical_dict(result.to_canonical_dict()) == result
    assert run_formal_hypothesis_family_evaluation(
        family=family,
        protocol=_evaluation(),
        inputs=inputs,
        formal_pit_evidence=None,
        created_at=NOW,
    ) == result

    estimated = tuple(
        item for item in result.metrics
        if item.metric.status is EvaluationMetricStatus.ESTIMATED
    )
    assert estimated
    assert {item.target_reference for item in estimated} == set(
        family.target_references
    )
    for item in estimated:
        assert item.metric.raw_p_value is not None
        assert item.metric.adjusted_p_value == min(
            item.metric.raw_p_value * Decimal(len(result.metrics)), Decimal("1")
        )
    all_slice = tuple(
        item
        for item in result.metrics
        if item.metric.slice_kind == "ALL" and item.metric.slice_value == "ALL"
    )
    expected_all_count = (
        len(family.target_references)
        * len({(item.fold, item.partition) for item in family.windows})
        * len(family.sensitivity_return_multipliers)
        * len(family.metric_names)
    )
    assert len(all_slice) == expected_all_count
    assert any(
        item.metric.partition is EvaluationPartition.TRAIN
        and item.metric.status is EvaluationMetricStatus.NOT_ESTIMABLE
        for item in all_slice
    )

    missing_target = inputs[:-1]
    with pytest.raises(ValueError, match="exact frozen Target family"):
        run_formal_hypothesis_family_evaluation(
            family=family,
            protocol=_evaluation(),
            inputs=missing_target,
            formal_pit_evidence=None,
            created_at=NOW,
        )


def test_family_evaluation_keeps_empty_preregistered_target_in_denominator() -> None:
    family = _family()
    inputs = (
        FamilyEvaluationInput(
            target_reference=family.target_references[0],
            panel_reference=_reference("RESEARCH_PANEL_V2", "panel-populated"),
            observations=_observations("populated"),
        ),
        FamilyEvaluationInput(
            target_reference=family.target_references[1],
            panel_reference=_reference("RESEARCH_PANEL_V2", "panel-empty"),
            observations=(),
        ),
    )

    result = run_formal_hypothesis_family_evaluation(
        family=family,
        protocol=_evaluation(),
        inputs=inputs,
        formal_pit_evidence=None,
        created_at=NOW,
    )

    empty_metrics = tuple(
        item
        for item in result.metrics
        if item.target_reference == family.target_references[1]
    )
    assert empty_metrics
    assert all(
        item.metric.status is EvaluationMetricStatus.NOT_ESTIMABLE
        and item.metric.reason_codes == ("NO_TARGET_OBSERVATIONS",)
        for item in empty_metrics
    )
    estimated = tuple(
        item
        for item in result.metrics
        if item.metric.status is EvaluationMetricStatus.ESTIMATED
    )
    assert estimated
    for item in estimated:
        assert item.metric.raw_p_value is not None
        assert item.metric.adjusted_p_value == min(
            item.metric.raw_p_value * Decimal(len(result.metrics)), Decimal("1")
        )
