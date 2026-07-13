"""Manual action state machine for the COSCO timing engine."""

from __future__ import annotations

from market_regime_alpha.dividend_t.attention import AttentionScore
from market_regime_alpha.dividend_t.certainty import CertaintyScore
from market_regime_alpha.dividend_t.chan import BUY_POINTS, SELL_POINTS, ChanStructure
from market_regime_alpha.dividend_t.cosco_profile import CoscoProfile
from market_regime_alpha.dividend_t.cosco_timing_capital_flow import _capital_flow_confirms_buy
from market_regime_alpha.dividend_t.cosco_timing_signal import _buy_signal_strength_score
from market_regime_alpha.dividend_t.cosco_timing_types import (
    BreakoutSetup,
    CapitalFlowEstimate,
    DailyContext,
    IntradayContext,
    ManualCandidateDecision,
    MultiPeriodTrend,
    TrendProbability,
    VolumePriceStructure,
    manual_candidate,
)
from market_regime_alpha.dividend_t.force_ratio import ForceRatioEstimate
from market_regime_alpha.dividend_t.memory import MemoryScore
from market_regime_alpha.dividend_t.models import Signal, TrendState
from market_regime_alpha.dividend_t.scoring import clamp
from market_regime_alpha.dividend_t.sell_pressure import SellPressureEstimate
from market_regime_alpha.dividend_t.signal_intent import EntryConfirmation, ExitConfirmation, PrimarySetupCode, RiskEnforcement

def _probability_allows_attack(trend_probability: TrendProbability, *, mode: str) -> bool:
    if mode == "force_reversal":
        return trend_probability.up_1d >= 0.56 and trend_probability.up_3d >= 0.52 and trend_probability.down_1d < 0.57
    if mode == "trend_follow":
        return trend_probability.up_1d >= 0.54 and trend_probability.up_3d >= 0.54 and trend_probability.down_3d < 0.57
    if mode == "attention_feedback":
        return trend_probability.up_1d >= 0.55 and trend_probability.up_3d >= 0.52 and trend_probability.down_1d < 0.56
    if mode == "range_probe":
        return trend_probability.up_1d >= 0.53 and trend_probability.up_3d >= 0.51 and trend_probability.down_1d < 0.58
    if mode == "low_buy":
        return trend_probability.up_1d >= 0.52 and trend_probability.up_3d >= 0.50 and trend_probability.down_1d < 0.59
    return trend_probability.state != "DOWN_RISK"

