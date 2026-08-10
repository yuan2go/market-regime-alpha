from __future__ import annotations

from datetime import UTC, date, datetime

from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.universe.research import (
    FreeDataEvidenceOrigin,
    ResearchUniverseMembershipStatus,
    build_free_research_universe_snapshot,
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
        ),
    )


def test_free_research_universe_retains_unknown_and_separates_population() -> None:
    snapshot = _snapshot()
    by_symbol = {item.symbol: item for item in snapshot.records}

    assert by_symbol["000001.SZ"].membership_status is ResearchUniverseMembershipStatus.INCLUDED
    assert by_symbol["600001.SH"].membership_status is ResearchUniverseMembershipStatus.EXCLUDED
    assert by_symbol["300999.SZ"].membership_status is ResearchUniverseMembershipStatus.EXCLUDED
    assert by_symbol["689999.SH"].membership_status is ResearchUniverseMembershipStatus.UNKNOWN
    assert snapshot.security_master_count == 4
    assert snapshot.included_count == 1
    assert snapshot.unknown_count == 1
    assert snapshot.formal_pit is False
    assert "FORMAL_PIT_NOT_ESTABLISHED" in snapshot.limitations
