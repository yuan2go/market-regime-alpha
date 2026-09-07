"""Explicit experimental use of a completed model, never qualification."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from market_regime_alpha.research_qualification.domain.model import ArtifactBinding
from market_regime_alpha.shared.identity import ContentHash
from market_regime_alpha.shared.hashing import canonical_json_sha256
from market_regime_alpha.shared.time import require_utc


@dataclass(frozen=True, slots=True)
class ExperimentalModelUsePlan:
    experimental_model_use_id: UUID
    model_version_id: UUID
    target_metric_definition_id: UUID
    feature_roster_sha256: str
    protocol_artifact: ArtifactBinding
    valid_from: datetime
    expires_at: datetime
    baseline_strategy_version_id: UUID
    purpose: str = "POST_CLOSE_RESEARCH"

    def __post_init__(self) -> None:
        ContentHash(self.feature_roster_sha256)
        require_utc(self.valid_from, field="valid_from")
        require_utc(self.expires_at, field="expires_at")
        if self.purpose != "POST_CLOSE_RESEARCH" or self.valid_from >= self.expires_at:
            raise ValueError("experimental use requires a bounded POST_CLOSE_RESEARCH interval")

    @property
    def content_sha256(self) -> str:
        return canonical_json_sha256(self)


@dataclass(frozen=True, slots=True)
class ExperimentalModelUseRecord:
    plan: ExperimentalModelUsePlan
    registered_at: datetime
    revoked_at: datetime | None
