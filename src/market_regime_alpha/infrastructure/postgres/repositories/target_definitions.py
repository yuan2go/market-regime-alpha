"""PostgreSQL Authority adapter for immutable Target Definition aggregates."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import psycopg

from market_regime_alpha.research_qualification.domain.model import ArtifactBinding
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
    TargetRegistrationStatus,
    TargetTimingRule,
    TargetValueField,
    TargetValueType,
)
from market_regime_alpha.research_qualification.ports.target_repository import (
    TargetDefinitionRecord,
    TargetRegistrationReconciliation,
)
from market_regime_alpha.runtime.errors import ArtifactIntegrityError, RuntimeNotFoundError


class PostgresTargetDefinitionRepository:
    def __init__(self, connection: psycopg.Connection[Any]) -> None:
        self._connection = connection

    def lock_registration_identity(self, target_code: str, version: int) -> None:
        self._connection.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            (f"target-definition:{target_code}:{version}",),
        )

    def insert_target_definition(
        self,
        definition: TargetDefinition,
        *,
        registration_request_identity: str,
        registration_request_sha256: str,
        actor_type: str,
        actor_id: str,
    ) -> TargetDefinitionRecord:
        self._validate_supersession(definition)
        with self._connection.cursor() as cursor:
            cursor.executemany(
                """
                INSERT INTO mra.target_checkpoint (
                    target_checkpoint_id, target_definition_id,
                    checkpoint_code, ordinal, checkpoint_role,
                    session_offset, timing_rule, local_time, timezone_name,
                    timeframe, price_basis, value_field, reference_rule,
                    availability_rule, finality_rule, content_sha256
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s
                )
                """,
                (
                    (
                        item.target_checkpoint_id,
                        definition.target_definition_id,
                        item.checkpoint_code,
                        item.ordinal,
                        item.role.value,
                        item.session_offset,
                        item.timing_rule.value,
                        item.local_time,
                        item.timezone_name,
                        item.timeframe.value,
                        item.price_basis.value,
                        item.value_field.value,
                        item.reference_rule.value,
                        item.availability_rule.value,
                        item.finality_rule.value,
                        str(item.content_sha256),
                    )
                    for item in definition.checkpoints
                ),
            )
            cursor.executemany(
                """
                INSERT INTO mra.target_metric_definition (
                    target_metric_definition_id, target_definition_id,
                    metric_code, ordinal, metric_kind, value_type, unit,
                    completion_rule, barrier_direction, barrier_threshold,
                    algorithm_code, algorithm_version, algorithm_sha256,
                    algorithm_binding_sha256,
                    code_artifact_id, code_content_sha256, code_size_bytes,
                    config_artifact_id, config_content_sha256,
                    config_size_bytes, content_sha256
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s
                )
                """,
                (_metric_parameters(definition, item) for item in definition.metrics),
            )
            cursor.executemany(
                """
                INSERT INTO mra.target_metric_dependency (
                    target_metric_dependency_id, target_definition_id,
                    target_metric_definition_id, target_checkpoint_id,
                    ordinal, dependency_role, content_sha256
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    (
                        item.target_metric_dependency_id,
                        definition.target_definition_id,
                        item.target_metric_definition_id,
                        item.target_checkpoint_id,
                        item.ordinal,
                        item.role.value,
                        str(item.content_sha256),
                    )
                    for item in definition.dependencies
                ),
            )
        algorithm = definition.algorithm
        self._connection.execute(
            """
            INSERT INTO mra.target_definition (
                target_definition_id, target_code, version,
                registration_status, supersedes_target_definition_id,
                instrument_scope, market_scope,
                algorithm_code, algorithm_version, algorithm_sha256,
                algorithm_binding_sha256,
                code_artifact_id, code_content_sha256, code_size_bytes,
                config_artifact_id, config_content_sha256, config_size_bytes,
                checkpoint_count, checkpoint_roster_sha256,
                metric_count, metric_roster_sha256,
                dependency_count, dependency_roster_sha256,
                content_sha256, registration_request_identity,
                registration_request_sha256, registered_by_actor_type,
                registered_by_actor_id
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s
            )
            """,
            (
                definition.target_definition_id,
                definition.target_code,
                definition.version,
                definition.registration_status.value,
                definition.supersedes_target_definition_id,
                definition.instrument_scope.value,
                definition.market_scope.value,
                algorithm.algorithm_code,
                algorithm.algorithm_version,
                str(algorithm.algorithm_sha256),
                str(algorithm.content_sha256),
                algorithm.code_artifact.artifact_id,
                str(algorithm.code_artifact.content_sha256),
                algorithm.code_artifact.size_bytes,
                algorithm.config_artifact.artifact_id,
                str(algorithm.config_artifact.content_sha256),
                algorithm.config_artifact.size_bytes,
                len(definition.checkpoints),
                str(definition.checkpoint_roster_sha256),
                len(definition.metrics),
                str(definition.metric_roster_sha256),
                len(definition.dependencies),
                str(definition.dependency_roster_sha256),
                str(definition.content_sha256),
                registration_request_identity,
                registration_request_sha256,
                actor_type,
                actor_id,
            ),
        )
        return self.target_record(definition.target_definition_id, lock=False)

    def target_definition(
        self,
        target_definition_id: UUID,
        *,
        lock: bool,
    ) -> TargetDefinition:
        root = self._root_row(target_definition_id, lock=lock)
        checkpoints = tuple(
            _checkpoint(row)
            for row in self._connection.execute(
                """
                SELECT target_checkpoint_id, target_definition_id,
                       checkpoint_code, ordinal, checkpoint_role,
                       session_offset, timing_rule, local_time, timezone_name,
                       timeframe, price_basis, value_field, reference_rule,
                       availability_rule, finality_rule, content_sha256
                FROM mra.target_checkpoint
                WHERE target_definition_id = %s
                ORDER BY ordinal
                """
                + (" FOR SHARE" if lock else ""),
                (target_definition_id,),
            ).fetchall()
        )
        metrics = tuple(
            _metric(row)
            for row in self._connection.execute(
                """
                SELECT target_metric_definition_id, target_definition_id,
                       metric_code, ordinal, metric_kind, value_type, unit,
                       completion_rule, barrier_direction, barrier_threshold,
                       algorithm_code, algorithm_version, algorithm_sha256,
                       algorithm_binding_sha256,
                       code_artifact_id, code_content_sha256, code_size_bytes,
                       config_artifact_id, config_content_sha256,
                       config_size_bytes, content_sha256
                FROM mra.target_metric_definition
                WHERE target_definition_id = %s
                ORDER BY ordinal
                """
                + (" FOR SHARE" if lock else ""),
                (target_definition_id,),
            ).fetchall()
        )
        dependencies = tuple(
            _dependency(row)
            for row in self._connection.execute(
                """
                SELECT target_metric_dependency_id, target_definition_id,
                       target_metric_definition_id, target_checkpoint_id,
                       ordinal, dependency_role, content_sha256
                FROM mra.target_metric_dependency
                WHERE target_definition_id = %s
                ORDER BY ordinal
                """
                + (" FOR SHARE" if lock else ""),
                (target_definition_id,),
            ).fetchall()
        )
        definition = TargetDefinition(
            target_definition_id=UUID(str(root[0])),
            target_code=str(root[1]),
            version=int(root[2]),
            registration_status=TargetRegistrationStatus(str(root[3])),
            supersedes_target_definition_id=(
                UUID(str(root[4])) if root[4] is not None else None
            ),
            instrument_scope=TargetInstrumentScope(str(root[5])),
            market_scope=TargetMarketScope(str(root[6])),
            algorithm=_algorithm(root, offset=7),
            checkpoints=checkpoints,
            metrics=metrics,
            dependencies=dependencies,
        )
        expected = (str(root[21]), str(root[18]), str(root[20]), str(root[22]))
        actual = (
            str(definition.content_sha256),
            str(definition.checkpoint_roster_sha256),
            str(definition.metric_roster_sha256),
            str(definition.dependency_roster_sha256),
        )
        if actual != expected:
            raise ArtifactIntegrityError(
                "persisted Target Definition hashes do not reconstruct"
            )
        return definition

    def target_record(
        self,
        target_definition_id: UUID,
        *,
        lock: bool,
    ) -> TargetDefinitionRecord:
        row = self._connection.execute(
            """
            SELECT target_definition_id, target_code, version,
                   registration_status, supersedes_target_definition_id,
                   content_sha256, checkpoint_count,
                   checkpoint_roster_sha256, metric_count,
                   metric_roster_sha256, dependency_count,
                   dependency_roster_sha256, registration_request_identity,
                   registration_request_sha256, registered_at
            FROM mra.target_definition
            WHERE target_definition_id = %s
            """
            + (" FOR SHARE" if lock else ""),
            (target_definition_id,),
        ).fetchone()
        if row is None:
            raise RuntimeNotFoundError(
                f"TargetDefinition {target_definition_id} does not exist"
            )
        return TargetDefinitionRecord(
            target_definition_id=UUID(str(row[0])),
            target_code=str(row[1]),
            version=int(row[2]),
            registration_status=str(row[3]),
            supersedes_target_definition_id=(
                UUID(str(row[4])) if row[4] is not None else None
            ),
            content_sha256=str(row[5]),
            checkpoint_count=int(row[6]),
            checkpoint_roster_sha256=str(row[7]),
            metric_count=int(row[8]),
            metric_roster_sha256=str(row[9]),
            dependency_count=int(row[10]),
            dependency_roster_sha256=str(row[11]),
            registration_request_identity=str(row[12]),
            registration_request_sha256=str(row[13]),
            registered_at=row[14],
        )

    def reconcile(
        self,
        target_definition_id: UUID,
        *,
        lock: bool,
    ) -> TargetRegistrationReconciliation:
        record = self.target_record(target_definition_id, lock=lock)
        definition = self.target_definition(target_definition_id, lock=lock)
        counts = self._connection.execute(
            """
            SELECT
              (SELECT count(*) FROM mra.target_checkpoint
               WHERE target_definition_id = %s),
              (SELECT count(*) FROM mra.target_metric_definition
               WHERE target_definition_id = %s),
              (SELECT count(*) FROM mra.target_metric_dependency
               WHERE target_definition_id = %s)
            """,
            (target_definition_id, target_definition_id, target_definition_id),
        ).fetchone()
        if counts is None:
            raise ArtifactIntegrityError("Target reconciliation returned no counts")
        matched = (
            (int(counts[0]), int(counts[1]), int(counts[2]))
            == (
                record.checkpoint_count,
                record.metric_count,
                record.dependency_count,
            )
            and str(definition.checkpoint_roster_sha256)
            == record.checkpoint_roster_sha256
            and str(definition.metric_roster_sha256) == record.metric_roster_sha256
            and str(definition.dependency_roster_sha256)
            == record.dependency_roster_sha256
            and str(definition.content_sha256) == record.content_sha256
        )
        return TargetRegistrationReconciliation(
            target_definition_id=target_definition_id,
            checkpoint_count=int(counts[0]),
            metric_count=int(counts[1]),
            dependency_count=int(counts[2]),
            checkpoint_roster_sha256=str(definition.checkpoint_roster_sha256),
            metric_roster_sha256=str(definition.metric_roster_sha256),
            dependency_roster_sha256=str(definition.dependency_roster_sha256),
            definition_sha256=str(definition.content_sha256),
            matched=matched,
        )

    def _root_row(self, target_definition_id: UUID, *, lock: bool) -> tuple[Any, ...]:
        row = self._connection.execute(
            """
            SELECT target_definition_id, target_code, version,
                   registration_status, supersedes_target_definition_id,
                   instrument_scope, market_scope,
                   algorithm_code, algorithm_version, algorithm_sha256,
                   algorithm_binding_sha256,
                   code_artifact_id, code_content_sha256, code_size_bytes,
                   config_artifact_id, config_content_sha256, config_size_bytes,
                   checkpoint_count, checkpoint_roster_sha256,
                   metric_count, metric_roster_sha256, content_sha256,
                   dependency_roster_sha256
            FROM mra.target_definition
            WHERE target_definition_id = %s
            """
            + (" FOR SHARE" if lock else ""),
            (target_definition_id,),
        ).fetchone()
        if row is None:
            raise RuntimeNotFoundError(
                f"TargetDefinition {target_definition_id} does not exist"
            )
        return tuple(row)

    def _validate_supersession(self, definition: TargetDefinition) -> None:
        if definition.supersedes_target_definition_id is None:
            return
        row = self._connection.execute(
            """
            SELECT target_code, version
            FROM mra.target_definition
            WHERE target_definition_id = %s
            FOR SHARE
            """,
            (definition.supersedes_target_definition_id,),
        ).fetchone()
        if row is None:
            raise RuntimeNotFoundError("superseded TargetDefinition does not exist")
        if str(row[0]) != definition.target_code or int(row[1]) + 1 != definition.version:
            raise ArtifactIntegrityError(
                "Target supersession must bind the immediately preceding same-code version"
            )


