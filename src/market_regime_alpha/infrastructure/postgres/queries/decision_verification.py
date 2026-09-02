"""Read-only typed replay and relational reconciliation for Decision Runs."""

from __future__ import annotations

from uuid import UUID

from market_regime_alpha.decision_support.domain import (
    DecisionRunMismatch,
    DecisionRunMismatchKind,
    DecisionRunVerification,
)
from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from market_regime_alpha.infrastructure.postgres.queries.decision_runs import (
    PostgresDecisionRunQueryProvider,
)
from market_regime_alpha.infrastructure.postgres.repositories.decision_runs import (
    PostgresDecisionRunRepository,
)


class PostgresDecisionRunVerificationProvider:
    """Rebuild frozen facts only; never resolves a Provider or latest value."""

    def __init__(self, pool: TargetPostgresPool) -> None:
        self._pool = pool
        self._queries = PostgresDecisionRunQueryProvider(pool)

    def verify(self, decision_run_id: UUID) -> DecisionRunVerification:
        typed_error: Exception | None = None
        try:
            self._queries.load(decision_run_id)
        except Exception as exc:  # diagnosis must report, never conceal, corruption
            typed_error = exc

        mismatches: list[DecisionRunMismatch] = []
        with self._pool.connection(read_only=True) as connection:
            root = connection.execute(
                """
                SELECT candidate_set_id, target_count, commitment_count,
                       reference_count, research_qualification_count,
                       research_qualification_roster_id
                FROM mra.decision_run
                WHERE decision_run_id = %s
                """,
                (decision_run_id,),
            ).fetchone()
            if root is None:
                return DecisionRunVerification(
                    decision_run_id=decision_run_id,
                    mismatches=(
                        DecisionRunMismatch(
                            kind=DecisionRunMismatchKind.MISSING_ROW,
                            fact_path="decision_run",
                            expected=str(decision_run_id),
                            actual="ABSENT",
                        ),
                    ),
                )
            reconciliation = PostgresDecisionRunRepository(connection).reconcile(
                decision_run_id,
                lock=False,
            )
            expected_counts = (
                int(root[1]),
                int(root[2]),
                int(root[3]),
                int(root[4]),
            )
            actual_counts = (
                reconciliation.actual_target_count,
                reconciliation.actual_commitment_count,
                reconciliation.actual_reference_count,
                reconciliation.actual_research_qualification_count,
            )
            if actual_counts != expected_counts:
                mismatches.append(
                    DecisionRunMismatch(
                        kind=DecisionRunMismatchKind.COUNT_MISMATCH,
                        fact_path="decision_run.roster_counts",
                        expected=str(expected_counts),
                        actual=str(actual_counts),
                    )
                )
            if any(a < e for a, e in zip(actual_counts, expected_counts, strict=True)):
                mismatches.append(
                    DecisionRunMismatch(
                        kind=DecisionRunMismatchKind.MISSING_ROW,
                        fact_path="decision_run.child_roster",
                        expected=str(expected_counts),
                        actual=str(actual_counts),
                    )
                )
            if any(a > e for a, e in zip(actual_counts, expected_counts, strict=True)):
                mismatches.append(
                    DecisionRunMismatch(
                        kind=DecisionRunMismatchKind.EXTRA_ROW,
                        fact_path="decision_run.child_roster",
                        expected=str(expected_counts),
                        actual=str(actual_counts),
                    )
                )
            if not reconciliation.matched and (
                reconciliation.candidate_roster_sha256,
                reconciliation.target_roster_sha256,
                reconciliation.commitment_roster_sha256,
                reconciliation.research_qualification_roster_sha256,
            ) != _stored_hashes(connection, decision_run_id):
                mismatches.append(
                    DecisionRunMismatch(
                        kind=DecisionRunMismatchKind.HASH_MISMATCH,
                        fact_path="decision_run.roster_hashes",
                        expected=str(_stored_hashes(connection, decision_run_id)),
                        actual=str(
                            (
                                reconciliation.candidate_roster_sha256,
                                reconciliation.target_roster_sha256,
                                reconciliation.commitment_roster_sha256,
                                reconciliation.research_qualification_roster_sha256,
                            )
                        ),
                    )
                )

            ordinals = tuple(
                int(row[0])
                for row in connection.execute(
                    """
                    SELECT ordinal
                    FROM mra.decision_run_target
                    WHERE decision_run_id = %s
                    ORDER BY ordinal
                    """,
                    (decision_run_id,),
                ).fetchall()
            )
            expected_ordinals = tuple(range(1, int(root[1]) + 1))
            if ordinals != expected_ordinals:
                mismatches.append(
                    DecisionRunMismatch(
                        kind=DecisionRunMismatchKind.ORDER_MISMATCH,
                        fact_path="decision_run_target.ordinal",
                        expected=str(expected_ordinals),
                        actual=str(ordinals),
                    )
                )

            qualification_ordinals = tuple(
                int(row[0])
                for row in connection.execute(
                    """
                    SELECT ordinal
                    FROM mra.decision_run_research_qualification_member
                    WHERE research_qualification_roster_id = %s
                    ORDER BY ordinal
                    """,
                    (UUID(str(root[5])),),
                ).fetchall()
            )
            expected_qualification_ordinals = tuple(
                range(1, int(root[4]) + 1)
            )
            if qualification_ordinals != expected_qualification_ordinals:
                mismatches.append(
                    DecisionRunMismatch(
                        kind=DecisionRunMismatchKind.ORDER_MISMATCH,
                        fact_path=(
                            "decision_run_research_qualification_member.ordinal"
                        ),
                        expected=str(expected_qualification_ordinals),
                        actual=str(qualification_ordinals),
                    )
                )

            identity_count = _scalar_count(
                connection,
                """
                    SELECT count(*)
                    FROM mra.decision_target_commitment AS commitment
                    LEFT JOIN mra.decision_run AS run
                      ON run.decision_run_id = commitment.decision_run_id
                    LEFT JOIN mra.candidate AS candidate
                      ON candidate.candidate_id = commitment.candidate_id
                     AND candidate.candidate_set_id =
                         commitment.candidate_set_id
                     AND candidate.instrument_id = commitment.instrument_id
                     AND candidate.disposition =
                         commitment.candidate_disposition
                    LEFT JOIN mra.decision_run_target AS target
                      ON target.decision_run_target_id =
                         commitment.decision_run_target_id
                     AND target.decision_run_id = commitment.decision_run_id
                     AND target.target_definition_id =
                         commitment.target_definition_id
                    WHERE commitment.decision_run_id = %s
                      AND (run.decision_run_id IS NULL
                           OR candidate.candidate_id IS NULL
                           OR target.decision_run_target_id IS NULL)
                """,
                (decision_run_id,),
            )
            if identity_count:
                mismatches.append(
                    DecisionRunMismatch(
                        kind=DecisionRunMismatchKind.IDENTITY_MISMATCH,
                        fact_path="decision_target_commitment.scope",
                        expected="0",
                        actual=str(identity_count),
                    )
                )

            qualification_identity_count = _scalar_count(
                connection,
                """
                    SELECT count(*)
                    FROM mra.decision_run_research_qualification_member AS member
                    JOIN mra.decision_run AS decision
                      ON decision.decision_run_id = member.decision_run_id
                     AND decision.research_qualification_roster_id =
                         member.research_qualification_roster_id
                     AND decision.research_purpose =
                         member.qualification_purpose
                     AND decision.decision_time = member.decision_time
                    LEFT JOIN mra.research_qualification_decision AS qualification
                      ON qualification.research_qualification_decision_id =
                         member.research_qualification_decision_id
                     AND qualification.decision_code = member.decision_code
                     AND qualification.revision = member.revision
                     AND qualification.research_assessment_id =
                         member.research_assessment_id
                     AND qualification.research_qualification_policy_id =
                         member.research_qualification_policy_id
                     AND qualification.experiment_id = member.experiment_id
                     AND qualification.target_definition_id =
                         member.target_definition_id
                     AND qualification.qualification_purpose =
                         member.qualification_purpose
                     AND qualification.decision_status = 'ADMITTED'
                     AND qualification.source_generation_max_decision_time =
                         member.source_generation_max_decision_time
                     AND qualification.effective_at = member.effective_at
                     AND qualification.known_at = member.known_at
                     AND qualification.content_sha256 =
                         member.qualification_content_sha256
                    LEFT JOIN mra.decision_run_target AS target
                      ON target.decision_run_id = member.decision_run_id
                     AND target.target_definition_id =
                         member.target_definition_id
                    WHERE member.decision_run_id = %s
                      AND (
                          qualification.research_qualification_decision_id IS NULL
                          OR target.decision_run_target_id IS NULL
                          OR EXISTS (
                              SELECT 1
                              FROM mra.research_qualification_decision AS successor
                              WHERE successor.supersedes_decision_id =
                                    member.research_qualification_decision_id
                                AND successor.effective_at <= member.decision_time
                                AND successor.known_at <= member.decision_time
                          )
                      )
                """,
                (decision_run_id,),
            )
            if qualification_identity_count:
                mismatches.append(
                    DecisionRunMismatch(
                        kind=DecisionRunMismatchKind.IDENTITY_MISMATCH,
                        fact_path="decision_run.research_qualification_roster",
                        expected="0",
                        actual=str(qualification_identity_count),
                    )
                )

            reference_count = _scalar_count(
                connection,
                """
                    SELECT count(*)
                    FROM mra.decision_reference_observation AS reference
                    LEFT JOIN mra.decision_target_commitment AS commitment
                      ON commitment.commitment_id = reference.commitment_id
                     AND commitment.decision_reference_observation_id =
                         reference.decision_reference_observation_id
                     AND commitment.decision_reference_sha256 =
                         reference.content_sha256
                    WHERE reference.decision_run_id = %s
                      AND (
                        commitment.commitment_id IS NULL
                        OR reference.known_at > reference.decision_time
                        OR reference.finality_status <> 'UNKNOWN'
                        OR (reference.source_kind = 'BAR_REVISION' AND (
                              reference.value_status <> 'PRESENT'
                              OR reference.availability_status <> 'AVAILABLE'
                              OR reference.bar_revision_id IS NULL
                              OR reference.source_gap_id IS NOT NULL
                        ))
                        OR (reference.source_kind = 'SOURCE_GAP' AND (
                              reference.source_gap_id IS NULL
                              OR reference.bar_revision_id IS NOT NULL
                        ))
                      )
                """,
                (decision_run_id,),
            )
            if reference_count:
                mismatches.append(
                    DecisionRunMismatch(
                        kind=DecisionRunMismatchKind.REFERENCE_STATE_MISMATCH,
                        fact_path="decision_reference_observation.state",
                        expected="0",
                        actual=str(reference_count),
                    )
                )

            runtime_count = _scalar_count(
                connection,
                """
                    SELECT count(*)
                    FROM mra.decision_run AS decision
                    LEFT JOIN mra.runtime_run AS run
                      ON run.run_id = decision.runtime_run_id
                     AND run.runtime_mode = decision.runtime_mode
                     AND run.decision_time = decision.decision_time
                     AND run.code_sha = decision.code_sha
                     AND run.config_artifact_id = decision.config_artifact_id
                     AND run.config_hash = decision.config_hash
                    LEFT JOIN mra.runtime_step AS step
                      ON step.step_id = decision.runtime_step_id
                     AND step.run_id = decision.runtime_run_id
                     AND step.step_key = decision.runtime_step_key
                     AND step.step_kind = decision.runtime_step_kind
                    LEFT JOIN mra.runtime_attempt AS attempt
                      ON attempt.attempt_id = decision.runtime_attempt_id
                     AND attempt.step_id = decision.runtime_step_id
                     AND attempt.fence_token = decision.runtime_fence_token
                    WHERE decision.decision_run_id = %s
                      AND (run.run_id IS NULL OR step.step_id IS NULL
                           OR attempt.attempt_id IS NULL)
                """,
                (decision_run_id,),
            )
            if runtime_count:
                mismatches.append(
                    DecisionRunMismatch(
                        kind=DecisionRunMismatchKind.RUNTIME_IDENTITY_MISMATCH,
                        fact_path="decision_run.runtime_identity",
                        expected="0",
                        actual=str(runtime_count),
                    )
                )

            mutation_count = _scalar_count(
                connection,
                """
                    SELECT
                      (SELECT count(*)
                       FROM mra.decision_run_target AS target
                       WHERE target.decision_run_id = %(decision_run_id)s
                         AND target.content_sha256 <>
                           mra.decision_run_target_content_sha256(
                             target.ordinal, target.reference_provider_id,
                             target.reference_provider_product_id,
                             target.reference_provider_product_revision,
                             target.target_checkpoint_id,
                             target.target_checkpoint_sha256,
                             target.target_definition_id,
                             target.target_definition_sha256,
                             target.target_version))
                      +
                      (SELECT count(*)
                       FROM mra.decision_target_commitment AS commitment
                       WHERE commitment.decision_run_id = %(decision_run_id)s
                         AND commitment.content_sha256 <>
                           mra.decision_commitment_content_sha256(
                             commitment.candidate_disposition,
                             commitment.candidate_id,
                             commitment.decision_reference_observation_id,
                             commitment.decision_reference_sha256,
                             commitment.decision_run_target_id,
                             commitment.instrument_id,
                             commitment.runtime_mode,
                             commitment.target_definition_id))
                      +
                      (SELECT count(*)
                       FROM mra.decision_reference_observation AS reference
                       WHERE reference.decision_run_id = %(decision_run_id)s
                         AND reference.content_sha256 <>
                           mra.decision_reference_content_sha256(
                             reference.availability_status,
                             reference.bar_revision,
                             reference.bar_revision_id,
                             reference.candidate_id, reference.capture_id,
                             reference.decimal_value,
                             reference.decision_run_target_id,
                             reference.event_end, reference.event_start,
                             reference.finality_status,
                             reference.instrument_id, reference.known_at,
                             reference.observation_time,
                             reference.price_basis,
                             reference.reference_provider_product_id,
                             reference.source_recorded_at,
                             reference.session_id, reference.source_gap_id,
                             reference.source_gap_kind,
                             reference.source_gap_reason_code,
                             reference.source_kind,
                             reference.target_checkpoint_id,
                             reference.timeframe, reference.value_field,
                             reference.value_status))
                      +
                      (SELECT count(*)
                       FROM mra.decision_run_research_qualification_member AS member
                       WHERE member.decision_run_id = %(decision_run_id)s
                         AND member.content_sha256 <>
                           mra.decision_qualification_member_content_sha256(
                             member.decision_code, member.experiment_id,
                             member.qualification_content_sha256,
                             member.qualification_purpose, member.revision,
                             member.research_assessment_id,
                             member.research_qualification_decision_id,
                             member.research_qualification_policy_id,
                             member.role,
                             member.source_generation_max_decision_time,
                             member.supersedes_decision_id,
                             member.target_definition_id))
                      +
                      (SELECT count(*)
                       FROM mra.decision_run AS decision
                       WHERE decision.decision_run_id = %(decision_run_id)s
                         AND decision.definition_summary_sha256 <>
                           mra.decision_run_definition_summary_sha256(
                             decision.candidate_count,
                             decision.candidate_roster_sha256,
                             decision.candidate_set_content_sha256,
                             decision.candidate_set_id,
                             decision.commitment_count,
                             decision.commitment_roster_sha256,
                             decision.decision_time,
                             decision.reference_count,
                             decision.research_purpose,
                             decision.research_qualification_count,
                             decision.research_qualification_roster_sha256,
                             decision.request_sha256,
                             decision.runtime_mode,
                             decision.target_count,
                             decision.target_roster_sha256))
                """,
                {"decision_run_id": decision_run_id},
            )
            if mutation_count:
                mismatches.append(
                    DecisionRunMismatch(
                        kind=DecisionRunMismatchKind.IMMUTABLE_FACT_MUTATION,
                        fact_path="decision_run.content_hashes",
                        expected="0",
                        actual=str(mutation_count),
                    )
                )

        if typed_error is not None and not mismatches:
            mismatches.append(
                DecisionRunMismatch(
                    kind=DecisionRunMismatchKind.IMMUTABLE_FACT_MUTATION,
                    fact_path="decision_run.typed_reconstruction",
                    expected="reconstructable",
                    actual=type(typed_error).__name__,
                )
            )
        return DecisionRunVerification(
            decision_run_id=decision_run_id,
            mismatches=tuple(mismatches),
        )


def _stored_hashes(
    connection, decision_run_id: UUID
) -> tuple[str, str, str, str]:
    row = connection.execute(
        """
        SELECT candidate_roster_sha256, target_roster_sha256,
               commitment_roster_sha256,
               research_qualification_roster_sha256
        FROM mra.decision_run
        WHERE decision_run_id = %s
        """,
        (decision_run_id,),
    ).fetchone()
    assert row is not None
    return str(row[0]), str(row[1]), str(row[2]), str(row[3])


def _scalar_count(connection, query: str, parameters) -> int:
    row = connection.execute(query, parameters).fetchone()
    if row is None:
        raise RuntimeError("Decision Run verification count query returned no row")
    return int(row[0])


__all__ = ["PostgresDecisionRunVerificationProvider"]
