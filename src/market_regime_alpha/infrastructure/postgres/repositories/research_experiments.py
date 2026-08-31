"""PostgreSQL Experiment, Partition binding, and execution identity writer."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import psycopg

from market_regime_alpha.research_qualification.domain.experiment import (
    ExperimentDefinition,
    ExperimentPartitionBinding,
    ExperimentRunPlan,
)
from market_regime_alpha.research_qualification.errors import ExperimentBindingError
from market_regime_alpha.research_qualification.ports.experiment_uow import (
    ExperimentRecord,
    ExperimentRunRecord,
)
from market_regime_alpha.runtime.errors import RuntimeNotFoundError


class PostgresExperimentRepository:
    def __init__(self, connection: psycopg.Connection[Any]) -> None:
        self._connection = connection

    def lock_identity(self, experiment_code: str) -> None:
        self._connection.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            (f"research-experiment:{experiment_code}",),
        )

    def register(
        self,
        definition: ExperimentDefinition,
        binding: ExperimentPartitionBinding,
        *,
        request_identity: str,
        request_sha256: str,
    ) -> ExperimentRecord:
        definition.validate_partition_binding(binding)
        partition = self._connection.execute(
            """
            SELECT target_definition_id, target_version,
                   target_definition_sha256, purpose, content_sha256
            FROM mra.research_partition
            WHERE research_partition_id = %s
            FOR SHARE
            """,
            (binding.research_partition_id,),
        ).fetchone()
        if partition is None:
            raise ExperimentBindingError("ResearchPartition does not exist")
        actual = (UUID(str(partition[0])), int(partition[1]), str(partition[2]), str(partition[3]), str(partition[4]))
        expected = (
            binding.target_definition_id,
            binding.target_version,
            str(binding.target_definition_sha256),
            binding.purpose.value,
            str(binding.partition_content_sha256),
        )
        if actual != expected:
            raise ExperimentBindingError("Experiment binding does not match exact Partition Authority")
        algorithm = definition
        self._connection.execute(
            """
            INSERT INTO mra.experiment (
                experiment_id, experiment_code, status, research_question,
                primary_change, hypothesis, target_definition_id,
                target_version, target_definition_sha256,
                protocol_identity, acceptance_semantics,
                code_artifact_id, code_content_sha256, code_size_bytes,
                config_artifact_id, config_content_sha256, config_size_bytes,
                provenance_sha256, content_sha256,
                request_identity, request_sha256
            ) VALUES (
                %s, %s, 'REGISTERED', %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            """,
            (
                definition.experiment_id, definition.experiment_code,
                definition.research_question, definition.primary_change,
                definition.hypothesis, definition.target_definition_id,
                definition.target_version, str(definition.target_definition_sha256),
                definition.protocol_identity, definition.acceptance_semantics,
                algorithm.code_artifact.artifact_id,
                str(algorithm.code_artifact.content_sha256), algorithm.code_artifact.size_bytes,
                algorithm.config_artifact.artifact_id,
                str(algorithm.config_artifact.content_sha256), algorithm.config_artifact.size_bytes,
                str(definition.provenance_sha256), str(definition.content_sha256),
                request_identity, request_sha256,
            ),
        )
        self._connection.execute(
            """
            INSERT INTO mra.experiment_partition (
                experiment_partition_id, experiment_id,
                research_partition_id, target_definition_id,
                target_version, target_definition_sha256,
                partition_purpose, partition_content_sha256
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                binding.experiment_partition_id, binding.experiment_id,
                binding.research_partition_id, binding.target_definition_id,
                binding.target_version, str(binding.target_definition_sha256),
                binding.purpose.value, str(binding.partition_content_sha256),
            ),
        )
        return self.record(definition.experiment_id, lock=False)

    def open_run(self, plan: ExperimentRunPlan) -> ExperimentRunRecord:
        row = self._connection.execute(
            """
            SELECT research_partition_id
            FROM mra.experiment_partition
            WHERE experiment_partition_id = %s AND experiment_id = %s
            FOR SHARE
            """,
            (plan.experiment_partition_id, plan.experiment_id),
        ).fetchone()
        if row is None:
            raise ExperimentBindingError("ExperimentPartition binding does not exist")
        self._connection.execute(
            """
            INSERT INTO mra.experiment_run (
                experiment_run_id, experiment_id,
                experiment_partition_id, research_partition_id,
                status, run_identity, content_sha256
            ) VALUES (%s, %s, %s, %s, 'OPENED', %s, %s)
            """,
            (
                plan.experiment_run_id, plan.experiment_id,
                plan.experiment_partition_id, row[0],
                plan.run_identity, str(plan.content_sha256),
            ),
        )
        return self.run_record(plan.experiment_run_id, lock=False)

    def record(self, experiment_id: UUID, *, lock: bool) -> ExperimentRecord:
        row = self._connection.execute(
            """
            SELECT experiment.experiment_id,
                   binding.experiment_partition_id,
                   binding.research_partition_id,
                   experiment.target_definition_id,
                   binding.partition_purpose,
                   experiment.registered_at, binding.bound_at
            FROM mra.experiment AS experiment
            JOIN mra.experiment_partition AS binding
              ON binding.experiment_id = experiment.experiment_id
            WHERE experiment.experiment_id = %s
            """ + (" FOR SHARE OF experiment, binding" if lock else ""),
            (experiment_id,),
        ).fetchone()
        if row is None:
            raise RuntimeNotFoundError(f"Experiment {experiment_id} does not exist")
        return ExperimentRecord(
            experiment_id=UUID(str(row[0])),
            experiment_partition_id=UUID(str(row[1])),
            research_partition_id=UUID(str(row[2])),
            target_definition_id=UUID(str(row[3])),
            partition_purpose=str(row[4]),
            registered_at=row[5], bound_at=row[6],
        )

    def run_record(self, experiment_run_id: UUID, *, lock: bool) -> ExperimentRunRecord:
        row = self._connection.execute(
            """
            SELECT experiment_run_id, experiment_id,
                   experiment_partition_id, research_partition_id,
                   opened_at
            FROM mra.experiment_run
            WHERE experiment_run_id = %s
            """ + (" FOR SHARE" if lock else ""),
            (experiment_run_id,),
        ).fetchone()
        if row is None:
            raise RuntimeNotFoundError(f"ExperimentRun {experiment_run_id} does not exist")
        return ExperimentRunRecord(
            experiment_run_id=UUID(str(row[0])), experiment_id=UUID(str(row[1])),
            experiment_partition_id=UUID(str(row[2])), research_partition_id=UUID(str(row[3])),
            opened_at=row[4],
        )


__all__ = ["PostgresExperimentRepository"]
