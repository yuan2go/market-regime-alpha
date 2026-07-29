# Market Regime Alpha

> **Status:** CURRENT_STATUS  
> **Authority:** Repository entry point; not a substitute for Constitution or current status documents  
> **Owner:** Market Regime Alpha maintainers  
> **Last Updated:** 2026-07-26  
> **Supersedes:** None  
> **Superseded By:** None  
> **Related Documents:** docs/README.md, docs/status/Current-State.md, docs/constitution/00-Project-Vision.md  
> **Code Evidence:** src/market_regime_alpha/**, tests/**

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
→ Entry Timing
→ Position Lifecycle
→ Exit Model
→ Portfolio Decision
→ Execution Simulation / Manual Execution Record
→ Validation / Review / Failure Attribution
→ Research Feedback
```

严格边界：

```text
Candidate Prediction
≠ Entry Proposal
≠ Position Lifecycle Proposal
≠ Exit Proposal
≠ Portfolio Decision
≠ Execution Result
```

## 当前事实

- 当前已核对的 `main` 基线：`8f10bd88d498077fe18e58d3d2a179a295afba3d`。
- 已具备 V2 identity/time/data/universe/eligibility/feature/candidate contracts、B0/B1、Candidate diagnostics、Entry Path Target infrastructure、Provider routing、Xuntou v4 evidence/adapters、PIT replication success path和不可变 Research Artifact验证器。
- Research Platform Kernel V1 已进入 `main`：Theory/Observable/Model contracts、Target/Evaluation Protocol、Experiment Governance、Model Registry和第一版Multi-model Candidate Slice均已有代码与测试。
- 当前已具备可恢复的探索性每日Runtime Journal、Source Manifest与质量门、B0/B1 PredictionRun、Phase D每日决策Artifact、CandidateRecommendation投影、禁止`ENTER`的Entry plumbing、MR1 outcome settlement和Daily Review；Model Registry与Experiment Governance仍是进程内权威。
- 历史 `daily_research` V1 的 immutable DailyResearchSnapshot、CandidateRecommendation、EntryAssessment、Artifact Publisher和Semantic Reader已实现并有测试，但它是 `IMPLEMENTED_NON_CANONICAL` compatibility layer，不是Canonical Phase D Runtime。
- 真实 Xuntou/XtQuant v4 输入在当前环境不可用，因此正式 PIT replication 仍为 `BLOCKED_EXTERNAL_INPUT`。
- 真实public LIVE运行仍因Decision-window与资格状态数据不足而`DATA_BLOCKED`；正式PIT/OOS Alpha与模型赢家均未建立。
- 持久化Platform Governance、validated Entry model、PositionSnapshot、Holding/Exit Assessment、rolling review/attribution、Portfolio Decision、Codex Evidence Pack和QuantDesk集成仍未形成Canonical Authority。
- 当前不做真实 QMT/PTrade 自动委托、自动撤改单、无人值守实盘、自动再平衡或依赖逐笔 Level-2 的高频系统。

唯一当前实现状态入口：[`docs/status/Current-State.md`](docs/status/Current-State.md)。

## 文档入口

- [文档总导航](docs/README.md)
- [Project Vision](docs/constitution/00-Project-Vision.md)
- [Architecture Blueprint](docs/constitution/02-Architecture-Blueprint.md)
- [Current State](docs/status/Current-State.md)
- [Capability Matrix](docs/status/Capability-Matrix.md)
- [Phase D Daily Decision Engine](docs/architecture/05-Phase-D-Daily-Decision-Engine-V1.md)
- [Phase D Work Packages](docs/roadmap/Phase-D-Work-Packages.md)
- [Post-Merge Reconciliation Audit](docs/audit/Post-Merge-Reconciliation-2026-07-26.md)
- [Post-Consolidation Code Audit](docs/audit/Post-Consolidation-Code-Audit-2026-07-26.md)

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
