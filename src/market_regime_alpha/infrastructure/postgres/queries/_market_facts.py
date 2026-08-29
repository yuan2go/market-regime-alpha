"""Cohesive PostgreSQL Market query responsibility."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID


from market_regime_alpha.infrastructure.postgres.queries._market_mapping import (
    _decision_time,
)
from market_regime_alpha.market.domain import (
    EvidenceScope,
    GapFactKind,
    InstrumentFactKind,
    InstrumentFactRevision,
    ListingStatus,
    NumericInstrumentFactKind,
    SecurityStatus,
    SpecialTreatmentStatus,
)
from market_regime_alpha.runtime.errors import ArtifactIntegrityError
from market_regime_alpha.shared.financial import Money, Quantity, QuantityUnit
from market_regime_alpha.shared.identity import InstrumentId, TradingSessionId
from market_regime_alpha.shared.time import DecisionTime, require_utc

from market_regime_alpha.infrastructure.postgres.queries._market_support import _MarketQuerySupport


class _InstrumentFactQueries(_MarketQuerySupport):
    def security_status_as_of(
        self, *, instrument_id: InstrumentId, session_id: TradingSessionId, evidence_scope: EvidenceScope, decision_time: DecisionTime
    ) -> SecurityStatus | None:
        instrument_id = InstrumentId.parse(instrument_id)
        session_id = TradingSessionId.parse(session_id)
        decision_time = _decision_time(decision_time)
        with self._connection_scope() as connection:
            row = connection.execute(
                "\n                WITH current_fact AS (\n                    SELECT fact.*\n                    FROM mra.instrument_fact_revision AS fact\n                    WHERE fact.provider_product_id = %s\n                      AND fact.instrument_id = %s\n                      AND fact.session_id = %s\n                      AND fact.fact_kind = 'SECURITY_STATUS'\n                      AND fact.evidence_scope = %s\n                      AND fact.decision_visible_at <= %s\n                    ORDER BY fact.decision_visible_at DESC,\n                             fact.revision DESC,\n                             fact.fact_revision_id DESC\n                    LIMIT 1\n                )\n                SELECT fact.status_value,\n                       mra.market_artifact_is_readable(\n                           artifact.integrity_state, artifact.last_verified_at\n                       ),\n                       fact.decision_visible_at,\n                       mra.market_artifact_is_readable(\n                           instrument_artifact.integrity_state,\n                           instrument_artifact.last_verified_at\n                       ),\n                       mra.market_artifact_is_readable(\n                           session_artifact.integrity_state,\n                           session_artifact.last_verified_at\n                       )\n                FROM current_fact AS fact\n                JOIN mra.data_capture AS capture ON capture.capture_id = fact.capture_id\n                JOIN mra.artifact AS artifact ON artifact.artifact_id = capture.artifact_id\n                JOIN mra.instrument AS instrument\n                  ON instrument.instrument_id = fact.instrument_id\n                JOIN mra.data_capture AS instrument_capture\n                  ON instrument_capture.capture_id = instrument.source_capture_id\n                JOIN mra.artifact AS instrument_artifact\n                  ON instrument_artifact.artifact_id = instrument_capture.artifact_id\n                JOIN mra.trading_session AS session\n                  ON session.session_id = fact.session_id\n                JOIN mra.data_capture AS session_capture\n                  ON session_capture.capture_id = session.source_capture_id\n                JOIN mra.artifact AS session_artifact\n                  ON session_artifact.artifact_id = session_capture.artifact_id\n                WHERE capture.status = 'CAPTURED'\n                ",
                (self._provider_product_id, instrument_id.value, session_id.value, evidence_scope.value, decision_time.value),
            ).fetchone()
        self._raise_if_gap_is_current(
            fact_kind=GapFactKind.INSTRUMENT_FACT,
            decision_time=decision_time,
            fact_decision_visible_at=row[2] if row is not None else None,
            instrument_id=instrument_id,
            session_id=session_id,
            instrument_fact_kind=InstrumentFactKind.SECURITY_STATUS,
            evidence_scope=evidence_scope,
            interval_semantics="EVENT_ANY",
        )
        if row is None:
            return None
        if any((row[index] is not True for index in (1, 3, 4))):
            raise ArtifactIntegrityError("current SecurityStatus evidence or reference Authority Artifact is not AVAILABLE")
        return SecurityStatus(str(row[0]))

    def instrument_fact_as_of(
        self,
        *,
        instrument_id: InstrumentId,
        fact_kind: NumericInstrumentFactKind,
        evidence_scope: EvidenceScope,
        event_time: datetime,
        decision_time: DecisionTime,
        session_id: TradingSessionId | None = None,
    ) -> InstrumentFactRevision | None:
        event_time = require_utc(event_time, field="event_time")
        instrument_id = InstrumentId.parse(instrument_id)
        decision_time = _decision_time(decision_time)
        if session_id is not None:
            session_id = TradingSessionId.parse(session_id)
        if (evidence_scope is EvidenceScope.EFFECTIVE_INTERVAL) != (session_id is None):
            raise ValueError("effective facts omit Session; session facts require exact Session")
        with self._connection_scope() as connection:
            row = connection.execute(
                "\n                WITH current_fact AS (\n                    SELECT DISTINCT ON (fact.event_start) fact.*\n                    FROM mra.instrument_fact_revision AS fact\n                    WHERE fact.provider_product_id = %s\n                      AND fact.instrument_id = %s\n                      AND fact.fact_kind = %s\n                      AND fact.evidence_scope = %s\n                      AND fact.session_id IS NOT DISTINCT FROM %s\n                      AND fact.decision_visible_at <= %s\n                    ORDER BY fact.event_start,\n                             fact.decision_visible_at DESC,\n                             fact.revision DESC,\n                             fact.fact_revision_id DESC\n                ), selected_fact AS (\n                    SELECT fact.*\n                    FROM current_fact AS fact\n                    WHERE fact.event_start <= %s\n                    ORDER BY fact.event_start DESC,\n                             fact.decision_visible_at DESC,\n                             fact.revision DESC,\n                             fact.fact_revision_id DESC\n                    LIMIT 1\n                )\n                SELECT fact.fact_revision_id, fact.provider_product_id,\n                       fact.capture_id, fact.instrument_id, fact.session_id,\n                       fact.fact_kind, fact.evidence_scope, fact.event_start,\n                       fact.event_end, fact.numeric_value, fact.unit_code,\n                       fact.revision, fact.supersedes_revision_id,\n                       mra.market_artifact_is_readable(\n                           artifact.integrity_state, artifact.last_verified_at\n                       ), fact.decision_visible_at,\n                       mra.market_artifact_is_readable(\n                           instrument_artifact.integrity_state,\n                           instrument_artifact.last_verified_at\n                       ),\n                       mra.market_artifact_is_readable(\n                           session_artifact.integrity_state,\n                           session_artifact.last_verified_at\n                       )\n                FROM selected_fact AS fact\n                JOIN mra.data_capture AS capture ON capture.capture_id = fact.capture_id\n                JOIN mra.artifact AS artifact ON artifact.artifact_id = capture.artifact_id\n                JOIN mra.instrument AS instrument\n                  ON instrument.instrument_id = fact.instrument_id\n                JOIN mra.data_capture AS instrument_capture\n                  ON instrument_capture.capture_id = instrument.source_capture_id\n                JOIN mra.artifact AS instrument_artifact\n                  ON instrument_artifact.artifact_id = instrument_capture.artifact_id\n                LEFT JOIN mra.trading_session AS session\n                  ON session.session_id = fact.session_id\n                LEFT JOIN mra.data_capture AS session_capture\n                  ON session_capture.capture_id = session.source_capture_id\n                LEFT JOIN mra.artifact AS session_artifact\n                  ON session_artifact.artifact_id = session_capture.artifact_id\n                WHERE capture.status = 'CAPTURED'\n                ",
                (
                    self._provider_product_id,
                    instrument_id.value,
                    fact_kind.value,
                    evidence_scope.value,
                    session_id.value if session_id is not None else None,
                    decision_time.value,
                    event_time,
                ),
            ).fetchone()
        self._raise_if_gap_is_current(
            fact_kind=GapFactKind.INSTRUMENT_FACT,
            decision_time=decision_time,
            fact_decision_visible_at=row[14] if row is not None and (row[8] is None or row[8] > event_time) else None,
            instrument_id=instrument_id,
            session_id=session_id,
            instrument_fact_kind=InstrumentFactKind(fact_kind.value),
            evidence_scope=evidence_scope,
            interval_semantics="EFFECTIVE" if evidence_scope is EvidenceScope.EFFECTIVE_INTERVAL else "EVENT",
            interval_time=event_time,
        )
        if row is None:
            return None
        if any((row[index] is not True for index in (13, 15))) or (session_id is not None and row[16] is not True):
            raise ArtifactIntegrityError("current InstrumentFact or Instrument Authority Artifact is not AVAILABLE")
        if row[8] is not None and row[8] <= event_time:
            return None
        return InstrumentFactRevision(
            fact_revision_id=UUID(str(row[0])),
            provider_product_id=UUID(str(row[1])),
            capture_id=UUID(str(row[2])),
            instrument_id=InstrumentId.parse(row[3]),
            session_id=TradingSessionId.parse(row[4]) if row[4] is not None else None,
            fact_kind=NumericInstrumentFactKind(str(row[5])),
            evidence_scope=EvidenceScope(str(row[6])),
            event_start=row[7],
            event_end=row[8],
            value=Quantity(Decimal(row[9]), QuantityUnit(str(row[10])))
            if NumericInstrumentFactKind(str(row[5]))
            in {NumericInstrumentFactKind.TOTAL_SHARES, NumericInstrumentFactKind.FREE_FLOAT_SHARES}
            else Money(Decimal(row[9]), str(row[10])),
            revision=int(row[11]),
            supersedes_revision_id=UUID(str(row[12])) if row[12] is not None else None,
        )

    def listing_status_as_of(
        self, *, instrument_id: InstrumentId, effective_time: datetime, decision_time: DecisionTime
    ) -> ListingStatus | None:
        status = self._lifecycle_status_as_of(
            instrument_id=instrument_id,
            fact_kind=InstrumentFactKind.LISTING_STATUS,
            effective_time=effective_time,
            decision_time=decision_time,
        )
        return ListingStatus(status) if status is not None else None

    def special_treatment_status_as_of(
        self, *, instrument_id: InstrumentId, effective_time: datetime, decision_time: DecisionTime
    ) -> SpecialTreatmentStatus | None:
        status = self._lifecycle_status_as_of(
            instrument_id=instrument_id,
            fact_kind=InstrumentFactKind.SPECIAL_TREATMENT_STATUS,
            effective_time=effective_time,
            decision_time=decision_time,
        )
        return SpecialTreatmentStatus(status) if status is not None else None

    def _lifecycle_status_as_of(
        self, *, instrument_id: InstrumentId, fact_kind: InstrumentFactKind, effective_time: datetime, decision_time: DecisionTime
    ) -> str | None:
        effective_time = require_utc(effective_time, field="effective_time")
        instrument_id = InstrumentId.parse(instrument_id)
        decision_time = _decision_time(decision_time)
        with self._connection_scope() as connection:
            row = connection.execute(
                "\n                WITH current_fact AS (\n                    SELECT DISTINCT ON (fact.event_start) fact.*\n                    FROM mra.instrument_fact_revision AS fact\n                    WHERE fact.provider_product_id = %s\n                      AND fact.instrument_id = %s\n                      AND fact.fact_kind = %s\n                      AND fact.evidence_scope = 'EFFECTIVE_INTERVAL'\n                      AND fact.decision_visible_at <= %s\n                    ORDER BY fact.event_start,\n                             fact.decision_visible_at DESC,\n                             fact.revision DESC,\n                             fact.fact_revision_id DESC\n                ), selected_fact AS (\n                    SELECT fact.*\n                    FROM current_fact AS fact\n                    WHERE fact.event_start <= %s\n                    ORDER BY fact.event_start DESC,\n                             fact.decision_visible_at DESC,\n                             fact.revision DESC,\n                             fact.fact_revision_id DESC\n                    LIMIT 1\n                )\n                SELECT fact.status_value,\n                       mra.market_artifact_is_readable(\n                           artifact.integrity_state, artifact.last_verified_at\n                       ),\n                       fact.decision_visible_at, fact.event_end,\n                       mra.market_artifact_is_readable(\n                           instrument_artifact.integrity_state,\n                           instrument_artifact.last_verified_at\n                       )\n                FROM selected_fact AS fact\n                JOIN mra.data_capture AS capture\n                  ON capture.capture_id = fact.capture_id\n                JOIN mra.artifact AS artifact\n                  ON artifact.artifact_id = capture.artifact_id\n                JOIN mra.instrument AS instrument\n                  ON instrument.instrument_id = fact.instrument_id\n                JOIN mra.data_capture AS instrument_capture\n                  ON instrument_capture.capture_id = instrument.source_capture_id\n                JOIN mra.artifact AS instrument_artifact\n                  ON instrument_artifact.artifact_id = instrument_capture.artifact_id\n                WHERE capture.status = 'CAPTURED'\n                ",
                (self._provider_product_id, instrument_id.value, fact_kind.value, decision_time.value, effective_time),
            ).fetchone()
        self._raise_if_gap_is_current(
            fact_kind=GapFactKind.INSTRUMENT_FACT,
            decision_time=decision_time,
            fact_decision_visible_at=row[2] if row is not None and (row[3] is None or row[3] > effective_time) else None,
            instrument_id=instrument_id,
            instrument_fact_kind=fact_kind,
            evidence_scope=EvidenceScope.EFFECTIVE_INTERVAL,
            interval_semantics="EFFECTIVE",
            interval_time=effective_time,
        )
        if row is None:
            return None
        if any((row[index] is not True for index in (1, 4))):
            raise ArtifactIntegrityError("current lifecycle or Instrument Authority Artifact is not AVAILABLE")
        if row[3] is not None and row[3] <= effective_time:
            return None
        return str(row[0])
