"""Market environment filters for dividend-T backtests."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from typing import Any


MARKET_RISK_ON = "RISK_ON"
MARKET_NEUTRAL = "NEUTRAL"
MARKET_CAUTION = "CAUTION"
MARKET_RISK_OFF = "RISK_OFF"


@dataclass(frozen=True)
class MarketEnvironmentPoint:
    trade_date: date
    state: str
    score: float
    max_total_position_pct: float
    allow_new_buy: bool
    trend_score: float = 55.0
    breadth_score: float = 50.0
    amount_score: float = 50.0
    limit_structure_score: float = 50.0
    industry_diffusion_score: float = 50.0
    model_state_score: float = 50.0
    advance_ratio: float = 0.50
    above_ma20_ratio: float = 0.50
    positive_20d_ratio: float = 0.50
    amount_ratio20: float = 1.00
    limit_up_ratio: float = 0.00
    limit_down_ratio: float = 0.00
    industry_risk_on_ratio: float = 0.50
    model_holding_win_rate: float = 0.50
    model_holding_profit_spread: float = 0.50
    model_new_buy_success_rate: float = 0.50


@dataclass(frozen=True)
class MarketEnvironmentFilter:
    name: str
    points: tuple[MarketEnvironmentPoint, ...]

    def point_at(self, timestamp: Any) -> MarketEnvironmentPoint:
        import pandas as pd

        if not self.points:
            return MarketEnvironmentPoint(date.min, MARKET_NEUTRAL, 55.0, 1.0, True)
        target = pd.Timestamp(timestamp).date()
        selected = self.points[0]
        for point in self.points:
            if point.trade_date > target:
                break
            selected = point
        return selected


def build_market_environment_filter(frame: Any, *, name: str = "market") -> MarketEnvironmentFilter:
    """Build a daily market environment filter.

    A single proxy series keeps the legacy trend-only behaviour. A frame with
    ``symbol`` plus per-stock bars upgrades RISK_ON to a composite market state:
    trend, breadth, amount, limit-up/down structure, industry diffusion and
    optional model self-state metrics.
    """

    data = frame.copy()
    if "timestamp" not in data.columns or "close" not in data.columns:
        raise ValueError("market environment frame must include timestamp and close")
    if "symbol" in data.columns:
        return _build_composite_market_environment_filter(data, name=name)
    return _build_proxy_market_environment_filter(data, name=name)


def market_environment_point_with_model_state(
    point: MarketEnvironmentPoint,
    *,
    model_holding_win_rate: float,
    model_holding_profit_spread: float,
    model_new_buy_success_rate: float,
) -> MarketEnvironmentPoint:
    holding_win_rate = _clamp(model_holding_win_rate, 0.0, 1.0)
    holding_profit_spread = _clamp(model_holding_profit_spread, 0.0, 1.0)
    new_buy_success_rate = _clamp(model_new_buy_success_rate, 0.0, 1.0)
    model_state_score = _model_state_score(
        holding_win_rate=holding_win_rate,
        holding_profit_spread=holding_profit_spread,
        new_buy_success_rate=new_buy_success_rate,
    )
    if not _point_has_composite_market_inputs(point):
        return replace(
            point,
            model_state_score=round(model_state_score, 2),
            model_holding_win_rate=round(holding_win_rate, 4),
            model_holding_profit_spread=round(holding_profit_spread, 4),
            model_new_buy_success_rate=round(new_buy_success_rate, 4),
        )
    score = _composite_score(
        trend_score=point.trend_score,
        breadth_score=point.breadth_score,
        amount_score=point.amount_score,
        limit_structure_score=point.limit_structure_score,
        industry_diffusion_score=point.industry_diffusion_score,
        model_state_score=model_state_score,
    )
    state, cap, allow_new_buy = _composite_state(
        score=score,
        trend_score=point.trend_score,
        breadth_score=point.breadth_score,
        amount_score=point.amount_score,
        limit_structure_score=point.limit_structure_score,
        model_state_score=model_state_score,
        model_holding_win_rate=holding_win_rate,
        model_holding_profit_spread=holding_profit_spread,
        model_new_buy_success_rate=new_buy_success_rate,
        limit_up_ratio=point.limit_up_ratio,
        limit_down_ratio=point.limit_down_ratio,
    )
    return replace(
        point,
        state=state,
        score=round(score, 2),
        max_total_position_pct=cap,
        allow_new_buy=allow_new_buy,
        model_state_score=round(model_state_score, 2),
        model_holding_win_rate=round(holding_win_rate, 4),
        model_holding_profit_spread=round(holding_profit_spread, 4),
        model_new_buy_success_rate=round(new_buy_success_rate, 4),
    )


def _build_proxy_market_environment_filter(data: Any, *, name: str) -> MarketEnvironmentFilter:
    import pandas as pd

    data["timestamp"] = pd.to_datetime(data["timestamp"])
    data["trade_date"] = data["timestamp"].dt.date
    daily = data.sort_values("timestamp").groupby("trade_date", sort=True).agg(close=("close", "last")).reset_index()
    close = daily["close"].astype(float)
    trend_components = _trend_components(close)

    points: list[MarketEnvironmentPoint] = []
    for index, row in daily.iterrows():
        score = _legacy_trend_score_at(close, trend_components, index=index)
        state, cap, allow_new_buy = _state_from_score(score)
        points.append(
            MarketEnvironmentPoint(
                trade_date=row["trade_date"],
                state=state,
                score=round(score, 2),
                max_total_position_pct=cap,
                allow_new_buy=allow_new_buy,
                trend_score=round(score, 2),
            )
        )
    return MarketEnvironmentFilter(name=name, points=tuple(points))


def _build_composite_market_environment_filter(data: Any, *, name: str) -> MarketEnvironmentFilter:
    import pandas as pd

    data = data.copy()
    data["timestamp"] = pd.to_datetime(data["timestamp"])
    data["trade_date"] = data["timestamp"].dt.date
    data["symbol"] = data["symbol"].astype(str)
    if "amount" not in data.columns:
        volume = data["volume"] if "volume" in data.columns else 0.0
        data["amount"] = data["close"].astype(float) * volume
    if "industry" not in data.columns:
        data["industry"] = "UNKNOWN"
    daily = (
        data.sort_values("timestamp")
        .groupby(["trade_date", "symbol"], sort=True)
        .agg(
            close=("close", "last"),
            amount=("amount", "sum"),
            industry=("industry", "last"),
        )
        .reset_index()
    )
    if daily.empty:
        return MarketEnvironmentFilter(name=name, points=())

    close = daily.pivot(index="trade_date", columns="symbol", values="close").sort_index().astype(float)
    amount = daily.pivot(index="trade_date", columns="symbol", values="amount").reindex(close.index).astype(float)
    first_close = close.apply(_first_valid_float, axis=0)
    normalized_close = close.divide(first_close.where(first_close > 0), axis=1)
    proxy = normalized_close.dropna(how="all").mean(axis=1)
    trend_components = _trend_components(proxy)
    ret1 = close / close.shift(1) - 1.0
    ret20 = close / close.shift(20) - 1.0
    ma20 = close.rolling(20, min_periods=5).mean()
    daily_amount = amount.sum(axis=1, min_count=1)
    amount_ratio20 = daily_amount / daily_amount.rolling(20, min_periods=5).mean()
    industry_by_symbol = daily.dropna(subset=["industry"]).drop_duplicates("symbol", keep="last").set_index("symbol")["industry"].to_dict()
    model_state = _daily_model_state(data)

    points: list[MarketEnvironmentPoint] = []
    for index, trade_date in enumerate(close.index):
        trend_score = _legacy_trend_score_at(proxy, trend_components, index=index)
        advance_ratio = _row_rate(ret1.loc[trade_date] > 0.0)
        above_ma20_ratio = _row_rate(close.loc[trade_date] >= ma20.loc[trade_date])
        positive_20d_ratio = _row_rate(ret20.loc[trade_date] > 0.0)
        breadth_score = _breadth_score(
            advance_ratio=advance_ratio,
            above_ma20_ratio=above_ma20_ratio,
            positive_20d_ratio=positive_20d_ratio,
        )
        current_amount_ratio = _optional_float(amount_ratio20.loc[trade_date]) or 1.0
        amount_score = _amount_score(current_amount_ratio)
        limit_up_ratio = _row_rate(ret1.loc[trade_date] >= 0.095)
        limit_down_ratio = _row_rate(ret1.loc[trade_date] <= -0.095)
        limit_structure_score = _limit_structure_score(
            limit_up_ratio=limit_up_ratio,
            limit_down_ratio=limit_down_ratio,
            advance_ratio=advance_ratio,
        )
        industry_risk_on_ratio = _industry_risk_on_ratio(
            trade_date=trade_date,
            ret1=ret1,
            ret20=ret20,
            close=close,
            ma20=ma20,
            industry_by_symbol=industry_by_symbol,
        )
        industry_diffusion_score = _industry_diffusion_score(industry_risk_on_ratio)
        holding_win_rate, holding_profit_spread, new_buy_success_rate = model_state.get(
            trade_date,
            (0.50, 0.50, 0.50),
        )
        model_state_score = _model_state_score(
            holding_win_rate=holding_win_rate,
            holding_profit_spread=holding_profit_spread,
            new_buy_success_rate=new_buy_success_rate,
        )
        score = _composite_score(
            trend_score=trend_score,
            breadth_score=breadth_score,
            amount_score=amount_score,
            limit_structure_score=limit_structure_score,
            industry_diffusion_score=industry_diffusion_score,
            model_state_score=model_state_score,
        )
        state, cap, allow_new_buy = _composite_state(
            score=score,
            trend_score=trend_score,
            breadth_score=breadth_score,
            amount_score=amount_score,
            limit_structure_score=limit_structure_score,
            model_state_score=model_state_score,
            model_holding_win_rate=holding_win_rate,
            model_holding_profit_spread=holding_profit_spread,
            model_new_buy_success_rate=new_buy_success_rate,
            limit_up_ratio=limit_up_ratio,
            limit_down_ratio=limit_down_ratio,
        )
        points.append(
            MarketEnvironmentPoint(
                trade_date=trade_date,
                state=state,
                score=round(score, 2),
                max_total_position_pct=cap,
                allow_new_buy=allow_new_buy,
                trend_score=round(trend_score, 2),
                breadth_score=round(breadth_score, 2),
                amount_score=round(amount_score, 2),
                limit_structure_score=round(limit_structure_score, 2),
                industry_diffusion_score=round(industry_diffusion_score, 2),
                model_state_score=round(model_state_score, 2),
                advance_ratio=round(advance_ratio, 4),
                above_ma20_ratio=round(above_ma20_ratio, 4),
                positive_20d_ratio=round(positive_20d_ratio, 4),
                amount_ratio20=round(current_amount_ratio, 4),
                limit_up_ratio=round(limit_up_ratio, 4),
                limit_down_ratio=round(limit_down_ratio, 4),
                industry_risk_on_ratio=round(industry_risk_on_ratio, 4),
                model_holding_win_rate=round(holding_win_rate, 4),
                model_holding_profit_spread=round(holding_profit_spread, 4),
                model_new_buy_success_rate=round(new_buy_success_rate, 4),
            )
        )
    return MarketEnvironmentFilter(name=name, points=tuple(points))


def _point_has_composite_market_inputs(point: MarketEnvironmentPoint) -> bool:
    return (
        abs(point.breadth_score - 50.0) > 1e-9
        or abs(point.amount_score - 50.0) > 1e-9
        or abs(point.limit_structure_score - 50.0) > 1e-9
        or abs(point.industry_diffusion_score - 50.0) > 1e-9
        or abs(point.advance_ratio - 0.50) > 1e-9
    )


def _trend_components(close: Any) -> dict[str, Any]:
    ma20 = close.rolling(20, min_periods=5).mean()
    ma60 = close.rolling(60, min_periods=20).mean()
    high60 = close.rolling(60, min_periods=20).max()
    return {
        "ma20": ma20,
        "ma60": ma60,
        "ret5": close / close.shift(5) - 1.0,
        "ret20": close / close.shift(20) - 1.0,
        "drawdown60": close / high60 - 1.0,
    }


def _legacy_trend_score_at(close: Any, components: dict[str, Any], *, index: int) -> float:
    score = 55.0
    current = _optional_float(close.iloc[index])
    current_ma20 = _optional_float(components["ma20"].iloc[index])
    current_ma60 = _optional_float(components["ma60"].iloc[index])
    current_ret5 = _optional_float(components["ret5"].iloc[index]) or 0.0
    current_ret20 = _optional_float(components["ret20"].iloc[index]) or 0.0
    current_drawdown = _optional_float(components["drawdown60"].iloc[index]) or 0.0
    if current is not None and current_ma20 is not None:
        score += 12.0 if current >= current_ma20 else -14.0
    if current_ma20 is not None and current_ma60 is not None:
        score += 10.0 if current_ma20 >= current_ma60 else -12.0
    if current_ret20 >= 0.03:
        score += 10.0
    elif current_ret20 <= -0.06:
        score -= 16.0
    elif current_ret20 <= -0.03:
        score -= 8.0
    if current_ret5 <= -0.035:
        score -= 8.0
    elif current_ret5 >= 0.025:
        score += 5.0
    if current_drawdown <= -0.10:
        score -= 12.0
    elif current_drawdown <= -0.06:
        score -= 6.0
    return _clamp(score, 0.0, 100.0)


def _state_from_score(score: float) -> tuple[str, float, bool]:
    if score < 38.0:
        return MARKET_RISK_OFF, 0.10, False
    if score < 50.0:
        return MARKET_CAUTION, 0.35, True
    if score >= 68.0:
        return MARKET_RISK_ON, 1.00, True
    return MARKET_NEUTRAL, 0.70, True


def _composite_state(
    *,
    score: float,
    trend_score: float,
    breadth_score: float,
    amount_score: float,
    limit_structure_score: float,
    model_state_score: float,
    model_holding_win_rate: float = 0.50,
    model_holding_profit_spread: float = 0.50,
    model_new_buy_success_rate: float = 0.50,
    limit_up_ratio: float = 0.0,
    limit_down_ratio: float = 0.0,
) -> tuple[str, float, bool]:
    severe_limit_down = limit_down_ratio >= 0.055 and limit_down_ratio > limit_up_ratio * 1.8
    if score < 38.0 or severe_limit_down or (trend_score < 36.0 and breadth_score < 42.0):
        return MARKET_RISK_OFF, 0.10, False
    if _model_profit_diffusion_risk_on_override(
        score=score,
        trend_score=trend_score,
        breadth_score=breadth_score,
        amount_score=amount_score,
        limit_structure_score=limit_structure_score,
        model_state_score=model_state_score,
        model_holding_win_rate=model_holding_win_rate,
        model_holding_profit_spread=model_holding_profit_spread,
        model_new_buy_success_rate=model_new_buy_success_rate,
        limit_up_ratio=limit_up_ratio,
        limit_down_ratio=limit_down_ratio,
    ):
        cap = 1.00 if score >= 64.0 or model_holding_profit_spread >= 0.70 else 0.95
        return MARKET_RISK_ON, cap, True
    if score < 50.0 or breadth_score < 42.0 or amount_score < 35.0 or limit_structure_score < 34.0:
        return MARKET_CAUTION, 0.35, True
    if (
        score >= 68.0
        and trend_score >= 60.0
        and breadth_score >= 55.0
        and limit_structure_score >= 45.0
        and model_state_score >= 45.0
    ):
        return MARKET_RISK_ON, 1.00, True
    return MARKET_NEUTRAL, 0.70, True


def _model_profit_diffusion_risk_on_override(
    *,
    score: float,
    trend_score: float,
    breadth_score: float,
    amount_score: float,
    limit_structure_score: float,
    model_state_score: float,
    model_holding_win_rate: float,
    model_holding_profit_spread: float,
    model_new_buy_success_rate: float,
    limit_up_ratio: float,
    limit_down_ratio: float,
) -> bool:
    """Let the strategy's own broad profitability extend RISK_ON in structural rallies."""

    profit_diffusion = model_holding_win_rate >= 0.56 and model_holding_profit_spread >= 0.62
    strong_profit_diffusion = model_holding_win_rate >= 0.52 and model_holding_profit_spread >= 0.70
    if not (profit_diffusion or strong_profit_diffusion):
        return False
    if model_state_score < 60.0:
        return False
    if model_new_buy_success_rate < 0.45 and not strong_profit_diffusion:
        return False
    if trend_score < 45.0 or breadth_score < 38.0 or amount_score < 32.0 or limit_structure_score < 36.0:
        return False
    if limit_down_ratio >= 0.035 and limit_down_ratio > max(limit_up_ratio * 1.4, 0.018):
        return False
    return score >= 50.0 or (trend_score >= 54.0 and breadth_score >= 45.0)


