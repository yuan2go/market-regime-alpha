"""Stateful Market Regime layered additively over the immutable V0 snapshot."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_datetime, canonical_hash
from market_regime_alpha.research.state_system.common import StateLineage
from market_regime_alpha.research.state_system.configuration import (
    MarketStateConfiguration,
)


class MarketRegimeState(str, Enum):
    DATA_INSUFFICIENT = "DATA_INSUFFICIENT"
    RISK_OFF = "RISK_OFF"
    DEFENSIVE = "DEFENSIVE"
    NEUTRAL = "NEUTRAL"
    RISK_ON = "RISK_ON"
    OVERHEATED = "OVERHEATED"


def _fraction(label: str, value: Decimal) -> None:
    if not isinstance(value, Decimal):
        raise TypeError(f"{label} must be Decimal")
    if not Decimal("0") <= value <= Decimal("1"):
        raise ValueError(f"{label} must be within [0, 1]")


def _canonical_reasons(label: str, values: tuple[str, ...], *, empty: bool = True) -> None:
    if not empty and not values:
        raise ValueError(f"{label} must not be empty")
    if any(not value or value != value.strip() for value in values):
        raise ValueError(f"{label} values must be non-empty and trimmed")
    if values != tuple(sorted(set(values))):
        raise ValueError(f"{label} must be unique and sorted")


@dataclass(frozen=True, slots=True)
class MarketRegimeObservation:
    observation_id: ArtifactId
    observation_hash: str
    v0_snapshot_id: ArtifactId
    regime_score: Decimal
    data_coverage: Decimal
    missing_evidence: tuple[str, ...]
    counter_evidence: tuple[str, ...]
    reason_codes: tuple[str, ...]
    lineage: StateLineage

    def __post_init__(self) -> None:
        if not Decimal("-1") <= self.regime_score <= Decimal("1"):
            raise ValueError("regime_score must be within [-1, 1]")
        _fraction("data_coverage", self.data_coverage)
        _canonical_reasons("missing_evidence", self.missing_evidence)
        _canonical_reasons("counter_evidence", self.counter_evidence)
        _canonical_reasons("reason_codes", self.reason_codes, empty=False)
        expected = canonical_hash(self.identity_payload())
        if self.observation_hash != expected:
            raise ValueError("observation_hash does not match content")
        if str(self.observation_id) != f"market-observation:{expected.removeprefix('sha256:')}":
            raise ValueError("observation_id does not match content")

    def identity_payload(self) -> dict[str, Any]:
        return {
            "schema": "stateful_market_regime_observation/v1",
            "v0_snapshot_id": str(self.v0_snapshot_id),
            "regime_score": str(self.regime_score),
            "data_coverage": str(self.data_coverage),
            "missing_evidence": list(self.missing_evidence),
            "counter_evidence": list(self.counter_evidence),
            "reason_codes": list(self.reason_codes),
            "lineage": self.lineage.identity_payload(),
        }

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "observation_id": str(self.observation_id),
            "observation_hash": self.observation_hash,
            **self.identity_payload(),
            "created_at": canonical_datetime(self.lineage.created_at),
        }

    @classmethod
    def create(
        cls,
        *,
        v0_snapshot_id: ArtifactId,
        regime_score: Decimal,
        data_coverage: Decimal,
        missing_evidence: tuple[str, ...],
        counter_evidence: tuple[str, ...],
        reason_codes: tuple[str, ...],
        lineage: StateLineage,
    ) -> MarketRegimeObservation:
        identity = {
            "schema": "stateful_market_regime_observation/v1",
            "v0_snapshot_id": str(v0_snapshot_id),
            "regime_score": str(regime_score),
            "data_coverage": str(data_coverage),
            "missing_evidence": list(missing_evidence),
            "counter_evidence": list(counter_evidence),
            "reason_codes": list(reason_codes),
            "lineage": lineage.identity_payload(),
        }
        digest = canonical_hash(identity)
        return cls(
            observation_id=ArtifactId(
                f"market-observation:{digest.removeprefix('sha256:')}"
            ),
            observation_hash=digest,
            v0_snapshot_id=v0_snapshot_id,
            regime_score=regime_score,
            data_coverage=data_coverage,
            missing_evidence=missing_evidence,
            counter_evidence=counter_evidence,
            reason_codes=reason_codes,
            lineage=lineage,
        )


@dataclass(frozen=True, slots=True)
class StatefulMarketRegime:
    state_id: ArtifactId
    state_hash: str
    previous_state_id: ArtifactId | None
    previous_state: MarketRegimeState | None
    proposed_state: MarketRegimeState
    effective_state: MarketRegimeState
    state_entered_at: datetime
    state_duration_seconds: int
    observation_count: int
    confirmation_count: int
    enter_threshold: Decimal
    exit_threshold: Decimal
    minimum_dwell_seconds: int
    hysteresis: Decimal
    data_coverage: Decimal
    missing_evidence: tuple[str, ...]
    counter_evidence: tuple[str, ...]
    reason_codes: tuple[str, ...]
    observation_id: ArtifactId
    lineage: StateLineage
    transitioned: bool

    @property
    def entry_authority_granted(self) -> bool:
        return False

    @property
    def broker_authority_granted(self) -> bool:
        return False

    def identity_payload(self) -> dict[str, Any]:
        return {
            "schema": "stateful_market_regime_state/v1",
            "previous_state_id": None if self.previous_state_id is None else str(self.previous_state_id),
            "previous_state": None if self.previous_state is None else self.previous_state.value,
            "proposed_state": self.proposed_state.value,
            "effective_state": self.effective_state.value,
            "state_entered_at": canonical_datetime(self.state_entered_at),
            "state_duration_seconds": self.state_duration_seconds,
            "observation_count": self.observation_count,
            "confirmation_count": self.confirmation_count,
            "enter_threshold": str(self.enter_threshold),
            "exit_threshold": str(self.exit_threshold),
            "minimum_dwell_seconds": self.minimum_dwell_seconds,
            "hysteresis": str(self.hysteresis),
            "data_coverage": str(self.data_coverage),
            "missing_evidence": list(self.missing_evidence),
            "counter_evidence": list(self.counter_evidence),
            "reason_codes": list(self.reason_codes),
            "observation_id": str(self.observation_id),
            "lineage": self.lineage.identity_payload(),
            "transitioned": self.transitioned,
        }


@dataclass(frozen=True, slots=True)
class MarketRegimeTransition:
    transition_id: ArtifactId
    transition_hash: str
    state_id: ArtifactId
    previous_state_id: ArtifactId | None
    from_state: MarketRegimeState | None
    proposed_state: MarketRegimeState
    to_state: MarketRegimeState
    observation_id: ArtifactId
    transitioned: bool
    reason_codes: tuple[str, ...]
    lineage: StateLineage

    def identity_payload(self) -> dict[str, Any]:
        return {
            "schema": "stateful_market_regime_transition/v1",
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
class MarketStateEvaluation:
    observation: MarketRegimeObservation
    state: StatefulMarketRegime
    transition: MarketRegimeTransition


def evaluate_market_state(
    observation: MarketRegimeObservation,
    *,
    previous: StatefulMarketRegime | None,
    configuration: MarketStateConfiguration,
) -> MarketStateEvaluation:
    """Deterministically evaluate one Observation against persisted prior state."""

    if observation.lineage.model_id != configuration.model_id or observation.lineage.model_version != configuration.model_version:
        raise ValueError("Observation model does not match selected configuration")
    if observation.lineage.configuration_id != configuration.configuration_id or observation.lineage.configuration_hash != configuration.configuration_hash:
        raise ValueError("Observation configuration does not match selected configuration")
    if previous is not None:
        if previous.lineage.continuous_operation_id != observation.lineage.continuous_operation_id:
            raise ValueError("Previous state belongs to another Continuous Operation")
        if observation.lineage.as_of_time <= previous.lineage.as_of_time:
            raise ValueError("Market observations must advance As-of Time")

    thresholds = configuration.thresholds
    proposed = _propose(observation, previous, configuration)
    reasons = set(observation.reason_codes)
    prior_effective = None if previous is None else previous.effective_state
    prior_entered = observation.lineage.as_of_time if previous is None else previous.state_entered_at
    duration = 0 if previous is None else int((observation.lineage.as_of_time - prior_entered).total_seconds())
    observations = 1 if previous is None else previous.observation_count + 1

    if previous is None:
        effective = proposed
        confirmation = 1
        transitioned = True
        entered = observation.lineage.as_of_time
        reasons.add("INITIAL_STATE")
    elif proposed is MarketRegimeState.DATA_INSUFFICIENT:
        effective = proposed
        confirmation = 1
        transitioned = proposed is not previous.effective_state
        entered = (
            observation.lineage.as_of_time
            if transitioned
            else previous.state_entered_at
        )
        reasons.add("MARKET_STATE_FAIL_CLOSED")
    else:
        same_proposal = previous.proposed_state is proposed and proposed is not previous.effective_state
        confirmation = previous.confirmation_count + 1 if same_proposal else (1 if proposed is not previous.effective_state else 0)
        effective = previous.effective_state
        transitioned = False
        entered = previous.state_entered_at
        advancing = _state_rank(proposed) > _state_rank(previous.effective_state)
        counter_blocked = advancing and bool(observation.counter_evidence)
        if counter_blocked:
            reasons.add("COUNTER_EVIDENCE_BLOCKED_ADVANCE")
        elif proposed is previous.effective_state:
            reasons.add("HYSTERESIS_RETAINED_STATE")
        elif confirmation < thresholds.confirmation_count:
            reasons.add("CONFIRMATION_PENDING")
        elif duration < thresholds.minimum_dwell_seconds:
            reasons.add("MINIMUM_DWELL_NOT_MET")
        else:
            effective = proposed
            transitioned = True
            entered = observation.lineage.as_of_time
            reasons.add("STATE_TRANSITION_CONFIRMED")

    state_reasons = tuple(sorted(reasons))
    state_payload = {
        "schema": "stateful_market_regime_state/v1",
        "previous_state_id": None if previous is None else str(previous.state_id),
        "previous_state": None if previous is None else previous.effective_state.value,
        "proposed_state": proposed.value,
        "effective_state": effective.value,
        "state_entered_at": canonical_datetime(entered),
        "state_duration_seconds": duration,
        "observation_count": observations,
        "confirmation_count": confirmation,
        "enter_threshold": str(thresholds.enter_threshold),
        "exit_threshold": str(thresholds.exit_threshold),
        "minimum_dwell_seconds": thresholds.minimum_dwell_seconds,
        "hysteresis": str(thresholds.hysteresis),
        "data_coverage": str(observation.data_coverage),
        "missing_evidence": list(observation.missing_evidence),
        "counter_evidence": list(observation.counter_evidence),
        "reason_codes": list(state_reasons),
        "observation_id": str(observation.observation_id),
        "lineage": observation.lineage.identity_payload(),
        "transitioned": transitioned,
    }
    state_hash = canonical_hash(state_payload)
    state = StatefulMarketRegime(
        state_id=ArtifactId(f"market-state:{state_hash.removeprefix('sha256:')}"),
        state_hash=state_hash,
        previous_state_id=None if previous is None else previous.state_id,
        previous_state=prior_effective,
        proposed_state=proposed,
        effective_state=effective,
        state_entered_at=entered,
        state_duration_seconds=duration,
        observation_count=observations,
        confirmation_count=confirmation,
        enter_threshold=thresholds.enter_threshold,
        exit_threshold=thresholds.exit_threshold,
        minimum_dwell_seconds=thresholds.minimum_dwell_seconds,
        hysteresis=thresholds.hysteresis,
        data_coverage=observation.data_coverage,
        missing_evidence=observation.missing_evidence,
        counter_evidence=observation.counter_evidence,
        reason_codes=state_reasons,
        observation_id=observation.observation_id,
        lineage=observation.lineage,
        transitioned=transitioned,
    )
    transition_payload = {
        "schema": "stateful_market_regime_transition/v1",
        "state_id": str(state.state_id),
        "previous_state_id": None if previous is None else str(previous.state_id),
        "from_state": None if prior_effective is None else prior_effective.value,
        "proposed_state": proposed.value,
        "to_state": effective.value,
        "observation_id": str(observation.observation_id),
        "transitioned": transitioned,
        "reason_codes": list(state_reasons),
        "lineage": observation.lineage.identity_payload(),
    }
    transition_hash = canonical_hash(transition_payload)
    transition = MarketRegimeTransition(
        transition_id=ArtifactId(f"market-transition:{transition_hash.removeprefix('sha256:')}"),
        transition_hash=transition_hash,
        state_id=state.state_id,
        previous_state_id=None if previous is None else previous.state_id,
        from_state=prior_effective,
        proposed_state=proposed,
        to_state=effective,
        observation_id=observation.observation_id,
        transitioned=transitioned,
        reason_codes=state_reasons,
        lineage=observation.lineage,
    )
    return MarketStateEvaluation(observation=observation, state=state, transition=transition)


def _propose(
    observation: MarketRegimeObservation,
    previous: StatefulMarketRegime | None,
    configuration: MarketStateConfiguration,
) -> MarketRegimeState:
    thresholds = configuration.thresholds
    if observation.data_coverage < thresholds.minimum_coverage:
        return MarketRegimeState.DATA_INSUFFICIENT
    score = observation.regime_score
    if previous is not None:
        current = previous.effective_state
        if current is MarketRegimeState.RISK_ON and thresholds.exit_threshold <= score < Decimal("0.85"):
            return MarketRegimeState.RISK_ON
        if current is MarketRegimeState.OVERHEATED and score >= thresholds.enter_threshold:
            return MarketRegimeState.OVERHEATED
        if current is MarketRegimeState.RISK_OFF and score <= -thresholds.exit_threshold:
            return MarketRegimeState.RISK_OFF
        if current is MarketRegimeState.DEFENSIVE:
            if score <= -thresholds.enter_threshold:
                return MarketRegimeState.RISK_OFF
            if score <= -thresholds.exit_threshold:
                return MarketRegimeState.DEFENSIVE
    if score >= Decimal("0.85"):
        proposed = MarketRegimeState.OVERHEATED
    elif score >= thresholds.enter_threshold:
        proposed = MarketRegimeState.RISK_ON
    elif score <= -thresholds.enter_threshold:
        proposed = MarketRegimeState.RISK_OFF
    elif score <= -thresholds.exit_threshold:
        proposed = MarketRegimeState.DEFENSIVE
    else:
        proposed = MarketRegimeState.NEUTRAL
    if previous is None or previous.effective_state is MarketRegimeState.DATA_INSUFFICIENT:
        return proposed
    return _adjacent(previous.effective_state, proposed)


_ORDER = (
    MarketRegimeState.RISK_OFF,
    MarketRegimeState.DEFENSIVE,
    MarketRegimeState.NEUTRAL,
    MarketRegimeState.RISK_ON,
    MarketRegimeState.OVERHEATED,
)


def _state_rank(value: MarketRegimeState) -> int:
    if value is MarketRegimeState.DATA_INSUFFICIENT:
        return -1
    return _ORDER.index(value)


def _adjacent(current: MarketRegimeState, proposed: MarketRegimeState) -> MarketRegimeState:
    if proposed is MarketRegimeState.DATA_INSUFFICIENT:
        return proposed
    current_index = _ORDER.index(current)
    proposed_index = _ORDER.index(proposed)
    if abs(proposed_index - current_index) <= 1:
        return proposed
    return _ORDER[current_index + (1 if proposed_index > current_index else -1)]
