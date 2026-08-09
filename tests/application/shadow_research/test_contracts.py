from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from market_regime_alpha.application.shadow_research.contracts import (
    ShadowSessionCommand,
    ShadowSessionStatus,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.platform.runtime_governance import RuntimeAuthorityMode


NOW = datetime(2026, 8, 10, 6, 30, tzinfo=UTC)


def test_shadow_session_command_is_content_addressed_and_grants_no_trade_authority() -> None:
    command = ShadowSessionCommand.create(
        idempotency_key="shadow-engineering-2026-08-10",
        run_id=ArtifactId("continuous-run-shadow-engineering"),
        trading_date=date(2026, 8, 10),
        runtime_mode=RuntimeAuthorityMode.SHADOW,
        scheduled_at=NOW,
        operator_observation="PRE_LIVE_ENGINEERING_FIXTURE",
    )

    assert str(command.session_id).startswith("shadow-session-")
    assert command.initial_status is ShadowSessionStatus.SCHEDULED
    assert command.no_order and command.no_fill and command.no_broker
    assert command.no_position_mutation
    assert ShadowSessionCommand.from_canonical_dict(
        command.to_canonical_dict()
    ) == command


def test_shadow_session_rejects_research_or_production_runtime() -> None:
    with pytest.raises(ValueError, match="SHADOW Runtime"):
        ShadowSessionCommand.create(
            idempotency_key="not-shadow",
            run_id=ArtifactId("continuous-run-research"),
            trading_date=date(2026, 8, 10),
            runtime_mode=RuntimeAuthorityMode.RESEARCH,
            scheduled_at=NOW,
            operator_observation=None,
        )
