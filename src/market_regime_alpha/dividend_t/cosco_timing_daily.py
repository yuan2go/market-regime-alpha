"""Daily and multi-period context for the COSCO timing engine."""

from __future__ import annotations

from typing import Any

from market_regime_alpha.dividend_t.cosco_profile import CoscoProfile
from market_regime_alpha.dividend_t.cosco_timing_types import DailyContext, MultiPeriodTrend
from market_regime_alpha.dividend_t.scoring import clamp

def _daily_context(frame: Any, *, profile: CoscoProfile) -> DailyContext:
    daily = _daily_bars(frame)
    latest = daily.iloc[-1]
    close = float(latest["close"])
    previous_close = float(daily["close"].iloc[-2]) if len(daily) >= 2 else None
    f_score = _dynamic_fundamental_score(profile=profile, daily=daily)
    base_position_limit_pct = _base_position_limit_from_f(f_score)

    if len(daily) < 3:
        source_reason = (
            (f"基本面来源：{profile.fundamental_source}，日期 {profile.fundamental_as_of or '未知'}。",)
            if profile.fundamental_source != "industry_profile"
            else ()
        )
        return DailyContext(
            score=60.0,
            state="INSUFFICIENT",
            fundamental_score=round(f_score, 2),
            base_position_limit_pct=base_position_limit_pct,
            close=round(close, 3),
            previous_close=round(previous_close, 3) if previous_close is not None else None,
            ma3=None,
            ma5=None,
            daily_support=None,
            daily_resistance=None,
            allow_t=f_score >= 55.0,
            allow_overnight=False,
            buyback_allowed=False,
            position_multiplier=round(0.5 * _fundamental_position_multiplier(f_score), 2),
            reasons=(
                f"动态基本面 F={f_score:.1f}，低底仓上限约 {base_position_limit_pct:.0%}。",
                *source_reason,
                *profile.fundamental_notes[:2],
                "日线样本不足，暂不把 5 分钟买点升级为隔夜买点。",
                "盘中 T 可以观察，但倒 T 买回价需要日线背景补足后再给出。",
            ),
        )

    close_series = daily["close"]
    ma3 = float(close_series.tail(min(3, len(daily))).mean())
    ma5 = float(close_series.tail(min(5, len(daily))).mean())
    prior = daily.iloc[:-1]
    daily_support = float(prior["low"].tail(min(5, len(prior))).min())
    daily_resistance = float(prior["high"].tail(min(5, len(prior))).max())
    ma5_previous = float(close_series.iloc[:-1].tail(min(5, len(daily) - 1)).mean())
    latest_range = max(float(latest["high"]) - float(latest["low"]), close * 0.002)
    close_position = (close - float(latest["low"])) / latest_range
    latest_volume = float(latest["volume"])
    volume_ma5 = float(daily["volume"].iloc[:-1].tail(min(5, len(daily) - 1)).mean())

    score = 60.0
    reasons: list[str] = []
    if close >= ma5:
        score += 8.0
        reasons.append("日线收盘价站在 5 日均价上方，背景不弱。")
    else:
        score -= 10.0
        reasons.append("日线收盘价低于 5 日均价，短线背景偏弱。")

    if ma3 >= ma5:
        score += 6.0
    else:
        score -= 6.0
        reasons.append("3 日均价低于 5 日均价，几日级别动能转弱。")

    if ma5 >= ma5_previous:
        score += 5.0
    else:
        score -= 7.0
        reasons.append("5 日均价斜率向下，不能把盘中支撑直接当成隔夜支撑。")

    if previous_close is not None and close >= previous_close:
        score += 5.0
    else:
        score -= 5.0

    if close < daily_support:
        score -= 18.0
        reasons.append("日线收盘跌破近端日线支撑，T 仓买回必须重新计算。")
    elif close > daily_resistance:
        score += 10.0
        reasons.append("日线突破近端压力，允许更积极地处理 T 仓。")

    if close_position < 0.25:
        score -= 6.0
        reasons.append("日线收在当日下四分位，尾盘承接不足。")
    elif close_position > 0.65:
        score += 4.0

    if previous_close is not None and close < previous_close and latest_volume > volume_ma5 * 1.15:
        score -= 6.0
        reasons.append("日线下跌伴随放量，卖压没有充分释放。")

    if f_score < 60.0:
        score -= 8.0
        reasons.append("动态基本面 F < 60，降低 T 仓积极性。")
    elif f_score >= 80.0:
        score += 4.0

    score = round(clamp(score, 20.0, 88.0), 2)
    f_multiplier = _fundamental_position_multiplier(f_score)
    if score >= 70.0:
        state = "STRONG"
        allow_t = True
        allow_overnight = True
        buyback_allowed = True
        position_multiplier = 1.0 * f_multiplier
        reasons.insert(0, "日线背景偏强，允许正常做 T 和计划买回。")
    elif score >= 55.0:
        state = "NEUTRAL"
        allow_t = True
        allow_overnight = False
        buyback_allowed = True
        position_multiplier = 0.5 * f_multiplier
        reasons.insert(0, "日线背景中性，只允许小仓 T，买回必须二次确认。")
    else:
        state = "WEAK"
        allow_t = False
        allow_overnight = False
        buyback_allowed = False
        position_multiplier = 0.0
        reasons.insert(0, "日线背景偏弱，禁止把 5 分钟买点升级为买回或补仓。")
    if f_score < 55.0:
        allow_t = False
        allow_overnight = False
        buyback_allowed = False
        position_multiplier = 0.0
        reasons.insert(1, "动态基本面 F < 55，触发 T 仓防守降级。")
    reasons.insert(1, f"动态基本面 F={f_score:.1f}，低底仓上限约 {base_position_limit_pct:.0%}。")
    if profile.fundamental_source != "industry_profile":
        reasons.insert(2, f"基本面来源：{profile.fundamental_source}，日期 {profile.fundamental_as_of or '未知'}。")
    reasons.extend(profile.fundamental_notes[:2])

    return DailyContext(
        score=score,
        state=state,
        fundamental_score=round(f_score, 2),
        base_position_limit_pct=base_position_limit_pct,
        close=round(close, 3),
        previous_close=round(previous_close, 3) if previous_close is not None else None,
        ma3=round(ma3, 3),
        ma5=round(ma5, 3),
        daily_support=round(daily_support, 3),
        daily_resistance=round(daily_resistance, 3),
        allow_t=allow_t,
        allow_overnight=allow_overnight,
        buyback_allowed=buyback_allowed,
        position_multiplier=round(clamp(position_multiplier, 0.0, 1.2), 2),
        reasons=tuple(reasons[:5]),
    )


