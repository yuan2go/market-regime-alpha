"""FastAPI dashboard for the long-term dividend T-trading model."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from market_regime_alpha.data_sources.a_share_bars import AShareDataError, TencentMinuteProvider, fetch_tencent_latest_quotes, provider_options
from market_regime_alpha.dividend_t.brokers import PaperBrokerAdapter, PTradeAdapter, QMTAdapter
from market_regime_alpha.dividend_t.cosco_timing import get_cosco_timing_from_free_sources, sample_cosco_timing
from market_regime_alpha.dividend_t.indicators import estimate_levels, infer_technical_inputs
from market_regime_alpha.dividend_t.models import FundamentalInputs, PositionState, RetreatInputs, TechnicalInputs, TrendState
from market_regime_alpha.dividend_t.risk import RiskEngine
from market_regime_alpha.dividend_t.scoring import clamp
from market_regime_alpha.dividend_t.storage import load_watchlist
from market_regime_alpha.dividend_t.strategy import DividendTStrategy


class FundamentalPayload(BaseModel):
    dividend_sustainability: float = Field(75, ge=0, le=100)
    valuation_margin: float = Field(70, ge=0, le=100)
    cycle_prosperity: float = Field(70, ge=0, le=100)
    financial_quality: float = Field(75, ge=0, le=100)
    catalyst_stability: float = Field(65, ge=0, le=100)


class RetreatPayload(BaseModel):
    market_attention: float = Field(3.5, ge=0, le=5)
    upside_certainty: float = Field(3.5, ge=0, le=5)
    risk_reward_ratio: float = Field(2.1, ge=0)
    sell_pressure: float = Field(2.5, ge=0, le=5)


class TechnicalPayload(BaseModel):
    position_quality: float = Field(80, ge=0, le=100)
    volume_structure: float = Field(75, ge=0, le=100)
    trend_quality: float = Field(75, ge=0, le=100)
    intraday_support: float = Field(75, ge=0, le=100)
    chan_score: float = Field(65, ge=0, le=100)
    trend_state: TrendState = TrendState.RANGE
    near_support: bool = True
    near_resistance: bool = False
    shrinking_pullback: bool = True
    volume_stalling: bool = False
    intraday_reversal: bool = True
    sector_healthy: bool = True
    chan_structure_type: str = "unknown"
    chan_trend_direction: str = "range"
    chan_divergence_type: str = "none"
    chan_buy_point_type: str = "none"
    chan_sell_point_type: str = "none"
    chan_pivot_low: float | None = None
    chan_pivot_high: float | None = None
    chan_invalid_price: float | None = None


class PositionPayload(BaseModel):
    symbol_position_pct: float = Field(0.12, ge=0, le=1)
    base_position_pct: float = Field(0.10, ge=0, le=1)
    t_position_pct: float = Field(0.02, ge=0, le=1)
    cash_pct: float = Field(0.40, ge=0, le=1)
    available_cash_pct: float = Field(0.40, ge=0, le=1)
    available_sell_pct: float = Field(0.10, ge=0, le=1)
    is_cycle_stock: bool = True
    consecutive_t_failures: int = Field(0, ge=0)


class EvaluatePayload(BaseModel):
    symbol: str = "601919.SH"
    fundamental: FundamentalPayload = Field(default_factory=FundamentalPayload)
    retreat: RetreatPayload = Field(default_factory=RetreatPayload)
    technical: TechnicalPayload = Field(default_factory=TechnicalPayload)
    position: PositionPayload = Field(default_factory=PositionPayload)


app = FastAPI(title="A-share Buy/Sell Point Identification Model", version="0.1.0")
strategy = DividendTStrategy()
risk_engine = RiskEngine()
paper_broker = PaperBrokerAdapter()
qmt_adapter = QMTAdapter()
ptrade_adapter = PTradeAdapter()

SIGNAL_LABELS = {
    "BUILD_BASE": "建底仓",
    "HOLD": "持有观察",
    "BUY_T": "买点",
    "SELL_T": "卖点",
    "SELL_REVERSE_T": "高位卖点",
    "BUY_BACK_REVERSE_T": "回补买点",
    "STOP_T": "风险卖点",
    "REDUCE": "减底仓",
    "CLEAR": "清仓",
}


@app.get("/", response_class=HTMLResponse)
def page() -> str:
    return PAGE_HTML


@app.get("/api/health")
def health() -> dict[str, object]:
    return {
        "status": "ok",
        "platform": "buy-sell-point-identification",
        "brokers": [paper_broker.status(), qmt_adapter.status(), ptrade_adapter.status()],
    }


@app.get("/api/watchlist")
def watchlist() -> list[dict[str, object]]:
    return [asdict(item) for item in load_watchlist()]


@app.get("/api/sample-decisions")
def sample_decisions() -> list[dict[str, object]]:
    items = load_watchlist()[:12]
    if not items:
        items = []
    try:
        quotes = fetch_tencent_latest_quotes(item.symbol for item in items)
    except AShareDataError:
        quotes = {}
    with ThreadPoolExecutor(max_workers=4) as executor:
        scans = list(
            executor.map(
                lambda indexed_item: _watchlist_payload(
                    indexed_item[1].symbol,
                    indexed_item[1].is_cycle_stock,
                    index=indexed_item[0],
                    minute_provider=TencentMinuteProvider(timeout_seconds=4.0),
                ),
                enumerate(items),
            )
        )

    output: list[dict[str, object]] = []
    for item, (payload, scan_meta) in zip(items, scans):
        result = _evaluate_payload(payload)
        result["name"] = item.name
        result["industry"] = item.industry
        quote = quotes.get(item.symbol)
        result["latest_price"] = quote.current_price if quote else None
        result["latest_price_time"] = quote.quote_time if quote else None
        result["latest_price_source"] = quote.source if quote else None
        result.update(scan_meta)
        output.append(result)
    return output


@app.get("/api/cosco-timing")
def cosco_timing(provider: str = "fast") -> dict[str, object]:
    result = get_cosco_timing_from_free_sources(provider=provider, persist=True)
    return result.to_dict()


@app.get("/api/cosco-timing/sample")
def cosco_timing_sample() -> dict[str, object]:
    return sample_cosco_timing().to_dict()


@app.get("/api/data-sources")
def data_sources() -> list[dict[str, str]]:
    return provider_options()


@app.post("/api/evaluate")
def evaluate(payload: EvaluatePayload) -> dict[str, object]:
    return _evaluate_payload(payload)


def _evaluate_payload(payload: EvaluatePayload) -> dict[str, object]:
    decision = strategy.evaluate(
        symbol=payload.symbol.strip().upper(),
        fundamental=FundamentalInputs(**payload.fundamental.model_dump()),
        retreat=RetreatInputs(**payload.retreat.model_dump()),
        technical=TechnicalInputs(**payload.technical.model_dump()),
        position=PositionState(**payload.position.model_dump()),
    )
    position = PositionState(**payload.position.model_dump())
    risk = risk_engine.validate_order(
        decision.order_intent,
        position=position,
        base_position_limit_pct=decision.base_position_limit_pct,
    )
    result = asdict(decision)
    result["signal"] = decision.signal.value
    result["signal_label"] = SIGNAL_LABELS.get(decision.signal.value, decision.signal.value)
    result["risk_check"] = asdict(risk)
    if result.get("order_intent"):
        order_signal = result["order_intent"].get("signal")
        if hasattr(order_signal, "value"):
            order_signal = order_signal.value
        result["order_intent"]["signal"] = order_signal
        result["order_intent"]["signal_label"] = SIGNAL_LABELS.get(str(order_signal), str(order_signal))
    return result


def _watchlist_payload(
    symbol: str,
    is_cycle_stock: bool,
    *,
    index: int,
    minute_provider: TencentMinuteProvider,
) -> tuple[EvaluatePayload, dict[str, object]]:
    try:
        bars = minute_provider.minute_bars(symbol)
        if len(bars) < 30:
            raise ValueError(f"腾讯分时 5 分钟 K 线只有 {len(bars)} 根，至少需要 30 根")
        technical = infer_technical_inputs(bars)
        retreat = _retreat_from_bars(bars, technical)
        return (
            EvaluatePayload(
                symbol=symbol,
                retreat=RetreatPayload(
                    market_attention=retreat.market_attention,
                    upside_certainty=retreat.upside_certainty,
                    risk_reward_ratio=retreat.risk_reward_ratio,
                    sell_pressure=retreat.sell_pressure,
                ),
                technical=TechnicalPayload(
                    position_quality=technical.position_quality,
                    volume_structure=technical.volume_structure,
                    trend_quality=technical.trend_quality,
                    intraday_support=technical.intraday_support,
                    chan_score=technical.chan_score,
                    trend_state=technical.trend_state,
                    near_support=technical.near_support,
                    near_resistance=technical.near_resistance,
                    shrinking_pullback=technical.shrinking_pullback,
                    volume_stalling=technical.volume_stalling,
                    intraday_reversal=technical.intraday_reversal,
                    sector_healthy=technical.sector_healthy,
                    chan_structure_type=technical.chan_structure_type,
                    chan_trend_direction=technical.chan_trend_direction,
                    chan_divergence_type=technical.chan_divergence_type,
                    chan_buy_point_type=technical.chan_buy_point_type,
                    chan_sell_point_type=technical.chan_sell_point_type,
                    chan_pivot_low=technical.chan_pivot_low,
                    chan_pivot_high=technical.chan_pivot_high,
                    chan_invalid_price=technical.chan_invalid_price,
                ),
                position=PositionPayload(is_cycle_stock=is_cycle_stock),
            ),
            {
                "scan_status": "real_tencent_intraday",
                "scan_message": "使用腾讯分时聚合 5 分钟 K 线生成模型输入。",
                "bar_count": len(bars),
                "bar_time": str(bars.iloc[-1]["timestamp"]),
            },
        )
    except Exception as exc:  # noqa: BLE001
        return _fallback_watchlist_payload(symbol, is_cycle_stock, index=index), {
            "scan_status": "fallback_static",
            "scan_message": f"真实分时扫描不可用，使用静态样例评分：{exc}",
            "bar_count": 0,
            "bar_time": None,
        }


def _fallback_watchlist_payload(symbol: str, is_cycle_stock: bool, *, index: int) -> EvaluatePayload:
    return EvaluatePayload(
        symbol=symbol,
        retreat=RetreatPayload(
            market_attention=3.3 + (index % 3) * 0.3,
            upside_certainty=3.4,
            risk_reward_ratio=2.2 if index % 4 != 0 else 1.2,
            sell_pressure=2.4 if index % 4 != 0 else 4.2,
        ),
        technical=TechnicalPayload(
            near_support=index % 4 != 0,
            near_resistance=index % 4 == 0,
            shrinking_pullback=index % 4 != 0,
            volume_stalling=index % 4 == 0,
            trend_state=TrendState.RANGE if index % 5 != 0 else TrendState.UPTREND,
        ),
        position=PositionPayload(is_cycle_stock=is_cycle_stock),
    )


def _retreat_from_bars(bars: object, technical: TechnicalInputs) -> RetreatPayload:
    data = bars.copy()
    levels = estimate_levels(data, support_window=min(20, len(data)), resistance_window=min(48, len(data)))
    latest = data.iloc[-1]
    previous = data.iloc[-2]
    volume_tail = data["volume"].tail(min(20, len(data)))
    volume_base = max(float(volume_tail.mean()), 1.0)
    volume_ratio = float(latest["volume"]) / volume_base
    close = float(latest["close"])
    open_price = float(latest["open"])
    previous_close = float(previous["close"])

    market_attention = clamp(2.8 + min(volume_ratio, 2.5) * 0.55, 0.0, 5.0)
    certainty = 3.0
    if technical.trend_state == TrendState.UPTREND:
        certainty += 0.45
    elif technical.trend_state == TrendState.DOWNTREND:
        certainty -= 0.65
    if close > open_price:
        certainty += 0.20
    if close > previous_close:
        certainty += 0.20
    upside_certainty = clamp(certainty, 0.0, 5.0)

    sell_pressure = 2.4
    if technical.near_resistance:
        sell_pressure += 1.1
    if technical.volume_stalling:
        sell_pressure += 0.8
    if levels.risk_reward_ratio < 1.5:
        sell_pressure += 0.6
    if technical.near_support:
        sell_pressure -= 0.3
    if technical.trend_state == TrendState.DOWNTREND:
        sell_pressure += 0.6

    return RetreatPayload(
        market_attention=round(market_attention, 2),
        upside_certainty=round(upside_certainty, 2),
        risk_reward_ratio=round(levels.risk_reward_ratio, 2),
        sell_pressure=round(clamp(sell_pressure, 0.0, 5.0), 2),
    )


PAGE_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>A股买卖点识别模型</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f5f6f8;
      --panel: #ffffff;
      --text: #20242a;
      --muted: #667085;
      --line: #d9dee7;
      --accent: #155eef;
      --danger: #b42318;
      --warn: #b54708;
      --ok: #027a48;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    header {
      background: var(--panel);
      border-bottom: 1px solid var(--line);
      padding: 18px 24px;
    }
    h1 { margin: 0; font-size: 22px; letter-spacing: 0; }
    main { max-width: 1440px; margin: 0 auto; padding: 18px; }
    section {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px;
      margin-bottom: 14px;
    }
    h2 { margin: 0 0 12px; font-size: 16px; }
    .layout {
      display: grid;
      grid-template-columns: minmax(320px, 420px) 1fr;
      gap: 14px;
      align-items: start;
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(120px, 1fr));
      gap: 10px;
    }
    .wide { grid-column: 1 / -1; }
    label { display: grid; gap: 5px; font-size: 12px; color: var(--muted); }
    input, select, button {
      min-height: 36px;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 7px 9px;
      font: inherit;
      background: #fff;
      color: var(--text);
    }
    input[type="checkbox"] { min-height: auto; width: 18px; height: 18px; }
    .check-row {
      display: grid;
      grid-template-columns: 18px 1fr;
      align-items: center;
      gap: 8px;
      color: var(--text);
    }
    button {
      background: var(--accent);
      border-color: var(--accent);
      color: white;
      cursor: pointer;
      font-weight: 650;
    }
    button.secondary {
      background: white;
      color: var(--accent);
    }
    .toolbar { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 10px; }
    .metrics {
      display: grid;
      grid-template-columns: repeat(5, minmax(110px, 1fr));
      gap: 10px;
      margin-bottom: 12px;
    }
    .metric {
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 10px;
      min-height: 74px;
      background: #fff;
    }
    .metric span { display: block; color: var(--muted); font-size: 12px; }
    .metric strong { display: block; margin-top: 6px; font-size: 24px; }
    .manual {
      display: grid;
      grid-template-columns: repeat(4, minmax(120px, 1fr));
      gap: 10px;
      margin-top: 12px;
    }
    .manual div {
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 10px;
      background: #fff;
    }
    .manual span { display: block; color: var(--muted); font-size: 12px; }
    .manual strong { display: block; margin-top: 6px; font-size: 20px; }
    .signal {
      display: inline-flex;
      align-items: center;
      min-height: 34px;
      border-radius: 6px;
      padding: 6px 10px;
      font-weight: 700;
      background: #eef4ff;
      color: #1849a9;
      border: 1px solid #b2ccff;
    }
    .signal.REDUCE, .signal.STOP_T, .signal.CLEAR { background: #fef3f2; color: var(--danger); border-color: #fecdca; }
    .signal.SELL_T, .signal.SELL_REVERSE_T { background: #fffaeb; color: var(--warn); border-color: #fedf89; }
    .signal.BUY_T, .signal.BUILD_BASE { background: #ecfdf3; color: var(--ok); border-color: #abefc6; }
    table { width: 100%; border-collapse: collapse; font-size: 13px; }
    th, td {
      border-bottom: 1px solid var(--line);
      padding: 8px 9px;
      text-align: right;
      white-space: nowrap;
    }
    th:first-child, td:first-child,
    th:nth-child(2), td:nth-child(2) { text-align: left; }
    th { background: #f9fafb; color: #475467; position: sticky; top: 0; }
    .table-wrap { overflow: auto; max-height: 380px; border: 1px solid var(--line); border-radius: 8px; }
    .list { margin: 8px 0 0; padding-left: 18px; line-height: 1.6; color: #344054; }
    .muted { color: var(--muted); }
    @media (max-width: 920px) {
      main { padding: 10px; }
      .layout { grid-template-columns: 1fr; }
      .metrics { grid-template-columns: repeat(2, minmax(120px, 1fr)); }
    }
  </style>
</head>
<body>
  <header>
    <h1>A 股买卖点识别模型</h1>
  </header>
  <main>
    <div class="layout">
      <section>
        <h2>模型输入</h2>
        <div class="grid">
          <label class="wide">股票代码
            <input id="symbol" value="601919.SH">
          </label>
          <label>分红可持续性
            <input id="dividend_sustainability" type="number" value="78" min="0" max="100">
          </label>
          <label>估值安全边际
            <input id="valuation_margin" type="number" value="72" min="0" max="100">
          </label>
          <label>行业景气度
            <input id="cycle_prosperity" type="number" value="72" min="0" max="100">
          </label>
          <label>财务质量
            <input id="financial_quality" type="number" value="76" min="0" max="100">
          </label>
          <label>催化稳定性
            <input id="catalyst_stability" type="number" value="68" min="0" max="100">
          </label>
          <label>市场关注 G
            <input id="market_attention" type="number" value="3.8" min="0" max="5" step="0.1">
          </label>
          <label>上涨确定性 Z
            <input id="upside_certainty" type="number" value="3.7" min="0" max="5" step="0.1">
          </label>
          <label>盈亏比 K
            <input id="risk_reward_ratio" type="number" value="2.2" min="0" step="0.1">
          </label>
          <label>卖压 S
            <input id="sell_pressure" type="number" value="2.4" min="0" max="5" step="0.1">
          </label>
          <label>位置质量
            <input id="position_quality" type="number" value="82" min="0" max="100">
          </label>
          <label>成交量结构
            <input id="volume_structure" type="number" value="78" min="0" max="100">
          </label>
          <label>趋势质量
            <input id="trend_quality" type="number" value="74" min="0" max="100">
          </label>
          <label>分时承接
            <input id="intraday_support" type="number" value="76" min="0" max="100">
          </label>
          <label>趋势状态
            <select id="trend_state">
              <option>RANGE</option>
              <option>UPTREND</option>
              <option>DOWNTREND</option>
              <option>BREAKOUT</option>
              <option>EXHAUSTION</option>
            </select>
          </label>
          <label>当前总仓位
            <input id="symbol_position_pct" type="number" value="0.12" min="0" max="1" step="0.01">
          </label>
          <label>可用现金
            <input id="available_cash_pct" type="number" value="0.40" min="0" max="1" step="0.01">
          </label>
          <label>可卖仓位
            <input id="available_sell_pct" type="number" value="0.10" min="0" max="1" step="0.01">
          </label>
          <label>连续 T 失败
            <input id="consecutive_t_failures" type="number" value="0" min="0">
          </label>
          <label class="check-row wide"><input id="near_support" type="checkbox" checked>接近支撑</label>
          <label class="check-row wide"><input id="near_resistance" type="checkbox">接近压力</label>
          <label class="check-row wide"><input id="shrinking_pullback" type="checkbox" checked>缩量回踩</label>
          <label class="check-row wide"><input id="volume_stalling" type="checkbox">放量滞涨</label>
          <label class="check-row wide"><input id="intraday_reversal" type="checkbox" checked>分时承接恢复</label>
          <label class="check-row wide"><input id="sector_healthy" type="checkbox" checked>板块未破位</label>
          <label class="check-row wide"><input id="is_cycle_stock" type="checkbox" checked>周期股仓位约束</label>
        </div>
        <div class="toolbar">
          <button id="evaluateBtn">计算信号</button>
          <button class="secondary" id="loadSamplesBtn">刷新观察池</button>
        </div>
      </section>

      <div>
        <section>
          <h2>中远海控 5 分钟买卖点</h2>
          <div><span id="coscoAction" class="signal">加载中</span></div>
          <div class="manual">
            <div><span>现价</span><strong id="coscoCurrent">-</strong></div>
            <div><span>参考买入</span><strong id="coscoBuy">-</strong></div>
            <div><span>参考卖出</span><strong id="coscoSell">-</strong></div>
            <div><span>止损/失效</span><strong id="coscoStop">-</strong></div>
            <div><span>买卖力比</span><strong id="coscoForce">-</strong></div>
            <div><span>置信分</span><strong id="coscoConfidence">-</strong></div>
            <div><span>支撑</span><strong id="coscoSupport">-</strong></div>
            <div><span>压力</span><strong id="coscoResistance">-</strong></div>
            <div><span>数据来源</span><strong id="coscoSource">-</strong></div>
            <div><span>K 线时间</span><strong id="coscoBarTime">-</strong></div>
            <div><span>数据年龄</span><strong id="coscoAge">-</strong></div>
            <div><span>数据新鲜度</span><strong id="coscoFreshness">-</strong></div>
            <div><span>实时性</span><strong id="coscoRealtime">-</strong></div>
            <div><span>日线背景 D</span><strong id="coscoDaily">-</strong></div>
            <div><span>盘中确认 I</span><strong id="coscoIntraday">-</strong></div>
            <div><span>缠论结构 C</span><strong id="coscoChan">-</strong></div>
            <div><span>T 仓系数</span><strong id="coscoScale">-</strong></div>
          </div>
          <p id="coscoTime" class="muted"></p>
          <ul id="coscoReasons" class="list"></ul>
          <ul id="coscoWarnings" class="list"></ul>
          <div class="toolbar">
            <select id="coscoProvider">
              <option value="fast">盘中快速：本地5分钟缓存 + Tencent</option>
              <option value="auto">自动快速：QMT -> 本地缓存+Tencent -> Tencent -> EastMoney -> AKShare</option>
              <option value="strict">完整慢速：Tencent/EastMoney + BaoStock/YFinance/Tushare</option>
              <option value="tencent-direct">腾讯盘中直连</option>
              <option value="eastmoney-direct">EastMoney 盘中直连</option>
              <option value="tencent">腾讯盘中 + BaoStock 历史</option>
              <option value="eastmoney">EastMoney 盘中 + BaoStock 历史</option>
              <option value="akshare">AKShare 免费</option>
              <option value="baostock">BaoStock 历史回补</option>
              <option value="yfinance">YFinance 历史分钟线</option>
              <option value="tushare">Tushare 基础权限</option>
            </select>
            <button id="refreshCoscoBtn">刷新买卖点</button>
            <button class="secondary" id="sampleCoscoBtn">加载样例（非实时）</button>
          </div>
        </section>

        <section>
          <h2>决策输出</h2>
          <div class="metrics">
            <div class="metric"><span>F 基本面</span><strong id="fScore">-</strong></div>
            <div class="metric"><span>R 退神</span><strong id="rScore">-</strong></div>
            <div class="metric"><span>T 技术</span><strong id="tScore">-</strong></div>
            <div class="metric"><span>C 缠论</span><strong id="cScore">-</strong></div>
            <div class="metric"><span>Total</span><strong id="totalScore">-</strong></div>
          </div>
          <div><span id="signal" class="signal">-</span></div>
          <ul id="reasons" class="list"></ul>
          <ul id="warnings" class="list"></ul>
          <p id="risk" class="muted"></p>
        </section>

        <section>
          <h2>红利观察池</h2>
          <p id="samplesStatus" class="muted">当前观察池优先使用腾讯真实分时扫描，失败时静态兜底。</p>
          <div class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>代码</th>
                  <th>名称</th>
                  <th>行业</th>
                  <th>最新价</th>
                  <th>扫描</th>
                  <th>信号</th>
                  <th>F</th>
                  <th>R</th>
                  <th>T</th>
                  <th>C</th>
                  <th>Total</th>
                  <th>建议仓位</th>
                  <th>风控</th>
                </tr>
              </thead>
              <tbody id="samples"></tbody>
            </table>
          </div>
        </section>
      </div>
    </div>
  </main>

  <script>
    function $(id) { return document.getElementById(id); }
    function num(id) { return Number($(id).value); }
    function checked(id) { return $(id).checked; }
    function pct(value) { return `${(Number(value) * 100).toFixed(1)}%`; }
    function escapeHtml(value) {
      return String(value ?? "").replace(/[&<>"']/g, (ch) => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;"
      }[ch]));
    }
    function listItems(items) {
      return (items || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("");
    }
    function elapsedText(item) {
      return Number.isFinite(Number(item?.elapsed_seconds)) ? `，${Number(item.elapsed_seconds).toFixed(3)} 秒` : "";
    }
    function attemptText(item) {
      const status = item.success ? "成功" : "失败";
      const detail = item.success ? `${item.rows || 0} 行` : (item.message || `${item.rows || 0} 行`);
      return `${item.provider}：${status}，${detail}${elapsedText(item)}`;
    }
    function price(value) {
      return value === null || value === undefined ? "-" : Number(value).toFixed(3);
    }
    function text(value) {
      return value === null || value === undefined || value === "" ? "-" : String(value);
    }
    function sourceName(value) {
      if (!value) return "-";
      if (value === "sample_static_5min") return "样例数据";
      if (value === "qmt_xtdata_l1_5min") return "QMT L1 5分钟";
      if (value === "local_csv_5min") return "本地5分钟缓存";
      if (value === "local_csv_5min+tencent_minute_query_1min_to_5min") return "本地缓存+腾讯盘中";
      if (value === "tencent_minute_query_1min_to_5min") return "腾讯分时转5分钟";
      if (value === "tencent_minute_query_1min_to_5min+baostock_history_5min") return "腾讯盘中+BaoStock历史";
      if (value === "eastmoney_direct_5min") return "EastMoney 5分钟";
      if (value === "eastmoney_direct_5min+baostock_history_5min") return "EastMoney盘中+BaoStock历史";
      if (value === "akshare_stock_zh_a_hist_min_em_5min") return "AKShare 5分钟";
      if (value === "baostock_query_history_k_data_plus_5min") return "BaoStock历史";
      if (value === "tushare_stk_mins_5min") return "Tushare 5分钟";
      if (value === "free_provider_fallback") return "免费源自动降级";
      return value;
    }
    function signalLabel(value) {
      const labels = {
        BUILD_BASE: "建底仓",
        HOLD: "持有观察",
        BUY_T: "买点",
        SELL_T: "卖点",
        SELL_REVERSE_T: "高位卖点",
        BUY_BACK_REVERSE_T: "回补买点",
        STOP_T: "风险卖点",
        REDUCE: "减底仓",
        CLEAR: "清仓"
      };
      return labels[value] || value || "-";
    }
    function timingActionLabel(value) {
      const labels = {
        BUY_T_TIMING: "买点",
        BREAKOUT_BUY_TIMING: "强势突破买入时机",
        WATCH_BREAKOUT_NEXT_DAY: "次日突破预警",
        SELL_T_TIMING: "卖点",
        STOP_T_WAIT: "风险卖点，等待",
        WAIT_STALE_DATA: "数据过期，等待",
        WAIT_DAILY_WEAK: "日线偏弱，等待",
        WAIT_CONFIRMATION: "等待分时确认",
        WAIT_LATE_SESSION: "尾盘等待",
        WAIT_STRONG_TREND: "强趋势保护，暂不卖出",
        WAIT: "等待",
        NEED_DATA: "需要数据"
      };
      return labels[value] || value || "-";
    }
    function ageText(value) {
      if (value === null || value === undefined) return "-";
      const minutes = Number(value);
      if (!Number.isFinite(minutes)) return "-";
      if (minutes < 1) return "小于1分钟";
      if (minutes < 60) return `${minutes.toFixed(1)}分钟`;
      return `${(minutes / 60).toFixed(1)}小时`;
    }
    function setCoscoEmpty() {
      ["coscoCurrent", "coscoBuy", "coscoSell", "coscoStop", "coscoForce", "coscoConfidence",
       "coscoSupport", "coscoResistance", "coscoSource", "coscoBarTime", "coscoAge", "coscoFreshness", "coscoRealtime",
       "coscoDaily", "coscoIntraday", "coscoChan", "coscoScale"]
        .forEach((id) => { $(id).textContent = "-"; });
    }

    function payload() {
      return {
        symbol: $("symbol").value,
        fundamental: {
          dividend_sustainability: num("dividend_sustainability"),
          valuation_margin: num("valuation_margin"),
          cycle_prosperity: num("cycle_prosperity"),
          financial_quality: num("financial_quality"),
          catalyst_stability: num("catalyst_stability")
        },
        retreat: {
          market_attention: num("market_attention"),
          upside_certainty: num("upside_certainty"),
          risk_reward_ratio: num("risk_reward_ratio"),
          sell_pressure: num("sell_pressure")
        },
        technical: {
          position_quality: num("position_quality"),
          volume_structure: num("volume_structure"),
          trend_quality: num("trend_quality"),
          intraday_support: num("intraday_support"),
          trend_state: $("trend_state").value,
          near_support: checked("near_support"),
          near_resistance: checked("near_resistance"),
          shrinking_pullback: checked("shrinking_pullback"),
          volume_stalling: checked("volume_stalling"),
          intraday_reversal: checked("intraday_reversal"),
          sector_healthy: checked("sector_healthy")
        },
        position: {
          symbol_position_pct: num("symbol_position_pct"),
          base_position_pct: num("symbol_position_pct"),
          t_position_pct: 0.02,
          cash_pct: num("available_cash_pct"),
          available_cash_pct: num("available_cash_pct"),
          available_sell_pct: num("available_sell_pct"),
          is_cycle_stock: checked("is_cycle_stock"),
          consecutive_t_failures: Number($("consecutive_t_failures").value)
        }
      };
    }

    async function postJson(url, body) {
      const response = await fetch(url, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(body)
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
      return data;
    }

    function renderDecision(data) {
      $("fScore").textContent = data.score.F_score.toFixed(1);
      $("rScore").textContent = data.score.R_score.toFixed(1);
      $("tScore").textContent = data.score.T_score.toFixed(1);
      $("cScore").textContent = data.score.C_score.toFixed(1);
      $("totalScore").textContent = data.score.total_score.toFixed(1);
      $("signal").textContent = data.signal_label || signalLabel(data.signal);
      $("signal").title = data.signal;
      $("signal").className = `signal ${data.signal}`;
      $("reasons").innerHTML = data.reasons.map((item) => `<li>${item}</li>`).join("");
      $("warnings").innerHTML = data.warnings.map((item) => `<li>${item}</li>`).join("");
      const risk = data.risk_check;
      const status = risk.allowed ? "通过" : "未通过";
      $("risk").textContent = `风控：${status}，最终可执行比例 ${pct(risk.final_notional_pct)}。${risk.violations.join(" ") || risk.warnings.join(" ")}`;
    }

    function renderCosco(data) {
      if (data.status === "data_unavailable") {
        setCoscoEmpty();
        $("coscoAction").textContent = timingActionLabel("NEED_DATA");
        $("coscoAction").title = "NEED_DATA";
        $("coscoAction").className = "signal STOP_T";
        $("coscoSource").textContent = sourceName(data.data_source);
        $("coscoFreshness").textContent = "不可用";
        $("coscoRealtime").textContent = "不可用";
        $("coscoTime").textContent = `真实 5 分钟数据不可用；当前没有实时价格。原因：${data.message}`;
        $("coscoReasons").innerHTML = listItems(data.required_user_steps);
        const attempts = (data.data_attempts || []).map((item) => attemptText(item));
        $("coscoWarnings").innerHTML = listItems([
          "当前没有生成真实 5 分钟时机信号；页面不会使用样例价格冒充实时行情。",
          ...attempts
        ]);
        return;
      }
      $("coscoAction").textContent = timingActionLabel(data.action);
      $("coscoAction").title = data.action;
      $("coscoAction").className = `signal ${data.action.includes("BUY") ? "BUY_T" : data.action.includes("SELL") ? "SELL_T" : data.action.includes("STOP") || data.action.includes("STALE") ? "STOP_T" : ""}`;
      $("coscoCurrent").textContent = price(data.prices.current_price);
      $("coscoBuy").textContent = price(data.prices.buy_reference_price);
      $("coscoSell").textContent = price(data.prices.sell_reference_price);
      $("coscoStop").textContent = price(data.prices.stop_price);
      $("coscoForce").textContent = Number(data.force.force_ratio).toFixed(2);
      $("coscoConfidence").textContent = Number(data.confidence).toFixed(1);
      $("coscoSupport").textContent = price(data.prices.support_price);
      $("coscoResistance").textContent = price(data.prices.resistance_price);
      $("coscoSource").textContent = sourceName(data.data_source);
      $("coscoBarTime").textContent = text(data.timestamp);
      $("coscoAge").textContent = ageText(data.data_age_minutes);
      $("coscoFreshness").textContent = data.data_fresh ? "新鲜" : `过期，阈值${Number(data.freshness_limit_minutes || 0).toFixed(0)}分钟`;
      $("coscoRealtime").textContent = data.is_realtime ? "实时" : "非实时";
      $("coscoDaily").textContent = scaleText(data.daily_context);
      $("coscoIntraday").textContent = scaleText(data.intraday_context);
      $("coscoChan").textContent = chanText(data.chan_structure);
      $("coscoScale").textContent = data.daily_context ? `${(Number(data.daily_context.position_multiplier || 0) * 100).toFixed(0)}%` : "-";
      const sampleNotice = data.data_source === "sample_static_5min" ? "这是样例数据，不是实时行情。" : "免费行情源是轮询数据，不是逐笔实时流。";
      const blockedNotice = data.signal_blocked ? " 数据过期，已禁止输出交易时机。" : "";
      $("coscoTime").textContent = `${data.symbol} ${data.name}，K线时间 ${data.timestamp}，生成时间 ${data.generated_at}。${sampleNotice}${blockedNotice} 仅供手动操作参考，不自动下单。`;
      $("coscoReasons").innerHTML = listItems(data.reasons);
      const failedAttempts = (data.data_attempts || [])
        .filter((item) => !item.success)
        .map((item) => `${item.provider} 获取失败，已自动降级：${item.message}${elapsedText(item)}`);
      const runtime = (data.runtime_profile || []).map((item) => `${item.step}：${item.elapsed_seconds} 秒${item.provider ? `，${item.provider}` : ""}${item.rows ? `，${item.rows} 行` : ""}`);
      $("coscoWarnings").innerHTML = listItems([...(data.warnings || []), ...failedAttempts, ...runtime]);
    }

    function scaleText(context) {
      if (!context) return "-";
      const score = Number(context.score);
      return `${context.state || "-"} / ${Number.isFinite(score) ? score.toFixed(1) : "-"}`;
    }

    function chanText(context) {
      if (!context) return "-";
      const score = Number(context.score);
      const point = context.buy_point_type && context.buy_point_type !== "none" ? context.buy_point_type : context.sell_point_type;
      return `${context.structure_type || "-"} ${point && point !== "none" ? point : ""} / ${Number.isFinite(score) ? score.toFixed(1) : "-"}`;
    }

    async function evaluate() {
      renderDecision(await postJson("/api/evaluate", payload()));
    }

    async function loadSamples() {
      const button = $("loadSamplesBtn");
      button.disabled = true;
      button.textContent = "刷新中";
      $("samplesStatus").textContent = "正在刷新红利观察池...";
      try {
        const response = await fetch("/api/sample-decisions");
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const rows = await response.json();
        $("samples").innerHTML = rows.map((row) => `
          <tr>
            <td>${escapeHtml(row.symbol)}</td>
            <td>${escapeHtml(row.name || "")}</td>
            <td>${escapeHtml(row.industry || "")}</td>
            <td title="${escapeHtml(row.latest_price_time || "")}">${price(row.latest_price)}</td>
            <td title="${escapeHtml(row.scan_message || "")}">${row.scan_status === "real_tencent_intraday" ? "真实分时" : "静态兜底"}</td>
            <td><span class="signal ${escapeHtml(row.signal)}" title="${escapeHtml(row.signal)}">${escapeHtml(row.signal_label || signalLabel(row.signal))}</span></td>
            <td>${row.score.F_score.toFixed(1)}</td>
            <td>${row.score.R_score.toFixed(1)}</td>
            <td>${row.score.T_score.toFixed(1)}</td>
            <td>${row.score.C_score.toFixed(1)}</td>
            <td>${row.score.total_score.toFixed(1)}</td>
            <td>${pct(row.suggested_trade_pct)}</td>
            <td>${row.risk_check.allowed ? "通过" : "未通过"}</td>
          </tr>`).join("");
        const realCount = rows.filter((row) => row.scan_status === "real_tencent_intraday").length;
        $("samplesStatus").textContent = `已刷新 ${rows.length} 只，${new Date().toLocaleTimeString()}。真实分时 ${realCount} 只，静态兜底 ${rows.length - realCount} 只。`;
      } catch (error) {
        $("samplesStatus").textContent = `刷新失败：${error.message}`;
      } finally {
        button.disabled = false;
        button.textContent = "刷新观察池";
      }
    }

    async function refreshCosco(useSample = false) {
      const provider = encodeURIComponent($("coscoProvider").value || "fast");
      const response = await fetch(useSample ? "/api/cosco-timing/sample" : `/api/cosco-timing?provider=${provider}`);
      renderCosco(await response.json());
    }

    $("evaluateBtn").addEventListener("click", evaluate);
    $("loadSamplesBtn").addEventListener("click", loadSamples);
    $("refreshCoscoBtn").addEventListener("click", () => refreshCosco(false));
    $("sampleCoscoBtn").addEventListener("click", () => refreshCosco(true));
    evaluate();
    loadSamples();
    refreshCosco(false);
    setInterval(() => refreshCosco(false), 300000);
  </script>
</body>
</html>
"""
