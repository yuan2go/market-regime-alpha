"""Capital-flow features for the COSCO timing engine."""

from __future__ import annotations

from typing import Any

from market_regime_alpha.dividend_t.cosco_timing_types import CapitalFlowEstimate
from market_regime_alpha.dividend_t.scoring import clamp

def _capital_flow_confirms_buy(capital_flow: CapitalFlowEstimate, *, min_score: float = 62.0) -> bool:
    if capital_flow.confirmation_state == "CONFIRMED_INFLOW":
        return True
    if capital_flow.source_type == "REAL_MONEY_FLOW":
        return capital_flow.confirmation_score >= max(58.0, min_score - 4.0) and capital_flow.short_flow_ratio > 0.02
    return (
        capital_flow.confirmation_score >= min_score
        and capital_flow.short_flow_ratio >= 0.06
        and capital_flow.medium_flow_ratio >= 0.0
        and capital_flow.confidence >= 0.50
    )

def _capital_flow_estimate(frame: Any) -> CapitalFlowEstimate:
    data = frame.copy().sort_values("timestamp").reset_index(drop=True)
    if "amount" not in data.columns:
        data["amount"] = data["close"] * data["volume"]
    data["amount"] = data["amount"].fillna(data["close"] * data["volume"])
    signed_amount, source_type, source_reason = _signed_money_flow(data)

    short_ratio = _flow_ratio(signed_amount, data["amount"], 6)
    medium_ratio = _flow_ratio(signed_amount, data["amount"], 24)
    long_ratio = _flow_ratio(signed_amount, data["amount"], 96)
    persistence = _positive_flow_persistence(signed_amount, window=24)
    amount_expansion = _amount_expansion_ratio(data["amount"], short_window=6, base_window=48)
    current = float(data["close"].iloc[-1])
    vwap_24 = _vwap(data.tail(min(24, len(data))))
    vwap_edge = current / vwap_24 - 1.0 if vwap_24 > 0 else 0.0
    score = 50.0 + 24.0 * short_ratio + 18.0 * medium_ratio + 12.0 * long_ratio
    score += clamp((persistence - 0.50) * 18.0, -7.0, 7.0)
    score += clamp((amount_expansion - 1.00) * 8.0, -4.0, 6.0)
    score += clamp(vwap_edge * 900.0, -5.0, 6.0)
    if short_ratio > 0 and medium_ratio > 0:
        score += 6.0
    if short_ratio < 0 and medium_ratio < 0:
        score -= 8.0
    score = round(clamp(score, 0.0, 100.0), 2)
    confirmation_score = 50.0
    confirmation_score += 28.0 * short_ratio + 22.0 * medium_ratio + 12.0 * long_ratio
    confirmation_score += clamp((persistence - 0.50) * 24.0, -9.0, 9.0)
    confirmation_score += clamp((amount_expansion - 1.00) * 10.0, -5.0, 8.0)
    confirmation_score += clamp(vwap_edge * 1100.0, -6.0, 7.0)
    if source_type == "REAL_MONEY_FLOW":
        confirmation_score += 6.0
    confirmation_score = round(clamp(confirmation_score, 0.0, 100.0), 2)
    if score >= 65.0:
        state = "INFLOW"
    elif score <= 42.0:
        state = "OUTFLOW"
    else:
        state = "NEUTRAL"
    if confirmation_score >= 66.0 and short_ratio >= 0.08 and medium_ratio >= 0.02:
        confirmation_state = "CONFIRMED_INFLOW"
    elif confirmation_score <= 38.0 and short_ratio <= -0.08 and medium_ratio <= -0.02:
        confirmation_state = "CONFIRMED_OUTFLOW"
    elif short_ratio * medium_ratio < 0:
        confirmation_state = "DIVERGENT"
    else:
        confirmation_state = "UNCONFIRMED"
    confidence = 0.86 if source_type == "REAL_MONEY_FLOW" else 0.55
    reasons = (
        f"短周期资金流代理={short_ratio:.1%}，中周期={medium_ratio:.1%}，长周期={long_ratio:.1%}。",
        f"资金流状态={state}，分数={score:.1f}；确认={confirmation_state}，确认分={confirmation_score:.1f}。",
        f"资金流来源={source_type}，可信度={confidence:.0%}；{source_reason}",
    )
    return CapitalFlowEstimate(
        score=score,
        state=state,
        short_flow_ratio=round(short_ratio, 4),
        medium_flow_ratio=round(medium_ratio, 4),
        long_flow_ratio=round(long_ratio, 4),
        confirmation_score=confirmation_score,
        confirmation_state=confirmation_state,
        confidence=round(confidence, 2),
        source_type=source_type,
        reasons=reasons,
    )