def _composite_score(
    *,
    trend_score: float,
    breadth_score: float,
    amount_score: float,
    limit_structure_score: float,
    industry_diffusion_score: float,
    model_state_score: float,
) -> float:
    return _clamp(
        trend_score * 0.28
        + breadth_score * 0.22
        + amount_score * 0.16
        + limit_structure_score * 0.14
        + industry_diffusion_score * 0.12
        + model_state_score * 0.08,
        0.0,
        100.0,
    )


def _breadth_score(*, advance_ratio: float, above_ma20_ratio: float, positive_20d_ratio: float) -> float:
    return _clamp(20.0 + advance_ratio * 30.0 + above_ma20_ratio * 32.0 + positive_20d_ratio * 18.0, 0.0, 100.0)


def _amount_score(amount_ratio20: float) -> float:
    ratio = _clamp(amount_ratio20, 0.0, 3.0)
    return _clamp(50.0 + (ratio - 1.0) * 36.0, 15.0, 90.0)


def _limit_structure_score(*, limit_up_ratio: float, limit_down_ratio: float, advance_ratio: float) -> float:
    return _clamp(50.0 + limit_up_ratio * 420.0 - limit_down_ratio * 620.0 + (advance_ratio - 0.50) * 18.0, 10.0, 95.0)


