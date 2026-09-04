"""Prepare exact later-fold ModelVersion inputs outside the write transaction."""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

import psycopg

from market_regime_alpha.decision_support.domain import (
    DecisionArtifactBinding,
    ModelForecastPrediction,
    ModelPredictionState,
)
from market_regime_alpha.decision_support.errors import (
    InferenceAuthorityIntegrityError,
)
from market_regime_alpha.decision_support.ports import (
    InferenceInputPreparationProvider,
    ModelForecastBindingSummary,
    PreparedModelForecastInputs,
)
from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from market_regime_alpha.infrastructure.postgres.queries.candidate_research_inputs import (
    load_research_dataset_definition,
)
from market_regime_alpha.infrastructure.postgres.queries.model_training_inputs import (
    PostgresModelTrainingInputProvider,
)
from market_regime_alpha.research_qualification.domain.manifest import (
    parse_decision_input_dataset_manifest,
)
from market_regime_alpha.research_qualification.domain.model import ArtifactBinding
from market_regime_alpha.research_qualification.domain.vocabulary import (
    FeatureCellStatus,
)
from market_regime_alpha.research_qualification.ports.artifacts import (
    ResearchArtifactByteStore,
)
from market_regime_alpha.research_qualification.ports.model_execution import (
    FrozenModelVersionPayload,
    ModelPredictionBatch,
    ModelPredictionRow,
    ModelPredictor,
    ModelScalarParameter,
    ModelScalarType,
)
from market_regime_alpha.runtime.errors import ArtifactIntegrityError
from market_regime_alpha.shared.hashing import canonical_json_sha256, sha256_bytes
from market_regime_alpha.shared.identity import ContentHash


