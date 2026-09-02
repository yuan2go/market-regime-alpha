"""Immutable formal-research campaign predeclaration."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
import re
from uuid import UUID

from market_regime_alpha.research_qualification.domain.model import ArtifactBinding
from market_regime_alpha.research_qualification.domain.partition import (
    ResearchPartitionPlan,
)
from market_regime_alpha.research_qualification.domain.research_vocabulary import (
    PartitionPurpose,
)
from market_regime_alpha.shared.financial import bounded_decimal
from market_regime_alpha.shared.hashing import canonical_json_sha256
from market_regime_alpha.shared.identity import ContentHash


class CampaignClass(StrEnum):
    ENGINEERING_REHEARSAL = "ENGINEERING_REHEARSAL"
    FORMAL_RESEARCH = "FORMAL_RESEARCH"


class CampaignCostKind(StrEnum):
    COMMISSION = "COMMISSION"
    SLIPPAGE = "SLIPPAGE"
    MARKET_IMPACT = "MARKET_IMPACT"


@dataclass(frozen=True, slots=True)
class FormalDatasetScope:
    formal_research_campaign_id: UUID
    provider_qualification_decision_id: UUID


@dataclass(frozen=True, slots=True)
class CampaignEvaluationProtocolBinding:
    formal_campaign_evaluation_binding_id: UUID
    ordinal: int
    purpose: PartitionPurpose
    evaluation_protocol_id: UUID
    evaluation_protocol_sha256: ContentHash | str
    content_sha256: ContentHash = field(init=False)

    def __post_init__(self) -> None:
        if isinstance(self.ordinal, bool) or self.ordinal < 1:
            raise ValueError("Evaluation binding ordinal must be positive")
        if not isinstance(self.purpose, PartitionPurpose):
            raise TypeError("purpose must be PartitionPurpose")
        protocol_hash = ContentHash(str(self.evaluation_protocol_sha256))
        object.__setattr__(self, "evaluation_protocol_sha256", protocol_hash)
        object.__setattr__(
            self,
            "content_sha256",
            ContentHash(
                canonical_json_sha256(
                    {
                        "evaluation_protocol_id": self.evaluation_protocol_id,
                        "evaluation_protocol_sha256": str(protocol_hash),
                        "ordinal": self.ordinal,
                        "purpose": self.purpose,
                    }
                )
            ),
        )


@dataclass(frozen=True, slots=True)
class CampaignCostAssumption:
    formal_campaign_cost_assumption_id: UUID
    ordinal: int
    cost_kind: CampaignCostKind
    amount_bps: Decimal
    content_sha256: ContentHash = field(init=False)

    def __post_init__(self) -> None:
        if isinstance(self.ordinal, bool) or self.ordinal < 1:
            raise ValueError("Cost assumption ordinal must be positive")
        if not isinstance(self.cost_kind, CampaignCostKind):
            raise TypeError("cost_kind must be CampaignCostKind")
        amount = bounded_decimal(
            self.amount_bps,
            field="amount_bps",
            precision=20,
            scale=10,
        )
        if amount < 0:
            raise ValueError("amount_bps must be non-negative")
        object.__setattr__(self, "amount_bps", amount)
        object.__setattr__(
            self,
            "content_sha256",
            ContentHash(
                canonical_json_sha256(
                    {
                        "amount_bps": amount,
                        "cost_kind": self.cost_kind,
                        "ordinal": self.ordinal,
                    }
                )
            ),
        )


@dataclass(frozen=True, slots=True)
class FormalResearchCampaignDefinition:
    formal_research_campaign_id: UUID
    campaign_code: str
    revision: int
    supersedes_campaign_id: UUID | None
    campaign_class: CampaignClass
    hypothesis: str
    experiment_code: str
    research_question: str
    primary_change: str
    protocol_identity: str
    acceptance_semantics: str
    target_definition_id: UUID
    target_version: int
    target_definition_sha256: ContentHash | str
    provider_product_id: UUID
    provider_qualification_protocol_id: UUID
    provider_qualification_protocol_sha256: ContentHash | str
    candidate_policy_id: UUID
    candidate_policy_sha256: ContentHash | str
    context_policy_id: UUID
    context_policy_sha256: ContentHash | str
    strategy_version_id: UUID
    strategy_version_sha256: ContentHash | str
    portfolio_policy_id: UUID
    portfolio_policy_sha256: ContentHash | str
    risk_policy_id: UUID
    risk_policy_sha256: ContentHash | str
    research_qualification_policy_id: UUID
    research_qualification_policy_sha256: ContentHash | str
    partition_plans: tuple[ResearchPartitionPlan, ...]
    evaluation_protocol_bindings: tuple[CampaignEvaluationProtocolBinding, ...]
    cost_assumptions: tuple[CampaignCostAssumption, ...]
    code_artifact: ArtifactBinding
    config_artifact: ArtifactBinding
    provenance_sha256: ContentHash | str
    partition_plan_count: int = field(init=False)
    partition_plan_roster_sha256: ContentHash = field(init=False)
    evaluation_protocol_count: int = field(init=False)
    evaluation_protocol_roster_sha256: ContentHash = field(init=False)
    cost_assumption_count: int = field(init=False)
    cost_assumption_roster_sha256: ContentHash = field(init=False)
    content_sha256: ContentHash = field(init=False)

    def __post_init__(self) -> None:
        for code_name in ("campaign_code", "experiment_code"):
            if not re.fullmatch(
                r"[a-z][a-z0-9_-]{0,99}", str(getattr(self, code_name))
            ):
                raise ValueError(f"{code_name} has an invalid format")
        if isinstance(self.revision, bool) or self.revision < 1:
            raise ValueError("revision must be positive")
        if (self.revision == 1) != (self.supersedes_campaign_id is None):
            raise ValueError("Formal campaign revision chain is invalid")
        if not isinstance(self.campaign_class, CampaignClass):
            raise TypeError("campaign_class must be CampaignClass")
        for name in (
            "hypothesis",
            "research_question",
            "primary_change",
            "protocol_identity",
            "acceptance_semantics",
        ):
            if not str(getattr(self, name)).strip():
                raise ValueError(f"{name} is required")
        if isinstance(self.target_version, bool) or self.target_version < 1:
            raise ValueError("target_version must be positive")
        target_hash = ContentHash(str(self.target_definition_sha256))
        object.__setattr__(self, "target_definition_sha256", target_hash)
        hash_fields = (
            "provider_qualification_protocol_sha256",
            "candidate_policy_sha256",
            "context_policy_sha256",
            "strategy_version_sha256",
            "portfolio_policy_sha256",
            "risk_policy_sha256",
            "research_qualification_policy_sha256",
            "provenance_sha256",
        )
        for name in hash_fields:
            object.__setattr__(self, name, ContentHash(str(getattr(self, name))))
        required_purposes = {
            PartitionPurpose.FIT,
            PartitionPurpose.VALIDATION,
            PartitionPurpose.LOCKED_OOS,
        }
        purposes = tuple(plan.purpose for plan in self.partition_plans)
        if len(set(purposes)) != len(purposes):
            raise ValueError("campaign Partition purposes must be unique")
        if not required_purposes.issubset(set(purposes)):
            raise ValueError("campaign requires FIT, VALIDATION, and LOCKED_OOS")
        if len({plan.research_partition_id for plan in self.partition_plans}) != len(
            self.partition_plans
        ):
            raise ValueError("campaign Partition identities must be unique")
        for plan in self.partition_plans:
            if (
                plan.target_definition_id != self.target_definition_id
                or plan.target_version != self.target_version
                or plan.target_definition_sha256 != target_hash
            ):
                raise ValueError("campaign Partition Target does not match exactly")
        eval_purposes = tuple(
            binding.purpose for binding in self.evaluation_protocol_bindings
        )
        if eval_purposes != purposes:
            raise ValueError(
                "campaign Evaluation binding purposes must equal Partition purposes"
            )
        _require_contiguous(
            tuple(binding.ordinal for binding in self.evaluation_protocol_bindings),
            "Evaluation binding",
        )
        cost_kinds = tuple(item.cost_kind for item in self.cost_assumptions)
        if set(cost_kinds) != set(CampaignCostKind) or len(cost_kinds) != len(
            CampaignCostKind
        ):
            raise ValueError("every campaign cost kind must occur exactly once")
        _require_contiguous(
            tuple(item.ordinal for item in self.cost_assumptions),
            "cost assumption",
        )
        partition_roster = ContentHash(
            canonical_json_sha256(
                [
                    {
                        "content_sha256": str(plan.content_sha256),
                        "ordinal": ordinal,
                        "purpose": plan.purpose,
                        "research_partition_id": plan.research_partition_id,
                    }
                    for ordinal, plan in enumerate(self.partition_plans, start=1)
                ]
            )
        )
        evaluation_roster = ContentHash(
            canonical_json_sha256(
                [
                    {
                        "content_sha256": str(binding.content_sha256),
                        "ordinal": binding.ordinal,
                        "purpose": binding.purpose,
                    }
                    for binding in self.evaluation_protocol_bindings
                ]
            )
        )
        cost_roster = ContentHash(
            canonical_json_sha256(
                [
                    {
                        "content_sha256": str(item.content_sha256),
                        "cost_kind": item.cost_kind,
                        "ordinal": item.ordinal,
                    }
                    for item in self.cost_assumptions
                ]
            )
        )
        object.__setattr__(self, "partition_plan_count", len(self.partition_plans))
        object.__setattr__(self, "partition_plan_roster_sha256", partition_roster)
        object.__setattr__(
            self,
            "evaluation_protocol_count",
            len(self.evaluation_protocol_bindings),
        )
        object.__setattr__(self, "evaluation_protocol_roster_sha256", evaluation_roster)
        object.__setattr__(self, "cost_assumption_count", len(self.cost_assumptions))
        object.__setattr__(self, "cost_assumption_roster_sha256", cost_roster)
        object.__setattr__(
            self,
            "content_sha256",
            ContentHash(
                canonical_json_sha256(
                    {
                        "acceptance_semantics": self.acceptance_semantics,
                        "campaign_class": self.campaign_class,
                        "candidate_policy_id": self.candidate_policy_id,
                        "candidate_policy_sha256": str(self.candidate_policy_sha256),
                        "code_artifact": self.code_artifact,
                        "config_artifact": self.config_artifact,
                        "context_policy_id": self.context_policy_id,
                        "context_policy_sha256": str(self.context_policy_sha256),
                        "cost_assumption_count": len(self.cost_assumptions),
                        "cost_assumption_roster_sha256": str(cost_roster),
                        "evaluation_protocol_count": len(self.evaluation_protocol_bindings),
                        "evaluation_protocol_roster_sha256": str(evaluation_roster),
                        "experiment_code": self.experiment_code,
                        "hypothesis": self.hypothesis,
                        "partition_plan_count": len(self.partition_plans),
                        "partition_plan_roster_sha256": str(partition_roster),
                        "portfolio_policy_id": self.portfolio_policy_id,
                        "portfolio_policy_sha256": str(self.portfolio_policy_sha256),
                        "primary_change": self.primary_change,
                        "protocol_identity": self.protocol_identity,
                        "provider_product_id": self.provider_product_id,
                        "provider_qualification_protocol_id": self.provider_qualification_protocol_id,
                        "provider_qualification_protocol_sha256": str(self.provider_qualification_protocol_sha256),
                        "provenance_sha256": str(self.provenance_sha256),
                        "research_qualification_policy_id": self.research_qualification_policy_id,
                        "research_qualification_policy_sha256": str(self.research_qualification_policy_sha256),
                        "research_question": self.research_question,
                        "risk_policy_id": self.risk_policy_id,
                        "risk_policy_sha256": str(self.risk_policy_sha256),
                        "strategy_version_id": self.strategy_version_id,
                        "strategy_version_sha256": str(self.strategy_version_sha256),
                        "target_definition_id": self.target_definition_id,
                        "target_definition_sha256": str(target_hash),
                        "target_version": self.target_version,
                    }
                )
            ),
        )


def _require_contiguous(ordinals: tuple[int, ...], name: str) -> None:
    if ordinals != tuple(range(1, len(ordinals) + 1)):
        raise ValueError(f"{name} ordinals must be contiguous")


__all__ = [
    "CampaignClass",
    "CampaignCostAssumption",
    "CampaignCostKind",
    "CampaignEvaluationProtocolBinding",
    "FormalResearchCampaignDefinition",
    "FormalDatasetScope",
]
