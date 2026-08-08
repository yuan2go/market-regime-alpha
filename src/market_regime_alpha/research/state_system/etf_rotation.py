"""Stateful ETF Rotation from observable price, amount and liquidity proxies."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_datetime, canonical_hash, require_text
from market_regime_alpha.research.state_system.common import StateLineage
from market_regime_alpha.research.state_system.configuration import EtfRotationConfiguration


class EtfRotationState(str, Enum):
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


def _signed(label: str, value: Decimal) -> None:
    if not isinstance(value, Decimal):
        raise TypeError(f"{label} must be Decimal")
    if not Decimal("-1") <= value <= Decimal("1"):
        raise ValueError(f"{label} must be within [-1, 1]")


def _ordered(label: str, values: tuple[str, ...]) -> None:
    if values != tuple(sorted(set(values))):
        raise ValueError(f"{label} must be unique and sorted")


@dataclass(frozen=True, slots=True)
class EtfRotationObservation:
    observation_id: ArtifactId
    observation_hash: str
    etf_id: str
    benchmark_id: str
    relative_strength_1d: Decimal
    relative_strength_3d: Decimal
    relative_strength_5d: Decimal
    relative_strength_10d: Decimal
    benchmark_excess: Decimal
    amount_change: Decimal
    amount_persistence: Decimal
    volume_change: Decimal
    drawdown: Decimal
    volatility: Decimal
    diffusion: Decimal
    liquidity: Decimal
    data_coverage: Decimal
    missing_evidence: tuple[str, ...]
    counter_evidence: tuple[str, ...]
    reason_codes: tuple[str, ...]
    lineage: StateLineage

    def __post_init__(self) -> None:
        require_text("etf_id", self.etf_id)
        require_text("benchmark_id", self.benchmark_id)
        for label, value in (
            ("relative_strength_1d", self.relative_strength_1d),
            ("relative_strength_3d", self.relative_strength_3d),
            ("relative_strength_5d", self.relative_strength_5d),
            ("relative_strength_10d", self.relative_strength_10d),
            ("benchmark_excess", self.benchmark_excess),
            ("amount_change", self.amount_change),
            ("volume_change", self.volume_change),
        ):
            _signed(label, value)
        for label, value in (
            ("amount_persistence", self.amount_persistence),
            ("drawdown", self.drawdown),
            ("volatility", self.volatility),
            ("diffusion", self.diffusion),
            ("liquidity", self.liquidity),
            ("data_coverage", self.data_coverage),
        ):
            _unit(label, value)
        _ordered("missing_evidence", self.missing_evidence)
        _ordered("counter_evidence", self.counter_evidence)
        _ordered("reason_codes", self.reason_codes)
        expected = canonical_hash(self.identity_payload())
        if expected != self.observation_hash:
            raise ValueError("ETF observation hash mismatch")
        if str(self.observation_id) != f"etf-observation:{expected[7:]}":
            raise ValueError("ETF observation identity mismatch")

    def identity_payload(self) -> dict[str, Any]:
        return {
            "schema": "etf_rotation_observation/v1",
            "etf_id": self.etf_id,
            "benchmark_id": self.benchmark_id,
            "relative_strength_1d": str(self.relative_strength_1d),
            "relative_strength_3d": str(self.relative_strength_3d),
            "relative_strength_5d": str(self.relative_strength_5d),
            "relative_strength_10d": str(self.relative_strength_10d),
            "benchmark_excess": str(self.benchmark_excess),
            "amount_change": str(self.amount_change),
            "amount_persistence": str(self.amount_persistence),
            "volume_change": str(self.volume_change),
            "drawdown": str(self.drawdown),
            "volatility": str(self.volatility),
            "diffusion": str(self.diffusion),
            "liquidity": str(self.liquidity),
            "data_coverage": str(self.data_coverage),
            "missing_evidence": list(self.missing_evidence),
            "counter_evidence": list(self.counter_evidence),
            "reason_codes": list(self.reason_codes),
            "lineage": self.lineage.identity_payload(),
        }

    @classmethod
    def create(cls, **values: Any) -> EtfRotationObservation:
        temporary = dict(values)
        lineage = temporary["lineage"]
        if not isinstance(lineage, StateLineage):
            raise TypeError("lineage must be StateLineage")
        identity = {
            "schema": "etf_rotation_observation/v1",
            **{
                key: str(value) if isinstance(value, Decimal) else value
                for key, value in temporary.items()
                if key not in {"lineage", "missing_evidence", "counter_evidence", "reason_codes"}
            },
            "missing_evidence": list(temporary["missing_evidence"]),
            "counter_evidence": list(temporary["counter_evidence"]),
            "reason_codes": list(temporary["reason_codes"]),
            "lineage": lineage.identity_payload(),
        }
        digest = canonical_hash(identity)
        return cls(
            observation_id=ArtifactId(f"etf-observation:{digest[7:]}"),
            observation_hash=digest,
            **values,
        )


@dataclass(frozen=True, slots=True)
class StatefulEtfRotation:
    state_id: ArtifactId
    state_hash: str
    etf_id: str
    previous_state_id: ArtifactId | None
    previous_state: EtfRotationState | None
    proposed_state: EtfRotationState
    effective_state: EtfRotationState
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

    @property
    def institutional_owner_identified(self) -> bool:
        return False

    def identity_payload(self) -> dict[str, Any]:
        return _state_payload(self, self.lineage)


@dataclass(frozen=True, slots=True)
class EtfRotationTransition:
    transition_id: ArtifactId
    transition_hash: str
    state_id: ArtifactId
    previous_state_id: ArtifactId | None
    from_state: EtfRotationState | None
    proposed_state: EtfRotationState
    to_state: EtfRotationState
    observation_id: ArtifactId
    transitioned: bool
    reason_codes: tuple[str, ...]
    lineage: StateLineage

    def identity_payload(self) -> dict[str, Any]:
        return {
            "schema": "etf_rotation_transition/v1",
            "state_id": str(self.state_id),
            "previous_state_id": None if self.previous_state_id is None else str(self.previous_state_id),
            "from_state": None if self.from_state is None else self.from_state.value,
            "proposed_state": self.proposed_state.value,
            "to_state": self.to_state.value,
            "observation_id": str(self.observation_id),
            "transitioned": self.transitioned,
            "reason_codes": list(self.reason_codes),
            "lineage": self.lineage.identity_payload(),
        }


@dataclass(frozen=True, slots=True)
class EtfRotationEvaluation:
    observation: EtfRotationObservation
    state: StatefulEtfRotation
    transition: EtfRotationTransition


def evaluate_etf_rotation(
    observation: EtfRotationObservation,
    *,
    previous: StatefulEtfRotation | None,
    configuration: EtfRotationConfiguration,
) -> EtfRotationEvaluation:
    _validate_binding(observation, previous, configuration)
    score = _score(observation)
    proposed, proposal_reasons = _propose(observation, previous, configuration, score)
    reasons = set(observation.reason_codes) | set(proposal_reasons)
    prior_state = None if previous is None else previous.effective_state
    entered = observation.lineage.as_of_time if previous is None else previous.state_entered_at
    duration = 0 if previous is None else int((observation.lineage.as_of_time - entered).total_seconds())
    count = 1 if previous is None else previous.observation_count + 1
    if previous is None:
        effective, confirmation, transitioned = proposed, 1, True
        reasons.add("INITIAL_ETF_ROTATION_STATE")
    elif proposed is EtfRotationState.DATA_INSUFFICIENT:
        effective, confirmation, transitioned = proposed, 1, proposed is not prior_state
        if transitioned:
            entered = observation.lineage.as_of_time
        reasons.add("ETF_ROTATION_FAIL_CLOSED")
    else:
        assert prior_state is not None
        same = previous.proposed_state is proposed and proposed is not prior_state
        confirmation = previous.confirmation_count + 1 if same else (1 if proposed is not prior_state else 0)
        effective, transitioned = prior_state, False
        if proposed is prior_state:
            reasons.add("ETF_HYSTERESIS_RETAINED_STATE")
        elif confirmation < configuration.thresholds.confirmation_count:
            reasons.add("ETF_CONFIRMATION_PENDING")
        elif duration < configuration.thresholds.minimum_dwell_seconds:
            reasons.add("ETF_MINIMUM_DWELL_NOT_MET")
        else:
            effective, transitioned = proposed, True
            entered = observation.lineage.as_of_time
            reasons.add("ETF_STATE_TRANSITION_CONFIRMED")
    ordered_reasons = tuple(sorted(reasons))
    threshold = configuration.thresholds
    prototype = StatefulEtfRotation(
        state_id=ArtifactId("pending"),
        state_hash="pending",
        etf_id=observation.etf_id,
        previous_state_id=None if previous is None else previous.state_id,
        previous_state=prior_state,
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
    state_hash = canonical_hash(_state_payload(prototype, observation.lineage))
    state = StatefulEtfRotation(
        **{
            field: getattr(prototype, field)
            for field in prototype.__dataclass_fields__
            if field not in {"state_id", "state_hash"}
        },
        state_id=ArtifactId(f"etf-state:{state_hash[7:]}"),
        state_hash=state_hash,
    )
    transition_payload = {
        "schema": "etf_rotation_transition/v1",
        "state_id": str(state.state_id),
        "previous_state_id": None if previous is None else str(previous.state_id),
        "from_state": None if prior_state is None else prior_state.value,
        "proposed_state": proposed.value,
        "to_state": effective.value,
        "observation_id": str(observation.observation_id),
        "transitioned": transitioned,
        "reason_codes": list(ordered_reasons),
        "lineage": observation.lineage.identity_payload(),
    }
    transition_hash = canonical_hash(transition_payload)
    transition = EtfRotationTransition(
        transition_id=ArtifactId(f"etf-transition:{transition_hash[7:]}"),
        transition_hash=transition_hash,
        state_id=state.state_id,
        previous_state_id=None if previous is None else previous.state_id,
        from_state=prior_state,
        proposed_state=proposed,
        to_state=effective,
        observation_id=observation.observation_id,
        transitioned=transitioned,
        reason_codes=ordered_reasons,
        lineage=observation.lineage,
    )
    return EtfRotationEvaluation(observation, state, transition)


def _score(value: EtfRotationObservation) -> Decimal:
    positive = (
        value.relative_strength_1d,
        value.relative_strength_3d,
        value.relative_strength_5d,
        value.relative_strength_10d,
        value.benchmark_excess,
        value.amount_change,
        value.amount_persistence,
        value.volume_change,
        value.diffusion,
        value.liquidity,
        Decimal("1") - value.volatility,
        -value.drawdown,
    )
    return sum(positive, Decimal("0")) / Decimal(len(positive))


def _propose(
    value: EtfRotationObservation,
    previous: StatefulEtfRotation | None,
    configuration: EtfRotationConfiguration,
    score: Decimal,
) -> tuple[EtfRotationState, tuple[str, ...]]:
    threshold = configuration.thresholds
    if value.data_coverage < threshold.minimum_coverage:
        return EtfRotationState.DATA_INSUFFICIENT, ("ETF_DATA_COVERAGE_INSUFFICIENT",)
    if value.liquidity < threshold.minimum_coverage:
        return EtfRotationState.DATA_INSUFFICIENT, ("ETF_LIQUIDITY_INSUFFICIENT",)
    if previous is None:
        return (
            EtfRotationState.DORMANT if score < Decimal("0.20") else EtfRotationState.STARTING,
            ("ETF_INITIAL_PULSE_CAPPED",),
        )
    current = previous.effective_state
    if current is EtfRotationState.LEADING and (value.counter_evidence or value.diffusion < Decimal("0.40")):
        return EtfRotationState.DIVERGING, ("ETF_ROTATION_DIVERGENCE",)
    if current in {EtfRotationState.LEADING, EtfRotationState.DIVERGING} and score < threshold.exit_threshold:
        return EtfRotationState.WEAKENING, ("ETF_ROTATION_WEAKENING",)
    if current is EtfRotationState.WEAKENING and score <= Decimal("0"):
        return EtfRotationState.FAILED, ("ETF_ROTATION_FAILED",)
    if score >= Decimal("0.70") and value.diffusion >= Decimal("0.60") and value.amount_persistence >= Decimal("0.60"):
        return EtfRotationState.LEADING, ("ETF_MULTI_HORIZON_LEADERSHIP",)
    if score >= threshold.exit_threshold:
        return EtfRotationState.STRENGTHENING, ("ETF_STRENGTH_PERSISTING",)
    if score >= Decimal("0.20"):
        return EtfRotationState.STARTING, ("ETF_ROTATION_STARTING",)
    if score <= Decimal("-0.20"):
        return EtfRotationState.FAILED, ("ETF_ROTATION_FAILED",)
    return EtfRotationState.DORMANT, ("ETF_ROTATION_DORMANT",)


def _validate_binding(
    observation: EtfRotationObservation,
    previous: StatefulEtfRotation | None,
    configuration: EtfRotationConfiguration,
) -> None:
    lineage = observation.lineage
    if (lineage.model_id, lineage.model_version, lineage.configuration_id, lineage.configuration_hash) != (
        configuration.model_id,
        configuration.model_version,
        configuration.configuration_id,
        configuration.configuration_hash,
    ):
        raise ValueError("ETF observation configuration binding mismatch")
    if previous is not None:
        if previous.etf_id != observation.etf_id:
            raise ValueError("Previous ETF state belongs to another ETF")
        if lineage.as_of_time <= previous.lineage.as_of_time:
            raise ValueError("ETF observations must advance As-of Time")


def _state_payload(value: StatefulEtfRotation, lineage: StateLineage) -> dict[str, Any]:
    return {
        "schema": "etf_rotation_state/v1",
        "etf_id": value.etf_id,
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
        "lineage": lineage.identity_payload(),
        "transitioned": value.transitioned,
    }
