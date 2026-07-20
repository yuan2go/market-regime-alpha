# A 股量化选股、买卖点与手动交易研究程序

> **Status:** CURRENT RESEARCH PROGRAM  
> **Project:** `market-regime-alpha`  
> **Decision date:** 2026-07-20  
> **Primary objective:** 量化选股 + 买卖点识别 + 手动下单 + 每日复盘  
> **Explicit non-goal:** 当前阶段不实现自动下单、自动撤单、券商成交回报和无人值守实盘

---

## 1. 执行摘要

当前阶段正式收敛为：

> **程序负责发现机会、判断买卖时机、生成风险边界并进行复盘；用户负责最终决策和手动下单。**

近期主链路为：

```text
股票池 / ETF 池
        ↓
市场、行业、主题、资金环境
        ↓
股票 / ETF Candidate Ranking
        ↓
Entry Timing 买点判断
        ↓
人工观察与手动买入
        ↓
Position Lifecycle / Exit 卖点判断
        ↓
人工减仓或卖出
        ↓
每日推荐复盘与失败归因
        ↓
模型、规则和参数迭代
```

开发优先顺序冻结为：

```text
P0  推荐、决策快照与复盘数据合同
P1  股票池 / ETF 池 / 行业主题映射
P2  ETF、主题、资金和市场强弱
P3  股票 Candidate Ranking
P4  Entry Timing 买点模型
P5  Holding / Exit 卖点模型
P6  每日自动复盘与失败归因
P7  回测、滚动验证和模型迭代
```

以下模块暂停开发：

```text
真实 QMT / PTrade 委托
自动撤单与改单
券商成交回报
自动仓位同步
无人值守实盘
组合自动再平衡
执行算法
订单状态机
```

现有 `PaperBrokerAdapter`、`QMTAdapter`、`PTradeAdapter` 可以保留接口和安全占位，但不进入当前里程碑。

---

## 2. 当前工程事实

### 2.1 已有能力

当前工程已经具备或基本具备：

- Historical Trading Calendar；
- Historical PIT Universe Membership；
- Trading Eligibility；
- Candidate Population；
- 透明 Feature materialization；
- Close Return / MFE / MAE Target；
- B0 单因子排序；
- B1 透明复合排序；
- Cross-sectional rehearsal evaluation；
- Candidate positive-return directional diagnostic；
- Entry Path Target 的基础合同；
- 退神、缠论、均线、MACD、ATR、支撑压力等已有技术组件；
- FastAPI Dashboard、飞书推送和本地调度器基础；
- 手动买卖点参考能力。

### 2.2 尚未完成的核心能力

当前仍缺少：

- 正式股票池和 ETF 池日常生产；
- 行业、主题、ETF 的稳定映射；
- ETF / Theme / Capital Context；
- 面向每日使用的 Candidate Recommendation；
- Entry Gate / Entry Assessment；
- Canonical Position State；
- Holding / Exit Assessment；
- 推荐结果自动匹配；
- 失败原因分类；
- 每日、20 日、60 日滚动复盘；
- 对人工实际交易的记录和模型/人工偏差拆分。

### 2.3 当前结论

工程已经具备 Candidate Research 的基础设施，但还没有形成每日可运行的：

```text
选股 → 买点 → 持仓 → 卖点 → 复盘
```

完整闭环。

---

## 3. 目标与边界

## 3.1 策略目标

每天对 A 股股票和场内 ETF 进行筛选，输出：

- 值得关注的股票和 ETF；
- 推荐理由和主要风险；
- 当前是否适合买入；
- 买入观察区间、最高可接受价格和失效条件；
- 已持仓标的应继续持有、减仓还是退出；
- 前一日推荐是否按预期发展；
- 失败发生在股票池、主题、选股、买点、卖点、数据还是人工执行层。

系统不承诺确定性收益，也不直接控制真实账户。

## 3.2 适用市场

第一阶段适用于：

- 沪深 A 股普通股票；
- 场内宽基 ETF；
- 行业 ETF；
- 主题 ETF；
- 红利、低波和防守类 ETF。

暂不覆盖：

- 期货；
- 期权；
- 港股；
- 美股；
- 高频交易；
- 依赖逐笔 Level-2 的超短模型。

## 3.3 交易频率

主要研究频率：

