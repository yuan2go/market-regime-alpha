from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from market_regime_alpha.data_sources.a_share_bars import (
    AShareDataError,
    LOCAL_CACHE_TENCENT_SOURCE,
    MERGED_EASTMONEY_BAOSTOCK_SOURCE,
    MERGED_TENCENT_BAOSTOCK_SOURCE,
    LocalCacheTencentProvider,
    QmtL1Provider,
    baostock_credentials,
    fetch_a_share_5min_with_fallback,
    merge_history_with_intraday,
    normalize_akshare_minute_frame,
    normalize_baostock_minute_frame,
    normalize_eastmoney_minute_rows,
    normalize_qmt_market_data_ex,
    normalize_qmt_tick_snapshot,
    normalize_tencent_minute_payload,
    parse_tencent_quote_text,
    provider_options,
    read_local_5min_cache,
    to_baostock_code,
    to_eastmoney_secid,
    to_plain_code,
    to_tencent_code,
)


class FailingProvider:
    name = "failing"
    data_source = "failing_source"
    is_realtime = False

    def minute_bars(self, *args, **kwargs):  # noqa: ANN002, ANN003
        raise AShareDataError("network blocked")


class WorkingProvider:
    name = "working"
    data_source = "working_source"
    is_realtime = False

    def minute_bars(self, *args, **kwargs):  # noqa: ANN002, ANN003
        base = pd.Timestamp("2026-06-01 09:35:00")
        return pd.DataFrame(
            {
                "symbol": ["601919.SH"] * 32,
                "timestamp": [base + pd.Timedelta(minutes=5 * index) for index in range(32)],
                "open": [14.0] * 32,
                "high": [14.1] * 32,
                "low": [13.9] * 32,
                "close": [14.0 + index * 0.001 for index in range(32)],
                "volume": [1_000_000.0] * 32,
                "amount": [14_000_000.0] * 32,
                "source_freq": ["5min"] * 32,
            }
        )


class IntradayProvider:
    def minute_bars(self, *args, **kwargs):  # noqa: ANN002, ANN003
        return pd.DataFrame(
            {
                "symbol": ["601919.SH", "601919.SH"],
                "timestamp": ["2026-06-08 09:30:00", "2026-06-08 09:35:00"],
                "open": [14.9, 14.95],
                "high": [14.96, 15.0],
                "low": [14.9, 14.95],
                "close": [14.95, 14.97],
                "volume": [1_000_000.0, 1_200_000.0],
                "amount": [14_950_000.0, 17_964_000.0],
                "source_freq": ["5min", "5min"],
            }
        )


