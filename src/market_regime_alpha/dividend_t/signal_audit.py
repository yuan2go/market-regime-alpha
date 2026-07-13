"""Leakage-safe candidate labels, calibration, and threshold research reports.

These utilities are deliberately offline-only.  They label a candidate from the
next executable bar and later bars; they neither alter live candidates nor
select production parameters.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from typing import Any, cast


_BAR_COLUMNS = {"symbol", "timestamp", "open", "high", "low", "close"}
_CANDIDATE_COLUMNS = {"symbol", "timestamp", "action", "primary_setup_code", "signal_intent"}


def label_candidate_outcomes(
    candidates: Any,
    bars: Any,
    *,
    intraday_horizons: Sequence[int] = (1, 3, 6, 12, 24),
    daily_horizons: Sequence[int] = (1, 3, 5),
    bars_per_day: int = 48,
    round_trip_cost_bps: float = 20.0,
    benchmark_bars: Any | None = None,
    industry_bars: Any | None = None,
) -> Any:
    """Label candidates with only information available after their next fill.

    The entry price is always the next executable bar's *open*.  Subsequent
    MFE/MAE uses only bars after that fill.  Candidate-bar high/low is never
    used for entry or outcome construction.
    """

    import pandas as pd

    _require_columns(candidates, _CANDIDATE_COLUMNS, name="candidates")
    _require_columns(bars, _BAR_COLUMNS, name="bars")
    if bars_per_day <= 0 or isinstance(bars_per_day, bool):
        raise ValueError("bars_per_day must be a positive integer")
    if not math.isfinite(round_trip_cost_bps) or round_trip_cost_bps < 0.0:
        raise ValueError("round_trip_cost_bps must be finite and non-negative")
    if any(isinstance(item, bool) or not isinstance(item, int) or item <= 0 for item in (*intraday_horizons, *daily_horizons)):
        raise ValueError("label horizons must be positive integers")

    ordered_bars = bars.copy()
    ordered_bars["timestamp"] = pd.to_datetime(ordered_bars["timestamp"])
    ordered_bars = ordered_bars.sort_values(["symbol", "timestamp"]).reset_index(drop=True)
    candidates_copy = candidates.copy()
    candidates_copy["timestamp"] = pd.to_datetime(candidates_copy["timestamp"])
    cost = float(round_trip_cost_bps) / 10_000.0
    rows: list[dict[str, object]] = []
    for candidate in candidates_copy.to_dict(orient="records"):
        symbol = str(candidate["symbol"])
        timestamp = pd.Timestamp(candidate["timestamp"])
        symbol_bars = ordered_bars.loc[ordered_bars["symbol"].astype(str) == symbol].reset_index(drop=True)
        action = str(candidate["action"])
        side = _side_for_action(action)
        entry_index = _next_executable_index(symbol_bars, after=timestamp, side=side)
        base = dict(candidate)
        base["timestamp"] = str(timestamp)
        base["label_taxonomy"] = _label_taxonomy(action)
        base["entry_time"] = None
        base["entry_price"] = None
        base["actual_executable"] = False
        base["execution_block_reason"] = "NO_NEXT_EXECUTABLE_BAR" if entry_index is None else None
        base["mfe"] = None
        base["mae"] = None
        base["stop_triggered"] = None
        for horizon in intraday_horizons:
            _empty_horizon(base, f"bar_{horizon}")
        for days in daily_horizons:
            _empty_horizon(base, f"day_{days}")
        if entry_index is None:
            rows.append(base)
            continue

        entry = symbol_bars.iloc[entry_index]
        entry_price = float(entry["open"])
        base["entry_time"] = str(entry["timestamp"])
        base["entry_price"] = entry_price
        base["actual_executable"] = True
        max_horizon = max((*intraday_horizons, *(days * bars_per_day for days in daily_horizons)), default=1)
        forward = symbol_bars.iloc[entry_index : min(len(symbol_bars), entry_index + max_horizon + 1)]
        base["mfe"], base["mae"] = _mfe_mae(forward, entry_price=entry_price, side=side)
        base["stop_triggered"] = _stop_triggered(forward, candidate.get("stop_price"), side=side)
        for horizon in intraday_horizons:
            _write_horizon(base, symbol_bars, entry_index, horizon, f"bar_{horizon}", entry_price, side, cost)
        for days in daily_horizons:
            _write_horizon(base, symbol_bars, entry_index, days * bars_per_day, f"day_{days}", entry_price, side, cost)
        _write_relative_returns(base, symbol_bars, entry_index, entry_price, side, intraday_horizons, benchmark_bars, "benchmark")
        _write_relative_returns(base, symbol_bars, entry_index, entry_price, side, intraday_horizons, industry_bars, "industry")
        rows.append(base)
    return pd.DataFrame(rows)


def calibration_report(
    labels: Any,
    *,
    probability_column: str,
    outcome_column: str,
    bins: int = 10,
    strata: Sequence[str] = ("market_regime", "symbol_type"),
) -> dict[str, object]:
    """Return reliability-curve, Brier, log loss, and requested strata."""

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
    by_stratum: dict[str, dict[str, object]] = {}
    for stratum in strata:
        if stratum not in valid.columns:
            continue
        values: dict[str, object] = {}
        for name, group in valid.groupby(stratum, dropna=False, sort=True):
            values[str(name)] = _calibration_values(
                [float(value) for value in group[probability_column]],
                [float(value) for value in group[outcome_column]],
                bins=bins,
            )
        by_stratum[stratum] = values
    report["by_stratum"] = by_stratum
    return report


def local_threshold_sensitivity(
    labels: Any,
    *,
    feature: str,
    thresholds: Iterable[float],
    return_column: str,
    success_column: str = "success",
) -> Any:
    """Report a local threshold sweep; it intentionally does not choose a winner."""

    import pandas as pd

    _require_columns(labels, {feature, return_column}, name="labels")
    values = tuple(float(value) for value in thresholds)
    if not values or any(not math.isfinite(value) for value in values):
        raise ValueError("thresholds must be finite and non-empty")
    rows: list[dict[str, object]] = []
    for threshold in sorted(set(values)):
        selected = labels.loc[labels[feature].astype(float) >= threshold]
        count = len(selected)
        row: dict[str, object] = {
            "feature": feature,
            "threshold": threshold,
            "selected_count": count,
            "coverage": count / max(len(labels), 1),
            "mean_return": float(selected[return_column].mean()) if count else None,
        }
        if success_column in selected.columns:
            row["success_rate"] = float(selected[success_column].mean()) if count else None
        rows.append(row)
    return pd.DataFrame(rows)


def sell_side_gap_report(labels: Any) -> dict[str, object]:
    """Keep discretionary T sells and hard risk exits on separate metrics."""

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
        "gaps": (
            "SELL_T_TIMING currently has no separately persisted TAKE_PROFIT_T, REDUCE_T, EXIT_T, "
            "or REVERSE_T_SELL action taxonomy; add them before judging sell-side precision."
        ),
    }


def audit_report(labels: Any) -> dict[str, object]:
    """Produce the non-test research report used by rehearsal artifacts."""

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
    }
    if {"up_probability", "success"} <= set(labels.columns):
        report["calibration"] = calibration_report(labels, probability_column="up_probability", outcome_column="success")
    sensitivity: dict[str, object] = {}
    for feature, thresholds in {
        "force_buy_edge": (52.0, 60.0, 68.0),
        "buy_strength_score": (58.0, 64.0, 70.0),
        "sell_pressure": (60.0, 70.0, 80.0),
        "capital_flow": (55.0, 65.0, 75.0),
        "multi_period_trend": (55.0, 65.0, 75.0),
        "risk_reward": (1.0, 1.2, 1.5),
        "breakout": (70.0, 80.0, 90.0),
        "macd_score_weight": (0.0, 0.10, 0.15),
        "mean_reversion_size_multiplier": (0.25, 0.50, 0.75),
    }.items():
        if feature in labels.columns and "net_return" in labels.columns:
            sensitivity[feature] = local_threshold_sensitivity(
                labels, feature=feature, thresholds=thresholds, return_column="net_return"
            ).to_dict(orient="records")
    report["threshold_sensitivity"] = sensitivity
    report["parameter_selection_rule"] = "report local neighborhoods; do not select an isolated best return"
    return report


def _require_columns(frame: Any, required: set[str], *, name: str) -> None:
    columns = set(getattr(frame, "columns", ()))
    missing = sorted(required - columns)
    if missing:
        raise ValueError(f"{name} missing required columns: {', '.join(missing)}")


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


def _next_executable_index(bars: Any, *, after: Any, side: str) -> int | None:
    import pandas as pd

    for index, row in bars.loc[bars["timestamp"] > pd.Timestamp(after)].iterrows():
        if _truthy(row.get("suspended", row.get("is_suspended", False))):
            continue
        if _truthy(row.get("tradable", True)) is False:
            continue
        if side == "BUY" and _truthy(row.get("at_limit_up", False)):
            continue
        if side == "SELL" and _truthy(row.get("at_limit_down", False)):
            continue
        if float(row["open"]) > 0.0:
            return int(index)
    return None


def _truthy(value: object) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def _empty_horizon(base: dict[str, object], suffix: str) -> None:
    base[f"gross_return_{suffix}"] = None
    base[f"cost_adjusted_return_{suffix}"] = None
    base[f"success_{suffix}"] = None


def _write_horizon(
    base: dict[str, object],
    bars: Any,
    entry_index: int,
    horizon: int,
    suffix: str,
    entry_price: float,
    side: str,
    cost: float,
) -> None:
    future_index = entry_index + horizon
    if future_index >= len(bars):
        return
    close = float(bars.iloc[future_index]["close"])
    gross = close / entry_price - 1.0 if side == "BUY" else entry_price / close - 1.0
    base[f"gross_return_{suffix}"] = gross
    base[f"cost_adjusted_return_{suffix}"] = gross - cost
    base[f"success_{suffix}"] = int(gross - cost > 0.0)


def _mfe_mae(forward: Any, *, entry_price: float, side: str) -> tuple[float, float]:
    high = float(forward["high"].max())
    low = float(forward["low"].min())
    if side == "BUY":
        return high / entry_price - 1.0, low / entry_price - 1.0
    return entry_price / low - 1.0, entry_price / high - 1.0


def _stop_triggered(forward: Any, stop: object, *, side: str) -> bool | None:
    if stop is None:
        return None
    value = float(cast(str | int | float, stop))
    return bool(float(forward["low"].min()) <= value) if side == "BUY" else bool(float(forward["high"].max()) >= value)


def _write_relative_returns(
    base: dict[str, object],
    bars: Any,
    entry_index: int,
    entry_price: float,
    side: str,
    horizons: Sequence[int],
    reference: Any | None,
    prefix: str,
) -> None:
    if reference is None:
        return
    import pandas as pd

    _require_columns(reference, {"timestamp", "close"}, name=f"{prefix}_bars")
    data = reference.copy()
    data["timestamp"] = pd.to_datetime(data["timestamp"])
    for horizon in horizons:
        own = base.get(f"gross_return_bar_{horizon}")
        target = bars.iloc[entry_index + horizon]["timestamp"] if entry_index + horizon < len(bars) else None
        if own is None or target is None:
            base[f"{prefix}_excess_return_bar_{horizon}"] = None
            continue
        before = data.loc[data["timestamp"] <= bars.iloc[entry_index]["timestamp"]]
        after = data.loc[data["timestamp"] <= target]
        if before.empty or after.empty:
            base[f"{prefix}_excess_return_bar_{horizon}"] = None
            continue
        reference_return = float(after.iloc[-1]["close"]) / float(before.iloc[-1]["close"]) - 1.0
        directional_reference = reference_return if side == "BUY" else -reference_return
        base[f"{prefix}_excess_return_bar_{horizon}"] = float(cast(str | int | float, own)) - directional_reference


def _calibration_values(probabilities: list[float], outcomes: list[float], *, bins: int) -> dict[str, object]:
    if not probabilities:
        return {"count": 0, "brier_score": None, "log_loss": None, "reliability_curve": []}
    brier = sum((probability - outcome) ** 2 for probability, outcome in zip(probabilities, outcomes, strict=True)) / len(probabilities)
    epsilon = 1e-15
    log_loss = -sum(
        outcome * math.log(max(probability, epsilon)) + (1.0 - outcome) * math.log(max(1.0 - probability, epsilon))
        for probability, outcome in zip(probabilities, outcomes, strict=True)
    ) / len(probabilities)
    grouped: list[list[tuple[float, float]]] = [[] for _ in range(bins)]
    for probability, outcome in zip(probabilities, outcomes, strict=True):
        grouped[min(int(probability * bins), bins - 1)].append((probability, outcome))
    curve = [
        {
            "lower": index / bins,
            "upper": (index + 1) / bins,
            "count": len(items),
            "mean_predicted": sum(item[0] for item in items) / len(items),
            "observed_rate": sum(item[1] for item in items) / len(items),
        }
        for index, items in enumerate(grouped)
        if items
    ]
    return {"count": len(probabilities), "brier_score": brier, "log_loss": log_loss, "reliability_curve": curve}


def _ordinary_sell_summary(frame: Any) -> dict[str, object]:
    payload: dict[str, object] = {"count": int(len(frame))}
    if "success" in frame.columns:
        payload["directional_hit_rate"] = float(frame["success"].mean()) if len(frame) else None
    if "net_return" in frame.columns:
        payload["mean_net_return"] = float(frame["net_return"].mean()) if len(frame) else None
    return payload


def _mean_if_present(frame: Any, column: str) -> float | None:
    if column not in frame.columns or not len(frame):
        return None
    return float(frame[column].dropna().mean()) if not frame[column].dropna().empty else None


def _count_by(frame: Any, column: str) -> dict[str, int]:
    if column not in frame.columns:
        return {}
    return {str(key): int(value) for key, value in frame.groupby(column, dropna=False).size().items()}
