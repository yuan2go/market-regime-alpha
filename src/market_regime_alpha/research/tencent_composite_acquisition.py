"""Bounded acquisition of identified Tencent composite source partitions."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from functools import partial
from hashlib import sha256
import json
from typing import Any, Callable, Iterable, Mapping

from market_regime_alpha.core.identity import ProviderId
from market_regime_alpha.core.time import RetrievedAt
from market_regime_alpha.research.tencent_composite_contracts import (
    CompositeAcquisitionResult,
    CompositeBar,
    CompositeSourceAttempt,
    CompositeSourceKind,
    CompositeSourcePartition,
    CompositeMergeResult,
)
from market_regime_alpha.research.tencent_composite_merge import (
    merge_composite_bars,
    normalize_composite_frame,
)


FrameFetcher = Callable[[], Any]


class TencentCompositeAcquirer:
    """Acquire exact local, BaoStock, Tencent-minute, and Tencent-quote inputs."""

    def __init__(
        self,
        *,
        tencent: Any,
        baostock: Any,
        local_reader: Callable[[str], Any],
        quote_fetcher: Callable[[Iterable[str]], Mapping[str, Any]],
        retry_count: int = 2,
    ) -> None:
        if retry_count <= 0:
            raise ValueError("retry_count must be positive")
        self.tencent = tencent
        self.baostock = baostock
        self.local_reader = local_reader
        self.quote_fetcher = quote_fetcher
        self.retry_count = retry_count

    def acquire(
        self,
        *,
        symbols: tuple[str, ...],
        start_date: str,
        end_date: str,
        retrieved_at: datetime,
    ) -> CompositeAcquisitionResult:
        """Acquire every declared partition without inventing rows after failure."""

        if not symbols or len(symbols) != len(set(symbols)):
            raise ValueError("symbols must be non-empty and unique")
        retrieval = RetrievedAt(retrieved_at)
        partitions: list[CompositeSourcePartition] = []
        attempts: list[CompositeSourceAttempt] = []
        bars: list[CompositeBar] = []

        for symbol in symbols:
            local_bars, local_raw_count, local_attempts = self._retry_frame(
                provider="local",
                symbol=symbol,
                source=CompositeSourceKind.LOCAL,
                fetch=partial(self.local_reader, symbol),
            )
            attempts.extend(local_attempts)
            bars.extend(local_bars)
            partitions.append(
                _partition(
                    symbol=symbol,
                    source=CompositeSourceKind.LOCAL,
                    bars=local_bars,
                    raw_row_count=local_raw_count,
                    retrieved_at=retrieval,
                    locator=f"local://{symbol}",
                    failed=not any(attempt.success for attempt in local_attempts),
                )
            )

            baostock_bars, baostock_raw_count, baostock_attempts = self._retry_frame(
                provider="baostock",
                symbol=symbol,
                source=CompositeSourceKind.BAOSTOCK,
                fetch=partial(
                    self.baostock.minute_bars,
                    symbol,
                    freq="5min",
                    start_date=start_date,
                    end_date=end_date,
                ),
            )
            attempts.extend(baostock_attempts)
            bars.extend(baostock_bars)
            partitions.append(
                _partition(
                    symbol=symbol,
                    source=CompositeSourceKind.BAOSTOCK,
                    bars=baostock_bars,
                    raw_row_count=baostock_raw_count,
                    retrieved_at=retrieval,
                    locator=f"baostock://{symbol}",
                    failed=not any(attempt.success for attempt in baostock_attempts),
                )
            )

            tencent_bars, tencent_raw_count, tencent_attempts = self._retry_frame(
                provider="tencent",
                symbol=symbol,
                source=CompositeSourceKind.TENCENT,
                fetch=partial(self.tencent.minute_bars, symbol, freq="5min"),
            )
            attempts.extend(tencent_attempts)
            bars.extend(tencent_bars)
            partitions.append(
                _partition(
                    symbol=symbol,
                    source=CompositeSourceKind.TENCENT,
                    bars=tencent_bars,
                    raw_row_count=tencent_raw_count,
                    retrieved_at=retrieval,
                    locator=f"tencent://minute/{symbol}",
                    failed=not any(attempt.success for attempt in tencent_attempts),
                )
            )

        quotes, quote_attempts = self._retry_quotes(symbols)
        attempts.extend(quote_attempts)
        quote_partition = _quote_partition(
            quotes=quotes,
            symbols=symbols,
            retrieved_at=retrieval,
            failed=not any(attempt.success for attempt in quote_attempts),
        )
        ordered_bars = tuple(
            sorted(bars, key=lambda bar: (bar.timestamp, bar.symbol, bar.source.value))
        )
        return CompositeAcquisitionResult(
            partitions=tuple(partitions),
            quote_partition=quote_partition,
            attempts=tuple(attempts),
            bars=ordered_bars,
            quotes=quotes,
            retrieved_at=retrieval,
        )

    def _retry_frame(
        self,
        *,
        provider: str,
        symbol: str,
        source: CompositeSourceKind,
        fetch: FrameFetcher,
    ) -> tuple[tuple[CompositeBar, ...], int, tuple[CompositeSourceAttempt, ...]]:
        attempts: list[CompositeSourceAttempt] = []
        for attempt_number in range(1, self.retry_count + 1):
            try:
                frame = fetch()
                raw_row_count = len(frame)
                normalized = normalize_composite_frame(frame, source=source)
            except Exception as exc:  # noqa: BLE001 - retained as source-attempt evidence.
                attempts.append(
                    CompositeSourceAttempt(
                        provider=provider,
                        symbol=symbol,
                        attempt_number=attempt_number,
                        success=False,
                        message=str(exc),
                    )
                )
                continue
            attempts.append(
                CompositeSourceAttempt(
                    provider=provider,
                    symbol=symbol,
                    attempt_number=attempt_number,
                    success=True,
                    message=f"normalized {len(normalized)} rows",
                )
            )
            return normalized, raw_row_count, tuple(attempts)
        return (), 0, tuple(attempts)

    def _retry_quotes(
        self,
        symbols: tuple[str, ...],
    ) -> tuple[dict[str, Any], tuple[CompositeSourceAttempt, ...]]:
        attempts: list[CompositeSourceAttempt] = []
        attempt_symbol = ",".join(symbols)
        for attempt_number in range(1, self.retry_count + 1):
            try:
                quotes = dict(self.quote_fetcher(symbols))
            except Exception as exc:  # noqa: BLE001 - retained as source-attempt evidence.
                attempts.append(
                    CompositeSourceAttempt(
                        provider="tencent-quote",
                        symbol=attempt_symbol,
                        attempt_number=attempt_number,
                        success=False,
                        message=str(exc),
                    )
                )
                continue
            attempts.append(
                CompositeSourceAttempt(
                    provider="tencent-quote",
                    symbol=attempt_symbol,
                    attempt_number=attempt_number,
                    success=True,
                    message=f"received {len(quotes)} quotes",
                )
            )
            return quotes, tuple(attempts)
        return {}, tuple(attempts)


def merge_acquisition(
    acquisition: CompositeAcquisitionResult,
    *,
    current_session: date | None = None,
):
    """Merge acquired rows under the declared source precedence."""

    session = current_session or acquisition.retrieved_at.value.date()
    by_source = {
        source: tuple(bar for bar in acquisition.bars if bar.source is source)
        for source in CompositeSourceKind
    }
    return merge_composite_bars(
        tencent=by_source[CompositeSourceKind.TENCENT],
        local=by_source[CompositeSourceKind.LOCAL],
        baostock=by_source[CompositeSourceKind.BAOSTOCK],
        current_session=session,
    )


def frames_for_accepted_symbols(
    merged: CompositeMergeResult,
    accepted_symbols: tuple[str, ...],
) -> dict[str, Any]:
    """Build read-only dividend-T frames from already-selected composite rows."""

    import pandas as pd

    frames: dict[str, Any] = {}
    for symbol in accepted_symbols:
        symbol_bars = tuple(bar for bar in merged.bars if bar.symbol == symbol)
        if not symbol_bars:
            raise ValueError(f"accepted symbol has no merged bars: {symbol}")
        frame = pd.DataFrame(
            [
                {
                    "symbol": bar.symbol,
                    "timestamp": bar.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                    "open": bar.open,
                    "high": bar.high,
                    "low": bar.low,
                    "close": bar.close,
                    "volume": bar.volume,
                    "amount": bar.amount,
                    "source_freq": "5min",
                }
                for bar in symbol_bars
            ]
        )
        frame.attrs["data_source"] = "tencent_current+local_history+baostock_gap_fill"
        frames[symbol] = frame
    return frames


def _partition(
    *,
    symbol: str,
    source: CompositeSourceKind,
    bars: tuple[CompositeBar, ...],
    raw_row_count: int,
    retrieved_at: RetrievedAt,
    locator: str,
    failed: bool,
) -> CompositeSourcePartition:
    provider_id, product = {
        CompositeSourceKind.LOCAL: (ProviderId("provider-local-cache"), "dividend-t-5min-cache"),
        CompositeSourceKind.BAOSTOCK: (
            ProviderId("provider-baostock"),
            "historical-5min-backfill",
        ),
        CompositeSourceKind.TENCENT: (
            ProviderId("provider-tencent-public"),
            "minute-query-1min-to-5min",
        ),
    }[source]
    return CompositeSourcePartition(
        source=source,
        provider_id=provider_id,
        product=product,
        retrieved_at=retrieved_at,
        locator=locator,
        content_hash=_bars_hash(bars),
        requested_symbols=(symbol,),
        raw_row_count=raw_row_count,
        normalized_row_count=len(bars),
        limitations=(f"{source.value}_FETCH_FAILED",) if failed else (),
    )


def _quote_partition(
    *,
    quotes: Mapping[str, Any],
    symbols: tuple[str, ...],
    retrieved_at: RetrievedAt,
    failed: bool,
) -> CompositeSourcePartition:
    return CompositeSourcePartition(
        source=CompositeSourceKind.TENCENT,
        provider_id=ProviderId("provider-tencent-public"),
        product="latest-quote",
        retrieved_at=retrieved_at,
        locator="tencent://latest-quote",
        content_hash=_canonical_hash(
            [
                {"symbol": symbol, "quote": _json_value(quotes[symbol])}
                for symbol in sorted(quotes)
            ]
        ),
        requested_symbols=symbols,
        raw_row_count=len(quotes),
        normalized_row_count=len(quotes),
        limitations=("TENCENT_QUOTE_FETCH_FAILED",) if failed else (),
    )


def _bars_hash(bars: tuple[CompositeBar, ...]) -> str:
    records = [
        {
            "amount": bar.amount,
            "close": bar.close,
            "high": bar.high,
            "low": bar.low,
            "open": bar.open,
            "source": bar.source.value,
            "symbol": bar.symbol,
            "timestamp": bar.timestamp.isoformat(),
            "volume": bar.volume,
        }
        for bar in sorted(bars, key=lambda item: (item.timestamp, item.symbol))
    ]
    return _canonical_hash(records)


def _canonical_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return f"sha256:{sha256(payload.encode('utf-8')).hexdigest()}"


def _json_value(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return {key: _json_value(item) for key, item in asdict(value).items()}
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    return value
