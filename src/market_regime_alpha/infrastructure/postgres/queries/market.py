"""Owner-selected exact/as-of Market/PIT query adapter."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from market_regime_alpha.market.domain import (
    AdjustmentBasis,
    BarTimeframe,
    CorporateActionRevision,
    DecisionReference,
    DecisionReferenceStatus,
    GapKind,
    InstrumentFactRevision,
    InstrumentFactValueKind,
    MarketBarRevision,
    SecurityStatus,
    SourceGap,
    TradingSession,
    classify_decision_reference,
)
from market_regime_alpha.shared.time import require_utc


_EXACT_BAR_SQL = """
    SELECT
        bar.bar_revision_id, bar.provider_product_id, bar.capture_id,
        bar.instrument_id, bar.session_id, bar.timeframe,
        bar.adjustment_basis, bar.event_start, bar.event_end,
        bar.revision, bar.supersedes_revision_id, bar.open_value,
        bar.high_value, bar.low_value, bar.close_value,
        bar.volume_value, bar.turnover_value
    FROM mra.market_bar_revision AS bar
    JOIN mra.data_capture AS capture ON capture.capture_id = bar.capture_id
    JOIN mra.artifact AS artifact ON artifact.artifact_id = capture.artifact_id
    WHERE bar.provider_product_id = %s
      AND bar.instrument_id = %s
      AND bar.session_id = %s
      AND bar.timeframe = %s
      AND bar.adjustment_basis = %s
      AND bar.event_start = %s
      AND bar.event_end = %s
      AND capture.status = 'CAPTURED'
      AND capture.decision_visible_at <= %s
      AND artifact.integrity_state = 'AVAILABLE'
      AND NOT EXISTS (
          SELECT 1
          FROM mra.source_gap AS newer_gap
          JOIN mra.data_capture AS gap_capture
            ON gap_capture.capture_id = newer_gap.capture_id
          LEFT JOIN mra.artifact AS gap_artifact
            ON gap_artifact.artifact_id = gap_capture.artifact_id
          WHERE newer_gap.provider_product_id = bar.provider_product_id
            AND newer_gap.instrument_id = bar.instrument_id
            AND newer_gap.session_id = bar.session_id
            AND newer_gap.fact_kind = 'MARKET_BAR'
            AND newer_gap.timeframe = bar.timeframe
            AND newer_gap.adjustment_basis = bar.adjustment_basis
            AND newer_gap.event_start = bar.event_start
            AND newer_gap.event_end = bar.event_end
            AND gap_capture.decision_visible_at <= %s
            AND gap_capture.decision_visible_at >= capture.decision_visible_at
            AND (
                gap_capture.status = 'PROVIDER_FAILURE'
                OR gap_artifact.integrity_state = 'AVAILABLE'
            )
      )
    ORDER BY bar.revision DESC, capture.decision_visible_at DESC,
             bar.bar_revision_id DESC
    LIMIT 1
