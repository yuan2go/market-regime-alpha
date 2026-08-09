"""PostgreSQL composition over source freeze and existing Controlled Runtime."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, time
from pathlib import Path
from time import sleep
from typing import Callable
from zoneinfo import ZoneInfo

from market_regime_alpha.application.controlled_operation.evidence_package import (
    ControlledOperationalEvidencePackage,
    load_controlled_operation_package,
)
from market_regime_alpha.application.controlled_operation.input_artifacts import (
    load_controlled_trading_calendar,
    load_controlled_runtime_configuration,
)
from market_regime_alpha.application.controlled_operation.journal import (
    ControlledOperationCommand,
    DecisionTimeOperationRunSnapshot,
)
from market_regime_alpha.application.controlled_operation.policy import (
    DecisionTimeOperationPolicy,
)
from market_regime_alpha.application.controlled_operation.runtime_configuration import (
    ControlledOperationRuntimeConfiguration,
)
from market_regime_alpha.application.controlled_operation.runner import (
    CandidateStateTransform,
    ControlledDecisionTimeOperationRunner,
    ControlledOperationDataBlocked,
    ControlledOperationDecisionResult,
    ControlledOperationInputPaths,
    ControlledOperationPreparation,
    Sleeper,
)
from market_regime_alpha.application.daily_loop import (
    DailyLoopRunner,
    DailyLoopSourceFreezeResult,
    DailyRunCommand,
    RunMode,
)
from market_regime_alpha.application.daily_loop.repositories import (
    AcquisitionStageReceipt,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.application.free_data_operation.builders import (
    prepare_free_data_inputs,
)
from market_regime_alpha.application.free_data_operation.blocked import (
    FreeDataBlockedArtifact,
    FreeDataOperationBlocked,
    publish_free_data_blocked,
)
from market_regime_alpha.application.free_data_operation.contracts import (
    FreeDataPreparationRequest,
    FreeDataPreparedInputs,
    FreeDataPreparedPaths,
    load_free_data_prepared_manifest,
)
from market_regime_alpha.data.providers.public_composite import (
    PublicCompositeLiveProfile,
    PublicSourceAcquisitionStage,
    TENCENT_FREE_OPERATIONAL_PROFILE_ID,
    load_verified_public_source_stage_artifact,
)
from market_regime_alpha.data.free_operational_policy import (
    FreeOperationalEvidencePolicy,
)
from market_regime_alpha.market_data.minute_batch import MinuteClientFactory
from market_regime_alpha.forecasting.sample_provider import PathForecastSampleProvider
from market_regime_alpha.persistence.repository_factory import RepositoryFactory
from market_regime_alpha.universe.daily_exploratory import DailyUniversePolicy


Clock = Callable[[], datetime]
_SHANGHAI = ZoneInfo("Asia/Shanghai")


def free_data_decision_time_operation_policy() -> DecisionTimeOperationPolicy:
    """Controlled policy for a 14:54 prepared, 14:55 FreeData decision."""

    return DecisionTimeOperationPolicy.create(
        policy_version="free-data-research-1455-v1",
        timezone_name="Asia/Shanghai",
        decision_time=time(14, 55),
        static_ready_deadline=time(14, 54, 59),
        minute_fetch_start=time(14, 54, 59),
        hard_cutoff=time(14, 56),
        limitations=(
            "FORMAL_OOS_ALPHA_NOT_ESTABLISHED",
            "FORMAL_PIT_NOT_ESTABLISHED",
            "NO_EARLY_CLOSE_INFERENCE",
            "TRADING_AUTHORITY_NOT_GRANTED",
        ),
    )


@dataclass(frozen=True, slots=True)
class FreeDataOperationPreparation:
    source: DailyLoopSourceFreezeResult
    prepared_inputs: FreeDataPreparedInputs
    controlled_command: ControlledOperationCommand
    controlled_preparation: ControlledOperationPreparation
    database_authority: str


@dataclass(frozen=True, slots=True)
class FreeDataOperationExecution:
    preparation: FreeDataOperationPreparation
    snapshot: DecisionTimeOperationRunSnapshot
    decision: ControlledOperationDecisionResult | None
    terminal_package: ControlledOperationalEvidencePackage | None
    blocked_reason: str | None

    @property
    def engineering_status(self) -> str:
        return (
            "ENGINEERING_RUN_COMPLETED"
            if self.decision is not None
            else "ENGINEERING_RUN_BLOCKED"
        )

    @property
    def entry_status(self) -> str:
        return (
            "BLOCKED_BY_MODEL_VALIDATION"
            if self.decision is not None
            else "NOT_REACHED"
        )


class FreeDataOperationService:
    """No journal of its own: compose Daily, Controlled, Feature, Canonical PG state."""

    def __init__(
        self,
        *,
        repositories: RepositoryFactory,
        output_root: Path,
        code_revision: str,
        clock: Clock,
        live_profile: PublicCompositeLiveProfile | None = None,
        minute_client_factory: MinuteClientFactory | None = None,
        sleeper: Sleeper = sleep,
        forecast_sample_provider: PathForecastSampleProvider | None = None,
        operational_supplemental_policy: FreeOperationalEvidencePolicy | None = None,
    ) -> None:
        if not code_revision or code_revision != code_revision.strip():
            raise ValueError("code_revision must be a non-empty trimmed value")
        self._repositories = repositories
        self._output_root = output_root.resolve()
        self._code_revision = code_revision
        self._clock = clock
        self._live_profile = live_profile
        self._minute_client_factory = minute_client_factory
        self._sleeper = sleeper
        self._forecast_sample_provider = forecast_sample_provider
        self._operational_supplemental_policy = operational_supplemental_policy

    def wait_until(self, instant: datetime) -> datetime:
        """Wait on the configured trusted/simulated clock without backfilling time."""

        observed = self._clock()
        remaining = (instant - observed).total_seconds()
        if remaining <= 0:
            return observed
        if remaining > 60:
            raise ValueError("DecisionTime is too far ahead for bounded Runtime wait")
        self._sleeper(remaining)
        observed = self._clock()
        if observed < instant:
            raise ValueError("Runtime clock did not reach DecisionTime")
        return observed

    def prepare_static_sources(
        self,
        *,
        request: FreeDataPreparationRequest,
        runtime_configuration_path: Path,
    ) -> tuple[AcquisitionStageReceipt, ...]:
        """Freeze BaoStock history/status before the Tencent quote window."""

        configuration = self._validate_request(
            request=request,
            runtime_configuration_path=runtime_configuration_path,
        )
        daily_command, runner = self._daily_source_runtime(
            request=request,
            configuration=configuration,
        )
        receipts = [
            runner.prepare_history(daily_command),
            runner.freeze_security_status(daily_command),
        ]
        if self._operational_supplemental_policy is not None:
            receipts.append(runner.freeze_supplemental(daily_command))
        return tuple(receipts)

    def prepare(
        self,
        *,
        request: FreeDataPreparationRequest,
        runtime_configuration_path: Path,
        idempotency_key: str,
        supplemental_evidence_path: Path | None = None,
    ) -> FreeDataOperationPreparation:
        configuration_path = runtime_configuration_path.resolve()
        configuration = self._validate_request(
            request=request,
            runtime_configuration_path=configuration_path,
        )
        operation_root = self._operation_root(request)
        operation_root.mkdir(parents=True, exist_ok=True)
        daily_command, daily_runner = self._daily_source_runtime(
            request=request,
            configuration=configuration,
        )
        decision_date = daily_command.decision_date
        daily_repository = self._repositories.daily()
        if (
            supplemental_evidence_path is None
            and self._operational_supplemental_policy is not None
        ):
            daily_runner.prepare_history(daily_command)
            daily_runner.freeze_supplemental(daily_command)
        source = daily_runner.freeze_sources(daily_command)
        history_receipt = daily_repository.get_acquisition_receipt(
            daily_command.run_request_id,
            PublicSourceAcquisitionStage.HISTORY_SOURCE_FROZEN,
        )
        if history_receipt is None:
            raise ValueError("PostgreSQL DailyRun lacks frozen History receipt")
        supplemental_source = None
        if (
            supplemental_evidence_path is None
            and self._operational_supplemental_policy is not None
        ):
            supplemental_receipt = daily_repository.get_acquisition_receipt(
                daily_command.run_request_id,
                PublicSourceAcquisitionStage.SUPPLEMENTAL_SOURCE_FROZEN,
            )
            if supplemental_receipt is None:
                raise ValueError(
                    "PostgreSQL DailyRun lacks frozen supplemental receipt"
                )
            supplemental_source = load_verified_public_source_stage_artifact(
                Path(supplemental_receipt.locator)
            )
        materialization_request = replace(
            request,
            # Preserve when this invocation actually materialized evidence.
            # A late caller must fail the DecisionTime checks; it may not
            # backfill CreatedAt to the semantic cutoff.
            created_at=self._clock(),
        )
        try:
            prepared = _load_existing_prepared_inputs(
                operation_root=operation_root,
                request=request,
                source=source,
            )
            if prepared is None:
                prepared = prepare_free_data_inputs(
                    request=materialization_request,
                    history_source=load_verified_public_source_stage_artifact(
                        Path(history_receipt.locator)
                    ),
                    provider_result=source.acquired.provider_result,
                    full_source_manifest=source.acquired.source_manifest,
                    output_root=operation_root,
                    runtime_configuration_path=configuration_path,
                    supplemental_evidence_path=supplemental_evidence_path,
                    operational_supplemental_source=supplemental_source,
                    operational_supplemental_policy=(
                        self._operational_supplemental_policy
                        if supplemental_source is not None
                        else None
                    ),
                )
        except Exception as exc:
            blocked = FreeDataBlockedArtifact.create(
                command_hash=materialization_request.command_hash,
                source_archive_id=ArtifactId(source.acquired.archive_id),
                source_manifest_id=(
                    source.acquired.source_manifest.source_manifest_id
                ),
                source_manifest_hash=source.acquired.source_manifest.content_hash,
                provider_result_hash=source.acquired.provider_result.content_hash,
                reason_code=_preparation_reason(exc),
                error_type=type(exc).__name__,
                created_at=materialization_request.created_at,
                code_revision=self._code_revision,
            )
            blocked_path = publish_free_data_blocked(
                root=operation_root / "blocked_operations",
                artifact=blocked,
            )
            self._repositories.free_data_blocked().record(
                artifact=blocked,
                locator=blocked_path,
            )
            raise FreeDataOperationBlocked(blocked, blocked_path) from exc
        active_configuration_path = prepared.paths.runtime_configuration
        if active_configuration_path is None:
            raise ValueError("prepared inputs omit active Runtime configuration")
        active_configuration = load_controlled_runtime_configuration(
            active_configuration_path
        )
        controlled_policy = free_data_decision_time_operation_policy()
        controlled_command = ControlledOperationCommand.create(
            idempotency_key=idempotency_key,
            decision_date=decision_date,
            decision_time=controlled_policy.decision_instant(decision_date),
            policy_id=controlled_policy.policy_id,
            policy_hash=controlled_policy.content_hash,
            trading_calendar_id=prepared.calendar.artifact_id,
            trading_calendar_hash=prepared.calendar.content_hash,
            configuration_manifest_id=active_configuration.configuration_id,
            configuration_manifest_hash=active_configuration.configuration_hash,
            model_manifest_id=active_configuration.model_manifest_id,
            model_manifest_hash=active_configuration.model_manifest_hash,
            code_revision=self._code_revision,
            limitations=(
                "ENTRY_BLOCKED",
                "FORMAL_OOS_ALPHA_NOT_ESTABLISHED",
                "FORMAL_PIT_NOT_ESTABLISHED",
                "NO_BROKER_AUTHORITY",
                "TRADING_AUTHORITY_NOT_GRANTED",
            ),
        )
        self._repositories.bind_runtime(
            "CONTROLLED_OPERATION",
            str(controlled_command.run_id),
        )
        controlled_preparation = self._controlled_runner(operation_root).prepare(
            command=controlled_command,
            policy=controlled_policy,
            inputs=_controlled_paths(prepared),
        )
        return FreeDataOperationPreparation(
            source=source,
            prepared_inputs=prepared,
            controlled_command=controlled_command,
            controlled_preparation=controlled_preparation,
            database_authority=self._repositories.binding.locator,
        )

    def run(
        self,
        *,
        request: FreeDataPreparationRequest,
        runtime_configuration_path: Path,
        idempotency_key: str,
        candidate_state_transform: CandidateStateTransform | None = None,
        supplemental_evidence_path: Path | None = None,
    ) -> FreeDataOperationExecution:
        preparation = self.prepare(
            request=request,
            runtime_configuration_path=runtime_configuration_path,
            idempotency_key=idempotency_key,
            supplemental_evidence_path=supplemental_evidence_path,
        )
        operation_root = self._operation_root(request)
        runner = self._controlled_runner(operation_root)
        try:
            decision = runner.run_decision_window(
                command=preparation.controlled_command,
                policy=free_data_decision_time_operation_policy(),
                inputs=preparation.controlled_preparation.input_paths,
                _resume_admitted_child=True,
                candidate_state_transform=candidate_state_transform,
            )
        except ControlledOperationDataBlocked as exc:
            snapshot = self._repositories.controlled_operation(
                clock=self._clock
            ).get(preparation.controlled_command.run_id)
            return FreeDataOperationExecution(
                preparation=preparation,
                snapshot=snapshot,
                decision=None,
                terminal_package=_terminal_package(
                    operation_root,
                    preparation.controlled_command,
                ),
                blocked_reason=str(exc),
            )
        return FreeDataOperationExecution(
            preparation=preparation,
            snapshot=decision.snapshot,
            decision=decision,
            terminal_package=decision.package,
            blocked_reason=None,
        )

    def record_model_not_qualified(
        self,
        *,
        preparation: FreeDataOperationPreparation,
        reason_codes: tuple[str, ...],
    ) -> FreeDataOperationExecution:
        """Persist a real Controlled blocked package without model execution."""

        snapshot, package = self._controlled_runner(
            self._operation_root_from_preparation(preparation)
        ).record_pre_research_blocked(
            preparation=preparation.controlled_preparation,
            policy=free_data_decision_time_operation_policy(),
            reason_codes=reason_codes,
        )
        return FreeDataOperationExecution(
            preparation=preparation,
            snapshot=snapshot,
            decision=None,
            terminal_package=package,
            blocked_reason="MODEL_NOT_QUALIFIED_FOR_MODE",
        )

    def _operation_root(self, request: FreeDataPreparationRequest) -> Path:
        return self._output_root / request.command_hash.split(":", 1)[1][:24]

    def _operation_root_from_preparation(
        self, preparation: FreeDataOperationPreparation
    ) -> Path:
        return self._output_root / preparation.prepared_inputs.manifest.command_hash.split(
            ":", 1
        )[1][:24]

    def _validate_request(
        self,
        *,
        request: FreeDataPreparationRequest,
        runtime_configuration_path: Path,
    ) -> ControlledOperationRuntimeConfiguration:
        configuration = load_controlled_runtime_configuration(
            runtime_configuration_path.resolve()
        )
        if configuration.configuration_hash != request.configuration_hash:
            raise ValueError("free-data request does not bind Runtime configuration")
        if request.provider_profile_id != TENCENT_FREE_OPERATIONAL_PROFILE_ID:
            raise ValueError("free-data service requires the Tencent operational profile")
        if request.code_revision != self._code_revision:
            raise ValueError("free-data request does not bind service code revision")
        if any(item.asset_type.value != "A_SHARE" for item in request.instruments):
            raise ValueError("free-data V1 acquisition currently supports A-share stocks")
        if request.minimum_median_daily_amount <= 0:
            raise ValueError("Daily acquisition liquidity minimum must be positive")
        return configuration

    def _daily_source_runtime(
        self,
        *,
        request: FreeDataPreparationRequest,
        configuration: ControlledOperationRuntimeConfiguration,
    ) -> tuple[DailyRunCommand, DailyLoopRunner]:
        operation_root = self._operation_root(request)
        operation_root.mkdir(parents=True, exist_ok=True)
        policy = DailyUniversePolicy(
            name=f"free-data-{request.scale.name.lower()}",
            version="v1",
            symbols=request.symbols,
            minimum_history_sessions=request.minimum_history_sessions,
            minimum_median_daily_amount=float(request.minimum_median_daily_amount),
        )
        decision_date = request.decision_time.value.astimezone(_SHANGHAI).date()
        command = DailyRunCommand(
            decision_date=decision_date,
            decision_time=request.decision_time,
            run_mode=RunMode.LIVE,
            provider_profile_id=request.provider_profile_id,
            universe_policy_id=str(policy.policy_id),
            model_set_id="free-data-canonical-inputs-v1",
            configuration_identity=configuration.configuration_id,
            output_root=operation_root / "source-runtime",
        )
        self._repositories.bind_runtime("FREE_DATA_OPERATION", request.command_hash)
        self._repositories.bind_runtime("DAILY_LOOP", str(command.run_request_id))
        return command, DailyLoopRunner(
            repository=self._repositories.daily(),
            code_revision=self._code_revision,
            live_profile=self._live_profile,
            policy=policy,
            clock=self._clock,
        )

    def _controlled_runner(
        self,
        operation_root: Path,
    ) -> ControlledDecisionTimeOperationRunner:
        return ControlledDecisionTimeOperationRunner(
            journal=self._repositories.controlled_operation(clock=self._clock),
            output_root=operation_root / "controlled-runtime",
            clock=self._clock,
            longitudinal_index=self._repositories.longitudinal(clock=self._clock),
            canonical_repository_factory=(
                self._repositories.controlled_canonical_repository
            ),
            feature_repository_factory=(
                self._repositories.feature_materialization_for_path
            ),
            minute_client_factory=self._minute_client_factory,
            sleeper=self._sleeper,
            forecast_sample_provider=self._forecast_sample_provider,
        )


def _load_existing_prepared_inputs(
    *,
    operation_root: Path,
    request: FreeDataPreparationRequest,
    source: DailyLoopSourceFreezeResult,
) -> FreeDataPreparedInputs | None:
    """Recover the first immutable materialization instead of changing its clock."""

    manifests_root = operation_root / "prepared_free_data_inputs"
    if not manifests_root.is_dir():
        return None
    matches = []
    for path in sorted(manifests_root.iterdir()):
        if not path.is_dir() or path.name.startswith("."):
            continue
        manifest = load_free_data_prepared_manifest(path)
        if (
            manifest.command_hash != request.command_hash
            or manifest.configuration_hash != request.configuration_hash
        ):
            continue
        references = {item.kind: item for item in manifest.artifacts}
        full = references.get("FULL_SOURCE_MANIFEST")
        if full is None or (
            full.artifact_id
            != source.acquired.source_manifest.source_manifest_id
            or full.content_hash != source.acquired.source_manifest.content_hash
        ):
            continue
        matches.append((path, manifest, references))
    if not matches:
        return None
    if len(matches) != 1:
        raise ValueError("multiple prepared input identities bind one source")
    manifest_path, manifest, references = matches[0]
    required = {
        "DAILY_SOURCE_STAGE",
        "DAILY_SOURCE_MANIFEST",
        "FULL_SOURCE_MANIFEST",
        "MARKET_DATA_DATASET",
        "OPERATIONAL_UNIVERSE",
        "SUPPLEMENTAL_RESEARCH_EVIDENCE",
        "TRADING_CALENDAR",
        "RUNTIME_CONFIGURATION",
    }
    if not required.issubset(references):
        raise ValueError("prepared input manifest omits required artifacts")

    def locate(kind: str) -> Path:
        value = (operation_root / references[kind].relative_locator).resolve()
        if not value.is_relative_to(operation_root) or not value.exists():
            raise ValueError("prepared input locator is invalid")
        return value

    paths = FreeDataPreparedPaths(
        history_source_stage=locate("DAILY_SOURCE_STAGE"),
        daily_source_manifest=locate("DAILY_SOURCE_MANIFEST"),
        full_source_manifest=locate("FULL_SOURCE_MANIFEST"),
        daily_market_data=locate("MARKET_DATA_DATASET"),
        trading_calendar=locate("TRADING_CALENDAR"),
        operational_universe=locate("OPERATIONAL_UNIVERSE"),
        supplemental_research_evidence=locate(
            "SUPPLEMENTAL_RESEARCH_EVIDENCE"
        ),
        runtime_configuration=locate("RUNTIME_CONFIGURATION"),
    )
    calendar = load_controlled_trading_calendar(paths.trading_calendar)
    return FreeDataPreparedInputs(
        manifest=manifest,
        manifest_path=manifest_path,
        paths=paths,
        calendar=calendar,
    )


def _controlled_paths(
    prepared: FreeDataPreparedInputs,
) -> ControlledOperationInputPaths:
    runtime_configuration = prepared.paths.runtime_configuration
    if runtime_configuration is None:
        raise ValueError("prepared inputs omit Runtime configuration")
    return ControlledOperationInputPaths(
        trading_calendar=prepared.paths.trading_calendar,
        operational_universe=prepared.paths.operational_universe,
        daily_source_stage=prepared.paths.history_source_stage,
        daily_source_manifest=prepared.paths.daily_source_manifest,
        supplemental_research_evidence=(
            prepared.paths.supplemental_research_evidence
        ),
        runtime_configuration=runtime_configuration,
    )


def _terminal_package(
    operation_root: Path,
    command: ControlledOperationCommand,
) -> ControlledOperationalEvidencePackage | None:
    root = (
        operation_root
        / "controlled-runtime"
        / str(command.run_id)
        / "operation-packages"
    )
    if not root.is_dir():
        return None
    packages = tuple(
        load_controlled_operation_package(path)
        for path in sorted(root.iterdir())
        if path.is_dir() and not path.name.startswith(".")
    )
    return packages[-1] if packages else None


def _preparation_reason(exc: Exception) -> str:
    message = str(exc)
    if "available after DecisionTime" in message:
        return "DATA_AVAILABLE_AFTER_DECISION_TIME"
    if "DECISION_DATE_NOT_IN_TRADING_CALENDAR" in message:
        return "DECISION_DATE_NOT_IN_EXPLICIT_TRADING_CALENDAR"
    return "FREE_DATA_PREPARATION_FAILED_CLOSED"


__all__ = [
    "FreeDataOperationExecution",
    "FreeDataOperationPreparation",
    "FreeDataOperationService",
    "free_data_decision_time_operation_policy",
]
