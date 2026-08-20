"""CandidateSet research contract separated from Recommendation and Entry."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite
from typing import Any

from market_regime_alpha.core.identity import ArtifactId, FeatureDefinitionId
from market_regime_alpha.evidence.envelope import ArtifactEnvelope
from market_regime_alpha.research.capital_evolution.contracts import (
    CapitalEvolutionState,
)
from market_regime_alpha.research.market_regime.contracts import MarketState
from market_regime_alpha.research.cross_sectional_ranking import competition_ranks
from market_regime_alpha.research.theme_rotation.contracts import RotationState


class CandidateSelectionStatus(str, Enum):
    SELECTED = "SELECTED"
    WATCHLIST = "WATCHLIST"
    REJECTED = "REJECTED"
    DATA_INSUFFICIENT = "DATA_INSUFFICIENT"


@dataclass(frozen=True, slots=True)
class CandidateRecord:
    symbol: str
    primary_theme_id: str | None
    supporting_theme_ids: tuple[str, ...]
    market_regime_status: MarketState
    theme_rotation_state: RotationState
    capital_evolution_state: CapitalEvolutionState
    market_regime_score: float | None
    theme_score: float | None
    capital_evolution_score: float | None
    candidate_discovery_score: float | None
    rank: int | None
    selection_status: CandidateSelectionStatus
    reason_codes: tuple[str, ...]
    source_feature_ids: tuple[FeatureDefinitionId, ...]
    input_artifact_ids: tuple[ArtifactId, ...]

    def __post_init__(self) -> None:
        for value in (
            self.market_regime_score,
            self.theme_score,
            self.capital_evolution_score,
        ):
            if value is not None and (
                not isfinite(value) or not -1.0 <= value <= 1.0
            ):
                raise ValueError("Candidate component score must be within [-1, 1]")
        if self.candidate_discovery_score is not None and (
            not isfinite(self.candidate_discovery_score)
            or not 0.0 <= self.candidate_discovery_score <= 1.0
        ):
            raise ValueError("Candidate Discovery score must be within [0, 1]")
        if self.rank is not None and self.rank <= 0:
            raise ValueError("Candidate rank must be positive")
        if (
            self.selection_status
            in {
                CandidateSelectionStatus.REJECTED,
                CandidateSelectionStatus.DATA_INSUFFICIENT,
            }
            and self.rank is not None
        ):
            raise ValueError("rejected or insufficient Candidate cannot carry rank")
        if not self.reason_codes:
            raise ValueError("Candidate reconciliation requires reason_codes")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "primary_theme_id": self.primary_theme_id,
            "supporting_theme_ids": list(self.supporting_theme_ids),
            "market_regime_status": self.market_regime_status.value,
            "theme_rotation_state": self.theme_rotation_state.value,
            "capital_evolution_state": self.capital_evolution_state.value,
            "market_regime_score": self.market_regime_score,
            "theme_score": self.theme_score,
            "capital_evolution_score": self.capital_evolution_score,
            "candidate_discovery_score": self.candidate_discovery_score,
            "rank": self.rank,
            "selection_status": self.selection_status.value,
            "reason_codes": list(self.reason_codes),
            "source_feature_ids": [
                str(item) for item in self.source_feature_ids
            ],
            "input_artifact_ids": [
                str(item) for item in self.input_artifact_ids
            ],
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: dict[str, Any]
    ) -> CandidateRecord:
        expected = {
            "symbol",
            "primary_theme_id",
            "supporting_theme_ids",
            "market_regime_status",
            "theme_rotation_state",
            "capital_evolution_state",
            "market_regime_score",
            "theme_score",
            "capital_evolution_score",
            "candidate_discovery_score",
            "rank",
            "selection_status",
            "reason_codes",
            "source_feature_ids",
            "input_artifact_ids",
        }
        if set(payload) != expected:
            raise ValueError("CandidateRecord fields mismatch")
        return cls(
            symbol=str(payload["symbol"]),
            primary_theme_id=(
                str(payload["primary_theme_id"])
                if payload["primary_theme_id"] is not None
                else None
            ),
            supporting_theme_ids=_strings(payload["supporting_theme_ids"]),
            market_regime_status=MarketState(
                str(payload["market_regime_status"])
            ),
            theme_rotation_state=RotationState(
                str(payload["theme_rotation_state"])
            ),
            capital_evolution_state=CapitalEvolutionState(
                str(payload["capital_evolution_state"])
            ),
            market_regime_score=_optional_float(
                payload["market_regime_score"]
            ),
            theme_score=_optional_float(payload["theme_score"]),
            capital_evolution_score=_optional_float(
                payload["capital_evolution_score"]
            ),
            candidate_discovery_score=_optional_float(
                payload["candidate_discovery_score"]
            ),
            rank=(
                int(payload["rank"]) if payload["rank"] is not None else None
            ),
            selection_status=CandidateSelectionStatus(
                str(payload["selection_status"])
            ),
            reason_codes=_strings(payload["reason_codes"]),
            source_feature_ids=tuple(
                FeatureDefinitionId(value)
                for value in _strings(payload["source_feature_ids"])
            ),
            input_artifact_ids=tuple(
                ArtifactId(value)
                for value in _strings(payload["input_artifact_ids"])
            ),
        )


@dataclass(frozen=True, slots=True)
class CandidateSet:
    """Complete research-layer reconciliation, not a Recommendation or buy list."""

    envelope: ArtifactEnvelope
    records: tuple[CandidateRecord, ...]
    minimum_candidate_population: int
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        symbols = tuple(item.symbol for item in self.records)
        if symbols != tuple(sorted(symbols)) or len(symbols) != len(set(symbols)):
            raise ValueError("CandidateSet records must be symbol-sorted and unique")
        ranked = tuple(item for item in self.records if item.rank is not None)
        if any(item.candidate_discovery_score is None for item in ranked):
            raise ValueError("ranked Candidate requires a discovery score")
        scores = {
            item.symbol: item.candidate_discovery_score
            for item in ranked
            if item.candidate_discovery_score is not None
        }
        if {item.symbol: item.rank for item in ranked} != competition_ranks(
            scores,
            higher_is_better=True,
        ):
            raise ValueError("CandidateSet ranks must preserve equal-score ties")
        if self.minimum_candidate_population <= 0:
            raise ValueError("minimum Candidate population must be positive")
        self.envelope.verify_payload(self.artifact_payload())

    @property
    def selected(self) -> tuple[CandidateRecord, ...]:
        return tuple(
            sorted(
                (
                    item
                    for item in self.records
                    if item.selection_status
                    is CandidateSelectionStatus.SELECTED
                ),
                key=lambda item: item.rank or 0,
            )
        )

    def artifact_payload(self) -> dict[str, Any]:
        return {
            "records": [item.to_canonical_dict() for item in self.records],
            "minimum_candidate_population": self.minimum_candidate_population,
            "reason_codes": list(self.reason_codes),
        }

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "envelope": self.envelope.to_canonical_dict(),
            **self.artifact_payload(),
        }

    @classmethod
    def from_canonical_dict(cls, payload: dict[str, Any]) -> CandidateSet:
        if set(payload) != {
            "envelope",
            "records",
            "minimum_candidate_population",
            "reason_codes",
        }:
            raise ValueError("CandidateSet fields mismatch")
        return cls(
            envelope=ArtifactEnvelope.from_canonical_dict(
                _object(payload["envelope"])
            ),
            records=tuple(
                CandidateRecord.from_canonical_dict(_object(item))
                for item in _array(payload["records"])
            ),
            minimum_candidate_population=int(
                payload["minimum_candidate_population"]
            ),
            reason_codes=_strings(payload["reason_codes"]),
        )


def _object(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("CandidateSet value must be an object")
    return value


def _array(value: object) -> list[object]:
    if not isinstance(value, list):
        raise ValueError("CandidateSet value must be an array")
    return value


def _strings(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) for item in value
    ):
        raise ValueError("CandidateSet value must be a string array")
    return tuple(value)


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("CandidateSet value must be numeric")
    return float(value)
