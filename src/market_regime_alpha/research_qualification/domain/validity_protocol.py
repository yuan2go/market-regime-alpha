"""Append-only source declarations for exploratory Research Validity.

These resources are protocol code, not a replacement for registered Artifact or
Evaluation truth. Commands cannot supply arbitrary dates, parameters or files.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, ROUND_FLOOR, localcontext
from hashlib import sha256
from importlib.resources import files
import json
from typing import Any
from zoneinfo import ZoneInfo

from market_regime_alpha.runtime.errors import ArtifactIntegrityError


# Published bytes are immutable. A revision adds a resource and predecessor;
# editing this entry cannot preserve the old protocol's content identity.
_PROTOCOL_HASHES = {
    1: "1414d39ab1082fffb1e45499c1ba2d93b1e54a442f58fe7a3cc68509d69c6944",
    2: "efb4b9683ccf6201b9c1e3cbe0eb32338559fc430756155b06374794ffdb52de",
    3: "39106ff7c6d1742761f73ceba937b99b21092a76ab136f0e2fe7ec2aa16fc53f",
}
CURRENT_PROTOCOL_VERSION = 3


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
    if protocol["protocol_version"] >= 3:
        _validate_capacity_revision(protocol, predecessor)


def _validate_capacity_revision(protocol: dict[str, Any], predecessor: dict[str, Any] | None) -> None:
    if predecessor is None:
        raise ValueError("PROTOCOL_PREDECESSOR_REQUIRED")
    for key in ("baseline_strategy_version_id", "formula_contract", "metric_roster", "minimum_sessions", "minimum_observations",
                "minimum_rank_pairs", "rolling_sessions", "ranking_k", "ranking_quantiles", "missingness_policy", "population",
                "slices", "unavailable_slices", "target_metric_code", "economic_assumptions", "economic_policy", "walk_forward"):
        if protocol[key] != predecessor[key]:
            raise ValueError("CAPACITY_REVISION_CANNOT_CHANGE_RESEARCH_SEMANTICS")
    for key in ("model_version", "feature_definition", "target_definition"):
        if protocol["identities"][key] != predecessor["identities"][key]:
            raise ValueError("CAPACITY_REVISION_CANNOT_CHANGE_RESEARCH_IDENTITY")
    if any(protocol["identities"]["experimental_model_use"][key] == predecessor["identities"]["experimental_model_use"][key]
           for key in ("id", "content_sha256")):
        raise ValueError("CAPACITY_REVISION_REQUIRES_SUCCESSOR_MODEL_USE")
    current_population = {key: value for key, value in protocol["frozen_population_semantics"].items() if key != "experimental_model_use_id"}
    previous_population = {key: value for key, value in predecessor["frozen_population_semantics"].items() if key != "experimental_model_use_id"}
    if current_population != previous_population:
        raise ValueError("CAPACITY_REVISION_CANNOT_CHANGE_POPULATION")
    if protocol["frozen_population_semantics"]["experimental_model_use_id"] != protocol["identities"]["experimental_model_use"]["id"]:
        raise ValueError("CAPACITY_REVISION_MODEL_USE_BINDING_MISMATCH")
    policy = protocol.get("capacity_policy")
    if (policy != {"downtime_buffer_sessions": 10, "missing_observation_buffer_fraction": "0.20", "expected_members_per_session": 32}
            or len(current_population["instrument_ids"]) != 32
            or len(set(current_population["instrument_ids"])) != 32):
        raise ValueError("CAPACITY_POLICY_NOT_FROZEN_OR_POPULATION_MISMATCH")


def _session_date(value: Any) -> date:
    if isinstance(value, datetime):
        raise ValueError("CAPACITY_REQUIRES_EXACT_SESSION_DATE")
    return value if isinstance(value, date) else date.fromisoformat(str(value))


def cohort_capacity(protocol: dict[str, Any], calendar: list[dict[str, Any]], model_use: dict[str, Any] | None, *,
                    observed_at: datetime, observed_sessions: tuple[date, ...] = (), observed_observations: int = 0,
                    pending_sessions: tuple[date, ...] = (), pending_observation_counts: dict[date, int] | None = None,
                    unavailable_sessions: tuple[date, ...] = (), calendar_coverage_witness: dict[str, Any] | None = None) -> dict[str, Any]:
    """Bound future capacity by captured sessions and an exact owner ModelUse.

    Bounds are scenario capacity, not promises of observations. Future slots use
    Target open >= Use valid_from and Target close <= expiry conservatively;
    already published pending work may still settle after expiry. No weekdays or
    missing calendar sessions are inferred. Historical protocol bytes stay fixed.
    """
    now = instant(observed_at)
    first = _session_date(protocol["first_eligible_future_session"])
    end = _session_date(protocol["cohort_end_exclusive"]) if protocol.get("cohort_end_exclusive") else None
    rows = {_session_date(row["session_date"]): row for row in calendar}
    if len(rows) != len(calendar) or len({str(row["session_id"]) for row in calendar}) != len(calendar):
        raise ArtifactIntegrityError("CAPACITY_DUPLICATE_CALENDAR_SESSION")
    if any(instant(row["open_at"]) >= instant(row["close_at"]) for row in calendar):
        raise ArtifactIntegrityError("CAPACITY_CALENDAR_INTERVAL_INVALID")
    observed = set(observed_sessions)
    pending = set(pending_sessions)
    unavailable = set(unavailable_sessions)
    pending_counts = pending_observation_counts or {}
    if (set(pending_counts) != pending or len(unavailable) != len(unavailable_sessions)
            or unavailable & (observed | pending)
            or any(day not in rows or day < first or (end is not None and day >= end) for day in unavailable)):
        raise ArtifactIntegrityError("CAPACITY_PENDING_EXACT_ROSTER_REQUIRED")
    if (len(observed) != len(observed_sessions) or len(pending) != len(pending_sessions) or observed & pending
            or type(observed_observations) is not int or observed_observations < 0
            or any(day not in rows or day < first or (end is not None and day >= end) for day in observed | pending)):
        raise ArtifactIntegrityError("CAPACITY_OBSERVATION_ROSTER_INVALID")
    members = len(protocol.get("frozen_population_semantics", {}).get("instrument_ids", ()))
    if any(type(count) is not int or not 1 <= count <= members for count in pending_counts.values()):
        raise ArtifactIntegrityError("CAPACITY_PENDING_OBSERVATION_COUNT_INVALID")
    if ((not observed and observed_observations) or observed_observations < len(observed)
            or (members and observed_observations > len(observed) * members)):
        raise ArtifactIntegrityError("CAPACITY_OBSERVATION_COUNT_INVALID")
    if any(instant(rows[day]["close_at"]) > now for day in observed):
        raise ArtifactIntegrityError("CAPACITY_OBSERVATIONS_PRECEDE_TARGET_MATURITY")
    base = {"minimum_sessions": protocol["minimum_sessions"], "minimum_observations": protocol["minimum_observations"],
            "observed_lower_bound": {"sessions": len(observed), "observations": observed_observations},
            "expected_members_per_session": members or None,
            "authority": "READ_ONLY_COHORT_CAPACITY_SCENARIO; NOT_FUTURE_OBSERVATION_OR_MODEL_VALUE",
            "session_window_policy": "FUTURE_TARGET_OPEN_GE_USE_VALID_FROM_AND_TARGET_CLOSE_LE_USE_EXPIRY; PUBLISHED_WORK_MAY_SETTLE_AFTER_EXPIRY"}
    if model_use is None or not members:
        reason = "MODEL_USE_OWNER_BINDING_UNAVAILABLE" if model_use is None else "PROTOCOL_POPULATION_BINDING_INCOMPLETE"
        return {**base, "COHORT_CAPACITY_FEASIBILITY": "NOT_ESTIMABLE", "state": "NOT_ESTIMABLE", "reason_codes": [reason],
                "possible": {"state": "NOT_ESTIMABLE", "reason_codes": [reason]},
                "robust": {"state": "NOT_ESTIMABLE", "reason_codes": [reason]},
                "model_use_lifecycle": {"state": "NOT_OBSERVED", "reason_code": reason}}
    expected = protocol["identities"]["experimental_model_use"]
    if (str(model_use["experimental_model_use_id"]) != expected["id"] or str(model_use["content_sha256"]) != expected["content_sha256"]
            or str(model_use["model_version_id"]) != protocol["identities"]["model_version"]["id"]):
        raise ArtifactIntegrityError("CAPACITY_MODEL_USE_OWNER_IDENTITY_MISMATCH")
    valid_from, expires = instant(model_use["valid_from"]), instant(model_use["expires_at"])
    registered = instant(model_use["registered_at"])
    revoked = instant(model_use["revoked_at"]) if model_use.get("revoked_at") else None
    if valid_from >= expires or registered > now or (revoked is not None and revoked > now):
        raise ArtifactIntegrityError("CAPACITY_MODEL_USE_OWNER_TIME_INVALID")
    lifecycle_state = "REVOKED" if revoked is not None and revoked <= now else "EXPIRED" if now >= expires else "NOT_YET_VALID" if now < valid_from else "ACTIVE"
    eligible = {day: row for day, row in rows.items() if day >= first and (end is None or day < end)
                and instant(row["open_at"]) >= valid_from and instant(row["close_at"]) <= expires}
    future = {day for day, row in eligible.items() if instant(row["open_at"]) > now
              and day not in observed | pending | unavailable}
    if revoked is not None and revoked <= now:
        future.clear()
    available = future | pending
    if observed & available:
        raise ArtifactIntegrityError("CAPACITY_DOUBLE_COUNTED_SESSION")
    coverage_complete = False
    witness_state = "NOT_OBSERVED"
    if calendar_coverage_witness is not None:
        witness = calendar_coverage_witness
        if witness.get("state") != "VERIFIED":
            witness_state = "NOT_VERIFIED"
        else:
            coverage_from = _session_date(witness["coverage_from"])
            coverage_through = _session_date(witness["coverage_through"])
            ids = [str(value) for value in witness["session_ids"]]
            expected_ids = {str(row["session_id"]) for day, row in rows.items() if coverage_from <= day <= coverage_through}
            if (coverage_from > coverage_through or instant(witness["known_at"]) > now or not witness["capture_id"]
                    or len(ids) != len(set(ids)) or set(ids) != expected_ids):
                raise ArtifactIntegrityError("CAPACITY_CALENDAR_COVERAGE_WITNESS_MISMATCH")
            witness_state = "VERIFIED"
            required_through = (min(expires.astimezone(ZoneInfo("Asia/Shanghai")).date(), end)
                                if end is not None else expires.astimezone(ZoneInfo("Asia/Shanghai")).date())
            coverage_complete = coverage_from <= first and coverage_through >= required_through
    possible_sessions = len(observed) + len(available)
    possible_observations = observed_observations + len(future) * members + sum(pending_counts.values())
    possible_pass = possible_sessions >= protocol["minimum_sessions"] and possible_observations >= protocol["minimum_observations"]
    initial_pass = len(eligible) >= protocol["minimum_sessions"] and len(eligible) * members >= protocol["minimum_observations"]
    failure = ("CALENDAR_COVERAGE_INSUFFICIENT" if not coverage_complete else
               "MODEL_USE_LIFETIME_INSUFFICIENT" if not initial_pass else "REMAINING_MODEL_USE_CAPACITY_INSUFFICIENT")
    possible_reasons = [] if possible_pass else [failure]
    if unavailable and not possible_pass:
        possible_reasons.append("UNAVAILABLE_WORK_NOT_ADMITTED_TO_CAPACITY")
    if lifecycle_state == "REVOKED" and not possible_pass:
        possible_reasons.append("MODEL_USE_REVOKED_NO_NEW_PREDICTIONS")
    policy = protocol.get("capacity_policy")
    robust: dict[str, Any] = {"state": "NOT_ESTIMABLE", "reason_codes": ["CAPACITY_BUFFER_NOT_PREDECLARED"]}
    if policy is not None:
        if (set(policy) != {"downtime_buffer_sessions", "missing_observation_buffer_fraction", "expected_members_per_session"}
                or type(policy["downtime_buffer_sessions"]) is not int or policy["downtime_buffer_sessions"] < 0
                or policy["expected_members_per_session"] != members):
            raise ArtifactIntegrityError("CAPACITY_POLICY_POPULATION_MISMATCH")
        fraction = Decimal(str(policy["missing_observation_buffer_fraction"]))
        if not fraction.is_finite() or not Decimal(0) <= fraction < Decimal(1):
            raise ArtifactIntegrityError("CAPACITY_MISSINGNESS_BUFFER_INVALID")
        # Discard the largest slot capacities first: the downtime buffer must
        # not inflate the remaining observation ceiling for partial rosters.
        slot_counts = sorted([members] * len(future) + list(pending_counts.values()))
        buffered_slots = max(0, len(slot_counts) - policy["downtime_buffer_sessions"])
        buffered_capacity = sum(slot_counts[:buffered_slots])
        with localcontext() as context:
            context.prec = 38
            buffered_observations = observed_observations + int((Decimal(buffered_capacity) * (1 - fraction)).to_integral_value(rounding=ROUND_FLOOR))
        buffered_sessions = len(observed) + buffered_slots
        robust_pass = buffered_sessions >= protocol["minimum_sessions"] and buffered_observations >= protocol["minimum_observations"]
        robust = {"state": "PASS" if robust_pass else "FAIL", "reason_codes": [] if robust_pass else ["PREDECLARED_BUFFER_CAPACITY_INSUFFICIENT"],
                  "policy": policy, "scenario_sessions": buffered_sessions, "scenario_observations": buffered_observations,
                  "guaranteed_observations": False}
    state = "PASS" if possible_pass and (policy is None or robust["state"] == "PASS") else "FAIL"
    cohort_end_reason = ("MODEL_USE_REVOKED" if lifecycle_state == "REVOKED" else
                         "MODEL_USE_EXPIRED" if lifecycle_state == "EXPIRED" else
                         "SUCCESSOR_COHORT_BOUNDARY" if end is not None and now.astimezone(ZoneInfo("Asia/Shanghai")).date() >= end else
                         "COHORT_NOT_STARTED" if now.astimezone(ZoneInfo("Asia/Shanghai")).date() < first else
                         "OPEN_FOR_CANONICAL_OBSERVATIONS")
    return {**base, "COHORT_CAPACITY_FEASIBILITY": state, "state": state,
            "first_eligible_target_session": first, "cohort_end_reason": cohort_end_reason,
            "reason_codes": possible_reasons + (robust["reason_codes"] if policy is not None else []),
            "possible": {"state": "PASS" if possible_pass else "FAIL", "reason_codes": possible_reasons}, "robust": robust,
            "initial_theoretical_capacity": {"known_sessions": len(eligible), "known_observation_upper_bound": len(eligible) * members,
                                             "session_roster": sorted(eligible), "ignores_elapsed_missed_opportunities": True},
            "remaining_attainable": {"known_remaining_sessions": len(available), "future_session_roster": sorted(future),
                                     "published_pending_session_roster": sorted(pending), "known_maximum_sessions": possible_sessions,
                                     "pending_exact_observation_counts": pending_counts,
                                     "unavailable_session_roster": sorted(unavailable),
                                     "unavailable_capacity_policy": "NO_REPLACEMENT_OR_ASSUMED_RECOVERY; EXCLUDED_UNTIL_CANONICAL_COMPLETION",
                                     "known_observation_upper_bound": possible_observations,
                                     "maximum_sessions": possible_sessions if coverage_complete and not unavailable else None,
                                     "maximum_observations": possible_observations if coverage_complete and not unavailable else None,
                                     "remaining_required_sessions": max(0, protocol["minimum_sessions"] - len(observed)),
                                     "remaining_required_observations": max(0, protocol["minimum_observations"] - observed_observations)},
            "calendar": {"known_calendar_through": max(rows) if rows else None, "coverage_witness_state": witness_state,
                         "use_lifetime_coverage_complete": coverage_complete, "coverage_witness": calendar_coverage_witness,
                         "coverage_scope": "THIS_VERIFIED_CAPTURE_INTERVAL; KNOWN_SESSION_CAPACITY_USES_ALL_CANONICAL_CALENDAR_FACTS"},
            "model_use_lifecycle": {"state": lifecycle_state, "valid_from": valid_from, "expires_at": expires,
                                    "registered_at": registered, "revoked_at": revoked,
                                    "known_future_cohort_sessions_before_expiry": len(eligible),
                                    "known_calendar_through": max(rows) if rows else None,
                                    "reason_code": "EXACT_CANONICAL_MODEL_USE; NO_LIFETIME_EXTENSION_OR_WEEKDAY_INFERENCE"}}


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
