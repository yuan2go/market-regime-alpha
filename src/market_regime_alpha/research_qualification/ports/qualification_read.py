"""Generation-safe exact-ID read port for admitted Research Qualification."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class AdmittedResearchQualification:
    research_qualification_decision_id: UUID
    research_assessment_id: UUID
    research_qualification_policy_id: UUID
    experiment_id: UUID
    target_definition_id: UUID
    qualification_purpose: str
    source_generation_max_decision_time: datetime
    effective_at: datetime
    known_at: datetime
    content_sha256: str


class ResearchQualificationAdmissionReadPort(Protocol):
    def admitted_by_id(
        self,
        research_qualification_decision_id: UUID,
        *,
        requested_knowledge_cutoff: datetime,
        consumer_generation_time: datetime,
    ) -> AdmittedResearchQualification | None: ...


__all__ = [
    "AdmittedResearchQualification",
    "ResearchQualificationAdmissionReadPort",
]
