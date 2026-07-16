from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from market_regime_alpha.data_sources.a_share_bars import LatestQuote
from market_regime_alpha.research.tencent_composite_acquisition import (
    TencentCompositeAcquirer,
)
from market_regime_alpha.research.tencent_composite_contracts import CompositeSourceKind


TZ = ZoneInfo("Asia/Shanghai")
RETRIEVED_AT = datetime(2026, 7, 16, 16, 0, tzinfo=TZ)


def _frame(symbol: str, close: float, timestamp: str) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "symbol": [symbol],
            "timestamp": [timestamp],
            "open": [close],
            "high": [close],
            "low": [close],
            "close": [close],
            "volume": [100.0],
            "amount": [close * 100.0],
            "source_freq": ["5min"],
        }
    )


class FakeProvider:
    def __init__(self, frame: pd.DataFrame, *, failures: int = 0) -> None:
        self.frame = frame
        self.failures = failures
        self.calls = 0

    def minute_bars(self, *_args: object, **_kwargs: object) -> pd.DataFrame:
        self.calls += 1
        if self.calls <= self.failures:
            raise RuntimeError("temporary source failure")
        return self.frame.copy()


def _quote_fetcher(symbols: tuple[str, ...]) -> dict[str, LatestQuote]:
    return {
        symbol: LatestQuote(symbol=symbol, current_price=10.3)
        for symbol in symbols
    }


def test_acquirer_records_attempts_hashes_and_all_three_source_partitions() -> None:
    symbol = "000001.SZ"
    tencent = FakeProvider(_frame(symbol, 10.3, "2026-07-16 14:50:00"))
    baostock = FakeProvider(_frame(symbol, 10.0, "2026-07-14 14:50:00"), failures=1)
    acquirer = TencentCompositeAcquirer(
        tencent=tencent,
        baostock=baostock,
        local_reader=lambda _symbol: _frame(symbol, 10.1, "2026-07-15 14:50:00"),
        quote_fetcher=_quote_fetcher,
        retry_count=2,
    )

    result = acquirer.acquire(
        symbols=(symbol,),
        start_date="2026-01-01",
        end_date="2026-07-16",
        retrieved_at=RETRIEVED_AT,
    )

    assert {partition.source for partition in result.partitions} == {
        CompositeSourceKind.TENCENT,
        CompositeSourceKind.LOCAL,
        CompositeSourceKind.BAOSTOCK,
    }
    assert all(partition.content_hash.startswith("sha256:") for partition in result.partitions)
    assert result.quote_partition.product == "latest-quote"
    assert result.quote_partition.content_hash.startswith("sha256:")
    assert len(result.bars) == 3
    assert [(attempt.provider, attempt.success) for attempt in result.attempts] == [
        ("local", True),
        ("baostock", False),
        ("baostock", True),
        ("tencent", True),
        ("tencent-quote", True),
    ]
    assert result.quotes[symbol].source == "tencent_qt_quote"


def test_failed_source_retains_attempts_and_an_empty_partition() -> None:
    symbol = "000001.SZ"
    acquirer = TencentCompositeAcquirer(
        tencent=FakeProvider(_frame(symbol, 10.3, "2026-07-16 14:50:00")),
        baostock=FakeProvider(_frame(symbol, 10.0, "2026-07-14 14:50:00"), failures=3),
        local_reader=lambda _symbol: _frame(symbol, 10.1, "2026-07-15 14:50:00"),
        quote_fetcher=_quote_fetcher,
        retry_count=2,
    )

    result = acquirer.acquire(
        symbols=(symbol,),
        start_date="2026-01-01",
        end_date="2026-07-16",
        retrieved_at=RETRIEVED_AT,
    )

    partition = next(
        item for item in result.partitions if item.source is CompositeSourceKind.BAOSTOCK
    )
    assert partition.normalized_row_count == 0
    assert [attempt.success for attempt in result.attempts if attempt.provider == "baostock"] == [
        False,
        False,
    ]
    assert not any(bar.source is CompositeSourceKind.BAOSTOCK for bar in result.bars)


def test_partition_hash_uses_canonical_normalized_row_order() -> None:
    symbol = "000001.SZ"
    first = _frame(symbol, 10.0, "2026-07-15 09:35:00")
    second = _frame(symbol, 10.1, "2026-07-15 09:40:00")

    def acquire(local: pd.DataFrame):
        return TencentCompositeAcquirer(
            tencent=FakeProvider(_frame(symbol, 10.3, "2026-07-16 14:50:00")),
            baostock=FakeProvider(_frame(symbol, 9.9, "2026-07-14 14:50:00")),
            local_reader=lambda _symbol: local,
            quote_fetcher=_quote_fetcher,
        ).acquire(
            symbols=(symbol,),
            start_date="2026-01-01",
            end_date="2026-07-16",
            retrieved_at=RETRIEVED_AT,
        )

    forward = acquire(pd.concat([first, second], ignore_index=True))
    reverse = acquire(pd.concat([second, first], ignore_index=True))
    forward_hash = next(
        item.content_hash
        for item in forward.partitions
        if item.source is CompositeSourceKind.LOCAL
    )
    reverse_hash = next(
        item.content_hash
        for item in reverse.partitions
        if item.source is CompositeSourceKind.LOCAL
    )
    assert forward_hash == reverse_hash
