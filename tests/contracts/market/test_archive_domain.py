from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

import pytest

from market_regime_alpha.market.domain import (
    ArchiveCaptureObservation,
    ArchiveEvidenceClass,
    ArchiveLane,
    ArchiveObservationRelation,
    ArchiveObservationTimeliness,
    ArchiveSealDisposition,
    ArchiveSliceStatus,
    MarketArchive,
    MarketArchiveSeal,
    MarketArchiveSlice,
    RetrospectiveSimulationClock,
)
from market_regime_alpha.market.domain.vocabulary import BarTimeframe, PriceBasis
from market_regime_alpha.shared.hashing import canonical_json_sha256


UTC = timezone.utc
ARCHIVE_ID = UUID("10000000-0000-0000-0000-000000000001")
SLICE_1_ID = UUID("10000000-0000-0000-0000-000000000011")
SLICE_2_ID = UUID("10000000-0000-0000-0000-000000000012")
SEAL_ID = UUID("10000000-0000-0000-0000-000000000021")
SESSION_ID = UUID("10000000-0000-0000-0000-000000000031")
PRODUCT_ID = UUID("10000000-0000-0000-0000-000000000041")
HASH_A = canonical_json_sha256({"a": 1})
HASH_B = canonical_json_sha256({"b": 2})


def _slice(*, ordinal: int, slice_id: UUID, status: ArchiveSliceStatus = ArchiveSliceStatus.PLANNED) -> MarketArchiveSlice:
    return MarketArchiveSlice(
        market_archive_slice_id=slice_id,
        market_archive_id=ARCHIVE_ID,
        ordinal=ordinal,
        scope_key=f"sh.60000{ordinal}",
        event_window_start=datetime(2026, 1, ordinal, tzinfo=UTC),
        event_window_end=datetime(2026, 1, ordinal, 23, 59, tzinfo=UTC),
        request_sha256=HASH_A if ordinal == 1 else HASH_B,
        expected_fact_kind="MARKET_BAR",
        status=status,
    )


def _archive(*, lane: ArchiveLane = ArchiveLane.RETROSPECTIVE_BACKFILL) -> MarketArchive:
    return MarketArchive(
        market_archive_id=ARCHIVE_ID,
        lane=lane,
        provider_product_id=PRODUCT_ID,
        exchange_code="SSE",
        timeframe=BarTimeframe.MINUTE_5,
        price_basis=PriceBasis.RAW_UNADJUSTED,
        instrument_scope="ENGINEERING_EXPLORATORY_PILOT_32",
        instrument_scope_sha256=HASH_A,
        event_window_start=datetime(2026, 1, 1, tzinfo=UTC),
        event_window_end=datetime(2026, 9, 2, 23, 59, tzinfo=UTC),
        archive_start_at=datetime(2026, 9, 3, 0, 1, tzinfo=UTC),
        reserved_free_bytes=2_000_000_000,
        maximum_archive_bytes=2_000_000_000,
        maximum_slice_bytes=50_000_000,
        code_artifact_id=UUID("10000000-0000-0000-0000-000000000051"),
        config_artifact_id=UUID("10000000-0000-0000-0000-000000000052"),
        provenance_sha256=HASH_B,
        slices=(
            _slice(ordinal=1, slice_id=SLICE_1_ID),
            _slice(ordinal=2, slice_id=SLICE_2_ID),
        ),
    )


def test_archive_freezes_contiguous_complete_slice_roster() -> None:
    archive = _archive()

    assert archive.slice_count == 2
    assert str(archive.slice_roster_sha256) == canonical_json_sha256(
        [
            {"content_sha256": str(item.content_sha256), "ordinal": item.ordinal}
            for item in archive.slices
        ]
    )
    assert archive.evidence_class is ArchiveEvidenceClass.EXPLORATORY_RETROSPECTIVE


def test_archive_rejects_non_contiguous_or_foreign_slice_roster() -> None:
    first = _slice(ordinal=1, slice_id=SLICE_1_ID)
    third = MarketArchiveSlice(
        market_archive_slice_id=SLICE_2_ID,
        market_archive_id=ARCHIVE_ID,
        ordinal=3,
        scope_key="sh.600003",
        event_window_start=datetime(2026, 1, 3, tzinfo=UTC),
        event_window_end=datetime(2026, 1, 3, 23, 59, tzinfo=UTC),
        request_sha256=HASH_B,
        expected_fact_kind="MARKET_BAR",
        status=ArchiveSliceStatus.PLANNED,
    )
    with pytest.raises(ValueError, match="ordinals must be contiguous"):
        MarketArchive(
            **{
                name: getattr(_archive(), name)
                for name in _archive().__dataclass_fields__
                if name not in {"slices", "slice_count", "slice_roster_sha256", "content_sha256", "evidence_class"}
            },
            slices=(first, third),
        )


def test_prospective_archive_rejects_event_window_before_database_start() -> None:
    with pytest.raises(ValueError, match="prospective event window cannot precede archive start"):
        _archive(lane=ArchiveLane.PROSPECTIVE_CONTEMPORANEOUS)


