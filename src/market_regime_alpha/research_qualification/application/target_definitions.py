"""TargetDefinition registration over its independent narrow UoW."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable
from uuid import UUID

from market_regime_alpha.research_qualification.application._command_support import (
    replay_concurrent_success,
    terminal_failure_boundary,
)
from market_regime_alpha.research_qualification.domain.model import ArtifactBinding
from market_regime_alpha.research_qualification.domain.targets import TargetDefinition
from market_regime_alpha.research_qualification.ports.target_repository import (
    TargetDefinitionRecord,
)
from market_regime_alpha.research_qualification.ports.target_uow import (
    TargetUnitOfWork,
    TargetUnitOfWorkProvider,
)
from market_regime_alpha.runtime.application import (
    CommandContext,
    RuntimeCommandFailureRecorder,
)
from market_regime_alpha.runtime.errors import ArtifactIntegrityError
from market_regime_alpha.runtime.ports import AttemptClaim, ReceiptRecord
from market_regime_alpha.shared.hashing import canonical_json_sha256


@dataclass(frozen=True, slots=True)
class TargetRegistrationResult:
    target_definition_id: UUID
    target_code: str
    version: int
    definition_sha256: str
    checkpoint_count: int
    checkpoint_roster_sha256: str
    metric_count: int
    metric_roster_sha256: str
    dependency_count: int
    dependency_roster_sha256: str
    result_hash: str
    receipt_id: UUID
    replayed: bool


class TargetDefinitionCommands:
    """Own the one complete immutable Target registration command."""

    def __init__(
        self,
        uow_provider: TargetUnitOfWorkProvider,
        *,
        id_factory: Callable[[], UUID],
    ) -> None:
        self._uow_provider = uow_provider
        self._id_factory = id_factory
        self._failure_recorder = RuntimeCommandFailureRecorder(
            uow_provider,
            id_factory=id_factory,
        )

    @replay_concurrent_success
    def register(
        self,
        definition: TargetDefinition,
        context: CommandContext,
        *,
        runtime_claim: AttemptClaim | None = None,
    ) -> TargetRegistrationResult:
        request_hash = canonical_json_sha256(definition)
        scope_id = f"{definition.target_code}:{definition.version}"
        with (
            terminal_failure_boundary(
                self._failure_recorder,
                operation="REGISTER_TARGET_DEFINITION",
                scope_id=scope_id,
                request_hash=request_hash,
                error_class="COMMAND",
                error_code="REGISTER_TARGET_DEFINITION_REJECTED",
                context=context,
                runtime_claim=runtime_claim,
            ),
            self._uow_provider() as uow,
        ):
            if runtime_claim is not None:
                uow.runtime_finalization.lock_live(runtime_claim)
            receipt = uow.receipts.start(
                receipt_id=self._id_factory(),
                command_kind="REGISTER_TARGET_DEFINITION",
                scope_id=scope_id,
                idempotency_key=context.idempotency_key,
                request_hash=request_hash,
            )
            if not receipt.is_new:
                result = _replay_target(uow, receipt)
                if runtime_claim is not None:
                    uow.runtime_finalization.succeed(
                        runtime_claim,
                        receipt_id=receipt.receipt_id,
                        result_hash=result.result_hash,
                    )
                    uow.commit()
                return result

            uow.target_definitions.lock_registration_identity(
                definition.target_code,
                definition.version,
            )
            for binding in _artifact_bindings(definition):
                uow.target_artifacts.require_exact(binding, lock=True)
            record = uow.target_definitions.insert_target_definition(
                definition,
                registration_request_identity=context.idempotency_key,
                registration_request_sha256=request_hash,
                actor_type=context.actor_type.value,
                actor_id=context.actor_id,
            )
            reconciliation = uow.target_definitions.reconcile(
                definition.target_definition_id,
                lock=True,
            )
            if not reconciliation.matched:
                raise ArtifactIntegrityError(
                    "Target Definition relational closure did not reconcile"
                )
            result_hash = _target_result_hash(record)
            uow.receipts.succeed(
                receipt_id=receipt.receipt_id,
                aggregate_kind="TARGET_DEFINITION",
                aggregate_id=str(record.target_definition_id),
                aggregate_version=record.version,
                result_hash=result_hash,
                runtime_claim=runtime_claim,
            )
            uow.audit.append(
                audit_event_id=self._id_factory(),
                receipt_id=receipt.receipt_id,
                actor_type=context.actor_type.value,
                actor_id=context.actor_id,
                aggregate_kind="TARGET_DEFINITION",
                aggregate_id=str(record.target_definition_id),
                action="REGISTER_TARGET_DEFINITION",
                reason_code=context.reason_code,
                before_version=None,
                after_version=record.version,
                runtime_claim=runtime_claim,
            )
            if runtime_claim is not None:
                uow.runtime_finalization.succeed(
                    runtime_claim,
                    receipt_id=receipt.receipt_id,
                    result_hash=result_hash,
                )
            uow.commit()
            return _target_result(
                record,
                result_hash=result_hash,
                receipt_id=receipt.receipt_id,
                replayed=False,
            )


def _artifact_bindings(definition: TargetDefinition) -> tuple[ArtifactBinding, ...]:
    by_identity: dict[UUID, ArtifactBinding] = {}
    algorithms = (definition.algorithm, *(item.algorithm for item in definition.metrics))
    for algorithm in algorithms:
        for binding in (algorithm.code_artifact, algorithm.config_artifact):
            existing = by_identity.get(binding.artifact_id)
            if existing is not None and existing != binding:
                raise ArtifactIntegrityError(
                    "one Target Artifact identity has conflicting immutable bindings"
                )
            by_identity[binding.artifact_id] = binding
    return tuple(by_identity[key] for key in sorted(by_identity, key=str))


def _replay_target(
    uow: TargetUnitOfWork,
    receipt: ReceiptRecord,
) -> TargetRegistrationResult:
    if receipt.status != "SUCCEEDED":
        from market_regime_alpha.research_qualification.application._results import (
            ensure_replay_succeeded,
        )

        ensure_replay_succeeded(receipt)
    if (
        receipt.result_aggregate_kind != "TARGET_DEFINITION"
        or receipt.result_aggregate_id is None
        or receipt.result_aggregate_version is None
        or receipt.result_hash is None
    ):
        raise ArtifactIntegrityError("Target receipt has no complete result")
    try:
        target_id = UUID(receipt.result_aggregate_id)
    except ValueError as exc:
        raise ArtifactIntegrityError("Target receipt identity is invalid") from exc
    record = uow.target_definitions.target_record(target_id, lock=False)
    reconciliation = uow.target_definitions.reconcile(target_id, lock=False)
    result_hash = _target_result_hash(record)
    if (
        not reconciliation.matched
        or record.version != receipt.result_aggregate_version
        or result_hash != receipt.result_hash
    ):
        raise ArtifactIntegrityError("Target receipt and Authority do not reconcile")
    return _target_result(
        record,
        result_hash=result_hash,
        receipt_id=receipt.receipt_id,
        replayed=True,
    )


def _target_result_hash(record: TargetDefinitionRecord) -> str:
    return canonical_json_sha256(record)


def _target_result(
    record: TargetDefinitionRecord,
    *,
    result_hash: str,
    receipt_id: UUID,
    replayed: bool,
) -> TargetRegistrationResult:
    return TargetRegistrationResult(
        target_definition_id=record.target_definition_id,
        target_code=record.target_code,
        version=record.version,
        definition_sha256=record.content_sha256,
        checkpoint_count=record.checkpoint_count,
        checkpoint_roster_sha256=record.checkpoint_roster_sha256,
        metric_count=record.metric_count,
        metric_roster_sha256=record.metric_roster_sha256,
        dependency_count=record.dependency_count,
        dependency_roster_sha256=record.dependency_roster_sha256,
        result_hash=result_hash,
        receipt_id=receipt_id,
        replayed=replayed,
    )


__all__ = ["TargetDefinitionCommands", "TargetRegistrationResult"]
