from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from market_regime_alpha.core.identity import ArtifactId, OpportunityId, ThesisId
from market_regime_alpha.decision import (
    DecisionEvidenceReference,
    InvalidationCondition,
    InvalidationKind,
    ThesisState,
    TradingThesis,
)
from market_regime_alpha.decision.thesis import TRADING_THESIS_SCHEMA
import market_regime_alpha.execution  # noqa: F401  # initialize existing lifecycle package order
from market_regime_alpha.forecasting import CalibrationStatus, PathForecastStatus
from market_regime_alpha.position import (
    CapitalRuleScope,
    InvalidationRuleType,
    ManualEvidenceRequiredRule,
    MarketStateInRule,
    PriceBelowRule,
    SignalStateInRule,
    ThesisHealthRuleConfiguration,
    ThesisHealthSupportState,
    ThesisInvalidationRuleSet,
    TimeAfterRule,
    TradePermissionInRule,
    invalidation_rule_from_canonical_dict,
)
from market_regime_alpha.research.capital_evolution import CapitalEvolutionState
from market_regime_alpha.research.market_regime import MarketState, TradePermission
from market_regime_alpha.research.theme_rotation import RotationState
from market_regime_alpha.signals import ConfirmationState, SignalState


TZ = ZoneInfo("Asia/Shanghai")
NOW = datetime(2026, 8, 4, 14, 55, tzinfo=TZ)


def _reference(name: str, artifact_type: str) -> DecisionEvidenceReference:
    return DecisionEvidenceReference(
        artifact_type=artifact_type,
        artifact_id=ArtifactId(name),
        content_hash="sha256:" + "a" * 64,
        status="VERIFIED_EXPLORATORY",
    )


def _thesis() -> TradingThesis:
    conditions = (
        InvalidationCondition(
            condition_id="manual-stop",
            kind=InvalidationKind.MANUAL,
            description="explicit operator invalidation",
            reason_code="MANUAL_INVALIDATION",
        ),
        InvalidationCondition(
            condition_id="market-stop",
            kind=InvalidationKind.MARKET_REGIME,
            description="market condition defined outside natural language",
            reason_code="MARKET_INVALIDATION",
        ),
        InvalidationCondition(
            condition_id="price-stop",
            kind=InvalidationKind.PRICE,
            description="price threshold supplied by typed rule",
            reason_code="PRICE_INVALIDATION",
        ),
        InvalidationCondition(
            condition_id="signal-stop",
            kind=InvalidationKind.SIGNAL,
            description="signal state supplied by typed rule",
            reason_code="SIGNAL_INVALIDATION",
        ),
        InvalidationCondition(
            condition_id="time-stop",
            kind=InvalidationKind.TIME,
            description="exact TradingThesis time invalidation",
            reason_code="TIME_INVALIDATION",
        ),
    )
    return TradingThesis(
        schema_version=TRADING_THESIS_SCHEMA,
        thesis_id=ThesisId("thesis-h5-rules"),
        opportunity_id=OpportunityId("opportunity-h5-rules"),
        source_opportunity_version=0,
        symbol="000001.SZ",
        supporting_evidence=(
            _reference("candidate-creation", "CANDIDATE_SET"),
            _reference("path-creation", "PATH_FORECAST"),
            _reference("signal-creation", "SIGNAL_SNAPSHOT"),
        ),
        invalidation_conditions=conditions,
        time_invalidation=NOW + timedelta(days=5),
        state=ThesisState.APPROVED,
        version=0,
        approved_by="approver-a",
        approval_reason="explicit H5 fixture",
        created_at=NOW - timedelta(days=1),
        updated_at=NOW - timedelta(days=1),
        last_actor="approver-a",
        last_reason="explicit H5 fixture",
    )


def _rules(thesis: TradingThesis) -> tuple[object, ...]:
    return (
        ManualEvidenceRequiredRule(condition_id="manual-stop"),
        MarketStateInRule(
            condition_id="market-stop",
            states=(MarketState.EXTREME_RISK,),
        ),
        PriceBelowRule(condition_id="price-stop", threshold=8.5),
        SignalStateInRule(
            condition_id="signal-stop",
            states=(SignalState.INACTIVE,),
        ),
        TimeAfterRule(
            condition_id="time-stop",
            threshold=thesis.time_invalidation,
        ),
    )


