from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from market_regime_alpha.application.research_validation.common import ValidationArtifactReference
from market_regime_alpha.application.research_validation.holding_exit_validation import (
    HoldingExitValidationProtocol,
    evaluate_holding_exit,
)
from market_regime_alpha.application.strategy_shadow.contracts import (
    HoldingRuleKind,
    ShadowExitDecision,
    StrategyShadowPolicy,
    assess_exit,
    assess_holding,
    make_shadow_entry,
    make_shadow_fill,
    make_shadow_position,
    settle_strategy_outcome,
    strategy_shadow_artifact_payload,
)
from market_regime_alpha.application.strategy_shadow.operations import (
    InMemoryStrategyShadowRepository,
    StrategyShadowArtifactKind,
    StrategyShadowArtifactRecord,
    StrategyShadowEventKind,
    StrategyShadowOperations,
    StrategyShadowSession,
    StrategyShadowSessionStatus,
    build_daily_report,
    replay_strategy_shadow,
)
from market_regime_alpha.application.strategy_shadow.operator import (
    StrategyDayObservation,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash


NOW = datetime(2026, 8, 10, 8, tzinfo=UTC)


def _ref(kind: str, name: str) -> ValidationArtifactReference:
    return ValidationArtifactReference(kind, ArtifactId(name), canonical_hash({"name": name}))


def test_strategy_day_accepts_an_initial_holding_observation_for_later_resume() -> None:
    values = {
        "trading_date": "2026-08-10",
        "observed_at": NOW.isoformat(),
        "symbol": "000001.SZ",
        "decision_reference_price": "10",
        "observed_fill_price": "10.01",
        "fillability": "1",
        "sessions_held": 0,
        "current_price": None,
    }

    observation = StrategyDayObservation.from_canonical_dict(values)

    assert observation.sessions_held == 0
    assert observation.current_price is None


def test_shadow_lifecycle_never_creates_real_trading_authority() -> None:
    policy = StrategyShadowPolicy.create(
        policy_version="v1",
        rule_kinds=(HoldingRuleKind.FIXED_TIME, HoldingRuleKind.SIGNAL_REVERSAL, HoldingRuleKind.TRAILING_PROTECTION),
        fixed_horizon_sessions=2,
        trailing_drawdown=Decimal("0.05"),
        protection_return=Decimal("-0.03"),
        participation_rate=Decimal("0.1"),
    )
    entry = make_shadow_entry(
        assessment_reference=_ref("ENTRY_RESEARCH_ASSESSMENT", "entry-assessment"),
        policy=policy,
        symbol="000001.SZ",
        decision_time=NOW,
        intended_quantity=Decimal("1000"),
        intended_reference_price=Decimal("10"),
        source_references=(_ref("RESEARCH_PANEL_V2", "panel"),),
    )
    fill = make_shadow_fill(
        entry=entry,
        observed_price=Decimal("10"),
        fillability=Decimal("0.8"),
        slippage_bps=Decimal("5"),
        impact_bps=Decimal("3"),
        commission_bps=Decimal("2"),
        observed_at=NOW,
        liquidity_reference=_ref("LIQUIDITY_CAPACITY", "liquidity"),
    )
    position = make_shadow_position(entry=entry, fill=fill)
    holding = assess_holding(
        position=position,
        policy=policy,
        assessed_at=NOW,
        sessions_held=2,
        current_price=Decimal("10.5"),
        signal_reversed=False,
        market_deteriorated=False,
        theme_deteriorated=False,
        capital_deteriorated=False,
    )
    exit_assessment = assess_exit(holding=holding, position=position, assessed_at=NOW)
    outcome = settle_strategy_outcome(
        entry=entry,
        fill=fill,
        position=position,
        exit_assessment=exit_assessment,
        exit_cost=Decimal("1"),
        mfe=Decimal("0.07"),
        mae=Decimal("-0.01"),
    )

    assert exit_assessment.decision is ShadowExitDecision.SHADOW_EXIT
    assert outcome.settled is True
    assert "STRATEGY_SHADOW_PROVEN_FALSE" in outcome.limitations
    assert "NOT_REAL_FILL" in fill.limitations
    assert "NOT_REAL_POSITION" in position.limitations
    assert canonical_hash(strategy_shadow_artifact_payload(policy)) == policy.policy_hash
    assert canonical_hash(strategy_shadow_artifact_payload(entry)) == entry.entry_hash
    assert canonical_hash(strategy_shadow_artifact_payload(fill)) == fill.fill_hash
    assert canonical_hash(strategy_shadow_artifact_payload(position)) == position.position_hash
    assert canonical_hash(strategy_shadow_artifact_payload(holding)) == holding.assessment_hash
    assert canonical_hash(strategy_shadow_artifact_payload(exit_assessment)) == exit_assessment.assessment_hash
    assert canonical_hash(strategy_shadow_artifact_payload(outcome)) == outcome.outcome_hash
    validation = evaluate_holding_exit(
        protocol=HoldingExitValidationProtocol.create(
            protocol_version="v1",
            minimum_samples=1,
            minimum_net_return=Decimal("-1"),
            maximum_mean_mae=Decimal("0"),
            required_exit_rule_coverage=(HoldingRuleKind.FIXED_TIME,),
            locked_at=NOW,
        ),
        outcomes=(outcome,),
        formal_oos_reference=None,
        created_at=NOW,
    )
    assert validation.observed_exit_rule_coverage == (HoldingRuleKind.FIXED_TIME,)
    assert validation.holding_exit_validated is False


def test_strategy_shadow_schedule_cas_replay_and_daily_report() -> None:
    session = StrategyShadowSession.schedule(
        trading_date=date(2026, 8, 10),
        scheduled_for=NOW,
        research_shadow_reference=_ref("SHADOW_DECISION", "decision"),
        runtime_run_reference=_ref("RUNTIME_RUN", "run"),
        runtime_tick_reference=_ref("RUNTIME_TICK", "tick"),
        policy_reference=_ref("STRATEGY_SHADOW_POLICY", "policy"),
        created_at=NOW,
    )
    repository = InMemoryStrategyShadowRepository()
    repository.save(session, expected_revision=None)
    running = session.append(event_kind=StrategyShadowEventKind.STARTED, occurred_at=NOW, status=StrategyShadowSessionStatus.RUNNING)
    repository.save(running, expected_revision=1)
    recovered = running.append(event_kind=StrategyShadowEventKind.RECOVERED, occurred_at=NOW, details=(("reason", "PROCESS_RESTART"),))
    repository.save(recovered, expected_revision=2)
    report = build_daily_report(trading_date=date(2026, 8, 10), sessions=(recovered,), generated_at=NOW)

    assert replay_strategy_shadow(repository.get(session.session_id)) == recovered
    assert report.sustained_prospective_proof is False
    assert "NOT_SUSTAINED_PROSPECTIVE_EVIDENCE" in report.limitations


def test_strategy_shadow_operations_enforce_state_and_persist_artifact() -> None:
    repository = InMemoryStrategyShadowRepository()
    operations = StrategyShadowOperations(repository)
    scheduled = operations.schedule(
        trading_date=date(2026, 8, 10),
        scheduled_for=NOW,
        research_shadow_reference=_ref("SHADOW_DECISION", "decision-ops"),
        runtime_run_reference=_ref("RUNTIME_RUN", "run-ops"),
        runtime_tick_reference=_ref("RUNTIME_TICK", "tick-ops"),
        policy_reference=_ref("STRATEGY_SHADOW_POLICY", "policy-ops"),
        created_at=NOW,
    )
    running = operations.start(scheduled.session_id, expected_revision=1, occurred_at=NOW)
    payload = {"entry": "shadow-only"}
    reference = ValidationArtifactReference("SHADOW_ENTRY", ArtifactId("entry-ops"), canonical_hash(payload))
    recorded = operations.record_artifact(
        scheduled.session_id,
        expected_revision=2,
        event_kind=StrategyShadowEventKind.ENTRY_CREATED,
        artifact=StrategyShadowArtifactRecord(
            reference,
            StrategyShadowArtifactKind.ENTRY,
            scheduled.session_id,
            payload,
            NOW,
        ),
        occurred_at=NOW,
    )

    assert running.status is StrategyShadowSessionStatus.RUNNING
    assert operations.replay(scheduled.session_id) == recorded
    with pytest.raises(ValueError, match="invalid Strategy Shadow transition"):
        scheduled.append(event_kind=StrategyShadowEventKind.ENTRY_CREATED, occurred_at=NOW)
    with pytest.raises(ValueError, match="missing prerequisite ENTRY_CREATED"):
        running.append(event_kind=StrategyShadowEventKind.FILL_OBSERVED, occurred_at=NOW)
    with pytest.raises(ValueError, match="requires FILL Artifact"):
        operations.record_artifact(
            scheduled.session_id,
            expected_revision=recorded.revision,
            event_kind=StrategyShadowEventKind.FILL_OBSERVED,
            artifact=StrategyShadowArtifactRecord(
                _ref("SHADOW_ENTRY", "wrong-fill-kind"),
                StrategyShadowArtifactKind.ENTRY,
                scheduled.session_id,
                {"name": "wrong-fill-kind"},
                NOW,
            ),
            occurred_at=NOW,
        )
