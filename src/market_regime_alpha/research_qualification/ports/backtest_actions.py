"""Typed read/model seams used by generic Backtest action execution."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Protocol
from uuid import UUID

from market_regime_alpha.research_qualification.domain.backtest import (
    BacktestSpecification,
)
from market_regime_alpha.research_qualification.domain.backtest_dataset import (
    BacktestDatasetFeatureCell,
)
from market_regime_alpha.research_qualification.domain.exploratory import (
    ExploratoryRetrospectiveDatasetScope,
)
from market_regime_alpha.shared.identity import ContentHash, InstrumentId


@dataclass(frozen=True, slots=True)
class BacktestArchiveSeal:
    knowledge_cutoff: datetime


@dataclass(frozen=True, slots=True)
class BacktestUniverseTemplate:
    universe_id: UUID
    market_provider_product_id: UUID
    classification_scheme: str
    classification_code: str


@dataclass(frozen=True, slots=True)
class BacktestTradingSession:
    trading_session_id: UUID
    exchange_code: str
    session_date: date
    timezone_name: str
    open_at: datetime
    close_at: datetime


@dataclass(frozen=True, slots=True)
class BacktestTargetCheckpoint:
    target_checkpoint_id: UUID
    role: str
    session_offset: int
    local_time: time
    timezone_name: str


@dataclass(frozen=True, slots=True)
class BacktestFeatureExecutionDefinition:
    feature_definition_id: UUID
    content_sha256: ContentHash | str
    feature_code: str
    algorithm_code: str
    algorithm_version: str
    algorithm_sha256: ContentHash | str

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "content_sha256", ContentHash(str(self.content_sha256))
        )
        object.__setattr__(
            self, "algorithm_sha256", ContentHash(str(self.algorithm_sha256))
        )


@dataclass(frozen=True, slots=True)
class BacktestPopulationMember:
    instrument_id: InstrumentId
    universe_member_id: UUID
    eligibility_assessment_id: UUID


@dataclass(frozen=True, slots=True)
class BacktestDatasetExecution:
    dataset_id: UUID
    universe_revision_id: UUID
    eligibility_policy_id: UUID
    retrospective_scope: ExploratoryRetrospectiveDatasetScope


@dataclass(frozen=True, slots=True)
class BacktestPartitionExecution:
    research_partition_id: UUID
    content_sha256: ContentHash | str
    purpose: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "content_sha256", ContentHash(str(self.content_sha256))
        )


@dataclass(frozen=True, slots=True)
class BacktestEvaluationResult:
    evaluation_run_id: UUID
    evaluation_protocol_id: UUID
    metric_count: int
    metric_roster_sha256: ContentHash | str
    completed_at: datetime

    def __post_init__(self) -> None:
        if self.metric_count < 1:
            raise ValueError("completed Backtest Evaluation requires metrics")
        if self.completed_at.tzinfo is None:
            raise ValueError("completed Backtest Evaluation time must be aware")
        object.__setattr__(
            self,
            "metric_roster_sha256",
            ContentHash(str(self.metric_roster_sha256)),
        )


@dataclass(frozen=True, slots=True)
class BacktestFeatureRequest:
    definition: BacktestFeatureExecutionDefinition
    scope: ExploratoryRetrospectiveDatasetScope
    instrument_id: InstrumentId
    session_date: date
    session_close_at: datetime


class BacktestFeatureMaterializer(Protocol):
    def supports(self, definition: BacktestFeatureExecutionDefinition) -> bool: ...

    def materialize(
        self,
        request: BacktestFeatureRequest,
    ) -> BacktestDatasetFeatureCell: ...


class BacktestActionReadPort(Protocol):
    def archive_seal(
        self, specification: BacktestSpecification
    ) -> BacktestArchiveSeal: ...

    def universe_template(
        self, specification: BacktestSpecification
    ) -> BacktestUniverseTemplate: ...

    def trading_session(
        self,
        specification: BacktestSpecification,
        trading_session_id: UUID,
    ) -> BacktestTradingSession: ...

    def target_checkpoints(
        self, specification: BacktestSpecification
    ) -> tuple[BacktestTargetCheckpoint, ...]: ...

    def feature_definitions(
        self, specification: BacktestSpecification
    ) -> tuple[BacktestFeatureExecutionDefinition, ...]: ...

    def retrospective_universe_id(
        self,
        *,
        specification: BacktestSpecification,
        decision_time: datetime,
        scope_content_sha256: str,
    ) -> UUID: ...

    def eligible_population(
        self,
        *,
        universe_revision_id: UUID,
        eligibility_policy_id: UUID,
    ) -> tuple[BacktestPopulationMember, ...]: ...

    def dataset_execution(
        self,
        *,
        exploratory_backtest_run_id: UUID,
        arm_id: UUID,
        fold_session_id: UUID,
    ) -> BacktestDatasetExecution: ...

    def candidate_set_id(
        self,
        *,
        dataset_id: UUID,
        candidate_policy_id: UUID,
    ) -> UUID: ...

    def decision_run_id(self, *, dataset_id: UUID) -> UUID: ...

    def decision_commitment_ids(
        self,
        *,
        exploratory_backtest_run_id: UUID,
        arm_id: UUID,
        fold_id: UUID,
        fold_session_id: UUID,
        target_definition_id: UUID,
    ) -> tuple[UUID, ...]: ...

    def model_version_id(
        self,
        *,
        exploratory_backtest_run_id: UUID,
        model_training_requirement_id: UUID,
    ) -> UUID: ...

    def partition_execution(
        self, research_partition_id: UUID
    ) -> BacktestPartitionExecution: ...

    def evaluation_result(
        self, evaluation_run_id: UUID
    ) -> BacktestEvaluationResult: ...


__all__ = [
    "BacktestActionReadPort",
    "BacktestArchiveSeal",
    "BacktestDatasetExecution",
    "BacktestFeatureExecutionDefinition",
    "BacktestFeatureMaterializer",
    "BacktestFeatureRequest",
    "BacktestEvaluationResult",
    "BacktestPartitionExecution",
    "BacktestPopulationMember",
    "BacktestTargetCheckpoint",
    "BacktestTradingSession",
    "BacktestUniverseTemplate",
]
