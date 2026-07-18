"""PRR-MVP-1 fixed Candidate-ranking replay under an EXPLORATORY ceiling.

This module writes no files and never places an order. It converts the existing Candidate
materializations into complete ranking rows, then applies a declared research-mark replay.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
import math
from statistics import mean, pstdev
from typing import Any
from zoneinfo import ZoneInfo

from market_regime_alpha.candidates.baselines import rank_candidates_by_feature
from market_regime_alpha.candidates.composite_baseline import (
    rank_candidates_by_transparent_composite,
)
from market_regime_alpha.candidates.dataset import CandidateResearchDataset
from market_regime_alpha.candidates.rehearsal_targets import (
    R5_NEXT_SESSION_RETURN_TARGET_ID,
)
from market_regime_alpha.core.identity import ModelId
from market_regime_alpha.core.status import InputAvailabilityStatus
from market_regime_alpha.research.r5_baseline_runner import r5_b1_fixed_specs
from market_regime_alpha.research.tencent_composite_execution import (
    TencentCompositeResearchExecution,
)
from market_regime_alpha.research.tencent_composite_materialization import (
    materialize_tencent_composite_slice,
)


PRR_MVP_1_SCHEMA_VERSION = "prr-mvp-1-v1"
PRR_MVP_1_EXECUTION_ASSUMPTION = "PRR_MVP_1_1455_REFERENCE_TO_NEXT_CLOSE_V1"
_SHANGHAI = ZoneInfo("Asia/Shanghai")


@dataclass(frozen=True, slots=True)
class ExploratoryExecutionCostConfig:
    """Versioned research assumptions, not asserted China-market fee facts."""

    schema_version: str = "prr-mvp-1-execution-cost-v1"
    buy_commission_bps: float = 3.0
    sell_commission_bps: float = 3.0
    minimum_commission: float = 5.0
    sell_stamp_duty_bps: float = 5.0
    transfer_fee_bps: float = 0.0
    entry_slippage_bps: float = 5.0
    exit_slippage_bps: float = 5.0
    normalized_trade_notional: float = 100_000.0

    def __post_init__(self) -> None:
        if self.schema_version != "prr-mvp-1-execution-cost-v1":
            raise ValueError("unsupported PRR-MVP-1 execution cost schema")
        values = (
            self.buy_commission_bps,
            self.sell_commission_bps,
            self.minimum_commission,
            self.sell_stamp_duty_bps,
            self.transfer_fee_bps,
            self.entry_slippage_bps,
            self.exit_slippage_bps,
            self.normalized_trade_notional,
        )
        if any(isinstance(value, bool) or not math.isfinite(float(value)) for value in values):
            raise ValueError("execution costs must be finite numeric values")
        if any(value < 0.0 for value in values) or self.normalized_trade_notional <= 0.0:
            raise ValueError("execution costs must be non-negative and notional positive")


@dataclass(frozen=True, slots=True)
class PRRCandidateData:
    """Complete Candidate ranking evidence for all fixed models and Target families."""

    decision_dates: tuple[date, ...]
    datasets: tuple[CandidateResearchDataset, ...]
    ranking_rows: tuple[dict[str, Any], ...]

    def __post_init__(self) -> None:
        if len(self.decision_dates) != 60:
            raise ValueError("PRR-MVP-1 requires exactly 60 Decision Dates")
        if tuple(sorted(self.decision_dates)) != self.decision_dates:
            raise ValueError("PRR Decision Dates must be chronological")


@dataclass(frozen=True, slots=True)
class PRRReplayResult:
    """Pure tables and metrics from independently replaying every fixed model."""

    orders: tuple[dict[str, Any], ...]
    fills: tuple[dict[str, Any], ...]
    trades: tuple[dict[str, Any], ...]
    daily_equity: tuple[dict[str, Any], ...]
    metrics: dict[str, Any]
    limitations: tuple[str, ...]


def acceptance_accounting(
    *,
    replay: PRRReplayResult,
    model_count: int,
    decision_date_count: int,
    top_k: int,
) -> dict[str, Any]:
    """Reconcile declared Top-K slots with explicit simulated-mark outcomes."""

    selection_slots = model_count * decision_date_count * top_k
    completed = sum(1 for item in replay.trades if item["trade_status"] == "COMPLETED")
    entry_marks = sum(1 for item in replay.fills if item["side"] == "BUY")
    exit_marks = sum(1 for item in replay.fills if item["side"] == "SELL")
    cash_events = [item for item in replay.orders if item["reason_code"] == "ACTIVE_POSITION_CASH_LOCKED"]
    cash_slots = len(cash_events) * top_k
    missing_entry = sum(1 for item in replay.orders if item["reason_code"] == "MISSING_ENTRY_REFERENCE")
    missing_exit = sum(1 for item in replay.trades if item["trade_status"] == "MISSING_EXIT")
    excluded = selection_slots - completed - cash_slots - missing_entry - missing_exit
    if excluded < 0 or completed + cash_slots + missing_entry + missing_exit + excluded != selection_slots:
        raise ValueError("selection-slot accounting identity does not reconcile")
    return {
        "model_count": model_count,
        "decision_date_count": decision_date_count,
        "top_k": top_k,
        "selection_slot_count": selection_slots,
        "order_count": len(replay.orders),
        "entry_mark_count": entry_marks,
        "exit_mark_count": exit_marks,
        "completed_trade_count": completed,
        "missing_entry_count": missing_entry,
        "missing_exit_count": missing_exit,
        "cash_slot_count": cash_slots,
        "excluded_count": excluded,
        "slot_identity": "selection_slot_count = completed_trade_count + missing_entry_count + missing_exit_count + cash_slot_count + excluded_count",
        "reason_code_counts": {
            "ACTIVE_POSITION_CASH_LOCKED": cash_slots,
            "NO_RANKED_CANDIDATE": excluded,
        },
        "fill_status_required": "SIMULATED_REFERENCE_FILL",
        "rank_six_backfill": False,
    }


def build_prr_candidate_data(
    *,
    execution: TencentCompositeResearchExecution,
    code_revision: str,
    config_hash: str,
) -> PRRCandidateData:
    """Materialize complete B0/B1 rankings without using target values as inputs."""

    prepared = execution.prepared
    decision_dates = prepared.common_session_dates[-61:-1]
    datasets: list[CandidateResearchDataset] = []
    ranking_rows: list[dict[str, Any]] = []
    for decision_date in decision_dates:
        slices = materialize_tencent_composite_slice(
            prepared=prepared,
            decision_date=decision_date,
            dataset_contract=execution.dataset_contract,
            retrieved_at=execution.acquisition.retrieved_at,
            code_revision=code_revision,
            config_hash=config_hash,
        )
        datasets.extend(slices)
        for dataset in slices:
            for name, feature_ids, ranking in _fixed_rankings(
                dataset=dataset,
                code_revision=code_revision,
                config_hash=config_hash,
            ):
                ranking_rows.extend(
                    _ranking_rows(
                        dataset=dataset,
                        model_name=name,
                        feature_ids=feature_ids,
                        ranking=ranking,
                    )
                )
    return PRRCandidateData(
        decision_dates=decision_dates,
        datasets=tuple(datasets),
        ranking_rows=tuple(
            sorted(
                ranking_rows,
                key=lambda row: (
                    row["decision_time"],
                    row["target_id"],
                    row["model_id"],
                    row["symbol"],
                ),
            )
        ),
    )


def replay_fixed_candidate_portfolios(
    *,
    execution: TencentCompositeResearchExecution,
    candidate_data: PRRCandidateData,
    run_id: str,
    top_k: int,
    cost_config: ExploratoryExecutionCostConfig,
) -> PRRReplayResult:
    """Replay fixed Top-K close-return rankings as simulated reference-mark fills.

    To avoid inventing intraday cash availability, a model does not open a new daily sleeve while
    its prior 14:55-to-next-close sleeve remains active. The skipped order is explicit; rank six is
    never substituted. This makes the cash constraint conservative rather than implicit leverage.
    """

    if top_k <= 0:
        raise ValueError("top_k must be positive")
    close_rows = [
        row
        for row in candidate_data.ranking_rows
        if row["target_id"] == str(R5_NEXT_SESSION_RETURN_TARGET_ID)
    ]
    model_ids = tuple(sorted({str(row["model_id"]) for row in close_rows}))
    orders: list[dict[str, Any]] = []
    fills: list[dict[str, Any]] = []
    trades: list[dict[str, Any]] = []
    equity: list[dict[str, Any]] = []
    for model_id in model_ids:
        model_rows = [row for row in close_rows if row["model_id"] == model_id]
        by_date: dict[str, list[dict[str, Any]]] = {}
        for row in model_rows:
            by_date.setdefault(str(row["decision_date"]), []).append(row)
        net_equity = 1.0
        gross_equity = 1.0
        active_until: date | None = None
        for decision_date in candidate_data.decision_dates:
            key = decision_date.isoformat()
            ranked = sorted(
                (
                    row
                    for row in by_date.get(key, ())
                    if row["eligible_for_ranking"] and row["rank"] is not None
                ),
                key=lambda row: int(row["rank"]),
            )
            next_date = execution.prepared.next_session_date(decision_date)
            if active_until is not None and decision_date <= active_until:
                orders.append(
                    _order_row(
                        run_id,
                        execution,
                        model_id,
                        decision_date,
                        symbol="__CASH__",
                        rank=None,
                        reference_price=None,
                        status="SKIPPED",
                        reason="ACTIVE_POSITION_CASH_LOCKED",
                    )
                )
                equity.append(
                    _equity_row(model_id, decision_date, 0.0, 0.0, gross_equity, net_equity, 1.0, 0.0, 0.0, 0, 0, 0)
                )
                continue
            selected = tuple(row for row in ranked if int(row["rank"]) <= top_k)
            if not selected:
                orders.append(
                    _order_row(run_id, execution, model_id, decision_date, "__CASH__", None, None, "SKIPPED", "NO_RANKED_CANDIDATE")
                )
                equity.append(_equity_row(model_id, decision_date, 0.0, 0.0, gross_equity, net_equity, 1.0, 0.0, 0.0, 0, 0, 0))
                continue
            gross_returns: list[float] = []
            net_returns: list[float] = []
            total_cost = 0.0
            total_slippage = 0.0
            completed = 0
            for row in selected:
                symbol = str(row["symbol"])
                entry = execution.prepared.session_for(symbol, decision_date)
                exit_session = execution.prepared.session_for(symbol, next_date)
                order = _order_row(
                    run_id,
                    execution,
                    model_id,
                    decision_date,
                    symbol,
                    int(row["rank"]),
                    entry.reference_price,
                    "SUBMITTED",
                    "FIXED_TOP_K",
                )
                orders.append(order)
                trade, trade_fills = _simulate_trade(
                    run_id=run_id,
                    model_id=model_id,
                    decision_date=decision_date,
                    exit_date=next_date,
                    symbol=symbol,
                    rank=int(row["rank"]),
                    reference_price=entry.reference_price,
                    reference_timestamp=entry.reference_timestamp,
                    exit_close=exit_session.close,
                    cost_config=cost_config,
                    weight=1.0 / len(selected),
                )
                fills.extend(trade_fills)
                trades.append(trade)
                if trade["trade_status"] == "COMPLETED":
                    gross_returns.append(float(trade["gross_return"]))
                    net_returns.append(float(trade["net_return"]))
                    total_cost += float(trade["transaction_cost"])
                    total_slippage += float(trade["slippage_cost"])
                    completed += 1
            gross_return = mean(gross_returns) if gross_returns else 0.0
            net_return = mean(net_returns) if net_returns else 0.0
            gross_equity *= 1.0 + gross_return
            net_equity *= 1.0 + net_return
            active_until = next_date
            equity.append(
                _equity_row(
                    model_id,
                    next_date,
                    gross_return,
                    net_return,
                    gross_equity,
                    net_equity,
                    0.0 if completed else 1.0,
                    float(completed),
                    total_cost,
                    completed,
                    0,
                    0,
                )
            )
    metrics = _metrics(equity, trades)
    return PRRReplayResult(
        orders=tuple(orders),
        fills=tuple(fills),
        trades=tuple(trades),
        daily_equity=tuple(equity),
        metrics=metrics,
        limitations=(
            "CURRENT_WATCHLIST_BACKFILL_BIAS",
            "HISTORICAL_PIT_NOT_VERIFIED",
            "HISTORICAL_BUYABILITY_NOT_VERIFIED",
            "REFERENCE_MARK_NOT_FILL_PROOF",
            "NO_LEVEL2_OR_ORDER_BOOK",
            "FEE_ASSUMPTIONS_REQUIRE_CURRENT_VERIFICATION",
            "AUXILIARY_DATA_ONLY",
            "FORMAL_OOS_NOT_ESTABLISHED",
            "CASH_CONSTRAINED_OVERLAPPING_DAILY_SLEEVES_SKIPPED",
        ),
    )


def _fixed_rankings(
    *,
    dataset: CandidateResearchDataset,
    code_revision: str,
    config_hash: str,
) -> tuple[tuple[str, tuple[str, ...], Any], ...]:
    b0 = tuple(
        (
            f"B0-{feature_id.value}",
            (str(feature_id),),
            rank_candidates_by_feature(
                dataset,
                feature_id=feature_id,
                model_id=ModelId(f"prr-mvp-1-b0-{feature_id.value}"),
                code_revision=code_revision,
                config_hash=config_hash,
            ),
        )
        for feature_id in dataset.feature_definition_ids
    )
    b1 = tuple(
        (
            name,
            tuple(str(component.feature_id) for component in spec.components),
            rank_candidates_by_transparent_composite(
                dataset,
                spec=spec,
                model_id=ModelId(f"prr-mvp-1-{name.lower()}-v1"),
                code_revision=code_revision,
                config_hash=config_hash,
            ),
        )
        for name, spec in r5_b1_fixed_specs().items()
    )
    return (*b0, *b1)


def _ranking_rows(
    *,
    dataset: CandidateResearchDataset,
    model_name: str,
    feature_ids: tuple[str, ...],
    ranking: Any,
) -> tuple[dict[str, Any], ...]:
    prediction_by_symbol = {item.symbol: item for item in ranking.predictions}
    rejection_by_symbol = {item.symbol: item for item in ranking.rejections}
    target_by_symbol = {row.symbol: row.target for row in dataset.rows}
    rows: list[dict[str, Any]] = []
    for symbol in dataset.population_symbols:
        prediction = prediction_by_symbol.get(symbol)
        rejection = rejection_by_symbol.get(symbol)
        target = target_by_symbol[symbol]
        rows.append(
            {
                "decision_date": dataset.decision_time.value.date().isoformat(),
                "decision_time": dataset.decision_time.isoformat(),
                "target_id": str(dataset.target_id),
                "target_family": _target_family(dataset.target_id.value),
                "model_id": str(ranking.model_id),
                "model_family": "B1" if model_name.startswith("B1-") else "B0",
                "model_name": model_name,
                "symbol": symbol,
                "candidate_population_size": ranking.candidate_population_size,
                "eligible_for_ranking": prediction is not None,
                "rank": prediction.rank if prediction is not None else None,
                "score": prediction.model_score if prediction is not None else None,
                "selected_top5": prediction is not None and prediction.rank is not None and prediction.rank <= 5,
                "feature_definition_ids": list(feature_ids),
                "feature_values": {
                    str(cell.feature_id): cell.value
                    for cell in next(row for row in dataset.rows if row.symbol == symbol).feature_values
                    if cell.status is InputAvailabilityStatus.AVAILABLE
                },
                "target_observation_status": target.status.value,
                "target_value": target.value,
                "rejection_reason_code": rejection.reason_code if rejection is not None else None,
            }
        )
    return tuple(rows)


def _simulate_trade(
    *,
    run_id: str,
    model_id: str,
    decision_date: date,
    exit_date: date,
    symbol: str,
    rank: int,
    reference_price: float,
    reference_timestamp: datetime,
    exit_close: float,
    cost_config: ExploratoryExecutionCostConfig,
    weight: float,
) -> tuple[dict[str, Any], tuple[dict[str, Any], dict[str, Any]]]:
    entry_price = reference_price * (1.0 + cost_config.entry_slippage_bps / 10_000.0)
    exit_price = exit_close * (1.0 - cost_config.exit_slippage_bps / 10_000.0)
    entry_notional = cost_config.normalized_trade_notional * weight
    quantity = entry_notional / entry_price
    buy_commission = max(
        entry_notional * cost_config.buy_commission_bps / 10_000.0,
        cost_config.minimum_commission,
    )
    exit_notional = quantity * exit_price
    sell_commission = max(
        exit_notional * cost_config.sell_commission_bps / 10_000.0,
        cost_config.minimum_commission,
    )
    stamp_duty = exit_notional * cost_config.sell_stamp_duty_bps / 10_000.0
    transfer_fee = (entry_notional + exit_notional) * cost_config.transfer_fee_bps / 10_000.0
    transaction_cost = buy_commission + sell_commission + stamp_duty + transfer_fee
    gross_return = exit_close / reference_price - 1.0
    net_return = (exit_notional - sell_commission - stamp_duty - transfer_fee - entry_notional - buy_commission) / entry_notional
    slippage_cost = quantity * (entry_price - reference_price) + quantity * (exit_close - exit_price)
    entry_fill = {
        "run_id": run_id,
        "model_id": model_id,
        "symbol": symbol,
        "side": "BUY",
        "mark_time": reference_timestamp.isoformat(),
        "reference_price": reference_price,
        "slippage_bps": cost_config.entry_slippage_bps,
        "fill_price": entry_price,
        "normalized_weight": weight,
        "quantity": quantity,
        "commission": buy_commission,
        "stamp_duty": 0.0,
        "transfer_fee": entry_notional * cost_config.transfer_fee_bps / 10_000.0,
        "total_cost": buy_commission + entry_notional * cost_config.transfer_fee_bps / 10_000.0,
        "fill_status": "SIMULATED_REFERENCE_FILL",
        "reason_code": PRR_MVP_1_EXECUTION_ASSUMPTION,
    }
    exit_fill = {
        "run_id": run_id,
        "model_id": model_id,
        "symbol": symbol,
        "side": "SELL",
        "mark_time": datetime.combine(exit_date, time(15, 0), tzinfo=_SHANGHAI).isoformat(),
        "reference_price": exit_close,
        "slippage_bps": cost_config.exit_slippage_bps,
        "fill_price": exit_price,
        "normalized_weight": weight,
        "quantity": quantity,
        "commission": sell_commission,
        "stamp_duty": stamp_duty,
        "transfer_fee": exit_notional * cost_config.transfer_fee_bps / 10_000.0,
        "total_cost": sell_commission + stamp_duty + exit_notional * cost_config.transfer_fee_bps / 10_000.0,
        "fill_status": "SIMULATED_REFERENCE_FILL",
        "reason_code": PRR_MVP_1_EXECUTION_ASSUMPTION,
    }
    trade = {
        "model_id": model_id,
        "decision_date": decision_date.isoformat(),
        "entry_date": decision_date.isoformat(),
        "exit_date": exit_date.isoformat(),
        "symbol": symbol,
        "rank": rank,
        "entry_price": entry_price,
        "exit_price": exit_price,
        "gross_return": gross_return,
        "net_return": net_return,
        "transaction_cost": transaction_cost,
        "slippage_cost": slippage_cost,
        "holding_sessions": 1,
        "trade_status": "COMPLETED",
    }
    return trade, (entry_fill, exit_fill)


def _order_row(
    run_id: str,
    execution: TencentCompositeResearchExecution,
    model_id: str,
    decision_date: date,
    symbol: str,
    rank: int | None,
    reference_price: float | None,
    status: str,
    reason: str,
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "dataset_id": str(execution.dataset_contract.dataset_id),
        "model_id": model_id,
        "decision_date": decision_date.isoformat(),
        "decision_time": datetime.combine(decision_date, time(14, 55), tzinfo=_SHANGHAI).isoformat(),
        "symbol": symbol,
        "side": "BUY",
        "rank": rank,
        "target_weight": None if rank is None else 0.2,
        "reference_price": reference_price,
        "order_status": status,
        "reason_code": reason,
    }


def _equity_row(
    model_id: str,
    session_date: date,
    gross_return: float,
    net_return: float,
    gross_equity: float,
    net_equity: float,
    cash_ratio: float,
    turnover: float,
    transaction_cost: float,
    active_position_count: int,
    missing_entry_count: int,
    missing_exit_count: int,
) -> dict[str, Any]:
    return {
        "model_id": model_id,
        "session_date": session_date.isoformat(),
        "gross_return": gross_return,
        "net_return": net_return,
        "gross_equity": gross_equity,
        "net_equity": net_equity,
        "cash_ratio": cash_ratio,
        "turnover": turnover,
        "transaction_cost": transaction_cost,
        "active_position_count": active_position_count,
        "missing_entry_count": missing_entry_count,
        "missing_exit_count": missing_exit_count,
    }


def _metrics(equity: list[dict[str, Any]], trades: list[dict[str, Any]]) -> dict[str, Any]:
    by_model: dict[str, list[dict[str, Any]]] = {}
    for row in equity:
        by_model.setdefault(str(row["model_id"]), []).append(row)
    result: dict[str, Any] = {
        "annualization_convention": "252_SESSION_DAYS_V1",
        "risk_free_rate_assumption": 0.0,
        "missing_data_treatment": "EXPLICIT_SKIP_OR_INCOMPLETE_ONLY",
        "models": {},
    }
    for model_id, rows in sorted(by_model.items()):
        returns = [float(row["net_return"]) for row in rows]
        net_equity = float(rows[-1]["net_equity"]) if rows else 1.0
        gross_equity = float(rows[-1]["gross_equity"]) if rows else 1.0
        sessions = max(len(rows), 1)
        annualized = net_equity ** (252.0 / sessions) - 1.0 if net_equity > 0.0 else None
        volatility = pstdev(returns) * math.sqrt(252.0) if len(returns) > 1 else 0.0
        downside = [min(0.0, value) for value in returns]
        downside_deviation = pstdev(downside) * math.sqrt(252.0) if len(downside) > 1 else 0.0
        peak = 1.0
        drawdowns: list[float] = []
        for row in rows:
            peak = max(peak, float(row["net_equity"]))
            drawdowns.append(float(row["net_equity"]) / peak - 1.0)
        max_drawdown = min(drawdowns) if drawdowns else 0.0
        model_trades = [item for item in trades if item["model_id"] == model_id]
        wins = [float(item["net_return"]) for item in model_trades if float(item["net_return"]) > 0.0]
        losses = [float(item["net_return"]) for item in model_trades if float(item["net_return"]) < 0.0]
        result["models"][model_id] = {
            "gross_cumulative_return": gross_equity - 1.0,
            "net_cumulative_return": net_equity - 1.0,
            "annualized_return": annualized,
            "annualized_volatility": volatility,
            "maximum_drawdown": max_drawdown,
            "sharpe_ratio": (mean(returns) / pstdev(returns) * math.sqrt(252.0) if len(returns) > 1 and pstdev(returns) else None),
            "sortino_ratio": (mean(returns) / downside_deviation * math.sqrt(252.0) if downside_deviation else None),
            "calmar_ratio": (annualized / abs(max_drawdown) if annualized is not None and max_drawdown < 0.0 else None),
            "turnover": sum(float(row["turnover"]) for row in rows),
            "total_transaction_cost": sum(float(item["transaction_cost"]) for item in model_trades),
            "total_slippage_cost": sum(float(item["slippage_cost"]) for item in model_trades),
            "average_cash_ratio": mean(float(row["cash_ratio"]) for row in rows),
            "active_session_count": sum(1 for row in rows if int(row["active_position_count"]) > 0),
            "trade_count": len(model_trades),
            "completed_trade_count": len(model_trades),
            "win_rate": len(wins) / len(model_trades) if model_trades else None,
            "average_win": mean(wins) if wins else None,
            "average_loss": mean(losses) if losses else None,
            "profit_factor": (sum(wins) / abs(sum(losses)) if losses else None),
            "average_holding_sessions": 1.0 if model_trades else None,
            "missing_entry_count": 0,
            "missing_exit_count": 0,
            "no_candidate_dates": sum(1 for row in rows if row["cash_ratio"] == 1.0),
            "descriptive_only": True,
        }
    return result


def _target_family(target_id: str) -> str:
    if target_id == str(R5_NEXT_SESSION_RETURN_TARGET_ID):
        return "CLOSE_RETURN"
    if "mfe" in target_id.lower():
        return "MFE"
    return "MAE"
