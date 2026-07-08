"""FastAPI page for browsing Tushare A-share bars."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse

from market_regime_alpha.data_sources.tushare_client import (
    TushareConfigError,
    TushareDataError,
    build_tushare_client,
    dataframe_records,
)


PAGE_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Tushare A股行情查询</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f6f7f9;
      --panel: #ffffff;
      --text: #20242a;
      --muted: #68707c;
      --line: #d8dde5;
      --accent: #1f6feb;
      --danger: #c62828;
      --up: #c62828;
      --down: #15803d;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    header {
      padding: 22px 28px 16px;
      border-bottom: 1px solid var(--line);
      background: var(--panel);
    }
    h1 { margin: 0 0 8px; font-size: 24px; }
    p { margin: 0; color: var(--muted); line-height: 1.5; }
    main { max-width: 1280px; margin: 0 auto; padding: 20px; }
    section {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 16px;
      margin-bottom: 16px;
    }
    h2 { margin: 0 0 12px; font-size: 18px; }
    .grid {
      display: grid;
      grid-template-columns: repeat(6, minmax(130px, 1fr));
      gap: 12px;
      align-items: end;
    }
    label { display: grid; gap: 6px; font-size: 13px; color: var(--muted); }
    input, select, button {
      min-height: 38px;
      border-radius: 6px;
      border: 1px solid var(--line);
      padding: 8px 10px;
      font: inherit;
      background: #fff;
      color: var(--text);
    }
    button {
      border-color: var(--accent);
      background: var(--accent);
      color: #fff;
      cursor: pointer;
      font-weight: 600;
    }
    button.secondary {
      color: var(--accent);
      background: #fff;
    }
    .results {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 12px;
    }
    .pill {
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 6px 10px;
      background: #fff;
      color: var(--text);
      cursor: pointer;
    }
    .status {
      margin: 10px 0 0;
      color: var(--muted);
      min-height: 20px;
    }
    .error { color: var(--danger); }
    canvas {
      width: 100%;
      height: 280px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
      margin: 12px 0;
    }
    .table-wrap {
      overflow: auto;
      border: 1px solid var(--line);
      border-radius: 8px;
      max-height: 420px;
      background: #fff;
    }
    table { width: 100%; border-collapse: collapse; font-size: 13px; }
    th, td {
      border-bottom: 1px solid var(--line);
      padding: 8px 10px;
      text-align: right;
      white-space: nowrap;
    }
    th:first-child, td:first-child,
    th:nth-child(2), td:nth-child(2) { text-align: left; }
    th {
      position: sticky;
      top: 0;
      background: #f9fafb;
      z-index: 1;
    }
    @media (max-width: 860px) {
      header { padding: 18px; }
      main { padding: 12px; }
      .grid { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <header>
    <h1>Tushare A股行情查询</h1>
    <p>服务端读取 TUSHARE_TOKEN，支持按股票代码或名称搜索，并查询日线、1/5/15/30/60 分钟线。</p>
  </header>
  <main>
    <section>
      <h2>股票搜索</h2>
      <div class="grid">
        <label style="grid-column: span 3;">代码或名称
          <input id="keyword" placeholder="例如 600000.SH、000001、平安银行">
        </label>
        <button id="searchBtn">搜索股票</button>
        <button class="secondary" id="clearBtn">清空</button>
      </div>
      <div id="stockStatus" class="status"></div>
      <div id="stockResults" class="results"></div>
    </section>

    <section>
      <h2>日线</h2>
      <div class="grid">
        <label>股票代码
          <input id="dailySymbol" placeholder="600000.SH">
        </label>
        <label>开始日期
          <input id="dailyStart" type="date">
        </label>
        <label>结束日期
          <input id="dailyEnd" type="date">
        </label>
        <label>显示行数
          <input id="dailyLimit" type="number" min="1" max="2000" value="300">
        </label>
        <button id="dailyBtn">查询日线</button>
      </div>
      <div id="dailyStatus" class="status"></div>
      <canvas id="dailyChart"></canvas>
      <div id="dailyTable" class="table-wrap"></div>
    </section>

    <section>
      <h2>分钟线</h2>
      <div class="grid">
        <label>股票代码
          <input id="minuteSymbol" placeholder="600000.SH">
        </label>
        <label>频率
          <select id="minuteFreq">
            <option value="1min">1min</option>
            <option value="5min">5min</option>
            <option value="15min">15min</option>
            <option value="30min">30min</option>
            <option value="60min">60min</option>
          </select>
        </label>
        <label>开始时间
          <input id="minuteStart" type="datetime-local">
        </label>
        <label>结束时间
          <input id="minuteEnd" type="datetime-local">
        </label>
        <label>显示行数
          <input id="minuteLimit" type="number" min="1" max="2000" value="500">
        </label>
        <button id="minuteBtn">查询分钟线</button>
      </div>
      <div id="minuteStatus" class="status"></div>
      <canvas id="minuteChart"></canvas>
      <div id="minuteTable" class="table-wrap"></div>
    </section>
  </main>
  <script>
    const columns = ["symbol", "timestamp", "open", "high", "low", "close", "volume", "amount", "source_freq"];

    function $(id) { return document.getElementById(id); }

    function dateValue(daysBack) {
      const date = new Date();
      date.setDate(date.getDate() - daysBack);
      return date.toISOString().slice(0, 10);
    }

    function minuteValue(date, time) {
      return `${date}T${time}`;
    }

    $("dailyStart").value = dateValue(120);
    $("dailyEnd").value = dateValue(0);
    $("minuteStart").value = minuteValue(dateValue(5), "09:00");
    $("minuteEnd").value = minuteValue(dateValue(0), "15:30");

    function toDailyDate(value) {
      return value ? value.replaceAll("-", "") : "";
    }

    function toMinuteDatetime(value) {
      return value ? value.replace("T", " ") + (value.length === 16 ? ":00" : "") : "";
    }

    async function fetchJson(url) {
      const response = await fetch(url);
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || `HTTP ${response.status}`);
      }
      return data;
    }

    function setStatus(id, text, isError = false) {
      const node = $(id);
      node.textContent = text;
      node.className = isError ? "status error" : "status";
    }

    function pickSymbol(symbol) {
      $("dailySymbol").value = symbol;
      $("minuteSymbol").value = symbol;
    }

    function renderStocks(records) {
      const box = $("stockResults");
      box.innerHTML = "";
      records.forEach((row) => {
        const item = document.createElement("button");
        item.className = "pill";
        item.type = "button";
        item.textContent = `${row.ts_code} ${row.name || ""} ${row.industry || ""}`;
        item.addEventListener("click", () => pickSymbol(row.ts_code));
        box.appendChild(item);
      });
    }

    function renderTable(id, records) {
      const box = $(id);
      if (!records.length) {
        box.innerHTML = "<table><tbody><tr><td>没有数据</td></tr></tbody></table>";
        return;
      }
      const html = [
        "<table><thead><tr>",
        ...columns.map((column) => `<th>${column}</th>`),
        "</tr></thead><tbody>",
        ...records.map((row) => "<tr>" + columns.map((column) => `<td>${formatCell(row[column])}</td>`).join("") + "</tr>"),
        "</tbody></table>"
      ].join("");
      box.innerHTML = html;
    }

    function formatCell(value) {
      if (value === null || value === undefined) return "";
      if (typeof value === "number") return Number.isInteger(value) ? String(value) : value.toFixed(4);
      return String(value);
    }

    function drawCandles(canvasId, records) {
      const canvas = $(canvasId);
      const ratio = window.devicePixelRatio || 1;
      const width = canvas.clientWidth;
      const height = canvas.clientHeight;
      canvas.width = Math.floor(width * ratio);
      canvas.height = Math.floor(height * ratio);
      const ctx = canvas.getContext("2d");
      ctx.scale(ratio, ratio);
      ctx.clearRect(0, 0, width, height);

      const rows = records.slice(-160).filter((row) => row.high !== null && row.low !== null);
      if (!rows.length) {
        ctx.fillStyle = "#68707c";
        ctx.fillText("没有可绘制的数据", 18, 28);
        return;
      }

      const padding = { top: 18, right: 60, bottom: 24, left: 12 };
      const plotWidth = width - padding.left - padding.right;
      const plotHeight = height - padding.top - padding.bottom;
      const high = Math.max(...rows.map((row) => Number(row.high)));
      const low = Math.min(...rows.map((row) => Number(row.low)));
      const span = high - low || 1;
      const xStep = plotWidth / rows.length;
      const bodyWidth = Math.max(2, Math.min(9, xStep * 0.62));
      const y = (price) => padding.top + (high - price) / span * plotHeight;

      ctx.strokeStyle = "#e5e7eb";
      ctx.lineWidth = 1;
      for (let i = 0; i <= 4; i += 1) {
        const yy = padding.top + plotHeight * i / 4;
        ctx.beginPath();
        ctx.moveTo(padding.left, yy);
        ctx.lineTo(width - padding.right, yy);
        ctx.stroke();
      }

      rows.forEach((row, index) => {
        const open = Number(row.open);
        const close = Number(row.close);
        const candleHigh = Number(row.high);
        const candleLow = Number(row.low);
        const x = padding.left + index * xStep + xStep / 2;
        const color = close >= open ? "#c62828" : "#15803d";
        ctx.strokeStyle = color;
        ctx.fillStyle = color;
        ctx.beginPath();
        ctx.moveTo(x, y(candleHigh));
        ctx.lineTo(x, y(candleLow));
        ctx.stroke();
        const top = Math.min(y(open), y(close));
        const bodyHeight = Math.max(1, Math.abs(y(open) - y(close)));
        ctx.fillRect(x - bodyWidth / 2, top, bodyWidth, bodyHeight);
      });

      ctx.fillStyle = "#68707c";
      ctx.font = "12px -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif";
      ctx.fillText(high.toFixed(2), width - padding.right + 8, padding.top + 4);
      ctx.fillText(low.toFixed(2), width - padding.right + 8, padding.top + plotHeight);
      ctx.fillText(rows[0].timestamp, padding.left, height - 6);
      ctx.fillText(rows[rows.length - 1].timestamp, Math.max(padding.left, width - 210), height - 6);
    }

    $("searchBtn").addEventListener("click", async () => {
      const keyword = $("keyword").value.trim();
      if (!keyword) return setStatus("stockStatus", "请输入股票代码或名称。", true);
      setStatus("stockStatus", "搜索中...");
      try {
        const data = await fetchJson(`/api/stocks?keyword=${encodeURIComponent(keyword)}`);
        renderStocks(data.records);
        setStatus("stockStatus", `找到 ${data.records.length} 个结果。点击结果会填入查询框。`);
      } catch (error) {
        setStatus("stockStatus", error.message, true);
      }
    });

    $("clearBtn").addEventListener("click", () => {
      $("keyword").value = "";
      $("stockResults").innerHTML = "";
      setStatus("stockStatus", "");
    });

    $("dailyBtn").addEventListener("click", async () => {
      const symbol = $("dailySymbol").value.trim();
      if (!symbol) return setStatus("dailyStatus", "请先选择或输入股票代码。", true);
      const params = new URLSearchParams({
        kind: "daily",
        symbol,
        start: toDailyDate($("dailyStart").value),
        end: toDailyDate($("dailyEnd").value),
        limit: $("dailyLimit").value || "300"
      });
      setStatus("dailyStatus", "读取日线中...");
      try {
        const data = await fetchJson(`/api/bars?${params.toString()}`);
        renderTable("dailyTable", data.records);
        drawCandles("dailyChart", data.records);
        setStatus("dailyStatus", `${data.symbol} 日线 ${data.rows} 行，页面显示 ${data.records.length} 行。`);
      } catch (error) {
        setStatus("dailyStatus", error.message, true);
      }
    });

    $("minuteBtn").addEventListener("click", async () => {
      const symbol = $("minuteSymbol").value.trim();
      if (!symbol) return setStatus("minuteStatus", "请先选择或输入股票代码。", true);
      const params = new URLSearchParams({
        kind: "minute",
        symbol,
        freq: $("minuteFreq").value,
        start: toMinuteDatetime($("minuteStart").value),
        end: toMinuteDatetime($("minuteEnd").value),
        limit: $("minuteLimit").value || "500"
      });
      setStatus("minuteStatus", "读取分钟线中...");
      try {
        const data = await fetchJson(`/api/bars?${params.toString()}`);
        renderTable("minuteTable", data.records);
        drawCandles("minuteChart", data.records);
        setStatus("minuteStatus", `${data.symbol} ${data.freq} 分钟线 ${data.rows} 行，页面显示 ${data.records.length} 行。`);
      } catch (error) {
        setStatus("minuteStatus", error.message, true);
      }
    });

    window.addEventListener("resize", () => {
      const dailyRows = $("dailyTable").querySelectorAll("tbody tr").length ? collectRows("dailyTable") : [];
      const minuteRows = $("minuteTable").querySelectorAll("tbody tr").length ? collectRows("minuteTable") : [];
      drawCandles("dailyChart", dailyRows);
      drawCandles("minuteChart", minuteRows);
    });

    function collectRows(tableId) {
      const rows = [];
      $(tableId).querySelectorAll("tbody tr").forEach((tr) => {
        const cells = [...tr.children].map((td) => td.textContent);
        if (cells.length === columns.length) {
          const row = {};
          columns.forEach((column, index) => {
            const value = cells[index];
            row[column] = ["open", "high", "low", "close", "volume", "amount"].includes(column) ? Number(value) : value;
          });
          rows.push(row);
        }
      });
      return rows;
    }
  </script>
</body>
</html>
"""


