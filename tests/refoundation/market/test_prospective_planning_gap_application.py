from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from market_regime_alpha.market.application import (
    ArchiveCommands,
    RecordProspectivePlanningGapRequest,
)
from market_regime_alpha.runtime.application import ActorType, CommandContext
from market_regime_alpha.runtime.ports import ReceiptRecord


class _Archives:
    def __init__(self, now: datetime) -> None:
        self.now = now
        self.inserted = None

    def database_now(self) -> datetime:
        return self.now

    def insert_prospective_planning_gap(self, gap) -> None:
        self.inserted = gap


class _Receipts:
    def __init__(self, receipt_id: UUID) -> None:
        self.receipt_id = receipt_id
        self.succeeded = None

    def start(self, **kwargs):
        return ReceiptRecord(
            receipt_id=self.receipt_id,
            status="PENDING",
            request_hash=kwargs["request_hash"],
            result_aggregate_kind=None,
            result_aggregate_id=None,
            result_aggregate_version=None,
            result_hash=None,
            error_code=None,
            is_new=True,
        )

    def succeed(self, **kwargs) -> None:
        self.succeeded = kwargs


class _Audit:
    def append(self, **kwargs) -> None:
        return None


class _RuntimeFinalization:
    def succeed(self, *args, **kwargs) -> None:
        raise AssertionError("test command has no Runtime claim")


class _Uow:
    def __init__(self, now: datetime, receipt_id: UUID) -> None:
        self.archives = _Archives(now)
        self.receipts = _Receipts(receipt_id)
        self.audit = _Audit()
        self.runtime_finalization = _RuntimeFinalization()
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, *args) -> None:
        return None

    def commit(self) -> None:
        self.committed = True


def test_planning_gap_uses_authoritative_uow_clock_and_is_audited() -> None:
    detected_at = datetime(2026, 9, 4, 2, 10, tzinfo=UTC)
    ids = iter(
        (
            UUID("38000000-0000-0000-0000-000000000001"),
            UUID("38000000-0000-0000-0000-000000000002"),
            UUID("38000000-0000-0000-0000-000000000003"),
        )
    )
    uow = _Uow(
        detected_at,
        UUID("38000000-0000-0000-0000-000000000099"),
    )
    commands = ArchiveCommands(  # type: ignore[arg-type]
        lambda: uow,
        id_factory=lambda: next(ids),
    )

    result = commands.record_prospective_planning_gap(
        RecordProspectivePlanningGapRequest(
            series_code="xshg_target_archive",
            expected_generation=1,
            predecessor_market_archive_id=None,
            target_definition_id=UUID(
                "38000000-0000-0000-0000-000000000010"
            ),
            target_version=1,
            target_definition_sha256="a" * 64,
            expected_decision_session_id=UUID(
                "38000000-0000-0000-0000-000000000011"
            ),
            reason_code="GENERATION_NOT_PREDECLARED",
        ),
        CommandContext(
            idempotency_key="prospective-gap:test",
            actor_type=ActorType.SYSTEM,
            actor_id="prospective-test",
            reason_code="RECORD_PROSPECTIVE_GAP",
        ),
    )

    assert result.gap.detected_at == detected_at
    assert uow.archives.inserted == result.gap
    assert uow.receipts.succeeded is not None
    assert uow.committed is True
