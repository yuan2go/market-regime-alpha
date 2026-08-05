"""Execute the Controlled Signal/Path/Entry segment in the canonical journal."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Callable

from market_regime_alpha.application.canonical_lifecycle._immutable_io import (
    publish_immutable_text,
)
from market_regime_alpha.application.canonical_lifecycle.commands import (
    CanonicalLifecycleCommand,
)
from market_regime_alpha.application.canonical_lifecycle.contracts import (
    LifecycleConfigurationKind,
    LifecycleConfigurationReference,
    LifecycleModelVersionReference,
    LifecycleObjectReference,
    LifecycleObjectType,
    LifecycleReaderKind,
)
from market_regime_alpha.application.canonical_lifecycle.input_manifest import (
    LifecycleAuthorityCeiling,
)
from market_regime_alpha.application.canonical_lifecycle.repositories import (
    LifecycleHistory,
    LifecycleRunNotFound,
)
from market_regime_alpha.application.canonical_lifecycle.runner import (
    AfterStageHook,
    CanonicalDecisionLifecycleRunner,
    LifecycleRunResult,
)
from market_regime_alpha.application.canonical_lifecycle.sqlite_repository import (
    SQLiteLifecycleRunRepository,
)
from market_regime_alpha.application.canonical_lifecycle.stages.contracts import (
    LifecycleStageContext,
    LifecycleStageHandler,
    StageExecutionResult,
    StageMutationKind,
)
from market_regime_alpha.application.canonical_lifecycle.stages.evidence import (
    ordered_references,
    output_reference,
    references_for_type,
)
from market_regime_alpha.application.canonical_lifecycle.stages.signal_forecast import (
    EntryAssessmentStageHandler,
    PathForecastStageHandler,
    SignalStageHandler,
)
from market_regime_alpha.application.canonical_lifecycle.stages.unavailable import (
    UnavailableLifecycleStageHandler,
)
from market_regime_alpha.application.canonical_lifecycle.states import (
    LIFECYCLE_STAGE_ORDER,
    LifecycleRunStatus,
    LifecycleRunType,
    LifecycleStageName,
    LifecycleStageStatus,
)
from market_regime_alpha.application.controlled_operation.journal import (
    ControlledOperationCommand,
)
from market_regime_alpha.application.controlled_operation.entry_blocker import (
    ControlledEntryAssessmentBlocker,
    publish_controlled_entry_blocker,
)
from market_regime_alpha.application.controlled_operation.input_artifacts import (
    load_controlled_source_manifest,
)
from market_regime_alpha.application.controlled_operation.research_runner import (
    VerifiedControlledResearchArtifact,
    load_verified_controlled_research_artifact,
)
from market_regime_alpha.application.controlled_operation.runtime_configuration import (
    ControlledOperationRuntimeConfiguration,
)
from market_regime_alpha.application.operational_research.supplemental_artifact import (
    load_verified_supplemental_research_evidence,
)
from market_regime_alpha.core.identity import ArtifactId, ModelId
from market_regime_alpha.data.trading_calendar import TradingCalendarArtifact
from market_regime_alpha.evidence.canonical import canonical_hash, canonical_json
from market_regime_alpha.features.materialization_v2 import VerifiedFeatureBundleV2
from market_regime_alpha.features.operational_overlay import (
    CandidateIntradayFeatureOverlay,
    StaticUniverseFeatureBundle,
)
from market_regime_alpha.forecasting.artifact import (
    VerifiedPathForecastArtifact,
    load_verified_path_forecast,
)
from market_regime_alpha.market_data.artifacts import VerifiedMarketDataDataset
from market_regime_alpha.research.candidate_discovery.contracts import CandidateSet
from market_regime_alpha.signals.candidate_view_v2 import (
    CandidateFeatureViewV2,
    load_candidate_feature_view_v2,
)
from market_regime_alpha.signals.v3 import (
    VerifiedSignalRunArtifactV3,
    load_verified_signal_run_v3,
)
from market_regime_alpha.universe.operational import OperationalUniverseArtifact


Clock = Callable[[], datetime]


class ControlledCanonicalDeadlineExceeded(RuntimeError):
    """The canonical child crossed the operation's immutable hard cutoff."""


