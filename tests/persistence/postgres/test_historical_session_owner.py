from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from market_regime_alpha.application.continuous_research.contracts import (
    ContinuousResearchCommand,
)
from market_regime_alpha.application.historical_research.postgres_journal import (
    HistoricalRunStatus,
    PostgresHistoricalResearchJournal,
)
from market_regime_alpha.application.historical_research.postgres_session_owner import (
    HistoricalResearchConflict,
    PostgresHistoricalSessionOwner,
    _continuous_command_matches,
    _required_configuration,
)
from market_regime_alpha.application.historical_research.runner import (
    HistoricalResearchRunner,
)
from market_regime_alpha.application.research_session.kernel import (
    ResearchDecisionSessionKernel,
    ResearchSessionStage,
    SessionStageStatus,
)
from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.core.identity import ArtifactId
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
    assert (
        _continuous_command_matches(
            ContinuousResearchCommand.create(
                idempotency_key=command.idempotency_key,
                trading_date=command.trading_date,
                requested_symbols=command.requested_symbols,
                trading_calendar_id=command.trading_calendar_id,
                trading_calendar_hash=command.trading_calendar_hash,
                policy_id=command.policy_id,
                policy_hash=command.policy_hash,
                provider_configuration_id=command.provider_configuration_id,
                provider_configuration_hash="sha256:" + "0" * 64,
                research_configuration_id=command.research_configuration_id,
                research_configuration_hash=command.research_configuration_hash,
                code_revision=command.code_revision,
                limitations=command.limitations,
            ),
            request,
            scope,
        )
        is False
    )


def test_historical_stages_require_exact_policy_configurations() -> None:
    request = _command(sessions=(date(2020, 1, 2),)).session_request(
        date(2020, 1, 2)
    )

    for artifact_kind in (
        "STRATEGY_SHADOW_POLICY",
        "SHADOW_PORTFOLIO_POLICY",
        "SHADOW_PERFORMANCE_POLICY",
    ):
        with pytest.raises(
            HistoricalResearchConflict,
            match=f"{artifact_kind} exact configuration is required",
        ):
            _required_configuration(request, artifact_kind)


def test_historical_decision_rejects_multiple_exact_owner_matches() -> None:
    request = _command(sessions=(date(2020, 1, 2),)).session_request(
        date(2020, 1, 2)
    )
    scope = _receipt()
    owner = object.__new__(PostgresHistoricalSessionOwner)
    owner._scope = SimpleNamespace(get=lambda _artifact_id: scope)
    owner._continuous = SimpleNamespace(
        get_run=lambda _run_id: SimpleNamespace(
            command=_continuous_command_for_historical_session()
        )
    )
    owner._decisions = SimpleNamespace(
        get_decision=lambda artifact_id: SimpleNamespace(
            decision_id=artifact_id,
            decision_hash="sha256:" + "d" * 64,
            decision_frozen_at=CREATED_AT,
        )
    )
    owner._rows = lambda _query, _parameters: (
        ("decision-1", "run-1"),
        ("decision-2", "run-2"),
    )
    owner._formal_experiment_matches = lambda _request: True

    with pytest.raises(
        HistoricalResearchConflict,
        match="Decision owner is ambiguous for exact session inputs",
    ):
        owner._decision_stage(
            request,
            (
                ValidationArtifactReference(
                    "RUNTIME_SCOPE", scope.scope_id, scope.scope_hash
                ),
            ),
        )


def test_historical_portfolio_requires_one_owner_for_each_exact_strategy() -> None:
    base_request = _command(sessions=(date(2020, 1, 2),)).session_request(
        date(2020, 1, 2)
    )
    strategy_hash = "sha256:" + "a" * 64
    policy = ValidationArtifactReference(
        "SHADOW_PORTFOLIO_POLICY",
        ArtifactId("portfolio-policy-1"),
        "sha256:" + "b" * 64,
    )
    request = type(base_request).create(
        **{
            **base_request.semantic_values(),
            "configuration_references": (
                *base_request.configuration_references,
                policy,
            ),
        }
    )
    strategies = tuple(
        ValidationArtifactReference(
            "STRATEGY_SHADOW_SESSION",
            ArtifactId(artifact_id),
            strategy_hash,
        )
        for artifact_id in ("strategy-1", "strategy-2")
    )
    owner = object.__new__(PostgresHistoricalSessionOwner)
    owner._rows = lambda _query, _parameters: (
        (
            "state-1",
            "portfolio-1",
            "sha256:" + "1" * 64,
            "strategy-1",
            strategy_hash,
            str(policy.artifact_id),
            policy.content_hash,
        ),
        (
            "state-2",
            "portfolio-2",
            "sha256:" + "2" * 64,
            "strategy-1",
            strategy_hash,
            str(policy.artifact_id),
            policy.content_hash,
        ),
    )
    owner._portfolio = SimpleNamespace(
        get_portfolio=lambda portfolio_id: (
            SimpleNamespace(),
            SimpleNamespace(
                portfolio_id=portfolio_id,
                portfolio_hash=(
                    "sha256:" + ("1" if str(portfolio_id) == "portfolio-1" else "2") * 64
                ),
                strategy_reference=strategies[0],
                research_reference=ValidationArtifactReference(
                    "SHADOW_DECISION", "decision-1", "sha256:" + "d" * 64
                ),
                candidate_reference=ValidationArtifactReference(
                    "CANDIDATE_SET", "candidate-1", "sha256:" + "c" * 64
                ),
            ),
        ),
        get_state=lambda state_id: SimpleNamespace(
            state_id=state_id,
            recorded_at=CREATED_AT,
        ),
    )
    owner._portfolio_receipt = lambda **_kwargs: SimpleNamespace(
        source_references=(
            ValidationArtifactReference(
                "SHADOW_DECISION", "decision-1", "sha256:" + "d" * 64
            ),
            ValidationArtifactReference(
                "CANDIDATE_SET", "candidate-1", "sha256:" + "c" * 64
            ),
        )
    )

    with pytest.raises(
        HistoricalResearchConflict,
        match="not unique for exact Strategy and Policy",
    ):
        owner._portfolio_stage(
            request,
            (
                ValidationArtifactReference(
                    "SHADOW_DECISION", "decision-1", "sha256:" + "d" * 64
                ),
                *strategies,
            ),
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
