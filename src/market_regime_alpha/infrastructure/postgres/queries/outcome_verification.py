"""Read-only relational replay checks for Market Target Outcome."""

from __future__ import annotations

from uuid import UUID

from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from market_regime_alpha.infrastructure.postgres.repositories.outcomes import (
    PostgresOutcomeRepository,
)
from market_regime_alpha.outcome.domain import OutcomeMismatch, OutcomeMismatchKind


class PostgresOutcomeVerificationProvider:
    def __init__(self, pool: TargetPostgresPool) -> None:
        self._pool = pool

    def inspect(self, revision_id: UUID) -> tuple[OutcomeMismatch, ...]:
        mismatches: list[OutcomeMismatch] = []
        with self._pool.connection(read_only=True) as connection:
            root = connection.execute(
                """
                SELECT revision.market_target_outcome_id,
                       revision.revision_ordinal,
                       revision.supersedes_revision_id,
                       revision.commitment_id,
                       revision.decision_reference_observation_id,
                       revision.observation_cutoff,
                       revision.knowledge_cutoff,
                       revision.runtime_run_id, revision.runtime_step_id,
                       revision.runtime_attempt_id,
                       revision.runtime_fence_token,
                       revision.command_receipt_id,
                       revision.source_count,
                       revision.observation_count,
                       revision.metric_count,
                       revision.reference_dependency_count,
                       revision.observation_dependency_count,
                       revision.reason_count,
                       revision.source_roster_sha256,
                       revision.observation_roster_sha256,
                       revision.metric_roster_sha256,
                       revision.reference_dependency_roster_sha256,
                       revision.observation_dependency_roster_sha256,
                       revision.reason_roster_sha256
                FROM mra.market_target_outcome_revision AS revision
                WHERE revision.market_target_outcome_revision_id = %s
                """,
                (revision_id,),
            ).fetchone()
            if root is None:
                return (
                    OutcomeMismatch(
                        kind=OutcomeMismatchKind.MISSING_ROW,
                        path="market_target_outcome_revision",
                        expected=str(revision_id),
                        actual="absent",
                    ),
                )
            outcome_id = UUID(str(root[0]))
            reconciliation = PostgresOutcomeRepository(connection).reconcile(
                revision_id,
                lock=False,
            )
            actual_counts = (
                reconciliation.source_count,
                reconciliation.observation_count,
                reconciliation.metric_count,
                reconciliation.reference_dependency_count,
                reconciliation.observation_dependency_count,
                reconciliation.reason_count,
            )
            stored_counts = tuple(int(value) for value in root[12:18])
            actual_hashes = (
                reconciliation.source_roster_sha256,
                reconciliation.observation_roster_sha256,
                reconciliation.metric_roster_sha256,
                reconciliation.reference_dependency_roster_sha256,
                reconciliation.observation_dependency_roster_sha256,
                reconciliation.reason_roster_sha256,
            )
            stored_hashes = tuple(str(value) for value in root[18:24])
            roster_names = (
                "source",
                "observation",
                "metric",
                "reference_dependency",
                "observation_dependency",
                "reason",
            )
            for name, actual_count, stored_count, actual_hash, stored_hash in zip(
                roster_names,
                actual_counts,
                stored_counts,
                actual_hashes,
                stored_hashes,
                strict=True,
            ):
                if actual_count != stored_count:
                    mismatches.extend(
                        (
                            OutcomeMismatch(
                                kind=OutcomeMismatchKind.COUNT_MISMATCH,
                                path=f"revision.{name}_count",
                                expected=str(stored_count),
                                actual=str(actual_count),
                            ),
                            OutcomeMismatch(
                                kind=(
                                    OutcomeMismatchKind.MISSING_ROW
                                    if actual_count < stored_count
                                    else OutcomeMismatchKind.EXTRA_ROW
                                ),
                                path=f"revision.{name}_roster",
                                expected=str(stored_count),
                                actual=str(actual_count),
                            ),
                        )
                    )
                if actual_hash != stored_hash:
                    mismatches.append(
                        OutcomeMismatch(
                            kind=OutcomeMismatchKind.HASH_MISMATCH,
                            path=f"revision.{name}_roster_sha256",
                            expected=stored_hash,
                            actual=actual_hash,
                        )
                    )
            ordinal_rows = connection.execute(
                """
                SELECT 'source', count(*), count(DISTINCT source_ordinal),
                       min(source_ordinal), max(source_ordinal)
                FROM mra.market_target_outcome_source
                WHERE market_target_outcome_revision_id = %(revision_id)s
                UNION ALL
                SELECT 'observation', count(*),
                       count(DISTINCT observation_ordinal),
                       min(observation_ordinal), max(observation_ordinal)
                FROM mra.market_target_outcome_observation
                WHERE market_target_outcome_revision_id = %(revision_id)s
                UNION ALL
                SELECT 'metric', count(*), count(DISTINCT metric_ordinal),
                       min(metric_ordinal), max(metric_ordinal)
                FROM mra.market_target_outcome_metric
                WHERE market_target_outcome_revision_id = %(revision_id)s
                UNION ALL
                SELECT 'reason', count(*), count(DISTINCT reason_ordinal),
                       min(reason_ordinal), max(reason_ordinal)
                FROM mra.market_target_outcome_reason
                WHERE market_target_outcome_revision_id = %(revision_id)s
                """,
                {"revision_id": revision_id},
            ).fetchall()
            for name, count, distinct_count, minimum, maximum in ordinal_rows:
                size = int(count)
                if size and (
                    int(distinct_count) != size
                    or int(minimum) != 1
                    or int(maximum) != size
                ):
                    mismatches.append(
                        OutcomeMismatch(
                            kind=OutcomeMismatchKind.ORDER_MISMATCH,
                            path=f"revision.{name}_ordinals",
                            expected=f"1..{size}",
                            actual=(
                                f"min={minimum},max={maximum},"
                                f"distinct={distinct_count}"
                            ),
                        )
                    )
            dependency_orders = connection.execute(
                """
                SELECT
                  (SELECT array_agg(dependency_ordinal ORDER BY dependency_ordinal)
                   FROM mra.market_target_outcome_metric_reference
                   WHERE market_target_outcome_revision_id = %(revision_id)s),
                  (SELECT array_agg(dependency.ordinal ORDER BY dependency.ordinal)
                   FROM mra.target_metric_dependency AS dependency
                   JOIN mra.market_target_outcome_revision AS revision
                     ON revision.target_definition_id =
                        dependency.target_definition_id
                   WHERE revision.market_target_outcome_revision_id =
                         %(revision_id)s
                     AND dependency.dependency_role = 'REFERENCE'),
                  (SELECT array_agg(dependency_ordinal ORDER BY dependency_ordinal)
                   FROM mra.market_target_outcome_metric_observation
                   WHERE market_target_outcome_revision_id = %(revision_id)s),
                  (SELECT array_agg(dependency.ordinal ORDER BY dependency.ordinal)
                   FROM mra.target_metric_dependency AS dependency
                   JOIN mra.market_target_outcome_revision AS revision
                     ON revision.target_definition_id =
                        dependency.target_definition_id
                   WHERE revision.market_target_outcome_revision_id =
                         %(revision_id)s
                     AND dependency.dependency_role IN (
                         'OBSERVATION', 'PATH_MEMBER'
                     ))
                """,
                {"revision_id": revision_id},
            ).fetchone()
            assert dependency_orders is not None
            for name, actual, expected in (
                (
                    "reference_dependency",
                    dependency_orders[0],
                    dependency_orders[1],
                ),
                (
                    "observation_dependency",
                    dependency_orders[2],
                    dependency_orders[3],
                ),
            ):
                if actual != expected:
                    mismatches.append(
                        OutcomeMismatch(
                            kind=OutcomeMismatchKind.ORDER_MISMATCH,
                            path=f"revision.{name}_ordinals",
                            expected=str(expected or []),
                            actual=str(actual or []),
                        )
                    )
            chain = connection.execute(
                """
                SELECT count(*), min(revision_ordinal), max(revision_ordinal),
                       count(*) FILTER (
                           WHERE supersedes_revision_id IS NULL
                       ),
                       count(*) FILTER (
                           WHERE NOT EXISTS (
                               SELECT 1
                               FROM mra.market_target_outcome_revision AS next
                               WHERE next.supersedes_revision_id =
                                     item.market_target_outcome_revision_id
                           )
                       )
                FROM mra.market_target_outcome_revision AS item
                WHERE market_target_outcome_id = %s
                """,
                (outcome_id,),
            ).fetchone()
            assert chain is not None
            if (
                int(chain[1]) != 1
                or int(chain[2]) != int(chain[0])
                or int(chain[3]) != 1
                or int(chain[4]) != 1
            ):
                mismatches.append(
                    OutcomeMismatch(
                        kind=OutcomeMismatchKind.REVISION_CHAIN_MISMATCH,
                        path="outcome.revision_chain",
                        expected="contiguous single-root single-leaf chain",
                        actual=str(tuple(chain)),
                    )
                )
            violations = connection.execute(
                """
                SELECT
                  (SELECT count(*)
                   FROM mra.market_target_outcome_metric_reference AS dep
                   JOIN mra.market_target_outcome AS outcome
                     ON outcome.market_target_outcome_id =
                        dep.market_target_outcome_id
                   WHERE dep.market_target_outcome_revision_id = %(revision_id)s
                     AND dep.decision_reference_observation_id <>
                         outcome.decision_reference_observation_id),
                  (SELECT count(*)
                   FROM mra.market_target_outcome_metric_observation AS dep
                   JOIN mra.market_target_outcome_observation AS observation
                     ON observation.market_target_outcome_observation_id =
                        dep.market_target_outcome_observation_id
                   WHERE dep.market_target_outcome_revision_id = %(revision_id)s
                     AND observation.market_target_outcome_revision_id <>
                         dep.market_target_outcome_revision_id),
                  (SELECT count(*)
                   FROM mra.market_target_outcome_source
                   WHERE market_target_outcome_revision_id = %(revision_id)s
                     AND (known_at > knowledge_cutoff
                          OR session_known_at > knowledge_cutoff
                          OR (event_end IS NOT NULL
                              AND event_end > observation_cutoff))),
                  (SELECT count(*)
                   FROM mra.market_target_outcome_revision AS revision
                   JOIN mra.market_target_outcome AS outcome
                     ON outcome.market_target_outcome_id =
                        revision.market_target_outcome_id
                   WHERE revision.market_target_outcome_revision_id =
                         %(revision_id)s
                     AND (revision.commitment_id <> outcome.commitment_id
                          OR revision.decision_reference_observation_id <>
                             outcome.decision_reference_observation_id)),
                  (SELECT count(*)
                   FROM mra.market_target_outcome_revision AS revision
                   LEFT JOIN mra.runtime_run AS run
                     ON run.run_id = revision.runtime_run_id
                    AND run.runtime_mode = revision.runtime_mode
                    AND run.decision_time = revision.runtime_decision_time
                    AND run.code_sha = revision.runtime_code_sha
                    AND run.config_artifact_id =
                        revision.runtime_config_artifact_id
                    AND run.config_hash = revision.runtime_config_hash
                   LEFT JOIN mra.runtime_step AS step
                     ON step.step_id = revision.runtime_step_id
                    AND step.run_id = revision.runtime_run_id
                    AND step.step_key = revision.runtime_step_key
                    AND step.step_kind = revision.runtime_step_kind
                   LEFT JOIN mra.runtime_attempt AS attempt
                     ON attempt.attempt_id = revision.runtime_attempt_id
                    AND attempt.step_id = revision.runtime_step_id
                    AND attempt.fence_token = revision.runtime_fence_token
                   LEFT JOIN mra.command_receipt AS receipt
                     ON receipt.receipt_id = revision.command_receipt_id
                    AND receipt.status = 'SUCCEEDED'
                   WHERE revision.market_target_outcome_revision_id =
                         %(revision_id)s
                     AND (run.run_id IS NULL OR step.step_id IS NULL
                          OR attempt.attempt_id IS NULL
                          OR receipt.receipt_id IS NULL))
                """,
                {"revision_id": revision_id},
            ).fetchone()
            assert violations is not None
        kinds = (
            (
                OutcomeMismatchKind.REFERENCE_MISMATCH,
                "dependency.reference",
            ),
            (
                OutcomeMismatchKind.DEPENDENCY_MISMATCH,
                "dependency.observation_revision",
            ),
            (OutcomeMismatchKind.CUTOFF_MISMATCH, "source.cutoffs"),
            (OutcomeMismatchKind.IDENTITY_MISMATCH, "outcome.root_scope"),
            (
                OutcomeMismatchKind.RUNTIME_IDENTITY_MISMATCH,
                "revision.runtime_receipt",
            ),
        )
        mismatches.extend(
            OutcomeMismatch(
                kind=kind,
                path=path,
                expected="0 violations",
                actual=f"{int(count)} violations",
            )
            for (kind, path), count in zip(kinds, violations, strict=True)
            if int(count) != 0
        )
        return tuple(mismatches)


__all__ = ["PostgresOutcomeVerificationProvider"]
