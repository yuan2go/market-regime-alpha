from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from uuid import UUID

import pytest

from market_regime_alpha.outcome.domain import (
    MarketTargetOutcomeIdentityPlan,
    OutcomeCommitmentSnapshot,
    OutcomeRuntimeSnapshot,
    FrozenDecisionReference,
    OutcomeAvailabilityStatus,
    OutcomeBarSource,
    OutcomeBarrierDirection,
    OutcomeCheckpoint,
    OutcomeCompletionRule,
    OutcomeDependencyRole,
    OutcomeFinalityStatus,
    OutcomeGapKind,
    OutcomeGapSource,
    OutcomeMetricDefinition,
    OutcomeMetricDependency,
    OutcomeMetricKind,
    OutcomeReferenceValueStatus,
    OutcomeSessionSource,
    OutcomeStatus,
    OutcomeTargetDefinition,
    OutcomeValueField,
    OutcomeValueType,
    calculate_market_target_outcome,
    build_market_target_outcome_authority,
)


TARGET_ID = UUID("00000000-0000-4000-8000-000000001001")
REFERENCE_ID = UUID("00000000-0000-4000-8000-000000001002")
CHECKPOINT_A = UUID("00000000-0000-4000-8000-000000001003")
CHECKPOINT_B = UUID("00000000-0000-4000-8000-000000001004")
SESSION_ID = UUID("00000000-0000-4000-8000-000000001005")
PRODUCT_ID = UUID("00000000-0000-4000-8000-000000001006")
CAPTURE_ID = UUID("00000000-0000-4000-8000-000000001007")
INSTRUMENT_ID = UUID("00000000-0000-4000-8000-000000001008")
HASH_A = "a" * 64
HASH_B = "b" * 64


def _instant(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 8, 31, hour, minute, tzinfo=UTC)


def _checkpoint(
    checkpoint_id: UUID,
    *,
    ordinal: int,
    local_time: time,
    value_field: OutcomeValueField = OutcomeValueField.CLOSE,
) -> OutcomeCheckpoint:
    return OutcomeCheckpoint(
        target_checkpoint_id=checkpoint_id,
        content_sha256=HASH_A,
        ordinal=ordinal,
        checkpoint_code=f"checkpoint_{ordinal}",
        session_offset=1,
        local_time=local_time,
        timezone_name="UTC",
        timeframe="MINUTE_5",
        price_basis="RAW_UNADJUSTED",
        value_field=value_field,
    )


def _metric(
    metric_id: int,
    *,
    ordinal: int,
    kind: OutcomeMetricKind,
    completion: OutcomeCompletionRule = OutcomeCompletionRule.REQUIRED,
    barrier_direction: OutcomeBarrierDirection | None = None,
    barrier_threshold: Decimal | None = None,
) -> OutcomeMetricDefinition:
    value_type = (
        OutcomeValueType.BOOLEAN
        if kind is OutcomeMetricKind.BARRIER_HIT
        else OutcomeValueType.DECIMAL
    )
    return OutcomeMetricDefinition(
        target_metric_definition_id=UUID(
            f"00000000-0000-4000-8000-{metric_id:012d}"
        ),
        ordinal=ordinal,
        metric_code=f"metric_{ordinal}",
        metric_kind=kind,
        value_type=value_type,
        unit=(
            "BOOLEAN"
            if value_type is OutcomeValueType.BOOLEAN
            else "PRICE"
            if kind is OutcomeMetricKind.OBSERVATION_VALUE
            else "RATIO"
        ),
        completion_rule=completion,
        algorithm_code=kind.value.lower(),
        algorithm_version="1.0.0",
        algorithm_sha256=HASH_A,
        code_artifact_id=UUID("00000000-0000-4000-8000-000000001090"),
        code_content_sha256=HASH_A,
        code_size_bytes=80,
        config_artifact_id=UUID("00000000-0000-4000-8000-000000001091"),
        config_content_sha256=HASH_B,
        config_size_bytes=52,
        content_sha256=HASH_A,
        barrier_direction=barrier_direction,
        barrier_threshold=barrier_threshold,
    )


