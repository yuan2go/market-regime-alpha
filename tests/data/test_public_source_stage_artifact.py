from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from market_regime_alpha.core.identity import ProviderId
from market_regime_alpha.core.time import RetrievedAt
from market_regime_alpha.data.providers.public_composite import (
    AcquiredSourcePayload,
    PublicCompositeBatch,
    PublicSourceAcquisitionStage,
    find_verified_public_source_stage_artifact,
    load_verified_public_source_stage_artifact,
    publish_public_source_stage_artifact,
)


SHANGHAI = ZoneInfo("Asia/Shanghai")


def _history_batch() -> PublicCompositeBatch:
    payload = AcquiredSourcePayload(
        provider_id=ProviderId("provider-baostock-public"),
        product="fixture-stage-history",
        locator="baostock://fixture/stage-history",
        raw_payload=b"date,code,close\n2025-01-03,sz.000001,10.0\n",
        retrieved_time=RetrievedAt(
            datetime(2025, 1, 6, 14, 50, tzinfo=SHANGHAI)
        ),
        limitations=("PUBLIC_DATA_EXPLORATORY_ONLY",),
    )
    return PublicCompositeBatch(
        raw_payloads=(payload,),
        bars=(),
        quotes=(),
        source_conflicts=(),
        limitations=("BAOSTOCK_HISTORY_ONLY",),
    )


def test_source_stage_artifact_round_trips_exact_bytes(tmp_path: Path) -> None:
    batch = _history_batch()

    path = publish_public_source_stage_artifact(
        root=tmp_path,
        stage=PublicSourceAcquisitionStage.HISTORY_SOURCE_FROZEN,
        batch=batch,
    )
    verified = load_verified_public_source_stage_artifact(path)

    assert verified.stage is PublicSourceAcquisitionStage.HISTORY_SOURCE_FROZEN
    assert verified.batch == batch
    assert verified.artifact_id.value == path.name
    assert {item.name for item in path.iterdir()} == {
        "SHA256SUMS.json",
        "batch.json",
        "manifest.json",
    }


def test_source_stage_reader_rejects_tampered_batch(tmp_path: Path) -> None:
    path = publish_public_source_stage_artifact(
        root=tmp_path,
        stage=PublicSourceAcquisitionStage.HISTORY_SOURCE_FROZEN,
        batch=_history_batch(),
    )
    (path / "batch.json").write_text("{}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="checksum"):
        load_verified_public_source_stage_artifact(path)


def test_v2_stage_can_be_recovered_by_run_request_before_receipt(
    tmp_path: Path,
) -> None:
    path = publish_public_source_stage_artifact(
        root=tmp_path,
        stage=PublicSourceAcquisitionStage.HISTORY_SOURCE_FROZEN,
        batch=_history_batch(),
        acquisition_key="run-request-stage-recovery",
    )

    recovered = find_verified_public_source_stage_artifact(
        root=tmp_path,
        stage=PublicSourceAcquisitionStage.HISTORY_SOURCE_FROZEN,
        acquisition_key="run-request-stage-recovery",
    )

    assert recovered is not None
    assert recovered.root == path
    assert recovered.acquisition_key == "run-request-stage-recovery"
