# Data Spec

## OHLCV

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| symbol | string | 标的 |
| timestamp | datetime | 时间 |
| open | float | 开盘价 |
| high | float | 最高价 |
| low | float | 最低价 |
| close | float | 收盘价 |
| volume | float | 成交量 |

## 数据目录规则

- `data/raw`：原始数据，不直接改。
- `data/processed`：清洗后的数据。
- `data/external`：第三方数据或临时导入。

## 5 分钟行情加速存储

逐票 CSV 仍然是原始数据落地点；为了加快 walk-forward 和事件研究，回测加载层支持同一份数据转成 Parquet 或 PostgreSQL。

Parquet 是默认推荐路径。生成一次缓存：

```bash
PYTHONPATH=src ./.venv/bin/python scripts/build_5min_bar_store.py \
  --csv-dir data/raw/top1000_largecap_5min_2y \
  --overwrite
```

默认输出到同级目录 `data/raw/top1000_largecap_5min_2y_parquet`，现有 `load_5min_bars_path(data_dir, symbol=...)` 会自动优先读取该 Parquet 缓存，找不到时再回退 CSV。也可以显式指定：

```bash
QUANT_5MIN_BAR_BACKEND=parquet \
QUANT_5MIN_PARQUET_DIR=data/raw/top1000_largecap_5min_2y_parquet \
PYTHONPATH=src ./.venv/bin/python backtesting/run_top1000_screened_portfolio_backtest.py ...
```

PostgreSQL 适合多进程共享、跨实验查询和后续特征表 join。导入前需要本机可用 `psql`：

```bash
PYTHONPATH=src ./.venv/bin/python scripts/build_5min_bar_store.py \
  --csv-dir data/raw/top1000_largecap_5min_2y \
  --skip-parquet \
  --postgres-dsn postgresql://user:password@127.0.0.1:5432/quant \
  --postgres-table public.bars_5min
```

如果 `psql` 不在 `PATH`，用 `--psql-bin /path/to/psql` 指定。回测从 PostgreSQL 读取需要安装可选依赖：

```bash
pip install -e ".[postgres]"
```

然后设置：

```bash
QUANT_5MIN_BAR_BACKEND=postgres
QUANT_5MIN_POSTGRES_DSN=postgresql://user:password@127.0.0.1:5432/quant
QUANT_5MIN_POSTGRES_TABLE=public.bars_5min
```

存储字段固定为 `symbol,timestamp,open,high,low,close,volume,amount,source_freq,is_suspended,is_st,prev_close,cash_dividend_per_share,share_bonus_ratio`，PostgreSQL 主键为 `(symbol, timestamp)`。

## Tushare 规范化字段

Tushare A股日线和分钟线读取后，会先规范化为以下字段，方便后续回测和页面展示：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| symbol | string | Tushare 股票代码，例如 `600000.SH` |
| timestamp | datetime | 日线为 `YYYY-MM-DD`，分钟线为 `YYYY-MM-DD HH:MM:SS` |
| open | float | 开盘价 |
| high | float | 最高价 |
| low | float | 最低价 |
| close | float | 收盘价 |
| volume | float | 成交量，保留 Tushare 原始单位 |
| amount | float | 成交额，保留 Tushare 原始单位 |
| source_freq | string | `daily`、`1min`、`5min`、`15min`、`30min` 或 `60min` |

## 资金流确认字段

A 股买卖点识别模型会优先使用真实资金流字段；如果这些字段不存在，才退回到 OHLCV 成交额方向代理。代理资金流只能用于研究和预警，不应等同于交易软件里的大单净流入。

推荐统一字段如下：

| 字段 | 类型 | 来源 | 说明 |
| --- | --- | --- | --- |
| main_net_inflow | float | QMT L2 / 东方财富资金流 / 腾讯资金接口 | 主力净流入金额，优先级最高 |
| large_net_inflow | float | QMT L2 / 东方财富资金流 | 大单净流入金额 |
| super_large_net_inflow | float | QMT L2 / 东方财富资金流 | 超大单净流入金额 |
| active_buy_amount | float | QMT tick / 逐笔成交 | 主动买入金额 |
| active_sell_amount | float | QMT tick / 逐笔成交 | 主动卖出金额 |
| bid_buy_amount | float | 五档盘口快照聚合 | 买盘挂单金额或主动吃卖金额，需在采集层注明口径 |
| ask_sell_amount | float | 五档盘口快照聚合 | 卖盘挂单金额或主动砸买金额，需在采集层注明口径 |

模型识别优先级：

1. `main_net_inflow` / `main_net_amount` / `net_inflow` / `large_net_inflow` / `big_order_net_inflow` / `super_large_net_inflow` / `active_net_inflow`
2. `active_buy_amount - active_sell_amount`
3. `buy_amount - sell_amount`
4. OHLCV 方向代理

回测和实时信号里会输出：

| 字段 | 说明 |
| --- | --- |
| capital_flow_score | 资金流综合分 |
| capital_flow_confirmation_score | 资金确认分 |
| capital_flow_confirmation_state | `CONFIRMED_INFLOW` / `CONFIRMED_OUTFLOW` / `DIVERGENT` / `UNCONFIRMED` |
| capital_flow_source_type | `REAL_MONEY_FLOW` / `OHLCV_PROXY` |
| capital_flow_confidence | 资金流可信度 |

## 缠论结构字段

当前第一阶段用 OHLCV 计算缠论结构，不依赖 Level-2。字段会出现在 `CoscoTimingSnapshot.chan_structure`、回测信号缓存，以及通用策略的 `TechnicalInputs` 中。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| level | string | 结构级别，例如 `daily`、`30m`、`5m` |
| score | float | 缠论结构分 C，0-100 |
| structure_type | string | `pivot` / `breakout` / `breakdown` / `divergence` / `trend` / `insufficient` |
| pivot_low | float | 中枢下沿 |
| pivot_high | float | 中枢上沿 |
| pivot_mid | float | 中枢中轴 |
| pivot_width | float | 中枢宽度比例 |
| trend_direction | string | `up` / `down` / `range` |
| divergence_type | string | `top` / `bottom` / `none` |
| divergence_score | float | 背驰强度分 |
| buy_point_type | string | `buy1` / `buy2` / `buy3` / `range_buy` / `none` |
| sell_point_type | string | `sell1` / `sell2` / `sell3` / `none` |
| invalid_price | float | 买点或结构失效价 |
| fractal_count | int | 分型数量 |
| stroke_count | int | 笔数量 |
| pivot_count | int | 中枢数量 |
| latest_fractal_type | string | 最近分型类型 |
| reasons | list[string] | 结构解释 |

策略使用方式：

1. 退神买卖力判断资金是否认可。
2. 缠论结构判断位置、买点、卖点和失效价。
3. 风控门优先处理三卖、跌破中枢、顶背驰和日线弱势。

## 样例数据

- `data/raw/sample_etf_ohlcv.csv`：合成 ETF 日线样例，字段严格对应上面的 OHLCV 规范。
- 样例数据只用于验证读取、策略和回测流程，不作为真实行情或投资结论。
