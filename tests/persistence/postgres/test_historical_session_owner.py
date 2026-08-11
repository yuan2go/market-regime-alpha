from __future__ import annotations

from datetime import date

from market_regime_alpha.application.continuous_research.contracts import (
    ContinuousResearchCommand,
)
from market_regime_alpha.application.historical_research.postgres_journal import (
    HistoricalRunStatus,
    PostgresHistoricalResearchJournal,
)
from market_regime_alpha.application.historical_research.postgres_session_owner import (
    PostgresHistoricalSessionOwner,
    _continuous_command_matches,
)
from market_regime_alpha.application.historical_research.runner import (
    HistoricalResearchRunner,
)
from market_regime_alpha.application.research_session.kernel import (
    ResearchDecisionSessionKernel,
    ResearchSessionStage,
    SessionStageStatus,
)
from market_regime_alpha.universe.postgres_runtime_scope import (
    PostgresRuntimeScopeRepository,
)
from tests.application.historical_research.test_contracts import CREATED_AT, _command
from tests.persistence.postgres.test_historical_research_journal import MutableClock
from tests.persistence.postgres.test_runtime_scope import _receipt
from tests.universe.test_runtime_scope import _policy


def _continuous_command_for_historical_session() -> ContinuousResearchCommand:
    historical = _command(sessions=(date(2020, 1, 2),))
    scope = _receipt()
    return ContinuousResearchCommand.create(
        idempotency_key="continuous-2020-01-02-historical-owner",
        trading_date=date(2020, 1, 2),
        requested_symbols=scope.requested_symbols,
        trading_calendar_id=historical.trading_calendar_id,
        trading_calendar_hash=historical.trading_calendar_hash,
        policy_id=historical.decision_policy_id,
        policy_hash=historical.decision_policy_hash,
        provider_configuration_id=historical.configuration_references[0].artifact_id,
        provider_configuration_hash=historical.configuration_references[0].content_hash,
        research_configuration_id=historical.configuration_references[0].artifact_id,
        research_configuration_hash=historical.configuration_references[0].content_hash,
        code_revision=historical.code_revision,
        limitations=(
            "ENTRY_BLOCKED",
            "FORMAL_OOS_ALPHA_NOT_ESTABLISHED",
            "FORMAL_PIT_NOT_ESTABLISHED",
            "NO_BROKER_AUTHORITY",
        ),
    )


def test_historical_decision_owner_requires_exact_continuous_session_binding() -> None:
    historical = _command(sessions=(date(2020, 1, 2),))
    request = historical.session_request(date(2020, 1, 2))
    scope = _receipt()
    command = _continuous_command_for_historical_session()

    assert _continuous_command_matches(command, request, scope) is True
    assert (
        _continuous_command_matches(
            ContinuousResearchCommand.create(
                **{
                    **{
                        "idempotency_key": command.idempotency_key,
                        "trading_date": command.trading_date,
                        "requested_symbols": command.requested_symbols,
                        "trading_calendar_id": command.trading_calendar_id,
                        "trading_calendar_hash": command.trading_calendar_hash,
                        "policy_id": command.policy_id,
                        "policy_hash": command.policy_hash,
                        "provider_configuration_id": command.provider_configuration_id,
                        "provider_configuration_hash": command.provider_configuration_hash,
                        "research_configuration_id": command.research_configuration_id,
                        "research_configuration_hash": command.research_configuration_hash,
                        "limitations": command.limitations,
                    },
                    "code_revision": "different-revision",
                }
            ),
            request,
            scope,
        )
        is False
    )


def test_postgres_session_owner_resolves_scope_then_blocks_missing_decision(
    postgres_factory,
) -> None:
    command = _command(sessions=(date(2020, 1, 2),))
    scope = PostgresRuntimeScopeRepository(postgres_factory).publish(
        policy=_policy(),
        receipt=_receipt(),
    )
    journal = PostgresHistoricalResearchJournal(
        postgres_factory,
        clock=MutableClock(CREATED_AT),
    )
    runner = HistoricalResearchRunner(
        journal=journal,
        kernel=ResearchDecisionSessionKernel(
            PostgresHistoricalSessionOwner(postgres_factory)
        ),
    )

    result = runner.run(command=command)

    assert result.status is HistoricalRunStatus.COMPLETE_WITH_BLOCKS
    receipts = result.sessions[0].receipts
    assert tuple(item.stage for item in receipts) == (
        ResearchSessionStage.SCOPE,
        ResearchSessionStage.DECISION,
    )
    assert receipts[0].status is SessionStageStatus.COMPLETE
    assert receipts[0].output_references[0].artifact_id == scope.scope_id
    assert receipts[1].status is SessionStageStatus.BLOCKED
    assert receipts[1].reason_codes == ("HISTORICAL_DECISION_OWNER_MISSING",)
    assert runner.replay(run_id=command.run_id).matched is True
