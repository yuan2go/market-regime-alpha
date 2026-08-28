"""Owner-selected exact/as-of Market/PIT query adapter."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Iterator
from uuid import UUID

import psycopg

from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from market_regime_alpha.market.domain import (
    BarTimeframe,
    CorporateActionRevision,
    CorporateActionType,
    ClassificationEvidenceStatus,
    ClassificationMembersResult,
    DecisionReference,
    DecisionReferenceReason,
    DecisionReferenceStatus,
    GapFactKind,
    GapKind,
    GapReasonCode,
    EvidenceScope,
    InstrumentFactKind,
    InstrumentFactRevision,
    ListingStatus,
    MarketBarRevision,
    MarketEvidenceGapError,
    NumericInstrumentFactKind,
    PriceBasis,
    SecurityStatus,
    SpecialTreatmentStatus,
    SourceGap,
    TradingSession,
    classify_decision_reference,
)
from market_regime_alpha.runtime.errors import ArtifactIntegrityError
from market_regime_alpha.shared.financial import Money, Quantity, QuantityUnit
from market_regime_alpha.shared.identity import InstrumentId, TradingSessionId
from market_regime_alpha.shared.time import DecisionTime, require_utc


_EXACT_BAR_SQL = """
    WITH current_bar AS (
        SELECT candidate.*
        FROM mra.market_bar_revision AS candidate
        WHERE candidate.provider_product_id = %s
          AND candidate.instrument_id = %s
          AND candidate.session_id = %s
          AND candidate.timeframe = %s
          AND candidate.price_basis = %s
          AND candidate.event_start = %s
          AND candidate.event_end = %s
          AND candidate.decision_visible_at <= %s
        ORDER BY candidate.decision_visible_at DESC,
                 candidate.revision DESC,
                 candidate.bar_revision_id DESC
        LIMIT 1
    )
    SELECT
        bar.bar_revision_id, bar.provider_product_id, bar.capture_id,
        bar.instrument_id, bar.session_id, bar.timeframe,
        bar.price_basis, bar.event_start, bar.event_end,
        bar.revision, bar.supersedes_revision_id, bar.open_value,
        bar.high_value, bar.low_value, bar.close_value,
        bar.volume_value, bar.turnover_value, instrument.currency,
        mra.artifact_is_authoritatively_readable(
            artifact.integrity_state, artifact.last_verified_at
        ),
        mra.artifact_is_authoritatively_readable(
            instrument_artifact.integrity_state, instrument_artifact.last_verified_at
        ),
        mra.artifact_is_authoritatively_readable(
            session_artifact.integrity_state, session_artifact.last_verified_at
        )
    FROM current_bar AS bar
    JOIN mra.instrument AS instrument ON instrument.instrument_id = bar.instrument_id
    JOIN mra.data_capture AS instrument_capture
      ON instrument_capture.capture_id = instrument.source_capture_id
    JOIN mra.artifact AS instrument_artifact
      ON instrument_artifact.artifact_id = instrument_capture.artifact_id
    JOIN mra.trading_session AS session ON session.session_id = bar.session_id
    JOIN mra.data_capture AS session_capture
      ON session_capture.capture_id = session.source_capture_id
    JOIN mra.artifact AS session_artifact
      ON session_artifact.artifact_id = session_capture.artifact_id
    JOIN mra.data_capture AS capture ON capture.capture_id = bar.capture_id
    JOIN mra.artifact AS artifact ON artifact.artifact_id = capture.artifact_id
    WHERE capture.status = 'CAPTURED'
      AND NOT EXISTS (
          SELECT 1
          FROM mra.source_gap AS newer_gap
          WHERE newer_gap.provider_product_id = bar.provider_product_id
            AND newer_gap.instrument_id = bar.instrument_id
            AND newer_gap.session_id = bar.session_id
            AND newer_gap.fact_kind = 'MARKET_BAR'
            AND newer_gap.timeframe = bar.timeframe
            AND newer_gap.price_basis = bar.price_basis
            AND newer_gap.event_start = bar.event_start
            AND newer_gap.event_end = bar.event_end
            AND newer_gap.decision_visible_at <= %s
            AND newer_gap.decision_visible_at >= bar.decision_visible_at
      )
"""

_TRADING_SESSION_SQL = """
    SELECT session.session_id, session.exchange,
           session.session_date, session.timezone_name,
           session.open_at, session.break_start_at,
           session.break_end_at, session.close_at,
           session.decision_reference_at,
           session.source_capture_id,
           mra.artifact_is_authoritatively_readable(
               artifact.integrity_state, artifact.last_verified_at
           ),
           session.decision_visible_at
    FROM mra.trading_session AS session
    JOIN mra.data_capture AS capture
      ON capture.capture_id = session.source_capture_id
    LEFT JOIN mra.artifact AS artifact
      ON artifact.artifact_id = capture.artifact_id
    WHERE session.exchange = %s
      AND session.session_date = %s
      AND session.decision_visible_at <= %s
      AND capture.status = 'CAPTURED'
    ORDER BY session.decision_visible_at DESC, session.recorded_at DESC
    LIMIT 1
"""

_IDENTIFIER_SQL = """
    WITH candidate_identifier AS (
        SELECT identifier.*
        FROM mra.instrument_identifier AS identifier
        JOIN mra.data_capture AS capture
          ON capture.capture_id = identifier.source_capture_id
        WHERE identifier.identifier_scheme = %s
          AND identifier.identifier_value = %s
          AND capture.provider_product_id = %s
          AND identifier.decision_visible_at <= %s
          AND capture.status = 'CAPTURED'
    ), current_identifier AS (
        SELECT DISTINCT ON (
            instrument_id, identifier_scheme, identifier_value, effective_from
        ) *
        FROM candidate_identifier
        ORDER BY instrument_id, identifier_scheme, identifier_value,
                 effective_from, decision_visible_at DESC, revision DESC,
                 instrument_identifier_id DESC
    ), selected_identifier AS (
        SELECT identifier.*
        FROM current_identifier AS identifier
        WHERE identifier.effective_from <= %s
        ORDER BY identifier.effective_from DESC,
                 identifier.decision_visible_at DESC,
                 identifier.revision DESC,
                 identifier.instrument_identifier_id DESC
        LIMIT 1
    )
    SELECT identifier.instrument_id,
           mra.artifact_is_authoritatively_readable(
               artifact.integrity_state, artifact.last_verified_at
           ),
           identifier.decision_visible_at, identifier.effective_to,
           mra.artifact_is_authoritatively_readable(
               instrument_artifact.integrity_state,
               instrument_artifact.last_verified_at
           )
    FROM selected_identifier AS identifier
    JOIN mra.data_capture AS capture
      ON capture.capture_id = identifier.source_capture_id
    JOIN mra.artifact AS artifact
      ON artifact.artifact_id = capture.artifact_id
    JOIN mra.instrument AS instrument
      ON instrument.instrument_id = identifier.instrument_id
    JOIN mra.data_capture AS instrument_capture
      ON instrument_capture.capture_id = instrument.source_capture_id
    JOIN mra.artifact AS instrument_artifact
      ON instrument_artifact.artifact_id = instrument_capture.artifact_id
