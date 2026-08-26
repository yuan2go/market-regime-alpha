"""PostgreSQL persistence for typed Alpha-correctness failure details."""

from __future__ import annotations

from typing import Any, Mapping

from psycopg.types.json import Jsonb

from market_regime_alpha.application.historical_corpus.correctness_failures import (
    AlphaCorrectnessFailureIndex,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from market_regime_alpha.persistence.postgres.migrator import PostgresMigrator


class AlphaCorrectnessFailureConflict(RuntimeError):
    """Stored correctness failure identity or owner lineage diverged."""


class PostgresAlphaCorrectnessFailureRepository:
    """Append-only owner for one source Evidence's typed failure index."""

    def __init__(
        self,
        factory: PostgresConnectionFactory,
        *,
        apply_migrations: bool = False,
    ) -> None:
        self._factory = factory
        if apply_migrations:
            PostgresMigrator().apply_all(factory)

    def put(
        self, index: AlphaCorrectnessFailureIndex
    ) -> AlphaCorrectnessFailureIndex:
        def operation(connection: Any) -> None:
            self._verify_owners(connection, index)
            connection.execute(
                """
                INSERT INTO alpha_correctness_failure_index(
                    index_id, index_hash, source_run_id, source_command_hash,
                    source_evidence_id, source_evidence_hash,
                    experiment_id, experiment_hash,
                    target_protocol_id, target_protocol_hash,
                    calendar_id, calendar_hash,
                    raw_owner_id, raw_owner_hash,
                    normalized_owner_id, normalized_owner_hash,
                    normalization_revision, analysis_code_sha,
                    semantic_revision, detail_count, payload_json, created_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                ) ON CONFLICT DO NOTHING
                """,
                (
                    str(index.index_id),
                    index.index_hash,
                    str(index.source_run_reference.artifact_id),
                    index.source_run_reference.content_hash,
                    str(index.source_evidence_reference.artifact_id),
                    index.source_evidence_reference.content_hash,
                    str(index.experiment_reference.artifact_id),
                    index.experiment_reference.content_hash,
                    str(index.target_protocol_reference.artifact_id),
                    index.target_protocol_reference.content_hash,
                    str(index.calendar_reference.artifact_id),
                    index.calendar_reference.content_hash,
                    str(index.raw_owner_reference.artifact_id),
                    index.raw_owner_reference.content_hash,
                    str(index.normalized_owner_reference.artifact_id),
                    index.normalized_owner_reference.content_hash,
                    index.normalization_revision,
                    index.analysis_code_sha,
                    index.semantic_revision,
                    len(index.details),
                    Jsonb(index.to_canonical_dict()),
                    index.created_at,
                ),
            )
            for ordinal, detail in enumerate(index.details, 1):
                connection.execute(
                    """
                    INSERT INTO alpha_correctness_failure_detail(
                        index_id, index_hash, ordinal, detail_id, detail_hash,
                        decision_session, decision_time, target_session,
                        target_window_end, symbol, classification,
                        discrepancy_code, payload_json
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s
                    ) ON CONFLICT DO NOTHING
                    """,
                    (
                        str(index.index_id),
                        index.index_hash,
                        ordinal,
                        str(detail.detail_id),
                        detail.detail_hash,
                        detail.decision_session,
                        detail.decision_time,
                        detail.target_session,
                        detail.target_window_end,
                        detail.symbol,
                        detail.classification,
                        detail.discrepancy_code,
                        Jsonb(detail.to_canonical_dict()),
                    ),
                )
                for source_ordinal, binding in enumerate(
                    detail.source_bindings, 1
                ):
                    reference = binding.reference
                    connection.execute(
                        """
                        INSERT INTO alpha_correctness_failure_source_binding(
                            detail_id, detail_hash, ordinal, source_role,
                            artifact_kind, artifact_id, content_hash
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT DO NOTHING
                        """,
                        (
                            str(detail.detail_id),
                            detail.detail_hash,
                            source_ordinal,
                            binding.source_role,
                            reference.artifact_kind,
                            str(reference.artifact_id),
                            reference.content_hash,
                        ),
                    )
            self._verify_projection(connection, index)

        self._factory.run_transaction(operation)
        return self.get(index.index_id)

    def get(self, index_id: ArtifactId) -> AlphaCorrectnessFailureIndex:
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                """
                SELECT payload_json FROM alpha_correctness_failure_index
                WHERE index_id = %s
                """,
                (str(index_id),),
            ).fetchone()
            if row is None or not isinstance(row[0], Mapping):
                raise KeyError(str(index_id))
            index = AlphaCorrectnessFailureIndex.from_canonical_dict(row[0])
            self._verify_owners(connection, index)
            self._verify_projection(connection, index)
        return index

    def get_for_source(
        self,
        *,
        run_id: ArtifactId,
        evidence_id: ArtifactId,
        semantic_revision: str,
    ) -> AlphaCorrectnessFailureIndex:
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                """
                SELECT index_id FROM alpha_correctness_failure_index
                WHERE source_run_id = %s AND source_evidence_id = %s
                  AND semantic_revision = %s
                """,
                (str(run_id), str(evidence_id), semantic_revision),
            ).fetchone()
        if row is None:
            raise KeyError(
                f"{run_id}/{evidence_id}/{semantic_revision}"
            )
        return self.get(ArtifactId(str(row[0])))

    @staticmethod
    def _verify_owners(
        connection: Any,
        index: AlphaCorrectnessFailureIndex,
    ) -> None:
        run = connection.execute(
            """
            SELECT command_hash, experiment_definition_id,
                   experiment_definition_hash, target_protocol_id,
                   target_protocol_hash, trading_calendar_id,
                   trading_calendar_hash
            FROM historical_research_run WHERE run_id = %s
            """,
            (str(index.source_run_reference.artifact_id),),
        ).fetchone()
        expected_run = (
            index.source_run_reference.content_hash,
            str(index.experiment_reference.artifact_id),
            index.experiment_reference.content_hash,
            str(index.target_protocol_reference.artifact_id),
            index.target_protocol_reference.content_hash,
            str(index.calendar_reference.artifact_id),
            index.calendar_reference.content_hash,
        )
        if run is None or tuple(str(item) for item in run) != expected_run:
            raise AlphaCorrectnessFailureConflict(
                "correctness failure source run owner mismatch"
            )
        evidence = connection.execute(
            """
            SELECT evidence_hash, run_id, command_hash, experiment_id,
                   experiment_hash, evidence_kind
            FROM historical_research_evidence WHERE evidence_id = %s
            """,
            (str(index.source_evidence_reference.artifact_id),),
        ).fetchone()
        expected_evidence = (
            index.source_evidence_reference.content_hash,
            str(index.source_run_reference.artifact_id),
            index.source_run_reference.content_hash,
            str(index.experiment_reference.artifact_id),
            index.experiment_reference.content_hash,
            "ALPHA_CORRECTNESS",
        )
        if evidence is None or tuple(str(item) for item in evidence) != (
            expected_evidence
        ):
            raise AlphaCorrectnessFailureConflict(
                "correctness failure source Evidence owner mismatch"
            )
        experiment = connection.execute(
            """
            SELECT artifact_hash, artifact_kind
            FROM research_validation_artifact WHERE artifact_id = %s
            """,
            (str(index.experiment_reference.artifact_id),),
        ).fetchone()
        if experiment is None or tuple(str(item) for item in experiment) != (
            index.experiment_reference.content_hash,
            "RESEARCH_EXPERIMENT_DEFINITION",
        ):
            raise AlphaCorrectnessFailureConflict(
                "correctness failure Experiment owner mismatch"
            )
        target = connection.execute(
            """
            SELECT protocol_hash FROM outcome_target_protocol
            WHERE protocol_id = %s
            """,
            (str(index.target_protocol_reference.artifact_id),),
        ).fetchone()
        if target is None or str(target[0]) != (
            index.target_protocol_reference.content_hash
        ):
            raise AlphaCorrectnessFailureConflict(
                "correctness failure Target owner mismatch"
            )
        normalized = connection.execute(
            """
            SELECT content_hash, artifact_kind, normalization_version,
                   parent_owner_id, parent_owner_hash
            FROM historical_corpus_owner WHERE owner_id = %s
            """,
            (str(index.normalized_owner_reference.artifact_id),),
        ).fetchone()
        expected_normalized = (
            index.normalized_owner_reference.content_hash,
            "NORMALIZED_DATASET",
            index.normalization_revision,
            str(index.raw_owner_reference.artifact_id),
            index.raw_owner_reference.content_hash,
        )
        if normalized is None or tuple(str(item) for item in normalized) != (
            expected_normalized
        ):
            raise AlphaCorrectnessFailureConflict(
                "correctness failure Normalized owner mismatch"
            )
        raw = connection.execute(
            """
            SELECT content_hash, artifact_kind
            FROM historical_corpus_owner WHERE owner_id = %s
            """,
            (str(index.raw_owner_reference.artifact_id),),
        ).fetchone()
        if raw is None or tuple(str(item) for item in raw) != (
            index.raw_owner_reference.content_hash,
            "RAW_PROVIDER_ARCHIVE",
        ):
            raise AlphaCorrectnessFailureConflict(
                "correctness failure Raw owner mismatch"
            )

    @staticmethod
    def _verify_projection(
        connection: Any,
        index: AlphaCorrectnessFailureIndex,
    ) -> None:
        row = connection.execute(
            """
            SELECT index_hash, source_run_id, source_command_hash,
                   source_evidence_id, source_evidence_hash,
                   experiment_id, experiment_hash,
                   target_protocol_id, target_protocol_hash,
                   calendar_id, calendar_hash,
                   raw_owner_id, raw_owner_hash,
                   normalized_owner_id, normalized_owner_hash,
                   normalization_revision, analysis_code_sha,
                   semantic_revision, detail_count, payload_json, created_at
            FROM alpha_correctness_failure_index WHERE index_id = %s
            """,
            (str(index.index_id),),
        ).fetchone()
        expected = (
            index.index_hash,
            str(index.source_run_reference.artifact_id),
            index.source_run_reference.content_hash,
            str(index.source_evidence_reference.artifact_id),
            index.source_evidence_reference.content_hash,
            str(index.experiment_reference.artifact_id),
            index.experiment_reference.content_hash,
            str(index.target_protocol_reference.artifact_id),
            index.target_protocol_reference.content_hash,
            str(index.calendar_reference.artifact_id),
            index.calendar_reference.content_hash,
            str(index.raw_owner_reference.artifact_id),
            index.raw_owner_reference.content_hash,
            str(index.normalized_owner_reference.artifact_id),
            index.normalized_owner_reference.content_hash,
            index.normalization_revision,
            index.analysis_code_sha,
            index.semantic_revision,
            len(index.details),
            index.to_canonical_dict(),
            index.created_at,
        )
        actual = None if row is None else (*row[:19], dict(row[19]), row[20])
        if actual != expected:
            raise AlphaCorrectnessFailureConflict(
                "correctness failure index projection conflict"
            )
        detail_rows = connection.execute(
            """
            SELECT ordinal, detail_id, detail_hash, decision_session,
                   decision_time, target_session, target_window_end, symbol,
                   classification, discrepancy_code, payload_json
            FROM alpha_correctness_failure_detail
            WHERE index_id = %s AND index_hash = %s ORDER BY ordinal
            """,
            (str(index.index_id), index.index_hash),
        ).fetchall()
        expected_details = tuple(
            (
                ordinal,
                str(detail.detail_id),
                detail.detail_hash,
                detail.decision_session,
                detail.decision_time,
                detail.target_session,
                detail.target_window_end,
                detail.symbol,
                detail.classification,
                detail.discrepancy_code,
                detail.to_canonical_dict(),
            )
            for ordinal, detail in enumerate(index.details, 1)
        )
        actual_details = tuple(
            (*row[:10], dict(row[10])) for row in detail_rows
        )
        if actual_details != expected_details:
            raise AlphaCorrectnessFailureConflict(
                "correctness failure detail projection conflict"
            )
        for detail in index.details:
            bindings = connection.execute(
                """
                SELECT ordinal, source_role, artifact_kind, artifact_id,
                       content_hash
                FROM alpha_correctness_failure_source_binding
                WHERE detail_id = %s AND detail_hash = %s ORDER BY ordinal
                """,
                (str(detail.detail_id), detail.detail_hash),
            ).fetchall()
            expected_bindings = tuple(
                (
                    ordinal,
                    binding.source_role,
                    binding.reference.artifact_kind,
                    str(binding.reference.artifact_id),
                    binding.reference.content_hash,
                )
                for ordinal, binding in enumerate(detail.source_bindings, 1)
            )
            if tuple(tuple(item) for item in bindings) != expected_bindings:
                raise AlphaCorrectnessFailureConflict(
                    "correctness failure source projection conflict"
                )


__all__ = [
    "AlphaCorrectnessFailureConflict",
    "PostgresAlphaCorrectnessFailureRepository",
]
