from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from market_regime_alpha.dividend_t.macd_event_rehearsal import (
    run_controlled_event_rehearsal,
    write_controlled_event_rehearsal,
)
from market_regime_alpha.dividend_t.macd_experiments import CounterfactualEventType


def test_controlled_rehearsal_exercises_non_empty_four_arm_events_and_intents() -> None:
    rehearsal = run_controlled_event_rehearsal()

    counts = Counter(event.event_type for events in rehearsal.events_by_profile.values() for event in events)
    assert counts[CounterfactualEventType.UNCHANGED] > 0
    assert counts[CounterfactualEventType.SCORE_SUPPRESSED] > 0
    assert counts[CounterfactualEventType.POLICY_DOWNGRADED] > 0
    assert counts[CounterfactualEventType.POLICY_SIZED] > 0

    assert {
        "MEAN_REVERSION_T_BUY",
        "MEAN_REVERSION_T_SELL",
        "TREND_FOLLOWING_BUY",
        "RISK_REDUCTION_HARD",
        "RISK_REDUCTION_SOFT",
    } <= rehearsal.intent_buckets
    assert rehearsal.execution_checks["suspension_skip"].passed
    assert rehearsal.execution_checks["t1_lock"].passed
    assert rehearsal.execution_checks["limit_up"].passed
    assert rehearsal.execution_checks["limit_down"].passed
    assert rehearsal.execution_checks["cash_limit"].passed
    assert rehearsal.execution_checks["sized_paths"].passed

    sized = [
        event
        for events in rehearsal.events_by_profile.values()
        for event in events
        if event.event_type is CounterfactualEventType.POLICY_SIZED
    ]
    assert all(event.adjusted_path_executable and event.original_path_executable for event in sized)
    assert all(event.adjusted_path_shares < event.original_path_shares for event in sized)


def test_controlled_rehearsal_writes_immutable_rehearsal_artifact(tmp_path: Path) -> None:
    artifact = write_controlled_event_rehearsal(tmp_path, run_id="nonempty-event-fixture-v1")

    manifest = json.loads((artifact / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["classification"] == "REHEARSAL"
    assert manifest["sealed_test_accessed"] is False
    assert (artifact / "COMPLETED").is_file()
    assert (artifact / "execution_evidence.json").is_file()
    audit_path = artifact / "audit" / "report.json"
    assert audit_path.is_file()
    assert "NaN" not in audit_path.read_text(encoding="utf-8")
    assert json.loads(audit_path.read_text(encoding="utf-8"))["sell_side_gap"]["hard_risk_exit"]["count"] > 0
    for profile in ("baseline", "score-only", "policy-only", "full"):
        assert (artifact / profile / "counterfactual_events.jsonl").read_text(encoding="utf-8").strip()