```text
日线选股
+
14:30～14:55 决策快照
+
次日 10:30 / 14:45 / 收盘评价
```

短线模型和波段模型必须分开定义 Target、持有期限和风险参数。

---

## 4. 核心问题分解

四个问题必须分别建模：

| 模型 | 核心问题 | 输出 |
|---|---|---|
| Candidate Discovery | 买什么 | 股票 / ETF 排名 |
| Entry Timing | 为什么现在买 | `ENTER / WAIT_PULLBACK / WAIT_CONFIRMATION / REJECT` |
| Position Lifecycle | 已有持仓现在怎么办 | `HOLD / REDUCE / EXIT` |
| Review & Attribution | 推荐为什么成功或失败 | 分层结果与失败原因 |

治理原则：

> Candidate 高排名不等于当前必须买入；不适合新开仓也不等于已有仓位必须卖出；Exit 不是 Entry 的反向信号。

---

## 5. 决策与复盘数据合同

所有每日决策必须在产生时冻结，禁止事后覆盖。

## 5.1 `DailyResearchSnapshot`

记录决策时系统真实可见的信息：

```text
snapshot_id
decision_date
decision_time
market_context_id
universe_id
etf_universe_id
theme_mapping_version
feature_set_version
candidate_model_version
entry_model_version
exit_model_version
risk_policy_version
data_source_manifest
data_freshness
holding_snapshot_id
created_at
content_hash
```

要求：

- 内容寻址；
- 不可覆盖；
- 时间、时区明确；
- 数据源和模型版本完整；
- 能重建当日推荐。

## 5.2 `CandidateRecommendation`

```text
recommendation_id
snapshot_id
instrument_type
symbol
candidate_rank
candidate_score
score_components
industry_id
theme_ids
related_etf_ids
selection_reasons
risk_reasons
expected_horizon
expected_relative_strength
data_quality_grade
evidence_level
```

推荐理由必须来自结构化证据，不允许只保存自然语言结论。

## 5.3 `EntryAssessment`

```text
entry_assessment_id
recommendation_id
decision
entry_score
entry_price_zone
maximum_acceptable_price
invalidation_price
reference_stop_price
expected_mfe
expected_mae
expected_horizon
risk_reward_estimate
entry_reasons
rejection_reasons
```

`decision` 第一版固定为：

```text
ENTER
WAIT_PULLBACK
WAIT_CONFIRMATION
REJECT
```

## 5.4 `PositionSnapshot`

```text
position_snapshot_id
symbol
manual_trade_id
entry_date
entry_price
quantity
holding_age
current_price
current_return
mfe_since_entry
mae_since_entry
original_thesis
current_candidate_rank
current_theme_rank
invalidation_status
```

该对象记录用户手动交易后的研究状态，不代表券商权威账户。

## 5.5 `HoldingAssessment`

```text
holding_assessment_id
position_snapshot_id
decision
holding_score
thesis_status
theme_status
structure_status
risk_status
reference_reduce_zone
reference_exit_zone
invalidation_price
assessment_reasons
```

`decision` 第一版固定为：

```text
HOLD
REDUCE
EXIT
```

## 5.6 `ManualTradeRecord`

```text
manual_trade_id
recommendation_id
symbol
action
trade_date
trade_time
price
quantity
user_note
plan_followed
plan_deviation_reason
```

用途：

- 区分模型问题和人工执行问题；
- 记录是否追高、延迟、漏买或提前卖出；
- 不作为券商结算权威数据。

## 5.7 `RecommendationOutcome`

```text
outcome_id
recommendation_id
actual_open_return
actual_1030_return
actual_close_return
forward_3d_return
forward_5d_return
mfe
mae
entry_path_label
theme_relative_return
market_relative_return
tradability_result
manual_execution_result
failure_reason_codes
```

## 5.8 `DailyReviewReport`

必须同时输出：

- Candidate Review；
- ETF / Theme Review；
- Entry Review；
- Holding / Exit Review；
- Risk Review；
- Manual Execution Review；
- Data Quality Review；
- Failure Attribution；
- 20 日和 60 日滚动统计。

---

## 6. 股票池与 ETF 池

## 6.1 股票池

第一版可从高流动性股票开始，逐步扩展：

```text
沪深 300
中证 500
中证 1000 中满足流动性条件的股票
主要行业和主题龙头
用户自定义观察池
```

