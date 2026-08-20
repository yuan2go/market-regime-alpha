from __future__ import annotations

from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import Mock

from market_regime_alpha.application.continuous_research.journal import (
    RuntimeArtifactReference,
)
from market_regime_alpha.application.historical_corpus.golden_loop import (
    GoldenLoopScoringContract,
    GoldenLoopSessionEvaluation,
)
from market_regime_alpha.application.historical_corpus.materialization_contracts import (
    HistoricalComponentKind,
    HistoricalSessionComponent,
)
from market_regime_alpha.application.historical_research.multi_strategy import (
    MultiStrategyHistoricalAdapter,
)
from market_regime_alpha.application.research_session.contracts import (
    DataAuthorityMode,
    EvidenceQualification,
    ResearchDecisionSessionRequest,
    ResearchExecutionMode,
)
from market_regime_alpha.application.research_session.kernel import (
    ResearchSessionStage,
    SessionStageComputation,
    SessionStageStatus,
)
from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.core.identity import ArtifactId


AT = datetime(2026, 8, 20, 7, 0, tzinfo=UTC)


def test_performance_stage_persists_owner_resolved_v2_evaluation() -> None:
    panel, outcome = _components()
    cycle_reference = _reference("MULTI_STRATEGY_CYCLE", "cycle")
    portfolio_reference = _reference("CROSS_STRATEGY_PORTFOLIO", "portfolio")
    request = _request(v2=True)
    delegated = _delegated(panel.reference)
    delegate = Mock()
    delegate.compute_stage.return_value = delegated
    components = Mock()
    components.get.side_effect = lambda reference: {
        panel.reference: panel,
        outcome.reference: outcome,
    }[reference]
    components.put.side_effect = lambda *, component, ordinal: component
    strategies = Mock()
    strategies.get_cycle.return_value = SimpleNamespace(
        cycle_id=cycle_reference.artifact_id,
        cycle_hash=cycle_reference.content_hash,
        runs=(),
    )
    strategies.get_portfolio.return_value = SimpleNamespace(
        decision_id=portfolio_reference.artifact_id,
        decision_hash=portfolio_reference.content_hash,
        cycle_reference=RuntimeArtifactReference(
            cycle_reference.artifact_kind,
            cycle_reference.artifact_id,
            cycle_reference.content_hash,
        ),
        status=SimpleNamespace(value="NO_ACTION"),
        lines=(),
    )
    adapter = MultiStrategyHistoricalAdapter(
        delegate=delegate,
        component_repository=components,
        strategy_repository=strategies,
        parent_run_reference=RuntimeArtifactReference(
            "HISTORICAL_RESEARCH_RUN",
            panel.run_id,
            _hash("parent"),
        ),
        portfolio_policy=Mock(),
    )

    result = adapter.compute_stage(
        request=request,
        stage=ResearchSessionStage.PERFORMANCE,
        input_references=tuple(
            sorted(
                (
                    panel.reference,
                    outcome.reference,
                    cycle_reference,
                    portfolio_reference,
                ),
                key=lambda item: (
                    item.artifact_kind,
                    str(item.artifact_id),
                    item.content_hash,
                ),
            )
        ),
    )

    stored = components.put.call_args.kwargs["component"]
    evaluation = GoldenLoopSessionEvaluation.from_canonical_dict(stored.payload)
    assert stored.component_kind is HistoricalComponentKind.RESEARCH_EVALUATION
    assert evaluation.portfolio_status == "NO_ACTION"
    assert evaluation.portfolio_line_count == 0
    assert {item.artifact_kind for item in stored.source_references} >= {
        "MULTI_STRATEGY_CYCLE",
        "CROSS_STRATEGY_PORTFOLIO",
        "HISTORICAL_OUTCOME",
    }
    assert result.output_references == tuple(
        sorted(
            (panel.reference, stored.reference),
            key=lambda item: (
                item.artifact_kind,
                str(item.artifact_id),
                item.content_hash,
            ),
        )
    )


