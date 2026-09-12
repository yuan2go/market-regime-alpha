"""Transaction-bound exploratory Backtest holdout reservation and opening."""

from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

import psycopg

from market_regime_alpha.research_qualification.domain.backtest_holdout import BacktestHoldoutOpening, BacktestHoldoutReservation
from market_regime_alpha.runtime.errors import ArtifactIntegrityError, RuntimeNotFoundError, RuntimeStateConflictError
from market_regime_alpha.shared.hashing import canonical_json_sha256


def evaluation_roster(connection: psycopg.Connection[Any], run_id: UUID) -> tuple[tuple[str, str, str, str], ...]:
    rows = connection.execute("""
        SELECT evaluation.evaluation_run_id,evaluation.content_sha256,
               evaluation.input_roster_sha256,evaluation.metric_roster_sha256,evaluation.status
        FROM mra.backtest_evaluation_requirement requirement
        LEFT JOIN mra.backtest_evaluation_execution execution USING(backtest_evaluation_requirement_id)
        LEFT JOIN mra.evaluation_run evaluation USING(evaluation_run_id)
        WHERE requirement.exploratory_backtest_run_id=%s ORDER BY requirement.ordinal
        """, (run_id,)).fetchall()
    if not rows or any(row[4] != "COMPLETED" or any(value is None for value in row[:4]) for row in rows):
        raise RuntimeStateConflictError("holdout selection requires every development Evaluation completed")
    return tuple((str(row[0]), str(row[1]), str(row[2]), str(row[3])) for row in rows)


