from __future__ import annotations

from datetime import timedelta

from market_regime_alpha.dividend_t.cosco_timing import CoscoTimingEngine, build_sample_cosco_bars


def test_cosco_timing_stale_data_gate_blocks_final_action_after_integrated_evaluation() -> None:
    bars = build_sample_cosco_bars()
    last_bar_time = bars["timestamp"].iloc[-1].to_pydatetime()
    generated_at = last_bar_time + timedelta(minutes=60)

    snapshot = CoscoTimingEngine().evaluate(
        bars,
        data_source="legacy-characterization-fixture",
        is_realtime=False,
        require_fresh=True,
        freshness_limit_minutes=10.0,
        generated_at=generated_at,
    )

    assert snapshot.data_fresh is False
    assert snapshot.freshness_status == "stale"
    assert snapshot.signal_blocked is True
    assert snapshot.action == "WAIT_STALE_DATA"
    assert snapshot.confidence == 0.0
    assert snapshot.decision_trace.freshness_filtered_action == "WAIT_STALE_DATA"
    assert snapshot.decision_trace.final_action == "WAIT_STALE_DATA"
    assert snapshot.decision_trace.final_signal == "HOLD"
    assert any("新鲜度门禁" in reason for reason in snapshot.reasons)


def test_cosco_timing_same_stale_fixture_is_not_blocked_when_freshness_gate_is_disabled() -> None:
    bars = build_sample_cosco_bars()
    last_bar_time = bars["timestamp"].iloc[-1].to_pydatetime()
    generated_at = last_bar_time + timedelta(minutes=60)

    snapshot = CoscoTimingEngine().evaluate(
        bars,
        data_source="legacy-characterization-fixture",
        is_realtime=False,
        require_fresh=False,
        freshness_limit_minutes=10.0,
        generated_at=generated_at,
    )

    assert snapshot.data_fresh is False
    assert snapshot.freshness_status == "stale"
    assert snapshot.signal_blocked is False
    assert snapshot.action != "WAIT_STALE_DATA"
    assert snapshot.decision_trace.freshness_filtered_action == snapshot.action
