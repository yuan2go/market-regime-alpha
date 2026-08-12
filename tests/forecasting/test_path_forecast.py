from __future__ import annotations

from datetime import datetime, timedelta
import json
from zoneinfo import ZoneInfo

import pytest

from market_regime_alpha.core.identity import ArtifactId, ModelId
from market_regime_alpha.core.time import AvailabilityTime, DecisionTime
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.evidence.envelope import ArtifactEnvelope, EvidenceAuthority
from market_regime_alpha.forecasting import (
    PATH_FORECAST_CONFIG_SCHEMA,
    PATH_FORECAST_SAMPLE_SCHEMA,
    CalibrationStatus,
    PathForecastConfig,
    PathForecastSample,
    PathForecastStatus,
    build_path_forecast,
    build_retrospective_path_forecast,
    load_verified_path_forecast,
    publish_path_forecast,
    replay_path_forecast,
)
from market_regime_alpha.signals.contracts import (
    ConfirmationState,
    SignalFamily,
    SignalSnapshot,
    SignalState,
)
from market_regime_alpha.strategies.entry import (
    EntryBarrierSpec,
    EntryPathObservationStatus,
    EntryPathReasonCode,
    build_entry_path_target_contract,
)


TZ = ZoneInfo("Asia/Shanghai")
DECISION = DecisionTime(datetime(2026, 7, 20, 14, 55, tzinfo=TZ))
CREATED = datetime(2026, 7, 20, 15, 0, tzinfo=TZ)
HASH = "sha256:" + "3" * 64


def _signal() -> SignalSnapshot:
    payload = {
        "symbol": "000001.SZ",
        "signal_family": SignalFamily.TREND_CONTINUATION.value,
        "signal_state": SignalState.CONFIRMED_FOR_RESEARCH.value,
        "price_action_state": ConfirmationState.CONFIRMED.value,
        "volume_confirmation_state": ConfirmationState.CONFIRMED.value,
        "trend_confirmation_state": ConfirmationState.CONFIRMED.value,
        "vwap_state": ConfirmationState.CONFIRMED.value,
        "overheat_state": ConfirmationState.CONFIRMED.value,
        "signal_score": 1.0,
        "confidence": 1.0,
        "reason_codes": ["SYNTHETIC_SIGNAL_FIXTURE"],
    }
    envelope = ArtifactEnvelope.create(
        artifact_type="SIGNAL_SNAPSHOT",
        artifact_payload=payload,
        decision_date=DECISION.value.date(),
        decision_time=DECISION,
        created_at=CREATED,
        code_revision="test-revision",
        configuration_id=ArtifactId("signal-config-test"),
        configuration_hash=canonical_hash({"fixture": "signal"}),
        source_manifest_id=ArtifactId("source-manifest-test"),
        source_manifest_hash=HASH,
        input_artifact_ids=(),
        input_content_hashes=(),
        model_id=ModelId("signal-model-test"),
        model_version="test-v1",
        data_eligibility=DataEligibility.EXPLORATORY,
        evidence_authority=EvidenceAuthority.IMMUTABLE_CONTENT_ADDRESSED_ARTIFACT,
        status=SignalState.CONFIRMED_FOR_RESEARCH.value,
        reason_codes=("SYNTHETIC_SIGNAL_FIXTURE",),
        limitations=("TEST_ONLY",),
    )
    return SignalSnapshot(
        envelope=envelope,
        symbol="000001.SZ",
        signal_family=SignalFamily.TREND_CONTINUATION,
        signal_state=SignalState.CONFIRMED_FOR_RESEARCH,
        price_action_state=ConfirmationState.CONFIRMED,
        volume_confirmation_state=ConfirmationState.CONFIRMED,
        trend_confirmation_state=ConfirmationState.CONFIRMED,
        vwap_state=ConfirmationState.CONFIRMED,
        overheat_state=ConfirmationState.CONFIRMED,
        signal_score=1.0,
        confidence=1.0,
        reason_codes=("SYNTHETIC_SIGNAL_FIXTURE",),
    )


def _config(minimum: int = 2) -> PathForecastConfig:
    target = build_entry_path_target_contract(
        EntryBarrierSpec(
            upper_return=0.03,
            lower_return=-0.02,
            horizon_sessions=5,
            price_adjustment_basis="RAW_UNADJUSTED_TRADABLE_PRICE_V1",
        )
    )
    return PathForecastConfig(
        profile_id="synthetic_path_profile_v1",
        model_id=ModelId("empirical-path-forecast-v1"),
        model_version="1.0.0-exploratory",
        decision_profile_id="a_share_1455_v1",
        decision_time_local="14:55",
        timezone_name="Asia/Shanghai",
        market_scope="A_SHARE",
        allowed_side="LONG_ONLY",
        target_contract=target,
        horizon_label="5_TRADING_SESSIONS",
        return_quantile_levels=(0.25, 0.5, 0.75),
        minimum_usable_samples=minimum,
        aggregation_method="EMPIRICAL_LINEAR_QUANTILE_MEAN_EXCURSION_V1",
        schema_version=PATH_FORECAST_CONFIG_SCHEMA,
    )


