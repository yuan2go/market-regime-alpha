from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest

from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.application.research_validation.phase_c_gates import (
    PhaseCStageOutcome,
    ProspectiveShadowQualificationPolicy,
)
from market_regime_alpha.application.research_validation.postgres_phase_c_gates import (
    PostgresPhaseCGateAuthority,
)
from market_regime_alpha.application.strategy_shadow.contracts import (
    HoldingRuleKind,
    StrategyShadowPolicy,
)
from market_regime_alpha.application.strategy_shadow.operations import (
    StrategyShadowSession,
)
from market_regime_alpha.application.strategy_shadow.portfolio import (
    PortfolioWeightingMethod,
    ShadowParameterProvenance,
    ShadowPortfolioPolicy,
    build_shadow_portfolio,
)
from market_regime_alpha.application.strategy_shadow.postgres_portfolio import (
    PostgresShadowPortfolioRepository,
)
from market_regime_alpha.application.strategy_shadow.postgres_repository import (
    PostgresStrategyShadowRepository,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from tests.persistence.postgres.test_research_strategy_validation import _runtime


def _reference(kind: str, name: str) -> ValidationArtifactReference:
    return ValidationArtifactReference(
        kind,
        ArtifactId(name),
        canonical_hash({"kind": kind, "name": name}),
    )


def test_prospective_shadow_owner_excludes_forged_unbound_session(
    postgres_factory: PostgresConnectionFactory,
) -> None:
    command, tick, now = _runtime(postgres_factory)
    strategy_policy = StrategyShadowPolicy.create(
        policy_version="phase-c7-strategy-v1",
        rule_kinds=(HoldingRuleKind.FIXED_TIME,),
        fixed_horizon_sessions=2,
        trailing_drawdown=None,
        protection_return=None,
        participation_rate=Decimal("0.10"),
    )
    session = StrategyShadowSession.schedule(
        trading_date=command.trading_date,
        scheduled_for=now,
        research_shadow_reference=_reference(
            "SHADOW_DECISION", "phase-c7-shadow-decision"
        ),
        runtime_run_reference=ValidationArtifactReference(
            "RUNTIME_RUN", command.run_id, command.command_hash
        ),
        runtime_tick_reference=ValidationArtifactReference(
            "RUNTIME_TICK", tick.tick_id, tick.tick_hash
        ),
        policy_reference=ValidationArtifactReference(
            "STRATEGY_SHADOW_POLICY",
            strategy_policy.policy_id,
            strategy_policy.policy_hash,
        ),
        created_at=now,
    )
    strategy = PostgresStrategyShadowRepository(postgres_factory)
    strategy.save_policy(strategy_policy, created_at=now)
    with pytest.raises(ValueError, match="Decision owner identity/time mismatch"):
        strategy.save(session, expected_revision=None)
    portfolio_policy = ShadowPortfolioPolicy.create(
        policy_version="phase-c7-portfolio-v1",
        top_k=1,
        weighting_method=PortfolioWeightingMethod.EQUAL_WEIGHT,
        lot_size=100,
        t_plus_one=True,
        parameters={
            name: (value, ShadowParameterProvenance.ENGINEERING_ASSUMPTION)
            for name, value in (
                ("commission_bps", Decimal("2")),
                ("slippage_bps", Decimal("5")),
                ("impact_bps", Decimal("3")),
                ("exit_cost_bps", Decimal("2")),
                ("max_participation_rate", Decimal("0.10")),
            )
        },
        created_at=now,
    )
    portfolio = build_shadow_portfolio(
        policy=portfolio_policy,
        research_reference=_reference("RESEARCH_PANEL_V2", "phase-c7-panel"),
        candidate_reference=_reference("CANDIDATE_SET", "phase-c7-candidates"),
        initial_cash=Decimal("100000"),
        created_at=now,
    )
    PostgresShadowPortfolioRepository(postgres_factory).save_portfolio(
        policy=portfolio_policy,
        portfolio=portfolio,
    )
    policy = ProspectiveShadowQualificationPolicy.create(
        policy_version="phase-c7-v1",
        strategy_policy_reference=ValidationArtifactReference(
            "STRATEGY_SHADOW_POLICY",
            strategy_policy.policy_id,
            strategy_policy.policy_hash,
        ),
        portfolio_policy_reference=ValidationArtifactReference(
            "SHADOW_PORTFOLIO_POLICY",
            portfolio_policy.policy_id,
            portfolio_policy.policy_hash,
        ),
        minimum_sessions=20,
        minimum_distinct_days=10,
        maximum_incidents=0,
        maximum_drifts=0,
        maximum_provider_failures=0,
        locked_at=now,
    )

    decision = PostgresPhaseCGateAuthority(
        postgres_factory
    ).resolve_prospective_shadow(
        policy=policy,
        actor="phase-c-test",
        reason="resolve real prospective evidence window",
        idempotency_key="phase-c7-accumulating",
    )

    assert decision.outcome is PhaseCStageOutcome.ACCUMULATING
    assert decision.qualification_established is False
    assert decision.reason_codes == (
        "NO_POST_LOCK_PROSPECTIVE_STRATEGY_SHADOW_SESSIONS",
    )

    post_lock_policy = ProspectiveShadowQualificationPolicy.create(
        policy_version="phase-c7-post-lock-v1",
        strategy_policy_reference=policy.strategy_policy_reference,
        portfolio_policy_reference=policy.portfolio_policy_reference,
        minimum_sessions=1,
        minimum_distinct_days=1,
        maximum_incidents=0,
        maximum_drifts=0,
        maximum_provider_failures=0,
        locked_at=now + timedelta(seconds=1),
    )
    post_lock = PostgresPhaseCGateAuthority(
        postgres_factory
    ).resolve_prospective_shadow(
        policy=post_lock_policy,
        actor="phase-c-test",
        reason="exclude sessions created before the frozen policy",
        idempotency_key="phase-c7-post-lock",
    )

    assert post_lock.outcome is PhaseCStageOutcome.ACCUMULATING
    assert post_lock.reason_codes == (
        "NO_POST_LOCK_PROSPECTIVE_STRATEGY_SHADOW_SESSIONS",
    )