"""


class PostgresMarketQueries:
    """Queries are bound to one owner Product; callers never request `latest`."""

    def __init__(
        self,
        pool: TargetPostgresPool,
        *,
        provider_product_id: UUID,
    ) -> None:
        self._pool = pool
        self._provider_product_id = provider_product_id

    def exact_bar_as_of(
        self,
        *,
        instrument_id: UUID,
        session_id: UUID,
        timeframe: BarTimeframe,
        adjustment_basis: AdjustmentBasis,
        event_start: datetime,
        event_end: datetime,
        decision_time: datetime,
    ) -> MarketBarRevision | None:
        event_start = require_utc(event_start, field="event_start")
        event_end = require_utc(event_end, field="event_end")
        decision_time = require_utc(decision_time, field="decision_time")
        with self._pool.connection() as connection:
            row = connection.execute(
                _EXACT_BAR_SQL,
                (
                    self._provider_product_id,
                    instrument_id,
                    session_id,
                    timeframe.value,
                    adjustment_basis.value,
                    event_start,
                    event_end,
                    decision_time,
                    decision_time,
                ),
            ).fetchone()
        return _bar(row) if row is not None else None

    def trading_session_as_of(
        self,
        *,
        exchange: str,
        session_date: date,
        decision_time: datetime,
    ) -> TradingSession | None:
        decision_time = require_utc(decision_time, field="decision_time")
        with self._pool.connection() as connection:
            row = connection.execute(
                """
                SELECT session.session_id, session.exchange,
                       session.session_date, session.timezone_name,
                       session.open_at, session.break_start_at,
                       session.break_end_at, session.close_at,
                       session.decision_reference_at,
                       session.source_capture_id
                FROM mra.trading_session AS session
                JOIN mra.data_capture AS capture
                  ON capture.capture_id = session.source_capture_id
                LEFT JOIN mra.artifact AS artifact
                  ON artifact.artifact_id = capture.artifact_id
                WHERE session.exchange = %s
                  AND session.session_date = %s
                  AND capture.decision_visible_at <= %s
                  AND capture.status = 'CAPTURED'
                  AND artifact.integrity_state = 'AVAILABLE'
                ORDER BY capture.decision_visible_at DESC, session.recorded_at DESC
                LIMIT 1
                """,
                (exchange, session_date, decision_time),
            ).fetchone()
        return _session(row) if row is not None else None

    def instrument_for_identifier_as_of(
        self,
        *,
        identifier_scheme: str,
        identifier_value: str,
        effective_time: datetime,
        decision_time: datetime,
    ) -> UUID | None:
        effective_time = require_utc(effective_time, field="effective_time")
        decision_time = require_utc(decision_time, field="decision_time")
        with self._pool.connection() as connection:
            row = connection.execute(
                """
                SELECT identifier.instrument_id
                FROM mra.instrument_identifier AS identifier
                JOIN mra.data_capture AS capture
                  ON capture.capture_id = identifier.source_capture_id
                JOIN mra.artifact AS artifact
                  ON artifact.artifact_id = capture.artifact_id
                WHERE identifier.identifier_scheme = %s
                  AND identifier.identifier_value = %s
                  AND identifier.effective_from <= %s
                  AND (identifier.effective_to IS NULL OR identifier.effective_to > %s)
                  AND capture.decision_visible_at <= %s
                  AND capture.status = 'CAPTURED'
                  AND artifact.integrity_state = 'AVAILABLE'
                ORDER BY identifier.revision DESC,
                         capture.decision_visible_at DESC,
                         identifier.instrument_identifier_id DESC
                LIMIT 1
                """,
                (
                    identifier_scheme,
                    identifier_value,
                    effective_time,
                    effective_time,
                    decision_time,
                ),
            ).fetchone()
        return UUID(str(row[0])) if row is not None else None

    def classification_members_as_of(
        self,
        *,
        classification_scheme: str,
        classification_code: str,
        effective_time: datetime,
        decision_time: datetime,
    ) -> tuple[UUID, ...]:
        effective_time = require_utc(effective_time, field="effective_time")
        decision_time = require_utc(decision_time, field="decision_time")
        with self._pool.connection() as connection:
            rows = connection.execute(
                """
                WITH visible_classification AS (
                    SELECT classification.classification_id
                    FROM mra.classification AS classification
                    JOIN mra.data_capture AS capture
                      ON capture.capture_id = classification.source_capture_id
                    JOIN mra.artifact AS artifact
                      ON artifact.artifact_id = capture.artifact_id
                    WHERE classification.classification_scheme = %s
                      AND classification.classification_code = %s
                      AND classification.effective_from <= %s
                      AND (classification.effective_to IS NULL OR classification.effective_to > %s)
                      AND capture.decision_visible_at <= %s
                      AND capture.status = 'CAPTURED'
                      AND artifact.integrity_state = 'AVAILABLE'
                    ORDER BY classification.revision DESC,
                             capture.decision_visible_at DESC
                    LIMIT 1
                ), visible_membership AS (
                    SELECT DISTINCT ON (membership.instrument_id)
                           membership.instrument_id,
                           membership.membership_status
                    FROM mra.classification_membership_revision AS membership
                    JOIN visible_classification AS classification
                      ON classification.classification_id = membership.classification_id
                    JOIN mra.data_capture AS capture
                      ON capture.capture_id = membership.source_capture_id
                    JOIN mra.artifact AS artifact
                      ON artifact.artifact_id = capture.artifact_id
                    WHERE membership.effective_from <= %s
                      AND (membership.effective_to IS NULL OR membership.effective_to > %s)
                      AND capture.decision_visible_at <= %s
                      AND capture.status = 'CAPTURED'
                      AND artifact.integrity_state = 'AVAILABLE'
                    ORDER BY membership.instrument_id, membership.revision DESC,
                             capture.decision_visible_at DESC
                )
                SELECT instrument_id
                FROM visible_membership
                WHERE membership_status = 'MEMBER'
                ORDER BY instrument_id
                """,
                (
                    classification_scheme,
                    classification_code,
                    effective_time,
                    effective_time,
                    decision_time,
                    effective_time,
                    effective_time,
                    decision_time,
                ),
            ).fetchall()
        return tuple(UUID(str(row[0])) for row in rows)

    def security_status_as_of(
        self,
        *,
        instrument_id: UUID,
        session_id: UUID,
        evidence_scope: str,
        decision_time: datetime,
    ) -> SecurityStatus | None:
        decision_time = require_utc(decision_time, field="decision_time")
        with self._pool.connection() as connection:
            row = connection.execute(
                """
                SELECT fact.status_value
                FROM mra.instrument_fact_revision AS fact
                JOIN mra.data_capture AS capture ON capture.capture_id = fact.capture_id
                JOIN mra.artifact AS artifact ON artifact.artifact_id = capture.artifact_id
                WHERE fact.provider_product_id = %s
                  AND fact.instrument_id = %s
                  AND fact.session_id = %s
                  AND fact.fact_kind = 'SECURITY_STATUS'
                  AND fact.evidence_scope = %s
                  AND capture.decision_visible_at <= %s
                  AND capture.status = 'CAPTURED'
                  AND artifact.integrity_state = 'AVAILABLE'
                ORDER BY fact.revision DESC, capture.decision_visible_at DESC
                LIMIT 1
                """,
                (
                    self._provider_product_id,
                    instrument_id,
                    session_id,
                    evidence_scope,
                    decision_time,
                ),
            ).fetchone()
        return SecurityStatus(str(row[0])) if row is not None else None

    def instrument_fact_as_of(
        self,
        *,
        instrument_id: UUID,
        fact_kind: str,
        evidence_scope: str,
        event_time: datetime,
        decision_time: datetime,
    ) -> InstrumentFactRevision | None:
        event_time = require_utc(event_time, field="event_time")
        decision_time = require_utc(decision_time, field="decision_time")
        with self._pool.connection() as connection:
            row = connection.execute(
                """
                SELECT fact.fact_revision_id, fact.provider_product_id,
                       fact.capture_id, fact.instrument_id, fact.session_id,
                       fact.fact_kind, fact.evidence_scope, fact.event_start,
                       fact.event_end, fact.value_kind, fact.status_value,
                       fact.numeric_value, fact.text_value, fact.unit_code,
                       fact.revision, fact.supersedes_revision_id
                FROM mra.instrument_fact_revision AS fact
                JOIN mra.data_capture AS capture ON capture.capture_id = fact.capture_id
                JOIN mra.artifact AS artifact ON artifact.artifact_id = capture.artifact_id
                WHERE fact.provider_product_id = %s
                  AND fact.instrument_id = %s
                  AND fact.fact_kind = %s
                  AND fact.evidence_scope = %s
                  AND fact.event_start <= %s
                  AND fact.event_end > %s
                  AND capture.decision_visible_at <= %s
                  AND capture.status = 'CAPTURED'
                  AND artifact.integrity_state = 'AVAILABLE'
                ORDER BY fact.revision DESC, capture.decision_visible_at DESC
                LIMIT 1
                """,
                (
                    self._provider_product_id,
                    instrument_id,
                    fact_kind,
                    evidence_scope,
                    event_time,
                    event_time,
                    decision_time,
                ),
            ).fetchone()
        if row is None:
            return None
        return InstrumentFactRevision(
            fact_revision_id=UUID(str(row[0])),
            provider_product_id=UUID(str(row[1])),
            capture_id=UUID(str(row[2])),
            instrument_id=UUID(str(row[3])),
            session_id=UUID(str(row[4])) if row[4] is not None else None,
            fact_kind=str(row[5]),
            evidence_scope=str(row[6]),
            event_start=row[7],
            event_end=row[8],
            value_kind=InstrumentFactValueKind(str(row[9])),
            status_value=str(row[10]) if row[10] is not None else None,
            numeric_value=Decimal(row[11]) if row[11] is not None else None,
            text_value=str(row[12]) if row[12] is not None else None,
            unit_code=str(row[13]) if row[13] is not None else None,
            revision=int(row[14]),
            supersedes_revision_id=UUID(str(row[15]))
            if row[15] is not None
            else None,
        )

    def corporate_actions_as_of(
        self,
        *,
        instrument_id: UUID,
        ex_session_id: UUID,
        decision_time: datetime,
    ) -> tuple[CorporateActionRevision, ...]:
        decision_time = require_utc(decision_time, field="decision_time")
        with self._pool.connection() as connection:
            rows = connection.execute(
                """
                SELECT DISTINCT ON (action.action_key)
                       action.corporate_action_revision_id,
                       action.provider_product_id, action.capture_id,
                       action.instrument_id, action.action_key,
                       action.action_type, action.ex_session_id,
                       action.payable_at, action.cash_amount,
                       action.ratio_factor, action.currency, action.revision,
                       action.supersedes_revision_id
                FROM mra.corporate_action_revision AS action
                JOIN mra.data_capture AS capture
                  ON capture.capture_id = action.capture_id
                JOIN mra.artifact AS artifact
                  ON artifact.artifact_id = capture.artifact_id
                WHERE action.provider_product_id = %s
                  AND action.instrument_id = %s
                  AND action.ex_session_id = %s
                  AND capture.decision_visible_at <= %s
                  AND capture.status = 'CAPTURED'
                  AND artifact.integrity_state = 'AVAILABLE'
                ORDER BY action.action_key, action.revision DESC,
                         capture.decision_visible_at DESC
                """,
                (
                    self._provider_product_id,
                    instrument_id,
                    ex_session_id,
                    decision_time,
                ),
            ).fetchall()
        return tuple(
            CorporateActionRevision(
                corporate_action_revision_id=UUID(str(row[0])),
                provider_product_id=UUID(str(row[1])),
                capture_id=UUID(str(row[2])),
                instrument_id=UUID(str(row[3])),
                action_key=str(row[4]),
                action_type=str(row[5]),
                ex_session_id=UUID(str(row[6])),
                payable_at=row[7],
                cash_amount=Decimal(row[8]) if row[8] is not None else None,
                ratio_factor=Decimal(row[9]) if row[9] is not None else None,
                currency=str(row[10]) if row[10] is not None else None,
                revision=int(row[11]),
                supersedes_revision_id=UUID(str(row[12]))
                if row[12] is not None
                else None,
            )
            for row in rows
        )

    def decision_reference_1455(
        self,
        *,
        instrument_id: UUID,
        exchange: str,
        session_date: date,
        decision_time: datetime,
    ) -> DecisionReference:
        decision_time = require_utc(decision_time, field="decision_time")
        session = self.trading_session_as_of(
            exchange=exchange,
            session_date=session_date,
            decision_time=decision_time,
        )
        if session is None:
            return DecisionReference(
                status=DecisionReferenceStatus.UNAVAILABLE,
                reason_code="TRADING_SESSION_MISSING",
                bar=None,
            )
        event_end = session.decision_reference_at
        from datetime import timedelta

        event_start = event_end - timedelta(minutes=5)
        bar = self.exact_bar_as_of(
            instrument_id=instrument_id,
            session_id=session.session_id,
            timeframe=BarTimeframe.MINUTE_5,
            adjustment_basis=AdjustmentBasis.RAW_UNADJUSTED,
            event_start=event_start,
            event_end=event_end,
            decision_time=decision_time,
        )
        status = self.security_status_as_of(
            instrument_id=instrument_id,
            session_id=session.session_id,
            evidence_scope="DECISION_SESSION",
            decision_time=decision_time,
        )
        gap = self._exact_gap_as_of(
            instrument_id=instrument_id,
            session_id=session.session_id,
            event_start=event_start,
            event_end=event_end,
            decision_time=decision_time,
        )
        return classify_decision_reference(
            session=session,
            bar=bar,
            current_session_status=status,
            gap=gap,
        )

    def _exact_gap_as_of(
        self,
        *,
        instrument_id: UUID,
        session_id: UUID,
        event_start: datetime,
        event_end: datetime,
        decision_time: datetime,
    ) -> SourceGap | None:
        with self._pool.connection() as connection:
            row = connection.execute(
                """
                SELECT gap.gap_id, gap.provider_product_id, gap.capture_id,
                       gap.instrument_id, gap.session_id, gap.gap_kind,
                       gap.reason_code, gap.fact_kind, gap.timeframe,
                       gap.adjustment_basis, gap.event_start, gap.event_end,
                       gap.detail
                FROM mra.source_gap AS gap
                JOIN mra.data_capture AS capture ON capture.capture_id = gap.capture_id
                LEFT JOIN mra.artifact AS artifact ON artifact.artifact_id = capture.artifact_id
                WHERE gap.provider_product_id = %s
                  AND gap.instrument_id = %s
                  AND gap.session_id = %s
                  AND gap.fact_kind = 'MARKET_BAR'
                  AND gap.timeframe = 'MINUTE_5'
                  AND gap.adjustment_basis = 'RAW_UNADJUSTED'
                  AND gap.event_start = %s
                  AND gap.event_end = %s
                  AND capture.decision_visible_at <= %s
                  AND (
                      capture.status = 'PROVIDER_FAILURE'
                      OR artifact.integrity_state = 'AVAILABLE'
                  )
                  AND NOT EXISTS (
                      SELECT 1
                      FROM mra.market_bar_revision AS newer_bar
                      JOIN mra.data_capture AS bar_capture
                        ON bar_capture.capture_id = newer_bar.capture_id
                      JOIN mra.artifact AS bar_artifact
                        ON bar_artifact.artifact_id = bar_capture.artifact_id
                      WHERE newer_bar.provider_product_id = gap.provider_product_id
                        AND newer_bar.instrument_id = gap.instrument_id
                        AND newer_bar.session_id = gap.session_id
                        AND newer_bar.timeframe = gap.timeframe
                        AND newer_bar.adjustment_basis = gap.adjustment_basis
                        AND newer_bar.event_start = gap.event_start
                        AND newer_bar.event_end = gap.event_end
                        AND bar_capture.decision_visible_at <= %s
                        AND bar_capture.decision_visible_at > capture.decision_visible_at
                        AND bar_capture.status = 'CAPTURED'
                        AND bar_artifact.integrity_state = 'AVAILABLE'
                  )
                ORDER BY capture.decision_visible_at DESC, gap.recorded_at DESC
                LIMIT 1
                """,
                (
                    self._provider_product_id,
                    instrument_id,
                    session_id,
                    event_start,
                    event_end,
                    decision_time,
                    decision_time,
                ),
            ).fetchone()
        if row is None:
            return None
        return SourceGap(
            gap_id=UUID(str(row[0])),
            provider_product_id=UUID(str(row[1])),
            capture_id=UUID(str(row[2])),
            instrument_id=UUID(str(row[3])) if row[3] is not None else None,
            session_id=UUID(str(row[4])) if row[4] is not None else None,
            gap_kind=GapKind(str(row[5])),
            reason_code=str(row[6]),
            fact_kind=str(row[7]),
            timeframe=BarTimeframe(str(row[8])) if row[8] is not None else None,
            adjustment_basis=AdjustmentBasis(str(row[9])) if row[9] is not None else None,
            event_start=row[10],
            event_end=row[11],
            detail=str(row[12]) if row[12] is not None else None,
        )

    def explain_exact_bar_as_of(
        self,
        *,
        instrument_id: UUID,
        session_id: UUID,
        event_start: datetime,
        event_end: datetime,
        decision_time: datetime,
    ) -> dict[str, Any]:
        """Representative plan evidence; callers must not depend on its exact shape."""

        with self._pool.connection() as connection:
            row = connection.execute(
                "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + _EXACT_BAR_SQL,
                (
                    self._provider_product_id,
                    instrument_id,
                    session_id,
                    BarTimeframe.MINUTE_5.value,
                    AdjustmentBasis.RAW_UNADJUSTED.value,
                    event_start,
                    event_end,
                    decision_time,
                    decision_time,
                ),
            ).fetchone()
        if row is None:
            raise AssertionError("EXPLAIN must return a plan")
        return row[0][0]


def _bar(row: tuple[Any, ...]) -> MarketBarRevision:
    return MarketBarRevision(
        bar_revision_id=UUID(str(row[0])),
        provider_product_id=UUID(str(row[1])),
        capture_id=UUID(str(row[2])),
        instrument_id=UUID(str(row[3])),
        session_id=UUID(str(row[4])),
        timeframe=BarTimeframe(str(row[5])),
        adjustment_basis=AdjustmentBasis(str(row[6])),
        event_start=row[7],
        event_end=row[8],
        revision=int(row[9]),
        supersedes_revision_id=UUID(str(row[10])) if row[10] is not None else None,
        open=Decimal(row[11]),
        high=Decimal(row[12]),
        low=Decimal(row[13]),
        close=Decimal(row[14]),
        volume=Decimal(row[15]),
        turnover=Decimal(row[16]) if row[16] is not None else None,
    )


def _session(row: tuple[Any, ...]) -> TradingSession:
    return TradingSession(
        session_id=UUID(str(row[0])),
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


__all__ = ["PostgresMarketQueries"]
