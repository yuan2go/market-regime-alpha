"""Tushare data access for A-share daily and minute bars."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CACHE_DIR = PROJECT_ROOT / "data" / "raw" / "tushare"
TUSHARE_TOKEN_ENV = "TUSHARE_TOKEN"
SUPPORTED_MINUTE_FREQS = ("1min", "5min", "15min", "30min", "60min")

BAR_COLUMNS = (
    "symbol",
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "amount",
    "source_freq",
)


class TushareConfigError(RuntimeError):
    """Raised when Tushare credentials or dependencies are missing."""


class TushareDataError(RuntimeError):
    """Raised when Tushare returns unusable data."""


@dataclass(frozen=True)
class BarQuery:
    symbol: str
    start: str | None = None
    end: str | None = None
    freq: str = "1min"
    use_cache: bool = True


def load_dotenv_if_available() -> None:
    """Load a local .env file when python-dotenv is installed."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(PROJECT_ROOT / ".env")


def get_tushare_token(token: str | None = None, env: dict[str, str] | None = None) -> str:
    if token:
        return token.strip()
    values = env if env is not None else os.environ
    value = values.get(TUSHARE_TOKEN_ENV, "").strip()
    if not value:
        raise TushareConfigError(
            f"Missing Tushare token. Set {TUSHARE_TOKEN_ENV}=your_token in the shell or in "
            f"{PROJECT_ROOT / '.env'}."
        )
    return value


def normalize_ts_code(value: str) -> str:
    raw = value.strip().upper()
    if not raw:
        raise ValueError("stock code cannot be empty")

    if re.fullmatch(r"\d{6}\.(SH|SZ|BJ)", raw):
        return raw
    if re.fullmatch(r"(SH|SZ|BJ)\d{6}", raw):
        return f"{raw[2:]}.{raw[:2]}"
    if not re.fullmatch(r"\d{6}", raw):
        raise ValueError("stock code must look like 600000.SH, 000001.SZ, SH600000, or 600000")

    if raw.startswith("6"):
        return f"{raw}.SH"
    if raw.startswith(("0", "2", "3")):
        return f"{raw}.SZ"
    if raw.startswith(("4", "8", "9")):
        return f"{raw}.BJ"
    raise ValueError(f"cannot infer exchange suffix for stock code {raw}")


def normalize_daily_date(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    raw = value.strip().replace("-", "")
    try:
        return datetime.strptime(raw, "%Y%m%d").strftime("%Y%m%d")
    except ValueError as exc:
        raise ValueError("daily date must be YYYYMMDD or YYYY-MM-DD") from exc


def normalize_minute_datetime(value: str | None, *, is_end: bool) -> str | None:
    if value is None or not value.strip():
        return None

    raw = value.strip().replace("T", " ")
    default_time = "15:30:00" if is_end else "09:00:00"
    if re.fullmatch(r"\d{8}", raw):
        raw = f"{raw[:4]}-{raw[4:6]}-{raw[6:]} {default_time}"
    elif re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        raw = f"{raw} {default_time}"
    elif re.fullmatch(r"\d{14}", raw):
        raw = f"{raw[:4]}-{raw[4:6]}-{raw[6:8]} {raw[8:10]}:{raw[10:12]}:{raw[12:]}"
    elif re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}", raw):
        raw = f"{raw}:00"

    try:
        return datetime.fromisoformat(raw).strftime("%Y-%m-%d %H:%M:%S")
    except ValueError as exc:
        raise ValueError("minute datetime must be YYYY-MM-DD HH:MM:SS, YYYY-MM-DD, or YYYYMMDD") from exc


def normalize_minute_freq(value: str) -> str:
    freq = value.strip().lower()
    if freq in {"1m", "1"}:
        freq = "1min"
    elif freq in {"5m", "5"}:
        freq = "5min"
    elif freq in {"15m", "15"}:
        freq = "15min"
    elif freq in {"30m", "30"}:
        freq = "30min"
    elif freq in {"60m", "60", "1h"}:
        freq = "60min"

    if freq not in SUPPORTED_MINUTE_FREQS:
        raise ValueError(f"minute freq must be one of: {', '.join(SUPPORTED_MINUTE_FREQS)}")
    return freq


def dataframe_records(frame: Any, *, limit: int | None = None) -> list[dict[str, Any]]:
    data = frame.head(limit) if limit else frame
    records = data.to_dict(orient="records")
    return [_clean_record(record) for record in records]


def build_tushare_client(
    *,
    token: str | None = None,
    cache_dir: str | Path = DEFAULT_CACHE_DIR,
    pro_api: Any | None = None,
) -> "TushareClient":
    load_dotenv_if_available()
    return TushareClient(token=token, cache_dir=cache_dir, pro_api=pro_api)