def _sample(index: int, **changes: object) -> PathForecastSample:
    config = _config()
    sample_decision = DecisionTime(
        datetime(2026, 7, 10 + index, 14, 55, tzinfo=TZ)
    )
    values: dict[str, object] = {
        "sample_id": ArtifactId(f"path-sample-{index}"),
        "source_artifact_id": ArtifactId(f"path-source-{index}"),
        "source_content_hash": f"sha256:{index}" + "4" * 63,
        "symbol": "000001.SZ",
        "target_id": config.target_contract.target_id,
        "sample_decision_time": sample_decision,
        "available_at": AvailabilityTime(sample_decision.value + timedelta(days=6)),
        "observation_status": EntryPathObservationStatus.AVAILABLE,
        "observation_reason_code": EntryPathReasonCode.OUTCOME_RESOLVED,
        "realized_mfe": 0.02 + index * 0.01,
        "realized_mae": -0.01 - index * 0.002,
        "realized_return": -0.01 + index * 0.02,
        "schema_version": PATH_FORECAST_SAMPLE_SCHEMA,
    }
    values.update(changes)
    return PathForecastSample(**values)  # type: ignore[arg-type]


def _build(samples: tuple[PathForecastSample, ...], minimum: int = 2):
    return build_path_forecast(
        signal_snapshot=_signal(),
        configuration=_config(minimum),
        samples=samples,
        decision_time=DECISION,
        created_at=CREATED,
        code_revision="test-revision",
    )


def test_path_forecast_reuses_target_and_never_emits_uncalibrated_probability() -> None:
    artifact = _build((_sample(1), _sample(2)))
    forecast = artifact.forecast

    assert forecast.target_id == _config().target_contract.target_id
    assert forecast.forecast_status is PathForecastStatus.AVAILABLE_FOR_RESEARCH
    assert forecast.calibration_status is CalibrationStatus.NOT_CALIBRATED
    assert forecast.expected_mfe is not None
    assert forecast.expected_mae is not None
    assert len(forecast.return_quantiles) == 3
    assert "probability_positive_return" not in forecast.artifact_payload()
    assert forecast.envelope.trading_authority == "TRADING_AUTHORITY_NOT_GRANTED"


def test_path_forecast_rejects_temporal_leakage() -> None:
    late = _sample(
        1,
        available_at=AvailabilityTime(DECISION.value + timedelta(minutes=1)),
    )

    with pytest.raises(ValueError, match="AvailabilityTime exceeds DecisionTime"):
        _build((late,), minimum=1)


def test_retrospective_forecast_uses_event_time_without_faking_availability() -> None:
    retrieved_later = _sample(
        1,
        available_at=AvailabilityTime(DECISION.value + timedelta(days=30)),
    )
    artifact = build_retrospective_path_forecast(
        signal_snapshot=_signal(),
        configuration=_config(minimum=1),
        samples=(retrieved_later,),
        sample_event_ends={
            retrieved_later.sample_id: DECISION.value - timedelta(days=1)
        },
        decision_time=DECISION,
        created_at=CREATED,
        code_revision="test-revision",
    )

    assert artifact.samples[0].available_at.value > DECISION.value
    assert artifact.forecast.forecast_status is PathForecastStatus.AVAILABLE_FOR_RESEARCH
    assert "RETROSPECTIVE_EVENT_TIME" in artifact.forecast.reason_codes
    assert "PIT_INCOMPLETE" in artifact.forecast.envelope.limitations


def test_retrospective_forecast_rejects_future_outcome_event() -> None:
    sample = _sample(1)

    with pytest.raises(ValueError, match="leaks a future outcome"):
        build_retrospective_path_forecast(
            signal_snapshot=_signal(),
            configuration=_config(minimum=1),
            samples=(sample,),
            sample_event_ends={sample.sample_id: DECISION.value + timedelta(minutes=1)},
            decision_time=DECISION,
            created_at=CREATED,
            code_revision="test-revision",
        )


def test_dual_touch_and_missing_future_bar_fail_closed() -> None:
    ambiguous = _sample(
        1,
        observation_status=EntryPathObservationStatus.AMBIGUOUS,
        observation_reason_code=EntryPathReasonCode.DAILY_BAR_DUAL_TOUCH_ORDER_UNRESOLVED,
        realized_mfe=None,
        realized_mae=None,
        realized_return=None,
    )
    missing = _sample(
        2,
        observation_status=EntryPathObservationStatus.MISSING,
        observation_reason_code=EntryPathReasonCode.FUTURE_DAILY_BAR_MISSING,
        realized_mfe=None,
        realized_mae=None,
        realized_return=None,
    )

    forecast = _build((ambiguous, missing), minimum=1).forecast
    assert forecast.forecast_status is PathForecastStatus.DATA_INSUFFICIENT
    assert forecast.return_quantiles == ()
    assert "DAILY_BAR_DUAL_TOUCH_ORDER_UNRESOLVED" in forecast.reason_codes
    assert "FUTURE_DAILY_BAR_MISSING" in forecast.reason_codes


def test_path_forecast_artifact_reader_and_replay_are_deterministic(tmp_path) -> None:
    artifact = _build((_sample(1), _sample(2)))
    path = publish_path_forecast(root=tmp_path, artifact=artifact)

    assert load_verified_path_forecast(path).artifact == artifact
    assert replay_path_forecast(path).artifact == artifact
    assert publish_path_forecast(root=tmp_path, artifact=artifact) == path

    artifact_path = path / "artifact.json"
    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    payload["forecast"]["expected_mfe"] = 99.0
    artifact_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="checksum mismatch"):
        load_verified_path_forecast(path)
