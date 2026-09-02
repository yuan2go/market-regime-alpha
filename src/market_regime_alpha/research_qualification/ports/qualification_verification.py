"""Read-only verifier port for WP-12 Research Authorities."""

from typing import Protocol
from uuid import UUID

from market_regime_alpha.research_qualification.domain.verification import (
    ResearchVerificationMismatch,
)


class ResearchQualificationVerificationProvider(Protocol):
    def inspect_evidence(
        self, evidence_item_id: UUID
    ) -> tuple[ResearchVerificationMismatch, ...]: ...

    def inspect_assessment(
        self, research_assessment_id: UUID
    ) -> tuple[ResearchVerificationMismatch, ...]: ...

    def inspect_policy(
        self, research_qualification_policy_id: UUID
    ) -> tuple[ResearchVerificationMismatch, ...]: ...

    def inspect_decision(
        self, research_qualification_decision_id: UUID
    ) -> tuple[ResearchVerificationMismatch, ...]: ...


__all__ = ["ResearchQualificationVerificationProvider"]
