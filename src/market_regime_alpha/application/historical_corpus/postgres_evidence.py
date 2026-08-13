"""PostgreSQL Authority repository for Phase E research findings."""

from __future__ import annotations

from typing import Any, Mapping

from psycopg.types.json import Jsonb

from market_regime_alpha.application.historical_corpus.evidence import (
    HistoricalResearchEvidence,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.persistence.postgres.connection import PostgresConnectionFactory
from market_regime_alpha.persistence.postgres.migrator import PostgresMigrator


class HistoricalEvidenceConflict(RuntimeError):
    """Stored evidence identity, lineage or relational projection diverged."""


class PostgresHistoricalEvidenceRepository:
    def __init__(
        self,
        factory: PostgresConnectionFactory,
        *,
        apply_migrations: bool = True,
    ) -> None:
        self._factory = factory
        if apply_migrations:
            PostgresMigrator().apply_all(factory)

    def put(self, evidence: HistoricalResearchEvidence) -> HistoricalResearchEvidence:
        evidence.verify_identity()

        def operation(connection: Any) -> None:
            run = connection.execute(
                """
                SELECT command_hash, experiment_definition_id,
                       experiment_definition_hash
                FROM historical_research_run WHERE run_id = %s
                """,
                (str(evidence.run_id),),
            ).fetchone()
            expected_run = (
                evidence.command_hash,
                str(evidence.experiment_reference.artifact_id),
                evidence.experiment_reference.content_hash,
            )
            if run is None or tuple(str(item) for item in run) != expected_run:
                raise HistoricalEvidenceConflict(
                    "Historical Evidence run/Experiment owner mismatch"
                )
            connection.execute(
                """
                INSERT INTO historical_research_evidence(
                    evidence_id, evidence_hash, run_id, command_hash,
                    experiment_id, experiment_hash, evidence_kind,
                    research_question, classification, rationale,
                    payload_json, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (evidence_id) DO NOTHING
                """,
                (
                    str(evidence.evidence_id),
                    evidence.evidence_hash,
                    str(evidence.run_id),
                    evidence.command_hash,
                    str(evidence.experiment_reference.artifact_id),
                    evidence.experiment_reference.content_hash,
                    evidence.evidence_kind.value,
                    evidence.research_question,
                    evidence.classification.value,
                    evidence.rationale,
                    Jsonb(evidence.to_canonical_dict()),
                    evidence.created_at,
                ),
            )
            for ordinal, source in enumerate(evidence.source_references, 1):
                connection.execute(
                    """
                    INSERT INTO historical_research_evidence_source_binding(
                        evidence_id, evidence_hash, ordinal, artifact_kind,
                        artifact_id, content_hash
                    ) VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (evidence_id, ordinal) DO NOTHING
                    """,
                    (
                        str(evidence.evidence_id),
                        evidence.evidence_hash,
                        ordinal,
                        source.artifact_kind,
                        str(source.artifact_id),
                        source.content_hash,
                    ),
                )
            for ordinal, metric in enumerate(evidence.metrics, 1):
                connection.execute(
                    """
                    INSERT INTO historical_research_evidence_metric(
                        evidence_id, evidence_hash, ordinal, variant_id,
                        slice_kind, slice_value, metric_name, metric_value,
                        metric_status, assumption_status
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (evidence_id, ordinal) DO NOTHING
                    """,
                    (
                        str(evidence.evidence_id),
                        evidence.evidence_hash,
                        ordinal,
                        metric.variant_id,
                        metric.slice_kind,
                        metric.slice_value,
                        metric.metric_name,
                        metric.metric_value,
                        metric.metric_status.value,
                        metric.assumption_status.value,
                    ),
                )
            self._verify_projection(connection, evidence)

        self._factory.run_transaction(operation)
        return self.get(evidence.evidence_id)

    def get(self, evidence_id: ArtifactId) -> HistoricalResearchEvidence:
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                """
                SELECT payload_json FROM historical_research_evidence
                WHERE evidence_id = %s
                """,
                (str(evidence_id),),
            ).fetchone()
            if row is None or not isinstance(row[0], Mapping):
                raise KeyError(str(evidence_id))
            evidence = HistoricalResearchEvidence.from_canonical_dict(row[0])
            self._verify_projection(connection, evidence)
        return evidence

    def list_for_run(
        self, run_id: ArtifactId
    ) -> tuple[HistoricalResearchEvidence, ...]:
        with self._factory.connection(read_only=True) as connection:
            rows = connection.execute(
                """
                SELECT evidence_id FROM historical_research_evidence
                WHERE run_id = %s ORDER BY evidence_kind, evidence_id
                """,
                (str(run_id),),
            ).fetchall()
        return tuple(self.get(ArtifactId(str(row[0]))) for row in rows)

    @staticmethod
    def _verify_projection(
        connection: Any, evidence: HistoricalResearchEvidence
    ) -> None:
        row = connection.execute(
            """
            SELECT evidence_hash, run_id, command_hash, experiment_id,
                   experiment_hash, evidence_kind, research_question,
                   classification, rationale, payload_json, created_at
            FROM historical_research_evidence WHERE evidence_id = %s
            """,
            (str(evidence.evidence_id),),
        ).fetchone()
        expected = (
            evidence.evidence_hash,
            str(evidence.run_id),
            evidence.command_hash,
            str(evidence.experiment_reference.artifact_id),
            evidence.experiment_reference.content_hash,
            evidence.evidence_kind.value,
            evidence.research_question,
            evidence.classification.value,
            evidence.rationale,
            evidence.to_canonical_dict(),
            evidence.created_at,
        )
        actual = None if row is None else (*row[:9], dict(row[9]), row[10])
        if actual != expected:
            raise HistoricalEvidenceConflict(
                "Historical Evidence PostgreSQL projection conflict"
            )
        sources = connection.execute(
            """
            SELECT ordinal, artifact_kind, artifact_id, content_hash
            FROM historical_research_evidence_source_binding
            WHERE evidence_id = %s AND evidence_hash = %s ORDER BY ordinal
            """,
            (str(evidence.evidence_id), evidence.evidence_hash),
        ).fetchall()
        expected_sources = tuple(
            (index, item.artifact_kind, str(item.artifact_id), item.content_hash)
            for index, item in enumerate(evidence.source_references, 1)
        )
        if tuple(
            (int(item[0]), str(item[1]), str(item[2]), str(item[3]))
            for item in sources
        ) != expected_sources:
            raise HistoricalEvidenceConflict(
                "Historical Evidence source projection conflict"
            )
        metrics = connection.execute(
            """
            SELECT variant_id, slice_kind, slice_value, metric_name,
                   metric_value, metric_status, assumption_status
            FROM historical_research_evidence_metric
            WHERE evidence_id = %s AND evidence_hash = %s ORDER BY ordinal
            """,
            (str(evidence.evidence_id), evidence.evidence_hash),
        ).fetchall()
        expected_metrics = tuple(
            (
                item.variant_id,
                item.slice_kind,
                item.slice_value,
                item.metric_name,
                item.metric_value,
                item.metric_status.value,
                item.assumption_status.value,
            )
            for item in evidence.metrics
        )
        if tuple(tuple(item) for item in metrics) != expected_metrics:
            raise HistoricalEvidenceConflict(
                "Historical Evidence metric projection conflict"
            )


__all__ = [
    "HistoricalEvidenceConflict",
    "PostgresHistoricalEvidenceRepository",
]
