"""Free A-share bar data adapters with a shared normalized schema."""

from __future__ import annotations

from contextlib import redirect_stdout
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from io import StringIO
import json
import os
from pathlib import Path
import time
from typing import Any, Iterable, Protocol
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from market_regime_alpha.data_sources.tushare_client import load_dotenv_if_available, normalize_ts_code


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
BAOSTOCK_USER_ID_ENV = "BAOSTOCK_USER_ID"
BAOSTOCK_PASSWORD_ENV = "BAOSTOCK_PASSWORD"
BAOSTOCK_ANONYMOUS_USER_ID = "anonymous"
BAOSTOCK_ANONYMOUS_PASSWORD = "123456"
QMT_L1_AUTO_ENV = "QMT_L1_AUTO"
EASTMONEY_KLINE_URL = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
EASTMONEY_USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X) AppleWebKit/537.36"
TENCENT_MINUTE_URL = "https://web.ifzq.gtimg.cn/appstock/app/minute/query"
TENCENT_QUOTE_URL = "https://qt.gtimg.cn/q="
TENCENT_USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X) AppleWebKit/537.36"
MERGED_EASTMONEY_BAOSTOCK_SOURCE = "eastmoney_direct_5min+baostock_history_5min"
MERGED_TENCENT_BAOSTOCK_SOURCE = "tencent_minute_query_1min_to_5min+baostock_history_5min"
LOCAL_CACHE_TENCENT_SOURCE = "local_csv_5min+tencent_minute_query_1min_to_5min"
LOCAL_CACHE_SOURCE = "local_csv_5min"
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_LOCAL_5MIN_CACHE_DIR = PROJECT_ROOT / "data" / "raw" / "dividend_t_5min"


class AShareDataError(RuntimeError):
    """Raised when a free A-share data source cannot produce usable bars."""


