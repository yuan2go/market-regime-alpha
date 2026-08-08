from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.market_data import AssetType, Exchange, FormalPitStatus
from market_regime_alpha.universe.operational import (
    ListingStatus,
    OperationalLiquidityEvidence,
    OperationalUniverseArtifact,
    OperationalUniverseRecord,
    STStatus,
    SuspensionStatus,
)
from market_regime_alpha.universe.request_scoped import (
    RequestScopedUniverse,
    UniverseAuthority,
    build_request_scoped_universe,
)


UTC = timezone.utc
HASH = "sha256:" + "1" * 64


def _record(symbol: str, *, included: bool) -> OperationalUniverseRecord:
    source = ArtifactId(f"source-{symbol}")
    return OperationalUniverseRecord(
        symbol=symbol,
        asset_type=AssetType.A_SHARE,
        exchange=Exchange.SH if symbol.endswith(".SH") else Exchange.SZ,
        membership_source="CONTROLLED_REQUEST_SCOPE_V1",
        listing_status=ListingStatus.LISTED,
        st_status=STStatus.NOT_ST,
        suspension_status=SuspensionStatus.NOT_SUSPENDED,
        liquidity_evidence=OperationalLiquidityEvidence(
            lookback_sessions=20,
            observed_sessions=20,
            median_daily_amount=Decimal("250000000"),
            minimum_daily_amount=Decimal("100000000"),
            available_at=datetime(2026, 8, 6, 6, 25, tzinfo=UTC),
            source_artifact_id=source,
            source_content_hash=HASH,
        ),
        history_sessions_observed=250,
        history_sessions_required=250,
        included=included,
        inclusion_reasons=("SOURCE_INCLUDED",) if included else (),
        exclusion_reasons=() if included else ("SOURCE_EXCLUDED",),
        source_artifact_references=((source, HASH),),
        data_eligibility=DataEligibility.EXPLORATORY,
    )


def _source() -> OperationalUniverseArtifact:
    return OperationalUniverseArtifact.create(
        decision_date=date(2026, 8, 6),
        effective_at=datetime(2026, 8, 6, 6, 20, tzinfo=UTC),
        available_at=datetime(2026, 8, 6, 6, 30, tzinfo=UTC),
        records=(
            _record("000001.SZ", included=False),
            _record("600000.SH", included=True),
        ),
        formal_pit_status=FormalPitStatus.FORMAL_PIT_NOT_ESTABLISHED,
        data_eligibility=DataEligibility.EXPLORATORY,
        source_artifact_references=(
            (ArtifactId("source-000001.SZ"), HASH),
            (ArtifactId("source-600000.SH"), HASH),
        ),
        limitations=("FORMAL_PIT_NOT_ESTABLISHED",),
    )


def test_request_scope_preserves_exact_partition_and_source_authority() -> None:
    scoped = build_request_scoped_universe(
        source=_source(),
        requested_symbols=("688001.SH", "600000.SH", "000001.SZ"),
        configuration_id=ArtifactId("request-scope-config-v1"),
        configuration_hash=HASH,
    )

    assert scoped.authority is UniverseAuthority.REQUEST_SCOPED_UNIVERSE
    assert scoped.requested_symbols == (
        "000001.SZ",
        "600000.SH",
        "688001.SH",
    )
    assert scoped.included_symbols == ("600000.SH",)
    assert scoped.excluded_symbols == ("000001.SZ", "688001.SH")
    assert scoped.record_for("000001.SZ").reason_codes == ("SOURCE_EXCLUDED",)
    assert scoped.record_for("688001.SH").reason_codes == (
        "SOURCE_UNIVERSE_RECORD_MISSING",
    )
    assert scoped.formal_pit_status is FormalPitStatus.FORMAL_PIT_NOT_ESTABLISHED
    assert "COMPLETE_A_SHARE_PIT_UNIVERSE" not in scoped.limitations


def test_request_scope_identity_round_trip_and_tamper_rejection() -> None:
    scoped = build_request_scoped_universe(
        source=_source(),
        requested_symbols=("600000.SH",),
        configuration_id=ArtifactId("request-scope-config-v1"),
        configuration_hash=HASH,
    )

    restored = RequestScopedUniverse.from_canonical_dict(scoped.to_canonical_dict())

    assert restored == scoped
    with pytest.raises(ValueError, match="content hash mismatch"):
        replace(scoped, content_hash="sha256:" + "0" * 64)


def test_request_scope_rejects_silent_symbol_drop() -> None:
    scoped = build_request_scoped_universe(
        source=_source(),
        requested_symbols=("000001.SZ", "600000.SH"),
        configuration_id=ArtifactId("request-scope-config-v1"),
        configuration_hash=HASH,
    )

    with pytest.raises(ValueError, match="partition"):
        replace(scoped, records=scoped.records[:1])
