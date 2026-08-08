"""State-system repository contracts and content-validating Pool reader."""

from __future__ import annotations

from dataclasses import dataclass
import json
from enum import Enum
from typing import Any, Mapping

from market_regime_alpha.core.identity import ArtifactId
from market_regime_alpha.evidence.canonical import canonical_hash, require_sha256, require_text
from market_regime_alpha.research.state_system.common import StateLineage


class StateSystemConflict(RuntimeError):
    """Raised for stale CAS/fence or conflicting idempotency content."""


class StateSystemIntegrityError(RuntimeError):
    """Raised when durable state-system content fails Reader validation."""


class StateDomain(str, Enum):
    MARKET_REGIME = "MARKET_REGIME"
    ETF_ROTATION = "ETF_ROTATION"
    THEME_ROTATION = "THEME_ROTATION"
    CAPITAL_STATE = "CAPITAL_STATE"


@dataclass(frozen=True, slots=True)
class StateArtifactWrite:
    domain: StateDomain
    scope_key: str
    observation_id: ArtifactId
    observation_hash: str
    observation_payload: Mapping[str, Any]
    state_id: ArtifactId
    state_hash: str
    previous_state_id: ArtifactId | None
    effective_state: str
    state_payload: Mapping[str, Any]
    transition_id: ArtifactId
    transition_hash: str
    transition_payload: Mapping[str, Any]
    lineage: StateLineage

    def __post_init__(self) -> None:
        require_text("scope_key", self.scope_key)
        require_text("effective_state", self.effective_state)
        for label, digest, payload in (
            ("observation_hash", self.observation_hash, self.observation_payload),
            ("state_hash", self.state_hash, self.state_payload),
            ("transition_hash", self.transition_hash, self.transition_payload),
        ):
            require_sha256(label, digest)
            if canonical_hash(payload) != digest:
                raise ValueError(f"{label} does not match Artifact content")


def decode_and_verify_pool(pool_json: str) -> dict[str, Any]:
    try:
        payload = json.loads(pool_json)
    except (TypeError, json.JSONDecodeError) as exc:
        raise StateSystemIntegrityError("Dynamic Pool JSON is invalid") from exc
    if not isinstance(payload, dict):
        raise StateSystemIntegrityError("Dynamic Pool payload must be an object")
    if not isinstance(payload.get("pool_id"), str) or not isinstance(payload.get("pool_hash"), str):
        raise StateSystemIntegrityError("Dynamic Pool identity fields are invalid")
    digest = str(payload["pool_hash"])
    try:
        require_sha256("pool_hash", digest)
    except ValueError as exc:
        raise StateSystemIntegrityError("Dynamic Pool hash is invalid") from exc
    identity: Mapping[str, Any] = {
        key: value
        for key, value in payload.items()
        if key not in {"pool_id", "pool_hash", "created_at"}
    }
    if canonical_hash(identity) != digest:
        raise StateSystemIntegrityError("Dynamic Pool content hash mismatch")
    if payload["pool_id"] != f"dynamic-pool:{digest[7:]}":
        raise StateSystemIntegrityError("Dynamic Pool content identity mismatch")
    return payload
