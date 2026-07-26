# Research Platform Kernel V1

> **Status:** FROZEN ARCHITECTURE CONTRACT  
> **Project:** `market-regime-alpha`  
> **Purpose:** 将现有 Candidate Research 基础设施渐进演化为多理论、多模型、统一验证与受控反馈的 A 股 Alpha Research Operating System。  
> **Authority boundary:** 本文定义平台合同与研究治理，不建立任何 Alpha、模型赢家、生产交易或收益承诺。

---

## 1. 决策摘要

本工作包一次性冻结以下五项：

1. Canonical Domain Model；
2. Target / Evaluation Protocol；
3. Experiment Governance；
4. Model Registry；
5. 首个 Multi-Model Candidate Vertical Slice。

项目不另建第二套平台仓库，也不大爆炸重写 Legacy。现有 `FeatureDefinition`、`CandidateResearchDataset`、`CandidatePrediction`、`ExperimentIdentity`、B0 和 B1 排名继续作为权威基础合同。平台内核只补充缺失的模型身份、比较协议、研究预算、生命周期和多模型编排。

冻结后的主链路为：

```text
Provider / Dataset
        ↓
Universe Snapshot
        ↓
Registered Feature Matrix
        ↓
Frozen Target Protocol
        ↓
Registered Models
        ↓
Frozen Experiment Protocol
        ↓
Comparable Multi-Model Prediction
        ↓
Outcome / Evaluation
        ↓
Model Lifecycle Decision
        ↓
Codex Research Proposal（后续工作包）
```

---

# Part A — Canonical Domain Model

## 2. 领域分层

平台使用以下不可混淆的概念层级：

```text
Theory
→ Observable
→ Feature
→ Signal / Prediction
→ Model
→ Strategy
→ Portfolio
→ Execution
```

### 2.1 Theory

理论是对市场行为的解释框架，例如：

- 动量；
- 量价关系；
- MACD / 均线；
- 缠论；
- 退神理论；
- ETF / Theme Rotation；
- Market Regime。

理论本身不产生交易权限。

### 2.2 Observable

Observable 是从理论中提取的可观察市场现象，例如：

- 相对强度上升；
- 成交额扩张；
- 中枢突破；
- 攻击强度上升；
- 主题宽度扩张。

Observable 必须提供：

- 可计算规则；
- 边界案例；
- 对应 Feature；
- 版本；
- 成熟度状态。

### 2.3 Feature

Feature 继续由现有 `FeatureDefinition` 和 `FeatureMaterialization` 拥有权威。平台不创建第二套 Feature 定义。

### 2.4 Model

Model 只负责一个明确角色：

```text
CONTEXT
CANDIDATE
ENTRY
HOLDING
EXIT
PORTFOLIO
```

一个 Model Definition 必须绑定：

- `model_id`；
- 版本；
- family；
- role；
- Target；
- Universe；
- Feature 集；
- 实现引用；
- 参数哈希；
- 决策时间；
- Horizon；
- 父模型；
- 可接受的数据证据等级。

Model 不拥有最终账户仓位，也不直接发送订单。

### 2.5 Strategy、Portfolio 与 Execution

它们不在本工作包中实现，但权威边界从现在起冻结：

| 对象 | 唯一职责 |
|---|---|
| Model | 预测、评分、排名、概率或风险分布 |
| Strategy | Candidate、Entry、Holding、Exit 的行为组合 |
| Portfolio | 跨标的、跨主题、跨策略的资金与风险分配 |
| Execution | T+1、涨跌停、停牌、整数手、费用、滑点和成交状态 |

任何模型输出都不能绕过 Strategy / Portfolio / Execution 直接成为账户动作。

---

## 3. 定义成熟度

Theory 和 Observable 统一采用：

```text
CONCEPTUAL
→ FORMALIZED
→ IMPLEMENTED
→ UNIT_VALIDATED
→ EMPIRICALLY_TESTED
→ APPROVED
→ RETIRED
```

只有 `APPROVED` Feature/Observable 才能进入正式模型；较低状态可以进入探索实验，但必须在结果中保留限制。

---

## 4. 显式无结论状态

平台必须允许：

```text
PREDICTION_AVAILABLE
NO_PREDICTION
NO_TRADE
INSUFFICIENT_EVIDENCE
DATA_BLOCKED
MODEL_DISAGREEMENT
```

相对排名第一不代表绝对值得交易。系统不得为了生成日报而强制产生推荐。

---

# Part B — Target / Evaluation Protocol

## 5. Target 是模型比较赛道的核心

“明天上涨”不是合法正式 Target。Target 必须明确：