class PostgresModelForecastInputPreparationProvider:
    def __init__(
        self,
        pool: TargetPostgresPool,
        byte_store: ResearchArtifactByteStore,
        inference: InferenceInputPreparationProvider,
        predictor: ModelPredictor,
    ) -> None:
        self._pool = pool
        self._byte_store = byte_store
        self._inference = inference
        self._predictor = predictor

    def prepare(
        self,
        decision_run_id: UUID,
        strategy_version_id: UUID,
        model_version_id: UUID,
    ) -> PreparedModelForecastInputs:
        inference = self._inference.prepare(decision_run_id, strategy_version_id)
        with self._pool.connection(read_only=True) as connection:
            root = _load_root(connection, decision_run_id, model_version_id)
            definition, feature_definitions = load_research_dataset_definition(
                connection,
                dataset_id=UUID(str(root[0])),
            )
            model_features = tuple(
                UUID(str(row[0]))
                for row in connection.execute(
                    """
                    SELECT feature_definition_id
                    FROM mra.model_feature_definition
                    WHERE model_id = %s ORDER BY ordinal
                    """,
                    (root[7],),
                ).fetchall()
            )

        fitted_binding = _binding(root[14:17])
        fitted_bytes = _read_exact(
            self._byte_store,
            fitted_binding,
            context="fitted ModelVersion",
        )
        if bool(root[26]):
            registered = PostgresModelTrainingInputProvider(
                self._pool,
                self._byte_store,
            ).load_registered_reproducible(UUID(str(root[8])))
            if registered.training.model_id != UUID(str(root[7])):
                raise ArtifactIntegrityError(
                    "Model Forecast reproducibility Model differs"
                )
            hyperparameters = tuple(
                ModelScalarParameter(
                    parameter_code=item.parameter_code,
                    value_type=ModelScalarType(item.value_type.value),
                    decimal_value=item.decimal_value,
                    integer_value=item.integer_value,
                    boolean_value=item.boolean_value,
                    text_value=item.text_value,
                )
                for item in registered.reproducibility.hyperparameters
            )
        else:
            hyperparameters = (
                ModelScalarParameter(
                    parameter_code="ridge_alpha",
                    value_type=ModelScalarType.DECIMAL,
                    decimal_value=Decimal(str(root[20])),
                ),
            )
        frozen_model = FrozenModelVersionPayload(
            algorithm_code=str(root[23]),
            algorithm_version=str(root[24]),
            implementation_sha256=str(root[25]),
            fitted_content=fitted_bytes,
            fitted_content_sha256=fitted_binding.content_sha256,
            feature_definition_ids=model_features,
            hyperparameters=hyperparameters,
            seed=int(root[21]),
            coefficient_count=int(root[19]),
        )

        manifest_bytes = _read_exact(
            self._byte_store,
            definition.manifest_artifact,
            context="Model Forecast Dataset manifest",
        )
        manifest = parse_decision_input_dataset_manifest(
            manifest_bytes,
            dataset=definition,
            feature_definitions=feature_definitions,
        )
        if manifest.content_sha256 != definition.manifest_artifact.content_sha256:
            raise ArtifactIntegrityError("Model Forecast Dataset manifest hash differs")
        manifest_rows = {item.instrument_id: item for item in manifest.rows}
        if len(manifest_rows) != len(manifest.rows):
            raise ArtifactIntegrityError("Model Forecast Dataset rows are ambiguous")

        rules = inference.signal_inputs.strategy_version.forecast_rules
        if len(rules) != 1 or rules[0].target_metric_definition_id != UUID(
            str(root[18])
        ):
            raise InferenceAuthorityIntegrityError(
                "Model Forecast requires one exact training-target Strategy rule"
            )
        if any(
            commitment.target_definition_id != UUID(str(root[22]))
            for commitment in inference.commitments
        ):
            raise InferenceAuthorityIntegrityError(
                "ModelVersion Target differs from Forecast commitments"
            )

        predictions: list[ModelForecastPrediction] = []
        for commitment in inference.commitments:
            row = manifest_rows.get(commitment.instrument_id)
            if row is None:
                raise ArtifactIntegrityError(
                    "Model Forecast commitment instrument is absent from Dataset"
                )
            cells = {item.feature_definition_id: item for item in row.cells}
            if not set(model_features).issubset(cells):
                raise ArtifactIntegrityError(
                    "Model Forecast Dataset row omits a Model feature"
                )
            payload: list[dict[str, object]] = []
            values: list[Decimal] = []
            failure: str | None = None
            for feature_id in model_features:
                cell = cells[feature_id]
                payload.append(
                    {
                        "feature_definition_id": feature_id,
                        "reason_code": cell.reason_code,
                        "source_ids": cell.source_ids,
                        "status": cell.status,
                        "value": cell.value,
                    }
                )
                if cell.status is not FeatureCellStatus.AVAILABLE:
                    failure = f"FEATURE_{cell.status.value}"
                elif isinstance(cell.value, bool) or not isinstance(
                    cell.value,
                    (Decimal, int),
                ):
                    raise ArtifactIntegrityError(
                        "Model Forecast feature is not numeric"
                    )
                else:
                    values.append(Decimal(cell.value))
            vector_hash = ContentHash(canonical_json_sha256(tuple(payload)))
            predictions.append(
                ModelForecastPrediction(
                    candidate_id=commitment.candidate_id,
                    commitment_id=commitment.commitment_id,
                    dataset_id=definition.dataset_id,
                    feature_vector_sha256=vector_hash,
                    state=(
                        ModelPredictionState.AVAILABLE
                        if failure is None
                        else ModelPredictionState.NOT_ESTIMABLE
                    ),
                    reason_code=(
                        "MODEL_ESTIMATE_AVAILABLE"
                        if failure is None
                        else failure
                    ),
                    point_estimate=(
                        _predict_one(
                            self._predictor,
                            frozen_model,
                            commitment.commitment_id,
                            tuple(values),
                        )
                        if failure is None
                        else None
                    ),
                )
            )
        return PreparedModelForecastInputs(
            inference=inference,
            dataset_id=UUID(str(root[0])),
            exploratory_backtest_run_id=UUID(str(root[1])),
            exploratory_backtest_arm_id=UUID(str(root[2])),
            exploratory_backtest_fold_id=UUID(str(root[3])),
            exploratory_backtest_fold_session_id=UUID(str(root[4])),
            inference_fold_ordinal=int(root[5]),
            model_version_id=model_version_id,
            model_id=UUID(str(root[7])),
            model_training_run_id=UUID(str(root[8])),
            training_fold_id=UUID(str(root[9])),
            training_fold_ordinal=int(root[10]),
            model_version_sha256=str(root[11]),
            fitted_model_artifact=fitted_binding,
            model_registered_at=root[17],
            target_metric_definition_id=UUID(str(root[18])),
            predictions=tuple(predictions),
        )


