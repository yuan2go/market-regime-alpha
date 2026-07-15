# Market Regime Alpha 目录与领域边界

`market-regime-alpha` 是面向 A 股市场的 Alpha Research Operating System。仓库继续承载已有买卖点、红利/T、单股时机、回测、数据适配、Dashboard 和通知能力，同时按照 Constitution 与 Roadmap 渐进建立新的研究边界。

本文件定义的是**仓库物理目录边界和目标领域放置方向**。它不要求大爆炸重命名现有 `dividend_t` 包，也不把目录移动本身视为架构迁移。

## 仓库级目录边界

```text
market-regime-alpha/
├── README.md                       项目入口、当前能力和常用命令
├── pyproject.toml                  项目元数据、pytest、ruff、mypy 配置
├── requirements.txt                运行依赖
├── .env.example                    本地环境变量模板，不放真实密钥
├── src/market_regime_alpha/        可复用 Python 包和领域能力
├── tests/                          单元测试、characterization 和小型集成测试
├── scripts/                        数据抓取、推送、调度等运行工具
├── backtesting/                    回测入口、实验入口和兼容运行脚本
├── docs/                           Constitution、架构、研究、设计、规范和使用文档
├── strategies/                     策略假设、研究状态和历史归档
├── data/                           本地数据，不直接提交敏感或受限数据
└── reports/                        本地生成的回测与研究输出
```

仓库级目录解决文件组织问题；领域 bounded context 解决**谁拥有语义和责任**。两者不是同一层级。

## `src/market_regime_alpha/` 目标 bounded contexts

随着 R1/R2 以后逐步迁移，可复用代码的目标领域方向是：

```text
src/market_regime_alpha/
├── core/           最小共享 identity、time 和基础语义合同
├── data/           Provider、Dataset、PIT 数据和质量边界
├── universe/       PIT Universe、成员资格和 eligibility
├── features/       Feature Definition、materialization、lineage、registry
├── market/         Market Context、Market Regime、ETF/Theme context
├── candidates/     Candidate Discovery、Target、Prediction、ranking
├── strategies/     Entry、Position Lifecycle、Exit、Strategy Proposal
├── portfolio/      最终资金分配、组合约束、跨策略冲突
├── execution/      A 股执行约束、simulation、request/result
├── research/       Experiment Identity、validation artifacts、research workflow
├── application/    应用编排与 use cases
├── interfaces/     Web/API/CLI/通知等适配边界
└── legacy/         必要的显式 Legacy compatibility adapters（按需建立）
```

这些是目标责任边界，不要求一次性创建所有目录。新模块应当在有明确研究消费者和 Owner 时建立，避免 architecture astronautics。

## Legacy `dividend_t` 边界

`src/market_regime_alpha/dividend_t/` 当前同时包含：

- Dividend/T 策略领域逻辑；
- 单股时机研究；
- 指标与量价研究；
- Market Environment；
- Universe 构造；
- 回测、OOS、Dataset rehearsal 等历史平台能力。

迁移期间它被视为：

```text
Legacy Strategy Domain
+
Legacy Research Assets
```

允许继续：

- correctness / security 修复；
- tests 和 characterization；
- trace 与 reproducibility 改进；
- compatibility 修复；
- 已有 Legacy 研究维护。

禁止继续：

- 把新的平台级 Candidate System 建进 `CoscoTimingEngine`；
- 把新的全局 Feature/Factor Platform 继续塞进 `dividend_t`；
- 在 Legacy `backtest.py` 中继续增加新的平台级生命周期、Portfolio 或 Execution Owner；
- 仅通过改目录名把 Legacy 宣布为 V2。

Legacy import path 只有在替代能力、characterization、迁移消费者和回滚方案都具备后才可退休。

## 文档权威边界

```text
Constitution
    ↓
Architecture
    ↓
Research / Design
    ↓
Specification
    ↓
Implementation
    ↓
Evidence Artifact
```

推荐文档目录：

```text
docs/
├── constitution/   最高层项目治理与 canonical vocabulary
├── architecture/   当前架构、迁移审计、责任边界
├── research/       具体研究 Charter、实验和结论
├── designs/        子系统设计
├── specs/          可实施合同与接口规范
└── ...             现有平台、理论和使用文档
```

下层文档不得静默覆盖上层 Constitution。

## 放置规则

- 可复用领域逻辑放 `src/market_regime_alpha/`，不要长期堆在脚本中。
- 一次性或运维运行入口放 `scripts/`；回测/实验入口可放 `backtesting/`，但核心逻辑应进入可复用模块。
- 策略假设和交易边界可放 `strategies/ideas/`；正式研究应逐步引用明确的 Research Charter、Target、Dataset、Experiment Identity 和 Evidence Artifact。
- Constitution 放 `docs/constitution/`；架构与迁移审计放 `docs/architecture/`。
- 原始行情放 `data/raw/`，清洗结果和缓存放 `data/processed/`，观察池等外部清单放 `data/external/`。
- 受许可限制的数据不得因为研究方便而提交到公共仓库。
- 回测输出放 `reports/backtests/` 或内容寻址的研究 artifact 目录；不要把可变报告当作源码逻辑或唯一正式证据。
- UI、Dashboard、通知和 JSON 字段是 Interface，不得反向定义 canonical Domain semantics。

## 版本与提交边界

提交到 Git 的内容通常包括：

- `src/`、`tests/`、`scripts/`、`backtesting/` 中的源码和可维护入口；
- `README.md`、`docs/`、`strategies/` 中的核心文档和策略/研究设计；
- 小型、授权允许的样例数据、synthetic fixtures 和观察池配置；
- schema、manifest schema、hash、非敏感质量报告和报告模板。

默认不提交：

- `reports/` 下普通脚本生成的可变 `.md`、`.csv`、`.html`、`.json` 输出；
- `data/processed/` 下的 Parquet、DuckDB、信号缓存；
- `data/raw/dividend_t_5min/`、`data/raw/dividend_t_5min_6m/` 下的本地行情缓存；
- `data/local/` 下的账户、仓位、本地运行状态；
- API key、券商账户、交易凭证、受限供应商原始数据；
- `__pycache__/`、`.venv/`、`.env` 等环境产物。

正式 Evidence Artifact 是否提交 Git 取决于大小、授权、敏感性和存储策略，但必须具有稳定 Identity，不能只依赖一个可覆盖的 `latest` 目录。

## 当前迁移阶段

```text
R0  Constitution / Refoundation Freeze       → 收尾完成
R1  Repository Truth / Legacy Characterization → ACTIVE
R2  Minimal V2 Kernel + Compatibility Boundary → ACTIVE（受控并行）
```

R1 与 R2 可受控并行：R1 持续补足 Legacy characterization，R2 只建立最小、稳定、无策略逻辑的共享合同。

## 常用入口

```bash
cd /Users/yuan/projects/market-regime-alpha
python3 -m pytest
python3 -m ruff check .
python3 -m mypy
python3 backtesting/run_ma_crossover.py
PYTHONPATH=src python3 backtesting/run_cosco_dividend_t_backtest.py
PYTHONPATH=src python3 backtesting/run_buy_sell_point_hit_rate.py
PYTHONPATH=src uvicorn market_regime_alpha.web.dividend_t_app:app --reload --host 127.0.0.1 --port 8010
```

以上 Legacy 入口可继续运行；新的 V2 能力通过兼容边界逐步接入，不要求一次性迁移全部消费者。
