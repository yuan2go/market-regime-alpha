from __future__ import annotations

from datetime import datetime, timedelta
import json
from pathlib import Path
import subprocess
import sys
from zoneinfo import ZoneInfo

import pytest

from market_regime_alpha.core.identity import ArtifactId, ModelId
from market_regime_alpha.core.time import AvailabilityTime, DecisionTime
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.evidence.envelope import ArtifactEnvelope, EvidenceAuthority
from market_regime_alpha.research.candidate_discovery.contracts import (
    CandidateRecord,
    CandidateSelectionStatus,
    CandidateSet,
)
from market_regime_alpha.research.capital_evolution.contracts import CapitalEvolutionState
from market_regime_alpha.research.market_regime.contracts import MarketState
from market_regime_alpha.research.theme_rotation.contracts import RotationState
from market_regime_alpha.signals import (
    SIGNAL_MODEL_CONFIG_SCHEMA,
    SIGNAL_OBSERVATION_SCHEMA,
    ConfirmationState,
    SignalFamily,
    SignalModelConfig,
    SignalObservation,
    SignalState,
    load_verified_signal_run,
    publish_signal_run,
    replay_signal_run,
    run_signal_model,
)


TZ = ZoneInfo("Asia/Shanghai")
DECISION = DecisionTime(datetime(2026, 7, 20, 14, 55, tzinfo=TZ))
CREATED = datetime(2026, 7, 20, 15, 0, tzinfo=TZ)
HASH = "sha256:" + "1" * 64


def _candidate_set() -> CandidateSet:
    record = CandidateRecord(
        symbol="000001.SZ",
        primary_theme_id="theme-bank",
        supporting_theme_ids=(),
        market_regime_status=MarketState.RISK_ON,
        theme_rotation_state=RotationState.STRENGTHENING,
        capital_evolution_state=CapitalEvolutionState.IGNITION,
        market_regime_score=0.5,
        theme_score=0.4,
        capital_evolution_score=0.3,
        candidate_discovery_score=0.6,
        rank=1,
        selection_status=CandidateSelectionStatus.SELECTED,
        reason_codes=("SYNTHETIC_SELECTED",),
        source_feature_ids=(),
        input_artifact_ids=(),
    )
    payload = {
        "records": [record.to_canonical_dict()],
        "minimum_candidate_population": 1,
        "reason_codes": ["SYNTHETIC_FIXTURE"],
    }
    envelope = ArtifactEnvelope.create(
        artifact_type="CANDIDATE_SET",
        artifact_payload=payload,
        decision_date=DECISION.value.date(),
        decision_time=DECISION,
        created_at=CREATED,
        code_revision="test-revision",
        configuration_id=ArtifactId("candidate-config-test"),
        configuration_hash=canonical_hash({"fixture": "candidate"}),
        source_manifest_id=ArtifactId("source-manifest-test"),
        source_manifest_hash=HASH,
        input_artifact_ids=(),
        input_content_hashes=(),
        model_id=ModelId("candidate-model-test"),
        model_version="test-v1",
        data_eligibility=DataEligibility.EXPLORATORY,
        evidence_authority=EvidenceAuthority.IMMUTABLE_CONTENT_ADDRESSED_ARTIFACT,
        status="RESEARCH_READY",
        reason_codes=("SYNTHETIC_FIXTURE",),
        limitations=("TEST_ONLY",),
    )
    return CandidateSet(
        envelope=envelope,
        records=(record,),
        minimum_candidate_population=1,
        reason_codes=("SYNTHETIC_FIXTURE",),
    )


