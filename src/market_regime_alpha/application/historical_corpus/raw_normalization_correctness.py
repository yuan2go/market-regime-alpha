"""Independent BaoStock Raw-to-Normalized correctness kernel.

This module deliberately does not import the production normalization module.
It shares only immutable historical contracts and independently implements the
frozen BaoStock parsing/normalization semantics used for correctness evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Final, Mapping
from zoneinfo import ZoneInfo

from market_regime_alpha.application.historical_corpus.contracts import (
    HistoricalArtifactKind,
    HistoricalDataOwner,
    HistoricalListingStatus,
    HistoricalNormalizedBar,
    HistoricalRawRequest,
    HistoricalTradingStatus,
)
from market_regime_alpha.application.historical_corpus.artifacts import (
    verify_historical_package_files,
)
from market_regime_alpha.application.historical_corpus.postgres_repository import (
    PostgresHistoricalCorpusRepository,
)
from market_regime_alpha.application.historical_corpus.selective_read import (
    HistoricalReadQuery,
)
from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash, require_sha256
from market_regime_alpha.market_data.contracts import Timeframe


_PROVIDER: Final[str] = "BAOSTOCK_QUERY_HISTORY_K_DATA_PLUS"
_ADJUSTMENT_BASIS: Final[str] = "BAOSTOCK_ADJUSTFLAG_3_RAW"
_SHANGHAI: Final[ZoneInfo] = ZoneInfo("Asia/Shanghai")


class PhysicalAcquisitionProvenance(str, Enum):
    ORIGINAL_PHYSICAL_REOPENED = "ORIGINAL_PHYSICAL_REOPENED"
    REACQUIRED_EQUIVALENT_SOURCE = "REACQUIRED_EQUIVALENT_SOURCE"


class IndependentNormalizationStatus(str, Enum):
    MATCHED = "MATCHED"
    MISMATCH = "MISMATCH"
    INCONCLUSIVE = "INCONCLUSIVE"


class NormalizationDiscrepancyKind(str, Enum):
    ADJUSTMENT_SEMANTICS_MISMATCH = "ADJUSTMENT_SEMANTICS_MISMATCH"
    AMOUNT_MISMATCH = "AMOUNT_MISMATCH"
    CANONICAL_VALUE_MISMATCH = "CANONICAL_VALUE_MISMATCH"
    CONTENT_HASH_MISMATCH = "CONTENT_HASH_MISMATCH"
    EVENT_INTERVAL_MISMATCH = "EVENT_INTERVAL_MISMATCH"
    MARKET_DATE_MISMATCH = "MARKET_DATE_MISMATCH"
    MISSING_CANONICAL_OBSERVATION = "MISSING_CANONICAL_OBSERVATION"
    MISSINGNESS_MISMATCH = "MISSINGNESS_MISMATCH"
    OHLC_MISMATCH = "OHLC_MISMATCH"
    OWNER_LINEAGE_MISMATCH = "OWNER_LINEAGE_MISMATCH"
    RAW_ROW_INVALID = "RAW_ROW_INVALID"
    RETRIEVED_AT_MISMATCH = "RETRIEVED_AT_MISMATCH"
    SOURCE_IDENTITY_MISMATCH = "SOURCE_IDENTITY_MISMATCH"
    STATUS_MISMATCH = "STATUS_MISMATCH"
    SYMBOL_MISMATCH = "SYMBOL_MISMATCH"
    TIMEFRAME_MISMATCH = "TIMEFRAME_MISMATCH"
    UNEXPECTED_CANONICAL_OBSERVATION = "UNEXPECTED_CANONICAL_OBSERVATION"
    VOLUME_MISMATCH = "VOLUME_MISMATCH"


@dataclass(frozen=True, slots=True)
class NormalizationDiscrepancy:
    kind: NormalizationDiscrepancyKind
    observation_key: str
    independent_value: str | None
    canonical_value: str | None

    def to_canonical_dict(self) -> dict[str, str | None]:
        return {
            "kind": self.kind.value,
            "observation_key": self.observation_key,
            "independent_value": self.independent_value,
            "canonical_value": self.canonical_value,
        }


@dataclass(frozen=True, slots=True)
class IndependentNormalizationVerification:
    verification_id: ArtifactId
    verification_hash: str
    provenance: PhysicalAcquisitionProvenance
    raw_owner_reference: ValidationArtifactReference
    normalized_owner_reference: ValidationArtifactReference
    comparison_count: int
    independent_value_hash: str | None
    canonical_value_hash: str | None
    status: IndependentNormalizationStatus
    discrepancies: tuple[NormalizationDiscrepancy, ...]
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        require_sha256("verification_hash", self.verification_hash)
        if self.raw_owner_reference.artifact_kind != "RAW_PROVIDER_ARCHIVE":
            raise ValueError("independent normalization requires Raw owner")
        if self.normalized_owner_reference.artifact_kind != "NORMALIZED_DATASET":
            raise ValueError("independent normalization requires Normalized owner")
        if self.comparison_count < 0:
            raise ValueError("comparison_count must be non-negative")
        for label, value in (
            ("independent_value_hash", self.independent_value_hash),
            ("canonical_value_hash", self.canonical_value_hash),
        ):
            if value is not None:
                require_sha256(label, value)
        if self.discrepancies != tuple(
            sorted(
                set(self.discrepancies),
                key=lambda item: (
                    item.kind.value,
                    item.observation_key,
                    item.independent_value or "",
                    item.canonical_value or "",
                ),
            )
        ):
            raise ValueError("normalization discrepancies must be unique and sorted")
        if self.reason_codes != tuple(sorted(set(self.reason_codes))):
            raise ValueError("normalization reason codes must be unique and sorted")
        if self.status is IndependentNormalizationStatus.MATCHED and (
            self.discrepancies
            or self.comparison_count == 0
            or self.independent_value_hash != self.canonical_value_hash
        ):
            raise ValueError("matched normalization verification is inconsistent")
        if self.status is IndependentNormalizationStatus.MISMATCH and not self.discrepancies:
            raise ValueError("mismatched normalization verification requires discrepancies")
        if self.status is IndependentNormalizationStatus.INCONCLUSIVE and (
            self.comparison_count != 0 or not self.reason_codes
        ):
            raise ValueError("inconclusive normalization verification is inconsistent")
        digest = canonical_hash(self.identity_payload())
        if digest != self.verification_hash or self.verification_id != ArtifactId(
            f"independent-normalization-verification:{digest[7:]}"
        ):
            raise ValueError("independent normalization verification identity mismatch")

    @property
    def original_physical_reopened(self) -> bool:
        return self.provenance is PhysicalAcquisitionProvenance.ORIGINAL_PHYSICAL_REOPENED

    @classmethod
    def create(
        cls,
        *,
        provenance: PhysicalAcquisitionProvenance,
        raw_owner_reference: ValidationArtifactReference,
        normalized_owner_reference: ValidationArtifactReference,
        comparison_count: int,
        independent_value_hash: str | None,
        canonical_value_hash: str | None,
        status: IndependentNormalizationStatus,
        discrepancies: tuple[NormalizationDiscrepancy, ...],
        reason_codes: tuple[str, ...],
    ) -> IndependentNormalizationVerification:
        ordered_discrepancies = tuple(
            sorted(
                set(discrepancies),
                key=lambda item: (
                    item.kind.value,
                    item.observation_key,
                    item.independent_value or "",
                    item.canonical_value or "",
                ),
            )
        )
        ordered_reasons = tuple(sorted(set(reason_codes)))
        payload = {
            "provenance": provenance.value,
            "raw_owner_reference": raw_owner_reference.to_canonical_dict(),
            "normalized_owner_reference": normalized_owner_reference.to_canonical_dict(),
            "comparison_count": comparison_count,
            "independent_value_hash": independent_value_hash,
            "canonical_value_hash": canonical_value_hash,
            "status": status.value,
            "discrepancies": [
                item.to_canonical_dict() for item in ordered_discrepancies
            ],
            "reason_codes": list(ordered_reasons),
        }
        digest = canonical_hash(payload)
        return cls(
            verification_id=ArtifactId(
                f"independent-normalization-verification:{digest[7:]}"
            ),
            verification_hash=digest,
            provenance=provenance,
            raw_owner_reference=raw_owner_reference,
            normalized_owner_reference=normalized_owner_reference,
            comparison_count=comparison_count,
            independent_value_hash=independent_value_hash,
            canonical_value_hash=canonical_value_hash,
            status=status,
            discrepancies=ordered_discrepancies,
            reason_codes=ordered_reasons,
        )

    @property
    def reference(self) -> ValidationArtifactReference:
        return ValidationArtifactReference(
            "INDEPENDENT_NORMALIZATION_VERIFICATION",
            self.verification_id,
            self.verification_hash,
        )

    def identity_payload(self) -> dict[str, object]:
        return {
            "provenance": self.provenance.value,
            "raw_owner_reference": self.raw_owner_reference.to_canonical_dict(),
            "normalized_owner_reference": self.normalized_owner_reference.to_canonical_dict(),
            "comparison_count": self.comparison_count,
            "independent_value_hash": self.independent_value_hash,
            "canonical_value_hash": self.canonical_value_hash,
            "status": self.status.value,
            "discrepancies": [item.to_canonical_dict() for item in self.discrepancies],
            "reason_codes": list(self.reason_codes),
        }

    def to_canonical_dict(self) -> dict[str, object]:
        return {
            "verification_id": str(self.verification_id),
            "verification_hash": self.verification_hash,
            **self.identity_payload(),
        }


class _IndependentRowError(ValueError):
    def __init__(self, kind: NormalizationDiscrepancyKind, reason: str) -> None:
        self.kind = kind
        self.reason = reason
        super().__init__(reason)


def verify_independent_baostock_normalization(
    *,
    raw_owner: HistoricalDataOwner,
    canonical_normalized_owner: HistoricalDataOwner,
    provenance: PhysicalAcquisitionProvenance,
) -> IndependentNormalizationVerification:
    """Independently normalize Raw records and compare the canonical owner."""

    raw_owner.verify_identity()
    canonical_normalized_owner.verify_identity()
    _require_owner_contract(raw_owner, canonical_normalized_owner)
    discrepancies: list[NormalizationDiscrepancy] = []
    independent: list[HistoricalNormalizedBar] = []
    raw_row_count = 0
    for partition in raw_owner.partitions:
        for record in partition.records:
            if not isinstance(record, HistoricalRawRequest):
                raise ValueError("Raw owner contains non-Raw record")
            if not record.succeeded:
                continue
            for row_number, row in enumerate(record.rows, 1):
                raw_row_count += 1
                try:
                    independent.append(
                        _independently_normalize_row(record, row, row_number)
                    )
                except _IndependentRowError as exc:
                    discrepancies.append(
                        NormalizationDiscrepancy(
                            exc.kind,
                            f"{record.request_id}:{row_number}",
                            exc.reason,
                            None,
                        )
                    )
    canonical = _normalized_bars(canonical_normalized_owner)
    if raw_row_count == 0:
        return _verification(
            provenance=provenance,
            raw_owner_reference=raw_owner.reference,
            normalized_owner_reference=canonical_normalized_owner.reference,
            comparison_count=0,
            independent_value_hash=None,
            canonical_value_hash=(
                canonical_hash({"bars": [_value_payload(item) for item in canonical]})
                if canonical
                else None
            ),
            status=IndependentNormalizationStatus.INCONCLUSIVE,
            discrepancies=(),
            reason_codes=("RAW_NORMALIZATION_POPULATION_EMPTY",),
        )
    independent_by_key = {_observation_key(item): item for item in independent}
    canonical_by_key = {_observation_key(item): item for item in canonical}
    if len(independent_by_key) != len(independent):
        raise ValueError("independent normalization produced duplicate observations")
    if len(canonical_by_key) != len(canonical):
        raise ValueError("canonical Normalized owner contains duplicate observations")
    for key in sorted(set(independent_by_key) | set(canonical_by_key)):
        independently_normalized = independent_by_key.get(key)
        canonical_bar = canonical_by_key.get(key)
        rendered_key = _render_key(key)
        if independently_normalized is None:
            discrepancies.append(
                NormalizationDiscrepancy(
                    NormalizationDiscrepancyKind.UNEXPECTED_CANONICAL_OBSERVATION,
                    rendered_key,
                    None,
                    str(canonical_bar.bar_id) if canonical_bar is not None else None,
                )
            )
            continue
        if canonical_bar is None:
            discrepancies.append(
                NormalizationDiscrepancy(
                    NormalizationDiscrepancyKind.MISSING_CANONICAL_OBSERVATION,
                    rendered_key,
                    str(independently_normalized.bar_id),
                    None,
                )
            )
            continue
        discrepancies.extend(
            _compare_bars(independently_normalized, canonical_bar, rendered_key)
        )
    ordered_discrepancies = tuple(
        sorted(
            set(discrepancies),
            key=lambda item: (
                item.kind.value,
                item.observation_key,
                item.independent_value or "",
                item.canonical_value or "",
            ),
        )
    )
    independent_value_hash = canonical_hash(
        {"bars": [_value_payload(item) for item in sorted(independent, key=_observation_key)]}
    )
    canonical_value_hash = canonical_hash(
        {"bars": [_value_payload(item) for item in sorted(canonical, key=_observation_key)]}
    )
    status = (
        IndependentNormalizationStatus.MATCHED
        if not ordered_discrepancies and independent_value_hash == canonical_value_hash
        else IndependentNormalizationStatus.MISMATCH
    )
    reason_codes = (
        ("RAW_NORMALIZATION_MATCHED",)
        if status is IndependentNormalizationStatus.MATCHED
        else tuple(
            sorted(
                {
                    f"RAW_NORMALIZATION_{item.kind.value}"
                    for item in ordered_discrepancies
                }
            )
        )
    )
    return _verification(
        provenance=provenance,
        raw_owner_reference=raw_owner.reference,
        normalized_owner_reference=canonical_normalized_owner.reference,
        comparison_count=len(independent),
        independent_value_hash=independent_value_hash,
        canonical_value_hash=canonical_value_hash,
        status=status,
        discrepancies=ordered_discrepancies,
        reason_codes=reason_codes,
    )


def verify_independent_baostock_package_normalization(
    *,
    corpus: PostgresHistoricalCorpusRepository,
    raw_owner_reference: ValidationArtifactReference,
    normalized_owner_reference: ValidationArtifactReference,
    provenance: PhysicalAcquisitionProvenance,
) -> IndependentNormalizationVerification:
    """Compare exact physical owners in bounded provider-period slices.

    Every package file is checksum-verified once. Raw provider rows are then
    independently normalized by the same pure kernel as the in-memory checker,
    while PostgreSQL-resolved Parquet slices keep the 1.95M-row campaign within
    a bounded memory envelope.
    """

    raw_index = corpus.open_index(raw_owner_reference)
    normalized_index = corpus.open_index(normalized_owner_reference)
    verify_historical_package_files(raw_index)
    verify_historical_package_files(normalized_index)
    if (
        raw_index.artifact_kind is not HistoricalArtifactKind.RAW_PROVIDER_ARCHIVE
        or normalized_index.artifact_kind
        is not HistoricalArtifactKind.NORMALIZED_DATASET
        or raw_index.provider_id != _PROVIDER
        or normalized_index.provider_id != _PROVIDER
        or normalized_index.parent_reference != raw_index.reference
    ):
        raise ValueError("independent package correctness owner contract drifted")

    periods = tuple(
        sorted(
            {
                (
                    partition.timeframe,
                    partition.first_market_date,
                    partition.last_market_date,
                )
                for partition in raw_index.partitions
            },
            key=lambda item: (item[0].value, item[1], item[2]),
        )
    )
    discrepancies: list[NormalizationDiscrepancy] = []
    hash_chunks: list[dict[str, object]] = []
    raw_row_count = 0
    independent_count = 0
    canonical_count = 0
    for timeframe, first_market_date, last_market_date in periods:
        raw_slice = corpus.read(
            HistoricalReadQuery.create(
                reference=raw_index.reference,
                timeframes=(timeframe,),
                first_market_date=first_market_date,
                last_market_date=last_market_date,
                symbols=None,
                max_rows=10_000,
                batch_size=8_192,
            )
        )
        normalized_slice = corpus.read(
            HistoricalReadQuery.create(
                reference=normalized_index.reference,
                timeframes=(timeframe,),
                first_market_date=first_market_date,
                last_market_date=last_market_date,
                symbols=None,
                max_rows=500_000,
                batch_size=8_192,
            )
        )
        independent: list[HistoricalNormalizedBar] = []
        for record in raw_slice.records:
            if not isinstance(record, HistoricalRawRequest):
                raise ValueError("Raw package slice contains non-Raw record")
            if not record.succeeded:
                continue
            for row_number, row in enumerate(record.rows, 1):
                raw_row_count += 1
                try:
                    independent.append(
                        _independently_normalize_row(record, row, row_number)
                    )
                except _IndependentRowError as exc:
                    discrepancies.append(
                        NormalizationDiscrepancy(
                            exc.kind,
                            f"{record.request_id}:{row_number}",
                            exc.reason,
                            None,
                        )
                    )
        canonical = tuple(
            item
            for item in normalized_slice.records
            if isinstance(item, HistoricalNormalizedBar)
        )
        if len(canonical) != len(normalized_slice.records):
            raise ValueError("Normalized package slice contains non-Normalized record")
        independent_by_key = {_observation_key(item): item for item in independent}
        canonical_by_key = {_observation_key(item): item for item in canonical}
        if len(independent_by_key) != len(independent):
            raise ValueError("independent normalization produced duplicate observations")
        if len(canonical_by_key) != len(canonical):
            raise ValueError("canonical Normalized package contains duplicate observations")
        for key in sorted(set(independent_by_key) | set(canonical_by_key)):
            independently_normalized = independent_by_key.get(key)
            canonical_bar = canonical_by_key.get(key)
            rendered_key = _render_key(key)
            if independently_normalized is None:
                discrepancies.append(
                    NormalizationDiscrepancy(
                        NormalizationDiscrepancyKind.UNEXPECTED_CANONICAL_OBSERVATION,
                        rendered_key,
                        None,
                        (
                            str(canonical_bar.bar_id)
                            if canonical_bar is not None
                            else None
                        ),
                    )
                )
            elif canonical_bar is None:
                discrepancies.append(
                    NormalizationDiscrepancy(
                        NormalizationDiscrepancyKind.MISSING_CANONICAL_OBSERVATION,
                        rendered_key,
                        str(independently_normalized.bar_id),
                        None,
                    )
                )
            else:
                discrepancies.extend(
                    _compare_bars(independently_normalized, canonical_bar, rendered_key)
                )
        ordered_independent = sorted(independent, key=_observation_key)
        ordered_canonical = sorted(canonical, key=_observation_key)
        independent_chunk_hash = canonical_hash(
            {"bars": [_value_payload(item) for item in ordered_independent]}
        )
        canonical_chunk_hash = canonical_hash(
            {"bars": [_value_payload(item) for item in ordered_canonical]}
        )
        hash_chunks.append(
            {
                "timeframe": timeframe.value,
                "first_market_date": first_market_date.isoformat(),
                "last_market_date": last_market_date.isoformat(),
                "independent_count": len(independent),
                "canonical_count": len(canonical),
                "independent_hash": independent_chunk_hash,
                "canonical_hash": canonical_chunk_hash,
            }
        )
        independent_count += len(independent)
        canonical_count += len(canonical)

    if raw_row_count == 0:
        return _verification(
            provenance=provenance,
            raw_owner_reference=raw_index.reference,
            normalized_owner_reference=normalized_index.reference,
            comparison_count=0,
            independent_value_hash=None,
            canonical_value_hash=None,
            status=IndependentNormalizationStatus.INCONCLUSIVE,
            discrepancies=(),
            reason_codes=("RAW_NORMALIZATION_POPULATION_EMPTY",),
        )
    if raw_row_count != raw_index.coverage.source_row_count:
        discrepancies.append(
            NormalizationDiscrepancy(
                NormalizationDiscrepancyKind.RAW_ROW_INVALID,
                "RAW_OWNER_COVERAGE",
                str(raw_row_count),
                str(raw_index.coverage.source_row_count),
            )
        )
    if canonical_count != normalized_index.coverage.normalized_row_count:
        discrepancies.append(
            NormalizationDiscrepancy(
                NormalizationDiscrepancyKind.CANONICAL_VALUE_MISMATCH,
                "NORMALIZED_OWNER_COVERAGE",
                str(canonical_count),
                str(normalized_index.coverage.normalized_row_count),
            )
        )
    independent_value_hash = canonical_hash(
        {
            "schema_version": "independent-normalization-chunk-manifest/v1",
            "chunks": [
                {
                    **chunk,
                    "value_hash": chunk["independent_hash"],
                }
                for chunk in hash_chunks
            ],
        }
    )
    canonical_value_hash = canonical_hash(
        {
            "schema_version": "independent-normalization-chunk-manifest/v1",
            "chunks": [
                {
                    **chunk,
                    "value_hash": chunk["canonical_hash"],
                }
                for chunk in hash_chunks
            ],
        }
    )
    ordered_discrepancies = tuple(
        sorted(
            set(discrepancies),
            key=lambda item: (
                item.kind.value,
                item.observation_key,
                item.independent_value or "",
                item.canonical_value or "",
            ),
        )
    )
    status = (
        IndependentNormalizationStatus.MATCHED
        if not ordered_discrepancies
        and independent_count == canonical_count
        and all(
            item["independent_hash"] == item["canonical_hash"]
            for item in hash_chunks
        )
        else IndependentNormalizationStatus.MISMATCH
    )
    return _verification(
        provenance=provenance,
        raw_owner_reference=raw_index.reference,
        normalized_owner_reference=normalized_index.reference,
        comparison_count=independent_count,
        independent_value_hash=independent_value_hash,
        canonical_value_hash=canonical_value_hash,
        status=status,
        discrepancies=ordered_discrepancies,
        reason_codes=(
            ("RAW_NORMALIZATION_MATCHED",)
            if status is IndependentNormalizationStatus.MATCHED
            else tuple(
                sorted(
                    {
                        f"RAW_NORMALIZATION_{item.kind.value}"
                        for item in ordered_discrepancies
                    }
                )
            )
        ),
    )


def _require_owner_contract(
    raw_owner: HistoricalDataOwner,
    normalized_owner: HistoricalDataOwner,
) -> None:
    if (
        raw_owner.artifact_kind is not HistoricalArtifactKind.RAW_PROVIDER_ARCHIVE
        or normalized_owner.artifact_kind is not HistoricalArtifactKind.NORMALIZED_DATASET
    ):
        raise ValueError("independent correctness requires Raw and Normalized owners")
    if raw_owner.provider_id != _PROVIDER or normalized_owner.provider_id != _PROVIDER:
        raise ValueError("independent correctness requires frozen BaoStock provider")
    if normalized_owner.parent_reference != raw_owner.reference:
        raise ValueError("Normalized owner does not bind the supplied Raw owner")


def _independently_normalize_row(
    request: HistoricalRawRequest,
    raw_row: tuple[str, ...],
    row_number: int,
) -> HistoricalNormalizedBar:
    row = dict(zip(request.fields, raw_row, strict=True))
    requested_adjustment = dict(request.request_parameters).get("adjustflag")
    if requested_adjustment != "3" or row.get("adjustflag") != "3":
        raise _IndependentRowError(
            NormalizationDiscrepancyKind.ADJUSTMENT_SEMANTICS_MISMATCH,
            "BAOSTOCK_ADJUSTFLAG_3_REQUIRED",
        )
    raw_code = row.get("code")
    if raw_code is not None and raw_code != _baostock_code(request.symbol):
        raise _IndependentRowError(
            NormalizationDiscrepancyKind.SYMBOL_MISMATCH,
            "RAW_SYMBOL_DIFFERS_FROM_REQUEST",
        )
    market_date = _date_value(row.get("date"))
    if not request.start_date <= market_date <= request.end_date:
        raise _IndependentRowError(
            NormalizationDiscrepancyKind.MARKET_DATE_MISMATCH,
            "EVENT_OUTSIDE_REQUEST_RANGE",
        )
    event_start, event_end = _event_interval(request.timeframe, market_date, row)
    trading_status = _status(row.get("tradestatus"))
    prices = _ohlc(row, trading_status)
    missing_fields: set[str] = set()
    if prices[0] is None:
        missing_fields.add("OHLC")
    volume = _decimal(row.get("volume"), "VOLUME", allow_blank=True)
    if volume is None:
        volume = Decimal("0")
        missing_fields.add("VOLUME")
    amount = _decimal(row.get("amount"), "AMOUNT", allow_blank=True)
    if amount is None:
        missing_fields.add("AMOUNT")
    raw_st = row.get("isST")
    st_status = None if raw_st in {None, ""} else raw_st == "1"
    if st_status is None:
        missing_fields.add("ST_STATUS")
    missing_fields.add("LISTING_STATUS")
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
        adjustment_basis=_ADJUSTMENT_BASIS,
        trading_status=trading_status,
        st_status=st_status,
        listing_status=HistoricalListingStatus.UNKNOWN,
        raw_request_reference=ValidationArtifactReference(
            "RAW_PROVIDER_REQUEST", request.request_id, request.content_hash
        ),
        raw_row_number=row_number,
        missing_fields=tuple(sorted(missing_fields)),
        limitations=tuple(sorted(limitations)),
    )


def _event_interval(
    timeframe: Timeframe,
    market_date: date,
    row: Mapping[str, str],
) -> tuple[datetime, datetime]:
    if timeframe is Timeframe.DAILY:
        start = datetime.combine(market_date, time(9, 30), _SHANGHAI)
        end = datetime.combine(market_date, time(15), _SHANGHAI)
    elif timeframe is Timeframe.MINUTE_5:
        raw_time = row.get("time")
        if not raw_time:
            raise _IndependentRowError(
                NormalizationDiscrepancyKind.EVENT_INTERVAL_MISMATCH,
                "MINUTE_TIME_MISSING",
            )
        try:
            end = datetime.strptime(raw_time, "%Y%m%d%H%M%S%f").replace(
                tzinfo=_SHANGHAI
            )
        except ValueError as exc:
            raise _IndependentRowError(
                NormalizationDiscrepancyKind.EVENT_INTERVAL_MISMATCH,
                "MINUTE_TIME_INVALID",
            ) from exc
        if end.date() != market_date:
            raise _IndependentRowError(
                NormalizationDiscrepancyKind.EVENT_INTERVAL_MISMATCH,
                "MINUTE_DATE_MISMATCH",
            )
        start = end - timedelta(minutes=5)
    else:
        raise _IndependentRowError(
            NormalizationDiscrepancyKind.TIMEFRAME_MISMATCH,
            "UNSUPPORTED_TIMEFRAME",
        )
    return (
        start.astimezone(UTC).replace(microsecond=0),
        end.astimezone(UTC).replace(microsecond=0),
    )


def _date_value(value: str | None) -> date:
    if not value:
        raise _IndependentRowError(
            NormalizationDiscrepancyKind.MARKET_DATE_MISMATCH,
            "DATE_MISSING",
        )
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise _IndependentRowError(
            NormalizationDiscrepancyKind.MARKET_DATE_MISMATCH,
            "DATE_INVALID",
        ) from exc


def _ohlc(
    row: Mapping[str, str],
    status: HistoricalTradingStatus,
) -> tuple[Decimal | None, Decimal | None, Decimal | None, Decimal | None]:
    values = tuple(
        _decimal(row.get(field), field.upper(), allow_blank=True)
        for field in ("open", "high", "low", "close")
    )
    if all(value is None or value == 0 for value in values):
        if status is HistoricalTradingStatus.TRADING:
            raise _IndependentRowError(
                NormalizationDiscrepancyKind.OHLC_MISMATCH,
                "TRADING_ROW_OHLC_MISSING",
            )
        return (None, None, None, None)
    if any(value is None or value <= 0 for value in values):
        raise _IndependentRowError(
            NormalizationDiscrepancyKind.OHLC_MISMATCH,
            "OHLC_PARTIAL_OR_NON_POSITIVE",
        )
    return (values[0], values[1], values[2], values[3])


def _decimal(value: str | None, label: str, *, allow_blank: bool) -> Decimal | None:
    if value is None or value == "":
        if allow_blank:
            return None
        raise _IndependentRowError(
            NormalizationDiscrepancyKind.CANONICAL_VALUE_MISMATCH,
            f"{label}_MISSING",
        )
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise _IndependentRowError(
            NormalizationDiscrepancyKind.CANONICAL_VALUE_MISMATCH,
            f"{label}_INVALID",
        ) from exc
    if not parsed.is_finite() or parsed < 0:
        raise _IndependentRowError(
            NormalizationDiscrepancyKind.CANONICAL_VALUE_MISMATCH,
            f"{label}_INVALID",
        )
    return parsed


def _status(value: str | None) -> HistoricalTradingStatus:
    if value == "1":
        return HistoricalTradingStatus.TRADING
    if value == "0":
        return HistoricalTradingStatus.SUSPENDED
    return HistoricalTradingStatus.UNKNOWN


def _baostock_code(symbol: str) -> str:
    code, exchange = symbol.split(".", 1)
    return f"{exchange.lower()}.{code}"


def _normalized_bars(owner: HistoricalDataOwner) -> tuple[HistoricalNormalizedBar, ...]:
    result = tuple(
        record
        for partition in owner.partitions
        for record in partition.records
        if isinstance(record, HistoricalNormalizedBar)
    )
    if sum(len(partition.records) for partition in owner.partitions) != len(result):
        raise ValueError("Normalized owner contains non-Normalized record")
    return result


def _observation_key(bar: HistoricalNormalizedBar) -> tuple[date, str, str, datetime]:
    return (bar.market_date, bar.symbol, bar.timeframe.value, bar.event_start)


def _render_key(key: tuple[date, str, str, datetime]) -> str:
    return "|".join((key[0].isoformat(), key[1], key[2], key[3].isoformat()))


def _compare_bars(
    independent: HistoricalNormalizedBar,
    canonical: HistoricalNormalizedBar,
    key: str,
) -> tuple[NormalizationDiscrepancy, ...]:
    result: list[NormalizationDiscrepancy] = []

    def compare(
        kind: NormalizationDiscrepancyKind,
        left: object,
        right: object,
    ) -> None:
        if left != right:
            result.append(
                NormalizationDiscrepancy(kind, key, str(left), str(right))
            )

    compare(
        NormalizationDiscrepancyKind.EVENT_INTERVAL_MISMATCH,
        (independent.event_start, independent.event_end),
        (canonical.event_start, canonical.event_end),
    )
    compare(
        NormalizationDiscrepancyKind.MARKET_DATE_MISMATCH,
        independent.market_date,
        canonical.market_date,
    )
    compare(
        NormalizationDiscrepancyKind.RETRIEVED_AT_MISMATCH,
        independent.retrieved_at,
        canonical.retrieved_at,
    )
    compare(
        NormalizationDiscrepancyKind.OHLC_MISMATCH,
        (independent.open, independent.high, independent.low, independent.close),
        (canonical.open, canonical.high, canonical.low, canonical.close),
    )
    compare(
        NormalizationDiscrepancyKind.VOLUME_MISMATCH,
        independent.volume,
        canonical.volume,
    )
    compare(
        NormalizationDiscrepancyKind.AMOUNT_MISMATCH,
        independent.amount,
        canonical.amount,
    )
    compare(
        NormalizationDiscrepancyKind.ADJUSTMENT_SEMANTICS_MISMATCH,
        independent.adjustment_basis,
        canonical.adjustment_basis,
    )
    compare(
        NormalizationDiscrepancyKind.STATUS_MISMATCH,
        (
            independent.trading_status,
            independent.st_status,
            independent.listing_status,
        ),
        (canonical.trading_status, canonical.st_status, canonical.listing_status),
    )
    compare(
        NormalizationDiscrepancyKind.SOURCE_IDENTITY_MISMATCH,
        (independent.raw_request_reference, independent.raw_row_number),
        (canonical.raw_request_reference, canonical.raw_row_number),
    )
    compare(
        NormalizationDiscrepancyKind.MISSINGNESS_MISMATCH,
        (independent.missing_fields, independent.limitations),
        (canonical.missing_fields, canonical.limitations),
    )
    if independent.content_hash != canonical.content_hash:
        result.append(
            NormalizationDiscrepancy(
                NormalizationDiscrepancyKind.CONTENT_HASH_MISMATCH,
                key,
                independent.content_hash,
                canonical.content_hash,
            )
        )
    return tuple(result)


def _value_payload(bar: HistoricalNormalizedBar) -> dict[str, object]:
    return bar.to_canonical_dict()


def _verification(
    *,
    provenance: PhysicalAcquisitionProvenance,
    raw_owner_reference: ValidationArtifactReference,
    normalized_owner_reference: ValidationArtifactReference,
    comparison_count: int,
    independent_value_hash: str | None,
    canonical_value_hash: str | None,
    status: IndependentNormalizationStatus,
    discrepancies: tuple[NormalizationDiscrepancy, ...],
    reason_codes: tuple[str, ...],
) -> IndependentNormalizationVerification:
    return IndependentNormalizationVerification.create(
        provenance=provenance,
        raw_owner_reference=raw_owner_reference,
        normalized_owner_reference=normalized_owner_reference,
        comparison_count=comparison_count,
        independent_value_hash=independent_value_hash,
        canonical_value_hash=canonical_value_hash,
        status=status,
        discrepancies=discrepancies,
        reason_codes=reason_codes,
    )


__all__ = [
    "IndependentNormalizationStatus",
    "IndependentNormalizationVerification",
    "NormalizationDiscrepancy",
    "NormalizationDiscrepancyKind",
    "PhysicalAcquisitionProvenance",
    "verify_independent_baostock_normalization",
    "verify_independent_baostock_package_normalization",
]
