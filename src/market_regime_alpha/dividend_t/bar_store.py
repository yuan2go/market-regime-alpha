"""Fast local bar storage helpers for 5-minute A-share backtests."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
import subprocess
from typing import Any, Iterable


BAR_STORE_BACKEND_ENV = "QUANT_5MIN_BAR_BACKEND"
PARQUET_DIR_ENV = "QUANT_5MIN_PARQUET_DIR"
POSTGRES_DSN_ENV = "QUANT_5MIN_POSTGRES_DSN"
POSTGRES_TABLE_ENV = "QUANT_5MIN_POSTGRES_TABLE"
DEFAULT_POSTGRES_TABLE = "public.bars_5min"
BAR_STORE_COLUMNS = (
    "symbol",
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "amount",
    "source_freq",
    "is_suspended",
    "is_st",
    "prev_close",
    "cash_dividend_per_share",
    "share_bonus_ratio",
)
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(frozen=True)
class BuiltBarFile:
    symbol: str
    rows: int
    start: str
    end: str
    csv_path: Path
    parquet_path: Path | None = None
    postgres_rows: int = 0


@dataclass(frozen=True)
class BarStoreBuildResult:
    csv_dir: Path
    parquet_dir: Path | None
    manifest_path: Path | None
    file_count: int
    row_count: int
    postgres_table: str | None = None


def load_raw_5min_bars_path(
    path: str | Path,
    *,
    symbol: str,
    backend: str | None = None,
    parquet_dir: str | Path | None = None,
    postgres_dsn: str | None = None,
    postgres_table: str | None = None,
) -> Any:
    """Load raw 5-minute bars from Parquet, PostgreSQL, or CSV.

    ``backend='auto'`` prefers PostgreSQL when a DSN is configured, then Parquet,
    then CSV. Existing callers can keep passing the original CSV directory; a
    sibling ``<csv_dir>_parquet`` store is detected automatically.
    """

    selected_backend = (backend or os.getenv(BAR_STORE_BACKEND_ENV, "auto")).strip().lower()
    if selected_backend not in {"auto", "parquet", "postgres", "postgresql", "csv"}:
        raise ValueError("bar store backend must be one of auto, parquet, postgres, csv")
    dsn = postgres_dsn or os.getenv(POSTGRES_DSN_ENV)
    table = postgres_table or os.getenv(POSTGRES_TABLE_ENV, DEFAULT_POSTGRES_TABLE)
    if selected_backend in {"auto", "postgres", "postgresql"} and dsn:
        try:
            return load_raw_5min_bars_postgres(dsn, table=table, symbol=symbol)
        except ModuleNotFoundError:
            if selected_backend in {"postgres", "postgresql"}:
                raise
        except Exception:
            if selected_backend in {"postgres", "postgresql"}:
                raise
    data_path = Path(path)
    if selected_backend in {"auto", "parquet"}:
        parquet_path = _find_parquet_path(data_path, symbol=symbol, parquet_dir=parquet_dir)
        if parquet_path is not None:
            return _read_parquet(parquet_path, symbol=symbol)
        if selected_backend == "parquet":
            raise FileNotFoundError(f"no 5-minute Parquet found for {symbol} near {data_path}")
    return _read_csv_path(data_path, symbol=symbol)


def load_raw_5min_bars_csv(path: str | Path, *, symbol: str | None = None) -> Any:
    return _read_csv_path(Path(path), symbol=symbol)


def load_raw_5min_bars_postgres(dsn: str, *, table: str = DEFAULT_POSTGRES_TABLE, symbol: str) -> Any:
    try:
        import psycopg
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError("PostgreSQL bar loading requires psycopg; install with `pip install psycopg[binary]`.") from exc

    import pandas as pd

    sql = f"""
        SELECT {", ".join(BAR_STORE_COLUMNS)}
        FROM {_sql_table_identifier(table)}
        WHERE symbol = %s
        ORDER BY timestamp
    """
    with psycopg.connect(dsn) as connection:
        return pd.read_sql_query(sql, connection, params=(symbol,))


def build_parquet_bar_store(
    csv_dir: str | Path,
    *,
    parquet_dir: str | Path | None = None,
    symbols: Iterable[str] | None = None,
    overwrite: bool = False,
    compression: str = "zstd",
) -> BarStoreBuildResult:
    import pandas as pd

    source_dir = Path(csv_dir)
    if not source_dir.exists():
        raise FileNotFoundError(source_dir)
    target_dir = Path(parquet_dir) if parquet_dir is not None else default_parquet_dir_for_csv_dir(source_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    symbol_filter = {symbol.upper() for symbol in symbols} if symbols else None
    records: list[BuiltBarFile] = []
    for csv_path in iter_5min_csv_files(source_dir):
        symbol = symbol_from_bar_file(csv_path)
        if symbol_filter is not None and symbol.upper() not in symbol_filter:
            continue
        output = target_dir / f"{symbol}_5min.parquet"
        if output.exists() and not overwrite:
            frame = pd.read_parquet(output, columns=["timestamp"])
            records.append(
                BuiltBarFile(
                    symbol=symbol,
                    rows=len(frame),
                    start=str(frame["timestamp"].min()),
                    end=str(frame["timestamp"].max()),
                    csv_path=csv_path,
                    parquet_path=output,
                )
            )
            continue
        frame = normalize_raw_bar_frame(pd.read_csv(csv_path), symbol=symbol)
        frame.to_parquet(output, index=False, compression=compression)
        records.append(
            BuiltBarFile(
                symbol=symbol,
                rows=len(frame),
                start=str(frame["timestamp"].min()),
                end=str(frame["timestamp"].max()),
                csv_path=csv_path,
                parquet_path=output,
            )
        )
    manifest_path = write_bar_store_manifest(records, target_dir / "bar_store_manifest.csv")
    return BarStoreBuildResult(
        csv_dir=source_dir,
        parquet_dir=target_dir,
        manifest_path=manifest_path,
        file_count=len(records),
        row_count=sum(record.rows for record in records),
    )


def import_csv_dir_to_postgres(
    csv_dir: str | Path,
    *,
    dsn: str,
    table: str = DEFAULT_POSTGRES_TABLE,
    symbols: Iterable[str] | None = None,
    replace_symbols: bool = True,
    psql_bin: str = "psql",
) -> BarStoreBuildResult:
    source_dir = Path(csv_dir)
    if not source_dir.exists():
        raise FileNotFoundError(source_dir)
    symbol_filter = {symbol.upper() for symbol in symbols} if symbols else None
    _psql_execute(psql_bin, dsn, _postgres_create_table_sql(table))
    records: list[BuiltBarFile] = []
    for csv_path in iter_5min_csv_files(source_dir):
        symbol = symbol_from_bar_file(csv_path)
        if symbol_filter is not None and symbol.upper() not in symbol_filter:
            continue
        frame = normalize_raw_bar_frame(_read_csv_path(csv_path, symbol=symbol), symbol=symbol)
        if replace_symbols:
            _psql_execute(psql_bin, dsn, f"DELETE FROM {_sql_table_identifier(table)} WHERE symbol = {_sql_literal(symbol)};")
        csv_payload = frame.loc[:, BAR_STORE_COLUMNS].to_csv(index=False)
        _psql_copy(psql_bin, dsn, table=table, csv_payload=csv_payload)
        records.append(
            BuiltBarFile(
                symbol=symbol,
                rows=len(frame),
                start=str(frame["timestamp"].min()),
                end=str(frame["timestamp"].max()),
                csv_path=csv_path,
                postgres_rows=len(frame),
            )
        )
    return BarStoreBuildResult(
        csv_dir=source_dir,
        parquet_dir=None,
        manifest_path=None,
        file_count=len(records),
        row_count=sum(record.rows for record in records),
        postgres_table=table,
    )


def iter_5min_csv_files(csv_dir: str | Path) -> list[Path]:
    return sorted(Path(csv_dir).glob("*_5min.csv"))


def default_parquet_dir_for_csv_dir(csv_dir: str | Path) -> Path:
    source_dir = Path(csv_dir)
    return source_dir.with_name(f"{source_dir.name}_parquet")


def symbol_from_bar_file(path: str | Path) -> str:
    name = Path(path).name
    if name.endswith("_5min.csv"):
        return name[: -len("_5min.csv")]
    if name.endswith("_5min.parquet"):
        return name[: -len("_5min.parquet")]
    return Path(path).stem


def normalize_raw_bar_frame(frame: Any, *, symbol: str | None = None) -> Any:
    import pandas as pd

    data = frame.copy()
    if symbol is not None:
        data["symbol"] = symbol
    if "symbol" not in data.columns:
        raise ValueError("bar frame missing required field: symbol")
    if "timestamp" not in data.columns:
        raise ValueError("bar frame missing required field: timestamp")
    data["symbol"] = data["symbol"].astype(str)
    data["timestamp"] = pd.to_datetime(data["timestamp"])
    for column in ("open", "high", "low", "close", "volume"):
        if column not in data.columns:
            raise ValueError(f"bar frame missing required field: {column}")
        data[column] = pd.to_numeric(data[column], errors="coerce")
    if "amount" not in data.columns:
        data["amount"] = data["close"] * data["volume"]
    data["amount"] = pd.to_numeric(data["amount"], errors="coerce").fillna(data["close"] * data["volume"])
    if "source_freq" not in data.columns:
        data["source_freq"] = "5min"
    if "is_suspended" not in data.columns:
        data["is_suspended"] = False
    if "is_st" not in data.columns:
        data["is_st"] = False
    if "prev_close" not in data.columns:
        data["prev_close"] = None
    if "cash_dividend_per_share" not in data.columns:
        data["cash_dividend_per_share"] = 0.0
    if "share_bonus_ratio" not in data.columns:
        data["share_bonus_ratio"] = 0.0
    return data.loc[:, BAR_STORE_COLUMNS].sort_values(["symbol", "timestamp"]).reset_index(drop=True)


def write_bar_store_manifest(records: Iterable[BuiltBarFile], path: str | Path) -> Path:
    import pandas as pd

    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        {
            "symbol": record.symbol,
            "rows": record.rows,
            "start": record.start,
            "end": record.end,
            "csv_path": str(record.csv_path),
            "parquet_path": str(record.parquet_path) if record.parquet_path is not None else "",
            "postgres_rows": record.postgres_rows,
        }
        for record in records
    ).to_csv(output, index=False)
    return output


def _read_csv_path(path: Path, *, symbol: str | None) -> Any:
    import pandas as pd

    csv_path = _find_csv_path(path, symbol=symbol)
    data = pd.read_csv(csv_path)
    if symbol is not None:
        data = data[data["symbol"].astype(str) == symbol].copy() if "symbol" in data.columns else data.copy()
        if "symbol" not in data.columns:
            data["symbol"] = symbol
    return data


def _read_parquet(path: Path, *, symbol: str | None) -> Any:
    import pandas as pd

    data = pd.read_parquet(path)
    if symbol is not None and "symbol" in data.columns:
        data = data[data["symbol"].astype(str) == symbol].copy()
    return data


def _find_parquet_path(data_path: Path, *, symbol: str, parquet_dir: str | Path | None = None) -> Path | None:
    candidates: list[Path] = []
    if parquet_dir is not None:
        candidates.extend(_symbol_parquet_candidates(Path(parquet_dir), symbol=symbol))
    env_dir = os.getenv(PARQUET_DIR_ENV)
    if env_dir:
        candidates.extend(_symbol_parquet_candidates(Path(env_dir), symbol=symbol))
    if data_path.is_dir():
        candidates.extend(_symbol_parquet_candidates(data_path, symbol=symbol))
        candidates.extend(_symbol_parquet_candidates(default_parquet_dir_for_csv_dir(data_path), symbol=symbol))
        candidates.extend(_symbol_parquet_candidates(data_path / "parquet", symbol=symbol))
    elif data_path.suffix.lower() == ".parquet":
        candidates.append(data_path)
    else:
        candidates.append(data_path.with_suffix(".parquet"))
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _find_csv_path(data_path: Path, *, symbol: str | None) -> Path:
    if data_path.is_dir():
        if symbol is None:
            raise ValueError("symbol is required when loading bars from a CSV directory")
        for candidate in _symbol_csv_candidates(data_path, symbol=symbol):
            if candidate.exists():
                return candidate
        raise FileNotFoundError(f"no 5-minute CSV found for {symbol} in {data_path}")
    return data_path


def _symbol_csv_candidates(directory: Path, *, symbol: str) -> list[Path]:
    return [
        directory / f"{symbol}_5min.csv",
        directory / f"{symbol.replace('.', '_')}_5min.csv",
        directory / f"{symbol}.csv",
        directory / f"{symbol.replace('.', '_')}.csv",
    ]


def _symbol_parquet_candidates(directory: Path, *, symbol: str) -> list[Path]:
    return [
        directory / f"{symbol}_5min.parquet",
        directory / f"{symbol.replace('.', '_')}_5min.parquet",
        directory / f"{symbol}.parquet",
        directory / f"{symbol.replace('.', '_')}.parquet",
    ]


def _psql_execute(psql_bin: str, dsn: str, sql: str) -> None:
    completed = subprocess.run(
        [psql_bin, dsn, "-v", "ON_ERROR_STOP=1", "-c", sql],
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or f"exit code {completed.returncode}"
        raise RuntimeError(f"psql command failed: {detail}")


def _psql_copy(psql_bin: str, dsn: str, *, table: str, csv_payload: str) -> None:
    copy_sql = f"COPY {_sql_table_identifier(table)} ({', '.join(BAR_STORE_COLUMNS)}) FROM STDIN WITH (FORMAT csv, HEADER true)"
    completed = subprocess.run(
        [psql_bin, dsn, "-v", "ON_ERROR_STOP=1", "-c", copy_sql],
        input=csv_payload,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or f"exit code {completed.returncode}"
        raise RuntimeError(f"psql COPY failed: {detail}")


def _postgres_create_table_sql(table: str) -> str:
    schema, _ = _split_table_identifier(table)
    schema_sql = f"CREATE SCHEMA IF NOT EXISTS {_quote_identifier(schema)};" if schema else ""
    table_sql = _sql_table_identifier(table)
    index_name = _quote_identifier(f"idx_{table.replace('.', '_')}_symbol_timestamp")
    return f"""
        {schema_sql}
        CREATE TABLE IF NOT EXISTS {table_sql} (
            symbol text NOT NULL,
            timestamp timestamp without time zone NOT NULL,
            open double precision NOT NULL,
            high double precision NOT NULL,
            low double precision NOT NULL,
            close double precision NOT NULL,
            volume double precision NOT NULL,
            amount double precision,
            source_freq text,
            is_suspended boolean DEFAULT false,
            is_st boolean DEFAULT false,
            prev_close double precision,
            cash_dividend_per_share double precision DEFAULT 0,
            share_bonus_ratio double precision DEFAULT 0,
            PRIMARY KEY (symbol, timestamp)
        );
        CREATE INDEX IF NOT EXISTS {index_name} ON {table_sql} (symbol, timestamp);
    """


def _sql_table_identifier(table: str) -> str:
    schema, name = _split_table_identifier(table)
    if schema:
        return f"{_quote_identifier(schema)}.{_quote_identifier(name)}"
    return _quote_identifier(name)


def _split_table_identifier(table: str) -> tuple[str | None, str]:
    parts = table.split(".")
    if len(parts) == 1:
        return None, _validate_identifier(parts[0])
    if len(parts) == 2:
        return _validate_identifier(parts[0]), _validate_identifier(parts[1])
    raise ValueError("PostgreSQL table must be formatted as table or schema.table")


def _quote_identifier(value: str) -> str:
    return f'"{_validate_identifier(value)}"'


def _validate_identifier(value: str) -> str:
    if not _IDENTIFIER_RE.match(value):
        raise ValueError(f"invalid SQL identifier: {value!r}")
    return value


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"
