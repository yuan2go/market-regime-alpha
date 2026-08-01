"""Storage-neutral repository contracts for durable platform governance."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from market_regime_alpha.core.identity import ExperimentId, ModelId
from market_regime_alpha.platform.experiment_governance import (
    ExperimentAccessRecord,
    FrozenExperimentProtocol,
)
from market_regime_alpha.platform.model_registry import ModelRegistration


class VersionConflictError(RuntimeError):
    """A mutable aggregate changed after the caller loaded it."""


@dataclass(frozen=True, slots=True)
class VersionedModelRegistration:
    registration: ModelRegistration
    version: int

    def __post_init__(self) -> None:
        if self.version < 0:
            raise ValueError("model registration version must be non-negative")


@dataclass(frozen=True, slots=True)
class VersionedExperimentGovernance:
    protocol: FrozenExperimentProtocol
    access_record: ExperimentAccessRecord
    version: int

    def __post_init__(self) -> None:
        if self.protocol.experiment_id != self.access_record.experiment_id:
            raise ValueError("experiment governance identity mismatch")
        if self.version < 0:
            raise ValueError("experiment governance version must be non-negative")
        if self.version != (
            self.access_record.validation_access_count
            + self.access_record.sealed_test_access_count
        ):
            raise ValueError("experiment version must equal append-only access count")


class ModelRegistryRepository(Protocol):
    def resolve_command(
        self,
        model_id: ModelId,
        *,
        idempotency_key: str,
        command_hash: str,
    ) -> VersionedModelRegistration | None: ...

    def get(self, model_id: ModelId) -> VersionedModelRegistration: ...

    def create(
        self,
        registration: ModelRegistration,
        *,
        idempotency_key: str,
    ) -> VersionedModelRegistration: ...

    def compare_and_set(
        self,
        model_id: ModelId,
        *,
        expected_version: int,
        registration: ModelRegistration,
        idempotency_key: str,
        command_hash: str | None = None,
    ) -> VersionedModelRegistration: ...


class ExperimentGovernanceRepository(Protocol):
    def resolve_command(
        self,
        experiment_id: ExperimentId,
        *,
        idempotency_key: str,
        command_hash: str,
    ) -> VersionedExperimentGovernance | None: ...

    def get(
        self, experiment_id: ExperimentId
    ) -> VersionedExperimentGovernance: ...

    def create(
        self,
        protocol: FrozenExperimentProtocol,
        *,
        idempotency_key: str,
    ) -> VersionedExperimentGovernance: ...

    def append_access(
        self,
        experiment_id: ExperimentId,
        *,
        expected_version: int,
        access_kind: str,
        access_record: ExperimentAccessRecord,
        idempotency_key: str,
        command_hash: str | None = None,
    ) -> VersionedExperimentGovernance: ...
