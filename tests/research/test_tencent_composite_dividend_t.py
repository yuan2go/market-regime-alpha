from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from market_regime_alpha.data_sources.a_share_bars import LatestQuote
from market_regime_alpha.research.tencent_composite_dividend_t import (
    CompositeFrameProvider,
    refresh_dividend_t_from_composite,
)


TZ = ZoneInfo("Asia/Shanghai")


def _frame(symbol: str = "000001.SZ") -> pd.DataFrame:
    base = pd.Timestamp("2026-07-16 09:35:00")
    rows = []
    for index in range(80):
        close = 10.0 + index * 0.01
        rows.append(
            {
                "symbol": symbol,
                "timestamp": (base + pd.Timedelta(minutes=5 * index)).strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
                "open": close - 0.01,
                "high": close + 0.02,
                "low": close - 0.02,
                "close": close,
                "volume": 1_000.0 + index,
                "amount": (1_000.0 + index) * close,
                "source_freq": "5min",
            }
        )
    return pd.DataFrame(rows)


def _watchlist(root: Path) -> Path:
    path = root / "watchlist.csv"
    path.write_text(
        "symbol,name,industry,is_cycle_stock,notes\n"
        "000001.SZ,平安银行,银行,false,测试\n",
        encoding="utf-8",
    )
    return path


def test_composite_frame_provider_exposes_only_accepted_symbols() -> None:
    provider = CompositeFrameProvider(
        frames={"000001.SZ": _frame(), "000002.SZ": _frame("000002.SZ")}
    )

    assert len(provider.minute_bars("000001.SZ")) > 0
    with pytest.raises(KeyError, match="not accepted"):
        provider.minute_bars("000003.SZ")


def test_refresh_keeps_candidate_rank_separate_from_dividend_action(tmp_path: Path) -> None:
    result = refresh_dividend_t_from_composite(
        watchlist_path=_watchlist(tmp_path),
        frames={"000001.SZ": _frame()},
        quotes={"000001.SZ": LatestQuote("000001.SZ", 10.5)},
        before_snapshot={"schema_version": 2, "rows": []},
        generated_at=datetime(2026, 7, 16, 16, 0, tzinfo=TZ),
    )

    row = result.snapshot["rows"][0]
    assert "candidate_rank" not in row
    assert "signal" in row
    assert result.diff["symbols"]["000001.SZ"]["after_status"] == "ok"
