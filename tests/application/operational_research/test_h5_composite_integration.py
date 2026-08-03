from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from market_regime_alpha.application.research_layer.runner import (
    PlatformResearchRunner,
)
from market_regime_alpha.core.identity import (
    ArtifactId,
    ModelId,
    OpportunityId,
    TargetId,
    ThesisId,
)
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.decision import (
    DecisionEvidenceReference,
    DecisionModelReference,
    InvalidationCondition,
    InvalidationKind,
    OpportunityState,
    ThesisState,
    TradingOpportunity,
    TradingThesis,
)
from market_regime_alpha.decision.opportunity import TRADING_OPPORTUNITY_SCHEMA
from market_regime_alpha.decision.thesis import TRADING_THESIS_SCHEMA
from market_regime_alpha.evidence import ArtifactEnvelope, EvidenceAuthority
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.forecasting import (
    CalibrationStatus,
    PathForecast,
    PathForecastStatus,
)
import market_regime_alpha.execution  # noqa: F401  # established package init order
from market_regime_alpha.position.thesis_health import (
    ThesisHealthInputBundle,
    ThesisHealthObservationBuilder,
    ThesisInvalidationRuleSet,
    TimeAfterRule,
)
from market_regime_alpha.research.platform_v2.configs import (
    default_research_pipeline_config,
)
from market_regime_alpha.signals import (
    ConfirmationState,
    SignalFamily,
    SignalSnapshot,
    SignalState,
)
from tests.position.thesis_health_fixtures import health_configuration
from tests.research.platform_v2.test_composite_input_v2 import _v2_inputs
from tests.daily_decision.conftest import DailyDecisionFixture


def _evidence(envelope: ArtifactEnvelope) -> DecisionEvidenceReference:
    return DecisionEvidenceReference(
        artifact_type=envelope.artifact_type,
        artifact_id=envelope.artifact_id,
        content_hash=envelope.content_hash,
        status=envelope.status,
    )


def _model(envelope: ArtifactEnvelope) -> DecisionModelReference:
    assert envelope.model_id is not None and envelope.model_version is not None
    return DecisionModelReference(
        model_id=envelope.model_id,
        model_version=envelope.model_version,
        configuration_id=envelope.configuration_id,
        configuration_hash=envelope.configuration_hash,
    )