"""

_CLASSIFICATION_MEMBERS_SQL = """
    WITH candidate_classification AS (
        SELECT classification.*
        FROM mra.classification AS classification
        JOIN mra.data_capture AS capture
          ON capture.capture_id = classification.source_capture_id
        WHERE classification.classification_scheme = %s
          AND classification.classification_code = %s
          AND classification.decision_visible_at <= %s
          AND capture.status = 'CAPTURED'
    ), current_classification AS (
        SELECT DISTINCT ON (classification.effective_from) classification.*
        FROM candidate_classification AS classification
        ORDER BY classification.effective_from,
                 classification.decision_visible_at DESC,
                 classification.revision DESC,
                 classification.classification_id DESC
    ), selected_classification AS (
        SELECT classification.*
        FROM current_classification AS classification
        WHERE classification.effective_from <= %s
        ORDER BY classification.effective_from DESC,
                 classification.decision_visible_at DESC,
                 classification.revision DESC,
                 classification.classification_id DESC
        LIMIT 1
    ), classification_evidence AS (
        SELECT classification.classification_scheme,
               classification.classification_code,
               mra.artifact_is_authoritatively_readable(
                   artifact.integrity_state, artifact.last_verified_at
               )
                 AS classification_artifact_readable,
               classification.decision_visible_at AS classification_decision_visible_at,
               classification.effective_to AS classification_effective_to,
               capture.provider_product_id AS classification_provider_product_id
        FROM selected_classification AS classification
        JOIN mra.data_capture AS capture
          ON capture.capture_id = classification.source_capture_id
        JOIN mra.artifact AS artifact
          ON artifact.artifact_id = capture.artifact_id
    ), candidate_membership AS (
        SELECT membership.*
        FROM mra.classification_membership_revision AS membership
        JOIN mra.classification AS membership_classification
          ON membership_classification.classification_id = membership.classification_id
        JOIN classification_evidence AS classification
          ON classification.classification_scheme =
             membership_classification.classification_scheme
         AND classification.classification_code =
             membership_classification.classification_code
        JOIN mra.data_capture AS capture
          ON capture.capture_id = membership.source_capture_id
        WHERE capture.provider_product_id = %s
          AND membership.decision_visible_at <= %s
          AND capture.status = 'CAPTURED'
    ), current_membership AS (
        SELECT DISTINCT ON (instrument_id, effective_from)
               membership_revision_id, source_capture_id, instrument_id,
               membership_status, effective_from, effective_to,
               decision_visible_at, revision
        FROM candidate_membership
        ORDER BY instrument_id, effective_from,
                 decision_visible_at DESC, revision DESC,
                 membership_revision_id DESC
    ), selected_membership AS (
        SELECT DISTINCT ON (membership.instrument_id)
               membership.*
        FROM current_membership AS membership
        WHERE membership.effective_from <= %s
        ORDER BY membership.instrument_id, membership.effective_from DESC,
                 membership.decision_visible_at DESC,
                 membership.revision DESC,
                 membership.membership_revision_id DESC
    )
    SELECT classification.classification_artifact_readable,
           classification.classification_decision_visible_at,
           classification.classification_effective_to,
           membership.instrument_id, membership.membership_status,
           mra.artifact_is_authoritatively_readable(
               membership_artifact.integrity_state,
               membership_artifact.last_verified_at
           ),
           membership.decision_visible_at, membership.effective_to,
           mra.artifact_is_authoritatively_readable(
               instrument_artifact.integrity_state,
               instrument_artifact.last_verified_at
           ),
           classification.classification_provider_product_id
    FROM classification_evidence AS classification
    LEFT JOIN selected_membership AS membership ON true
    LEFT JOIN mra.data_capture AS membership_capture
      ON membership_capture.capture_id = membership.source_capture_id
    LEFT JOIN mra.artifact AS membership_artifact
      ON membership_artifact.artifact_id = membership_capture.artifact_id
    LEFT JOIN mra.instrument AS instrument
      ON instrument.instrument_id = membership.instrument_id
    LEFT JOIN mra.data_capture AS instrument_capture
      ON instrument_capture.capture_id = instrument.source_capture_id
    LEFT JOIN mra.artifact AS instrument_artifact
      ON instrument_artifact.artifact_id = instrument_capture.artifact_id
    ORDER BY membership.instrument_id
