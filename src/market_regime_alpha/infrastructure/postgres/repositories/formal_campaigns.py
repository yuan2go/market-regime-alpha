"""PostgreSQL writer for FormalResearchCampaign and exact child bindings."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import psycopg

from market_regime_alpha.research_qualification.domain.formal_campaign import (
    FormalResearchCampaignDefinition,
)
from market_regime_alpha.research_qualification.ports.formal_campaign_uow import (
    FormalCampaignBindingRecord,
    FormalCampaignRecord,
)
from market_regime_alpha.runtime.errors import (
    ArtifactIntegrityError,
    RuntimeNotFoundError,
    RuntimeStateConflictError,
)
from market_regime_alpha.shared.hashing import canonical_json_sha256


class PostgresFormalCampaignRepository:
    def __init__(self, connection: psycopg.Connection[Any]) -> None:
        self._connection = connection

    def lock_identity(self, campaign_code: str) -> None:
        self._connection.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            (f"formal-research-campaign:{campaign_code}",),
        )

    def predeclare(
        self,
        definition: FormalResearchCampaignDefinition,
        *,
        request_identity: str,
        request_sha256: str,
    ) -> FormalCampaignRecord:
        campaign_id = definition.formal_research_campaign_id
        for ordinal, plan in enumerate(definition.partition_plans, start=1):
            self._connection.execute(
                """
                INSERT INTO mra.formal_research_campaign_partition_plan (
                    formal_research_campaign_id, plan_ordinal,
                    research_partition_id, partition_code,
                    target_definition_id, target_version,
                    target_definition_sha256, purpose, population_scope,
                    overlap_policy, exchange_code,
                    decision_start_session_id, decision_end_session_id,
                    purge_before_sessions, purge_after_sessions,
                    embargo_sessions, series_code, fold_ordinal,
                    code_artifact_id, code_content_sha256, code_size_bytes,
                    config_artifact_id, config_content_sha256, config_size_bytes,
                    provenance_sha256, content_sha256
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
                """,
                (
                    campaign_id,
                    ordinal,
                    plan.research_partition_id,
                    plan.partition_code,
                    plan.target_definition_id,
                    plan.target_version,
                    str(plan.target_definition_sha256),
                    plan.purpose.value,
                    plan.population_scope.value,
                    plan.overlap_policy.value,
                    plan.exchange_code,
                    plan.decision_start_session_id,
                    plan.decision_end_session_id,
                    plan.purge_before_sessions,
                    plan.purge_after_sessions,
                    plan.embargo_sessions,
                    plan.series_code,
                    plan.fold_ordinal,
                    plan.code_artifact.artifact_id,
                    str(plan.code_artifact.content_sha256),
                    plan.code_artifact.size_bytes,
                    plan.config_artifact.artifact_id,
                    str(plan.config_artifact.content_sha256),
                    plan.config_artifact.size_bytes,
                    str(plan.provenance_sha256),
                    str(plan.content_sha256),
                ),
            )
        for binding in definition.evaluation_protocol_bindings:
            self._connection.execute(
                """
                INSERT INTO mra.formal_research_campaign_evaluation_protocol (
                    formal_research_campaign_id,
                    formal_campaign_evaluation_binding_id,
                    binding_ordinal, purpose, evaluation_protocol_id,
                    evaluation_protocol_sha256, content_sha256
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    campaign_id,
                    binding.formal_campaign_evaluation_binding_id,
                    binding.ordinal,
                    binding.purpose.value,
                    binding.evaluation_protocol_id,
                    str(binding.evaluation_protocol_sha256),
                    str(binding.content_sha256),
                ),
            )
        for cost in definition.cost_assumptions:
            self._connection.execute(
                """
                INSERT INTO mra.formal_research_campaign_cost_assumption (
                    formal_research_campaign_id,
                    formal_campaign_cost_assumption_id,
                    assumption_ordinal, cost_kind, amount_bps,
                    content_sha256
                ) VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    campaign_id,
                    cost.formal_campaign_cost_assumption_id,
                    cost.ordinal,
                    cost.cost_kind.value,
                    cost.amount_bps,
                    str(cost.content_sha256),
                ),
            )
        values = {
            "campaign_id": campaign_id,
            "campaign_code": definition.campaign_code,
            "revision": definition.revision,
            "supersedes": definition.supersedes_campaign_id,
            "campaign_class": definition.campaign_class.value,
            "hypothesis": definition.hypothesis,
            "experiment_code": definition.experiment_code,
            "research_question": definition.research_question,
            "primary_change": definition.primary_change,
            "protocol_identity": definition.protocol_identity,
            "acceptance_semantics": definition.acceptance_semantics,
            "target_id": definition.target_definition_id,
            "target_version": definition.target_version,
            "target_hash": str(definition.target_definition_sha256),
            "product_id": definition.provider_product_id,
            "provider_protocol_id": definition.provider_qualification_protocol_id,
            "provider_protocol_hash": str(
                definition.provider_qualification_protocol_sha256
            ),
            "candidate_id": definition.candidate_policy_id,
            "candidate_hash": str(definition.candidate_policy_sha256),
            "context_id": definition.context_policy_id,
            "context_hash": str(definition.context_policy_sha256),
            "strategy_id": definition.strategy_version_id,
            "strategy_hash": str(definition.strategy_version_sha256),
            "portfolio_id": definition.portfolio_policy_id,
            "portfolio_hash": str(definition.portfolio_policy_sha256),
            "risk_id": definition.risk_policy_id,
            "risk_hash": str(definition.risk_policy_sha256),
            "qualification_id": definition.research_qualification_policy_id,
            "qualification_hash": str(
                definition.research_qualification_policy_sha256
            ),
            "plan_count": definition.partition_plan_count,
            "plan_hash": str(definition.partition_plan_roster_sha256),
            "evaluation_count": definition.evaluation_protocol_count,
            "evaluation_hash": str(definition.evaluation_protocol_roster_sha256),
            "cost_count": definition.cost_assumption_count,
            "cost_hash": str(definition.cost_assumption_roster_sha256),
            "code_id": definition.code_artifact.artifact_id,
            "code_hash": str(definition.code_artifact.content_sha256),
            "code_size": definition.code_artifact.size_bytes,
            "config_id": definition.config_artifact.artifact_id,
            "config_hash": str(definition.config_artifact.content_sha256),
            "config_size": definition.config_artifact.size_bytes,
            "provenance": str(definition.provenance_sha256),
            "content": str(definition.content_sha256),
            "request_identity": request_identity,
            "request_hash": request_sha256,
        }
        self._connection.execute(
            """
            INSERT INTO mra.formal_research_campaign (
                formal_research_campaign_id, campaign_code, revision,
                supersedes_campaign_id, campaign_class, hypothesis,
                experiment_code, research_question, primary_change,
                protocol_identity, acceptance_semantics,
                target_definition_id, target_version,
                target_definition_sha256, provider_product_id,
                provider_qualification_protocol_id,
                provider_qualification_protocol_sha256,
                candidate_policy_id, candidate_policy_sha256,
                context_policy_id, context_policy_sha256,
                strategy_version_id, strategy_version_sha256,
                portfolio_policy_id, portfolio_policy_sha256,
                risk_policy_id, risk_policy_sha256,
                research_qualification_policy_id,
                research_qualification_policy_sha256,
                partition_plan_count, partition_plan_roster_sha256,
                evaluation_protocol_count,
                evaluation_protocol_roster_sha256,
                cost_assumption_count, cost_assumption_roster_sha256,
                code_artifact_id, code_content_sha256, code_size_bytes,
                config_artifact_id, config_content_sha256, config_size_bytes,
                provenance_sha256, content_sha256,
                request_identity, request_sha256
            ) VALUES (
                %(campaign_id)s, %(campaign_code)s, %(revision)s,
                %(supersedes)s, %(campaign_class)s, %(hypothesis)s,
                %(experiment_code)s, %(research_question)s, %(primary_change)s,
                %(protocol_identity)s, %(acceptance_semantics)s,
                %(target_id)s, %(target_version)s, %(target_hash)s,
                %(product_id)s, %(provider_protocol_id)s,
                %(provider_protocol_hash)s,
                %(candidate_id)s, %(candidate_hash)s,
                %(context_id)s, %(context_hash)s,
                %(strategy_id)s, %(strategy_hash)s,
                %(portfolio_id)s, %(portfolio_hash)s,
                %(risk_id)s, %(risk_hash)s,
                %(qualification_id)s, %(qualification_hash)s,
                %(plan_count)s, %(plan_hash)s,
                %(evaluation_count)s, %(evaluation_hash)s,
                %(cost_count)s, %(cost_hash)s,
                %(code_id)s, %(code_hash)s, %(code_size)s,
                %(config_id)s, %(config_hash)s, %(config_size)s,
                %(provenance)s, %(content)s,
                %(request_identity)s, %(request_hash)s
            )
            """,
            values,
        )
        return self.record(campaign_id, lock=False)

    def record(
        self, formal_research_campaign_id: UUID, *, lock: bool
    ) -> FormalCampaignRecord:
        row = self._connection.execute(
            """
            SELECT formal_research_campaign_id, campaign_code, revision,
                   campaign_class, target_definition_id,
                   partition_plan_count, partition_plan_roster_sha256,
                   evaluation_protocol_count,
                   evaluation_protocol_roster_sha256,
                   cost_assumption_count, cost_assumption_roster_sha256,
                   content_sha256, predeclared_at
            FROM mra.formal_research_campaign
            WHERE formal_research_campaign_id = %s
            """
            + (" FOR SHARE" if lock else ""),
            (formal_research_campaign_id,),
        ).fetchone()
        if row is None:
            raise RuntimeNotFoundError("FormalResearchCampaign does not exist")
        return FormalCampaignRecord(
            formal_research_campaign_id=UUID(str(row[0])),
            campaign_code=str(row[1]),
            revision=int(row[2]),
            campaign_class=str(row[3]),
            target_definition_id=UUID(str(row[4])),
            partition_plan_count=int(row[5]),
            partition_plan_roster_sha256=str(row[6]),
            evaluation_protocol_count=int(row[7]),
            evaluation_protocol_roster_sha256=str(row[8]),
            cost_assumption_count=int(row[9]),
            cost_assumption_roster_sha256=str(row[10]),
            content_sha256=str(row[11]),
            predeclared_at=row[12],
        )

    def reconcile(self, formal_research_campaign_id: UUID) -> bool:
        row = self._connection.execute(
            """
            SELECT plan_count = campaign.partition_plan_count
                   AND evaluation_count = campaign.evaluation_protocol_count
                   AND cost_count = campaign.cost_assumption_count
                   AND plan_min = 1 AND plan_max = campaign.partition_plan_count
                   AND evaluation_min = 1
                   AND evaluation_max = campaign.evaluation_protocol_count
                   AND cost_min = 1 AND cost_max = campaign.cost_assumption_count
            FROM mra.formal_research_campaign AS campaign
            CROSS JOIN LATERAL (
                SELECT count(*)::integer AS plan_count,
                       min(plan_ordinal) AS plan_min,
                       max(plan_ordinal) AS plan_max
                FROM mra.formal_research_campaign_partition_plan
                WHERE formal_research_campaign_id = campaign.formal_research_campaign_id
            ) AS plans
            CROSS JOIN LATERAL (
                SELECT count(*)::integer AS evaluation_count,
                       min(binding_ordinal) AS evaluation_min,
                       max(binding_ordinal) AS evaluation_max
                FROM mra.formal_research_campaign_evaluation_protocol
                WHERE formal_research_campaign_id = campaign.formal_research_campaign_id
            ) AS evaluations
            CROSS JOIN LATERAL (
                SELECT count(*)::integer AS cost_count,
                       min(assumption_ordinal) AS cost_min,
                       max(assumption_ordinal) AS cost_max
                FROM mra.formal_research_campaign_cost_assumption
                WHERE formal_research_campaign_id = campaign.formal_research_campaign_id
            ) AS costs
            WHERE campaign.formal_research_campaign_id = %s
            """,
            (formal_research_campaign_id,),
        ).fetchone()
        return bool(row and row[0])

    def bind_provider_decision(
        self,
        formal_research_campaign_id: UUID,
        provider_qualification_decision_id: UUID,
    ) -> FormalCampaignBindingRecord:
        decision = self._connection.execute(
            """
            SELECT content_sha256 FROM mra.provider_qualification_decision
            WHERE provider_qualification_decision_id = %s FOR SHARE
            """,
            (provider_qualification_decision_id,),
        ).fetchone()
        if decision is None:
            raise RuntimeNotFoundError("Provider qualification Decision does not exist")
        content = canonical_json_sha256(
            {
                "formal_research_campaign_id": formal_research_campaign_id,
                "provider_qualification_decision_id": provider_qualification_decision_id,
                "provider_qualification_decision_sha256": str(decision[0]),
            }
        )
        row = self._connection.execute(
            """
            INSERT INTO mra.formal_research_campaign_provider_decision (
                formal_research_campaign_id,
                provider_qualification_decision_id,
                provider_qualification_decision_sha256, content_sha256
            ) VALUES (%s, %s, %s, %s)
            RETURNING bound_at
            """,
            (
                formal_research_campaign_id,
                provider_qualification_decision_id,
                str(decision[0]),
                content,
            ),
        ).fetchone()
        assert row is not None
        return FormalCampaignBindingRecord(
            formal_research_campaign_id,
            "PROVIDER_DECISION",
            provider_qualification_decision_id,
            1,
            content,
            row[0],
        )

    def bind_partition_roster(
        self, formal_research_campaign_id: UUID
    ) -> FormalCampaignBindingRecord:
        campaign = self._connection.execute(
            """
            SELECT partition_plan_count
            FROM mra.formal_research_campaign
            WHERE formal_research_campaign_id = %s
            FOR SHARE
            """,
            (formal_research_campaign_id,),
        ).fetchone()
        if campaign is None:
            raise RuntimeNotFoundError("FormalResearchCampaign does not exist")
        plans = self._connection.execute(
            """
            SELECT plan.plan_ordinal, plan.research_partition_id,
                   plan.purpose, partition.content_sha256
            FROM mra.formal_research_campaign_partition_plan AS plan
            JOIN mra.research_partition AS partition
              ON partition.research_partition_id = plan.research_partition_id
            WHERE plan.formal_research_campaign_id = %s
            ORDER BY plan.plan_ordinal
            FOR SHARE OF partition
            """,
            (formal_research_campaign_id,),
        ).fetchall()
        if len(plans) != int(campaign[0]):
            raise RuntimeStateConflictError("planned Partition roster is incomplete")
        bound_at = None
        hashes: list[str] = []
        for ordinal, partition_id, purpose, partition_hash in plans:
            content = canonical_json_sha256(
                {
                    "binding_ordinal": int(ordinal),
                    "partition_content_sha256": str(partition_hash),
                    "purpose": str(purpose),
                    "research_partition_id": UUID(str(partition_id)),
                }
            )
            row = self._connection.execute(
                """
                INSERT INTO mra.formal_research_campaign_partition_binding (
                    formal_research_campaign_id, binding_ordinal,
                    research_partition_id, purpose,
                    partition_content_sha256, content_sha256
                ) VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING bound_at
                """,
                (
                    formal_research_campaign_id,
                    ordinal,
                    partition_id,
                    purpose,
                    partition_hash,
                    content,
                ),
            ).fetchone()
            assert row is not None
            bound_at = row[0]
            hashes.append(content)
        assert bound_at is not None
        return FormalCampaignBindingRecord(
            formal_research_campaign_id,
            "PARTITION_ROSTER",
            formal_research_campaign_id,
            len(plans),
            canonical_json_sha256(hashes),
            bound_at,
        )

    def bind_experiment(
        self, formal_research_campaign_id: UUID, experiment_id: UUID
    ) -> FormalCampaignBindingRecord:
        experiment = self._connection.execute(
            """
            SELECT content_sha256, partition_count, partition_roster_sha256
            FROM mra.experiment WHERE experiment_id = %s FOR SHARE
            """,
            (experiment_id,),
        ).fetchone()
        if experiment is None:
            raise RuntimeNotFoundError("Experiment does not exist")
        content = canonical_json_sha256(
            {
                "experiment_content_sha256": str(experiment[0]),
                "experiment_id": experiment_id,
                "partition_count": int(experiment[1]),
                "partition_roster_sha256": str(experiment[2]),
            }
        )
        row = self._connection.execute(
            """
            INSERT INTO mra.formal_research_campaign_experiment (
                formal_research_campaign_id, experiment_id,
                experiment_content_sha256, partition_count,
                partition_roster_sha256, content_sha256
            ) VALUES (%s, %s, %s, %s, %s, %s) RETURNING bound_at
            """,
            (
                formal_research_campaign_id,
                experiment_id,
                experiment[0],
                experiment[1],
                experiment[2],
                content,
            ),
        ).fetchone()
        assert row is not None
        return FormalCampaignBindingRecord(
            formal_research_campaign_id,
            "EXPERIMENT",
            experiment_id,
            int(experiment[1]),
            content,
            row[0],
        )

    def open_protected(
        self,
        formal_research_campaign_id: UUID,
        *,
        purpose: str,
        experiment_run_id: UUID,
        evaluation_run_id: UUID,
    ) -> FormalCampaignBindingRecord:
        content = canonical_json_sha256(
            {
                "evaluation_run_id": evaluation_run_id,
                "experiment_run_id": experiment_run_id,
                "purpose": purpose,
            }
        )
        row = self._connection.execute(
            """
            INSERT INTO mra.formal_research_campaign_protected_open (
                formal_research_campaign_id, purpose, experiment_run_id,
                evaluation_run_id, content_sha256
            ) VALUES (%s, %s, %s, %s, %s) RETURNING opened_at
            """,
            (
                formal_research_campaign_id,
                purpose,
                experiment_run_id,
                evaluation_run_id,
                content,
            ),
        ).fetchone()
        assert row is not None
        return FormalCampaignBindingRecord(
            formal_research_campaign_id,
            "PROTECTED_OPEN",
            evaluation_run_id,
            1,
            content,
            row[0],
        )

    def bind_runtime_run(
        self,
        formal_research_campaign_id: UUID,
        *,
        runtime_profile: str,
        runtime_run_id: UUID,
    ) -> FormalCampaignBindingRecord:
        content = canonical_json_sha256(
            {"runtime_profile": runtime_profile, "runtime_run_id": runtime_run_id}
        )
        row = self._connection.execute(
            """
            INSERT INTO mra.formal_research_campaign_runtime_run (
                formal_research_campaign_id, runtime_profile,
                runtime_run_id, content_sha256
            ) VALUES (%s, %s, %s, %s) RETURNING bound_at
            """,
            (formal_research_campaign_id, runtime_profile, runtime_run_id, content),
        ).fetchone()
        if row is None:
            raise ArtifactIntegrityError("Runtime binding insert returned no row")
        return FormalCampaignBindingRecord(
            formal_research_campaign_id,
            "RUNTIME_RUN",
            runtime_run_id,
            1,
            content,
            row[0],
        )

    def binding_matches(
        self,
        formal_research_campaign_id: UUID,
        *,
        binding_kind: str,
        aggregate_id: UUID,
        content_sha256: str,
    ) -> bool:
        queries = {
            "PROVIDER_DECISION": (
                "formal_research_campaign_provider_decision",
                "provider_qualification_decision_id",
            ),
            "PARTITION_ROSTER": (
                "formal_research_campaign_partition_binding",
                "formal_research_campaign_id",
            ),
            "EXPERIMENT": (
                "formal_research_campaign_experiment",
                "experiment_id",
            ),
            "PROTECTED_OPEN": (
                "formal_research_campaign_protected_open",
                "evaluation_run_id",
            ),
            "RUNTIME_RUN": (
                "formal_research_campaign_runtime_run",
                "runtime_run_id",
            ),
        }
        target = queries.get(binding_kind)
        if target is None:
            return False
        table, aggregate_column = target
        if binding_kind == "PARTITION_ROSTER":
            rows = self._connection.execute(
                """
                SELECT binding.binding_ordinal, binding.content_sha256,
                       campaign.partition_plan_count
                FROM mra.formal_research_campaign_partition_binding AS binding
                JOIN mra.formal_research_campaign AS campaign
                  ON campaign.formal_research_campaign_id =
                     binding.formal_research_campaign_id
                WHERE binding.formal_research_campaign_id = %s
                ORDER BY binding.binding_ordinal
                """,
                (formal_research_campaign_id,),
            ).fetchall()
            if not rows or aggregate_id != formal_research_campaign_id:
                return False
            expected_count = int(rows[0][2])
            return (
                len(rows) == expected_count
                and tuple(int(row[0]) for row in rows)
                == tuple(range(1, expected_count + 1))
                and canonical_json_sha256([str(row[1]) for row in rows])
                == content_sha256
            )
        row = self._connection.execute(
            f"""
            SELECT content_sha256 = %s
            FROM mra.{table}
            WHERE formal_research_campaign_id = %s
              AND {aggregate_column} = %s
            """,  # noqa: S608 -- closed table/column vocabulary above
            (content_sha256, formal_research_campaign_id, aggregate_id),
        ).fetchone()
        return bool(row and row[0])


__all__ = ["PostgresFormalCampaignRepository"]