def _dependency(
    dependency_id: int,
    *,
    ordinal: int,
    metric: OutcomeMetricDefinition,
    checkpoint_id: UUID,
    role: OutcomeDependencyRole,
) -> OutcomeMetricDependency:
    return OutcomeMetricDependency(
        target_metric_dependency_id=UUID(
            f"00000000-0000-4000-8000-{dependency_id:012d}"
        ),
        ordinal=ordinal,
        target_metric_definition_id=metric.target_metric_definition_id,
        target_checkpoint_id=checkpoint_id,
        role=role,
        content_sha256=HASH_B,
    )


def _reference(
    *,
    value: Decimal | None = Decimal("100"),
    status: OutcomeReferenceValueStatus = OutcomeReferenceValueStatus.PRESENT,
) -> FrozenDecisionReference:
    availability = (
        OutcomeAvailabilityStatus.AVAILABLE
        if status is OutcomeReferenceValueStatus.PRESENT
        else OutcomeAvailabilityStatus.UNAVAILABLE
        if status is OutcomeReferenceValueStatus.UNAVAILABLE
        else OutcomeAvailabilityStatus.FAILED
    )
    return FrozenDecisionReference(
        decision_reference_observation_id=REFERENCE_ID,
        content_sha256=HASH_A,
        value_status=status,
        availability_status=availability,
        finality_status=OutcomeFinalityStatus.UNKNOWN,
        decimal_value=value,
    )


def _session() -> OutcomeSessionSource:
    return OutcomeSessionSource(
        session_id=SESSION_ID,
        session_offset=1,
        exchange="SSE",
        session_date=date(2026, 8, 31),
        timezone_name="UTC",
        open_at=_instant(9, 30),
        close_at=_instant(15),
        source_capture_id=CAPTURE_ID,
        provider_product_id=PRODUCT_ID,
        recorded_at=_instant(8),
        known_at=_instant(8),
    )


def _bar(
    checkpoint: OutcomeCheckpoint,
    *,
    ordinal: int,
    event_end: datetime,
    open_value: str,
    high_value: str,
    low_value: str,
    close_value: str,
    known_at: datetime | None = None,
) -> OutcomeBarSource:
    return OutcomeBarSource(
        bar_revision_id=UUID(
            f"00000000-0000-4000-8000-{2000 + ordinal:012d}"
        ),
        target_checkpoint_id=checkpoint.target_checkpoint_id,
        source_ordinal=ordinal,
        provider_product_id=PRODUCT_ID,
        capture_id=CAPTURE_ID,
        instrument_id=INSTRUMENT_ID,
        session_id=SESSION_ID,
        timeframe=checkpoint.timeframe,
        price_basis=checkpoint.price_basis,
        event_start=event_end - timedelta(minutes=5),
        event_end=event_end,
        revision=1,
        recorded_at=event_end,
        known_at=known_at or event_end,
        open_value=Decimal(open_value),
        high_value=Decimal(high_value),
        low_value=Decimal(low_value),
        close_value=Decimal(close_value),
    )


def _target(
    *,
    checkpoints: tuple[OutcomeCheckpoint, ...],
    metrics: tuple[OutcomeMetricDefinition, ...],
    dependencies: tuple[OutcomeMetricDependency, ...],
) -> OutcomeTargetDefinition:
    return OutcomeTargetDefinition(
        target_definition_id=TARGET_ID,
        target_code="wp10_kernel_target",
        version=1,
        content_sha256=HASH_A,
        reference_checkpoint_id=REFERENCE_ID,
        algorithm_code="market_target_outcome",
        algorithm_version="1.0.0",
        algorithm_sha256=HASH_A,
        code_artifact_id=UUID("00000000-0000-4000-8000-000000001090"),
        code_content_sha256=HASH_A,
        code_size_bytes=80,
        config_artifact_id=UUID("00000000-0000-4000-8000-000000001091"),
        config_content_sha256=HASH_B,
        config_size_bytes=52,
        checkpoints=checkpoints,
        metrics=metrics,
        dependencies=dependencies,
    )