def test_h6_operational_package_is_consumable_by_h5_without_authority_inflation(
    tmp_path: Path,
    daily_decision_fixture: DailyDecisionFixture,
) -> None:
    inputs, _, composite = _v2_inputs(
        tmp_path / "h6", daily_decision_fixture
    )
    research = PlatformResearchRunner().run(
        inputs=inputs,
        configuration=default_research_pipeline_config(),
        output_root=tmp_path / "research",
        code_revision="h6-h5-integration",
    ).artifact
    candidate_record = next(
        item
        for item in research.candidate_set.records
        if item.primary_theme_id is not None
    )
    symbol = candidate_record.symbol
    decision_time = research.envelope.decision_time
    created_at = research.envelope.created_at

    signal_values = {
        "symbol": symbol,
        "signal_family": SignalFamily.TREND_CONTINUATION,
        "signal_state": SignalState.CONFIRMED_FOR_RESEARCH,
        "price_action_state": ConfirmationState.CONFIRMED,
        "volume_confirmation_state": ConfirmationState.CONFIRMED,
        "trend_confirmation_state": ConfirmationState.CONFIRMED,
        "vwap_state": ConfirmationState.CONFIRMED,
        "overheat_state": ConfirmationState.CONFIRMED,
        "signal_score": 0.8,
        "confidence": 1.0,
        "reason_codes": ("H6_H5_INTEGRATION_SIGNAL",),
    }
    signal_payload = {
        name: (
            value.value
            if hasattr(value, "value")
            else list(value)
            if isinstance(value, tuple)
            else value
        )
        for name, value in signal_values.items()
    }
    signal_envelope = ArtifactEnvelope.create(
        artifact_type="SIGNAL_SNAPSHOT",
        artifact_payload=signal_payload,
        decision_date=decision_time.value.date(),
        decision_time=decision_time,
        created_at=created_at,
        code_revision="h6-h5-integration",
        configuration_id=ArtifactId("h6-h5-signal-config"),
        configuration_hash=canonical_hash({"config": "h6-h5-signal"}),
        source_manifest_id=research.envelope.source_manifest_id,
        source_manifest_hash=research.envelope.source_manifest_hash,
        input_artifact_ids=(research.candidate_set.envelope.artifact_id,),
        input_content_hashes=(research.candidate_set.envelope.content_hash,),
        model_id=ModelId("h6-h5-signal-model"),
        model_version="1.0.0-exploratory",
        data_eligibility=DataEligibility.EXPLORATORY,
        evidence_authority=EvidenceAuthority.IMMUTABLE_CONTENT_ADDRESSED_ARTIFACT,
        status=SignalState.CONFIRMED_FOR_RESEARCH.value,
        reason_codes=("H6_H5_INTEGRATION_SIGNAL",),
        limitations=("FORMAL_OOS_ALPHA_NOT_ESTABLISHED",),
    )
    signal = SignalSnapshot(envelope=signal_envelope, **signal_values)  # type: ignore[arg-type]

    path_values = {
        "symbol": symbol,
        "target_id": TargetId("h6-h5-path-target"),
        "forecast_horizon": "next-session-path",
        "upper_barrier_return": 0.08,
        "lower_barrier_return": -0.04,
        "expected_mfe": 0.06,
        "expected_mae": -0.03,
        "return_quantiles": (),
        "calibration_status": CalibrationStatus.NOT_CALIBRATED,
        "forecast_status": PathForecastStatus.AVAILABLE_FOR_RESEARCH,
        "usable_sample_count": 100,
        "excluded_sample_count": 0,
        "reason_codes": ("H6_H5_INTEGRATION_PATH",),
    }
    path_payload = {
        "symbol": symbol,
        "target_id": str(path_values["target_id"]),
        "forecast_horizon": path_values["forecast_horizon"],
        "upper_barrier_return": path_values["upper_barrier_return"],
        "lower_barrier_return": path_values["lower_barrier_return"],
        "expected_mfe": path_values["expected_mfe"],
        "expected_mae": path_values["expected_mae"],
        "return_quantiles": [],
        "calibration_status": CalibrationStatus.NOT_CALIBRATED.value,
        "forecast_status": PathForecastStatus.AVAILABLE_FOR_RESEARCH.value,
        "usable_sample_count": 100,
        "excluded_sample_count": 0,
        "reason_codes": ["H6_H5_INTEGRATION_PATH"],
    }
    path_envelope = ArtifactEnvelope.create(
        artifact_type="PATH_FORECAST",
        artifact_payload=path_payload,
        decision_date=decision_time.value.date(),
        decision_time=decision_time,
        created_at=created_at,
        code_revision="h6-h5-integration",
        configuration_id=ArtifactId("h6-h5-path-config"),
        configuration_hash=canonical_hash({"config": "h6-h5-path"}),
        source_manifest_id=research.envelope.source_manifest_id,
        source_manifest_hash=research.envelope.source_manifest_hash,
        input_artifact_ids=(signal.envelope.artifact_id,),
        input_content_hashes=(signal.envelope.content_hash,),
        model_id=ModelId("h6-h5-path-model"),
        model_version="1.0.0-exploratory",
        data_eligibility=DataEligibility.EXPLORATORY,
        evidence_authority=EvidenceAuthority.IMMUTABLE_CONTENT_ADDRESSED_ARTIFACT,
        status=PathForecastStatus.AVAILABLE_FOR_RESEARCH.value,
        reason_codes=("H6_H5_INTEGRATION_PATH",),
        limitations=("FORMAL_OOS_ALPHA_NOT_ESTABLISHED",),
    )
    path = PathForecast(envelope=path_envelope, **path_values)  # type: ignore[arg-type]

    opportunity = TradingOpportunity(
        schema_version=TRADING_OPPORTUNITY_SCHEMA,
        opportunity_id=OpportunityId("opportunity-h6-h5-integration"),
        symbol=symbol,
        candidate_set=_evidence(research.candidate_set.envelope),
        signal_snapshot=_evidence(signal.envelope),
        path_forecast=_evidence(path.envelope),
        decision_time=decision_time,
        signal_model=_model(signal.envelope),
        forecast_model=_model(path.envelope),
        valid_until=decision_time.value + timedelta(days=2),
        state=OpportunityState.CONFIRMED_TO_THESIS,
        version=1,
        created_at=created_at,
        created_by="h6-h5-test",
        creation_reason="verified H6 integration evidence",
        updated_at=created_at + timedelta(seconds=1),
        last_actor="h6-h5-test",
        last_reason="confirmed to Thesis",
        reason_codes=("H6_COMPOSITE_EVIDENCE_BOUND",),
    )
    assessed_at = created_at + timedelta(seconds=2)
    condition = InvalidationCondition(
        condition_id="time-stop",
        kind=InvalidationKind.TIME,
        description="typed time invalidation",
        reason_code="TIME_INVALIDATION",
    )
    thesis = TradingThesis(
        schema_version=TRADING_THESIS_SCHEMA,
        thesis_id=ThesisId("thesis-h6-h5-integration"),
        opportunity_id=opportunity.opportunity_id,
        source_opportunity_version=0,
        symbol=symbol,
        supporting_evidence=tuple(
            sorted(
                (
                    opportunity.candidate_set,
                    opportunity.signal_snapshot,
                    opportunity.path_forecast,
                ),
                key=lambda item: str(item.artifact_id),
            )
        ),
        invalidation_conditions=(condition,),
        time_invalidation=assessed_at + timedelta(days=1),
        state=ThesisState.APPROVED,
        version=0,
        approved_by="h6-h5-test",
        approval_reason="verified H6 integration evidence",
        created_at=opportunity.updated_at,
        updated_at=opportunity.updated_at,
        last_actor="h6-h5-test",
        last_reason="approved for H5 observation",
    )
    rule_set = ThesisInvalidationRuleSet.create(
        thesis_id=thesis.thesis_id,
        thesis_version=thesis.version,
        rules=(TimeAfterRule("time-stop", thesis.time_invalidation),),
    )
    bundle = ThesisHealthInputBundle.create(
        thesis=thesis,
        opportunity=opportunity,
        market_regime=research.market_regime,
        theme_rotation=research.theme_rotation,
        capital_evolution=research.capital_evolution,
        candidate_set=research.candidate_set,
        signal_snapshot=signal,
        path_forecast=path,
        price_snapshot=inputs.decision_price_snapshot,
        configuration=health_configuration(),
        rule_set=rule_set,
        manual_evidence=(),
        prior_observation=None,
        assessed_at=assessed_at,
        actor="h6-h5-test",
        reason="prove H6 inputs are consumable by H5",
    )
    observation = ThesisHealthObservationBuilder().build(bundle)

    assert observation.candidate_set_id == research.candidate_set.envelope.artifact_id
    assert composite.manifest.manifest_id in (
        research.candidate_set.envelope.input_artifact_ids
    )
    assert bundle.replay_boundary == "H5_PRIVATE_REPLAY_BUNDLE"
    assert bundle.h6_authority == "NOT_H6_AUTHORITY"
    assert observation.formal_oos_alpha == "FORMAL_OOS_ALPHA_NOT_ESTABLISHED"
    assert observation.trading_authority == "TRADING_AUTHORITY_NOT_GRANTED"
