"""SQLite composition root for the canonical lifecycle stage graph."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Callable

from market_regime_alpha.application.canonical_lifecycle.commands import (
    CanonicalLifecycleCommand,
)
from market_regime_alpha.application.canonical_lifecycle.composition import (
    build_lifecycle_stage_handlers,
)
from market_regime_alpha.application.canonical_lifecycle.input_manifest import (
    CanonicalLifecycleInputManifest,
)
from market_regime_alpha.application.canonical_lifecycle.runner import (
    CanonicalDecisionLifecycleRunner,
)
from market_regime_alpha.application.canonical_lifecycle.runtime_configuration import (
    RuntimeConfigurationSet,
)
from market_regime_alpha.application.canonical_lifecycle.repositories import (
    LifecycleRunRepository,
)
from market_regime_alpha.application.canonical_lifecycle.stages.assessment import (
    ExitAssessmentStageHandler,
    HoldingAssessmentStageHandler,
    OutcomeReviewStageHandler,
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
    LifecycleStageName,
)
from market_regime_alpha.application.operational_research.sqlite_composite_repository import (
    SQLiteCompositeOperationalRepository,
)
from market_regime_alpha.application.trading_lifecycle.sqlite_risk_reduction import (
    SQLiteRiskReductionManualIntentRepository,
)
from market_regime_alpha.decision.sqlite_repository import (
    SQLiteDecisionLifecycleRepository,
)
from market_regime_alpha.portfolio.sqlite_account_authority import (
    SQLiteCompleteAccountPortfolioRiskRepository,
)
from market_regime_alpha.portfolio.sqlite_risk_routes import (
    SQLiteRiskRouteRepository,
)
from market_regime_alpha.position.sqlite_thesis_health import (
    SQLiteThesisHealthRepository,
)


Clock = Callable[[], datetime]


def build_sqlite_lifecycle_runner(
    *,
    repository: LifecycleRunRepository,
    command: CanonicalLifecycleCommand,
    manifest: CanonicalLifecycleInputManifest | None,
    configurations: RuntimeConfigurationSet,
    clock: Clock,
) -> CanonicalDecisionLifecycleRunner:
    """Build the exact 16-stage graph from explicit persisted authorities."""

    handlers = build_lifecycle_stage_handlers(
        command=command,
        manifest=manifest,
        configurations=configurations,
        authority_binder=_bind_authority_handlers,
    )
    return CanonicalDecisionLifecycleRunner(
        repository=repository,
        handlers=handlers,
        clock=clock,
    )


def _bind_authority_handlers(
    handlers: dict[LifecycleStageName, LifecycleStageHandler],
    authority_path: Path,
) -> None:
    decision_repository = SQLiteDecisionLifecycleRepository(authority_path)
    portfolio_repository = SQLiteCompleteAccountPortfolioRiskRepository(authority_path)
    risk_repository = SQLiteRiskRouteRepository(authority_path)
    execution_repository = SQLiteRiskReductionManualIntentRepository(authority_path)
    thesis_health_repository = SQLiteThesisHealthRepository(authority_path)
    composite_repository = SQLiteCompositeOperationalRepository(authority_path)
    handlers[LifecycleStageName.OPPORTUNITY] = OpportunityStageHandler(repository=decision_repository)
    handlers[LifecycleStageName.THESIS] = ThesisStageHandler(repository=decision_repository)
    handlers[LifecycleStageName.PORTFOLIO_RISK] = PortfolioRiskStageHandler(repository=portfolio_repository)
    handlers[LifecycleStageName.RISK_REDUCTION] = RiskReductionStageHandler(
        risk_repository=risk_repository,
        execution_repository=execution_repository,
        decision_repository=decision_repository,
        thesis_health_repository=thesis_health_repository,
        composite_repository=composite_repository,
    )
    handlers[LifecycleStageName.MANUAL_CONFIRMATION] = ManualConfirmationStageHandler(repository=execution_repository)
    handlers[LifecycleStageName.MANUAL_TRADE] = ManualTradeStageHandler(repository=execution_repository)
    handlers[LifecycleStageName.FILL_POSITION] = FillPositionStageHandler(repository=execution_repository)
    handlers[LifecycleStageName.THESIS_HEALTH] = ThesisHealthStageHandler(repository=thesis_health_repository)
    handlers[LifecycleStageName.HOLDING_ASSESSMENT] = HoldingAssessmentStageHandler()
    handlers[LifecycleStageName.EXIT_ASSESSMENT] = ExitAssessmentStageHandler()
    handlers[LifecycleStageName.OUTCOME_REVIEW] = OutcomeReviewStageHandler()
