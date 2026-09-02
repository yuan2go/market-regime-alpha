"""Complete Opportunity roster and falsifiable Thesis authority."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
import re
from uuid import UUID

from market_regime_alpha.decision_support.domain.context import DecisionArtifactBinding
from market_regime_alpha.decision_support.domain.inference import (
    ForecastCalibrationStatus,
    ForecastStatus,
    SignalStatus,
)
from market_regime_alpha.shared.hashing import canonical_json_sha256
from market_regime_alpha.shared.identity import ContentHash
from market_regime_alpha.shared.time import require_utc


_REQUEST = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}$")
_CODE = re.compile(r"^[a-z][a-z0-9_.-]{0,99}$")


class OpportunityStatus(StrEnum):
    ACTIONABLE = "ACTIONABLE"
    NO_ACTION = "NO_ACTION"
    WAIT = "WAIT"
    NOT_ESTIMABLE = "NOT_ESTIMABLE"


class DecisionAction(StrEnum):
    ENTER = "ENTER"
    NO_ACTION = "NO_ACTION"
    WAIT = "WAIT"
    DATA_INSUFFICIENT = "DATA_INSUFFICIENT"


class ThesisConditionKind(StrEnum):
    ENTRY = "ENTRY"
    HOLD = "HOLD"
    INVALIDATE = "INVALIDATE"
    REDUCE = "REDUCE"
    EXIT = "EXIT"


class ThesisConditionSource(StrEnum):
    CONTEXT = "CONTEXT"
    SIGNAL = "SIGNAL"
    FORECAST = "FORECAST"
    OPPORTUNITY = "OPPORTUNITY"


class ThesisConditionOperator(StrEnum):
    EQUALS = "EQUALS"
    AT_LEAST = "AT_LEAST"
    AT_MOST = "AT_MOST"


class ThesisMissingAction(StrEnum):
    WAIT = "WAIT"
    INVALIDATE = "INVALIDATE"
    DATA_INSUFFICIENT = "DATA_INSUFFICIENT"


def _sha(value: str, label: str) -> str:
    try:
        return str(ContentHash(value))
    except ValueError as exc:
        raise ValueError(f"{label} must be a lowercase SHA-256") from exc


@dataclass(frozen=True, slots=True)
class PreparedOpportunityContext:
    signal_context_binding_id: UUID
    strategy_context_requirement_id: UUID
    context_assessment_id: UUID
    context_kind: str
    content_sha256: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "content_sha256", _sha(self.content_sha256, "Context binding hash"))


@dataclass(frozen=True, slots=True)
class PreparedOpportunityInput:
    forecast_id: UUID
    forecast_ordinal: int
    forecast_content_sha256: str
    forecast_status: ForecastStatus
    calibration_status: ForecastCalibrationStatus
    signal_id: UUID
    signal_content_sha256: str
    signal_status: SignalStatus
    candidate_id: UUID
    instrument_id: UUID
    commitment_id: UUID
    commitment_content_sha256: str
    target_definition_id: UUID
    target_definition_sha256: str
    contexts: tuple[PreparedOpportunityContext, ...]

    def __post_init__(self) -> None:
        if isinstance(self.forecast_ordinal, bool) or self.forecast_ordinal < 1:
            raise ValueError("Opportunity input ordinal must be positive")
        for name in (
            "forecast_content_sha256",
            "signal_content_sha256",
            "commitment_content_sha256",
            "target_definition_sha256",
        ):
            object.__setattr__(self, name, _sha(getattr(self, name), name))
        if not self.contexts:
            raise ValueError("Opportunity requires complete Context bindings")
        requirements = tuple(item.strategy_context_requirement_id for item in self.contexts)
        if len(set(requirements)) != len(requirements):
            raise ValueError("Opportunity Context roster contains a duplicate")


@dataclass(frozen=True, slots=True)
class PreparedOpportunityInputs:
    decision_run_id: UUID
    strategy_version_id: UUID
    strategy_version_sha256: str
    signal_group_id: UUID
    signal_content_sha256: str
    forecast_group_id: UUID
    forecast_content_sha256: str
    forecast_recorded_at: datetime
    items: tuple[PreparedOpportunityInput, ...]

    def __post_init__(self) -> None:
        for name in (
            "strategy_version_sha256",
            "signal_content_sha256",
            "forecast_content_sha256",
        ):
            object.__setattr__(self, name, _sha(getattr(self, name), name))
        object.__setattr__(
            self,
            "forecast_recorded_at",
            require_utc(self.forecast_recorded_at, field="Forecast recorded_at"),
        )
        if tuple(item.forecast_ordinal for item in self.items) != tuple(range(1, len(self.items) + 1)):
            raise ValueError("Opportunity input ordinals must be contiguous")
        if len({item.forecast_id for item in self.items}) != len(self.items):
            raise ValueError("Opportunity input roster contains a duplicate")


@dataclass(frozen=True, slots=True)
class OpportunityContextPlan:
    opportunity_context_id: UUID
    source: PreparedOpportunityContext
    ordinal: int
    content_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "content_sha256", canonical_json_sha256({
            "context_assessment_id": self.source.context_assessment_id,
            "ordinal": self.ordinal,
            "opportunity_context_id": self.opportunity_context_id,
            "signal_context_binding_id": self.source.signal_context_binding_id,
            "strategy_context_requirement_id": self.source.strategy_context_requirement_id,
        }))


@dataclass(frozen=True, slots=True)
class OpportunityPlan:
    opportunity_id: UUID
    ordinal: int
    source: PreparedOpportunityInput
    status: OpportunityStatus
    action: DecisionAction
    reason_code: str
    contexts: tuple[OpportunityContextPlan, ...]
    context_roster_sha256: str
    content_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "context_roster_sha256", _sha(self.context_roster_sha256, "Opportunity Context roster hash"))
        object.__setattr__(self, "content_sha256", canonical_json_sha256({
            "action": self.action,
            "commitment_id": self.source.commitment_id,
            "context_count": len(self.contexts),
            "context_roster_sha256": self.context_roster_sha256,
            "forecast_id": self.source.forecast_id,
            "opportunity_id": self.opportunity_id,
            "ordinal": self.ordinal,
            "reason_code": self.reason_code,
            "signal_id": self.source.signal_id,
            "status": self.status,
        }))


@dataclass(frozen=True, slots=True)
class OpportunityAuthority:
    opportunity_set_id: UUID
    prepared: PreparedOpportunityInputs
    opportunities: tuple[OpportunityPlan, ...]
    opportunity_roster_sha256: str
    context_count: int
    request_identity: str
    request_sha256: str
    command_receipt_id: UUID
    recorded_at: datetime
    content_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "opportunity_roster_sha256", _sha(self.opportunity_roster_sha256, "Opportunity roster hash"))
        object.__setattr__(self, "recorded_at", require_utc(self.recorded_at, field="Opportunity recorded_at"))
        if self.recorded_at < self.prepared.forecast_recorded_at:
            raise ValueError("Opportunity cannot precede Forecast")
        object.__setattr__(self, "content_sha256", canonical_json_sha256({
            "context_count": self.context_count,
            "decision_run_id": self.prepared.decision_run_id,
            "forecast_group_id": self.prepared.forecast_group_id,
            "opportunity_count": len(self.opportunities),
            "opportunity_roster_sha256": self.opportunity_roster_sha256,
            "opportunity_set_id": self.opportunity_set_id,
            "request_identity": self.request_identity,
            "request_sha256": self.request_sha256,
            "strategy_version_id": self.prepared.strategy_version_id,
        }))


def build_opportunity_authority(
    *,
    opportunity_set_id: UUID,
    prepared: PreparedOpportunityInputs,
    request_identity: str,
    request_sha256: str,
    command_receipt_id: UUID,
    recorded_at: datetime,
    opportunity_id_factory: Callable[[PreparedOpportunityInput], UUID],
    context_id_factory: Callable[[PreparedOpportunityInput, PreparedOpportunityContext], UUID],
) -> OpportunityAuthority:
    if not _REQUEST.fullmatch(request_identity):
        raise ValueError("Opportunity request identity is invalid")
    request_sha256 = _sha(request_sha256, "Opportunity request hash")
    plans: list[OpportunityPlan] = []
    for ordinal, source in enumerate(prepared.items, start=1):
        if source.signal_status is SignalStatus.PRESENT and source.forecast_status is ForecastStatus.AVAILABLE:
            status, action, reason = OpportunityStatus.ACTIONABLE, DecisionAction.ENTER, "SIGNAL_FORECAST_ACTIONABLE"
        elif source.signal_status is SignalStatus.WAIT:
            status, action, reason = OpportunityStatus.WAIT, DecisionAction.WAIT, "SIGNAL_WAIT"
        elif source.signal_status in {SignalStatus.UNKNOWN, SignalStatus.NOT_ESTIMABLE} or source.forecast_status is ForecastStatus.NOT_ESTIMABLE:
            status, action, reason = OpportunityStatus.NOT_ESTIMABLE, DecisionAction.DATA_INSUFFICIENT, "INPUT_NOT_ESTIMABLE"
        else:
            status, action, reason = OpportunityStatus.NO_ACTION, DecisionAction.NO_ACTION, "SIGNAL_FORECAST_NO_ACTION"
        contexts = tuple(
            OpportunityContextPlan(
                opportunity_context_id=context_id_factory(source, item),
                source=item,
                ordinal=context_ordinal,
            )
            for context_ordinal, item in enumerate(source.contexts, start=1)
        )
        context_hash = canonical_json_sha256(tuple({
            "content_sha256": item.content_sha256,
            "opportunity_context_id": item.opportunity_context_id,
            "ordinal": item.ordinal,
        } for item in contexts))
        plans.append(OpportunityPlan(
            opportunity_id=opportunity_id_factory(source),
            ordinal=ordinal,
            source=source,
            status=status,
            action=action,
            reason_code=reason,
            contexts=contexts,
            context_roster_sha256=context_hash,
        ))
    opportunities = tuple(plans)
    roster_hash = canonical_json_sha256(tuple({
        "content_sha256": item.content_sha256,
        "opportunity_id": item.opportunity_id,
        "ordinal": item.ordinal,
    } for item in opportunities))
    return OpportunityAuthority(
        opportunity_set_id=opportunity_set_id,
        prepared=prepared,
        opportunities=opportunities,
        opportunity_roster_sha256=roster_hash,
        context_count=sum(len(item.contexts) for item in opportunities),
        request_identity=request_identity,
        request_sha256=request_sha256,
        command_receipt_id=command_receipt_id,
        recorded_at=recorded_at,
    )


@dataclass(frozen=True, slots=True)
class ThesisConditionPlan:
    thesis_condition_id: UUID
    thesis_id: UUID
    ordinal: int
    condition_code: str
    kind: ThesisConditionKind
    source: ThesisConditionSource
    operator: ThesisConditionOperator
    decimal_threshold: Decimal | None
    text_threshold: str | None
    value_unit: str
    missing_action: ThesisMissingAction
    invalidates: bool
    content_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        if not _CODE.fullmatch(self.condition_code) or self.ordinal < 1:
            raise ValueError("Thesis condition identity is invalid")
        if (self.decimal_threshold is None) == (self.text_threshold is None):
            raise ValueError("Thesis condition requires exactly one threshold")
        if self.decimal_threshold is not None and not self.decimal_threshold.is_finite():
            raise ValueError("Thesis Decimal threshold must be finite")
        if self.kind is ThesisConditionKind.INVALIDATE and not self.invalidates:
            raise ValueError("INVALIDATE condition must invalidate the Thesis")
        object.__setattr__(self, "content_sha256", canonical_json_sha256({
            "condition_code": self.condition_code,
            "decimal_threshold": self.decimal_threshold,
            "invalidates": self.invalidates,
            "kind": self.kind,
            "missing_action": self.missing_action,
            "operator": self.operator,
            "ordinal": self.ordinal,
            "source": self.source,
            "text_threshold": self.text_threshold,
            "thesis_condition_id": self.thesis_condition_id,
            "thesis_id": self.thesis_id,
            "value_unit": self.value_unit,
        }))


@dataclass(frozen=True, slots=True)
class ThesisPlan:
    thesis_id: UUID
    opportunity_id: UUID
    opportunity_content_sha256: str
    revision: int
    supersedes_thesis_id: UUID | None
    claim: str
    conditions: tuple[ThesisConditionPlan, ...]
    code_artifact: DecisionArtifactBinding
    config_artifact: DecisionArtifactBinding
    provenance_sha256: str
    condition_roster_sha256: str = field(init=False)
    content_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        if (self.revision == 1) != (self.supersedes_thesis_id is None):
            raise ValueError("Thesis supersession shape is invalid")
        if not self.claim.strip() or len(self.claim) > 1000:
            raise ValueError("Thesis claim is invalid")
        if not self.conditions or tuple(item.ordinal for item in self.conditions) != tuple(range(1, len(self.conditions) + 1)):
            raise ValueError("Thesis condition roster must be non-empty and contiguous")
        if any(item.thesis_id != self.thesis_id for item in self.conditions):
            raise ValueError("Thesis condition belongs to a different Thesis")
        if len({item.condition_code for item in self.conditions}) != len(self.conditions):
            raise ValueError("Thesis condition roster contains a duplicate")
        object.__setattr__(self, "opportunity_content_sha256", _sha(self.opportunity_content_sha256, "Opportunity hash"))
        object.__setattr__(self, "provenance_sha256", _sha(self.provenance_sha256, "Thesis provenance"))
        roster_hash = canonical_json_sha256(tuple({
            "content_sha256": item.content_sha256,
            "ordinal": item.ordinal,
            "thesis_condition_id": item.thesis_condition_id,
        } for item in self.conditions))
        object.__setattr__(self, "condition_roster_sha256", roster_hash)
        object.__setattr__(self, "content_sha256", canonical_json_sha256({
            "claim": self.claim,
            "code_artifact": self.code_artifact,
            "condition_count": len(self.conditions),
            "condition_roster_sha256": roster_hash,
            "config_artifact": self.config_artifact,
            "opportunity_content_sha256": self.opportunity_content_sha256,
            "opportunity_id": self.opportunity_id,
            "provenance_sha256": self.provenance_sha256,
            "revision": self.revision,
            "supersedes_thesis_id": self.supersedes_thesis_id,
            "thesis_id": self.thesis_id,
        }))


__all__ = [
    "DecisionAction", "OpportunityAuthority", "OpportunityContextPlan",
    "OpportunityPlan", "OpportunityStatus", "PreparedOpportunityContext",
    "PreparedOpportunityInput", "PreparedOpportunityInputs",
    "ThesisConditionKind", "ThesisConditionOperator", "ThesisConditionPlan",
    "ThesisConditionSource", "ThesisMissingAction", "ThesisPlan",
    "build_opportunity_authority",
]
