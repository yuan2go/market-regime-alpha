"""Theme Rotation as a separate multi-source, mapping-aware state domain."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_datetime, canonical_hash, require_text
from market_regime_alpha.research.state_system.common import StateLineage
from market_regime_alpha.research.state_system.configuration import ThemeRotationConfiguration


class ThemeRotationState(str, Enum):
    DATA_INSUFFICIENT = "DATA_INSUFFICIENT"
    DORMANT = "DORMANT"
    STARTING = "STARTING"
    STRENGTHENING = "STRENGTHENING"
    LEADING = "LEADING"
    DIVERGING = "DIVERGING"
    WEAKENING = "WEAKENING"
    FAILED = "FAILED"


def _unit(label: str, value: Decimal) -> None:
    if not isinstance(value, Decimal):
        raise TypeError(f"{label} must be Decimal")
    if not Decimal("0") <= value <= Decimal("1"):
        raise ValueError(f"{label} must be within [0, 1]")


def _ordered(label: str, values: tuple[str, ...], *, required: bool = False) -> None:
    if required and not values:
        raise ValueError(f"{label} must not be empty")
    if values != tuple(sorted(set(values))):
        raise ValueError(f"{label} must be unique and sorted")


def _ordered_ids(label: str, values: tuple[ArtifactId, ...]) -> None:
    if not values or values != tuple(sorted(set(values), key=str)):
        raise ValueError(f"{label} must be non-empty, unique and sorted")


@dataclass(frozen=True, slots=True)
class ThemeRotationObservation:
    observation_id: ArtifactId
    observation_hash: str
    theme_id: str
    theme_mapping_id: ArtifactId
    theme_mapping_version: str
    mapping_complete: bool
    proxy_etf_ids: tuple[str, ...]
    etf_rotation_state_ids: tuple[ArtifactId, ...]
    verified_etf_strength: Decimal
    stock_breadth: Decimal
    participation_rate: Decimal
    leader_resonance: Decimal
    internal_concentration: Decimal
    amount_persistence: Decimal
    data_coverage: Decimal
    missing_evidence: tuple[str, ...]
    counter_evidence: tuple[str, ...]
    reason_codes: tuple[str, ...]
    lineage: StateLineage

    def __post_init__(self) -> None:
        require_text("theme_id", self.theme_id)
        require_text("theme_mapping_version", self.theme_mapping_version)
        if not isinstance(self.mapping_complete, bool):
            raise TypeError("mapping_complete must be bool")
        _ordered("proxy_etf_ids", self.proxy_etf_ids, required=True)
        _ordered_ids("etf_rotation_state_ids", self.etf_rotation_state_ids)
        for label, value in (
            ("verified_etf_strength", self.verified_etf_strength),
            ("stock_breadth", self.stock_breadth),
            ("participation_rate", self.participation_rate),
            ("leader_resonance", self.leader_resonance),
            ("internal_concentration", self.internal_concentration),
            ("amount_persistence", self.amount_persistence),
            ("data_coverage", self.data_coverage),
        ):
            _unit(label, value)
        _ordered("missing_evidence", self.missing_evidence)
        _ordered("counter_evidence", self.counter_evidence)
        _ordered("reason_codes", self.reason_codes, required=True)
        expected = canonical_hash(self.identity_payload())
        if self.observation_hash != expected or str(self.observation_id) != f"theme-observation:{expected[7:]}":
            raise ValueError("Theme observation identity mismatch")

    def identity_payload(self) -> dict[str, Any]:
        return {
            "schema": "theme_rotation_observation/v1",
            "theme_id": self.theme_id,
            "theme_mapping_id": str(self.theme_mapping_id),
            "theme_mapping_version": self.theme_mapping_version,
            "mapping_complete": self.mapping_complete,
            "proxy_etf_ids": list(self.proxy_etf_ids),
            "etf_rotation_state_ids": [str(value) for value in self.etf_rotation_state_ids],
            "verified_etf_strength": str(self.verified_etf_strength),
            "stock_breadth": str(self.stock_breadth),
            "participation_rate": str(self.participation_rate),
            "leader_resonance": str(self.leader_resonance),
            "internal_concentration": str(self.internal_concentration),
            "amount_persistence": str(self.amount_persistence),
            "data_coverage": str(self.data_coverage),
            "missing_evidence": list(self.missing_evidence),
            "counter_evidence": list(self.counter_evidence),
            "reason_codes": list(self.reason_codes),
            "lineage": self.lineage.identity_payload(),
        }

    @classmethod
    def create(
        cls,
        *,
        theme_id: str,
        theme_mapping_id: ArtifactId,
        theme_mapping_version: str,
        mapping_complete: bool,
        proxy_etf_ids: tuple[str, ...],
        etf_rotation_state_ids: tuple[ArtifactId, ...],
        verified_etf_strength: Decimal,
        stock_breadth: Decimal,
        participation_rate: Decimal,
        leader_resonance: Decimal,
        internal_concentration: Decimal,
        amount_persistence: Decimal,
        data_coverage: Decimal,
        missing_evidence: tuple[str, ...],
        counter_evidence: tuple[str, ...],
        reason_codes: tuple[str, ...],
        lineage: StateLineage,
    ) -> ThemeRotationObservation:
        counters = set(counter_evidence)
        reasons = set(reason_codes)
        missing = set(missing_evidence)
        if not mapping_complete:
            missing.add("THEME_MAPPING")
            reasons.add("THEME_MAPPING_INCOMPLETE")
        if verified_etf_strength >= Decimal("0.65") and (
            stock_breadth < Decimal("0.45") or participation_rate < Decimal("0.45")
        ):
            counters.add("ETF_STOCK_EVIDENCE_CONFLICT")
            reasons.add("ETF_STOCK_EVIDENCE_CONFLICT")
        if leader_resonance >= Decimal("0.75") and participation_rate < Decimal("0.45"):
            counters.add("LEADER_PARTICIPATION_CONFLICT")
            reasons.add("LEADER_PARTICIPATION_CONFLICT")
        ordered_proxy_etfs = tuple(sorted(set(proxy_etf_ids)))
        ordered_etf_states = tuple(sorted(set(etf_rotation_state_ids), key=str))
        ordered_missing = tuple(sorted(missing))
        ordered_counters = tuple(sorted(counters))
        ordered_reasons = tuple(sorted(reasons))
        identity = {
            "schema": "theme_rotation_observation/v1",
            "theme_id": theme_id,
            "theme_mapping_id": str(theme_mapping_id),
            "theme_mapping_version": theme_mapping_version,
            "mapping_complete": mapping_complete,
            "proxy_etf_ids": list(ordered_proxy_etfs),
            "etf_rotation_state_ids": [str(value) for value in ordered_etf_states],
            "verified_etf_strength": str(verified_etf_strength),
            "stock_breadth": str(stock_breadth),
            "participation_rate": str(participation_rate),
            "leader_resonance": str(leader_resonance),
            "internal_concentration": str(internal_concentration),
            "amount_persistence": str(amount_persistence),
            "data_coverage": str(data_coverage),
            "missing_evidence": list(ordered_missing),
            "counter_evidence": list(ordered_counters),
            "reason_codes": list(ordered_reasons),
            "lineage": lineage.identity_payload(),
        }
        digest = canonical_hash(identity)
        return cls(
            observation_id=ArtifactId(f"theme-observation:{digest[7:]}"),
            observation_hash=digest,
            theme_id=theme_id,
            theme_mapping_id=theme_mapping_id,
            theme_mapping_version=theme_mapping_version,
            mapping_complete=mapping_complete,
            proxy_etf_ids=ordered_proxy_etfs,
            etf_rotation_state_ids=ordered_etf_states,
            verified_etf_strength=verified_etf_strength,
            stock_breadth=stock_breadth,
            participation_rate=participation_rate,
            leader_resonance=leader_resonance,
            internal_concentration=internal_concentration,
            amount_persistence=amount_persistence,
            data_coverage=data_coverage,
            missing_evidence=ordered_missing,
            counter_evidence=ordered_counters,
            reason_codes=ordered_reasons,
            lineage=lineage,
        )


@dataclass(frozen=True, slots=True)
class StatefulThemeRotation:
    state_id: ArtifactId
    state_hash: str
    theme_id: str
    theme_mapping_id: ArtifactId
    theme_mapping_version: str
    proxy_etf_ids: tuple[str, ...]
    etf_rotation_state_ids: tuple[ArtifactId, ...]
    previous_state_id: ArtifactId | None
    previous_state: ThemeRotationState | None
    proposed_state: ThemeRotationState
    effective_state: ThemeRotationState
    state_entered_at: datetime
    state_duration_seconds: int
    observation_count: int
    confirmation_count: int
    enter_threshold: Decimal
    exit_threshold: Decimal
    minimum_dwell_seconds: int
    hysteresis: Decimal
    rotation_score: Decimal
    data_coverage: Decimal
    missing_evidence: tuple[str, ...]
    counter_evidence: tuple[str, ...]
    reason_codes: tuple[str, ...]
    observation_id: ArtifactId
    lineage: StateLineage
    transitioned: bool

    def identity_payload(self) -> dict[str, Any]:
        return _state_payload(self)


@dataclass(frozen=True, slots=True)
class ThemeRotationTransition:
    transition_id: ArtifactId
    transition_hash: str
    state_id: ArtifactId
    previous_state_id: ArtifactId | None
    from_state: ThemeRotationState | None
    proposed_state: ThemeRotationState
    to_state: ThemeRotationState
    observation_id: ArtifactId
    transitioned: bool
    reason_codes: tuple[str, ...]
    lineage: StateLineage


@dataclass(frozen=True, slots=True)
class ThemeRotationEvaluation:
    observation: ThemeRotationObservation
    state: StatefulThemeRotation
    transition: ThemeRotationTransition


def evaluate_theme_rotation(
    observation: ThemeRotationObservation,
    *,
    previous: StatefulThemeRotation | None,
    configuration: ThemeRotationConfiguration,
) -> ThemeRotationEvaluation:
    _validate_binding(observation, previous, configuration)
    score = _score(observation)
    proposed, proposal_reasons = _propose(observation, previous, configuration, score)
    reasons = set(observation.reason_codes) | set(proposal_reasons)
    prior = None if previous is None else previous.effective_state
    entered = observation.lineage.as_of_time if previous is None else previous.state_entered_at
    duration = 0 if previous is None else int((observation.lineage.as_of_time - entered).total_seconds())
    count = 1 if previous is None else previous.observation_count + 1
    if previous is None:
        effective, confirmation, transitioned = proposed, 1, True
        reasons.add("INITIAL_THEME_ROTATION_STATE")
    elif proposed is ThemeRotationState.DATA_INSUFFICIENT:
        effective, confirmation, transitioned = proposed, 1, proposed is not prior
        if transitioned:
            entered = observation.lineage.as_of_time
        reasons.add("THEME_ROTATION_FAIL_CLOSED")
    else:
        assert prior is not None
        same = previous.proposed_state is proposed and proposed is not prior
        confirmation = previous.confirmation_count + 1 if same else (1 if proposed is not prior else 0)
        effective, transitioned = prior, False
        if proposed is prior:
            reasons.add("THEME_HYSTERESIS_RETAINED_STATE")
        elif confirmation < configuration.thresholds.confirmation_count:
            reasons.add("THEME_CONFIRMATION_PENDING")
        elif duration < configuration.thresholds.minimum_dwell_seconds:
            reasons.add("THEME_MINIMUM_DWELL_NOT_MET")
        else:
            effective, transitioned = proposed, True
            entered = observation.lineage.as_of_time
            reasons.add("THEME_STATE_TRANSITION_CONFIRMED")
    ordered_reasons = tuple(sorted(reasons))
    threshold = configuration.thresholds
    prototype = StatefulThemeRotation(
        state_id=ArtifactId("pending"),
        state_hash="pending",
        theme_id=observation.theme_id,
        theme_mapping_id=observation.theme_mapping_id,
        theme_mapping_version=observation.theme_mapping_version,
        proxy_etf_ids=observation.proxy_etf_ids,
        etf_rotation_state_ids=observation.etf_rotation_state_ids,
        previous_state_id=None if previous is None else previous.state_id,
        previous_state=prior,
        proposed_state=proposed,
        effective_state=effective,
        state_entered_at=entered,
        state_duration_seconds=duration,
        observation_count=count,
        confirmation_count=confirmation,
        enter_threshold=threshold.enter_threshold,
        exit_threshold=threshold.exit_threshold,
        minimum_dwell_seconds=threshold.minimum_dwell_seconds,
        hysteresis=threshold.hysteresis,
        rotation_score=score,
        data_coverage=observation.data_coverage,
        missing_evidence=observation.missing_evidence,
        counter_evidence=observation.counter_evidence,
        reason_codes=ordered_reasons,
        observation_id=observation.observation_id,
        lineage=observation.lineage,
        transitioned=transitioned,
    )
    state_hash = canonical_hash(_state_payload(prototype))
    state = replace(
        prototype,
        state_id=ArtifactId(f"theme-state:{state_hash[7:]}"),
        state_hash=state_hash,
    )
    transition_payload = {
        "schema": "theme_rotation_transition/v1",
        "state_id": str(state.state_id),
        "previous_state_id": None if previous is None else str(previous.state_id),
        "from_state": None if prior is None else prior.value,
        "proposed_state": proposed.value,
        "to_state": effective.value,
        "observation_id": str(observation.observation_id),
        "transitioned": transitioned,
        "reason_codes": list(ordered_reasons),
        "lineage": observation.lineage.identity_payload(),
    }
    transition_hash = canonical_hash(transition_payload)
    transition = ThemeRotationTransition(
        transition_id=ArtifactId(f"theme-transition:{transition_hash[7:]}"),
        transition_hash=transition_hash,
        state_id=state.state_id,
        previous_state_id=None if previous is None else previous.state_id,
        from_state=prior,
        proposed_state=proposed,
        to_state=effective,
        observation_id=observation.observation_id,
        transitioned=transitioned,
        reason_codes=ordered_reasons,
        lineage=observation.lineage,
    )
    return ThemeRotationEvaluation(observation, state, transition)


def _score(value: ThemeRotationObservation) -> Decimal:
    concentration_quality = Decimal("1") - abs(value.internal_concentration - Decimal("0.50")) * Decimal("2")
    values = (
        value.verified_etf_strength,
        value.stock_breadth,
        value.participation_rate,
        value.leader_resonance,
        value.amount_persistence,
        concentration_quality,
    )
    return sum(values, Decimal("0")) / Decimal(len(values))


def _propose(
    value: ThemeRotationObservation,
    previous: StatefulThemeRotation | None,
    configuration: ThemeRotationConfiguration,
    score: Decimal,
) -> tuple[ThemeRotationState, tuple[str, ...]]:
    threshold = configuration.thresholds
    if not value.mapping_complete:
        return ThemeRotationState.DATA_INSUFFICIENT, ("THEME_MAPPING_INCOMPLETE",)
    if value.data_coverage < threshold.minimum_coverage:
        return ThemeRotationState.DATA_INSUFFICIENT, ("THEME_DATA_COVERAGE_INSUFFICIENT",)
    if value.counter_evidence:
        return ThemeRotationState.DIVERGING, ("THEME_MULTI_SOURCE_DIVERGENCE",)
    if previous is None:
        return (
            ThemeRotationState.DORMANT if score < Decimal("0.20") else ThemeRotationState.STARTING,
            ("THEME_INITIAL_PULSE_CAPPED",),
        )
    current = previous.effective_state
    if current in {ThemeRotationState.LEADING, ThemeRotationState.DIVERGING} and score < threshold.exit_threshold:
        return ThemeRotationState.WEAKENING, ("THEME_ROTATION_WEAKENING",)
    if current is ThemeRotationState.WEAKENING and score <= Decimal("0.20"):
        return ThemeRotationState.FAILED, ("THEME_ROTATION_FAILED",)
    if score >= Decimal("0.70"):
        candidate = ThemeRotationState.LEADING
    elif score >= threshold.exit_threshold:
        candidate = ThemeRotationState.STRENGTHENING
    elif score >= Decimal("0.20"):
        candidate = ThemeRotationState.STARTING
    else:
        candidate = ThemeRotationState.DORMANT
    if current is ThemeRotationState.STARTING and candidate is ThemeRotationState.LEADING:
        candidate = ThemeRotationState.STRENGTHENING
    return candidate, (f"THEME_ROTATION_{candidate.value}",)


def _validate_binding(
    observation: ThemeRotationObservation,
    previous: StatefulThemeRotation | None,
    configuration: ThemeRotationConfiguration,
) -> None:
    lineage = observation.lineage
    if (lineage.model_id, lineage.model_version, lineage.configuration_id, lineage.configuration_hash) != (
        configuration.model_id,
        configuration.model_version,
        configuration.configuration_id,
        configuration.configuration_hash,
    ):
        raise ValueError("Theme observation configuration binding mismatch")
    if previous is not None:
        if previous.theme_id != observation.theme_id:
            raise ValueError("Previous Theme state belongs to another Theme")
        if lineage.as_of_time <= previous.lineage.as_of_time:
            raise ValueError("Theme observations must advance As-of Time")


def _state_payload(value: StatefulThemeRotation) -> dict[str, Any]:
    return {
        "schema": "theme_rotation_state/v1",
        "theme_id": value.theme_id,
        "theme_mapping_id": str(value.theme_mapping_id),
        "theme_mapping_version": value.theme_mapping_version,
        "proxy_etf_ids": list(value.proxy_etf_ids),
        "etf_rotation_state_ids": [str(item) for item in value.etf_rotation_state_ids],
        "previous_state_id": None if value.previous_state_id is None else str(value.previous_state_id),
        "previous_state": None if value.previous_state is None else value.previous_state.value,
        "proposed_state": value.proposed_state.value,
        "effective_state": value.effective_state.value,
        "state_entered_at": canonical_datetime(value.state_entered_at),
        "state_duration_seconds": value.state_duration_seconds,
        "observation_count": value.observation_count,
        "confirmation_count": value.confirmation_count,
        "enter_threshold": str(value.enter_threshold),
        "exit_threshold": str(value.exit_threshold),
        "minimum_dwell_seconds": value.minimum_dwell_seconds,
        "hysteresis": str(value.hysteresis),
        "rotation_score": str(value.rotation_score),
        "data_coverage": str(value.data_coverage),
        "missing_evidence": list(value.missing_evidence),
        "counter_evidence": list(value.counter_evidence),
        "reason_codes": list(value.reason_codes),
        "observation_id": str(value.observation_id),
        "lineage": value.lineage.identity_payload(),
        "transitioned": value.transitioned,
    }
