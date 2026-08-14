from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal, localcontext

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