@dataclass(frozen=True, slots=True)
class ControlledCanonicalLifecycleExecution:
    result: LifecycleRunResult
    history: LifecycleHistory
    database_path: Path
    signal: VerifiedSignalRunArtifactV3
    candidate_view: CandidateFeatureViewV2
    candidate_view_path: Path
    forecasts: tuple[VerifiedPathForecastArtifact, ...]
    entry_blocker: ControlledEntryAssessmentBlocker
    entry_blocker_path: Path
    stage_latencies_ms: tuple[tuple[LifecycleStageName, int], ...]


class _TimedStageHandler:
    def __init__(
        self,
        handler: LifecycleStageHandler,
        sink: dict[LifecycleStageName, int],
        *,
        clock: Clock,
        hard_cutoff: datetime,
    ) -> None:
        self._handler = handler
        self._sink = sink
        self.stage_name = handler.stage_name
        self.mutation_kind = handler.mutation_kind
        self._clock = clock
        self._hard_cutoff = hard_cutoff

    def recover(self, context: LifecycleStageContext) -> StageExecutionResult | None:
        self._require_before_cutoff()
        started = perf_counter()
        try:
            result = self._handler.recover(context)
        finally:
            self._record(started)
        self._require_before_cutoff()
        return result

    def execute(self, context: LifecycleStageContext) -> StageExecutionResult:
        self._require_before_cutoff()
        started = perf_counter()
        try:
            result = self._handler.execute(context)
        finally:
            self._record(started)
        self._require_before_cutoff()
        return result

    def _record(self, started: float) -> None:
        elapsed = int((perf_counter() - started) * 1000)
        self._sink[self.stage_name] = self._sink.get(self.stage_name, 0) + elapsed

    def _require_before_cutoff(self) -> None:
        if self._clock() > self._hard_cutoff:
            raise ControlledCanonicalDeadlineExceeded(
                "CONTROLLED_CANONICAL_HARD_CUTOFF_EXCEEDED"
            )


class _ControlledEvidenceStageHandler:
    stage_name = LifecycleStageName.VERIFY_COMPOSITE_EVIDENCE
    mutation_kind = StageMutationKind.READ_ONLY

    def recover(self, context: LifecycleStageContext) -> StageExecutionResult | None:
        return self.execute(context)

    def execute(self, context: LifecycleStageContext) -> StageExecutionResult:
        if context.run.input_manifest_id is not None:
            raise ValueError("Controlled canonical child requires explicit V2 inputs")
        required = {
            LifecycleObjectType.MARKET_DATA_DATASET,
            LifecycleObjectType.FEATURE_BUNDLE,
            LifecycleObjectType.OPERATIONAL_UNIVERSE,
            LifecycleObjectType.STATIC_UNIVERSE_FEATURE_BUNDLE,
            LifecycleObjectType.CANDIDATE_INTRADAY_FEATURE_OVERLAY,
            LifecycleObjectType.SOURCE_MANIFEST,
            LifecycleObjectType.SUPPLEMENTAL_RESEARCH_EVIDENCE,
            LifecycleObjectType.TRADING_CALENDAR_ARTIFACT,
        }
        present = {item.object_type for item in context.initial_references}
        if not required.issubset(present):
            raise ValueError("Controlled canonical child input authority is incomplete")
        return StageExecutionResult(
            stage_status=LifecycleStageStatus.COMPLETED,
            run_status=LifecycleRunStatus.RUNNING,
            input_references=context.initial_references,
            output_references=(),
            model_versions=(),
            configuration_hashes=(),
            reason_codes=("CONTROLLED_EXPLICIT_V2_EVIDENCE_VERIFIED",),
            blocker_reason=None,
        )


