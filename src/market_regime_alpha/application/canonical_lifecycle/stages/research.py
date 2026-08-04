"""Canonical adapter around the existing H6 -> Platform V2 research chain."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from market_regime_alpha.application.canonical_lifecycle.contracts import (
    LifecycleObjectReference,
    LifecycleObjectType,
    LifecycleReaderKind,
)
from market_regime_alpha.application.canonical_lifecycle.stages.contracts import (
    LifecycleStageContext,
    StageExecutionResult,
    StageMutationKind,
)
from market_regime_alpha.application.canonical_lifecycle.stages.evidence import (
    lifecycle_code_revision,
    ordered_references,
    output_reference,
    reference_path,
    references_for_type,
    require_configuration_binding,
    require_model_binding,
    require_single_reference,
)
from market_regime_alpha.application.canonical_lifecycle.states import (
    LifecycleRunStatus,
    LifecycleStageName,
    LifecycleStageStatus,
)
from market_regime_alpha.application.operational_research.bridge import (
    OperationalResearchRunner,
    adapt_verified_composite_operational_inputs,
)
from market_regime_alpha.application.operational_research.composite_artifact import (
    VerifiedCompositeOperationalManifest,
    load_verified_composite_operational_manifest,
)
from market_regime_alpha.application.operational_research.supplemental_artifact import (
    VerifiedSupplementalResearchEvidence,
    load_verified_supplemental_research_evidence,
)
from market_regime_alpha.application.research_layer.runner import (
    PlatformResearchRunner,
)
from market_regime_alpha.daily_decision.reader import (
    VerifiedPhaseDDailyDecisionArtifact,
)
from market_regime_alpha.daily_decision.reader_registry import (
    load_verified_daily_decision_artifact,
)
from market_regime_alpha.research.platform_v2.configs import (
    ResearchPipelineConfig,
)
from market_regime_alpha.research.platform_v2.reader import (
    VerifiedResearchLayerArtifact,
)
from market_regime_alpha.research.platform_v2.reader_registry import (
    load_verified_research_artifact,
)


@dataclass(frozen=True, slots=True)
class _OperationalSources:
    references: tuple[LifecycleObjectReference, ...]
    composite: VerifiedCompositeOperationalManifest
    daily: VerifiedPhaseDDailyDecisionArtifact
    supplemental: VerifiedSupplementalResearchEvidence


class PlatformResearchStageHandler:
    """Invoke the existing OperationalResearchRunner with command-bound config."""

    stage_name = LifecycleStageName.PLATFORM_RESEARCH
    mutation_kind = StageMutationKind.IDEMPOTENT_MUTATION

    def __init__(
        self,
        *,
        configuration: ResearchPipelineConfig,
        output_root: Path,
    ) -> None:
        if not isinstance(configuration, ResearchPipelineConfig):
            raise TypeError("configuration must be a ResearchPipelineConfig")
        if not isinstance(output_root, Path):
            raise TypeError("output_root must be a Path")
        self._configuration = configuration
        self._output_root = output_root.resolve()

    def recover(self, context: LifecycleStageContext) -> StageExecutionResult | None:
        sources = self._load_sources(context)
        self._validate_command_bindings(context)
        inputs = adapt_verified_composite_operational_inputs(
            composite=sources.composite,
            daily=sources.daily,
            supplemental=sources.supplemental,
        )
        expected = PlatformResearchRunner().compute(
            inputs=inputs,
            configuration=self._configuration,
            code_revision=lifecycle_code_revision(context.run),
        )
        path = self._output_root / str(expected.artifact_id)
        if not path.exists():
            return None
        verified = load_verified_research_artifact(path)
        if verified.artifact != expected:
            raise ValueError("recovered Research Layer Artifact semantic mismatch")
        return self._result(context, sources.references, verified)

    def execute(self, context: LifecycleStageContext) -> StageExecutionResult:
        sources = self._load_sources(context)
        self._validate_command_bindings(context)
        verified = OperationalResearchRunner().run(
            composite_artifact_path=sources.composite.root,
            daily_artifact_path=sources.daily.root,
            supplemental_artifact_path=sources.supplemental.root,
            configuration=self._configuration,
            output_root=self._output_root,
            code_revision=lifecycle_code_revision(context.run),
        )
        return self._result(context, sources.references, verified)

    def _validate_command_bindings(self, context: LifecycleStageContext) -> None:
        require_configuration_binding(
            context.run,
            self._configuration,
            configuration_version=ResearchPipelineConfig.SCHEMA_VERSION,
        )
        for configuration in (
            self._configuration.market_regime,
            self._configuration.theme_rotation,
            self._configuration.capital_evolution,
            self._configuration.candidate_discovery,
        ):
            require_model_binding(
                context.run,
                model_id=configuration.model_id,
                model_version=configuration.model_version,
            )

    @staticmethod
    def _load_sources(context: LifecycleStageContext) -> _OperationalSources:
        composite_reference = require_single_reference(context, LifecycleObjectType.COMPOSITE_OPERATIONAL_MANIFEST)
        daily_reference = require_single_reference(context, LifecycleObjectType.DAILY_DECISION_ARTIFACT)
        supplemental_reference = require_single_reference(context, LifecycleObjectType.SUPPLEMENTAL_RESEARCH_EVIDENCE)
        source_references = references_for_type(context, LifecycleObjectType.SOURCE_MANIFEST)
        composite = load_verified_composite_operational_manifest(reference_path(composite_reference))
        daily = load_verified_daily_decision_artifact(reference_path(daily_reference))
        supplemental = load_verified_supplemental_research_evidence(reference_path(supplemental_reference))
        expected = (
            (
                str(composite.manifest.manifest_id),
                composite.manifest.content_hash,
                composite_reference,
            ),
            (
                daily.artifact_id,
                daily.bundle.content_hash,
                daily_reference,
            ),
            (
                str(supplemental.bundle.bundle_id),
                supplemental.bundle.content_hash,
                supplemental_reference,
            ),
        )
        if any(
            str(reference.object_id) != str(object_id) or reference.content_hash != content_hash
            for object_id, content_hash, reference in expected
        ):
            raise ValueError("operational research input reference mismatch")
        expected_sources = {
            (
                str(daily.bundle.source_manifest.source_manifest_id),
                daily.bundle.source_manifest.content_hash,
            ),
            (
                str(supplemental.bundle.source_manifest.source_manifest_id),
                supplemental.bundle.source_manifest.content_hash,
            ),
        }
        actual_sources = {(str(reference.object_id), reference.content_hash) for reference in source_references}
        if actual_sources != expected_sources:
            raise ValueError("SourceManifest references do not cover operational research inputs")
        return _OperationalSources(
            references=ordered_references(
                (
                    composite_reference,
                    daily_reference,
                    supplemental_reference,
                    *source_references,
                )
            ),
            composite=composite,
            daily=daily,
            supplemental=supplemental,
        )

    def _result(
        self,
        context: LifecycleStageContext,
        inputs: tuple[LifecycleObjectReference, ...],
        verified: VerifiedResearchLayerArtifact,
    ) -> StageExecutionResult:
        artifact = verified.artifact
        output = output_reference(
            object_type=LifecycleObjectType.PLATFORM_RESEARCH_ARTIFACT,
            object_id=artifact.artifact_id,
            content_hash=artifact.content_hash,
            reader_kind=LifecycleReaderKind.PLATFORM_RESEARCH_ARTIFACT_READER,
            locator=verified.root,
            available_at=artifact.envelope.created_at,
        )
        model_versions = tuple(
            sorted(
                (
                    (str(configuration.model_id), configuration.model_version)
                    for configuration in (
                        self._configuration.market_regime,
                        self._configuration.theme_rotation,
                        self._configuration.capital_evolution,
                        self._configuration.candidate_discovery,
                    )
                )
            )
        )
        return StageExecutionResult(
            stage_status=LifecycleStageStatus.COMPLETED,
            run_status=LifecycleRunStatus.RUNNING,
            input_references=inputs,
            output_references=(output,),
            model_versions=model_versions,
            configuration_hashes=(self._configuration.configuration_hash,),
            reason_codes=tuple(
                sorted(
                    {
                        "PLATFORM_RESEARCH_ARTIFACT_VERIFIED",
                        f"RESEARCH_STATUS_{artifact.research_status.value}",
                        *artifact.reason_codes,
                    }
                )
            ),
            blocker_reason=None,
        )