def test_retrospective_seal_requires_terminal_slice_roster_and_database_cutoff() -> None:
    terminal = (
        _slice(ordinal=1, slice_id=SLICE_1_ID, status=ArchiveSliceStatus.CAPTURED),
        _slice(ordinal=2, slice_id=SLICE_2_ID, status=ArchiveSliceStatus.GAP_RECORDED),
    )
    sealed_at = datetime(2026, 9, 3, 0, 30, tzinfo=UTC)
    seal = MarketArchiveSeal.create(
        market_archive_seal_id=SEAL_ID,
        archive=_archive(),
        terminal_slices=terminal,
        sealed_at=sealed_at,
        disposition=ArchiveSealDisposition.PARTIAL_WITH_GAPS,
        capture_count=1,
        capture_roster_sha256=HASH_A,
        artifact_count=1,
        artifact_roster_sha256=HASH_A,
        normalized_revision_count=96,
        normalized_revision_roster_sha256=HASH_B,
        gap_count=1,
        gap_roster_sha256=HASH_B,
    )

    assert seal.knowledge_cutoff == sealed_at
    assert seal.disposition is ArchiveSealDisposition.PARTIAL_WITH_GAPS

    non_terminal = (
        _slice(ordinal=1, slice_id=SLICE_1_ID, status=ArchiveSliceStatus.CAPTURED),
        _slice(ordinal=2, slice_id=SLICE_2_ID, status=ArchiveSliceStatus.PLANNED),
    )
    with pytest.raises(ValueError, match="every archive slice must be terminal"):
        MarketArchiveSeal.create(
            market_archive_seal_id=SEAL_ID,
            archive=_archive(),
            terminal_slices=non_terminal,
            sealed_at=sealed_at,
            disposition=ArchiveSealDisposition.PARTIAL_WITH_GAPS,
            capture_count=1,
            capture_roster_sha256=HASH_A,
            artifact_count=1,
            artifact_roster_sha256=HASH_A,
            normalized_revision_count=96,
            normalized_revision_roster_sha256=HASH_B,
            gap_count=1,
            gap_roster_sha256=HASH_B,
        )


def test_dual_clock_is_fixed_to_retrospective_evidence_and_real_knowledge_time() -> None:
    clock = RetrospectiveSimulationClock(
        market_archive_id=ARCHIVE_ID,
        market_archive_seal_id=SEAL_ID,
        simulation_session_id=SESSION_ID,
        knowledge_cutoff=datetime(2026, 9, 3, 0, 30, tzinfo=UTC),
        simulated_event_cutoff=datetime(2026, 6, 30, 2, 30, tzinfo=UTC),
    )

    assert clock.evidence_class is ArchiveEvidenceClass.EXPLORATORY_RETROSPECTIVE

    with pytest.raises(ValueError, match="simulated event cutoff must precede knowledge cutoff"):
        RetrospectiveSimulationClock(
            market_archive_id=ARCHIVE_ID,
            market_archive_seal_id=SEAL_ID,
            simulation_session_id=SESSION_ID,
            knowledge_cutoff=datetime(2026, 9, 3, 0, 30, tzinfo=UTC),
            simulated_event_cutoff=datetime(2026, 9, 3, 0, 30, tzinfo=UTC),
        )


def test_capture_observation_freezes_global_chain_and_real_times() -> None:
    observation = ArchiveCaptureObservation(
        market_archive_capture_observation_id=UUID("10000000-0000-0000-0000-000000000061"),
        market_archive_id=ARCHIVE_ID,
        market_archive_slice_id=SLICE_1_ID,
        capture_id=UUID("10000000-0000-0000-0000-000000000062"),
        observation_ordinal=1,
        previous_observation_id=None,
        schedule_slot="POST_CLOSE",
        requested_at=datetime(2026, 9, 3, 7, 1, tzinfo=UTC),
        capture_started_at=datetime(2026, 9, 3, 7, 1, 1, tzinfo=UTC),
        capture_completed_at=datetime(2026, 9, 3, 7, 1, 2, tzinfo=UTC),
        recorded_at=datetime(2026, 9, 3, 7, 1, 3, tzinfo=UTC),
        known_at=datetime(2026, 9, 3, 7, 1, 3, tzinfo=UTC),
        event_window_start=datetime(2026, 9, 3, 6, 55, tzinfo=UTC),
        event_window_end=datetime(2026, 9, 3, 7, 0, tzinfo=UTC),
        artifact_sha256=HASH_A,
        artifact_size_bytes=2048,
        normalized_revision_count=32,
        normalized_revision_roster_sha256=HASH_B,
        relation=ArchiveObservationRelation.FIRST,
        timeliness=ArchiveObservationTimeliness.ON_TIME,
    )

    assert observation.known_at == datetime(2026, 9, 3, 7, 1, 3, tzinfo=UTC)

    with pytest.raises(ValueError, match="observation revision chain"):
        ArchiveCaptureObservation(
            **{
                name: getattr(observation, name)
                for name in observation.__dataclass_fields__
                if name not in {"observation_ordinal", "content_sha256"}
            },
            observation_ordinal=2,
        )
