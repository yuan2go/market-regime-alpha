"""Explicit inputs for one post-close experimental prediction, never a fold."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid5

from market_regime_alpha.research_qualification.domain.model import ArtifactBinding
from market_regime_alpha.shared.hashing import canonical_json_sha256
from market_regime_alpha.shared.time import require_utc


@dataclass(frozen=True, slots=True)
class DailyPredictionPlan:
    prediction_id: UUID
    experimental_model_use_id: UUID
    model_version_id: UUID
    provider_product_id: UUID
    universe_id: UUID
    universe_scope: ArtifactBinding
    classification_scheme: str
    classification_code: str
    instrument_ids: tuple[UUID, ...]
    eligibility_policy_id: UUID
    feature_definition_id: UUID
    candidate_policy_id: UUID
    context_policy_id: UUID
    strategy_version_id: UUID
    target_definition_id: UUID
    input_session_id: UUID
    target_session_id: UUID
    input_cutoff: datetime
    decision_time: datetime
    input_content_sha256: str
    code_artifact: ArtifactBinding
    config_artifact: ArtifactBinding
    code_sha: str
    baseline_strategy_version_id: UUID

    def __post_init__(self) -> None:
        from market_regime_alpha.shared.identity import ContentHash

        for name in ("input_cutoff", "decision_time"):
            require_utc(getattr(self, name), field=name)
        if self.input_cutoff > self.decision_time:
            raise ValueError("daily input cutoff exceeds DecisionTime")
        if self.input_session_id == self.target_session_id:
            raise ValueError("daily Target must be a future session")
        if self.strategy_version_id == self.baseline_strategy_version_id:
            raise ValueError("model and rule Forecast authorities require distinct explicit strategies")
        if not self.instrument_ids or self.instrument_ids != tuple(sorted(set(self.instrument_ids), key=str)):
            raise ValueError("daily population must be complete, unique and UUID ordered")
        ContentHash(self.input_content_sha256)
        if not self.classification_scheme or not self.classification_code:
            raise ValueError("explicit Universe classification is required")

    @property
    def dataset_id(self) -> UUID:
        return uuid5(self.prediction_id, "decision-input-dataset")

    @property
    def runtime_run_id(self) -> UUID:
        return uuid5(self.prediction_id, "prediction-runtime")

    @property
    def content_sha256(self) -> str:
        return canonical_json_sha256(self)


@dataclass(frozen=True, slots=True)
class DailyPopulationMember:
    instrument_id: UUID
    universe_member_id: UUID
    membership_status: str
    membership_reason: str
    eligibility_assessment_id: UUID | None
    eligibility_result: str | None
    eligibility_reason: str | None

    @property
    def eligible(self) -> bool:
        return self.membership_status == "INCLUDED" and self.eligibility_result == "ELIGIBLE"
