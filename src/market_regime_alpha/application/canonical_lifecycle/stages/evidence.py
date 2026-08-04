"""Verified H6 evidence adapter for the canonical lifecycle.

This module performs only Reader-level verification and lineage binding.  It
does not reinterpret the H6 composition policy or copy any research logic.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from market_regime_alpha.application.canonical_lifecycle.contracts import (
    LifecycleConfigurationReference,
    LifecycleModelVersionReference,
    LifecycleObjectId,
    LifecycleObjectReference,
    LifecycleObjectType,
    LifecycleReaderKind,
    LifecycleRun,
)
from market_regime_alpha.application.canonical_lifecycle.stages.contracts import (
    LifecycleStageContext,
    StageExecutionResult,
    StageMutationKind,
)
from market_regime_alpha.application.canonical_lifecycle.states import (
    LifecycleRunStatus,
    LifecycleStageName,
    LifecycleStageStatus,
)
from market_regime_alpha.application.operational_research.composite_artifact import (
    VerifiedCompositeOperationalManifest,
    load_verified_composite_operational_manifest,
)
from market_regime_alpha.application.operational_research.composite_manifest import (
    CompositeOperationalCompositionStatus,
)
from market_regime_alpha.core.identity import ArtifactId, ModelId
from market_regime_alpha.evidence.canonical import require_text


class _IdentifiedConfiguration(Protocol):
    @property
    def configuration_id(self) -> ArtifactId: ...

    @property
    def configuration_hash(self) -> str: ...


def ordered_references(
    references: tuple[LifecycleObjectReference, ...],
) -> tuple[LifecycleObjectReference, ...]:
    """Return the journal's canonical reference ordering."""

    return tuple(sorted(references, key=lambda item: item.sort_key))


def references_for_type(
    context: LifecycleStageContext,
    object_type: LifecycleObjectType,
) -> tuple[LifecycleObjectReference, ...]:
    """Resolve exact typed references without allowing ambiguous substitution."""

    if not isinstance(object_type, LifecycleObjectType):
        raise TypeError("object_type must be a LifecycleObjectType")
    candidates = (
        *context.initial_references,
        *context.upstream_references,
    )
    by_identity: dict[tuple[str, str, str], LifecycleObjectReference] = {}
    for reference in candidates:
        if reference.object_type is not object_type:
            continue
        key = reference.sort_key
        existing = by_identity.get(key)
        if existing is not None and existing != reference:
            raise ValueError(f"conflicting {object_type.value} lifecycle references")
        by_identity[key] = reference
    return ordered_references(tuple(by_identity.values()))


def require_single_reference(
    context: LifecycleStageContext,
    object_type: LifecycleObjectType,
) -> LifecycleObjectReference:
    values = references_for_type(context, object_type)
    if len(values) != 1:
        raise ValueError(f"lifecycle stage requires exactly one {object_type.value} reference")
    return values[0]


def reference_path(reference: LifecycleObjectReference) -> Path:
    if reference.locator is None:
        raise ValueError(f"{reference.reader_kind.value} reference has no locator")
    return Path(reference.locator).resolve()


def output_reference(
    *,
    object_type: LifecycleObjectType,
    object_id: ArtifactId,
    content_hash: str,
    reader_kind: LifecycleReaderKind,
    locator: Path,
    available_at: datetime,
) -> LifecycleObjectReference:
    """Build a Reader-bound reference from one verified published Artifact."""

    if available_at.tzinfo is None or available_at.utcoffset() is None:
        raise ValueError("Artifact available_at must be timezone-aware")
    canonical_available_at = available_at.astimezone(timezone.utc)
    if canonical_available_at.microsecond != 0:
        raise ValueError("Artifact available_at must have whole-second precision")
    return LifecycleObjectReference(
        object_type=object_type,
        object_id=LifecycleObjectId(str(object_id)),
        content_hash=content_hash,
        reader_kind=reader_kind,
        locator=str(locator.resolve()),
        available_at=canonical_available_at,
    )


