"""DecisionSystem child for account-neutral Research and Shadow summaries."""

from __future__ import annotations

from typing import Callable

from market_regime_alpha.application.continuous_research.journal import (
    ClaimedRuntimeTick,
    ContinuousChildKind,
)
from market_regime_alpha.application.continuous_research.ports import (
    ChildExecutionRequest,
    ChildExecutionResult,
)
from market_regime_alpha.application.decision_system.postgres_repository import (
    PostgresDecisionSystemRepository,
)
from market_regime_alpha.application.decision_system.research_summary import (
    ResearchDailySummary,
)
from market_regime_alpha.platform.runtime_governance import RuntimeAuthorityMode


ResearchSummaryInputLoader = Callable[
    [ChildExecutionRequest], ResearchDailySummary
]


class ResearchSummaryRuntimeService:
    """Publish the normal Research/Shadow endpoint under the active Tick fence."""

    def __init__(self, repository: PostgresDecisionSystemRepository) -> None:
        self._repository = repository

    def execute(
        self,
        *,
        request: ChildExecutionRequest,
        summary: ResearchDailySummary,
    ) -> ResearchDailySummary:
        if request.authority_mode not in {
            RuntimeAuthorityMode.RESEARCH,
            RuntimeAuthorityMode.SHADOW,
        }:
            raise ValueError(
                "Research Summary Runtime accepts Research/Shadow modes only"
            )
        if (
            summary.runtime_mode is not request.authority_mode
            or summary.run_id != request.run_id
            or summary.tick_id != request.tick_id
            or summary.trading_date != request.trading_date
            or summary.decision_time != request.as_of_time
        ):
            raise ValueError("Research Summary Runtime lineage mismatch")
        return self._repository.save_research_summary(
            summary,
            claim=_claim(request),
        )


class ResearchSummaryDelegate:
    """The DECISION_SYSTEM child in Research and Shadow compositions."""

    child_kind = ContinuousChildKind.DECISION_SYSTEM

    def __init__(
        self,
        service: ResearchSummaryRuntimeService,
        *,
        input_loader: ResearchSummaryInputLoader,
    ) -> None:
        self._service = service
        self._input_loader = input_loader

    def lookup(
        self, request: ChildExecutionRequest
    ) -> ChildExecutionResult | None:
        if request.authority_mode is RuntimeAuthorityMode.PRODUCTION:
            raise ValueError("Production must use the strict Decision Runtime")
        try:
            summary = self._service._repository.get_research_summary_for_tick(
                run_id=request.run_id,
                tick_id=request.tick_id,
                runtime_mode=request.authority_mode,
            )
        except KeyError:
            return None
        return _child_result(request, summary)

    def execute(self, request: ChildExecutionRequest) -> ChildExecutionResult:
        summary = self._service.execute(
            request=request,
            summary=self._input_loader(request),
        )
        return _child_result(request, summary)


def _claim(request: ChildExecutionRequest) -> ClaimedRuntimeTick:
    return ClaimedRuntimeTick(
        run_id=request.run_id,
        tick_id=request.tick_id,
        tick_sequence=request.tick_sequence,
        claim_id=request.claim_id,
        fencing_token=request.fencing_token,
        tick_version=request.tick_version,
        lease_acquired_at=request.lease_acquired_at,
        lease_expires_at=request.lease_expires_at,
        heartbeat_at=request.heartbeat_at,
    )


def _child_result(
    request: ChildExecutionRequest,
    summary: ResearchDailySummary,
) -> ChildExecutionResult:
    return ChildExecutionResult(
        child_kind=ContinuousChildKind.DECISION_SYSTEM,
        child_run_id=summary.run_id,
        child_receipt_id=summary.summary_id,
        child_receipt_hash=summary.content_hash,
        child_artifact_id=summary.summary_id,
        child_artifact_hash=summary.content_hash,
        input_references=request.input_references,
        configuration_references=request.configuration_references,
    )


__all__ = [
    "ResearchSummaryDelegate",
    "ResearchSummaryInputLoader",
    "ResearchSummaryRuntimeService",
]
