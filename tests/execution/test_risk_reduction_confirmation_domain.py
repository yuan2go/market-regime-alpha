from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from market_regime_alpha.core.identity import (
    ArtifactId,
    ExitAssessmentId,
    ManualTradeId,
    OpportunityId,
    PositionBookId,
    PositionSnapshotId,
    ThesisId,
)
from market_regime_alpha.execution.risk_reduction import (
    OPERATOR_AUTHENTICATION_NOT_ESTABLISHED,
    TRADING_AUTHORITY_NOT_GRANTED,
    OperationalExitDirectiveV2,
    OperatorAuthenticationRequirement,
    RequiredExitAuthorityRoute,
    RiskReductionConfirmationAttempt,
    RiskReductionConfirmationPolicy,
    RiskReductionConfirmationState,
)
from market_regime_alpha.position.assessment import PositionLifecycleAction


NOW = datetime(2026, 8, 4, 14, 30, tzinfo=ZoneInfo("Asia/Shanghai"))


def _sha(character: str) -> str:
    return "sha256:" + character * 64


def _directive() -> OperationalExitDirectiveV2:
    return OperationalExitDirectiveV2.create(
        exit_assessment_id=ExitAssessmentId("exit-assessment-a"),
        exit_assessment_hash=_sha("a"),
        action=PositionLifecycleAction.REDUCE,
        thesis_id=ThesisId("thesis-a"),
        thesis_version=4,
        opportunity_id=OpportunityId("opportunity-a"),
        position_book_id=PositionBookId("book-a"),
        symbol="000001.SZ",
        position_snapshot_id=PositionSnapshotId("position-a"),
        position_snapshot_hash=_sha("b"),
        position_snapshot_version=3,
        thesis_health_observation_id=ArtifactId("health-a"),
        thesis_health_observation_hash=_sha("c"),
        composite_manifest_id=ArtifactId("composite-a"),
        composite_manifest_hash=_sha("d"),
        created_at=NOW,
        reason_codes=("REDUCE_REQUIRED",),
    )


def _policy() -> RiskReductionConfirmationPolicy:
    return RiskReductionConfirmationPolicy.create(
        profile_id="manual-risk-reduction-v1",
        builder_revision="h4.5-v1",
        maximum_decision_age_seconds=300,
        maximum_position_age_seconds=60,
        maximum_execution_observation_age_seconds=15,
        maximum_reference_price_deviation=0.02,
        operator_authentication_requirement=(
            OperatorAuthenticationRequirement.RECORDED_ACTOR_ONLY
        ),
    )


def _attempt() -> RiskReductionConfirmationAttempt:
    directive = _directive()
    policy = _policy()
    return RiskReductionConfirmationAttempt.create(
        state=RiskReductionConfirmationState.CONFIRMED_INTENT,
        risk_reducing_decision_id=ArtifactId("reducing-a"),
        risk_reducing_decision_hash=_sha("e"),
        exit_directive_id=directive.directive_id,
        exit_directive_hash=directive.content_hash,
        source_position_snapshot_id=PositionSnapshotId("position-a"),
        source_position_snapshot_hash=_sha("b"),
        current_position_snapshot_id=PositionSnapshotId("position-a"),
        current_position_snapshot_hash=_sha("b"),
        thesis_health_observation_id=ArtifactId("health-a"),
        thesis_health_observation_hash=_sha("c"),
        composite_manifest_id=ArtifactId("composite-a"),
        composite_manifest_hash=_sha("d"),
        recheck_observation_id=ArtifactId("execution-a"),
        recheck_observation_hash=_sha("f"),
        configuration_id=ArtifactId("configuration-a"),
        configuration_hash=_sha("1"),
        confirmation_policy_id=policy.policy_id,
        confirmation_policy_hash=policy.policy_hash,
        manual_trade_id=ManualTradeId("manual-trade-a"),
        actor="operator-a",
        reason="confirmed after current evidence recheck",
        confirmed_at=NOW,
        reason_codes=("MANUAL_INTENT_CREATED",),
    )


def test_operational_exit_directive_v2_is_content_addressed_and_round_trips() -> None:
    directive = _directive()

    restored = OperationalExitDirectiveV2.from_canonical_dict(
        directive.to_canonical_dict()
    )

    assert restored == directive
    assert (
        restored.required_authority_route
        is RequiredExitAuthorityRoute.REDUCING_RISK_DECISION
    )
    assert restored.trading_authority == TRADING_AUTHORITY_NOT_GRANTED


@pytest.mark.parametrize(
    "action",
    [
        PositionLifecycleAction.WAIT,
        PositionLifecycleAction.HOLD,
        PositionLifecycleAction.ADD,
        PositionLifecycleAction.DATA_INSUFFICIENT,
    ],
)
def test_operational_exit_directive_v2_rejects_non_actionable_actions(
    action: PositionLifecycleAction,
) -> None:
    with pytest.raises(ValueError, match="REDUCE or EXIT"):
        replace(_directive(), action=action)


def test_operational_exit_directive_v2_rejects_identity_tamper() -> None:
    with pytest.raises(ValueError, match="identity mismatch"):
        replace(_directive(), content_hash=_sha("9"))


def test_confirmation_policy_is_explicit_content_addressed_and_limited() -> None:
    policy = _policy()

    restored = RiskReductionConfirmationPolicy.from_canonical_dict(
        policy.to_canonical_dict()
    )

    assert restored == policy
    assert (
        restored.operator_authentication_limitation
        == OPERATOR_AUTHENTICATION_NOT_ESTABLISHED
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("maximum_decision_age_seconds", 0),
        ("maximum_position_age_seconds", -1),
        ("maximum_execution_observation_age_seconds", 0),
        ("maximum_reference_price_deviation", -0.01),
    ],
)
def test_confirmation_policy_rejects_invalid_thresholds(
    field: str, value: float
) -> None:
    with pytest.raises(ValueError, match="policy thresholds"):
        replace(_policy(), **{field: value})


def test_confirmation_attempt_is_content_addressed_and_round_trips() -> None:
    attempt = _attempt()

    restored = RiskReductionConfirmationAttempt.from_canonical_dict(
        attempt.to_canonical_dict()
    )

    assert restored == attempt
    assert restored.state is RiskReductionConfirmationState.CONFIRMED_INTENT


def test_failed_confirmation_attempt_cannot_bind_manual_trade() -> None:
    with pytest.raises(ValueError, match="failed attempt cannot bind"):
        replace(_attempt(), state=RiskReductionConfirmationState.POSITION_CHANGED)


def test_confirmed_attempt_requires_manual_trade() -> None:
    with pytest.raises(ValueError, match="confirmed attempt requires"):
        replace(_attempt(), manual_trade_id=None)


def test_confirmation_attempt_rejects_identity_tamper() -> None:
    with pytest.raises(ValueError, match="identity mismatch"):
        replace(_attempt(), content_hash=_sha("8"))
