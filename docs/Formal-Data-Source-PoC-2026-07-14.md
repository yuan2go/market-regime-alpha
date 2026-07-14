# BaoStock 正式数据源 PoC（2026-07-14）

状态：**完成实际抓取；Builder 拒绝；不得进入真实 development dataset。**

本 PoC 未读取 sealed test，未运行策略收益，也未修改生产 profile。候选源为 BaoStock 匿名
历史 5 分钟接口：它不要求本机账户凭据，适合验证“真实源数据能否通过正式 Builder”，但不
预设其已满足 PIT 数据契约。

## 抓取范围与可复现证据

- 标的：`600519.SH, 601398.SH, 600036.SH, 000001.SZ, 510300.SH`。
- 请求窗口：2026-06-14 至 2026-07-14；实际返回 2026-06-15 至 2026-07-13。
- 每标的：20 个交易日、960 根 5m bar（48 根/完整日），总计 4,800 根。
- 本地原始 artifact：`data/external/formal_source_poc/baostock_20260714/`；包含 fetch checkpoint。
- 5 个 CSV 的 SHA-256 已在本次命令输出记录；数据只用于本地 PoC，不是正式 dataset。

时间戳均落在 `09:35 … 15:00` 的 interval-end 模式，且每个实际交易日 48 根，说明该源可
作为**待适配**的原始历史 5m 候选。但这不是 finalized provenance：源文件没有来源级
`bar_final` 或抓取/修订证明。

## Builder 结果

使用完整 `FormalDatasetBuildRequest` 路径（临时空 sidecar 仅为让调用进入 bar contract）执行后：

```text
BUILDER_RESULT=BAR_FINAL_REQUIRED
```

原始字段为：

```text
symbol,timestamp,open,high,low,close,volume,amount,source_freq
```

缺少 `bar_final`、已归一化单位/VWAP、PIT corporate-action evidence、PIT universe、交易
资格（停牌/ST/涨跌停）、以及逐 symbol/timestamp 的行业/benchmark as-of sidecar。依既有
规则，不能由 Builder、MACD 层或 CSV 导入默认补齐。

## 结论与下一步

BaoStock 的本次真实 PoC **未通过**正式 Builder，因而不能作为当前主源，不能开始 5–10 标的
3–6 个月真实 development dataset。要继续 PoC，必须取得一个能导出并证明以下字段的授权
价格/PIT 组合，或从多个有 as-of 版本的来源构建受审计 adapter：

1. interval-end 与 finalized/revision provenance；
2. source-unit normalization 和可审计 VWAP；
3. `symbol,effective_time,adjustment_as_of,corporate_action_id,factor`；
4. PIT universe、交易资格和历史行业/benchmark mapping。

```text
sealed_test_accessed=false
score_weight=0.0
conflict_gate_enabled=False
production promotion unauthorized
```
