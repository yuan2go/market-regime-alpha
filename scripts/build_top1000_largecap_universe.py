#!/usr/bin/env python3
"""Build a top large-cap A-share watchlist from Tushare snapshots."""

from __future__ import annotations

from pathlib import Path
import argparse
from contextlib import redirect_stdout
from io import StringIO
import sys
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from market_regime_alpha.data_sources.tushare_client import build_tushare_client  # noqa: E402
from market_regime_alpha.dividend_t.universe import (  # noqa: E402
    LargecapUniverseConfig,
    build_largecap_universe,
    format_largecap_universe_report,
)


DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "external" / "watchlists" / "top1000_largecap_watchlist.csv"
DEFAULT_REPORT = PROJECT_ROOT / "reports" / "universe" / "top1000_largecap_watchlist.md"
TENCENT_QUOTE_URL = "https://qt.gtimg.cn/q="
TENCENT_USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X) AppleWebKit/537.36"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        choices=["tushare", "tencent-baostock"],
        default="tushare",
        help="Snapshot source. tencent-baostock does not require a Tushare token.",
    )
    parser.add_argument("--trade-date", required=True, help="Tushare trade date, YYYYMMDD or YYYY-MM-DD.")
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument("--market-value-field", choices=["total_mv", "circ_mv"], default="total_mv")
    parser.add_argument("--min-list-days", type=int, default=365)
    parser.add_argument("--min-amount", type=float, default=50_000.0, help="Minimum same-day amount. Tushare daily amount unit is thousand CNY.")
    parser.add_argument("--quote-batch-size", type=int, default=120, help="Tencent quote symbols per request.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--no-cache", action="store_true")
    args = parser.parse_args()

    if args.source == "tushare":
        client = build_tushare_client()
        use_cache = not args.no_cache
        stock_basic = client.stock_basic(use_cache=use_cache)
        daily_basic = client.daily_basic_snapshot(args.trade_date, use_cache=use_cache)
        daily_quote = client.daily_market_snapshot(args.trade_date, use_cache=use_cache)
        source_note = "tushare stock_basic + daily_basic + daily"
    else:
        stock_basic = load_baostock_stock_basic()
        daily_basic, daily_quote = load_tencent_quote_snapshot(stock_basic["ts_code"].tolist(), batch_size=args.quote_batch_size)
        source_note = (
            "baostock query_stock_basic + tencent qt quote; "
            "Tencent market values are converted from 亿元 to 万元, amount from 万元 to 千元"
        )
    config = LargecapUniverseConfig(
        trade_date=args.trade_date.replace("-", ""),
        limit=args.limit,
        market_value_field=args.market_value_field,
        min_list_days=args.min_list_days,
        min_amount=args.min_amount,
    )
    watchlist, diagnostics = build_largecap_universe(
        stock_basic=stock_basic,
        daily_basic=daily_basic,
        daily_quote=daily_quote,
        config=config,
    )
    diagnostics["data_source"] = source_note
    args.output.parent.mkdir(parents=True, exist_ok=True)
    watchlist.to_csv(args.output, index=False)

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(format_largecap_universe_report(watchlist, diagnostics, output_path=str(args.output)), encoding="utf-8")

    print(f"Saved {len(watchlist)} symbols to {args.output}")
    print(f"Report: {args.report}")
    print(watchlist.head(20).to_string(index=False))
    return 0


def load_baostock_stock_basic() -> object:
    try:
        import baostock as bs
        import pandas as pd
    except ImportError as exc:
        raise RuntimeError("Missing dependency: install baostock.") from exc

    with redirect_stdout(StringIO()):
        login = bs.login(user_id="anonymous", password="123456")
    try:
        if getattr(login, "error_code", "0") != "0":
            raise RuntimeError(f"BaoStock login failed: {login.error_msg}")
        rs = bs.query_stock_basic()
        if getattr(rs, "error_code", "0") != "0":
            raise RuntimeError(f"BaoStock stock_basic failed: {rs.error_msg}")
        rows: list[list[str]] = []
        while rs.next():
            rows.append(rs.get_row_data())
        frame = pd.DataFrame(rows, columns=rs.fields)
    finally:
        with redirect_stdout(StringIO()):
            bs.logout()

    if frame.empty:
        raise RuntimeError("BaoStock stock_basic returned no rows.")
    frame = frame.rename(columns={"code_name": "name", "ipoDate": "list_date"})
    frame["ts_code"] = frame["code"].map(_baostock_code_to_ts_code)
    frame["market"] = frame["ts_code"].astype(str).str[-2:]
    frame["industry"] = "未知"
    frame["list_date"] = frame["list_date"].astype(str).str.replace("-", "", regex=False)
    frame = frame[(frame["type"].astype(str) == "1") & (frame["status"].astype(str) == "1")].copy()
    frame = frame[frame["ts_code"].str.endswith((".SH", ".SZ"), na=False)].copy()
    return frame[["ts_code", "name", "industry", "market", "list_date"]].reset_index(drop=True)


