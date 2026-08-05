"""PostgreSQL composition over source freeze and existing Controlled Runtime."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo

from market_regime_alpha.application.controlled_operation.evidence_package import (
    ControlledOperationalEvidencePackage,
    load_controlled_operation_package,
)
from market_regime_alpha.application.controlled_operation.input_artifacts import (
    load_controlled_runtime_configuration,
)
from market_regime_alpha.application.controlled_operation.journal import (
    ControlledOperationCommand,
    DecisionTimeOperationRunSnapshot,
)
from market_regime_alpha.application.controlled_operation.policy import (
    default_decision_time_operation_policy,
)
from market_regime_alpha.application.controlled_operation.runner import (
    ControlledDecisionTimeOperationRunner,
    ControlledOperationDataBlocked,
    ControlledOperationDecisionResult,
    ControlledOperationInputPaths,
    ControlledOperationPreparation,
)
from market_regime_alpha.application.daily_loop import (
    DailyLoopRunner,
    DailyLoopSourceFreezeResult,
    DailyRunCommand,
    RunMode,
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
)
from market_regime_alpha.data.providers.public_composite import (
    PublicCompositeLiveProfile,
    PublicSourceAcquisitionStage,
    TENCENT_FREE_OPERATIONAL_PROFILE_ID,
    load_verified_public_source_stage_artifact,
)
from market_regime_alpha.persistence.repository_factory import RepositoryFactory
from market_regime_alpha.persistence.settings import DatabaseBackend
from market_regime_alpha.universe.daily_exploratory import DailyUniversePolicy


Clock = Callable[[], datetime]
_SHANGHAI = ZoneInfo("Asia/Shanghai")


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
    ) -> None:
        if repositories.settings.backend is not DatabaseBackend.POSTGRES:
            raise ValueError("free-data Canonical Runtime requires PostgreSQL authority")
        if not code_revision or code_revision != code_revision.strip():
            raise ValueError("code_revision must be a non-empty trimmed value")
        self._repositories = repositories
        self._output_root = output_root.resolve()
        self._code_revision = code_revision
        self._clock = clock
        self._live_profile = live_profile

    def prepare(
        self,
        *,
        request: FreeDataPreparationRequest,
        runtime_configuration_path: Path,
        idempotency_key: str,
    ) -> FreeDataOperationPreparation:
        configuration_path = runtime_configuration_path.resolve()
        configuration = load_controlled_runtime_configuration(configuration_path)
        if configuration.configuration_hash != request.configuration_hash:
            raise ValueError("free-data request does not bind Runtime configuration")
        if request.provider_profile_id != TENCENT_FREE_OPERATIONAL_PROFILE_ID:
            raise ValueError("free-data service requires the Tencent operational profile")
        if any(item.asset_type.value != "A_SHARE" for item in request.instruments):
            raise ValueError("free-data V1 acquisition currently supports A-share stocks")
        if request.minimum_median_daily_amount <= 0:
            raise ValueError("Daily acquisition liquidity minimum must be positive")
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
        daily_command = DailyRunCommand(
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
        self._repositories.bind_runtime("DAILY_LOOP", str(daily_command.run_request_id))
        daily_repository = self._repositories.daily()
        source = DailyLoopRunner(
            repository=daily_repository,
            code_revision=self._code_revision,
            live_profile=self._live_profile,
            policy=policy,
            clock=self._clock,
        ).freeze_sources(daily_command)
        history_receipt = daily_repository.get_acquisition_receipt(
            daily_command.run_request_id,
            PublicSourceAcquisitionStage.HISTORY_SOURCE_FROZEN,
        )
        if history_receipt is None:
            raise ValueError("PostgreSQL DailyRun lacks frozen History receipt")
        materialization_request = replace(
            request,
            created_at=max(
                source.record.created_at,
                request.decision_time.value,
            ),
        )
        try:
            prepared = prepare_free_data_inputs(
                request=materialization_request,
                history_source=load_verified_public_source_stage_artifact(
                    Path(history_receipt.locator)
                ),
                provider_result=source.acquired.provider_result,
                full_source_manifest=source.acquired.source_manifest,
                output_root=operation_root,
                runtime_configuration_path=configuration_path,
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
                created_at=self._clock(),
                code_revision=self._code_revision,
            )
            blocked_path = publish_free_data_blocked(
                root=operation_root / "blocked_operations",
                artifact=blocked,
            )
            raise FreeDataOperationBlocked(blocked, blocked_path) from exc
        active_configuration_path = prepared.paths.runtime_configuration
        if active_configuration_path is None:
            raise ValueError("prepared inputs omit active Runtime configuration")
        active_configuration = load_controlled_runtime_configuration(
            active_configuration_path
        )
        controlled_policy = default_decision_time_operation_policy()
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
    ) -> FreeDataOperationExecution:
        preparation = self.prepare(
            request=request,
            runtime_configuration_path=runtime_configuration_path,
            idempotency_key=idempotency_key,
        )
        operation_root = self._operation_root(request)
        runner = self._controlled_runner(operation_root)
        try:
            decision = runner.run_decision_window(
                command=preparation.controlled_command,
                policy=default_decision_time_operation_policy(),
                inputs=preparation.controlled_preparation.input_paths,
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

    def _operation_root(self, request: FreeDataPreparationRequest) -> Path:
        return self._output_root / request.command_hash.split(":", 1)[1][:24]

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
]