硬过滤：

```text
ST / *ST
停牌
上市不足 60 日
长期无成交
成交额不足
数据缺失
已知无法正常交易
异常价格或复权数据
```

每个被排除标的必须记录：

```text
exclusion_reason
policy_version
evidence_time
source
```

## 6.2 ETF 池

分层：

```text
宽基 ETF
行业 ETF
主题 ETF
红利 / 低波 ETF
黄金 / 债券等防守 ETF
```

ETF 过滤维度：

- 上市时间；
- 日均成交额；
- 基金规模；
- 跟踪标的；
- 同类 ETF 重复度；
- 折溢价异常；
- 流动性；
- 数据完整性。

同一指数建议保留：

```text
1 只主交易 ETF
1～2 只观察 ETF
```

ETF 和股票必须使用独立 Universe、Feature 和 Ranking，不允许混合排名。

---

## 7. 市场、ETF、主题和资金环境

## 7.1 市场环境

输出：

```text
RISK_ON
NEUTRAL
RISK_OFF
EXTREME_RISK
```

观察指标：

- 主要指数趋势；
- 全市场上涨比例；
- 涨跌停结构；
- 市场成交额；
- 高位股亏钱效应；
- 波动率；
- 主题扩散和退潮；
- 候选模型近期成功率。

必须区分：

```text
Market Observation
Model Performance State
Strategy Gate
Position Limit
```

不得把四者混成一个不可解释分数。

## 7.2 ETF 和主题强弱

第一版使用六组透明指标：

| 指标组 | 量化定义 |
|---|---|
| 相对强度 | 1/3/5/10/20 日相对沪深 300、中证全指收益 |
| 趋势 | 均线斜率、收盘位置、近期高点距离 |
| 宽度 | 成分股上涨比例、站上 MA5/MA10 比例、新高比例 |
| 成交活跃度 | 当前成交额相对 20 日中位数 |
| 龙头共振 | 龙头股排名、突破、成交量、持续性 |
| 持续性 | 强度连续天数、排名稳定性、衰减速度 |

主题状态第一版划分：

```text
ACCELERATING
EXPANDING
STABLE
DECAYING
RECEDING
```

## 7.3 资金流

证据分层：

### 较强证据

- ETF 份额变化；
- 融资余额变化；
- 可验证的北向或公开资金数据；
- 成交额和换手变化；
- 真实 Level-2 数据。

### 代理指标

- 公开接口的主力净流入；
- 大单、中单、小单算法分类；
- 主动买卖估计；
- 量价资金强弱。

所有公开算法资金流必须标记：

```text
CAPITAL_FLOW_PROXY
```

不能表述为真实机构买卖事实。

---

## 8. 股票 Candidate Ranking

## 8.1 目标

在可交易股票池内，对未来相对机会进行横截面排序。

## 8.2 特征组

### A. 个股相对强度

- 1/3/5/10/20 日收益；
- 相对沪深 300 超额收益；
- 相对行业指数超额收益；
- 相对主题 ETF 超额收益；
- 近期高点距离；
- 收盘位置。

### B. 行业与主题强度

- 所属主题排名；
- 主题 ETF 强度；
- 主题宽度；
- 龙头共振；
- 主题持续性；
- 主题退潮风险。

### C. 成交量与资金

- 成交额相对 20 日中位数；
- 换手率变化；
- 放量突破；
- 缩量回踩；
- ETF 份额变化；
- 融资余额变化；
- 资金流代理。

### D. 技术结构

- 均线方向与斜率；
- MACD 状态；
- ATR；
- 支撑压力；
- 突破与回踩；
- 缠论分型、笔和中枢；
- 一买、二买、三买；
- 背驰；
- 结构失效价格；
- 退神 G/Z/K/S；
- 买卖力比。

### E. 持续性

- 强度连续天数；
- 排名改善速度；
- 主题排名稳定性；
- 龙头持续性；
- 成交额持续性；
- 高开承接能力。

### F. 风险惩罚

- 短期涨幅过高；
- 偏离均线过大；
- ATR 过高；
- 连续涨停；
- 放量滞涨；
- 顶背驰；
- 主题拥挤；
- 数据质量不足。

## 8.3 第一版评分模型

