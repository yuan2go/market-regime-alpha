# Backtesting Experiments

## MACD four-arm sealed rehearsal

`run_macd_ablation.py` runs the fixed `baseline`, `score-only`, `policy-only`, and `full`
profiles against one content-addressed dataset and split manifest. Development runs may select only
`train`, `validation`, or `rehearsal`; the `test` segment is rejected unless `--final-test` is explicit.

The runner requires bar files with explicit `bar_final`, plus point-in-time universe, corporate-action,
suspension, and exchange-calendar sidecars. It writes through a temporary sibling directory and only
publishes a checksummed `COMPLETED` artifact after all four profiles succeed. Existing run ids are never
overwritten and there is intentionally no force option.

```bash
PYTHONPATH=src ./.venv/bin/python backtesting/run_macd_ablation.py \
  --data /path/to/rehearsal-bars.csv \
  --split-manifest /path/to/split.json \
  --universe /path/to/universe.json \
  --corporate-actions /path/to/corporate-actions.json \
  --suspensions /path/to/suspensions.json \
  --trading-calendar /path/to/trading-calendar.json \
  --trading-calendar-version sse-calendar-v1 \
  --data-source sealed-research-source-v1 \
  --dataset-classification REHEARSAL \
  --pit-adjustment-complete \
  --segment rehearsal \
  --dry-run
```

Production remains `baseline`: `score_weight=0.0`, `conflict_gate_enabled=False`. Neither the 15% score
weight nor the MACD policy is authorized for production by this runner.

## ETF Moving-Average Crossover

Run the first prototype from the project root:

```bash
python3 backtesting/run_ma_crossover.py
```

The experiment loads `data/raw/sample_etf_ohlcv.csv`, goes long when the fast moving average is above the slow moving average, and otherwise stays in cash. The sample data is synthetic and only exists to verify the OHLCV contract and backtest loop.

Useful parameters:

```bash
python3 backtesting/run_ma_crossover.py --fast-window 5 --slow-window 20
python3 backtesting/run_ma_crossover.py --data data/raw/sample_etf_ohlcv.csv --symbol SAMPLE_ETF
```

Build a self-contained web visualization:

```bash
python3 backtesting/build_ma_crossover_visual.py
```

Open `backtesting/ma_crossover_visual.html` in a browser. The page shows the ETF close price, fast/slow moving averages, buy/sell signals, long-position zones, summary metrics, and the equity curve.

## 中远海控长期红利做 T 回测

运行优化后的中远海控 5 分钟手动时机模型回测：

```bash
PYTHONPATH=src ./.venv/bin/python backtesting/run_cosco_dividend_t_backtest.py
```

默认使用内置多日样例数据，并生成：

```text
reports/backtests/cosco_dividend_t_backtest.md
```

使用本地 5 分钟 CSV：

```bash
PYTHONPATH=src ./.venv/bin/python backtesting/run_cosco_dividend_t_backtest.py \
  --data data/raw/your_601919_5min.csv \
  --symbol 601919.SH
```

CSV 至少需要字段：

```text
symbol,timestamp,open,high,low,close,volume
```

也可以尝试免费数据源：

```bash
PYTHONPATH=src ./.venv/bin/python backtesting/run_cosco_dividend_t_backtest.py --provider tencent
```

注意：免费数据源的历史分钟线覆盖和稳定性有限；严肃回测应优先使用已落地的历史 5 分钟 CSV 或后续 QMT/PTrade 导出的行情。

回测规则：

- 用上一根 5 分钟 K 线生成信号，下一根 K 线开盘执行，避免未来函数。
- 模拟底仓、T 仓、倒 T 待买回仓位、手续费、印花税、滑点和最小 100 股交易单位。
- 默认启用 A 股成交约束：T+1 可卖股、涨停不买、跌停不卖、停牌/零成交量不成交。
- 除权除息支持 `cash_dividend_per_share` / `share_bonus_ratio` 字段；普通分钟 CSV 缺少这些字段时，报告会保留偏差说明。
- 统计总收益、买入持有基准收益、超额收益、最大回撤、胜率、交易次数和时间尺度门控次数。
- `WAIT_DAILY_WEAK`、`WAIT_CONFIRMATION`、`WAIT_LATE_SESSION` 用来观察优化后的日线/分时门控是否减少误买。
- `WAIT_STRONG_TREND` 用来观察强趋势保护是否减少过早倒 T。

## 红利观察池批量回测

批量回测 `data/external/watchlists/dividend_t_watchlist.csv` 中的股票：

```bash
PYTHONPATH=src ./.venv/bin/python backtesting/run_dividend_watchlist_backtest.py \
  --data-dir data/raw/dividend_t_5min
```

每只股票一个 CSV，文件名支持：

```text
601919.SH_5min.csv
601919_SH_5min.csv
601919.SH.csv
601919_SH.csv
```

CSV 字段至少需要：

```text
symbol,timestamp,open,high,low,close,volume
```

批量报告输出：

```text
reports/backtests/dividend_watchlist_backtest.md
reports/backtests/dividend_watchlist_backtest.csv
```

如果要尝试免费数据源：

```bash
PYTHONPATH=src ./.venv/bin/python backtesting/run_dividend_watchlist_backtest.py \
  --provider baostock \
  --timeout-seconds 35 \
  --workers 4 \
  --worker-mode auto
```

