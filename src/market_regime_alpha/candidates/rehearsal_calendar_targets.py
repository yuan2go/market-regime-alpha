"""Calendar-resolved R5 opportunity Target materialization."""

from __future__ import annotations

from market_regime_alpha.candidates.contracts import CandidatePopulation
from market_regime_alpha.candidates.rehearsal_opportunity_targets import (
    materialize_r5_next_session_opportunity_targets,
)
from market_regime_alpha.candidates.target_bundle import TargetMaterializationBundle
from market_regime_alpha.core.identity import DatasetId
from market_regime_alpha.core.time import AsOfTime
from market_regime_alpha.data.rehearsal import RehearsalDecisionSnapshot, RehearsalNextSessionBar
from market_regime_alpha.data.trading_calendar import TradingCalendarArtifact


def materialize_r5_opportunity_targets_from_calendar(
    *,
    population: CandidatePopulation,
    calendar: TradingCalendarArtifact,
    source_dataset_id: DatasetId,
    decision_snapshots: tuple[RehearsalDecisionSnapshot, ...],
    next_session_bars: tuple[RehearsalNextSessionBar, ...],
    materialized_at: AsOfTime,
    code_revision: str,
    config_hash: str,
) -> TargetMaterializationBundle:
    """Resolve the next trading session from the identified calendar artifact."""

    next_session_date = calendar.resolve_next_session_date(population.decision_time)
    return materialize_r5_next_session_opportunity_targets(
        population=population,
        source_dataset_id=source_dataset_id,
        decision_snapshots=decision_snapshots,
        next_session_date=next_session_date,
        next_session_bars=next_session_bars,
        materialized_at=materialized_at,
        code_revision=code_revision,
        config_hash=config_hash,
    )
