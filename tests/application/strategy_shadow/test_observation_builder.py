from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.application.strategy_shadow.observation_builder import (
    ObservationBuildStatus,
    ObservationKind,
    OwnerObservationValue,
    ShadowObservationPolicy,
    build_observation_receipt,
    build_portfolio_observation_receipt,
)
from market_regime_alpha.application.strategy_shadow.portfolio import (
    ShadowParameterProvenance,
    ShadowPortfolioTradeSession,
)
from market_regime_alpha.application.research_evaluation.targets import (
    OutcomeCheckpoint,
)
from market_regime_alpha.core.identity import ArtifactId


NOW = datetime(2026, 8, 11, 7, tzinfo=UTC)


def _reference(kind: str, suffix: str) -> ValidationArtifactReference:
    return ValidationArtifactReference(
        kind,
        ArtifactId(f"{kind.lower()}:{suffix}"),
        "sha256:" + suffix[0] * 64,
    )


def _policy() -> ShadowObservationPolicy:
    return ShadowObservationPolicy.create(
        policy_version="free-data-auto-observation-v1",
        intended_quantity=Decimal("100"),
        fill_checkpoint=OutcomeCheckpoint.OPEN,
        mark_checkpoint=OutcomeCheckpoint.TIME_1030,
        trade_session=ShadowPortfolioTradeSession.CONTINUOUS_AM,
        fillability=Decimal("1"),
        slippage_bps=Decimal("5"),
        impact_bps=Decimal("3"),
        commission_bps=Decimal("2"),
        exit_cost_bps=Decimal("2"),
        created_at=NOW - timedelta(days=1),
    )


def _value(
    name: str,
    value: str | int | bool | None,
    *,
    provenance: ShadowParameterProvenance = ShadowParameterProvenance.OBSERVED_FACT,
    available_at: datetime = NOW,
) -> OwnerObservationValue:
    return OwnerObservationValue(
        name=name,
        value=value,
        provenance=provenance,
        source_reference=_reference("OWNER_FACT", "a"),
        effective_at=NOW - timedelta(minutes=1),
        available_at=available_at,
        source_value_path=f"facts.{name}",
    )


def _strategy_values() -> tuple[OwnerObservationValue, ...]:
    observed = {
        "decision_reference_price": "10",
        "observed_fill_price": "10.01",
        "sessions_held": 1,
        "current_price": "10.20",
        "mfe": "0.03",
        "mae": "-0.01",
    }
    assumptions: dict[str, str | int | bool] = {
        "intended_quantity": "100",
        "fillability": "1",
        "slippage_bps": "5",
        "impact_bps": "3",
        "commission_bps": "2",
        "signal_reversed": False,
        "market_deteriorated": False,
        "theme_deteriorated": False,
        "capital_deteriorated": False,
        "exit_cost": "0.204",
    }
    return tuple(
        sorted(
            (
                *(_value(name, value) for name, value in observed.items()),
                *(
                    _value(
                        name,
                        value,
                        provenance=ShadowParameterProvenance.ENGINEERING_ASSUMPTION,
                    )
                    for name, value in assumptions.items()
                ),
            ),
            key=lambda item: item.name,
        )
    )


def test_strategy_observation_receipt_is_deterministic_and_provenance_complete() -> None:
    policy = _policy()
    values = _strategy_values()

    first = build_observation_receipt(
        kind=ObservationKind.STRATEGY,
        research_trading_date=date(2026, 8, 10),
        trading_date=date(2026, 8, 11),
        observed_at=NOW,
        symbol="000001.SZ",
        policy=policy,
        values=values,
        source_references=(_reference("TARGETED_OUTCOME", "b"),),
    )
    second = build_observation_receipt(
        kind=ObservationKind.STRATEGY,
        research_trading_date=date(2026, 8, 10),
        trading_date=date(2026, 8, 11),
        observed_at=NOW,
        symbol="000001.SZ",
        policy=policy,
        values=values,
        source_references=(_reference("TARGETED_OUTCOME", "b"),),
    )

    assert first == second
    assert first.status is ObservationBuildStatus.READY
    assert first.observation_payload is not None
    assert first.observation_payload["value_provenance"]["current_price"] == (
        "OBSERVED_FACT"
    )
    assert first.observation_payload["value_provenance"]["exit_cost"] == (
        "ENGINEERING_ASSUMPTION"
    )
    assert first.formal_pit is False
    assert first.formal_oos is False
    assert first.calibrated is False


