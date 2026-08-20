"""Phase D CandidateRecommendation projection without Entry semantics."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import math
from typing import Any, Mapping

from market_regime_alpha.core.identity import (
    ArtifactId,
    ModelId,
    TargetId,
)
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.data.daily_quality import (
    DailyDataQualityStatus,
    DataQualityReport,
)
from market_regime_alpha.daily_decision._support import (
    canonical_hash,
    require_finite,
    require_strings,
    require_text,
)
from market_regime_alpha.daily_decision.snapshot import (
    DecisionPriceQuality,
    DecisionPriceSnapshot,
)
from market_regime_alpha.platform.prediction_run import PredictionRun
from market_regime_alpha.research.mr1_morning_pop import MR1TargetId


class CandidateDataQuality(str, Enum):
    COMPLETE = "COMPLETE"
    DEGRADED = "DEGRADED"
    INSUFFICIENT = "INSUFFICIENT"


@dataclass(frozen=True, slots=True)
class RecommendationScoreComponent:
    component_id: ArtifactId
    value: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", require_finite("component value", self.value))

    def to_canonical_dict(self) -> dict[str, Any]:
        return {"component_id": str(self.component_id), "value": self.value}


@dataclass(frozen=True, slots=True)
class CandidateRecommendation:
    SCHEMA_VERSION = "phase-d-candidate-recommendation-v2"

    decision_snapshot_id: ArtifactId
    prediction_run_id: ArtifactId
    model_id: ModelId
    symbol: str
    rank: int
    score: float
    score_components: tuple[RecommendationScoreComponent, ...]
    selection_reasons: tuple[str, ...]
    risk_reasons: tuple[str, ...]
    data_quality: CandidateDataQuality
    target_id: TargetId
    expected_horizon: str
    invalidation_conditions: tuple[str, ...]
    data_eligibility: DataEligibility
    selection_policy: str = "INCLUDE_ALL_BOUNDARY_TIES_V1"
    content_hash: str = field(init=False)
    recommendation_id: ArtifactId = field(init=False)

    def __post_init__(self) -> None:
        require_text("symbol", self.symbol)
        if isinstance(self.rank, bool) or self.rank < 1:
            raise ValueError("rank must be a positive integer")
        object.__setattr__(self, "score", require_finite("score", self.score))
        if not self.score_components:
            raise ValueError("score_components must not be empty")
        component_ids = tuple(item.component_id for item in self.score_components)
        if len(component_ids) != len(set(component_ids)):
            raise ValueError("score_components must be unique")
        if not math.isclose(
            math.fsum(item.value for item in self.score_components),
            self.score,
            rel_tol=1e-12,
            abs_tol=1e-12,
        ):
            raise ValueError("score_components must sum to score")
        require_strings(
            "selection_reasons",
            self.selection_reasons,
            required=True,
        )
        require_strings("risk_reasons", self.risk_reasons, required=True)
        require_strings(
            "invalidation_conditions",
            self.invalidation_conditions,
            required=True,
        )
        require_text("expected_horizon", self.expected_horizon)
        if not isinstance(self.data_quality, CandidateDataQuality):
            raise TypeError("data_quality must be a CandidateDataQuality")
        if self.target_id != TargetId(
            MR1TargetId.NEXT_SESSION_1030_RETURN.value
        ):
            raise ValueError("daily Recommendation requires the frozen MR1 10:30 Target")
        if self.data_eligibility is not DataEligibility.EXPLORATORY:
            raise ValueError("daily Recommendation is EXPLORATORY-only")
        if self.selection_policy != "INCLUDE_ALL_BOUNDARY_TIES_V1":
            raise ValueError("daily Recommendation requires the frozen boundary policy")
        content_hash = canonical_hash(self.semantic_payload())
        object.__setattr__(self, "content_hash", content_hash)
        object.__setattr__(
            self,
            "recommendation_id",
            ArtifactId(f"recommendation-{content_hash.split(':', 1)[1][:24]}"),
        )

    def semantic_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "decision_snapshot_id": str(self.decision_snapshot_id),
            "prediction_run_id": str(self.prediction_run_id),
            "model_id": str(self.model_id),
            "symbol": self.symbol,
            "rank": self.rank,
            "score": self.score,
            "score_components": [
                item.to_canonical_dict() for item in self.score_components
            ],
            "selection_reasons": list(self.selection_reasons),
            "risk_reasons": list(self.risk_reasons),
            "data_quality": self.data_quality.value,
            "target_id": str(self.target_id),
            "expected_horizon": self.expected_horizon,
            "invalidation_conditions": list(self.invalidation_conditions),
            "data_eligibility": self.data_eligibility.value,
            "selection_policy": self.selection_policy,
        }

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            **self.semantic_payload(),
            "content_hash": self.content_hash,
            "recommendation_id": str(self.recommendation_id),
        }

    @classmethod
    def from_canonical_dict(
        cls,
        payload: Mapping[str, Any],
    ) -> CandidateRecommendation:
        expected = {
            "schema_version",
            "decision_snapshot_id",
            "prediction_run_id",
            "model_id",
            "symbol",
            "rank",
            "score",
            "score_components",
            "selection_reasons",
            "risk_reasons",
            "data_quality",
            "target_id",
            "expected_horizon",
            "invalidation_conditions",
            "data_eligibility",
            "selection_policy",
            "content_hash",
            "recommendation_id",
        }
        if set(payload) != expected or payload["schema_version"] != cls.SCHEMA_VERSION:
            raise ValueError("CandidateRecommendation schema mismatch")
        recommendation = cls(
            decision_snapshot_id=ArtifactId(str(payload["decision_snapshot_id"])),
            prediction_run_id=ArtifactId(str(payload["prediction_run_id"])),
            model_id=ModelId(str(payload["model_id"])),
            symbol=str(payload["symbol"]),
            rank=int(payload["rank"]),
            score=float(payload["score"]),
            score_components=tuple(
                _score_component_from_canonical(item)
                for item in payload["score_components"]
            ),
            selection_reasons=tuple(
                str(item) for item in payload["selection_reasons"]
            ),
            risk_reasons=tuple(str(item) for item in payload["risk_reasons"]),
            data_quality=CandidateDataQuality(str(payload["data_quality"])),
            target_id=TargetId(str(payload["target_id"])),
            expected_horizon=str(payload["expected_horizon"]),
            invalidation_conditions=tuple(
                str(item) for item in payload["invalidation_conditions"]
            ),
            data_eligibility=DataEligibility(str(payload["data_eligibility"])),
            selection_policy=str(payload["selection_policy"]),
        )
        if (
            recommendation.content_hash != payload["content_hash"]
            or str(recommendation.recommendation_id)
            != payload["recommendation_id"]
        ):
            raise ValueError("CandidateRecommendation identity mismatch")
        return recommendation


def project_candidate_recommendations(
    *,
    prediction_runs: tuple[PredictionRun, ...],
    decision_snapshot: DecisionPriceSnapshot,
    data_quality_report: DataQualityReport,
    top_k: int = 5,
) -> tuple[CandidateRecommendation, ...]:
    """Project an independent frozen Top-K for every supplied model run."""

    if isinstance(top_k, bool) or top_k < 1:
        raise ValueError("top_k must be positive")
    if (
        data_quality_report.source_manifest_id
        != decision_snapshot.source_manifest_id
    ):
        raise ValueError("quality report and Decision Price Snapshot mismatch")
    if data_quality_report.status is DailyDataQualityStatus.DATA_BLOCKED:
        return ()
    run_ids = tuple(item.prediction_run_id for item in prediction_runs)
    model_ids = tuple(item.model_id for item in prediction_runs)
    if len(run_ids) != len(set(run_ids)) or len(model_ids) != len(set(model_ids)):
        raise ValueError("PredictionRuns must be unique by run and model")
    output: list[CandidateRecommendation] = []
    for run in prediction_runs:
        if (
            run.decision_time != decision_snapshot.decision_time
            or run.data_eligibility is not DataEligibility.EXPLORATORY
        ):
            raise ValueError("PredictionRun is outside daily Recommendation scope")
        selected_predictions = tuple(
            prediction
            for prediction in run.predictions
            if prediction.rank is not None and prediction.rank <= top_k
        )
        for prediction in selected_predictions:
            if prediction.model_score is None or prediction.rank is None:
                raise ValueError("ranked Candidate must carry score and rank")
            observation = decision_snapshot.observation_for(prediction.symbol)
            if (
                observation is None
                or observation.quality is DecisionPriceQuality.INSUFFICIENT
                or data_quality_report.status
                is DailyDataQualityStatus.INSUFFICIENT
            ):
                candidate_quality = CandidateDataQuality.INSUFFICIENT
            elif data_quality_report.status is DailyDataQualityStatus.DEGRADED:
                candidate_quality = CandidateDataQuality.DEGRADED
            else:
                candidate_quality = CandidateDataQuality.COMPLETE
            output.append(
                CandidateRecommendation(
                    decision_snapshot_id=decision_snapshot.decision_snapshot_id,
                    prediction_run_id=run.prediction_run_id,
                    model_id=run.model_id,
                    symbol=prediction.symbol,
                    rank=prediction.rank,
                    score=prediction.model_score,
                    score_components=(
                        RecommendationScoreComponent(
                            component_id=ArtifactId(
                                f"score-component-{run.model_id}-aggregate-v1"
                            ),
                            value=prediction.model_score,
                        ),
                    ),
                    selection_reasons=(
                        "FROZEN_MODEL_RANK_WITHIN_TOP_K_OR_BOUNDARY_TIE",
                        "SCORE_IS_NOT_A_PROBABILITY",
                    ),
                    risk_reasons=(
                        "EXPLORATORY_DATA_ONLY",
                        "FORMAL_OOS_ALPHA_NOT_ESTABLISHED",
                    ),
                    data_quality=candidate_quality,
                    target_id=run.target_id,
                    expected_horizon="next trading session 10:30",
                    invalidation_conditions=(
                        "DECISION_PRICE_SNAPSHOT_INVALIDATED",
                        "PREDICTION_RUN_VERIFICATION_FAILED",
                        "SOURCE_MANIFEST_INVALIDATED",
                    ),
                    data_eligibility=DataEligibility.EXPLORATORY,
                )
            )
    return tuple(output)


def _score_component_from_canonical(
    payload: Mapping[str, Any],
) -> RecommendationScoreComponent:
    if set(payload) != {"component_id", "value"}:
        raise ValueError("Recommendation Score Component fields mismatch")
    return RecommendationScoreComponent(
        component_id=ArtifactId(str(payload["component_id"])),
        value=float(payload["value"]),
    )
