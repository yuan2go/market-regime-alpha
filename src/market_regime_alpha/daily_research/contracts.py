"""Public domain contract facade for one immutable daily research decision."""

from market_regime_alpha.daily_research._contract_support import (
    DailyDataAuthority,
    DecisionDataQuality,
    EntryState,
    InstrumentType,
    canonical_content_hash,
)
from market_regime_alpha.daily_research.entry import (
    ENTRY_ASSESSMENT_SCHEMA_VERSION,
    EntryAssessment,
    PriceZone,
)
from market_regime_alpha.daily_research.recommendation import (
    CANDIDATE_RECOMMENDATION_SCHEMA_VERSION,
    CandidateRecommendation,
    ScoreComponent,
)
from market_regime_alpha.daily_research.snapshot import (
    DAILY_RESEARCH_SNAPSHOT_SCHEMA_VERSION,
    DailyResearchSnapshot,
    DecisionSourceArtifact,
)

__all__ = [
    "CANDIDATE_RECOMMENDATION_SCHEMA_VERSION",
    "DAILY_RESEARCH_SNAPSHOT_SCHEMA_VERSION",
    "ENTRY_ASSESSMENT_SCHEMA_VERSION",
    "CandidateRecommendation",
    "DailyDataAuthority",
    "DailyResearchSnapshot",
    "DecisionDataQuality",
    "DecisionSourceArtifact",
    "EntryAssessment",
    "EntryState",
    "InstrumentType",
    "PriceZone",
    "ScoreComponent",
    "canonical_content_hash",
]
