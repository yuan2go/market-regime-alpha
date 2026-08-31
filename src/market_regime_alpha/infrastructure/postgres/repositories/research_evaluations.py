"""PostgreSQL Evaluation Protocol/Run and pure completion writer."""

from __future__ import annotations

from typing import Any, Callable
from uuid import UUID

import psycopg

from market_regime_alpha.research_qualification.domain.evaluation import (
    EvaluationInput,
    EvaluationProtocolPlan,
    EvaluationRunPlan,
    ProtocolMetricDefinition,
    evaluate_metric,
)
from market_regime_alpha.research_qualification.domain.research_vocabulary import (
    AcceptanceOperator,
    CandidateDisposition,
    EvaluationInclusionPolicy,
    EvaluationMissingnessPolicy,
    EvaluationReducer,
    EvaluationSliceKind,
    MetricDirection,
    SourceMetricValueType,
)
from market_regime_alpha.research_qualification.errors import (
    EvaluationProtocolError,
    EvaluationReconciliationError,
)
from market_regime_alpha.research_qualification.ports.evaluation_uow import (
    EvaluationCompletionResult,
    EvaluationProtocolRecord,
    EvaluationRunRecord,
)
from market_regime_alpha.runtime.errors import RuntimeNotFoundError, RuntimeStateConflictError
from market_regime_alpha.shared.hashing import canonical_json_sha256


