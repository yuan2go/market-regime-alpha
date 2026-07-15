"""R5 opportunity-profile Target materializers for controlled rehearsal research.

The bundle preserves three independent Target identities:
- next-session close return;
- next-session maximum favorable excursion (MFE);
- next-session maximum adverse excursion (MAE).

These are future research outcomes. MFE is not assumed executable at the session high and
MAE is not an automatic stop-loss policy.
"""

from __future__ import annotations

from datetime import date
from hashlib import sha256
import json
from zoneinfo import ZoneInfo

from market_regime_alpha.candidates.contracts import CandidatePopulation, TargetContract
from market_regime_alpha.candidates.dataset import (
    TargetMaterialization,
    TargetObservation,
    TargetObservationStatus,
)
from market_regime_alpha.candidates.rehearsal_targets import (
    R5_NEXT_SESSION_RETURN_TARGET_ID,
    r5_next_session_return_target_contract,
)
from market_regime_alpha.candidates.target_bundle import (
    TargetMaterializationBundle,
    bundle_target_materializations,
)
from market_regime_alpha.core.identity import ArtifactId, DatasetId, TargetId
from market_regime_alpha.core.time import AsOfTime, AvailabilityTime
from market_regime_alpha.data.rehearsal import RehearsalDecisionSnapshot, RehearsalNextSessionBar


R5_NEXT_SESSION_MFE_TARGET_ID = TargetId("target-r5-next-session-mfe-v1")
R5_NEXT_SESSION_MAE_TARGET_ID = TargetId("target-r5-next-session-mae-v1")
_SHANGHAI = ZoneInfo("Asia/Shanghai")


def r5_next_session_opportunity_target_contracts() -> tuple[TargetContract, ...]:
    """Return the minimum R5 opportunity-profile Target schema."""

    contracts = (
        r5_next_session_return_target_contract(),
        TargetContract(
            target_id=R5_NEXT_SESSION_MFE_TARGET_ID,
            name="R5 Next-Session Maximum Favorable Excursion",
            horizon="next-session",
            outcome="maximum favorable excursion",
            price_convention="max(0, next-session-high / decision-reference-price - 1)",
            decision_time_convention="14:55 Asia/Shanghai; feature side uses only information available by Decision Time",
            population_scope="complete eligible A-share Candidate Population at each Decision Time",
            version="v1",
        ),
        TargetContract(
            target_id=R5_NEXT_SESSION_MAE_TARGET_ID,
            name="R5 Next-Session Maximum Adverse Excursion",
            horizon="next-session",
            outcome="maximum adverse excursion",
            price_convention="min(0, next-session-low / decision-reference-price - 1)",
            decision_time_convention="14:55 Asia/Shanghai; feature side uses only information available by Decision Time",
            population_scope="complete eligible A-share Candidate Population at each Decision Time",
            version="v1",
        ),
    )
    return tuple(sorted(contracts, key=lambda contract: str(contract.target_id)))