本地 CSV 回测和退神/缠论信号计算属于 CPU 密集任务，优先使用 `--worker-mode auto`。它会先尝试进程并行；如果运行环境限制进程信号量，则自动回退到线程。非沙箱环境可用 `--worker-mode process` 做更快的全量回测；如果主要瓶颈是联网拉行情，可以改用 `--worker-mode thread`。

回测加载层会自动优先读取同级 Parquet 缓存。对大 universe 先构建一次缓存，后续命令仍然传原 CSV 目录即可：

```bash
PYTHONPATH=src ./.venv/bin/python scripts/build_5min_bar_store.py \
  --csv-dir data/raw/top1000_largecap_5min_2y \
  --overwrite
```

防守/进攻拆分和市场环境过滤：

```bash
PYTHONPATH=src ./.venv/bin/python backtesting/run_dividend_watchlist_backtest.py \
  --data-dir data/raw/dividend_t_5min_1y \
  --strategy-mode dynamic \
  --market-filter equal-weight \
  --signal-step-bars 24 \
  --worker-mode process

PYTHONPATH=src ./.venv/bin/python backtesting/run_dividend_watchlist_backtest.py \
  --data-dir data/raw/dividend_t_5min_1y \
  --strategy-mode defensive \
  --market-filter equal-weight \
  --signal-step-bars 24 \
  --worker-mode process

PYTHONPATH=src ./.venv/bin/python backtesting/run_dividend_watchlist_backtest.py \
  --data-dir data/raw/dividend_t_5min_1y \
  --strategy-mode offensive \
  --market-filter equal-weight \
  --signal-step-bars 24 \
  --worker-mode process
```

- `--strategy-mode defensive` 收窄主动仓位、提高买入强度阈值，并关闭进攻状态机，适合先控制回撤和交易磨损。
- `--strategy-mode offensive` 保留满攻状态机，允许强突破/三买/资金确认信号把总仓位提高到 100%。
- `--strategy-mode dynamic` 默认使用防守画像；只有 `RISK_ON` 且个股强趋势、三买或资金确认时才切到进攻画像。
- `--market-filter equal-weight` 会用观察池本地 CSV 构建等权市场代理；风险关闭时停止新买入并退出主动仓，谨慎环境只放行高质量买点。

## 1000 大盘股 Universe

使用 Tushare 当日快照生成可被批量回测脚本读取的 watchlist：

```bash
PYTHONPATH=src ./.venv/bin/python scripts/build_top1000_largecap_universe.py \
  --trade-date 20260624 \
  --limit 1000 \
  --market-value-field total_mv \
  --min-list-days 365 \
  --min-amount 50000
```

默认输出：

```text
data/external/watchlists/top1000_largecap_watchlist.csv
reports/universe/top1000_largecap_watchlist.md
```

筛选规则：

- 按 `total_mv` 或 `circ_mv` 排名前 1000。
- 剔除 ST、名称含退、北交所、上市不足一年的标的。
- 用当日 `daily` 成交额过滤长期停牌/流动性过低近似问题，初版默认 `amount >= 50000`（Tushare daily amount 单位为千元）。
- 这是当前快照 universe，不是严格 point-in-time 成分；正式研究需要按历史日期重建 universe，避免幸存者偏差。

拉取和回测该 universe：

```bash
PYTHONPATH=src ./.venv/bin/python scripts/fetch_dividend_5min_csv.py \
  --watchlist data/external/watchlists/top1000_largecap_watchlist.csv \
  --provider baostock \
  --days 365 \
  --output-dir data/raw/top1000_largecap_5min_1y

PYTHONPATH=src ./.venv/bin/python backtesting/run_dividend_watchlist_backtest.py \
  --watchlist data/external/watchlists/top1000_largecap_watchlist.csv \
  --data-dir data/raw/top1000_largecap_5min_1y \
  --strategy-mode dynamic \
  --market-filter equal-weight \
  --signal-step-bars 24 \
  --worker-mode process \
  --report reports/backtests/top1000_largecap_dynamic_backtest.md
```

当前免费源稳定性不适合作为严肃回测的唯一来源；推荐优先使用 QMT/PTrade/券商终端导出的最近一个月 5 分钟 CSV。

### BaoStock 可续跑增量抓取

`scripts/fetch_baostock_5min_batch.py` 适合批量补历史 5 分钟线。全量初始化后，日常更新应使用增量模式，避免每次重拉全部两年数据：

```bash
PYTHONPATH=src ./.venv/bin/python scripts/fetch_baostock_5min_batch.py \
  --watchlist data/external/watchlists/top1000_largecap_watchlist.csv \
  --days 735 \
  --mode incremental \
  --output-dir data/raw/top1000_largecap_5min_2y \
  --min-rows 18000 \
  --min-existing-end-date 2026-06-26 \
  --request-timeout 45 \
  --login-timeout 30 \
  --max-consecutive-failures 20 \
  --failures reports/backtests/top1000_largecap_2y_fetch_failures.csv
```

- 默认 checkpoint：`data/raw/top1000_largecap_5min_2y/.fetch_baostock_5min_batch_checkpoint.csv`。
- 每只股票成功、跳过或失败都会写 checkpoint；中断后直接重跑命令即可从本地 CSV 和 checkpoint 续跑。
- `--mode incremental` 会读取已有 CSV 的最后一根 K 线，只请求缺失日期，再按 `timestamp` 去重合并。
- `--request-timeout` 和 `--login-timeout` 会中断卡住的 BaoStock socket 调用；单票失败会写入 failures 并继续后续标的。
