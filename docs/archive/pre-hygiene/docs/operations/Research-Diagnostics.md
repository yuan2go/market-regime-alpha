# 已完成研究活动的只读诊断

> **Status:** CURRENT_STATUS
> **Authority:** Read-only projection of reconciled research Authority; no qualification or execution authority
> **Owner:** Market Regime Alpha maintainers
> **Last Updated:** 2026-09-08
> **Code Evidence:** `src/market_regime_alpha/research_qualification/application/backtest_diagnostics.py`, `src/market_regime_alpha/research_qualification/domain/backtest_diagnostics.py`, `src/market_regime_alpha/infrastructure/postgres/queries/backtest_diagnostics.py`

报告不可估计的原因已能分类；当前样本中的模型排序增量及 Alpha 瓶颈仍未确定。本诊断保留完整成员去向，金融指标只引用已对账的 canonical Evaluation，不读取 raw bars、不重训、不调参，也不修改冻结协议、阈值或历史结果。

## 新盘后协议的独立探索结果

新 Run `7ef9337b-9efd-5573-8d67-f29b0a6a92e0` 在原库 OID 287543、
cluster `7681924516459622681` 完成 187 个 Generic actions；它不是旧 R2
失败 Run 的重开或结果覆盖。冻结实现为 `ec43f8aa`，参数在 Validation
访问前登记：20 FIT、10 VALIDATION 交易日、32 证券、一个 purge 和一个
embargo session、两个实验臂、Ridge alpha=1。目标是下一交易日原始价格
close/open−1；结果只评价预测，不产生账户收益或交易盈利结论。

完整成员核算为 1,920 个证券×实验臂×FIT/VALIDATION session 单元，1,918
个合法 Candidate，2 个合法排除，无未解释成员丢失。每个 Validation 臂
声明 320 个成员：`sh.600438` 在 2026-02-25 因 canonical SUSPENDED 状态
排除一次，319 个成员有预测。其前一日预测的目标窗口遇到封存的
`INVALID_OHLC` SourceGap，保留失败 Outcome，最终 318 个共同成员可估计。
预测覆盖是 319/320，估计覆盖是 318/320；两臂没有可用性差异。
报告不因失败已记录而把它计为可估计，亦不从分母删除该成员。

下表直接投影两份 canonical Validation Evaluation（`302fcca4…` rule、
`c2f9e8f0…` Ridge），不是报告侧重新计算的金融指标。单位均为 RATIO；
IC 先按各实际交易日的横截面计算，再汇总 10 个交易日。

| 指标 | 规则基线 | Ridge |
|---|---:|---:|
| MAE，318 个共同可估计成员 | 0.015712149687 | 0.013995517332 |
| RMSE，318 个共同可估计成员 | 0.023151517933 | 0.021096356302 |
| Bias | -0.002017002007 | -0.001139424020 |
| 每日 RankIC 均值 | -0.173538973950 | 0.173538973950 |
| 每日 IC 样本标准差 | 0.277669773697 | 0.277669773697 |

ModelVersion `fe47f296-17dc-5654-a9eb-cf149f5b01c9` 使用 640 个 FIT 行、
20 个独立交易日；两者不能混作样本量。唯一 Feature 的 FIT 均值
0.002049193615、标准差 0.023766942487、系数 -0.000319080908、截距
0.000894723259 均来自已核验 fitted Artifact
`5adb43bafae4180e351706d5407b2446410a65f618e97bf84e0efd7b59e36a53`。
319 个共同预测的 4,929 次排序/并列比较与**反向**规则排序完全一致，
而非新增独立排序信息。该方向由固定 FIT 学得，没有按 Validation 结果
调参。误差减少也可能来自预测幅度收缩；未预声明常数均值对照，不能
从这次结果单独归因。下一版本可预声明该对照，并继续观察未到期的实际
预测；不能重标已观察历史为 untouched OOS。Alpha 瓶颈仍为 NOT_DETERMINED。

标准报告含 6 个 Evaluation、30 个已声明可估计指标。重复 publish/resume/
replay 保持 19 个相关表的计数、报告绑定与字节；初次执行的读对账超时
及 canonical 恢复日志保留。报告 JSON SHA
`90318517a9ff82bfa36da4f9c23b5e57ae6c742e398cb1c585dbb9398de3c581`，
Markdown SHA `8a9de10ad4cae5f42e93f9ccc627ec223a0ebb277023642d9023ce410c8fea66`。
完整来源位于增量包 `daily-model-research-loop-20260907` 的
`baseline-canonical-diagnosis.json`、`baseline-denominator-summary.json`、
`baseline-ridge-rule-order-proof.json` 和 `baseline-repeat-proof.json`。
以下旧 R2 诊断仍保留它自己的协议、数据库范围和失败/不可估计事实。