class PostgresEvaluationRepository:
    def __init__(self, connection: psycopg.Connection[Any], *, id_factory: Callable[[], UUID]) -> None:
        self._connection = connection
        self._id_factory = id_factory

    def lock_protocol_identity(self, protocol_code: str) -> None:
        self._connection.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            (f"evaluation-protocol:{protocol_code}",),
        )

    def register_protocol(
        self,
        plan: EvaluationProtocolPlan,
        *,
        request_identity: str,
        request_sha256: str,
    ) -> EvaluationProtocolRecord:
        with self._connection.cursor() as cursor:
            cursor.executemany(
                """
                INSERT INTO mra.evaluation_protocol_metric (
                    evaluation_protocol_metric_id, evaluation_protocol_id,
                    target_definition_id, ordinal, metric_code,
                    source_target_metric_definition_id, source_metric_code,
                    source_value_type, reducer, slice_kind,
                    candidate_disposition, direction, inclusion_policy,
                    missingness_policy, minimum_estimable_count,
                    acceptance_operator, acceptance_threshold, content_sha256
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
                """,
                (
                    (
                        metric.evaluation_protocol_metric_id,
                        plan.evaluation_protocol_id,
                        plan.target_definition_id,
                        metric.ordinal,
                        metric.metric_code,
                        metric.source_target_metric_definition_id,
                        metric.source_metric_code,
                        metric.source_value_type.value,
                        metric.reducer.value,
                        metric.slice_kind.value,
                        metric.candidate_disposition.value if metric.candidate_disposition else None,
                        metric.direction.value,
                        metric.inclusion_policy.value,
                        metric.missingness_policy.value,
                        metric.minimum_estimable_count,
                        metric.acceptance_operator.value,
                        metric.acceptance_threshold,
                        str(metric.content_sha256),
                    )
                    for metric in plan.metrics
                ),
            )
        self._connection.execute(
            """
            INSERT INTO mra.evaluation_protocol (
                evaluation_protocol_id, protocol_code, protocol_version, status,
                target_definition_id, target_version,
                target_definition_sha256, applicable_purpose,
                decision_rule, metric_count, metric_roster_sha256,
                code_artifact_id, code_content_sha256, code_size_bytes,
                config_artifact_id, config_content_sha256, config_size_bytes,
                provenance_sha256, content_sha256,
                request_identity, request_sha256
            ) VALUES (
                %s, %s, %s, 'FROZEN', %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            """,
            (
                plan.evaluation_protocol_id, plan.protocol_code, plan.protocol_version,
                plan.target_definition_id, plan.target_version,
                str(plan.target_definition_sha256), plan.applicable_purpose.value,
                plan.decision_rule, len(plan.metrics), str(plan.metric_roster_sha256),
                plan.code_artifact.artifact_id, str(plan.code_artifact.content_sha256),
                plan.code_artifact.size_bytes, plan.config_artifact.artifact_id,
                str(plan.config_artifact.content_sha256), plan.config_artifact.size_bytes,
                str(plan.provenance_sha256), str(plan.content_sha256),
                request_identity, request_sha256,
            ),
        )
        record = self.protocol_record(plan.evaluation_protocol_id, lock=False)
        if not self._protocol_reconciles(record):
            raise EvaluationReconciliationError("EvaluationProtocol metric roster does not reconcile")
        return record

    def open_run(
        self, plan: EvaluationRunPlan, *, request_sha256: str
    ) -> EvaluationRunRecord:
        binding = self._connection.execute(
            """
            SELECT run.experiment_id, run.experiment_partition_id,
                   run.research_partition_id, binding.target_definition_id,
                   binding.partition_purpose, partition.member_count,
                   protocol.metric_count
            FROM mra.experiment_run AS run
            JOIN mra.experiment_partition AS binding
              ON binding.experiment_partition_id = run.experiment_partition_id
            JOIN mra.research_partition AS partition
              ON partition.research_partition_id = run.research_partition_id
            JOIN mra.evaluation_protocol AS protocol
              ON protocol.evaluation_protocol_id = %s
             AND protocol.target_definition_id = binding.target_definition_id
             AND protocol.applicable_purpose = binding.partition_purpose
            WHERE run.experiment_run_id = %s
              AND run.status = 'OPENED'
              AND partition.status = 'FROZEN'
            FOR SHARE OF run, binding, partition, protocol
            """,
            (plan.evaluation_protocol_id, plan.experiment_run_id),
        ).fetchone()
        if binding is None:
            raise EvaluationProtocolError(
                "EvaluationRun requires exact Experiment/Partition/Protocol binding"
            )
        member_count = self._connection.execute(
            "SELECT count(*) FROM mra.research_partition_member WHERE research_partition_id = %s",
            (binding[2],),
        ).fetchone()
        assert member_count is not None
        if int(member_count[0]) != int(binding[5]):
            raise EvaluationReconciliationError("Partition member roster is incomplete")
        self._connection.execute(
            """
            INSERT INTO mra.evaluation_run (
                evaluation_run_id, experiment_run_id, experiment_id,
                experiment_partition_id, research_partition_id,
                evaluation_protocol_id, target_definition_id,
                partition_purpose, requested_knowledge_cutoff,
                expected_member_count, expected_protocol_metric_count,
                code_artifact_id, code_content_sha256, code_size_bytes,
                config_artifact_id, config_content_sha256, config_size_bytes,
                provenance_sha256, content_sha256,
                status, request_identity, request_sha256
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                'OPEN', %s, %s
            )
            """,
            (
                plan.evaluation_run_id, plan.experiment_run_id,
                binding[0], binding[1], binding[2], plan.evaluation_protocol_id,
                binding[3], binding[4], plan.requested_knowledge_cutoff,
                binding[5], binding[6],
                plan.code_artifact.artifact_id,
                str(plan.code_artifact.content_sha256),
                plan.code_artifact.size_bytes,
                plan.config_artifact.artifact_id,
                str(plan.config_artifact.content_sha256),
                plan.config_artifact.size_bytes,
                str(plan.provenance_sha256), str(plan.content_sha256),
                plan.request_identity, request_sha256,
            ),
        )
        return self.run_record(plan.evaluation_run_id, lock=False)

    def complete(self, evaluation_run_id: UUID) -> EvaluationCompletionResult:
        run = self._connection.execute(
            """
            SELECT evaluation_protocol_id, expected_member_count,
                   expected_protocol_metric_count, observation_count,
                   status, metric_count, metric_observation_count,
                   metric_roster_sha256
            FROM mra.evaluation_run
            WHERE evaluation_run_id = %s
            FOR UPDATE
            """,
            (evaluation_run_id,),
        ).fetchone()
        if run is None:
            raise RuntimeNotFoundError(f"EvaluationRun {evaluation_run_id} does not exist")
        if run[4] == "COMPLETED":
            if run[7] is None:
                raise EvaluationReconciliationError("completed EvaluationRun has no metric roster hash")
            return EvaluationCompletionResult(
                evaluation_run_id, int(run[5]), int(run[6]), str(run[7])
            )
        if run[4] != "INPUTS_ACQUIRED":
            raise RuntimeStateConflictError("EvaluationRun is not INPUTS_ACQUIRED")
        if int(run[1]) != int(run[3]):
            raise EvaluationReconciliationError("EvaluationObservation roster is incomplete")
        metric_rows = self._connection.execute(
            """
            SELECT evaluation_protocol_metric_id, metric_code, ordinal,
                   source_target_metric_definition_id, source_metric_code,
                   source_value_type, reducer, slice_kind,
                   candidate_disposition, direction,
                   minimum_estimable_count, acceptance_operator,
                   acceptance_threshold, inclusion_policy,
                   missingness_policy
            FROM mra.evaluation_protocol_metric
            WHERE evaluation_protocol_id = %s
            ORDER BY ordinal
            FOR SHARE
            """,
            (run[0],),
        ).fetchall()
        if len(metric_rows) != int(run[2]):
            raise EvaluationReconciliationError("Protocol metric roster is incomplete")
        output_hashes: list[tuple[UUID, str]] = []
        total_inputs = 0
        for row in metric_rows:
            metric = _protocol_metric(row)
            source_rows = self._connection.execute(
                """
                SELECT observation.evaluation_observation_id,
                       observation.research_partition_member_id,
                       observation.market_target_outcome_revision_id,
                       observation.candidate_disposition,
                       source.market_target_outcome_metric_id,
                       source.value_status, source.decimal_value,
                       source.boolean_value
                FROM mra.evaluation_observation AS observation
                JOIN mra.market_target_outcome_metric AS source
                  ON source.market_target_outcome_revision_id =
                     observation.market_target_outcome_revision_id
                 AND source.target_metric_definition_id = %s
                WHERE observation.evaluation_run_id = %s
                ORDER BY observation.research_partition_member_id
                FOR SHARE OF observation, source
                """,
                (metric.source_target_metric_definition_id, evaluation_run_id),
            ).fetchall()
            if len(source_rows) != int(run[1]):
                raise EvaluationReconciliationError(
                    "exact Outcome metric input roster is incomplete"
                )
            inputs = tuple(
                EvaluationInput(
                    evaluation_observation_id=UUID(str(source[0])),
                    candidate_disposition=CandidateDisposition(str(source[3])),
                    source_value_status=str(source[5]),
                    decimal_value=source[6], boolean_value=source[7],
                )
                for source in source_rows
            )
            result = evaluate_metric(metric, inputs)
            evaluation_metric_id = self._id_factory()
            result_hash = canonical_json_sha256(
                {"metric": metric.content_sha256, "result": result}
            )
            self._connection.execute(
                """
                INSERT INTO mra.evaluation_metric (
                    evaluation_metric_id, evaluation_run_id,
                    evaluation_protocol_metric_id,
                    evaluation_protocol_id, metric_state,
                    decimal_value, boolean_value, estimable_count,
                    acceptance_state, content_sha256
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    evaluation_metric_id, evaluation_run_id,
                    metric.evaluation_protocol_metric_id, run[0],
                    result.state.value, result.decimal_value,
                    result.boolean_value, result.estimable_count,
                    result.acceptance_state.value, result_hash,
                ),
            )
            classifications = {
                item.evaluation_observation_id: item for item in result.observations
            }
            with self._connection.cursor() as cursor:
                cursor.executemany(
                    """
                    INSERT INTO mra.evaluation_metric_observation (
                        evaluation_metric_observation_id,
                        evaluation_metric_id, evaluation_run_id,
                        evaluation_protocol_metric_id,
                        evaluation_observation_id,
                        research_partition_member_id,
                        market_target_outcome_revision_id,
                        source_outcome_metric_id,
                        source_target_metric_definition_id,
                        source_value_type, source_value_status,
                        input_state, reason_code, content_sha256
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s
                    )
                    """,
                    (
                        _metric_observation_values(
                            self._id_factory(), evaluation_metric_id,
                            evaluation_run_id, metric, source,
                            classifications[UUID(str(source[0]))],
                        )
                        for source in source_rows
                    ),
                )
            total_inputs += len(source_rows)
            output_hashes.append((evaluation_metric_id, result_hash))
        expected_inputs = int(run[1]) * int(run[2])
        actual = self._connection.execute(
            """
            SELECT count(DISTINCT metric.evaluation_metric_id),
                   count(input.evaluation_metric_observation_id)
            FROM mra.evaluation_metric AS metric
            LEFT JOIN mra.evaluation_metric_observation AS input
              ON input.evaluation_metric_id = metric.evaluation_metric_id
            WHERE metric.evaluation_run_id = %s
            """,
            (evaluation_run_id,),
        ).fetchone()
        assert actual is not None
        if int(actual[0]) != int(run[2]) or int(actual[1]) != expected_inputs or total_inputs != expected_inputs:
            raise EvaluationReconciliationError("Evaluation metric Cartesian roster is incomplete")
        roster_hash = canonical_json_sha256(tuple(output_hashes))
        self._connection.execute(
            """
            UPDATE mra.evaluation_run
            SET status = 'COMPLETED', completed_at = clock_timestamp(),
                metric_count = %s, metric_observation_count = %s,
                metric_roster_sha256 = %s, version = version + 1
            WHERE evaluation_run_id = %s AND status = 'INPUTS_ACQUIRED'
            """,
            (len(metric_rows), expected_inputs, roster_hash, evaluation_run_id),
        )
        return EvaluationCompletionResult(
            evaluation_run_id, len(metric_rows), expected_inputs, roster_hash
        )

    def fail(
        self,
        evaluation_run_id: UUID,
        reason_code: str,
    ) -> EvaluationRunRecord:
        changed = self._connection.execute(
            """
            UPDATE mra.evaluation_run
            SET status = 'FAILED', failed_at = clock_timestamp(),
                failure_reason_code = %s, version = version + 1
            WHERE evaluation_run_id = %s
              AND status IN ('OPEN', 'INPUTS_ACQUIRED')
            """,
            (reason_code, evaluation_run_id),
        ).rowcount
        if changed != 1:
            raise RuntimeStateConflictError("EvaluationRun cannot transition to FAILED")
        return self.run_record(evaluation_run_id, lock=False)

    def protocol_record(self, evaluation_protocol_id: UUID, *, lock: bool) -> EvaluationProtocolRecord:
        row = self._connection.execute(
            """
            SELECT evaluation_protocol_id, target_definition_id,
                   applicable_purpose, metric_count,
                   metric_roster_sha256, frozen_at
            FROM mra.evaluation_protocol
            WHERE evaluation_protocol_id = %s
            """ + (" FOR SHARE" if lock else ""),
            (evaluation_protocol_id,),
        ).fetchone()
        if row is None:
            raise RuntimeNotFoundError(f"EvaluationProtocol {evaluation_protocol_id} does not exist")
        return EvaluationProtocolRecord(
            UUID(str(row[0])), UUID(str(row[1])), str(row[2]),
            int(row[3]), str(row[4]), row[5],
        )

    def run_record(self, evaluation_run_id: UUID, *, lock: bool) -> EvaluationRunRecord:
        row = self._connection.execute(
            """
            SELECT evaluation_run_id, experiment_run_id,
                   research_partition_id, evaluation_protocol_id,
                   status, opened_at, content_sha256, version
            FROM mra.evaluation_run WHERE evaluation_run_id = %s
            """ + (" FOR SHARE" if lock else ""),
            (evaluation_run_id,),
        ).fetchone()
        if row is None:
            raise RuntimeNotFoundError(f"EvaluationRun {evaluation_run_id} does not exist")
        return EvaluationRunRecord(
            UUID(str(row[0])), UUID(str(row[1])), UUID(str(row[2])),
            UUID(str(row[3])), str(row[4]), row[5], str(row[6]), int(row[7]),
        )

    def _protocol_reconciles(self, record: EvaluationProtocolRecord) -> bool:
        rows = self._connection.execute(
            """
            SELECT evaluation_protocol_metric_id, metric_code, ordinal,
                   source_target_metric_definition_id, source_metric_code,
                   source_value_type, reducer, slice_kind,
                   candidate_disposition, direction,
                   minimum_estimable_count, acceptance_operator,
                   acceptance_threshold, inclusion_policy, missingness_policy
            FROM mra.evaluation_protocol_metric
            WHERE evaluation_protocol_id = %s ORDER BY ordinal
            """,
            (record.evaluation_protocol_id,),
        ).fetchall()
        metrics = tuple(_protocol_metric(row) for row in rows)
        return len(metrics) == record.metric_count and canonical_json_sha256(metrics) == record.metric_roster_sha256


def _protocol_metric(row: tuple[Any, ...]) -> ProtocolMetricDefinition:
    return ProtocolMetricDefinition(
        evaluation_protocol_metric_id=UUID(str(row[0])), metric_code=str(row[1]),
        ordinal=int(row[2]), source_target_metric_definition_id=UUID(str(row[3])),
        source_metric_code=str(row[4]), source_value_type=SourceMetricValueType(str(row[5])),
        reducer=EvaluationReducer(str(row[6])), slice_kind=EvaluationSliceKind(str(row[7])),
        candidate_disposition=CandidateDisposition(str(row[8])) if row[8] is not None else None,
        direction=MetricDirection(str(row[9])), minimum_estimable_count=int(row[10]),
        acceptance_operator=AcceptanceOperator(str(row[11])), acceptance_threshold=row[12],
        inclusion_policy=EvaluationInclusionPolicy(str(row[13])),
        missingness_policy=EvaluationMissingnessPolicy(str(row[14])),
    )


def _metric_observation_values(
    identity: UUID,
    evaluation_metric_id: UUID,
    evaluation_run_id: UUID,
    metric: ProtocolMetricDefinition,
    source: tuple[Any, ...],
    classification: Any,
) -> tuple[Any, ...]:
    content_hash = canonical_json_sha256(
        {
            "evaluation_metric_id": evaluation_metric_id,
            "evaluation_observation_id": source[0],
            "input_state": classification.state,
            "reason_code": classification.reason_code,
            "source_outcome_metric_id": source[4],
        }
    )
    return (
        identity, evaluation_metric_id, evaluation_run_id,
        metric.evaluation_protocol_metric_id, source[0], source[1], source[2],
        source[4], metric.source_target_metric_definition_id,
        metric.source_value_type.value, source[5], classification.state.value,
        classification.reason_code, content_hash,
    )


__all__ = ["PostgresEvaluationRepository"]
