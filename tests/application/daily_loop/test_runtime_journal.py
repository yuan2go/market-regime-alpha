from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from market_regime_alpha.application.daily_loop.commands import (
    DailyRunCommand,
    DailyRunIdentity,
    RunMode,
)
from market_regime_alpha.application.daily_loop.repositories import (
    AcquisitionStageReceipt,
    StageReceipt,
)
from tests.postgres_path_repositories import (
    PostgresDailyRunRepository,
)
from market_regime_alpha.application.daily_loop.state import (
    DailyRunStatus,
    validate_daily_run_transition,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.core.time import DecisionTime
from market_regime_alpha.data.providers.public_composite.stage_artifact import (
    PublicSourceAcquisitionStage,
)


SHANGHAI = ZoneInfo("Asia/Shanghai")
DECISION = DecisionTime(
    datetime(2026, 7, 24, 14, 55, tzinfo=SHANGHAI)
)


def _command(
    output_root: Path,
    *,
    provider_profile_id: str = "public-composite-live-v1",
    run_mode: RunMode = RunMode.LIVE,
) -> DailyRunCommand:
    return DailyRunCommand(
        decision_date=date(2026, 7, 24),
        decision_time=DECISION,
        run_mode=run_mode,
        provider_profile_id=provider_profile_id,
        universe_policy_id="a-share-smoke-20-v1",
        model_set_id="platform-b0-b1-v1",
        configuration_identity=ArtifactId("daily-config-test-v1"),
        output_root=output_root,
        replay_source_manifest_id=(
            ArtifactId("source-manifest-replay-test-v1")
            if run_mode is RunMode.REPLAY
            else None
        ),
    )


def _identity(command: DailyRunCommand, *, source_suffix: str = "a") -> DailyRunIdentity:
    return DailyRunIdentity(
        run_request_id=command.run_request_id,
        run_request_hash=command.content_hash,
        code_revision="772ecfb09410588b5a406ad900d793a5850e60d5",
        configuration_hash="sha256:" + "1" * 64,
        source_manifest_id=ArtifactId(
            f"source-manifest-{source_suffix}-v1"
        ),
        source_manifest_content_hash="sha256:" + "2" * 64,
        source_content_hashes=(
            "sha256:" + "3" * 64,
            "sha256:" + "4" * 64,
        ),
    )


def test_run_request_identity_is_deterministic_and_binds_command(tmp_path: Path) -> None:
    first = _command(tmp_path / "runs")
    repeated = _command(tmp_path / "runs")
    changed = _command(
        tmp_path / "runs",
        provider_profile_id="public-composite-replay-v1",
        run_mode=RunMode.REPLAY,
    )

    assert first.run_request_id == repeated.run_request_id
    assert first.content_hash == repeated.content_hash
    assert changed.run_request_id != first.run_request_id
    assert first.output_root.is_absolute()
    with pytest.raises(ValueError, match="decision_date"):
        DailyRunCommand(
            decision_date=date(2026, 7, 23),
            decision_time=DECISION,
            run_mode=RunMode.LIVE,
            provider_profile_id="public-composite-live-v1",
            universe_policy_id="a-share-smoke-20-v1",
            model_set_id="platform-b0-b1-v1",
            configuration_identity=ArtifactId("daily-config-test-v1"),
            output_root=tmp_path,
        )
    with pytest.raises(ValueError, match="replay_source_manifest_id"):
        DailyRunCommand(
            decision_date=date(2026, 7, 24),
            decision_time=DECISION,
            run_mode=RunMode.REPLAY,
            provider_profile_id="public-composite-replay-v1",
            universe_policy_id="a-share-smoke-20-v1",
            model_set_id="platform-b0-b1-v1",
            configuration_identity=ArtifactId("daily-config-test-v1"),
            output_root=tmp_path,
        )


def test_daily_run_identity_is_derived_only_after_source_freeze(
    tmp_path: Path,
) -> None:
    command = _command(tmp_path / "runs")
    first = _identity(command)
    repeated = _identity(command)
    changed_source = _identity(command, source_suffix="b")

    assert first.daily_run_id == repeated.daily_run_id
    assert first.content_hash == repeated.content_hash
    assert first.daily_run_id.value.startswith("daily-run-")
    assert first.daily_run_id.value != command.run_request_id.value
    assert changed_source.daily_run_id != first.daily_run_id


def test_daily_run_state_machine_distinguishes_blocked_failed_and_reviewed() -> None:
    validate_daily_run_transition(
        DailyRunStatus.CREATED,
        DailyRunStatus.SOURCE_ACQUIRING,
    )
    validate_daily_run_transition(
        DailyRunStatus.SOURCE_ACQUIRING,
        DailyRunStatus.SOURCE_FROZEN,
    )
    validate_daily_run_transition(
        DailyRunStatus.SOURCE_FROZEN,
        DailyRunStatus.DATA_BLOCKED,
    )
    with pytest.raises(ValueError, match="terminal"):
        validate_daily_run_transition(
            DailyRunStatus.DATA_BLOCKED,
            DailyRunStatus.UNIVERSE_READY,
        )
    with pytest.raises(ValueError, match="invalid"):
        validate_daily_run_transition(
            DailyRunStatus.SOURCE_ACQUIRING,
            DailyRunStatus.DATA_BLOCKED,
        )
    validate_daily_run_transition(
        DailyRunStatus.OUTCOME_PENDING,
        DailyRunStatus.REVIEW_PUBLISHED,
    )


def test_postgres_journal_is_idempotent_and_preserves_request_primary_key(
    tmp_path: Path,
) -> None:
    journal = tmp_path / "runtime.postgres-scope"
    command = _command(tmp_path / "runs")
    repository = PostgresDailyRunRepository(journal)
    now = datetime(2026, 7, 24, 14, 54, tzinfo=SHANGHAI)

    created = repository.create_or_get(command, created_at=now)
    repeated = repository.create_or_get(command, created_at=now)

    assert created == repeated
    assert created.status is DailyRunStatus.CREATED
    assert repository.begin_source_acquisition(
        command.run_request_id,
        changed_at=now,
    )
    assert not repository.begin_source_acquisition(
        command.run_request_id,
        changed_at=now,
    )
    with pytest.raises(ValueError, match="bind_source_frozen"):
        repository.transition(
            command.run_request_id,
            expected_status=DailyRunStatus.SOURCE_ACQUIRING,
            target_status=DailyRunStatus.SOURCE_FROZEN,
            changed_at=now,
        )

    restarted = PostgresDailyRunRepository(journal)
    acquiring = restarted.get(command.run_request_id)
    assert acquiring.status is DailyRunStatus.SOURCE_ACQUIRING
    identity = _identity(command)
    frozen = restarted.bind_source_frozen(
        command.run_request_id,
        identity=identity,
        changed_at=now,
    )

    assert frozen.run_request_id == command.run_request_id
    assert frozen.daily_run_id == identity.daily_run_id
    assert frozen.status is DailyRunStatus.SOURCE_FROZEN
    assert restarted.bind_source_frozen(
        command.run_request_id,
        identity=identity,
        changed_at=now,
    ) == frozen
    with pytest.raises(ValueError, match="immutable"):
        restarted.bind_source_frozen(
            command.run_request_id,
            identity=_identity(command, source_suffix="other"),
            changed_at=now,
        )


def test_postgres_journal_recovers_failed_stage_after_restart(tmp_path: Path) -> None:
    journal = tmp_path / "runtime.postgres-scope"
    command = _command(tmp_path / "runs")
    repository = PostgresDailyRunRepository(journal)
    now = datetime(2026, 7, 24, 14, 54, tzinfo=SHANGHAI)
    repository.create_or_get(command, created_at=now)
    repository.begin_source_acquisition(command.run_request_id, changed_at=now)
    repository.bind_source_frozen(
        command.run_request_id,
        identity=_identity(command),
        changed_at=now,
    )
    failed = repository.mark_failed(
        command.run_request_id,
        reason="simulated interruption",
        changed_at=now,
    )

    assert failed.status is DailyRunStatus.FAILED
    assert failed.resume_status is DailyRunStatus.SOURCE_FROZEN
    restarted = PostgresDailyRunRepository(journal)
    resumed = restarted.resume_failed(
        command.run_request_id,
        changed_at=now,
    )
    assert resumed.status is DailyRunStatus.SOURCE_FROZEN
    assert resumed.failure_reason is None
    assert resumed.resume_status is None


def test_postgres_stage_receipts_are_idempotent_and_conflict_checked(
    tmp_path: Path,
) -> None:
    command = _command(tmp_path / "runs")
    repository = PostgresDailyRunRepository(tmp_path / "runtime.postgres-scope")
    now = datetime(2026, 7, 24, 14, 54, tzinfo=SHANGHAI)
    repository.create_or_get(command, created_at=now)
    receipt = StageReceipt(
        run_request_id=command.run_request_id,
        stage=DailyRunStatus.SOURCE_ACQUIRING,
        input_artifact_ids=(ArtifactId("provider-profile-live-v1"),),
        output_artifact_ids=(ArtifactId("source-attempt-a-v1"),),
        completed_at=now,
    )

    assert repository.record_stage_receipt(receipt) == receipt
    assert repository.record_stage_receipt(receipt) == receipt
    assert (
        PostgresDailyRunRepository(tmp_path / "runtime.postgres-scope").get_stage_receipt(
            command.run_request_id,
            DailyRunStatus.SOURCE_ACQUIRING,
        )
        == receipt
    )
    with pytest.raises(ValueError, match="receipt conflict"):
        repository.record_stage_receipt(
            StageReceipt(
                run_request_id=command.run_request_id,
                stage=DailyRunStatus.SOURCE_ACQUIRING,
                input_artifact_ids=(ArtifactId("provider-profile-live-v1"),),
                output_artifact_ids=(ArtifactId("source-attempt-b-v1"),),
                completed_at=now,
            )
        )


def test_postgres_acquisition_receipts_survive_restart(tmp_path: Path) -> None:
    command = _command(tmp_path / "runs")
    journal = tmp_path / "runtime.postgres-scope"
    repository = PostgresDailyRunRepository(journal)
    now = datetime(2026, 7, 24, 14, 54, tzinfo=SHANGHAI)
    repository.create_or_get(command, created_at=now)
    receipt = AcquisitionStageReceipt(
        run_request_id=command.run_request_id,
        stage=PublicSourceAcquisitionStage.HISTORY_SOURCE_FROZEN,
        artifact_id=ArtifactId("source-stage-history-test"),
        content_hash="sha256:" + "8" * 64,
        locator=str(tmp_path / "source-stage-history-test"),
        completed_at=now,
    )

    assert repository.record_acquisition_receipt(receipt) == receipt
    assert repository.record_acquisition_receipt(receipt) == receipt
    assert (
        PostgresDailyRunRepository(journal).get_acquisition_receipt(
            command.run_request_id,
            PublicSourceAcquisitionStage.HISTORY_SOURCE_FROZEN,
        )
        == receipt
    )
