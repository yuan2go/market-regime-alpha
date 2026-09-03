from __future__ import annotations

from datetime import UTC, date, datetime, time
from uuid import UUID

import pytest

from market_regime_alpha.market.domain import (
    ProspectiveArchiveDueState,
    ProspectiveArchiveGenerationPlan,
    ProspectiveArchiveMemberPlan,
    ProspectiveArchiveScheduleSlot,
    ProspectiveArchiveSession,
    ProspectiveArchiveSliceSchedulePlan,
    ProspectiveArchiveTerminalState,
    TargetArchiveCheckpoint,
    derive_target_archive_sessions,
    target_aligned_capture_windows,
)


D = ProspectiveArchiveSession(
    session_id=UUID("18000000-0000-0000-0000-000000000001"),
    exchange="XSHG",
    session_date=date(2026, 9, 4),
    open_at=datetime(2026, 9, 4, 1, 30, tzinfo=UTC),
    close_at=datetime(2026, 9, 4, 7, 0, tzinfo=UTC),
)
MONDAY = ProspectiveArchiveSession(
    session_id=UUID("18000000-0000-0000-0000-000000000002"),
    exchange="XSHG",
    session_date=date(2026, 9, 7),
    open_at=datetime(2026, 9, 7, 1, 30, tzinfo=UTC),
    close_at=datetime(2026, 9, 7, 7, 0, tzinfo=UTC),
)
LATER = ProspectiveArchiveSession(
    session_id=UUID("18000000-0000-0000-0000-000000000003"),
    exchange="XSHG",
    session_date=date(2026, 9, 14),
    open_at=datetime(2026, 9, 14, 1, 30, tzinfo=UTC),
    close_at=datetime(2026, 9, 14, 7, 0, tzinfo=UTC),
)


def _checkpoint(*, offset: int, role: str, local_time: time) -> TargetArchiveCheckpoint:
    return TargetArchiveCheckpoint(
        target_checkpoint_id=UUID(f"18000000-0000-0000-0000-{offset + 10:012d}"),
        ordinal=offset + 1,
        checkpoint_role=role,
        session_offset=offset,
        local_time=local_time,
        timezone_name="Asia/Shanghai",
    )


def test_friday_target_resolves_next_actual_session_not_calendar_day() -> None:
    result = derive_target_archive_sessions(
        exchange="XSHG",
        decision_session_id=D.session_id,
        sessions=(D, MONDAY, LATER),
        checkpoints=(
            _checkpoint(offset=0, role="DECISION_REFERENCE", local_time=time(14, 55)),
            _checkpoint(offset=1, role="OUTCOME_OBSERVATION", local_time=time(10, 30)),
        ),
        later_verification_session_offset=2,
    )

    assert result.decision.session_date == date(2026, 9, 4)
    assert result.outcome.session_date == date(2026, 9, 7)
    assert result.later_verification.session_date == date(2026, 9, 14)
    assert result.reference_at == datetime(2026, 9, 4, 6, 55, tzinfo=UTC)
    assert result.outcome_at == datetime(2026, 9, 7, 2, 30, tzinfo=UTC)

    windows = target_aligned_capture_windows(result)
    by_slot = {item.slot: item for item in windows}
    assert len(windows) == 9
    assert by_slot[ProspectiveArchiveScheduleSlot.DECISION_NEAR].window_start == (
        result.reference_at
    )
    assert by_slot[ProspectiveArchiveScheduleSlot.OUTCOME_PATH].window_start == (
        result.outcome_at
    )
    assert by_slot[ProspectiveArchiveScheduleSlot.OUTCOME_PATH].session_id == (
        MONDAY.session_id
    )


