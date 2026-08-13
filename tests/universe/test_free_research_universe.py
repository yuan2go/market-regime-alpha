from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.universe.research import (
    FreeDataEvidenceOrigin,
    ResearchUniverseSelectionBasis,
    ResearchUniverseMembershipStatus,
    build_free_research_universe_snapshot,
    build_historical_constituent_universe_snapshot,
    project_free_research_universe_as_of,
)


KNOWN_AT = datetime(2026, 8, 10, 8, tzinfo=UTC)


def _snapshot():
    return build_free_research_universe_snapshot(
        as_of_date=date(2020, 1, 2),
        known_at=KNOWN_AT,
        provider_id="provider-baostock-public",
        provider_contract="baostock-query-stock-basic-all/v1",
        source_manifest_reference=ValidationArtifactReference(
            "SOURCE_MANIFEST",
            ArtifactId("research-universe-manifest"),
            canonical_hash({"manifest": 1}),
        ),
        raw_archive_id="source-replay-research-universe",
        evidence_origin=FreeDataEvidenceOrigin.ENGINEERING_FIXTURE,
        rows=(
            {
                "code": "sz.000001",
                "code_name": "平安银行",
                "ipoDate": "1991-04-03",
                "outDate": "",
                "type": "1",
                "status": "1",
            },
            {
                "code": "sh.600001",
                "code_name": "已退市样本",
                "ipoDate": "1990-12-19",
                "outDate": "2019-12-31",
                "type": "1",
                "status": "0",
            },
            {
                "code": "sz.300999",
                "code_name": "未来上市样本",
                "ipoDate": "2021-01-01",
                "outDate": "",
                "type": "1",
                "status": "1",
            },
            {
                "code": "sh.689999",
                "code_name": "类型未知但不得丢弃",
                "ipoDate": "",
                "outDate": "",
                "type": "",
                "status": "",
            },
            {
                "code": "sz.000002",
                "code_name": "上市状态未知但不得纳入",
                "ipoDate": "1991-01-29",
                "outDate": "",
                "type": "1",
                "status": "",
            },
        ),
    )


def test_free_research_universe_retains_unknown_and_separates_population() -> None:
    snapshot = _snapshot()
    by_symbol = {item.symbol: item for item in snapshot.records}

    assert by_symbol["000001.SZ"].membership_status is ResearchUniverseMembershipStatus.INCLUDED
    assert by_symbol["600001.SH"].membership_status is ResearchUniverseMembershipStatus.EXCLUDED
    assert by_symbol["300999.SZ"].membership_status is ResearchUniverseMembershipStatus.EXCLUDED
    assert by_symbol["689999.SH"].membership_status is ResearchUniverseMembershipStatus.UNKNOWN
    assert by_symbol["000002.SZ"].membership_status is ResearchUniverseMembershipStatus.UNKNOWN
    assert "CURRENT_LISTING_STATUS_UNKNOWN" in by_symbol["000002.SZ"].reason_codes
    assert snapshot.security_master_count == 5
    assert snapshot.included_count == 1
    assert snapshot.unknown_count == 2
    assert snapshot.formal_pit is False
    assert "FORMAL_PIT_NOT_ESTABLISHED" in snapshot.limitations


def test_retrospective_projection_uses_listing_dates_but_keeps_true_known_at() -> None:
    source = _snapshot()

    projected = project_free_research_universe_as_of(
        source,
        as_of_date=date(2022, 1, 3),
    )
    by_symbol = {item.symbol: item for item in projected.records}

    assert projected.known_at == KNOWN_AT
    assert by_symbol["300999.SZ"].membership_status is ResearchUniverseMembershipStatus.INCLUDED
    assert by_symbol["600001.SH"].membership_status is ResearchUniverseMembershipStatus.EXCLUDED
    assert "CURRENT_SECURITY_MASTER_PROJECTED_RETROSPECTIVELY" in projected.limitations
    assert projected.snapshot_hash != source.snapshot_hash


def test_retrospective_projection_can_freeze_exact_selector_subset() -> None:
    source = _snapshot()

    projected = project_free_research_universe_as_of(
        source,
        as_of_date=date(2022, 1, 3),
        symbols=("300999.SZ", "000001.SZ"),
    )

    assert tuple(item.symbol for item in projected.records) == (
        "000001.SZ",
        "300999.SZ",
    )
    assert projected.source_manifest_reference == source.source_manifest_reference
    assert "FROZEN_SELECTOR_SUBSET_PROJECTION" in projected.limitations


