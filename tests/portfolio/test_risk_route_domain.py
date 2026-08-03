from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.portfolio.risk_routes import (
    RISK_REDUCING_GATE_CONFIG_SCHEMA,
    ExecutionConstraintState,
    ReducingExecutionObservation,
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


def test_numeric_inputs_are_canonicalized_before_identity_is_computed() -> None:
    configuration = RiskReducingGateConfiguration.create(
        profile_id="integer-valued-risk-reducing-gate",
        maximum_position_age_seconds=60,
        maximum_observation_age_seconds=30,
        maximum_liquidity_participation=1,
    )
    observation = ReducingExecutionObservation.create(
        symbol="000001.SZ",
        session_date=date(2026, 7, 20),
        state=ExecutionConstraintState.EXECUTABLE,
        reference_price=10,
        average_daily_volume=10_000,
        source_artifact_id=ArtifactId("integer-observation-source"),
        source_artifact_hash="sha256:" + "a" * 64,
        availability_time=datetime(
            2026, 7, 20, 14, 54, tzinfo=ZoneInfo("Asia/Shanghai")
        ),
        reason_code="INTEGER_NUMERIC_FIXTURE",
    )

    assert type(configuration.maximum_position_age_seconds) is float
    assert type(configuration.maximum_observation_age_seconds) is float
    assert type(configuration.maximum_liquidity_participation) is float
    assert type(observation.reference_price) is float
    assert (
        RiskReducingGateConfiguration.from_canonical_dict(
            configuration.to_canonical_dict()
        )
        == configuration
    )
    assert (
        ReducingExecutionObservation.from_canonical_dict(
            observation.to_canonical_dict()
        )
        == observation
    )
