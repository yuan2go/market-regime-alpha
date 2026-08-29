"""Cohesive PostgreSQL Market query responsibility."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any


from market_regime_alpha.infrastructure.postgres.queries._market_mapping import (
    _bar,
    _decision_time,
    _session,
)
from market_regime_alpha.infrastructure.postgres.queries._market_sql import (
    _EXACT_BAR_SQL,
    _TRADING_SESSION_SQL,
)
from market_regime_alpha.market.domain import (
    BarTimeframe,
    GapFactKind,
    MarketBarRevision,
    PriceBasis,
    TradingSession,
)
from market_regime_alpha.runtime.errors import ArtifactIntegrityError
from market_regime_alpha.shared.identity import InstrumentId, TradingSessionId
from market_regime_alpha.shared.time import DecisionTime, require_utc

from market_regime_alpha.infrastructure.postgres.queries._market_support import _MarketQuerySupport


class _BarSessionQueries(_MarketQuerySupport):
    def exact_bar_as_of(
        self,
        *,
        instrument_id: InstrumentId,
        session_id: TradingSessionId,
        timeframe: BarTimeframe,
        price_basis: PriceBasis,
        event_start: datetime,
        event_end: datetime,
        decision_time: DecisionTime,
    ) -> MarketBarRevision | None:
        event_start = require_utc(event_start, field="event_start")
        event_end = require_utc(event_end, field="event_end")
        instrument_id = InstrumentId.parse(instrument_id)
        session_id = TradingSessionId.parse(session_id)
        decision_time = _decision_time(decision_time)
        if decision_time.value < event_end:
            return None
        with self._connection_scope() as connection:
            row = connection.execute(
                _EXACT_BAR_SQL,
                (
                    self._provider_product_id,
                    instrument_id.value,
                    session_id.value,
                    timeframe.value,
                    price_basis.value,
                    event_start,
                    event_end,
                    decision_time.value,
                    decision_time.value,
                ),
            ).fetchone()
        if row is None:
            self._raise_if_gap_is_current(
                fact_kind=GapFactKind.MARKET_BAR,
                decision_time=decision_time,
                fact_decision_visible_at=None,
                instrument_id=instrument_id,
                session_id=session_id,
                timeframe=timeframe,
                price_basis=price_basis,
                interval_semantics="EVENT_EXACT",
                event_start=event_start,
                event_end=event_end,
            )
            return None
        if any((row[index] is not True for index in (18, 19, 20))):
            raise ArtifactIntegrityError("current MarketBar evidence Artifact is not AVAILABLE")
        return _bar(row)

    def trading_session_as_of(self, *, exchange: str, session_date: date, decision_time: DecisionTime) -> TradingSession | None:
        decision_time = _decision_time(decision_time)
        with self._connection_scope() as connection:
            row = connection.execute(_TRADING_SESSION_SQL, (exchange, session_date, decision_time.value)).fetchone()
        if row is None:
            self._raise_if_gap_is_current(
                fact_kind=GapFactKind.TRADING_SESSION,
                decision_time=decision_time,
                fact_decision_visible_at=None,
                exchange=exchange,
                session_date=session_date,
            )
            return None
        if row[10] is not True:
            raise ArtifactIntegrityError("current TradingSession evidence Artifact is not AVAILABLE")
        return _session(row)

    def explain_exact_bar_as_of(
        self,
        *,
        instrument_id: InstrumentId,
        session_id: TradingSessionId,
        event_start: datetime,
        event_end: datetime,
        decision_time: DecisionTime,
    ) -> dict[str, Any]:
        """Representative plan evidence; callers must not depend on its exact shape."""
        return self._explain(
            _EXACT_BAR_SQL,
            (
                self._provider_product_id,
                InstrumentId.parse(instrument_id).value,
                TradingSessionId.parse(session_id).value,
                BarTimeframe.MINUTE_5.value,
                PriceBasis.RAW_UNADJUSTED.value,
                event_start,
                event_end,
                _decision_time(decision_time).value,
                _decision_time(decision_time).value,
            ),
        )

    def explain_trading_session_as_of(self, *, exchange: str, session_date: date, decision_time: DecisionTime) -> dict[str, Any]:
        return self._explain(_TRADING_SESSION_SQL, (exchange, session_date, _decision_time(decision_time).value))
