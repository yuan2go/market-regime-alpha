"""Concrete controlled target materializer for the first R5 Candidate rehearsal.

The target is a forward research outcome. It does not define a mandatory holding period or
Exit time for a trading strategy.
"""

from __future__ import annotations

from datetime import date
from hashlib import sha256
import json

from market_regime_alpha.candidates.contracts import CandidatePopulation, TargetContract
from market_regime_alpha.candidates.dataset import (
    TargetMaterialization,
    TargetObservation,
    TargetObservationStatus,
)
from market_regime_alpha.core.identity import ArtifactId, DatasetId, TargetId
from market_regime_alpha.core.time import AsOfTime, AvailabilityTime
from market_regime_alpha.data.rehearsal import (
    RehearsalDecisionSnapshot,
    RehearsalNextSessionClose,
)


R5_NEXT_SESSION_RETURN_TARGET_ID = TargetId(
    "target-r5-decision-reference-to-next-session-close-return-v1"
)


def r5_next_session_return_target_contract() -> TargetContract:
    """Return the first R5 fixed-horizon rehearsal Target Contract."""

    return TargetContract(
        target_id=R5_NEXT_SESSION_RETURN_TARGET_ID,
        name="R5 Decision Reference to Next Session Close Return",
        horizon="next-session",
        outcome="forward return",
        price_convention="next-session-close / decision-reference-price - 1",
        decision_time_convention="14:55 Asia/Shanghai; only information available by Decision Time on feature side",
        population_scope="complete eligible A-share Candidate Population at each Decision Time",
        version="v1",
    )


def materialize_r5_next_session_return_target(
    *,
    population: CandidatePopulation,
    source_dataset_id: DatasetId,
    decision_snapshots: tuple[RehearsalDecisionSnapshot, ...],
    next_session_date: date,
    next_session_closes: tuple[RehearsalNextSessionClose, ...],
    materialized_at: AsOfTime,
    code_revision: str,
    config_hash: str,
) -> TargetMaterialization:
    """Materialize next-session close return for one Candidate Decision Time cross-section."""

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

    close_by_symbol: dict[str, RehearsalNextSessionClose] = {}
    for observation in next_session_closes:
        if observation.session_date != next_session_date:
            raise ValueError("next-session close does not match resolved next_session_date")
        if observation.available_at.value <= population.decision_time.value:
            raise ValueError("next-session close must become available after Decision Time")
        if observation.available_at.value > materialized_at.value:
            raise ValueError("next-session close cannot be available after target materialization")
        if observation.symbol in close_by_symbol:
            raise ValueError(f"duplicate rehearsal next-session close: {observation.symbol}")
        close_by_symbol[observation.symbol] = observation

    observations: list[TargetObservation] = []
    known_at = AvailabilityTime(materialized_at.value)
    for symbol in population.symbols:
        snapshot = snapshot_by_symbol.get(symbol)
        future_close = close_by_symbol.get(symbol)
        if snapshot is None:
            observations.append(
                TargetObservation(
                    symbol=symbol,
                    status=TargetObservationStatus.INVALID,
                    value=None,
                    observed_at=known_at,
                )
            )
            continue
        if future_close is None:
            observations.append(
                TargetObservation(
                    symbol=symbol,
                    status=TargetObservationStatus.MISSING,
                    value=None,
                    observed_at=known_at,
                )
            )
            continue
        observations.append(
            TargetObservation(
                symbol=symbol,
                status=TargetObservationStatus.AVAILABLE,
                value=float(future_close.close / snapshot.reference_price - 1.0),
                observed_at=future_close.available_at,
            )
        )

    target = r5_next_session_return_target_contract()
    artifact_id = _target_artifact_id(
        target_id=target.target_id,
        source_dataset_id=source_dataset_id,
        population=population,
        next_session_date=next_session_date,
        materialized_at=materialized_at,
        code_revision=code_revision,
        config_hash=config_hash,
        observations=tuple(observations),
    )
    return TargetMaterialization(
        artifact_id=artifact_id,
        target_id=target.target_id,
        source_dataset_id=source_dataset_id,
        universe_id=population.universe_id,
        decision_time=population.decision_time,
        materialized_at=materialized_at,
        code_revision=code_revision,
        config_hash=config_hash,
        observations=tuple(observations),
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
        "schema_version": "r5-next-session-target-materialization-v1",
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
