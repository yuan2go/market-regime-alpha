from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from market_regime_alpha.application.historical_corpus.contracts import (
    HistoricalArtifactKind,
    HistoricalCorpusCoverage,
    HistoricalDataOwner,
    HistoricalNormalizedBar,
    HistoricalRawRequest,
    build_partitions,
)
from market_regime_alpha.application.historical_corpus.normalization import (
    normalize_baostock_archive,
)
from market_regime_alpha.application.historical_corpus.raw_normalization_correctness import (
    IndependentNormalizationStatus,
    NormalizationDiscrepancyKind,
    PhysicalAcquisitionProvenance,
    verify_independent_baostock_normalization,
)
from market_regime_alpha.market_data.contracts import Timeframe


RETRIEVED_AT = datetime(2026, 8, 21, 8, tzinfo=UTC)


def test_independent_raw_normalization_matches_canonical_owner() -> None:
    raw = _raw_owner()
    canonical = normalize_baostock_archive(raw)

    verification = verify_independent_baostock_normalization(
        raw_owner=raw,
        canonical_normalized_owner=canonical,
        provenance=PhysicalAcquisitionProvenance.REACQUIRED_EQUIVALENT_SOURCE,
    )

    assert verification.status is IndependentNormalizationStatus.MATCHED
    assert verification.provenance is PhysicalAcquisitionProvenance.REACQUIRED_EQUIVALENT_SOURCE
    assert verification.comparison_count == 2
    assert verification.discrepancies == ()
    assert verification.raw_owner_reference == raw.reference
    assert verification.normalized_owner_reference == canonical.reference
    assert verification.original_physical_reopened is False


def test_physical_provenance_is_derived_from_raw_owner_chronology() -> None:
    raw = _raw_owner()
    canonical = normalize_baostock_archive(raw)

    with pytest.raises(
        ValueError,
        match="declared physical acquisition provenance disagrees",
    ):
        verify_independent_baostock_normalization(
            raw_owner=raw,
            canonical_normalized_owner=canonical,
            provenance=PhysicalAcquisitionProvenance.ORIGINAL_PHYSICAL_REOPENED,
        )


def test_independent_normalization_classifies_amount_and_hash_mismatch() -> None:
    raw = _raw_owner()
    canonical = normalize_baostock_archive(raw)
    records = _bars(canonical)
    first = records[0]
    assert first.amount is not None
    changed = HistoricalNormalizedBar.create(
        symbol=first.symbol,
        timeframe=first.timeframe,
        market_date=first.market_date,
        event_start=first.event_start,
        event_end=first.event_end,
        retrieved_at=first.retrieved_at,
        open=first.open,
        high=first.high,
        low=first.low,
        close=first.close,
        volume=first.volume,
        amount=first.amount + Decimal("1"),
        adjustment_basis=first.adjustment_basis,
        trading_status=first.trading_status,
        st_status=first.st_status,
        listing_status=first.listing_status,
        raw_request_reference=first.raw_request_reference,
        raw_row_number=first.raw_row_number,
        missing_fields=first.missing_fields,
        limitations=first.limitations,
    )
    mismatched = _normalized_owner(
        raw,
        canonical,
        (changed, *records[1:]),
    )

    verification = verify_independent_baostock_normalization(
        raw_owner=raw,
        canonical_normalized_owner=mismatched,
        provenance=PhysicalAcquisitionProvenance.REACQUIRED_EQUIVALENT_SOURCE,
    )

    assert verification.status is IndependentNormalizationStatus.MISMATCH
    assert tuple(item.kind for item in verification.discrepancies) == (
        NormalizationDiscrepancyKind.AMOUNT_MISMATCH,
        NormalizationDiscrepancyKind.CONTENT_HASH_MISMATCH,
    )


def test_adjustment_semantics_fail_closed_even_when_production_would_normalize() -> None:
    raw = _raw_owner(adjustflag="2")
    canonical = normalize_baostock_archive(raw)

    verification = verify_independent_baostock_normalization(
        raw_owner=raw,
        canonical_normalized_owner=canonical,
        provenance=PhysicalAcquisitionProvenance.REACQUIRED_EQUIVALENT_SOURCE,
    )

    assert verification.status is IndependentNormalizationStatus.MISMATCH
    assert tuple(item.kind for item in verification.discrepancies) == (
        NormalizationDiscrepancyKind.ADJUSTMENT_SEMANTICS_MISMATCH,
        NormalizationDiscrepancyKind.ADJUSTMENT_SEMANTICS_MISMATCH,
        NormalizationDiscrepancyKind.UNEXPECTED_CANONICAL_OBSERVATION,
        NormalizationDiscrepancyKind.UNEXPECTED_CANONICAL_OBSERVATION,
    )


