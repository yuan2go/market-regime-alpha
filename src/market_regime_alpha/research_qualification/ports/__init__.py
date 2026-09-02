"""Stable Research Definition ports."""

from market_regime_alpha.research_qualification.ports.artifacts import ResearchArtifactByteStore, ResearchArtifactRepository
from market_regime_alpha.research_qualification.ports.repository import DatasetRecord, ResearchDefinitionRepository
from market_regime_alpha.research_qualification.ports.sources import (
    DatasetMarketSourceObservation,
    DatasetPopulationMember,
    ResearchSourceQueries,
)
from market_regime_alpha.research_qualification.ports.uow import ResearchUnitOfWork, ResearchUnitOfWorkProvider
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
from market_regime_alpha.research_qualification.ports.formal_pit import FormalPitSource, FormalPitSourceKind, FormalPitSourceReadPort
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
__all__ = [
    "AdmittedResearchQualification", "DatasetMarketSourceObservation", "DatasetPopulationMember",
    "DatasetRecord", "DueOutcomeMember", "DueOutcomeState", "FormalCampaignBindingRecord",
    "FormalCampaignInspection", "FormalCampaignQueryPort", "FormalCampaignRecord",
    "FormalCampaignRepository", "FormalCampaignUnitOfWork", "FormalCampaignUnitOfWorkProvider",
    "FormalCampaignVerification", "FormalPitSource", "FormalPitSourceKind", "FormalPitSourceReadPort",
    "ResearchArtifactByteStore", "ResearchArtifactRepository", "ResearchDefinitionRepository",
    "ResearchQualificationAdmissionReadPort", "ResearchSourceQueries", "ResearchUnitOfWork",
    "ModelArtifactPublisher", "ModelTrainingInputProvider", "OpenModelTrainingRunRequest",
    "PreparedModelTrainingInputs", "RegisteredModelTrainingInputs",
    "ResearchUnitOfWorkProvider", "TargetArtifactRepository", "TargetDefinitionRecord",
    "TargetDefinitionRepository", "TargetRegistrationReconciliation", "TargetUnitOfWork", "TargetUnitOfWorkProvider",
]
