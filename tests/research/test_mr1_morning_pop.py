from __future__ import annotations

from datetime import date, datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from market_regime_alpha.research.mr1_morning_pop import (
    MR1ExitTime,
    MR1TargetId,
    build_mr1_targets,
    replay_mr1_fixed_portfolios,
)
from market_regime_alpha.research.tencent_composite_contracts import (
    CompositeBar,
    CompositeSourceKind,
    PreparedCompositeData,
    PreparedCompositeSession,
)


TZ = ZoneInfo("Asia/Shanghai")
SYMBOL = "000001.SZ"
DAY_1 = date(2026, 1, 5)
DAY_2 = date(2026, 1, 6)
DAY_3 = date(2026, 1, 7)


def _bar(day: date, hour: int, minute: int, close: float) -> CompositeBar:
    return CompositeBar(
        symbol=SYMBOL,
        timestamp=datetime(day.year, day.month, day.day, hour, minute, tzinfo=TZ),
        open=close,
        high=close + 0.2,
        low=close - 0.2,
        close=close,
        volume=1.0,
        amount=1.0,
        source=CompositeSourceKind.LOCAL,
    )


def _prepared() -> PreparedCompositeData:
    sessions = tuple(
        PreparedCompositeSession(
            symbol=SYMBOL,
            session_date=day,
            open=10.0,
            high=11.0,
            low=9.0,
            close=10.5,
            amount=1.0,
            reference_price=10.0,
            reference_timestamp=datetime(day.year, day.month, day.day, 14, 50, tzinfo=TZ),
            source_kinds=(CompositeSourceKind.LOCAL,),
        )
        for day in (DAY_1, DAY_2, DAY_3)
    )
    return PreparedCompositeData(
        accepted_symbols=(SYMBOL,),
        common_session_dates=(DAY_1, DAY_2, DAY_3),
        sessions=sessions,
        quality=SimpleNamespace(accepted_symbols=(SYMBOL,)),
        limitations=(),
    )


def test_morning_targets_require_exact_endpoint_and_never_forward_fill() -> None:
    targets = build_mr1_targets(
        prepared=_prepared(),
        bars=(
            _bar(DAY_2, 9, 35, 10.2),
            _bar(DAY_2, 10, 5, 10.4),
            _bar(DAY_2, 10, 30, 10.6),
            _bar(DAY_2, 15, 0, 10.8),
        ),
        decision_dates=(DAY_1,),
    )

    by_target = {item["target_id"]: item for item in targets}
    assert by_target[MR1TargetId.NEXT_SESSION_0935_RETURN.value]["status"] == "AVAILABLE"
    assert by_target[MR1TargetId.NEXT_SESSION_0935_RETURN.value]["value"] == 0.02
    assert by_target[MR1TargetId.NEXT_SESSION_1000_RETURN.value]["status"] == "UNAVAILABLE"
    assert by_target[MR1TargetId.NEXT_SESSION_1000_RETURN.value]["missing_reason"] == "EXACT_ENDPOINT_BAR_MISSING"
    assert by_target[MR1TargetId.NEXT_SESSION_1030_MFE.value]["status"] == "UNAVAILABLE"
    assert by_target[MR1TargetId.NEXT_SESSION_1030_MFE.value]["missing_reason"] == "INCOMPLETE_MORNING_PATH"
    assert by_target[MR1TargetId.MORNING_1030_MFE.value]["status"] == "UNAVAILABLE"


def test_complete_grid_is_required_for_morning_path_and_competing_event_is_ambiguous() -> None:
    bars = tuple(_bar(DAY_2, 9 + (35 + 5 * index) // 60, (35 + 5 * index) % 60, 10.1) for index in range(12))
    targets = build_mr1_targets(prepared=_prepared(), bars=bars, decision_dates=(DAY_1,))
    by_target = {item["target_id"]: item for item in targets}

    assert by_target[MR1TargetId.MORNING_1030_MFE.value]["status"] == "AVAILABLE"
    assert by_target[MR1TargetId.MORNING_TIME_OF_MFE.value]["value"] == 575.0
    assert by_target[MR1TargetId.MORNING_UP_005_DOWN_005_V1.value]["outcome"] == "AMBIGUOUS"


def test_morning_replay_allows_next_day_1455_entry_after_1030_exit() -> None:
    prepared = _prepared()
    targets = build_mr1_targets(
        prepared=prepared,
        bars=(
            _bar(DAY_2, 10, 30, 10.5),
            _bar(DAY_3, 10, 30, 10.5),
        ),
        decision_dates=(DAY_1, DAY_2),
    )
    rankings = tuple(
        {
            "decision_date": day.isoformat(),
            "target_id": "target-r5-decision-reference-to-next-session-close-return-v1",
            "model_id": "fixed-b0",
            "symbol": SYMBOL,
            "eligible_for_ranking": True,
            "rank": 1,
        }
        for day in (DAY_1, DAY_2)
    )
    result = replay_mr1_fixed_portfolios(
        prepared=prepared,
        ranking_rows=rankings,
        target_rows=targets,
        decision_dates=(DAY_1, DAY_2),
        top_k=1,
        exit_time=MR1ExitTime.T_1030,
        cost_scenario="BASE",
    )

    assert {trade["decision_date"] for trade in result.trades} == {DAY_1.isoformat(), DAY_2.isoformat()}
    assert not any(row["reason_code"] == "ACTIVE_POSITION_CASH_LOCKED" for row in result.orders)


def test_missing_target_keeps_its_fixed_slot_weight_as_cash() -> None:
    prepared = _prepared()
    targets = tuple(
        row
        for row in build_mr1_targets(
            prepared=prepared,
            bars=(_bar(DAY_2, 10, 30, 11.0),),
            decision_dates=(DAY_1,),
        )
        if row["symbol"] == SYMBOL
    )
    rankings = (
        {"decision_date": DAY_1.isoformat(), "target_id": "target-r5-decision-reference-to-next-session-close-return-v1", "model_id": "fixed-b0", "symbol": SYMBOL, "eligible_for_ranking": True, "rank": 1},
    )
    result = replay_mr1_fixed_portfolios(
        prepared=prepared, ranking_rows=rankings, target_rows=targets, decision_dates=(DAY_1,), top_k=2,
        exit_time=MR1ExitTime.T_1030, cost_scenario="BASE",
    )

    assert result.daily_equity[0]["cash_ratio"] == 0.5
    assert result.daily_equity[0]["missing_weight"] == 0.0
    assert result.trades[0]["slot_weight"] == 0.5
