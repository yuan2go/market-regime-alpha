"""Raw-preserving BaoStock acquisition for bounded Phase E archives."""

from __future__ import annotations

import base64
import binascii
from contextlib import redirect_stdout
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from io import StringIO
import json
import os
from pathlib import Path
import signal
import socket
import tempfile
from typing import Any, Callable, Iterator, Mapping
import zlib

from market_regime_alpha.application.historical_corpus.artifacts import (
    HistoricalPackageIndex,
)

from market_regime_alpha.application.historical_corpus.contracts import (
    HistoricalArtifactKind,
    HistoricalCorpusCoverage,
    HistoricalDataOwner,
    HistoricalDataPartition,
    HistoricalRawRequest,
    build_partitions,
    historical_symbol_bucket,
)
from market_regime_alpha.application.historical_corpus.staged_package import (
    HistoricalOwnerMetadata,
    StagedHistoricalPackageWriter,
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
_BAOSTOCK_AUTHENTICATION_ERROR_CODES = frozenset({"10001001"})
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


@dataclass(frozen=True, slots=True)
class HistoricalRequestCheckpointDescriptor:
    path: Path
    symbol: str
    timeframe: Timeframe
    start_date: date
    end_date: date
    source_row_count: int

    @property
    def identity(self) -> dict[str, str]:
        return _request_identity(
            symbol=self.symbol,
            timeframe=self.timeframe,
            start_date=self.start_date,
            end_date=self.end_date,
        )


@dataclass(frozen=True, slots=True)
class HistoricalArchivePrefetch:
    expected_request_count: int
    assigned_request_count: int
    worker_index: int
    worker_count: int

    def __post_init__(self) -> None:
        assigned = _assigned_request_indices(
            total=self.expected_request_count,
            worker_index=self.worker_index,
            worker_count=self.worker_count,
        )
        if self.assigned_request_count != len(assigned):
            raise ValueError("Historical prefetch assignment count drifted")


@dataclass(frozen=True, slots=True)
class _AcquisitionScope:
    ordered_symbols: tuple[str, ...]
    ordered_timeframes: tuple[Timeframe, ...]
    ranges: Mapping[Timeframe, tuple[date, date]]
    request_ranges: Mapping[Timeframe, tuple[tuple[date, date], ...]]
    checkpoint_directory: Path | None
    expected_request_count: int


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
        maximum_source_rows: int = 20_000_000,
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
        acquisition_id: str | None = None,
    ) -> HistoricalDataOwner:
        scope = _prepare_acquisition_scope(
            symbols=symbols,
            start_date=start_date,
            end_date=end_date,
            timeframes=timeframes,
            timeframe_ranges=timeframe_ranges,
            bucket_count=bucket_count,
            checkpoint_root=checkpoint_root,
            acquisition_id=acquisition_id,
            maximum_source_requests=self._maximum_source_requests,
        )
        ordered_symbols = scope.ordered_symbols
        requests = list(self._request_stream(scope))
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

    def acquire_to_package(
        self,
        *,
        symbols: tuple[str, ...],
        start_date: date,
        end_date: date,
        artifact_root: Path,
        checkpoint_root: Path,
        acquisition_id: str,
        timeframes: tuple[Timeframe, ...] = (
            Timeframe.DAILY,
            Timeframe.MINUTE_5,
        ),
        timeframe_ranges: Mapping[Timeframe, tuple[date, date]] | None = None,
        bucket_count: int = 16,
    ) -> HistoricalPackageIndex:
        """Acquire durable checkpoints, then publish one bounded Raw package."""

        scope = _prepare_acquisition_scope(
            symbols=symbols,
            start_date=start_date,
            end_date=end_date,
            timeframes=timeframes,
            timeframe_ranges=timeframe_ranges,
            bucket_count=bucket_count,
            checkpoint_root=checkpoint_root,
            acquisition_id=acquisition_id,
            maximum_source_requests=self._maximum_source_requests,
        )
        checkpoint_directory = scope.checkpoint_directory
        if checkpoint_directory is None:
            raise ValueError("package acquisition requires durable checkpoints")
        grouped: dict[
            tuple[Timeframe, int, int, int | None],
            list[HistoricalRequestCheckpointDescriptor],
        ] = {}
        observed: set[str] = set()
        failures: dict[str, int] = {}
        retrieved_at: datetime | None = None
        source_row_count = 0
        successful_request_count = 0
        for request in self._request_stream(scope):
            identity = _request_identity(
                symbol=request.symbol,
                timeframe=request.timeframe,
                start_date=request.start_date,
                end_date=request.end_date,
            )
            checkpoint = checkpoint_directory / f"{canonical_hash(identity)[7:]}.json"
            if not checkpoint.is_file():
                raise AShareDataError(
                    "Historical package acquisition checkpoint is missing"
                )
            month = (
                None
                if request.timeframe is Timeframe.DAILY
                else request.start_date.month
            )
            key = (
                request.timeframe,
                request.start_date.year,
                historical_symbol_bucket(request.symbol, bucket_count),
                month,
            )
            grouped.setdefault(key, []).append(
                HistoricalRequestCheckpointDescriptor(
                    path=checkpoint,
                    symbol=request.symbol,
                    timeframe=request.timeframe,
                    start_date=request.start_date,
                    end_date=request.end_date,
                    source_row_count=len(request.rows),
                )
            )
            source_row_count += len(request.rows)
            successful_request_count += int(request.succeeded)
            if request.rows:
                observed.add(request.symbol)
            else:
                failures["EMPTY_PROVIDER_RESULT"] = (
                    failures.get("EMPTY_PROVIDER_RESULT", 0) + 1
                )
            retrieved_at = (
                request.retrieved_at
                if retrieved_at is None
                else max(retrieved_at, request.retrieved_at)
            )
        if len(tuple(item for values in grouped.values() for item in values)) != (
            scope.expected_request_count
        ):
            raise AShareDataError("Historical package request catalog is incomplete")
        writer = StagedHistoricalPackageWriter(
            artifact_root=artifact_root,
            artifact_kind=HistoricalArtifactKind.RAW_PROVIDER_ARCHIVE,
            bucket_count=bucket_count,
        )
        for (timeframe, _year, bucket, _month), descriptors in sorted(
            grouped.items(),
            key=lambda item: (
                item[0][0].value,
                item[0][1],
                item[0][3] or 0,
                item[0][2],
            ),
        ):
            requests = tuple(
                _load_request_checkpoint(item.path, item.identity)
                for item in descriptors
            )
            writer.add_partition(
                HistoricalDataPartition.create(
                    artifact_kind=HistoricalArtifactKind.RAW_PROVIDER_ARCHIVE,
                    timeframe=timeframe,
                    symbol_bucket=bucket,
                    bucket_count=bucket_count,
                    records=requests,
                )
            )
        if retrieved_at is None:
            raise AShareDataError("Historical package acquisition produced no requests")
        return writer.finalize(
            HistoricalOwnerMetadata(
                provider_id=BAOSTOCK_HISTORICAL_PROVIDER_ID,
                normalization_version=None,
                parent_reference=None,
                created_at=retrieved_at,
                retrieved_at=retrieved_at,
                coverage=HistoricalCorpusCoverage(
                    expected_symbols=scope.ordered_symbols,
                    observed_symbols=tuple(sorted(observed)),
                    expected_request_count=scope.expected_request_count,
                    successful_request_count=successful_request_count,
                    source_row_count=source_row_count,
                    normalized_row_count=0,
                    missing_field_counts=(),
                    failure_counts=tuple(sorted(failures.items())),
                ),
                limitations=BAOSTOCK_RAW_LIMITATIONS,
            )
        )

    def prefetch_to_checkpoints(
        self,
        *,
        symbols: tuple[str, ...],
        start_date: date,
        end_date: date,
        checkpoint_root: Path,
        acquisition_id: str,
        worker_index: int,
        worker_count: int,
        timeframes: tuple[Timeframe, ...] = (
            Timeframe.DAILY,
            Timeframe.MINUTE_5,
        ),
        timeframe_ranges: Mapping[Timeframe, tuple[date, date]] | None = None,
        bucket_count: int = 16,
    ) -> HistoricalArchivePrefetch:
        """Fill one deterministic request shard; never publish a Raw owner."""

        scope = _prepare_acquisition_scope(
            symbols=symbols,
            start_date=start_date,
            end_date=end_date,
            timeframes=timeframes,
            timeframe_ranges=timeframe_ranges,
            bucket_count=bucket_count,
            checkpoint_root=checkpoint_root,
            acquisition_id=acquisition_id,
            maximum_source_requests=self._maximum_source_requests,
        )
        assigned = _assigned_request_indices(
            total=scope.expected_request_count,
            worker_index=worker_index,
            worker_count=worker_count,
        )
        tuple(self._request_stream(scope, assigned_indices=frozenset(assigned)))
        return HistoricalArchivePrefetch(
            expected_request_count=scope.expected_request_count,
            assigned_request_count=len(assigned),
            worker_index=worker_index,
            worker_count=worker_count,
        )

    def _request_stream(
        self,
        scope: _AcquisitionScope,
        *,
        assigned_indices: frozenset[int] | None = None,
    ) -> Iterator[HistoricalRawRequest]:
        bs = self._module()
        user_id, password = baostock_credentials()
        previous_timeout = socket.getdefaulttimeout()
        socket.setdefaulttimeout(self._timeout_seconds)
        logged_in = False
        source_row_count = 0
        request_index = 0
        try:
            try:
                for symbol in scope.ordered_symbols:
                    for timeframe in scope.ordered_timeframes:
                        for request_start, request_end in scope.request_ranges[
                            timeframe
                        ]:
                            active_index = request_index
                            request_index += 1
                            if (
                                assigned_indices is not None
                                and active_index not in assigned_indices
                            ):
                                continue
                            request = self._load_existing_checkpoint(
                                checkpoint_root=scope.checkpoint_directory,
                                symbol=symbol,
                                timeframe=timeframe,
                                start_date=request_start,
                                end_date=request_end,
                            )
                            if request is None:
                                if not logged_in:
                                    with redirect_stdout(StringIO()):
                                        login = self._timed_login(
                                            bs,
                                            user_id=user_id,
                                            password=password,
                                        )
                                    if str(getattr(login, "error_code", "0")) != "0":
                                        raise AShareDataError(
                                            "BaoStock login failed: "
                                            f"{getattr(login, 'error_msg', 'unknown')}"
                                        )
                                    logged_in = True
                                request = self._checkpointed_acquire_one(
                                    checkpoint_root=scope.checkpoint_directory,
                                    bs=bs,
                                    symbol=symbol,
                                    timeframe=timeframe,
                                    start_date=request_start,
                                    end_date=request_end,
                                )
                            if request.provider_error_code in (
                                _BAOSTOCK_AUTHENTICATION_ERROR_CODES
                            ):
                                with redirect_stdout(StringIO()):
                                    if logged_in:
                                        self._timed_logout(bs)
                                    relogin = self._timed_login(
                                        bs,
                                        user_id=user_id,
                                        password=password,
                                    )
                                if str(getattr(relogin, "error_code", "0")) != "0":
                                    raise AShareDataError(
                                        "BaoStock reauthentication failed during acquisition"
                                    )
                                logged_in = True
                                request = self._checkpointed_acquire_one(
                                    checkpoint_root=scope.checkpoint_directory,
                                    bs=bs,
                                    symbol=symbol,
                                    timeframe=timeframe,
                                    start_date=request_start,
                                    end_date=request_end,
                                )
                            if request.provider_error_code in (
                                _BAOSTOCK_AUTHENTICATION_ERROR_CODES
                            ):
                                raise AShareDataError(
                                    "BaoStock authentication expired after bounded retry; "
                                    "partial corpus is not publishable"
                                )
                            if request.provider_error_code is not None:
                                raise AShareDataError(
                                    "BaoStock Provider request failed with "
                                    f"{request.provider_error_code}; partial corpus is not publishable"
                                )
                            source_row_count += len(request.rows)
                            if source_row_count > self._maximum_source_rows:
                                raise AShareDataError(
                                    "BaoStock acquisition exceeds declared row ceiling"
                                )
                            yield request
            finally:
                if logged_in:
                    with redirect_stdout(StringIO()):
                        self._timed_logout(bs)
        finally:
            socket.setdefaulttimeout(previous_timeout)

    def _checkpointed_acquire_one(
        self,
        *,
        checkpoint_root: Path | None,
        **values: Any,
    ) -> HistoricalRawRequest:
        identity = _request_identity(**values)
        if checkpoint_root is None:
            return self._timed_acquire_one(**values)
        checkpoint_root.mkdir(parents=True, exist_ok=True)
        checkpoint = checkpoint_root / f"{canonical_hash(identity)[7:]}.json"
        if checkpoint.exists():
            return _load_request_checkpoint(checkpoint, identity)
        response = self._timed_acquire_one(**values)
        if response.provider_error_code is not None:
            return response
        payload = _checkpoint_payload(response, identity)
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

    def _load_existing_checkpoint(
        self,
        *,
        checkpoint_root: Path | None,
        **values: Any,
    ) -> HistoricalRawRequest | None:
        if checkpoint_root is None:
            return None
        identity = _request_identity(**values)
        checkpoint = checkpoint_root / f"{canonical_hash(identity)[7:]}.json"
        if not checkpoint.exists():
            return None
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
    "HistoricalArchivePrefetch",
    "HistoricalRequestCheckpointDescriptor",
]


