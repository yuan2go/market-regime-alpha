"""Raw-preserving BaoStock acquisition for bounded Phase E archives."""

from __future__ import annotations

from contextlib import redirect_stdout
from datetime import UTC, date, datetime
from io import StringIO
from typing import Any, Callable

from market_regime_alpha.application.historical_corpus.contracts import (
    HistoricalArtifactKind,
    HistoricalCorpusCoverage,
    HistoricalDataOwner,
    HistoricalRawRequest,
    build_partitions,
)
from market_regime_alpha.data_sources.a_share_bars import (
    AShareDataError,
    baostock_credentials,
    to_baostock_code,
)
from market_regime_alpha.evidence.canonical import normalize_canonical_datetime
from market_regime_alpha.market_data.contracts import Timeframe


BAOSTOCK_HISTORICAL_PROVIDER_ID = "BAOSTOCK_QUERY_HISTORY_K_DATA_PLUS"
BAOSTOCK_RAW_LIMITATIONS = (
    "BAOSTOCK_LIBRARY_RESULT_REENCODED_NOT_TRANSPORT_BYTES",
    "HISTORICAL_AVAILABLE_TIME_NOT_PROVIDED",
    "PUBLIC_DATA_EXPLORATORY_ONLY",
)
_DAILY_FIELDS = (
    "date",
    "code",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "amount",
    "adjustflag",
    "tradestatus",
    "isST",
)
_MINUTE_FIELDS = (
    "date",
    "time",
    "code",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "amount",
    "adjustflag",
)
Clock = Callable[[], datetime]


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


