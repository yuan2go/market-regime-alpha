"""One ordered STATE child under the sole Continuous Research Runtime."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Mapping, Protocol

from market_regime_alpha.application.continuous_research.journal import (
    ContinuousChildKind,
    RuntimeArtifactReference,
)
from market_regime_alpha.application.continuous_research.ports import (
    ChildExecutionRequest,
    ChildExecutionResult,
)
from market_regime_alpha.application.state_system.postgres_repository import (
    PostgresStateSystemRepository,
)
from market_regime_alpha.application.state_system.bundles import (
    state_research_pipeline_identity,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.evidence.canonical import (
    canonical_hash,
    require_sha256,
    require_text,
)


class StateResearchStage(str, Enum):
    OBSERVATION = "OBSERVATION"
    MARKET_REGIME = "MARKET_REGIME"
    ETF_ROTATION = "ETF_ROTATION"
    THEME_ROTATION = "THEME_ROTATION"
    CAPITAL_STATE = "CAPITAL_STATE"
    DYNAMIC_POOL = "DYNAMIC_POOL"
    CANDIDATE = "CANDIDATE"
    SIGNAL = "SIGNAL"
    FORECAST = "FORECAST"


class StateResearchStageStatus(str, Enum):
    COMPLETED = "COMPLETED"
    DATA_INSUFFICIENT = "DATA_INSUFFICIENT"


STATE_RESEARCH_STAGE_ORDER = tuple(StateResearchStage)
STATE_SYSTEM_STAGE_ORDER = STATE_RESEARCH_STAGE_ORDER[:7]


@dataclass(frozen=True, slots=True)
class StateResearchStageArtifact:
    stage: StateResearchStage
    artifact_id: ArtifactId
    artifact_hash: str
    available_at: datetime
    data_eligibility: DataEligibility
    reason_codes: tuple[str, ...]
    status: StateResearchStageStatus = StateResearchStageStatus.COMPLETED

    def __post_init__(self) -> None:
        require_sha256("artifact_hash", self.artifact_hash)
        if self.available_at.tzinfo is None or self.available_at.utcoffset() is None:
            raise ValueError("stage available_at must be timezone-aware")
        if not isinstance(self.data_eligibility, DataEligibility):
            raise TypeError("stage data_eligibility must be DataEligibility")
        if self.reason_codes != tuple(sorted(set(self.reason_codes))):
            raise ValueError("stage reason_codes must be unique and sorted")

    def to_reference(self) -> RuntimeArtifactReference:
        return RuntimeArtifactReference(
            reference_kind=f"STATE_RESEARCH_{self.stage.value}",
            artifact_id=self.artifact_id,
            content_hash=self.artifact_hash,
        )


@dataclass(frozen=True, slots=True)
class StateResearchStageContext:
    request: ChildExecutionRequest
    completed: tuple[StateResearchStageArtifact, ...]


class StateResearchStageService(Protocol):
    stage: StateResearchStage

    def execute(
        self, context: StateResearchStageContext
    ) -> StateResearchStageArtifact: ...


@dataclass(frozen=True, slots=True)
class StateResearchPipelineResult:
    artifact_id: ArtifactId
    artifact_hash: str
    stages: tuple[StateResearchStageArtifact, ...]
    reason_codes: tuple[str, ...]

    @property
    def entry_authority_granted(self) -> bool:
        return False

    @property
    def broker_authority_granted(self) -> bool:
        return False


class OrderedStateResearchPipeline:
    """Adapters call existing domain services in one auditable dependency order."""

    def __init__(
        self,
        *,
        services: Mapping[StateResearchStage, StateResearchStageService],
    ) -> None:
        if set(services) != set(STATE_SYSTEM_STAGE_ORDER):
            raise ValueError("State System pipeline requires every owned stage")
        for stage, service in services.items():
            if service.stage is not stage:
                raise ValueError("State Research stage service identity mismatch")
        self._services = dict(services)

    def execute(self, request: ChildExecutionRequest) -> StateResearchPipelineResult:
        completed: list[StateResearchStageArtifact] = []
        for stage in STATE_SYSTEM_STAGE_ORDER:
            artifact = self._services[stage].execute(
                StateResearchStageContext(request=request, completed=tuple(completed))
            )
            if artifact.stage is not stage:
                raise ValueError("State Research service returned an out-of-order stage")
            if artifact.available_at > request.as_of_time:
                raise ValueError("State Research stage cannot publish future evidence")
            completed.append(artifact)
        pipeline_id, digest = state_research_pipeline_identity(
            run_id=request.run_id,
            tick_id=request.tick_id,
            as_of_time=request.as_of_time,
            stages=tuple(
                (
                    artifact.stage.value,
                    artifact.artifact_id,
                    artifact.artifact_hash,
                    artifact.available_at,
                )
                for artifact in completed
            ),
        )
        return StateResearchPipelineResult(
            artifact_id=pipeline_id,
            artifact_hash=digest,
            stages=tuple(completed),
            reason_codes=("ENTRY_BLOCKED", "STATE_RESEARCH_CHAIN_COMPLETED"),
        )


class StateSystemRuntimeDelegate:
    """Durable STATE_SYSTEM child; it owns no scheduler or Provider."""

    child_kind = ContinuousChildKind.STATE_SYSTEM

    def __init__(
        self,
        *,
        pipeline: OrderedStateResearchPipeline,
        repository: PostgresStateSystemRepository,
    ) -> None:
        if not isinstance(pipeline, OrderedStateResearchPipeline):
            raise TypeError("pipeline must be OrderedStateResearchPipeline")
        if not isinstance(repository, PostgresStateSystemRepository):
            raise TypeError("repository must be PostgresStateSystemRepository")
        self._pipeline = pipeline
        self._repository = repository

    @property
    def entry_authority_granted(self) -> bool:
        return False

    @property
    def broker_authority_granted(self) -> bool:
        return False

    def lookup(self, request: ChildExecutionRequest) -> ChildExecutionResult | None:
        return self._repository.lookup_runtime_child(request)

    def execute(self, request: ChildExecutionRequest) -> ChildExecutionResult:
        existing = self.lookup(request)
        if existing is not None:
            return existing
        pipeline_result = self._pipeline.execute(request)
        receipt_payload = {
            "schema": "state_system_runtime_receipt/v3",
            "request_idempotency_key": request.idempotency_key,
            "pipeline_artifact_id": str(pipeline_result.artifact_id),
            "pipeline_artifact_hash": pipeline_result.artifact_hash,
            "stage_references": [
                {
                    **artifact.to_reference().to_canonical_dict(),
                    "data_eligibility": artifact.data_eligibility.value,
                    "stage_status": artifact.status.value,
                }
                for artifact in pipeline_result.stages
            ],
            "reason_codes": list(pipeline_result.reason_codes),
        }
        receipt_hash = canonical_hash(receipt_payload)
        result = ChildExecutionResult(
            child_kind=self.child_kind,
            child_run_id=ArtifactId(
                f"state-system-run:{request.idempotency_key.removeprefix('continuous-children-')}"
            ),
            child_receipt_id=ArtifactId(f"state-system-receipt:{receipt_hash[7:]}"),
            child_receipt_hash=receipt_hash,
            child_artifact_id=pipeline_result.artifact_id,
            child_artifact_hash=pipeline_result.artifact_hash,
            input_references=request.input_references,
            configuration_references=request.configuration_references,
        )
        return self._repository.record_runtime_child(
            request,
            result,
            stage_authorities=pipeline_result.stages,
            receipt_payload=receipt_payload,
        )


def require_versioned_stage_service_name(name: str) -> None:
    """Small construction guard for adapters selected by Runtime Policy/Command."""

    require_text("versioned State Research stage service", name)
