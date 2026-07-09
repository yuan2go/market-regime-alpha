"""Build static dividend-watchlist trend snapshots for GitHub Pages."""

from __future__ import annotations

import csv
from dataclasses import asdict
from datetime import datetime
import json
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from market_regime_alpha.data_sources.a_share_bars import (
    AShareBarProvider,
    LatestQuote,
    LocalCacheTencentProvider,
    TencentMinuteProvider,
    fetch_tencent_latest_quotes,
)
from market_regime_alpha.dividend_t.cosco_profile import profile_for_watchlist_item
from market_regime_alpha.dividend_t.cosco_timing import CoscoTimingEngine
from market_regime_alpha.dividend_t.fundamentals import build_fundamental_resolver
from market_regime_alpha.dividend_t.indicators import estimate_levels, infer_technical_inputs
from market_regime_alpha.dividend_t.models import FundamentalInputs, PositionState, RetreatInputs, Signal, StrategyDecision, TrendState, WatchlistItem
from market_regime_alpha.dividend_t.scoring import clamp
from market_regime_alpha.dividend_t.storage import DEFAULT_WATCHLIST_PATH, PROJECT_ROOT, load_watchlist
from market_regime_alpha.dividend_t.strategy import DividendTStrategy


SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")
DEFAULT_TREND_OUTPUT = PROJECT_ROOT / "docs" / "data" / "dividend_trends.json"
DEFAULT_LOCAL_TIMING_CACHE_DIR = PROJECT_ROOT / "data" / "raw" / "dividend_t_5min_1y"
DEFAULT_HIT_RATE_SUMMARY = PROJECT_ROOT / "reports" / "backtests" / "buy_sell_point_hit_rate_summary.csv"
DEFAULT_MIN_BARS = 30

SIGNAL_LABELS = {
    "BUILD_BASE": "建底仓",
    "HOLD": "持有观察",
    "BUY_T": "正 T 买入",
    "SELL_T": "卖出 T 仓",
    "SELL_REVERSE_T": "倒 T 卖出",
    "BUY_BACK_REVERSE_T": "倒 T 买回",
    "STOP_T": "停止做 T",
    "REDUCE": "减底仓",
    "CLEAR": "清仓",
}

TREND_LABELS = {
    "bullish": "偏强",
    "neutral": "震荡",
    "bearish": "偏弱",
    "risk_off": "风险回避",
}

TIMING_ACTION_LABELS = {
    "BUY_T_TIMING": "买点",
    "BREAKOUT_BUY_TIMING": "突破买点",
    "WATCH_BREAKOUT_NEXT_DAY": "突破观察",
    "STOP_T_WAIT": "卖点",
    "SELL_T_TIMING": "卖点观察",
    "WAIT": "等待",
    "WAIT_CONFIRMATION": "观察",
    "WAIT_DAILY_WEAK": "日线弱观察",
    "WAIT_STRONG_TREND": "强趋势持有",
    "WAIT_STALE_DATA": "数据过期",
}


def build_dividend_trend_snapshot(
    *,
    watchlist_path: str | Path = DEFAULT_WATCHLIST_PATH,
    limit: int = 20,
    provider: AShareBarProvider | None = None,
    quotes: dict[str, LatestQuote] | None = None,
    timeout_seconds: float = 4.0,
    generated_at: datetime | None = None,
    min_bars: int = DEFAULT_MIN_BARS,
) -> dict[str, Any]:
    """Scan the dividend watchlist and return a JSON-serializable trend snapshot."""
    generated = generated_at or datetime.now(SHANGHAI_TZ)
    items = load_watchlist(watchlist_path)[:limit]
    symbols = [item.symbol for item in items]
    quote_map = quotes if quotes is not None else _safe_quote_fetch(symbols, timeout_seconds=timeout_seconds)
    minute_provider = provider or LocalCacheTencentProvider(
        cache_dir=DEFAULT_LOCAL_TIMING_CACHE_DIR,
        tencent=TencentMinuteProvider(timeout_seconds=timeout_seconds),
    )
    strategy = DividendTStrategy()

    rows: list[dict[str, Any]] = []
    for item in items:
        quote = quote_map.get(item.symbol)
        try:
            rows.append(_build_symbol_row(item=item, provider=minute_provider, quote=quote, strategy=strategy, min_bars=min_bars))
        except Exception as exc:  # noqa: BLE001 - one bad symbol should not block the public snapshot.
            rows.append(_error_row(item=item, quote=quote, exc=exc))

    successful_count = sum(1 for row in rows if row["status"] == "ok")
    failed_count = len(rows) - successful_count
    return {
        "schema_version": 1,
        "generated_at": generated.isoformat(),
        "generated_timezone": "Asia/Shanghai",
        "watchlist_path": str(Path(watchlist_path)),
        "source": getattr(minute_provider, "data_source", getattr(minute_provider, "name", "unknown")),
        "horizon": "未来1/3/5日上涨概率与1/3/5日历史命中率",
        "point_hit_rates": load_point_hit_rate_summary(),
        "row_count": len(rows),
        "successful_count": successful_count,
        "failed_count": failed_count,
        "rows": rows,
        "notice": "模型输出仅用于研究复盘，不构成投资建议。",
    }