def _dynamic_fundamental_score(*, profile: CoscoProfile, daily: Any) -> float:
    """Blend static F with slow market evidence until real fundamentals are wired in."""
    score = float(profile.base_fundamental_score)
    if len(daily) < 3:
        return clamp(score, 0.0, 100.0)

    latest = daily.iloc[-1]
    close = float(latest["close"])
    recent = daily.tail(min(20, len(daily)))
    recent_high = float(recent["high"].max())
    recent_low = float(recent["low"].min())
    previous_close = float(daily["close"].iloc[-2])
    close_series = daily["close"]
    ma3 = float(close_series.tail(min(3, len(daily))).mean())
    ma5 = float(close_series.tail(min(5, len(daily))).mean())
    drawdown = close / recent_high - 1.0 if recent_high > 0 else 0.0
    recovery = close / recent_low - 1.0 if recent_low > 0 else 0.0

    if close >= ma5:
        score += 2.5
    else:
        score -= 4.0
    if ma3 >= ma5:
        score += 2.0
    else:
        score -= 2.5
    if close >= previous_close:
        score += 1.5
    else:
        score -= 1.5
    if drawdown <= -0.12 and profile.is_cycle_stock:
        score -= 6.0
    elif drawdown <= -0.08:
        score -= 3.5
    if recovery >= 0.08:
        score += 2.0
    return clamp(score, 35.0, 88.0)


def _base_position_limit_from_f(f_score: float) -> float:
    if f_score >= 60.0:
        return 0.10
    if f_score >= 50.0:
        return 0.05
    return 0.0


