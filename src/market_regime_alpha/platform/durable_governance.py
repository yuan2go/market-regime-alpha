"""Domain-validating application services for persistent governance."""

from __future__ import annotations

from datetime import datetime
from hashlib import sha256
import json
from typing import Any

from market_regime_alpha.core.identity import ExperimentId, ModelId
from market_regime_alpha.platform.contracts import (
    EvidenceLevel,
    ModelDefinition,
    ModelLifecycleStatus,
)
from market_regime_alpha.platform.experiment_governance import (
    ExperimentGovernance,
    FrozenExperimentProtocol,
)
from market_regime_alpha.platform.model_registry import ModelRegistry
from market_regime_alpha.platform.repositories import (
    ExperimentGovernanceRepository,
    ModelRegistryRepository,
    VersionedExperimentGovernance,
    VersionedModelRegistration,
)


class PersistentModelRegistry:
    """Apply existing ModelRegistry rules before repository CAS writes."""

    def __init__(self, repository: ModelRegistryRepository) -> None:
        self._repository = repository

    def register(
        self, definition: ModelDefinition, *, idempotency_key: str
    ) -> VersionedModelRegistration:
        registration = ModelRegistry().register(definition)
        return self._repository.create(
            registration, idempotency_key=idempotency_key
        )

    def get(self, model_id: ModelId) -> VersionedModelRegistration:
        versioned = self._repository.get(model_id)
        ModelRegistry().restore(versioned.registration)
        return versioned

    def transition(
        self,
        model_id: ModelId,
        *,
        expected_version: int,
        idempotency_key: str,
        to_status: ModelLifecycleStatus,
        changed_at: datetime,
        reason: str,
        evidence_refs: tuple[str, ...] = (),
        evidence_level: EvidenceLevel | None = None,
        approval_ref: str | None = None,
    ) -> VersionedModelRegistration:
        command_hash = _command_hash(
            {
                "operation": "MODEL_TRANSITION",
                "model_id": str(model_id),
                "expected_version": expected_version,
                "to_status": to_status.value,
                "changed_at": changed_at.isoformat(),
                "reason": reason,
                "evidence_refs": list(evidence_refs),
                "evidence_level": (
                    evidence_level.value if evidence_level is not None else None
                ),
                "approval_ref": approval_ref,
            }
        )
        duplicate = self._repository.resolve_command(
            model_id,
            idempotency_key=idempotency_key,
            command_hash=command_hash,
        )
        if duplicate is not None:
            return duplicate
        current = self.get(model_id)
        registry = ModelRegistry()
        registry.restore(current.registration)
        updated = registry.transition(
            model_id,
            to_status=to_status,
            changed_at=changed_at,
            reason=reason,
            evidence_refs=evidence_refs,
            evidence_level=evidence_level,
            approval_ref=approval_ref,
        )
        return self._repository.compare_and_set(
            model_id,
            expected_version=expected_version,
            registration=updated,
            idempotency_key=idempotency_key,
            command_hash=command_hash,
        )


class PersistentExperimentGovernance:
    """Replay existing access-budget rules before append-only persistence."""

    def __init__(self, repository: ExperimentGovernanceRepository) -> None:
        self._repository = repository

    def register(
        self, protocol: FrozenExperimentProtocol, *, idempotency_key: str
    ) -> VersionedExperimentGovernance:
        ExperimentGovernance().register(protocol)
        return self._repository.create(
            protocol, idempotency_key=idempotency_key
        )

    def get(
        self, experiment_id: ExperimentId
    ) -> VersionedExperimentGovernance:
        versioned = self._repository.get(experiment_id)
        _restore_experiment_domain(versioned)
        return versioned

    def record_validation_access(
        self,
        experiment_id: ExperimentId,
        *,
        expected_version: int,
        idempotency_key: str,
    ) -> VersionedExperimentGovernance:
        command_hash = _command_hash(
            {
                "operation": "VALIDATION_ACCESS",
                "experiment_id": str(experiment_id),
                "expected_version": expected_version,
            }
        )
        duplicate = self._repository.resolve_command(
            experiment_id,
            idempotency_key=idempotency_key,
            command_hash=command_hash,
        )
        if duplicate is not None:
            return duplicate
        current = self.get(experiment_id)
        governance = _restore_experiment_domain(current)
        access = governance.record_validation_access(experiment_id)
        return self._repository.append_access(
            experiment_id,
            expected_version=expected_version,
            access_kind="VALIDATION",
            access_record=access,
            idempotency_key=idempotency_key,
            command_hash=command_hash,
        )

    def record_sealed_test_access(
        self,
        experiment_id: ExperimentId,
        *,
        expected_version: int,
        idempotency_key: str,
    ) -> VersionedExperimentGovernance:
        command_hash = _command_hash(
            {
                "operation": "SEALED_TEST_ACCESS",
                "experiment_id": str(experiment_id),
                "expected_version": expected_version,
            }
        )
        duplicate = self._repository.resolve_command(
            experiment_id,
            idempotency_key=idempotency_key,
            command_hash=command_hash,
        )
        if duplicate is not None:
            return duplicate
        current = self.get(experiment_id)
        governance = _restore_experiment_domain(current)
        access = governance.record_sealed_test_access(experiment_id)
        return self._repository.append_access(
            experiment_id,
            expected_version=expected_version,
            access_kind="SEALED_TEST",
            access_record=access,
            idempotency_key=idempotency_key,
            command_hash=command_hash,
        )


def _restore_experiment_domain(
    versioned: VersionedExperimentGovernance,
) -> ExperimentGovernance:
    governance = ExperimentGovernance()
    experiment_id = governance.register(versioned.protocol)
    for _ in range(versioned.access_record.validation_access_count):
        governance.record_validation_access(experiment_id)
    for _ in range(versioned.access_record.sealed_test_access_count):
        governance.record_sealed_test_access(experiment_id)
    if governance.access_record(experiment_id) != versioned.access_record:
        raise ValueError("experiment access history is not reconstructible")
    return governance


def _command_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return f"sha256:{sha256(canonical.encode('utf-8')).hexdigest()}"