def write_dividend_trend_snapshot(snapshot: dict[str, Any], *, output_path: str | Path = DEFAULT_TREND_OUTPUT) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _build_symbol_row(
    *,
    item: WatchlistItem,
    provider: AShareBarProvider,
    quote: LatestQuote | None,
    strategy: DividendTStrategy,
    min_bars: int,
) -> dict[str, Any]:
    bars = provider.minute_bars(item.symbol, freq="5min")
    if len(bars) < min_bars:
        raise ValueError(f"5分钟K线只有 {len(bars)} 根，至少需要 {min_bars} 根")

    technical = infer_technical_inputs(bars)
    retreat = infer_retreat_inputs(bars, technical)
    decision = strategy.evaluate(
        symbol=item.symbol,
        fundamental=default_fundamental_inputs(item),
        retreat=retreat,
        technical=technical,
        position=PositionState(is_cycle_stock=item.is_cycle_stock),
    )
    latest = bars.iloc[-1]
    levels = estimate_levels(bars, support_window=min(20, len(bars)), resistance_window=min(60, len(bars)))
    future_trend = classify_future_trend(decision=decision, technical=technical)
    score = asdict(decision.score)
    timing = _timing_payload(item=item, bars=bars, data_source=_data_source(provider, bars))
    return {
        "status": "ok",
        "symbol": item.symbol,
        "name": item.name,
        "industry": item.industry,
        "is_cycle_stock": item.is_cycle_stock,
        "latest_price": _round(quote.current_price if quote else float(latest["close"])),
        "change_pct": _round(quote.change_pct, digits=4) if quote and quote.change_pct is not None else None,
        "quote_time": quote.quote_time if quote else None,
        "quote_source": quote.source if quote else None,
        "bar_time": str(latest["timestamp"]),
        "bar_count": int(len(bars)),
        "close": _round(float(latest["close"])),
        "support": _round(levels.support),
        "resistance": _round(levels.resistance),
        "future_trend": future_trend,
        "future_trend_label": TREND_LABELS[future_trend],
        "confidence": trend_confidence(decision=decision, technical=technical),
        "trend_state": _enum_value(technical.trend_state),
        "chan_structure_type": technical.chan_structure_type,
        "chan_trend_direction": technical.chan_trend_direction,
        "signal": _enum_value(decision.signal),
        "signal_label": SIGNAL_LABELS.get(_enum_value(decision.signal), _enum_value(decision.signal)),
        "total_score": _round(score["total_score"], digits=1),
        "F_score": _round(score["F_score"], digits=1),
        "R_score": _round(score["R_score"], digits=1),
        "T_score": _round(score["T_score"], digits=1),
        "risk_reward_ratio": _round(retreat.risk_reward_ratio, digits=2),
        "sell_pressure": _round(retreat.sell_pressure, digits=2),
        **timing,
        "reasons": list(decision.reasons),
        "warnings": list(decision.warnings),
    }


def _error_row(*, item: WatchlistItem, quote: LatestQuote | None, exc: Exception) -> dict[str, Any]:
    return {
        "status": "error",
        "symbol": item.symbol,
        "name": item.name,
        "industry": item.industry,
        "is_cycle_stock": item.is_cycle_stock,
        "latest_price": _round(quote.current_price) if quote else None,
        "change_pct": _round(quote.change_pct, digits=4) if quote and quote.change_pct is not None else None,
        "quote_time": quote.quote_time if quote else None,
        "quote_source": quote.source if quote else None,
        "future_trend": "neutral",
        "future_trend_label": "数据不足",
        "confidence": 0,
        "signal": "NO_DATA",
        "signal_label": "数据不足",
        "timing_status": "error",
        "timing_action": "NO_DATA",
        "timing_action_label": "数据不足",
        "timing_point_type": "none",
        "timing_point_label": "无信号",
        "up_probability_1d": None,
        "down_probability_1d": None,
        "up_probability_3d": None,
        "down_probability_3d": None,
        "up_probability_5d": None,
        "up_probability_5d_source": "unavailable",
        "probability_state": "NO_DATA",
        "buy_reference_price": None,
        "sell_reference_price": None,
        "stop_price": None,
        "buy_back_reference_price": None,
        "scan_error": f"{type(exc).__name__}: {exc}",
    }


