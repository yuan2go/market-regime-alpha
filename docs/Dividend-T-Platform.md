# 长期 / 红利 / 做 T 交易平台

本文档对应 `strategies/ideas/Long-Term-Dividend-T-Model.md` 的第一版工程实现。

当前实盘边界：

```text
程序只提供中远海控 A 股的手动下单时机和参考价格。
不会自动下单。
不会调用 QMT / PTrade 发出真实委托。
```

## 当前实现范围

- 语言：Python。
- API：FastAPI。
- 数据分析：pandas 为主，polars 预留。
- 本地研究存储：DuckDB + Parquet 接口已预留。
- 实盘状态存储：Postgres 暂不启用，先使用本地状态和后续接口。
- 实时状态缓存：内存缓存已实现，Redis 作为可选实现。
- 任务调度：APScheduler 本地调度器，用于在交易时段调用量化报告并推送飞书。
- 前端：FastAPI 内置 Web Dashboard。
- 交易网关：`PaperBrokerAdapter` 可本地模拟，`QMTAdapter` / `PTradeAdapter` 默认安全占位，不会真实下单。
- 中远海控 5 分钟监听：`601919.SH` 专用手动时机引擎已实现。
- 免费行情适配：Tencent / EastMoney / AKShare / BaoStock / Tushare 基础权限统一成同一份 K 线数据契约。
- 退神理论：已实现市场关注度、上涨确定性、特定情境记忆、最大可卖量、动态权重和买量 / 卖量估算比。
- 缠论结构：已接入包含关系处理、分型、笔、中枢、背驰、一买/二买/三买/中枢低吸、卖点和结构失效门控。

## 仓位口径

当前工程化近似版本统一使用账户权益百分比表达仓位：

- 底仓目标：长期持有的底仓目标，当前策略边界为 5% 到 10%，由 `initial_base_position_pct`、`range_base_position_pct`、`strong_trend_base_position_pct` 表达。
- 主动增量上限：买入信号允许在底仓之上增加的主动 / T 仓空间，等于“买入后总仓位上限 - 底仓目标”。
- 最大总仓位：单票最终暴露上限，包含底仓和主动仓。`max_signal_position_pct` 是全局硬上限；历史字段 `t_trade_pct` / `t_trade_limit_pct` 在当前兼容层表示“买入后总仓位上限”，不是单独的 T 仓比例。

因此，强趋势下“底仓 10%、总仓位 80%”的真实含义是：底仓目标 10%，主动增量上限 70%，最终单票总仓位不超过 80%。满攻状态若允许 100% 总仓位，则主动增量为 90%，不是底仓变成 100%。

## 运行 Dashboard

```bash
source .venv/bin/activate
PYTHONPATH=src uvicorn market_regime_alpha.web.dividend_t_app:app --reload --host 127.0.0.1 --port 8010
```

打开：

```text
http://127.0.0.1:8010
```

核心 API：

```text
GET  /api/health
GET  /api/watchlist
GET  /api/sample-decisions
GET  /api/cosco-timing
GET  /api/cosco-timing/sample
GET  /api/data-sources
POST /api/evaluate
```

`/api/cosco-timing` 会尝试读取中远海控 `601919.SH` 的 5 分钟线并生成手动操作参考。默认使用免费数据源自动降级：

```text
TencentMinute -> EastMoneyDirect -> AKShare -> BaoStock -> Tushare
```

自动模式会先用腾讯分时接口读取今天盘中的 1 分钟分时，并聚合成 5 分钟 K 线，同时尝试用 BaoStock 只回补今天之前的历史 5 分钟 K 线，让 ATR、支撑压力、情境记忆等指标有足够窗口。若腾讯不可用，会尝试 EastMoney；再失败尝试 AKShare；之后才尝试 BaoStock 和 Tushare。BaoStock 单独返回的数据会被视为历史/过期分析，不允许生成盘中 BUY_T / SELL_T 信号。若所有数据源都不可用，会返回 `data_unavailable`、每个数据源的尝试结果和需要操作的清单，不会用样例价格冒充真实行情。

`/api/cosco-timing/sample` 使用本地固定样例数据，便于验证页面和计算逻辑；它不是实时行情。

