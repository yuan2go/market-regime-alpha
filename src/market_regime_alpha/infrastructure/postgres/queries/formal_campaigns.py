"""Database-clock campaign discovery and mutation-free reconciliation."""

from __future__ import annotations

from uuid import UUID

from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from market_regime_alpha.infrastructure.postgres.queries.research_qualification_verification import (
    PostgresResearchQualificationVerificationProvider,
)
from market_regime_alpha.infrastructure.postgres.queries.research_verification import (
    PostgresResearchEvaluationVerificationProvider,
)
from market_regime_alpha.research_qualification.ports.formal_campaign_queries import (
    DueOutcomeMember,
    DueOutcomeState,
    FormalCampaignInspection,
    FormalCampaignVerification,
)
from market_regime_alpha.runtime.errors import RuntimeNotFoundError


class PostgresFormalCampaignQueryPort:
    def __init__(self, pool: TargetPostgresPool) -> None:
        self._pool = pool

    def discover_due_outcomes(
        self, formal_research_campaign_id: UUID
    ) -> tuple[DueOutcomeMember, ...]:
        with self._pool.connection(read_only=True) as connection:
            rows = connection.execute(
                """
                WITH database_clock AS (SELECT clock_timestamp() AS now_at)
                SELECT member.research_partition_member_id,
                       member.research_partition_id, member.commitment_id,
                       member.outcome_due_at, database_clock.now_at,
                       CASE
                         WHEN member.outcome_due_at > database_clock.now_at
                           THEN 'NOT_DUE'
                         WHEN root.market_target_outcome_id IS NULL
                           THEN 'MISSING'
                         WHEN count(revision.market_target_outcome_revision_id) = 0
                           THEN 'DUE'
                         ELSE 'SETTLED'
                       END AS due_state,
                       root.market_target_outcome_id,
                       count(revision.market_target_outcome_revision_id)
                FROM mra.formal_research_campaign_partition_binding AS binding
                JOIN mra.research_partition_member AS member
                  ON member.research_partition_id = binding.research_partition_id
                CROSS JOIN database_clock
                LEFT JOIN mra.market_target_outcome AS root
                  ON root.commitment_id = member.commitment_id
                 AND root.target_definition_id = member.target_definition_id
                LEFT JOIN mra.market_target_outcome_revision AS revision
                  ON revision.market_target_outcome_id = root.market_target_outcome_id
                WHERE binding.formal_research_campaign_id = %s
                  AND binding.purpose = 'PROSPECTIVE'
                GROUP BY member.research_partition_member_id,
                         member.research_partition_id, member.commitment_id,
                         member.outcome_due_at, database_clock.now_at,
                         root.market_target_outcome_id
                ORDER BY member.outcome_due_at, member.research_partition_member_id
                """,
                (formal_research_campaign_id,),
            ).fetchall()
        return tuple(
            DueOutcomeMember(
                research_partition_member_id=UUID(str(row[0])),
                research_partition_id=UUID(str(row[1])),
                commitment_id=UUID(str(row[2])),
                outcome_due_at=row[3],
                database_now=row[4],
                state=DueOutcomeState(str(row[5])),
                market_target_outcome_id=(
                    UUID(str(row[6])) if row[6] is not None else None
                ),
                terminal_revision_count=int(row[7]),
            )
            for row in rows
        )

    def inspect(
        self, formal_research_campaign_id: UUID
    ) -> FormalCampaignInspection:
        due = self.discover_due_outcomes(formal_research_campaign_id)
        with self._pool.connection(read_only=True) as connection:
            row = connection.execute(
                """
                SELECT campaign.campaign_code, campaign.revision,
                       campaign.campaign_class,
                       CASE WHEN protected.formal_research_campaign_id IS NOT NULL
                            THEN 'PROTECTED_OPEN'
                            WHEN experiment.formal_research_campaign_id IS NOT NULL
                            THEN 'EXPERIMENT_BOUND'
                            WHEN provider.formal_research_campaign_id IS NOT NULL
                            THEN 'PROVIDER_BOUND'
                            ELSE 'PREDECLARED' END,
                       decision.decision_status,
                       campaign.partition_plan_count,
                       (SELECT count(*) FROM mra.formal_research_campaign_partition_binding b
                        WHERE b.formal_research_campaign_id = campaign.formal_research_campaign_id),
                       (SELECT count(*) FROM mra.research_partition_outcome_access access
                        JOIN mra.research_partition_member member
                          ON member.research_partition_member_id = access.research_partition_member_id
                        JOIN mra.formal_research_campaign_partition_binding b
                          ON b.research_partition_id = member.research_partition_id
                        WHERE b.formal_research_campaign_id = campaign.formal_research_campaign_id
                          AND access.access_ordinal = 1),
                       (SELECT count(*) FROM mra.evaluation_run run
                        JOIN mra.formal_research_campaign_partition_binding b
                          ON b.research_partition_id = run.research_partition_id
                        WHERE b.formal_research_campaign_id = campaign.formal_research_campaign_id
                          AND run.status IN ('OPEN', 'INPUTS_ACQUIRED')),
                       (SELECT count(*) FROM mra.evaluation_run run
                        JOIN mra.formal_research_campaign_partition_binding b
                          ON b.research_partition_id = run.research_partition_id
                        WHERE b.formal_research_campaign_id = campaign.formal_research_campaign_id
                          AND run.status IN ('COMPLETED', 'FAILED')),
                       (SELECT count(*) FROM mra.evidence_item evidence
                        JOIN mra.evaluation_run run ON run.evaluation_run_id = evidence.evaluation_run_id
                        WHERE experiment.experiment_id IS NOT NULL
                          AND run.experiment_id = experiment.experiment_id),
                       (SELECT count(*) FROM mra.research_assessment assessment
                        WHERE experiment.experiment_id IS NOT NULL
                          AND assessment.experiment_id = experiment.experiment_id),
                       (SELECT count(*) FROM mra.research_qualification_decision qualification
                        JOIN mra.research_assessment assessment
                          ON assessment.research_assessment_id = qualification.research_assessment_id
                        WHERE experiment.experiment_id IS NOT NULL
                          AND assessment.experiment_id = experiment.experiment_id)
                FROM mra.formal_research_campaign AS campaign
                LEFT JOIN mra.formal_research_campaign_provider_decision AS provider
                  ON provider.formal_research_campaign_id = campaign.formal_research_campaign_id
                LEFT JOIN mra.provider_qualification_decision AS decision
                  ON decision.provider_qualification_decision_id = provider.provider_qualification_decision_id
                LEFT JOIN mra.formal_research_campaign_experiment AS experiment
                  ON experiment.formal_research_campaign_id = campaign.formal_research_campaign_id
                LEFT JOIN mra.formal_research_campaign_protected_open AS protected
                  ON protected.formal_research_campaign_id = campaign.formal_research_campaign_id
                WHERE campaign.formal_research_campaign_id = %s
                """,
                (formal_research_campaign_id,),
            ).fetchone()
        if row is None:
            raise RuntimeNotFoundError("FormalResearchCampaign does not exist")
        due_count = sum(item.state is DueOutcomeState.DUE for item in due)
        missing_count = sum(item.state is DueOutcomeState.MISSING for item in due)
        settled_count = sum(item.state is DueOutcomeState.SETTLED for item in due)
        blockers: list[str] = []
        if row[4] != "ADMITTED":
            blockers.append("PROVIDER_NOT_ADMITTED")
        if int(row[6]) != int(row[5]):
            blockers.append("PARTITION_ROSTER_INCOMPLETE")
        if row[3] != "PROTECTED_OPEN":
            blockers.append("PROTECTED_CAMPAIGN_NOT_OPEN")
        if missing_count:
            blockers.append("DUE_OUTCOME_MISSING")
        return FormalCampaignInspection(
            formal_research_campaign_id=formal_research_campaign_id,
            campaign_code=str(row[0]), revision=int(row[1]),
            campaign_class=str(row[2]), state=str(row[3]),
            provider_decision_status=(str(row[4]) if row[4] is not None else None),
            planned_partition_count=int(row[5]), bound_partition_count=int(row[6]),
            first_access_count=int(row[7]), evaluation_open_count=int(row[8]),
            evaluation_terminal_count=int(row[9]), due_count=due_count,
            missing_count=missing_count, settled_count=settled_count,
            evidence_count=int(row[10]), assessment_count=int(row[11]),
            qualification_count=int(row[12]), blockers=tuple(blockers),
        )

    def verify(
        self, formal_research_campaign_id: UUID
    ) -> FormalCampaignVerification:
        mismatches: list[str] = []
        with self._pool.connection(read_only=True) as connection:
            row = connection.execute(
                """
                SELECT campaign.partition_plan_count, plans.item_count,
                       plans.minimum_ordinal, plans.maximum_ordinal,
                       campaign.partition_plan_roster_sha256 = plans.roster_sha256,
                       campaign.evaluation_protocol_count, protocols.item_count,
                       protocols.minimum_ordinal, protocols.maximum_ordinal,
                       campaign.evaluation_protocol_roster_sha256 = protocols.roster_sha256,
                       campaign.cost_assumption_count, costs.item_count,
                       costs.minimum_ordinal, costs.maximum_ordinal,
                       campaign.cost_assumption_roster_sha256 = costs.roster_sha256
                FROM mra.formal_research_campaign AS campaign
                CROSS JOIN LATERAL (
                    SELECT count(*)::integer AS item_count,
                           min(plan_ordinal) AS minimum_ordinal,
                           max(plan_ordinal) AS maximum_ordinal,
                           mra.canonical_sha256(mra.canonical_json_text(
                               json_agg(json_build_object(
                                   'content_sha256', content_sha256,
                                   'ordinal', plan_ordinal,
                                   'purpose', purpose,
                                   'research_partition_id', research_partition_id
                               ) ORDER BY plan_ordinal)::jsonb
                           )) AS roster_sha256
                    FROM mra.formal_research_campaign_partition_plan
                    WHERE formal_research_campaign_id = campaign.formal_research_campaign_id
                ) AS plans
                CROSS JOIN LATERAL (
                    SELECT count(*)::integer AS item_count,
                           min(binding_ordinal) AS minimum_ordinal,
                           max(binding_ordinal) AS maximum_ordinal,
                           mra.canonical_sha256(mra.canonical_json_text(
                               json_agg(json_build_object(
                                   'content_sha256', content_sha256,
                                   'ordinal', binding_ordinal,
                                   'purpose', purpose
                               ) ORDER BY binding_ordinal)::jsonb
                           )) AS roster_sha256
                    FROM mra.formal_research_campaign_evaluation_protocol
                    WHERE formal_research_campaign_id = campaign.formal_research_campaign_id
                ) AS protocols
                CROSS JOIN LATERAL (
                    SELECT count(*)::integer AS item_count,
                           min(assumption_ordinal) AS minimum_ordinal,
                           max(assumption_ordinal) AS maximum_ordinal,
                           mra.canonical_sha256(mra.canonical_json_text(
                               json_agg(json_build_object(
                                   'content_sha256', content_sha256,
                                   'cost_kind', cost_kind,
                                   'ordinal', assumption_ordinal
                               ) ORDER BY assumption_ordinal)::jsonb
                           )) AS roster_sha256
                    FROM mra.formal_research_campaign_cost_assumption
                    WHERE formal_research_campaign_id = campaign.formal_research_campaign_id
                ) AS costs
                WHERE campaign.formal_research_campaign_id = %s
                """,
                (formal_research_campaign_id,),
            ).fetchone()
            if row is None:
                mismatches.append("CAMPAIGN_ROSTER_MISSING")
            elif (
                int(row[0]) != int(row[1]) or int(row[2]) != 1
                or int(row[3]) != int(row[0])
                or row[4] is not True
                or int(row[5]) != int(row[6]) or int(row[7]) != 1
                or int(row[8]) != int(row[5]) or row[9] is not True
                or int(row[10]) != int(row[11]) or int(row[12]) != 1
                or int(row[13]) != int(row[10]) or row[14] is not True
            ):
                mismatches.append("CAMPAIGN_ROSTER_INCOMPLETE")
            drift = connection.execute(
                """
                SELECT count(*) FROM mra.formal_research_campaign_partition_binding b
                JOIN mra.formal_research_campaign_partition_plan p
                  ON p.formal_research_campaign_id = b.formal_research_campaign_id
                 AND p.plan_ordinal = b.binding_ordinal
                JOIN mra.research_partition r ON r.research_partition_id = b.research_partition_id
                WHERE b.formal_research_campaign_id = %s
                  AND (b.research_partition_id <> p.research_partition_id
                    OR b.purpose <> p.purpose OR r.purpose <> p.purpose
                    OR r.target_definition_id <> p.target_definition_id
                    OR r.exchange_code <> p.exchange_code
                    OR r.decision_start_session_id <> p.decision_start_session_id
                    OR r.decision_end_session_id <> p.decision_end_session_id)
                """,
                (formal_research_campaign_id,),
            ).fetchone()
            if drift is not None and int(drift[0]):
                mismatches.append("PARTITION_PLAN_DRIFT")
            authority_drift = connection.execute(
                """
                SELECT
                  EXISTS (
                    SELECT 1
                    FROM mra.formal_research_campaign_provider_decision b
                    JOIN mra.formal_research_campaign c USING (formal_research_campaign_id)
                    JOIN mra.provider_qualification_decision d
                      ON d.provider_qualification_decision_id = b.provider_qualification_decision_id
                    WHERE c.formal_research_campaign_id = %s
                      AND (d.provider_qualification_protocol_id <> c.provider_qualification_protocol_id
                        OR d.provider_product_id <> c.provider_product_id
                        OR d.protocol_content_sha256 <> c.provider_qualification_protocol_sha256
                        OR d.content_sha256 <> b.provider_qualification_decision_sha256
                        OR b.bound_at <= c.predeclared_at
                        OR (c.campaign_class = 'FORMAL_RESEARCH'
                            AND (d.evidence_class <> 'RECORDED_PROVIDER'
                                 OR d.decision_status <> 'ADMITTED'))
                        OR (c.campaign_class = 'ENGINEERING_REHEARSAL'
                            AND d.evidence_class <> 'ENGINEERING_REHEARSAL'))
                  ) AS provider_drift,
                  EXISTS (
                    SELECT 1
                    FROM mra.formal_research_campaign_experiment b
                    JOIN mra.formal_research_campaign c USING (formal_research_campaign_id)
                    JOIN mra.experiment e ON e.experiment_id = b.experiment_id
                    WHERE c.formal_research_campaign_id = %s
                      AND (e.experiment_code <> c.experiment_code
                        OR e.target_definition_id <> c.target_definition_id
                        OR e.target_version <> c.target_version
                        OR e.target_definition_sha256 <> c.target_definition_sha256
                        OR e.content_sha256 <> b.experiment_content_sha256
                        OR e.partition_count <> b.partition_count
                        OR e.partition_roster_sha256 <> b.partition_roster_sha256
                        OR (SELECT count(*) FROM mra.experiment_partition ep
                            WHERE ep.experiment_id = e.experiment_id) <> c.partition_plan_count
                        OR EXISTS (
                            SELECT cb.binding_ordinal, cb.research_partition_id,
                                   cb.purpose, cb.partition_content_sha256
                            FROM mra.formal_research_campaign_partition_binding cb
                            WHERE cb.formal_research_campaign_id = c.formal_research_campaign_id
                            EXCEPT
                            SELECT ep.binding_ordinal, ep.research_partition_id,
                                   ep.partition_purpose, ep.partition_content_sha256
                            FROM mra.experiment_partition ep
                            WHERE ep.experiment_id = e.experiment_id))
                  ) AS experiment_drift,
                  EXISTS (
                    SELECT 1
                    FROM mra.formal_research_campaign_protected_open p
                    JOIN mra.formal_research_campaign c USING (formal_research_campaign_id)
                    JOIN mra.formal_research_campaign_experiment b USING (formal_research_campaign_id)
                    JOIN mra.experiment_run er ON er.experiment_run_id = p.experiment_run_id
                    JOIN mra.evaluation_run ev ON ev.evaluation_run_id = p.evaluation_run_id
                    WHERE c.formal_research_campaign_id = %s
                      AND (er.experiment_id <> b.experiment_id
                        OR ev.experiment_run_id <> er.experiment_run_id
                        OR ev.experiment_id <> b.experiment_id
                        OR ev.partition_purpose <> p.purpose
                        OR NOT (c.predeclared_at < b.bound_at
                            AND b.bound_at <= er.opened_at
                            AND er.opened_at < ev.opened_at
                            AND ev.opened_at < p.opened_at)
                        OR EXISTS (
                            SELECT 1
                            FROM mra.research_partition_outcome_access a
                            JOIN mra.research_partition_member m
                              ON m.research_partition_member_id = a.research_partition_member_id
                            WHERE m.research_partition_id = ev.research_partition_id
                              AND a.accessed_at <= p.opened_at))
                  ) AS protected_drift,
                  EXISTS (
                    SELECT 1
                    FROM mra.formal_research_campaign_runtime_run b
                    WHERE b.formal_research_campaign_id = %s
                      AND ((b.runtime_profile = 'DECISION_PROOF' AND (
                              (SELECT count(*) FROM mra.runtime_step s
                               WHERE s.run_id = b.runtime_run_id
                                 AND s.step_key LIKE 'formal-decision-%%') <> 10
                              OR EXISTS (SELECT 1 FROM mra.runtime_step s
                                         WHERE s.run_id = b.runtime_run_id
                                           AND s.step_key NOT LIKE 'formal-decision-%%')))
                        OR (b.runtime_profile = 'DUE_PROOF' AND (
                              (SELECT count(*) FROM mra.runtime_step s
                               WHERE s.run_id = b.runtime_run_id
                                 AND s.step_key LIKE 'formal-due-%%') <> 6
                              OR EXISTS (SELECT 1 FROM mra.runtime_step s
                                         WHERE s.run_id = b.runtime_run_id
                                           AND s.step_key NOT LIKE 'formal-due-%%'))))
                  ) AS runtime_drift
                """,
                (
                    formal_research_campaign_id,
                    formal_research_campaign_id,
                    formal_research_campaign_id,
                    formal_research_campaign_id,
                ),
            ).fetchone()
            assert authority_drift is not None
            if authority_drift[0]:
                mismatches.append("PROVIDER_DECISION_DRIFT")
            if authority_drift[1]:
                mismatches.append("EXPERIMENT_ROSTER_DRIFT")
            if authority_drift[2]:
                mismatches.append("PROTECTED_OPEN_DRIFT")
            if authority_drift[3]:
                mismatches.append("RUNTIME_PROFILE_DRIFT")
            provenance = connection.execute(
                """
                SELECT
                  EXISTS (
                    SELECT 1
                    FROM mra.formal_research_campaign c
                    JOIN mra.command_receipt receipt
                      ON receipt.command_kind = 'PREDECLARE_FORMAL_RESEARCH_CAMPAIGN'
                     AND receipt.scope_id = c.campaign_code
                     AND receipt.idempotency_key = c.request_identity
                     AND receipt.request_hash = c.request_sha256
                     AND receipt.status = 'SUCCEEDED'
                     AND receipt.result_aggregate_kind = 'FORMAL_RESEARCH_CAMPAIGN'
                     AND receipt.result_aggregate_id = c.formal_research_campaign_id::text
                    JOIN mra.audit_event audit
                      ON audit.command_receipt_id = receipt.receipt_id
                     AND audit.action = 'PREDECLARE_FORMAL_RESEARCH_CAMPAIGN'
                     AND audit.aggregate_id = c.formal_research_campaign_id::text
                    WHERE c.formal_research_campaign_id = %s
                  ) AS root_provenance,
                  NOT EXISTS (
                    WITH expected(kind, aggregate_id, action) AS (
                      SELECT 'PROVIDER_DECISION', provider_qualification_decision_id::text,
                             'BIND_FORMAL_CAMPAIGN_PROVIDER_DECISION'
                      FROM mra.formal_research_campaign_provider_decision
                      WHERE formal_research_campaign_id = %s
                      UNION ALL
                      SELECT 'PARTITION_ROSTER', formal_research_campaign_id::text,
                             'BIND_FORMAL_CAMPAIGN_PARTITION_ROSTER'
                      FROM mra.formal_research_campaign_partition_binding
                      WHERE formal_research_campaign_id = %s
                      GROUP BY formal_research_campaign_id
                      UNION ALL
                      SELECT 'EXPERIMENT', experiment_id::text,
                             'BIND_FORMAL_CAMPAIGN_EXPERIMENT'
                      FROM mra.formal_research_campaign_experiment
                      WHERE formal_research_campaign_id = %s
                      UNION ALL
                      SELECT 'PROTECTED_OPEN', evaluation_run_id::text,
                             'OPEN_FORMAL_CAMPAIGN_PROTECTED'
                      FROM mra.formal_research_campaign_protected_open
                      WHERE formal_research_campaign_id = %s
                      UNION ALL
                      SELECT 'RUNTIME_RUN', runtime_run_id::text,
                             'BIND_FORMAL_CAMPAIGN_RUNTIME_RUN'
                      FROM mra.formal_research_campaign_runtime_run
                      WHERE formal_research_campaign_id = %s
                    )
                    SELECT 1 FROM expected
                    WHERE NOT EXISTS (
                      SELECT 1 FROM mra.command_receipt receipt
                      JOIN mra.audit_event audit
                        ON audit.command_receipt_id = receipt.receipt_id
                      WHERE receipt.status = 'SUCCEEDED'
                        AND receipt.result_aggregate_kind = expected.kind
                        AND receipt.result_aggregate_id = expected.aggregate_id
                        AND audit.action = expected.action
                        AND audit.aggregate_id = expected.aggregate_id)
                  ) AS binding_provenance
                """,
                (formal_research_campaign_id,) * 6,
            ).fetchone()
            assert provenance is not None
            if provenance[0] is not True:
                mismatches.append("CAMPAIGN_RECEIPT_AUDIT_MISMATCH")
            if provenance[1] is not True:
                mismatches.append("CAMPAIGN_BINDING_RECEIPT_AUDIT_MISMATCH")
            ordinal = connection.execute(
                """
                SELECT count(*) FROM (
                    SELECT access.research_partition_member_id,
                           min(access.access_ordinal), max(access.access_ordinal),
                           count(*), count(DISTINCT access.access_ordinal)
                    FROM mra.research_partition_outcome_access access
                    JOIN mra.research_partition_member member
                      ON member.research_partition_member_id = access.research_partition_member_id
                    JOIN mra.formal_research_campaign_partition_binding b
                      ON b.research_partition_id = member.research_partition_id
                    WHERE b.formal_research_campaign_id = %s
                    GROUP BY access.research_partition_member_id
                    HAVING min(access.access_ordinal) <> 1
                        OR max(access.access_ordinal) <> count(*)
                        OR count(*) <> count(DISTINCT access.access_ordinal)
                ) invalid
                """,
                (formal_research_campaign_id,),
            ).fetchone()
            if ordinal is not None and int(ordinal[0]):
                mismatches.append("OUTCOME_ACCESS_ORDINAL_CHAIN_INVALID")
            partition_ids = tuple(
                UUID(str(row[0]))
                for row in connection.execute(
                    """
                    SELECT research_partition_id
                    FROM mra.formal_research_campaign_partition_binding
                    WHERE formal_research_campaign_id = %s
                    ORDER BY binding_ordinal
                    """,
                    (formal_research_campaign_id,),
                ).fetchall()
            )
            experiment_row = connection.execute(
                """
                SELECT experiment_id
                FROM mra.formal_research_campaign_experiment
                WHERE formal_research_campaign_id = %s
                """,
                (formal_research_campaign_id,),
            ).fetchone()
            experiment_id = (
                UUID(str(experiment_row[0])) if experiment_row is not None else None
            )
            evaluation_ids = tuple(
                UUID(str(row[0]))
                for row in connection.execute(
                    """
                    SELECT evaluation_run_id FROM mra.evaluation_run
                    WHERE experiment_id = %s
                    ORDER BY opened_at, evaluation_run_id
                    """,
                    (experiment_id,),
                ).fetchall()
                if experiment_id is not None
            )
            evidence_ids = tuple(
                UUID(str(row[0]))
                for row in connection.execute(
                    """
                    SELECT evidence_item_id FROM mra.evidence_item
                    WHERE evaluation_run_id = ANY(%s::uuid[])
                    ORDER BY recorded_at, evidence_item_id
                    """,
                    (list(evaluation_ids),),
                ).fetchall()
            )
            assessment_ids = tuple(
                UUID(str(row[0]))
                for row in connection.execute(
                    """
                    SELECT research_assessment_id FROM mra.research_assessment
                    WHERE experiment_id = %s
                    ORDER BY recorded_at, research_assessment_id
                    """,
                    (experiment_id,),
                ).fetchall()
                if experiment_id is not None
            )
            qualification_ids = tuple(
                UUID(str(row[0]))
                for row in connection.execute(
                    """
                    SELECT decision.research_qualification_decision_id
                    FROM mra.research_qualification_decision decision
                    JOIN mra.research_assessment assessment
                      ON assessment.research_assessment_id = decision.research_assessment_id
                    WHERE assessment.experiment_id = %s
                    ORDER BY decision.recorded_at,
                             decision.research_qualification_decision_id
                    """,
                    (experiment_id,),
                ).fetchall()
                if experiment_id is not None
            )
            policy_row = connection.execute(
                """
                SELECT research_qualification_policy_id
                FROM mra.formal_research_campaign
                WHERE formal_research_campaign_id = %s
                """,
                (formal_research_campaign_id,),
            ).fetchone()
            policy_id = UUID(str(policy_row[0])) if policy_row is not None else None
        evaluation_verifier = PostgresResearchEvaluationVerificationProvider(self._pool)
        for partition_id in partition_ids:
            if evaluation_verifier.inspect_partition(partition_id):
                mismatches.append(f"PARTITION_DOWNSTREAM_DRIFT:{partition_id}")
        if experiment_id is not None and evaluation_verifier.inspect_experiment(
            experiment_id
        ):
            mismatches.append(f"EXPERIMENT_DOWNSTREAM_DRIFT:{experiment_id}")
        for evaluation_id in evaluation_ids:
            if evaluation_verifier.inspect_evaluation_run(evaluation_id):
                mismatches.append(f"EVALUATION_DOWNSTREAM_DRIFT:{evaluation_id}")
        qualification_verifier = PostgresResearchQualificationVerificationProvider(
            self._pool
        )
        if policy_id is not None and qualification_verifier.inspect_policy(policy_id):
            mismatches.append(f"QUALIFICATION_POLICY_DRIFT:{policy_id}")
        for evidence_id in evidence_ids:
            if qualification_verifier.inspect_evidence(evidence_id):
                mismatches.append(f"EVIDENCE_DOWNSTREAM_DRIFT:{evidence_id}")
        for assessment_id in assessment_ids:
            if qualification_verifier.inspect_assessment(assessment_id):
                mismatches.append(f"ASSESSMENT_DOWNSTREAM_DRIFT:{assessment_id}")
        for qualification_id in qualification_ids:
            if qualification_verifier.inspect_decision(qualification_id):
                mismatches.append(f"QUALIFICATION_DOWNSTREAM_DRIFT:{qualification_id}")
        return FormalCampaignVerification(
            formal_research_campaign_id=formal_research_campaign_id,
            matched=not mismatches,
            mismatch_count=len(mismatches),
            mismatches=tuple(mismatches),
        )


__all__ = ["PostgresFormalCampaignQueryPort"]
