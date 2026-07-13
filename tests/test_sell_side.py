from __future__ import annotations

import pytest

from market_regime_alpha.dividend_t.models import Signal
from market_regime_alpha.dividend_t.sell_side import SELL_ACTION_SPECS, SellAction, sell_action_spec
from market_regime_alpha.dividend_t.signal_intent import PrimarySetupCode, RiskEnforcement, SignalIntent


@pytest.mark.parametrize(
    ("action", "signal", "setup", "intent", "enforcement"),
    [
        (SellAction.TAKE_PROFIT_T, Signal.SELL_T, PrimarySetupCode.TAKE_PROFIT_T, SignalIntent.MEAN_REVERSION_T, RiskEnforcement.NONE),
        (
            SellAction.TAKE_PROFIT_REDUCE_T,
            Signal.REDUCE,
            PrimarySetupCode.TAKE_PROFIT_REDUCE_T,
            SignalIntent.MEAN_REVERSION_T,
            RiskEnforcement.NONE,
        ),
        (SellAction.RISK_REDUCE_T, Signal.REDUCE, PrimarySetupCode.RISK_REDUCE_T, SignalIntent.RISK_REDUCTION, RiskEnforcement.SOFT),
        (SellAction.EXIT_T_SOFT, Signal.STOP_T, PrimarySetupCode.EXIT_T_SOFT, SignalIntent.RISK_REDUCTION, RiskEnforcement.SOFT),
        (SellAction.EXIT_T_HARD, Signal.STOP_T, PrimarySetupCode.EXIT_T_HARD, SignalIntent.RISK_REDUCTION, RiskEnforcement.HARD),
        (SellAction.STOP_T, Signal.STOP_T, PrimarySetupCode.STOP_T, SignalIntent.RISK_REDUCTION, RiskEnforcement.HARD),
        (
            SellAction.REVERSE_T_SELL,
            Signal.SELL_REVERSE_T,
            PrimarySetupCode.REVERSE_T_SELL,
            SignalIntent.MEAN_REVERSION_T,
            RiskEnforcement.NONE,
        ),
        (SellAction.CLEAR_BASE, Signal.CLEAR, PrimarySetupCode.CLEAR_BASE, SignalIntent.RISK_REDUCTION, RiskEnforcement.HARD),
    ],
)
def test_each_research_sell_action_has_one_frozen_contract(
    action: SellAction, signal: Signal, setup: PrimarySetupCode, intent: SignalIntent, enforcement: RiskEnforcement
) -> None:
    spec = sell_action_spec(action)

    assert spec.signal is signal
    assert spec.primary_setup_code is setup
    assert spec.signal_intent is intent
    assert spec.risk_enforcement is enforcement


def test_sell_action_map_is_total_and_does_not_relax_intent_enforcement_contract() -> None:
    assert set(SELL_ACTION_SPECS) == set(SellAction)
    assert all(
        (spec.signal_intent is SignalIntent.RISK_REDUCTION) == (spec.risk_enforcement is not RiskEnforcement.NONE)
        for spec in SELL_ACTION_SPECS.values()
    )
