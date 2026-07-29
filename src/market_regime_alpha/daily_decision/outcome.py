"""MR1 10:30 Outcome Settlement and DailyReview contracts."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, time
from enum import Enum
import math
from statistics import mean
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from market_regime_alpha.core.identity import (
    ArtifactId,
    ModelId,
    TargetId,
    UniverseId,
)
from market_regime_alpha.core.time import AvailabilityTime
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.data.providers.public_composite import (
    PublicBar,
    PublicCompositeProviderResult,
)
from market_regime_alpha.daily_decision._support import (
    canonical_hash,
    require_finite,
    require_text,
)
from market_regime_alpha.daily_decision.artifact import (
    DailyDecisionArtifactStatus,
    PhaseDDailyDecisionBundle,
)
from market_regime_alpha.daily_decision.target_adapter import (
    mr1_next_session_1030_target_protocol,
)
from market_regime_alpha.platform.candidate_prediction_adapter import (
    B0_MOMENTUM_MODEL_ID,
    B1_BALANCED_MODEL_ID,
)
from market_regime_alpha.platform.target_evaluation import TargetProtocol
from market_regime_alpha.research.mr1_morning_pop import (
    MR1TargetId,
    build_mr1_next_session_1030_return_observation,
)
from market_regime_alpha.research.tencent_composite_contracts import (
    CompositeBar,
    CompositeSourceKind,
)


_SHANGHAI = ZoneInfo("Asia/Shanghai")
_TARGET_ID = TargetId(MR1TargetId.NEXT_SESSION_1030_RETURN.value)


class OutcomeStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    UNRESOLVED = "UNRESOLVED"


@dataclass(frozen=True, slots=True)
class PopulationTargetObservation:
    SCHEMA_VERSION = "phase-d-population-target-observation-v1"

    daily_decision_artifact_id: ArtifactId
    symbol: str
    target_id: TargetId
    status: OutcomeStatus
    target_value: float | None
    observed_at: AvailabilityTime | None
    source_artifact_id: ArtifactId | None
    reason_code: str | None
    data_eligibility: DataEligibility
    content_hash: str = field(init=False)
    observation_id: ArtifactId = field(init=False)

    def __post_init__(self) -> None:
        require_text("symbol", self.symbol)
        if self.target_id != _TARGET_ID:
            raise ValueError("Population Outcome requires the unique MR1 10:30 Target")
        if not isinstance(self.status, OutcomeStatus):
            raise TypeError("status must be an OutcomeStatus")
        if self.status is OutcomeStatus.AVAILABLE:
            if (
                self.target_value is None
                or self.observed_at is None
                or self.source_artifact_id is None
                or self.reason_code is not None
            ):
                raise ValueError("AVAILABLE Outcome requires complete evidence")
            object.__setattr__(
                self,
                "target_value",
                require_finite("target_value", self.target_value),
            )
        else:
            if self.target_value is not None or self.observed_at is not None:
                raise ValueError("UNRESOLVED Outcome cannot carry a target value")
            if self.reason_code is None:
                raise ValueError("UNRESOLVED Outcome requires a reason")
            require_text("reason_code", self.reason_code)
        if self.data_eligibility is not DataEligibility.EXPLORATORY:
            raise ValueError("Outcome Settlement is EXPLORATORY-only")
        content_hash = canonical_hash(self.semantic_payload())
        object.__setattr__(self, "content_hash", content_hash)
        object.__setattr__(
            self,
            "observation_id",
            ArtifactId(f"target-observation-{content_hash.split(':', 1)[1][:24]}"),
        )

    def semantic_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "daily_decision_artifact_id": str(
                self.daily_decision_artifact_id
            ),
            "symbol": self.symbol,
            "target_id": str(self.target_id),
            "status": self.status.value,
            "target_value": self.target_value,
            "observed_at": (
                self.observed_at.isoformat()
                if self.observed_at is not None
                else None
            ),
            "source_artifact_id": (
                str(self.source_artifact_id)
                if self.source_artifact_id is not None
                else None
            ),
            "reason_code": self.reason_code,
            "data_eligibility": self.data_eligibility.value,
        }

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            **self.semantic_payload(),
            "content_hash": self.content_hash,
            "observation_id": str(self.observation_id),
        }

    @classmethod
    def from_canonical_dict(
        cls,
        payload: Mapping[str, Any],
    ) -> PopulationTargetObservation:
        expected = {
            "schema_version",
            "daily_decision_artifact_id",
            "symbol",
            "target_id",
            "status",
            "target_value",
            "observed_at",
            "source_artifact_id",
            "reason_code",
            "data_eligibility",
            "content_hash",
            "observation_id",
        }
        if set(payload) != expected or payload["schema_version"] != cls.SCHEMA_VERSION:
            raise ValueError("PopulationTargetObservation schema mismatch")
        observed = payload["observed_at"]
        source = payload["source_artifact_id"]
        value = payload["target_value"]
        observation = cls(
            daily_decision_artifact_id=ArtifactId(
                str(payload["daily_decision_artifact_id"])
            ),
            symbol=str(payload["symbol"]),
            target_id=TargetId(str(payload["target_id"])),
            status=OutcomeStatus(str(payload["status"])),
            target_value=float(value) if value is not None else None,
            observed_at=(
                AvailabilityTime(datetime.fromisoformat(str(observed)))
                if observed is not None
                else None
            ),
            source_artifact_id=(
                ArtifactId(str(source)) if source is not None else None
            ),
            reason_code=(
                str(payload["reason_code"])
                if payload["reason_code"] is not None
                else None
            ),
            data_eligibility=DataEligibility(str(payload["data_eligibility"])),
        )
        if (
            observation.content_hash != payload["content_hash"]
            or str(observation.observation_id) != payload["observation_id"]
        ):
            raise ValueError("PopulationTargetObservation identity mismatch")
        return observation


@dataclass(frozen=True, slots=True)
class RecommendationOutcome:
    SCHEMA_VERSION = "phase-d-recommendation-outcome-v1"

    daily_decision_artifact_id: ArtifactId
    recommendation_id: ArtifactId
    prediction_run_id: ArtifactId
    model_id: ModelId
    symbol: str
    target_id: TargetId
    population_observation_id: ArtifactId
    status: OutcomeStatus
    target_value: float | None
    data_eligibility: DataEligibility
    content_hash: str = field(init=False)
    outcome_id: ArtifactId = field(init=False)

    def __post_init__(self) -> None:
        require_text("symbol", self.symbol)
        if self.target_id != _TARGET_ID:
            raise ValueError("RecommendationOutcome requires MR1 10:30 Target")
        if self.status is OutcomeStatus.AVAILABLE:
            if self.target_value is None:
                raise ValueError("AVAILABLE RecommendationOutcome requires value")
            object.__setattr__(
                self,
                "target_value",
                require_finite("target_value", self.target_value),
            )
        elif self.target_value is not None:
            raise ValueError("UNRESOLVED RecommendationOutcome cannot carry value")
        if self.data_eligibility is not DataEligibility.EXPLORATORY:
            raise ValueError("RecommendationOutcome is EXPLORATORY-only")
        content_hash = canonical_hash(self.semantic_payload())
        object.__setattr__(self, "content_hash", content_hash)
        object.__setattr__(
            self,
            "outcome_id",
            ArtifactId(f"recommendation-outcome-{content_hash.split(':', 1)[1][:24]}"),
        )

    def semantic_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "daily_decision_artifact_id": str(
                self.daily_decision_artifact_id
            ),
            "recommendation_id": str(self.recommendation_id),
            "prediction_run_id": str(self.prediction_run_id),
            "model_id": str(self.model_id),
            "symbol": self.symbol,
            "target_id": str(self.target_id),
            "population_observation_id": str(
                self.population_observation_id
            ),
            "status": self.status.value,
            "target_value": self.target_value,
            "data_eligibility": self.data_eligibility.value,
        }

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            **self.semantic_payload(),
            "content_hash": self.content_hash,
            "outcome_id": str(self.outcome_id),
        }

    @classmethod
    def from_canonical_dict(
        cls,
        payload: Mapping[str, Any],
    ) -> RecommendationOutcome:
        expected = {
            "schema_version",
            "daily_decision_artifact_id",
            "recommendation_id",
            "prediction_run_id",
            "model_id",
            "symbol",
            "target_id",
            "population_observation_id",
            "status",
            "target_value",
            "data_eligibility",
            "content_hash",
            "outcome_id",
        }
        if set(payload) != expected or payload["schema_version"] != cls.SCHEMA_VERSION:
            raise ValueError("RecommendationOutcome schema mismatch")
        value = payload["target_value"]
        outcome = cls(
            daily_decision_artifact_id=ArtifactId(
                str(payload["daily_decision_artifact_id"])
            ),
            recommendation_id=ArtifactId(str(payload["recommendation_id"])),
            prediction_run_id=ArtifactId(str(payload["prediction_run_id"])),
            model_id=ModelId(str(payload["model_id"])),
            symbol=str(payload["symbol"]),
            target_id=TargetId(str(payload["target_id"])),
            population_observation_id=ArtifactId(
                str(payload["population_observation_id"])
            ),
            status=OutcomeStatus(str(payload["status"])),
            target_value=float(value) if value is not None else None,
            data_eligibility=DataEligibility(str(payload["data_eligibility"])),
        )
        if (
            outcome.content_hash != payload["content_hash"]
            or str(outcome.outcome_id) != payload["outcome_id"]
        ):
            raise ValueError("RecommendationOutcome identity mismatch")
        return outcome


@dataclass(frozen=True, slots=True)
class DailyReviewReport:
    SCHEMA_VERSION = "phase-d-daily-review-v1"

    daily_decision_artifact_id: ArtifactId
    target_id: TargetId
    recommendation_count: int
    outcome_coverage: float
    positive_return_count: int
    top_k_mean_target: float | None
    candidate_population_mean_target: float | None
    ranking_coverage: float
    data_quality_summary: tuple[tuple[str, int], ...]
    blocked_reason_counts: tuple[tuple[str, int], ...]
    b0_b1_top_k_overlap_count: int
    b0_b1_top_k_union_count: int
    b0_b1_top_k_jaccard: float
    unresolved_outcome_count: int
    data_eligibility: DataEligibility
    content_hash: str = field(init=False)
    review_id: ArtifactId = field(init=False)

    def __post_init__(self) -> None:
        if self.target_id != _TARGET_ID:
            raise ValueError("DailyReview requires MR1 10:30 Target")
        for count_label, count_value in (
            ("recommendation_count", self.recommendation_count),
            ("positive_return_count", self.positive_return_count),
            ("b0_b1_top_k_overlap_count", self.b0_b1_top_k_overlap_count),
            ("b0_b1_top_k_union_count", self.b0_b1_top_k_union_count),
            ("unresolved_outcome_count", self.unresolved_outcome_count),
        ):
            if isinstance(count_value, bool) or count_value < 0:
                raise ValueError(f"{count_label} must be non-negative")
        for ratio_label, ratio_value in (
            ("outcome_coverage", self.outcome_coverage),
            ("ranking_coverage", self.ranking_coverage),
            ("b0_b1_top_k_jaccard", self.b0_b1_top_k_jaccard),
        ):
            finite = require_finite(ratio_label, ratio_value)
            if not 0.0 <= finite <= 1.0:
                raise ValueError(f"{ratio_label} must be in [0, 1]")
        for optional_label, optional_value in (
            ("top_k_mean_target", self.top_k_mean_target),
            (
                "candidate_population_mean_target",
                self.candidate_population_mean_target,
            ),
        ):
            if optional_value is not None:
                require_finite(optional_label, optional_value)
        for values in (self.data_quality_summary, self.blocked_reason_counts):
            if tuple(sorted(values)) != values:
                raise ValueError("DailyReview counts must be ordered")
            for key, count in values:
                require_text("DailyReview count key", key)
                if isinstance(count, bool) or count < 0:
                    raise ValueError("DailyReview count must be non-negative")
        if self.unresolved_outcome_count > self.recommendation_count:
            raise ValueError("unresolved outcomes exceed recommendations")
        resolved_count = self.recommendation_count - self.unresolved_outcome_count
        expected_coverage = (
            resolved_count / self.recommendation_count
            if self.recommendation_count
            else 0.0
        )
        if not math.isclose(
            self.outcome_coverage,
            expected_coverage,
            rel_tol=0.0,
            abs_tol=1e-15,
        ):
            raise ValueError("outcome_coverage does not match unresolved count")
        if self.positive_return_count > resolved_count:
            raise ValueError("positive return count exceeds resolved outcomes")
        if (
            self.b0_b1_top_k_overlap_count
            > self.b0_b1_top_k_union_count
        ):
            raise ValueError("B0/B1 overlap exceeds union")
        expected_jaccard = (
            self.b0_b1_top_k_overlap_count
            / self.b0_b1_top_k_union_count
            if self.b0_b1_top_k_union_count
            else 0.0
        )
        if not math.isclose(
            self.b0_b1_top_k_jaccard,
            expected_jaccard,
            rel_tol=0.0,
            abs_tol=1e-15,
        ):
            raise ValueError("B0/B1 Jaccard does not match counts")
        if self.data_eligibility is not DataEligibility.EXPLORATORY:
            raise ValueError("DailyReview is EXPLORATORY-only")
        content_hash = canonical_hash(self.semantic_payload())
        object.__setattr__(self, "content_hash", content_hash)
        object.__setattr__(
            self,
            "review_id",
            ArtifactId(f"daily-review-{content_hash.split(':', 1)[1][:24]}"),
        )

    def semantic_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "daily_decision_artifact_id": str(
                self.daily_decision_artifact_id
            ),
            "target_id": str(self.target_id),
            "recommendation_count": self.recommendation_count,
            "outcome_coverage": self.outcome_coverage,
            "positive_return_count": self.positive_return_count,
            "top_k_mean_target": self.top_k_mean_target,
            "candidate_population_mean_target": (
                self.candidate_population_mean_target
            ),
            "ranking_coverage": self.ranking_coverage,
            "data_quality_summary": [list(item) for item in self.data_quality_summary],
            "blocked_reason_counts": [
                list(item) for item in self.blocked_reason_counts
            ],
            "b0_b1_top_k_overlap_count": self.b0_b1_top_k_overlap_count,
            "b0_b1_top_k_union_count": self.b0_b1_top_k_union_count,
            "b0_b1_top_k_jaccard": self.b0_b1_top_k_jaccard,
            "unresolved_outcome_count": self.unresolved_outcome_count,
            "data_eligibility": self.data_eligibility.value,
        }

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            **self.semantic_payload(),
            "content_hash": self.content_hash,
            "review_id": str(self.review_id),
        }

    @classmethod
    def from_canonical_dict(
        cls,
        payload: Mapping[str, Any],
    ) -> DailyReviewReport:
        expected = {
            "schema_version",
            "daily_decision_artifact_id",
            "target_id",
            "recommendation_count",
            "outcome_coverage",
            "positive_return_count",
            "top_k_mean_target",
            "candidate_population_mean_target",
            "ranking_coverage",
            "data_quality_summary",
            "blocked_reason_counts",
            "b0_b1_top_k_overlap_count",
            "b0_b1_top_k_union_count",
            "b0_b1_top_k_jaccard",
            "unresolved_outcome_count",
            "data_eligibility",
            "content_hash",
            "review_id",
        }
        if set(payload) != expected or payload["schema_version"] != cls.SCHEMA_VERSION:
            raise ValueError("DailyReviewReport schema mismatch")
        top_mean = payload["top_k_mean_target"]
        population_mean = payload["candidate_population_mean_target"]
        review = cls(
            daily_decision_artifact_id=ArtifactId(
                str(payload["daily_decision_artifact_id"])
            ),
            target_id=TargetId(str(payload["target_id"])),
            recommendation_count=int(payload["recommendation_count"]),
            outcome_coverage=float(payload["outcome_coverage"]),
            positive_return_count=int(payload["positive_return_count"]),
            top_k_mean_target=(
                float(top_mean) if top_mean is not None else None
            ),
            candidate_population_mean_target=(
                float(population_mean)
                if population_mean is not None
                else None
            ),
            ranking_coverage=float(payload["ranking_coverage"]),
            data_quality_summary=_count_pairs(
                payload["data_quality_summary"],
                "data_quality_summary",
            ),
            blocked_reason_counts=_count_pairs(
                payload["blocked_reason_counts"],
                "blocked_reason_counts",
            ),
            b0_b1_top_k_overlap_count=int(
                payload["b0_b1_top_k_overlap_count"]
            ),
            b0_b1_top_k_union_count=int(
                payload["b0_b1_top_k_union_count"]
            ),
            b0_b1_top_k_jaccard=float(payload["b0_b1_top_k_jaccard"]),
            unresolved_outcome_count=int(payload["unresolved_outcome_count"]),
            data_eligibility=DataEligibility(str(payload["data_eligibility"])),
        )
        if (
            review.content_hash != payload["content_hash"]
            or str(review.review_id) != payload["review_id"]
        ):
            raise ValueError("DailyReviewReport identity mismatch")
        return review


@dataclass(frozen=True, slots=True)
class OutcomeSettlement:
    SCHEMA_VERSION = "phase-d-outcome-settlement-v1"

    daily_decision_artifact_id: ArtifactId
    daily_decision_content_hash: str
    settlement_source_archive_id: ArtifactId
    settlement_source_result_hash: str
    next_session_date: date
    target_protocol: TargetProtocol
    population_outcomes: tuple[PopulationTargetObservation, ...]
    recommendation_outcomes: tuple[RecommendationOutcome, ...]
    review: DailyReviewReport
    data_eligibility: DataEligibility
    content_hash: str = field(init=False)
    settlement_id: ArtifactId = field(init=False)

    def __post_init__(self) -> None:
        for label, value in (
            ("daily_decision_content_hash", self.daily_decision_content_hash),
            (
                "settlement_source_result_hash",
                self.settlement_source_result_hash,
            ),
        ):
            if (
                not isinstance(value, str)
                or not value.startswith("sha256:")
                or len(value) != 71
            ):
                raise ValueError(f"{label} must be a sha256 content hash")
        if self.target_protocol.target_id != _TARGET_ID:
            raise ValueError("OutcomeSettlement Target mismatch")
        if tuple(item.symbol for item in self.population_outcomes) != tuple(
            sorted(item.symbol for item in self.population_outcomes)
        ):
            raise ValueError("Population Outcomes must be ordered")
        population_by_id = {
            item.observation_id: item for item in self.population_outcomes
        }
        if len(population_by_id) != len(self.population_outcomes):
            raise ValueError("Population Outcomes must be unique")
        for item in self.recommendation_outcomes:
            population = population_by_id.get(item.population_observation_id)
            if (
                population is None
                or item.symbol != population.symbol
                or item.status != population.status
                or item.target_value != population.target_value
            ):
                raise ValueError("RecommendationOutcome population lineage mismatch")
        if (
            self.review.daily_decision_artifact_id
            != self.daily_decision_artifact_id
            or self.review.recommendation_count
            != len(self.recommendation_outcomes)
        ):
            raise ValueError("DailyReview lineage mismatch")
        if self.data_eligibility is not DataEligibility.EXPLORATORY:
            raise ValueError("OutcomeSettlement is EXPLORATORY-only")
        content_hash = canonical_hash(self.semantic_payload())
        object.__setattr__(self, "content_hash", content_hash)
        object.__setattr__(
            self,
            "settlement_id",
            ArtifactId(f"outcome-settlement-{content_hash.split(':', 1)[1][:24]}"),
        )

    def semantic_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "daily_decision_artifact_id": str(
                self.daily_decision_artifact_id
            ),
            "daily_decision_content_hash": self.daily_decision_content_hash,
            "settlement_source_archive_id": str(
                self.settlement_source_archive_id
            ),
            "settlement_source_result_hash": self.settlement_source_result_hash,
            "next_session_date": self.next_session_date.isoformat(),
            "target_protocol": self.target_protocol.canonical_payload(),
            "target_protocol_hash": self.target_protocol.protocol_hash,
            "population_outcomes": [
                item.to_canonical_dict() for item in self.population_outcomes
            ],
            "recommendation_outcomes": [
                item.to_canonical_dict()
                for item in self.recommendation_outcomes
            ],
            "review": self.review.to_canonical_dict(),
            "data_eligibility": self.data_eligibility.value,
        }

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            **self.semantic_payload(),
            "content_hash": self.content_hash,
            "settlement_id": str(self.settlement_id),
        }

    @classmethod
    def from_canonical_dict(
        cls,
        payload: Mapping[str, Any],
    ) -> OutcomeSettlement:
        expected = {
            "schema_version",
            "daily_decision_artifact_id",
            "daily_decision_content_hash",
            "settlement_source_archive_id",
            "settlement_source_result_hash",
            "next_session_date",
            "target_protocol",
            "target_protocol_hash",
            "population_outcomes",
            "recommendation_outcomes",
            "review",
            "data_eligibility",
            "content_hash",
            "settlement_id",
        }
        if set(payload) != expected or payload["schema_version"] != cls.SCHEMA_VERSION:
            raise ValueError("OutcomeSettlement schema mismatch")
        protocol_payload = _mapping(payload["target_protocol"], "TargetProtocol")
        universe_id = UniverseId(str(protocol_payload["universe_id"]))
        protocol = mr1_next_session_1030_target_protocol(universe_id)
        if (
            protocol.canonical_payload() != protocol_payload
            or protocol.protocol_hash != payload["target_protocol_hash"]
        ):
            raise ValueError("OutcomeSettlement TargetProtocol mismatch")
        settlement = cls(
            daily_decision_artifact_id=ArtifactId(
                str(payload["daily_decision_artifact_id"])
            ),
            daily_decision_content_hash=str(
                payload["daily_decision_content_hash"]
            ),
            settlement_source_archive_id=ArtifactId(
                str(payload["settlement_source_archive_id"])
            ),
            settlement_source_result_hash=str(
                payload["settlement_source_result_hash"]
            ),
            next_session_date=date.fromisoformat(
                str(payload["next_session_date"])
            ),
            target_protocol=protocol,
            population_outcomes=tuple(
                PopulationTargetObservation.from_canonical_dict(
                    _mapping(item, "PopulationTargetObservation")
                )
                for item in payload["population_outcomes"]
            ),
            recommendation_outcomes=tuple(
                RecommendationOutcome.from_canonical_dict(
                    _mapping(item, "RecommendationOutcome")
                )
                for item in payload["recommendation_outcomes"]
            ),
            review=DailyReviewReport.from_canonical_dict(
                _mapping(payload["review"], "DailyReviewReport")
            ),
            data_eligibility=DataEligibility(str(payload["data_eligibility"])),
        )
        if (
            settlement.content_hash != payload["content_hash"]
            or str(settlement.settlement_id) != payload["settlement_id"]
        ):
            raise ValueError("OutcomeSettlement identity mismatch")
        return settlement


def settle_mr1_1030_outcomes(
    *,
    daily_decision_bundle: PhaseDDailyDecisionBundle,
    daily_decision_artifact_id: ArtifactId,
    settlement_provider_result: PublicCompositeProviderResult,
    settlement_source_archive_id: ArtifactId,
    next_session_date: date,
) -> OutcomeSettlement:
    """Settle the exact existing MR1 10:30 Target without mutating T evidence."""

    if (
        daily_decision_bundle.status
        is not DailyDecisionArtifactStatus.DECISION_PUBLISHED
        or daily_decision_bundle.artifact_id != daily_decision_artifact_id
        or daily_decision_bundle.decision_price_snapshot is None
    ):
        raise ValueError("Outcome Settlement requires a published daily decision")
    decision_date = daily_decision_bundle.source_manifest.decision_time.value.astimezone(
        _SHANGHAI
    ).date()
    if next_session_date <= decision_date:
        raise ValueError("next_session_date must follow the Decision Date")
    protocol = mr1_next_session_1030_target_protocol(
        daily_decision_bundle.prediction_runs[0].universe_id
    )
    population_symbols = tuple(
        sorted(
            {
                *(
                    item.symbol
                    for item in daily_decision_bundle.prediction_runs[0].predictions
                ),
                *(
                    item.symbol
                    for item in daily_decision_bundle.prediction_runs[0].rejections
                ),
            }
        )
    )
    for run in daily_decision_bundle.prediction_runs[1:]:
        other_symbols = tuple(
            sorted(
                {
                    *(item.symbol for item in run.predictions),
                    *(item.symbol for item in run.rejections),
                }
            )
        )
        if other_symbols != population_symbols:
            raise ValueError("PredictionRuns disagree on Candidate Population")
    reference_by_symbol = {
        item.symbol: item
        for item in daily_decision_bundle.decision_price_snapshot.observations
    }
    payload_by_id = {
        item.source_artifact_id: item
        for item in settlement_provider_result.raw_payloads
    }
    endpoint_by_symbol: dict[str, PublicBar] = {}
    for bar in settlement_provider_result.bars:
        local = bar.event_time.astimezone(_SHANGHAI)
        if local.date() != next_session_date or local.time().replace(
            tzinfo=None
        ) != time(10, 30):
            continue
        if bar.symbol in endpoint_by_symbol:
            raise ValueError("duplicate exact 10:30 endpoint bar")
        endpoint_by_symbol[bar.symbol] = bar
    population_outcomes: list[PopulationTargetObservation] = []
    for symbol in population_symbols:
        reference = reference_by_symbol.get(symbol)
        endpoint = endpoint_by_symbol.get(symbol)
        reason: str | None = None
        composite: CompositeBar | None = None
        if reference is None or reference.price is None:
            reason = "DECISION_REFERENCE_PRICE_UNAVAILABLE"
        elif endpoint is None:
            reason = "EXACT_ENDPOINT_BAR_MISSING"
        elif endpoint.available_time is None:
            reason = "ENDPOINT_AVAILABLE_TIME_UNKNOWN"
        elif endpoint.adjustment_basis != "NONE":
            reason = "ADJUSTMENT_BASIS_INCOMPATIBLE"
        else:
            source = payload_by_id[endpoint.source_artifact_id]
            if source.provider_id.value != "provider-tencent-public":
                reason = "ENDPOINT_PROVIDER_NOT_TENCENT"
            else:
                composite = CompositeBar(
                    symbol=endpoint.symbol,
                    timestamp=endpoint.event_time,
                    open=endpoint.open,
                    high=endpoint.high,
                    low=endpoint.low,
                    close=endpoint.close,
                    volume=endpoint.volume,
                    amount=endpoint.amount,
                    source=CompositeSourceKind.TENCENT,
                )
        row = build_mr1_next_session_1030_return_observation(
            symbol=symbol,
            decision_date=decision_date,
            next_date=next_session_date,
            reference_price=(
                float(reference.price)
                if reference is not None and reference.price is not None
                else 1.0
            ),
            endpoint_bar=composite,
        )
        if reason is None and row["status"] == "AVAILABLE":
            assert endpoint is not None
            population_outcomes.append(
                PopulationTargetObservation(
                    daily_decision_artifact_id=daily_decision_artifact_id,
                    symbol=symbol,
                    target_id=_TARGET_ID,
                    status=OutcomeStatus.AVAILABLE,
                    target_value=float(row["value"]),
                    observed_at=endpoint.available_time,
                    source_artifact_id=endpoint.source_artifact_id,
                    reason_code=None,
                    data_eligibility=DataEligibility.EXPLORATORY,
                )
            )
        else:
            population_outcomes.append(
                PopulationTargetObservation(
                    daily_decision_artifact_id=daily_decision_artifact_id,
                    symbol=symbol,
                    target_id=_TARGET_ID,
                    status=OutcomeStatus.UNRESOLVED,
                    target_value=None,
                    observed_at=None,
                    source_artifact_id=(
                        endpoint.source_artifact_id
                        if endpoint is not None
                        else None
                    ),
                    reason_code=reason or str(row["missing_reason"]),
                    data_eligibility=DataEligibility.EXPLORATORY,
                )
            )
    population_by_symbol = {
        item.symbol: item for item in population_outcomes
    }
    recommendation_outcomes = tuple(
        RecommendationOutcome(
            daily_decision_artifact_id=daily_decision_artifact_id,
            recommendation_id=item.recommendation_id,
            prediction_run_id=item.prediction_run_id,
            model_id=item.model_id,
            symbol=item.symbol,
            target_id=_TARGET_ID,
            population_observation_id=population_by_symbol[
                item.symbol
            ].observation_id,
            status=population_by_symbol[item.symbol].status,
            target_value=population_by_symbol[item.symbol].target_value,
            data_eligibility=DataEligibility.EXPLORATORY,
        )
        for item in daily_decision_bundle.recommendations
    )
    review = _build_daily_review(
        daily_decision_bundle=daily_decision_bundle,
        daily_decision_artifact_id=daily_decision_artifact_id,
        population_outcomes=tuple(population_outcomes),
        recommendation_outcomes=recommendation_outcomes,
    )
    return OutcomeSettlement(
        daily_decision_artifact_id=daily_decision_artifact_id,
        daily_decision_content_hash=daily_decision_bundle.content_hash,
        settlement_source_archive_id=settlement_source_archive_id,
        settlement_source_result_hash=settlement_provider_result.content_hash,
        next_session_date=next_session_date,
        target_protocol=protocol,
        population_outcomes=tuple(population_outcomes),
        recommendation_outcomes=recommendation_outcomes,
        review=review,
        data_eligibility=DataEligibility.EXPLORATORY,
    )


def _build_daily_review(
    *,
    daily_decision_bundle: PhaseDDailyDecisionBundle,
    daily_decision_artifact_id: ArtifactId,
    population_outcomes: tuple[PopulationTargetObservation, ...],
    recommendation_outcomes: tuple[RecommendationOutcome, ...],
) -> DailyReviewReport:
    recommendation_values = [
        float(item.target_value)
        for item in recommendation_outcomes
        if item.status is OutcomeStatus.AVAILABLE
        and item.target_value is not None
    ]
    population_values = [
        float(item.target_value)
        for item in population_outcomes
        if item.status is OutcomeStatus.AVAILABLE
        and item.target_value is not None
    ]
    blocked = Counter(
        reason
        for item in daily_decision_bundle.entry_assessments
        for reason in item.blocking_reasons
    )
    by_model = {
        model_id: {
            item.symbol
            for item in daily_decision_bundle.recommendations
            if item.model_id == model_id
        }
        for model_id in (B0_MOMENTUM_MODEL_ID, B1_BALANCED_MODEL_ID)
    }
    intersection = (
        by_model[B0_MOMENTUM_MODEL_ID]
        & by_model[B1_BALANCED_MODEL_ID]
    )
    union = (
        by_model[B0_MOMENTUM_MODEL_ID]
        | by_model[B1_BALANCED_MODEL_ID]
    )
    recommendation_count = len(recommendation_outcomes)
    unresolved = recommendation_count - len(recommendation_values)
    return DailyReviewReport(
        daily_decision_artifact_id=daily_decision_artifact_id,
        target_id=_TARGET_ID,
        recommendation_count=recommendation_count,
        outcome_coverage=(
            len(recommendation_values) / recommendation_count
            if recommendation_count
            else 0.0
        ),
        positive_return_count=sum(
            value > 0.0 for value in recommendation_values
        ),
        top_k_mean_target=(
            mean(recommendation_values) if recommendation_values else None
        ),
        candidate_population_mean_target=(
            mean(population_values) if population_values else None
        ),
        ranking_coverage=(
            mean(
                item.ranking_coverage
                for item in daily_decision_bundle.prediction_runs
            )
            if daily_decision_bundle.prediction_runs
            else 0.0
        ),
        data_quality_summary=(
            (daily_decision_bundle.data_quality_report.status.value, 1),
        ),
        blocked_reason_counts=tuple(sorted(blocked.items())),
        b0_b1_top_k_overlap_count=len(intersection),
        b0_b1_top_k_union_count=len(union),
        b0_b1_top_k_jaccard=(
            len(intersection) / len(union) if union else 0.0
        ),
        unresolved_outcome_count=unresolved,
        data_eligibility=DataEligibility.EXPLORATORY,
    )


def _count_pairs(value: Any, label: str) -> tuple[tuple[str, int], ...]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    output: list[tuple[str, int]] = []
    for item in value:
        if (
            not isinstance(item, list)
            or len(item) != 2
            or isinstance(item[1], bool)
            or not isinstance(item[1], int)
        ):
            raise ValueError(f"{label} item mismatch")
        output.append((str(item[0]), item[1]))
    return tuple(output)


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value
