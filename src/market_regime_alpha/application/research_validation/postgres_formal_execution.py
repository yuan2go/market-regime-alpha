"""PostgreSQL owner and resolver for ordered Formal execution assessments."""

from __future__ import annotations

from typing import Any, Mapping

from psycopg.types.json import Jsonb

from market_regime_alpha.application.research_validation.formal_execution import (
    FormalExecutionAssessment,
    FormalExecutionOwnerResolver,
    FormalExecutionRequest,
    assess_formal_execution,
)
from market_regime_alpha.application.research_validation.postgres_calibration_qualification import (
    PostgresCalibrationQualificationAuthority,
)
from market_regime_alpha.application.research_validation.postgres_formal_protocol import (
    PostgresFormalProtocolRepository,
)
from market_regime_alpha.application.research_validation.postgres_qualification import (
    PostgresResearchQualificationAuthority,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.data.postgres_pit_authority import PostgresPITAuthority
from market_regime_alpha.data.postgres_provider_qualification import (
    PostgresProviderFactQualificationAuthority,
)
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from market_regime_alpha.persistence.postgres.migrator import PostgresMigrator
from market_regime_alpha.platform.runtime_governance import (
    ModelQualificationDecision,
)


class PostgresFormalExecutionOwnerResolver(FormalExecutionOwnerResolver):
    def __init__(self, factory: PostgresConnectionFactory) -> None:
        self._factory = factory
        self._providers = PostgresProviderFactQualificationAuthority(
            factory, apply_migrations=False
        )
        self._protocols = PostgresFormalProtocolRepository(
            factory, apply_migrations=False
        )
        self._pit = PostgresPITAuthority(factory)
        self._qualification = PostgresResearchQualificationAuthority(
            factory, apply_migrations=False
        )
        self._calibration = PostgresCalibrationQualificationAuthority(
            factory, apply_migrations=False
        )

    def provider_fact(self, decision_id: ArtifactId):
        return self._providers.get(decision_id)

    def protocol(self, protocol_id: ArtifactId):
        return self._protocols.get_protocol(protocol_id)

    def formal_pit(self, evidence_id: ArtifactId):
        return self._pit.get_evidence(evidence_id)

    def historical(self, decision_id: ArtifactId):
        return self._qualification.get_historical_sample_decision(decision_id)

    def model(self, decision_id: ArtifactId) -> ModelQualificationDecision:
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                "SELECT decision_hash, payload_json FROM model_qualification_decision WHERE decision_id = %s",
                (str(decision_id),),
            ).fetchone()
        if row is None or not isinstance(row[1], Mapping):
            raise KeyError(str(decision_id))
        decision = ModelQualificationDecision.from_canonical_dict(row[1])
        if decision.decision_hash != str(row[0]):
            raise ValueError("Model Qualification owner hash diverged")
        return decision

    def formal_oos(self, decision_id: ArtifactId):
        return self._qualification.get_formal_oos_decision(decision_id)

    def calibration(self, decision_id: ArtifactId):
        return self._calibration.get(decision_id)