def test_v1_performance_stage_is_replay_stable_and_not_rewritten() -> None:
    panel, _outcome = _components()
    delegated = _delegated(panel.reference)
    delegate = Mock()
    delegate.compute_stage.return_value = delegated
    components = Mock()
    adapter = MultiStrategyHistoricalAdapter(
        delegate=delegate,
        component_repository=components,
        strategy_repository=Mock(),
        parent_run_reference=RuntimeArtifactReference(
            "HISTORICAL_RESEARCH_RUN",
            panel.run_id,
            _hash("parent"),
        ),
        portfolio_policy=Mock(),
    )

    result = adapter.compute_stage(
        request=_request(v2=False),
        stage=ResearchSessionStage.PERFORMANCE,
        input_references=(panel.reference,),
    )

    assert result is delegated
    components.put.assert_not_called()


def _components() -> tuple[HistoricalSessionComponent, HistoricalSessionComponent]:
    source = (_reference("TEST_OWNER", "source"),)
    common = {
        "run_id": ArtifactId("historical-run-golden-loop-adapter"),
        "session_id": ArtifactId("historical-session-golden-loop-adapter"),
        "trading_date": date(2026, 8, 19),
        "source_max_event_time": AT,
        "materialized_at": AT,
        "source_references": source,
    }
    panel = HistoricalSessionComponent.create(
        **common,
        component_kind=HistoricalComponentKind.RESEARCH_PANEL,
        payload={
            "rows": [
                {
                    "symbol": f"SYMBOL-{index:02d}",
                    "target_return": str(index / 1000),
                    "factor_values": {"price": str(index)},
                }
                for index in range(12)
            ]
        },
    )
    outcome = HistoricalSessionComponent.create(
        **common,
        component_kind=HistoricalComponentKind.OUTCOME,
        payload={"status": "SETTLED"},
    )
    return panel, outcome


def _request(*, v2: bool) -> ResearchDecisionSessionRequest:
    configurations = (
        (
            GoldenLoopScoringContract.create_v2().reference,
            _reference("HISTORICAL_STRATEGY_ECONOMICS_POLICY_SET", "cost"),
        )
        if v2
        else (_reference("TEST_CONFIGURATION", "v1"),)
    )
    return ResearchDecisionSessionRequest.create(
        trading_date=date(2026, 8, 19),
        decision_time=AT,
        materialized_at=AT,
        data_authority_mode=DataAuthorityMode.FREE_RESEARCH_ARCHIVE,
        execution_mode=ResearchExecutionMode.HISTORICAL_RESEARCH,
        evidence_qualification=EvidenceQualification.EXPLORATORY_PIT_INCOMPLETE,
        trading_calendar_id=ArtifactId("calendar"),
        trading_calendar_hash=_hash("calendar"),
        runtime_scope_policy_id=ArtifactId("scope"),
        runtime_scope_policy_hash=_hash("scope"),
        decision_policy_id=ArtifactId("decision"),
        decision_policy_hash=_hash("decision"),
        target_protocol_reference=_reference("OUTCOME_TARGET_PROTOCOL", "target"),
        experiment_definition_reference=_reference(
            "RESEARCH_EXPERIMENT_DEFINITION",
            "experiment",
        ),
        code_revision="test-revision",
        configuration_references=configurations,
    )


def _delegated(reference: ValidationArtifactReference) -> SessionStageComputation:
    return SessionStageComputation(
        status=SessionStageStatus.COMPLETE,
        output_references=(reference,),
        input_references=(),
        completed_at=AT,
        reason_codes=("HISTORICAL_RESEARCH_PANEL_MATERIALIZED",),
    )


def _reference(kind: str, identity: str) -> ValidationArtifactReference:
    return ValidationArtifactReference(
        kind,
        ArtifactId(f"{kind.lower()}-{identity}"),
        _hash(identity),
    )


def _hash(identity: str) -> str:
    return f"sha256:{identity.encode().hex().ljust(64, '0')[:64]}"
