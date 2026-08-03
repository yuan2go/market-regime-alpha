from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from market_regime_alpha.core.identity import (
    ArtifactId,
    ModelId,
    OpportunityId,
    ProviderId,
    TargetId,
    ThesisId,
)
from market_regime_alpha.core.time import AvailabilityTime, DecisionTime
from market_regime_alpha.daily_decision import (
    DecisionPriceObservation,
    DecisionPriceQuality,
    DecisionPriceSnapshot,
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
from market_regime_alpha.forecasting import (
    CalibrationStatus,
    PathForecast,
    PathForecastStatus,
)
from market_regime_alpha.position import (
    CapitalEvolutionStateInRule,
    CapitalRuleScope,
    ManualEvidenceRequiredRule,
    MarketStateInRule,
    PriceBelowRule,
    SignalStateInRule,
    ThesisHealthRuleConfiguration,
    ThesisHealthSupportState,
    ThesisInvalidationRuleSet,
    ThemeRotationStateInRule,
    TimeAfterRule,
)
from market_regime_alpha.research.candidate_discovery.contracts import (
    CandidateRecord,
    CandidateSelectionStatus,
    CandidateSet,
)
from market_regime_alpha.research.capital_evolution.contracts import (
    CapitalEvolutionSnapshot,
    CapitalEvolutionState,
    SymbolCapitalEvolution,
    ThemeCapitalEvolution,
)
from market_regime_alpha.research.market_regime.contracts import (
    MarketBreadth,
    MarketDirection,
    MarketLiquidity,
    MarketRegimeSnapshot,
    MarketState,
    MarketVolatility,
    RiskAppetite,
    TradePermission,
)
from market_regime_alpha.research.theme_rotation.contracts import (
    RotationState,
    ThemeRotationItem,
    ThemeRotationSnapshot,
)
from market_regime_alpha.signals import (
    ConfirmationState,
    SignalFamily,
    SignalSnapshot,
    SignalState,
)


TZ = ZoneInfo("Asia/Shanghai")
RESEARCH_AT = datetime(2026, 8, 4, 14, 50, tzinfo=TZ)
ASSESSED_AT = datetime(2026, 8, 4, 14, 55, tzinfo=TZ)
SYMBOL = "000001.SZ"
THEME_ID = "theme-bank"
SOURCE_MANIFEST_ID = ArtifactId("source-manifest-h5-fixture")
SOURCE_MANIFEST_HASH = "sha256:" + "1" * 64


@dataclass(frozen=True, slots=True)
class H5Fixture:
    thesis: TradingThesis
    opportunity: TradingOpportunity
    market: MarketRegimeSnapshot
    theme: ThemeRotationSnapshot
    capital: CapitalEvolutionSnapshot
    candidate: CandidateSet
    signal: SignalSnapshot
    path: PathForecast
    price: DecisionPriceSnapshot
    configuration: ThesisHealthRuleConfiguration
    rule_set: ThesisInvalidationRuleSet


def make_h5_fixture() -> H5Fixture:
    market = _market()
    theme = _theme()
    capital = _capital(theme)
    candidate = _candidate(market, theme, capital)
    signal = _signal(candidate)
    path = _path(signal)
    opportunity = _opportunity(candidate, signal, path)
    thesis = _thesis(opportunity)
    return H5Fixture(
        thesis=thesis,
        opportunity=opportunity,
        market=market,
        theme=theme,
        capital=capital,
        candidate=candidate,
        signal=signal,
        path=path,
        price=_price(),
        configuration=health_configuration(),
        rule_set=health_rule_set(thesis),
    )


def _sha(character: str) -> str:
    return "sha256:" + character * 64


def _envelope(
    artifact_type: str,
    payload: dict[str, object],
    *,
    inputs: tuple[tuple[ArtifactId, str], ...] = (),
    status: str = "RESEARCH_READY",
    decision_at: datetime = RESEARCH_AT,
    model_name: str | None = None,
) -> ArtifactEnvelope:
    return ArtifactEnvelope.create(
        artifact_type=artifact_type,
        artifact_payload=payload,
        decision_date=decision_at.date(),
        decision_time=DecisionTime(decision_at),
        created_at=decision_at + timedelta(seconds=10),
        code_revision="h5-fixture-revision",
        configuration_id=ArtifactId(f"config-{artifact_type.lower()}"),
        configuration_hash=_sha("2"),
        source_manifest_id=SOURCE_MANIFEST_ID,
        source_manifest_hash=SOURCE_MANIFEST_HASH,
        input_artifact_ids=tuple(item[0] for item in inputs),
        input_content_hashes=tuple(item[1] for item in inputs),
        model_id=ModelId(model_name) if model_name is not None else None,
        model_version="fixture-v1" if model_name is not None else None,
        data_eligibility=DataEligibility.EXPLORATORY,
        evidence_authority=EvidenceAuthority.IMMUTABLE_CONTENT_ADDRESSED_ARTIFACT,
        status=status,
        reason_codes=("H5_SYNTHETIC_FIXTURE",),
        limitations=("SYNTHETIC_TEST_EVIDENCE",),
    )


def _market() -> MarketRegimeSnapshot:
    values = {
        "market_state": MarketState.RISK_ON,
        "trade_permission": TradePermission.ALLOW,
        "maximum_gross_exposure": 1.0,
        "confidence": 1.0,
        "direction_score": 0.5,
        "breadth_score": 0.5,
        "liquidity_score": 0.5,
        "volatility_score": 0.5,
        "limit_structure_score": 0.5,
        "market_direction": MarketDirection.UP,
        "market_breadth": MarketBreadth.STRONG,
        "market_liquidity": MarketLiquidity.EXPANDING,
        "market_volatility": MarketVolatility.NORMAL,
        "risk_appetite": RiskAppetite.STRONG,
        "observed_metrics": (),
        "reason_codes": ("H5_MARKET_SUPPORTED",),
    }
    payload = {
        "market_state": values["market_state"].value,
        "trade_permission": values["trade_permission"].value,
        "maximum_gross_exposure": values["maximum_gross_exposure"],
        "confidence": values["confidence"],
        "direction_score": values["direction_score"],
        "breadth_score": values["breadth_score"],
        "liquidity_score": values["liquidity_score"],
        "volatility_score": values["volatility_score"],
        "limit_structure_score": values["limit_structure_score"],
        "market_direction": values["market_direction"].value,
        "market_breadth": values["market_breadth"].value,
        "market_liquidity": values["market_liquidity"].value,
        "market_volatility": values["market_volatility"].value,
        "risk_appetite": values["risk_appetite"].value,
        "observed_metrics": [],
        "reason_codes": list(values["reason_codes"]),
    }
    return MarketRegimeSnapshot(envelope=_envelope("MARKET_REGIME_SNAPSHOT", payload), **values)  # type: ignore[arg-type]


def _theme_item() -> ThemeRotationItem:
    return ThemeRotationItem(
        theme_id=THEME_ID,
        theme_name="Banking",
        benchmark_id="benchmark-bank",
        proxy_etf_ids=("512800.SH",),
        rotation_state=RotationState.LEADING,
        rotation_score=0.8,
        rank=1,
        confidence=1.0,
        relative_strength_1d=0.02,
        relative_strength_3d=0.03,
        relative_strength_5d=0.04,
        relative_strength_10d=0.05,
        amount_expansion=0.3,
        breadth=0.8,
        new_high_breadth=0.6,
        leader_strength=0.05,
        participation_change=0.2,
        persistence=0.8,
        reason_codes=("H5_THEME_SUPPORTED",),
    )


def _theme() -> ThemeRotationSnapshot:
    item = _theme_item()
    payload = {
        "themes": [item.to_canonical_dict()],
        "reason_codes": ["H5_THEME_FIXTURE"],
    }
    return ThemeRotationSnapshot(
        envelope=_envelope("THEME_ROTATION_SNAPSHOT", payload),
        themes=(item,),
        reason_codes=("H5_THEME_FIXTURE",),
    )


def _capital(theme: ThemeRotationSnapshot) -> CapitalEvolutionSnapshot:
    theme_item = ThemeCapitalEvolution(
        theme_id=THEME_ID,
        capital_evolution_score=0.8,
        capital_evolution_state=CapitalEvolutionState.ACCELERATION,
        confidence=1.0,
        theme_relative_strength=0.04,
        etf_amount_expansion=0.3,
        theme_amount_expansion=0.3,
        breadth=0.8,
        new_high_breadth=0.6,
        leader_strength=0.05,
        participation_expansion=0.2,
        capital_concentration=0.4,
        rank_persistence=0.8,
        amount_persistence=0.8,
        diffusion_score=0.8,
        reason_codes=("H5_THEME_CAPITAL_SUPPORTED",),
    )
    symbol_item = SymbolCapitalEvolution(
        symbol=SYMBOL,
        theme_id=THEME_ID,
        symbol_relative_strength=0.05,
        symbol_amount_expansion=0.3,
        theme_participation_contribution=0.2,
        leader_correlation=0.8,
        leader_lag=0.0,
        rank_persistence=0.8,
        amount_persistence=0.8,
        capital_evolution_score=0.8,
        capital_evolution_state=CapitalEvolutionState.ACCELERATION,
        confidence=1.0,
        reason_codes=("H5_SYMBOL_CAPITAL_SUPPORTED",),
    )
    payload = {
        "themes": [theme_item.to_canonical_dict()],
        "symbols": [symbol_item.to_canonical_dict()],
        "reason_codes": ["CAPITAL_EVOLUTION_IS_MODEL_INFERENCE"],
    }
    return CapitalEvolutionSnapshot(
        envelope=_envelope(
            "CAPITAL_EVOLUTION_SNAPSHOT",
            payload,
            inputs=((theme.envelope.artifact_id, theme.envelope.content_hash),),
        ),
        themes=(theme_item,),
        symbols=(symbol_item,),
        reason_codes=("CAPITAL_EVOLUTION_IS_MODEL_INFERENCE",),
    )


def _candidate(
    market: MarketRegimeSnapshot,
    theme: ThemeRotationSnapshot,
    capital: CapitalEvolutionSnapshot,
) -> CandidateSet:
    record = CandidateRecord(
        symbol=SYMBOL,
        primary_theme_id=THEME_ID,
        supporting_theme_ids=(),
        market_regime_status=market.market_state,
        theme_rotation_state=theme.themes[0].rotation_state,
        capital_evolution_state=capital.symbols[0].capital_evolution_state,
        market_regime_score=0.5,
        theme_score=0.8,
        capital_evolution_score=0.8,
        candidate_discovery_score=0.8,
        rank=1,
        selection_status=CandidateSelectionStatus.SELECTED,
        reason_codes=("H5_CANDIDATE_SELECTED",),
        source_feature_ids=(),
        input_artifact_ids=(),
    )
    payload = {
        "records": [record.to_canonical_dict()],
        "minimum_candidate_population": 1,
        "reason_codes": ["CANDIDATE_SET_IS_NOT_RECOMMENDATION"],
    }
    return CandidateSet(
        envelope=_envelope(
            "CANDIDATE_SET",
            payload,
            inputs=(
                (market.envelope.artifact_id, market.envelope.content_hash),
                (theme.envelope.artifact_id, theme.envelope.content_hash),
                (capital.envelope.artifact_id, capital.envelope.content_hash),
            ),
        ),
        records=(record,),
        minimum_candidate_population=1,
        reason_codes=("CANDIDATE_SET_IS_NOT_RECOMMENDATION",),
    )


def _signal(candidate: CandidateSet) -> SignalSnapshot:
    values = {
        "symbol": SYMBOL,
        "signal_family": SignalFamily.TREND_CONTINUATION,
        "signal_state": SignalState.CONFIRMED_FOR_RESEARCH,
        "price_action_state": ConfirmationState.CONFIRMED,
        "volume_confirmation_state": ConfirmationState.CONFIRMED,
        "trend_confirmation_state": ConfirmationState.CONFIRMED,
        "vwap_state": ConfirmationState.CONFIRMED,
        "overheat_state": ConfirmationState.CONFIRMED,
        "signal_score": 0.8,
        "confidence": 1.0,
        "reason_codes": ("SIGNAL_CONFIRMED_FOR_RESEARCH_ONLY",),
    }
    payload = {
        name: value.value if hasattr(value, "value") else list(value) if isinstance(value, tuple) else value
        for name, value in values.items()
    }
    return SignalSnapshot(
        envelope=_envelope(
            "SIGNAL_SNAPSHOT",
            payload,
            inputs=((candidate.envelope.artifact_id, candidate.envelope.content_hash),),
            status=SignalState.CONFIRMED_FOR_RESEARCH.value,
            model_name="h5-signal-model",
        ),
        **values,  # type: ignore[arg-type]
    )


def _path(signal: SignalSnapshot) -> PathForecast:
    values = {
        "symbol": SYMBOL,
        "target_id": TargetId("h5-path-target"),
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
        "reason_codes": ("PATH_FORECAST_UNCALIBRATED_RESEARCH_ONLY",),
    }
    payload = {
        "symbol": SYMBOL,
        "target_id": str(values["target_id"]),
        "forecast_horizon": values["forecast_horizon"],
        "upper_barrier_return": values["upper_barrier_return"],
        "lower_barrier_return": values["lower_barrier_return"],
        "expected_mfe": values["expected_mfe"],
        "expected_mae": values["expected_mae"],
        "return_quantiles": [],
        "calibration_status": CalibrationStatus.NOT_CALIBRATED.value,
        "forecast_status": PathForecastStatus.AVAILABLE_FOR_RESEARCH.value,
        "usable_sample_count": 100,
        "excluded_sample_count": 0,
        "reason_codes": ["PATH_FORECAST_UNCALIBRATED_RESEARCH_ONLY"],
    }
    return PathForecast(
        envelope=_envelope(
            "PATH_FORECAST",
            payload,
            inputs=((signal.envelope.artifact_id, signal.envelope.content_hash),),
            status=PathForecastStatus.AVAILABLE_FOR_RESEARCH.value,
            model_name="h5-path-model",
        ),
        **values,  # type: ignore[arg-type]
    )


def _price() -> DecisionPriceSnapshot:
    price_time = RESEARCH_AT + timedelta(minutes=2)
    observation = DecisionPriceObservation(
        symbol=SYMBOL,
        provider_id=ProviderId("provider-h5-fixture"),
        source_artifact_id=ArtifactId("quote-source-h5-fixture"),
        event_time=price_time - timedelta(seconds=2),
        available_time=AvailabilityTime(price_time - timedelta(seconds=1)),
        price=10.5,
        quality=DecisionPriceQuality.AVAILABLE,
        reason_codes=(),
    )
    return DecisionPriceSnapshot(
        source_manifest_id=SOURCE_MANIFEST_ID,
        decision_time=DecisionTime(price_time),
        observations=(observation,),
        data_eligibility=DataEligibility.EXPLORATORY,
    )


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


def _opportunity(
    candidate: CandidateSet,
    signal: SignalSnapshot,
    path: PathForecast,
) -> TradingOpportunity:
    created_at = RESEARCH_AT + timedelta(minutes=1)
    return TradingOpportunity(
        schema_version=TRADING_OPPORTUNITY_SCHEMA,
        opportunity_id=OpportunityId("opportunity-h5-fixture"),
        symbol=SYMBOL,
        candidate_set=_evidence(candidate.envelope),
        signal_snapshot=_evidence(signal.envelope),
        path_forecast=_evidence(path.envelope),
        decision_time=DecisionTime(RESEARCH_AT),
        signal_model=_model(signal.envelope),
        forecast_model=_model(path.envelope),
        valid_until=RESEARCH_AT + timedelta(days=2),
        state=OpportunityState.CONFIRMED_TO_THESIS,
        version=1,
        created_at=created_at,
        created_by="researcher-a",
        creation_reason="verified creation evidence",
        updated_at=created_at + timedelta(seconds=1),
        last_actor="approver-a",
        last_reason="confirmed to Thesis",
        reason_codes=("VERIFIED_RESEARCH_EVIDENCE_BOUND",),
    )


def _conditions() -> tuple[InvalidationCondition, ...]:
    return tuple(
        sorted(
            (
                InvalidationCondition("capital-stop", InvalidationKind.CAPITAL, "typed capital rule", "CAPITAL_INVALIDATION"),
                InvalidationCondition("manual-stop", InvalidationKind.MANUAL, "typed manual rule", "MANUAL_INVALIDATION"),
                InvalidationCondition("market-stop", InvalidationKind.MARKET_REGIME, "typed market rule", "MARKET_INVALIDATION"),
                InvalidationCondition("price-stop", InvalidationKind.PRICE, "typed price rule", "PRICE_INVALIDATION"),
                InvalidationCondition("signal-stop", InvalidationKind.SIGNAL, "typed signal rule", "SIGNAL_INVALIDATION"),
                InvalidationCondition("theme-stop", InvalidationKind.THEME, "typed theme rule", "THEME_INVALIDATION"),
                InvalidationCondition("time-stop", InvalidationKind.TIME, "exact Thesis time", "TIME_INVALIDATION"),
            ),
            key=lambda item: item.condition_id,
        )
    )


def _thesis(opportunity: TradingOpportunity) -> TradingThesis:
    created_at = opportunity.updated_at
    return TradingThesis(
        schema_version=TRADING_THESIS_SCHEMA,
        thesis_id=ThesisId("thesis-h5-fixture"),
        opportunity_id=opportunity.opportunity_id,
        source_opportunity_version=0,
        symbol=SYMBOL,
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
        invalidation_conditions=_conditions(),
        time_invalidation=ASSESSED_AT + timedelta(days=5),
        state=ThesisState.APPROVED,
        version=0,
        approved_by="approver-a",
        approval_reason="verified explicit Thesis",
        created_at=created_at,
        updated_at=created_at,
        last_actor="approver-a",
        last_reason="verified explicit Thesis",
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


def health_configuration() -> ThesisHealthRuleConfiguration:
    return ThesisHealthRuleConfiguration.create(
        profile_id="h5-fixture-profile-v1",
        builder_revision="h5-builder-v1",
        maximum_market_age_seconds=600.0,
        maximum_theme_age_seconds=600.0,
        maximum_capital_age_seconds=600.0,
        maximum_candidate_age_seconds=600.0,
        maximum_signal_age_seconds=600.0,
        maximum_path_age_seconds=600.0,
        maximum_price_age_seconds=300.0,
        maximum_price_research_skew_seconds=300.0,
        maximum_prior_observation_age_seconds=86_400.0,
        market_state_mapping=_mapping(MarketState, {MarketState.RISK_ON, MarketState.RISK_NEUTRAL}, {MarketState.RISK_OFF, MarketState.EXTREME_RISK}, {MarketState.DATA_INSUFFICIENT}),
        trade_permission_mapping=_mapping(TradePermission, {TradePermission.ALLOW}, {TradePermission.RESTRICT}, {TradePermission.PROHIBIT}),
        signal_state_mapping=_mapping(SignalState, {SignalState.CONFIRMED_FOR_RESEARCH}, {SignalState.WATCH, SignalState.INACTIVE}, {SignalState.DATA_INSUFFICIENT}),
        confirmation_state_mapping=_mapping(ConfirmationState, {ConfirmationState.CONFIRMED}, {ConfirmationState.UNCONFIRMED, ConfirmationState.CONTRADICTED}, {ConfirmationState.UNKNOWN}),
        path_status_mapping=_mapping(PathForecastStatus, {PathForecastStatus.AVAILABLE_FOR_RESEARCH}, set(), {PathForecastStatus.DATA_INSUFFICIENT}),
        path_calibration_mapping=_mapping(CalibrationStatus, {CalibrationStatus.NOT_CALIBRATED}, {CalibrationStatus.CALIBRATED_EXPLORATORY}, {CalibrationStatus.DATA_INSUFFICIENT}),
        theme_state_mapping=_mapping(RotationState, {RotationState.STARTING, RotationState.STRENGTHENING, RotationState.LEADING}, {RotationState.DIVERGING, RotationState.WEAKENING, RotationState.FAILED}, {RotationState.DATA_INSUFFICIENT}),
        capital_state_mapping=_mapping(CapitalEvolutionState, {CapitalEvolutionState.ACCUMULATION, CapitalEvolutionState.IGNITION, CapitalEvolutionState.DIFFUSION, CapitalEvolutionState.ACCELERATION}, {CapitalEvolutionState.DORMANT, CapitalEvolutionState.DIVERGENCE, CapitalEvolutionState.EXHAUSTION, CapitalEvolutionState.COLLAPSE}, {CapitalEvolutionState.DATA_INSUFFICIENT}),
        minimum_signal_score=0.2,
        minimum_signal_confidence=0.8,
        minimum_path_usable_sample_count=20,
        minimum_path_expected_mfe=0.02,
        minimum_path_expected_mae=-0.05,
        minimum_path_reward_risk_ratio=1.5,
    )


def health_rule_set(thesis: TradingThesis) -> ThesisInvalidationRuleSet:
    return ThesisInvalidationRuleSet.create(
        thesis_id=thesis.thesis_id,
        thesis_version=thesis.version,
        rules=(
            CapitalEvolutionStateInRule("capital-stop", CapitalRuleScope.BOTH, (CapitalEvolutionState.COLLAPSE,)),
            ManualEvidenceRequiredRule("manual-stop"),
            MarketStateInRule("market-stop", (MarketState.EXTREME_RISK,)),
            PriceBelowRule("price-stop", 9.0),
            SignalStateInRule("signal-stop", (SignalState.INACTIVE,)),
            ThemeRotationStateInRule("theme-stop", (RotationState.FAILED,)),
            TimeAfterRule("time-stop", thesis.time_invalidation),
        ),
    )