def _signed_money_flow(data: Any) -> tuple[Any, str, str]:
    import pandas as pd

    real_flow = _first_numeric_series(
        data,
        (
            "main_net_inflow",
            "main_net_amount",
            "net_inflow",
            "large_net_inflow",
            "big_order_net_inflow",
            "super_large_net_inflow",
            "active_net_inflow",
        ),
    )
    if real_flow is not None:
        return real_flow.fillna(0.0), "REAL_MONEY_FLOW", "已识别真实资金流净额列，优先使用真实净流入。"

    buy_amount = _first_numeric_series(data, ("active_buy_amount", "buy_amount", "bid_buy_amount"))
    sell_amount = _first_numeric_series(data, ("active_sell_amount", "sell_amount", "ask_sell_amount"))
    if buy_amount is not None and sell_amount is not None:
        return (buy_amount.fillna(0.0) - sell_amount.fillna(0.0)), "REAL_MONEY_FLOW", "已识别主动买入/主动卖出金额列，按买卖差额估算净流入。"

    previous_close = data["close"].shift(1).fillna(data["open"])
    direction = data["close"] - data["open"]
    fallback_direction = data["close"] - previous_close
    signed_direction = direction.where(direction.abs() > 1e-9, fallback_direction)
    signed_amount = data["amount"] * signed_direction.apply(lambda value: 1.0 if value > 0 else (-1.0 if value < 0 else 0.0))
    return pd.to_numeric(signed_amount, errors="coerce").fillna(0.0), "OHLCV_PROXY", "未发现真实资金流列，当前使用 5 分钟 OHLCV 方向代理，不等同于软件大单净流入。"


def _first_numeric_series(data: Any, columns: tuple[str, ...]) -> Any | None:
    import pandas as pd

    for column in columns:
        if column in data.columns:
            return pd.to_numeric(data[column], errors="coerce")
    return None


def _flow_ratio(signed_amount: Any, amount: Any, window: int) -> float:
    denominator = float(amount.tail(min(window, len(amount))).sum())
    if denominator <= 0:
        return 0.0
    numerator = float(signed_amount.tail(min(window, len(signed_amount))).sum())
    return clamp(numerator / denominator, -1.0, 1.0)


def _positive_flow_persistence(signed_amount: Any, *, window: int) -> float:
    tail = signed_amount.tail(min(window, len(signed_amount)))
    if len(tail) == 0:
        return 0.5
    return float((tail > 0).mean())


def _amount_expansion_ratio(amount: Any, *, short_window: int, base_window: int) -> float:
    short = amount.tail(min(short_window, len(amount)))
    base = amount.tail(min(base_window, len(amount)))
    if len(short) == 0 or len(base) == 0:
        return 1.0
    base_mean = float(base.mean())
    if base_mean <= 0:
        return 1.0
    return clamp(float(short.mean()) / base_mean, 0.2, 3.0)


def _vwap(frame: Any) -> float:
    amount = float(frame["amount"].sum()) if "amount" in frame.columns else float((frame["close"] * frame["volume"]).sum())
    volume = float(frame["volume"].sum())
    if volume <= 0:
        return 0.0
    return amount / volume
