from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from random import Random

from market_regime_alpha.application.research_evaluation.targets import (
    engineering_multi_horizon_protocol,
)
from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.application.research_validation.formal_evaluation import (
    AlternativeHypothesis,
    ConfidenceIntervalMethod,
    EvaluationHypothesisSpec,
    EvaluationMetric,
    EvaluationMetricStatus,
    EvaluationObservation,
    EvaluationPartition,
    EvaluationWindow,
    FormalEvaluationProtocol,
    HypothesisTestMethod,
    MetricRole,
    MultipleTestingErrorRate,
    MultipleTestingMethod,
    adjust_multiple_testing,
    benchmark_evaluation_hypotheses,
    run_formal_evaluation,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash


NOW = datetime(2026, 8, 12, tzinfo=UTC)
PANEL = ValidationArtifactReference(
    "RESEARCH_PANEL_V2",
    ArtifactId("statistical-proof-panel"),
    canonical_hash({"panel": "statistical-proof"}),
)


def _protocol(*, iterations: int = 49) -> FormalEvaluationProtocol:
    return FormalEvaluationProtocol.create(
        protocol_version="statistical-proof-v1",
        target_protocol=engineering_multi_horizon_protocol(),
        windows=(
            EvaluationWindow(
                "train", EvaluationPartition.TRAIN,
                date(2025, 10, 1), date(2025, 10, 31), 1,
            ),
            EvaluationWindow(
                "validation", EvaluationPartition.VALIDATION,
                date(2026, 1, 1), date(2026, 4, 30), 1,
            ),
            EvaluationWindow(
                "locked", EvaluationPartition.LOCKED_OOS,
                date(2026, 6, 1), date(2026, 6, 30), 1,
            ),
        ),
        bootstrap_iterations=iterations,
        bootstrap_block_sessions=4,
        confidence_level=Decimal("0.95"),
        multiple_testing_method=MultipleTestingMethod.HOLM_BONFERRONI,
        multiple_testing_error_rate=MultipleTestingErrorRate.FWER,
        hypothesis_family_id="DETERMINISTIC-STATISTICAL-PROOF-V1",
        hypothesis_specs=benchmark_evaluation_hypotheses(),
        top_k=3,
        sensitivity_return_multipliers=(Decimal("1"),),
        locked_at=NOW,
    )


def _panel(*, seed: int, signal: float) -> tuple[EvaluationObservation, ...]:
    random = Random(seed)
    observations: list[EvaluationObservation] = []
    market_state = 0.0
    symbol_state = [0.0] * 12
    for session in range(28):
        session_date = date(2026, 1, 2) + timedelta(days=session)
        market_state = 0.65 * market_state + random.gauss(0.0, 0.006)
        for symbol_index in range(12):
            score = random.gauss(0.0, 1.0)
            symbol_state[symbol_index] = (
                0.45 * symbol_state[symbol_index] + random.gauss(0.0, 0.008)
            )
            realized = (
                market_state
                + symbol_state[symbol_index]
                + signal * score
                + random.gauss(0.0, 0.012)
            )
            observations.append(
                EvaluationObservation(
                    observation_id=f"{seed}:{session}:{symbol_index}",
                    session_date=session_date,
                    label_end_date=session_date,
                    symbol=f"{symbol_index:06d}.SZ",
                    score=Decimal(str(score)),
                    realized_return=Decimal(str(realized)),
                    mfe=Decimal(str(max(realized, 0.0) + 0.004)),
                    mae=Decimal(str(min(realized, 0.0) - 0.004)),
                    regime="COMMON_FACTOR",
                    liquidity_slice="HIGH",
                    market_cap_slice="LARGE",
                    theme_slice="SYNTHETIC",
                )
            )
    return tuple(observations)


def _all_metrics(
    observations: tuple[EvaluationObservation, ...]
) -> dict[str, EvaluationMetric]:
    result = run_formal_evaluation(
        protocol=_protocol(),
        panel_reference=PANEL,
        observations=observations,
        formal_pit_evidence=None,
        created_at=NOW,
    )
    return {
        item.metric_name: item
        for item in result.metrics
        if item.partition is EvaluationPartition.VALIDATION
        and item.slice_kind == "ALL"
        and item.slice_value == "ALL"
    }


def _all_metric(
    observations: tuple[EvaluationObservation, ...], metric_name: str
):
    return _all_metrics(observations)[metric_name]


def test_protocol_freezes_explicit_hypothesis_semantics() -> None:
    protocol = _protocol(iterations=49)
    rank_ic = next(
        item for item in protocol.hypothesis_specs if item.metric_name == "RANK_IC"
    )
    drawdown = next(
        item for item in protocol.hypothesis_specs if item.metric_name == "DRAWDOWN"
    )

    assert rank_ic.null_value == Decimal("0")
    assert rank_ic.benchmark == "NO_CROSS_SECTIONAL_ASSOCIATION"
    assert rank_ic.alternative is AlternativeHypothesis.TWO_SIDED
    assert rank_ic.test_method is HypothesisTestMethod.NULL_CENTERED_MOVING_BLOCK
    assert rank_ic.interval_method is ConfidenceIntervalMethod.MOVING_BLOCK_PERCENTILE
    assert rank_ic.role is MetricRole.PRIMARY
    assert drawdown.test_method is HypothesisTestMethod.NONE
    assert drawdown.null_value is None
    assert protocol.multiple_testing_error_rate is MultipleTestingErrorRate.FWER
    assert FormalEvaluationProtocol.from_canonical_dict(
        protocol.to_canonical_dict()
    ) == protocol


def test_metric_without_defensible_null_has_interval_but_no_p_value() -> None:
    metric = _all_metric(_panel(seed=4, signal=0.0), "DRAWDOWN")

    assert metric.status is EvaluationMetricStatus.ESTIMATED
    assert metric.confidence_low is not None
    assert metric.confidence_high is not None
    assert metric.raw_p_value is None
    assert metric.adjusted_p_value is None
    assert metric.test_method is HypothesisTestMethod.NONE


def test_null_centered_test_is_deterministic_and_preserves_type_i_error() -> None:
    p_values = tuple(
        _all_metric(_panel(seed=seed, signal=0.0), "RANK_IC").raw_p_value
        for seed in range(8)
    )

    assert all(value is not None for value in p_values)
    assert p_values[0] == _all_metric(
        _panel(seed=0, signal=0.0), "RANK_IC"
    ).raw_p_value
    # Fixed synthetic ensemble with serial and common-factor dependence.  This
    # is a deterministic size proof, not a probabilistic/flaky assertion.
    assert sum(value <= Decimal("0.05") for value in p_values if value is not None) <= 2


def test_known_signal_recovers_rank_ic_and_top_bottom_spread() -> None:
    observations = _panel(seed=991, signal=0.018)
    metrics = _all_metrics(observations)
    rank_ic = metrics["RANK_IC"]
    spread = metrics["SPREAD"]

    assert rank_ic.estimate is not None and rank_ic.estimate > Decimal("0.35")
    assert rank_ic.raw_p_value is not None and rank_ic.raw_p_value <= Decimal("0.04")
    assert spread.estimate is not None and spread.estimate > Decimal("0.015")
    assert spread.raw_p_value is not None and spread.raw_p_value <= Decimal("0.04")


def test_known_signal_has_deterministic_power_across_seed_cohort() -> None:
    metrics = tuple(
        _all_metric(_panel(seed=100 + seed, signal=0.018), "RANK_IC")
        for seed in range(6)
    )

    assert all(
        item.estimate is not None and item.estimate > Decimal("0.6")
        for item in metrics
    )
    assert sum(
        item.raw_p_value is not None
        and item.raw_p_value <= Decimal("0.05")
        for item in metrics
    ) == 6


def test_signal_detection_improves_with_more_sessions_in_fixed_cohort() -> None:
    def detections(session_count: int) -> int:
        detected = 0
        for seed in range(10, 18):
            panel = _panel(seed=seed, signal=0.003)
            dates = tuple(
                sorted({item.session_date for item in panel})[:session_count]
            )
            metric = _all_metric(
                tuple(item for item in panel if item.session_date in dates),
                "RANK_IC",
            )
            if (
                metric.raw_p_value is not None
                and metric.raw_p_value <= Decimal("0.05")
            ):
                detected += 1
        return detected

    # Cohort-level sensitivity is the stable invariant. Individual short
    # samples may still be significant by chance and are deliberately retained.
    assert detections(12) == 4
    assert detections(28) == 5


def test_holm_correction_controls_a_frozen_fwer_family() -> None:
    adjusted = adjust_multiple_testing(
        (Decimal("0.01"), Decimal("0.03"), Decimal("0.04"), Decimal("0.20")),
        MultipleTestingMethod.HOLM_BONFERRONI,
    )

    assert adjusted == (
        Decimal("0.04"), Decimal("0.09"), Decimal("0.09"), Decimal("0.20")
    )


def test_invalid_test_spec_cannot_hide_an_unfrozen_null() -> None:
    try:
        EvaluationHypothesisSpec(
            hypothesis_id="rank-ic-without-null",
            metric_name="RANK_IC",
            role=MetricRole.PRIMARY,
            benchmark="NO_ASSOCIATION",
            interval_method=ConfidenceIntervalMethod.MOVING_BLOCK_PERCENTILE,
            test_method=HypothesisTestMethod.NULL_CENTERED_MOVING_BLOCK,
            null_value=None,
            alternative=AlternativeHypothesis.TWO_SIDED,
            economic_threshold=None,
        )
    except ValueError as exc:
        assert "null" in str(exc).lower()
    else:
        raise AssertionError("test specification accepted an absent null")
