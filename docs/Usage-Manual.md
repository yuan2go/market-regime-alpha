# market-regime-alpha 使用手册

## 1. 项目定位

`market-regime-alpha` 是独立的可运行量化研究项目，当前重点不是直接实盘交易，而是把 A 股红利 / 做 T 研究流程拆成可验证的工程模块：

- 多源行情读取与标准化
- 红利观察池和中远海控 5 分钟手动择时
- 策略假设、回测报告和风险控制
- 本地 Dashboard 与飞书提醒
- 样例 ETF 均线回测，用于验证最小回测链路

所有命令默认从项目根目录 `/Users/yuan/projects/market-regime-alpha` 运行。

## 2. 目录结构

```text
market-regime-alpha/
├── data/
│   ├── raw/                   原始数据，只读保存
│   ├── processed/             清洗后的数据
│   └── external/              第三方或临时导入数据
├── backtesting/               回测实验入口和实验说明
├── strategies/
│   ├── ideas/                 策略想法模板
│   ├── implemented/           已实现策略
│   └── archived/              暂停或废弃策略
├── reports/
│   ├── daily/                 日报
│   ├── weekly/                周报
│   └── backtests/             回测报告模板和输出
├── docs/                      项目文档
├── notebooks/                 Jupyter 实验
├── scripts/                   一次性脚本和工具脚本
├── src/market_regime_alpha/        可复用 Python 代码
└── tests/                     单元测试
```

## 3. 关键文件

| 文件 | 用途 |
| --- | --- |
| `README.md` | 项目总览和第一个回测的快速说明 |
| `docs/Data-Spec.md` | OHLCV 数据字段规范和数据目录规则 |
| `docs/Dividend-T-Platform.md` | 红利做 T 平台说明 |
| `docs/theory/退神股票涨跌理论.md` | 策略理论原文 |
| `data/raw/sample_etf_ohlcv.csv` | 合成 ETF 日线样例数据 |
| `src/market_regime_alpha/backtesting.py` | 最小回测工具：数据读取、均线、回测指标 |
| `src/market_regime_alpha/dividend_t/cosco_timing.py` | 中远海控 5 分钟手动时机总入口 |
| `src/market_regime_alpha/dividend_t/cosco_timing_daily.py` | 日线背景和多周期趋势 |
| `src/market_regime_alpha/dividend_t/cosco_timing_intraday.py` | 盘中支撑/压力确认 |
| `src/market_regime_alpha/dividend_t/cosco_timing_capital_flow.py` | 资金流和买入确认 |
| `src/market_regime_alpha/dividend_t/cosco_timing_breakout.py` | 突破/次日预警识别 |
| `src/market_regime_alpha/dividend_t/cosco_timing_manual.py` | 手动动作状态机 |
| `src/market_regime_alpha/dividend_t/backtest.py` | 红利做 T 回测引擎 |
| `backtesting/run_ma_crossover.py` | ETF 均线交叉回测命令行入口 |
| `backtesting/run_dividend_watchlist_backtest.py` | 红利观察池批量回测入口 |
| `backtesting/README.md` | 回测实验说明 |
| `strategies/ideas/Strategy-Idea-Template.md` | 策略想法模板 |
| `reports/backtests/Backtest-Report-Template.md` | 回测报告模板 |
| `tests/test_backtesting.py` | 回测模块测试 |

## 4. 环境要求

建议从项目根目录运行命令：

```bash
cd /Users/yuan/projects/market-regime-alpha
python3 --version
```

安装依赖：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

当前 `.gitignore` 已排除 `.env`、`.venv/`、缓存、数据库文件和敏感数据文件。

如需运行开发检查：

```bash
pip install -e ".[dev]"
python3 -m pytest
python3 -m ruff check .
python3 -m mypy
```

版本边界以 `docs/Project-Structure.md` 为准：源码、测试、核心文档、样例数据和观察池清单进入 Git；生成报告、信号缓存、本地行情缓存、处理后数据和账户本地状态不进入 Git。

## 5. 快速运行

运行当前最小 ETF 均线交叉回测：

```bash
python3 backtesting/run_ma_crossover.py
```

默认行为：

- 读取 `data/raw/sample_etf_ohlcv.csv`
- 只加载 `SAMPLE_ETF`
- 使用 `MA(3)` 和 `MA(8)`
- 当短期均线高于长期均线时持有 ETF，否则空仓
- 使用下一根 K 线收益模拟信号执行后的组合收益

常用参数：

```bash
python3 backtesting/run_ma_crossover.py --fast-window 5 --slow-window 20
python3 backtesting/run_ma_crossover.py --data data/raw/sample_etf_ohlcv.csv --symbol SAMPLE_ETF
python3 backtesting/run_ma_crossover.py --initial-cash 50000
```

重要限制：

