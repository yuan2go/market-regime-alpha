# 正式数据源能力审计（Task 11A.9）

状态：**能力审计完成；没有任何当前免费/缓存数据源被批准为正式 MACD 数据集主源。**

本审计区分“接口能返回行情”与“可以证明正式研究所需的 point-in-time（PIT）语义”。后者
要求可追溯的历史文件、明确的 interval-end 时间戳、收盘资格、PIT 复权、PIT universe、
停牌/ST/涨跌停、行业/主题历史和授权记录。缺任一项即只能用于研究原型，不能进入
`FORMAL_FINAL_CANDIDATE`，更不能读取 sealed test。

## 能力矩阵

| 来源/适配器 | 5m 历史深度 | 时间戳/收盘证明 | PIT 复权 | PIT universe/交易资格 | 历史行业/指数 ETF | 授权与成本 | 审计结论 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 现有 Tencent cache | 当前会话及本地缓存；本地 1–2 年 CSV/Parquet | 腾讯起始标签语义未由导入层证明；缓存无 `bar_final` | 无 | 无完整 sidecar | 仅另行拼接 | 非正式公开接口，无 SLA | **拒绝**正式集；可作本地 exploratory source |
| EastMoney/AKShare | 文档明确部分分钟接口只返回近期数据 | 没有本项目可验证 finalization 证据 | 无 PIT 证明 | 不完整 | 指数可取但行业历史不完整 | 抓取型/第三方库 | **拒绝**正式主源 |
| BaoStock | 项目可拉取 5m 历史回补 | 历史接口不等于收盘资格；需导入证据 | 不提供本项目所需的分钟 PIT 复权链 | 不完整 | 不完整 | 免费 SDK，无研究数据授权证明 | **拒绝**正式主源；仅历史回补 |
| Tushare Pro | `stk_mins` 支持分钟频率，权限取决于账户 | API timestamp 可规范化，但仍须 adapter 写入 interval-end/finalized evidence | 官方说明的 `pro_bar` 复权以日线为主；不能据此宣称分钟 PIT 复权 | 可提供部分日历/证券基础资料，尚未证明 PIT 版本 | 可作为指数/ETF/行业辅助候选，具体权限另验 | 账户积分/单独分钟权限 | **条件辅助源**，未获主源批准 |
| QMT/PTrade/券商归档（待接入） | 取决于账户合约 | 若提供历史归档与 session-close metadata，可满足 | 需企业行为/PIT 数据补齐 | 需单独 sidecar | 可作价格主源，非全部 sidecar 源 | 需核验账户协议 | **主源候选，尚未验收** |
| 商业 PIT 数据供应商（待采购） | 合约确认后可覆盖 | 应在合同/数据字典中保证 | 需要日内可用 PIT 因子 | 应提供或可拼接有版本侧表 | 需要明确 as-of 历史分类/指数 | 需采购及许可审查 | **推荐主源类别，尚未选型** |

“不完整”表示本仓库没有受控、可哈希且可按 `as_of` 验证的导入物；它不是由 MACD 或
Dataset Builder 推断后补齐的字段。

## 本地实测结论

已检查的 `data/raw/dividend_t_5min_1y/*.csv` 与
`data/raw/top1000_largecap_5min_2y_parquet/*.parquet` 主要含
`symbol,timestamp,open,high,low,close,volume,amount,source_freq`。它们缺少：

- 显式 `bar_final` 与其来源/抓取时间证明；
- `vwap` 或可审计的累计成交额/量口径；
- PIT adjustment/corporate action、PIT universe；
- `is_suspended,is_st,prev_close,limit_up_price,limit_down_price,limit_regime`；
- 逐时点 benchmark/industry/theme/regime sidecar。

因此 Data Builder 必须报告阻断原因，禁止为这些文件填默认值或把它们升级为正式数据。

## 建议的来源组合与验收顺序

1. **价格主源**：先采购或确认有书面历史权限的券商/商业分钟归档，并取得数据字典，明确
   timestamp 是 interval-end、何时 final、修订政策和覆盖范围。
2. **PIT sidecars**：为公司行为/复权、universe、停牌/ST/涨跌停与交易日历分别取得可按
   `as_of` 回放的版本文件；不得从今天的证券状态回填历史。
3. **市场侧表**：独立导入指数、行业、主题和 regime，附带 `industry_as_of` 与源文件 hash。
4. **Tushare**：只在所需权限确实开通、每个输出经 timestamp/finalization/PIT adapter 验收后，
   才可用作辅助 source；不能以日线复权能力替代分钟 PIT 复权。
5. 通过 5–10 标的、3–6 个月的 `REHEARSAL` Builder gate 后，再讨论扩展范围。此时仍不
   启动 sealed test。

## 不可获得/尚未证明的字段

截至本审计，当前本地环境没有可验证的：分钟 PIT 复权、PIT universe、历史行业 as-of、
bar finalization provenance、逐日限价制度版本及商业数据授权。它们是正式数据构建的
**外部前置条件**，不是代码兼容问题。

官方资料交叉核对：Tushare 的分钟接口权限另行管理，且其公开 `pro_bar` 复权说明明确将
复权支持限定为 A 股日线；AKShare 对部分指数分钟接口也说明仅提供近期数据。来源链接：
[Tushare 复权说明](https://www.tushare.pro/document/2?doc_id=146)、
[Tushare 分钟指数示例](https://tushare.pro/document/2?doc_id=469)、
[AKShare 指数分钟说明](https://akshare.akfamily.xyz/data/index/index.html)。

## 不变约束

```text
sealed_test_accessed=false
score_weight=0.0
conflict_gate_enabled=False
production promotion unauthorized
```