```text
CandidateScore
=
IndividualStrength
+ ThemeStrength
+ CapitalStrength
+ StructureStrength
+ PersistenceStrength
- RiskPenalty
```

要求：

- 使用横截面 rank-percentile 或同类可解释归一化；
- 每个因子方向明确；
- 权重显式；
- 缺失数据拒绝或降级，禁止静默填充；
- 市场环境优先作为 Gate 或风险限制，不直接掩盖股票因子；
- 保留 B0 单因子比较器；
- B1 继续作为透明复合基线。

## 8.4 每日输出

ETF 层：

```text
强势 ETF Top 5
潜伏 ETF Top 5
转弱 ETF 列表
防守 ETF 状态
```

股票层：

```text
可执行候选 Top 5
重点观察候选 Top 10
备选候选 Top 20
完整 Candidate Population 排名
```

每只候选必须输出：

- 总分和排名；
- 各因子子分；
- 所属行业、主题和 ETF；
- 推荐理由；
- 主要风险；
- 数据质量；
- 预期周期；
- 当前 Entry Assessment。

---

## 9. Entry Timing 买点模型

## 9.1 输出状态

```text
ENTER
WAIT_PULLBACK
WAIT_CONFIRMATION
REJECT
```

## 9.2 `ENTER`

满足：

```text
Candidate 排名合格
AND 市场风险门未阻断
AND 主题未确认退潮
AND 个股结构有效
AND 当前价格未严重追高
AND 收益风险比满足最低要求
AND 数据新鲜完整
```

## 9.3 `WAIT_PULLBACK`

适用于：

- 股票和主题较强；
- 短期偏离过大；
- 当日涨幅过高；
- 接近压力区；
- 预计买入后 MAE 偏大；
- 等待缩量回踩更优。

必须输出：

```text
观察区间
支撑区间
最高可接受价格
结构失效价格
等待确认条件
```

## 9.4 `WAIT_CONFIRMATION`

适用于：

- 突破尚未确认；
- 成交量不足；
- 龙头和 ETF 尚未共振；
- 市场环境偏弱；
- 主题刚启动但宽度不足。

## 9.5 `REJECT`

适用于：

- 数据不完整；
- 结构失效；
- 主题退潮；
- 高位放量滞涨；
- 跌破关键支撑；
- 流动性不足；
- 收益风险比不足。

## 9.6 Entry Target

短线研究协议示例：

```text
Horizon: 1～3 个交易日
Upper Barrier: +3%
Lower Barrier: -2%
```

波段研究协议示例：

```text
Horizon: 5～10 个交易日
Upper Barrier: +6%
Lower Barrier: -3%
```

标签：

```text
UP_FIRST
DOWN_FIRST
TIMEOUT
```

以上阈值属于模型假设，必须版本化并通过回测验证，不能视为固定市场规律。

## 9.7 买点评价指标

- `UP_FIRST` 比例；
- `DOWN_FIRST` 比例；
- `TIMEOUT` 比例；
- 平均 MFE；
- 平均 MAE；
- MFE/MAE；
- 达到盈利阈值所需时间；
- 推荐后最大回撤；
- `ENTER`、`WAIT`、`REJECT` 各组效果差异。

核心验证要求：

```text
ENTER 组应优于 WAIT 组
WAIT 组应优于 REJECT 组
```

如果没有稳定分层，Entry Gate 不具备增量价值。

---

## 10. Position Lifecycle 与卖点模型

## 10.1 未持仓候选失效

输出：

```text
CONTINUE_WATCH
CANCEL_RECOMMENDATION
STRUCTURE_INVALIDATED
THEME_INVALIDATED
PRICE_TOO_EXTENDED
```

## 10.2 已持仓输出

第一版固定为：

```text
HOLD
REDUCE
EXIT
```

## 10.3 `HOLD`

- 原始推荐逻辑仍成立；
- 主题没有明显转弱；
- Candidate 排名未大幅下降；
- 技术结构未失效；
- 当前回撤在计划范围内。

## 10.4 `REDUCE`

- 主题仍强但个股开始落后；
- 上涨后量价背离；
- 盈利回吐超过阈值；
- 市场环境转弱；
- 风险收益比下降；
- 接近重要压力区。

## 10.5 `EXIT`

