"""Read-only Evaluation-owned validity interpretation of canonical observations.

No Provider acquisition, label calculation, protocol registration or business
writes occur here. Historical Evaluation metric truth is projected unchanged.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_EVEN, localcontext
from typing import Any
from uuid import UUID

from market_regime_alpha.research_qualification.domain.validity_protocol import classify_cohort, instant, require_frozen_protocol
from market_regime_alpha.research_qualification.domain.validity_readiness import readiness_matrix, walk_forward_readiness
from market_regime_alpha.research_qualification.domain.validity_statistics import ValidityPair, validity_statistics
from market_regime_alpha.research_qualification.domain.validity_temporal import temporal_integrity
from market_regime_alpha.runtime.errors import ArtifactIntegrityError
from market_regime_alpha.shared.hashing import canonical_json_sha256


def _decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    result = Decimal(str(value))
    return result if result.is_finite() else None


def _rate(numerator: int, denominator: int, kind: str) -> dict[str, Any]:
    with localcontext() as context:
        context.prec = 38
        context.rounding = ROUND_HALF_EVEN
        return {"numerator": numerator, "denominator": denominator, "denominator_kind": kind,
                "value": Decimal(numerator) / Decimal(denominator) if denominator else None,
                "state": "ESTIMABLE" if denominator else "NOT_ESTIMABLE",
                "reason_code": "EXACT_CANONICAL_ROSTER" if denominator else "EMPTY_DENOMINATOR"}


def _field(row: Any, key: str) -> Any:
    return row.get(key) if isinstance(row, dict) else getattr(row, key)


def _require_identity(cycle: dict[str, Any], protocol: dict[str, Any]) -> None:
    for key, expected in protocol.get("frozen_population_semantics", {}).items():
        if cycle["frozen_plan"]["plan"].get(key) != expected:
            raise ArtifactIntegrityError("VALIDITY_FROZEN_POPULATION_SEMANTICS_MISMATCH")
    if protocol.get("frozen_population_semantics"):
        expected_instruments = protocol["frozen_population_semantics"]["instrument_ids"]
        sampled = [str(_field(row, "instrument_id")) for row in cycle["publication"]["population"]]
        if sorted(sampled) != sorted(expected_instruments) or len(sampled) != len(set(sampled)):
            raise ArtifactIntegrityError("VALIDITY_SAMPLED_POPULATION_ROSTER_MISMATCH")
    identities = cycle["frozen_identities"]
    for protocol_key, key in (("model_version", "model"), ("experimental_model_use", "experimental_model_use"),
                              ("feature_definition", "feature"), ("target_definition", "target")):
        expected = protocol["identities"][protocol_key]
        identity_key = protocol_key + "_id"
        if (str(identities[key][identity_key]) != expected["id"]
                or str(identities[key]["content_sha256"]) != expected["content_sha256"]):
            raise ArtifactIntegrityError("VALIDITY_FROZEN_PROTOCOL_IDENTITY_MISMATCH")
    if str(cycle["publication"]["baseline_strategy_version_id"]) != protocol["baseline_strategy_version_id"]:
        raise ArtifactIntegrityError("VALIDITY_BASELINE_IDENTITY_MISMATCH")
    replay = cycle["replay"]
    if replay.get("matched") is not True or replay.get("mismatch_count") != 0 or replay.get("business_writes") != 0:
        raise ArtifactIntegrityError("VALIDITY_REPLAY_MISMATCH")


def _session(cycle: dict[str, Any], protocol: dict[str, Any]) -> tuple[dict[str, Any], tuple[ValidityPair, ...]]:
    _require_identity(cycle, protocol)
    temporal = temporal_integrity(cycle)
    invalid = {str(row["commitment_id"]): row["reason_codes"] for row in temporal["members"] if row["state"] != "VALID"}
    publication = cycle["publication"]
    labels = {str(row["commitment_id"]): row for row in cycle["labels"] if row["metric_code"] == protocol["target_metric_code"]}
    if len(labels) != sum(row["metric_code"] == protocol["target_metric_code"] for row in cycle["labels"]):
        raise ArtifactIntegrityError("VALIDITY_DUPLICATE_CANONICAL_LABEL")
    pairs = []
    exclusions = []
    model_estimable = baseline_estimable = label_estimable = 0
    for row in publication["predictions"]:
        commitment = row["commitment_id"]
        if commitment is None:
            continue
        identity = str(commitment)
        label = labels.get(identity)
        actual = _decimal(label["decimal_value"]) if label and label["value_status"] == "COMPLETE" and label["availability_status"] == "AVAILABLE" else None
        model = _decimal(row["point_estimate"]) if row["forecast_status"] == "AVAILABLE" else None
        baseline = _decimal(row["baseline_point_estimate"]) if row["baseline_status"] == "AVAILABLE" else None
        is_valid = identity not in invalid
        model_estimable += model is not None and actual is not None and is_valid
        baseline_estimable += baseline is not None and actual is not None and is_valid
        label_estimable += actual is not None
        reasons = list(invalid.get(identity, []))
        if actual is None:
            reasons.append("CANONICAL_LABEL_UNAVAILABLE")
        if model is None:
            reasons.append("MODEL_FORECAST_UNAVAILABLE")
        if baseline is None:
            reasons.append("BASELINE_FORECAST_UNAVAILABLE")
        if reasons:
            exclusions.append({"commitment_id": commitment, "instrument_id": row["instrument_id"], "reason_codes": reasons})
        else:
            assert model is not None and baseline is not None and actual is not None
            pairs.append(ValidityPair(commitment_id=UUID(identity), session=cycle["target_session"], model=model,
                                      baseline=baseline, label=actual, instrument_id=UUID(str(row["instrument_id"]))))
    counts = publication["denominators"]
    population = publication["population"]
    disposition_rows = [{key: _field(row, key) for key in ("instrument_id", "membership_status", "membership_reason", "eligibility_result", "eligibility_reason")}
                        for row in population]
    population_exclusions = [row for row in disposition_rows if row["membership_status"] != "INCLUDED" or row["eligibility_result"] != "ELIGIBLE"]
    expected = len(cycle["observations"])
    source_gaps = {str(row["commitment_id"]) for row in cycle["temporal_facts"]["outcome_observations"] if row.get("source_gap_id") is not None}
    unknown_labels = sum(row.get("availability_status") == "UNKNOWN" or row.get("value_status") == "UNKNOWN" for row in labels.values())
    unknown_finality = sum(row.get("finality_status") == "UNKNOWN" for row in labels.values())
    classification = classify_cohort(protocol, cycle["target_session"], instant(cycle["temporal_facts"]["target_start"]))
    result = {
        "target_session": cycle["target_session"], "prediction_id": cycle["prediction_id"],
        "classification": classification, "baseline_observation": "SESSION_1_BASELINE_OBSERVATION" if str(cycle["target_session"]) == "2026-09-10" else None,
        "population": {**counts, "published_commitments": expected, "canonical_label_estimable": label_estimable,
                       "model_estimable": model_estimable, "baseline_estimable": baseline_estimable, "common_estimable": len(pairs)},
        "data_quality": {
            "prediction_coverage": _rate(counts["model_prediction"], counts["sampled"], "ALL_SAMPLED"),
            "pair_coverage": _rate(len(pairs), expected, "PUBLISHED_COMMITMENTS"),
            "missingness": _rate(expected - label_estimable, expected, "PUBLISHED_COMMITMENTS"),
            "unknown_labels": _rate(unknown_labels, expected, "PUBLISHED_COMMITMENTS"),
            "unknown_membership": _rate(sum(row["membership_status"] == "UNKNOWN" for row in disposition_rows), counts["sampled"], "ALL_SAMPLED"),
            "unknown_finality": _rate(unknown_finality, expected, "PUBLISHED_COMMITMENTS"),
            "source_gap": _rate(len(source_gaps), expected, "PUBLISHED_COMMITMENTS"),
            "missingness_differential": {"model_missing": expected - model_estimable, "baseline_missing": expected - baseline_estimable,
                                         "model_minus_baseline_missing_count": baseline_estimable - model_estimable,
                                         "denominator": expected, "denominator_kind": "PUBLISHED_COMMITMENTS"},
            "publication_timeliness": _rate(int(instant(publication["published_at"]) <= instant(cycle["temporal_facts"]["target_start"])), 1, "PUBLISHED_SESSION"),
        },
        "temporal_integrity": temporal, "exclusions": exclusions, "sampled_exclusions": population_exclusions,
        "canonical_evaluation": cycle["evaluation"], "replay": cycle["replay"],
        "lineage": {"plan_sha256": cycle["plan_sha256"], "dataset_id": publication["dataset_id"], "decision_run_id": publication["decision_run_id"],
                    "forecast_group_id": publication["forecast_group_id"], "evaluation_id": cycle["replay"]["evaluation_id"],
                    "acquired_outcome_revision_ids": [row["market_target_outcome_revision_id"] for row in cycle["observations"]]},
    }
    return result, tuple(pairs)


def validity_report(observations: dict[str, Any], protocol: dict[str, Any], calendar: list[dict[str, Any]], *,
                    target_session_from: date | None = None, target_session_to: date | None = None) -> dict[str, Any]:
    require_frozen_protocol(protocol)
    if target_session_from and target_session_to and target_session_from > target_session_to:
        raise ValueError("INVALID_SESSION_RANGE")
    cycles = observations["cycles"]
    dates = [row["target_session"] for row in cycles]
    if len(dates) != len(set(dates)):
        raise ArtifactIntegrityError("VALIDITY_DUPLICATE_SESSION_POPULATION")
    rows: list[dict[str, Any]] = []
    pairs: list[ValidityPair] = []
    for cycle in sorted(cycles, key=lambda row: row["target_session"]):
        row, members = _session(cycle, protocol)
        rows.append(row)
        pairs.extend(members)
    first = date.fromisoformat(protocol["first_eligible_future_session"])
    formal_dates = {row["target_session"] for row in rows if row["classification"] == "PREDECLARED_EXPLORATORY"}
    historic_dates = {row["target_session"] for row in rows if row["classification"] == "POST_HOC_DESCRIPTIVE"}
    predecessor_dates = {row["target_session"] for row in rows if row["classification"] == "PREDECESSOR_PROTOCOL_DESCRIPTIVE"}
    formal_pairs = tuple(pair for pair in pairs if pair.session in formal_dates)
    historic_pairs = tuple(pair for pair in pairs if pair.session in historic_dates)
    predecessor_pairs = tuple(pair for pair in pairs if pair.session in predecessor_dates)
    closed = tuple(row["session_date"] for row in calendar if instant(row["close_at"]) <= instant(observations["observed_at"]))
    calendar_first = next((row for row in calendar if str(row["session_id"]) == protocol["first_eligible_target_session_id"]), None)
    if calendar_first is None or instant(calendar_first["open_at"]) != instant(protocol["first_eligible_target_start"]) or calendar_first["session_date"] != first:
        raise ArtifactIntegrityError("VALIDITY_PROTOCOL_CALENDAR_BINDING_MISMATCH")
    kwargs = {"minimum_sessions": protocol["minimum_sessions"], "minimum_observations": protocol["minimum_observations"],
              "rolling_sessions": protocol["rolling_sessions"], "ranking_k": protocol["ranking_k"], "quantiles": protocol["ranking_quantiles"]}
    end = date.fromisoformat(protocol["cohort_end_exclusive"]) if protocol["cohort_end_exclusive"] else None
    formal = validity_statistics(formal_pairs, session_roster=tuple(day for day in closed if day >= first and (end is None or day < end)), **kwargs)
    historic = validity_statistics(historic_pairs, **kwargs)
    formal_session_count = len({pair.session for pair in formal_pairs})
    meets_floor = formal_session_count >= protocol["minimum_sessions"] and len(formal_pairs) >= protocol["minimum_observations"]
    invalid_formal = sum(row["temporal_integrity"]["invalid_count"] for row in rows if row["target_session"] >= first)
    status = "VALIDITY_BASELINE_ESTABLISHED" if meets_floor and not invalid_formal else (
        "VALIDITY_EVIDENCE_ACCUMULATING" if formal_session_count else "INSUFFICIENT_OBSERVATIONS")
    filtered = target_session_from is not None or target_session_to is not None
    selected = [row for row in rows if (target_session_from is None or row["target_session"] >= target_session_from)
                and (target_session_to is None or row["target_session"] <= target_session_to)]
    complete_dates = set(dates)
    streak = best = 0
    for day in closed:
        streak = streak + 1 if day in complete_dates else 0
        best = max(best, streak)
    declared_dates = {row["target_session"] for row in rows} | {row["target_session"] for row in observations["unavailable"]}
    current_rows = [row for row in rows if row["target_session"] >= first and (end is None or row["target_session"] < end)]
    current_unavailable = [row for row in observations["unavailable"] if row["target_session"] >= first
                           and (end is None or row["target_session"] < end)]
    for row in current_unavailable:
        for key, expected in protocol.get("frozen_population_semantics", {}).items():
            if row["frozen_plan"]["plan"].get(key) != expected:
                raise ArtifactIntegrityError("VALIDITY_PENDING_POPULATION_SEMANTICS_MISMATCH")
    declared = len(current_rows) + len(current_unavailable)
    published = [cycle["publication"] for cycle in cycles if cycle["target_session"] >= first
                 and (end is None or cycle["target_session"] < end)]
    published.extend(row["publication"] for row in current_unavailable if row.get("publication") is not None)
    calendar_by_date = {row["session_date"]: row for row in calendar}
    calendar_by_id = {str(row["session_id"]): row for row in calendar}
    timely = sum(instant(row["published_at"]) <= instant(calendar_by_id[str(row["target_session_id"])]["open_at"])
                 for row in published)
    sampled = sum(row["population"]["sampled"] for row in current_rows) + sum(row["sampled"] for row in current_unavailable)
    use = cycles[0]["frozen_identities"]["experimental_model_use"] if cycles else None
    lifecycle: dict[str, Any] = {"state": "NOT_OBSERVED", "reason_code": "NO_COMPLETED_CANONICAL_MODEL_USE_BINDING"}
    if use is not None:
        lifecycle = {"valid_from": use["valid_from"], "expires_at": use["expires_at"],
                     "state": "ACTIVE" if instant(observations["observed_at"]) < instant(use["expires_at"]) else "EXPIRED",
                     "known_future_cohort_sessions_before_expiry": sum(day >= first and instant(row["open_at"]) < instant(use["expires_at"])
                                                                       for day, row in calendar_by_date.items()),
                     "known_calendar_through": max(calendar_by_date),
                     "reason_code": "NO_EXTENSION_OR_NEW_MODEL_USE_AUTHORIZED; FUTURE_COHORT_CAPACITY_NOT_ASSUMED"}
    return {
        "schema": "canonical-research-validity-report-v1", "protocol": protocol, "observed_at": observations["observed_at"],
        "RESEARCH_VALIDITY_STATUS": "DESCRIPTIVE" if filtered else status,
        "evidence_class": "DESCRIPTIVE_VIEW_NOT_COHORT_SELECTION" if filtered else "EXPLORATORY_RESEARCH_VALIDITY",
        "MODEL_VALUE": "NOT_ESTIMABLE" if not meets_floor else "REQUIRES_REPEATABLE_INFORMATION_GAIN_REVIEW",
        "ALPHA_PROVEN": "NO", "protocol_predeclared": protocol["population_binding_state"] == "PASS", "full_cohort_status": status,
        "session_cohort": [row["target_session"] for row in rows], "selected_view_sessions": [row["target_session"] for row in selected],
        "cohort_population": {"all_sampled": sampled, "declared_daily_requests": declared,
                              "model_estimable": sum(row["population"]["model_estimable"] for row in current_rows),
                              "baseline_estimable": sum(row["population"]["baseline_estimable"] for row in current_rows),
                              "common_estimable": len(formal_pairs)},
        "cohort_data_quality": {"publication_timeliness": _rate(timely, declared, "DECLARED_DAILY_REQUESTS_IN_PROTOCOL_COHORT"),
                                "prediction_coverage": _rate(sum(row["denominators"]["model_prediction"] for row in published), sampled, "ALL_SAMPLED_IN_DECLARED_COHORT"),
                                "evaluation_completion": _rate(len(current_rows), declared, "DECLARED_DAILY_REQUESTS_IN_PROTOCOL_COHORT")},
        "model_use_lifecycle": lifecycle,
        "per_session": selected, "predeclared": formal, "post_hoc_descriptive": historic,
        "predecessor_protocol_descriptive": validity_statistics(predecessor_pairs, **kwargs),
        "post_hoc_policy": "NEW_HISTORICAL_STATISTICS_NEVER_MUTATE_OR_UPGRADE_FROZEN_EVALUATION",
        "metric_authority": "canonical_evaluation projects original stored metrics exactly; validity statistics are separately versioned derived interpretation",
        "unavailable_sessions": observations["unavailable"], "planning_gaps": [day for day in closed if day >= first and day not in declared_dates],
        "canonical_observation_sha256": canonical_json_sha256(cycles), "canonical_observations": cycles,
        "operational_session_count": len(complete_dates), "predeclared_session_count": formal_session_count,
        "common_observation_count": len(formal_pairs), "sustained_consecutive_sessions": best,
        "sustained_current_streak": streak, "SUSTAINED_MULTI_DAY_PROOF": "PASS" if best >= 3 else "BLOCKED_BY_ELAPSED_REAL_TIME",
        "walk_forward": walk_forward_readiness(protocol, calendar, cycles, observed_at=instant(observations["observed_at"])), **readiness_matrix(),
        "reconciliation": {"matched": True, "mismatch_count": 0, "business_writes": 0,
                           "scope": "ORIGINAL_CANONICAL_COMPLETED_CYCLES_AND_REPORTS"}, "business_writes": 0,
    }
