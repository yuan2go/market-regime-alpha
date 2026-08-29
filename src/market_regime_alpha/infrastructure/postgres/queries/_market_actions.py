"""Cohesive PostgreSQL Market query responsibility."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID


from market_regime_alpha.infrastructure.postgres.queries._market_mapping import (
    _decision_time,
)
from market_regime_alpha.market.domain import (
    CorporateActionRevision,
    CorporateActionType,
)
from market_regime_alpha.runtime.errors import ArtifactIntegrityError
from market_regime_alpha.shared.financial import Money
from market_regime_alpha.shared.identity import InstrumentId, TradingSessionId
from market_regime_alpha.shared.time import DecisionTime

from market_regime_alpha.infrastructure.postgres.queries._market_support import _MarketQuerySupport


class _CorporateActionQueries(_MarketQuerySupport):
    def corporate_actions_as_of(
        self, *, instrument_id: InstrumentId, ex_session_id: TradingSessionId, decision_time: DecisionTime
    ) -> tuple[CorporateActionRevision, ...]:
        instrument_id = InstrumentId.parse(instrument_id)
        ex_session_id = TradingSessionId.parse(ex_session_id)
        decision_time = _decision_time(decision_time)
        with self._connection_scope() as connection:
            rows = connection.execute(
                "\n                WITH current_action AS (\n                    SELECT DISTINCT ON (action.action_key) action.*\n                    FROM mra.corporate_action_revision AS action\n                    WHERE action.provider_product_id = %s\n                      AND action.instrument_id = %s\n                      AND action.decision_visible_at <= %s\n                    ORDER BY action.action_key,\n                             action.decision_visible_at DESC,\n                             action.revision DESC\n                )\n                SELECT action.corporate_action_revision_id,\n                       action.provider_product_id, action.capture_id,\n                       action.instrument_id, action.action_key,\n                       action.action_type, action.ex_session_id,\n                       action.record_session_id, action.pay_session_id,\n                       action.successor_instrument_id,\n                       action.cash_amount_per_share, action.ratio_factor,\n                       action.subscription_price, action.currency,\n                       action.revision, action.supersedes_revision_id,\n                       mra.market_artifact_is_readable(\n                           artifact.integrity_state, artifact.last_verified_at\n                       ),\n                       action.decision_visible_at,\n                       mra.market_artifact_is_readable(\n                           instrument_artifact.integrity_state,\n                           instrument_artifact.last_verified_at\n                       ),\n                       mra.market_artifact_is_readable(\n                           ex_artifact.integrity_state, ex_artifact.last_verified_at\n                       ),\n                       mra.market_artifact_is_readable(\n                           record_artifact.integrity_state,\n                           record_artifact.last_verified_at\n                       ),\n                       mra.market_artifact_is_readable(\n                           pay_artifact.integrity_state,\n                           pay_artifact.last_verified_at\n                       ),\n                       mra.market_artifact_is_readable(\n                           successor_artifact.integrity_state,\n                           successor_artifact.last_verified_at\n                       )\n                FROM current_action AS action\n                JOIN mra.data_capture AS capture\n                  ON capture.capture_id = action.capture_id\n                JOIN mra.artifact AS artifact\n                  ON artifact.artifact_id = capture.artifact_id\n                JOIN mra.instrument AS instrument\n                  ON instrument.instrument_id = action.instrument_id\n                JOIN mra.data_capture AS instrument_capture\n                  ON instrument_capture.capture_id = instrument.source_capture_id\n                JOIN mra.artifact AS instrument_artifact\n                  ON instrument_artifact.artifact_id = instrument_capture.artifact_id\n                JOIN mra.trading_session AS ex_session\n                  ON ex_session.session_id = action.ex_session_id\n                JOIN mra.data_capture AS ex_capture\n                  ON ex_capture.capture_id = ex_session.source_capture_id\n                JOIN mra.artifact AS ex_artifact\n                  ON ex_artifact.artifact_id = ex_capture.artifact_id\n                LEFT JOIN mra.trading_session AS record_session\n                  ON record_session.session_id = action.record_session_id\n                LEFT JOIN mra.data_capture AS record_capture\n                  ON record_capture.capture_id = record_session.source_capture_id\n                LEFT JOIN mra.artifact AS record_artifact\n                  ON record_artifact.artifact_id = record_capture.artifact_id\n                LEFT JOIN mra.trading_session AS pay_session\n                  ON pay_session.session_id = action.pay_session_id\n                LEFT JOIN mra.data_capture AS pay_capture\n                  ON pay_capture.capture_id = pay_session.source_capture_id\n                LEFT JOIN mra.artifact AS pay_artifact\n                  ON pay_artifact.artifact_id = pay_capture.artifact_id\n                LEFT JOIN mra.instrument AS successor\n                  ON successor.instrument_id = action.successor_instrument_id\n                LEFT JOIN mra.data_capture AS successor_capture\n                  ON successor_capture.capture_id = successor.source_capture_id\n                LEFT JOIN mra.artifact AS successor_artifact\n                  ON successor_artifact.artifact_id = successor_capture.artifact_id\n                WHERE capture.status = 'CAPTURED'\n                ORDER BY action.action_key\n                ",
                (self._provider_product_id, instrument_id.value, decision_time.value),
            ).fetchall()
        if any((row[16] is not True for row in rows)):
            raise ArtifactIntegrityError("current CorporateAction evidence Artifact is not AVAILABLE")
        if any(
            (
                row[18] is not True
                or row[19] is not True
                or (row[7] is not None and row[20] is not True)
                or (row[8] is not None and row[21] is not True)
                or (row[9] is not None and row[22] is not True)
                for row in rows
            )
        ):
            raise ArtifactIntegrityError("current CorporateAction reference Authority Artifact is not AVAILABLE")
        self._raise_if_corporate_action_gap_is_current(
            instrument_id=instrument_id, ex_session_id=ex_session_id, decision_time=decision_time
        )
        return tuple(
            (
                CorporateActionRevision(
                    corporate_action_revision_id=UUID(str(row[0])),
                    provider_product_id=UUID(str(row[1])),
                    capture_id=UUID(str(row[2])),
                    instrument_id=InstrumentId.parse(row[3]),
                    action_key=str(row[4]),
                    action_type=CorporateActionType(str(row[5])),
                    ex_session_id=TradingSessionId.parse(row[6]),
                    record_session_id=TradingSessionId.parse(row[7]) if row[7] is not None else None,
                    pay_session_id=TradingSessionId.parse(row[8]) if row[8] is not None else None,
                    successor_instrument_id=InstrumentId.parse(row[9]) if row[9] is not None else None,
                    cash_amount_per_share=Money(Decimal(row[10]), str(row[13])) if row[10] is not None else None,
                    ratio_factor=Decimal(row[11]) if row[11] is not None else None,
                    subscription_price=Money(Decimal(row[12]), str(row[13])) if row[12] is not None else None,
                    revision=int(row[14]),
                    supersedes_revision_id=UUID(str(row[15])) if row[15] is not None else None,
                )
                for row in rows
                if TradingSessionId.parse(row[6]) == ex_session_id
            )
        )