class _ControlledResearchReceiptStageHandler:
    stage_name = LifecycleStageName.PLATFORM_RESEARCH
    mutation_kind = StageMutationKind.READ_ONLY

    def __init__(
        self,
        *,
        research: VerifiedControlledResearchArtifact,
        input_references: tuple[LifecycleObjectReference, ...],
        available_at: datetime,
        configuration: ControlledOperationRuntimeConfiguration,
    ) -> None:
        self._research = research
        self._inputs = input_references
        self._available_at = available_at
        self._configuration = configuration

    def recover(self, context: LifecycleStageContext) -> StageExecutionResult | None:
        return self.execute(context)

    def execute(self, context: LifecycleStageContext) -> StageExecutionResult:
        restored = load_verified_controlled_research_artifact(self._research.root)
        if restored != self._research:
            raise ValueError("Controlled Platform Research Reader divergence")
        _require_traceable(context, self._inputs)
        artifact = restored.artifact
        candidate = artifact.candidate_set
        outputs = ordered_references(
            (
                output_reference(
                    object_type=(
                        LifecycleObjectType.CONTROLLED_PLATFORM_RESEARCH_ARTIFACT
                    ),
                    object_id=artifact.artifact_id,
                    content_hash=artifact.content_hash,
                    reader_kind=(
                        LifecycleReaderKind.CONTROLLED_PLATFORM_RESEARCH_ARTIFACT_READER
                    ),
                    locator=restored.root,
                    available_at=self._available_at,
                ),
                output_reference(
                    object_type=LifecycleObjectType.CANDIDATE_SET,
                    object_id=candidate.envelope.artifact_id,
                    content_hash=candidate.envelope.content_hash,
                    reader_kind=LifecycleReaderKind.CANDIDATE_SET_READER,
                    locator=restored.root,
                    available_at=self._available_at,
                ),
            )
        )
        models = tuple(
            sorted(
                (
                    (str(item.model_id), item.model_version)
                    for item in (
                        self._configuration.research.market_regime,
                        self._configuration.research.theme_rotation,
                        self._configuration.research.capital_evolution,
                        self._configuration.research.candidate_discovery,
                    )
                )
            )
        )
        return StageExecutionResult(
            stage_status=LifecycleStageStatus.COMPLETED,
            run_status=LifecycleRunStatus.RUNNING,
            input_references=self._inputs,
            output_references=outputs,
            model_versions=models,
            configuration_hashes=(
                self._configuration.research.configuration_hash,
            ),
            reason_codes=tuple(
                sorted(
                    {
                        "CONTROLLED_PLATFORM_RESEARCH_READER_VERIFIED",
                        *artifact.reason_codes,
                    }
                )
            ),
            blocker_reason=None,
        )