- 原始逻辑失效；
- 跌破失效价格；
- 主题确认退潮；
- 个股显著跑输主题；
- 出现顶背驰、三卖或中枢失效；
- 达到最大持有期限；
- 触发强制风控。

## 10.6 Exit Target

标签：

```text
CONTINUE_UP_FIRST
DRAWDOWN_FIRST
TIMEOUT
```

复盘指标：

- Post-Exit Regret；
- Avoided Drawdown；
- Late Exit；
- Profit Giveback；
- 卖出后继续上涨幅度；
- 卖出后最大回撤；
- 持仓机会成本。

---

## 11. 手动交易工作流

## 11.1 买入研究卡片

```text
标的
Candidate 排名
所属行业 / 主题 / ETF
当前 Entry 状态
总分和子分
推荐理由
主要风险
观察买入区间
最高可接受价格
结构失效价格
预期周期
```

## 11.2 持仓研究卡片

```text
标的
手动录入成本
当前收益
持仓天数
当前判断：HOLD / REDUCE / EXIT
原始逻辑状态
主题状态
Candidate 排名变化
MFE / MAE
失效价格
建议原因
```

## 11.3 用户手动录入

```text
是否买入
实际买入日期
实际买入时间
实际买入价格
实际买入数量
是否减仓 / 卖出
实际卖出价格
实际操作备注
是否遵循计划
偏离计划原因
```

系统不连接券商，也不自动生成真实委托。

---

## 12. 每日运行流程

## 12.1 交易日 14:30

- 更新股票池和 ETF 池；
- 更新行业和主题映射；
- 更新市场、ETF、主题和资金环境；
- 更新手动持仓状态。

## 12.2 交易日 14:45～14:55

- 生成 ETF 排名；
- 生成股票 Candidate 排名；
- 生成 Entry Assessment；
- 生成 Holding Assessment；
- 冻结 `DailyResearchSnapshot`；
- 输出 Dashboard 和飞书报告。

决策时间必须版本化，例如：

```text
DECISION_TIME_1450_V1
DECISION_TIME_1455_V1
```

不得静默改变已有 Target 的时间语义。

## 12.3 次日 10:30

- 记录隔夜和早盘结果；
- 计算实际 10:30 收益；
- 更新 MFE / MAE；
- 判断是否 `UP_FIRST / DOWN_FIRST / TIMEOUT`；
- 形成早盘复盘。

## 12.4 次日 14:45～收盘

- 更新持仓延续判断；
- 评估主题和 Candidate 排名变化；
- 判断 `HOLD / REDUCE / EXIT`；
- 收盘后生成完整 Daily Review。

---

## 13. 每日复盘与归因

## 13.1 “买什么”是否正确

比较：

```text
Top 5
Top 10
Top 20
完整 Candidate Population
主题中位数
行业中位数
市场基准
```

指标：

- Top-K 正收益率；
- Top-K 平均收益；
- Top-K 超额收益；
- Rank IC；
- Candidate 排名单调性；
- 推荐覆盖率；
- 排名稳定性。

核心要求：

```text
Top 1～5 > Top 6～10 > Top 11～20
```

若长期没有单调性，Candidate Ranking 需要重新设计。

## 13.2 主题判断是否正确

评价：

- 推荐主题次日排名；
- 主题宽度变化；
- 龙头是否继续；
- 成交额是否维持；
- ETF 是否跑赢市场；
- 是否一日游；
- 个股是否与主题共振。

## 13.3 买点是否正确

比较：

```text
ENTER
WAIT_PULLBACK
WAIT_CONFIRMATION
REJECT
```

指标：

- 次日收益；
- 3 日收益；
- 5 日收益；
- MFE；
- MAE；
- UP_FIRST 比例；
- DOWN_FIRST 比例；
- 盈利阈值到达时间。

## 13.4 卖点是否正确

评价：

- HOLD 后继续上涨；
- REDUCE 后是否避免回撤；
- EXIT 后是否继续大涨；
- 是否卖早；
- 是否卖迟；
- 是否发生盈利回吐；
- 是否因机会成本应当轮换。

## 13.5 风控是否正确

同时统计：

```text
避免的亏损
vs
错失的盈利
```

分类：

- 正确阻断；
- 错误阻断；
- 正确降风险；
- 过度降风险；
- 风险未识别；
- 数据问题阻断。

## 13.6 人工执行是否正确

