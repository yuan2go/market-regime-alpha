"""Versioned Signal Layer output boundary."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite
from typing import Any

from market_regime_alpha.evidence.envelope import ArtifactEnvelope


class SignalFamily(str, Enum):
    BREAKOUT = "BREAKOUT"
    PULLBACK = "PULLBACK"
    TREND_CONTINUATION = "TREND_CONTINUATION"
    REVERSAL = "REVERSAL"
    OVERNIGHT_MOMENTUM = "OVERNIGHT_MOMENTUM"


class SignalState(str, Enum):
    INACTIVE = "INACTIVE"
    WATCH = "WATCH"
    CONFIRMED_FOR_RESEARCH = "CONFIRMED_FOR_RESEARCH"
    DATA_INSUFFICIENT = "DATA_INSUFFICIENT"


class ConfirmationState(str, Enum):
    CONFIRMED = "CONFIRMED"
    UNCONFIRMED = "UNCONFIRMED"
    CONTRADICTED = "CONTRADICTED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class SignalSnapshot:
    envelope: ArtifactEnvelope
    symbol: str
    signal_family: SignalFamily
    signal_state: SignalState
    price_action_state: ConfirmationState
    volume_confirmation_state: ConfirmationState
    trend_confirmation_state: ConfirmationState
    vwap_state: ConfirmationState
    overheat_state: ConfirmationState
    signal_score: float | None
    confidence: float
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.signal_score is not None and (
            not isfinite(self.signal_score)
            or not -1.0 <= self.signal_score <= 1.0
        ):
            raise ValueError("Signal score must be within [-1, 1]")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("Signal confidence must be within [0, 1]")
        self.envelope.verify_payload(self.artifact_payload())

    def artifact_payload(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "signal_family": self.signal_family.value,
            "signal_state": self.signal_state.value,
            "price_action_state": self.price_action_state.value,
            "volume_confirmation_state": self.volume_confirmation_state.value,
            "trend_confirmation_state": self.trend_confirmation_state.value,
            "vwap_state": self.vwap_state.value,
            "overheat_state": self.overheat_state.value,
            "signal_score": self.signal_score,
            "confidence": self.confidence,
            "reason_codes": list(self.reason_codes),
        }

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "envelope": self.envelope.to_canonical_dict(),
            **self.artifact_payload(),
        }

    @classmethod
    def from_canonical_dict(cls, payload: dict[str, Any]) -> SignalSnapshot:
        expected = {
            "envelope",
            "symbol",
            "signal_family",
            "signal_state",
            "price_action_state",
            "volume_confirmation_state",
            "trend_confirmation_state",
            "vwap_state",
            "overheat_state",
            "signal_score",
            "confidence",
            "reason_codes",
        }
        if set(payload) != expected:
            raise ValueError("SignalSnapshot fields mismatch")
        envelope = payload["envelope"]
        reason_codes = payload["reason_codes"]
        if not isinstance(envelope, dict) or not isinstance(reason_codes, list):
            raise ValueError("SignalSnapshot canonical value type mismatch")
        score = payload["signal_score"]
        return cls(
            envelope=ArtifactEnvelope.from_canonical_dict(envelope),
            symbol=str(payload["symbol"]),
            signal_family=SignalFamily(str(payload["signal_family"])),
            signal_state=SignalState(str(payload["signal_state"])),
            price_action_state=ConfirmationState(
                str(payload["price_action_state"])
            ),
            volume_confirmation_state=ConfirmationState(
                str(payload["volume_confirmation_state"])
            ),
            trend_confirmation_state=ConfirmationState(
                str(payload["trend_confirmation_state"])
            ),
            vwap_state=ConfirmationState(str(payload["vwap_state"])),
            overheat_state=ConfirmationState(str(payload["overheat_state"])),
            signal_score=float(score) if score is not None else None,
            confidence=float(payload["confidence"]),
            reason_codes=tuple(str(item) for item in reason_codes),
        )
