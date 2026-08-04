"""Signal, path-forecast, and fail-closed Entry lifecycle adapters."""

from __future__ import annotations

import json
from enum import Enum
from pathlib import Path
from typing import TypeAlias

from market_regime_alpha.application.canonical_lifecycle.contracts import (
    LifecycleConfigurationKind,
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
from market_regime_alpha.forecasting.sample_provider import (
    PathForecastSampleBatch,
    PathForecastSampleProvider,
    UnavailablePathForecastSampleProvider,
)
from market_regime_alpha.features.materialization_v2 import (
    VerifiedFeatureBundleV2,
    load_verified_feature_bundle_v2,
)
from market_regime_alpha.features.spine import FeatureSetConfiguration
from market_regime_alpha.data.trading_calendar import TradingCalendarArtifact
from market_regime_alpha.core.time import DecisionTime
from market_regime_alpha.market_data import (
    VerifiedMarketDataDataset,
    load_verified_market_data_dataset,
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
from market_regime_alpha.signals.input_assembly import (
    SignalInputAssembler,
    SignalInputMappingConfiguration,
)
from market_regime_alpha.signals.v2 import (
    SignalRunArtifactV2,
    VerifiedSignalRunArtifactV2,
    load_verified_signal_run_v2,
    publish_signal_run_v2,
    run_signal_model_v2,
)
from market_regime_alpha.signals.candidate_view import (
    CandidateFeatureView,
    publish_candidate_feature_view,
)
from market_regime_alpha.signals.decimal_model import SignalModelConfigurationV2
from market_regime_alpha.signals.input_v3 import (
    SignalInputAssemblerV3,
    SignalInputMappingConfigurationV2,
)
from market_regime_alpha.signals.policies import (
    SignalFactorFreshnessPolicy,
    SignalFactorRequirementPolicy,
)
from market_regime_alpha.signals.v3 import (
    SignalRunArtifactV3,
    VerifiedSignalRunArtifactV3,
    load_verified_signal_run_v3,
    publish_signal_run_v3,
    run_signal_model_v3,
)


_H6_SIGNAL_LIMITATION = "H6_SIGNAL_FACTOR_INPUTS_NOT_AVAILABLE"
_H6_PATH_LIMITATION = "H6_PATH_FORECAST_SAMPLES_NOT_AVAILABLE"
_VerifiedSignalRun: TypeAlias = VerifiedSignalRunArtifact | VerifiedSignalRunArtifactV2 | VerifiedSignalRunArtifactV3
_SignalRun: TypeAlias = SignalRunArtifact | SignalRunArtifactV2 | SignalRunArtifactV3
_HistoricalSignalRun: TypeAlias = SignalRunArtifact | SignalRunArtifactV2


class HistoricalSignalProductionContext(str, Enum):
    LEGACY_REPLAY = "LEGACY_REPLAY"
    HISTORICAL_COMPATIBILITY_TEST = "HISTORICAL_COMPATIBILITY_TEST"


class SignalStageHandler:
    """Canonical runtime Signal authority; V1/V2 production is disabled."""

    stage_name = LifecycleStageName.SIGNAL
    mutation_kind = StageMutationKind.IDEMPOTENT_MUTATION

    def __init__(
        self,
        *,
        configuration: SignalModelConfigurationV2,
        output_root: Path,
        mapping_configuration: SignalInputMappingConfigurationV2,
        feature_set_configuration: FeatureSetConfiguration,
        requirement_policy: SignalFactorRequirementPolicy,
        freshness_policy: SignalFactorFreshnessPolicy,
    ) -> None:
        if not isinstance(configuration, SignalModelConfigurationV2):
            raise TypeError("Canonical Signal requires SignalModelConfigurationV2")
        if not isinstance(mapping_configuration, SignalInputMappingConfigurationV2):
            raise TypeError("Canonical Signal requires SignalInputMappingConfigurationV2")
        if not isinstance(feature_set_configuration, FeatureSetConfiguration):
            raise TypeError("Canonical Signal requires FeatureSetConfiguration")
        if not isinstance(requirement_policy, SignalFactorRequirementPolicy):
            raise TypeError("Canonical Signal requires SignalFactorRequirementPolicy")
        if not isinstance(freshness_policy, SignalFactorFreshnessPolicy):
            raise TypeError("Canonical Signal requires SignalFactorFreshnessPolicy")
        mapping_configuration.validate_requirement_policy(requirement_policy)
        self._configuration = configuration
        self._mapping_configuration = mapping_configuration
        self._feature_set_configuration = feature_set_configuration
        self._requirement_policy = requirement_policy
        self._freshness_policy = freshness_policy
        self._output_root = output_root.resolve()

    def recover(self, context: LifecycleStageContext) -> StageExecutionResult | None:
        inputs = self._inputs(context)
        artifact = self._compute(context, *inputs[1::2])
        signal_path = self._output_root / str(artifact.artifact_id)
        view_path = self._output_root / "candidate-feature-views" / str(artifact.candidate_feature_view.view_id)
        if not signal_path.exists() or not view_path.exists():
            return None
        verified = load_verified_signal_run_v3(signal_path)
        if verified.artifact != artifact:
            raise ValueError("recovered Canonical Signal V3 semantic mismatch")
        return self._result(inputs=inputs[::2], verified=verified, view_path=view_path)

    def execute(self, context: LifecycleStageContext) -> StageExecutionResult:
        inputs = self._inputs(context)
        artifact = self._compute(context, *inputs[1::2])
        view_path = publish_candidate_feature_view(
            root=self._output_root / "candidate-feature-views",
            view=artifact.candidate_feature_view,
        )
        signal_path = publish_signal_run_v3(root=self._output_root, artifact=artifact)
        verified = load_verified_signal_run_v3(signal_path)
        if verified.artifact != artifact:
            raise ValueError("published Canonical Signal V3 semantic mismatch")
        return self._result(inputs=inputs[::2], verified=verified, view_path=view_path)

    def _inputs(
        self, context: LifecycleStageContext
    ) -> tuple[
        LifecycleObjectReference,
        VerifiedResearchLayerArtifact,
        LifecycleObjectReference,
        VerifiedFeatureBundleV2,
        LifecycleObjectReference,
        VerifiedMarketDataDataset,
        LifecycleObjectReference,
        TradingCalendarArtifact,
    ]:
        self._validate_command_bindings(context)
        research_reference, research = _load_research(context)
        feature_reference = require_single_reference(context, LifecycleObjectType.FEATURE_BUNDLE)
        feature_path = reference_path(feature_reference)
        feature_bundle = load_verified_feature_bundle_v2(
            feature_path,
            artifact_root=feature_path.parent.parent / "feature-artifacts",
        )
        if (
            str(feature_bundle.artifact.bundle_id) != str(feature_reference.object_id)
            or feature_bundle.artifact.content_hash != feature_reference.content_hash
        ):
            raise ValueError("Feature Bundle lifecycle reference mismatch")
        dataset_reference = require_single_reference(context, LifecycleObjectType.MARKET_DATA_DATASET)
        dataset = load_verified_market_data_dataset(reference_path(dataset_reference))
        if (
            str(dataset.artifact.dataset_id) != str(dataset_reference.object_id)
            or dataset.artifact.content_hash != dataset_reference.content_hash
        ):
            raise ValueError("Market Data Dataset lifecycle reference mismatch")
        calendar_reference = require_single_reference(context, LifecycleObjectType.TRADING_CALENDAR_ARTIFACT)
        calendar = _load_trading_calendar(calendar_reference)
        return (
            research_reference,
            research,
            feature_reference,
            feature_bundle,
            dataset_reference,
            dataset,
            calendar_reference,
            calendar,
        )

    def _validate_command_bindings(self, context: LifecycleStageContext) -> None:
        for configuration, kind, version in (
            (
                self._configuration,
                LifecycleConfigurationKind.SIGNAL_MODEL,
                self._configuration.configuration_version,
            ),
            (
                self._mapping_configuration,
                LifecycleConfigurationKind.SIGNAL_INPUT_MAPPING,
                self._mapping_configuration.configuration_version,
            ),
            (
                self._feature_set_configuration,
                LifecycleConfigurationKind.FEATURE_SET,
                self._feature_set_configuration.feature_set_version,
            ),
            (
                self._requirement_policy,
                LifecycleConfigurationKind.SIGNAL_FACTOR_REQUIREMENT,
                self._requirement_policy.policy_version,
            ),
            (
                self._freshness_policy,
                LifecycleConfigurationKind.SIGNAL_FACTOR_FRESHNESS,
                self._freshness_policy.policy_version,
            ),
        ):
            require_configuration_binding(
                context.run,
                configuration,
                configuration_kind=kind,
                configuration_version=version,
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
        feature_bundle: VerifiedFeatureBundleV2,
        dataset: VerifiedMarketDataDataset,
        trading_calendar: TradingCalendarArtifact,
    ) -> SignalRunArtifactV3:
        if feature_bundle.artifact.feature_set != self._feature_set_configuration:
            raise ValueError("Feature Bundle does not match command Feature Set")
        if (
            trading_calendar.artifact_id != self._freshness_policy.trading_calendar_id
            or trading_calendar.content_hash != self._freshness_policy.trading_calendar_hash
        ):
            raise ValueError("TradingCalendar does not match Signal Freshness Policy")
        candidate_set = research.artifact.candidate_set
        canonical_decision_time = DecisionTime(feature_bundle.artifact.decision_time)
        view = CandidateFeatureView.create(
            candidate_set=candidate_set,
            feature_bundle=feature_bundle,
            verified_dataset=dataset,
            minimum_data_eligibility=candidate_set.envelope.data_eligibility,
        )
        observations = SignalInputAssemblerV3().assemble(
            candidate_set=candidate_set,
            candidate_feature_view=view,
            feature_bundle=feature_bundle,
            verified_dataset=dataset,
            mapping_configuration=self._mapping_configuration,
            requirement_policy=self._requirement_policy,
            freshness_policy=self._freshness_policy,
            trading_calendar=trading_calendar,
            decision_time=canonical_decision_time,
        )
        return run_signal_model_v3(
            candidate_set=candidate_set,
            candidate_feature_view=view,
            feature_bundle=feature_bundle,
            verified_dataset=dataset,
            mapping_configuration=self._mapping_configuration,
            requirement_policy=self._requirement_policy,
            freshness_policy=self._freshness_policy,
            trading_calendar=trading_calendar,
            signal_configuration=self._configuration,
            observations=observations,
            decision_time=canonical_decision_time,
            created_at=research.artifact.envelope.created_at,
            code_revision=lifecycle_code_revision(context.run),
        )

    def _result(
        self,
        *,
        inputs: tuple[LifecycleObjectReference, ...],
        verified: VerifiedSignalRunArtifactV3,
        view_path: Path,
    ) -> StageExecutionResult:
        artifact = verified.artifact
        signal_output = output_reference(
            object_type=LifecycleObjectType.SIGNAL_ARTIFACT,
            object_id=artifact.artifact_id,
            content_hash=artifact.envelope.content_hash,
            reader_kind=LifecycleReaderKind.SIGNAL_ARTIFACT_READER,
            locator=verified.root,
            available_at=artifact.envelope.created_at,
        )
        view = artifact.candidate_feature_view
        research_inputs = tuple(item for item in inputs if item.object_type is LifecycleObjectType.PLATFORM_RESEARCH_ARTIFACT)
        if len(research_inputs) != 1:
            raise ValueError("Canonical Signal result requires one research input")
        research_input = research_inputs[0]
        candidate_input = output_reference(
            object_type=LifecycleObjectType.CANDIDATE_SET,
            object_id=artifact.candidate_set.envelope.artifact_id,
            content_hash=artifact.candidate_set.envelope.content_hash,
            reader_kind=LifecycleReaderKind.CANDIDATE_SET_READER,
            locator=reference_path(research_input),
            available_at=artifact.candidate_set.envelope.created_at,
        )
        view_output = output_reference(
            object_type=LifecycleObjectType.CANDIDATE_FEATURE_VIEW,
            object_id=view.view_id,
            content_hash=view.content_hash,
            reader_kind=LifecycleReaderKind.CANDIDATE_FEATURE_VIEW_READER,
            locator=view_path,
            available_at=artifact.envelope.created_at,
        )
        reasons = {
            "CANONICAL_SIGNAL_V3_ARTIFACT_VERIFIED",
            "CANDIDATE_FEATURE_VIEW_VERIFIED",
            *(reason for snapshot in artifact.snapshots for reason in snapshot.reason_codes),
        }
        if any(item.signal_state is SignalState.DATA_INSUFFICIENT for item in artifact.snapshots) or not artifact.snapshots:
            reasons.add("SIGNAL_DATA_INSUFFICIENT")
        return StageExecutionResult(
            stage_status=LifecycleStageStatus.COMPLETED,
            run_status=LifecycleRunStatus.RUNNING,
            input_references=ordered_references((*inputs, candidate_input)),
            output_references=ordered_references((signal_output, view_output)),
            model_versions=((str(self._configuration.model_id), self._configuration.model_version),),
            configuration_hashes=tuple(
                sorted(
                    {
                        self._configuration.configuration_hash,
                        self._mapping_configuration.configuration_hash,
                        self._feature_set_configuration.content_hash,
                        self._requirement_policy.policy_hash,
                        self._freshness_policy.policy_hash,
                    }
                )
            ),
            reason_codes=tuple(sorted(reasons)),
            blocker_reason=None,
        )


class HistoricalCompatibilitySignalStageHandler:
    """Run V2 from a Feature Bundle, retaining only an explicit V1 fallback."""

    stage_name = LifecycleStageName.SIGNAL
    mutation_kind = StageMutationKind.IDEMPOTENT_MUTATION

    def __init__(
        self,
        *,
        production_context: HistoricalSignalProductionContext,
        configuration: SignalModelConfig,
        output_root: Path,
        mapping_configuration: SignalInputMappingConfiguration | None = None,
        feature_set_configuration: FeatureSetConfiguration | None = None,
    ) -> None:
        if not isinstance(production_context, HistoricalSignalProductionContext):
            raise TypeError("historical Signal production requires an explicit compatibility context")
        if not isinstance(configuration, SignalModelConfig):
            raise TypeError("configuration must be a SignalModelConfig")
        if not isinstance(output_root, Path):
            raise TypeError("output_root must be a Path")
        self._configuration = configuration
        self._production_context = production_context
        self._output_root = output_root.resolve()
        if mapping_configuration is not None and not isinstance(mapping_configuration, SignalInputMappingConfiguration):
            raise TypeError("mapping_configuration must be a SignalInputMappingConfiguration")
        self._mapping_configuration = mapping_configuration
        if feature_set_configuration is not None and not isinstance(feature_set_configuration, FeatureSetConfiguration):
            raise TypeError("feature_set_configuration must be a FeatureSetConfiguration")
        self._feature_set_configuration = feature_set_configuration

    def recover(self, context: LifecycleStageContext) -> StageExecutionResult | None:
        research_reference, research = _load_research(context)
        self._validate_command_bindings(context)
        feature_reference, feature_bundle, dataset_reference, dataset = self._optional_feature_inputs(context)
        expected = self._compute(context, research, feature_bundle, dataset)
        path = self._output_root / str(expected.artifact_id)
        if not path.exists():
            return None
        verified = _load_signal_package(path)
        if verified.artifact != expected:
            raise ValueError("recovered Signal Artifact semantic mismatch")
        return self._result(research_reference, feature_reference, dataset_reference, verified)

    def execute(self, context: LifecycleStageContext) -> StageExecutionResult:
        research_reference, research = _load_research(context)
        self._validate_command_bindings(context)
        feature_reference, feature_bundle, dataset_reference, dataset = self._optional_feature_inputs(context)
        artifact = self._compute(context, research, feature_bundle, dataset)
        path = (
            publish_signal_run_v2(root=self._output_root, artifact=artifact)
            if isinstance(artifact, SignalRunArtifactV2)
            else publish_signal_run(root=self._output_root, artifact=artifact)
        )
        verified = _load_signal_package(path)
        if verified.artifact != artifact:
            raise ValueError("published Signal Artifact semantic mismatch")
        return self._result(research_reference, feature_reference, dataset_reference, verified)

    def _validate_command_bindings(self, context: LifecycleStageContext) -> None:
        require_configuration_binding(
            context.run,
            self._configuration,
            configuration_kind=LifecycleConfigurationKind.SIGNAL_MODEL,
            configuration_version=self._configuration.schema_version,
        )
        require_model_binding(
            context.run,
            model_id=self._configuration.model_id,
            model_version=self._configuration.model_version,
        )
        if self._mapping_configuration is not None:
            require_configuration_binding(
                context.run,
                self._mapping_configuration,
                configuration_kind=LifecycleConfigurationKind.SIGNAL_INPUT_MAPPING,
                configuration_version=(self._mapping_configuration.configuration_version),
            )
        if self._feature_set_configuration is not None:
            require_configuration_binding(
                context.run,
                self._feature_set_configuration,
                configuration_kind=LifecycleConfigurationKind.FEATURE_SET,
                configuration_version=(self._feature_set_configuration.feature_set_version),
            )

    def _compute(
        self,
        context: LifecycleStageContext,
        research: VerifiedResearchLayerArtifact,
        feature_bundle: VerifiedFeatureBundleV2 | None,
        verified_dataset: VerifiedMarketDataDataset | None,
    ) -> _HistoricalSignalRun:
        if feature_bundle is not None:
            if verified_dataset is None:
                raise ValueError("Feature-derived Signal requires Market Data Dataset")
            if self._mapping_configuration is None or (self._feature_set_configuration is None):
                raise ValueError("Feature-derived Signal requires FEATURE_SET and SIGNAL_INPUT_MAPPING configurations")
            if feature_bundle.artifact.feature_set != self._feature_set_configuration:
                raise ValueError("Feature Bundle does not match command Feature Set")
            v2_observations = SignalInputAssembler().assemble(
                candidate_set=research.artifact.candidate_set,
                feature_bundle=feature_bundle,
                verified_dataset=verified_dataset,
                configuration=self._mapping_configuration,
                decision_time=research.artifact.envelope.decision_time,
            )
            return run_signal_model_v2(
                candidate_set=research.artifact.candidate_set,
                feature_bundle=feature_bundle,
                mapping_configuration=self._mapping_configuration,
                signal_configuration=self._configuration,
                observations=v2_observations,
                decision_time=research.artifact.envelope.decision_time,
                created_at=research.artifact.envelope.created_at,
                code_revision=lifecycle_code_revision(context.run),
            )
        if self._mapping_configuration is not None:
            raise ValueError("SIGNAL_INPUT_MAPPING cannot run without one FEATURE_BUNDLE input")
        if self._feature_set_configuration is not None:
            raise ValueError("FEATURE_SET cannot run without one FEATURE_BUNDLE input")
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
        feature_reference: LifecycleObjectReference | None,
        dataset_reference: LifecycleObjectReference | None,
        verified: _VerifiedSignalRun,
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
        is_v2 = isinstance(artifact, SignalRunArtifactV2)
        if any(item.signal_state is SignalState.DATA_INSUFFICIENT for item in artifact.snapshots):
            reasons.add("SIGNAL_DATA_INSUFFICIENT")
            if not is_v2:
                reasons.add(_H6_SIGNAL_LIMITATION)
        if not artifact.snapshots:
            reasons.update(
                {
                    "NO_SELECTED_SIGNAL_SNAPSHOTS",
                    "SIGNAL_DATA_INSUFFICIENT",
                }
            )
            if not is_v2:
                reasons.add(_H6_SIGNAL_LIMITATION)
        inputs: tuple[LifecycleObjectReference, ...]
        if feature_reference is None:
            inputs = (research_reference,)
        else:
            if dataset_reference is None:
                raise ValueError("Feature-derived Signal result lacks Dataset input")
            inputs = ordered_references((research_reference, feature_reference, dataset_reference))
        configuration_hashes = {self._configuration.configuration_hash}
        model_versions = {(str(self._configuration.model_id), self._configuration.model_version)}
        if isinstance(artifact, SignalRunArtifactV2):
            configuration_hashes.add(artifact.mapping_configuration.configuration_hash)
            assert self._feature_set_configuration is not None
            configuration_hashes.add(self._feature_set_configuration.content_hash)
        return StageExecutionResult(
            stage_status=LifecycleStageStatus.COMPLETED,
            run_status=LifecycleRunStatus.RUNNING,
            input_references=inputs,
            output_references=(output,),
            model_versions=tuple(sorted(model_versions)),
            configuration_hashes=tuple(sorted(configuration_hashes)),
            reason_codes=tuple(sorted(reasons)),
            blocker_reason=None,
        )

    def _optional_feature_inputs(
        self, context: LifecycleStageContext
    ) -> tuple[
        LifecycleObjectReference | None,
        VerifiedFeatureBundleV2 | None,
        LifecycleObjectReference | None,
        VerifiedMarketDataDataset | None,
    ]:
        references = references_for_type(context, LifecycleObjectType.FEATURE_BUNDLE)
        if not references:
            return None, None, None, None
        if len(references) != 1:
            raise ValueError("lifecycle Signal stage requires one FEATURE_BUNDLE")
        reference = references[0]
        package = reference_path(reference)
        artifact_root = package.parent.parent / "feature-artifacts"
        verified = load_verified_feature_bundle_v2(package, artifact_root=artifact_root)
        if str(verified.artifact.bundle_id) != str(reference.object_id) or verified.artifact.content_hash != reference.content_hash:
            raise ValueError("Feature Bundle lifecycle reference mismatch")
        dataset_references = references_for_type(context, LifecycleObjectType.MARKET_DATA_DATASET)
        if len(dataset_references) != 1:
            raise ValueError("Feature-derived Signal requires one MARKET_DATA_DATASET")
        dataset_reference = dataset_references[0]
        dataset = load_verified_market_data_dataset(reference_path(dataset_reference))
        if (
            str(dataset.artifact.dataset_id) != str(dataset_reference.object_id)
            or dataset.artifact.content_hash != dataset_reference.content_hash
        ):
            raise ValueError("Market Data Dataset lifecycle reference mismatch")
        return reference, verified, dataset_reference, dataset


class PathForecastStageHandler:
    """Run one existing PathForecast per Signal snapshot, without fake samples."""

    stage_name = LifecycleStageName.PATH_FORECAST
    mutation_kind = StageMutationKind.IDEMPOTENT_MUTATION

    def __init__(
        self,
        *,
        configuration: PathForecastConfig,
        output_root: Path,
        sample_provider: PathForecastSampleProvider | None = None,
    ) -> None:
        if not isinstance(configuration, PathForecastConfig):
            raise TypeError("configuration must be a PathForecastConfig")
        if not isinstance(output_root, Path):
            raise TypeError("output_root must be a Path")
        self._configuration = configuration
        self._output_root = output_root.resolve()
        self._sample_provider = sample_provider if sample_provider is not None else UnavailablePathForecastSampleProvider()

    def recover(self, context: LifecycleStageContext) -> StageExecutionResult | None:
        signal_reference, signal = _load_signal(context)
        self._validate_command_bindings(context)
        computed = self._compute(context, signal)
        expected = tuple(item[0] for item in computed)
        verified: list[VerifiedPathForecastArtifact] = []
        for artifact in expected:
            path = self._output_root / str(artifact.artifact_id)
            if not path.exists():
                return None
            restored = load_verified_path_forecast(path)
            if restored.artifact != artifact:
                raise ValueError("recovered PathForecast semantic mismatch")
            verified.append(restored)
        return self._result(
            signal_reference,
            tuple(verified),
            tuple(item[1] for item in computed),
        )

    def execute(self, context: LifecycleStageContext) -> StageExecutionResult:
        signal_reference, signal = _load_signal(context)
        self._validate_command_bindings(context)
        computed = self._compute(context, signal)
        artifacts = tuple(item[0] for item in computed)
        verified: list[VerifiedPathForecastArtifact] = []
        for artifact in artifacts:
            path = publish_path_forecast(root=self._output_root, artifact=artifact)
            restored = load_verified_path_forecast(path)
            if restored.artifact != artifact:
                raise ValueError("published PathForecast semantic mismatch")
            verified.append(restored)
        return self._result(
            signal_reference,
            tuple(verified),
            tuple(item[1] for item in computed),
        )

    def _validate_command_bindings(self, context: LifecycleStageContext) -> None:
        require_configuration_binding(
            context.run,
            self._configuration,
            configuration_kind=LifecycleConfigurationKind.PATH_FORECAST,
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
        signal: _VerifiedSignalRun,
    ) -> tuple[tuple[PathForecastArtifact, PathForecastSampleBatch], ...]:
        artifact = signal.artifact
        return tuple(
            (
                build_path_forecast(
                    signal_snapshot=snapshot,
                    configuration=self._configuration,
                    samples=batch.samples,
                    decision_time=artifact.envelope.decision_time,
                    created_at=artifact.envelope.created_at,
                    code_revision=lifecycle_code_revision(context.run),
                ),
                batch,
            )
            for snapshot in artifact.snapshots
            for batch in (
                self._sample_provider.load_samples(
                    signal_snapshot=snapshot,
                    configuration=self._configuration,
                    decision_time=artifact.envelope.decision_time,
                ),
            )
        )

    def _result(
        self,
        signal_reference: LifecycleObjectReference,
        verified: tuple[VerifiedPathForecastArtifact, ...],
        sample_batches: tuple[PathForecastSampleBatch, ...],
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
            *(reason for batch in sample_batches for reason in batch.reason_codes),
            *(limitation for batch in sample_batches for limitation in batch.limitations),
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
) -> tuple[LifecycleObjectReference, _VerifiedSignalRun]:
    reference = require_single_reference(context, LifecycleObjectType.SIGNAL_ARTIFACT)
    verified = _load_signal_package(reference_path(reference))
    if str(verified.artifact.artifact_id) != str(reference.object_id) or verified.artifact.envelope.content_hash != reference.content_hash:
        raise ValueError("Signal Artifact reference mismatch")
    return reference, verified


def _load_signal_package(path: Path) -> _VerifiedSignalRun:
    manifest_path = path / "manifest.json"
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError("cannot inspect Signal Artifact package schema") from exc
    if not isinstance(payload, dict):
        raise ValueError("Signal Artifact manifest must be an object")
    if payload.get("schema_version") == "signal-run-package-v2":
        return load_verified_signal_run_v2(path)
    if payload.get("schema_version") == "signal-run-package-v3":
        return load_verified_signal_run_v3(path)
    return load_verified_signal_run(path)


def _load_trading_calendar(
    reference: LifecycleObjectReference,
) -> TradingCalendarArtifact:
    path = reference_path(reference)
    target = path / "artifact.json" if path.is_dir() else path
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("cannot read TradingCalendar Artifact") from exc
    if not isinstance(payload, dict):
        raise ValueError("TradingCalendar Artifact must be a JSON object")
    calendar = TradingCalendarArtifact.from_canonical_dict(payload)
    if str(calendar.artifact_id) != str(reference.object_id) or calendar.content_hash != reference.content_hash:
        raise ValueError("TradingCalendar Artifact reference mismatch")
    return calendar


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
