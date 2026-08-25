"""Deterministic BaoStock Raw-to-Normalized historical derivation."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Mapping
from zoneinfo import ZoneInfo

from market_regime_alpha.application.historical_corpus.baostock_archive import (
    BAOSTOCK_HISTORICAL_PROVIDER_ID,
)
from market_regime_alpha.application.historical_corpus.contracts import (
    HistoricalArtifactKind,
    HistoricalCorpusCoverage,
    HistoricalDataOwner,
    HistoricalDataPartition,
    HistoricalListingStatus,
    HistoricalNormalizedBar,
    HistoricalRawRequest,
    HistoricalTradingStatus,
    build_partitions,
)
from market_regime_alpha.application.historical_corpus.artifacts import (
    HistoricalPackageIndex,
    read_verified_historical_partition,
)
from market_regime_alpha.application.historical_corpus.staged_package import (
    HistoricalOwnerMetadata,
    StagedHistoricalPackageWriter,
)
from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.market_data.contracts import Timeframe


BAOSTOCK_NORMALIZATION_VERSION = "baostock-historical-normalization/v1"
_SHANGHAI = ZoneInfo("Asia/Shanghai")


class HistoricalNormalizationError(ValueError):
    """Raised when deterministic normalization cannot preserve correctness."""


@dataclass(frozen=True, slots=True)
class _NormalizationBatch:
    bars: tuple[HistoricalNormalizedBar, ...]
    successful_request_count: int
    source_row_count: int
    missing_field_counts: tuple[tuple[str, int], ...]
    failure_counts: tuple[tuple[str, int], ...]


def normalize_baostock_requests(
    requests: tuple[HistoricalRawRequest, ...],
) -> tuple[HistoricalNormalizedBar, ...]:
    """Normalize one bounded Raw request partition."""

    return _normalize_request_batch(requests).bars


def normalize_historical_package(
    *,
    raw: HistoricalPackageIndex,
    artifact_root: Path,
) -> HistoricalPackageIndex:
    """Normalize a physical Raw owner one immutable partition at a time."""

    if (
        raw.artifact_kind is not HistoricalArtifactKind.RAW_PROVIDER_ARCHIVE
        or raw.provider_id != BAOSTOCK_HISTORICAL_PROVIDER_ID
    ):
        raise HistoricalNormalizationError(
            "BaoStock normalization requires exact Raw owner"
        )
    writer = StagedHistoricalPackageWriter(
        artifact_root=artifact_root,
        artifact_kind=HistoricalArtifactKind.NORMALIZED_DATASET,
        bucket_count=raw.bucket_count,
    )
    observed: set[str] = set()
    missing: Counter[str] = Counter()
    failures: Counter[str] = Counter()
    successful_request_count = 0
    source_row_count = 0
    normalized_row_count = 0
    try:
        for descriptor in raw.partitions:
            partition = read_verified_historical_partition(
                package=raw,
                descriptor=descriptor,
            )
            if any(
                not isinstance(item, HistoricalRawRequest)
                for item in partition.records
            ):
                raise HistoricalNormalizationError(
                    "Raw package contains normalized records"
                )
            requests = tuple(
                item
                for item in partition.records
                if isinstance(item, HistoricalRawRequest)
            )
            batch = _normalize_request_batch(requests)
            successful_request_count += batch.successful_request_count
            source_row_count += batch.source_row_count
            normalized_row_count += len(batch.bars)
            missing.update(dict(batch.missing_field_counts))
            failures.update(dict(batch.failure_counts))
            observed.update(item.symbol for item in batch.bars)
            if not batch.bars:
                continue
            writer.add_partition(
                HistoricalDataPartition.create(
                    artifact_kind=HistoricalArtifactKind.NORMALIZED_DATASET,
                    timeframe=descriptor.timeframe,
                    symbol_bucket=descriptor.symbol_bucket,
                    bucket_count=descriptor.bucket_count,
                    records=batch.bars,
                )
            )
        if normalized_row_count == 0:
            raise HistoricalNormalizationError("normalized Dataset has no valid rows")
        if (
            source_row_count != raw.coverage.source_row_count
            or successful_request_count != raw.coverage.successful_request_count
        ):
            raise HistoricalNormalizationError(
                "Raw package coverage diverges from physical requests"
            )
        limitations = tuple(
            sorted(
                {
                    "BAOSTOCK_HISTORICAL_NORMALIZATION",
                    "HISTORICAL_LISTING_STATUS_NOT_PROVIDED",
                    "MINUTE_ST_STATUS_NOT_PROVIDED",
                    *raw.limitations,
                }
            )
        )
        return writer.finalize(
            HistoricalOwnerMetadata(
                provider_id=raw.provider_id,
                normalization_version=BAOSTOCK_NORMALIZATION_VERSION,
                parent_reference=raw.reference,
                created_at=raw.created_at,
                retrieved_at=raw.retrieved_at,
                coverage=HistoricalCorpusCoverage(
                    expected_symbols=raw.coverage.expected_symbols,
                    observed_symbols=tuple(sorted(observed)),
                    expected_request_count=raw.coverage.expected_request_count,
                    successful_request_count=successful_request_count,
                    source_row_count=source_row_count,
                    normalized_row_count=normalized_row_count,
                    missing_field_counts=tuple(sorted(missing.items())),
                    failure_counts=tuple(sorted(failures.items())),
                ),
                limitations=limitations,
            )
        )
    except BaseException:
        writer.abort()
        raise


def normalize_baostock_archive(raw_owner: HistoricalDataOwner) -> HistoricalDataOwner:
    raw_owner.verify_identity()
    if (
        raw_owner.artifact_kind is not HistoricalArtifactKind.RAW_PROVIDER_ARCHIVE
        or raw_owner.provider_id != BAOSTOCK_HISTORICAL_PROVIDER_ID
    ):
        raise HistoricalNormalizationError("BaoStock normalization requires exact Raw owner")
    bars: list[HistoricalNormalizedBar] = []
    failures: Counter[str] = Counter()
    missing: Counter[str] = Counter()
    requests = []
    source_row_count = 0
    for partition in raw_owner.partitions:
        for record in partition.records:
            if not isinstance(record, HistoricalRawRequest):
                raise HistoricalNormalizationError("Raw owner contains normalized records")
            requests.append(record)
            source_row_count += len(record.rows)
            if not record.succeeded:
                failures[f"PROVIDER_ERROR::{record.provider_error_code}"] += 1
                continue
            for row_number, raw_row in enumerate(record.rows, 1):
                try:
                    bar = _normalize_row(record, raw_row, row_number)
                except HistoricalNormalizationError as exc:
                    failures[f"ROW_REJECTED::{exc}"] += 1
                    continue
                bars.append(bar)
                missing.update(bar.missing_fields)
    if not bars:
        raise HistoricalNormalizationError("normalized Dataset has no valid rows")
    duplicate_keys = Counter(
        (item.symbol, item.timeframe, item.event_start) for item in bars
    )
    duplicates = tuple(key for key, count in duplicate_keys.items() if count > 1)
    if duplicates:
        raise HistoricalNormalizationError(
            f"duplicate normalized event facts: {len(duplicates)}"
        )
    partitions = build_partitions(
        artifact_kind=HistoricalArtifactKind.NORMALIZED_DATASET,
        records=tuple(bars),
        bucket_count=raw_owner.bucket_count,
    )
    observed = tuple(sorted({item.symbol for item in bars}))
    limitations = {
        "BAOSTOCK_HISTORICAL_NORMALIZATION",
        "HISTORICAL_LISTING_STATUS_NOT_PROVIDED",
        "MINUTE_ST_STATUS_NOT_PROVIDED",
        *raw_owner.limitations,
    }
    return HistoricalDataOwner.create(
        artifact_kind=HistoricalArtifactKind.NORMALIZED_DATASET,
        provider_id=raw_owner.provider_id,
        normalization_version=BAOSTOCK_NORMALIZATION_VERSION,
        parent_reference=raw_owner.reference,
        # Logical derivation time is frozen to the immutable Raw owner so retrying
        # normalization cannot change identity merely because wall time advanced.
        created_at=raw_owner.created_at,
        retrieved_at=raw_owner.retrieved_at,
        first_market_date=min(item.first_market_date for item in partitions),
        last_market_date=max(item.last_market_date for item in partitions),
        bucket_count=raw_owner.bucket_count,
        partitions=partitions,
        coverage=HistoricalCorpusCoverage(
            expected_symbols=raw_owner.coverage.expected_symbols,
            observed_symbols=observed,
            expected_request_count=raw_owner.coverage.expected_request_count,
            successful_request_count=sum(item.succeeded for item in requests),
            source_row_count=source_row_count,
            normalized_row_count=len(bars),
            missing_field_counts=tuple(sorted(missing.items())),
            failure_counts=tuple(sorted(failures.items())),
        ),
        limitations=tuple(sorted(limitations)),
    )


def _normalize_request_batch(
    requests: tuple[HistoricalRawRequest, ...],
) -> _NormalizationBatch:
    bars: list[HistoricalNormalizedBar] = []
    failures: Counter[str] = Counter()
    missing: Counter[str] = Counter()
    source_row_count = 0
    for request in requests:
        source_row_count += len(request.rows)
        if not request.succeeded:
            failures[f"PROVIDER_ERROR::{request.provider_error_code}"] += 1
            continue
        for row_number, raw_row in enumerate(request.rows, 1):
            try:
                bar = _normalize_row(request, raw_row, row_number)
            except HistoricalNormalizationError as exc:
                failures[f"ROW_REJECTED::{exc}"] += 1
                continue
            bars.append(bar)
            missing.update(bar.missing_fields)
    duplicate_keys = Counter(
        (item.symbol, item.timeframe, item.event_start) for item in bars
    )
    duplicate_count = sum(
        count - 1 for count in duplicate_keys.values() if count > 1
    )
    if duplicate_count:
        raise HistoricalNormalizationError(
            f"duplicate normalized event facts: {duplicate_count}"
        )
    return _NormalizationBatch(
        bars=tuple(
            sorted(
                bars,
                key=lambda item: (
                    item.market_date,
                    item.symbol,
                    item.event_start,
                    str(item.bar_id),
                ),
            )
        ),
        successful_request_count=sum(item.succeeded for item in requests),
        source_row_count=source_row_count,
        missing_field_counts=tuple(sorted(missing.items())),
        failure_counts=tuple(sorted(failures.items())),
    )


def _normalize_row(
    request: HistoricalRawRequest,
    raw_row: tuple[str, ...],
    row_number: int,
) -> HistoricalNormalizedBar:
    row = dict(zip(request.fields, raw_row, strict=True))
    event_start, event_end, market_date = _event_times(request, row)
    if not request.start_date <= market_date <= request.end_date:
        raise HistoricalNormalizationError("EVENT_OUTSIDE_REQUEST_RANGE")
    status = _trading_status(row.get("tradestatus"))
    missing_fields = []
    prices = _prices(row, status=status)
    if prices[0] is None:
        missing_fields.append("OHLC")
    volume = _decimal(row.get("volume"), label="VOLUME", allow_blank=True)
    if volume is None:
        missing_fields.append("VOLUME")
        volume = Decimal("0")
    amount = _decimal(row.get("amount"), label="AMOUNT", allow_blank=True)
    if amount is None:
        missing_fields.append("AMOUNT")
    raw_st = row.get("isST")
    st_status = None if raw_st in {None, ""} else raw_st == "1"
    if st_status is None:
        missing_fields.append("ST_STATUS")
    missing_fields.append("LISTING_STATUS")
    limitations = {
        "HISTORICAL_LISTING_STATUS_NOT_PROVIDED",
        "RETROSPECTIVE_PROVIDER_RETRIEVAL",
    }
    if request.timeframe is Timeframe.MINUTE_5:
        limitations.add("MINUTE_ST_STATUS_NOT_PROVIDED")
    return HistoricalNormalizedBar.create(
        symbol=request.symbol,
        timeframe=request.timeframe,
        market_date=market_date,
        event_start=event_start,
        event_end=event_end,
        retrieved_at=request.retrieved_at,
        open=prices[0],
        high=prices[1],
        low=prices[2],
        close=prices[3],
        volume=volume,
        amount=amount,
        adjustment_basis="BAOSTOCK_ADJUSTFLAG_3_RAW",
        trading_status=status,
        st_status=st_status,
        listing_status=HistoricalListingStatus.UNKNOWN,
        raw_request_reference=ValidationArtifactReference(
            "RAW_PROVIDER_REQUEST", request.request_id, request.content_hash
        ),
        raw_row_number=row_number,
        missing_fields=tuple(sorted(set(missing_fields))),
        limitations=tuple(sorted(limitations)),
    )


def _event_times(
    request: HistoricalRawRequest,
    row: Mapping[str, str],
) -> tuple[datetime, datetime, date]:
    raw_date = row.get("date")
    if not raw_date:
        raise HistoricalNormalizationError("DATE_MISSING")
    try:
        market_date = datetime.strptime(raw_date, "%Y-%m-%d").date()
    except ValueError as exc:
        raise HistoricalNormalizationError("DATE_INVALID") from exc
    if request.timeframe is Timeframe.DAILY:
        start = datetime.combine(market_date, time(9, 30), _SHANGHAI)
        end = datetime.combine(market_date, time(15, 0), _SHANGHAI)
    else:
        raw_time = row.get("time")
        if not raw_time:
            raise HistoricalNormalizationError("MINUTE_TIME_MISSING")
        try:
            parsed = datetime.strptime(raw_time, "%Y%m%d%H%M%S%f").replace(
                tzinfo=_SHANGHAI
            )
        except ValueError as exc:
            raise HistoricalNormalizationError("MINUTE_TIME_INVALID") from exc
        if parsed.date() != market_date:
            raise HistoricalNormalizationError("MINUTE_DATE_MISMATCH")
        end = parsed
        start = end - timedelta(minutes=5)
    return (
        start.astimezone(UTC).replace(microsecond=0),
        end.astimezone(UTC).replace(microsecond=0),
        market_date,
    )


def _prices(
    row: Mapping[str, str],
    *,
    status: HistoricalTradingStatus,
) -> tuple[Decimal | None, Decimal | None, Decimal | None, Decimal | None]:
    values = tuple(
        _decimal(row.get(name), label=name.upper(), allow_blank=True)
        for name in ("open", "high", "low", "close")
    )
    if all(item is None or item == 0 for item in values):
        if status is HistoricalTradingStatus.TRADING:
            raise HistoricalNormalizationError("TRADING_ROW_OHLC_MISSING")
        return (None, None, None, None)
    if any(item is None or item <= 0 for item in values):
        raise HistoricalNormalizationError("OHLC_PARTIAL_OR_NON_POSITIVE")
    return (values[0], values[1], values[2], values[3])


def _decimal(
    value: str | None,
    *,
    label: str,
    allow_blank: bool,
) -> Decimal | None:
    if value in {None, ""}:
        if allow_blank:
            return None
        raise HistoricalNormalizationError(f"{label}_MISSING")
    assert value is not None
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise HistoricalNormalizationError(f"{label}_INVALID") from exc
    if not parsed.is_finite() or parsed < 0:
        raise HistoricalNormalizationError(f"{label}_INVALID")
    return parsed


def _trading_status(value: str | None) -> HistoricalTradingStatus:
    if value == "1":
        return HistoricalTradingStatus.TRADING
    if value == "0":
        return HistoricalTradingStatus.SUSPENDED
    return HistoricalTradingStatus.UNKNOWN


__all__ = [
    "BAOSTOCK_NORMALIZATION_VERSION",
    "HistoricalNormalizationError",
    "normalize_baostock_archive",
    "normalize_baostock_requests",
    "normalize_historical_package",
]
