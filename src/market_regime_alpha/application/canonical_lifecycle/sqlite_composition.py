"""SQLite composition root for the canonical lifecycle stage graph."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Callable

from market_regime_alpha.application.canonical_lifecycle.commands import (
    CanonicalLifecycleCommand,
)
from market_regime_alpha.application.canonical_lifecycle.contracts import (
    LifecycleConfigurationKind,
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
from market_regime_alpha.application.canonical_lifecycle.sqlite_repository import (
    SQLiteLifecycleRunRepository,
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
from market_regime_alpha.application.canonical_lifecycle.stages.evidence import (
    VerifiedCompositeEvidenceStageHandler,
)
from market_regime_alpha.application.canonical_lifecycle.stages.execution_position import (
    FillPositionStageHandler,
    ManualConfirmationStageHandler,
    ManualTradeStageHandler,
)
from market_regime_alpha.application.canonical_lifecycle.stages.research import (
    PlatformResearchStageHandler,
)
from market_regime_alpha.application.canonical_lifecycle.stages.risk_reduction import (
    RiskReductionStageHandler,
)
from market_regime_alpha.application.canonical_lifecycle.stages.signal_forecast import (
    EntryAssessmentStageHandler,
    PathForecastStageHandler,
    SignalStageHandler,
)
from market_regime_alpha.application.canonical_lifecycle.stages.unavailable import (
    UnavailableLifecycleStageHandler,
)
from market_regime_alpha.application.canonical_lifecycle.states import (
    LIFECYCLE_STAGE_ORDER,
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
from market_regime_alpha.forecasting.path import PathForecastConfig
from market_regime_alpha.features.spine import FeatureSetConfiguration
from market_regime_alpha.portfolio.sqlite_account_authority import (
    SQLiteCompleteAccountPortfolioRiskRepository,
)
from market_regime_alpha.portfolio.sqlite_risk_routes import (
    SQLiteRiskRouteRepository,
)
from market_regime_alpha.position.sqlite_thesis_health import (
    SQLiteThesisHealthRepository,
)
from market_regime_alpha.research.platform_v2.configs import ResearchPipelineConfig
from market_regime_alpha.signals.decimal_model import SignalModelConfigurationV2
from market_regime_alpha.signals.input_v3 import (
    SignalInputMappingConfigurationV2,
)
from market_regime_alpha.signals.policies import (
    SignalFactorFreshnessPolicy,
    SignalFactorRequirementPolicy,
)


Clock = Callable[[], datetime]


def build_sqlite_lifecycle_runner(
    *,
    repository: SQLiteLifecycleRunRepository,
    command: CanonicalLifecycleCommand,
    manifest: CanonicalLifecycleInputManifest | None,
    configurations: RuntimeConfigurationSet,
    clock: Clock,
) -> CanonicalDecisionLifecycleRunner:
    """Build the exact 16-stage graph from explicit persisted authorities."""

    handlers = _build_handlers(
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


def _build_handlers(
    *,
    command: CanonicalLifecycleCommand,
    manifest: CanonicalLifecycleInputManifest | None,
    configurations: RuntimeConfigurationSet,
    authority_binder: Callable[..., None] | None,
) -> tuple[LifecycleStageHandler, ...]:
    output_root = command.output_directory
    research_configuration = configurations.get(
        LifecycleConfigurationKind.RESEARCH_PIPELINE
    )
    signal_configuration = configurations.get(
        LifecycleConfigurationKind.SIGNAL_MODEL
    )
    signal_input_mapping = configurations.get(
        LifecycleConfigurationKind.SIGNAL_INPUT_MAPPING
    )
    feature_set_configuration = configurations.get(
        LifecycleConfigurationKind.FEATURE_SET
    )
    signal_requirement_policy = configurations.get(
        LifecycleConfigurationKind.SIGNAL_FACTOR_REQUIREMENT
    )
    signal_freshness_policy = configurations.get(
        LifecycleConfigurationKind.SIGNAL_FACTOR_FRESHNESS
    )
    forecast_configuration = configurations.get(
        LifecycleConfigurationKind.PATH_FORECAST
    )

    handlers: dict[LifecycleStageName, LifecycleStageHandler] = {
        stage: _unavailable(
            stage,
            "COMMAND_BOUND_DOMAIN_REPOSITORY_UNAVAILABLE",
            (
                "the standalone CLI was not given an explicit authority mapping; "
                "no Repository, ManualTrade, Fill or Broker operation was inferred"
            ),
        )
        for stage in LIFECYCLE_STAGE_ORDER
    }
    handlers[LifecycleStageName.VERIFY_COMPOSITE_EVIDENCE] = (
        VerifiedCompositeEvidenceStageHandler()
    )
    if isinstance(research_configuration, ResearchPipelineConfig):
        handlers[LifecycleStageName.PLATFORM_RESEARCH] = PlatformResearchStageHandler(
            configuration=research_configuration,
            output_root=output_root / "platform-research",
        )
    else:
        handlers[LifecycleStageName.PLATFORM_RESEARCH] = _unavailable(
            LifecycleStageName.PLATFORM_RESEARCH,
            "RESEARCH_PIPELINE_CONFIGURATION_UNAVAILABLE",
            "no command-bound RESEARCH_PIPELINE configuration was supplied",
        )
    if (
        isinstance(signal_configuration, SignalModelConfigurationV2)
        and isinstance(signal_input_mapping, SignalInputMappingConfigurationV2)
        and isinstance(feature_set_configuration, FeatureSetConfiguration)
        and isinstance(signal_requirement_policy, SignalFactorRequirementPolicy)
        and isinstance(signal_freshness_policy, SignalFactorFreshnessPolicy)
    ):
        handlers[LifecycleStageName.SIGNAL] = SignalStageHandler(
            configuration=signal_configuration,
            output_root=output_root / "signals",
            mapping_configuration=signal_input_mapping,
            feature_set_configuration=feature_set_configuration,
            requirement_policy=signal_requirement_policy,
            freshness_policy=signal_freshness_policy,
        )
    else:
        handlers[LifecycleStageName.SIGNAL] = _unavailable(
            LifecycleStageName.SIGNAL,
            "SIGNAL_MODEL_CONFIGURATION_UNAVAILABLE",
            (
                "canonical Signal requires command-bound FEATURE_SET, "
                "SIGNAL_INPUT_MAPPING, SIGNAL_FACTOR_REQUIREMENT, "
                "SIGNAL_FACTOR_FRESHNESS and Decimal SIGNAL_MODEL configurations"
            ),
        )
    if isinstance(forecast_configuration, PathForecastConfig):
        handlers[LifecycleStageName.PATH_FORECAST] = PathForecastStageHandler(
            configuration=forecast_configuration,
            output_root=output_root / "path-forecasts",
        )
    else:
        handlers[LifecycleStageName.PATH_FORECAST] = _unavailable(
            LifecycleStageName.PATH_FORECAST,
            "PATH_FORECAST_CONFIGURATION_UNAVAILABLE",
            "no command-bound PATH_FORECAST configuration was supplied",
        )
    if manifest is not None:
        handlers[LifecycleStageName.ENTRY_ASSESSMENT] = EntryAssessmentStageHandler(
            authority_ceiling=manifest.authority_ceiling
        )
    if command.authority_database_locator is not None and authority_binder is not None:
        authority_binder(
            handlers=handlers,
            authority_path=command.authority_database_locator,
        )
    return tuple(handlers[stage] for stage in LIFECYCLE_STAGE_ORDER)


def _bind_authority_handlers(
    *,
    handlers: dict[LifecycleStageName, LifecycleStageHandler],
    authority_path: Path,
) -> None:
    decision_repository = SQLiteDecisionLifecycleRepository(authority_path)
    portfolio_repository = SQLiteCompleteAccountPortfolioRiskRepository(
        authority_path
    )
    risk_repository = SQLiteRiskRouteRepository(authority_path)
    execution_repository = SQLiteRiskReductionManualIntentRepository(authority_path)
    thesis_health_repository = SQLiteThesisHealthRepository(authority_path)
    composite_repository = SQLiteCompositeOperationalRepository(authority_path)
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
    handlers[LifecycleStageName.HOLDING_ASSESSMENT] = HoldingAssessmentStageHandler()
    handlers[LifecycleStageName.EXIT_ASSESSMENT] = ExitAssessmentStageHandler()
    handlers[LifecycleStageName.OUTCOME_REVIEW] = OutcomeReviewStageHandler()


def _unavailable(
    stage: LifecycleStageName,
    reason_code: str,
    detail: str,
) -> UnavailableLifecycleStageHandler:
    return UnavailableLifecycleStageHandler(
        stage_name=stage,
        reason_code=reason_code,
        detail=detail,
    )
