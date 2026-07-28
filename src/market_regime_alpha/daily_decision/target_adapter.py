"""Adapter from the unique MR1 10:30 identity into TargetProtocol."""

from __future__ import annotations

from hashlib import sha256
import json

from market_regime_alpha.candidates.contracts import (
    TargetContract,
)
from market_regime_alpha.candidates.dataset import (
    CandidateResearchDataset,
    TargetMaterialization,
    build_candidate_research_dataset,
)
from market_regime_alpha.core.identity import ArtifactId, TargetId, UniverseId
from market_regime_alpha.core.time import AsOfTime
from market_regime_alpha.features.daily_pipeline import DailyFeaturePipelineResult
from market_regime_alpha.platform.target_evaluation import (
    MissingTargetPolicy,
    PriceMark,
    ReturnBasis,
    TargetKind,
    TargetProtocol,
)
from market_regime_alpha.research.mr1_morning_pop import (
    MR1TargetId,
    MR1_EXACT_ENDPOINT_CONVENTION,
)
from market_regime_alpha.universe.daily_exploratory import (
    DailyUniverseReconciliation,
)


def mr1_next_session_1030_target_protocol(
    universe_id: UniverseId,
) -> TargetProtocol:
    """Describe MR1TargetId.NEXT_SESSION_1030_RETURN without a new Target ID."""

    return TargetProtocol(
        target_id=TargetId(MR1TargetId.NEXT_SESSION_1030_RETURN.value),
        name="MR1 Next-session 10:30 Return",
        version="mr1-adapter-v1",
        kind=TargetKind.RETURN,
        decision_time_convention="14:55 Asia/Shanghai exact Decision Price Snapshot",
        horizon="next trading session exact 10:30 five-minute endpoint",
        start_mark=PriceMark.DECISION_PRICE,
        end_mark=PriceMark.NEXT_1030,
        return_basis=ReturnBasis.ABSOLUTE,
        availability_rule=(
            f"{MR1_EXACT_ENDPOINT_CONVENTION}; exact 10:30 bar required; "
            "no later-bar substitution"
        ),
        adjustment_rule=(
            "decision and endpoint marks must declare compatible adjustment basis"
        ),
        missing_policy=MissingTargetPolicy.RETAIN_AS_UNRESOLVED,
        universe_id=universe_id,
        benchmark_ref=None,
        cost_adjusted=False,
        path_required=False,
    )


def mr1_next_session_1030_candidate_target_contract() -> TargetContract:
    """Expose the same MR1 identity through the existing Candidate Target contract."""

    return TargetContract(
        target_id=TargetId(MR1TargetId.NEXT_SESSION_1030_RETURN.value),
        name="MR1 Next-session 10:30 Return",
        horizon="next trading session exact 10:30 five-minute endpoint",
        outcome="exact 10:30 close / 14:55 Decision Price - 1",
        price_convention=MR1_EXACT_ENDPOINT_CONVENTION,
        decision_time_convention="14:55 Asia/Shanghai exact Decision Price Snapshot",
        population_scope="identified daily Candidate Population",
        version="mr1-adapter-v1",
    )


def build_pending_mr1_candidate_dataset(
    *,
    reconciliation: DailyUniverseReconciliation,
    feature_result: DailyFeaturePipelineResult,
    code_revision: str,
    config_hash: str,
) -> CandidateResearchDataset:
    """Build the existing CandidateResearchDataset with unresolved future Target cells."""

    if feature_result.population != reconciliation.population:
        raise ValueError("Feature and Universe Candidate Population mismatch")
    target_contract = mr1_next_session_1030_candidate_target_contract()
    identity_payload = {
        "schema_version": "pending-mr1-1030-target-materialization-v1",
        "target_id": str(target_contract.target_id),
        "source_dataset_id": str(reconciliation.dataset_contract.dataset_id),
        "universe_id": str(reconciliation.population.universe_id),
        "decision_time": reconciliation.population.decision_time.isoformat(),
        "population_symbols": list(reconciliation.population.symbols),
        "code_revision": code_revision,
        "config_hash": config_hash,
    }
    digest = sha256(
        json.dumps(
            identity_payload,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    pending = TargetMaterialization(
        artifact_id=ArtifactId(f"pending-target-{digest[:24]}"),
        target_id=target_contract.target_id,
        source_dataset_id=reconciliation.dataset_contract.dataset_id,
        universe_id=reconciliation.population.universe_id,
        decision_time=reconciliation.population.decision_time,
        materialized_at=AsOfTime(
            reconciliation.population.decision_time.value
        ),
        code_revision=code_revision,
        config_hash=config_hash,
        observations=(),
    )
    return build_candidate_research_dataset(
        population=reconciliation.population,
        dataset_contracts=(reconciliation.dataset_contract,),
        feature_definitions=feature_result.definitions,
        feature_materializations=feature_result.materializations,
        target_contract=target_contract,
        target_materialization=pending,
        limitations=(
            "EXPLORATORY_DAILY_LOOP",
            "MR1_1030_OUTCOME_NOT_YET_OBSERVED",
            "FORMAL_OOS_ALPHA_NOT_ESTABLISHED",
        ),
    )
