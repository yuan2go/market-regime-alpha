"""PostgreSQL journal for exploratory model selection, artifacts and inference."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from psycopg.types.json import Jsonb

from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.application.research_validation.research_model import (
    RegularizedLinearForecastExecutor,
    ResearchInferenceRequest,
    ResearchModelArtifact,
    ResearchModelInferenceReceipt,
    ResearchModelTrainingRequest,
    research_model_parameter_hash,
    train_research_model,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from market_regime_alpha.persistence.postgres.migrator import PostgresMigrator


class PostgresResearchModelRepository:
    def __init__(
        self,
        factory: PostgresConnectionFactory,
        *,
        apply_migrations: bool = True,
    ) -> None:
        self._factory = factory
        if apply_migrations:
            PostgresMigrator().apply_all(factory)

    def publish_request(
        self, request: ResearchModelTrainingRequest
    ) -> ResearchModelTrainingRequest:
        def operation(connection: Any) -> None:
            connection.execute(
                """
                INSERT INTO research_model_training_request(
                    request_id, request_hash, model_definition_id,
                    model_definition_hash, configuration_id, configuration_hash,
                    feature_catalog_id, target_protocol_id,
                    experiment_definition_id, experiment_definition_hash,
                    locked_oos_partition_id, locked_oos_partition_hash,
                    oos_start_date, fold_seed, code_revision, code_hash,
                    formal_pit, formal_oos, calibrated, payload_json, requested_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, false, false, false, %s, %s
                ) ON CONFLICT (request_id) DO NOTHING
                """,
                (
                    str(request.request_id),
                    request.request_hash,
                    str(request.model_definition_reference.artifact_id),
                    request.model_definition_reference.content_hash,
                    str(request.configuration_reference.artifact_id),
                    request.configuration_reference.content_hash,
                    str(request.feature_catalog_reference.artifact_id),
                    str(request.target_protocol_reference.artifact_id),
                    (
                        None
                        if request.experiment_definition is None
                        else str(request.experiment_definition.definition_id)
                    ),
                    (
                        None
                        if request.experiment_definition is None
                        else request.experiment_definition.definition_hash
                    ),
                    str(request.locked_oos_reference.artifact_id),
                    request.locked_oos_reference.content_hash,
                    request.oos_start_date,
                    request.fold_seed,
                    request.code_revision,
                    request.code_hash,
                    Jsonb(request.to_canonical_dict()),
                    request.requested_at,
                ),
            )
            stored = connection.execute(
                "SELECT request_hash, payload_json FROM research_model_training_request WHERE request_id = %s",
                (str(request.request_id),),
            ).fetchone()
            if stored is None or str(stored[0]) != request.request_hash or stored[1] != request.to_canonical_dict():
                raise ValueError("Research Model request identity conflict")
            for ordinal, sample in enumerate(request.samples, start=1):
                connection.execute(
                    """
                    INSERT INTO research_model_training_sample(
                        request_id, ordinal, sample_id, sample_hash, symbol,
                        trading_date, decision_time, payload_json
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (request_id, ordinal) DO NOTHING
                    """,
                    (
                        str(request.request_id), ordinal, str(sample.sample_id),
                        sample.sample_hash, sample.symbol, sample.trading_date,
                        sample.decision_time, Jsonb(sample.to_canonical_dict()),
                    ),
                )
                for feature in sample.features:
                    connection.execute(
                        """
                        INSERT INTO research_model_training_feature(
                            request_id, sample_id, feature_name, available_at,
                            source_artifact_id, source_content_hash, payload_json
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (request_id, sample_id, feature_name) DO NOTHING
                        """,
                        (
                            str(request.request_id), str(sample.sample_id), feature.name,
                            feature.available_at, str(feature.source_reference.artifact_id),
                            feature.source_reference.content_hash,
                            Jsonb(feature.to_canonical_dict()),
                        ),
                    )
                for target in sample.targets:
                    connection.execute(
                        """
                        INSERT INTO research_model_training_target(
                            request_id, sample_id, target_name, available_at,
                            source_artifact_id, source_content_hash, payload_json
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (request_id, sample_id, target_name) DO NOTHING
                        """,
                        (
                            str(request.request_id), str(sample.sample_id), target.name,
                            target.available_at, str(target.source_reference.artifact_id),
                            target.source_reference.content_hash,
                            Jsonb(target.to_canonical_dict()),
                        ),
                    )
            for fold in request.folds:
                connection.execute(
                    """
                    INSERT INTO research_model_walk_forward_fold(
                        request_id, fold_name, payload_json
                    ) VALUES (%s, %s, %s)
                    ON CONFLICT (request_id, fold_name) DO NOTHING
                    """,
                    (str(request.request_id), fold.fold_name, Jsonb(fold.to_canonical_dict())),
                )
            for ordinal, reference in enumerate(_request_sources(request), start=1):
                connection.execute(
                    """
                    INSERT INTO research_model_training_source_binding(
                        request_id, ordinal, artifact_kind, artifact_id, content_hash
                    ) VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (request_id, ordinal) DO NOTHING
                    """,
                    (
                        str(request.request_id), ordinal, reference.artifact_kind,
                        str(reference.artifact_id), reference.content_hash,
                    ),
                )
            self._verify_request_projections(connection, request)

        self._factory.run_transaction(operation)
        return self.get_request(request.request_id)

    def get_request(self, request_id: ArtifactId) -> ResearchModelTrainingRequest:
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                "SELECT request_hash, payload_json FROM research_model_training_request WHERE request_id = %s",
                (str(request_id),),
            ).fetchone()
            if row is None or not isinstance(row[1], dict):
                raise KeyError(str(request_id))
            request = ResearchModelTrainingRequest.from_canonical_dict(row[1])
            if str(row[0]) != request.request_hash:
                raise ValueError("Research Model request owner hash diverged")
            self._verify_request_projections(connection, request)
        return request

    def train(
        self,
        request: ResearchModelTrainingRequest,
        *,
        trained_at: datetime,
    ) -> ResearchModelArtifact:
        self.publish_request(request)
        existing = self.find_artifact(request.request_id)
        if existing is not None:
            return existing
        artifact = train_research_model(request, trained_at=trained_at)
        return self.publish_artifact(artifact)

    def publish_artifact(self, artifact: ResearchModelArtifact) -> ResearchModelArtifact:
        request = self.get_request(artifact.request_reference.artifact_id)
        if artifact.request_reference != ValidationArtifactReference(
            "RESEARCH_MODEL_TRAINING_REQUEST", request.request_id, request.request_hash
        ):
            raise ValueError("Research Model artifact does not bind its Request owner")

        def operation(connection: Any) -> None:
            connection.execute(
                """
                INSERT INTO research_model_artifact(
                    artifact_id, artifact_hash, request_id, status,
                    selected_penalty, model_parameter_hash,
                    research_model_available, runtime_role,
                    formal_model_qualified, formal_oos, calibrated,
                    production_authorized, payload_json, trained_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s,
                    false, false, false, false, %s, %s
                ) ON CONFLICT (artifact_id) DO NOTHING
                """,
                (
                    str(artifact.artifact_id), artifact.artifact_hash,
                    str(request.request_id), artifact.status.value,
                    artifact.selected_penalty, artifact.model_parameter_hash,
                    artifact.research_model_available,
                    artifact.runtime_role,
                    Jsonb(artifact.to_canonical_dict()), artifact.trained_at,
                ),
            )
            stored = connection.execute(
                "SELECT artifact_hash, payload_json FROM research_model_artifact WHERE artifact_id = %s",
                (str(artifact.artifact_id),),
            ).fetchone()
            if stored is None or str(stored[0]) != artifact.artifact_hash or stored[1] != artifact.to_canonical_dict():
                raise ValueError("Research Model artifact identity conflict")
            for diagnostic in artifact.diagnostics:
                connection.execute(
                    """
                    INSERT INTO research_model_candidate_diagnostic(
                        artifact_id, penalty, status, aggregate_loss, payload_json
                    ) VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (artifact_id, penalty) DO NOTHING
                    """,
                    (
                        str(artifact.artifact_id), diagnostic.penalty,
                        diagnostic.status.value, diagnostic.aggregate_loss,
                        Jsonb(diagnostic.to_canonical_dict()),
                    ),
                )
            if artifact.model is not None:
                for head in (*artifact.model.continuous_heads, *artifact.model.barrier_heads):
                    connection.execute(
                        """
                        INSERT INTO research_model_coefficient_head(
                            artifact_id, target_name, head_kind, payload_json
                        ) VALUES (%s, %s, %s, %s)
                        ON CONFLICT (artifact_id, target_name) DO NOTHING
                        """,
                        (
                            str(artifact.artifact_id), head.target_name,
                            head.head_kind, Jsonb(head.to_canonical_dict()),
                        ),
                    )
            self._verify_artifact_projections(connection, artifact)

        try:
            self._factory.run_transaction(operation)
        except Exception:
            existing = self.find_artifact(request.request_id)
            if existing == artifact:
                return existing
            raise
        return self.get_artifact(artifact.artifact_id)

    def find_artifact(self, request_id: ArtifactId) -> ResearchModelArtifact | None:
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                "SELECT artifact_id FROM research_model_artifact WHERE request_id = %s",
                (str(request_id),),
            ).fetchone()
        return None if row is None else self.get_artifact(ArtifactId(str(row[0])))

    def get_artifact(self, artifact_id: ArtifactId) -> ResearchModelArtifact:
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                "SELECT artifact_hash, payload_json FROM research_model_artifact WHERE artifact_id = %s",
                (str(artifact_id),),
            ).fetchone()
            if row is None or not isinstance(row[1], dict):
                raise KeyError(str(artifact_id))
            artifact = ResearchModelArtifact.from_canonical_dict(row[1])
            if str(row[0]) != artifact.artifact_hash:
                raise ValueError("Research Model artifact owner hash diverged")
            self._verify_artifact_projections(connection, artifact)
        return artifact

    def replay(self, artifact_id: ArtifactId) -> ResearchModelArtifact:
        artifact = self.get_artifact(artifact_id)
        request = self.get_request(artifact.request_reference.artifact_id)
        reproduced = train_research_model(request, trained_at=artifact.trained_at)
        if reproduced != artifact:
            raise ValueError("Research Model deterministic replay diverged")
        return artifact

    def get_executable_by_parameter_hash(
        self, model_parameter_hash: str
    ) -> tuple[ResearchModelArtifact, ResearchModelTrainingRequest]:
        with self._factory.connection(read_only=True) as connection:
            return load_executable_research_model_owner(
                connection, model_parameter_hash=model_parameter_hash
            )

    def execute(
        self,
        *,
        artifact_id: ArtifactId,
        request: ResearchInferenceRequest,
        executed_at: datetime,
    ) -> ResearchModelInferenceReceipt:
        artifact = self.get_artifact(artifact_id)
        training = self.get_request(artifact.request_reference.artifact_id)
        result = RegularizedLinearForecastExecutor(
            artifact=artifact,
            request=training,
        ).execute(request)
        receipt = ResearchModelInferenceReceipt.create(
            model_reference=ValidationArtifactReference(
                "RESEARCH_MODEL_ARTIFACT", artifact.artifact_id, artifact.artifact_hash
            ),
            request=request,
            result=result,
            executed_at=executed_at,
        )
        return self.publish_inference(receipt)

    def publish_inference(
        self, receipt: ResearchModelInferenceReceipt
    ) -> ResearchModelInferenceReceipt:
        self.get_artifact(receipt.model_reference.artifact_id)

        def operation(connection: Any) -> None:
            connection.execute(
                """
                INSERT INTO research_model_inference_receipt(
                    receipt_id, receipt_hash, artifact_id, symbol,
                    decision_time, status, formal_model_qualified, formal_oos,
                    calibrated, production_authorized, payload_json, executed_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s,
                    false, false, false, false, %s, %s
                ) ON CONFLICT (receipt_id) DO NOTHING
                """,
                (
                    str(receipt.receipt_id), receipt.receipt_hash,
                    str(receipt.model_reference.artifact_id), receipt.request.symbol,
                    receipt.request.decision_time, receipt.result.status.value,
                    Jsonb(receipt.to_canonical_dict()), receipt.executed_at,
                ),
            )
            stored = connection.execute(
                "SELECT receipt_hash, payload_json FROM research_model_inference_receipt WHERE receipt_id = %s",
                (str(receipt.receipt_id),),
            ).fetchone()
            if stored is None or str(stored[0]) != receipt.receipt_hash or stored[1] != receipt.to_canonical_dict():
                raise ValueError("Research Model inference identity conflict")
            for ordinal, reference in enumerate(receipt.source_references, start=1):
                connection.execute(
                    """
                    INSERT INTO research_model_inference_source_binding(
                        receipt_id, ordinal, artifact_kind, artifact_id, content_hash
                    ) VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (receipt_id, ordinal) DO NOTHING
                    """,
                    (
                        str(receipt.receipt_id), ordinal, reference.artifact_kind,
                        str(reference.artifact_id), reference.content_hash,
                    ),
                )
            self._verify_inference_projection(connection, receipt)

        self._factory.run_transaction(operation)
        return self.get_inference(receipt.receipt_id)

    def get_inference(self, receipt_id: ArtifactId) -> ResearchModelInferenceReceipt:
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                "SELECT receipt_hash, payload_json FROM research_model_inference_receipt WHERE receipt_id = %s",
                (str(receipt_id),),
            ).fetchone()
            if row is None or not isinstance(row[1], dict):
                raise KeyError(str(receipt_id))
            receipt = ResearchModelInferenceReceipt.from_canonical_dict(row[1])
            if str(row[0]) != receipt.receipt_hash:
                raise ValueError("Research Model inference owner hash diverged")
            self._verify_inference_projection(connection, receipt)
        return receipt

    @staticmethod
    def _verify_request_projections(
        connection: Any, request: ResearchModelTrainingRequest
    ) -> None:
        sample_rows = connection.execute(
            "SELECT payload_json FROM research_model_training_sample WHERE request_id = %s ORDER BY ordinal",
            (str(request.request_id),),
        ).fetchall()
        feature_rows = connection.execute(
            """
            SELECT feature.payload_json
            FROM research_model_training_feature AS feature
            JOIN research_model_training_sample AS sample
              ON sample.request_id = feature.request_id AND sample.sample_id = feature.sample_id
            WHERE feature.request_id = %s
            ORDER BY sample.ordinal, feature.feature_name
            """,
            (str(request.request_id),),
        ).fetchall()
        target_rows = connection.execute(
            """
            SELECT target.payload_json
            FROM research_model_training_target AS target
            JOIN research_model_training_sample AS sample
              ON sample.request_id = target.request_id AND sample.sample_id = target.sample_id
            WHERE target.request_id = %s
            ORDER BY sample.ordinal, target.target_name
            """,
            (str(request.request_id),),
        ).fetchall()
        fold_rows = connection.execute(
            "SELECT payload_json FROM research_model_walk_forward_fold WHERE request_id = %s ORDER BY fold_name",
            (str(request.request_id),),
        ).fetchall()
        source_rows = connection.execute(
            "SELECT artifact_kind, artifact_id, content_hash FROM research_model_training_source_binding WHERE request_id = %s ORDER BY ordinal",
            (str(request.request_id),),
        ).fetchall()
        if [row[0] for row in sample_rows] != [item.to_canonical_dict() for item in request.samples]:
            raise ValueError("Research Model sample projection diverged")
        if [row[0] for row in feature_rows] != [item.to_canonical_dict() for sample in request.samples for item in sample.features]:
            raise ValueError("Research Model feature projection diverged")
        if [row[0] for row in target_rows] != [item.to_canonical_dict() for sample in request.samples for item in sample.targets]:
            raise ValueError("Research Model target projection diverged")
        if [row[0] for row in fold_rows] != [item.to_canonical_dict() for item in request.folds]:
            raise ValueError("Research Model fold projection diverged")
        if [tuple(str(value) for value in row) for row in source_rows] != [
            (item.artifact_kind, str(item.artifact_id), item.content_hash)
            for item in _request_sources(request)
        ]:
            raise ValueError("Research Model source projection diverged")

    @staticmethod
    def _verify_artifact_projections(connection: Any, artifact: ResearchModelArtifact) -> None:
        diagnostics = connection.execute(
            "SELECT payload_json FROM research_model_candidate_diagnostic WHERE artifact_id = %s ORDER BY penalty",
            (str(artifact.artifact_id),),
        ).fetchall()
        heads = connection.execute(
            "SELECT payload_json FROM research_model_coefficient_head WHERE artifact_id = %s ORDER BY target_name",
            (str(artifact.artifact_id),),
        ).fetchall()
        expected_heads = [] if artifact.model is None else sorted(
            (item.to_canonical_dict() for item in (*artifact.model.continuous_heads, *artifact.model.barrier_heads)),
            key=lambda item: str(item["target_name"]),
        )
        if [row[0] for row in diagnostics] != [item.to_canonical_dict() for item in artifact.diagnostics]:
            raise ValueError("Research Model diagnostic projection diverged")
        if [row[0] for row in heads] != expected_heads:
            raise ValueError("Research Model head projection diverged")

    @staticmethod
    def _verify_inference_projection(
        connection: Any, receipt: ResearchModelInferenceReceipt
    ) -> None:
        rows = connection.execute(
            "SELECT artifact_kind, artifact_id, content_hash FROM research_model_inference_source_binding WHERE receipt_id = %s ORDER BY ordinal",
            (str(receipt.receipt_id),),
        ).fetchall()
        if [tuple(str(value) for value in row) for row in rows] != [
            (item.artifact_kind, str(item.artifact_id), item.content_hash)
            for item in receipt.source_references
        ]:
            raise ValueError("Research Model inference source projection diverged")


def _request_sources(
    request: ResearchModelTrainingRequest,
) -> tuple[ValidationArtifactReference, ...]:
    return tuple(
        sorted(
            {
                request.model_definition_reference,
                request.configuration_reference,
                request.feature_catalog_reference,
                request.target_protocol_reference,
                request.locked_oos_reference,
                *request.dataset_references,
                *(reference for sample in request.samples for reference in sample.source_references),
            },
            key=lambda item: (item.artifact_kind, str(item.artifact_id), item.content_hash),
        )
    )


def load_executable_research_model_owner(
    connection: Any,
    *,
    model_parameter_hash: str,
) -> tuple[ResearchModelArtifact, ResearchModelTrainingRequest]:
    """Resolve one immutable executable parameter owner or fail closed."""

    rows = connection.execute(
        """
        SELECT artifact.artifact_hash, artifact.payload_json,
               request.request_hash, request.payload_json,
               artifact.status, artifact.research_model_available,
               artifact.formal_model_qualified, artifact.formal_oos,
               artifact.calibrated, artifact.production_authorized
        FROM research_model_artifact AS artifact
        JOIN research_model_training_request AS request
          ON request.request_id = artifact.request_id
        WHERE artifact.model_parameter_hash = %s
        ORDER BY artifact.artifact_id
        """,
        (model_parameter_hash,),
    ).fetchall()
    if not rows:
        raise KeyError(model_parameter_hash)
    if len(rows) != 1:
        raise ValueError("Research Model parameter owner is ambiguous")
    row = rows[0]
    if not isinstance(row[1], dict) or not isinstance(row[3], dict):
        raise ValueError("Research Model owner payload is malformed")
    artifact = ResearchModelArtifact.from_canonical_dict(row[1])
    request = ResearchModelTrainingRequest.from_canonical_dict(row[3])
    if (
        str(row[0]) != artifact.artifact_hash
        or str(row[2]) != request.request_hash
        or artifact.request_reference
        != ValidationArtifactReference(
            "RESEARCH_MODEL_TRAINING_REQUEST", request.request_id, request.request_hash
        )
        or artifact.status.value != str(row[4])
        or bool(row[5]) is not True
        or any(bool(item) for item in row[6:10])
        or artifact.model is None
        or artifact.model_parameter_hash != model_parameter_hash
        or request.experiment_definition is None
        or not request.measure_bindings
        or research_model_parameter_hash(request, artifact.model)
        != model_parameter_hash
    ):
        raise ValueError("Research Model executable owner verification failed")
    return artifact, request


__all__ = [
    "PostgresResearchModelRepository",
    "load_executable_research_model_owner",
]
