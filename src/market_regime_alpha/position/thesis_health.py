"""Artifact-derived Thesis health contracts and deterministic H5 rules."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from math import isfinite
from typing import Any, Mapping, Protocol, TypeVar

from market_regime_alpha.core.identity import (
    ArtifactId,
    OpportunityId,
    ThesisId,
)
from market_regime_alpha.decision.opportunity import DecisionEvidenceReference
from market_regime_alpha.decision.opportunity import TradingOpportunity
from market_regime_alpha.decision.thesis import (
    InvalidationKind,
    TradingThesis,
)
from market_regime_alpha.evidence.canonical import (
    canonical_hash,
    require_sha256,
    require_text,
)
from market_regime_alpha.evidence.envelope import ArtifactEnvelope
from market_regime_alpha.forecasting.contracts import (
    CalibrationStatus,
    PathForecast,
    PathForecastStatus,
)
from market_regime_alpha.daily_decision.snapshot import (
    DecisionPriceQuality,
    DecisionPriceSnapshot,
)
from market_regime_alpha.research.candidate_discovery.contracts import CandidateSet
from market_regime_alpha.research.capital_evolution.contracts import (
    CapitalEvolutionSnapshot,
    CapitalEvolutionState,
    SymbolCapitalEvolution,
    ThemeCapitalEvolution,
)
from market_regime_alpha.research.market_regime.contracts import (
    MarketRegimeSnapshot,
    MarketState,
    TradePermission,
)
from market_regime_alpha.research.theme_rotation.contracts import (
    RotationState,
    ThemeRotationItem,
    ThemeRotationSnapshot,
)
from market_regime_alpha.signals.contracts import (
    ConfirmationState,
    SignalSnapshot,
    SignalState,
)
from market_regime_alpha.position.assessment import ThesisHealth


THESIS_HEALTH_RULE_CONFIGURATION_SCHEMA = (
    "thesis-health-rule-configuration-v1"
)
THESIS_INVALIDATION_RULE_SET_SCHEMA = "thesis-invalidation-rule-set-v1"
MANUAL_INVALIDATION_EVIDENCE_SCHEMA = "manual-invalidation-evidence-v1"
THESIS_HEALTH_OBSERVATION_V2_SCHEMA = "thesis-health-observation-v2"
THESIS_HEALTH_INPUT_BUNDLE_SCHEMA = "thesis-health-private-replay-bundle-v1"

FORMAL_OOS_ALPHA_NOT_ESTABLISHED = "FORMAL_OOS_ALPHA_NOT_ESTABLISHED"
MANUAL_EVIDENCE_AUTHENTICATION_NOT_ESTABLISHED = (
    "MANUAL_EVIDENCE_AUTHENTICATION_NOT_ESTABLISHED"
)
TRADING_AUTHORITY_NOT_GRANTED = "TRADING_AUTHORITY_NOT_GRANTED"


class ThesisHealthSupportState(str, Enum):
    SUPPORTED = "SUPPORTED"
    WEAKENING = "WEAKENING"
    INVALIDATING = "INVALIDATING"
    DATA_INSUFFICIENT = "DATA_INSUFFICIENT"


class InvalidationRuleType(str, Enum):
    PRICE_BELOW = "PRICE_BELOW"
    PRICE_ABOVE = "PRICE_ABOVE"
    MARKET_STATE_IN = "MARKET_STATE_IN"
    TRADE_PERMISSION_IN = "TRADE_PERMISSION_IN"
    THEME_ROTATION_STATE_IN = "THEME_ROTATION_STATE_IN"
    CAPITAL_EVOLUTION_STATE_IN = "CAPITAL_EVOLUTION_STATE_IN"
    SIGNAL_STATE_IN = "SIGNAL_STATE_IN"
    TIME_AFTER = "TIME_AFTER"
    MANUAL_EVIDENCE_REQUIRED = "MANUAL_EVIDENCE_REQUIRED"


class CapitalRuleScope(str, Enum):
    THEME = "THEME"
    SYMBOL = "SYMBOL"
    BOTH = "BOTH"


@dataclass(frozen=True, slots=True)
class ManualInvalidationEvidence:
    schema_version: str
    evidence_id: ArtifactId
    content_hash: str
    thesis_id: ThesisId
    thesis_version: int
    condition_id: str
    actor: str
    reason: str
    recorded_at: datetime
    availability_time: datetime
    authentication_limitation: str = (
        MANUAL_EVIDENCE_AUTHENTICATION_NOT_ESTABLISHED
    )

    def __post_init__(self) -> None:
        if self.schema_version != MANUAL_INVALIDATION_EVIDENCE_SCHEMA:
            raise ValueError("unsupported Manual invalidation evidence schema")
        object.__setattr__(
            self,
            "thesis_version",
            _integer(self.thesis_version, "thesis_version"),
        )
        if self.thesis_version < 0:
            raise ValueError("Manual evidence Thesis version cannot be negative")
        _condition_id(self.condition_id)
        require_text("actor", self.actor)
        require_text("reason", self.reason)
        _aware("recorded_at", self.recorded_at)
        _aware("availability_time", self.availability_time)
        if self.availability_time < self.recorded_at:
            raise ValueError("availability_time cannot precede recorded_at")
        if (
            self.authentication_limitation
            != MANUAL_EVIDENCE_AUTHENTICATION_NOT_ESTABLISHED
        ):
            raise ValueError("Manual evidence authentication cannot be inflated")
        require_sha256("content_hash", self.content_hash)
        expected_hash = canonical_hash(self.semantic_payload())
        expected_id = ArtifactId(
            f"manual-invalidation-{expected_hash.split(':', 1)[1][:24]}"
        )
        if self.content_hash != expected_hash or self.evidence_id != expected_id:
            raise ValueError("Manual invalidation evidence identity mismatch")

    @classmethod
    def create(
        cls,
        *,
        thesis_id: ThesisId,
        thesis_version: int,
        condition_id: str,
        actor: str,
        reason: str,
        recorded_at: datetime,
        availability_time: datetime,
    ) -> ManualInvalidationEvidence:
        semantic = cls.semantic_payload_for(
            thesis_id=thesis_id,
            thesis_version=thesis_version,
            condition_id=condition_id,
            actor=actor,
            reason=reason,
            recorded_at=recorded_at,
            availability_time=availability_time,
        )
        digest = canonical_hash(semantic)
        return cls(
            schema_version=MANUAL_INVALIDATION_EVIDENCE_SCHEMA,
            evidence_id=ArtifactId(
                f"manual-invalidation-{digest.split(':', 1)[1][:24]}"
            ),
            content_hash=digest,
            thesis_id=thesis_id,
            thesis_version=thesis_version,
            condition_id=condition_id,
            actor=actor,
            reason=reason,
            recorded_at=recorded_at,
            availability_time=availability_time,
        )

    @staticmethod
    def semantic_payload_for(
        *,
        thesis_id: ThesisId,
        thesis_version: int,
        condition_id: str,
        actor: str,
        reason: str,
        recorded_at: datetime,
        availability_time: datetime,
    ) -> dict[str, Any]:
        return {
            "schema_version": MANUAL_INVALIDATION_EVIDENCE_SCHEMA,
            "thesis_id": str(thesis_id),
            "thesis_version": thesis_version,
            "condition_id": condition_id,
            "actor": actor,
            "reason": reason,
            "recorded_at": recorded_at.isoformat(),
            "availability_time": availability_time.isoformat(),
            "authentication_limitation": (
                MANUAL_EVIDENCE_AUTHENTICATION_NOT_ESTABLISHED
            ),
        }

    def semantic_payload(self) -> dict[str, Any]:
        return self.semantic_payload_for(
            thesis_id=self.thesis_id,
            thesis_version=self.thesis_version,
            condition_id=self.condition_id,
            actor=self.actor,
            reason=self.reason,
            recorded_at=self.recorded_at,
            availability_time=self.availability_time,
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            **self.semantic_payload(),
            "evidence_id": str(self.evidence_id),
            "content_hash": self.content_hash,
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> ManualInvalidationEvidence:
        _fields(
            payload,
            {
                "schema_version",
                "evidence_id",
                "content_hash",
                "thesis_id",
                "thesis_version",
                "condition_id",
                "actor",
                "reason",
                "recorded_at",
                "availability_time",
                "authentication_limitation",
            },
            "Manual invalidation evidence",
        )
        return cls(
            schema_version=str(payload["schema_version"]),
            evidence_id=ArtifactId(str(payload["evidence_id"])),
            content_hash=str(payload["content_hash"]),
            thesis_id=ThesisId(str(payload["thesis_id"])),
            thesis_version=_integer(payload["thesis_version"], "thesis_version"),
            condition_id=str(payload["condition_id"]),
            actor=str(payload["actor"]),
            reason=str(payload["reason"]),
            recorded_at=datetime.fromisoformat(str(payload["recorded_at"])),
            availability_time=datetime.fromisoformat(
                str(payload["availability_time"])
            ),
            authentication_limitation=str(payload["authentication_limitation"]),
        )


@dataclass(frozen=True, slots=True)
class ThesisHealthObservationV2:
    schema_version: str
    observation_id: ArtifactId
    content_hash: str
    thesis_id: ThesisId
    thesis_version: int
    opportunity_id: OpportunityId
    symbol: str
    primary_theme_id: str | None
    assessed_at: datetime
    actor: str
    reason: str
    market_price: float | None
    price_observation_id: ArtifactId
    price_observation_hash: str
    price_snapshot_id: ArtifactId
    price_snapshot_hash: str
    market_regime_id: ArtifactId
    market_regime_hash: str
    candidate_set_id: ArtifactId
    candidate_set_hash: str
    signal_snapshot_id: ArtifactId
    signal_snapshot_hash: str
    path_forecast_id: ArtifactId
    path_forecast_hash: str
    theme_rotation_id: ArtifactId
    theme_rotation_hash: str
    capital_evolution_id: ArtifactId
    capital_evolution_hash: str
    thesis_supporting_evidence: tuple[DecisionEvidenceReference, ...]
    configuration_id: ArtifactId
    configuration_hash: str
    rule_set_id: ArtifactId
    rule_set_hash: str
    builder_revision: str
    market_support_state: ThesisHealthSupportState
    signal_support_state: ThesisHealthSupportState
    path_support_state: ThesisHealthSupportState
    theme_support_state: ThesisHealthSupportState
    capital_support_state: ThesisHealthSupportState
    triggered_condition_ids: tuple[str, ...]
    missing_reason_codes: tuple[str, ...]
    reason_codes: tuple[str, ...]
    observed_health_state: ThesisHealth
    prior_observation_id: ArtifactId | None
    prior_observation_hash: str | None
    prior_observed_health_state: ThesisHealth | None
    prior_effective_health_state: ThesisHealth | None
    effective_health_state: ThesisHealth | None
    manual_evidence_ids: tuple[ArtifactId, ...]
    manual_evidence_hashes: tuple[str, ...]
    formal_oos_alpha: str = FORMAL_OOS_ALPHA_NOT_ESTABLISHED
    manual_evidence_authentication: str = (
        MANUAL_EVIDENCE_AUTHENTICATION_NOT_ESTABLISHED
    )
    trading_authority: str = TRADING_AUTHORITY_NOT_GRANTED

    def __post_init__(self) -> None:
        if self.schema_version != THESIS_HEALTH_OBSERVATION_V2_SCHEMA:
            raise ValueError("unsupported ThesisHealthObservationV2 schema")
        object.__setattr__(
            self,
            "thesis_version",
            _integer(self.thesis_version, "thesis_version"),
        )
        if self.thesis_version < 0:
            raise ValueError("Observation Thesis version cannot be negative")
        for label, text_value in (
            ("symbol", self.symbol),
            ("actor", self.actor),
            ("reason", self.reason),
            ("builder_revision", self.builder_revision),
        ):
            require_text(label, text_value)
        if self.primary_theme_id is not None:
            require_text("primary_theme_id", self.primary_theme_id)
        _aware("assessed_at", self.assessed_at)
        if self.market_price is not None:
            object.__setattr__(
                self,
                "market_price",
                _positive("market_price", self.market_price),
            )
        for label, hash_value in _observation_hashes(self):
            require_sha256(label, hash_value)
        evidence_ids = tuple(
            item.artifact_id for item in self.thesis_supporting_evidence
        )
        if evidence_ids != tuple(sorted(evidence_ids, key=str)) or len(
            evidence_ids
        ) != len(set(evidence_ids)):
            raise ValueError("Thesis supporting evidence must be sorted and unique")
        for label, text_values in (
            ("triggered condition", self.triggered_condition_ids),
            ("missing reason", self.missing_reason_codes),
            ("reason", self.reason_codes),
        ):
            _sorted_unique_text(label, text_values)
        if not isinstance(self.observed_health_state, ThesisHealth):
            raise TypeError("observed health state must be a ThesisHealth")
        prior_present = self.prior_observation_id is not None
        if prior_present != (self.prior_observation_hash is not None) or prior_present != (
            self.prior_observed_health_state is not None
        ):
            raise ValueError("prior observation identity/hash/state must be bound together")
        if not prior_present and self.prior_effective_health_state is not None:
            raise ValueError("prior effective health requires a prior observation")
        if self.prior_observation_hash is not None:
            require_sha256("prior_observation_hash", self.prior_observation_hash)
        for state in (
            self.prior_effective_health_state,
            self.effective_health_state,
        ):
            if state is ThesisHealth.DATA_INSUFFICIENT:
                raise ValueError("effective health cannot be DATA_INSUFFICIENT")
        expected_effective = _effective_transition(
            self.prior_effective_health_state,
            self.observed_health_state,
        )
        if self.effective_health_state is not expected_effective:
            raise ValueError("effective health state transition is invalid")
        if len(self.manual_evidence_ids) != len(self.manual_evidence_hashes):
            raise ValueError("manual evidence identities and hashes must align")
        if self.manual_evidence_ids != tuple(
            sorted(self.manual_evidence_ids, key=str)
        ) or len(self.manual_evidence_ids) != len(set(self.manual_evidence_ids)):
            raise ValueError("manual evidence identities must be sorted and unique")
        for value in self.manual_evidence_hashes:
            require_sha256("manual_evidence_hash", value)
        if (
            self.formal_oos_alpha != FORMAL_OOS_ALPHA_NOT_ESTABLISHED
            or self.manual_evidence_authentication
            != MANUAL_EVIDENCE_AUTHENTICATION_NOT_ESTABLISHED
            or self.trading_authority != TRADING_AUTHORITY_NOT_GRANTED
        ):
            raise ValueError("Thesis health Observation authority cannot be inflated")
        require_sha256("content_hash", self.content_hash)
        expected_hash = canonical_hash(self.semantic_payload())
        expected_id = ArtifactId(
            f"thesis-health-{expected_hash.split(':', 1)[1][:24]}"
        )
        if self.content_hash != expected_hash or self.observation_id != expected_id:
            raise ValueError("Thesis health Observation identity mismatch")

    @classmethod
    def create(cls, **values: Any) -> ThesisHealthObservationV2:
        semantic = cls.semantic_payload_for(**values)
        digest = canonical_hash(semantic)
        return cls(
            schema_version=THESIS_HEALTH_OBSERVATION_V2_SCHEMA,
            observation_id=ArtifactId(
                f"thesis-health-{digest.split(':', 1)[1][:24]}"
            ),
            content_hash=digest,
            **values,
        )

    @classmethod
    def create_from_semantic(
        cls, payload: Mapping[str, Any]
    ) -> ThesisHealthObservationV2:
        _fields(payload, set(_OBSERVATION_SEMANTIC_FIELDS), "Thesis health Observation semantic")
        return cls.create(**_observation_values_from_payload(payload))

    @staticmethod
    def semantic_payload_for(**values: Any) -> dict[str, Any]:
        if set(values) != set(_OBSERVATION_VALUE_FIELDS):
            raise ValueError("Thesis health Observation creation fields mismatch")
        payload: dict[str, Any] = {
            "schema_version": THESIS_HEALTH_OBSERVATION_V2_SCHEMA,
            "thesis_id": str(values["thesis_id"]),
            "thesis_version": values["thesis_version"],
            "opportunity_id": str(values["opportunity_id"]),
            "symbol": values["symbol"],
            "primary_theme_id": values["primary_theme_id"],
            "assessed_at": values["assessed_at"].isoformat(),
            "actor": values["actor"],
            "reason": values["reason"],
            "market_price": (
                float(values["market_price"])
                if values["market_price"] is not None
                else None
            ),
        }
        for name in _ARTIFACT_ID_FIELDS:
            payload[name] = str(values[name])
        for name in _ARTIFACT_HASH_FIELDS:
            payload[name] = values[name]
        payload.update(
            {
                "thesis_supporting_evidence": [
                    item.to_canonical_dict()
                    for item in values["thesis_supporting_evidence"]
                ],
                "builder_revision": values["builder_revision"],
            }
        )
        for name in _SUPPORT_STATE_FIELDS:
            payload[name] = values[name].value
        for name in (
            "triggered_condition_ids",
            "missing_reason_codes",
            "reason_codes",
        ):
            payload[name] = list(values[name])
        payload["observed_health_state"] = values["observed_health_state"].value
        payload["prior_observation_id"] = (
            str(values["prior_observation_id"])
            if values["prior_observation_id"] is not None
            else None
        )
        payload["prior_observation_hash"] = values["prior_observation_hash"]
        for name in (
            "prior_observed_health_state",
            "prior_effective_health_state",
            "effective_health_state",
        ):
            payload[name] = values[name].value if values[name] is not None else None
        payload["manual_evidence_ids"] = [
            str(item) for item in values["manual_evidence_ids"]
        ]
        payload["manual_evidence_hashes"] = list(values["manual_evidence_hashes"])
        payload.update(
            {
                "formal_oos_alpha": FORMAL_OOS_ALPHA_NOT_ESTABLISHED,
                "manual_evidence_authentication": (
                    MANUAL_EVIDENCE_AUTHENTICATION_NOT_ESTABLISHED
                ),
                "trading_authority": TRADING_AUTHORITY_NOT_GRANTED,
            }
        )
        return payload

    def semantic_payload(self) -> dict[str, Any]:
        return self.semantic_payload_for(
            **{name: getattr(self, name) for name in _OBSERVATION_VALUE_FIELDS}
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            **self.semantic_payload(),
            "observation_id": str(self.observation_id),
            "content_hash": self.content_hash,
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> ThesisHealthObservationV2:
        _fields(
            payload,
            {"observation_id", "content_hash", *_OBSERVATION_SEMANTIC_FIELDS},
            "ThesisHealthObservationV2",
        )
        return cls(
            schema_version=str(payload["schema_version"]),
            observation_id=ArtifactId(str(payload["observation_id"])),
            content_hash=str(payload["content_hash"]),
            **_observation_values_from_payload(payload),
        )


@dataclass(frozen=True, slots=True)
class PriceBelowRule:
    condition_id: str
    threshold: float

    def __post_init__(self) -> None:
        _condition_id(self.condition_id)
        object.__setattr__(self, "threshold", _positive("threshold", self.threshold))

    @property
    def rule_type(self) -> InvalidationRuleType:
        return InvalidationRuleType.PRICE_BELOW

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "rule_type": self.rule_type.value,
            "condition_id": self.condition_id,
            "threshold": self.threshold,
        }


@dataclass(frozen=True, slots=True)
class PriceAboveRule:
    condition_id: str
    threshold: float

    def __post_init__(self) -> None:
        _condition_id(self.condition_id)
        object.__setattr__(self, "threshold", _positive("threshold", self.threshold))

    @property
    def rule_type(self) -> InvalidationRuleType:
        return InvalidationRuleType.PRICE_ABOVE

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "rule_type": self.rule_type.value,
            "condition_id": self.condition_id,
            "threshold": self.threshold,
        }


@dataclass(frozen=True, slots=True)
class MarketStateInRule:
    condition_id: str
    states: tuple[MarketState, ...]

    def __post_init__(self) -> None:
        _condition_id(self.condition_id)
        _state_set("market states", self.states)

    @property
    def rule_type(self) -> InvalidationRuleType:
        return InvalidationRuleType.MARKET_STATE_IN

    def to_canonical_dict(self) -> dict[str, Any]:
        return _state_rule_payload(self.rule_type, self.condition_id, self.states)


@dataclass(frozen=True, slots=True)
class TradePermissionInRule:
    condition_id: str
    states: tuple[TradePermission, ...]

    def __post_init__(self) -> None:
        _condition_id(self.condition_id)
        _state_set("trade permission states", self.states)

    @property
    def rule_type(self) -> InvalidationRuleType:
        return InvalidationRuleType.TRADE_PERMISSION_IN

    def to_canonical_dict(self) -> dict[str, Any]:
        return _state_rule_payload(self.rule_type, self.condition_id, self.states)


@dataclass(frozen=True, slots=True)
class ThemeRotationStateInRule:
    condition_id: str
    states: tuple[RotationState, ...]

    def __post_init__(self) -> None:
        _condition_id(self.condition_id)
        _state_set("theme rotation states", self.states)

    @property
    def rule_type(self) -> InvalidationRuleType:
        return InvalidationRuleType.THEME_ROTATION_STATE_IN

    def to_canonical_dict(self) -> dict[str, Any]:
        return _state_rule_payload(self.rule_type, self.condition_id, self.states)


@dataclass(frozen=True, slots=True)
class CapitalEvolutionStateInRule:
    condition_id: str
    scope: CapitalRuleScope
    states: tuple[CapitalEvolutionState, ...]

    def __post_init__(self) -> None:
        _condition_id(self.condition_id)
        if not isinstance(self.scope, CapitalRuleScope):
            raise TypeError("capital rule scope must be a CapitalRuleScope")
        _state_set("capital evolution states", self.states)

    @property
    def rule_type(self) -> InvalidationRuleType:
        return InvalidationRuleType.CAPITAL_EVOLUTION_STATE_IN

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "rule_type": self.rule_type.value,
            "condition_id": self.condition_id,
            "scope": self.scope.value,
            "states": [item.value for item in self.states],
        }


@dataclass(frozen=True, slots=True)
class SignalStateInRule:
    condition_id: str
    states: tuple[SignalState, ...]

    def __post_init__(self) -> None:
        _condition_id(self.condition_id)
        _state_set("signal states", self.states)

    @property
    def rule_type(self) -> InvalidationRuleType:
        return InvalidationRuleType.SIGNAL_STATE_IN

    def to_canonical_dict(self) -> dict[str, Any]:
        return _state_rule_payload(self.rule_type, self.condition_id, self.states)


@dataclass(frozen=True, slots=True)
class TimeAfterRule:
    condition_id: str
    threshold: datetime

    def __post_init__(self) -> None:
        _condition_id(self.condition_id)
        _aware("time rule threshold", self.threshold)

    @property
    def rule_type(self) -> InvalidationRuleType:
        return InvalidationRuleType.TIME_AFTER

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "rule_type": self.rule_type.value,
            "condition_id": self.condition_id,
            "threshold": self.threshold.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class ManualEvidenceRequiredRule:
    condition_id: str

    def __post_init__(self) -> None:
        _condition_id(self.condition_id)

    @property
    def rule_type(self) -> InvalidationRuleType:
        return InvalidationRuleType.MANUAL_EVIDENCE_REQUIRED

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "rule_type": self.rule_type.value,
            "condition_id": self.condition_id,
        }


ThesisInvalidationRule = (
    PriceBelowRule
    | PriceAboveRule
    | MarketStateInRule
    | TradePermissionInRule
    | ThemeRotationStateInRule
    | CapitalEvolutionStateInRule
    | SignalStateInRule
    | TimeAfterRule
    | ManualEvidenceRequiredRule
)


def invalidation_rule_from_canonical_dict(
    payload: Mapping[str, Any],
) -> ThesisInvalidationRule:
    rule_type_value = payload.get("rule_type")
    try:
        rule_type = InvalidationRuleType(str(rule_type_value))
    except ValueError as exc:
        raise ValueError("unknown invalidation rule type") from exc
    condition_id = str(payload.get("condition_id"))
    if rule_type in {InvalidationRuleType.PRICE_BELOW, InvalidationRuleType.PRICE_ABOVE}:
        _fields(payload, {"rule_type", "condition_id", "threshold"}, "price rule")
        rule_cls = PriceBelowRule if rule_type is InvalidationRuleType.PRICE_BELOW else PriceAboveRule
        return rule_cls(condition_id=condition_id, threshold=_number(payload["threshold"]))
    if rule_type is InvalidationRuleType.MARKET_STATE_IN:
        _fields(payload, {"rule_type", "condition_id", "states"}, "market rule")
        return MarketStateInRule(condition_id, _states(payload["states"], MarketState))
    if rule_type is InvalidationRuleType.TRADE_PERMISSION_IN:
        _fields(payload, {"rule_type", "condition_id", "states"}, "trade permission rule")
        return TradePermissionInRule(condition_id, _states(payload["states"], TradePermission))
    if rule_type is InvalidationRuleType.THEME_ROTATION_STATE_IN:
        _fields(payload, {"rule_type", "condition_id", "states"}, "theme rule")
        return ThemeRotationStateInRule(condition_id, _states(payload["states"], RotationState))
    if rule_type is InvalidationRuleType.CAPITAL_EVOLUTION_STATE_IN:
        _fields(payload, {"rule_type", "condition_id", "scope", "states"}, "capital rule")
        return CapitalEvolutionStateInRule(
            condition_id,
            CapitalRuleScope(str(payload["scope"])),
            _states(payload["states"], CapitalEvolutionState),
        )
    if rule_type is InvalidationRuleType.SIGNAL_STATE_IN:
        _fields(payload, {"rule_type", "condition_id", "states"}, "signal rule")
        return SignalStateInRule(condition_id, _states(payload["states"], SignalState))
    if rule_type is InvalidationRuleType.TIME_AFTER:
        _fields(payload, {"rule_type", "condition_id", "threshold"}, "time rule")
        return TimeAfterRule(condition_id, datetime.fromisoformat(str(payload["threshold"])))
    _fields(payload, {"rule_type", "condition_id"}, "manual rule")
    return ManualEvidenceRequiredRule(condition_id)


_RULE_KIND = {
    InvalidationRuleType.PRICE_BELOW: InvalidationKind.PRICE,
    InvalidationRuleType.PRICE_ABOVE: InvalidationKind.PRICE,
    InvalidationRuleType.MARKET_STATE_IN: InvalidationKind.MARKET_REGIME,
    InvalidationRuleType.TRADE_PERMISSION_IN: InvalidationKind.MARKET_REGIME,
    InvalidationRuleType.THEME_ROTATION_STATE_IN: InvalidationKind.THEME,
    InvalidationRuleType.CAPITAL_EVOLUTION_STATE_IN: InvalidationKind.CAPITAL,
    InvalidationRuleType.SIGNAL_STATE_IN: InvalidationKind.SIGNAL,
    InvalidationRuleType.TIME_AFTER: InvalidationKind.TIME,
    InvalidationRuleType.MANUAL_EVIDENCE_REQUIRED: InvalidationKind.MANUAL,
}


@dataclass(frozen=True, slots=True)
class ThesisInvalidationRuleSet:
    schema_version: str
    rule_set_id: ArtifactId
    rule_set_hash: str
    thesis_id: ThesisId
    thesis_version: int
    rules: tuple[ThesisInvalidationRule, ...]

    def __post_init__(self) -> None:
        if self.schema_version != THESIS_INVALIDATION_RULE_SET_SCHEMA:
            raise ValueError("unsupported Thesis invalidation rule-set schema")
        object.__setattr__(
            self,
            "thesis_version",
            _integer(self.thesis_version, "thesis_version"),
        )
        if self.thesis_version < 0:
            raise ValueError("rule-set Thesis version cannot be negative")
        condition_ids = tuple(item.condition_id for item in self.rules)
        if condition_ids != tuple(sorted(condition_ids)):
            raise ValueError("rule-set conditions must be sorted")
        if len(condition_ids) != len(set(condition_ids)):
            raise ValueError("rule-set condition IDs must be unique")
        require_sha256("rule_set_hash", self.rule_set_hash)
        expected_hash = canonical_hash(self.semantic_payload())
        expected_id = ArtifactId(
            f"thesis-invalidation-rules-{expected_hash.split(':', 1)[1][:24]}"
        )
        if self.rule_set_hash != expected_hash or self.rule_set_id != expected_id:
            raise ValueError("Thesis invalidation rule-set identity mismatch")

    @classmethod
    def create(
        cls,
        *,
        thesis_id: ThesisId,
        thesis_version: int,
        rules: tuple[object, ...],
    ) -> ThesisInvalidationRuleSet:
        if any(not isinstance(item, _RULE_CLASSES) for item in rules):
            raise TypeError("rule set requires typed invalidation rules")
        typed_rules = tuple(
            sorted((item for item in rules if isinstance(item, _RULE_CLASSES)), key=lambda item: item.condition_id)
        )
        semantic = cls.semantic_payload_for(
            thesis_id=thesis_id,
            thesis_version=thesis_version,
            rules=typed_rules,
        )
        digest = canonical_hash(semantic)
        return cls(
            schema_version=THESIS_INVALIDATION_RULE_SET_SCHEMA,
            rule_set_id=ArtifactId(f"thesis-invalidation-rules-{digest.split(':', 1)[1][:24]}"),
            rule_set_hash=digest,
            thesis_id=thesis_id,
            thesis_version=thesis_version,
            rules=typed_rules,
        )

    @staticmethod
    def semantic_payload_for(
        *,
        thesis_id: ThesisId,
        thesis_version: int,
        rules: tuple[ThesisInvalidationRule, ...],
    ) -> dict[str, Any]:
        return {
            "schema_version": THESIS_INVALIDATION_RULE_SET_SCHEMA,
            "thesis_id": str(thesis_id),
            "thesis_version": thesis_version,
            "rules": [item.to_canonical_dict() for item in rules],
        }

    def semantic_payload(self) -> dict[str, Any]:
        return self.semantic_payload_for(
            thesis_id=self.thesis_id,
            thesis_version=self.thesis_version,
            rules=self.rules,
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            **self.semantic_payload(),
            "rule_set_id": str(self.rule_set_id),
            "rule_set_hash": self.rule_set_hash,
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> ThesisInvalidationRuleSet:
        _fields(
            payload,
            {"schema_version", "rule_set_id", "rule_set_hash", "thesis_id", "thesis_version", "rules"},
            "Thesis invalidation rule set",
        )
        rules = tuple(
            invalidation_rule_from_canonical_dict(_object(item, "rule"))
            for item in _array(payload["rules"], "rules")
        )
        return cls(
            schema_version=str(payload["schema_version"]),
            rule_set_id=ArtifactId(str(payload["rule_set_id"])),
            rule_set_hash=str(payload["rule_set_hash"]),
            thesis_id=ThesisId(str(payload["thesis_id"])),
            thesis_version=_integer(payload["thesis_version"], "thesis_version"),
            rules=rules,
        )

    def validate_for(self, thesis: TradingThesis) -> None:
        if self.thesis_id != thesis.thesis_id or self.thesis_version != thesis.version:
            raise ValueError("rule-set Thesis identity/version mismatch")
        conditions = {item.condition_id: item for item in thesis.invalidation_conditions}
        rule_ids = {item.condition_id for item in self.rules}
        if rule_ids != set(conditions):
            raise ValueError("rule-set condition mapping must exactly match Thesis conditions")
        for rule in self.rules:
            condition = conditions[rule.condition_id]
            if condition.kind is not _RULE_KIND[rule.rule_type]:
                raise ValueError("typed invalidation rule kind mismatch")
            if isinstance(rule, TimeAfterRule) and rule.threshold != thesis.time_invalidation:
                raise ValueError("TIME_AFTER must equal Thesis time_invalidation")


_RULE_CLASSES = (
    PriceBelowRule,
    PriceAboveRule,
    MarketStateInRule,
    TradePermissionInRule,
    ThemeRotationStateInRule,
    CapitalEvolutionStateInRule,
    SignalStateInRule,
    TimeAfterRule,
    ManualEvidenceRequiredRule,
)


@dataclass(frozen=True, slots=True)
class ThesisHealthRuleConfiguration:
    schema_version: str
    configuration_id: ArtifactId
    configuration_hash: str
    profile_id: str
    builder_revision: str
    maximum_market_age_seconds: float
    maximum_theme_age_seconds: float
    maximum_capital_age_seconds: float
    maximum_candidate_age_seconds: float
    maximum_signal_age_seconds: float
    maximum_path_age_seconds: float
    maximum_price_age_seconds: float
    maximum_price_research_skew_seconds: float
    maximum_prior_observation_age_seconds: float
    market_state_mapping: tuple[tuple[MarketState, ThesisHealthSupportState], ...]
    trade_permission_mapping: tuple[tuple[TradePermission, ThesisHealthSupportState], ...]
    signal_state_mapping: tuple[tuple[SignalState, ThesisHealthSupportState], ...]
    confirmation_state_mapping: tuple[tuple[ConfirmationState, ThesisHealthSupportState], ...]
    path_status_mapping: tuple[tuple[PathForecastStatus, ThesisHealthSupportState], ...]
    path_calibration_mapping: tuple[tuple[CalibrationStatus, ThesisHealthSupportState], ...]
    theme_state_mapping: tuple[tuple[RotationState, ThesisHealthSupportState], ...]
    capital_state_mapping: tuple[tuple[CapitalEvolutionState, ThesisHealthSupportState], ...]
    minimum_signal_score: float
    minimum_signal_confidence: float
    minimum_path_usable_sample_count: int
    minimum_path_expected_mfe: float
    minimum_path_expected_mae: float
    minimum_path_reward_risk_ratio: float

    def __post_init__(self) -> None:
        if self.schema_version != THESIS_HEALTH_RULE_CONFIGURATION_SCHEMA:
            raise ValueError("unsupported Thesis health configuration schema")
        require_text("profile_id", self.profile_id)
        require_text("builder_revision", self.builder_revision)
        for name in _AGE_FIELDS:
            object.__setattr__(self, name, _positive(name, getattr(self, name)))
        _validate_mapping("market_state_mapping", self.market_state_mapping, MarketState)
        _validate_mapping("trade_permission_mapping", self.trade_permission_mapping, TradePermission)
        _validate_mapping("signal_state_mapping", self.signal_state_mapping, SignalState)
        _validate_mapping("confirmation_state_mapping", self.confirmation_state_mapping, ConfirmationState)
        _validate_mapping("path_status_mapping", self.path_status_mapping, PathForecastStatus)
        _validate_mapping("path_calibration_mapping", self.path_calibration_mapping, CalibrationStatus)
        _validate_mapping("theme_state_mapping", self.theme_state_mapping, RotationState)
        _validate_mapping("capital_state_mapping", self.capital_state_mapping, CapitalEvolutionState)
        object.__setattr__(self, "minimum_signal_score", _bounded("minimum_signal_score", self.minimum_signal_score, -1.0, 1.0))
        object.__setattr__(self, "minimum_signal_confidence", _bounded("minimum_signal_confidence", self.minimum_signal_confidence, 0.0, 1.0))
        object.__setattr__(
            self,
            "minimum_path_usable_sample_count",
            _integer(
                self.minimum_path_usable_sample_count,
                "minimum_path_usable_sample_count",
            ),
        )
        if self.minimum_path_usable_sample_count <= 0:
            raise ValueError("minimum_path_usable_sample_count must be a positive integer")
        object.__setattr__(self, "minimum_path_expected_mfe", _bounded("minimum_path_expected_mfe", self.minimum_path_expected_mfe, 0.0, 1.0))
        object.__setattr__(self, "minimum_path_expected_mae", _bounded("minimum_path_expected_mae", self.minimum_path_expected_mae, -1.0, 0.0))
        object.__setattr__(self, "minimum_path_reward_risk_ratio", _positive("minimum_path_reward_risk_ratio", self.minimum_path_reward_risk_ratio))
        require_sha256("configuration_hash", self.configuration_hash)
        expected_hash = canonical_hash(self.semantic_payload())
        expected_id = ArtifactId(f"thesis-health-config-{expected_hash.split(':', 1)[1][:24]}")
        if self.configuration_hash != expected_hash or self.configuration_id != expected_id:
            raise ValueError("Thesis health configuration identity mismatch")

    @classmethod
    def create(cls, **values: Any) -> ThesisHealthRuleConfiguration:
        semantic = cls.semantic_payload_for(**values)
        digest = canonical_hash(semantic)
        return cls(
            schema_version=THESIS_HEALTH_RULE_CONFIGURATION_SCHEMA,
            configuration_id=ArtifactId(f"thesis-health-config-{digest.split(':', 1)[1][:24]}"),
            configuration_hash=digest,
            **values,
        )

    @staticmethod
    def semantic_payload_for(**values: Any) -> dict[str, Any]:
        expected = set(_CONFIG_VALUE_FIELDS)
        if set(values) != expected:
            raise ValueError("Thesis health configuration creation fields mismatch")
        payload: dict[str, Any] = {
            "schema_version": THESIS_HEALTH_RULE_CONFIGURATION_SCHEMA,
            "profile_id": values["profile_id"],
            "builder_revision": values["builder_revision"],
        }
        for name in _AGE_FIELDS:
            payload[name] = float(values[name])
        for name in _MAPPING_TYPES:
            payload[name] = _mapping_payload(values[name])
        payload.update(
            {
                "minimum_signal_score": float(values["minimum_signal_score"]),
                "minimum_signal_confidence": float(values["minimum_signal_confidence"]),
                "minimum_path_usable_sample_count": values["minimum_path_usable_sample_count"],
                "minimum_path_expected_mfe": float(values["minimum_path_expected_mfe"]),
                "minimum_path_expected_mae": float(values["minimum_path_expected_mae"]),
                "minimum_path_reward_risk_ratio": float(values["minimum_path_reward_risk_ratio"]),
            }
        )
        return payload

    def semantic_payload(self) -> dict[str, Any]:
        return self.semantic_payload_for(
            **{name: getattr(self, name) for name in _CONFIG_VALUE_FIELDS}
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            **self.semantic_payload(),
            "configuration_id": str(self.configuration_id),
            "configuration_hash": self.configuration_hash,
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> ThesisHealthRuleConfiguration:
        expected = {"schema_version", "configuration_id", "configuration_hash", *_CONFIG_VALUE_FIELDS}
        _fields(payload, expected, "Thesis health configuration")
        values: dict[str, Any] = {
            "profile_id": str(payload["profile_id"]),
            "builder_revision": str(payload["builder_revision"]),
        }
        for name in _AGE_FIELDS:
            values[name] = _number(payload[name])
        for name, enum_type in _MAPPING_TYPES.items():
            values[name] = _parse_mapping(payload[name], enum_type)
        values.update(
            {
                "minimum_signal_score": _number(payload["minimum_signal_score"]),
                "minimum_signal_confidence": _number(payload["minimum_signal_confidence"]),
                "minimum_path_usable_sample_count": _integer(payload["minimum_path_usable_sample_count"], "minimum_path_usable_sample_count"),
                "minimum_path_expected_mfe": _number(payload["minimum_path_expected_mfe"]),
                "minimum_path_expected_mae": _number(payload["minimum_path_expected_mae"]),
                "minimum_path_reward_risk_ratio": _number(payload["minimum_path_reward_risk_ratio"]),
            }
        )
        return cls(
            schema_version=str(payload["schema_version"]),
            configuration_id=ArtifactId(str(payload["configuration_id"])),
            configuration_hash=str(payload["configuration_hash"]),
            **values,
        )


@dataclass(frozen=True, slots=True)
class ThesisHealthInputBundle:
    """H5-private canonical inputs for deterministic Builder replay."""

    schema_version: str
    input_bundle_id: ArtifactId
    content_hash: str
    thesis: TradingThesis
    opportunity: TradingOpportunity
    market_regime: MarketRegimeSnapshot
    theme_rotation: ThemeRotationSnapshot
    capital_evolution: CapitalEvolutionSnapshot
    candidate_set: CandidateSet
    signal_snapshot: SignalSnapshot
    path_forecast: PathForecast
    price_snapshot: DecisionPriceSnapshot
    configuration: ThesisHealthRuleConfiguration
    rule_set: ThesisInvalidationRuleSet
    manual_evidence: tuple[ManualInvalidationEvidence, ...]
    prior_observation: ThesisHealthObservationV2 | None
    assessed_at: datetime
    actor: str
    reason: str
    replay_boundary: str = "H5_PRIVATE_REPLAY_BUNDLE"
    composite_authority: str = "NOT_COMPOSITE_OPERATIONAL_INPUT_MANIFEST"
    h6_authority: str = "NOT_H6_AUTHORITY"
    source_artifact_authority: str = "DOES_NOT_REPLACE_SOURCE_ARTIFACTS"
    data_authority: str = "DOES_NOT_INFLATE_DATA_ELIGIBILITY_OR_PIT_STATUS"
    formal_pit: str = "FORMAL_PIT_NOT_ESTABLISHED"

    def __post_init__(self) -> None:
        if self.schema_version != THESIS_HEALTH_INPUT_BUNDLE_SCHEMA:
            raise ValueError("unsupported Thesis health input-bundle schema")
        for label, value, expected_type in (
            ("thesis", self.thesis, TradingThesis),
            ("opportunity", self.opportunity, TradingOpportunity),
            ("market_regime", self.market_regime, MarketRegimeSnapshot),
            ("theme_rotation", self.theme_rotation, ThemeRotationSnapshot),
            ("capital_evolution", self.capital_evolution, CapitalEvolutionSnapshot),
            ("candidate_set", self.candidate_set, CandidateSet),
            ("signal_snapshot", self.signal_snapshot, SignalSnapshot),
            ("path_forecast", self.path_forecast, PathForecast),
            ("price_snapshot", self.price_snapshot, DecisionPriceSnapshot),
            ("configuration", self.configuration, ThesisHealthRuleConfiguration),
            ("rule_set", self.rule_set, ThesisInvalidationRuleSet),
        ):
            if not isinstance(value, expected_type):
                raise TypeError(f"{label} must be a {expected_type.__name__}")
        if self.prior_observation is not None and not isinstance(
            self.prior_observation, ThesisHealthObservationV2
        ):
            raise TypeError("prior_observation must be a ThesisHealthObservationV2")
        evidence_ids = tuple(item.evidence_id for item in self.manual_evidence)
        if evidence_ids != tuple(sorted(evidence_ids, key=str)) or len(
            evidence_ids
        ) != len(set(evidence_ids)):
            raise ValueError("manual evidence must be identity-sorted and unique")
        _aware("assessed_at", self.assessed_at)
        require_text("actor", self.actor)
        require_text("reason", self.reason)
        if (
            self.replay_boundary != "H5_PRIVATE_REPLAY_BUNDLE"
            or self.composite_authority
            != "NOT_COMPOSITE_OPERATIONAL_INPUT_MANIFEST"
            or self.h6_authority != "NOT_H6_AUTHORITY"
            or self.source_artifact_authority
            != "DOES_NOT_REPLACE_SOURCE_ARTIFACTS"
            or self.data_authority
            != "DOES_NOT_INFLATE_DATA_ELIGIBILITY_OR_PIT_STATUS"
            or self.formal_pit != "FORMAL_PIT_NOT_ESTABLISHED"
        ):
            raise ValueError("H5 replay bundle authority cannot be inflated")
        require_sha256("content_hash", self.content_hash)
        expected_hash = canonical_hash(self.semantic_payload())
        expected_id = ArtifactId(
            f"thesis-health-input-{expected_hash.split(':', 1)[1][:24]}"
        )
        if self.content_hash != expected_hash or self.input_bundle_id != expected_id:
            raise ValueError("Thesis health input-bundle identity mismatch")

    @classmethod
    def create(cls, **values: Any) -> ThesisHealthInputBundle:
        if set(values) != set(_INPUT_BUNDLE_VALUE_FIELDS):
            raise ValueError("Thesis health input-bundle creation fields mismatch")
        for name, expected_type in _INPUT_BUNDLE_TYPES.items():
            if not isinstance(values[name], expected_type):
                raise TypeError(f"{name} must be a {expected_type.__name__}")
        prior = values["prior_observation"]
        if prior is not None and not isinstance(prior, ThesisHealthObservationV2):
            raise TypeError("prior_observation must be a ThesisHealthObservationV2")
        manual = values["manual_evidence"]
        if not isinstance(manual, tuple) or any(
            not isinstance(item, ManualInvalidationEvidence) for item in manual
        ):
            raise TypeError("manual_evidence must contain ManualInvalidationEvidence")
        values["manual_evidence"] = tuple(
            sorted(manual, key=lambda item: str(item.evidence_id))
        )
        semantic = cls.semantic_payload_for(**values)
        digest = canonical_hash(semantic)
        return cls(
            schema_version=THESIS_HEALTH_INPUT_BUNDLE_SCHEMA,
            input_bundle_id=ArtifactId(
                f"thesis-health-input-{digest.split(':', 1)[1][:24]}"
            ),
            content_hash=digest,
            **values,
        )

    @staticmethod
    def semantic_payload_for(**values: Any) -> dict[str, Any]:
        if set(values) != set(_INPUT_BUNDLE_VALUE_FIELDS):
            raise ValueError("Thesis health input-bundle semantic fields mismatch")
        return {
            "schema_version": THESIS_HEALTH_INPUT_BUNDLE_SCHEMA,
            "thesis": values["thesis"].to_canonical_dict(),
            "opportunity": values["opportunity"].to_canonical_dict(),
            "market_regime": values["market_regime"].to_canonical_dict(),
            "theme_rotation": values["theme_rotation"].to_canonical_dict(),
            "capital_evolution": values["capital_evolution"].to_canonical_dict(),
            "candidate_set": values["candidate_set"].to_canonical_dict(),
            "signal_snapshot": values["signal_snapshot"].to_canonical_dict(),
            "path_forecast": values["path_forecast"].to_canonical_dict(),
            "price_snapshot": values["price_snapshot"].to_canonical_dict(),
            "configuration": values["configuration"].to_canonical_dict(),
            "rule_set": values["rule_set"].to_canonical_dict(),
            "manual_evidence": [
                item.to_canonical_dict() for item in values["manual_evidence"]
            ],
            "prior_observation": (
                values["prior_observation"].to_canonical_dict()
                if values["prior_observation"] is not None
                else None
            ),
            "assessed_at": values["assessed_at"].isoformat(),
            "actor": values["actor"],
            "reason": values["reason"],
            "replay_boundary": "H5_PRIVATE_REPLAY_BUNDLE",
            "composite_authority": "NOT_COMPOSITE_OPERATIONAL_INPUT_MANIFEST",
            "h6_authority": "NOT_H6_AUTHORITY",
            "source_artifact_authority": "DOES_NOT_REPLACE_SOURCE_ARTIFACTS",
            "data_authority": "DOES_NOT_INFLATE_DATA_ELIGIBILITY_OR_PIT_STATUS",
            "formal_pit": "FORMAL_PIT_NOT_ESTABLISHED",
        }

    def semantic_payload(self) -> dict[str, Any]:
        return self.semantic_payload_for(
            **{name: getattr(self, name) for name in _INPUT_BUNDLE_VALUE_FIELDS}
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            **self.semantic_payload(),
            "input_bundle_id": str(self.input_bundle_id),
            "content_hash": self.content_hash,
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: Mapping[str, Any]
    ) -> ThesisHealthInputBundle:
        expected = {
            "schema_version",
            "input_bundle_id",
            "content_hash",
            *_INPUT_BUNDLE_VALUE_FIELDS,
            "replay_boundary",
            "composite_authority",
            "h6_authority",
            "source_artifact_authority",
            "data_authority",
            "formal_pit",
        }
        _fields(payload, expected, "Thesis health input bundle")
        prior = payload["prior_observation"]
        bundle = cls(
            schema_version=str(payload["schema_version"]),
            input_bundle_id=ArtifactId(str(payload["input_bundle_id"])),
            content_hash=str(payload["content_hash"]),
            thesis=TradingThesis.from_canonical_dict(_object(payload["thesis"], "thesis")),
            opportunity=TradingOpportunity.from_canonical_dict(_object(payload["opportunity"], "opportunity")),
            market_regime=MarketRegimeSnapshot.from_canonical_dict(_object(payload["market_regime"], "market_regime")),
            theme_rotation=ThemeRotationSnapshot.from_canonical_dict(_object(payload["theme_rotation"], "theme_rotation")),
            capital_evolution=CapitalEvolutionSnapshot.from_canonical_dict(_object(payload["capital_evolution"], "capital_evolution")),
            candidate_set=CandidateSet.from_canonical_dict(_object(payload["candidate_set"], "candidate_set")),
            signal_snapshot=SignalSnapshot.from_canonical_dict(_object(payload["signal_snapshot"], "signal_snapshot")),
            path_forecast=PathForecast.from_canonical_dict(_object(payload["path_forecast"], "path_forecast")),
            price_snapshot=DecisionPriceSnapshot.from_canonical_dict(_object(payload["price_snapshot"], "price_snapshot")),
            configuration=ThesisHealthRuleConfiguration.from_canonical_dict(_object(payload["configuration"], "configuration")),
            rule_set=ThesisInvalidationRuleSet.from_canonical_dict(_object(payload["rule_set"], "rule_set")),
            manual_evidence=tuple(
                ManualInvalidationEvidence.from_canonical_dict(_object(item, "manual evidence"))
                for item in _array(payload["manual_evidence"], "manual_evidence")
            ),
            prior_observation=(
                ThesisHealthObservationV2.from_canonical_dict(_object(prior, "prior_observation"))
                if prior is not None
                else None
            ),
            assessed_at=datetime.fromisoformat(str(payload["assessed_at"])),
            actor=str(payload["actor"]),
            reason=str(payload["reason"]),
            replay_boundary=str(payload["replay_boundary"]),
            composite_authority=str(payload["composite_authority"]),
            h6_authority=str(payload["h6_authority"]),
            source_artifact_authority=str(payload["source_artifact_authority"]),
            data_authority=str(payload["data_authority"]),
            formal_pit=str(payload["formal_pit"]),
        )
        return bundle


@dataclass(slots=True)
class _BuilderScope:
    missing: set[str]
    candidate_theme_id: str | None = None
    theme_item: ThemeRotationItem | None = None
    theme_capital: ThemeCapitalEvolution | None = None
    symbol_capital: SymbolCapitalEvolution | None = None
    market_valid: bool = True
    theme_valid: bool = True
    capital_valid: bool = True
    candidate_valid: bool = True
    signal_valid: bool = True
    path_valid: bool = True
    price_valid: bool = True


class ThesisHealthObservationBuilder:
    """Derive V2 health solely from verified typed inputs and explicit rules."""

    def build(self, inputs: ThesisHealthInputBundle) -> ThesisHealthObservationV2:
        if not isinstance(inputs, ThesisHealthInputBundle):
            raise TypeError("Builder requires a ThesisHealthInputBundle")
        # Force exact canonical restoration before any derivation.
        bundle = ThesisHealthInputBundle.from_canonical_dict(
            inputs.to_canonical_dict()
        )
        bundle.rule_set.validate_for(bundle.thesis)
        scope = _BuilderScope(missing=set())
        self._validate_decision_scope(bundle, scope)
        research_at = self._validate_research_chain(bundle, scope)
        self._validate_current_entities(bundle, scope)
        price, price_id, price_hash = self._validate_price(
            bundle, research_at, scope
        )
        manual_by_condition = self._validate_manual_evidence(bundle, scope)
        prior = self._validate_prior(bundle, scope)

        market_support = self._market_support(bundle, scope)
        signal_support = self._signal_support(bundle, scope)
        path_support = self._path_support(bundle, scope)
        theme_support = self._theme_support(bundle, scope)
        capital_support = self._capital_support(bundle, scope)

        triggered = self._triggered_conditions(
            bundle,
            scope,
            market_price=price,
            manual_by_condition=manual_by_condition,
        )
        conditions = {
            item.condition_id: item for item in bundle.thesis.invalidation_conditions
        }
        triggered_kinds = {
            conditions[item].kind for item in triggered if item in conditions
        }
        if InvalidationKind.MARKET_REGIME in triggered_kinds:
            market_support = ThesisHealthSupportState.INVALIDATING
        if InvalidationKind.SIGNAL in triggered_kinds:
            signal_support = ThesisHealthSupportState.INVALIDATING
        if InvalidationKind.THEME in triggered_kinds:
            theme_support = ThesisHealthSupportState.INVALIDATING
        if InvalidationKind.CAPITAL in triggered_kinds:
            capital_support = ThesisHealthSupportState.INVALIDATING

        deterministic_invalidated = bool(triggered) or bundle.thesis.state.value in {
            "INVALIDATED",
            "CLOSED",
        }
        if prior is not None and prior.effective_health_state is ThesisHealth.INVALIDATED:
            deterministic_invalidated = True
        supports = (
            market_support,
            signal_support,
            path_support,
            theme_support,
            capital_support,
        )
        if deterministic_invalidated:
            observed = ThesisHealth.INVALIDATED
        elif scope.missing or ThesisHealthSupportState.DATA_INSUFFICIENT in supports:
            observed = ThesisHealth.DATA_INSUFFICIENT
        elif ThesisHealthSupportState.WEAKENING in supports:
            observed = ThesisHealth.WEAKENING
        else:
            observed = ThesisHealth.HEALTHY
        prior_effective = prior.effective_health_state if prior is not None else None
        effective = _effective_transition(prior_effective, observed)
        reasons = self._observation_reasons(
            bundle,
            observed,
            effective,
            triggered,
            prior,
        )
        manual_pairs = tuple(
            sorted(
                (
                    (item.evidence_id, item.content_hash)
                    for item in bundle.manual_evidence
                ),
                key=lambda item: str(item[0]),
            )
        )
        assert price_id is not None and price_hash is not None
        return ThesisHealthObservationV2.create(
            thesis_id=bundle.thesis.thesis_id,
            thesis_version=bundle.thesis.version,
            opportunity_id=bundle.thesis.opportunity_id,
            symbol=bundle.thesis.symbol,
            primary_theme_id=scope.candidate_theme_id,
            assessed_at=bundle.assessed_at,
            actor=bundle.actor,
            reason=bundle.reason,
            market_price=price,
            price_observation_id=price_id,
            price_observation_hash=price_hash,
            price_snapshot_id=bundle.price_snapshot.decision_snapshot_id,
            price_snapshot_hash=bundle.price_snapshot.content_hash,
            market_regime_id=bundle.market_regime.envelope.artifact_id,
            market_regime_hash=bundle.market_regime.envelope.content_hash,
            candidate_set_id=bundle.candidate_set.envelope.artifact_id,
            candidate_set_hash=bundle.candidate_set.envelope.content_hash,
            signal_snapshot_id=bundle.signal_snapshot.envelope.artifact_id,
            signal_snapshot_hash=bundle.signal_snapshot.envelope.content_hash,
            path_forecast_id=bundle.path_forecast.envelope.artifact_id,
            path_forecast_hash=bundle.path_forecast.envelope.content_hash,
            theme_rotation_id=bundle.theme_rotation.envelope.artifact_id,
            theme_rotation_hash=bundle.theme_rotation.envelope.content_hash,
            capital_evolution_id=bundle.capital_evolution.envelope.artifact_id,
            capital_evolution_hash=bundle.capital_evolution.envelope.content_hash,
            thesis_supporting_evidence=bundle.thesis.supporting_evidence,
            configuration_id=bundle.configuration.configuration_id,
            configuration_hash=bundle.configuration.configuration_hash,
            rule_set_id=bundle.rule_set.rule_set_id,
            rule_set_hash=bundle.rule_set.rule_set_hash,
            builder_revision=bundle.configuration.builder_revision,
            market_support_state=market_support,
            signal_support_state=signal_support,
            path_support_state=path_support,
            theme_support_state=theme_support,
            capital_support_state=capital_support,
            triggered_condition_ids=tuple(sorted(triggered)),
            missing_reason_codes=tuple(sorted(scope.missing)),
            reason_codes=tuple(sorted(reasons)),
            observed_health_state=observed,
            prior_observation_id=(prior.observation_id if prior is not None else None),
            prior_observation_hash=(prior.content_hash if prior is not None else None),
            prior_observed_health_state=(
                prior.observed_health_state if prior is not None else None
            ),
            prior_effective_health_state=prior_effective,
            effective_health_state=effective,
            manual_evidence_ids=tuple(item[0] for item in manual_pairs),
            manual_evidence_hashes=tuple(item[1] for item in manual_pairs),
        )

    def _validate_decision_scope(
        self, bundle: ThesisHealthInputBundle, scope: _BuilderScope
    ) -> None:
        thesis = bundle.thesis
        opportunity = bundle.opportunity
        if (
            thesis.opportunity_id != opportunity.opportunity_id
            or thesis.symbol != opportunity.symbol
            or thesis.source_opportunity_version >= opportunity.version
        ):
            scope.missing.add("THESIS_OPPORTUNITY_SCOPE_MISMATCH")
        required = {
            (opportunity.candidate_set.artifact_id, opportunity.candidate_set.content_hash),
            (opportunity.signal_snapshot.artifact_id, opportunity.signal_snapshot.content_hash),
            (opportunity.path_forecast.artifact_id, opportunity.path_forecast.content_hash),
        }
        provided = {
            (item.artifact_id, item.content_hash)
            for item in thesis.supporting_evidence
        }
        if not required.issubset(provided):
            scope.missing.add("THESIS_CREATION_EVIDENCE_INCOMPLETE")

    def _validate_research_chain(
        self, bundle: ThesisHealthInputBundle, scope: _BuilderScope
    ) -> datetime:
        components = (
            ("MARKET", bundle.market_regime.envelope, bundle.configuration.maximum_market_age_seconds),
            ("THEME", bundle.theme_rotation.envelope, bundle.configuration.maximum_theme_age_seconds),
            ("CAPITAL", bundle.capital_evolution.envelope, bundle.configuration.maximum_capital_age_seconds),
            ("CANDIDATE", bundle.candidate_set.envelope, bundle.configuration.maximum_candidate_age_seconds),
            ("SIGNAL", bundle.signal_snapshot.envelope, bundle.configuration.maximum_signal_age_seconds),
            ("PATH", bundle.path_forecast.envelope, bundle.configuration.maximum_path_age_seconds),
        )
        research_at = bundle.candidate_set.envelope.decision_time.value
        decision_times = {item[1].decision_time for item in components}
        if len(decision_times) != 1:
            scope.missing.add("CURRENT_RESEARCH_DECISION_TIME_MISMATCH")
            for label in ("market", "theme", "capital", "candidate", "signal", "path"):
                setattr(scope, f"{label}_valid", False)
        source_lineage = {
            (item[1].source_manifest_id, item[1].source_manifest_hash)
            for item in components
        }
        if len(source_lineage) != 1:
            scope.missing.add("CURRENT_RESEARCH_SOURCE_MANIFEST_MISMATCH")
            for label in ("market", "theme", "capital", "candidate", "signal", "path"):
                setattr(scope, f"{label}_valid", False)
        if any(
            envelope.decision_time.value < bundle.opportunity.decision_time.value
            for _, envelope, _ in components
        ):
            scope.missing.add("CURRENT_RESEARCH_PRECEDES_THESIS_CREATION_EVIDENCE")
        for label, envelope, maximum_age in components:
            if envelope.decision_time.value > bundle.assessed_at or envelope.created_at > bundle.assessed_at:
                scope.missing.add(f"CURRENT_{label}_ARTIFACT_FROM_FUTURE")
                setattr(scope, f"{label.lower()}_valid", False)
            elif (bundle.assessed_at - envelope.decision_time.value).total_seconds() > maximum_age:
                scope.missing.add(f"CURRENT_{label}_ARTIFACT_STALE")
                setattr(scope, f"{label.lower()}_valid", False)
        if not _contains_reference(
            bundle.capital_evolution.envelope,
            bundle.theme_rotation.envelope.artifact_id,
            bundle.theme_rotation.envelope.content_hash,
        ):
            scope.missing.add("CURRENT_CAPITAL_THEME_LINEAGE_MISMATCH")
            scope.capital_valid = False
        candidate_inputs = (
            bundle.market_regime.envelope,
            bundle.theme_rotation.envelope,
            bundle.capital_evolution.envelope,
        )
        if any(
            not _contains_reference(
                bundle.candidate_set.envelope,
                item.artifact_id,
                item.content_hash,
            )
            for item in candidate_inputs
        ):
            scope.missing.add("CURRENT_CANDIDATE_RESEARCH_LINEAGE_MISMATCH")
            scope.candidate_valid = False
        if not _contains_reference(
            bundle.signal_snapshot.envelope,
            bundle.candidate_set.envelope.artifact_id,
            bundle.candidate_set.envelope.content_hash,
        ):
            scope.missing.add("CURRENT_SIGNAL_CANDIDATE_LINEAGE_MISMATCH")
            scope.signal_valid = False
        if not _contains_reference(
            bundle.path_forecast.envelope,
            bundle.signal_snapshot.envelope.artifact_id,
            bundle.signal_snapshot.envelope.content_hash,
        ):
            scope.missing.add("CURRENT_PATH_SIGNAL_LINEAGE_MISMATCH")
            scope.path_valid = False
        return research_at

    def _validate_current_entities(
        self, bundle: ThesisHealthInputBundle, scope: _BuilderScope
    ) -> None:
        records = tuple(
            item for item in bundle.candidate_set.records if item.symbol == bundle.thesis.symbol
        )
        if len(records) != 1 or records[0].primary_theme_id is None:
            scope.missing.add("CURRENT_CANDIDATE_PRIMARY_THEME_NOT_ESTABLISHED")
            scope.candidate_valid = False
            return
        scope.candidate_theme_id = records[0].primary_theme_id
        themes = tuple(
            item for item in bundle.theme_rotation.themes if item.theme_id == scope.candidate_theme_id
        )
        if len(themes) != 1:
            scope.missing.add("CURRENT_THEME_ROTATION_SCOPE_MISMATCH")
            scope.theme_valid = False
        else:
            scope.theme_item = themes[0]
        theme_capital = tuple(
            item for item in bundle.capital_evolution.themes if item.theme_id == scope.candidate_theme_id
        )
        symbol_capital = tuple(
            item for item in bundle.capital_evolution.symbols if item.symbol == bundle.thesis.symbol
        )
        if len(theme_capital) != 1:
            scope.missing.add("CURRENT_CAPITAL_THEME_MISSING")
            scope.capital_valid = False
        else:
            scope.theme_capital = theme_capital[0]
        if len(symbol_capital) != 1:
            scope.missing.add("CURRENT_CAPITAL_SYMBOL_MISSING")
            scope.capital_valid = False
        elif symbol_capital[0].theme_id != scope.candidate_theme_id:
            scope.missing.add("CURRENT_CAPITAL_SYMBOL_THEME_MISMATCH")
            scope.capital_valid = False
        else:
            scope.symbol_capital = symbol_capital[0]
        if bundle.signal_snapshot.symbol != bundle.thesis.symbol:
            scope.missing.add("CURRENT_SIGNAL_SYMBOL_MISMATCH")
            scope.signal_valid = False
        if bundle.path_forecast.symbol != bundle.thesis.symbol:
            scope.missing.add("CURRENT_PATH_SYMBOL_MISMATCH")
            scope.path_valid = False

    def _validate_price(
        self,
        bundle: ThesisHealthInputBundle,
        research_at: datetime,
        scope: _BuilderScope,
    ) -> tuple[float | None, ArtifactId | None, str | None]:
        snapshot = bundle.price_snapshot
        if snapshot.source_manifest_id != bundle.candidate_set.envelope.source_manifest_id:
            scope.missing.add("PRICE_SOURCE_MANIFEST_MISMATCH")
            scope.price_valid = False
        skew = abs((snapshot.decision_time.value - research_at).total_seconds())
        if skew > bundle.configuration.maximum_price_research_skew_seconds:
            scope.missing.add("PRICE_RESEARCH_TIME_SKEW_EXCEEDED")
            scope.price_valid = False
        item = snapshot.observation_for(bundle.thesis.symbol)
        if item is None:
            scope.missing.add("PRICE_OBSERVATION_MISSING")
            scope.price_valid = False
            missing_hash = canonical_hash(
                {
                    "schema_version": "thesis-price-observation-missing-v1",
                    "price_snapshot_id": str(snapshot.decision_snapshot_id),
                    "price_snapshot_hash": snapshot.content_hash,
                    "symbol": bundle.thesis.symbol,
                }
            )
            return (
                None,
                ArtifactId(
                    f"thesis-price-{missing_hash.split(':', 1)[1][:24]}"
                ),
                missing_hash,
            )
        item_hash = canonical_hash(item.to_canonical_dict())
        item_id = ArtifactId(f"thesis-price-{item_hash.split(':', 1)[1][:24]}")
        if (
            item.quality is not DecisionPriceQuality.AVAILABLE
            or item.price is None
            or item.event_time is None
            or item.available_time is None
        ):
            scope.missing.update(item.reason_codes or ("PRICE_OBSERVATION_INSUFFICIENT",))
            scope.price_valid = False
            return item.price, item_id, item_hash
        available = item.available_time.value
        if item.event_time > bundle.assessed_at or available > bundle.assessed_at:
            scope.missing.add("PRICE_OBSERVATION_FROM_FUTURE")
            scope.price_valid = False
        elif (
            bundle.assessed_at - available
        ).total_seconds() > bundle.configuration.maximum_price_age_seconds:
            scope.missing.add("PRICE_OBSERVATION_STALE")
            scope.price_valid = False
        return item.price, item_id, item_hash

    def _validate_manual_evidence(
        self, bundle: ThesisHealthInputBundle, scope: _BuilderScope
    ) -> dict[str, ManualInvalidationEvidence]:
        grouped: dict[str, list[ManualInvalidationEvidence]] = {}
        manual_conditions = {
            item.condition_id
            for item in bundle.rule_set.rules
            if isinstance(item, ManualEvidenceRequiredRule)
        }
        for item in bundle.manual_evidence:
            grouped.setdefault(item.condition_id, []).append(item)
            if (
                item.thesis_id != bundle.thesis.thesis_id
                or item.thesis_version != bundle.thesis.version
                or item.condition_id not in manual_conditions
            ):
                scope.missing.add("MANUAL_INVALIDATION_EVIDENCE_SCOPE_MISMATCH")
            if item.recorded_at > bundle.assessed_at or item.availability_time > bundle.assessed_at:
                scope.missing.add("MANUAL_INVALIDATION_EVIDENCE_FROM_FUTURE")
        if any(len(items) != 1 for items in grouped.values()):
            scope.missing.add("MANUAL_INVALIDATION_EVIDENCE_CONFLICT")
        return {
            condition_id: items[0]
            for condition_id, items in grouped.items()
            if len(items) == 1
            and items[0].thesis_id == bundle.thesis.thesis_id
            and items[0].thesis_version == bundle.thesis.version
            and condition_id in manual_conditions
            and items[0].recorded_at <= bundle.assessed_at
            and items[0].availability_time <= bundle.assessed_at
        }

    def _validate_prior(
        self, bundle: ThesisHealthInputBundle, scope: _BuilderScope
    ) -> ThesisHealthObservationV2 | None:
        prior = bundle.prior_observation
        if prior is None:
            return None
        if prior.thesis_id != bundle.thesis.thesis_id:
            raise ValueError("prior Observation belongs to a different Thesis")
        if prior.thesis_version > bundle.thesis.version:
            raise ValueError("prior Observation has a future Thesis version")
        if prior.assessed_at >= bundle.assessed_at:
            raise ValueError("prior Observation must precede current assessed_at")
        if (
            bundle.assessed_at - prior.assessed_at
        ).total_seconds() > bundle.configuration.maximum_prior_observation_age_seconds:
            scope.missing.add("PRIOR_THESIS_HEALTH_OBSERVATION_STALE")
        return prior

    def _market_support(
        self, bundle: ThesisHealthInputBundle, scope: _BuilderScope
    ) -> ThesisHealthSupportState:
        if not scope.market_valid:
            return ThesisHealthSupportState.DATA_INSUFFICIENT
        return _worst_support(
            _mapped(bundle.configuration.market_state_mapping, bundle.market_regime.market_state),
            _mapped(bundle.configuration.trade_permission_mapping, bundle.market_regime.trade_permission),
        )

    def _signal_support(
        self, bundle: ThesisHealthInputBundle, scope: _BuilderScope
    ) -> ThesisHealthSupportState:
        signal = bundle.signal_snapshot
        if not scope.signal_valid:
            return ThesisHealthSupportState.DATA_INSUFFICIENT
        states = [
            _mapped(bundle.configuration.signal_state_mapping, signal.signal_state),
            *(
                _mapped(bundle.configuration.confirmation_state_mapping, value)
                for value in (
                    signal.price_action_state,
                    signal.volume_confirmation_state,
                    signal.trend_confirmation_state,
                    signal.vwap_state,
                    signal.overheat_state,
                )
            ),
        ]
        if signal.signal_score is None:
            states.append(ThesisHealthSupportState.DATA_INSUFFICIENT)
        elif signal.signal_score < bundle.configuration.minimum_signal_score:
            states.append(ThesisHealthSupportState.WEAKENING)
        if signal.confidence < bundle.configuration.minimum_signal_confidence:
            states.append(ThesisHealthSupportState.WEAKENING)
        return _worst_support(*states)

    def _path_support(
        self, bundle: ThesisHealthInputBundle, scope: _BuilderScope
    ) -> ThesisHealthSupportState:
        path = bundle.path_forecast
        if not scope.path_valid:
            return ThesisHealthSupportState.DATA_INSUFFICIENT
        states = [
            _mapped(bundle.configuration.path_status_mapping, path.forecast_status),
            _mapped(bundle.configuration.path_calibration_mapping, path.calibration_status),
        ]
        if path.usable_sample_count < bundle.configuration.minimum_path_usable_sample_count:
            states.append(ThesisHealthSupportState.WEAKENING)
        if path.expected_mfe is None or path.expected_mae is None:
            states.append(ThesisHealthSupportState.DATA_INSUFFICIENT)
        else:
            if path.expected_mfe < bundle.configuration.minimum_path_expected_mfe:
                states.append(ThesisHealthSupportState.WEAKENING)
            if path.expected_mae < bundle.configuration.minimum_path_expected_mae:
                states.append(ThesisHealthSupportState.WEAKENING)
        barrier_ratio = path.upper_barrier_return / abs(path.lower_barrier_return)
        if barrier_ratio < bundle.configuration.minimum_path_reward_risk_ratio:
            states.append(ThesisHealthSupportState.WEAKENING)
        return _worst_support(*states)

    def _theme_support(
        self, bundle: ThesisHealthInputBundle, scope: _BuilderScope
    ) -> ThesisHealthSupportState:
        if not scope.theme_valid or scope.theme_item is None:
            return ThesisHealthSupportState.DATA_INSUFFICIENT
        return _mapped(
            bundle.configuration.theme_state_mapping,
            scope.theme_item.rotation_state,
        )

    def _capital_support(
        self, bundle: ThesisHealthInputBundle, scope: _BuilderScope
    ) -> ThesisHealthSupportState:
        if (
            not scope.capital_valid
            or scope.theme_capital is None
            or scope.symbol_capital is None
        ):
            return ThesisHealthSupportState.DATA_INSUFFICIENT
        return _worst_support(
            _mapped(
                bundle.configuration.capital_state_mapping,
                scope.theme_capital.capital_evolution_state,
            ),
            _mapped(
                bundle.configuration.capital_state_mapping,
                scope.symbol_capital.capital_evolution_state,
            ),
        )

    def _triggered_conditions(
        self,
        bundle: ThesisHealthInputBundle,
        scope: _BuilderScope,
        *,
        market_price: float | None,
        manual_by_condition: Mapping[str, ManualInvalidationEvidence],
    ) -> set[str]:
        triggered: set[str] = set()
        for rule in bundle.rule_set.rules:
            if isinstance(rule, PriceBelowRule):
                if scope.price_valid and market_price is not None and market_price < rule.threshold:
                    triggered.add(rule.condition_id)
            elif isinstance(rule, PriceAboveRule):
                if scope.price_valid and market_price is not None and market_price > rule.threshold:
                    triggered.add(rule.condition_id)
            elif isinstance(rule, MarketStateInRule):
                if scope.market_valid and bundle.market_regime.market_state in rule.states:
                    triggered.add(rule.condition_id)
            elif isinstance(rule, TradePermissionInRule):
                if scope.market_valid and bundle.market_regime.trade_permission in rule.states:
                    triggered.add(rule.condition_id)
            elif isinstance(rule, ThemeRotationStateInRule):
                if scope.theme_valid and scope.theme_item is not None and scope.theme_item.rotation_state in rule.states:
                    triggered.add(rule.condition_id)
            elif isinstance(rule, CapitalEvolutionStateInRule):
                if self._capital_rule_triggered(rule, scope):
                    triggered.add(rule.condition_id)
            elif isinstance(rule, SignalStateInRule):
                if scope.signal_valid and bundle.signal_snapshot.signal_state in rule.states:
                    triggered.add(rule.condition_id)
            elif isinstance(rule, TimeAfterRule):
                if bundle.assessed_at >= rule.threshold:
                    triggered.add(rule.condition_id)
            elif isinstance(rule, ManualEvidenceRequiredRule):
                if rule.condition_id in manual_by_condition:
                    triggered.add(rule.condition_id)
        return triggered

    @staticmethod
    def _capital_rule_triggered(
        rule: CapitalEvolutionStateInRule, scope: _BuilderScope
    ) -> bool:
        if (
            not scope.capital_valid
            or scope.theme_capital is None
            or scope.symbol_capital is None
        ):
            return False
        theme_match = scope.theme_capital.capital_evolution_state in rule.states
        symbol_match = scope.symbol_capital.capital_evolution_state in rule.states
        if rule.scope is CapitalRuleScope.THEME:
            return theme_match
        if rule.scope is CapitalRuleScope.SYMBOL:
            return symbol_match
        return theme_match and symbol_match

    @staticmethod
    def _observation_reasons(
        bundle: ThesisHealthInputBundle,
        observed: ThesisHealth,
        effective: ThesisHealth | None,
        triggered: set[str],
        prior: ThesisHealthObservationV2 | None,
    ) -> set[str]:
        reasons = {
            "THESIS_HEALTH_DERIVED_FROM_VERIFIED_ARTIFACTS",
            "FORMAL_OOS_ALPHA_NOT_ESTABLISHED",
            "MANUAL_EVIDENCE_AUTHENTICATION_NOT_ESTABLISHED",
            f"OBSERVED_THESIS_HEALTH_{observed.value}",
        }
        conditions = {
            item.condition_id: item for item in bundle.thesis.invalidation_conditions
        }
        reasons.update(conditions[item].reason_code for item in triggered)
        if prior is not None and prior.effective_health_state is ThesisHealth.WEAKENING and observed is ThesisHealth.HEALTHY:
            reasons.add("THESIS_HEALTH_RECOVERY_NOT_AUTHORIZED")
        if prior is not None and prior.effective_health_state is ThesisHealth.INVALIDATED:
            reasons.add("PRIOR_THESIS_HEALTH_INVALIDATED_TERMINAL")
        if effective is None:
            reasons.add("EFFECTIVE_THESIS_HEALTH_NOT_ESTABLISHED")
        else:
            reasons.add(f"EFFECTIVE_THESIS_HEALTH_{effective.value}")
        return reasons


class ThesisHealthRepository(Protocol):
    """Persistence boundary for immutable, replayable H5 observations."""

    def save_observation(
        self,
        observation: ThesisHealthObservationV2,
        *,
        input_bundle: ThesisHealthInputBundle,
        idempotency_key: str,
        command_hash: str,
    ) -> ThesisHealthObservationV2: ...

    def resolve_command(
        self, *, idempotency_key: str, command_hash: str
    ) -> ThesisHealthObservationV2 | None: ...

    def get_observation(
        self, observation_id: ArtifactId
    ) -> ThesisHealthObservationV2: ...

    def get_latest_observation(
        self, thesis_id: ThesisId
    ) -> ThesisHealthObservationV2 | None: ...


_AGE_FIELDS = (
    "maximum_market_age_seconds",
    "maximum_theme_age_seconds",
    "maximum_capital_age_seconds",
    "maximum_candidate_age_seconds",
    "maximum_signal_age_seconds",
    "maximum_path_age_seconds",
    "maximum_price_age_seconds",
    "maximum_price_research_skew_seconds",
    "maximum_prior_observation_age_seconds",
)

_MAPPING_TYPES: dict[str, type[Enum]] = {
    "market_state_mapping": MarketState,
    "trade_permission_mapping": TradePermission,
    "signal_state_mapping": SignalState,
    "confirmation_state_mapping": ConfirmationState,
    "path_status_mapping": PathForecastStatus,
    "path_calibration_mapping": CalibrationStatus,
    "theme_state_mapping": RotationState,
    "capital_state_mapping": CapitalEvolutionState,
}

_CONFIG_VALUE_FIELDS = (
    "profile_id",
    "builder_revision",
    *_AGE_FIELDS,
    *_MAPPING_TYPES,
    "minimum_signal_score",
    "minimum_signal_confidence",
    "minimum_path_usable_sample_count",
    "minimum_path_expected_mfe",
    "minimum_path_expected_mae",
    "minimum_path_reward_risk_ratio",
)

_ARTIFACT_ID_FIELDS = (
    "price_observation_id",
    "price_snapshot_id",
    "market_regime_id",
    "candidate_set_id",
    "signal_snapshot_id",
    "path_forecast_id",
    "theme_rotation_id",
    "capital_evolution_id",
    "configuration_id",
    "rule_set_id",
)

_ARTIFACT_HASH_FIELDS = (
    "price_observation_hash",
    "price_snapshot_hash",
    "market_regime_hash",
    "candidate_set_hash",
    "signal_snapshot_hash",
    "path_forecast_hash",
    "theme_rotation_hash",
    "capital_evolution_hash",
    "configuration_hash",
    "rule_set_hash",
)

_SUPPORT_STATE_FIELDS = (
    "market_support_state",
    "signal_support_state",
    "path_support_state",
    "theme_support_state",
    "capital_support_state",
)

_OBSERVATION_VALUE_FIELDS = (
    "thesis_id",
    "thesis_version",
    "opportunity_id",
    "symbol",
    "primary_theme_id",
    "assessed_at",
    "actor",
    "reason",
    "market_price",
    *_ARTIFACT_ID_FIELDS,
    *_ARTIFACT_HASH_FIELDS,
    "thesis_supporting_evidence",
    "builder_revision",
    *_SUPPORT_STATE_FIELDS,
    "triggered_condition_ids",
    "missing_reason_codes",
    "reason_codes",
    "observed_health_state",
    "prior_observation_id",
    "prior_observation_hash",
    "prior_observed_health_state",
    "prior_effective_health_state",
    "effective_health_state",
    "manual_evidence_ids",
    "manual_evidence_hashes",
)

_OBSERVATION_SEMANTIC_FIELDS = (
    "schema_version",
    *_OBSERVATION_VALUE_FIELDS,
    "formal_oos_alpha",
    "manual_evidence_authentication",
    "trading_authority",
)

_INPUT_BUNDLE_VALUE_FIELDS = (
    "thesis",
    "opportunity",
    "market_regime",
    "theme_rotation",
    "capital_evolution",
    "candidate_set",
    "signal_snapshot",
    "path_forecast",
    "price_snapshot",
    "configuration",
    "rule_set",
    "manual_evidence",
    "prior_observation",
    "assessed_at",
    "actor",
    "reason",
)

_INPUT_BUNDLE_TYPES: dict[str, type[object]] = {
    "thesis": TradingThesis,
    "opportunity": TradingOpportunity,
    "market_regime": MarketRegimeSnapshot,
    "theme_rotation": ThemeRotationSnapshot,
    "capital_evolution": CapitalEvolutionSnapshot,
    "candidate_set": CandidateSet,
    "signal_snapshot": SignalSnapshot,
    "path_forecast": PathForecast,
    "price_snapshot": DecisionPriceSnapshot,
    "configuration": ThesisHealthRuleConfiguration,
    "rule_set": ThesisInvalidationRuleSet,
}


def _condition_id(value: str) -> None:
    require_text("condition_id", value)


def _observation_hashes(
    observation: ThesisHealthObservationV2,
) -> tuple[tuple[str, str], ...]:
    return tuple(
        (name, str(getattr(observation, name))) for name in _ARTIFACT_HASH_FIELDS
    )


def _contains_reference(
    envelope: ArtifactEnvelope,
    artifact_id: ArtifactId,
    content_hash: str,
) -> bool:
    return (artifact_id, content_hash) in zip(
        envelope.input_artifact_ids,
        envelope.input_content_hashes,
        strict=True,
    )


def _mapped(
    mapping: tuple[tuple[E, ThesisHealthSupportState], ...],
    value: E,
) -> ThesisHealthSupportState:
    for source, support in mapping:
        if source == value:
            return support
    raise ValueError(f"configuration does not map {value!r}")


def _worst_support(
    *values: ThesisHealthSupportState,
) -> ThesisHealthSupportState:
    priority = {
        ThesisHealthSupportState.SUPPORTED: 0,
        ThesisHealthSupportState.WEAKENING: 1,
        ThesisHealthSupportState.DATA_INSUFFICIENT: 2,
        ThesisHealthSupportState.INVALIDATING: 3,
    }
    if not values:
        raise ValueError("at least one support state is required")
    return max(values, key=priority.__getitem__)


def _sorted_unique_text(label: str, values: tuple[str, ...]) -> None:
    if values != tuple(sorted(values)) or len(values) != len(set(values)):
        raise ValueError(f"{label} values must be sorted and unique")
    for value in values:
        require_text(label, value)


def _effective_transition(
    prior: ThesisHealth | None,
    observed: ThesisHealth,
) -> ThesisHealth | None:
    if prior is ThesisHealth.INVALIDATED:
        return ThesisHealth.INVALIDATED
    if observed is ThesisHealth.INVALIDATED:
        return ThesisHealth.INVALIDATED
    if observed is ThesisHealth.DATA_INSUFFICIENT:
        return prior
    if prior is ThesisHealth.WEAKENING:
        return ThesisHealth.WEAKENING
    return observed


def _optional_thesis_health(value: object) -> ThesisHealth | None:
    return ThesisHealth(str(value)) if value is not None else None


def _observation_values_from_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    values: dict[str, Any] = {
        "thesis_id": ThesisId(str(payload["thesis_id"])),
        "thesis_version": _integer(payload["thesis_version"], "thesis_version"),
        "opportunity_id": OpportunityId(str(payload["opportunity_id"])),
        "symbol": str(payload["symbol"]),
        "primary_theme_id": (
            str(payload["primary_theme_id"])
            if payload["primary_theme_id"] is not None
            else None
        ),
        "assessed_at": datetime.fromisoformat(str(payload["assessed_at"])),
        "actor": str(payload["actor"]),
        "reason": str(payload["reason"]),
        "market_price": (
            _number(payload["market_price"])
            if payload["market_price"] is not None
            else None
        ),
    }
    for name in _ARTIFACT_ID_FIELDS:
        values[name] = ArtifactId(str(payload[name]))
    for name in _ARTIFACT_HASH_FIELDS:
        values[name] = str(payload[name])
    values["thesis_supporting_evidence"] = tuple(
        DecisionEvidenceReference.from_canonical_dict(
            _object(item, "Thesis supporting evidence")
        )
        for item in _array(
            payload["thesis_supporting_evidence"], "thesis_supporting_evidence"
        )
    )
    values["builder_revision"] = str(payload["builder_revision"])
    for name in _SUPPORT_STATE_FIELDS:
        values[name] = ThesisHealthSupportState(str(payload[name]))
    for name in (
        "triggered_condition_ids",
        "missing_reason_codes",
        "reason_codes",
    ):
        values[name] = tuple(str(item) for item in _array(payload[name], name))
    values["observed_health_state"] = ThesisHealth(
        str(payload["observed_health_state"])
    )
    prior_id = payload["prior_observation_id"]
    values["prior_observation_id"] = (
        ArtifactId(str(prior_id)) if prior_id is not None else None
    )
    values["prior_observation_hash"] = (
        str(payload["prior_observation_hash"])
        if payload["prior_observation_hash"] is not None
        else None
    )
    for name in (
        "prior_observed_health_state",
        "prior_effective_health_state",
        "effective_health_state",
    ):
        values[name] = _optional_thesis_health(payload[name])
    values["manual_evidence_ids"] = tuple(
        ArtifactId(str(item))
        for item in _array(payload["manual_evidence_ids"], "manual_evidence_ids")
    )
    values["manual_evidence_hashes"] = tuple(
        str(item)
        for item in _array(
            payload["manual_evidence_hashes"], "manual_evidence_hashes"
        )
    )
    for name, expected in (
        ("formal_oos_alpha", FORMAL_OOS_ALPHA_NOT_ESTABLISHED),
        (
            "manual_evidence_authentication",
            MANUAL_EVIDENCE_AUTHENTICATION_NOT_ESTABLISHED,
        ),
        ("trading_authority", TRADING_AUTHORITY_NOT_GRANTED),
    ):
        if payload[name] != expected:
            raise ValueError("Thesis health Observation authority cannot be inflated")
    return values


def _aware(label: str, value: datetime) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")


def _number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
        raise ValueError("numeric value must be finite")
    return float(value)


def _positive(label: str, value: object) -> float:
    result = _number(value)
    if result <= 0.0:
        raise ValueError(f"{label} must be positive")
    return result


def _bounded(label: str, value: object, lower: float, upper: float) -> float:
    result = _number(value)
    if not lower <= result <= upper:
        raise ValueError(f"{label} must be within [{lower}, {upper}]")
    return result


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be an integer")
    return value


def _state_set(label: str, states: tuple[Enum, ...]) -> None:
    if not states or tuple(sorted(states, key=lambda item: item.value)) != states or len(states) != len(set(states)):
        raise ValueError(f"{label} must be non-empty, sorted and unique")


def _state_rule_payload(rule_type: InvalidationRuleType, condition_id: str, states: tuple[Enum, ...]) -> dict[str, Any]:
    return {
        "rule_type": rule_type.value,
        "condition_id": condition_id,
        "states": [item.value for item in states],
    }


E = TypeVar("E", bound=Enum)


def _states(value: object, enum_type: type[E]) -> tuple[E, ...]:
    return tuple(enum_type(str(item)) for item in _array(value, "states"))


def _validate_mapping(label: str, mapping: tuple[tuple[E, ThesisHealthSupportState], ...], enum_type: type[E]) -> None:
    if tuple(item[0] for item in mapping) != tuple(enum_type):
        raise ValueError(f"{label} must exactly cover {enum_type.__name__}")
    for source, support in mapping:
        if not isinstance(source, enum_type) or not isinstance(support, ThesisHealthSupportState):
            raise TypeError(f"{label} entries have invalid types")
        if support is ThesisHealthSupportState.INVALIDATING:
            raise ValueError(f"{label} cannot add invalidation outside typed rules")


def _mapping_payload(mapping: object) -> list[dict[str, str]]:
    if not isinstance(mapping, tuple):
        raise TypeError("configuration mapping must be a tuple")
    result: list[dict[str, str]] = []
    for item in mapping:
        if not isinstance(item, tuple) or len(item) != 2 or not isinstance(item[0], Enum) or not isinstance(item[1], ThesisHealthSupportState):
            raise TypeError("configuration mapping entry is invalid")
        result.append({"source_state": item[0].value, "support_state": item[1].value})
    return result


def _parse_mapping(value: object, enum_type: type[E]) -> tuple[tuple[E, ThesisHealthSupportState], ...]:
    return tuple(
        (
            enum_type(str(_object(item, "mapping entry")["source_state"])),
            ThesisHealthSupportState(str(_object(item, "mapping entry")["support_state"])),
        )
        for item in _array(value, "mapping")
    )


def _fields(payload: Mapping[str, Any], expected: set[str], label: str) -> None:
    if set(payload) != expected:
        raise ValueError(f"{label} fields mismatch")


def _array(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    return value


def _object(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value
