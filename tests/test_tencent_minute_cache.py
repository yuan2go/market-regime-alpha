from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sys
import tempfile
import unittest
from zoneinfo import ZoneInfo


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from market_regime_alpha.data_sources.tencent_minute_cache import (  # noqa: E402
    TENCENT_1M_TABLE,
    is_a_share_market_session,
    normalize_tencent_1min_payload,
    write_tencent_1min_cache,
)


class TencentMinuteCacheTests(unittest.TestCase):
    def test_normalize_tencent_1min_payload_outputs_incremental_volume(self) -> None:
        payload = {
            "code": 0,
            "data": {
                "sh601919": {
                    "data": {
                        "date": "20260608",
                        "data": [
                            "0930 14.90 100 149000.00",
                            "0931 14.91 160 238460.00",
                        ],
                    }
                }
            },
        }

        frame = normalize_tencent_1min_payload(payload, symbol="601919.SH")

        self.assertEqual(list(frame["timestamp"]), ["2026-06-08 09:30:00", "2026-06-08 09:31:00"])
        self.assertEqual(float(frame.iloc[0]["volume"]), 10_000.0)
        self.assertEqual(float(frame.iloc[1]["volume"]), 6_000.0)
        self.assertEqual(float(frame.iloc[1]["amount"]), 89_460.0)

    def test_write_tencent_1min_cache_upserts_by_symbol_and_timestamp(self) -> None:
        payload = {
            "code": 0,
            "data": {
                "sh601919": {
                    "data": {
                        "date": "20260608",
                        "data": [
                            "0930 14.90 100 149000.00",
                            "0931 14.91 160 238460.00",
                        ],
                    }
                }
            },
        }
        frame = normalize_tencent_1min_payload(payload, symbol="601919.SH")
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "research.duckdb"
            first = write_tencent_1min_cache(frame, database_path=db_path)
            second = write_tencent_1min_cache(frame, database_path=db_path)

            import duckdb

            with duckdb.connect(str(db_path)) as connection:
                count = connection.execute(f"SELECT COUNT(*) FROM {TENCENT_1M_TABLE}").fetchone()[0]

        self.assertEqual(first.fetched_rows, 2)
        self.assertEqual(first.inserted_rows, 2)
        self.assertEqual(second.inserted_rows, 0)
        self.assertEqual(int(count), 2)

    def test_a_share_session_only_in_trading_windows(self) -> None:
        tz = ZoneInfo("Asia/Shanghai")

        self.assertTrue(is_a_share_market_session(datetime(2026, 6, 8, 9, 31, tzinfo=tz)))
        self.assertFalse(is_a_share_market_session(datetime(2026, 6, 8, 12, 0, tzinfo=tz)))
        self.assertFalse(is_a_share_market_session(datetime(2026, 6, 13, 10, 0, tzinfo=tz)))


if __name__ == "__main__":
    unittest.main()