def _metric_parameters(
    definition: TargetDefinition,
    metric: TargetMetricDefinition,
) -> tuple[object, ...]:
    algorithm = metric.algorithm
    return (
        metric.target_metric_definition_id,
        definition.target_definition_id,
        metric.metric_code,
        metric.ordinal,
        metric.metric_kind.value,
        metric.value_type.value,
        metric.unit.value,
        metric.completion_rule.value,
        metric.barrier_direction.value if metric.barrier_direction is not None else None,
        metric.barrier_threshold,
        algorithm.algorithm_code,
        algorithm.algorithm_version,
        str(algorithm.algorithm_sha256),
        str(algorithm.content_sha256),
        algorithm.code_artifact.artifact_id,
        str(algorithm.code_artifact.content_sha256),
        algorithm.code_artifact.size_bytes,
        algorithm.config_artifact.artifact_id,
        str(algorithm.config_artifact.content_sha256),
        algorithm.config_artifact.size_bytes,
        str(metric.content_sha256),
    )


def _algorithm(row: tuple[Any, ...], *, offset: int) -> TargetAlgorithmBinding:
    algorithm = TargetAlgorithmBinding(
        algorithm_code=str(row[offset]),
        algorithm_version=str(row[offset + 1]),
        algorithm_sha256=str(row[offset + 2]),
        code_artifact=ArtifactBinding(
            artifact_id=UUID(str(row[offset + 4])),
            content_sha256=str(row[offset + 5]),
            size_bytes=int(row[offset + 6]),
        ),
        config_artifact=ArtifactBinding(
            artifact_id=UUID(str(row[offset + 7])),
            content_sha256=str(row[offset + 8]),
            size_bytes=int(row[offset + 9]),
        ),
    )
    if str(algorithm.content_sha256) != str(row[offset + 3]):
        raise ArtifactIntegrityError("Target algorithm binding hash does not reconstruct")
    return algorithm


