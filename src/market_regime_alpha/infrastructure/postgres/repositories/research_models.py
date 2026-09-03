"""PostgreSQL writer for optional immutable Model Authority."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import psycopg

from market_regime_alpha.research_qualification.domain.research_models import (
    ModelTrainingRunPlan,
    ModelVersionPlan,
    ResearchModelPlan,
)
from market_regime_alpha.research_qualification.ports.model_uow import (
    ModelTrainingRunRecord,
    ModelVersionRecord,
    ResearchModelRecord,
)
from market_regime_alpha.runtime.errors import RuntimeNotFoundError


class PostgresResearchModelRepository:
    def __init__(self, connection: psycopg.Connection[Any]) -> None:
        self._connection = connection

    def lock_model_identity(self, model_code: str) -> None:
        self._connection.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            (f"research-model:{model_code}",),
        )

    def register_model(
        self,
        plan: ResearchModelPlan,
        *,
        request_identity: str,
        request_sha256: str,
    ) -> ResearchModelRecord:
        self._connection.execute(
            """
            INSERT INTO mra.model (
                model_id, model_code, target_definition_id, target_version,
                target_definition_sha256, feature_count,
                feature_roster_sha256,
                code_artifact_id, code_content_sha256, code_size_bytes,
                config_artifact_id, config_content_sha256, config_size_bytes,
                provenance_sha256, content_sha256,
                request_identity, request_sha256
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            """,
            (
                plan.model_id,
                plan.model_code,
                plan.target_definition_id,
                plan.target_version,
                str(plan.target_definition_sha256),
                plan.feature_count,
                str(plan.feature_roster_sha256),
                plan.code_artifact.artifact_id,
                str(plan.code_artifact.content_sha256),
                plan.code_artifact.size_bytes,
                plan.config_artifact.artifact_id,
                str(plan.config_artifact.content_sha256),
                plan.config_artifact.size_bytes,
                str(plan.provenance_sha256),
                str(plan.content_sha256),
                request_identity,
                request_sha256,
            ),
        )
        for ordinal, (feature_id, feature_hash) in enumerate(
            plan.feature_definitions,
            start=1,
        ):
            result = self._connection.execute(
                """
                INSERT INTO mra.model_feature_definition (
                    model_id, ordinal, feature_definition_id,
                    feature_definition_sha256, feature_value_type
                )
                SELECT %s, %s, feature_definition_id, content_sha256,
                       value_type
                FROM mra.feature_definition
                WHERE feature_definition_id = %s AND content_sha256 = %s
                  AND value_type IN ('DECIMAL', 'INTEGER')
                """,
                (plan.model_id, ordinal, feature_id, str(feature_hash)),
            )
            if result.rowcount != 1:
                raise RuntimeNotFoundError(
                    f"numeric FeatureDefinition {feature_id} is not exact"
                )
        self._connection.execute("SET CONSTRAINTS model_reconcile_guard IMMEDIATE")
        return self.model_record(plan.model_id, lock=False)

    def register_training_run(
        self,
        plan: ModelTrainingRunPlan,
        *,
        request_identity: str,
        request_sha256: str,
    ) -> ModelTrainingRunRecord:
        target_row = self._connection.execute(
            "SELECT target_definition_id FROM mra.model WHERE model_id = %s FOR SHARE",
            (plan.model_id,),
        ).fetchone()
        if target_row is None:
            raise RuntimeNotFoundError(f"Model {plan.model_id} does not exist")
        self._connection.execute(
            """
            INSERT INTO mra.model_training_run (
                model_training_run_id, model_id, evaluation_run_id,
                evaluation_protocol_metric_id, exploratory_backtest_run_id,
                exploratory_backtest_arm_id, exploratory_backtest_fold_id,
                target_definition_id,
                algorithm_code, algorithm_version, algorithm_sha256,
                ridge_alpha, random_seed, sample_count, estimable_count,
                sample_roster_sha256,
                training_input_artifact_id, training_input_content_sha256,
                training_input_size_bytes,
                code_artifact_id, code_content_sha256, code_size_bytes,
                config_artifact_id, config_content_sha256, config_size_bytes,
                provenance_sha256, content_sha256,
                request_identity, request_sha256
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s
            )
            """,
            (
                plan.model_training_run_id,
                plan.model_id,
                plan.evaluation_run_id,
                plan.evaluation_protocol_metric_id,
                plan.exploratory_backtest_run_id,
                plan.exploratory_backtest_arm_id,
                plan.exploratory_backtest_fold_id,
                UUID(str(target_row[0])),
                plan.algorithm_code,
                plan.algorithm_version,
                str(plan.algorithm_sha256),
                plan.ridge_alpha,
                plan.random_seed,
                plan.sample_count,
                plan.estimable_count,
                str(plan.sample_roster_sha256),
                plan.training_input_artifact.artifact_id,
                str(plan.training_input_artifact.content_sha256),
                plan.training_input_artifact.size_bytes,
                plan.code_artifact.artifact_id,
                str(plan.code_artifact.content_sha256),
                plan.code_artifact.size_bytes,
                plan.config_artifact.artifact_id,
                str(plan.config_artifact.content_sha256),
                plan.config_artifact.size_bytes,
                str(plan.provenance_sha256),
                str(plan.content_sha256),
                request_identity,
                request_sha256,
            ),
        )
        with self._connection.cursor() as cursor:
            cursor.executemany(
                """
                INSERT INTO mra.model_training_sample (
                    model_training_sample_id, model_training_run_id,
                    evaluation_run_id, evaluation_protocol_metric_id,
                    ordinal, evaluation_observation_id,
                    evaluation_metric_observation_id,
                    research_partition_member_id, commitment_id,
                    decision_run_id, candidate_id, instrument_id, dataset_id,
                    dataset_manifest_artifact_id,
                    dataset_manifest_content_sha256,
                    dataset_manifest_size_bytes,
                    market_target_outcome_revision_id,
                    source_outcome_metric_id, evaluation_input_state,
                    sample_state, reason_code, target_value,
                    feature_vector_sha256, content_sha256
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s
                )
                """,
                (
                    (
                        sample.model_training_sample_id,
                        plan.model_training_run_id,
                        plan.evaluation_run_id,
                        plan.evaluation_protocol_metric_id,
                        sample.ordinal,
                        sample.evaluation_observation_id,
                        sample.evaluation_metric_observation_id,
                        sample.research_partition_member_id,
                        sample.commitment_id,
                        sample.decision_run_id,
                        sample.candidate_id,
                        sample.instrument_id,
                        sample.dataset_id,
                        sample.dataset_manifest_artifact.artifact_id,
                        str(sample.dataset_manifest_artifact.content_sha256),
                        sample.dataset_manifest_artifact.size_bytes,
                        sample.market_target_outcome_revision_id,
                        sample.source_outcome_metric_id,
                        sample.evaluation_input_state,
                        sample.state.value,
                        sample.reason_code,
                        sample.target_value,
                        None
                        if sample.feature_vector_sha256 is None
                        else str(sample.feature_vector_sha256),
                        str(sample.content_sha256),
                    )
                    for sample in plan.samples
                ),
            )
        self._connection.execute(
            "SET CONSTRAINTS model_training_run_reconcile_guard IMMEDIATE"
        )
        return self.training_run_record(plan.model_training_run_id, lock=False)

    def register_version(
        self,
        plan: ModelVersionPlan,
        *,
        request_identity: str,
        request_sha256: str,
    ) -> ModelVersionRecord:
        self._connection.execute(
            """
            INSERT INTO mra.model_version (
                model_version_id, model_id, version, model_training_run_id,
                training_input_artifact_id, training_input_content_sha256,
                training_input_size_bytes,
                fitted_model_artifact_id, fitted_model_content_sha256,
                fitted_model_size_bytes, coefficient_count,
                code_artifact_id, code_content_sha256, code_size_bytes,
                config_artifact_id, config_content_sha256, config_size_bytes,
                provenance_sha256, content_sha256,
                request_identity, request_sha256
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            """,
            (
                plan.model_version_id,
                plan.model_id,
                plan.version,
                plan.model_training_run_id,
                plan.training_input_artifact.artifact_id,
                str(plan.training_input_artifact.content_sha256),
                plan.training_input_artifact.size_bytes,
                plan.fitted_model_artifact.artifact_id,
                str(plan.fitted_model_artifact.content_sha256),
                plan.fitted_model_artifact.size_bytes,
                plan.coefficient_count,
                plan.code_artifact.artifact_id,
                str(plan.code_artifact.content_sha256),
                plan.code_artifact.size_bytes,
                plan.config_artifact.artifact_id,
                str(plan.config_artifact.content_sha256),
                plan.config_artifact.size_bytes,
                str(plan.provenance_sha256),
                str(plan.content_sha256),
                request_identity,
                request_sha256,
            ),
        )
        return self.version_record(plan.model_version_id, lock=False)

    def model_record(self, model_id: UUID, *, lock: bool) -> ResearchModelRecord:
        suffix = " FOR SHARE" if lock else ""
        row = self._connection.execute(
            """
            SELECT model_id, model_code, target_definition_id, feature_count,
                   feature_roster_sha256, content_sha256, registered_at
            FROM mra.model WHERE model_id = %s
            """
            + suffix,
            (model_id,),
        ).fetchone()
        if row is None:
            raise RuntimeNotFoundError(f"Model {model_id} does not exist")
        return ResearchModelRecord(
            UUID(str(row[0])), str(row[1]), UUID(str(row[2])), int(row[3]),
            str(row[4]), str(row[5]), row[6]
        )

    def training_run_record(
        self, model_training_run_id: UUID, *, lock: bool
    ) -> ModelTrainingRunRecord:
        suffix = " FOR SHARE" if lock else ""
        row = self._connection.execute(
            """
            SELECT model_training_run_id, model_id, evaluation_run_id,
                   exploratory_backtest_run_id, exploratory_backtest_fold_id,
                   sample_count, estimable_count, sample_roster_sha256,
                   training_input_artifact_id, content_sha256, opened_at
            FROM mra.model_training_run WHERE model_training_run_id = %s
            """
            + suffix,
            (model_training_run_id,),
        ).fetchone()
        if row is None:
            raise RuntimeNotFoundError(
                f"ModelTrainingRun {model_training_run_id} does not exist"
            )
        return ModelTrainingRunRecord(
            UUID(str(row[0])), UUID(str(row[1])), UUID(str(row[2])),
            UUID(str(row[3])), UUID(str(row[4])), int(row[5]), int(row[6]),
            str(row[7]), UUID(str(row[8])), str(row[9]), row[10]
        )

    def version_record(
        self, model_version_id: UUID, *, lock: bool
    ) -> ModelVersionRecord:
        suffix = " FOR SHARE" if lock else ""
        row = self._connection.execute(
            """
            SELECT model_version_id, model_id, version,
                   model_training_run_id, fitted_model_artifact_id,
                   content_sha256, registered_at
            FROM mra.model_version WHERE model_version_id = %s
            """
            + suffix,
            (model_version_id,),
        ).fetchone()
        if row is None:
            raise RuntimeNotFoundError(
                f"ModelVersion {model_version_id} does not exist"
            )
        return ModelVersionRecord(
            UUID(str(row[0])), UUID(str(row[1])), int(row[2]), UUID(str(row[3])),
            UUID(str(row[4])), str(row[5]), row[6]
        )


__all__ = ["PostgresResearchModelRepository"]
