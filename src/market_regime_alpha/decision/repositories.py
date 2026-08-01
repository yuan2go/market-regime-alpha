"""Storage-neutral repository protocol for Opportunity and Thesis aggregates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from market_regime_alpha.core.identity import OpportunityId, ThesisId
from market_regime_alpha.decision.opportunity import TradingOpportunity
from market_regime_alpha.decision.thesis import TradingThesis


class DecisionVersionConflictError(RuntimeError):
    """A decision aggregate changed after the caller observed its version."""


@dataclass(frozen=True, slots=True)
class DecisionCommandResult:
    opportunity: TradingOpportunity | None
    thesis: TradingThesis | None


class DecisionLifecycleRepository(Protocol):
    """Allows future PostgreSQL parity without exposing persistence writes."""

    def resolve_command(
        self, *, idempotency_key: str, command_hash: str
    ) -> DecisionCommandResult | None: ...

    def get_opportunity(self, opportunity_id: OpportunityId) -> TradingOpportunity: ...

    def get_thesis(self, thesis_id: ThesisId) -> TradingThesis: ...

    def create_opportunity(
        self,
        opportunity: TradingOpportunity,
        *,
        idempotency_key: str,
        command_hash: str,
    ) -> DecisionCommandResult: ...

    def transition_opportunity(
        self,
        opportunity: TradingOpportunity,
        *,
        expected_version: int,
        idempotency_key: str,
        command_hash: str,
    ) -> DecisionCommandResult: ...

    def confirm_opportunity(
        self,
        opportunity: TradingOpportunity,
        thesis: TradingThesis,
        *,
        expected_version: int,
        idempotency_key: str,
        command_hash: str,
    ) -> DecisionCommandResult: ...

    def transition_thesis(
        self,
        thesis: TradingThesis,
        *,
        expected_version: int,
        idempotency_key: str,
        command_hash: str,
    ) -> DecisionCommandResult: ...