`/api/data-sources` 返回 Dashboard 可选择的数据源：`auto`、`tencent`、`eastmoney`、`akshare`、`baostock`、`tushare`。

## 模型模块

```text
src/market_regime_alpha/dividend_t/models.py
    核心数据结构：F/R/T 输入、仓位状态、信号、订单意图。

src/market_regime_alpha/dividend_t/scoring.py
    基本面评分 F、退神评分 R、技术评分 T、总评分。

src/market_regime_alpha/dividend_t/strategy.py
    BUY_T / SELL_T / HOLD / REDUCE / STOP_T / CLEAR 决策规则。

src/market_regime_alpha/dividend_t/risk.py
    单票总仓位上限、周期股上限、单次主动买入上限、现金保留、T+1 可卖约束。

src/market_regime_alpha/dividend_t/brokers.py
    Paper / QMT / PTrade 交易网关接口。

src/market_regime_alpha/dividend_t/storage.py
    DuckDB + Parquet 研究数据存储接口。

src/market_regime_alpha/data_sources/a_share_bars.py
    免费 A 股行情适配层：Tencent、EastMoney、AKShare、BaoStock、Tushare 统一成标准 K 线字段。

src/market_regime_alpha/dividend_t/indicators.py
    均线、ATR、支撑压力、技术状态推断，并把缠论结构写入 TechnicalInputs。

src/market_regime_alpha/dividend_t/chan.py
    OHLCV 简化缠论结构识别：包含关系、分型、笔、中枢、背驰、买卖点、失效价和 C_score。

src/market_regime_alpha/dividend_t/tushare_provider.py
    Tushare Pro 财务、分红、复权数据的适配入口。

src/market_regime_alpha/dividend_t/attention.py
    市场关注度八点属性估算。

src/market_regime_alpha/dividend_t/certainty.py
    涨跌确定性的六大判断依据估算。

src/market_regime_alpha/dividend_t/memory.py
    特定情境记忆：最近相似情境、近端加权、时间衰减。

src/market_regime_alpha/dividend_t/dynamic_weights.py
    根据趋势、记忆、卖压调整 G/Z/K/S 权重。

src/market_regime_alpha/dividend_t/sell_pressure.py
    最大可卖量市场结构估算和卖出率估算。

src/market_regime_alpha/dividend_t/force_ratio.py
    买量 / 卖量估算比。

src/market_regime_alpha/dividend_t/cosco_timing.py
    中远海控 5 分钟手动下单时机和参考价格。当前使用“退神买卖力门 + 缠论结构门 + 风控门”共同决定 BUY_T / SELL_T / STOP_T / WAIT。
```

## 缠论 + 退神接入边界

当前实现不是全量 Level-2 盘口模型，而是第一阶段可回测版本：

```text
OHLCV / 资金流字段
    -> 退神 G/Z/K/S、记忆、买卖力比
    -> 缠论 C_score、中枢、背驰、买卖点
    -> 日线/盘中/多周期门控
    -> 手动信号、参考价格、止损/失效价
```

已实现的缠论字段会出现在 `/api/cosco-timing` 的 `chan_structure` 中，也会进入回测信号缓存：

```text
score
structure_type
pivot_low / pivot_high / pivot_mid / pivot_width
trend_direction
divergence_type / divergence_score
buy_point_type
sell_point_type
invalid_price
```

执行原则：

- 三买可以提升突破/趋势观察信号和进攻仓位分层。
- 一买、二买和中枢低吸只作为试探买点，仍需要退神买卖力、日线背景和风控确认。
- 顶背驰、一卖/二卖会优先给出卖 T 或降风险。
- 三卖、跌破中枢或结构失效会触发 `STOP_T_WAIT` / 主动仓位退出。
- 所有输出仍是手动参考，不自动下单。

## 用户需要操作的清单

1. 准备 Python 环境并安装依赖：

```bash
source .venv/bin/activate
pip install -r requirements.txt
```

2. 可选配置 Tushare Token：

```bash
cp .env.example .env
```

如果要使用 Tushare 作为第三个备选数据源，在 `.env` 中写入：

