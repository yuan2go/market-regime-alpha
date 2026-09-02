from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from market_regime_alpha.decision_support.domain import (
    OpenDecisionRunRequest,
    PreparedResearchQualification,
    QualificationInputRole,
    ResearchPurpose,
    RequestedDecisionTarget,
    RequestedResearchQualification,
    build_decision_authority,
)
from tests.refoundation.decision_support.test_decision_domain import (
    DECISION_TIME,
    _candidate_snapshot,
    _references,
    _runtime,
    _target_snapshot,
    _uuid,
)


def _requested(
    suffix: int = 801,
    *,
    role: QualificationInputRole = QualificationInputRole.PRIMARY,
) -> RequestedResearchQualification:
    return RequestedResearchQualification(
        research_qualification_decision_id=_uuid(suffix),
        role=role,
    )


def _prepared(
    suffix: int = 801,
    *,
    role: QualificationInputRole = QualificationInputRole.PRIMARY,
) -> PreparedResearchQualification:
    return PreparedResearchQualification(
        research_qualification_decision_id=_uuid(suffix),
        role=role,
        decision_code=f"qualification_{suffix}",
        revision=1,
        supersedes_decision_id=None,
        research_assessment_id=_uuid(suffix + 10),
        research_qualification_policy_id=_uuid(suffix + 20),
        experiment_id=_uuid(suffix + 30),
        target_definition_id=_uuid(20),
        qualification_purpose=ResearchPurpose.DISCOVERY,
        source_generation_max_decision_time=datetime(
            2026, 8, 27, 6, 55, tzinfo=UTC
        ),
        effective_at=datetime(2026, 8, 27, 7, 0, tzinfo=UTC),
        known_at=datetime(2026, 8, 27, 7, 1, tzinfo=UTC),
        content_sha256="9" * 64,
    )


def _request(
    qualifications: tuple[RequestedResearchQualification, ...],
) -> OpenDecisionRunRequest:
    target = _target_snapshot()
    return OpenDecisionRunRequest(
        candidate_set_id=_candidate_snapshot().candidate_set_id,
        targets=(
            RequestedDecisionTarget(
                target_definition_id=target.target_definition_id,
                reference_provider_product_id=(
                    target.reference_provider_product.provider_product_id
                ),
            ),
        ),
        research_purpose=ResearchPurpose.DISCOVERY,
        research_qualifications=qualifications,
    )


def test_request_freezes_intentional_empty_qualification_roster() -> None:
    request = _request(())

    assert request.validated_research_qualifications() == ()
    assert request.research_qualification_count == 0
    assert len(request.research_qualification_roster_sha256) == 64


def test_non_empty_roster_requires_one_primary_and_unique_exact_decisions() -> None:
    primary = _requested()
    supporting = _requested(802, role=QualificationInputRole.SUPPORTING)

    request = _request((primary, supporting))
    assert request.validated_research_qualifications() == (primary, supporting)
    assert request.research_qualification_count == 2

    with pytest.raises(ValueError, match="duplicate"):
        _request((primary, replace(primary, role=QualificationInputRole.LIMITATION)))
    with pytest.raises(ValueError, match="exactly one PRIMARY"):
        _request((supporting,))
    with pytest.raises(ValueError, match="exactly one PRIMARY"):
        _request((primary, _requested(803)))


def test_request_hash_is_sensitive_to_purpose_order_role_and_exact_identity() -> None:
    baseline = _request(
        (_requested(), _requested(802, role=QualificationInputRole.SUPPORTING))
    )

    assert baseline.request_roster_sha256 != replace(
        baseline,
        research_purpose=ResearchPurpose.VALIDATION,
    ).request_roster_sha256
    assert baseline.request_roster_sha256 != replace(
        baseline,
        research_qualifications=tuple(reversed(baseline.research_qualifications)),
    ).request_roster_sha256
    assert baseline.request_roster_sha256 != replace(
        baseline,
        research_qualifications=(
            baseline.research_qualifications[0],
            replace(
                baseline.research_qualifications[1],
                role=QualificationInputRole.LIMITATION,
            ),
        ),
    ).request_roster_sha256


def test_authority_freezes_exact_qualification_facts_and_generation_order() -> None:
    qualification = _prepared()
    authority = build_decision_authority(
        decision_run_id=_uuid(870),
        command_receipt_id=_uuid(871),
        candidate_set=_candidate_snapshot(),
        targets=(_target_snapshot(),),
        references=_references(),
        runtime=_runtime(),
        research_purpose=ResearchPurpose.DISCOVERY,
        research_qualifications=(qualification,),
        request_identity="open-qualified-decision",
        request_sha256="8" * 64,
        request_received_at=DECISION_TIME,
        commitment_recorded_at=DECISION_TIME,
        actor_type="WORKER",
        actor_id="decision-test",
        reason_code="OPEN_DECISION_RUN",
        qualification_roster_id=_uuid(872),
        qualification_member_id_factory=lambda item, ordinal: _uuid(880 + ordinal),
        commitment_id_factory=lambda candidate, target: _uuid(
            900 + int(str(candidate.candidate_id)[-1])
        ),
        observation_id_factory=lambda commitment_id: _uuid(
            920 + int(str(commitment_id)[-1])
        ),
    )

    assert authority.research_purpose is ResearchPurpose.DISCOVERY
    assert authority.research_qualification_count == 1
    assert authority.research_qualification_roster.roster_id == _uuid(872)
    assert authority.research_qualification_roster.members[0].source is qualification
    assert authority.research_qualification_roster.members[0].ordinal == 1
    assert len(authority.research_qualification_roster_sha256) == 64
    assert len(authority.definition_summary_sha256) == 64

    with pytest.raises(ValueError, match="strictly earlier"):
        build_decision_authority(
            decision_run_id=_uuid(970),
            command_receipt_id=_uuid(971),
            candidate_set=_candidate_snapshot(),
            targets=(_target_snapshot(),),
            references=_references(),
            runtime=_runtime(),
            research_purpose=ResearchPurpose.DISCOVERY,
            research_qualifications=(
                replace(
                    qualification,
                    source_generation_max_decision_time=DECISION_TIME,
                ),
            ),
            request_identity="same-generation-qualified-decision",
            request_sha256="7" * 64,
            request_received_at=DECISION_TIME,
            commitment_recorded_at=DECISION_TIME,
            actor_type="WORKER",
            actor_id="decision-test",
            reason_code="OPEN_DECISION_RUN",
            qualification_roster_id=_uuid(972),
            qualification_member_id_factory=lambda item, ordinal: _uuid(980),
            commitment_id_factory=lambda candidate, target: _uuid(
                990 + int(str(candidate.candidate_id)[-1])
            ),
            observation_id_factory=lambda commitment_id: _uuid(
                995 + int(str(commitment_id)[-1])
            ),
        )