def _manual_action(
    *,
    force: ForceRatioEstimate,
    attention: AttentionScore,
    certainty: CertaintyScore,
    memory: MemoryScore,
    sell_pressure: SellPressureEstimate,
    trend_state: TrendState,
    levels: dict[str, float],
    daily_context: DailyContext,
    intraday_context: IntradayContext,
    multi_period_trend: MultiPeriodTrend,
    capital_flow: CapitalFlowEstimate,
    volume_price_structure: VolumePriceStructure,
    trend_probability: TrendProbability,
    breakout_setup: BreakoutSetup,
    chan_structure: ChanStructure,
    profile: CoscoProfile,
    decision_bar_time: str,
) -> ManualCandidateDecision:
    reasons: list[str] = []
    warnings: list[str] = []
    current = levels["current"]
    support = levels["support"]
    resistance = levels["resistance"]
    near_support = current <= support + profile.support_atr_width * levels["atr"]
    near_resistance = current >= resistance - 0.90 * levels["atr"]
    chan_buy_point = chan_structure.buy_point_type in BUY_POINTS
    chan_sell_point = chan_structure.sell_point_type in SELL_POINTS
    entry_values: set[EntryConfirmation] = set()
    if intraday_context.rebound_from_low:
        entry_values.add(EntryConfirmation.INTRADAY_REVERSAL)
    if chan_buy_point:
        entry_values.add(EntryConfirmation.CHAN_BUY_POINT)
    if intraday_context.support_confirmed:
        entry_values.add(EntryConfirmation.SUPPORT_HOLD)
    if intraday_context.five_min_reclaim:
        entry_values.add(EntryConfirmation.VWAP_RECLAIM)
    exit_values: set[ExitConfirmation] = set()
    if volume_price_structure.high_volume_stall_score >= 72.0:
        exit_values.add(ExitConfirmation.VOLUME_STALLING)
    if intraday_context.resistance_confirmed:
        exit_values.add(ExitConfirmation.RESISTANCE_REJECTION)
    if chan_sell_point:
        exit_values.add(ExitConfirmation.CHAN_SELL_POINT)
    if chan_structure.divergence_type == "top":
        exit_values.add(ExitConfirmation.TOP_DIVERGENCE)
    entry_confirmations = frozenset(entry_values) or frozenset({EntryConfirmation.NONE})
    exit_confirmations = frozenset(exit_values) or frozenset({ExitConfirmation.NONE})

    def emit(
        action: str,
        signal: Signal | None,
        setup: PrimarySetupCode | None,
        branch_reasons: list[str],
        branch_warnings: list[str],
        risk_enforcement: RiskEnforcement = RiskEnforcement.NONE,
    ) -> ManualCandidateDecision:
        return manual_candidate(
            action,
            signal,
            setup,
            decision_bar_time=decision_bar_time,
            entry_confirmations=entry_confirmations,
            exit_confirmations=exit_confirmations,
            reasons=tuple(branch_reasons),
            warnings=tuple(branch_warnings),
            risk_enforcement=risk_enforcement,
        )

    low_buy_confirmed = intraday_context.support_confirmed or (
        intraday_context.near_support
        and intraday_context.five_min_reclaim
        and force.force_ratio >= profile.early_buy_force_threshold
        and sell_pressure.score <= profile.early_buy_sell_pressure_max
    ) or chan_structure.buy_point_type in {"buy1", "buy2", "range_buy"}
    buy_strength_score = _buy_signal_strength_score(
        force=force,
        certainty=certainty,
        sell_pressure=sell_pressure,
        daily_context=daily_context,
        intraday_context=intraday_context,
        multi_period_trend=multi_period_trend,
        capital_flow=capital_flow,
        chan_structure=chan_structure,
        volume_price_structure=volume_price_structure,
        risk_reward_ratio=levels["risk_reward_ratio"],
    )
    force_buy_edge = _tuishen_force_buy_edge(
        force=force,
        attention=attention,
        certainty=certainty,
        memory=memory,
        sell_pressure=sell_pressure,
        multi_period_trend=multi_period_trend,
        capital_flow=capital_flow,
        volume_price_structure=volume_price_structure,
    )
    flow_confirmed = _capital_flow_confirms_buy(capital_flow, min_score=60.0)
    volume_price_constructive = volume_price_structure.score >= 62.0 and volume_price_structure.high_volume_stall_score < 72.0
    volume_price_strong = (
        volume_price_structure.score >= 72.0
        and (
            volume_price_structure.volume_breakout_score >= 70.0
            or volume_price_structure.post_breakout_volume_persistence_score >= 70.0
            or volume_price_structure.low_volume_pullback_score >= 72.0
        )
        and volume_price_structure.high_volume_stall_score < 70.0
    )
    trend_5_20_allows_pullback = multi_period_trend.trend_5_20_state in {"UP", "PULLBACK_IN_UPTREND"}

    if daily_context.state == "WEAK" and (near_support or intraday_context.support_confirmed) and not trend_5_20_allows_pullback:
        return emit(
            "WAIT_DAILY_WEAK",
            None,
            None,
            [
                "价格接近支撑区，但日线背景偏弱，禁止把分钟线低点当成买 T 机会。",
                "需要等日线重新站回近端支撑，或次日重新计算新的支撑区。",
                *list(daily_context.reasons)[:2],
            ],
            ["时间尺度门控已拦截 BUY_T：日线不允许，分钟线信号只保留为观察。"],
        )

    if chan_structure.sell_point_type == "sell3" or chan_structure.structure_type == "breakdown":
        return emit(
            "STOP_T_WAIT",
            Signal.STOP_T,
            PrimarySetupCode.THIRD_SELL if chan_structure.sell_point_type == "sell3" else PrimarySetupCode.STRUCTURE_BREAK,
            [
                "缠论风控门触发：价格跌破中枢或形成三卖，主动 T 仓停止。",
                f"中枢下沿={chan_structure.pivot_low if chan_structure.pivot_low is not None else '-'}，结构={chan_structure.structure_type}。",
                *list(chan_structure.reasons)[:3],
            ],
            ["结构失效优先级高于退神评分；跌回中枢下方不做买入修正。"],
            RiskEnforcement.HARD,
        )

    if chan_sell_point or chan_structure.divergence_type == "top":
        reasons.extend(
            [
                "缠论卖点优先：出现顶背驰、一卖/二卖或高位结构转弱。",
                f"缠论结构分 {chan_structure.score:.1f}，卖点={chan_structure.sell_point_type}，背驰={chan_structure.divergence_type}。",
                *list(chan_structure.reasons)[:3],
            ]
        )
        if not daily_context.buyback_allowed:
            warnings.append("日线背景不允许买回；本次只给卖出 T 参考，不给倒 T 买回价。")
        setup = PrimarySetupCode.TOP_DIVERGENCE_RISK if chan_structure.divergence_type == "top" else PrimarySetupCode.CHAN_SELL_RISK
        return emit("SELL_T_TIMING", Signal.SELL_T, setup, reasons, warnings, RiskEnforcement.SOFT)

    high_pressure_sell, high_pressure_reasons = _high_pressure_sell_setup(
        force=force,
        sell_pressure=sell_pressure,
        levels=levels,
        daily_context=daily_context,
        intraday_context=intraday_context,
        capital_flow=capital_flow,
        breakout_setup=breakout_setup,
        profile=profile,
    )
    if high_pressure_sell:
        reasons.extend(
            [
                "高位压力卖 T 优先：涨幅已经明显，价格接近当日/近端压力，买盘边际转弱。",
                "该信号优先级高于突破买入；强势日也允许先卖出部分 T 仓锁定波动收益。",
                *high_pressure_reasons,
            ]
        )
        if not daily_context.buyback_allowed:
            warnings.append("日线背景不允许买回；本次只给卖出 T 参考，不给倒 T 买回价。")
        return emit(
            "SELL_T_TIMING",
            Signal.SELL_T,
            PrimarySetupCode.PRESSURE_SELL_T,
            reasons + list(sell_pressure.reasons)[:2],
            list(force.reasons)[:1],
        )

    if breakout_setup.breakout_confirmed and not intraday_context.late_session:
        breakout_level = _fmt_optional_price(breakout_setup.breakout_level)
        trigger_price = _fmt_optional_price(breakout_setup.trigger_price)
        reasons.extend(
            [
                "强势启动买点：价格放量突破近端压力，盘中加速度和分时承接同时出现。",
                "该信号不是低吸做 T，而是突破跟随试错；仓位由强度和 Kelly 折扣控制。",
                f"突破分 {breakout_setup.score:.1f}，突破位 {breakout_level}，触发价 {trigger_price}。",
                f"当日涨幅 {breakout_setup.day_return:.1%}，最近 5 分钟组涨幅 {breakout_setup.recent_return:.1%}，量能 {breakout_setup.volume_expansion:.2f} 倍。",
            ]
        )
        if sell_pressure.score >= 74.0:
            warnings.append("突破时卖压不低，只适合试错仓；若跌回突破位下方，执行层必须止损。")
        return emit(
            "BREAKOUT_BUY_TIMING",
            Signal.BUY_T,
            PrimarySetupCode.BREAKOUT_CONFIRMED,
            reasons + list(breakout_setup.reasons),
            list(capital_flow.reasons)[:1],
        )

    early_start_setup = (
        breakout_setup.state == "EARLY_START"
        and daily_context.allow_t
        and daily_context.fundamental_score >= 60.0
        and not intraday_context.late_session
        and force_buy_edge >= (52.0 if flow_confirmed else 56.0)
        and buy_strength_score >= max(58.0, profile.probe_buy_strength_threshold - 8.0)
        and sell_pressure.score <= 74.0
        and (capital_flow.score >= 50.0 or flow_confirmed or volume_price_constructive)
        and trend_probability.down_1d < 0.60
    )
    if early_start_setup:
        breakout_level = _fmt_optional_price(breakout_setup.breakout_level)
        trigger_price = _fmt_optional_price(breakout_setup.trigger_price)
        reasons.extend(
            [
                "强势启动早期买点：价格正在靠近或轻微越过近端压力，但尚未完成突破确认。",
                "该信号只用于提前试探，不允许直接按满攻处理；后续只有放量站稳才升级为 BREAKOUT_BUY_TIMING。",
                f"启动分 {breakout_setup.score:.1f}，买入强度 {buy_strength_score:.1f}，资金流 {capital_flow.score:.1f}，量价 {volume_price_structure.score:.1f}。",
                f"触发价 {trigger_price}，突破位 {breakout_level}。",
            ]
        )
        return emit(
            "BUY_T_TIMING",
            Signal.BUY_T,
            PrimarySetupCode.STRONG_LAUNCH_FOLLOW,
            reasons + list(breakout_setup.reasons)[:3],
            list(capital_flow.reasons)[:1],
        )

    if breakout_setup.pre_breakout_watch:
        breakout_level = _fmt_optional_price(breakout_setup.breakout_level)
        trigger_price = _fmt_optional_price(breakout_setup.trigger_price)
        return emit(
            "WATCH_BREAKOUT_NEXT_DAY",
            None,
            None,
            [
                "次日强势突破预警：当前离压力位很近，但尚未确认突破。",
                "明日只在放量站上触发价、分时不跌回均价线时，才升级为 BREAKOUT_BUY_TIMING。",
                f"突破位 {breakout_level}，触发价 {trigger_price}，预警分 {breakout_setup.score:.1f}。",
                *list(breakout_setup.reasons)[:3],
            ],
            ["这是提前一天的候选预警，不是买入信号；不能在未突破前提前重仓。"],
        )

    force_reversal_setup = (
        daily_context.allow_t
        and daily_context.fundamental_score >= 60.0
        and force_buy_edge >= 68.0
        and (force.force_ratio >= 1.12 or (volume_price_strong and force.weighted_score >= 46.0))
        and certainty.score >= 48.0
        and sell_pressure.score <= 76.0
        and (chan_buy_point or near_support or intraday_context.rebound_from_low or trend_state != TrendState.DOWNTREND)
        and multi_period_trend.monthly_state != "DOWN"
        and buy_strength_score >= profile.probe_buy_strength_threshold
        and _probability_allows_attack(trend_probability, mode="force_reversal")
    )

    if trend_state == TrendState.DOWNTREND and not force_reversal_setup:
        return emit(
            "STOP_T_WAIT",
            Signal.STOP_T,
            PrimarySetupCode.STOP_T,
            ["5 分钟趋势进入空头结构，暂停正 T，只观察或等更低支撑。"],
            ["趋势破位时不要把 T 仓变成底仓。"],
            RiskEnforcement.SOFT,
        )

    if near_support and not daily_context.allow_t and not trend_5_20_allows_pullback:
        return emit(
            "WAIT_DAILY_WEAK",
            None,
            None,
            [
                "价格接近支撑区，但日线背景偏弱，禁止把分钟线低点当成买 T 机会。",
                "需要等日线重新站回近端支撑，或次日重新计算新的支撑区。",
                *list(daily_context.reasons)[:2],
            ],
            ["时间尺度门控已拦截 BUY_T：日线不允许，分钟线信号只保留为观察。"],
        )

    if force_reversal_setup and not intraday_context.late_session:
        reasons.extend(
            [
                "退神买盘优势触发：买量/卖量估算比和关注度正反馈同时改善。",
                "该信号允许在趋势刚转强或空头末端做进攻试探，但仍受日线和基本面约束。",
                f"退神买盘优势分 {force_buy_edge:.1f}，force_ratio {force.force_ratio:.2f}，量价 {volume_price_structure.score:.1f}，买入强度 {buy_strength_score:.1f}。",
                f"记忆 {memory.score:.1f}，资金流 {capital_flow.score:.1f}，最大可卖量压力 {sell_pressure.score:.1f}。",
                f"概率门控通过：1日上行 {trend_probability.up_1d:.1%}，3日上行 {trend_probability.up_3d:.1%}，1日下行 {trend_probability.down_1d:.1%}。",
            ]
        )
        if trend_state == TrendState.DOWNTREND:
            warnings.append("这是逆势转强试探：若后续无法站回支撑或买卖力回落，执行层必须按 STOP_T 处理。")
        return emit(
            "BUY_T_TIMING",
            Signal.BUY_T,
            PrimarySetupCode.FORCE_REVERSAL_PROBE,
            reasons + list(force.reasons),
            list(attention.reasons)[:1],
        )

    low_buy_setup = (
        (near_support or chan_structure.buy_point_type in {"buy1", "buy2", "range_buy"})
        and levels["risk_reward_ratio"] >= 1.05
        and (force.force_ratio >= max(0.85, profile.buy_force_threshold - 0.18) or volume_price_constructive)
        and certainty.score >= max(42.0, profile.buy_certainty_threshold - 8.0)
        and sell_pressure.score <= min(84.0, profile.buy_sell_pressure_max + 6.0)
        and multi_period_trend.score >= 40.0
        and (capital_flow.score >= 38.0 or volume_price_structure.low_volume_pullback_score >= 70.0)
        and buy_strength_score >= profile.probe_buy_strength_threshold
        and _probability_allows_attack(trend_probability, mode="low_buy")
    )

    if low_buy_setup:
        if not daily_context.allow_t and not trend_5_20_allows_pullback:
            return emit(
                "WAIT_DAILY_WEAK",
                None,
                None,
                [
                    "5 分钟到达支撑区，但日线背景偏弱，禁止把盘中买点升级为买回或补仓。",
                    "需要等日线重新站回近端支撑，或次日重新计算新的支撑区。",
                    *list(daily_context.reasons)[:2],
                ],
                ["时间尺度门控已拦截 BUY_T：日线不允许，分钟线信号只保留为观察。"],
            )
        if not low_buy_confirmed and buy_strength_score < profile.probe_buy_strength_threshold + 6.0:
            return emit(
                "WAIT_CONFIRMATION",
                None,
                None,
                [
                    "价格接近支撑区，但 5 分钟承接没有确认，先观察。",
                    "必须看到收回支撑、反抽离开低点、买卖力继续改善后，才允许动手。",
                    *list(intraday_context.reasons)[:2],
                ],
                ["到达参考价不等于可以买回；本次信号被分时确认门控拦截。"],
            )
        if intraday_context.late_session and not daily_context.allow_overnight:
            return emit(
                "WAIT_LATE_SESSION",
                None,
                None,
                [
                    "14:30 后到达买点，但日线不支持隔夜，尾盘不追买回。",
                    "若次日低开跌破今日支撑，原买回逻辑作废。",
                ],
                ["尾盘买回需要日线强背景；当前只允许次日重新确认。"],
            )
        reasons.extend(
            [
                "买量/卖量估算比大于 1，买盘力量占优。",
                "价格靠近支撑区，信号强度达到试探买 T 阈值。",
                f"日线背景 {daily_context.state}，D_score={daily_context.score}，F={daily_context.fundamental_score}，仓位系数 {daily_context.position_multiplier:.2f}。",
                f"多周期趋势 {multi_period_trend.score:.1f}，资金流 {capital_flow.score:.1f}。",
                f"买入信号强度 {buy_strength_score:.1f}，后续用 Kelly 折扣决定 T 仓大小。",
                f"概率门控通过：1日上行 {trend_probability.up_1d:.1%}，3日上行 {trend_probability.up_3d:.1%}，1日下行 {trend_probability.down_1d:.1%}。",
            ]
        )
        if not low_buy_confirmed:
            warnings.append("这是试探型买 T：分时承接未完全确认，Kelly 仓位会自动压低。")
        return emit(
            "BUY_T_TIMING",
            Signal.BUY_T,
            PrimarySetupCode.PULLBACK_LOW_BUY,
            reasons + list(force.reasons),
            list(attention.reasons)[:1],
        )

    mid_trend_pullback_setup = (
        trend_5_20_allows_pullback
        and (intraday_context.support_confirmed or intraday_context.rebound_from_low or near_support)
        and levels["risk_reward_ratio"] >= 1.20
        and force.force_ratio >= 1.0
        and certainty.score >= 48.0
        and sell_pressure.score <= 70.0
        and capital_flow.score >= 46.0
        and multi_period_trend.score >= 48.0
        and trend_probability.down_1d < 0.58
    )
    if mid_trend_pullback_setup:
        reasons.extend(
            [
                "5-20 日趋势回踩买点：不再只看单日强弱，先确认 20 日趋势仍支持，再用 5 分钟支撑做买点。",
                f"5-20 日状态 {multi_period_trend.trend_5_20_state}，5 日收益 {multi_period_trend.return_5d:.1%}，20 日收益 {multi_period_trend.return_20d:.1%}。",
                f"分时状态 {intraday_context.state}，盈亏比 {levels['risk_reward_ratio']:.2f}，资金流 {capital_flow.score:.1f}。",
            ]
        )
        if not daily_context.allow_t:
            warnings.append("单日日线背景偏弱，但 5-20 日趋势仍处于上行回踩，允许小仓真实买点。")
        return emit(
            "BUY_T_TIMING",
            Signal.BUY_T,
            PrimarySetupCode.TREND_PULLBACK_FOLLOW,
            reasons + list(multi_period_trend.reasons)[:2],
            list(capital_flow.reasons)[:1],
        )

    trend_follow_setup = (
        (daily_context.state == "STRONG" or (daily_context.state == "NEUTRAL" and force_buy_edge >= (64.0 if flow_confirmed else 70.0)))
        and (trend_state == TrendState.UPTREND or chan_structure.buy_point_type == "buy3")
        and daily_context.fundamental_score >= 65.0
        and not (intraday_context.late_session and intraday_context.resistance_confirmed and near_resistance)
        and certainty.score >= (46.0 if flow_confirmed else max(48.0, profile.buy_certainty_threshold - 4.0))
        and (force.force_ratio >= 0.92 or force.weighted_score >= 48.0 or capital_flow.short_flow_ratio > 0.05 or flow_confirmed or volume_price_strong)
        and sell_pressure.score <= (82.0 if flow_confirmed else min(profile.strong_trend_sell_pressure_threshold, 78.0))
        and multi_period_trend.score >= (50.0 if flow_confirmed else 54.0)
        and multi_period_trend.monthly_state != "DOWN"
        and (capital_flow.score >= 42.0 or flow_confirmed or volume_price_constructive)
        and buy_strength_score >= profile.probe_buy_strength_threshold
        and (
            not intraday_context.resistance_confirmed
            or (force.force_ratio >= 1.18 and capital_flow.short_flow_ratio > 0.10)
            or (flow_confirmed and sell_pressure.score < 68.0)
        )
        and (
            _probability_allows_attack(trend_probability, mode="trend_follow")
            or (flow_confirmed and trend_probability.up_1d >= 0.52 and trend_probability.down_3d < 0.60)
        )
    )
    if trend_follow_setup:
        reasons.extend(
            [
                "强趋势跟随买点：日线、5 分钟和多周期趋势同时保持向上。",
                "该信号不是低吸支撑，而是在趋势未破坏时提高主动仓位参与。",
                f"买入信号强度 {buy_strength_score:.1f}，资金流 {capital_flow.score:.1f}，量价 {volume_price_structure.score:.1f}，卖压 {sell_pressure.score:.1f}。",
                f"概率门控通过：1日上行 {trend_probability.up_1d:.1%}，3日上行 {trend_probability.up_3d:.1%}，3日下行 {trend_probability.down_3d:.1%}。",
                "后续若出现 SELL_T / STOP_T / WAIT_DAILY_WEAK，执行层会卖出主动仓位。",
            ]
        )
        setup = PrimarySetupCode.THIRD_BUY_FOLLOW if chan_structure.buy_point_type == "buy3" else PrimarySetupCode.TREND_FOLLOW
        return emit(
            "BUY_T_TIMING",
            Signal.BUY_T,
            setup,
            reasons + list(force.reasons),
            list(capital_flow.reasons)[:1],
        )

    attention_feedback_setup = (
        daily_context.allow_t
        and not intraday_context.late_session
        and not near_resistance
        and force_buy_edge >= 64.0
        and (force.force_ratio >= 1.04 or volume_price_strong)
        and attention.score >= 60.0
        and certainty.score >= 48.0
        and sell_pressure.score <= 72.0
        and not chan_sell_point
        and (capital_flow.score >= 46.0 or flow_confirmed or volume_price_constructive)
        and multi_period_trend.monthly_state != "DOWN"
        and buy_strength_score >= profile.probe_buy_strength_threshold
        and _probability_allows_attack(trend_probability, mode="attention_feedback")
    )
    if attention_feedback_setup:
        reasons.extend(
            [
                "市场关注度正反馈买点：关注度、买卖力和资金流同步改善。",
                "该信号更贴近退神理论里的市场关注资金量上升，不要求必须回踩到最低支撑。",
                f"退神买盘优势分 {force_buy_edge:.1f}，关注度 {attention.score:.1f}，force_ratio {force.force_ratio:.2f}，量价 {volume_price_structure.score:.1f}。",
                f"概率门控通过：1日上行 {trend_probability.up_1d:.1%}，3日上行 {trend_probability.up_3d:.1%}，1日下行 {trend_probability.down_1d:.1%}。",
            ]
        )
        return emit(
            "BUY_T_TIMING",
            Signal.BUY_T,
            PrimarySetupCode.ATTENTION_FEEDBACK_FOLLOW,
            reasons + list(force.reasons),
            list(attention.reasons)[:1],
        )

    range_probe_setup = (
        daily_context.allow_t
        and trend_state == TrendState.RANGE
        and not intraday_context.late_session
        and not near_resistance
        and (
            intraday_context.near_support
            or intraday_context.rebound_from_low
            or current <= support + 1.65 * levels["atr"]
            or chan_structure.buy_point_type == "range_buy"
        )
        and levels["risk_reward_ratio"] >= 1.20
        and (force.force_ratio >= 0.88 or force.weighted_score >= 46.0 or capital_flow.short_flow_ratio > 0.05 or volume_price_constructive)
        and certainty.score >= 44.0
        and sell_pressure.score <= 74.0
        and multi_period_trend.score >= 42.0
        and (capital_flow.score >= 42.0 or volume_price_constructive)
        and buy_strength_score >= profile.probe_buy_strength_threshold
        and _probability_allows_attack(trend_probability, mode="range_probe")
    )
    if range_probe_setup:
        reasons.extend(
            [
                "震荡试探买点：价格在箱体下半区或从低位反抽，允许更高频 T 仓试探。",
                "该信号仓位上限低于强趋势，只用于震荡区间低买高卖。",
                f"买入信号强度 {buy_strength_score:.1f}，盈亏比 {levels['risk_reward_ratio']:.2f}，资金流 {capital_flow.score:.1f}。",
                f"概率门控通过：1日上行 {trend_probability.up_1d:.1%}，3日上行 {trend_probability.up_3d:.1%}，1日下行 {trend_probability.down_1d:.1%}。",
                "如果后续跌破支撑或日线转弱，执行层会按 STOP_T / WAIT_DAILY_WEAK 卖出主动仓位。",
            ]
        )
        return emit(
            "BUY_T_TIMING",
            Signal.BUY_T,
            PrimarySetupCode.RANGE_LOW_BUY,
            reasons + list(force.reasons),
            list(capital_flow.reasons)[:1],
        )

    if (force.force_ratio <= profile.sell_force_threshold or sell_pressure.score >= profile.sell_pressure_threshold) and near_resistance:
        if _strong_trend_protects_sell(
            force=force,
            sell_pressure=sell_pressure,
            trend_state=trend_state,
            daily_context=daily_context,
            intraday_context=intraday_context,
            profile=profile,
        ):
            return emit(
                "WAIT_STRONG_TREND",
                None,
                None,
                [
                    "日线和 5 分钟仍处于强趋势，压力区信号先降级为观察。",
                    "当前卖压未达到强卖压阈值，不适合主动倒 T，避免卖飞底仓。",
                    "若已有正 T 仓，可只按计划小比例落袋；若只有底仓，等待放量滞涨或趋势衰竭再处理。",
                ],
                [
                    "强趋势保护已拦截 SELL_T_TIMING：上涨趋势里不能只因接近压力位就倒 T。",
                    *list(sell_pressure.reasons)[:1],
                ],
            )
        reasons.extend(
            [
                "卖盘力量或最大可卖量压力偏高。",
                "价格接近压力区，适合考虑卖 T 或倒 T。",
                "卖出后若继续上涨，不追高纠错。",
            ]
        )
        if not daily_context.buyback_allowed:
            warnings.append("日线背景不允许买回；本次只给卖出 T 参考，不给倒 T 买回价。")
        elif intraday_context.late_session and not daily_context.allow_overnight:
            warnings.append("尾盘且日线不支持隔夜，倒 T 买回价需要次日重新计算。")
        elif daily_context.position_multiplier < 1.0:
            warnings.append(f"日线背景只允许小仓买回，建议仓位系数 {daily_context.position_multiplier:.2f}。")
        return emit(
            "SELL_T_TIMING",
            Signal.SELL_T,
            PrimarySetupCode.PRESSURE_SELL_T,
            reasons + list(sell_pressure.reasons)[:2],
            list(force.reasons)[:1],
        )

    if memory.score <= 38 and sell_pressure.score >= 60:
        warnings.append("相似情境记忆偏负，且卖压不低，当前不适合主动买 T。")
    if multi_period_trend.score < 45.0:
        warnings.append("5日/周线/月线趋势合成偏弱，暂不放大买入信号。")
    if capital_flow.score < 42.0:
        warnings.append("成交额方向代理显示资金净流偏弱，买入信号降级观察。")
    if not daily_context.allow_t:
        warnings.append("日线背景偏弱，分钟线到支撑也只观察，不主动买回。")
    if trend_probability.state == "DOWN_RISK":
        warnings.append("概率门控显示下跌风险偏高，退神买盘优势不放大为买入。")

    reasons.extend(
        [
            "买卖力量没有形成清晰优势，默认等待。",
            "只有日线允许、接近支撑或压力且信号强度达到阈值后，才考虑手动操作。",
        ]
    )
    return emit("WAIT", None, None, reasons + list(certainty.reasons)[:1] + list(memory.reasons)[:1], warnings)


