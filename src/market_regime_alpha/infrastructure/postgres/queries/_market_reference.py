"""Cohesive PostgreSQL Market query responsibility."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID


from market_regime_alpha.infrastructure.postgres.queries._market_mapping import (
    _decision_time,
)
from market_regime_alpha.infrastructure.postgres.queries._market_sql import (
    _CLASSIFICATION_MEMBERS_SQL,
    _IDENTIFIER_SQL,
)
from market_regime_alpha.market.domain import (
    ClassificationEvidenceStatus,
    ClassificationMembersResult,
    GapFactKind,
)
from market_regime_alpha.runtime.errors import ArtifactIntegrityError
from market_regime_alpha.shared.identity import InstrumentId
from market_regime_alpha.shared.time import DecisionTime, require_utc

from market_regime_alpha.infrastructure.postgres.queries._market_support import _MarketQuerySupport


class _ReferenceQueries(_MarketQuerySupport):
    def instrument_for_identifier_as_of(
        self, *, identifier_scheme: str, identifier_value: str, effective_time: datetime, decision_time: DecisionTime
    ) -> InstrumentId | None:
        effective_time = require_utc(effective_time, field="effective_time")
        decision_time = _decision_time(decision_time)
        with self._connection_scope() as connection:
            row = connection.execute(
                _IDENTIFIER_SQL, (identifier_scheme, identifier_value, self._provider_product_id, decision_time.value, effective_time)
            ).fetchone()
        self._raise_if_gap_is_current(
            fact_kind=GapFactKind.INSTRUMENT_IDENTIFIER,
            decision_time=decision_time,
            fact_decision_visible_at=row[2] if row is not None and (row[3] is None or row[3] > effective_time) else None,
            identifier_scheme=identifier_scheme,
            identifier_value=identifier_value,
            interval_semantics="EFFECTIVE",
            interval_time=effective_time,
            wildcard_instrument=True,
        )
        if row is None:
            return None
        if any((row[index] is not True for index in (1, 4))):
            raise ArtifactIntegrityError("current InstrumentIdentifier or Instrument Authority Artifact is not AVAILABLE")
        if row[3] is not None and row[3] <= effective_time:
            return None
        return InstrumentId.parse(row[0])

    def classification_members_as_of(
        self, *, classification_scheme: str, classification_code: str, effective_time: datetime, decision_time: DecisionTime
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
        classification_time = rows[0][1] if rows and (rows[0][2] is None or rows[0][2] > effective_time) else None
        self._raise_if_gap_is_current(
            fact_kind=GapFactKind.CLASSIFICATION,
            decision_time=decision_time,
            fact_decision_visible_at=classification_time,
            gap_provider_product_id=UUID(str(rows[0][9])) if rows else None,
            classification_scheme=classification_scheme,
            classification_code=classification_code,
            interval_semantics="EFFECTIVE",
            interval_time=effective_time,
        )
        if not rows:
            return ClassificationMembersResult(status=ClassificationEvidenceStatus.MISSING, members=())
        if any((row[0] is not True for row in rows)):
            raise ArtifactIntegrityError("current Classification evidence Artifact is not AVAILABLE")
        if rows[0][2] is not None and rows[0][2] <= effective_time:
            return ClassificationMembersResult(status=ClassificationEvidenceStatus.MISSING, members=())
        self._raise_if_membership_gap_is_current(
            classification_scheme=classification_scheme,
            classification_code=classification_code,
            effective_time=effective_time,
            decision_time=decision_time,
        )
        if any((row[3] is not None and any((row[index] is not True for index in (5, 8))) for row in rows)):
            raise ArtifactIntegrityError("current ClassificationMembership or Instrument Authority Artifact is not AVAILABLE")
        member_rows = tuple((row for row in rows if row[3] is not None))
        if not member_rows:
            return ClassificationMembersResult(status=ClassificationEvidenceStatus.MISSING, members=())
        return ClassificationMembersResult(
            status=ClassificationEvidenceStatus.AVAILABLE,
            members=tuple(
                (
                    InstrumentId.parse(row[3])
                    for row in member_rows
                    if str(row[4]) == "MEMBER" and (row[7] is None or row[7] > effective_time)
                )
            ),
        )

    def explain_instrument_identifier_as_of(
        self, *, identifier_scheme: str, identifier_value: str, effective_time: datetime, decision_time: DecisionTime
    ) -> dict[str, Any]:
        return self._explain(
            _IDENTIFIER_SQL,
            (identifier_scheme, identifier_value, self._provider_product_id, _decision_time(decision_time).value, effective_time),
        )

    def explain_classification_members_as_of(
        self, *, classification_scheme: str, classification_code: str, effective_time: datetime, decision_time: DecisionTime
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
