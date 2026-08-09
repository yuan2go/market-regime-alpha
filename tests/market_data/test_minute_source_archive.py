from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
from pathlib import Path

import pytest

from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.market_data.contracts import (
    AssetType,
    CanonicalMarketBar,
    Timeframe,
    VolumeUnit,
)
from market_regime_alpha.market_data import FormalPitStatus, MarketDataDatasetArtifact
from market_regime_alpha.market_data.minute_source import (
    CanonicalVolumeUnitPolicy,
    MinuteDataConflictError,
    MinuteSourceRequest,
    MinuteSourceResponse,
    RawMinuteSourceArtifact,
    RawMinuteSourceAttempt,
    RawMinuteSourceReader,
    acquire_and_archive_minute_source,
    build_combined_market_data_dataset,
    load_raw_minute_attempt,
    minute_normalization_to_dataset,
    normalize_tencent_minute_source,
    publish_raw_minute_attempt,
    publish_raw_minute_source,
)


DECISION_TIME = datetime(2026, 8, 4, 7, 5, tzinfo=timezone.utc)
STARTED_AT = datetime(2026, 8, 4, 6, 58, tzinfo=timezone.utc)
RECEIVED_AT = datetime(2026, 8, 4, 6, 59, tzinfo=timezone.utc)


def _raw_payload(*, rows: list[str] | None = None, code: int = 0) -> bytes:
    values = rows or [
        "0930 10.00 1 1000",
        "0931 10.01 2 2001",
        "0932 10.02 3 3003",
        "0933 10.03 4 4006",
        "0934 10.04 5 5010",
        "0935 10.05 6 6015",
        "0936 10.06 7 7021",
        "0937 10.07 8 8028",
        "0938 10.08 9 9036",
        "0939 10.09 10 10045",
    ]
    return json.dumps(
        {
            "code": code,
            "data": {"sh600000": {"data": {"date": "20260804", "data": values}}},
        },
        separators=(",", ":"),
    ).encode()


def _artifact(*, raw: bytes | None = None, content_type: str = "application/json") -> RawMinuteSourceArtifact:
    request = MinuteSourceRequest(
        symbols=("600000.SH",),
        timeframe=Timeframe.MINUTE_1,
        decision_time=DECISION_TIME,
    )
    return RawMinuteSourceArtifact.from_response(
        MinuteSourceResponse(
            request=request,
            request_started_at=STARTED_AT,
            response_received_at=RECEIVED_AT,
            http_status=200,
            content_type=content_type,
            raw_payload=raw or _raw_payload(),
            provider_timestamp="20260804",
            limitations=("PUBLIC_TENCENT_EXPLORATORY_ONLY",),
        )
    )


def test_raw_source_archive_is_immutable_tamper_evident_and_replayable(
    tmp_path: Path,
) -> None:
    artifact = _artifact()
    package = publish_raw_minute_source(tmp_path, artifact)

    loaded = RawMinuteSourceReader().read(package)

    assert loaded.content_hash == artifact.content_hash
    assert loaded.raw_payload == artifact.raw_payload
    assert loaded.raw_payload_hash == artifact.raw_payload_hash
    with pytest.raises(FileExistsError, match="already exists"):
        publish_raw_minute_source(tmp_path, artifact)

    (package / "raw-response.bin").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="checksum mismatch"):
        RawMinuteSourceReader().read(package)


def test_raw_source_archive_publish_is_crash_atomic(tmp_path: Path) -> None:
    artifact = _artifact()

    def fail_after_staging(stage: str) -> None:
        if stage == "AFTER_STAGING_VALIDATED":
            raise RuntimeError("injected archive crash")

    with pytest.raises(RuntimeError, match="injected archive crash"):
        publish_raw_minute_source(tmp_path, artifact, failure_injector=fail_after_staging)
    assert not (tmp_path / str(artifact.source_artifact_id)).exists()
    assert not tuple(tmp_path.glob(".*"))


