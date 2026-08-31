from __future__ import annotations

from dataclasses import fields, replace
from datetime import time
from decimal import Decimal
from uuid import UUID

import pytest

from market_regime_alpha.outcome.domain import (
    OutcomeBarrierDirection,
    OutcomeCheckpoint,
    OutcomeCompletionRule,
    OutcomeDependencyRole,
    OutcomeMetricDefinition,
    OutcomeMetricDependency,
    OutcomeMetricKind,
    OutcomeTargetDefinition,
    OutcomeValueField,
    OutcomeValueType,
)
from market_regime_alpha.research_qualification.domain import ArtifactBinding
from market_regime_alpha.research_qualification.domain.targets import (
    TargetAlgorithmBinding,
    TargetCheckpoint,
    TargetDefinition,
    TargetMetricDefinition,
    TargetMetricDependency,
)
from market_regime_alpha.research_qualification.domain.target_vocabulary import (
    TargetAvailabilityRule,
    TargetBarTimeframe,
    TargetBarrierDirection,
    TargetCheckpointRole,
    TargetCompletionRule,
    TargetDependencyRole,
    TargetFinalityRule,
    TargetInstrumentScope,
    TargetMarketScope,
    TargetMetricKind,
    TargetMetricUnit,
    TargetPriceBasis,
    TargetReferenceRule,
    TargetTimingRule,
    TargetValueField,
    TargetValueType,
)


TARGET_ID = UUID("00000000-0000-4000-8000-000000000901")
REFERENCE_ID = UUID("00000000-0000-4000-8000-000000000902")
OUTCOME_ID = UUID("00000000-0000-4000-8000-000000000903")
METRIC_ID = UUID("00000000-0000-4000-8000-000000000904")
REFERENCE_DEPENDENCY_ID = UUID("00000000-0000-4000-8000-000000000905")
OUTCOME_DEPENDENCY_ID = UUID("00000000-0000-4000-8000-000000000906")
CODE_ID = UUID("00000000-0000-4000-8000-000000000907")
CONFIG_ID = UUID("00000000-0000-4000-8000-000000000908")
HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_C = "c" * 64


def _artifact(artifact_id: UUID, content_hash: str) -> ArtifactBinding:
    return ArtifactBinding(
        artifact_id=artifact_id,
        content_sha256=content_hash,
        size_bytes=128,
    )


def _algorithm() -> TargetAlgorithmBinding:
    return TargetAlgorithmBinding(
        algorithm_code="simple_return",
        algorithm_version="1.0.0",
        algorithm_sha256=HASH_C,
        code_artifact=_artifact(CODE_ID, HASH_A),
        config_artifact=_artifact(CONFIG_ID, HASH_B),
    )


def _checkpoint(
    checkpoint_id: UUID,
    *,
    code: str,
    ordinal: int,
    role: TargetCheckpointRole,
    session_offset: int,
    local_time: time,
) -> TargetCheckpoint:
    return TargetCheckpoint(
        target_checkpoint_id=checkpoint_id,
        target_definition_id=TARGET_ID,
        checkpoint_code=code,
        ordinal=ordinal,
        role=role,
        session_offset=session_offset,
        timing_rule=TargetTimingRule.SESSION_LOCAL_BAR_END,
        local_time=local_time,
        timezone_name="Asia/Shanghai",
        timeframe=TargetBarTimeframe.MINUTE_5,
        price_basis=TargetPriceBasis.RAW_UNADJUSTED,
        value_field=TargetValueField.CLOSE,
        reference_rule=TargetReferenceRule.EXACT_SESSION_BAR,
        availability_rule=TargetAvailabilityRule.EXACT_REVISION_OR_SOURCE_GAP,
        finality_rule=TargetFinalityRule.RECORD_UNKNOWN,
    )


