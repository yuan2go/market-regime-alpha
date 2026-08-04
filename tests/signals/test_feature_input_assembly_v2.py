from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from market_regime_alpha.core.identity import ArtifactId, ModelId
from market_regime_alpha.core.time import DecisionTime
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.evidence.envelope import ArtifactEnvelope, EvidenceAuthority
from market_regime_alpha.features.materialization_v2 import (
    load_verified_feature_bundle_v2,
)
from market_regime_alpha.research.candidate_discovery.contracts import (
    CandidateRecord,
    CandidateSelectionStatus,
    CandidateSet,
)
from market_regime_alpha.research.capital_evolution.contracts import (
    CapitalEvolutionState,
)
from market_regime_alpha.research.market_regime.contracts import MarketState
from market_regime_alpha.research.theme_rotation.contracts import RotationState
from market_regime_alpha.signals import (
    SIGNAL_MODEL_CONFIG_SCHEMA,
    SignalFamily,
    SignalModelConfig,
    SignalState,
)
from market_regime_alpha.signals.input_assembly import (
    SignalFactorName,
    SignalInputAssembler,
    SignalInputMappingConfiguration,
    SignalObservationV2,
    canonical_signal_input_mapping,
)
from market_regime_alpha.signals.v2 import (
    load_verified_signal_run_v2,
    publish_signal_run_v2,
    replay_signal_run_v2,
    run_signal_model_v2,
)
from tests.features.test_materialization_runner_v2 import (
    CREATED_AT,
    DECISION_TIME,
    _run as run_features,
)


UTC = timezone.utc
HASH = "sha256:" + "9" * 64


def _candidate_set(*, symbol: str = "600000.SH") -> CandidateSet:
    decision = DecisionTime(DECISION_TIME)
    record = CandidateRecord(
        symbol=symbol,
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
        reason_codes=("TEST_SELECTED",),
        source_feature_ids=(),
        input_artifact_ids=(),
    )
    payload = {
        "records": [record.to_canonical_dict()],
        "minimum_candidate_population": 1,
        "reason_codes": ["TEST_FIXTURE"],
    }
    envelope = ArtifactEnvelope.create(
        artifact_type="CANDIDATE_SET",
        artifact_payload=payload,
        decision_date=DECISION_TIME.date(),
        decision_time=decision,
        created_at=CREATED_AT,
        code_revision="test-revision",
        configuration_id=ArtifactId("candidate-config"),
        configuration_hash=canonical_hash({"candidate": "fixture"}),
        source_manifest_id=ArtifactId("source-manifest"),
        source_manifest_hash=HASH,
        input_artifact_ids=(),
        input_content_hashes=(),
        model_id=ModelId("candidate-model"),
        model_version="1.0.0",
        data_eligibility=DataEligibility.EXPLORATORY,
        evidence_authority=EvidenceAuthority.IMMUTABLE_CONTENT_ADDRESSED_ARTIFACT,
        status="RESEARCH_READY",
        reason_codes=("TEST_FIXTURE",),
        limitations=("TEST_ONLY",),
    )
    return CandidateSet(
        envelope=envelope,
        records=(record,),
        minimum_candidate_population=1,
        reason_codes=("TEST_FIXTURE",),
    )


def _signal_config() -> SignalModelConfig:
    return SignalModelConfig(
        profile_id="exploratory_a_share_1030_v1",
        model_id=ModelId("signal-five-confirmation-v1"),
        model_version="1.0.0-exploratory",
        decision_profile_id="a_share_1030_v1",
        decision_time_local="10:30",
        timezone_name="Asia/Shanghai",
        market_scope="A_SHARE",
        allowed_side="LONG_ONLY",
        signal_family=SignalFamily.TREND_CONTINUATION,
        price_action_min_return=0.001,
        volume_confirmation_min_ratio=0.9,
        trend_confirmation_min_return=0.001,
        vwap_min_relative_return=0.0,
        overheat_max_return=0.08,
        minimum_confirmations=3,
        scoring_method="EQUAL_CONFIRMATION_MEAN_V1",
        schema_version=SIGNAL_MODEL_CONFIG_SCHEMA,
    )


def _bundle(tmp_path: Path, *, include_minutes: bool = True):
    _, _, receipt = run_features(tmp_path, include_minutes=include_minutes)
    return load_verified_feature_bundle_v2(
        tmp_path / "features" / receipt.bundle_locator,
        artifact_root=tmp_path / "features" / "feature-artifacts",
    )


