"""Minimal backtesting utilities for simple daily OHLCV experiments."""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Sequence


REQUIRED_OHLCV_FIELDS = (
    "symbol",
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "volume",
)


@dataclass(frozen=True)
class OHLCVBar:
    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class BacktestResult:
    symbol: str
    start: datetime
    end: datetime
    rows: int
    fast_window: int
    slow_window: int
    initial_cash: float
    final_equity: float
    total_return: float
    annualized_return: float
    max_drawdown: float
    sharpe: float | None
    trade_events: int
    completed_trades: int
    win_rate: float | None
    equity_curve: tuple[float, ...]
    signals: tuple[int, ...]


def load_ohlcv_csv(path: str | Path, symbol: str | None = None) -> list[OHLCVBar]:
    """Load a single-symbol OHLCV CSV that follows docs/Data-Spec.md."""
    csv_path = Path(path)
    rows: list[OHLCVBar] = []

    with csv_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        missing = [field for field in REQUIRED_OHLCV_FIELDS if field not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"{csv_path} is missing required OHLCV fields: {', '.join(missing)}")

        for line_number, row in enumerate(reader, start=2):
            if symbol and row["symbol"] != symbol:
                continue

            try:
                bar = OHLCVBar(
                    symbol=row["symbol"],
                    timestamp=datetime.fromisoformat(row["timestamp"]),
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row["volume"]),
                )
            except (KeyError, ValueError) as exc:
                raise ValueError(f"Invalid OHLCV value in {csv_path} line {line_number}") from exc

            if bar.high < max(bar.open, bar.close) or bar.low > min(bar.open, bar.close):
                raise ValueError(f"Invalid OHLC range in {csv_path} line {line_number}")
            rows.append(bar)

    rows.sort(key=lambda bar: bar.timestamp)
    if not rows:
        target = f" for symbol {symbol}" if symbol else ""
        raise ValueError(f"No OHLCV rows found in {csv_path}{target}")
    return rows


def moving_average(values: Sequence[float], window: int) -> tuple[float | None, ...]:
    if window <= 0:
        raise ValueError("window must be positive")

    averages: list[float | None] = [None] * len(values)
    running_total = 0.0
    for index, value in enumerate(values):
        running_total += value
        if index >= window:
            running_total -= values[index - window]
        if index >= window - 1:
            averages[index] = running_total / window
    return tuple(averages)


def run_moving_average_crossover(
    bars: Sequence[OHLCVBar],
    *,
    fast_window: int,
    slow_window: int,
    initial_cash: float = 10_000.0,
    periods_per_year: int = 252,
) -> BacktestResult:
    """Run a long/cash moving-average crossover backtest.

    The strategy is long when the fast moving average is above the slow moving
    average. Signals are evaluated on each close and applied on the next bar.
    """
    if fast_window <= 0 or slow_window <= 0:
        raise ValueError("fast_window and slow_window must be positive")
    if fast_window >= slow_window:
        raise ValueError("fast_window must be smaller than slow_window")
    if initial_cash <= 0:
        raise ValueError("initial_cash must be positive")

    ordered_bars = tuple(sorted(bars, key=lambda bar: bar.timestamp))
    if len(ordered_bars) <= slow_window:
        raise ValueError("not enough bars to apply the slow moving average and next-bar execution")

    symbols = {bar.symbol for bar in ordered_bars}
    if len(symbols) != 1:
        raise ValueError(f"expected one symbol, found: {', '.join(sorted(symbols))}")

    closes = [bar.close for bar in ordered_bars]
    fast_ma = moving_average(closes, fast_window)
    slow_ma = moving_average(closes, slow_window)
    signals = tuple(
        1 if fast_value is not None and slow_value is not None and fast_value > slow_value else 0
        for fast_value, slow_value in zip(fast_ma, slow_ma)
    )

    equity = initial_cash
    equity_curve = [equity]
    portfolio_returns: list[float] = []
    for index in range(1, len(ordered_bars)):
        position = signals[index - 1]
        asset_return = closes[index] / closes[index - 1] - 1.0
        period_return = position * asset_return
        portfolio_returns.append(period_return)
        equity *= 1.0 + period_return
        equity_curve.append(equity)

    trade_events, completed_returns = _trade_stats(signals, closes)
    win_rate = None
    if completed_returns:
        win_rate = sum(1 for trade_return in completed_returns if trade_return > 0) / len(completed_returns)

    total_return = equity / initial_cash - 1.0
    annualized_return = _annualized_return(total_return, len(portfolio_returns), periods_per_year)
    sharpe = _sharpe_ratio(portfolio_returns, periods_per_year)

    return BacktestResult(
        symbol=next(iter(symbols)),
        start=ordered_bars[0].timestamp,
        end=ordered_bars[-1].timestamp,
        rows=len(ordered_bars),
        fast_window=fast_window,
        slow_window=slow_window,
        initial_cash=initial_cash,
        final_equity=equity,
        total_return=total_return,
        annualized_return=annualized_return,
        max_drawdown=_max_drawdown(equity_curve),
        sharpe=sharpe,
        trade_events=trade_events,
        completed_trades=len(completed_returns),
        win_rate=win_rate,
        equity_curve=tuple(equity_curve),
        signals=signals,
    )


def _trade_stats(signals: Sequence[int], closes: Sequence[float]) -> tuple[int, list[float]]:
    trade_events = 0
    completed_returns: list[float] = []
    entry_price: float | None = None
    previous_signal = signals[0]

    for index, signal in enumerate(signals[1:], start=1):
        if signal == previous_signal:
            continue

        trade_events += 1
        if previous_signal == 0 and signal == 1:
            entry_price = closes[index]
        elif previous_signal == 1 and signal == 0:
            if entry_price is not None:
                completed_returns.append(closes[index] / entry_price - 1.0)
            entry_price = None
        previous_signal = signal

    return trade_events, completed_returns


def _annualized_return(total_return: float, periods: int, periods_per_year: int) -> float:
    if periods <= 0 or total_return <= -1.0:
        return float("nan")
    return (1.0 + total_return) ** (periods_per_year / periods) - 1.0


def _sharpe_ratio(returns: Sequence[float], periods_per_year: int) -> float | None:
    if len(returns) < 2:
        return None

    mean_return = sum(returns) / len(returns)
    variance = sum((period_return - mean_return) ** 2 for period_return in returns) / (len(returns) - 1)
    standard_deviation = math.sqrt(variance)
    if standard_deviation == 0:
        return None
    return mean_return / standard_deviation * math.sqrt(periods_per_year)


def _max_drawdown(equity_curve: Sequence[float]) -> float:
    peak = equity_curve[0]
    worst_drawdown = 0.0
    for equity in equity_curve:
        peak = max(peak, equity)
        drawdown = equity / peak - 1.0
        worst_drawdown = min(worst_drawdown, drawdown)
    return worst_drawdown

