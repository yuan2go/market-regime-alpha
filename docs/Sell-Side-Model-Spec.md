# 卖点模型独立设计规格（Task 11A.5）

状态：**设计冻结，未授权大范围实现或启用生产。** 本规格不改变默认
`score_weight=0.0`、`conflict_gate_enabled=False`，也不授权 sealed test。

## 候选动作契约

| Action | SignalIntent | RiskEnforcement | 持仓对象 | 主触发 | 建议比例 | 等待 | MACD | 买回 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `TAKE_PROFIT_T` | `MEAN_REVERSION_T` | `NONE` | T 仓 | 达到收益目标且出现压力/衰减确认 | 可配置 25–100% T 仓 | 允许 | 允许非对称 policy（强多头无确认时阻断；有确认时缩仓） | 不自动 |
| `TAKE_PROFIT_REDUCE_T` | `MEAN_REVERSION_T` | `NONE` | T 仓 | 浮盈回撤/时间条件下的主动止盈减仓 | 可配置部分 T 仓 | 允许 | 允许非对称 policy | 不自动 |
| `RISK_REDUCE_T` | `RISK_REDUCTION` | `SOFT` | T 仓 | 进攻状态下调或软风险阈值 | 可配置部分 T 仓 | 允许 | 不阻断/缩仓，仅记录 | 不自动 |
| `EXIT_T_SOFT` / `EXIT_T_HARD` | `RISK_REDUCTION` | `SOFT` / `HARD` | T 仓 | setup 失效或风险阈值 | 100% 可卖 T 仓 | SOFT 可等；HARD 不可等 | 不阻断/缩仓，仅记录 | 不自动 |
| `STOP_T` | `RISK_REDUCTION` | `HARD` | T 仓，再按契约可扩展至总仓 | 硬止损、结构破位、尾部风险 | 100% 可卖范围 | 不允许 | 完全豁免 | 不自动 |
| `REVERSE_T_SELL` | `MEAN_REVERSION_T` | `NONE` | 可卖底仓 | 压力位高抛并建立待买回义务 | 受核心仓位下限约束 | 允许 | 强多头无 exit confirmation 时阻断；有确认时缩仓 | 必须，创建 pending buyback |
| `CLEAR_BASE` | `RISK_REDUCTION` | `HARD` | 底仓与 T 仓 | 硬止损、结构破位或组合级强制退出 | 100% 可卖总仓 | 不允许 | 完全豁免 | 不允许 |

同一候选只允许一个 `primary_setup_code`、一个动作、一个 `SignalIntent` 与一个
`RiskEnforcement`。非 `RISK_REDUCTION` intent 只能使用 `NONE` enforcement，因此不得再使用
`REDUCE_T = MEAN_REVERSION_T + SOFT` 的混合定义。`STOP_T_WAIT` 是 `SOFT` 风险的等待状态，不能由 action 文案
倒推为 HARD；HARD 风控永远不经过 MACD policy。

## 持仓生命周期上下文

所有卖点候选生成器必须显式携带以下字段；缺失时不得伪造为零：

```text
entry_price, entry_time, holding_bars, unrealized_return,
max_unrealized_return, drawdown_from_peak, t_position_pct, base_position_pct,
same_day_bought_qty, sellable_qty, pending_buyback, setup_invalidation_level,
atr_trailing_level
```

另需持久化 `base_shares/t_shares`、各自锁定数量、`core_position_floor_pct`、
`buyback_target_price` 与已分配反向卖出所得。候选生成阶段负责计算这些当前 bar
状态；quality、MACD、回测和执行层只能消费，不能重新分类。

Task 11A.8 的最小 research 实现以 `ResearchExecutionState` 承载现金、底仓/T 仓、T+1
锁定数量、交易日与 `PendingBuyback`。跨日转移解锁同日买入数量；买回允许受控 partial
fill，更新现金、持仓及剩余买回义务；超过 `buyback_expiry_bars` 或
`buyback_expiry_trade_days` 后过期；HARD 风险退出取消 pending buyback。该状态机仅被标签和
受控 rehearsal 使用，尚未接入生产策略 profile。

## 标准化退出组件

- ATR trailing：以当前已收盘 bar 的 ATR、最高收盘/最高价与配置倍数计算。触发仅在
  下一可执行 bar 执行；不得使用同 bar 的最低价成交。
- MFE 回撤退出：达到最小 `max_unrealized_return` 后，`drawdown_from_peak` 超过阈值，
生成 `TAKE_PROFIT_T` 或 `TAKE_PROFIT_REDUCE_T`，而不是硬编码成 `STOP_T`。
- 时间止损：超过 setup 的 `max_holding_bars` 且没有后续确认，生成 `RISK_REDUCE_T` 或
  `EXIT_T_SOFT`；不能把持有时间本身当作 HARD 风险。
- setup invalidation：由结构模块输出 `NONE/SOFT/HARD`。`HARD` 生成 `EXIT_T_HARD` 或
  `CLEAR_BASE` 并带 `RiskEnforcement.HARD`；`SOFT` 可以保留等待确认。

最小选择器的固定优先级为：`HARD invalidation` → `ATR trailing` → `SOFT invalidation` →
`MFE drawdown` → `time stop`。它的输出仍是 research action；没有修改当前生产 action
路由或 MACD 默认 profile。

## reverse-T 买回状态机

```text
READY
  -> REVERSE_T_SELL executed
  -> PENDING_BUYBACK(quantity, allocated_proceeds, target_price)
  -> BUYBACK_FILLED | BUYBACK_PARTIAL | BUYBACK_EXPIRED | BUYBACK_CANCELLED_BY_HARD_RISK
```

创建反向 T 前必须同时通过：`allow_reverse_t`、T mode、可卖底仓、T+1、核心仓位下限、
涨跌停和最小手数。`PENDING_BUYBACK` 存在时不允许再开新的 reverse-T。买回由共享执行
解析器在后续符合 target 的可执行 bar 完成，扣费后比较已分配卖出所得；只有买回数量
完整且 cycle net PnL 为正，`completed_t_cycle_label=1`。

## 研究标签

普通卖 T 同时输出：

- `directional_decline_label_<horizon>`：卖出后该 horizon 收盘是否低于实际卖出填充价；
- `completed_t_cycle_label`：遵守正式买回、费用、滑点、T+1、涨跌停和现金约束后是否完成
  正收益 T 周期。

风险退出不参与普通方向命中率；报告尾部风险、最大不利变动、避免损失和回撤变化。所有
标签、回测、反事实复用 `a-share-execution-v1`，并记录 `execution_constraint_version`。

## 实施边界

Task 11A.5 只冻结数据/状态/动作设计。现有 `SELL_T_TIMING -> WAIT` 逻辑没有在本任务
改写；`point_hit_rate.py` 为 `LEGACY_DIAGNOSTIC_ONLY`，不得用于参数选择、MACD promotion、
sealed test 或生产结论。后续实现必须以小步提交、失败测试、共享 execution/policy seam 和独立回归为前提。
