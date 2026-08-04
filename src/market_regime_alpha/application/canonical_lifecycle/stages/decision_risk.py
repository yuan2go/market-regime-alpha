"""Fail-closed Decision and complete-account Portfolio/Risk stage adapters.

The canonical command does not yet carry authenticated Thesis approval or all
position-authoritative inputs needed to construct a new Portfolio/Risk result.
These handlers load exact durable authorities when command-bound and otherwise
stop without inventing business inputs.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from market_regime_alpha.application.canonical_lifecycle.contracts import (
    LifecycleObjectId,
    LifecycleObjectReference,
    LifecycleObjectType,
    LifecycleReaderKind,
)
from market_regime_alpha.application.canonical_lifecycle.stages.contracts import (
    LifecycleStageContext,
    StageExecutionResult,
    StageMutationKind,
)
from market_regime_alpha.application.canonical_lifecycle.stages.evidence import (
    ordered_references,
    references_for_type,
    require_single_reference,
)
from market_regime_alpha.application.canonical_lifecycle.states import (
    LifecycleRunStatus,
    LifecycleStageName,
    LifecycleStageStatus,
)
from market_regime_alpha.core.identity import (
    OpportunityId,
    PortfolioDecisionId,
    RiskDecisionId,
    StableId,
    ThesisId,
)
from market_regime_alpha.decision.opportunity import (
    OpportunityState,
    TradingOpportunity,
)
from market_regime_alpha.decision.repositories import DecisionLifecycleRepository
from market_regime_alpha.decision.thesis import ThesisState, TradingThesis
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.portfolio.account_authority import (
    CompleteAccountPortfolioDecision,
    CompleteAccountRiskDecision,
)
from market_regime_alpha.portfolio.lifecycle import RiskDecisionState
from market_regime_alpha.portfolio.repositories import (
    CompleteAccountPortfolioRiskRepository,
)


class OpportunityStageHandler:
    """Load an existing durable Opportunity or stop for missing creation inputs."""

    stage_name = LifecycleStageName.OPPORTUNITY
    mutation_kind = StageMutationKind.READ_ONLY

    def __init__(self, *, repository: DecisionLifecycleRepository) -> None:
        self._repository = repository

    def recover(self, context: LifecycleStageContext) -> StageExecutionResult | None:
        return self.execute(context)

    def execute(self, context: LifecycleStageContext) -> StageExecutionResult:
        references = references_for_type(context, LifecycleObjectType.OPPORTUNITY)
        evidence_inputs = _decision_evidence_references(context)
        if not references:
            return _waiting(
                inputs=evidence_inputs,
                reasons=(
                    "OPPORTUNITY_CREATION_AUTHORITY_REQUIRED",
                    "OPPORTUNITY_VALIDITY_AND_ACTOR_NOT_PERSISTED",
                ),
                blocker=(
                    "Opportunity creation requires persisted validity, actor, and "
                    "reason semantics"
                ),
            )
        if len(references) != 1:
            raise ValueError("Opportunity stage requires at most one Opportunity")
        reference = references[0]
        opportunity = self._repository.get_opportunity(
            OpportunityId(str(reference.object_id))
        )
        _verify_domain_reference(
            reference,
            object_id=opportunity.opportunity_id,
            payload=opportunity.to_canonical_dict(),
        )
        if opportunity.updated_at > context.run.as_of_time:
            raise ValueError("Opportunity was not available by lifecycle as-of time")
        if opportunity.valid_until < context.run.as_of_time:
            return _waiting(
                inputs=ordered_references((*evidence_inputs, reference)),
                reasons=("OPPORTUNITY_EXPIRED",),
                blocker="The command-bound Opportunity expired before lifecycle as-of",
            )
        return StageExecutionResult(
            stage_status=LifecycleStageStatus.COMPLETED,
            run_status=LifecycleRunStatus.RUNNING,
            input_references=ordered_references((*evidence_inputs, reference)),
            output_references=(reference,),
            model_versions=tuple(
                sorted(
                    {
                        (
                            str(opportunity.signal_model.model_id),
                            opportunity.signal_model.model_version,
                        ),
                        (
                            str(opportunity.forecast_model.model_id),
                            opportunity.forecast_model.model_version,
                        ),
                    }
                )
            ),
            configuration_hashes=tuple(
                sorted(
                    {
                        opportunity.signal_model.configuration_hash,
                        opportunity.forecast_model.configuration_hash,
                    }
                )
            ),
            reason_codes=(
                "DURABLE_OPPORTUNITY_AUTHORITY_VERIFIED",
                f"OPPORTUNITY_STATE_{opportunity.state.value}",
            ),
            blocker_reason=None,
        )


class ThesisStageHandler:
    """Load an already approved Thesis; never manufacture human approval."""

    stage_name = LifecycleStageName.THESIS
    mutation_kind = StageMutationKind.READ_ONLY

    def __init__(self, *, repository: DecisionLifecycleRepository) -> None:
        self._repository = repository

    def recover(self, context: LifecycleStageContext) -> StageExecutionResult | None:
        return self.execute(context)

    def execute(self, context: LifecycleStageContext) -> StageExecutionResult:
        opportunity_reference = require_single_reference(
            context, LifecycleObjectType.OPPORTUNITY
        )
        opportunity = self._repository.get_opportunity(
            OpportunityId(str(opportunity_reference.object_id))
        )
        _verify_domain_reference(
            opportunity_reference,
            object_id=opportunity.opportunity_id,
            payload=opportunity.to_canonical_dict(),
        )
        thesis_references = references_for_type(context, LifecycleObjectType.THESIS)
        if not thesis_references:
            return _waiting(
                inputs=(opportunity_reference,),
                reasons=("THESIS_APPROVAL_AUTHORITY_REQUIRED",),
                blocker=(
                    "The lifecycle cannot approve a Thesis without a persisted "
                    "human approval authority"
                ),
            )
        if len(thesis_references) != 1:
            raise ValueError("Thesis stage requires at most one Thesis")
        thesis_reference = thesis_references[0]
        thesis = self._repository.get_thesis(ThesisId(str(thesis_reference.object_id)))
        _verify_domain_reference(
            thesis_reference,
            object_id=thesis.thesis_id,
            payload=thesis.to_canonical_dict(),
        )
        _verify_thesis_scope(thesis, opportunity, context.run.as_of_time)
        return StageExecutionResult(
            stage_status=LifecycleStageStatus.COMPLETED,
            run_status=LifecycleRunStatus.RUNNING,
            input_references=ordered_references(
                (opportunity_reference, thesis_reference)
            ),
            output_references=(thesis_reference,),
            model_versions=(),
            configuration_hashes=(),
            reason_codes=(
                "DURABLE_THESIS_APPROVAL_AUTHORITY_VERIFIED",
                f"THESIS_STATE_{thesis.state.value}",
            ),
            blocker_reason=None,
        )


class PortfolioRiskStageHandler:
    """Load complete-account Portfolio/Risk authorities or fail closed."""

    stage_name = LifecycleStageName.PORTFOLIO_RISK
    mutation_kind = StageMutationKind.READ_ONLY

    def __init__(self, *, repository: CompleteAccountPortfolioRiskRepository) -> None:
        self._repository = repository

    def recover(self, context: LifecycleStageContext) -> StageExecutionResult | None:
        return self.execute(context)

    def execute(self, context: LifecycleStageContext) -> StageExecutionResult:
        thesis_references = references_for_type(context, LifecycleObjectType.THESIS)
        portfolio_references = references_for_type(
            context, LifecycleObjectType.PORTFOLIO_DECISION
        )
        risk_references = references_for_type(
            context, LifecycleObjectType.RISK_DECISION
        )
        if not portfolio_references and not risk_references:
            return _waiting(
                inputs=thesis_references,
                reasons=(
                    "PORTFOLIO_RISK_DATA_INSUFFICIENT",
                    "POSITION_AUTHORITATIVE_COMPLETE_ACCOUNT_INPUTS_REQUIRED",
                ),
                blocker=(
                    "Complete-account Fill-derived positions, valuations, allocations, "
                    "and versioned Risk configuration are not command-bound"
                ),
            )
        if len(portfolio_references) != 1 or len(risk_references) != 1:
            raise ValueError(
                "Portfolio/Risk stage requires one Portfolio and one Risk reference"
            )
        portfolio_reference = portfolio_references[0]
        risk_reference = risk_references[0]
        portfolio = self._repository.get_complete_account_portfolio(
            PortfolioDecisionId(str(portfolio_reference.object_id))
        )
        risk = self._repository.get_complete_account_risk(
            RiskDecisionId(str(risk_reference.object_id))
        )
        _verify_domain_reference(
            portfolio_reference,
            object_id=portfolio.decision_id,
            payload=portfolio.to_canonical_dict(),
        )
        _verify_domain_reference(
            risk_reference,
            object_id=risk.risk_decision_id,
            payload=risk.to_canonical_dict(),
        )
        _verify_complete_account_scope(
            context=context,
            portfolio=portfolio,
            risk=risk,
            thesis_references=thesis_references,
        )
        inputs = ordered_references(
            (*thesis_references, portfolio_reference, risk_reference)
        )
        if risk.state is not RiskDecisionState.APPROVED:
            return _waiting(
                inputs=inputs,
                reasons=tuple(
                    sorted(
                        {
                            "PORTFOLIO_RISK_NOT_APPROVED",
                            f"RISK_STATE_{risk.state.value}",
                            *risk.reason_codes,
                        }
                    )
                ),
                blocker="The complete-account Risk authority did not approve manual intent",
            )
        return StageExecutionResult(
            stage_status=LifecycleStageStatus.COMPLETED,
            run_status=LifecycleRunStatus.RUNNING,
            input_references=inputs,
            output_references=(portfolio_reference, risk_reference),
            model_versions=(),
            configuration_hashes=(risk.configuration_hash,),
            reason_codes=tuple(
                sorted(
                    {
                        "COMPLETE_ACCOUNT_PORTFOLIO_RISK_AUTHORITY_VERIFIED",
                        *risk.reason_codes,
                    }
                )
            ),
            blocker_reason=None,
        )


def _decision_evidence_references(
    context: LifecycleStageContext,
) -> tuple[LifecycleObjectReference, ...]:
    return ordered_references(
        tuple(
            reference
            for object_type in (
                LifecycleObjectType.PLATFORM_RESEARCH_ARTIFACT,
                LifecycleObjectType.SIGNAL_ARTIFACT,
                LifecycleObjectType.PATH_FORECAST_ARTIFACT,
            )
            for reference in references_for_type(context, object_type)
        )
    )


def _waiting(
    *,
    inputs: tuple[LifecycleObjectReference, ...],
    reasons: tuple[str, ...],
    blocker: str,
) -> StageExecutionResult:
    return StageExecutionResult(
        stage_status=LifecycleStageStatus.WAITING,
        run_status=LifecycleRunStatus.WAITING_FOR_MANUAL_CONFIRMATION,
        input_references=ordered_references(inputs),
        output_references=(),
        model_versions=(),
        configuration_hashes=(),
        reason_codes=tuple(sorted(set(reasons))),
        blocker_reason=blocker,
    )


def _verify_domain_reference(
    reference: LifecycleObjectReference,
    *,
    object_id: StableId,
    payload: Mapping[str, Any],
) -> None:
    if (
        str(reference.object_id) != str(object_id)
        or reference.content_hash != canonical_hash(payload)
    ):
        raise ValueError(f"{reference.object_type.value} reference mismatch")


def _verify_thesis_scope(
    thesis: TradingThesis,
    opportunity: TradingOpportunity,
    as_of: datetime,
) -> None:
    required = {
        (opportunity.candidate_set.artifact_id, opportunity.candidate_set.content_hash),
        (opportunity.signal_snapshot.artifact_id, opportunity.signal_snapshot.content_hash),
        (opportunity.path_forecast.artifact_id, opportunity.path_forecast.content_hash),
    }
    actual = {(item.artifact_id, item.content_hash) for item in thesis.supporting_evidence}
    if (
        thesis.opportunity_id != opportunity.opportunity_id
        or thesis.symbol != opportunity.symbol
        or opportunity.state is not OpportunityState.CONFIRMED_TO_THESIS
        or thesis.state is not ThesisState.APPROVED
        or not required.issubset(actual)
        or thesis.updated_at > as_of
        or thesis.time_invalidation <= as_of
    ):
        raise ValueError("command-bound Thesis approval scope or validity mismatch")


def _verify_complete_account_scope(
    *,
    context: LifecycleStageContext,
    portfolio: CompleteAccountPortfolioDecision,
    risk: CompleteAccountRiskDecision,
    thesis_references: tuple[LifecycleObjectReference, ...],
) -> None:
    thesis_ids = tuple(
        sorted(
            (ThesisId(str(item.object_id)) for item in thesis_references), key=str
        )
    )
    if (
        portfolio.thesis_ids != thesis_ids
        or risk.portfolio_decision_id != portfolio.decision_id
        or risk.portfolio_decision_version != portfolio.version
        or risk.post_trade_snapshot_id != portfolio.post_trade.snapshot_id
        or risk.post_trade_content_hash != portfolio.post_trade.content_hash
        or risk.configuration_id != portfolio.configuration.configuration_id
        or risk.configuration_hash != portfolio.configuration.configuration_hash
        or portfolio.account_snapshot.as_of > context.run.as_of_time
        or portfolio.created_at > context.run.as_of_time
        or risk.completed_at > context.run.as_of_time
    ):
        raise ValueError("complete-account Portfolio/Risk lineage mismatch")


def repository_output_reference(
    *,
    object_type: LifecycleObjectType,
    object_id: StableId,
    payload: Mapping[str, Any],
    reader_kind: LifecycleReaderKind,
    available_at: datetime,
) -> LifecycleObjectReference:
    """Build an exact repository-bound reference for commands and tests."""

    canonical_available_at = available_at.astimezone(timezone.utc)
    if canonical_available_at.microsecond:
        raise ValueError("repository output available_at must have second precision")
    return LifecycleObjectReference(
        object_type=object_type,
        object_id=LifecycleObjectId(str(object_id)),
        content_hash=canonical_hash(payload),
        reader_kind=reader_kind,
        locator=None,
        available_at=canonical_available_at,
    )