def test_kernel_reuses_frozen_reference_for_return_and_observation_value() -> None:
    checkpoint = _checkpoint(CHECKPOINT_A, ordinal=1, local_time=time(10, 30))
    simple_return = _metric(1101, ordinal=1, kind=OutcomeMetricKind.SIMPLE_RETURN)
    observation_value = _metric(
        1102,
        ordinal=2,
        kind=OutcomeMetricKind.OBSERVATION_VALUE,
        completion=OutcomeCompletionRule.OPTIONAL,
    )
    dependencies = (
        _dependency(
            1201,
            ordinal=1,
            metric=simple_return,
            checkpoint_id=REFERENCE_ID,
            role=OutcomeDependencyRole.REFERENCE,
        ),
        _dependency(
            1202,
            ordinal=2,
            metric=simple_return,
            checkpoint_id=CHECKPOINT_A,
            role=OutcomeDependencyRole.OBSERVATION,
        ),
        _dependency(
            1203,
            ordinal=3,
            metric=observation_value,
            checkpoint_id=CHECKPOINT_A,
            role=OutcomeDependencyRole.OBSERVATION,
        ),
    )
    target = _target(
        checkpoints=(checkpoint,),
        metrics=(simple_return, observation_value),
        dependencies=dependencies,
    )
    draft = calculate_market_target_outcome(
        target=target,
        reference=_reference(value=Decimal("100")),
        sessions=(_session(),),
        sources=(
            _bar(
                checkpoint,
                ordinal=1,
                event_end=_instant(10, 30),
                open_value="104",
                high_value="106",
                low_value="103",
                close_value="105",
            ),
        ),
        observation_cutoff=_instant(10, 30),
        knowledge_cutoff=_instant(10, 31),
    )

    by_kind = {item.metric_kind: item for item in draft.metrics}
    assert by_kind[OutcomeMetricKind.SIMPLE_RETURN].decimal_value == Decimal(
        "0.050000000000000000"
    )
    assert by_kind[OutcomeMetricKind.OBSERVATION_VALUE].decimal_value == Decimal(
        "105"
    )
    assert draft.status is OutcomeStatus.COMPLETE
    assert draft.availability_status is OutcomeAvailabilityStatus.AVAILABLE
    assert draft.finality_status is OutcomeFinalityStatus.UNKNOWN


def test_calculated_fact_models_reject_internally_inconsistent_state_shapes() -> None:
    checkpoint = _checkpoint(CHECKPOINT_A, ordinal=1, local_time=time(10, 30))
    metric = _metric(
        1710,
        ordinal=1,
        kind=OutcomeMetricKind.SIMPLE_RETURN,
    )
    target = _target(
        checkpoints=(checkpoint,),
        metrics=(metric,),
        dependencies=(
            _dependency(
                1711,
                ordinal=1,
                metric=metric,
                checkpoint_id=REFERENCE_ID,
                role=OutcomeDependencyRole.REFERENCE,
            ),
            _dependency(
                1712,
                ordinal=2,
                metric=metric,
                checkpoint_id=CHECKPOINT_A,
                role=OutcomeDependencyRole.OBSERVATION,
            ),
        ),
    )
    draft = calculate_market_target_outcome(
        target=target,
        reference=_reference(),
        sessions=(_session(),),
        sources=(
            _bar(
                checkpoint,
                ordinal=1,
                event_end=_instant(10, 30),
                open_value="100",
                high_value="102",
                low_value="99",
                close_value="101",
            ),
        ),
        observation_cutoff=_instant(10, 30),
        knowledge_cutoff=_instant(10, 31),
    )

    with pytest.raises(ValueError, match="observation state shape"):
        replace(
            draft.observations[0],
            availability_status=OutcomeAvailabilityStatus.UNAVAILABLE,
        )
    with pytest.raises(ValueError, match="metric state shape"):
        replace(draft.metrics[0], decimal_value=None)
    with pytest.raises(ValueError, match="REFERENCE dependency role"):
        replace(
            draft.reference_dependencies[0],
            dependency_role=OutcomeDependencyRole.OBSERVATION,
        )
    with pytest.raises(ValueError, match="aggregate state shape"):
        replace(
            draft,
            availability_status=OutcomeAvailabilityStatus.UNAVAILABLE,
        )
    assert {item.dependency_role for item in draft.reference_dependencies} == {
        OutcomeDependencyRole.REFERENCE
    }


