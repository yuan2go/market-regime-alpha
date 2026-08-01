"""Explicit ownership boundaries for Platform Architecture V2."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class PlatformLayer(str, Enum):
    DATA_EVIDENCE_FOUNDATION = "LAYER_0_DATA_EVIDENCE_FOUNDATION"
    RESEARCH_OPPORTUNITY_DISCOVERY = "LAYER_1_RESEARCH_OPPORTUNITY_DISCOVERY"
    SIGNAL_TIMING = "LAYER_2_SIGNAL_TIMING"
    TRADE_DECISION_RISK = "LAYER_3_TRADE_DECISION_RISK"
    POSITION_LIFECYCLE_EXECUTION = "LAYER_4_POSITION_LIFECYCLE_EXECUTION"
    OUTCOME_EVALUATION_LEARNING = "LAYER_5_OUTCOME_EVALUATION_LEARNING"


@dataclass(frozen=True, slots=True)
class PlatformBoundary:
    layer: PlatformLayer
    owned_outputs: tuple[str, ...]
    forbidden_outputs: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.owned_outputs:
            raise ValueError("Platform boundary must own at least one output")
        if set(self.owned_outputs) & set(self.forbidden_outputs):
            raise ValueError("Platform boundary ownership cannot contradict itself")


PLATFORM_V2_BOUNDARIES = (
    PlatformBoundary(
        PlatformLayer.DATA_EVIDENCE_FOUNDATION,
        ("SourceManifest", "DataQualityReport", "ArtifactEnvelope"),
        ("CandidateSet", "TradeDecision", "ExecutionRecord"),
    ),
    PlatformBoundary(
        PlatformLayer.RESEARCH_OPPORTUNITY_DISCOVERY,
        (
            "MarketRegimeSnapshot",
            "ThemeRotationSnapshot",
            "CapitalEvolutionSnapshot",
            "CandidateSet",
        ),
        ("BUY", "SELL", "ENTER", "PositionPlan"),
    ),
    PlatformBoundary(
        PlatformLayer.SIGNAL_TIMING,
        ("SignalSnapshot", "NextSessionForecast", "PathForecast"),
        ("PositionPlan", "ExecutionRecord"),
    ),
    PlatformBoundary(
        PlatformLayer.TRADE_DECISION_RISK,
        (
            "TradeDecision",
            "PositionPlan",
            "TradingOpportunity",
            "TradingThesis",
            "PortfolioDecision",
            "RiskDecision",
        ),
        ("LIVE_ORDER", "BROKER_FILL"),
    ),
    PlatformBoundary(
        PlatformLayer.POSITION_LIFECYCLE_EXECUTION,
        (
            "ExecutionRecord",
            "ExitDecision",
            "ManualTradeRecord",
            "Fill",
            "PositionSnapshot",
            "HoldingAssessment",
            "ExitAssessment",
        ),
        ("MODEL_PROMOTION",),
    ),
    PlatformBoundary(
        PlatformLayer.OUTCOME_EVALUATION_LEARNING,
        (
            "EvaluationReport",
            "DailyReviewReport",
            "TradeOutcome",
            "AttributionRecord",
            "RollingScorecard",
        ),
        ("AUTO_MODEL_PROMOTION", "LIVE_ORDER"),
    ),
)
