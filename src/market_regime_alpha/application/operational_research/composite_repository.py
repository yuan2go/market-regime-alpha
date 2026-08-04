"""Storage-neutral H6 command and publication-index boundary."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from market_regime_alpha.application.operational_research.composite_artifact import (
    VerifiedCompositeOperationalManifest,
)
from market_regime_alpha.application.operational_research.supplemental_artifact import (
    VerifiedSupplementalResearchEvidence,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.daily_decision.reader import (
    VerifiedPhaseDDailyDecisionArtifact,
)
from market_regime_alpha.evidence.canonical import canonical_datetime, canonical_hash


class CompositeOperationalRepository(Protocol):
    def resolve_command(
        self, *, idempotency_key: str, command_hash: str
    ) -> VerifiedCompositeOperationalManifest | None: ...

    def get_manifest(
        self, manifest_id: ArtifactId
    ) -> VerifiedCompositeOperationalManifest: ...

    def save_manifest(
        self,
        composite: VerifiedCompositeOperationalManifest,
        *,
        daily_package_path: Path,
        supplemental_package_path: Path,
        idempotency_key: str,
        command_hash: str,
        before_command_insert: Callable[[], None] | None = None,
    ) -> VerifiedCompositeOperationalManifest: ...


def composite_operational_command_hash(
    *,
    daily: VerifiedPhaseDDailyDecisionArtifact,
    supplemental: VerifiedSupplementalResearchEvidence,
    composite: VerifiedCompositeOperationalManifest,
) -> str:
    manifest = composite.manifest
    if (
        manifest.daily_artifact_id != ArtifactId(daily.artifact_id)
        or manifest.daily_artifact_hash != daily.bundle.content_hash
        or manifest.supplemental_bundle_id != supplemental.bundle.bundle_id
        or manifest.supplemental_bundle_hash != supplemental.bundle.content_hash
    ):
        raise ValueError("composite command source identity mismatch")
    return canonical_hash(
        {
            "schema_version": "composite-operational-command-v1",
            "daily_artifact_id": daily.artifact_id,
            "daily_artifact_hash": daily.bundle.content_hash,
            "daily_package_checksums_hash": daily.checksums_hash,
            "daily_source_manifest_id": str(
                daily.bundle.source_manifest.source_manifest_id
            ),
            "daily_source_manifest_hash": (
                daily.bundle.source_manifest.content_hash
            ),
            "supplemental_bundle_id": str(supplemental.bundle.bundle_id),
            "supplemental_bundle_hash": supplemental.bundle.content_hash,
            "supplemental_package_checksums_hash": supplemental.checksums_hash,
            "supplemental_source_manifest_id": str(
                supplemental.bundle.source_manifest.source_manifest_id
            ),
            "supplemental_source_manifest_hash": (
                supplemental.bundle.source_manifest.content_hash
            ),
            "composition_policy_id": str(
                composite.composition_policy.policy_id
            ),
            "composition_policy_hash": composite.composition_policy.policy_hash,
            "builder_revision": composite.composition_policy.builder_revision,
            "created_at": canonical_datetime(manifest.created_at),
            "manifest_id": str(manifest.manifest_id),
            "manifest_hash": manifest.content_hash,
            "composite_package_checksums_hash": composite.checksums_hash,
        }
    )