class _BaoStockRequestTimeout(BaseException):
    """Escape Provider code that catches ordinary socket exceptions."""


def _assigned_request_indices(
    *,
    total: int,
    worker_index: int,
    worker_count: int,
) -> tuple[int, ...]:
    if total <= 0:
        raise ValueError("Historical request total must be positive")
    if worker_count <= 0:
        raise ValueError("Historical request worker count must be positive")
    if not 0 <= worker_index < worker_count:
        raise ValueError("Historical request worker index is outside worker count")
    return tuple(range(worker_index, total, worker_count))


def _request_identity(**values: Any) -> dict[str, str]:
    timeframe = values["timeframe"]
    if not isinstance(timeframe, Timeframe):
        raise ValueError("Historical checkpoint timeframe is invalid")
    fields = _DAILY_FIELDS if timeframe is Timeframe.DAILY else _MINUTE_FIELDS
    return {
        "provider_id": BAOSTOCK_HISTORICAL_PROVIDER_ID,
        "symbol": str(values["symbol"]),
        "timeframe": timeframe.value,
        "start_date": values["start_date"].isoformat(),
        "end_date": values["end_date"].isoformat(),
        "fields": ",".join(fields),
        "frequency": "d" if timeframe is Timeframe.DAILY else "5",
        "adjustflag": "3",
    }


