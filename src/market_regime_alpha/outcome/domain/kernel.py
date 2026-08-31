"""Pure Decimal numerical kernel for Market Target Outcome revisions."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext
from uuid import UUID
from zoneinfo import ZoneInfo

from market_regime_alpha.outcome.domain.model import (
    FrozenDecisionReference,
    OutcomeBarSource,
    OutcomeMetricDefinition,
    OutcomeMetricDependency,
    OutcomeMetricDraft,
    OutcomeObservationDependencyDraft,
    OutcomeObservationDraft,
    OutcomeObservationSource,
    OutcomeCheckpoint,
    OutcomeReasonDraft,
    OutcomeReferenceDependencyDraft,
    OutcomeRevisionDraft,
    OutcomeSessionSource,
    OutcomeTargetDefinition,
)
from market_regime_alpha.outcome.domain.vocabulary import (
    OutcomeAvailabilityStatus,
    OutcomeBarrierDirection,
    OutcomeCompletionRule,
    OutcomeDependencyRole,
    OutcomeFinalityStatus,
    OutcomeGapKind,
    OutcomeMetricKind,
    OutcomeReasonDimension,
    OutcomeReferenceValueStatus,
    OutcomeSourceKind,
    OutcomeStatus,
    OutcomeValueField,
)


_CONTEXT = Context(prec=38, rounding=ROUND_HALF_EVEN)
_RATIO_QUANTUM = Decimal("0.000000000000000001")


def calculate_market_target_outcome(
    *,
    target: OutcomeTargetDefinition,
    reference: FrozenDecisionReference,
    sessions: tuple[OutcomeSessionSource, ...],
    sources: tuple[OutcomeObservationSource, ...],
    observation_cutoff: datetime,
    knowledge_cutoff: datetime,
) -> OutcomeRevisionDraft:
    """Calculate one full immutable draft without any I/O or mutable state."""

    _aware(observation_cutoff, "observation_cutoff")
    _aware(knowledge_cutoff, "knowledge_cutoff")
    with localcontext(_CONTEXT):
        _validate_inputs(
            target=target,
            sessions=sessions,
            sources=sources,
            observation_cutoff=observation_cutoff,
            knowledge_cutoff=knowledge_cutoff,
        )
        observations = tuple(
            _observation(checkpoint, source)
            for checkpoint, source in zip(target.checkpoints, sources, strict=True)
        )
        observations_by_checkpoint = {
            item.target_checkpoint_id: item for item in observations
        }
        dependencies_by_metric = {
            metric.target_metric_definition_id: tuple(
                dependency
                for dependency in target.dependencies
                if dependency.target_metric_definition_id
                == metric.target_metric_definition_id
            )
            for metric in target.metrics
        }
        metrics = tuple(
            _metric(
                metric,
                dependencies=dependencies_by_metric[
                    metric.target_metric_definition_id
                ],
                observations=observations_by_checkpoint,
                reference=reference,
            )
            for metric in target.metrics
        )
        metrics, ambiguity_reasons = _apply_barrier_ambiguity(target, metrics)
        reference_dependencies = tuple(
            OutcomeReferenceDependencyDraft(
                target_metric_dependency_id=item.target_metric_dependency_id,
                target_metric_definition_id=item.target_metric_definition_id,
                target_checkpoint_id=item.target_checkpoint_id,
                dependency_role=item.role,
                decision_reference_observation_id=(
                    reference.decision_reference_observation_id
                ),
            )
            for item in target.dependencies
            if item.role is OutcomeDependencyRole.REFERENCE
        )
        observation_dependencies = tuple(
            OutcomeObservationDependencyDraft(
                target_metric_dependency_id=item.target_metric_dependency_id,
                target_metric_definition_id=item.target_metric_definition_id,
                target_checkpoint_id=item.target_checkpoint_id,
                dependency_role=item.role,
            )
            for item in target.dependencies
            if item.role
            in {OutcomeDependencyRole.OBSERVATION, OutcomeDependencyRole.PATH_MEMBER}
        )
        reasons = _reasons(observations, metrics, ambiguity_reasons)
        status, availability = _roll_up(metrics)
        return OutcomeRevisionDraft(
            target_definition_id=target.target_definition_id,
            target_definition_sha256=target.content_sha256,
            decision_reference_observation_id=(
                reference.decision_reference_observation_id
            ),
            decision_reference_sha256=reference.content_sha256,
            observation_cutoff=observation_cutoff,
            knowledge_cutoff=knowledge_cutoff,
            status=status,
            availability_status=availability,
            finality_status=OutcomeFinalityStatus.UNKNOWN,
            sessions=sessions,
            sources=sources,
            observations=observations,
            metrics=metrics,
            reference_dependencies=reference_dependencies,
            observation_dependencies=observation_dependencies,
            reasons=reasons,
        )


def _validate_inputs(
    *,
    target: OutcomeTargetDefinition,
    sessions: tuple[OutcomeSessionSource, ...],
    sources: tuple[OutcomeObservationSource, ...],
    observation_cutoff: datetime,
    knowledge_cutoff: datetime,
) -> None:
    session_by_offset = {item.session_offset: item for item in sessions}
    if len(session_by_offset) != len(sessions):
        raise ValueError("Outcome Session offsets must be unique")
    required_offsets = {item.session_offset for item in target.checkpoints}
    if set(session_by_offset) != required_offsets:
        raise ValueError("Outcome Session roster does not match Target checkpoints")
    if len(sources) != len(target.checkpoints):
        raise ValueError("Outcome source roster must cover every checkpoint")
    source_by_checkpoint = {item.target_checkpoint_id: item for item in sources}
    if len(source_by_checkpoint) != len(sources) or set(source_by_checkpoint) != {
        item.target_checkpoint_id for item in target.checkpoints
    }:
        raise ValueError("Outcome source/checkpoint roster mismatch")
    if tuple(item.source_ordinal for item in sources) != tuple(
        range(1, len(sources) + 1)
    ):
        raise ValueError("Outcome source ordinals must be contiguous")
    ordered = tuple(source_by_checkpoint[item.target_checkpoint_id] for item in target.checkpoints)
    if ordered != sources:
        raise ValueError("Outcome sources must follow Target checkpoint order")
    for session in sessions:
        if session.known_at > knowledge_cutoff:
            raise ValueError("Outcome Session known_at exceeds knowledge_cutoff")
    for checkpoint, source in zip(target.checkpoints, sources, strict=True):
        session = session_by_offset[checkpoint.session_offset]
        expected_end = datetime.combine(
            session.session_date,
            checkpoint.local_time,
            ZoneInfo(checkpoint.timezone_name),
        ).astimezone(source.event_end.tzinfo)
        if source.event_end != expected_end:
            raise ValueError("Outcome source event_end differs from Target checkpoint")
        if source.event_end > observation_cutoff:
            raise ValueError("Outcome source exceeds observation_cutoff")
        if source.known_at > knowledge_cutoff:
            raise ValueError("Outcome source exceeds knowledge_cutoff")
        if (
            source.session_id != session.session_id
            or source.timeframe != checkpoint.timeframe
            or source.price_basis != checkpoint.price_basis
        ):
            raise ValueError("Outcome source scope differs from Target/Session")
    if sources:
        instrument_ids = {item.instrument_id for item in sources}
        provider_products = {item.provider_product_id for item in sources}
        if len(instrument_ids) != 1 or len(provider_products) != 1:
            raise ValueError("Outcome source roster crosses instrument/Product scope")


def _observation(
    checkpoint: OutcomeCheckpoint,
    source: OutcomeObservationSource,
) -> OutcomeObservationDraft:
    # Target is validated before dispatch; the local annotation avoids coupling
    # this pure helper to a repository or external model.
    target_checkpoint_id = source.target_checkpoint_id
    if isinstance(source, OutcomeBarSource):
        selected = {
            OutcomeValueField.OPEN: source.open_value,
            OutcomeValueField.HIGH: source.high_value,
            OutcomeValueField.LOW: source.low_value,
            OutcomeValueField.CLOSE: source.close_value,
        }[checkpoint.value_field]
        return OutcomeObservationDraft(
            target_checkpoint_id=target_checkpoint_id,
            source_kind=OutcomeSourceKind.BAR_REVISION,
            source_fact_id=source.bar_revision_id,
            status=OutcomeStatus.COMPLETE,
            availability_status=OutcomeAvailabilityStatus.AVAILABLE,
            finality_status=OutcomeFinalityStatus.UNKNOWN,
            selected_value=selected,
            open_value=source.open_value,
            high_value=source.high_value,
            low_value=source.low_value,
            close_value=source.close_value,
            event_start=source.event_start,
            event_end=source.event_end,
            known_at=source.known_at,
        )
    status = (
        OutcomeStatus.UNAVAILABLE
        if source.gap_kind in {OutcomeGapKind.MISSING, OutcomeGapKind.PLACEHOLDER}
        else OutcomeStatus.FAILED
    )
    availability = (
        OutcomeAvailabilityStatus.UNAVAILABLE
        if status is OutcomeStatus.UNAVAILABLE
        else OutcomeAvailabilityStatus.FAILED
    )
    return OutcomeObservationDraft(
        target_checkpoint_id=target_checkpoint_id,
        source_kind=OutcomeSourceKind.SOURCE_GAP,
        source_fact_id=source.gap_id,
        status=status,
        availability_status=availability,
        finality_status=OutcomeFinalityStatus.UNKNOWN,
        selected_value=None,
        open_value=None,
        high_value=None,
        low_value=None,
        close_value=None,
        event_start=source.event_start,
        event_end=source.event_end,
        known_at=source.known_at,
    )


def _metric(
    definition: OutcomeMetricDefinition,
    *,
    dependencies: tuple[OutcomeMetricDependency, ...],
    observations: dict[UUID, OutcomeObservationDraft],
    reference: FrozenDecisionReference,
) -> OutcomeMetricDraft:
    dependency_observations = tuple(
        observations[item.target_checkpoint_id]
        for item in dependencies
        if item.role in {OutcomeDependencyRole.OBSERVATION, OutcomeDependencyRole.PATH_MEMBER}
    )
    needs_reference = any(
        item.role is OutcomeDependencyRole.REFERENCE
        for item in dependencies
    )
    dependency_states = [item.status for item in dependency_observations]
    if needs_reference:
        dependency_states.append(_reference_status(reference))
    if OutcomeStatus.FAILED in dependency_states:
        return _empty_metric(definition, OutcomeStatus.FAILED)
    if any(item is not OutcomeStatus.COMPLETE for item in dependency_states):
        return _empty_metric(definition, OutcomeStatus.UNAVAILABLE)
    reference_value = reference.decimal_value
    decimal_value: Decimal | None = None
    boolean_value: bool | None = None
    first_passage_at: datetime | None = None
    if definition.metric_kind is OutcomeMetricKind.OBSERVATION_VALUE:
        decimal_value = dependency_observations[0].selected_value
    elif definition.metric_kind is OutcomeMetricKind.SIMPLE_RETURN:
        assert reference_value is not None
        observed = dependency_observations[0].selected_value
        assert observed is not None
        decimal_value = _ratio(observed / reference_value - Decimal("1"))
    elif definition.metric_kind is OutcomeMetricKind.MAX_FAVORABLE_EXCURSION:
        assert reference_value is not None
        highs = tuple(item.high_value for item in dependency_observations)
        assert all(item is not None for item in highs)
        decimal_value = _ratio(
            max(
                Decimal("0"),
                max(item for item in highs if item is not None) / reference_value
                - Decimal("1"),
            )
        )
    elif definition.metric_kind is OutcomeMetricKind.MAX_ADVERSE_EXCURSION:
        assert reference_value is not None
        lows = tuple(item.low_value for item in dependency_observations)
        assert all(item is not None for item in lows)
        decimal_value = _ratio(
            min(
                Decimal("0"),
                min(item for item in lows if item is not None) / reference_value
                - Decimal("1"),
            )
        )
    else:
        assert definition.metric_kind is OutcomeMetricKind.BARRIER_HIT
        assert reference_value is not None
        assert definition.barrier_direction is not None
        assert definition.barrier_threshold is not None
        boundary = reference_value * (
            Decimal("1") + definition.barrier_threshold
            if definition.barrier_direction is OutcomeBarrierDirection.UP
            else Decimal("1") - definition.barrier_threshold
        )
        ordered = tuple(sorted(dependency_observations, key=lambda item: item.event_end))
        hits = tuple(
            item
            for item in ordered
            if (
                definition.barrier_direction is OutcomeBarrierDirection.UP
                and item.high_value is not None
                and item.high_value >= boundary
            )
            or (
                definition.barrier_direction is OutcomeBarrierDirection.DOWN
                and item.low_value is not None
                and item.low_value <= boundary
            )
        )
        boolean_value = bool(hits)
        first_passage_at = None if not hits else hits[0].event_end
    return _metric_result(
        definition,
        status=OutcomeStatus.COMPLETE,
        decimal_value=decimal_value,
        boolean_value=boolean_value,
        first_passage_at=first_passage_at,
    )


def _reference_status(reference: FrozenDecisionReference) -> OutcomeStatus:
    return {
        OutcomeReferenceValueStatus.PRESENT: OutcomeStatus.COMPLETE,
        OutcomeReferenceValueStatus.UNAVAILABLE: OutcomeStatus.UNAVAILABLE,
        OutcomeReferenceValueStatus.FAILED: OutcomeStatus.FAILED,
    }[reference.value_status]


def _empty_metric(
    definition: OutcomeMetricDefinition,
    status: OutcomeStatus,
) -> OutcomeMetricDraft:
    availability = (
        OutcomeAvailabilityStatus.UNAVAILABLE
        if status is OutcomeStatus.UNAVAILABLE
        else OutcomeAvailabilityStatus.FAILED
    )
    return _metric_result(
        definition,
        status=status,
        availability=availability,
        decimal_value=None,
        boolean_value=None,
        first_passage_at=None,
    )


def _metric_result(
    definition: OutcomeMetricDefinition,
    *,
    status: OutcomeStatus,
    decimal_value: Decimal | None,
    boolean_value: bool | None,
    first_passage_at: datetime | None,
    availability: OutcomeAvailabilityStatus = OutcomeAvailabilityStatus.AVAILABLE,
) -> OutcomeMetricDraft:
    return OutcomeMetricDraft(
        target_metric_definition_id=definition.target_metric_definition_id,
        ordinal=definition.ordinal,
        metric_code=definition.metric_code,
        metric_kind=definition.metric_kind,
        value_type=definition.value_type,
        unit=definition.unit,
        completion_rule=definition.completion_rule,
        status=status,
        availability_status=availability,
        finality_status=OutcomeFinalityStatus.UNKNOWN,
        decimal_value=decimal_value,
        boolean_value=boolean_value,
        first_passage_at=first_passage_at,
        algorithm_code=definition.algorithm_code,
        algorithm_version=definition.algorithm_version,
        algorithm_sha256=definition.algorithm_sha256,
        code_artifact_id=definition.code_artifact_id,
        code_content_sha256=definition.code_content_sha256,
        code_size_bytes=definition.code_size_bytes,
        config_artifact_id=definition.config_artifact_id,
        config_content_sha256=definition.config_content_sha256,
        config_size_bytes=definition.config_size_bytes,
        target_metric_sha256=definition.content_sha256,
    )


def _apply_barrier_ambiguity(
    target: OutcomeTargetDefinition,
    metrics: tuple[OutcomeMetricDraft, ...],
) -> tuple[tuple[OutcomeMetricDraft, ...], tuple[UUID, ...]]:
    definition_by_id = {
        item.target_metric_definition_id: item for item in target.metrics
    }
    up = tuple(
        item
        for item in metrics
        if item.metric_kind is OutcomeMetricKind.BARRIER_HIT
        and definition_by_id[item.target_metric_definition_id].barrier_direction
        is OutcomeBarrierDirection.UP
        and item.first_passage_at is not None
    )
    down = tuple(
        item
        for item in metrics
        if item.metric_kind is OutcomeMetricKind.BARRIER_HIT
        and definition_by_id[item.target_metric_definition_id].barrier_direction
        is OutcomeBarrierDirection.DOWN
        and item.first_passage_at is not None
    )
    if not up or not down:
        return metrics, ()
    first_up = min(item.first_passage_at for item in up if item.first_passage_at)
    first_down = min(item.first_passage_at for item in down if item.first_passage_at)
    if first_up != first_down:
        return metrics, ()
    affected = {
        item.target_metric_definition_id
        for item in (*up, *down)
        if item.first_passage_at == first_up
    }
    return (
        tuple(
            replace(item, status=OutcomeStatus.PARTIAL)
            if item.target_metric_definition_id in affected
            else item
            for item in metrics
        ),
        tuple(sorted(affected, key=str)),
    )


def _reasons(
    observations: tuple[OutcomeObservationDraft, ...],
    metrics: tuple[OutcomeMetricDraft, ...],
    ambiguous_metric_ids: tuple[UUID, ...],
) -> tuple[OutcomeReasonDraft, ...]:
    values: list[tuple[OutcomeReasonDimension, str, UUID | None, UUID | None]] = []
    for observation in observations:
        if observation.status is not OutcomeStatus.COMPLETE:
            values.append(
                (
                    OutcomeReasonDimension.OBSERVATION,
                    f"OBSERVATION_{observation.status.value}",
                    observation.target_checkpoint_id,
                    None,
                )
            )
    for metric in metrics:
        if metric.status is not OutcomeStatus.COMPLETE:
            values.append(
                (
                    OutcomeReasonDimension.METRIC,
                    f"METRIC_{metric.status.value}",
                    None,
                    metric.target_metric_definition_id,
                )
            )
    for metric_id in ambiguous_metric_ids:
        values.append(
            (
                OutcomeReasonDimension.METRIC,
                "INTRABAR_ORDERING_NOT_OBSERVABLE",
                None,
                metric_id,
            )
        )
    ordered = tuple(
        sorted(
            set(values),
            key=lambda item: (
                item[0].value,
                item[1],
                "" if item[2] is None else str(item[2]),
                "" if item[3] is None else str(item[3]),
            ),
        )
    )
    return tuple(
        OutcomeReasonDraft(
            ordinal=ordinal,
            dimension=item[0],
            reason_code=item[1],
            target_checkpoint_id=item[2],
            target_metric_definition_id=item[3],
        )
        for ordinal, item in enumerate(ordered, start=1)
    )


def _roll_up(
    metrics: tuple[OutcomeMetricDraft, ...],
) -> tuple[OutcomeStatus, OutcomeAvailabilityStatus]:
    required = tuple(
        item
        for item in metrics
        if item.completion_rule is OutcomeCompletionRule.REQUIRED
    )
    statuses = tuple(item.status for item in required)
    if OutcomeStatus.FAILED in statuses:
        return OutcomeStatus.FAILED, OutcomeAvailabilityStatus.FAILED
    if all(item is OutcomeStatus.COMPLETE for item in statuses):
        return OutcomeStatus.COMPLETE, OutcomeAvailabilityStatus.AVAILABLE
    if all(item is OutcomeStatus.UNAVAILABLE for item in statuses):
        return OutcomeStatus.UNAVAILABLE, OutcomeAvailabilityStatus.UNAVAILABLE
    availability = (
        OutcomeAvailabilityStatus.UNAVAILABLE
        if OutcomeStatus.UNAVAILABLE in statuses
        else OutcomeAvailabilityStatus.AVAILABLE
    )
    return OutcomeStatus.PARTIAL, availability


def _ratio(value: Decimal) -> Decimal:
    return value.quantize(_RATIO_QUANTUM, rounding=ROUND_HALF_EVEN)


def _aware(value: datetime, label: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")


__all__ = ["calculate_market_target_outcome"]