区分：

```text
模型判断错误
人工没有遵循模型计划
人工执行优于模型计划
无法归因
```

---

## 14. 失败原因分类

一级分类固定为：

```text
DATA_QUALITY_ERROR
UNIVERSE_ERROR
MARKET_REGIME_ERROR
ETF_THEME_ERROR
CANDIDATE_RANKING_ERROR
ENTRY_TIMING_ERROR
HOLDING_DECISION_ERROR
EXIT_TIMING_ERROR
CAPITAL_FLOW_SIGNAL_ERROR
TECHNICAL_STRUCTURE_ERROR
RISK_POLICY_ERROR
HUMAN_EXECUTION_ERROR
TARGET_DEFINITION_ERROR
UNEXPLAINED_MARKET_NOISE
```

允许一条推荐同时拥有多个原因。

### 示例一：选股有效，买点过早

```text
股票 3 日后上涨 8%
但推荐次日先跌 4%
```

归因：

```text
Candidate Ranking 有效
Entry Timing 错误
```

### 示例二：主题有效，个股选择失败

```text
主题 ETF 上涨 4%
推荐股票下跌 2%
```

归因：

```text
ETF_THEME 有效
CANDIDATE_RANKING_ERROR
```

### 示例三：模型有效，人工追高

```text
模型给出 WAIT_PULLBACK
用户实际追高买入
随后正常回踩
```

归因：

```text
Entry Timing 有效
HUMAN_EXECUTION_ERROR
```

---

## 15. 仓位与风险管理

虽然当前不自动下单，但系统仍需给出研究风险边界。

第一版风险规则：

- 单票最大建议仓位；
- 单主题最大建议仓位；
- 股票和 ETF 总风险预算；
- 单日新增风险暴露上限；
- 现金保留比例；
- 最大计划亏损；
- 连续失败后降级；
- 数据过期禁止推荐；
- 涨跌停和停牌门控；
- T+1 可卖约束；
- 同主题高相关性限制。

风险模型输出：

```text
ALLOW
REDUCE_RISK
BLOCK
```

风险输出只能影响 Entry/Holding 建议和建议仓位，不应静默修改 Candidate 原始排名。

---

## 16. 回测与验证要求

## 16.1 Candidate 验证

- 保留完整 Candidate Population；
- 使用时间切分；
- 计算 Rank IC；
- 验证 Top-K 单调性；
- 验证不同行情、主题和波动环境；
- 进行成本前和成本后评估；
- 保留 B0 最低比较器。

## 16.2 Entry 验证

- 使用 Path-Dependent Target；
- 分别统计 `ENTER / WAIT / REJECT`；
- 验证是否降低 MAE；
- 验证是否保留足够的有效上涨机会；
- 分析不同阈值和周期稳定性；
- 禁止使用未来数据。

## 16.3 Exit 验证

- 验证是否减少 Profit Giveback；
- 验证是否降低重大回撤；
- 统计 Post-Exit Regret；
- 分析卖早和卖迟；
- 区分主题退潮、个股失效和市场风险。

## 16.4 每日滚动验证

必须提供：

```text
当日
5 日
20 日
60 日
```

滚动指标，并对模型版本切换建立明确分界。

---

## 17. 实盘观察方式

当前实盘方式为：

```text
模型生成研究建议
→ 用户阅读研究卡片
→ 用户手动下单
→ 用户录入实际交易
→ 系统匹配行情结果
→ 系统拆分模型与人工执行偏差
```

系统输出属于交易研究和决策辅助，不构成收益保证。

所有最新行情、价格、政策、主题、指数、分红、ETF 规模、资金流和数据费用必须在使用时实时核验。

---

## 18. 工作包

## WP-DQS-0：决策快照和复盘合同

实现：

```text
DailyResearchSnapshot
CandidateRecommendation
EntryAssessment
PositionSnapshot
HoldingAssessment
ManualTradeRecord
RecommendationOutcome
DailyReviewReport
```

验收：

- 不可覆盖；
- 内容哈希；
- 数据、模型和配置身份完整；
- 能重建每日推荐；
- 推荐生成后禁止修改历史证据。

## WP-DQS-1：股票池与 ETF 池

实现：

- 股票 Universe；
- ETF Universe；
- 行业、主题和 ETF 映射；
- 可交易性过滤；
- 数据完整度报告；
- 每日新增、退出和排除原因。