class PostgresModelForecastQueryProvider:
    def __init__(self, pool: TargetPostgresPool) -> None:
        self._pool = pool

    def summary(
        self,
        forecast_group_id: UUID,
    ) -> ModelForecastBindingSummary | None:
        with self._pool.connection(read_only=True) as connection:
            rows = connection.execute(
                """
                SELECT binding.model_version_id,
                       binding.forecast_model_binding_id,
                       binding.content_sha256,
                       forecast.ordinal,
                       receipt.result_hash
                FROM mra.forecast_model_binding AS binding
                JOIN mra.forecast AS forecast
                  ON forecast.forecast_id = binding.forecast_id
                 AND forecast.forecast_group_id = binding.forecast_group_id
                JOIN mra.forecast_run AS run
                  ON run.forecast_group_id = binding.forecast_group_id
                JOIN mra.command_receipt AS receipt
                  ON receipt.receipt_id = run.command_receipt_id
                 AND receipt.status = 'SUCCEEDED'
                WHERE binding.forecast_group_id = %s
                ORDER BY forecast.ordinal
                """,
                (forecast_group_id,),
            ).fetchall()
        if not rows:
            return None
        model_versions = {UUID(str(item[0])) for item in rows}
        result_hashes = {str(item[4]) for item in rows}
        if len(model_versions) != 1 or len(result_hashes) != 1:
            raise InferenceAuthorityIntegrityError(
                "Model Forecast replay identity is ambiguous"
            )
        return ModelForecastBindingSummary(
            forecast_group_id=forecast_group_id,
            model_version_id=next(iter(model_versions)),
            binding_count=len(rows),
            binding_roster_sha256=canonical_json_sha256(
                tuple(
                    {
                        "content_sha256": str(item[2]),
                        "forecast_model_binding_id": UUID(str(item[1])),
                        "ordinal": int(item[3]),
                    }
                    for item in rows
                )
            ),
            receipt_result_hash=next(iter(result_hashes)),
        )


def _load_root(
    connection: psycopg.Connection[Any],
    decision_run_id: UUID,
    model_version_id: UUID,
    *,
    lock: bool = False,
) -> tuple[Any, ...]:
    suffix = (
        " FOR SHARE OF decision, retrospective, dataset, arm, inference_fold, "
        "version, training, training_fold, model"
        if lock
        else ""
    )
    row = connection.execute(
        """
        SELECT retrospective.dataset_id,
               retrospective.exploratory_backtest_run_id,
               retrospective.exploratory_backtest_arm_id,
               retrospective.exploratory_backtest_fold_id,
               retrospective.exploratory_backtest_fold_session_id,
               inference_fold.ordinal,
               decision.decision_time,
               version.model_id,
               version.model_training_run_id,
               training.exploratory_backtest_fold_id,
               training_fold.ordinal,
               version.content_sha256,
               training.exploratory_backtest_run_id,
               training.exploratory_backtest_arm_id,
               version.fitted_model_artifact_id,
               version.fitted_model_content_sha256,
               version.fitted_model_size_bytes,
               version.registered_at,
               metric.source_target_metric_definition_id,
               version.coefficient_count,
               training.ridge_alpha,
               training.random_seed,
               model.target_definition_id,
               training.algorithm_code,
               training.algorithm_version,
               training.algorithm_sha256,
               specification.exploratory_backtest_run_id IS NOT NULL
        FROM mra.decision_run AS decision
        JOIN mra.exploratory_retrospective_decision_run AS retrospective
          ON retrospective.decision_run_id = decision.decision_run_id
        JOIN mra.exploratory_backtest_dataset AS dataset
          ON dataset.dataset_id = retrospective.dataset_id
         AND dataset.exploratory_backtest_run_id =
             retrospective.exploratory_backtest_run_id
         AND dataset.exploratory_backtest_arm_id =
             retrospective.exploratory_backtest_arm_id
         AND dataset.exploratory_backtest_fold_id =
             retrospective.exploratory_backtest_fold_id
         AND dataset.exploratory_backtest_fold_session_id =
             retrospective.exploratory_backtest_fold_session_id
        JOIN mra.exploratory_backtest_arm AS arm
          ON arm.exploratory_backtest_arm_id =
             retrospective.exploratory_backtest_arm_id
         AND arm.exploratory_backtest_run_id =
             retrospective.exploratory_backtest_run_id
        LEFT JOIN mra.backtest_specification AS specification
          ON specification.exploratory_backtest_run_id =
             retrospective.exploratory_backtest_run_id
        LEFT JOIN mra.backtest_arm_specification AS arm_specification
          ON arm_specification.exploratory_backtest_arm_id =
             arm.exploratory_backtest_arm_id
         AND arm_specification.exploratory_backtest_run_id =
             arm.exploratory_backtest_run_id
         AND arm_specification.specification_sha256 =
             specification.specification_sha256
        JOIN mra.exploratory_backtest_fold AS inference_fold
          ON inference_fold.exploratory_backtest_fold_id =
             retrospective.exploratory_backtest_fold_id
         AND inference_fold.exploratory_backtest_run_id =
             retrospective.exploratory_backtest_run_id
         AND inference_fold.purpose IN ('DISCOVERY', 'VALIDATION')
        JOIN mra.exploratory_backtest_fold_session AS session
          ON session.exploratory_backtest_fold_session_id =
             retrospective.exploratory_backtest_fold_session_id
         AND session.exploratory_backtest_fold_id =
             inference_fold.exploratory_backtest_fold_id
         AND session.session_role = 'EVALUATION'
        JOIN mra.model_version AS version
          ON version.model_version_id = %s
        JOIN mra.model_training_run AS training
          ON training.model_training_run_id = version.model_training_run_id
         AND training.model_id = version.model_id
         AND training.exploratory_backtest_run_id =
             retrospective.exploratory_backtest_run_id
         AND training.exploratory_backtest_arm_id =
             retrospective.exploratory_backtest_arm_id
        JOIN mra.exploratory_backtest_fold AS training_fold
          ON training_fold.exploratory_backtest_fold_id =
             training.exploratory_backtest_fold_id
         AND training_fold.exploratory_backtest_run_id =
             training.exploratory_backtest_run_id
         AND training_fold.purpose = 'FIT'
        JOIN mra.model AS model ON model.model_id = version.model_id
        JOIN mra.evaluation_protocol_metric AS metric
          ON metric.evaluation_protocol_metric_id =
             training.evaluation_protocol_metric_id
        WHERE decision.decision_run_id = %s
          AND version.registered_at < clock_timestamp()
          AND NOT EXISTS (
              SELECT 1
              FROM mra.model_training_sample AS sample
              JOIN mra.decision_run AS source_decision
                ON source_decision.decision_run_id = sample.decision_run_id
              WHERE sample.model_training_run_id =
                    training.model_training_run_id
                AND source_decision.decision_time >= decision.decision_time
          )
          AND (
              (specification.exploratory_backtest_run_id IS NOT NULL
               AND arm_specification.execution_kind = 'MODEL'
               AND arm_specification.model_id = version.model_id
               AND EXISTS (
                   SELECT 1
                   FROM mra.backtest_model_lineage AS lineage
                   JOIN mra.backtest_model_training_requirement AS requirement
                     ON requirement.backtest_model_training_requirement_id =
                        lineage.model_training_requirement_id
                    AND requirement.exploratory_backtest_run_id =
                        retrospective.exploratory_backtest_run_id
                    AND requirement.exploratory_backtest_arm_id =
                        retrospective.exploratory_backtest_arm_id
                    AND requirement.fit_fold_id =
                        training.exploratory_backtest_fold_id
                    AND requirement.validation_fold_id =
                        inference_fold.exploratory_backtest_fold_id
                   JOIN mra.backtest_fold_dependency AS dependency
                     ON dependency.exploratory_backtest_run_id =
                        requirement.exploratory_backtest_run_id
                    AND dependency.fit_fold_id = requirement.fit_fold_id
                    AND dependency.validation_fold_id =
                        requirement.validation_fold_id
                   WHERE lineage.model_training_run_id =
                         training.model_training_run_id
                     AND lineage.model_version_id = version.model_version_id
               ))
              OR
              (specification.exploratory_backtest_run_id IS NULL
               AND arm.arm_kind IN (
                   'MODEL_CHALLENGER', 'RIDGE_CURRENT_CONTEXT',
                   'RIDGE_CONTEXT_OBSERVATIONAL'
               )
               AND training_fold.ordinal < inference_fold.ordinal)
          )
        """
        + suffix,
        (model_version_id, decision_run_id),
    ).fetchone()
    if row is None:
        raise InferenceAuthorityIntegrityError(
            "Model Forecast requires an exact later-fold retrospective Decision"
        )
    return tuple(row)