def test_mapping_and_v2_observation_are_content_addressed(tmp_path: Path) -> None:
    mapping = canonical_signal_input_mapping(
        effective_from=datetime(2026, 1, 1, tzinfo=UTC)
    )
    observations = SignalInputAssembler().assemble(
        candidate_set=_candidate_set(),
        feature_bundle=_bundle(tmp_path),
        configuration=mapping,
        decision_time=DecisionTime(DECISION_TIME),
    )

    assert SignalInputMappingConfiguration.from_canonical_dict(
        mapping.to_canonical_dict()
    ) == mapping
    assert len(observations) == 1
    observation = observations[0]
    assert SignalObservationV2.from_canonical_dict(
        observation.to_canonical_dict()
    ) == observation
    factors = {item.factor_name: item for item in observation.factors}
    assert all(item.value is not None for item in factors.values())
    assert factors[SignalFactorName.PRICE_ACTION_RETURN].source_output_id == "return_3"
    assert factors[SignalFactorName.VOLUME_RATIO].source_output_id == "amount_ratio_5"
    assert factors[SignalFactorName.TREND_RETURN].source_output_id == "price_vs_sma20_return"
    assert factors[SignalFactorName.PRICE_VS_VWAP_RETURN].source_output_id == "price_vs_vwap_return"
    assert factors[SignalFactorName.OVERHEAT_RETURN].source_output_id == "short_return"
    assert len({item.source_artifact_id for item in factors.values()}) >= 4


def test_missing_vwap_remains_per_factor_missing_without_zero_fill(tmp_path: Path) -> None:
    observation = SignalInputAssembler().assemble(
        candidate_set=_candidate_set(),
        feature_bundle=_bundle(tmp_path, include_minutes=False),
        configuration=canonical_signal_input_mapping(
            effective_from=datetime(2026, 1, 1, tzinfo=UTC)
        ),
        decision_time=DecisionTime(DECISION_TIME),
    )[0]
    vwap = next(
        item
        for item in observation.factors
        if item.factor_name is SignalFactorName.PRICE_VS_VWAP_RETURN
    )

    assert vwap.value is None
    assert "DATA_UNAVAILABLE_TIMEFRAME" in vwap.missing_reason_codes
    assert "FACTOR_PRICE_VS_VWAP_RETURN_MISSING" in observation.reason_codes


def test_observation_identity_tamper_and_candidate_scope_mismatch_fail_closed(
    tmp_path: Path,
) -> None:
    observation = SignalInputAssembler().assemble(
        candidate_set=_candidate_set(),
        feature_bundle=_bundle(tmp_path),
        configuration=canonical_signal_input_mapping(
            effective_from=datetime(2026, 1, 1, tzinfo=UTC)
        ),
        decision_time=DecisionTime(DECISION_TIME),
    )[0]
    payload = observation.to_canonical_dict()
    payload["content_hash"] = "sha256:" + "f" * 64
    with pytest.raises(ValueError, match="payload hash mismatch"):
        SignalObservationV2.from_canonical_dict(payload)

    with pytest.raises(ValueError, match="Candidate symbols"):
        SignalInputAssembler().assemble(
            candidate_set=_candidate_set(symbol="000001.SZ"),
            feature_bundle=_bundle(tmp_path / "mismatch"),
            configuration=canonical_signal_input_mapping(
                effective_from=datetime(2026, 1, 1, tzinfo=UTC)
            ),
            decision_time=DecisionTime(DECISION_TIME),
        )


def test_v2_signal_run_uses_shared_model_and_replays_from_feature_bundle(
    tmp_path: Path,
) -> None:
    candidate = _candidate_set()
    bundle = _bundle(tmp_path)
    mapping = canonical_signal_input_mapping(
        effective_from=datetime(2026, 1, 1, tzinfo=UTC)
    )
    observations = SignalInputAssembler().assemble(
        candidate_set=candidate,
        feature_bundle=bundle,
        configuration=mapping,
        decision_time=DecisionTime(DECISION_TIME),
    )
    signal = run_signal_model_v2(
        candidate_set=candidate,
        feature_bundle=bundle,
        mapping_configuration=mapping,
        signal_configuration=_signal_config(),
        observations=observations,
        decision_time=DecisionTime(DECISION_TIME),
        created_at=CREATED_AT,
        code_revision="test-revision",
    )

    assert signal.snapshots[0].signal_state in {
        SignalState.CONFIRMED_FOR_RESEARCH,
        SignalState.WATCH,
    }
    assert len(signal.snapshots[0].envelope.input_artifact_ids) >= 5
    package = publish_signal_run_v2(root=tmp_path / "signals", artifact=signal)
    assert load_verified_signal_run_v2(package).artifact == signal
    replayed = replay_signal_run_v2(package, feature_bundle=bundle)
    assert replayed.artifact == signal


def test_v2_signal_stays_data_insufficient_when_vwap_is_missing(tmp_path: Path) -> None:
    candidate = _candidate_set()
    bundle = _bundle(tmp_path, include_minutes=False)
    mapping = canonical_signal_input_mapping(
        effective_from=datetime(2026, 1, 1, tzinfo=UTC)
    )
    observations = SignalInputAssembler().assemble(
        candidate_set=candidate,
        feature_bundle=bundle,
        configuration=mapping,
        decision_time=DecisionTime(DECISION_TIME),
    )
    signal = run_signal_model_v2(
        candidate_set=candidate,
        feature_bundle=bundle,
        mapping_configuration=mapping,
        signal_configuration=_signal_config(),
        observations=observations,
        decision_time=DecisionTime(DECISION_TIME),
        created_at=CREATED_AT,
        code_revision="test-revision",
    )

    assert signal.snapshots[0].signal_state is SignalState.DATA_INSUFFICIENT
    assert any(
        factor.value is not None for factor in signal.observations[0].factors
    )
