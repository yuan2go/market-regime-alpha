"""PostgreSQL append-only authority for Summary-scoped factual outcomes."""

from __future__ import annotations

from datetime import UTC, date, datetime
import json
from typing import Any, Callable

import psycopg
from psycopg.types.json import Jsonb

from market_regime_alpha.application.controlled_operation.outcome_evidence import (
    TradeHorizonOutcomeEvidence,
)
from market_regime_alpha.application.controlled_operation.outcome_source_archive import (
    OutcomeSettlementSourceArchive,
)
from market_regime_alpha.application.controlled_operation.prospective_outcome import (
    ProspectiveShadowOutcome,
    SettlementSessionStatus,
    build_prospective_shadow_outcome,
)
from market_regime_alpha.application.continuous_research.daily_alpha import (
    DAILY_ALPHA_PREDICTION_KIND,
    DailyAlphaPredictionSnapshot,
)
from market_regime_alpha.application.shadow_research.contracts import ShadowSessionStatus
from market_regime_alpha.application.shadow_research.postgres_repository import (
    PostgresShadowResearchRepository,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.market_data.artifacts import VerifiedMarketDataDataset
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from market_regime_alpha.persistence.postgres.migrator import PostgresMigrator


Clock = Callable[[], datetime]


class ProspectiveOutcomeConflict(ValueError):
    """Outcome idempotency, lineage or Shadow CAS conflict."""


class ProspectiveOutcomeIntegrityError(ValueError):
    """Stored factual Outcome failed canonical restoration or replay."""


def _now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


class PostgresProspectiveOutcomeRepository:
    """Settle one frozen Shadow Decision from verified immutable evidence."""

    def __init__(
        self,
        factory: PostgresConnectionFactory,
        *,
        clock: Clock = _now,
        apply_migrations: bool = False,
    ) -> None:
        if not isinstance(factory, PostgresConnectionFactory):
            raise TypeError("factory must be PostgresConnectionFactory")
        if not callable(clock):
            raise TypeError("clock must be callable")
        self._factory = factory
        self._clock = clock
        if apply_migrations:
            PostgresMigrator().apply_all(factory)
        self._shadow = PostgresShadowResearchRepository(factory, clock=clock, apply_migrations=False)

    def build(
        self,
        *,
        decision_id: ArtifactId,
        prediction_snapshot: DailyAlphaPredictionSnapshot,
        source_archive: OutcomeSettlementSourceArchive,
        settlement_dataset: VerifiedMarketDataDataset,
        factual_evidence: TradeHorizonOutcomeEvidence,
        next_session_date: date,
        session_status: SettlementSessionStatus,
        created_at: datetime,
    ) -> ProspectiveShadowOutcome:
        decision = self._shadow.replay(decision_id)
        return build_prospective_shadow_outcome(
            decision=decision,
            prediction_snapshot=prediction_snapshot,
            source_archive=source_archive,
            settlement_dataset=settlement_dataset,
            factual_evidence=factual_evidence,
            next_session_date=next_session_date,
            session_status=session_status,
            created_at=created_at,
        )

    def settle(
        self,
        settlement: ProspectiveShadowOutcome,
        *,
        expected_shadow_version: int,
    ) -> ProspectiveShadowOutcome:
        if not isinstance(settlement, ProspectiveShadowOutcome):
            raise TypeError("settlement must be ProspectiveShadowOutcome")
        decision = self._shadow.replay(settlement.shadow_decision.artifact_id)
        prediction = self._verify_prediction_lineage(settlement)
        if (
            settlement.shadow_decision.content_hash != decision.decision_hash
            or settlement.shadow_session_id != decision.session_id
            or settlement.run_id != decision.run_id
            or settlement.tick_id != decision.tick_id
            or settlement.summary != decision.summary
            or settlement.candidate_set != decision.candidate_set
            or settlement.signal != decision.signal
            or settlement.forecast != decision.forecast
            or settlement.model_selection_receipts != decision.model_selection_receipts
            or (
                prediction is not None
                and (
                    prediction.run_reference.artifact_id != decision.run_id
                    or prediction.tick_reference.artifact_id != decision.tick_id
                    or prediction.candidate_reference != decision.candidate_set
                    or prediction.signal_reference != decision.signal
                    or decision.forecast not in prediction.forecast_references
                    or prediction.strategy_diagnostic_reference
                    != settlement.strategy_diagnostic
                )
            )
        ):
            raise ProspectiveOutcomeConflict("Outcome frozen-decision lineage mismatch")
        if settlement.outcome_available_at <= decision.decision_frozen_at:
            raise ProspectiveOutcomeConflict("Outcome is not prospective to decision freeze")

        def operation(connection: psycopg.Connection[Any]) -> None:
            session = connection.execute(
                """
                SELECT status, outcome_status, decision_id, version
                FROM shadow_research_session
                WHERE session_id = %s FOR UPDATE
                """,
                (str(settlement.shadow_session_id),),
            ).fetchone()
            if session is None:
                raise KeyError(str(settlement.shadow_session_id))
            existing = connection.execute(
                """
                SELECT settlement_id, settlement_hash, payload_json
                FROM prospective_outcome_settlement
                WHERE shadow_decision_id = %s
                """,
                (str(decision.decision_id),),
            ).fetchone()
            if existing is not None:
                if (
                    str(existing[0]) != str(settlement.settlement_id)
                    or str(existing[1]) != settlement.settlement_hash
                    or _json_object(existing[2]) != settlement.to_canonical_dict()
                ):
                    raise ProspectiveOutcomeConflict("Outcome settlement idempotency conflict")
                if str(session[0]) == ShadowSessionStatus.SETTLED.value:
                    return
            if (
                str(session[0]) != ShadowSessionStatus.OUTCOME_PENDING.value
                or str(session[2]) != str(decision.decision_id)
                or int(session[3]) != expected_shadow_version
            ):
                raise ProspectiveOutcomeConflict("Outcome settlement rejected by Shadow status/version CAS")
            if existing is None:
                if (
                    settlement.prediction_snapshot is None
                    or settlement.strategy_diagnostic is None
                ):
                    raise ProspectiveOutcomeConflict(
                        "new Outcome requires exact Daily prediction lineage"
                    )
                connection.execute(
                    """
                    INSERT INTO prospective_outcome_settlement(
                        settlement_id, settlement_hash, shadow_decision_id,
                        shadow_session_id, run_id, tick_id, summary_id,
                        next_session_date, source_archive_id,
                        source_archive_hash, source_dataset_id,
                        source_dataset_hash, factual_evidence_id,
                        factual_evidence_hash, availability_status,
                        outcome_available_at, prediction_snapshot_id,
                        prediction_snapshot_hash, strategy_diagnostic_id,
                        strategy_diagnostic_hash, payload_json, created_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s
                    )
                    """,
                    (
                        str(settlement.settlement_id),
                        settlement.settlement_hash,
                        str(decision.decision_id),
                        str(settlement.shadow_session_id),
                        str(settlement.run_id),
                        str(settlement.tick_id),
                        str(settlement.summary.artifact_id),
                        settlement.next_session_date,
                        str(settlement.source_archive.artifact_id),
                        settlement.source_archive.content_hash,
                        str(settlement.source_dataset.artifact_id),
                        settlement.source_dataset.content_hash,
                        str(settlement.factual_evidence.artifact_id),
                        settlement.factual_evidence.content_hash,
                        settlement.availability_status.value,
                        settlement.outcome_available_at,
                        str(settlement.prediction_snapshot.artifact_id),
                        settlement.prediction_snapshot.content_hash,
                        str(settlement.strategy_diagnostic.artifact_id),
                        settlement.strategy_diagnostic.content_hash,
                        Jsonb(settlement.to_canonical_dict()),
                        settlement.created_at,
                    ),
                )
            reasons = tuple(sorted({*settlement.reason_codes, "OUTCOME_SETTLEMENT_RECORDED"}))
            updated = connection.execute(
                """
                UPDATE shadow_research_session
                SET status = 'SETTLED', outcome_status = %s,
                    version = version + 1, reason_codes_json = %s,
                    updated_at = %s, finished_at = %s
                WHERE session_id = %s AND status = 'OUTCOME_PENDING'
                  AND decision_id = %s AND version = %s
                """,
                (
                    ("UNAVAILABLE" if settlement.availability_status.value == "UNAVAILABLE" else "SETTLED"),
                    Jsonb(list(reasons)),
                    settlement.created_at,
                    settlement.created_at,
                    str(settlement.shadow_session_id),
                    str(decision.decision_id),
                    expected_shadow_version,
                ),
            ).rowcount
            if updated != 1:
                raise ProspectiveOutcomeConflict("Outcome settlement lost Shadow CAS")
            connection.execute(
                """
                INSERT INTO shadow_research_event(
                    session_id, decision_id, event_type, from_status,
                    to_status, expected_version, resulting_version,
                    reason_codes_json, event_time, payload_json
                ) VALUES (
                    %s, %s, 'SESSION_SETTLED', 'OUTCOME_PENDING',
                    'SETTLED', %s, %s, %s, %s, %s
                )
                """,
                (
                    str(settlement.shadow_session_id),
                    str(decision.decision_id),
                    expected_shadow_version,
                    expected_shadow_version + 1,
                    Jsonb(list(reasons)),
                    settlement.created_at,
                    Jsonb(
                        {
                            "settlement_id": str(settlement.settlement_id),
                            "settlement_hash": settlement.settlement_hash,
                        }
                    ),
                ),
            )

        self._factory.run_transaction(operation)
        return self.get(settlement.settlement_id)

    def get(self, settlement_id: ArtifactId) -> ProspectiveShadowOutcome:
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                """
                SELECT payload_json, settlement_hash, shadow_decision_id,
                       source_archive_id, source_archive_hash,
                       source_dataset_id, source_dataset_hash,
                       factual_evidence_id, factual_evidence_hash,
                       prediction_snapshot_id, prediction_snapshot_hash,
                       strategy_diagnostic_id, strategy_diagnostic_hash
                FROM prospective_outcome_settlement
                WHERE settlement_id = %s
                """,
                (str(settlement_id),),
            ).fetchone()
        if row is None:
            raise KeyError(str(settlement_id))
        try:
            settlement = ProspectiveShadowOutcome.from_canonical_dict(_json_object(row[0]))
        except (KeyError, TypeError, ValueError) as exc:
            raise ProspectiveOutcomeIntegrityError("Outcome settlement failed canonical restoration") from exc
        expected = (
            settlement.settlement_hash,
            str(settlement.shadow_decision.artifact_id),
            str(settlement.source_archive.artifact_id),
            settlement.source_archive.content_hash,
            str(settlement.source_dataset.artifact_id),
            settlement.source_dataset.content_hash,
            str(settlement.factual_evidence.artifact_id),
            settlement.factual_evidence.content_hash,
            (
                None
                if settlement.prediction_snapshot is None
                else str(settlement.prediction_snapshot.artifact_id)
            ),
            (
                None
                if settlement.prediction_snapshot is None
                else settlement.prediction_snapshot.content_hash
            ),
            (
                None
                if settlement.strategy_diagnostic is None
                else str(settlement.strategy_diagnostic.artifact_id)
            ),
            (
                None
                if settlement.strategy_diagnostic is None
                else settlement.strategy_diagnostic.content_hash
            ),
        )
        actual = tuple(None if item is None else str(item) for item in row[1:])
        if expected != actual:
            raise ProspectiveOutcomeIntegrityError("Outcome owner lineage drift")
        return settlement

    def get_for_decision(self, decision_id: ArtifactId) -> ProspectiveShadowOutcome:
        """Resolve the immutable factual settlement for one frozen Decision."""

        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                """
                SELECT settlement_id FROM prospective_outcome_settlement
                WHERE shadow_decision_id = %s
                """,
                (str(decision_id),),
            ).fetchone()
        if row is None:
            raise KeyError(str(decision_id))
        return self.get(ArtifactId(str(row[0])))

    def replay(
        self,
        settlement_id: ArtifactId,
        *,
        source_archive: OutcomeSettlementSourceArchive,
        settlement_dataset: VerifiedMarketDataDataset,
        factual_evidence: TradeHorizonOutcomeEvidence,
    ) -> ProspectiveShadowOutcome:
        stored = self.get(settlement_id)
        prediction = self._verify_prediction_lineage(stored)
        if prediction is None:
            decision = self._shadow.replay(stored.shadow_decision.artifact_id)
            rebuilt = build_prospective_shadow_outcome(
                decision=decision,
                prediction_snapshot=None,
                source_archive=source_archive,
                settlement_dataset=settlement_dataset,
                factual_evidence=factual_evidence,
                next_session_date=stored.next_session_date,
                session_status=stored.session_status,
                created_at=stored.created_at,
                schema_version="prospective-shadow-outcome/v1",
            )
        else:
            rebuilt = self.build(
                decision_id=stored.shadow_decision.artifact_id,
                prediction_snapshot=prediction,
                source_archive=source_archive,
                settlement_dataset=settlement_dataset,
                factual_evidence=factual_evidence,
                next_session_date=stored.next_session_date,
                session_status=stored.session_status,
                created_at=stored.created_at,
            )
        if rebuilt != stored:
            raise ProspectiveOutcomeIntegrityError("Outcome settlement did not replay deterministically")
        return rebuilt

    def _verify_prediction_lineage(
        self,
        settlement: ProspectiveShadowOutcome,
    ) -> DailyAlphaPredictionSnapshot | None:
        reference = settlement.prediction_snapshot
        if reference is None:
            if settlement.schema_version != "prospective-shadow-outcome/v1":
                raise ProspectiveOutcomeIntegrityError(
                    "Outcome prediction lineage is missing"
                )
            return None
        if reference.reference_kind != DAILY_ALPHA_PREDICTION_KIND:
            raise ProspectiveOutcomeIntegrityError(
                "Outcome prediction owner kind drifted"
            )
        with self._factory.connection(read_only=True) as connection:
            row = connection.execute(
                """
                SELECT artifact_hash, payload_json
                FROM research_validation_artifact
                WHERE artifact_id = %s AND artifact_kind = %s
                """,
                (str(reference.artifact_id), DAILY_ALPHA_PREDICTION_KIND),
            ).fetchone()
        if row is None or str(row[0]) != reference.content_hash:
            raise ProspectiveOutcomeIntegrityError(
                "Outcome prediction owner hash drifted"
            )
        prediction = DailyAlphaPredictionSnapshot.from_canonical_dict(
            {
                "snapshot_id": str(reference.artifact_id),
                "snapshot_hash": reference.content_hash,
                **_json_object(row[1]),
            }
        )
        if (
            prediction.reference != reference
            or settlement.strategy_diagnostic
            != prediction.strategy_diagnostic_reference
            or settlement.outcome_available_at <= prediction.available_at
        ):
            raise ProspectiveOutcomeIntegrityError(
                "Outcome exact prediction lineage drifted"
            )
        return prediction


def _json_object(value: object) -> dict[str, Any]:
    if isinstance(value, str):
        value = json.loads(value)
    if not isinstance(value, dict):
        raise ProspectiveOutcomeIntegrityError("stored Outcome payload is not an object")
    return value


__all__ = [
    "PostgresProspectiveOutcomeRepository",
    "ProspectiveOutcomeConflict",
    "ProspectiveOutcomeIntegrityError",
]
