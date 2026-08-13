"""Raw-preserving BaoStock acquisition for bounded Phase E archives."""

from __future__ import annotations

from contextlib import redirect_stdout
from datetime import UTC, date, datetime, timedelta
from io import StringIO
import json
import os
from pathlib import Path
import signal
import socket
import tempfile
from typing import Any, Callable, Mapping

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
from market_regime_alpha.evidence.canonical import (
    canonical_hash,
    canonical_json,
    normalize_canonical_datetime,
)
from market_regime_alpha.market_data.contracts import Timeframe


BAOSTOCK_HISTORICAL_PROVIDER_ID = "BAOSTOCK_QUERY_HISTORY_K_DATA_PLUS"
_BAOSTOCK_TRANSPORT_ERROR_CODES = frozenset({"10002007", "CLIENT_EXCEPTION"})
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
        timeout_seconds: float = 30.0,
        maximum_source_requests: int = 10_000,
        maximum_source_rows: int = 2_500_000,
    ) -> None:
        if (
            timeout_seconds <= 0
            or maximum_source_requests <= 0
            or maximum_source_rows <= 0
        ):
            raise ValueError("BaoStock archive limits must be positive")
        self._clock = clock
        self._baostock_module = baostock_module
        self._timeout_seconds = timeout_seconds
        self._maximum_source_requests = maximum_source_requests
        self._maximum_source_rows = maximum_source_rows

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
        timeframe_ranges: Mapping[Timeframe, tuple[date, date]] | None = None,
        bucket_count: int = 16,
        checkpoint_root: Path | None = None,
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
        ranges = {
            timeframe: (start_date, end_date) for timeframe in ordered_timeframes
        }
        if timeframe_ranges is not None:
            if set(timeframe_ranges) != set(ordered_timeframes):
                raise ValueError(
                    "Historical timeframe ranges must exactly cover timeframes"
                )
            ranges = dict(timeframe_ranges)
        for timeframe, (range_start, range_end) in ranges.items():
            if range_start > range_end:
                raise ValueError(
                    f"Historical {timeframe.value} acquisition range is reversed"
                )
            if range_start < start_date or range_end > end_date:
                raise ValueError(
                    "Historical timeframe range exceeds owner acquisition range"
                )
        request_ranges = {
            timeframe: _request_ranges(timeframe, *bounds)
            for timeframe, bounds in ranges.items()
        }
        request_count = sum(
            len(items) for items in request_ranges.values()
        ) * len(ordered_symbols)
        if request_count > self._maximum_source_requests:
            raise ValueError("Historical acquisition exceeds declared request ceiling")
        bs = self._module()
        user_id, password = baostock_credentials()
        previous_timeout = socket.getdefaulttimeout()
        socket.setdefaulttimeout(self._timeout_seconds)
        try:
            with redirect_stdout(StringIO()):
                login = self._timed_login(
                    bs,
                    user_id=user_id,
                    password=password,
                )
            if str(getattr(login, "error_code", "0")) != "0":
                raise AShareDataError(
                    f"BaoStock login failed: {getattr(login, 'error_msg', 'unknown')}"
                )
            requests: list[HistoricalRawRequest] = []
            source_row_count = 0
            try:
                for symbol in ordered_symbols:
                    for timeframe in ordered_timeframes:
                        for request_start, request_end in request_ranges[timeframe]:
                            request = self._checkpointed_acquire_one(
                                checkpoint_root=checkpoint_root,
                                bs=bs,
                                symbol=symbol,
                                timeframe=timeframe,
                                start_date=request_start,
                                end_date=request_end,
                            )
                            if request.provider_error_code in _BAOSTOCK_TRANSPORT_ERROR_CODES:
                                raise AShareDataError(
                                    "BaoStock transport failed; partial corpus is not publishable"
                                )
                            source_row_count += len(request.rows)
                            if source_row_count > self._maximum_source_rows:
                                raise AShareDataError(
                                    "BaoStock acquisition exceeds declared row ceiling"
                                )
                            requests.append(request)
            finally:
                with redirect_stdout(StringIO()):
                    self._timed_logout(bs)
        finally:
            socket.setdefaulttimeout(previous_timeout)
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

    def _checkpointed_acquire_one(
        self,
        *,
        checkpoint_root: Path | None,
        **values: Any,
    ) -> HistoricalRawRequest:
        identity = {
            "provider_id": BAOSTOCK_HISTORICAL_PROVIDER_ID,
            "symbol": str(values["symbol"]),
            "timeframe": values["timeframe"].value,
            "start_date": values["start_date"].isoformat(),
            "end_date": values["end_date"].isoformat(),
            "fields": ",".join(
                _DAILY_FIELDS
                if values["timeframe"] is Timeframe.DAILY
                else _MINUTE_FIELDS
            ),
            "frequency": (
                "d" if values["timeframe"] is Timeframe.DAILY else "5"
            ),
            "adjustflag": "3",
        }
        if checkpoint_root is None:
            return self._timed_acquire_one(**values)
        checkpoint_root.mkdir(parents=True, exist_ok=True)
        checkpoint = checkpoint_root / f"{canonical_hash(identity)[7:]}.json"
        if checkpoint.exists():
            return _load_request_checkpoint(checkpoint, identity)
        response = self._timed_acquire_one(**values)
        if response.provider_error_code in _BAOSTOCK_TRANSPORT_ERROR_CODES:
            return response
        envelope = {
            "schema_version": "baostock-historical-request-checkpoint/v1",
            "request_identity": identity,
            "response": response.to_canonical_dict(),
        }
        payload = {**envelope, "checkpoint_hash": canonical_hash(envelope)}
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{checkpoint.stem}.",
            suffix=".tmp",
            dir=checkpoint_root,
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(canonical_json(payload))
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.link(temporary_name, checkpoint)
            except FileExistsError:
                # The immutable checkpoint is Authority.  A concurrent valid
                # Provider call normally has different request/retrieval times,
                # so equality with this loser's response is neither expected nor
                # relevant.  Loading validates the winner's identity and hashes.
                return _load_request_checkpoint(checkpoint, identity)
            _fsync_directory(checkpoint_root)
        finally:
            Path(temporary_name).unlink(missing_ok=True)
        return _load_request_checkpoint(checkpoint, identity)

    def _timed_login(self, bs: Any, **credentials: str) -> Any:
        if not hasattr(signal, "setitimer"):
            return bs.login(**credentials)
        previous_handler = signal.getsignal(signal.SIGALRM)

        def timeout_handler(_signum: int, _frame: object) -> None:
            raise _BaoStockRequestTimeout

        signal.signal(signal.SIGALRM, timeout_handler)
        signal.setitimer(signal.ITIMER_REAL, self._timeout_seconds)
        try:
            return bs.login(**credentials)
        except _BaoStockRequestTimeout as exc:
            raise AShareDataError("BaoStock login timed out") from exc
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, previous_handler)

    def _timed_logout(self, bs: Any) -> None:
        if not hasattr(signal, "setitimer"):
            bs.logout()
            return
        previous_handler = signal.getsignal(signal.SIGALRM)

        def timeout_handler(_signum: int, _frame: object) -> None:
            raise _BaoStockRequestTimeout

        signal.signal(signal.SIGALRM, timeout_handler)
        signal.setitimer(signal.ITIMER_REAL, self._timeout_seconds)
        try:
            bs.logout()
        except _BaoStockRequestTimeout:
            return
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, previous_handler)

    def _timed_acquire_one(
        self,
        **values: Any,
    ) -> HistoricalRawRequest:
        if not hasattr(signal, "setitimer"):
            return self._acquire_one(**values)
        previous_handler = signal.getsignal(signal.SIGALRM)

        def timeout_handler(_signum: int, _frame: object) -> None:
            raise _BaoStockRequestTimeout

        signal.signal(signal.SIGALRM, timeout_handler)
        signal.setitimer(signal.ITIMER_REAL, self._timeout_seconds)
        try:
            return self._acquire_one(**values)
        except _BaoStockRequestTimeout:
            return HistoricalRawRequest.create(
                provider_id=BAOSTOCK_HISTORICAL_PROVIDER_ID,
                product="query_history_k_data_plus:transport-timeout",
                symbol=str(values["symbol"]),
                timeframe=values["timeframe"],
                start_date=values["start_date"],
                end_date=values["end_date"],
                request_parameters=(
                    ("timeout_seconds", str(self._timeout_seconds)),
                ),
                requested_at=normalize_canonical_datetime(self._clock()),
                retrieved_at=normalize_canonical_datetime(self._clock()),
                fields=(),
                rows=(),
                provider_error_code="CLIENT_EXCEPTION",
                provider_error_message="BaoStock request wall-clock timeout",
                limitations=BAOSTOCK_RAW_LIMITATIONS,
            )
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, previous_handler)

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
                page = getattr(result, "data", None)
                per_page = int(getattr(result, "per_page_count", 0))
                consumed = int(
                    getattr(
                        result,
                        "cur_row_num",
                        len(page) if page is not None else 0,
                    )
                )
                if (
                    page is not None
                    and per_page > 0
                    and len(page) >= per_page
                    and consumed >= len(page)
                ):
                    raise AShareDataError(
                        "BaoStock pagination ended without a terminal partial page"
                    )
                if str(getattr(result, "error_code", "0")) != "0":
                    raise AShareDataError(
                        "BaoStock pagination returned a provider error"
                    )
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


