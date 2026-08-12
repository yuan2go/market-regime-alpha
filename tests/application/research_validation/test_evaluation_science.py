from __future__ import annotations

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
    MultipleTestingErrorRate,
    MultipleTestingMethod,
    benchmark_evaluation_hypotheses,
    run_formal_evaluation,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash


NOW = datetime(2026, 8, 10, tzinfo=UTC)


def _reference() -> ValidationArtifactReference:
    return ValidationArtifactReference(
        "RESEARCH_PANEL_V2",
        ArtifactId("evaluation-science-panel"),
        canonical_hash({"panel": "evaluation-science"}),
    )


def _protocol(*, bootstrap_block_sessions: int = 1) -> FormalEvaluationProtocol:
    return FormalEvaluationProtocol.create(
        protocol_version="evaluation-science-v1",
        target_protocol=engineering_multi_horizon_protocol(),
        windows=(
            EvaluationWindow(
                "train",
                EvaluationPartition.TRAIN,
                date(2026, 1, 1),
                date(2026, 1, 10),
                1,
            ),
            EvaluationWindow(
                "validation",
                EvaluationPartition.VALIDATION,
                date(2026, 1, 13),
                date(2026, 1, 20),
                1,
            ),
            EvaluationWindow(
                "oos",
                EvaluationPartition.LOCKED_OOS,
                date(2026, 1, 23),
                date(2026, 1, 30),
                1,
            ),
        ),
        bootstrap_iterations=40,
        bootstrap_block_sessions=bootstrap_block_sessions,
        confidence_level=Decimal("0.90"),
        multiple_testing_method=MultipleTestingMethod.BENJAMINI_HOCHBERG,
        multiple_testing_error_rate=MultipleTestingErrorRate.FDR,
        hypothesis_specs=benchmark_evaluation_hypotheses(),
        hypothesis_family_id="PHASE_B_DAILY_CROSS_SECTION_V1",
        top_k=1,
        locked_at=NOW,
    )


def _observation(
    observation_id: str,
    session_date: date,
    symbol: str,
    score: str,
    realized_return: str,
    *,
    label_end_date: date | None = None,
) -> EvaluationObservation:
    return EvaluationObservation(
        observation_id=observation_id,
        session_date=session_date,
        label_end_date=label_end_date or session_date,
        symbol=symbol,
        score=Decimal(score),
        realized_return=Decimal(realized_return),
        mfe=Decimal("0.03"),
        mae=Decimal("-0.01"),
        regime="RISK_ON",
        liquidity_slice="HIGH",
        market_cap_slice="LARGE",
        theme_slice="T1",
    )


def test_daily_cross_sectional_rank_ic_is_tie_aware_not_pooled() -> None:
    observations = (
        _observation("d1-a", date(2026, 1, 13), "000001.SZ", "1", "0.01"),
        _observation("d1-b", date(2026, 1, 13), "000002.SZ", "1", "0.01"),
        _observation("d1-c", date(2026, 1, 13), "000003.SZ", "2", "0.03"),
        _observation("d2-a", date(2026, 1, 14), "000001.SZ", "1", "0.03"),
        _observation("d2-b", date(2026, 1, 14), "000002.SZ", "2", "0.02"),
        _observation("d2-c", date(2026, 1, 14), "000003.SZ", "3", "0.01"),
        # The observed final Validation session is embargoed from Locked OOS.
        _observation("embargo", date(2026, 1, 20), "000001.SZ", "1", "0.01"),
    )

    result = run_formal_evaluation(
        protocol=_protocol(),
        panel_reference=_reference(),
        observations=observations,
        formal_pit_evidence=None,
        created_at=NOW,
    )

    metrics = {
        item.metric_name: item
        for item in result.metrics
        if item.slice_kind == "ALL"
        and item.sensitivity_return_multiplier == Decimal("1")
    }
    assert metrics["RANK_IC"].status is EvaluationMetricStatus.ESTIMATED
    # Day 1 is +1 with average ties; day 2 is -1.  The daily mean is zero.
    assert metrics["RANK_IC"].estimate is not None
    assert abs(metrics["RANK_IC"].estimate) < Decimal("1e-12")
    assert metrics["POSITIVE_IC_RATIO"].estimate == Decimal("0.5")
    assert metrics["TOP_K_RETURN"].estimate == Decimal("0.02")
    assert metrics["SPREAD"].estimate == Decimal("0")
    assert metrics["INCREMENTAL_LIFT"].status is EvaluationMetricStatus.ESTIMATED


def test_not_estimable_is_explicit_for_single_symbol_cross_sections() -> None:
    result = run_formal_evaluation(
        protocol=_protocol(),
        panel_reference=_reference(),
        observations=(
            _observation("only-a", date(2026, 1, 13), "000001.SZ", "1", "0.01"),
            _observation("only-b", date(2026, 1, 14), "000001.SZ", "2", "0.02"),
        ),
        formal_pit_evidence=None,
        created_at=NOW,
    )

    metrics = {
        item.metric_name: item
        for item in result.metrics
        if item.slice_kind == "ALL"
        and item.sensitivity_return_multiplier == Decimal("1")
    }
    assert metrics["IC"].status is EvaluationMetricStatus.NOT_ESTIMABLE
    assert metrics["IC"].estimate is None
    assert metrics["IC"].reason_codes == ("INSUFFICIENT_DAILY_CROSS_SECTIONS",)
    assert metrics["IC"].raw_p_value is None
    assert metrics["IC"].adjusted_p_value is None


def test_purge_and_embargo_apply_to_validation_to_locked_oos_boundary() -> None:
    observations = (
        _observation(
            "validation-overlap",
            date(2026, 1, 20),
            "000001.SZ",
            "1",
            "0.01",
            label_end_date=date(2026, 1, 23),
        ),
        _observation(
            "oos-safe",
            date(2026, 1, 23),
            "000001.SZ",
            "1",
            "0.01",
        ),
    )

    result = run_formal_evaluation(
        protocol=_protocol(bootstrap_block_sessions=2),
        panel_reference=_reference(),
        observations=observations,
        formal_pit_evidence=None,
        created_at=NOW,
    )

    assert "validation-overlap" in result.excluded_observation_ids
    assert {item.partition for item in result.metrics} == {
        EvaluationPartition.LOCKED_OOS
    }
    assert result.protocol_reference.artifact_id == _protocol(
        bootstrap_block_sessions=2
    ).protocol_id


def test_embargo_uses_frozen_calendar_not_observation_presence() -> None:
    observations = (
        _observation(
            "validation-before-calendar-embargo",
            date(2026, 1, 19),
            "000001.SZ",
            "1",
            "0.01",
        ),
        _observation(
            "locked-oos",
            date(2026, 1, 23),
            "000001.SZ",
            "1",
            "0.02",
        ),
    )
    frozen_dates = tuple(date(2026, 1, day) for day in range(1, 31))

    result = run_formal_evaluation(
        protocol=_protocol(),
        panel_reference=_reference(),
        observations=observations,
        formal_pit_evidence=None,
        created_at=NOW,
        frozen_trading_dates=frozen_dates,
    )

    assert "validation-before-calendar-embargo" not in result.excluded_observation_ids
    assert "locked-oos" not in result.excluded_observation_ids

    with pytest.raises(ValueError, match="Frozen Trading Calendar"):
        run_formal_evaluation(
            protocol=_protocol(),
            panel_reference=_reference(),
            observations=observations,
            formal_pit_evidence=None,
            created_at=NOW,
            frozen_trading_dates=tuple(reversed(frozen_dates)),
        )
