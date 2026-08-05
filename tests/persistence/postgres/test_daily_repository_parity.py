from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from market_regime_alpha.application.daily_loop.postgres_repository import (
    PostgresDailyRunRepository,
)
from market_regime_alpha.application.daily_loop.repositories import (
    AcquisitionStageReceipt,
    StageReceipt,
)
from market_regime_alpha.application.daily_loop.state import DailyRunStatus
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.data.providers.public_composite.stage_artifact import (
    PublicSourceAcquisitionStage,
)
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from tests.application.daily_loop.test_runtime_journal import _command, _identity


SHANGHAI = ZoneInfo("Asia/Shanghai")
NOW = datetime(2026, 8, 5, 14, 54, tzinfo=SHANGHAI)


def test_postgres_daily_journal_restarts_and_preserves_receipts(
    tmp_path,
    postgres_factory: PostgresConnectionFactory,
) -> None:
    command = _command(tmp_path / "runs")
    repository = PostgresDailyRunRepository(postgres_factory)
    created = repository.create_or_get(command, created_at=NOW)
    assert repository.create_or_get(command, created_at=NOW) == created
    assert repository.begin_source_acquisition(command.run_request_id, changed_at=NOW)
    assert not repository.begin_source_acquisition(
        command.run_request_id, changed_at=NOW
    )
    frozen = repository.bind_source_frozen(
        command.run_request_id,
        identity=_identity(command),
        changed_at=NOW,
    )
    assert frozen.status is DailyRunStatus.SOURCE_FROZEN

    stage_receipt = StageReceipt(
        run_request_id=command.run_request_id,
        stage=DailyRunStatus.SOURCE_ACQUIRING,
        input_artifact_ids=(ArtifactId("pg-provider-profile"),),
        output_artifact_ids=(ArtifactId("pg-source-attempt"),),
        completed_at=NOW,
    )
    acquisition_receipt = AcquisitionStageReceipt(
        run_request_id=command.run_request_id,
        stage=PublicSourceAcquisitionStage.HISTORY_SOURCE_FROZEN,
        artifact_id=ArtifactId("pg-history-source"),
        content_hash="sha256:" + "8" * 64,
        locator=str(tmp_path / "pg-history-source"),
        completed_at=NOW,
    )
    assert repository.record_stage_receipt(stage_receipt) == stage_receipt
    assert repository.record_stage_receipt(stage_receipt) == stage_receipt
    assert repository.record_acquisition_receipt(acquisition_receipt) == (
        acquisition_receipt
    )

    restarted = PostgresDailyRunRepository(postgres_factory)
    assert restarted.get_by_daily_run_id(frozen.daily_run_id) == frozen
    assert restarted.get_stage_receipt(
        command.run_request_id, DailyRunStatus.SOURCE_ACQUIRING
    ) == stage_receipt
    assert restarted.get_acquisition_receipt(
        command.run_request_id,
        PublicSourceAcquisitionStage.HISTORY_SOURCE_FROZEN,
    ) == acquisition_receipt

    with pytest.raises(ValueError, match="receipt conflict"):
        restarted.record_stage_receipt(
            StageReceipt(
                run_request_id=command.run_request_id,
                stage=DailyRunStatus.SOURCE_ACQUIRING,
                input_artifact_ids=(ArtifactId("pg-provider-profile"),),
                output_artifact_ids=(ArtifactId("pg-other-attempt"),),
                completed_at=NOW,
            )
        )