class BaoStockHistoricalArchiveClient:
    """Acquire exact annual provider requests under one immutable Raw owner."""

    def __init__(
        self,
        *,
        clock: Clock = _utc_now,
        baostock_module: Any | None = None,
    ) -> None:
        self._clock = clock
        self._baostock_module = baostock_module

    def acquire(
        self,
        *,
        symbols: tuple[str, ...],
        start_date: date,
        end_date: date,
        timeframes: tuple[Timeframe, ...] = (
            Timeframe.DAILY,
            Timeframe.MINUTE_5,
        ),
        bucket_count: int = 16,
    ) -> HistoricalDataOwner:
        ordered_symbols = tuple(sorted(set(symbols)))
        ordered_timeframes = tuple(sorted(set(timeframes), key=lambda item: item.value))
        if not ordered_symbols:
            raise ValueError("Historical acquisition requires symbols")
        if start_date > end_date:
            raise ValueError("Historical acquisition date range is reversed")
        if not ordered_timeframes or any(
            item not in {Timeframe.DAILY, Timeframe.MINUTE_5}
            for item in ordered_timeframes
        ):
            raise ValueError("BaoStock archive supports DAILY and MINUTE_5")
        if bucket_count <= 0:
            raise ValueError("Historical acquisition bucket_count must be positive")
        bs = self._module()
        user_id, password = baostock_credentials()
        with redirect_stdout(StringIO()):
            login = bs.login(user_id=user_id, password=password)
        if str(getattr(login, "error_code", "0")) != "0":
            raise AShareDataError(
                f"BaoStock login failed: {getattr(login, 'error_msg', 'unknown')}"
            )
        requests: list[HistoricalRawRequest] = []
        try:
            for symbol in ordered_symbols:
                for timeframe in ordered_timeframes:
                    for year in range(start_date.year, end_date.year + 1):
                        request_start = max(start_date, date(year, 1, 1))
                        request_end = min(end_date, date(year, 12, 31))
                        requests.append(
                            self._acquire_one(
                                bs=bs,
                                symbol=symbol,
                                timeframe=timeframe,
                                start_date=request_start,
                                end_date=request_end,
                            )
                        )
        finally:
            with redirect_stdout(StringIO()):
                bs.logout()
        partitions = build_partitions(
            artifact_kind=HistoricalArtifactKind.RAW_PROVIDER_ARCHIVE,
            records=tuple(requests),
            bucket_count=bucket_count,
        )
        failures: dict[str, int] = {}
        observed = set()
        source_rows = 0
        for request in requests:
            source_rows += len(request.rows)
            if request.rows:
                observed.add(request.symbol)
            if request.provider_error_code is not None:
                key = f"PROVIDER_ERROR::{request.provider_error_code}"
                failures[key] = failures.get(key, 0) + 1
            elif not request.rows:
                failures["EMPTY_PROVIDER_RESULT"] = (
                    failures.get("EMPTY_PROVIDER_RESULT", 0) + 1
                )
        retrieved_at = max(item.retrieved_at for item in requests)
        return HistoricalDataOwner.create(
            artifact_kind=HistoricalArtifactKind.RAW_PROVIDER_ARCHIVE,
            provider_id=BAOSTOCK_HISTORICAL_PROVIDER_ID,
            normalization_version=None,
            parent_reference=None,
            created_at=retrieved_at,
            retrieved_at=retrieved_at,
            first_market_date=min(item.first_market_date for item in partitions),
            last_market_date=max(item.last_market_date for item in partitions),
            bucket_count=bucket_count,
            partitions=partitions,
            coverage=HistoricalCorpusCoverage(
                expected_symbols=ordered_symbols,
                observed_symbols=tuple(sorted(observed)),
                expected_request_count=len(requests),
                successful_request_count=sum(item.succeeded for item in requests),
                source_row_count=source_rows,
                normalized_row_count=0,
                missing_field_counts=(),
                failure_counts=tuple(sorted(failures.items())),
            ),
            limitations=BAOSTOCK_RAW_LIMITATIONS,
        )

    def _acquire_one(
        self,
        *,
        bs: Any,
        symbol: str,
        timeframe: Timeframe,
        start_date: date,
        end_date: date,
    ) -> HistoricalRawRequest:
        requested_at = normalize_canonical_datetime(self._clock())
        fields = _DAILY_FIELDS if timeframe is Timeframe.DAILY else _MINUTE_FIELDS
        frequency = "d" if timeframe is Timeframe.DAILY else "5"
        error_code: str | None = None
        error_message: str | None = None
        response_fields: tuple[str, ...] = ()
        rows: tuple[tuple[str, ...], ...] = ()
        try:
            result = bs.query_history_k_data_plus(
                to_baostock_code(symbol),
                ",".join(fields),
                start_date=start_date.isoformat(),
                end_date=end_date.isoformat(),
                frequency=frequency,
                adjustflag="3",
            )
            if str(getattr(result, "error_code", "0")) != "0":
                error_code = str(result.error_code)
                error_message = str(getattr(result, "error_msg", "unknown"))
            else:
                response_fields = tuple(str(item) for item in result.fields)
                collected = []
                while result.next():
                    collected.append(tuple(str(item) for item in result.get_row_data()))
                rows = tuple(collected)
        except Exception as exc:  # noqa: BLE001 - failure becomes durable Raw evidence
            error_code = "CLIENT_EXCEPTION"
            error_message = f"{type(exc).__name__}: {exc}"
        retrieved_at = normalize_canonical_datetime(self._clock())
        return HistoricalRawRequest.create(
            provider_id=BAOSTOCK_HISTORICAL_PROVIDER_ID,
            product=f"query_history_k_data_plus:{frequency}:adjustflag=3",
            symbol=symbol,
            timeframe=timeframe,
            start_date=start_date,
            end_date=end_date,
            request_parameters=(
                ("adjustflag", "3"),
                ("end_date", end_date.isoformat()),
                ("fields", ",".join(fields)),
                ("frequency", frequency),
                ("start_date", start_date.isoformat()),
                ("symbol", to_baostock_code(symbol)),
            ),
            requested_at=requested_at,
            retrieved_at=retrieved_at,
            fields=response_fields,
            rows=rows,
            provider_error_code=error_code,
            provider_error_message=error_message,
            limitations=BAOSTOCK_RAW_LIMITATIONS,
        )

    def _module(self) -> Any:
        if self._baostock_module is not None:
            return self._baostock_module
        try:
            import baostock as bs
        except ImportError as exc:
            raise AShareDataError("baostock is not installed") from exc
        return bs


__all__ = [
    "BAOSTOCK_HISTORICAL_PROVIDER_ID",
    "BAOSTOCK_RAW_LIMITATIONS",
    "BaoStockHistoricalArchiveClient",
]
