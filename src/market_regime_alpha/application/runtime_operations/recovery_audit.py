"""Read-only PostgreSQL recovery audit across the one Continuous Runtime."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any

from market_regime_alpha.application.strategy_shadow.postgres_portfolio import (
    PostgresShadowPortfolioRepository,
)
from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.persistence.postgres.connection import (
    PostgresConnectionFactory,
)


class RecoveryIssueKind(str, Enum):
    EXPIRED_TICK_LEASE = "EXPIRED_TICK_LEASE"
    RETRYABLE_TICK = "RETRYABLE_TICK"
    PROVIDER_FAILURE = "PROVIDER_FAILURE"
    PARTIAL_RESEARCH_SHADOW = "PARTIAL_RESEARCH_SHADOW"
    MISSED_SETTLEMENT = "MISSED_SETTLEMENT"
    EVALUATION_PANEL_MISSING = "EVALUATION_PANEL_MISSING"
    PARTIAL_STRATEGY_SHADOW = "PARTIAL_STRATEGY_SHADOW"
    PORTFOLIO_REPLAY_FAILED = "PORTFOLIO_REPLAY_FAILED"


@dataclass(frozen=True, slots=True)
class RecoveryIssue:
    issue_kind: RecoveryIssueKind
    authority_kind: str
    authority_id: str
    status: str
    recovery_command: str
    reason_codes: tuple[str, ...]

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "issue_kind": self.issue_kind.value,
            "authority_kind": self.authority_kind,
            "authority_id": self.authority_id,
            "status": self.status,
            "recovery_command": self.recovery_command,
            "reason_codes": list(self.reason_codes),
        }


@dataclass(frozen=True, slots=True)
class RecoveryAuditReport:
    checked_at: datetime
    checked_through_date: date
    issues: tuple[RecoveryIssue, ...]
    portfolio_replay_verified_count: int
    production_mutation_performed: bool = False

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "operation": "RECOVERY_AUDIT",
            "checked_at": self.checked_at.isoformat(),
            "checked_through_date": self.checked_through_date.isoformat(),
            "status": "RECOVERY_REQUIRED" if self.issues else "CLEAN",
            "issue_count": len(self.issues),
            "issues": [item.to_canonical_dict() for item in self.issues],
            "portfolio_replay_verified_count": self.portfolio_replay_verified_count,
            "production_mutation_performed": False,
            "formal_pit": False,
            "formal_oos": False,
            "production_authorized": False,
            "live_broker_authorized": False,
        }


class PostgresRecoveryAudit:
    def __init__(self, factory: PostgresConnectionFactory) -> None:
        self._factory = factory
        self._portfolios = PostgresShadowPortfolioRepository(
            factory, apply_migrations=False
        )

    def inspect(self, *, checked_at: datetime) -> RecoveryAuditReport:
        if checked_at.tzinfo is None or checked_at.utcoffset() is None:
            raise ValueError("Recovery audit checked_at must be timezone-aware")
        issues: list[RecoveryIssue] = []
        with self._factory.connection(read_only=True) as connection:
            expired = connection.execute(
                """
                SELECT run_id, tick_id FROM continuous_runtime_tick
                WHERE status = 'IN_PROGRESS' AND lease_expires_at <= %s
                ORDER BY run_id, tick_id
                """,
                (checked_at,),
            ).fetchall()
            retryable = connection.execute(
                """
                SELECT run_id, tick_id, status FROM continuous_runtime_tick
                WHERE status IN ('FAILED', 'DATA_BLOCKED')
                  AND (retry_at IS NULL OR retry_at <= %s)
                ORDER BY run_id, tick_id
                """,
                (checked_at,),
            ).fetchall()
            provider_failures = connection.execute(
                """
                SELECT run_id, tick_id, status FROM (
                    SELECT DISTINCT ON (run_id, tick_id)
                           run_id, tick_id, status, retry_at
                    FROM continuous_provider_attempt
                    ORDER BY run_id, tick_id, attempt_number DESC
                ) AS latest
                WHERE status IN (
                    'FAILED', 'TIMED_OUT', 'INVALID_RESPONSE', 'RATE_LIMITED',
                    'CIRCUIT_OPEN', 'LEASE_EXPIRED'
                ) AND (retry_at IS NULL OR retry_at <= %s)
                ORDER BY run_id, tick_id
                """,
                (checked_at,),
            ).fetchall()
            research_partial = connection.execute(
                """
                SELECT session_id, run_id, status, trading_date
                FROM shadow_research_session
                WHERE status IN ('SCHEDULED', 'RUNNING', 'FROZEN', 'OUTCOME_PENDING')
                ORDER BY trading_date, session_id
                """
            ).fetchall()
            panel_missing = connection.execute(
                """
                SELECT session.session_id, session.run_id
                FROM shadow_research_session AS session
                JOIN shadow_research_decision AS decision
                  ON decision.decision_id = session.decision_id
                LEFT JOIN research_evaluation_panel_slice_v2 AS slice
                  ON slice.shadow_decision_id = decision.decision_id
                WHERE session.status = 'SETTLED' AND slice.panel_id IS NULL
                ORDER BY session.session_id
                """
            ).fetchall()
            strategy_partial = connection.execute(
                """
                SELECT session_id, status FROM strategy_shadow_session
                WHERE status IN ('SCHEDULED', 'RUNNING')
                ORDER BY trading_date, session_id
                """
            ).fetchall()
            portfolio_rows = connection.execute(
                "SELECT portfolio_id FROM strategy_shadow_portfolio ORDER BY portfolio_id"
            ).fetchall()
        for run_id, tick_id in expired:
            issues.append(
                _issue(
                    RecoveryIssueKind.EXPIRED_TICK_LEASE,
                    "CONTINUOUS_RUNTIME_TICK",
                    f"{run_id}/{tick_id}",
                    "IN_PROGRESS",
                    f"continuous-research resume --run-id {run_id}",
                    "LEASE_EXPIRED_RECLAIM_WITH_NEW_FENCE",
                )
            )
        for run_id, tick_id, status in retryable:
            issues.append(
                _issue(
                    RecoveryIssueKind.RETRYABLE_TICK,
                    "CONTINUOUS_RUNTIME_TICK",
                    f"{run_id}/{tick_id}",
                    str(status),
                    f"continuous-research resume --run-id {run_id}",
                    "POSTGRESQL_JOURNAL_RESUME_REQUIRED",
                )
            )
        for run_id, tick_id, status in provider_failures:
            issues.append(
                _issue(
                    RecoveryIssueKind.PROVIDER_FAILURE,
                    "CONTINUOUS_PROVIDER_ATTEMPT",
                    f"{run_id}/{tick_id}",
                    str(status),
                    f"continuous-research resume --run-id {run_id}",
                    "EXPLICIT_PROVIDER_RETRY_REQUIRED",
                )
            )
        for session_id, run_id, status, trading_date in research_partial:
            issue_kind = (
                RecoveryIssueKind.MISSED_SETTLEMENT
                if str(status) == "OUTCOME_PENDING"
                and trading_date < checked_at.date()
                else RecoveryIssueKind.PARTIAL_RESEARCH_SHADOW
            )
            issues.append(
                _issue(
                    issue_kind,
                    "RESEARCH_SHADOW_SESSION",
                    str(session_id),
                    str(status),
                    (
                        "continuous-research settle-day"
                        if issue_kind is RecoveryIssueKind.MISSED_SETTLEMENT
                        else f"continuous-research resume --run-id {run_id}"
                    ),
                    "POSTGRESQL_SHADOW_STATE_RESUME_REQUIRED",
                )
            )
        for session_id, run_id in panel_missing:
            issues.append(
                _issue(
                    RecoveryIssueKind.EVALUATION_PANEL_MISSING,
                    "RESEARCH_SHADOW_SESSION",
                    str(session_id),
                    "SETTLED_WITHOUT_PANEL",
                    f"continuous-research replay --run-id {run_id}",
                    "EVALUATION_REBUILD_FROM_OWNER_ARTIFACTS_REQUIRED",
                )
            )
        for session_id, status in strategy_partial:
            issues.append(
                _issue(
                    RecoveryIssueKind.PARTIAL_STRATEGY_SHADOW,
                    "STRATEGY_SHADOW_SESSION",
                    str(session_id),
                    str(status),
                    f"continuous-research strategy-replay --session-id {session_id}",
                    "STRATEGY_SHADOW_RESUME_FROM_EVENT_JOURNAL",
                )
            )
        verified_portfolios = 0
        for row in portfolio_rows:
            portfolio_id = ArtifactId(str(row[0]))
            try:
                self._portfolios.replay(portfolio_id)
                verified_portfolios += 1
            except (KeyError, ValueError):
                issues.append(
                    _issue(
                        RecoveryIssueKind.PORTFOLIO_REPLAY_FAILED,
                        "STRATEGY_SHADOW_PORTFOLIO",
                        str(portfolio_id),
                        "REPLAY_FAILED",
                        f"continuous-research portfolio-shadow-replay --portfolio-id {portfolio_id}",
                        "PORTFOLIO_CAS_CHAIN_REQUIRES_OPERATOR_REVIEW",
                    )
                )
        return RecoveryAuditReport(
            checked_at=checked_at,
            checked_through_date=checked_at.date(),
            issues=tuple(
                sorted(
                    issues,
                    key=lambda item: (
                        item.issue_kind.value,
                        item.authority_kind,
                        item.authority_id,
                    ),
                )
            ),
            portfolio_replay_verified_count=verified_portfolios,
        )


def _issue(
    issue_kind: RecoveryIssueKind,
    authority_kind: str,
    authority_id: str,
    status: str,
    recovery_command: str,
    reason: str,
) -> RecoveryIssue:
    return RecoveryIssue(
        issue_kind,
        authority_kind,
        authority_id,
        status,
        recovery_command,
        (reason,),
    )


__all__ = ["PostgresRecoveryAudit", "RecoveryAuditReport", "RecoveryIssue"]
