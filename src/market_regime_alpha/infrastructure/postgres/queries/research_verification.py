"""Read-only relational replay checks for WP-11 research Authorities."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import psycopg

from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from market_regime_alpha.research_qualification.domain.evaluation import (
    ProtocolMetricDefinition,
)
from market_regime_alpha.research_qualification.domain.research_vocabulary import (
    AcceptanceOperator,
    CandidateDisposition,
    EvaluationInclusionPolicy,
    EvaluationMissingnessPolicy,
    EvaluationReducer,
    EvaluationSourceKind,
    EvaluationSourceMeasure,
    EvaluationSliceKind,
    ExploratoryBacktestArmKind,
    MetricDirection,
    SourceMetricValueType,
)
from market_regime_alpha.research_qualification.domain.verification import (
    ResearchVerificationMismatch,
    ResearchVerificationMismatchKind,
)
from market_regime_alpha.shared.hashing import canonical_json_sha256


Mismatch = ResearchVerificationMismatch
Kind = ResearchVerificationMismatchKind


class PostgresResearchEvaluationVerificationProvider:
    """Recomputes frozen WP-11 facts without Provider, Market, or mutation paths."""

    def __init__(self, pool: TargetPostgresPool) -> None:
        self._pool = pool

    def inspect_partition(self, research_partition_id: UUID) -> tuple[Mismatch, ...]:
        mismatches: list[Mismatch] = []
        with self._pool.connection(read_only=True) as connection:
            root = connection.execute(
                """
                SELECT target_definition_id, target_version,
                       target_definition_sha256, status, purpose,
                       population_scope, exchange_code, timezone_name,
                       decision_start_session_id, decision_end_session_id,
                       decision_start_date, decision_end_date,
                       outcome_horizon_sessions, purge_before_sessions,
                       purge_after_sessions, embargo_sessions,
                       protected_start_session_id, protected_end_session_id,
                       protected_start_date, protected_end_date,
                       calendar_session_count, calendar_roster_sha256,
                       member_count, member_roster_sha256
                FROM mra.research_partition
                WHERE research_partition_id = %s
                """,
                (research_partition_id,),
            ).fetchone()
            if root is None:
                return (_missing("research_partition", research_partition_id),)
            if str(root[3]) != "FROZEN":
                mismatches.append(
                    _state("partition.status", "FROZEN", str(root[3]))
                )
            self._inspect_target_contract(
                connection, UUID(str(root[0])), int(root[1]), str(root[2]), mismatches
            )
            calendar = connection.execute(
                """
                SELECT count(*),
                       mra.canonical_sha256(
                           replace(
                               json_agg(
                                   json_build_object(
                                       'break_end_at', break_end_at,
                                       'break_start_at', break_start_at,
                                       'close_at', close_at,
                                       'decision_reference_at', decision_reference_at,
                                       'decision_visible_at', decision_visible_at,
                                       'exchange_code', exchange,
                                       'known_at', known_at,
                                       'open_at', open_at,
                                       'recorded_at', recorded_at,
                                       'session_date', session_date,
                                       'session_id', session_id,
                                       'source_capture_id', source_capture_id,
                                       'timezone_name', timezone_name
                                   ) ORDER BY session_date, session_id
                               )::text,
                               ' ',
                               ''
                           )
                       )
                FROM mra.trading_session
                WHERE exchange = %s
                  AND session_date BETWEEN %s AND %s
                """,
                (str(root[6]), root[18], root[19]),
            ).fetchone()
            assert calendar is not None
            _compare_count(
                mismatches,
                "partition.calendar_session_count",
                int(root[20]),
                int(calendar[0]),
            )
            _compare_hash(
                mismatches,
                "partition.calendar_roster_sha256",
                str(root[21]),
                str(calendar[1]),
            )
            members = connection.execute(
                """
                SELECT member_ordinal, commitment_id, content_sha256,
                       target_definition_id, exchange_code, timezone_name,
                       decision_session_date,
                       decision_reference_observation_id, decision_time,
                       candidate_disposition, commitment_recorded_at,
                       runtime_mode, decision_session_id,
                       earliest_outcome_event_at, outcome_due_at
                FROM mra.research_partition_member
                WHERE research_partition_id = %s
                ORDER BY member_ordinal
                """,
                (research_partition_id,),
            ).fetchall()
            actual_member_hash = canonical_json_sha256(
                tuple(
                    {
                        "commitment_id": UUID(str(row[1])),
                        "content_sha256": str(row[2]),
                        "member_ordinal": int(row[0]),
                    }
                    for row in members
                )
            )
            _inspect_order(
                mismatches,
                "partition.member_ordinals",
                tuple(int(row[0]) for row in members),
            )
            _compare_count(
                mismatches,
                "partition.member_count",
                int(root[22]),
                len(members),
            )
            _compare_hash(
                mismatches,
                "partition.member_roster_sha256",
                str(root[23]),
                actual_member_hash,
            )
            invalid_members = sum(
                UUID(str(row[3])) != UUID(str(root[0]))
                or str(row[4]) != str(root[6])
                or str(row[5]) != str(root[7])
                or not (root[10] <= row[6] <= root[11])
                for row in members
            )
            if invalid_members:
                mismatches.append(
                    _identity(
                        "partition.member_calendar_target",
                        "all members match frozen Target/exchange/window",
                        str(invalid_members),
                    )
                )
            invalid_member_hashes = sum(
                str(row[2])
                != canonical_json_sha256(
                    {
                        "candidate_disposition": str(row[9]),
                        "commitment_id": UUID(str(row[1])),
                        "commitment_recorded_at": row[10],
                        "decision_reference_observation_id": UUID(str(row[7])),
                        "decision_session_id": UUID(str(row[12])),
                        "decision_session_date": row[6],
                        "decision_time": row[8],
                        "earliest_outcome_event_at": row[13],
                        "exchange_code": str(row[4]),
                        "outcome_due_at": row[14],
                        "runtime_mode": str(row[11]),
                        "target_definition_id": UUID(str(row[3])),
                        "timezone_name": str(row[5]),
                    }
                )
                for row in members
            )
            if invalid_member_hashes:
                mismatches.append(
                    _compare_content_count(
                        "partition.member_content_sha256",
                        invalid_member_hashes,
                    )
                )
            population_difference = connection.execute(
                """
                WITH expected AS (
                    SELECT commitment.commitment_id
                    FROM mra.decision_target_commitment AS commitment
                    JOIN mra.decision_reference_observation AS reference
                      ON reference.decision_reference_observation_id =
                         commitment.decision_reference_observation_id
                    JOIN mra.trading_session AS session
                      ON session.session_id = reference.session_id
                    WHERE commitment.target_definition_id = %s
                      AND session.exchange = %s
                      AND session.session_date BETWEEN %s AND %s
                      AND (%s = 'ALL_COMMITMENTS'
                           OR commitment.candidate_disposition = %s)
                ), actual AS (
                    SELECT commitment_id
                    FROM mra.research_partition_member
                    WHERE research_partition_id = %s
                )
                SELECT count(*) FROM (
                    (SELECT commitment_id FROM expected
                     EXCEPT SELECT commitment_id FROM actual)
                    UNION ALL
                    (SELECT commitment_id FROM actual
                     EXCEPT SELECT commitment_id FROM expected)
                ) AS difference
                """,
                (
                    root[0],
                    root[6],
                    root[10],
                    root[11],
                    root[5],
                    root[5],
                    research_partition_id,
                ),
            ).fetchone()
            assert population_difference is not None
            if int(population_difference[0]):
                mismatches.append(
                    _identity(
                        "partition.population_roster",
                        "exact database-derived commitment set",
                        str(population_difference[0]),
                    )
                )
            shifted = connection.execute(
                """
                SELECT
                  (SELECT session_id FROM mra.trading_session
                   WHERE exchange = %s AND session_date <= %s
                   ORDER BY session_date DESC, session_id DESC
                   OFFSET %s LIMIT 1),
                  (SELECT session_id FROM mra.trading_session
                   WHERE exchange = %s AND session_date >= %s
                   ORDER BY session_date, session_id
                   OFFSET %s LIMIT 1)
                """,
                (
                    root[6],
                    root[10],
                    root[13],
                    root[6],
                    root[11],
                    int(root[12]) + int(root[14]) + int(root[15]),
                ),
            ).fetchone()
            assert shifted is not None
            if shifted != (root[16], root[17]):
                mismatches.append(
                    _identity(
                        "partition.protected_bounds",
                        str((root[16], root[17])),
                        str(shifted),
                    )
                )
            self._inspect_provenance(
                connection,
                aggregate_kind="RESEARCH_PARTITION",
                aggregate_id=research_partition_id,
                required_commands=("FREEZE_RESEARCH_PARTITION",),
                mismatches=mismatches,
            )
        return tuple(mismatches)

    def inspect_experiment(self, experiment_id: UUID) -> tuple[Mismatch, ...]:
        mismatches: list[Mismatch] = []
        with self._pool.connection(read_only=True) as connection:
            root = connection.execute(
                """
                SELECT target_definition_id, target_version,
                       target_definition_sha256, status,
                       definition_sha256, partition_count,
                       partition_roster_sha256, content_sha256,
                       registered_at
                FROM mra.experiment WHERE experiment_id = %s
                """,
                (experiment_id,),
            ).fetchone()
            if root is None:
                return (_missing("experiment", experiment_id),)
            if str(root[3]) != "REGISTERED":
                mismatches.append(_state("experiment.status", "REGISTERED", str(root[3])))
            self._inspect_target_contract(
                connection, UUID(str(root[0])), int(root[1]), str(root[2]), mismatches
            )
            rows = connection.execute(
                """
                SELECT binding.binding_ordinal,
                       binding.experiment_partition_id,
                       binding.research_partition_id,
                       binding.content_sha256,
                       binding.target_definition_id, binding.target_version,
                       binding.target_definition_sha256,
                       binding.partition_purpose,
                       binding.partition_content_sha256, binding.bound_at,
                       partition.frozen_at, partition.purpose,
                       partition.content_sha256
                FROM mra.experiment_partition AS binding
                JOIN mra.research_partition AS partition
                  ON partition.research_partition_id = binding.research_partition_id
                WHERE binding.experiment_id = %s
                ORDER BY binding.binding_ordinal
                """,
                (experiment_id,),
            ).fetchall()
            _inspect_order(
                mismatches,
                "experiment.partition_ordinals",
                tuple(int(row[0]) for row in rows),
            )
            _compare_count(
                mismatches, "experiment.partition_count", int(root[5]), len(rows)
            )
            actual_roster_hash = canonical_json_sha256(
                tuple(
                    {
                        "binding_ordinal": int(row[0]),
                        "content_sha256": str(row[3]),
                        "experiment_partition_id": UUID(str(row[1])),
                        "research_partition_id": UUID(str(row[2])),
                    }
                    for row in rows
                )
            )
            _compare_hash(
                mismatches,
                "experiment.partition_roster_sha256",
                str(root[6]),
                actual_roster_hash,
            )
            actual_content_hash = canonical_json_sha256(
                {
                    "definition_sha256": str(root[4]),
                    "partition_count": int(root[5]),
                    "partition_roster_sha256": str(root[6]),
                }
            )
            _compare_hash(
                mismatches,
                "experiment.content_sha256",
                str(root[7]),
                actual_content_hash,
            )
            invalid = sum(
                UUID(str(row[4])) != UUID(str(root[0]))
                or int(row[5]) != int(root[1])
                or str(row[6]) != str(root[2])
                or str(row[7]) != str(row[11])
                or str(row[8]) != str(row[12])
                or not (row[10] < root[8] <= row[9])
                for row in rows
            )
            if invalid:
                mismatches.append(
                    _identity(
                        "experiment.partition_bindings",
                        "exact Target/Partition/time binding",
                        str(invalid),
                    )
                )
            invalid_binding_hashes = sum(
                str(row[3])
                != canonical_json_sha256(
                    {
                        "binding_ordinal": int(row[0]),
                        "experiment_id": experiment_id,
                        "experiment_partition_id": UUID(str(row[1])),
                        "partition_content_sha256": str(row[8]),
                        "partition_purpose": str(row[7]),
                        "research_partition_id": UUID(str(row[2])),
                        "target_definition_id": UUID(str(row[4])),
                        "target_definition_sha256": str(row[6]),
                        "target_version": int(row[5]),
                    }
                )
                for row in rows
            )
            if invalid_binding_hashes:
                mismatches.append(
                    _compare_content_count(
                        "experiment.partition_content_sha256",
                        invalid_binding_hashes,
                    )
                )
            self._inspect_provenance(
                connection,
                aggregate_kind="EXPERIMENT",
                aggregate_id=experiment_id,
                required_commands=("REGISTER_EXPERIMENT",),
                mismatches=mismatches,
            )
        return tuple(mismatches)

    def inspect_evaluation_run(self, evaluation_run_id: UUID) -> tuple[Mismatch, ...]:
        mismatches: list[Mismatch] = []
        with self._pool.connection(read_only=True) as connection:
            run = connection.execute(
                """
                SELECT status, evaluation_protocol_id,
                       research_partition_id, target_definition_id,
                       partition_purpose, expected_member_count,
                       expected_protocol_metric_count, access_count,
                       observation_count, metric_count,
                       metric_observation_count, input_roster_sha256,
                       metric_roster_sha256, opened_at,
                       inputs_acquired_at, completed_at, failed_at,
                       version
                FROM mra.evaluation_run WHERE evaluation_run_id = %s
                """,
                (evaluation_run_id,),
            ).fetchone()
            if run is None:
                return (_missing("evaluation_run", evaluation_run_id),)
            status = str(run[0])
            if status not in {"OPEN", "INPUTS_ACQUIRED", "COMPLETED", "FAILED"}:
                mismatches.append(
                    _state(
                        "evaluation_run.status",
                        "OPEN|INPUTS_ACQUIRED|COMPLETED|FAILED",
                        status,
                    )
                )
            self._inspect_protocol(
                connection,
                UUID(str(run[1])),
                int(run[6]),
                UUID(str(run[3])),
                str(run[4]),
                mismatches,
            )
            partition_count = connection.execute(
                """
                SELECT count(*) FROM mra.research_partition_member
                WHERE research_partition_id = %s
                """,
                (run[2],),
            ).fetchone()
            assert partition_count is not None
            _compare_count(
                mismatches,
                "evaluation_run.expected_member_count",
                int(run[5]),
                int(partition_count[0]),
            )
            accesses = connection.execute(
                """
                SELECT access.research_partition_member_id,
                       access.research_partition_outcome_access_id,
                       access.market_target_outcome_revision_id,
                       access.access_ordinal,
                       access.commitment_id, access.target_definition_id,
                       access.knowledge_cutoff, access.observation_cutoff,
                       access.settled_at, access.content_sha256,
                       access.outcome_status
                FROM mra.research_partition_outcome_access AS access
                JOIN mra.research_partition_member AS member
                  ON member.research_partition_member_id =
                     access.research_partition_member_id
                WHERE access.evaluation_run_id = %s
                ORDER BY member.member_ordinal
                """,
                (evaluation_run_id,),
            ).fetchall()
            observations = connection.execute(
                """
                SELECT research_partition_member_id, outcome_access_id,
                       market_target_outcome_revision_id,
                       candidate_disposition, outcome_status, content_sha256
                FROM mra.evaluation_observation
                WHERE evaluation_run_id = %s
                ORDER BY research_partition_member_id
                """,
                (evaluation_run_id,),
            ).fetchall()
            _compare_count(
                mismatches, "evaluation_run.access_count", int(run[7]), len(accesses)
            )
            _compare_count(
                mismatches,
                "evaluation_run.observation_count",
                int(run[8]),
                len(observations),
            )
            expected_observations = {
                (row[0], row[1], row[2]) for row in accesses
            }
            actual_observations = {tuple(row[:3]) for row in observations}
            if expected_observations != actual_observations:
                mismatches.append(
                    _identity(
                        "evaluation_run.observation_roster",
                        str(len(expected_observations)),
                        str(len(actual_observations)),
                    )
                )
            invalid_access_hashes = sum(
                str(row[9])
                != canonical_json_sha256(
                    {
                        "access_ordinal": int(row[3]),
                        "evaluation_run_id": evaluation_run_id,
                        "member_id": UUID(str(row[0])),
                        "revision_id": UUID(str(row[2])),
                    }
                )
                for row in accesses
            )
            invalid_observation_hashes = sum(
                str(row[5])
                != canonical_json_sha256(
                    {
                        "access_id": UUID(str(row[1])),
                        "candidate_disposition": str(row[3]),
                        "outcome_status": str(row[4]),
                    }
                )
                for row in observations
            )
            if invalid_access_hashes:
                mismatches.append(
                    _compare_content_count(
                        "evaluation_run.access_content_sha256",
                        invalid_access_hashes,
                    )
                )
            if invalid_observation_hashes:
                mismatches.append(
                    _compare_content_count(
                        "evaluation_run.observation_content_sha256",
                        invalid_observation_hashes,
                    )
                )
            if accesses:
                actual_input_hash = canonical_json_sha256(
                    tuple((row[0], row[1], row[2], int(row[3])) for row in accesses)
                )
                _compare_hash(
                    mismatches,
                    "evaluation_run.input_roster_sha256",
                    str(run[11]),
                    actual_input_hash,
                )
            ordinal_breaks = connection.execute(
                """
                SELECT count(*) FROM (
                    SELECT access_ordinal,
                           row_number() OVER (
                               PARTITION BY research_partition_member_id
                               ORDER BY access_ordinal
                           ) AS expected_ordinal
                    FROM mra.research_partition_outcome_access
                    WHERE research_partition_member_id IN (
                        SELECT research_partition_member_id
                        FROM mra.research_partition_member
                        WHERE research_partition_id = %s
                    )
                ) AS chain
                WHERE access_ordinal <> expected_ordinal
                """,
                (run[2],),
            ).fetchone()
            assert ordinal_breaks is not None
            if int(ordinal_breaks[0]):
                mismatches.append(
                    _order(
                        "evaluation_run.global_access_ordinals",
                        "1..N per PartitionMember",
                        str(ordinal_breaks[0]),
                    )
                )
            invalid_accesses = connection.execute(
                """
                SELECT count(*)
                FROM mra.research_partition_outcome_access AS access
                JOIN mra.market_target_outcome_revision AS revision
                  ON revision.market_target_outcome_revision_id =
                     access.market_target_outcome_revision_id
                JOIN mra.evaluation_run AS run
                  ON run.evaluation_run_id = access.evaluation_run_id
                WHERE access.evaluation_run_id = %s
                  AND (revision.commitment_id <> access.commitment_id
                    OR revision.target_definition_id <> access.target_definition_id
                    OR revision.knowledge_cutoff <> access.knowledge_cutoff
                    OR revision.observation_cutoff <> access.observation_cutoff
                    OR revision.settled_at <> access.settled_at
                    OR revision.knowledge_cutoff > run.requested_knowledge_cutoff
                    OR revision.observation_cutoff > run.requested_knowledge_cutoff
                    OR revision.settled_at > run.requested_knowledge_cutoff
                    OR EXISTS (
                        SELECT 1
                        FROM mra.market_target_outcome_revision AS successor
                        WHERE successor.supersedes_revision_id =
                              revision.market_target_outcome_revision_id
                          AND successor.commitment_id = revision.commitment_id
                          AND successor.target_definition_id =
                              revision.target_definition_id
                          AND successor.knowledge_cutoff <=
                              run.requested_knowledge_cutoff
                          AND successor.observation_cutoff <=
                              run.requested_knowledge_cutoff
                          AND successor.settled_at <=
                              run.requested_knowledge_cutoff
                    ))
                """,
                (evaluation_run_id,),
            ).fetchone()
            assert invalid_accesses is not None
            if int(invalid_accesses[0]):
                mismatches.append(
                    _identity(
                        "evaluation_run.outcome_revisions",
                        "exact unique cutoff-visible leaf revisions",
                        str(invalid_accesses[0]),
                    )
                )
            metrics = connection.execute(
                """
                SELECT metric.evaluation_metric_id, metric.content_sha256
                FROM mra.evaluation_metric AS metric
                JOIN mra.evaluation_protocol_metric AS protocol_metric
                  ON protocol_metric.evaluation_protocol_metric_id =
                     metric.evaluation_protocol_metric_id
                WHERE metric.evaluation_run_id = %s
                ORDER BY protocol_metric.ordinal
                """,
                (evaluation_run_id,),
            ).fetchall()
            metric_inputs = connection.execute(
                """
                SELECT count(*)
                FROM mra.evaluation_metric_observation
                WHERE evaluation_run_id = %s
                """,
                (evaluation_run_id,),
            ).fetchone()
            assert metric_inputs is not None
            _compare_count(
                mismatches, "evaluation_run.metric_count", int(run[9]), len(metrics)
            )
            _compare_count(
                mismatches,
                "evaluation_run.metric_observation_count",
                int(run[10]),
                int(metric_inputs[0]),
            )
            if metrics:
                actual_metric_hash = canonical_json_sha256(
                    tuple((UUID(str(row[0])), str(row[1])) for row in metrics)
                )
                _compare_hash(
                    mismatches,
                    "evaluation_run.metric_roster_sha256",
                    str(run[12]),
                    actual_metric_hash,
                )
            if status == "COMPLETED":
                cartesian_difference = connection.execute(
                    """
                    WITH expected AS (
                        SELECT metric.evaluation_protocol_metric_id,
                               observation.evaluation_observation_id
                        FROM mra.evaluation_protocol_metric AS metric
                        CROSS JOIN mra.evaluation_observation AS observation
                        WHERE metric.evaluation_protocol_id = %s
                          AND observation.evaluation_run_id = %s
                    ), actual AS (
                        SELECT evaluation_protocol_metric_id,
                               evaluation_observation_id
                        FROM mra.evaluation_metric_observation
                        WHERE evaluation_run_id = %s
                    )
                    SELECT count(*) FROM (
                        (SELECT * FROM expected EXCEPT SELECT * FROM actual)
                        UNION ALL
                        (SELECT * FROM actual EXCEPT SELECT * FROM expected)
                    ) AS difference
                    """,
                    (run[1], evaluation_run_id, evaluation_run_id),
                ).fetchone()
                assert cartesian_difference is not None
                if int(cartesian_difference[0]):
                    mismatches.append(
                        _identity(
                            "evaluation_run.metric_member_cartesian",
                            "complete protocol metric x member roster",
                            str(cartesian_difference[0]),
                        )
                    )
                canonical_source_difference = connection.execute(
                    """
                    SELECT count(*)
                    FROM mra.evaluation_protocol_metric AS metric
                    WHERE metric.evaluation_protocol_id = %s
                      AND (
                        ((metric.slice_kind = 'EXPLORATORY_BACKTEST_ARM'
                          OR metric.source_kind <> 'OUTCOME_METRIC')
                         AND (SELECT count(*)
                              FROM mra.evaluation_backtest_arm_source AS source
                              WHERE source.evaluation_run_id = %s
                                AND source.evaluation_protocol_metric_id =
                                    metric.evaluation_protocol_metric_id)
                             <> %s)
                        OR (metric.source_kind = 'CANDIDATE_DISPOSITION'
                            AND (SELECT count(*) FROM mra.evaluation_candidate_source AS source
                                 WHERE source.evaluation_run_id = %s
                                   AND source.evaluation_protocol_metric_id = metric.evaluation_protocol_metric_id) <> %s)
                        OR (metric.source_kind = 'SIGNAL_STATUS'
                            AND (SELECT count(*) FROM mra.evaluation_signal_source AS source
                                 WHERE source.evaluation_run_id = %s
                                   AND source.evaluation_protocol_metric_id = metric.evaluation_protocol_metric_id) <> %s)
                        OR (metric.source_kind = 'FORECAST_OUTCOME_PAIR'
                            AND (SELECT count(*) FROM mra.evaluation_forecast_source AS source
                                 WHERE source.evaluation_run_id = %s
                                   AND source.evaluation_protocol_metric_id = metric.evaluation_protocol_metric_id) <> %s)
                        OR (metric.source_kind IN ('PORTFOLIO_LINE', 'PORTFOLIO_OUTCOME')
                            AND (SELECT count(*) FROM mra.evaluation_portfolio_source AS source
                                 WHERE source.evaluation_run_id = %s
                                   AND source.evaluation_protocol_metric_id = metric.evaluation_protocol_metric_id) <> %s)
                        OR (metric.source_kind = 'RISK_DECISION'
                            AND (SELECT count(*) FROM mra.evaluation_risk_source AS source
                                 WHERE source.evaluation_run_id = %s
                                   AND source.evaluation_protocol_metric_id = metric.evaluation_protocol_metric_id) <> %s)
                      )
                    """,
                    (
                        run[1],
                        evaluation_run_id, int(run[5]),
                        evaluation_run_id, int(run[5]),
                        evaluation_run_id, int(run[5]),
                        evaluation_run_id, int(run[5]),
                        evaluation_run_id, int(run[5]),
                        evaluation_run_id, int(run[5]),
                    ),
                ).fetchone()
                assert canonical_source_difference is not None
                if int(canonical_source_difference[0]):
                    mismatches.append(
                        _identity(
                            "evaluation_run.canonical_source_rosters",
                            "complete typed source roster for every metric",
                            str(canonical_source_difference[0]),
                        )
                    )
            self._inspect_lifecycle(run, mismatches)
            required_commands = ["OPEN_EVALUATION_RUN"]
            if status in {"INPUTS_ACQUIRED", "COMPLETED"}:
                required_commands.append("ACQUIRE_OUTCOME_INPUTS")
            if status == "COMPLETED":
                required_commands.append("COMPLETE_EVALUATION_RUN")
            if status == "FAILED":
                required_commands.append("FAIL_EVALUATION_RUN")
            self._inspect_provenance(
                connection,
                aggregate_kind="EVALUATION_RUN",
                aggregate_id=evaluation_run_id,
                required_commands=tuple(required_commands),
                mismatches=mismatches,
            )
        return tuple(mismatches)

    @staticmethod
    def _inspect_target_contract(
        connection: psycopg.Connection[Any],
        target_id: UUID,
        target_version: int,
        target_hash: str,
        mismatches: list[Mismatch],
    ) -> None:
        facts = connection.execute(
            """
            SELECT
              EXISTS (
                SELECT 1 FROM mra.target_definition
                WHERE target_definition_id = %s
                  AND version = %s AND content_sha256 = %s
                  AND registration_status = 'REGISTERED'
              ),
              count(*) FILTER (WHERE metric.completion_rule = 'REQUIRED'),
              count(*) FILTER (WHERE
                  (metric.metric_kind = 'SIMPLE_RETURN'
                   AND NOT (dependency.reference_count = 1
                            AND dependency.observation_count = 1
                            AND dependency.path_count = 0))
               OR (metric.metric_kind = 'OBSERVATION_VALUE'
                   AND NOT (dependency.reference_count = 0
                            AND dependency.observation_count = 1
                            AND dependency.path_count = 0))
               OR (metric.metric_kind IN (
                       'MAX_FAVORABLE_EXCURSION',
                       'MAX_ADVERSE_EXCURSION', 'BARRIER_HIT'
                   ) AND NOT (dependency.reference_count = 1
                              AND dependency.observation_count = 0
                              AND dependency.path_count >= 1)))
            FROM mra.target_metric_definition AS metric
            CROSS JOIN LATERAL (
                SELECT
                  count(*) FILTER (WHERE dependency_role = 'REFERENCE')
                      AS reference_count,
                  count(*) FILTER (WHERE dependency_role = 'OBSERVATION')
                      AS observation_count,
                  count(*) FILTER (WHERE dependency_role = 'PATH_MEMBER')
                      AS path_count
                FROM mra.target_metric_dependency
                WHERE target_metric_definition_id =
                      metric.target_metric_definition_id
            ) AS dependency
            WHERE metric.target_definition_id = %s
            """,
            (target_id, target_version, target_hash, target_id),
        ).fetchone()
        assert facts is not None
        if not bool(facts[0]):
            mismatches.append(
                _identity(
                    "target.exact_registered_definition",
                    f"{target_id}@{target_version}:{target_hash}",
                    "absent",
                )
            )
        if int(facts[1]) < 1:
            mismatches.append(
                _state("target.required_metrics", ">=1", str(facts[1]))
            )
        if int(facts[2]):
            mismatches.append(
                _identity(
                    "target.outcome_dependency_contract",
                    "all metric dependency shapes canonical",
                    str(facts[2]),
                )
            )

    @staticmethod
    def _inspect_protocol(
        connection: psycopg.Connection[Any],
        protocol_id: UUID,
        expected_count: int,
        target_id: UUID,
        purpose: str,
        mismatches: list[Mismatch],
    ) -> None:
        root = connection.execute(
            """
            SELECT target_definition_id, applicable_purpose,
                   metric_count, metric_roster_sha256, status
            FROM mra.evaluation_protocol
            WHERE evaluation_protocol_id = %s
            """,
            (protocol_id,),
        ).fetchone()
        if root is None:
            mismatches.append(_missing("evaluation_protocol", protocol_id))
            return
        if (UUID(str(root[0])), str(root[1]), str(root[4])) != (
            target_id,
            purpose,
            "FROZEN",
        ):
            mismatches.append(
                _identity(
                    "evaluation_protocol.binding",
                    str((target_id, purpose, "FROZEN")),
                    str((root[0], root[1], root[4])),
                )
            )
        rows = connection.execute(
            """
            SELECT evaluation_protocol_metric_id, metric_code, ordinal,
                   source_target_metric_definition_id, source_metric_code,
                   source_value_type, source_kind, source_measure,
                   reducer, slice_kind, candidate_disposition,
                   backtest_arm_kind, direction,
                   minimum_estimable_count, acceptance_operator,
                   acceptance_threshold, inclusion_policy,
                   missingness_policy
            FROM mra.evaluation_protocol_metric
            WHERE evaluation_protocol_id = %s ORDER BY ordinal
            """,
            (protocol_id,),
        ).fetchall()
        metrics = tuple(_protocol_metric(row) for row in rows)
        _inspect_order(
            mismatches,
            "evaluation_protocol.metric_ordinals",
            tuple(metric.ordinal for metric in metrics),
        )
        _compare_count(
            mismatches,
            "evaluation_protocol.metric_count",
            int(root[2]),
            len(metrics),
        )
        _compare_count(
            mismatches,
            "evaluation_run.expected_protocol_metric_count",
            expected_count,
            len(metrics),
        )
        _compare_hash(
            mismatches,
            "evaluation_protocol.metric_roster_sha256",
            str(root[3]),
            canonical_json_sha256(metrics),
        )

    @staticmethod
    def _inspect_lifecycle(run: tuple[Any, ...], mismatches: list[Mismatch]) -> None:
        status = str(run[0])
        acquired, completed, failed, version = run[14], run[15], run[16], int(run[17])
        valid = {
            "OPEN": acquired is None and completed is None and failed is None and version == 1,
            "INPUTS_ACQUIRED": acquired is not None and completed is None and failed is None and version == 2,
            "COMPLETED": acquired is not None and completed is not None and failed is None and version == 3,
            "FAILED": failed is not None and completed is None and version in {2, 3},
        }.get(status, False)
        if not valid:
            mismatches.append(
                _state(
                    "evaluation_run.lifecycle",
                    "canonical timestamp/version shape",
                    str((status, acquired, completed, failed, version)),
                )
            )

    @staticmethod
    def _inspect_provenance(
        connection: psycopg.Connection[Any],
        *,
        aggregate_kind: str,
        aggregate_id: UUID,
        required_commands: tuple[str, ...],
        mismatches: list[Mismatch],
    ) -> None:
        rows = connection.execute(
            """
            SELECT receipt.command_kind, receipt.status,
                   count(audit.audit_event_id),
                   bool_and(
                       (receipt.runtime_step_id IS NULL
                        AND receipt.runtime_attempt_id IS NULL
                        AND receipt.fence_token IS NULL
                        AND audit.runtime_step_id IS NULL
                        AND audit.fence_token IS NULL)
                       OR
                       (receipt.runtime_step_id IS NOT NULL
                        AND receipt.runtime_attempt_id IS NOT NULL
                        AND receipt.fence_token > 0
                        AND audit.runtime_step_id = receipt.runtime_step_id
                        AND audit.fence_token = receipt.fence_token)
                   ) AS provenance_matches
            FROM mra.command_receipt AS receipt
            LEFT JOIN mra.audit_event AS audit
              ON audit.command_receipt_id = receipt.receipt_id
             AND audit.aggregate_kind = receipt.result_aggregate_kind
             AND audit.aggregate_id = receipt.result_aggregate_id
            WHERE receipt.result_aggregate_kind = %s
              AND receipt.result_aggregate_id = %s
              AND receipt.command_kind = ANY(%s::text[])
            GROUP BY receipt.receipt_id, receipt.command_kind, receipt.status
            """,
            (aggregate_kind, str(aggregate_id), list(required_commands)),
        ).fetchall()
        by_command = {str(row[0]): row for row in rows}
        for command in required_commands:
            row = by_command.get(command)
            if row is None:
                mismatches.append(
                    Mismatch(
                        Kind.PROVENANCE_MISMATCH,
                        f"provenance.{command}",
                        "one SUCCEEDED receipt with one matching audit",
                        "absent",
                    )
                )
            elif str(row[1]) != "SUCCEEDED" or int(row[2]) != 1 or not bool(row[3]):
                mismatches.append(
                    Mismatch(
                        Kind.PROVENANCE_MISMATCH,
                        f"provenance.{command}",
                        "SUCCEEDED/audit/runtime provenance exact",
                        str(tuple(row[1:])),
                    )
                )


def _protocol_metric(row: tuple[Any, ...]) -> ProtocolMetricDefinition:
    return ProtocolMetricDefinition(
        evaluation_protocol_metric_id=UUID(str(row[0])),
        metric_code=str(row[1]),
        ordinal=int(row[2]),
        source_target_metric_definition_id=UUID(str(row[3])),
        source_metric_code=str(row[4]),
        source_value_type=SourceMetricValueType(str(row[5])),
        source_kind=EvaluationSourceKind(str(row[6])),
        source_measure=EvaluationSourceMeasure(str(row[7])),
        reducer=EvaluationReducer(str(row[8])),
        slice_kind=EvaluationSliceKind(str(row[9])),
        candidate_disposition=(
            CandidateDisposition(str(row[10])) if row[10] is not None else None
        ),
        backtest_arm_kind=(
            ExploratoryBacktestArmKind(str(row[11]))
            if row[11] is not None
            else None
        ),
        direction=MetricDirection(str(row[12])),
        minimum_estimable_count=int(row[13]),
        acceptance_operator=AcceptanceOperator(str(row[14])),
        acceptance_threshold=row[15],
        inclusion_policy=EvaluationInclusionPolicy(str(row[16])),
        missingness_policy=EvaluationMissingnessPolicy(str(row[17])),
    )


def _missing(path: str, identity: UUID) -> Mismatch:
    return Mismatch(Kind.MISSING_ROW, path, str(identity), "absent")


def _state(path: str, expected: str, actual: str) -> Mismatch:
    return Mismatch(Kind.STATE_MISMATCH, path, expected, actual)


def _identity(path: str, expected: str, actual: str) -> Mismatch:
    return Mismatch(Kind.IDENTITY_MISMATCH, path, expected, actual)


def _order(path: str, expected: str, actual: str) -> Mismatch:
    return Mismatch(Kind.ORDER_MISMATCH, path, expected, actual)


def _compare_count(
    mismatches: list[Mismatch], path: str, expected: int, actual: int
) -> None:
    if expected != actual:
        mismatches.append(Mismatch(Kind.COUNT_MISMATCH, path, str(expected), str(actual)))


def _compare_hash(
    mismatches: list[Mismatch], path: str, expected: str, actual: str
) -> None:
    if expected != actual:
        mismatches.append(Mismatch(Kind.HASH_MISMATCH, path, expected, actual))


def _compare_content_count(path: str, invalid_count: int) -> Mismatch:
    return Mismatch(Kind.HASH_MISMATCH, path, "0 invalid rows", str(invalid_count))


def _inspect_order(
    mismatches: list[Mismatch], path: str, ordinals: tuple[int, ...]
) -> None:
    expected = tuple(range(1, len(ordinals) + 1))
    if ordinals != expected:
        mismatches.append(_order(path, str(expected), str(ordinals)))


__all__ = ["PostgresResearchEvaluationVerificationProvider"]
