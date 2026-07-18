"""MR-1 exploratory morning-pop Targets and fixed-model chronological replay.

This module consumes already-normalized 5-minute evidence.  It never uses a bar after an
exit endpoint to fill a missing endpoint, and it deliberately keeps Target observations out of
the Candidate-ranking inputs.  Its outputs remain EXPLORATORY research evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from enum import Enum
import math
from statistics import mean, pstdev
from typing import Any, Iterable, Mapping
from zoneinfo import ZoneInfo

from market_regime_alpha.research.prr_mvp_1 import ExploratoryExecutionCostConfig
from market_regime_alpha.research.tencent_composite_contracts import CompositeBar, PreparedCompositeData


MR1_MORNING_TARGET_SCHEMA_VERSION = "mr-1-overnight-morning-pop-target-v1"
MR1_EXACT_ENDPOINT_CONVENTION = "exact-5m-endpoint-close-v1"
MR1_EXECUTION_ASSUMPTION = "MR_1_1455_REFERENCE_TO_NEXT_SESSION_ENDPOINT_V1"
_SHANGHAI = ZoneInfo("Asia/Shanghai")


class MR1TargetId(str, Enum):
    NEXT_SESSION_0935_RETURN = "NEXT_SESSION_0935_RETURN"
    NEXT_SESSION_1000_RETURN = "NEXT_SESSION_1000_RETURN"
    NEXT_SESSION_1030_RETURN = "NEXT_SESSION_1030_RETURN"
    NEXT_SESSION_CLOSE_RETURN = "NEXT_SESSION_CLOSE_RETURN"
    NEXT_SESSION_1030_MFE = "NEXT_SESSION_1030_MFE"
    NEXT_SESSION_1030_MAE = "NEXT_SESSION_1030_MAE"


class MR1ExitTime(str, Enum):
    T_0935 = "09:35"
    T_1000 = "10:00"
    T_1030 = "10:30"
    CLOSE = "CLOSE"


_EXIT_TARGET = {
    MR1ExitTime.T_0935: MR1TargetId.NEXT_SESSION_0935_RETURN,
    MR1ExitTime.T_1000: MR1TargetId.NEXT_SESSION_1000_RETURN,
    MR1ExitTime.T_1030: MR1TargetId.NEXT_SESSION_1030_RETURN,
    MR1ExitTime.CLOSE: MR1TargetId.NEXT_SESSION_CLOSE_RETURN,
}
_ENDPOINT_TIME = {
    MR1TargetId.NEXT_SESSION_0935_RETURN: time(9, 35),
    MR1TargetId.NEXT_SESSION_1000_RETURN: time(10, 0),
    MR1TargetId.NEXT_SESSION_1030_RETURN: time(10, 30),
}


@dataclass(frozen=True, slots=True)
class MR1ReplayResult:
    """One model-ladder/cost scenario replay for a declared exit endpoint."""

    orders: tuple[dict[str, Any], ...]
    fills: tuple[dict[str, Any], ...]
    trades: tuple[dict[str, Any], ...]
    daily_equity: tuple[dict[str, Any], ...]
    metrics: dict[str, Any]


def build_mr1_targets(
    *,
    prepared: PreparedCompositeData,
    bars: Iterable[CompositeBar],
    decision_dates: Iterable[date],
) -> tuple[dict[str, Any], ...]:
    """Build post-decision Target observations using explicit endpoint semantics.

    Morning returns require exactly the named 5-minute endpoint bar.  10:30 MFE/MAE additionally
    require the exact 10:30 endpoint, so an incomplete morning cannot be silently treated as a
    complete target.  Close return uses the existing prepared next-session close, whose session
    completeness is the already-declared Tencent composite quality convention.
    """

    exact: dict[tuple[str, date, time], CompositeBar] = {}
    by_session: dict[tuple[str, date], list[CompositeBar]] = {}
    for bar in bars:
        local = bar.timestamp.astimezone(_SHANGHAI)
        key = (bar.symbol, local.date(), local.time().replace(tzinfo=None))
        if key in exact:
            raise ValueError("MR-1 requires unique normalized symbol/timestamp bars")
        exact[key] = bar
        by_session.setdefault((bar.symbol, local.date()), []).append(bar)
    for rows in by_session.values():
        rows.sort(key=lambda row: row.timestamp)

    observations: list[dict[str, Any]] = []
    for decision_date in tuple(decision_dates):
        next_date = prepared.next_session_date(decision_date)
        for symbol in prepared.accepted_symbols:
            reference = prepared.session_for(symbol, decision_date)
            for target_id, endpoint in _ENDPOINT_TIME.items():
                endpoint_bar = exact.get((symbol, next_date, endpoint))
                observations.append(
                    _observation_for_endpoint(
                        symbol=symbol,
                        decision_date=decision_date,
                        next_date=next_date,
                        target_id=target_id,
                        reference_price=reference.reference_price,
                        endpoint=endpoint,
                        endpoint_bar=endpoint_bar,
                    )
                )
            endpoint_bar = exact.get((symbol, next_date, time(10, 30)))
            morning_bars = tuple(
                row
                for row in by_session.get((symbol, next_date), ())
                if time(9, 35) <= row.timestamp.astimezone(_SHANGHAI).time().replace(tzinfo=None) <= time(10, 30)
            )
            observations.extend(
                _morning_excursion_observations(
                    symbol=symbol,
                    decision_date=decision_date,
                    next_date=next_date,
                    reference_price=reference.reference_price,
                    endpoint_bar=endpoint_bar,
                    morning_bars=morning_bars,
                )
            )
            close_session = prepared.session_for(symbol, next_date)
            observations.append(
                _available_observation(
                    symbol=symbol,
                    decision_date=decision_date,
                    next_date=next_date,
                    target_id=MR1TargetId.NEXT_SESSION_CLOSE_RETURN,
                    reference_price=reference.reference_price,
                    value=close_session.close / reference.reference_price - 1.0,
                    exit_price=close_session.close,
                    exit_timestamp=datetime.combine(next_date, time(15, 0), tzinfo=_SHANGHAI),
                    convention="prepared-session-close-v1",
                )
            )
    return tuple(sorted(observations, key=lambda row: (row["decision_date"], row["symbol"], row["target_id"])))


def replay_mr1_fixed_portfolios(
    *,
    prepared: PreparedCompositeData,
    ranking_rows: Iterable[Mapping[str, Any]],
    target_rows: Iterable[Mapping[str, Any]],
    decision_dates: Iterable[date],
    top_k: int,
    exit_time: MR1ExitTime,
    cost_scenario: str,
    cost_config: ExploratoryExecutionCostConfig | None = None,
) -> MR1ReplayResult:
    """Replay all fixed rankings at an early next-session endpoint.

    A 09:35/10:00/10:30 exit precedes the following 14:55 decision.  Therefore this replay has
    no ``ACTIVE_POSITION_CASH_LOCKED`` path: each Decision Date is eligible for a fresh sleeve.
    Missing endpoint evidence is explicit and never replaced by rank six or a later bar.
    """

    if top_k <= 0:
        raise ValueError("top_k must be positive")
    if not isinstance(exit_time, MR1ExitTime):
        raise TypeError("exit_time must be an MR1ExitTime")
    if not cost_scenario:
        raise ValueError("cost_scenario must be non-empty")
    costs = cost_config or ExploratoryExecutionCostConfig()
    target_id = _EXIT_TARGET[exit_time].value
    target_index = {
        (str(row["decision_date"]), str(row["symbol"]), str(row["target_id"])): dict(row)
        for row in target_rows
    }
    close_target_id = "target-r5-decision-reference-to-next-session-close-return-v1"
    source_rankings = [row for row in ranking_rows if str(row["target_id"]) == close_target_id]
    model_ids = tuple(sorted({str(row["model_id"]) for row in source_rankings}))
    dates = tuple(decision_dates)
    orders: list[dict[str, Any]] = []
    fills: list[dict[str, Any]] = []
    trades: list[dict[str, Any]] = []
    equity: list[dict[str, Any]] = []
    for model_id in model_ids:
        by_date: dict[str, list[Mapping[str, Any]]] = {}
        for row in source_rankings:
            if str(row["model_id"]) == model_id:
                by_date.setdefault(str(row["decision_date"]), []).append(row)
        gross_equity = 1.0
        net_equity = 1.0
        active_until: date | None = None
        for decision_date in dates:
            if exit_time is MR1ExitTime.CLOSE and active_until is not None and decision_date <= active_until:
                orders.append(_cash_order(model_id, decision_date, exit_time, cost_scenario, "ACTIVE_POSITION_CASH_LOCKED"))
                equity.append(_equity(model_id, decision_date, exit_time, cost_scenario, gross_equity, net_equity, 0.0, 0.0, 0.0, 1.0, 0, 0))
                continue
            ranked = sorted(
                (
                    row
                    for row in by_date.get(decision_date.isoformat(), ())
                    if bool(row["eligible_for_ranking"]) and row["rank"] is not None
                ),
                key=lambda row: int(row["rank"]),
            )
            selected = tuple(row for row in ranked if int(row["rank"]) <= top_k)
            if not selected:
                orders.append(_cash_order(model_id, decision_date, exit_time, cost_scenario, "NO_RANKED_CANDIDATE"))
                equity.append(_equity(model_id, decision_date, exit_time, cost_scenario, gross_equity, net_equity, 0.0, 0.0, 0.0, 1.0, 0, 0))
                continue
            gross_returns: list[float] = []
            net_returns: list[float] = []
            cost_total = 0.0
            completed = 0
            missing_exit = 0
            for row in selected:
                symbol = str(row["symbol"])
                rank = int(row["rank"])
                entry = prepared.session_for(symbol, decision_date)
                order_id = f"{model_id}:{decision_date.isoformat()}:{symbol}:{exit_time.value}:{cost_scenario}:order"
                orders.append({
                    "order_id": order_id,
                    "model_id": model_id,
                    "decision_date": decision_date.isoformat(),
                    "decision_time": datetime.combine(decision_date, time(14, 55), tzinfo=_SHANGHAI).isoformat(),
                    "exit_time": exit_time.value,
                    "cost_scenario": cost_scenario,
                    "symbol": symbol,
                    "rank": rank,
                    "reference_price": entry.reference_price,
                    "order_status": "SUBMITTED",
                    "reason_code": "FIXED_TOP_K",
                })
                target = target_index.get((decision_date.isoformat(), symbol, target_id))
                if target is None or target["status"] != "AVAILABLE":
                    trades.append({
                        "model_id": model_id,
                        "decision_date": decision_date.isoformat(),
                        "symbol": symbol,
                        "rank": rank,
                        "exit_time": exit_time.value,
                        "cost_scenario": cost_scenario,
                        "trade_status": "MISSING_EXIT",
                        "reason_code": target["missing_reason"] if target is not None else "TARGET_OBSERVATION_MISSING",
                    })
                    missing_exit += 1
                    continue
                trade, trade_fills = _simulate_mark_trade(
                    model_id=model_id,
                    decision_date=decision_date,
                    symbol=symbol,
                    rank=rank,
                    exit_time=exit_time,
                    cost_scenario=cost_scenario,
                    reference_price=entry.reference_price,
                    reference_timestamp=entry.reference_timestamp,
                    exit_price=float(target["exit_price"]),
                    exit_timestamp=datetime.fromisoformat(str(target["exit_timestamp"])),
                    cost_config=costs,
                    weight=1.0 / len(selected),
                )
                fills.extend(trade_fills)
                trades.append(trade)
                gross_returns.append(float(trade["gross_return"]))
                net_returns.append(float(trade["net_return"]))
                cost_total += float(trade["transaction_cost"])
                completed += 1
            gross_return = mean(gross_returns) if gross_returns else 0.0
            net_return = mean(net_returns) if net_returns else 0.0
            gross_equity *= 1.0 + gross_return
            net_equity *= 1.0 + net_return
            if exit_time is MR1ExitTime.CLOSE:
                active_until = prepared.next_session_date(decision_date)
            equity.append(
                _equity(
                    model_id, decision_date, exit_time, cost_scenario, gross_equity, net_equity,
                    gross_return, net_return, cost_total, 0.0 if completed else 1.0, completed, missing_exit,
                )
            )
    return MR1ReplayResult(tuple(orders), tuple(fills), tuple(trades), tuple(equity), _metrics(equity, trades))


def _observation_for_endpoint(*, symbol: str, decision_date: date, next_date: date, target_id: MR1TargetId, reference_price: float, endpoint: time, endpoint_bar: CompositeBar | None) -> dict[str, Any]:
    if endpoint_bar is None:
        return _unavailable_observation(symbol, decision_date, next_date, target_id, "EXACT_ENDPOINT_BAR_MISSING", endpoint)
    return _available_observation(
        symbol=symbol, decision_date=decision_date, next_date=next_date, target_id=target_id,
        reference_price=reference_price, value=endpoint_bar.close / reference_price - 1.0,
        exit_price=endpoint_bar.close, exit_timestamp=endpoint_bar.timestamp, convention=MR1_EXACT_ENDPOINT_CONVENTION,
    )


def _morning_excursion_observations(*, symbol: str, decision_date: date, next_date: date, reference_price: float, endpoint_bar: CompositeBar | None, morning_bars: tuple[CompositeBar, ...]) -> tuple[dict[str, Any], dict[str, Any]]:
    if endpoint_bar is None:
        missing = _unavailable_observation(symbol, decision_date, next_date, MR1TargetId.NEXT_SESSION_1030_MFE, "EXACT_ENDPOINT_BAR_MISSING", time(10, 30))
        return (missing, {**missing, "target_id": MR1TargetId.NEXT_SESSION_1030_MAE.value})
    return (
        _available_observation(symbol=symbol, decision_date=decision_date, next_date=next_date, target_id=MR1TargetId.NEXT_SESSION_1030_MFE, reference_price=reference_price, value=max(row.high for row in morning_bars) / reference_price - 1.0, exit_price=endpoint_bar.close, exit_timestamp=endpoint_bar.timestamp, convention="next-session-0935-through-1030-extrema-v1"),
        _available_observation(symbol=symbol, decision_date=decision_date, next_date=next_date, target_id=MR1TargetId.NEXT_SESSION_1030_MAE, reference_price=reference_price, value=min(row.low for row in morning_bars) / reference_price - 1.0, exit_price=endpoint_bar.close, exit_timestamp=endpoint_bar.timestamp, convention="next-session-0935-through-1030-extrema-v1"),
    )


def _available_observation(*, symbol: str, decision_date: date, next_date: date, target_id: MR1TargetId, reference_price: float, value: float, exit_price: float, exit_timestamp: datetime, convention: str) -> dict[str, Any]:
    return {
        "schema_version": MR1_MORNING_TARGET_SCHEMA_VERSION, "target_id": target_id.value,
        "symbol": symbol, "decision_date": decision_date.isoformat(), "target_session_date": next_date.isoformat(),
        "status": "AVAILABLE", "value": round(value, 12), "reference_price": reference_price,
        "exit_price": exit_price, "exit_timestamp": exit_timestamp.isoformat(), "missing_reason": None,
        "bar_convention": convention, "data_eligibility": "EXPLORATORY",
    }


def _unavailable_observation(symbol: str, decision_date: date, next_date: date, target_id: MR1TargetId, reason: str, endpoint: time) -> dict[str, Any]:
    return {
        "schema_version": MR1_MORNING_TARGET_SCHEMA_VERSION, "target_id": target_id.value,
        "symbol": symbol, "decision_date": decision_date.isoformat(), "target_session_date": next_date.isoformat(),
        "status": "UNAVAILABLE", "value": None, "reference_price": None, "exit_price": None,
        "exit_timestamp": None, "missing_reason": reason, "bar_convention": f"{MR1_EXACT_ENDPOINT_CONVENTION}:{endpoint.isoformat()}",
        "data_eligibility": "EXPLORATORY",
    }


def _simulate_mark_trade(*, model_id: str, decision_date: date, symbol: str, rank: int, exit_time: MR1ExitTime, cost_scenario: str, reference_price: float, reference_timestamp: datetime, exit_price: float, exit_timestamp: datetime, cost_config: ExploratoryExecutionCostConfig, weight: float) -> tuple[dict[str, Any], tuple[dict[str, Any], dict[str, Any]]]:
    entry_price = reference_price * (1.0 + cost_config.entry_slippage_bps / 10_000.0)
    realized_exit = exit_price * (1.0 - cost_config.exit_slippage_bps / 10_000.0)
    entry_notional = cost_config.normalized_trade_notional * weight
    quantity = entry_notional / entry_price
    buy_commission = max(entry_notional * cost_config.buy_commission_bps / 10_000.0, cost_config.minimum_commission)
    exit_notional = quantity * realized_exit
    sell_commission = max(exit_notional * cost_config.sell_commission_bps / 10_000.0, cost_config.minimum_commission)
    stamp_duty = exit_notional * cost_config.sell_stamp_duty_bps / 10_000.0
    transfer_fee = (entry_notional + exit_notional) * cost_config.transfer_fee_bps / 10_000.0
    transaction_cost = buy_commission + sell_commission + stamp_duty + transfer_fee
    common = {"model_id": model_id, "decision_date": decision_date.isoformat(), "symbol": symbol, "rank": rank, "exit_time": exit_time.value, "cost_scenario": cost_scenario}
    trade = {
        **common, "entry_date": decision_date.isoformat(), "exit_date": exit_timestamp.astimezone(_SHANGHAI).date().isoformat(),
        "entry_price": entry_price, "exit_price": realized_exit, "gross_return": exit_price / reference_price - 1.0,
        "net_return": (exit_notional - transaction_cost - entry_notional) / entry_notional,
        "transaction_cost": transaction_cost, "slippage_cost": quantity * (entry_price - reference_price) + quantity * (exit_price - realized_exit),
        "holding_sessions": 1, "trade_status": "COMPLETED", "reason_code": MR1_EXECUTION_ASSUMPTION,
    }
    fills = (
        {**common, "side": "BUY", "mark_time": reference_timestamp.isoformat(), "reference_price": reference_price, "fill_price": entry_price, "quantity": quantity, "total_cost": buy_commission, "fill_status": "SIMULATED_REFERENCE_FILL", "reason_code": MR1_EXECUTION_ASSUMPTION},
        {**common, "side": "SELL", "mark_time": exit_timestamp.isoformat(), "reference_price": exit_price, "fill_price": realized_exit, "quantity": quantity, "total_cost": transaction_cost - buy_commission, "fill_status": "SIMULATED_REFERENCE_FILL", "reason_code": MR1_EXECUTION_ASSUMPTION},
    )
    return trade, fills


def _cash_order(model_id: str, decision_date: date, exit_time: MR1ExitTime, cost_scenario: str, reason: str) -> dict[str, Any]:
    return {"model_id": model_id, "decision_date": decision_date.isoformat(), "exit_time": exit_time.value, "cost_scenario": cost_scenario, "symbol": "__CASH__", "order_status": "SKIPPED", "reason_code": reason}


def _equity(model_id: str, decision_date: date, exit_time: MR1ExitTime, cost_scenario: str, gross_equity: float, net_equity: float, gross_return: float, net_return: float, transaction_cost: float, cash_ratio: float, active_count: int, missing_exit: int) -> dict[str, Any]:
    return {"model_id": model_id, "session_date": decision_date.isoformat(), "exit_time": exit_time.value, "cost_scenario": cost_scenario, "gross_return": gross_return, "net_return": net_return, "gross_equity": gross_equity, "net_equity": net_equity, "transaction_cost": transaction_cost, "cash_ratio": cash_ratio, "active_position_count": active_count, "missing_exit_count": missing_exit}


def _metrics(equity: list[dict[str, Any]], trades: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in equity:
        grouped.setdefault(str(row["model_id"]), []).append(row)
    result: dict[str, Any] = {"annualization_convention": "252_SESSION_DAYS_V1", "risk_free_rate_assumption": 0.0, "models": {}}
    for model_id, rows in sorted(grouped.items()):
        returns = [float(row["net_return"]) for row in rows]
        model_trades = [row for row in trades if row["model_id"] == model_id and row["trade_status"] == "COMPLETED"]
        wins = [float(row["net_return"]) for row in model_trades if float(row["net_return"]) > 0.0]
        losses = [float(row["net_return"]) for row in model_trades if float(row["net_return"]) < 0.0]
        net_equity = float(rows[-1]["net_equity"])
        gross_equity = float(rows[-1]["gross_equity"])
        peak = 1.0
        drawdown = 0.0
        for row in rows:
            peak = max(peak, float(row["net_equity"]))
            drawdown = min(drawdown, float(row["net_equity"]) / peak - 1.0)
        result["models"][model_id] = {
            "gross_cumulative_return": gross_equity - 1.0, "net_cumulative_return": net_equity - 1.0,
            "annualized_return": net_equity ** (252.0 / max(1, len(rows))) - 1.0 if net_equity > 0 else None,
            "annualized_volatility": pstdev(returns) * math.sqrt(252.0) if len(returns) > 1 else 0.0,
            "maximum_drawdown": drawdown, "win_rate": len(wins) / len(model_trades) if model_trades else None,
            "average_win": mean(wins) if wins else None, "average_loss": mean(losses) if losses else None,
            "profit_factor": sum(wins) / abs(sum(losses)) if losses else None,
            "turnover": sum(float(row["active_position_count"]) for row in rows),
            "total_transaction_cost": sum(float(row["transaction_cost"]) for row in rows),
            "cost_ratio": sum(float(row["transaction_cost"]) for row in rows) / (len(model_trades) * 100_000.0) if model_trades else 0.0,
            "missing_exit_count": sum(int(row["missing_exit_count"]) for row in rows), "descriptive_only": True,
        }
    return result