def _timing_payload(*, item: WatchlistItem, bars: Any, data_source: str) -> dict[str, Any]:
    try:
        profile = profile_for_watchlist_item(item)
        snapshot = CoscoTimingEngine(
            profile=profile,
            fundamental_resolver=build_fundamental_resolver(profile, source="profile"),
        ).evaluate(bars, data_source=data_source)
    except Exception as exc:  # noqa: BLE001 - keep the public row useful when the timing engine cannot evaluate.
        return {
            "timing_status": "error",
            "timing_action": "ERROR",
            "timing_action_label": "计算失败",
            "timing_point_type": "none",
            "timing_point_label": "无信号",
            "timing_error": f"{type(exc).__name__}: {exc}",
            "up_probability_1d": None,
            "down_probability_1d": None,
            "up_probability_3d": None,
            "down_probability_3d": None,
            "up_probability_5d": None,
            "up_probability_5d_source": "unavailable",
            "probability_state": "ERROR",
            "buy_reference_price": None,
            "sell_reference_price": None,
            "stop_price": None,
            "buy_back_reference_price": None,
        }

    probability = snapshot.trend_probability
    prices = snapshot.prices
    action = snapshot.action
    point_type = _timing_point_type(action)
    return {
        "timing_status": "ok",
        "timing_action": action,
        "timing_action_label": TIMING_ACTION_LABELS.get(action, action),
        "timing_point_type": point_type,
        "timing_point_label": _timing_point_label(point_type),
        "buy_point_subtype": snapshot.buy_point_subtype,
        "signal_strength_score": _round(snapshot.signal_strength.score, digits=1),
        "signal_strength_label": snapshot.signal_strength.label,
        "estimated_win_rate": _round(snapshot.signal_strength.estimated_win_rate, digits=4),
        "up_probability_1d": _round(probability.up_1d, digits=4),
        "down_probability_1d": _round(probability.down_1d, digits=4),
        "up_probability_3d": _round(probability.up_3d, digits=4),
        "down_probability_3d": _round(probability.down_3d, digits=4),
        "up_probability_5d": _round(_estimate_up_probability_5d(snapshot), digits=4),
        "up_probability_5d_source": "derived_from_3d_probability_and_5_20_trend",
        "probability_state": probability.state,
        "buy_reference_price": _round(prices.buy_reference_price),
        "sell_reference_price": _round(prices.sell_reference_price),
        "stop_price": _round(prices.stop_price),
        "buy_back_reference_price": _round(prices.buy_back_reference_price),
    }


def _timing_point_type(action: str) -> str:
    if action in {"BUY_T_TIMING", "BREAKOUT_BUY_TIMING"}:
        return "buy"
    if action == "STOP_T_WAIT":
        return "sell"
    if action in {"WATCH_BREAKOUT_NEXT_DAY", "SELL_T_TIMING", "WAIT_CONFIRMATION", "WAIT_DAILY_WEAK", "WAIT_STRONG_TREND"}:
        return "watch"
    return "none"


def _timing_point_label(point_type: str) -> str:
    return {
        "buy": "买点",
        "sell": "卖点",
        "watch": "观察",
    }.get(point_type, "无信号")


def _data_source(provider: AShareBarProvider, bars: Any) -> str:
    attrs = getattr(bars, "attrs", {})
    return str(attrs.get("data_source") or getattr(provider, "data_source", getattr(provider, "name", "unknown")))


def _estimate_up_probability_5d(snapshot: Any) -> float:
    probability = snapshot.trend_probability
    multi_period = snapshot.multi_period_trend
    capital_flow = snapshot.capital_flow
    daily_context = snapshot.daily_context
    sell_pressure = snapshot.sell_pressure

    flow_score = 0.55 * capital_flow.score + 0.45 * capital_flow.confirmation_score
    sell_inverse = 100.0 - sell_pressure.score
    estimate = (
        0.45 * probability.up_3d
        + 0.24 * clamp(multi_period.score / 100.0, 0.0, 1.0)
        + 0.16 * clamp(daily_context.score / 100.0, 0.0, 1.0)
        + 0.10 * clamp(flow_score / 100.0, 0.0, 1.0)
        + 0.05 * clamp(sell_inverse / 100.0, 0.0, 1.0)
    )
    if multi_period.trend_5_20_state == "UP":
        estimate += 0.04
    elif multi_period.trend_5_20_state == "PULLBACK_IN_UPTREND":
        estimate += 0.02
    elif multi_period.trend_5_20_state == "DOWN":
        estimate -= 0.05
    if probability.state == "DOWN_RISK":
        estimate -= 0.04
    return clamp(estimate, 0.05, 0.95)


