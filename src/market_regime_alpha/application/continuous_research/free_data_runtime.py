"""Executable BaoStock/Tencent composition for the sole Continuous Runtime."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Protocol

from market_regime_alpha.application.continuous_research.composition import (
    CONTINUOUS_CHILD_ORDER,
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
from market_regime_alpha.application.controlled_operation.input_artifacts import (
    load_controlled_runtime_configuration,
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
from market_regime_alpha.core.identity import (
    ArtifactId,
    FeatureDefinitionId,
    ModelId,
)
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.data.pit_contracts import PITSourceEvidenceLevel
from market_regime_alpha.data.providers.public_composite import (
    BAOSTOCK_PUBLIC_PROVIDER_ID,
    TENCENT_FREE_OPERATIONAL_PROFILE_ID,
    TENCENT_PUBLIC_PROVIDER_ID,
)
from market_regime_alpha.evidence.canonical import canonical_hash
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
)


ChildInvocationBuilder = Callable[
    [ChildExecutionRequest], FreeDataPreparationInvocation
]
Clock = Callable[[], datetime]


class RuntimeModelGovernancePort(Protocol):
    def resolve_champion(
        self,
        *,
        runtime_scope: str,
        model_slot: str,
        purpose: RuntimePurpose,
        as_of: datetime,
    ) -> ModelRuntimeAssignment: ...

    def get_version_lineage_for_model(
        self, model_id: ModelId
    ) -> ModelVersionLineage: ...

    def select(self, request: ModelSelectionRequest) -> ModelSelectionReceipt: ...


@dataclass(frozen=True, slots=True)
class GovernedControlledModels:
    receipts: tuple[tuple[StateResearchStage, ModelSelectionReceipt], ...]

    @property
    def all_selected(self) -> bool:
        return all(
            receipt.status is SelectionStatus.SELECTED
            for _, receipt in self.receipts
        )

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
        configuration = load_controlled_runtime_configuration(
            runtime_configuration_path.resolve()
        )
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
                lineage = self._repository.get_version_lineage_for_model(
                    governed_model_id
                )
            except KeyError:
                lineage = None
                rejections.add("MODEL_VERSION_LINEAGE_MISSING")
            if governed_model_id != model_id:
                rejections.add("RUNTIME_CONFIGURATION_MODEL_MISMATCH")
            if lineage is not None:
                if lineage.model_version != model_version:
                    rejections.add("RUNTIME_CONFIGURATION_VERSION_MISMATCH")
                if (
                    lineage.configuration.artifact_id != config_id
                    or lineage.configuration.content_hash != config_hash
                ):
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
                            idempotency_key=(
                                f"{request.run_id}:{request.tick_id}:"
                                f"{request.authority_mode.value}:{slot}"
                            ),
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
        invocation_builder: Callable[
            [ProviderAcquisitionRequest], FreeDataPreparationInvocation
        ],
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
    ) -> None:
        self._service = service
        self._invocation_builder = invocation_builder
        self._model_selector = model_selector
        self._summary_repository = summary_repository
        self._summary_runtime = ResearchSummaryRuntimeService(summary_repository)

    def lookup_children(
        self, request: ChildExecutionRequest
    ) -> tuple[ChildExecutionResult, ...] | None:
        if request.authority_mode.requires_production_authorization:
            return None
        try:
            summary = self._summary_repository.get_research_summary_for_tick(
                run_id=request.run_id,
                tick_id=request.tick_id,
                runtime_mode=request.authority_mode,
            )
        except KeyError:
            return None
        return _child_results(request, summary)

    def execute_children(
        self, request: ChildExecutionRequest
    ) -> tuple[ChildExecutionResult, ...]:
        invocation = self._invocation_builder(request)
        preparation = self._service.prepare(
            request=invocation.request,
            runtime_configuration_path=invocation.runtime_configuration_path,
            idempotency_key=invocation.idempotency_key,
        )
        governed = self._model_selector.select(
            request=request,
            preparation=preparation,
            runtime_configuration_path=preparation.controlled_preparation.input_paths.runtime_configuration,
        )
        if request.authority_mode.requires_production_authorization:
            # Free public evidence remains below the Production data ceiling even
            # if a governance operator accidentally assigns a Production model.
            raise PermissionError("FREE_DATA_PRODUCTION_AUTHORITY_DENIED")
        execution = None
        if governed.all_selected:
            execution = self._service.run(
                request=invocation.request,
                runtime_configuration_path=invocation.runtime_configuration_path,
                idempotency_key=invocation.idempotency_key,
            )
        summary = _build_summary(
            request=request,
            preparation=preparation,
            execution=execution,
            governed=governed,
        )
        persisted = self._summary_runtime.execute(request=request, summary=summary)
        return _child_results(request, persisted)


def free_data_provider_result(
    preparation: FreeDataOperationPreparation,
    *,
    completed_at: datetime,
) -> ProviderAcquisitionResult:
    source = preparation.source.acquired
    manifest = source.source_manifest
    retrieved_at = max(
        item.retrieved_at.value for item in manifest.source_artifacts
    ).astimezone(UTC)
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
) -> ResearchDailySummary:
    controlled = preparation.controlled_preparation
    dataset = RuntimeArtifactReference(
        "MARKET_DATA_DATASET",
        ArtifactId(str(controlled.daily_dataset.artifact.dataset_id)),
        controlled.daily_dataset.artifact.content_hash,
    )
    feature = RuntimeArtifactReference(
        "STATIC_FEATURE_BUNDLE",
        controlled.static_bundle.artifact_id,
        controlled.static_bundle.content_hash,
    )
    stages = tuple(
        _stage_evidence(
            stage=stage,
            request=request,
            preparation=preparation,
            execution=execution,
            governed=governed,
        )
        for stage in STATE_RESEARCH_STAGE_ORDER
    )
    receipts = tuple(
        _selection_reference(receipt)
        for _, receipt in governed.receipts
    )
    active_configuration = load_controlled_runtime_configuration(
        controlled.input_paths.runtime_configuration
    )
    return ResearchDailySummary.create(
        runtime_mode=request.authority_mode,
        run_id=request.run_id,
        tick_id=request.tick_id,
        trading_date=request.trading_date,
        decision_time=request.as_of_time,
        provider_profile_id=TENCENT_FREE_OPERATIONAL_PROFILE_ID,
        provider_contracts=FREE_DATA_PROVIDER_CONTRACTS,
        source_manifest=RuntimeArtifactReference(
            "SOURCE_MANIFEST",
            request.source_manifest_id,
            request.source_manifest_hash,
        ),
        dataset=dataset,
        feature_bundle=feature,
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
        created_at=request.as_of_time,
    )


def _stage_evidence(
    *,
    stage: StateResearchStage,
    request: ChildExecutionRequest,
    preparation: FreeDataOperationPreparation,
    execution: FreeDataOperationExecution | None,
    governed: GovernedControlledModels,
) -> ResearchStageEvidence:
    receipt = governed.for_stage(stage)
    selection = None if receipt is None else _selection_reference(receipt)
    output = _execution_stage_output(stage, preparation, execution)
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
    elif (
        output is not None
        and (
            stage is StateResearchStage.OBSERVATION
            or (execution is not None and execution.decision is not None)
        )
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
        available_at=request.as_of_time,
        data_eligibility=DataEligibility.EXPLORATORY,
        evidence_ceiling=PITSourceEvidenceLevel.FREE_DATA_EXPLORATORY,
        missing_evidence=missing,
        reason_codes=reasons,
    )


def _execution_stage_output(
    stage: StateResearchStage,
    preparation: FreeDataOperationPreparation,
    execution: FreeDataOperationExecution | None,
) -> RuntimeArtifactReference | None:
    if stage is StateResearchStage.OBSERVATION:
        manifest = preparation.prepared_inputs.manifest
        return RuntimeArtifactReference(
            "FREE_DATA_PREPARED_INPUTS", manifest.manifest_id, manifest.content_hash
        )
    if execution is not None and execution.decision is None:
        package = execution.terminal_package
        if package is not None:
            reference_type = {
                StateResearchStage.MARKET_REGIME: "CONTROLLED_RESEARCH",
                StateResearchStage.THEME_ROTATION: "CONTROLLED_RESEARCH",
                StateResearchStage.CAPITAL_STATE: "CONTROLLED_RESEARCH",
                StateResearchStage.CANDIDATE: "CANDIDATE_SET",
            }.get(stage)
            matches = tuple(
                item
                for item in package.evidence_references
                if item.reference_type == reference_type
            )
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
        return RuntimeArtifactReference(
            "SIGNAL", signal.artifact_id, signal.envelope.content_hash
        )
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


def _child_results(
    request: ChildExecutionRequest,
    summary: ResearchDailySummary,
) -> tuple[ChildExecutionResult, ...]:
    stage_digest = canonical_hash(
        {"stages": [stage.to_canonical_dict() for stage in summary.stages]}
    )
    stage_ref = RuntimeArtifactReference(
        "STATE_RESEARCH_PIPELINE",
        ArtifactId(f"state-research-pipeline:{stage_digest[7:]}"),
        stage_digest,
    )
    artifacts = {
        ContinuousChildKind.DAILY_DATASET: summary.dataset,
        ContinuousChildKind.FEATURE_MATERIALIZATION: summary.feature_bundle,
        ContinuousChildKind.STATE_SYSTEM: stage_ref,
        ContinuousChildKind.CONTROLLED_OPERATION: stage_ref,
        ContinuousChildKind.CANONICAL_LIFECYCLE: stage_ref,
        ContinuousChildKind.DECISION_SYSTEM: RuntimeArtifactReference(
            "RESEARCH_DAILY_SUMMARY", summary.summary_id, summary.content_hash
        ),
    }
    results = []
    stage_request = request
    for kind in CONTINUOUS_CHILD_ORDER:
        artifact = artifacts[kind]
        receipt_hash = canonical_hash(
            {
                "schema_version": "canonical-free-data-child-receipt/v1",
                "child_kind": kind.value,
                "run_id": str(request.run_id),
                "tick_id": str(request.tick_id),
                "summary_id": str(summary.summary_id),
                "summary_hash": summary.content_hash,
                "artifact": artifact.to_canonical_dict(),
            }
        )
        result = ChildExecutionResult(
            child_kind=kind,
            child_run_id=request.run_id,
            child_receipt_id=ArtifactId(
                f"canonical-free-data-child-receipt:{receipt_hash[7:]}"
            ),
            child_receipt_hash=receipt_hash,
            child_artifact_id=artifact.artifact_id,
            child_artifact_hash=artifact.content_hash,
            input_references=stage_request.input_references,
            configuration_references=summary.configuration_references,
        )
        results.append(result)
        stage_request = _with_upstream_result(stage_request, result)
    return tuple(results)


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
                        "prepared_manifest_id": str(
                            preparation.prepared_inputs.manifest.manifest_id
                        ),
                        "static_bundle_id": str(controlled.static_bundle.artifact_id),
                        "feature_definition_id": str(feature_id),
                    }
                )[7:]
            ),
            content_hash=canonical_hash(
                {
                    "prepared_manifest_hash": preparation.prepared_inputs.manifest.content_hash,
                    "static_bundle_hash": controlled.static_bundle.content_hash,
                    "feature_definition_id": str(feature_id),
                }
            ),
        )
        for feature_id in feature_ids
    )
    definition_hash = (
        registered.definition_hash
        if registered is not None
        else canonical_hash({"unregistered_model_id": str(model_id)})[7:]
    )
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
        validation_protocol_refs=(
            registered.validation_protocol_refs
            if registered is not None
            else ()
        ),
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
    return RuntimeArtifactReference(
        "MODEL_SELECTION_RECEIPT", receipt.receipt_id, receipt.receipt_hash
    )


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
