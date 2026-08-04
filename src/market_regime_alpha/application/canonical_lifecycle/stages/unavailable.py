"""Explicit fail-closed handlers for runtime authorities not configured by a CLI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import NoReturn

from market_regime_alpha.application.canonical_lifecycle.stages.contracts import (
    LifecycleStageContext,
    StageExecutionResult,
    StageMutationKind,
)
from market_regime_alpha.application.canonical_lifecycle.states import (
    LifecycleStageName,
)
from market_regime_alpha.evidence.canonical import require_text


class LifecycleStageUnavailableError(RuntimeError):
    """The process lacks a command-bound Reader or Repository for a stage."""


@dataclass(frozen=True, slots=True)
class UnavailableLifecycleStageHandler:
    """Record a FAILED attempt instead of guessing defaults or publishing success."""

    stage_name: LifecycleStageName
    reason_code: str
    detail: str
    mutation_kind: StageMutationKind = StageMutationKind.READ_ONLY

    def __post_init__(self) -> None:
        if not isinstance(self.stage_name, LifecycleStageName):
            raise TypeError("stage_name must be a LifecycleStageName")
        require_text("reason_code", self.reason_code)
        require_text("detail", self.detail)
        if not isinstance(self.mutation_kind, StageMutationKind):
            raise TypeError("mutation_kind must be a StageMutationKind")

    def recover(self, context: LifecycleStageContext) -> StageExecutionResult | None:
        self._raise(context)

    def execute(self, context: LifecycleStageContext) -> StageExecutionResult:
        self._raise(context)

    def _raise(self, context: LifecycleStageContext) -> NoReturn:
        if not isinstance(context, LifecycleStageContext):
            raise TypeError("context must be a LifecycleStageContext")
        if context.stage_name is not self.stage_name:
            raise ValueError("unavailable handler received the wrong stage context")
        raise LifecycleStageUnavailableError(
            f"{self.reason_code}: {self.stage_name.value}: {self.detail}"
        )
