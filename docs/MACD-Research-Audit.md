# MACD 买卖点研究审计（Task 11A.3）

本审计只使用 train、validation 和 rehearsal。它不读取 sealed test、不修改生产参数，也不把受控 fixture 的结果解释为策略收益证据。

## 标签定义

候选的入场价格固定为候选 bar 收盘后**下一根可执行 bar 的 open**。跳过停牌、方向涨跌停和不可交易 bar；若不存在可执行 bar，则标记 `actual_executable=false`，不以候选 bar 的 high/low 代替成交。

- 买点：输出未来 1/3/5 个交易日（48/144/240 个 5 分钟 bar）与 1/3/6/12/24 个 5 分钟 bar 的毛收益、扣成本收益、相对指数/行业超额收益、MFE、MAE、止损触发和可成交性。
- 卖点：`HIGH_SELL_T`、`TAKE_PROFIT_T`、`REVERSE_T_SELL` 使用卖出后价格回落的方向收益；`RISK_EXIT`（CLEAR/REDUCE/EXIT_T/STOP_T）只报告尾部风险、MAE 和避免损失，不与普通卖 T 共用方向命中率。
- 成本：标签的 `cost_adjusted_return` 统一扣除同一执行假设下的往返费用和滑点；正式运行必须复用 backtest 的费率、T+1、涨跌停、停牌、现金和仓位约束。

## 校准与分层

概率审计输出 reliability curve、Brier score、log loss 及分箱命中率，并按 market regime、symbol type、primary setup、SignalIntent、标的、行业、波动率层、趋势/震荡和持有期分层。概率的定义、预测时点和对应 outcome horizon 必须同写入实验 Manifest。

## 阈值稳健性

`force_buy_edge`、`buy_strength_score`、`sell_pressure`、`capital_flow`、`multi_period_trend`、`risk_reward`、`breakout`、`macd_score_weight` 与 `mean_reversion_size_multiplier` 均只作局部网格报告。报告保留每个阈值的样本数、覆盖率、成功率与扣成本平均收益；不得按单点最高收益自动选参，候选参数必须来自样本量足够且相邻阈值表现稳定的区域。

## 当前卖点缺口

当前普通 `SELL_T_TIMING` 常被质量/等待链路降级，且缺少稳定的 `TAKE_PROFIT_T`、`REDUCE_T`、`EXIT_T` 和 `REVERSE_T_SELL` 研究标签。下一轮候选契约应显式记录：持仓成本、持有 bar 数、最高浮盈、ATR trailing 状态、MFE 回撤、时间止损、setup invalidation 与风险强制等级。该补齐前，卖点研究只能报告现有 `SELL_T_TIMING` 覆盖率及风险退出的尾部保护，不应宣称卖点优于买点。