def materialize_r5_next_session_opportunity_targets(
    *,
    population: CandidatePopulation,
    source_dataset_id: DatasetId,
    decision_snapshots: tuple[RehearsalDecisionSnapshot, ...],
    next_session_date: date,
    next_session_bars: tuple[RehearsalNextSessionBar, ...],
    materialized_at: AsOfTime,
    code_revision: str,
    config_hash: str,
) -> TargetMaterializationBundle:
    """Materialize Close Return, MFE, and MAE as independent Target artifacts."""

    _require_r5_decision_time(population)
    if not isinstance(next_session_date, date):
        raise TypeError("next_session_date must be a date")
    if next_session_date <= population.decision_time.value.date():
        raise ValueError("next_session_date must be after Candidate Decision Date")
    if materialized_at.value <= population.decision_time.value:
        raise ValueError("target materialization must occur after Candidate Decision Time")

    snapshot_by_symbol: dict[str, RehearsalDecisionSnapshot] = {}
    for snapshot in decision_snapshots:
        if snapshot.decision_time != population.decision_time:
            continue
        if snapshot.symbol in snapshot_by_symbol:
            raise ValueError(f"duplicate rehearsal Decision Time snapshot: {snapshot.symbol}")
        snapshot_by_symbol[snapshot.symbol] = snapshot

    bar_by_symbol: dict[str, RehearsalNextSessionBar] = {}
    for bar in next_session_bars:
        if bar.session_date != next_session_date:
            raise ValueError("next-session bar does not match resolved next_session_date")
        if bar.available_at.value <= population.decision_time.value:
            raise ValueError("next-session bar must become available after Decision Time")
        if bar.available_at.value > materialized_at.value:
            raise ValueError("next-session bar cannot be available after target materialization")
        if bar.symbol in bar_by_symbol:
            raise ValueError(f"duplicate rehearsal next-session bar: {bar.symbol}")
        bar_by_symbol[bar.symbol] = bar

    observations_by_target: dict[TargetId, list[TargetObservation]] = {
        R5_NEXT_SESSION_RETURN_TARGET_ID: [],
        R5_NEXT_SESSION_MFE_TARGET_ID: [],
        R5_NEXT_SESSION_MAE_TARGET_ID: [],
    }
    known_at = AvailabilityTime(materialized_at.value)

    for symbol in population.symbols:
        snapshot = snapshot_by_symbol.get(symbol)
        future_bar = bar_by_symbol.get(symbol)
        if snapshot is None:
            for observations in observations_by_target.values():
                observations.append(
                    TargetObservation(
                        symbol=symbol,
                        status=TargetObservationStatus.INVALID,
                        value=None,
                        observed_at=known_at,
                    )
                )
            continue
        if future_bar is None:
            for observations in observations_by_target.values():
                observations.append(
                    TargetObservation(
                        symbol=symbol,
                        status=TargetObservationStatus.MISSING,
                        value=None,
                        observed_at=known_at,
                    )
                )
            continue

        reference_price = float(snapshot.reference_price)
        values = {
            R5_NEXT_SESSION_RETURN_TARGET_ID: float(future_bar.close / reference_price - 1.0),
            R5_NEXT_SESSION_MFE_TARGET_ID: float(max(0.0, future_bar.high / reference_price - 1.0)),
            R5_NEXT_SESSION_MAE_TARGET_ID: float(min(0.0, future_bar.low / reference_price - 1.0)),
        }
        for target_id, value in values.items():
            observations_by_target[target_id].append(
                TargetObservation(
                    symbol=symbol,
                    status=TargetObservationStatus.AVAILABLE,
                    value=value,
                    observed_at=future_bar.available_at,
                )
            )

    contract_by_target = {
        contract.target_id: contract
        for contract in r5_next_session_opportunity_target_contracts()
    }
    materializations = tuple(
        _build_materialization(
            target_contract=contract_by_target[target_id],
            source_dataset_id=source_dataset_id,
            population=population,
            next_session_date=next_session_date,
            materialized_at=materialized_at,
            code_revision=code_revision,
            config_hash=config_hash,
            observations=tuple(observations_by_target[target_id]),
        )
        for target_id in sorted(observations_by_target, key=str)
    )
    return bundle_target_materializations(materializations)


def _build_materialization(
    *,
    target_contract: TargetContract,
    source_dataset_id: DatasetId,
    population: CandidatePopulation,
    next_session_date: date,
    materialized_at: AsOfTime,
    code_revision: str,
    config_hash: str,
    observations: tuple[TargetObservation, ...],
) -> TargetMaterialization:
    artifact_id = _target_artifact_id(
        target_id=target_contract.target_id,
        source_dataset_id=source_dataset_id,
        population=population,
        next_session_date=next_session_date,
        materialized_at=materialized_at,
        code_revision=code_revision,
        config_hash=config_hash,
        observations=observations,
    )
    return TargetMaterialization(
        artifact_id=artifact_id,
        target_id=target_contract.target_id,
        source_dataset_id=source_dataset_id,
        universe_id=population.universe_id,
        decision_time=population.decision_time,
        materialized_at=materialized_at,
        code_revision=code_revision,
        config_hash=config_hash,
        observations=observations,
    )


def _target_artifact_id(
    *,
    target_id: TargetId,
    source_dataset_id: DatasetId,
    population: CandidatePopulation,
    next_session_date: date,
    materialized_at: AsOfTime,
    code_revision: str,
    config_hash: str,
    observations: tuple[TargetObservation, ...],
) -> ArtifactId:
    payload = {
        "schema_version": "r5-opportunity-target-materialization-v1",
        "target_id": str(target_id),
        "source_dataset_id": str(source_dataset_id),
        "universe_id": str(population.universe_id),
        "decision_time": population.decision_time.isoformat(),
        "next_session_date": next_session_date.isoformat(),
        "materialized_at": materialized_at.isoformat(),
        "code_revision": code_revision,
        "config_hash": config_hash,
        "population_symbols": list(population.symbols),
        "observations": [
            {
                "symbol": observation.symbol,
                "status": observation.status.value,
                "value": observation.value,
                "observed_at": observation.observed_at.isoformat() if observation.observed_at else None,
            }
            for observation in observations
        ],
    }
    canonical = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    digest = sha256(canonical.encode("utf-8")).hexdigest()
    return ArtifactId(f"target-materialization-{digest[:24]}")


def _require_r5_decision_time(population: CandidatePopulation) -> None:
    local = population.decision_time.value.astimezone(_SHANGHAI)
    if (local.hour, local.minute, local.second, local.microsecond) != (14, 55, 0, 0):
        raise ValueError("R5 opportunity Target materializer requires 14:55:00 Asia/Shanghai Decision Time")
