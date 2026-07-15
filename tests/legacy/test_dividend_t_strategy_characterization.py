from __future__ import annotations

import pytest

from market_regime_alpha.dividend_t.models import (
    FundamentalInputs,
    PositionState,
    RetreatInputs,
    Signal,
    TechnicalInputs,
    TrendState,
)
from market_regime_alpha.dividend_t.signal_intent import PrimarySetupCode, RiskEnforcement, SignalIntent
from market_regime_alpha.dividend_t.strategy import DividendTStrategy


STRATEGY = DividendTStrategy()
DECISION_BAR = "2026-07-15 14:55:00"


def _fundamental(score: float) -> FundamentalInputs:
    return FundamentalInputs(score, score, score, score, score)


def test_legacy_hard_clear_golden_decision() -> None:
    decision = STRATEGY.evaluate(
        symbol="600001.SH",
        fundamental=_fundamental(40.0),
        retreat=RetreatInputs(4.0, 4.0, 2.5, 2.0),
        technical=TechnicalInputs(80.0, 80.0, 80.0, 80.0),
        position=PositionState(
            symbol_position_pct=0.30,
            base_position_pct=0.30,
            cash_pct=0.70,
            available_cash_pct=0.70,
            available_sell_pct=0.30,
        ),
        decision_bar_time=DECISION_BAR,
    )

    assert decision.signal is Signal.CLEAR
    assert decision.score.F_score == 40.0
    assert decision.base_position_limit_pct == 0.0
    assert decision.suggested_trade_pct == pytest.approx(0.20)
    assert decision.order_intent is not None
    assert decision.order_intent.side == "SELL"
    assert decision.order_intent.position_type == "base"
    assert decision.order_intent.signal is Signal.CLEAR
    assert decision.order_intent.notional_pct == pytest.approx(0.20)
    assert decision.decision_trace is not None
    assert decision.decision_trace.primary_setup_code is PrimarySetupCode.CLEAR
    assert decision.decision_trace.candidate_signal_intent is SignalIntent.RISK_REDUCTION
    assert decision.decision_trace.risk_enforcement is RiskEnforcement.HARD
    assert decision.decision_trace.final_signal is Signal.CLEAR


def test_legacy_buy_t_golden_decision() -> None:
    decision = STRATEGY.evaluate(
        symbol="000001.SZ",
        fundamental=_fundamental(80.0),
        retreat=RetreatInputs(4.0, 4.0, 2.5, 2.0),
        technical=TechnicalInputs(
            85.0,
            85.0,
            85.0,
            85.0,
            chan_score=80.0,
            trend_state=TrendState.RANGE,
            near_support=True,
            shrinking_pullback=True,
            sector_healthy=True,
        ),
        position=PositionState(
            symbol_position_pct=0.10,
            base_position_pct=0.10,
            t_position_pct=0.0,
            cash_pct=0.90,
            available_cash_pct=0.90,
            available_sell_pct=0.10,
        ),
        decision_bar_time=DECISION_BAR,
    )

    assert decision.signal is Signal.BUY_T
    assert decision.score.F_score == 80.0
    assert decision.score.R_score == 78.5
    assert decision.score.T_score == 84.0
    assert decision.score.total_score == 80.68
    assert decision.suggested_trade_pct == pytest.approx(0.45)
    assert decision.order_intent is not None
    assert decision.order_intent.side == "BUY"
    assert decision.order_intent.position_type == "t"
    assert decision.order_intent.signal is Signal.BUY_T
    assert decision.order_intent.notional_pct == pytest.approx(0.45)
    assert decision.decision_trace is not None
    assert decision.decision_trace.primary_setup_code is PrimarySetupCode.PULLBACK_LOW_BUY
    assert decision.decision_trace.candidate_signal_intent is SignalIntent.MEAN_REVERSION_T
    assert decision.decision_trace.final_signal is Signal.BUY_T
    assert decision.decision_trace.original_suggested_trade_pct == pytest.approx(0.45)
    assert decision.decision_trace.adjusted_suggested_trade_pct == pytest.approx(0.45)


def test_legacy_sell_t_golden_decision() -> None:
    decision = STRATEGY.evaluate(
        symbol="000001.SZ",
        fundamental=_fundamental(80.0),
        retreat=RetreatInputs(3.0, 3.0, 1.2, 4.5),
        technical=TechnicalInputs(
            80.0,
            80.0,
            80.0,
            80.0,
            chan_score=80.0,
            trend_state=TrendState.RANGE,
            near_resistance=True,
            volume_stalling=True,
            sector_healthy=True,
        ),
        position=PositionState(
            symbol_position_pct=0.50,
            base_position_pct=0.20,
            t_position_pct=0.30,
            cash_pct=0.50,
            available_cash_pct=0.50,
            available_sell_pct=0.50,
        ),
        decision_bar_time=DECISION_BAR,
    )

    assert decision.signal is Signal.SELL_T
    assert decision.suggested_trade_pct == pytest.approx(0.15)
    assert decision.order_intent is not None
    assert decision.order_intent.side == "SELL"
    assert decision.order_intent.position_type == "t"
    assert decision.order_intent.signal is Signal.SELL_T
    assert decision.order_intent.notional_pct == pytest.approx(0.15)
    assert decision.decision_trace is not None
    assert decision.decision_trace.primary_setup_code is PrimarySetupCode.PRESSURE_SELL_T
    assert decision.decision_trace.candidate_signal_intent is SignalIntent.MEAN_REVERSION_T
    assert decision.decision_trace.final_signal is Signal.SELL_T
