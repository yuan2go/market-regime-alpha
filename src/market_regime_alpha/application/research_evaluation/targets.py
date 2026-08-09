"""Content-addressed multi-horizon Outcome Target Protocol authority."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Any, Mapping

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
class TargetDefinition:
    target_id: ArtifactId
    target_hash: str
    target_version: str
    label_start: str
    label_end: OutcomeCheckpoint
    return_reference: ReturnReference
    checkpoint: OutcomeCheckpoint
    barriers: tuple[BarrierDefinition, ...]
    compute_mfe_mae: bool
    required_market_data: tuple[str, ...]
    tradability_policy: TradabilityPolicy
    corporate_action_policy: CorporateActionPolicy
    missing_quote_policy: MissingQuotePolicy

    def __post_init__(self) -> None:
        require_sha256("target_hash", self.target_hash)
        require_text("target_version", self.target_version)
        if not isinstance(self.compute_mfe_mae, bool):
            raise TypeError("compute_mfe_mae must be bool")
        if self.label_start != "FROZEN_DECISION_TIME":
            raise ValueError("Target label start must bind the frozen Decision time")
        if self.label_end is not self.checkpoint:
            raise ValueError("Target label end must equal its checkpoint")
        if self.required_market_data != tuple(sorted(set(self.required_market_data))):
            raise ValueError("Target required market data must be unique and sorted")
        barrier_ids = tuple(value.barrier_id for value in self.barriers)
        if barrier_ids != tuple(sorted(set(barrier_ids))):
            raise ValueError("Target barriers must be unique and sorted")
        if canonical_hash(self.identity_payload()) != self.target_hash:
            raise ValueError("Target hash does not match content")
        if str(self.target_id) != f"outcome-target:{self.target_hash[7:]}":
            raise ValueError("Target id does not match content")

    @classmethod
    def create(
        cls,
        *,
        target_version: str,
        checkpoint: OutcomeCheckpoint,
        barriers: tuple[BarrierDefinition, ...],
        compute_mfe_mae: bool,
        required_market_data: tuple[str, ...],
        tradability_policy: TradabilityPolicy,
        corporate_action_policy: CorporateActionPolicy,
        missing_quote_policy: MissingQuotePolicy,
    ) -> TargetDefinition:
        values = {
            "schema": "outcome_target_definition/v1",
            "target_version": target_version,
            "label_start": "FROZEN_DECISION_TIME",
            "label_end": checkpoint.value,
            "return_reference": ReturnReference.FROZEN_DECISION_REFERENCE_PRICE.value,
            "checkpoint": checkpoint.value,
            "barriers": [item.to_canonical_dict() for item in barriers],
            "compute_mfe_mae": compute_mfe_mae,
            "required_market_data": list(required_market_data),
            "tradability_policy": tradability_policy.value,
            "corporate_action_policy": corporate_action_policy.value,
            "missing_quote_policy": missing_quote_policy.value,
        }
        digest = canonical_hash(values)
        return cls(
            target_id=ArtifactId(f"outcome-target:{digest[7:]}"),
            target_hash=digest,
            target_version=target_version,
            label_start="FROZEN_DECISION_TIME",
            label_end=checkpoint,
            return_reference=ReturnReference.FROZEN_DECISION_REFERENCE_PRICE,
            checkpoint=checkpoint,
            barriers=barriers,
            compute_mfe_mae=compute_mfe_mae,
            required_market_data=required_market_data,
            tradability_policy=tradability_policy,
            corporate_action_policy=corporate_action_policy,
            missing_quote_policy=missing_quote_policy,
        )

    def identity_payload(self) -> dict[str, Any]:
        return {
            "schema": "outcome_target_definition/v1",
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

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "target_id": str(self.target_id),
            "target_hash": self.target_hash,
            **self.identity_payload(),
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> TargetDefinition:
        return cls(
            target_id=ArtifactId(str(payload["target_id"])),
            target_hash=str(payload["target_hash"]),
            target_version=str(payload["target_version"]),
            label_start=str(payload["label_start"]),
            label_end=OutcomeCheckpoint(str(payload["label_end"])),
            return_reference=ReturnReference(str(payload["return_reference"])),
            checkpoint=OutcomeCheckpoint(str(payload["checkpoint"])),
            barriers=tuple(
                BarrierDefinition(
                    barrier_id=str(item["barrier_id"]),
                    return_threshold=Decimal(str(item["return_threshold"])),
                    direction=str(item["direction"]),
                )
                for item in _objects(payload["barriers"])
            ),
            compute_mfe_mae=_boolean(payload["compute_mfe_mae"]),
            required_market_data=_strings(payload["required_market_data"]),
            tradability_policy=TradabilityPolicy(str(payload["tradability_policy"])),
            corporate_action_policy=CorporateActionPolicy(str(payload["corporate_action_policy"])),
            missing_quote_policy=MissingQuotePolicy(str(payload["missing_quote_policy"])),
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
        if self.limitations != tuple(sorted(set(self.limitations))):
            raise ValueError("Protocol limitations must be unique and sorted")
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
    ) -> OutcomeTargetProtocol:
        ordered_targets = tuple(sorted(targets, key=lambda item: str(item.target_id)))
        ordered_limitations = tuple(sorted(set(limitations)))
        identity = _protocol_payload(
            protocol_version=protocol_version,
            timezone_name=timezone_name,
            session_offset=session_offset,
            targets=ordered_targets,
            limitations=ordered_limitations,
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
        )

    def identity_payload(self) -> dict[str, Any]:
        return _protocol_payload(
            protocol_version=self.protocol_version,
            timezone_name=self.timezone_name,
            session_offset=self.session_offset,
            targets=self.targets,
            limitations=self.limitations,
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
        )


def engineering_multi_horizon_protocol() -> OutcomeTargetProtocol:
    barriers = (
        BarrierDefinition("DOWN_1_PERCENT", Decimal("0.01"), "DOWN"),
        BarrierDefinition("UP_1_PERCENT", Decimal("0.01"), "UP"),
        BarrierDefinition("UP_2_PERCENT", Decimal("0.02"), "UP"),
    )
    targets = tuple(
        TargetDefinition.create(
            target_version="engineering-v1",
            checkpoint=checkpoint,
            barriers=barriers,
            compute_mfe_mae=True,
            required_market_data=(
                ("FACTUAL_OUTCOME_V1",)
                if checkpoint is OutcomeCheckpoint.OPEN
                else ("DAILY", "MINUTE_1")
                if checkpoint is OutcomeCheckpoint.CLOSE
                else ("MINUTE_1",)
            ),
            tradability_policy=TradabilityPolicy.LABEL_FACT_AND_ANNOTATE,
            corporate_action_policy=CorporateActionPolicy.RAW_ONLY_FAIL_CLOSED,
            missing_quote_policy=MissingQuotePolicy.UNAVAILABLE_NOT_ZERO,
        )
        for checkpoint in OutcomeCheckpoint
    )
    return OutcomeTargetProtocol.create(
        protocol_version="multi-horizon-engineering-v1",
        timezone_name="Asia/Shanghai",
        session_offset=1,
        targets=targets,
        limitations=(
            "FORMAL_OOS_NOT_ESTABLISHED",
            "NO_TARGET_SELECTED_AS_WINNER",
            "RESEARCH_LABELS_ONLY",
        ),
    )


def _protocol_payload(**values: Any) -> dict[str, Any]:
    return {
        "schema": "outcome_target_protocol/v1",
        "protocol_version": values["protocol_version"],
        "timezone_name": values["timezone_name"],
        "session_offset": values["session_offset"],
        "targets": [item.to_canonical_dict() for item in values["targets"]],
        "limitations": list(values["limitations"]),
    }


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
    "CorporateActionPolicy",
    "MissingQuotePolicy",
    "OutcomeCheckpoint",
    "OutcomeTargetProtocol",
    "ReturnReference",
    "TargetDefinition",
    "TradabilityPolicy",
    "engineering_multi_horizon_protocol",
]
