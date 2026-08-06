"""Stateful capital-proxy inference; never an assertion about hidden actors."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_datetime, canonical_hash, require_text
from market_regime_alpha.research.state_system.common import StateLineage
from market_regime_alpha.research.state_system.configuration import CapitalStateConfiguration


class CapitalState(str, Enum):
    DATA_INSUFFICIENT = "DATA_INSUFFICIENT"
    CONTRACTION_BIAS = "CONTRACTION_BIAS"
    ACCUMULATION_BIAS = "ACCUMULATION_BIAS"
    EXPANSION_BIAS = "EXPANSION_BIAS"
    DISTRIBUTION_BIAS = "DISTRIBUTION_BIAS"


def _signed(label: str, value: Decimal) -> None:
    if not isinstance(value, Decimal):
        raise TypeError(f"{label} must be Decimal")
    if not Decimal("-1") <= value <= Decimal("1"):
        raise ValueError(f"{label} must be within [-1, 1]")


def _unit(label: str, value: Decimal) -> None:
    if not isinstance(value, Decimal):
        raise TypeError(f"{label} must be Decimal")
    if not Decimal("0") <= value <= Decimal("1"):
        raise ValueError(f"{label} must be within [0, 1]")


@dataclass(frozen=True, slots=True)
class CapitalObservation:
    observation_id: ArtifactId
    observation_hash: str
    scope_id: str
    price_change: Decimal
    volume_change: Decimal
    amount_change: Decimal
    breadth_change: Decimal
    participation_change: Decimal
    concentration: Decimal
    etf_strength: Decimal
    data_coverage: Decimal
    uncertainty: Decimal
    missing_evidence: tuple[str, ...]
    counter_evidence: tuple[str, ...]
    reason_codes: tuple[str, ...]
    lineage: StateLineage

    def __post_init__(self) -> None:
        require_text("scope_id", self.scope_id)
        for label, value in (
            ("price_change", self.price_change),
            ("volume_change", self.volume_change),
            ("amount_change", self.amount_change),
            ("breadth_change", self.breadth_change),
            ("participation_change", self.participation_change),
            ("etf_strength", self.etf_strength),
        ):
            _signed(label, value)
        for label, value in (
            ("concentration", self.concentration),
            ("data_coverage", self.data_coverage),
            ("uncertainty", self.uncertainty),
        ):
            _unit(label, value)
        for label, values in (
            ("missing_evidence", self.missing_evidence),
            ("counter_evidence", self.counter_evidence),
            ("reason_codes", self.reason_codes),
        ):
            if values != tuple(sorted(set(values))):
                raise ValueError(f"{label} must be unique and sorted")
        expected = canonical_hash(self.identity_payload())
        if expected != self.observation_hash or str(self.observation_id) != f"capital-observation:{expected[7:]}":
            raise ValueError("Capital observation identity mismatch")

    def identity_payload(self) -> dict[str, Any]:
        return {
            "schema": "capital_observation/v1",
            "scope_id": self.scope_id,
            "observable_features": {
                "price_change": str(self.price_change),
                "volume_change": str(self.volume_change),
                "amount_change": str(self.amount_change),
                "breadth_change": str(self.breadth_change),
                "participation_change": str(self.participation_change),
                "concentration": str(self.concentration),
                "etf_strength": str(self.etf_strength),
            },
            "data_coverage": str(self.data_coverage),
            "uncertainty": str(self.uncertainty),
            "missing_evidence": list(self.missing_evidence),
            "counter_evidence": list(self.counter_evidence),
            "reason_codes": list(self.reason_codes),
            "lineage": self.lineage.identity_payload(),
        }

    @classmethod
    def create(cls, **values: Any) -> CapitalObservation:
        lineage = values.get("lineage")
        if not isinstance(lineage, StateLineage):
            raise TypeError("lineage must be StateLineage")
        identity = {
            "schema": "capital_observation/v1",
            "scope_id": values["scope_id"],
            "observable_features": {
                key: str(values[key])
                for key in (
                    "price_change",
                    "volume_change",
                    "amount_change",
                    "breadth_change",
                    "participation_change",
                    "concentration",
                    "etf_strength",
                )
            },
            "data_coverage": str(values["data_coverage"]),
            "uncertainty": str(values["uncertainty"]),
            "missing_evidence": list(values["missing_evidence"]),
            "counter_evidence": list(values["counter_evidence"]),
            "reason_codes": list(values["reason_codes"]),
            "lineage": lineage.identity_payload(),
        }
        digest = canonical_hash(identity)
        return cls(
            observation_id=ArtifactId(f"capital-observation:{digest[7:]}"),
            observation_hash=digest,
            **values,
        )


@dataclass(frozen=True, slots=True)
class StatefulCapitalState:
    state_id: ArtifactId
    state_hash: str
    scope_id: str
    previous_state_id: ArtifactId | None
    previous_state: CapitalState | None
    proposed_state: CapitalState
    effective_state: CapitalState
    state_entered_at: datetime
    state_duration_seconds: int
    observation_count: int
    confirmation_count: int
    enter_threshold: Decimal
    exit_threshold: Decimal
    minimum_dwell_seconds: int
    hysteresis: Decimal
    data_coverage: Decimal
    uncertainty: Decimal
    missing_evidence: tuple[str, ...]
    counter_evidence: tuple[str, ...]
    reason_codes: tuple[str, ...]
    observation_id: ArtifactId
    lineage: StateLineage
    transitioned: bool

    def identity_payload(self) -> dict[str, Any]:
        return _state_payload(self)


@dataclass(frozen=True, slots=True)
class CapitalTransition:
    transition_id: ArtifactId
    transition_hash: str
    state_id: ArtifactId
    previous_state_id: ArtifactId | None
    from_state: CapitalState | None
    proposed_state: CapitalState
    to_state: CapitalState
    observation_id: ArtifactId
    transitioned: bool
    reason_codes: tuple[str, ...]
    lineage: StateLineage


@dataclass(frozen=True, slots=True)
class CapitalStateEvaluation:
    observation: CapitalObservation
    state: StatefulCapitalState
    transition: CapitalTransition


def evaluate_capital_state(
    observation: CapitalObservation,
    *,
    previous: StatefulCapitalState | None,
    configuration: CapitalStateConfiguration,
) -> CapitalStateEvaluation:
    _validate_binding(observation, previous, configuration)
    proposed, proposal_reasons = _propose(observation, configuration)
    prior = None if previous is None else previous.effective_state
    entered = observation.lineage.as_of_time if previous is None else previous.state_entered_at
    duration = 0 if previous is None else int((observation.lineage.as_of_time - entered).total_seconds())
    count = 1 if previous is None else previous.observation_count + 1
    reasons = set(observation.reason_codes) | set(proposal_reasons)
    if previous is None:
        effective, confirmation, transitioned = proposed, 1, True
        reasons.add("INITIAL_CAPITAL_PROXY_STATE")
    elif proposed is CapitalState.DATA_INSUFFICIENT:
        effective, confirmation, transitioned = proposed, 1, proposed is not prior
        if transitioned:
            entered = observation.lineage.as_of_time
        reasons.add("CAPITAL_PROXY_FAIL_CLOSED")
    else:
        assert prior is not None
        same = previous.proposed_state is proposed and proposed is not prior
        confirmation = previous.confirmation_count + 1 if same else (1 if proposed is not prior else 0)
        effective, transitioned = prior, False
        if observation.counter_evidence and proposed is not prior:
            reasons.add("CAPITAL_COUNTER_EVIDENCE_BLOCKED")
        elif proposed is prior:
            reasons.add("CAPITAL_HYSTERESIS_RETAINED_STATE")
        elif confirmation < configuration.thresholds.confirmation_count:
            reasons.add("CAPITAL_CONFIRMATION_PENDING")
        elif duration < configuration.thresholds.minimum_dwell_seconds:
            reasons.add("CAPITAL_MINIMUM_DWELL_NOT_MET")
        else:
            effective, transitioned = proposed, True
            entered = observation.lineage.as_of_time
            reasons.add("CAPITAL_STATE_TRANSITION_CONFIRMED")
    ordered_reasons = tuple(sorted(reasons))
    threshold = configuration.thresholds
    prototype = StatefulCapitalState(
        state_id=ArtifactId("pending"),
        state_hash="pending",
        scope_id=observation.scope_id,
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
        data_coverage=observation.data_coverage,
        uncertainty=observation.uncertainty,
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
        state_id=ArtifactId(f"capital-state:{state_hash[7:]}"),
        state_hash=state_hash,
    )
    transition_payload = {
        "schema": "capital_transition/v1",
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
    transition = CapitalTransition(
        transition_id=ArtifactId(f"capital-transition:{transition_hash[7:]}"),
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
    return CapitalStateEvaluation(observation, state, transition)


def _propose(
    value: CapitalObservation,
    configuration: CapitalStateConfiguration,
) -> tuple[CapitalState, tuple[str, ...]]:
    if value.data_coverage < configuration.thresholds.minimum_coverage:
        return CapitalState.DATA_INSUFFICIENT, ("CAPITAL_DATA_COVERAGE_INSUFFICIENT",)
    if (
        value.amount_change >= Decimal("0.50")
        and value.volume_change >= Decimal("0.50")
        and value.breadth_change <= Decimal("-0.30")
        and value.participation_change <= Decimal("-0.30")
        and value.concentration >= Decimal("0.60")
    ):
        return CapitalState.DISTRIBUTION_BIAS, ("DISTRIBUTION_PROXY_PATTERN",)
    if (
        abs(value.price_change) <= Decimal("0.20")
        and value.amount_change >= Decimal("0.50")
        and value.volume_change >= Decimal("0.50")
        and value.concentration >= Decimal("0.60")
    ):
        return CapitalState.ACCUMULATION_BIAS, ("ACCUMULATION_PROXY_PATTERN",)
    expansion_score = sum(
        (
            value.price_change,
            value.volume_change,
            value.amount_change,
            value.breadth_change,
            value.participation_change,
            value.etf_strength,
        ),
        Decimal("0"),
    ) / Decimal("6")
    if expansion_score >= configuration.thresholds.enter_threshold:
        return CapitalState.EXPANSION_BIAS, ("EXPANSION_PROXY_PATTERN",)
    return CapitalState.CONTRACTION_BIAS, ("CONTRACTION_PROXY_PATTERN",)


def _validate_binding(
    observation: CapitalObservation,
    previous: StatefulCapitalState | None,
    configuration: CapitalStateConfiguration,
) -> None:
    lineage = observation.lineage
    if (lineage.model_id, lineage.model_version, lineage.configuration_id, lineage.configuration_hash) != (
        configuration.model_id,
        configuration.model_version,
        configuration.configuration_id,
        configuration.configuration_hash,
    ):
        raise ValueError("Capital observation configuration binding mismatch")
    if previous is not None:
        if previous.scope_id != observation.scope_id:
            raise ValueError("Previous Capital state belongs to another scope")
        if lineage.as_of_time <= previous.lineage.as_of_time:
            raise ValueError("Capital observations must advance As-of Time")


def _state_payload(value: StatefulCapitalState) -> dict[str, Any]:
    return {
        "schema": "capital_state/v1",
        "scope_id": value.scope_id,
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
        "data_coverage": str(value.data_coverage),
        "uncertainty": str(value.uncertainty),
        "missing_evidence": list(value.missing_evidence),
        "counter_evidence": list(value.counter_evidence),
        "reason_codes": list(value.reason_codes),
        "observation_id": str(value.observation_id),
        "lineage": value.lineage.identity_payload(),
        "transitioned": value.transitioned,
    }
