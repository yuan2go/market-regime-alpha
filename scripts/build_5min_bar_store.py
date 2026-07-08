#!/usr/bin/env python3
"""Build fast 5-minute bar stores from per-symbol CSV files."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from market_regime_alpha.dividend_t.bar_store import (  # noqa: E402
    DEFAULT_POSTGRES_TABLE,
    build_parquet_bar_store,
    default_parquet_dir_for_csv_dir,
    import_csv_dir_to_postgres,
)


DEFAULT_TOP1000_CSV_DIR = PROJECT_ROOT / "data" / "raw" / "top1000_largecap_5min_1y"


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert local 5-minute CSV bars into Parquet and optionally PostgreSQL.")
    parser.add_argument("--csv-dir", type=Path, default=DEFAULT_TOP1000_CSV_DIR)
    parser.add_argument("--parquet-dir", type=Path, default=None, help="Defaults to sibling <csv-dir>_parquet.")
    parser.add_argument("--symbols", default=None, help="Comma-separated symbol allowlist, e.g. 601919.SH,600900.SH.")
    parser.add_argument("--overwrite", action="store_true", help="Rewrite existing Parquet files.")
    parser.add_argument("--compression", default="zstd", help="Parquet compression codec. Use snappy if zstd is unavailable.")
    parser.add_argument("--skip-parquet", action="store_true", help="Only import to PostgreSQL.")
    parser.add_argument("--postgres-dsn", default=None, help="Optional PostgreSQL connection string accepted by psql.")
    parser.add_argument("--postgres-table", default=DEFAULT_POSTGRES_TABLE)
    parser.add_argument("--postgres-append", action="store_true", help="Append instead of deleting existing rows for each imported symbol.")
    parser.add_argument("--psql-bin", default="psql", help="psql executable path.")
    args = parser.parse_args()

    symbols = _parse_symbols(args.symbols)
    parquet_result = None
    if not args.skip_parquet:
        parquet_result = build_parquet_bar_store(
            args.csv_dir,
            parquet_dir=args.parquet_dir,
            symbols=symbols,
            overwrite=args.overwrite,
            compression=args.compression,
        )
        print(
            "Parquet store built: "
            f"files={parquet_result.file_count}, rows={parquet_result.row_count}, "
            f"dir={parquet_result.parquet_dir}, manifest={parquet_result.manifest_path}",
            flush=True,
        )
    if args.postgres_dsn:
        postgres_result = import_csv_dir_to_postgres(
            args.csv_dir,
            dsn=args.postgres_dsn,
            table=args.postgres_table,
            symbols=symbols,
            replace_symbols=not args.postgres_append,
            psql_bin=args.psql_bin,
        )
        print(
            "PostgreSQL store imported: "
            f"files={postgres_result.file_count}, rows={postgres_result.row_count}, table={postgres_result.postgres_table}",
            flush=True,
        )
    if args.skip_parquet and not args.postgres_dsn:
        raise SystemExit("--skip-parquet requires --postgres-dsn")
    if parquet_result is None and not args.postgres_dsn:
        target = args.parquet_dir or default_parquet_dir_for_csv_dir(args.csv_dir)
        print(f"No store built. Remove --skip-parquet or provide --postgres-dsn. Default parquet target would be {target}.")
    return 0


def _parse_symbols(value: str | None) -> list[str] | None:
    if value is None or not value.strip():
        return None
    return [item.strip().upper() for item in value.split(",") if item.strip()]


if __name__ == "__main__":
    raise SystemExit(main())
