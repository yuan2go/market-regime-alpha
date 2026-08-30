"""Target Definition aggregate persistence port."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from market_regime_alpha.research_qualification.domain.targets import TargetDefinition


@dataclass(frozen=True, slots=True)
class TargetDefinitionRecord:
    target_definition_id: UUID
    target_code: str
    version: int
    registration_status: str
    supersedes_target_definition_id: UUID | None
    content_sha256: str
    checkpoint_count: int
    checkpoint_roster_sha256: str
    metric_count: int
    metric_roster_sha256: str
    dependency_count: int
    dependency_roster_sha256: str
    registration_request_identity: str
    registration_request_sha256: str
    registered_at: datetime


@dataclass(frozen=True, slots=True)
class TargetRegistrationReconciliation:
    target_definition_id: UUID
    checkpoint_count: int
    metric_count: int
    dependency_count: int
    checkpoint_roster_sha256: str
    metric_roster_sha256: str
    dependency_roster_sha256: str
    definition_sha256: str
    matched: bool


class TargetDefinitionRepository(Protocol):
    def lock_registration_identity(self, target_code: str, version: int) -> None: ...

    def insert_target_definition(
        self,
        definition: TargetDefinition,
        *,
        registration_request_identity: str,
        registration_request_sha256: str,
        actor_type: str,
        actor_id: str,
    ) -> TargetDefinitionRecord: ...

    def target_definition(
        self,
        target_definition_id: UUID,
        *,
        lock: bool,
    ) -> TargetDefinition: ...

    def target_record(
        self,
        target_definition_id: UUID,
        *,
        lock: bool,
    ) -> TargetDefinitionRecord: ...

    def reconcile(
        self,
        target_definition_id: UUID,
        *,
        lock: bool,
    ) -> TargetRegistrationReconciliation: ...


__all__ = [
    "TargetDefinitionRecord",
    "TargetDefinitionRepository",
    "TargetRegistrationReconciliation",
]
