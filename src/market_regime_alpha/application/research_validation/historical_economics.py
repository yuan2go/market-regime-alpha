"""Immutable owner for Historical Strategy Economics inputs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping

from market_regime_alpha.application.research_validation.common import (
    ValidationArtifactReference,
    content_identity,
    timestamp,
)
from market_regime_alpha.application.research_validation.liquidity_capacity import (
    LiquidityCapacityProtocol,
)
from market_regime_alpha.application.strategy_shadow.economics import (
    StrategyEconomicsPolicy,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash, require_sha256, require_text


HISTORICAL_STRATEGY_ECONOMICS_POLICY_SET_KIND = (
    "HISTORICAL_STRATEGY_ECONOMICS_POLICY_SET"
)


@dataclass(frozen=True, slots=True)
class HistoricalStrategyEconomicsPolicySet:
    """One immutable owner for every policy consumed by Historical Economics."""

    policy_set_id: ArtifactId
    policy_set_hash: str
    policy_set_version: str
    target_protocol_reference: ValidationArtifactReference
    strategy_policies: tuple[StrategyEconomicsPolicy, ...]
    capacity_protocol: LiquidityCapacityProtocol
    created_at: datetime
    limitations: tuple[str, ...]
    schema_version: str = "historical-strategy-economics-policy-set/v1"

    def __post_init__(self) -> None:
        require_sha256("policy_set_hash", self.policy_set_hash)
        require_text("policy_set_version", self.policy_set_version)
        if self.schema_version != "historical-strategy-economics-policy-set/v1":
            raise ValueError("unsupported Historical Strategy Economics Policy Set schema")
        if self.target_protocol_reference.artifact_kind != "OUTCOME_TARGET_PROTOCOL":
            raise ValueError("Historical Strategy Economics Target protocol kind mismatch")
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("Historical Strategy Economics owner time must be timezone-aware")
        policy_keys = tuple(
            str(item.prediction_target_reference.artifact_id)
            for item in self.strategy_policies
        )
        if not policy_keys or policy_keys != tuple(sorted(set(policy_keys))):
            raise ValueError("Historical Strategy Economics policies must be unique and sorted")
        if any(item.created_at != self.created_at for item in self.strategy_policies):
            raise ValueError("Historical Strategy Economics policy time mismatch")
        if self.capacity_protocol.created_at != self.created_at:
            raise ValueError("Historical Strategy Economics capacity time mismatch")
        if self.limitations != tuple(sorted(set(self.limitations))):
            raise ValueError("Historical Strategy Economics limitations must be unique and sorted")
        if canonical_hash(self.identity_payload()) != self.policy_set_hash:
            raise ValueError("Historical Strategy Economics Policy Set hash mismatch")
        if self.policy_set_id != ArtifactId(
            f"historical-strategy-economics-policy-set:{self.policy_set_hash[7:]}"
        ):
            raise ValueError("Historical Strategy Economics Policy Set identity mismatch")

    @classmethod
    def create(
        cls,
        *,
        policy_set_version: str,
        target_protocol_reference: ValidationArtifactReference,
        strategy_policies: tuple[StrategyEconomicsPolicy, ...],
        capacity_protocol: LiquidityCapacityProtocol,
        created_at: datetime,
        limitations: tuple[str, ...],
    ) -> HistoricalStrategyEconomicsPolicySet:
        values = {
            "policy_set_version": policy_set_version,
            "target_protocol_reference": target_protocol_reference,
            "strategy_policies": tuple(
                sorted(
                    strategy_policies,
                    key=lambda item: str(
                        item.prediction_target_reference.artifact_id
                    ),
                )
            ),
            "capacity_protocol": capacity_protocol,
            "created_at": created_at,
            "limitations": tuple(sorted(set(limitations))),
        }
        payload = _policy_set_payload(**values)
        owner_id, owner_hash = content_identity(
            "historical-strategy-economics-policy-set", payload
        )
        return cls(owner_id, owner_hash, **values)

    def identity_payload(self) -> dict[str, Any]:
        return _policy_set_payload(
            policy_set_version=self.policy_set_version,
            target_protocol_reference=self.target_protocol_reference,
            strategy_policies=self.strategy_policies,
            capacity_protocol=self.capacity_protocol,
            created_at=self.created_at,
            limitations=self.limitations,
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "policy_set_id": str(self.policy_set_id),
            "policy_set_hash": self.policy_set_hash,
            **self.identity_payload(),
        }

    @classmethod
    def from_canonical_dict(
        cls, value: Mapping[str, Any]
    ) -> HistoricalStrategyEconomicsPolicySet:
        raw_policies = value.get("strategy_policies")
        raw_limitations = value.get("limitations")
        if not isinstance(raw_policies, (list, tuple)):
            raise ValueError("Historical Strategy Economics policies are malformed")
        if not isinstance(raw_limitations, (list, tuple)):
            raise ValueError("Historical Strategy Economics limitations are malformed")
        return cls(
            policy_set_id=ArtifactId(str(value["policy_set_id"])),
            policy_set_hash=str(value["policy_set_hash"]),
            policy_set_version=str(value["policy_set_version"]),
            target_protocol_reference=ValidationArtifactReference.from_canonical_dict(
                _mapping(value["target_protocol_reference"])
            ),
            strategy_policies=tuple(
                StrategyEconomicsPolicy.from_canonical_dict(_mapping(item))
                for item in raw_policies
            ),
            capacity_protocol=LiquidityCapacityProtocol.from_canonical_dict(
                _mapping(value["capacity_protocol"])
            ),
            created_at=datetime.fromisoformat(str(value["created_at"])),
            limitations=tuple(str(item) for item in raw_limitations),
            schema_version=str(value["schema_version"]),
        )

    @property
    def reference(self) -> ValidationArtifactReference:
        return ValidationArtifactReference(
            HISTORICAL_STRATEGY_ECONOMICS_POLICY_SET_KIND,
            self.policy_set_id,
            self.policy_set_hash,
        )

    def policy_for_reference(
        self, reference: ValidationArtifactReference
    ) -> StrategyEconomicsPolicy:
        matched = tuple(
            item
            for item in self.strategy_policies
            if item.prediction_target_reference == reference
        )
        if len(matched) != 1:
            raise ValueError("Historical Strategy Economics Target policy is missing")
        return matched[0]


def _policy_set_payload(
    *,
    policy_set_version: str,
    target_protocol_reference: ValidationArtifactReference,
    strategy_policies: tuple[StrategyEconomicsPolicy, ...],
    capacity_protocol: LiquidityCapacityProtocol,
    created_at: datetime,
    limitations: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "schema_version": "historical-strategy-economics-policy-set/v1",
        "policy_set_version": policy_set_version,
        "target_protocol_reference": target_protocol_reference.to_canonical_dict(),
        "strategy_policies": [item.to_canonical_dict() for item in strategy_policies],
        "capacity_protocol": capacity_protocol.to_canonical_dict(),
        "created_at": timestamp(created_at),
        "limitations": list(limitations),
    }


def _mapping(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("Historical Strategy Economics payload is not an object")
    return value


__all__ = [
    "HISTORICAL_STRATEGY_ECONOMICS_POLICY_SET_KIND",
    "HistoricalStrategyEconomicsPolicySet",
]
