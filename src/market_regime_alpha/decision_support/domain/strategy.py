"""Immutable Strategy and StrategyVersion definition authority."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
import re
from typing import TYPE_CHECKING
from uuid import UUID

from market_regime_alpha.decision_support.domain.context import (
    ContextKind,
    ContextState,
    DecisionArtifactBinding,
)
from market_regime_alpha.decision_support.domain.vocabulary import (
    CandidateDisposition,
)
from market_regime_alpha.shared.hashing import canonical_json_sha256
from market_regime_alpha.shared.identity import ContentHash

if TYPE_CHECKING:
    from market_regime_alpha.decision_support.domain.inference import SignalStatus


_CODE = re.compile(r"^[a-z][a-z0-9_.-]{0,99}$")


class StrategyActionPolicy(StrEnum):
    LONG_ONLY_RESEARCH = "LONG_ONLY_RESEARCH"


class ContextFailureAction(StrEnum):
    WAIT = "WAIT"
    UNKNOWN = "UNKNOWN"
    NOT_ESTIMABLE = "NOT_ESTIMABLE"
    OBSERVE_ONLY = "OBSERVE_ONLY"


class ForecastSourceMeasure(StrEnum):
    CANDIDATE_COMPOSITE_SCORE = "CANDIDATE_COMPOSITE_SCORE"


def _sha(value: str, label: str) -> str:
    try:
        return str(ContentHash(value))
    except ValueError as exc:
        raise ValueError(f"{label} must be a lowercase SHA-256") from exc


def _finite(value: Decimal, label: str) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError(f"{label} must be a finite Decimal")
    return value


@dataclass(frozen=True, slots=True)
class StrategyPlan:
    strategy_id: UUID
    strategy_code: str
    objective: str
    content_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        if not _CODE.fullmatch(self.strategy_code):
            raise ValueError("Strategy code is invalid")
        if not self.objective.strip() or len(self.objective) > 500:
            raise ValueError("Strategy objective is invalid")
        object.__setattr__(
            self,
            "content_sha256",
            canonical_json_sha256(
                {
                    "objective": self.objective,
                    "strategy_code": self.strategy_code,
                    "strategy_id": self.strategy_id,
                }
            ),
        )


@dataclass(frozen=True, slots=True)
class StrategyContextRequirement:
    strategy_context_requirement_id: UUID
    strategy_version_id: UUID
    ordinal: int
    context_policy_id: UUID
    context_policy_content_sha256: str
    context_kind: ContextKind
    required_state: ContextState
    missing_action: ContextFailureAction
    content_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        if isinstance(self.ordinal, bool) or self.ordinal < 1:
            raise ValueError("Strategy Context ordinal must be positive")
        if not isinstance(self.context_kind, ContextKind):
            raise TypeError("Strategy Context kind must be typed")
        object.__setattr__(
            self,
            "context_policy_content_sha256",
            _sha(self.context_policy_content_sha256, "ContextPolicy hash"),
        )
        if self.required_state not in {
            ContextState.POSITIVE,
            ContextState.NEUTRAL,
            ContextState.NEGATIVE,
        }:
            raise ValueError("Strategy required Context state must be estimable")
        if not isinstance(self.missing_action, ContextFailureAction):
            raise TypeError("Strategy Context missing action must be typed")
        object.__setattr__(
            self,
            "content_sha256",
            canonical_json_sha256(
                {
                    "context_kind": self.context_kind,
                    "context_policy_content_sha256": (
                        self.context_policy_content_sha256
                    ),
                    "context_policy_id": self.context_policy_id,
                    "missing_action": self.missing_action,
                    "ordinal": self.ordinal,
                    "required_state": self.required_state,
                    "strategy_context_requirement_id": (
                        self.strategy_context_requirement_id
                    ),
                    "strategy_version_id": self.strategy_version_id,
                }
            ),
        )


@dataclass(frozen=True, slots=True)
class StrategySignalRule:
    strategy_signal_rule_id: UUID
    strategy_version_id: UUID
    eligible_disposition: CandidateDisposition
    positive_status: SignalStatus
    negative_status: SignalStatus
    ineligible_status: SignalStatus
    content_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        from market_regime_alpha.decision_support.domain.inference import SignalStatus

        if not isinstance(self.eligible_disposition, CandidateDisposition):
            raise TypeError("Signal eligible disposition must be typed")
        if self.positive_status is not SignalStatus.PRESENT:
            raise ValueError("positive Signal status must be PRESENT")
        if self.negative_status is not SignalStatus.NO_SIGNAL:
            raise ValueError("negative Signal status must be NO_SIGNAL")
        if self.ineligible_status is not SignalStatus.NO_SIGNAL:
            raise ValueError("ineligible Signal status must be NO_SIGNAL")
        object.__setattr__(
            self,
            "content_sha256",
            canonical_json_sha256(
                {
                    "eligible_disposition": self.eligible_disposition,
                    "ineligible_status": self.ineligible_status,
                    "negative_status": self.negative_status,
                    "positive_status": self.positive_status,
                    "strategy_signal_rule_id": self.strategy_signal_rule_id,
                    "strategy_version_id": self.strategy_version_id,
                }
            ),
        )


@dataclass(frozen=True, slots=True)
class StrategyForecastRule:
    strategy_forecast_rule_id: UUID
    strategy_version_id: UUID
    ordinal: int
    target_definition_id: UUID
    target_definition_sha256: str
    target_checkpoint_id: UUID
    target_checkpoint_sha256: str
    target_metric_definition_id: UUID
    target_metric_definition_sha256: str
    source_measure: ForecastSourceMeasure
    coefficient: Decimal
    intercept: Decimal
    lower_offset: Decimal
    upper_offset: Decimal
    value_unit: str
    content_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        if isinstance(self.ordinal, bool) or self.ordinal < 1:
            raise ValueError("Strategy Forecast ordinal must be positive")
        if len(
            {
                self.target_definition_id,
                self.target_checkpoint_id,
                self.target_metric_definition_id,
            }
        ) != 3:
            raise ValueError("Target definition/checkpoint/metric identities conflict")
        for name in (
            "target_definition_sha256",
            "target_checkpoint_sha256",
            "target_metric_definition_sha256",
        ):
            object.__setattr__(self, name, _sha(getattr(self, name), name))
        if not isinstance(self.source_measure, ForecastSourceMeasure):
            raise TypeError("Forecast source measure must be typed")
        for name in ("coefficient", "intercept", "lower_offset", "upper_offset"):
            _finite(getattr(self, name), f"Forecast {name}")
        if self.lower_offset < 0 or self.upper_offset < 0:
            raise ValueError("Forecast offset must be non-negative")
        if self.value_unit != "DECIMAL_RETURN":
            raise ValueError("Forecast value unit must be DECIMAL_RETURN")
        object.__setattr__(
            self,
            "content_sha256",
            canonical_json_sha256(
                {
                    "coefficient": self.coefficient,
                    "intercept": self.intercept,
                    "lower_offset": self.lower_offset,
                    "ordinal": self.ordinal,
                    "source_measure": self.source_measure,
                    "strategy_forecast_rule_id": self.strategy_forecast_rule_id,
                    "strategy_version_id": self.strategy_version_id,
                    "target_checkpoint_id": self.target_checkpoint_id,
                    "target_checkpoint_sha256": self.target_checkpoint_sha256,
                    "target_definition_id": self.target_definition_id,
                    "target_definition_sha256": self.target_definition_sha256,
                    "target_metric_definition_id": (
                        self.target_metric_definition_id
                    ),
                    "target_metric_definition_sha256": (
                        self.target_metric_definition_sha256
                    ),
                    "upper_offset": self.upper_offset,
                    "value_unit": self.value_unit,
                }
            ),
        )


@dataclass(frozen=True, slots=True)
class StrategyVersionPlan:
    strategy: StrategyPlan
    strategy_version_id: UUID
    version: int
    supersedes_strategy_version_id: UUID | None
    primary_change: str
    action_policy: StrategyActionPolicy
    context_requirements: tuple[StrategyContextRequirement, ...]
    signal_rule: StrategySignalRule
    forecast_rules: tuple[StrategyForecastRule, ...]
    code_artifact: DecisionArtifactBinding
    config_artifact: DecisionArtifactBinding
    provenance_sha256: str
    context_requirement_count: int = field(init=False)
    forecast_rule_count: int = field(init=False)
    context_requirement_roster_sha256: str = field(init=False)
    forecast_rule_roster_sha256: str = field(init=False)
    content_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        if isinstance(self.version, bool) or self.version < 1:
            raise ValueError("StrategyVersion version must be positive")
        if (self.version == 1) != (self.supersedes_strategy_version_id is None):
            raise ValueError("StrategyVersion predecessor shape is invalid")
        if not self.primary_change.strip() or len(self.primary_change) > 500:
            raise ValueError("StrategyVersion primary change is invalid")
        if not isinstance(self.action_policy, StrategyActionPolicy):
            raise TypeError("Strategy action policy must be typed")
        self._validate_roster(
            self.context_requirements,
            "Context requirement",
            lambda item: item.strategy_context_requirement_id,
        )
        kinds = tuple(item.context_kind for item in self.context_requirements)
        if len(set(kinds)) != len(kinds):
            raise ValueError("Strategy Context roster contains a duplicate kind")
        self._validate_roster(
            self.forecast_rules,
            "Forecast rule",
            lambda item: item.strategy_forecast_rule_id,
        )
        target_metrics = tuple(
            (item.target_definition_id, item.target_metric_definition_id)
            for item in self.forecast_rules
        )
        if len(set(target_metrics)) != len(target_metrics):
            raise ValueError("Strategy Forecast roster contains a duplicate Target metric")
        if (
            any(
                item.strategy_version_id != self.strategy_version_id
                for item in self.context_requirements
            )
            or any(
                item.strategy_version_id != self.strategy_version_id
                for item in self.forecast_rules
            )
            or self.signal_rule.strategy_version_id != self.strategy_version_id
        ):
            raise ValueError("Strategy child belongs to a different version")
        provenance = _sha(self.provenance_sha256, "Strategy provenance")
        object.__setattr__(self, "provenance_sha256", provenance)
        context_hash = canonical_json_sha256(
            tuple(
                {
                    "content_sha256": item.content_sha256,
                    "ordinal": item.ordinal,
                    "strategy_context_requirement_id": (
                        item.strategy_context_requirement_id
                    ),
                }
                for item in self.context_requirements
            )
        )
        forecast_hash = canonical_json_sha256(
            tuple(
                {
                    "content_sha256": item.content_sha256,
                    "ordinal": item.ordinal,
                    "strategy_forecast_rule_id": item.strategy_forecast_rule_id,
                }
                for item in self.forecast_rules
            )
        )
        object.__setattr__(
            self, "context_requirement_count", len(self.context_requirements)
        )
        object.__setattr__(self, "forecast_rule_count", len(self.forecast_rules))
        object.__setattr__(
            self, "context_requirement_roster_sha256", context_hash
        )
        object.__setattr__(self, "forecast_rule_roster_sha256", forecast_hash)
        object.__setattr__(
            self,
            "content_sha256",
            canonical_json_sha256(
                {
                    "action_policy": self.action_policy,
                    "code_artifact": self.code_artifact,
                    "config_artifact": self.config_artifact,
                    "context_requirement_count": len(self.context_requirements),
                    "context_requirement_roster_sha256": context_hash,
                    "forecast_rule_count": len(self.forecast_rules),
                    "forecast_rule_roster_sha256": forecast_hash,
                    "primary_change": self.primary_change,
                    "provenance_sha256": provenance,
                    "signal_rule_sha256": self.signal_rule.content_sha256,
                    "strategy_content_sha256": self.strategy.content_sha256,
                    "strategy_id": self.strategy.strategy_id,
                    "strategy_version_id": self.strategy_version_id,
                    "supersedes_strategy_version_id": (
                        self.supersedes_strategy_version_id
                    ),
                    "version": self.version,
                }
            ),
        )

    def _validate_roster(self, items, label: str, identity) -> None:
        if not items:
            raise ValueError(f"Strategy {label} roster must be non-empty")
        if tuple(item.ordinal for item in items) != tuple(range(1, len(items) + 1)):
            raise ValueError(f"Strategy {label} ordinals must be contiguous")
        identities = tuple(identity(item) for item in items)
        if len(set(identities)) != len(identities):
            raise ValueError(f"Strategy {label} roster contains a duplicate")


__all__ = [
    "ContextFailureAction",
    "ForecastSourceMeasure",
    "StrategyActionPolicy",
    "StrategyContextRequirement",
    "StrategyForecastRule",
    "StrategyPlan",
    "StrategySignalRule",
    "StrategyVersionPlan",
]
