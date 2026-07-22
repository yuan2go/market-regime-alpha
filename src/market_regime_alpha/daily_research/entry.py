"""Immutable Entry Assessment contract, separate from Candidate ranking."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar, Mapping

from market_regime_alpha.core.identity import ArtifactId, ModelId
from market_regime_alpha.daily_research._contract_support import (
    DailyDataAuthority,
    EntryState,
    canonical_content_hash,
    exact_fields,
    finite,
    identity,
    object_value,
    optional_float,
    positive_price,
    required_float,
    required_string,
    string_tuple,
    strings,
)


ENTRY_ASSESSMENT_SCHEMA_VERSION = "entry-assessment-v1"


@dataclass(frozen=True, slots=True)
class PriceZone:
    """Inclusive preferred research price zone."""

    lower: float
    upper: float

    def __post_init__(self) -> None:
        positive_price("price zone lower", self.lower)
        positive_price("price zone upper", self.upper)
        object.__setattr__(self, "lower", float(self.lower))
        object.__setattr__(self, "upper", float(self.upper))
        if self.lower > self.upper:
            raise ValueError("price zone lower must not exceed upper")

    def to_canonical_dict(self) -> dict[str, float]:
        return {"lower": self.lower, "upper": self.upper}

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> PriceZone:
        exact_fields(payload, {"lower", "upper"}, "Price Zone")
        return cls(
            lower=required_float(payload["lower"], "price zone lower"),
            upper=required_float(payload["upper"], "price zone upper"),
        )


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
        finite("entry_score", self.entry_score)
        object.__setattr__(self, "entry_score", float(self.entry_score))
        strings("entry_reasons", self.entry_reasons, sorted_values=True)
        strings("blocking_reasons", self.blocking_reasons, sorted_values=True)
        for label, value in (
            ("reference_price", self.reference_price),
            ("maximum_acceptable_price", self.maximum_acceptable_price),
            ("invalidation_price", self.invalidation_price),
        ):
            positive_price(label, value)
        for label, value in (
            ("expected_mfe", self.expected_mfe),
            ("expected_mae", self.expected_mae),
            ("risk_reward_estimate", self.risk_reward_estimate),
            ("uncertainty", self.uncertainty),
        ):
            finite(label, value)
        self._canonicalize_numeric_fields()
        self._validate_state()
        digest = canonical_content_hash(self._identity_payload())
        object.__setattr__(self, "content_hash", digest)
        object.__setattr__(self, "entry_assessment_id", identity("entry-assessment", digest))

    def _canonicalize_numeric_fields(self) -> None:
        for field_name in (
            "reference_price",
            "maximum_acceptable_price",
            "invalidation_price",
            "expected_mfe",
            "expected_mae",
            "risk_reward_estimate",
            "uncertainty",
        ):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(self, field_name, float(value))

    def _validate_state(self) -> None:
        if self.risk_reward_estimate is not None and self.risk_reward_estimate < 0.0:
            raise ValueError("risk_reward_estimate must be non-negative")
        if self.uncertainty is not None and self.uncertainty < 0.0:
            raise ValueError("uncertainty must be non-negative")
        if self.maximum_acceptable_price is not None and self.preferred_price_zone is not None:
            if self.maximum_acceptable_price < self.preferred_price_zone.upper:
                raise ValueError("maximum_acceptable_price must cover the preferred zone")
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
            assert self.reference_price is not None
            assert self.preferred_price_zone is not None
            assert self.maximum_acceptable_price is not None
            assert self.invalidation_price is not None
            if self.reference_price > self.maximum_acceptable_price:
                raise ValueError("ENTER reference price exceeds maximum acceptable price")
            if not self.preferred_price_zone.lower <= self.reference_price <= self.preferred_price_zone.upper:
                raise ValueError("ENTER reference price must be inside the preferred zone")
            if self.invalidation_price >= self.reference_price:
                raise ValueError("ENTER invalidation price must be below reference price")
        if self.entry_state is EntryState.REJECT and not self.blocking_reasons:
            raise ValueError("REJECT requires blocking reasons")

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
            "entry_score": self.entry_score,
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
            "schema_version", "entry_assessment_id", "decision_snapshot_id", "recommendation_id",
            "entry_state", "entry_score", "entry_reasons", "blocking_reasons", "reference_price",
            "preferred_price_zone", "maximum_acceptable_price", "invalidation_price", "expected_mfe",
            "expected_mae", "risk_reward_estimate", "uncertainty", "model_identity",
            "configuration_identity", "data_authority", "content_hash",
        }
        exact_fields(payload, expected, "Entry Assessment")
        if payload["schema_version"] != cls.schema_version:
            raise ValueError("Entry Assessment Schema mismatch")
        raw_zone = payload["preferred_price_zone"]
        assessment = cls(
            decision_snapshot_id=ArtifactId(required_string(payload["decision_snapshot_id"], "decision_snapshot_id")),
            recommendation_id=ArtifactId(required_string(payload["recommendation_id"], "recommendation_id")),
            entry_state=EntryState(required_string(payload["entry_state"], "entry_state")),
            entry_score=required_float(payload["entry_score"], "entry_score"),
            entry_reasons=string_tuple(payload["entry_reasons"], "entry_reasons"),
            blocking_reasons=string_tuple(payload["blocking_reasons"], "blocking_reasons"),
            reference_price=optional_float(payload["reference_price"]),
            preferred_price_zone=(
                PriceZone.from_canonical_dict(object_value(raw_zone, "Price Zone"))
                if raw_zone is not None
                else None
            ),
            maximum_acceptable_price=optional_float(payload["maximum_acceptable_price"]),
            invalidation_price=optional_float(payload["invalidation_price"]),
            expected_mfe=optional_float(payload["expected_mfe"]),
            expected_mae=optional_float(payload["expected_mae"]),
            risk_reward_estimate=optional_float(payload["risk_reward_estimate"]),
            uncertainty=optional_float(payload["uncertainty"]),
            model_identity=ModelId(required_string(payload["model_identity"], "model_identity")),
            configuration_identity=ArtifactId(required_string(payload["configuration_identity"], "configuration_identity")),
            data_authority=DailyDataAuthority(required_string(payload["data_authority"], "data_authority")),
        )
        if (
            str(assessment.entry_assessment_id) != payload["entry_assessment_id"]
            or assessment.content_hash != payload["content_hash"]
        ):
            raise ValueError("Entry Assessment identity mismatch")
        return assessment
