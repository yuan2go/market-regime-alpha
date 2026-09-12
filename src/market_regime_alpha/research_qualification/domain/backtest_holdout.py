"""Append-only exploratory reservation and opening, never formal LOCKED_OOS."""

from dataclasses import dataclass
from datetime import date
from typing import Any
from uuid import UUID

from market_regime_alpha.research_qualification.domain.historical_matrix import HistoricalTimeSplit
from market_regime_alpha.research_qualification.domain.model import ArtifactBinding
from market_regime_alpha.shared.hashing import canonical_json_sha256
from market_regime_alpha.shared.identity import ContentHash


def artifact_payload(binding: ArtifactBinding) -> dict[str, Any]:
    return {"artifact_id": str(binding.artifact_id), "content_sha256": str(binding.content_sha256), "size_bytes": binding.size_bytes}


@dataclass(frozen=True, slots=True)
class BacktestHoldoutReservation:
    reservation_id: UUID
    development_run_id: UUID
    development_specification_sha256: str
    future_run_id: UUID
    future_study_code: str
    time_split: HistoricalTimeSplit
    selection_arm_codes: tuple[str, ...]
    protocol_artifact: ArtifactBinding

    def __post_init__(self) -> None:
        ContentHash(self.development_specification_sha256)
        if self.future_run_id == self.development_run_id:
            raise ValueError("holdout requires a separate future Backtest")
        if not self.selection_arm_codes or len(set(self.selection_arm_codes)) != len(self.selection_arm_codes) or len(self.selection_arm_codes) > 13:
            raise ValueError("holdout requires 1..13 distinct predeclared selection candidates")
        if len(self.time_split.validation_dates) > 60 or len(self.time_split.fit_dates) > 250:
            raise ValueError("holdout is bounded to 60 validation and 250 FIT sessions")
        if not self.future_study_code or len(self.future_study_code) > 50:
            raise ValueError("holdout needs its exact future study code")

    def payload(self) -> dict[str, Any]:
        return {
            "schema": "mra-backtest-exploratory-holdout-v1",
            "reservation_id": str(self.reservation_id),
            "development_run_id": str(self.development_run_id),
            "development_specification_sha256": self.development_specification_sha256,
            "future_run_id": str(self.future_run_id),
            "future_study_code": self.future_study_code,
            "time_split": {name: [str(d) for d in getattr(self.time_split, name)] for name in
                ("fit_dates", "purge_dates", "embargo_dates", "validation_dates")},
            "selection_arm_codes": list(self.selection_arm_codes),
            "protocol_artifact": artifact_payload(self.protocol_artifact),
            "selection_rule": "ALL_ARM_COMMON_VALIDATION_MAE_TIES_BY_FROZEN_ORDINAL",
            "authority": "EXPLORATORY_TEMPORAL_ONLY_NOT_FORMAL_OOS_OR_PIT",
        }

    @property
    def content_sha256(self) -> str:
        return canonical_json_sha256(self.payload())

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "BacktestHoldoutReservation":
        b = payload["protocol_artifact"]
        plan = cls(UUID(payload["reservation_id"]), UUID(payload["development_run_id"]),
            payload["development_specification_sha256"], UUID(payload["future_run_id"]), payload["future_study_code"],
            HistoricalTimeSplit(**{name: tuple(date.fromisoformat(d) for d in days) for name, days in payload["time_split"].items()}),
            tuple(payload["selection_arm_codes"]), ArtifactBinding(UUID(b["artifact_id"]), ContentHash(b["content_sha256"]), b["size_bytes"]))
        if plan.payload() != payload:
            raise ValueError("holdout reservation payload differs from its closed contract")
        return plan


@dataclass(frozen=True, slots=True)
class BacktestHoldoutOpening:
    reservation_id: UUID
    reservation_sha256: str
    heldout_run_id: UUID
    heldout_specification_sha256: str
    selected_development_arm_id: UUID
    selected_arm_code: str
    development_projection_sha256: str
    selection_artifact: ArtifactBinding
    allowed_evaluation_ids: tuple[UUID, ...]
    development_evaluation_roster: tuple[tuple[str, str, str, str], ...]
    evaluation_scopes: tuple[tuple[UUID, UUID, UUID, UUID], ...]

    def __post_init__(self) -> None:
        for digest in (self.reservation_sha256, self.heldout_specification_sha256, self.development_projection_sha256):
            ContentHash(digest)
        if not self.allowed_evaluation_ids or len(self.allowed_evaluation_ids) > 200 or self.allowed_evaluation_ids != tuple(sorted(set(self.allowed_evaluation_ids), key=str)):
            raise ValueError("holdout opening requires the complete sorted bounded Evaluation roster")
        if not self.development_evaluation_roster or len(self.development_evaluation_roster)>300:
            raise ValueError("holdout opening needs exact completed development Evaluations")
        if tuple(row[0] for row in self.evaluation_scopes) != self.allowed_evaluation_ids or any(len(set(row[i] for row in self.evaluation_scopes))!=len(self.evaluation_scopes) for i in range(4)):
            raise ValueError("holdout requires one exact Evaluation/Partition/Experiment/requirement mapping")
        for identity, plan, inputs, metrics in self.development_evaluation_roster:
            UUID(identity)
            for digest in (plan, inputs, metrics):
                ContentHash(digest)

    def payload(self) -> dict[str, Any]:
        return {"schema": "mra-backtest-exploratory-holdout-opening-v1",
            "reservation_id": str(self.reservation_id), "reservation_sha256": self.reservation_sha256,
            "heldout_run_id": str(self.heldout_run_id), "heldout_specification_sha256": self.heldout_specification_sha256,
            "selected_development_arm_id": str(self.selected_development_arm_id), "selected_arm_code": self.selected_arm_code,
            "development_projection_sha256": self.development_projection_sha256, "selection_artifact": artifact_payload(self.selection_artifact),
            "allowed_evaluation_ids": [str(i) for i in self.allowed_evaluation_ids],
            "evaluation_scopes": [[str(i) for i in row] for row in self.evaluation_scopes],
            "development_evaluation_roster": [list(row) for row in self.development_evaluation_roster]}

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "BacktestHoldoutOpening":
        artifact=payload["selection_artifact"]
        if any(len(row)!=4 for row in payload["evaluation_scopes"]):
            raise ValueError("holdout Evaluation scope needs exactly four identities")
        result=cls(UUID(payload["reservation_id"]),payload["reservation_sha256"],UUID(payload["heldout_run_id"]),
            payload["heldout_specification_sha256"],UUID(payload["selected_development_arm_id"]),payload["selected_arm_code"],
            payload["development_projection_sha256"],ArtifactBinding(UUID(artifact["artifact_id"]),ContentHash(artifact["content_sha256"]),artifact["size_bytes"]),
            tuple(UUID(identity) for identity in payload["allowed_evaluation_ids"]),tuple(tuple(row) for row in payload["development_evaluation_roster"]),
            tuple((UUID(row[0]),UUID(row[1]),UUID(row[2]),UUID(row[3])) for row in payload["evaluation_scopes"]))
        if result.payload()!=payload:
            raise ValueError("holdout opening payload differs from its closed contract")
        return result

    @property
    def content_sha256(self) -> str:
        return canonical_json_sha256(self.payload())
