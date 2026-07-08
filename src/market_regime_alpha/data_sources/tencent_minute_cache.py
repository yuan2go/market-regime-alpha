"""Tencent 1-minute intraday cache backed by DuckDB."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo

from market_regime_alpha.data_sources.a_share_bars import (
    AShareDataError,
    _read_tencent_minute_json,
    normalize_ts_code,
    to_tencent_code,
)
from market_regime_alpha.dividend_t.storage import DEFAULT_RESEARCH_DIR


SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")
DEFAULT_TENCENT_CACHE_DB = DEFAULT_RESEARCH_DIR / "research.duckdb"
TENCENT_1M_TABLE = "tencent_minute_bars_1m"


@dataclass(frozen=True)
class CacheWriteResult:
    symbol: str
    fetched_rows: int
    inserted_rows: int
    latest_timestamp: str | None
    database_path: str
    table: str = TENCENT_1M_TABLE

    def to_dict(self) -> dict[str, object]:
        return {
            "symbol": self.symbol,
            "fetched_rows": self.fetched_rows,
            "inserted_rows": self.inserted_rows,
            "latest_timestamp": self.latest_timestamp,
            "database_path": self.database_path,
            "table": self.table,
        }


def fetch_tencent_1min_frame(symbol: str, *, timeout_seconds: float = 3.0) -> Any:
    payload = _read_tencent_minute_json(symbol=symbol, timeout_seconds=timeout_seconds)
    return normalize_tencent_1min_payload(payload, symbol=symbol)


def normalize_tencent_1min_payload(payload: dict[str, Any], *, symbol: str) -> Any:
    import pandas as pd

    normalized = normalize_ts_code(symbol)
    stock = (payload.get("data") or {}).get(to_tencent_code(normalized)) or {}
    minute_data = stock.get("data") or {}
    rows = minute_data.get("data") or []
    date_text = str(minute_data.get("date") or "").strip()
    if not rows or not date_text:
        raise AShareDataError("Tencent minute query returned no 1-minute rows")

    records: list[dict[str, object]] = []
    previous_volume = 0.0
    previous_amount = 0.0
    for raw in rows:
        parts = str(raw).split()
        if len(parts) < 4:
            continue
        time_text, price_text, volume_text, amount_text = parts[:4]
        timestamp = datetime.strptime(f"{date_text}{time_text}", "%Y%m%d%H%M")
        price = float(price_text)
        cumulative_volume = float(volume_text) * 100.0
        cumulative_amount = float(amount_text)
        interval_volume = max(cumulative_volume - previous_volume, 0.0)
        interval_amount = max(cumulative_amount - previous_amount, 0.0)
        previous_volume = cumulative_volume
        previous_amount = cumulative_amount
        records.append(
            {
                "symbol": normalized,
                "timestamp": timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                "price": price,
                "close": price,
                "volume": interval_volume,
                "amount": interval_amount,
                "cumulative_volume": cumulative_volume,
                "cumulative_amount": cumulative_amount,
                "source": "tencent_minute_query_1min",
            }
        )
    if not records:
        raise AShareDataError("Tencent minute query returned no usable 1-minute rows")
    return pd.DataFrame(records)


def write_tencent_1min_cache(frame: Any, *, database_path: str | Path = DEFAULT_TENCENT_CACHE_DB) -> CacheWriteResult:
    import duckdb

    data = _prepare_cache_frame(frame)
    db_path = Path(database_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    symbol = str(data["symbol"].iloc[0])
    latest_timestamp = str(data["timestamp"].max()) if len(data) else None
    with duckdb.connect(str(db_path)) as connection:
        connection.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {TENCENT_1M_TABLE} (
                symbol VARCHAR NOT NULL,
                timestamp TIMESTAMP NOT NULL,
                price DOUBLE,
                close DOUBLE,
                volume DOUBLE,
                amount DOUBLE,
                cumulative_volume DOUBLE,
                cumulative_amount DOUBLE,
                source VARCHAR,
                fetched_at TIMESTAMP,
                PRIMARY KEY(symbol, timestamp)
            )
            """
        )
        before_count = _table_count(connection, symbol=symbol)
        connection.register("incoming_tencent_1m", data)
        connection.execute(
            f"""
            DELETE FROM {TENCENT_1M_TABLE}
            USING incoming_tencent_1m
            WHERE {TENCENT_1M_TABLE}.symbol = incoming_tencent_1m.symbol
              AND {TENCENT_1M_TABLE}.timestamp = incoming_tencent_1m.timestamp
            """
        )
        connection.execute(
            f"""
            INSERT INTO {TENCENT_1M_TABLE}
            SELECT symbol, timestamp, price, close, volume, amount,
                   cumulative_volume, cumulative_amount, source, fetched_at
            FROM incoming_tencent_1m
            """
        )
        connection.unregister("incoming_tencent_1m")
        after_count = _table_count(connection, symbol=symbol)
    return CacheWriteResult(
        symbol=symbol,
        fetched_rows=len(data),
        inserted_rows=max(after_count - before_count, 0),
        latest_timestamp=latest_timestamp,
        database_path=str(db_path),
    )


def cache_tencent_1min(symbols: Iterable[str], *, database_path: str | Path = DEFAULT_TENCENT_CACHE_DB, timeout_seconds: float = 3.0) -> list[CacheWriteResult]:
    results: list[CacheWriteResult] = []
    for symbol in symbols:
        frame = fetch_tencent_1min_frame(symbol, timeout_seconds=timeout_seconds)
        results.append(write_tencent_1min_cache(frame, database_path=database_path))
    return results


def is_a_share_market_session(now: datetime | None = None) -> bool:
    current = now.astimezone(SHANGHAI_TZ) if now is not None and now.tzinfo else (now or datetime.now(SHANGHAI_TZ))
    if current.weekday() >= 5:
        return False
    current_time = current.time()
    return time(9, 30) <= current_time <= time(11, 30) or time(13, 0) <= current_time <= time(15, 5)


def _prepare_cache_frame(frame: Any) -> Any:
    import pandas as pd

    required = {
        "symbol",
        "timestamp",
        "price",
        "close",
        "volume",
        "amount",
        "cumulative_volume",
        "cumulative_amount",
        "source",
    }
    if frame is None or getattr(frame, "empty", False):
        raise AShareDataError("Tencent 1-minute frame is empty")
    missing = sorted(required.difference(set(frame.columns)))
    if missing:
        raise AShareDataError(f"Tencent 1-minute frame is missing columns: {', '.join(missing)}")
    data = frame.copy()
    data["symbol"] = data["symbol"].map(normalize_ts_code)
    data["timestamp"] = pd.to_datetime(data["timestamp"])
    data["fetched_at"] = datetime.now(SHANGHAI_TZ).replace(tzinfo=None)
    data = data.drop_duplicates(subset=["symbol", "timestamp"], keep="last")
    return data.sort_values(["symbol", "timestamp"]).reset_index(drop=True)


def _table_count(connection: Any, *, symbol: str) -> int:
    value = connection.execute(f"SELECT COUNT(*) FROM {TENCENT_1M_TABLE} WHERE symbol = ?", [symbol]).fetchone()[0]
    return int(value)
