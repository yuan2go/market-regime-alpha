"""Thin stage-adapter contracts for the canonical lifecycle runner."""

from market_regime_alpha.application.canonical_lifecycle.stages.contracts import (
    LifecycleStageContext,
    LifecycleStageHandler,
    StageExecutionResult,
    StageMutationKind,
)

__all__ = [
    "LifecycleStageContext",
    "LifecycleStageHandler",
    "StageExecutionResult",
    "StageMutationKind",
]