def _mapping(enum_type, supported, weakening, insufficient):
    return tuple(
        (
            item,
            ThesisHealthSupportState.SUPPORTED
            if item in supported
            else ThesisHealthSupportState.WEAKENING
            if item in weakening
            else ThesisHealthSupportState.DATA_INSUFFICIENT,
        )
        for item in enum_type
    )


def _configuration() -> ThesisHealthRuleConfiguration:
    return ThesisHealthRuleConfiguration.create(
        profile_id="h5-rules-test-v1",
        builder_revision="h5-builder-v1",
        maximum_market_age_seconds=600.0,
        maximum_theme_age_seconds=600.0,
        maximum_capital_age_seconds=600.0,
        maximum_candidate_age_seconds=600.0,
        maximum_signal_age_seconds=300.0,
        maximum_path_age_seconds=600.0,
        maximum_price_age_seconds=120.0,
        maximum_price_research_skew_seconds=600.0,
        maximum_prior_observation_age_seconds=86_400.0,
        market_state_mapping=_mapping(
            MarketState,
            {MarketState.RISK_ON, MarketState.RISK_NEUTRAL},
            {MarketState.RISK_OFF, MarketState.EXTREME_RISK},
            {MarketState.DATA_INSUFFICIENT},
        ),
        trade_permission_mapping=_mapping(
            TradePermission,
            {TradePermission.ALLOW},
            {TradePermission.RESTRICT},
            {TradePermission.PROHIBIT},
        ),
        signal_state_mapping=_mapping(
            SignalState,
            {SignalState.CONFIRMED_FOR_RESEARCH},
            {SignalState.WATCH, SignalState.INACTIVE},
            {SignalState.DATA_INSUFFICIENT},
        ),
        confirmation_state_mapping=_mapping(
            ConfirmationState,
            {ConfirmationState.CONFIRMED},
            {ConfirmationState.UNCONFIRMED, ConfirmationState.CONTRADICTED},
            {ConfirmationState.UNKNOWN},
        ),
        path_status_mapping=_mapping(
            PathForecastStatus,
            {PathForecastStatus.AVAILABLE_FOR_RESEARCH},
            set(),
            {PathForecastStatus.DATA_INSUFFICIENT},
        ),
        path_calibration_mapping=_mapping(
            CalibrationStatus,
            {CalibrationStatus.NOT_CALIBRATED},
            {CalibrationStatus.CALIBRATED_EXPLORATORY},
            {CalibrationStatus.DATA_INSUFFICIENT},
        ),
        theme_state_mapping=_mapping(
            RotationState,
            {
                RotationState.STARTING,
                RotationState.STRENGTHENING,
                RotationState.LEADING,
            },
            {
                RotationState.DIVERGING,
                RotationState.WEAKENING,
                RotationState.FAILED,
            },
            {RotationState.DATA_INSUFFICIENT},
        ),
        capital_state_mapping=_mapping(
            CapitalEvolutionState,
            {
                CapitalEvolutionState.ACCUMULATION,
                CapitalEvolutionState.IGNITION,
                CapitalEvolutionState.DIFFUSION,
                CapitalEvolutionState.ACCELERATION,
            },
            {
                CapitalEvolutionState.DORMANT,
                CapitalEvolutionState.DIVERGENCE,
                CapitalEvolutionState.EXHAUSTION,
                CapitalEvolutionState.COLLAPSE,
            },
            {CapitalEvolutionState.DATA_INSUFFICIENT},
        ),
        minimum_signal_score=0.2,
        minimum_signal_confidence=0.8,
        minimum_path_usable_sample_count=20,
        minimum_path_expected_mfe=0.02,
        minimum_path_expected_mae=-0.05,
        minimum_path_reward_risk_ratio=1.5,
    )


def test_typed_rules_have_strict_canonical_round_trip() -> None:
    thesis = _thesis()
    for rule in _rules(thesis):
        restored = invalidation_rule_from_canonical_dict(
            rule.to_canonical_dict()  # type: ignore[attr-defined]
        )
        assert restored == rule

    assert PriceBelowRule("price-stop", 8.5).rule_type is InvalidationRuleType.PRICE_BELOW
    assert CapitalRuleScope.BOTH.value == "BOTH"


