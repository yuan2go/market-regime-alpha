"""Direct exploratory R5 Feature and Target materialization for composite data."""

from __future__ import annotations

from datetime import date, datetime, time
from hashlib import sha256
import json
import math
from zoneinfo import ZoneInfo

from market_regime_alpha.candidates.contracts import CandidatePopulation, TargetContract
from market_regime_alpha.candidates.dataset import (
    CandidateResearchDataset,
    TargetMaterialization,
    TargetObservation,
    TargetObservationStatus,
    build_candidate_research_dataset,
)
from market_regime_alpha.candidates.rehearsal_opportunity_targets import (
    R5_NEXT_SESSION_MAE_TARGET_ID,
    R5_NEXT_SESSION_MFE_TARGET_ID,
    r5_next_session_opportunity_target_contracts,
)
from market_regime_alpha.candidates.rehearsal_targets import R5_NEXT_SESSION_RETURN_TARGET_ID
from market_regime_alpha.core.identity import (
    ArtifactId,
    DatasetId,
    FeatureDefinitionId,
    FeatureMaterializationId,
    TargetId,
    UniverseId,
)
from market_regime_alpha.core.status import InputAvailabilityStatus
from market_regime_alpha.core.time import (
    AsOfTime,
    AvailabilityTime,
    DecisionTime,
    RetrievedAt,
)
from market_regime_alpha.data.contracts import DataEligibility, DatasetContract
from market_regime_alpha.features.contracts import FeatureMaterialization, FeatureObservation
from market_regime_alpha.features.rehearsal_baselines import (
    calculate_r5_baseline_feature_values,
    r5_baseline_feature_definitions,
)
from market_regime_alpha.research.tencent_composite_contracts import PreparedCompositeData


SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


def materialize_tencent_composite_slice(
    *,
    prepared: PreparedCompositeData,
    decision_date: date,
    dataset_contract: DatasetContract,
    retrieved_at: RetrievedAt,
    code_revision: str,
    config_hash: str,
) -> tuple[CandidateResearchDataset, ...]:
    """Build the three R5 Target slices under an explicit exploratory ceiling."""

    if (
        dataset_contract.eligibility is not DataEligibility.EXPLORATORY
        or dataset_contract.pit_correct_for_scope
    ):
        raise ValueError("Tencent composite slice requires non-PIT EXPLORATORY DatasetContract")
    decision_time = DecisionTime(
        datetime.combine(decision_date, time(14, 55), tzinfo=SHANGHAI_TZ)
    )
    if retrieved_at.value <= decision_time.value:
        raise ValueError("retrieved_at must be after the historical Candidate Decision Time")
    if decision_date not in prepared.common_session_dates:
        raise KeyError(f"decision date unavailable: {decision_date.isoformat()}")

    next_date = prepared.next_session_date(decision_date)
    symbols = tuple(sorted(prepared.accepted_symbols))
    population = CandidatePopulation(
        universe_id=_universe_id(dataset_contract.dataset_id, decision_date, symbols),
        decision_time=decision_time,
        symbols=symbols,
        source_dataset_ids=(dataset_contract.dataset_id,),
    )
    feature_materializations = _materialize_features(
        prepared=prepared,
        population=population,
        source_dataset_id=dataset_contract.dataset_id,
        decision_date=decision_date,
        code_revision=code_revision,
        config_hash=config_hash,
    )
    targets = _materialize_targets(
        prepared=prepared,
        population=population,
        source_dataset_id=dataset_contract.dataset_id,
        decision_date=decision_date,
        next_date=next_date,
        retrieved_at=retrieved_at,
        code_revision=code_revision,
        config_hash=config_hash,
    )
    definitions = r5_baseline_feature_definitions()
    target_contracts = r5_next_session_opportunity_target_contracts()
    limitations = tuple(
        dict.fromkeys(
            (
                *dataset_contract.limitations,
                *prepared.limitations,
                "HISTORICAL_TARGET_OBSERVED_AT_IS_RUN_RETRIEVAL_TIME",
                "ACCEPTED_CURRENT_WATCHLIST_IS_NOT_PIT_TRADING_ELIGIBILITY",
            )
        )
    )
    return tuple(
        build_candidate_research_dataset(
            population=population,
            dataset_contracts=(dataset_contract,),
            feature_definitions=definitions,
            feature_materializations=feature_materializations,
            target_contract=target_contract,
            target_materialization=targets[target_contract.target_id],
            limitations=limitations,
        )
        for target_contract in target_contracts
    )