def valid_target() -> TargetDefinition:
    reference = _checkpoint(
        REFERENCE_ID,
        code="decision_reference_1455",
        ordinal=1,
        role=TargetCheckpointRole.DECISION_REFERENCE,
        session_offset=0,
        local_time=time(14, 55),
    )
    outcome = _checkpoint(
        OUTCOME_ID,
        code="next_session_1030",
        ordinal=2,
        role=TargetCheckpointRole.OUTCOME_OBSERVATION,
        session_offset=1,
        local_time=time(10, 30),
    )
    metric = TargetMetricDefinition(
        target_metric_definition_id=METRIC_ID,
        target_definition_id=TARGET_ID,
        metric_code="next_session_return",
        ordinal=1,
        metric_kind=TargetMetricKind.SIMPLE_RETURN,
        value_type=TargetValueType.DECIMAL,
        unit=TargetMetricUnit.RATIO,
        completion_rule=TargetCompletionRule.REQUIRED,
        algorithm=_algorithm(),
    )
    dependencies = (
        TargetMetricDependency(
            target_metric_dependency_id=REFERENCE_DEPENDENCY_ID,
            target_definition_id=TARGET_ID,
            target_metric_definition_id=METRIC_ID,
            target_checkpoint_id=REFERENCE_ID,
            ordinal=1,
            role=TargetDependencyRole.REFERENCE,
        ),
        TargetMetricDependency(
            target_metric_dependency_id=OUTCOME_DEPENDENCY_ID,
            target_definition_id=TARGET_ID,
            target_metric_definition_id=METRIC_ID,
            target_checkpoint_id=OUTCOME_ID,
            ordinal=2,
            role=TargetDependencyRole.OBSERVATION,
        ),
    )
    return TargetDefinition(
        target_definition_id=TARGET_ID,
        target_code="mr1_next_session_return",
        version=1,
        supersedes_target_definition_id=None,
        instrument_scope=TargetInstrumentScope.A_SHARE_EQUITY,
        market_scope=TargetMarketScope.SSE_SZSE,
        algorithm=_algorithm(),
        checkpoints=(reference, outcome),
        metrics=(metric,),
        dependencies=dependencies,
    )


def _target_for_metric_kind(
    metric_kind: TargetMetricKind,
    roles: tuple[TargetDependencyRole, ...],
    *,
    completion_rule: TargetCompletionRule = TargetCompletionRule.REQUIRED,
) -> TargetDefinition:
    definition = valid_target()
    barrier = metric_kind is TargetMetricKind.BARRIER_HIT
    observation_value = metric_kind is TargetMetricKind.OBSERVATION_VALUE
    metric = replace(
        definition.metrics[0],
        metric_kind=metric_kind,
        value_type=(
            TargetValueType.BOOLEAN if barrier else TargetValueType.DECIMAL
        ),
        unit=(
            TargetMetricUnit.BOOLEAN
            if barrier
            else TargetMetricUnit.PRICE
            if observation_value
            else TargetMetricUnit.RATIO
        ),
        completion_rule=completion_rule,
        barrier_direction=(
            TargetBarrierDirection.UP if barrier else None
        ),
        barrier_threshold=Decimal("0.05") if barrier else None,
    )
    checkpoints = {
        TargetDependencyRole.REFERENCE: REFERENCE_ID,
        TargetDependencyRole.OBSERVATION: OUTCOME_ID,
        TargetDependencyRole.PATH_MEMBER: OUTCOME_ID,
    }
    dependencies = tuple(
        TargetMetricDependency(
            target_metric_dependency_id=UUID(
                f"00000000-0000-4000-8000-{930 + ordinal:012d}"
            ),
            target_definition_id=TARGET_ID,
            target_metric_definition_id=METRIC_ID,
            target_checkpoint_id=checkpoints[role],
            ordinal=ordinal,
            role=role,
        )
        for ordinal, role in enumerate(roles, start=1)
    )
    return replace(definition, metrics=(metric,), dependencies=dependencies)


