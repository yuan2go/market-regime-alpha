"""Stable Research Definition ports."""

from market_regime_alpha.research_qualification.ports.artifacts import (
    ResearchArtifactByteStore,
    ResearchArtifactRepository,
)
from market_regime_alpha.research_qualification.ports.repository import (
    DatasetRecord,
    ResearchDefinitionRepository,
)
from market_regime_alpha.research_qualification.ports.sources import (
    DatasetMarketSourceObservation,
    DatasetPopulationMember,
    ResearchSourceQueries,
)
from market_regime_alpha.research_qualification.ports.uow import (
    ResearchUnitOfWork,
    ResearchUnitOfWorkProvider,
)
from market_regime_alpha.research_qualification.ports.target_artifacts import (
    TargetArtifactRepository,
)
from market_regime_alpha.research_qualification.ports.target_repository import (
    TargetDefinitionRecord,
    TargetDefinitionRepository,
    TargetRegistrationReconciliation,
)
from market_regime_alpha.research_qualification.ports.target_uow import (
    TargetUnitOfWork,
    TargetUnitOfWorkProvider,
)
__all__ = [
    "ResearchArtifactByteStore",
    "ResearchArtifactRepository",
    "DatasetMarketSourceObservation",
    "DatasetPopulationMember",
    "DatasetRecord",
    "ResearchDefinitionRepository",
    "ResearchSourceQueries",
    "ResearchUnitOfWork",
    "ResearchUnitOfWorkProvider",
    "TargetArtifactRepository",
    "TargetDefinitionRecord",
    "TargetDefinitionRepository",
    "TargetRegistrationReconciliation",
    "TargetUnitOfWork",
    "TargetUnitOfWorkProvider",
]