def _strong_trend_protects_sell(
    *,
    force: ForceRatioEstimate,
    sell_pressure: SellPressureEstimate,
    trend_state: TrendState,
    daily_context: DailyContext,
    intraday_context: IntradayContext,
    profile: CoscoProfile,
) -> bool:
    """Block reverse-T style sell signals when trend evidence is still constructive."""
    if trend_state != TrendState.UPTREND:
        return False
    if daily_context.state != "STRONG" or daily_context.score < 70.0:
        return False
    if sell_pressure.score >= profile.strong_trend_sell_pressure_threshold:
        return False
    if intraday_context.resistance_confirmed and force.force_ratio <= 0.05 and sell_pressure.score >= 68.0:
        return False
    return True


def _high_pressure_sell_setup(
    *,
    force: ForceRatioEstimate,
    sell_pressure: SellPressureEstimate,
    levels: dict[str, float],
    daily_context: DailyContext,
    intraday_context: IntradayContext,
    capital_flow: CapitalFlowEstimate,
    breakout_setup: BreakoutSetup,
    profile: CoscoProfile,
) -> tuple[bool, list[str]]:
    current = levels["current"]
    atr = max(levels["atr"], current * 0.002)
    resistance = levels["resistance"]
    near_pressure = (
        current >= resistance - max(0.85 * atr, current * 0.003)
        or intraday_context.near_resistance
    )
    fast_gain = breakout_setup.day_return >= 0.033
    extended_breakout = breakout_setup.breakout_confirmed and breakout_setup.day_return >= 0.038
    force_fading = force.force_ratio <= 0.35 or force.weighted_score <= 48.0 or capital_flow.short_flow_ratio <= -0.04
    pressure_visible = sell_pressure.score >= 52.0 or intraday_context.resistance_confirmed
    high_volume_stall = (
        intraday_context.resistance_confirmed
        and sell_pressure.score >= 58.0
        and breakout_setup.volume_expansion >= 1.25
        and breakout_setup.recent_return <= 0.0025
    )
    confirmed_inflow = (
        _capital_flow_confirms_buy(capital_flow, min_score=62.0)
        and force.force_ratio >= 0.55
        and force.weighted_score >= 46.0
        and breakout_setup.recent_return >= -0.0015
        and sell_pressure.score < 74.0
    )
    distribution_hint = (
        capital_flow.short_flow_ratio <= 0.60
        or capital_flow.medium_flow_ratio <= 0.0
        or sell_pressure.score >= 60.0
        or high_volume_stall
    )
    monotonic_inflow = (
        capital_flow.short_flow_ratio >= 0.85
        and capital_flow.medium_flow_ratio >= 0.35
        and breakout_setup.recent_return >= 0.003
        and sell_pressure.score < 60.0
    ) or confirmed_inflow
    daily_allows_sell = daily_context.state in {"STRONG", "NEUTRAL", "INSUFFICIENT"}
    trigger = (
        daily_allows_sell
        and near_pressure
        and pressure_visible
        and force_fading
        and (fast_gain or extended_breakout or high_volume_stall)
        and distribution_hint
        and not monotonic_inflow
        and sell_pressure.score < 88.0
    )
    if not trigger:
        return False, []
    reasons = [
        f"当日涨幅 {breakout_setup.day_return:.1%}，现价 {current:.3f} 接近压力 {resistance:.3f}。",
        f"force_ratio={force.force_ratio:.2f}，卖压={sell_pressure.score:.1f}，短周期资金流={capital_flow.short_flow_ratio:.1%}。",
        f"强趋势卖压阈值={profile.strong_trend_sell_pressure_threshold:.1f}，当前按高位压力优先处理。",
    ]
    return True, reasons