def create_app() -> FastAPI:
    app = FastAPI(title="quant-learning Tushare Browser")

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return PAGE_HTML

    @app.get("/api/stocks")
    def stocks(
        keyword: str = Query(..., min_length=1),
        limit: int = Query(20, ge=1, le=100),
    ) -> dict[str, object]:
        try:
            frame = _client().search_stocks(keyword, limit=limit)
        except (TushareConfigError, TushareDataError, ValueError) as exc:
            _raise_http(exc)
        return {"records": dataframe_records(frame)}

    @app.get("/api/bars")
    def bars(
        kind: Literal["daily", "minute"],
        symbol: str = Query(..., min_length=1),
        start: str | None = None,
        end: str | None = None,
        freq: str = "1min",
        limit: int = Query(500, ge=1, le=2000),
        use_cache: bool = True,
    ) -> dict[str, object]:
        try:
            if kind == "daily":
                frame = _client().daily_bars(symbol, start_date=start, end_date=end, use_cache=use_cache)
                normalized_freq = "daily"
            else:
                frame = _client().minute_bars(
                    symbol,
                    freq=freq,
                    start_date=start,
                    end_date=end,
                    use_cache=use_cache,
                )
                normalized_freq = frame["source_freq"].iloc[0] if not frame.empty else freq
        except (TushareConfigError, TushareDataError, ValueError) as exc:
            _raise_http(exc)

        records = dataframe_records(frame, limit=limit)
        return {
            "kind": kind,
            "symbol": records[0]["symbol"] if records else symbol,
            "freq": normalized_freq,
            "rows": int(len(frame)),
            "records": records,
        }

    return app


@lru_cache(maxsize=1)
def _client():
    return build_tushare_client()


def _raise_http(exc: Exception) -> None:
    if isinstance(exc, TushareConfigError):
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if isinstance(exc, TushareDataError):
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    raise HTTPException(status_code=400, detail=str(exc)) from exc


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("market_regime_alpha.web.tushare_app:app", host="127.0.0.1", port=8000, reload=True)