def test_authority_builder_closes_id_bearing_rosters_and_runtime_identity() -> None:
    checkpoint = _checkpoint(CHECKPOINT_A, ordinal=1, local_time=time(10, 30))
    metric = _metric(2101, ordinal=1, kind=OutcomeMetricKind.SIMPLE_RETURN)
    target = _target(
        checkpoints=(checkpoint,),
        metrics=(metric,),
        dependencies=(
            _dependency(
                2201,
                ordinal=1,
                metric=metric,
                checkpoint_id=REFERENCE_ID,
                role=OutcomeDependencyRole.REFERENCE,
            ),
            _dependency(
                2202,
                ordinal=2,
                metric=metric,
                checkpoint_id=CHECKPOINT_A,
                role=OutcomeDependencyRole.OBSERVATION,
            ),
        ),
    )
    reference = _reference()
    draft = calculate_market_target_outcome(
        target=target,
        reference=reference,
        sessions=(_session(),),
        sources=(
            _bar(
                checkpoint,
                ordinal=1,
                event_end=_instant(10, 30),
                open_value="99",
                high_value="106",
                low_value="98",
                close_value="105",
            ),
        ),
        observation_cutoff=_instant(10, 30),
        knowledge_cutoff=_instant(10, 31),
    )
    commitment = OutcomeCommitmentSnapshot(
        commitment_id=UUID("00000000-0000-4000-8000-000000002301"),
        decision_run_id=UUID("00000000-0000-4000-8000-000000002302"),
        decision_run_target_id=UUID("00000000-0000-4000-8000-000000002303"),
        candidate_set_id=UUID("00000000-0000-4000-8000-000000002304"),
        candidate_id=UUID("00000000-0000-4000-8000-000000002305"),
        instrument_id=INSTRUMENT_ID,
        target_definition_id=TARGET_ID,
        target_version=1,
        target_definition_sha256=HASH_A,
        target_checkpoint_id=REFERENCE_ID,
        reference_provider_product_id=PRODUCT_ID,
        reference_capture_id=CAPTURE_ID,
        reference_session_id=SESSION_ID,
        reference_source_kind="BAR_REVISION",
        reference_fact_id=UUID("00000000-0000-4000-8000-000000002306"),
        reference_known_at=_instant(9),
        decision_time=_instant(9),
        runtime_mode="HISTORICAL",
        commitment_recorded_at=_instant(9, 1),
        reference=reference,
    )
    runtime = OutcomeRuntimeSnapshot(
        run_id=UUID("00000000-0000-4000-8000-000000002311"),
        step_id=UUID("00000000-0000-4000-8000-000000002312"),
        attempt_id=UUID("00000000-0000-4000-8000-000000002313"),
        fence_token=1,
        step_key="settle-outcome",
        step_kind="SETTLE_OUTCOME",
        runtime_mode="HISTORICAL",
        decision_time=_instant(9),
        code_sha="c" * 40,
        config_artifact_id=UUID("00000000-0000-4000-8000-000000002314"),
        config_hash=HASH_B,
    )
    next_id = iter(
        UUID(f"00000000-0000-4000-8000-{value:012d}")
        for value in range(2401, 2420)
    ).__next__
    identities = MarketTargetOutcomeIdentityPlan.create(draft, next_id)
    authority = build_market_target_outcome_authority(
        identities=identities,
        commitment=commitment,
        target=target,
        draft=draft,
        runtime=runtime,
        revision_ordinal=1,
        supersedes_revision_id=None,
        request_identity="settle-authority-1",
        request_sha256=HASH_A,
        request_received_at=_instant(10, 31),
        settled_at=_instant(10, 32),
        command_receipt_id=UUID("00000000-0000-4000-8000-000000002399"),
        actor_type="WORKER",
        actor_id="wp10-test",
        reason_code="SETTLE_DUE_OUTCOME",
    )

    assert authority.revision.revision_ordinal == 1
    assert authority.revision.source_count == 2
    assert authority.revision.observation_count == 1
    assert authority.revision.metric_count == 1
    assert authority.revision.reference_dependency_count == 1
    assert authority.revision.observation_dependency_count == 1
    assert authority.revision.source_roster_sha256 != draft.source_roster_sha256
    assert authority.revision.definition_summary_sha256 != HASH_A
    assert authority.revision.runtime == runtime
    assert authority.root.decision_reference_observation_id == REFERENCE_ID


