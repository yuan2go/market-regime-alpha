from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from market_regime_alpha.dividend_t.backtest import load_5min_bars_path  # noqa: E402
from market_regime_alpha.dividend_t.bar_store import (  # noqa: E402
    build_parquet_bar_store,
    default_parquet_dir_for_csv_dir,
    load_raw_5min_bars_path,
    symbol_from_bar_file,
)


class BarStoreTests(unittest.TestCase):
    def test_build_parquet_store_and_loader_reads_sibling_cache(self) -> None:
        with _temporary_bar_dir() as csv_dir:
            result = build_parquet_bar_store(csv_dir, overwrite=True)

            parquet_dir = default_parquet_dir_for_csv_dir(csv_dir)
            csv_path = csv_dir / "601919.SH_5min.csv"
            csv_path.unlink()
            bars = load_5min_bars_path(csv_dir, symbol="601919.SH")
            manifest_exists = result.manifest_path is not None and result.manifest_path.exists()

        self.assertEqual(result.file_count, 1)
        self.assertEqual(result.row_count, 4)
        self.assertEqual(parquet_dir, result.parquet_dir)
        self.assertTrue(manifest_exists)
        self.assertEqual(len(bars), 4)
        self.assertEqual(str(bars.loc[0, "symbol"]), "601919.SH")
        self.assertAlmostEqual(float(bars.loc[3, "close"]), 10.35)
        self.assertIn("amount", bars.columns)

    def test_load_raw_backend_parquet_requires_existing_store(self) -> None:
        with _temporary_bar_dir() as csv_dir:
            with self.assertRaises(FileNotFoundError):
                load_raw_5min_bars_path(csv_dir, symbol="601919.SH", backend="parquet")

    def test_directory_csv_fallback_matches_existing_loader_contract(self) -> None:
        with _temporary_bar_dir() as csv_dir:
            bars = load_5min_bars_path(csv_dir, symbol="601919.SH")

        self.assertEqual(len(bars), 4)
        self.assertAlmostEqual(float(bars.loc[0, "open"]), 10.0)
        self.assertEqual(str(bars.loc[0, "source_freq"]), "5min")

    def test_symbol_from_bar_file_supports_csv_and_parquet_names(self) -> None:
        self.assertEqual(symbol_from_bar_file("601919.SH_5min.csv"), "601919.SH")
        self.assertEqual(symbol_from_bar_file("601919.SH_5min.parquet"), "601919.SH")


class _temporary_bar_dir:
    def __enter__(self) -> Path:
        import tempfile

        self._context = tempfile.TemporaryDirectory()
        parent_dir = Path(self._context.__enter__())
        csv_dir = parent_dir / "raw"
        csv_dir.mkdir()
        _sample_bars().to_csv(csv_dir / "601919.SH_5min.csv", index=False)
        return csv_dir

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self._context.__exit__(exc_type, exc, traceback)


def _sample_bars() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "symbol": "601919.SH",
                "timestamp": "2026-01-02 09:35:00",
                "open": 10.00,
                "high": 10.10,
                "low": 9.95,
                "close": 10.05,
                "volume": 1000,
                "amount": 10050,
            },
            {
                "symbol": "601919.SH",
                "timestamp": "2026-01-02 09:40:00",
                "open": 10.05,
                "high": 10.20,
                "low": 10.02,
                "close": 10.18,
                "volume": 1100,
                "amount": 11198,
            },
            {
                "symbol": "601919.SH",
                "timestamp": "2026-01-02 09:45:00",
                "open": 10.18,
                "high": 10.28,
                "low": 10.16,
                "close": 10.22,
                "volume": 1200,
                "amount": 12264,
            },
            {
                "symbol": "601919.SH",
                "timestamp": "2026-01-02 09:50:00",
                "open": 10.22,
                "high": 10.38,
                "low": 10.20,
                "close": 10.35,
                "volume": 1400,
                "amount": 14490,
            },
        ]
    )
