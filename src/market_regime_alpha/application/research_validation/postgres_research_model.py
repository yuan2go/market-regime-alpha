"""PostgreSQL journal for exploratory model selection, artifacts and inference."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Mapping

from psycopg.types.json import Jsonb

from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.application.research_validation.factor_extraction import (
    ResearchPanelEnrichment,
)
from market_regime_alpha.application.research_validation.formal_protocol import (
    ForecastMeasureKind,
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
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from market_regime_alpha.persistence.postgres.migrator import PostgresMigrator
from market_regime_alpha.platform.postgres_runtime_governance import (
    resolve_formal_research_model_lineage,
)


_OWNER_RESOLVED_PROVENANCE = "OWNER_RESOLVED_POSTGRES_INPUTS"
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

    feature_recorded_at = _verify_research_artifact_owner(
        connection,
        request.feature_catalog_reference,
        expected_kind="FEATURE_DEFINITION_SET",
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

    historical_references = set(protocol.historical_sample_dataset_references)
    request_references = set(request.dataset_references)
    if not historical_references.issubset(request_references):
        raise ValueError("Research Model request omits frozen Historical Dataset owners")
    extra_references = request_references - historical_references
    if any(item.artifact_kind != "PANEL_ENRICHMENT" for item in extra_references):
        raise ValueError("Research Model dataset scope contains unsupported owner kinds")

    dataset_owners = {
        reference: _load_historical_dataset_owner(connection, reference)
        for reference in protocol.historical_sample_dataset_references
    }
    enrichment_owners = {
        reference: _load_panel_enrichment_owner(connection, reference)
        for reference in sorted(
            extra_references,
            key=lambda item: (item.artifact_kind, str(item.artifact_id)),
        )
    }
    if not enrichment_owners:
        raise ValueError("Owner-resolved Research Model training requires Panel Enrichment owners")

    expected_locked_ids = tuple(
        sorted((ArtifactId(item) for item in roster.label_ids), key=str)
    )
    if request.locked_oos_sample_ids != expected_locked_ids:
        raise ValueError("Research Model Locked OOS member identities diverged")
    if request.oos_start_date != roster.oos_start_date:
        raise ValueError("Research Model Locked OOS start date diverged")
    if request.session_sequence != protocol.frozen_trading_dates:
        raise ValueError("Research Model session sequence is not the frozen Calendar owner")

    bindings = {item.training_target_name: item for item in request.measure_bindings}
    resolved_samples: list[ResearchTrainingSample] = []
    sample_ids: dict[ArtifactId, ArtifactId] = {}
    latest_input_at = max(
        model.owner_recorded_at,
        feature_recorded_at,
        target_recorded_at,
        roster.frozen_at,
        *(item[1] for item in dataset_owners.values()),
        *(item[1] for item in enrichment_owners.values()),
    )
    for sample in request.samples:
        features = tuple(
            _resolve_feature_owner(
                sample=sample,
                feature=feature,
                owners=enrichment_owners,
            )
            for feature in sample.features
        )
        targets = tuple(
            _resolve_target_owner(
                sample=sample,
                target=target,
                binding=bindings[target.name],
                owners=dataset_owners,
            )
            for target in sample.targets
        )
        resolved = ResearchTrainingSample.create(
            symbol=sample.symbol,
            trading_date=sample.trading_date,
            decision_time=sample.decision_time,
            features=features,
            targets=targets,
        )
        sample_ids[sample.sample_id] = resolved.sample_id
        resolved_samples.append(resolved)
        latest_input_at = max(
            latest_input_at,
            *(item.available_at for item in features),
            *(item.available_at for item in targets),
        )
    if request.requested_at < latest_input_at:
        raise ValueError("Research Model request predates required owner availability")
    folds = tuple(
        WalkForwardFold(
            fold_name=fold.fold_name,
            train_sample_ids=tuple(
                sorted((sample_ids[item] for item in fold.train_sample_ids), key=str)
            ),
            validation_sample_ids=tuple(
                sorted(
                    (sample_ids[item] for item in fold.validation_sample_ids),
                    key=str,
                )
            ),
            purge_sessions=fold.purge_sessions,
            embargo_sessions=fold.embargo_sessions,
        )
        for fold in request.folds
    )
    return _rebuild_request(
        request,
        samples=tuple(resolved_samples),
        folds=folds,
        limitations=(*request.limitations, _OWNER_RESOLVED_PROVENANCE),
    )


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


def _load_panel_enrichment_owner(
    connection: Any, reference: ValidationArtifactReference
) -> tuple[ResearchPanelEnrichment, datetime]:
    recorded_at = _verify_research_artifact_owner(
        connection, reference, expected_kind="PANEL_ENRICHMENT"
    )
    row = connection.execute(
        "SELECT payload_json FROM research_validation_artifact WHERE artifact_id = %s",
        (str(reference.artifact_id),),
    ).fetchone()
    assert row is not None and isinstance(row[0], Mapping)
    enrichment = ResearchPanelEnrichment.from_canonical_dict(
        {
            "enrichment_id": str(reference.artifact_id),
            "enrichment_hash": reference.content_hash,
            **dict(row[0]),
        }
    )
    projections = connection.execute(
        """
        SELECT exposure_json FROM research_panel_factor_exposure
        WHERE enrichment_id = %s
        ORDER BY symbol, factor_family, factor_id, timeframe,
                 exposure_json->>'source_value_path'
        """,
        (str(reference.artifact_id),),
    ).fetchall()
    if [item[0] for item in projections] != [
        item.to_canonical_dict() for item in enrichment.exposures
    ]:
        raise ValueError("Research Model Panel Enrichment projection mismatch")
    return enrichment, recorded_at


def _resolve_feature_owner(
    *,
    sample: ResearchTrainingSample,
    feature: TimedResearchFeature,
    owners: Mapping[
        ValidationArtifactReference, tuple[ResearchPanelEnrichment, datetime]
    ],
) -> TimedResearchFeature:
    owner = owners.get(feature.source_reference)
    if owner is None:
        raise ValueError("Research Model feature source is not a frozen dataset owner")
    enrichment, recorded_at = owner
    matches = tuple(
        item
        for item in enrichment.exposures
        if item.symbol == sample.symbol and item.factor_id == feature.name
    )
    if len(matches) != 1:
        raise ValueError("Research Model feature owner is missing or ambiguous")
    exposure = matches[0]
    path_values = {
        f"exposures.{feature.name}.raw_numeric": exposure.raw_numeric,
        f"exposures.{feature.name}.normalized_exposure": exposure.normalized_exposure,
        f"exposures.{feature.name}.model_contribution": exposure.model_contribution,
    }
    if feature.source_value_path not in path_values:
        raise ValueError("Research Model feature source path is unsupported")
    available_at = exposure.available_at or recorded_at
    return TimedResearchFeature(
        name=feature.name,
        value=path_values[feature.source_value_path],
        effective_at=feature.effective_at,
        available_at=available_at,
        source_reference=feature.source_reference,
        source_value_path=feature.source_value_path,
    )


def _resolve_target_owner(
    *,
    sample: ResearchTrainingSample,
    target: TimedResearchTarget,
    binding: Any,
    owners: Mapping[
        ValidationArtifactReference, tuple[HistoricalSampleDataset, datetime]
    ],
) -> TimedResearchTarget:
    owner = owners.get(target.source_reference)
    if owner is None:
        raise ValueError("Research Model target source is not a frozen dataset owner")
    dataset, _recorded_at = owner
    if dataset.target_reference != binding.target_reference:
        raise ValueError("Research Model target owner Target identity mismatch")
    matches = tuple(
        item
        for item in dataset.records
        if item.sample.symbol == sample.symbol
        and item.sample.sample_decision_time.value == sample.decision_time
    )
    if len(matches) != 1:
        raise ValueError("Research Model target owner is missing or ambiguous")
    record = matches[0]
    expected_path, value = _historical_target_value(record, binding.measure_kind)
    if target.source_value_path != expected_path:
        raise ValueError("Research Model target source path diverged")
    return TimedResearchTarget(
        name=target.name,
        value=value,
        available_at=record.sample.available_at.value,
        source_reference=target.source_reference,
        source_value_path=target.source_value_path,
    )


def _historical_target_value(
    record: HistoricalPathSampleRecord,
    measure: ForecastMeasureKind,
) -> tuple[str, Decimal | bool]:
    prefix = f"records.{record.record_id}.sample"
    if measure in {
        ForecastMeasureKind.RANKING_SCORE,
        ForecastMeasureKind.EXPECTED_RETURN,
    }:
        value = record.sample.realized_return
        field = "realized_return"
    elif measure is ForecastMeasureKind.EXPECTED_MFE:
        value = record.sample.realized_mfe
        field = "realized_mfe"
    elif measure in {
        ForecastMeasureKind.EXPECTED_MAE,
        ForecastMeasureKind.EXPECTED_DOWNSIDE,
    }:
        value = record.sample.realized_mae
        field = "realized_mae"
    elif measure is ForecastMeasureKind.RETURN_POSITIVE_RAW_LOGIT:
        value = record.sample.realized_return
        if value is None:
            raise ValueError("Research Model return-direction target is unavailable")
        return f"{prefix}.realized_return_positive", value > 0
    else:
        raise ValueError(
            "Historical Dataset owner cannot establish the requested barrier target"
        )
    if value is None:
        raise ValueError("Research Model continuous target owner value is unavailable")
    return f"{prefix}.{field}", Decimal(str(value))


def _rebuild_request(
    request: ResearchModelTrainingRequest,
    *,
    samples: tuple[ResearchTrainingSample, ...] | None = None,
    folds: tuple[WalkForwardFold, ...] | None = None,
    limitations: tuple[str, ...] | None = None,
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
        feature_names=request.feature_names,
        continuous_target_names=request.continuous_target_names,
        barrier_target_names=request.barrier_target_names,
        penalty_candidates=request.penalty_candidates,
        fold_seed=request.fold_seed,
        code_revision=request.code_revision,
        code_hash=request.code_hash,
        requested_at=request.requested_at,
        experiment_definition=request.experiment_definition,
        measure_bindings=request.measure_bindings,
        limitations=(
            request.limitations if limitations is None else tuple(sorted(set(limitations)))
        ),
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
