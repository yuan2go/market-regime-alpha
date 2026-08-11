from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from market_regime_alpha.application.research_session.contracts import (
    DataAuthorityMode,
    EvidenceQualification,
    ResearchDecisionSessionRequest,
    ResearchExecutionMode,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash


HASH = canonical_hash({"test": "owner"})
DECISION_TIME = datetime(2026, 8, 10, 6, 55, tzinfo=UTC)


def _request() -> ResearchDecisionSessionRequest:
    return ResearchDecisionSessionRequest.create(
        trading_date=date(2026, 8, 10),
        decision_time=DECISION_TIME,
        materialized_at=DECISION_TIME,
        data_authority_mode=DataAuthorityMode.FREE_RESEARCH_ARCHIVE,
        execution_mode=ResearchExecutionMode.HISTORICAL_RESEARCH,
        evidence_qualification=EvidenceQualification.EXPLORATORY_PIT_INCOMPLETE,
        trading_calendar_id=ArtifactId("calendar-cn-a-2026-v1"),
        trading_calendar_hash=HASH,
        runtime_scope_policy_id=ArtifactId("full-a-liquid-v1"),
        runtime_scope_policy_hash=HASH,
        decision_policy_id=ArtifactId("decision-1455-v1"),
        decision_policy_hash=HASH,
        code_revision="d27bc355",
    )


def test_session_request_has_deterministic_identity_and_round_trip() -> None:
    request = _request()

    assert request == ResearchDecisionSessionRequest.from_canonical_dict(
        request.to_canonical_dict()
    )
    assert request.session_hash == _request().session_hash
    assert str(request.session_id).startswith("research-decision-session-")


def test_free_archive_cannot_claim_formal_pit() -> None:
    with pytest.raises(ValueError, match="free Research data cannot claim Formal PIT"):
        ResearchDecisionSessionRequest.create(
            trading_date=date(2026, 8, 10),
            decision_time=DECISION_TIME,
            materialized_at=DECISION_TIME,
            data_authority_mode=DataAuthorityMode.FREE_RESEARCH_ARCHIVE,
            execution_mode=ResearchExecutionMode.HISTORICAL_RESEARCH,
            evidence_qualification=EvidenceQualification.FORMAL_PIT_QUALIFIED,
            trading_calendar_id=ArtifactId("calendar-cn-a-2026-v1"),
            trading_calendar_hash=HASH,
            runtime_scope_policy_id=ArtifactId("full-a-liquid-v1"),
            runtime_scope_policy_hash=HASH,
            decision_policy_id=ArtifactId("decision-1455-v1"),
            decision_policy_hash=HASH,
            code_revision="d27bc355",
        )


def test_session_request_rejects_naive_or_post_materialized_decision_time() -> None:
    values = _request().semantic_values()

    with pytest.raises(ValueError, match="timezone-aware"):
        ResearchDecisionSessionRequest.create(
            **{**values, "decision_time": DECISION_TIME.replace(tzinfo=None)}
        )
    with pytest.raises(ValueError, match="materialized_at cannot precede"):
        ResearchDecisionSessionRequest.create(
            **{
                **values,
                "materialized_at": datetime(2026, 8, 10, 6, 54, tzinfo=UTC),
            }
        )