def _config() -> SignalModelConfig:
    return SignalModelConfig(
        profile_id="exploratory_a_share_1455_v1",
        model_id=ModelId("signal-five-confirmation-v1"),
        model_version="1.0.0-exploratory",
        decision_profile_id="a_share_1455_v1",
        decision_time_local="14:55",
        timezone_name="Asia/Shanghai",
        market_scope="A_SHARE",
        allowed_side="LONG_ONLY",
        signal_family=SignalFamily.TREND_CONTINUATION,
        price_action_min_return=0.01,
        volume_confirmation_min_ratio=1.2,
        trend_confirmation_min_return=0.02,
        vwap_min_relative_return=0.0,
        overheat_max_return=0.08,
        minimum_confirmations=3,
        scoring_method="EQUAL_CONFIRMATION_MEAN_V1",
        schema_version=SIGNAL_MODEL_CONFIG_SCHEMA,
    )


def _observation(**changes: object) -> SignalObservation:
    values: dict[str, object] = {
        "symbol": "000001.SZ",
        "source_artifact_id": ArtifactId("signal-source-test"),
        "source_content_hash": "sha256:" + "2" * 64,
        "availability_time": AvailabilityTime(
            datetime(2026, 7, 20, 14, 54, tzinfo=TZ)
        ),
        "price_action_return": 0.02,
        "volume_ratio": 1.4,
        "trend_return": 0.03,
        "price_vs_vwap_return": 0.01,
        "overheat_return": 0.04,
        "reason_codes": (),
        "schema_version": SIGNAL_OBSERVATION_SCHEMA,
    }
    values.update(changes)
    return SignalObservation(**values)  # type: ignore[arg-type]


def _run(observation: SignalObservation | None = None):
    return run_signal_model(
        candidate_set=_candidate_set(),
        configuration=_config(),
        observations=(observation or _observation(),),
        decision_time=DECISION,
        created_at=CREATED,
        code_revision="test-revision",
    )


def test_five_factor_signal_is_research_confirmation_not_trade_action() -> None:
    artifact = _run()
    snapshot = artifact.snapshots[0]

    assert snapshot.signal_state is SignalState.CONFIRMED_FOR_RESEARCH
    assert snapshot.price_action_state is ConfirmationState.CONFIRMED
    assert snapshot.volume_confirmation_state is ConfirmationState.CONFIRMED
    assert snapshot.trend_confirmation_state is ConfirmationState.CONFIRMED
    assert snapshot.vwap_state is ConfirmationState.CONFIRMED
    assert snapshot.overheat_state is ConfirmationState.CONFIRMED
    assert "probability" not in snapshot.artifact_payload()
    assert "action" not in snapshot.artifact_payload()
    assert artifact.envelope.trading_authority == "TRADING_AUTHORITY_NOT_GRANTED"


def test_missing_metric_fails_closed_to_data_insufficient() -> None:
    snapshot = _run(
        _observation(volume_ratio=None, reason_codes=("VOLUME_MISSING",))
    ).snapshots[0]

    assert snapshot.signal_state is SignalState.DATA_INSUFFICIENT
    assert snapshot.signal_score is None
    assert snapshot.volume_confirmation_state is ConfirmationState.UNKNOWN


def test_signal_rejects_temporal_leakage() -> None:
    late = _observation(
        availability_time=AvailabilityTime(DECISION.value + timedelta(minutes=1))
    )

    with pytest.raises(ValueError, match="AvailabilityTime exceeds DecisionTime"):
        _run(late)


def test_signal_artifact_reader_and_replay_are_deterministic(tmp_path) -> None:
    artifact = _run()
    path = publish_signal_run(root=tmp_path, artifact=artifact)

    assert load_verified_signal_run(path).artifact == artifact
    assert replay_signal_run(path).artifact == artifact
    assert publish_signal_run(root=tmp_path, artifact=artifact) == path
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/run_signal_path_research.py",
            "replay-signal",
            "--artifact",
            str(path),
        ],
        cwd=Path(__file__).parents[2],
        check=True,
        capture_output=True,
        text=True,
    )
    assert str(path.resolve()) in completed.stdout

    artifact_path = path / "artifact.json"
    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    payload["snapshots"][0]["confidence"] = 0.1
    artifact_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="checksum mismatch"):
        load_verified_signal_run(path)
