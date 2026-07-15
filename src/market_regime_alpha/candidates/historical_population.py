"""Candidate Population assembly from identified historical Universe and Eligibility artifacts.

Universe owns membership. Universe eligibility artifacts own explicit policy results. Candidate
Discovery owns the intersection that creates the complete opportunity population for one
Decision Time.
"""

from __future__ import annotations

from market_regime_alpha.candidates.contracts import CandidatePopulation, build_candidate_population
from market_regime_alpha.core.time import DecisionTime
from market_regime_alpha.universe.artifacts import HistoricalPITUniverseArtifact
from market_regime_alpha.universe.eligibility_artifacts import HistoricalTradingEligibilityArtifact


def build_candidate_population_from_historical_artifacts(
    *,
    universe_artifact: HistoricalPITUniverseArtifact,
    eligibility_artifact: HistoricalTradingEligibilityArtifact,
    decision_time: DecisionTime,
) -> CandidatePopulation:
    """Intersect exact-date membership with exact-time eligibility for one Decision Time."""

    universe = universe_artifact.snapshot_for_decision_time(decision_time)
    eligibility = eligibility_artifact.snapshot_for_decision_time(decision_time)
    return build_candidate_population(universe, eligibility, decision_time=decision_time)