def test_historical_constituent_snapshot_does_not_project_current_master() -> None:
    constituent_source = ValidationArtifactReference(
        "HISTORICAL_CONSTITUENT_SNAPSHOT",
        ArtifactId("hs300-2026-06-15"),
        canonical_hash({"hs300": "2026-06-15"}),
    )
    snapshot = build_historical_constituent_universe_snapshot(
        effective_date=date(2026, 6, 15),
        known_at=KNOWN_AT,
        provider_id="provider-baostock-public",
        provider_contract="baostock-query-hs300-stocks/v1",
        source_manifest_reference=ValidationArtifactReference(
            "SOURCE_MANIFEST",
            ArtifactId("historical-universe-manifest"),
            canonical_hash({"manifest": "historical"}),
        ),
        constituent_source_reference=constituent_source,
        raw_archive_id="historical-hs300-archive",
        evidence_origin=FreeDataEvidenceOrigin.REAL_FREE_PROVIDER_OBSERVATION,
        constituent_rows=(
            {"updateDate": "2026-06-15", "code": "sh.600000", "code_name": "浦发银行"},
            {"updateDate": "2026-06-15", "code": "sz.000001", "code_name": "平安银行"},
        ),
        security_master_rows=(
            {
                "code": "sh.600000",
                "code_name": "浦发银行",
                "ipoDate": "1999-11-10",
                "outDate": "2026-06-30",
                "type": "1",
                "status": "1",
            },
        ),
    )

    projected = project_free_research_universe_as_of(
        snapshot,
        as_of_date=date(2026, 7, 1),
    )

    assert snapshot.selection_basis is ResearchUniverseSelectionBasis.HISTORICAL_CONSTITUENT_SNAPSHOT
    assert snapshot.included_count == 2
    assert projected.known_at == KNOWN_AT
    assert projected.constituent_source_reference == constituent_source
    assert "CURRENT_SECURITY_MASTER_PROJECTED_RETROSPECTIVELY" not in projected.limitations
    assert "FROZEN_HISTORICAL_CONSTITUENT_SNAPSHOT" in projected.limitations
    assert "CURRENT_CLASSIFICATION_NOT_BACKFILLED" in projected.limitations
    assert next(item for item in projected.records if item.symbol == "000001.SZ").listing_status.value == "UNKNOWN"
    delisted = next(item for item in projected.records if item.symbol == "600000.SH")
    assert delisted.listing_status.value == "DELISTED"
    assert delisted.membership_status is ResearchUniverseMembershipStatus.EXCLUDED
    assert "DELISTED_BY_AS_OF_DATE" in delisted.reason_codes

    with pytest.raises(ValueError, match="predates frozen constituent"):
        project_free_research_universe_as_of(
            snapshot,
            as_of_date=date(2026, 6, 14),
        )


def test_historical_constituent_uses_provider_effective_date_not_query_date() -> None:
    snapshot = build_historical_constituent_universe_snapshot(
        effective_date=date(2025, 1, 2),
        known_at=KNOWN_AT,
        provider_id="provider-baostock-public",
        provider_contract="baostock-query-hs300-stocks/v1",
        source_manifest_reference=ValidationArtifactReference(
            "SOURCE_MANIFEST",
            ArtifactId("historical-universe-query-date-manifest"),
            canonical_hash({"manifest": "query-date"}),
        ),
        constituent_source_reference=ValidationArtifactReference(
            "HISTORICAL_CONSTITUENT_SNAPSHOT",
            ArtifactId("hs300-query-date"),
            canonical_hash({"hs300": "query-date"}),
        ),
        raw_archive_id="historical-hs300-query-date-archive",
        evidence_origin=FreeDataEvidenceOrigin.REAL_FREE_PROVIDER_OBSERVATION,
        constituent_rows=(
            {
                "updateDate": "2024-12-30",
                "code": "sh.600000",
                "code_name": "浦发银行",
            },
        ),
        security_master_rows=(),
    )

    assert snapshot.as_of_date == date(2025, 1, 2)
    assert snapshot.constituent_effective_date == date(2024, 12, 30)


def test_historical_constituent_rejects_mixed_provider_effective_dates() -> None:
    with pytest.raises(ValueError, match="one Provider effective date"):
        build_historical_constituent_universe_snapshot(
            effective_date=date(2025, 1, 2),
            known_at=KNOWN_AT,
            provider_id="provider-baostock-public",
            provider_contract="baostock-query-hs300-stocks/v1",
            source_manifest_reference=ValidationArtifactReference(
                "SOURCE_MANIFEST",
                ArtifactId("historical-universe-mixed-manifest"),
                canonical_hash({"manifest": "mixed"}),
            ),
            constituent_source_reference=ValidationArtifactReference(
                "HISTORICAL_CONSTITUENT_SNAPSHOT",
                ArtifactId("hs300-mixed"),
                canonical_hash({"hs300": "mixed"}),
            ),
            raw_archive_id="historical-hs300-mixed-archive",
            evidence_origin=FreeDataEvidenceOrigin.REAL_FREE_PROVIDER_OBSERVATION,
            constituent_rows=(
                {
                    "updateDate": "2024-12-30",
                    "code": "sh.600000",
                    "code_name": "浦发银行",
                },
                {
                    "updateDate": "2025-01-02",
                    "code": "sz.000001",
                    "code_name": "平安银行",
                },
            ),
            security_master_rows=(),
        )