## 旧 R2 精确范围与使用限制

恢复基线为 `85d0080ab3bf14fade5b91e8ef98aa9a16e0c2b2`。本轮新增诊断读者的实际源码内容身份记录在证据包中；不能把新读者的验证归入基线原有代码。最终实现关系由现有 [R2 Verification](../references/WP-ARCHITECTURE-REFOUNDATION-18Q-R2-Verification.md) 和 [R2 证据索引](../references/WP-ARCHITECTURE-REFOUNDATION-18Q-R2-Evidence.json) 记录。

| 身份 | 本报告采用的精确范围 |
|---|---|
| BacktestRun | `6318cbb0-e1d5-54b4-96bf-a2f458d0ef71` |
| Database logical role | `COMPLETED_RECOVERY` |
| Database name / OID | `mra_wp18q_r2_continuation_restore_20260906` / `117559774` |
| PostgreSQL cluster identity | `7682058034626392615` |
| Definition SHA256 | `05d0db442105251914d41ef075fd0b287d974908ed180102119b379b45635701` |
| Specification SHA256 | `4f98cb6949da19c3cf7517cc14846ce6f4aed61f89ed0f06640f561cfa1f968f` |
| 研究口径 | `EXPLORATORY_RETROSPECTIVE`，既有冻结 V1 公式及经济结果 |

原库 OID `287543` 中同一 Run 的 `FAILED` 事实保留。完成恢复范围不替代原库，也不证明原库连续运行或已切换写入范围。既有 [V2 独立 episode 经济性验收](../references/WP-RESEARCH-ECONOMICS-CORRECTNESS-01-Verification.md) 不升级这些 V1 结果；Target 标签期限不自动成为可交易持有期，建议和 Risk 授权也不等于真实成交。已观察的 Validation 不重新标为 untouched OOS。

## 完整分母与成员去向

冻结范围包含 **44 个独立实际交易日、32 只证券、4 个实验臂、296 个 Dataset/Decision cell**。完整分母为 **9,472 个证券 × 实验臂 × fold-session 成员**；同一证券和交易日可能用于多个臂及重叠 FIT。下列成员数不是独立事件、交易、episode 或账户数。

| 漏斗位置 | Canonical 投影结果及去向 |
|---|---|
| Universe / Eligibility | 9,472 个声明成员；9,436 个通过，36 个合法排除；不明成员丢失为 0 |
| Feature | 9,436 个成员为 `AVAILABLE:EXACT_ARCHIVED_BAR`；36 个资格排除成员未进入该 Dataset Feature roster |
| Candidate | 1,512 个 `SELECTED`，7,924 个 `RANKED_NOT_SELECTED`；36 个资格排除成员没有 Candidate |
| Context | 按完整成员投影：7,936 个 POSITIVE、1,536 个 NEGATIVE；Context 是 Decision 级事实，不能把重复成员计数当独立状态观测 |
| Signal / Forecast | Validation 中 376 个 Signal PRESENT、2,160 个 NO_SIGNAL、24 个资格排除成员无下游；Forecast 保留 188 个 rule、188 个 model 可用估计，以及各 1,080 个 NOT_APPLICABLE / NOT_ESTIMABLE |
| Opportunity | Validation 中 376 个 ACTIONABLE、1,080 个 NO_ACTION、1,080 个 NOT_ESTIMABLE、24 个资格排除成员无下游 |
| Portfolio / Risk | Portfolio 为 360 个 INCLUDED、2,049 个 EXCLUDED、127 个 NOT_ESTIMABLE、24 个资格排除成员无 line；Risk 按成员投影为 2,304 个 AUTHORIZED、128 个 NO_ACTION、128 个 UNKNOWN |
| Outcome / Evaluation | 9,428 个成员有 COMPLETE Outcome，8 个有 UNAVAILABLE revision，36 个资格排除成员无承诺下的 Outcome；不可估计结果按下一节保留 |

36 个资格排除均可追溯到 `SECURITY_STATUS=SUSPENDED` 不满足冻结的 `EQ ACTIVE` 规则。这是跨臂及 FIT/fold 用途的 cell-member 计数，不能称为 36 次独立停牌或 36 次行情缺失。FIT 的 6,912 个声明成员用途不规划 Signal、Forecast、Opportunity、Portfolio 或 Risk；`NOT_PLANNED_FIT` 是设计边界。

