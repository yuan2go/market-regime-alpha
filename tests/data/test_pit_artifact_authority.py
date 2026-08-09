from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from market_regime_alpha.application.controlled_operation.input_artifacts import (
    publish_controlled_source_manifest,
)
from market_regime_alpha.core.identity import ArtifactId, ProviderId
from market_regime_alpha.core.time import DecisionTime, RetrievedAt
from market_regime_alpha.data.contracts import DataEligibility, SourceArtifactReference
from market_regime_alpha.data.pit_artifact_authority import (
    CanonicalPITArtifactAuthorityResolver,
    PITArtifactAuthorityUnavailableError,
)
from market_regime_alpha.data.pit_authority import (
    PITArtifactKind,
    PITArtifactReference,
)
from market_regime_alpha.data.source_manifest import SourceManifest


UTC = timezone.utc
NOW = datetime(2026, 8, 8, 7, 0, tzinfo=UTC)
HASH_A = "sha256:" + "a" * 64
HASH_B = "sha256:" + "b" * 64


def _published_source_manifest(tmp_path: Path) -> tuple[SourceManifest, Path]:
    manifest = SourceManifest(
        provider_profile_id="engineering-fixture-provider",
        decision_time=DecisionTime(NOW),
        source_artifacts=(
            SourceArtifactReference(
                artifact_id=ArtifactId("raw-source-a"),
                provider_id=ProviderId("engineering-fixture-provider"),
                retrieved_at=RetrievedAt(NOW),
                content_hash=HASH_A,
                locator="fixture://raw-source-a",
            ),
        ),
        fields=(),
        source_conflicts=(),
        limitations=("ENGINEERING_FIXTURE",),
        data_eligibility=DataEligibility.EXPLORATORY,
    )
    path = publish_controlled_source_manifest(
        root=tmp_path / "source-manifests",
        artifact=manifest,
    )
    return manifest, path


def test_resolver_uses_strict_reader_and_records_resolution(tmp_path: Path) -> None:
    manifest, _ = _published_source_manifest(tmp_path)
    resolver = CanonicalPITArtifactAuthorityResolver(
        artifact_roots={
            PITArtifactKind.SOURCE_MANIFEST: tmp_path / "source-manifests",
        },
    )

    resolution = resolver.resolve(
        PITArtifactReference(
            reference_kind=PITArtifactKind.SOURCE_MANIFEST.value,
            artifact_id=manifest.source_manifest_id,
            content_hash=manifest.content_hash,
        ),
        resolved_at=NOW,
    )

    assert resolution.reference.artifact_id == manifest.source_manifest_id
    assert resolution.canonical_schema == manifest.schema_version
    assert resolution.reader_contract == "controlled-source-manifest-package-v1"
    assert resolution.data_eligibility is DataEligibility.EXPLORATORY
    assert resolution.physical_checksums_hash.startswith("sha256:")


@pytest.mark.parametrize(
    ("artifact_id", "content_hash"),
    [
        (ArtifactId("forged-source-manifest"), HASH_B),
        (ArtifactId("source-manifest-placeholder"), HASH_B),
    ],
)
def test_resolver_rejects_forged_source_manifest_identity(
    tmp_path: Path,
    artifact_id: ArtifactId,
    content_hash: str,
) -> None:
    manifest, _ = _published_source_manifest(tmp_path)
    if artifact_id == ArtifactId("source-manifest-placeholder"):
        artifact_id = manifest.source_manifest_id
    resolver = CanonicalPITArtifactAuthorityResolver(
        artifact_roots={
            PITArtifactKind.SOURCE_MANIFEST: tmp_path / "source-manifests",
        },
    )

    with pytest.raises(PITArtifactAuthorityUnavailableError):
        resolver.resolve(
            PITArtifactReference(
                reference_kind=PITArtifactKind.SOURCE_MANIFEST.value,
                artifact_id=artifact_id,
                content_hash=content_hash,
            ),
            resolved_at=NOW,
        )


def test_resolver_fails_closed_without_authoritative_reader() -> None:
    resolver = CanonicalPITArtifactAuthorityResolver(artifact_roots={})

    with pytest.raises(
        PITArtifactAuthorityUnavailableError,
        match="no canonical Reader",
    ):
        resolver.resolve(
            PITArtifactReference(
                reference_kind=PITArtifactKind.VALIDATION_PROTOCOL.value,
                artifact_id=ArtifactId("caller-invented-protocol"),
                content_hash=HASH_A,
            ),
            resolved_at=NOW,
        )


def test_resolver_rejects_wrong_authority_kind(tmp_path: Path) -> None:
    manifest, _ = _published_source_manifest(tmp_path)
    resolver = CanonicalPITArtifactAuthorityResolver(
        artifact_roots={PITArtifactKind.SOURCE_MANIFEST: tmp_path / "source-manifests"}
    )

    with pytest.raises(PITArtifactAuthorityUnavailableError, match="no canonical Reader"):
        resolver.resolve(
            PITArtifactReference(
                reference_kind=PITArtifactKind.ELIGIBILITY.value,
                artifact_id=manifest.source_manifest_id,
                content_hash=manifest.content_hash,
            ),
            resolved_at=NOW,
        )