class TushareClient:
    def __init__(
        self,
        *,
        token: str | None = None,
        cache_dir: str | Path = DEFAULT_CACHE_DIR,
        pro_api: Any | None = None,
    ) -> None:
        self.cache_dir = Path(cache_dir)
        if pro_api is not None:
            self._pro = pro_api
            self._ts_module = None
            return

        resolved_token = get_tushare_token(token)
        try:
            import tushare as ts
        except ImportError as exc:
            raise TushareConfigError("Missing dependency: install tushare with `pip install tushare`.") from exc

        ts.set_token(resolved_token)
        self._pro = ts.pro_api(resolved_token)
        self._ts_module = ts

    def search_stocks(self, keyword: str, *, limit: int = 20, use_cache: bool = True) -> Any:
        if limit <= 0:
            raise ValueError("limit must be positive")

        frame = self._stock_basic(use_cache=use_cache)
        term = keyword.strip().upper()
        if term:
            name_term = keyword.strip()
            mask = (
                frame["ts_code"].astype(str).str.upper().str.contains(term, na=False)
                | frame["symbol"].astype(str).str.upper().str.contains(term, na=False)
                | frame["name"].astype(str).str.contains(name_term, na=False)
            )
            frame = frame[mask]
        return frame.head(limit)

    def stock_basic(self, *, use_cache: bool = True) -> Any:
        return self._stock_basic(use_cache=use_cache)

    def daily_basic_snapshot(self, trade_date: str, *, use_cache: bool = True) -> Any:
        normalized_date = normalize_daily_date(trade_date)
        if normalized_date is None:
            raise ValueError("trade_date is required")
        cache_path = self.cache_dir / "meta" / f"daily_basic_{normalized_date}.csv"
        if use_cache and cache_path.exists():
            return _read_csv(cache_path)
        try:
            frame = self._pro.daily_basic(
                trade_date=normalized_date,
                fields="ts_code,trade_date,total_mv,circ_mv,turnover_rate,turnover_rate_f,volume_ratio,pe,pb,ps,dv_ratio",
            )
        except Exception as exc:  # noqa: BLE001
            raise TushareDataError(f"Tushare daily_basic query failed: {exc}") from exc
        if frame is None or frame.empty:
            raise TushareDataError(f"Tushare daily_basic returned no rows for {normalized_date}.")
        frame = frame.sort_values("ts_code").reset_index(drop=True)
        self._write_cache(cache_path, frame)
        return frame

    def daily_market_snapshot(self, trade_date: str, *, use_cache: bool = True) -> Any:
        normalized_date = normalize_daily_date(trade_date)
        if normalized_date is None:
            raise ValueError("trade_date is required")
        cache_path = self.cache_dir / "meta" / f"daily_market_{normalized_date}.csv"
        if use_cache and cache_path.exists():
            return _read_csv(cache_path)
        try:
            frame = self._pro.daily(
                trade_date=normalized_date,
                fields="ts_code,trade_date,open,high,low,close,vol,amount",
            )
        except Exception as exc:  # noqa: BLE001
            raise TushareDataError(f"Tushare daily market query failed: {exc}") from exc
        if frame is None or frame.empty:
            raise TushareDataError(f"Tushare daily market returned no rows for {normalized_date}.")
        frame = frame.sort_values("ts_code").reset_index(drop=True)
        self._write_cache(cache_path, frame)
        return frame

    def daily_bars(
        self,
        symbol: str,
        *,
        start_date: str | None = None,
        end_date: str | None = None,
        use_cache: bool = True,
    ) -> Any:
        query = BarQuery(
            symbol=normalize_ts_code(symbol),
            start=normalize_daily_date(start_date),
            end=normalize_daily_date(end_date),
            freq="daily",
            use_cache=use_cache,
        )
        cache_path = self._cache_path("daily", query)
        if query.use_cache and cache_path.exists():
            return _read_csv(cache_path)

        try:
            raw = self._pro.daily(
                ts_code=query.symbol,
                start_date=query.start,
                end_date=query.end,
                fields="ts_code,trade_date,open,high,low,close,vol,amount",
            )
        except Exception as exc:  # noqa: BLE001 - third-party clients raise inconsistent exceptions.
            raise TushareDataError(f"Tushare daily query failed: {exc}") from exc

        data = normalize_daily_frame(raw)
        self._write_cache(cache_path, data)
        return data

    def minute_bars(
        self,
        symbol: str,
        *,
        freq: str = "1min",
        start_date: str | None = None,
        end_date: str | None = None,
        use_cache: bool = True,
    ) -> Any:
        query = BarQuery(
            symbol=normalize_ts_code(symbol),
            start=normalize_minute_datetime(start_date, is_end=False),
            end=normalize_minute_datetime(end_date, is_end=True),
            freq=normalize_minute_freq(freq),
            use_cache=use_cache,
        )
        cache_path = self._cache_path("minute", query)
        if query.use_cache and cache_path.exists():
            return _read_csv(cache_path)

        try:
            raw = self._pro.stk_mins(
                ts_code=query.symbol,
                freq=query.freq,
                start_date=query.start,
                end_date=query.end,
            )
        except AttributeError:
            raw = self._minute_bars_with_pro_bar(query)
        except Exception as exc:  # noqa: BLE001 - third-party clients raise inconsistent exceptions.
            raise TushareDataError(f"Tushare minute query failed: {exc}") from exc

        data = normalize_minute_frame(raw, source_freq=query.freq)
        self._write_cache(cache_path, data)
        return data

    def _minute_bars_with_pro_bar(self, query: BarQuery) -> Any:
        if self._ts_module is None:
            raise TushareDataError("The injected Tushare API object does not provide stk_mins.")
        try:
            return self._ts_module.pro_bar(
                ts_code=query.symbol,
                freq=query.freq,
                start_date=query.start,
                end_date=query.end,
                pro_api=self._pro,
            )
        except Exception as exc:  # noqa: BLE001
            raise TushareDataError(f"Tushare pro_bar minute query failed: {exc}") from exc

    def _stock_basic(self, *, use_cache: bool) -> Any:
        cache_path = self.cache_dir / "meta" / "stock_basic.csv"
        if use_cache and cache_path.exists():
            return _read_csv(cache_path)

        try:
            frame = self._pro.stock_basic(
                exchange="",
                list_status="L",
                fields="ts_code,symbol,name,area,industry,market,list_date",
            )
        except Exception as exc:  # noqa: BLE001
            raise TushareDataError(f"Tushare stock_basic query failed: {exc}") from exc

        if frame is None or frame.empty:
            raise TushareDataError("Tushare stock_basic returned no rows.")
        frame = frame.sort_values(["ts_code"]).reset_index(drop=True)
        self._write_cache(cache_path, frame)
        return frame

    def _cache_path(self, kind: Literal["daily", "minute"], query: BarQuery) -> Path:
        code = query.symbol.replace(".", "_")
        start = _cache_part(query.start, "start")
        end = _cache_part(query.end, "end")
        suffix = "daily" if kind == "daily" else query.freq
        return self.cache_dir / kind / f"{code}_{suffix}_{start}_{end}.csv"

    def _write_cache(self, path: Path, frame: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(path, index=False)


def normalize_daily_frame(frame: Any) -> Any:
    data = _require_columns(frame, {"ts_code", "trade_date", "open", "high", "low", "close", "vol"})
    data = data.rename(columns={"ts_code": "symbol", "trade_date": "timestamp", "vol": "volume"})
    data["timestamp"] = data["timestamp"].astype(str).map(_daily_timestamp)
    data["source_freq"] = "daily"
    if "amount" not in data.columns:
        data["amount"] = None
    return _select_bar_columns(data)


def normalize_minute_frame(frame: Any, *, source_freq: str) -> Any:
    data = _require_columns(frame, {"ts_code", "trade_time", "open", "high", "low", "close", "vol"})
    data = data.rename(columns={"ts_code": "symbol", "trade_time": "timestamp", "vol": "volume"})
    data["timestamp"] = data["timestamp"].astype(str).map(_minute_timestamp)
    data["source_freq"] = source_freq
    if "amount" not in data.columns:
        data["amount"] = None
    return _select_bar_columns(data)


def _require_columns(frame: Any, required: set[str]) -> Any:
    if frame is None:
        raise TushareDataError("Tushare returned no data frame.")
    if getattr(frame, "empty", False):
        raise TushareDataError("Tushare returned an empty data frame.")
    missing = sorted(required.difference(set(frame.columns)))
    if missing:
        raise TushareDataError(f"Tushare data is missing columns: {', '.join(missing)}")
    return frame.copy()


def _select_bar_columns(data: Any) -> Any:
    data = data.loc[:, list(BAR_COLUMNS)]
    data = data.sort_values("timestamp").reset_index(drop=True)
    for column in ("open", "high", "low", "close", "volume", "amount"):
        data[column] = data[column].astype("float64")
    return data


def _daily_timestamp(value: str) -> str:
    return datetime.strptime(value, "%Y%m%d").date().isoformat()


def _minute_timestamp(value: str) -> str:
    return datetime.fromisoformat(value.replace("T", " ")).strftime("%Y-%m-%d %H:%M:%S")


def _read_csv(path: Path) -> Any:
    try:
        import pandas as pd
    except ImportError as exc:
        raise TushareConfigError("Missing dependency: install pandas with `pip install pandas`.") from exc
    return pd.read_csv(path)


def _cache_part(value: str | None, fallback: str) -> str:
    if not value:
        return fallback
    return re.sub(r"[^0-9A-Za-z]+", "", value)


def _clean_record(record: dict[str, Any]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for key, value in record.items():
        if value != value:
            cleaned[key] = None
        else:
            cleaned[key] = value
    return cleaned
