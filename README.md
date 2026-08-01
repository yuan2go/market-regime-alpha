# Market Regime Alpha

> **Status:** CURRENT_STATUS  
> **Authority:** Repository entry point; not a substitute for Constitution or current status documents  
> **Owner:** Market Regime Alpha maintainers  
> **Last Updated:** 2026-08-01  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** docs/README.md, docs/status/Current-State.md, docs/constitution/00-Project-Vision.md, docs/architecture/10-Production-Decision-Lifecycle.md  
> **Code Evidence:** `src/market_regime_alpha/**`, `tests/**`; current implementation facts are maintained in Current-State.md.

`market-regime-alpha` 是面向 A 股的 **Alpha Research Operating System**。当前可交付产品边界是：

> A 股量化研究与交易决策辅助系统。

程序负责市场、ETF、主题与资金环境分析，股票和 ETF Candidate Discovery，Entry、持仓、Exit、风险边界、推荐复盘和失败归因；用户负责最终判断、手动下单和真实交易记录。

## Canonical chain

```text
Market Regime
→ ETF / Theme / Capital Context
→ Tradable Universe and Eligibility
→ Feature / Factor Pipeline
→ Candidate Discovery
→ Signal and Path Forecast
→ Trading Opportunity and Thesis
→ Portfolio and Risk Decision
→ Manual Execution Record
→ Position Lifecycle
→ Holding and Exit
→ Validation / Review / Failure Attribution
→ Research Feedback
```

严格边界：

```text
Candidate Prediction
≠ Signal Confirmation
≠ Trading Opportunity
≠ Portfolio / Risk Approval
≠ Manual Execution Record
≠ Actual Position
≠ Exit Result
```

## 当前事实

- 已具备 V2 identity/time/data/universe/eligibility/feature/candidate contracts、B0/B1、Candidate diagnostics、Entry Path Target infrastructure、Provider routing、Xuntou v4 evidence/adapters、PIT replication success path 和不可变 Research Artifact 验证器。
- Research Platform Kernel V1 已进入 `main`：Theory/Observable/Model contracts、Target/Evaluation Protocol、Experiment Governance、Model Registry 和第一版 Multi-model Candidate Slice 均已有代码与测试。
- 当前已具备可恢复的探索性每日 Runtime Journal、Source Manifest 与质量门、B0/B1 PredictionRun、Phase D 每日决策 Artifact、CandidateRecommendation 投影、禁止 `ENTER` 的 Entry plumbing、MR1 outcome settlement 和 Daily Review；Model Registry 与 Experiment Governance 仍是进程内权威。
- Platform V2 Research Layer 已实现 Market Regime、Theme Rotation、Capital Evolution 和 Candidate Discovery 的离线可回放工程闭环，但当前模型权重与阈值仍是未验证假设。
- 2026-08-01 已提交 Production Decision Lifecycle 文档基线，明确采用“现有仓库内模块化单体，未来仅按真实部署边界拆分执行适配器”的组织方式。
- Production Decision Lifecycle 当前仍是目标架构，不代表 Signal Engine、PathForecast、TradingOpportunity、TradingThesis、Risk Authority、Manual Fill Ledger、PositionSnapshot、Holding/Exit 或 Attribution 已经实现。
- 历史 `daily_research` V1 的 immutable DailyResearchSnapshot、CandidateRecommendation、EntryAssessment、Artifact Publisher 和 Semantic Reader 已实现并有测试，但它是 frozen compatibility layer，不是 Canonical Phase D Runtime。
- 真实 Xuntou/XtQuant v4 输入在当前环境不可用，因此正式 PIT replication 仍为 `BLOCKED_EXTERNAL_INPUT`。
- 真实 public LIVE 运行仍因 Decision-window 与资格状态数据不足而 `DATA_BLOCKED`；正式 PIT、OOS Alpha 与模型赢家均未建立。
- 当前不做真实 QMT/PTrade 自动委托、自动撤改单、无人值守实盘、自动再平衡或依赖逐笔 Level-2 的高频系统。

唯一当前实现状态入口：[`docs/status/Current-State.md`](docs/status/Current-State.md)。

## Production Decision Lifecycle

目标生产决策辅助链路由以下文档共同定义：

- [Production Decision Lifecycle Architecture](docs/architecture/10-Production-Decision-Lifecycle.md)
- [ADR-004 — Production Decision Lifecycle Organization](docs/architecture/decisions/ADR-004-Production-Decision-Lifecycle-Organization.md)
- [Production Decision Lifecycle Requirements](docs/specs/Production-Decision-Lifecycle-Requirements.md)
- [WP-PDL — Production Decision Lifecycle](docs/roadmap/work-packages/WP-PDL-Production-Decision-Lifecycle.md)
- [Production Decision Lifecycle Gap Analysis](docs/audit/Production-Decision-Lifecycle-Gap-Analysis.md)
- [Production Decision Lifecycle Runbook](docs/operations/Production-Decision-Lifecycle-Runbook.md)
- [Claude Code Implementation Prompt](docs/prompts/Claude-Code-Production-Decision-Lifecycle.md)

当前唯一推荐的工程组织方式是：

```text
现有仓库
+ 模块化单体
+ 明确 bounded contexts
+ Application 编排
+ 不可变 Evidence Authority
+ 实际 Fill 作为 Position 的未来权威来源
+ 仅在真实外部运行边界出现后拆分 Broker Adapter
```

## 文档入口

- [文档总导航](docs/README.md)
- [Project Vision](docs/constitution/00-Project-Vision.md)
- [Architecture Blueprint](docs/constitution/02-Architecture-Blueprint.md)
- [Platform Architecture V2](docs/architecture/09-Platform-Architecture-V2.md)
- [Production Decision Lifecycle](docs/architecture/10-Production-Decision-Lifecycle.md)
- [Current State](docs/status/Current-State.md)
- [Capability Matrix](docs/status/Capability-Matrix.md)
- [Gap Register](docs/status/Gap-Register.md)
- [Phase D Daily Decision Engine](docs/architecture/05-Phase-D-Daily-Decision-Engine-V1.md)
- [Detailed Work Packages](docs/roadmap/work-packages/README.md)

## Development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python scripts/check_docs_links.py
python -m pytest -q
python -m ruff check .
python -m mypy
```

Legacy Dividend-T、Cosco timing、Dashboard、飞书调度和 broker adapters 仍保留用于行为复现与渐进迁移。它们不是 V2 Kernel，也不拥有平台最终研究或账户权威。Legacy 运行说明见 [`docs/archive/legacy/README.md`](docs/archive/legacy/README.md)。
