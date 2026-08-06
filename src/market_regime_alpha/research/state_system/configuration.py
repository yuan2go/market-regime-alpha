"""Explicit versioned transition configuration selected by Runtime Policy."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Any, ClassVar, Mapping, Self

from market_regime_alpha.core.identity import ArtifactId, ModelId
from market_regime_alpha.evidence.canonical import canonical_hash, require_sha256, require_text


class MissingDataPolicy(str, Enum):
    FAIL_CLOSED = "FAIL_CLOSED"
    RETAIN_WITHIN_DWELL = "RETAIN_WITHIN_DWELL"


def _fraction(label: str, value: Decimal) -> None:
    if not isinstance(value, Decimal):
        raise TypeError(f"{label} must be Decimal")
    if not Decimal("0") <= value <= Decimal("1"):
        raise ValueError(f"{label} must be within [0, 1]")


@dataclass(frozen=True, slots=True)
class TransitionThresholds:
    enter_threshold: Decimal
    exit_threshold: Decimal
    hysteresis: Decimal
    confirmation_count: int
    minimum_dwell_seconds: int
    minimum_coverage: Decimal
    missing_data_policy: MissingDataPolicy

    def __post_init__(self) -> None:
        _fraction("enter_threshold", self.enter_threshold)
        _fraction("exit_threshold", self.exit_threshold)
        _fraction("hysteresis", self.hysteresis)
        _fraction("minimum_coverage", self.minimum_coverage)
        if self.enter_threshold <= self.exit_threshold:
            raise ValueError("enter_threshold must exceed exit_threshold")
        if self.hysteresis != self.enter_threshold - self.exit_threshold:
            raise ValueError("hysteresis must equal enter_threshold minus exit_threshold")
        if isinstance(self.confirmation_count, bool) or self.confirmation_count <= 0:
            raise ValueError("confirmation_count must be positive")
        if isinstance(self.minimum_dwell_seconds, bool) or self.minimum_dwell_seconds < 0:
            raise ValueError("minimum_dwell_seconds must be non-negative")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "enter_threshold": str(self.enter_threshold),
            "exit_threshold": str(self.exit_threshold),
            "hysteresis": str(self.hysteresis),
            "confirmation_count": self.confirmation_count,
            "minimum_dwell_seconds": self.minimum_dwell_seconds,
            "minimum_coverage": str(self.minimum_coverage),
            "missing_data_policy": self.missing_data_policy.value,
        }

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> TransitionThresholds:
        expected = {
            "enter_threshold",
            "exit_threshold",
            "hysteresis",
            "confirmation_count",
            "minimum_dwell_seconds",
            "minimum_coverage",
            "missing_data_policy",
        }
        if set(payload) != expected:
            raise ValueError("TransitionThresholds fields mismatch")
        return cls(
            enter_threshold=Decimal(str(payload["enter_threshold"])),
            exit_threshold=Decimal(str(payload["exit_threshold"])),
            hysteresis=Decimal(str(payload["hysteresis"])),
            confirmation_count=int(payload["confirmation_count"]),
            minimum_dwell_seconds=int(payload["minimum_dwell_seconds"]),
            minimum_coverage=Decimal(str(payload["minimum_coverage"])),
            missing_data_policy=MissingDataPolicy(str(payload["missing_data_policy"])),
        )


@dataclass(frozen=True, slots=True)
class VersionedStateConfiguration:
    model_id: ModelId
    model_version: str
    configuration_id: ArtifactId
    configuration_version: str
    configuration_hash: str
    thresholds: TransitionThresholds

    DOMAIN: ClassVar[str] = "BASE"

    def __post_init__(self) -> None:
        require_text("model_version", self.model_version)
        require_text("configuration_version", self.configuration_version)
        require_sha256("configuration_hash", self.configuration_hash)
        if self.configuration_hash != canonical_hash(self.identity_payload()):
            raise ValueError("configuration_hash does not match configuration content")

    def identity_payload(self) -> dict[str, Any]:
        return {
            "domain": self.DOMAIN,
            "model_id": str(self.model_id),
            "model_version": self.model_version,
            "configuration_id": str(self.configuration_id),
            "configuration_version": self.configuration_version,
            "thresholds": self.thresholds.to_canonical_dict(),
        }

    def to_canonical_dict(self) -> dict[str, Any]:
        return {**self.identity_payload(), "configuration_hash": self.configuration_hash}

    @classmethod
    def create(
        cls,
        *,
        model_id: ModelId,
        model_version: str,
        configuration_id: ArtifactId,
        configuration_version: str,
        thresholds: TransitionThresholds,
    ) -> Self:
        require_text("model_version", model_version)
        require_text("configuration_version", configuration_version)
        identity = {
            "domain": cls.DOMAIN,
            "model_id": str(model_id),
            "model_version": model_version,
            "configuration_id": str(configuration_id),
            "configuration_version": configuration_version,
            "thresholds": thresholds.to_canonical_dict(),
        }
        return cls(
            model_id=model_id,
            model_version=model_version,
            configuration_id=configuration_id,
            configuration_version=configuration_version,
            configuration_hash=canonical_hash(identity),
            thresholds=thresholds,
        )

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> Self:
        expected = {
            "domain",
            "model_id",
            "model_version",
            "configuration_id",
            "configuration_version",
            "configuration_hash",
            "thresholds",
        }
        if set(payload) != expected or payload["domain"] != cls.DOMAIN:
            raise ValueError(f"{cls.__name__} fields/domain mismatch")
        threshold_payload = payload["thresholds"]
        if not isinstance(threshold_payload, Mapping):
            raise ValueError("thresholds must be an object")
        return cls(
            model_id=ModelId(str(payload["model_id"])),
            model_version=str(payload["model_version"]),
            configuration_id=ArtifactId(str(payload["configuration_id"])),
            configuration_version=str(payload["configuration_version"]),
            configuration_hash=str(payload["configuration_hash"]),
            thresholds=TransitionThresholds.from_canonical_dict(threshold_payload),
        )


@dataclass(frozen=True, slots=True)
class MarketStateConfiguration(VersionedStateConfiguration):
    DOMAIN: ClassVar[str] = "MARKET_REGIME"


@dataclass(frozen=True, slots=True)
class EtfRotationConfiguration(VersionedStateConfiguration):
    DOMAIN: ClassVar[str] = "ETF_ROTATION"


@dataclass(frozen=True, slots=True)
class ThemeRotationConfiguration(VersionedStateConfiguration):
    DOMAIN: ClassVar[str] = "THEME_ROTATION"


@dataclass(frozen=True, slots=True)
class CapitalStateConfiguration(VersionedStateConfiguration):
    DOMAIN: ClassVar[str] = "CAPITAL_STATE"
