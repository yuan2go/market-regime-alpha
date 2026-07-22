"""Domain contracts for one immutable daily quant research decision.

Candidate Recommendation and Entry Assessment deliberately remain different objects.
These contracts carry research evidence only; they define no order, fill, Portfolio
Decision, broker state, or Formal OOS authority.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from enum import Enum
from hashlib import sha256
import json
import math
import re
from typing import Any, ClassVar, Mapping
from zoneinfo import ZoneInfo

from market_regime_alpha.core.identity import (
    ArtifactId,
    DatasetId,
    ModelId,
    ProviderId,
    TargetId,
    UniverseId,
)
from market_regime_alpha.core.time import AsOfTime, AvailabilityTime, DecisionTime


DAILY_RESEARCH_SNAPSHOT_SCHEMA_VERSION = "daily-research-snapshot-v1"
CANDIDATE_RECOMMENDATION_SCHEMA_VERSION = "candidate-recommendation-v1"
ENTRY_ASSESSMENT_SCHEMA_VERSION = "entry-assessment-v1"
_SHANGHAI = ZoneInfo("Asia/Shanghai")
_SHA256_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")


class DailyDataAuthority(str, Enum):
    """Allowed data classifications for V1 daily decision evidence."""

    EXPLORATORY = "EXPLORATORY"
    AUXILIARY = "AUXILIARY"
    TEST_ONLY_NOT_RESEARCH_EVIDENCE = "TEST_ONLY_NOT_RESEARCH_EVIDENCE"


class InstrumentType(str, Enum):
    """Instrument families ranked independently by V1."""

    A_SHARE_STOCK = "A_SHARE_STOCK"
    ETF = "ETF"


class DecisionDataQuality(str, Enum):
    """Decision-record data quality, not model performance."""

    COMPLETE = "COMPLETE"
    DEGRADED = "DEGRADED"
    INSUFFICIENT = "INSUFFICIENT"


class EntryState(str, Enum):
    """Entry timing decision for an already identified recommendation."""

    ENTER = "ENTER"
    WAIT_PULLBACK = "WAIT_PULLBACK"
    WAIT_CONFIRMATION = "WAIT_CONFIRMATION"
    REJECT = "REJECT"


def _text(label: str, value: str) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{label} must be a non-empty trimmed string")


def _hash(label: str, value: str) -> None:
    if not isinstance(value, str) or _SHA256_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{label} must be a sha256-prefixed lowercase digest")


def _finite(label: str, value: float | None) -> None:
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise ValueError(f"{label} must be finite when present")


def _positive_price(label: str, value: float | None) -> None:
    _finite(label, value)
    if value is not None and float(value) <= 0.0:
        raise ValueError(f"{label} must be positive when present")


def _strings(label: str, values: tuple[str, ...], *, required: bool = False, sorted_values: bool = False) -> None:
    if required and not values:
        raise ValueError(f"{label} must not be empty")
    for value in values:
        _text(label, value)
    if len(values) != len(set(values)):
        raise ValueError(f"{label} values must be unique")
    if sorted_values and tuple(sorted(values)) != values:
        raise ValueError(f"{label} values must be sorted")


def _exact_fields(payload: Mapping[str, Any], expected: set[str], label: str) -> None:
    if set(payload) != expected:
        raise ValueError(f"{label} fields mismatch")


def _datetime(value: object, label: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be an ISO-8601 string")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{label} must be an ISO-8601 string") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")
    return parsed


def _required_string(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a string")
    return value


def _required_float(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a number")
    return float(value)


def _required_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be an integer")
    return value


def _required_date(value: object, label: str) -> date:
    raw = _required_string(value, label)
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError(f"{label} must be an ISO date") from exc


def canonical_content_hash(payload: Mapping[str, Any]) -> str:
    """Hash one JSON-compatible semantic payload deterministically."""

    canonical = json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return f"sha256:{sha256(canonical.encode('utf-8')).hexdigest()}"


def _identity(prefix: str, content_hash: str) -> ArtifactId:
    return ArtifactId(f"{prefix}-{content_hash.split(':', 1)[1][:24]}")


@dataclass(frozen=True, slots=True)
class DecisionSourceArtifact:
    """One exact source item visible at the daily Decision Time."""

    artifact_id: ArtifactId
    provider_id: ProviderId
    content_hash: str
    observed_at: AsOfTime
    available_at: AvailabilityTime
    data_authority: DailyDataAuthority

    def __post_init__(self) -> None:
        _hash("source content_hash", self.content_hash)
        if not isinstance(self.data_authority, DailyDataAuthority):
            raise TypeError("data_authority must be a DailyDataAuthority")
        if self.available_at.value < self.observed_at.value:
            raise ValueError("source available_at must not precede observed_at")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": str(self.artifact_id),
            "provider_id": str(self.provider_id),
            "content_hash": self.content_hash,
            "observed_at": self.observed_at.isoformat(),
            "available_at": self.available_at.isoformat(),
            "data_authority": self.data_authority.value,
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> DecisionSourceArtifact:
        _exact_fields(
            payload,
            {"artifact_id", "provider_id", "content_hash", "observed_at", "available_at", "data_authority"},
            "Decision Source Artifact",
        )
        return cls(
            artifact_id=ArtifactId(_required_string(payload["artifact_id"], "artifact_id")),
            provider_id=ProviderId(_required_string(payload["provider_id"], "provider_id")),
            content_hash=_required_string(payload["content_hash"], "content_hash"),
            observed_at=AsOfTime(_datetime(payload["observed_at"], "observed_at")),
            available_at=AvailabilityTime(_datetime(payload["available_at"], "available_at")),
            data_authority=DailyDataAuthority(_required_string(payload["data_authority"], "data_authority")),
        )


@dataclass(frozen=True, slots=True)
class ScoreComponent:
    """One named, finite Candidate score component; never a probability."""

    name: str
    value: float

    def __post_init__(self) -> None:
        _text("score component name", self.name)
        _finite("score component value", self.value)

    def to_canonical_dict(self) -> dict[str, Any]:
        return {"name": self.name, "value": float(self.value)}

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> ScoreComponent:
        _exact_fields(payload, {"name", "value"}, "Score Component")
        return cls(
            name=_required_string(payload["name"], "score component name"),
            value=_required_float(payload["value"], "score component value"),
        )


@dataclass(frozen=True, slots=True)
class PriceZone:
    """Inclusive preferred research price zone."""

    lower: float
    upper: float

    def __post_init__(self) -> None:
        _positive_price("price zone lower", self.lower)
        _positive_price("price zone upper", self.upper)
        if self.lower > self.upper:
            raise ValueError("price zone lower must not exceed upper")

    def to_canonical_dict(self) -> dict[str, float]:
        return {"lower": float(self.lower), "upper": float(self.upper)}

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> PriceZone:
        _exact_fields(payload, {"lower", "upper"}, "Price Zone")
        return cls(
            lower=_required_float(payload["lower"], "price zone lower"),
            upper=_required_float(payload["upper"], "price zone upper"),
        )


@dataclass(frozen=True, slots=True)
class DailyResearchSnapshot:
    """Root information-state identity for one daily research decision."""

    schema_version: ClassVar[str] = DAILY_RESEARCH_SNAPSHOT_SCHEMA_VERSION

    decision_date: date
    decision_time: DecisionTime
    timezone: str
    universe_identity: UniverseId
    market_data_identity: DatasetId
    feature_registry_identity: ArtifactId
    model_identity: ModelId
    configuration_identity: ArtifactId
    market_context_identity: ArtifactId
    etf_snapshot_identity: ArtifactId
    theme_snapshot_identity: ArtifactId
    holdings_identity: ArtifactId
    source_artifacts: tuple[DecisionSourceArtifact, ...]
    data_authority: DailyDataAuthority
    created_at: AsOfTime
    snapshot_id: ArtifactId = field(init=False)
    content_hash: str = field(init=False)

    def __post_init__(self) -> None:
        if self.timezone != "Asia/Shanghai":
            raise ValueError("Daily Research Snapshot timezone must be Asia/Shanghai")
        if self.decision_time.value.utcoffset() != timedelta(hours=8):
            raise ValueError("Daily Research Snapshot Decision Time must use Asia/Shanghai offset")
        local_date = self.decision_time.value.astimezone(_SHANGHAI).date()
        if self.decision_date != local_date:
            raise ValueError("decision_date must equal the Asia/Shanghai Decision Time date")
        if self.created_at.value < self.decision_time.value:
            raise ValueError("created_at must not precede Decision Time")
        if not isinstance(self.data_authority, DailyDataAuthority):
            raise TypeError("data_authority must be a DailyDataAuthority")
        if not self.source_artifacts:
            raise ValueError("Daily Research Snapshot requires source_artifacts")
        source_ids = tuple(str(item.artifact_id) for item in self.source_artifacts)
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("source_artifacts must have unique Artifact IDs")
        if tuple(sorted(source_ids)) != source_ids:
            raise ValueError("source_artifacts must be sorted by Artifact ID")
        for source in self.source_artifacts:
            if source.data_authority is not self.data_authority:
                raise ValueError("source Artifact authority must match snapshot authority")
            if source.observed_at.value > self.decision_time.value:
                raise ValueError("source observed_at is after Decision Time")
            if source.available_at.value > self.decision_time.value:
                raise ValueError("source available_at is after Decision Time")
        digest = canonical_content_hash(self._identity_payload())
        prefix = (
            "test-only-daily-snapshot"
            if self.data_authority is DailyDataAuthority.TEST_ONLY_NOT_RESEARCH_EVIDENCE
            else "daily-snapshot"
        )
        object.__setattr__(self, "content_hash", digest)
        object.__setattr__(self, "snapshot_id", _identity(prefix, digest))

    def _identity_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "decision_date": self.decision_date.isoformat(),
            "decision_time": self.decision_time.isoformat(),
            "timezone": self.timezone,
            "universe_identity": str(self.universe_identity),
            "market_data_identity": str(self.market_data_identity),
            "feature_registry_identity": str(self.feature_registry_identity),
            "model_identity": str(self.model_identity),
            "configuration_identity": str(self.configuration_identity),
            "market_context_identity": str(self.market_context_identity),
            "etf_snapshot_identity": str(self.etf_snapshot_identity),
            "theme_snapshot_identity": str(self.theme_snapshot_identity),
            "holdings_identity": str(self.holdings_identity),
            "source_artifacts": [item.to_canonical_dict() for item in self.source_artifacts],
            "data_authority": self.data_authority.value,
        }

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            **self._identity_payload(),
            "snapshot_id": str(self.snapshot_id),
            "created_at": self.created_at.isoformat(),
            "content_hash": self.content_hash,
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> DailyResearchSnapshot:
        expected = {
            "schema_version",
            "snapshot_id",
            "decision_date",
            "decision_time",
            "timezone",
            "universe_identity",
            "market_data_identity",
            "feature_registry_identity",
            "model_identity",
            "configuration_identity",
            "market_context_identity",
            "etf_snapshot_identity",
            "theme_snapshot_identity",
            "holdings_identity",
            "source_artifacts",
            "data_authority",
            "created_at",
            "content_hash",
        }
        _exact_fields(payload, expected, "Daily Research Snapshot")
        if payload["schema_version"] != cls.schema_version:
            raise ValueError("Daily Research Snapshot Schema mismatch")
        raw_sources = payload["source_artifacts"]
        if not isinstance(raw_sources, list):
            raise ValueError("source_artifacts must be an array")
        snapshot = cls(
            decision_date=_required_date(payload["decision_date"], "decision_date"),
            decision_time=DecisionTime(_datetime(payload["decision_time"], "decision_time")),
            timezone=_required_string(payload["timezone"], "timezone"),
            universe_identity=UniverseId(_required_string(payload["universe_identity"], "universe_identity")),
            market_data_identity=DatasetId(_required_string(payload["market_data_identity"], "market_data_identity")),
            feature_registry_identity=ArtifactId(
                _required_string(payload["feature_registry_identity"], "feature_registry_identity")
            ),
            model_identity=ModelId(_required_string(payload["model_identity"], "model_identity")),
            configuration_identity=ArtifactId(
                _required_string(payload["configuration_identity"], "configuration_identity")
            ),
            market_context_identity=ArtifactId(
                _required_string(payload["market_context_identity"], "market_context_identity")
            ),
            etf_snapshot_identity=ArtifactId(
                _required_string(payload["etf_snapshot_identity"], "etf_snapshot_identity")
            ),
            theme_snapshot_identity=ArtifactId(
                _required_string(payload["theme_snapshot_identity"], "theme_snapshot_identity")
            ),
            holdings_identity=ArtifactId(_required_string(payload["holdings_identity"], "holdings_identity")),
            source_artifacts=tuple(
                DecisionSourceArtifact.from_canonical_dict(_object(item, "source Artifact"))
                for item in raw_sources
            ),
            data_authority=DailyDataAuthority(_required_string(payload["data_authority"], "data_authority")),
            created_at=AsOfTime(_datetime(payload["created_at"], "created_at")),
        )
        if str(snapshot.snapshot_id) != payload["snapshot_id"] or snapshot.content_hash != payload["content_hash"]:
            raise ValueError("Daily Research Snapshot identity mismatch")
        return snapshot


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
        _text("symbol", self.symbol)
        if isinstance(self.candidate_rank, bool) or not isinstance(self.candidate_rank, int) or self.candidate_rank <= 0:
            raise ValueError("candidate_rank must be a positive integer")
        _finite("candidate_score", self.candidate_score)
        if not self.score_components:
            raise ValueError("score_components must not be empty")
        component_names = tuple(item.name for item in self.score_components)
        if len(component_names) != len(set(component_names)):
            raise ValueError("score component names must be unique")
        if tuple(sorted(component_names)) != component_names:
            raise ValueError("score components must be sorted by name")
        if self.industry is not None:
            _text("industry", self.industry)
        _strings("themes", self.themes, sorted_values=True)
        _strings("related_etfs", self.related_etfs, sorted_values=True)
        _strings("selection_reasons", self.selection_reasons, required=True, sorted_values=True)
        _strings("risk_reasons", self.risk_reasons, sorted_values=True)
        _strings("invalidation_conditions", self.invalidation_conditions, required=True, sorted_values=True)
        _text("expected_horizon", self.expected_horizon)
        digest = canonical_content_hash(self._identity_payload())
        object.__setattr__(self, "content_hash", digest)
        object.__setattr__(self, "recommendation_id", _identity("candidate-recommendation", digest))

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
            "candidate_score": float(self.candidate_score),
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
            "schema_version",
            "recommendation_id",
            "decision_snapshot_id",
            "instrument_type",
            "symbol",
            "candidate_rank",
            "candidate_score",
            "score_components",
            "industry",
            "themes",
            "related_etfs",
            "selection_reasons",
            "risk_reasons",
            "expected_horizon",
            "target_definition",
            "invalidation_conditions",
            "data_quality",
            "model_identity",
            "data_authority",
            "content_hash",
        }
        _exact_fields(payload, expected, "Candidate Recommendation")
        if payload["schema_version"] != cls.schema_version:
            raise ValueError("Candidate Recommendation Schema mismatch")
        components = payload["score_components"]
        if not isinstance(components, list):
            raise ValueError("Candidate Recommendation score_components must be an array")
        recommendation = cls(
            decision_snapshot_id=ArtifactId(
                _required_string(payload["decision_snapshot_id"], "decision_snapshot_id")
            ),
            instrument_type=InstrumentType(_required_string(payload["instrument_type"], "instrument_type")),
            symbol=_required_string(payload["symbol"], "symbol"),
            candidate_rank=_required_int(payload["candidate_rank"], "candidate_rank"),
            candidate_score=_required_float(payload["candidate_score"], "candidate_score"),
            score_components=tuple(
                ScoreComponent.from_canonical_dict(_object(item, "Score Component"))
                for item in components
            ),
            industry=(
                _required_string(payload["industry"], "industry")
                if payload["industry"] is not None
                else None
            ),
            themes=_string_tuple(payload["themes"], "themes"),
            related_etfs=_string_tuple(payload["related_etfs"], "related_etfs"),
            selection_reasons=_string_tuple(payload["selection_reasons"], "selection_reasons"),
            risk_reasons=_string_tuple(payload["risk_reasons"], "risk_reasons"),
            expected_horizon=_required_string(payload["expected_horizon"], "expected_horizon"),
            target_definition=TargetId(
                _required_string(payload["target_definition"], "target_definition")
            ),
            invalidation_conditions=_string_tuple(payload["invalidation_conditions"], "invalidation_conditions"),
            data_quality=DecisionDataQuality(_required_string(payload["data_quality"], "data_quality")),
            model_identity=ModelId(_required_string(payload["model_identity"], "model_identity")),
            data_authority=DailyDataAuthority(_required_string(payload["data_authority"], "data_authority")),
        )
        if (
            str(recommendation.recommendation_id) != payload["recommendation_id"]
            or recommendation.content_hash != payload["content_hash"]
        ):
            raise ValueError("Candidate Recommendation identity mismatch")
        return recommendation


@dataclass(frozen=True, slots=True)
class EntryAssessment:
    """Entry timing evidence for one immutable Candidate Recommendation."""

    schema_version: ClassVar[str] = ENTRY_ASSESSMENT_SCHEMA_VERSION

    decision_snapshot_id: ArtifactId
    recommendation_id: ArtifactId
    entry_state: EntryState
    entry_score: float
    entry_reasons: tuple[str, ...]
    blocking_reasons: tuple[str, ...]
    reference_price: float | None
    preferred_price_zone: PriceZone | None
    maximum_acceptable_price: float | None
    invalidation_price: float | None
    expected_mfe: float | None
    expected_mae: float | None
    risk_reward_estimate: float | None
    uncertainty: float | None
    model_identity: ModelId
    configuration_identity: ArtifactId
    data_authority: DailyDataAuthority
    entry_assessment_id: ArtifactId = field(init=False)
    content_hash: str = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.entry_state, EntryState):
            raise TypeError("entry_state must be an EntryState")
        if not isinstance(self.data_authority, DailyDataAuthority):
            raise TypeError("data_authority must be a DailyDataAuthority")
        _finite("entry_score", self.entry_score)
        _strings("entry_reasons", self.entry_reasons, sorted_values=True)
        _strings("blocking_reasons", self.blocking_reasons, sorted_values=True)
        for label, value in (
            ("reference_price", self.reference_price),
            ("maximum_acceptable_price", self.maximum_acceptable_price),
            ("invalidation_price", self.invalidation_price),
        ):
            _positive_price(label, value)
        for label, value in (
            ("expected_mfe", self.expected_mfe),
            ("expected_mae", self.expected_mae),
            ("risk_reward_estimate", self.risk_reward_estimate),
            ("uncertainty", self.uncertainty),
        ):
            _finite(label, value)
        if self.risk_reward_estimate is not None and self.risk_reward_estimate < 0.0:
            raise ValueError("risk_reward_estimate must be non-negative")
        if self.uncertainty is not None and self.uncertainty < 0.0:
            raise ValueError("uncertainty must be non-negative")
        if self.maximum_acceptable_price is not None and self.preferred_price_zone is not None:
            if self.maximum_acceptable_price < self.preferred_price_zone.lower:
                raise ValueError("maximum_acceptable_price must not be below preferred zone")
        if self.entry_state is EntryState.ENTER:
            if self.blocking_reasons:
                raise ValueError("ENTER must not carry blocking reasons")
            if not self.entry_reasons:
                raise ValueError("ENTER requires entry reasons")
            if any(
                value is None
                for value in (
                    self.reference_price,
                    self.preferred_price_zone,
                    self.maximum_acceptable_price,
                    self.invalidation_price,
                )
            ):
                raise ValueError("ENTER requires complete price and invalidation evidence")
        if self.entry_state is EntryState.REJECT and not self.blocking_reasons:
            raise ValueError("REJECT requires blocking reasons")
        digest = canonical_content_hash(self._identity_payload())
        object.__setattr__(self, "content_hash", digest)
        object.__setattr__(self, "entry_assessment_id", _identity("entry-assessment", digest))

    def semantic_payload(self) -> dict[str, Any]:
        """Return constructor-compatible semantic fields for controlled transformations."""

        return {
            "decision_snapshot_id": self.decision_snapshot_id,
            "recommendation_id": self.recommendation_id,
            "entry_state": self.entry_state,
            "entry_score": self.entry_score,
            "entry_reasons": self.entry_reasons,
            "blocking_reasons": self.blocking_reasons,
            "reference_price": self.reference_price,
            "preferred_price_zone": self.preferred_price_zone,
            "maximum_acceptable_price": self.maximum_acceptable_price,
            "invalidation_price": self.invalidation_price,
            "expected_mfe": self.expected_mfe,
            "expected_mae": self.expected_mae,
            "risk_reward_estimate": self.risk_reward_estimate,
            "uncertainty": self.uncertainty,
            "model_identity": self.model_identity,
            "configuration_identity": self.configuration_identity,
            "data_authority": self.data_authority,
        }

    def _identity_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "decision_snapshot_id": str(self.decision_snapshot_id),
            "recommendation_id": str(self.recommendation_id),
            "entry_state": self.entry_state.value,
            "entry_score": float(self.entry_score),
            "entry_reasons": list(self.entry_reasons),
            "blocking_reasons": list(self.blocking_reasons),
            "reference_price": self.reference_price,
            "preferred_price_zone": (
                self.preferred_price_zone.to_canonical_dict()
                if self.preferred_price_zone is not None
                else None
            ),
            "maximum_acceptable_price": self.maximum_acceptable_price,
            "invalidation_price": self.invalidation_price,
            "expected_mfe": self.expected_mfe,
            "expected_mae": self.expected_mae,
            "risk_reward_estimate": self.risk_reward_estimate,
            "uncertainty": self.uncertainty,
            "model_identity": str(self.model_identity),
            "configuration_identity": str(self.configuration_identity),
            "data_authority": self.data_authority.value,
        }

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            **self._identity_payload(),
            "entry_assessment_id": str(self.entry_assessment_id),
            "content_hash": self.content_hash,
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> EntryAssessment:
        expected = {
            "schema_version",
            "entry_assessment_id",
            "decision_snapshot_id",
            "recommendation_id",
            "entry_state",
            "entry_score",
            "entry_reasons",
            "blocking_reasons",
            "reference_price",
            "preferred_price_zone",
            "maximum_acceptable_price",
            "invalidation_price",
            "expected_mfe",
            "expected_mae",
            "risk_reward_estimate",
            "uncertainty",
            "model_identity",
            "configuration_identity",
            "data_authority",
            "content_hash",
        }
        _exact_fields(payload, expected, "Entry Assessment")
        if payload["schema_version"] != cls.schema_version:
            raise ValueError("Entry Assessment Schema mismatch")
        raw_zone = payload["preferred_price_zone"]
        assessment = cls(
            decision_snapshot_id=ArtifactId(
                _required_string(payload["decision_snapshot_id"], "decision_snapshot_id")
            ),
            recommendation_id=ArtifactId(_required_string(payload["recommendation_id"], "recommendation_id")),
            entry_state=EntryState(_required_string(payload["entry_state"], "entry_state")),
            entry_score=_required_float(payload["entry_score"], "entry_score"),
            entry_reasons=_string_tuple(payload["entry_reasons"], "entry_reasons"),
            blocking_reasons=_string_tuple(payload["blocking_reasons"], "blocking_reasons"),
            reference_price=_optional_float(payload["reference_price"]),
            preferred_price_zone=(
                PriceZone.from_canonical_dict(_object(raw_zone, "Price Zone"))
                if raw_zone is not None
                else None
            ),
            maximum_acceptable_price=_optional_float(payload["maximum_acceptable_price"]),
            invalidation_price=_optional_float(payload["invalidation_price"]),
            expected_mfe=_optional_float(payload["expected_mfe"]),
            expected_mae=_optional_float(payload["expected_mae"]),
            risk_reward_estimate=_optional_float(payload["risk_reward_estimate"]),
            uncertainty=_optional_float(payload["uncertainty"]),
            model_identity=ModelId(_required_string(payload["model_identity"], "model_identity")),
            configuration_identity=ArtifactId(
                _required_string(payload["configuration_identity"], "configuration_identity")
            ),
            data_authority=DailyDataAuthority(_required_string(payload["data_authority"], "data_authority")),
        )
        if (
            str(assessment.entry_assessment_id) != payload["entry_assessment_id"]
            or assessment.content_hash != payload["content_hash"]
        ):
            raise ValueError("Entry Assessment identity mismatch")
        return assessment


def _object(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _string_tuple(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{label} must be an array of strings")
    return tuple(value)


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    return _required_float(value, "optional numeric field")