class _ControlledSignalStageHandler:
    stage_name = LifecycleStageName.SIGNAL
    mutation_kind = StageMutationKind.IDEMPOTENT_MUTATION

    def __init__(
        self,
        *,
        candidates: CandidateSet,
        static_bundle: StaticUniverseFeatureBundle,
        static_feature_bundle: VerifiedFeatureBundleV2,
        daily_dataset: VerifiedMarketDataDataset,
        intraday_overlay: CandidateIntradayFeatureOverlay,
        intraday_feature_bundle: VerifiedFeatureBundleV2,
        minute_dataset: VerifiedMarketDataDataset,
        trading_calendar: TradingCalendarArtifact,
        input_references: tuple[LifecycleObjectReference, ...],
        decision_time: datetime,
        code_revision: str,
        output_root: Path,
        available_at: datetime,
        configuration: ControlledOperationRuntimeConfiguration,
    ) -> None:
        self._candidates = candidates
        self._static_bundle = static_bundle
        self._static_feature_bundle = static_feature_bundle
        self._daily_dataset = daily_dataset
        self._intraday_overlay = intraday_overlay
        self._intraday_feature_bundle = intraday_feature_bundle
        self._minute_dataset = minute_dataset
        self._trading_calendar = trading_calendar
        self._inputs = input_references
        self._decision_time = decision_time
        self._code_revision = code_revision
        self._output_root = output_root
        self._available_at = available_at
        self._configuration = configuration

    def recover(self, context: LifecycleStageContext) -> StageExecutionResult | None:
        return None

    def execute(self, context: LifecycleStageContext) -> StageExecutionResult:
        candidate_refs = references_for_type(context, LifecycleObjectType.CANDIDATE_SET)
        if len(candidate_refs) != 1:
            raise ValueError("Controlled Signal requires one CandidateSet")
        candidate_ref = candidate_refs[0]
        if (
            str(candidate_ref.object_id) != str(self._candidates.envelope.artifact_id)
            or candidate_ref.content_hash != self._candidates.envelope.content_hash
        ):
            raise ValueError("Controlled Signal CandidateSet reference divergence")
        _require_traceable(context, self._inputs)
        output = SignalStageHandler(
            configuration=self._configuration.signal_model,
            output_root=self._output_root,
            mapping_configuration=self._configuration.signal_mapping,
            feature_set_configuration=self._configuration.static_feature_set,
            requirement_policy=self._configuration.signal_requirement,
            freshness_policy=self._configuration.signal_freshness,
        ).run_controlled_v2(
            candidate_set=self._candidates,
            static_bundle=self._static_bundle,
            static_feature_bundle=self._static_feature_bundle,
            daily_dataset=self._daily_dataset,
            intraday_overlay=self._intraday_overlay,
            intraday_feature_bundle=self._intraday_feature_bundle,
            minute_dataset=self._minute_dataset,
            trading_calendar=self._trading_calendar,
            decision_time=_decision_time(self._decision_time),
            created_at=self._decision_time,
            code_revision=self._code_revision,
        )
        inputs = ordered_references((candidate_ref, *self._inputs))
        outputs = ordered_references(
            (
                output_reference(
                    object_type=LifecycleObjectType.CANDIDATE_FEATURE_VIEW,
                    object_id=output.candidate_view.view_id,
                    content_hash=output.candidate_view.content_hash,
                    reader_kind=LifecycleReaderKind.CANDIDATE_FEATURE_VIEW_READER,
                    locator=output.candidate_view_path,
                    available_at=self._available_at,
                ),
                output_reference(
                    object_type=LifecycleObjectType.SIGNAL_ARTIFACT,
                    object_id=output.signal.artifact.artifact_id,
                    content_hash=output.signal.artifact.envelope.content_hash,
                    reader_kind=LifecycleReaderKind.SIGNAL_ARTIFACT_READER,
                    locator=output.signal.root,
                    available_at=self._available_at,
                ),
            )
        )
        return StageExecutionResult(
            stage_status=LifecycleStageStatus.COMPLETED,
            run_status=LifecycleRunStatus.RUNNING,
            input_references=inputs,
            output_references=outputs,
            model_versions=((
                str(self._configuration.signal_model.model_id),
                self._configuration.signal_model.model_version,
            ),),
            configuration_hashes=tuple(
                sorted(
                    {
                        self._configuration.signal_model.configuration_hash,
                        self._configuration.signal_mapping.configuration_hash,
                        self._configuration.static_feature_set.content_hash,
                        self._configuration.signal_requirement.policy_hash,
                        self._configuration.signal_freshness.policy_hash,
                    }
                )
            ),
            reason_codes=("CANONICAL_SIGNAL_V3_FROM_CANDIDATE_VIEW_V2",),
            blocker_reason=None,
        )