class _BaoStockRequestTimeout(BaseException):
    """Escape Provider code that catches ordinary socket exceptions."""


def _request_ranges(
    timeframe: Timeframe,
    start_date: date,
    end_date: date,
) -> tuple[tuple[date, date], ...]:
    values: list[tuple[date, date]] = []
    cursor = start_date
    while cursor <= end_date:
        if timeframe is Timeframe.DAILY:
            boundary = date(cursor.year, 12, 31)
        else:
            boundary = (
                date(cursor.year + 1, 1, 1)
                if cursor.month == 12
                else date(cursor.year, cursor.month + 1, 1)
            ) - timedelta(days=1)
        current_end = min(boundary, end_date)
        values.append((cursor, current_end))
        cursor = current_end + timedelta(days=1)
    return tuple(values)


def _load_request_checkpoint(
    path: Path,
    identity: Mapping[str, str],
) -> HistoricalRawRequest:
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise AShareDataError("BaoStock request checkpoint is corrupt") from exc
    if not isinstance(payload, Mapping):
        raise AShareDataError("BaoStock request checkpoint is invalid")
    envelope = {
        "schema_version": payload.get("schema_version"),
        "request_identity": payload.get("request_identity"),
        "response": payload.get("response"),
    }
    if (
        envelope["schema_version"]
        != "baostock-historical-request-checkpoint/v1"
        or envelope["request_identity"] != dict(identity)
        or payload.get("checkpoint_hash") != canonical_hash(envelope)
        or not isinstance(envelope["response"], Mapping)
    ):
        raise AShareDataError("BaoStock request checkpoint identity drift")
    response = HistoricalRawRequest.from_canonical_dict(envelope["response"])
    if (
        response.provider_id != identity["provider_id"]
        or response.symbol != identity["symbol"]
        or response.timeframe.value != identity["timeframe"]
        or response.start_date.isoformat() != identity["start_date"]
        or response.end_date.isoformat() != identity["end_date"]
    ):
        raise AShareDataError("BaoStock request checkpoint response drift")
    return response


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
