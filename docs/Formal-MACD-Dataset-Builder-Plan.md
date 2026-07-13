# 正式 MACD 候选数据构建器计划（Task 11A.6）

状态：**数据适配与构建计划，未构建正式数据集，未访问 sealed test。**

## 责任边界与适配器

| Adapter | 输入责任 | 输出/失败规则 |
| --- | --- | --- |
| `TencentMinuteAdapter` | 读取原始腾讯分钟标签 | 显式把 start-label 转为 interval-end；不能确认的标签报 `BAR_TIMESTAMP_SEMANTICS_UNKNOWN`。MACD 层不猜测。 |
| `FinalizationAdapter` | 来源/导入流程证明 bar 已收盘 | 写入 `bar_final=true` 和来源证据；CSV 缺字段或未知为失败，不能默认 true。 |
| `PITAdjustmentAdapter` | 公司行为与当时可得调整因子 | 输出 raw execution price 与 `POINT_IN_TIME_ADJUSTED` feature price；缺因子/无效公司行为/非正调整价失败。 |
| `PITUniverseAdapter` | 逐日可得成分、上市状态与可交易资格 | 输出 `eligible`，禁止用当日 universe 回填历史。 |
| `EligibilityAdapter` | 停牌、ST、10%/20%/30% 涨跌停制度、前收 | 输出 `is_suspended,is_st,prev_close,limit_up_price,limit_down_price,limit_regime`；缺失不填前值。 |
| `MarketSidecarAdapter` | 指数、行业、主题、regime 与 as-of 分类 | 同频率、同日历、PIT 精确对齐；过期/缺失记录原因。 |

## 构建步骤

1. 固定 20–50 个 A 股/ETF 和不少于两年的候选范围，但由 `PITUniverseAdapter` 在每个
   `as_of_date` 决定实际可用标的。
2. 导入原始 5 分钟成交、日线、公司行为、交易日历、行业/主题/指数 sidecar；写入每个
   原始文件 SHA-256、来源、覆盖时间、字段表与下载时间。
3. 规范化为 interval-end timestamp，验证只保留已收盘 bar；午休、隔夜、节假日和停牌
   不插入伪造 bar。正常应有而缺失的 5 分钟 bar 进入质量报告。
4. 生成 feature price（PIT adjusted close）和 execution price（同一时点 raw open），
   将两个字段、`price_adjustment_mode` 和 corporate-action as-of 全部写入 manifest。
5. 计算区间及当日 VWAP：优先源端累计成交额/累计量；若仅区间数据，适配器只在可复算时
   生成。close 不能替代 VWAP。
6. join 交易资格、PIT universe、市场/行业/主题 sidecar；禁止 as-of 向后填充。随后执行
   duplicate、bar final、OHLC 正数、成交额/量、日历、复权和 reference 对齐质量门禁。
7. 输出不可变 dataset manifest、quality report、symbol holdout 和 chronological split
   manifest。通过 gate 后，才可成为 train/validation/rehearsal 的真实候选输入；此计划不
   启动 sealed test。

## 频率、字段与口径

- 正式策略 MACD：`bar_interval=5m`、`closed_bars_only=true`；日线只作为单独 pipeline
  和独立 identity，不能与 5m 共用 MACD 配置/缓存。
- bar：`symbol,timestamp,open,high,low,close,volume,amount,vwap,bar_final,source_freq`。
- 审计/执行：`prev_close,is_suspended,is_st,limit_up_price,limit_down_price,limit_regime`。
- reference：候选显式携带 `benchmark_symbol,industry_id,industry_as_of`；reference 数据
  只能按同频率、同交易日历与精确 timestamp/as-of 匹配，不取任意最后一行。
- 日线 horizon 依交易日历的第 N 个后续交易日，选该日最后有效已收盘 bar；缺失时为
  `HORIZON_BAR_MISSING`，绝不以 `48*N` 代替。

## 涨跌停、停牌与交易资格

- A 股默认 10%，创业板/科创板 20%，北交所 30%，ST 5%；实际 `limit_regime` 优先于代码
  推断，并把规则版本写入 manifest。
- 停牌、涨停买入、跌停卖出、T+1 锁定、现金不足、最小手数、核心仓位下限和 reverse-T
  权限都由共享 `a-share-execution-v1` 解析器处理。标签、反事实和回测不得各自复制。

## 质量报告与 Manifest

质量报告至少列出每 symbol/date 的 expected/actual bars、缺失原因、重复、provisional、
复权异常、sidecar 缺失、日历外 timestamp、涨跌停/停牌计数与 rejected rows。任何阻断项
非零即不能标记为 `FORMAL_FINAL_CANDIDATE`。

dataset manifest 至少记录所有原始/派生文件 hash、数据源、symbol 数、时间范围、bar 数、
复权和日历版本、质量统计、PIT universe version、sidecar versions、`bar_interval` 与
`closed_bars_only`。它进入 `dataset_manifest_hash`；split manifest 独立产生
`data_split_hash`。

## 切分

- chronological：明确连续 `train -> validation -> rehearsal -> sealed test`，每段边界由
  完整交易日定义，所有特征仅使用当时可得数据。
- symbol holdout：PIT universe 中选取未参与阈值/校准选择的一组标的；固定选择种子、规则
  和结果 hash。
- 训练、校准和 rehearsal 可以迭代；sealed test 在 runner/readiness 全部冻结前不读取，并且
  只允许一次不可覆盖 run。

## 当前结论

当前仓库尚无能够同时提供可信 finalized 5m、PIT adjustment、PIT universe、交易资格和
sidecar 的正式适配数据。因此**不具备真实 train/validation/rehearsal 建设条件**；现有
fixture rehearsal 只验证执行与归因管道，不能作为买卖点或 MACD 有效性证据。

## Task 11A.10 MVP（research-only）

`formal_dataset_builder.py` 实现了一个故意收紧的 `REHEARSAL` Builder：只接受 5–10 个标的、
3–6 个自然月、`POINT_IN_TIME_ADJUSTED`、完整 `bar_final`、`vwap`、日历 session-close、
PIT universe、交易资格和市场/行业 sidecar 的输入。它产出内容寻址 Manifest 与不可覆盖的
`manifest.json/quality.json/REHEARSAL_ONLY` artifact；它不支持 sealed-test 选择，也不会拉取、
猜测或修复源数据。

受控 fixture 已验证所有 adapter 输入、sidecar coverage、质量 gate 与 artifact 不覆盖。现有
`data/raw` CSV/Parquet 会因缺少 `bar_final`（以及后续 PIT/sidecar）明确被拒绝，故 MVP 证明
的是构建器和门禁，不是正式市场数据可用性。真实 train/validation/rehearsal 仍依赖
`Formal-Data-Source-Capability-Audit.md` 中列明的外部数据前置项。
