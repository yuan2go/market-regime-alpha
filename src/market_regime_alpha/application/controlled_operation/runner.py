"""Application orchestration for one Controlled A-share Decision-Time operation."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import shutil
from time import perf_counter, sleep
from typing import Callable, NoReturn

from market_regime_alpha.application.controlled_operation.canonical_bridge import (
    CanonicalRepositoryFactory,
    ControlledCanonicalDeadlineExceeded,
    run_controlled_canonical_lifecycle,
    sqlite_controlled_canonical_repository,
)
from market_regime_alpha.application.canonical_lifecycle.runner import (
    AfterStageHook,
    LifecycleStageExecutionError,
)
from market_regime_alpha.application.canonical_lifecycle.contracts import (
    LifecycleObjectType,
)
from market_regime_alpha.application.canonical_lifecycle.states import (
    LifecycleRunType,
    LifecycleStageName,
)
from market_regime_alpha.application.controlled_operation.canonical_segment import (
    CanonicalLifecycleRunObjectReference,
    ControlledCanonicalLifecycleRunReceipt,
    publish_controlled_canonical_lifecycle_run,
)
from market_regime_alpha.application.controlled_operation.evidence_package import (
    ControlledEvidenceReference,
    ControlledOperationalEvidencePackage,
    ControlledOperationalEvidenceStatus,
    StageRuntimeLatency,
    load_controlled_operation_package,
    publish_controlled_operation_package,
)
from market_regime_alpha.application.controlled_operation.input_artifacts import (
    load_controlled_runtime_configuration,
    load_controlled_source_manifest,
    load_controlled_trading_calendar,
)
from market_regime_alpha.application.controlled_operation.longitudinal_index import (
    LongitudinalOperationalIndex,
    LongitudinalOperationalRecord,
    SQLiteLongitudinalOperationalIndex,
)
from market_regime_alpha.application.controlled_operation.journal import (
    ChildRunReferenceKind,
    ClaimedDecisionTimeOperationStage,
    ControlledOperationCommand,
    DecisionTimeOperationJournal,
    DecisionTimeOperationReceipt,
    DecisionTimeOperationRunSnapshot,
    DecisionTimeOperationRunStatus,
    DecisionTimeOperationStageName,
    DecisionTimeOperationStageStatus,
    OperationArtifactReference,
    OperationChildRunReference,
)
from market_regime_alpha.application.controlled_operation.policy import (
    DecisionTimeOperationPolicy,
    DecisionWindowState,
)
from market_regime_alpha.application.controlled_operation.research_input import (
    ControlledOperationalResearchInput,
)
from market_regime_alpha.application.controlled_operation.research_runner import (
    VerifiedControlledResearchArtifact,
    load_verified_controlled_research_artifact,
)
from market_regime_alpha.application.controlled_operation.outcome_evidence import (
    TradeHorizonDefinition,
    TradeHorizonOutcomeEvidence,
    build_trade_horizon_outcome_evidence,
    load_trade_horizon_outcome_evidence,
    publish_trade_horizon_outcome_evidence,
)
from market_regime_alpha.application.controlled_operation.outcome_source_archive import (
    load_outcome_settlement_source_archive,
    replay_outcome_dataset_from_source_archive,
)
from market_regime_alpha.application.controlled_operation.runtime_configuration import (
    ControlledOperationRuntimeConfiguration,
)
from market_regime_alpha.application.operational_research.supplemental_artifact import (
    load_verified_supplemental_research_evidence,
)
from market_regime_alpha.application.research_layer.runner import PlatformResearchRunner
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.data.providers.public_composite import (
    load_verified_public_source_stage_artifact,
)
from market_regime_alpha.data.providers.public_composite.stage_artifact import (
    PublicSourceAcquisitionStage,
)
from market_regime_alpha.data.trading_calendar import TradingCalendarArtifact
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.features import (
    FeatureMaterializationExecutionMode,
    FeatureMaterializationRunner,
)
from market_regime_alpha.features.materialization_v2 import (
    FeatureRunRepositoryFactory,
    VerifiedFeatureBundleV2,
    load_verified_feature_bundle_v2,
)
from market_regime_alpha.features.operational_overlay import (
    CandidateIntradayFeatureOverlay,
    StaticUniverseFeatureBundle,
    publish_candidate_intraday_feature_overlay,
    publish_static_universe_feature_bundle,
)
from market_regime_alpha.features.v2_contracts import FeatureMaterializationReceipt
from market_regime_alpha.forecasting.artifact import (
    VerifiedPathForecastArtifact,
    load_verified_path_forecast,
)
from market_regime_alpha.market_data import (
    AssetType,
    VerifiedMarketDataDataset,
    load_verified_market_data_dataset,
    normalize_public_history_stage,
    publish_market_data_dataset,
)
from market_regime_alpha.market_data.minute_batch import (
    CandidateMinuteAcquisitionCommand,
    CandidateMinuteBatchAcquirer,
    MinuteAcquisitionCoverageArtifact,
    MinuteClientFactory,
    MinuteCoverageState,
    load_minute_acquisition_coverage,
)
from market_regime_alpha.market_data.minute_source import (
    CanonicalVolumeUnitPolicy,
    RawMinuteSourceReader,
    minute_normalizations_to_dataset,
    normalize_tencent_minute_source,
)
from market_regime_alpha.research.candidate_discovery.contracts import CandidateSet
from market_regime_alpha.signals.v3 import (
    VerifiedSignalRunArtifactV3,
    load_verified_signal_run_v3,
)
from market_regime_alpha.universe import (
    OperationalUniverseArtifact,
    load_operational_universe,
)


Clock = Callable[[], datetime]
Sleeper = Callable[[float], None]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


class ControlledOperationDataBlocked(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ControlledOperationInputPaths:
    trading_calendar: Path
    operational_universe: Path
    daily_source_stage: Path
    daily_source_manifest: Path
    supplemental_research_evidence: Path
    runtime_configuration: Path


@dataclass(frozen=True, slots=True)
class ControlledOperationSettlementInputPaths:
    outcome_source_archive: Path
    outcome_source_manifest: Path
    outcome_dataset: Path


@dataclass(frozen=True, slots=True)
class ControlledOperationPreparation:
    snapshot: DecisionTimeOperationRunSnapshot
    calendar: TradingCalendarArtifact
    universe: OperationalUniverseArtifact
    daily_dataset: VerifiedMarketDataDataset
    daily_dataset_path: Path
    static_feature_bundle: VerifiedFeatureBundleV2
    static_feature_receipt: FeatureMaterializationReceipt
    static_bundle: StaticUniverseFeatureBundle
    static_bundle_path: Path
    input_paths: ControlledOperationInputPaths


@dataclass(frozen=True, slots=True)
class ControlledOperationDecisionResult:
    snapshot: DecisionTimeOperationRunSnapshot
    research: VerifiedControlledResearchArtifact
    candidate_set: CandidateSet
    minute_coverage: MinuteAcquisitionCoverageArtifact
    minute_dataset: VerifiedMarketDataDataset
    minute_dataset_path: Path
    intraday_feature_bundle: VerifiedFeatureBundleV2
    intraday_feature_receipt: FeatureMaterializationReceipt
    overlay: CandidateIntradayFeatureOverlay
    overlay_path: Path
    signal: VerifiedSignalRunArtifactV3
    forecasts: tuple[VerifiedPathForecastArtifact, ...]
    entry_blocker_path: Path
    package: ControlledOperationalEvidencePackage
    package_path: Path


@dataclass(frozen=True, slots=True)
class ControlledOperationSettlementResult:
    snapshot: DecisionTimeOperationRunSnapshot
    outcome: TradeHorizonOutcomeEvidence
    outcome_path: Path
    package: ControlledOperationalEvidencePackage
    package_path: Path
    longitudinal_record: LongitudinalOperationalRecord


class ControlledDecisionTimeOperationRunner:
    """Compose existing bounded contexts; never create execution authority."""

    def __init__(
        self,
        *,
        journal: DecisionTimeOperationJournal,
        output_root: Path,
        clock: Clock = _utc_now,
        minute_client_factory: MinuteClientFactory | None = None,
        sleeper: Sleeper = sleep,
        canonical_after_stage_hook: AfterStageHook | None = None,
        longitudinal_index: LongitudinalOperationalIndex | None = None,
        canonical_repository_factory: CanonicalRepositoryFactory = (
            sqlite_controlled_canonical_repository
        ),
        feature_repository_factory: FeatureRunRepositoryFactory | None = None,
    ) -> None:
        self._journal = journal
        self._output_root = output_root.resolve()
        self._clock = clock
        self._minute_client_factory = minute_client_factory
        self._sleeper = sleeper
        self._canonical_after_stage_hook = canonical_after_stage_hook
        self._longitudinal_index = longitudinal_index or (
            SQLiteLongitudinalOperationalIndex(
                self._output_root / "longitudinal-operational-index.sqlite3",
                clock=self._clock,
            )
        )
        self._canonical_repository_factory = canonical_repository_factory
        self._feature_repository_factory = feature_repository_factory

    def prepare(
        self,
        *,
        command: ControlledOperationCommand,
        policy: DecisionTimeOperationPolicy,
        inputs: ControlledOperationInputPaths,
    ) -> ControlledOperationPreparation:
        run_root = self._run_root(command)
        run_root.mkdir(parents=True, exist_ok=True)
        inputs = _freeze_input_paths(run_root=run_root, inputs=inputs)
        calendar = load_controlled_trading_calendar(inputs.trading_calendar)
        universe = load_operational_universe(inputs.operational_universe)
        configuration = load_controlled_runtime_configuration(inputs.runtime_configuration)
        self._validate_command(command, policy, calendar, configuration)
        if not calendar.contains(command.decision_date):
            raise ControlledOperationDataBlocked("DECISION_DATE_NOT_IN_TRADING_CALENDAR")
        if universe.decision_date != command.decision_date:
            raise ValueError("Operational Universe DecisionDate mismatch")
        self._journal.create_or_get(command)
        latencies: dict[str, int] = {}

        self._execute_stage(
            command=command,
            stage=DecisionTimeOperationStageName.CALENDAR_UNIVERSE_FREEZE,
            run_status=DecisionTimeOperationRunStatus.WAITING_FOR_STATIC_INPUTS,
            inputs=(),
            outputs=(
                _reference("TRADING_CALENDAR", calendar.artifact_id, calendar.content_hash),
                _reference("OPERATIONAL_UNIVERSE", universe.universe_id, universe.content_hash),
            ),
            reasons=("CALENDAR_AND_OPERATIONAL_UNIVERSE_VERIFIED",),
            latency_sink=latencies,
        )

        source = load_verified_public_source_stage_artifact(inputs.daily_source_stage)
        source_manifest = load_controlled_source_manifest(inputs.daily_source_manifest)
        if source.stage is not PublicSourceAcquisitionStage.HISTORY_SOURCE_FROZEN:
            raise ValueError("Controlled preparation requires frozen daily source history")
        if source_manifest.decision_time.value != command.decision_time:
            raise ValueError("Controlled daily SourceManifest DecisionTime mismatch")
        if any(item.retrieved_at.value > command.decision_time for item in source_manifest.source_artifacts):
            raise ControlledOperationDataBlocked("DAILY_SOURCE_AVAILABLE_AFTER_DECISION_TIME")
        self._execute_stage(
            command=command,
            stage=DecisionTimeOperationStageName.DAILY_SOURCE_FREEZE,
            run_status=DecisionTimeOperationRunStatus.WAITING_FOR_STATIC_INPUTS,
            inputs=(),
            outputs=(
                _reference("DAILY_SOURCE_ARCHIVE", source.artifact_id, source.content_hash),
                _reference(
                    "DAILY_SOURCE_MANIFEST",
                    source_manifest.source_manifest_id,
                    source_manifest.content_hash,
                ),
            ),
            child_runs=(
                OperationChildRunReference(
                    ChildRunReferenceKind.DAILY_ACQUISITION_RUN,
                    source.acquisition_key or str(source.artifact_id),
                    source.checksums_hash,
                ),
            ),
            reasons=("DAILY_SOURCE_ARCHIVE_VERIFIED",),
            latency_sink=latencies,
        )

        daily_artifact = normalize_public_history_stage(
            verified=source,
            decision_time=command.decision_time,
            created_at=command.decision_time,
            expected_symbols=universe.symbols,
            source_manifest=source_manifest,
            asset_types={item: AssetType.A_SHARE for item in universe.symbols},
        )
        daily_path = publish_market_data_dataset(root=run_root / "daily-datasets", artifact=daily_artifact)
        daily = load_verified_market_data_dataset(daily_path)
        self._execute_stage(
            command=command,
            stage=DecisionTimeOperationStageName.DAILY_DATASET,
            run_status=DecisionTimeOperationRunStatus.WAITING_FOR_STATIC_INPUTS,
            inputs=(
                _reference("DAILY_SOURCE_ARCHIVE", source.artifact_id, source.content_hash),
                _reference("DAILY_SOURCE_MANIFEST", source_manifest.source_manifest_id, source_manifest.content_hash),
            ),
            outputs=(_reference("DAILY_DATASET", daily.artifact.dataset_id, daily.artifact.content_hash),),
            reasons=("DAILY_CANONICAL_DATASET_PUBLISHED",),
            latency_sink=latencies,
        )

        feature_start = perf_counter()
        static_receipt = _run_feature_materialization(
            verified_dataset=daily,
            feature_set=configuration.static_feature_set,
            selected_symbols=universe.symbols,
            code_revision=command.code_revision,
            output_root=run_root / "static-features",
            idempotency_key=f"{command.idempotency_key}:static",
            max_workers=configuration.feature_max_workers,
            repository_factory=self._feature_repository_factory,
        )
        static_features = load_verified_feature_bundle_v2(
            run_root / "static-features" / static_receipt.bundle_locator,
            artifact_root=run_root / "static-features" / "feature-artifacts",
        )
        static_bundle = StaticUniverseFeatureBundle.create(
            universe=universe,
            daily_dataset=daily,
            feature_bundle=static_features,
            run_receipt=static_receipt,
            code_revision=command.code_revision,
        )
        static_path = publish_static_universe_feature_bundle(root=run_root / "static-bundles", artifact=static_bundle)
        latencies[DecisionTimeOperationStageName.STATIC_FEATURES.value] = int((perf_counter() - feature_start) * 1000)
        self._execute_stage(
            command=command,
            stage=DecisionTimeOperationStageName.STATIC_FEATURES,
            run_status=DecisionTimeOperationRunStatus.STATIC_READY,
            inputs=(_reference("DAILY_DATASET", daily.artifact.dataset_id, daily.artifact.content_hash),),
            outputs=(_reference("STATIC_FEATURE_BUNDLE", static_bundle.artifact_id, static_bundle.content_hash),),
            child_runs=(
                OperationChildRunReference(
                    ChildRunReferenceKind.STATIC_FEATURE_RUN,
                    static_receipt.command_hash,
                    static_receipt.content_hash,
                ),
            ),
            reasons=("PRE_DECISION_STATIC_FEATURES_READY",),
            latency_sink=latencies,
            premeasured=True,
        )
        snapshot = self._journal.get(command.run_id)
        return ControlledOperationPreparation(
            snapshot=snapshot,
            calendar=calendar,
            universe=universe,
            daily_dataset=daily,
            daily_dataset_path=daily_path,
            static_feature_bundle=static_features,
            static_feature_receipt=static_receipt,
            static_bundle=static_bundle,
            static_bundle_path=static_path,
            input_paths=inputs,
        )

    def run_decision_window(
        self,
        *,
        command: ControlledOperationCommand,
        policy: DecisionTimeOperationPolicy,
        inputs: ControlledOperationInputPaths,
        _resume_admitted_child: bool = False,
    ) -> ControlledOperationDecisionResult:
        preparation = self.prepare(command=command, policy=policy, inputs=inputs)
        run_root = self._run_root(command)
        inputs = preparation.input_paths
        configuration = load_controlled_runtime_configuration(inputs.runtime_configuration)
        observed_at = self._now()
        static_stage_receipt = _completed_receipt(
            preparation.snapshot,
            DecisionTimeOperationStageName.STATIC_FEATURES,
        )
        assessment = policy.assess(
            decision_date=command.decision_date,
            observed_at=observed_at,
            calendar=preparation.calendar,
            expected_calendar_hash=command.trading_calendar_hash,
            static_inputs_ready_at=(
                static_stage_receipt.created_at
                if static_stage_receipt is not None
                else None
            ),
        )
        resume_admitted_child = (
            _resume_admitted_child
            and self._canonical_child_was_admitted(
                command=command,
                observed_at=observed_at,
                hard_cutoff=policy.hard_cutoff_instant(command.decision_date),
            )
        )
        completed_operation = self._outcome_pending_operation_is_complete(command)
        if (
            assessment.state is not DecisionWindowState.DECISION_WINDOW_RUNNING
            and not resume_admitted_child
            and not completed_operation
        ):
            status = (
                DecisionTimeOperationRunStatus.DEADLINE_MISSED
                if assessment.state is DecisionWindowState.DEADLINE_MISSED
                else DecisionTimeOperationRunStatus.DATA_BLOCKED
            )
            self._publish_terminal_package(
                command=command,
                policy=policy,
                inputs=inputs,
                preparation=preparation,
                configuration=configuration,
                status=(
                    ControlledOperationalEvidenceStatus.DEADLINE_MISSED
                    if status is DecisionTimeOperationRunStatus.DEADLINE_MISSED
                    else ControlledOperationalEvidenceStatus.DATA_BLOCKED
                ),
                deadline_status=assessment.state.value,
                reason_codes=assessment.reason_codes,
                latencies={},
            )
            snapshot = self._journal.get(command.run_id)
            self._journal.set_run_status(
                run_id=command.run_id,
                expected_version=snapshot.version,
                status=status,
                reason=assessment.reason_codes[0],
            )
            raise ControlledOperationDataBlocked(assessment.reason_codes[0])
        if (
            not assessment.accepts_signal_evidence
            and not resume_admitted_child
            and not completed_operation
        ):
            raise ControlledOperationDataBlocked("DECISION_TIME_EVIDENCE_WINDOW_CLOSED")
        latencies: dict[str, int] = {}

        supplemental = load_verified_supplemental_research_evidence(inputs.supplemental_research_evidence)
        research_inputs = ControlledOperationalResearchInput.create(
            operational_universe=preparation.universe,
            static_feature_bundle=preparation.static_bundle,
            supplemental_evidence=supplemental,
        )
        started = perf_counter()
        research = PlatformResearchRunner().run_controlled(
            inputs=research_inputs,
            static_feature_bundle=preparation.static_feature_bundle,
            configuration=configuration.research,
            output_root=run_root / "research",
            code_revision=command.code_revision,
        )
        latencies[DecisionTimeOperationStageName.OPERATIONAL_RESEARCH.value] = int((perf_counter() - started) * 1000)
        self._execute_stage(
            command=command,
            stage=DecisionTimeOperationStageName.OPERATIONAL_RESEARCH,
            run_status=DecisionTimeOperationRunStatus.DECISION_WINDOW_RUNNING,
            inputs=(_reference("STATIC_FEATURE_BUNDLE", preparation.static_bundle.artifact_id, preparation.static_bundle.content_hash),),
            outputs=(_reference("CONTROLLED_RESEARCH", research.artifact.artifact_id, research.artifact.content_hash),),
            reasons=("CONTROLLED_RESEARCH_WITHOUT_B0_B1_COMPLETED",),
            latency_sink=latencies,
            premeasured=True,
        )
        candidates = research.artifact.candidate_set
        self._execute_stage(
            command=command,
            stage=DecisionTimeOperationStageName.CANDIDATE_SET,
            run_status=DecisionTimeOperationRunStatus.DECISION_WINDOW_RUNNING,
            inputs=(_reference("CONTROLLED_RESEARCH", research.artifact.artifact_id, research.artifact.content_hash),),
            outputs=(_reference("CANDIDATE_SET", candidates.envelope.artifact_id, candidates.envelope.content_hash),),
            reasons=("CANDIDATE_SET_DERIVED_FROM_CONTROLLED_RESEARCH",),
            latency_sink=latencies,
        )
        if not candidates.selected:
            reason = "CONTROLLED_CANDIDATE_SET_EMPTY"
            self._publish_terminal_package(
                command=command,
                policy=policy,
                inputs=inputs,
                preparation=preparation,
                configuration=configuration,
                status=ControlledOperationalEvidenceStatus.DATA_BLOCKED,
                deadline_status=assessment.state.value,
                reason_codes=(reason, "SUPPLEMENTAL_EVIDENCE_INSUFFICIENT"),
                latencies=latencies,
                research=research,
                candidates=candidates,
            )
            snapshot = self._journal.get(command.run_id)
            self._journal.set_run_status(
                run_id=command.run_id,
                expected_version=snapshot.version,
                status=DecisionTimeOperationRunStatus.DATA_BLOCKED,
                reason=reason,
            )
            raise ControlledOperationDataBlocked(reason)

        minute_command = CandidateMinuteAcquisitionCommand.create(
            candidate_set=candidates,
            decision_time=command.decision_time,
            provider_profile_id=configuration.provider_profile_id,
            concurrency_limit=configuration.minute_concurrency_limit,
            per_request_timeout_seconds=configuration.minute_per_request_timeout_seconds,
            max_attempts=configuration.minute_max_attempts,
            retry_backoff_seconds=configuration.minute_retry_backoff_seconds,
            hard_cutoff=policy.hard_cutoff_instant(command.decision_date),
        )
        started = perf_counter()
        existing_minute_receipt = _completed_receipt(
            self._journal.get(command.run_id),
            DecisionTimeOperationStageName.CANDIDATE_MINUTE_ACQUISITION,
        )
        if existing_minute_receipt is None:
            coverage = CandidateMinuteBatchAcquirer(
                client_factory=self._minute_client_factory,
                clock=self._clock,
            ).run(command=minute_command, output_root=run_root / "minute-acquisition")
        else:
            reference = next(
                item for item in existing_minute_receipt.output_references if item.reference_type == "MINUTE_ACQUISITION_COVERAGE"
            )
            coverage = load_minute_acquisition_coverage(run_root / "minute-acquisition" / "coverage" / str(reference.object_id))
            if coverage.content_hash != reference.content_hash:
                raise ValueError("recovered minute Coverage Receipt mismatch")
        latencies[DecisionTimeOperationStageName.CANDIDATE_MINUTE_ACQUISITION.value] = int((perf_counter() - started) * 1000)
        self._execute_stage(
            command=command,
            stage=DecisionTimeOperationStageName.CANDIDATE_MINUTE_ACQUISITION,
            run_status=DecisionTimeOperationRunStatus.DECISION_WINDOW_RUNNING,
            inputs=(_reference("CANDIDATE_SET", candidates.envelope.artifact_id, candidates.envelope.content_hash),),
            outputs=(_reference("MINUTE_ACQUISITION_COVERAGE", coverage.artifact_id, coverage.content_hash),),
            child_runs=(
                OperationChildRunReference(
                    ChildRunReferenceKind.MINUTE_ACQUISITION_BATCH,
                    str(minute_command.command_id),
                    coverage.content_hash,
                ),
            ),
            reasons=coverage.reason_codes,
            latency_sink=latencies,
            premeasured=True,
        )
        if coverage.coverage_state in {MinuteCoverageState.FAILED, MinuteCoverageState.DEADLINE_MISSED}:
            reason = "CANDIDATE_MINUTE_ACQUISITION_HAS_NO_USABLE_SOURCE"
            self._publish_terminal_package(
                command=command,
                policy=policy,
                inputs=inputs,
                preparation=preparation,
                configuration=configuration,
                status=(
                    ControlledOperationalEvidenceStatus.DEADLINE_MISSED
                    if coverage.coverage_state is MinuteCoverageState.DEADLINE_MISSED
                    else ControlledOperationalEvidenceStatus.DATA_BLOCKED
                ),
                deadline_status=coverage.coverage_state.value,
                reason_codes=(reason, *coverage.reason_codes),
                latencies=latencies,
                research=research,
                candidates=candidates,
                coverage=coverage,
            )
            snapshot = self._journal.get(command.run_id)
            self._journal.set_run_status(
                run_id=command.run_id,
                expected_version=snapshot.version,
                status=(
                    DecisionTimeOperationRunStatus.DEADLINE_MISSED
                    if coverage.coverage_state is MinuteCoverageState.DEADLINE_MISSED
                    else DecisionTimeOperationRunStatus.DATA_BLOCKED
                ),
                reason=reason,
            )
            raise ControlledOperationDataBlocked(reason)

        started = perf_counter()
        normalized_sources = []
        source_reader = RawMinuteSourceReader()
        for source_id, expected_hash in coverage.accepted_source_references:
            source = source_reader.read(run_root / "minute-acquisition" / "sources" / str(source_id))
            if source.content_hash != expected_hash or source.response_received_at > command.decision_time:
                raise ControlledOperationDataBlocked("MINUTE_SOURCE_AUTHORITY_OR_DECISION_TIME_CONFLICT")
            normalized_sources.append(
                (
                    normalize_tencent_minute_source(
                        artifact=source,
                        asset_type=AssetType.A_SHARE,
                        volume_policy=CanonicalVolumeUnitPolicy.a_share_v1(),
                    ),
                    source,
                )
            )
        minute_artifact = minute_normalizations_to_dataset(
            normalized_sources=tuple(normalized_sources),
            expected_symbols=tuple(sorted(item.symbol for item in candidates.selected)),
            decision_time=command.decision_time,
            created_at=command.decision_time,
        )
        minute_path = publish_market_data_dataset(root=run_root / "minute-datasets", artifact=minute_artifact)
        minute = load_verified_market_data_dataset(minute_path)
        latencies[DecisionTimeOperationStageName.INTRADAY_DATASET.value] = int(
            (perf_counter() - started) * 1000
        )
        self._execute_stage(
            command=command,
            stage=DecisionTimeOperationStageName.INTRADAY_DATASET,
            run_status=DecisionTimeOperationRunStatus.DECISION_WINDOW_RUNNING,
            inputs=(_reference("MINUTE_ACQUISITION_COVERAGE", coverage.artifact_id, coverage.content_hash),),
            outputs=(_reference("MINUTE_DATASET", minute.artifact.dataset_id, minute.artifact.content_hash),),
            reasons=("CANDIDATE_INTRADAY_CANONICAL_DATASET_PUBLISHED",),
            latency_sink=latencies,
            premeasured=True,
        )

        started = perf_counter()
        intraday_receipt = _run_feature_materialization(
            verified_dataset=minute,
            feature_set=configuration.intraday_feature_set,
            selected_symbols=tuple(sorted(item.symbol for item in candidates.selected)),
            code_revision=command.code_revision,
            output_root=run_root / "intraday-features",
            idempotency_key=f"{command.idempotency_key}:intraday",
            max_workers=configuration.feature_max_workers,
            repository_factory=self._feature_repository_factory,
        )
        intraday_features = load_verified_feature_bundle_v2(
            run_root / "intraday-features" / intraday_receipt.bundle_locator,
            artifact_root=run_root / "intraday-features" / "feature-artifacts",
        )
        overlay = CandidateIntradayFeatureOverlay.create(
            candidate_set=candidates,
            static_bundle=preparation.static_bundle,
            minute_dataset=minute,
            intraday_feature_bundle=intraday_features,
            trading_calendar=preparation.calendar,
        )
        overlay_path = publish_candidate_intraday_feature_overlay(root=run_root / "intraday-overlays", artifact=overlay)
        latencies[DecisionTimeOperationStageName.INTRADAY_FEATURE_OVERLAY.value] = int((perf_counter() - started) * 1000)
        self._execute_stage(
            command=command,
            stage=DecisionTimeOperationStageName.INTRADAY_FEATURE_OVERLAY,
            run_status=DecisionTimeOperationRunStatus.DECISION_WINDOW_RUNNING,
            inputs=(_reference("MINUTE_DATASET", minute.artifact.dataset_id, minute.artifact.content_hash),),
            outputs=(_reference("INTRADAY_FEATURE_OVERLAY", overlay.artifact_id, overlay.content_hash),),
            child_runs=(
                OperationChildRunReference(
                    ChildRunReferenceKind.INTRADAY_FEATURE_RUN,
                    intraday_receipt.command_hash,
                    intraday_receipt.content_hash,
                ),
            ),
            reasons=("CANDIDATE_INTRADAY_FEATURE_OVERLAY_PUBLISHED",),
            latency_sink=latencies,
            premeasured=True,
        )

        canonical_observed_at = self._now()
        if canonical_observed_at < command.decision_time:
            wait_seconds = (
                command.decision_time - canonical_observed_at
            ).total_seconds()
            if wait_seconds > 60:
                raise ControlledOperationDataBlocked(
                    "DECISION_TIME_NOT_REACHED_FOR_SIGNAL"
                )
            self._sleeper(wait_seconds)
            canonical_observed_at = self._now()
            if canonical_observed_at < command.decision_time:
                raise ControlledOperationDataBlocked(
                    "DECISION_TIME_NOT_REACHED_FOR_SIGNAL"
                )
        if (
            canonical_observed_at > command.decision_time
            and not resume_admitted_child
            and not completed_operation
        ):
            reason = (
                "HARD_CUTOFF_EXCEEDED_BEFORE_CANONICAL_CHILD"
                if canonical_observed_at
                > policy.hard_cutoff_instant(command.decision_date)
                else "DECISION_TIME_START_MISSED_FOR_CANONICAL_CHILD"
            )
            self._reject_decision_window_deadline(
                command=command,
                policy=policy,
                inputs=inputs,
                preparation=preparation,
                configuration=configuration,
                reason=reason,
                latencies=latencies,
                research=research,
                candidates=candidates,
                coverage=coverage,
                minute=minute,
                minute_path=minute_path,
                overlay=overlay,
                overlay_path=overlay_path,
            )
        hard_cutoff = policy.hard_cutoff_instant(command.decision_date)
        canonical_available_at = (
            command.decision_time
            if resume_admitted_child or completed_operation
            else canonical_observed_at
        )
        try:
            canonical_execution = run_controlled_canonical_lifecycle(
                parent_command=command,
                run_root=run_root,
                clock=self._clock,
                available_at=canonical_available_at,
                configuration=configuration,
                runtime_configuration_path=inputs.runtime_configuration,
                calendar=preparation.calendar,
                calendar_path=inputs.trading_calendar,
                universe=preparation.universe,
                universe_path=inputs.operational_universe,
                daily_source_manifest_path=inputs.daily_source_manifest,
                supplemental_path=inputs.supplemental_research_evidence,
                research=research,
                daily_dataset=preparation.daily_dataset,
                daily_dataset_path=preparation.daily_dataset_path,
                static_bundle=preparation.static_bundle,
                static_bundle_path=preparation.static_bundle_path,
                static_feature_bundle=preparation.static_feature_bundle,
                minute_dataset=minute,
                minute_dataset_path=minute_path,
                intraday_feature_bundle=intraday_features,
                overlay=overlay,
                overlay_path=overlay_path,
                hard_cutoff=hard_cutoff,
                after_stage_hook=self._canonical_after_stage_hook,
                repository_factory=self._canonical_repository_factory,
            )
        except LifecycleStageExecutionError as exc:
            if exc.exception_type != ControlledCanonicalDeadlineExceeded.__name__:
                raise
            self._reject_decision_window_deadline(
                command=command,
                policy=policy,
                inputs=inputs,
                preparation=preparation,
                configuration=configuration,
                reason="HARD_CUTOFF_EXCEEDED_DURING_CANONICAL_CHILD",
                latencies=latencies,
                research=research,
                candidates=candidates,
                coverage=coverage,
                minute=minute,
                minute_path=minute_path,
                overlay=overlay,
                overlay_path=overlay_path,
            )
        if self._now() > hard_cutoff and not completed_operation:
            self._reject_decision_window_deadline(
                command=command,
                policy=policy,
                inputs=inputs,
                preparation=preparation,
                configuration=configuration,
                reason="HARD_CUTOFF_EXCEEDED_AFTER_CANONICAL_CHILD",
                latencies=latencies,
                research=research,
                candidates=candidates,
                coverage=coverage,
                minute=minute,
                minute_path=minute_path,
                overlay=overlay,
                overlay_path=overlay_path,
            )
        canonical_latencies = dict(canonical_execution.stage_latencies_ms)
        signal_output = canonical_execution.signal
        candidate_view = canonical_execution.candidate_view
        path_output = canonical_execution.forecasts
        entry = canonical_execution.entry_blocker
        entry_path = canonical_execution.entry_blocker_path
        latencies[DecisionTimeOperationStageName.SIGNAL.value] = (
            canonical_latencies.get(LifecycleStageName.SIGNAL, 0)
        )
        self._execute_stage(
            command=command,
            stage=DecisionTimeOperationStageName.SIGNAL,
            run_status=DecisionTimeOperationRunStatus.DECISION_WINDOW_RUNNING,
            inputs=(_reference("INTRADAY_FEATURE_OVERLAY", overlay.artifact_id, overlay.content_hash),),
            outputs=(
                _reference("CANDIDATE_FEATURE_VIEW_V2", candidate_view.view_id, candidate_view.content_hash),
                _reference("SIGNAL_V3", signal_output.artifact.artifact_id, signal_output.artifact.envelope.content_hash),
            ),
            reasons=("CANONICAL_SIGNAL_V3_FROM_CANDIDATE_VIEW_V2",),
            latency_sink=latencies,
            premeasured=True,
        )

        latencies[DecisionTimeOperationStageName.PATH_FORECAST.value] = (
            canonical_latencies.get(LifecycleStageName.PATH_FORECAST, 0)
        )
        self._execute_stage(
            command=command,
            stage=DecisionTimeOperationStageName.PATH_FORECAST,
            run_status=DecisionTimeOperationRunStatus.DECISION_WINDOW_RUNNING,
            inputs=(
                _reference("SIGNAL_V3", signal_output.artifact.artifact_id, signal_output.artifact.envelope.content_hash),
            ),
            outputs=tuple(
                _reference("PATH_FORECAST", item.artifact.artifact_id, item.artifact.forecast.envelope.content_hash)
                for item in path_output
            ),
            reasons=("PATH_FORECAST_SAMPLE_AUTHORITY_UNAVAILABLE", "PATH_FORECAST_DATA_INSUFFICIENT"),
            latency_sink=latencies,
            premeasured=True,
        )
        canonical_run = ControlledCanonicalLifecycleRunReceipt.create(
            parent_operation_run_id=command.run_id,
            parent_operation_command_hash=command.command_hash,
            decision_time=command.decision_time,
            code_revision=command.code_revision,
            configuration_manifest_hash=command.configuration_manifest_hash,
            model_manifest_hash=command.model_manifest_hash,
            input_references=(
                CanonicalLifecycleRunObjectReference(
                    "CANDIDATE_FEATURE_VIEW_V2",
                    candidate_view.view_id,
                    candidate_view.content_hash,
                ),
            ),
            output_references=(
                CanonicalLifecycleRunObjectReference(
                    "SIGNAL_V3",
                    signal_output.artifact.artifact_id,
                    signal_output.artifact.envelope.content_hash,
                ),
                *(
                    CanonicalLifecycleRunObjectReference(
                        "PATH_FORECAST",
                        item.artifact.artifact_id,
                        item.artifact.forecast.envelope.content_hash,
                    )
                    for item in path_output
                ),
                CanonicalLifecycleRunObjectReference(
                    "ENTRY_BLOCKER",
                    entry.artifact_id,
                    entry.content_hash,
                ),
            ),
            canonical_result=canonical_execution.result,
            canonical_history=canonical_execution.history,
        )
        canonical_run_path = publish_controlled_canonical_lifecycle_run(
            root=run_root / "canonical-lifecycle-runs",
            artifact=canonical_run,
        )
        latencies[DecisionTimeOperationStageName.ENTRY_ASSESSMENT.value] = (
            canonical_latencies.get(LifecycleStageName.ENTRY_ASSESSMENT, 0)
        )
        self._execute_stage(
            command=command,
            stage=DecisionTimeOperationStageName.ENTRY_ASSESSMENT,
            run_status=DecisionTimeOperationRunStatus.DECISION_WINDOW_RUNNING,
            inputs=tuple(
                _reference("PATH_FORECAST", item.artifact.artifact_id, item.artifact.forecast.envelope.content_hash)
                for item in path_output
            ),
            outputs=(_reference("ENTRY_BLOCKER", entry.artifact_id, entry.content_hash),),
            child_runs=(
                OperationChildRunReference(
                    ChildRunReferenceKind.CANONICAL_LIFECYCLE_RUN,
                    str(canonical_run.run_id),
                    canonical_run.content_hash,
                ),
            ),
            reasons=entry.reason_codes,
            latency_sink=latencies,
            premeasured=True,
        )

        package_root = run_root / "operation-packages"
        package = _find_operation_package(package_root, command.run_id)
        if package is None:
            snapshot = self._journal.get(command.run_id)
            package = ControlledOperationalEvidencePackage.create(
                command=command,
                policy=policy,
                status=ControlledOperationalEvidenceStatus.OUTCOME_PENDING,
                evidence_references=self._package_references(
                    run_root=run_root,
                    inputs=inputs,
                    preparation=preparation,
                    research=research,
                    candidates=candidates,
                    coverage=coverage,
                    minute_path=minute_path,
                    minute=minute,
                    overlay_path=overlay_path,
                    overlay=overlay,
                    candidate_view_path=canonical_execution.candidate_view_path,
                    candidate_view_id=candidate_view.view_id,
                    candidate_view_hash=candidate_view.content_hash,
                    signal=signal_output,
                    forecasts=path_output,
                    entry_path=entry_path,
                    entry_id=entry.artifact_id,
                    entry_hash=entry.content_hash,
                    canonical_run=canonical_run,
                    canonical_run_path=canonical_run_path,
                ),
                stage_receipts=tuple(
                    item.receipt
                    for item in snapshot.stages
                    if item.receipt is not None and item.stage_name is not DecisionTimeOperationStageName.OPERATION_PACKAGE
                ),
                code_revision=command.code_revision,
                feature_set_id=configuration.static_feature_set.feature_set_id,
                signal_model_id=str(configuration.signal_model.model_id),
                signal_model_version=configuration.signal_model.model_version,
                configuration_hashes=configuration.configuration_hashes,
                universe_count=len(preparation.universe.symbols),
                candidate_count=len(candidates.selected),
                minute_success_count=coverage.succeeded_count,
                minute_failure_count=coverage.failed_count,
                signal_state_counts=tuple(
                    sorted(
                        Counter(
                            item.signal_state.value
                            for item in signal_output.artifact.snapshots
                        ).items()
                    )
                ),
                stage_latencies=tuple(StageRuntimeLatency(name, value) for name, value in sorted(latencies.items())),
                deadline_status=(
                    "RECOVERED_BEFORE_HARD_CUTOFF"
                    if resume_admitted_child
                    else "ON_TIME"
                    if not assessment.late_run
                    else "LATE_RUN"
                ),
                created_at=command.decision_time,
                authority_ceiling=(
                    "BROKER_NOT_INVOKED",
                    "ENTRY_MODEL_EMPIRICALLY_VALIDATED_FALSE",
                    "FORMAL_OOS_ALPHA_NOT_ESTABLISHED",
                    "NO_FILL_CREATED",
                    "NO_ORDER_CREATED",
                    "TRADING_AUTHORITY_NOT_GRANTED",
                ),
                limitations=(
                    "FORMAL_PIT_NOT_ESTABLISHED",
                    "OPERATIONAL_EXPLORATORY_ARCHIVE",
                    "OUTCOME_PENDING",
                    *(("PARTIAL_PROVIDER_FAILURE",) if coverage.failed_count else ()),
                ),
            )
            package_path = publish_controlled_operation_package(root=package_root, artifact=package)
        else:
            package_path = package_root / str(package.package_id)
        self._execute_stage(
            command=command,
            stage=DecisionTimeOperationStageName.OPERATION_PACKAGE,
            run_status=DecisionTimeOperationRunStatus.OUTCOME_PENDING,
            inputs=(_reference("ENTRY_BLOCKER", entry.artifact_id, entry.content_hash),),
            outputs=(_reference("OPERATION_PACKAGE", package.package_id, package.content_hash),),
            reasons=("CONTROLLED_OPERATION_PACKAGE_OUTCOME_PENDING",),
            latency_sink=latencies,
        )
        return ControlledOperationDecisionResult(
            snapshot=self._journal.get(command.run_id),
            research=research,
            candidate_set=candidates,
            minute_coverage=coverage,
            minute_dataset=minute,
            minute_dataset_path=minute_path,
            intraday_feature_bundle=intraday_features,
            intraday_feature_receipt=intraday_receipt,
            overlay=overlay,
            overlay_path=overlay_path,
            signal=signal_output,
            forecasts=path_output,
            entry_blocker_path=entry_path,
            package=package,
            package_path=package_path,
        )

    def resume(
        self,
        *,
        command: ControlledOperationCommand,
        policy: DecisionTimeOperationPolicy,
        inputs: ControlledOperationInputPaths,
    ) -> ControlledOperationDecisionResult:
        self._journal.resume(command.run_id)
        return self.run_decision_window(
            command=command,
            policy=policy,
            inputs=inputs,
            _resume_admitted_child=True,
        )

    def settle(
        self,
        *,
        command: ControlledOperationCommand,
        inputs: ControlledOperationSettlementInputPaths,
        horizon: TradeHorizonDefinition | None = None,
    ) -> ControlledOperationSettlementResult:
        """Attach immutable T+1 facts and index the superseding settled package."""

        command.verify_identity()
        run_root = self._run_root(command)
        pending = _find_operation_package(
            run_root / "operation-packages",
            command.run_id,
            status=ControlledOperationalEvidenceStatus.OUTCOME_PENDING,
        )
        if pending is None:
            raise ControlledOperationDataBlocked("OUTCOME_PENDING_PACKAGE_MISSING")
        if pending.command != command:
            raise ValueError("Outcome settlement command conflicts with pending package")
        settled = _find_operation_package(
            run_root / "operation-packages",
            command.run_id,
            status=ControlledOperationalEvidenceStatus.SETTLED,
        )
        inputs = _freeze_settlement_input_paths(run_root=run_root, inputs=inputs)
        source_archive = load_outcome_settlement_source_archive(
            inputs.outcome_source_archive
        )
        source_manifest = load_controlled_source_manifest(inputs.outcome_source_manifest)
        settlement_dataset = load_verified_market_data_dataset(inputs.outcome_dataset)
        if (
            source_archive.source_manifest_id != source_manifest.source_manifest_id
            or source_archive.source_manifest_hash != source_manifest.content_hash
        ):
            raise ValueError("Outcome source Archive and SourceManifest lineage mismatch")
        if (
            source_manifest.source_manifest_id,
            source_manifest.content_hash,
        ) not in settlement_dataset.artifact.source_manifest_references:
            raise ValueError("Outcome Dataset and SourceManifest lineage mismatch")
        replayed_settlement = replay_outcome_dataset_from_source_archive(
            archive_path=inputs.outcome_source_archive,
            source_manifest=source_manifest,
            expected_dataset=settlement_dataset,
        )
        if (
            replayed_settlement.to_canonical_dict()
            != settlement_dataset.artifact.to_canonical_dict()
        ):
            raise ValueError("Outcome Dataset does not match immutable raw source archive")
        if source_manifest.decision_time.value <= command.decision_time:
            raise ValueError("Outcome SourceManifest must be subsequent to DecisionTime")
        if settled is not None:
            if settled.supersedes_package_id != pending.package_id or settled.supersedes_package_hash != pending.content_hash:
                raise ValueError("settled package supersession lineage mismatch")
            source_ref = next(item for item in settled.evidence_references if item.reference_type == "OUTCOME_SOURCE_MANIFEST")
            archive_ref = next(item for item in settled.evidence_references if item.reference_type == "OUTCOME_SOURCE_ARCHIVE")
            dataset_ref = next(item for item in settled.evidence_references if item.reference_type == "OUTCOME_DATASET")
            if (
                archive_ref.object_id != source_archive.artifact_id
                or archive_ref.content_hash != source_archive.content_hash
                or source_ref.object_id != source_manifest.source_manifest_id
                or source_ref.content_hash != source_manifest.content_hash
                or dataset_ref.object_id != ArtifactId(str(settlement_dataset.artifact.dataset_id))
                or dataset_ref.content_hash != settlement_dataset.artifact.content_hash
            ):
                raise ValueError("settled package input identity conflict")
            settled_path = run_root / "operation-packages" / str(settled.package_id)
            outcome_path = _evidence_path(run_root, settled, "OUTCOME_OBSERVATION")
            outcome = load_trade_horizon_outcome_evidence(outcome_path)
            longitudinal_record = self._longitudinal_index.append(
                package=settled,
                package_locator=settled_path.relative_to(self._output_root).as_posix(),
            )
            return ControlledOperationSettlementResult(
                snapshot=self._journal.get(command.run_id),
                outcome=outcome,
                outcome_path=outcome_path,
                package=settled,
                package_path=settled_path,
                longitudinal_record=longitudinal_record,
            )

        calendar = load_controlled_trading_calendar(_evidence_path(run_root, pending, "TRADING_CALENDAR"))
        next_sessions = tuple(item.trade_date for item in calendar.sessions if item.trade_date > command.decision_date)
        if not next_sessions:
            raise ControlledOperationDataBlocked("NEXT_TRADING_SESSION_UNAVAILABLE")
        next_session_date = min(next_sessions)
        if source_archive.next_session_date != next_session_date:
            raise ValueError("Outcome source Archive next-session mismatch")
        if settlement_dataset.artifact.decision_time < source_manifest.decision_time.value:
            raise ValueError("Outcome Dataset predates its SourceManifest authority")

        research = load_verified_controlled_research_artifact(_evidence_path(run_root, pending, "CONTROLLED_RESEARCH"))
        candidates = research.artifact.candidate_set
        signal = load_verified_signal_run_v3(_evidence_path(run_root, pending, "SIGNAL_V3"))
        forecasts = tuple(load_verified_path_forecast(path) for path in _evidence_paths(run_root, pending, "PATH_FORECAST"))
        decision_dataset = load_verified_market_data_dataset(_evidence_path(run_root, pending, "DAILY_DATASET"))
        horizon = horizon or TradeHorizonDefinition.create()
        started = perf_counter()
        outcome = build_trade_horizon_outcome_evidence(
            operation_package=pending,
            candidate_set=candidates,
            signal=signal,
            forecasts=forecasts,
            decision_dataset=decision_dataset,
            settlement_dataset=settlement_dataset,
            next_session_date=next_session_date,
            horizon=horizon,
            created_at=self._now(),
        )
        outcome_path = publish_trade_horizon_outcome_evidence(root=run_root / "outcomes", artifact=outcome)
        settlement_elapsed = int((perf_counter() - started) * 1000)
        self._execute_stage(
            command=command,
            stage=DecisionTimeOperationStageName.OUTCOME_SETTLEMENT,
            run_status=DecisionTimeOperationRunStatus.SETTLED,
            inputs=(
                _reference("OPERATION_PACKAGE", pending.package_id, pending.content_hash),
                _reference(
                    "OUTCOME_SOURCE_ARCHIVE",
                    source_archive.artifact_id,
                    source_archive.content_hash,
                ),
                _reference(
                    "OUTCOME_SOURCE_MANIFEST",
                    source_manifest.source_manifest_id,
                    source_manifest.content_hash,
                ),
                _reference(
                    "OUTCOME_DATASET",
                    settlement_dataset.artifact.dataset_id,
                    settlement_dataset.artifact.content_hash,
                ),
            ),
            outputs=(_reference("OUTCOME_OBSERVATION", outcome.artifact_id, outcome.content_hash),),
            child_runs=(
                OperationChildRunReference(
                    ChildRunReferenceKind.OUTCOME_RUN,
                    str(outcome.artifact_id),
                    outcome.content_hash,
                ),
            ),
            reasons=("T_PLUS_ONE_FACTUAL_OUTCOME_ARCHIVED",),
            latency_sink={},
            premeasured=True,
        )
        if settled is None:
            evidence = (
                *pending.evidence_references,
                _evidence(
                    "OUTCOME_SOURCE_ARCHIVE",
                    source_archive.artifact_id,
                    source_archive.content_hash,
                    inputs.outcome_source_archive,
                    run_root,
                ),
                _evidence(
                    "OUTCOME_SOURCE_MANIFEST",
                    source_manifest.source_manifest_id,
                    source_manifest.content_hash,
                    inputs.outcome_source_manifest,
                    run_root,
                ),
                _evidence(
                    "OUTCOME_DATASET",
                    settlement_dataset.artifact.dataset_id,
                    settlement_dataset.artifact.content_hash,
                    inputs.outcome_dataset,
                    run_root,
                ),
                _evidence(
                    "OUTCOME_OBSERVATION",
                    outcome.artifact_id,
                    outcome.content_hash,
                    outcome_path,
                    run_root,
                ),
            )
            snapshot = self._journal.get(command.run_id)
            limitations = tuple(
                sorted(
                    {
                        *(item for item in pending.limitations if item != "OUTCOME_PENDING"),
                        "FACTUAL_OUTCOME_ARCHIVED_NOT_H9_VALIDATION",
                        "SETTLED",
                    }
                )
            )
            latencies = {item.stage_name: item.elapsed_ms for item in pending.stage_latencies}
            latencies[DecisionTimeOperationStageName.OUTCOME_SETTLEMENT.value] = settlement_elapsed
            settled = ControlledOperationalEvidencePackage.create(
                command=command,
                policy=pending.policy,
                status=ControlledOperationalEvidenceStatus.SETTLED,
                evidence_references=tuple(evidence),
                stage_receipts=tuple(item.receipt for item in snapshot.stages if item.receipt is not None),
                code_revision=pending.code_revision,
                feature_set_id=pending.feature_set_id,
                signal_model_id=pending.signal_model_id,
                signal_model_version=pending.signal_model_version,
                configuration_hashes=pending.configuration_hashes,
                universe_count=pending.universe_count,
                candidate_count=pending.candidate_count,
                minute_success_count=pending.minute_success_count,
                minute_failure_count=pending.minute_failure_count,
                signal_state_counts=pending.signal_state_counts,
                stage_latencies=tuple(StageRuntimeLatency(name, value) for name, value in sorted(latencies.items())),
                deadline_status=pending.deadline_status,
                created_at=self._now(),
                authority_ceiling=pending.authority_ceiling,
                limitations=limitations,
                supersedes_package_id=pending.package_id,
                supersedes_package_hash=pending.content_hash,
            )
            settled_path = publish_controlled_operation_package(root=run_root / "operation-packages", artifact=settled)
        else:
            if settled.supersedes_package_id != pending.package_id or settled.supersedes_package_hash != pending.content_hash:
                raise ValueError("settled package supersession lineage mismatch")
            settled_path = run_root / "operation-packages" / str(settled.package_id)

        locator = settled_path.relative_to(self._output_root).as_posix()
        longitudinal_record = self._longitudinal_index.append(
            package=settled,
            package_locator=locator,
        )
        return ControlledOperationSettlementResult(
            snapshot=self._journal.get(command.run_id),
            outcome=outcome,
            outcome_path=outcome_path,
            package=settled,
            package_path=settled_path,
            longitudinal_record=longitudinal_record,
        )

    def _execute_stage(
        self,
        *,
        command: ControlledOperationCommand,
        stage: DecisionTimeOperationStageName,
        run_status: DecisionTimeOperationRunStatus,
        inputs: tuple[OperationArtifactReference, ...],
        outputs: tuple[OperationArtifactReference, ...],
        reasons: tuple[str, ...],
        latency_sink: dict[str, int],
        child_runs: tuple[OperationChildRunReference, ...] = (),
        premeasured: bool = False,
    ) -> DecisionTimeOperationReceipt:
        snapshot = self._journal.get(command.run_id)
        stage_snapshot = next(item for item in snapshot.stages if item.stage_name is stage)
        if stage_snapshot.status is DecisionTimeOperationStageStatus.COMPLETED:
            assert stage_snapshot.receipt is not None
            expected_inputs = tuple(
                sorted(inputs, key=lambda item: (item.reference_type, str(item.object_id)))
            )
            expected_outputs = tuple(
                sorted(outputs, key=lambda item: (item.reference_type, str(item.object_id)))
            )
            expected_children = tuple(
                sorted(
                    child_runs,
                    key=lambda item: (item.reference_kind.value, item.child_run_id),
                )
            )
            if (
                stage_snapshot.receipt.input_references != expected_inputs
                or stage_snapshot.receipt.output_references != expected_outputs
                or stage_snapshot.receipt.child_run_references != expected_children
                or stage_snapshot.receipt.reason_codes != tuple(sorted(set(reasons)))
            ):
                raise ValueError(f"completed {stage.value} Receipt conflicts with replayed evidence")
            return stage_snapshot.receipt
        started = perf_counter()
        claim = self._journal.claim_stage(run_id=command.run_id, stage_name=stage)
        try:
            receipt = DecisionTimeOperationReceipt.create(
                run_id=command.run_id,
                stage_name=stage,
                attempt_number=claim.attempt_number,
                input_references=inputs,
                output_references=outputs,
                child_run_references=child_runs,
                reason_codes=reasons,
                created_at=self._now(),
            )
            self._journal.complete_stage(claim=claim, receipt=receipt, run_status=run_status)
        except Exception as exc:
            self._fail_claim(claim, exc)
            raise
        if not premeasured:
            latency_sink[stage.value] = int((perf_counter() - started) * 1000)
        return receipt

    def _fail_claim(self, claim: ClaimedDecisionTimeOperationStage, exc: Exception) -> None:
        try:
            self._journal.fail_stage(claim=claim, error=f"{type(exc).__name__}:{exc}")
        except Exception:
            pass

    def _package_references(
        self,
        *,
        run_root: Path,
        inputs: ControlledOperationInputPaths,
        preparation: ControlledOperationPreparation,
        research: VerifiedControlledResearchArtifact,
        candidates: CandidateSet,
        coverage: MinuteAcquisitionCoverageArtifact,
        minute_path: Path,
        minute: VerifiedMarketDataDataset,
        overlay_path: Path,
        overlay: CandidateIntradayFeatureOverlay,
        candidate_view_path: Path,
        candidate_view_id: ArtifactId,
        candidate_view_hash: str,
        signal: VerifiedSignalRunArtifactV3,
        forecasts: tuple[VerifiedPathForecastArtifact, ...],
        entry_path: Path,
        entry_id: ArtifactId,
        entry_hash: str,
        canonical_run: ControlledCanonicalLifecycleRunReceipt,
        canonical_run_path: Path,
    ) -> tuple[ControlledEvidenceReference, ...]:
        daily_source = load_verified_public_source_stage_artifact(inputs.daily_source_stage)
        source_manifest = load_controlled_source_manifest(inputs.daily_source_manifest)
        items = [
            _evidence(
                "TRADING_CALENDAR", preparation.calendar.artifact_id, preparation.calendar.content_hash, inputs.trading_calendar, run_root
            ),
            _evidence(
                "OPERATIONAL_UNIVERSE",
                preparation.universe.universe_id,
                preparation.universe.content_hash,
                inputs.operational_universe,
                run_root,
            ),
            _evidence(
                "DAILY_SOURCE_ARCHIVE",
                daily_source.artifact_id,
                daily_source.content_hash,
                inputs.daily_source_stage,
                run_root,
            ),
            _evidence(
                "DAILY_SOURCE_MANIFEST",
                source_manifest.source_manifest_id,
                source_manifest.content_hash,
                inputs.daily_source_manifest,
                run_root,
            ),
            _evidence(
                "DAILY_DATASET",
                preparation.daily_dataset.artifact.dataset_id,
                preparation.daily_dataset.artifact.content_hash,
                preparation.daily_dataset_path,
                run_root,
            ),
            _evidence(
                "STATIC_FEATURE_BUNDLE",
                preparation.static_bundle.artifact_id,
                preparation.static_bundle.content_hash,
                preparation.static_bundle_path,
                run_root,
            ),
            _evidence("CONTROLLED_RESEARCH", research.artifact.artifact_id, research.artifact.content_hash, research.root, run_root),
            _evidence("CANDIDATE_SET", candidates.envelope.artifact_id, candidates.envelope.content_hash, research.root, run_root),
            _evidence(
                "MINUTE_ACQUISITION_COVERAGE",
                coverage.artifact_id,
                coverage.content_hash,
                run_root / "minute-acquisition" / "coverage" / str(coverage.artifact_id),
                run_root,
            ),
            _evidence("MINUTE_DATASET", minute.artifact.dataset_id, minute.artifact.content_hash, minute_path, run_root),
            _evidence("INTRADAY_FEATURE_OVERLAY", overlay.artifact_id, overlay.content_hash, overlay_path, run_root),
            _evidence("CANDIDATE_FEATURE_VIEW_V2", candidate_view_id, candidate_view_hash, candidate_view_path, run_root),
            _evidence("SIGNAL_V3", signal.artifact.artifact_id, signal.artifact.envelope.content_hash, signal.root, run_root),
            _evidence("ENTRY_BLOCKER", entry_id, entry_hash, entry_path, run_root),
            _evidence(
                "CANONICAL_LIFECYCLE_RUN",
                canonical_run.run_id,
                canonical_run.content_hash,
                canonical_run_path,
                run_root,
            ),
        ]
        items.extend(
            _evidence("PATH_FORECAST", item.artifact.artifact_id, item.artifact.forecast.envelope.content_hash, item.root, run_root)
            for item in forecasts
        )
        return tuple(sorted(items, key=lambda item: (item.reference_type, str(item.object_id))))

    def _publish_terminal_package(
        self,
        *,
        command: ControlledOperationCommand,
        policy: DecisionTimeOperationPolicy,
        inputs: ControlledOperationInputPaths,
        preparation: ControlledOperationPreparation,
        configuration: ControlledOperationRuntimeConfiguration,
        status: ControlledOperationalEvidenceStatus,
        deadline_status: str,
        reason_codes: tuple[str, ...],
        latencies: dict[str, int],
        research: VerifiedControlledResearchArtifact | None = None,
        candidates: CandidateSet | None = None,
        coverage: MinuteAcquisitionCoverageArtifact | None = None,
        minute: VerifiedMarketDataDataset | None = None,
        minute_path: Path | None = None,
        overlay: CandidateIntradayFeatureOverlay | None = None,
        overlay_path: Path | None = None,
    ) -> tuple[ControlledOperationalEvidencePackage, Path]:
        run_root = self._run_root(command)
        package_root = run_root / "operation-packages"
        existing = _find_operation_package(package_root, command.run_id, status=status)
        if existing is not None:
            return existing, package_root / str(existing.package_id)
        daily_source = load_verified_public_source_stage_artifact(inputs.daily_source_stage)
        source_manifest = load_controlled_source_manifest(inputs.daily_source_manifest)
        references = [
            _evidence(
                "TRADING_CALENDAR",
                preparation.calendar.artifact_id,
                preparation.calendar.content_hash,
                inputs.trading_calendar,
                run_root,
            ),
            _evidence(
                "OPERATIONAL_UNIVERSE",
                preparation.universe.universe_id,
                preparation.universe.content_hash,
                inputs.operational_universe,
                run_root,
            ),
            _evidence(
                "DAILY_SOURCE_ARCHIVE",
                daily_source.artifact_id,
                daily_source.content_hash,
                inputs.daily_source_stage,
                run_root,
            ),
            _evidence(
                "DAILY_SOURCE_MANIFEST",
                source_manifest.source_manifest_id,
                source_manifest.content_hash,
                inputs.daily_source_manifest,
                run_root,
            ),
            _evidence(
                "DAILY_DATASET",
                preparation.daily_dataset.artifact.dataset_id,
                preparation.daily_dataset.artifact.content_hash,
                preparation.daily_dataset_path,
                run_root,
            ),
            _evidence(
                "STATIC_FEATURE_BUNDLE",
                preparation.static_bundle.artifact_id,
                preparation.static_bundle.content_hash,
                preparation.static_bundle_path,
                run_root,
            ),
        ]
        if research is not None and candidates is not None:
            references.extend(
                (
                    _evidence(
                        "CONTROLLED_RESEARCH",
                        research.artifact.artifact_id,
                        research.artifact.content_hash,
                        research.root,
                        run_root,
                    ),
                    _evidence(
                        "CANDIDATE_SET",
                        candidates.envelope.artifact_id,
                        candidates.envelope.content_hash,
                        research.root,
                        run_root,
                    ),
                )
            )
        if coverage is not None:
            references.append(
                _evidence(
                    "MINUTE_ACQUISITION_COVERAGE",
                    coverage.artifact_id,
                    coverage.content_hash,
                    run_root / "minute-acquisition" / "coverage" / str(coverage.artifact_id),
                    run_root,
                )
            )
        if minute is not None and minute_path is not None:
            references.append(
                _evidence(
                    "MINUTE_DATASET",
                    minute.artifact.dataset_id,
                    minute.artifact.content_hash,
                    minute_path,
                    run_root,
                )
            )
        if overlay is not None and overlay_path is not None:
            references.append(
                _evidence(
                    "INTRADAY_FEATURE_OVERLAY",
                    overlay.artifact_id,
                    overlay.content_hash,
                    overlay_path,
                    run_root,
                )
            )
        snapshot = self._journal.get(command.run_id)
        candidate_count = len(candidates.selected) if candidates is not None else 0
        package = ControlledOperationalEvidencePackage.create(
            command=command,
            policy=policy,
            status=status,
            evidence_references=tuple(references),
            stage_receipts=tuple(item.receipt for item in snapshot.stages if item.receipt is not None),
            code_revision=command.code_revision,
            feature_set_id=configuration.static_feature_set.feature_set_id,
            signal_model_id=str(configuration.signal_model.model_id),
            signal_model_version=configuration.signal_model.model_version,
            configuration_hashes=configuration.configuration_hashes,
            universe_count=len(preparation.universe.symbols),
            candidate_count=candidate_count,
            minute_success_count=(coverage.succeeded_count if coverage is not None else 0),
            minute_failure_count=(candidate_count - coverage.succeeded_count if coverage is not None else candidate_count),
            signal_state_counts=(),
            stage_latencies=tuple(StageRuntimeLatency(name, value) for name, value in sorted(latencies.items())),
            deadline_status=deadline_status,
            created_at=command.decision_time,
            authority_ceiling=(
                "BROKER_NOT_INVOKED",
                "ENTRY_MODEL_EMPIRICALLY_VALIDATED_FALSE",
                "FORMAL_OOS_ALPHA_NOT_ESTABLISHED",
                "NO_FILL_CREATED",
                "NO_ORDER_CREATED",
                "TRADING_AUTHORITY_NOT_GRANTED",
            ),
            limitations=tuple(
                sorted(
                    {
                        "CONTROLLED_OPERATION_FAILED_CLOSED",
                        "FORMAL_PIT_NOT_ESTABLISHED",
                        status.value,
                        *reason_codes,
                    }
                )
            ),
        )
        path = publish_controlled_operation_package(root=package_root, artifact=package)
        return package, path

    def _reject_decision_window_deadline(
        self,
        *,
        command: ControlledOperationCommand,
        policy: DecisionTimeOperationPolicy,
        inputs: ControlledOperationInputPaths,
        preparation: ControlledOperationPreparation,
        configuration: ControlledOperationRuntimeConfiguration,
        reason: str,
        latencies: dict[str, int],
        research: VerifiedControlledResearchArtifact,
        candidates: CandidateSet,
        coverage: MinuteAcquisitionCoverageArtifact,
        minute: VerifiedMarketDataDataset,
        minute_path: Path,
        overlay: CandidateIntradayFeatureOverlay,
        overlay_path: Path,
    ) -> NoReturn:
        self._publish_terminal_package(
            command=command,
            policy=policy,
            inputs=inputs,
            preparation=preparation,
            configuration=configuration,
            status=ControlledOperationalEvidenceStatus.DEADLINE_MISSED,
            deadline_status=DecisionWindowState.DEADLINE_MISSED.value,
            reason_codes=(reason,),
            latencies=latencies,
            research=research,
            candidates=candidates,
            coverage=coverage,
            minute=minute,
            minute_path=minute_path,
            overlay=overlay,
            overlay_path=overlay_path,
        )
        snapshot = self._journal.get(command.run_id)
        self._journal.set_run_status(
            run_id=command.run_id,
            expected_version=snapshot.version,
            status=DecisionTimeOperationRunStatus.DEADLINE_MISSED,
            reason=reason,
        )
        raise ControlledOperationDataBlocked(reason)

    def _validate_command(
        self,
        command: ControlledOperationCommand,
        policy: DecisionTimeOperationPolicy,
        calendar: TradingCalendarArtifact,
        configuration: ControlledOperationRuntimeConfiguration,
    ) -> None:
        command.verify_identity()
        policy.verify_identity()
        configuration.verify_identity()
        if command.decision_time != policy.decision_instant(command.decision_date):
            raise ValueError("Controlled command DecisionTime differs from policy")
        if (
            command.policy_id != policy.policy_id
            or command.policy_hash != policy.content_hash
            or command.trading_calendar_id != calendar.artifact_id
            or command.trading_calendar_hash != calendar.content_hash
            or command.configuration_manifest_id != configuration.configuration_id
            or command.configuration_manifest_hash != configuration.configuration_hash
            or command.model_manifest_id != configuration.model_manifest_id
            or command.model_manifest_hash != configuration.model_manifest_hash
        ):
            raise ValueError("Controlled command authority binding mismatch")
        if (
            configuration.signal_freshness.trading_calendar_id != calendar.artifact_id
            or configuration.signal_freshness.trading_calendar_hash != calendar.content_hash
        ):
            raise ValueError("Controlled Signal Freshness Calendar mismatch")
        expected_path_time = policy.decision_time.strftime("%H:%M")
        if configuration.path_forecast.decision_time_local != expected_path_time:
            raise ValueError("Controlled PathForecast DecisionTime profile mismatch")

    def _run_root(self, command: ControlledOperationCommand) -> Path:
        return self._output_root / str(command.run_id)

    def _canonical_child_was_admitted(
        self,
        *,
        command: ControlledOperationCommand,
        observed_at: datetime,
        hard_cutoff: datetime,
    ) -> bool:
        """Admit only a frozen, already-started child to resume before cutoff."""

        if not (command.decision_time <= observed_at <= hard_cutoff):
            return False
        snapshot = self._journal.get(command.run_id)
        if snapshot.status is not DecisionTimeOperationRunStatus.DECISION_WINDOW_RUNNING:
            return False
        required = {
            DecisionTimeOperationStageName.CALENDAR_UNIVERSE_FREEZE,
            DecisionTimeOperationStageName.DAILY_SOURCE_FREEZE,
            DecisionTimeOperationStageName.DAILY_DATASET,
            DecisionTimeOperationStageName.STATIC_FEATURES,
            DecisionTimeOperationStageName.OPERATIONAL_RESEARCH,
            DecisionTimeOperationStageName.CANDIDATE_SET,
            DecisionTimeOperationStageName.CANDIDATE_MINUTE_ACQUISITION,
            DecisionTimeOperationStageName.INTRADAY_DATASET,
            DecisionTimeOperationStageName.INTRADAY_FEATURE_OVERLAY,
        }
        completed = {
            item.stage_name
            for item in snapshot.stages
            if item.status is DecisionTimeOperationStageStatus.COMPLETED
        }
        if not required.issubset(completed):
            return False
        database_path = self._run_root(command) / "canonical-lifecycle.sqlite3"
        try:
            repository = self._canonical_repository_factory(database_path, True)
            child_run = repository.get_run_by_idempotency_key(
                f"{command.idempotency_key}:canonical-controlled-v2"
            )
            if child_run is None:
                return False
            child_command = repository.get_command(child_run.run_id)
        except (OSError, ValueError):
            return False
        if (
            child_run.created_at > command.decision_time
            or child_run.command_hash != child_command.command_hash
            or child_command.run_id != child_run.run_id
            or child_command.run_type
            is not LifecycleRunType.CANONICAL_DECISION_LIFECYCLE
            or child_command.decision_date != command.decision_date
            or child_command.as_of_time != command.decision_time
            or child_command.input_manifest_id is not None
            or child_command.output_directory
            != (self._run_root(command) / "canonical-lifecycle" / "outputs").resolve()
            or any(
                item.available_at > command.decision_time
                for item in child_command.input_references
            )
        ):
            return False
        parent_to_child_type = {
            "TRADING_CALENDAR": LifecycleObjectType.TRADING_CALENDAR_ARTIFACT,
            "OPERATIONAL_UNIVERSE": LifecycleObjectType.OPERATIONAL_UNIVERSE,
            "DAILY_SOURCE_MANIFEST": LifecycleObjectType.SOURCE_MANIFEST,
            "DAILY_DATASET": LifecycleObjectType.MARKET_DATA_DATASET,
            "STATIC_FEATURE_BUNDLE": (
                LifecycleObjectType.STATIC_UNIVERSE_FEATURE_BUNDLE
            ),
            "MINUTE_DATASET": LifecycleObjectType.MARKET_DATA_DATASET,
            "INTRADAY_FEATURE_OVERLAY": (
                LifecycleObjectType.CANDIDATE_INTRADAY_FEATURE_OVERLAY
            ),
        }
        frozen_parent_objects = {
            (
                parent_to_child_type[reference.reference_type],
                str(reference.object_id),
                reference.content_hash,
            )
            for stage in snapshot.stages
            if stage.receipt is not None
            for reference in stage.receipt.output_references
            if reference.reference_type in parent_to_child_type
        }
        child_objects = {
            (item.object_type, str(item.object_id), item.content_hash)
            for item in child_command.input_references
        }
        return frozen_parent_objects.issubset(child_objects)

    def _outcome_pending_operation_is_complete(
        self,
        command: ControlledOperationCommand,
    ) -> bool:
        """Recognize a completed immutable package before consulting wall time."""

        snapshot = self._journal.get(command.run_id)
        if snapshot.status is not DecisionTimeOperationRunStatus.OUTCOME_PENDING:
            return False
        package_stage = next(
            item
            for item in snapshot.stages
            if item.stage_name is DecisionTimeOperationStageName.OPERATION_PACKAGE
        )
        if package_stage.status is not DecisionTimeOperationStageStatus.COMPLETED:
            return False
        package = _find_operation_package(
            self._run_root(command) / "operation-packages",
            command.run_id,
            status=ControlledOperationalEvidenceStatus.OUTCOME_PENDING,
        )
        if package is None:
            raise ValueError("OUTCOME_PENDING run is missing its immutable package")
        if package.command != command:
            raise ValueError("OUTCOME_PENDING package command conflicts with journal")
        return True

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Controlled operation clock must be timezone-aware")
        return value.astimezone(timezone.utc).replace(microsecond=0)


def _run_feature_materialization(
    *,
    verified_dataset: VerifiedMarketDataDataset,
    feature_set: object,
    selected_symbols: tuple[str, ...],
    code_revision: str,
    output_root: Path,
    idempotency_key: str,
    max_workers: int,
    repository_factory: FeatureRunRepositoryFactory | None,
) -> FeatureMaterializationReceipt:
    runner = FeatureMaterializationRunner(
        max_workers=max_workers,
        repository_factory=repository_factory,
    )
    common = {
        "verified_dataset": verified_dataset,
        "feature_set": feature_set,
        "decision_time": verified_dataset.artifact.decision_time,
        "created_at": verified_dataset.artifact.created_at,
        "selected_symbols": selected_symbols,
        "code_revision": code_revision,
        "output_root": output_root,
        "idempotency_key": idempotency_key,
    }
    try:
        return runner.run(**common, execution_mode=FeatureMaterializationExecutionMode.START_NEW)  # type: ignore[arg-type]
    except ValueError as exc:
        if "already exists" not in str(exc):
            raise
    try:
        return runner.run(**common, execution_mode=FeatureMaterializationExecutionMode.RETURN_IF_COMPLETE)  # type: ignore[arg-type]
    except ValueError as exc:
        if "not complete" not in str(exc):
            raise
    return runner.run(**common, execution_mode=FeatureMaterializationExecutionMode.RESUME_EXISTING)  # type: ignore[arg-type]


def _reference(reference_type: str, object_id: object, content_hash: str) -> OperationArtifactReference:
    return OperationArtifactReference(
        reference_type=reference_type,
        object_id=ArtifactId(str(object_id)),
        content_hash=content_hash,
    )


def _evidence(
    reference_type: str,
    object_id: object,
    content_hash: str,
    path: Path,
    run_root: Path,
) -> ControlledEvidenceReference:
    try:
        locator = path.resolve().relative_to(run_root.resolve()).as_posix()
    except ValueError:
        locator = (Path("external-inputs") / reference_type.lower() / str(object_id)).as_posix()
    return ControlledEvidenceReference(
        reference_type=reference_type,
        object_id=ArtifactId(str(object_id)),
        content_hash=content_hash,
        locator=locator,
    )


def _find_operation_package(
    root: Path,
    run_id: ArtifactId,
    *,
    status: ControlledOperationalEvidenceStatus | None = None,
) -> ControlledOperationalEvidencePackage | None:
    if not root.exists():
        return None
    matches = tuple(
        artifact
        for path in sorted(root.iterdir())
        if path.is_dir() and not path.name.startswith(".")
        for artifact in (load_controlled_operation_package(path),)
        if artifact.command.run_id == run_id and (status is None or artifact.status is status)
    )
    by_status = {item.status: item for item in matches}
    if len(by_status) != len(matches):
        raise ValueError("multiple Controlled operation packages share one status and run")
    pending = by_status.get(ControlledOperationalEvidenceStatus.OUTCOME_PENDING)
    settled = by_status.get(ControlledOperationalEvidenceStatus.SETTLED)
    if (
        pending is not None
        and settled is not None
        and (settled.supersedes_package_id != pending.package_id or settled.supersedes_package_hash != pending.content_hash)
    ):
        raise ValueError("Controlled operation package supersession conflict")
    if status is not None:
        return by_status.get(status)
    return settled or pending or (matches[0] if matches else None)


def _evidence_paths(
    run_root: Path,
    package: ControlledOperationalEvidencePackage,
    reference_type: str,
) -> tuple[Path, ...]:
    references = tuple(item for item in package.evidence_references if item.reference_type == reference_type)
    if not references:
        raise ValueError(f"Controlled package reference missing: {reference_type}")
    paths = tuple((run_root / item.locator).resolve() for item in references)
    if any(run_root.resolve() not in (path, *path.parents) for path in paths):
        raise ValueError("Controlled package evidence locator escapes run root")
    return paths


def _evidence_path(
    run_root: Path,
    package: ControlledOperationalEvidencePackage,
    reference_type: str,
) -> Path:
    paths = _evidence_paths(run_root, package, reference_type)
    if len(paths) != 1:
        raise ValueError(f"Controlled package reference is not singular: {reference_type}")
    return paths[0]


def _completed_receipt(
    snapshot: DecisionTimeOperationRunSnapshot,
    stage: DecisionTimeOperationStageName,
) -> DecisionTimeOperationReceipt | None:
    item = next(value for value in snapshot.stages if value.stage_name is stage)
    return item.receipt if item.status is DecisionTimeOperationStageStatus.COMPLETED else None


def _freeze_input_paths(*, run_root: Path, inputs: ControlledOperationInputPaths) -> ControlledOperationInputPaths:
    frozen_root = run_root / "input-freeze"
    return ControlledOperationInputPaths(
        trading_calendar=_install_input(
            source=inputs.trading_calendar,
            destination=frozen_root / "trading-calendar" / inputs.trading_calendar.name,
        ),
        operational_universe=_install_input(
            source=inputs.operational_universe,
            destination=frozen_root / "operational-universe" / inputs.operational_universe.name,
        ),
        daily_source_stage=_install_input(
            source=inputs.daily_source_stage,
            destination=frozen_root / "daily-source-stage" / inputs.daily_source_stage.name,
        ),
        daily_source_manifest=_install_input(
            source=inputs.daily_source_manifest,
            destination=frozen_root / "daily-source-manifest" / inputs.daily_source_manifest.name,
        ),
        supplemental_research_evidence=_install_input(
            source=inputs.supplemental_research_evidence,
            destination=(frozen_root / "supplemental-research-evidence" / inputs.supplemental_research_evidence.name),
        ),
        runtime_configuration=_install_input(
            source=inputs.runtime_configuration,
            destination=frozen_root / "runtime-configuration" / inputs.runtime_configuration.name,
        ),
    )


def _freeze_settlement_input_paths(
    *,
    run_root: Path,
    inputs: ControlledOperationSettlementInputPaths,
) -> ControlledOperationSettlementInputPaths:
    frozen_root = run_root / "input-freeze"
    return ControlledOperationSettlementInputPaths(
        outcome_source_archive=_install_input(
            source=inputs.outcome_source_archive,
            destination=(
                frozen_root
                / "outcome-source-archive"
                / inputs.outcome_source_archive.name
            ),
        ),
        outcome_source_manifest=_install_input(
            source=inputs.outcome_source_manifest,
            destination=(frozen_root / "outcome-source-manifest" / inputs.outcome_source_manifest.name),
        ),
        outcome_dataset=_install_input(
            source=inputs.outcome_dataset,
            destination=frozen_root / "outcome-dataset" / inputs.outcome_dataset.name,
        ),
    )


def _install_input(*, source: Path, destination: Path) -> Path:
    if not source.is_dir():
        raise ValueError(f"Controlled input package is missing: {source}")
    if destination.exists():
        if _directory_fingerprint(source) != _directory_fingerprint(destination):
            raise ValueError(f"Controlled frozen input identity conflict: {destination.parent.name}")
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = destination.parent / f".{destination.name}.staging"
    if stage.exists():
        shutil.rmtree(stage)
    shutil.copytree(source, stage, symlinks=False)
    try:
        stage.rename(destination)
    except FileExistsError:
        shutil.rmtree(stage)
    return destination


def _directory_fingerprint(root: Path) -> str:
    files = tuple(sorted(item for item in root.rglob("*") if item.is_file()))
    return canonical_hash(
        {
            "exact_file_set": [item.relative_to(root).as_posix() for item in files],
            "sha256": [sha256(item.read_bytes()).hexdigest() for item in files],
        }
    )


__all__ = [
    "ControlledDecisionTimeOperationRunner",
    "ControlledOperationDataBlocked",
    "ControlledOperationDecisionResult",
    "ControlledOperationInputPaths",
    "ControlledOperationPreparation",
    "ControlledOperationSettlementInputPaths",
    "ControlledOperationSettlementResult",
]
