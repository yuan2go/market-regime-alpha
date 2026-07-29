"""Run-first orchestration for the exploratory Phase D daily loop."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from hashlib import sha256
import json
from pathlib import Path

from market_regime_alpha.application.daily_loop.commands import (
    DailyRunCommand,
    DailyRunId,
    DailyRunIdentity,
    RunMode,
)
from market_regime_alpha.application.daily_loop.errors import OutcomeNotReadyError
from market_regime_alpha.application.daily_loop.repositories import (
    DailyRunRecord,
    DailyRunRepository,
    StageReceipt,
)
from market_regime_alpha.application.daily_loop.state import DailyRunStatus
from market_regime_alpha.core.identity import (
    ArtifactId,
    ExperimentId,
    ProviderId,
)
from market_regime_alpha.core.status import InputAvailabilityStatus
from market_regime_alpha.core.time import RetrievedAt
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.data.daily_quality import (
    DailyDataQualityStatus,
    DataQualityFinding,
    DataQualityReport,
    evaluate_daily_data_quality,
)
from market_regime_alpha.data.providers.public_composite import (
    PUBLIC_COMPOSITE_LIVE_PROFILE_ID,
    AcquiredReplaySource,
    AcquiredSourcePayload,
    PublicCompositeAcquisitionError,
    PublicCompositeBatch,
    PublicCompositeLiveProfile,
    PublicCompositeProviderResult,
    PublicCompositeReplayProfile,
    PublicCompositeRequest,
    SourceReplayArchiveReader,
    build_daily_control_source_evidence,
    build_public_source_manifest,
    publish_source_archive,
    source_archive_id,
)
from market_regime_alpha.data.source_manifest import SourceManifest
from market_regime_alpha.daily_decision.artifact import (
    DailyDecisionArtifactStatus,
    PhaseDDailyDecisionBundle,
    publish_phase_d_daily_decision_artifact,
)
from market_regime_alpha.daily_decision.entry import assess_entry_plumbing
from market_regime_alpha.daily_decision.outcome import (
    OutcomeSettlement,
    settle_mr1_1030_outcomes,
)
from market_regime_alpha.daily_decision.outcome_artifact import (
    VerifiedDailyReviewArtifact,
    daily_review_artifact_id,
    load_verified_daily_review_artifact,
    publish_daily_review_artifact,
)
from market_regime_alpha.daily_decision.reader import (
    VerifiedPhaseDDailyDecisionArtifact,
)
from market_regime_alpha.daily_decision.reader_registry import (
    load_verified_daily_decision_artifact,
)
from market_regime_alpha.daily_decision.recommendation import (
    project_candidate_recommendations,
)
from market_regime_alpha.daily_decision.snapshot import (
    DecisionPriceSnapshot,
    build_decision_price_snapshot,
)
from market_regime_alpha.daily_decision.target_adapter import (
    build_pending_mr1_candidate_dataset,
)
from market_regime_alpha.features.daily_pipeline import (
    DailyFeaturePipelineResult,
    materialize_public_daily_baseline_features,
)
from market_regime_alpha.platform.candidate_prediction_adapter import (
    B0_MOMENTUM_MODEL_ID,
    B1_BALANCED_MODEL_ID,
    b0_b1_model_definitions,
    publish_b0_b1_prediction_runs,
)
from market_regime_alpha.platform.contracts import (
    EvaluationProtocolId,
    ModelDefinition,
)
from market_regime_alpha.platform.model_registry import ModelRegistry
from market_regime_alpha.platform.prediction_artifacts import (
    publish_prediction_run_artifact,
)
from market_regime_alpha.platform.prediction_reader import (
    load_verified_prediction_run_artifact,
)
from market_regime_alpha.platform.prediction_run import PredictionRun
from market_regime_alpha.universe.daily_exploratory import (
    DailyUniversePolicy,
    reconcile_daily_universe,
    smoke_pool_policy_v1,
)
from market_regime_alpha.data_sources.a_share_bars import AShareDataError


DAILY_B0_B1_MODEL_SET_ID = "daily-b0-b1-v1"
DAILY_B0_B1_EVALUATION_PROTOCOL_ID = EvaluationProtocolId(
    "daily-b0-b1-1030-evaluation-v1"
)
DAILY_B0_B1_EXPERIMENT_PROTOCOL_IDS = {
    B0_MOMENTUM_MODEL_ID: ExperimentId("daily-b0-frozen-experiment-v1"),
    B1_BALANCED_MODEL_ID: ExperimentId("daily-b1-frozen-experiment-v1"),
}
MINIMUM_CANDIDATE_POPULATION = 5

Clock = Callable[[], datetime]
StageHook = Callable[[DailyRunStatus], None]


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class DailyLoopRunResult:
    """Observed Runtime Journal state plus verified Evidence Authority."""

    record: DailyRunRecord
    source_archive_path: Path
    decision_artifact: VerifiedPhaseDDailyDecisionArtifact


@dataclass(frozen=True, slots=True)
class DailyLoopSettlementResult:
    """Append-only settlement result over immutable T-day evidence."""

    record: DailyRunRecord
    review_artifact: VerifiedDailyReviewArtifact


class DailyLoopRunner:
    """Application service; domain models remain in their existing contexts."""

    def __init__(
        self,
        *,
        repository: DailyRunRepository,
        code_revision: str,
        live_profile: PublicCompositeLiveProfile | None = None,
        policy: DailyUniversePolicy | None = None,
        clock: Clock = _utc_now,
        after_stage_hook: StageHook | None = None,
    ) -> None:
        if not code_revision or code_revision != code_revision.strip():
            raise ValueError("code_revision must be a non-empty trimmed string")
        self._repository = repository
        self._code_revision = code_revision
        self._live_profile = live_profile
        self._policy = policy or smoke_pool_policy_v1()
        self._clock = clock
        self._after_stage_hook = after_stage_hook

    def run(
        self,
        command: DailyRunCommand,
        *,
        replay_archive_path: Path | None = None,
    ) -> DailyLoopRunResult:
        """Run or resume one request without re-acquiring a frozen source."""

        self._validate_command(command)
        record = self._repository.create_or_get(
            command,
            created_at=self._now(),
        )
        if record.status is DailyRunStatus.FAILED:
            record = self._repository.resume_failed(
                record.run_request_id,
                changed_at=self._now(),
            )
        try:
            if record.status in {
                DailyRunStatus.DATA_BLOCKED,
                DailyRunStatus.OUTCOME_PENDING,
                DailyRunStatus.REVIEW_PUBLISHED,
            }:
                return self._load_completed(record)
            acquired, source_archive_path, record = self._freeze_source(
                command=command,
                record=record,
                replay_archive_path=replay_archive_path,
            )
            quality_report = evaluate_daily_data_quality(
                manifest=acquired.source_manifest,
                required_symbols=self._policy.symbols,
            )
            decision_snapshot = build_decision_price_snapshot(
                provider_result=acquired.provider_result,
                source_manifest=acquired.source_manifest,
            )
            if quality_report.status is DailyDataQualityStatus.DATA_BLOCKED:
                return self._publish_blocked(
                    record=record,
                    acquired=acquired,
                    source_archive_path=source_archive_path,
                    quality_report=quality_report,
                    decision_snapshot=decision_snapshot,
                )
            reconciliation = reconcile_daily_universe(
                policy=self._policy,
                source_manifest=acquired.source_manifest,
                provider_result=acquired.provider_result,
            )
            record = self._advance(
                record,
                DailyRunStatus.UNIVERSE_READY,
                outputs=(
                    ArtifactId(str(reconciliation.universe_snapshot.universe_id)),
                ),
            )
            if len(reconciliation.population.symbols) < MINIMUM_CANDIDATE_POPULATION:
                return self._publish_blocked(
                    record=record,
                    acquired=acquired,
                    source_archive_path=source_archive_path,
                    quality_report=_blocked_report(
                        quality_report,
                        reason_code="CANDIDATE_POPULATION_INSUFFICIENT",
                    ),
                    decision_snapshot=decision_snapshot,
                )
            configuration_hash = _configuration_hash(command)
            feature_result = materialize_public_daily_baseline_features(
                reconciliation=reconciliation,
                provider_result=acquired.provider_result,
                code_revision=self._code_revision,
                config_hash=configuration_hash,
            )
            record = self._advance(
                record,
                DailyRunStatus.FEATURES_READY,
                outputs=tuple(
                    ArtifactId(str(item.materialization_id))
                    for item in feature_result.materializations
                ),
            )
            missing_features = _missing_feature_reasons(feature_result)
            if missing_features:
                return self._publish_blocked(
                    record=record,
                    acquired=acquired,
                    source_archive_path=source_archive_path,
                    quality_report=_blocked_report(
                        quality_report,
                        reason_code=missing_features[0],
                        additional_reason_codes=missing_features[1:],
                    ),
                    decision_snapshot=decision_snapshot,
                )
            dataset = build_pending_mr1_candidate_dataset(
                reconciliation=reconciliation,
                feature_result=feature_result,
                code_revision=self._code_revision,
                config_hash=configuration_hash,
            )
            definitions = b0_b1_model_definitions(dataset)
            registry = ModelRegistry()
            for definition in definitions.values():
                registry.register(definition)
            prediction_runs = publish_b0_b1_prediction_runs(
                dataset,
                model_definitions=definitions,
                evaluation_protocol_id=DAILY_B0_B1_EVALUATION_PROTOCOL_ID,
                experiment_protocol_ids=DAILY_B0_B1_EXPERIMENT_PROTOCOL_IDS,
                code_revision=self._code_revision,
            )
            for prediction_run in prediction_runs:
                _publish_or_verify_prediction(
                    root=command.output_root / "prediction_runs",
                    prediction_run=prediction_run,
                    model_definition=definitions[prediction_run.model_id],
                )
            record = self._advance(
                record,
                DailyRunStatus.PREDICTIONS_PUBLISHED,
                outputs=tuple(
                    item.prediction_run_id for item in prediction_runs
                ),
            )
            recommendations = project_candidate_recommendations(
                prediction_runs=prediction_runs,
                decision_snapshot=decision_snapshot,
                data_quality_report=quality_report,
            )
            entries = assess_entry_plumbing(
                recommendations=recommendations,
                prediction_runs=prediction_runs,
                decision_snapshot=decision_snapshot,
                source_manifest=acquired.source_manifest,
                data_quality_report=quality_report,
                eligibility_snapshot=reconciliation.eligibility_snapshot,
            )
            identity = _required_identity(record)
            bundle = PhaseDDailyDecisionBundle(
                status=DailyDecisionArtifactStatus.DECISION_PUBLISHED,
                run_identity=identity,
                source_archive_id=ArtifactId(source_archive_path.name),
                source_manifest=acquired.source_manifest,
                data_quality_report=quality_report,
                universe_snapshot=reconciliation.universe_snapshot,
                eligibility_snapshot=reconciliation.eligibility_snapshot,
                decision_price_snapshot=decision_snapshot,
                feature_definitions=feature_result.definitions,
                feature_materializations=feature_result.materializations,
                prediction_runs=prediction_runs,
                recommendations=recommendations,
                entry_assessments=entries,
            )
            verified = _publish_or_verify_daily_decision(
                root=command.output_root / "daily_decisions",
                bundle=bundle,
            )
            record = self._advance(
                record,
                DailyRunStatus.DECISION_PUBLISHED,
                outputs=(bundle.artifact_id,),
            )
            record = self._advance(
                record,
                DailyRunStatus.OUTCOME_PENDING,
                inputs=(bundle.artifact_id,),
                outputs=(bundle.artifact_id,),
            )
            return DailyLoopRunResult(
                record=record,
                source_archive_path=source_archive_path,
                decision_artifact=verified,
            )
        except Exception as exc:
            current = self._repository.get(record.run_request_id)
            if current.status not in {
                DailyRunStatus.DATA_BLOCKED,
                DailyRunStatus.REVIEW_PUBLISHED,
            }:
                self._repository.mark_failed(
                    current.run_request_id,
                    reason=f"{type(exc).__name__}:{exc}",
                    changed_at=self._now(),
                )
            raise

    def replay_daily_run(
        self,
        daily_run_id: DailyRunId,
    ) -> VerifiedPhaseDDailyDecisionArtifact:
        """Semantically replay one immutable Daily Decision Artifact."""

        record = self._repository.get_by_daily_run_id(daily_run_id)
        stage = (
            DailyRunStatus.DATA_BLOCKED
            if record.status is DailyRunStatus.DATA_BLOCKED
            else DailyRunStatus.DECISION_PUBLISHED
        )
        receipt = self._repository.get_stage_receipt(
            record.run_request_id,
            stage,
        )
        if receipt is None:
            raise ValueError(f"{stage.value} stage receipt is missing")
        artifact_id = next(
            (
                item
                for item in receipt.output_artifact_ids
                if str(item).startswith("daily-decision-")
            ),
            None,
        )
        if artifact_id is None:
            raise ValueError("Daily Decision Artifact receipt is missing")
        return load_verified_daily_decision_artifact(
            record.command.output_root / "daily_decisions" / str(artifact_id)
        )

    def settle_daily_run(
        self,
        daily_run_id: DailyRunId,
        *,
        settlement_archive_path: Path,
    ) -> DailyLoopSettlementResult:
        """Append MR1 10:30 Outcomes and DailyReview without mutating T."""

        record = self._repository.get_by_daily_run_id(daily_run_id)
        if record.status is DailyRunStatus.REVIEW_PUBLISHED:
            return DailyLoopSettlementResult(
                record=record,
                review_artifact=self._load_review(record),
            )
        if record.status is not DailyRunStatus.OUTCOME_PENDING:
            raise ValueError("only OUTCOME_PENDING runs can be settled")
        daily = self.replay_daily_run(daily_run_id)
        source = SourceReplayArchiveReader().read(settlement_archive_path)
        next_session_date = _next_session_date(
            decision_time=daily.bundle.source_manifest.decision_time.value,
            provider_result=source.provider_result,
        )
        settlement = settle_mr1_1030_outcomes(
            daily_decision_bundle=daily.bundle,
            daily_decision_artifact_id=daily.bundle.artifact_id,
            settlement_provider_result=source.provider_result,
            settlement_source_archive_id=ArtifactId(source.archive_id),
            next_session_date=next_session_date,
        )
        review = _publish_or_verify_daily_review(
            root=record.command.output_root / "daily_reviews",
            settlement=settlement,
        )
        record = self._advance(
            record,
            DailyRunStatus.REVIEW_PUBLISHED,
            inputs=(
                daily.bundle.artifact_id,
                ArtifactId(source.archive_id),
            ),
            outputs=(ArtifactId(review.artifact_id),),
        )
        return DailyLoopSettlementResult(
            record=record,
            review_artifact=review,
        )

    def report_daily_run(self, daily_run_id: DailyRunId) -> str:
        """Reconstruct the authoritative Markdown report for the latest stage."""

        record = self._repository.get_by_daily_run_id(daily_run_id)
        if record.status is DailyRunStatus.REVIEW_PUBLISHED:
            path = self._load_review(record).root / "report.md"
        else:
            path = self.replay_daily_run(daily_run_id).root / "report.md"
        return path.read_text(encoding="utf-8")

    def _freeze_source(
        self,
        *,
        command: DailyRunCommand,
        record: DailyRunRecord,
        replay_archive_path: Path | None,
    ) -> tuple[AcquiredReplaySource, Path, DailyRunRecord]:
        if record.daily_run_identity is not None:
            source_path = self._source_archive_path(record)
            return (
                SourceReplayArchiveReader().read(source_path),
                source_path,
                record,
            )
        if record.status is DailyRunStatus.CREATED:
            self._repository.begin_source_acquisition(
                record.run_request_id,
                changed_at=self._now(),
            )
            record = self._repository.get(record.run_request_id)
        if record.status is not DailyRunStatus.SOURCE_ACQUIRING:
            raise ValueError("run cannot acquire source from current status")
        request = self._provider_request(command)
        if command.run_mode is RunMode.REPLAY:
            if replay_archive_path is None:
                raise ValueError("REPLAY requires replay_archive_path")
            assert command.replay_source_manifest_id is not None
            acquired_input = PublicCompositeReplayProfile().acquire(
                archive_path=replay_archive_path,
                expected_source_manifest_id=command.replay_source_manifest_id,
            )
            provider_result = acquired_input.provider_result
            source_manifest = acquired_input.source_manifest
        else:
            provider_result, source_manifest = self._acquire_live(
                request,
                run_created_at=record.created_at,
            )
        source_path = _publish_or_verify_source(
            root=command.output_root / "source_archives",
            provider_result=provider_result,
            source_manifest=source_manifest,
        )
        acquired = SourceReplayArchiveReader().read(source_path)
        identity = DailyRunIdentity(
            run_request_id=record.run_request_id,
            run_request_hash=command.content_hash,
            code_revision=self._code_revision,
            configuration_hash=_configuration_hash(command),
            source_manifest_id=source_manifest.source_manifest_id,
            source_manifest_content_hash=source_manifest.content_hash,
            source_content_hashes=tuple(
                sorted(set(source_manifest.source_hashes))
            ),
        )
        record = self._repository.bind_source_frozen(
            record.run_request_id,
            identity=identity,
            changed_at=self._now(),
        )
        self._receipt(
            record,
            DailyRunStatus.SOURCE_FROZEN,
            inputs=tuple(
                item.artifact_id for item in source_manifest.source_artifacts
            ),
            outputs=(
                ArtifactId(source_path.name),
                source_manifest.source_manifest_id,
            ),
        )
        self._after_stage(DailyRunStatus.SOURCE_FROZEN)
        return acquired, source_path, record

    def _acquire_live(
        self,
        request: PublicCompositeRequest,
        *,
        run_created_at: datetime,
    ) -> tuple[PublicCompositeProviderResult, SourceManifest]:
        if self._live_profile is None:
            result = self._live_failure_result(
                request,
                RuntimeError("LIVE_PROVIDER_NOT_CONFIGURED"),
            )
            return self._bind_live_control_evidence(
                result=result,
                request=request,
                run_created_at=run_created_at,
            )
        try:
            result = self._live_profile.acquire(request)
        except PublicCompositeAcquisitionError as exc:
            result = self._live_failure_result(
                request,
                exc,
                partial_batch=exc.partial_batch,
            )
        except AShareDataError as exc:
            result = self._live_failure_result(request, exc)
        return self._bind_live_control_evidence(
            result=result,
            request=request,
            run_created_at=run_created_at,
        )

    def _bind_live_control_evidence(
        self,
        *,
        result: PublicCompositeProviderResult,
        request: PublicCompositeRequest,
        run_created_at: datetime,
    ) -> tuple[PublicCompositeProviderResult, SourceManifest]:
        evidence = build_daily_control_source_evidence(
            request=request,
            retrieved_time=RetrievedAt(run_created_at),
            policy_id=self._policy.policy_id,
            policy_hash=self._policy.content_hash,
            policy_version=self._policy.policy_version,
            instrument_scope=self._policy.instrument_scope,
            symbols=self._policy.symbols,
        )
        bound = PublicCompositeProviderResult(
            profile_id=result.profile_id,
            decision_time=result.decision_time,
            raw_payloads=(*result.raw_payloads, *evidence.raw_payloads),
            bars=result.bars,
            quotes=result.quotes,
            source_conflicts=result.source_conflicts,
            limitations=tuple(
                dict.fromkeys(
                    (
                        *result.limitations,
                        "PROTOCOL_AND_POLICY_EVIDENCE_ARCHIVED",
                    )
                )
            ),
        )
        return bound, build_public_source_manifest(
            result=bound,
            request=request,
            declared_fields=evidence.fields,
        )

    def _live_failure_result(
        self,
        request: PublicCompositeRequest,
        error: Exception,
        *,
        partial_batch: PublicCompositeBatch | None = None,
    ) -> PublicCompositeProviderResult:
        retrieved_at = RetrievedAt(self._now())
        raw = json.dumps(
            {
                "error_type": type(error).__name__,
                "error": str(error),
                "decision_time": request.decision_time.isoformat(),
            },
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        payload = AcquiredSourcePayload(
            provider_id=ProviderId("provider-public-composite-live-runtime"),
            product="live-acquisition-failure",
            locator="runtime://public-composite-live-v1/acquisition-failure",
            raw_payload=raw,
            retrieved_time=retrieved_at,
            limitations=(
                "LIVE_ACQUISITION_FAILED",
                "NO_LOCAL_ARCHIVE_FALLBACK",
            ),
        )
        partial = partial_batch or PublicCompositeBatch(
            raw_payloads=(),
            bars=(),
            quotes=(),
            source_conflicts=(),
            limitations=(),
        )
        return PublicCompositeProviderResult(
            profile_id=PUBLIC_COMPOSITE_LIVE_PROFILE_ID,
            decision_time=request.decision_time,
            raw_payloads=(*partial.raw_payloads, payload),
            bars=partial.bars,
            quotes=partial.quotes,
            source_conflicts=partial.source_conflicts,
            limitations=tuple(
                dict.fromkeys(
                    (
                        *partial.limitations,
                        "LIVE_ACQUISITION_FAILED",
                        "PUBLIC_DATA_EXPLORATORY_ONLY",
                        "NO_LOCAL_ARCHIVE_FALLBACK",
                    )
                )
            ),
        )

    def _provider_request(
        self,
        command: DailyRunCommand,
    ) -> PublicCompositeRequest:
        return PublicCompositeRequest(
            symbols=self._policy.symbols,
            decision_time=command.decision_time,
            history_start=command.decision_date - timedelta(days=90),
            minimum_history_sessions=self._policy.minimum_history_sessions,
        )

    def _publish_blocked(
        self,
        *,
        record: DailyRunRecord,
        acquired: AcquiredReplaySource,
        source_archive_path: Path,
        quality_report: DataQualityReport,
        decision_snapshot: DecisionPriceSnapshot,
    ) -> DailyLoopRunResult:
        bundle = PhaseDDailyDecisionBundle(
            status=DailyDecisionArtifactStatus.DATA_BLOCKED,
            run_identity=_required_identity(record),
            source_archive_id=ArtifactId(source_archive_path.name),
            source_manifest=acquired.source_manifest,
            data_quality_report=quality_report,
            universe_snapshot=None,
            eligibility_snapshot=None,
            decision_price_snapshot=decision_snapshot,
            feature_definitions=(),
            feature_materializations=(),
            prediction_runs=(),
            recommendations=(),
            entry_assessments=(),
        )
        verified = _publish_or_verify_daily_decision(
            root=record.command.output_root / "daily_decisions",
            bundle=bundle,
        )
        record = self._advance(
            record,
            DailyRunStatus.DATA_BLOCKED,
            outputs=(bundle.artifact_id,),
        )
        return DailyLoopRunResult(
            record=record,
            source_archive_path=source_archive_path,
            decision_artifact=verified,
        )

    def _load_completed(self, record: DailyRunRecord) -> DailyLoopRunResult:
        receipt_stage = (
            DailyRunStatus.DATA_BLOCKED
            if record.status is DailyRunStatus.DATA_BLOCKED
            else DailyRunStatus.DECISION_PUBLISHED
        )
        receipt = self._repository.get_stage_receipt(
            record.run_request_id,
            receipt_stage,
        )
        if receipt is None:
            raise ValueError(f"{receipt_stage.value} stage receipt is missing")
        artifact_id = next(
            (
                item
                for item in receipt.output_artifact_ids
                if str(item).startswith("daily-decision-")
            ),
            None,
        )
        if artifact_id is None:
            raise ValueError("Daily Decision Artifact receipt is missing")
        source_path = self._source_archive_path(record)
        verified = load_verified_daily_decision_artifact(
            record.command.output_root / "daily_decisions" / str(artifact_id)
        )
        return DailyLoopRunResult(
            record=record,
            source_archive_path=source_path,
            decision_artifact=verified,
        )

    def _load_review(
        self,
        record: DailyRunRecord,
    ) -> VerifiedDailyReviewArtifact:
        receipt = self._repository.get_stage_receipt(
            record.run_request_id,
            DailyRunStatus.REVIEW_PUBLISHED,
        )
        if receipt is None:
            raise ValueError("REVIEW_PUBLISHED stage receipt is missing")
        artifact_id = next(
            (
                item
                for item in receipt.output_artifact_ids
                if str(item).startswith("daily-review-artifact-")
            ),
            None,
        )
        if artifact_id is None:
            raise ValueError("DailyReview Artifact receipt is missing")
        return load_verified_daily_review_artifact(
            record.command.output_root / "daily_reviews" / str(artifact_id)
        )

    def _source_archive_path(self, record: DailyRunRecord) -> Path:
        receipt = self._repository.get_stage_receipt(
            record.run_request_id,
            DailyRunStatus.SOURCE_FROZEN,
        )
        if receipt is None:
            return self._recover_source_archive_receipt(record)
        archive_id = next(
            (
                item
                for item in receipt.output_artifact_ids
                if str(item).startswith("source-replay-")
            ),
            None,
        )
        if archive_id is None:
            raise ValueError("Source Archive receipt is missing")
        return record.command.output_root / "source_archives" / str(archive_id)

    def _recover_source_archive_receipt(
        self,
        record: DailyRunRecord,
    ) -> Path:
        identity = _required_identity(record)
        root = record.command.output_root / "source_archives"
        matches: list[tuple[Path, AcquiredReplaySource]] = []
        if root.is_dir():
            for path in sorted(root.iterdir()):
                if not path.is_dir():
                    continue
                try:
                    acquired = SourceReplayArchiveReader().read(path)
                except ValueError:
                    continue
                manifest = acquired.source_manifest
                if (
                    manifest.source_manifest_id == identity.source_manifest_id
                    and manifest.content_hash
                    == identity.source_manifest_content_hash
                    and tuple(sorted(set(manifest.source_hashes)))
                    == identity.source_content_hashes
                ):
                    matches.append((path, acquired))
        if len(matches) != 1:
            raise ValueError(
                "SOURCE_FROZEN recovery requires exactly one matching Source Archive"
            )
        path, acquired = matches[0]
        self._receipt(
            record,
            DailyRunStatus.SOURCE_FROZEN,
            inputs=tuple(
                item.artifact_id
                for item in acquired.source_manifest.source_artifacts
            ),
            outputs=(
                ArtifactId(path.name),
                acquired.source_manifest.source_manifest_id,
            ),
        )
        return path

    def _advance(
        self,
        record: DailyRunRecord,
        target: DailyRunStatus,
        *,
        inputs: tuple[ArtifactId, ...] = (),
        outputs: tuple[ArtifactId, ...] = (),
    ) -> DailyRunRecord:
        if record.status is target:
            self._receipt(
                record,
                target,
                inputs=inputs,
                outputs=outputs,
            )
            return record
        record = self._repository.transition(
            record.run_request_id,
            expected_status=record.status,
            target_status=target,
            changed_at=self._now(),
        )
        self._receipt(record, target, inputs=inputs, outputs=outputs)
        self._after_stage(target)
        return record

    def _receipt(
        self,
        record: DailyRunRecord,
        stage: DailyRunStatus,
        *,
        inputs: tuple[ArtifactId, ...],
        outputs: tuple[ArtifactId, ...],
    ) -> StageReceipt:
        existing = self._repository.get_stage_receipt(
            record.run_request_id,
            stage,
        )
        if existing is not None:
            if (
                existing.input_artifact_ids
                != tuple(sorted(set(inputs), key=str))
                or existing.output_artifact_ids
                != tuple(sorted(set(outputs), key=str))
            ):
                raise ValueError(f"{stage.value} stage receipt semantic mismatch")
            return existing
        return self._repository.record_stage_receipt(
            StageReceipt(
                run_request_id=record.run_request_id,
                stage=stage,
                input_artifact_ids=tuple(sorted(set(inputs), key=str)),
                output_artifact_ids=tuple(sorted(set(outputs), key=str)),
                completed_at=self._now(),
            )
        )

    def _after_stage(self, status: DailyRunStatus) -> None:
        if self._after_stage_hook is not None:
            self._after_stage_hook(status)

    def _validate_command(self, command: DailyRunCommand) -> None:
        if command.universe_policy_id != str(self._policy.policy_id):
            raise ValueError("DailyRunCommand Universe Policy identity mismatch")
        if command.model_set_id != DAILY_B0_B1_MODEL_SET_ID:
            raise ValueError("DailyRunCommand requires the frozen B0/B1 model set")

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("daily loop clock must return an aware datetime")
        return value


def _required_identity(record: DailyRunRecord) -> DailyRunIdentity:
    if record.daily_run_identity is None:
        raise ValueError("DailyRunIdentity is required after Source Freeze")
    return record.daily_run_identity


def _configuration_hash(command: DailyRunCommand) -> str:
    canonical = json.dumps(
        {
            "schema_version": "daily-loop-configuration-binding-v1",
            "configuration_identity": str(command.configuration_identity),
            "provider_profile_id": command.provider_profile_id,
            "universe_policy_id": command.universe_policy_id,
            "model_set_id": command.model_set_id,
        },
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"sha256:{sha256(canonical.encode('utf-8')).hexdigest()}"


def _blocked_report(
    report: DataQualityReport,
    *,
    reason_code: str,
    additional_reason_codes: tuple[str, ...] = (),
) -> DataQualityReport:
    findings = (
        *report.findings,
        *(
            DataQualityFinding(
                symbol=None,
                field_id=None,
                critical_fact=None,
                reason_code=value,
                blocking=True,
            )
            for value in (reason_code, *additional_reason_codes)
        ),
    )
    return DataQualityReport(
        source_manifest_id=report.source_manifest_id,
        status=DailyDataQualityStatus.DATA_BLOCKED,
        required_symbols=report.required_symbols,
        findings=findings,
        data_eligibility=DataEligibility.EXPLORATORY,
    )


def _missing_feature_reasons(
    result: DailyFeaturePipelineResult,
) -> tuple[str, ...]:
    reasons: list[str] = []
    population = set(result.population.symbols)
    for materialization in result.materializations:
        by_symbol = {
            item.symbol: item for item in materialization.observations
        }
        for symbol in sorted(population):
            observation = by_symbol.get(symbol)
            if (
                observation is None
                or observation.status is not InputAvailabilityStatus.AVAILABLE
            ):
                reasons.append(
                    f"FEATURE_MISSING:{symbol}:{materialization.definition_id}"
                )
    return tuple(reasons)


def _publish_or_verify_source(
    *,
    root: Path,
    provider_result: PublicCompositeProviderResult,
    source_manifest: SourceManifest,
) -> Path:
    try:
        return publish_source_archive(
            root=root,
            provider_result=provider_result,
            source_manifest=source_manifest,
        )
    except FileExistsError:
        path = root / source_archive_id(
            provider_result=provider_result,
            source_manifest=source_manifest,
        )
        acquired = SourceReplayArchiveReader().read(path)
        if (
            acquired.provider_result != provider_result
            or acquired.source_manifest != source_manifest
        ):
            raise ValueError("existing Source Archive semantic mismatch")
        return path


def _publish_or_verify_prediction(
    *,
    root: Path,
    prediction_run: PredictionRun,
    model_definition: ModelDefinition,
) -> Path:
    try:
        return publish_prediction_run_artifact(
            root=root,
            prediction_run=prediction_run,
            model_definition=model_definition,
        )
    except FileExistsError:
        path = root / str(prediction_run.prediction_run_id)
        verified = load_verified_prediction_run_artifact(path)
        if verified.prediction_run != prediction_run:
            raise ValueError("existing PredictionRun Artifact semantic mismatch")
        return path


def _publish_or_verify_daily_decision(
    *,
    root: Path,
    bundle: PhaseDDailyDecisionBundle,
) -> VerifiedPhaseDDailyDecisionArtifact:
    try:
        path = publish_phase_d_daily_decision_artifact(
            root=root,
            bundle=bundle,
        )
    except FileExistsError:
        path = root / str(bundle.artifact_id)
    verified = load_verified_daily_decision_artifact(path)
    if verified.bundle != bundle:
        raise ValueError("existing Phase D Artifact semantic mismatch")
    return verified


def _next_session_date(
    *,
    decision_time: datetime,
    provider_result: PublicCompositeProviderResult,
) -> date:
    decision_date = decision_time.date()
    dates = sorted(
        {
            item.event_time.date()
            for item in provider_result.bars
            if item.event_time.date() > decision_date
            and item.event_time.time().replace(tzinfo=None) == time(10, 30)
        }
    )
    if not dates:
        raise OutcomeNotReadyError(
            "settlement archive has no exact next-session 10:30 evidence"
        )
    return dates[0]


def _publish_or_verify_daily_review(
    *,
    root: Path,
    settlement: OutcomeSettlement,
) -> VerifiedDailyReviewArtifact:
    try:
        path = publish_daily_review_artifact(
            root=root,
            settlement=settlement,
        )
    except FileExistsError:
        path = root / daily_review_artifact_id(settlement)
    verified = load_verified_daily_review_artifact(path)
    if verified.settlement != settlement:
        raise ValueError("existing DailyReview Artifact semantic mismatch")
    return verified
