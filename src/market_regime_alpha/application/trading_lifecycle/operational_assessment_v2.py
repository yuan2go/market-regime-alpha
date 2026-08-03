"""Thin V2-only Holding/Exit assessment adapter over derived H5 evidence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from market_regime_alpha.decision.opportunity import DecisionEvidenceReference
from market_regime_alpha.decision.thesis import TradingThesis
from market_regime_alpha.portfolio.lifecycle import PortfolioDecision, RiskDecision
from market_regime_alpha.position.assessment import (
    ExitAssessment,
    ExitAssessmentModel,
    HoldingAssessment,
    HoldingAssessmentModel,
    PositionLifecycleConfig,
    ResolvedThesisHealthContext,
    ThesisHealth,
)
from market_regime_alpha.position.authority import PositionSnapshot, PositionState
from market_regime_alpha.position.thesis_health import ThesisHealthObservationV2


@dataclass(frozen=True, slots=True)
class OperationalPositionAssessmentV2:
    holding_assessment: HoldingAssessment
    exit_assessment: ExitAssessment
    mode: str = "ASSESSMENT_ONLY"
    execution_boundary: str = "NO_TRADE_ACTION_CREATED"
    trading_authority: str = "TRADING_AUTHORITY_NOT_GRANTED"

    def __post_init__(self) -> None:
        if (
            self.mode != "ASSESSMENT_ONLY"
            or self.execution_boundary != "NO_TRADE_ACTION_CREATED"
            or self.trading_authority != "TRADING_AUTHORITY_NOT_GRANTED"
        ):
            raise ValueError("V2 operational assessment authority cannot be inflated")


class OperationalPositionAssessmentServiceV2:
    """Assess only; never transition Thesis, create H4, or create execution."""

    def assess(
        self,
        *,
        thesis: TradingThesis,
        position: PositionSnapshot,
        health_observation: ThesisHealthObservationV2,
        configuration: PositionLifecycleConfig,
        assessed_at: datetime,
        actor: str,
        reason: str,
        add_portfolio: PortfolioDecision | None = None,
        add_risk: RiskDecision | None = None,
    ) -> OperationalPositionAssessmentV2:
        if not isinstance(health_observation, ThesisHealthObservationV2):
            raise TypeError("V2 service requires ThesisHealthObservationV2")
        observation = ThesisHealthObservationV2.from_canonical_dict(
            health_observation.to_canonical_dict()
        )
        if (
            observation.thesis_id != thesis.thesis_id
            or observation.thesis_version != thesis.version
            or observation.opportunity_id != thesis.opportunity_id
            or observation.symbol != thesis.symbol
        ):
            raise ValueError("V2 health Observation Thesis scope mismatch")
        if assessed_at.tzinfo is None or assessed_at.utcoffset() is None:
            raise ValueError("assessment time must be timezone-aware")
        if observation.assessed_at > assessed_at:
            raise ValueError("assessment cannot consume future V2 health evidence")
        if observation.market_price is None:
            raise ValueError(
                "V2 Holding/Exit assessment requires established market price"
            )
        health = observation.effective_health_state
        reasons = set(observation.reason_codes)
        reasons.update(observation.missing_reason_codes)
        if health is None:
            health = ThesisHealth.DATA_INSUFFICIENT
            reasons.add("EFFECTIVE_THESIS_HEALTH_NOT_ESTABLISHED")
        if position.state is PositionState.RECONCILIATION_REQUIRED:
            health = ThesisHealth.DATA_INSUFFICIENT
            reasons.add("POSITION_RECONCILIATION_REQUIRED")
        context = ResolvedThesisHealthContext(
            health=health,
            market_price=observation.market_price,
            evidence=DecisionEvidenceReference(
                artifact_type="THESIS_HEALTH_OBSERVATION_V2",
                artifact_id=observation.observation_id,
                content_hash=observation.content_hash,
                status="VERIFIED_EXPLORATORY",
            ),
            reason_codes=tuple(sorted(reasons)),
        )
        holding = HoldingAssessmentModel().assess_resolved(
            thesis,
            position,
            context,
            configuration,
            assessed_at=assessed_at,
            actor=actor,
            reason=reason,
            add_portfolio=add_portfolio,
            add_risk=add_risk,
        )
        exit_assessment = ExitAssessmentModel().assess_resolved(
            thesis,
            position,
            context,
            configuration,
            assessed_at=assessed_at,
            actor=actor,
            reason=reason,
        )
        return OperationalPositionAssessmentV2(
            holding_assessment=holding,
            exit_assessment=exit_assessment,
        )
