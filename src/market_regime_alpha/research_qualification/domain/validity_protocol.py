"""Append-only source declarations for exploratory Research Validity.

These resources are protocol code, not a replacement for registered Artifact or
Evaluation truth. Commands cannot supply arbitrary dates, parameters or files.
"""

from __future__ import annotations

from datetime import date, datetime
from hashlib import sha256
from importlib.resources import files
import json
from typing import Any

from market_regime_alpha.runtime.errors import ArtifactIntegrityError


# Published bytes are immutable. A revision adds a resource and predecessor;
# editing this entry cannot preserve the old protocol's content identity.
_PROTOCOL_HASHES = {
    1: "1414d39ab1082fffb1e45499c1ba2d93b1e54a442f58fe7a3cc68509d69c6944",
    2: "efb4b9683ccf6201b9c1e3cbe0eb32338559fc430756155b06374794ffdb52de",
}
CURRENT_PROTOCOL_VERSION = 2


def instant(value: Any) -> datetime:
    result = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("validity time must be timezone aware")
    return result


def validate_protocol_revision(protocol: dict[str, Any], predecessor: dict[str, Any] | None = None) -> None:
    declared = instant(protocol["declared_at"])
    first_start = instant(protocol["first_eligible_target_start"])
    if declared >= first_start:
        raise ValueError("PROTOCOL_DECLARATION_NOT_BEFORE_FUTURE_TARGET")
    if min(protocol[key] for key in ("minimum_sessions", "minimum_observations", "minimum_rank_pairs", "rolling_sessions")) < 3:
        raise ValueError("VALIDITY_MINIMUM_SAMPLE_INVALID")
    if protocol["slices"] != ["ALL_POPULATION"] or protocol["economic_assumptions"] is not None:
        raise ValueError("UNIMPLEMENTED_VALIDITY_SLICE_OR_ECONOMICS")
    if predecessor is None:
        if protocol["protocol_version"] != 1 or protocol["predecessor"] is not None:
            raise ValueError("PROTOCOL_PREDECESSOR_REQUIRED")
    elif (protocol["protocol_version"] != predecessor["protocol_version"] + 1
          or protocol["predecessor"] != predecessor["protocol_sha256"]
          or declared <= instant(predecessor["declared_at"])
          or date.fromisoformat(protocol["first_eligible_future_session"]) <= date.fromisoformat(predecessor["first_eligible_future_session"])):
        raise ValueError("PROTOCOL_REVISION_CANNOT_RELABEL_OLD_COHORT")
    if not protocol["reason"]:
        raise ValueError("PROTOCOL_REVISION_REASON_REQUIRED")


def _resource(version: int) -> tuple[dict[str, Any], str]:
    if version not in _PROTOCOL_HASHES:
        raise ValueError("UNDECLARED_VALIDITY_PROTOCOL")
    payload = files("market_regime_alpha").joinpath(f"research_qualification/protocols/validity_v{version}.json").read_bytes()
    digest = sha256(payload).hexdigest()
    if digest != _PROTOCOL_HASHES[version]:
        raise ArtifactIntegrityError("FROZEN_VALIDITY_PROTOCOL_BYTES_CHANGED")
    result = json.loads(payload)
    return result, digest


def load_validity_protocol(version: int = CURRENT_PROTOCOL_VERSION) -> dict[str, Any]:
    result, digest = _resource(version)
    validate_protocol_revision(result, load_validity_protocol(version - 1) if version > 1 else None)
    result["protocol_sha256"] = digest
    result["population_binding_state"] = "PASS" if "frozen_population_semantics" in result else "PROTOCOL_POPULATION_BINDING_INCOMPLETE"
    result["cohort_end_exclusive"] = _resource(version + 1)[0]["first_eligible_future_session"] if version + 1 in _PROTOCOL_HASHES else None
    return result


def require_frozen_protocol(protocol: dict[str, Any]) -> None:
    if protocol != load_validity_protocol(protocol["protocol_version"]):
        raise ArtifactIntegrityError("FROZEN_VALIDITY_PROTOCOL_CONTENT_MISMATCH")


def classify_cohort(protocol: dict[str, Any], session: date, target_start: datetime) -> str:
    if protocol["cohort_end_exclusive"] is not None and session >= date.fromisoformat(protocol["cohort_end_exclusive"]):
        return "OUTSIDE_PROTOCOL_COHORT"
    if session < date.fromisoformat(protocol["first_eligible_future_session"]):
        if protocol["protocol_version"] > 1 and session >= date.fromisoformat(load_validity_protocol(1)["first_eligible_future_session"]):
            return "PREDECESSOR_PROTOCOL_DESCRIPTIVE"
        return "POST_HOC_DESCRIPTIVE"
    if instant(protocol["declared_at"]) >= target_start:
        raise ArtifactIntegrityError("PREDECLARED_COHORT_TIME_CONFLICT")
    return "PREDECLARED_EXPLORATORY" if protocol["population_binding_state"] == "PASS" else "PREDECESSOR_PROTOCOL_DESCRIPTIVE"