def test_failed_and_successful_source_attempts_are_immutable_evidence(
    tmp_path: Path,
) -> None:
    artifact = _artifact()
    success = RawMinuteSourceAttempt.succeeded(artifact)
    success_path = publish_raw_minute_attempt(tmp_path, success)
    assert load_raw_minute_attempt(success_path) == success

    failed = RawMinuteSourceAttempt.failed(
        request=MinuteSourceRequest(
            symbols=("600000.SH",),
            timeframe=Timeframe.MINUTE_1,
            decision_time=DECISION_TIME,
        ),
        request_started_at=STARTED_AT,
        completed_at=RECEIVED_AT,
        error_code="HTTP_ERROR",
        error_message="provider unavailable",
        http_status=503,
    )
    failed_path = publish_raw_minute_attempt(tmp_path, failed)
    assert load_raw_minute_attempt(failed_path) == failed
    with pytest.raises(FileExistsError, match="already exists"):
        publish_raw_minute_attempt(tmp_path, failed)
    failed_path.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="fields mismatch"):
        load_raw_minute_attempt(failed_path)


def test_acquisition_archives_source_and_attempt_and_records_fetch_failure(
    tmp_path: Path,
) -> None:
    artifact = _artifact()

    class SuccessfulClient:
        def fetch(self, request: MinuteSourceRequest) -> MinuteSourceResponse:
            assert request.request_identity == artifact.request_identity
            return MinuteSourceResponse(
                request=request,
                request_started_at=STARTED_AT,
                response_received_at=RECEIVED_AT,
                http_status=artifact.http_status,
                content_type=artifact.content_type,
                raw_payload=artifact.raw_payload,
                provider_timestamp=artifact.provider_timestamp,
                limitations=artifact.retrieval_limitations,
            )

    acquired = acquire_and_archive_minute_source(
        client=SuccessfulClient(),
        request=MinuteSourceRequest(
            symbols=("600000.SH",),
            timeframe=Timeframe.MINUTE_1,
            decision_time=DECISION_TIME,
        ),
        source_root=tmp_path / "sources",
        attempt_root=tmp_path / "attempts",
        clock=lambda: RECEIVED_AT,
    )
    assert RawMinuteSourceReader().read(acquired.source_path) == artifact
    assert load_raw_minute_attempt(acquired.attempt_path) == acquired.attempt

    class FailedClient:
        def fetch(self, request: MinuteSourceRequest) -> MinuteSourceResponse:
            raise ConnectionError("provider unavailable")

    with pytest.raises(ConnectionError, match="provider unavailable"):
        acquire_and_archive_minute_source(
            client=FailedClient(),
            request=MinuteSourceRequest(
                symbols=("000001.SZ",),
                timeframe=Timeframe.MINUTE_1,
                decision_time=DECISION_TIME,
            ),
            source_root=tmp_path / "sources",
            attempt_root=tmp_path / "attempts",
            clock=lambda: RECEIVED_AT,
        )
    failed_paths = tuple((tmp_path / "attempts").glob("*.json"))
    assert len(failed_paths) == 2
    failed = next(load_raw_minute_attempt(path) for path in failed_paths if load_raw_minute_attempt(path).status.value == "FAILED")
    assert failed.error_code == "CONNECTIONERROR"
    assert failed.source_artifact_id is None


def test_html_or_failed_provider_response_never_becomes_source_artifact() -> None:
    request = MinuteSourceRequest(
        symbols=("600000.SH",),
        timeframe=Timeframe.MINUTE_1,
        decision_time=DECISION_TIME,
    )
    response = MinuteSourceResponse(
        request=request,
        request_started_at=STARTED_AT,
        response_received_at=RECEIVED_AT,
        http_status=200,
        content_type="text/html",
        raw_payload=b"<html>provider error</html>",
        provider_timestamp=None,
        limitations=(),
    )
    with pytest.raises(MinuteDataConflictError, match="not valid Tencent JSON"):
        RawMinuteSourceArtifact.from_response(response)


def test_valid_tencent_json_with_html_content_type_is_archived_with_limitation() -> None:
    artifact = _artifact(content_type="text/html")

    assert "PROVIDER_CONTENT_TYPE_MISMATCH_VALID_JSON" in (artifact.retrieval_limitations)
    normalized = normalize_tencent_minute_source(
        artifact=artifact,
        asset_type=AssetType.A_SHARE,
        volume_policy=CanonicalVolumeUnitPolicy.a_share_v1(),
    )
    assert normalized.one_minute_bars


def test_provider_declared_error_never_becomes_source_artifact() -> None:
    with pytest.raises(MinuteDataConflictError, match="declares an error"):
        normalize_tencent_minute_source(
            artifact=_artifact(raw=_raw_payload(code=7)),
            asset_type=AssetType.A_SHARE,
            volume_policy=CanonicalVolumeUnitPolicy.a_share_v1(),
        )


