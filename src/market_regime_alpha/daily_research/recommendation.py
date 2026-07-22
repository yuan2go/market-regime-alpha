"""Immutable Candidate Recommendation and score-lineage contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any, ClassVar, Mapping

from market_regime_alpha.core.identity import ArtifactId, ModelId, TargetId
from market_regime_alpha.daily_research._contract_support import (
    DailyDataAuthority,
    DecisionDataQuality,
    InstrumentType,
    canonical_content_hash,
    exact_fields,
    finite,
    identity,
    object_value,
    required_float,
    required_int,
    required_string,
    string_tuple,
    strings,
    text,
)


CANDIDATE_RECOMMENDATION_SCHEMA_VERSION = "candidate-recommendation-v1"


@dataclass(frozen=True, slots=True)
class ScoreComponent:
    """One identified, finite Candidate score contribution; never a probability."""

    component_identity: ArtifactId
    value: float

    def __post_init__(self) -> None:
        finite("score component value", self.value)
        object.__setattr__(self, "value", float(self.value))

    def to_canonical_dict(self) -> dict[str, Any]:
        return {"component_identity": str(self.component_identity), "value": self.value}

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> ScoreComponent:
        exact_fields(payload, {"component_identity", "value"}, "Score Component")
        return cls(
            component_identity=ArtifactId(
                required_string(payload["component_identity"], "score component identity")
            ),
            value=required_float(payload["value"], "score component value"),
        )


@dataclass(frozen=True, slots=True)
class CandidateRecommendation:
    """Structured Candidate evidence without Entry or execution action."""

    schema_version: ClassVar[str] = CANDIDATE_RECOMMENDATION_SCHEMA_VERSION

    decision_snapshot_id: ArtifactId
    instrument_type: InstrumentType
    symbol: str
    candidate_rank: int
    candidate_score: float
    score_components: tuple[ScoreComponent, ...]
    industry: str | None
    themes: tuple[str, ...]
    related_etfs: tuple[str, ...]
    selection_reasons: tuple[str, ...]
    risk_reasons: tuple[str, ...]
    expected_horizon: str
    target_definition: TargetId
    invalidation_conditions: tuple[str, ...]
    data_quality: DecisionDataQuality
    model_identity: ModelId
    data_authority: DailyDataAuthority
    recommendation_id: ArtifactId = field(init=False)
    content_hash: str = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.instrument_type, InstrumentType):
            raise TypeError("instrument_type must be an InstrumentType")
        if not isinstance(self.data_quality, DecisionDataQuality):
            raise TypeError("data_quality must be a DecisionDataQuality")
        if not isinstance(self.data_authority, DailyDataAuthority):
            raise TypeError("data_authority must be a DailyDataAuthority")
        text("symbol", self.symbol)
        if isinstance(self.candidate_rank, bool) or not isinstance(self.candidate_rank, int) or self.candidate_rank <= 0:
            raise ValueError("candidate_rank must be a positive integer")
        finite("candidate_score", self.candidate_score)
        object.__setattr__(self, "candidate_score", float(self.candidate_score))
        self._validate_components()
        if self.industry is not None:
            text("industry", self.industry)
        strings("themes", self.themes, sorted_values=True)
        strings("related_etfs", self.related_etfs, sorted_values=True)
        strings("selection_reasons", self.selection_reasons, required=True, sorted_values=True)
        strings("risk_reasons", self.risk_reasons, sorted_values=True)
        strings("invalidation_conditions", self.invalidation_conditions, required=True, sorted_values=True)
        text("expected_horizon", self.expected_horizon)
        self._validate_mapping_evidence()
        digest = canonical_content_hash(self._identity_payload())
        object.__setattr__(self, "content_hash", digest)
        object.__setattr__(self, "recommendation_id", identity("candidate-recommendation", digest))

    def _validate_components(self) -> None:
        if not self.score_components:
            raise ValueError("score_components must not be empty")
        component_ids = tuple(str(item.component_identity) for item in self.score_components)
        if len(component_ids) != len(set(component_ids)):
            raise ValueError("score component identities must be unique")
        if tuple(sorted(component_ids)) != component_ids:
            raise ValueError("score components must be sorted by identity")
        if not math.isclose(
            math.fsum(item.value for item in self.score_components),
            self.candidate_score,
            rel_tol=1e-12,
            abs_tol=1e-12,
        ):
            raise ValueError("candidate_score must equal identified component contributions")

    def _validate_mapping_evidence(self) -> None:
        missing_mapping_rules = (
            (self.industry is None, "INDUSTRY_MAPPING_UNAVAILABLE", "industry"),
            (not self.themes, "THEME_MAPPING_UNAVAILABLE", "theme"),
            (not self.related_etfs, "RELATED_ETF_MAPPING_UNAVAILABLE", "related ETF"),
        )
        for missing, required_reason, label in missing_mapping_rules:
            if missing and (
                self.data_quality is DecisionDataQuality.COMPLETE
                or required_reason not in self.risk_reasons
            ):
                raise ValueError(
                    f"missing {label} mapping requires non-COMPLETE quality and {required_reason}"
                )

    def semantic_payload(self) -> dict[str, Any]:
        """Return constructor-compatible semantic fields for controlled transformations."""

        return {
            "decision_snapshot_id": self.decision_snapshot_id,
            "instrument_type": self.instrument_type,
            "symbol": self.symbol,
            "candidate_rank": self.candidate_rank,
            "candidate_score": self.candidate_score,
            "score_components": self.score_components,
            "industry": self.industry,
            "themes": self.themes,
            "related_etfs": self.related_etfs,
            "selection_reasons": self.selection_reasons,
            "risk_reasons": self.risk_reasons,
            "expected_horizon": self.expected_horizon,
            "target_definition": self.target_definition,
            "invalidation_conditions": self.invalidation_conditions,
            "data_quality": self.data_quality,
            "model_identity": self.model_identity,
            "data_authority": self.data_authority,
        }

    def _identity_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "decision_snapshot_id": str(self.decision_snapshot_id),
            "instrument_type": self.instrument_type.value,
            "symbol": self.symbol,
            "candidate_rank": self.candidate_rank,
            "candidate_score": self.candidate_score,
            "score_components": [item.to_canonical_dict() for item in self.score_components],
            "industry": self.industry,
            "themes": list(self.themes),
            "related_etfs": list(self.related_etfs),
            "selection_reasons": list(self.selection_reasons),
            "risk_reasons": list(self.risk_reasons),
            "expected_horizon": self.expected_horizon,
            "target_definition": str(self.target_definition),
            "invalidation_conditions": list(self.invalidation_conditions),
            "data_quality": self.data_quality.value,
            "model_identity": str(self.model_identity),
            "data_authority": self.data_authority.value,
        }

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            **self._identity_payload(),
            "recommendation_id": str(self.recommendation_id),
            "content_hash": self.content_hash,
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> CandidateRecommendation:
        expected = {
            "schema_version", "recommendation_id", "decision_snapshot_id", "instrument_type",
            "symbol", "candidate_rank", "candidate_score", "score_components", "industry",
            "themes", "related_etfs", "selection_reasons", "risk_reasons", "expected_horizon",
            "target_definition", "invalidation_conditions", "data_quality", "model_identity",
            "data_authority", "content_hash",
        }
        exact_fields(payload, expected, "Candidate Recommendation")
        if payload["schema_version"] != cls.schema_version:
            raise ValueError("Candidate Recommendation Schema mismatch")
        components = payload["score_components"]
        if not isinstance(components, list):
            raise ValueError("Candidate Recommendation score_components must be an array")
        recommendation = cls(
            decision_snapshot_id=ArtifactId(required_string(payload["decision_snapshot_id"], "decision_snapshot_id")),
            instrument_type=InstrumentType(required_string(payload["instrument_type"], "instrument_type")),
            symbol=required_string(payload["symbol"], "symbol"),
            candidate_rank=required_int(payload["candidate_rank"], "candidate_rank"),
            candidate_score=required_float(payload["candidate_score"], "candidate_score"),
            score_components=tuple(
                ScoreComponent.from_canonical_dict(object_value(item, "Score Component"))
                for item in components
            ),
            industry=required_string(payload["industry"], "industry") if payload["industry"] is not None else None,
            themes=string_tuple(payload["themes"], "themes"),
            related_etfs=string_tuple(payload["related_etfs"], "related_etfs"),
            selection_reasons=string_tuple(payload["selection_reasons"], "selection_reasons"),
            risk_reasons=string_tuple(payload["risk_reasons"], "risk_reasons"),
            expected_horizon=required_string(payload["expected_horizon"], "expected_horizon"),
            target_definition=TargetId(required_string(payload["target_definition"], "target_definition")),
            invalidation_conditions=string_tuple(payload["invalidation_conditions"], "invalidation_conditions"),
            data_quality=DecisionDataQuality(required_string(payload["data_quality"], "data_quality")),
            model_identity=ModelId(required_string(payload["model_identity"], "model_identity")),
            data_authority=DailyDataAuthority(required_string(payload["data_authority"], "data_authority")),
        )
        if (
            str(recommendation.recommendation_id) != payload["recommendation_id"]
            or recommendation.content_hash != payload["content_hash"]
        ):
            raise ValueError("Candidate Recommendation identity mismatch")
        return recommendation