def run_controlled_canonical_lifecycle(
    *,
    parent_command: ControlledOperationCommand,
    run_root: Path,
    clock: Clock,
    available_at: datetime,
    configuration: ControlledOperationRuntimeConfiguration,
    runtime_configuration_path: Path,
    calendar: TradingCalendarArtifact,
    calendar_path: Path,
    universe: OperationalUniverseArtifact,
    universe_path: Path,
    daily_source_manifest_path: Path,
    supplemental_path: Path,
    research: VerifiedControlledResearchArtifact,
    daily_dataset: VerifiedMarketDataDataset,
    daily_dataset_path: Path,
    static_bundle: StaticUniverseFeatureBundle,
    static_bundle_path: Path,
    static_feature_bundle: VerifiedFeatureBundleV2,
    minute_dataset: VerifiedMarketDataDataset,
    minute_dataset_path: Path,
    intraday_feature_bundle: VerifiedFeatureBundleV2,
    overlay: CandidateIntradayFeatureOverlay,
    overlay_path: Path,
    hard_cutoff: datetime,
    after_stage_hook: AfterStageHook | None = None,
) -> ControlledCanonicalLifecycleExecution:
    """Run and durably journal the real canonical stage graph through Entry."""

    source_manifest = load_controlled_source_manifest(daily_source_manifest_path)
    supplemental = load_verified_supplemental_research_evidence(supplemental_path)
    initial = ordered_references(
        (
            output_reference(
                object_type=LifecycleObjectType.OPERATIONAL_UNIVERSE,
                object_id=ArtifactId(str(universe.universe_id)),
                content_hash=universe.content_hash,
                reader_kind=LifecycleReaderKind.OPERATIONAL_UNIVERSE_READER,
                locator=universe_path,
                available_at=available_at,
            ),
            output_reference(
                object_type=LifecycleObjectType.STATIC_UNIVERSE_FEATURE_BUNDLE,
                object_id=static_bundle.artifact_id,
                content_hash=static_bundle.content_hash,
                reader_kind=(
                    LifecycleReaderKind.STATIC_UNIVERSE_FEATURE_BUNDLE_READER
                ),
                locator=static_bundle_path,
                available_at=available_at,
            ),
            output_reference(
                object_type=LifecycleObjectType.CANDIDATE_INTRADAY_FEATURE_OVERLAY,
                object_id=overlay.artifact_id,
                content_hash=overlay.content_hash,
                reader_kind=(
                    LifecycleReaderKind.CANDIDATE_INTRADAY_FEATURE_OVERLAY_READER
                ),
                locator=overlay_path,
                available_at=available_at,
            ),
            output_reference(
                object_type=LifecycleObjectType.MARKET_DATA_DATASET,
                object_id=ArtifactId(str(daily_dataset.artifact.dataset_id)),
                content_hash=daily_dataset.artifact.content_hash,
                reader_kind=LifecycleReaderKind.MARKET_DATA_DATASET_READER,
                locator=daily_dataset_path,
                available_at=available_at,
            ),
            output_reference(
                object_type=LifecycleObjectType.MARKET_DATA_DATASET,
                object_id=ArtifactId(str(minute_dataset.artifact.dataset_id)),
                content_hash=minute_dataset.artifact.content_hash,
                reader_kind=LifecycleReaderKind.MARKET_DATA_DATASET_READER,
                locator=minute_dataset_path,
                available_at=available_at,
            ),
            output_reference(
                object_type=LifecycleObjectType.FEATURE_BUNDLE,
                object_id=static_feature_bundle.artifact.bundle_id,
                content_hash=static_feature_bundle.artifact.content_hash,
                reader_kind=LifecycleReaderKind.FEATURE_BUNDLE_READER,
                locator=static_feature_bundle.root,
                available_at=available_at,
            ),
            output_reference(
                object_type=LifecycleObjectType.FEATURE_BUNDLE,
                object_id=intraday_feature_bundle.artifact.bundle_id,
                content_hash=intraday_feature_bundle.artifact.content_hash,
                reader_kind=LifecycleReaderKind.FEATURE_BUNDLE_READER,
                locator=intraday_feature_bundle.root,
                available_at=available_at,
            ),
            output_reference(
                object_type=LifecycleObjectType.SOURCE_MANIFEST,
                object_id=source_manifest.source_manifest_id,
                content_hash=source_manifest.content_hash,
                reader_kind=LifecycleReaderKind.SOURCE_MANIFEST_READER,
                locator=daily_source_manifest_path,
                available_at=available_at,
            ),
            output_reference(
                object_type=LifecycleObjectType.SUPPLEMENTAL_RESEARCH_EVIDENCE,
                object_id=supplemental.bundle.bundle_id,
                content_hash=supplemental.bundle.content_hash,
                reader_kind=(
                    LifecycleReaderKind.SUPPLEMENTAL_RESEARCH_EVIDENCE_READER
                ),
                locator=supplemental_path,
                available_at=available_at,
            ),
            output_reference(
                object_type=LifecycleObjectType.TRADING_CALENDAR_ARTIFACT,
                object_id=calendar.artifact_id,
                content_hash=calendar.content_hash,
                reader_kind=LifecycleReaderKind.TRADING_CALENDAR_ARTIFACT_READER,
                locator=calendar_path,
                available_at=available_at,
            ),
        )
    )
    canonical_root = run_root / "canonical-lifecycle"
    configuration_refs = _configuration_references(
        configuration=configuration,
        runtime_configuration_path=runtime_configuration_path,
        root=canonical_root / "configurations",
    )
    model_refs = _model_references(configuration)
    command = CanonicalLifecycleCommand(
        run_type=LifecycleRunType.CANONICAL_DECISION_LIFECYCLE,
        decision_date=parent_command.decision_date,
        as_of_time=parent_command.decision_time,
        idempotency_key=f"{parent_command.idempotency_key}:canonical-controlled-v2",
        input_manifest_id=None,
        input_content_hash=None,
        input_manifest_locator=None,
        input_references=initial,
        configuration_references=configuration_refs,
        model_references=model_refs,
        stop_after_stage=None,
        output_directory=canonical_root / "outputs",
        authority_database_locator=None,
    )
    research_inputs = tuple(
        item
        for item in initial
        if item.object_type
        in {
            LifecycleObjectType.OPERATIONAL_UNIVERSE,
            LifecycleObjectType.STATIC_UNIVERSE_FEATURE_BUNDLE,
            LifecycleObjectType.SUPPLEMENTAL_RESEARCH_EVIDENCE,
        }
    )
    signal_inputs = tuple(
        item
        for item in initial
        if item.object_type
        in {
            LifecycleObjectType.MARKET_DATA_DATASET,
            LifecycleObjectType.FEATURE_BUNDLE,
            LifecycleObjectType.STATIC_UNIVERSE_FEATURE_BUNDLE,
            LifecycleObjectType.CANDIDATE_INTRADAY_FEATURE_OVERLAY,
            LifecycleObjectType.TRADING_CALENDAR_ARTIFACT,
        }
    )
    handlers: dict[LifecycleStageName, LifecycleStageHandler] = {
        LifecycleStageName.VERIFY_COMPOSITE_EVIDENCE: (
            _ControlledEvidenceStageHandler()
        ),
        LifecycleStageName.PLATFORM_RESEARCH: (
            _ControlledResearchReceiptStageHandler(
                research=research,
                input_references=ordered_references(research_inputs),
                available_at=available_at,
                configuration=configuration,
            )
        ),
        LifecycleStageName.SIGNAL: _ControlledSignalStageHandler(
            candidates=research.artifact.candidate_set,
            static_bundle=static_bundle,
            static_feature_bundle=static_feature_bundle,
            daily_dataset=daily_dataset,
            intraday_overlay=overlay,
            intraday_feature_bundle=intraday_feature_bundle,
            minute_dataset=minute_dataset,
            trading_calendar=calendar,
            input_references=ordered_references(signal_inputs),
            decision_time=parent_command.decision_time,
            code_revision=parent_command.code_revision,
            output_root=canonical_root / "outputs" / "signals",
            available_at=available_at,
            configuration=configuration,
        ),
        LifecycleStageName.PATH_FORECAST: PathForecastStageHandler(
            configuration=configuration.path_forecast,
            output_root=canonical_root / "outputs" / "path-forecasts",
        ),
        LifecycleStageName.ENTRY_ASSESSMENT: EntryAssessmentStageHandler(
            authority_ceiling=LifecycleAuthorityCeiling()
        ),
    }
    unavailable = {
        stage: UnavailableLifecycleStageHandler(
            stage_name=stage,
            reason_code="CONTROLLED_OPERATION_STOPS_AT_ENTRY",
            detail="Entry remains blocked; downstream authority is unavailable",
        )
        for stage in LIFECYCLE_STAGE_ORDER
        if stage not in handlers
    }
    database_path = run_root / "canonical-lifecycle.sqlite3"
    repository = SQLiteLifecycleRunRepository(database_path)
    stage_latencies: dict[LifecycleStageName, int] = {}
    runner = CanonicalDecisionLifecycleRunner(
        repository=repository,
        handlers=tuple(
            _TimedStageHandler(
                handlers[stage] if stage in handlers else unavailable[stage],
                stage_latencies,
                clock=clock,
                hard_cutoff=hard_cutoff,
            )
            for stage in LIFECYCLE_STAGE_ORDER
        ),
        clock=clock,
        after_stage_hook=after_stage_hook,
    )
    try:
        existing_run = repository.get_run(command.run_id)
    except LifecycleRunNotFound:
        result = runner.run(command)
    else:
        stored_command = repository.get_command(command.run_id)
        if stored_command != command:
            raise ValueError(
                "Controlled canonical resume command identity divergence"
            )
        if existing_run.status in {
            LifecycleRunStatus.CREATED,
            LifecycleRunStatus.BLOCKED_BY_MODEL_VALIDATION,
            LifecycleRunStatus.COMPLETED,
        }:
            result = runner.run(command)
        else:
            result = runner.resume(command.run_id)
    if result.run.status is not LifecycleRunStatus.BLOCKED_BY_MODEL_VALIDATION:
        raise ValueError("Controlled canonical child did not stop at Entry")
    history = repository.history(result.run.run_id)
    signal_stage = next(
        item
        for item in history.stages
        if item.stage_name is LifecycleStageName.SIGNAL
    )
    signal_ref = next(
        item
        for item in signal_stage.output_references
        if item.object_type is LifecycleObjectType.SIGNAL_ARTIFACT
    )
    view_ref = next(
        item
        for item in signal_stage.output_references
        if item.object_type is LifecycleObjectType.CANDIDATE_FEATURE_VIEW
    )
    signal = load_verified_signal_run_v3(Path(signal_ref.locator or ""))
    view = load_candidate_feature_view_v2(Path(view_ref.locator or ""))
    path_stage = next(
        item
        for item in history.stages
        if item.stage_name is LifecycleStageName.PATH_FORECAST
    )
    forecasts = tuple(
        load_verified_path_forecast(Path(item.locator or ""))
        for item in path_stage.output_references
    )
    entry = ControlledEntryAssessmentBlocker.create(
        signal=signal,
        forecasts=forecasts,
        created_at=parent_command.decision_time,
    )
    entry_path = publish_controlled_entry_blocker(
        root=run_root / "entry-blockers",
        artifact=entry,
    )
    return ControlledCanonicalLifecycleExecution(
        result=result,
        history=history,
        database_path=database_path,
        signal=signal,
        candidate_view=view,
        candidate_view_path=Path(view_ref.locator or ""),
        forecasts=forecasts,
        entry_blocker=entry,
        entry_blocker_path=entry_path,
        stage_latencies_ms=tuple(
            sorted(stage_latencies.items(), key=lambda item: item[0].value)
        ),
    )