def _predict_one(
    predictor: ModelPredictor,
    model: FrozenModelVersionPayload,
    row_id: UUID,
    features: tuple[Decimal, ...],
) -> Decimal:
    result = predictor.predict(
        model,
        ModelPredictionBatch((ModelPredictionRow(row_id, features),)),
    )
    if len(result) != 1 or result[0].row_id != row_id:
        raise InferenceAuthorityIntegrityError(
            "ModelPredictor output does not match the exact input roster"
        )
    return result[0].point_estimate


def _binding(values: tuple[Any, ...]) -> DecisionArtifactBinding:
    return DecisionArtifactBinding(
        artifact_id=UUID(str(values[0])),
        content_sha256=str(values[1]),
        size_bytes=int(values[2]),
    )


def _read_exact(
    store: ResearchArtifactByteStore,
    binding: DecisionArtifactBinding | ArtifactBinding,
    *,
    context: str,
) -> bytes:
    verification = store.verify(
        str(binding.content_sha256),
        expected_size=binding.size_bytes,
    )
    if verification.result != "VERIFIED":
        raise ArtifactIntegrityError(f"{context} bytes are not exact")
    content = store.read_bytes(
        str(binding.content_sha256),
        expected_size=binding.size_bytes,
    )
    if sha256_bytes(content) != str(binding.content_sha256):
        raise ArtifactIntegrityError(f"{context} hash differs")
    return content


__all__ = [
    "PostgresModelForecastInputPreparationProvider",
    "PostgresModelForecastQueryProvider",
]