@pytest.mark.parametrize(
    ("rows", "message"),
    [
        (["0930 10 1 100", "0930 10 2 200"], "duplicate provider minute"),
        (
            ["0930 10 2 200", "0931 10 1 300"],
            "CUMULATIVE_VOLUME_DECREASE",
        ),
        (
            ["0930 10 1 300", "0931 10 2 200"],
            "CUMULATIVE_AMOUNT_DECREASE",
        ),
    ],
)
def test_cumulative_conflicts_fail_closed(rows: list[str], message: str) -> None:
    with pytest.raises(MinuteDataConflictError, match=message):
        normalize_tencent_minute_source(
            artifact=_artifact(raw=_raw_payload(rows=rows)),
            asset_type=AssetType.A_SHARE,
            volume_policy=CanonicalVolumeUnitPolicy.a_share_v1(),
        )


def test_volume_lots_are_explicitly_converted_and_complete_windows_resampled() -> None:
    artifact = _artifact()
    normalized = normalize_tencent_minute_source(
        artifact=artifact,
        asset_type=AssetType.A_SHARE,
        volume_policy=CanonicalVolumeUnitPolicy.a_share_v1(),
    )

    assert len(normalized.one_minute_bars) == 10
    assert len(normalized.five_minute_bars) == 2
    assert normalized.one_minute_bars[0].volume == Decimal("100")
    assert normalized.five_minute_bars[0].volume == Decimal("500")
    assert normalized.five_minute_bars[0].amount == Decimal("5010")
    assert all(item.volume_unit is VolumeUnit.SHARES for item in normalized.one_minute_bars)
    assert normalized.five_minute_bars[0].event_start.isoformat() == "2026-08-04T01:30:00+00:00"
    assert normalized.five_minute_bars[0].event_end.isoformat() == "2026-08-04T01:35:00+00:00"
    assert normalized.source_manifest.source_artifacts[0].artifact_id == artifact.source_artifact_id
    assert normalized.source_manifest.data_eligibility is DataEligibility.EXPLORATORY

    dataset = minute_normalization_to_dataset(
        normalized=normalized,
        artifact=artifact,
        created_at=DECISION_TIME,
    )
    assert dataset.data_eligibility is DataEligibility.EXPLORATORY
    assert dataset.formal_pit_status.value == "FORMAL_PIT_NOT_ESTABLISHED"
    assert {item.timeframe for item in dataset.iter_bars()} == {
        Timeframe.MINUTE_1,
        Timeframe.MINUTE_5,
    }
    assert all(item.source_artifact_id == artifact.source_artifact_id for item in dataset.iter_bars())


def test_incomplete_five_minute_window_is_withheld_with_explicit_missingness() -> None:
    rows = [
        "0930 10.00 1 1000",
        "0931 10.01 2 2001",
        "0933 10.03 4 4006",
        "0934 10.04 5 5010",
    ]
    normalized = normalize_tencent_minute_source(
        artifact=_artifact(raw=_raw_payload(rows=rows)),
        asset_type=AssetType.A_SHARE,
        volume_policy=CanonicalVolumeUnitPolicy.a_share_v1(),
    )

    assert normalized.five_minute_bars == ()
    assert normalized.missing_minutes == ("2026-08-04T01:32:00Z",)
    assert normalized.source_manifest.fields[0].reason_codes == ("MISSING_PROVIDER_MINUTES",)


def test_resampling_boundaries_exclude_lunch_and_post_close_stamps() -> None:
    stamps = (
        "1125",
        "1126",
        "1127",
        "1128",
        "1129",
        "1130",
        "1300",
        "1301",
        "1302",
        "1303",
        "1304",
        "1455",
        "1456",
        "1457",
        "1458",
        "1459",
        "1500",
    )
    rows = [
        f"{stamp} {Decimal('10') + Decimal(index) / Decimal('100')} {index + 1} {(index + 1) * 1000}" for index, stamp in enumerate(stamps)
    ]
    normalized = normalize_tencent_minute_source(
        artifact=_artifact(raw=_raw_payload(rows=rows)),
        asset_type=AssetType.A_SHARE,
        volume_policy=CanonicalVolumeUnitPolicy.a_share_v1(),
    )
    local_starts = tuple(item.event_start.astimezone(timezone(timedelta(hours=8))).strftime("%H%M") for item in normalized.one_minute_bars)
    assert "1130" not in local_starts
    assert "1500" not in local_starts
    assert "1459" not in local_starts
    assert tuple(item.event_start.astimezone(timezone(timedelta(hours=8))).strftime("%H%M") for item in normalized.five_minute_bars) == (
        "1125",
        "1300",
    )
    assert tuple(item.event_end.astimezone(timezone(timedelta(hours=8))).strftime("%H%M") for item in normalized.five_minute_bars) == (
        "1130",
        "1305",
    )


