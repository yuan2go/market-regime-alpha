"""Exact read-only preparation of existing canonical study dependencies."""

from typing import Any

from psycopg.rows import dict_row

from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from market_regime_alpha.infrastructure.postgres.queries.decision_inference_inputs import _load_strategy
from market_regime_alpha.research_qualification.domain.historical_study import HistoricalStudyPlan
from market_regime_alpha.research_qualification.domain.historical_matrix import HistoricalTimeSplit
from market_regime_alpha.runtime.errors import ArtifactIntegrityError


_ARCHIVE_CALENDAR_BINDING = """EXISTS (
    SELECT 1 FROM mra.market_capture_trading_session_normalization binding
    JOIN mra.market_archive_capture_observation observation USING(capture_id)
    JOIN mra.data_capture capture USING(capture_id)
    WHERE binding.session_id=session.session_id AND observation.market_archive_id=%s
      AND observation.known_at<=%s AND capture.recorded_at<=%s
      AND capture.status='CAPTURED'
)"""


def read_study_dependencies(pool: TargetPostgresPool, plan: HistoricalStudyPlan, additional_splits: tuple[HistoricalTimeSplit, ...] = (), step_sessions: int | None = None, *, stride_anchor: str = "FIT_START") -> dict[str, Any]:
    if stride_anchor not in {"FIT_START", "VALIDATION_START"}:
        raise ValueError("unknown Calendar stride anchor")
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
            calendar_scope = (plan.market_archive_id, seal["knowledge_cutoff"], seal["knowledge_cutoff"])
            sessions = cursor.execute("SELECT session_id,session_date,open_at,close_at,known_at," + _ARCHIVE_CALENDAR_BINDING + """ AS archive_bound
                FROM mra.trading_session session WHERE exchange=%s AND session_date BETWEEN %s AND %s
                ORDER BY session_date""", (*calendar_scope, archive["exchange_code"], dates[0], dates[-1])).fetchall()
            if any(not row.pop("archive_bound") for row in sessions):
                raise ValueError("study Calendar lacks selected Archive Capture/normalization bindings")
            for window in expected_windows:
                if tuple(r["session_date"] for r in sessions if window[0]<=r["session_date"]<=window[-1]) != window:
                    actual = tuple(r["session_date"] for r in sessions if window[0]<=r["session_date"]<=window[-1])
                    raise ValueError(f"each study split must cover every real Calendar session in its interval: exchange={archive['exchange_code']}, expected={window}, actual={actual}")
            if additional_splits:
                index={r["session_date"]:i for i,r in enumerate(sessions)}
                def anchor(window):
                    return window.fit_dates[0] if stride_anchor == "FIT_START" else window.validation_dates[0]
                if step_sessions is None or any(index[anchor(current)]-index[anchor(previous)]!=step_sessions
                    for previous,current in zip(windows,windows[1:])):
                    raise ValueError("rolling stride must match actual archived Calendar session positions")
            if any(r["known_at"] > seal["knowledge_cutoff"] for r in sessions):
                raise ArtifactIntegrityError("study Calendar exceeds the frozen Archive knowledge cutoff")
            # Inspect the actual immediate successor before checking provenance;
            # filtering first could silently skip an unbound/missing label day.
            next_session = cursor.execute("SELECT session_id,session_date,known_at," + _ARCHIVE_CALENDAR_BINDING + """ AS archive_bound FROM mra.trading_session session
                WHERE exchange=%s AND session_date>%s ORDER BY session_date LIMIT 1""", (*calendar_scope, archive["exchange_code"], dates[-1])).fetchone()
            if next_session is None or not next_session.pop("archive_bound") or next_session["known_at"] > seal["knowledge_cutoff"]:
                raise ValueError("study Calendar must cover the final next-session label")
            # Canonical validation Partitions extend past the label horizon by
            # their declared embargo. Validate that source here, before any
            # frozen file or owner declaration, not at the last Evaluation.
            following = cursor.execute("SELECT session_id,session_date,known_at," + _ARCHIVE_CALENDAR_BINDING + """ AS archive_bound FROM mra.trading_session session
                WHERE exchange=%s AND session_date>%s ORDER BY session_date LIMIT %s""",
                (*calendar_scope,archive["exchange_code"],dates[-1],1+max(len(w.embargo_dates) for w in windows))).fetchall()
            full_calendar = [*sessions,*following]
            positions = {row["session_date"]:i for i,row in enumerate(full_calendar)}
            ends = tuple(positions[w.validation_dates[-1]]+1+len(w.embargo_dates) for w in windows)
            required_end = max(ends)
            if required_end >= len(full_calendar) or any(not row["archive_bound"] or row["known_at"]>seal["knowledge_cutoff"]
                    for row in full_calendar[len(sessions):required_end+1]):
                raise ValueError("study Calendar must cover the exact label horizon and Partition embargo")
            partition_coverage = tuple({"validation_end":w.validation_dates[-1],"protected_end":full_calendar[end]["session_date"]}
                for w,end in zip(windows,ends,strict=True))
        strategy = _load_strategy(connection, root["strategy_version_id"], lock=False)
    return {"template": root, "archive": archive, "seal": seal, "sessions": sessions, "target_coverage": next_session, "strategy": strategy,
        "partition_coverage":partition_coverage}