- 决策时间；
- 起始价格标记；
- 终止价格标记；
- Horizon；
- 绝对收益或相对收益；
- Benchmark；
- 复权规则；
- 可用时间；
- 缺失处理；
- 是否依赖分钟路径；
- 是否已经扣成本。

V1 支持的标准语义包括：

```text
RETURN
RELATIVE_RETURN
MFE
MAE
PATH_EVENT
TIME_TO_EVENT
```

价格标记包括：

```text
DECISION_PRICE
NEXT_OPEN
NEXT_1030
NEXT_1445
NEXT_CLOSE
SESSION_HIGH
SESSION_LOW
HORIZON_CLOSE
```

## 6. 第一条正式比较赛道

首个纵向切片冻结为：

```text
Universe: 高流动性沪深 A 股的既有 CandidateResearchDataset
Decision Time: 14:50 Asia/Shanghai
Target: 次交易日 10:30 相对基准收益
Model Role: CANDIDATE
Entry / Exit: 不在本切片中比较
Portfolio: 等权研究组合，仅用于后续评价
Execution: 固定成本模型引用，当前切片不发送订单
```

该 Target 的正式 `TargetId` 由运行数据集提供；推荐命名语义为：

```text
target-next-session-1030-relative-return-v1
```

## 7. Evaluation Protocol

每个直接比较赛道必须冻结：

- `model_role`；
- `target_id`；
- `universe_id`；
- 主指标；
- 次指标；
- 风险指标；
- 稳健性指标；
- Top-K；
- 基准模型；
- 成本模型；
- 数据切分；
- 最小交易日；
- 最小覆盖率；
- 通过条件；
- 失败条件。

### 7.1 Candidate 主指标

推荐冻结为：

```text
Top-K cost-adjusted benchmark-relative return
```

Candidate 辅助指标：

- Rank IC；
- Top-K 正收益率；
- 排名单调性；
- MFE / MAE；
- 覆盖率；
- 换手率；
- 收益集中度；
- 参数和时间切片稳定性。

### 7.2 不能直接比较的模型

只有以下条件一致时才能直接比较：

```text
Universe
Decision Time
Target
Horizon
Cost Model
Split Protocol
Evaluation Window
```

隔夜、3日趋势、ETF轮动、红利、做T等策略不得进入一个简单总榜。跨赛道只能在后续 Portfolio 层比较风险收益、资金占用、相关性和组合边际贡献。

---

# Part C — Experiment Governance

## 8. 冻结实验协议

每次实验必须在读取验证结果前绑定：

- Research Hypothesis；
- 当前模型；
- 父模型；
- Dataset；
- Universe；
- Target；
- Evaluation Protocol；
- Feature；
- 参数候选；
- 唯一 Primary Change；
- 比较模型；
- Split；
- Cost Model；
- Code Revision；
- Environment；
- Experiment Budget。

协议内容寻址生成 `ExperimentId`。修改任何结果相关字段都必须生成新实验。

## 9. 单一主要变化原则

挑战模型每次只允许一个主要变化：

```text
FEATURE_SET
FEATURE_DEFINITION
MODEL_FORM
PARAMETER_SET
TARGET
UNIVERSE
ENTRY_POLICY
EXIT_POLICY
PORTFOLIO_POLICY
COST_MODEL
```

新建基线使用：

```text
BASELINE_CREATION
```

除基线外，挑战模型必须绑定父模型。禁止在同一实验同时修改 Feature、Target、Universe、持有周期和成本后声称找到增量来源。

## 10. 实验预算

V1 默认预算：

```text
max_parameter_variants = 3
max_targets = 1
max_validation_accesses = 1
max_sealed_test_accesses = 1
```

这些是初始治理默认值，不是统计定理。任何扩大预算都必须创建新协议并说明理由。

## 11. 验证集和 Sealed Test

系统必须记录：

```text
validation_access_count
sealed_test_access_count
```

超过预算必须 fail-closed。失败实验永久保留，不能换名后重新测试。Codex 后续只能提出新实验，不能重置访问计数。

---

# Part D — Model Registry

## 12. 生命周期

模型状态统一为：

```text
DRAFT
→ RESEARCH
→ BACKTESTED
→ OOS_VALIDATED
→ SHADOW
→ PROMOTION_CANDIDATE
→ ACTIVE
```

异常和退出状态：

```text
DEGRADED
SUSPENDED
RETIRED
```

## 13. 证据等级

证据与生命周期独立：

```text
UNQUALIFIED
EXPLORATORY
REHEARSAL
FORMAL_RESEARCH
SHADOW_EVIDENCE
LIVE_OBSERVED
```

