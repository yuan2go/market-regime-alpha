"""Resolve exact completed FIT Evaluation samples and immutable Dataset cells."""

from __future__ import annotations

from decimal import Decimal
import json
from typing import Any
from uuid import UUID, uuid5

import psycopg

from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from market_regime_alpha.infrastructure.postgres.queries.candidate_research_inputs import (
    load_research_dataset_definition,
)
from market_regime_alpha.research_qualification.domain.manifest import (
    DecisionInputDatasetManifest,
    parse_decision_input_dataset_manifest,
)
from market_regime_alpha.research_qualification.domain.model import ArtifactBinding
from market_regime_alpha.research_qualification.domain.research_models import (
    LinearTrainingRow,
    ModelDependencyVersion,
    ModelExecutionEnvironment,
    ModelScalarParameter,
    ModelScalarType,
    ModelTrainingReproducibility,
    ModelTrainingSamplePlan,
    ModelTrainingSampleState,
)
from market_regime_alpha.research_qualification.domain.vocabulary import (
    FeatureCellStatus,
)
from market_regime_alpha.research_qualification.ports.artifacts import (
    ResearchArtifactByteStore,
)
from market_regime_alpha.research_qualification.ports.model_inputs import (
    OpenModelTrainingRunRequest,
    PreparedModelTrainingInputs,
    PreparedReproducibleModelTrainingInputs,
    RegisteredModelTrainingInputs,
    RegisteredReproducibleModelTrainingInputs,
    ReproducibleModelTrainingRunRequest,
)
from market_regime_alpha.runtime.errors import (
    ArtifactIntegrityError,
    RuntimeNotFoundError,
    RuntimeStateConflictError,
)
from market_regime_alpha.shared.hashing import canonical_json_sha256, sha256_bytes
from market_regime_alpha.shared.identity import ContentHash


