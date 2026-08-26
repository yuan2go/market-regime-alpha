"""Content-addressed multi-horizon Outcome Target Protocol authority."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Any, Mapping

from market_regime_alpha.application.research_evaluation.target_semantics import (
    TargetSemanticSpecification,
    wp_alpha_correctness_02_target_semantic_specification,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash, require_sha256, require_text


class OutcomeCheckpoint(str, Enum):
    OPEN = "OPEN"
    TIME_0945 = "09:45"
    TIME_1000 = "10:00"
    TIME_1030 = "10:30"
    TIME_1130 = "11:30"
    CLOSE = "CLOSE"


class ReturnReference(str, Enum):
    FROZEN_DECISION_REFERENCE_PRICE = "FROZEN_DECISION_REFERENCE_PRICE"


class TradabilityPolicy(str, Enum):
    LABEL_FACT_AND_ANNOTATE = "LABEL_FACT_AND_ANNOTATE"


class CorporateActionPolicy(str, Enum):
    RAW_ONLY_FAIL_CLOSED = "RAW_ONLY_FAIL_CLOSED"


class MissingQuotePolicy(str, Enum):
    UNAVAILABLE_NOT_ZERO = "UNAVAILABLE_NOT_ZERO"


class DecisionTimePolicy(str, Enum):
    FROZEN_DECISION_TIME = "FROZEN_DECISION_TIME"


class ReturnDefinition(str, Enum):
    SIMPLE_PRICE_RETURN = "SIMPLE_PRICE_RETURN"


class BarrierOrderingSemantics(str, Enum):
    EVENT_TIME_ELSE_NOT_OBSERVABLE = "EVENT_TIME_ELSE_NOT_OBSERVABLE"


class SuspensionPolicy(str, Enum):
    NOT_ESTIMABLE_AND_ANNOTATE = "NOT_ESTIMABLE_AND_ANNOTATE"


class PriceLimitPolicy(str, Enum):
    ANNOTATE_NOT_ASSUME_FILL = "ANNOTATE_NOT_ASSUME_FILL"


@dataclass(frozen=True, slots=True)
class TargetTimePoint:
    session_offset: int
    checkpoint: OutcomeCheckpoint | None
    frozen_decision_time: bool = False

    def __post_init__(self) -> None:
        if self.session_offset < 0:
            raise ValueError("Target time-point session offset cannot be negative")
        if self.frozen_decision_time != (self.checkpoint is None):
            raise ValueError("Target time point must be DecisionTime or a checkpoint")
        if self.frozen_decision_time and self.session_offset != 0:
            raise ValueError("Frozen DecisionTime must use session offset zero")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "session_offset": self.session_offset,
            "checkpoint": None if self.checkpoint is None else self.checkpoint.value,
            "frozen_decision_time": self.frozen_decision_time,
        }

    @classmethod
    def from_canonical_dict(cls, value: Mapping[str, Any]) -> TargetTimePoint:
        checkpoint = value.get("checkpoint")
        return cls(
            session_offset=int(value["session_offset"]),
            checkpoint=(
                None if checkpoint is None else OutcomeCheckpoint(str(checkpoint))
            ),
            frozen_decision_time=_boolean(value["frozen_decision_time"]),
        )


@dataclass(frozen=True, slots=True)
class TargetWindow:
    start: TargetTimePoint
    end: TargetTimePoint

    def __post_init__(self) -> None:
        if _time_point_key(self.start) > _time_point_key(self.end):
            raise ValueError("Target window cannot end before it starts")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "start": self.start.to_canonical_dict(),
            "end": self.end.to_canonical_dict(),
        }

    @classmethod
    def from_canonical_dict(cls, value: Mapping[str, Any]) -> TargetWindow:
        return cls(
            TargetTimePoint.from_canonical_dict(_object(value["start"])),
            TargetTimePoint.from_canonical_dict(_object(value["end"])),
        )


@dataclass(frozen=True, slots=True)
class BarrierDefinition:
    barrier_id: str
    return_threshold: Decimal
    direction: str

    def __post_init__(self) -> None:
        require_text("barrier_id", self.barrier_id)
        if self.direction not in {"UP", "DOWN"}:
            raise ValueError("Barrier direction must be UP or DOWN")
        if self.return_threshold <= 0:
            raise ValueError("Barrier threshold must be positive")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "barrier_id": self.barrier_id,
            "return_threshold": str(self.return_threshold),
            "direction": self.direction,
        }


@dataclass(frozen=True, slots=True)
class CanonicalTargetHorizon:
    decision_time_policy: DecisionTimePolicy
    session_offset: int
    entry_window: TargetWindow
    observation_window: TargetWindow
    evaluation_timestamp: TargetTimePoint
    return_reference: ReturnReference
    return_definition: ReturnDefinition
    mfe_window: TargetWindow | None
    mae_window: TargetWindow | None
    barriers: tuple[BarrierDefinition, ...]
    barrier_ordering_semantics: BarrierOrderingSemantics
    tradability_policy: TradabilityPolicy
    corporate_action_policy: CorporateActionPolicy
    missing_quote_policy: MissingQuotePolicy
    suspension_policy: SuspensionPolicy
    price_limit_policy: PriceLimitPolicy

    def __post_init__(self) -> None:
        if self.session_offset <= 0:
            raise ValueError("Canonical Target session offset must be positive")
        decision = TargetTimePoint(0, None, True)
        if self.entry_window != TargetWindow(decision, decision):
            raise ValueError("Target entry/reference window must bind Frozen DecisionTime")
        expected_start = TargetTimePoint(
            self.session_offset, OutcomeCheckpoint.OPEN
        )
        if self.observation_window.start != expected_start:
            raise ValueError("Target observation must start at the future session open")
        if self.observation_window.end != self.evaluation_timestamp:
            raise ValueError("Target observation must end at EvaluationTimestamp")
        if self.evaluation_timestamp.session_offset != self.session_offset:
            raise ValueError("Target evaluation offset drift")
        if self.mfe_window != self.mae_window:
            raise ValueError("MFE and MAE windows must share one canonical path window")
        if self.mfe_window is not None and self.mfe_window != self.observation_window:
            raise ValueError("Excursion window must equal the observation window")
        barrier_ids = tuple(value.barrier_id for value in self.barriers)
        if barrier_ids != tuple(sorted(set(barrier_ids))):
            raise ValueError("Target barriers must be unique and sorted")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "decision_time_policy": self.decision_time_policy.value,
            "session_offset": self.session_offset,
            "entry_window": self.entry_window.to_canonical_dict(),
            "observation_window": self.observation_window.to_canonical_dict(),
            "evaluation_timestamp": self.evaluation_timestamp.to_canonical_dict(),
            "return_reference": self.return_reference.value,
            "return_definition": self.return_definition.value,
            "mfe_window": None if self.mfe_window is None else self.mfe_window.to_canonical_dict(),
            "mae_window": None if self.mae_window is None else self.mae_window.to_canonical_dict(),
            "barriers": [item.to_canonical_dict() for item in self.barriers],
            "barrier_ordering_semantics": self.barrier_ordering_semantics.value,
            "tradability_policy": self.tradability_policy.value,
            "corporate_action_policy": self.corporate_action_policy.value,
            "missing_quote_policy": self.missing_quote_policy.value,
            "suspension_policy": self.suspension_policy.value,
            "price_limit_policy": self.price_limit_policy.value,
        }

    @classmethod
    def from_canonical_dict(
        cls, value: Mapping[str, Any]
    ) -> CanonicalTargetHorizon:
        mfe = value.get("mfe_window")
        mae = value.get("mae_window")
        return cls(
            decision_time_policy=DecisionTimePolicy(str(value["decision_time_policy"])),
            session_offset=int(value["session_offset"]),
            entry_window=TargetWindow.from_canonical_dict(_object(value["entry_window"])),
            observation_window=TargetWindow.from_canonical_dict(_object(value["observation_window"])),
            evaluation_timestamp=TargetTimePoint.from_canonical_dict(_object(value["evaluation_timestamp"])),
            return_reference=ReturnReference(str(value["return_reference"])),
            return_definition=ReturnDefinition(str(value["return_definition"])),
            mfe_window=None if mfe is None else TargetWindow.from_canonical_dict(_object(mfe)),
            mae_window=None if mae is None else TargetWindow.from_canonical_dict(_object(mae)),
            barriers=tuple(
                BarrierDefinition(
                    barrier_id=str(item["barrier_id"]),
                    return_threshold=Decimal(str(item["return_threshold"])),
                    direction=str(item["direction"]),
                )
                for item in _objects(value["barriers"])
            ),
            barrier_ordering_semantics=BarrierOrderingSemantics(str(value["barrier_ordering_semantics"])),
            tradability_policy=TradabilityPolicy(str(value["tradability_policy"])),
            corporate_action_policy=CorporateActionPolicy(str(value["corporate_action_policy"])),
            missing_quote_policy=MissingQuotePolicy(str(value["missing_quote_policy"])),
            suspension_policy=SuspensionPolicy(str(value["suspension_policy"])),
            price_limit_policy=PriceLimitPolicy(str(value["price_limit_policy"])),
        )


def canonical_target_horizon(
    *,
    checkpoint: OutcomeCheckpoint,
    barriers: tuple[BarrierDefinition, ...],
    compute_mfe_mae: bool,
    session_offset: int = 1,
) -> CanonicalTargetHorizon:
    decision = TargetTimePoint(0, None, True)
    observation = TargetWindow(
        TargetTimePoint(session_offset, OutcomeCheckpoint.OPEN),
        TargetTimePoint(session_offset, checkpoint),
    )
    return CanonicalTargetHorizon(
        decision_time_policy=DecisionTimePolicy.FROZEN_DECISION_TIME,
        session_offset=session_offset,
        entry_window=TargetWindow(decision, decision),
        observation_window=observation,
        evaluation_timestamp=observation.end,
        return_reference=ReturnReference.FROZEN_DECISION_REFERENCE_PRICE,
        return_definition=ReturnDefinition.SIMPLE_PRICE_RETURN,
        mfe_window=observation if compute_mfe_mae else None,
        mae_window=observation if compute_mfe_mae else None,
        barriers=tuple(sorted(barriers, key=lambda item: item.barrier_id)),
        barrier_ordering_semantics=(
            BarrierOrderingSemantics.EVENT_TIME_ELSE_NOT_OBSERVABLE
        ),
        tradability_policy=TradabilityPolicy.LABEL_FACT_AND_ANNOTATE,
        corporate_action_policy=CorporateActionPolicy.RAW_ONLY_FAIL_CLOSED,
        missing_quote_policy=MissingQuotePolicy.UNAVAILABLE_NOT_ZERO,
        suspension_policy=SuspensionPolicy.NOT_ESTIMABLE_AND_ANNOTATE,
        price_limit_policy=PriceLimitPolicy.ANNOTATE_NOT_ASSUME_FILL,
    )


@dataclass(frozen=True, slots=True)
class TargetDefinition:
    target_id: ArtifactId
    target_hash: str
    target_version: str
    canonical_horizon: CanonicalTargetHorizon
    required_market_data: tuple[str, ...]
    schema_version: str

    def __post_init__(self) -> None:
        require_sha256("target_hash", self.target_hash)
        require_text("target_version", self.target_version)
        if self.required_market_data != tuple(sorted(set(self.required_market_data))):
            raise ValueError("Target required market data must be unique and sorted")
        if self.schema_version not in {
            "outcome_target_definition/v1",
            "outcome_target_definition/v2",
        }:
            raise ValueError("unsupported Outcome Target Definition schema")
        if canonical_hash(self.identity_payload()) != self.target_hash:
            raise ValueError("Target hash does not match content")
        if str(self.target_id) != f"outcome-target:{self.target_hash[7:]}":
            raise ValueError("Target id does not match content")

    @classmethod
    def create(
        cls,
        *,
        target_version: str,
        canonical_horizon: CanonicalTargetHorizon,
        required_market_data: tuple[str, ...],
    ) -> TargetDefinition:
        values = {
            "schema": "outcome_target_definition/v2",
            "target_version": target_version,
            "canonical_horizon": canonical_horizon.to_canonical_dict(),
            "required_market_data": list(tuple(sorted(set(required_market_data)))),
        }
        digest = canonical_hash(values)
        return cls(
            target_id=ArtifactId(f"outcome-target:{digest[7:]}"),
            target_hash=digest,
            target_version=target_version,
            canonical_horizon=canonical_horizon,
            required_market_data=tuple(sorted(set(required_market_data))),
            schema_version="outcome_target_definition/v2",
        )

    @property
    def label_start(self) -> str:
        return self.canonical_horizon.decision_time_policy.value

    @property
    def label_end(self) -> OutcomeCheckpoint:
        return self.checkpoint

    @property
    def return_reference(self) -> ReturnReference:
        return self.canonical_horizon.return_reference

    @property
    def checkpoint(self) -> OutcomeCheckpoint:
        checkpoint = self.canonical_horizon.evaluation_timestamp.checkpoint
        if checkpoint is None:
            raise RuntimeError("validated Target evaluation checkpoint disappeared")
        return checkpoint

    @property
    def barriers(self) -> tuple[BarrierDefinition, ...]:
        return self.canonical_horizon.barriers

    @property
    def compute_mfe_mae(self) -> bool:
        return self.canonical_horizon.mfe_window is not None

    @property
    def tradability_policy(self) -> TradabilityPolicy:
        return self.canonical_horizon.tradability_policy

    @property
    def corporate_action_policy(self) -> CorporateActionPolicy:
        return self.canonical_horizon.corporate_action_policy

    @property
    def missing_quote_policy(self) -> MissingQuotePolicy:
        return self.canonical_horizon.missing_quote_policy

    def identity_payload(self) -> dict[str, Any]:
        if self.schema_version == "outcome_target_definition/v1":
            return {
                "schema": self.schema_version,
                "target_version": self.target_version,
                "label_start": self.label_start,
                "label_end": self.label_end.value,
                "return_reference": self.return_reference.value,
                "checkpoint": self.checkpoint.value,
                "barriers": [item.to_canonical_dict() for item in self.barriers],
                "compute_mfe_mae": self.compute_mfe_mae,
                "required_market_data": list(self.required_market_data),
                "tradability_policy": self.tradability_policy.value,
                "corporate_action_policy": self.corporate_action_policy.value,
                "missing_quote_policy": self.missing_quote_policy.value,
            }
        return {
            "schema": self.schema_version,
            "target_version": self.target_version,
            "canonical_horizon": self.canonical_horizon.to_canonical_dict(),
            "required_market_data": list(self.required_market_data),
        }

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "target_id": str(self.target_id),
            "target_hash": self.target_hash,
            **self.identity_payload(),
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> TargetDefinition:
        schema = str(payload.get("schema"))
        if schema == "outcome_target_definition/v2":
            horizon = CanonicalTargetHorizon.from_canonical_dict(
                _object(payload["canonical_horizon"])
            )
        elif schema == "outcome_target_definition/v1":
            checkpoint = OutcomeCheckpoint(str(payload["checkpoint"]))
            barriers = tuple(
                BarrierDefinition(
                    barrier_id=str(item["barrier_id"]),
                    return_threshold=Decimal(str(item["return_threshold"])),
                    direction=str(item["direction"]),
                )
                for item in _objects(payload["barriers"])
            )
            horizon = canonical_target_horizon(
                checkpoint=checkpoint,
                barriers=barriers,
                compute_mfe_mae=_boolean(payload["compute_mfe_mae"]),
                session_offset=1,
            )
        else:
            raise ValueError("unsupported Outcome Target Definition schema")
        return cls(
            target_id=ArtifactId(str(payload["target_id"])),
            target_hash=str(payload["target_hash"]),
            target_version=str(payload["target_version"]),
            canonical_horizon=horizon,
            required_market_data=_strings(payload["required_market_data"]),
            schema_version=schema,
        )


@dataclass(frozen=True, slots=True)
class OutcomeTargetProtocol:
    protocol_id: ArtifactId
    protocol_hash: str
    protocol_version: str
    timezone_name: str
    session_offset: int
    targets: tuple[TargetDefinition, ...]
    limitations: tuple[str, ...]
    target_semantic_specification: TargetSemanticSpecification | None = None
    schema_version: str = "outcome-target-protocol/v1"

    def __post_init__(self) -> None:
        require_sha256("protocol_hash", self.protocol_hash)
        require_text("protocol_version", self.protocol_version)
        require_text("timezone_name", self.timezone_name)
        if self.session_offset <= 0:
            raise ValueError("Target session offset must be positive")
        if self.targets != tuple(sorted(self.targets, key=lambda item: str(item.target_id))):
            raise ValueError("Protocol targets must be unique and sorted")
        if len({item.target_id for item in self.targets}) != len(self.targets):
            raise ValueError("Protocol targets must be unique")
        if any(
            item.canonical_horizon.session_offset != self.session_offset
            for item in self.targets
        ):
            raise ValueError("Protocol and Target session offsets must agree")
        if self.limitations != tuple(sorted(set(self.limitations))):
            raise ValueError("Protocol limitations must be unique and sorted")
        if self.schema_version not in {
            "outcome-target-protocol/v1",
            "outcome-target-protocol/v2",
        }:
            raise ValueError("unsupported Outcome Target Protocol schema")
        if (self.schema_version == "outcome-target-protocol/v2") != (
            self.target_semantic_specification is not None
        ):
            raise ValueError(
                "Outcome Target Protocol v2 requires one semantic specification"
            )
        if canonical_hash(self.identity_payload()) != self.protocol_hash:
            raise ValueError("Target Protocol hash does not match content")
        if str(self.protocol_id) != f"outcome-target-protocol:{self.protocol_hash[7:]}":
            raise ValueError("Target Protocol id does not match content")

    @classmethod
    def create(
        cls,
        *,
        protocol_version: str,
        timezone_name: str,
        session_offset: int,
        targets: tuple[TargetDefinition, ...],
        limitations: tuple[str, ...],
        target_semantic_specification: TargetSemanticSpecification | None = None,
    ) -> OutcomeTargetProtocol:
        ordered_targets = tuple(sorted(targets, key=lambda item: str(item.target_id)))
        ordered_limitations = tuple(sorted(set(limitations)))
        identity = _protocol_payload(
            protocol_version=protocol_version,
            timezone_name=timezone_name,
            session_offset=session_offset,
            targets=ordered_targets,
            limitations=ordered_limitations,
            target_semantic_specification=target_semantic_specification,
            schema_version=(
                "outcome-target-protocol/v2"
                if target_semantic_specification is not None
                else "outcome-target-protocol/v1"
            ),
        )
        digest = canonical_hash(identity)
        return cls(
            protocol_id=ArtifactId(f"outcome-target-protocol:{digest[7:]}"),
            protocol_hash=digest,
            protocol_version=protocol_version,
            timezone_name=timezone_name,
            session_offset=session_offset,
            targets=ordered_targets,
            limitations=ordered_limitations,
            target_semantic_specification=target_semantic_specification,
            schema_version=(
                "outcome-target-protocol/v2"
                if target_semantic_specification is not None
                else "outcome-target-protocol/v1"
            ),
        )

    def identity_payload(self) -> dict[str, Any]:
        return _protocol_payload(
            protocol_version=self.protocol_version,
            timezone_name=self.timezone_name,
            session_offset=self.session_offset,
            targets=self.targets,
            limitations=self.limitations,
            target_semantic_specification=self.target_semantic_specification,
            schema_version=self.schema_version,
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "protocol_id": str(self.protocol_id),
            "protocol_hash": self.protocol_hash,
            **self.identity_payload(),
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> OutcomeTargetProtocol:
        return cls(
            protocol_id=ArtifactId(str(payload["protocol_id"])),
            protocol_hash=str(payload["protocol_hash"]),
            protocol_version=str(payload["protocol_version"]),
            timezone_name=str(payload["timezone_name"]),
            session_offset=int(payload["session_offset"]),
            targets=tuple(TargetDefinition.from_canonical_dict(item) for item in _objects(payload["targets"])),
            limitations=_strings(payload["limitations"]),
            target_semantic_specification=(
                None
                if payload.get("target_semantic_specification") is None
                else TargetSemanticSpecification.from_canonical_dict(
                    _object(payload["target_semantic_specification"])
                )
            ),
            schema_version=str(
                payload.get("schema_version", "outcome-target-protocol/v1")
            ),
        )


def engineering_multi_horizon_protocol() -> OutcomeTargetProtocol:
    barriers = (
        BarrierDefinition("DOWN_1_PERCENT", Decimal("0.01"), "DOWN"),
        BarrierDefinition("UP_1_PERCENT", Decimal("0.01"), "UP"),
        BarrierDefinition("UP_2_PERCENT", Decimal("0.02"), "UP"),
    )
    targets = tuple(
        TargetDefinition.create(
            target_version="engineering-v2",
            canonical_horizon=canonical_target_horizon(
                checkpoint=checkpoint,
                barriers=barriers,
                compute_mfe_mae=True,
            ),
            required_market_data=(
                ("FACTUAL_OUTCOME_V1",)
                if checkpoint is OutcomeCheckpoint.OPEN
                else ("DAILY", "MINUTE_1")
                if checkpoint is OutcomeCheckpoint.CLOSE
                else ("MINUTE_1",)
            ),
        )
        for checkpoint in OutcomeCheckpoint
    )
    return OutcomeTargetProtocol.create(
        protocol_version="multi-horizon-engineering-v2",
        timezone_name="Asia/Shanghai",
        session_offset=1,
        targets=targets,
        limitations=(
            "FORMAL_OOS_NOT_ESTABLISHED",
            "NO_TARGET_SELECTED_AS_WINNER",
            "RESEARCH_LABELS_ONLY",
        ),
    )


def exploratory_five_minute_multi_horizon_protocol() -> OutcomeTargetProtocol:
    """Canonical T+1 checkpoints whose frozen market-data basis is 5m.

    BaoStock does not provide the formal one-minute provider evidence expected
    by the engineering protocol.  This explicit exploratory protocol prevents
    a silent timeframe substitution while retaining the same Target/Horizon
    semantics and raw-only fail-closed label kernel.
    """

    barriers = (
        BarrierDefinition("DOWN_1_PERCENT", Decimal("0.01"), "DOWN"),
        BarrierDefinition("UP_1_PERCENT", Decimal("0.01"), "UP"),
        BarrierDefinition("UP_2_PERCENT", Decimal("0.02"), "UP"),
    )
    targets = tuple(
        TargetDefinition.create(
            target_version="phase-e-free-5m-exploratory-v1",
            canonical_horizon=canonical_target_horizon(
                checkpoint=checkpoint,
                barriers=barriers,
                compute_mfe_mae=True,
            ),
            required_market_data=(
                ("NORMALIZED_DAILY_OPEN",)
                if checkpoint is OutcomeCheckpoint.OPEN
                else ("MINUTE_5", "DAILY")
                if checkpoint is OutcomeCheckpoint.CLOSE
                else ("MINUTE_5",)
            ),
        )
        for checkpoint in OutcomeCheckpoint
    )
    return OutcomeTargetProtocol.create(
        protocol_version="phase-e-free-5m-exploratory-v1",
        timezone_name="Asia/Shanghai",
        session_offset=1,
        targets=targets,
        limitations=(
            "BARRIER_ORDERING_WITHIN_FIVE_MINUTE_BAR_NOT_OBSERVABLE",
            "FORMAL_OOS_FALSE",
            "PIT_INCOMPLETE",
            "RESEARCH_LABELS_ONLY",
        ),
    )


def exploratory_five_minute_multi_horizon_protocol_v2() -> OutcomeTargetProtocol:
    """Correctness revision with exact Decision and path-state semantics.

    The v1 factory remains immutable. This revision changes identities instead
    of reinterpreting an already persisted protocol or Target label.
    """

    barriers = (
        BarrierDefinition("DOWN_1_PERCENT", Decimal("0.01"), "DOWN"),
        BarrierDefinition("UP_1_PERCENT", Decimal("0.01"), "UP"),
        BarrierDefinition("UP_2_PERCENT", Decimal("0.02"), "UP"),
    )
    targets = tuple(
        TargetDefinition.create(
            target_version="phase-e-free-5m-exploratory-v2",
            canonical_horizon=canonical_target_horizon(
                checkpoint=checkpoint,
                barriers=barriers,
                compute_mfe_mae=True,
            ),
            required_market_data=(
                ("NORMALIZED_DAILY_OPEN",)
                if checkpoint is OutcomeCheckpoint.OPEN
                else ("MINUTE_5", "DAILY")
                if checkpoint is OutcomeCheckpoint.CLOSE
                else ("MINUTE_5",)
            ),
        )
        for checkpoint in OutcomeCheckpoint
    )
    return OutcomeTargetProtocol.create(
        protocol_version="phase-e-free-5m-exploratory-v2",
        timezone_name="Asia/Shanghai",
        session_offset=1,
        targets=targets,
        limitations=(
            "BARRIER_ORDERING_WITHIN_FIVE_MINUTE_BAR_NOT_OBSERVABLE",
            "FORMAL_OOS_FALSE",
            "PIT_INCOMPLETE",
            "RESEARCH_LABELS_ONLY",
        ),
        target_semantic_specification=(
            wp_alpha_correctness_02_target_semantic_specification()
        ),
    )
def _protocol_payload(**values: Any) -> dict[str, Any]:
    result = {
        "schema": "outcome_target_protocol/v1",
        "protocol_version": values["protocol_version"],
        "timezone_name": values["timezone_name"],
        "session_offset": values["session_offset"],
        "targets": [item.to_canonical_dict() for item in values["targets"]],
        "limitations": list(values["limitations"]),
    }
    if values.get("schema_version") == "outcome-target-protocol/v2":
        result["schema_version"] = "outcome-target-protocol/v2"
        specification = values.get("target_semantic_specification")
        if not isinstance(specification, TargetSemanticSpecification):
            raise ValueError("Outcome Target Protocol v2 semantics are missing")
        result["target_semantic_specification"] = (
            specification.to_canonical_dict()
        )
    return result


def _time_point_key(value: TargetTimePoint) -> tuple[int, int]:
    minutes = {
        None: 0,
        OutcomeCheckpoint.OPEN: 570,
        OutcomeCheckpoint.TIME_0945: 585,
        OutcomeCheckpoint.TIME_1000: 600,
        OutcomeCheckpoint.TIME_1030: 630,
        OutcomeCheckpoint.TIME_1130: 690,
        OutcomeCheckpoint.CLOSE: 900,
    }
    return value.session_offset, minutes[value.checkpoint]


def _object(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("expected object")
    return value


def _objects(value: object) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, list) or any(not isinstance(item, Mapping) for item in value):
        raise ValueError("expected object array")
    return tuple(value)


def _strings(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError("expected string array")
    return tuple(value)


def _boolean(value: object) -> bool:
    if not isinstance(value, bool):
        raise ValueError("expected boolean")
    return value


__all__ = [
    "BarrierDefinition",
    "BarrierOrderingSemantics",
    "CanonicalTargetHorizon",
    "CorporateActionPolicy",
    "DecisionTimePolicy",
    "MissingQuotePolicy",
    "OutcomeCheckpoint",
    "OutcomeTargetProtocol",
    "PriceLimitPolicy",
    "ReturnDefinition",
    "ReturnReference",
    "SuspensionPolicy",
    "TargetDefinition",
    "TargetTimePoint",
    "TargetWindow",
    "TradabilityPolicy",
    "canonical_target_horizon",
    "engineering_multi_horizon_protocol",
    "exploratory_five_minute_multi_horizon_protocol",
]
