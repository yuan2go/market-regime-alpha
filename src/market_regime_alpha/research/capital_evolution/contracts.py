"""Capital Evolution contracts for observable-proxy model inferences."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite
from typing import Any

from market_regime_alpha.evidence.envelope import ArtifactEnvelope


class CapitalEvolutionState(str, Enum):
    DORMANT = "DORMANT"
    ACCUMULATION = "ACCUMULATION"
    IGNITION = "IGNITION"
    DIFFUSION = "DIFFUSION"
    ACCELERATION = "ACCELERATION"
    DIVERGENCE = "DIVERGENCE"
    EXHAUSTION = "EXHAUSTION"
    COLLAPSE = "COLLAPSE"
    DATA_INSUFFICIENT = "DATA_INSUFFICIENT"


@dataclass(frozen=True, slots=True)
class ThemeCapitalEvolution:
    theme_id: str
    capital_evolution_score: float | None
    capital_evolution_state: CapitalEvolutionState
    confidence: float
    theme_relative_strength: float | None
    etf_amount_expansion: float | None
    theme_amount_expansion: float | None
    breadth: float | None
    new_high_breadth: float | None
    leader_strength: float | None
    participation_expansion: float | None
    capital_concentration: float | None
    rank_persistence: float | None
    amount_persistence: float | None
    diffusion_score: float | None
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        _validate_score(self.capital_evolution_score)

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "theme_id": self.theme_id,
            "capital_evolution_score": self.capital_evolution_score,
            "capital_evolution_state": self.capital_evolution_state.value,
            "confidence": self.confidence,
            "theme_relative_strength": self.theme_relative_strength,
            "etf_amount_expansion": self.etf_amount_expansion,
            "theme_amount_expansion": self.theme_amount_expansion,
            "breadth": self.breadth,
            "new_high_breadth": self.new_high_breadth,
            "leader_strength": self.leader_strength,
            "participation_expansion": self.participation_expansion,
            "capital_concentration": self.capital_concentration,
            "rank_persistence": self.rank_persistence,
            "amount_persistence": self.amount_persistence,
            "diffusion_score": self.diffusion_score,
            "reason_codes": list(self.reason_codes),
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: dict[str, Any]
    ) -> ThemeCapitalEvolution:
        expected = {
            "theme_id",
            "capital_evolution_score",
            "capital_evolution_state",
            "confidence",
            "theme_relative_strength",
            "etf_amount_expansion",
            "theme_amount_expansion",
            "breadth",
            "new_high_breadth",
            "leader_strength",
            "participation_expansion",
            "capital_concentration",
            "rank_persistence",
            "amount_persistence",
            "diffusion_score",
            "reason_codes",
        }
        if set(payload) != expected:
            raise ValueError("ThemeCapitalEvolution fields mismatch")
        return cls(
            theme_id=str(payload["theme_id"]),
            capital_evolution_score=_optional_float(
                payload["capital_evolution_score"]
            ),
            capital_evolution_state=CapitalEvolutionState(
                str(payload["capital_evolution_state"])
            ),
            confidence=float(payload["confidence"]),
            theme_relative_strength=_optional_float(
                payload["theme_relative_strength"]
            ),
            etf_amount_expansion=_optional_float(
                payload["etf_amount_expansion"]
            ),
            theme_amount_expansion=_optional_float(
                payload["theme_amount_expansion"]
            ),
            breadth=_optional_float(payload["breadth"]),
            new_high_breadth=_optional_float(payload["new_high_breadth"]),
            leader_strength=_optional_float(payload["leader_strength"]),
            participation_expansion=_optional_float(
                payload["participation_expansion"]
            ),
            capital_concentration=_optional_float(
                payload["capital_concentration"]
            ),
            rank_persistence=_optional_float(payload["rank_persistence"]),
            amount_persistence=_optional_float(payload["amount_persistence"]),
            diffusion_score=_optional_float(payload["diffusion_score"]),
            reason_codes=_strings(payload["reason_codes"]),
        )


@dataclass(frozen=True, slots=True)
class SymbolCapitalEvolution:
    symbol: str
    theme_id: str
    symbol_relative_strength: float | None
    symbol_amount_expansion: float | None
    theme_participation_contribution: float | None
    leader_correlation: float | None
    leader_lag: float | None
    rank_persistence: float | None
    amount_persistence: float | None
    capital_evolution_score: float | None
    capital_evolution_state: CapitalEvolutionState
    confidence: float
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        _validate_score(self.capital_evolution_score)

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "theme_id": self.theme_id,
            "symbol_relative_strength": self.symbol_relative_strength,
            "symbol_amount_expansion": self.symbol_amount_expansion,
            "theme_participation_contribution": self.theme_participation_contribution,
            "leader_correlation": self.leader_correlation,
            "leader_lag": self.leader_lag,
            "rank_persistence": self.rank_persistence,
            "amount_persistence": self.amount_persistence,
            "capital_evolution_score": self.capital_evolution_score,
            "capital_evolution_state": self.capital_evolution_state.value,
            "confidence": self.confidence,
            "reason_codes": list(self.reason_codes),
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: dict[str, Any]
    ) -> SymbolCapitalEvolution:
        expected = {
            "symbol",
            "theme_id",
            "symbol_relative_strength",
            "symbol_amount_expansion",
            "theme_participation_contribution",
            "leader_correlation",
            "leader_lag",
            "rank_persistence",
            "amount_persistence",
            "capital_evolution_score",
            "capital_evolution_state",
            "confidence",
            "reason_codes",
        }
        if set(payload) != expected:
            raise ValueError("SymbolCapitalEvolution fields mismatch")
        return cls(
            symbol=str(payload["symbol"]),
            theme_id=str(payload["theme_id"]),
            symbol_relative_strength=_optional_float(
                payload["symbol_relative_strength"]
            ),
            symbol_amount_expansion=_optional_float(
                payload["symbol_amount_expansion"]
            ),
            theme_participation_contribution=_optional_float(
                payload["theme_participation_contribution"]
            ),
            leader_correlation=_optional_float(payload["leader_correlation"]),
            leader_lag=_optional_float(payload["leader_lag"]),
            rank_persistence=_optional_float(payload["rank_persistence"]),
            amount_persistence=_optional_float(payload["amount_persistence"]),
            capital_evolution_score=_optional_float(
                payload["capital_evolution_score"]
            ),
            capital_evolution_state=CapitalEvolutionState(
                str(payload["capital_evolution_state"])
            ),
            confidence=float(payload["confidence"]),
            reason_codes=_strings(payload["reason_codes"]),
        )


@dataclass(frozen=True, slots=True)
class CapitalEvolutionSnapshot:
    """Inferred states from observable proxies, not claims about hidden actors."""

    envelope: ArtifactEnvelope
    themes: tuple[ThemeCapitalEvolution, ...]
    symbols: tuple[SymbolCapitalEvolution, ...]
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if len({item.theme_id for item in self.themes}) != len(self.themes):
            raise ValueError("Capital Evolution themes must be unique")
        if len({item.symbol for item in self.symbols}) != len(self.symbols):
            raise ValueError("Capital Evolution symbols must be unique")
        self.envelope.verify_payload(self.artifact_payload())

    def artifact_payload(self) -> dict[str, Any]:
        return {
            "themes": [item.to_canonical_dict() for item in self.themes],
            "symbols": [item.to_canonical_dict() for item in self.symbols],
            "reason_codes": list(self.reason_codes),
        }

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "envelope": self.envelope.to_canonical_dict(),
            **self.artifact_payload(),
        }

    @classmethod
    def from_canonical_dict(
        cls, payload: dict[str, Any]
    ) -> CapitalEvolutionSnapshot:
        if set(payload) != {
            "envelope",
            "themes",
            "symbols",
            "reason_codes",
        }:
            raise ValueError("CapitalEvolutionSnapshot fields mismatch")
        return cls(
            envelope=ArtifactEnvelope.from_canonical_dict(
                _object(payload["envelope"])
            ),
            themes=tuple(
                ThemeCapitalEvolution.from_canonical_dict(_object(item))
                for item in _array(payload["themes"])
            ),
            symbols=tuple(
                SymbolCapitalEvolution.from_canonical_dict(_object(item))
                for item in _array(payload["symbols"])
            ),
            reason_codes=_strings(payload["reason_codes"]),
        )


def _validate_score(value: float | None) -> None:
    if value is not None and (
        not isfinite(value) or not -1.0 <= value <= 1.0
    ):
        raise ValueError("Capital Evolution score must be within [-1, 1]")


def _object(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("Capital Evolution value must be an object")
    return value


def _array(value: object) -> list[object]:
    if not isinstance(value, list):
        raise ValueError("Capital Evolution value must be an array")
    return value


def _strings(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) for item in value
    ):
        raise ValueError("Capital Evolution value must be a string array")
    return tuple(value)


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("Capital Evolution value must be numeric")
    return float(value)
