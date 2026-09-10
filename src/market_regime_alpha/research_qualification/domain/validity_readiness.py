"""Research boundary readiness, distinct from training or qualification."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from market_regime_alpha.research_qualification.domain.validity_protocol import instant
from market_regime_alpha.research_qualification.domain.validity_temporal import temporal_integrity


def readiness_matrix() -> dict[str, Any]:
    economics = {
        "turnover": ("IMPLEMENTED", "evaluation_formula.py", "NO_CONTINUOUS_HOLDING_OR_FILL_PATH"),
        "transaction_cost": ("IMPLEMENTED", "evaluation_formula.py", "NO_FROZEN_DAILY_COST_ASSUMPTIONS"),
        "slippage": ("IMPLEMENTED", "episode_economics.py", "EPISODE_V2_ZERO_SLIPPAGE_ONLY_NOT_EMPIRICAL_EVIDENCE"),
        "suspension": ("WIRED", "baostock_archive_normalizer.py", "INPUT_ELIGIBILITY_NOT_TARGET_EXECUTION"),
        "limit_up_down": ("IMPLEMENTED", "eligibility_vocabulary.py", "NO_TARGET_ORDERABILITY_BINDING"),
        "liquidity": ("WIRED", "baostock_archive_normalizer.py", "INPUT_AMOUNT_NOT_EXECUTION_CAPACITY"),
        "tradability": ("NOT_READY", "xuntou_pit_v4_contract.py", "HISTORICAL_CONTRACT_NOT_CURRENT_CAPTURE"),
        "position_size_capacity": ("IMPLEMENTED", "decision_support/domain/risk.py", "NO_POSITION_OR_IMPACT_ASSUMPTIONS"),
        "t_plus_one": ("IMPLEMENTED", "position/authority.py", "SEPARATE_ACCOUNT_OWNER_NOT_INTRADAY_ROUND_TRIP_AUTHORITY"),
        "independent_episode_economics": ("WIRED", "evaluation_economics.py", "GENERIC_EVALUATION_ONLY_NOT_DAILY_PROTOCOL"),
    }
    pit = {
        "historical_coverage": "NO_CANONICAL_XUNTou_CAPTURE_ROSTER",
        "realtime_availability": "NO_NATIVE_PROVIDER_AVAILABILITY_COHORT",
        "known_time": "LOCAL_RECORDING_IS_NOT_HISTORICAL_PROVIDER_KNOWLEDGE",
        "revision_finality": "BAOSTOCK_FINALITY_UNKNOWN",
        "suspension_adjustment": "NO_FORMAL_PIT_STATUS_OR_ADJUSTMENT_BINDING",
        "trading_calendar": "CAPTURED_CALENDAR_NOT_FORMAL_PROVIDER_QUALIFICATION",
        "classification": "NO_FORMAL_HISTORICAL_MEMBERSHIP_PIT",
        "corporate_action": "NO_COMPLETE_ACTION_REVISION_AVAILABILITY_COHORT",
        "rate_limits": "NO_NATIVE_XUNTou_LIMIT_OR_THROTTLE_EVIDENCE",
        "recovery": "RUNTIME_CONTRACT_EXISTS_NATIVE_PROVIDER_RECOVERY_UNOBSERVED",
    }
    return {
        "ECONOMIC_VALIDITY_READINESS": "NOT_READY",
        "economics": [{"capability": key, "implementation_state": value[0], "source": value[1],
                       "wired_to_daily_economics": False, "observed_daily_economics": False,
                       "state": "NOT_READY", "reason_code": value[2]} for key, value in economics.items()],
        "episode_boundary": "FULLY_FUNDED_INDEPENDENT_HYPOTHETICAL_EPISODES != CONTINUOUS_ACCOUNT_NAV_OR_REAL_PNL",
        "FORMAL_PIT_READINESS": "NOT_READY", "PROVIDER_EVIDENCE_CLASS": "EXPLORATORY",
        "formal_pit": [{"capability": key, "state": "NOT_READY", "reason_code": value.upper()} for key, value in pit.items()],
        "regime_slice_state": "REGIME_SLICE_NOT_READY",
        "slice_policy": "ALL_POPULATION_ONLY; existing Context owner is wired, but no extra PIT-bound slice roster is declared",
        "unavailable_metrics": [{"metric": key, "state": "NOT_ESTIMABLE", "reason_code": reason} for key, reason in (
            ("net_return_assumed_cost", "NO_FROZEN_ECONOMIC_ASSUMPTIONS"),
            ("continuous_turnover", "NO_POSITION_PATH"),
            ("tradable_alpha", "NO_STRATEGY_OR_FORMAL_PIT_QUALIFICATION"),
            ("inferential_confidence_interval", "SESSION_INDEPENDENCE_NOT_ESTABLISHED"),
        )],
    }


def walk_forward_readiness(protocol: dict[str, Any], calendar: list[dict[str, Any]], cycles: list[dict[str, Any]], *,
                           observed_at: datetime | None = None) -> dict[str, Any]:
    policy = protocol["walk_forward"]
    boundary = instant(observed_at or max((source["known_at"] for cycle in cycles
        for source in cycle["temporal_facts"]["outcome_observations"] if source.get("known_at") is not None),
        default=instant(protocol["declared_at"])))
    sessions = [row for row in calendar if instant(row["close_at"]) <= boundary]
    dates = [row["session_date"] for row in sessions]
    if dates != sorted(set(dates)):
        raise ValueError("WALK_FORWARD_CALENDAR_ROSTER_INVALID")
    if any(instant(row["open_at"]) >= instant(row["close_at"]) for row in sessions):
        raise ValueError("WALK_FORWARD_SESSION_WINDOW_INVALID")
    training = policy["training_sessions"]
    validation = policy["validation_sessions"]
    embargo = policy["embargo_sessions"]
    oos = policy["oos_sessions"]
    required = training + validation + embargo + oos
    if required != policy["minimum_history_sessions"] or min(training, validation, embargo, oos, policy["step_sessions"]) <= 0:
        raise ValueError("WALK_FORWARD_PROTOCOL_WINDOWS_INVALID")
    historical = {row["target_session"]: row for row in cycles if instant(row["temporal_facts"]["target_end"]) <= boundary}
    temporal = {day: temporal_integrity(cycle) for day, cycle in historical.items()}
    usable = {day: _common_inputs(cycle, protocol) for day, cycle in historical.items()}
    blockers = []
    if len(sessions) < required:
        blockers.append("INSUFFICIENT_CAPTURED_TRADING_SESSION_HISTORY")
    folds = []
    # Historical cadence probes are retained. The latest complete window is a
    # separate readiness probe, not a selected successful backtest or a trade.
    endpoints = sorted(set(range(required, len(sessions) + 1, policy["step_sessions"]))
                       | ({len(sessions)} if len(sessions) >= required else set()))
    for end in endpoints:
        window = sessions[end - required:end]
        train_end = training
        validation_end = train_end + validation
        gap_end = validation_end + embargo
        groups = {"training": window[:train_end], "validation": window[train_end:validation_end],
                  "embargo": window[validation_end:gap_end], "oos": window[gap_end:]}
        missing = [str(row["session_date"]) for row in window if row["session_date"] not in historical]
        unavailable = [str(row["session_date"]) for row in window if row["session_date"] in historical
                       and usable[row["session_date"]] == 0]
        cutoff = instant(groups["embargo"][0]["open_at"])
        invalid = []
        oos_start = instant(groups["oos"][0]["open_at"])
        model_invalid = []
        for row in window:
            cycle = historical.get(row["session_date"])
            if cycle is not None:
                identity = cycle["frozen_identities"]["model"]
                if (str(identity["model_version_id"]) != protocol["identities"]["model_version"]["id"]
                        or str(identity["content_sha256"]) != protocol["identities"]["model_version"]["content_sha256"]
                        or instant(cycle["temporal_facts"]["model_recorded_at"]) > oos_start):
                    model_invalid.append(str(row["session_date"]))
                if temporal[row["session_date"]]["state"] != "PASS":
                    invalid.append(str(row["session_date"]))
        for row in groups["training"] + groups["validation"]:
            cycle = historical.get(row["session_date"])
            if cycle is not None:
                source_times = [source.get("known_at") for source in cycle["temporal_facts"]["outcome_observations"]]
                if not source_times or any(value is None or instant(value) > cutoff for value in source_times):
                    invalid.append(str(row["session_date"]))
        folds.append({"sessions": {key: [row["session_date"] for row in values] for key, values in groups.items()},
                      "dataset_pit_cutoff": cutoff, "model_version_id": protocol["identities"]["model_version"]["id"],
                      "missing_canonical_sessions": missing, "invalid_pit_sessions": sorted(set(invalid)),
                      "unavailable_canonical_input_sessions": unavailable,
                      "invalid_model_binding_sessions": model_invalid,
                      "probe_kind": "CURRENT_READINESS" if end == len(sessions) else "HISTORICAL_CADENCE_AUDIT",
                      "state": "READY" if not missing and not unavailable and not invalid and not model_invalid else "NOT_READY"})
    if sum(count > 0 for count in usable.values()) < required or not folds or folds[-1]["state"] != "READY":
        blockers.append("INSUFFICIENT_EXACT_CANONICAL_PIT_DATA_HISTORY")
    return {"WALK_FORWARD_READY": "NO" if blockers else "YES", "protocol_boundary_validation": "PASS",
            "policy": policy, "captured_history_sessions": len(sessions), "canonical_history_sessions": len(historical),
            "usable_canonical_history_sessions": sum(count > 0 for count in usable.values()),
            "required_sessions": required, "folds": folds, "blockers": blockers,
            "observation_cutoff": boundary,
            "execution": "DRY_RUN_ONLY_NO_TRAINING", "partition_authority": "EXISTING_DAILY_DISCOVERY_NOT_FORMAL_LOCKED_OOS"}


def _common_inputs(cycle: dict[str, Any], protocol: dict[str, Any]) -> int:
    """Count available canonical inputs without creating a training sample."""
    labels = {str(row["commitment_id"]): row for row in cycle["labels"]
              if row["metric_code"] == protocol["target_metric_code"]}
    count = 0
    for prediction in cycle["publication"]["predictions"]:
        label = labels.get(str(prediction["commitment_id"]))
        if (label is None or label["value_status"] != "COMPLETE" or label["availability_status"] != "AVAILABLE"
                or prediction["forecast_status"] != "AVAILABLE" or prediction["baseline_status"] != "AVAILABLE"):
            continue
        values = (label["decimal_value"], prediction["point_estimate"], prediction["baseline_point_estimate"])
        if all(value is not None and Decimal(str(value)).is_finite() for value in values):
            count += 1
    return count
