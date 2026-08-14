from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal, localcontext

import pytest

from market_regime_alpha.application.continuous_research.journal import (
    RuntimeArtifactReference,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.strategies.path_outcomes import (
    BarrierOrderingOutcome,
    PathPriceObservation,
    measure_strategy_path,
)


START = datetime(2026, 1, 5, 7, 0, tzinfo=UTC)


def _reference(kind: str, name: str) -> RuntimeArtifactReference:
    digest = canonical_hash({"kind": kind, "name": name})
    return RuntimeArtifactReference(kind, ArtifactId(f"{name}:{digest[7:]}"), digest)


def _point(
    session: int,
    *,
    high: str,
    low: str,
    close: str,
    minutes: int = 0,
) -> PathPriceObservation:
    return PathPriceObservation(
        observed_at=START + timedelta(days=session, minutes=minutes),
        session_offset=session,
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal(close),
    )


def test_path_outcome_measures_multi_horizon_and_post_exit_costs() -> None:
    outcome = measure_strategy_path(
        strategy_version_reference=_reference("STRATEGY_VERSION", "swing-v1"),
        strategy_run_reference=_reference("STRATEGY_RUN", "run-1"),
        dataset_reference=_reference("DATASET", "dataset-1"),
        target_reference=_reference("TARGET_DEFINITION", "swing-5-close"),
        symbol="000001.SZ",
        decision_time=START,
        reference_price=Decimal("10"),
        target_return=Decimal("0.05"),
        stop_return=Decimal("0.03"),
        continuation_return=Decimal("0.02"),
        failure_return=Decimal("-0.02"),
        observations=(
            _point(1, high="10.30", low="9.90", close="10.20"),
            _point(2, high="10.60", low="10.10", close="10.50"),
            _point(3, high="10.80", low="10.20", close="10.40"),
            _point(4, high="10.70", low="9.70", close="9.90"),
            _point(5, high="10.20", low="9.50", close="9.80"),
        ),
        exit_time=START + timedelta(days=3),
        exit_price=Decimal("10.40"),
        measured_at=START + timedelta(days=6),
    )

    assert outcome.horizon_sessions == 5
    assert outcome.mfe == Decimal("0.08")
    assert outcome.mae == Decimal("-0.05")
    assert outcome.barrier_ordering is BarrierOrderingOutcome.TARGET_BEFORE_STOP
    assert outcome.time_to_mfe_seconds == 3 * 24 * 60 * 60
    assert outcome.trend_continuation is False
    assert outcome.failure is True
    assert outcome.post_exit_opportunity_loss == Decimal("0.028846153846153846153846154")
    assert outcome.avoided_drawdown == Decimal("0.0865384615384615384615384615")


def test_same_observation_target_and_stop_is_not_ordered() -> None:
    outcome = measure_strategy_path(
        strategy_version_reference=_reference("STRATEGY_VERSION", "overnight-v1"),
        strategy_run_reference=_reference("STRATEGY_RUN", "run-2"),
        dataset_reference=_reference("DATASET", "dataset-2"),
        target_reference=_reference("TARGET_DEFINITION", "overnight"),
        symbol="600000.SH",
        decision_time=START,
        reference_price=Decimal("10"),
        target_return=Decimal("0.02"),
        stop_return=Decimal("0.02"),
        continuation_return=Decimal("0.01"),
        failure_return=Decimal("-0.01"),
        observations=(_point(1, high="10.30", low="9.70", close="10.00"),),
        exit_time=None,
        exit_price=None,
        measured_at=START + timedelta(days=2),
    )

    assert outcome.barrier_ordering is BarrierOrderingOutcome.NOT_OBSERVABLE
    assert outcome.mfe == Decimal("0.03")
    assert outcome.mae == Decimal("-0.03")
    assert outcome.post_exit_opportunity_loss is None
    assert outcome.avoided_drawdown is None


@pytest.mark.parametrize(
    ("high", "low", "close", "expected_mfe", "expected_mae", "time_to_mfe"),
    (
        ("10.40", "10.10", "10.30", Decimal("0.04"), Decimal("0"), 24 * 60 * 60),
        ("9.90", "9.50", "9.60", Decimal("0"), Decimal("-0.05"), 0),
        ("10.00", "10.00", "10.00", Decimal("0"), Decimal("0"), 0),
    ),
)
def test_path_excursions_are_clamped_to_the_decision_price(
    high: str,
    low: str,
    close: str,
    expected_mfe: Decimal,
    expected_mae: Decimal,
    time_to_mfe: int,
) -> None:
    outcome = measure_strategy_path(
        strategy_version_reference=_reference("STRATEGY_VERSION", "swing-v1"),
        strategy_run_reference=_reference("STRATEGY_RUN", f"run-{high}"),
        dataset_reference=_reference("DATASET", "dataset-edge"),
        target_reference=_reference("TARGET_DEFINITION", "swing-edge"),
        symbol="000001.SZ",
        decision_time=START,
        reference_price=Decimal("10"),
        target_return=Decimal("0.02"),
        stop_return=Decimal("0.02"),
        continuation_return=Decimal("0.01"),
        failure_return=Decimal("-0.01"),
        observations=(_point(1, high=high, low=low, close=close),),
        exit_time=None,
        exit_price=None,
        measured_at=START + timedelta(days=2),
    )

    assert outcome.mfe == expected_mfe
    assert outcome.mae == expected_mae
    assert outcome.time_to_mfe_seconds == time_to_mfe


def test_stop_before_target_and_post_exit_measures_are_distinct() -> None:
    outcome = measure_strategy_path(
        strategy_version_reference=_reference("STRATEGY_VERSION", "swing-v1"),
        strategy_run_reference=_reference("STRATEGY_RUN", "run-stop-first"),
        dataset_reference=_reference("DATASET", "dataset-stop-first"),
        target_reference=_reference("TARGET_DEFINITION", "swing-stop-first"),
        symbol="000001.SZ",
        decision_time=START,
        reference_price=Decimal("10"),
        target_return=Decimal("0.05"),
        stop_return=Decimal("0.03"),
        continuation_return=Decimal("0.01"),
        failure_return=Decimal("-0.01"),
        observations=(
            _point(1, high="10.10", low="9.60", close="9.80"),
            _point(2, high="10.60", low="9.70", close="10.50"),
        ),
        exit_time=START + timedelta(days=1),
        exit_price=Decimal("9.80"),
        measured_at=START + timedelta(days=3),
    )

    assert outcome.barrier_ordering is BarrierOrderingOutcome.STOP_BEFORE_TARGET
    assert outcome.post_exit_opportunity_loss == Decimal("0.081632653061224489795918367")
    assert outcome.avoided_drawdown == Decimal("0.0102040816326530612244897959")
    assert "MARKET_OUTCOME_NOT_STRATEGY_PNL" in outcome.limitations


def test_partial_horizon_is_explicit_and_deterministic() -> None:
    arguments = {
        "strategy_version_reference": _reference("STRATEGY_VERSION", "swing-v1"),
        "strategy_run_reference": _reference("STRATEGY_RUN", "run-partial"),
        "dataset_reference": _reference("DATASET", "dataset-partial"),
        "target_reference": _reference("TARGET_DEFINITION", "swing-five-session"),
        "symbol": "000001.SZ",
        "decision_time": START,
        "reference_price": Decimal("10"),
        "target_return": Decimal("0.05"),
        "stop_return": Decimal("0.03"),
        "continuation_return": Decimal("0.01"),
        "failure_return": Decimal("-0.01"),
        "observations": (
            _point(1, high="10.10", low="9.90", close="10.00"),
            _point(2, high="10.20", low="9.80", close="10.10"),
        ),
        "expected_horizon_sessions": 5,
        "exit_time": None,
        "exit_price": None,
        "measured_at": START + timedelta(days=3),
    }

    first = measure_strategy_path(**arguments)
    second = measure_strategy_path(**arguments)

    assert first.horizon_sessions == 2
    assert "PARTIAL_HORIZON" in first.limitations
    assert first == second


def test_missing_path_observations_fail_explicitly() -> None:
    with pytest.raises(ValueError, match="requires observations"):
        measure_strategy_path(
            strategy_version_reference=_reference("STRATEGY_VERSION", "swing-v1"),
            strategy_run_reference=_reference("STRATEGY_RUN", "run-missing"),
            dataset_reference=_reference("DATASET", "dataset-missing"),
            target_reference=_reference("TARGET_DEFINITION", "swing-missing"),
            symbol="000001.SZ",
            decision_time=START,
            reference_price=Decimal("10"),
            target_return=Decimal("0.05"),
            stop_return=Decimal("0.03"),
            continuation_return=Decimal("0.01"),
            failure_return=Decimal("-0.01"),
            observations=(),
            exit_time=None,
            exit_price=None,
            measured_at=START + timedelta(days=1),
        )


def test_path_outcome_identity_does_not_depend_on_process_decimal_context() -> None:
    arguments = {
        "strategy_version_reference": _reference("STRATEGY_VERSION", "swing-v1"),
        "strategy_run_reference": _reference("STRATEGY_RUN", "run-context"),
        "dataset_reference": _reference("DATASET", "dataset-context"),
        "target_reference": _reference("TARGET_DEFINITION", "swing-context"),
        "symbol": "000001.SZ",
        "decision_time": START,
        "reference_price": Decimal("10"),
        "target_return": Decimal("0.05"),
        "stop_return": Decimal("0.03"),
        "continuation_return": Decimal("0.02"),
        "failure_return": Decimal("-0.02"),
        "observations": (
            _point(1, high="10.30", low="9.90", close="10.20"),
            _point(2, high="10.60", low="10.10", close="10.50"),
        ),
        "exit_time": START + timedelta(days=1),
        "exit_price": Decimal("10.20"),
        "measured_at": START + timedelta(days=3),
    }

    with localcontext() as context:
        context.prec = 8
        low_precision = measure_strategy_path(**arguments)
    with localcontext() as context:
        context.prec = 50
        high_precision = measure_strategy_path(**arguments)

    assert low_precision == high_precision
