from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

import pytest

from market_regime_alpha.runtime.application import ActorType, CommandContext
from market_regime_alpha.runtime.application.command_failure import (
    CommandFailureDescriptor,
    RuntimeCommandFailureRecorder,
)
from market_regime_alpha.runtime.errors import StaleFenceError
from market_regime_alpha.runtime.ports import AttemptClaim, ReceiptRecord


_CLAIM = AttemptClaim(
    attempt_id=UUID("00000000-0000-0000-0000-000000000101"),
    run_id=UUID("00000000-0000-0000-0000-000000000102"),
    step_id=UUID("00000000-0000-0000-0000-000000000103"),
    step_key="ASSESS_ELIGIBILITY",
    attempt_no=1,
    fence_token=7,
    lease_owner="worker-1",
    lease_until=datetime(2026, 8, 29, 9, tzinfo=timezone.utc),
)
_CONTEXT = CommandContext(
    idempotency_key="failure-contract-1",
    actor_type=ActorType.WORKER,
    actor_id="worker-1",
    reason_code="RUNTIME_STEP",
)
_DESCRIPTOR = CommandFailureDescriptor(
    command_kind="ASSESS_ELIGIBILITY",
    scope_id="universe:policy",
    request_hash="a" * 64,
    error_class="COMMAND",
    error_code="ASSESS_ELIGIBILITY_REJECTED",
    aggregate_kind="SELECTION_COMMAND",
    failure_action="SELECTION_COMMAND_FAILED",
    rejection_command_kind="SELECTION_COMMAND_REJECTION",
    rejection_action="SELECTION_COMMAND_REJECTED",
    rejection_key_prefix="selection-command-rejection",
)


class _Finalization:
    def __init__(self, events: list[str], *, stale: bool = False) -> None:
        self._events = events
        self._stale = stale

    def lock_live(self, claim: AttemptClaim) -> None:
        assert claim == _CLAIM
        self._events.append("lock_live")
        if self._stale:
            raise StaleFenceError("STALE_FENCE")

    def succeed(self, claim: AttemptClaim, *, receipt_id: UUID, result_hash: str):
        raise AssertionError("failure recording cannot succeed a Runtime claim")

    def fail(
        self,
        claim: AttemptClaim,
        *,
        receipt_id: UUID,
        error_class: str,
        error_code: str,
    ):
        assert claim == _CLAIM
        assert error_class == "COMMAND"
        assert error_code == "ASSESS_ELIGIBILITY_REJECTED"
        self._events.append("fail_attempt")
        return "FAILED_TERMINAL", 2, 3


class _Receipts:
    def __init__(self, events: list[str]) -> None:
        self._events = events
        self.receipt_id = UUID("00000000-0000-0000-0000-000000000104")

    def start(self, **kwargs) -> ReceiptRecord:
        assert kwargs["command_kind"] == "ASSESS_ELIGIBILITY"
        assert kwargs["scope_id"] == "universe:policy"
        assert kwargs["idempotency_key"] == "failure-contract-1"
        self._events.append("start_receipt")
        return ReceiptRecord(
            receipt_id=self.receipt_id,
            status="PENDING",
            request_hash="a" * 64,
            result_aggregate_kind=None,
            result_aggregate_id=None,
            result_aggregate_version=None,
            result_hash=None,
            error_code=None,
            is_new=True,
        )

    def fail(self, **kwargs) -> None:
        assert kwargs["receipt_id"] == self.receipt_id
        assert kwargs["runtime_claim"] == _CLAIM
        self._events.append("fail_receipt")


class _Audit:
    def __init__(self, events: list[str]) -> None:
        self._events = events

    def append(self, **kwargs) -> None:
        assert kwargs["action"] == "SELECTION_COMMAND_FAILED"
        assert kwargs["reason_code"] == "ASSESS_ELIGIBILITY_REJECTED"
        assert kwargs["runtime_claim"] == _CLAIM
        self._events.append("append_audit")


class _FailureUow:
    def __init__(self, events: list[str], *, stale: bool = False) -> None:
        self.events = events
        self.receipts = _Receipts(events)
        self.audit = _Audit(events)
        self.runtime_finalization = _Finalization(events, stale=stale)

    def __enter__(self):
        self.events.append("enter")
        return self

    def __exit__(self, exception_type, exception, traceback) -> None:
        self.events.append("rollback" if exception is not None else "exit")

    def commit(self) -> None:
        self.events.append("commit")


def test_failure_contract_locks_before_writes_and_commits_one_short_uow() -> None:
    events: list[str] = []
    uow = _FailureUow(events)
    recorder = RuntimeCommandFailureRecorder(lambda: uow, id_factory=lambda: UUID(int=999))

    recorder.record(_DESCRIPTOR, context=_CONTEXT, runtime_claim=_CLAIM)

    assert events == [
        "enter",
        "lock_live",
        "start_receipt",
        "fail_receipt",
        "append_audit",
        "fail_attempt",
        "commit",
        "exit",
    ]


def test_failure_contract_rejects_stale_fence_before_any_failure_write() -> None:
    events: list[str] = []
    uow = _FailureUow(events, stale=True)
    recorder = RuntimeCommandFailureRecorder(lambda: uow, id_factory=lambda: UUID(int=999))

    with pytest.raises(StaleFenceError, match="STALE_FENCE"):
        recorder.record(_DESCRIPTOR, context=_CONTEXT, runtime_claim=_CLAIM)

    assert events == ["enter", "lock_live", "rollback"]
