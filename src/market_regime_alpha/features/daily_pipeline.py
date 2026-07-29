"""Public-data adapter into the existing frozen R5 Feature materializers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from market_regime_alpha.candidates.contracts import CandidatePopulation
from market_regime_alpha.core.time import AvailabilityTime
from market_regime_alpha.data.providers.public_composite import (
    HISTORICAL_PUBLIC_RETRIEVAL_SEMANTICS_V1,
    PublicBar,
    PublicCompositeProviderResult,
)
from market_regime_alpha.data.rehearsal import (
    RehearsalDailyBar,
    RehearsalDecisionSnapshot,
)
from market_regime_alpha.features.contracts import (
    FeatureDefinition,
    FeatureMaterialization,
)
from market_regime_alpha.features.rehearsal_baselines import (
    materialize_r5_baseline_features,
    r5_baseline_feature_definitions,
)
from market_regime_alpha.data.source_manifest import SourceFieldFinality
from market_regime_alpha.universe.daily_exploratory import (
    DailyUniverseReconciliation,
)


@dataclass(frozen=True, slots=True)
class DailyFeaturePipelineResult:
    population: CandidatePopulation
    definitions: tuple[FeatureDefinition, ...]
    materializations: tuple[FeatureMaterialization, ...]


def materialize_public_daily_baseline_features(
    *,
    reconciliation: DailyUniverseReconciliation,
    provider_result: PublicCompositeProviderResult,
    code_revision: str,
    config_hash: str,
) -> DailyFeaturePipelineResult:
    """Aggregate source bars and invoke existing Feature formulas unchanged."""

    if (
        reconciliation.population.decision_time
        != provider_result.decision_time
    ):
        raise ValueError("Universe and provider Decision Time mismatch")
    population = reconciliation.population
    daily_bars = _daily_bars(provider_result)
    snapshots = tuple(
        RehearsalDecisionSnapshot(
            symbol=item.symbol,
            decision_time=provider_result.decision_time,
            reference_price=float(item.price),
            available_at=item.available_time,
        )
        for item in provider_result.quotes
        if item.symbol in population.symbols
        and item.price is not None
        and item.event_time is not None
        and item.event_time <= provider_result.decision_time.value
        and item.available_time is not None
        and item.available_time.value <= provider_result.decision_time.value
    )
    definitions = r5_baseline_feature_definitions()
    materializations = materialize_r5_baseline_features(
        population=population,
        source_dataset_id=reconciliation.dataset_contract.dataset_id,
        daily_bars=daily_bars,
        decision_snapshots=snapshots,
        code_revision=code_revision,
        config_hash=config_hash,
    )
    return DailyFeaturePipelineResult(
        population=population,
        definitions=definitions,
        materializations=materializations,
    )


def _daily_bars(
    provider_result: PublicCompositeProviderResult,
) -> tuple[RehearsalDailyBar, ...]:
    exploratory_history = (
        HISTORICAL_PUBLIC_RETRIEVAL_SEMANTICS_V1
        in provider_result.limitations
    )
    grouped: dict[tuple[str, date], list[PublicBar]] = {}
    for item in provider_result.bars:
        grouped.setdefault(
            (item.symbol, item.event_time.date()),
            [],
        ).append(item)
    output: list[RehearsalDailyBar] = []
    for (symbol, session_date), raw_items in sorted(grouped.items()):
        items = sorted(raw_items, key=lambda value: value.event_time)
        uses_exploratory_policy = (
            exploratory_history
            and all(
                item.available_time is None
                and item.event_time.date()
                < provider_result.decision_time.value.date()
                for item in items
            )
        )
        if (
            not uses_exploratory_policy
            and any(item.available_time is None for item in items)
        ):
            continue
        available_times = [
            item.available_time for item in items if item.available_time is not None
        ]
        available = (
            AvailabilityTime(provider_result.decision_time.value)
            if uses_exploratory_policy
            else max(available_times, key=lambda value: value.as_utc())
        )
        output.append(
            RehearsalDailyBar(
                symbol=str(symbol),
                session_date=session_date,
                close=float(items[-1].close),
                amount=sum(float(item.amount) for item in items),
                available_at=AvailabilityTime(available.value),
                finalized=uses_exploratory_policy
                or all(
                    item.finality is SourceFieldFinality.FINAL for item in items
                ),
            )
        )
    return tuple(output)