def _fmt_optional_price(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.3f}"


def _tuishen_force_buy_edge(
    *,
    force: ForceRatioEstimate,
    attention: AttentionScore,
    certainty: CertaintyScore,
    memory: MemoryScore,
    sell_pressure: SellPressureEstimate,
    multi_period_trend: MultiPeriodTrend,
    capital_flow: CapitalFlowEstimate,
    volume_price_structure: VolumePriceStructure | None = None,
) -> float:
    force_component = clamp((force.force_ratio - 0.75) / 0.75 * 100.0, 0.0, 100.0)
    sellable_inverse = clamp(100.0 - sell_pressure.score, 0.0, 100.0)
    volume_price_score = 50.0 if volume_price_structure is None else volume_price_structure.score
    score = (
        0.18 * force_component
        + 0.18 * volume_price_score
        + 0.16 * attention.score
        + 0.15 * certainty.score
        + 0.11 * memory.score
        + 0.09 * sellable_inverse
        + 0.08 * capital_flow.score
        + 0.05 * multi_period_trend.score
    )
    if capital_flow.confirmation_state == "CONFIRMED_INFLOW":
        score += 4.0
    elif capital_flow.confirmation_state == "CONFIRMED_OUTFLOW":
        score -= 4.0
    if volume_price_structure is not None:
        if volume_price_structure.volume_breakout_score >= 72.0 or volume_price_structure.low_volume_pullback_score >= 72.0:
            score += 5.0
        if volume_price_structure.post_breakout_volume_persistence_score >= 72.0:
            score += 4.0
        if volume_price_structure.high_volume_stall_score >= 70.0:
            score -= clamp((volume_price_structure.high_volume_stall_score - 65.0) * 0.20, 0.0, 8.0)
        if volume_price_structure.price_up_volume_down_score >= 72.0:
            score -= clamp((volume_price_structure.price_up_volume_down_score - 68.0) * 0.16, 0.0, 6.0)
    return round(clamp(score, 0.0, 100.0), 2)
