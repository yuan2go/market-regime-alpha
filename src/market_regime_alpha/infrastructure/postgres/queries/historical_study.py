"""Exact read-only preparation of existing canonical study dependencies."""

from typing import Any

from psycopg.rows import dict_row

from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from market_regime_alpha.infrastructure.postgres.queries.decision_inference_inputs import _load_strategy
from market_regime_alpha.research_qualification.domain.historical_study import HistoricalStudyPlan
from market_regime_alpha.research_qualification.domain.historical_matrix import HistoricalTimeSplit
from market_regime_alpha.runtime.errors import ArtifactIntegrityError


def read_study_dependencies(pool: TargetPostgresPool, plan: HistoricalStudyPlan, additional_splits: tuple[HistoricalTimeSplit, ...] = (), step_sessions: int | None = None) -> dict[str, Any]:
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
            windows = (HistoricalTimeSplit(plan.fit_dates,plan.purge_dates,plan.embargo_dates,plan.validation_dates),*additional_splits)
            expected_windows = tuple(p.fit_dates+p.purge_dates+p.embargo_dates+p.validation_dates for p in windows)
            dates = tuple(sorted({day for window in expected_windows for day in window}))
            sessions = cursor.execute("""SELECT session_id,session_date,open_at,close_at,known_at
                FROM mra.trading_session WHERE exchange=%s AND session_date BETWEEN %s AND %s
                ORDER BY session_date""", (archive["exchange_code"], dates[0], dates[-1])).fetchall()
            for window in expected_windows:
                if tuple(r["session_date"] for r in sessions if window[0]<=r["session_date"]<=window[-1]) != window:
                    actual = tuple(r["session_date"] for r in sessions if window[0]<=r["session_date"]<=window[-1])
                    raise ValueError(f"each study split must cover every real Calendar session in its interval: exchange={archive['exchange_code']}, expected={window}, actual={actual}")
            if additional_splits:
                index={r["session_date"]:i for i,r in enumerate(sessions)}
                if step_sessions is None or any(index[current.fit_dates[0]]-index[previous.fit_dates[0]]!=step_sessions
                    for previous,current in zip(windows,windows[1:])):
                    raise ValueError("rolling stride must match actual archived Calendar session positions")
            if any(r["known_at"] > seal["knowledge_cutoff"] for r in sessions):
                raise ArtifactIntegrityError("study Calendar exceeds the frozen Archive knowledge cutoff")
            next_session = cursor.execute("""SELECT session_id,session_date,known_at FROM mra.trading_session
                WHERE exchange=%s AND session_date>%s ORDER BY session_date LIMIT 1""", (archive["exchange_code"], dates[-1])).fetchone()
            if next_session is None or next_session["known_at"] > seal["knowledge_cutoff"]:
                raise ValueError("study Calendar must cover the final next-session label")
        strategy = _load_strategy(connection, root["strategy_version_id"], lock=False)
    return {"template": root, "archive": archive, "seal": seal, "sessions": sessions, "target_coverage": next_session, "strategy": strategy}