def test_missing_or_future_owner_fact_is_not_estimable_not_defaulted() -> None:
    policy = _policy()
    missing_price = tuple(
        item for item in _strategy_values() if item.name != "current_price"
    )

    missing = build_observation_receipt(
        kind=ObservationKind.STRATEGY,
        research_trading_date=date(2026, 8, 10),
        trading_date=date(2026, 8, 11),
        observed_at=NOW,
        symbol="000001.SZ",
        policy=policy,
        values=missing_price,
        source_references=(_reference("TARGETED_OUTCOME", "b"),),
    )
    future = build_observation_receipt(
        kind=ObservationKind.STRATEGY,
        research_trading_date=date(2026, 8, 10),
        trading_date=date(2026, 8, 11),
        observed_at=NOW,
        symbol="000001.SZ",
        policy=policy,
        values=tuple(
            replace(item, available_at=NOW + timedelta(seconds=1))
            if item.name == "current_price"
            else item
            for item in _strategy_values()
        ),
        source_references=(_reference("TARGETED_OUTCOME", "b"),),
    )

    assert missing.status is ObservationBuildStatus.NOT_ESTIMABLE
    assert missing.observation_payload is None
    assert "REQUIRED_VALUE_MISSING:current_price" in missing.reason_codes
    assert future.status is ObservationBuildStatus.NOT_ESTIMABLE
    assert "FUTURE_VALUE_REJECTED:current_price" in future.reason_codes


def test_observed_fact_requires_an_owner_reference_and_value_path() -> None:
    with pytest.raises(ValueError, match="Observed Fact requires an owner reference"):
        OwnerObservationValue(
            name="current_price",
            value="10",
            provenance=ShadowParameterProvenance.OBSERVED_FACT,
            source_reference=None,
            effective_at=NOW,
            available_at=NOW,
            source_value_path="facts.current_price",
        )


def test_policy_identity_includes_every_result_affecting_assumption() -> None:
    policy = _policy()

    changed = ShadowObservationPolicy.create(
        policy_version=policy.policy_version,
        intended_quantity=policy.intended_quantity,
        fill_checkpoint=policy.fill_checkpoint,
        mark_checkpoint=policy.mark_checkpoint,
        trade_session=policy.trade_session,
        fillability=policy.fillability,
        slippage_bps=Decimal("6"),
        impact_bps=policy.impact_bps,
        commission_bps=policy.commission_bps,
        exit_cost_bps=policy.exit_cost_bps,
        created_at=policy.created_at,
    )

    assert changed.policy_id != policy.policy_id
    assert changed.policy_hash != policy.policy_hash


def test_portfolio_observation_requires_adv_and_preserves_market_payload() -> None:
    values = tuple(
        _value(f"000001.SZ.{name}", value)
        for name, value in (
            ("reference_price", "10"),
            ("mark_price", "10.2"),
            ("average_daily_amount", "10500000"),
            ("trading_status", "TRADING"),
            ("price_limit_state", "NORMAL"),
            ("trade_session", "CONTINUOUS_AM"),
        )
    )
    payload = {
        "market_observations": [
            {
                "symbol": "000001.SZ",
                "reference_price": "10",
                "mark_price": "10.2",
                "average_daily_amount": "10500000",
            }
        ]
    }

    ready = build_portfolio_observation_receipt(
        research_trading_date=date(2026, 8, 10),
        trading_date=date(2026, 8, 11),
        observed_at=NOW,
        policy=_policy(),
        values=values,
        source_references=(_reference("RESEARCH_PANEL_V2", "c"),),
        observation_payload=payload,
    )
    missing_adv = build_portfolio_observation_receipt(
        research_trading_date=date(2026, 8, 10),
        trading_date=date(2026, 8, 11),
        observed_at=NOW,
        policy=_policy(),
        values=tuple(
            item
            for item in values
            if not item.name.endswith("average_daily_amount")
        ),
        source_references=(_reference("RESEARCH_PANEL_V2", "c"),),
        observation_payload=payload,
    )

    assert ready.status is ObservationBuildStatus.READY
    assert ready.observation_payload == payload
    assert missing_adv.status is ObservationBuildStatus.NOT_ESTIMABLE
    assert missing_adv.observation_payload is None
    assert "REQUIRED_VALUE_MISSING:000001.SZ.average_daily_amount" in (
        missing_adv.reason_codes
    )