def require_configuration_binding(
    run: LifecycleRun,
    configuration: _IdentifiedConfiguration,
    *,
    configuration_version: str,
) -> LifecycleConfigurationReference:
    """Bind an injected immutable configuration to the persisted command."""

    require_text("configuration_version", configuration_version)
    matches = tuple(
        reference
        for reference in run.configuration_references
        if reference.configuration_id == configuration.configuration_id
    )
    if len(matches) != 1:
        raise ValueError("command does not bind the injected configuration identity")
    reference = matches[0]
    if (
        reference.content_hash != configuration.configuration_hash
        or reference.configuration_version != configuration_version
    ):
        raise ValueError("injected configuration does not match command reference")
    return reference


def require_model_binding(
    run: LifecycleRun,
    *,
    model_id: ModelId,
    model_version: str,
) -> LifecycleModelVersionReference:
    """Bind a model/version to exactly one persisted command reference."""

    require_text("model_version", model_version)
    matches = tuple(
        reference
        for reference in run.model_references
        if reference.model_id == model_id
        and reference.model_version == model_version
    )
    if len(matches) != 1:
        raise ValueError("command does not bind the required model version")
    return matches[0]


def lifecycle_code_revision(run: LifecycleRun) -> str:
    """Derive the domain audit revision from the command-bound model manifest."""

    return f"canonical-lifecycle:{run.model_version_manifest_hash}"


class VerifiedCompositeEvidenceStageHandler:
    """Verify the H6 package and its exact Daily/Supplemental bindings."""

    stage_name = LifecycleStageName.VERIFY_COMPOSITE_EVIDENCE
    mutation_kind = StageMutationKind.READ_ONLY

    def recover(self, context: LifecycleStageContext) -> StageExecutionResult | None:
        return self.execute(context)

    def execute(self, context: LifecycleStageContext) -> StageExecutionResult:
        composite_reference = require_single_reference(
            context, LifecycleObjectType.COMPOSITE_OPERATIONAL_MANIFEST
        )
        daily_reference = require_single_reference(
            context, LifecycleObjectType.DAILY_DECISION_ARTIFACT
        )
        supplemental_reference = require_single_reference(
            context, LifecycleObjectType.SUPPLEMENTAL_RESEARCH_EVIDENCE
        )
        source_references = references_for_type(
            context, LifecycleObjectType.SOURCE_MANIFEST
        )
        verified = load_verified_composite_operational_manifest(
            reference_path(composite_reference)
        )
        self._verify_reference(verified, composite_reference)
        manifest = verified.manifest
        if manifest.status is not CompositeOperationalCompositionStatus.VERIFIED:
            raise ValueError("canonical lifecycle requires VERIFIED H6 evidence")
        if (
            str(manifest.daily_artifact_id) != str(daily_reference.object_id)
            or manifest.daily_artifact_hash != daily_reference.content_hash
            or str(manifest.supplemental_bundle_id) != str(supplemental_reference.object_id)
            or manifest.supplemental_bundle_hash != supplemental_reference.content_hash
        ):
            raise ValueError(
                "Composite Operational Manifest does not bind lifecycle inputs"
            )
        expected_sources = {
            (
                str(manifest.daily_source_manifest_id),
                manifest.daily_source_manifest_hash,
            ),
            (
                str(manifest.supplemental_source_manifest_id),
                manifest.supplemental_source_manifest_hash,
            ),
        }
        actual_sources = {
            (str(reference.object_id), reference.content_hash)
            for reference in source_references
        }
        if actual_sources != expected_sources:
            raise ValueError(
                "lifecycle SourceManifest references do not exactly cover H6 bindings"
            )
        inputs = ordered_references(
            (
                composite_reference,
                daily_reference,
                supplemental_reference,
                *source_references,
            )
        )
        return StageExecutionResult(
            stage_status=LifecycleStageStatus.COMPLETED,
            run_status=LifecycleRunStatus.RUNNING,
            input_references=inputs,
            output_references=(composite_reference,),
            model_versions=(),
            configuration_hashes=(),
            reason_codes=("COMPOSITE_OPERATIONAL_EVIDENCE_VERIFIED",),
            blocker_reason=None,
        )

    @staticmethod
    def _verify_reference(
        verified: VerifiedCompositeOperationalManifest,
        reference: LifecycleObjectReference,
    ) -> None:
        if (
            str(verified.manifest.manifest_id) != str(reference.object_id)
            or verified.manifest.content_hash != reference.content_hash
            or verified.root != reference_path(reference)
        ):
            raise ValueError("Composite Operational Manifest reference mismatch")