def test_kernel_calculates_clamped_excursions_and_first_passage() -> None:
    first = _checkpoint(CHECKPOINT_A, ordinal=1, local_time=time(10, 0))
    second = _checkpoint(CHECKPOINT_B, ordinal=2, local_time=time(10, 30))
    mfe = _metric(1301, ordinal=1, kind=OutcomeMetricKind.MAX_FAVORABLE_EXCURSION)
    mae = _metric(1302, ordinal=2, kind=OutcomeMetricKind.MAX_ADVERSE_EXCURSION)
    up = _metric(
        1303,
        ordinal=3,
        kind=OutcomeMetricKind.BARRIER_HIT,
        barrier_direction=OutcomeBarrierDirection.UP,
        barrier_threshold=Decimal("0.05"),
    )
    dependencies: list[OutcomeMetricDependency] = []
    ordinal = 1
    for metric in (mfe, mae, up):
        dependencies.append(
            _dependency(
                1400 + ordinal,
                ordinal=ordinal,
                metric=metric,
                checkpoint_id=REFERENCE_ID,
                role=OutcomeDependencyRole.REFERENCE,
            )
        )
        ordinal += 1
        for checkpoint in (first, second):
            dependencies.append(
                _dependency(
                    1400 + ordinal,
                    ordinal=ordinal,
                    metric=metric,
                    checkpoint_id=checkpoint.target_checkpoint_id,
                    role=OutcomeDependencyRole.PATH_MEMBER,
                )
            )
            ordinal += 1
    target = _target(
        checkpoints=(first, second),
        metrics=(mfe, mae, up),
        dependencies=tuple(dependencies),
    )
    draft = calculate_market_target_outcome(
        target=target,
        reference=_reference(),
        sessions=(_session(),),
        sources=(
            _bar(
                first,
                ordinal=1,
                event_end=_instant(10),
                open_value="99",
                high_value="104",
                low_value="98",
                close_value="101",
            ),
            _bar(
                second,
                ordinal=2,
                event_end=_instant(10, 30),
                open_value="101",
                high_value="108",
                low_value="96",
                close_value="107",
            ),
        ),
        observation_cutoff=_instant(10, 30),
        knowledge_cutoff=_instant(10, 31),
    )
    by_kind = {item.metric_kind: item for item in draft.metrics}
    assert by_kind[OutcomeMetricKind.MAX_FAVORABLE_EXCURSION].decimal_value == Decimal(
        "0.080000000000000000"
    )
    assert by_kind[OutcomeMetricKind.MAX_ADVERSE_EXCURSION].decimal_value == Decimal(
        "-0.040000000000000000"
    )
    barrier = by_kind[OutcomeMetricKind.BARRIER_HIT]
    assert barrier.boolean_value is True
    assert barrier.first_passage_at == _instant(10, 30)


