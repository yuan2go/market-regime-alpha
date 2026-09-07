"""Separate sealed historical and actual-time reads of one daily Feature."""

from datetime import date, datetime
from typing import Protocol
from uuid import UUID

from market_regime_alpha.research_qualification.domain.daily_inputs import DailyInputMember
from market_regime_alpha.research_qualification.domain.exploratory import ExploratoryRetrospectiveDatasetScope
from market_regime_alpha.shared.identity import InstrumentId


class DailyFeatureInputReadPort(Protocol):
    def archived(
        self, *, scope: ExploratoryRetrospectiveDatasetScope, instrument_id: InstrumentId, session_date: date
    ) -> DailyInputMember: ...

    def visible(
        self, *, provider_product_id: UUID, session_id: UUID, instrument_ids: tuple[UUID, ...], input_cutoff: datetime
    ) -> tuple[DailyInputMember, ...]: ...
