"""Fail-closed temporal interpretation of exact acquired daily source facts."""

from __future__ import annotations

from typing import Any
from zoneinfo import ZoneInfo

from market_regime_alpha.research_qualification.domain.validity_protocol import instant


def temporal_integrity(cycle: dict[str, Any]) -> dict[str, Any]:
    facts = cycle["temporal_facts"]
    publication = cycle["publication"]
    reasons: list[str] = []
    try:
        cutoff = instant(publication["input_cutoff"])
        decision = instant(publication["decision_time"])
        published = instant(publication["published_at"])
        start, end = instant(facts["target_start"]), instant(facts["target_end"])
        if cycle["target_session"] != start.astimezone(ZoneInfo("Asia/Shanghai")).date():
            reasons.append("TARGET_SESSION_WINDOW_DATE_MISMATCH")
        if not cutoff <= decision < published <= start < end:
            reasons.append("DECISION_PUBLICATION_TARGET_ORDER_INVALID")
        if instant(facts["feature_known_at"]) > cutoff:
            reasons.append("FEATURE_NOT_KNOWN_AT_INPUT_CUTOFF")
        if instant(facts["model_recorded_at"]) > decision:
            reasons.append("MODEL_NOT_FROZEN_BEFORE_DECISION")
        if instant(facts["model_training_knowledge_cutoff"]) > cutoff:
            reasons.append("TRAINING_LABEL_KNOWLEDGE_AFTER_INPUT_CUTOFF")
        if instant(facts["dataset_frozen_at"]) > published:
            reasons.append("DATASET_NOT_FROZEN_BEFORE_PUBLICATION")
    except (ValueError, TypeError, KeyError):
        reasons.append("TEMPORAL_IDENTITY_UNAVAILABLE")
    commitments = {str(r["commitment_id"]) for r in cycle["observations"]}
    by_member: dict[str, list[str]] = {identity: list(reasons) for identity in commitments}
    observed: set[str] = set()
    for source in facts["outcome_observations"]:
        if source.get("source_role", source.get("checkpoint_role")) != "OUTCOME_OBSERVATION":
            continue
        identity = str(source["commitment_id"])
        if identity not in by_member:
            raise ValueError("TEMPORAL_SOURCE_OUTSIDE_ACQUIRED_ROSTER")
        observed.add(identity)
        try:
            requested = instant(source["capture_requested_at"])
            response = instant(source["capture_response_at"])
            recorded = instant(source["capture_recorded_at"])
            known = instant(source["known_at"])
            capture_known = instant(source["capture_known_at"])
            if not instant(facts["target_end"]) <= requested <= response <= recorded <= capture_known <= known:
                by_member[identity].append("OUTCOME_NOT_ACTUALLY_OBSERVED_AFTER_MATURITY")
            if not instant(facts["target_start"]) < known:
                by_member[identity].append("OUTCOME_KNOWLEDGE_BEFORE_TARGET")
        except (ValueError, TypeError, KeyError):
            by_member[identity].append("OUTCOME_OBSERVATION_TIME_UNAVAILABLE")
    for identity in commitments - observed:
        by_member[identity].append("OUTCOME_SOURCE_LINEAGE_UNAVAILABLE")
    members = [{"commitment_id": key, "state": "INVALID_FOR_VALIDITY" if values else "VALID",
                "action": "EXCLUDE_WITH_REASON" if values else "INCLUDE", "reason_codes": sorted(set(values))}
               for key, values in sorted(by_member.items())]
    invalid = sum(bool(row["reason_codes"]) for row in members)
    return {"state": "INVALID_FOR_VALIDITY" if invalid or reasons else ("PASS" if members else "NOT_ESTIMABLE"),
            "valid_count": len(members) - invalid, "invalid_count": invalid, "members": members,
            "session_reason_codes": sorted(set(reasons)), "formal_provider_pit_qualification": "NOT_ESTABLISHED"}
