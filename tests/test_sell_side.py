from __future__ import annotations

import pytest

from market_regime_alpha.dividend_t.backtest import DividendTBacktestConfig
from market_regime_alpha.dividend_t.models import Signal
from market_regime_alpha.dividend_t.sell_side import (
    SELL_ACTION_SPECS,
    PendingBuyback,
    PositionLifecycleContext,
    ResearchExecutionState,
    SellAction,
    SellLifecyclePolicy,
    advance_research_execution_state,
    atr_trailing_level,
    execute_research_action,
    select_research_sell_action,
    sell_action_spec,
)
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


def test_research_lifecycle_selector_prioritizes_hard_risk_then_atr_profit_and_time_exit() -> None:
    policy = SellLifecyclePolicy(atr_multiple=2.0, mfe_drawdown_trigger=0.03, time_stop_bars=10)

    hard = select_research_sell_action(
        PositionLifecycleContext(
            entry_price=10.0,
            entry_time="2026-01-05 10:00",
            holding_bars=2,
            unrealized_return=-0.12,
            max_unrealized_return=0.0,
            drawdown_from_peak=-0.12,
            t_position_pct=0.2,
            base_position_pct=0.3,
            same_day_bought_qty=0,
            sellable_qty=1000,
            pending_buyback=False,
            setup_invalidation_level="HARD",
            atr_trailing_level=9.0,
            current_price=8.8,
        ),
        policy,
    )
    profit = select_research_sell_action(
        PositionLifecycleContext(
            entry_price=10.0,
            entry_time="2026-01-05 10:00",
            holding_bars=2,
            unrealized_return=0.04,
            max_unrealized_return=0.10,
            drawdown_from_peak=-0.06,
            t_position_pct=0.2,
            base_position_pct=0.3,
            same_day_bought_qty=0,
            sellable_qty=1000,
            pending_buyback=False,
            setup_invalidation_level="NONE",
            atr_trailing_level=9.0,
            current_price=10.4,
        ),
        policy,
    )
    timed = select_research_sell_action(
        PositionLifecycleContext(
            entry_price=10.0,
            entry_time="2026-01-05 10:00",
            holding_bars=10,
            unrealized_return=0.0,
            max_unrealized_return=0.01,
            drawdown_from_peak=-0.01,
            t_position_pct=0.2,
            base_position_pct=0.3,
            same_day_bought_qty=0,
            sellable_qty=1000,
            pending_buyback=False,
            setup_invalidation_level="NONE",
            atr_trailing_level=9.0,
            current_price=10.0,
        ),
        policy,
    )

    assert hard.action is SellAction.EXIT_T_HARD
    assert profit.action is SellAction.TAKE_PROFIT_T
    assert timed.action is SellAction.RISK_REDUCE_T
    assert atr_trailing_level(12.0, atr=1.0, policy=policy) == 10.0


def test_research_execution_state_unlocks_t1_and_tracks_partial_buyback_expiry_and_hard_risk_cancel() -> None:
    config = DividendTBacktestConfig(enable_t_sell=True)
    state = ResearchExecutionState(
        cash=2_000.0,
        base_shares=500,
        t_shares=0,
        base_locked_shares=500,
        t_locked_shares=0,
        trade_date="2026-01-05",
        pending_buyback=PendingBuyback(
            remaining_shares=200,
            allocated_proceeds=2000.0,
            target_price=9.8,
            created_bar_index=1,
            created_trade_date="2026-01-05",
            expiry_bars=3,
            expiry_trade_days=2,
        ),
    )

    unlocked = advance_research_execution_state(state, bar_time="2026-01-06 09:35", bar_index=2)
    partial = execute_research_action(
        unlocked,
        signal=Signal.BUY_BACK_REVERSE_T,
        symbol="600000.SH",
        candidate_bar_close_time="2026-01-06 09:30",
        next_bar={
            "timestamp": "2026-01-06 09:35",
            "open": 9.7,
            "high": 9.8,
            "low": 9.6,
            "close": 9.7,
            "volume": 1000,
            "research_max_fill_shares": 100,
        },
        config=config,
        trade_pct=1.0,
        bar_index=2,
    )
    cancelled = execute_research_action(
        partial.state,
        signal=Signal.STOP_T,
        symbol="600000.SH",
        candidate_bar_close_time="2026-01-06 09:35",
        next_bar={"timestamp": "2026-01-06 09:40", "open": 9.5, "high": 9.6, "low": 9.4, "close": 9.5, "volume": 1000},
        config=config,
        trade_pct=1.0,
        bar_index=3,
        hard_risk_exit=True,
    )

    assert unlocked.base_locked_shares == 0
    assert partial.resolution.executable and partial.resolution.shares == 100
    assert partial.state.pending_buyback is not None and partial.state.pending_buyback.remaining_shares == 100
    assert cancelled.state.pending_buyback is None
    assert cancelled.pending_buyback_event == "BUYBACK_CANCELLED_BY_HARD_RISK"
