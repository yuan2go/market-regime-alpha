"""Canonical aggregate identity for multi-scope Stateful Research stages."""

from __future__ import annotations

from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash, require_sha256


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


__all__ = ["scoped_state_stage_bundle_identity"]