8 个 UNAVAILABLE Outcome revision 对应同一证券在 `2026-02-24` 的不同臂/fold 承诺用途，canonical reason 为 `OBSERVATION_UNAVAILABLE` / `METRIC_UNAVAILABLE`。现有证据没有证明停牌是它们的因果来源。Feature 投影未发现 SourceGap reason 也不能推出全部 Outcome 行情齐备。

## 97 个 NOT_ESTIMABLE 的实际分类

这些数字统计 Evaluation 结果，不是缺失交易日或证券数。

| 数量 | 保存的 reason | 对完整成员及输入 roster 的核验 |
|---|---|---|
| 88 | `EXPECTED_ROSTER_MISMATCH` | 公式声明资格筛选前分母，canonical Partition/Observation 保留全部资格通过成员；差额逐一对应合法 Eligibility 排除，未发现丢写或查询漏成员 |
| 8 | `INSUFFICIENT_OBSERVATIONS` | 对应 canonical Context Partition 为空 |
| 1 | `INSUFFICIENT_OBSERVATIONS` | `ridge_current_context` 的 `MARKET_REGIME:NEGATIVE` 切片包含完整 127 个成员，但全部 metric input 为 NOT_ESTIMABLE；它不是空切片，也不是成员丢失 |

这定位了报告的分母与可估计性边界，不能据此定位 Alpha 的经济瓶颈。后续若修订研究协议，应在新版本中预先分开 sampled Universe、Eligibility 通过人口和 Outcome 可用性分母，并继续保存每个成员的去向。旧公式、Partition 和这 97 个结果不回写、不补零、不重标。

## 模型有什么已观察增量

比较前已核验相同 Sample/Feature/Target、fold-session、Candidate/Portfolio/Risk/Cost 绑定和逐指标公式身份。以下是保存的 aggregate canonical 指标的展示值，四舍五入至六位；精确 Decimal、Evaluation/Metric 身份与输入 roster 在证据包中。

| 实验臂 | Forecast RankIC | Bias | MAE | RMSE |
|---|---:|---:|---:|---:|
| `rule_current_context` | -0.037825 | 0.020174 | 0.026766 | 0.033132 |
| `ridge_current_context` | -0.037825 | 0.003510 | 0.017918 | 0.026515 |
| `rule_context_observational` | -0.079991 | 0.021671 | 0.027332 | 0.033620 |
| `ridge_context_observational` | -0.079991 | 0.005203 | 0.017675 | 0.026298 |

同一 Context 口径内，ridge 与 rule 的 Forecast RankIC 在**保存的完整 Decimal 精度上完全相同**，当前已观察样本没有显示该排序指标的增量。ridge 的上述 Bias/MAE/RMSE 数值较低，这是误差指标的描述性差异。它不证明模型优越、可交易经济增量或未来可重复性；两种 Context 口径之间也没有独立随机实验支持因果归因。

| FIT 用途 | 每个 ModelTrainingRun 的完整证券观测行 | 每项可估计行 | 每项独立交易日 | ModelTrainingRun / ModelVersion 数 |
|---|---:|---:|---:|---:|
| 较短 FIT | 640 | 640 | 20 | 2 / 2 |
| 较长 FIT | 1,085 | 1,084 | 34 | 2 / 2 |

共 4 个已完成训练及 4 个 ModelVersion。较长 FIT 的不可估计成员仍保留在训练分母中。跨模型、重叠 FIT 的观测行或天数不能相加为独立样本；证券观测行不是 episode 数。本活动的 V1 成员结果不能提供 V2 episode 分母或连续账户净值证据。

## 2026-09-08：旧 Ridge/rule 排序的精确向量核验

在上表同一 `COMPLETED_RECOVERY` 数据库 OID `117559774` 中，重新执行
只读、重复读取一致的模型/预测向量检查；未修改原库或恢复库，未重算
第二套 Evaluation。4 个拟合 Artifact 的实际 bytes、SHA256 和 size 均匹配
ModelVersion 引用。较短 FIT 的单特征标准化系数为 `0.001765549501`、
scale 为 `0.001910506736`；较长 FIT 分别为 `0.000662372967` 和
`0.001704827678`。系数与 scale 均为正，和同一单特征的规则排序同向。

40 个 Context/fold/session 比较组保留 1,268 对资格通过成员，包括
188 对共同可用预测和 1,080 对共同不可用预测；两臂可用性差异为 0。
对每个交易日实际保存向量的 428 次两两顺序及并列比较，差异为 0。
因此，旧活动中相同 RankIC 有正单调变换和实际排序一致的双重支持。
该结论限定于这些可用预测及其原 Signal/Context 筛选，不能推广为完整
Universe 的模型排序有效性。既有合法排除及 97 个不可估计结果保留。