"""


class PostgresMarketQueryProvider:
    """Explicit query composition boundary bound to one ProviderProduct."""

    def __init__(self, pool: TargetPostgresPool) -> None:
        self._pool = pool

    def for_provider_product(
        self,
        provider_product_id: UUID,
    ) -> PostgresMarketQueries:
        return PostgresMarketQueries(
            self._pool,
            provider_product_id=provider_product_id,
        )


class PostgresMarketQueries:
    """Queries are bound to one owner Product; callers never request `latest`."""

    def __init__(
        self,
        pool: TargetPostgresPool,
        *,
        provider_product_id: UUID,
        _connection: psycopg.Connection[Any] | None = None,
    ) -> None:
        self._pool = pool
        self._provider_product_id = provider_product_id
        self._bound_connection = _connection

    @contextmanager
    def _connection_scope(self) -> Iterator[psycopg.Connection[Any]]:
        if self._bound_connection is not None:
            yield self._bound_connection
            return
        with self._pool.connection(read_only=True) as connection:
            yield connection

    def _raise_if_gap_is_current(
        self,
        *,
        fact_kind: GapFactKind,
        decision_time: DecisionTime,
        fact_decision_visible_at: datetime | None,
        gap_provider_product_id: UUID | None = None,
        instrument_id: InstrumentId | None = None,
        session_id: TradingSessionId | None = None,
        instrument_code: str | None = None,
        identifier_scheme: str | None = None,
        identifier_value: str | None = None,
        exchange: str | None = None,
        session_date: date | None = None,
        classification_scheme: str | None = None,
        classification_code: str | None = None,
        instrument_fact_kind: InstrumentFactKind | None = None,
        evidence_scope: EvidenceScope | None = None,
        timeframe: BarTimeframe | None = None,
        price_basis: PriceBasis | None = None,
        action_key: str | None = None,
        interval_semantics: str = "NONE",
        interval_time: datetime | None = None,
        event_start: datetime | None = None,
        event_end: datetime | None = None,
        wildcard_instrument: bool = False,
        wildcard_action: bool = False,
    ) -> None:
        """Choose fact-or-gap before Artifact verification; equal-time gaps win."""

        with self._connection_scope() as connection:
            row = connection.execute(
                """
                SELECT gap.gap_id, gap.provider_product_id, gap.capture_id,
                       gap.instrument_id, gap.session_id, gap.instrument_code,
                       gap.identifier_scheme, gap.identifier_value,
                       gap.exchange, gap.session_date,
                       gap.classification_scheme, gap.classification_code,
                       gap.action_key, gap.gap_kind, gap.reason_code,
                       gap.fact_kind, gap.instrument_fact_kind,
                       gap.evidence_scope, gap.timeframe, gap.price_basis,
                       gap.event_start, gap.event_end,
                       gap.effective_from, gap.effective_to, gap.detail,
                       gap.decision_visible_at, capture.status,
                       mra.artifact_is_authoritatively_readable(
                           artifact.integrity_state, artifact.last_verified_at
                       )
                FROM mra.source_gap AS gap
                JOIN mra.data_capture AS capture
                  ON capture.capture_id = gap.capture_id
                LEFT JOIN mra.artifact AS artifact
                  ON artifact.artifact_id = capture.artifact_id
                WHERE gap.provider_product_id = %(provider_product_id)s
                  AND gap.fact_kind = %(fact_kind)s
                  AND gap.decision_visible_at <= %(decision_time)s
                  AND (%(wildcard_instrument)s OR gap.instrument_id IS NOT DISTINCT FROM %(instrument_id)s)
                  AND gap.session_id IS NOT DISTINCT FROM %(session_id)s
                  AND gap.instrument_code IS NOT DISTINCT FROM %(instrument_code)s
                  AND gap.identifier_scheme IS NOT DISTINCT FROM %(identifier_scheme)s
                  AND gap.identifier_value IS NOT DISTINCT FROM %(identifier_value)s
                  AND gap.exchange IS NOT DISTINCT FROM %(exchange)s
                  AND gap.session_date IS NOT DISTINCT FROM %(session_date)s
                  AND gap.classification_scheme IS NOT DISTINCT FROM %(classification_scheme)s
                  AND gap.classification_code IS NOT DISTINCT FROM %(classification_code)s
                  AND gap.instrument_fact_kind IS NOT DISTINCT FROM %(instrument_fact_kind)s
                  AND gap.evidence_scope IS NOT DISTINCT FROM %(evidence_scope)s
                  AND gap.timeframe IS NOT DISTINCT FROM %(timeframe)s
                  AND gap.price_basis IS NOT DISTINCT FROM %(price_basis)s
                  AND (%(wildcard_action)s OR gap.action_key IS NOT DISTINCT FROM %(action_key)s)
                  AND (
                      (%(interval_semantics)s = 'NONE'
                       AND gap.event_start IS NULL AND gap.event_end IS NULL
                       AND gap.effective_from IS NULL AND gap.effective_to IS NULL)
                      OR
                      (%(interval_semantics)s = 'EVENT_ANY'
                       AND gap.event_start IS NOT NULL)
                      OR
                      (%(interval_semantics)s = 'EVENT_EXACT'
                       AND gap.event_start = %(event_start)s
                       AND gap.event_end = %(event_end)s
                       AND gap.effective_from IS NULL
                       AND gap.effective_to IS NULL)
                      OR
                      (%(interval_semantics)s = 'EVENT'
                       AND gap.event_start <= %(interval_time)s
                       AND gap.event_end > %(interval_time)s)
                      OR
                      (%(interval_semantics)s = 'EFFECTIVE'
                       AND gap.effective_from <= %(interval_time)s
                       AND (gap.effective_to IS NULL OR gap.effective_to > %(interval_time)s))
                  )
                ORDER BY gap.decision_visible_at DESC,
                         gap.recorded_at DESC, gap.gap_id DESC
                LIMIT 1
                """,
                {
                    "provider_product_id": (
                        gap_provider_product_id or self._provider_product_id
                    ),
                    "fact_kind": fact_kind.value,
                    "decision_time": decision_time.value,
                    "wildcard_instrument": wildcard_instrument,
                    "instrument_id": instrument_id.value
                    if instrument_id is not None
                    else None,
                    "session_id": session_id.value if session_id is not None else None,
                    "instrument_code": instrument_code,
                    "identifier_scheme": identifier_scheme,
                    "identifier_value": identifier_value,
                    "exchange": exchange,
                    "session_date": session_date,
                    "classification_scheme": classification_scheme,
                    "classification_code": classification_code,
                    "instrument_fact_kind": instrument_fact_kind.value
                    if instrument_fact_kind is not None
                    else None,
                    "evidence_scope": evidence_scope.value
                    if evidence_scope is not None
                    else None,
                    "timeframe": timeframe.value if timeframe is not None else None,
                    "price_basis": price_basis.value
                    if price_basis is not None
                    else None,
                    "wildcard_action": wildcard_action,
                    "action_key": action_key,
                    "interval_semantics": interval_semantics,
                    "interval_time": interval_time,
                    "event_start": event_start,
                    "event_end": event_end,
                },
            ).fetchone()
        if row is None:
            return
        gap_time = row[25]
        if fact_decision_visible_at is not None and gap_time < fact_decision_visible_at:
            return
        if str(row[26]) != "CAPTURED" or row[27] is not True:
            raise ArtifactIntegrityError(
                "current SourceGap evidence Artifact is not AVAILABLE"
            )
        raise MarketEvidenceGapError(_source_gap(row))

    def _raise_if_membership_gap_is_current(
        self,
        *,
        classification_scheme: str,
        classification_code: str,
        effective_time: datetime,
        decision_time: DecisionTime,
    ) -> None:
        """Block an incomplete set when any member disposition is a current gap."""

        with self._connection_scope() as connection:
            row = connection.execute(
                """
                SELECT gap.gap_id, gap.provider_product_id, gap.capture_id,
                       gap.instrument_id, gap.session_id, gap.instrument_code,
                       gap.identifier_scheme, gap.identifier_value,
                       gap.exchange, gap.session_date,
                       gap.classification_scheme, gap.classification_code,
                       gap.action_key, gap.gap_kind, gap.reason_code,
                       gap.fact_kind, gap.instrument_fact_kind,
                       gap.evidence_scope, gap.timeframe, gap.price_basis,
                       gap.event_start, gap.event_end,
                       gap.effective_from, gap.effective_to, gap.detail,
                       capture.status,
                       mra.artifact_is_authoritatively_readable(
                           artifact.integrity_state, artifact.last_verified_at
                       )
                FROM mra.source_gap AS gap
                JOIN mra.data_capture AS capture
                  ON capture.capture_id = gap.capture_id
                LEFT JOIN mra.artifact AS artifact
                  ON artifact.artifact_id = capture.artifact_id
                WHERE gap.provider_product_id = %s
                  AND gap.fact_kind = 'CLASSIFICATION_MEMBERSHIP'
                  AND gap.classification_scheme = %s
                  AND gap.classification_code = %s
                  AND gap.effective_from <= %s
                  AND (gap.effective_to IS NULL OR gap.effective_to > %s)
                  AND gap.decision_visible_at <= %s
                  AND NOT EXISTS (
                      SELECT 1
                      FROM mra.classification_membership_revision AS membership
                      JOIN mra.classification AS classification
                        ON classification.classification_id = membership.classification_id
                      JOIN mra.data_capture AS member_capture
                        ON member_capture.capture_id = membership.source_capture_id
                      WHERE member_capture.provider_product_id = gap.provider_product_id
                        AND classification.classification_scheme = gap.classification_scheme
                        AND classification.classification_code = gap.classification_code
                        AND membership.instrument_id = gap.instrument_id
                        AND membership.effective_from <= %s
                        AND (
                            membership.effective_to IS NULL
                            OR membership.effective_to > %s
                        )
                        AND membership.decision_visible_at <= %s
                        AND membership.decision_visible_at > gap.decision_visible_at
                  )
                ORDER BY gap.decision_visible_at DESC, gap.gap_id DESC
                LIMIT 1
                """,
                (
                    self._provider_product_id,
                    classification_scheme,
                    classification_code,
                    effective_time,
                    effective_time,
                    decision_time.value,
                    effective_time,
                    effective_time,
                    decision_time.value,
                ),
            ).fetchone()
        if row is None:
            return
        if str(row[25]) != "CAPTURED" or row[26] is not True:
            raise ArtifactIntegrityError(
                "current ClassificationMembership gap Artifact is not AVAILABLE"
            )
        raise MarketEvidenceGapError(_source_gap(row))

    def _raise_if_corporate_action_gap_is_current(
        self,
        *,
        instrument_id: InstrumentId,
        ex_session_id: TradingSessionId,
        decision_time: DecisionTime,
    ) -> None:
        with self._connection_scope() as connection:
            row = connection.execute(
                """
                SELECT gap.gap_id, gap.provider_product_id, gap.capture_id,
                       gap.instrument_id, gap.session_id, gap.instrument_code,
                       gap.identifier_scheme, gap.identifier_value,
                       gap.exchange, gap.session_date,
                       gap.classification_scheme, gap.classification_code,
                       gap.action_key, gap.gap_kind, gap.reason_code,
                       gap.fact_kind, gap.instrument_fact_kind,
                       gap.evidence_scope, gap.timeframe, gap.price_basis,
                       gap.event_start, gap.event_end,
                       gap.effective_from, gap.effective_to, gap.detail,
                       capture.status,
                       mra.artifact_is_authoritatively_readable(
                           artifact.integrity_state, artifact.last_verified_at
                       )
                FROM mra.source_gap AS gap
                JOIN mra.data_capture AS capture
                  ON capture.capture_id = gap.capture_id
                LEFT JOIN mra.artifact AS artifact
                  ON artifact.artifact_id = capture.artifact_id
                WHERE gap.provider_product_id = %s
                  AND gap.fact_kind = 'CORPORATE_ACTION'
                  AND gap.instrument_id = %s
                  AND gap.session_id = %s
                  AND gap.decision_visible_at <= %s
                  AND NOT EXISTS (
                      SELECT 1
                      FROM mra.corporate_action_revision AS action
                      WHERE action.provider_product_id = gap.provider_product_id
                        AND action.instrument_id = gap.instrument_id
                        AND action.action_key = gap.action_key
                        AND action.decision_visible_at <= %s
                        AND action.decision_visible_at > gap.decision_visible_at
                  )
                ORDER BY gap.decision_visible_at DESC, gap.gap_id DESC
                LIMIT 1
                """,
                (
                    self._provider_product_id,
                    instrument_id.value,
                    ex_session_id.value,
                    decision_time.value,
                    decision_time.value,
                ),
            ).fetchone()
        if row is None:
            return
        if str(row[25]) != "CAPTURED" or row[26] is not True:
            raise ArtifactIntegrityError(
                "current CorporateAction gap Artifact is not AVAILABLE"
            )
        raise MarketEvidenceGapError(_source_gap(row))

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
        if any(row[index] is not True for index in (18, 19, 20)):
            raise ArtifactIntegrityError(
                "current MarketBar evidence Artifact is not AVAILABLE"
            )
        return _bar(row)

    def trading_session_as_of(
        self,
        *,
        exchange: str,
        session_date: date,
        decision_time: DecisionTime,
    ) -> TradingSession | None:
        decision_time = _decision_time(decision_time)
        with self._connection_scope() as connection:
            row = connection.execute(
                _TRADING_SESSION_SQL,
                (exchange, session_date, decision_time.value),
            ).fetchone()
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
            raise ArtifactIntegrityError(
                "current TradingSession evidence Artifact is not AVAILABLE"
            )
        return _session(row)

    def instrument_for_identifier_as_of(
        self,
        *,
        identifier_scheme: str,
        identifier_value: str,
        effective_time: datetime,
        decision_time: DecisionTime,
    ) -> InstrumentId | None:
        effective_time = require_utc(effective_time, field="effective_time")
        decision_time = _decision_time(decision_time)
        with self._connection_scope() as connection:
            row = connection.execute(
                _IDENTIFIER_SQL,
                (
                    identifier_scheme,
                    identifier_value,
                    self._provider_product_id,
                    decision_time.value,
                    effective_time,
                ),
            ).fetchone()
        self._raise_if_gap_is_current(
            fact_kind=GapFactKind.INSTRUMENT_IDENTIFIER,
            decision_time=decision_time,
            fact_decision_visible_at=(
                row[2]
                if row is not None
                and (row[3] is None or row[3] > effective_time)
                else None
            ),
            identifier_scheme=identifier_scheme,
            identifier_value=identifier_value,
            interval_semantics="EFFECTIVE",
            interval_time=effective_time,
            wildcard_instrument=True,
        )
        if row is None:
            return None
        if any(row[index] is not True for index in (1, 4)):
            raise ArtifactIntegrityError(
                "current InstrumentIdentifier or Instrument Authority Artifact "
                "is not AVAILABLE"
            )
        if row[3] is not None and row[3] <= effective_time:
            return None
        return InstrumentId.parse(row[0])

    def classification_members_as_of(
        self,
        *,
        classification_scheme: str,
        classification_code: str,
        effective_time: datetime,
        decision_time: DecisionTime,
    ) -> ClassificationMembersResult:
        effective_time = require_utc(effective_time, field="effective_time")
        decision_time = _decision_time(decision_time)
        with self._connection_scope() as connection:
            rows = connection.execute(
                _CLASSIFICATION_MEMBERS_SQL,
                (
                    classification_scheme,
                    classification_code,
                    decision_time.value,
                    effective_time,
                    self._provider_product_id,
                    decision_time.value,
                    effective_time,
                ),
            ).fetchall()
        classification_time = (
            rows[0][1]
            if rows and (rows[0][2] is None or rows[0][2] > effective_time)
            else None
        )
        self._raise_if_gap_is_current(
            fact_kind=GapFactKind.CLASSIFICATION,
            decision_time=decision_time,
            fact_decision_visible_at=classification_time,
            gap_provider_product_id=(
                UUID(str(rows[0][9])) if rows else None
            ),
            classification_scheme=classification_scheme,
            classification_code=classification_code,
            interval_semantics="EFFECTIVE",
            interval_time=effective_time,
        )
        if not rows:
            return ClassificationMembersResult(
                status=ClassificationEvidenceStatus.MISSING,
                members=(),
            )
        if any(row[0] is not True for row in rows):
            raise ArtifactIntegrityError(
                "current Classification evidence Artifact is not AVAILABLE"
            )
        if rows[0][2] is not None and rows[0][2] <= effective_time:
            return ClassificationMembersResult(
                status=ClassificationEvidenceStatus.MISSING,
                members=(),
            )
        self._raise_if_membership_gap_is_current(
            classification_scheme=classification_scheme,
            classification_code=classification_code,
            effective_time=effective_time,
            decision_time=decision_time,
        )
        if any(
            row[3] is not None
            and any(row[index] is not True for index in (5, 8))
            for row in rows
        ):
            raise ArtifactIntegrityError(
                "current ClassificationMembership or Instrument Authority Artifact "
                "is not AVAILABLE"
            )
        member_rows = tuple(row for row in rows if row[3] is not None)
        if not member_rows:
            return ClassificationMembersResult(
                status=ClassificationEvidenceStatus.MISSING,
                members=(),
            )
        return ClassificationMembersResult(
            status=ClassificationEvidenceStatus.AVAILABLE,
            members=tuple(
                InstrumentId.parse(row[3])
                for row in member_rows
                if str(row[4]) == "MEMBER"
                and (row[7] is None or row[7] > effective_time)
            ),
        )

    def security_status_as_of(
        self,
        *,
        instrument_id: InstrumentId,
        session_id: TradingSessionId,
        evidence_scope: EvidenceScope,
        decision_time: DecisionTime,
    ) -> SecurityStatus | None:
        instrument_id = InstrumentId.parse(instrument_id)
        session_id = TradingSessionId.parse(session_id)
        decision_time = _decision_time(decision_time)
        with self._connection_scope() as connection:
            row = connection.execute(
                """
                WITH current_fact AS (
                    SELECT fact.*
                    FROM mra.instrument_fact_revision AS fact
                    WHERE fact.provider_product_id = %s
                      AND fact.instrument_id = %s
                      AND fact.session_id = %s
                      AND fact.fact_kind = 'SECURITY_STATUS'
                      AND fact.evidence_scope = %s
                      AND fact.decision_visible_at <= %s
                    ORDER BY fact.decision_visible_at DESC,
                             fact.revision DESC,
                             fact.fact_revision_id DESC
                    LIMIT 1
                )
                SELECT fact.status_value,
                       mra.artifact_is_authoritatively_readable(
                           artifact.integrity_state, artifact.last_verified_at
                       ),
                       fact.decision_visible_at,
                       mra.artifact_is_authoritatively_readable(
                           instrument_artifact.integrity_state,
                           instrument_artifact.last_verified_at
                       ),
                       mra.artifact_is_authoritatively_readable(
                           session_artifact.integrity_state,
                           session_artifact.last_verified_at
                       )
                FROM current_fact AS fact
                JOIN mra.data_capture AS capture ON capture.capture_id = fact.capture_id
                JOIN mra.artifact AS artifact ON artifact.artifact_id = capture.artifact_id
                JOIN mra.instrument AS instrument
                  ON instrument.instrument_id = fact.instrument_id
                JOIN mra.data_capture AS instrument_capture
                  ON instrument_capture.capture_id = instrument.source_capture_id
                JOIN mra.artifact AS instrument_artifact
                  ON instrument_artifact.artifact_id = instrument_capture.artifact_id
                JOIN mra.trading_session AS session
                  ON session.session_id = fact.session_id
                JOIN mra.data_capture AS session_capture
                  ON session_capture.capture_id = session.source_capture_id
                JOIN mra.artifact AS session_artifact
                  ON session_artifact.artifact_id = session_capture.artifact_id
                WHERE capture.status = 'CAPTURED'
                """,
                (
                    self._provider_product_id,
                    instrument_id.value,
                    session_id.value,
                    evidence_scope.value,
                    decision_time.value,
                ),
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
        if any(row[index] is not True for index in (1, 3, 4)):
            raise ArtifactIntegrityError(
                "current SecurityStatus evidence or reference Authority Artifact "
                "is not AVAILABLE"
            )
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
        if (evidence_scope is EvidenceScope.EFFECTIVE_INTERVAL) != (
            session_id is None
        ):
            raise ValueError(
                "effective facts omit Session; session facts require exact Session"
            )
        with self._connection_scope() as connection:
            row = connection.execute(
                """
                WITH current_fact AS (
                    SELECT DISTINCT ON (fact.event_start) fact.*
                    FROM mra.instrument_fact_revision AS fact
                    WHERE fact.provider_product_id = %s
                      AND fact.instrument_id = %s
                      AND fact.fact_kind = %s
                      AND fact.evidence_scope = %s
                      AND fact.session_id IS NOT DISTINCT FROM %s
                      AND fact.decision_visible_at <= %s
                    ORDER BY fact.event_start,
                             fact.decision_visible_at DESC,
                             fact.revision DESC,
                             fact.fact_revision_id DESC
                ), selected_fact AS (
                    SELECT fact.*
                    FROM current_fact AS fact
                    WHERE fact.event_start <= %s
                    ORDER BY fact.event_start DESC,
                             fact.decision_visible_at DESC,
                             fact.revision DESC,
                             fact.fact_revision_id DESC
                    LIMIT 1
                )
                SELECT fact.fact_revision_id, fact.provider_product_id,
                       fact.capture_id, fact.instrument_id, fact.session_id,
                       fact.fact_kind, fact.evidence_scope, fact.event_start,
                       fact.event_end, fact.numeric_value, fact.unit_code,
                       fact.revision, fact.supersedes_revision_id,
                       mra.artifact_is_authoritatively_readable(
                           artifact.integrity_state, artifact.last_verified_at
                       ), fact.decision_visible_at,
                       mra.artifact_is_authoritatively_readable(
                           instrument_artifact.integrity_state,
                           instrument_artifact.last_verified_at
                       ),
                       mra.artifact_is_authoritatively_readable(
                           session_artifact.integrity_state,
                           session_artifact.last_verified_at
                       )
                FROM selected_fact AS fact
                JOIN mra.data_capture AS capture ON capture.capture_id = fact.capture_id
                JOIN mra.artifact AS artifact ON artifact.artifact_id = capture.artifact_id
                JOIN mra.instrument AS instrument
                  ON instrument.instrument_id = fact.instrument_id
                JOIN mra.data_capture AS instrument_capture
                  ON instrument_capture.capture_id = instrument.source_capture_id
                JOIN mra.artifact AS instrument_artifact
                  ON instrument_artifact.artifact_id = instrument_capture.artifact_id
                LEFT JOIN mra.trading_session AS session
                  ON session.session_id = fact.session_id
                LEFT JOIN mra.data_capture AS session_capture
                  ON session_capture.capture_id = session.source_capture_id
                LEFT JOIN mra.artifact AS session_artifact
                  ON session_artifact.artifact_id = session_capture.artifact_id
                WHERE capture.status = 'CAPTURED'
                """,
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
            fact_decision_visible_at=(
                row[14]
                if row is not None and (row[8] is None or row[8] > event_time)
                else None
            ),
            instrument_id=instrument_id,
            session_id=session_id,
            instrument_fact_kind=InstrumentFactKind(fact_kind.value),
            evidence_scope=evidence_scope,
            interval_semantics=(
                "EFFECTIVE"
                if evidence_scope is EvidenceScope.EFFECTIVE_INTERVAL
                else "EVENT"
            ),
            interval_time=event_time,
        )
        if row is None:
            return None
        if any(row[index] is not True for index in (13, 15)) or (
            session_id is not None and row[16] is not True
        ):
            raise ArtifactIntegrityError(
                "current InstrumentFact or Instrument Authority Artifact "
                "is not AVAILABLE"
            )
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
            value=(
                Quantity(Decimal(row[9]), QuantityUnit(str(row[10])))
                if NumericInstrumentFactKind(str(row[5]))
                in {
                    NumericInstrumentFactKind.TOTAL_SHARES,
                    NumericInstrumentFactKind.FREE_FLOAT_SHARES,
                }
                else Money(Decimal(row[9]), str(row[10]))
            ),
            revision=int(row[11]),
            supersedes_revision_id=UUID(str(row[12]))
            if row[12] is not None
            else None,
        )

    def listing_status_as_of(
        self,
        *,
        instrument_id: InstrumentId,
        effective_time: datetime,
        decision_time: DecisionTime,
    ) -> ListingStatus | None:
        status = self._lifecycle_status_as_of(
            instrument_id=instrument_id,
            fact_kind=InstrumentFactKind.LISTING_STATUS,
            effective_time=effective_time,
            decision_time=decision_time,
        )
        return ListingStatus(status) if status is not None else None

    def special_treatment_status_as_of(
        self,
        *,
        instrument_id: InstrumentId,
        effective_time: datetime,
        decision_time: DecisionTime,
    ) -> SpecialTreatmentStatus | None:
        status = self._lifecycle_status_as_of(
            instrument_id=instrument_id,
            fact_kind=InstrumentFactKind.SPECIAL_TREATMENT_STATUS,
            effective_time=effective_time,
            decision_time=decision_time,
        )
        return SpecialTreatmentStatus(status) if status is not None else None

    def _lifecycle_status_as_of(
        self,
        *,
        instrument_id: InstrumentId,
        fact_kind: InstrumentFactKind,
        effective_time: datetime,
        decision_time: DecisionTime,
    ) -> str | None:
        effective_time = require_utc(effective_time, field="effective_time")
        instrument_id = InstrumentId.parse(instrument_id)
        decision_time = _decision_time(decision_time)
        with self._connection_scope() as connection:
            row = connection.execute(
                """
                WITH current_fact AS (
                    SELECT DISTINCT ON (fact.event_start) fact.*
                    FROM mra.instrument_fact_revision AS fact
                    WHERE fact.provider_product_id = %s
                      AND fact.instrument_id = %s
                      AND fact.fact_kind = %s
                      AND fact.evidence_scope = 'EFFECTIVE_INTERVAL'
                      AND fact.decision_visible_at <= %s
                    ORDER BY fact.event_start,
                             fact.decision_visible_at DESC,
                             fact.revision DESC,
                             fact.fact_revision_id DESC
                ), selected_fact AS (
                    SELECT fact.*
                    FROM current_fact AS fact
                    WHERE fact.event_start <= %s
                    ORDER BY fact.event_start DESC,
                             fact.decision_visible_at DESC,
                             fact.revision DESC,
                             fact.fact_revision_id DESC
                    LIMIT 1
                )
                SELECT fact.status_value,
                       mra.artifact_is_authoritatively_readable(
                           artifact.integrity_state, artifact.last_verified_at
                       ),
                       fact.decision_visible_at, fact.event_end,
                       mra.artifact_is_authoritatively_readable(
                           instrument_artifact.integrity_state,
                           instrument_artifact.last_verified_at
                       )
                FROM selected_fact AS fact
                JOIN mra.data_capture AS capture
                  ON capture.capture_id = fact.capture_id
                JOIN mra.artifact AS artifact
                  ON artifact.artifact_id = capture.artifact_id
                JOIN mra.instrument AS instrument
                  ON instrument.instrument_id = fact.instrument_id
                JOIN mra.data_capture AS instrument_capture
                  ON instrument_capture.capture_id = instrument.source_capture_id
                JOIN mra.artifact AS instrument_artifact
                  ON instrument_artifact.artifact_id = instrument_capture.artifact_id
                WHERE capture.status = 'CAPTURED'
                """,
                (
                    self._provider_product_id,
                    instrument_id.value,
                    fact_kind.value,
                    decision_time.value,
                    effective_time,
                ),
            ).fetchone()
        self._raise_if_gap_is_current(
            fact_kind=GapFactKind.INSTRUMENT_FACT,
            decision_time=decision_time,
            fact_decision_visible_at=(
                row[2]
                if row is not None
                and (row[3] is None or row[3] > effective_time)
                else None
            ),
            instrument_id=instrument_id,
            instrument_fact_kind=fact_kind,
            evidence_scope=EvidenceScope.EFFECTIVE_INTERVAL,
            interval_semantics="EFFECTIVE",
            interval_time=effective_time,
        )
        if row is None:
            return None
        if any(row[index] is not True for index in (1, 4)):
            raise ArtifactIntegrityError(
                "current lifecycle or Instrument Authority Artifact is not AVAILABLE"
            )
        if row[3] is not None and row[3] <= effective_time:
            return None
        return str(row[0])

    def corporate_actions_as_of(
        self,
        *,
        instrument_id: InstrumentId,
        ex_session_id: TradingSessionId,
        decision_time: DecisionTime,
    ) -> tuple[CorporateActionRevision, ...]:
        instrument_id = InstrumentId.parse(instrument_id)
        ex_session_id = TradingSessionId.parse(ex_session_id)
        decision_time = _decision_time(decision_time)
        with self._connection_scope() as connection:
            rows = connection.execute(
                """
                WITH current_action AS (
                    SELECT DISTINCT ON (action.action_key) action.*
                    FROM mra.corporate_action_revision AS action
                    WHERE action.provider_product_id = %s
                      AND action.instrument_id = %s
                      AND action.decision_visible_at <= %s
                    ORDER BY action.action_key,
                             action.decision_visible_at DESC,
                             action.revision DESC
                )
                SELECT action.corporate_action_revision_id,
                       action.provider_product_id, action.capture_id,
                       action.instrument_id, action.action_key,
                       action.action_type, action.ex_session_id,
                       action.record_session_id, action.pay_session_id,
                       action.successor_instrument_id,
                       action.cash_amount_per_share, action.ratio_factor,
                       action.subscription_price, action.currency,
                       action.revision, action.supersedes_revision_id,
                       mra.artifact_is_authoritatively_readable(
                           artifact.integrity_state, artifact.last_verified_at
                       ),
                       action.decision_visible_at,
                       mra.artifact_is_authoritatively_readable(
                           instrument_artifact.integrity_state,
                           instrument_artifact.last_verified_at
                       ),
                       mra.artifact_is_authoritatively_readable(
                           ex_artifact.integrity_state, ex_artifact.last_verified_at
                       ),
                       mra.artifact_is_authoritatively_readable(
                           record_artifact.integrity_state,
                           record_artifact.last_verified_at
                       ),
                       mra.artifact_is_authoritatively_readable(
                           pay_artifact.integrity_state,
                           pay_artifact.last_verified_at
                       ),
                       mra.artifact_is_authoritatively_readable(
                           successor_artifact.integrity_state,
                           successor_artifact.last_verified_at
                       )
                FROM current_action AS action
                JOIN mra.data_capture AS capture
                  ON capture.capture_id = action.capture_id
                JOIN mra.artifact AS artifact
                  ON artifact.artifact_id = capture.artifact_id
                JOIN mra.instrument AS instrument
                  ON instrument.instrument_id = action.instrument_id
                JOIN mra.data_capture AS instrument_capture
                  ON instrument_capture.capture_id = instrument.source_capture_id
                JOIN mra.artifact AS instrument_artifact
                  ON instrument_artifact.artifact_id = instrument_capture.artifact_id
                JOIN mra.trading_session AS ex_session
                  ON ex_session.session_id = action.ex_session_id
                JOIN mra.data_capture AS ex_capture
                  ON ex_capture.capture_id = ex_session.source_capture_id
                JOIN mra.artifact AS ex_artifact
                  ON ex_artifact.artifact_id = ex_capture.artifact_id
                LEFT JOIN mra.trading_session AS record_session
                  ON record_session.session_id = action.record_session_id
                LEFT JOIN mra.data_capture AS record_capture
                  ON record_capture.capture_id = record_session.source_capture_id
                LEFT JOIN mra.artifact AS record_artifact
                  ON record_artifact.artifact_id = record_capture.artifact_id
                LEFT JOIN mra.trading_session AS pay_session
                  ON pay_session.session_id = action.pay_session_id
                LEFT JOIN mra.data_capture AS pay_capture
                  ON pay_capture.capture_id = pay_session.source_capture_id
                LEFT JOIN mra.artifact AS pay_artifact
                  ON pay_artifact.artifact_id = pay_capture.artifact_id
                LEFT JOIN mra.instrument AS successor
                  ON successor.instrument_id = action.successor_instrument_id
                LEFT JOIN mra.data_capture AS successor_capture
                  ON successor_capture.capture_id = successor.source_capture_id
                LEFT JOIN mra.artifact AS successor_artifact
                  ON successor_artifact.artifact_id = successor_capture.artifact_id
                WHERE capture.status = 'CAPTURED'
                ORDER BY action.action_key
                """,
                (
                    self._provider_product_id,
                    instrument_id.value,
                    decision_time.value,
                ),
            ).fetchall()
        if any(row[16] is not True for row in rows):
            raise ArtifactIntegrityError(
                "current CorporateAction evidence Artifact is not AVAILABLE"
            )
        if any(
            row[18] is not True
            or row[19] is not True
            or (row[7] is not None and row[20] is not True)
            or (row[8] is not None and row[21] is not True)
            or (row[9] is not None and row[22] is not True)
            for row in rows
        ):
            raise ArtifactIntegrityError(
                "current CorporateAction reference Authority Artifact is not AVAILABLE"
            )
        self._raise_if_corporate_action_gap_is_current(
            instrument_id=instrument_id,
            ex_session_id=ex_session_id,
            decision_time=decision_time,
        )
        return tuple(
            CorporateActionRevision(
                corporate_action_revision_id=UUID(str(row[0])),
                provider_product_id=UUID(str(row[1])),
                capture_id=UUID(str(row[2])),
                instrument_id=InstrumentId.parse(row[3]),
                action_key=str(row[4]),
                action_type=CorporateActionType(str(row[5])),
                ex_session_id=TradingSessionId.parse(row[6]),
                record_session_id=TradingSessionId.parse(row[7])
                if row[7] is not None
                else None,
                pay_session_id=TradingSessionId.parse(row[8])
                if row[8] is not None
                else None,
                successor_instrument_id=InstrumentId.parse(row[9])
                if row[9] is not None
                else None,
                cash_amount_per_share=Money(Decimal(row[10]), str(row[13]))
                if row[10] is not None
                else None,
                ratio_factor=Decimal(row[11]) if row[11] is not None else None,
                subscription_price=Money(Decimal(row[12]), str(row[13]))
                if row[12] is not None
                else None,
                revision=int(row[14]),
                supersedes_revision_id=UUID(str(row[15]))
                if row[15] is not None
                else None,
            )
            for row in rows
            if TradingSessionId.parse(row[6]) == ex_session_id
        )

    def source_gaps_as_of(
        self,
        *,
        decision_time: DecisionTime,
        capture_id: UUID | None = None,
        fact_kind: GapFactKind | None = None,
        instrument_id: InstrumentId | None = None,
        session_id: TradingSessionId | None = None,
        instrument_code: str | None = None,
        identifier_scheme: str | None = None,
        identifier_value: str | None = None,
        exchange: str | None = None,
        session_date: date | None = None,
        classification_scheme: str | None = None,
        classification_code: str | None = None,
        instrument_fact_kind: InstrumentFactKind | None = None,
        evidence_scope: EvidenceScope | None = None,
        action_key: str | None = None,
    ) -> tuple[SourceGap, ...]:
        """Inspect typed gaps without turning an unscoped failure into a fact."""

        decision_time = _decision_time(decision_time)
        if instrument_id is not None:
            instrument_id = InstrumentId.parse(instrument_id)
        if session_id is not None:
            session_id = TradingSessionId.parse(session_id)
        with self._connection_scope() as connection:
            rows = connection.execute(
                """
                SELECT gap.gap_id, gap.provider_product_id, gap.capture_id,
                       gap.instrument_id, gap.session_id, gap.instrument_code,
                       gap.identifier_scheme, gap.identifier_value,
                       gap.exchange, gap.session_date,
                       gap.classification_scheme, gap.classification_code,
                       gap.action_key, gap.gap_kind, gap.reason_code,
                       gap.fact_kind, gap.instrument_fact_kind,
                       gap.evidence_scope, gap.timeframe, gap.price_basis,
                       gap.event_start, gap.event_end,
                       gap.effective_from, gap.effective_to, gap.detail,
                       capture.status,
                       mra.artifact_is_authoritatively_readable(
                           artifact.integrity_state, artifact.last_verified_at
                       )
                FROM mra.source_gap AS gap
                JOIN mra.data_capture AS capture
                  ON capture.capture_id = gap.capture_id
                LEFT JOIN mra.artifact AS artifact
                  ON artifact.artifact_id = capture.artifact_id
                WHERE gap.provider_product_id = %(provider_product_id)s
                  AND gap.decision_visible_at <= %(decision_time)s
                  AND (%(capture_id)s::uuid IS NULL OR gap.capture_id = %(capture_id)s)
                  AND (%(fact_kind)s::text IS NULL OR gap.fact_kind = %(fact_kind)s)
                  AND (%(instrument_id)s::uuid IS NULL OR gap.instrument_id = %(instrument_id)s)
                  AND (%(session_id)s::uuid IS NULL OR gap.session_id = %(session_id)s)
                  AND (%(instrument_code)s::text IS NULL OR gap.instrument_code = %(instrument_code)s)
                  AND (%(identifier_scheme)s::text IS NULL OR gap.identifier_scheme = %(identifier_scheme)s)
                  AND (%(identifier_value)s::text IS NULL OR gap.identifier_value = %(identifier_value)s)
                  AND (%(exchange)s::text IS NULL OR gap.exchange = %(exchange)s)
                  AND (%(session_date)s::date IS NULL OR gap.session_date = %(session_date)s)
                  AND (%(classification_scheme)s::text IS NULL OR gap.classification_scheme = %(classification_scheme)s)
                  AND (%(classification_code)s::text IS NULL OR gap.classification_code = %(classification_code)s)
                  AND (%(instrument_fact_kind)s::text IS NULL OR gap.instrument_fact_kind = %(instrument_fact_kind)s)
                  AND (%(evidence_scope)s::text IS NULL OR gap.evidence_scope = %(evidence_scope)s)
                  AND (%(action_key)s::text IS NULL OR gap.action_key = %(action_key)s)
                ORDER BY gap.decision_visible_at, gap.gap_id
                """,
                {
                    "provider_product_id": self._provider_product_id,
                    "decision_time": decision_time.value,
                    "capture_id": capture_id,
                    "fact_kind": fact_kind.value if fact_kind is not None else None,
                    "instrument_id": instrument_id.value
                    if instrument_id is not None
                    else None,
                    "session_id": session_id.value if session_id is not None else None,
                    "instrument_code": instrument_code,
                    "identifier_scheme": identifier_scheme,
                    "identifier_value": identifier_value,
                    "exchange": exchange,
                    "session_date": session_date,
                    "classification_scheme": classification_scheme,
                    "classification_code": classification_code,
                    "instrument_fact_kind": instrument_fact_kind.value
                    if instrument_fact_kind is not None
                    else None,
                    "evidence_scope": evidence_scope.value
                    if evidence_scope is not None
                    else None,
                    "action_key": action_key,
                },
            ).fetchall()
        if any(
            str(row[25]) == "CAPTURED" and row[26] is not True
            for row in rows
        ):
            raise ArtifactIntegrityError(
                "SourceGap evidence Artifact is not AVAILABLE"
            )
        return tuple(_source_gap(row) for row in rows)

    def decision_reference_1455(
        self,
        *,
        instrument_id: InstrumentId,
        exchange: str,
        session_date: date,
        decision_time: DecisionTime,
    ) -> DecisionReference:
        instrument_id = InstrumentId.parse(instrument_id)
        decision_time = _decision_time(decision_time)
        if self._bound_connection is None:
            with self._pool.connection(read_only=True) as connection:
                connection.execute(
                    "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"
                )
                snapshot = self._bind_snapshot(connection)
                return snapshot.decision_reference_1455(
                    instrument_id=instrument_id,
                    exchange=exchange,
                    session_date=session_date,
                    decision_time=decision_time,
                )
        try:
            session = self.trading_session_as_of(
                exchange=exchange,
                session_date=session_date,
                decision_time=decision_time,
            )
        except MarketEvidenceGapError as exc:
            return _decision_reference_for_gap(exc.gap)
        if session is None:
            return DecisionReference(
                status=DecisionReferenceStatus.UNAVAILABLE,
                reason_code=DecisionReferenceReason.TRADING_SESSION_MISSING,
                bar=None,
            )
        event_end = session.decision_reference_at
        from datetime import timedelta

        event_start = event_end - timedelta(minutes=5)
        gaps: list[SourceGap] = []
        try:
            bar = self.exact_bar_as_of(
                instrument_id=instrument_id,
                session_id=session.session_id,
                timeframe=BarTimeframe.MINUTE_5,
                price_basis=PriceBasis.RAW_UNADJUSTED,
                event_start=event_start,
                event_end=event_end,
                decision_time=decision_time,
            )
        except MarketEvidenceGapError as exc:
            bar = None
            gaps.append(exc.gap)
        try:
            status = self.security_status_as_of(
                instrument_id=instrument_id,
                session_id=session.session_id,
                evidence_scope=EvidenceScope.DECISION_SESSION,
                decision_time=decision_time,
            )
        except MarketEvidenceGapError as exc:
            status = None
            gaps.append(exc.gap)
        if not gaps:
            exact_gap = self._exact_gap_as_of(
                instrument_id=instrument_id,
                session_id=session.session_id,
                event_start=event_start,
                event_end=event_end,
                decision_time=decision_time,
            )
            if exact_gap is not None:
                gaps.append(exact_gap)
        return classify_decision_reference(
            session=session,
            bar=bar,
            current_session_status=status,
            gap=_dominant_gap(gaps),
        )

    def _bind_snapshot(
        self,
        connection: psycopg.Connection[Any],
    ) -> PostgresMarketQueries:
        return PostgresMarketQueries(
            self._pool,
            provider_product_id=self._provider_product_id,
            _connection=connection,
        )

    def _exact_gap_as_of(
        self,
        *,
        instrument_id: InstrumentId,
        session_id: TradingSessionId,
        event_start: datetime,
        event_end: datetime,
        decision_time: DecisionTime,
    ) -> SourceGap | None:
        with self._connection_scope() as connection:
            row = connection.execute(
                """
                WITH current_gap AS (
                    SELECT candidate.*
                    FROM mra.source_gap AS candidate
                    WHERE candidate.provider_product_id = %s
                      AND candidate.instrument_id = %s
                      AND candidate.session_id = %s
                      AND candidate.fact_kind = 'MARKET_BAR'
                      AND candidate.timeframe = 'MINUTE_5'
                      AND candidate.price_basis = 'RAW_UNADJUSTED'
                      AND candidate.event_start = %s
                      AND candidate.event_end = %s
                      AND candidate.decision_visible_at <= %s
                    ORDER BY candidate.decision_visible_at DESC,
                             candidate.recorded_at DESC,
                             candidate.gap_id DESC
                    LIMIT 1
                )
                SELECT gap.gap_id, gap.provider_product_id, gap.capture_id,
                       gap.instrument_id, gap.session_id, gap.instrument_code,
                       gap.identifier_scheme, gap.identifier_value,
                       gap.exchange, gap.session_date,
                       gap.classification_scheme, gap.classification_code,
                       gap.action_key, gap.gap_kind, gap.reason_code,
                       gap.fact_kind, gap.instrument_fact_kind,
                       gap.evidence_scope, gap.timeframe, gap.price_basis,
                       gap.event_start, gap.event_end,
                       gap.effective_from, gap.effective_to, gap.detail,
                       capture.status,
                       mra.artifact_is_authoritatively_readable(
                           artifact.integrity_state, artifact.last_verified_at
                       )
                FROM current_gap AS gap
                JOIN mra.data_capture AS capture ON capture.capture_id = gap.capture_id
                LEFT JOIN mra.artifact AS artifact ON artifact.artifact_id = capture.artifact_id
                WHERE NOT EXISTS (
                      SELECT 1
                      FROM mra.market_bar_revision AS newer_bar
                    JOIN mra.data_capture AS bar_capture
                      ON bar_capture.capture_id = newer_bar.capture_id
                    WHERE newer_bar.provider_product_id = gap.provider_product_id
                        AND newer_bar.instrument_id = gap.instrument_id
                        AND newer_bar.session_id = gap.session_id
                        AND newer_bar.timeframe = gap.timeframe
                        AND newer_bar.price_basis = gap.price_basis
                        AND newer_bar.event_start = gap.event_start
                        AND newer_bar.event_end = gap.event_end
                      AND newer_bar.decision_visible_at <= %s
                      AND newer_bar.decision_visible_at > gap.decision_visible_at
                      AND bar_capture.status = 'CAPTURED'
                  )
                """,
                (
                    self._provider_product_id,
                    instrument_id.value,
                    session_id.value,
                    event_start,
                    event_end,
                    decision_time.value,
                    decision_time.value,
                ),
            ).fetchone()
        if row is None:
            return None
        if str(row[25]) != "CAPTURED" or row[26] is not True:
            raise ArtifactIntegrityError(
                "current MarketBar SourceGap Artifact is not AVAILABLE"
            )
        return _source_gap(row)

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

    def explain_trading_session_as_of(
        self,
        *,
        exchange: str,
        session_date: date,
        decision_time: DecisionTime,
    ) -> dict[str, Any]:
        return self._explain(
            _TRADING_SESSION_SQL,
            (
                exchange,
                session_date,
                _decision_time(decision_time).value,
            ),
        )

    def explain_instrument_identifier_as_of(
        self,
        *,
        identifier_scheme: str,
        identifier_value: str,
        effective_time: datetime,
        decision_time: DecisionTime,
    ) -> dict[str, Any]:
        return self._explain(
            _IDENTIFIER_SQL,
            (
                identifier_scheme,
                identifier_value,
                self._provider_product_id,
                _decision_time(decision_time).value,
                effective_time,
            ),
        )

    def explain_classification_members_as_of(
        self,
        *,
        classification_scheme: str,
        classification_code: str,
        effective_time: datetime,
        decision_time: DecisionTime,
    ) -> dict[str, Any]:
        return self._explain(
            _CLASSIFICATION_MEMBERS_SQL,
            (
                classification_scheme,
                classification_code,
                _decision_time(decision_time).value,
                effective_time,
                self._provider_product_id,
                _decision_time(decision_time).value,
                effective_time,
            ),
        )

    def _explain(self, sql: str, parameters: tuple[object, ...]) -> dict[str, Any]:
        with self._connection_scope() as connection:
            row = connection.execute(
                "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + sql,
                parameters,
            ).fetchone()
        if row is None:
            raise AssertionError("EXPLAIN must return a plan")
        return row[0][0]


def _bar(row: tuple[Any, ...]) -> MarketBarRevision:
    return MarketBarRevision(
        bar_revision_id=UUID(str(row[0])),
        provider_product_id=UUID(str(row[1])),
        capture_id=UUID(str(row[2])),
        instrument_id=InstrumentId.parse(row[3]),
        session_id=TradingSessionId.parse(row[4]),
        timeframe=BarTimeframe(str(row[5])),
        price_basis=PriceBasis(str(row[6])),
        event_start=row[7],
        event_end=row[8],
        revision=int(row[9]),
        supersedes_revision_id=UUID(str(row[10])) if row[10] is not None else None,
        open=Money(Decimal(row[11]), str(row[17])),
        high=Money(Decimal(row[12]), str(row[17])),
        low=Money(Decimal(row[13]), str(row[17])),
        close=Money(Decimal(row[14]), str(row[17])),
        volume=Quantity(Decimal(row[15]), QuantityUnit.SHARES),
        turnover=Money(Decimal(row[16]), str(row[17]))
        if row[16] is not None
        else None,
    )


def _session(row: tuple[Any, ...]) -> TradingSession:
    return TradingSession(
        session_id=TradingSessionId.parse(row[0]),
        exchange=str(row[1]),
        session_date=row[2],
        timezone_name=str(row[3]),
        open_at=row[4],
        break_start_at=row[5],
        break_end_at=row[6],
        close_at=row[7],
        decision_reference_at=row[8],
        source_capture_id=UUID(str(row[9])),
    )


def _source_gap(row: tuple[Any, ...]) -> SourceGap:
    return SourceGap(
        gap_id=UUID(str(row[0])),
        provider_product_id=UUID(str(row[1])),
        capture_id=UUID(str(row[2])),
        instrument_id=InstrumentId.parse(row[3]) if row[3] is not None else None,
        session_id=TradingSessionId.parse(row[4]) if row[4] is not None else None,
        instrument_code=str(row[5]) if row[5] is not None else None,
        identifier_scheme=str(row[6]) if row[6] is not None else None,
        identifier_value=str(row[7]) if row[7] is not None else None,
        exchange=str(row[8]) if row[8] is not None else None,
        session_date=row[9],
        classification_scheme=str(row[10]) if row[10] is not None else None,
        classification_code=str(row[11]) if row[11] is not None else None,
        action_key=str(row[12]) if row[12] is not None else None,
        gap_kind=GapKind(str(row[13])),
        reason_code=GapReasonCode(str(row[14])),
        fact_kind=GapFactKind(str(row[15])),
        instrument_fact_kind=InstrumentFactKind(str(row[16]))
        if row[16] is not None
        else None,
        evidence_scope=EvidenceScope(str(row[17]))
        if row[17] is not None
        else None,
        timeframe=BarTimeframe(str(row[18])) if row[18] is not None else None,
        price_basis=PriceBasis(str(row[19]))
        if row[19] is not None
        else None,
        event_start=row[20],
        event_end=row[21],
        effective_from=row[22],
        effective_to=row[23],
        detail=str(row[24]) if row[24] is not None else None,
    )


def _decision_time(value: DecisionTime | datetime) -> DecisionTime:
    return value if isinstance(value, DecisionTime) else DecisionTime(value)


def _decision_reference_for_gap(gap: SourceGap) -> DecisionReference:
    return DecisionReference(
        status=(
            DecisionReferenceStatus.UNAVAILABLE
            if gap.gap_kind in {GapKind.MISSING, GapKind.PLACEHOLDER}
            else DecisionReferenceStatus.FAILED
        ),
        reason_code=gap.reason_code,
        bar=None,
    )


def _dominant_gap(gaps: list[SourceGap]) -> SourceGap | None:
    """Choose a stable fail-closed disposition independent of query call order."""

    if not gaps:
        return None
    priority = {
        GapKind.MISSING: 1,
        GapKind.PLACEHOLDER: 2,
        GapKind.PROVIDER_FAILURE: 3,
        GapKind.CONFLICT: 4,
        GapKind.INVALID_OHLC: 5,
    }
    return max(
        gaps,
        key=lambda gap: (
            priority[gap.gap_kind],
            gap.fact_kind.value,
            gap.reason_code.value,
            str(gap.gap_id),
        ),
    )


__all__ = ["PostgresMarketQueries", "PostgresMarketQueryProvider"]
