"""Universe builders for broader A-share backtests."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


DEFAULT_POINT_IN_TIME_WARNING = "current-snapshot universe; not point-in-time historical constituents"
CYCLE_INDUSTRY_KEYWORDS = ("煤", "石油", "钢", "有色", "化工", "航运", "港口", "铁路", "建材", "地产", "券商")


@dataclass(frozen=True)
class LargecapUniverseConfig:
    trade_date: str
    limit: int = 1000
    market_value_field: str = "total_mv"
    min_list_days: int = 365
    min_amount: float = 50_000.0


def build_largecap_universe(
    *,
    stock_basic: Any,
    daily_basic: Any,
    daily_quote: Any,
    config: LargecapUniverseConfig,
) -> tuple[Any, dict[str, int | float | str]]:
    """Build a large-cap watchlist from stock metadata and one market snapshot."""

    import pandas as pd

    if config.limit <= 0:
        raise ValueError("limit must be positive")
    if config.market_value_field not in {"total_mv", "circ_mv"}:
        raise ValueError("market_value_field must be total_mv or circ_mv")

    basic = _require_columns(stock_basic, {"ts_code", "name", "industry", "market", "list_date"}).copy()
    valuation = _require_columns(daily_basic, {"ts_code", "total_mv", "circ_mv"}).copy()
    quote = _require_columns(daily_quote, {"ts_code", "amount"}).copy()

    diagnostics: dict[str, int | float | str] = {
        "trade_date": config.trade_date,
        "raw_stock_basic": int(len(basic)),
        "raw_daily_basic": int(len(valuation)),
        "raw_daily_quote": int(len(quote)),
    }

    basic["ts_code"] = basic["ts_code"].astype(str).str.upper()
    basic["name"] = basic["name"].astype(str)
    basic["industry"] = basic["industry"].fillna("未知").astype(str)
    basic["market"] = basic["market"].fillna("").astype(str)
    basic["list_date"] = basic["list_date"].astype(str)
    basic = basic[basic["ts_code"].str.endswith((".SH", ".SZ"))].copy()
    basic = basic[~basic["ts_code"].str.endswith(".BJ")].copy()
    basic = basic[~basic["market"].str.contains("北", na=False)].copy()
    basic = basic[~basic["name"].str.contains("ST|退", case=False, regex=True, na=False)].copy()
    diagnostics["after_board_and_name_filters"] = int(len(basic))

    as_of = pd.to_datetime(config.trade_date, format="%Y%m%d")
    basic["list_days"] = (as_of - pd.to_datetime(basic["list_date"], format="%Y%m%d", errors="coerce")).dt.days
    basic = basic[basic["list_days"] >= config.min_list_days].copy()
    diagnostics["after_listing_age_filter"] = int(len(basic))

    valuation["ts_code"] = valuation["ts_code"].astype(str).str.upper()
    for column in ("total_mv", "circ_mv"):
        valuation[column] = pd.to_numeric(valuation[column], errors="coerce")
    valuation = valuation[valuation[config.market_value_field].notna() & (valuation[config.market_value_field] > 0)].copy()
    diagnostics["after_market_value_filter"] = int(len(valuation))

    quote["ts_code"] = quote["ts_code"].astype(str).str.upper()
    quote["amount"] = pd.to_numeric(quote["amount"], errors="coerce")
    quote = quote[quote["amount"].notna() & (quote["amount"] >= config.min_amount)].copy()
    diagnostics["after_liquidity_filter"] = int(len(quote))

    merged = basic.merge(valuation[["ts_code", "total_mv", "circ_mv"]], on="ts_code", how="inner")
    merged = merged.merge(quote[["ts_code", "amount"]], on="ts_code", how="inner")
    diagnostics["after_inner_join"] = int(len(merged))

    selected = merged.sort_values([config.market_value_field, "amount", "ts_code"], ascending=[False, False, True]).head(config.limit).copy()
    selected["symbol"] = selected["ts_code"]
    selected["is_cycle_stock"] = selected["industry"].map(_is_cycle_industry)
    selected["notes"] = (
        f"top{config.limit}_largecap {config.market_value_field} asof={config.trade_date}; "
        f"{DEFAULT_POINT_IN_TIME_WARNING}"
    )
    selected["asof_date"] = config.trade_date
    selected["universe_method"] = f"top{config.limit}_{config.market_value_field}_largecap"
    selected["bias_notes"] = DEFAULT_POINT_IN_TIME_WARNING
    output = selected[
        [
            "symbol",
            "name",
            "industry",
            "is_cycle_stock",
            "notes",
            "total_mv",
            "circ_mv",
            "amount",
            "list_date",
            "list_days",
            "asof_date",
            "universe_method",
            "bias_notes",
        ]
    ].reset_index(drop=True)
    diagnostics["selected"] = int(len(output))
    diagnostics["min_amount"] = float(config.min_amount)
    diagnostics["market_value_field"] = config.market_value_field
    return output, diagnostics


def format_largecap_universe_report(frame: Any, diagnostics: dict[str, int | float | str], *, output_path: str) -> str:
    top_preview = "\n".join(
        f"| `{row.symbol}` | {row.name} | {row.industry} | {row.total_mv:,.0f} | {row.circ_mv:,.0f} | {row.amount:,.0f} |"
        for row in frame.head(20).itertuples(index=False)
    )
    if not top_preview:
        top_preview = "| - | - | - | - | - | - |"
    return (
        "# Top 大盘股 Universe\n\n"
        "## 生成参数\n\n"
        f"- 交易日：{diagnostics.get('trade_date')}\n"
        f"- 数据源：{diagnostics.get('data_source', '-')}\n"
        f"- 市值字段：{diagnostics.get('market_value_field')}\n"
        f"- 最小成交额：{diagnostics.get('min_amount')}\n"
        f"- 输出：`{output_path}`\n\n"
        "## 筛选漏斗\n\n"
        f"- 原始 stock_basic：{diagnostics.get('raw_stock_basic')}\n"
        f"- 原始 daily_basic：{diagnostics.get('raw_daily_basic')}\n"
        f"- 原始 daily quote：{diagnostics.get('raw_daily_quote')}\n"
        f"- 剔除北交所/ST/退市名后：{diagnostics.get('after_board_and_name_filters')}\n"
        f"- 上市天数过滤后：{diagnostics.get('after_listing_age_filter')}\n"
        f"- 市值有效过滤后：{diagnostics.get('after_market_value_filter')}\n"
        f"- 成交额过滤后：{diagnostics.get('after_liquidity_filter')}\n"
        f"- 合并后：{diagnostics.get('after_inner_join')}\n"
        f"- 最终入选：{diagnostics.get('selected')}\n\n"
        "## 前 20\n\n"
        "| 代码 | 名称 | 行业 | 总市值 | 流通市值 | 成交额 |\n"
        "| --- | --- | --- | ---: | ---: | ---: |\n"
        f"{top_preview}\n\n"
        "## 偏差说明\n\n"
        f"- {DEFAULT_POINT_IN_TIME_WARNING}。\n"
        "- 初版用于扩大回测覆盖面；严格研究需要按历史日期重建 point-in-time 成分，避免幸存者偏差。\n"
    )


def _require_columns(frame: Any, required: set[str]) -> Any:
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"universe input missing columns: {', '.join(missing)}")
    return frame


def _is_cycle_industry(industry: str) -> bool:
    return any(keyword in str(industry) for keyword in CYCLE_INDUSTRY_KEYWORDS)