def _materialize_features(
    *,
    prepared: PreparedCompositeData,
    population: CandidatePopulation,
    source_dataset_id: DatasetId,
    decision_date: date,
    code_revision: str,
    config_hash: str,
) -> tuple[FeatureMaterialization, ...]:
    definitions = r5_baseline_feature_definitions()
    observations: dict[FeatureDefinitionId, list[FeatureObservation]] = {
        definition.feature_id: [] for definition in definitions
    }
    prior_dates = tuple(
        session_date
        for session_date in prepared.common_session_dates
        if session_date < decision_date
    )
    for symbol in population.symbols:
        prior = tuple(prepared.session_for(symbol, session_date) for session_date in prior_dates)
        current = prepared.session_for(symbol, decision_date)
        values = calculate_r5_baseline_feature_values(
            prior_closes=tuple(session.close for session in prior),
            prior_amounts=tuple(session.amount for session in prior),
            reference_price=current.reference_price,
        )
        for feature_id, value in values.items():
            observations[feature_id].append(_feature_observation(symbol, value))

    as_of = AsOfTime(population.decision_time.value)
    return tuple(
        FeatureMaterialization(
            materialization_id=FeatureMaterializationId(
                _stable_id(
                    "fm-tencent-composite",
                    {
                        "schema_version": "tencent-composite-feature-materialization-v1",
                        "definition_id": str(definition.feature_id),
                        "dataset_id": str(source_dataset_id),
                        "universe_id": str(population.universe_id),
                        "as_of": as_of.isoformat(),
                        "code_revision": code_revision,
                        "config_hash": config_hash,
                    },
                )
            ),
            definition_id=definition.feature_id,
            dataset_id=source_dataset_id,
            universe_id=population.universe_id,
            as_of=as_of,
            code_revision=code_revision,
            config_hash=config_hash,
            observations=tuple(observations[definition.feature_id]),
        )
        for definition in definitions
    )


def _materialize_targets(
    *,
    prepared: PreparedCompositeData,
    population: CandidatePopulation,
    source_dataset_id: DatasetId,
    decision_date: date,
    next_date: date,
    retrieved_at: RetrievedAt,
    code_revision: str,
    config_hash: str,
) -> dict[TargetId, TargetMaterialization]:
    target_contracts = r5_next_session_opportunity_target_contracts()
    observations: dict[TargetId, list[TargetObservation]] = {
        contract.target_id: [] for contract in target_contracts
    }
    observed_at = AvailabilityTime(retrieved_at.value)
    materialized_at = AsOfTime(retrieved_at.value)
    for symbol in population.symbols:
        reference_price = prepared.session_for(symbol, decision_date).reference_price
        future = prepared.session_for(symbol, next_date)
        values = {
            R5_NEXT_SESSION_RETURN_TARGET_ID: future.close / reference_price - 1.0,
            R5_NEXT_SESSION_MFE_TARGET_ID: max(0.0, future.high / reference_price - 1.0),
            R5_NEXT_SESSION_MAE_TARGET_ID: min(0.0, future.low / reference_price - 1.0),
        }
        for target_id, value in values.items():
            observations[target_id].append(
                TargetObservation(
                    symbol=symbol,
                    status=TargetObservationStatus.AVAILABLE,
                    value=float(value),
                    observed_at=observed_at,
                )
            )

    return {
        contract.target_id: _target_materialization(
            contract=contract,
            source_dataset_id=source_dataset_id,
            population=population,
            next_date=next_date,
            materialized_at=materialized_at,
            code_revision=code_revision,
            config_hash=config_hash,
            observations=tuple(observations[contract.target_id]),
        )
        for contract in target_contracts
    }


def _target_materialization(
    *,
    contract: TargetContract,
    source_dataset_id: DatasetId,
    population: CandidatePopulation,
    next_date: date,
    materialized_at: AsOfTime,
    code_revision: str,
    config_hash: str,
    observations: tuple[TargetObservation, ...],
) -> TargetMaterialization:
    payload = {
        "schema_version": "tencent-composite-target-materialization-v1",
        "target_id": str(contract.target_id),
        "source_dataset_id": str(source_dataset_id),
        "universe_id": str(population.universe_id),
        "decision_time": population.decision_time.isoformat(),
        "next_session_date": next_date.isoformat(),
        "materialized_at": materialized_at.isoformat(),
        "code_revision": code_revision,
        "config_hash": config_hash,
        "observations": [
            {
                "symbol": observation.symbol,
                "status": observation.status.value,
                "value": observation.value,
                "observed_at": observation.observed_at.isoformat()
                if observation.observed_at
                else None,
            }
            for observation in observations
        ],
    }
    return TargetMaterialization(
        artifact_id=ArtifactId(_stable_id("target-tencent-composite", payload)),
        target_id=contract.target_id,
        source_dataset_id=source_dataset_id,
        universe_id=population.universe_id,
        decision_time=population.decision_time,
        materialized_at=materialized_at,
        code_revision=code_revision,
        config_hash=config_hash,
        observations=observations,
    )


def _feature_observation(symbol: str, value: float | None) -> FeatureObservation:
    if value is None:
        return FeatureObservation(symbol, InputAvailabilityStatus.MISSING, None)
    if not math.isfinite(float(value)):
        return FeatureObservation(symbol, InputAvailabilityStatus.INVALID, None)
    return FeatureObservation(symbol, InputAvailabilityStatus.AVAILABLE, float(value))


def _universe_id(
    dataset_id: DatasetId,
    decision_date: date,
    symbols: tuple[str, ...],
) -> UniverseId:
    return UniverseId(
        _stable_id(
            "universe-tencent-composite",
            {
                "schema_version": "tencent-composite-accepted-watchlist-v1",
                "dataset_id": str(dataset_id),
                "decision_date": decision_date.isoformat(),
                "symbols": list(symbols),
            },
        )
    )


def _stable_id(prefix: str, payload: object) -> str:
    canonical = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    digest = sha256(canonical.encode("utf-8")).hexdigest()
    return f"{prefix}-{digest[:24]}"