def _industry_diffusion_score(industry_risk_on_ratio: float) -> float:
    return _clamp(30.0 + industry_risk_on_ratio * 60.0, 20.0, 95.0)


def _model_state_score(
    *,
    holding_win_rate: float,
    holding_profit_spread: float,
    new_buy_success_rate: float,
) -> float:
    return _clamp(
        50.0
        + (holding_win_rate - 0.50) * 35.0
        + (holding_profit_spread - 0.50) * 30.0
        + (new_buy_success_rate - 0.50) * 35.0,
        10.0,
        90.0,
    )


def _industry_risk_on_ratio(
    *,
    trade_date: Any,
    ret1: Any,
    ret20: Any,
    close: Any,
    ma20: Any,
    industry_by_symbol: dict[str, str],
) -> float:
    industries: dict[str, list[str]] = {}
    for symbol in close.columns:
        industries.setdefault(str(industry_by_symbol.get(symbol, "UNKNOWN") or "UNKNOWN"), []).append(symbol)
    states: list[bool] = []
    for symbols in industries.values():
        day_ret = ret1.loc[trade_date, symbols]
        day_close = close.loc[trade_date, symbols]
        day_ma20 = ma20.loc[trade_date, symbols]
        day_ret20 = ret20.loc[trade_date, symbols]
        valid = day_close.dropna()
        if valid.empty:
            continue
        advance = _row_rate(day_ret > 0.0)
        above = _row_rate(day_close >= day_ma20)
        medium_ret = _optional_float(day_ret20.mean()) or 0.0
        states.append((advance >= 0.55 and above >= 0.50) or medium_ret >= 0.02)
    if not states:
        return 0.50
    return sum(1 for state in states if state) / len(states)


