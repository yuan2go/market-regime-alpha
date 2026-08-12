"""PostgreSQL journal for exploratory model selection, artifacts and inference."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import json
from typing import Any, Mapping

from psycopg.types.json import Jsonb

from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.application.controlled_operation.prospective_outcome import (
    OutcomeAvailabilityStatus,
)
from market_regime_alpha.application.research_evaluation.targeted_outcome import (
    BarrierOrderingOutcome,
    TargetOutcomeLabel,
    TargetedShadowOutcome,
)
from market_regime_alpha.application.research_validation.formal_evaluation import (
    EvaluationPartition,
    FormalEvaluationProtocol,
)
from market_regime_alpha.application.research_validation.formal_protocol import (
    ForecastMeasureKind,
)
from market_regime_alpha.application.research_validation.formal_protocol_components import (
    FeatureDefinitionSet,
)
from market_regime_alpha.application.research_validation.research_model import (
    RegularizedLinearForecastExecutor,
    ResearchInferenceRequest,
    ResearchModelArtifact,
    ResearchModelInferenceReceipt,
    ResearchModelTrainingRequest,
    ResearchTrainingSample,
    TimedResearchFeature,
    TimedResearchTarget,
    WalkForwardFold,
    research_model_parameter_hash,
    train_research_model,
)
from market_regime_alpha.application.research_validation.samples import (
    HistoricalPathSampleRecord,
    HistoricalSampleDataset,
)
from market_regime_alpha.application.research_validation.qualification import (
    HistoricalSampleQualificationDecision,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.data.pit_authority import (
    FormalPITEvidenceArtifact,
    FormalPITValidationRequest,
    PITAsOfSnapshot,
    PITFactKind,
    PITFactRevision,
    PITValidationOutcome,
)
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from market_regime_alpha.persistence.postgres.migrator import PostgresMigrator
from market_regime_alpha.platform.postgres_runtime_governance import (
    resolve_formal_research_model_lineage,
)


_CALLER_PAYLOAD_PROVENANCE = "EXPLORATORY_CALLER_PAYLOAD"


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
        with self._factory.connection(read_only=True) as connection:
            resolved = _resolve_owner_training_request(connection, request)
        return self._publish_request(resolved)

    def publish_exploratory_request(
        self, request: ResearchModelTrainingRequest
    ) -> ResearchModelTrainingRequest:
        """Persist caller payload only with an explicit non-owner provenance ceiling."""

        return self._publish_request(
            _rebuild_request(
                request,
                limitations=(*request.limitations, _CALLER_PAYLOAD_PROVENANCE),
            )
        )

    def _publish_request(
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
        resolved = self.publish_request(request)
        existing = self.find_artifact(resolved.request_id)
        if existing is not None:
            return existing
        artifact = train_research_model(resolved, trained_at=trained_at)
        return self.publish_artifact(artifact)

    def train_exploratory(
        self,
        request: ResearchModelTrainingRequest,
        *,
        trained_at: datetime,
    ) -> ResearchModelArtifact:
        """Train caller payload without representing it as owner-derived evidence."""

        exploratory = self.publish_exploratory_request(request)
        existing = self.find_artifact(exploratory.request_id)
        if existing is not None:
            return existing
        artifact = train_research_model(exploratory, trained_at=trained_at)
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
                "SELECT artifact_hash, request_id, payload_json "
                "FROM research_model_artifact WHERE artifact_id = %s",
                (str(artifact_id),),
            ).fetchone()
            if row is None or not isinstance(row[2], dict):
                raise KeyError(str(artifact_id))
            artifact = ResearchModelArtifact.from_canonical_dict(row[2])
            if (
                str(row[0]) != artifact.artifact_hash
                or str(row[1]) != str(artifact.request_reference.artifact_id)
            ):
                raise ValueError("Research Model artifact owner hash diverged")
            self._verify_artifact_projections(connection, artifact)
        request = self.get_request(artifact.request_reference.artifact_id)
        if artifact.request_reference != ValidationArtifactReference(
            "RESEARCH_MODEL_TRAINING_REQUEST",
            request.request_id,
            request.request_hash,
        ):
            raise ValueError("Research Model artifact Request owner mismatch")
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
        required_at = max(
            artifact.trained_at,
            request.decision_time,
            *(item.available_at for item in request.features),
        )
        if executed_at < required_at:
            raise ValueError(
                "Research Model inference executed_at predates required input availability"
            )
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
        artifact = self.get_artifact(receipt.model_reference.artifact_id)
        if receipt.model_reference != ValidationArtifactReference(
            "RESEARCH_MODEL_ARTIFACT",
            artifact.artifact_id,
            artifact.artifact_hash,
        ):
            raise ValueError("Research Model owner identity mismatch")
        required_at = max(
            artifact.trained_at,
            receipt.request.decision_time,
            *(item.available_at for item in receipt.request.features),
        )
        if receipt.executed_at < required_at:
            raise ValueError(
                "Research Model inference executed_at predates required input availability"
            )

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
                "SELECT receipt_hash, artifact_id, payload_json "
                "FROM research_model_inference_receipt WHERE receipt_id = %s",
                (str(receipt_id),),
            ).fetchone()
            if row is None or not isinstance(row[2], dict):
                raise KeyError(str(receipt_id))
            receipt = ResearchModelInferenceReceipt.from_canonical_dict(row[2])
            if (
                str(row[0]) != receipt.receipt_hash
                or str(row[1]) != str(receipt.model_reference.artifact_id)
            ):
                raise ValueError("Research Model inference owner hash diverged")
            self._verify_inference_projection(connection, receipt)
        artifact = self.get_artifact(receipt.model_reference.artifact_id)
        if receipt.model_reference != ValidationArtifactReference(
            "RESEARCH_MODEL_ARTIFACT",
            artifact.artifact_id,
            artifact.artifact_hash,
        ):
            raise ValueError("Research Model inference Artifact owner mismatch")
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


def _resolve_owner_training_request(
    connection: Any,
    request: ResearchModelTrainingRequest,
) -> ResearchModelTrainingRequest:
    """Rebuild the training matrix from bounded PostgreSQL owners."""

    # Keep the owner loaders acyclic: Formal Protocol resolves executable Research
    # Models, while formal Model training resolves the frozen protocol owner here.
    from market_regime_alpha.application.research_validation.postgres_formal_protocol import (
        load_formal_protocol_pre_oos_owner,
    )

    if request.schema_version != "research-model-training-request/v2":
        raise ValueError("Owner-resolved Research Model training requires V2 Experiment bindings")
    if request.model_definition_reference.artifact_kind != "MODEL_VERSION_LINEAGE":
        raise ValueError("Research Model Definition must resolve through Model Governance")
    if request.locked_oos_reference.artifact_kind != "FORMAL_LOCKED_OOS_ROSTER":
        raise ValueError("Research Model Locked OOS scope must use the formal roster owner")

    model = resolve_formal_research_model_lineage(
        connection,
        lineage_id=request.model_definition_reference.artifact_id,
        lineage_hash=request.model_definition_reference.content_hash,
    )
    model_configuration = ValidationArtifactReference(
        model.lineage.configuration.reference_kind,
        model.lineage.configuration.artifact_id,
        model.lineage.configuration.content_hash,
    )
    if request.configuration_reference != model_configuration:
        raise ValueError("Research Model Configuration owner mismatch")
    if (
        request.code_revision != model.lineage.code_revision
        or request.code_hash != model.lineage.code_hash
    ):
        raise ValueError("Research Model code identity diverged from Model Governance")

    feature_set, feature_recorded_at = _load_feature_definition_owner(
        connection, request.feature_catalog_reference
    )
    target_recorded_at = _verify_target_protocol_owner(
        connection, request.target_protocol_reference
    )
    roster = _load_locked_oos_roster(connection, request.locked_oos_reference)
    protocol_reference = ValidationArtifactReference.from_canonical_dict(
        _mapping(roster.payload["formal_protocol_reference"])
    )
    protocol = load_formal_protocol_pre_oos_owner(
        connection, protocol_reference.artifact_id
    )
    if (
        protocol_reference.content_hash != protocol.protocol_hash
        or request.model_definition_reference != protocol.model_reference
        or request.feature_catalog_reference != protocol.feature_reference
        or request.target_protocol_reference
        != protocol.outcome_target_protocol_reference
        or request.experiment_definition != protocol.experiment_definition
    ):
        raise ValueError("Research Model request diverged from frozen Formal Protocol owners")
    experiment = protocol.experiment_definition
    assert experiment is not None
    penalty_domain = next(
        (
            item
            for item in experiment.hyperparameter_space
            if item.parameter_name == "ridge_penalty"
        ),
        None,
    )
    if penalty_domain is None:
        raise ValueError("Research Model frozen ridge penalty domain is missing")
    try:
        frozen_penalties = tuple(
            sorted(Decimal(item) for item in penalty_domain.allowed_values)
        )
    except InvalidOperation as error:
        raise ValueError("Research Model frozen ridge penalty domain is invalid") from error
    if request.penalty_candidates != frozen_penalties:
        raise ValueError("Research Model penalty grid must equal the frozen owner")
    if experiment.random_seeds != (request.fold_seed,):
        raise ValueError("Research Model fold seed must equal the sole frozen owner seed")

    if request.dataset_references != protocol.historical_sample_dataset_references:
        raise ValueError(
            "Research Model datasets must equal the frozen Historical Dataset owners"
        )
    dataset_owners = tuple(
        _load_historical_dataset_owner(connection, reference)
        for reference in protocol.historical_sample_dataset_references
    )
    evaluation, evaluation_recorded_at = _load_evaluation_protocol_owner(
        connection, protocol.evaluation_protocol_reference
    )

    expected_locked_ids = tuple(
        sorted((ArtifactId(item) for item in roster.label_ids), key=str)
    )
    if request.locked_oos_sample_ids != expected_locked_ids:
        raise ValueError("Research Model Locked OOS member identities diverged")
    if request.oos_start_date != roster.oos_start_date:
        raise ValueError("Research Model Locked OOS start date diverged")
    if request.session_sequence != protocol.frozen_trading_dates:
        raise ValueError("Research Model session sequence is not the frozen Calendar owner")

    latest_input_at = max(
        model.owner_recorded_at,
        feature_recorded_at,
        target_recorded_at,
        roster.frozen_at,
        evaluation_recorded_at,
        *(item[1] for item in dataset_owners),
    )
    if request.requested_at < latest_input_at:
        raise ValueError("Research Model request predates required owner availability")
    samples = _build_owner_training_samples(
        connection,
        request=request,
        feature_set=feature_set,
        datasets=tuple(item[0] for item in dataset_owners),
        formal_protocol_reference=protocol_reference,
    )
    folds = _build_owner_walk_forward_folds(
        samples=samples,
        evaluation=evaluation,
        oos_start_date=roster.oos_start_date,
        session_sequence=request.session_sequence,
    )
    selected_ids = {
        sample_id
        for fold in folds
        for sample_id in (*fold.train_sample_ids, *fold.validation_sample_ids)
    }
    samples = tuple(item for item in samples if item.sample_id in selected_ids)
    return _rebuild_request(
        request,
        samples=samples,
        folds=folds,
        feature_names=tuple(
            sorted(item.feature_id for item in feature_set.definitions)
        ),
        limitations=(*request.limitations, "OWNER_RESOLVED_POSTGRES_INPUTS"),
    )


def _build_owner_training_samples(
    connection: Any,
    *,
    request: ResearchModelTrainingRequest,
    feature_set: FeatureDefinitionSet,
    datasets: tuple[HistoricalSampleDataset, ...],
    formal_protocol_reference: ValidationArtifactReference,
) -> tuple[ResearchTrainingSample, ...]:
    feature_names = tuple(sorted(item.feature_id for item in feature_set.definitions))
    if request.feature_names != feature_names:
        raise ValueError("Research Model feature names diverge from frozen owner")
    datasets_by_target = {item.target_reference: item for item in datasets}
    if len(datasets_by_target) != len(datasets):
        raise ValueError("Research Model Historical Dataset target owner is ambiguous")
    binding_targets = {item.target_reference for item in request.measure_bindings}
    if binding_targets != set(datasets_by_target):
        raise ValueError("Research Model target bindings diverge from frozen Datasets")

    records_by_target: dict[
        ValidationArtifactReference,
        dict[tuple[datetime, str], HistoricalPathSampleRecord],
    ] = {}
    qualifications: dict[
        ValidationArtifactReference,
        tuple[HistoricalSampleQualificationDecision, dict[datetime, FormalPITEvidenceArtifact]],
    ] = {}
    for target, dataset in datasets_by_target.items():
        decision = _load_qualified_historical_dataset_owner(
            connection,
            dataset=dataset,
            formal_protocol_reference=formal_protocol_reference,
        )
        evidence_by_time = _load_qualified_pit_evidence_set(
            connection, decision
        )
        if request.requested_at < max(
            decision.evaluated_at,
            *(item.recorded_at for item in evidence_by_time.values()),
        ):
            raise ValueError(
                "Research Model request predates qualification/PIT owner recording"
            )
        qualifications[target] = decision, evidence_by_time
        by_key = {
            (item.sample.sample_decision_time.value, item.sample.symbol): item
            for item in dataset.records
        }
        if len(by_key) != len(dataset.records):
            raise ValueError("Research Model Historical sample owner key is ambiguous")
        records_by_target[target] = by_key

    owner_keys = {frozenset(items) for items in records_by_target.values()}
    if len(owner_keys) != 1:
        raise ValueError("Research Model Target datasets do not align by session/symbol")
    keys = sorted(next(iter(owner_keys)), key=lambda item: (item[0], item[1]))
    samples: list[ResearchTrainingSample] = []
    for decision_time, symbol in keys:
        target_records = {
            target: records_by_target[target][(decision_time, symbol)]
            for target in records_by_target
        }
        feature_sets = {
            frozenset(
                item
                for item in record.pit_lineage
                if item.artifact_kind == "PIT_FACT_REVISION"
            )
            for record in target_records.values()
        }
        if len(feature_sets) != 1:
            raise ValueError("Research Model Target records diverge on PIT lineage")
        pit_references = tuple(
            sorted(
                next(iter(feature_sets)),
                key=lambda item: (str(item.artifact_id), item.content_hash),
            )
        )
        for target, record in target_records.items():
            _decision, evidence_by_time = qualifications[target]
            evidence = evidence_by_time.get(decision_time)
            if evidence is None or symbol not in _formal_pit_symbols(
                connection, evidence.evidence_id
            ):
                raise ValueError("Research Model Historical sample PIT owner is missing")
            selected = {
                (str(item.fact_id), item.fact_hash)
                for item in evidence.selected_fact_authorities
            }
            if {
                (str(item.artifact_id), item.content_hash)
                for item in pit_references
            } != selected:
                raise ValueError("Research Model Historical sample PIT owner set diverged")
        features = _load_feature_vector(
            connection,
            references=pit_references,
            symbol=symbol,
            decision_time=decision_time,
            feature_names=feature_names,
        )
        targets = tuple(
            _load_training_target(
                connection,
                binding=binding,
                record=target_records[binding.target_reference],
            )
            for binding in request.measure_bindings
        )
        samples.append(
            ResearchTrainingSample.create(
                symbol=symbol,
                trading_date=decision_time.date(),
                decision_time=decision_time,
                features=features,
                targets=targets,
            )
        )
    if not samples:
        raise ValueError("Research Model owner-derived training matrix is empty")
    return tuple(samples)


def _load_feature_vector(
    connection: Any,
    *,
    references: tuple[ValidationArtifactReference, ...],
    symbol: str,
    decision_time: datetime,
    feature_names: tuple[str, ...],
) -> tuple[TimedResearchFeature, ...]:
    facts = tuple(_load_pit_fact_owner(connection, item) for item in references)
    feature_facts = tuple(
        (reference, fact)
        for reference, fact in zip(references, facts, strict=True)
        if fact.fact_kind is PITFactKind.FEATURE_MATERIALIZATION
    )
    if len(feature_facts) != 1:
        raise ValueError("Research Model requires exactly one PIT Feature vector")
    reference, fact = feature_facts[0]
    if (
        fact.data_eligibility is not DataEligibility.FORMAL_RESEARCH
        or fact.effective_from > decision_time
        or fact.available_at > decision_time
        or fact.recorded_at > decision_time
    ):
        raise ValueError("Research Model Feature Fact is not valid at DecisionTime")
    try:
        value = json.loads(fact.value_json)
    except json.JSONDecodeError as error:
        raise ValueError("Research Model Feature vector JSON is invalid") from error
    if (
        not isinstance(value, dict)
        or set(value) != {"schema_version", "symbol", "decision_time", "features"}
        or value["schema_version"] != "forecast-feature-vector/v1"
        or value["symbol"] != symbol
        or value["decision_time"] != decision_time.isoformat()
        or not isinstance(value["features"], dict)
        or tuple(sorted(str(item) for item in value["features"])) != feature_names
    ):
        raise ValueError("Research Model Feature vector owner identity mismatch")
    output = []
    for name in feature_names:
        raw = value["features"][name]
        try:
            parsed = None if raw is None else Decimal(str(raw))
        except InvalidOperation as error:
            raise ValueError("Research Model Feature value is not decimal") from error
        if parsed is not None and not parsed.is_finite():
            raise ValueError("Research Model Feature value is not finite")
        output.append(
            TimedResearchFeature(
                name=name,
                value=parsed,
                effective_at=fact.effective_from,
                available_at=max(fact.available_at, fact.recorded_at),
                source_reference=reference,
                source_value_path=f"value_json.features.{name}",
            )
        )
    return tuple(output)


def _load_training_target(
    connection: Any,
    *,
    binding: Any,
    record: HistoricalPathSampleRecord,
) -> TimedResearchTarget:
    label = _load_target_label_owner(connection, record)
    measure = binding.measure_kind
    value: Decimal | bool | None
    path: str
    if measure in {ForecastMeasureKind.RANKING_SCORE, ForecastMeasureKind.EXPECTED_RETURN}:
        value, path = label.checkpoint_return, "checkpoint_return"
    elif measure is ForecastMeasureKind.EXPECTED_DOWNSIDE:
        value = (
            None
            if label.checkpoint_return is None
            else min(label.checkpoint_return, Decimal("0"))
        )
        path = "checkpoint_return.downside"
    elif measure is ForecastMeasureKind.EXPECTED_MFE:
        value, path = label.mfe, "mfe"
    elif measure is ForecastMeasureKind.EXPECTED_MAE:
        value, path = label.mae, "mae"
    elif measure is ForecastMeasureKind.RETURN_POSITIVE_RAW_LOGIT:
        value = (
            None
            if label.checkpoint_return is None
            else label.checkpoint_return > 0
        )
        path = "checkpoint_return.positive"
    elif measure is ForecastMeasureKind.UPPER_BEFORE_LOWER_RAW_LOGIT:
        if label.barrier_ordering not in {
            BarrierOrderingOutcome.UP_FIRST,
            BarrierOrderingOutcome.DOWN_FIRST,
        }:
            value = None
        else:
            value = label.barrier_ordering is BarrierOrderingOutcome.UP_FIRST
        path = "barrier_ordering.upper_before_lower"
    elif measure is ForecastMeasureKind.BARRIER_RAW_LOGIT:
        passages = dict(label.barrier_passages)
        value = None if binding.barrier_id not in passages else passages[binding.barrier_id] is not None
        path = f"barrier_passages.{binding.barrier_id}"
    else:
        raise ValueError("Research Model measure cannot be owner-derived for training")
    if value is None:
        raise ValueError("Research Model Target owner value is not estimable")
    return TimedResearchTarget(
        name=binding.training_target_name,
        value=value,
        available_at=max(label.outcome_available_at, record.registered_at),
        source_reference=record.outcome_reference,
        source_value_path=path,
    )


def _build_owner_walk_forward_folds(
    *,
    samples: tuple[ResearchTrainingSample, ...],
    evaluation: FormalEvaluationProtocol,
    oos_start_date: date,
    session_sequence: tuple[date, ...],
) -> tuple[WalkForwardFold, ...]:
    session_index = {item: index for index, item in enumerate(session_sequence)}
    if any(item.trading_date not in session_index for item in samples):
        raise ValueError("Research Model owner sample is outside frozen Calendar")
    folds = []
    for fold_number in sorted({item.fold for item in evaluation.windows}):
        scoped = tuple(item for item in evaluation.windows if item.fold == fold_number)
        train = next(item for item in scoped if item.partition is EvaluationPartition.TRAIN)
        validation = next(
            item for item in scoped if item.partition is EvaluationPartition.VALIDATION
        )
        locked = next(
            item for item in scoped if item.partition is EvaluationPartition.LOCKED_OOS
        )
        if locked.start_date != oos_start_date:
            raise ValueError("Research Model Locked OOS start diverges from Evaluation owner")
        try:
            validation_start_index = session_index[validation.start_date]
            locked_start_index = session_index[locked.start_date]
        except KeyError as error:
            raise ValueError(
                "Research Model Evaluation boundary is outside frozen Calendar"
            ) from error
        purge = evaluation.embargo_sessions
        train_latest_index = validation_start_index - purge - 1
        validation_latest_index = locked_start_index - purge - 1
        train_ids = tuple(
            sorted(
                (
                    item.sample_id
                    for item in samples
                    if train.start_date <= item.trading_date <= train.end_date
                    and session_index[item.trading_date] <= train_latest_index
                ),
                key=str,
            )
        )
        validation_ids = tuple(
            sorted(
                (
                    item.sample_id
                    for item in samples
                    if validation.start_date <= item.trading_date <= validation.end_date
                    and session_index[item.trading_date] <= validation_latest_index
                ),
                key=str,
            )
        )
        folds.append(
            WalkForwardFold(
                fold_name=f"fold-{fold_number:02d}",
                train_sample_ids=train_ids,
                validation_sample_ids=validation_ids,
                purge_sessions=purge,
                embargo_sessions=purge,
            )
        )
    return tuple(folds)


class _LockedOOSOwner:
    def __init__(
        self,
        *,
        payload: Mapping[str, Any],
        frozen_at: datetime,
        label_ids: tuple[str, ...],
        oos_start_date: date,
    ) -> None:
        self.payload = payload
        self.frozen_at = frozen_at
        self.label_ids = label_ids
        self.oos_start_date = oos_start_date


def _load_locked_oos_roster(
    connection: Any,
    reference: ValidationArtifactReference,
) -> _LockedOOSOwner:
    row = connection.execute(
        """
        SELECT roster_hash, payload_json, frozen_at
        FROM formal_locked_oos_roster WHERE roster_id = %s
        """,
        (str(reference.artifact_id),),
    ).fetchone()
    if row is None or not isinstance(row[1], Mapping):
        raise ValueError("Research Model Locked OOS owner is missing")
    payload = dict(row[1])
    if (
        str(row[0]) != reference.content_hash
        or canonical_hash(payload) != reference.content_hash
        or payload.get("schema_version") != "formal-locked-oos-roster/v1"
        or payload.get("outcome_values_read") is not False
        or not isinstance(row[2], datetime)
    ):
        raise ValueError("Research Model Locked OOS owner identity mismatch")
    members = connection.execute(
        """
        SELECT label_id, decision_time, member_hash, payload_json
        FROM formal_locked_oos_roster_member
        WHERE roster_id = %s ORDER BY decision_time, label_id
        """,
        (str(reference.artifact_id),),
    ).fetchall()
    if not members or any(
        not isinstance(item[1], datetime)
        or not isinstance(item[3], Mapping)
        or canonical_hash(dict(item[3])) != str(item[2])
        for item in members
    ):
        raise ValueError("Research Model Locked OOS member owner mismatch")
    return _LockedOOSOwner(
        payload=payload,
        frozen_at=row[2],
        label_ids=tuple(str(item[0]) for item in members),
        oos_start_date=min(item[1].date() for item in members),
    )


def _verify_research_artifact_owner(
    connection: Any,
    reference: ValidationArtifactReference,
    *,
    expected_kind: str,
) -> datetime:
    row = connection.execute(
        """
        SELECT artifact_hash, artifact_kind, payload_json, created_at
        FROM research_validation_artifact WHERE artifact_id = %s
        """,
        (str(reference.artifact_id),),
    ).fetchone()
    if (
        row is None
        or str(row[0]) != reference.content_hash
        or str(row[1]) != expected_kind
        or not isinstance(row[2], Mapping)
        or canonical_hash(dict(row[2])) != reference.content_hash
        or not isinstance(row[3], datetime)
    ):
        raise ValueError(f"Research Model {expected_kind} owner identity mismatch")
    return row[3]


def _verify_target_protocol_owner(
    connection: Any, reference: ValidationArtifactReference
) -> datetime:
    row = connection.execute(
        """
        SELECT protocol_hash, protocol_json, created_at
        FROM outcome_target_protocol WHERE protocol_id = %s
        """,
        (str(reference.artifact_id),),
    ).fetchone()
    if (
        reference.artifact_kind != "OUTCOME_TARGET_PROTOCOL"
        or row is None
        or str(row[0]) != reference.content_hash
        or not isinstance(row[1], Mapping)
        or str(row[1].get("protocol_hash")) != reference.content_hash
        or not isinstance(row[2], datetime)
    ):
        raise ValueError("Research Model Target Protocol owner identity mismatch")
    return row[2]


def _load_feature_definition_owner(
    connection: Any,
    reference: ValidationArtifactReference,
) -> tuple[FeatureDefinitionSet, datetime]:
    recorded_at = _verify_research_artifact_owner(
        connection, reference, expected_kind="FEATURE_DEFINITION_SET"
    )
    row = connection.execute(
        "SELECT payload_json FROM research_validation_artifact WHERE artifact_id = %s",
        (str(reference.artifact_id),),
    ).fetchone()
    assert row is not None and isinstance(row[0], Mapping)
    feature_set = FeatureDefinitionSet.from_canonical_dict(
        {
            "definition_set_id": str(reference.artifact_id),
            "definition_set_hash": reference.content_hash,
            **dict(row[0]),
        }
    )
    return feature_set, recorded_at


def _load_evaluation_protocol_owner(
    connection: Any,
    reference: ValidationArtifactReference,
) -> tuple[FormalEvaluationProtocol, datetime]:
    recorded_at = _verify_research_artifact_owner(
        connection, reference, expected_kind="FORMAL_EVALUATION_PROTOCOL"
    )
    row = connection.execute(
        "SELECT payload_json FROM research_validation_artifact WHERE artifact_id = %s",
        (str(reference.artifact_id),),
    ).fetchone()
    assert row is not None and isinstance(row[0], Mapping)
    evaluation = FormalEvaluationProtocol.from_canonical_dict(
        {
            "protocol_id": str(reference.artifact_id),
            "protocol_hash": reference.content_hash,
            **dict(row[0]),
        }
    )
    return evaluation, recorded_at


def _load_historical_dataset_owner(
    connection: Any, reference: ValidationArtifactReference
) -> tuple[HistoricalSampleDataset, datetime]:
    recorded_at = _verify_research_artifact_owner(
        connection, reference, expected_kind="HISTORICAL_SAMPLE_DATASET"
    )
    row = connection.execute(
        "SELECT payload_json FROM research_validation_artifact WHERE artifact_id = %s",
        (str(reference.artifact_id),),
    ).fetchone()
    assert row is not None and isinstance(row[0], Mapping)
    dataset = HistoricalSampleDataset.from_canonical_dict(
        {
            "dataset_id": str(reference.artifact_id),
            "dataset_hash": reference.content_hash,
            **dict(row[0]),
        }
    )
    return dataset, recorded_at


def _load_qualified_historical_dataset_owner(
    connection: Any,
    *,
    dataset: HistoricalSampleDataset,
    formal_protocol_reference: ValidationArtifactReference,
) -> HistoricalSampleQualificationDecision:
    row = connection.execute(
        """
        SELECT decision_hash, payload_json, evaluated_at
        FROM historical_sample_qualification_decision
        WHERE dataset_id = %s AND formal_protocol_id = %s
        ORDER BY revision DESC LIMIT 1
        """,
        (
            str(dataset.dataset_id),
            str(formal_protocol_reference.artifact_id),
        ),
    ).fetchone()
    if row is None or not isinstance(row[1], Mapping):
        raise ValueError("Research Model qualified Historical Dataset owner is missing")
    decision = HistoricalSampleQualificationDecision.from_canonical_dict(row[1])
    if (
        decision.decision_hash != str(row[0])
        or not decision.qualified
        or decision.dataset_reference
        != ValidationArtifactReference(
            "HISTORICAL_SAMPLE_DATASET", dataset.dataset_id, dataset.dataset_hash
        )
        or decision.formal_protocol_reference != formal_protocol_reference
        or decision.evaluated_at != row[2]
    ):
        raise ValueError("Research Model Historical Dataset qualification mismatch")
    pit_rows = connection.execute(
        """
        SELECT formal_pit_evidence_id, formal_pit_evidence_hash
        FROM historical_sample_qualification_pit_evidence
        WHERE decision_id = %s ORDER BY ordinal
        """,
        (str(decision.decision_id),),
    ).fetchall()
    if [tuple(str(item) for item in row) for row in pit_rows] != [
        (str(item.artifact_id), item.content_hash)
        for item in decision.formal_pit_references
    ]:
        raise ValueError("Research Model Historical qualification PIT projection mismatch")
    return decision


def _load_qualified_pit_evidence_set(
    connection: Any,
    decision: HistoricalSampleQualificationDecision,
) -> dict[datetime, FormalPITEvidenceArtifact]:
    output: dict[datetime, FormalPITEvidenceArtifact] = {}
    for reference in decision.formal_pit_references:
        row = connection.execute(
            """
            SELECT evidence_hash, payload_json, request_json
            FROM formal_pit_validation_evidence WHERE evidence_id = %s
            """,
            (str(reference.artifact_id),),
        ).fetchone()
        if (
            row is None
            or not isinstance(row[1], Mapping)
            or not isinstance(row[2], Mapping)
        ):
            raise ValueError("Research Model Formal PIT owner is missing")
        evidence = FormalPITEvidenceArtifact.from_canonical_dict(row[1])
        pit_request = FormalPITValidationRequest.from_canonical_dict(row[2])
        if (
            evidence.evidence_hash != str(row[0])
            or reference.artifact_id != evidence.evidence_id
            or reference.content_hash != evidence.evidence_hash
            or evidence.request_hash != pit_request.request_hash
            or evidence.outcome is not PITValidationOutcome.SATISFIED
            or pit_request.decision_time in output
        ):
            raise ValueError("Research Model Formal PIT owner identity mismatch")
        snapshot_row = connection.execute(
            "SELECT snapshot_hash, payload_json FROM pit_as_of_snapshot "
            "WHERE snapshot_id = %s",
            (str(evidence.snapshot_id),),
        ).fetchone()
        if snapshot_row is None or not isinstance(snapshot_row[1], Mapping):
            raise ValueError("Research Model Formal PIT Snapshot owner is missing")
        snapshot = PITAsOfSnapshot.from_canonical_dict(snapshot_row[1])
        if (
            snapshot.snapshot_hash != str(snapshot_row[0])
            or snapshot.snapshot_hash != evidence.snapshot_hash
            or snapshot.selected_fact_authorities
            != evidence.selected_fact_authorities
        ):
            raise ValueError("Research Model Formal PIT Snapshot identity mismatch")
        output[pit_request.decision_time] = evidence
    if not output:
        raise ValueError("Research Model requires qualified Formal PIT evidence")
    return output


def _formal_pit_symbols(
    connection: Any,
    evidence_id: ArtifactId,
) -> tuple[str, ...]:
    row = connection.execute(
        "SELECT request_json FROM formal_pit_validation_evidence WHERE evidence_id = %s",
        (str(evidence_id),),
    ).fetchone()
    if row is None or not isinstance(row[0], Mapping):
        raise ValueError("Research Model Formal PIT request owner is missing")
    return FormalPITValidationRequest.from_canonical_dict(row[0]).symbols


def _load_pit_fact_owner(
    connection: Any,
    reference: ValidationArtifactReference,
) -> PITFactRevision:
    row = connection.execute(
        "SELECT content_hash, payload_json FROM pit_fact_revision WHERE fact_id = %s",
        (str(reference.artifact_id),),
    ).fetchone()
    if row is None or not isinstance(row[1], Mapping):
        raise ValueError("Research Model PIT Fact owner is missing")
    fact = PITFactRevision.from_canonical_dict(row[1])
    if (
        reference.artifact_kind != "PIT_FACT_REVISION"
        or fact.fact_id != reference.artifact_id
        or fact.content_hash != reference.content_hash
        or str(row[0]) != reference.content_hash
    ):
        raise ValueError("Research Model PIT Fact owner identity mismatch")
    return fact


def _load_target_label_owner(
    connection: Any,
    record: HistoricalPathSampleRecord,
) -> TargetOutcomeLabel:
    rows = connection.execute(
        """
        SELECT outcome.settlement_hash, outcome.payload_json,
               label.label_hash, label.label_json, label.availability_status
        FROM targeted_shadow_outcome_label AS label
        JOIN targeted_shadow_outcome AS outcome
          ON outcome.settlement_id = label.settlement_id
        WHERE label.label_id = %s
        """,
        (str(record.outcome_reference.artifact_id),),
    ).fetchall()
    exact = []
    for row in rows:
        if (
            str(row[2]) != record.outcome_reference.content_hash
            or str(row[4]) != OutcomeAvailabilityStatus.COMPLETE.value
            or not isinstance(row[1], Mapping)
            or not isinstance(row[3], Mapping)
        ):
            continue
        outcome = TargetedShadowOutcome.from_canonical_dict(row[1])
        label = TargetOutcomeLabel.from_canonical_dict(row[3])
        if (
            outcome.settlement_hash == str(row[0])
            and label in outcome.labels
            and label.label_id == record.outcome_reference.artifact_id
            and label.label_hash == record.outcome_reference.content_hash
            and label.target.artifact_id == record.target_reference.artifact_id
            and label.target.content_hash == record.target_reference.content_hash
            and label.symbol == record.sample.symbol
            and label.label_interval_start
            == record.sample.sample_decision_time.value
            and record.outcome_reference.artifact_kind == "TARGET_OUTCOME_LABEL"
            and record.sample.source_artifact_id == outcome.settlement_id
            and record.sample.source_content_hash == outcome.settlement_hash
            and label.outcome_available_at <= record.sample.available_at.value
            and (
                None
                if record.sample.realized_return is None
                else Decimal(str(record.sample.realized_return))
            )
            == label.checkpoint_return
            and (
                None
                if record.sample.realized_mfe is None
                else Decimal(str(record.sample.realized_mfe))
            )
            == label.mfe
            and (
                None
                if record.sample.realized_mae is None
                else Decimal(str(record.sample.realized_mae))
            )
            == label.mae
        ):
            exact.append(label)
    if len(exact) != 1:
        raise ValueError("Research Model Target Label owner mismatch")
    return exact[0]


def _rebuild_request(
    request: ResearchModelTrainingRequest,
    *,
    samples: tuple[ResearchTrainingSample, ...] | None = None,
    folds: tuple[WalkForwardFold, ...] | None = None,
    feature_names: tuple[str, ...] | None = None,
    limitations: tuple[str, ...],
) -> ResearchModelTrainingRequest:
    return ResearchModelTrainingRequest.create(
        model_definition_reference=request.model_definition_reference,
        configuration_reference=request.configuration_reference,
        feature_catalog_reference=request.feature_catalog_reference,
        target_protocol_reference=request.target_protocol_reference,
        dataset_references=request.dataset_references,
        locked_oos_reference=request.locked_oos_reference,
        locked_oos_sample_ids=request.locked_oos_sample_ids,
        oos_start_date=request.oos_start_date,
        session_sequence=request.session_sequence,
        samples=request.samples if samples is None else samples,
        folds=request.folds if folds is None else folds,
        feature_names=(
            request.feature_names if feature_names is None else feature_names
        ),
        continuous_target_names=request.continuous_target_names,
        barrier_target_names=request.barrier_target_names,
        penalty_candidates=request.penalty_candidates,
        fold_seed=request.fold_seed,
        code_revision=request.code_revision,
        code_hash=request.code_hash,
        requested_at=request.requested_at,
        experiment_definition=request.experiment_definition,
        measure_bindings=request.measure_bindings,
        limitations=tuple(sorted(set(limitations))),
    )


def _mapping(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("Research Model owner payload must be an object")
    return value


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
