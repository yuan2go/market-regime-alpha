from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from market_regime_alpha.application.continuous_research.journal import (
    RuntimeArtifactReference,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.outcome.domain import (
    OutcomeBarrierDirection,
    OutcomeDependencyRole,
    OutcomeMetricKind,
    calculate_market_target_outcome,
)
from market_regime_alpha.strategies.path_outcomes import (
    BarrierOrderingOutcome,
    PathPriceObservation,
    measure_strategy_path,
)
from tests.refoundation.outcome.test_outcome_kernel import (
    CHECKPOINT_A,
    CHECKPOINT_B,
    REFERENCE_ID,
    _bar,
    _checkpoint,
    _dependency,
    _instant,
    _metric,
    _reference,
    _session,
    _target,
)


def _legacy_reference(kind: str, name: str) -> RuntimeArtifactReference:
    digest = canonical_hash({"kind": kind, "name": name})
    return RuntimeArtifactReference(
        kind,
        ArtifactId(f"{name}:{digest[7:]}"),
        digest,
    )


def test_canonical_decimal_kernel_preserves_intended_legacy_path_numerics() -> None:
    first = _checkpoint(
        CHECKPOINT_A,
        ordinal=1,
        local_time=_instant(10).time(),
    )
    terminal = _checkpoint(
        CHECKPOINT_B,
        ordinal=2,
        local_time=_instant(10, 30).time(),
    )
    simple_return = _metric(
        4101,
        ordinal=1,
        kind=OutcomeMetricKind.SIMPLE_RETURN,
    )
    mfe = _metric(
        4102,
        ordinal=2,
        kind=OutcomeMetricKind.MAX_FAVORABLE_EXCURSION,
    )
    mae = _metric(
        4103,
        ordinal=3,
        kind=OutcomeMetricKind.MAX_ADVERSE_EXCURSION,
    )
    upper = _metric(
        4104,
        ordinal=4,
        kind=OutcomeMetricKind.BARRIER_HIT,
        barrier_direction=OutcomeBarrierDirection.UP,
        barrier_threshold=Decimal("0.05"),
    )
    lower = _metric(
        4105,
        ordinal=5,
        kind=OutcomeMetricKind.BARRIER_HIT,
        barrier_direction=OutcomeBarrierDirection.DOWN,
        barrier_threshold=Decimal("0.05"),
    )
    dependencies = []
    dependency_ordinal = 1
    dependencies.extend(
        (
            _dependency(
                4200 + dependency_ordinal,
                ordinal=dependency_ordinal,
                metric=simple_return,
                checkpoint_id=REFERENCE_ID,
                role=OutcomeDependencyRole.REFERENCE,
            ),
            _dependency(
                4200 + dependency_ordinal + 1,
                ordinal=dependency_ordinal + 1,
                metric=simple_return,
                checkpoint_id=CHECKPOINT_B,
                role=OutcomeDependencyRole.OBSERVATION,
            ),
        )
    )
    dependency_ordinal += 2
    for metric in (mfe, mae, upper, lower):
        dependencies.append(
            _dependency(
                4200 + dependency_ordinal,
                ordinal=dependency_ordinal,
                metric=metric,
                checkpoint_id=REFERENCE_ID,
                role=OutcomeDependencyRole.REFERENCE,
            )
        )
        dependency_ordinal += 1
        for checkpoint in (first, terminal):
            dependencies.append(
                _dependency(
                    4200 + dependency_ordinal,
                    ordinal=dependency_ordinal,
                    metric=metric,
                    checkpoint_id=checkpoint.target_checkpoint_id,
                    role=OutcomeDependencyRole.PATH_MEMBER,
                )
            )
            dependency_ordinal += 1
    target = _target(
        checkpoints=(first, terminal),
        metrics=(simple_return, mfe, mae, upper, lower),
        dependencies=tuple(dependencies),
    )
    bars = (
        _bar(
            first,
            ordinal=1,
            event_end=_instant(10),
            open_value="100",
            high_value="106",
            low_value="99",
            close_value="104",
        ),
        _bar(
            terminal,
            ordinal=2,
            event_end=_instant(10, 30),
            open_value="104",
            high_value="107",
            low_value="94",
            close_value="95",
        ),
    )
    canonical = calculate_market_target_outcome(
        target=target,
        reference=_reference(value=Decimal("100")),
        sessions=(_session(),),
        sources=bars,
        observation_cutoff=_instant(10, 30),
        knowledge_cutoff=_instant(10, 31),
    )
    legacy = measure_strategy_path(
        strategy_version_reference=_legacy_reference("STRATEGY_VERSION", "wp10-v1"),
        strategy_run_reference=_legacy_reference("STRATEGY_RUN", "wp10-run"),
        dataset_reference=_legacy_reference("DATASET", "wp10-dataset"),
        target_reference=_legacy_reference("TARGET_DEFINITION", "wp10-target"),
        symbol="000001.SZ",
        decision_time=_instant(9),
        reference_price=Decimal("100"),
        target_return=Decimal("0.05"),
        stop_return=Decimal("0.05"),
        continuation_return=Decimal("0.01"),
        failure_return=Decimal("-0.01"),
        observations=tuple(
            PathPriceObservation(
                observed_at=bar.event_end,
                session_offset=1,
                high=bar.high_value,
                low=bar.low_value,
                close=bar.close_value,
            )
            for bar in bars
        ),
        exit_time=None,
        exit_price=None,
        measured_at=_instant(10, 30) + timedelta(minutes=1),
    )
    by_kind = {item.metric_kind: item for item in canonical.metrics[:3]}
    barrier_values = {
        item.target_metric_definition_id: item
        for item in canonical.metrics
        if item.metric_kind is OutcomeMetricKind.BARRIER_HIT
    }

    assert by_kind[OutcomeMetricKind.SIMPLE_RETURN].decimal_value == (
        legacy.terminal_return
    )
    assert by_kind[OutcomeMetricKind.MAX_FAVORABLE_EXCURSION].decimal_value == (
        legacy.mfe
    )
    assert by_kind[OutcomeMetricKind.MAX_ADVERSE_EXCURSION].decimal_value == legacy.mae
    assert barrier_values[upper.target_metric_definition_id].boolean_value is True
    assert barrier_values[lower.target_metric_definition_id].boolean_value is True
    assert barrier_values[upper.target_metric_definition_id].first_passage_at < (
        barrier_values[lower.target_metric_definition_id].first_passage_at
    )
    assert legacy.barrier_ordering is BarrierOrderingOutcome.TARGET_BEFORE_STOP
