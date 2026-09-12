# WP-HISTORICAL-RESEARCH-CAMPAIGN-01

本包开发、真实历史研究、报告及隔离恢复验证已完成。本文只使用真实历史研究结果，工程测试与研究绩效分别记账。

## 结论

当前 Ridge **没有证明稳定优于简单基线**。它在四个观察窗口的 MAE 都优于冻结规则，却都劣于零预测；开发期总体和留出期也劣于训练标签均值。单特征 Ridge 的排序每天都与原因子正向或反向严格等价，误差收缩不构成新的排序信息。Ridge v1/v2 的数值差异约为 1e-14 量级，排序一致，数值工件语义改进不等于模型改进。

动量组是十三个扩展候选中按预注册共同样本 MAE 入选的唯一方案。它相对原 Ridge 的 MAE 改善很小：开发期约 0.00000452，留出约 0.00002960，仍未超过零和均值基线。留出日均 Rank IC 为 0.0844，高于 Ridge/反向因子的 0.0458，构成有限的后续验证线索；只有十天、两个有效五日块，不能形成稳定增量或显著性结论。

| 同一共同样本上的方案 | 开发期 MAE，922 对 / 30 天 | 留出 MAE，320 对 / 10 天 | 开发期日均 IC | 留出日均 IC |
|---|---:|---:|---:|---:|
| 零预测 | 0.014726 | 0.011141 | NOT_ESTIMABLE | NOT_ESTIMABLE |
| FIT 标签均值 | 0.015268 | 0.011100 | NOT_ESTIMABLE | NOT_ESTIMABLE |
| 冻结规则 | 0.015801 | 0.012672 | -0.0630 | -0.0458 |
| 当前 Ridge v2 规格 | 0.015343 | 0.011213 | 0.0510 | 0.0458 |
| Ridge 加动量组 | 0.015338 | 0.011184 | 0.0551 | 0.0844 |

表中数值是收益标签的无量纲预测误差和相关诊断，不是可交易收益。完整 Bias、MAE、RMSE、方向、分布、覆盖、逐日/折/月、配对差值和精确 lineage 在下列 canonical 报告中。

## 报告与证据入口

- [开发期完整 20 配置对照、消融与证券集中度](historical-matrix-01/analysis.md)；[逐月诊断](historical-matrix-01/monthly-diagnostics.md)；[原始 canonical 比较](historical-matrix-01/comparison.json)。
- [冻结候选留出报告、分布、月份与全部模型身份](historical-selected-holdout-01/analysis.md)；[原始 canonical 比较](historical-selected-holdout-01/comparison.json)。
- [冻结协议、数据/特征公式、窗口、预算与经济边界](historical-campaign-context-01.md)；[完整数据质量摘要](history-data-01/data-summary-v1.json)；[owner 清单](history-data-01/inventory-v2.json)。
- [全部主试验/留出配置、折、模型和先前尝试索引](../records/historical-trial-roster-final.json)；[选择及首次开放的完整事实](../records/historical-holdout-01-frozen-access-index.json)。
- [可直接使用的执行、恢复、比较、回放、lineage 与恢复命令](reproduce-historical-campaign-01.md)。

这些报告来自已对账的 Outcome/Evaluation/Model/Backtest 工件。证券敏感性是对其已有绝对误差和作事后减法，单独标注，不改标签、不改主要排除规则、不重新选择。

## 数据与实际验证总体

97 次免费 BaoStock 请求实际采集 2022–2025 年、32 个固定证券、969 个真实交易日。RAW 与 BACKWARD_ADJUSTED 分开，共 60,398 条 bar revision；每种价格口径实有 30,199 / 应有 31,008 个证券日槽位，缺失 802、无效 OHLC 7。SourceGap 中另有 Instrument/行情等事实种类，不能重复相加扩大缺失分母。

封存 Archive `44d0020a-04d7-5954-b9db-f64de8840eaf`，Seal `77f31d6a-f2db-4393-91ae-bde57b51412b`。真实归档知识截止为 2026-09-12 08:46:37.888978 UTC。上市、证券状态和采集知识时间都保留真实 2026 年时间，没有倒填到模拟决策日。

本轮是 STATIC_UNIVERSE / SURVIVORSHIP_LIMITED / EXPLORATORY_RETROSPECTIVE，不是正式 PIT。四年行情覆盖不等于四年连续回测：主矩阵为 2022/2023/2024 三段各十天 FIT、十天验证；留出为 2025 年十天 FIT、十天验证，窗口都集中在 6–7 月。purge 与 embargo 使用真实 Calendar；下一交易日标签成熟先于后续验证。原始价格早已可访问，留出保护是 canonical 标签访问控制，不宣称正式盲测或 LOCKED_OOS。

开发期完整分母 960，标签可用 930，全方案共同可估计 922。30 个预候选缺口对应固定名单证券的上市年龄/证券状态证据不足；8 个新增特征缺口来自 688472.XSHG 的窗口不完整。缺失没有被当成未上市事实、零值或坏日期删除。留出完整/标签/预测/共同分母均为 320。

## 实验与解释