def _fundamental_position_multiplier(f_score: float) -> float:
    if f_score >= 82.0:
        return 1.10
    if f_score >= 70.0:
        return 1.00
    if f_score >= 60.0:
        return 0.65
    if f_score >= 55.0:
        return 0.35
    return 0.0


def _daily_bars(frame: Any) -> Any:
    data = frame.copy().sort_values("timestamp").reset_index(drop=True)
    data["trade_date"] = data["timestamp"].dt.date
    return (
        data.groupby("trade_date", sort=True)
        .agg(
            open=("open", "first"),
            high=("high", "max"),
            low=("low", "min"),
            close=("close", "last"),
            volume=("volume", "sum"),
            amount=("amount", "sum"),
        )
        .reset_index()
    )

def _multi_period_trend(frame: Any) -> MultiPeriodTrend:
    daily = _daily_bars(frame)
    close = daily["close"]
    latest_close = float(close.iloc[-1])
    reasons: list[str] = []

    daily_score = 50.0
    if len(daily) >= 5:
        ma5 = float(close.tail(5).mean())
        ma5_prev = float(close.iloc[:-1].tail(5).mean()) if len(daily) >= 6 else ma5
        ret5 = latest_close / float(close.iloc[-5]) - 1.0
        if latest_close >= ma5 and ma5 >= ma5_prev:
            daily_5d_state = "UP"
            daily_score = 72.0 + min(ret5 * 220.0, 12.0)
            reasons.append("5 日线向上且收盘站上 5 日均线。")
        elif latest_close < ma5 and ma5 < ma5_prev:
            daily_5d_state = "DOWN"
            daily_score = 32.0 + max(ret5 * 180.0, -12.0)
            reasons.append("5 日线向下且收盘低于 5 日均线。")
        else:
            daily_5d_state = "MIXED"
            daily_score = 52.0 + max(min(ret5 * 160.0, 10.0), -10.0)
            reasons.append("5 日线方向未形成单边。")
    else:
        daily_5d_state = "INSUFFICIENT"
        reasons.append("5 日线样本不足。")

    weekly_state, weekly_score, weekly_reason = _period_trend_state(daily, period="W-FRI", min_periods=4, label="周线")
    monthly_state, monthly_score, monthly_reason = _period_trend_state(daily, period="ME", min_periods=3, label="月线")
    reasons.extend([weekly_reason, monthly_reason])
    score = 0.50 * daily_score + 0.30 * weekly_score + 0.20 * monthly_score
    return MultiPeriodTrend(
        score=round(clamp(score, 0.0, 100.0), 2),
        daily_5d_state=daily_5d_state,
        weekly_state=weekly_state,
        monthly_state=monthly_state,
        reasons=tuple(item for item in reasons if item)[:5],
    )


def _period_trend_state(daily: Any, *, period: str, min_periods: int, label: str) -> tuple[str, float, str]:
    import pandas as pd

    data = daily.copy()
    data["trade_date"] = pd.to_datetime(data["trade_date"])
    data = data.set_index("trade_date")
    periods = data.resample(period).agg(open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"))
    periods = periods.dropna(subset=["close"])
    if len(periods) < min_periods:
        return "INSUFFICIENT", 50.0, f"{label}样本不足，不作为强过滤。"
    close = periods["close"]
    ma_short = float(close.tail(min(2, len(close))).mean())
    ma_long = float(close.tail(min(min_periods, len(close))).mean())
    previous = float(close.iloc[-2])
    latest = float(close.iloc[-1])
    change = latest / previous - 1.0 if previous > 0 else 0.0
    if latest >= ma_short >= ma_long and change >= -0.005:
        return "UP", round(clamp(68.0 + change * 260.0, 60.0, 86.0), 2), f"{label}趋势向上或保持强势。"
    if latest < ma_short < ma_long and change <= 0.0:
        return "DOWN", round(clamp(36.0 + change * 220.0, 20.0, 45.0), 2), f"{label}趋势向下。"
    return "MIXED", round(clamp(52.0 + change * 180.0, 42.0, 62.0), 2), f"{label}趋势震荡。"
