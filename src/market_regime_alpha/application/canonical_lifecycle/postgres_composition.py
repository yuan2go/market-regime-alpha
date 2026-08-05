"""PostgreSQL composition root for the canonical lifecycle stage graph."""

from __future__ import annotations

from datetime import datetime
from typing import Callable

from market_regime_alpha.application.canonical_lifecycle.commands import (
    CanonicalLifecycleCommand,
)
from market_regime_alpha.application.canonical_lifecycle.input_manifest import (
    CanonicalLifecycleInputManifest,
)
from market_regime_alpha.application.canonical_lifecycle.postgres_repository import (
    PostgresLifecycleRunRepository,
)
from market_regime_alpha.application.canonical_lifecycle.runner import (
    CanonicalDecisionLifecycleRunner,
)
from market_regime_alpha.application.canonical_lifecycle.runtime_configuration import (
    RuntimeConfigurationSet,
)
from market_regime_alpha.application.canonical_lifecycle.sqlite_composition import (
    _build_handlers,
)
from market_regime_alpha.application.canonical_lifecycle.stages.assessment import (
    ThesisHealthStageHandler,
)
from market_regime_alpha.application.canonical_lifecycle.stages.contracts import (
    LifecycleStageHandler,
)
from market_regime_alpha.application.canonical_lifecycle.stages.decision_risk import (
    OpportunityStageHandler,
    PortfolioRiskStageHandler,
    ThesisStageHandler,
)
from market_regime_alpha.application.canonical_lifecycle.stages.execution_position import (
    FillPositionStageHandler,
    ManualConfirmationStageHandler,
    ManualTradeStageHandler,
)
from market_regime_alpha.application.canonical_lifecycle.stages.risk_reduction import (
    RiskReductionStageHandler,
)
from market_regime_alpha.application.canonical_lifecycle.states import (
    LIFECYCLE_STAGE_ORDER,
    LifecycleStageName,
)
from market_regime_alpha.application.operational_research.postgres_composite_repository import (
    PostgresCompositeOperationalRepository,
)
from market_regime_alpha.application.trading_lifecycle.postgres_risk_reduction import (
    PostgresRiskReductionManualIntentRepository,
)
from market_regime_alpha.decision.postgres_repository import (
    PostgresDecisionLifecycleRepository,
)
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from market_regime_alpha.portfolio.postgres_repository import (
    PostgresCompleteAccountPortfolioRiskRepository,
    PostgresRiskRouteRepository,
)
from market_regime_alpha.position.postgres_thesis_health import (
    PostgresThesisHealthRepository,
)


Clock = Callable[[], datetime]


def build_postgres_lifecycle_runner(
    *,
    repository: PostgresLifecycleRunRepository,
    factory: PostgresConnectionFactory,
    command: CanonicalLifecycleCommand,
    manifest: CanonicalLifecycleInputManifest | None,
    configurations: RuntimeConfigurationSet,
    clock: Clock,
) -> CanonicalDecisionLifecycleRunner:
    """Build the 16-stage graph with one PostgreSQL authority schema."""

    base_handlers = _build_handlers(
        command=command,
        manifest=manifest,
        configurations=configurations,
        authority_binder=None,
    )
    handlers = postgres_lifecycle_stage_handlers(
        factory=factory,
        base_handlers=base_handlers,
    )
    return CanonicalDecisionLifecycleRunner(
        repository=repository,
        handlers=handlers,
        clock=clock,
    )


def postgres_lifecycle_stage_handlers(
    *,
    factory: PostgresConnectionFactory,
    base_handlers: tuple[LifecycleStageHandler, ...],
) -> tuple[LifecycleStageHandler, ...]:
    """Bind domain-authority stages without a SQLite compatibility path."""

    if len(base_handlers) != len(LIFECYCLE_STAGE_ORDER):
        raise ValueError("base_handlers must cover the canonical 16-stage graph")
    handlers = dict(zip(LIFECYCLE_STAGE_ORDER, base_handlers, strict=True))
    decision_repository = PostgresDecisionLifecycleRepository(factory)
    portfolio_repository = PostgresCompleteAccountPortfolioRiskRepository(factory)
    risk_repository = PostgresRiskRouteRepository(factory)
    execution_repository = PostgresRiskReductionManualIntentRepository(factory)
    thesis_health_repository = PostgresThesisHealthRepository(factory)
    composite_repository = PostgresCompositeOperationalRepository(factory)
    handlers[LifecycleStageName.OPPORTUNITY] = OpportunityStageHandler(
        repository=decision_repository
    )
    handlers[LifecycleStageName.THESIS] = ThesisStageHandler(
        repository=decision_repository
    )
    handlers[LifecycleStageName.PORTFOLIO_RISK] = PortfolioRiskStageHandler(
        repository=portfolio_repository
    )
    handlers[LifecycleStageName.RISK_REDUCTION] = RiskReductionStageHandler(
        risk_repository=risk_repository,
        execution_repository=execution_repository,
        decision_repository=decision_repository,
        thesis_health_repository=thesis_health_repository,
        composite_repository=composite_repository,
    )
    handlers[LifecycleStageName.MANUAL_CONFIRMATION] = (
        ManualConfirmationStageHandler(repository=execution_repository)
    )
    handlers[LifecycleStageName.MANUAL_TRADE] = ManualTradeStageHandler(
        repository=execution_repository
    )
    handlers[LifecycleStageName.FILL_POSITION] = FillPositionStageHandler(
        repository=execution_repository
    )
    handlers[LifecycleStageName.THESIS_HEALTH] = ThesisHealthStageHandler(
        repository=thesis_health_repository
    )
    return tuple(handlers[stage] for stage in LIFECYCLE_STAGE_ORDER)


__all__ = [
    "build_postgres_lifecycle_runner",
    "postgres_lifecycle_stage_handlers",
]
