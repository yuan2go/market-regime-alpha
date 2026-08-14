from __future__ import annotations

from datetime import timedelta
from decimal import Decimal, localcontext

import pytest

from market_regime_alpha.application.continuous_research.journal import (
    RuntimeArtifactReference,
)
from market_regime_alpha.strategies.feedback import (
    StrategyFeedbackKind,
    StrategyFeedbackStatus,
    attribute_path_outcomes,
    decide_strategy_qualification,
    evaluate_strategy_challenger,
)
from market_regime_alpha.strategies.path_outcomes import (
    PathPriceObservation,
    measure_strategy_path,
)
from tests.strategies.test_multi_strategy_runtime import NOW, _reference


def _outcome(
    version: RuntimeArtifactReference,
    *,
    suffix: str,
    close: str,
) -> object:
    return measure_strategy_path(
        strategy_version_reference=version,
        strategy_run_reference=_reference("STRATEGY_RUN", f"run-{suffix}"),
        dataset_reference=_reference("DATASET", "frozen-dataset"),
        target_reference=_reference("TARGET_DEFINITION", "swing-5"),
        symbol=f"00000{suffix}.SZ",
        decision_time=NOW,
        reference_price=Decimal("10"),
        target_return=Decimal("0.02"),
        stop_return=Decimal("0.02"),
        continuation_return=Decimal("0.01"),
        failure_return=Decimal("-0.01"),
        observations=(
            PathPriceObservation(
                observed_at=NOW + timedelta(days=1),
                session_offset=1,
                high=Decimal("10.30"),
                low=Decimal("9.80"),
                close=Decimal(close),
            ),
        ),
        exit_time=None,
        exit_price=None,
        measured_at=NOW + timedelta(days=2),
    )


def test_outcome_attribution_is_strictly_strategy_scoped() -> None:
    version_a = _reference("STRATEGY_VERSION", "swing-a")
    version_b = _reference("STRATEGY_VERSION", "swing-b")
    outcome_a = _outcome(version_a, suffix="1", close="10.20")
    outcome_b = _outcome(version_b, suffix="2", close="9.90")

    attribution = attribute_path_outcomes(
        strategy_version_reference=version_a,
        outcomes=(outcome_a,),
        created_at=NOW + timedelta(days=3),
    )

    assert attribution.artifact_kind is StrategyFeedbackKind.ATTRIBUTION
    assert attribution.status is StrategyFeedbackStatus.EXPLORATORY
    assert dict(attribution.metrics)["outcome_count"] == "1"
    assert attribution.source_references == (
        RuntimeArtifactReference(
            "STRATEGY_PATH_OUTCOME",
            outcome_a.outcome_id,
            outcome_a.outcome_hash,
        ),
    )
    with pytest.raises(ValueError, match="Strategy Version"):
        attribute_path_outcomes(
            strategy_version_reference=version_a,
            outcomes=(outcome_a, outcome_b),
            created_at=NOW + timedelta(days=3),
        )
    with pytest.raises(ValueError, match="before its Path Outcome"):
        attribute_path_outcomes(
            strategy_version_reference=version_a,
            outcomes=(outcome_a,),
            created_at=NOW + timedelta(days=1),
        )


def test_challenger_and_qualification_remain_exploratory_and_fail_closed() -> None:
    incumbent_version = _reference("STRATEGY_VERSION", "incumbent")
    challenger_version = _reference("STRATEGY_VERSION", "challenger")
    incumbent = attribute_path_outcomes(
        strategy_version_reference=incumbent_version,
        outcomes=(_outcome(incumbent_version, suffix="1", close="10.20"),),
        created_at=NOW + timedelta(days=3),
    )
    challenger = attribute_path_outcomes(
        strategy_version_reference=challenger_version,
        outcomes=(_outcome(challenger_version, suffix="2", close="10.10"),),
        created_at=NOW + timedelta(days=3),
    )

    comparison = evaluate_strategy_challenger(
        incumbent=incumbent,
        challenger=challenger,
        created_at=NOW + timedelta(days=4),
    )
    qualification = decide_strategy_qualification(
        strategy_version_reference=challenger_version,
        attribution=challenger,
        challenger_evaluation=comparison,
        formal_pit=False,
        formal_oos=False,
        calibrated=False,
        net_economics_established=False,
        prospective_evidence=False,
        created_at=NOW + timedelta(days=5),
    )

    assert comparison.artifact_kind is StrategyFeedbackKind.CHALLENGER_EVALUATION
    assert comparison.strategy_version_reference == challenger_version
    assert comparison.status is StrategyFeedbackStatus.EXPLORATORY
    assert qualification.artifact_kind is StrategyFeedbackKind.QUALIFICATION_DECISION
    assert qualification.status is StrategyFeedbackStatus.NOT_QUALIFIED
    assert qualification.production_authorized is False
    assert set(qualification.findings) >= {
        "ALPHA_NOT_ESTABLISHED",
        "CALIBRATED_FALSE",
        "FORMAL_OOS_FALSE",
        "FORMAL_PIT_NOT_ESTABLISHED",
        "NET_ECONOMICS_NOT_ESTABLISHED",
        "PROSPECTIVE_EVIDENCE_NOT_ESTABLISHED",
        "PRODUCTION_AUTHORIZED_FALSE",
    }

    with pytest.raises(ValueError, match="before its Attribution"):
        evaluate_strategy_challenger(
            incumbent=incumbent,
            challenger=challenger,
            created_at=NOW + timedelta(days=2),
        )
    with pytest.raises(ValueError, match="before its feedback inputs"):
        decide_strategy_qualification(
            strategy_version_reference=challenger_version,
            attribution=challenger,
            challenger_evaluation=comparison,
            formal_pit=False,
            formal_oos=False,
            calibrated=False,
            net_economics_established=False,
            prospective_evidence=False,
            created_at=NOW + timedelta(days=3),
        )


def test_feedback_identity_does_not_depend_on_process_decimal_context() -> None:
    version = _reference("STRATEGY_VERSION", "context-version")
    outcomes = (_outcome(version, suffix="3", close="10.123456789"),)

    with localcontext() as context:
        context.prec = 8
        low_precision = attribute_path_outcomes(
            strategy_version_reference=version,
            outcomes=outcomes,
            created_at=NOW + timedelta(days=3),
        )
    with localcontext() as context:
        context.prec = 50
        high_precision = attribute_path_outcomes(
            strategy_version_reference=version,
            outcomes=outcomes,
            created_at=NOW + timedelta(days=3),
        )

    assert low_precision == high_precision
