"""Entry plumbing gate v0: REJECT or WAIT_CONFIRMATION, never ENTER."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.data.daily_quality import (
    DailyDataQualityStatus,
    DataQualityReport,
)
from market_regime_alpha.data.source_manifest import (
    CriticalSourceFact,
    SourceFieldQualityStatus,
    SourceManifest,
)
from market_regime_alpha.daily_decision._support import (
    canonical_hash,
    require_strings,
    require_text,
)
from market_regime_alpha.daily_decision.recommendation import (
    CandidateDataQuality,
    CandidateRecommendation,
)
from market_regime_alpha.daily_decision.snapshot import (
    DecisionPriceQuality,
    DecisionPriceSnapshot,
)
from market_regime_alpha.platform.prediction_run import PredictionRun
from market_regime_alpha.universe.contracts import (
    TradingEligibilitySnapshot,
    TradingEligibilityStatus,
)


ENTRY_PLUMBING_GATE_V0 = ArtifactId("entry-plumbing-gate-v0")


class EntryAssessmentState(str, Enum):
    REJECT = "REJECT"
    WAIT_CONFIRMATION = "WAIT_CONFIRMATION"


@dataclass(frozen=True, slots=True)
class EntryAssessment:
    SCHEMA_VERSION = "phase-d-entry-assessment-v1"

    gate_id: ArtifactId
    decision_snapshot_id: ArtifactId
    recommendation_id: ArtifactId
    prediction_run_id: ArtifactId
    symbol: str
    entry_state: EntryAssessmentState
    blocking_reasons: tuple[str, ...]
    data_eligibility: DataEligibility
    content_hash: str = field(init=False)
    entry_assessment_id: ArtifactId = field(init=False)

    def __post_init__(self) -> None:
        if self.gate_id != ENTRY_PLUMBING_GATE_V0:
            raise ValueError("unsupported Entry plumbing gate")
        require_text("symbol", self.symbol)
        if not isinstance(self.entry_state, EntryAssessmentState):
            raise TypeError("entry_state must be an EntryAssessmentState")
        require_strings(
            "blocking_reasons",
            self.blocking_reasons,
            required=True,
        )
        if (
            self.entry_state is EntryAssessmentState.WAIT_CONFIRMATION
            and self.blocking_reasons != ("ENTRY_MODEL_NOT_YET_VALIDATED",)
        ):
            raise ValueError("WAIT_CONFIRMATION requires the fixed validation blocker")
        if (
            self.entry_state is EntryAssessmentState.REJECT
            and self.blocking_reasons == ("ENTRY_MODEL_NOT_YET_VALIDATED",)
        ):
            raise ValueError("REJECT requires a data/plumbing blocker")
        if self.data_eligibility is not DataEligibility.EXPLORATORY:
            raise ValueError("Entry plumbing is EXPLORATORY-only")
        content_hash = canonical_hash(self.semantic_payload())
        object.__setattr__(self, "content_hash", content_hash)
        object.__setattr__(
            self,
            "entry_assessment_id",
            ArtifactId(f"entry-assessment-{content_hash.split(':', 1)[1][:24]}"),
        )

    def semantic_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "gate_id": str(self.gate_id),
            "decision_snapshot_id": str(self.decision_snapshot_id),
            "recommendation_id": str(self.recommendation_id),
            "prediction_run_id": str(self.prediction_run_id),
            "symbol": self.symbol,
            "entry_state": self.entry_state.value,
            "blocking_reasons": list(self.blocking_reasons),
            "data_eligibility": self.data_eligibility.value,
        }

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            **self.semantic_payload(),
            "content_hash": self.content_hash,
            "entry_assessment_id": str(self.entry_assessment_id),
        }

    @classmethod
    def from_canonical_dict(
        cls,
        payload: Mapping[str, Any],
    ) -> EntryAssessment:
        expected = {
            "schema_version",
            "gate_id",
            "decision_snapshot_id",
            "recommendation_id",
            "prediction_run_id",
            "symbol",
            "entry_state",
            "blocking_reasons",
            "data_eligibility",
            "content_hash",
            "entry_assessment_id",
        }
        if set(payload) != expected or payload["schema_version"] != cls.SCHEMA_VERSION:
            raise ValueError("EntryAssessment schema mismatch")
        assessment = cls(
            gate_id=ArtifactId(str(payload["gate_id"])),
            decision_snapshot_id=ArtifactId(str(payload["decision_snapshot_id"])),
            recommendation_id=ArtifactId(str(payload["recommendation_id"])),
            prediction_run_id=ArtifactId(str(payload["prediction_run_id"])),
            symbol=str(payload["symbol"]),
            entry_state=EntryAssessmentState(str(payload["entry_state"])),
            blocking_reasons=tuple(
                str(item) for item in payload["blocking_reasons"]
            ),
            data_eligibility=DataEligibility(str(payload["data_eligibility"])),
        )
        if (
            assessment.content_hash != payload["content_hash"]
            or str(assessment.entry_assessment_id)
            != payload["entry_assessment_id"]
        ):
            raise ValueError("EntryAssessment identity mismatch")
        return assessment


def assess_entry_plumbing(
    *,
    recommendations: tuple[CandidateRecommendation, ...],
    prediction_runs: tuple[PredictionRun, ...],
    decision_snapshot: DecisionPriceSnapshot,
    source_manifest: SourceManifest,
    data_quality_report: DataQualityReport,
    eligibility_snapshot: TradingEligibilitySnapshot,
) -> tuple[EntryAssessment, ...]:
    """Bind Candidate evidence and emit only fail-closed plumbing states."""

    if (
        source_manifest.source_manifest_id
        != decision_snapshot.source_manifest_id
        or data_quality_report.source_manifest_id
        != source_manifest.source_manifest_id
    ):
        raise ValueError("Entry plumbing source evidence mismatch")
    runs = {item.prediction_run_id: item for item in prediction_runs}
    assessments: list[EntryAssessment] = []
    for recommendation in recommendations:
        blockers: list[str] = []
        run = runs.get(recommendation.prediction_run_id)
        if (
            run is None
            or run.model_id != recommendation.model_id
            or run.target_id != recommendation.target_id
        ):
            raise ValueError("Recommendation does not bind a supplied PredictionRun")
        if (
            recommendation.decision_snapshot_id
            != decision_snapshot.decision_snapshot_id
        ):
            raise ValueError("Recommendation Decision Price Snapshot mismatch")
        if recommendation.data_quality is CandidateDataQuality.INSUFFICIENT:
            blockers.append("CANDIDATE_DATA_QUALITY_INSUFFICIENT")
        if data_quality_report.status in {
            DailyDataQualityStatus.DATA_BLOCKED,
            DailyDataQualityStatus.INSUFFICIENT,
        }:
            blockers.append("SOURCE_MANIFEST_INCOMPLETE")
        if (
            eligibility_snapshot.status_for(recommendation.symbol)
            is not TradingEligibilityStatus.ELIGIBLE
        ):
            blockers.append("ELIGIBILITY_NOT_PASSED")
        price = decision_snapshot.observation_for(recommendation.symbol)
        if price is None or price.quality is DecisionPriceQuality.INSUFFICIENT:
            blockers.append("DECISION_PRICE_SNAPSHOT_MISSING")
        trading_field = next(
            (
                item
                for item in source_manifest.fields
                if item.symbol == recommendation.symbol
                and item.critical_fact is CriticalSourceFact.TRADING_STATUS
            ),
            None,
        )
        if (
            trading_field is None
            or trading_field.quality_status
            is SourceFieldQualityStatus.INSUFFICIENT
        ):
            blockers.append("TRADING_STATUS_UNAVAILABLE")
        unique_blockers = tuple(dict.fromkeys(blockers))
        if unique_blockers:
            state = EntryAssessmentState.REJECT
            reasons = unique_blockers
        else:
            state = EntryAssessmentState.WAIT_CONFIRMATION
            reasons = ("ENTRY_MODEL_NOT_YET_VALIDATED",)
        assessments.append(
            EntryAssessment(
                gate_id=ENTRY_PLUMBING_GATE_V0,
                decision_snapshot_id=decision_snapshot.decision_snapshot_id,
                recommendation_id=recommendation.recommendation_id,
                prediction_run_id=recommendation.prediction_run_id,
                symbol=recommendation.symbol,
                entry_state=state,
                blocking_reasons=reasons,
                data_eligibility=DataEligibility.EXPLORATORY,
            )
        )
    return tuple(assessments)
