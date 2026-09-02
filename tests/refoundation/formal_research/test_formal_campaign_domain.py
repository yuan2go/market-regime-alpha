from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from uuid import uuid4

import pytest

from market_regime_alpha.research_qualification.domain import ArtifactBinding
from market_regime_alpha.research_qualification.domain.formal_campaign import (
    CampaignClass,
    CampaignCostAssumption,
    CampaignCostKind,
    CampaignEvaluationProtocolBinding,
    FormalResearchCampaignDefinition,
)
from market_regime_alpha.research_qualification.domain.partition import (
    ResearchPartitionPlan,
)
from market_regime_alpha.research_qualification.domain.research_vocabulary import (
    PartitionOverlapPolicy,
    PartitionPopulationScope,
    PartitionPurpose,
)


def _artifact(value: str) -> ArtifactBinding:
    return ArtifactBinding(uuid4(), value * 64, 10)


def _campaign() -> FormalResearchCampaignDefinition:
    target_id = uuid4()
    code = _artifact("a")
    config = _artifact("b")
    purposes = (
        PartitionPurpose.FIT,
        PartitionPurpose.VALIDATION,
        PartitionPurpose.LOCKED_OOS,
    )
    plans = tuple(
        ResearchPartitionPlan(
            research_partition_id=uuid4(),
            partition_code=f"wp14-{purpose.value.lower().replace('_', '-')}",
            target_definition_id=target_id,
            target_version=1,
            target_definition_sha256="c" * 64,
            purpose=purpose,
            population_scope=PartitionPopulationScope.SELECTED,
            overlap_policy=(
                PartitionOverlapPolicy.ISOLATED_PROTECTED
                if purpose is PartitionPurpose.LOCKED_OOS
                else PartitionOverlapPolicy.PURGED_WALK_FORWARD
            ),
            exchange_code="SSE",
            decision_start_session_id=uuid4(),
            decision_end_session_id=uuid4(),
            purge_before_sessions=5,
            purge_after_sessions=5,
            embargo_sessions=2,
            series_code="wp14-baseline",
            fold_ordinal=ordinal,
            code_artifact=code,
            config_artifact=config,
            provenance_sha256="d" * 64,
        )
        for ordinal, purpose in enumerate(purposes, start=1)
    )
    evaluation_bindings = tuple(
        CampaignEvaluationProtocolBinding(
            formal_campaign_evaluation_binding_id=uuid4(),
            ordinal=ordinal,
            purpose=purpose,
            evaluation_protocol_id=uuid4(),
            evaluation_protocol_sha256=str(ordinal) * 64,
        )
        for ordinal, purpose in enumerate(purposes, start=1)
    )
    costs = tuple(
        CampaignCostAssumption(
            formal_campaign_cost_assumption_id=uuid4(),
            ordinal=ordinal,
            cost_kind=kind,
            amount_bps=Decimal("2.5000000000"),
        )
        for ordinal, kind in enumerate(CampaignCostKind, start=1)
    )
    return FormalResearchCampaignDefinition(
        formal_research_campaign_id=uuid4(),
        campaign_code="wp14-rehearsal",
        revision=1,
        supersedes_campaign_id=None,
        campaign_class=CampaignClass.ENGINEERING_REHEARSAL,
        hypothesis="One frozen transparent rule baseline",
        experiment_code="wp14-experiment",
        research_question="Does the frozen rule generalize?",
        primary_change="One declared baseline",
        protocol_identity="wp14-protocol-v1",
        acceptance_semantics="All declared floors are evaluated",
        target_definition_id=target_id,
        target_version=1,
        target_definition_sha256="c" * 64,
        provider_product_id=uuid4(),
        provider_qualification_protocol_id=uuid4(),
        provider_qualification_protocol_sha256="e" * 64,
        candidate_policy_id=uuid4(),
        candidate_policy_sha256="f" * 64,
        context_policy_id=uuid4(),
        context_policy_sha256="0" * 64,
        strategy_version_id=uuid4(),
        strategy_version_sha256="1" * 64,
        portfolio_policy_id=uuid4(),
        portfolio_policy_sha256="2" * 64,
        risk_policy_id=uuid4(),
        risk_policy_sha256="3" * 64,
        research_qualification_policy_id=uuid4(),
        research_qualification_policy_sha256="4" * 64,
        partition_plans=plans,
        evaluation_protocol_bindings=evaluation_bindings,
        cost_assumptions=costs,
        code_artifact=code,
        config_artifact=config,
        provenance_sha256="5" * 64,
    )


def test_campaign_freezes_required_partitions_evaluations_costs_and_baseline() -> None:
    campaign = _campaign()

    assert campaign.partition_plan_count == 3
    assert campaign.evaluation_protocol_count == 3
    assert campaign.cost_assumption_count == len(CampaignCostKind)
    assert campaign.partition_plan_roster_sha256
    assert campaign.content_sha256


def test_campaign_rejects_missing_locked_oos_duplicate_purpose_and_wrong_target() -> None:
    campaign = _campaign()
    with pytest.raises(ValueError, match="FIT, VALIDATION, and LOCKED_OOS"):
        replace(campaign, partition_plans=campaign.partition_plans[:-1])
    with pytest.raises(ValueError, match="unique"):
        replace(
            campaign,
            partition_plans=(campaign.partition_plans[0], campaign.partition_plans[0], campaign.partition_plans[2]),
        )
    with pytest.raises(ValueError, match="Target"):
        replace(
            campaign,
            partition_plans=(
                replace(campaign.partition_plans[0], target_definition_id=uuid4()),
                *campaign.partition_plans[1:],
            ),
        )


def test_campaign_rejects_changed_generation_without_supersession() -> None:
    campaign = _campaign()
    with pytest.raises(ValueError, match="revision chain"):
        replace(campaign, revision=2, supersedes_campaign_id=None)
