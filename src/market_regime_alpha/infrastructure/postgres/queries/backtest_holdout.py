"""Exact holdout facts and visible execution blockers; no label values."""

from typing import Any
from uuid import UUID

from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from market_regime_alpha.infrastructure.postgres.repositories.backtest_holdout import PostgresBacktestHoldoutRepository, evaluation_roster
from market_regime_alpha.research_qualification.domain.backtest_holdout import BacktestHoldoutReservation
from market_regime_alpha.research_qualification.ports.artifacts import ResearchArtifactByteStore
from market_regime_alpha.runtime.errors import ArtifactIntegrityError


class PostgresBacktestHoldoutReadPort:
    def __init__(self, pool: TargetPostgresPool, byte_store: ResearchArtifactByteStore) -> None:
        self._pool, self._byte_store = pool, byte_store

    def reservation(self, reservation_id: UUID) -> BacktestHoldoutReservation:
        with self._pool.connection(read_only=True) as c:
            record = PostgresBacktestHoldoutRepository(c).record(reservation_id, opening=False)
        return BacktestHoldoutReservation.from_payload(record["body"])

    def development_evaluation_roster(self, run_id: UUID) -> tuple[tuple[str, str, str, str], ...]:
        with self._pool.connection(read_only=True) as c:
            return evaluation_roster(c, run_id)

    def model_features(self, model_id: UUID) -> tuple[tuple[UUID, str], ...]:
        with self._pool.connection(read_only=True) as c:
            return tuple(c.execute("SELECT feature_definition_id,feature_definition_sha256 FROM mra.model_feature_definition "
                "WHERE model_id=%s ORDER BY ordinal", (model_id,)).fetchall())

    def inspect(self, reservation_id: UUID) -> dict[str, Any]:
        with self._pool.connection(read_only=True) as c:
            c.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            repository = PostgresBacktestHoldoutRepository(c)
            reservation = repository.record(reservation_id, opening=False)
            exists = c.execute("SELECT 1 FROM mra.backtest_holdout_opening WHERE reservation_id=%s", (reservation_id,)).fetchone()
            opening = None if exists is None else repository.record(reservation_id, opening=True)
            accesses = c.execute("""
                SELECT access.evaluation_run_id,count(*),min(access.accessed_at),max(access.accessed_at)
                FROM mra.research_partition_outcome_access access
                JOIN mra.backtest_holdout_opening opening ON access.evaluation_run_id=ANY(opening.allowed_evaluation_ids)
                WHERE opening.reservation_id=%s GROUP BY access.evaluation_run_id ORDER BY access.evaluation_run_id
                """, (reservation_id,)).fetchall()
        return {"reservation": reservation, "opening": opening, "state": "RESERVED_BLOCKED" if opening is None else
            ("OPENED_NOT_ACCESSED" if not accesses else "ACCESSED"), "evaluation_accesses": accesses,
            "authority": "EXPLORATORY_TEMPORAL_ONLY; RAW_BACKFILL_ALREADY_VISIBLE; NOT_FORMAL_OOS"}

    def execution_blockers(self, run_id: UUID) -> tuple[str, ...]:
        with self._pool.connection(read_only=True) as c:
            rows = c.execute("""
                SELECT reservation.reservation_id FROM mra.backtest_holdout_reservation reservation
                WHERE future_run_id=%s AND NOT EXISTS(SELECT 1 FROM mra.backtest_holdout_opening opening
                    WHERE opening.reservation_id=reservation.reservation_id)
                """, (run_id,)).fetchall()
        self.verify_artifacts(run_id=run_id)
        return tuple("EXPLORATORY_HOLDOUT_RESERVED:" + str(row[0]) for row in rows)

    def verify_evaluation_artifacts(self, evaluation_id: UUID) -> None:
        self.verify_artifacts(evaluation_id=evaluation_id)

    def verify_artifacts(self, *, run_id: UUID | None = None, commitment_id: UUID | None = None, evaluation_id: UUID | None = None) -> None:
        with self._pool.connection(read_only=True) as c:
            rows = c.execute("""SELECT reservation.protocol_content_sha256,reservation.protocol_size_bytes,
                opening.selection_content_sha256,opening.selection_size_bytes
                FROM mra.backtest_holdout_reservation reservation
                LEFT JOIN mra.backtest_holdout_opening opening USING(reservation_id)
                WHERE reservation.future_run_id=%s OR %s=ANY(opening.allowed_evaluation_ids) OR EXISTS (
                    SELECT 1 FROM mra.decision_target_commitment commitment WHERE commitment.commitment_id=%s
                    AND commitment.instrument_id=ANY(reservation.instrument_ids)
                    AND commitment.decision_time<reservation.protected_end
                    AND mra.backtest_holdout_commitment_end(commitment.commitment_id)>=reservation.protected_start)
                """,(run_id,evaluation_id,commitment_id)).fetchall()
        # Immutable owner identities are reloaded each call; physical bytes are
        # hashed outside a business write transaction, without a mutable cache.
        for row in rows:
            for digest,size in ((row[0],row[1]),(row[2],row[3])):
                if digest is not None and self._byte_store.verify(digest,expected_size=size).result != "VERIFIED":
                    raise ArtifactIntegrityError("EXPLORATORY_HOLDOUT_ARTIFACT_INTEGRITY_BLOCKED")