```text
TUSHARE_TOKEN=你的 token
```

如果只用 Tencent / EastMoney / AKShare / BaoStock 跑通免费计算流程，可以先不配置 Tushare Token。

3. 可选配置 BaoStock 注册账号：

```text
BAOSTOCK_USER_ID=你的 BaoStock 用户名
BAOSTOCK_PASSWORD=你的 BaoStock 密码
```

如果不配置，BaoStock SDK 会使用匿名登录参数。账号密码只应写在本地 `.env`，不要提交到 Git。

4. 可选配置飞书机器人推送：

```text
NOTIFY_CHANNELS=feishu
FEISHU_WEBHOOK_URL=你的飞书自定义机器人 webhook
FEISHU_SECRET=你的飞书签名密钥
```

`FEISHU_SECRET` 只有在飞书机器人开启“签名校验”时才需要。飞书官方文档说明，自定义机器人支持关键词、IP 白名单和签名三类安全配置，签名使用 `timestamp + "\n" + 密钥` 进行 HMAC-SHA256 后再 Base64 编码。

测试飞书推送：

```bash
PYTHONPATH=src ./.venv/bin/python scripts/cosco_timing_report.py --provider auto --no-persist --push --notify-channel feishu
```

启动飞书专用调度器：

```bash
PYTHONPATH=src ./.venv/bin/python scripts/cosco_feishu_scheduler.py
```

后台运行：

```bash
tmux new-session -d -s cosco-feishu 'cd /Users/yuan/projects/market-regime-alpha && PYTHONPATH=src ./.venv/bin/python scripts/cosco_feishu_scheduler.py'
```

查看后台调度器：

```bash
tmux ls
tmux capture-pane -pt cosco-feishu
```

停止后台调度器：

```bash
tmux kill-session -t cosco-feishu
```

当前自动推送时间：

```text
09:35
10:05
10:35
11:05
13:05
13:35
14:05
14:35
15:05
```

这些定时推送只走飞书机器人。Codex 内置定时任务不再用于中远海控上报，避免手机通知路径不明确。

5. 确认观察池：

```text
data/external/watchlists/dividend_t_watchlist.csv
```

先保留 10-30 只，不要一开始扩展太大。

6. QMT / PTrade 实盘接入前必须完成：

```text
确认券商账户和交易权限。
先在模拟盘验证登录、账户、持仓、委托、撤单、成交回报。
确认可卖数量字段，避免违反 A 股 T+1。
确认最小下单单位、价格精度、涨跌停处理。
确认断线重连、重复下单防护、撤单失败处理。
```

7. 实盘前必须先跑三层验证：

```text
只读模式：只读行情、账户、持仓。
模拟模式：真实行情 + 模拟订单。
人工确认模式：系统出信号，人工点击确认后才提交。
```

8. 5 分钟监听要生效，需要至少满足其一：

```text
QMT L1 能读取本地 5 分钟线、tick 快照和五档盘口。
腾讯分时接口能访问当日 1 分钟分时。
EastMoney 直连接口能访问东方财富分钟线。
AKShare 能访问东方财富分钟线。
BaoStock 能访问 5 分钟历史 K 线，用于历史回补。
Tushare 有 stk_mins 分钟线权限。
```

当前版本的 Dashboard 会每 5 分钟调用一次 `/api/cosco-timing`。如果数据不可用，页面不会伪造实时信号，只会提示配置缺失。如果最后一根 K 线超过新鲜度阈值，页面会显示 `WAIT_STALE_DATA`，并清空参考买入/卖出/止损价。

注意：腾讯、EastMoney、AKShare、BaoStock、Tushare 免费/基础行情都是轮询型或延迟数据源，不是逐笔实时流。Dashboard 会显示数据来源、K 线时间、生成时间、数据年龄、数据新鲜度和实时性标记；只有 QMT L1 这类券商本地实时行情源才应把 `is_realtime` 标记为真实实时。

## QMT L1 只读行情接入

当前实现只接行情，不接下单：

