from __future__ import annotations

from market_regime_alpha.portfolio.risk_routes import (
    RISK_REDUCING_GATE_CONFIG_SCHEMA,
    RiskReducingGateConfiguration,
)


def test_gate_configuration_identifies_observation_freshness() -> None:
    configuration = RiskReducingGateConfiguration.create(
        profile_id="test_risk_reducing_gate_v2",
        maximum_position_age_seconds=60.0,
        maximum_observation_age_seconds=30.0,
        maximum_liquidity_participation=0.1,
    )

    assert RISK_REDUCING_GATE_CONFIG_SCHEMA == (
        "risk-reducing-gate-configuration-v2"
    )
    assert configuration.maximum_observation_age_seconds == 30.0
    assert (
        RiskReducingGateConfiguration.from_canonical_dict(
            configuration.to_canonical_dict()
        )
        == configuration
    )
