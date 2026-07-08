# market-regime-alpha

Market-regime-driven A-share stock selection, dividend-T, and ETF rotation research tool.

本项目集中承载 A 股红利 / 做 T 模型、行情适配、回测、Dashboard、通知脚本和核心文档。

完整使用手册见 [`docs/Usage-Manual.md`](docs/Usage-Manual.md)，目录边界见 [`docs/Project-Structure.md`](docs/Project-Structure.md)。

## 目录

- `data`：原始数据、清洗后数据和外部数据。
- `backtesting`：回测框架、实验和结果。
- `strategies`：策略想法、实现和归档。
- `reports`：日报、周报、回测报告。
- `scripts`：一次性脚本和工具脚本。
- `src`：可复用代码。
- `tests`：测试。
- `docs`：项目文档。

## 运行前提

推荐在项目根目录创建虚拟环境：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

开发检查工具在 `pyproject.toml` 里配置。需要运行测试、ruff 和 mypy 时安装开发依赖：

```bash
pip install -e ".[dev]"
```

常用质量检查：

```bash
python3 -m pytest
python3 -m ruff check .
python3 -m mypy
```

## 第一个可运行回测

本项目现在有一个最小 ETF 均线交叉回测原型。它使用 `docs/Data-Spec.md` 中定义的 OHLCV 字段，读取 `data/raw/sample_etf_ohlcv.csv`，当短期均线高于长期均线时持有 ETF，否则空仓。

从项目根目录运行：

```bash
python3 backtesting/run_ma_crossover.py
```

常用参数：

```bash
python3 backtesting/run_ma_crossover.py --fast-window 5 --slow-window 20
python3 backtesting/run_ma_crossover.py --data data/raw/sample_etf_ohlcv.csv --symbol SAMPLE_ETF
```

生成 Web 可视化图形：

```bash
python3 backtesting/build_ma_crossover_visual.py
```

生成文件为 `backtesting/ma_crossover_visual.html`，浏览器打开后可以看到价格、快慢均线、买卖信号、持仓区间、核心指标和权益曲线。该文件属于运行产物，不提交到 Git。

输出含义：

- `Total return`：期末权益相对初始资金的总收益。
- `Annualized return`：按日频 252 个交易日折算的年化收益。
- `Max drawdown`：权益曲线从历史高点到低点的最大回撤。
- `Sharpe ratio`：不含无风险利率的简化夏普。
- `Trade events` / `Completed trades` / `Win rate`：开平仓事件、完成交易次数和盈利交易比例。

样例 CSV 是合成数据，只用来验证数据契约和回测流程跑通，不代表策略在真实市场有效。

运行中远海控长期红利做 T 模型回测：

```bash
PYTHONPATH=src ./.venv/bin/python backtesting/run_cosco_dividend_t_backtest.py
```

该脚本会回放优化后的 `DailyContext + IntradayContext` 时间尺度门控模型，输出 Markdown 报告到 `reports/backtests/cosco_dividend_t_backtest.md`。`reports/` 下生成的报告和 CSV 属于研究产物，不提交到 Git。严肃回测请传入更长的真实 5 分钟 CSV：

```bash
PYTHONPATH=src ./.venv/bin/python backtesting/run_cosco_dividend_t_backtest.py --data data/raw/your_601919_5min.csv --symbol 601919.SH
```

批量回测红利观察池：

```bash
PYTHONPATH=src ./.venv/bin/python backtesting/run_dividend_watchlist_backtest.py --data-dir data/raw/dividend_t_5min
```

## Tushare A股行情查询

本项目现在提供一个最小 Tushare A股数据读取和本地网页查询入口，支持股票搜索、日线和分钟线：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

在项目根目录创建 `.env`：

```bash
TUSHARE_TOKEN=你的Tushare Token
```

启动页面：

```bash
PYTHONPATH=src uvicorn market_regime_alpha.web.tushare_app:app --reload --host 127.0.0.1 --port 8000
```

也可以直接抓取 CSV：

```bash
python3 scripts/fetch_tushare_bars.py daily 600000.SH --start 20240101 --end 20240518
python3 scripts/fetch_tushare_bars.py minute 600000.SH --freq 1min --start "2024-05-17 09:00:00" --end "2024-05-17 15:30:00"
```

详细说明见 `docs/Tushare-App.md`。

## 长期 / 红利 / 做 T 交易平台

本项目现在有一版长期红利做 T 模型平台骨架，覆盖 F/R/T/C 评分、退神买卖力、缠论结构、策略信号、风控检查、观察池、Paper/QMT/PTrade 交易网关接口和本地 Dashboard。
当前已增加中远海控 `601919.SH` 的 5 分钟手动时机面板，只输出参考买入价、参考卖出价、止损价和理由，不自动下单。行情层已适配腾讯分时、EastMoney 直连、AKShare、BaoStock、Tushare 基础权限，默认按 `Tencent -> EastMoney -> AKShare -> BaoStock -> Tushare` 自动降级；自动模式会优先用腾讯分时聚合 5 分钟线，并用 BaoStock 只回补历史 K 线。面板会显示数据来源、K 线时间、数据年龄和数据新鲜度；如果数据过期，会禁止输出交易时机。

启动页面：

```bash
PYTHONPATH=src uvicorn market_regime_alpha.web.dividend_t_app:app --reload --host 127.0.0.1 --port 8010
```

打开 `http://127.0.0.1:8010`。详细说明见 `docs/Dividend-T-Platform.md`。

生成并推送中远海控提醒：

```bash
PYTHONPATH=src ./.venv/bin/python scripts/cosco_timing_report.py --provider auto --no-persist --push --notify-channel feishu
```

飞书机器人配置放在本地 `.env`：`FEISHU_WEBHOOK_URL`，可选 `FEISHU_SECRET`。

如果要在 A 股交易时间自动推送到手机，只运行本地飞书调度器，不再使用 Codex 内置定时任务：

```bash
PYTHONPATH=src ./.venv/bin/python scripts/cosco_feishu_scheduler.py
```

后台运行可以用 `tmux`：

```bash
tmux new-session -d -s cosco-feishu 'cd /Users/yuan/projects/market-regime-alpha && PYTHONPATH=src ./.venv/bin/python scripts/cosco_feishu_scheduler.py'
```

当前推送时间为交易日 `09:35`、`10:05`、`10:35`、`11:05`、`13:05`、`13:35`、`14:05`、`14:35`、`15:05`，所有消息只通过飞书机器人发送。

## 规则

- 不提交 API key、账户、交易凭证。
- 样例数据和观察池清单可以提交；本地行情缓存、信号缓存、处理后数据和生成报告不提交。
- 每个策略必须有假设、数据、回测、风险和结论。
- Agent 可以辅助研究，不自动做资金决策。