def _as_outcome_target(definition: TargetDefinition) -> OutcomeTargetDefinition:
    reference = next(
        item
        for item in definition.checkpoints
        if item.role is TargetCheckpointRole.DECISION_REFERENCE
    )
    checkpoints = tuple(
        OutcomeCheckpoint(
            target_checkpoint_id=item.target_checkpoint_id,
            content_sha256=str(item.content_sha256),
            ordinal=item.ordinal,
            checkpoint_code=item.checkpoint_code,
            session_offset=item.session_offset,
            local_time=item.local_time,
            timezone_name=item.timezone_name,
            timeframe=item.timeframe.value,
            price_basis=item.price_basis.value,
            value_field=OutcomeValueField(item.value_field.value),
        )
        for item in definition.checkpoints
        if item.role is TargetCheckpointRole.OUTCOME_OBSERVATION
    )
    metrics = tuple(
        OutcomeMetricDefinition(
            target_metric_definition_id=item.target_metric_definition_id,
            ordinal=item.ordinal,
            metric_code=item.metric_code,
            metric_kind=OutcomeMetricKind(item.metric_kind.value),
            value_type=OutcomeValueType(item.value_type.value),
            unit=item.unit.value,
            completion_rule=OutcomeCompletionRule(item.completion_rule.value),
            algorithm_code=item.algorithm.algorithm_code,
            algorithm_version=item.algorithm.algorithm_version,
            algorithm_sha256=str(item.algorithm.algorithm_sha256),
            code_artifact_id=item.algorithm.code_artifact.artifact_id,
            code_content_sha256=str(item.algorithm.code_artifact.content_sha256),
            code_size_bytes=item.algorithm.code_artifact.size_bytes,
            config_artifact_id=item.algorithm.config_artifact.artifact_id,
            config_content_sha256=str(item.algorithm.config_artifact.content_sha256),
            config_size_bytes=item.algorithm.config_artifact.size_bytes,
            content_sha256=str(item.content_sha256),
            barrier_direction=(
                OutcomeBarrierDirection(item.barrier_direction.value)
                if item.barrier_direction is not None
                else None
            ),
            barrier_threshold=item.barrier_threshold,
        )
        for item in definition.metrics
    )
    dependencies = tuple(
        OutcomeMetricDependency(
            target_metric_dependency_id=item.target_metric_dependency_id,
            ordinal=item.ordinal,
            target_metric_definition_id=item.target_metric_definition_id,
            target_checkpoint_id=item.target_checkpoint_id,
            role=OutcomeDependencyRole(item.role.value),
            content_sha256=str(item.content_sha256),
        )
        for item in definition.dependencies
    )
    algorithm = definition.algorithm
    return OutcomeTargetDefinition(
        target_definition_id=definition.target_definition_id,
        target_code=definition.target_code,
        version=definition.version,
        content_sha256=str(definition.content_sha256),
        reference_checkpoint_id=reference.target_checkpoint_id,
        algorithm_code=algorithm.algorithm_code,
        algorithm_version=algorithm.algorithm_version,
        algorithm_sha256=str(algorithm.algorithm_sha256),
        code_artifact_id=algorithm.code_artifact.artifact_id,
        code_content_sha256=str(algorithm.code_artifact.content_sha256),
        code_size_bytes=algorithm.code_artifact.size_bytes,
        config_artifact_id=algorithm.config_artifact.artifact_id,
        config_content_sha256=str(algorithm.config_artifact.content_sha256),
        config_size_bytes=algorithm.config_artifact.size_bytes,
        checkpoints=checkpoints,
        metrics=metrics,
        dependencies=dependencies,
    )


def test_target_definition_is_provider_neutral_and_hashes_complete_relational_semantics() -> None:
    definition = valid_target()
    assert str(definition.content_sha256) == (
        "a7d74593d676ac8b907d35eb318cf52d24c1a0bb4a69ebf10fca3a956a4a658b"
    )
    assert str(definition.checkpoint_roster_sha256) == (
        "0a247d0fcbed70f6a1704e5d203ffedc88b658938f035edcdb3172ada504e90d"
    )
    assert str(definition.metric_roster_sha256) == (
        "8d79d1104d75024ad9a8468d071b3b21011a18a4b7e4507e24a41b27a3f6fc2f"
    )
    assert str(definition.dependency_roster_sha256) == (
        "41e23cc0616538cf4f4af8f92204479461a0e8a9dbf45f5a659614f40978b179"
    )
    all_fields = {
        item.name
        for value_type in (
            TargetDefinition,
            TargetCheckpoint,
            TargetMetricDefinition,
            TargetMetricDependency,
        )
        for item in fields(value_type)
    }
    assert "provider_id" not in all_fields
    assert "provider_product_id" not in all_fields
    assert "json" not in " ".join(all_fields)


def test_target_definition_rejects_empty_or_incomplete_relational_rosters() -> None:
    definition = valid_target()
    with pytest.raises(ValueError, match="checkpoints"):
        replace(definition, checkpoints=())
    with pytest.raises(ValueError, match="metrics"):
        replace(definition, metrics=())
    with pytest.raises(ValueError, match="dependencies"):
        replace(definition, dependencies=())


def test_target_definition_requires_contiguous_order_and_one_reference_checkpoint() -> None:
    definition = valid_target()
    with pytest.raises(ValueError, match="checkpoint ordinals"):
        replace(
            definition,
            checkpoints=(
                definition.checkpoints[0],
                replace(definition.checkpoints[1], ordinal=3),
            ),
        )
    with pytest.raises(ValueError, match="exactly one DECISION_REFERENCE"):
        replace(
            definition,
            checkpoints=(
                replace(
                    definition.checkpoints[0],
                    role=TargetCheckpointRole.OUTCOME_OBSERVATION,
                    session_offset=1,
                ),
                definition.checkpoints[1],
            ),
        )


