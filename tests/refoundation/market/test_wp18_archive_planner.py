from __future__ import annotations

from datetime import UTC, date, datetime, time
from uuid import UUID

from market_regime_alpha.interfaces.archive import ArchiveOperatorManifest
from market_regime_alpha.interfaces.wp18_archive import (
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


def _sessions():
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
                1, "DECISION_REFERENCE", 0, time(14, 55), "Asia/Shanghai",
            ),
            TargetArchiveCheckpoint(
                UUID("18000000-0000-0000-0000-000000000102"),
                2, "OUTCOME_OBSERVATION", 1, time(10, 30), "Asia/Shanghai",
            ),
        ),
    )


def test_target_aligned_generation_round_trips_complete_manifest() -> None:
    sessions = _sessions()
    contract = _contract()
    resolved = derive_target_archive_sessions(
        exchange="XSHG",
        decision_session_id=sessions[0].session_id,
        sessions=sessions,
        checkpoints=contract.checkpoints,
        later_verification_session_offset=2,
    )
    manifest = build_target_aligned_prospective_manifest(
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
        series_code="wp18_xshg_target",
        generation=1,
        predecessor_market_archive_id=None,
        planned_not_before=datetime(2026, 9, 3, tzinfo=UTC),
        provenance_sha256="b" * 64,
    )

    generation = manifest.start_request.prospective_generation
    assert generation is not None
    assert len(manifest.slices) == 9
    assert {item.slot for item in generation.schedules} == set(
        ProspectiveArchiveScheduleSlot
    )
    assert generation.outcome_session_id == sessions[1].session_id
    assert ArchiveOperatorManifest.from_json(manifest.to_json()) == manifest
