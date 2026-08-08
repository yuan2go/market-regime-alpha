"""Explicit non-authoritative selector fixture for DailyLoop unit tests only."""

from __future__ import annotations

from dataclasses import dataclass

from market_regime_alpha.core.identity import ArtifactId, ModelId
from market_regime_alpha.platform.candidate_prediction_adapter import (
    B0_MOMENTUM_MODEL_ID,
    B1_BALANCED_MODEL_ID,
)
from market_regime_alpha.data.contracts import DataEligibility
from market_regime_alpha.evidence.canonical import canonical_hash
from market_regime_alpha.platform.contracts import ModelLifecycleStatus
from market_regime_alpha.platform.runtime_governance import (
    AssignmentLane,
    ModelGovernancePolicy,
    ModelRuntimeAssignment,
    ModelSelectionReceipt,
    ModelSelectionRequest,
    QualificationEvidenceKind,
    RuntimePurpose,
)


class EngineeringFixtureModelSelector:
    """Return typed fixture receipts; never used by a composition root."""

    def __init__(self) -> None:
        self._receipts: dict[ArtifactId, ModelSelectionReceipt] = {}

    def resolve_champion(self, *, model_slot: str, **_: object) -> _FixtureChampion:
        return _FixtureChampion(
            B0_MOMENTUM_MODEL_ID
            if model_slot == "DAILY_B0"
            else B1_BALANCED_MODEL_ID
        )

    def select(self, request: ModelSelectionRequest) -> ModelSelectionReceipt:
        if request.purpose is not RuntimePurpose.RESEARCH:
            raise ValueError("engineering fixture is Research-only")
        policy = ModelGovernancePolicy.create(
            name="engineering-fixture-research-policy",
            version="1",
            purpose=RuntimePurpose.RESEARCH,
            allowed_lifecycle_statuses=(ModelLifecycleStatus.RESEARCH,),
            required_evidence_kinds=(
                QualificationEvidenceKind.IMPLEMENTATION_REPRODUCIBILITY,
            ),
            allowed_data_eligibilities=(DataEligibility.EXPLORATORY,),
            production_authorization=False,
        )
        champion = ModelRuntimeAssignment.create(
            runtime_scope=request.runtime_scope,
            model_slot=request.model_slot,
            purpose=request.purpose,
            lane=AssignmentLane.CHAMPION,
            model_id=request.runtime_lineage.model_id,
            definition_hash=request.runtime_lineage.definition_hash,
            policy_id=policy.policy_id,
            policy_hash=policy.policy_hash,
            effective_at=request.selected_at,
            actor="pytest-fixture",
            reason="DailyLoop unit-test model authority fixture",
            approval_ref="fixture:non-authoritative",
            governance_revision=1,
        )
        receipt = ModelSelectionReceipt.accepted(
            request_hash=request.request_hash,
            runtime_scope=request.runtime_scope,
            model_slot=request.model_slot,
            purpose=request.purpose,
            governance_revision=1,
            policy=policy,
            champion=champion,
            challengers=(),
            qualification_decision_id=ArtifactId(
                f"fixture-qualification:{request.runtime_lineage.model_id}"
            ),
            qualification_decision_hash=canonical_hash(
                {
                    "fixture": "qualification",
                    "model_id": str(request.runtime_lineage.model_id),
                }
            ),
            selected_registry_version=1,
            runtime_lineage_hash=request.runtime_lineage.runtime_lineage_hash,
            evidence_ids=(
                ArtifactId(f"fixture-evidence:{request.runtime_lineage.model_id}"),
            ),
            selected_at=request.selected_at,
            production_authorized=False,
        )
        self._receipts[receipt.receipt_id] = receipt
        return receipt

    def replay_selection(
        self, receipt_id: ArtifactId
    ) -> ModelSelectionReceipt:
        return self._receipts[receipt_id]


FIXTURE_MODEL_SELECTOR = EngineeringFixtureModelSelector()


@dataclass(frozen=True)
class _FixtureChampion:
    model_id: ModelId
