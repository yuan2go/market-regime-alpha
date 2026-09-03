"""Narrow composition contracts for Runtime-backed Backtest actions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from market_regime_alpha.research_qualification.domain.backtest import (
    BacktestSpecification,
)
from market_regime_alpha.research_qualification.domain.backtest_execution import (
    BacktestExpectedAction,
)
from market_regime_alpha.runtime.domain import ExternalEffectClass
from market_regime_alpha.runtime.ports import AttemptClaim
from market_regime_alpha.shared.identity import ContentHash


@dataclass(frozen=True, slots=True)
class BacktestRuntimeStep:
    step_key: str
    step_kind: str
    request_sha256: ContentHash | str
    external_effect_class: ExternalEffectClass = ExternalEffectClass.NONE

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "request_sha256",
            ContentHash(str(self.request_sha256)),
        )


class BacktestSpecificationReadPort(Protocol):
    def load_specification(
        self,
        exploratory_backtest_run_id,
    ) -> BacktestSpecification: ...


class BacktestCanonicalStepHandler(Protocol):
    """Execute closed, typed steps through their canonical owner Applications."""

    def requested_at(
        self,
        specification: BacktestSpecification,
        action: BacktestExpectedAction,
    ) -> datetime: ...

    def decision_time(
        self,
        specification: BacktestSpecification,
        action: BacktestExpectedAction,
    ) -> datetime | None: ...

    def steps(
        self,
        specification: BacktestSpecification,
        action: BacktestExpectedAction,
    ) -> tuple[BacktestRuntimeStep, ...]: ...

    def execute_step(
        self,
        specification: BacktestSpecification,
        action: BacktestExpectedAction,
        claim: AttemptClaim,
    ) -> None: ...


__all__ = [
    "BacktestCanonicalStepHandler",
    "BacktestRuntimeStep",
    "BacktestSpecificationReadPort",
]
