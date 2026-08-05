"""Deterministic, assumption-bound Market Regime V0."""

from __future__ import annotations

from dataclasses import dataclass

from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.evidence.envelope import (
    ArtifactEnvelope,
    EvidenceAuthority,
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
from market_regime_alpha.research.platform_v2.configs import (
    MarketRegimeModelConfig,
)
from market_regime_alpha.research.platform_v2.inputs import ResearchContextView


def evaluate_market_regime_v0(
    inputs: ResearchContextView,
    config: MarketRegimeModelConfig,
    *,
    code_revision: str,
) -> MarketRegimeSnapshot:
    observation = inputs.market_observation
    metrics = _observed_metrics(inputs)
    required = (
        observation.market_direction_return if observation else None,
        observation.market_intraday_range_to_cutoff if observation else None,
        observation.market_amount_change_same_cutoff if observation else None,
        observation.candidate_breadth_at_cutoff if observation else None,
    )
    if (
        observation is None
        or observation.coverage < config.minimum_coverage
        or any(value is None for value in required)
    ):
        payload = _MarketValues(
            market_state=MarketState.DATA_INSUFFICIENT,
            trade_permission=TradePermission.PROHIBIT,
            maximum_gross_exposure=0.0,
            confidence=observation.coverage if observation else 0.0,
            scores=(None, None, None, None, None),
            labels=(
                MarketDirection.UNKNOWN,
                MarketBreadth.UNKNOWN,
                MarketLiquidity.UNKNOWN,
                MarketVolatility.UNKNOWN,
                RiskAppetite.UNKNOWN,
            ),
            observed_metrics=metrics,
            reason_codes=("MARKET_REGIME_DATA_INSUFFICIENT",),
        )
        return _snapshot(inputs, config, code_revision, payload)
    assert observation.market_direction_return is not None
    assert observation.market_intraday_range_to_cutoff is not None
    assert observation.market_amount_change_same_cutoff is not None
    assert observation.candidate_breadth_at_cutoff is not None
    direction = _clip(
        observation.market_direction_return / config.direction_scale
    )
    breadth = _clip(
        2.0 * (observation.candidate_breadth_at_cutoff - 0.5)
    )
    liquidity = _clip(
        observation.market_amount_change_same_cutoff / config.liquidity_scale
    )
    volatility = _clip(
        1.0
        - 2.0
        * observation.market_intraday_range_to_cutoff
        / config.volatility_scale
    )
    limit_structure = _clip(observation.limit_structure_score or 0.0)
    combined = (
        direction * config.direction_weight
        + breadth * config.breadth_weight
        + liquidity * config.liquidity_weight
        + volatility * config.volatility_weight
        + limit_structure * config.limit_structure_weight
    )
    state, permission, exposure, appetite = _state(combined, config)
    reasons = tuple(
        dict.fromkeys(
            (
                *observation.reason_codes,
                f"MARKET_STATE_{state.value}",
                "MARKET_REGIME_IS_RESEARCH_GATE_NOT_SIGNAL",
            )
        )
    )
    payload = _MarketValues(
        market_state=state,
        trade_permission=permission,
        maximum_gross_exposure=exposure,
        confidence=observation.coverage,
        scores=(direction, breadth, liquidity, volatility, limit_structure),
        labels=(
            MarketDirection.UP
            if direction > 0.10
            else MarketDirection.DOWN
            if direction < -0.10
            else MarketDirection.FLAT,
            MarketBreadth.STRONG
            if breadth > 0.20
            else MarketBreadth.WEAK
            if breadth < -0.20
            else MarketBreadth.MIXED,
            MarketLiquidity.EXPANDING
            if liquidity > 0.10
            else MarketLiquidity.CONTRACTING
            if liquidity < -0.10
            else MarketLiquidity.STABLE,
            MarketVolatility.LOW
            if volatility > 0.30
            else MarketVolatility.HIGH
            if volatility < -0.30
            else MarketVolatility.NORMAL,
            appetite,
        ),
        observed_metrics=metrics,
        reason_codes=reasons,
    )
    return _snapshot(inputs, config, code_revision, payload)


def _state(
    score: float, config: MarketRegimeModelConfig
) -> tuple[MarketState, TradePermission, float, RiskAppetite]:
    if score >= config.risk_on_threshold:
        return MarketState.RISK_ON, TradePermission.ALLOW, 1.0, RiskAppetite.STRONG
    if score >= config.neutral_threshold:
        return (
            MarketState.RISK_NEUTRAL,
            TradePermission.RESTRICT,
            config.restricted_exposure,
            RiskAppetite.NEUTRAL,
        )
    if score >= config.extreme_risk_threshold:
        return (
            MarketState.RISK_OFF,
            TradePermission.RESTRICT,
            min(config.restricted_exposure, 0.25),
            RiskAppetite.DEFENSIVE,
        )
    return (
        MarketState.EXTREME_RISK,
        TradePermission.PROHIBIT,
        0.0,
        RiskAppetite.EXTREME_DEFENSIVE,
    )


@dataclass(frozen=True, slots=True)
class _MarketValues:
    market_state: MarketState
    trade_permission: TradePermission
    maximum_gross_exposure: float
    confidence: float
    scores: tuple[
        float | None,
        float | None,
        float | None,
        float | None,
        float | None,
    ]
    labels: tuple[
        MarketDirection,
        MarketBreadth,
        MarketLiquidity,
        MarketVolatility,
        RiskAppetite,
    ]
    observed_metrics: tuple[tuple[str, float], ...]
    reason_codes: tuple[str, ...]


def _snapshot(
    inputs: ResearchContextView,
    config: MarketRegimeModelConfig,
    code_revision: str,
    values: _MarketValues,
) -> MarketRegimeSnapshot:
    scores = values.scores
    labels = values.labels
    payload = {
        "market_state": values.market_state.value,
        "trade_permission": values.trade_permission.value,
        "maximum_gross_exposure": values.maximum_gross_exposure,
        "confidence": values.confidence,
        "direction_score": scores[0],
        "breadth_score": scores[1],
        "liquidity_score": scores[2],
        "volatility_score": scores[3],
        "limit_structure_score": scores[4],
        "market_direction": labels[0].value,
        "market_breadth": labels[1].value,
        "market_liquidity": labels[2].value,
        "market_volatility": labels[3].value,
        "risk_appetite": labels[4].value,
        "observed_metrics": [
            {"metric": key, "value": value}
            for key, value in values.observed_metrics
        ],
        "reason_codes": list(values.reason_codes),
    }
    envelope = ArtifactEnvelope.create(
        artifact_type="MARKET_REGIME_SNAPSHOT",
        artifact_payload=payload,
        decision_date=inputs.source_manifest.decision_time.value.date(),
        decision_time=inputs.source_manifest.decision_time,
        created_at=inputs.created_at,
        code_revision=code_revision,
        configuration_id=config.configuration_id,
        configuration_hash=config.configuration_hash,
        source_manifest_id=inputs.source_manifest.source_manifest_id,
        source_manifest_hash=inputs.source_manifest.content_hash,
        input_artifact_ids=(
            *inputs.input_artifact_ids,
            inputs.input_bundle_id,
        ),
        input_content_hashes=(
            *inputs.input_content_hashes,
            inputs.content_hash,
        ),
        model_id=config.model_id,
        model_version=config.model_version,
        data_eligibility=DataEligibility.EXPLORATORY,
        evidence_authority=EvidenceAuthority.IMMUTABLE_CONTENT_ADDRESSED_ARTIFACT,
        status=values.market_state.value,
        reason_codes=values.reason_codes,
        limitations=config.assumptions,
    )
    return MarketRegimeSnapshot(
        envelope=envelope,
        market_state=values.market_state,
        trade_permission=values.trade_permission,
        maximum_gross_exposure=values.maximum_gross_exposure,
        confidence=values.confidence,
        direction_score=scores[0],
        breadth_score=scores[1],
        liquidity_score=scores[2],
        volatility_score=scores[3],
        limit_structure_score=scores[4],
        market_direction=labels[0],
        market_breadth=labels[1],
        market_liquidity=labels[2],
        market_volatility=labels[3],
        risk_appetite=labels[4],
        observed_metrics=values.observed_metrics,
        reason_codes=values.reason_codes,
    )


def _observed_metrics(
    inputs: ResearchContextView,
) -> tuple[tuple[str, float], ...]:
    item = inputs.market_observation
    if item is None:
        return ()
    return tuple(
        (name, value)
        for name, value in (
            ("market_direction_return", item.market_direction_return),
            (
                "market_intraday_range_to_cutoff",
                item.market_intraday_range_to_cutoff,
            ),
            (
                "market_amount_change_same_cutoff",
                item.market_amount_change_same_cutoff,
            ),
            (
                "candidate_breadth_at_cutoff",
                item.candidate_breadth_at_cutoff,
            ),
            ("limit_structure_score", item.limit_structure_score),
            ("coverage", item.coverage),
        )
        if value is not None
    )


def _clip(value: float) -> float:
    return max(-1.0, min(1.0, value))