def test_rule_set_binds_every_thesis_condition_exactly_once() -> None:
    thesis = _thesis()
    rule_set = ThesisInvalidationRuleSet.create(
        thesis_id=thesis.thesis_id,
        thesis_version=thesis.version,
        rules=_rules(thesis),
    )

    rule_set.validate_for(thesis)
    assert ThesisInvalidationRuleSet.from_canonical_dict(
        rule_set.to_canonical_dict()
    ) == rule_set


@pytest.mark.parametrize("mutation", ("missing", "extra", "duplicate"))
def test_rule_set_rejects_missing_extra_or_duplicate_condition(
    mutation: str,
) -> None:
    thesis = _thesis()
    rules = list(_rules(thesis))
    if mutation == "missing":
        rules.pop()
    elif mutation == "extra":
        rules.append(PriceBelowRule("not-in-thesis", 7.0))
    else:
        rules.append(PriceBelowRule("price-stop", 7.0))

    with pytest.raises(ValueError, match="condition"):
        ThesisInvalidationRuleSet.create(
            thesis_id=thesis.thesis_id,
            thesis_version=thesis.version,
            rules=tuple(rules),
        ).validate_for(thesis)


def test_rule_set_rejects_kind_mismatch_and_time_drift() -> None:
    thesis = _thesis()
    wrong_kind = tuple(
        TradePermissionInRule(
            condition_id="price-stop",
            states=(TradePermission.PROHIBIT,),
        )
        if getattr(item, "condition_id") == "price-stop"
        else item
        for item in _rules(thesis)
    )
    with pytest.raises(ValueError, match="kind"):
        ThesisInvalidationRuleSet.create(
            thesis_id=thesis.thesis_id,
            thesis_version=thesis.version,
            rules=wrong_kind,
        ).validate_for(thesis)

    wrong_time = tuple(
        TimeAfterRule(
            condition_id="time-stop",
            threshold=thesis.time_invalidation + timedelta(seconds=1),
        )
        if getattr(item, "condition_id") == "time-stop"
        else item
        for item in _rules(thesis)
    )
    with pytest.raises(ValueError, match="time_invalidation"):
        ThesisInvalidationRuleSet.create(
            thesis_id=thesis.thesis_id,
            thesis_version=thesis.version,
            rules=wrong_time,
        ).validate_for(thesis)


def test_unknown_typed_rule_is_rejected() -> None:
    with pytest.raises(ValueError, match="unknown invalidation rule"):
        invalidation_rule_from_canonical_dict(
            {"rule_type": "DESCRIPTION_GUESS", "condition_id": "price-stop"}
        )


def test_configuration_has_content_identity_and_exact_enum_coverage() -> None:
    configuration = _configuration()
    restored = ThesisHealthRuleConfiguration.from_canonical_dict(
        configuration.to_canonical_dict()
    )

    assert restored == configuration
    assert configuration.builder_revision == "h5-builder-v1"
    assert configuration.maximum_price_age_seconds == 120.0
    assert configuration.maximum_price_research_skew_seconds == 600.0

    with pytest.raises(ValueError, match="exactly cover"):
        replace(
            configuration,
            market_state_mapping=configuration.market_state_mapping[:-1],
        )


def test_configuration_identity_and_hash_tamper_are_rejected() -> None:
    payload = _configuration().to_canonical_dict()
    payload["configuration_hash"] = "sha256:" + "f" * 64
    with pytest.raises(ValueError, match="identity"):
        ThesisHealthRuleConfiguration.from_canonical_dict(payload)

    payload = _configuration().to_canonical_dict()
    payload["configuration_id"] = "thesis-health-config-forged"
    with pytest.raises(ValueError, match="identity"):
        ThesisHealthRuleConfiguration.from_canonical_dict(payload)


def test_rule_set_identity_tamper_is_rejected() -> None:
    thesis = _thesis()
    payload = ThesisInvalidationRuleSet.create(
        thesis_id=thesis.thesis_id,
        thesis_version=thesis.version,
        rules=_rules(thesis),
    ).to_canonical_dict()
    payload["rule_set_hash"] = "sha256:" + "e" * 64

    with pytest.raises(ValueError, match="identity"):
        ThesisInvalidationRuleSet.from_canonical_dict(payload)
