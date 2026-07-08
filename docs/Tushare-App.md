# Tushare A股行情查询项目

这个模块提供两个入口：

- 命令行抓取：`scripts/fetch_tushare_bars.py`
- 本地网页查询：`market_regime_alpha.web.tushare_app`

## 安装依赖

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 配置 Token

在项目根目录创建 `.env`，写入：

```bash
TUSHARE_TOKEN=你的Tushare Token
```

`.env` 已在 `.gitignore` 中排除，不要提交真实 token。

## 命令行读取数据

日线：

```bash
python3 scripts/fetch_tushare_bars.py daily 600000.SH --start 20240101 --end 20240518
```

分钟线：

```bash
python3 scripts/fetch_tushare_bars.py minute 600000.SH --freq 1min --start "2024-05-17 09:00:00" --end "2024-05-17 15:30:00"
```

输出字段统一为：

```text
symbol,timestamp,open,high,low,close,volume,amount,source_freq
```

默认会在 `data/raw/tushare` 下缓存 Tushare 返回并规范化后的 CSV。

## 启动页面

```bash
PYTHONPATH=src uvicorn market_regime_alpha.web.tushare_app:app --reload --host 127.0.0.1 --port 8000
```

打开：

```text
http://127.0.0.1:8000
```

页面支持：

- 按股票代码或名称搜索 A 股列表。
- 查询日线。
- 查询 1min、5min、15min、30min、60min 分钟线。
- 显示简易 K 线图和明细表格。

## 注意

- Tushare 日线接口通常更容易直接使用。
- A股分钟线需要 Tushare 单独开通分钟权限，否则可能返回空数据或权限错误。
- 日线日期使用 `YYYYMMDD`，分钟线时间使用 `YYYY-MM-DD HH:MM:SS`。

