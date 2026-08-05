from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.market_data import AssetType, Exchange, FormalPitStatus
from market_regime_alpha.universe import (
    ListingStatus,
    OperationalLiquidityEvidence,
    OperationalUniverseArtifact,
    OperationalUniverseRecord,
    STStatus,
    SuspensionStatus,
    load_operational_universe,
    publish_operational_universe,
)


UTC = timezone.utc
SOURCE_HASH = "sha256:" + "1" * 64


def _record(index: int, *, included: bool = True) -> OperationalUniverseRecord:
    symbol = f"{600000 + index:06d}.SH"
    source = ArtifactId(f"listing-source-{index}")
    return OperationalUniverseRecord(
        symbol=symbol,
        asset_type=AssetType.A_SHARE,
        exchange=Exchange.SH,
        membership_source="CONTROLLED_LIQUID_A_SHARE_SELECTION_V1",
        listing_status=ListingStatus.LISTED,
        st_status=STStatus.NOT_ST,
        suspension_status=SuspensionStatus.NOT_SUSPENDED,
        liquidity_evidence=OperationalLiquidityEvidence(
            lookback_sessions=20,
            observed_sessions=20,
            median_daily_amount=Decimal("250000000"),
            minimum_daily_amount=Decimal("100000000"),
            available_at=datetime(2026, 8, 5, 6, 40, tzinfo=UTC),
            source_artifact_id=source,
            source_content_hash=SOURCE_HASH,
        ),
        history_sessions_observed=250,
        history_sessions_required=250,
        included=included,
        inclusion_reasons=("HISTORY_AND_LIQUIDITY_EVIDENCE_COMPLETE",)
        if included
        else (),
        exclusion_reasons=()
        if included
        else ("CONTROLLED_SCOPE_CAP_EXCEEDED",),
        source_artifact_references=((source, SOURCE_HASH),),
        data_eligibility=DataEligibility.EXPLORATORY,
    )


def _artifact(count: int) -> OperationalUniverseArtifact:
    records = tuple(_record(index) for index in range(count))
    return OperationalUniverseArtifact.create(
        decision_date=date(2026, 8, 5),
        effective_at=datetime(2026, 8, 5, 6, 30, tzinfo=UTC),
        available_at=datetime(2026, 8, 5, 6, 45, tzinfo=UTC),
        records=records,
        formal_pit_status=FormalPitStatus.FORMAL_PIT_NOT_ESTABLISHED,
        data_eligibility=DataEligibility.EXPLORATORY,
        source_artifact_references=tuple(
            (ArtifactId(f"listing-source-{index}"), SOURCE_HASH)
            for index in range(count)
        ),
        limitations=(
            "CONTROLLED_EXPLORATORY_UNIVERSE",
            "FORMAL_PIT_NOT_ESTABLISHED",
            "NOT_THE_LEGACY_20_SYMBOL_SMOKE_POOL",
        ),
    )


@pytest.mark.parametrize("count", (100, 300))
def test_operational_universe_supports_controlled_scope_and_round_trip(
    tmp_path: Path, count: int
) -> None:
    artifact = _artifact(count)

    package = publish_operational_universe(root=tmp_path, artifact=artifact)
    restored = load_operational_universe(package)

    assert restored == artifact
    assert len(restored.symbols) == count
    assert restored.formal_pit_status is FormalPitStatus.FORMAL_PIT_NOT_ESTABLISHED
    assert all(item.inclusion_reasons for item in restored.records)
    assert "NOT_THE_LEGACY_20_SYMBOL_SMOKE_POOL" in restored.limitations
    assert {item.name for item in package.iterdir()} == {
        "artifact.json",
        "SHA256SUMS.json",
    }


def test_operational_universe_records_explicit_exclusion_without_silent_drop() -> None:
    records = (*tuple(_record(index) for index in range(100)), _record(100, included=False))
    artifact = OperationalUniverseArtifact.create(
        decision_date=date(2026, 8, 5),
        effective_at=datetime(2026, 8, 5, 6, 30, tzinfo=UTC),
        available_at=datetime(2026, 8, 5, 6, 45, tzinfo=UTC),
        records=records,
        formal_pit_status=FormalPitStatus.FORMAL_PIT_NOT_ESTABLISHED,
        data_eligibility=DataEligibility.EXPLORATORY,
        source_artifact_references=tuple(
            (ArtifactId(f"listing-source-{index}"), SOURCE_HASH)
            for index in range(101)
        ),
        limitations=("FORMAL_PIT_NOT_ESTABLISHED",),
    )

    assert len(artifact.symbols) == 100
    assert artifact.records[-1].exclusion_reasons == (
        "CONTROLLED_SCOPE_CAP_EXCEEDED",
    )


def test_operational_universe_cannot_inflate_formal_pit_authority() -> None:
    with pytest.raises(ValueError, match="FORMAL_RESEARCH"):
        OperationalUniverseArtifact.create(
            decision_date=date(2026, 8, 5),
            effective_at=datetime(2026, 8, 5, 6, 30, tzinfo=UTC),
            available_at=datetime(2026, 8, 5, 6, 45, tzinfo=UTC),
            records=(_record(0),),
            formal_pit_status=FormalPitStatus.PIT_CORRECT_FOR_DECLARED_SCOPE,
            data_eligibility=DataEligibility.EXPLORATORY,
            source_artifact_references=((ArtifactId("listing-source-0"), SOURCE_HASH),),
            limitations=(),
        )


def test_operational_universe_tamper_and_extra_file_are_rejected(tmp_path: Path) -> None:
    package = publish_operational_universe(root=tmp_path, artifact=_artifact(100))
    (package / "unexpected.tmp").write_text("unexpected", encoding="utf-8")
    with pytest.raises(ValueError, match="exact file set"):
        load_operational_universe(package)
