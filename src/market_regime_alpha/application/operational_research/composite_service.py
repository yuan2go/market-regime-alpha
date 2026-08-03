"""File-first application orchestration for H6 composite publication."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from market_regime_alpha.application.operational_research.composite_artifact import (
    VerifiedCompositeOperationalManifest,
    cleanup_orphan_composite_staging,
    load_verified_composite_operational_manifest,
    publish_composite_operational_manifest,
)
from market_regime_alpha.application.operational_research.composite_manifest import (
    CompositeOperationalCompositionPolicy,
    CompositeOperationalManifestBuilder,
)
from market_regime_alpha.application.operational_research.composite_repository import (
    CompositeOperationalRepository,
    composite_operational_command_hash,
)
from market_regime_alpha.application.operational_research.supplemental_artifact import (
    load_verified_supplemental_research_evidence,
)
from market_regime_alpha.daily_decision.reader_registry import (
    load_verified_daily_decision_artifact,
)


class CompositeOperationalEvidenceApplicationService:
    """Publish and index one terminal H6 result; run no research or trade action."""

    def __init__(self, repository: CompositeOperationalRepository) -> None:
        self._repository = repository

    def build_and_publish(
        self,
        *,
        daily_package_path: Path,
        supplemental_package_path: Path,
        composition_policy: CompositeOperationalCompositionPolicy,
        package_root: Path,
        created_at: datetime,
        idempotency_key: str,
        after_package_publish: (
            Callable[[VerifiedCompositeOperationalManifest], None] | None
        ) = None,
    ) -> VerifiedCompositeOperationalManifest:
        cleanup_orphan_composite_staging(package_root)
        daily = load_verified_daily_decision_artifact(daily_package_path)
        supplemental = load_verified_supplemental_research_evidence(
            supplemental_package_path
        )
        manifest = CompositeOperationalManifestBuilder().build(
            daily=daily,
            supplemental=supplemental,
            composition_policy=composition_policy,
            created_at=created_at,
        )
        package_path = publish_composite_operational_manifest(
            root=package_root,
            manifest=manifest,
            composition_policy=composition_policy,
        )
        composite = load_verified_composite_operational_manifest(package_path)
        command_hash = composite_operational_command_hash(
            daily=daily,
            supplemental=supplemental,
            composite=composite,
        )
        if after_package_publish is not None:
            after_package_publish(composite)
        return self._repository.save_manifest(
            composite,
            daily_package_path=daily.root,
            supplemental_package_path=supplemental.root,
            idempotency_key=idempotency_key,
            command_hash=command_hash,
        )
