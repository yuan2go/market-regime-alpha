from __future__ import annotations

from datetime import date, datetime, timezone
from hashlib import sha256
from pathlib import Path

import pytest

from market_regime_alpha.application.controlled_operation.outcome_source_archive import (
    OutcomeRawSourcePayload,
    OutcomeSettlementSourceArchive,
    load_outcome_settlement_source_archive,
    publish_outcome_settlement_source_archive,
)
from market_regime_alpha.core.identity import ArtifactId, ProviderId
from market_regime_alpha.core.time import DecisionTime, RetrievedAt
from market_regime_alpha.data.contracts import DataEligibility, SourceArtifactReference
from market_regime_alpha.data.source_manifest import SourceManifest


UTC = timezone.utc


def _fixture() -> tuple[OutcomeSettlementSourceArchive, tuple[OutcomeRawSourcePayload, ...]]:
    payload = b"recorded-t-plus-one-source"
    source_hash = "sha256:" + sha256(payload).hexdigest()
    source_id = ArtifactId("outcome-source")
    observed = datetime(2026, 8, 6, 7, 1, tzinfo=UTC)
    manifest = SourceManifest(
        provider_profile_id="recorded-outcome-v1",
        decision_time=DecisionTime(observed),
        source_artifacts=(
            SourceArtifactReference(
                artifact_id=source_id,
                provider_id=ProviderId("recorded-provider"),
                retrieved_at=RetrievedAt(observed),
                content_hash=source_hash,
                locator="fixture://outcome/source",
            ),
        ),
        fields=(),
        source_conflicts=(),
        limitations=("ENGINEERING_FIXTURE",),
        data_eligibility=DataEligibility.EXPLORATORY,
        schema_version=SourceManifest.SCHEMA_V2,
    )
    payloads = (
        OutcomeRawSourcePayload(
            source_artifact_id=source_id,
            source_kind="T_PLUS_ONE_MINUTE_AND_DAILY",
            media_type="application/octet-stream",
            payload=payload,
        ),
    )
    return (
        OutcomeSettlementSourceArchive.create(
            source_manifest=manifest,
            next_session_date=date(2026, 8, 6),
            raw_payloads=payloads,
            created_at=observed,
        ),
        payloads,
    )


def test_outcome_source_archive_verifies_exact_raw_bytes(tmp_path: Path) -> None:
    artifact, payloads = _fixture()
    path = publish_outcome_settlement_source_archive(
        root=tmp_path,
        artifact=artifact,
        raw_payloads=payloads,
    )

    assert load_outcome_settlement_source_archive(path) == artifact
    (path / artifact.entries[0].archived_locator).write_bytes(b"tampered")
    with pytest.raises(ValueError, match="checksums mismatch"):
        load_outcome_settlement_source_archive(path)
