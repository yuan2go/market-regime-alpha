"""Operational free ETF/Theme/Capital producer over verified source bytes."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from math import sqrt
from statistics import fmean, median, pstdev
from typing import Mapping

from market_regime_alpha.application.operational_research.contracts import (
    CapitalObservationEvidence,
    ETFThemeMappingEvidence,
    MissingEvidence,
    PITThemeMembershipEvidence,
    StatefulETFObservationEvidence,
    SupplementalResearchEvidenceBundle,
    ThemeObservationEvidence,
)
from market_regime_alpha.core.time import AvailabilityTime
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.data.free_operational_policy import (
    FREE_OPERATIONAL_POLICY_AUTHORITY_ID,
    FreeOperationalEvidencePolicy,
)
from market_regime_alpha.data.providers.public_composite import (
    BAOSTOCK_PUBLIC_PROVIDER_ID,
    PublicBar,
    PublicSourceAcquisitionStage,
    VerifiedPublicSourceStageArtifact,
)
from market_regime_alpha.data.source_manifest import SourceManifest
from market_regime_alpha.evidence.canonical import canonical_json
from market_regime_alpha.research.platform_v2.inputs import (
    ETFObservation,
    ResearchDailyBar,
    SymbolResearchObservation,
)


def produce_free_operational_evidence(
    *,
    base: SupplementalResearchEvidenceBundle,
    source: VerifiedPublicSourceStageArtifact,
    policy: FreeOperationalEvidencePolicy,
    created_at: datetime,
) -> SupplementalResearchEvidenceBundle:
    """Enrich built-in stock evidence; never substitute a missing Provider."""

    if source.stage is not PublicSourceAcquisitionStage.SUPPLEMENTAL_SOURCE_FROZEN:
        raise ValueError("operational evidence requires frozen supplemental source")
    if len(policy.themes) != 1:
        raise ValueError("free operational V1 requires exactly one Theme")
    decision_time = base.decision_time.value
    if decision_time.date() < min(item.effective_from for item in policy.themes):
        raise ValueError("operational policy is not effective at DecisionTime")
    if any(
        item.retrieved_time.value > decision_time for item in source.batch.raw_payloads
    ):
        raise ValueError(
            "operational supplemental evidence is available after DecisionTime"
        )
    if created_at < max(
        item.retrieved_time.value for item in source.batch.raw_payloads
    ):
        raise ValueError("operational supplemental created_at predates source")
    policy_sources = tuple(
        item
        for item in source.batch.raw_payloads
        if item.provider_id == FREE_OPERATIONAL_POLICY_AUTHORITY_ID
    )
    if len(policy_sources) != 1:
        raise ValueError("operational policy source is missing")
    expected_policy_bytes = (canonical_json(policy.to_canonical_dict()) + "\n").encode(
        "utf-8"
    )
    if (
        policy_sources[0].raw_payload != expected_policy_bytes
        or policy_sources[0].locator != f"policy://free-operational/{policy.policy_id}"
    ):
        raise ValueError("operational policy source identity mismatch")
    allowed_providers = {
        BAOSTOCK_PUBLIC_PROVIDER_ID,
        FREE_OPERATIONAL_POLICY_AUTHORITY_ID,
    }
    if any(
        item.provider_id not in allowed_providers for item in source.batch.raw_payloads
    ):
        raise ValueError(
            "operational supplemental source contains an undeclared Provider"
        )
    etf_sources = {
        item.source_artifact_id: item
        for item in source.batch.raw_payloads
        if item.provider_id == BAOSTOCK_PUBLIC_PROVIDER_ID
    }
    if not etf_sources:
        raise ValueError("BaoStock ETF source is missing; no fallback is allowed")

    manifest = SourceManifest(
        provider_profile_id=base.source_manifest.provider_profile_id,
        decision_time=base.decision_time,
        source_artifacts=tuple(
            sorted(
                {
                    *base.source_manifest.source_artifacts,
                    *(item.reference for item in source.batch.raw_payloads),
                },
                key=lambda item: str(item.artifact_id),
            )
        ),
        fields=base.source_manifest.fields,
        source_conflicts=tuple(
            sorted(
                {
                    *base.source_manifest.source_conflicts,
                    *source.batch.source_conflicts,
                }
            )
        ),
        limitations=tuple(
            dict.fromkeys(
                (
                    *base.source_manifest.limitations,
                    *source.batch.limitations,
                    *policy.limitations,
                    "FREE_OPERATIONAL_EVIDENCE_POLICY_BOUND",
                    "NO_PROVIDER_FALLBACK",
                )
            )
        ),
        data_eligibility=DataEligibility.EXPLORATORY,
        schema_version=SourceManifest.SCHEMA_V2,
    )
    bars_by_etf = {
        definition.etf_id: tuple(
            sorted(
                (
                    item
                    for item in source.batch.bars
                    if item.symbol == definition.etf_id
                    and item.event_time < decision_time
                ),
                key=lambda item: item.event_time,
            )
        )
        for definition in policy.etfs
    }
    stateful = []
    etf_observations = []
    missing = []
    for definition in policy.etfs:
        bars = bars_by_etf[definition.etf_id]
        if len(bars) < 11:
            missing.append(
                MissingEvidence(
                    evidence_kind="STATEFUL_ETF_OBSERVATION",
                    key=definition.etf_id,
                    reason_codes=(
                        "BAOSTOCK_ETF_HISTORY_INSUFFICIENT",
                        "NO_PROVIDER_FALLBACK",
                    ),
                )
            )
            continue
        source_id = bars[-1].source_artifact_id
        if source_id not in etf_sources:
            raise ValueError("ETF bar references an undeclared BaoStock source")
        available_at = AvailabilityTime(etf_sources[source_id].retrieved_time.value)
        returns = _period_returns(bars)
        amount_change = _latest_amount_change(bars)
        amount_persistence = _positive_fraction(
            [float(item.amount or 0.0) for item in bars[-6:]]
        )
        close_returns = _one_step_returns([float(item.close) for item in bars[-11:]])
        peak = max(float(item.close) for item in bars[-11:])
        latest = float(bars[-1].close)
        volatility = _unit(pstdev(close_returns) if len(close_returns) > 1 else 0.0)
        drawdown = _unit((peak - latest) / peak if peak > 0 else 0.0)
        liquidity = _unit(
            median(float(item.amount or 0.0) for item in bars[-10:]) / 100_000_000.0
        )
        direction_consistency = _positive_fraction(
            [float(item.close) for item in bars[-6:]]
        )
        market_return = base.market_observation.market_direction_return or 0.0
        stateful.append(
            StatefulETFObservationEvidence(
                etf_id=definition.etf_id,
                benchmark_id=definition.tracking_index_id,
                available_at=available_at,
                source_artifact_id=source_id,
                relative_strength_1d=_signed(returns[1]),
                relative_strength_3d=_signed(returns[3]),
                relative_strength_5d=_signed(returns[5]),
                relative_strength_10d=_signed(returns[10]),
                benchmark_excess=_signed(returns[1] - market_return),
                amount_change=_signed(amount_change),
                amount_persistence=amount_persistence,
                volume_change=_signed(_latest_volume_change(bars)),
                drawdown=drawdown,
                volatility=volatility,
                diffusion=direction_consistency,
                liquidity=liquidity,
                data_coverage=1.0,
                reason_codes=(
                    "BAOSTOCK_PRIOR_SESSION_ETF_HISTORY",
                    "FREE_OPERATIONAL_ETF_OBSERVATION",
                    "FORMAL_PIT_NOT_ESTABLISHED",
                ),
            )
        )
        etf_observations.append(
            ETFObservation(
                etf_id=definition.etf_id,
                theme_id=definition.theme_id,
                available_at=available_at,
                source_artifact_id=source_id,
                relative_strength=returns[1],
                amount_expansion=amount_change,
            )
        )

    policy_available_at = AvailabilityTime(policy_sources[0].retrieved_time.value)
    stock_bars_by_symbol = {
        item.symbol: tuple(
            sorted(
                (bar for bar in base.stock_daily_bars if bar.symbol == item.symbol),
                key=lambda bar: bar.session_date,
            )
        )
        for item in base.symbol_observations
    }
    theme_daily_returns = _theme_daily_returns(stock_bars_by_symbol)
    enriched_symbols = tuple(
        _enrich_symbol_observation(
            item,
            stock_bars_by_symbol[item.symbol],
            theme_daily_returns,
        )
        for item in base.symbol_observations
    )
    memberships = tuple(
        PITThemeMembershipEvidence(
            symbol=item.symbol,
            primary_theme_id=policy.themes[0].theme_id,
            supporting_theme_ids=(),
            available_at=policy_available_at,
            source_artifact_id=policy_sources[0].source_artifact_id,
        )
        for item in enriched_symbols
    )
    mappings = tuple(
        ETFThemeMappingEvidence(
            etf_id=item.etf_id,
            theme_id=item.theme_id,
            available_at=policy_available_at,
            source_artifact_id=policy_sources[0].source_artifact_id,
        )
        for item in policy.etfs
    )
    stateful_by_theme = {item.etf_id: item for item in stateful}
    etf_by_theme = {item.etf_id: item for item in etf_observations}
    stock_returns = tuple(
        item.symbol_relative_strength
        for item in enriched_symbols
        if item.symbol_relative_strength is not None
    )
    stock_amount = tuple(
        item.symbol_amount_expansion
        for item in enriched_symbols
        if item.symbol_amount_expansion is not None
    )
    themes = []
    capital = []
    for theme in policy.themes:
        proxy_ids = tuple(
            item.etf_id for item in policy.etfs if item.theme_id == theme.theme_id
        )
        proxy_state = tuple(
            stateful_by_theme[item] for item in proxy_ids if item in stateful_by_theme
        )
        proxy_simple = tuple(
            etf_by_theme[item] for item in proxy_ids if item in etf_by_theme
        )
        if not memberships or len(proxy_state) != len(proxy_ids):
            missing.extend(
                (
                    MissingEvidence(
                        evidence_kind="THEME_OBSERVATION",
                        key=theme.theme_id,
                        reason_codes=(
                            "THEME_MEMBER_OR_ETF_PROXY_INCOMPLETE",
                            "NO_PROVIDER_FALLBACK",
                        ),
                    ),
                    MissingEvidence(
                        evidence_kind="CAPITAL_OBSERVATION",
                        key=theme.theme_id,
                        reason_codes=(
                            "THEME_OBSERVATION_INCOMPLETE",
                            "NO_PROVIDER_FALLBACK",
                        ),
                    ),
                )
            )
            continue
        evidence_at = AvailabilityTime(
            max(
                base.market_observation.available_at.value,
                policy_available_at.value,
                *(item.available_at.value for item in proxy_state),
            )
        )
        theme_returns = {
            horizon: _mean_horizon_return(stock_bars_by_symbol, horizon)
            for horizon in (1, 3, 5, 10)
        }
        breadth = (
            sum(value > 0.0 for value in stock_returns) / len(stock_returns)
            if stock_returns
            else None
        )
        participation = (
            sum(value > 0.0 for value in stock_amount) / len(stock_amount)
            if stock_amount
            else None
        )
        leader_strength = max(stock_returns) if stock_returns else None
        amount_expansion = fmean(stock_amount) if stock_amount else None
        stock_amount_persistence = tuple(
            item.amount_persistence
            for item in enriched_symbols
            if item.amount_persistence is not None
        )
        rank_persistence_values = tuple(
            item.rank_persistence
            for item in enriched_symbols
            if item.rank_persistence is not None
        )
        latest_amounts = tuple(
            float(items[-1].amount) for items in stock_bars_by_symbol.values() if items
        )
        etf_expansion = fmean(item.amount_expansion for item in proxy_simple)
        concentration = _concentration(latest_amounts)
        diffusion = None if concentration is None else 1.0 - concentration
        new_high_breadth = _new_high_breadth(stock_bars_by_symbol)
        confidence = min(
            base.market_observation.coverage,
            *(item.data_coverage for item in proxy_state),
        )
        themes.append(
            ThemeObservationEvidence(
                theme_id=theme.theme_id,
                theme_name=theme.theme_name,
                benchmark_id=theme.benchmark_id,
                proxy_etf_ids=proxy_ids,
                available_at=evidence_at,
                source_artifact_id=base.market_observation.source_artifact_id,
                relative_strength_1d=theme_returns[1],
                relative_strength_3d=theme_returns[3],
                relative_strength_5d=theme_returns[5],
                relative_strength_10d=theme_returns[10],
                amount_expansion=amount_expansion,
                breadth=breadth,
                new_high_breadth=new_high_breadth,
                leader_strength=leader_strength,
                participation_change=participation,
                rank_persistence=(
                    fmean(rank_persistence_values) if rank_persistence_values else None
                ),
                confidence=confidence,
                reason_codes=(
                    "CURRENT_OPERATIONAL_UNIVERSE_THEME",
                    "OBSERVABLE_PROXIES_ONLY",
                    "PROXY_MAPPING_IS_NOT_INDEX_MEMBERSHIP",
                ),
            )
        )
        capital.append(
            CapitalObservationEvidence(
                theme_id=theme.theme_id,
                available_at=evidence_at,
                source_artifact_id=base.market_observation.source_artifact_id,
                etf_amount_expansion=etf_expansion,
                amount_persistence=(
                    fmean(
                        (
                            *(item.amount_persistence for item in proxy_state),
                            *stock_amount_persistence,
                        )
                    )
                    if stock_amount_persistence
                    else fmean(item.amount_persistence for item in proxy_state)
                ),
                capital_concentration=concentration,
                diffusion_score=diffusion,
                reason_codes=(
                    "OBSERVABLE_CAPITAL_PROXIES_ONLY",
                    "HIDDEN_INVESTOR_INTENT_NOT_ASSERTED",
                ),
            )
        )

    return SupplementalResearchEvidenceBundle(
        source_manifest=manifest,
        decision_time=base.decision_time,
        market_observation=base.market_observation,
        theme_observations=tuple(themes),
        capital_observations=tuple(capital),
        symbol_observations=enriched_symbols,
        theme_memberships=memberships,
        etf_theme_mappings=mappings,
        etf_observations=tuple(etf_observations),
        stateful_etf_observations=tuple(stateful),
        stock_daily_bars=base.stock_daily_bars,
        missing_evidence=tuple(
            sorted(missing, key=lambda item: (item.evidence_kind, item.key))
        ),
        reason_codes=(
            "EXPLORATORY",
            "FORMAL_OOS_ALPHA_NOT_ESTABLISHED",
            "FORMAL_PIT_NOT_ESTABLISHED",
            "NO_PROVIDER_FALLBACK",
            "OPERATIONAL_FREE_EVIDENCE_PRODUCED",
            "TRADING_AUTHORITY_NOT_GRANTED",
        ),
        created_at=created_at,
        data_eligibility=DataEligibility.EXPLORATORY,
    )


def _period_returns(bars: tuple[PublicBar, ...]) -> dict[int, float]:
    closes = [float(item.close) for item in bars]
    return {period: closes[-1] / closes[-1 - period] - 1.0 for period in (1, 3, 5, 10)}


def _latest_amount_change(bars: tuple[PublicBar, ...]) -> float:
    latest = float(bars[-1].amount or 0.0)
    previous = float(bars[-2].amount or 0.0)
    return 0.0 if previous <= 0.0 else latest / previous - 1.0


def _latest_volume_change(bars: tuple[PublicBar, ...]) -> float:
    latest = float(bars[-1].volume)
    previous = float(bars[-2].volume)
    return 0.0 if previous <= 0.0 else latest / previous - 1.0


def _one_step_returns(values: list[float]) -> list[float]:
    return [
        current / previous - 1.0
        for previous, current in zip(values, values[1:])
        if previous > 0.0
    ]


def _positive_fraction(values: list[float]) -> float:
    changes = [current - previous for previous, current in zip(values, values[1:])]
    return sum(value > 0.0 for value in changes) / len(changes) if changes else 0.0


def _concentration(values: tuple[float, ...]) -> float | None:
    positive = sorted((max(0.0, item) for item in values), reverse=True)
    total = sum(positive)
    if not positive or total <= 0.0:
        return None
    return _unit(sum(positive[:5]) / total)


def _enrich_symbol_observation(
    observation: SymbolResearchObservation,
    bars: tuple[ResearchDailyBar, ...],
    theme_daily_returns: tuple[float, ...],
) -> SymbolResearchObservation:
    if len(bars) < 11:
        return observation
    closes = [float(item.close) for item in bars]
    amounts = [float(item.amount) for item in bars]
    symbol_daily_returns = tuple(_one_step_returns(closes[-11:]))
    relative = closes[-1] / closes[-2] - 1.0
    theme_mean = fmean(theme_daily_returns) if theme_daily_returns else 0.0
    return replace(
        observation,
        theme_participation_contribution=relative - theme_mean,
        leader_correlation=_correlation(symbol_daily_returns, theme_daily_returns),
        leader_lag=0.0,
        rank_persistence=_positive_fraction(closes[-6:]),
        amount_persistence=_positive_fraction(amounts[-6:]),
        reason_codes=(
            "FREE_DATA_SYMBOL_OBSERVABLE_PROXY",
            "OPERATIONAL_THEME_CAPITAL_PROXY_PRODUCED",
        ),
    )


def _theme_daily_returns(
    bars_by_symbol: Mapping[str, tuple[ResearchDailyBar, ...]],
) -> tuple[float, ...]:
    series = tuple(
        tuple(_one_step_returns([float(item.close) for item in bars[-11:]]))
        for bars in bars_by_symbol.values()
        if len(bars) >= 11
    )
    if not series:
        return ()
    width = min(len(item) for item in series)
    return tuple(
        fmean(item[-width + index] for item in series) for index in range(width)
    )


def _mean_horizon_return(
    bars_by_symbol: Mapping[str, tuple[ResearchDailyBar, ...]], horizon: int
) -> float | None:
    values = tuple(
        float(bars[-1].close) / float(bars[-1 - horizon].close) - 1.0
        for bars in bars_by_symbol.values()
        if len(bars) > horizon
    )
    return fmean(values) if values else None


def _new_high_breadth(
    bars_by_symbol: Mapping[str, tuple[ResearchDailyBar, ...]],
) -> float | None:
    flags = tuple(
        float(bars[-1].close) >= max(float(item.close) for item in bars[-11:-1])
        for bars in bars_by_symbol.values()
        if len(bars) >= 11
    )
    return sum(flags) / len(flags) if flags else None


def _correlation(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    width = min(len(left), len(right))
    if width < 2:
        return 0.0
    x = left[-width:]
    y = right[-width:]
    mean_x = fmean(x)
    mean_y = fmean(y)
    numerator = sum((a - mean_x) * (b - mean_y) for a, b in zip(x, y))
    denominator = sqrt(
        sum((a - mean_x) ** 2 for a in x) * sum((b - mean_y) ** 2 for b in y)
    )
    return 0.0 if denominator == 0.0 else _signed(numerator / denominator)


def _signed(value: float) -> float:
    return max(-1.0, min(1.0, value))


def _unit(value: float) -> float:
    return max(0.0, min(1.0, value))


__all__ = ["produce_free_operational_evidence"]