def load_point_hit_rate_summary(path: str | Path = DEFAULT_HIT_RATE_SUMMARY) -> dict[str, Any]:
    summary_path = Path(path)
    if not summary_path.exists():
        return {"status": "missing", "source": str(summary_path), "rows": [], "by_type": {}}
    rows: list[dict[str, Any]] = []
    by_type: dict[str, dict[str, dict[str, Any]]] = {}
    with summary_path.open(newline="", encoding="utf-8") as file:
        for row in csv.DictReader(file):
            point_type = str(row.get("point_type") or row.get("group") or "")
            horizon = str(int(float(row.get("horizon_days") or 0)))
            payload = {
                "point_type": point_type,
                "horizon_days": int(horizon),
                "sample_count": int(float(row.get("sample_count") or 0)),
                "hit_count": int(float(row.get("hit_count") or 0)),
                "hit_rate": _round(float(row["hit_rate"]), digits=4) if row.get("hit_rate") else None,
                "average_future_return": _round(float(row["average_future_return"]), digits=6) if row.get("average_future_return") else None,
            }
            rows.append(payload)
            by_type.setdefault(point_type, {})[horizon] = payload
    return {"status": "ok", "source": str(summary_path), "rows": rows, "by_type": by_type}


def infer_retreat_inputs(bars: Any, technical: Any) -> RetreatInputs:
    data = bars.copy()
    levels = estimate_levels(data, support_window=min(20, len(data)), resistance_window=min(60, len(data)))
    latest = data.iloc[-1]
    previous = data.iloc[-2]
    volume_tail = data["volume"].tail(min(20, len(data)))
    volume_base = max(float(volume_tail.mean()), 1.0)
    volume_ratio = float(latest["volume"]) / volume_base
    close = float(latest["close"])
    open_price = float(latest["open"])
    previous_close = float(previous["close"])

    market_attention = clamp(2.8 + min(volume_ratio, 2.5) * 0.55, 0.0, 5.0)
    certainty = 3.0
    if technical.trend_state in {TrendState.UPTREND, TrendState.BREAKOUT}:
        certainty += 0.45
    elif technical.trend_state == TrendState.DOWNTREND:
        certainty -= 0.65
    if close > open_price:
        certainty += 0.20
    if close > previous_close:
        certainty += 0.20

    sell_pressure = 2.4
    if technical.near_resistance:
        sell_pressure += 1.1
    if technical.volume_stalling:
        sell_pressure += 0.8
    if levels.risk_reward_ratio < 1.5:
        sell_pressure += 0.6
    if technical.near_support:
        sell_pressure -= 0.3
    if technical.trend_state == TrendState.DOWNTREND:
        sell_pressure += 0.6

    return RetreatInputs(
        market_attention=round(market_attention, 2),
        upside_certainty=round(clamp(certainty, 0.0, 5.0), 2),
        risk_reward_ratio=round(levels.risk_reward_ratio, 2),
        sell_pressure=round(clamp(sell_pressure, 0.0, 5.0), 2),
    )


def default_fundamental_inputs(item: WatchlistItem) -> FundamentalInputs:
    cycle_bonus = 4.0 if item.is_cycle_stock else 0.0
    return FundamentalInputs(
        dividend_sustainability=78.0,
        valuation_margin=70.0,
        cycle_prosperity=68.0 + cycle_bonus,
        financial_quality=76.0,
        catalyst_stability=66.0,
    )


def classify_future_trend(*, decision: StrategyDecision, technical: Any) -> str:
    signal = decision.signal
    if signal in {Signal.CLEAR, Signal.REDUCE, Signal.STOP_T, Signal.SELL_T, Signal.SELL_REVERSE_T}:
        return "risk_off" if signal in {Signal.CLEAR, Signal.STOP_T} else "bearish"
    if technical.trend_state == TrendState.DOWNTREND:
        return "bearish"
    if signal in {Signal.BUY_T, Signal.BUILD_BASE, Signal.BUY_BACK_REVERSE_T}:
        return "bullish"
    if technical.trend_state in {TrendState.UPTREND, TrendState.BREAKOUT} and decision.score.total_score >= 70:
        return "bullish"
    return "neutral"


def trend_confidence(*, decision: StrategyDecision, technical: Any) -> int:
    score_component = decision.score.total_score * 0.55
    trend_component = technical.trend_quality * 0.30
    chan_component = technical.chan_score * 0.15
    confidence = clamp(score_component + trend_component + chan_component, 0.0, 100.0)
    return int(round(confidence))


def _safe_quote_fetch(symbols: list[str], *, timeout_seconds: float) -> dict[str, LatestQuote]:
    try:
        return fetch_tencent_latest_quotes(symbols, timeout_seconds=timeout_seconds)
    except Exception:  # noqa: BLE001 - quote failures should not block trend rows.
        return {}


def _enum_value(value: Any) -> str:
    return str(value.value) if hasattr(value, "value") else str(value)


def _round(value: float | None, *, digits: int = 3) -> float | None:
    if value is None:
        return None
    return round(float(value), digits)
