from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from market_regime_alpha.research.tencent_composite_contracts import CompositeBar, CompositeSourceKind
from market_regime_alpha.research.tencent_composite_merge import (
    merge_composite_bars,
    normalize_composite_frame,
)


TZ = ZoneInfo("Asia/Shanghai")


def _bar(timestamp: str, close: float, source: CompositeSourceKind) -> CompositeBar:
    parsed = datetime.strptime(timestamp, "%Y-%m-%d %H:%M").replace(tzinfo=TZ)
    return CompositeBar(
        symbol="000001.SZ",
        timestamp=parsed,
        open=close,
        high=close,
        low=close,
        close=close,
        volume=100.0,
        amount=close * 100.0,
        source=source,
    )


def _row(timestamp: str, close: float) -> dict[str, object]:
    return {
        "symbol": "000001.SZ",
        "timestamp": timestamp,
        "open": close,
        "high": close,
        "low": close,
        "close": close,
        "volume": 100.0,
        "amount": close * 100.0,
    }


def test_merge_uses_tencent_for_current_session_local_for_history_and_baostock_for_gaps() -> None:
    result = merge_composite_bars(
        tencent=(_bar("2026-07-16 09:35", 10.3, CompositeSourceKind.TENCENT),),
        local=(
            _bar("2026-07-15 09:35", 10.1, CompositeSourceKind.LOCAL),
            _bar("2026-07-16 09:35", 99.0, CompositeSourceKind.LOCAL),
        ),
        baostock=(
            _bar("2026-07-14 09:35", 9.9, CompositeSourceKind.BAOSTOCK),
            _bar("2026-07-15 09:35", 88.0, CompositeSourceKind.BAOSTOCK),
        ),
        current_session=date(2026, 7, 16),
    )

    assert [(bar.timestamp.date(), bar.source) for bar in result.bars] == [
        (date(2026, 7, 14), CompositeSourceKind.BAOSTOCK),
        (date(2026, 7, 15), CompositeSourceKind.LOCAL),
        (date(2026, 7, 16), CompositeSourceKind.TENCENT),
    ]
    assert [bar.close for bar in result.bars] == [9.9, 10.1, 10.3]
    assert len(result.conflicts) == 2
    assert {conflict.selected.source for conflict in result.conflicts} == {
        CompositeSourceKind.LOCAL,
        CompositeSourceKind.TENCENT,
    }


def test_tencent_rows_outside_current_session_are_ignored() -> None:
    result = merge_composite_bars(
        tencent=(_bar("2026-07-15 09:35", 77.0, CompositeSourceKind.TENCENT),),
        local=(_bar("2026-07-15 09:35", 10.1, CompositeSourceKind.LOCAL),),
        baostock=(),
        current_session=date(2026, 7, 16),
    )

    assert len(result.bars) == 1
    assert result.bars[0].source is CompositeSourceKind.LOCAL
    assert result.conflicts == ()


def test_identical_lower_priority_row_does_not_create_conflict() -> None:
    result = merge_composite_bars(
        tencent=(),
        local=(_bar("2026-07-15 09:35", 10.1, CompositeSourceKind.LOCAL),),
        baostock=(_bar("2026-07-15 09:35", 10.1, CompositeSourceKind.BAOSTOCK),),
        current_session=date(2026, 7, 16),
    )

    assert result.bars[0].source is CompositeSourceKind.LOCAL
    assert result.conflicts == ()


def test_normalize_rejects_duplicate_keys_and_missing_columns() -> None:
    duplicate = pd.DataFrame([_row("2026-07-15 09:35", 10.0), _row("2026-07-15 09:35", 10.0)])
    with pytest.raises(ValueError, match="duplicate"):
        normalize_composite_frame(duplicate, source=CompositeSourceKind.LOCAL)

    with pytest.raises(ValueError, match="missing columns"):
        normalize_composite_frame(pd.DataFrame({"symbol": ["000001.SZ"]}), source=CompositeSourceKind.LOCAL)


def test_normalize_localizes_naive_shanghai_timestamps_and_sorts() -> None:
    frame = pd.DataFrame(
        [
            _row("2026-07-15 09:40", 10.1),
            _row("2026-07-15 09:35", 10.0),
        ]
    )

    bars = normalize_composite_frame(frame, source=CompositeSourceKind.LOCAL)

    assert [bar.timestamp.strftime("%H:%M") for bar in bars] == ["09:35", "09:40"]
    assert all(bar.timestamp.tzinfo is not None for bar in bars)
    assert all(bar.source is CompositeSourceKind.LOCAL for bar in bars)
