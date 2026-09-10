"""Read-only daily composition queries; canonical owners retain all writes."""

from dataclasses import fields
from hashlib import sha256
from datetime import datetime
import json
from typing import Any
from uuid import UUID, uuid4, uuid5

from psycopg.rows import dict_row

from market_regime_alpha.decision_support.domain import ForecastModelBindingPlan, ModelPredictionState
from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from market_regime_alpha.infrastructure.postgres.queries.daily_feature_inputs import PostgresDailyFeatureInputReadPort
from market_regime_alpha.infrastructure.postgres.queries.daily_validity import PostgresDailyValidityReads
from market_regime_alpha.infrastructure.postgres.repositories.decision_inference import PostgresInferenceRepository
from market_regime_alpha.infrastructure.postgres.repositories.target_definitions import PostgresTargetDefinitionRepository
from market_regime_alpha.infrastructure.postgres.repositories.research_models import PostgresResearchModelRepository
from market_regime_alpha.infrastructure.postgres.repositories.research_partitions import PostgresResearchPartitionRepository
from market_regime_alpha.research_qualification.domain.model import ArtifactBinding
from market_regime_alpha.research_qualification.domain.targets import TargetDefinition
from market_regime_alpha.research_qualification.domain.daily_inputs import DailyDataReady, freeze_data_ready
from market_regime_alpha.research_qualification.domain.daily_prediction import DailyPopulationMember, DailyPredictionPlan
from market_regime_alpha.research_qualification.ports.daily_prediction import (
    DailyOutcomeWorkItem,
)
from market_regime_alpha.research_qualification.ports.artifacts import ResearchArtifactByteStore
from market_regime_alpha.runtime.errors import (
    ArtifactByteStoreError,
    ArtifactIntegrityError,
    RuntimeStateConflictError,
)