增量原件 `existing-ridge-rule-order-proof.json` 属于 logical bundle
`daily-model-research-loop-20260907`，SHA256
`831af8d34f3d08cbdb0aa29b96c07b5209cef715efe4e1ba8d092d8f87dce561`。
新盘后协议采用完整预测人口及不同输入/Target，结果须按其自己的实际
Run/ModelVersion/Evaluation 判断，不能继承本段旧模型的结论。

## 下一步实验与 Daily Shadow 的依赖

1. 明确并授权唯一研究写入范围，完成真实 prospective 输入、窗口终态及恢复证据；完成恢复副本不替代这一步。启动和备份操作沿用 [Runtime Runbook](Runtime-Runbook.md)。
2. 新实验预先冻结分母语义和缺失处置；若要评价受支持的模拟经济性，显式采用已验收的 V2 独立出资、完整清算 episode 协议。此处只提出新版本边界，不修改或重新执行旧活动。
3. 每次 prospective Decision 显式绑定已完成 ModelVersion、Feature/Target、knowledge cutoff、generation 及实际 Outcome known-time。现有 retrospective fold 不能冒充每日前瞻预测。
4. 先验证数据新鲜度、全成员报告、Risk 拒绝/UNKNOWN 传播和独立恢复，再决定是否提出下一项研究假设；本报告不授权新模型、调参或模型准入。执行顺序仍由唯一 [Roadmap](../status/Roadmap.md) 管理。

`ALPHA_BOTTLENECK = NOT_DETERMINED`；`MODEL_SUPERIORITY = NOT_DETERMINED`。
`DAILY_MODEL_SELECTION_READINESS = BLOCKED_BY_PROSPECTIVE_INPUT_AND_EXPLICIT_DAILY_BINDING`。
`ALPHA_PROVEN = NO`；`PRODUCTION_ADMISSION = NO`。

## 可恢复原件与只读验证

通过 [R2 证据索引](../references/WP-ARCHITECTURE-REFOUNDATION-18Q-R2-Evidence.json) 定位 logical bundle `wp-research-operations-activation-01-20260907`，以下均为包内相对名称。物理根目录、连接配置和凭据不属于共享文档；索引存在不能代替原件可读取及哈希匹配。

| 相对原件名称 | SHA256 / 内容 |
|---|---|
| `research-funnel-diagnostics.json` | `6824fc6d11e17d6ac02466fc66f8d630405a3199e5f4da712abfed2f3b9e55cf`；完整成员、来源、Metric 和模型身份 |
| `research-funnel-diagnostics.md` | `8503b7f0bc5955f734525d329d760582a7325bad2fb0fb3f9f974656a6829ab0`；确定性明细投影 |
| `research-funnel-proof.json` | `a0f0b79cc27411c15f2c3344a76c9445d640cbe72e99c8287ee197c2d8d77211`；源文件哈希、重复投影、replay 和 192 表前后核验 |
| `research-funnel-performance.json` | `e535be15c36d4c59e1187c4512f8bb94be74b6a9acb2888e14e24e583cde7fd0`；真实活动查询计划与资源观测 |
| `funnel-subtask-ledger.json` | 执行命令、退出码、失败记录、测试日志及产物哈希 |

这次只读诊断重复生成的 JSON/Markdown bytes 相同，`matched=true / mismatch_count=0`，192 张表的行数和有序哈希前后不变，业务写入为 0。历史 canonical Report JSON 保持 SHA256 `c6ee9f51216693ece843a3e1578ac76e4a69e69ec6a19bf556e36c92eb406a88`，指定活动 replay 匹配。这证明本次读取及投影的完整性，不单独构成 WP-18Q 总退出、持续服务或 Alpha 资格。

## Daily field consumer correction

The first actual-time consumer collected and normalized all 32 daily inputs,
but its historical CSI300 membership observations were no longer effective.
Selection retained all 32 UNKNOWN members; none disappeared. Empty model
consumption failed before publication. That exact Run and plan were preserved,
its expired safe-effect Attempt was recovered through Runtime, and an explicit
failed Attempt terminalized the known defect. The old experimental use was
revoked. A new consumer identity adds actual-date membership Capture/Normalize
and explicit empty-population closure while reusing the same completed model.
This changes input readiness and consumer behavior, not the frozen baseline,
its fitted parameters or its observed Validation status.