def _checkpoint(row: tuple[Any, ...]) -> TargetCheckpoint:
    item = TargetCheckpoint(
        target_checkpoint_id=UUID(str(row[0])),
        target_definition_id=UUID(str(row[1])),
        checkpoint_code=str(row[2]),
        ordinal=int(row[3]),
        role=TargetCheckpointRole(str(row[4])),
        session_offset=int(row[5]),
        timing_rule=TargetTimingRule(str(row[6])),
        local_time=row[7],
        timezone_name=str(row[8]),
        timeframe=TargetBarTimeframe(str(row[9])),
        price_basis=TargetPriceBasis(str(row[10])),
        value_field=TargetValueField(str(row[11])),
        reference_rule=TargetReferenceRule(str(row[12])),
        availability_rule=TargetAvailabilityRule(str(row[13])),
        finality_rule=TargetFinalityRule(str(row[14])),
    )
    if str(item.content_sha256) != str(row[15]):
        raise ArtifactIntegrityError("Target checkpoint hash does not reconstruct")
    return item


def _metric(row: tuple[Any, ...]) -> TargetMetricDefinition:
    item = TargetMetricDefinition(
        target_metric_definition_id=UUID(str(row[0])),
        target_definition_id=UUID(str(row[1])),
        metric_code=str(row[2]),
        ordinal=int(row[3]),
        metric_kind=TargetMetricKind(str(row[4])),
        value_type=TargetValueType(str(row[5])),
        unit=TargetMetricUnit(str(row[6])),
        completion_rule=TargetCompletionRule(str(row[7])),
        barrier_direction=(
            TargetBarrierDirection(str(row[8])) if row[8] is not None else None
        ),
        barrier_threshold=row[9],
        algorithm=_algorithm(row, offset=10),
    )
    if str(item.content_sha256) != str(row[20]):
        raise ArtifactIntegrityError("Target metric hash does not reconstruct")
    return item


def _dependency(row: tuple[Any, ...]) -> TargetMetricDependency:
    item = TargetMetricDependency(
        target_metric_dependency_id=UUID(str(row[0])),
        target_definition_id=UUID(str(row[1])),
        target_metric_definition_id=UUID(str(row[2])),
        target_checkpoint_id=UUID(str(row[3])),
        ordinal=int(row[4]),
        role=TargetDependencyRole(str(row[5])),
    )
    if str(item.content_sha256) != str(row[6]):
        raise ArtifactIntegrityError("Target dependency hash does not reconstruct")
    return item


__all__ = ["PostgresTargetDefinitionRepository"]
