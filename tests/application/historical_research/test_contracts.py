from __future__ import annotations

from datetime import UTC, date, datetime, time

import pytest

from market_regime_alpha.application.historical_research.contracts import (
    HistoricalResearchCommand,
)
from market_regime_alpha.application.research_session.contracts import (
    DataAuthorityMode,
    EvidenceQualification,
)
from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash
from tests.universe.test_runtime_scope import _policy


HASH = canonical_hash({"historical": "owner"})
CREATED_AT = datetime(2026, 8, 11, 3, 0, tzinfo=UTC)


def _command(*, sessions: tuple[date, ...] | None = None) -> HistoricalResearchCommand:
    scope_policy = _policy()
    return HistoricalResearchCommand.create(
        idempotency_key="historical-2020-q1-v1",
        start_date=date(2020, 1, 2),
        end_date=date(2020, 1, 6),
        trading_sessions=sessions
        or (date(2020, 1, 2), date(2020, 1, 3), date(2020, 1, 6)),
        decision_local_time=time(14, 55),
        timezone_name="Asia/Shanghai",
        trading_calendar_id=ArtifactId("calendar-cn-a-2020-frozen-v1"),
        trading_calendar_hash=HASH,
        runtime_scope_policy_id=scope_policy.policy_id,
        runtime_scope_policy_hash=scope_policy.policy_hash,
        decision_policy_id=ArtifactId("decision-1455-v1"),
        decision_policy_hash=HASH,
        target_protocol_reference=ValidationArtifactReference(
            "OUTCOME_TARGET_PROTOCOL", ArtifactId("target-protocol-v2"), HASH
        ),
        experiment_definition_reference=ValidationArtifactReference(
            "RESEARCH_EXPERIMENT_DEFINITION", ArtifactId("experiment-v1"), HASH
        ),
        configuration_references=(
            ValidationArtifactReference(
                "RESEARCH_CONFIGURATION",
                ArtifactId("historical-config-v1"),
                HASH,
            ),
        ),
        data_authority_mode=DataAuthorityMode.FREE_RESEARCH_ARCHIVE,
        evidence_qualification=EvidenceQualification.EXPLORATORY_PIT_INCOMPLETE,
        code_revision="d27bc355",
        created_at=CREATED_AT,
    )


def test_historical_command_freezes_calendar_and_builds_session_requests() -> None:
    command = _command()

    assert command == HistoricalResearchCommand.from_canonical_dict(
        command.to_canonical_dict()
    )
    assert command.session_count == 3
    request = command.session_request(date(2020, 1, 3))
    assert request.decision_time.isoformat() == "2020-01-03T06:55:00+00:00"
    assert request.materialized_at == CREATED_AT
    assert request.data_authority_mode is DataAuthorityMode.FREE_RESEARCH_ARCHIVE


def test_historical_command_rejects_calendar_gaps_or_unsorted_sessions() -> None:
    with pytest.raises(ValueError, match="sorted and unique"):
        _command(sessions=(date(2020, 1, 3), date(2020, 1, 2)))
    with pytest.raises(ValueError, match="outside the requested period"):
        _command(sessions=(date(2019, 12, 31), date(2020, 1, 2)))


def test_historical_command_rejects_free_data_formal_qualification() -> None:
    values = _command().semantic_values()

    with pytest.raises(ValueError, match="free Research data cannot claim Formal PIT"):
        HistoricalResearchCommand.create(
            **{
                **values,
                "evidence_qualification": EvidenceQualification.FORMAL_PIT_QUALIFIED,
            }
        )
