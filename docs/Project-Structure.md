# A 股买卖点识别模型目录规划

`market-regime-alpha` 是独立的 A 股买点 / 卖点识别研究项目。后续量化代码、核心文档、脚本、测试、数据契约和报告都应优先放在本仓库内。

## 目录边界

```text
market-regime-alpha/
├── README.md                  项目入口、常用命令和运行说明
├── pyproject.toml             pytest、ruff、mypy 和包元数据配置
├── requirements.txt           项目运行依赖
├── .env.example               本地环境变量模板，不放真实密钥
├── src/market_regime_alpha/        可复用 Python 包
├── tests/                     单元测试和小型集成测试
├── scripts/                   数据抓取、推送、调度等工具脚本
├── backtesting/               回测入口、参数搜索和回测说明
├── docs/                      核心文档、数据规范、平台说明、理论说明
├── strategies/                策略假设、实现状态和归档
├── data/                      本地数据，不直接提交敏感数据
└── reports/                   回测报告和研究输出
```

## 放置规则

- 可复用逻辑放 `src/market_regime_alpha/`，不要长期堆在脚本里。
- 一次性运行入口放 `scripts/` 或 `backtesting/`。
- 策略假设和交易边界放 `strategies/ideas/`，成熟后再进入 `strategies/implemented/`。
- 数据规范、平台手册、理论文档放 `docs/`。
- 原始行情放 `data/raw/`，清洗结果和缓存放 `data/processed/`，观察池等外部清单放 `data/external/`。
- 回测输出放 `reports/backtests/`，不要把报告当成源码逻辑引用。
- 仓库根目录保持项目入口文件，业务代码、实验脚本、数据契约和报告按上面的目录边界放置。

## 版本边界

提交到 Git 的内容：

- `src/`、`tests/`、`scripts/`、`backtesting/` 中的源码和可维护入口。
- `README.md`、`docs/`、`strategies/` 中的核心文档和策略设计。
- `data/raw/sample_etf_ohlcv.csv`、`data/external/watchlists/dividend_t_watchlist.csv` 这类小型样例或配置清单。
- `reports/backtests/Backtest-Report-Template.md` 这类报告模板。

不提交到 Git 的内容：

- `reports/` 下脚本生成的 `.md`、`.csv`、`.html`、`.json` 研究输出。
- `data/processed/` 下的 Parquet、DuckDB、信号缓存。
- `data/raw/dividend_t_5min/`、`data/raw/dividend_t_5min_6m/` 下的本地行情缓存。
- `data/local/` 下的账户、仓位、本地运行状态。
- `__pycache__/`、`.venv/`、`.env` 等本地环境产物。

## 常用入口

```bash
cd /Users/yuan/projects/market-regime-alpha
python3 -m pytest
python3 -m ruff check .
python3 -m mypy src
python3 backtesting/run_ma_crossover.py
PYTHONPATH=src python3 backtesting/run_cosco_dividend_t_backtest.py
PYTHONPATH=src python3 backtesting/run_buy_sell_point_hit_rate.py
PYTHONPATH=src uvicorn market_regime_alpha.web.dividend_t_app:app --reload --host 127.0.0.1 --port 8010
```
