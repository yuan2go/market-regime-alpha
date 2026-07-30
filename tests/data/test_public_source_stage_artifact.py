from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from market_regime_alpha.core.identity import ProviderId
from market_regime_alpha.core.time import (
    AvailabilityTime,
    DecisionTime,
    RetrievedAt,
)
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.data.providers.public_composite import (
    AcquiredSourcePayload,
    PublicCompositeBatch,
    PublicSecurityStatusObservation,
    PublicSourceAcquisitionStage,
    PublicSourceStageScope,
    STStatus,
    SecurityStatusEvidenceScope,
    SecurityStatusFactType,
    find_verified_public_source_stage_artifact,
    load_verified_public_source_stage_artifact,
    publish_public_source_stage_artifact,
)
from market_regime_alpha.data.source_manifest import (
    SourceAuthorityKind,
    SourceFieldFinality,
    SourceFieldQualityStatus,
)


SHANGHAI = ZoneInfo("Asia/Shanghai")
DECISION = DecisionTime(datetime(2025, 1, 6, 14, 55, tzinfo=SHANGHAI))


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


def _status_batch() -> PublicCompositeBatch:
    payload = AcquiredSourcePayload(
        provider_id=ProviderId("provider-baostock-public"),
        product="fixture-stage-security-status",
        locator="baostock://fixture/stage-security-status",
        raw_payload=b'{"date":"2025-01-06","isST":"0"}',
        retrieved_time=RetrievedAt(
            datetime(2025, 1, 6, 14, 49, tzinfo=SHANGHAI)
        ),
        limitations=("PUBLIC_DATA_EXPLORATORY_ONLY",),
    )
    return PublicCompositeBatch(
        raw_payloads=(payload,),
        bars=(),
        quotes=(),
        source_conflicts=(),
        limitations=("BAOSTOCK_CURRENT_SECURITY_STATUS_ONLY",),
        security_status_observations=(
            PublicSecurityStatusObservation(
                symbol="000001.SZ",
                fact_type=SecurityStatusFactType.ST_STATUS,
                value=STStatus.NOT_ST,
                scope=SecurityStatusEvidenceScope.CURRENT_DECISION_SESSION,
                event_time=None,
                available_time=AvailabilityTime(payload.retrieved_time.value),
                retrieved_time=payload.retrieved_time,
                decision_time=DECISION,
                policy_effective_time=None,
                provider_id=payload.provider_id,
                source_artifact_id=payload.source_artifact_id,
                authority_kind=SourceAuthorityKind.PROVIDER,
                quality_status=SourceFieldQualityStatus.COMPLETE,
                reason_codes=(),
                finality=SourceFieldFinality.PRELIMINARY,
                data_eligibility=DataEligibility.EXPLORATORY,
            ),
        ),
    )


def _scope(
    stage: PublicSourceAcquisitionStage,
    *,
    run_request_id: str = "run-request-v3",
) -> PublicSourceStageScope:
    return PublicSourceStageScope(
        run_request_id=run_request_id,
        decision_date=date(2025, 1, 6),
        decision_time=DECISION,
        provider_profile_id="public-composite-live-v1",
        universe_policy_id="smoke-pool-policy-v1",
        acquisition_stage=stage,
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


def test_v3_security_status_stage_round_trips_scope_and_observations(
    tmp_path: Path,
) -> None:
    stage = PublicSourceAcquisitionStage.SECURITY_STATUS_SOURCE_FROZEN
    scope = _scope(stage)
    batch = _status_batch()

    path = publish_public_source_stage_artifact(
        root=tmp_path,
        stage=stage,
        batch=batch,
        scope=scope,
    )
    verified = load_verified_public_source_stage_artifact(path)
    recovered = find_verified_public_source_stage_artifact(
        root=tmp_path,
        stage=stage,
        scope=scope,
    )

    assert verified.scope == scope
    assert verified.acquisition_key is None
    assert verified.batch == batch
    assert recovered == verified
    manifest = (path / "manifest.json").read_text(encoding="utf-8")
    assert '"schema_version": "public-source-acquisition-stage-v3"' in manifest
    assert batch.raw_payloads[0].raw_hash in manifest


def test_v3_recovery_does_not_claim_another_run_request(
    tmp_path: Path,
) -> None:
    stage = PublicSourceAcquisitionStage.SECURITY_STATUS_SOURCE_FROZEN
    publish_public_source_stage_artifact(
        root=tmp_path,
        stage=stage,
        batch=_status_batch(),
        scope=_scope(stage),
    )

    recovered = find_verified_public_source_stage_artifact(
        root=tmp_path,
        stage=stage,
        scope=_scope(stage, run_request_id="run-request-other"),
    )

    assert recovered is None


def test_v3_stage_rejects_scope_for_another_stage(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="scope does not match"):
        publish_public_source_stage_artifact(
            root=tmp_path,
            stage=PublicSourceAcquisitionStage.SECURITY_STATUS_SOURCE_FROZEN,
            batch=_status_batch(),
            scope=_scope(
                PublicSourceAcquisitionStage.DECISION_QUOTE_SOURCE_FROZEN
            ),
        )


def test_v3_reader_rejects_tampered_scope(tmp_path: Path) -> None:
    stage = PublicSourceAcquisitionStage.SECURITY_STATUS_SOURCE_FROZEN
    path = publish_public_source_stage_artifact(
        root=tmp_path,
        stage=stage,
        batch=_status_batch(),
        scope=_scope(stage),
    )
    manifest_path = path / "manifest.json"
    manifest = manifest_path.read_text(encoding="utf-8").replace(
        "run-request-v3",
        "run-request-other",
    )
    manifest_path.write_text(manifest, encoding="utf-8")

    with pytest.raises(ValueError, match="checksum"):
        load_verified_public_source_stage_artifact(path)