- 样例 CSV 是合成数据，只用于验证流程。
- 输出指标不是实盘有效性证据。
- 当前回测未包含手续费、滑点、分红、复权、税费和真实订单撮合。

## 6. 回测输出解读

当前脚本会输出：

| 指标 | 含义 |
| --- | --- |
| `Initial cash` | 初始资金 |
| `Final equity` | 期末权益 |
| `Total return` | 总收益 |
| `Annualized return` | 按 252 个交易日折算的年化收益 |
| `Max drawdown` | 权益曲线历史高点到低点的最大回撤 |
| `Sharpe ratio` | 不含无风险利率的简化夏普 |
| `Trade events` | 信号切换次数 |
| `Completed trades` | 完整开平仓交易次数 |
| `Win rate` | 完整交易中盈利交易占比 |

## 7. 数据使用规范

OHLCV CSV 必须包含以下字段：

```text
symbol,timestamp,open,high,low,close,volume
```

字段要求：

- `symbol`：标的代码
- `timestamp`：ISO 日期或日期时间，例如 `2026-01-02`
- `open/high/low/close`：价格字段，可转成浮点数
- `volume`：成交量，可转成浮点数

目录规则：

- `data/raw` 保存原始数据，不直接改。
- `data/processed` 保存清洗、复权、聚合后的数据。
- `data/external` 保存第三方临时导入或参考数据。

新增真实数据时，先放入 `data/raw`，再写清洗脚本输出到 `data/processed`。不要把 API key、账号、交易凭证放进数据目录。

## 8. 新增策略流程

推荐按这个顺序推进一个策略：

1. 在 `strategies/ideas/` 复制 `Strategy-Idea-Template.md`，写清楚假设、数据需求、入场、出场和风控。
2. 把所需原始数据放入 `data/raw/`，并检查是否符合 `docs/Data-Spec.md`。
3. 在 `backtesting/` 新增一个实验入口脚本，优先复用 `src/market_regime_alpha/` 中的通用代码。
4. 把可复用逻辑沉淀到 `src/market_regime_alpha/`，不要长期堆在实验脚本里。
5. 在 `tests/` 为关键函数补测试。
6. 在 `reports/backtests/` 复制 `Backtest-Report-Template.md`，记录数据范围、参数、结果、风险和结论。
7. 只有当假设、数据、回测、风险和结论都清楚时，才把策略从 `ideas/` 移到 `implemented/`。

## 9. Python 模块用法

可以直接复用当前回测模块：

```python
from pathlib import Path

from market_regime_alpha.backtesting import load_ohlcv_csv, run_moving_average_crossover

bars = load_ohlcv_csv(Path("data/raw/sample_etf_ohlcv.csv"), symbol="SAMPLE_ETF")
result = run_moving_average_crossover(
    bars,
    fast_window=3,
    slow_window=8,
    initial_cash=10_000,
)

print(result.total_return)
print(result.max_drawdown)
```

如果从项目根目录外部运行，需要先把 `src` 加入 `PYTHONPATH`，或后续把项目整理成可安装包。

## 10. 测试

推荐测试命令：

```bash
python3 -m unittest discover -s tests
```

当前测试覆盖样例回测、红利做 T 策略、COSCO 时机引擎、A 股行情标准化、回测交易闭环、Web API 和通知模块。

注意：直接运行 `python3 -m unittest` 在当前项目结构下不会可靠发现测试，请使用上面的显式 discovery 命令。

## 11. 研究工作流

日常建议：

1. 每次写策略，先在 `strategies/ideas/` 写清假设、适用条件、失效条件和风险。
2. 每次跑回测，都把参数和结论写进 `reports/backtests/`。
3. 每周在 `reports/weekly/` 写一次复盘：学了什么、验证了什么、下一步做什么。
4. 可复用逻辑进入 `src/market_regime_alpha/`，一次性入口留在 `scripts/` 或 `backtesting/`。

## 12. 后续扩展建议

短期优先级：

- 给回测加入手续费、滑点和交易成本。
- 增加多标的数据读取和过滤。
- 把策略信号生成、组合权益计算、指标统计拆成更清晰的模块。
- 增加市场环境分层和 ETF 轮动相关的样例实验。
- 增加真实数据下载脚本，但把凭证放在 `.env`，不要提交。

中期优先级：

- 增加特征、标签、训练、验证的最小流程。
- 让 Agent 只做研究辅助、报告整理和代码检查。
- 评估高性能数据读取、行情缓存和并发处理的独立模块。

## 13. 安全边界

- 本项目用于学习和研究，不直接做资金决策。
- Agent 可以辅助搜索、整理、生成报告和检查代码，但不应该自动下单。
- 不提交 API key、账户、交易凭证和真实资金相关敏感信息。
- 所有策略结论必须同时包含适用条件、失败条件和风险说明。