def _configuration_references(
    *,
    configuration: ControlledOperationRuntimeConfiguration,
    runtime_configuration_path: Path,
    root: Path,
) -> tuple[LifecycleConfigurationReference, ...]:
    values = (
        (
            LifecycleConfigurationKind.RESEARCH_PIPELINE,
            configuration.research.configuration_id,
            configuration.research.schema_version,
            configuration.research.configuration_hash,
            configuration.research.to_canonical_dict(),
        ),
        (
            LifecycleConfigurationKind.SIGNAL_MODEL,
            configuration.signal_model.configuration_id,
            configuration.signal_model.schema_version,
            configuration.signal_model.configuration_hash,
            configuration.signal_model.to_canonical_dict(),
        ),
        (
            LifecycleConfigurationKind.FEATURE_SET,
            configuration.static_feature_set.feature_set_id,
            configuration.static_feature_set.schema_version,
            configuration.static_feature_set.content_hash,
            configuration.static_feature_set.to_canonical_dict(),
        ),
        (
            LifecycleConfigurationKind.SIGNAL_INPUT_MAPPING,
            configuration.signal_mapping.configuration_id,
            configuration.signal_mapping.schema_version,
            configuration.signal_mapping.configuration_hash,
            configuration.signal_mapping.to_canonical_dict(),
        ),
        (
            LifecycleConfigurationKind.SIGNAL_FACTOR_REQUIREMENT,
            configuration.signal_requirement.policy_id,
            configuration.signal_requirement.schema_version,
            configuration.signal_requirement.policy_hash,
            configuration.signal_requirement.to_canonical_dict(),
        ),
        (
            LifecycleConfigurationKind.SIGNAL_FACTOR_FRESHNESS,
            configuration.signal_freshness.policy_id,
            configuration.signal_freshness.schema_version,
            configuration.signal_freshness.policy_hash,
            configuration.signal_freshness.to_canonical_dict(),
        ),
        (
            LifecycleConfigurationKind.PATH_FORECAST,
            configuration.path_forecast.configuration_id,
            configuration.path_forecast.schema_version,
            configuration.path_forecast.configuration_hash,
            configuration.path_forecast.to_canonical_dict(),
        ),
        (
            LifecycleConfigurationKind.GENERIC,
            configuration.configuration_id,
            configuration.schema_version,
            configuration.configuration_hash,
            configuration.to_canonical_dict(),
        ),
    )
    root.mkdir(parents=True, exist_ok=True)
    references = []
    for kind, identity, version, digest, payload in values:
        path = root / f"{identity}.json"
        publish_immutable_text(
            path=path,
            payload=canonical_json(payload) + "\n",
            collision_message="Controlled canonical configuration collision",
        )
        references.append(
            LifecycleConfigurationReference(
                configuration_kind=kind,
                configuration_id=identity,
                configuration_version=version,
                content_hash=digest,
                locator=str(path.resolve()),
            )
        )
    if not runtime_configuration_path.is_dir():
        raise ValueError("Controlled runtime configuration package is unavailable")
    return tuple(sorted(references, key=lambda item: item.sort_key))


