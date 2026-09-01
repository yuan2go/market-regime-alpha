"""FreezeResearchPartition over the independent Partition UoW."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, cast
from uuid import UUID

from market_regime_alpha.research_qualification.application._command_support import (
    replay_concurrent_success,
    retry_transient_transaction,
    terminal_failure_boundary,
)
from market_regime_alpha.research_qualification.application._results import ensure_replay_succeeded
from market_regime_alpha.research_qualification.domain.partition import ResearchPartitionPlan
from market_regime_alpha.research_qualification.domain.research_vocabulary import PartitionPurpose
from market_regime_alpha.research_qualification.ports.partition_uow import (
    PartitionUnitOfWorkProvider,
    ResearchPartitionRecord,
)
from market_regime_alpha.runtime.application import CommandContext, RuntimeCommandFailureRecorder
from market_regime_alpha.runtime.errors import ArtifactIntegrityError
from market_regime_alpha.runtime.ports import AttemptClaim, CommandFailureUnitOfWorkProvider
from market_regime_alpha.shared.hashing import canonical_json_sha256


@dataclass(frozen=True, slots=True)
class PartitionFreezeResult:
    research_partition_id: UUID
    member_count: int
    member_roster_sha256: str
    content_sha256: str
    receipt_id: UUID
    replayed: bool


class ResearchPartitionCommands:
    def __init__(self, uow_provider: PartitionUnitOfWorkProvider, *, id_factory: Callable[[], UUID]) -> None:
        self._uow_provider = uow_provider
        self._id_factory = id_factory
        self._failure_recorder = RuntimeCommandFailureRecorder(
            cast(CommandFailureUnitOfWorkProvider, uow_provider), id_factory=id_factory
        )

    @retry_transient_transaction
    @replay_concurrent_success
    def freeze(
        self,
        plan: ResearchPartitionPlan,
        context: CommandContext,
        *,
        runtime_claim: AttemptClaim | None = None,
    ) -> PartitionFreezeResult:
        request_hash = canonical_json_sha256(plan)
        with (
            terminal_failure_boundary(
                self._failure_recorder,
                operation="FREEZE_RESEARCH_PARTITION",
                scope_id=plan.partition_code,
                request_hash=request_hash,
                error_class="COMMAND",
                error_code="FREEZE_RESEARCH_PARTITION_REJECTED",
                context=context,
                runtime_claim=runtime_claim,
            ),
            self._uow_provider() as uow,
        ):
            if runtime_claim is not None:
                uow.runtime_finalization.lock_live(runtime_claim)
            receipt = uow.receipts.start(
                receipt_id=self._id_factory(),
                command_kind="FREEZE_RESEARCH_PARTITION",
                scope_id=plan.partition_code,
                idempotency_key=context.idempotency_key,
                request_hash=request_hash,
            )
            if not receipt.is_new:
                ensure_replay_succeeded(receipt)
                if receipt.result_aggregate_id is None or receipt.result_hash is None:
                    raise ArtifactIntegrityError("Partition receipt is incomplete")
                record = uow.partitions.record(UUID(receipt.result_aggregate_id), lock=False)
                if not uow.partitions.reconcile(record.research_partition_id):
                    raise ArtifactIntegrityError("Partition replay does not reconcile")
                result = _result(record, receipt.receipt_id, receipt.result_hash, True)
                if runtime_claim is not None:
                    uow.runtime_finalization.succeed(runtime_claim, receipt_id=receipt.receipt_id, result_hash=receipt.result_hash)
                    uow.commit()
                return result
            uow.partitions.lock_identity(plan.partition_code)
            uow.artifacts.require_exact(plan.code_artifact, lock=True)
            uow.artifacts.require_exact(plan.config_artifact, lock=True)
            bounds = uow.inputs.lock_target_and_calendar(plan)
            members = uow.inputs.derive_complete_roster(plan)
            if plan.purpose is PartitionPurpose.PROSPECTIVE:
                uow.inputs.require_canonical_live_clock(members)
            record = uow.partitions.insert(
                plan,
                bounds,
                members,
                request_identity=context.idempotency_key,
                request_sha256=request_hash,
            )
            uow.partitions.reconcile(record.research_partition_id)
            result_hash = canonical_json_sha256(record)
            uow.receipts.succeed(
                receipt_id=receipt.receipt_id,
                aggregate_kind="RESEARCH_PARTITION",
                aggregate_id=str(record.research_partition_id),
                aggregate_version=1,
                result_hash=result_hash,
                runtime_claim=runtime_claim,
            )
            uow.audit.append(
                audit_event_id=self._id_factory(), receipt_id=receipt.receipt_id,
                actor_type=context.actor_type.value, actor_id=context.actor_id,
                aggregate_kind="RESEARCH_PARTITION", aggregate_id=str(record.research_partition_id),
                action="FREEZE_RESEARCH_PARTITION", reason_code=context.reason_code,
                before_version=None, after_version=1, runtime_claim=runtime_claim,
            )
            if runtime_claim is not None:
                uow.runtime_finalization.succeed(runtime_claim, receipt_id=receipt.receipt_id, result_hash=result_hash)
            uow.commit()
            return _result(record, receipt.receipt_id, result_hash, False)


def _result(record: ResearchPartitionRecord, receipt_id: UUID, result_hash: str, replayed: bool) -> PartitionFreezeResult:
    if canonical_json_sha256(record) != result_hash:
        raise ArtifactIntegrityError("Partition receipt and Authority differ")
    return PartitionFreezeResult(
        research_partition_id=record.research_partition_id,
        member_count=record.member_count,
        member_roster_sha256=record.member_roster_sha256,
        content_sha256=record.content_sha256,
        receipt_id=receipt_id,
        replayed=replayed,
    )


__all__ = ["PartitionFreezeResult", "ResearchPartitionCommands"]
