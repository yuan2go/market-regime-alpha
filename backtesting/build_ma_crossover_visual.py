#!/usr/bin/env python3
"""Build a self-contained HTML visualization for the MA crossover prototype."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from market_regime_alpha.backtesting import (
    OHLCVBar,
    BacktestResult,
    load_ohlcv_csv,
    moving_average,
    run_moving_average_crossover,
)


DEFAULT_DATA = PROJECT_ROOT / "data" / "raw" / "sample_etf_ohlcv.csv"
DEFAULT_OUTPUT = PROJECT_ROOT / "backtesting" / "ma_crossover_visual.html"


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a static web chart for the MA crossover backtest.")
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA, help="OHLCV CSV path.")
    parser.add_argument("--symbol", default="SAMPLE_ETF", help="Symbol to load from the CSV.")
    parser.add_argument("--fast-window", type=int, default=3, help="Fast moving-average window.")
    parser.add_argument("--slow-window", type=int, default=8, help="Slow moving-average window.")
    parser.add_argument("--initial-cash", type=float, default=10_000.0, help="Starting cash.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Output HTML file.")
    args = parser.parse_args()

    bars = load_ohlcv_csv(args.data, symbol=args.symbol)
    result = run_moving_average_crossover(
        bars,
        fast_window=args.fast_window,
        slow_window=args.slow_window,
        initial_cash=args.initial_cash,
    )
    payload = build_visual_payload(bars, result, data_path=args.data)

    output_path = args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(build_html(payload), encoding="utf-8")
    print(f"Wrote {output_path}")
    return 0


def build_visual_payload(
    bars: list[OHLCVBar],
    result: BacktestResult,
    *,
    data_path: Path,
) -> dict[str, Any]:
    closes = [bar.close for bar in bars]
    fast_ma = moving_average(closes, result.fast_window)
    slow_ma = moving_average(closes, result.slow_window)

    points = []
    for index, bar in enumerate(bars):
        points.append(
            {
                "date": bar.timestamp.date().isoformat(),
                "close": round(bar.close, 4),
                "fast_ma": _round_optional(fast_ma[index]),
                "slow_ma": _round_optional(slow_ma[index]),
                "signal": result.signals[index],
                "equity": round(result.equity_curve[index], 4),
            }
        )

    return {
        "meta": {
            "title": "ETF 均线交叉可视化",
            "subtitle": "价格、均线、交易信号和权益曲线",
            "symbol": result.symbol,
            "data_path": str(data_path),
            "start": result.start.date().isoformat(),
            "end": result.end.date().isoformat(),
            "rows": result.rows,
            "fast_window": result.fast_window,
            "slow_window": result.slow_window,
        },
        "metrics": {
            "initial_cash": result.initial_cash,
            "final_equity": result.final_equity,
            "total_return": result.total_return,
            "annualized_return": result.annualized_return,
            "max_drawdown": result.max_drawdown,
            "sharpe": result.sharpe,
            "trade_events": result.trade_events,
            "completed_trades": result.completed_trades,
            "win_rate": result.win_rate,
        },
        "points": points,
    }


def build_html(payload: dict[str, Any]) -> str:
    chart_json = json.dumps(payload, ensure_ascii=False, indent=2).replace("</", "<\\/")
    return HTML_TEMPLATE.replace("__CHART_DATA__", chart_json)


def _round_optional(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value, 4)


HTML_TEMPLATE = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>ETF 均线交叉可视化</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f6f8fb;
      --panel: #ffffff;
      --text: #172033;
      --muted: #667085;
      --border: #d8dee8;
      --grid: #e7ebf2;
      --close: #1f6feb;
      --fast: #d97706;
      --slow: #334155;
      --buy: #15803d;
      --sell: #dc2626;
      --equity: #0f766e;
      --shadow: 0 10px 30px rgba(23, 32, 51, 0.08);
    }

    * {
      box-sizing: border-box;
    }

    body {
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.5;
    }

    main {
      width: min(1180px, calc(100vw - 32px));
      margin: 0 auto;
      padding: 32px 0 48px;
    }

    header {
      display: flex;
      justify-content: space-between;
      gap: 20px;
      align-items: flex-end;
      margin-bottom: 20px;
    }

    h1 {
      margin: 0;
      font-size: clamp(28px, 4vw, 42px);
      letter-spacing: 0;
    }

    .subtitle {
      margin: 8px 0 0;
      color: var(--muted);
      font-size: 16px;
    }

    .badge {
      display: inline-flex;
      align-items: center;
      border: 1px solid var(--border);
      border-radius: 999px;
      padding: 6px 12px;
      background: #fff;
      color: var(--muted);
      white-space: nowrap;
      font-size: 13px;
    }

    .metrics {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
      margin-bottom: 16px;
    }

    .metric {
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 14px 16px;
      box-shadow: var(--shadow);
      min-width: 0;
    }

    .metric-label {
      color: var(--muted);
      font-size: 13px;
      margin-bottom: 4px;
    }

    .metric-value {
      font-size: 24px;
      font-weight: 700;
      letter-spacing: 0;
    }

    .chart-panel {
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 8px;
      box-shadow: var(--shadow);
      padding: 18px;
      margin-top: 16px;
    }

    .panel-title {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      margin-bottom: 8px;
    }

    .panel-title h2 {
      font-size: 18px;
      margin: 0;
    }

    .legend {
      display: flex;
      flex-wrap: wrap;
      justify-content: flex-end;
      gap: 12px;
      color: var(--muted);
      font-size: 13px;
    }

    .legend-item {
      display: inline-flex;
      align-items: center;
      gap: 6px;
    }

    .legend-swatch {
      width: 18px;
      height: 3px;
      border-radius: 99px;
      background: currentColor;
    }

    svg {
      display: block;
      width: 100%;
      height: auto;
      overflow: visible;
    }

    .axis-label {
      fill: var(--muted);
      font-size: 12px;
    }

    .grid-line {
      stroke: var(--grid);
      stroke-width: 1;
    }

    .axis-line {
      stroke: var(--border);
      stroke-width: 1;
    }

    .line {
      fill: none;
      stroke-width: 2.5;
      stroke-linecap: round;
      stroke-linejoin: round;
    }

    .long-zone {
      fill: var(--buy);
      opacity: 0.07;
    }

    .note {
      margin: 14px 0 0;
      color: var(--muted);
      font-size: 13px;
    }

    .tooltip {
      position: fixed;
      z-index: 5;
      display: none;
      min-width: 190px;
      pointer-events: none;
      background: rgba(255, 255, 255, 0.96);
      border: 1px solid var(--border);
      border-radius: 8px;
      box-shadow: var(--shadow);
      padding: 10px 12px;
      font-size: 13px;
    }

    .tooltip strong {
      display: block;
      margin-bottom: 6px;
    }

    .tooltip-row {
      display: flex;
      justify-content: space-between;
      gap: 20px;
      color: var(--muted);
    }

    .tooltip-row span:last-child {
      color: var(--text);
      font-variant-numeric: tabular-nums;
    }

    @media (max-width: 760px) {
      main {
        width: min(100vw - 20px, 1180px);
        padding-top: 20px;
      }

      header {
        display: block;
      }

      .badge {
        margin-top: 12px;
      }

      .metrics {
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }

      .panel-title {
        display: block;
      }

      .legend {
        justify-content: flex-start;
        margin-top: 8px;
      }

      .metric-value {
        font-size: 20px;
      }
    }
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1 id="title"></h1>
        <p class="subtitle" id="subtitle"></p>
      </div>
      <div class="badge" id="rangeBadge"></div>
    </header>

    <section class="metrics" id="metrics"></section>

    <section class="chart-panel">
      <div class="panel-title">
        <h2>价格、均线与交易信号</h2>
        <div class="legend">
          <span class="legend-item" style="color: var(--close)"><span class="legend-swatch"></span>收盘价</span>
          <span class="legend-item" style="color: var(--fast)"><span class="legend-swatch"></span>快均线</span>
          <span class="legend-item" style="color: var(--slow)"><span class="legend-swatch"></span>慢均线</span>
          <span class="legend-item" style="color: var(--buy)">▲ 买入信号</span>
          <span class="legend-item" style="color: var(--sell)">▼ 卖出信号</span>
        </div>
      </div>
      <svg id="priceChart" viewBox="0 0 1000 360" role="img" aria-label="价格、均线与交易信号图"></svg>
    </section>

    <section class="chart-panel">
      <div class="panel-title">
        <h2>权益曲线</h2>
        <div class="legend">
          <span class="legend-item" style="color: var(--equity)"><span class="legend-swatch"></span>账户权益</span>
          <span class="legend-item" style="color: var(--buy)">浅绿色区间表示持仓</span>
        </div>
      </div>
      <svg id="equityChart" viewBox="0 0 1000 300" role="img" aria-label="账户权益曲线图"></svg>
    </section>

    <p class="note">样例数据是合成 ETF 日线数据，只用于验证数据契约、策略逻辑和可视化链路，不代表真实市场表现。</p>
  </main>

  <div class="tooltip" id="tooltip"></div>

  <script id="chart-data" type="application/json">
__CHART_DATA__
  </script>
  <script>
    const payload = JSON.parse(document.getElementById("chart-data").textContent);
    const points = payload.points;

    document.getElementById("title").textContent = payload.meta.title;
    document.getElementById("subtitle").textContent = `${payload.meta.subtitle} · ${payload.meta.symbol} · MA(${payload.meta.fast_window}) / MA(${payload.meta.slow_window})`;
    document.getElementById("rangeBadge").textContent = `${payload.meta.start} 到 ${payload.meta.end} · ${payload.meta.rows} 行`;

    const metrics = [
      ["期末权益", money(payload.metrics.final_equity)],
      ["总收益", percent(payload.metrics.total_return)],
      ["最大回撤", percent(payload.metrics.max_drawdown)],
      ["夏普", optionalNumber(payload.metrics.sharpe)],
      ["年化收益", percent(payload.metrics.annualized_return)],
      ["交易事件", String(payload.metrics.trade_events)],
      ["完成交易", String(payload.metrics.completed_trades)],
      ["胜率", optionalPercent(payload.metrics.win_rate)],
    ];

    document.getElementById("metrics").innerHTML = metrics.map(([label, value]) => `
      <article class="metric">
        <div class="metric-label">${label}</div>
        <div class="metric-value">${value}</div>
      </article>
    `).join("");

    drawPriceChart();
    drawEquityChart();

    function drawPriceChart() {
      const svg = document.getElementById("priceChart");
      const series = [
        { key: "close", color: cssVar("--close"), label: "收盘价" },
        { key: "fast_ma", color: cssVar("--fast"), label: "快均线" },
        { key: "slow_ma", color: cssVar("--slow"), label: "慢均线" },
      ];
      const chart = makeChart(svg, points, series, { height: 360, formatter: number });
      drawLongZones(svg, chart);
      series.forEach((item) => drawLine(svg, chart, item));
      drawSignalMarkers(svg, chart);
      bindTooltip(svg, chart, "price");
    }

    function drawEquityChart() {
      const svg = document.getElementById("equityChart");
      const series = [{ key: "equity", color: cssVar("--equity"), label: "权益" }];
      const chart = makeChart(svg, points, series, { height: 300, formatter: money });
      drawLongZones(svg, chart);
      drawLine(svg, chart, series[0]);
      bindTooltip(svg, chart, "equity");
    }

    function makeChart(svg, data, series, options) {
      svg.innerHTML = "";
      const width = 1000;
      const height = options.height;
      const margin = { top: 24, right: 28, bottom: 44, left: 70 };
      const plot = {
        x: margin.left,
        y: margin.top,
        width: width - margin.left - margin.right,
        height: height - margin.top - margin.bottom,
      };
      const values = [];
      data.forEach((point) => {
        series.forEach((item) => {
          if (point[item.key] !== null && point[item.key] !== undefined) {
            values.push(point[item.key]);
          }
        });
      });
      let minValue = Math.min(...values);
      let maxValue = Math.max(...values);
      const padding = (maxValue - minValue || maxValue || 1) * 0.08;
      minValue -= padding;
      maxValue += padding;
      const xScale = (index) => plot.x + (index / Math.max(data.length - 1, 1)) * plot.width;
      const yScale = (value) => plot.y + plot.height - ((value - minValue) / (maxValue - minValue)) * plot.height;

      for (let tick = 0; tick <= 4; tick += 1) {
        const y = plot.y + (plot.height / 4) * tick;
        const value = maxValue - ((maxValue - minValue) / 4) * tick;
        add(svg, "line", { class: "grid-line", x1: plot.x, y1: y, x2: plot.x + plot.width, y2: y });
        add(svg, "text", { class: "axis-label", x: 12, y: y + 4 }, options.formatter(value));
      }

      const xTicks = [0, Math.floor((data.length - 1) / 2), data.length - 1];
      xTicks.forEach((index) => {
        add(svg, "text", { class: "axis-label", x: xScale(index), y: height - 12, "text-anchor": "middle" }, data[index].date);
      });

      add(svg, "line", { class: "axis-line", x1: plot.x, y1: plot.y, x2: plot.x, y2: plot.y + plot.height });
      add(svg, "line", { class: "axis-line", x1: plot.x, y1: plot.y + plot.height, x2: plot.x + plot.width, y2: plot.y + plot.height });

      return { data, plot, xScale, yScale, minValue, maxValue };
    }

    function drawLine(svg, chart, series) {
      let path = "";
      let started = false;
      chart.data.forEach((point, index) => {
        const value = point[series.key];
        if (value === null || value === undefined) {
          started = false;
          return;
        }
        path += `${started ? "L" : "M"} ${chart.xScale(index).toFixed(2)} ${chart.yScale(value).toFixed(2)} `;
        started = true;
      });
      add(svg, "path", { class: "line", d: path.trim(), stroke: series.color });
    }

    function drawLongZones(svg, chart) {
      let start = null;
      chart.data.forEach((point, index) => {
        const isLong = point.signal === 1;
        if (isLong && start === null) {
          start = index;
        }
        if ((!isLong || index === chart.data.length - 1) && start !== null) {
          const end = isLong && index === chart.data.length - 1 ? index : index - 1;
          const x = chart.xScale(start);
          const width = Math.max(4, chart.xScale(end) - x);
          add(svg, "rect", { class: "long-zone", x, y: chart.plot.y, width, height: chart.plot.height });
          start = null;
        }
      });
    }

    function drawSignalMarkers(svg, chart) {
      for (let index = 1; index < chart.data.length; index += 1) {
        const previous = chart.data[index - 1].signal;
        const current = chart.data[index].signal;
        if (previous === current) {
          continue;
        }
        const point = chart.data[index];
        const x = chart.xScale(index);
        const y = chart.yScale(point.close);
        if (previous === 0 && current === 1) {
          add(svg, "path", { d: `M ${x} ${y - 12} L ${x - 8} ${y + 6} L ${x + 8} ${y + 6} Z`, fill: cssVar("--buy") });
        } else {
          add(svg, "path", { d: `M ${x} ${y + 12} L ${x - 8} ${y - 6} L ${x + 8} ${y - 6} Z`, fill: cssVar("--sell") });
        }
      }
    }

    function bindTooltip(svg, chart, mode) {
      const tooltip = document.getElementById("tooltip");
      const hover = add(svg, "rect", {
        x: chart.plot.x,
        y: chart.plot.y,
        width: chart.plot.width,
        height: chart.plot.height,
        fill: "transparent",
      });

      hover.addEventListener("mousemove", (event) => {
        const rect = svg.getBoundingClientRect();
        const scaleX = 1000 / rect.width;
        const svgX = (event.clientX - rect.left) * scaleX;
        const ratio = Math.min(1, Math.max(0, (svgX - chart.plot.x) / chart.plot.width));
        const index = Math.round(ratio * (chart.data.length - 1));
        const point = chart.data[index];
        tooltip.style.display = "block";
        tooltip.style.left = `${Math.min(window.innerWidth - 220, event.clientX + 16)}px`;
        tooltip.style.top = `${event.clientY + 16}px`;
        tooltip.innerHTML = mode === "price" ? priceTooltip(point) : equityTooltip(point);
      });
      hover.addEventListener("mouseleave", () => {
        tooltip.style.display = "none";
      });
    }

    function priceTooltip(point) {
      return `
        <strong>${point.date}</strong>
        <div class="tooltip-row"><span>收盘价</span><span>${number(point.close)}</span></div>
        <div class="tooltip-row"><span>快均线</span><span>${optionalNumber(point.fast_ma)}</span></div>
        <div class="tooltip-row"><span>慢均线</span><span>${optionalNumber(point.slow_ma)}</span></div>
        <div class="tooltip-row"><span>状态</span><span>${point.signal === 1 ? "持仓" : "空仓"}</span></div>
      `;
    }

    function equityTooltip(point) {
      return `
        <strong>${point.date}</strong>
        <div class="tooltip-row"><span>账户权益</span><span>${money(point.equity)}</span></div>
        <div class="tooltip-row"><span>状态</span><span>${point.signal === 1 ? "持仓" : "空仓"}</span></div>
      `;
    }

    function add(svg, tag, attrs, text) {
      const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
      Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, value));
      if (text !== undefined) {
        node.textContent = text;
      }
      svg.appendChild(node);
      return node;
    }

    function cssVar(name) {
      return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    }

    function money(value) {
      return `$${Number(value).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
    }

    function percent(value) {
      return `${(Number(value) * 100).toFixed(2)}%`;
    }

    function optionalPercent(value) {
      return value === null || value === undefined ? "n/a" : percent(value);
    }

    function number(value) {
      return Number(value).toLocaleString("en-US", { maximumFractionDigits: 2 });
    }

    function optionalNumber(value) {
      return value === null || value === undefined ? "n/a" : number(value);
    }
  </script>
</body>
</html>
"""


if __name__ == "__main__":
    raise SystemExit(main())

