"""Chan-structure recognition for the dividend T-trading model.

This is a conservative, OHLCV-only implementation. It turns Chan concepts into
auditable features for gates, scores and backtests; it is not a discretionary
charting engine and does not claim perfect Chan labeling.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from market_regime_alpha.dividend_t.scoring import clamp


BUY_POINTS = {"buy1", "buy2", "buy3", "range_buy"}
SELL_POINTS = {"sell1", "sell2", "sell3"}


@dataclass(frozen=True)
class ChanFractal:
    index: int
    timestamp: str
    fractal_type: str
    price: float
    high: float
    low: float
    strength: float


@dataclass(frozen=True)
class ChanStroke:
    start_index: int
    end_index: int
    start_time: str
    end_time: str
    direction: str
    start_price: float
    end_price: float
    high: float
    low: float
    price_change_pct: float
    volume: float
    amount: float
    macd_area: float
    strength: float


@dataclass(frozen=True)
class ChanPivot:
    start_time: str
    end_time: str
    low: float
    high: float
    mid: float
    width: float
    score: float


@dataclass(frozen=True)
class ChanStructure:
    level: str
    score: float
    structure_type: str
    pivot_low: float | None
    pivot_high: float | None
    pivot_mid: float | None
    pivot_width: float | None
    trend_direction: str
    divergence_type: str
    divergence_score: float
    buy_point_type: str
    sell_point_type: str
    invalid_price: float | None
    fractal_count: int
    stroke_count: int
    pivot_count: int
    latest_fractal_type: str
    reasons: tuple[str, ...]


def analyze_chan_structure(
    frame: Any,
    *,
    level: str = "5m",
    min_kline_gap: int | None = None,
    min_price_change: float | None = None,
) -> ChanStructure:
    """Infer a compact Chan structure snapshot from OHLCV bars."""
    data = _prepare(frame)
    if len(data) < 12:
        return _neutral(level, "缠论样本不足：至少需要 12 根 K 线。")

    gap, change_threshold = _level_params(level, min_kline_gap=min_kline_gap, min_price_change=min_price_change)
    normalized = _add_macd(_normalize_inclusions(data))
    if len(normalized) < 8:
        return _neutral(level, "包含关系处理后 K 线过少，缠论结构按中性处理。")

    fractals = _find_fractals(normalized)
    strokes = _build_strokes(normalized, fractals, min_kline_gap=gap, min_price_change=change_threshold)
    pivots = _find_pivots(strokes)
    latest_pivot = pivots[-1] if pivots else None
    divergence_type, divergence_score = _detect_divergence(strokes)
    buy_point, sell_point, invalid_price = _classify_buy_sell(
        normalized,
        fractals=fractals,
        strokes=strokes,
        pivot=latest_pivot,
        divergence_type=divergence_type,
        divergence_score=divergence_score,
    )
    trend_direction = _trend_direction(normalized, strokes=strokes, pivot=latest_pivot)
    structure_type = _structure_type(normalized, pivot=latest_pivot, trend_direction=trend_direction, divergence_type=divergence_type)
    score = _chan_score(
        pivot=latest_pivot,
        trend_direction=trend_direction,
        divergence_type=divergence_type,
        divergence_score=divergence_score,
        buy_point=buy_point,
        sell_point=sell_point,
        stroke_count=len(strokes),
    )
    reasons = _reasons(
        pivot=latest_pivot,
        trend_direction=trend_direction,
        divergence_type=divergence_type,
        divergence_score=divergence_score,
        buy_point=buy_point,
        sell_point=sell_point,
        stroke_count=len(strokes),
    )
    return ChanStructure(
        level=level,
        score=round(score, 2),
        structure_type=structure_type,
        pivot_low=round(latest_pivot.low, 3) if latest_pivot else None,
        pivot_high=round(latest_pivot.high, 3) if latest_pivot else None,
        pivot_mid=round(latest_pivot.mid, 3) if latest_pivot else None,
        pivot_width=round(latest_pivot.width, 5) if latest_pivot else None,
        trend_direction=trend_direction,
        divergence_type=divergence_type,
        divergence_score=round(divergence_score, 2),
        buy_point_type=buy_point,
        sell_point_type=sell_point,
        invalid_price=round(invalid_price, 3) if invalid_price is not None else None,
        fractal_count=len(fractals),
        stroke_count=len(strokes),
        pivot_count=len(pivots),
        latest_fractal_type=fractals[-1].fractal_type if fractals else "none",
        reasons=reasons,
    )


def _prepare(frame: Any) -> Any:
    import pandas as pd

    required = {"timestamp", "open", "high", "low", "close", "volume"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"chan structure bars missing required fields: {', '.join(missing)}")
    data = frame.copy()
    data["timestamp"] = pd.to_datetime(data["timestamp"])
    data = data.sort_values("timestamp").reset_index(drop=True)
    if "amount" not in data.columns:
        data["amount"] = data["close"] * data["volume"]
    data["amount"] = data["amount"].fillna(data["close"] * data["volume"])
    return data


def _level_params(level: str, *, min_kline_gap: int | None, min_price_change: float | None) -> tuple[int, float]:
    normalized = level.lower()
    if normalized in {"daily", "day", "d", "1d"}:
        default_gap, default_change = 5, 0.020
    elif normalized in {"30m", "30min", "30"}:
        default_gap, default_change = 5, 0.010
    else:
        default_gap, default_change = 5, 0.005
    return min_kline_gap or default_gap, min_price_change or default_change


def _normalize_inclusions(data: Any) -> Any:
    import pandas as pd

    rows: list[dict[str, Any]] = []
    direction = "up"
    for source_index, row in data.iterrows():
        bar = {
            "timestamp": row["timestamp"],
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "volume": float(row["volume"]),
            "amount": float(row["amount"]),
            "source_start_index": int(source_index),
            "source_end_index": int(source_index),
        }
        if not rows:
            rows.append(bar)
            continue

        previous = rows[-1]
        contains = (previous["high"] >= bar["high"] and previous["low"] <= bar["low"]) or (
            previous["high"] <= bar["high"] and previous["low"] >= bar["low"]
        )
        if contains:
            if direction == "down":
                high = min(previous["high"], bar["high"])
                low = min(previous["low"], bar["low"])
            else:
                high = max(previous["high"], bar["high"])
                low = max(previous["low"], bar["low"])
            rows[-1] = {
                **previous,
                "timestamp": bar["timestamp"],
                "high": high,
                "low": low,
                "close": bar["close"],
                "volume": previous["volume"] + bar["volume"],
                "amount": previous["amount"] + bar["amount"],
                "source_end_index": bar["source_end_index"],
            }
            continue

        if bar["high"] > previous["high"] and bar["low"] > previous["low"]:
            direction = "up"
        elif bar["high"] < previous["high"] and bar["low"] < previous["low"]:
            direction = "down"
        rows.append(bar)

    return pd.DataFrame(rows).reset_index(drop=True)


def _add_macd(data: Any) -> Any:
    frame = data.copy()
    close = frame["close"]
    dif = close.ewm(span=12, adjust=False).mean() - close.ewm(span=26, adjust=False).mean()
    dea = dif.ewm(span=9, adjust=False).mean()
    frame["macd_hist"] = (dif - dea) * 2.0
    return frame


def _find_fractals(data: Any) -> list[ChanFractal]:
    fractals: list[ChanFractal] = []
    volume_ma = data["volume"].rolling(5, min_periods=1).mean()
    for index in range(1, len(data) - 1):
        previous = data.iloc[index - 1]
        current = data.iloc[index]
        following = data.iloc[index + 1]
        high = float(current["high"])
        low = float(current["low"])
        is_top = high > float(previous["high"]) and high > float(following["high"]) and low > float(previous["low"]) and low > float(following["low"])
        is_bottom = low < float(previous["low"]) and low < float(following["low"]) and high < float(previous["high"]) and high < float(following["high"])
        if not is_top and not is_bottom:
            continue
        fractal_type = "top" if is_top else "bottom"
        neighbor_extreme = max(float(previous["high"]), float(following["high"])) if is_top else min(float(previous["low"]), float(following["low"]))
        prominence = (high - neighbor_extreme) / high if is_top and high > 0 else (neighbor_extreme - low) / low if low > 0 else 0.0
        volume_ratio = float(current["volume"]) / max(float(volume_ma.iloc[index]), 1.0)
        strength = clamp(45.0 + prominence * 2500.0 + (volume_ratio - 1.0) * 12.0, 20.0, 100.0)
        fractals.append(
            ChanFractal(
                index=index,
                timestamp=str(current["timestamp"]),
                fractal_type=fractal_type,
                price=round(high if is_top else low, 3),
                high=round(high, 3),
                low=round(low, 3),
                strength=round(strength, 2),
            )
        )
    return fractals


def _build_strokes(
    data: Any,
    fractals: list[ChanFractal],
    *,
    min_kline_gap: int,
    min_price_change: float,
) -> list[ChanStroke]:
    accepted: list[ChanFractal] = []
    for fractal in fractals:
        if not accepted:
            accepted.append(fractal)
            continue
        previous = accepted[-1]
        if fractal.fractal_type == previous.fractal_type:
            if _more_extreme(fractal, previous):
                accepted[-1] = fractal
            continue
        if _valid_stroke(previous, fractal, min_kline_gap=min_kline_gap, min_price_change=min_price_change):
            accepted.append(fractal)

    strokes: list[ChanStroke] = []
    for start, end in zip(accepted, accepted[1:]):
        direction = "up" if start.fractal_type == "bottom" and end.fractal_type == "top" else "down"
        start_price = start.price
        end_price = end.price
        low_index, high_index = sorted((start.index, end.index))
        window = data.iloc[low_index : high_index + 1]
        high = float(window["high"].max())
        low = float(window["low"].min())
        volume = float(window["volume"].sum())
        amount = float(window["amount"].sum())
        hist = window["macd_hist"]
        if direction == "up":
            macd_area = float(hist[hist > 0].sum())
        else:
            macd_area = float((-hist[hist < 0]).sum())
        price_change = abs(end_price / start_price - 1.0) if start_price > 0 else 0.0
        strength = clamp(40.0 + price_change * 1000.0 + min(len(window), 12) * 2.0, 20.0, 100.0)
        strokes.append(
            ChanStroke(
                start_index=start.index,
                end_index=end.index,
                start_time=start.timestamp,
                end_time=end.timestamp,
                direction=direction,
                start_price=start_price,
                end_price=end_price,
                high=round(high, 3),
                low=round(low, 3),
                price_change_pct=round(price_change, 5),
                volume=round(volume, 2),
                amount=round(amount, 2),
                macd_area=round(max(macd_area, 0.0), 6),
                strength=round(strength, 2),
            )
        )
    return strokes


def _more_extreme(candidate: ChanFractal, current: ChanFractal) -> bool:
    if candidate.fractal_type == "top":
        return candidate.price > current.price
    return candidate.price < current.price


def _valid_stroke(
    start: ChanFractal,
    end: ChanFractal,
    *,
    min_kline_gap: int,
    min_price_change: float,
) -> bool:
    gap_ok = abs(end.index - start.index) >= min_kline_gap
    price_change = abs(end.price / start.price - 1.0) if start.price > 0 else 0.0
    return gap_ok and price_change >= min_price_change


def _find_pivots(strokes: list[ChanStroke]) -> list[ChanPivot]:
    pivots: list[ChanPivot] = []
    for index in range(0, len(strokes) - 2):
        window = strokes[index : index + 3]
        zg = min(stroke.high for stroke in window)
        zd = max(stroke.low for stroke in window)
        if zd > zg:
            continue
        mid = (zg + zd) / 2.0
        width = (zg - zd) / mid if mid > 0 else 0.0
        total_range = max(stroke.high for stroke in window) - min(stroke.low for stroke in window)
        overlap = (zg - zd) / total_range if total_range > 0 else 0.0
        touches = sum(1 for stroke in window if stroke.low <= zd * 1.003 or stroke.high >= zg * 0.997)
        width_score = clamp((0.10 - width) / 0.10 * 100.0, 20.0, 100.0)
        score = 0.45 * clamp(overlap * 220.0, 0.0, 100.0) + 0.25 * width_score + 0.20 * min(touches / 3.0 * 100.0, 100.0) + 10.0
        pivots.append(
            ChanPivot(
                start_time=window[0].start_time,
                end_time=window[-1].end_time,
                low=round(zd, 3),
                high=round(zg, 3),
                mid=round(mid, 3),
                width=round(width, 5),
                score=round(clamp(score, 0.0, 100.0), 2),
            )
        )
    return pivots


def _detect_divergence(strokes: list[ChanStroke]) -> tuple[str, float]:
    up_strokes = [stroke for stroke in strokes if stroke.direction == "up"]
    down_strokes = [stroke for stroke in strokes if stroke.direction == "down"]
    top_score = 0.0
    bottom_score = 0.0
    if len(up_strokes) >= 2:
        previous, latest = up_strokes[-2], up_strokes[-1]
        if latest.high > previous.high:
            top_score = _divergence_score(previous, latest, price_change=latest.high / previous.high - 1.0)
    if len(down_strokes) >= 2:
        previous, latest = down_strokes[-2], down_strokes[-1]
        if latest.low < previous.low:
            bottom_score = _divergence_score(previous, latest, price_change=previous.low / latest.low - 1.0)

    if top_score >= 62.0 and top_score >= bottom_score:
        return "top", top_score
    if bottom_score >= 62.0:
        return "bottom", bottom_score
    return "none", max(top_score, bottom_score)


def _divergence_score(previous: ChanStroke, latest: ChanStroke, *, price_change: float) -> float:
    macd_weaker = latest.macd_area < previous.macd_area * 0.92 if previous.macd_area > 0 else False
    volume_weaker = latest.volume < previous.volume * 0.92 if previous.volume > 0 else False
    amount_weaker = latest.amount < previous.amount * 0.92 if previous.amount > 0 else False
    score = 28.0 + clamp(price_change / 0.025 * 14.0, 0.0, 14.0)
    if macd_weaker:
        score += 25.0
    if volume_weaker:
        score += 18.0
    if amount_weaker:
        score += 15.0
    return clamp(score, 0.0, 100.0)


def _classify_buy_sell(
    data: Any,
    *,
    fractals: list[ChanFractal],
    strokes: list[ChanStroke],
    pivot: ChanPivot | None,
    divergence_type: str,
    divergence_score: float,
) -> tuple[str, str, float | None]:
    close = float(data["close"].iloc[-1])
    atr = _atr(data)
    recent_low = float(data["low"].tail(min(8, len(data))).min())
    avg_volume = float(data["volume"].tail(min(20, len(data))).mean())
    latest_volume = float(data["volume"].iloc[-1])
    volume_shrinking = latest_volume <= avg_volume * 0.88 if avg_volume > 0 else False
    price_turn_up = len(data) < 2 or close >= float(data["close"].iloc[-2])
    price_turn_down = len(data) >= 2 and close <= float(data["close"].iloc[-2])
    last_bottom = _last_fractal(fractals, "bottom")
    previous_bottom = _previous_fractal(fractals, "bottom")
    last_top = _last_fractal(fractals, "top")
    previous_top = _previous_fractal(fractals, "top")
    recent_fractal_limit = max(len(data) - 8, 0)

    buy_point = "none"
    sell_point = "none"
    invalid_price: float | None = None

    if pivot is not None:
        pullback_low = recent_low
        breakout_holds = close > pivot.high and pullback_low > pivot.high * 0.995
        if breakout_holds and price_turn_up and (volume_shrinking or latest_volume <= avg_volume * 1.15):
            buy_point = "buy3"
            invalid_price = max(pivot.high - 0.25 * atr, pullback_low - 0.35 * atr)
        elif close <= pivot.low + max((pivot.high - pivot.low) * 0.25, 0.35 * atr) and volume_shrinking and price_turn_up:
            buy_point = "range_buy"
            invalid_price = pivot.low - 0.45 * atr

    if buy_point == "none" and divergence_type == "bottom" and divergence_score >= 68.0 and last_bottom is not None and last_bottom.index >= recent_fractal_limit:
        buy_point = "buy1"
        invalid_price = min(last_bottom.price, recent_low) - 0.35 * atr

    if (
        buy_point == "none"
        and last_bottom is not None
        and previous_bottom is not None
        and last_bottom.price > previous_bottom.price
        and volume_shrinking
        and price_turn_up
    ):
        buy_point = "buy2"
        invalid_price = last_bottom.price - 0.35 * atr

    if divergence_type == "top" and divergence_score >= 68.0 and last_top is not None and last_top.index >= recent_fractal_limit:
        sell_point = "sell1"
    elif pivot is not None and close < pivot.low:
        sell_point = "sell3"
        invalid_price = pivot.low
    elif last_top is not None and previous_top is not None and last_top.price < previous_top.price and price_turn_down:
        sell_point = "sell2"

    return buy_point, sell_point, invalid_price


def _last_fractal(fractals: list[ChanFractal], fractal_type: str) -> ChanFractal | None:
    for fractal in reversed(fractals):
        if fractal.fractal_type == fractal_type:
            return fractal
    return None


def _previous_fractal(fractals: list[ChanFractal], fractal_type: str) -> ChanFractal | None:
    seen = 0
    for fractal in reversed(fractals):
        if fractal.fractal_type != fractal_type:
            continue
        seen += 1
        if seen == 2:
            return fractal
    return None


def _trend_direction(data: Any, *, strokes: list[ChanStroke], pivot: ChanPivot | None) -> str:
    close = float(data["close"].iloc[-1])
    if pivot is not None:
        if close > pivot.high:
            return "up"
        if close < pivot.low:
            return "down"
        return "range"
    if len(strokes) >= 4:
        recent = strokes[-4:]
        highs = [stroke.high for stroke in recent]
        lows = [stroke.low for stroke in recent]
        if highs[-1] > highs[0] and lows[-1] > lows[0]:
            return "up"
        if highs[-1] < highs[0] and lows[-1] < lows[0]:
            return "down"
    return "range"


def _structure_type(data: Any, *, pivot: ChanPivot | None, trend_direction: str, divergence_type: str) -> str:
    if divergence_type != "none":
        return "divergence"
    if pivot is None:
        return "trend" if trend_direction != "range" else "insufficient"
    close = float(data["close"].iloc[-1])
    if close > pivot.high:
        return "breakout"
    if close < pivot.low:
        return "breakdown"
    return "pivot"


def _chan_score(
    *,
    pivot: ChanPivot | None,
    trend_direction: str,
    divergence_type: str,
    divergence_score: float,
    buy_point: str,
    sell_point: str,
    stroke_count: int,
) -> float:
    score = 45.0
    if pivot is not None:
        score += pivot.score * 0.22
    else:
        score -= 8.0
    score += clamp((stroke_count - 3) * 3.0, 0.0, 12.0)
    if trend_direction == "up":
        score += 6.0
    elif trend_direction == "down":
        score -= 10.0
    if divergence_type == "bottom":
        score += clamp((divergence_score - 55.0) * 0.35, 0.0, 12.0)
    elif divergence_type == "top":
        score -= clamp((divergence_score - 55.0) * 0.45, 0.0, 18.0)
    if buy_point == "buy3":
        score += 22.0
    elif buy_point == "buy2":
        score += 18.0
    elif buy_point == "buy1":
        score += 14.0
    elif buy_point == "range_buy":
        score += 11.0
    if sell_point in SELL_POINTS:
        score -= 28.0 if sell_point == "sell3" else 20.0
    return clamp(score, 0.0, 100.0)


def _reasons(
    *,
    pivot: ChanPivot | None,
    trend_direction: str,
    divergence_type: str,
    divergence_score: float,
    buy_point: str,
    sell_point: str,
    stroke_count: int,
) -> tuple[str, ...]:
    reasons: list[str] = []
    if pivot is None:
        reasons.append(f"已识别 {stroke_count} 笔，但尚未形成有效三笔重叠中枢。")
    else:
        reasons.append(f"中枢区间 {pivot.low:.3f}-{pivot.high:.3f}，宽度 {pivot.width:.2%}，中枢分 {pivot.score:.1f}。")
    if trend_direction == "up":
        reasons.append("当前价格结构位于中枢上方或高低点抬升。")
    elif trend_direction == "down":
        reasons.append("当前价格结构跌破中枢或高低点下移。")
    else:
        reasons.append("当前仍按中枢震荡结构处理。")
    if divergence_type != "none":
        label = "顶背驰" if divergence_type == "top" else "底背驰"
        reasons.append(f"检测到{label}，背驰分 {divergence_score:.1f}。")
    if buy_point != "none":
        reasons.append(f"缠论买点={buy_point}，必须继续接受资金和风控门确认。")
    if sell_point != "none":
        reasons.append(f"缠论卖点={sell_point}，主动仓位需要优先降风险。")
    return tuple(reasons[:6])


def _atr(data: Any, *, window: int = 14) -> float:
    import pandas as pd

    previous_close = data["close"].shift(1)
    true_range = pd.concat(
        [
            data["high"] - data["low"],
            (data["high"] - previous_close).abs(),
            (data["low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    value = float(true_range.tail(min(window, len(true_range))).mean())
    close = float(data["close"].iloc[-1])
    return max(value, close * 0.002)


def _neutral(level: str, reason: str) -> ChanStructure:
    return ChanStructure(
        level=level,
        score=50.0,
        structure_type="insufficient",
        pivot_low=None,
        pivot_high=None,
        pivot_mid=None,
        pivot_width=None,
        trend_direction="range",
        divergence_type="none",
        divergence_score=0.0,
        buy_point_type="none",
        sell_point_type="none",
        invalid_price=None,
        fractal_count=0,
        stroke_count=0,
        pivot_count=0,
        latest_fractal_type="none",
        reasons=(reason,),
    )