def test_calendar_gap_or_wrong_exchange_fails_closed() -> None:
    with pytest.raises(ValueError, match="complete authoritative session roster"):
        derive_target_archive_sessions(
            exchange="XSHG",
            decision_session_id=D.session_id,
            sessions=(D, MONDAY),
            checkpoints=(
                _checkpoint(offset=0, role="DECISION_REFERENCE", local_time=time(14, 55)),
                _checkpoint(offset=1, role="OUTCOME_OBSERVATION", local_time=time(10, 30)),
            ),
            later_verification_session_offset=2,
        )
    with pytest.raises(ValueError, match="exchange"):
        derive_target_archive_sessions(
            exchange="XSHE",
            decision_session_id=D.session_id,
            sessions=(D, MONDAY, LATER),
            checkpoints=(
                _checkpoint(offset=0, role="DECISION_REFERENCE", local_time=time(14, 55)),
                _checkpoint(offset=1, role="OUTCOME_OBSERVATION", local_time=time(10, 30)),
            ),
            later_verification_session_offset=2,
        )


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        (datetime(2026, 9, 4, 6, 49, tzinfo=UTC), ProspectiveArchiveDueState.NOT_DUE),
        (datetime(2026, 9, 4, 6, 52, tzinfo=UTC), ProspectiveArchiveDueState.DUE),
        (datetime(2026, 9, 4, 6, 57, tzinfo=UTC), ProspectiveArchiveDueState.OVERDUE),
    ],
)
def test_due_state_is_closed_by_database_time(now: datetime, expected: ProspectiveArchiveDueState) -> None:
    assert ProspectiveArchiveDueState.at(
        now=now,
        window_start=datetime(2026, 9, 4, 6, 50, tzinfo=UTC),
        window_end=datetime(2026, 9, 4, 6, 56, tzinfo=UTC),
    ) is expected


def test_wp18_closed_vocabularies_include_target_and_missed_semantics() -> None:
    assert ProspectiveArchiveScheduleSlot.OUTCOME_10_30.value == "OUTCOME_10_30"
    assert ProspectiveArchiveScheduleSlot.REVISION_VERIFICATION.value == "REVISION_VERIFICATION"
    assert ProspectiveArchiveTerminalState.CAPTURED_ON_TIME.value == "CAPTURED_ON_TIME"
    assert ProspectiveArchiveTerminalState.MISSED.value == "MISSED"
    assert ProspectiveArchiveTerminalState.RESOURCE_STOP.value == "RESOURCE_STOP"


def test_generation_requires_complete_target_al_aligned_schedule_per_member() -> None:
    member = ProspectiveArchiveMemberPlan(
        instrument_id=UUID("18000000-0000-0000-0000-000000000090"),
        instrument_identifier_id=UUID("18000000-0000-0000-0000-000000000091"),
        ordinal=1,
    )
    schedules = tuple(
        ProspectiveArchiveSliceSchedulePlan(
            market_archive_slice_id=UUID(
                f"18000000-0000-0000-0000-{100 + ordinal:012d}"
            ),
            instrument_id=member.instrument_id,
            ordinal=ordinal,
            slot=slot,
            trading_session_id=(
                D.session_id
                if slot.value in {"PRE_DECISION", "DECISION_NEAR", "POST_CLOSE", "EVENING_REVISION"}
                else MONDAY.session_id
                if slot is not ProspectiveArchiveScheduleSlot.REVISION_VERIFICATION
                else LATER.session_id
            ),
            target_checkpoint_id=UUID("18000000-0000-0000-0000-000000000010"),
            comparison_ordinal=ordinal,
        )
        for ordinal, slot in enumerate(ProspectiveArchiveScheduleSlot, start=1)
    )
    plan = ProspectiveArchiveGenerationPlan(
        market_archive_id=UUID("18000000-0000-0000-0000-000000000080"),
        series_code="wp18_xshg_target_archive",
        generation=1,
        predecessor_market_archive_id=None,
        exchange="XSHG",
        target_definition_id=UUID("18000000-0000-0000-0000-000000000081"),
        target_version=1,
        target_definition_sha256="a" * 64,
        reference_checkpoint_id=UUID("18000000-0000-0000-0000-000000000010"),
        outcome_checkpoint_id=UUID("18000000-0000-0000-0000-000000000011"),
        decision_session_id=D.session_id,
        outcome_session_id=MONDAY.session_id,
        later_verification_session_id=LATER.session_id,
        members=(member,),
        schedules=schedules,
        provenance_sha256="b" * 64,
    )
    assert len(plan.schedules) == 9

    with pytest.raises(ValueError, match="schedule is incomplete"):
        ProspectiveArchiveGenerationPlan(
            **{
                name: getattr(plan, name)
                for name in plan.__dataclass_fields__
                if name not in {
                    "schedules",
                    "member_roster_sha256",
                    "schedule_roster_sha256",
                    "content_sha256",
                }
            },
            schedules=schedules[:-1],
        )
