"""Trading decision engine for the long-term dividend T-trading model."""

from __future__ import annotations

from market_regime_alpha.dividend_t.models import (
    FundamentalInputs,
    OrderIntent,
    PositionState,
    RetreatInputs,
    ScoreBreakdown,
    Signal,
    StrategyDecision,
    TechnicalInputs,
    TrendState,
)
from market_regime_alpha.dividend_t.scoring import base_position_limit, build_score_breakdown
from market_regime_alpha.dividend_t.chan import BUY_POINTS, SELL_POINTS
from market_regime_alpha.dividend_t.signal_intent import (
    CandidateSignal,
    PrimarySetupCode,
    candidate_for,
    decision_trace_for,
    no_candidate,
)


LEGACY_CURRENT_BAR = "CURRENT_DECISION_BAR"


class DividendTStrategy:
    """Evaluate the model document rules into one actionable signal."""

    def evaluate(
        self,
        *,
        symbol: str,
        fundamental: FundamentalInputs,
        retreat: RetreatInputs,
        technical: TechnicalInputs,
        position: PositionState | None = None,
        decision_bar_time: str = LEGACY_CURRENT_BAR,
    ) -> StrategyDecision:
        position = position or PositionState()
        score = build_score_breakdown(fundamental, retreat, technical)
        base_limit = base_position_limit(score.F_score)
        candidate = select_simplified_candidate(
            score=score,
            retreat=retreat,
            technical=technical,
            position=position,
            decision_bar_time=decision_bar_time,
        )
        signal = candidate.candidate_signal or Signal.HOLD
        reasons = candidate.candidate_reasons
        trace = decision_trace_for(candidate, final_signal=signal)

        if signal is Signal.CLEAR:
            pct = min(position.symbol_position_pct, 0.20)
            return StrategyDecision(
                symbol=symbol,
                signal=signal,
                score=score,
                base_position_limit_pct=base_limit,
                suggested_trade_pct=pct,
                reasons=reasons,
                warnings=("基本面不支持底仓。",),
                order_intent=_order(symbol, "SELL", "base", signal, pct, reasons[0]),
                decision_trace=trace,
            )

        if signal is Signal.REDUCE:
            pct = min(position.symbol_position_pct, 0.10)
            return StrategyDecision(
                symbol=symbol,
                signal=signal,
                score=score,
                base_position_limit_pct=base_limit,
                suggested_trade_pct=pct,
                reasons=reasons,
                warnings=("基本面评分低于减底仓阈值。",),
                order_intent=_order(symbol, "SELL", "base", signal, pct, reasons[0]),
                decision_trace=trace,
            )

        if signal is Signal.STOP_T:
            return StrategyDecision(
                symbol=symbol,
                signal=signal,
                score=score,
                base_position_limit_pct=base_limit,
                suggested_trade_pct=0.0,
                reasons=reasons,
                warnings=("暂停 T 仓交易，只保留复盘和底仓管理。",),
                decision_trace=trace,
            )

        if signal is Signal.BUY_T:
            target_pct = _target_position_pct(score.total_score)
            pct = max(0.0, target_pct - position.symbol_position_pct)
            return StrategyDecision(
                symbol=symbol,
                signal=signal,
                score=score,
                base_position_limit_pct=base_limit,
                suggested_trade_pct=pct,
                reasons=reasons,
                order_intent=_order(symbol, "BUY", "t", signal, pct, "买入主动仓位"),
                decision_trace=trace,
            )

        if signal is Signal.SELL_T:
            active_position_pct = max(position.t_position_pct, position.symbol_position_pct - position.base_position_pct)
            pct = min(active_position_pct, _sell_t_pct(retreat.sell_pressure, technical))
            return StrategyDecision(
                symbol=symbol,
                signal=signal,
                score=score,
                base_position_limit_pct=base_limit,
                suggested_trade_pct=pct,
                reasons=reasons,
                order_intent=_order(symbol, "SELL", "t", signal, pct, "卖出主动仓位"),
                decision_trace=trace,
            )

        if signal is Signal.BUILD_BASE:
            pct = min(0.05, base_limit - position.symbol_position_pct)
            return StrategyDecision(
                symbol=symbol,
                signal=signal,
                score=score,
                base_position_limit_pct=base_limit,
                suggested_trade_pct=max(0.0, pct),
                reasons=reasons,
                order_intent=_order(symbol, "BUY", "base", signal, max(0.0, pct), "分批建底仓"),
                decision_trace=trace,
            )

        return StrategyDecision(
            symbol=symbol,
            signal=signal,
            score=score,
            base_position_limit_pct=base_limit,
            suggested_trade_pct=0.0,
            reasons=reasons,
            decision_trace=trace,
        )


