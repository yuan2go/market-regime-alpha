"""Historical daily-research compatibility contracts and Readers.

`EntryState.ENTER` is retained only to restore immutable historical Artifacts.
This namespace is not a current executable or writable authority. New business
writes use the Canonical Runtime, Decision System and `daily_decision` Entry
plumbing declared by :mod:`market_regime_alpha.application.authority_boundary`.
"""

LEGACY_COMPATIBILITY_ONLY = True

from .artifacts import (
    DAILY_QUANT_DECISION_FILES,
    publish_daily_quant_decision_artifact,
)
from .contracts import (
    CandidateRecommendation,
    DailyDataAuthority,
    DailyResearchSnapshot,
    DecisionDataQuality,
    DecisionSourceArtifact,
    EntryAssessment,
    EntryState,
    InstrumentType,
    PriceZone,
    ScoreComponent,
)
from .reader import (
    VerifiedDailyQuantDecisionArtifact,
    load_verified_daily_quant_decision_artifact,
)

__all__ = [
    "CandidateRecommendation",
    "DAILY_QUANT_DECISION_FILES",
    "DailyDataAuthority",
    "DailyResearchSnapshot",
    "DecisionDataQuality",
    "DecisionSourceArtifact",
    "EntryAssessment",
    "EntryState",
    "InstrumentType",
    "PriceZone",
    "ScoreComponent",
    "VerifiedDailyQuantDecisionArtifact",
    "load_verified_daily_quant_decision_artifact",
    "publish_daily_quant_decision_artifact",
    "LEGACY_COMPATIBILITY_ONLY",
]