先完成真实小样本 pilot（7 方案、2 FIT / 2 验证日），随后完成两段小窗口的十特征工程预跑，才冻结主矩阵。早期失败和已查看预跑结果全部保留，不把预跑当作未见留出。

主矩阵 Run `7b2f292c-3334-5c86-916b-7f950a61da4d`：20 套配置，3 段窗口，57 个新折内模型，3,797 个动作，140 个 Evaluation。留出 Run `67794a06-8f16-5732-ace1-de8b00aa4f13`：7 个对照加唯一入选动量组，7 个新模型，511 个动作，24 个 Evaluation。全部完成，报告回放无不一致。参数只在 alpha 0.1 / 1 / 10 的既定范围比较；加入/移除五个特征组，未进行无界搜索。保留原在线模型和全部前瞻协议。

原 Ridge 的开发期 IC 按窗口为 +0.1856、-0.0180、-0.0145，正总体均值主要来自 2022 窗口。动量组为 +0.1501、+0.1014、-0.0863；2025 留出均值为 +0.0844。留出改善集中在八个六月日期；两个七月日期的动量 IC 低于 Ridge。年间差异不能解释为已验证的市场状态因果关系。

开发期动量误差改善很容易受个别证券影响：全部绝对误差和的净改善约 0.00417，而仅 688472.XSHG 的改善约 0.03351；去掉这一个证券，净差值会变坏。这是保留全部样本的事后敏感性检查。留出改善较多的证券包括 688036.XSHG、600438.XSHG、688472.XSHG、600588.XSHG；变差包括 601601.XSHG、688396.XSHG、603296.XSHG、601857.XSHG。证券作用与开发期并不稳定。

完整十特征 alpha-1 模型开发期 MAE 0.019524，数值高于简单误差基线。提高 alpha 到 10 将其 MAE 缩至 0.017635，但平均 IC 仍为负。对该完整模型移除任一组都改善误差。本轮证据不支持推广完整特征堆叠，也不支持继续盲目扫描单特征 alpha。

下一轮最有信息增益的工作是：保留少量对照和动量假设，预注册更长训练窗口与跨月份时间验证；优先补真实历史成员、复权/公司行动和源间一致性证据。已经访问的留出不能继续用于挑选参数，必须使用新实验和新的验证安排。上述只是后续方向，没有在本包追加试验或付费调用。

## 已实现能力与接线

复用现有 `mra` / bootstrap / Runtime 和 Market、Capture、Archive、Feature、Dataset、Model、Backtest、Partition、Outcome、Evaluation、Artifact owner，完成真实有界采集/断点恢复、静态研究总体、质量清单、十个共享纯计算特征、折内预处理和模型特征子集、有限矩阵、受保护留出、完整配对比较及持久化报告。未增加第二套 scheduler、runner 或账本。

真实入口包括 `research prepare-history-data`、既有 Archive 采集/封存、`research history-inventory`、`research prepare-historical`、`backtest run/resume/progress/publish-report/replay`、`research history-compare`、`research holdout-reserve/select/open/inspect`、`research daily lineage`、`evidence backup/fresh-restore/restore-check`。完整参数见上面的复现手册及仓库 Runtime Runbook。

新增前向迁移 005–008 分别绑定静态研究总体、显式多价格口径历史清单、冻结模型特征子集和留出保留/开放事实。只升级授权的独立研究及 disposable 范围；原运营库未升级。基线中 232 个受保护文件字节保持一致；历史 SQL、协议和既有工件未改写。

## 验证、性能和恢复

[工程阶段索引](../records/engineering-verification-09-final.json)保留早期状态；[最终模型边界组](../records/model-numeric-boundaries-final-09.json) 24 PASS / 0 FAIL / 0 SKIP。相关共享 owner PostgreSQL 组 28 PASS，schema/注册升级组 11 PASS，相邻 owner 单元组 60 PASS，专业录制契约单元组 17 PASS；这些是分别执行、部分重叠的组，不能合并为不重复总数。特征、归一化、恢复、子集、Backtest、未来标签和留出拒绝的此前组详见各 checkpoint 索引。

首次失败包括真实 pilot 的静态总体能力误判、归一化/测试 Capture 绑定遗漏、空总体 Outcome/Model Forecast 对账边界、新迁移注册/RESTRICT 问题及若干 fixture/schema 不匹配；修复及原日志均保留。升级预检首次拒绝相对备份路径；失效计划未应用，重新生成后在有效期内执行。lineage 的一次错误 CLI 命名空间调用被拒绝，改用 `mra research daily lineage` 成功。最终仓库检查还发现当前 schema 事实段仍写 194 张表，已按可执行契约修正为 196；首次失败及重跑通过日志分别保存。没有通过 skip、吞异常、弱化断言或改写历史结果过关。

使用 Python 3.12.2、冻结 uv.lock、PostgreSQL 16.15 和独立 wheel。mypy 681 个文件、ruff、文档链接、仓库清单及独立 CLI 检查通过；全仓库长回归 NOT_RUN，采用受影响 owner 的必要回归。无真实外发、交易、付费 Provider、安装切换或原环境服务停启。