def select_simplified_candidate(
    *,
    score: ScoreBreakdown,
    retreat: RetreatInputs,
    technical: TechnicalInputs,
    position: PositionState,
    decision_bar_time: str,
) -> CandidateSignal:
    """Select one primary setup before assigning the candidate intent."""

    if score.F_score < 50:
        clear_reasons = ("F < 50，标的不合格，停止做 T 并准备清仓。",)
        return candidate_for(Signal.CLEAR, PrimarySetupCode.CLEAR, technical, decision_bar_time, reasons=clear_reasons)
    if score.F_score < 55:
        reduce_reasons = ("F < 55，分红或周期逻辑偏弱，优先减底仓。",)
        return candidate_for(Signal.REDUCE, PrimarySetupCode.REDUCE, technical, decision_bar_time, reasons=reduce_reasons)

    stop_reasons = tuple(_stop_t_reasons(score.F_score, technical, position))
    if stop_reasons:
        return candidate_for(Signal.STOP_T, _primary_stop_setup(technical), technical, decision_bar_time, reasons=stop_reasons)

    if _can_buy_t(score, retreat, technical):
        target_pct = _target_position_pct(score.total_score)
        buy_reasons = (
            "F/R/T 同时满足买入主动仓位门槛。",
            _buy_location_reason(technical),
            f"卖压未超过阈值，板块和趋势没有破位，目标总仓位约 {target_pct:.0%}。",
        )
        return candidate_for(Signal.BUY_T, _primary_buy_setup(technical), technical, decision_bar_time, reasons=buy_reasons)

    if _should_sell_t(retreat, technical):
        sell_reasons = (
            "价格接近压力或出现放量滞涨，卖出主动仓位。",
            "盈亏比下降，卖压上升。",
        )
        return candidate_for(Signal.SELL_T, _primary_sell_setup(technical), technical, decision_bar_time, reasons=sell_reasons)

    if position.symbol_position_pct < min(base_position_limit(score.F_score), 0.20) and score.F_score >= 70:
        build_reasons = ("F >= 70 且当前底仓不足，可分批建立观察底仓。",)
        return candidate_for(Signal.BUILD_BASE, PrimarySetupCode.BUILD_BASE, technical, decision_bar_time, reasons=build_reasons)

    return no_candidate(decision_bar_time, reasons=("没有触发买 T、卖 T、减仓或停手机制。",))


def _primary_stop_setup(technical: TechnicalInputs) -> PrimarySetupCode:
    if technical.chan_structure_type == "breakdown":
        return PrimarySetupCode.STRUCTURE_BREAK
    if technical.chan_sell_point_type == "sell3":
        return PrimarySetupCode.THIRD_SELL
    if technical.chan_sell_point_type in {"sell1", "sell2"}:
        return PrimarySetupCode.CHAN_SELL_RISK
    return PrimarySetupCode.STOP_T


def _primary_buy_setup(technical: TechnicalInputs) -> PrimarySetupCode:
    if technical.chan_buy_point_type == "buy3":
        return PrimarySetupCode.THIRD_BUY_FOLLOW
    if technical.chan_structure_type == "breakout":
        return PrimarySetupCode.BREAKOUT_CONFIRMED
    if technical.intraday_reversal:
        return PrimarySetupCode.INTRADAY_REVERSAL
    return PrimarySetupCode.PULLBACK_LOW_BUY