def load_tencent_quote_snapshot(symbols: list[str], *, batch_size: int) -> tuple[object, object]:
    import pandas as pd

    if batch_size <= 0:
        raise ValueError("quote batch size must be positive")
    rows: list[dict[str, float | str]] = []
    unique_symbols = list(dict.fromkeys(symbols))
    for start in range(0, len(unique_symbols), batch_size):
        batch = unique_symbols[start : start + batch_size]
        text = _read_tencent_quote_batch(batch)
        rows.extend(_parse_tencent_quote_text(text))
        time.sleep(0.05)
    frame = pd.DataFrame(rows)
    if frame.empty:
        raise RuntimeError("Tencent quote snapshot returned no usable rows.")
    daily_basic = frame[["ts_code", "total_mv", "circ_mv"]].copy()
    daily_quote = frame[["ts_code", "amount"]].copy()
    return daily_basic, daily_quote


def _read_tencent_quote_batch(symbols: list[str], *, retries: int = 3) -> str:
    query = ",".join(_to_tencent_code(symbol) for symbol in symbols)
    url = f"{TENCENT_QUOTE_URL}{urlencode({'': query})[1:]}"
    request = Request(url, headers={"User-Agent": TENCENT_USER_AGENT, "Referer": "https://gu.qq.com/"})
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            with urlopen(request, timeout=15) as response:  # noqa: S310 - fixed public quote API.
                return response.read().decode("gb18030", errors="ignore")
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            time.sleep(0.3 * (attempt + 1))
    raise RuntimeError(f"Tencent quote request failed after {retries} attempts: {last_error}")


def _parse_tencent_quote_text(text: str) -> list[dict[str, float | str]]:
    rows: list[dict[str, float | str]] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or '="' not in line:
            continue
        key = line.split("=", 1)[0].replace("v_", "").strip().lower()
        body = line.split('="', 1)[1].rsplit('"', 1)[0]
        parts = body.split("~")
        if len(parts) < 58:
            continue
        symbol = _tencent_key_to_ts_code(key)
        total_mv_yi = _optional_float(parts[45])
        circ_mv_yi = _optional_float(parts[44])
        amount_wan = _optional_float(parts[57]) or _optional_float(parts[37])
        price = _optional_float(parts[3])
        if symbol is None or total_mv_yi is None or circ_mv_yi is None or amount_wan is None or price is None:
            continue
        if total_mv_yi <= 0 or circ_mv_yi <= 0 or amount_wan < 0 or price <= 0:
            continue
        rows.append(
            {
                "ts_code": symbol,
                "total_mv": total_mv_yi * 10_000.0,
                "circ_mv": circ_mv_yi * 10_000.0,
                "amount": amount_wan * 10.0,
            }
        )
    return rows


def _optional_float(value: str) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _baostock_code_to_ts_code(value: str) -> str:
    raw = value.strip().lower()
    if raw.startswith("sh."):
        return f"{raw[3:]}.SH"
    if raw.startswith("sz."):
        return f"{raw[3:]}.SZ"
    return raw.upper()


def _to_tencent_code(symbol: str) -> str:
    raw = symbol.strip().upper()
    if raw.endswith(".SH"):
        return f"sh{raw[:6]}"
    if raw.endswith(".SZ"):
        return f"sz{raw[:6]}"
    raise ValueError(f"unsupported Tencent quote symbol: {symbol}")


def _tencent_key_to_ts_code(key: str) -> str | None:
    if key.startswith("sh") and len(key) >= 8:
        return f"{key[2:8].upper()}.SH"
    if key.startswith("sz") and len(key) >= 8:
        return f"{key[2:8].upper()}.SZ"
    return None


if __name__ == "__main__":
    raise SystemExit(main())
