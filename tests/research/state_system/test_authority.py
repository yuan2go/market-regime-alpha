from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

from market_regime_alpha.core.identity import ArtifactId, ModelId
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.research.state_system.authority import (
    StateAuthorityDomain,
    StateSeries,
    engineering_dynamic_pool_policy,
    engineering_state_transition_policy,
)


def _series(*, policy_hash: str | None = None, configuration_hash: str | None = None) -> StateSeries:
    policy = engineering_state_transition_policy(StateAuthorityDomain.MARKET_REGIME)
    return StateSeries.create(
        domain=StateAuthorityDomain.MARKET_REGIME,
        logical_scope="A_SHARE_MARKET",
        research_family="FREE_DATA_STATE_RESEARCH_V2",
        authority_mode="SHADOW",
        universe_policy_id=ArtifactId("universe-policy-v1"),
        universe_policy_hash=canonical_hash({"universe_policy": "v1"}),
        model_id=ModelId("market-model-v1"),
        model_version="1.0.0",
        configuration_id=ArtifactId("market-config-v1"),
        configuration_hash=configuration_hash or canonical_hash({"config": "v1"}),
        state_policy_id=policy.policy_id,
        state_policy_version=policy.policy_version,
        state_policy_hash=policy_hash or policy.policy_hash,
    )


def test_state_series_identity_excludes_runtime_and_calendar_identity() -> None:
    series = _series()

    assert "run_id" not in series.identity_payload()
    assert "tick_id" not in series.identity_payload()
    assert "trading_date" not in series.identity_payload()


def test_policy_or_model_configuration_change_resets_series() -> None:
    original = _series()
    changed_configuration = _series(configuration_hash=canonical_hash({"config": "v2"}))
    policy = engineering_state_transition_policy(StateAuthorityDomain.MARKET_REGIME)
    changed_policy = _series(policy_hash=canonical_hash({"policy": "v2"}))

    assert original.series_id != changed_configuration.series_id
    assert original.series_id != changed_policy.series_id
    assert policy.policy_hash == original.state_policy_hash


def test_engineering_policies_are_explicit_content_addressed_authorities() -> None:
    transition = engineering_state_transition_policy(StateAuthorityDomain.CAPITAL_STATE)
    pool = engineering_dynamic_pool_policy()

    assert transition.policy_hash == canonical_hash(transition.identity_payload())
    assert pool.policy_hash == canonical_hash(pool.identity_payload())
    assert transition.thresholds.minimum_coverage.as_tuple().exponent < 0
    assert transition.parameter("amount_expansion_threshold") == Decimal("0.50")
    assert pool.missing_data_policy.value == "FAIL_CLOSED"
    assert "ENGINEERING_DEFAULT_NOT_ECONOMIC_TRUTH" in transition.limitations
    assert "ENGINEERING_DEFAULT_NOT_ECONOMIC_TRUTH" in pool.limitations


def test_state_series_is_immutable_value() -> None:
    original = _series()
    assert replace(original) == original