def _ensure_acquisition_manifest(
    checkpoint_root: Path,
    manifest: Mapping[str, Any],
) -> None:
    checkpoint_root.mkdir(parents=True, exist_ok=True)
    path = checkpoint_root / "acquisition-manifest.json"
    envelope = {
        "manifest": dict(manifest),
        "manifest_hash": canonical_hash(dict(manifest)),
    }
    if path.exists():
        try:
            durable = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise AShareDataError(
                "Historical acquisition checkpoint manifest is unreadable"
            ) from exc
        if durable != envelope:
            raise AShareDataError(
                "Historical acquisition checkpoint manifest identity drift"
            )
        return
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".acquisition-manifest.",
        suffix=".tmp",
        dir=checkpoint_root,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(canonical_json(envelope))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary_name, path)
        except FileExistsError:
            durable = json.loads(path.read_text(encoding="utf-8"))
            if durable != envelope:
                raise AShareDataError(
                    "Historical acquisition checkpoint manifest identity drift"
                )
        _fsync_directory(checkpoint_root)
    finally:
        Path(temporary_name).unlink(missing_ok=True)


def _prepare_acquisition_scope(
    *,
    symbols: tuple[str, ...],
    start_date: date,
    end_date: date,
    timeframes: tuple[Timeframe, ...],
    timeframe_ranges: Mapping[Timeframe, tuple[date, date]] | None,
    bucket_count: int,
    checkpoint_root: Path | None,
    acquisition_id: str | None,
    maximum_source_requests: int,
) -> _AcquisitionScope:
    ordered_symbols = tuple(sorted(set(symbols)))
    ordered_timeframes = tuple(
        sorted(set(timeframes), key=lambda item: item.value)
    )
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
    if checkpoint_root is not None and not (
        acquisition_id is not None and acquisition_id.strip()
    ):
        raise ValueError("checkpointed Historical acquisition requires acquisition_id")
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
            raise ValueError("Historical timeframe range exceeds owner acquisition range")
    request_ranges = {
        timeframe: _request_ranges(timeframe, *bounds)
        for timeframe, bounds in ranges.items()
    }
    request_count = sum(len(items) for items in request_ranges.values()) * len(
        ordered_symbols
    )
    if request_count > maximum_source_requests:
        raise ValueError("Historical acquisition exceeds declared request ceiling")
    checkpoint_directory = None
    if checkpoint_root is not None:
        acquisition_manifest = {
            "schema_version": "baostock-historical-acquisition-manifest/v1",
            "acquisition_id": acquisition_id,
            "provider_id": BAOSTOCK_HISTORICAL_PROVIDER_ID,
            "symbols": list(ordered_symbols),
            "timeframe_ranges": {
                timeframe.value: {
                    "start_date": ranges[timeframe][0].isoformat(),
                    "end_date": ranges[timeframe][1].isoformat(),
                }
                for timeframe in ordered_timeframes
            },
            "bucket_count": bucket_count,
        }
        checkpoint_directory = (
            checkpoint_root / canonical_hash(acquisition_manifest)[7:]
        )
        _ensure_acquisition_manifest(
            checkpoint_directory,
            acquisition_manifest,
        )
    return _AcquisitionScope(
        ordered_symbols=ordered_symbols,
        ordered_timeframes=ordered_timeframes,
        ranges=ranges,
        request_ranges=request_ranges,
        checkpoint_directory=checkpoint_directory,
        expected_request_count=request_count,
    )


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
    schema_version = payload.get("schema_version")
    if schema_version == "baostock-historical-request-checkpoint/v1":
        envelope = {
            "schema_version": schema_version,
            "request_identity": payload.get("request_identity"),
            "response": payload.get("response"),
        }
        response_payload = envelope["response"]
    elif schema_version == "baostock-historical-request-checkpoint/v2":
        envelope = {
            "schema_version": schema_version,
            "request_identity": payload.get("request_identity"),
            "response_codec": payload.get("response_codec"),
            "response_hash": payload.get("response_hash"),
            "response_compressed": payload.get("response_compressed"),
        }
        response_payload = _decompress_checkpoint_response(envelope)
        if envelope["response_hash"] != canonical_hash(response_payload):
            raise AShareDataError("BaoStock request checkpoint response drift")
    else:
        raise AShareDataError("BaoStock request checkpoint identity drift")
    if (
        envelope["request_identity"] != dict(identity)
        or payload.get("checkpoint_hash") != canonical_hash(envelope)
        or not isinstance(response_payload, Mapping)
    ):
        raise AShareDataError("BaoStock request checkpoint identity drift")
    response = HistoricalRawRequest.from_canonical_dict(response_payload)
    if (
        response.provider_id != identity["provider_id"]
        or response.symbol != identity["symbol"]
        or response.timeframe.value != identity["timeframe"]
        or response.start_date.isoformat() != identity["start_date"]
        or response.end_date.isoformat() != identity["end_date"]
    ):
        raise AShareDataError("BaoStock request checkpoint response drift")
    return response