class AShareBarsTests(unittest.TestCase):
    def test_symbol_conversions(self) -> None:
        self.assertEqual(to_plain_code("601919.SH"), "601919")
        self.assertEqual(to_plain_code("sh601919"), "601919")
        self.assertEqual(to_baostock_code("601919.SH"), "sh.601919")
        self.assertEqual(to_eastmoney_secid("601919.SH"), "1.601919")
        self.assertEqual(to_eastmoney_secid("000001.SZ"), "0.000001")
        self.assertEqual(to_tencent_code("601919.SH"), "sh601919")
        self.assertEqual(to_tencent_code("000001.SZ"), "sz000001")

    def test_baostock_credentials_use_env_or_anonymous_default(self) -> None:
        self.assertEqual(baostock_credentials(env={}), ("anonymous", "123456"))
        self.assertEqual(
            baostock_credentials(env={"BAOSTOCK_USER_ID": "demo", "BAOSTOCK_PASSWORD": "secret"}),
            ("demo", "secret"),
        )

    def test_normalize_akshare_minute_frame(self) -> None:
        raw = pd.DataFrame(
            {
                "时间": ["2026-06-01 09:35:00", "2026-06-01 09:40:00"],
                "开盘": [14.0, 14.1],
                "最高": [14.2, 14.2],
                "最低": [13.9, 14.0],
                "收盘": [14.1, 14.15],
                "成交量": [1000, 1100],
                "成交额": [1_410_000, 1_556_500],
            }
        )

        data = normalize_akshare_minute_frame(raw, symbol="601919.SH")

        self.assertEqual(list(data.columns), ["symbol", "timestamp", "open", "high", "low", "close", "volume", "amount", "source_freq"])
        self.assertEqual(data.iloc[0]["symbol"], "601919.SH")
        self.assertEqual(data.iloc[0]["timestamp"], "2026-06-01 09:35:00")
        self.assertEqual(float(data.iloc[1]["close"]), 14.15)

    def test_normalize_baostock_minute_frame(self) -> None:
        raw = pd.DataFrame(
            {
                "date": ["2026-06-01"],
                "time": ["20260601150000000"],
                "code": ["sh.601919"],
                "open": ["14.8700"],
                "high": ["14.8700"],
                "low": ["14.8600"],
                "close": ["14.8600"],
                "volume": ["3468180"],
                "amount": ["51547053.0000"],
            }
        )

        data = normalize_baostock_minute_frame(raw, symbol="601919.SH")

        self.assertEqual(data.iloc[0]["timestamp"], "2026-06-01 15:00:00")
        self.assertEqual(float(data.iloc[0]["amount"]), 51547053.0)

    def test_normalize_eastmoney_minute_rows(self) -> None:
        rows = [
            "2026-06-02 09:35,14.94,14.89,14.95,14.83,13022,141000000,0.80,0.20,0.03,0.08",
            "2026-06-02 09:40,14.89,14.95,14.95,14.87,14620,266000000,0.60,0.61,0.09,0.14",
        ]

        data = normalize_eastmoney_minute_rows(rows, symbol="601919.SH")

        self.assertEqual(data.iloc[0]["timestamp"], "2026-06-02 09:35:00")
        self.assertEqual(float(data.iloc[1]["close"]), 14.95)
        self.assertEqual(float(data.iloc[0]["amount"]), 141000000.0)

    def test_normalize_tencent_minute_payload_to_5min_bars(self) -> None:
        rows = [
            "0930 14.94 100 149400.00",
            "0931 14.93 130 194190.00",
            "0932 14.88 180 268590.00",
            "0933 14.85 210 313140.00",
            "0934 14.86 260 387440.00",
            "0935 14.92 310 462040.00",
            "1300 14.91 310 462040.00",
            "1301 14.84 350 521400.00",
        ]
        payload = {"code": 0, "data": {"sh601919": {"data": {"date": "20260602", "data": rows}}}}

        data = normalize_tencent_minute_payload(payload, symbol="601919.SH")

        self.assertEqual(list(data["timestamp"]), ["2026-06-02 09:30:00", "2026-06-02 09:35:00", "2026-06-02 13:00:00"])
        self.assertEqual(float(data.iloc[0]["open"]), 14.94)
        self.assertEqual(float(data.iloc[0]["low"]), 14.85)
        self.assertEqual(float(data.iloc[0]["close"]), 14.86)
        self.assertEqual(float(data.iloc[0]["volume"]), 26000.0)
        self.assertEqual(float(data.iloc[-1]["close"]), 14.84)

    def test_parse_tencent_quote_text(self) -> None:
        raw = (
            'v_sh601919="1~中远海控~601919~14.91~14.86~14.94~989225~528140~461085~14.90~2221~'
            '14.89~582~14.88~1189~14.87~783~14.86~591~14.91~6727~14.92~1604~14.93~4367~'
            '14.94~6746~14.95~11373~~20260602153528~0.05~0.34~14.98~14.78";\n'
        )

        quotes = parse_tencent_quote_text(raw)

        self.assertIn("601919.SH", quotes)
        quote = quotes["601919.SH"]
        self.assertEqual(quote.current_price, 14.91)
        self.assertEqual(quote.previous_close, 14.86)
        self.assertEqual(quote.open_price, 14.94)
        self.assertEqual(quote.high_price, 14.98)
        self.assertEqual(quote.low_price, 14.78)
        self.assertEqual(quote.change_pct, 0.34)
        self.assertEqual(quote.quote_time, "20260602153528")

    def test_normalize_qmt_market_data_ex(self) -> None:
        raw = {
            "601919.SH": pd.DataFrame(
                {
                    "time": [20260601093500, 20260601094000],
                    "open": [14.50, 14.55],
                    "high": [14.60, 14.61],
                    "low": [14.48, 14.53],
                    "close": [14.56, 14.58],
                    "vol": [1000000, 1200000],
                    "amount": [14560000, 17496000],
                }
            )
        }

        data = normalize_qmt_market_data_ex(raw, symbol="601919.SH")

        self.assertEqual(data.iloc[0]["timestamp"], "2026-06-01 09:35:00")
        self.assertEqual(float(data.iloc[1]["volume"]), 1200000.0)
        self.assertEqual(data.attrs.get("data_source"), None)

    def test_normalize_qmt_tick_snapshot_extracts_five_level_book(self) -> None:
        snapshot = normalize_qmt_tick_snapshot(
            {
                "lastPrice": 14.58,
                "preClose": 14.40,
                "open": 14.50,
                "high": 14.61,
                "low": 14.48,
                "volume": 2_000_000,
                "amount": 29_000_000,
                "time": 20260601094000,
                "bidPrice": [14.57, 14.56, 14.55, 14.54, 14.53],
                "askPrice": [14.58, 14.59, 14.60, 14.61, 14.62],
                "bidVol": [1000, 900, 800, 700, 600],
                "askVol": [500, 400, 300, 200, 100],
            },
            symbol="601919.SH",
        )

        self.assertEqual(snapshot.current_price, 14.58)
        self.assertEqual(snapshot.timestamp, "2026-06-01 09:40:00")
        self.assertGreater(snapshot.book.imbalance, 0)
        self.assertEqual(len(snapshot.book.bid_prices), 5)

    def test_qmt_l1_provider_uses_injected_xtdata(self) -> None:
        provider = QmtL1Provider(xtdata=_FakeXtData(), auto_download=False)

        bars = provider.minute_bars("601919.SH")
        ticks = provider.tick_snapshots(["601919.SH"])

        self.assertEqual(provider.is_realtime, True)
        self.assertEqual(len(bars), 2)
        self.assertIn("601919.SH", ticks)
        self.assertGreater(ticks["601919.SH"].book.bid_amount, ticks["601919.SH"].book.ask_amount)

    def test_merge_history_with_intraday_keeps_today_from_intraday_only(self) -> None:
        history = pd.DataFrame(
            {
                "symbol": ["601919.SH", "601919.SH"],
                "timestamp": ["2026-06-01 15:00:00", "2026-06-02 09:35:00"],
                "open": [14.8, 14.0],
                "high": [14.9, 14.1],
                "low": [14.7, 13.9],
                "close": [14.86, 14.0],
                "volume": [1000.0, 1000.0],
                "amount": [14860.0, 14000.0],
                "source_freq": ["5min", "5min"],
            }
        )
        intraday = pd.DataFrame(
            {
                "symbol": ["601919.SH"],
                "timestamp": ["2026-06-02 09:35:00"],
                "open": [14.94],
                "high": [14.95],
                "low": [14.83],
                "close": [14.89],
                "volume": [13022.0],
                "amount": [141000000.0],
                "source_freq": ["5min"],
            }
        )

        merged = merge_history_with_intraday(history, intraday, session_date=pd.Timestamp("2026-06-02").date())

        self.assertEqual(list(merged["timestamp"]), ["2026-06-01 15:00:00", "2026-06-02 09:35:00"])
        self.assertEqual(float(merged.iloc[-1]["close"]), 14.89)
        self.assertEqual(merged.attrs["data_source"], MERGED_EASTMONEY_BAOSTOCK_SOURCE)

    def test_merge_history_with_intraday_allows_custom_data_source(self) -> None:
        history = pd.DataFrame(
            {
                "symbol": ["601919.SH"],
                "timestamp": ["2026-06-01 15:00:00"],
                "open": [14.8],
                "high": [14.9],
                "low": [14.7],
                "close": [14.86],
                "volume": [1000.0],
                "amount": [14860.0],
                "source_freq": ["5min"],
            }
        )
        intraday = history.copy()
        intraday["timestamp"] = ["2026-06-02 09:30:00"]

        merged = merge_history_with_intraday(
            history,
            intraday,
            session_date=pd.Timestamp("2026-06-02").date(),
            data_source=MERGED_TENCENT_BAOSTOCK_SOURCE,
        )

        self.assertEqual(merged.attrs["data_source"], MERGED_TENCENT_BAOSTOCK_SOURCE)

    def test_provider_options_put_fast_intraday_first(self) -> None:
        options = provider_options()

        self.assertEqual(options[0]["value"], "fast")
        self.assertEqual(options[1]["value"], "auto")
        self.assertEqual(options[2]["value"], "qmt")
        self.assertEqual(options[3]["value"], "strict")

    def test_local_cache_tencent_provider_merges_cache_and_intraday(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            cache_path = Path(directory) / "601919.SH_5min.csv"
            pd.DataFrame(
                {
                    "symbol": ["601919.SH", "601919.SH", "601919.SH"],
                    "timestamp": ["2026-06-01 09:35:00", "2026-06-07 14:55:00", "2026-06-08 09:30:00"],
                    "open": [14.4, 14.7, 99.0],
                    "high": [14.5, 14.8, 99.0],
                    "low": [14.3, 14.6, 99.0],
                    "close": [14.45, 14.75, 99.0],
                    "volume": [1_000_000.0, 1_000_000.0, 1_000_000.0],
                    "amount": [14_450_000.0, 14_750_000.0, 99_000_000.0],
                    "source_freq": ["5min", "5min", "5min"],
                }
            ).to_csv(cache_path, index=False)
            provider = LocalCacheTencentProvider(cache_dir=directory, tencent=IntradayProvider())

            merged = provider.minute_bars(
                "601919.SH",
                start_date="2026-06-01 09:00:00",
                end_date="2026-06-08 10:00:00",
            )

        self.assertEqual(merged.attrs["data_source"], LOCAL_CACHE_TENCENT_SOURCE)
        self.assertEqual(list(merged["timestamp"]), ["2026-06-01 09:35:00", "2026-06-07 14:55:00", "2026-06-08 09:30:00", "2026-06-08 09:35:00"])
        self.assertEqual(float(merged.iloc[-2]["close"]), 14.95)

    def test_read_local_5min_cache_preserves_normalized_rows_without_tencent_merge(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "601919.SH_5min.csv"
            pd.DataFrame(
                {
                    "symbol": ["601919.SH"],
                    "timestamp": ["2026-07-15 09:35:00"],
                    "open": [14.5],
                    "high": [14.6],
                    "low": [14.4],
                    "close": [14.55],
                    "volume": [1_000_000.0],
                    "amount": [14_550_000.0],
                    "source_freq": ["5min"],
                }
            ).to_csv(path, index=False)

            frame = read_local_5min_cache("601919.SH", cache_dir=directory)

        self.assertEqual(list(frame["timestamp"]), ["2026-07-15 09:35:00"])
        self.assertEqual(frame.attrs["data_source"], "local_csv_5min")

    def test_fallback_uses_second_provider_after_first_failure(self) -> None:
        result = fetch_a_share_5min_with_fallback(
            "601919.SH",
            start_date="2026-06-01 09:30:00",
            end_date="2026-06-01 15:00:00",
            providers=[FailingProvider(), WorkingProvider()],
        )

        self.assertEqual(result.provider, "working")
        self.assertEqual(result.source, "working_source")
        self.assertEqual(len(result.attempts), 2)
        self.assertFalse(result.attempts[0].success)
        self.assertTrue(result.attempts[1].success)
        self.assertIsNotNone(result.attempts[0].elapsed_seconds)
        self.assertIsNotNone(result.attempts[1].elapsed_seconds)

class _FakeXtData:
    def get_market_data_ex(self, *_args, **_kwargs):
        return {
            "601919.SH": pd.DataFrame(
                {
                    "time": [20260601093500, 20260601094000],
                    "open": [14.50, 14.55],
                    "high": [14.60, 14.61],
                    "low": [14.48, 14.53],
                    "close": [14.56, 14.58],
                    "vol": [1000000, 1200000],
                    "amount": [14560000, 17496000],
                }
            )
        }

    def get_full_tick(self, _symbols):
        return {
            "601919.SH": {
                "lastPrice": 14.58,
                "preClose": 14.40,
                "time": 20260601094000,
                "bidPrice": [14.57, 14.56, 14.55, 14.54, 14.53],
                "askPrice": [14.58, 14.59, 14.60, 14.61, 14.62],
                "bidVol": [1000, 900, 800, 700, 600],
                "askVol": [500, 400, 300, 200, 100],
            }
        }


if __name__ == "__main__":
    unittest.main()
