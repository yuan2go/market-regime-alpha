from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.data.providers.public_composite.research_universe import (
    _normalize_security_master_rows,
)
from market_regime_alpha.data_sources.a_share_bars import AShareDataError
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.universe.research import (
    FreeDataEvidenceOrigin,
    ResearchUniverseMembershipStatus,
    build_free_research_universe_snapshot,
)


def test_malformed_security_master_row_with_code_is_retained_as_unknown() -> None:
    rows = _normalize_security_master_rows(
        fields=("code", "code_name", "ipoDate", "outDate", "type", "status"),
        rows=(("sz.000001", "平安银行", "1991-04-03", "", "1"),),
    )
    snapshot = build_free_research_universe_snapshot(
        as_of_date=date(2026, 8, 10),
        known_at=datetime(2026, 8, 10, 8, tzinfo=UTC),
        provider_id="provider-baostock-public",
        provider_contract="baostock-query-stock-basic-all/v1",
        source_manifest_reference=ValidationArtifactReference(
            "SOURCE_MANIFEST",
            ArtifactId("malformed-universe-manifest"),
            canonical_hash({"manifest": "malformed"}),
        ),
        raw_archive_id="malformed-universe-archive",
        evidence_origin=FreeDataEvidenceOrigin.ENGINEERING_FIXTURE,
        rows=rows,
    )

    record = snapshot.records[0]
    assert record.symbol == "000001.SZ"
    assert record.membership_status is ResearchUniverseMembershipStatus.UNKNOWN
    assert "PROVIDER_ROW_FIELD_COUNT_MISMATCH" in record.reason_codes


def test_malformed_security_master_row_without_code_fails_closed() -> None:
    with pytest.raises(AShareDataError, match="has no security code"):
        _normalize_security_master_rows(
            fields=("code", "code_name", "ipoDate"),
            rows=(("", "unknown", ""),),
        )
