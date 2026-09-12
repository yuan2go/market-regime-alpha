"""Exact reads used by the existing Runtime's daily prediction steps."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from market_regime_alpha.research_qualification.domain.daily_inputs import DailyDataReady
from market_regime_alpha.research_qualification.domain.daily_prediction import DailyPopulationMember, DailyPredictionPlan
from market_regime_alpha.research_qualification.domain.model import ArtifactBinding
from market_regime_alpha.research_qualification.domain.targets import TargetDefinition


DailyOutcomeCursor = tuple[int, datetime, UUID]
DailyPublicationCursor = tuple[datetime, UUID]


@dataclass(frozen=True, slots=True)
class DailyDeliveryWorkItem:
    run_id: UUID
    requested_at: datetime
    code_sha: str
    config_sha256: str
    schedule_id: UUID
    schedule_code: str
    fire_key: str
    plan_content: bytes | None
    delivery_state: str
    error_code: str | None = None

    @property
    def cursor(self) -> DailyPublicationCursor:
        return self.requested_at, self.run_id


@dataclass(frozen=True, slots=True)
class DailyOutcomeWorkItem:
    """Bounded Runtime discovery result; frozen bytes remain the request Authority."""

    run_id: UUID
    schedule_id: UUID
    schedule_code: str
    fire_key: str
    parent_run_id: UUID | None
    run_state: str
    requested_at: datetime
    code_sha: str
    config_sha256: str
    plan_content: bytes | None
    error_code: str | None
    settlement_steps_completed: bool = False

    @property
    def cursor(self) -> DailyOutcomeCursor:
        return ({"RUNNING": 0, "QUEUED": 1, "WAITING": 2}.get(self.run_state, 3), self.requested_at, self.run_id)


@dataclass(frozen=True, slots=True)
class DailySessionWorkItem:
    """Exact Runtime candidate for one session pair, including terminal work."""

    experimental_model_use_id: UUID
    prediction_id: UUID
    phase: str
    run_id: UUID
    schedule_id: UUID
    schedule_code: str
    fire_key: str
    code_sha: str
    config_sha256: str
    plan_content: bytes


class DailyPredictionReads(Protocol):
    def unfinished_delivery_channels(self) -> tuple[str, ...]: ...
    def delivery_work_items(self, channel: str, *, limit: int = 32, after: DailyPublicationCursor | None = None, recent: bool = False) -> tuple[DailyDeliveryWorkItem, ...]: ...
    def delivery_work_counts(self, channel: str) -> dict[str, int]: ...
    def delivery_attempt_id(self, run_id: UUID, attempt_no: int) -> UUID: ...
    def operational_ledger_rows(self, *, complete_history: bool = False) -> dict[str, Any]: ...
    def published_report(self, plan: DailyPredictionPlan, key: str, expected: bytes) -> ArtifactBinding: ...
    def now(self) -> datetime: ...
    def ready(self, plan: DailyPredictionPlan) -> DailyDataReady: ...
    def universe_revision(self, plan: DailyPredictionPlan) -> UUID: ...
    def population(self, plan: DailyPredictionPlan) -> tuple[DailyPopulationMember, ...]: ...
    def candidate_set(self, plan: DailyPredictionPlan) -> UUID: ...
    def decision_run(self, plan: DailyPredictionPlan) -> UUID: ...
    def forecast_projection(self, plan: DailyPredictionPlan) -> dict[str, Any]: ...
    def first_attempt_at(self, step_id: UUID) -> datetime: ...
    def target_definition(self, plan: DailyPredictionPlan) -> TargetDefinition: ...
    def partition_hash(self, partition_id: UUID) -> str: ...
    def require_partition_roster(self, partition_id: UUID, commitments: tuple[UUID, ...]) -> None: ...
    def evaluation_projection(self, evaluation_id: UUID) -> dict[str, Any]: ...
    def evaluation_observations(self, evaluation_id: UUID) -> dict[str, Any]: ...
    def validity_observation_facts(self, plan: DailyPredictionPlan, evaluation_id: UUID) -> dict[str, Any]: ...
    def validity_calendar(self) -> list[dict[str, Any]]: ...
    def outcome_work_items(self, *, limit: int = 64, after: DailyOutcomeCursor | None = None) -> tuple[DailyOutcomeWorkItem, ...]: ...
    def outcome_work_counts(self) -> dict[str, int]: ...
    def run_plan_content(self, run_id: UUID) -> bytes | None: ...
    def session_work_items(self, plan: DailyPredictionPlan, input_session_id: UUID,
                           target_session_id: UUID) -> tuple[DailySessionWorkItem, ...]: ...
    def model_use_available(self, plan: DailyPredictionPlan) -> bool: ...
    def experimental_model_use_record(self, identity: UUID) -> dict[str, Any]: ...
    def operational_health(self, plan: DailyPredictionPlan, *, template: DailyPredictionPlan | None = None) -> dict[str, Any]: ...
    def published_artifact(
        self, idempotency_key: str
    ) -> tuple[ArtifactBinding, bytes] | None: ...
    def research_dispositions(
        self, prediction_id: UUID
    ) -> tuple[dict[str, Any], ...]: ...
