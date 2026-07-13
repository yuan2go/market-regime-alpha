"""COSCO 5-minute manual timing signal engine.

This module produces manual reference prices and timing signals only. It does
not create broker orders and must not be used as an automated order executor.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
import time
from typing import Any

from market_regime_alpha.data_sources.a_share_bars import MultiSourceDataError, fetch_a_share_5min_with_fallback
from market_regime_alpha.data_sources.tushare_client import TushareConfigError, TushareDataError, build_tushare_client
from market_regime_alpha.dividend_t.attention import AttentionScore, estimate_attention
from market_regime_alpha.dividend_t.buy_point_quality import (
    BUY_POINT_SUBTYPE_BREAKOUT_WATCH,
    BUY_POINT_SUBTYPE_PULLBACK_LOW_BUY,
    buy_point_overheat_reasons,
    classify_buy_point_subtype,
)
from market_regime_alpha.dividend_t.certainty import CertaintyScore, estimate_certainty
from market_regime_alpha.dividend_t.chan import BUY_POINTS, SELL_POINTS, ChanStructure, analyze_chan_structure
from market_regime_alpha.dividend_t.cosco_profile import COSCO_A_SYMBOL, CoscoProfile
from market_regime_alpha.dividend_t.dynamic_weights import build_dynamic_weights
from market_regime_alpha.dividend_t.force_ratio import ForceRatioEstimate, estimate_force_ratio
from market_regime_alpha.dividend_t.indicators import add_daily_indicators
from market_regime_alpha.dividend_t.memory import MemoryScore, classify_current_setup, estimate_memory
from market_regime_alpha.dividend_t.models import Signal, TrendState
from market_regime_alpha.dividend_t.macd import BarInterval, MACDResult
from market_regime_alpha.dividend_t.position_sizing import PositionBudget
from market_regime_alpha.dividend_t.scoring import clamp
from market_regime_alpha.dividend_t.sell_pressure import SellPressureEstimate, estimate_sell_pressure
from market_regime_alpha.dividend_t.storage import ResearchStore
from market_regime_alpha.dividend_t.cosco_timing_breakout import _breakout_setup
from market_regime_alpha.dividend_t.cosco_timing_capital_flow import _capital_flow_confirms_buy, _capital_flow_estimate
from market_regime_alpha.dividend_t.cosco_timing_daily import _daily_context, _multi_period_trend
from market_regime_alpha.dividend_t.cosco_timing_intraday import _intraday_context, _trend_state
from market_regime_alpha.dividend_t.cosco_timing_manual import _manual_action, _tuishen_force_buy_edge
from market_regime_alpha.dividend_t.cosco_timing_signal import _signal_strength
from market_regime_alpha.dividend_t.cosco_timing_types import (
    BreakoutSetup,
    CapitalFlowEstimate,
    CoscoTimingSnapshot,
    CoscoTimingUnavailable,
    DailyContext,
    IntradayContext,
    MarketRegime,
    MultiPeriodTrend,
    ReferencePrices,
    TrendProbability,
    TimingDecisionTrace,
    VolumePriceStructure,
    apply_timing_macd_policy,
    candidate_trace_fields,
)
from market_regime_alpha.dividend_t.signal_intent import MACDPolicyConfig, MACDPolicyState
from market_regime_alpha.dividend_t.tuishen_volume_price import estimate_volume_price_structure



class CoscoTimingEngine:
    def __init__(
        self,
        profile: CoscoProfile | None = None,
        fundamental_resolver: Any | None = None,
        macd_policy_config: MACDPolicyConfig | None = None,
    ) -> None:
        self.profile = profile or CoscoProfile()
        self.fundamental_resolver = fundamental_resolver
        self.macd_policy_config = macd_policy_config or MACDPolicyConfig()

    def evaluate(
        self,
        bars: Any,
        *,
        data_source: str = "input_5min_bars",
        is_realtime: bool = False,
        require_fresh: bool = False,
        freshness_limit_minutes: float = 10.0,
        generated_at: datetime | None = None,
        macd_result: MACDResult | None = None,
    ) -> CoscoTimingSnapshot:
        data = _prepare_bars(bars)
        if len(data) < 30:
            raise ValueError("at least 30 5-minute bars are required for COSCO timing")

        evaluation_time = (generated_at or datetime.now()).replace(microsecond=0)
        last_bar_time = data["timestamp"].iloc[-1]
        timestamp = str(last_bar_time)
        data_age_minutes = _data_age_minutes(last_bar_time, evaluation_time)
        data_fresh = data_age_minutes <= freshness_limit_minutes
        freshness_status = "fresh" if data_fresh else "stale"
        profile = _profile_for_data(self.profile, data, self.fundamental_resolver)
        levels = _reference_levels(data)
        daily_context = _daily_context(data, profile=profile)
        intraday_context = _intraday_context(data, levels=levels)
        multi_period_trend = _multi_period_trend(data)
        capital_flow = _capital_flow_estimate(data)
        volume_price_structure = estimate_volume_price_structure(data)
        chan_structure = analyze_chan_structure(data, level="5m")
        setup = classify_current_setup(data)
        attention = estimate_attention(data)
        memory = estimate_memory(data, setup=setup)
        sell_pressure = estimate_sell_pressure(data)
        certainty = estimate_certainty(
            data,
            profile=profile,
            attention=attention,
            memory=memory,
            sell_pressure=sell_pressure,
        )
        trend_state = _trend_state(data)
        weights = build_dynamic_weights(
            trend_state=trend_state,
            memory_score=memory.score,
            sell_pressure_score=sell_pressure.score,
        )
        force = estimate_force_ratio(
            attention=attention,
            certainty=certainty,
            memory=memory,
            sell_pressure=sell_pressure,
            risk_reward_ratio=levels["risk_reward_ratio"],
            current_amount=levels["current_amount"],
            weights=weights,
        )
        trend_probability = _trend_probability(
            force=force,
            attention=attention,
            certainty=certainty,
            memory=memory,
            sell_pressure=sell_pressure,
            trend_state=trend_state,
            daily_context=daily_context,
            intraday_context=intraday_context,
            multi_period_trend=multi_period_trend,
            capital_flow=capital_flow,
            volume_price_structure=volume_price_structure,
            chan_structure=chan_structure,
            risk_reward_ratio=levels["risk_reward_ratio"],
        )
        breakout_setup = _breakout_setup(
            data,
            levels=levels,
            force=force,
            attention=attention,
            certainty=certainty,
            sell_pressure=sell_pressure,
            trend_state=trend_state,
            daily_context=daily_context,
            intraday_context=intraday_context,
            multi_period_trend=multi_period_trend,
            capital_flow=capital_flow,
            volume_price_structure=volume_price_structure,
            trend_probability=trend_probability,
            chan_structure=chan_structure,
        )
        market_regime = _market_regime(
            force=force,
            attention=attention,
            certainty=certainty,
            memory=memory,
            sell_pressure=sell_pressure,
            trend_state=trend_state,
            daily_context=daily_context,
            intraday_context=intraday_context,
            multi_period_trend=multi_period_trend,
            capital_flow=capital_flow,
            volume_price_structure=volume_price_structure,
            trend_probability=trend_probability,
            breakout_setup=breakout_setup,
            chan_structure=chan_structure,
            profile=profile,
        )
        candidate = _manual_action(
            force=force,
            attention=attention,
            certainty=certainty,
            memory=memory,
            sell_pressure=sell_pressure,
            trend_state=trend_state,
            levels=levels,
            daily_context=daily_context,
            intraday_context=intraday_context,
            multi_period_trend=multi_period_trend,
            capital_flow=capital_flow,
            volume_price_structure=volume_price_structure,
            trend_probability=trend_probability,
            breakout_setup=breakout_setup,
            chan_structure=chan_structure,
            profile=profile,
            decision_bar_time=timestamp,
        )
        raw_candidate_action = candidate.action
        action = raw_candidate_action
        reasons = list(candidate.reasons)
        warnings = list(candidate.warnings)
        initial_buy_point_subtype = classify_buy_point_subtype(candidate.primary_setup_code)
        overheat_reasons = buy_point_overheat_reasons(
            trend_state=trend_state.value,
            volume_price_state=volume_price_structure.state,
            volume_price_score=volume_price_structure.score,
            volume_breakout_score=volume_price_structure.volume_breakout_score,
            high_volume_stall_score=volume_price_structure.high_volume_stall_score,
            capital_flow_confirmation_state=capital_flow.confirmation_state,
            up_probability_1d=trend_probability.up_1d,
            pretrade_volume_ratio_to_prev=volume_price_structure.volume_expansion_ratio,
            breakout_confirmed=breakout_setup.breakout_confirmed,
            breakout_score=breakout_setup.score,
        )
        if action == "BREAKOUT_BUY_TIMING":
            action = "WATCH_BREAKOUT_NEXT_DAY"
            reasons = [
                "5 日命中率优先：突破买点默认降级为观察点，等待回踩不破或下一交易日重新确认。",
                *list(reasons),
            ]
            warnings = [
                *list(warnings),
                "突破类买点当前历史 5 日命中率不足，暂不作为真实买点输出。",
            ]
        elif candidate.candidate_signal is Signal.BUY_T and overheat_reasons:
            action = "WAIT_CONFIRMATION"
            reasons = [
                "5 日命中率优先：原始买点触发，但量价/概率结构显示追涨过热，先等待回踩或站稳确认。",
                f"原始主 setup={candidate.primary_setup_code.value if candidate.primary_setup_code else 'none'}。",
                *list(overheat_reasons)[:3],
                *list(reasons),
            ]
            warnings = [
                *list(warnings),
                "过热质量过滤已拦截 BUY_T；原始 setup 和 intent 仅保留在 DecisionTrace。",
            ]
        elif action == "BUY_T_TIMING" and initial_buy_point_subtype != BUY_POINT_SUBTYPE_PULLBACK_LOW_BUY:
            action = "WAIT_CONFIRMATION"
            reasons = [
                "5 日命中率优先：非支撑/回踩型买点先降级为等待确认，不计入真实买点。",
                f"原始买点子类型={initial_buy_point_subtype}，需要回踩支撑、分时收回或低吸结构确认后再升级。",
                *list(reasons),
            ]
            warnings = [
                *list(warnings),
                "买点质量过滤已拦截：当前仅保留 pullback_low_buy 作为真实买点。",
            ]
        elif action == "BUY_T_TIMING" and not _trend_5_20_allows_buy(multi_period_trend):
            action = "WAIT_CONFIRMATION"
            reasons = [
                "5-20 日趋势过滤：中期趋势没有支持真实买点，不能只凭单日或盘中支撑推断买入。",
                f"5-20 日状态={multi_period_trend.trend_5_20_state}，5 日收益={multi_period_trend.return_5d:.1%}，20 日收益={multi_period_trend.return_20d:.1%}。",
                *list(reasons),
            ]
            warnings = [
                *list(warnings),
                "买点趋势过滤已拦截：需要 5-20 日趋势向上或上升趋势内回踩，才输出真实买点。",
            ]
        elif action == "BUY_T_TIMING" and not _pullback_buy_quality_allows_5d(volume_price_structure, capital_flow):
            action = "WAIT_CONFIRMATION"
            reasons = [
                "5 日命中率优先：真实买点必须是低量回踩，并且有 VWAP 承接或资金确认流入。",
                f"量价状态={volume_price_structure.state}，VWAP 承接分={volume_price_structure.vwap_support_score:.1f}，资金确认={capital_flow.confirmation_state}。",
                *list(reasons),
            ]
            warnings = [
                *list(warnings),
                "买点质量过滤已拦截：需要 LOW_VOLUME_PULLBACK，且 VWAP 承接 >=70 或资金确认流入。",
            ]
        elif action == "SELL_T_TIMING":
            action = "WAIT_CONFIRMATION"
            reasons = [
                "5 日命中率优先：普通卖 T 的历史 5 日命中率没有过线，先降级为观察点。",
                f"量价状态={volume_price_structure.state}，资金确认={capital_flow.confirmation_state}，卖压={sell_pressure.score:.1f}，概率状态={trend_probability.state}。",
                *list(reasons),
            ]
            warnings = [
                *list(warnings),
                "卖点质量过滤已拦截：SELL_T_TIMING 暂不计入真实卖点，等待 STOP_T_WAIT 或结构破位确认。",
            ]
        elif action == "STOP_T_WAIT" and not _stop_wait_quality_allows_5d(
            capital_flow=capital_flow,
            volume_price_structure=volume_price_structure,
        ):
            action = "WAIT_CONFIRMATION"
            reasons = [
                "5 日命中率优先：STOP_T_WAIT 只有在资金不背离且 VWAP 承接转弱时才作为真实卖点。",
                f"资金确认={capital_flow.confirmation_state}，资金分={capital_flow.score:.1f}，VWAP 承接分={volume_price_structure.vwap_support_score:.1f}。",
                *list(reasons),
            ]
            warnings = [
                *list(warnings),
                "卖点质量过滤已拦截：STOP_T_WAIT 需要资金不背离且 VWAP 承接 < 50。",
            ]
        elif action == "WAIT_DAILY_WEAK":
            action = "WAIT_CONFIRMATION"
            reasons = [
                "5 日命中率优先：日线弱只作为风险观察和禁止买入条件，不再计作主动卖点。",
                "历史校准显示 WAIT_DAILY_WEAK 的 5 日方向命中率接近随机，等待 STOP_T 或强卖压确认。",
                *list(reasons),
            ]
            warnings = [
                *list(warnings),
                "卖点质量过滤已拦截：WAIT_DAILY_WEAK 降级为观察，不输出卖点参考价。",
            ]
        quality_filtered_action = action
        policy_state = (
            MACDPolicyState.neutral()
            if macd_result is None
            else MACDPolicyState.from_result(macd_result, expected_interval=BarInterval.MINUTE_5)
        )
        macd_filtered_action, policy_decision = apply_timing_macd_policy(
            candidate,
            quality_filtered_action=quality_filtered_action,
            macd=policy_state,
            config=self.macd_policy_config,
        )
        action = macd_filtered_action
        if policy_decision is not None and policy_decision.final_signal is Signal.HOLD:
            reasons = [
                f"MACD policy 已将候选 {candidate.candidate_signal.value if candidate.candidate_signal else 'NONE'} 降级为 HOLD。",
                *reasons,
            ]
            warnings = [*warnings, f"MACD policy 原因：{policy_decision.trace.downgrade_reason}。"]
        signal_blocked = False
        if require_fresh and not data_fresh:
            original_action = action
            action = "WAIT_STALE_DATA"
            signal_blocked = True
            reasons = [
                f"数据已过期：最后一根 5 分钟 K 线为 {timestamp}，距本次计算 {data_age_minutes:.1f} 分钟，超过 {freshness_limit_minutes:.1f} 分钟阈值。",
                "新鲜度门禁已禁止输出 BUY_T / SELL_T 时机；等待 Tencent、EastMoney、AKShare 或 QMT/PTrade 刷新后再判断。",
            ]
            warnings = [
                *warnings,
                f"原始模型动作 {original_action} 已被数据新鲜度门禁拦截。",
                "BaoStock 只允许作为历史回补；不能用过期历史线生成盘中主信号。",
            ]
        freshness_filtered_action = action
        prices = (
            _blocked_reference_prices(levels)
            if signal_blocked
            else _reference_prices(
                action=action,
                levels=levels,
                daily_context=daily_context,
                intraday_context=intraday_context,
                breakout_setup=breakout_setup,
                chan_structure=chan_structure,
                profile=profile,
            )
        )
        confidence = _confidence(force=force, daily_context=daily_context, intraday_context=intraday_context)
        buy_point_subtype = initial_buy_point_subtype
        if candidate.primary_setup_code is not None and candidate.primary_setup_code.value == "breakout_confirmed" and action == "WATCH_BREAKOUT_NEXT_DAY":
            buy_point_subtype = BUY_POINT_SUBTYPE_BREAKOUT_WATCH
        policy_signal = policy_decision.final_signal if policy_decision is not None else candidate.candidate_signal
        final_signal = (
            policy_signal.value
            if policy_signal is not None and freshness_filtered_action == raw_candidate_action
            else Signal.HOLD.value
        )
        policy_trace = policy_decision.trace if policy_decision is not None else None
        decision_trace = TimingDecisionTrace(
            **candidate_trace_fields(candidate),
            raw_candidate_action=raw_candidate_action,
            quality_filtered_action=quality_filtered_action,
            macd_filtered_action=macd_filtered_action,
            freshness_filtered_action=freshness_filtered_action,
            final_action=action,
            final_signal=final_signal,
            signal_downgraded=bool(policy_trace and policy_trace.signal_downgraded),
            downgrade_source=policy_trace.downgrade_source if policy_trace else None,
            downgrade_reason=policy_trace.downgrade_reason if policy_trace else None,
            macd_sizing_multiplier=policy_decision.macd_sizing_multiplier if policy_decision else 1.0,
            sizing_adjustment_source=policy_trace.sizing_adjustment_source if policy_trace else None,
            macd_sizing_applied=False,
            macd_sizing_owner=None,
            macd_policy_applied=bool(policy_trace and policy_trace.macd_policy_applied),
            macd_policy_changed_candidate=bool(
                policy_trace
                and (policy_trace.signal_downgraded or policy_trace.macd_sizing_multiplier != 1.0)
            ),
            macd_score=macd_result.score if macd_result is not None else 50.0,
            macd_cross=macd_result.cross.value if macd_result is not None else "NONE",
            macd_zero_axis=macd_result.zero_axis.value if macd_result is not None else "STRADDLING",
            macd_histogram_trend=(
                macd_result.histogram_trend.value if macd_result is not None else "FLAT"
            ),
        )
        signal_strength = _signal_strength(
            action=action,
            force=force,
            certainty=certainty,
            sell_pressure=sell_pressure,
            daily_context=daily_context,
            intraday_context=intraday_context,
            multi_period_trend=multi_period_trend,
            capital_flow=capital_flow,
            volume_price_structure=volume_price_structure,
            trend_probability=trend_probability,
            breakout_setup=breakout_setup,
            chan_structure=chan_structure,
            risk_reward_ratio=levels["risk_reward_ratio"],
            buy_point_subtype=buy_point_subtype,
        )
        return CoscoTimingSnapshot(
            symbol=profile.symbol,
            name=profile.name,
            timestamp=timestamp,
            generated_at=evaluation_time.strftime("%Y-%m-%d %H:%M:%S"),
            data_source=data_source,
            data_age_minutes=data_age_minutes,
            data_fresh=data_fresh,
            freshness_status=freshness_status,
            freshness_limit_minutes=freshness_limit_minutes,
            interval_minutes=profile.preferred_interval_minutes,
            action=action,
            confidence=0.0 if signal_blocked else confidence,
            prices=prices,
            attention=attention,
            certainty=certainty,
            memory=memory,
            sell_pressure=sell_pressure,
            weights=weights,
            force=force,
            market_regime=market_regime,
            multi_period_trend=multi_period_trend,
            capital_flow=capital_flow,
            volume_price_structure=volume_price_structure,
            chan_structure=chan_structure,
            trend_probability=trend_probability,
            breakout_setup=breakout_setup,
            signal_strength=signal_strength,
            risk_reward_ratio=round(levels["risk_reward_ratio"], 4),
            trend_state=trend_state.value,
            daily_context=daily_context,
            intraday_context=intraday_context,
            decision_trace=decision_trace,
            reasons=tuple(reasons),
            warnings=tuple(warnings),
            manual_only=True,
            is_realtime=is_realtime,
            signal_blocked=signal_blocked,
            buy_point_subtype=buy_point_subtype,
        )


def get_cosco_timing_from_tushare(*, persist: bool = True) -> CoscoTimingSnapshot | CoscoTimingUnavailable:
    """Fetch recent 5-minute bars from Tushare and evaluate a manual signal."""
    now = datetime.now()
    start = now - timedelta(days=10)
    try:
        client = build_tushare_client()
        bars = client.minute_bars(
            COSCO_A_SYMBOL,
            freq="5min",
            start_date=start.strftime("%Y-%m-%d 09:00:00"),
            end_date=now.strftime("%Y-%m-%d %H:%M:%S"),
            use_cache=False,
        )
        snapshot = CoscoTimingEngine().evaluate(
            bars,
            data_source="tushare_stk_mins_5min",
            is_realtime=False,
            require_fresh=True,
        )
        if persist:
            save_cosco_snapshot(snapshot)
        return snapshot
    except (TushareConfigError, TushareDataError, ValueError) as exc:
        return CoscoTimingUnavailable(
            symbol=COSCO_A_SYMBOL,
            status="data_unavailable",
            message=str(exc),
            required_user_steps=(
                "配置 .env 中的 TUSHARE_TOKEN。",
                "确认 Tushare 有 A 股 5min 分钟线权限。",
                "若要盘中更稳定，后续接入 QMT/PTrade 实时 5 分钟行情。",
            ),
        )


def get_cosco_timing_from_free_sources(
    *,
    provider: str | None = None,
    persist: bool = True,
) -> CoscoTimingSnapshot | CoscoTimingUnavailable:
    """Fetch recent 5-minute bars from free providers and evaluate a manual signal."""
    started_at = time.perf_counter()
    profile_steps: list[dict[str, object]] = []
    now = datetime.now()
    start = now - timedelta(days=10)
    provider_key = (provider or "fast").strip().lower()
    providers = None if provider_key in {"", "auto", "free"} else (provider_key,)
    try:
        fetch_started_at = time.perf_counter()
        result = fetch_a_share_5min_with_fallback(
            COSCO_A_SYMBOL,
            start_date=start.strftime("%Y-%m-%d 09:00:00"),
            end_date=now.strftime("%Y-%m-%d %H:%M:%S"),
            providers=providers,
        )
        profile_steps.append(
            {
                "step": "fetch_bars",
                "provider": result.provider,
                "elapsed_seconds": round(time.perf_counter() - fetch_started_at, 3),
                "rows": len(result.bars),
            }
        )
        evaluate_started_at = time.perf_counter()
        snapshot = CoscoTimingEngine().evaluate(
            result.bars,
            data_source=result.source,
            is_realtime=result.is_realtime,
            require_fresh=True,
        )
        profile_steps.append(
            {
                "step": "evaluate_model",
                "elapsed_seconds": round(time.perf_counter() - evaluate_started_at, 3),
                "rows": len(result.bars),
            }
        )
        persist_elapsed = None
        snapshot = replace(
            snapshot,
            warnings=(
                *snapshot.warnings,
                "当前使用免费行情源轮询数据，不是逐笔实时行情；下单前必须以券商终端盘口为准。",
                "盘中默认快路径为本地 5 分钟缓存 + Tencent；完整慢速回补请手动使用 provider=strict。",
            ),
            data_attempts=tuple(item.to_dict() for item in result.attempts),
        )
        if persist:
            persist_started_at = time.perf_counter()
            save_cosco_snapshot(snapshot)
            persist_elapsed = round(time.perf_counter() - persist_started_at, 3)
            profile_steps.append({"step": "persist_snapshot", "elapsed_seconds": persist_elapsed})
        profile_steps.append({"step": "total", "elapsed_seconds": round(time.perf_counter() - started_at, 3)})
        snapshot = replace(snapshot, runtime_profile=tuple(profile_steps))
        return snapshot
    except (MultiSourceDataError, ValueError) as exc:
        profile_steps.append({"step": "total", "elapsed_seconds": round(time.perf_counter() - started_at, 3)})
        attempts = tuple(item.to_dict() for item in getattr(exc, "attempts", ()))
        return CoscoTimingUnavailable(
            symbol=COSCO_A_SYMBOL,
            status="data_unavailable",
            message=str(exc),
            required_user_steps=(
                "确认本地 5 分钟缓存存在：data/raw/dividend_t_5min/601919.SH_5min.csv。",
                "优先用 provider=fast 跑通盘中快路径；若要补历史数据，盘后再用 provider=strict。",
                "若要更接近盘中实时，后续接入 QMT/PTrade 实时 5 分钟行情。",
            ),
            data_source="free_provider_fallback",
            data_attempts=attempts,
            runtime_profile=tuple(profile_steps),
        )


def save_cosco_snapshot(snapshot: CoscoTimingSnapshot) -> None:
    store = ResearchStore()
    store.write_parquet("cosco_latest_manual_timing", [snapshot.to_dict()])


def build_sample_cosco_bars() -> Any:
    import pandas as pd

    base_time = pd.Timestamp("2026-06-01 09:35:00")
    rows: list[dict[str, Any]] = []
    price = 13.80
    for index in range(72):
        if index < 22:
            price += 0.015
        elif index < 42:
            price -= 0.018
        elif index < 60:
            price += 0.010
        else:
            price += 0.004
        open_price = price - 0.015
        high = max(open_price, price) + 0.035
        low = min(open_price, price) - 0.035
        volume = float(900_000 + (index % 9) * 55_000)
        if index in {55, 56, 57}:
            volume *= 1.8
        rows.append(
            {
                "symbol": COSCO_A_SYMBOL,
                "timestamp": base_time + pd.Timedelta(minutes=5 * index),
                "open": round(open_price, 3),
                "high": round(high, 3),
                "low": round(low, 3),
                "close": round(price, 3),
                "volume": float(volume),
                "amount": float(volume * price),
                "source_freq": "5min",
            }
        )
    return pd.DataFrame(rows)


def sample_cosco_timing() -> CoscoTimingSnapshot:
    snapshot = CoscoTimingEngine().evaluate(
        build_sample_cosco_bars(),
        data_source="sample_static_5min",
        is_realtime=False,
    )
    return replace(
        snapshot,
        warnings=(
            *snapshot.warnings,
            "这是固定样例数据，只用于验证页面和模型计算链路，不代表实时行情。",
        ),
    )


def _trend_5_20_allows_buy(multi_period_trend: MultiPeriodTrend) -> bool:
    return multi_period_trend.trend_5_20_state in {"UP", "PULLBACK_IN_UPTREND"}


def _pullback_buy_quality_allows_5d(
    volume_price_structure: VolumePriceStructure,
    capital_flow: CapitalFlowEstimate,
) -> bool:
    if volume_price_structure.state != "LOW_VOLUME_PULLBACK":
        return False
    if capital_flow.confirmation_state == "DIVERGENT":
        return False
    return volume_price_structure.vwap_support_score >= 70.0 or capital_flow.confirmation_state == "CONFIRMED_INFLOW"


def _stop_wait_quality_allows_5d(
    *,
    capital_flow: CapitalFlowEstimate,
    volume_price_structure: VolumePriceStructure,
) -> bool:
    return capital_flow.confirmation_state != "DIVERGENT" and volume_price_structure.vwap_support_score < 50.0


def _prepare_bars(frame: Any) -> Any:
    import pandas as pd

    data = frame.copy()
    data["timestamp"] = pd.to_datetime(data["timestamp"])
    data = data.sort_values("timestamp").reset_index(drop=True)
    if "amount" not in data.columns:
        data["amount"] = data["close"] * data["volume"]
    data["amount"] = data["amount"].fillna(data["close"] * data["volume"])
    return data


def _data_age_minutes(last_bar_time: Any, generated_at: datetime) -> float:
    last_time = last_bar_time.to_pydatetime() if hasattr(last_bar_time, "to_pydatetime") else last_bar_time
    if not isinstance(last_time, datetime):
        return 0.0
    age_seconds = (generated_at - last_time.replace(tzinfo=None)).total_seconds()
    return round(max(age_seconds, 0.0) / 60, 2)


def _profile_for_data(profile: CoscoProfile, frame: Any, resolver: Any | None) -> CoscoProfile:
    if resolver is None:
        return profile
    try:
        return resolver.profile_for_timestamp(frame["timestamp"].iloc[-1])
    except Exception:  # noqa: BLE001 - fundamental data must not block manual timing calculation.
        return profile


def _reference_levels(frame: Any) -> dict[str, float]:
    data = add_daily_indicators(frame, atr_window=14)
    latest = data.iloc[-1]
    current = float(latest["close"])
    atr = float(latest["atr"]) if latest["atr"] == latest["atr"] else max(current * 0.01, 0.01)
    support = float(data["low"].tail(24).min())
    resistance = float(data["high"].tail(48).max())
    downside = max(current - (support - 0.35 * atr), current * 0.004)
    upside = max((resistance - 0.20 * atr) - current, 0.0)
    return {
        "current": current,
        "atr": atr,
        "support": support,
        "resistance": resistance,
        "risk_reward_ratio": upside / downside if downside > 0 else 0.0,
        "current_amount": float(latest["amount"]),
    }




def _trend_probability(
    *,
    force: ForceRatioEstimate,
    attention: AttentionScore,
    certainty: CertaintyScore,
    memory: MemoryScore,
    sell_pressure: SellPressureEstimate,
    trend_state: TrendState,
    daily_context: DailyContext,
    intraday_context: IntradayContext,
    multi_period_trend: MultiPeriodTrend,
    capital_flow: CapitalFlowEstimate,
    volume_price_structure: VolumePriceStructure,
    chan_structure: ChanStructure,
    risk_reward_ratio: float,
) -> TrendProbability:
    force_edge = clamp((force.force_ratio - 1.0) / 0.60, -1.0, 1.0)
    attention_edge = clamp((attention.score - 50.0) / 35.0, -1.0, 1.0)
    certainty_edge = clamp((certainty.score - 50.0) / 35.0, -1.0, 1.0)
    memory_edge = clamp((memory.score - 50.0) / 35.0, -1.0, 1.0)
    sell_inverse_edge = clamp((65.0 - sell_pressure.score) / 45.0, -1.0, 1.0)
    flow_edge = clamp(((0.55 * capital_flow.score + 0.45 * capital_flow.confirmation_score) - 50.0) / 35.0, -1.0, 1.0)
    volume_price_edge = clamp((volume_price_structure.score - 50.0) / 35.0, -1.0, 1.0)
    multi_edge = clamp((multi_period_trend.score - 50.0) / 35.0, -1.0, 1.0)
    chan_edge = clamp((chan_structure.score - 50.0) / 35.0, -1.0, 1.0)
    daily_edge = clamp((daily_context.score - 60.0) / 30.0, -1.0, 1.0)
    intraday_edge = clamp((intraday_context.score - 50.0) / 35.0, -1.0, 1.0)
    rr_edge = clamp((risk_reward_ratio - 1.3) / 1.7, -1.0, 1.0)

    edge_1d = (
        0.23 * force_edge
        + 0.18 * flow_edge
        + 0.13 * volume_price_edge
        + 0.14 * attention_edge
        + 0.12 * intraday_edge
        + 0.09 * certainty_edge
        + 0.08 * chan_edge
        + 0.06 * memory_edge
        + 0.04 * sell_inverse_edge
        + 0.03 * rr_edge
    )
    edge_3d = (
        0.21 * multi_edge
        + 0.17 * daily_edge
        + 0.12 * volume_price_edge
        + 0.16 * certainty_edge
        + 0.11 * force_edge
        + 0.10 * chan_edge
        + 0.08 * memory_edge
        + 0.08 * flow_edge
        + 0.05 * sell_inverse_edge
        + 0.05 * rr_edge
    )

    reasons: list[str] = []
    if trend_state == TrendState.UPTREND:
        edge_1d += 0.08
        edge_3d += 0.06
        reasons.append("5 分钟趋势向上，提高 1 日和 3 日上行概率。")
    elif trend_state == TrendState.DOWNTREND:
        edge_1d -= 0.12
        edge_3d -= 0.10
        reasons.append("5 分钟趋势空头，降低上行概率并提高风险门控。")
    elif trend_state == TrendState.EXHAUSTION:
        edge_1d -= 0.08
        reasons.append("5 分钟高位衰竭，降低 1 日上行概率。")

    if multi_period_trend.monthly_state == "DOWN":
        edge_3d -= 0.12
        reasons.append("月线向下，压低 3 日上行概率。")
    if daily_context.state == "WEAK":
        edge_1d -= 0.12
        edge_3d -= 0.10
        reasons.append("日线背景偏弱，概率门控禁止放大分钟线买点。")
    if capital_flow.state == "OUTFLOW":
        edge_1d -= 0.08
        reasons.append("资金流代理偏流出，降低短线延续概率。")
    if capital_flow.confirmation_state == "CONFIRMED_INFLOW":
        edge_1d += 0.06
        edge_3d += 0.04
        reasons.append("资金流确认分显示持续流入，提高上涨延续概率。")
    elif capital_flow.confirmation_state == "CONFIRMED_OUTFLOW":
        edge_1d -= 0.08
        edge_3d -= 0.05
        reasons.append("资金流确认分显示持续流出，降低趋势跟随胜率。")
    if volume_price_structure.state in {"VOLUME_BREAKOUT", "VWAP_ACCUMULATION", "LOW_VOLUME_PULLBACK"}:
        edge_1d += 0.05
        edge_3d += 0.05
        reasons.append(f"量价结构={volume_price_structure.state}，提高趋势延续概率。")
    if volume_price_structure.state in {"HIGH_VOLUME_STALL", "PRICE_UP_VOLUME_DOWN"}:
        edge_1d -= 0.07
        edge_3d -= 0.05
        reasons.append(f"量价结构={volume_price_structure.state}，降低追涨和延续概率。")
    if chan_structure.buy_point_type in BUY_POINTS:
        edge_1d += 0.05
        edge_3d += 0.04
        reasons.append(f"缠论结构出现 {chan_structure.buy_point_type}，提高买点有效性。")
    if chan_structure.sell_point_type in SELL_POINTS or chan_structure.structure_type == "breakdown":
        edge_1d -= 0.10
        edge_3d -= 0.08
        reasons.append("缠论结构出现卖点或跌破中枢，降低上行概率。")

    edge_1d = clamp(edge_1d, -1.0, 1.0)
    edge_3d = clamp(edge_3d, -1.0, 1.0)
    pressure_penalty_1d = 0.04 if sell_pressure.score >= 78.0 else (0.02 if sell_pressure.score >= 70.0 else 0.0)
    pressure_penalty_3d = 0.03 if sell_pressure.score >= 78.0 else (0.015 if sell_pressure.score >= 70.0 else 0.0)
    up_1d = clamp(0.50 + 0.16 * edge_1d, 0.34, 0.68)
    up_3d = clamp(0.50 + 0.15 * edge_3d, 0.34, 0.68)
    down_1d = clamp(0.50 - 0.14 * edge_1d + pressure_penalty_1d, 0.32, 0.70)
    down_3d = clamp(0.50 - 0.13 * edge_3d + pressure_penalty_3d, 0.32, 0.70)

    if up_1d >= 0.55 and up_3d >= 0.53 and down_1d < 0.56:
        state = "UP_PROBABLE"
    elif down_1d >= 0.57 or down_3d >= 0.57:
        state = "DOWN_RISK"
    else:
        state = "RANGE"

    reasons.insert(
        0,
        f"概率门控：1日上行 {up_1d:.1%} / 下行 {down_1d:.1%}，3日上行 {up_3d:.1%} / 下行 {down_3d:.1%}。",
    )
    return TrendProbability(
        up_1d=round(up_1d, 4),
        down_1d=round(down_1d, 4),
        up_3d=round(up_3d, 4),
        down_3d=round(down_3d, 4),
        edge_1d=round(edge_1d, 4),
        edge_3d=round(edge_3d, 4),
        state=state,
        reasons=tuple(reasons[:5]),
    )






def _reference_prices(
    *,
    action: str,
    levels: dict[str, float],
    daily_context: DailyContext,
    intraday_context: IntradayContext,
    breakout_setup: BreakoutSetup,
    chan_structure: ChanStructure,
    profile: CoscoProfile,
) -> ReferencePrices:
    current = levels["current"]
    atr = levels["atr"]
    support = levels["support"]
    resistance = levels["resistance"]
    buy_price = None
    sell_price = None
    stop_price = None
    buy_back_price = None

    if action == "BUY_T_TIMING":
        buy_price = min(current, support + 0.20 * atr)
        sell_price = max(current + 0.80 * atr, resistance - 0.20 * atr)
        stop_price = support - 0.45 * atr
        if chan_structure.buy_point_type == "buy3" and chan_structure.pivot_high is not None:
            buy_price = current
            sell_price = max(sell_price, current + 1.20 * atr)
            stop_price = chan_structure.invalid_price or chan_structure.pivot_high - 0.35 * atr
        elif chan_structure.buy_point_type in {"buy1", "buy2", "range_buy"} and chan_structure.invalid_price is not None:
            stop_price = min(stop_price, chan_structure.invalid_price)
    elif action == "BREAKOUT_BUY_TIMING":
        buy_price = current
        breakout_level = breakout_setup.breakout_level or resistance
        sell_price = max(current + 1.15 * atr, breakout_level + 1.80 * atr)
        stop_price = chan_structure.invalid_price if chan_structure.buy_point_type == "buy3" else breakout_level - 0.55 * atr
    elif action == "WATCH_BREAKOUT_NEXT_DAY":
        buy_price = breakout_setup.trigger_price
        stop_price = (breakout_setup.breakout_level - 0.55 * atr) if breakout_setup.breakout_level is not None else None
    elif action == "SELL_T_TIMING":
        sell_price = max(current, resistance - 0.20 * atr)
        if _buyback_reference_allowed(daily_context=daily_context, intraday_context=intraday_context):
            buy_back_price = support + profile.reverse_buyback_atr_offset * atr
        stop_price = resistance + 0.35 * atr
    elif action in {"STOP_T_WAIT", "WAIT_DAILY_WEAK", "WAIT_CONFIRMATION", "WAIT_LATE_SESSION", "WAIT_STRONG_TREND"}:
        stop_price = support - 0.45 * atr
    else:
        buy_price = support + 0.15 * atr
        sell_price = resistance - 0.15 * atr
        stop_price = support - 0.45 * atr

    return ReferencePrices(
        current_price=round(current, 3),
        support_price=round(support, 3),
        resistance_price=round(resistance, 3),
        buy_reference_price=_round_or_none(buy_price),
        sell_reference_price=_round_or_none(sell_price),
        stop_price=_round_or_none(stop_price),
        buy_back_reference_price=_round_or_none(buy_back_price),
    )


def _buyback_reference_allowed(*, daily_context: DailyContext, intraday_context: IntradayContext) -> bool:
    if not daily_context.buyback_allowed:
        return False
    if intraday_context.late_session and not daily_context.allow_overnight:
        return False
    return True


def _blocked_reference_prices(levels: dict[str, float]) -> ReferencePrices:
    return ReferencePrices(
        current_price=round(levels["current"], 3),
        support_price=round(levels["support"], 3),
        resistance_price=round(levels["resistance"], 3),
        buy_reference_price=None,
        sell_reference_price=None,
        stop_price=None,
        buy_back_reference_price=None,
    )


def _round_or_none(value: float | None) -> float | None:
    return None if value is None else round(value, 3)



def _market_regime(
    *,
    force: ForceRatioEstimate,
    attention: AttentionScore,
    certainty: CertaintyScore,
    memory: MemoryScore,
    sell_pressure: SellPressureEstimate,
    trend_state: TrendState,
    daily_context: DailyContext,
    intraday_context: IntradayContext,
    multi_period_trend: MultiPeriodTrend,
    capital_flow: CapitalFlowEstimate,
    volume_price_structure: VolumePriceStructure,
    trend_probability: TrendProbability,
    breakout_setup: BreakoutSetup,
    chan_structure: ChanStructure,
    profile: CoscoProfile,
) -> MarketRegime:
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
    force_reversal = (
        daily_context.fundamental_score >= 60.0
        and daily_context.state != "WEAK"
        and (force.force_ratio >= (1.02 if flow_confirmed else 1.12) or (volume_price_strong and force.weighted_score >= 46.0))
        and (force.weighted_score >= (48.0 if flow_confirmed else 52.0) or volume_price_strong)
        and sell_pressure.score <= 76.0
        and (capital_flow.score >= 46.0 or flow_confirmed or volume_price_constructive)
        and multi_period_trend.monthly_state != "DOWN"
        and trend_probability.up_1d >= (0.53 if flow_confirmed else 0.55)
        and trend_probability.down_1d < 0.58
    )
    chan_breakdown = chan_structure.sell_point_type == "sell3" or chan_structure.structure_type == "breakdown"
    if daily_context.fundamental_score < 55.0 or daily_context.state == "WEAK" or chan_breakdown or (trend_state == TrendState.DOWNTREND and not force_reversal):
        target = profile.defensive_base_position_pct if daily_context.fundamental_score >= 50.0 else 0.0
        budget = PositionBudget.from_total_cap(base_target_pct=target, max_total_position_pct=target)
        reasons = [
            "防守行情：日线、基本面或 5 分钟趋势至少一项触发风险门控。",
            f"底仓目标降到 {budget.base_target_pct:.0%}，主动增量上限 {budget.active_position_cap_pct:.0%}，不主动扩张。",
            *chan_structure.reasons[:1],
            *multi_period_trend.reasons[:1],
            *capital_flow.reasons[:1],
        ]
        return MarketRegime(
            state="DEFENSIVE",
            label="防守",
            base_position_target_pct=round(target, 4),
            base_position_limit_pct=round(target, 4),
            t_trade_limit_pct=0.0,
            active_position_cap_pct=budget.active_position_cap_pct,
            max_total_position_pct=budget.max_total_position_pct,
            reasons=tuple(reasons),
        )

    if (breakout_setup.breakout_confirmed or chan_structure.buy_point_type == "buy3") and not intraday_context.late_session:
        budget = PositionBudget.from_total_cap(
            base_target_pct=profile.range_base_position_pct,
            max_total_position_pct=min(profile.strong_trend_max_total_position_pct, 0.50),
        )
        trigger_price = _fmt_optional_price(breakout_setup.trigger_price)
        reasons = [
            "强势启动行情：价格放量突破近端压力，允许用主动仓位做突破跟随试错。",
            f"底仓仍控制在 {budget.base_target_pct:.0%} 附近，主动增量上限 {budget.active_position_cap_pct:.0%}，总仓位上限 {budget.max_total_position_pct:.0%}。",
            f"突破分={breakout_setup.score:.1f}，触发价={trigger_price}。",
            *chan_structure.reasons[:1],
            *breakout_setup.reasons[:2],
        ]
        return MarketRegime(
            state="BREAKOUT_ATTACK",
            label="强势启动",
            base_position_target_pct=round(profile.range_base_position_pct, 4),
            base_position_limit_pct=round(profile.range_base_position_pct, 4),
            t_trade_limit_pct=budget.max_total_position_pct,
            active_position_cap_pct=budget.active_position_cap_pct,
            max_total_position_pct=budget.max_total_position_pct,
            reasons=tuple(reasons),
        )

    strong_trend = (
        (daily_context.state == "STRONG" or force_buy_edge >= 70.0)
        and (trend_state == TrendState.UPTREND or multi_period_trend.score >= 66.0 or chan_structure.buy_point_type == "buy3")
        and daily_context.fundamental_score >= 65.0
        and certainty.score >= (48.0 if flow_confirmed else 52.0)
        and (force.force_ratio >= 0.86 or force.weighted_score >= 46.0 or flow_confirmed or volume_price_strong)
        and sell_pressure.score < (84.0 if flow_confirmed else profile.strong_trend_sell_pressure_threshold)
        and multi_period_trend.score >= (50.0 if flow_confirmed else 54.0)
        and multi_period_trend.monthly_state != "DOWN"
        and (capital_flow.score >= 42.0 or flow_confirmed or volume_price_constructive)
        and trend_probability.up_3d >= (0.51 if flow_confirmed else 0.53)
        and trend_probability.down_3d < 0.58
    )
    if strong_trend:
        budget = PositionBudget.from_total_cap(
            base_target_pct=profile.range_base_position_pct,
            max_total_position_pct=profile.strong_trend_max_total_position_pct,
        )
        reasons = [
            "强趋势行情：日线 STRONG、5 分钟 UPTREND，且买卖力和确定性未转弱。",
            f"底仓仍控制在 {budget.base_target_pct:.0%} 附近，主动增量上限 {budget.active_position_cap_pct:.0%}，总仓位上限 {budget.max_total_position_pct:.0%}。",
            "若后续出现卖出或止损信号，执行层卖出主动仓位，保留低底仓。",
            f"量价结构={volume_price_structure.state}，V={volume_price_structure.score:.1f}。",
            *multi_period_trend.reasons[:1],
            *capital_flow.reasons[:1],
        ]
        return MarketRegime(
            state="STRONG_TREND",
            label="强趋势",
            base_position_target_pct=round(profile.range_base_position_pct, 4),
            base_position_limit_pct=round(profile.range_base_position_pct, 4),
            t_trade_limit_pct=budget.max_total_position_pct,
            active_position_cap_pct=budget.active_position_cap_pct,
            max_total_position_pct=budget.max_total_position_pct,
            reasons=tuple(reasons),
        )

    if (
        daily_context.state == "STRONG"
        or trend_state == TrendState.UPTREND
        or chan_structure.buy_point_type in BUY_POINTS
        or force_buy_edge >= 62.0
        or volume_price_constructive
        or trend_probability.state == "UP_PROBABLE"
    ):
        budget = PositionBudget.from_total_cap(
            base_target_pct=profile.range_base_position_pct,
            max_total_position_pct=profile.range_max_total_position_pct,
        )
        reasons = [
            "趋势观察行情：有上行证据或买卖力开始转强，但强趋势条件未全部满足。",
            f"底仓仍控制在 {budget.base_target_pct:.0%} 附近，当前总仓位上限 {budget.max_total_position_pct:.0%}，等待强趋势确认再扩仓。",
            f"概率状态={trend_probability.state}，1日上行 {trend_probability.up_1d:.1%}，3日上行 {trend_probability.up_3d:.1%}。",
            f"量价结构={volume_price_structure.state}，V={volume_price_structure.score:.1f}。",
            *chan_structure.reasons[:1],
            *multi_period_trend.reasons[:1],
            *capital_flow.reasons[:1],
        ]
        return MarketRegime(
            state="TREND_WATCH",
            label="趋势观察",
            base_position_target_pct=round(profile.range_base_position_pct, 4),
            base_position_limit_pct=round(profile.range_base_position_pct, 4),
            t_trade_limit_pct=budget.max_total_position_pct,
            active_position_cap_pct=budget.active_position_cap_pct,
            max_total_position_pct=budget.max_total_position_pct,
            reasons=tuple(reasons),
        )

    budget = PositionBudget.from_total_cap(
        base_target_pct=profile.range_base_position_pct,
        max_total_position_pct=profile.range_max_total_position_pct,
    )
    reasons = [
        "震荡行情：强趋势条件不足，维持低底仓，用 T 仓处理支撑压力。",
        f"底仓目标 {budget.base_target_pct:.0%}，主动增量上限 {budget.active_position_cap_pct:.0%}，总仓位上限 {budget.max_total_position_pct:.0%}。",
    ]
    if intraday_context.late_session:
        reasons.append("尾盘信号不主动扩张仓位。")
    return MarketRegime(
        state="RANGE_T",
        label="震荡做 T",
        base_position_target_pct=round(profile.range_base_position_pct, 4),
        base_position_limit_pct=round(profile.range_base_position_pct, 4),
        t_trade_limit_pct=budget.max_total_position_pct,
        active_position_cap_pct=budget.active_position_cap_pct,
        max_total_position_pct=budget.max_total_position_pct,
        reasons=tuple(reasons),
    )


def _fmt_optional_price(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.3f}"


def _confidence(
    *,
    force: ForceRatioEstimate,
    daily_context: DailyContext,
    intraday_context: IntradayContext,
) -> float:
    score = 0.65 * force.weighted_score + 0.20 * intraday_context.score + 0.15 * daily_context.score
    return round(clamp(score, 0.0, 100.0), 2)
