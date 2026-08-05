"""Backend-neutral construction for the canonical lifecycle stage graph."""

from __future__ import annotations

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
from market_regime_alpha.application.canonical_lifecycle.runtime_configuration import (
    RuntimeConfigurationSet,
)
from market_regime_alpha.application.canonical_lifecycle.stages.contracts import (
    LifecycleStageHandler,
)
from market_regime_alpha.application.canonical_lifecycle.stages.evidence import (
    VerifiedCompositeEvidenceStageHandler,
)
from market_regime_alpha.application.canonical_lifecycle.stages.research import (
    PlatformResearchStageHandler,
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
from market_regime_alpha.forecasting.path import PathForecastConfig
from market_regime_alpha.features.spine import FeatureSetConfiguration
from market_regime_alpha.research.platform_v2.configs import ResearchPipelineConfig
from market_regime_alpha.signals.decimal_model import SignalModelConfigurationV2
from market_regime_alpha.signals.input_v3 import SignalInputMappingConfigurationV2
from market_regime_alpha.signals.policies import (
    SignalFactorFreshnessPolicy,
    SignalFactorRequirementPolicy,
)


AuthorityBinder = Callable[[dict[LifecycleStageName, LifecycleStageHandler], Path], None]


def build_lifecycle_stage_handlers(
    *,
    command: CanonicalLifecycleCommand,
    manifest: CanonicalLifecycleInputManifest | None,
    configurations: RuntimeConfigurationSet,
    authority_binder: AuthorityBinder | None,
) -> tuple[LifecycleStageHandler, ...]:
    """Build stages shared by PostgreSQL and explicit compatibility roots."""

    output_root = command.output_directory
    research_configuration = configurations.get(LifecycleConfigurationKind.RESEARCH_PIPELINE)
    signal_configuration = configurations.get(LifecycleConfigurationKind.SIGNAL_MODEL)
    signal_input_mapping = configurations.get(LifecycleConfigurationKind.SIGNAL_INPUT_MAPPING)
    feature_set_configuration = configurations.get(LifecycleConfigurationKind.FEATURE_SET)
    signal_requirement_policy = configurations.get(LifecycleConfigurationKind.SIGNAL_FACTOR_REQUIREMENT)
    signal_freshness_policy = configurations.get(LifecycleConfigurationKind.SIGNAL_FACTOR_FRESHNESS)
    forecast_configuration = configurations.get(LifecycleConfigurationKind.PATH_FORECAST)

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
    handlers[LifecycleStageName.VERIFY_COMPOSITE_EVIDENCE] = VerifiedCompositeEvidenceStageHandler()
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
        handlers[LifecycleStageName.ENTRY_ASSESSMENT] = EntryAssessmentStageHandler(authority_ceiling=manifest.authority_ceiling)
    if command.authority_database_locator is not None and authority_binder is not None:
        authority_binder(handlers, command.authority_database_locator)
    return tuple(handlers[stage] for stage in LIFECYCLE_STAGE_ORDER)


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


__all__ = ["AuthorityBinder", "build_lifecycle_stage_handlers"]