def test_zero_volume_minute_is_preserved_without_unit_guessing() -> None:
    rows = [
        "0930 10.00 0 0",
        "0931 10.00 0 0",
        "0932 10.00 1 1000",
        "0933 10.00 1 1000",
        "0934 10.00 2 2000",
    ]
    normalized = normalize_tencent_minute_source(
        artifact=_artifact(raw=_raw_payload(rows=rows)),
        asset_type=AssetType.A_SHARE,
        volume_policy=CanonicalVolumeUnitPolicy.a_share_v1(),
    )
    assert normalized.one_minute_bars[0].volume == 0
    assert normalized.one_minute_bars[1].volume == 0
    assert normalized.five_minute_bars[0].volume == Decimal("200")


def test_volume_policy_refuses_asset_types_without_board_lot_authority() -> None:
    policy = CanonicalVolumeUnitPolicy.a_share_v1()
    with pytest.raises(MinuteDataConflictError, match="no board-lot authority"):
        policy.to_shares(
            value=Decimal("1"),
            unit=VolumeUnit.LOTS,
            asset_type=AssetType.ETF,
        )
    assert policy.to_shares(
        value=Decimal("7"),
        unit=VolumeUnit.SHARES,
        asset_type=AssetType.ETF,
    ) == Decimal("7")


def test_archive_raw_hash_is_not_the_semantic_artifact_hash() -> None:
    artifact = _artifact()
    assert artifact.raw_payload_hash != artifact.content_hash
    assert artifact.source_artifact_id != ArtifactId(f"raw-minute-source-{artifact.raw_payload_hash.split(':', 1)[1][:24]}")


def test_combined_dataset_rejects_completed_session_provider_close_conflict() -> None:
    artifact = _artifact()
    normalized = normalize_tencent_minute_source(
        artifact=artifact,
        asset_type=AssetType.A_SHARE,
        volume_policy=CanonicalVolumeUnitPolicy.a_share_v1(),
    )
    minute = minute_normalization_to_dataset(
        normalized=normalized,
        artifact=artifact,
        created_at=DECISION_TIME,
    )
    last_minute = normalized.one_minute_bars[-1]
    daily_bar = CanonicalMarketBar.create(
        symbol=last_minute.symbol,
        exchange=last_minute.exchange,
        asset_type=last_minute.asset_type,
        timeframe=Timeframe.DAILY,
        market_date=last_minute.market_date,
        event_start=last_minute.event_start,
        event_end=last_minute.event_end,
        available_at=last_minute.available_at,
        open=Decimal("99"),
        high=Decimal("99"),
        low=Decimal("99"),
        close=Decimal("99"),
        previous_close=last_minute.previous_close,
        volume=last_minute.volume,
        volume_unit=last_minute.volume_unit,
        amount=last_minute.amount,
        turnover_rate=last_minute.turnover_rate,
        adjustment_mode=last_minute.adjustment_mode,
        adjustment_factor=last_minute.adjustment_factor,
        trading_status=last_minute.trading_status,
        price_limit_state=last_minute.price_limit_state,
        source_artifact_id=ArtifactId("daily-source"),
        source_content_hash="sha256:" + "d" * 64,
    )
    daily = MarketDataDatasetArtifact.create(
        decision_time=artifact.decision_time,
        created_at=DECISION_TIME,
        bars=(daily_bar,),
        expected_symbols=artifact.requested_symbols,
        expected_timeframes=(Timeframe.DAILY,),
        adjustment_policy=minute.adjustment_policy,
        source_manifest_references=((ArtifactId("daily-source"), "sha256:" + "d" * 64),),
        data_eligibility=DataEligibility.EXPLORATORY,
        formal_pit_status=FormalPitStatus.FORMAL_PIT_NOT_ESTABLISHED,
        limitations=("RECORDED_DAILY_FIXTURE",),
    )
    with pytest.raises(ValueError, match="provider disagreement"):
        build_combined_market_data_dataset(
            daily=daily,
            minute=minute,
            created_at=DECISION_TIME,
        )
