"""PostgreSQL write owner for the target Market/PIT bounded context."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID


from market_regime_alpha.market.domain import (
    CorporateActionRevision,
    GapFactKind,
    InstrumentLifecycleFactRevision,
    InstrumentFactRevision,
    MarketBarRevision,
    NormalizationBatch,
    ProviderCapture,
    SecurityStatusFactRevision,
    SourceGap,
)
from market_regime_alpha.runtime.errors import (
    ArtifactIntegrityError,
    RuntimeNotFoundError,
    RuntimeStateConflictError,
)
from market_regime_alpha.shared.financial import Money
from market_regime_alpha.shared.identity import ContentHash
from market_regime_alpha.shared.time import DecisionTime


from market_regime_alpha.infrastructure.postgres.repositories._market_reference_repository import _MarketReferenceRepository
from market_regime_alpha.infrastructure.postgres.repositories._market_capture_repository import _MarketCaptureRepository


class _MarketNormalizationRepository(_MarketReferenceRepository, _MarketCaptureRepository):
    def insert_normalization(
        self,
        batch: NormalizationBatch,
        *,
        normalization_receipt_id: UUID,
        expected_artifact_sha256: ContentHash,
        expected_artifact_size: int,
    ) -> DecisionTime:
        """Bind one Capture-owned normalization aggregate in the active transaction."""
        source = self.lock_capture_source(batch.source_capture_id)
        if batch.source_provider_product_id != source.capture.provider_product_id:
            raise RuntimeStateConflictError("Normalization ProviderProduct differs from its Capture")
        if (
            source.artifact is None
            or source.artifact.content_sha256 != expected_artifact_sha256.value
            or source.artifact.size_bytes != expected_artifact_size
        ):
            raise ArtifactIntegrityError("Capture source changed during normalization")
        self._validate_product_capabilities(batch)
        classification_lineage = self._lock_normalization_roots(batch)
        recorded_at, known_at = self._normalization_times(source.capture)
        inserted_evidence = False
        for instrument in sorted(batch.instruments, key=lambda item: (item.canonical_code, str(item.instrument_id))):
            inserted_evidence |= self._insert_instrument(
                instrument, recorded_at=recorded_at, known_at=known_at
            )
        for identifier in sorted(
            batch.instrument_identifiers,
            key=lambda item: (item.identifier_scheme, item.effective_from, item.revision, item.identifier_value, str(item.instrument_id)),
        ):
            inserted_evidence |= self._insert_instrument_identifier(
                identifier, recorded_at=recorded_at, known_at=known_at
            )
        for session in sorted(batch.trading_sessions, key=lambda item: (item.exchange, item.session_date, str(item.session_id))):
            inserted_evidence |= self._insert_trading_session(
                session, recorded_at=recorded_at, known_at=known_at
            )
        for classification in sorted(
            batch.classifications,
            key=lambda item: (item.classification_scheme, item.classification_code, item.effective_from, item.revision),
        ):
            inserted_evidence |= self._insert_classification(
                classification, recorded_at=recorded_at, known_at=known_at
            )
        for membership in sorted(
            batch.classification_memberships,
            key=lambda item: (*classification_lineage[item.classification_id], str(item.instrument_id), item.effective_from, item.revision),
        ):
            inserted_evidence |= self._insert_classification_membership(
                membership, recorded_at=recorded_at, known_at=known_at
            )
        self._insert_reference_normalization(
            batch,
            normalization_receipt_id=normalization_receipt_id,
            recorded_at=recorded_at,
        )
        for bar in sorted(
            batch.bars,
            key=lambda item: (
                str(item.instrument_id),
                str(item.session_id),
                item.timeframe.value,
                item.price_basis.value,
                item.event_start,
                item.revision,
            ),
        ):
            if bar.event_end > known_at:
                raise RuntimeStateConflictError("MarketBar cannot become known before its event interval ends")
            self._insert_bar_revision(bar, recorded_at=recorded_at, known_at=known_at)
            inserted_evidence = True
        for instrument_fact in sorted(
            batch.instrument_facts, key=lambda item: (str(item.instrument_id), item.fact_kind.value, item.event_start, item.revision)
        ):
            self._insert_instrument_fact_revision(instrument_fact, recorded_at=recorded_at, known_at=known_at)
            inserted_evidence = True
        for security_fact in sorted(
            batch.security_status_facts,
            key=lambda item: (str(item.instrument_id), str(item.session_id), item.evidence_scope.value, item.revision),
        ):
            self._insert_security_status_revision(security_fact, recorded_at=recorded_at, known_at=known_at)
            inserted_evidence = True
        for lifecycle_fact in sorted(
            batch.lifecycle_status_facts,
            key=lambda item: (str(item.instrument_id), item.fact_kind.value, item.effective_from, item.revision),
        ):
            self._insert_lifecycle_status_revision(lifecycle_fact, recorded_at=recorded_at, known_at=known_at)
            inserted_evidence = True
        for action in sorted(batch.corporate_actions, key=lambda item: (str(item.instrument_id), item.action_key, item.revision)):
            self._insert_corporate_action(action, recorded_at=recorded_at, known_at=known_at)
            inserted_evidence = True
        for gap in sorted(
            batch.gaps,
            key=lambda item: (
                item.fact_kind.value,
                str(item.instrument_id) if item.instrument_id is not None else "",
                str(item.session_id) if item.session_id is not None else "",
                item.event_start or datetime.min.replace(tzinfo=recorded_at.tzinfo),
                str(item.gap_id),
            ),
        ):
            if gap.fact_kind is GapFactKind.MARKET_BAR and gap.event_end is not None and (gap.event_end > known_at):
                raise RuntimeStateConflictError("MarketBar SourceGap cannot become known before its expected interval ends")
            self._insert_source_gap(gap, recorded_at=recorded_at, known_at=known_at)
            inserted_evidence = True
        return DecisionTime(
            known_at
            if inserted_evidence
            else source.capture.temporal.decision_visible_at.value
        )

    def _lock_normalization_roots(self, batch: NormalizationBatch) -> dict[UUID, tuple[str, str]]:
        """Acquire every multi-root advisory lock in one deterministic order."""
        classification_lineage = {
            item.classification_id: (item.classification_scheme, item.classification_code) for item in batch.classifications
        }
        unresolved_ids = {
            item.classification_id for item in batch.classification_memberships if item.classification_id not in classification_lineage
        }
        if unresolved_ids:
            rows = self._connection.execute(
                "\n                SELECT classification_id, classification_scheme, classification_code\n                FROM mra.classification\n                WHERE classification_id = ANY(%s)\n                ",
                (list(unresolved_ids),),
            ).fetchall()
            classification_lineage.update({UUID(str(row[0])): (str(row[1]), str(row[2])) for row in rows})
        if any((item.classification_id not in classification_lineage for item in batch.classification_memberships)):
            raise RuntimeNotFoundError("ClassificationMembership references an unknown Classification")
        lock_keys = {f"mra:instrument-identifier:{item.identifier_scheme}" for item in batch.instrument_identifiers}
        lock_keys.update((f"mra:classification:{item.classification_scheme}:{item.classification_code}" for item in batch.classifications))
        lock_keys.update(
            (
                f"mra:classification-membership:{classification_lineage[item.classification_id][0]}:{classification_lineage[item.classification_id][1]}:{item.instrument_id}"
                for item in batch.classification_memberships
            )
        )
        lock_keys.update(
            (
                f"mra:instrument-fact-timeline:{batch.source_provider_product_id}:{item.instrument_id}:{item.fact_kind.value}"
                for item in batch.instrument_facts
                if item.evidence_scope.value == "EFFECTIVE_INTERVAL"
            )
        )
        lock_keys.update(
            (
                f"mra:instrument-fact-timeline:{batch.source_provider_product_id}:{item.instrument_id}:{item.fact_kind.value}"
                for item in batch.lifecycle_status_facts
            )
        )
        for lock_key in sorted(lock_keys):
            self._connection.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (lock_key,))
        return classification_lineage

    def _insert_bar_revision(self, bar: MarketBarRevision, *, recorded_at: datetime, known_at: datetime) -> None:
        instrument_currency_row = self._connection.execute(
            "\n            SELECT instrument.currency\n            FROM mra.instrument AS instrument\n            JOIN mra.data_capture AS capture\n              ON capture.capture_id = instrument.source_capture_id\n            JOIN mra.artifact AS artifact\n              ON artifact.artifact_id = capture.artifact_id\n            JOIN mra.trading_session AS session ON session.session_id = %s\n            JOIN mra.data_capture AS session_capture\n              ON session_capture.capture_id = session.source_capture_id\n            JOIN mra.artifact AS session_artifact\n              ON session_artifact.artifact_id = session_capture.artifact_id\n            WHERE instrument.instrument_id = %s\n              AND capture.status = 'CAPTURED'\n              AND artifact.integrity_state = 'AVAILABLE'\n              AND session_capture.status = 'CAPTURED'\n              AND session_artifact.integrity_state = 'AVAILABLE'\n            FOR SHARE OF instrument, session\n            ",
            (bar.session_id.value, bar.instrument_id.value),
        ).fetchone()
        if instrument_currency_row is None:
            raise RuntimeNotFoundError(f"Instrument {bar.instrument_id} does not exist")
        if str(instrument_currency_row[0]) != bar.open.currency:
            raise RuntimeStateConflictError("MarketBar money currency differs from canonical Instrument")
        self._validate_bar_predecessor(bar)
        self._connection.execute(
            "\n            INSERT INTO mra.market_bar_revision (\n                bar_revision_id, provider_product_id, capture_id,\n                instrument_id, session_id, timeframe, price_basis,\n                event_start, event_end, revision, supersedes_revision_id,\n                open_value, high_value, low_value, close_value,\n                volume_value, turnover_value, recorded_at, known_at,\n                decision_visible_at\n            )\n            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s,\n                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)\n            ",
            (
                bar.bar_revision_id,
                bar.provider_product_id,
                bar.capture_id,
                bar.instrument_id.value,
                bar.session_id.value,
                bar.timeframe.value,
                bar.price_basis.value,
                bar.event_start,
                bar.event_end,
                bar.revision,
                bar.supersedes_revision_id,
                bar.open.amount,
                bar.high.amount,
                bar.low.amount,
                bar.close.amount,
                bar.volume.amount,
                bar.turnover.amount if bar.turnover is not None else None,
                recorded_at,
                known_at,
                known_at,
            ),
        )

    def _insert_security_status_revision(self, fact: SecurityStatusFactRevision, *, recorded_at: datetime, known_at: datetime) -> None:
        self._validate_fact_predecessor(fact)
        self._connection.execute(
            "\n            INSERT INTO mra.instrument_fact_revision (\n                fact_revision_id, provider_product_id, capture_id,\n                instrument_id, session_id, fact_kind, evidence_scope,\n                event_start, event_end, value_kind, status_value,\n                revision, supersedes_revision_id, recorded_at, known_at,\n                decision_visible_at\n            )\n            VALUES (%s, %s, %s, %s, %s, 'SECURITY_STATUS', %s,\n                    %s, %s, 'STATUS', %s, %s, %s, %s, %s, %s)\n            ",
            (
                fact.fact_revision_id,
                fact.provider_product_id,
                fact.capture_id,
                fact.instrument_id.value,
                fact.session_id.value,
                fact.evidence_scope.value,
                fact.event_start,
                fact.event_end,
                fact.status.value,
                fact.revision,
                fact.supersedes_revision_id,
                recorded_at,
                known_at,
                known_at,
            ),
        )

    def _insert_instrument_fact_revision(self, fact: InstrumentFactRevision, *, recorded_at: datetime, known_at: datetime) -> None:
        if isinstance(fact.value, Money):
            instrument_currency = self._connection.execute(
                "SELECT currency FROM mra.instrument WHERE instrument_id = %s FOR SHARE", (fact.instrument_id.value,)
            ).fetchone()
            if instrument_currency is None:
                raise RuntimeNotFoundError(f"Instrument {fact.instrument_id} does not exist")
            if str(instrument_currency[0]) != fact.value.currency:
                raise RuntimeStateConflictError("InstrumentFact Money currency differs from canonical Instrument")
        self._validate_generic_fact_predecessor(fact)
        self._connection.execute(
            "\n            INSERT INTO mra.instrument_fact_revision (\n                fact_revision_id, provider_product_id, capture_id,\n                instrument_id, session_id, fact_kind, evidence_scope,\n                event_start, event_end, value_kind, numeric_value, unit_code,\n                revision, supersedes_revision_id, recorded_at, known_at,\n                decision_visible_at\n            )\n            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'DECIMAL',\n                    %s, %s, %s, %s, %s, %s, %s)\n            ",
            (
                fact.fact_revision_id,
                fact.provider_product_id,
                fact.capture_id,
                fact.instrument_id.value,
                fact.session_id.value if fact.session_id is not None else None,
                fact.fact_kind.value,
                fact.evidence_scope.value,
                fact.event_start,
                fact.event_end,
                fact.numeric_value,
                fact.unit_code,
                fact.revision,
                fact.supersedes_revision_id,
                recorded_at,
                known_at,
                known_at,
            ),
        )

    def _insert_lifecycle_status_revision(
        self, fact: InstrumentLifecycleFactRevision, *, recorded_at: datetime, known_at: datetime
    ) -> None:
        self._validate_generic_fact_predecessor(fact)
        self._connection.execute(
            "\n            INSERT INTO mra.instrument_fact_revision (\n                fact_revision_id, provider_product_id, capture_id,\n                instrument_id, session_id, fact_kind, evidence_scope,\n                event_start, event_end, value_kind, status_value,\n                revision, supersedes_revision_id, recorded_at, known_at,\n                decision_visible_at\n            )\n            VALUES (%s, %s, %s, %s, NULL, %s, 'EFFECTIVE_INTERVAL',\n                    %s, %s, 'STATUS', %s, %s, %s, %s, %s, %s)\n            ",
            (
                fact.fact_revision_id,
                fact.provider_product_id,
                fact.capture_id,
                fact.instrument_id.value,
                fact.fact_kind.value,
                fact.effective_from,
                fact.effective_to,
                fact.status.value,
                fact.revision,
                fact.supersedes_revision_id,
                recorded_at,
                known_at,
                known_at,
            ),
        )

    def _insert_corporate_action(self, action: CorporateActionRevision, *, recorded_at: datetime, known_at: datetime) -> None:
        instrument_currency_row = self._connection.execute(
            "\n            SELECT currency\n            FROM mra.instrument\n            WHERE instrument_id = %s\n            FOR SHARE\n            ",
            (action.instrument_id.value,),
        ).fetchone()
        if instrument_currency_row is None:
            raise RuntimeNotFoundError(f"Instrument {action.instrument_id} does not exist")
        if action.currency is not None and str(instrument_currency_row[0]) != action.currency:
            raise RuntimeStateConflictError("CorporateAction money currency differs from canonical Instrument")
        self._validate_action_predecessor(action)
        self._connection.execute(
            "\n            INSERT INTO mra.corporate_action_revision (\n                corporate_action_revision_id, provider_product_id, capture_id,\n                instrument_id, action_key, action_type, ex_session_id,\n                record_session_id, pay_session_id, successor_instrument_id,\n                cash_amount_per_share,\n                ratio_factor, subscription_price, currency, revision,\n                supersedes_revision_id, recorded_at, known_at,\n                decision_visible_at\n            )\n            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,\n                    %s, %s, %s, %s, %s, %s)\n            ",
            (
                action.corporate_action_revision_id,
                action.provider_product_id,
                action.capture_id,
                action.instrument_id.value,
                action.action_key,
                action.action_type.value,
                action.ex_session_id.value,
                action.record_session_id.value if action.record_session_id is not None else None,
                action.pay_session_id.value if action.pay_session_id is not None else None,
                action.successor_instrument_id.value if action.successor_instrument_id is not None else None,
                action.cash_amount_per_share.amount if action.cash_amount_per_share is not None else None,
                action.ratio_factor,
                action.subscription_price.amount if action.subscription_price is not None else None,
                action.currency,
                action.revision,
                action.supersedes_revision_id,
                recorded_at,
                known_at,
                known_at,
            ),
        )

    def _insert_source_gap(self, gap: SourceGap, *, recorded_at: datetime, known_at: datetime) -> None:
        self._connection.execute(
            "\n            INSERT INTO mra.source_gap (\n                gap_id, provider_product_id, capture_id, instrument_id,\n                session_id, instrument_code, identifier_scheme,\n                identifier_value, exchange, session_date,\n                classification_scheme, classification_code, action_key,\n                gap_kind, reason_code, fact_kind, timeframe,\n                instrument_fact_kind, evidence_scope, price_basis,\n                event_start, event_end, effective_from, effective_to,\n                detail, recorded_at, known_at, decision_visible_at\n            )\n            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,\n                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,\n                    %s, %s)\n            ",
            (
                gap.gap_id,
                gap.provider_product_id,
                gap.capture_id,
                gap.instrument_id.value if gap.instrument_id is not None else None,
                gap.session_id.value if gap.session_id is not None else None,
                gap.instrument_code,
                gap.identifier_scheme,
                gap.identifier_value,
                gap.exchange,
                gap.session_date,
                gap.classification_scheme,
                gap.classification_code,
                gap.action_key,
                gap.gap_kind.value,
                gap.reason_code.value,
                gap.fact_kind.value,
                gap.timeframe.value if gap.timeframe is not None else None,
                gap.instrument_fact_kind.value if gap.instrument_fact_kind is not None else None,
                gap.evidence_scope.value if gap.evidence_scope is not None else None,
                gap.price_basis.value if gap.price_basis is not None else None,
                gap.event_start,
                gap.event_end,
                gap.effective_from,
                gap.effective_to,
                gap.detail,
                recorded_at,
                known_at,
                known_at,
            ),
        )

    def _normalization_times(self, capture: ProviderCapture) -> tuple[datetime, datetime]:
        row = self._connection.execute("SELECT clock_timestamp()").fetchone()
        if row is None:
            raise AssertionError("PostgreSQL normalization clock must return one row")
        recorded_at = row[0]
        return (recorded_at, max(capture.temporal.capture_completed_at, recorded_at))

    def _validate_bar_predecessor(self, item: MarketBarRevision) -> None:
        if item.supersedes_revision_id is None:
            return
        row = self._connection.execute(
            "\n            SELECT provider_product_id, instrument_id, session_id, timeframe,\n                   price_basis, event_start, event_end, revision\n            FROM mra.market_bar_revision\n            WHERE bar_revision_id = %s\n            FOR SHARE\n            ",
            (item.supersedes_revision_id,),
        ).fetchone()
        expected = (
            item.provider_product_id,
            item.instrument_id.value,
            item.session_id.value,
            item.timeframe.value,
            item.price_basis.value,
            item.event_start,
            item.event_end,
            item.revision - 1,
        )
        if row != expected:
            raise RuntimeStateConflictError("MarketBar predecessor is not the same logical fact")

    def _validate_fact_predecessor(self, item: SecurityStatusFactRevision) -> None:
        if item.supersedes_revision_id is None:
            return
        row = self._connection.execute(
            "\n            SELECT provider_product_id, instrument_id, session_id, fact_kind,\n                   evidence_scope, event_start, event_end, revision\n            FROM mra.instrument_fact_revision\n            WHERE fact_revision_id = %s\n            FOR SHARE\n            ",
            (item.supersedes_revision_id,),
        ).fetchone()
        expected = (
            item.provider_product_id,
            item.instrument_id.value,
            item.session_id.value,
            "SECURITY_STATUS",
            item.evidence_scope.value,
            item.event_start,
            item.event_end,
            item.revision - 1,
        )
        if row != expected:
            raise RuntimeStateConflictError("InstrumentFact predecessor is not the same logical fact")

    def _validate_generic_fact_predecessor(self, item: InstrumentFactRevision | InstrumentLifecycleFactRevision) -> None:
        if item.supersedes_revision_id is None:
            return
        row = self._connection.execute(
            "\n            SELECT provider_product_id, instrument_id, session_id, fact_kind,\n                   evidence_scope, event_start, event_end, revision\n            FROM mra.instrument_fact_revision\n            WHERE fact_revision_id = %s\n            FOR SHARE\n            ",
            (item.supersedes_revision_id,),
        ).fetchone()
        expected_prefix = (
            item.provider_product_id,
            item.instrument_id.value,
            item.session_id.value if isinstance(item, InstrumentFactRevision) and item.session_id is not None else None,
            item.fact_kind.value,
            item.evidence_scope.value if isinstance(item, InstrumentFactRevision) else "EFFECTIVE_INTERVAL",
            item.event_start if isinstance(item, InstrumentFactRevision) else item.effective_from,
        )
        effective_timeline = isinstance(item, InstrumentLifecycleFactRevision) or (
            isinstance(item, InstrumentFactRevision) and item.evidence_scope.value == "EFFECTIVE_INTERVAL"
        )
        if effective_timeline:
            matches = row is not None and (*row[:6], row[7]) == (*expected_prefix, item.revision - 1)
        else:
            assert isinstance(item, InstrumentFactRevision)
            matches = row == (*expected_prefix, item.event_end, item.revision - 1)
        if not matches:
            raise RuntimeStateConflictError("InstrumentFact predecessor is not the same logical fact")

    def _validate_action_predecessor(self, item: CorporateActionRevision) -> None:
        if item.supersedes_revision_id is None:
            return
        row = self._connection.execute(
            "\n            SELECT provider_product_id, instrument_id, action_key, revision\n            FROM mra.corporate_action_revision\n            WHERE corporate_action_revision_id = %s\n            FOR SHARE\n            ",
            (item.supersedes_revision_id,),
        ).fetchone()
        if row != (item.provider_product_id, item.instrument_id.value, item.action_key, item.revision - 1):
            raise RuntimeStateConflictError("CorporateAction predecessor is not exact")
