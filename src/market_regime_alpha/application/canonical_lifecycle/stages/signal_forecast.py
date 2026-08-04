"""Signal, path-forecast, and fail-closed Entry lifecycle adapters.

H6 currently contains candidate research and symbol capital proxies, but no
five-factor Signal observations or historical PathForecast samples.  These
adapters deliberately materialize that absence through the existing models'
``DATA_INSUFFICIENT`` states instead of substituting unrelated H6 fields.
"""

from __future__ import annotations

from pathlib import Path

from market_regime_alpha.application.canonical_lifecycle.contracts import (
    LifecycleObjectReference,
    LifecycleObjectType,
    LifecycleReaderKind,
)
from market_regime_alpha.application.canonical_lifecycle.input_manifest import (
    LifecycleAuthorityCeiling,
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
from market_regime_alpha.forecasting.artifact import (
    VerifiedPathForecastArtifact,
    load_verified_path_forecast,
    publish_path_forecast,
)
from market_regime_alpha.forecasting.contracts import (
    CalibrationStatus,
    PathForecastStatus,
)
from market_regime_alpha.forecasting.path import (
    PathForecastArtifact,
    PathForecastConfig,
    build_path_forecast,
)
from market_regime_alpha.research.platform_v2.reader import (
    VerifiedResearchLayerArtifact,
)
from market_regime_alpha.research.platform_v2.reader_registry import (
    load_verified_research_artifact,
)
from market_regime_alpha.signals.artifact import (
    VerifiedSignalRunArtifact,
    load_verified_signal_run,
    publish_signal_run,
)
from market_regime_alpha.signals.contracts import SignalState
from market_regime_alpha.signals.engine import (
    SIGNAL_OBSERVATION_SCHEMA,
    SignalModelConfig,
    SignalObservation,
    SignalRunArtifact,
    run_signal_model,
)


_H6_SIGNAL_LIMITATION = "H6_SIGNAL_FACTOR_INPUTS_NOT_AVAILABLE"
_H6_PATH_LIMITATION = "H6_PATH_FORECAST_SAMPLES_NOT_AVAILABLE"


class SignalStageHandler:
    """Run and publish the existing Signal model with explicit H6 missingness."""

    stage_name = LifecycleStageName.SIGNAL
    mutation_kind = StageMutationKind.IDEMPOTENT_MUTATION

    def __init__(
        self,
        *,
        configuration: SignalModelConfig,
        output_root: Path,
    ) -> None:
        if not isinstance(configuration, SignalModelConfig):
            raise TypeError("configuration must be a SignalModelConfig")
        if not isinstance(output_root, Path):
            raise TypeError("output_root must be a Path")
        self._configuration = configuration
        self._output_root = output_root.resolve()

    def recover(self, context: LifecycleStageContext) -> StageExecutionResult | None:
        research_reference, research = _load_research(context)
        self._validate_command_bindings(context)
        expected = self._compute(context, research)
        path = self._output_root / str(expected.artifact_id)
        if not path.exists():
            return None
        verified = load_verified_signal_run(path)
        if verified.artifact != expected:
            raise ValueError("recovered Signal Artifact semantic mismatch")
        return self._result(research_reference, verified)

    def execute(self, context: LifecycleStageContext) -> StageExecutionResult:
        research_reference, research = _load_research(context)
        self._validate_command_bindings(context)
        artifact = self._compute(context, research)
        path = publish_signal_run(root=self._output_root, artifact=artifact)
        verified = load_verified_signal_run(path)
        if verified.artifact != artifact:
            raise ValueError("published Signal Artifact semantic mismatch")
        return self._result(research_reference, verified)

    def _validate_command_bindings(self, context: LifecycleStageContext) -> None:
        require_configuration_binding(
            context.run,
            self._configuration,
            configuration_version=self._configuration.schema_version,
        )
        require_model_binding(
            context.run,
            model_id=self._configuration.model_id,
            model_version=self._configuration.model_version,
        )

    def _compute(
        self,
        context: LifecycleStageContext,
        research: VerifiedResearchLayerArtifact,
    ) -> SignalRunArtifact:
        artifact = research.artifact
        lineage = dict(
            zip(
                artifact.inputs.input_artifact_ids,
                artifact.inputs.input_content_hashes,
                strict=True,
            )
        )
        observations_by_symbol = {item.symbol: item for item in artifact.inputs.symbol_observations}
        observations: list[SignalObservation] = []
        for candidate in artifact.candidate_set.selected:
            source = observations_by_symbol.get(candidate.symbol)
            if source is None:
                raise ValueError("selected Candidate has no H6 symbol observation")
            source_hash = lineage.get(source.source_artifact_id)
            if source_hash is None:
                raise ValueError("H6 symbol observation has no content-hash lineage")
            observations.append(
                SignalObservation(
                    symbol=candidate.symbol,
                    source_artifact_id=source.source_artifact_id,
                    source_content_hash=source_hash,
                    availability_time=source.available_at,
                    price_action_return=None,
                    volume_ratio=None,
                    trend_return=None,
                    price_vs_vwap_return=None,
                    overheat_return=None,
                    reason_codes=(_H6_SIGNAL_LIMITATION,),
                    schema_version=SIGNAL_OBSERVATION_SCHEMA,
                )
            )
        return run_signal_model(
            candidate_set=artifact.candidate_set,
            configuration=self._configuration,
            observations=tuple(observations),
            decision_time=artifact.envelope.decision_time,
            created_at=artifact.envelope.created_at,
            code_revision=lifecycle_code_revision(context.run),
        )

    def _result(
        self,
        research_reference: LifecycleObjectReference,
        verified: VerifiedSignalRunArtifact,
    ) -> StageExecutionResult:
        artifact = verified.artifact
        output = output_reference(
            object_type=LifecycleObjectType.SIGNAL_ARTIFACT,
            object_id=artifact.artifact_id,
            content_hash=artifact.envelope.content_hash,
            reader_kind=LifecycleReaderKind.SIGNAL_ARTIFACT_READER,
            locator=verified.root,
            available_at=artifact.envelope.created_at,
        )
        reasons = {
            "SIGNAL_ARTIFACT_VERIFIED",
            *(reason_code for snapshot in artifact.snapshots for reason_code in snapshot.reason_codes),
        }
        if any(item.signal_state is SignalState.DATA_INSUFFICIENT for item in artifact.snapshots):
            reasons.update({_H6_SIGNAL_LIMITATION, "SIGNAL_DATA_INSUFFICIENT"})
        if not artifact.snapshots:
            reasons.update(
                {
                    _H6_SIGNAL_LIMITATION,
                    "NO_SELECTED_SIGNAL_SNAPSHOTS",
                    "SIGNAL_DATA_INSUFFICIENT",
                }
            )
        return StageExecutionResult(
            stage_status=LifecycleStageStatus.COMPLETED,
            run_status=LifecycleRunStatus.RUNNING,
            input_references=(research_reference,),
            output_references=(output,),
            model_versions=(
                (
                    str(self._configuration.model_id),
                    self._configuration.model_version,
                ),
            ),
            configuration_hashes=(self._configuration.configuration_hash,),
            reason_codes=tuple(sorted(reasons)),
            blocker_reason=None,
        )


class PathForecastStageHandler:
    """Run one existing PathForecast per Signal snapshot, without fake samples."""

    stage_name = LifecycleStageName.PATH_FORECAST
    mutation_kind = StageMutationKind.IDEMPOTENT_MUTATION

    def __init__(
        self,
        *,
        configuration: PathForecastConfig,
        output_root: Path,
    ) -> None:
        if not isinstance(configuration, PathForecastConfig):
            raise TypeError("configuration must be a PathForecastConfig")
        if not isinstance(output_root, Path):
            raise TypeError("output_root must be a Path")
        self._configuration = configuration
        self._output_root = output_root.resolve()

    def recover(self, context: LifecycleStageContext) -> StageExecutionResult | None:
        signal_reference, signal = _load_signal(context)
        self._validate_command_bindings(context)
        expected = self._compute(context, signal)
        verified: list[VerifiedPathForecastArtifact] = []
        for artifact in expected:
            path = self._output_root / str(artifact.artifact_id)
            if not path.exists():
                return None
            restored = load_verified_path_forecast(path)
            if restored.artifact != artifact:
                raise ValueError("recovered PathForecast semantic mismatch")
            verified.append(restored)
        return self._result(signal_reference, tuple(verified))

    def execute(self, context: LifecycleStageContext) -> StageExecutionResult:
        signal_reference, signal = _load_signal(context)
        self._validate_command_bindings(context)
        artifacts = self._compute(context, signal)
        verified: list[VerifiedPathForecastArtifact] = []
        for artifact in artifacts:
            path = publish_path_forecast(root=self._output_root, artifact=artifact)
            restored = load_verified_path_forecast(path)
            if restored.artifact != artifact:
                raise ValueError("published PathForecast semantic mismatch")
            verified.append(restored)
        return self._result(signal_reference, tuple(verified))

    def _validate_command_bindings(self, context: LifecycleStageContext) -> None:
        require_configuration_binding(
            context.run,
            self._configuration,
            configuration_version=self._configuration.schema_version,
        )
        require_model_binding(
            context.run,
            model_id=self._configuration.model_id,
            model_version=self._configuration.model_version,
        )

    def _compute(
        self,
        context: LifecycleStageContext,
        signal: VerifiedSignalRunArtifact,
    ) -> tuple[PathForecastArtifact, ...]:
        artifact = signal.artifact
        return tuple(
            build_path_forecast(
                signal_snapshot=snapshot,
                configuration=self._configuration,
                samples=(),
                decision_time=artifact.envelope.decision_time,
                created_at=artifact.envelope.created_at,
                code_revision=lifecycle_code_revision(context.run),
            )
            for snapshot in artifact.snapshots
        )

    def _result(
        self,
        signal_reference: LifecycleObjectReference,
        verified: tuple[VerifiedPathForecastArtifact, ...],
    ) -> StageExecutionResult:
        outputs = ordered_references(
            tuple(
                output_reference(
                    object_type=LifecycleObjectType.PATH_FORECAST_ARTIFACT,
                    object_id=item.artifact.artifact_id,
                    content_hash=item.artifact.forecast.envelope.content_hash,
                    reader_kind=LifecycleReaderKind.PATH_FORECAST_ARTIFACT_READER,
                    locator=item.root,
                    available_at=item.artifact.forecast.envelope.created_at,
                )
                for item in verified
            )
        )
        reasons = {
            "PATH_FORECAST_STAGE_COMPLETED",
            *(reason_code for item in verified for reason_code in item.artifact.forecast.reason_codes),
        }
        if not verified:
            reasons.update(
                {
                    _H6_PATH_LIMITATION,
                    "NO_SIGNAL_SNAPSHOTS_TO_FORECAST",
                    "PATH_FORECAST_DATA_INSUFFICIENT",
                }
            )
        if any(item.artifact.forecast.forecast_status is PathForecastStatus.DATA_INSUFFICIENT for item in verified):
            reasons.update({_H6_PATH_LIMITATION, "PATH_FORECAST_DATA_INSUFFICIENT"})
        return StageExecutionResult(
            stage_status=LifecycleStageStatus.COMPLETED,
            run_status=LifecycleRunStatus.RUNNING,
            input_references=(signal_reference,),
            output_references=outputs,
            model_versions=(
                (
                    str(self._configuration.model_id),
                    self._configuration.model_version,
                ),
            ),
            configuration_hashes=(self._configuration.configuration_hash,),
            reason_codes=tuple(sorted(reasons)),
            blocker_reason=None,
        )


class EntryAssessmentStageHandler:
    """Stop before Opportunity while the Entry model remains unvalidated."""

    stage_name = LifecycleStageName.ENTRY_ASSESSMENT
    mutation_kind = StageMutationKind.READ_ONLY

    def __init__(self, *, authority_ceiling: LifecycleAuthorityCeiling) -> None:
        if not isinstance(authority_ceiling, LifecycleAuthorityCeiling):
            raise TypeError("authority_ceiling must be a LifecycleAuthorityCeiling")
        self._authority_ceiling = authority_ceiling

    def recover(self, context: LifecycleStageContext) -> StageExecutionResult | None:
        return self.execute(context)

    def execute(self, context: LifecycleStageContext) -> StageExecutionResult:
        signal_reference, signal = _load_signal(context)
        forecast_references = references_for_type(context, LifecycleObjectType.PATH_FORECAST_ARTIFACT)
        forecasts = tuple(_load_forecast(reference) for reference in forecast_references)
        by_signal_id = {item.artifact.signal_snapshot.envelope.artifact_id: item for item in forecasts}
        expected_signal_ids = {item.envelope.artifact_id for item in signal.artifact.snapshots}
        if set(by_signal_id) != expected_signal_ids:
            raise ValueError("Entry assessment requires one PathForecast per Signal snapshot")
        if any(by_signal_id[snapshot.envelope.artifact_id].artifact.signal_snapshot != snapshot for snapshot in signal.artifact.snapshots):
            raise ValueError("PathForecast does not bind the exact Signal snapshot")

        reasons = {"ENTRY_MODEL_EMPIRICALLY_VALIDATED_FALSE"}
        if any(item.signal_state is SignalState.DATA_INSUFFICIENT for item in signal.artifact.snapshots):
            reasons.add("SIGNAL_DATA_INSUFFICIENT")
        if any(item.artifact.forecast.forecast_status is PathForecastStatus.DATA_INSUFFICIENT for item in forecasts):
            reasons.add("PATH_FORECAST_DATA_INSUFFICIENT")
        if any(item.artifact.forecast.calibration_status is not CalibrationStatus.CALIBRATED_EXPLORATORY for item in forecasts):
            reasons.add("PATH_FORECAST_NOT_CALIBRATED")
        if not signal.artifact.snapshots:
            reasons.update(
                {
                    "ENTRY_EVIDENCE_EMPTY",
                    "SIGNAL_DATA_INSUFFICIENT",
                    "PATH_FORECAST_DATA_INSUFFICIENT",
                    "PATH_FORECAST_NOT_CALIBRATED",
                }
            )
        if self._authority_ceiling.entry_model_empirically_validated:
            raise ValueError("current LifecycleAuthorityCeiling cannot grant Entry validation")
        inputs = ordered_references((signal_reference, *forecast_references))
        model_versions = {
            (
                str(signal.artifact.configuration.model_id),
                signal.artifact.configuration.model_version,
            ),
            *(
                (
                    str(item.artifact.configuration.model_id),
                    item.artifact.configuration.model_version,
                )
                for item in forecasts
            ),
        }
        configuration_hashes = {
            signal.artifact.configuration.configuration_hash,
            *(item.artifact.configuration.configuration_hash for item in forecasts),
        }
        return StageExecutionResult(
            stage_status=LifecycleStageStatus.BLOCKED,
            run_status=LifecycleRunStatus.BLOCKED_BY_MODEL_VALIDATION,
            input_references=inputs,
            output_references=(),
            model_versions=tuple(sorted(model_versions)),
            configuration_hashes=tuple(sorted(configuration_hashes)),
            reason_codes=tuple(sorted(reasons)),
            blocker_reason=("Entry cannot advance: the empirical Entry validation authority has not been established"),
        )


def _load_research(
    context: LifecycleStageContext,
) -> tuple[LifecycleObjectReference, VerifiedResearchLayerArtifact]:
    reference = require_single_reference(context, LifecycleObjectType.PLATFORM_RESEARCH_ARTIFACT)
    verified = load_verified_research_artifact(reference_path(reference))
    if str(verified.artifact.artifact_id) != str(reference.object_id) or verified.artifact.content_hash != reference.content_hash:
        raise ValueError("Research Layer Artifact reference mismatch")
    return reference, verified


def _load_signal(
    context: LifecycleStageContext,
) -> tuple[LifecycleObjectReference, VerifiedSignalRunArtifact]:
    reference = require_single_reference(context, LifecycleObjectType.SIGNAL_ARTIFACT)
    verified = load_verified_signal_run(reference_path(reference))
    if str(verified.artifact.artifact_id) != str(reference.object_id) or verified.artifact.envelope.content_hash != reference.content_hash:
        raise ValueError("Signal Artifact reference mismatch")
    return reference, verified


def _load_forecast(
    reference: LifecycleObjectReference,
) -> VerifiedPathForecastArtifact:
    verified = load_verified_path_forecast(reference_path(reference))
    if (
        str(verified.artifact.artifact_id) != str(reference.object_id)
        or verified.artifact.forecast.envelope.content_hash != reference.content_hash
    ):
        raise ValueError("PathForecast Artifact reference mismatch")
    return verified
