from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.application.research_validation.phase_c_gates import (
    EntryHoldingExitQualificationPolicy,
    PhaseCStage,
    PhaseCStageDecision,
    PhaseCStageOutcome,
    ProspectiveShadowQualificationPolicy,
)
from market_regime_alpha.application.strategy_shadow.contracts import HoldingRuleKind
from market_regime_alpha.application.strategy_shadow.portfolio import (
    ShadowParameterProvenance,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash


NOW = datetime(2026, 8, 11, 8, tzinfo=UTC)


def _reference(kind: str, name: str) -> ValidationArtifactReference:
    return ValidationArtifactReference(
        kind,
        ArtifactId(name),
        canonical_hash({"kind": kind, "name": name}),
    )


def test_prospective_policy_excludes_replay_and_stage_decision_is_fail_closed() -> None:
    policy = ProspectiveShadowQualificationPolicy.create(
        policy_version="phase-c7-v1",
        strategy_policy_reference=_reference(
            "STRATEGY_SHADOW_POLICY", "strategy-policy"
        ),
        portfolio_policy_reference=_reference(
            "SHADOW_PORTFOLIO_POLICY", "portfolio-policy"
        ),
        minimum_sessions=20,
        minimum_distinct_days=10,
        maximum_incidents=0,
        maximum_drifts=0,
        maximum_provider_failures=0,
        locked_at=NOW,
    )
    decision = PhaseCStageDecision.create(
        stage=PhaseCStage.PROSPECTIVE_STRATEGY_SHADOW,
        scope_id=str(policy.policy_id),
        policy_reference=_reference(
            "PROSPECTIVE_SHADOW_QUALIFICATION_POLICY", "prospective-policy"
        ),
        evidence_references=(),
        outcome=PhaseCStageOutcome.ACCUMULATING,
        qualification_established=False,
        revision=1,
        supersedes_decision_id=None,
        evaluated_at=NOW,
        actor="phase-c-test",
        reason="resolve current prospective evidence",
        reason_codes=("NO_PROSPECTIVE_STRATEGY_SHADOW_SESSIONS",),
    )

    assert policy.identity_payload()["required_clock_mode"] == "LIVE_TRUSTED"
    assert policy.identity_payload()["required_runtime_origin"] == "LIVE_ACQUISITION"
    assert policy.identity_payload()["replay_or_fixture_counts_as_prospective"] is False
    assert decision.qualification_established is False

    invalid_policy = policy.to_canonical_dict()
    invalid_policy["schema_version"] = "prospective-shadow-policy/forged"
    with pytest.raises(ValueError, match="unsupported Prospective Shadow Policy"):
        ProspectiveShadowQualificationPolicy.from_canonical_dict(invalid_policy)


def test_entry_holding_exit_policy_freezes_economic_and_provenance_floors() -> None:
    values = {
        "policy_version": "phase-c6-v1",
        "entry_model_reference": _reference(
            "ENTRY_RESEARCH_MODEL", "entry-model"
        ),
        "strategy_policy_reference": _reference(
            "STRATEGY_SHADOW_POLICY", "strategy-policy"
        ),
        "portfolio_policy_reference": _reference(
            "SHADOW_PORTFOLIO_POLICY", "portfolio-policy"
        ),
        "minimum_samples": 100,
        "minimum_hit_rate": Decimal("0.55"),
        "minimum_cost_adjusted_return": Decimal("0.001"),
        "maximum_mean_mae": Decimal("-0.05"),
        "required_exit_rule_coverage": (HoldingRuleKind.FIXED_TIME,),
        "allowed_result_provenance": (
            ShadowParameterProvenance.CALIBRATED_PARAMETER,
            ShadowParameterProvenance.OBSERVED_FACT,
        ),
        "locked_at": NOW,
    }
    policy = EntryHoldingExitQualificationPolicy.create(**values)
    stricter = EntryHoldingExitQualificationPolicy.create(
        **{**values, "minimum_samples": 101}
    )

    assert policy.policy_hash != stricter.policy_hash
    assert policy.identity_payload()["required_independent_governance_approval"] is True
    assert policy.identity_payload()["canonical_entry_unlock_automatic"] is False

    invalid_policy = policy.to_canonical_dict()
    invalid_policy["schema_version"] = "entry-holding-exit-policy/forged"
    with pytest.raises(ValueError, match="unsupported Entry/Holding/Exit"):
        EntryHoldingExitQualificationPolicy.from_canonical_dict(invalid_policy)
