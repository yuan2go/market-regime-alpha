# MACD 买卖点研究审计（Task 11A.3）

本审计只使用 train、validation 和 rehearsal。它不读取 sealed test、不修改生产参数，也不把受控 fixture 的结果解释为策略收益证据。

## 标签定义

候选的入场价格固定为候选 bar 收盘后**下一根实际可执行 bar 的 open**。`label_candidate_outcomes()`、反事实和回测复用 `a-share-execution-v1`：下一可执行 bar、T+1、可卖数量、现金、最小手数、核心仓位下限、停牌、涨跌停、手续费、印花税、滑点和 reverse-T 均只有一个解析语义。标签写入 `actual_executable`、`execution_block_reason`、`execution_time`、`execution_price`、`execution_quantity`、`execution_cost` 和 `execution_constraint_version`；若不存在可执行 bar，不以候选 bar 的 high/low 代替成交。

- 买点：输出未来 1/3/5 **后续交易日**与 1/3/6/12/24 个 5 分钟 bar 的毛收益、扣成本收益、相对指数/行业超额收益、MFE、MAE、止损触发和可成交性。日线 horizon 由交易日历定位，不使用 `48 × N`；每个 horizon 独立输出 `mfe_*`、`mae_*`、`stop_triggered_*`，不以最大窗口代替。
- 卖点：`HIGH_SELL_T`、`TAKE_PROFIT_T`、`REVERSE_T_SELL` 同时输出 `directional_decline_label_<horizon>` 和按正式买回规则计算的 `completed_t_cycle_label`；后者扣除买卖费用且遵守 pending buyback、T+1、涨跌停、现金和 reverse-T。`RISK_EXIT`（CLEAR/REDUCE/EXIT_T/STOP_T）只报告尾部风险、MAE 和避免损失，不与普通卖 T 共用方向命中率。
- 成本：标签的 `cost_adjusted_return` 统一扣除同一执行假设下的往返费用和滑点；正式运行必须复用 backtest 的费率、T+1、涨跌停、停牌、现金和仓位约束。

## 校准与分层

概率审计只接受 horizon 成对字段，例如 `up_probability_bar_6 ↔ success_bar_6` 或 `up_probability_day_3 ↔ success_day_3`；禁止无 horizon 的 `up_probability/success`。每对分别输出 reliability curve、Brier score、log loss、分箱命中率和样本量，并按 market regime、symbol type、primary setup、SignalIntent、标的、行业、波动率层、趋势/震荡和持有期分层。参考指数/行业由候选的 `benchmark_symbol,industry_id,industry_as_of` 同频率、同日历、PIT 精确对齐；缺失返回原因，不能取最后一条记录。

## 阈值稳健性

特征阈值使用明确比较类型：`GREATER_EQUAL`（force_buy_edge/buy_strength/capital_flow/risk_reward 等）、`LESS_EQUAL`（buy gate 的 sell_pressure）或 `BETWEEN`。报告围绕当前基准作局部邻域网格，保留样本数、覆盖率、成功率与扣成本平均收益和邻域稳定性；不得自动选择孤立最优点。`macd_score_weight` 和 `mean_reversion_size_multiplier` 是策略参数，必须重跑完整四组实验，禁止用 DataFrame 行筛选替代。

## 当前卖点缺口

当前普通 `SELL_T_TIMING` 常被质量/等待链路降级，且缺少稳定的 `TAKE_PROFIT_T`、`REDUCE_T`、`EXIT_T` 和 `REVERSE_T_SELL` 研究标签。下一轮候选契约应显式记录：持仓成本、持有 bar 数、最高浮盈、ATR trailing 状态、MFE 回撤、时间止损、setup invalidation 与风险强制等级。该补齐前，卖点研究只能报告现有 `SELL_T_TIMING` 覆盖率及风险退出的尾部保护，不应宣称卖点优于买点。

Task 11A.7 已将减仓动作拆分为 `TAKE_PROFIT_REDUCE_T`（`MEAN_REVERSION_T/NONE`）和
`RISK_REDUCE_T`（`RISK_REDUCTION/SOFT`），保留既有 intent/enforcement 不变量。旧
`point_hit_rate.py` 是 `LEGACY_DIAGNOSTIC_ONLY`，其将 `SELL_T_TIMING`、`STOP_T_WAIT` 与
`WAIT_DAILY_WEAK` 合并的历史统计不得进入正式卖点报告或任何 promotion 决策。
