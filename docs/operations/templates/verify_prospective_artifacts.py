"""Observe current bytes through Artifact owner; never change Capture known-time."""

from dataclasses import replace
from uuid import UUID, uuid5

from market_regime_alpha.bootstrap import bootstrap_application
from market_regime_alpha.runtime.application.service import ActorType, CommandContext


def _daily_input_artifacts(connection, plan):
    # Integrity observation can refresh bytes of the frozen input or its later
    # Outcome. It cannot change a Capture's original visibility or select labels.
    return connection.execute(
        """SELECT DISTINCT capture.artifact_id
        FROM mra.market_bar_revision bar
        JOIN mra.data_capture capture USING (capture_id, provider_product_id)
        WHERE bar.instrument_id=ANY(%s::uuid[])
          AND bar.provider_product_id=%s AND bar.timeframe='DAILY'
          AND bar.session_id=ANY(%s::uuid[]) AND capture.status='CAPTURED'
          AND (bar.session_id=%s OR capture.recorded_at<=%s)
          AND capture.artifact_id IS NOT NULL
        UNION
        SELECT capture.artifact_id FROM mra.trading_session session
        JOIN mra.data_capture capture ON capture.capture_id=session.source_capture_id
        WHERE session.session_id=ANY(%s::uuid[]) AND capture.status='CAPTURED'
          AND capture.artifact_id IS NOT NULL
        ORDER BY artifact_id""",
        (list(plan.instrument_ids), plan.provider_product_id,
         [plan.input_session_id, plan.target_session_id],
         plan.target_session_id, plan.input_cutoff,
         [plan.input_session_id, plan.target_session_id]),
    ).fetchall()


def _daily_execution_artifacts(connection, plan):
    # Outcome closure locks both the original Runtime config and every exact
    # Target algorithm/config binding. Integrity observation keeps their identity.
    return connection.execute(
        """WITH identities AS (
          SELECT code_artifact_id AS artifact_id FROM mra.target_definition WHERE target_definition_id=%(target)s
          UNION SELECT config_artifact_id FROM mra.target_definition WHERE target_definition_id=%(target)s
          UNION SELECT code_artifact_id FROM mra.target_metric_definition WHERE target_definition_id=%(target)s
          UNION SELECT config_artifact_id FROM mra.target_metric_definition WHERE target_definition_id=%(target)s
          UNION SELECT config_artifact_id FROM mra.runtime_run WHERE run_id=ANY(%(runs)s::uuid[])
          UNION SELECT unnest(%(plan_artifacts)s::uuid[])
        ) SELECT artifact_id FROM identities WHERE artifact_id IS NOT NULL ORDER BY artifact_id""",
        {"target": plan.target_definition_id,
         "runs": [plan.runtime_run_id, uuid5(plan.prediction_id, "outcome-evaluation-runtime")],
         "plan_artifacts": [plan.code_artifact.artifact_id, plan.config_artifact.artifact_id, plan.universe_scope.artifact_id]},
    ).fetchall()


def _daily_static_artifacts(connection, plan):
    return connection.execute(
        """WITH selected AS (
            SELECT source_capture_id FROM mra.instrument WHERE instrument_id=ANY(%s::uuid[])
            UNION SELECT instrument.source_capture_id FROM mra.instrument instrument
                JOIN mra.classification_membership_revision member USING (instrument_id)
                JOIN mra.classification classification USING (classification_id)
                WHERE classification.classification_scheme=%s AND classification.classification_code=%s
            UNION SELECT source_capture_id FROM mra.classification
                WHERE classification_scheme=%s AND classification_code=%s
            UNION SELECT source_capture_id FROM mra.classification_membership_revision
                WHERE instrument_id=ANY(%s::uuid[])
            UNION SELECT capture_id FROM mra.instrument_fact_revision
                WHERE instrument_id=ANY(%s::uuid[])
        )
        SELECT DISTINCT capture.artifact_id FROM selected
        JOIN mra.data_capture capture ON capture.capture_id=selected.source_capture_id
        WHERE capture.artifact_id IS NOT NULL AND capture.status='CAPTURED'
        ORDER BY capture.artifact_id""",
        (list(plan.instrument_ids), plan.classification_scheme,
         plan.classification_code, plan.classification_scheme,
         plan.classification_code, list(plan.instrument_ids), list(plan.instrument_ids)),
    ).fetchall()


