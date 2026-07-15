# Market Regime Alpha — A 股 Alpha Research Operating System

`market-regime-alpha` 是一个面向 A 股市场的 **Alpha Research Operating System（Alpha 研究操作系统）**。

项目目标不是寻找一条永久有效的买卖规则，也不是尽快自动下单，而是建立一个可以持续完成以下循环的研究系统：

```text
Market / ETF / Theme Context
        ↓
Tradable Universe
        ↓
Feature / Factor Research
        ↓
Candidate Discovery
        ↓
Entry
        ↓
Position Lifecycle
HOLD / ADD / REDUCE / ROTATE / EXIT
        ↓
Portfolio / Execution Simulation
        ↓
Validation / Review / Research Feedback
```

当前第一战略研究优先级是 **Candidate Discovery**：在明确的决策时间、目标和可复现股票池中，对 A 股机会进行横截面预测与排序。ETF、主题和 Market Regime 既可以作为上游 Context，也可以成为独立研究或直接交易策略；它们不会被默认当作未经验证的硬门控。

## 当前迁移状态

仓库正在从早期的 A 股买卖点、红利/T、单股时机研究，渐进迁移到上述 Alpha Research Operating System。

历史 `market_regime_alpha.dividend_t` 包、`CoscoTimingEngine`、买卖点模型、回测、Dashboard、调度器和通知脚本仍然是有价值的 **Legacy Research Assets**。为了保持现有导入路径、研究复现和运行能力，它们不会被大爆炸重写或立即删除。

迁移原则：

```text
Legacy Freeze
    ↓
Characterize Existing Behavior
    ↓
Minimal V2 Kernel and Compatibility Boundary
    ↓
Move New Research onto Explicit Contracts
    ↓
Extract Evidence-Backed Legacy Components
    ↓
Retire Redundant Paths Only After Replacement Evidence Exists
```

基础治理文档见 [`docs/constitution/`](docs/constitution/)，迁移路线见 [`docs/constitution/08-Roadmap.md`](docs/constitution/08-Roadmap.md)，canonical 术语见 [`docs/constitution/09-Glossary.md`](docs/constitution/09-Glossary.md)。完整使用手册见 [`docs/Usage-Manual.md`](docs/Usage-Manual.md)，目录边界见 [`docs/Project-Structure.md`](docs/Project-Structure.md)。

## 目录

- `data`：原始数据、清洗后数据和外部数据。
- `backtesting`：回测框架、实验和结果。
- `strategies`：策略想法、实现和归档。
- `reports`：日报、周报、回测报告。
- `scripts`：一次性脚本和工具脚本。
- `src`：可复用代码。
- `tests`：测试。
- `docs`：项目文档、Constitution、架构与研究规范。

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

运行中远海控买卖点识别模型回测：

```bash
PYTHONPATH=src ./.venv/bin/python backtesting/run_cosco_dividend_t_backtest.py
```

该脚本会回放优化后的 `DailyContext + IntradayContext` 时间尺度门控模型，输出 Markdown 报告到 `reports/backtests/cosco_dividend_t_backtest.md`。`reports/` 下生成的报告和 CSV 属于研究产物，不提交到 Git。严肃评估请传入更长的真实 5 分钟 CSV：

```bash
PYTHONPATH=src ./.venv/bin/python backtesting/run_cosco_dividend_t_backtest.py --data data/raw/your_601919_5min.csv --symbol 601919.SH
```

批量回测红利观察池：

```bash
PYTHONPATH=src ./.venv/bin/python backtesting/run_dividend_watchlist_backtest.py --data-dir data/raw/dividend_t_5min
```

评估买卖点 1 / 3 / 5 日命中率：

```bash
PYTHONPATH=src ./.venv/bin/python backtesting/run_buy_sell_point_hit_rate.py
```

该脚本输出 `reports/backtests/buy_sell_point_hit_rate.md` 以及总览、动作拆分、事件明细 CSV。买点命中定义为信号后未来收盘高于执行价；卖点命中定义为信号后未来收盘低于执行价。该能力属于 Legacy timing diagnostic，不代表所有 Exit intent 的统一验证标准。

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

## Legacy A 股买卖点识别平台

仓库仍保留一版 A 股买点 / 卖点识别平台骨架，覆盖 F/R/T/C 评分、退神买卖力、缠论结构、买卖点信号、风控检查、观察池、Paper/QMT/PTrade 交易网关接口和本地 Dashboard。

当前已增加中远海控 `601919.SH` 的 5 分钟手动时机面板，只输出参考买入价、参考卖出价、止损价和理由，不自动下单。行情层已适配腾讯分时、EastMoney 直连、AKShare、BaoStock、Tushare 基础权限，默认按 `Tencent -> EastMoney -> AKShare -> BaoStock -> Tushare` 自动降级；自动模式会优先用腾讯分时聚合 5 分钟线，并用 BaoStock 只回补历史 K 线。面板会显示数据来源、K 线时间、数据年龄和数据新鲜度；如果数据过期，会禁止输出交易时机。

这些路径用于 Legacy 研究、兼容和行为复现。数据可访问或已标准化不等于该数据自动具备正式 PIT 研究资格。

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

## GitHub Pages 红利趋势定时发布

本项目提供一个本地常驻任务，用于驱动 GitHub Pages 上的 20 支红利股票趋势看板：

- 每 5 分钟拉取 `data/external/watchlists/dividend_t_watchlist.csv` 前 20 支股票的腾讯 1 分钟交易数据，并写入本地 DuckDB。
- 每 10 分钟重新计算 20 支股票的未来 1 到 3 个交易日趋势倾向，写入 `docs/data/dividend_trends.json`。
- 如果 JSON 有变化，脚本会自动提交并 `git push` 到当前仓库远端，GitHub Pages 会展示最新结果。

先做一次单次验证，不推送：

```bash
PYTHONPATH=src ./.venv/bin/python scripts/dividend_trend_scheduler.py --once both --include-off-session --no-push
```

确认本地 git 远端、SSH key 和 GitHub Pages 都正常后，启动本地定时任务：

```bash
PYTHONPATH=src ./.venv/bin/python scripts/dividend_trend_scheduler.py
```

后台运行可以用 `tmux`：

```bash
tmux new-session -d -s dividend-trend 'cd /Users/yuan/projects/market-regime-alpha && PYTHONPATH=src ./.venv/bin/python scripts/dividend_trend_scheduler.py'
```

如果要在非交易时间测试完整流程，可以加 `--include-off-session`。该任务只生成研究快照并更新 Pages JSON，不自动下单；如果本地有未推送提交或远端拒绝 push，脚本会记录 git 发布失败并继续下一轮调度。

## 规则

- 不提交 API key、账户、交易凭证。
- 样例数据和观察池清单可以提交；本地行情缓存、信号缓存、处理后数据和生成报告不提交。
- 每个正式策略必须有明确目标、市场/股票池或 ETF 池、信号来源、入场、出场、仓位管理、风控、回测、观察、失效条件和复盘方式。
- 研究报告必须区分事实、推测、模型假设、研究结果、交易计划、风险、失效条件和后续观察指标。
- Agent 可以辅助研究和工程实现，但不自动获得资金决策或 sealed-test 访问权。