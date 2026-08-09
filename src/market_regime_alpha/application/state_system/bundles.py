"""Canonical aggregate identity for multi-scope Stateful Research stages."""

from __future__ import annotations

from datetime import datetime

from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import (
    canonical_datetime,
    canonical_hash,
    require_sha256,
)


def state_research_pipeline_identity(
    *,
    run_id: ArtifactId,
    tick_id: ArtifactId,
    as_of_time: datetime,
    stages: tuple[tuple[str, ArtifactId, str, datetime], ...],
) -> tuple[ArtifactId, str]:
    """Recompute the exact ordered State pipeline aggregate identity."""

    # Signal and Forecast belong to Canonical Lifecycle.  STATE_SYSTEM owns the
    # observation-to-candidate boundary and therefore hashes only those seven
    # owner artifacts.
    expected_order = (
        "OBSERVATION",
        "MARKET_REGIME",
        "ETF_ROTATION",
        "THEME_ROTATION",
        "CAPITAL_STATE",
        "DYNAMIC_POOL",
        "CANDIDATE",
    )
    if tuple(item[0] for item in stages) != expected_order:
        raise ValueError("State pipeline stages must use the canonical order")
    for _, _, artifact_hash, available_at in stages:
        require_sha256("State pipeline stage hash", artifact_hash)
        if available_at > as_of_time:
            raise ValueError("State pipeline stage cannot be available after AsOfTime")
    payload = {
        "schema": "state_research_pipeline_result/v2",
        "run_id": str(run_id),
        "tick_id": str(tick_id),
        "as_of_time": canonical_datetime(as_of_time),
        "stages": [
            {
                "stage": stage,
                "artifact_id": str(artifact_id),
                "artifact_hash": artifact_hash,
                "available_at": canonical_datetime(available_at),
            }
            for stage, artifact_id, artifact_hash, available_at in stages
        ],
    }
    digest = canonical_hash(payload)
    return ArtifactId(f"state-research-chain:{digest[7:]}"), digest


def scoped_state_stage_bundle_identity(
    *,
    stage: str,
    members: tuple[tuple[ArtifactId, str, str], ...],
) -> tuple[ArtifactId, str]:
    """Bind the exact State ID/hash/scope set exposed by one pipeline stage."""

    if stage not in {"ETF_ROTATION", "THEME_ROTATION"}:
        raise ValueError("scoped State bundle only supports ETF/Theme rotation")
    ordered = tuple(sorted(members, key=lambda item: (item[2], str(item[0]))))
    if not ordered:
        raise ValueError("scoped State bundle requires at least one member")
    if len({str(item[0]) for item in ordered}) != len(ordered):
        raise ValueError("scoped State bundle State identities must be unique")
    if len({item[2] for item in ordered}) != len(ordered):
        raise ValueError("scoped State bundle scopes must be unique")
    for _, content_hash, scope in ordered:
        require_sha256("scoped State bundle member hash", content_hash)
        if not scope or scope != scope.strip():
            raise ValueError("scoped State bundle scope must be trimmed text")
    payload = {
        "schema_version": "state_research_scoped_bundle/v1",
        "stage": stage,
        "members": [
            {
                "state_id": str(state_id),
                "state_hash": content_hash,
                "scope_key": scope,
            }
            for state_id, content_hash, scope in ordered
        ],
    }
    digest = canonical_hash(payload)
    return (
        ArtifactId(f"state-research-{stage.lower()}-bundle:{digest[7:]}"),
        digest,
    )


__all__ = [
    "scoped_state_stage_bundle_identity",
    "state_research_pipeline_identity",
]
