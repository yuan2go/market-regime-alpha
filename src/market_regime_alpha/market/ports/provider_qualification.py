"""Narrow Market-owned Provider qualification persistence ports."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from types import TracebackType
from typing import Protocol, Self
from uuid import UUID

from market_regime_alpha.market.domain import (
    ProviderFinalityObservation,
    ProviderQualificationProtocol,
)
from market_regime_alpha.runtime.ports import (
    AuditRepository,
    CommandReceiptRepository,
    RuntimeCommandFinalization,
)


@dataclass(frozen=True, slots=True)
class ProviderQualificationProtocolRecord:
    provider_qualification_protocol_id: UUID
    protocol_code: str
    revision: int
    provider_product_id: UUID
    purpose: str
    evidence_class: str
    requirement_count: int
    requirement_roster_sha256: str
    content_sha256: str
    registered_at: datetime


@dataclass(frozen=True, slots=True)
class ProviderQualificationCaptureMember:
    provider_qualification_capture_member_id: UUID
    member_ordinal: int
    capture_id: UUID
    provider_product_id: UUID
    capture_status: str
    artifact_id: UUID | None
    source_availability_status: str
    source_available_at: datetime | None
    known_at: datetime
    runtime_capture_lineage: bool
    artifact_verified: bool
    source_gap_count: int
    content_sha256: str


@dataclass(frozen=True, slots=True)
class ProviderRequirementEvaluation:
    provider_qualification_requirement_result_id: UUID
    provider_qualification_requirement_id: UUID
    result_ordinal: int
    requirement_kind: str
    result_status: str
    observation_count: int
    satisfied_count: int
    observed_ratio: Decimal
    reason_code: str
    content_sha256: str


@dataclass(frozen=True, slots=True)
class ProviderQualificationDecisionRecord:
    provider_qualification_decision_id: UUID
    decision_code: str
    provider_qualification_protocol_id: UUID
    provider_product_id: UUID
    purpose: str
    evidence_class: str
    decision_status: str
    capture_count: int
    capture_roster_sha256: str
    requirement_result_count: int
    requirement_result_roster_sha256: str
    reason_code: str
    content_sha256: str
    decided_at: datetime


class ProviderQualificationRepository(Protocol):
    def insert_protocol(
        self,
        protocol: ProviderQualificationProtocol,
        *,
        request_identity: str,
        request_sha256: str,
    ) -> ProviderQualificationProtocolRecord: ...

    def protocol_record(
        self, provider_qualification_protocol_id: UUID, *, lock: bool
    ) -> ProviderQualificationProtocolRecord: ...

    def insert_finality_observation(
        self, observation: ProviderFinalityObservation
    ) -> int: ...

    def complete(
        self,
        *,
        provider_qualification_decision_id: UUID,
        decision_code: str,
        provider_qualification_protocol_id: UUID,
        request_identity: str,
        request_sha256: str,
    ) -> ProviderQualificationDecisionRecord: ...

    def decision_record(
        self, provider_qualification_decision_id: UUID, *, lock: bool
    ) -> ProviderQualificationDecisionRecord: ...

    def reconcile_protocol(self, provider_qualification_protocol_id: UUID) -> bool: ...

    def reconcile_decision(self, provider_qualification_decision_id: UUID) -> bool: ...


class ProviderQualificationUnitOfWork(Protocol):
    @property
    def provider_qualifications(self) -> ProviderQualificationRepository: ...

    @property
    def receipts(self) -> CommandReceiptRepository: ...

    @property
    def audit(self) -> AuditRepository: ...

    @property
    def runtime_finalization(self) -> RuntimeCommandFinalization: ...

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    def commit(self) -> None: ...


class ProviderQualificationUnitOfWorkProvider(Protocol):
    def __call__(self) -> ProviderQualificationUnitOfWork: ...


__all__ = [
    "ProviderQualificationCaptureMember",
    "ProviderQualificationDecisionRecord",
    "ProviderQualificationProtocolRecord",
    "ProviderQualificationRepository",
    "ProviderQualificationUnitOfWork",
    "ProviderQualificationUnitOfWorkProvider",
    "ProviderRequirementEvaluation",
]
