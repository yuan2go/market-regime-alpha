"""Exact-ID, cutoff-aware Research Qualification admission query."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from market_regime_alpha.research_qualification.ports.qualification_read import (
    AdmittedResearchQualification,
)


class PostgresResearchQualificationAdmissionReadPort:
    def __init__(self, pool: TargetPostgresPool) -> None:
        self._pool = pool

    def admitted_by_id(
        self,
        research_qualification_decision_id: UUID,
        *,
        requested_knowledge_cutoff: datetime,
        consumer_generation_time: datetime,
    ) -> AdmittedResearchQualification | None:
        for name, value in (
            ("requested_knowledge_cutoff", requested_knowledge_cutoff),
            ("consumer_generation_time", consumer_generation_time),
        ):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"{name} must be timezone-aware")
        with self._pool.connection(read_only=True) as connection:
            row = connection.execute(
                """
                SELECT research_qualification_decision_id,
                       research_assessment_id,
                       research_qualification_policy_id, experiment_id,
                       target_definition_id, qualification_purpose,
                       source_generation_max_decision_time,
                       effective_at, known_at, content_sha256
                FROM mra.research_qualification_decision
                WHERE research_qualification_decision_id = %s
                  AND decision_status = 'ADMITTED'
                  AND effective_at <= %s AND known_at <= %s
                  AND source_generation_max_decision_time < %s
                """,
                (
                    research_qualification_decision_id,
                    requested_knowledge_cutoff,
                    requested_knowledge_cutoff,
                    consumer_generation_time,
                ),
            ).fetchone()
        if row is None:
            return None
        return AdmittedResearchQualification(
            research_qualification_decision_id=UUID(str(row[0])),
            research_assessment_id=UUID(str(row[1])),
            research_qualification_policy_id=UUID(str(row[2])),
            experiment_id=UUID(str(row[3])),
            target_definition_id=UUID(str(row[4])),
            qualification_purpose=str(row[5]),
            source_generation_max_decision_time=row[6],
            effective_at=row[7],
            known_at=row[8],
            content_sha256=str(row[9]),
        )


__all__ = ["PostgresResearchQualificationAdmissionReadPort"]
