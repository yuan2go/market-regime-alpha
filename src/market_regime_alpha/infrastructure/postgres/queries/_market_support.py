"""Cohesive PostgreSQL Market query responsibility."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime
from typing import Any, Iterator
from uuid import UUID

import psycopg

from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from market_regime_alpha.infrastructure.postgres.queries._market_mapping import (
    _source_gap,
)
from market_regime_alpha.market.domain import (
    BarTimeframe,
    EvidenceScope,
    GapFactKind,
    InstrumentFactKind,
    MarketEvidenceGapError,
    PriceBasis,
)
from market_regime_alpha.runtime.errors import ArtifactIntegrityError
from market_regime_alpha.shared.identity import InstrumentId, TradingSessionId
from market_regime_alpha.shared.time import DecisionTime


class _MarketQuerySupport:
    def __init__(self, pool: TargetPostgresPool, *, provider_product_id: UUID, _connection: psycopg.Connection[Any] | None = None) -> None:
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
                "\n                SELECT gap.gap_id, gap.provider_product_id, gap.capture_id,\n                       gap.instrument_id, gap.session_id, gap.instrument_code,\n                       gap.identifier_scheme, gap.identifier_value,\n                       gap.exchange, gap.session_date,\n                       gap.classification_scheme, gap.classification_code,\n                       gap.action_key, gap.gap_kind, gap.reason_code,\n                       gap.fact_kind, gap.instrument_fact_kind,\n                       gap.evidence_scope, gap.timeframe, gap.price_basis,\n                       gap.event_start, gap.event_end,\n                       gap.effective_from, gap.effective_to, gap.detail,\n                       gap.decision_visible_at, capture.status,\n                       mra.market_artifact_is_readable(\n                           artifact.integrity_state, artifact.last_verified_at\n                       )\n                FROM mra.source_gap AS gap\n                JOIN mra.data_capture AS capture\n                  ON capture.capture_id = gap.capture_id\n                LEFT JOIN mra.artifact AS artifact\n                  ON artifact.artifact_id = capture.artifact_id\n                WHERE gap.provider_product_id = %(provider_product_id)s\n                  AND gap.fact_kind = %(fact_kind)s\n                  AND gap.decision_visible_at <= %(decision_time)s\n                  AND (%(wildcard_instrument)s OR gap.instrument_id IS NOT DISTINCT FROM %(instrument_id)s)\n                  AND gap.session_id IS NOT DISTINCT FROM %(session_id)s\n                  AND gap.instrument_code IS NOT DISTINCT FROM %(instrument_code)s\n                  AND gap.identifier_scheme IS NOT DISTINCT FROM %(identifier_scheme)s\n                  AND gap.identifier_value IS NOT DISTINCT FROM %(identifier_value)s\n                  AND gap.exchange IS NOT DISTINCT FROM %(exchange)s\n                  AND gap.session_date IS NOT DISTINCT FROM %(session_date)s\n                  AND gap.classification_scheme IS NOT DISTINCT FROM %(classification_scheme)s\n                  AND gap.classification_code IS NOT DISTINCT FROM %(classification_code)s\n                  AND gap.instrument_fact_kind IS NOT DISTINCT FROM %(instrument_fact_kind)s\n                  AND gap.evidence_scope IS NOT DISTINCT FROM %(evidence_scope)s\n                  AND gap.timeframe IS NOT DISTINCT FROM %(timeframe)s\n                  AND gap.price_basis IS NOT DISTINCT FROM %(price_basis)s\n                  AND (%(wildcard_action)s OR gap.action_key IS NOT DISTINCT FROM %(action_key)s)\n                  AND (\n                      (%(interval_semantics)s = 'NONE'\n                       AND gap.event_start IS NULL AND gap.event_end IS NULL\n                       AND gap.effective_from IS NULL AND gap.effective_to IS NULL)\n                      OR\n                      (%(interval_semantics)s = 'EVENT_ANY'\n                       AND gap.event_start IS NOT NULL)\n                      OR\n                      (%(interval_semantics)s = 'EVENT_EXACT'\n                       AND gap.event_start = %(event_start)s\n                       AND gap.event_end = %(event_end)s\n                       AND gap.effective_from IS NULL\n                       AND gap.effective_to IS NULL)\n                      OR\n                      (%(interval_semantics)s = 'EVENT'\n                       AND gap.event_start <= %(interval_time)s\n                       AND gap.event_end > %(interval_time)s)\n                      OR\n                      (%(interval_semantics)s = 'EFFECTIVE'\n                       AND gap.effective_from <= %(interval_time)s\n                       AND (gap.effective_to IS NULL OR gap.effective_to > %(interval_time)s))\n                  )\n                ORDER BY gap.decision_visible_at DESC,\n                         gap.recorded_at DESC, gap.gap_id DESC\n                LIMIT 1\n                ",
                {
                    "provider_product_id": gap_provider_product_id or self._provider_product_id,
                    "fact_kind": fact_kind.value,
                    "decision_time": decision_time.value,
                    "wildcard_instrument": wildcard_instrument,
                    "instrument_id": instrument_id.value if instrument_id is not None else None,
                    "session_id": session_id.value if session_id is not None else None,
                    "instrument_code": instrument_code,
                    "identifier_scheme": identifier_scheme,
                    "identifier_value": identifier_value,
                    "exchange": exchange,
                    "session_date": session_date,
                    "classification_scheme": classification_scheme,
                    "classification_code": classification_code,
                    "instrument_fact_kind": instrument_fact_kind.value if instrument_fact_kind is not None else None,
                    "evidence_scope": evidence_scope.value if evidence_scope is not None else None,
                    "timeframe": timeframe.value if timeframe is not None else None,
                    "price_basis": price_basis.value if price_basis is not None else None,
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
            raise ArtifactIntegrityError("current SourceGap evidence Artifact is not AVAILABLE")
        raise MarketEvidenceGapError(_source_gap(row))

    def _raise_if_membership_gap_is_current(
        self, *, classification_scheme: str, classification_code: str, effective_time: datetime, decision_time: DecisionTime
    ) -> None:
        """Block an incomplete set when any member disposition is a current gap."""
        with self._connection_scope() as connection:
            row = connection.execute(
                "\n                SELECT gap.gap_id, gap.provider_product_id, gap.capture_id,\n                       gap.instrument_id, gap.session_id, gap.instrument_code,\n                       gap.identifier_scheme, gap.identifier_value,\n                       gap.exchange, gap.session_date,\n                       gap.classification_scheme, gap.classification_code,\n                       gap.action_key, gap.gap_kind, gap.reason_code,\n                       gap.fact_kind, gap.instrument_fact_kind,\n                       gap.evidence_scope, gap.timeframe, gap.price_basis,\n                       gap.event_start, gap.event_end,\n                       gap.effective_from, gap.effective_to, gap.detail,\n                       capture.status,\n                       mra.market_artifact_is_readable(\n                           artifact.integrity_state, artifact.last_verified_at\n                       )\n                FROM mra.source_gap AS gap\n                JOIN mra.data_capture AS capture\n                  ON capture.capture_id = gap.capture_id\n                LEFT JOIN mra.artifact AS artifact\n                  ON artifact.artifact_id = capture.artifact_id\n                WHERE gap.provider_product_id = %s\n                  AND gap.fact_kind = 'CLASSIFICATION_MEMBERSHIP'\n                  AND gap.classification_scheme = %s\n                  AND gap.classification_code = %s\n                  AND gap.effective_from <= %s\n                  AND (gap.effective_to IS NULL OR gap.effective_to > %s)\n                  AND gap.decision_visible_at <= %s\n                  AND NOT EXISTS (\n                      SELECT 1\n                      FROM mra.classification_membership_revision AS membership\n                      JOIN mra.classification AS classification\n                        ON classification.classification_id = membership.classification_id\n                      JOIN mra.data_capture AS member_capture\n                        ON member_capture.capture_id = membership.source_capture_id\n                      WHERE member_capture.provider_product_id = gap.provider_product_id\n                        AND classification.classification_scheme = gap.classification_scheme\n                        AND classification.classification_code = gap.classification_code\n                        AND membership.instrument_id = gap.instrument_id\n                        AND membership.effective_from <= %s\n                        AND (\n                            membership.effective_to IS NULL\n                            OR membership.effective_to > %s\n                        )\n                        AND membership.decision_visible_at <= %s\n                        AND membership.decision_visible_at > gap.decision_visible_at\n                  )\n                ORDER BY gap.decision_visible_at DESC, gap.gap_id DESC\n                LIMIT 1\n                ",
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
            raise ArtifactIntegrityError("current ClassificationMembership gap Artifact is not AVAILABLE")
        raise MarketEvidenceGapError(_source_gap(row))

    def _raise_if_corporate_action_gap_is_current(
        self, *, instrument_id: InstrumentId, ex_session_id: TradingSessionId, decision_time: DecisionTime
    ) -> None:
        with self._connection_scope() as connection:
            row = connection.execute(
                "\n                SELECT gap.gap_id, gap.provider_product_id, gap.capture_id,\n                       gap.instrument_id, gap.session_id, gap.instrument_code,\n                       gap.identifier_scheme, gap.identifier_value,\n                       gap.exchange, gap.session_date,\n                       gap.classification_scheme, gap.classification_code,\n                       gap.action_key, gap.gap_kind, gap.reason_code,\n                       gap.fact_kind, gap.instrument_fact_kind,\n                       gap.evidence_scope, gap.timeframe, gap.price_basis,\n                       gap.event_start, gap.event_end,\n                       gap.effective_from, gap.effective_to, gap.detail,\n                       capture.status,\n                       mra.market_artifact_is_readable(\n                           artifact.integrity_state, artifact.last_verified_at\n                       )\n                FROM mra.source_gap AS gap\n                JOIN mra.data_capture AS capture\n                  ON capture.capture_id = gap.capture_id\n                LEFT JOIN mra.artifact AS artifact\n                  ON artifact.artifact_id = capture.artifact_id\n                WHERE gap.provider_product_id = %s\n                  AND gap.fact_kind = 'CORPORATE_ACTION'\n                  AND gap.instrument_id = %s\n                  AND gap.session_id = %s\n                  AND gap.decision_visible_at <= %s\n                  AND NOT EXISTS (\n                      SELECT 1\n                      FROM mra.corporate_action_revision AS action\n                      WHERE action.provider_product_id = gap.provider_product_id\n                        AND action.instrument_id = gap.instrument_id\n                        AND action.action_key = gap.action_key\n                        AND action.decision_visible_at <= %s\n                        AND action.decision_visible_at > gap.decision_visible_at\n                  )\n                ORDER BY gap.decision_visible_at DESC, gap.gap_id DESC\n                LIMIT 1\n                ",
                (self._provider_product_id, instrument_id.value, ex_session_id.value, decision_time.value, decision_time.value),
            ).fetchone()
        if row is None:
            return
        if str(row[25]) != "CAPTURED" or row[26] is not True:
            raise ArtifactIntegrityError("current CorporateAction gap Artifact is not AVAILABLE")
        raise MarketEvidenceGapError(_source_gap(row))

    def _explain(
        self,
        sql: str,
        parameters: tuple[object, ...],
    ) -> dict[str, Any]:
        with self._connection_scope() as connection:
            row = connection.execute(
                "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + sql,
                parameters,
            ).fetchone()
        if row is None:
            raise AssertionError("EXPLAIN must return a plan")
        return row[0][0]
