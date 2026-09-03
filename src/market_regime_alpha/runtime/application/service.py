"""Explicit Runtime commands and query boundary over one UoW per use case."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from enum import StrEnum
import re
from typing import Callable
from uuid import UUID, uuid4

from market_regime_alpha.runtime.domain import (
    RunSpec,
    ScheduleSpec,
    StepDependency,
    StepSpec,
    validate_step_dag,
)
from market_regime_alpha.runtime.errors import (
    RuntimeStateConflictError,
)
from market_regime_alpha.runtime.ports import (
    AttemptClaim,
    ReceiptRecord,
    RunTrace,
    RuntimeUnitOfWork,
    RuntimeUnitOfWorkProvider,
)
from market_regime_alpha.shared.hashing import canonical_json_sha256
from market_regime_alpha.shared.identity import ContentHash, IdempotencyKey


_CODE = re.compile(r"^[A-Z][A-Z0-9_]{0,99}$")


class ActorType(StrEnum):
    SYSTEM = "SYSTEM"
    OPERATOR = "OPERATOR"
    WORKER = "WORKER"


@dataclass(frozen=True, slots=True)
class CommandContext:
    idempotency_key: str
    actor_type: ActorType
    actor_id: str
    reason_code: str

    def __post_init__(self) -> None:
        IdempotencyKey(self.idempotency_key)
        if not self.actor_id:
            raise ValueError("actor_id is required")
        if not _CODE.fullmatch(self.reason_code):
            raise ValueError("reason_code has an invalid format")


@dataclass(frozen=True, slots=True)
class MutationResult:
    aggregate_kind: str
    aggregate_id: str
    aggregate_version: int
    result_hash: str
    receipt_id: UUID
    replayed: bool


class RuntimeApplication:
    """Run/Step/Attempt use cases; it is not a generic command bus."""

    def __init__(
        self,
        uow_provider: RuntimeUnitOfWorkProvider,
        *,
        id_factory: Callable[[], UUID] = uuid4,
    ) -> None:
        self._uow_provider = uow_provider
        self._id_factory = id_factory

    def create_schedule(
        self,
        schedule: ScheduleSpec,
        context: CommandContext,
    ) -> MutationResult:
        request_hash = canonical_json_sha256(schedule)
        result_hash = canonical_json_sha256(
            {"schedule_id": schedule.schedule_id, "revision": schedule.revision}
        )
        with self._uow_provider() as uow:
            receipt = uow.receipts.start(
                receipt_id=self._id_factory(),
                command_kind="CREATE_RUNTIME_SCHEDULE",
                scope_id=schedule.schedule_code,
                idempotency_key=context.idempotency_key,
                request_hash=request_hash,
            )
            if not receipt.is_new:
                return _replayed_result(receipt)
            uow.runtime.insert_schedule(schedule)
            uow.receipts.succeed(
                receipt_id=receipt.receipt_id,
                aggregate_kind="RUNTIME_SCHEDULE",
                aggregate_id=str(schedule.schedule_id),
                aggregate_version=schedule.revision,
                result_hash=result_hash,
            )
            uow.audit.append(
                audit_event_id=self._id_factory(),
                receipt_id=receipt.receipt_id,
                actor_type=context.actor_type.value,
                actor_id=context.actor_id,
                aggregate_kind="RUNTIME_SCHEDULE",
                aggregate_id=str(schedule.schedule_id),
                action="CREATE_RUNTIME_SCHEDULE",
                reason_code=context.reason_code,
                before_version=None,
                after_version=schedule.revision,
            )
            uow.commit()
            return MutationResult(
                aggregate_kind="RUNTIME_SCHEDULE",
                aggregate_id=str(schedule.schedule_id),
                aggregate_version=schedule.revision,
                result_hash=result_hash,
                receipt_id=receipt.receipt_id,
                replayed=False,
            )

    def schedule_run(
        self,
        run: RunSpec,
        steps: tuple[StepSpec, ...],
        dependencies: tuple[StepDependency, ...],
        context: CommandContext,
    ) -> MutationResult:
        validate_step_dag(steps, dependencies)
        request_hash = canonical_json_sha256(
            {"run": run, "steps": steps, "dependencies": dependencies}
        )
        result_hash = canonical_json_sha256(
            {"run_id": run.run_id, "step_keys": tuple(step.step_key for step in steps)}
        )
        planned_steps = tuple((self._id_factory(), step) for step in steps)
        with self._uow_provider() as uow:
            receipt = uow.receipts.start(
                receipt_id=self._id_factory(),
                command_kind="SCHEDULE_RUNTIME_RUN",
                scope_id=f"{run.schedule_id}:{run.fire_key}",
                idempotency_key=context.idempotency_key,
                request_hash=request_hash,
            )
            if not receipt.is_new:
                return _replayed_result(receipt)
            uow.runtime.insert_run(run, planned_steps, dependencies)
            uow.receipts.succeed(
                receipt_id=receipt.receipt_id,
                aggregate_kind="RUNTIME_RUN",
                aggregate_id=str(run.run_id),
                aggregate_version=1,
                result_hash=result_hash,
            )
            uow.audit.append(
                audit_event_id=self._id_factory(),
                receipt_id=receipt.receipt_id,
                actor_type=context.actor_type.value,
                actor_id=context.actor_id,
                aggregate_kind="RUNTIME_RUN",
                aggregate_id=str(run.run_id),
                action="SCHEDULE_RUNTIME_RUN",
                reason_code=context.reason_code,
                before_version=None,
                after_version=1,
            )
            uow.commit()
            return MutationResult(
                aggregate_kind="RUNTIME_RUN",
                aggregate_id=str(run.run_id),
                aggregate_version=1,
                result_hash=result_hash,
                receipt_id=receipt.receipt_id,
                replayed=False,
            )

    def start_run(self, run_id: UUID, context: CommandContext) -> MutationResult:
        request_hash = canonical_json_sha256({"run_id": run_id})
        with self._uow_provider() as uow:
            receipt = uow.receipts.start(
                receipt_id=self._id_factory(),
                command_kind="START_RUNTIME_RUN",
                scope_id=str(run_id),
                idempotency_key=context.idempotency_key,
                request_hash=request_hash,
            )
            if not receipt.is_new:
                return _replayed_result(receipt)
            version = uow.runtime.start_run(run_id)
            result_hash = canonical_json_sha256(
                {"run_id": run_id, "state": "RUNNING", "version": version}
            )
            uow.receipts.succeed(
                receipt_id=receipt.receipt_id,
                aggregate_kind="RUNTIME_RUN",
                aggregate_id=str(run_id),
                aggregate_version=version,
                result_hash=result_hash,
            )
            self._append_audit(
                uow,
                receipt,
                context,
                aggregate_kind="RUNTIME_RUN",
                aggregate_id=str(run_id),
                action="START_RUNTIME_RUN",
                before_version=version - 1,
                after_version=version,
            )
            uow.commit()
            return _result(receipt, "RUNTIME_RUN", str(run_id), version, result_hash)

    def claim_next(
        self,
        *,
        run_id: UUID | None = None,
        worker_id: str,
        lease_duration: timedelta,
        context: CommandContext,
    ) -> AttemptClaim | None:
        if not worker_id:
            raise ValueError("worker_id is required")
        request_hash = canonical_json_sha256(
            {
                "lease_duration": lease_duration,
                "run_id": run_id,
                "worker_id": worker_id,
            }
        )
        with self._uow_provider() as uow:
            receipt = uow.receipts.start(
                receipt_id=self._id_factory(),
                command_kind="CLAIM_RUNTIME_STEP",
                scope_id=(
                    "runtime-ready-queue"
                    if run_id is None
                    else f"runtime-run:{run_id}"
                ),
                idempotency_key=context.idempotency_key,
                request_hash=request_hash,
            )
            if not receipt.is_new:
                if receipt.result_aggregate_id is None:
                    raise RuntimeStateConflictError("claim receipt has no Attempt identity")
                return self._load_claim(UUID(receipt.result_aggregate_id))
            claim = uow.runtime.claim_next(
                attempt_id=self._id_factory(),
                run_id=run_id,
                worker_id=worker_id,
                lease_duration=lease_duration,
            )
            if claim is None:
                return None
            result_hash = canonical_json_sha256(claim)
            uow.receipts.succeed(
                receipt_id=receipt.receipt_id,
                aggregate_kind="RUNTIME_ATTEMPT",
                aggregate_id=str(claim.attempt_id),
                aggregate_version=claim.attempt_no,
                result_hash=result_hash,
                runtime_claim=claim,
            )
            self._append_audit(
                uow,
                receipt,
                context,
                aggregate_kind="RUNTIME_ATTEMPT",
                aggregate_id=str(claim.attempt_id),
                action="CLAIM_RUNTIME_STEP",
                before_version=claim.attempt_no - 1,
                after_version=claim.attempt_no,
                runtime_claim=claim,
            )
            uow.commit()
            return claim

    def start_attempt(
        self,
        claim: AttemptClaim,
        context: CommandContext,
    ) -> MutationResult:
        return self._mutate_claim(
            command_kind="START_RUNTIME_ATTEMPT",
            action="START_RUNTIME_ATTEMPT",
            claim=claim,
            context=context,
            request={"attempt_id": claim.attempt_id, "fence": claim.fence_token},
            mutation=lambda uow, _receipt: (
                uow.runtime.start_attempt(claim),
                canonical_json_sha256(
                    {"attempt_id": claim.attempt_id, "state": "RUNNING"}
                ),
            ),
        )

    def heartbeat_attempt(
        self,
        claim: AttemptClaim,
        *,
        lease_duration: timedelta,
        context: CommandContext,
    ) -> MutationResult:
        def heartbeat(uow: RuntimeUnitOfWork, _receipt: UUID) -> tuple[int, str]:
            lease_until = uow.runtime.heartbeat_attempt(claim, lease_duration)
            return claim.attempt_no, canonical_json_sha256(
                {"attempt_id": claim.attempt_id, "lease_until": lease_until}
            )

        return self._mutate_claim(
            command_kind="HEARTBEAT_RUNTIME_ATTEMPT",
            action="HEARTBEAT_RUNTIME_ATTEMPT",
            claim=claim,
            context=context,
            request={
                "attempt_id": claim.attempt_id,
                "fence": claim.fence_token,
                "lease_duration": lease_duration,
            },
            mutation=heartbeat,
        )

    def succeed_attempt(
        self,
        claim: AttemptClaim,
        *,
        result_hash: str,
        context: CommandContext,
    ) -> MutationResult:
        ContentHash(result_hash)

        def succeed(uow: RuntimeUnitOfWork, receipt_id: UUID) -> tuple[int, str]:
            step_version, _run_version = uow.runtime.succeed_attempt(
                claim,
                receipt_id=receipt_id,
                result_hash=result_hash,
            )
            return step_version, result_hash

        return self._mutate_claim(
            command_kind="SUCCEED_RUNTIME_ATTEMPT",
            action="SUCCEED_RUNTIME_ATTEMPT",
            claim=claim,
            context=context,
            request={
                "attempt_id": claim.attempt_id,
                "fence": claim.fence_token,
                "result_hash": result_hash,
            },
            mutation=succeed,
        )

    def fail_attempt(
        self,
        claim: AttemptClaim,
        *,
        error_class: str,
        error_code: str,
        context: CommandContext,
    ) -> MutationResult:
        if not _CODE.fullmatch(error_class) or not _CODE.fullmatch(error_code):
            raise ValueError("error class and code must use the closed code format")

        def fail(uow: RuntimeUnitOfWork, receipt_id: UUID) -> tuple[int, str]:
            outcome, step_version, _run_version = uow.runtime.fail_attempt(
                claim,
                receipt_id=receipt_id,
                error_class=error_class,
                error_code=error_code,
            )
            return step_version, canonical_json_sha256(
                {
                    "attempt_id": claim.attempt_id,
                    "error_code": error_code,
                    "outcome": outcome,
                }
            )

        return self._mutate_claim(
            command_kind="FAIL_RUNTIME_ATTEMPT",
            action="FAIL_RUNTIME_ATTEMPT",
            claim=claim,
            context=context,
            request={
                "attempt_id": claim.attempt_id,
                "fence": claim.fence_token,
                "error_class": error_class,
                "error_code": error_code,
            },
            mutation=fail,
        )

    def recover_expired(
        self,
        *,
        actor_id: str,
        reason_code: str,
    ) -> tuple[UUID, ...]:
        if not actor_id or not _CODE.fullmatch(reason_code):
            raise ValueError("recovery actor and reason are required")
        with self._uow_provider() as scan_uow:
            attempt_ids = scan_uow.runtime.expired_attempt_ids()
        recovered: list[UUID] = []
        for attempt_id in attempt_ids:
            request_hash = canonical_json_sha256(
                {"attempt_id": attempt_id, "reason_code": reason_code}
            )
            with self._uow_provider() as uow:
                receipt = uow.receipts.start(
                    receipt_id=self._id_factory(),
                    command_kind="RECOVER_RUNTIME_ATTEMPT",
                    scope_id=str(attempt_id),
                    idempotency_key=f"lease-expiry:{attempt_id}",
                    request_hash=request_hash,
                )
                if not receipt.is_new:
                    continue
                claim = uow.runtime.load_claim(attempt_id)
                decision = uow.runtime.recover_expired_attempt(
                    attempt_id,
                    receipt_id=receipt.receipt_id,
                )
                if decision is None:
                    continue
                result_hash = canonical_json_sha256(decision)
                uow.receipts.succeed(
                    receipt_id=receipt.receipt_id,
                    aggregate_kind="RUNTIME_ATTEMPT",
                    aggregate_id=str(attempt_id),
                    aggregate_version=decision.attempt_version,
                    result_hash=result_hash,
                    runtime_claim=claim,
                )
                uow.audit.append(
                    audit_event_id=self._id_factory(),
                    receipt_id=receipt.receipt_id,
                    actor_type=ActorType.SYSTEM.value,
                    actor_id=actor_id,
                    aggregate_kind="RUNTIME_ATTEMPT",
                    aggregate_id=str(attempt_id),
                    action="RECOVER_RUNTIME_ATTEMPT",
                    reason_code=reason_code,
                    before_version=decision.attempt_version,
                    after_version=decision.attempt_version,
                    runtime_claim=claim,
                )
                uow.commit()
                recovered.append(attempt_id)
        with self._uow_provider() as scan_uow:
            step_ids = scan_uow.runtime.deadline_expired_step_ids()
        for step_id in step_ids:
            request_hash = canonical_json_sha256(
                {"step_id": step_id, "reason_code": reason_code}
            )
            with self._uow_provider() as uow:
                receipt = uow.receipts.start(
                    receipt_id=self._id_factory(),
                    command_kind="EXPIRE_RUNTIME_STEP_DEADLINE",
                    scope_id=str(step_id),
                    idempotency_key=f"deadline-expiry:{step_id}",
                    request_hash=request_hash,
                )
                if not receipt.is_new:
                    continue
                decision = uow.runtime.expire_step_deadline(
                    step_id,
                    attempt_id=self._id_factory(),
                    receipt_id=receipt.receipt_id,
                    lease_owner=f"recovery:{actor_id}",
                )
                if decision is None:
                    continue
                claim = uow.runtime.load_claim(decision.attempt_id)
                result_hash = canonical_json_sha256(decision)
                uow.receipts.succeed(
                    receipt_id=receipt.receipt_id,
                    aggregate_kind="RUNTIME_ATTEMPT",
                    aggregate_id=str(decision.attempt_id),
                    aggregate_version=decision.attempt_version,
                    result_hash=result_hash,
                    runtime_claim=claim,
                )
                uow.audit.append(
                    audit_event_id=self._id_factory(),
                    receipt_id=receipt.receipt_id,
                    actor_type=ActorType.SYSTEM.value,
                    actor_id=actor_id,
                    aggregate_kind="RUNTIME_ATTEMPT",
                    aggregate_id=str(decision.attempt_id),
                    action="EXPIRE_RUNTIME_STEP_DEADLINE",
                    reason_code=reason_code,
                    before_version=None,
                    after_version=decision.attempt_version,
                    runtime_claim=claim,
                )
                uow.commit()
                recovered.append(decision.attempt_id)
        return tuple(recovered)

    def resume_waiting_step(
        self,
        *,
        run_id: UUID,
        step_id: UUID,
        resolution_code: str,
        context: CommandContext,
    ) -> MutationResult:
        if resolution_code != "EXTERNAL_EFFECT_PROVEN_ABSENT":
            raise ValueError(
                "resume may retry only after EXTERNAL_EFFECT_PROVEN_ABSENT; "
                "a committed or unknown effect requires a separate resolver"
            )
        request_hash = canonical_json_sha256(
            {"run_id": run_id, "step_id": step_id, "resolution_code": resolution_code}
        )
        with self._uow_provider() as uow:
            receipt = uow.receipts.start(
                receipt_id=self._id_factory(),
                command_kind="RESUME_RUNTIME_STEP",
                scope_id=str(step_id),
                idempotency_key=context.idempotency_key,
                request_hash=request_hash,
            )
            if not receipt.is_new:
                return _replayed_result(receipt)
            step_version, run_version = uow.runtime.resume_waiting_step(
                run_id=run_id,
                step_id=step_id,
                resolution_code=resolution_code,
            )
            result_hash = canonical_json_sha256(
                {
                    "run_id": run_id,
                    "run_version": run_version,
                    "step_id": step_id,
                    "step_version": step_version,
                    "state": "READY",
                }
            )
            uow.receipts.succeed(
                receipt_id=receipt.receipt_id,
                aggregate_kind="RUNTIME_STEP",
                aggregate_id=str(step_id),
                aggregate_version=step_version,
                result_hash=result_hash,
            )
            self._append_audit(
                uow,
                receipt,
                context,
                aggregate_kind="RUNTIME_STEP",
                aggregate_id=str(step_id),
                action="RESUME_RUNTIME_STEP",
                before_version=step_version - 1,
                after_version=step_version,
            )
            uow.commit()
            return _result(receipt, "RUNTIME_STEP", str(step_id), step_version, result_hash)

    def inspect_run(self, run_id: UUID) -> RunTrace:
        with self._uow_provider() as uow:
            return uow.runtime.inspect_run(run_id)

    def _mutate_claim(
        self,
        *,
        command_kind: str,
        action: str,
        claim: AttemptClaim,
        context: CommandContext,
        request: object,
        mutation: Callable[[RuntimeUnitOfWork, UUID], tuple[int, str]],
    ) -> MutationResult:
        request_hash = canonical_json_sha256(request)
        with self._uow_provider() as uow:
            receipt = uow.receipts.start(
                receipt_id=self._id_factory(),
                command_kind=command_kind,
                scope_id=str(claim.attempt_id),
                idempotency_key=context.idempotency_key,
                request_hash=request_hash,
            )
            if not receipt.is_new:
                return _replayed_result(receipt)
            aggregate_version, result_hash = mutation(uow, receipt.receipt_id)
            uow.receipts.succeed(
                receipt_id=receipt.receipt_id,
                aggregate_kind="RUNTIME_STEP",
                aggregate_id=str(claim.step_id),
                aggregate_version=aggregate_version,
                result_hash=result_hash,
                runtime_claim=claim,
            )
            self._append_audit(
                uow,
                receipt,
                context,
                aggregate_kind="RUNTIME_STEP",
                aggregate_id=str(claim.step_id),
                action=action,
                before_version=max(0, aggregate_version - 1),
                after_version=aggregate_version,
                runtime_claim=claim,
            )
            uow.commit()
            return _result(
                receipt,
                "RUNTIME_STEP",
                str(claim.step_id),
                aggregate_version,
                result_hash,
            )

    def _append_audit(
        self,
        uow: RuntimeUnitOfWork,
        receipt: ReceiptRecord,
        context: CommandContext,
        *,
        aggregate_kind: str,
        aggregate_id: str,
        action: str,
        before_version: int | None,
        after_version: int | None,
        runtime_claim: AttemptClaim | None = None,
    ) -> None:
        uow.audit.append(
            audit_event_id=self._id_factory(),
            receipt_id=receipt.receipt_id,
            actor_type=context.actor_type.value,
            actor_id=context.actor_id,
            aggregate_kind=aggregate_kind,
            aggregate_id=aggregate_id,
            action=action,
            reason_code=context.reason_code,
            before_version=before_version,
            after_version=after_version,
            runtime_claim=runtime_claim,
        )

    def _load_claim(self, attempt_id: UUID) -> AttemptClaim:
        with self._uow_provider() as uow:
            return uow.runtime.load_claim(attempt_id)


def _replayed_result(receipt: ReceiptRecord) -> MutationResult:
    if (
        receipt.status != "SUCCEEDED"
        or receipt.result_aggregate_kind is None
        or receipt.result_aggregate_id is None
        or receipt.result_aggregate_version is None
        or receipt.result_hash is None
    ):
        raise RuntimeStateConflictError(
            f"terminal receipt {receipt.receipt_id} lacks a committed result"
        )
    return MutationResult(
        aggregate_kind=receipt.result_aggregate_kind,
        aggregate_id=receipt.result_aggregate_id,
        aggregate_version=receipt.result_aggregate_version,
        result_hash=receipt.result_hash,
        receipt_id=receipt.receipt_id,
        replayed=True,
    )


def _result(
    receipt: ReceiptRecord,
    aggregate_kind: str,
    aggregate_id: str,
    aggregate_version: int,
    result_hash: str,
) -> MutationResult:
    return MutationResult(
        aggregate_kind=aggregate_kind,
        aggregate_id=aggregate_id,
        aggregate_version=aggregate_version,
        result_hash=result_hash,
        receipt_id=receipt.receipt_id,
        replayed=False,
    )


__all__ = [
    "ActorType",
    "CommandContext",
    "MutationResult",
    "RuntimeApplication",
]