class AShareBarProvider(Protocol):
    name: str
    data_source: str
    is_realtime: bool

    def minute_bars(
        self,
        symbol: str,
        *,
        freq: str = "5min",
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> Any:
        ...


@dataclass(frozen=True)
class BarFetchAttempt:
    provider: str
    success: bool
    rows: int = 0
    message: str = ""
    elapsed_seconds: float | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class BarFetchResult:
    bars: Any
    provider: str
    source: str
    is_realtime: bool
    attempts: tuple[BarFetchAttempt, ...]


@dataclass(frozen=True)
class LatestQuote:
    symbol: str
    current_price: float
    previous_close: float | None = None
    open_price: float | None = None
    high_price: float | None = None
    low_price: float | None = None
    change_pct: float | None = None
    quote_time: str | None = None
    source: str = "tencent_qt_quote"

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class FiveLevelBook:
    bid_prices: tuple[float, ...]
    bid_volumes: tuple[float, ...]
    ask_prices: tuple[float, ...]
    ask_volumes: tuple[float, ...]
    bid_amount: float
    ask_amount: float
    imbalance: float
    spread_bps: float | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class L1TickSnapshot:
    symbol: str
    current_price: float
    previous_close: float | None
    open_price: float | None
    high_price: float | None
    low_price: float | None
    volume: float | None
    amount: float | None
    timestamp: str | None
    book: FiveLevelBook
    source: str = "qmt_xtdata_get_full_tick"
    is_realtime: bool = True

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class MultiSourceDataError(AShareDataError):
    def __init__(self, attempts: Iterable[BarFetchAttempt]) -> None:
        self.attempts = tuple(attempts)
        summary = "; ".join(f"{item.provider}: {item.message}" for item in self.attempts)
        super().__init__(f"all configured A-share data sources failed: {summary}")


class QmtL1Provider:
    """QMT/miniQMT L1行情适配器。

    只读取行情，不下单。真实运行需要在已安装并登录 QMT/miniQMT 的机器上，
    且 Python 环境能导入 `xtquant.xtdata`。
    """

    name = "qmt_l1"
    data_source = "qmt_xtdata_l1_5min"
    is_realtime = True

    def __init__(self, *, xtdata: Any | None = None, auto_download: bool = True) -> None:
        self._xtdata = xtdata
        self.auto_download = auto_download

    @property
    def xtdata(self) -> Any:
        if self._xtdata is not None:
            return self._xtdata
        try:
            from xtquant import xtdata  # type: ignore[import-not-found]
        except ImportError as exc:
            raise AShareDataError("xtquant is not installed; QMT L1 needs a logged-in QMT/miniQMT runtime") from exc
        self._xtdata = xtdata
        return xtdata

    def minute_bars(
        self,
        symbol: str,
        *,
        freq: str = "5min",
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> Any:
        _minute_period(freq)
        qmt_symbol = normalize_ts_code(symbol)
        period = "5m"
        client = self.xtdata
        if self.auto_download and hasattr(client, "download_history_data"):
            try:
                client.download_history_data(
                    qmt_symbol,
                    period=period,
                    start_time=_qmt_datetime(start_date, is_end=False),
                    end_time=_qmt_datetime(end_date, is_end=True),
                )
            except TypeError:
                client.download_history_data(qmt_symbol, period, _qmt_datetime(start_date, is_end=False), _qmt_datetime(end_date, is_end=True))
            except Exception:
                # QMT 本地已有缓存时，下载失败不一定代表读取失败；继续尝试读取。
                pass

        try:
            payload = client.get_market_data_ex(
                [],
                [qmt_symbol],
                period=period,
                start_time=_qmt_datetime(start_date, is_end=False),
                end_time=_qmt_datetime(end_date, is_end=True),
                count=-1,
                dividend_type="none",
                fill_data=True,
            )
        except TypeError:
            payload = client.get_market_data_ex([], [qmt_symbol], period=period, count=-1)
        except Exception as exc:  # noqa: BLE001
            raise AShareDataError(f"QMT L1 minute query failed: {exc}") from exc
        return normalize_qmt_market_data_ex(payload, symbol=qmt_symbol)

    def tick_snapshots(self, symbols: Iterable[str]) -> dict[str, L1TickSnapshot]:
        normalized = [normalize_ts_code(symbol) for symbol in symbols]
        if not normalized:
            return {}
        try:
            payload = self.xtdata.get_full_tick(normalized)
        except Exception as exc:  # noqa: BLE001
            raise AShareDataError(f"QMT L1 tick query failed: {exc}") from exc
        output: dict[str, L1TickSnapshot] = {}
        for symbol, raw in (payload or {}).items():
            try:
                snapshot = normalize_qmt_tick_snapshot(raw, symbol=normalize_ts_code(str(symbol)))
            except Exception:
                continue
            output[snapshot.symbol] = snapshot
        return output


class TencentMinuteProvider:
    name = "tencent_direct"
    data_source = "tencent_minute_query_1min_to_5min"
    is_realtime = False

    def __init__(self, *, timeout_seconds: float = 8.0) -> None:
        self.timeout_seconds = timeout_seconds

    def minute_bars(
        self,
        symbol: str,
        *,
        freq: str = "5min",
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> Any:
        _minute_period(freq)
        payload = _read_tencent_minute_json(symbol=symbol, timeout_seconds=self.timeout_seconds)
        return normalize_tencent_minute_payload(payload, symbol=symbol)


class LocalCacheTencentProvider:
    """Fast intraday provider: local 5-minute cache plus Tencent active-session bars."""

    name = "fast"
    data_source = LOCAL_CACHE_TENCENT_SOURCE
    is_realtime = False

    def __init__(
        self,
        *,
        cache_dir: str | Path | None = None,
        tencent: TencentMinuteProvider | None = None,
    ) -> None:
        self.cache_dir = Path(cache_dir) if cache_dir is not None else DEFAULT_LOCAL_5MIN_CACHE_DIR
        self.tencent = tencent or TencentMinuteProvider(timeout_seconds=3.0)

    def minute_bars(
        self,
        symbol: str,
        *,
        freq: str = "5min",
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> Any:
        _minute_period(freq)
        history = _read_local_5min_cache(symbol, cache_dir=self.cache_dir, source_freq=f"{_minute_period(freq)}min")
        history = _filter_bar_time_range(history, start_date=start_date, end_date=end_date)
        try:
            intraday = self.tencent.minute_bars(symbol, freq=freq, start_date=start_date, end_date=end_date)
        except Exception as exc:  # noqa: BLE001
            history = history.copy()
            history.attrs["data_source"] = LOCAL_CACHE_SOURCE
            history.attrs["intraday_error"] = str(exc)
            return history

        return merge_history_with_intraday(
            history,
            intraday,
            session_date=_last_bar_date(intraday),
            data_source=LOCAL_CACHE_TENCENT_SOURCE,
        )


class TencentBaoStockHistoryProvider:
    """Use Tencent minute data for the active session and BaoStock only as history backfill."""

    name = "tencent"
    data_source = MERGED_TENCENT_BAOSTOCK_SOURCE
    is_realtime = False

    def __init__(
        self,
        *,
        tencent: TencentMinuteProvider | None = None,
        history: BaoStockADataProvider | None = None,
    ) -> None:
        self.tencent = tencent or TencentMinuteProvider()
        self.history = history or BaoStockADataProvider()

    def minute_bars(
        self,
        symbol: str,
        *,
        freq: str = "5min",
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> Any:
        intraday = self.tencent.minute_bars(symbol, freq=freq, start_date=start_date, end_date=end_date)
        session_date = _last_bar_date(intraday)
        try:
            history = self.history.minute_bars(
                symbol,
                freq=freq,
                start_date=start_date,
                end_date=session_date.isoformat(),
            )
        except Exception:  # noqa: BLE001 - BaoStock is a backfill helper; intraday data still has value.
            intraday = intraday.copy()
            intraday.attrs["data_source"] = self.tencent.data_source
            return intraday
        return merge_history_with_intraday(
            history,
            intraday,
            session_date=session_date,
            data_source=MERGED_TENCENT_BAOSTOCK_SOURCE,
        )


class EastMoneyDirectProvider:
    name = "eastmoney_direct"
    data_source = "eastmoney_direct_5min"
    is_realtime = False

    def __init__(self, *, timeout_seconds: float = 8.0) -> None:
        self.timeout_seconds = timeout_seconds

    def minute_bars(
        self,
        symbol: str,
        *,
        freq: str = "5min",
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> Any:
        period = _minute_period(freq)
        payload = _read_eastmoney_kline_json(
            symbol=symbol,
            period=period,
            start_date=start_date,
            end_date=end_date,
            timeout_seconds=self.timeout_seconds,
        )
        data = payload.get("data") or {}
        rows = data.get("klines") or []
        if not rows:
            raise AShareDataError("EastMoney minute query returned no rows")
        return normalize_eastmoney_minute_rows(rows, symbol=symbol, source_freq=f"{period}min")


class EastMoneyBaoStockHistoryProvider:
    """Use EastMoney for today's 5-minute bars and BaoStock only as history backfill."""

    name = "eastmoney"
    data_source = MERGED_EASTMONEY_BAOSTOCK_SOURCE
    is_realtime = False

    def __init__(
        self,
        *,
        eastmoney: EastMoneyDirectProvider | None = None,
        history: BaoStockADataProvider | None = None,
    ) -> None:
        self.eastmoney = eastmoney or EastMoneyDirectProvider()
        self.history = history or BaoStockADataProvider()

    def minute_bars(
        self,
        symbol: str,
        *,
        freq: str = "5min",
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> Any:
        session_date = _session_date(end_date)
        intraday = self.eastmoney.minute_bars(
            symbol,
            freq=freq,
            start_date=f"{session_date.isoformat()} 09:30:00",
            end_date=end_date,
        )
        try:
            history = self.history.minute_bars(
                symbol,
                freq=freq,
                start_date=start_date,
                end_date=session_date.isoformat(),
            )
        except Exception:  # noqa: BLE001 - BaoStock is a backfill helper; intraday data still has value.
            intraday = intraday.copy()
            intraday.attrs["data_source"] = self.eastmoney.data_source
            return intraday
        return merge_history_with_intraday(history, intraday, session_date=session_date)


class AkshareADataProvider:
    name = "akshare"
    data_source = "akshare_stock_zh_a_hist_min_em_5min"
    is_realtime = False

    def minute_bars(
        self,
        symbol: str,
        *,
        freq: str = "5min",
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> Any:
        try:
            import akshare as ak
        except ImportError as exc:
            raise AShareDataError("akshare is not installed") from exc

        period = _minute_period(freq)
        try:
            frame = ak.stock_zh_a_hist_min_em(
                symbol=to_plain_code(symbol),
                start_date=start_date or "1979-09-01 09:30:00",
                end_date=end_date or "2222-01-01 15:00:00",
                period=period,
                adjust="",
            )
        except Exception as exc:  # noqa: BLE001 - upstream clients raise mixed exception types.
            raise AShareDataError(f"AKShare minute query failed: {exc}") from exc

        return normalize_akshare_minute_frame(frame, symbol=symbol, source_freq=f"{period}min")


class BaoStockADataProvider:
    name = "baostock"
    data_source = "baostock_query_history_k_data_plus_5min"
    is_realtime = False

    def __init__(self, *, chunk_days: int = 120) -> None:
        self.chunk_days = max(1, chunk_days)

    def minute_bars(
        self,
        symbol: str,
        *,
        freq: str = "5min",
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> Any:
        try:
            import baostock as bs
            import pandas as pd
        except ImportError as exc:
            raise AShareDataError("baostock is not installed") from exc

        frequency = _minute_period(freq)
        user_id, password = baostock_credentials()
        with redirect_stdout(StringIO()):
            login = bs.login(user_id=user_id, password=password)
        try:
            if getattr(login, "error_code", "0") != "0":
                raise AShareDataError(f"BaoStock login failed: {login.error_msg}")
            frames = []
            query_ranges = _baostock_date_chunks(start_date, end_date, chunk_days=self.chunk_days)
            for chunk_start, chunk_end in query_ranges:
                rs = bs.query_history_k_data_plus(
                    to_baostock_code(symbol),
                    "date,time,code,open,high,low,close,volume,amount",
                    start_date=chunk_start,
                    end_date=chunk_end,
                    frequency=frequency,
                    adjustflag="3",
                )
                if getattr(rs, "error_code", "0") != "0":
                    raise AShareDataError(f"BaoStock minute query failed: {rs.error_msg}")
                rows: list[list[str]] = []
                while rs.next():
                    rows.append(rs.get_row_data())
                frames.append(pd.DataFrame(rows, columns=rs.fields))
            frame = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
            if not frame.empty:
                frame = frame.drop_duplicates(subset=["date", "time", "code"], keep="last")
        finally:
            with redirect_stdout(StringIO()):
                bs.logout()

        return normalize_baostock_minute_frame(frame, symbol=symbol, source_freq=f"{frequency}min")


class TushareADataProvider:
    name = "tushare"
    data_source = "tushare_stk_mins_5min"
    is_realtime = False

    def minute_bars(
        self,
        symbol: str,
        *,
        freq: str = "5min",
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> Any:
        try:
            from market_regime_alpha.data_sources.tushare_client import build_tushare_client
        except ImportError as exc:
            raise AShareDataError("tushare client is not available") from exc

        try:
            return build_tushare_client().minute_bars(
                symbol,
                freq=freq,
                start_date=start_date,
                end_date=end_date,
                use_cache=False,
            )
        except Exception as exc:  # noqa: BLE001
            raise AShareDataError(f"Tushare minute query failed: {exc}") from exc


class YFinanceADataProvider:
    name = "yfinance"
    data_source = "yfinance_5min"
    is_realtime = False

    def __init__(self, *, period: str = "60d", timeout_seconds: float = 20.0) -> None:
        self.period = period
        self.timeout_seconds = timeout_seconds

    def minute_bars(
        self,
        symbol: str,
        *,
        freq: str = "5min",
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> Any:
        _minute_period(freq)
        try:
            import yfinance as yf
        except ImportError as exc:
            raise AShareDataError("yfinance is not installed") from exc

        ticker = to_yfinance_ticker(symbol)
        try:
            frame = yf.download(
                ticker,
                period=self.period,
                interval="5m",
                progress=False,
                auto_adjust=False,
                threads=False,
                timeout=self.timeout_seconds,
            )
        except Exception as exc:  # noqa: BLE001
            raise AShareDataError(f"YFinance minute query failed: {exc}") from exc
        return normalize_yfinance_minute_frame(frame, symbol=symbol)


def fetch_a_share_5min_with_fallback(
    symbol: str,
    *,
    start_date: str,
    end_date: str,
    providers: Iterable[str | AShareBarProvider] | None = None,
    min_rows: int = 30,
) -> BarFetchResult:
    attempts: list[BarFetchAttempt] = []
    for provider in _provider_sequence(providers):
        started_at = time.perf_counter()
        try:
            bars = provider.minute_bars(symbol, freq="5min", start_date=start_date, end_date=end_date)
            row_count = len(bars)
            if row_count < min_rows:
                raise AShareDataError(f"only {row_count} rows returned; need at least {min_rows}")
            elapsed = round(time.perf_counter() - started_at, 3)
            attempt = BarFetchAttempt(provider=provider.name, success=True, rows=row_count, message="ok", elapsed_seconds=elapsed)
            attempts.append(attempt)
            source = getattr(bars, "attrs", {}).get("data_source", provider.data_source)
            return BarFetchResult(
                bars=bars,
                provider=provider.name,
                source=source,
                is_realtime=provider.is_realtime,
                attempts=tuple(attempts),
            )
        except Exception as exc:  # noqa: BLE001
            elapsed = round(time.perf_counter() - started_at, 3)
            attempts.append(BarFetchAttempt(provider=provider.name, success=False, message=str(exc), elapsed_seconds=elapsed))
    raise MultiSourceDataError(attempts)


def fetch_tencent_latest_quotes(symbols: Iterable[str], *, timeout_seconds: float = 8.0) -> dict[str, LatestQuote]:
    normalized_symbols = [normalize_ts_code(symbol) for symbol in symbols]
    if not normalized_symbols:
        return {}
    query = ",".join(to_tencent_code(symbol) for symbol in normalized_symbols)
    url = f"{TENCENT_QUOTE_URL}{query}"
    request = Request(url, headers={"User-Agent": TENCENT_USER_AGENT, "Referer": "https://gu.qq.com/"})
    try:
        with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310 - fixed public quote API.
            payload = response.read().decode("gb18030", errors="ignore")
    except Exception as exc:  # noqa: BLE001
        raise AShareDataError(f"Tencent quote query failed: {exc}") from exc
    return parse_tencent_quote_text(payload)


def parse_tencent_quote_text(text: str) -> dict[str, LatestQuote]:
    output: dict[str, LatestQuote] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or '="' not in line:
            continue
        code_key = line.split("=", 1)[0].replace("v_", "").strip()
        body = line.split('="', 1)[1].rsplit('"', 1)[0]
        parts = body.split("~")
        if len(parts) < 34:
            continue
        try:
            symbol = normalize_ts_code(code_key)
            current_price = float(parts[3])
            previous_close = _optional_float(parts[4])
            open_price = _optional_float(parts[5])
            high_price = _optional_float(parts[33])
            low_price = _optional_float(parts[34]) if len(parts) > 34 else None
            change_pct = _optional_float(parts[32])
        except (ValueError, IndexError):
            continue
        if current_price <= 0 and previous_close:
            current_price = previous_close
        if current_price <= 0:
            continue
        output[symbol] = LatestQuote(
            symbol=symbol,
            current_price=current_price,
            previous_close=previous_close,
            open_price=open_price,
            high_price=high_price,
            low_price=low_price,
            change_pct=change_pct,
            quote_time=parts[30] or None,
        )
    return output


def normalize_akshare_minute_frame(frame: Any, *, symbol: str, source_freq: str = "5min") -> Any:
    data = _require_columns(frame, {"时间", "开盘", "最高", "最低", "收盘", "成交量"})
    data = data.rename(
        columns={
            "时间": "timestamp",
            "开盘": "open",
            "最高": "high",
            "最低": "low",
            "收盘": "close",
            "成交量": "volume",
            "成交额": "amount",
        }
    )
    return _normalize_bar_frame(data, symbol=symbol, source_freq=source_freq)


def normalize_baostock_minute_frame(frame: Any, *, symbol: str, source_freq: str = "5min") -> Any:
    data = _require_columns(frame, {"date", "time", "open", "high", "low", "close", "volume"})
    data = data.copy()
    data["timestamp"] = data.apply(lambda row: _baostock_timestamp(row["date"], row["time"]), axis=1)
    return _normalize_bar_frame(data, symbol=symbol, source_freq=source_freq)


def normalize_eastmoney_minute_rows(rows: Iterable[str], *, symbol: str, source_freq: str = "5min") -> Any:
    import pandas as pd

    records: list[dict[str, str]] = []
    for raw in rows:
        parts = str(raw).split(",")
        if len(parts) < 7:
            continue
        records.append(
            {
                "timestamp": parts[0],
                "open": parts[1],
                "close": parts[2],
                "high": parts[3],
                "low": parts[4],
                "volume": parts[5],
                "amount": parts[6],
            }
        )
    if not records:
        raise AShareDataError("EastMoney minute rows are empty")
    return _normalize_bar_frame(pd.DataFrame(records), symbol=symbol, source_freq=source_freq)


def normalize_tencent_minute_payload(payload: dict[str, Any], *, symbol: str, source_freq: str = "5min") -> Any:
    import pandas as pd

    code_key = to_tencent_code(symbol)
    stock = (payload.get("data") or {}).get(code_key) or {}
    minute_data = stock.get("data") or {}
    rows = minute_data.get("data") or []
    date_text = str(minute_data.get("date") or "").strip()
    if not rows or not date_text:
        raise AShareDataError("Tencent minute query returned no rows")

    records: list[dict[str, object]] = []
    prev_volume = 0.0
    prev_amount = 0.0
    for raw in rows:
        parts = str(raw).split()
        if len(parts) < 4:
            continue
        time_text, price_text, volume_text, amount_text = parts[:4]
        timestamp = datetime.strptime(f"{date_text}{time_text}", "%Y%m%d%H%M")
        price = float(price_text)
        cumulative_volume = float(volume_text) * 100.0
        cumulative_amount = float(amount_text)
        interval_volume = max(cumulative_volume - prev_volume, 0.0)
        interval_amount = max(cumulative_amount - prev_amount, 0.0)
        prev_volume = cumulative_volume
        prev_amount = cumulative_amount
        if timestamp.strftime("%H%M") == "1300" and interval_volume == 0 and interval_amount == 0:
            continue
        records.append(
            {
                "timestamp": timestamp,
                "open": price,
                "high": price,
                "low": price,
                "close": price,
                "volume": interval_volume,
                "amount": interval_amount,
            }
        )
    if not records:
        raise AShareDataError("Tencent minute rows are empty")

    minute = pd.DataFrame(records)
    minute["bucket"] = minute["timestamp"].dt.floor("5min")
    data = minute.groupby("bucket", as_index=False).agg(
        timestamp=("bucket", "first"),
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
        amount=("amount", "sum"),
    )
    return _normalize_bar_frame(data, symbol=symbol, source_freq=source_freq)


def normalize_yfinance_minute_frame(frame: Any, *, symbol: str, source_freq: str = "5min") -> Any:
    import pandas as pd

    if frame is None or getattr(frame, "empty", False):
        raise AShareDataError("YFinance minute query returned no rows")
    data = frame.copy()
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = [str(column[0]) for column in data.columns]
    data = data.reset_index()
    timestamp_column = "Datetime" if "Datetime" in data.columns else "Date"
    data = data.rename(
        columns={
            timestamp_column: "timestamp",
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume",
        }
    )
    data["timestamp"] = pd.to_datetime(data["timestamp"]).dt.tz_localize(None)
    data["amount"] = data["close"] * data["volume"]
    return _normalize_bar_frame(data, symbol=symbol, source_freq=source_freq)


def normalize_qmt_market_data_ex(payload: Any, *, symbol: str, source_freq: str = "5min") -> Any:
    import pandas as pd

    normalized_symbol = normalize_ts_code(symbol)
    if isinstance(payload, dict):
        frame = payload.get(normalized_symbol)
        if frame is None:
            frame = payload.get(to_plain_code(normalized_symbol))
        if frame is None and payload:
            frame = next(iter(payload.values()))
    else:
        frame = payload
    if frame is None or getattr(frame, "empty", False):
        raise AShareDataError("QMT L1 minute query returned no rows")

    data = frame.copy()
    if not isinstance(data, pd.DataFrame):
        data = pd.DataFrame(data)
    if isinstance(data.index, pd.DatetimeIndex) and "timestamp" not in data.columns and "time" not in data.columns:
        data = data.reset_index().rename(columns={"index": "timestamp"})
    rename_map = {
        "time": "timestamp",
        "datetime": "timestamp",
        "date": "timestamp",
        "vol": "volume",
    }
    data = data.rename(columns={key: value for key, value in rename_map.items() if key in data.columns})
    if "timestamp" not in data.columns:
        raise AShareDataError("QMT L1 minute data is missing timestamp/time column")
    data["timestamp"] = data["timestamp"].map(_qmt_timestamp_text)
    return _normalize_bar_frame(data, symbol=normalized_symbol, source_freq=source_freq)


def normalize_qmt_tick_snapshot(raw: dict[str, Any], *, symbol: str) -> L1TickSnapshot:
    bid_prices = _float_tuple(_first_present(raw, ("bidPrice", "bid_price", "bidPrices", "bid_prices")), limit=5)
    ask_prices = _float_tuple(_first_present(raw, ("askPrice", "ask_price", "askPrices", "ask_prices")), limit=5)
    bid_volumes = _float_tuple(_first_present(raw, ("bidVol", "bid_volume", "bidVols", "bid_volumes")), limit=5)
    ask_volumes = _float_tuple(_first_present(raw, ("askVol", "ask_volume", "askVols", "ask_volumes")), limit=5)
    book = _five_level_book(
        bid_prices=bid_prices,
        bid_volumes=bid_volumes,
        ask_prices=ask_prices,
        ask_volumes=ask_volumes,
    )
    return L1TickSnapshot(
        symbol=normalize_ts_code(symbol),
        current_price=_first_float(raw, ("lastPrice", "last_price", "price", "now", "last")),
        previous_close=_optional_any_float(_first_present(raw, ("lastClose", "preClose", "pre_close", "previous_close"))),
        open_price=_optional_any_float(_first_present(raw, ("open", "openPrice", "open_price"))),
        high_price=_optional_any_float(_first_present(raw, ("high", "highPrice", "high_price"))),
        low_price=_optional_any_float(_first_present(raw, ("low", "lowPrice", "low_price"))),
        volume=_optional_any_float(_first_present(raw, ("volume", "vol"))),
        amount=_optional_any_float(_first_present(raw, ("amount", "turnover"))),
        timestamp=_optional_qmt_timestamp(_first_present(raw, ("time", "datetime", "timestamp"))),
        book=book,
    )


def merge_history_with_intraday(
    history: Any,
    intraday: Any,
    *,
    session_date: date | None = None,
    data_source: str = MERGED_EASTMONEY_BAOSTOCK_SOURCE,
) -> Any:
    import pandas as pd

    if history is None or getattr(history, "empty", False):
        raise AShareDataError("history backfill bars are empty")
    if intraday is None or getattr(intraday, "empty", False):
        raise AShareDataError("intraday bars are empty")

    intraday_frame = _require_columns(intraday, set(BAR_COLUMNS))
    history_frame = _require_columns(history, set(BAR_COLUMNS))
    intraday_times = pd.to_datetime(intraday_frame["timestamp"])
    session = session_date or intraday_times.dt.date.max()
    history_frame = history_frame[pd.to_datetime(history_frame["timestamp"]).dt.date < session]
    combined = pd.concat([history_frame, intraday_frame], ignore_index=True)
    combined["timestamp"] = pd.to_datetime(combined["timestamp"]).dt.strftime("%Y-%m-%d %H:%M:%S")
    combined = combined.drop_duplicates(subset=["timestamp"], keep="last")
    combined = combined.sort_values("timestamp").reset_index(drop=True)
    combined = combined.loc[:, list(BAR_COLUMNS)]
    combined.attrs["data_source"] = data_source
    if combined.empty:
        raise AShareDataError("merged history and intraday bars are empty")
    return combined


def _read_local_5min_cache(symbol: str, *, cache_dir: Path, source_freq: str = "5min") -> Any:
    import pandas as pd

    normalized = normalize_ts_code(symbol)
    path = cache_dir / f"{normalized}_5min.csv"
    if not path.exists():
        raise AShareDataError(f"local 5min cache not found: {path}")
    try:
        frame = pd.read_csv(path)
    except Exception as exc:  # noqa: BLE001
        raise AShareDataError(f"local 5min cache read failed: {exc}") from exc
    data = _normalize_bar_frame(frame, symbol=normalized, source_freq=source_freq)
    data.attrs["data_source"] = LOCAL_CACHE_SOURCE
    return data


def _filter_bar_time_range(frame: Any, *, start_date: str | None, end_date: str | None) -> Any:
    import pandas as pd

    data = _require_columns(frame, set(BAR_COLUMNS))
    times = pd.to_datetime(data["timestamp"])
    if start_date:
        data = data[times >= pd.Timestamp(start_date)]
        times = pd.to_datetime(data["timestamp"])
    if end_date:
        data = data[times <= pd.Timestamp(end_date)]
    if data.empty:
        raise AShareDataError("local 5min cache has no rows in requested range")
    data = data.reset_index(drop=True)
    data.attrs["data_source"] = getattr(frame, "attrs", {}).get("data_source", LOCAL_CACHE_SOURCE)
    return data


def baostock_credentials(env: dict[str, str] | None = None) -> tuple[str, str]:
    if env is None:
        load_dotenv_if_available()
        env = os.environ
    user_id = env.get(BAOSTOCK_USER_ID_ENV, "").strip() or BAOSTOCK_ANONYMOUS_USER_ID
    password = env.get(BAOSTOCK_PASSWORD_ENV, "").strip() or BAOSTOCK_ANONYMOUS_PASSWORD
    return user_id, password


def provider_options() -> list[dict[str, str]]:
    return [
        {"value": "fast", "label": "盘中快速：本地5分钟缓存 + Tencent"},
        {"value": "auto", "label": "自动快速：QMT(开启时) -> 本地缓存+Tencent -> Tencent -> EastMoney -> AKShare"},
        {"value": "qmt", "label": "QMT L1 实时行情 + 本地分钟线"},
        {"value": "strict", "label": "完整慢速：Tencent/EastMoney + BaoStock/YFinance/Tushare"},
        {"value": "tencent", "label": "腾讯盘中 + BaoStock 历史"},
        {"value": "tencent-direct", "label": "腾讯盘中直连"},
        {"value": "eastmoney", "label": "EastMoney 盘中 + BaoStock 历史"},
        {"value": "eastmoney-direct", "label": "EastMoney 盘中直连"},
        {"value": "akshare", "label": "AKShare 免费"},
        {"value": "baostock", "label": "BaoStock 历史回补"},
        {"value": "yfinance", "label": "YFinance 历史分钟线"},
        {"value": "tushare", "label": "Tushare 基础权限"},
    ]


def to_plain_code(symbol: str) -> str:
    return normalize_ts_code(symbol).split(".", 1)[0]


def to_baostock_code(symbol: str) -> str:
    ts_code = normalize_ts_code(symbol)
    code, exchange = ts_code.split(".", 1)
    return f"{exchange.lower()}.{code}"


def to_eastmoney_secid(symbol: str) -> str:
    ts_code = normalize_ts_code(symbol)
    code, exchange = ts_code.split(".", 1)
    market_id = "1" if exchange == "SH" else "0"
    return f"{market_id}.{code}"


def to_tencent_code(symbol: str) -> str:
    ts_code = normalize_ts_code(symbol)
    code, exchange = ts_code.split(".", 1)
    return f"{exchange.lower()}{code}"


def to_yfinance_ticker(symbol: str) -> str:
    ts_code = normalize_ts_code(symbol)
    code, exchange = ts_code.split(".", 1)
    suffix = "SS" if exchange == "SH" else "SZ"
    return f"{code}.{suffix}"


def _provider_sequence(providers: Iterable[str | AShareBarProvider] | None) -> list[AShareBarProvider]:
    if providers is None:
        providers = ("auto",)

    output: list[AShareBarProvider] = []
    for item in providers:
        if isinstance(item, str):
            key = item.strip().lower()
            if key in {"auto", "free", ""}:
                if _qmt_auto_enabled():
                    output.append(QmtL1Provider())
                output.extend(
                    [
                        LocalCacheTencentProvider(),
                        TencentMinuteProvider(timeout_seconds=3.0),
                        EastMoneyDirectProvider(timeout_seconds=3.0),
                        AkshareADataProvider(),
                    ]
                )
            elif key in {"strict", "full", "slow"}:
                if _qmt_auto_enabled():
                    output.append(QmtL1Provider())
                output.extend(
                    [
                        LocalCacheTencentProvider(),
                        TencentBaoStockHistoryProvider(),
                        EastMoneyBaoStockHistoryProvider(),
                        AkshareADataProvider(),
                        BaoStockADataProvider(),
                        YFinanceADataProvider(),
                        TushareADataProvider(),
                    ]
                )
            elif key in {"fast", "local-cache", "local_cache", "local-cache+tencent", "local_cache+tencent"}:
                output.append(LocalCacheTencentProvider())
            elif key in {"qmt", "qmt_l1", "qmt-l1"}:
                output.append(QmtL1Provider())
            elif key in {"tencent", "tencent+baostock"}:
                output.append(TencentBaoStockHistoryProvider())
            elif key in {"tencent-direct", "tencent_direct"}:
                output.append(TencentMinuteProvider())
            elif key in {"eastmoney", "eastmoney+baostock"}:
                output.append(EastMoneyBaoStockHistoryProvider())
            elif key in {"eastmoney-direct", "eastmoney_direct"}:
                output.append(EastMoneyDirectProvider())
            elif key == "akshare":
                output.append(AkshareADataProvider())
            elif key in {"baostock", "bao"}:
                output.append(BaoStockADataProvider())
            elif key in {"yfinance", "yahoo"}:
                output.append(YFinanceADataProvider())
            elif key == "tushare":
                output.append(TushareADataProvider())
            else:
                raise ValueError(f"unknown A-share data provider: {item}")
        else:
            output.append(item)
    return output


def _normalize_bar_frame(data: Any, *, symbol: str, source_freq: str) -> Any:
    frame = data.copy()
    frame["symbol"] = normalize_ts_code(symbol)
    frame["timestamp"] = frame["timestamp"].astype(str).map(_timestamp_text)
    if "amount" not in frame.columns:
        frame["amount"] = None
    frame["source_freq"] = source_freq
    for column in ("open", "high", "low", "close", "volume", "amount"):
        frame[column] = _to_numeric(frame[column])
    frame["amount"] = frame["amount"].fillna(frame["close"] * frame["volume"])
    frame = frame.loc[:, list(BAR_COLUMNS)]
    frame = frame.dropna(subset=["open", "high", "low", "close"])
    frame = frame[(frame["close"] > 0) & (frame["high"] > 0) & (frame["low"] > 0)]
    if frame.empty:
        raise AShareDataError("normalized minute bars are empty")
    return frame.sort_values("timestamp").reset_index(drop=True)


def _require_columns(frame: Any, required: set[str]) -> Any:
    if frame is None or getattr(frame, "empty", False):
        raise AShareDataError("data source returned no rows")
    missing = sorted(required.difference(set(frame.columns)))
    if missing:
        raise AShareDataError(f"data source is missing columns: {', '.join(missing)}")
    return frame.copy()


def _minute_period(freq: str) -> str:
    value = freq.strip().lower()
    if value in {"5", "5m", "5min"}:
        return "5"
    raise ValueError("only 5-minute bars are supported in the COSCO timing flow")


def _read_eastmoney_kline_json(
    *,
    symbol: str,
    period: str,
    start_date: str | None,
    end_date: str | None,
    timeout_seconds: float,
) -> dict[str, Any]:
    params = {
        "secid": to_eastmoney_secid(symbol),
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
        "klt": period,
        "fqt": "0",
        "beg": _eastmoney_datetime(start_date, is_end=False),
        "end": _eastmoney_datetime(end_date, is_end=True),
    }
    url = f"{EASTMONEY_KLINE_URL}?{urlencode(params)}"
    request = Request(url, headers={"User-Agent": EASTMONEY_USER_AGENT, "Referer": "https://quote.eastmoney.com/"})
    try:
        with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310 - fixed public quote API.
            return json.loads(response.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise AShareDataError(f"EastMoney minute query failed: {exc}") from exc


def _read_tencent_minute_json(*, symbol: str, timeout_seconds: float) -> dict[str, Any]:
    params = {"code": to_tencent_code(symbol)}
    url = f"{TENCENT_MINUTE_URL}?{urlencode(params)}"
    request = Request(url, headers={"User-Agent": TENCENT_USER_AGENT, "Referer": "https://gu.qq.com/"})
    try:
        with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310 - fixed public quote API.
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise AShareDataError(f"Tencent minute query failed: {exc}") from exc
    if payload.get("code") not in {0, "0"}:
        raise AShareDataError(f"Tencent minute query failed: {payload.get('msg') or payload.get('message')}")
    return payload


def _eastmoney_datetime(value: str | None, *, is_end: bool) -> str:
    if not value:
        return "22220101150000" if is_end else "19790901093000"
    raw = value.strip().replace("T", " ")
    if len(raw) == 10:
        raw = f"{raw} {'15:00:00' if is_end else '09:30:00'}"
    return datetime.fromisoformat(raw).strftime("%Y%m%d%H%M%S")


def _session_date(end_date: str | None) -> date:
    if not end_date:
        return datetime.now().date()
    raw = end_date.strip().replace("T", " ")
    if len(raw) == 10:
        return datetime.fromisoformat(raw).date()
    return datetime.fromisoformat(raw).date()


def _last_bar_date(frame: Any) -> date:
    import pandas as pd

    data = _require_columns(frame, {"timestamp"})
    return pd.to_datetime(data["timestamp"]).dt.date.max()


def _date_only(value: str | None) -> str | None:
    if not value:
        return None
    return value[:10]


def _baostock_date_chunks(start_date: str | None, end_date: str | None, *, chunk_days: int) -> list[tuple[str | None, str | None]]:
    start_text = _date_only(start_date)
    end_text = _date_only(end_date)
    if not start_text or not end_text:
        return [(start_text, end_text)]
    start = datetime.fromisoformat(start_text).date()
    end = datetime.fromisoformat(end_text).date()
    if start > end:
        return [(start_text, end_text)]
    ranges: list[tuple[str, str]] = []
    current = start
    step = timedelta(days=max(1, chunk_days) - 1)
    while current <= end:
        chunk_end = min(current + step, end)
        ranges.append((current.isoformat(), chunk_end.isoformat()))
        current = chunk_end + timedelta(days=1)
    return ranges


def _timestamp_text(value: str) -> str:
    raw = value.strip().replace("T", " ")
    if len(raw) == 8 and raw.isdigit():
        raw = f"{raw[:4]}-{raw[4:6]}-{raw[6:8]} 00:00:00"
    return datetime.fromisoformat(raw).strftime("%Y-%m-%d %H:%M:%S")


def _qmt_datetime(value: str | None, *, is_end: bool) -> str:
    if not value:
        return ""
    raw = value.strip().replace("T", " ")
    if len(raw) == 10:
        raw = f"{raw} {'15:00:00' if is_end else '09:30:00'}"
    return datetime.fromisoformat(raw).strftime("%Y%m%d%H%M%S")


def _qmt_timestamp_text(value: Any) -> str:
    raw = str(value).strip()
    if not raw:
        raise ValueError("empty QMT timestamp")
    if raw.isdigit():
        if len(raw) >= 17:
            raw = raw[:14]
        if len(raw) == 13:
            return datetime.fromtimestamp(int(raw) / 1000.0).strftime("%Y-%m-%d %H:%M:%S")
        if len(raw) == 10:
            return datetime.fromtimestamp(int(raw)).strftime("%Y-%m-%d %H:%M:%S")
        if len(raw) >= 14:
            return datetime.strptime(raw[:14], "%Y%m%d%H%M%S").strftime("%Y-%m-%d %H:%M:%S")
        if len(raw) == 8:
            return datetime.strptime(raw, "%Y%m%d").strftime("%Y-%m-%d 00:00:00")
    return _timestamp_text(raw)


def _optional_qmt_timestamp(value: Any) -> str | None:
    if value is None:
        return None
    try:
        return _qmt_timestamp_text(value)
    except Exception:  # noqa: BLE001
        return None


def _baostock_timestamp(date_value: str, time_value: str) -> str:
    raw = str(time_value).strip()
    if raw.isdigit() and len(raw) >= 14:
        return datetime.strptime(raw[:14], "%Y%m%d%H%M%S").strftime("%Y-%m-%d %H:%M:%S")
    if raw:
        return _timestamp_text(raw)
    return _timestamp_text(f"{date_value} 00:00:00")


def _to_numeric(values: Any) -> Any:
    import pandas as pd

    return pd.to_numeric(values, errors="coerce")


def _optional_float(value: str) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _qmt_auto_enabled(env: dict[str, str] | None = None) -> bool:
    source = os.environ if env is None else env
    return source.get(QMT_L1_AUTO_ENV, "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _first_present(raw: dict[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        if key in raw and raw[key] is not None:
            return raw[key]
    return None


def _optional_any_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _first_float(raw: dict[str, Any], keys: Iterable[str]) -> float:
    value = _optional_any_float(_first_present(raw, keys))
    if value is None:
        raise AShareDataError("QMT tick snapshot is missing current price")
    return value


def _float_tuple(value: Any, *, limit: int) -> tuple[float, ...]:
    if value is None:
        return tuple(0.0 for _ in range(limit))
    if isinstance(value, str):
        parts = value.replace("|", ",").replace(";", ",").split(",")
    else:
        try:
            parts = list(value)
        except TypeError:
            parts = [value]
    parsed: list[float] = []
    for item in parts[:limit]:
        parsed.append(_optional_any_float(item) or 0.0)
    while len(parsed) < limit:
        parsed.append(0.0)
    return tuple(parsed)


def _five_level_book(
    *,
    bid_prices: tuple[float, ...],
    bid_volumes: tuple[float, ...],
    ask_prices: tuple[float, ...],
    ask_volumes: tuple[float, ...],
) -> FiveLevelBook:
    bid_amount = sum(price * volume for price, volume in zip(bid_prices, bid_volumes, strict=False) if price > 0 and volume > 0)
    ask_amount = sum(price * volume for price, volume in zip(ask_prices, ask_volumes, strict=False) if price > 0 and volume > 0)
    denominator = bid_amount + ask_amount
    imbalance = (bid_amount - ask_amount) / denominator if denominator > 0 else 0.0
    best_bid = next((price for price in bid_prices if price > 0), None)
    best_ask = next((price for price in ask_prices if price > 0), None)
    mid = ((best_bid or 0.0) + (best_ask or 0.0)) / 2.0
    spread_bps = ((best_ask - best_bid) / mid * 10_000.0) if best_bid and best_ask and mid > 0 else None
    return FiveLevelBook(
        bid_prices=bid_prices,
        bid_volumes=bid_volumes,
        ask_prices=ask_prices,
        ask_volumes=ask_volumes,
        bid_amount=round(bid_amount, 2),
        ask_amount=round(ask_amount, 2),
        imbalance=round(imbalance, 4),
        spread_bps=round(spread_bps, 2) if spread_bps is not None else None,
    )