def test_kernel_preserves_intrabar_barrier_ambiguity_without_hiding_hits() -> None:
    checkpoint = _checkpoint(CHECKPOINT_A, ordinal=1, local_time=time(10, 30))
    up = _metric(
        1501,
        ordinal=1,
        kind=OutcomeMetricKind.BARRIER_HIT,
        barrier_direction=OutcomeBarrierDirection.UP,
        barrier_threshold=Decimal("0.05"),
    )
    down = _metric(
        1502,
        ordinal=2,
        kind=OutcomeMetricKind.BARRIER_HIT,
        barrier_direction=OutcomeBarrierDirection.DOWN,
        barrier_threshold=Decimal("0.05"),
    )
    dependencies: list[OutcomeMetricDependency] = []
    for ordinal, metric in enumerate((up, down), start=1):
        dependencies.extend(
            (
                _dependency(
                    1600 + ordinal * 2,
                    ordinal=ordinal * 2 - 1,
                    metric=metric,
                    checkpoint_id=REFERENCE_ID,
                    role=OutcomeDependencyRole.REFERENCE,
                ),
                _dependency(
                    1601 + ordinal * 2,
                    ordinal=ordinal * 2,
                    metric=metric,
                    checkpoint_id=CHECKPOINT_A,
                    role=OutcomeDependencyRole.PATH_MEMBER,
                ),
            )
        )
    draft = calculate_market_target_outcome(
        target=_target(
            checkpoints=(checkpoint,),
            metrics=(up, down),
            dependencies=tuple(dependencies),
        ),
        reference=_reference(),
        sessions=(_session(),),
        sources=(
            _bar(
                checkpoint,
                ordinal=1,
                event_end=_instant(10, 30),
                open_value="100",
                high_value="106",
                low_value="94",
                close_value="101",
            ),
        ),
        observation_cutoff=_instant(10, 30),
        knowledge_cutoff=_instant(10, 31),
    )
    assert {item.boolean_value for item in draft.metrics} == {True}
    assert {item.status for item in draft.metrics} == {OutcomeStatus.PARTIAL}
    assert draft.status is OutcomeStatus.PARTIAL
    assert draft.availability_status is OutcomeAvailabilityStatus.AVAILABLE
    assert "INTRABAR_ORDERING_NOT_OBSERVABLE" in {
        item.reason_code for item in draft.reasons
    }


@pytest.mark.parametrize(
    ("gap_kind", "expected_status", "expected_availability"),
    (
        (
            OutcomeGapKind.MISSING,
            OutcomeStatus.UNAVAILABLE,
            OutcomeAvailabilityStatus.UNAVAILABLE,
        ),
        (
            OutcomeGapKind.PROVIDER_FAILURE,
            OutcomeStatus.FAILED,
            OutcomeAvailabilityStatus.FAILED,
        ),
    ),
)
def test_exact_source_gap_propagates_without_zero_fallback(
    gap_kind: OutcomeGapKind,
    expected_status: OutcomeStatus,
    expected_availability: OutcomeAvailabilityStatus,
) -> None:
    checkpoint = _checkpoint(CHECKPOINT_A, ordinal=1, local_time=time(10, 30))
    metric = _metric(1701, ordinal=1, kind=OutcomeMetricKind.SIMPLE_RETURN)
    target = _target(
        checkpoints=(checkpoint,),
        metrics=(metric,),
        dependencies=(
            _dependency(
                1801,
                ordinal=1,
                metric=metric,
                checkpoint_id=REFERENCE_ID,
                role=OutcomeDependencyRole.REFERENCE,
            ),
            _dependency(
                1802,
                ordinal=2,
                metric=metric,
                checkpoint_id=CHECKPOINT_A,
                role=OutcomeDependencyRole.OBSERVATION,
            ),
        ),
    )
    gap = OutcomeGapSource(
        gap_id=UUID("00000000-0000-4000-8000-000000001801"),
        target_checkpoint_id=CHECKPOINT_A,
        source_ordinal=1,
        provider_product_id=PRODUCT_ID,
        capture_id=CAPTURE_ID,
        instrument_id=INSTRUMENT_ID,
        session_id=SESSION_ID,
        timeframe="MINUTE_5",
        price_basis="RAW_UNADJUSTED",
        event_start=_instant(10, 25),
        event_end=_instant(10, 30),
        gap_kind=gap_kind,
        reason_code=(
            "EXACT_BAR_MISSING"
            if gap_kind is OutcomeGapKind.MISSING
            else "PROVIDER_FAILURE"
        ),
        recorded_at=_instant(10, 30),
        known_at=_instant(10, 30),
    )
    draft = calculate_market_target_outcome(
        target=target,
        reference=_reference(),
        sessions=(_session(),),
        sources=(gap,),
        observation_cutoff=_instant(10, 30),
        knowledge_cutoff=_instant(10, 31),
    )
    assert draft.status is expected_status
    assert draft.availability_status is expected_availability
    assert draft.observations[0].selected_value is None
    assert draft.metrics[0].decimal_value is None


