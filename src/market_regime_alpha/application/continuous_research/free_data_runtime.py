"""Executable BaoStock/Tencent composition for the sole Continuous Runtime."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Callable, Protocol

from market_regime_alpha.application.continuous_research.daily_alpha import (
    DailyAlphaConditionalForecastProjection,
    DailyAlphaEvidenceGate,
    DailyAlphaPathForecastProjection,
    DailyAlphaPredictionAuthority,
    DailyAlphaPredictionSnapshot,
    DailyAlphaSymbolProjection,
)

from market_regime_alpha.application.continuous_research.composition import (
    FreeDataPreparationInvocation,
    _with_upstream_result,
)
from market_regime_alpha.application.continuous_research.journal import (
    ContinuousChildKind,
    RuntimeArtifactReference,
)
from market_regime_alpha.application.continuous_research.ports import (
    ChildExecutionRequest,
    ChildExecutionResult,
    ProviderAcquisitionRequest,
    ProviderAcquisitionResult,
    ValidatedEvidencePayload,
)
from market_regime_alpha.application.continuous_research.multi_strategy import (
    MultiStrategyContinuousAdapter,
    ContinuousStrategyOpportunityResolver,
)
from market_regime_alpha.application.controlled_operation.input_artifacts import (
    load_controlled_runtime_configuration,
)
from market_regime_alpha.application.controlled_operation.journal import (
    DecisionTimeOperationReceipt,
    DecisionTimeOperationRunSnapshot,
    DecisionTimeOperationStageName,
)
from market_regime_alpha.application.controlled_operation.runtime_configuration import (
    ControlledOperationRuntimeConfiguration,
)
from market_regime_alpha.application.decision_system.postgres_repository import (
    PostgresDecisionSystemRepository,
)
from market_regime_alpha.application.decision_system.research_summary import (
    ProviderContractLineage,
    ResearchDailySummary,
    ResearchStageEvidence,
    ResearchStageResult,
    ResearchStageStatus,
)
from market_regime_alpha.application.decision_system.research_summary_runtime import (
    ResearchSummaryRuntimeService,
)
from market_regime_alpha.application.free_data_operation.service import (
    FreeDataOperationExecution,
    FreeDataOperationPreparation,
    FreeDataOperationService,
)
from market_regime_alpha.application.state_system.runtime import (
    STATE_RESEARCH_STAGE_ORDER,
    StateResearchStage,
)
from market_regime_alpha.application.state_system.free_data_composition import (
    CanonicalFreeDataStateCoordinator,
)
from market_regime_alpha.application.state_system.postgres_repository import (
    PostgresStateSystemRepository,
)
from market_regime_alpha.application.strategy_shadow.postgres_repository import (
    PostgresStrategyShadowRepository,
)
from market_regime_alpha.core.identity import (
    ArtifactId,
    FeatureDefinitionId,
    ModelId,
)
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.data.pit_contracts import PITSourceEvidenceLevel
from market_regime_alpha.data.free_operational_policy import (
    FREE_OPERATIONAL_POLICY_AUTHORITY_ID,
)
from market_regime_alpha.data.providers.public_composite import (
    BAOSTOCK_PUBLIC_PROVIDER_ID,
    TENCENT_FREE_OPERATIONAL_PROFILE_ID,
    TENCENT_PUBLIC_PROVIDER_ID,
)
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.forecasting.path import PathForecastArtifact
from market_regime_alpha.strategies.defaults import (
    canonical_exploratory_strategy_registry,
)
from market_regime_alpha.strategies.portfolio import CrossStrategyPortfolioPolicy
from market_regime_alpha.strategies.postgres_repository import (
    PostgresMultiStrategyRepository,
)
from market_regime_alpha.strategies.runtime import StrategyOpportunityAuthority
from decimal import Decimal
from market_regime_alpha.platform.postgres_runtime_governance import (
    ModelGovernanceIntegrityError,
)
from market_regime_alpha.platform.runtime_governance import (
    ArtifactLineageReference,
    ModelRuntimeAssignment,
    ModelSelectionReceipt,
    ModelSelectionRequest,
    ModelVersionLineage,
    RuntimeModelLineage,
    RuntimePurpose,
    SelectionStatus,
)


FREE_DATA_RUNTIME_SCOPE = "CONTROLLED_OPERATION"
FREE_DATA_MODEL_SLOTS = {
    StateResearchStage.MARKET_REGIME: "MARKET_REGIME",
    StateResearchStage.THEME_ROTATION: "THEME_ROTATION",
    StateResearchStage.CAPITAL_STATE: "CAPITAL_STATE",
    StateResearchStage.CANDIDATE: "CANDIDATE",
    StateResearchStage.SIGNAL: "STATE_SIGNAL",
    StateResearchStage.FORECAST: "STATE_FORECAST",
}
FREE_DATA_PROVIDER_CONTRACTS = (
    ProviderContractLineage(
        provider_id=str(BAOSTOCK_PUBLIC_PROVIDER_ID),
        product="query_history_k_data_plus:daily:adjustflag=3",
        contract_version="baostock-public-history-v1",
    ),
    ProviderContractLineage(
        provider_id=str(BAOSTOCK_PUBLIC_PROVIDER_ID),
        product="query_stock_basic+query_trade_dates",
        contract_version="baostock-public-status-v1",
    ),
    ProviderContractLineage(
        provider_id=str(TENCENT_PUBLIC_PROVIDER_ID),
        product="qt.gtimg.cn:current-quote",
        contract_version="tencent-public-current-v1",
    ),
    ProviderContractLineage(
        provider_id=str(TENCENT_PUBLIC_PROVIDER_ID),
        product="ifzq.gtimg.cn:minute",
        contract_version="tencent-public-minute-v1",
    ),
    ProviderContractLineage(
        provider_id=str(FREE_OPERATIONAL_POLICY_AUTHORITY_ID),
        product="free-operational-etf-theme-policy",
        contract_version="free-operational-evidence-policy-v1",
    ),
)


ChildInvocationBuilder = Callable[[ChildExecutionRequest], FreeDataPreparationInvocation]
Clock = Callable[[], datetime]


class DailyAlphaConditionalForecastResolver(Protocol):
    def resolve(
        self,
        *,
        path_forecast: PathForecastArtifact,
        decision_time: datetime,
    ) -> DailyAlphaConditionalForecastProjection: ...


class RuntimeModelGovernancePort(Protocol):
    def resolve_champion(
        self,
        *,
        runtime_scope: str,
        model_slot: str,
        purpose: RuntimePurpose,
        as_of: datetime,
    ) -> ModelRuntimeAssignment: ...

    def get_version_lineage_for_model(self, model_id: ModelId) -> ModelVersionLineage: ...

    def select(self, request: ModelSelectionRequest) -> ModelSelectionReceipt: ...


@dataclass(frozen=True, slots=True)
class GovernedControlledModels:
    receipts: tuple[tuple[StateResearchStage, ModelSelectionReceipt], ...]

    @property
    def all_selected(self) -> bool:
        return all(receipt.status is SelectionStatus.SELECTED for _, receipt in self.receipts)

    def for_stage(self, stage: StateResearchStage) -> ModelSelectionReceipt | None:
        return dict(self.receipts).get(stage)


class ControlledRuntimeModelSelector:
    """Admit the exact six executable Controlled model configurations."""

    def __init__(self, repository: RuntimeModelGovernancePort) -> None:
        self._repository = repository

    def select(
        self,
        *,
        request: ChildExecutionRequest,
        preparation: FreeDataOperationPreparation,
        runtime_configuration_path: Path,
    ) -> GovernedControlledModels:
        configuration = load_controlled_runtime_configuration(runtime_configuration_path.resolve())
        configured = _configured_models(configuration)
        receipts = []
        for stage in FREE_DATA_MODEL_SLOTS:
            slot = FREE_DATA_MODEL_SLOTS[stage]
            model_id, model_version, config_id, config_hash = configured[stage]
            rejections: set[str] = set()
            try:
                champion = self._repository.resolve_champion(
                    runtime_scope=FREE_DATA_RUNTIME_SCOPE,
                    model_slot=slot,
                    purpose=request.authority_mode.runtime_purpose,
                    as_of=request.as_of_time,
                )
                governed_model_id = champion.model_id
            except (KeyError, ValueError, ModelGovernanceIntegrityError):
                governed_model_id = model_id
                rejections.add("CHAMPION_AUTHORITY_UNAVAILABLE")
            try:
                lineage = self._repository.get_version_lineage_for_model(governed_model_id)
            except KeyError:
                lineage = None
                rejections.add("MODEL_VERSION_LINEAGE_MISSING")
            if governed_model_id != model_id:
                rejections.add("RUNTIME_CONFIGURATION_MODEL_MISMATCH")
            if lineage is not None:
                if lineage.model_version != model_version:
                    rejections.add("RUNTIME_CONFIGURATION_VERSION_MISMATCH")
                if lineage.configuration.artifact_id != config_id or lineage.configuration.content_hash != config_hash:
                    rejections.add("RUNTIME_CONFIGURATION_HASH_MISMATCH")
                if lineage.code_revision != preparation.controlled_command.code_revision:
                    rejections.add("RUNTIME_CODE_REVISION_MISMATCH")
            runtime_lineage = _runtime_lineage(
                preparation=preparation,
                model_id=governed_model_id,
                configuration_id=config_id,
                configuration_hash=config_hash,
                registered=lineage,
            )
            receipts.append(
                (
                    stage,
                    self._repository.select(
                        ModelSelectionRequest.create(
                            runtime_scope=FREE_DATA_RUNTIME_SCOPE,
                            model_slot=slot,
                            purpose=request.authority_mode.runtime_purpose,
                            runtime_lineage=runtime_lineage,
                            selected_at=request.as_of_time,
                            idempotency_key=(f"{request.run_id}:{request.tick_id}:{request.authority_mode.value}:{slot}"),
                            preselection_rejection_codes=tuple(sorted(rejections)),
                        )
                    ),
                )
            )
        return GovernedControlledModels(tuple(receipts))


class CanonicalFreeDataProvider:
    """Continuous Provider port over the one BaoStock/Tencent profile."""

    def __init__(
        self,
        *,
        service: FreeDataOperationService,
        invocation_builder: Callable[[ProviderAcquisitionRequest], FreeDataPreparationInvocation],
        clock: Clock,
    ) -> None:
        self._service = service
        self._invocation_builder = invocation_builder
        self._clock = clock

    def acquire(self, request: ProviderAcquisitionRequest) -> ProviderAcquisitionResult:
        invocation = self._invocation_builder(request)
        if invocation.request.command_hash != request.request_hash:
            raise ValueError("FreeData invocation does not bind Provider request")
        preparation = self._service.prepare(
            request=invocation.request,
            runtime_configuration_path=invocation.runtime_configuration_path,
            idempotency_key=invocation.idempotency_key,
            supplemental_evidence_path=invocation.supplemental_evidence_path,
        )
        return free_data_provider_result(
            preparation,
            completed_at=self._clock(),
        )


class CanonicalFreeDataResearchComposition:
    """One executable FreeData -> Controlled -> Summary child composition."""

    def __init__(
        self,
        *,
        service: FreeDataOperationService,
        invocation_builder: ChildInvocationBuilder,
        model_selector: ControlledRuntimeModelSelector,
        summary_repository: PostgresDecisionSystemRepository,
        state_repository: PostgresStateSystemRepository,
        strategy_repository: PostgresMultiStrategyRepository,
        strategy_shadow_repository: PostgresStrategyShadowRepository | None = None,
        strategy_account_id: str | None = None,
        daily_alpha_authority: DailyAlphaPredictionAuthority | None = None,
        daily_alpha_evidence_gate: Callable[[], DailyAlphaEvidenceGate] | None = None,
        daily_alpha_conditional_forecast_resolver: (
            DailyAlphaConditionalForecastResolver | None
        ) = None,
        target_session_date: date | None = None,
        target_calendar_reference: RuntimeArtifactReference | None = None,
        strategy_opportunity_resolver: ContinuousStrategyOpportunityResolver | None = None,
        strategy_opportunity_authority: StrategyOpportunityAuthority | None = None,
        clock: Clock,
    ) -> None:
        self._service = service
        self._invocation_builder = invocation_builder
        self._model_selector = model_selector
        self._summary_repository = summary_repository
        self._state_repository = state_repository
        self._strategy_repository = strategy_repository
        self._clock = clock
        self._daily_alpha_authority = daily_alpha_authority
        self._daily_alpha_evidence_gate = daily_alpha_evidence_gate
        self._daily_alpha_conditional_forecast_resolver = (
            daily_alpha_conditional_forecast_resolver
        )
        self._target_session_date = target_session_date
        self._target_calendar_reference = target_calendar_reference
        if (daily_alpha_authority is None) != (daily_alpha_evidence_gate is None):
            raise ValueError(
                "Daily Alpha projection requires both authority and Evidence gate"
            )
        if daily_alpha_authority is not None and (
            target_session_date is None or target_calendar_reference is None
        ):
            raise ValueError(
                "Daily Alpha projection requires one canonical target session"
            )
        if daily_alpha_authority is None and (
            target_session_date is not None or target_calendar_reference is not None
        ):
            raise ValueError("Daily Alpha target session requires its authority")
        self._summary_runtime = ResearchSummaryRuntimeService(summary_repository)
        self._strategy_runtime = MultiStrategyContinuousAdapter(
            repository=strategy_repository,
            portfolio_policy=CrossStrategyPortfolioPolicy(
                maximum_gross_weight=Decimal("0.50"),
                maximum_symbol_weight=Decimal("0.20"),
            ),
            strategy_shadow_repository=strategy_shadow_repository,
            account_id=strategy_account_id,
            opportunity_resolver=strategy_opportunity_resolver,
            opportunity_authority=strategy_opportunity_authority,
        )

    def lookup_children(self, request: ChildExecutionRequest) -> tuple[ChildExecutionResult, ...] | None:
        if request.authority_mode.requires_production_authorization:
            return None
        # A completed Continuous Tick is recovered by its own journal.  An
        # incomplete Tick re-enters the real bounded-context owners below;
        # their PostgreSQL receipts make that recovery idempotent.
        return None

    def execute_children(self, request: ChildExecutionRequest) -> tuple[ChildExecutionResult, ...]:
        invocation = self._invocation_builder(request)
        preparation = self._service.prepare(
            request=invocation.request,
            runtime_configuration_path=invocation.runtime_configuration_path,
            idempotency_key=invocation.idempotency_key,
            supplemental_evidence_path=invocation.supplemental_evidence_path,
        )
        if request.authority_mode.requires_production_authorization:
            # Free public evidence remains below the Production data ceiling even
            # if a governance operator accidentally assigns a Production model.
            raise PermissionError("FREE_DATA_PRODUCTION_AUTHORITY_DENIED")
        self._strategy_repository.register(
            canonical_exploratory_strategy_registry(),
            created_at=request.as_of_time,
        )
        governed = self._model_selector.select(
            request=request,
            preparation=preparation,
            runtime_configuration_path=preparation.controlled_preparation.input_paths.runtime_configuration,
        )
        dataset_result = _controlled_stage_child_result(
            kind=ContinuousChildKind.DAILY_DATASET,
            request=request,
            snapshot=preparation.controlled_preparation.snapshot,
            stage=DecisionTimeOperationStageName.DAILY_DATASET,
        )
        feature_request = _with_upstream_result(request, dataset_result)
        feature_result = _controlled_stage_child_result(
            kind=ContinuousChildKind.FEATURE_MATERIALIZATION,
            request=feature_request,
            snapshot=preparation.controlled_preparation.snapshot,
            stage=DecisionTimeOperationStageName.STATIC_FEATURES,
        )
        state_request = _with_upstream_result(feature_request, feature_result)
        state_coordinator = CanonicalFreeDataStateCoordinator(
            request=state_request,
            repository=self._state_repository,
            selection_receipts=governed.receipts,
            clock=self._clock,
        )
        execution = None
        if governed.all_selected:
            execution = self._service.run(
                request=invocation.request,
                runtime_configuration_path=invocation.runtime_configuration_path,
                idempotency_key=invocation.idempotency_key,
                supplemental_evidence_path=invocation.supplemental_evidence_path,
                candidate_state_transform=state_coordinator,
            )
        else:
            rejection_reasons = tuple(sorted({reason for _, receipt in governed.receipts for reason in receipt.reason_codes}))
            state_coordinator.record_model_blocked(reason_codes=rejection_reasons)
            execution = self._service.record_model_not_qualified(
                preparation=preparation,
                reason_codes=rejection_reasons,
            )
        summary_created_at = self._service.wait_until(request.as_of_time)
        summary = _build_summary(
            request=request,
            preparation=preparation,
            execution=execution,
            governed=governed,
            state_coordinator=state_coordinator,
            created_at=summary_created_at,
        )
        persisted = self._summary_runtime.execute(request=request, summary=summary)
        owner_results = _owner_child_results(
            request=request,
            dataset_result=dataset_result,
            feature_result=feature_result,
            state_result=state_coordinator.child_result,
            execution=execution,
            summary=persisted,
        )
        candidate_set = state_coordinator.final_candidates
        if candidate_set is None:
            raise ValueError("Strategy Runtime requires owner-resolved CandidateSet")
        decision = execution.decision
        strategy_request = replace(
            request,
            input_references=tuple(
                sorted(
                    {
                        *request.input_references,
                        RuntimeArtifactReference(
                            "TRADING_CALENDAR",
                            preparation.prepared_inputs.calendar.artifact_id,
                            preparation.prepared_inputs.calendar.content_hash,
                        ),
                    },
                    key=lambda item: (
                        item.reference_kind,
                        str(item.artifact_id),
                        item.content_hash,
                    ),
                )
            ),
        )
        strategy_result = self._strategy_runtime.execute(
            request=strategy_request,
            candidate_set=candidate_set,
            dataset_reference=persisted.dataset,
            upstream=owner_results[-1],
            decision_price_dataset=(
                None if decision is None else decision.minute_dataset.artifact
            ),
            path_forecasts=(
                ()
                if decision is None
                else tuple(item.artifact for item in decision.forecasts)
            ),
        )
        if self._daily_alpha_authority is None or self._daily_alpha_evidence_gate is None:
            return (*owner_results, strategy_result)
        daily_alpha = self._daily_alpha_authority.put(
            _build_daily_alpha_snapshot(
                request=request,
                preparation=preparation,
                execution=execution,
                state_coordinator=state_coordinator,
                summary=persisted,
                strategy_result=strategy_result,
                evidence_gate=self._daily_alpha_evidence_gate(),
                conditional_forecast_resolver=(
                    self._daily_alpha_conditional_forecast_resolver
                ),
                target_session_date=self._target_session_date,
                target_calendar_reference=self._target_calendar_reference,
                available_at=self._clock(),
            ),
            universe=preparation.controlled_preparation.universe,
        )
        daily_request = _with_upstream_result(strategy_request, strategy_result)
        daily_result = ChildExecutionResult(
            child_kind=ContinuousChildKind.DAILY_ALPHA_SNAPSHOT,
            child_run_id=request.run_id,
            child_receipt_id=daily_alpha.snapshot_id,
            child_receipt_hash=daily_alpha.snapshot_hash,
            child_artifact_id=daily_alpha.snapshot_id,
            child_artifact_hash=daily_alpha.snapshot_hash,
            input_references=daily_request.input_references,
            configuration_references=daily_request.configuration_references,
        )
        return (*owner_results, strategy_result, daily_result)


def _build_daily_alpha_snapshot(
    *,
    request: ChildExecutionRequest,
    preparation: FreeDataOperationPreparation,
    execution: FreeDataOperationExecution,
    state_coordinator: CanonicalFreeDataStateCoordinator,
    summary: ResearchDailySummary,
    strategy_result: ChildExecutionResult,
    evidence_gate: DailyAlphaEvidenceGate,
    conditional_forecast_resolver: DailyAlphaConditionalForecastResolver | None,
    target_session_date: date | None,
    target_calendar_reference: RuntimeArtifactReference | None,
    available_at: datetime,
) -> DailyAlphaPredictionSnapshot:
    if request.run_hash is None or request.tick_hash is None:
        raise ValueError("Daily Alpha snapshot requires Continuous Run/Tick hashes")
    candidate_set = state_coordinator.final_candidates
    if candidate_set is None:
        raise ValueError("Daily Alpha snapshot requires Candidate owner")
    if summary.candidate_set is None:
        raise ValueError("Daily Alpha snapshot requires Summary Candidate lineage")
    controlled = preparation.controlled_preparation
    feature_references = [
        RuntimeArtifactReference(
            "FEATURE_BUNDLE_V2",
            controlled.static_feature_bundle.artifact.bundle_id,
            controlled.static_feature_bundle.artifact.content_hash,
        )
    ]
    stage_outputs = {item.stage: item.output_reference for item in summary.stages}
    # The Summary freezes the aggregate Signal and Forecast owners consumed by
    # Shadow Decision.  Per-symbol snapshots below supplement these references;
    # they do not replace the aggregate lineage.
    signal_reference = stage_outputs[StateResearchStage.SIGNAL]
    forecast_stage_reference = stage_outputs[StateResearchStage.FORECAST]
    signals: dict[str, Any] = {}
    forecasts: dict[str, Any] = {}
    raw_forecast_references: list[RuntimeArtifactReference] = []
    if execution.decision is not None:
        feature_references.append(
            RuntimeArtifactReference(
                "INTRADAY_FEATURE_BUNDLE_V2",
                execution.decision.intraday_feature_bundle.artifact.bundle_id,
                execution.decision.intraday_feature_bundle.artifact.content_hash,
            )
        )
        signals = {
            item.symbol: item for item in execution.decision.signal.artifact.snapshots
        }
        forecasts = {
            item.artifact.forecast.symbol: item.artifact
            for item in execution.decision.forecasts
        }
        raw_forecast_references = [
            RuntimeArtifactReference(
                "PATH_FORECAST",
                item.artifact.artifact_id,
                item.artifact.forecast.envelope.content_hash,
            )
            for item in execution.decision.forecasts
        ]
    context_references = [
        RuntimeArtifactReference(
            "RESEARCH_DAILY_SUMMARY", summary.summary_id, summary.content_hash
        )
    ]
    for stage in (
        StateResearchStage.MARKET_REGIME,
        StateResearchStage.THEME_ROTATION,
        StateResearchStage.CAPITAL_STATE,
    ):
        reference = _state_stage_reference(state_coordinator, stage)
        if reference is not None:
            context_references.append(reference)
    symbol_rows = []
    selected_statuses = {"SELECTED", "WATCHLIST"}
    for candidate in candidate_set.records:
        if candidate.selection_status.value not in selected_statuses:
            continue
        feature_values = _daily_feature_values(
            symbol=candidate.symbol,
            static_bundle=controlled.static_feature_bundle,
            intraday_bundle=(
                None
                if execution.decision is None
                else execution.decision.intraday_feature_bundle
            ),
        )
        signal = signals.get(candidate.symbol)
        forecast_artifact = forecasts.get(candidate.symbol)
        forecast = (
            None if forecast_artifact is None else forecast_artifact.forecast
        )
        conditional_projection = (
            DailyAlphaConditionalForecastProjection.not_available()
            if forecast_artifact is None
            or conditional_forecast_resolver is None
            else conditional_forecast_resolver.resolve(
                path_forecast=forecast_artifact,
                decision_time=request.as_of_time,
            )
        )
        if conditional_projection.reference is not None:
            raw_forecast_references.append(conditional_projection.reference)
        symbol_reasons = {
            *candidate.reason_codes,
            *(() if signal is None else signal.reason_codes),
            *(() if forecast is None else forecast.reason_codes),
            *conditional_projection.reason_codes,
            "VALIDATED_ALPHA_CONTRIBUTION_OWNER_NOT_AVAILABLE",
        }
        if forecast is None:
            symbol_reasons.add("PATH_FORECAST_OWNER_NOT_AVAILABLE")
        incumbent_diagnostics = tuple(
            sorted(
                (
                    (
                        "candidate_discovery_score",
                        _value_text(candidate.candidate_discovery_score),
                    ),
                    (
                        "capital_evolution_score",
                        _value_text(candidate.capital_evolution_score),
                    ),
                    (
                        "market_regime_score",
                        _value_text(candidate.market_regime_score),
                    ),
                    ("theme_score", _value_text(candidate.theme_score)),
                    *((f"feature:{key}", value) for key, value in feature_values),
                )
            )
        )
        path_projection = (
            None
            if forecast is None
            else DailyAlphaPathForecastProjection(
                reference=RuntimeArtifactReference(
                    "PATH_FORECAST",
                    forecast.envelope.artifact_id,
                    forecast.envelope.content_hash,
                ),
                forecast_status=forecast.forecast_status.value,
                expected_mfe=_value_text(forecast.expected_mfe),
                expected_mae=_value_text(forecast.expected_mae),
                return_quantiles=tuple(
                    (
                        str(item.probability),
                        _value_text(item.return_value),
                    )
                    for item in forecast.return_quantiles
                ),
                usable_sample_count=forecast.usable_sample_count,
                excluded_sample_count=forecast.excluded_sample_count,
                calibration_status=forecast.calibration_status.value,
                reason_codes=tuple(
                    sorted(forecast.reason_codes or ("NO_PATH_FORECAST_REASON",))
                ),
            )
        )
        symbol_rows.append(
            DailyAlphaSymbolProjection(
                symbol=candidate.symbol,
                selection_status=candidate.selection_status.value,
                candidate_rank=candidate.rank,
                incumbent_diagnostics=incumbent_diagnostics,
                # No per-symbol Alpha contribution owner exists yet.  The
                # admission gate cannot turn Context diagnostics into one.
                validated_alpha_contributions=(),
                conditional_context=tuple(
                    sorted(
                        (
                            ("capital", candidate.capital_evolution_state.value),
                            ("market_regime", candidate.market_regime_status.value),
                            ("theme", candidate.theme_rotation_state.value),
                        )
                    )
                ),
                signal_reference=(
                    None
                    if signal is None
                    else RuntimeArtifactReference(
                        "SIGNAL_SNAPSHOT",
                        signal.artifact_id,
                        signal.envelope.content_hash,
                    )
                ),
                signal_state=None if signal is None else signal.signal_state.value,
                signal_score=None if signal is None else _value_text(signal.signal_score),
                path_forecast=path_projection,
                conditional_forecast=conditional_projection,
                strategy_diagnostic_reference=RuntimeArtifactReference(
                    "MULTI_STRATEGY_CYCLE",
                    strategy_result.child_receipt_id,
                    strategy_result.child_receipt_hash,
                ),
                reason_codes=tuple(sorted(symbol_reasons or {"NO_SYMBOL_REASON"})),
            )
        )
    return DailyAlphaPredictionSnapshot.create(
        run_reference=RuntimeArtifactReference(
            "CONTINUOUS_RESEARCH_RUN", request.run_id, request.run_hash
        ),
        tick_reference=RuntimeArtifactReference(
            "CONTINUOUS_RUNTIME_TICK", request.tick_id, request.tick_hash
        ),
        code_reference=RuntimeArtifactReference(
            "CONTINUOUS_RUN_CODE_IDENTITY", request.run_id, request.run_hash
        ),
        configuration_references=request.configuration_references,
        provider_evidence_reference=RuntimeArtifactReference(
            "EVIDENCE_COMMIT",
            request.evidence_commit_id,
            request.evidence_commit_hash,
        ),
        dataset_reference=summary.dataset,
        universe_reference=RuntimeArtifactReference(
            "OPERATIONAL_UNIVERSE",
            ArtifactId(str(controlled.universe.universe_id)),
            controlled.universe.content_hash,
        ),
        feature_references=tuple(feature_references),
        context_references=tuple(context_references),
        candidate_reference=summary.candidate_set,
        signal_reference=signal_reference,
        forecast_references=tuple(
            item
            for item in (forecast_stage_reference, *raw_forecast_references)
            if item is not None
        ),
        strategy_diagnostic_reference=RuntimeArtifactReference(
            "MULTI_STRATEGY_CYCLE",
            strategy_result.child_receipt_id,
            strategy_result.child_receipt_hash,
        ),
        evidence_gate=evidence_gate,
        trading_date=request.trading_date,
        target_session_date=target_session_date,
        target_calendar_reference=target_calendar_reference,
        decision_time=request.as_of_time,
        available_at=available_at,
        symbols=tuple(symbol_rows),
        reason_codes=("DAILY_PREDICTION_FROZEN_BEFORE_OUTCOME",),
    )


def _state_stage_reference(
    coordinator: CanonicalFreeDataStateCoordinator,
    stage: StateResearchStage,
) -> RuntimeArtifactReference | None:
    artifact = coordinator.stage_artifacts.get(stage)
    if artifact is None:
        return None
    reference = artifact.to_reference()
    return RuntimeArtifactReference(
        f"STATE_STAGE_{stage.value}", reference.artifact_id, reference.content_hash
    )


def _daily_feature_values(
    *,
    symbol: str,
    static_bundle: Any,
    intraday_bundle: Any | None,
) -> tuple[tuple[str, str | None], ...]:
    values: dict[str, str | None] = {}
    for bundle in (static_bundle, intraday_bundle):
        if bundle is None:
            continue
        for verified in bundle.artifacts:
            artifact = verified.artifact
            if artifact.symbol != symbol:
                continue
            for value in artifact.values:
                key = f"{artifact.feature_id}:{value.output_id}"
                projected = None if value.value is None else _value_text(value.value)
                existing = values.get(key)
                if key in values and existing != projected:
                    key = f"{artifact.timeframe.value}:{key}"
                values[key] = projected
    return tuple(sorted(values.items()))


def _value_text(value: Any) -> str | None:
    return None if value is None else str(value)


def free_data_provider_result(
    preparation: FreeDataOperationPreparation,
    *,
    completed_at: datetime,
) -> ProviderAcquisitionResult:
    source = preparation.source.acquired
    manifest = source.source_manifest
    retrieved_at = max(item.retrieved_at.value for item in manifest.source_artifacts).astimezone(UTC)
    decision_time = manifest.decision_time.value.astimezone(UTC)
    return ProviderAcquisitionResult.succeeded(
        completed_at=completed_at.astimezone(UTC),
        raw_response_hash=source.provider_result.content_hash,
        source_manifest_id=manifest.source_manifest_id,
        source_manifest_hash=manifest.content_hash,
        reason_codes=(
            "BAOSTOCK_TENCENT_PROFILE_EXPLICIT",
            "FREE_DATA_EXPLORATORY",
            "NO_PROVIDER_FALLBACK",
        ),
        evidence=ValidatedEvidencePayload(
            evidence_scope="CANONICAL_FREE_DATA_INPUTS",
            raw_artifact_id=ArtifactId(source.archive_id),
            raw_artifact_hash=source.provider_result.content_hash,
            evidence_artifact_id=preparation.prepared_inputs.manifest.manifest_id,
            evidence_artifact_hash=preparation.prepared_inputs.manifest.content_hash,
            material_identity_hash=preparation.prepared_inputs.manifest.content_hash,
            # The composite is effective when its last immutable source became
            # available. SourceManifest DecisionTime remains the later ceiling.
            effective_at=retrieved_at,
            retrieved_at=retrieved_at,
            available_at=retrieved_at,
            as_of_time=decision_time,
            evidence_qualification="FREE_DATA_EXPLORATORY",
            limitations=(
                "FORMAL_PIT_NOT_ESTABLISHED",
                "NO_PROVIDER_FALLBACK",
                "NO_TRADING_AUTHORITY",
                "PIT_INCOMPLETE",
            ),
            downstream_contract_satisfied=True,
        ),
    )


def _build_summary(
    *,
    request: ChildExecutionRequest,
    preparation: FreeDataOperationPreparation,
    execution: FreeDataOperationExecution | None,
    governed: GovernedControlledModels,
    state_coordinator: CanonicalFreeDataStateCoordinator,
    created_at: datetime,
) -> ResearchDailySummary:
    controlled = preparation.controlled_preparation
    dataset = RuntimeArtifactReference(
        "MARKET_DATA_DATASET",
        ArtifactId(str(controlled.daily_dataset.artifact.dataset_id)),
        controlled.daily_dataset.artifact.content_hash,
    )
    feature = RuntimeArtifactReference(
        "FEATURE_BUNDLE_V2",
        controlled.static_feature_bundle.artifact.bundle_id,
        controlled.static_feature_bundle.artifact.content_hash,
    )
    stages = tuple(
        _stage_evidence(
            stage=stage,
            request=request,
            preparation=preparation,
            execution=execution,
            governed=governed,
            state_coordinator=state_coordinator,
        )
        for stage in STATE_RESEARCH_STAGE_ORDER
    )
    receipts = tuple(_selection_reference(receipt) for _, receipt in governed.receipts)
    active_configuration = load_controlled_runtime_configuration(controlled.input_paths.runtime_configuration)
    governed_configurations = tuple(
        RuntimeArtifactReference(
            "MODEL_CONFIGURATION",
            configuration_id,
            configuration_hash,
        )
        for _, _, configuration_id, configuration_hash in _configured_models(active_configuration).values()
    )
    state_result = state_coordinator.child_result
    if state_result is None:
        raise ValueError("State System owner receipt is unavailable")
    candidate_set = state_coordinator.final_candidates
    return ResearchDailySummary.create(
        runtime_mode=request.authority_mode,
        run_id=request.run_id,
        tick_id=request.tick_id,
        trading_date=request.trading_date,
        decision_time=request.as_of_time,
        provider_profile_id=TENCENT_FREE_OPERATIONAL_PROFILE_ID,
        provider_contracts=_consumed_provider_contracts(preparation, execution),
        provider_source_references=_consumed_provider_sources(preparation, execution),
        source_manifest=RuntimeArtifactReference(
            "SOURCE_MANIFEST",
            request.source_manifest_id,
            request.source_manifest_hash,
        ),
        dataset=dataset,
        feature_bundle=feature,
        state_system_receipt=RuntimeArtifactReference(
            "STATE_SYSTEM_RECEIPT",
            state_result.child_receipt_id,
            state_result.child_receipt_hash,
        ),
        candidate_set=(
            None
            if candidate_set is None
            else RuntimeArtifactReference(
                "STATE_CONSTRAINED_CANDIDATE_SET",
                candidate_set.envelope.artifact_id,
                candidate_set.envelope.content_hash,
            )
        ),
        stages=stages,
        model_selection_receipts=tuple(sorted(receipts, key=_reference_key)),
        configuration_references=tuple(
            sorted(
                {
                    *request.configuration_references,
                    RuntimeArtifactReference(
                        "CONTROLLED_RUNTIME_CONFIGURATION",
                        active_configuration.configuration_id,
                        active_configuration.configuration_hash,
                    ),
                    *governed_configurations,
                },
                key=_reference_key,
            )
        ),
        data_eligibility=DataEligibility.EXPLORATORY,
        evidence_ceiling=PITSourceEvidenceLevel.FREE_DATA_EXPLORATORY,
        revision=1,
        previous_summary_id=None,
        correction_of_summary_id=None,
        idempotency_key=f"{request.idempotency_key}:research-summary",
        created_at=created_at,
    )


def _stage_evidence(
    *,
    stage: StateResearchStage,
    request: ChildExecutionRequest,
    preparation: FreeDataOperationPreparation,
    execution: FreeDataOperationExecution | None,
    governed: GovernedControlledModels,
    state_coordinator: CanonicalFreeDataStateCoordinator,
) -> ResearchStageEvidence:
    receipt = governed.for_stage(stage)
    selection = None if receipt is None else _selection_reference(receipt)
    state_artifact = state_coordinator.stage_artifacts.get(stage)
    output = state_artifact.to_reference() if state_artifact is not None else _execution_stage_output(stage, preparation, execution)
    if receipt is not None and receipt.status is SelectionStatus.REJECTED:
        status = ResearchStageStatus.MODEL_NOT_QUALIFIED_FOR_MODE
        missing: tuple[str, ...] = ()
        reasons = tuple(
            sorted(
                {
                    "MODEL_NOT_QUALIFIED_FOR_MODE",
                    *receipt.reason_codes,
                }
            )
        )
    elif state_artifact is not None:
        status = ResearchStageStatus.COMPLETED if state_artifact.status.value == "COMPLETED" else ResearchStageStatus.DATA_INSUFFICIENT
        missing = () if status is ResearchStageStatus.COMPLETED else _missing_evidence(stage, execution)
        reasons = state_artifact.reason_codes
    elif (
        stage in {StateResearchStage.SIGNAL, StateResearchStage.FORECAST}
        and state_coordinator.final_candidates is not None
        and not state_coordinator.final_candidates.selected
        and output is not None
    ):
        status = ResearchStageStatus.COMPLETED
        missing = ()
        reasons = (f"{stage.value}_NOT_REQUIRED_WITHOUT_CANDIDATE",)
    elif (
        output is not None
        and (stage is StateResearchStage.OBSERVATION or (execution is not None and execution.decision is not None))
        and stage
        not in {
            StateResearchStage.ETF_ROTATION,
            StateResearchStage.DYNAMIC_POOL,
        }
    ):
        status = ResearchStageStatus.COMPLETED
        missing = ()
        reasons = (_completed_reason(stage, execution),)
    else:
        status = ResearchStageStatus.DATA_INSUFFICIENT
        missing = _missing_evidence(stage, execution)
        reasons_set = {f"{stage.value}_DATA_INSUFFICIENT"}
        if stage in {
            StateResearchStage.DYNAMIC_POOL,
            StateResearchStage.CANDIDATE,
            StateResearchStage.SIGNAL,
            StateResearchStage.FORECAST,
        }:
            reasons_set.add("UPSTREAM_STAGE_DATA_INSUFFICIENT")
        reasons = tuple(sorted(reasons_set))
    return ResearchStageEvidence.create(
        stage=stage,
        status=status,
        output_reference=output,
        selection_receipt=selection,
        evidence_available_at=(
            state_artifact.available_at if state_artifact is not None else _canonical_stage_times(stage, request, execution)[0]
        ),
        stage_completed_at=state_coordinator.stage_completed_at.get(stage, _canonical_stage_times(stage, request, execution)[1]),
        result=_stage_result(
            stage,
            status,
            execution,
            state_coordinator.final_candidates,
        ),
        data_eligibility=DataEligibility.EXPLORATORY,
        evidence_ceiling=PITSourceEvidenceLevel.FREE_DATA_EXPLORATORY,
        missing_evidence=missing,
        reason_codes=reasons,
    )


def _canonical_stage_times(
    stage: StateResearchStage,
    request: ChildExecutionRequest,
    execution: FreeDataOperationExecution | None,
) -> tuple[datetime, datetime]:
    if execution is None or execution.decision is None:
        package = None if execution is None else execution.terminal_package
        completed = request.as_of_time if package is None else max(request.as_of_time, package.created_at)
        return request.as_of_time, completed
    decision = execution.decision
    if stage is StateResearchStage.SIGNAL:
        completed = decision.signal.artifact.envelope.created_at
        return decision.minute_coverage.request_completed_at, completed
    if stage is StateResearchStage.FORECAST:
        signal_completed = decision.signal.artifact.envelope.created_at
        completed = max(
            (item.artifact.forecast.envelope.created_at for item in decision.forecasts),
            default=signal_completed,
        )
        return signal_completed, completed
    return request.as_of_time, request.as_of_time


def _stage_result(
    stage: StateResearchStage,
    status: ResearchStageStatus,
    execution: FreeDataOperationExecution | None,
    state_candidates: Any | None = None,
) -> ResearchStageResult:
    if status is not ResearchStageStatus.COMPLETED:
        return ResearchStageResult.UNAVAILABLE
    if stage is StateResearchStage.CANDIDATE:
        if state_candidates is None:
            return ResearchStageResult.EMPTY
        return ResearchStageResult.RESEARCH_QUALIFIED if state_candidates.selected else ResearchStageResult.EMPTY
    if stage is StateResearchStage.SIGNAL:
        if execution is None or execution.decision is None:
            return ResearchStageResult.EMPTY
        states = {item.signal_state.value for item in execution.decision.signal.artifact.snapshots}
        if "CONFIRMED_FOR_RESEARCH" in states:
            return ResearchStageResult.RESEARCH_QUALIFIED
        if "WATCH" in states:
            return ResearchStageResult.WATCH
        return ResearchStageResult.EMPTY
    if stage is StateResearchStage.FORECAST:
        if execution is None or execution.decision is None:
            return ResearchStageResult.EMPTY
        return (
            ResearchStageResult.RESEARCH_QUALIFIED
            if any(item.artifact.forecast.forecast_status.value == "AVAILABLE_FOR_RESEARCH" for item in execution.decision.forecasts)
            else ResearchStageResult.EMPTY
        )
    return ResearchStageResult.AVAILABLE


def _execution_stage_output(
    stage: StateResearchStage,
    preparation: FreeDataOperationPreparation,
    execution: FreeDataOperationExecution | None,
) -> RuntimeArtifactReference | None:
    if stage is StateResearchStage.OBSERVATION:
        manifest = preparation.prepared_inputs.manifest
        return RuntimeArtifactReference("FREE_DATA_PREPARED_INPUTS", manifest.manifest_id, manifest.content_hash)
    if execution is not None and execution.decision is None:
        package = execution.terminal_package
        if package is not None:
            reference_type = {
                StateResearchStage.MARKET_REGIME: "CONTROLLED_RESEARCH",
                StateResearchStage.THEME_ROTATION: "CONTROLLED_RESEARCH",
                StateResearchStage.CAPITAL_STATE: "CONTROLLED_RESEARCH",
                StateResearchStage.CANDIDATE: "CANDIDATE_SET",
                StateResearchStage.SIGNAL: "OPERATION_PACKAGE",
                StateResearchStage.FORECAST: "OPERATION_PACKAGE",
            }.get(stage)
            if reference_type == "OPERATION_PACKAGE":
                return RuntimeArtifactReference(
                    f"NO_{stage.value}_REQUIRED_RECEIPT",
                    package.package_id,
                    package.content_hash,
                )
            matches = tuple(item for item in package.evidence_references if item.reference_type == reference_type)
            if len(matches) == 1:
                terminal_reference = matches[0]
                return RuntimeArtifactReference(
                    reference_type or stage.value,
                    terminal_reference.object_id,
                    terminal_reference.content_hash,
                )
        return None
    if execution is None or execution.decision is None:
        return None
    decision = execution.decision
    research = decision.research.artifact
    if stage is StateResearchStage.MARKET_REGIME:
        item = research.market_regime.envelope
        return RuntimeArtifactReference("MARKET_REGIME", item.artifact_id, item.content_hash)
    if stage is StateResearchStage.THEME_ROTATION:
        item = research.theme_rotation.envelope
        return RuntimeArtifactReference("THEME_ROTATION", item.artifact_id, item.content_hash)
    if stage is StateResearchStage.CAPITAL_STATE:
        item = research.capital_evolution.envelope
        return RuntimeArtifactReference("CAPITAL_STATE", item.artifact_id, item.content_hash)
    if stage is StateResearchStage.CANDIDATE:
        item = decision.candidate_set.envelope
        return RuntimeArtifactReference("CANDIDATE", item.artifact_id, item.content_hash)
    if stage is StateResearchStage.SIGNAL:
        signal = decision.signal.artifact
        return RuntimeArtifactReference("SIGNAL", signal.artifact_id, signal.envelope.content_hash)
    if stage is StateResearchStage.FORECAST:
        digest = canonical_hash(
            {
                "forecasts": [
                    {
                        "artifact_id": str(item.artifact.artifact_id),
                        "content_hash": item.artifact.forecast.envelope.content_hash,
                    }
                    for item in decision.forecasts
                ]
            }
        )
        return RuntimeArtifactReference(
            "FORECAST_SET",
            ArtifactId(f"forecast-set:{digest[7:]}"),
            digest,
        )
    return None


def _missing_evidence(
    stage: StateResearchStage,
    execution: FreeDataOperationExecution | None,
) -> tuple[str, ...]:
    explicit = {
        StateResearchStage.ETF_ROTATION: ("ETF_OBSERVATION",),
        StateResearchStage.THEME_ROTATION: ("THEME_MEMBERSHIP", "THEME_OBSERVATION"),
        StateResearchStage.CAPITAL_STATE: ("CAPITAL_OBSERVATION",),
        StateResearchStage.DYNAMIC_POOL: ("ETF_ROTATION", "THEME_ROTATION", "CAPITAL_STATE"),
        StateResearchStage.CANDIDATE: ("DYNAMIC_POOL",),
        StateResearchStage.SIGNAL: ("CANDIDATE", "INTRADAY_EVIDENCE"),
        StateResearchStage.FORECAST: ("FORECAST_SAMPLE", "SIGNAL"),
    }
    values = set(explicit.get(stage, (stage.value,)))
    if execution is not None and execution.blocked_reason is not None:
        values.add(execution.blocked_reason)
    return tuple(sorted(values))


def _completed_reason(
    stage: StateResearchStage,
    execution: FreeDataOperationExecution | None,
) -> str:
    if stage is StateResearchStage.OBSERVATION:
        return "FREE_DATA_OBSERVATION_FROZEN"
    if execution is not None and execution.decision is not None:
        return f"{stage.value}_COMPLETED"
    return f"{stage.value}_ARTIFACT_RECORDED"


def _controlled_stage_child_result(
    *,
    kind: ContinuousChildKind,
    request: ChildExecutionRequest,
    snapshot: DecisionTimeOperationRunSnapshot,
    stage: DecisionTimeOperationStageName,
) -> ChildExecutionResult:
    receipt = _required_controlled_receipt(snapshot, stage)
    if len(receipt.output_references) != 1:
        raise ValueError(f"{stage.value} owner Receipt must expose one output")
    output = receipt.output_references[0]
    return ChildExecutionResult(
        child_kind=kind,
        child_run_id=snapshot.command.run_id,
        child_receipt_id=receipt.receipt_id,
        child_receipt_hash=receipt.content_hash,
        child_artifact_id=output.object_id,
        child_artifact_hash=output.content_hash,
        input_references=request.input_references,
        configuration_references=request.configuration_references,
    )


def _required_controlled_receipt(
    snapshot: DecisionTimeOperationRunSnapshot,
    stage: DecisionTimeOperationStageName,
) -> DecisionTimeOperationReceipt:
    matches = tuple(item.receipt for item in snapshot.stages if item.stage_name is stage and item.receipt is not None)
    if len(matches) != 1:
        raise ValueError(f"{stage.value} owner Receipt is unavailable")
    return matches[0]


def _owner_child_results(
    *,
    request: ChildExecutionRequest,
    dataset_result: ChildExecutionResult,
    feature_result: ChildExecutionResult,
    state_result: ChildExecutionResult | None,
    execution: FreeDataOperationExecution | None,
    summary: ResearchDailySummary,
) -> tuple[ChildExecutionResult, ...]:
    if state_result is None:
        raise ValueError("State System owner Receipt is unavailable")
    if execution is None or execution.terminal_package is None:
        raise ValueError("Controlled Operation owner Receipt is unavailable")
    package = execution.terminal_package
    controlled_request = _with_upstream_result(
        _with_upstream_result(_with_upstream_result(request, dataset_result), feature_result),
        state_result,
    )
    package_receipts = tuple(
        item.receipt
        for item in execution.snapshot.stages
        if item.stage_name is DecisionTimeOperationStageName.OPERATION_PACKAGE and item.receipt is not None
    )
    if len(package_receipts) > 1:
        raise ValueError("Controlled Operation owner Receipt is ambiguous")
    package_receipt_id = package_receipts[0].receipt_id if package_receipts else package.package_id
    package_receipt_hash = package_receipts[0].content_hash if package_receipts else package.content_hash
    controlled = ChildExecutionResult(
        child_kind=ContinuousChildKind.CONTROLLED_OPERATION,
        child_run_id=execution.snapshot.command.run_id,
        child_receipt_id=package_receipt_id,
        child_receipt_hash=package_receipt_hash,
        child_artifact_id=package.package_id,
        child_artifact_hash=package.content_hash,
        input_references=controlled_request.input_references,
        configuration_references=summary.configuration_references,
    )
    canonical_request = _with_upstream_result(controlled_request, controlled)
    canonical_ref = tuple(item for item in package.evidence_references if item.reference_type == "CANONICAL_LIFECYCLE_RUN")
    if len(canonical_ref) > 1:
        raise ValueError("Canonical Lifecycle owner Receipt is ambiguous")
    canonical = None
    decision_request = canonical_request
    if canonical_ref:
        canonical_artifact = canonical_ref[0]
        canonical = ChildExecutionResult(
            child_kind=ContinuousChildKind.CANONICAL_LIFECYCLE,
            child_run_id=canonical_artifact.object_id,
            child_receipt_id=canonical_artifact.object_id,
            child_receipt_hash=canonical_artifact.content_hash,
            child_artifact_id=canonical_artifact.object_id,
            child_artifact_hash=canonical_artifact.content_hash,
            input_references=canonical_request.input_references,
            configuration_references=summary.configuration_references,
        )
        decision_request = _with_upstream_result(canonical_request, canonical)
    decision = ChildExecutionResult(
        child_kind=ContinuousChildKind.DECISION_SYSTEM,
        child_run_id=summary.run_id,
        child_receipt_id=summary.summary_id,
        child_receipt_hash=summary.content_hash,
        child_artifact_id=summary.summary_id,
        child_artifact_hash=summary.content_hash,
        input_references=decision_request.input_references,
        configuration_references=summary.configuration_references,
    )
    results = [
        dataset_result,
        feature_result,
        state_result,
        controlled,
        decision,
    ]
    if canonical is not None:
        results.insert(-1, canonical)
    return tuple(results)


def _consumed_provider_contracts(
    preparation: FreeDataOperationPreparation,
    execution: FreeDataOperationExecution | None,
) -> tuple[ProviderContractLineage, ...]:
    consumed_products = {(str(item.provider_id), item.product) for item in preparation.source.acquired.provider_result.raw_payloads}
    declared = {(item.provider_id, item.product): item for item in FREE_DATA_PROVIDER_CONTRACTS}
    contracts = {
        declared.get(
            key,
            ProviderContractLineage(
                provider_id=key[0],
                product=key[1],
                contract_version="UNDECLARED_EXPLORATORY_CONTRACT",
            ),
        )
        for key in consumed_products
    }
    if execution is not None and execution.decision is not None and execution.decision.minute_coverage.accepted_source_references:
        contracts.add(next(item for item in FREE_DATA_PROVIDER_CONTRACTS if item.product == "ifzq.gtimg.cn:minute"))
    return tuple(
        sorted(
            contracts,
            key=lambda item: (
                item.provider_id,
                item.product,
                item.contract_version,
            ),
        )
    )


def _consumed_provider_sources(
    preparation: FreeDataOperationPreparation,
    execution: FreeDataOperationExecution | None,
) -> tuple[RuntimeArtifactReference, ...]:
    from market_regime_alpha.application.operational_research.supplemental_artifact import (
        load_verified_supplemental_research_evidence,
    )

    references: dict[tuple[str, ArtifactId], RuntimeArtifactReference] = {}

    def add(kind: str, artifact_id: ArtifactId, content_hash: str) -> None:
        key = (kind, artifact_id)
        value = RuntimeArtifactReference(kind, artifact_id, content_hash)
        existing = references.get(key)
        if existing is not None and existing != value:
            raise ValueError("consumed Provider source identity conflict")
        references[key] = value

    for item in preparation.source.acquired.source_manifest.source_artifacts:
        add("PROVIDER_SOURCE_ARTIFACT", item.artifact_id, item.content_hash)
    supplemental = load_verified_supplemental_research_evidence(
        preparation.controlled_preparation.input_paths.supplemental_research_evidence
    ).bundle
    add("SUPPLEMENTAL_EVIDENCE_BUNDLE", supplemental.bundle_id, supplemental.content_hash)
    add(
        "SUPPLEMENTAL_SOURCE_MANIFEST",
        supplemental.source_manifest.source_manifest_id,
        supplemental.source_manifest.content_hash,
    )
    for item in supplemental.source_manifest.source_artifacts:
        add("SUPPLEMENTAL_SOURCE_ARTIFACT", item.artifact_id, item.content_hash)
    if execution is not None and execution.decision is not None:
        coverage = execution.decision.minute_coverage
        add("MINUTE_ACQUISITION_COVERAGE", coverage.artifact_id, coverage.content_hash)
        add(
            "MINUTE_ACQUISITION_COMMAND",
            coverage.command.command_id,
            coverage.command.command_hash,
        )
        for symbol in coverage.symbol_coverage:
            for attempt in symbol.attempt_references:
                add("PROVIDER_ATTEMPT", attempt.attempt_id, attempt.attempt_hash)
                if attempt.source_artifact_id is not None and attempt.source_content_hash is not None:
                    add(
                        "PROVIDER_SOURCE_ARTIFACT",
                        attempt.source_artifact_id,
                        attempt.source_content_hash,
                    )
    return tuple(
        sorted(
            references.values(),
            key=lambda item: (
                item.reference_kind,
                str(item.artifact_id),
                item.content_hash,
            ),
        )
    )


def _runtime_lineage(
    *,
    preparation: FreeDataOperationPreparation,
    model_id: ModelId,
    configuration_id: ArtifactId,
    configuration_hash: str,
    registered: ModelVersionLineage | None,
) -> RuntimeModelLineage:
    controlled = preparation.controlled_preparation
    feature_ids = () if registered is None else registered.feature_definition_ids
    feature_materializations = tuple(
        ArtifactLineageReference(
            reference_kind="PREPARED_FEATURE_INPUT_SCOPE",
            artifact_id=ArtifactId(
                "runtime-feature-input:"
                + canonical_hash(
                    {
                        "static_bundle_id": str(controlled.static_feature_bundle.artifact.bundle_id),
                        "feature_definition_id": str(feature_id),
                    }
                )[7:]
            ),
            content_hash=canonical_hash(
                {
                    "static_bundle_hash": (controlled.static_feature_bundle.artifact.content_hash),
                    "feature_definition_id": str(feature_id),
                }
            ),
        )
        for feature_id in feature_ids
    )
    definition_hash = registered.definition_hash if registered is not None else canonical_hash({"unregistered_model_id": str(model_id)})[7:]
    code_revision = preparation.controlled_command.code_revision
    return RuntimeModelLineage.create(
        model_id=model_id,
        definition_hash=definition_hash,
        dataset=ArtifactLineageReference(
            reference_kind="MARKET_DATA_DATASET",
            artifact_id=ArtifactId(str(controlled.daily_dataset.artifact.dataset_id)),
            content_hash=controlled.daily_dataset.artifact.content_hash,
        ),
        universe_id=controlled.universe.universe_id,
        feature_definition_ids=tuple(FeatureDefinitionId(str(item)) for item in feature_ids),
        feature_materializations=feature_materializations,
        configuration=ArtifactLineageReference(
            reference_kind="MODEL_CONFIGURATION",
            artifact_id=configuration_id,
            content_hash=configuration_hash,
        ),
        code_revision=code_revision,
        code_hash=(
            registered.code_hash
            if registered is not None and registered.code_revision == code_revision
            else canonical_hash({"code_revision": code_revision})
        ),
        validation_protocol_refs=(registered.validation_protocol_refs if registered is not None else ()),
        data_eligibility=DataEligibility.EXPLORATORY,
    )


def _configured_models(
    configuration: ControlledOperationRuntimeConfiguration,
) -> dict[StateResearchStage, tuple[ModelId, str, ArtifactId, str]]:
    items = {
        StateResearchStage.MARKET_REGIME: configuration.research.market_regime,
        StateResearchStage.THEME_ROTATION: configuration.research.theme_rotation,
        StateResearchStage.CAPITAL_STATE: configuration.research.capital_evolution,
        StateResearchStage.CANDIDATE: configuration.research.candidate_discovery,
        StateResearchStage.SIGNAL: configuration.signal_model,
        StateResearchStage.FORECAST: configuration.path_forecast,
    }
    return {stage: _configured_model(item) for stage, item in items.items()}


def _configured_model(item: Any) -> tuple[ModelId, str, ArtifactId, str]:
    return (
        item.model_id,
        item.model_version,
        item.configuration_id,
        item.configuration_hash,
    )


def _selection_reference(receipt: ModelSelectionReceipt) -> RuntimeArtifactReference:
    return RuntimeArtifactReference("MODEL_SELECTION_RECEIPT", receipt.receipt_id, receipt.receipt_hash)


def _reference_key(item: RuntimeArtifactReference) -> tuple[str, str, str]:
    return item.reference_kind, str(item.artifact_id), item.content_hash


__all__ = [
    "CanonicalFreeDataProvider",
    "CanonicalFreeDataResearchComposition",
    "ControlledRuntimeModelSelector",
    "FREE_DATA_MODEL_SLOTS",
    "FREE_DATA_PROVIDER_CONTRACTS",
    "FREE_DATA_RUNTIME_SCOPE",
    "GovernedControlledModels",
    "free_data_provider_result",
]