class PostgresModelTrainingInputProvider:
    """No Outcome resolver: consume only the exact revision already in Evaluation."""

    def __init__(
        self,
        pool: TargetPostgresPool,
        byte_store: ResearchArtifactByteStore,
    ) -> None:
        self._pool = pool
        self._byte_store = byte_store

    def prepare(
        self,
        request: OpenModelTrainingRunRequest,
    ) -> PreparedModelTrainingInputs:
        with self._pool.connection(read_only=True) as connection:
            feature_roster = _require_training_root(connection, request)
            source_rows = _training_source_rows(connection, request)
            dataset_contracts = {
                UUID(str(row[9])): load_research_dataset_definition(
                    connection,
                    dataset_id=UUID(str(row[9])),
                )
                for row in source_rows
            }

        manifests: dict[UUID, DecisionInputDatasetManifest] = {}
        for dataset_id, (definition, feature_definitions) in dataset_contracts.items():
            binding = definition.manifest_artifact
            verification = self._byte_store.verify(
                str(binding.content_sha256),
                expected_size=binding.size_bytes,
            )
            if verification.result != "VERIFIED":
                raise ArtifactIntegrityError(f"training Dataset {dataset_id} manifest bytes are not exact")
            content = self._byte_store.read_bytes(
                str(binding.content_sha256),
                expected_size=binding.size_bytes,
            )
            manifest = parse_decision_input_dataset_manifest(
                content,
                dataset=definition,
                feature_definitions=feature_definitions,
            )
            if manifest.content_sha256 != binding.content_sha256:
                raise ArtifactIntegrityError(f"training Dataset {dataset_id} manifest hash differs")
            manifests[dataset_id] = manifest

        samples: list[ModelTrainingSamplePlan] = []
        linear_rows: list[LinearTrainingRow] = []
        artifact_rows: list[dict[str, object]] = []
        feature_ids = tuple(item[0] for item in feature_roster)
        for ordinal, source in enumerate(source_rows, start=1):
            dataset_id = UUID(str(source[9]))
            instrument_id = UUID(str(source[8]))
            manifest = manifests[dataset_id]
            manifest_row = next(
                (item for item in manifest.rows if item.instrument_id == instrument_id),
                None,
            )
            if manifest_row is None:
                raise ArtifactIntegrityError("FIT commitment instrument is absent from exact Dataset manifest")
            cell_map = {item.feature_definition_id: item for item in manifest_row.cells}
            if not set(feature_ids).issubset(cell_map):
                raise ArtifactIntegrityError("FIT Dataset row omits a frozen Model feature")
            feature_values: list[Decimal] = []
            feature_payload: list[dict[str, object]] = []
            feature_failure: str | None = None
            for feature_id in feature_ids:
                cell = cell_map[feature_id]
                feature_payload.append(
                    {
                        "feature_definition_id": str(feature_id),
                        "reason_code": cell.reason_code,
                        "source_ids": [str(item) for item in cell.source_ids],
                        "status": cell.status.value,
                        "value": None if cell.value is None else str(cell.value),
                    }
                )
                if cell.status is not FeatureCellStatus.AVAILABLE:
                    feature_failure = f"FEATURE_{cell.status.value}"
                elif isinstance(cell.value, bool) or not isinstance(cell.value, (Decimal, int)):
                    raise ArtifactIntegrityError("Model feature roster contains a non-numeric value")
                else:
                    feature_values.append(Decimal(cell.value))

            evaluation_input_state = str(source[13])
            target_value = None if source[14] is None else Decimal(str(source[14]))
            if evaluation_input_state != "INCLUDED":
                state = ModelTrainingSampleState.NOT_ESTIMABLE
                reason_code = f"EVALUATION_{evaluation_input_state}"
            elif target_value is None:
                state = ModelTrainingSampleState.NOT_ESTIMABLE
                reason_code = f"SOURCE_{source[15]}"
            elif feature_failure is not None:
                state = ModelTrainingSampleState.NOT_ESTIMABLE
                reason_code = feature_failure
            else:
                state = ModelTrainingSampleState.ESTIMABLE
                reason_code = "COMPLETE_INPUT"
            vector_hash = (
                ContentHash(
                    canonical_json_sha256(
                        tuple(
                            {
                                "feature_definition_id": feature_id,
                                "value": value,
                            }
                            for feature_id, value in zip(
                                feature_ids,
                                feature_values,
                                strict=True,
                            )
                        )
                    )
                )
                if state is ModelTrainingSampleState.ESTIMABLE
                else None
            )
            sample_id = uuid5(
                request.model_training_run_id,
                str(UUID(str(source[1]))),
            )
            definition = dataset_contracts[dataset_id][0]
            sample = ModelTrainingSamplePlan(
                model_training_sample_id=sample_id,
                ordinal=ordinal,
                evaluation_observation_id=UUID(str(source[1])),
                evaluation_metric_observation_id=UUID(str(source[2])),
                research_partition_member_id=UUID(str(source[3])),
                commitment_id=UUID(str(source[4])),
                decision_run_id=UUID(str(source[5])),
                candidate_id=UUID(str(source[7])),
                instrument_id=instrument_id,
                dataset_id=dataset_id,
                dataset_manifest_artifact=definition.manifest_artifact,
                market_target_outcome_revision_id=UUID(str(source[11])),
                source_outcome_metric_id=UUID(str(source[12])),
                evaluation_input_state=evaluation_input_state,
                state=state,
                reason_code=reason_code,
                target_value=(target_value if state is ModelTrainingSampleState.ESTIMABLE else None),
                feature_vector_sha256=vector_hash,
            )
            samples.append(sample)
            if state is ModelTrainingSampleState.ESTIMABLE:
                assert target_value is not None
                linear_rows.append(
                    LinearTrainingRow(
                        sample.model_training_sample_id,
                        tuple(feature_values),
                        target_value,
                    )
                )
            artifact_rows.append(
                {
                    "dataset_id": str(dataset_id),
                    "dataset_manifest": _artifact_payload(definition.manifest_artifact),
                    "evaluation_input_state": evaluation_input_state,
                    "evaluation_observation_id": str(sample.evaluation_observation_id),
                    "feature_cells": feature_payload,
                    "feature_vector_sha256": (None if vector_hash is None else str(vector_hash)),
                    "instrument_id": str(instrument_id),
                    "model_training_sample_id": str(sample_id),
                    "ordinal": ordinal,
                    "reason_code": reason_code,
                    "source_outcome_metric_id": str(sample.source_outcome_metric_id),
                    "state": state.value,
                    "target_value": (None if sample.target_value is None else str(sample.target_value)),
                }
            )
        payload = {
            "evaluation_protocol_metric_id": str(request.evaluation_protocol_metric_id),
            "evaluation_run_id": str(request.evaluation_run_id),
            "feature_roster": [
                {
                    "feature_definition_id": str(identity),
                    "feature_definition_sha256": content_hash,
                    "ordinal": ordinal,
                }
                for ordinal, (identity, content_hash) in enumerate(
                    feature_roster,
                    start=1,
                )
            ],
            "model_id": str(request.model_id),
            "model_training_run_id": str(request.model_training_run_id),
            "samples": artifact_rows,
            "schema": "mra-model-training-input-v1",
        }
        content = json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return PreparedModelTrainingInputs(
            request=request,
            samples=tuple(samples),
            linear_rows=tuple(linear_rows),
            training_input_content=content,
            training_input_content_sha256=ContentHash(sha256_bytes(content)),
        )

    def prepare_reproducible(
        self,
        request: ReproducibleModelTrainingRunRequest,
    ) -> PreparedReproducibleModelTrainingInputs:
        legacy = request.training
        with self._pool.connection(read_only=True) as connection:
            cutoff_row = connection.execute("SELECT clock_timestamp()").fetchone()
            if cutoff_row is None:  # pragma: no cover - PostgreSQL invariant
                raise ArtifactIntegrityError("authoritative database clock is absent")
            training_knowledge_cutoff = cutoff_row[0]
            _require_reproducible_training_scope(connection, request)
            source_rows = _training_source_rows(connection, legacy)
        if any(row[16] > training_knowledge_cutoff for row in source_rows):
            raise ArtifactIntegrityError("training Outcome was not available by the authoritative cutoff")

        prepared = self.prepare(legacy)
        expected_revisions = tuple(UUID(str(row[11])) for row in source_rows)
        if tuple(sample.market_target_outcome_revision_id for sample in prepared.samples) != expected_revisions:
            raise ArtifactIntegrityError("training Outcome roster changed across immutable reads")
        reproducibility = ModelTrainingReproducibility(
            model_training_run_id=legacy.model_training_run_id,
            training_knowledge_cutoff=training_knowledge_cutoff,
            implementation_sha256=legacy.algorithm_sha256,
            environment=request.environment,
            hyperparameters=request.hyperparameters,
        )
        try:
            payload = json.loads(prepared.training_input_content.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:  # pragma: no cover
            raise ArtifactIntegrityError("prepared Model training input is malformed") from exc
        payload["schema"] = "mra-model-training-input-v2"
        payload["reproducibility"] = _reproducibility_payload(reproducibility)
        content = json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return PreparedReproducibleModelTrainingInputs(
            training=PreparedModelTrainingInputs(
                request=prepared.request,
                samples=prepared.samples,
                linear_rows=prepared.linear_rows,
                training_input_content=content,
                training_input_content_sha256=ContentHash(sha256_bytes(content)),
            ),
            reproducibility=reproducibility,
        )

    def load_registered(
        self,
        model_training_run_id: UUID,
    ) -> RegisteredModelTrainingInputs:
        with self._pool.connection(read_only=True) as connection:
            row = connection.execute(
                """
                SELECT training.model_id, training.algorithm_code,
                       training.algorithm_version, training.algorithm_sha256,
                       training.ridge_alpha, training.random_seed, training.sample_count,
                       training.estimable_count,
                       training.training_input_artifact_id,
                       training.training_input_content_sha256,
                       training.training_input_size_bytes,
                       training.code_artifact_id,
                       training.code_content_sha256,
                       training.code_size_bytes,
                       training.config_artifact_id,
                       training.config_content_sha256,
                       training.config_size_bytes
                FROM mra.model_training_run AS training
                WHERE training.model_training_run_id = %s
                """,
                (model_training_run_id,),
            ).fetchone()
            if row is None:
                raise RuntimeNotFoundError(f"ModelTrainingRun {model_training_run_id} does not exist")
            feature_ids = tuple(
                UUID(str(item[0]))
                for item in connection.execute(
                    """
                    SELECT feature.feature_definition_id
                    FROM mra.model_training_run AS training
                    JOIN mra.model_feature_definition AS feature
                      ON feature.model_id = training.model_id
                    WHERE training.model_training_run_id = %s
                    ORDER BY feature.ordinal
                    """,
                    (model_training_run_id,),
                ).fetchall()
            )
            sample_rows = tuple(
                (UUID(str(item[0])), str(item[1]), item[2])
                for item in connection.execute(
                    """
                    SELECT model_training_sample_id, sample_state, target_value
                    FROM mra.model_training_sample
                    WHERE model_training_run_id = %s ORDER BY ordinal
                    """,
                    (model_training_run_id,),
                ).fetchall()
            )
        binding = _binding(row[8:11])
        verification = self._byte_store.verify(
            str(binding.content_sha256),
            expected_size=binding.size_bytes,
        )
        if verification.result != "VERIFIED":
            raise ArtifactIntegrityError("Model training input Artifact bytes are not exact")
        content = self._byte_store.read_bytes(
            str(binding.content_sha256),
            expected_size=binding.size_bytes,
        )
        if sha256_bytes(content) != str(binding.content_sha256):
            raise ArtifactIntegrityError("Model training input Artifact hash differs")
        linear_rows = _parse_registered_training_input(
            content,
            model_training_run_id=model_training_run_id,
            feature_definition_ids=feature_ids,
            sample_rows=sample_rows,
        )
        if len(sample_rows) != int(row[6]) or len(linear_rows) != int(row[7]):
            raise ArtifactIntegrityError("Model training Artifact does not match frozen sample counts")
        return RegisteredModelTrainingInputs(
            model_training_run_id=model_training_run_id,
            model_id=UUID(str(row[0])),
            algorithm_code=str(row[1]),
            algorithm_version=str(row[2]),
            implementation_sha256=str(row[3]),
            training_input_artifact=binding,
            feature_definition_ids=feature_ids,
            linear_rows=linear_rows,
            ridge_alpha=Decimal(str(row[4])),
            random_seed=int(row[5]),
            code_artifact=_binding(row[11:14]),
            config_artifact=_binding(row[14:17]),
        )

    def load_registered_reproducible(
        self,
        model_training_run_id: UUID,
    ) -> RegisteredReproducibleModelTrainingInputs:
        training = self.load_registered(model_training_run_id)
        with self._pool.connection(read_only=True) as connection:
            root = connection.execute(
                """
                SELECT training_knowledge_cutoff, implementation_sha256,
                       python_implementation, python_version,
                       runtime_code, runtime_version, uv_lock_sha256,
                       dependency_count, dependency_roster_sha256,
                       hyperparameter_count, hyperparameter_roster_sha256,
                       environment_sha256, content_sha256
                FROM mra.model_training_reproducibility
                WHERE model_training_run_id = %s
                """,
                (model_training_run_id,),
            ).fetchone()
            if root is None:
                raise RuntimeStateConflictError("reproducible Model training closure is missing")
            dependency_rows = connection.execute(
                """
                SELECT ordinal, package_name, package_version,
                       distribution_sha256, content_sha256
                FROM mra.model_training_dependency
                WHERE model_training_run_id = %s ORDER BY ordinal
                """,
                (model_training_run_id,),
            ).fetchall()
            parameter_rows = connection.execute(
                """
                SELECT ordinal, parameter_code, value_type,
                       decimal_value, integer_value, boolean_value,
                       text_value, content_sha256
                FROM mra.model_training_hyperparameter
                WHERE model_training_run_id = %s ORDER BY ordinal
                """,
                (model_training_run_id,),
            ).fetchall()
        dependencies = tuple(
            ModelDependencyVersion(
                ordinal=int(row[0]),
                package_name=str(row[1]),
                package_version=str(row[2]),
                distribution_sha256=str(row[3]),
            )
            for row in dependency_rows
        )
        environment = ModelExecutionEnvironment(
            python_implementation=str(root[2]),
            python_version=str(root[3]),
            runtime_code=str(root[4]),
            runtime_version=str(root[5]),
            uv_lock_sha256=str(root[6]),
            dependencies=dependencies,
        )
        hyperparameters = tuple(
            ModelScalarParameter(
                ordinal=int(row[0]),
                parameter_code=str(row[1]),
                value_type=ModelScalarType(str(row[2])),
                decimal_value=(None if row[3] is None else Decimal(str(row[3]))),
                integer_value=(None if row[4] is None else int(row[4])),
                boolean_value=(None if row[5] is None else bool(row[5])),
                text_value=(None if row[6] is None else str(row[6])),
            )
            for row in parameter_rows
        )
        if (
            len(dependencies) != int(root[7])
            or str(environment.dependency_roster_sha256) != str(root[8])
            or len(hyperparameters) != int(root[9])
        ):
            raise ArtifactIntegrityError("Model reproducibility child roster does not reconcile")
        reproducibility = ModelTrainingReproducibility(
            model_training_run_id=model_training_run_id,
            training_knowledge_cutoff=root[0],
            implementation_sha256=str(root[1]),
            environment=environment,
            hyperparameters=hyperparameters,
        )
        if (
            str(reproducibility.hyperparameter_roster_sha256) != str(root[10])
            or str(environment.content_sha256) != str(root[11])
            or str(reproducibility.content_sha256) != str(root[12])
            or any(str(item.content_sha256) != str(row[4]) for item, row in zip(dependencies, dependency_rows, strict=True))
            or any(str(item.content_sha256) != str(row[7]) for item, row in zip(hyperparameters, parameter_rows, strict=True))
        ):
            raise ArtifactIntegrityError("Model reproducibility hashes do not reconcile")
        artifact_content = self._byte_store.read_bytes(
            str(training.training_input_artifact.content_sha256),
            expected_size=training.training_input_artifact.size_bytes,
        )
        try:
            artifact_payload = json.loads(artifact_content.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ArtifactIntegrityError("reproducible Model training Artifact is malformed") from exc
        if (
            not isinstance(artifact_payload, dict)
            or artifact_payload.get("schema") != "mra-model-training-input-v2"
            or artifact_payload.get("reproducibility") != _reproducibility_payload(reproducibility)
        ):
            raise ArtifactIntegrityError("Model training Artifact reproducibility closure differs")
        return RegisteredReproducibleModelTrainingInputs(
            training=training,
            reproducibility=reproducibility,
        )


def _require_training_root(
    connection: psycopg.Connection[Any],
    request: OpenModelTrainingRunRequest,
) -> tuple[tuple[UUID, str], ...]:
    row = connection.execute(
        """
        SELECT model.feature_count, model.feature_roster_sha256
        FROM mra.model AS model
        JOIN mra.evaluation_run AS evaluation
          ON evaluation.evaluation_run_id = %s
         AND evaluation.target_definition_id = model.target_definition_id
         AND evaluation.status = 'COMPLETED'
         AND evaluation.partition_purpose = 'FIT'
        JOIN mra.evaluation_protocol_metric AS metric
          ON metric.evaluation_protocol_metric_id = %s
         AND metric.evaluation_protocol_id = evaluation.evaluation_protocol_id
         AND metric.source_value_type = 'DECIMAL'
        JOIN mra.exploratory_backtest_run AS backtest
          ON backtest.exploratory_backtest_run_id = %s
         AND backtest.target_definition_id = model.target_definition_id
         AND backtest.feature_count = model.feature_count
         AND backtest.feature_roster_sha256 = model.feature_roster_sha256
         AND backtest.evidence_lane = 'EXPLORATORY_RETROSPECTIVE'
        JOIN mra.exploratory_backtest_arm AS arm
          ON arm.exploratory_backtest_arm_id = %s
         AND arm.exploratory_backtest_run_id = backtest.exploratory_backtest_run_id
        LEFT JOIN mra.backtest_specification AS specification
          ON specification.exploratory_backtest_run_id =
             backtest.exploratory_backtest_run_id
        LEFT JOIN mra.backtest_arm_specification AS arm_specification
          ON arm_specification.exploratory_backtest_arm_id =
             arm.exploratory_backtest_arm_id
         AND arm_specification.exploratory_backtest_run_id =
             arm.exploratory_backtest_run_id
         AND arm_specification.specification_sha256 =
             specification.specification_sha256
        JOIN mra.exploratory_backtest_fold AS fold
          ON fold.exploratory_backtest_fold_id = %s
         AND fold.exploratory_backtest_run_id = backtest.exploratory_backtest_run_id
         AND fold.purpose = 'FIT'
         AND fold.evaluation_protocol_id = evaluation.evaluation_protocol_id
        WHERE model.model_id = %s
          AND (
              (specification.exploratory_backtest_run_id IS NOT NULL
               AND arm_specification.execution_kind = 'MODEL'
               AND arm_specification.model_id = model.model_id)
              OR
              (specification.exploratory_backtest_run_id IS NULL
               AND arm.arm_kind IN (
                   'MODEL_CHALLENGER', 'RIDGE_CURRENT_CONTEXT',
                   'RIDGE_CONTEXT_OBSERVATIONAL'
               ))
          )
        """,
        (
            request.evaluation_run_id,
            request.evaluation_protocol_metric_id,
            request.exploratory_backtest_run_id,
            request.exploratory_backtest_arm_id,
            request.exploratory_backtest_fold_id,
            request.model_id,
        ),
    ).fetchone()
    if row is None:
        raise RuntimeStateConflictError("Model training requires exact completed FIT Evaluation/backtest parents")
    features = tuple(
        (UUID(str(item[0])), str(item[1]))
        for item in connection.execute(
            """
            SELECT feature_definition_id, feature_definition_sha256
            FROM mra.model_feature_definition
            WHERE model_id = %s ORDER BY ordinal
            """,
            (request.model_id,),
        ).fetchall()
    )
    if len(features) != int(row[0]) or canonical_json_sha256(
        tuple(
            {
                "feature_definition_id": identity,
                "feature_definition_sha256": content_hash,
                "ordinal": ordinal,
            }
            for ordinal, (identity, content_hash) in enumerate(features, start=1)
        )
    ) != str(row[1]):
        raise ArtifactIntegrityError("Model Feature roster does not reconcile")
    return features


def _require_reproducible_training_scope(
    connection: psycopg.Connection[Any],
    request: ReproducibleModelTrainingRunRequest,
) -> None:
    training = request.training
    row = connection.execute(
        """
        SELECT 1
        FROM mra.backtest_specification AS specification
        JOIN mra.backtest_arm_specification AS arm
          ON arm.exploratory_backtest_run_id =
             specification.exploratory_backtest_run_id
         AND arm.specification_sha256 = specification.specification_sha256
         AND arm.exploratory_backtest_arm_id = %s
         AND arm.execution_kind = 'MODEL'
         AND arm.model_id = %s
        JOIN mra.backtest_model_training_requirement AS requirement
          ON requirement.exploratory_backtest_run_id =
             specification.exploratory_backtest_run_id
         AND requirement.specification_sha256 =
             specification.specification_sha256
         AND requirement.exploratory_backtest_arm_id =
             arm.exploratory_backtest_arm_id
         AND requirement.model_id = arm.model_id
         AND requirement.fit_fold_id = %s
        JOIN mra.backtest_fold_dependency AS dependency
          ON dependency.exploratory_backtest_run_id =
             specification.exploratory_backtest_run_id
         AND dependency.specification_sha256 =
             specification.specification_sha256
         AND dependency.fit_fold_id = requirement.fit_fold_id
         AND dependency.validation_fold_id = requirement.validation_fold_id
         AND dependency.dependency_kind = 'MODEL_TRAINING'
        JOIN mra.evaluation_run AS evaluation
          ON evaluation.evaluation_run_id = %s
         AND evaluation.evaluation_protocol_id =
             requirement.required_fit_evaluation_protocol_id
         AND evaluation.partition_purpose = 'FIT'
         AND evaluation.status = 'COMPLETED'
        JOIN mra.evaluation_protocol_metric AS metric
          ON metric.evaluation_protocol_metric_id = %s
         AND metric.evaluation_protocol_id = evaluation.evaluation_protocol_id
        WHERE specification.exploratory_backtest_run_id = %s
        LIMIT 1
        """,
        (
            training.exploratory_backtest_arm_id,
            training.model_id,
            training.exploratory_backtest_fold_id,
            training.evaluation_run_id,
            training.evaluation_protocol_metric_id,
            training.exploratory_backtest_run_id,
        ),
    ).fetchone()
    if row is None:
        raise RuntimeStateConflictError("reproducible Model training requires an exact current specification dependency")


def _training_source_rows(
    connection: psycopg.Connection[Any],
    request: OpenModelTrainingRunRequest,
) -> tuple[tuple[Any, ...], ...]:
    rows = connection.execute(
        """
        SELECT member.member_ordinal,
               observation.evaluation_observation_id,
               input.evaluation_metric_observation_id,
               member.research_partition_member_id,
               member.commitment_id,
               commitment.decision_run_id,
               commitment.candidate_set_id,
               commitment.candidate_id,
               commitment.instrument_id,
               candidate_set.dataset_id,
               dataset.manifest_artifact_id,
               observation.market_target_outcome_revision_id,
               input.source_outcome_metric_id,
               input.input_state,
               outcome_metric.decimal_value,
               outcome_metric.value_status,
               outcome_revision.knowledge_cutoff
        FROM mra.evaluation_observation AS observation
        JOIN mra.research_partition_member AS member
          ON member.research_partition_member_id =
             observation.research_partition_member_id
        JOIN mra.decision_target_commitment AS commitment
          ON commitment.commitment_id = member.commitment_id
        JOIN mra.candidate_set AS candidate_set
          ON candidate_set.candidate_set_id = commitment.candidate_set_id
        JOIN mra.dataset AS dataset
          ON dataset.dataset_id = candidate_set.dataset_id
        JOIN mra.exploratory_backtest_dataset AS backtest_dataset
          ON backtest_dataset.dataset_id = dataset.dataset_id
         AND backtest_dataset.exploratory_backtest_run_id = %s
         AND backtest_dataset.exploratory_backtest_arm_id = %s
         AND backtest_dataset.exploratory_backtest_fold_id = %s
        JOIN mra.exploratory_backtest_fold_session AS fold_session
          ON fold_session.exploratory_backtest_fold_session_id =
             backtest_dataset.exploratory_backtest_fold_session_id
         AND fold_session.session_role = 'FIT_INPUT'
        JOIN mra.evaluation_metric_observation AS input
          ON input.evaluation_run_id = observation.evaluation_run_id
         AND input.evaluation_observation_id =
             observation.evaluation_observation_id
         AND input.evaluation_protocol_metric_id = %s
        JOIN mra.market_target_outcome_metric AS outcome_metric
          ON outcome_metric.market_target_outcome_metric_id =
             input.source_outcome_metric_id
         AND outcome_metric.market_target_outcome_revision_id =
             observation.market_target_outcome_revision_id
        JOIN mra.market_target_outcome_revision AS outcome_revision
          ON outcome_revision.market_target_outcome_revision_id =
             observation.market_target_outcome_revision_id
        WHERE observation.evaluation_run_id = %s
        ORDER BY member.member_ordinal
        """,
        (
            request.exploratory_backtest_run_id,
            request.exploratory_backtest_arm_id,
            request.exploratory_backtest_fold_id,
            request.evaluation_protocol_metric_id,
            request.evaluation_run_id,
        ),
    ).fetchall()
    if not rows:
        raise RuntimeNotFoundError("completed FIT Evaluation has no training samples")
    if tuple(int(row[0]) for row in rows) != tuple(sorted(int(row[0]) for row in rows)):
        raise ArtifactIntegrityError("FIT Evaluation roster order is unstable")
    return tuple(rows)


def _reproducibility_payload(
    reproducibility: ModelTrainingReproducibility,
) -> dict[str, object]:
    environment = reproducibility.environment
    return {
        "content_sha256": str(reproducibility.content_sha256),
        "environment": {
            "content_sha256": str(environment.content_sha256),
            "dependencies": [
                {
                    "content_sha256": str(item.content_sha256),
                    "distribution_sha256": str(item.distribution_sha256),
                    "ordinal": item.ordinal,
                    "package_name": item.package_name,
                    "package_version": item.package_version,
                }
                for item in environment.dependencies
            ],
            "dependency_roster_sha256": str(environment.dependency_roster_sha256),
            "python_implementation": environment.python_implementation,
            "python_version": environment.python_version,
            "runtime_code": environment.runtime_code,
            "runtime_version": environment.runtime_version,
            "uv_lock_sha256": str(environment.uv_lock_sha256),
        },
        "hyperparameter_roster_sha256": str(reproducibility.hyperparameter_roster_sha256),
        "hyperparameters": [
            {
                "boolean_value": item.boolean_value,
                "content_sha256": str(item.content_sha256),
                "decimal_value": (None if item.decimal_value is None else str(item.decimal_value)),
                "integer_value": item.integer_value,
                "ordinal": item.ordinal,
                "parameter_code": item.parameter_code,
                "text_value": item.text_value,
                "value_type": item.value_type.value,
            }
            for item in reproducibility.hyperparameters
        ],
        "implementation_sha256": str(reproducibility.implementation_sha256),
        "model_training_run_id": str(reproducibility.model_training_run_id),
        "training_knowledge_cutoff": (reproducibility.training_knowledge_cutoff.isoformat()),
    }


def _artifact_payload(binding: ArtifactBinding) -> dict[str, object]:
    return {
        "artifact_id": str(binding.artifact_id),
        "content_sha256": str(binding.content_sha256),
        "size_bytes": binding.size_bytes,
    }


def _binding(values: tuple[Any, ...]) -> ArtifactBinding:
    return ArtifactBinding(
        artifact_id=UUID(str(values[0])),
        content_sha256=str(values[1]),
        size_bytes=int(values[2]),
    )


def _parse_registered_training_input(
    content: bytes,
    *,
    model_training_run_id: UUID,
    feature_definition_ids: tuple[UUID, ...],
    sample_rows: tuple[tuple[UUID, str, Any], ...],
) -> tuple[LinearTrainingRow, ...]:
    try:
        payload = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ArtifactIntegrityError("Model training input Artifact is malformed") from exc
    if not isinstance(payload, dict) or payload.get("schema") not in {
        "mra-model-training-input-v1",
        "mra-model-training-input-v2",
    }:
        raise ArtifactIntegrityError("Model training input Artifact schema is invalid")
    if payload.get("model_training_run_id") != str(model_training_run_id):
        raise ArtifactIntegrityError("Model training input Artifact identity differs")
    raw_features = payload.get("feature_roster")
    raw_samples = payload.get("samples")
    if not isinstance(raw_features, list) or not isinstance(raw_samples, list):
        raise ArtifactIntegrityError("Model training input rosters are malformed")
    if tuple(UUID(str(item["feature_definition_id"])) for item in raw_features) != feature_definition_ids:
        raise ArtifactIntegrityError("Model training input Feature roster differs")
    authoritative = {identity: (state, value) for identity, state, value in sample_rows}
    if len(authoritative) != len(sample_rows) or len(raw_samples) != len(sample_rows):
        raise ArtifactIntegrityError("Model training input sample roster differs")
    result: list[LinearTrainingRow] = []
    observed: set[UUID] = set()
    for raw in raw_samples:
        if not isinstance(raw, dict):
            raise ArtifactIntegrityError("Model training input sample is malformed")
        sample_id = UUID(str(raw.get("model_training_sample_id")))
        if sample_id in observed or sample_id not in authoritative:
            raise ArtifactIntegrityError("Model training input sample identity differs")
        observed.add(sample_id)
        state, target_value = authoritative[sample_id]
        if raw.get("state") != state:
            raise ArtifactIntegrityError("Model training input sample state differs")
        if state != "ESTIMABLE":
            continue
        if target_value is None or raw.get("target_value") is None:
            raise ArtifactIntegrityError("estimable Model training target is missing")
        raw_cells = raw.get("feature_cells")
        if not isinstance(raw_cells, list) or len(raw_cells) != len(feature_definition_ids):
            raise ArtifactIntegrityError("Model training feature vector differs")
        values: list[Decimal] = []
        for feature_id, cell in zip(feature_definition_ids, raw_cells, strict=True):
            if (
                not isinstance(cell, dict)
                or cell.get("feature_definition_id") != str(feature_id)
                or cell.get("status") != "AVAILABLE"
                or cell.get("value") is None
            ):
                raise ArtifactIntegrityError("estimable Model feature cell differs")
            values.append(Decimal(str(cell["value"])))
        result.append(LinearTrainingRow(sample_id, tuple(values), Decimal(str(target_value))))
    if observed != set(authoritative):
        raise ArtifactIntegrityError("Model training input omitted a sample")
    return tuple(result)


__all__ = ["PostgresModelTrainingInputProvider"]