def verify_scope(settings, config, guard, observation_key, *, daily_plan=None):
    # This read-only operational roster has no business Authority or FK consumers.
    # Capture lineage and Artifact metadata are reloaded by their existing owner.
    with guard.connection.transaction():
        rows = guard.connection.execute(
            """
            WITH generations AS (
                SELECT market_archive_id, target_definition_id
                FROM mra.prospective_archive_generation WHERE series_code = %s
            ), identities AS (
                SELECT root.code_artifact_id AS artifact_id
                FROM mra.market_archive root JOIN generations USING (market_archive_id)
                UNION SELECT root.config_artifact_id
                FROM mra.market_archive root JOIN generations USING (market_archive_id)
                UNION SELECT target.code_artifact_id
                FROM mra.target_definition target JOIN generations USING (target_definition_id)
                UNION SELECT target.config_artifact_id
                FROM mra.target_definition target JOIN generations USING (target_definition_id)
                UNION SELECT run.config_artifact_id
                FROM mra.runtime_run run JOIN generations g
                ON run.fire_key = 'archive:' || g.market_archive_id::text || ':predeclare'
                UNION SELECT capture.artifact_id
                FROM mra.market_archive_capture_observation observation
                JOIN generations USING (market_archive_id)
                JOIN mra.data_capture capture USING (capture_id)
            )
            SELECT artifact_id FROM identities WHERE artifact_id IS NOT NULL
            ORDER BY artifact_id
            """,
            (config.series_code,),
        ).fetchall()
        if daily_plan is not None:
            # Static instrument/classification evidence does not get a new Capture
            # every day. Refresh physical integrity, never its historical time.
            daily_rows = _daily_static_artifacts(guard.connection, daily_plan)
            rows = sorted(set(rows) | set(daily_rows), key=lambda row: str(row[0]))
    observations = []
    with bootstrap_application(settings) as application:
        if daily_plan is not None:
            from market_regime_alpha.interfaces.daily_service import _historical_outcome_plan
            from market_regime_alpha.interfaces.daily_collection import DailyCollectionPlan

            reads = application.daily_prediction_reads
            input_session, target_session, now = reads.current_sessions()
            identity = uuid5(daily_plan.experimental_model_use_id, "daily:" + str(input_session) + ":" + str(target_session))
            plans = [daily_plan, replace(daily_plan, input_session_id=input_session,
                target_session_id=target_session, input_cutoff=now, decision_time=now)]
            # Discover frozen Artifact references before asking DataReady to read
            # them; stale physical verification is precisely what this repairs.
            plans.extend(DailyCollectionPlan.decode(content).prediction
                for phase in ("population", "input")
                for _, _, _, content in reads.collection_rounds(identity, phase))
            plans.extend(_historical_outcome_plan(item) for item in reads.outcome_work_items(limit=64)
                         if item.run_state not in {'FAILED', 'WAITING'})
            with guard.connection.transaction():
                rows = sorted(set(rows) | {row for plan in plans
                    for row in (*_daily_input_artifacts(guard.connection, plan),
                                *_daily_execution_artifacts(guard.connection, plan))}, key=lambda row: str(row[0]))
        if not rows:
            raise ValueError("PROSPECTIVE_ARTIFACT_ROSTER_EMPTY")
        for row in rows:
            guard.before_action()
            artifact_id = UUID(str(row[0]))
            record = application.artifacts.verify(
                artifact_id,
                verifier_id=config.actor_id,
                context=CommandContext(
                    idempotency_key=f"{observation_key}:{artifact_id}",
                    actor_type=ActorType.SYSTEM,
                    actor_id=config.actor_id,
                    reason_code="OPERATIONAL_ARTIFACT_INTEGRITY_OBSERVATION",
                ),
            )
            observations.append(
                {
                    "artifact_id": str(artifact_id),
                    "result": record.result,
                    "verification_id": str(record.verification_id),
                }
            )
            if record.result != 'VERIFIED':
                raise ValueError('OPERATIONAL_ARTIFACT_VERIFICATION_FAILED')
    return observations
