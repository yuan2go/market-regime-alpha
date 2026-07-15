"""Canonical point-in-time universe and trading-eligibility contracts.

Universe membership and trading eligibility are intentionally separate. Membership says
an instrument belongs to a research population. Trading eligibility says whether the
instrument may enter a candidate population under a declared eligibility policy.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from market_regime_alpha.core.identity import ArtifactId, DatasetId, UniverseId
from market_regime_alpha.core.time import AsOfTime


def _validate_symbol(value: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError("symbol must be a non-empty trimmed string")
    return value


@dataclass(frozen=True, slots=True)
class UniverseMembershipRecord:
    """Membership state for one instrument inside one PIT universe snapshot."""

    symbol: str
    is_member: bool

    def __post_init__(self) -> None:
        _validate_symbol(self.symbol)
        if not isinstance(self.is_member, bool):
            raise TypeError("is_member must be boolean")


@dataclass(frozen=True, slots=True)
class PITUniverseSnapshot:
    """Point-in-time universe membership snapshot for a declared as-of time."""

    universe_id: UniverseId
    as_of: AsOfTime
    source_dataset_id: DatasetId
    evidence_artifact_id: ArtifactId
    method_version: str
    records: tuple[UniverseMembershipRecord, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.method_version, str) or not self.method_version.strip() or self.method_version != self.method_version.strip():
            raise ValueError("method_version must be a non-empty trimmed string")
        symbols = [record.symbol for record in self.records]
        if len(symbols) != len(set(symbols)):
            raise ValueError("universe records must have unique symbols")

    @property
    def member_symbols(self) -> tuple[str, ...]:
        return tuple(sorted(record.symbol for record in self.records if record.is_member))


class TradingEligibilityStatus(str, Enum):
    """Declared trading/research eligibility under a specific eligibility policy."""

    ELIGIBLE = "ELIGIBLE"
    INELIGIBLE = "INELIGIBLE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class TradingEligibilityRecord:
    """Eligibility result for one instrument without redefining universe membership."""

    symbol: str
    status: TradingEligibilityStatus
    reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _validate_symbol(self.symbol)


@dataclass(frozen=True, slots=True)
class TradingEligibilitySnapshot:
    """Point-in-time eligibility snapshot used to filter a universe into candidates."""

    as_of: AsOfTime
    source_dataset_id: DatasetId
    evidence_artifact_id: ArtifactId
    records: tuple[TradingEligibilityRecord, ...]

    def __post_init__(self) -> None:
        symbols = [record.symbol for record in self.records]
        if len(symbols) != len(set(symbols)):
            raise ValueError("trading eligibility records must have unique symbols")

    def status_for(self, symbol: str) -> TradingEligibilityStatus:
        for record in self.records:
            if record.symbol == symbol:
                return record.status
        return TradingEligibilityStatus.UNKNOWN
