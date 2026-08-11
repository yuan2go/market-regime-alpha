"""Typed C0 owners for Feature definitions and threshold semantics.

These contracts freeze result-affecting research inputs.  They do not qualify
data, establish Formal OOS, or grant Production authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Mapping

from market_regime_alpha.application.research_validation.common import (
    content_identity,
    decimal_text,
    timestamp,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash, require_sha256, require_text
from market_regime_alpha.features.spine import FeatureDefinitionV2


@dataclass(frozen=True, slots=True)
class FeatureDefinitionSet:
    definition_set_id: ArtifactId
    definition_set_hash: str
    definition_set_version: str
    definitions: tuple[FeatureDefinitionV2, ...]
    locked_at: datetime
    schema_version: str = "feature-definition-set/v1"

    def __post_init__(self) -> None:
        require_sha256("definition_set_hash", self.definition_set_hash)
        require_text("definition_set_version", self.definition_set_version)
        if self.schema_version != "feature-definition-set/v1":
            raise ValueError("unsupported Feature Definition Set schema")
        if self.locked_at.tzinfo is None or self.locked_at.utcoffset() is None:
            raise ValueError("Feature Definition Set lock time must be timezone-aware")
        keys = tuple(str(item.definition_id) for item in self.definitions)
        if not keys or keys != tuple(sorted(set(keys))):
            raise ValueError("Feature definitions must be non-empty, unique and sorted")
        for definition in self.definitions:
            definition.verify_identity()
        if canonical_hash(self.identity_payload()) != self.definition_set_hash:
            raise ValueError("Feature Definition Set hash mismatch")
        if self.definition_set_id != ArtifactId(
            f"feature-definition-set:{self.definition_set_hash[7:]}"
        ):
            raise ValueError("Feature Definition Set identity mismatch")

    @classmethod
    def create(
        cls,
        *,
        definition_set_version: str,
        definitions: tuple[FeatureDefinitionV2, ...],
        locked_at: datetime,
    ) -> FeatureDefinitionSet:
        ordered = tuple(sorted(definitions, key=lambda item: str(item.definition_id)))
        payload = _feature_definition_set_payload(
            definition_set_version=definition_set_version,
            definitions=ordered,
            locked_at=locked_at,
        )
        artifact_id, digest = content_identity("feature-definition-set", payload)
        return cls(
            artifact_id,
            digest,
            definition_set_version,
            ordered,
            locked_at,
        )

    def identity_payload(self) -> dict[str, Any]:
        return _feature_definition_set_payload(
            definition_set_version=self.definition_set_version,
            definitions=self.definitions,
            locked_at=self.locked_at,
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "definition_set_id": str(self.definition_set_id),
            "definition_set_hash": self.definition_set_hash,
            **self.identity_payload(),
        }

    @classmethod
    def from_canonical_dict(cls, value: Mapping[str, Any]) -> FeatureDefinitionSet:
        raw_definitions = value["definitions"]
        if not isinstance(raw_definitions, list):
            raise ValueError("Feature Definition Set definitions must be an array")
        return cls(
            definition_set_id=ArtifactId(str(value["definition_set_id"])),
            definition_set_hash=str(value["definition_set_hash"]),
            definition_set_version=str(value["definition_set_version"]),
            definitions=tuple(
                FeatureDefinitionV2.from_canonical_dict(_mapping(item))
                for item in raw_definitions
            ),
            locked_at=datetime.fromisoformat(str(value["locked_at"])),
            schema_version=str(value["schema_version"]),
        )


class ThresholdComparison(str, Enum):
    GREATER_THAN = "GREATER_THAN"
    GREATER_THAN_OR_EQUAL = "GREATER_THAN_OR_EQUAL"
    LESS_THAN = "LESS_THAN"
    LESS_THAN_OR_EQUAL = "LESS_THAN_OR_EQUAL"


@dataclass(frozen=True, slots=True)
class ThresholdRule:
    name: str
    comparison: ThresholdComparison
    value: Decimal

    def __post_init__(self) -> None:
        require_text("threshold rule name", self.name)
        if not self.value.is_finite():
            raise ValueError("Threshold rule value must be finite")

    def to_canonical_dict(self) -> dict[str, str]:
        return {
            "name": self.name,
            "comparison": self.comparison.value,
            "value": decimal_text(self.value),
        }

    @classmethod
    def from_canonical_dict(cls, value: Mapping[str, Any]) -> ThresholdRule:
        if set(value) != {"name", "comparison", "value"}:
            raise ValueError("Threshold Rule fields mismatch")
        return cls(
            name=str(value["name"]),
            comparison=ThresholdComparison(str(value["comparison"])),
            value=Decimal(str(value["value"])),
        )


@dataclass(frozen=True, slots=True)
class ThresholdPolicy:
    policy_id: ArtifactId
    policy_hash: str
    policy_version: str
    rules: tuple[ThresholdRule, ...]
    locked_at: datetime
    schema_version: str = "threshold-policy/v1"

    def __post_init__(self) -> None:
        require_sha256("policy_hash", self.policy_hash)
        require_text("policy_version", self.policy_version)
        if self.schema_version != "threshold-policy/v1":
            raise ValueError("unsupported Threshold Policy schema")
        if self.locked_at.tzinfo is None or self.locked_at.utcoffset() is None:
            raise ValueError("Threshold Policy lock time must be timezone-aware")
        names = tuple(item.name for item in self.rules)
        if not names or names != tuple(sorted(set(names))):
            raise ValueError("Threshold rules must be non-empty, unique and sorted")
        if canonical_hash(self.identity_payload()) != self.policy_hash:
            raise ValueError("Threshold Policy hash mismatch")
        if self.policy_id != ArtifactId(f"threshold-policy:{self.policy_hash[7:]}"):
            raise ValueError("Threshold Policy identity mismatch")

    @classmethod
    def create(
        cls,
        *,
        policy_version: str,
        rules: tuple[ThresholdRule, ...],
        locked_at: datetime,
    ) -> ThresholdPolicy:
        ordered = tuple(sorted(rules, key=lambda item: item.name))
        payload = _threshold_policy_payload(
            policy_version=policy_version,
            rules=ordered,
            locked_at=locked_at,
        )
        policy_id, digest = content_identity("threshold-policy", payload)
        return cls(policy_id, digest, policy_version, ordered, locked_at)

    def identity_payload(self) -> dict[str, Any]:
        return _threshold_policy_payload(
            policy_version=self.policy_version,
            rules=self.rules,
            locked_at=self.locked_at,
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "policy_id": str(self.policy_id),
            "policy_hash": self.policy_hash,
            **self.identity_payload(),
        }

    @classmethod
    def from_canonical_dict(cls, value: Mapping[str, Any]) -> ThresholdPolicy:
        raw_rules = value["rules"]
        if not isinstance(raw_rules, list):
            raise ValueError("Threshold Policy rules must be an array")
        return cls(
            policy_id=ArtifactId(str(value["policy_id"])),
            policy_hash=str(value["policy_hash"]),
            policy_version=str(value["policy_version"]),
            rules=tuple(
                ThresholdRule.from_canonical_dict(_mapping(item)) for item in raw_rules
            ),
            locked_at=datetime.fromisoformat(str(value["locked_at"])),
            schema_version=str(value["schema_version"]),
        )


def _feature_definition_set_payload(
    *,
    definition_set_version: str,
    definitions: tuple[FeatureDefinitionV2, ...],
    locked_at: datetime,
) -> dict[str, Any]:
    return {
        "schema_version": "feature-definition-set/v1",
        "definition_set_version": definition_set_version,
        "definitions": [item.to_canonical_dict() for item in definitions],
        "locked_at": timestamp(locked_at),
    }


def _threshold_policy_payload(
    *,
    policy_version: str,
    rules: tuple[ThresholdRule, ...],
    locked_at: datetime,
) -> dict[str, Any]:
    return {
        "schema_version": "threshold-policy/v1",
        "policy_version": policy_version,
        "rules": [item.to_canonical_dict() for item in rules],
        "locked_at": timestamp(locked_at),
        "automatic_tuning": False,
    }


def _mapping(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("expected object payload")
    return value


__all__ = [
    "FeatureDefinitionSet",
    "ThresholdComparison",
    "ThresholdPolicy",
    "ThresholdRule",
]
