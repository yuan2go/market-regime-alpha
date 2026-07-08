"""Standalone daily-close 2.5% dividend T-grid test model.

This module is intentionally separate from the production dividend T timing
model. It implements only the experimental rule under test:

- no base position;
- decide once per trading day, on the last 5-minute bar;
- buy 30% of remaining cash when flat and the day closes down 2% or more;
- otherwise buy a 10% initial-cash layer after each further 2.5% slide,
  unless the close is below the 20-day moving average;
- close profitable or near-breakeven sellable holdings when the day closes up more than 3%;
- sell mature layers after a 2.5% rebound.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
import math
from typing import Any


@dataclass(frozen=True)
class Grid25TConfig:
    initial_cash: float = 500_000.0
    initial_base_position_pct: float = 0.0
    daily_drop_buy_trigger_pct: float = 0.02
    daily_drop_cash_pct: float = 0.30
    daily_rise_clear_pct: float = 0.03
    daily_clear_min_realized_return_pct: float = -0.005
    grid_pct: float = 0.025
    layer_cash_pct: float = 0.10
    enable_ladder_ma_filter: bool = True
    ma_window_days: int = 20
    enable_dividend_reinvestment: bool = True
    commission_rate: float = 0.00025
    stamp_duty_rate: float = 0.0005
    slippage_bps: float = 2.0
    min_lot: int = 100
    periods_per_year: int = 252
    enable_t1: bool = True


@dataclass(frozen=True)
class Grid25TTrade:
    timestamp: str
    action: str
    side: str
    shares: int
    price: float
    cash_after: float
    equity_after: float
    reason: str
    layer_id: int | None = None
    realized_pnl: float | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class Grid25TPoint:
    timestamp: str
    close: float
    equity: float
    cash: float
    base_shares: int
    grid_shares: int
    active_layer_count: int
    next_buy_price: float | None
    ma_close: float | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class Grid25TResult:
    symbol: str
    start: str
    end: str
    rows: int
    config: Grid25TConfig
    initial_cash: float
    final_equity: float
    total_return: float
    benchmark_return: float
    excess_return: float
    annualized_return: float
    max_drawdown: float
    trade_count: int
    completed_cycles: int
    win_rate: float | None
    realized_pnl: float
    buy_count: int
    sell_count: int
    daily_drop_buy_count: int
    ladder_buy_count: int
    target_sell_count: int
    daily_clear_count: int
    cash_exhausted_count: int
    t1_blocked_closeout_shares: int
    ma_filter_blocked_ladder_count: int
    daily_clear_skipped_layer_count: int
    dividend_event_count: int
    cash_dividend_total: float
    share_bonus_total: int
    trades: tuple[Grid25TTrade, ...] = field(default_factory=tuple)
    equity_curve: tuple[Grid25TPoint, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["config"] = asdict(self.config)
        return data


@dataclass(frozen=True)
class _DailyDecisionBar:
    timestamp: Any
    trade_date: date
    open: float
    high: float
    low: float
    close: float
    ma_close: float | None
    cash_dividend_per_share: float = 0.0
    share_bonus_ratio: float = 0.0


@dataclass
class _GridLayer:
    layer_id: int
    buy_timestamp: str
    buy_trade_date: date
    shares: int
    buy_price: float
    reference_price: float
    target_price: float
    cost_basis: float


def run_grid_25t_backtest(bars: Any, *, config: Grid25TConfig | None = None) -> Grid25TResult:
    """Run the standalone daily-close 2.5% T-grid test on 5-minute bars."""

    cfg = config or Grid25TConfig()
    _validate_config(cfg)
    data = _normalize_bars(bars)
    if data.empty:
        raise ValueError("grid 25T backtest requires at least one bar")

    symbol = str(data["symbol"].iloc[0])
    first_open = float(data["open"].iloc[0])
    if first_open <= 0:
        raise ValueError("first open price must be positive")

    cash = float(cfg.initial_cash)
    base_shares = 0
    active_layers: list[_GridLayer] = []
    trades: list[Grid25TTrade] = []
    equity_curve: list[Grid25TPoint] = []
    completed_pnls: list[float] = []
    cash_exhausted_count = 0
    t1_blocked_closeout_shares = 0
    ma_filter_blocked_ladder_count = 0
    daily_clear_skipped_layer_count = 0
    dividend_event_count = 0
    cash_dividend_total = 0.0
    share_bonus_total = 0
    next_layer_id = 1
    last_buy_reference_price: float | None = None

    first_decision = True
    for daily_bar in _iter_daily_decision_bars(data, cfg):
        timestamp_text = str(daily_bar.timestamp)
        close_price = daily_bar.close
        day_return = close_price / daily_bar.open - 1.0
        if cfg.enable_dividend_reinvestment:
            corporate_action = _apply_corporate_action(active_layers, daily_bar)
            if corporate_action.applied:
                cash += corporate_action.cash_dividend
                dividend_event_count += 1
                cash_dividend_total += corporate_action.cash_dividend
                share_bonus_total += corporate_action.share_bonus_shares

        sold_layers: list[_GridLayer] = []
        if day_return > cfg.daily_rise_clear_pct and active_layers:
            sellable_layers = _sellable_layers(active_layers, daily_bar.trade_date, cfg)
            blocked_shares = sum(layer.shares for layer in active_layers if layer not in sellable_layers)
            t1_blocked_closeout_shares += blocked_shares
            clearable_layers = [
                layer
                for layer in sellable_layers
                if _layer_realized_return(layer, raw_sell_price=close_price, cfg=cfg) >= cfg.daily_clear_min_realized_return_pct
            ]
            daily_clear_skipped_layer_count += len(sellable_layers) - len(clearable_layers)
            if clearable_layers:
                sell_execution = _sell_layers(
                    clearable_layers,
                    action="DAILY_CLEAR",
                    reason=(
                        f"daily close up {day_return:.2%}, clear layers with realized return "
                        f">= {cfg.daily_clear_min_realized_return_pct:.2%}"
                    ),
                    raw_sell_price=close_price,
                    timestamp_text=timestamp_text,
                    close_price=close_price,
                    cash_ref={"cash": cash},
                    base_shares=base_shares,
                    active_layers=active_layers,
                    completed_pnls=completed_pnls,
                    trades=trades,
                    cfg=cfg,
                )
                cash += sell_execution.proceeds
                sold_layers.extend(clearable_layers)
            active_layers = _remove_layers(active_layers, sold_layers)
            last_buy_reference_price = _last_reference_price(active_layers)
        else:
            target_sold_layers = [
                layer
                for layer in sorted(active_layers, key=lambda item: item.target_price)
                if close_price >= layer.target_price and _is_sellable(layer, daily_bar.trade_date, cfg)
            ]
            if target_sold_layers:
                sell_execution = _sell_layers(
                    target_sold_layers,
                    action="TARGET_SELL",
                    reason=f"daily-close rebound {cfg.grid_pct:.1%} from layer buy",
                    raw_sell_price=close_price,
                    timestamp_text=timestamp_text,
                    close_price=close_price,
                    cash_ref={"cash": cash},
                    base_shares=base_shares,
                    active_layers=active_layers,
                    completed_pnls=completed_pnls,
                    trades=trades,
                    cfg=cfg,
                )
                cash += sell_execution.proceeds
                sold_layers.extend(target_sold_layers)
            active_layers = _remove_layers(active_layers, sold_layers)
            last_buy_reference_price = _last_reference_price(active_layers)

            if not sold_layers:
                buy_target_notional: float | None = None
                buy_action = ""
                buy_reason = ""
                if not active_layers and day_return <= -cfg.daily_drop_buy_trigger_pct:
                    buy_target_notional = cash * cfg.daily_drop_cash_pct
                    buy_action = "DAILY_DROP_BUY"
                    buy_reason = f"daily close down {day_return:.2%}, buy {cfg.daily_drop_cash_pct:.0%} remaining cash"
                elif last_buy_reference_price is not None and close_price <= last_buy_reference_price * (1.0 - cfg.grid_pct):
                    if _ladder_ma_filter_blocks(daily_bar, cfg):
                        ma_filter_blocked_ladder_count += 1
                    else:
                        buy_target_notional = cfg.initial_cash * cfg.layer_cash_pct
                        buy_action = "LADDER_BUY"
                        buy_reason = f"daily-close slide {cfg.grid_pct:.1%} from last add reference"

                if buy_target_notional is not None and buy_target_notional > 0:
                    shares = _shares_for_notional(target_notional=buy_target_notional, price=_buy_fill_price(close_price, cfg), cash=cash, cfg=cfg)
                    if shares <= 0:
                        cash_exhausted_count += 1
                    else:
                        buy_price = _buy_fill_price(close_price, cfg)
                        cost = _buy_cost(shares, buy_price, cfg)
                        cash -= cost
                        layer = _GridLayer(
                            layer_id=next_layer_id,
                            buy_timestamp=timestamp_text,
                            buy_trade_date=daily_bar.trade_date,
                            shares=shares,
                            buy_price=buy_price,
                            reference_price=close_price,
                            target_price=close_price * (1.0 + cfg.grid_pct),
                            cost_basis=cost,
                        )
                        active_layers.append(layer)
                        last_buy_reference_price = close_price
                        equity_after = cash + (base_shares + sum(item.shares for item in active_layers)) * close_price
                        trades.append(
                            Grid25TTrade(
                                timestamp=timestamp_text,
                                action=buy_action,
                                side="BUY",
                                shares=shares,
                                price=round(buy_price, 4),
                                cash_after=round(cash, 2),
                                equity_after=round(equity_after, 2),
                                reason=buy_reason,
                                layer_id=next_layer_id,
                            )
                        )
                        next_layer_id += 1

        if first_decision and cfg.initial_base_position_pct > 0:
            raise ValueError("daily-close test mode is configured for no base position; set initial_base_position_pct=0")
        first_decision = False

        grid_shares = sum(layer.shares for layer in active_layers)
        equity = cash + (base_shares + grid_shares) * close_price
        next_buy_price = None if last_buy_reference_price is None else last_buy_reference_price * (1.0 - cfg.grid_pct)
        equity_curve.append(
            Grid25TPoint(
                timestamp=timestamp_text,
                close=round(close_price, 4),
                equity=round(equity, 2),
                cash=round(cash, 2),
                base_shares=base_shares,
                grid_shares=grid_shares,
                active_layer_count=len(active_layers),
                next_buy_price=None if next_buy_price is None else round(next_buy_price, 4),
                ma_close=None if daily_bar.ma_close is None else round(daily_bar.ma_close, 4),
            )
        )

    final_equity = equity_curve[-1].equity
    total_return = final_equity / cfg.initial_cash - 1.0
    benchmark_return = float(data["close"].iloc[-1]) / first_open - 1.0
    completed_cycles = len(completed_pnls)
    winning_cycles = sum(1 for value in completed_pnls if value > 0)
    win_rate = winning_cycles / completed_cycles if completed_cycles else None
    return Grid25TResult(
        symbol=symbol,
        start=str(data["timestamp"].iloc[0]),
        end=str(data["timestamp"].iloc[-1]),
        rows=len(data),
        config=cfg,
        initial_cash=cfg.initial_cash,
        final_equity=round(final_equity, 2),
        total_return=round(total_return, 6),
        benchmark_return=round(benchmark_return, 6),
        excess_return=round(total_return - benchmark_return, 6),
        annualized_return=round(_annualized_return(total_return, len(equity_curve), cfg.periods_per_year), 6),
        max_drawdown=round(max_drawdown([point.equity for point in equity_curve]), 6),
        trade_count=len(trades),
        completed_cycles=completed_cycles,
        win_rate=None if win_rate is None else round(win_rate, 6),
        realized_pnl=round(sum(completed_pnls), 2),
        buy_count=sum(1 for trade in trades if trade.side == "BUY"),
        sell_count=sum(1 for trade in trades if trade.side == "SELL"),
        daily_drop_buy_count=sum(1 for trade in trades if trade.action == "DAILY_DROP_BUY"),
        ladder_buy_count=sum(1 for trade in trades if trade.action == "LADDER_BUY"),
        target_sell_count=sum(1 for trade in trades if trade.action == "TARGET_SELL"),
        daily_clear_count=sum(1 for trade in trades if trade.action == "DAILY_CLEAR"),
        cash_exhausted_count=cash_exhausted_count,
        t1_blocked_closeout_shares=t1_blocked_closeout_shares,
        ma_filter_blocked_ladder_count=ma_filter_blocked_ladder_count,
        daily_clear_skipped_layer_count=daily_clear_skipped_layer_count,
        dividend_event_count=dividend_event_count,
        cash_dividend_total=round(cash_dividend_total, 2),
        share_bonus_total=share_bonus_total,
        trades=tuple(trades),
        equity_curve=tuple(equity_curve),
    )


@dataclass(frozen=True)
class _CorporateAction:
    cash_dividend: float = 0.0
    share_bonus_shares: int = 0

    @property
    def applied(self) -> bool:
        return self.cash_dividend > 0 or self.share_bonus_shares > 0


@dataclass(frozen=True)
class _SellExecution:
    proceeds: float


def _sell_layers(
    layers: list[_GridLayer],
    *,
    action: str,
    reason: str,
    raw_sell_price: float,
    timestamp_text: str,
    close_price: float,
    cash_ref: dict[str, float],
    base_shares: int,
    active_layers: list[_GridLayer],
    completed_pnls: list[float],
    trades: list[Grid25TTrade],
    cfg: Grid25TConfig,
) -> _SellExecution:
    if not layers:
        return _SellExecution(proceeds=0.0)
    sell_price = _sell_fill_price(raw_sell_price, cfg)
    total_shares = sum(layer.shares for layer in layers)
    proceeds = _sell_proceeds(total_shares, sell_price, cfg)
    realized_pnls: list[float] = []
    for layer in layers:
        layer_proceeds = _sell_proceeds(layer.shares, sell_price, cfg)
        realized_pnl = layer_proceeds - layer.cost_basis
        realized_pnls.append(realized_pnl)
        completed_pnls.append(realized_pnl)
    realized_pnl_total = sum(realized_pnls)
    sold_ids = {layer.layer_id for layer in layers}
    grid_shares_after = sum(item.shares for item in active_layers if item.layer_id not in sold_ids)
    equity_after = cash_ref["cash"] + proceeds + (base_shares + grid_shares_after) * close_price
    trades.append(
        Grid25TTrade(
            timestamp=timestamp_text,
            action=action,
            side="SELL",
            shares=total_shares,
            price=round(sell_price, 4),
            cash_after=round(cash_ref["cash"] + proceeds, 2),
            equity_after=round(equity_after, 2),
            reason=reason,
            layer_id=None if len(layers) > 1 else layers[0].layer_id,
            realized_pnl=round(realized_pnl_total, 2),
        )
    )
    return _SellExecution(proceeds=proceeds)


def max_drawdown(equity_values: list[float] | tuple[float, ...]) -> float:
    peak = -math.inf
    worst = 0.0
    for value in equity_values:
        peak = max(peak, value)
        if peak > 0:
            worst = min(worst, value / peak - 1.0)
    return worst


def _iter_daily_decision_bars(data: Any, cfg: Grid25TConfig) -> list[_DailyDecisionBar]:
    with_trade_date = data.copy()
    with_trade_date["trade_date"] = with_trade_date["timestamp"].dt.date
    daily_records: list[dict[str, Any]] = []
    for trade_date, day in with_trade_date.groupby("trade_date", sort=True):
        first = day.iloc[0]
        last = day.iloc[-1]
        daily_records.append(
            {
                "timestamp": last["timestamp"],
                "trade_date": trade_date,
                "open": float(first["open"]),
                "high": float(day["high"].max()),
                "low": float(day["low"].min()),
                "close": float(last["close"]),
                "cash_dividend_per_share": _positive_max(day, "cash_dividend_per_share"),
                "share_bonus_ratio": _positive_max(day, "share_bonus_ratio"),
            }
        )
    closes: list[float] = []
    daily_bars: list[_DailyDecisionBar] = []
    for record in daily_records:
        closes.append(record["close"])
        ma_close = sum(closes[-cfg.ma_window_days :]) / cfg.ma_window_days if len(closes) >= cfg.ma_window_days else None
        daily_bars.append(
            _DailyDecisionBar(
                timestamp=record["timestamp"],
                trade_date=record["trade_date"],
                open=record["open"],
                high=record["high"],
                low=record["low"],
                close=record["close"],
                ma_close=ma_close,
                cash_dividend_per_share=record["cash_dividend_per_share"],
                share_bonus_ratio=record["share_bonus_ratio"],
            )
        )
    return daily_bars


def _normalize_bars(frame: Any) -> Any:
    import pandas as pd

    required = {"symbol", "timestamp", "open", "high", "low", "close"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"grid 25T bars missing required fields: {', '.join(missing)}")
    data = frame.copy()
    data["timestamp"] = pd.to_datetime(data["timestamp"])
    data = data.sort_values("timestamp").reset_index(drop=True)
    for column in ("open", "high", "low", "close"):
        data[column] = pd.to_numeric(data[column], errors="coerce")
    data = data.dropna(subset=["open", "high", "low", "close"])
    data = data[(data["open"] > 0) & (data["high"] > 0) & (data["low"] > 0) & (data["close"] > 0)]
    return data.reset_index(drop=True)


def _validate_config(cfg: Grid25TConfig) -> None:
    if cfg.initial_cash <= 0:
        raise ValueError("initial_cash must be positive")
    if cfg.initial_base_position_pct != 0:
        raise ValueError("daily-close test model does not keep a base position")
    if cfg.daily_drop_buy_trigger_pct <= 0:
        raise ValueError("daily_drop_buy_trigger_pct must be positive")
    if not 0 < cfg.daily_drop_cash_pct <= 1:
        raise ValueError("daily_drop_cash_pct must be between 0 and 1")
    if cfg.daily_rise_clear_pct <= 0:
        raise ValueError("daily_rise_clear_pct must be positive")
    if cfg.grid_pct <= 0:
        raise ValueError("grid_pct must be positive")
    if cfg.layer_cash_pct <= 0:
        raise ValueError("layer_cash_pct must be positive")
    if cfg.ma_window_days <= 0:
        raise ValueError("ma_window_days must be positive")
    if cfg.min_lot <= 0:
        raise ValueError("min_lot must be positive")


def _shares_for_notional(*, target_notional: float, price: float, cash: float, cfg: Grid25TConfig) -> int:
    gross_lot_cost = _buy_cost(cfg.min_lot, price, cfg)
    if cash < gross_lot_cost:
        return 0
    target_lots = int(target_notional // gross_lot_cost)
    if target_lots <= 0:
        target_lots = 1
    affordable_lots = int(cash // gross_lot_cost)
    return max(0, min(target_lots, affordable_lots) * cfg.min_lot)


def _buy_fill_price(raw_price: float, cfg: Grid25TConfig) -> float:
    return raw_price * (1.0 + cfg.slippage_bps / 10_000.0)


def _sell_fill_price(raw_price: float, cfg: Grid25TConfig) -> float:
    return raw_price * (1.0 - cfg.slippage_bps / 10_000.0)


def _buy_cost(shares: int, price: float, cfg: Grid25TConfig) -> float:
    notional = shares * price
    return notional * (1.0 + cfg.commission_rate)


def _sell_proceeds(shares: int, price: float, cfg: Grid25TConfig) -> float:
    notional = shares * price
    return notional * (1.0 - cfg.commission_rate - cfg.stamp_duty_rate)


def _sellable_layers(layers: list[_GridLayer], trade_date: date, cfg: Grid25TConfig) -> list[_GridLayer]:
    return [layer for layer in layers if _is_sellable(layer, trade_date, cfg)]


def _is_sellable(layer: _GridLayer, trade_date: date, cfg: Grid25TConfig) -> bool:
    return not cfg.enable_t1 or layer.buy_trade_date < trade_date


def _apply_corporate_action(layers: list[_GridLayer], daily_bar: _DailyDecisionBar) -> _CorporateAction:
    total_shares = sum(layer.shares for layer in layers)
    if total_shares <= 0:
        return _CorporateAction()
    cash_dividend = round(total_shares * daily_bar.cash_dividend_per_share, 2) if daily_bar.cash_dividend_per_share > 0 else 0.0
    share_bonus_shares = 0
    if daily_bar.share_bonus_ratio > 0:
        for layer in layers:
            bonus_shares = int(layer.shares * daily_bar.share_bonus_ratio)
            if bonus_shares > 0:
                layer.shares += bonus_shares
                share_bonus_shares += bonus_shares
    return _CorporateAction(cash_dividend=cash_dividend, share_bonus_shares=share_bonus_shares)


def _layer_realized_return(layer: _GridLayer, *, raw_sell_price: float, cfg: Grid25TConfig) -> float:
    sell_price = _sell_fill_price(raw_sell_price, cfg)
    proceeds = _sell_proceeds(layer.shares, sell_price, cfg)
    if layer.cost_basis <= 0:
        return 0.0
    return proceeds / layer.cost_basis - 1.0


def _ladder_ma_filter_blocks(daily_bar: _DailyDecisionBar, cfg: Grid25TConfig) -> bool:
    return cfg.enable_ladder_ma_filter and daily_bar.ma_close is not None and daily_bar.close < daily_bar.ma_close


def _positive_max(day: Any, column: str) -> float:
    if column not in day.columns:
        return 0.0
    value = day[column].fillna(0).max()
    return max(0.0, float(value))


def _remove_layers(layers: list[_GridLayer], removed_layers: list[_GridLayer]) -> list[_GridLayer]:
    removed_ids = {layer.layer_id for layer in removed_layers}
    return [layer for layer in layers if layer.layer_id not in removed_ids]


def _last_reference_price(layers: list[_GridLayer]) -> float | None:
    if not layers:
        return None
    return max(layers, key=lambda layer: layer.layer_id).reference_price


def _annualized_return(total_return: float, periods: int, periods_per_year: int) -> float:
    if periods <= 0 or periods_per_year <= 0:
        return 0.0
    if total_return <= -1:
        return -1.0
    return (1.0 + total_return) ** (periods_per_year / periods) - 1.0
