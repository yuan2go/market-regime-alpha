"""Persistence and Runtime services for WP-STATE-01."""

from market_regime_alpha.application.state_system.bundles import (
    scoped_state_stage_bundle_identity,
    state_research_pipeline_identity,
)
from market_regime_alpha.application.state_system.postgres_repository import (
    PostgresStateSystemRepository,
)
from market_regime_alpha.application.state_system.repository import (
    StateArtifactWrite,
    StateDomain,
    StateSystemConflict,
    StateSystemIntegrityError,
)
from market_regime_alpha.application.state_system.runtime import (
    OrderedStateResearchPipeline,
    StateResearchPipelineResult,
    StateResearchStage,
    StateResearchStageArtifact,
    StateSystemRuntimeDelegate,
)

__all__ = [
    "PostgresStateSystemRepository",
    "StateSystemConflict",
    "StateSystemIntegrityError",
    "OrderedStateResearchPipeline",
    "StateResearchPipelineResult",
    "StateResearchStage",
    "StateResearchStageArtifact",
    "StateSystemRuntimeDelegate",
    "StateArtifactWrite",
    "StateDomain",
    "scoped_state_stage_bundle_identity",
    "state_research_pipeline_identity",
]