def test_kernel_rejects_later_known_or_after_observation_cutoff_sources() -> None:
    checkpoint = _checkpoint(CHECKPOINT_A, ordinal=1, local_time=time(10, 30))
    metric = _metric(1901, ordinal=1, kind=OutcomeMetricKind.OBSERVATION_VALUE)
    target = _target(
        checkpoints=(checkpoint,),
        metrics=(metric,),
        dependencies=(
            _dependency(
                1902,
                ordinal=1,
                metric=metric,
                checkpoint_id=CHECKPOINT_A,
                role=OutcomeDependencyRole.OBSERVATION,
            ),
        ),
    )
    late = _bar(
        checkpoint,
        ordinal=1,
        event_end=_instant(10, 30),
        open_value="100",
        high_value="101",
        low_value="99",
        close_value="100",
        known_at=_instant(11),
    )
    with pytest.raises(ValueError, match="knowledge_cutoff"):
        calculate_market_target_outcome(
            target=target,
            reference=_reference(),
            sessions=(_session(),),
            sources=(late,),
            observation_cutoff=_instant(10, 30),
            knowledge_cutoff=_instant(10, 31),
        )
    with pytest.raises(ValueError, match="observation_cutoff"):
        calculate_market_target_outcome(
            target=target,
            reference=_reference(),
            sessions=(_session(),),
            sources=(late,),
            observation_cutoff=_instant(10),
            knowledge_cutoff=_instant(11),
        )


def test_optional_metric_failure_does_not_inflate_or_block_required_completion() -> None:
    required_checkpoint = _checkpoint(
        CHECKPOINT_A, ordinal=1, local_time=time(10)
    )
    optional_checkpoint = _checkpoint(
        CHECKPOINT_B, ordinal=2, local_time=time(10, 30)
    )
    required = _metric(2001, ordinal=1, kind=OutcomeMetricKind.SIMPLE_RETURN)
    optional = _metric(
        2002,
        ordinal=2,
        kind=OutcomeMetricKind.OBSERVATION_VALUE,
        completion=OutcomeCompletionRule.OPTIONAL,
    )
    target = _target(
        checkpoints=(required_checkpoint, optional_checkpoint),
        metrics=(required, optional),
        dependencies=(
            _dependency(
                2011,
                ordinal=1,
                metric=required,
                checkpoint_id=REFERENCE_ID,
                role=OutcomeDependencyRole.REFERENCE,
            ),
            _dependency(
                2012,
                ordinal=2,
                metric=required,
                checkpoint_id=CHECKPOINT_A,
                role=OutcomeDependencyRole.OBSERVATION,
            ),
            _dependency(
                2013,
                ordinal=3,
                metric=optional,
                checkpoint_id=CHECKPOINT_B,
                role=OutcomeDependencyRole.OBSERVATION,
            ),
        ),
    )
    optional_gap = OutcomeGapSource(
        gap_id=UUID("00000000-0000-4000-8000-000000002013"),
        target_checkpoint_id=CHECKPOINT_B,
        source_ordinal=2,
        provider_product_id=PRODUCT_ID,
        capture_id=CAPTURE_ID,
        instrument_id=INSTRUMENT_ID,
        session_id=SESSION_ID,
        timeframe="MINUTE_5",
        price_basis="RAW_UNADJUSTED",
        event_start=_instant(10, 25),
        event_end=_instant(10, 30),
        gap_kind=OutcomeGapKind.MISSING,
        reason_code="EXACT_BAR_MISSING",
        recorded_at=_instant(10, 30),
        known_at=_instant(10, 30),
    )
    draft = calculate_market_target_outcome(
        target=target,
        reference=_reference(),
        sessions=(_session(),),
        sources=(
            _bar(
                required_checkpoint,
                ordinal=1,
                event_end=_instant(10),
                open_value="100",
                high_value="102",
                low_value="99",
                close_value="101",
            ),
            optional_gap,
        ),
        observation_cutoff=_instant(10, 30),
        knowledge_cutoff=_instant(10, 31),
    )
    assert draft.status is OutcomeStatus.COMPLETE
    assert draft.availability_status is OutcomeAvailabilityStatus.AVAILABLE
    optional_result = next(
        item for item in draft.metrics if item.completion_rule is OutcomeCompletionRule.OPTIONAL
    )
    assert optional_result.status is OutcomeStatus.UNAVAILABLE
