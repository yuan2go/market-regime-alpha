from __future__ import annotations

from dataclasses import replace

import pytest

from market_regime_alpha.application.decision_system.postgres_repository import (
    DecisionSystemConflict,
    PostgresDecisionSystemRepository,
)
from market_regime_alpha.application.decision_system.research_summary_runtime import (
    ResearchSummaryDelegate,
    ResearchSummaryRuntimeService,
)
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from market_regime_alpha.platform.runtime_governance import RuntimeAuthorityMode
from tests.application.decision_system.support import AS_OF, active_claim
from tests.application.decision_system.test_research_summary import (
    _stages,
    _summary,
)
from tests.application.decision_system.test_runtime import _request
from tests.persistence.postgres.conftest import postgres_factory as postgres_factory
from tests.persistence.postgres.test_continuous_research_journal import MutableClock


def test_research_summary_delegate_rejects_synthetic_state_owner(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    clock = MutableClock(AS_OF)
    _, claim = active_claim(postgres_factory, clock)
    request = replace(
        _request(claim),
        authority_mode=RuntimeAuthorityMode.RESEARCH,
    )
    summary = _summary(
        run_id=claim.run_id,
        tick_id=claim.tick_id,
        trading_date=request.trading_date,
        decision_time=request.as_of_time,
        stages=_stages(available_at=request.as_of_time, missing="THEME_ROTATION"),
    )
    delegate = ResearchSummaryDelegate(
        ResearchSummaryRuntimeService(
            PostgresDecisionSystemRepository(postgres_factory, clock=clock)
        ),
        input_loader=lambda _: summary,
    )

    with pytest.raises(DecisionSystemConflict, match="State owner mismatch"):
        delegate.execute(request)


def test_production_cannot_enter_research_summary_runtime(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    clock = MutableClock(AS_OF)
    _, claim = active_claim(postgres_factory, clock)
    request = _request(claim)
    summary = _summary(
        run_id=claim.run_id,
        tick_id=claim.tick_id,
        trading_date=request.trading_date,
        decision_time=request.as_of_time,
        stages=_stages(available_at=request.as_of_time),
    )
    service = ResearchSummaryRuntimeService(
        PostgresDecisionSystemRepository(postgres_factory, clock=clock)
    )

    with pytest.raises(ValueError, match="Research/Shadow"):
        service.execute(request=request, summary=summary)
