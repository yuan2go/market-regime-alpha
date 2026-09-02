"""Stable Research Definition ports."""

from market_regime_alpha.research_qualification.ports.artifacts import (
    ResearchArtifactByteStore,
    ResearchArtifactRepository,
)
from market_regime_alpha.research_qualification.ports.exploratory_feature_inputs import (
    ExploratoryFeatureInputReadPort,
    ExploratoryIntradayFeatureGap,
    ExploratoryIntradayFeatureInput,
    ExploratoryIntradayFeatureObservation,
)
from market_regime_alpha.research_qualification.ports.exploratory_campaign import (
    CompletedExploratoryCampaign,
    ExploratoryCampaignReadPort,
)
from market_regime_alpha.research_qualification.ports.sources import (
    DatasetMarketSourceObservation,
    DatasetPopulationMember,
    ResearchSourceQueries,
)
from market_regime_alpha.research_qualification.ports.target_artifacts import TargetArtifactRepository
from market_regime_alpha.research_qualification.ports.target_repository import (
    TargetDefinitionRecord,
    TargetDefinitionRepository,
    TargetRegistrationReconciliation,
)
from market_regime_alpha.research_qualification.ports.target_uow import TargetUnitOfWork, TargetUnitOfWorkProvider
from market_regime_alpha.research_qualification.ports.qualification_read import (
    AdmittedResearchQualification,
    ResearchQualificationAdmissionReadPort,
)
from market_regime_alpha.research_qualification.ports.formal_campaign_uow import (
    FormalCampaignBindingRecord,
    FormalCampaignRecord,
    FormalCampaignRepository,
    FormalCampaignUnitOfWork,
    FormalCampaignUnitOfWorkProvider,
)
from market_regime_alpha.research_qualification.ports.formal_pit import (
    FormalPitSource,
    FormalPitSourceKind,
    FormalPitSourceReadPort,
)
from market_regime_alpha.research_qualification.ports.formal_campaign_queries import (
    DueOutcomeMember,
    DueOutcomeState,
    FormalCampaignInspection,
    FormalCampaignQueryPort,
    FormalCampaignVerification,
)
from market_regime_alpha.research_qualification.ports.model_inputs import (
    ModelArtifactPublisher,
    ModelTrainingInputProvider,
    OpenModelTrainingRunRequest,
    PreparedModelTrainingInputs,
    RegisteredModelTrainingInputs,
)
from market_regime_alpha.research_qualification.ports.repository import (
    DatasetRecord,
    ResearchDefinitionRepository,
)
from market_regime_alpha.research_qualification.ports.uow import (
    ResearchUnitOfWork,
    ResearchUnitOfWorkProvider,
)

__all__ = [
    "AdmittedResearchQualification",
    "DatasetMarketSourceObservation",
    "DatasetPopulationMember",
    "DatasetRecord",
    "DueOutcomeMember",
    "DueOutcomeState",
    "CompletedExploratoryCampaign",
    "ExploratoryCampaignReadPort",
    "ExploratoryFeatureInputReadPort",
    "ExploratoryIntradayFeatureGap",
    "ExploratoryIntradayFeatureInput",
    "ExploratoryIntradayFeatureObservation",
    "FormalCampaignBindingRecord",
    "FormalCampaignInspection",
    "FormalCampaignQueryPort",
    "FormalCampaignRecord",
    "FormalCampaignRepository",
    "FormalCampaignUnitOfWork",
    "FormalCampaignUnitOfWorkProvider",
    "FormalCampaignVerification",
    "FormalPitSource",
    "FormalPitSourceKind",
    "FormalPitSourceReadPort",
    "ModelArtifactPublisher",
    "ModelTrainingInputProvider",
    "OpenModelTrainingRunRequest",
    "PreparedModelTrainingInputs",
    "RegisteredModelTrainingInputs",
    "ResearchArtifactByteStore",
    "ResearchArtifactRepository",
    "ResearchDefinitionRepository",
    "ResearchQualificationAdmissionReadPort",
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