class PostgresFormalExecutionRepository:
    def __init__(
        self,
        factory: PostgresConnectionFactory,
        *,
        apply_migrations: bool = False,
    ) -> None:
        self._factory = factory
        if apply_migrations:
            PostgresMigrator().apply_all(factory)

    def assess(self, request: FormalExecutionRequest) -> FormalExecutionAssessment:
        self.publish_request(request)
        existing = self.find_assessment(request.request_id)
        if existing is not None:
            return existing
        assessment = assess_formal_execution(
            request,
            resolver=PostgresFormalExecutionOwnerResolver(self._factory),
        )
        return self.publish_assessment(assessment)

    def publish_request(self, request: FormalExecutionRequest) -> FormalExecutionRequest:
        def operation(connection: Any) -> None:
            connection.execute(
                """
                INSERT INTO formal_execution_request(
                    request_id, request_hash, idempotency_key,
                    provider_requirement_count, formal_protocol_id,
                    assessed_at, actor, reason, payload_json
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (request_id) DO NOTHING
                """,
                (
                    str(request.request_id), request.request_hash,
                    request.idempotency_key, len(request.provider_requirements),
                    None if request.formal_protocol_id is None else str(request.formal_protocol_id),
                    request.assessed_at, request.actor, request.reason,
                    Jsonb(request.to_canonical_dict()),
                ),
            )
            stored = connection.execute(
                "SELECT request_hash, payload_json FROM formal_execution_request WHERE request_id = %s",
                (str(request.request_id),),
            ).fetchone()
            if stored is None or str(stored[0]) != request.request_hash or stored[1] != request.to_canonical_dict():
                raise ValueError("Formal Execution request identity conflict")
            for ordinal, requirement in enumerate(request.provider_requirements, start=1):
                connection.execute(
                    """
                    INSERT INTO formal_execution_provider_requirement(
                        request_id, ordinal, provider_id, provider_contract,
                        fact_kind, decision_id, payload_json
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (request_id, ordinal) DO NOTHING
                    """,
                    (
                        str(request.request_id), ordinal, requirement.provider_id,
                        requirement.provider_contract, requirement.fact_kind.value,
                        None if requirement.decision_id is None else str(requirement.decision_id),
                        Jsonb(requirement.to_canonical_dict()),
                    ),
                )
            self._verify_request_projection(connection, request)

        self._factory.run_transaction(operation)
        return self.get_request(request.request_id)

    def get_request(self, request_id: ArtifactId) -> FormalExecutionRequest:
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                "SELECT request_hash, payload_json FROM formal_execution_request WHERE request_id = %s",
                (str(request_id),),
            ).fetchone()
            if row is None or not isinstance(row[1], Mapping):
                raise KeyError(str(request_id))
            request = FormalExecutionRequest.from_canonical_dict(row[1])
            if request.request_hash != str(row[0]):
                raise ValueError("Formal Execution request owner hash diverged")
            self._verify_request_projection(connection, request)
        return request

    def publish_assessment(
        self, assessment: FormalExecutionAssessment
    ) -> FormalExecutionAssessment:
        request = self.get_request(assessment.request_reference.artifact_id)
        if (
            assessment.request_reference.artifact_id != request.request_id
            or assessment.request_reference.content_hash != request.request_hash
        ):
            raise ValueError("Formal Execution assessment/request binding mismatch")

        def operation(connection: Any) -> None:
            connection.execute(
                """
                INSERT INTO formal_execution_assessment(
                    assessment_id, assessment_hash, request_id, status,
                    terminal_stage, formal_model_qualified,
                    formal_oos_alpha_established, calibrated,
                    production_authorized, payload_json, assessed_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, false, %s, %s)
                ON CONFLICT (assessment_id) DO NOTHING
                """,
                (
                    str(assessment.assessment_id), assessment.assessment_hash,
                    str(request.request_id), assessment.status.value,
                    assessment.terminal_stage.value,
                    assessment.formal_model_qualified,
                    assessment.formal_oos_alpha_established,
                    assessment.calibrated,
                    Jsonb(assessment.to_canonical_dict()), assessment.assessed_at,
                ),
            )
            stored = connection.execute(
                "SELECT assessment_hash, payload_json FROM formal_execution_assessment WHERE assessment_id = %s",
                (str(assessment.assessment_id),),
            ).fetchone()
            if stored is None or str(stored[0]) != assessment.assessment_hash or stored[1] != assessment.to_canonical_dict():
                raise ValueError("Formal Execution assessment identity conflict")
            for ordinal, stage in enumerate(assessment.stages, start=1):
                connection.execute(
                    """
                    INSERT INTO formal_execution_stage_assessment(
                        assessment_id, ordinal, stage, status, payload_json
                    ) VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (assessment_id, ordinal) DO NOTHING
                    """,
                    (
                        str(assessment.assessment_id), ordinal, stage.stage.value,
                        stage.status.value, Jsonb(stage.to_canonical_dict()),
                    ),
                )
            for ordinal, reference in enumerate(assessment.source_references, start=1):
                connection.execute(
                    """
                    INSERT INTO formal_execution_source_binding(
                        assessment_id, ordinal, artifact_kind, artifact_id, content_hash
                    ) VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (assessment_id, ordinal) DO NOTHING
                    """,
                    (
                        str(assessment.assessment_id), ordinal,
                        reference.artifact_kind, str(reference.artifact_id),
                        reference.content_hash,
                    ),
                )
            self._verify_assessment_projection(connection, assessment)

        self._factory.run_transaction(operation)
        return self.get_assessment(assessment.assessment_id)

    def find_assessment(self, request_id: ArtifactId) -> FormalExecutionAssessment | None:
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                "SELECT assessment_id FROM formal_execution_assessment WHERE request_id = %s",
                (str(request_id),),
            ).fetchone()
        return None if row is None else self.get_assessment(ArtifactId(str(row[0])))

    def get_assessment(self, assessment_id: ArtifactId) -> FormalExecutionAssessment:
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                "SELECT assessment_hash, payload_json FROM formal_execution_assessment WHERE assessment_id = %s",
                (str(assessment_id),),
            ).fetchone()
            if row is None or not isinstance(row[1], Mapping):
                raise KeyError(str(assessment_id))
            assessment = FormalExecutionAssessment.from_canonical_dict(row[1])
            if assessment.assessment_hash != str(row[0]):
                raise ValueError("Formal Execution assessment owner hash diverged")
            self._verify_assessment_projection(connection, assessment)
        return assessment

    def replay(self, assessment_id: ArtifactId) -> FormalExecutionAssessment:
        stored = self.get_assessment(assessment_id)
        request = self.get_request(stored.request_reference.artifact_id)
        replayed = assess_formal_execution(
            request,
            resolver=PostgresFormalExecutionOwnerResolver(self._factory),
        )
        if replayed != stored:
            raise ValueError("Formal Execution deterministic replay diverged")
        return stored

    @staticmethod
    def _verify_request_projection(connection: Any, request: FormalExecutionRequest) -> None:
        rows = connection.execute(
            "SELECT payload_json FROM formal_execution_provider_requirement WHERE request_id = %s ORDER BY ordinal",
            (str(request.request_id),),
        ).fetchall()
        if [row[0] for row in rows] != [item.to_canonical_dict() for item in request.provider_requirements]:
            raise ValueError("Formal Execution Provider projection diverged")

    @staticmethod
    def _verify_assessment_projection(connection: Any, assessment: FormalExecutionAssessment) -> None:
        stages = connection.execute(
            "SELECT payload_json FROM formal_execution_stage_assessment WHERE assessment_id = %s ORDER BY ordinal",
            (str(assessment.assessment_id),),
        ).fetchall()
        sources = connection.execute(
            "SELECT artifact_kind, artifact_id, content_hash FROM formal_execution_source_binding WHERE assessment_id = %s ORDER BY ordinal",
            (str(assessment.assessment_id),),
        ).fetchall()
        if [row[0] for row in stages] != [item.to_canonical_dict() for item in assessment.stages]:
            raise ValueError("Formal Execution stage projection diverged")
        if [tuple(str(item) for item in row) for row in sources] != [
            (item.artifact_kind, str(item.artifact_id), item.content_hash)
            for item in assessment.source_references
        ]:
            raise ValueError("Formal Execution source projection diverged")


__all__ = [
    "PostgresFormalExecutionOwnerResolver",
    "PostgresFormalExecutionRepository",
]
