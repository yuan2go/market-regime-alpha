"""Local research storage using Parquet files and DuckDB queries."""

from __future__ import annotations

import csv
from dataclasses import asdict
from pathlib import Path
from typing import Any, Iterable

from market_regime_alpha.dividend_t.models import WatchlistItem


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_RESEARCH_DIR = PROJECT_ROOT / "data" / "processed" / "dividend_t"
DEFAULT_WATCHLIST_PATH = PROJECT_ROOT / "data" / "external" / "watchlists" / "dividend_t_watchlist.csv"


class ResearchStore:
    def __init__(self, root: str | Path = DEFAULT_RESEARCH_DIR) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.database_path = self.root / "research.duckdb"

    def write_parquet(self, name: str, records: Iterable[dict[str, Any]]) -> Path:
        import pandas as pd

        path = self.root / f"{name}.parquet"
        path.parent.mkdir(parents=True, exist_ok=True)
        frame = pd.DataFrame(list(records))
        frame.to_parquet(path, index=False)
        return path

    def write_dataclasses(self, name: str, items: Iterable[Any]) -> Path:
        return self.write_parquet(name, (asdict(item) for item in items))

    def query(self, sql: str) -> list[dict[str, Any]]:
        import duckdb

        with duckdb.connect(str(self.database_path)) as connection:
            return connection.execute(sql).fetchdf().to_dict(orient="records")


def load_watchlist(path: str | Path = DEFAULT_WATCHLIST_PATH) -> list[WatchlistItem]:
    watchlist_path = Path(path)
    if not watchlist_path.exists():
        return []

    items: list[WatchlistItem] = []
    with watchlist_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            items.append(
                WatchlistItem(
                    symbol=row["symbol"],
                    name=row.get("name", ""),
                    industry=row.get("industry", ""),
                    is_cycle_stock=row.get("is_cycle_stock", "true").strip().lower() in {"1", "true", "yes", "y"},
                    notes=row.get("notes", ""),
                )
            )
    return items
