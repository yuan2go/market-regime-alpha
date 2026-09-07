"""Observe current bytes through Artifact owner; never change Capture known-time."""

from uuid import UUID

from market_regime_alpha.bootstrap import bootstrap_application
from market_regime_alpha.runtime.application.service import ActorType, CommandContext


def verify_scope(settings, config, guard, observation_key):
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
    if not rows:
        raise ValueError("PROSPECTIVE_ARTIFACT_ROSTER_EMPTY")
    observations = []
    with bootstrap_application(settings) as application:
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
    return observations
