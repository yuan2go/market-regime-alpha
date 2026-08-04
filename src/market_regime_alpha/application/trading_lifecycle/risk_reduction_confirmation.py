"""ID-only H4.5 application boundary for manual risk-reduction intent."""

from __future__ import annotations

from datetime import datetime

from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.data.trading_calendar import TradingCalendarArtifact
from market_regime_alpha.execution.repositories import (
    RiskReductionManualIntentRepository,
)
from market_regime_alpha.execution.risk_reduction import (
    RiskReductionConfirmationCommand,
    RiskReductionConfirmationPolicy,
    RiskReductionConfirmationResult,
)
from market_regime_alpha.portfolio.risk_routes import (
    ReducingExecutionObservation,
)
from market_regime_alpha.position.authority import SymbolTradingSessionStatus


class RiskReductionConfirmationIdempotencyConflict(ValueError):
    """An H4.5 idempotency key was reused for different command semantics."""


class RiskReductionConfirmationApplicationService:
    """Canonicalize caller evidence; repository reloads every durable authority."""

    def __init__(self, repository: RiskReductionManualIntentRepository) -> None:
        self._repository = repository

    def confirm(
        self,
        *,
        risk_reducing_decision_id: ArtifactId,
        risk_reducing_decision_hash: str,
        exit_directive_id: ArtifactId,
        exit_directive_hash: str,
        thesis_health_observation_id: ArtifactId,
        thesis_health_observation_hash: str,
        composite_manifest_id: ArtifactId,
        composite_manifest_hash: str,
        trading_calendar: TradingCalendarArtifact,
        symbol_trading_statuses: tuple[SymbolTradingSessionStatus, ...],
        execution_observation: ReducingExecutionObservation,
        confirmation_policy: RiskReductionConfirmationPolicy,
        expected_price_lower: float,
        expected_price_upper: float,
        confirmed_at: datetime,
        actor: str,
        reason: str,
        idempotency_key: str,
    ) -> RiskReductionConfirmationResult:
        restored_calendar = TradingCalendarArtifact.from_canonical_dict(
            trading_calendar.to_canonical_dict()
        )
        restored_statuses = tuple(
            SymbolTradingSessionStatus.from_canonical_dict(
                item.to_canonical_dict()
            )
            for item in symbol_trading_statuses
        )
        restored_observation = ReducingExecutionObservation.from_canonical_dict(
            execution_observation.to_canonical_dict()
        )
        restored_policy = RiskReductionConfirmationPolicy.from_canonical_dict(
            confirmation_policy.to_canonical_dict()
        )
        return self._repository.confirm_risk_reduction(
            RiskReductionConfirmationCommand(
                risk_reducing_decision_id=risk_reducing_decision_id,
                risk_reducing_decision_hash=risk_reducing_decision_hash,
                exit_directive_id=exit_directive_id,
                exit_directive_hash=exit_directive_hash,
                thesis_health_observation_id=thesis_health_observation_id,
                thesis_health_observation_hash=thesis_health_observation_hash,
                composite_manifest_id=composite_manifest_id,
                composite_manifest_hash=composite_manifest_hash,
                trading_calendar=restored_calendar,
                symbol_trading_statuses=restored_statuses,
                execution_observation=restored_observation,
                confirmation_policy=restored_policy,
                expected_price_lower=expected_price_lower,
                expected_price_upper=expected_price_upper,
                confirmed_at=confirmed_at,
                actor=actor,
                reason=reason,
                idempotency_key=idempotency_key,
            )
        )