def _primary_sell_setup(technical: TechnicalInputs) -> PrimarySetupCode:
    if technical.chan_divergence_type == "top":
        return PrimarySetupCode.TOP_DIVERGENCE_RISK
    return PrimarySetupCode.PRESSURE_SELL_T


def _can_buy_t(score, retreat: RetreatInputs, technical: TechnicalInputs) -> bool:
    chan_buy = _chan_buy_point(technical)
    chan_sell = _chan_sell_point(technical)
    traditional_entry = technical.near_support and (technical.shrinking_pullback or technical.intraday_reversal)
    chan_entry = chan_buy and technical.chan_score >= 68.0 and (
        technical.chan_buy_point_type == "buy3"
        or technical.near_support
        or technical.chan_structure_type in {"pivot", "breakout", "divergence"}
    )
    return (
        score.F_score >= 65
        and score.R_score >= 70
        and score.T_score >= 75
        and retreat.risk_reward_ratio >= 2.0
        and retreat.sell_pressure <= 3.0
        and not chan_sell
        and technical.sector_healthy
        and technical.trend_state != TrendState.DOWNTREND
        and (traditional_entry or chan_entry)
    )


def _should_sell_t(retreat: RetreatInputs, technical: TechnicalInputs) -> bool:
    if _chan_sell_point(technical):
        return True
    pressure_signal = retreat.sell_pressure >= 4.0 or retreat.risk_reward_ratio < 1.5
    technical_signal = technical.near_resistance or technical.volume_stalling or technical.trend_state == TrendState.EXHAUSTION
    return pressure_signal and technical_signal


def _stop_t_reasons(score_f: float, technical: TechnicalInputs, position: PositionState) -> list[str]:
    reasons: list[str] = []
    if score_f < 60:
        reasons.append("F < 60，不允许重仓做 T。")
    if technical.trend_state == TrendState.DOWNTREND:
        reasons.append("技术趋势进入下跌状态，停止做 T。")
    if technical.chan_sell_point_type == "sell3" or technical.chan_structure_type == "breakdown":
        reasons.append("缠论结构跌破中枢或形成三卖，停止主动 T 仓。")
    elif technical.chan_sell_point_type in {"sell1", "sell2"}:
        reasons.append("缠论结构出现卖点，主动 T 仓优先降风险。")
    if not technical.sector_healthy:
        reasons.append("板块系统性走弱，停止做 T。")
    if position.consecutive_t_failures >= 2:
        reasons.append("连续两次 T 失败，触发停手机制。")
    return reasons


def _chan_buy_point(technical: TechnicalInputs) -> bool:
    return technical.chan_buy_point_type in BUY_POINTS and technical.chan_sell_point_type not in SELL_POINTS


def _chan_sell_point(technical: TechnicalInputs) -> bool:
    return technical.chan_sell_point_type in SELL_POINTS or technical.chan_divergence_type == "top"


def _buy_location_reason(technical: TechnicalInputs) -> str:
    if _chan_buy_point(technical):
        return f"缠论结构出现 {technical.chan_buy_point_type}，中枢/背驰位置满足买点门。"
    return "价格接近支撑，盈亏比达到模型要求。"


def _target_position_pct(total_score: float) -> float:
    if total_score >= 85:
        return 0.80
    if total_score >= 78:
        return 0.55
    return 0.35


def _sell_t_pct(sell_pressure: float, technical: TechnicalInputs) -> float:
    if sell_pressure >= 4.5 or technical.trend_state == TrendState.EXHAUSTION:
        return 0.15
    if sell_pressure >= 4.0 or technical.volume_stalling:
        return 0.10
    return 0.05


def _order(
    symbol: str,
    side: str,
    position_type: str,
    signal: Signal,
    pct: float,
    reason: str,
) -> OrderIntent | None:
    if pct <= 0:
        return None
    return OrderIntent(
        symbol=symbol,
        side=side,
        position_type=position_type,
        signal=signal,
        notional_pct=round(pct, 4),
        reason=reason,
    )