```text
QmtL1Provider.minute_bars
    通过 xtdata.download_history_data + xtdata.get_market_data_ex 读取本地 5 分钟线。

QmtL1Provider.tick_snapshots
    通过 xtdata.get_full_tick 读取 tick 快照、成交量/成交额和五档盘口。

FiveLevelBook
    归一化 bid/ask 五档价格、五档量、买盘金额、卖盘金额、盘口不平衡和价差。
```

默认自动源不会启用 QMT，避免没有 QMT 的机器反复报错。需要在已安装并登录 QMT/miniQMT、且 Python 能导入 `xtquant` 的机器上配置：

```text
QMT_L1_AUTO=1
```

也可以在命令行显式选择：

```bash
PYTHONPATH=src ./.venv/bin/python backtesting/run_cosco_dividend_t_backtest.py --provider qmt --symbol 601919.SH
```

QMT L1 接入后，下一步应把 `FiveLevelBook.imbalance`、盘口价差、五档买卖金额和 tick 成交额变化接入买量/卖量模型；在没有真实逐笔成交和 Level-2 委托队列前，五档盘口只能提高盘中稳定性，不能保证稳定盈利。

## 中远海控 5 分钟输出字段

```text
action
    BUY_T_TIMING / SELL_T_TIMING / STOP_T_WAIT / WAIT_DAILY_WEAK / WAIT_CONFIRMATION / WAIT_LATE_SESSION / WAIT_STRONG_TREND / WAIT_STALE_DATA / WAIT

timestamp
    输入数据中最后一根 5 分钟 K 线的时间。

generated_at
    本次模型信号生成时间。

data_source
    数据来源，例如 akshare_stock_zh_a_hist_min_em_5min、baostock_query_history_k_data_plus_5min、tushare_stk_mins_5min 或 sample_static_5min。

data_age_minutes
    信号生成时间与最后一根 K 线时间的差值。

data_fresh
    最后一根 K 线是否落在新鲜度阈值内。当前盘中默认阈值为 10 分钟。

freshness_status
    fresh 或 stale。

signal_blocked
    如果为 true，说明模型原本可能给出 BUY_T / SELL_T，但已被数据新鲜度门禁拦截。

is_realtime
    是否为真实实时流。当前免费轮询和样例数据均为 false。

data_attempts
    自动降级时每个数据源的尝试结果，用于定位是网络问题、接口权限问题还是数据为空。

prices.current_price
    当前价。

prices.buy_reference_price
    手动正 T 可观察的低吸参考价。

prices.sell_reference_price
    手动卖 T 或倒 T 可观察的高抛参考价。

prices.stop_price
    当前 T 仓逻辑失效价。

prices.buy_back_reference_price
    倒 T 后的买回观察价。

daily_context
    日线背景评分 D。日线决定是否允许做 T、是否允许隔夜、倒 T 后是否允许给买回价，以及 T 仓仓位系数。

intraday_context
    盘中执行评分 I。5 分钟统计只负责确认支撑/压力、是否收回支撑、是否接近尾盘、是否具备盘中执行条件。

时间尺度门控规则：

```text
日线强：允许正常做 T，允许计划买回。
日线中性：只允许小仓 T，买回必须二次确认，不默认隔夜。
日线弱：禁止把 5 分钟买点升级为买回或补仓。
14:30 后：如果日线不支持隔夜，尾盘买回被拦截，次日重新计算。
```

关键原则：

```text
到达买回价 != 可以买回。
日线允许 + 分时确认 + 卖压下降，才允许输出可执行买回信号。
```

force.force_ratio
    买量 / 卖量估算比。

attention.attributes
    市场关注度八点属性。

certainty.bases
    涨跌确定性的六大判断依据。

memory
    当前情境的历史近端加权记忆。

sell_pressure
    最大可卖量、卖出率、前高压力、获利盘、套牢盘、放量滞涨压力。
```

## 当前边界

- 当前版本不会真实调用 QMT / PTrade 下单。
- 当前中远海控 5 分钟版本会自动估算 G/Z/K/S、买卖力量比和参考价格，但基础面 F 仍以配置和人工校准为主。
- 当前版本适合验证模型规则、风控边界和 Dashboard 工作流。
- 后续再把 Tushare 财务/分红/复权数据接入 F 分数，把 QMT/PTrade 实时行情接入 G/K/S/T。
