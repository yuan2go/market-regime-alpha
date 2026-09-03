from __future__ import annotations

from datetime import UTC, date, datetime, time
from uuid import UUID

from market_regime_alpha.market.application import (
    ProspectiveArchiveInstrument,
    build_target_aligned_prospective_manifest,
    compile_prospective_runtime_plan,
)
from market_regime_alpha.market.application.archive_operations import (
    ArchiveSliceExecutionRequest,
)
from market_regime_alpha.market.domain import (
    ProspectiveArchiveSession,
    TargetArchiveCheckpoint,
    derive_target_archive_sessions,
)
from market_regime_alpha.market.ports import TargetArchiveContract
from market_regime_alpha.shared.hashing import canonical_json_sha256


def _manifest():
    target_id = UUID("28000000-0000-0000-0000-000000000100")
    contract = TargetArchiveContract(
        target_definition_id=target_id,
        version=1,
        content_sha256="a" * 64,
        checkpoints=(
            TargetArchiveCheckpoint(
                UUID("28000000-0000-0000-0000-000000000101"),
                1,
                "DECISION_REFERENCE",
                0,
                time(14, 55),
                "Asia/Shanghai",
            ),
            TargetArchiveCheckpoint(
                UUID("28000000-0000-0000-0000-000000000102"),
                2,
                "OUTCOME_OBSERVATION",
                1,
                time(10, 30),
                "Asia/Shanghai",
            ),
        ),
    )
    sessions = tuple(
        ProspectiveArchiveSession(
            session_id=UUID(f"28000000-0000-0000-0000-{ordinal:012d}"),
            exchange="XSHG",
            session_date=session_date,
            open_at=datetime.combine(session_date, time(1, 30), tzinfo=UTC),
            close_at=datetime.combine(session_date, time(7), tzinfo=UTC),
        )
        for ordinal, session_date in (
            (1, date(2026, 9, 4)),
            (2, date(2026, 9, 7)),
            (3, date(2026, 9, 8)),
        )
    )
    resolved = derive_target_archive_sessions(
        exchange="XSHG",
        decision_session_id=sessions[0].session_id,
        sessions=sessions,
        checkpoints=contract.checkpoints,
        later_verification_session_offset=2,
    )
    return build_target_aligned_prospective_manifest(
        provider_product_id=UUID("28000000-0000-0000-0000-000000000110"),
        code_artifact_id=UUID("28000000-0000-0000-0000-000000000111"),
        config_artifact_id=UUID("28000000-0000-0000-0000-000000000112"),
        contract=contract,
        resolved_sessions=resolved,
        instruments=(
            ProspectiveArchiveInstrument(
                UUID("28000000-0000-0000-0000-000000000113"),
                UUID("28000000-0000-0000-0000-000000000114"),
                "sh.600000",
            ),
            ProspectiveArchiveInstrument(
                UUID("28000000-0000-0000-0000-000000000115"),
                UUID("28000000-0000-0000-0000-000000000116"),
                "sh.600004",
            ),
        ),
        series_code="runtime_plan",
        generation=1,
        predecessor_market_archive_id=None,
        planned_not_before=datetime(2026, 9, 3, tzinfo=UTC),
        provenance_sha256="b" * 64,
    )


def test_runtime_plan_groups_exact_windows_and_hashes_every_slice_request() -> None:
    manifest = _manifest()
    plan = compile_prospective_runtime_plan(manifest, code_sha="1" * 40)

    assert plan.schedule.schedule_code == "prospective-archive"
    assert plan.schedule.runtime_mode.value == "PROSPECTIVE"
    assert plan.config_bytes == manifest.to_bytes()
    assert len(plan.capture_runs) == 9
    assert all(len(run.steps) == 2 for run in plan.capture_runs)
    assert plan.predeclare.steps[0].step_kind == "RECORD_EVIDENCE"
    assert plan.predeclare.steps[0].external_effect_class.value == "NONE"
    for run in plan.capture_runs:
        assert run.window_start < run.window_end
        assert all(step.retry_policy.deadline == run.window_end for step in run.steps)
        for step, item in zip(run.steps, run.slices, strict=True):
            request = ArchiveSliceExecutionRequest(
                market_archive_id=manifest.start_request.market_archive_id,
                market_archive_slice_id=item.plan.market_archive_slice_id,
                capture_request=item.capture_request,
                schedule_slot=item.schedule_slot,
            )
            assert step.request_hash == canonical_json_sha256(request)


def test_runtime_plan_is_exactly_reproducible() -> None:
    manifest = _manifest()

    assert compile_prospective_runtime_plan(
        manifest, code_sha="1" * 40
    ) == compile_prospective_runtime_plan(manifest, code_sha="1" * 40)