def test_empty_reacquired_source_is_inconclusive_not_supported() -> None:
    raw = _raw_owner(rows=())
    # A canonical owner cannot be empty, so use a valid owner to prove the
    # independent side never upgrades missing Raw observations.
    template = normalize_baostock_archive(_raw_owner())
    canonical = _normalized_owner(raw, template, _bars(template))

    verification = verify_independent_baostock_normalization(
        raw_owner=raw,
        canonical_normalized_owner=canonical,
        provenance=PhysicalAcquisitionProvenance.REACQUIRED_EQUIVALENT_SOURCE,
    )

    assert verification.status is IndependentNormalizationStatus.INCONCLUSIVE
    assert verification.comparison_count == 0
    assert verification.reason_codes == ("RAW_NORMALIZATION_POPULATION_EMPTY",)


def _raw_owner(
    *,
    adjustflag: str = "3",
    rows: tuple[tuple[str, ...], ...] | None = None,
) -> HistoricalDataOwner:
    fields = (
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
    values = rows if rows is not None else (
        ("2025-01-02", "sh.600000", "10", "11", "9", "10.5", "100", "1000", adjustflag, "1", "0"),
        ("2025-01-03", "sh.600000", "10.5", "12", "10", "11", "120", "1300", adjustflag, "1", "0"),
    )
    request = HistoricalRawRequest.create(
        provider_id="BAOSTOCK_QUERY_HISTORY_K_DATA_PLUS",
        product="query_history_k_data_plus",
        symbol="600000.SH",
        timeframe=Timeframe.DAILY,
        start_date=date(2025, 1, 1),
        end_date=date(2025, 1, 3),
        request_parameters=(
            ("adjustflag", "3"),
            ("frequency", "d"),
        ),
        requested_at=RETRIEVED_AT,
        retrieved_at=RETRIEVED_AT,
        fields=fields,
        rows=values,
        limitations=("PUBLIC_DATA_EXPLORATORY_ONLY",),
    )
    return HistoricalDataOwner.create(
        artifact_kind=HistoricalArtifactKind.RAW_PROVIDER_ARCHIVE,
        provider_id=request.provider_id,
        normalization_version=None,
        parent_reference=None,
        created_at=RETRIEVED_AT,
        retrieved_at=RETRIEVED_AT,
        first_market_date=request.start_date,
        last_market_date=request.end_date,
        bucket_count=4,
        partitions=build_partitions(
            artifact_kind=HistoricalArtifactKind.RAW_PROVIDER_ARCHIVE,
            records=(request,),
            bucket_count=4,
        ),
        coverage=HistoricalCorpusCoverage(
            expected_symbols=("600000.SH",),
            observed_symbols=("600000.SH",) if values else (),
            expected_request_count=1,
            successful_request_count=1,
            source_row_count=len(values),
            normalized_row_count=0,
            missing_field_counts=(),
            failure_counts=(),
        ),
        limitations=("PUBLIC_DATA_EXPLORATORY_ONLY",),
    )


def _bars(owner: HistoricalDataOwner) -> tuple[HistoricalNormalizedBar, ...]:
    return tuple(
        record
        for partition in owner.partitions
        for record in partition.records
        if isinstance(record, HistoricalNormalizedBar)
    )


def _normalized_owner(
    raw: HistoricalDataOwner,
    template: HistoricalDataOwner,
    records: tuple[HistoricalNormalizedBar, ...],
) -> HistoricalDataOwner:
    partitions = build_partitions(
        artifact_kind=HistoricalArtifactKind.NORMALIZED_DATASET,
        records=records,
        bucket_count=template.bucket_count,
    )
    return HistoricalDataOwner.create(
        artifact_kind=HistoricalArtifactKind.NORMALIZED_DATASET,
        provider_id=template.provider_id,
        normalization_version=template.normalization_version,
        parent_reference=raw.reference,
        created_at=template.created_at,
        retrieved_at=template.retrieved_at,
        first_market_date=min(item.first_market_date for item in partitions),
        last_market_date=max(item.last_market_date for item in partitions),
        bucket_count=template.bucket_count,
        partitions=partitions,
        coverage=replace(template.coverage, normalized_row_count=len(records)),
        limitations=template.limitations,
    )
