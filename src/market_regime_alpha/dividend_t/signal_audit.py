"""Offline, leakage-safe signal labels and audit statistics.

The module deliberately consumes the same execution resolver as counterfactual
replay.  It does not infer tradability from a local OHLC heuristic and it does
not read a sealed test segment.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from enum import StrEnum
from typing import Any, cast

from .backtest import (
    EXECUTION_CONSTRAINT_VERSION,
    CounterfactualExecutionContext,
    DividendTBacktestConfig,
    resolve_execution_request,
)
from .macd_experiments import ExecutionResolution


_BAR_COLUMNS = {"symbol", "timestamp", "open", "high", "low", "close"}
_CANDIDATE_COLUMNS = {
    "symbol",
    "timestamp",
    "action",
    "primary_setup_code",
    "signal_intent",
    "equity_before",
    "cash",
    "suggested_trade_pct",
}
_TEMPORARY_EXECUTION_BLOCKS = {"SUSPENDED", "LIMIT_UP", "LIMIT_DOWN", "LIMIT_LOCK"}
_STRATEGY_PARAMETERS = {"macd_score_weight", "mean_reversion_size_multiplier"}


class ThresholdComparison(StrEnum):
    GREATER_EQUAL = "GREATER_EQUAL"
    LESS_EQUAL = "LESS_EQUAL"
    BETWEEN = "BETWEEN"


def label_candidate_outcomes(
    candidates: Any,
    bars: Any,
    *,
    intraday_horizons: Sequence[int] = (1, 3, 6, 12, 24),
    daily_horizons: Sequence[int] = (1, 3, 5),
    trading_calendar: Any | None = None,
    execution_config: DividendTBacktestConfig | None = None,
    benchmark_bars: Any | None = None,
    industry_bars: Any | None = None,
) -> Any:
    """Label candidates from their first actually executable post-signal bar.

    Every fill, fee, lot, T+1, core-floor and reverse-T check is delegated to
    :func:`resolve_execution_request`.  Daily horizons use an explicit trading
    calendar; a missing or half-day bar is recorded as missing, never replaced
    by a fixed number of five-minute bars.
    """

    import pandas as pd

    _require_columns(candidates, _CANDIDATE_COLUMNS, name="candidates")
    _require_columns(bars, _BAR_COLUMNS, name="bars")
    _validate_horizons(intraday_horizons, daily_horizons)
    if daily_horizons and trading_calendar is None:
        raise ValueError("TRADING_CALENDAR_REQUIRED_FOR_DAILY_HORIZONS")
    config = execution_config or DividendTBacktestConfig()
    ordered = bars.copy()
    ordered["timestamp"] = pd.to_datetime(ordered["timestamp"])
    ordered = ordered.sort_values(["symbol", "timestamp"]).reset_index(drop=True)
    calendar_dates = _calendar_dates(trading_calendar) if trading_calendar is not None else ()
    rows: list[dict[str, object]] = []
    for candidate in candidates.copy().assign(timestamp=lambda frame: pd.to_datetime(frame["timestamp"])).to_dict(orient="records"):
        symbol = str(candidate["symbol"])
        candidate_time = pd.Timestamp(candidate["timestamp"])
        symbol_bars = ordered.loc[ordered["symbol"].astype(str) == symbol].reset_index(drop=True)
        context = _execution_context(candidate)
        resolution, entry_index = _find_next_execution(
            symbol_bars,
            symbol=symbol,
            candidate_time=candidate_time,
            action=str(candidate["action"]),
            context=context,
            config=config,
            trade_pct=float(candidate["suggested_trade_pct"]),
        )
        base = dict(candidate)
        base["timestamp"] = str(candidate_time)
        base["label_taxonomy"] = _label_taxonomy(str(candidate["action"]))
        _write_execution(base, resolution)
        base["entry_time"] = resolution.execution_time if resolution.executable else None
        base["entry_price"] = resolution.reference_fill_price if resolution.executable else None
        for horizon in intraday_horizons:
            _empty_horizon(base, f"bar_{horizon}")
        for horizon in daily_horizons:
            _empty_horizon(base, f"day_{horizon}")
        _empty_completed_t_cycle(base)
        if not resolution.executable or entry_index is None or resolution.reference_fill_price is None:
            rows.append(base)
            continue
        side = _side_for_action(str(candidate["action"]))
        entry_price = resolution.reference_fill_price
        for horizon in intraday_horizons:
            target_index = entry_index + horizon
            _write_horizon(
                base, symbol_bars, entry_index, target_index, f"bar_{horizon}", entry_price, side, config, candidate.get("stop_price")
            )
            _write_reference_return(
                base, candidate, symbol_bars, entry_index, target_index, f"bar_{horizon}", entry_price, side, benchmark_bars, "benchmark"
            )
            _write_reference_return(
                base, candidate, symbol_bars, entry_index, target_index, f"bar_{horizon}", entry_price, side, industry_bars, "industry"
            )
        for horizon in daily_horizons:
            daily_target_index, daily_reason = _daily_target_index(symbol_bars, entry_index, calendar_dates, horizon)
            _write_horizon(
                base,
                symbol_bars,
                entry_index,
                daily_target_index,
                f"day_{horizon}",
                entry_price,
                side,
                config,
                candidate.get("stop_price"),
                unavailable_reason=daily_reason,
            )
        if side == "SELL":
            _write_completed_t_cycle(base, symbol_bars, entry_index, resolution, context, config)
        rows.append(base)
    return pd.DataFrame(rows)


def calibration_report(
    labels: Any,
    *,
    horizon: str,
    bins: int = 10,
    strata: Sequence[str] = ("market_regime", "symbol_type"),
) -> dict[str, object]:
    """Report calibration for exactly one ``up_probability_<horizon>`` pair."""

    if not horizon or not isinstance(horizon, str):
        raise ValueError("CALIBRATION_HORIZON_REQUIRED")
    return _calibration_report_for_columns(
        labels,
        probability_column=f"up_probability_{horizon}",
        outcome_column=f"success_{horizon}",
        bins=bins,
        strata=strata,
    )


def local_threshold_sensitivity(
    labels: Any,
    *,
    feature: str,
    thresholds: Iterable[float | tuple[float, float]],
    return_column: str,
    success_column: str | None = None,
    comparison: ThresholdComparison = ThresholdComparison.GREATER_EQUAL,
) -> Any:
    """Report, but never select, a local feature threshold neighbourhood.

    Strategy parameters are intentionally excluded: those require four-profile
    replay, not post-hoc DataFrame filtering.
    """

    import pandas as pd

    if feature in _STRATEGY_PARAMETERS:
        raise ValueError("STRATEGY_PARAMETER_REQUIRES_FULL_EXPERIMENT")
    _require_columns(labels, {feature, return_column}, name="labels")
    values = tuple(thresholds)
    if not values:
        raise ValueError("thresholds must be non-empty")
    rows: list[dict[str, object]] = []
    for threshold in _normalized_thresholds(values, comparison):
        numeric = labels[feature].astype(float)
        if comparison is ThresholdComparison.GREATER_EQUAL:
            selected = labels.loc[numeric >= cast(float, threshold)]
            payload: dict[str, object] = {"threshold": threshold}
        elif comparison is ThresholdComparison.LESS_EQUAL:
            selected = labels.loc[numeric <= cast(float, threshold)]
            payload = {"threshold": threshold}
        else:
            lower, upper = cast(tuple[float, float], threshold)
            selected = labels.loc[(numeric >= lower) & (numeric <= upper)]
            payload = {"lower": lower, "upper": upper}
        count = len(selected)
        row = {
            "feature": feature,
            "comparison": comparison.value,
            **payload,
            "selected_count": count,
            "coverage": count / max(len(labels), 1),
            "mean_return": float(selected[return_column].mean()) if count else None,
        }
        if success_column is not None and success_column in selected.columns:
            row["success_rate"] = float(selected[success_column].mean()) if count else None
        rows.append(row)
    return pd.DataFrame(rows)


def sell_side_gap_report(labels: Any) -> dict[str, object]:
    """Keep discretionary T sell assessment distinct from hard-risk outcomes."""

    _require_columns(labels, {"label_taxonomy"}, name="labels")
    ordinary = labels.loc[labels["label_taxonomy"].isin({"HIGH_SELL_T", "TAKE_PROFIT_T", "REVERSE_T_SELL"})]
    hard_risk = labels.loc[labels["label_taxonomy"] == "RISK_EXIT"]
    return {
        "ordinary_sell_t": _ordinary_sell_summary(ordinary),
        "hard_risk_exit": {
            "count": int(len(hard_risk)),
            "mean_max_adverse_excursion": _mean_if_present(hard_risk, "max_adverse_excursion"),
            "mean_avoided_loss": _mean_if_present(hard_risk, "avoided_loss"),
            "evaluation": "tail-risk-and-avoided-loss-only",
        },
        "gaps": "SELL_T_TIMING remains a WAIT path until the independent sell-side action specification is implemented.",
    }


def audit_report(labels: Any) -> dict[str, object]:
    """Produce research-only, horizon-explicit diagnostics for non-sealed data."""

    report: dict[str, object] = {
        "scope": "TRAIN_VALIDATION_REHEARSAL_ONLY",
        "label_count": int(len(labels)),
        "by_primary_setup": _count_by(labels, "primary_setup_code"),
        "by_signal_intent": _count_by(labels, "signal_intent"),
        "by_market_regime": _count_by(labels, "market_regime"),
        "by_symbol": _count_by(labels, "symbol"),
        "by_industry": _count_by(labels, "industry"),
        "by_volatility_bucket": _count_by(labels, "volatility_bucket"),
        "by_trend_state": _count_by(labels, "trend_state"),
        "by_holding_period": _count_by(labels, "holding_period_bucket"),
        "by_label_taxonomy": _count_by(labels, "label_taxonomy"),
        "sell_side_gap": sell_side_gap_report(labels),
        "calibration": {},
        "threshold_sensitivity": {},
        "strategy_parameter_rule": "macd_score_weight and mean_reversion_size_multiplier require complete experiment replays",
        "parameter_selection_rule": "report local neighborhoods and stability; never select an isolated best return",
    }
    for column in labels.columns:
        if column.startswith("up_probability_"):
            horizon = column.removeprefix("up_probability_")
            outcome = f"success_{horizon}"
            if outcome in labels.columns:
                cast(dict[str, object], report["calibration"])[horizon] = calibration_report(labels, horizon=horizon)
    for feature, thresholds, comparison in (
        ("force_buy_edge", (52.0, 60.0, 68.0), ThresholdComparison.GREATER_EQUAL),
        ("buy_strength_score", (58.0, 64.0, 70.0), ThresholdComparison.GREATER_EQUAL),
        ("sell_pressure", (60.0, 70.0, 80.0), ThresholdComparison.LESS_EQUAL),
        ("capital_flow", (55.0, 65.0, 75.0), ThresholdComparison.GREATER_EQUAL),
        ("multi_period_trend", (55.0, 65.0, 75.0), ThresholdComparison.GREATER_EQUAL),
        ("risk_reward", (1.0, 1.2, 1.5), ThresholdComparison.GREATER_EQUAL),
        ("breakout", (70.0, 80.0, 90.0), ThresholdComparison.GREATER_EQUAL),
    ):
        if feature in labels.columns and "cost_adjusted_return_bar_1" in labels.columns:
            cast(dict[str, object], report["threshold_sensitivity"])[feature] = local_threshold_sensitivity(
                labels,
                feature=feature,
                thresholds=thresholds,
                return_column="cost_adjusted_return_bar_1",
                success_column="success_bar_1",
                comparison=comparison,
            ).to_dict(orient="records")
    return report


def _find_next_execution(
    bars: Any,
    *,
    symbol: str,
    candidate_time: Any,
    action: str,
    context: CounterfactualExecutionContext,
    config: DividendTBacktestConfig,
    trade_pct: float,
) -> tuple[ExecutionResolution, int | None]:
    for index, row in bars.loc[bars["timestamp"] > candidate_time].iterrows():
        resolution = resolve_execution_request(
            signal=action,
            symbol=symbol,
            candidate_bar_close_time=str(candidate_time),
            next_bar=row,
            context=context,
            config=config,
            trade_pct=trade_pct,
        )
        if resolution.executable:
            return resolution, int(index)
        if resolution.block_reason not in _TEMPORARY_EXECUTION_BLOCKS:
            return resolution, None
    return ExecutionResolution(False, "NO_NEXT_EXECUTABLE_BAR", None, None, 0, 0.0, 0.0, 0.0, EXECUTION_CONSTRAINT_VERSION), None


def _execution_context(candidate: dict[str, object]) -> CounterfactualExecutionContext:
    def integer(name: str) -> int:
        value = candidate.get(name, 0)
        if value is None:
            return 0
        try:
            number = float(cast(str | int | float, value))
        except (TypeError, ValueError):
            return 0
        return int(number) if math.isfinite(number) else 0

    return CounterfactualExecutionContext(
        equity_before=_required_float(candidate, "equity_before"),
        cash=_required_float(candidate, "cash"),
        total_sell_shares=integer("total_position_shares"),
        sellable_shares=integer("sellable_qty"),
        previous_daily_close=_optional_float(candidate.get("previous_daily_close")),
        base_shares=integer("base_position_shares"),
        base_locked_shares=integer("base_locked_shares"),
        t_shares=integer("t_shares"),
        t_locked_shares=integer("t_locked_shares"),
        core_position_floor_pct=_optional_float(candidate.get("core_position_floor_pct")) or 0.0,
        hard_risk_exit=bool(candidate.get("hard_risk_exit", False)),
        pending_buyback_shares=integer("pending_buyback_shares"),
        pending_buyback_target_price=_optional_float(candidate.get("buyback_target_price")),
    )


def _write_execution(base: dict[str, object], resolution: ExecutionResolution) -> None:
    base["actual_executable"] = resolution.executable
    base["execution_block_reason"] = resolution.block_reason
    base["execution_time"] = resolution.execution_time
    base["execution_price"] = resolution.reference_fill_price
    base["execution_quantity"] = resolution.shares
    base["execution_cost"] = resolution.execution_cost
    base["execution_constraint_version"] = resolution.execution_constraint_version


def _empty_horizon(base: dict[str, object], suffix: str) -> None:
    for name in ("gross_return", "cost_adjusted_return", "success", "mfe", "mae", "stop_triggered", "horizon_end_time"):
        base[f"{name}_{suffix}"] = None
    base[f"horizon_reason_{suffix}"] = None
    if base.get("label_taxonomy") in {"HIGH_SELL_T", "TAKE_PROFIT_T", "REVERSE_T_SELL"}:
        base[f"directional_decline_label_{suffix}"] = None


def _write_horizon(
    base: dict[str, object],
    bars: Any,
    entry_index: int,
    target_index: int | None,
    suffix: str,
    entry_price: float,
    side: str,
    config: DividendTBacktestConfig,
    stop: object,
    *,
    unavailable_reason: str | None = None,
) -> None:
    if target_index is None or target_index >= len(bars):
        base[f"horizon_reason_{suffix}"] = unavailable_reason or "HORIZON_OUT_OF_RANGE"
        return
    forward = bars.iloc[entry_index : target_index + 1]
    target = bars.iloc[target_index]
    close = float(target["close"])
    gross = close / entry_price - 1.0 if side == "BUY" else entry_price / close - 1.0
    costs = _round_trip_cost(entry_price, close, config, side)
    base[f"horizon_end_time_{suffix}"] = str(target["timestamp"])
    base[f"gross_return_{suffix}"] = gross
    base[f"cost_adjusted_return_{suffix}"] = gross - costs
    base[f"success_{suffix}"] = int(gross - costs > 0.0)
    base[f"mfe_{suffix}"], base[f"mae_{suffix}"] = _mfe_mae(forward, entry_price=entry_price, side=side)
    base[f"stop_triggered_{suffix}"] = _stop_triggered(forward, stop, side=side)
    if f"directional_decline_label_{suffix}" in base:
        base[f"directional_decline_label_{suffix}"] = int(close < entry_price)


def _write_completed_t_cycle(
    base: dict[str, object],
    bars: Any,
    entry_index: int,
    sell: ExecutionResolution,
    context: CounterfactualExecutionContext,
    config: DividendTBacktestConfig,
) -> None:
    target = context.pending_buyback_target_price
    if target is None:
        base["completed_t_cycle_reason"] = "BUYBACK_TARGET_MISSING"
        return
    if sell.reference_fill_price is None:
        base["completed_t_cycle_reason"] = "SELL_NOT_EXECUTED"
        return
    buyback_context = CounterfactualExecutionContext(
        equity_before=context.equity_before,
        cash=context.cash + sell.reference_fill_price * sell.shares - sell.fee_amount,
        pending_buyback_shares=sell.shares,
        pending_buyback_target_price=target,
    )
    for _, row in bars.iloc[entry_index + 1 :].iterrows():
        resolution = resolve_execution_request(
            signal="BUY_BACK_REVERSE_T",
            symbol=str(row["symbol"]),
            candidate_bar_close_time=sell.execution_time or str(row["timestamp"]),
            next_bar=row,
            context=buyback_context,
            config=config,
            trade_pct=1.0,
        )
        if resolution.block_reason in _TEMPORARY_EXECUTION_BLOCKS:
            continue
        if not resolution.executable:
            base["completed_t_cycle_reason"] = resolution.block_reason
            return
        _write_buyback(base, resolution)
        proceeds = sell.reference_fill_price * sell.shares - sell.fee_amount
        cost = (
            resolution.reference_fill_price * resolution.shares + resolution.fee_amount
            if resolution.reference_fill_price is not None
            else math.inf
        )
        base["completed_t_cycle_label"] = int(resolution.shares == sell.shares and proceeds > cost)
        base["completed_t_cycle_reason"] = "COMPLETED" if base["completed_t_cycle_label"] else "PARTIAL_OR_UNPROFITABLE_BUYBACK"
        return
    base["completed_t_cycle_reason"] = "BUYBACK_NOT_REACHED"


def _empty_completed_t_cycle(base: dict[str, object]) -> None:
    base["completed_t_cycle_label"] = None
    base["completed_t_cycle_reason"] = None
    for name in ("buyback_execution_time", "buyback_execution_price", "buyback_execution_quantity", "buyback_execution_cost"):
        base[name] = None


def _write_buyback(base: dict[str, object], resolution: ExecutionResolution) -> None:
    base["buyback_execution_time"] = resolution.execution_time
    base["buyback_execution_price"] = resolution.reference_fill_price
    base["buyback_execution_quantity"] = resolution.shares
    base["buyback_execution_cost"] = resolution.execution_cost


def _calendar_dates(calendar: Any) -> tuple[object, ...]:
    import pandas as pd

    _require_columns(calendar, {"trade_date"}, name="trading_calendar")
    dates = tuple(sorted({pd.Timestamp(value).date() for value in calendar["trade_date"]}))
    if not dates:
        raise ValueError("TRADING_CALENDAR_EMPTY")
    return dates


def _daily_target_index(bars: Any, entry_index: int, calendar_dates: tuple[object, ...], horizon: int) -> tuple[int | None, str | None]:
    import pandas as pd

    entry_date = pd.Timestamp(bars.iloc[entry_index]["timestamp"]).date()
    try:
        date_index = calendar_dates.index(entry_date)
    except ValueError as exc:
        raise ValueError("EXECUTION_DATE_NOT_IN_TRADING_CALENDAR") from exc
    target_position = date_index + horizon
    if target_position >= len(calendar_dates):
        return None, "HORIZON_OUT_OF_RANGE"
    target_date = calendar_dates[target_position]
    indices = bars.index[pd.to_datetime(bars["timestamp"]).dt.date == target_date]
    return (int(indices[-1]), None) if len(indices) else (None, "HORIZON_BAR_MISSING")


def _write_reference_return(
    base: dict[str, object],
    candidate: dict[str, object],
    own_bars: Any,
    entry_index: int,
    target_index: int,
    suffix: str,
    entry_price: float,
    side: str,
    reference: Any | None,
    prefix: str,
) -> None:
    key = f"{prefix}_excess_return_{suffix}"
    reason_key = f"{prefix}_reference_reason_{suffix}"
    base[key] = None
    base[reason_key] = None
    if target_index >= len(own_bars):
        base[reason_key] = "OWN_HORIZON_UNAVAILABLE"
        return
    required = {"timestamp", "close"}
    identity = "benchmark_symbol" if prefix == "benchmark" else "industry_id"
    reference_identity = "symbol" if prefix == "benchmark" else "industry_id"
    if reference is None:
        base[reason_key] = "REFERENCE_SERIES_MISSING"
        return
    _require_columns(reference, required | {reference_identity}, name=f"{prefix}_bars")
    requested = candidate.get(identity)
    if requested in {None, ""}:
        base[reason_key] = f"{identity.upper()}_MISSING"
        return
    data = reference.loc[reference[reference_identity].astype(str) == str(requested)].copy()
    import pandas as pd

    data["timestamp"] = pd.to_datetime(data["timestamp"])
    start = pd.Timestamp(own_bars.iloc[entry_index]["timestamp"])
    end = pd.Timestamp(own_bars.iloc[target_index]["timestamp"])
    start_row = data.loc[data["timestamp"] == start]
    end_row = data.loc[data["timestamp"] == end]
    if start_row.empty or end_row.empty:
        base[reason_key] = "REFERENCE_TIMESTAMP_MISSING"
        return
    reference_return = float(end_row.iloc[-1]["close"]) / float(start_row.iloc[-1]["close"]) - 1.0
    own = base.get(f"gross_return_{suffix}")
    if own is None:
        base[reason_key] = "OWN_RETURN_MISSING"
        return
    base[key] = float(cast(float, own)) - (reference_return if side == "BUY" else -reference_return)


def _calibration_report_for_columns(
    labels: Any, *, probability_column: str, outcome_column: str, bins: int, strata: Sequence[str]
) -> dict[str, object]:
    if isinstance(bins, bool) or not isinstance(bins, int) or bins < 2:
        raise ValueError("bins must be an integer >= 2")
    _require_columns(labels, {probability_column, outcome_column}, name="labels")
    valid = labels[[probability_column, outcome_column, *[item for item in strata if item in labels.columns]]].dropna()
    probabilities = [float(value) for value in valid[probability_column]]
    outcomes = [float(value) for value in valid[outcome_column]]
    if any(not math.isfinite(value) or not 0.0 <= value <= 1.0 for value in probabilities):
        raise ValueError("probabilities must be finite values in [0, 1]")
    if any(value not in {0.0, 1.0} for value in outcomes):
        raise ValueError("calibration outcomes must be binary")
    report = _calibration_values(probabilities, outcomes, bins=bins)
    report["horizon_probability_column"] = probability_column
    report["horizon_outcome_column"] = outcome_column
    by_stratum: dict[str, dict[str, object]] = {}
    for stratum in strata:
        if stratum in valid.columns:
            by_stratum[stratum] = {
                str(name): _calibration_values(
                    [float(value) for value in group[probability_column]], [float(value) for value in group[outcome_column]], bins=bins
                )
                for name, group in valid.groupby(stratum, dropna=False, sort=True)
            }
    report["by_stratum"] = by_stratum
    return report


def _normalized_thresholds(
    values: tuple[float | tuple[float, float], ...], comparison: ThresholdComparison
) -> tuple[float | tuple[float, float], ...]:
    if comparison is ThresholdComparison.BETWEEN:
        ranges = tuple((float(item[0]), float(item[1])) for item in values if isinstance(item, tuple) and len(item) == 2)
        if len(ranges) != len(values) or any(not math.isfinite(lo) or not math.isfinite(hi) or lo > hi for lo, hi in ranges):
            raise ValueError("BETWEEN thresholds must be finite (lower, upper) pairs")
        return tuple(sorted(set(ranges)))
    scalars = tuple(float(item) for item in values if not isinstance(item, tuple))
    if len(scalars) != len(values) or any(not math.isfinite(item) for item in scalars):
        raise ValueError("thresholds must be finite scalars")
    return tuple(sorted(set(scalars)))


def _validate_horizons(intraday: Sequence[int], daily: Sequence[int]) -> None:
    if any(isinstance(item, bool) or not isinstance(item, int) or item <= 0 for item in (*intraday, *daily)):
        raise ValueError("label horizons must be positive integers")


def _round_trip_cost(entry: float, exit_price: float, config: DividendTBacktestConfig, side: str) -> float:
    if side == "BUY":
        gross = exit_price / entry - 1.0
        net = (exit_price * (1.0 - config.commission_rate - config.stamp_duty_rate)) / (entry * (1.0 + config.commission_rate)) - 1.0
    else:
        gross = entry / exit_price - 1.0
        net = (entry * (1.0 - config.commission_rate - config.stamp_duty_rate)) / (exit_price * (1.0 + config.commission_rate)) - 1.0
    return gross - net


def _mfe_mae(forward: Any, *, entry_price: float, side: str) -> tuple[float, float]:
    high = float(forward["high"].max())
    low = float(forward["low"].min())
    return (high / entry_price - 1.0, low / entry_price - 1.0) if side == "BUY" else (entry_price / low - 1.0, entry_price / high - 1.0)


def _stop_triggered(forward: Any, stop: object, *, side: str) -> bool | None:
    value = _optional_float(stop)
    if value is None:
        return None
    return bool(float(forward["low"].min()) <= value) if side == "BUY" else bool(float(forward["high"].max()) >= value)


def _side_for_action(action: str) -> str:
    return "SELL" if action in {"SELL_T", "TAKE_PROFIT_T", "REDUCE_T", "EXIT_T", "STOP_T", "REVERSE_T_SELL", "CLEAR", "REDUCE"} else "BUY"


def _label_taxonomy(action: str) -> str:
    if action == "SELL_T":
        return "HIGH_SELL_T"
    if action == "TAKE_PROFIT_T":
        return "TAKE_PROFIT_T"
    if action in {"CLEAR", "REDUCE", "EXIT_T", "STOP_T"}:
        return "RISK_EXIT"
    if action == "REVERSE_T_SELL":
        return "REVERSE_T_SELL"
    return "BUY_ENTRY"


def _require_columns(frame: Any, required: set[str], *, name: str) -> None:
    missing = sorted(required - set(getattr(frame, "columns", ())))
    if missing:
        raise ValueError(f"{name} missing required columns: {', '.join(missing)}")


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        number = float(cast(str | int | float, value))
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _required_float(candidate: dict[str, object], name: str) -> float:
    number = _optional_float(candidate.get(name))
    if number is None:
        raise ValueError(f"INVALID_EXECUTION_CONTEXT_{name.upper()}")
    return number


def _calibration_values(probabilities: list[float], outcomes: list[float], *, bins: int) -> dict[str, object]:
    if not probabilities:
        return {"count": 0, "brier_score": None, "log_loss": None, "reliability_curve": []}
    brier = sum((p - y) ** 2 for p, y in zip(probabilities, outcomes, strict=True)) / len(probabilities)
    epsilon = 1e-15
    log_loss = -sum(
        y * math.log(max(p, epsilon)) + (1.0 - y) * math.log(max(1.0 - p, epsilon)) for p, y in zip(probabilities, outcomes, strict=True)
    ) / len(probabilities)
    grouped: list[list[tuple[float, float]]] = [[] for _ in range(bins)]
    for probability, outcome in zip(probabilities, outcomes, strict=True):
        grouped[min(int(probability * bins), bins - 1)].append((probability, outcome))
    curve = [
        {
            "lower": i / bins,
            "upper": (i + 1) / bins,
            "count": len(items),
            "mean_predicted": sum(p for p, _ in items) / len(items),
            "observed_rate": sum(y for _, y in items) / len(items),
        }
        for i, items in enumerate(grouped)
        if items
    ]
    return {"count": len(probabilities), "brier_score": brier, "log_loss": log_loss, "reliability_curve": curve}


def _ordinary_sell_summary(frame: Any) -> dict[str, object]:
    payload: dict[str, object] = {"count": int(len(frame))}
    if "directional_decline_label_bar_1" in frame.columns:
        payload["directional_hit_rate"] = float(frame["directional_decline_label_bar_1"].mean()) if len(frame) else None
    if "completed_t_cycle_label" in frame.columns:
        payload["completed_t_cycle_rate"] = float(frame["completed_t_cycle_label"].mean()) if len(frame) else None
    return payload


def _mean_if_present(frame: Any, column: str) -> float | None:
    return float(frame[column].dropna().mean()) if column in frame.columns and not frame[column].dropna().empty else None


def _count_by(frame: Any, column: str) -> dict[str, int]:
    return {str(key): int(value) for key, value in frame.groupby(column, dropna=False).size().items()} if column in frame.columns else {}
