"""Complete Candidate Signal and Target-bound rule Forecast authority."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
import re
from typing import TYPE_CHECKING
from uuid import UUID

from market_regime_alpha.decision_support.domain.context import (
    ContextKind,
    ContextMetricStatus,
    ContextState,
)
from market_regime_alpha.decision_support.domain.vocabulary import (
    CandidateDisposition,
)
from market_regime_alpha.shared.hashing import canonical_json_sha256
from market_regime_alpha.shared.identity import ContentHash
from market_regime_alpha.shared.time import require_utc

if TYPE_CHECKING:
    from market_regime_alpha.decision_support.domain.strategy import (
        StrategyForecastRule,
        StrategyVersionPlan,
    )


_REQUEST = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}$")


class SignalStatus(StrEnum):
    PRESENT = "PRESENT"
    NO_SIGNAL = "NO_SIGNAL"
    WAIT = "WAIT"
    UNKNOWN = "UNKNOWN"
    NOT_ESTIMABLE = "NOT_ESTIMABLE"


class ForecastStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    NOT_ESTIMABLE = "NOT_ESTIMABLE"


class ForecastCalibrationStatus(StrEnum):
    UNCALIBRATED = "UNCALIBRATED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


def _sha(value: str, label: str) -> str:
    try:
        return str(ContentHash(value))
    except ValueError as exc:
        raise ValueError(f"{label} must be a lowercase SHA-256") from exc


@dataclass(frozen=True, slots=True)
class PreparedSignalContext:
    strategy_context_requirement_id: UUID
    context_assessment_id: UUID
    assessment_group_id: UUID
    context_kind: ContextKind
    assessment_status: ContextMetricStatus
    assessment_state: ContextState
    assessment_content_sha256: str
    recorded_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.context_kind, ContextKind):
            raise TypeError("Signal Context kind must be typed")
        if not isinstance(self.assessment_status, ContextMetricStatus):
            raise TypeError("Signal Context status must be typed")
        if not isinstance(self.assessment_state, ContextState):
            raise TypeError("Signal Context state must be typed")
        object.__setattr__(
            self,
            "assessment_content_sha256",
            _sha(self.assessment_content_sha256, "ContextAssessment hash"),
        )
        object.__setattr__(
            self,
            "recorded_at",
            require_utc(self.recorded_at, field="ContextAssessment recorded_at"),
        )


@dataclass(frozen=True, slots=True)
class PreparedSignalCandidate:
    candidate_id: UUID
    instrument_id: UUID
    disposition: CandidateDisposition
    composite_score: Decimal | None
    contexts: tuple[PreparedSignalContext, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.disposition, CandidateDisposition):
            raise TypeError("Signal Candidate disposition must be typed")
        if self.disposition is CandidateDisposition.UNRANKABLE:
            if self.composite_score is not None:
                raise ValueError("unrankable Candidate cannot have a score")
        elif (
            self.composite_score is None
            or not self.composite_score.is_finite()
            or not Decimal("0") <= self.composite_score <= Decimal("1")
        ):
            raise ValueError("rankable Candidate requires a finite descriptive score")
        if not self.contexts:
            raise ValueError("Signal Candidate Context roster must be non-empty")
        requirements = tuple(
            item.strategy_context_requirement_id for item in self.contexts
        )
        kinds = tuple(item.context_kind for item in self.contexts)
        if len(set(requirements)) != len(requirements) or len(set(kinds)) != len(kinds):
            raise ValueError("Signal Candidate Context roster contains a duplicate")


@dataclass(frozen=True, slots=True)
class PreparedSignalInputs:
    decision_run_id: UUID
    candidate_set_id: UUID
    candidate_roster_sha256: str
    decision_time: datetime
    strategy_version: StrategyVersionPlan
    candidates: tuple[PreparedSignalCandidate, ...]

    def __post_init__(self) -> None:
        from market_regime_alpha.decision_support.domain.strategy import (
            StrategyVersionPlan,
        )

        if not isinstance(self.strategy_version, StrategyVersionPlan):
            raise TypeError("Signal StrategyVersion must be typed")
        object.__setattr__(
            self,
            "candidate_roster_sha256",
            _sha(self.candidate_roster_sha256, "Candidate roster hash"),
        )
        object.__setattr__(
            self,
            "decision_time",
            require_utc(self.decision_time, field="DecisionTime"),
        )
        candidate_ids = tuple(item.candidate_id for item in self.candidates)
        if len(set(candidate_ids)) != len(candidate_ids):
            raise ValueError("Signal Candidate roster contains a duplicate")
        expected = tuple(
            item.strategy_context_requirement_id
            for item in self.strategy_version.context_requirements
        )
        expected_group: tuple[UUID, ...] | None = None
        for candidate in self.candidates:
            actual = tuple(
                item.strategy_context_requirement_id for item in candidate.contexts
            )
            if actual != expected:
                raise ValueError("Signal requires the complete Context roster")
            groups = tuple(item.assessment_group_id for item in candidate.contexts)
            if len(set(groups)) != 1:
                raise ValueError("Signal Context roster must share one assessment group")
            context_identity = tuple(
                item.context_assessment_id for item in candidate.contexts
            )
            if expected_group is None:
                expected_group = context_identity
            elif context_identity != expected_group:
                raise ValueError("Signal Candidates must bind the same Context Authority")


@dataclass(frozen=True, slots=True)
class SignalContextBindingPlan:
    signal_context_binding_id: UUID
    context: PreparedSignalContext
    content_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "content_sha256",
            canonical_json_sha256(
                {
                    "context_assessment_id": self.context.context_assessment_id,
                    "context_assessment_sha256": (
                        self.context.assessment_content_sha256
                    ),
                    "signal_context_binding_id": self.signal_context_binding_id,
                    "strategy_context_requirement_id": (
                        self.context.strategy_context_requirement_id
                    ),
                }
            ),
        )


@dataclass(frozen=True, slots=True)
class SignalPlan:
    signal_id: UUID
    ordinal: int
    candidate: PreparedSignalCandidate
    status: SignalStatus
    reason_code: str
    context_binding_roster_sha256: str
    context_bindings: tuple[SignalContextBindingPlan, ...]
    content_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "context_binding_roster_sha256",
            _sha(self.context_binding_roster_sha256, "Signal Context roster hash"),
        )
        object.__setattr__(
            self,
            "content_sha256",
            canonical_json_sha256(
                {
                    "candidate_id": self.candidate.candidate_id,
                    "candidate_score": self.candidate.composite_score,
                    "context_binding_count": len(self.context_bindings),
                    "context_binding_roster_sha256": (
                        self.context_binding_roster_sha256
                    ),
                    "ordinal": self.ordinal,
                    "reason_code": self.reason_code,
                    "signal_id": self.signal_id,
                    "status": self.status,
                }
            ),
        )


@dataclass(frozen=True, slots=True)
class SignalAuthority:
    signal_group_id: UUID
    decision_run_id: UUID
    candidate_set_id: UUID
    candidate_roster_sha256: str
    decision_time: datetime
    strategy_version: StrategyVersionPlan
    request_identity: str
    request_sha256: str
    command_receipt_id: UUID
    recorded_at: datetime
    signal_count: int
    context_binding_count: int
    signal_roster_sha256: str
    signals: tuple[SignalPlan, ...]
    content_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "signal_roster_sha256",
            _sha(self.signal_roster_sha256, "Signal roster hash"),
        )
        object.__setattr__(
            self,
            "content_sha256",
            canonical_json_sha256(
                {
                    "candidate_roster_sha256": self.candidate_roster_sha256,
                    "candidate_set_id": self.candidate_set_id,
                    "context_binding_count": self.context_binding_count,
                    "decision_run_id": self.decision_run_id,
                    "decision_time": self.decision_time,
                    "request_identity": self.request_identity,
                    "request_sha256": self.request_sha256,
                    "signal_count": self.signal_count,
                    "signal_group_id": self.signal_group_id,
                    "signal_roster_sha256": self.signal_roster_sha256,
                    "strategy_version_sha256": self.strategy_version.content_sha256,
                }
            ),
        )


def _missing_status(candidate: PreparedSignalCandidate, requirements) -> SignalStatus | None:
    from market_regime_alpha.decision_support.domain.strategy import (
        ContextFailureAction,
    )

    priority = {
        SignalStatus.UNKNOWN: 1,
        SignalStatus.WAIT: 2,
        SignalStatus.NOT_ESTIMABLE: 3,
    }
    result: SignalStatus | None = None
    for context, requirement in zip(candidate.contexts, requirements, strict=True):
        if context.assessment_status is ContextMetricStatus.AVAILABLE:
            continue
        mapped = {
            ContextFailureAction.UNKNOWN: SignalStatus.UNKNOWN,
            ContextFailureAction.WAIT: SignalStatus.WAIT,
            ContextFailureAction.NOT_ESTIMABLE: SignalStatus.NOT_ESTIMABLE,
        }[requirement.missing_action]
        if result is None or priority[mapped] > priority[result]:
            result = mapped
    return result


def build_signal_authority(
    *,
    signal_group_id: UUID,
    prepared: PreparedSignalInputs,
    request_identity: str,
    request_sha256: str,
    command_receipt_id: UUID,
    recorded_at: datetime,
    signal_id_factory: Callable[[PreparedSignalCandidate, int], UUID],
    binding_id_factory: Callable[[PreparedSignalCandidate, PreparedSignalContext], UUID],
) -> SignalAuthority:
    if not _REQUEST.fullmatch(request_identity):
        raise ValueError("Signal request identity is invalid")
    request_sha256 = _sha(request_sha256, "Signal request hash")
    recorded_at = require_utc(recorded_at, field="Signal recorded_at")
    if recorded_at <= prepared.decision_time:
        raise ValueError("Signal must be recorded after DecisionTime")
    rule = prepared.strategy_version.signal_rule
    signals: list[SignalPlan] = []
    for ordinal, candidate in enumerate(prepared.candidates, start=1):
        bindings = tuple(
            SignalContextBindingPlan(
                signal_context_binding_id=binding_id_factory(candidate, context),
                context=context,
            )
            for context in candidate.contexts
        )
        binding_hash = canonical_json_sha256(
            tuple(
                {
                    "content_sha256": binding.content_sha256,
                    "ordinal": binding_ordinal,
                    "signal_context_binding_id": (
                        binding.signal_context_binding_id
                    ),
                }
                for binding_ordinal, binding in enumerate(bindings, start=1)
            )
        )
        missing = _missing_status(
            candidate,
            prepared.strategy_version.context_requirements,
        )
        if candidate.disposition is not rule.eligible_disposition:
            status = rule.ineligible_status
            reason = "CANDIDATE_INELIGIBLE"
        elif missing is not None:
            status = missing
            reason = f"CONTEXT_{missing.value}"
        elif all(
            context.assessment_state is requirement.required_state
            for context, requirement in zip(
                candidate.contexts,
                prepared.strategy_version.context_requirements,
                strict=True,
            )
        ):
            status = rule.positive_status
            reason = "CONTEXT_REQUIREMENTS_SATISFIED"
        else:
            status = rule.negative_status
            reason = "CONTEXT_REQUIREMENTS_NOT_SATISFIED"
        signals.append(
            SignalPlan(
                signal_id=signal_id_factory(candidate, ordinal),
                ordinal=ordinal,
                candidate=candidate,
                status=status,
                reason_code=reason,
                context_binding_roster_sha256=binding_hash,
                context_bindings=bindings,
            )
        )
    signal_tuple = tuple(signals)
    roster_hash = canonical_json_sha256(
        tuple(
            {
                "content_sha256": signal.content_sha256,
                "ordinal": signal.ordinal,
                "signal_id": signal.signal_id,
            }
            for signal in signal_tuple
        )
    )
    return SignalAuthority(
        signal_group_id=signal_group_id,
        decision_run_id=prepared.decision_run_id,
        candidate_set_id=prepared.candidate_set_id,
        candidate_roster_sha256=prepared.candidate_roster_sha256,
        decision_time=prepared.decision_time,
        strategy_version=prepared.strategy_version,
        request_identity=request_identity,
        request_sha256=request_sha256,
        command_receipt_id=command_receipt_id,
        recorded_at=recorded_at,
        signal_count=len(signal_tuple),
        context_binding_count=sum(len(item.context_bindings) for item in signal_tuple),
        signal_roster_sha256=roster_hash,
        signals=signal_tuple,
    )


@dataclass(frozen=True, slots=True)
class PreparedForecastCommitment:
    commitment_id: UUID
    candidate_id: UUID
    instrument_id: UUID
    target_definition_id: UUID
    target_definition_sha256: str
    target_checkpoint_id: UUID
    target_checkpoint_sha256: str
    commitment_content_sha256: str

    def __post_init__(self) -> None:
        for name in (
            "target_definition_sha256",
            "target_checkpoint_sha256",
            "commitment_content_sha256",
        ):
            object.__setattr__(self, name, _sha(getattr(self, name), name))


@dataclass(frozen=True, slots=True)
class PreparedForecastInputs:
    decision_run_id: UUID
    strategy_version: StrategyVersionPlan
    signal_authority: SignalAuthority
    commitments: tuple[PreparedForecastCommitment, ...]

    def __post_init__(self) -> None:
        if self.signal_authority.decision_run_id != self.decision_run_id:
            raise ValueError("Forecast Signal belongs to a different DecisionRun")
        if self.signal_authority.strategy_version != self.strategy_version:
            raise ValueError("Forecast Signal belongs to a different StrategyVersion")
        targets = tuple(
            dict.fromkeys(
                rule.target_definition_id
                for rule in self.strategy_version.forecast_rules
            )
        )
        expected = {
            (signal.candidate.candidate_id, target_id)
            for signal in self.signal_authority.signals
            for target_id in targets
        }
        actual = {
            (item.candidate_id, item.target_definition_id)
            for item in self.commitments
        }
        if len(actual) != len(self.commitments) or actual != expected:
            raise ValueError("Forecast requires the complete commitment roster")
        for commitment in self.commitments:
            rules = tuple(
                rule
                for rule in self.strategy_version.forecast_rules
                if rule.target_definition_id == commitment.target_definition_id
            )
            if not rules or any(
                rule.target_definition_sha256 != commitment.target_definition_sha256
                or rule.target_checkpoint_id != commitment.target_checkpoint_id
                or rule.target_checkpoint_sha256 != commitment.target_checkpoint_sha256
                for rule in rules
            ):
                raise ValueError("Forecast commitment Target binding is not exact")


@dataclass(frozen=True, slots=True)
class PreparedInferenceInputs:
    signal_inputs: PreparedSignalInputs
    commitments: tuple[PreparedForecastCommitment, ...]

    def __post_init__(self) -> None:
        candidate_ids = {
            candidate.candidate_id for candidate in self.signal_inputs.candidates
        }
        if {
            commitment.candidate_id for commitment in self.commitments
        } != candidate_ids:
            raise ValueError("Inference requires commitments for every Candidate")


@dataclass(frozen=True, slots=True)
class ForecastEstimatePlan:
    forecast_estimate_id: UUID
    rule: StrategyForecastRule
    point_estimate: Decimal | None
    lower_bound: Decimal | None
    upper_bound: Decimal | None
    content_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "content_sha256",
            canonical_json_sha256(
                {
                    "forecast_estimate_id": self.forecast_estimate_id,
                    "lower_bound": self.lower_bound,
                    "point_estimate": self.point_estimate,
                    "strategy_forecast_rule_id": (
                        self.rule.strategy_forecast_rule_id
                    ),
                    "target_metric_definition_id": (
                        self.rule.target_metric_definition_id
                    ),
                    "upper_bound": self.upper_bound,
                }
            ),
        )


@dataclass(frozen=True, slots=True)
class ForecastPlan:
    forecast_id: UUID
    ordinal: int
    signal: SignalPlan
    commitment: PreparedForecastCommitment
    status: ForecastStatus
    calibration_status: ForecastCalibrationStatus
    reason_code: str
    estimate_roster_sha256: str
    estimates: tuple[ForecastEstimatePlan, ...]
    content_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "estimate_roster_sha256",
            _sha(self.estimate_roster_sha256, "Forecast estimate roster hash"),
        )
        object.__setattr__(
            self,
            "content_sha256",
            canonical_json_sha256(
                {
                    "calibration_status": self.calibration_status,
                    "commitment_content_sha256": (
                        self.commitment.commitment_content_sha256
                    ),
                    "commitment_id": self.commitment.commitment_id,
                    "estimate_count": len(self.estimates),
                    "estimate_roster_sha256": self.estimate_roster_sha256,
                    "forecast_id": self.forecast_id,
                    "ordinal": self.ordinal,
                    "reason_code": self.reason_code,
                    "signal_content_sha256": self.signal.content_sha256,
                    "signal_id": self.signal.signal_id,
                    "status": self.status,
                }
            ),
        )


@dataclass(frozen=True, slots=True)
class ForecastAuthority:
    forecast_group_id: UUID
    decision_run_id: UUID
    strategy_version: StrategyVersionPlan
    signal_group_id: UUID
    request_identity: str
    request_sha256: str
    command_receipt_id: UUID
    recorded_at: datetime
    forecast_count: int
    estimate_count: int
    forecast_roster_sha256: str
    forecasts: tuple[ForecastPlan, ...]
    content_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "forecast_roster_sha256",
            _sha(self.forecast_roster_sha256, "Forecast roster hash"),
        )
        object.__setattr__(
            self,
            "content_sha256",
            canonical_json_sha256(
                {
                    "decision_run_id": self.decision_run_id,
                    "estimate_count": self.estimate_count,
                    "forecast_count": self.forecast_count,
                    "forecast_group_id": self.forecast_group_id,
                    "forecast_roster_sha256": self.forecast_roster_sha256,
                    "request_identity": self.request_identity,
                    "request_sha256": self.request_sha256,
                    "signal_group_id": self.signal_group_id,
                    "strategy_version_sha256": self.strategy_version.content_sha256,
                }
            ),
        )


def build_forecast_authority(
    *,
    forecast_group_id: UUID,
    prepared: PreparedForecastInputs,
    request_identity: str,
    request_sha256: str,
    command_receipt_id: UUID,
    recorded_at: datetime,
    forecast_id_factory: Callable[[SignalPlan, PreparedForecastCommitment], UUID],
    estimate_id_factory: Callable[[StrategyForecastRule, ForecastPlan], UUID],
) -> ForecastAuthority:
    if not _REQUEST.fullmatch(request_identity):
        raise ValueError("Forecast request identity is invalid")
    request_sha256 = _sha(request_sha256, "Forecast request hash")
    recorded_at = require_utc(recorded_at, field="Forecast recorded_at")
    forecasts: list[ForecastPlan] = []
    for signal in prepared.signal_authority.signals:
        for commitment in prepared.commitments:
            if commitment.candidate_id != signal.candidate.candidate_id:
                continue
            rules = tuple(
                rule
                for rule in prepared.strategy_version.forecast_rules
                if rule.target_definition_id == commitment.target_definition_id
            )
            available = (
                signal.status is SignalStatus.PRESENT
                and signal.candidate.composite_score is not None
            )
            provisional = ForecastPlan(
                forecast_id=forecast_id_factory(signal, commitment),
                ordinal=len(forecasts) + 1,
                signal=signal,
                commitment=commitment,
                status=(
                    ForecastStatus.AVAILABLE
                    if available
                    else ForecastStatus.NOT_APPLICABLE
                ),
                calibration_status=(
                    ForecastCalibrationStatus.UNCALIBRATED
                    if available
                    else ForecastCalibrationStatus.NOT_APPLICABLE
                ),
                reason_code=(
                    "RULE_ESTIMATE_AVAILABLE"
                    if available
                    else "SIGNAL_NOT_PRESENT"
                ),
                estimate_roster_sha256="0" * 64,
                estimates=(),
            )
            estimates = tuple(
                _estimate(rule, provisional, available, estimate_id_factory)
                for rule in rules
            )
            estimate_hash = canonical_json_sha256(
                tuple(
                    {
                        "content_sha256": estimate.content_sha256,
                        "forecast_estimate_id": estimate.forecast_estimate_id,
                        "ordinal": ordinal,
                    }
                    for ordinal, estimate in enumerate(estimates, start=1)
                )
            )
            forecasts.append(
                ForecastPlan(
                    forecast_id=provisional.forecast_id,
                    ordinal=provisional.ordinal,
                    signal=signal,
                    commitment=commitment,
                    status=provisional.status,
                    calibration_status=provisional.calibration_status,
                    reason_code=provisional.reason_code,
                    estimate_roster_sha256=estimate_hash,
                    estimates=estimates,
                )
            )
    forecast_tuple = tuple(forecasts)
    roster_hash = canonical_json_sha256(
        tuple(
            {
                "content_sha256": forecast.content_sha256,
                "forecast_id": forecast.forecast_id,
                "ordinal": forecast.ordinal,
            }
            for forecast in forecast_tuple
        )
    )
    return ForecastAuthority(
        forecast_group_id=forecast_group_id,
        decision_run_id=prepared.decision_run_id,
        strategy_version=prepared.strategy_version,
        signal_group_id=prepared.signal_authority.signal_group_id,
        request_identity=request_identity,
        request_sha256=request_sha256,
        command_receipt_id=command_receipt_id,
        recorded_at=recorded_at,
        forecast_count=len(forecast_tuple),
        estimate_count=sum(len(item.estimates) for item in forecast_tuple),
        forecast_roster_sha256=roster_hash,
        forecasts=forecast_tuple,
    )


def _estimate(rule, forecast, available, factory) -> ForecastEstimatePlan:
    if available:
        assert forecast.signal.candidate.composite_score is not None
        point = (
            forecast.signal.candidate.composite_score * rule.coefficient
            + rule.intercept
        )
        lower = point - rule.lower_offset
        upper = point + rule.upper_offset
    else:
        point = lower = upper = None
    return ForecastEstimatePlan(
        forecast_estimate_id=factory(rule, forecast),
        rule=rule,
        point_estimate=point,
        lower_bound=lower,
        upper_bound=upper,
    )


__all__ = [
    "ForecastAuthority",
    "ForecastCalibrationStatus",
    "ForecastEstimatePlan",
    "ForecastPlan",
    "ForecastStatus",
    "PreparedForecastCommitment",
    "PreparedForecastInputs",
    "PreparedInferenceInputs",
    "PreparedSignalCandidate",
    "PreparedSignalContext",
    "PreparedSignalInputs",
    "SignalAuthority",
    "SignalContextBindingPlan",
    "SignalPlan",
    "SignalStatus",
    "build_forecast_authority",
    "build_signal_authority",
]
