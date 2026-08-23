"""T+1 Outcome orchestration inside the sole Continuous control plane."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable, Protocol

from market_regime_alpha.application.continuous_research.daily_alpha import (
    DailyAlphaPredictionSnapshot,
)
from market_regime_alpha.application.shadow_research.free_data_settlement import (
    FreeDataSettlementOperator,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)
from market_regime_alpha.platform.runtime_governance import RuntimeAuthorityMode


class TradingSessionCalendar(Protocol):
    @property
    def trading_dates(self) -> tuple[date, ...]: ...


class ContinuousOutcomeSettlementService:
    """Resolve one due Shadow Decision, then delegate to existing Outcome owners."""

    def __init__(
        self,
        factory: PostgresConnectionFactory,
        *,
        clock: Callable[[], datetime],
    ) -> None:
        self._factory = factory
        self._clock = clock

    def settle_previous_if_due(
        self,
        *,
        calendar: TradingSessionCalendar,
        current_session: date,
        artifact_root: Path,
        authority_mode: RuntimeAuthorityMode,
    ) -> dict[str, Any]:
        if authority_mode is not RuntimeAuthorityMode.SHADOW:
            return {
                "status": "NOT_APPLICABLE",
                "reason_codes": ["SHADOW_OUTCOME_AUTHORITY_NOT_ACTIVE"],
            }
        sessions = calendar.trading_dates
        if current_session not in sessions:
            return {
                "status": "CALENDAR_BLOCKED",
                "reason_codes": ["CURRENT_SESSION_NOT_IN_CANONICAL_CALENDAR"],
            }
        with self._factory.connection(read_only=True) as connection:
            target_rows = connection.execute(
                """
                SELECT artifact.artifact_id, artifact.artifact_hash,
                       artifact.payload_json
                FROM daily_alpha_prediction_target_session AS target
                JOIN research_validation_artifact AS artifact
                  ON artifact.artifact_id = target.snapshot_id
                 AND artifact.artifact_hash = target.snapshot_hash
                WHERE target.target_session = %s
                ORDER BY artifact.artifact_id
                """,
                (current_session,),
            ).fetchall()
        if len(target_rows) > 1:
            return {
                "status": "LINEAGE_AMBIGUOUS",
                "target_session": current_session.isoformat(),
                "reason_codes": ["DAILY_PREDICTION_TARGET_SCOPE_AMBIGUOUS"],
            }
        snapshot: DailyAlphaPredictionSnapshot | None = None
        if target_rows:
            row = target_rows[0]
            if not isinstance(row[2], dict):
                return {
                    "status": "LINEAGE_AMBIGUOUS",
                    "target_session": current_session.isoformat(),
                    "reason_codes": ["DAILY_PREDICTION_TARGET_OWNER_MALFORMED"],
                }
            try:
                snapshot = DailyAlphaPredictionSnapshot.from_canonical_dict(
                    {
                        "snapshot_id": str(row[0]),
                        "snapshot_hash": str(row[1]),
                        **row[2],
                    }
                )
            except (KeyError, TypeError, ValueError):
                return {
                    "status": "LINEAGE_AMBIGUOUS",
                    "target_session": current_session.isoformat(),
                    "reason_codes": ["DAILY_PREDICTION_TARGET_OWNER_MALFORMED"],
                }
            if snapshot.target_session_date != current_session:
                return {
                    "status": "LINEAGE_AMBIGUOUS",
                    "target_session": current_session.isoformat(),
                    "reason_codes": ["DAILY_PREDICTION_TARGET_OWNER_DRIFTED"],
                }
            previous_session = snapshot.trading_date
            with self._factory.connection(read_only=True) as connection:
                rows = connection.execute(
                    """
                    SELECT session.session_id, decision.decision_id, session.status
                    FROM shadow_research_decision AS decision
                    JOIN shadow_research_session AS session
                      ON session.session_id = decision.session_id
                    WHERE decision.run_id = %s AND decision.tick_id = %s
                      AND session.trading_date = %s
                      AND session.status IN ('OUTCOME_PENDING', 'SETTLED')
                    ORDER BY session.session_id
                    """,
                    (
                        str(snapshot.run_reference.artifact_id),
                        str(snapshot.tick_reference.artifact_id),
                        previous_session,
                    ),
                ).fetchall()
        else:
            index = sessions.index(current_session)
            if index == 0:
                return {
                    "status": "NO_DUE_PREDICTION",
                    "reason_codes": ["NO_PREVIOUS_CANONICAL_SESSION"],
                }
            previous_session = sessions[index - 1]
            with self._factory.connection(read_only=True) as connection:
                rows = connection.execute(
                """
                SELECT session_id, decision_id, status
                FROM shadow_research_session
                WHERE trading_date = %s
                  AND status IN ('OUTCOME_PENDING', 'SETTLED')
                ORDER BY session_id
                """,
                (previous_session,),
            ).fetchall()
            if rows and any(str(row[2]) != "SETTLED" for row in rows):
                return {
                    "status": "LINEAGE_MISSING",
                    "decision_session": previous_session.isoformat(),
                    "target_session": current_session.isoformat(),
                    "reason_codes": ["DAILY_PREDICTION_TARGET_OWNER_MISSING"],
                }
        if not rows:
            return {
                "status": "NO_DUE_PREDICTION",
                "decision_session": previous_session.isoformat(),
                "target_session": current_session.isoformat(),
                "reason_codes": ["NO_PENDING_SHADOW_PREDICTION"],
            }
        if len(rows) != 1 or rows[0][1] is None:
            return {
                "status": "LINEAGE_AMBIGUOUS",
                "decision_session": previous_session.isoformat(),
                "target_session": current_session.isoformat(),
                "reason_codes": ["SHADOW_DECISION_SCOPE_AMBIGUOUS"],
            }
        decision_id = ArtifactId(str(rows[0][1]))
        already_settled = str(rows[0][2]) == "SETTLED"
        try:
            settled = FreeDataSettlementOperator(
                self._factory,
                clock=self._clock,
            ).settle_day(
                trading_date=previous_session,
                next_session_date=current_session,
                artifact_root=artifact_root,
                decision_id=decision_id,
                prediction_snapshot_reference=(
                    None if snapshot is None else snapshot.reference
                ),
            )
        except ValueError as exc:
            if str(exc) == "settle-day requires selected Candidates":
                return {
                    "status": "NO_SELECTED_CANDIDATES",
                    "decision_session": previous_session.isoformat(),
                    "target_session": current_session.isoformat(),
                    "reason_codes": ["NO_SELECTED_CANDIDATES"],
                }
            raise
        if settled["prediction_snapshot_id"] is None:
            return {
                "status": "HISTORICAL_V1_REPLAY_VERIFIED",
                "decision_session": previous_session.isoformat(),
                "target_session": current_session.isoformat(),
                "shadow_decision_id": str(decision_id),
                "settlement_id": settled["factual_outcome_id"],
                "targeted_outcome_id": settled["targeted_outcome_id"],
                "reason_codes": [
                    "HISTORICAL_OUTCOME_V1_IMMUTABLE",
                    "DAILY_PREDICTION_LINEAGE_NOT_RETROFITTED",
                ],
            }
        return {
            "status": "REPLAY_VERIFIED" if already_settled else "SETTLED",
            "decision_session": previous_session.isoformat(),
            "target_session": current_session.isoformat(),
            "shadow_decision_id": str(decision_id),
            "prediction_snapshot_id": settled["prediction_snapshot_id"],
            "prediction_snapshot_hash": settled["prediction_snapshot_hash"],
            "settlement_id": settled["factual_outcome_id"],
            "targeted_outcome_id": settled["targeted_outcome_id"],
            "reason_codes": [
                "T_PLUS_1_OUTCOME_SETTLED_IDEMPOTENTLY",
                "EXACT_PREDICTION_SNAPSHOT_LINEAGE",
                "PREDICTION_SNAPSHOT_IMMUTABLE",
            ],
        }


__all__ = ["ContinuousOutcomeSettlementService"]
