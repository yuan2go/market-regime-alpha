"""Exact read-only preparation of existing canonical study dependencies."""

from typing import Any

from psycopg.rows import dict_row

from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from market_regime_alpha.infrastructure.postgres.queries.decision_inference_inputs import _load_strategy
from market_regime_alpha.research_qualification.domain.historical_study import HistoricalStudyPlan
from market_regime_alpha.runtime.errors import ArtifactIntegrityError


def read_study_dependencies(pool: TargetPostgresPool, plan: HistoricalStudyPlan) -> dict[str, Any]:
    with pool.connection(read_only=True) as connection:
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        with connection.cursor(row_factory=dict_row) as cursor:
            root = cursor.execute("SELECT * FROM mra.exploratory_backtest_run WHERE exploratory_backtest_run_id=%s", (plan.template_backtest_id,)).fetchone()
            archive = cursor.execute("SELECT * FROM mra.market_archive WHERE market_archive_id=%s", (plan.market_archive_id,)).fetchone()
            seal = cursor.execute("SELECT * FROM mra.market_archive_seal WHERE market_archive_seal_id=%s AND market_archive_id=%s", (plan.market_archive_seal_id, plan.market_archive_id)).fetchone()
            if (root is None or archive is None or seal is None
                    or root["definition_sha256"] != plan.template_definition_sha256
                    or archive["content_sha256"] != plan.market_archive_sha256
                    or seal["content_sha256"] != plan.market_archive_seal_sha256
                    or archive["lane"] != "RETROSPECTIVE_BACKFILL"):
                raise ArtifactIntegrityError("HISTORICAL_STUDY_DEPENDENCY_IDENTITY_MISMATCH")
            dates = plan.fit_dates + plan.purge_dates + plan.embargo_dates + plan.validation_dates
            sessions = cursor.execute("""SELECT session_id,session_date,open_at,close_at,known_at
                FROM mra.trading_session WHERE exchange=%s AND session_date BETWEEN %s AND %s
                ORDER BY session_date""", (archive["exchange_code"], dates[0], dates[-1])).fetchall()
            if tuple(r["session_date"] for r in sessions) != dates:
                raise ValueError("study session roster must cover every real Calendar session in its interval")
            if any(r["known_at"] > seal["knowledge_cutoff"] for r in sessions):
                raise ArtifactIntegrityError("study Calendar exceeds the frozen Archive knowledge cutoff")
            next_session = cursor.execute("""SELECT session_id,session_date,known_at FROM mra.trading_session
                WHERE exchange=%s AND session_date>%s ORDER BY session_date LIMIT 1""", (archive["exchange_code"], dates[-1])).fetchone()
            if next_session is None or next_session["known_at"] > seal["knowledge_cutoff"]:
                raise ValueError("study Calendar must cover the final next-session label")
        strategy = _load_strategy(connection, root["strategy_version_id"], lock=False)
    return {"template": root, "archive": archive, "seal": seal, "sessions": sessions, "target_coverage": next_session, "strategy": strategy}