def _daily_model_state(data: Any) -> dict[Any, tuple[float, float, float]]:
    columns = {
        "model_holding_win_rate": "model_holding_win_rate",
        "holding_win_rate": "model_holding_win_rate",
        "model_holding_profit_spread": "model_holding_profit_spread",
        "holding_profit_spread": "model_holding_profit_spread",
        "model_new_buy_success_rate": "model_new_buy_success_rate",
        "new_buy_success_rate": "model_new_buy_success_rate",
    }
    available = {source: target for source, target in columns.items() if source in data.columns}
    if not available:
        return {}
    renamed = data[["trade_date", *available]].rename(columns=available)
    grouped = renamed.groupby("trade_date", sort=True).mean(numeric_only=True)
    states: dict[Any, tuple[float, float, float]] = {}
    for trade_date, row in grouped.iterrows():
        states[trade_date] = (
            _clamp(_optional_float(row.get("model_holding_win_rate")) or 0.50, 0.0, 1.0),
            _clamp(_optional_float(row.get("model_holding_profit_spread")) or 0.50, 0.0, 1.0),
            _clamp(_optional_float(row.get("model_new_buy_success_rate")) or 0.50, 0.0, 1.0),
        )
    return states


def _row_rate(mask: Any) -> float:
    import pandas as pd

    clean = pd.Series(mask).dropna()
    if clean.empty:
        return 0.50
    return float(clean.astype(bool).mean())


def _first_valid_float(values: Any) -> float:
    clean = values.dropna()
    return float(clean.iloc[0]) if not clean.empty else float("nan")


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, float(value)))


def _optional_float(value: Any) -> float | None:
    try:
        import pandas as pd

        if pd.isna(value):
            return None
    except Exception:  # noqa: BLE001
        pass
    return float(value)