示例：模型可以处于 `SHADOW`，但数据仍只有 `EXPLORATORY`，此时不能声称正式 Alpha。

## 14. 晋级规则

以下晋级必须绑定 evidence references：

- `OOS_VALIDATED`；
- `SHADOW`；
- `PROMOTION_CANDIDATE`；
- `ACTIVE`。

进入 `ACTIVE` 额外要求人工 `approval_ref`。模型、Codex、回测收益和单日表现均不能单独完成晋级。

## 15. Definition Identity Conflict

同一个 `model_id` 只能对应一个完全一致的 `ModelDefinition`。实现、参数、Target、Universe 或 Feature 发生结果相关变化时必须注册新模型版本。

---

# Part E — First Multi-Model Vertical Slice

## 16. 模型梯子

首个切片固定运行三个 Candidate 模型：

### B0 — Momentum

```text
model_id = platform-b0-momentum-v1
score = momentum feature
```

### B1 — Balanced Composite

```text
model_id = platform-b1-balanced-v1
momentum = 0.50
volume expansion = 0.30
lower volatility = 0.20
```

### B2 — Volume-Momentum Challenger

```text
model_id = platform-b2-volume-momentum-v1
momentum = 0.45
volume expansion = 0.55
```

权重是固定的工程验证配置，不构成 Alpha 结论。

## 17. 可比性门控

三个模型必须共享同一个：

- `CandidateResearchDataset`；
- Candidate Population；
- Universe；
- Decision Time；
- Target；
- Code Revision；
- Outcome评价协议。

每个模型必须保存：

- 完整预测排序；
- 显式 rejection；
- ranking coverage；
- Experiment ID；
- config hash。

切片额外输出模型间 Top-K：

- overlap count；
- union count；
- Jaccard。

共识度只作为描述指标，不能默认等于更高收益。

## 18. 当前完成边界

本工作包完成：

- 多模型统一运行；
- 相同研究范围门控；
- B0/B1/B2固定定义；
- 完整排名和拒绝记录；
- Top-K横向重叠；
- 单元测试夹具。

本工作包没有完成：

- 真实腾讯每日调度；
- 次日 Outcome 自动匹配；
- 60日滚动评价；
- Entry / Exit；
- Portfolio；
- Codex Evidence Pack；
- 正式讯投 PIT 运行；
- Alpha证明；
- 自动或真实下单。

---

# Part F — Acceptance Criteria

## 19. 五项验收

### 19.1 Canonical Domain Model

- Theory、Observable、Model和生命周期对象存在；
- 复用现有 Feature、Candidate、Target和Experiment身份；
- Model角色唯一；
- 定义可内容哈希。

### 19.2 Target / Evaluation Protocol

- Target时间、价格、收益基准、缺失和路径语义显式；
- Evaluation定义主指标、基准、成本、Split和门槛；
- 相同赛道才可直接比较。

### 19.3 Experiment Governance

- 协议在验证访问前冻结；
- 挑战模型绑定父模型；
- Primary Change唯一；
- 参数、Target和测试访问有预算；
- 超预算fail-closed。

### 19.4 Model Registry

- 同身份冲突被拒绝；
- 生命周期只能按允许路径迁移；
- 晋级必须有证据；
- ACTIVE必须人工批准。

### 19.5 Multi-Model Slice

- 同一 Candidate Dataset运行三模型；
- 每个模型保留完整结果；
- 输出模型间Top-K重叠；
- 不产生订单；
- 测试验证合同和门控。

---

# Part G — Next Ordered Work

五项完成后，后续顺序冻结为：

```text
1. 将现有真实 Candidate builder 接到 Multi-Model Slice
2. 生成不可覆盖 Prediction Ledger
3. 次日 10:30 Outcome 自动匹配
4. 5/20/60日 Model Scorecard
5. Research Evidence Pack
6. Codex Diagnosis / Experiment Proposal
7. Entry Registry 与增量验证
8. Holding / Exit Registry
9. Portfolio / Execution Simulation
10. 正式讯投 PIT 与 Shadow
```

在第4项完成前，不新增大量缠论、退神或主题模型；在第6项完成前，Codex不进入自动研究闭环；在正式PIT和Shadow通过前，不授予真实交易权限。

---

## 20. 最终状态声明

完成本工作包后，项目可以声明：

```text
RESEARCH_PLATFORM_KERNEL_V1_COMPLETE
MULTI_MODEL_CANDIDATE_SLICE_AVAILABLE
ARCHITECTURE_LOGIC_FROZEN
ALPHA_NOT_PROVEN
TRADING_AUTHORITY_NOT_GRANTED
```
