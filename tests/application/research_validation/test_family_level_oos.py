from __future__ import annotations

from market_regime_alpha.application.research_validation.formal_execution import (
    FormalExecutionStage,
    FormalExecutionStatus,
    assess_formal_execution,
)
from market_regime_alpha.data.postgres_provider_qualification import (
    ProviderFactQualificationStatus,
)
from tests.application.research_validation.test_formal_execution import (
    _Resolver,
    _provider_decision,
    _request,
)


def test_formal_oos_is_not_reached_without_a_frozen_protocol() -> None:
    provider = _provider_decision(ProviderFactQualificationStatus.QUALIFIED)
    resolver = _Resolver(provider)

    assessment = assess_formal_execution(
        _request(provider.decision_id),
        resolver=resolver,
    )

    assert assessment.status is FormalExecutionStatus.BLOCKED
    assert assessment.terminal_stage is FormalExecutionStage.FORMAL_PROTOCOL
    assert assessment.formal_oos_alpha_established is False
    assert resolver.calls == ["provider"]
