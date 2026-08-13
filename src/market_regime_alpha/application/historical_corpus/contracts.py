"""Immutable contracts for Phase E raw, normalized and research packages.

These contracts deliberately keep retrospective event time separate from true
provider retrieval time.  They cannot be consumed as Live or Formal PIT market
data artifacts.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Mapping, TypeAlias, cast

from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import (
    canonical_datetime,
    canonical_hash,
    require_sha256,
    require_text,
    require_unique_text,
)
from market_regime_alpha.market_data.contracts import (
    Timeframe,
    canonical_decimal,
    parse_canonical_decimal,
    parse_utc_second,
    require_utc_second,
)


HISTORICAL_RAW_REQUEST_SCHEMA = "historical-raw-request/v1"
HISTORICAL_NORMALIZED_BAR_SCHEMA = "historical-normalized-bar/v1"
HISTORICAL_PARTITION_SCHEMA_V1 = "historical-data-partition/v1"
HISTORICAL_PARTITION_SCHEMA_V2 = "historical-data-partition/v2"
HISTORICAL_PARTITION_SCHEMA = "historical-data-partition/v3"
HISTORICAL_OWNER_SCHEMA = "historical-data-owner/v1"
HISTORICAL_AVAILABILITY_BASIS = "RETROSPECTIVE_EVENT_TIME"
HISTORICAL_EVIDENCE_LIMITATIONS = (
    "CALIBRATED_FALSE",
    "EXPLORATORY",
    "FORMAL_OOS_FALSE",
    "FORMAL_PIT_NOT_ESTABLISHED",
    "NO_TRADING_AUTHORITY",
    "PIT_INCOMPLETE",
    "RETRIEVED_AFTER_HISTORICAL_DECISION_TIME",
)


class HistoricalArtifactKind(str, Enum):
    RAW_PROVIDER_ARCHIVE = "RAW_PROVIDER_ARCHIVE"
    NORMALIZED_DATASET = "NORMALIZED_DATASET"
    RESEARCH_MATERIALIZATION = "RESEARCH_MATERIALIZATION"


class HistoricalTradingStatus(str, Enum):
    TRADING = "TRADING"
    SUSPENDED = "SUSPENDED"
    UNKNOWN = "UNKNOWN"


class HistoricalListingStatus(str, Enum):
    LISTED = "LISTED"
    DELISTED = "DELISTED"
    PRE_LISTING = "PRE_LISTING"
    UNKNOWN = "UNKNOWN"


def _require_sorted_unique(label: str, values: tuple[str, ...]) -> None:
    require_unique_text(label, values)
    if values != tuple(sorted(values)):
        raise ValueError(f"{label} must be sorted")


def _require_optional_text(label: str, value: str | None) -> None:
    if value is not None:
        require_text(label, value)


@dataclass(frozen=True, slots=True)
class HistoricalRawRequest:
    request_id: ArtifactId
    content_hash: str
    provider_id: str
    product: str
    symbol: str
    timeframe: Timeframe
    start_date: date
    end_date: date
    request_parameters: tuple[tuple[str, str], ...]
    requested_at: datetime
    retrieved_at: datetime
    provider_error_code: str | None
    provider_error_message: str | None
    fields: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]
    limitations: tuple[str, ...]
    schema_version: str = HISTORICAL_RAW_REQUEST_SCHEMA

    def __post_init__(self) -> None:
        if self.schema_version != HISTORICAL_RAW_REQUEST_SCHEMA:
            raise ValueError("unsupported Historical Raw request schema")
        require_sha256("content_hash", self.content_hash)
        require_text("provider_id", self.provider_id)
        require_text("product", self.product)
        require_text("symbol", self.symbol)
        if self.start_date > self.end_date:
            raise ValueError("Historical Raw request date range is reversed")
        if self.start_date.year != self.end_date.year:
            raise ValueError("Historical Raw requests must be split by calendar year")
        require_utc_second("requested_at", self.requested_at)
        require_utc_second("retrieved_at", self.retrieved_at)
        if self.retrieved_at < self.requested_at:
            raise ValueError("Historical Raw retrieval predates request")
        parameters = tuple(key for key, _ in self.request_parameters)
        if parameters != tuple(sorted(set(parameters))):
            raise ValueError("Historical Raw request parameters must be sorted and unique")
        for key, value in self.request_parameters:
            require_text("request parameter", key)
            if not isinstance(value, str):
                raise TypeError("request parameter value must be text")
        _require_optional_text("provider_error_code", self.provider_error_code)
        _require_optional_text("provider_error_message", self.provider_error_message)
        if (self.provider_error_code is None) != (self.provider_error_message is None):
            raise ValueError("provider error code/message must be paired")
        _require_sorted_unique("fields", self.fields)
        if any(len(row) != len(self.fields) for row in self.rows):
            raise ValueError("Historical Raw row width does not match fields")
        if self.provider_error_code is not None and self.rows:
            raise ValueError("failed Historical Raw request cannot carry rows")
        _require_sorted_unique("limitation", self.limitations)
        self.verify_identity()

    @classmethod
    def create(
        cls,
        *,
        provider_id: str,
        product: str,
        symbol: str,
        timeframe: Timeframe,
        start_date: date,
        end_date: date,
        request_parameters: tuple[tuple[str, str], ...],
        requested_at: datetime,
        retrieved_at: datetime,
        fields: tuple[str, ...],
        rows: tuple[tuple[str, ...], ...],
        provider_error_code: str | None = None,
        provider_error_message: str | None = None,
        limitations: tuple[str, ...] = (),
    ) -> HistoricalRawRequest:
        values = {
            "provider_id": provider_id,
            "product": product,
            "symbol": symbol,
            "timeframe": timeframe,
            "start_date": start_date,
            "end_date": end_date,
            "request_parameters": tuple(sorted(request_parameters)),
            "requested_at": requested_at,
            "retrieved_at": retrieved_at,
            "provider_error_code": provider_error_code,
            "provider_error_message": provider_error_message,
            "fields": tuple(sorted(fields)),
            "rows": rows,
            "limitations": tuple(sorted(set(limitations))),
        }
        # Provider field order determines row meaning. Canonicalize by reordering
        # rows together with fields, never by sorting field labels alone.
        ordered_fields = tuple(sorted(fields))
        if ordered_fields != fields:
            indexes = tuple(fields.index(item) for item in ordered_fields)
            values["rows"] = tuple(tuple(row[index] for index in indexes) for row in rows)
        digest = canonical_hash(_raw_payload(**values))
        return cls(
            request_id=ArtifactId(f"historical-raw-request-{digest[7:31]}"),
            content_hash=digest,
            **cast(Any, values),
        )

    @property
    def succeeded(self) -> bool:
        return self.provider_error_code is None

    def semantic_payload(self) -> dict[str, Any]:
        return _raw_payload(**_raw_values(self))

    def verify_identity(self) -> None:
        digest = canonical_hash(self.semantic_payload())
        if digest != self.content_hash:
            raise ValueError("Historical Raw request hash mismatch")
        if str(self.request_id) != f"historical-raw-request-{digest[7:31]}":
            raise ValueError("Historical Raw request identity mismatch")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "request_id": str(self.request_id),
            "content_hash": self.content_hash,
            **self.semantic_payload(),
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> HistoricalRawRequest:
        result = cls(
            request_id=ArtifactId(str(payload["request_id"])),
            content_hash=str(payload["content_hash"]),
            provider_id=str(payload["provider_id"]),
            product=str(payload["product"]),
            symbol=str(payload["symbol"]),
            timeframe=Timeframe(str(payload["timeframe"])),
            start_date=date.fromisoformat(str(payload["start_date"])),
            end_date=date.fromisoformat(str(payload["end_date"])),
            request_parameters=tuple(
                (str(item["name"]), str(item["value"]))
                for item in _objects(payload["request_parameters"], "request_parameters")
            ),
            requested_at=parse_utc_second("requested_at", payload["requested_at"]),
            retrieved_at=parse_utc_second("retrieved_at", payload["retrieved_at"]),
            provider_error_code=_optional_string(payload["provider_error_code"]),
            provider_error_message=_optional_string(payload["provider_error_message"]),
            fields=_strings(payload["fields"], "fields"),
            rows=tuple(
                _strings(item, "raw row") for item in _arrays(payload["rows"], "rows")
            ),
            limitations=_strings(payload["limitations"], "limitations"),
            schema_version=str(payload["schema_version"]),
        )
        return result


@dataclass(frozen=True, slots=True)
class HistoricalNormalizedBar:
    bar_id: ArtifactId
    content_hash: str
    symbol: str
    timeframe: Timeframe
    market_date: date
    event_start: datetime
    event_end: datetime
    retrieved_at: datetime
    open: Decimal | None
    high: Decimal | None
    low: Decimal | None
    close: Decimal | None
    volume: Decimal
    amount: Decimal | None
    adjustment_basis: str
    trading_status: HistoricalTradingStatus
    st_status: bool | None
    listing_status: HistoricalListingStatus
    raw_request_reference: ValidationArtifactReference
    raw_row_number: int
    missing_fields: tuple[str, ...]
    limitations: tuple[str, ...]
    schema_version: str = HISTORICAL_NORMALIZED_BAR_SCHEMA

    def __post_init__(self) -> None:
        if self.schema_version != HISTORICAL_NORMALIZED_BAR_SCHEMA:
            raise ValueError("unsupported Historical normalized bar schema")
        require_sha256("content_hash", self.content_hash)
        require_text("symbol", self.symbol)
        require_text("adjustment_basis", self.adjustment_basis)
        require_utc_second("event_start", self.event_start)
        require_utc_second("event_end", self.event_end)
        require_utc_second("retrieved_at", self.retrieved_at)
        if self.event_start >= self.event_end:
            raise ValueError("Historical normalized event range is invalid")
        if self.retrieved_at < self.event_end:
            raise ValueError("Historical normalized retrieval predates event")
        if self.event_start.date() != self.market_date:
            raise ValueError("Historical normalized market date mismatch")
        prices = (self.open, self.high, self.low, self.close)
        if any(item is None for item in prices) and any(item is not None for item in prices):
            raise ValueError("Historical normalized OHLC must be present or absent together")
        if self.trading_status is HistoricalTradingStatus.TRADING and self.open is None:
            raise ValueError("trading Historical bar requires OHLC")
        for label, decimal_value in (
            ("open", self.open),
            ("high", self.high),
            ("low", self.low),
            ("close", self.close),
        ):
            if decimal_value is not None and (
                not decimal_value.is_finite() or decimal_value <= 0
            ):
                raise ValueError(f"{label} must be positive and finite")
        if self.open is not None:
            assert self.high is not None and self.low is not None and self.close is not None
            if self.high < max(self.open, self.low, self.close) or self.low > min(
                self.open, self.high, self.close
            ):
                raise ValueError("Historical normalized OHLC ordering is invalid")
        if not self.volume.is_finite() or self.volume < 0:
            raise ValueError("Historical normalized volume must be non-negative")
        if self.amount is not None and (not self.amount.is_finite() or self.amount < 0):
            raise ValueError("Historical normalized amount must be non-negative")
        if self.raw_request_reference.artifact_kind != "RAW_PROVIDER_REQUEST":
            raise ValueError("Historical normalized bar requires Raw request lineage")
        if self.raw_row_number <= 0:
            raise ValueError("Historical normalized raw row number must be positive")
        _require_sorted_unique("missing_field", self.missing_fields)
        _require_sorted_unique("limitation", self.limitations)
        self.verify_identity()

    @classmethod
    def create(cls, **values: Any) -> HistoricalNormalizedBar:
        values["missing_fields"] = tuple(sorted(set(values.get("missing_fields", ()))))
        values["limitations"] = tuple(sorted(set(values.get("limitations", ()))))
        digest = canonical_hash(_bar_payload(**values))
        return cls(
            bar_id=ArtifactId(f"historical-normalized-bar-{digest[7:31]}"),
            content_hash=digest,
            **cast(Any, values),
        )

    def semantic_payload(self) -> dict[str, Any]:
        return _bar_payload(**_bar_values(self))

    def verify_identity(self) -> None:
        digest = canonical_hash(self.semantic_payload())
        if digest != self.content_hash:
            raise ValueError("Historical normalized bar hash mismatch")
        if str(self.bar_id) != f"historical-normalized-bar-{digest[7:31]}":
            raise ValueError("Historical normalized bar identity mismatch")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "bar_id": str(self.bar_id),
            "content_hash": self.content_hash,
            **self.semantic_payload(),
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> HistoricalNormalizedBar:
        return cls(
            bar_id=ArtifactId(str(payload["bar_id"])),
            content_hash=str(payload["content_hash"]),
            symbol=str(payload["symbol"]),
            timeframe=Timeframe(str(payload["timeframe"])),
            market_date=date.fromisoformat(str(payload["market_date"])),
            event_start=parse_utc_second("event_start", payload["event_start"]),
            event_end=parse_utc_second("event_end", payload["event_end"]),
            retrieved_at=parse_utc_second("retrieved_at", payload["retrieved_at"]),
            open=_optional_decimal(payload["open"], "open"),
            high=_optional_decimal(payload["high"], "high"),
            low=_optional_decimal(payload["low"], "low"),
            close=_optional_decimal(payload["close"], "close"),
            volume=parse_canonical_decimal("volume", payload["volume"]),
            amount=(
                parse_canonical_decimal("amount", payload["amount"])
                if payload["amount"] is not None
                else None
            ),
            adjustment_basis=str(payload["adjustment_basis"]),
            trading_status=HistoricalTradingStatus(str(payload["trading_status"])),
            st_status=(
                bool(payload["st_status"])
                if payload["st_status"] is not None
                else None
            ),
            listing_status=HistoricalListingStatus(str(payload["listing_status"])),
            raw_request_reference=ValidationArtifactReference.from_canonical_dict(
                payload["raw_request_reference"]
            ),
            raw_row_number=int(payload["raw_row_number"]),
            missing_fields=_strings(payload["missing_fields"], "missing_fields"),
            limitations=_strings(payload["limitations"], "limitations"),
            schema_version=str(payload["schema_version"]),
        )


HistoricalPartitionRecord: TypeAlias = HistoricalRawRequest | HistoricalNormalizedBar


@dataclass(frozen=True, slots=True)
class HistoricalDataPartition:
    partition_id: ArtifactId
    content_hash: str
    artifact_kind: HistoricalArtifactKind
    timeframe: Timeframe
    first_market_date: date
    last_market_date: date
    symbol_bucket: int
    bucket_count: int
    row_count: int
    symbol_count: int
    relative_path: str
    records: tuple[HistoricalPartitionRecord, ...]
    schema_version: str = HISTORICAL_PARTITION_SCHEMA

    def __post_init__(self) -> None:
        if self.schema_version not in {
            HISTORICAL_PARTITION_SCHEMA_V1,
            HISTORICAL_PARTITION_SCHEMA_V2,
            HISTORICAL_PARTITION_SCHEMA,
        }:
            raise ValueError("unsupported Historical partition schema")
        if self.artifact_kind is HistoricalArtifactKind.RESEARCH_MATERIALIZATION:
            raise ValueError("research materialization uses JSON component packages")
        require_sha256("content_hash", self.content_hash)
        if not 0 <= self.symbol_bucket < self.bucket_count or self.bucket_count <= 0:
            raise ValueError("Historical partition bucket is invalid")
        if self.row_count != len(self.records) or self.row_count <= 0:
            raise ValueError("Historical partition row count mismatch")
        symbols = {item.symbol for item in self.records}
        if self.symbol_count != len(symbols):
            raise ValueError("Historical partition symbol count mismatch")
        first_dates, last_dates = _partition_record_dates(
            self.records,
            schema_version=self.schema_version,
        )
        if (
            self.first_market_date != min(first_dates)
            or self.last_market_date != max(last_dates)
        ):
            raise ValueError("Historical partition date range mismatch")
        if any(item.timeframe is not self.timeframe for item in self.records):
            raise ValueError("Historical partition timeframe mismatch")
        if any(_stable_bucket(item.symbol, self.bucket_count) != self.symbol_bucket for item in self.records):
            raise ValueError("Historical partition symbol bucket mismatch")
        keys = tuple(_record_sort_key(item) for item in self.records)
        if keys != tuple(sorted(set(keys))):
            raise ValueError("Historical partition records must be unique and sorted")
        if self.relative_path != _partition_relative_path(self):
            raise ValueError("Historical partition path mismatch")
        self.verify_identity()

    @classmethod
    def create(
        cls,
        *,
        artifact_kind: HistoricalArtifactKind,
        timeframe: Timeframe,
        symbol_bucket: int,
        bucket_count: int,
        records: tuple[HistoricalPartitionRecord, ...],
        schema_version: str = HISTORICAL_PARTITION_SCHEMA,
    ) -> HistoricalDataPartition:
        ordered = tuple(sorted(records, key=_record_sort_key))
        if not ordered:
            raise ValueError("Historical partition requires records")
        if schema_version not in {
            HISTORICAL_PARTITION_SCHEMA_V1,
            HISTORICAL_PARTITION_SCHEMA_V2,
            HISTORICAL_PARTITION_SCHEMA,
        }:
            raise ValueError("unsupported Historical partition schema")
        first_dates, last_dates = _partition_record_dates(
            ordered,
            schema_version=schema_version,
        )
        values = {
            "schema_version": schema_version,
            "artifact_kind": artifact_kind,
            "timeframe": timeframe,
            "first_market_date": min(first_dates),
            "last_market_date": max(last_dates),
            "symbol_bucket": symbol_bucket,
            "bucket_count": bucket_count,
            "row_count": len(ordered),
            "symbol_count": len({item.symbol for item in ordered}),
            "records": ordered,
        }
        digest = canonical_hash(_partition_payload(**values))
        return cls(
            partition_id=ArtifactId(f"historical-data-partition-{digest[7:31]}"),
            content_hash=digest,
            relative_path=_partition_path(
                artifact_kind=artifact_kind,
                timeframe=timeframe,
                first_market_date=min(first_dates),
                last_market_date=max(last_dates),
                symbol_bucket=symbol_bucket,
                schema_version=schema_version,
            ),
            **cast(Any, values),
        )

    @classmethod
    def from_reference_dict(
        cls,
        payload: Mapping[str, Any],
        *,
        records: tuple[HistoricalPartitionRecord, ...],
    ) -> HistoricalDataPartition:
        schema_version = str(
            payload.get("schema_version", HISTORICAL_PARTITION_SCHEMA_V1)
        )
        result = cls.create(
            artifact_kind=HistoricalArtifactKind(str(payload["artifact_kind"])),
            timeframe=Timeframe(str(payload["timeframe"])),
            symbol_bucket=int(payload["symbol_bucket"]),
            bucket_count=int(payload["bucket_count"]),
            records=records,
            schema_version=schema_version,
        )
        if result.reference_dict() != dict(payload):
            raise ValueError("Historical partition logical projection mismatch")
        return result

    def semantic_payload(self) -> dict[str, Any]:
        return _partition_payload(
            schema_version=self.schema_version,
            artifact_kind=self.artifact_kind,
            timeframe=self.timeframe,
            first_market_date=self.first_market_date,
            last_market_date=self.last_market_date,
            symbol_bucket=self.symbol_bucket,
            bucket_count=self.bucket_count,
            row_count=self.row_count,
            symbol_count=self.symbol_count,
            records=self.records,
        )

    def verify_identity(self) -> None:
        digest = canonical_hash(self.semantic_payload())
        if digest != self.content_hash:
            raise ValueError("Historical partition hash mismatch")
        if str(self.partition_id) != f"historical-data-partition-{digest[7:31]}":
            raise ValueError("Historical partition identity mismatch")

    def reference_dict(self) -> dict[str, Any]:
        result = {
            "partition_id": str(self.partition_id),
            "content_hash": self.content_hash,
            "artifact_kind": self.artifact_kind.value,
            "timeframe": self.timeframe.value,
            "first_market_date": self.first_market_date.isoformat(),
            "last_market_date": self.last_market_date.isoformat(),
            "symbol_bucket": self.symbol_bucket,
            "bucket_count": self.bucket_count,
            "row_count": self.row_count,
            "symbol_count": self.symbol_count,
            "relative_path": self.relative_path,
        }
        if self.schema_version != HISTORICAL_PARTITION_SCHEMA_V1:
            result["schema_version"] = self.schema_version
        return result


@dataclass(frozen=True, slots=True)
class HistoricalCorpusCoverage:
    expected_symbols: tuple[str, ...]
    observed_symbols: tuple[str, ...]
    expected_request_count: int
    successful_request_count: int
    source_row_count: int
    normalized_row_count: int
    missing_field_counts: tuple[tuple[str, int], ...]
    failure_counts: tuple[tuple[str, int], ...]

    def __post_init__(self) -> None:
        _require_sorted_unique("expected_symbols", self.expected_symbols)
        _require_sorted_unique("observed_symbols", self.observed_symbols)
        if not set(self.observed_symbols).issubset(self.expected_symbols):
            raise ValueError("Historical observed symbols exceed expected scope")
        counts = (
            self.expected_request_count,
            self.successful_request_count,
            self.source_row_count,
            self.normalized_row_count,
        )
        if any(isinstance(item, bool) or item < 0 for item in counts):
            raise ValueError("Historical coverage counts must be non-negative")
        if self.successful_request_count > self.expected_request_count:
            raise ValueError("successful requests exceed expected requests")
        for label, values in (
            ("missing_field_counts", self.missing_field_counts),
            ("failure_counts", self.failure_counts),
        ):
            keys = tuple(key for key, _ in values)
            if keys != tuple(sorted(set(keys))) or any(count <= 0 for _, count in values):
                raise ValueError(f"{label} must have sorted keys and positive counts")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "expected_symbols": list(self.expected_symbols),
            "observed_symbols": list(self.observed_symbols),
            "expected_request_count": self.expected_request_count,
            "successful_request_count": self.successful_request_count,
            "source_row_count": self.source_row_count,
            "normalized_row_count": self.normalized_row_count,
            "missing_field_counts": [
                {"name": name, "count": count}
                for name, count in self.missing_field_counts
            ],
            "failure_counts": [
                {"name": name, "count": count} for name, count in self.failure_counts
            ],
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> HistoricalCorpusCoverage:
        return cls(
            expected_symbols=_strings(payload["expected_symbols"], "expected_symbols"),
            observed_symbols=_strings(payload["observed_symbols"], "observed_symbols"),
            expected_request_count=int(payload["expected_request_count"]),
            successful_request_count=int(payload["successful_request_count"]),
            source_row_count=int(payload["source_row_count"]),
            normalized_row_count=int(payload["normalized_row_count"]),
            missing_field_counts=_count_pairs(payload["missing_field_counts"]),
            failure_counts=_count_pairs(payload["failure_counts"]),
        )


@dataclass(frozen=True, slots=True)
class HistoricalDataOwner:
    owner_id: ArtifactId
    content_hash: str
    artifact_kind: HistoricalArtifactKind
    provider_id: str
    normalization_version: str | None
    parent_reference: ValidationArtifactReference | None
    created_at: datetime
    retrieved_at: datetime
    first_market_date: date
    last_market_date: date
    bucket_count: int
    partitions: tuple[HistoricalDataPartition, ...]
    coverage: HistoricalCorpusCoverage
    availability_basis: str
    data_eligibility: str
    formal_pit_status: str
    limitations: tuple[str, ...]
    schema_version: str = HISTORICAL_OWNER_SCHEMA

    def __post_init__(self) -> None:
        if self.schema_version != HISTORICAL_OWNER_SCHEMA:
            raise ValueError("unsupported Historical data owner schema")
        require_sha256("content_hash", self.content_hash)
        require_text("provider_id", self.provider_id)
        _require_optional_text("normalization_version", self.normalization_version)
        require_utc_second("created_at", self.created_at)
        require_utc_second("retrieved_at", self.retrieved_at)
        if self.created_at < self.retrieved_at:
            raise ValueError("Historical owner predates provider retrieval")
        if self.first_market_date > self.last_market_date:
            raise ValueError("Historical owner date range is reversed")
        if self.bucket_count <= 0:
            raise ValueError("Historical owner bucket count must be positive")
        if not self.partitions:
            raise ValueError("Historical owner requires partitions")
        if any(
            item.artifact_kind is not self.artifact_kind
            or item.bucket_count != self.bucket_count
            for item in self.partitions
        ):
            raise ValueError("Historical owner partition contract mismatch")
        keys = tuple(
            (item.timeframe.value, item.first_market_date, item.symbol_bucket)
            for item in self.partitions
        )
        if keys != tuple(sorted(set(keys))):
            raise ValueError("Historical owner partitions must be unique and sorted")
        relative_paths = tuple(item.relative_path for item in self.partitions)
        if len(relative_paths) != len(set(relative_paths)):
            raise ValueError("Historical owner partition paths must be unique")
        if self.first_market_date != min(item.first_market_date for item in self.partitions):
            raise ValueError("Historical owner first date mismatch")
        if self.last_market_date != max(item.last_market_date for item in self.partitions):
            raise ValueError("Historical owner last date mismatch")
        if self.availability_basis != HISTORICAL_AVAILABILITY_BASIS:
            raise ValueError("Historical owner must declare retrospective event time")
        if self.data_eligibility != "EXPLORATORY" or self.formal_pit_status != "PIT_INCOMPLETE":
            raise ValueError("Historical free data cannot exceed exploratory PIT-incomplete")
        _require_sorted_unique("limitation", self.limitations)
        if not set(HISTORICAL_EVIDENCE_LIMITATIONS).issubset(self.limitations):
            raise ValueError("Historical evidence ceiling is incomplete")
        if self.artifact_kind is HistoricalArtifactKind.RAW_PROVIDER_ARCHIVE:
            if self.parent_reference is not None or self.normalization_version is not None:
                raise ValueError("Raw archive cannot have a parent or normalization version")
        elif self.artifact_kind is HistoricalArtifactKind.NORMALIZED_DATASET:
            if (
                self.parent_reference is None
                or self.parent_reference.artifact_kind != "RAW_PROVIDER_ARCHIVE"
                or self.normalization_version is None
            ):
                raise ValueError("Normalized Dataset requires exact Raw parent and version")
        else:
            raise ValueError("Historical Data Owner supports Raw and Normalized packages")
        self.verify_identity()

    @classmethod
    def create(cls, **values: Any) -> HistoricalDataOwner:
        values["partitions"] = tuple(
            sorted(
                values["partitions"],
                key=lambda item: (
                    item.timeframe.value,
                    item.first_market_date,
                    item.symbol_bucket,
                ),
            )
        )
        values["limitations"] = tuple(
            sorted(set(values.get("limitations", ())) | set(HISTORICAL_EVIDENCE_LIMITATIONS))
        )
        values.setdefault("availability_basis", HISTORICAL_AVAILABILITY_BASIS)
        values.setdefault("data_eligibility", "EXPLORATORY")
        values.setdefault("formal_pit_status", "PIT_INCOMPLETE")
        digest = canonical_hash(_owner_payload(**values))
        return cls(
            owner_id=ArtifactId(f"historical-data-owner-{digest[7:31]}"),
            content_hash=digest,
            **values,
        )

    def semantic_payload(self) -> dict[str, Any]:
        return _owner_payload(**_owner_values(self))

    def verify_identity(self) -> None:
        for item in self.partitions:
            item.verify_identity()
        digest = canonical_hash(self.semantic_payload())
        if digest != self.content_hash:
            raise ValueError("Historical data owner hash mismatch")
        if str(self.owner_id) != f"historical-data-owner-{digest[7:31]}":
            raise ValueError("Historical data owner identity mismatch")

    @property
    def reference(self) -> ValidationArtifactReference:
        return ValidationArtifactReference(
            self.artifact_kind.value, self.owner_id, self.content_hash
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "owner_id": str(self.owner_id),
            "content_hash": self.content_hash,
            **self.semantic_payload(),
        }

    @classmethod
    def from_canonical_dict(
        cls,
        payload: Mapping[str, Any],
        *,
        partitions: tuple[HistoricalDataPartition, ...],
    ) -> HistoricalDataOwner:
        return cls(
            owner_id=ArtifactId(str(payload["owner_id"])),
            content_hash=str(payload["content_hash"]),
            artifact_kind=HistoricalArtifactKind(str(payload["artifact_kind"])),
            provider_id=str(payload["provider_id"]),
            normalization_version=_optional_string(payload["normalization_version"]),
            parent_reference=(
                ValidationArtifactReference.from_canonical_dict(payload["parent_reference"])
                if payload["parent_reference"] is not None
                else None
            ),
            created_at=parse_utc_second("created_at", payload["created_at"]),
            retrieved_at=parse_utc_second("retrieved_at", payload["retrieved_at"]),
            first_market_date=date.fromisoformat(str(payload["first_market_date"])),
            last_market_date=date.fromisoformat(str(payload["last_market_date"])),
            bucket_count=int(payload["bucket_count"]),
            partitions=partitions,
            coverage=HistoricalCorpusCoverage.from_canonical_dict(payload["coverage"]),
            availability_basis=str(payload["availability_basis"]),
            data_eligibility=str(payload["data_eligibility"]),
            formal_pit_status=str(payload["formal_pit_status"]),
            limitations=_strings(payload["limitations"], "limitations"),
            schema_version=str(payload["schema_version"]),
        )


def build_partitions(
    *,
    artifact_kind: HistoricalArtifactKind,
    records: tuple[HistoricalPartitionRecord, ...],
    bucket_count: int,
) -> tuple[HistoricalDataPartition, ...]:
    if artifact_kind is HistoricalArtifactKind.RESEARCH_MATERIALIZATION:
        raise ValueError("research materialization does not use data partitions")
    grouped: dict[tuple[Timeframe, int, int, int | None], list[HistoricalPartitionRecord]] = {}
    for item in records:
        item_date = _record_first_date(item)
        month = item_date.month if item.timeframe is not Timeframe.DAILY else None
        key = (
            item.timeframe,
            item_date.year,
            _stable_bucket(item.symbol, bucket_count),
            month,
        )
        grouped.setdefault(key, []).append(item)
    return tuple(
        HistoricalDataPartition.create(
            artifact_kind=artifact_kind,
            timeframe=timeframe,
            symbol_bucket=bucket,
            bucket_count=bucket_count,
            records=tuple(items),
        )
        for (timeframe, _year, bucket, _month), items in sorted(
            grouped.items(),
            key=lambda value: (
                value[0][0].value,
                value[0][1],
                value[0][3] or 0,
                value[0][2],
            ),
        )
    )


def _raw_values(item: HistoricalRawRequest) -> dict[str, Any]:
    return {
        "provider_id": item.provider_id,
        "product": item.product,
        "symbol": item.symbol,
        "timeframe": item.timeframe,
        "start_date": item.start_date,
        "end_date": item.end_date,
        "request_parameters": item.request_parameters,
        "requested_at": item.requested_at,
        "retrieved_at": item.retrieved_at,
        "provider_error_code": item.provider_error_code,
        "provider_error_message": item.provider_error_message,
        "fields": item.fields,
        "rows": item.rows,
        "limitations": item.limitations,
    }


def _raw_payload(**values: Any) -> dict[str, Any]:
    return {
        "schema_version": HISTORICAL_RAW_REQUEST_SCHEMA,
        "provider_id": values["provider_id"],
        "product": values["product"],
        "symbol": values["symbol"],
        "timeframe": values["timeframe"].value,
        "start_date": values["start_date"].isoformat(),
        "end_date": values["end_date"].isoformat(),
        "request_parameters": [
            {"name": name, "value": value}
            for name, value in values["request_parameters"]
        ],
        "requested_at": canonical_datetime(values["requested_at"]),
        "retrieved_at": canonical_datetime(values["retrieved_at"]),
        "provider_error_code": values["provider_error_code"],
        "provider_error_message": values["provider_error_message"],
        "fields": list(values["fields"]),
        "rows": [list(row) for row in values["rows"]],
        "limitations": list(values["limitations"]),
    }


def _bar_values(item: HistoricalNormalizedBar) -> dict[str, Any]:
    return {
        name: getattr(item, name)
        for name in (
            "symbol", "timeframe", "market_date", "event_start", "event_end",
            "retrieved_at", "open", "high", "low", "close", "volume", "amount",
            "adjustment_basis", "trading_status", "st_status", "listing_status",
            "raw_request_reference", "raw_row_number", "missing_fields", "limitations",
        )
    }


def _bar_payload(**values: Any) -> dict[str, Any]:
    return {
        "schema_version": HISTORICAL_NORMALIZED_BAR_SCHEMA,
        "symbol": values["symbol"],
        "timeframe": values["timeframe"].value,
        "market_date": values["market_date"].isoformat(),
        "event_start": canonical_datetime(values["event_start"]),
        "event_end": canonical_datetime(values["event_end"]),
        "retrieved_at": canonical_datetime(values["retrieved_at"]),
        "open": canonical_decimal(values["open"]) if values["open"] is not None else None,
        "high": canonical_decimal(values["high"]) if values["high"] is not None else None,
        "low": canonical_decimal(values["low"]) if values["low"] is not None else None,
        "close": canonical_decimal(values["close"]) if values["close"] is not None else None,
        "volume": canonical_decimal(values["volume"]),
        "amount": canonical_decimal(values["amount"]) if values["amount"] is not None else None,
        "adjustment_basis": values["adjustment_basis"],
        "trading_status": values["trading_status"].value,
        "st_status": values["st_status"],
        "listing_status": values["listing_status"].value,
        "raw_request_reference": values["raw_request_reference"].to_canonical_dict(),
        "raw_row_number": values["raw_row_number"],
        "missing_fields": list(values["missing_fields"]),
        "limitations": list(values["limitations"]),
    }


def _partition_payload(**values: Any) -> dict[str, Any]:
    return {
        "schema_version": values.get(
            "schema_version",
            HISTORICAL_PARTITION_SCHEMA,
        ),
        "artifact_kind": values["artifact_kind"].value,
        "timeframe": values["timeframe"].value,
        "first_market_date": values["first_market_date"].isoformat(),
        "last_market_date": values["last_market_date"].isoformat(),
        "symbol_bucket": values["symbol_bucket"],
        "bucket_count": values["bucket_count"],
        "row_count": values["row_count"],
        "symbol_count": values["symbol_count"],
        "records": [item.to_canonical_dict() for item in values["records"]],
    }


def _owner_values(item: HistoricalDataOwner) -> dict[str, Any]:
    return {
        name: getattr(item, name)
        for name in (
            "artifact_kind", "provider_id", "normalization_version",
            "parent_reference", "created_at", "retrieved_at", "first_market_date",
            "last_market_date", "bucket_count", "partitions", "coverage",
            "availability_basis", "data_eligibility", "formal_pit_status", "limitations",
        )
    }


def _owner_payload(**values: Any) -> dict[str, Any]:
    return {
        "schema_version": HISTORICAL_OWNER_SCHEMA,
        "artifact_kind": values["artifact_kind"].value,
        "provider_id": values["provider_id"],
        "normalization_version": values["normalization_version"],
        "parent_reference": (
            values["parent_reference"].to_canonical_dict()
            if values["parent_reference"] is not None else None
        ),
        "created_at": canonical_datetime(values["created_at"]),
        "retrieved_at": canonical_datetime(values["retrieved_at"]),
        "first_market_date": values["first_market_date"].isoformat(),
        "last_market_date": values["last_market_date"].isoformat(),
        "bucket_count": values["bucket_count"],
        "partitions": [item.reference_dict() for item in values["partitions"]],
        "coverage": values["coverage"].to_canonical_dict(),
        "availability_basis": values["availability_basis"],
        "data_eligibility": values["data_eligibility"],
        "formal_pit_status": values["formal_pit_status"],
        "limitations": list(values["limitations"]),
    }


def _record_first_date(item: HistoricalPartitionRecord) -> date:
    return item.start_date if isinstance(item, HistoricalRawRequest) else item.market_date


def _record_last_date(item: HistoricalPartitionRecord) -> date:
    return item.end_date if isinstance(item, HistoricalRawRequest) else item.market_date


def _partition_record_dates(
    records: tuple[HistoricalPartitionRecord, ...],
    *,
    schema_version: str,
) -> tuple[tuple[date, ...], tuple[date, ...]]:
    first_dates = tuple(_record_first_date(item) for item in records)
    if schema_version == HISTORICAL_PARTITION_SCHEMA_V1:
        return first_dates, first_dates
    return first_dates, tuple(_record_last_date(item) for item in records)


def _record_sort_key(item: HistoricalPartitionRecord) -> tuple[Any, ...]:
    if isinstance(item, HistoricalRawRequest):
        return (item.start_date, item.symbol, str(item.request_id))
    return (item.market_date, item.symbol, item.event_start, str(item.bar_id))


def _stable_bucket(symbol: str, bucket_count: int) -> int:
    if bucket_count <= 0:
        raise ValueError("bucket_count must be positive")
    return int(canonical_hash({"symbol": symbol})[7:23], 16) % bucket_count


def historical_symbol_bucket(symbol: str, bucket_count: int) -> int:
    """Return the stable package bucket used by the canonical partitioner."""

    require_text("symbol", symbol)
    return _stable_bucket(symbol, bucket_count)


def _partition_relative_path(item: HistoricalDataPartition) -> str:
    return _partition_path(
        artifact_kind=item.artifact_kind,
        timeframe=item.timeframe,
        first_market_date=item.first_market_date,
        last_market_date=item.last_market_date,
        symbol_bucket=item.symbol_bucket,
        schema_version=item.schema_version,
    )


def _partition_path(
    *,
    artifact_kind: HistoricalArtifactKind,
    timeframe: Timeframe,
    first_market_date: date,
    last_market_date: date,
    symbol_bucket: int,
    schema_version: str,
) -> str:
    bucket = f"{symbol_bucket:03d}"
    if artifact_kind is HistoricalArtifactKind.RAW_PROVIDER_ARCHIVE:
        prefix = f"raw/timeframe={timeframe.value.lower()}"
    else:
        prefix = "daily" if timeframe is Timeframe.DAILY else "minute_5"
    year = first_market_date.year
    if first_market_date.year != last_market_date.year:
        raise ValueError("Historical partition cannot cross a calendar year")
    if artifact_kind is HistoricalArtifactKind.RAW_PROVIDER_ARCHIVE:
        if (
            schema_version == HISTORICAL_PARTITION_SCHEMA
            and timeframe is not Timeframe.DAILY
        ):
            if first_market_date.month != last_market_date.month:
                raise ValueError("intraday Raw partition cannot cross a month")
            return (
                f"{prefix}/year={year}/month={first_market_date.month:02d}/"
                f"bucket={bucket}/part.parquet"
            )
        return f"{prefix}/year={year}/bucket={bucket}/part.parquet"
    if timeframe is Timeframe.DAILY:
        return f"{prefix}/year={year}/bucket={bucket}/part.parquet"
    if first_market_date.month != last_market_date.month:
        raise ValueError("intraday Historical partition cannot cross a month")
    return (
        f"{prefix}/year={year}/month={first_market_date.month:02d}/"
        f"bucket={bucket}/part.parquet"
    )


def _optional_string(value: object) -> str | None:
    return str(value) if value is not None else None


def _optional_decimal(value: object, label: str) -> Decimal | None:
    return parse_canonical_decimal(label, value) if value is not None else None


def _strings(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{label} must be a string array")
    return tuple(value)


def _objects(value: object, label: str) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, list) or any(not isinstance(item, Mapping) for item in value):
        raise ValueError(f"{label} must be an object array")
    return tuple(value)


def _arrays(value: object, label: str) -> tuple[object, ...]:
    if not isinstance(value, list) or any(not isinstance(item, list) for item in value):
        raise ValueError(f"{label} must be an array of arrays")
    return tuple(value)


def _count_pairs(value: object) -> tuple[tuple[str, int], ...]:
    return tuple(
        (str(item["name"]), int(item["count"]))
        for item in _objects(value, "count pairs")
    )


__all__ = [
    "HISTORICAL_AVAILABILITY_BASIS",
    "HISTORICAL_EVIDENCE_LIMITATIONS",
    "HistoricalArtifactKind",
    "HistoricalCorpusCoverage",
    "HistoricalDataOwner",
    "HistoricalDataPartition",
    "HistoricalListingStatus",
    "HistoricalNormalizedBar",
    "HistoricalRawRequest",
    "HistoricalTradingStatus",
    "build_partitions",
    "historical_symbol_bucket",
]
