"""Application orchestration for one H5 artifact-derived health command."""

from __future__ import annotations

from datetime import datetime

from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.daily_decision import DecisionPriceSnapshot
from market_regime_alpha.decision import TradingOpportunity, TradingThesis
from market_regime_alpha.forecasting import PathForecast
from market_regime_alpha.position.thesis_health import (
    ManualInvalidationEvidence,
    ThesisHealthInputBundle,
    ThesisHealthObservationBuilder,
    ThesisHealthObservationV2,
    ThesisHealthRepository,
    ThesisHealthRuleConfiguration,
    ThesisInvalidationRuleSet,
    thesis_health_command_hash,
)
from market_regime_alpha.research.candidate_discovery import CandidateSet
from market_regime_alpha.research.capital_evolution import CapitalEvolutionSnapshot
from market_regime_alpha.research.market_regime import MarketRegimeSnapshot
from market_regime_alpha.research.theme_rotation import ThemeRotationSnapshot
from market_regime_alpha.signals import SignalSnapshot


class ThesisHealthApplicationService:
    """Build and atomically persist a V2 Observation; create no trade action."""

    def __init__(self, repository: ThesisHealthRepository) -> None:
        self._repository = repository

    def assess(
        self,
        *,
        thesis: TradingThesis,
        opportunity: TradingOpportunity,
        market_regime: MarketRegimeSnapshot,
        theme_rotation: ThemeRotationSnapshot,
        capital_evolution: CapitalEvolutionSnapshot,
        candidate_set: CandidateSet,
        signal_snapshot: SignalSnapshot,
        path_forecast: PathForecast,
        price_snapshot: DecisionPriceSnapshot,
        configuration: ThesisHealthRuleConfiguration,
        rule_set: ThesisInvalidationRuleSet,
        manual_evidence: tuple[ManualInvalidationEvidence, ...],
        expected_prior_observation_id: ArtifactId | None,
        expected_prior_observation_hash: str | None,
        assessed_at: datetime,
        actor: str,
        reason: str,
        idempotency_key: str,
    ) -> ThesisHealthObservationV2:
        if (expected_prior_observation_id is None) != (
            expected_prior_observation_hash is None
        ):
            raise ValueError(
                "expected prior Observation ID and hash must be supplied together"
            )
        prior = (
            self._repository.get_observation(expected_prior_observation_id)
            if expected_prior_observation_id is not None
            else None
        )
        if (
            prior is not None
            and prior.content_hash != expected_prior_observation_hash
        ):
            raise ValueError("expected prior Observation hash mismatch")
        bundle = ThesisHealthInputBundle.create(
            thesis=thesis,
            opportunity=opportunity,
            market_regime=market_regime,
            theme_rotation=theme_rotation,
            capital_evolution=capital_evolution,
            candidate_set=candidate_set,
            signal_snapshot=signal_snapshot,
            path_forecast=path_forecast,
            price_snapshot=price_snapshot,
            configuration=configuration,
            rule_set=rule_set,
            manual_evidence=manual_evidence,
            prior_observation=prior,
            assessed_at=assessed_at,
            actor=actor,
            reason=reason,
        )
        try:
            bundle.rule_set.validate_for(bundle.thesis)
        except ValueError as error:
            raise ValueError(
                "THESIS_INVALIDATION_RULESET_NOT_ESTABLISHED"
            ) from error
        bundle = ThesisHealthInputBundle.from_canonical_dict(
            bundle.to_canonical_dict()
        )
        command_hash = thesis_health_command_hash(bundle)
        replay = self._repository.resolve_command(
            idempotency_key=idempotency_key,
            command_hash=command_hash,
        )
        if replay is not None:
            return replay
        latest = self._repository.get_latest_observation(bundle.thesis.thesis_id)
        prior = bundle.prior_observation
        if latest is None and prior is not None:
            raise ValueError("prior Thesis health Observation is not stored")
        if latest is not None and prior is None:
            raise ValueError("Thesis health command omits the latest prior Observation")
        if latest is not None and prior != latest:
            raise ValueError("Thesis health command does not bind latest prior Observation")
        observation = ThesisHealthObservationBuilder().build(bundle)
        return self._repository.save_observation(
            observation,
            input_bundle=bundle,
            idempotency_key=idempotency_key,
            command_hash=command_hash,
        )