def _checkpoint_payload(
    response: HistoricalRawRequest,
    identity: Mapping[str, str],
) -> dict[str, object]:
    response_payload = response.to_canonical_dict()
    compressed = zlib.compress(
        canonical_json(response_payload).encode("utf-8"),
        level=9,
    )
    envelope = {
        "schema_version": "baostock-historical-request-checkpoint/v2",
        "request_identity": dict(identity),
        "response_codec": "ZLIB_BASE64_CANONICAL_JSON",
        "response_hash": canonical_hash(response_payload),
        "response_compressed": base64.b64encode(compressed).decode("ascii"),
    }
    return {**envelope, "checkpoint_hash": canonical_hash(envelope)}


def _decompress_checkpoint_response(
    envelope: Mapping[str, object],
) -> Mapping[str, Any]:
    encoded = envelope.get("response_compressed")
    if (
        envelope.get("response_codec") != "ZLIB_BASE64_CANONICAL_JSON"
        or not isinstance(encoded, str)
    ):
        raise AShareDataError("BaoStock request checkpoint identity drift")
    try:
        compressed = base64.b64decode(
            encoded,
            validate=True,
        )
        decoded = zlib.decompress(compressed).decode("utf-8")
        payload = json.loads(decoded)
    except (
        binascii.Error,
        UnicodeDecodeError,
        json.JSONDecodeError,
        zlib.error,
    ) as exc:
        raise AShareDataError("BaoStock request checkpoint is corrupt") from exc
    if not isinstance(payload, Mapping):
        raise AShareDataError("BaoStock request checkpoint is invalid")
    return payload


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