class PostgresDailyPredictionReads:
    def __init__(self, pool: TargetPostgresPool, byte_store: ResearchArtifactByteStore) -> None:
        self._pool = pool
        self._byte_store = byte_store
        self._inputs = PostgresDailyFeatureInputReadPort(pool, byte_store)

    def published_report(self, plan: DailyPredictionPlan, key: str, expected: bytes) -> ArtifactBinding:
        with self._pool.connection(read_only=True) as connection:
            row = connection.execute(
                """SELECT artifact.artifact_id,artifact.content_sha256,artifact.size_bytes
                FROM mra.command_receipt receipt JOIN mra.artifact artifact ON artifact.artifact_id::text=receipt.result_aggregate_id
                WHERE receipt.command_kind='REGISTER_ARTIFACT' AND receipt.status='SUCCEEDED' AND receipt.idempotency_key=%s""",
                ("daily:" + str(plan.prediction_id) + ":" + key,),
            ).fetchone()
        if row is None or row[1] != sha256(expected).hexdigest() or row[2] != len(expected):
            raise ArtifactIntegrityError("daily report identity/complete projection differs")
        if self._byte_store.read_bytes(row[1], expected_size=row[2]) != expected:
            raise ArtifactIntegrityError("daily report bytes differ")
        return ArtifactBinding(*row)

    def published_artifact(
        self, idempotency_key: str
    ) -> tuple[ArtifactBinding, bytes] | None:
        with self._pool.connection(read_only=True) as connection:
            rows = connection.execute(
                """
                SELECT artifact.artifact_id, artifact.content_sha256,
                       artifact.size_bytes
                FROM mra.command_receipt AS receipt
                JOIN mra.artifact AS artifact
                  ON artifact.artifact_id::text = receipt.result_aggregate_id
                WHERE receipt.command_kind = 'REGISTER_ARTIFACT'
                  AND receipt.status = 'SUCCEEDED'
                  AND receipt.idempotency_key = %s
                """,
                (idempotency_key,),
            ).fetchall()
        if not rows:
            return None
        if len(rows) != 1:
            raise ArtifactIntegrityError(
                "artifact idempotency key resolves to multiple published identities"
            )
        row = rows[0]
        binding = ArtifactBinding(*row)
        content = self._byte_store.read_bytes(row[1], expected_size=row[2])
        if sha256(content).hexdigest() != row[1]:
            raise ArtifactIntegrityError("published Artifact bytes differ")
        return binding, content

    def research_dispositions(
        self, prediction_id: UUID
    ) -> tuple[dict[str, Any], ...]:
        prefix = "daily:" + str(prediction_id) + ":research-disposition:"
        with self._pool.connection(read_only=True) as connection:
            rows = connection.execute(
                """
                SELECT receipt.idempotency_key, artifact.artifact_id,
                       artifact.content_sha256, artifact.size_bytes
                FROM mra.command_receipt AS receipt
                JOIN mra.artifact AS artifact
                  ON artifact.artifact_id::text = receipt.result_aggregate_id
                WHERE receipt.command_kind = 'REGISTER_ARTIFACT'
                  AND receipt.status = 'SUCCEEDED'
                  AND receipt.idempotency_key LIKE %s
                ORDER BY receipt.created_at, receipt.receipt_id
                """,
                (prefix + "%",),
            ).fetchall()
        result: list[dict[str, Any]] = []
        for key, artifact_id, content_sha256, size_bytes in rows:
            content = self._byte_store.read_bytes(
                content_sha256, expected_size=size_bytes
            )
            value = json.loads(content)
            if (
                not isinstance(value, dict)
                or value.get("schema") != "daily-research-disposition-v1"
                or value.get("prediction_id") != str(prediction_id)
                or key
                != prefix + str(value.get("review_id"))
                or sha256(content).hexdigest() != content_sha256
            ):
                raise ArtifactIntegrityError(
                    "daily research disposition identity differs"
                )
            value["artifact"] = ArtifactBinding(
                artifact_id, content_sha256, size_bytes
            )
            result.append(value)
        return tuple(result)

    def now(self) -> datetime:
        with self._pool.connection(read_only=True) as connection:
            row = connection.execute("SELECT clock_timestamp()").fetchone()
        assert row is not None
        return row[0]

    def operational_ledger_rows(self, *, complete_history: bool = False) -> dict[str, Any]:
        """Bounded operational read by default; explicit research export keeps history."""
        if type(complete_history) is not bool:
            raise TypeError("complete_history must be boolean")
        with self._pool.connection(read_only=True) as connection:
            connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            with connection.cursor(row_factory=dict_row) as cursor:
                now = cursor.execute("SELECT clock_timestamp() AS observed_at").fetchone()
                assert now is not None
                runs = cursor.execute("""
                    SELECT r.*,s.schedule_code,a.content_sha256,a.size_bytes
                    FROM mra.runtime_run r JOIN mra.runtime_schedule s USING(schedule_id)
                    LEFT JOIN mra.artifact a ON a.artifact_id=r.config_artifact_id
                    WHERE s.schedule_code ~ '^daily-(model|outcome|abstention)-[0-9a-f]{32}$'
                      AND r.runtime_mode='SHADOW' AND s.runtime_mode='SHADOW'
                    ORDER BY r.requested_at,r.run_id
                """ + ("" if complete_history else " LIMIT 513")).fetchall()
                if not complete_history and len(runs)>512:
                    raise ValueError("daily health ledger exceeds explicit row budget")
                steps = cursor.execute("SELECT * FROM mra.runtime_step WHERE run_id=ANY(%s::uuid[]) ORDER BY run_id,ordinal", ([r['run_id'] for r in runs],)).fetchall()
                attempts = cursor.execute("SELECT * FROM mra.runtime_attempt WHERE step_id=ANY(%s::uuid[]) ORDER BY step_id,attempt_no", ([s['step_id'] for s in steps],)).fetchall()
                sessions = cursor.execute("""SELECT session_id,session_date,open_at,close_at FROM mra.trading_session
                    WHERE exchange='XSHG' ORDER BY open_at DESC"""
                    + ("" if complete_history else " LIMIT 10000")).fetchall()
                if not complete_history and len(sessions)==10000:
                    raise ValueError("daily health calendar exceeds explicit row budget")
                freshness = cursor.execute("""
                    SELECT max(recorded_at) FILTER(WHERE capture_key LIKE 'daily-input:%%') AS input_capture,
                           max(recorded_at) FILTER(WHERE capture_key LIKE 'daily-population:%%') AS population_capture
                    FROM mra.data_capture WHERE status='CAPTURED'
                """).fetchone()
                artifact = cursor.execute("SELECT max(last_verified_at) AS last_verified_at FROM mra.artifact").fetchone()
        for run in runs:
            run['plan_content'] = None
            if run['config_hash'] != run['content_sha256'] or run['size_bytes'] is None:
                run['plan_error'] = 'FROZEN_PLAN_IDENTITY_MISMATCH'
                continue
            try:
                run['plan_content'] = self._byte_store.read_bytes(run['content_sha256'],expected_size=run['size_bytes'])
            except (OSError, ValueError, ArtifactByteStoreError, ArtifactIntegrityError):
                run['plan_error'] = 'FROZEN_PLAN_BYTES_UNREADABLE'
        return {**now, 'runs': runs,'steps': steps,'attempts': attempts,'sessions': sessions,
                'freshness': freshness,'artifact_verification': artifact}

    def operational_health(self, plan: DailyPredictionPlan) -> dict[str, Any]:
        """Bounded facts for publication, backlog, calendar, model, and freshness."""

        work = self.outcome_work_items(limit=256)
        target_ids: dict[UUID, UUID] = {}
        plan_decode_failures = 0
        for item in work:
            if item.plan_content is None:
                plan_decode_failures += 1
                continue
            try:
                root = json.loads(item.plan_content)
                target_ids[item.run_id] = UUID(root["plan"]["target_session_id"])
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                plan_decode_failures += 1
        with self._pool.connection(read_only=True) as connection:
            observed = connection.execute("SELECT clock_timestamp()").fetchone()
            assert observed is not None
            observed_at = observed[0]
            use = PostgresResearchModelRepository(connection).experimental_use(
                plan.experimental_model_use_id, lock=False
            )
            publication = connection.execute(
                """
                SELECT max(forecast.recorded_at)
                FROM mra.forecast_model_binding AS binding
                JOIN mra.forecast_run AS forecast
                  ON forecast.forecast_group_id = binding.forecast_group_id
                JOIN mra.decision_run AS decision
                  ON decision.decision_run_id = forecast.decision_run_id
                JOIN mra.runtime_run AS run
                  ON run.run_id = decision.runtime_run_id
                JOIN mra.runtime_schedule AS schedule USING (schedule_id)
                WHERE schedule.schedule_code ~ '^daily-model-[0-9a-f]{32}$'
                  AND schedule.runtime_mode = 'SHADOW'
                  AND run.runtime_mode = 'SHADOW'
                """
            ).fetchone()
            report = connection.execute(
                """
                SELECT max(attempt.finished_at)
                FROM mra.runtime_run AS run
                JOIN mra.runtime_schedule AS schedule USING (schedule_id)
                JOIN mra.runtime_step AS step USING (run_id)
                JOIN mra.runtime_attempt AS attempt USING (step_id)
                WHERE schedule.schedule_code ~ '^daily-model-[0-9a-f]{32}$'
                  AND schedule.runtime_mode = 'SHADOW'
                  AND run.runtime_mode = 'SHADOW'
                  AND step.step_key = 'report'
                  AND attempt.state = 'SUCCEEDED'
                """
            ).fetchone()
            calendar = connection.execute(
                """
                SELECT count(*) FILTER (WHERE session.open_at > %s),
                       max(session.session_date) FILTER (WHERE session.open_at > %s)
                FROM mra.trading_session AS session
                WHERE session.exchange = 'XSHG'
                  AND EXISTS (
                    SELECT 1
                    FROM mra.market_capture_trading_session_normalization AS binding
                    JOIN mra.data_capture AS capture USING (capture_id)
                    WHERE binding.session_id = session.session_id
                      AND capture.status = 'CAPTURED'
                  )
                """,
                (observed_at, observed_at),
            ).fetchone()
            freshness = connection.execute(
                """
                SELECT
                  (SELECT max(recorded_at) FROM mra.data_capture
                   WHERE provider_product_id = %s),
                  (SELECT max(recorded_at) FROM mra.market_bar_revision
                   WHERE provider_product_id = %s
                     AND instrument_id = ANY(%s::uuid[])
                     AND session_id = ANY(%s::uuid[])),
                  (SELECT max(recorded_at) FROM mra.source_gap
                   WHERE provider_product_id = %s)
                """,
                (
                    plan.provider_product_id,
                    plan.provider_product_id,
                    list(plan.instrument_ids),
                    [plan.input_session_id, plan.target_session_id],
                    plan.provider_product_id,
                ),
            ).fetchone()
            delivery = connection.execute(
                """
                SELECT
                  max(attempt.finished_at) FILTER (
                    WHERE attempt.state = 'SUCCEEDED'
                  ),
                  count(DISTINCT run.run_id) FILTER (
                    WHERE run.state IN ('QUEUED', 'RUNNING')
                  ),
                  count(DISTINCT run.run_id) FILTER (
                    WHERE run.state = 'WAITING'
                  ),
                  count(DISTINCT run.run_id) FILTER (
                    WHERE run.state = 'FAILED'
                  ),
                  count(DISTINCT run.run_id) FILTER (
                    WHERE run.state = 'SUCCEEDED'
                  )
                FROM mra.runtime_run AS run
                JOIN mra.runtime_schedule AS schedule USING (schedule_id)
                LEFT JOIN mra.runtime_step AS step USING (run_id)
                LEFT JOIN mra.runtime_attempt AS attempt USING (step_id)
                WHERE schedule.schedule_code
                      ~ '^daily-delivery-[0-9a-f]{32}-[a-z][a-z0-9_-]{0,31}$'
                  AND schedule.runtime_mode = 'SHADOW'
                  AND run.runtime_mode = 'SHADOW'
                """
            ).fetchone()
            runtime = connection.execute(
                """
                SELECT
                  count(*) FILTER (
                    WHERE run.state IN ('QUEUED', 'RUNNING')
                  ),
                  count(*) FILTER (WHERE run.state = 'WAITING'),
                  count(*) FILTER (WHERE run.state = 'FAILED'),
                  count(*) FILTER (WHERE run.state = 'BLOCKED'),
                  count(*) FILTER (WHERE run.state = 'CANCELLED')
                FROM mra.runtime_run AS run
                JOIN mra.runtime_schedule AS schedule USING (schedule_id)
                WHERE schedule.schedule_code ~
                    '^daily-(model|outcome|abstention|input-collection|outcome-collection|population-collection|delivery)-'
                  AND schedule.runtime_mode = 'SHADOW'
                  AND run.runtime_mode = 'SHADOW'
                """
            ).fetchone()
            review = connection.execute(
                """
                SELECT
                  count(*) FILTER (WHERE NOT EXISTS (
                    SELECT 1
                    FROM mra.command_receipt AS receipt
                    WHERE receipt.command_kind = 'REGISTER_ARTIFACT'
                      AND receipt.status = 'SUCCEEDED'
                      AND receipt.idempotency_key LIKE
                          'daily:' || split_part(run.fire_key, ':', 2)
                          || ':research-disposition:%'
                  )),
                  count(*) FILTER (WHERE EXISTS (
                    SELECT 1
                    FROM mra.command_receipt AS receipt
                    WHERE receipt.command_kind = 'REGISTER_ARTIFACT'
                      AND receipt.status = 'SUCCEEDED'
                      AND receipt.idempotency_key LIKE
                          'daily:' || split_part(run.fire_key, ':', 2)
                          || ':research-disposition:%'
                  ))
                FROM mra.runtime_run AS run
                JOIN mra.runtime_schedule AS schedule USING (schedule_id)
                WHERE schedule.schedule_code ~ '^daily-outcome-[0-9a-f]{32}$'
                  AND run.fire_key ~ '^daily-outcome:[0-9a-f-]{36}$'
                  AND run.state = 'SUCCEEDED'
                """
            ).fetchone()
            session_rows = connection.execute(
                "SELECT session_id, close_at FROM mra.trading_session WHERE session_id=ANY(%s::uuid[])",
                (list(target_ids.values()),),
            ).fetchall() if target_ids else ()
        assert publication is not None
        assert report is not None
        assert calendar is not None
        assert freshness is not None
        assert delivery is not None
        assert runtime is not None
        assert review is not None
        close_by_id = {row[0]: row[1] for row in session_rows}
        active = [item for item in work if item.run_state in {"QUEUED", "RUNNING"}]
        known_active = [
            (item, close_by_id[target_ids[item.run_id]])
            for item in active
            if item.run_id in target_ids and target_ids[item.run_id] in close_by_id
        ]
        pending_maturity = sum(
            target_close > observed_at for _item, target_close in known_active
        )
        pending_settlement = sum(
            target_close <= observed_at for _item, target_close in known_active
        )
        plan_decode_failures += len(active) - len(known_active)
        future_calendar_count = int(calendar[0])
        return {
            "schema": "daily-research-operational-health-v1",
            "observed_at": observed_at,
            "last_successful_publication_at": publication[0],
            "last_successful_report_at": report[0],
            "outcome_backlog": {
                "observed_count": len(work),
                "pending_maturity_count": pending_maturity,
                "pending_settlement_count": pending_settlement,
                "waiting_count": sum(item.run_state == "WAITING" for item in work),
                "failed_count": sum(item.run_state == "FAILED" for item in work),
                "integrity_blocked_count": plan_decode_failures,
                "scan_limit": 256,
                "scan_truncated": len(work) == 256,
            },
            "calendar": {
                "future_captured_session_count": future_calendar_count,
                "last_future_captured_session_date": calendar[1],
                "state": (
                    "CALENDAR_COVERAGE_LOW"
                    if future_calendar_count < 3
                    else "CALENDAR_COVERAGE_AVAILABLE"
                ),
            },
            "model_use": {
                "experimental_model_use_id": use.plan.experimental_model_use_id,
                "model_version_id": use.plan.model_version_id,
                "expires_at": use.plan.expires_at,
                "revoked_at": use.revoked_at,
                "expires_in_seconds": int(
                    (use.plan.expires_at - observed_at).total_seconds()
                ),
                "state": (
                    "REVOKED"
                    if use.revoked_at is not None
                    else "EXPIRED"
                    if observed_at >= use.plan.expires_at
                    else "AVAILABLE"
                ),
            },
            "data_freshness": {
                "last_capture_recorded_at": freshness[0],
                "last_bar_recorded_at": freshness[1],
                "bar_scope": "FROZEN_PLAN_INSTRUMENTS_INPUT_AND_TARGET_SESSIONS",
                "last_source_gap_recorded_at": freshness[2],
                "capture_age_seconds": (
                    None
                    if freshness[0] is None
                    else int((observed_at - freshness[0]).total_seconds())
                ),
            },
            "delivery": {
                "last_acknowledged_at": delivery[0],
                "active_count": int(delivery[1]),
                "reconciliation_required_count": int(delivery[2]),
                "failed_count": int(delivery[3]),
                "delivered_count": int(delivery[4]),
            },
            "runtime": {
                "active_count": int(runtime[0]),
                "waiting_count": int(runtime[1]),
                "failed_count": int(runtime[2]),
                "blocked_count": int(runtime[3]),
                "cancelled_count": int(runtime[4]),
            },
            "human_research_disposition": {
                "pending_review_count": int(review[0]),
                "reviewed_count": int(review[1]),
                "automatic_model_change": False,
                "automatic_qualification_change": False,
            },
        }

    def first_attempt_at(self, step_id: UUID) -> datetime:
        with self._pool.connection(read_only=True) as connection:
            row = connection.execute(
                "SELECT created_at FROM mra.runtime_attempt WHERE step_id=%s ORDER BY attempt_no LIMIT 1", (step_id,)
            ).fetchone()
        if row is None:
            raise ArtifactIntegrityError("daily Runtime Step lacks its first Attempt clock")
        return row[0]

    def target_definition(self, plan: DailyPredictionPlan) -> TargetDefinition:
        with self._pool.connection(read_only=True) as connection:
            return PostgresTargetDefinitionRepository(connection).target_definition(plan.target_definition_id, lock=False)

    def partition_hash(self, partition_id: UUID) -> str:
        with self._pool.connection(read_only=True) as connection:
            repository = PostgresResearchPartitionRepository(connection, id_factory=uuid4)
            record = repository.record(partition_id, lock=False)
            if not repository.reconcile(partition_id, lock=False):
                raise ArtifactIntegrityError("daily Partition does not reconcile")
        return record.content_sha256

    def evaluation_projection(self, evaluation_id: UUID) -> dict[str, Any]:
        with self._pool.connection(read_only=True) as connection, connection.cursor(row_factory=dict_row) as cursor:
            root = cursor.execute("SELECT * FROM mra.evaluation_run WHERE evaluation_run_id=%s", (evaluation_id,)).fetchone()
            if root is None or root["status"] != "COMPLETED":
                raise ArtifactIntegrityError("daily Evaluation is not completed")
            metrics = cursor.execute(
                """
                SELECT metric.*, protocol.metric_code
                FROM mra.evaluation_metric AS metric
                JOIN mra.evaluation_protocol_metric AS protocol
                  USING (evaluation_protocol_metric_id)
                WHERE metric.evaluation_run_id = %s
                ORDER BY protocol.ordinal
                """,
                (evaluation_id,),
            ).fetchall()
        return {"evaluation": root, "metrics": metrics}

    def require_partition_roster(self, partition_id: UUID, commitments: tuple[UUID, ...]) -> None:
        self.partition_hash(partition_id)
        with self._pool.connection(read_only=True) as connection:
            rows = connection.execute(
                "SELECT commitment_id FROM mra.research_partition_member WHERE research_partition_id=%s ORDER BY commitment_id",
                (partition_id,),
            ).fetchall()
        if tuple(row[0] for row in rows) != tuple(sorted(commitments, key=str)):
            raise ArtifactIntegrityError("daily Evaluation partition differs from the exact published commitment roster")

    def evaluation_observations(self, evaluation_id: UUID) -> dict[str, Any]:
        """Project the acquired immutable Outcome revisions, never current bars."""
        with self._pool.connection(read_only=True) as connection, connection.cursor(row_factory=dict_row) as cursor:
            observations = cursor.execute("""
                SELECT observation.*, member.commitment_id, commitment.instrument_id
                FROM mra.evaluation_observation observation
                JOIN mra.research_partition_member member USING(research_partition_member_id)
                JOIN mra.decision_target_commitment commitment USING(commitment_id)
                WHERE observation.evaluation_run_id=%s ORDER BY member.commitment_id
            """, (evaluation_id,)).fetchall()
            labels = cursor.execute("""
                SELECT metric.*, member.commitment_id, definition.metric_code
                FROM mra.evaluation_observation observation
                JOIN mra.research_partition_member member USING(research_partition_member_id)
                JOIN mra.market_target_outcome_metric metric USING(market_target_outcome_revision_id)
                JOIN mra.target_metric_definition definition USING(target_metric_definition_id)
                WHERE observation.evaluation_run_id=%s
                ORDER BY member.commitment_id, definition.metric_code
            """, (evaluation_id,)).fetchall()
            outcomes = cursor.execute("""
                SELECT revision.*, outcome.commitment_id
                FROM mra.evaluation_observation observation
                JOIN mra.market_target_outcome_revision revision USING(market_target_outcome_revision_id)
                JOIN mra.market_target_outcome outcome USING(market_target_outcome_id)
                WHERE observation.evaluation_run_id=%s ORDER BY outcome.commitment_id
            """, (evaluation_id,)).fetchall()
            sources = cursor.execute("""
                SELECT source.* FROM mra.evaluation_observation observation
                JOIN mra.market_target_outcome_source source USING(market_target_outcome_revision_id)
                WHERE observation.evaluation_run_id=%s ORDER BY source.market_target_outcome_source_id
            """, (evaluation_id,)).fetchall()
        return {"observations": observations, "labels": labels, "outcomes": outcomes, "sources": sources}

    def validity_observation_facts(self, plan: DailyPredictionPlan, evaluation_id: UUID) -> dict[str, Any]:
        return PostgresDailyValidityReads(self._pool, self._byte_store).project(
            plan, evaluation_id, self.decision_run(plan)
        )

    def validity_calendar(self) -> list[dict[str, Any]]:
        return PostgresDailyValidityReads(self._pool, self._byte_store).calendar()

    def current_sessions(self) -> tuple[UUID, UUID, datetime]:
        with self._pool.connection(read_only=True) as connection:
            row = connection.execute("""WITH observed AS (SELECT clock_timestamp() AS at),
                visible AS (SELECT session.* FROM mra.trading_session session,observed
                    WHERE session.exchange='XSHG' AND EXISTS (SELECT 1 FROM mra.market_capture_trading_session_normalization binding
                        JOIN mra.data_capture capture USING(capture_id) WHERE binding.session_id=session.session_id
                        AND capture.status='CAPTURED' AND capture.recorded_at<=observed.at)),
                input AS (SELECT visible.* FROM visible,observed WHERE close_at<=observed.at ORDER BY session_date DESC LIMIT 1)
                SELECT input.session_id,target.session_id,observed.at FROM input,observed,
                LATERAL (SELECT * FROM visible WHERE session_date>input.session_date ORDER BY session_date LIMIT 1) target""").fetchone()
        if row is None:
            raise RuntimeStateConflictError("DAILY_CALENDAR_COVERAGE_INCOMPLETE")
        return row[0], row[1], row[2]

    def run_plan_content(self, run_id: UUID) -> bytes | None:
        with self._pool.connection(read_only=True) as connection:
            row = connection.execute(
                """SELECT artifact.content_sha256,artifact.size_bytes FROM mra.runtime_run run
                JOIN mra.artifact artifact ON artifact.artifact_id=run.config_artifact_id AND artifact.content_sha256=run.config_hash
                WHERE run.run_id=%s""",
                (run_id,),
            ).fetchone()
        return None if row is None else self._byte_store.read_bytes(row[0], expected_size=row[1])

    def outcome_work_items(
        self, *, limit: int = 64
    ) -> tuple[DailyOutcomeWorkItem, ...]:
        """Discover historical settlement work independently of the current use."""

        if type(limit) is not int or not 1 <= limit <= 256:
            raise ValueError("daily Outcome scan limit must be between 1 and 256")
        with self._pool.connection(read_only=True) as connection:
            rows = connection.execute(
                """
                SELECT run.run_id, run.schedule_id, schedule.schedule_code,
                       run.fire_key, run.parent_run_id, run.state,
                       run.requested_at, run.code_sha, run.config_hash,
                       artifact.content_sha256, artifact.size_bytes,
                       coalesce(
                         latest.error_code,
                         run.terminal_reason_code
                       ) AS error_code,
                       EXISTS(SELECT 1 FROM mra.runtime_step settled
                              WHERE settled.run_id=run.run_id AND settled.step_key LIKE 'settle-%%')
                       AND NOT EXISTS(SELECT 1 FROM mra.runtime_step unsettled
                                      WHERE unsettled.run_id=run.run_id AND unsettled.step_key LIKE 'settle-%%'
                                        AND unsettled.state <> 'SUCCEEDED') AS settlement_steps_completed
                FROM mra.runtime_run AS run
                JOIN mra.runtime_schedule AS schedule USING (schedule_id)
                LEFT JOIN mra.artifact AS artifact
                  ON artifact.artifact_id = run.config_artifact_id
                 AND artifact.content_sha256 = run.config_hash
                 AND artifact.integrity_state = 'AVAILABLE'
                LEFT JOIN LATERAL (
                  SELECT attempt.error_code
                  FROM mra.runtime_attempt AS attempt
                  JOIN mra.runtime_step AS step USING (step_id)
                  WHERE step.run_id = run.run_id
                    AND attempt.error_code IS NOT NULL
                  ORDER BY attempt.created_at DESC, attempt.attempt_id DESC
                  LIMIT 1
                ) AS latest ON true
                WHERE schedule.schedule_code ~ '^daily-outcome-[0-9a-f]{32}$'
                  AND schedule.runtime_mode = 'SHADOW'
                  AND run.runtime_mode = 'SHADOW'
                  AND run.state IN ('QUEUED', 'RUNNING', 'WAITING', 'FAILED')
                  AND EXISTS (
                    SELECT 1 FROM mra.runtime_step AS step
                    WHERE step.run_id = run.run_id
                  )
                  AND NOT EXISTS (
                    SELECT 1 FROM mra.runtime_step AS step
                    WHERE step.run_id = run.run_id
                      AND step.implementation NOT LIKE 'research.daily_outcome.%%'
                  )
                ORDER BY
                  CASE run.state
                    WHEN 'RUNNING' THEN 0
                    WHEN 'QUEUED' THEN 1
                    WHEN 'WAITING' THEN 2
                    ELSE 3
                  END,
                  run.requested_at,
                  run.run_id
                LIMIT %s
                """,
                (limit,),
            ).fetchall()
        result: list[DailyOutcomeWorkItem] = []
        for row in rows:
            content = None
            error_code = row[11]
            if row[9] is None or row[10] is None:
                error_code = error_code or "FROZEN_PLAN_ARTIFACT_UNAVAILABLE"
            else:
                try:
                    content = self._byte_store.read_bytes(
                        row[9], expected_size=row[10]
                    )
                except (
                    OSError,
                    ValueError,
                    ArtifactByteStoreError,
                    ArtifactIntegrityError,
                ):
                    error_code = error_code or "FROZEN_PLAN_BYTES_UNREADABLE"
            result.append(
                DailyOutcomeWorkItem(
                    run_id=row[0],
                    schedule_id=row[1],
                    schedule_code=row[2],
                    fire_key=row[3],
                    parent_run_id=row[4],
                    run_state=row[5],
                    requested_at=row[6],
                    code_sha=row[7],
                    config_sha256=row[8],
                    plan_content=content,
                    error_code=error_code,
                    settlement_steps_completed=row[12],
                )
            )
        return tuple(result)

    def missing_elapsed_session_pairs(self, plan: DailyPredictionPlan) -> tuple[tuple[UUID, UUID], ...]:
        """Return at most 64 actual gaps without capping the ModelUse lifetime."""

        missing: list[tuple[UUID, UUID]] = []
        with self._pool.connection(read_only=True) as connection:
            cursor = connection.cursor()
            cursor.execute(
                """WITH calendar AS (
                    SELECT session_id,close_at,lead(session_id) OVER (ORDER BY session_date) AS target_id,
                           lead(open_at) OVER (ORDER BY session_date) AS target_start
                    FROM mra.trading_session WHERE exchange='XSHG'
                )
                SELECT calendar.session_id,calendar.target_id FROM calendar
                JOIN mra.experimental_model_use usage ON usage.experimental_model_use_id=%s
                LEFT JOIN mra.experimental_model_use_revocation stopped USING(experimental_model_use_id)
                WHERE calendar.target_start>greatest(usage.registered_at,usage.valid_from)
                  AND calendar.target_start<=least(
                    clock_timestamp(), usage.expires_at,
                    coalesce(stopped.revoked_at, usage.expires_at)
                  )
                ORDER BY calendar.close_at""",
                (plan.experimental_model_use_id,),
            )
            while len(missing) < 64:
                rows = cursor.fetchmany(128)
                if not rows:
                    break
                identities = {
                    (row[0], row[1]): uuid5(
                        plan.experimental_model_use_id,
                        "daily:" + str(row[0]) + ":" + str(row[1]),
                    )
                    for row in rows
                }
                run_ids = [
                    uuid5(identity, suffix)
                    for identity in identities.values()
                    for suffix in ("prediction-runtime", "abstention-runtime")
                ]
                existing = {
                    row[0]
                    for row in connection.execute(
                        "SELECT run_id FROM mra.runtime_run WHERE run_id=ANY(%s::uuid[])",
                        (run_ids,),
                    ).fetchall()
                }
                for pair, identity in identities.items():
                    if not any(
                        uuid5(identity, suffix) in existing
                        for suffix in ("prediction-runtime", "abstention-runtime")
                    ):
                        missing.append(pair)
                        if len(missing) == 64:
                            break
        return tuple(missing)

    def capture_roster(self, plan: DailyPredictionPlan, *, outcome: bool = False) -> tuple[tuple[UUID, str, Any], ...]:
        with self._pool.connection(read_only=True) as connection:
            rows = connection.execute(
                """SELECT instrument_id,identifier_value,session_date FROM mra.instrument_identifier,
                mra.trading_session WHERE identifier_scheme='BAOSTOCK' AND instrument_id=ANY(%s::uuid[])
                AND session_id=%s ORDER BY instrument_id""",
                (list(plan.instrument_ids), plan.target_session_id if outcome else plan.input_session_id),
            ).fetchall()
        if tuple(row[0] for row in rows) != plan.instrument_ids:
            raise ArtifactIntegrityError("daily Provider identifier roster is absent or ambiguous")
        return tuple(rows)

    def target_price_members(self, plan: DailyPredictionPlan) -> tuple[Any, ...]:
        return self._inputs.visible(
            provider_product_id=plan.provider_product_id,
            session_id=plan.target_session_id,
            instrument_ids=plan.instrument_ids,
            input_cutoff=self.now(),
        )

    def capture_by_key(self, product_id: UUID, key: str) -> UUID:
        with self._pool.connection(read_only=True) as connection:
            row = connection.execute(
                "SELECT capture_id FROM mra.data_capture WHERE provider_product_id=%s AND capture_key=%s AND status='CAPTURED'",
                (product_id, key),
            ).fetchone()
        if row is None:
            raise ArtifactIntegrityError("daily normalization has no exact successful Capture")
        return row[0]

    def collection_rounds(self, prediction_id: UUID, phase: str) -> tuple[tuple[int, str, datetime, bytes], ...]:
        if phase not in {"input", "outcome", "population"}:
            raise ValueError("unsupported daily collection phase")
        ids = {uuid5(prediction_id, phase + "-collection:" + str(n)): n for n in range(1, 17)}
        with self._pool.connection(read_only=True) as connection:
            rows = connection.execute(
                """SELECT run.run_id,run.state,run.created_at,artifact.content_sha256,artifact.size_bytes
                FROM mra.runtime_run run JOIN mra.artifact artifact ON artifact.artifact_id=run.config_artifact_id
                  AND artifact.content_sha256=run.config_hash WHERE run.run_id=ANY(%s::uuid[])""",
                (list(ids),),
            ).fetchall()
        result = tuple(
            sorted(
                ((ids[row[0]], row[1], row[2], self._byte_store.read_bytes(row[3], expected_size=row[4])) for row in rows),
                key=lambda row: row[0],
            )
        )
        if tuple(row[0] for row in result) != tuple(range(1, len(result) + 1)):
            raise ArtifactIntegrityError("daily collection round roster has a gap")
        return result

    def population_source_ready(self, plan: DailyPredictionPlan) -> bool:
        """Readiness only; Selection still freezes and verifies every member independently."""
        with self._pool.connection(read_only=True) as connection:
            row = connection.execute(
                """SELECT EXISTS (SELECT 1 FROM mra.classification classification
                JOIN mra.market_capture_classification_normalization binding USING(classification_id)
                JOIN mra.data_capture capture USING(capture_id)
                JOIN mra.artifact artifact ON artifact.artifact_id=capture.artifact_id
                WHERE classification.classification_scheme=%s AND classification.classification_code=%s
                  AND classification.effective_from<=%s
                  AND (classification.effective_to IS NULL OR classification.effective_to>%s)
                  AND capture.provider_product_id=%s AND capture.status='CAPTURED'
                  AND capture.recorded_at<=%s
                  AND mra.market_artifact_is_readable(artifact.integrity_state,artifact.last_verified_at))""",
                (plan.classification_scheme,plan.classification_code,plan.decision_time,plan.decision_time,
                 plan.provider_product_id,plan.input_cutoff),
            ).fetchone()
        return row == (True,)

    def model_use_available(self, plan: DailyPredictionPlan) -> bool:
        with self._pool.connection(read_only=True) as connection:
            record = PostgresResearchModelRepository(connection).experimental_use(plan.experimental_model_use_id, lock=False)
            now = connection.execute("SELECT clock_timestamp()").fetchone()
        assert now is not None
        return (
            record.revoked_at is None
            and record.registered_at < plan.decision_time
            and record.plan.valid_from <= plan.decision_time < record.plan.expires_at
            and now[0] < record.plan.expires_at
        )

    def validate_configuration(self, plan: DailyPredictionPlan) -> None:
        with self._pool.connection(read_only=True) as connection:
            use = PostgresResearchModelRepository(connection).experimental_use(plan.experimental_model_use_id, lock=False)
            row = connection.execute(
                """SELECT feature.algorithm_code,feature.algorithm_version,feature.value_unit,
                model.target_definition_id FROM mra.model_version version JOIN mra.model model USING(model_id)
                JOIN mra.model_feature_definition feature_binding USING(model_id)
                JOIN mra.feature_definition feature USING(feature_definition_id)
                WHERE version.model_version_id=%s AND feature.feature_definition_id=%s
                  AND NOT EXISTS(SELECT 1 FROM mra.model_feature_definition other WHERE other.model_id=model.model_id AND other.feature_definition_id<>feature.feature_definition_id)""",
                (plan.model_version_id, plan.feature_definition_id),
            ).fetchall()
        if (
            use.plan.model_version_id != plan.model_version_id
            or use.plan.baseline_strategy_version_id != plan.baseline_strategy_version_id
            or len(row) != 1
            or row[0] != ("session_open_close_move_v1", "1", "RATIO", plan.target_definition_id)
        ):
            raise ArtifactIntegrityError("daily configuration differs from the exact model/feature/baseline use")

    def ready(self, plan: DailyPredictionPlan) -> DailyDataReady:
        result = self.observe(plan)
        if result.content_sha256 != plan.input_content_sha256:
            raise ArtifactIntegrityError("daily frozen complete input snapshot changed")
        return result

    def observe(self, plan: DailyPredictionPlan) -> DailyDataReady:
        """Observe exact request scope before freezing its input hash."""
        with self._pool.connection(read_only=True) as connection:
            row = connection.execute(
                """
                SELECT input.close_at, target.open_at, target.close_at, clock_timestamp()
                FROM mra.trading_session input JOIN mra.trading_session target ON target.session_id=%s
                WHERE input.session_id=%s AND target.exchange=input.exchange
                  AND target.session_date>input.session_date
                  AND NOT EXISTS (SELECT 1 FROM mra.trading_session intermediate
                     WHERE intermediate.exchange=input.exchange AND intermediate.session_date>input.session_date
                       AND intermediate.session_date<target.session_date)
                  AND (SELECT count(DISTINCT binding.session_id)
                       FROM mra.market_capture_trading_session_normalization binding JOIN mra.data_capture capture USING(capture_id)
                       WHERE binding.session_id IN(input.session_id,target.session_id)
                         AND capture.status='CAPTURED' AND capture.recorded_at<=%s)=2
                """,
                (plan.target_session_id, plan.input_session_id, plan.input_cutoff),
            ).fetchone()
        if row is None or plan.decision_time > row[3]:
            raise RuntimeStateConflictError("daily plan lacks an exact visible next TradingSession or actual DecisionTime")
        members = self._inputs.visible(
            provider_product_id=plan.provider_product_id,
            session_id=plan.input_session_id,
            instrument_ids=plan.instrument_ids,
            input_cutoff=plan.input_cutoff,
        )
        ready = freeze_data_ready(
            input_session_id=plan.input_session_id,
            target_session_id=plan.target_session_id,
            input_event_end=row[0],
            input_cutoff=plan.input_cutoff,
            decision_time=plan.decision_time,
            target_window_start=row[1],
            target_window_end=row[2],
            expected_instruments=plan.instrument_ids,
            members=members,
        )
        return ready

    def universe_revision(self, plan: DailyPredictionPlan) -> UUID:
        with self._pool.connection(read_only=True) as connection:
            rows = connection.execute(
                """SELECT universe_revision_id FROM mra.universe_revision
                WHERE universe_id=%s AND decision_time=%s AND scope_content_sha256=%s
                AND NOT EXISTS (SELECT 1 FROM mra.exploratory_retrospective_universe_revision source
                    WHERE source.universe_revision_id=universe_revision.universe_revision_id)""",
                (plan.universe_id, plan.decision_time, str(plan.universe_scope.content_sha256)),
            ).fetchall()
        if len(rows) != 1:
            raise ArtifactIntegrityError("daily exact UniverseRevision is absent or ambiguous")
        return rows[0][0]

    def population(self, plan: DailyPredictionPlan) -> tuple[DailyPopulationMember, ...]:
        universe = self.universe_revision(plan)
        with self._pool.connection(read_only=True) as connection:
            rows = connection.execute(
                """SELECT member.instrument_id, member.universe_member_id,
                member.membership_status, member.reason_code, assessment.eligibility_assessment_id, assessment.result,
                (SELECT string_agg(reason.reason_code,',' ORDER BY reason.eligibility_rule_id) FROM mra.eligibility_reason reason
                 WHERE reason.eligibility_assessment_id=assessment.eligibility_assessment_id)
                FROM mra.universe_member member LEFT JOIN mra.eligibility_assessment assessment
                  ON assessment.universe_member_id=member.universe_member_id AND assessment.eligibility_policy_id=%s
                  AND assessment.decision_time=%s
                WHERE member.universe_revision_id=%s ORDER BY member.instrument_id""",
                (plan.eligibility_policy_id, plan.decision_time, universe),
            ).fetchall()
        members = tuple(DailyPopulationMember(*row) for row in rows)
        if tuple(item.instrument_id for item in members) != plan.instrument_ids or any(
            item.eligibility_assessment_id is None for item in members
        ):
            raise ArtifactIntegrityError("daily Universe/Eligibility full population differs")
        return members

    def candidate_set(self, plan: DailyPredictionPlan) -> UUID:
        with self._pool.connection(read_only=True) as connection:
            rows = connection.execute(
                "SELECT candidate_set_id FROM mra.candidate_set WHERE dataset_id=%s AND candidate_policy_id=%s",
                (plan.dataset_id, plan.candidate_policy_id),
            ).fetchall()
        if len(rows) != 1:
            raise ArtifactIntegrityError("daily exact CandidateSet is absent or ambiguous")
        return rows[0][0]

    def decision_run(self, plan: DailyPredictionPlan) -> UUID:
        with self._pool.connection(read_only=True) as connection:
            rows = connection.execute(
                "SELECT decision_run_id FROM mra.decision_run WHERE candidate_set_id=%s", (self.candidate_set(plan),)
            ).fetchall()
        if len(rows) != 1:
            raise ArtifactIntegrityError("daily exact DecisionRun is absent or ambiguous")
        return rows[0][0]

    def forecast_projection(self, plan: DailyPredictionPlan) -> dict[str, Any]:
        decision = self.decision_run(plan)
        population = self.population(plan)
        with self._pool.connection(read_only=True) as connection:
            root = connection.execute(
                """SELECT run.forecast_group_id,run.signal_group_id,run.recorded_at,
                    run.forecast_count,run.content_sha256,run.command_receipt_id,receipt.result_hash
                FROM mra.forecast_run run JOIN mra.command_receipt receipt ON receipt.receipt_id=run.command_receipt_id
                WHERE run.decision_run_id=%s AND run.strategy_version_id=%s AND receipt.status='SUCCEEDED'""",
                (decision, plan.strategy_version_id),
            ).fetchone()
            if root is None or not PostgresInferenceRepository(connection).reconcile(root[1], root[0], lock=False).matched:
                raise ArtifactIntegrityError("daily Forecast Authority does not reconcile")
            use = PostgresResearchModelRepository(connection).experimental_use(plan.experimental_model_use_id, lock=False)
            baseline = connection.execute(
                """SELECT forecast_group_id,signal_group_id,recorded_at,content_sha256
                FROM mra.forecast_run WHERE decision_run_id=%s AND strategy_version_id=%s""",
                (decision, plan.baseline_strategy_version_id),
            ).fetchone()
            if (
                use.plan.baseline_strategy_version_id != plan.baseline_strategy_version_id
                or baseline is None
                or baseline[2] > root[2]
                or not PostgresInferenceRepository(connection).reconcile(baseline[1], baseline[0], lock=False).matched
            ):
                raise ArtifactIntegrityError("daily baseline publication does not reconcile with explicit model use")
            with connection.cursor(row_factory=dict_row) as cursor:
                bindings = cursor.execute(
                    "SELECT * FROM mra.forecast_model_binding WHERE forecast_group_id=%s ORDER BY commitment_id", (root[0],)
                ).fetchall()
                rows = cursor.execute(
                    """SELECT candidate.instrument_id,candidate.disposition,candidate.reason_code AS candidate_reason,
                    candidate.composite_score,candidate.competition_rank,commitment.commitment_id,
                    forecast.forecast_id,forecast.status AS forecast_status,forecast.reason_code AS forecast_reason,
                    estimate.forecast_estimate_id,estimate.point_estimate,estimate.target_metric_definition_id,
                    signal.status AS signal_status,signal.reason_code AS signal_reason,
                    baseline.forecast_id AS baseline_forecast_id,baseline.status AS baseline_status,baseline.reason_code AS baseline_reason,
                    baseline_estimate.point_estimate AS baseline_point_estimate
                    FROM mra.candidate candidate
                    LEFT JOIN mra.decision_target_commitment commitment ON commitment.candidate_id=candidate.candidate_id AND commitment.decision_run_id=%s
                    LEFT JOIN mra.forecast forecast ON forecast.commitment_id=commitment.commitment_id AND forecast.forecast_group_id=%s
                    LEFT JOIN mra.forecast_estimate estimate ON estimate.forecast_id=forecast.forecast_id
                    LEFT JOIN mra.signal signal ON signal.signal_id=forecast.signal_id
                    LEFT JOIN mra.forecast baseline ON baseline.commitment_id=commitment.commitment_id AND baseline.forecast_group_id=%s
                    LEFT JOIN mra.forecast_estimate baseline_estimate ON baseline_estimate.forecast_id=baseline.forecast_id
                      AND baseline_estimate.target_metric_definition_id=estimate.target_metric_definition_id
                    WHERE candidate.candidate_set_id=%s ORDER BY candidate.instrument_id""",
                    (decision, root[0], baseline[0], self.candidate_set(plan)),
                ).fetchall()
        if len(bindings) != int(root[3]):
            raise ArtifactIntegrityError("daily model binding roster is incomplete")
        fitted: set[tuple[str, int]] = set()
        by_estimate = {}
        for row in bindings:
            values = {
                field.name: row["status" if field.name == "prediction_state" else field.name]
                for field in fields(ForecastModelBindingPlan)
                if field.init
            }
            values["prediction_state"] = ModelPredictionState(values["prediction_state"])
            rebuilt = ForecastModelBindingPlan(**values)
            if any(
                str(getattr(rebuilt, key)) != str(row[key])
                for key in ("content_sha256", "inference_input_sha256", "inference_output_sha256")
            ):
                raise ArtifactIntegrityError("daily model binding actual fields differ from content identity")
            if rebuilt.experimental_model_use_id != plan.experimental_model_use_id or rebuilt.model_version_id != plan.model_version_id:
                raise ArtifactIntegrityError("daily Forecast uses another explicit ModelVersion/use")
            by_estimate[rebuilt.forecast_estimate_id] = rebuilt
            fitted.add((str(rebuilt.fitted_model_content_sha256), rebuilt.fitted_model_size_bytes))
        for row in rows:
            if row["forecast_estimate_id"] is not None:
                binding = by_estimate.get(row["forecast_estimate_id"])
                if binding is None or binding.point_estimate != row["point_estimate"] or binding.commitment_id != row["commitment_id"]:
                    raise ArtifactIntegrityError("daily published prediction and model binding differ")
        for content, size in fitted:
            self._byte_store.read_bytes(content, expected_size=size)
        for column, label in (("point_estimate", "model_rank"), ("baseline_point_estimate", "baseline_rank")):
            ranking_values = sorted((row[column] for row in rows if row[column] is not None), reverse=True)
            ranks = {value: ranking_values.index(value) + 1 for value in set(ranking_values)}
            for row in rows:
                row[label] = ranks.get(row[column])
        counts = {
            "sampled": len(population),
            "eligible": sum(m.eligible for m in population),
            "feature_ready": sum(row["composite_score"] is not None for row in rows),
            "model_prediction": sum(row["point_estimate"] is not None for row in rows),
            "baseline_prediction": sum(row["baseline_point_estimate"] is not None for row in rows),
            "common_prediction": sum(row["point_estimate"] is not None and row["baseline_point_estimate"] is not None for row in rows),
        }
        return {
            "schema": "daily-experimental-prediction-report-v1",
            "prediction_id": plan.prediction_id,
            "plan_sha256": plan.content_sha256,
            "dataset_id": plan.dataset_id,
            "decision_run_id": decision,
            "forecast_group_id": root[0],
            "forecast_sha256": root[4],
            "publication_receipt_id": root[5],
            "publication_result_hash": root[6],
            "published_at": root[2],
            "decision_time": plan.decision_time,
            "input_cutoff": plan.input_cutoff,
            "input_session_id": plan.input_session_id,
            "target_session_id": plan.target_session_id,
            "model_version_id": plan.model_version_id,
            "model_inference_state": "NOT_RUN_EMPTY_POPULATION" if not rows else "EXECUTED",
            "experimental_model_use_id": plan.experimental_model_use_id,
            "target_definition_id": plan.target_definition_id,
            "feature_definition_id": plan.feature_definition_id,
            "evidence_class": "EXPERIMENTAL_SHADOW",
            "qualification": "NOT_QUALIFIED",
            "trading_instruction": False,
            "risk_state": "NOT_REQUESTED_PREDICTION_ONLY",
            "code_sha": plan.code_sha,
            "code_artifact": plan.code_artifact,
            "configuration_artifact": plan.config_artifact,
            "baseline_forecast_group_id": baseline[0],
            "baseline_forecast_sha256": baseline[3],
            "baseline_strategy_version_id": plan.baseline_strategy_version_id,
            "denominators": counts,
            "population": population,
            "predictions": rows,
        }
