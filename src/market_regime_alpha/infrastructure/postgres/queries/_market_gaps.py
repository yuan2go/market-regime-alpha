"""Cohesive PostgreSQL Market query responsibility."""

from __future__ import annotations

from datetime import date
from uuid import UUID


from market_regime_alpha.infrastructure.postgres.queries._market_mapping import (
    _decision_time,
    _source_gap,
)
from market_regime_alpha.market.domain import (
    EvidenceScope,
    GapFactKind,
    InstrumentFactKind,
    SourceGap,
)
from market_regime_alpha.runtime.errors import ArtifactIntegrityError
from market_regime_alpha.shared.identity import InstrumentId, TradingSessionId
from market_regime_alpha.shared.time import DecisionTime

from market_regime_alpha.infrastructure.postgres.queries._market_support import _MarketQuerySupport


class _GapQueries(_MarketQuerySupport):
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
                "\n                SELECT gap.gap_id, gap.provider_product_id, gap.capture_id,\n                       gap.instrument_id, gap.session_id, gap.instrument_code,\n                       gap.identifier_scheme, gap.identifier_value,\n                       gap.exchange, gap.session_date,\n                       gap.classification_scheme, gap.classification_code,\n                       gap.action_key, gap.gap_kind, gap.reason_code,\n                       gap.fact_kind, gap.instrument_fact_kind,\n                       gap.evidence_scope, gap.timeframe, gap.price_basis,\n                       gap.event_start, gap.event_end,\n                       gap.effective_from, gap.effective_to, gap.detail,\n                       capture.status,\n                       mra.market_artifact_is_readable(\n                           artifact.integrity_state, artifact.last_verified_at\n                       )\n                FROM mra.source_gap AS gap\n                JOIN mra.data_capture AS capture\n                  ON capture.capture_id = gap.capture_id\n                LEFT JOIN mra.artifact AS artifact\n                  ON artifact.artifact_id = capture.artifact_id\n                WHERE gap.provider_product_id = %(provider_product_id)s\n                  AND gap.decision_visible_at <= %(decision_time)s\n                  AND (%(capture_id)s::uuid IS NULL OR gap.capture_id = %(capture_id)s)\n                  AND (%(fact_kind)s::text IS NULL OR gap.fact_kind = %(fact_kind)s)\n                  AND (%(instrument_id)s::uuid IS NULL OR gap.instrument_id = %(instrument_id)s)\n                  AND (%(session_id)s::uuid IS NULL OR gap.session_id = %(session_id)s)\n                  AND (%(instrument_code)s::text IS NULL OR gap.instrument_code = %(instrument_code)s)\n                  AND (%(identifier_scheme)s::text IS NULL OR gap.identifier_scheme = %(identifier_scheme)s)\n                  AND (%(identifier_value)s::text IS NULL OR gap.identifier_value = %(identifier_value)s)\n                  AND (%(exchange)s::text IS NULL OR gap.exchange = %(exchange)s)\n                  AND (%(session_date)s::date IS NULL OR gap.session_date = %(session_date)s)\n                  AND (%(classification_scheme)s::text IS NULL OR gap.classification_scheme = %(classification_scheme)s)\n                  AND (%(classification_code)s::text IS NULL OR gap.classification_code = %(classification_code)s)\n                  AND (%(instrument_fact_kind)s::text IS NULL OR gap.instrument_fact_kind = %(instrument_fact_kind)s)\n                  AND (%(evidence_scope)s::text IS NULL OR gap.evidence_scope = %(evidence_scope)s)\n                  AND (%(action_key)s::text IS NULL OR gap.action_key = %(action_key)s)\n                ORDER BY gap.decision_visible_at, gap.gap_id\n                ",
                {
                    "provider_product_id": self._provider_product_id,
                    "decision_time": decision_time.value,
                    "capture_id": capture_id,
                    "fact_kind": fact_kind.value if fact_kind is not None else None,
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
                    "action_key": action_key,
                },
            ).fetchall()
        if any((str(row[25]) == "CAPTURED" and row[26] is not True for row in rows)):
            raise ArtifactIntegrityError("SourceGap evidence Artifact is not AVAILABLE")
        return tuple((_source_gap(row) for row in rows))