def test_target_definition_requires_typed_same_target_metric_dependencies() -> None:
    definition = valid_target()
    with pytest.raises(ValueError, match="same Target Definition"):
        replace(
            definition,
            dependencies=(
                replace(
                    definition.dependencies[0],
                    target_definition_id=UUID(
                        "00000000-0000-4000-8000-000000000999"
                    ),
                ),
                definition.dependencies[1],
            ),
        )
    with pytest.raises(ValueError, match="REFERENCE and OBSERVATION"):
        replace(
            definition,
            dependencies=(
                definition.dependencies[0],
                replace(
                    definition.dependencies[1],
                    role=TargetDependencyRole.PATH_MEMBER,
                ),
            ),
        )


@pytest.mark.parametrize(
    ("metric_kind", "roles"),
    (
        (
            TargetMetricKind.SIMPLE_RETURN,
            (TargetDependencyRole.REFERENCE, TargetDependencyRole.OBSERVATION),
        ),
        (
            TargetMetricKind.OBSERVATION_VALUE,
            (TargetDependencyRole.OBSERVATION,),
        ),
        (
            TargetMetricKind.MAX_FAVORABLE_EXCURSION,
            (TargetDependencyRole.REFERENCE, TargetDependencyRole.PATH_MEMBER),
        ),
        (
            TargetMetricKind.MAX_ADVERSE_EXCURSION,
            (TargetDependencyRole.REFERENCE, TargetDependencyRole.PATH_MEMBER),
        ),
        (
            TargetMetricKind.BARRIER_HIT,
            (TargetDependencyRole.REFERENCE, TargetDependencyRole.PATH_MEMBER),
        ),
    ),
)
def test_every_registered_metric_shape_reconstructs_as_an_outcome_contract(
    metric_kind: TargetMetricKind,
    roles: tuple[TargetDependencyRole, ...],
) -> None:
    definition = _target_for_metric_kind(metric_kind, roles)
    reconstructed = _as_outcome_target(definition)
    assert reconstructed.target_definition_id == definition.target_definition_id
    assert reconstructed.metrics[0].metric_kind.value == metric_kind.value


@pytest.mark.parametrize(
    ("metric_kind", "roles"),
    (
        (TargetMetricKind.SIMPLE_RETURN, (TargetDependencyRole.REFERENCE,)),
        (TargetMetricKind.SIMPLE_RETURN, (TargetDependencyRole.OBSERVATION,)),
        (
            TargetMetricKind.SIMPLE_RETURN,
            (TargetDependencyRole.REFERENCE, TargetDependencyRole.PATH_MEMBER),
        ),
        (
            TargetMetricKind.SIMPLE_RETURN,
            (
                TargetDependencyRole.REFERENCE,
                TargetDependencyRole.OBSERVATION,
                TargetDependencyRole.PATH_MEMBER,
            ),
        ),
        (
            TargetMetricKind.OBSERVATION_VALUE,
            (TargetDependencyRole.REFERENCE, TargetDependencyRole.OBSERVATION),
        ),
        (
            TargetMetricKind.OBSERVATION_VALUE,
            (TargetDependencyRole.PATH_MEMBER,),
        ),
        (
            TargetMetricKind.MAX_FAVORABLE_EXCURSION,
            (TargetDependencyRole.PATH_MEMBER,),
        ),
        (
            TargetMetricKind.MAX_ADVERSE_EXCURSION,
            (TargetDependencyRole.REFERENCE,),
        ),
        (
            TargetMetricKind.BARRIER_HIT,
            (
                TargetDependencyRole.REFERENCE,
                TargetDependencyRole.PATH_MEMBER,
                TargetDependencyRole.OBSERVATION,
            ),
        ),
    ),
)
def test_target_rejects_every_outcome_incompatible_metric_dependency_shape(
    metric_kind: TargetMetricKind,
    roles: tuple[TargetDependencyRole, ...],
) -> None:
    with pytest.raises(ValueError, match="dependency shape"):
        _target_for_metric_kind(metric_kind, roles)


def test_target_definition_requires_at_least_one_required_metric() -> None:
    with pytest.raises(ValueError, match="REQUIRED metric"):
        _target_for_metric_kind(
            TargetMetricKind.SIMPLE_RETURN,
            (TargetDependencyRole.REFERENCE, TargetDependencyRole.OBSERVATION),
            completion_rule=TargetCompletionRule.OPTIONAL,
        )


def test_barrier_metric_requires_typed_direction_and_positive_threshold() -> None:
    definition = valid_target()
    with pytest.raises(ValueError, match="barrier_direction"):
        replace(
            definition.metrics[0],
            metric_kind=TargetMetricKind.BARRIER_HIT,
            value_type=TargetValueType.BOOLEAN,
            unit=TargetMetricUnit.BOOLEAN,
            barrier_threshold=Decimal("0.05"),
        )
