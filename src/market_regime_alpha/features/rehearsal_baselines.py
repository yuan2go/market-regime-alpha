"""Transparent baseline Feature Definitions and materializers for R5 rehearsal.

The first baseline deliberately uses a small set of interpretable inputs. These features
are rehearsal research objects, not promoted Predictive Factors.
"""

from __future__ import annotations

from collections import defaultdict
from hashlib import sha256
import json
import math
from statistics import mean, median, pstdev
from zoneinfo import ZoneInfo

from market_regime_alpha.candidates.contracts import CandidatePopulation
from market_regime_alpha.core.identity import (
    DatasetId,
    FeatureDefinitionId,
    FeatureMaterializationId,
    UniverseId,
)
from market_regime_alpha.core.status import InputAvailabilityStatus
from market_regime_alpha.core.time import AsOfTime
from market_regime_alpha.data.rehearsal import RehearsalDailyBar, RehearsalDecisionSnapshot
from market_regime_alpha.features.contracts import (
    FeatureDefinition,
    FeatureMaterialization,
    FeatureObservation,
)


MOMENTUM_5S_ID = FeatureDefinitionId("feature-r5-momentum-5s-v1")
VOLATILITY_20S_ID = FeatureDefinitionId("feature-r5-volatility-20s-v1")
LIQUIDITY_20S_ID = FeatureDefinitionId("feature-r5-log-median-amount-20s-v1")
PRICE_VS_MA20_ID = FeatureDefinitionId("feature-r5-price-vs-ma20-v1")
_R5_TIMEZONE = ZoneInfo("Asia/Shanghai")


def r5_baseline_feature_definitions() -> tuple[FeatureDefinition, ...]:
    """Return the frozen first R5 transparent baseline Feature schema."""

    return (
        FeatureDefinition(
            feature_id=MOMENTUM_5S_ID,
            name="R5 5-Session Momentum",
            semantic_family="Momentum",
            source_information_families=("PRICE_ONLY",),
            representation_method="decision_reference_price / close_t_minus_5 - 1",
            source_fields=("close", "decision_reference_price"),
            frequency="one value per Candidate Decision Time",
            lookback="5 finalized prior trading sessions plus Decision Time price snapshot",
            availability_rule="all historical closes finalized and decision snapshot available by 14:55 Asia/Shanghai Decision Time",
            missingness_policy="MISSING when Decision Time price or five prior finalized sessions are unavailable",
            research_status="REHEARSAL_BASELINE",
            parameters=(("lookback_sessions", "5"), ("decision_time", "14:55 Asia/Shanghai")),
        ),
        FeatureDefinition(
            feature_id=VOLATILITY_20S_ID,
            name="R5 20-Session Realized Volatility",
            semantic_family="Volatility",
            source_information_families=("PRICE_ONLY",),
            representation_method="population_std_of_20_close_to_close_returns",
            source_fields=("close",),
            frequency="one value per Candidate Decision Time",
            lookback="21 finalized prior closes producing 20 session returns",
            availability_rule="all required historical closes finalized and available by 14:55 Asia/Shanghai Decision Time",
            missingness_policy="MISSING when fewer than 21 finalized prior closes are available",
            research_status="REHEARSAL_BASELINE",
            parameters=(("return_count", "20"), ("decision_time", "14:55 Asia/Shanghai")),
        ),
        FeatureDefinition(
            feature_id=LIQUIDITY_20S_ID,
            name="R5 20-Session Log Median Amount",
            semantic_family="Liquidity",
            source_information_families=("TRADE_AMOUNT",),
            representation_method="log1p(median(amount_last_20_finalized_sessions))",
            source_fields=("amount",),
            frequency="one value per Candidate Decision Time",
            lookback="20 finalized prior trading sessions",
            availability_rule="historical amount observations finalized and available by 14:55 Asia/Shanghai Decision Time",
            missingness_policy="MISSING when fewer than 20 finalized prior amount observations are available",
            research_status="REHEARSAL_BASELINE",
            parameters=(("lookback_sessions", "20"), ("decision_time", "14:55 Asia/Shanghai")),
        ),
        FeatureDefinition(
            feature_id=PRICE_VS_MA20_ID,
            name="R5 Decision Price versus Prior MA20",
            semantic_family="Trend",
            source_information_families=("PRICE_ONLY",),
            representation_method="decision_reference_price / mean(close_last_20_finalized_sessions) - 1",
            source_fields=("close", "decision_reference_price"),
            frequency="one value per Candidate Decision Time",
            lookback="20 finalized prior trading sessions plus Decision Time price snapshot",
            availability_rule="historical closes finalized and decision snapshot available by 14:55 Asia/Shanghai Decision Time",
            missingness_policy="MISSING when Decision Time price or twenty prior finalized closes are unavailable",
            research_status="REHEARSAL_BASELINE",
            parameters=(("moving_average_sessions", "20"), ("decision_time", "14:55 Asia/Shanghai")),
        ),
    )


