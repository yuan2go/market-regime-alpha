"""Read-only WP-12 Evidence, Assessment, and Qualification verifier."""

from uuid import UUID

from market_regime_alpha.research_qualification.domain.verification import (
    ResearchVerificationReport,
)
from market_regime_alpha.research_qualification.ports.qualification_verification import (
    ResearchQualificationVerificationProvider,
)


class ResearchQualificationVerifier:
    def __init__(self, provider: ResearchQualificationVerificationProvider) -> None:
        self._provider = provider

    def verify_evidence(self, evidence_item_id: UUID) -> ResearchVerificationReport:
        return ResearchVerificationReport.create(
            authority_kind="EVIDENCE_ITEM",
            authority_id=evidence_item_id,
            mismatches=self._provider.inspect_evidence(evidence_item_id),
        )

    def verify_assessment(
        self, research_assessment_id: UUID
    ) -> ResearchVerificationReport:
        return ResearchVerificationReport.create(
            authority_kind="RESEARCH_ASSESSMENT",
            authority_id=research_assessment_id,
            mismatches=self._provider.inspect_assessment(research_assessment_id),
        )

    def verify_policy(
        self, research_qualification_policy_id: UUID
    ) -> ResearchVerificationReport:
        return ResearchVerificationReport.create(
            authority_kind="RESEARCH_QUALIFICATION_POLICY",
            authority_id=research_qualification_policy_id,
            mismatches=self._provider.inspect_policy(
                research_qualification_policy_id
            ),
        )

    def verify_decision(
        self, research_qualification_decision_id: UUID
    ) -> ResearchVerificationReport:
        return ResearchVerificationReport.create(
            authority_kind="RESEARCH_QUALIFICATION_DECISION",
            authority_id=research_qualification_decision_id,
            mismatches=self._provider.inspect_decision(
                research_qualification_decision_id
            ),
        )


__all__ = ["ResearchQualificationVerifier"]
