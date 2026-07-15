"""Bundles of independently identified Candidate Target Materializations.

A bundle is a reproducibility convenience, not one merged target. Every member keeps its
own Target Identity, artifact identity, observation semantics, and evaluation meaning.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json

from market_regime_alpha.candidates.dataset import TargetMaterialization
from market_regime_alpha.core.identity import ArtifactId, TargetId, UniverseId
from market_regime_alpha.core.time import DecisionTime


@dataclass(frozen=True, slots=True)
class TargetMaterializationBundle:
    """One Decision Time bundle of independent Target Materializations."""

    artifact_id: ArtifactId
    universe_id: UniverseId
    decision_time: DecisionTime
    materializations: tuple[TargetMaterialization, ...]

    def __post_init__(self) -> None:
        if not self.materializations:
            raise ValueError("Target Materialization bundle must not be empty")
        target_ids = tuple(item.target_id for item in self.materializations)
        if len(target_ids) != len(set(target_ids)):
            raise ValueError("Target Materialization bundle target identities must be unique")
        artifact_ids = tuple(item.artifact_id for item in self.materializations)
        if len(artifact_ids) != len(set(artifact_ids)):
            raise ValueError("Target Materialization bundle artifact identities must be unique")
        if tuple(sorted(target_ids, key=str)) != target_ids:
            raise ValueError("Target Materialization bundle must be ordered by Target Identity")
        for materialization in self.materializations:
            if materialization.universe_id != self.universe_id:
                raise ValueError("Target Materialization bundle universe mismatch")
            if materialization.decision_time != self.decision_time:
                raise ValueError("Target Materialization bundle Decision Time mismatch")

    @property
    def target_ids(self) -> tuple[TargetId, ...]:
        return tuple(item.target_id for item in self.materializations)

    def get(self, target_id: TargetId) -> TargetMaterialization:
        for materialization in self.materializations:
            if materialization.target_id == target_id:
                return materialization
        raise KeyError(str(target_id))


def bundle_target_materializations(
    materializations: tuple[TargetMaterialization, ...],
) -> TargetMaterializationBundle:
    """Create a deterministic bundle without collapsing member Target identities."""

    if not materializations:
        raise ValueError("Target Materialization bundle must not be empty")
    ordered = tuple(sorted(materializations, key=lambda item: str(item.target_id)))
    universe_id = ordered[0].universe_id
    decision_time = ordered[0].decision_time
    for materialization in ordered[1:]:
        if materialization.universe_id != universe_id:
            raise ValueError("Target Materializations must share one Universe Identity")
        if materialization.decision_time != decision_time:
            raise ValueError("Target Materializations must share one Decision Time")

    payload = {
        "schema_version": "target-materialization-bundle-v1",
        "universe_id": str(universe_id),
        "decision_time": decision_time.isoformat(),
        "members": [
            {
                "target_id": str(materialization.target_id),
                "artifact_id": str(materialization.artifact_id),
            }
            for materialization in ordered
        ],
    }
    canonical = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    digest = sha256(canonical.encode("utf-8")).hexdigest()
    return TargetMaterializationBundle(
        artifact_id=ArtifactId(f"target-bundle-{digest[:24]}"),
        universe_id=universe_id,
        decision_time=decision_time,
        materializations=ordered,
    )