def _model_references(
    configuration: ControlledOperationRuntimeConfiguration,
) -> tuple[LifecycleModelVersionReference, ...]:
    values: dict[tuple[ModelId, str], str] = {}
    for item, config_hash in (
        (
            configuration.research.market_regime,
            configuration.research.market_regime.configuration_hash,
        ),
        (
            configuration.research.theme_rotation,
            configuration.research.theme_rotation.configuration_hash,
        ),
        (
            configuration.research.capital_evolution,
            configuration.research.capital_evolution.configuration_hash,
        ),
        (
            configuration.research.candidate_discovery,
            configuration.research.candidate_discovery.configuration_hash,
        ),
        (configuration.signal_model, configuration.signal_model.configuration_hash),
        (configuration.path_forecast, configuration.path_forecast.configuration_hash),
    ):
        key = (item.model_id, item.model_version)
        digest = canonical_hash(
            {
                "schema_version": "controlled-canonical-model-reference-v1",
                "model_id": str(item.model_id),
                "model_version": item.model_version,
                "configuration_hash": config_hash,
            }
        )
        existing = values.setdefault(key, digest)
        if existing != digest:
            raise ValueError("Controlled canonical model identity conflict")
    return tuple(
        sorted(
            (
                LifecycleModelVersionReference(
                    model_id=model_id,
                    model_version=version,
                    content_hash=digest,
                )
                for (model_id, version), digest in values.items()
            ),
            key=lambda item: item.sort_key,
        )
    )


def _require_traceable(
    context: LifecycleStageContext,
    expected: tuple[LifecycleObjectReference, ...],
) -> None:
    available = {
        item.sort_key: item
        for item in (*context.initial_references, *context.upstream_references)
    }
    if any(available.get(item.sort_key) != item for item in expected):
        raise ValueError("Controlled canonical stage input is not traceable")


def _decision_time(value: datetime):
    from market_regime_alpha.core.time import DecisionTime

    return DecisionTime(value)


__all__ = [
    "ControlledCanonicalDeadlineExceeded",
    "ControlledCanonicalLifecycleExecution",
    "run_controlled_canonical_lifecycle",
]