主矩阵执行 15,789.91 秒，留出执行 2,025.46 秒；共 4,308 动作 / 17,815.37 秒，符合冻结的 5,000 动作 / 21,600 秒预算。采集、工程测试、对账报告和恢复另外记账。实际 inventory 从 12.88 秒 / 698 MB 降至 3.05 秒 / 187 MB，身份不变。主运行末次峰值约 628 MB，完整比较约 725 MB；研究库在完成留出时约 3.96 GB。共享主机和完整对账成本均有记录，不是孤立容量基准。

实际 fresh restore 已通过：将 491,973,099 字节 dump 和 2,114 个工件（3,104,743,422 字节）恢复到第三个 pristine disposable 数据库及新 root，核验全部 196 张表、3 个 Archive 和 6 个 Backtest 的完整性。5 个 Backtest 完成回放通过；原失败 pilot 仍为 FAILED。备份耗时 302.74 秒，完整恢复核验 895.81 秒。

只在恢复副本移走一个拟合工件后，现有 `evidence verify` 以退出码 2 准确拒绝 `ARTIFACT_BYTES_MISSING`。恢复确切原字节后主矩阵回放匹配，已完成留出再次 `resume` 的尝试动作数为 0。最后全部 196 张表内容哈希与备份一致，2,114 个物理工件再次核验一致。恢复副本没有被选作运营写者。详见[恢复索引](../records/historical-campaign-fresh-restore-index-09.json)、[缺失拒绝](../records/historical-restore-missing-artifact-result-09.json)、[零业务写核验](../records/historical-restored-zero-business-writes-09.json)。

## 同模型证据链与验收边界

动量 ModelVersion `3924eb4a-b7cd-5741-bc65-d90b93f6f444` 的真实 owner 追溯通过：FIT Evaluation `8db751a6-35d9-59bb-be7e-ee00ad38d837` → TrainingRun `697a0c31-7663-5bb2-aa07-9141b1361658` → fitted Artifact `8da7c0ab-db70-4dfd-9df0-018aa4cba953` → 主 Backtest 和已发布报告。全体 Forecast/OutcomeRevision/Evaluation 输入 roster 在 canonical 比较中。首个后续条件 `NO_EXPERIMENTAL_MODEL_USE` 是本轮独立历史模型的预期边界，不是历史链断裂；没有为研究结果新增在线 Use。

| 验收项 | 判定 |
|---|---|
| ENGINEERING_VERIFICATION | PASS：定向回归、独立 wheel、实际 fresh restore、缺失拒绝与零业务写回放 |
| REAL_HISTORICAL_EXECUTION | PASS：真实采集、训练、基线、消融、留出和报告链已执行 |
| TEMPORAL_VALIDATION | PASS，仅探索性时间隔离；正式 PIT / LOCKED_OOS 未成立 |
| MODEL_INCREMENTAL_VALUE | NOT_ESTABLISHED：当前 Ridge 未优于简单误差基线；动量仅有限线索 |
| ECONOMIC_VALIDITY | NOT_ESTIMABLE |
| PROFESSIONAL_PROVIDER_READINESS | 版本化契约与本地录制/owner CLI PASS；真实 Provider NOT_RUN |

经济性首个阻塞是缺经过验证的成交/可售库存/费用滑点/容量与连续资金持仓估值路径；本包不建设 OMS，也不注入默认费用或生成 NAV、年化、实盘夏普。专业数据首个阻塞是缺授权真实样本和可核验的单位、复权、成员、可获知时间、finality、权限、历史覆盖、延迟、费用及使用限制。本地录制契约可执行；它不构成专业源完整标准化或正式 PIT 资格。

[实际命令与作用范围索引](../records/historical-delivery-command-index-09.json)保留本轮主要执行入口和日志；各早期 checkpoint 保留首次失败及重跑。

## 修订与工作区

Baseline `origin/main`: `2e5474342ec14b2dc74704cfa9ef981ffcfec870`。
主矩阵 implementation: `e7c9d42d36cbc97ad56e64bf0231031f552c6ff9`。
最终可执行 implementation / 留出 wheel source: `81f1ce47508c30e25f9e7dfe104ac2bf77641375`。
留出 wheel SHA-256: `49df336cf609bdc2986882a365b0c2e263869073d710a5bf19b3a549727bca2f`。
Final documentation revision: `4934e87a436595c3e61c070c486633e946672f2f`。独立工作树干净；该提交只改当前文档，可执行源码仍为 implementation 81f1ce47508c30e25f9e7dfe104ac2bf77641375。

独立分支 `agent/wp-historical-research-campaign-01`；不 push、不创建 PR、不合并。原工作区无关改动和 `.idea/modules.xml` 保留。凭证、个人配置、原始行情和数据库 dump 没有提交 Git。所有验证包、原始命令日志、协议、报告与恢复记录保存在持久研究目录。最终 [SHA/哈希/状态索引](../records/final-delivery-index.json) 和 [文件哈希清单](../records/final-evidence-manifest.json) 可核验交付。