class PostgresBacktestHoldoutRepository:
    def __init__(self, connection: psycopg.Connection[Any]) -> None:
        self._connection = connection

    def record(self, reservation_id: UUID, *, opening: bool) -> dict[str, Any]:
        table = "backtest_holdout_opening" if opening else "backtest_holdout_reservation"
        # Only these two owner constants enter the SQL identifier.
        row = self._connection.execute(
            f"SELECT mra.{table}_payload(fact),content_sha256,{'opened_at' if opening else 'reserved_at'} FROM mra.{table} fact WHERE reservation_id=%s",
            (reservation_id,),
        ).fetchone()
        if row is None:
            raise RuntimeNotFoundError("Backtest holdout fact does not exist")
        if canonical_json_sha256(row[0]) != row[1]:
            raise ArtifactIntegrityError("Backtest holdout content differs from its exact identity")
        return {"body": row[0], "content_sha256": row[1], "recorded_at": row[2]}

    def reserve(self, request: BacktestHoldoutReservation) -> dict[str, Any]:
        c = self._connection
        c.execute("SELECT pg_advisory_xact_lock(hashtextextended('mra:backtest-holdout-admission',0))")
        root = c.execute("""
            SELECT specification.specification_sha256,specification.exchange_code,seal.knowledge_cutoff,
                   (SELECT max(session_date) FROM mra.exploratory_backtest_fold_session
                    WHERE exploratory_backtest_run_id=root.exploratory_backtest_run_id)
            FROM mra.exploratory_backtest_run root
            JOIN mra.backtest_specification specification USING(exploratory_backtest_run_id)
            JOIN mra.market_archive_seal seal USING(market_archive_seal_id)
            WHERE root.exploratory_backtest_run_id=%s FOR SHARE OF specification
            """, (request.development_run_id,)).fetchone()
        if root is None or root[0] != request.development_specification_sha256:
            raise ArtifactIntegrityError("holdout development specification differs")
        split = request.time_split
        dates = split.fit_dates + split.purge_dates + split.embargo_dates + split.validation_dates
        calendar = c.execute("""
            SELECT session_date,close_at,known_at FROM mra.trading_session
            WHERE exchange=%s AND session_date BETWEEN %s AND %s ORDER BY session_date
            """, (root[1], dates[0], dates[-1])).fetchall()
        after = c.execute("""
            SELECT close_at,known_at FROM mra.trading_session
            WHERE exchange=%s AND session_date>%s ORDER BY session_date LIMIT 1
            """, (root[1], dates[-1])).fetchone()
        if (tuple(row[0] for row in calendar) != dates or root[3] >= dates[0] or after is None
                or after[1] > root[2] or any(row[2] > root[2] for row in calendar)):
            raise RuntimeStateConflictError("holdout must follow development on the complete original Calendar with mature label coverage")
        arms = c.execute("""
            SELECT arm.arm_kind FROM mra.exploratory_backtest_arm arm
            JOIN mra.backtest_arm_specification specification USING(exploratory_backtest_arm_id)
            WHERE arm.exploratory_backtest_run_id=%s AND specification.execution_kind='MODEL'
            ORDER BY arm.ordinal
            """, (request.development_run_id,)).fetchall()
        actual = tuple(row[0] for row in arms if row[0] in request.selection_arm_codes)
        if actual != request.selection_arm_codes:
            raise RuntimeStateConflictError("holdout selection candidates differ from frozen development arm order")
        instruments = tuple(row[0] for row in c.execute(
            "SELECT instrument_id FROM mra.backtest_sample_member WHERE exploratory_backtest_run_id=%s ORDER BY instrument_id",
            (request.development_run_id,),
        ).fetchall())
        protected_start = next(row[1] for row in calendar if row[0] == split.validation_dates[0])
        c.execute("""
            INSERT INTO mra.backtest_holdout_reservation(reservation_id,development_run_id,development_specification_sha256,
                future_run_id,future_study_code,fit_dates,purge_dates,embargo_dates,validation_dates,selection_arm_codes,
                protocol_artifact_id,protocol_content_sha256,protocol_size_bytes,instrument_ids,protected_start,protected_end,content_sha256)
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (request.reservation_id, request.development_run_id, request.development_specification_sha256,
                request.future_run_id, request.future_study_code, list(split.fit_dates), list(split.purge_dates), list(split.embargo_dates),
                list(split.validation_dates), list(request.selection_arm_codes), request.protocol_artifact.artifact_id,
                str(request.protocol_artifact.content_sha256), request.protocol_artifact.size_bytes, list(instruments),
                protected_start, after[0], request.content_sha256))
        return self.record(request.reservation_id, opening=False)

    def open(self, request: BacktestHoldoutOpening) -> dict[str, Any]:
        c = self._connection
        c.execute("SELECT pg_advisory_xact_lock(hashtextextended('mra:backtest-holdout-admission',0))")
        record = self.record(request.reservation_id, opening=False)
        reservation = BacktestHoldoutReservation.from_payload(record["body"])
        if record["content_sha256"] != request.reservation_sha256 or reservation.future_run_id != request.heldout_run_id:
            raise ArtifactIntegrityError("holdout opening changed the original reservation identity")
        if evaluation_roster(c, reservation.development_run_id) != request.development_evaluation_roster:
            raise ArtifactIntegrityError("holdout selection Evaluation roster changed before commit")
        exact = c.execute("""
            SELECT 1 FROM mra.backtest_specification WHERE exploratory_backtest_run_id=%s
                AND specification_sha256=%s FOR SHARE
            """, (request.heldout_run_id, request.heldout_specification_sha256)).fetchone()
        if exact is None:
            raise ArtifactIntegrityError("holdout execution specification changed before opening")
        rows = c.execute("""SELECT root.definition_sha256,requirement.scope_kind,requirement.exploratory_backtest_arm_id,
            requirement.exploratory_backtest_fold_id,requirement.backtest_evaluation_requirement_id
            FROM mra.backtest_evaluation_requirement requirement
            JOIN mra.exploratory_backtest_run root USING(exploratory_backtest_run_id)
            LEFT JOIN mra.exploratory_backtest_fold fold USING(exploratory_backtest_fold_id)
            WHERE requirement.exploratory_backtest_run_id=%s AND (requirement.scope_kind='AGGREGATE' OR fold.purpose='VALIDATION')""",
            (request.heldout_run_id,)).fetchall()
        scopes = []
        for digest, kind, arm_id, fold_id, requirement_id in rows:
            action = uuid5(NAMESPACE_URL, ':'.join(('mra','backtest-action',str(request.heldout_run_id),digest,
                'COMPLETE_AGGREGATE_EVALUATION' if kind=='AGGREGATE' else 'COMPLETE_FOLD_EVALUATION',
                str(arm_id),'-' if fold_id is None else str(fold_id),'-',str(requirement_id))))
            scopes.append((uuid5(action,'evaluation-run'),uuid5(action,'research-partition'),uuid5(action,'experiment-run'),requirement_id))
        if tuple(sorted(scopes,key=lambda row:str(row[0]))) != request.evaluation_scopes:
            raise ArtifactIntegrityError("holdout exact Evaluation/Partition/Experiment identities differ from frozen requirements at commit")
        c.execute("""
            INSERT INTO mra.backtest_holdout_opening(reservation_id,reservation_sha256,heldout_run_id,heldout_specification_sha256,
                selected_development_arm_id,selected_arm_code,development_projection_sha256,
                selection_artifact_id,selection_content_sha256,selection_size_bytes,allowed_evaluation_ids,
                allowed_partition_ids,allowed_experiment_run_ids,allowed_requirement_ids,
                development_evaluation_ids,development_evaluation_plan_hashes,development_evaluation_input_hashes,
                development_evaluation_metric_hashes,content_sha256)
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (request.reservation_id, request.reservation_sha256, request.heldout_run_id, request.heldout_specification_sha256,
                request.selected_development_arm_id, request.selected_arm_code, request.development_projection_sha256,
                request.selection_artifact.artifact_id, str(request.selection_artifact.content_sha256), request.selection_artifact.size_bytes,
                list(request.allowed_evaluation_ids),*[list(row[i] for row in request.evaluation_scopes) for i in (1,2,3)],
                [UUID(row[0]) for row in request.development_evaluation_roster],
                [row[1] for row in request.development_evaluation_roster], [row[2] for row in request.development_evaluation_roster],
                [row[3] for row in request.development_evaluation_roster], request.content_sha256))
        return self.record(request.reservation_id, opening=True)