def materialize_r5_baseline_features(
    *,
    population: CandidatePopulation,
    source_dataset_id: DatasetId,
    daily_bars: tuple[RehearsalDailyBar, ...],
    decision_snapshots: tuple[RehearsalDecisionSnapshot, ...],
    code_revision: str,
    config_hash: str,
) -> tuple[FeatureMaterialization, ...]:
    """Materialize the first four transparent baseline features for one Candidate cross-section."""

    _require_r5_decision_time(population)
    bars_by_symbol: dict[str, list[RehearsalDailyBar]] = defaultdict(list)
    seen_bar_keys: set[tuple[str, object]] = set()
    for bar in daily_bars:
        if not bar.finalized:
            continue
        if bar.available_at.value > population.decision_time.value:
            continue
        if bar.session_date >= population.decision_time.value.astimezone(_R5_TIMEZONE).date():
            continue
        key = (bar.symbol, bar.session_date)
        if key in seen_bar_keys:
            raise ValueError(f"duplicate eligible rehearsal daily bar: {bar.symbol} {bar.session_date}")
        seen_bar_keys.add(key)
        bars_by_symbol[bar.symbol].append(bar)
    for bars in bars_by_symbol.values():
        bars.sort(key=lambda bar: bar.session_date)

    snapshot_by_symbol: dict[str, RehearsalDecisionSnapshot] = {}
    for snapshot in decision_snapshots:
        if snapshot.decision_time != population.decision_time:
            continue
        if snapshot.symbol in snapshot_by_symbol:
            raise ValueError(f"duplicate rehearsal Decision Time snapshot: {snapshot.symbol}")
        snapshot_by_symbol[snapshot.symbol] = snapshot

    definitions = r5_baseline_feature_definitions()
    observations_by_feature: dict[FeatureDefinitionId, list[FeatureObservation]] = {
        definition.feature_id: [] for definition in definitions
    }

    for symbol in population.symbols:
        bars = bars_by_symbol.get(symbol, [])
        snapshot = snapshot_by_symbol.get(symbol)
        closes = [float(bar.close) for bar in bars]
        amounts = [float(bar.amount) for bar in bars]

        observations_by_feature[MOMENTUM_5S_ID].append(
            _feature_observation(
                symbol=symbol,
                value=(snapshot.reference_price / closes[-5] - 1.0)
                if snapshot is not None and len(closes) >= 5
                else None,
            )
        )

        volatility: float | None = None
        if len(closes) >= 21:
            recent = closes[-21:]
            returns = [recent[index] / recent[index - 1] - 1.0 for index in range(1, len(recent))]
            volatility = pstdev(returns)
        observations_by_feature[VOLATILITY_20S_ID].append(
            _feature_observation(symbol=symbol, value=volatility)
        )

        liquidity = math.log1p(median(amounts[-20:])) if len(amounts) >= 20 else None
        observations_by_feature[LIQUIDITY_20S_ID].append(
            _feature_observation(symbol=symbol, value=liquidity)
        )

        price_vs_ma20 = (
            snapshot.reference_price / mean(closes[-20:]) - 1.0
            if snapshot is not None and len(closes) >= 20
            else None
        )
        observations_by_feature[PRICE_VS_MA20_ID].append(
            _feature_observation(symbol=symbol, value=price_vs_ma20)
        )

    return tuple(
        FeatureMaterialization(
            materialization_id=_materialization_id(
                definition_id=definition.feature_id,
                dataset_id=source_dataset_id,
                universe_id=population.universe_id,
                as_of=AsOfTime(population.decision_time.value),
                code_revision=code_revision,
                config_hash=config_hash,
            ),
            definition_id=definition.feature_id,
            dataset_id=source_dataset_id,
            universe_id=population.universe_id,
            as_of=AsOfTime(population.decision_time.value),
            code_revision=code_revision,
            config_hash=config_hash,
            observations=tuple(observations_by_feature[definition.feature_id]),
        )
        for definition in definitions
    )


def _require_r5_decision_time(population: CandidatePopulation) -> None:
    local = population.decision_time.value.astimezone(_R5_TIMEZONE)
    if (local.hour, local.minute, local.second, local.microsecond) != (14, 55, 0, 0):
        raise ValueError("R5 rehearsal baseline requires Decision Time 14:55:00 Asia/Shanghai")


def _feature_observation(*, symbol: str, value: float | None) -> FeatureObservation:
    if value is None:
        return FeatureObservation(symbol, InputAvailabilityStatus.MISSING, None)
    if not math.isfinite(float(value)):
        return FeatureObservation(symbol, InputAvailabilityStatus.INVALID, None)
    return FeatureObservation(symbol, InputAvailabilityStatus.AVAILABLE, float(value))


def _materialization_id(
    *,
    definition_id: FeatureDefinitionId,
    dataset_id: DatasetId,
    universe_id: UniverseId,
    as_of: AsOfTime,
    code_revision: str,
    config_hash: str,
) -> FeatureMaterializationId:
    payload = {
        "schema_version": "r5-baseline-feature-materialization-v1",
        "definition_id": str(definition_id),
        "dataset_id": str(dataset_id),
        "universe_id": str(universe_id),
        "as_of": as_of.isoformat(),
        "code_revision": code_revision,
        "config_hash": config_hash,
    }
    canonical = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    digest = sha256(canonical.encode("utf-8")).hexdigest()
    return FeatureMaterializationId(f"fm-{digest[:24]}")
