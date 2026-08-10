from __future__ import annotations

from market_regime_alpha.application.strategy_shadow.portfolio import (
    PortfolioWeightingMethod,
    ShadowParameterProvenance,
)
from market_regime_alpha.application.strategy_shadow.portfolio_operator import (
    PortfolioShadowDayInput,
)


def _payload() -> dict[str, object]:
    parameter = {
        "value": "2",
        "provenance": "ENGINEERING_ASSUMPTION",
    }
    return {
        "research_trading_date": "2026-08-10",
        "trading_date": "2026-08-10",
        "observed_at": "2026-08-10T06:00:00+00:00",
        "portfolio_id": None,
        "initial_cash": "1000000",
        "policy": {
            "policy_version": "phase-b-portfolio-v1",
            "effective_at": "2026-08-10T00:00:00+00:00",
            "top_k": 3,
            "weighting_method": "EQUAL_WEIGHT",
            "lot_size": 100,
            "t_plus_one": True,
            "parameters": {
                "commission_bps": parameter,
                "slippage_bps": {**parameter, "value": "5"},
                "impact_bps": {**parameter, "value": "3"},
                "exit_cost_bps": parameter,
                "max_participation_rate": {**parameter, "value": "0.1"},
            },
        },
        "market_observations": [
            {
                "symbol": "000001.SZ",
                "reference_price": "10",
                "mark_price": "10.1",
                "average_daily_amount": "10000000",
                "trading_status": "TRADING",
                "price_limit_state": "NORMAL",
                "trade_session": "CONTINUOUS_PM",
                "risk_weight": None,
                "risk_weight_provenance": None,
                "reason_codes": [],
            }
        ],
    }


def test_portfolio_shadow_operator_input_requires_explicit_policy_provenance() -> None:
    request = PortfolioShadowDayInput.from_canonical_dict(_payload())

    assert request.policy.weighting_method is PortfolioWeightingMethod.EQUAL_WEIGHT
    assert request.policy.parameters[0].provenance is (
        ShadowParameterProvenance.ENGINEERING_ASSUMPTION
    )
    assert request.market_inputs[0].symbol == "000001.SZ"
