"""Exact existing Market references required by recorded daily normalization."""

from dataclasses import dataclass
from typing import Protocol

from market_regime_alpha.market.domain import ProviderCapture
from market_regime_alpha.market.domain.professional_daily import ProfessionalDailyContract
from market_regime_alpha.market.ports.session_roster import ArchiveTradingSession
from market_regime_alpha.shared.identity import InstrumentId


@dataclass(frozen=True, slots=True)
class ProfessionalInstrumentReference:
    stock_code: str
    instrument_id: InstrumentId
    sessions: tuple[ArchiveTradingSession, ...]


class ProfessionalNormalizationReferencePort(Protocol):
    def references(self, contract: ProfessionalDailyContract, capture: ProviderCapture) -> tuple[ProfessionalInstrumentReference, ...]: ...
