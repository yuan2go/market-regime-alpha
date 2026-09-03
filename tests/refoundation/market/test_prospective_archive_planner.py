from __future__ import annotations

from datetime import UTC, date, datetime, time
from uuid import UUID

import pytest

from market_regime_alpha.market.application import (
    ArchiveOperatorManifest,
    ProspectiveArchiveInstrument,
    build_target_aligned_prospective_manifest,
)
from market_regime_alpha.market.domain import (
    ProspectiveArchiveScheduleSlot,
    ProspectiveArchiveSession,
    TargetArchiveCheckpoint,
    derive_target_archive_sessions,
)
from market_regime_alpha.market.ports import TargetArchiveContract


def _sessions() -> tuple[ProspectiveArchiveSession, ...]:
    values = (
        (1, date(2026, 9, 4)),
        (2, date(2026, 9, 7)),
        (3, date(2026, 9, 8)),
    )
    return tuple(
        ProspectiveArchiveSession(
            session_id=UUID(f"18000000-0000-0000-0000-{ordinal:012d}"),
            exchange="XSHG",
            session_date=session_date,
            open_at=datetime.combine(session_date, time(1, 30), tzinfo=UTC),
            close_at=datetime.combine(session_date, time(7), tzinfo=UTC),
        )
        for ordinal, session_date in values
    )


def _contract() -> TargetArchiveContract:
    target_id = UUID("18000000-0000-0000-0000-000000000100")
    return TargetArchiveContract(
        target_definition_id=target_id,
        version=1,
        content_sha256="a" * 64,
        checkpoints=(
            TargetArchiveCheckpoint(
                UUID("18000000-0000-0000-0000-000000000101"),
                1,
                "DECISION_REFERENCE",
                0,
                time(14, 55),
                "Asia/Shanghai",
            ),
            TargetArchiveCheckpoint(
                UUID("18000000-0000-0000-0000-000000000102"),
                2,
                "OUTCOME_OBSERVATION",
                1,
                time(10, 30),
                "Asia/Shanghai",
            ),
        ),
    )


def _manifest(*, planned_not_before: datetime) -> ArchiveOperatorManifest:
    sessions = _sessions()
    contract = _contract()
    resolved = derive_target_archive_sessions(
        exchange="XSHG",
        decision_session_id=sessions[0].session_id,
        sessions=sessions,
        checkpoints=contract.checkpoints,
        later_verification_session_offset=2,
    )
    return build_target_aligned_prospective_manifest(
        provider_product_id=UUID("18000000-0000-0000-0000-000000000110"),
        code_artifact_id=UUID("18000000-0000-0000-0000-000000000111"),
        config_artifact_id=UUID("18000000-0000-0000-0000-000000000112"),
        contract=contract,
        resolved_sessions=resolved,
        instruments=(
            ProspectiveArchiveInstrument(
                UUID("18000000-0000-0000-0000-000000000113"),
                UUID("18000000-0000-0000-0000-000000000114"),
                "sh.600000",
            ),
        ),
        series_code="xshg_target_archive",
        generation=1,
        predecessor_market_archive_id=None,
        planned_not_before=planned_not_before,
        provenance_sha256="b" * 64,
    )


def test_permanent_target_aligned_planner_is_stable_and_wp_neutral() -> None:
    first = _manifest(planned_not_before=datetime(2026, 9, 3, tzinfo=UTC))
    second = _manifest(planned_not_before=datetime(2026, 9, 3, tzinfo=UTC))

    generation = first.start_request.prospective_generation
    assert generation is not None
    assert first == second
    assert len(first.slices) == 9
    assert {item.slot for item in generation.schedules} == set(
        ProspectiveArchiveScheduleSlot
    )
    assert first.start_request.archive_code == "prospective_xshg_target_archive_g0001"
    assert "wp17" not in first.to_json().lower()
    assert "wp18" not in first.to_json().lower()
    assert ArchiveOperatorManifest.from_json(first.to_json()) == first


def test_permanent_planner_rejects_backdated_generation() -> None:
    with pytest.raises(ValueError, match="cannot backdate"):
        _manifest(planned_not_before=datetime(2026, 9, 4, 6, 50, 1, tzinfo=UTC))
