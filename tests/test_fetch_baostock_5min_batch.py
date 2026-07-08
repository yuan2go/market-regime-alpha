from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "fetch_baostock_5min_batch.py"
SPEC = importlib.util.spec_from_file_location("fetch_baostock_5min_batch", SCRIPT_PATH)
assert SPEC is not None
fetch_baostock = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = fetch_baostock
SPEC.loader.exec_module(fetch_baostock)


class FakeBaoStockResult:
    fields = ["date", "time", "code", "open", "high", "low", "close", "volume", "amount"]
    error_code = "0"
    error_msg = ""

    def __init__(self, rows: list[list[str]]) -> None:
        self._rows = rows
        self._index = 0
        self._current: list[str] | None = None

    def next(self) -> bool:
        if self._index >= len(self._rows):
            return False
        self._current = self._rows[self._index]
        self._index += 1
        return True

    def get_row_data(self) -> list[str]:
        assert self._current is not None
        return self._current


class FakeBaoStock:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def query_history_k_data_plus(self, _code: str, _fields: str, *, start_date: str, end_date: str, **_kwargs: object) -> FakeBaoStockResult:
        self.calls.append((start_date, end_date))
        return FakeBaoStockResult(
            [
                [
                    "2026-06-26",
                    "20260626150000000",
                    "sh.601939",
                    "10.00",
                    "10.20",
                    "9.90",
                    "10.10",
                    "1000",
                    "10100",
                ]
            ]
        )


def _normalized_rows(timestamps: list[str], closes: list[float]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "symbol": ["601939.SH"] * len(timestamps),
            "timestamp": timestamps,
            "open": closes,
            "high": closes,
            "low": closes,
            "close": closes,
            "volume": [1000.0] * len(timestamps),
            "amount": [10_000.0] * len(timestamps),
            "source_freq": ["5min"] * len(timestamps),
        }
    )


class FetchBaoStockBatchTests(unittest.TestCase):
    def test_incremental_fetch_start_uses_next_day_after_completed_close(self) -> None:
        self.assertEqual(
            fetch_baostock._incremental_fetch_start_date(pd.Timestamp("2026-06-25 15:00:00"), "2026-06-26"),
            "2026-06-26",
        )
        self.assertEqual(
            fetch_baostock._incremental_fetch_start_date(pd.Timestamp("2026-06-25 14:55:00"), "2026-06-26"),
            "2026-06-25",
        )
        self.assertEqual(
            fetch_baostock._incremental_fetch_start_date(pd.Timestamp("2026-06-26 15:00:00"), "2026-06-26"),
            "2026-06-26",
        )

    def test_merge_incremental_bars_deduplicates_timestamp_and_keeps_new_row(self) -> None:
        existing = _normalized_rows(["2026-06-25 14:55:00", "2026-06-25 15:00:00"], [10.0, 10.1])
        incoming = _normalized_rows(["2026-06-25 15:00:00", "2026-06-26 09:35:00"], [10.5, 10.6])

        merged = fetch_baostock._merge_incremental_bars(existing, incoming)

        self.assertEqual(list(merged["timestamp"]), ["2026-06-25 14:55:00", "2026-06-25 15:00:00", "2026-06-26 09:35:00"])
        self.assertEqual(float(merged.loc[merged["timestamp"] == "2026-06-25 15:00:00", "close"].iloc[0]), 10.5)

    def test_checkpoint_skip_requires_success_and_current_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "601939.SH_5min.csv"
            _normalized_rows(["2026-06-26 15:00:00"], [10.1]).to_csv(output, index=False)

            self.assertTrue(fetch_baostock._checkpoint_can_skip({"status": "success"}, output, target_end_date="2026-06-26"))
            self.assertFalse(fetch_baostock._checkpoint_can_skip({"status": "failed"}, output, target_end_date="2026-06-26"))
            self.assertFalse(fetch_baostock._checkpoint_can_skip({"status": "success"}, output, target_end_date="2026-06-27"))

    def test_fetch_symbol_incremental_only_queries_missing_dates_and_appends(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "601939.SH_5min.csv"
            _normalized_rows(["2026-06-25 15:00:00"], [10.1]).to_csv(output, index=False)
            fake_bs = FakeBaoStock()

            outcome = fetch_baostock._fetch_symbol(
                fake_bs,
                "601939.SH",
                output=output,
                start_date="2024-06-21",
                end_date="2026-06-26",
                min_existing_end_date=None,
                mode="incremental",
                force=False,
                min_rows=1,
                chunk_days=120,
                request_timeout=0,
            )

            data = pd.read_csv(output)
            self.assertEqual(fake_bs.calls, [("2026-06-26", "2026-06-26")])
            self.assertEqual(outcome.mode, "incremental")
            self.assertEqual(outcome.fetch_start, "2026-06-26")
            self.assertEqual(list(data["timestamp"]), ["2026-06-25 15:00:00", "2026-06-26 15:00:00"])


if __name__ == "__main__":
    unittest.main()