## WP-DQS-2：市场、ETF、主题和资金环境

实现：

- 市场状态；
- ETF 相对强度；
- 主题宽度；
- 龙头共振；
- 成交额变化；
- 主题持续性；
- 资金流代理分层；
- 主题退潮识别。

## WP-DQS-3：股票 Candidate Ranking

实现：

- 复用 B0 / B1；
- 增加主题和 ETF Context；
- 增加成交量和资金特征；
- 增加技术结构；
- 增加持续性；
- 增加风险惩罚；
- 输出 Top 5 / Top 10 / Top 20 和完整排名。

## WP-DQS-4：Entry Timing

实现：

```text
ENTER
WAIT_PULLBACK
WAIT_CONFIRMATION
REJECT
```

并输出：

- 买入观察区间；
- 最高可接受价格；
- 失效价格；
- 预期周期；
- 预期 MFE / MAE；
- 风险收益比；
- Entry Path Target。

## WP-DQS-5：Holding / Exit

实现：

```text
HOLD
REDUCE
EXIT
```

并建立：

- Position State；
- 原始逻辑；
- 排名变化；
- 主题状态；
- MFE / MAE；
- Exit Target；
- 卖早、卖迟和盈利回吐诊断。

## WP-DQS-6：每日复盘与归因

实现：

- Candidate Review；
- ETF / Theme Review；
- Entry Review；
- Holding / Exit Review；
- Risk Review；
- Manual Execution Review；
- Failure Attribution；
- 20 日和 60 日滚动统计。

## WP-DQS-7：回测与模型迭代

实现：

- 时间序列回测；
- 样本外验证；
- 参数敏感性；
- 市场环境分层；
- 模型版本对比；
- 失败案例集；
- 规则调整前后对照。

---

## 19. 暂停项

以下工作不进入当前路线：

```text
真实 Order Proposal
券商 Broker Adapter 实现
QMT 自动委托
PTrade 自动委托
自动成交回报
自动仓位同步
自动撤单与改单
无人值守交易
Portfolio Auto-Rebalance
Execution Algorithm
```

后续只有在 Candidate、Entry 和 Exit 均通过持续验证后，才重新评估自动执行。

---

## 20. 成功标准

第一阶段完成不以“自动下单”为标准，而以以下结果为标准：

1. 每天稳定生成可解释的股票和 ETF 候选；
2. 推荐记录可以无后见偏差地完整复现；
3. Top-K 排名存在稳定的收益或胜率单调性；
4. Entry Gate 能够降低买入后 MAE；
5. Holding / Exit 能够减少盈利回吐和重大回撤；
6. 每次失败能够定位到股票池、市场、主题、Candidate、Entry、Exit、数据、风险或人工执行；
7. 模型改动必须经过历史回测和每日滚动复盘；
8. 用户能够依据研究卡片完成手动交易，并记录实际执行结果。

---

## 21. 失效条件

出现以下情况时，应暂停扩大实盘使用并回到研究阶段：

- Top-K 长期无法产生相对收益；
- Candidate 排名无单调性；
- Entry Gate 无法降低 MAE；
- `ENTER` 不优于 `WAIT` 或 `REJECT`；
- Exit 规则长期产生严重 Post-Exit Regret；
- 收益在交易成本后消失；
- 效果集中于极少数日期或单一主题；
- 主题和资金因子无法提供增量价值；
- 数据质量不足以支持决策时间语义；
- 人工执行偏差无法可靠记录；
- 模型版本变更无法复现。

---

## 22. 复盘方式

复盘分为四层：

```text
每日逐条推荐复盘
每周错误类型汇总
20 日滚动模型评估
60 日稳定性和失效检查
```

每次模型调整必须记录：

```text
变更原因
假设
修改内容
预期改善指标
回测结果
样本外结果
实盘观察结果
是否保留
```

禁止仅根据单日盈亏调整权重或规则。

---

## 23. 最终定位

本阶段工程正式定位为：

> **A 股量化研究与手动交易决策辅助系统。**

它的核心能力不是自动下单，而是：

```text
量化发现机会
+
量化判断买点
+
量化判断持有与卖点
+
人工完成最终交易
+
每日验证模型是否按预期工作
```
